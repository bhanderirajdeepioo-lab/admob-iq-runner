"""GA4 "💸 Install value" tab — the engine (pure: no I/O, no prints, no clock of its own).

What it answers (SPEC_AB_FINAL §0):
  B. per install week (Monday–Sunday, GA4 days): installs, Google Ads spend, cost per install, how much came back per
     ₹100 of ads after 1 / 7 / 30 / 90 / 180 / 365 days, and in how many days all of it came back — observed where the
     week is old enough, else ≈ projected from the app's own older weeks (median shape + a 20–80% band);
  A. per country: out of 100 installs how many came back next day / after a week / after 30 days, what one install
     earned after 1 / 7 / 30 / 90 days, a verdict and one Hinglish sentence.

Inputs: the app's GA4 store (history_start, time_zone, property / stream), its install-day file `ida` (written by
fetch.ga4_uninstall.fetch_iday: `x` per install day from Q-B, `c` per install week × country from Q-C with the
measured unassigned `gap`, and a ledger `days` per activity day), the AdMob all-source revenue of the app (the money
truth: GA4 only SPLITS it, scaled per activity month with k = AdMob ÷ GA4 — countries use the same k), Google Ads spend
+ installs per day (raw source currency) and an FX series. Every number is a ratio of sums; unknown = None, never 0;
an estimate carries ≈, a projection is marked.

Alerts (pay_slow, pay_loss, geo_move, geo_cost, iv_link) are evaluated once per settled week end. They keep the
Active tab's rules against floods: the first evaluation, a new input (28-day burn-in) and a moved GA4 stream are
seeded (shown, never sent); hourly re-runs with the same week end change nothing.

Behind flags, both off by default (SPEC_CD_GEO; off = every output exactly as before): GADS_GEO hands the engine
Google Ads cost per country as a week envelope (_Geo: a week's cost is used only while Google Ads' own country total
covers its campaign cost) — a country's cost per install, its money back and geo_cost; VALUE_CD adds C (new users by
the app version of their install day) and D (long-term by install month) from engine.value_cd, with ver_ret / long_ret
on the same episode rules (dedupe per family group: DEDUP).

Dates in texts come from uninstall.fmt_span / fmt_day (the page formats ISO dates itself); no date literal lives here.
"""

import bisect
import math
import re
from datetime import timedelta

from ..alerting.rules import fingerprint
from . import active as act
from . import attrib
from . import impact as imp
from . import uninstall as U

VALUE_V = 1
T = (0, 1, 3, 7, 14, 30, 60, 90, 180, 365)       # the ages (days after install) every curve is read at
ULAGS = (0, 1, 3, 7, 14, 30, 45, 60, 90, 120, 180, 270, 365)     # x[X].u slots (mirrors the fetch module)
RBANDS = ((0, 0), (1, 1), (2, 3), (4, 7), (8, 14), (15, 30), (31, 60), (61, 90), (91, 180), (181, 365))
CLAGS = (1, 3, 7, 14, 30, 60, 90)                  # c[W][slot].u slots
CBANDS = RBANDS[:8]                                # c[W][slot].r bands (≤ 90 days)
H_ALLOWED = (30, 60, 90, 180, 365)
H_DEFAULT = 90
SPEND_MIN_WEEK = 20                                # USD: less is "thoda kharcha — faisla nahi"
N_MIN_WEEK = 100
WIN_WEEKS = 4
WIN_WEEKS_SMALL = 12
RANK_MIN = 3
CTY_SHOW = 50
CTY_JUDGE = 300
CTY_RPI_RANK = 1000
CTY_MIN_RET = 10
CTY_MAX_LAG = 90
GAP_MAX = 0.02
WILSON_Z = 1.645
PHI_DEFAULT = 2.0
PHI_MIN_WEEKS = 8
PHI_CAP = 10
REF_WEEKS = 26
REF_MIN = 6
REF_MIN_N = 300
BAND_Q = (0.2, 0.8)
PORTF_MIN_APPS = 4
EST_HALF = 0.25
RANK_HALF = 0.30
K_OK = (0.8, 1.25)
K_CLAMP = (0.5, 2.0)
K_MIN_DAYS = 14
K_MIN_USD = 20
PAY_REL_DN = 0.8
PAY_REL_UP = 1.25
PAY_Z = 3
PAY_WEEK_REL = 0.1
PAY_MOVE_DAYS = 7
PAY_MOVE_REL = 0.25
PAY_NULL_WEEKS = 26
PAY_NULL_MIN = 12
PAY_SIGMA_FLOOR = 0.08
LOSS_BIG_SPEND = 100
GEO_TOPK = 8
GEO_MIN_SHARE = 0.05
GEO_MIN_WEEK_N = 300
GEO_MINPP = {1: 5, 7: 3, 30: 2}
GEO_MINREL = 0.15
GEO_RPI_REL = 0.30
GEO_Z = 3
GEO_WARN_Z = 5
GEO_WARN_SHARE = 0.20
GEO_APPWIDE = 0.5
GEOCOST_MIN_SPEND = 50
GEOCOST_SHARE = 0.05
GEOCOST_WARN_SHARE = 0.25
LINK_DROP = 0.7
LINK_MIN_REV = 50
BURNIN_DAYS = 28
CLOSE_WEEKS = 2
CLOSED_KEEP_DAYS = 400
# the engine's own (not in the spec's list; every one is exported in CONSTS too)
PAY_BASE_WEEKS = 8                                 # "the 8 weeks before"
PAY_BASE_MIN = 6                                   # … at least 6 of them judged
PAY_MIN_N = 300                                    # installs a week for a pay_slow judgement
TILE_WEEKS = 4
MAYBE_Z = 2.0
MAYBE_REL = 0.10
FRESH_DAYS = 14
INFO_PTS = 10                                      # a share moved ≥ 10 points: an info row / a "mix" tag
TAG_REL = 0.15                                     # "cpi" / "value" tags: ≥ 15%
IAP_SHOW = 0.01
SCALE_WEEKS = 26
GAP_WEEKS = 12
TREND_WEEKS = 12
DOUBLE_LOG = 1.5                                   # GA4 ÷ AdMob ≥ 1.5 for ≥ 8 weeks: ad revenue logged twice?
DOUBLE_WEEKS = 8
OK_SHARE = 0.9
INPUT_IDAY_WEEKS = 12                              # the iday input "arrives" with 12 complete weeks at t = 7
INPUT_CTY_WEEKS = 10                               # the cty input with 10 clean country weeks at D30
PAY_DEDUP_DAYS = 7
DAYS_PER_FETCH = 60                                # the backfill's ~120 calls ≈ 60 days with countries
K_WEEK_DAYS = 4                                    # k per activity WEEK: ≥ 4 GA4 days with both sides known …
K_POOL_WEEKS = 4                                   # … a thin week (< $20 a side) pooled with ≤ ±4 neighbours
ADS_STALE_DAYS = 14                                # the newest judged ads week ended > 14 days before E: ads stopped
CPI_JUMP = 1.5                                     # the newest judged week's cost per install ≥ 1.5× (or ≤ 1/1.5×)
                                                   # its 8 judged weeks before: the cost tile says "maybe" at once
CTY_ALPHA = 0.05                                   # country Top / Low: one-sided 5%, Bonferroni over the judged ones
CTY_MIN_DF = 3                                     # … a t-quantile with ≥ 3 degrees of freedom (≥ 4 weeks)
REOPEN_SEED_DAYS = {"pay_loss": 91, "geo_move": 42}   # a reopen this soon after its close: shown, never sent again

GOOD = ("ok", "q", "empty")                        # a folded Q-B day
CGOOD = ("ok", "smp", "gap")                       # a folded Q-C day
FAMILIES = ("pay_slow", "pay_loss", "geo_move", "geo_cost", "iv_link", "ver_ret", "long_ret")
SEV_ORDER = {"warning": 0, "watch": 1, "good": 2}
UNIT = {"pay_slow": "per100", "pay_loss": "days", "geo_move": "pp", "geo_cost": "usd", "iv_link": "pct",
        "ver_ret": "pp", "long_ret": "pp"}
INPUTS = {"pay_slow": ("iday", "spend", "k"), "pay_loss": ("iday", "spend", "k"), "geo_move": ("iday", "cty"),
          "geo_cost": ("cty", "geo", "spend"), "iv_link": ("iday", "k"),
          "ver_ret": ("iday", "ver"), "long_ret": ("iday", "long")}      # (+ "k" when an earning metric leads)
RPI_METRICS = ("rpi7", "rpi180")                   # an earning metric: unit usd, and the AdMob scale is an input
# Google Ads cost by country (GADS_GEO, the week envelope of value_build._app_geo): a week's country cost is used only
# when Σ country cost ÷ campaign cost lies in [GEO_COV_MIN, GEO_COV_MAX]; UNMAPPED = cost Google Ads could not place in
# a country (counted in totals, shown, never judged). Exported in consts only while GADS_GEO is on (value_build.consts)
GEO_COV_MIN = 0.97
GEO_COV_MAX = 1.03
# … or when the two differ by no more than the cache's own rounding: each country-week cell keeps 1/100 of the
# currency (half a unit of error at most), so value_build puts the bound of the week's cells into the envelope ("tol",
# USD); GEO_COV_ABS is the floor (and the bound of an envelope without "tol"). A trickle week (a few paise after a
# campaign stopped) can miss 3% by that rounding alone and must not hide a whole window's country cost — but a week
# with real cost missing (more than the rounding can explain) is not covered, however small
GEO_COV_ABS = 0.05
UNMAPPED = "XX"
# a week whose "Other / unmapped" cost is more than 1 − GEO_COV_MIN of its campaign cost (a failed country map) is not
# covered either: Google Ads' cost is there, but not in any country — never read as "No ads here" in a real country
# ── a country's cost is JUDGED (Keep / Slow / Costly, money back, ₹ per ₹100 and geo_cost) only when ads there are more
# than a trickle: ≥ SPEND_MIN_WEEK USD a window week on average, ≥ GEO_DL_MIN Google Ads downloads in the window and ads
# bringing ≥ GEO_PAID_MIN of its new users — else "Little ads" (its cost shown, the no-cost verdict, no alert). The
# blended cost of a country where ads buy 1% of the installs says nothing about whether those ads pay back
GEO_DL_MIN = 50
GEO_PAID_MIN = 0.3
GEO_XX_NOADS = 0.005            # unmapped above this share of the window's cost: a country with no cost of its own is
                                # "unknown" (its cost may sit in the unmapped part), never "No ads here"
GEO_BACK_REL = 0.15             # a country's money back is "seen" only when the earning weeks' own cost per install is
                                # within ±15% of the window's (the ₹ back per ₹100 uses those weeks' own cost)
GEOCOST_DEDUP_DAYS = 7          # one geo_cost notification per app per 7 days (the rest shown, not sent)
# one notification per app, family group and direction per N days (episodes): the pay_* rule, generalised
VER_DEDUP_DAYS = 7
LONG_DEDUP_DAYS = 28
NWORD = {1: "agle din", 7: "hafte baad", 30: "30 din baad"}
NAMES = {"US": "United States", "IN": "India", "GB": "United Kingdom", "DE": "Germany", "FR": "France", "BR": "Brazil", "ID": "Indonesia",
         "PK": "Pakistan", "BD": "Bangladesh", "NG": "Nigeria", "PH": "Philippines", "VN": "Vietnam", "TH": "Thailand",
         "MX": "Mexico", "TR": "Turkey", "EG": "Egypt", "RU": "Russia", "IT": "Italy", "ES": "Spain", "CA": "Canada",
         "AU": "Australia", "JP": "Japan", "KR": "South Korea", "SA": "Saudi Arabia", "AE": "United Arab Emirates", "MY": "Malaysia",
         "ZA": "South Africa", "KE": "Kenya", "NP": "Nepal", "LK": "Sri Lanka", "IR": "Iran", "IQ": "Iraq",
         "DZ": "Algeria", "MA": "Morocco", "CO": "Colombia", "AR": "Argentina", "PE": "Peru", "CL": "Chile",
         "PL": "Poland", "NL": "Netherlands", "UA": "Ukraine", "RO": "Romania", "TW": "Taiwan", "HK": "Hong Kong",
         "SG": "Singapore", "CN": "China", "MM": "Myanmar", "KH": "Cambodia", "ET": "Ethiopia", "GH": "Ghana",
         "TZ": "Tanzania", "UG": "Uganda", "VE": "Venezuela", "EC": "Ecuador", "PT": "Portugal", "SE": "Sweden",
         "CH": "Switzerland", "BE": "Belgium", "AT": "Austria", "IL": "Israel", "--": "Unknown", "ZZ": "Other countries"}

CONSTS = {k.lower(): (list(v) if isinstance(v, tuple) else (dict(v) if isinstance(v, dict) else v)) for k, v in dict(
    VALUE_V=VALUE_V, T=T, ULAGS=ULAGS, RBANDS=[list(b) for b in RBANDS], CLAGS=CLAGS, H_ALLOWED=H_ALLOWED,
    SPEND_MIN_WEEK=SPEND_MIN_WEEK, N_MIN_WEEK=N_MIN_WEEK, WIN_WEEKS=WIN_WEEKS, WIN_WEEKS_SMALL=WIN_WEEKS_SMALL,
    RANK_MIN=RANK_MIN, CTY_SHOW=CTY_SHOW, CTY_JUDGE=CTY_JUDGE, CTY_RPI_RANK=CTY_RPI_RANK, CTY_MIN_RET=CTY_MIN_RET,
    CTY_MAX_LAG=CTY_MAX_LAG, GAP_MAX=GAP_MAX, WILSON_Z=WILSON_Z, PHI_DEFAULT=PHI_DEFAULT, PHI_MIN_WEEKS=PHI_MIN_WEEKS,
    PHI_CAP=PHI_CAP, REF_WEEKS=REF_WEEKS, REF_MIN=REF_MIN, REF_MIN_N=REF_MIN_N, BAND_Q=BAND_Q,
    PORTF_MIN_APPS=PORTF_MIN_APPS, EST_HALF=EST_HALF, RANK_HALF=RANK_HALF, K_OK=K_OK, K_CLAMP=K_CLAMP,
    K_MIN_DAYS=K_MIN_DAYS, K_MIN_USD=K_MIN_USD, PAY_REL_DN=PAY_REL_DN, PAY_REL_UP=PAY_REL_UP, PAY_Z=PAY_Z,
    PAY_WEEK_REL=PAY_WEEK_REL, PAY_MOVE_DAYS=PAY_MOVE_DAYS, PAY_MOVE_REL=PAY_MOVE_REL, PAY_NULL_WEEKS=PAY_NULL_WEEKS,
    PAY_NULL_MIN=PAY_NULL_MIN, PAY_SIGMA_FLOOR=PAY_SIGMA_FLOOR, LOSS_BIG_SPEND=LOSS_BIG_SPEND, GEO_TOPK=GEO_TOPK,
    GEO_MIN_SHARE=GEO_MIN_SHARE, GEO_MIN_WEEK_N=GEO_MIN_WEEK_N, GEO_MINPP={str(k): v for k, v in GEO_MINPP.items()},
    GEO_MINREL=GEO_MINREL, GEO_RPI_REL=GEO_RPI_REL, GEO_Z=GEO_Z, GEO_WARN_Z=GEO_WARN_Z, GEO_WARN_SHARE=GEO_WARN_SHARE,
    GEO_APPWIDE=GEO_APPWIDE, GEOCOST_MIN_SPEND=GEOCOST_MIN_SPEND, GEOCOST_SHARE=GEOCOST_SHARE,
    GEOCOST_WARN_SHARE=GEOCOST_WARN_SHARE, LINK_DROP=LINK_DROP, LINK_MIN_REV=LINK_MIN_REV, BURNIN_DAYS=BURNIN_DAYS,
    CLOSE_WEEKS=CLOSE_WEEKS, CLOSED_KEEP_DAYS=CLOSED_KEEP_DAYS, PAY_BASE_WEEKS=PAY_BASE_WEEKS,
    PAY_BASE_MIN=PAY_BASE_MIN, PAY_MIN_N=PAY_MIN_N, TILE_WEEKS=TILE_WEEKS, MAYBE_Z=MAYBE_Z, MAYBE_REL=MAYBE_REL,
    IAP_SHOW=IAP_SHOW, TREND_WEEKS=TREND_WEEKS, K_WEEK_DAYS=K_WEEK_DAYS, K_POOL_WEEKS=K_POOL_WEEKS,
    ADS_STALE_DAYS=ADS_STALE_DAYS, CPI_JUMP=CPI_JUMP, CTY_ALPHA=CTY_ALPHA, CTY_MIN_DF=CTY_MIN_DF,
    REOPEN_SEED_DAYS=dict(REOPEN_SEED_DAYS)).items()}

# added after CONSTS on purpose: CONSTS (and so dashboard["value"]["consts"] / asset_v) stays exactly as it was while
# GADS_GEO and VALUE_CD are off — value_cd.CONSTS carries the whole table when VALUE_CD is on
REOPEN_SEED_DAYS.update(geo_cost=42, long_ret=91)
DEDUP = {"pay": (("pay_slow", "pay_loss"), PAY_DEDUP_DAYS), "ver": (("ver_ret",), VER_DEDUP_DAYS),
         "long": (("long_ret",), LONG_DEDUP_DAYS), "geo": (("geo_cost",), GEOCOST_DEDUP_DAYS)}
DEDUP_OF = {f: g for g, (fams, _) in DEDUP.items() for f in fams}

ONE = timedelta(days=1)


# ── small helpers ───────────────────────────────────────────────────────────────────────────────

def _d(s):
    return U._d(s)


def _iso(d):
    return d.isoformat() if d else None


def _mon(d):
    return d - timedelta(days=d.weekday())


def _g4(x):
    """Ratios: 4 significant digits."""
    return None if x is None else float("%.4g" % x)


def _m6(x):
    """Money: 6 significant digits (per-install values are tiny)."""
    return None if x is None else float("%.6g" % x)


def _int(x):
    return None if x is None else int(round(x))


def _med(v):
    return U.median(list(v))


def _quant(v, p):
    """Linear-interpolated quantile p of v (None when empty)."""
    v = sorted(v)
    n = len(v)
    if not n:
        return None
    pos = p * (n - 1)
    i = int(math.floor(pos))
    j = min(i + 1, n - 1)
    return v[i] + (v[j] - v[i]) * (pos - i)


def _pad(v, n):
    v = list(v or [])[:n]
    return [(x or 0) for x in v] + [0] * (n - len(v))


def _mkey(d):
    return "%04d-%02d" % (d.year, d.month)


def _mnum(k):
    y, m = k.split("-")
    return int(y) * 12 + int(m) - 1


def usd(v, sym="$"):
    """A per-install / small amount exactly as the page's valMoney writes it: ≥ 0.1 → 2 dp ("$0.15"), ≥ 0.01 → 3 dp
    ("$0.021"), else 2 significant digits ("$0.0042") — never "<$0.01", never a "$0.00" that reads as zero."""
    if v is None:
        return "—"
    a = abs(v)
    if a >= 0.1:
        s = "{:,.2f}".format(a)
    elif a >= 0.01:
        s = "%.3f" % a
    elif a == 0:
        s = "0"
    else:
        s = ("%.2g" % a)
        if "e" in s:
            s = "%.10f" % float(s)
        s = s.rstrip("0").rstrip(".") if "." in s else s
    return ("-" if v < 0 else "") + sym + s


def usd_big(v, sym="$"):
    """A spend total as the page's valBig writes it: "$1,234" (≥ 10) or "$4.20"."""
    if v is None:
        return "—"
    return sym + ("{:,.0f}".format(v) if abs(v) >= 10 or v == 0 else "%.2f" % v)


def per100(v, sym="$"):
    """Back per 100 of ads as the page's valP100 writes it: "$42", "$4.3", "$0.04" (a small value never reads $0)."""
    if v is None:
        return "—"
    a = abs(v)
    if a >= 10:
        s = "{:,.0f}".format(a)
    elif a >= 1:
        s = ("%.1f" % a).rstrip("0").rstrip(".")
    elif a == 0:
        s = "0"
    else:
        s = "%.2g" % a
        if "e" in s:
            s = "%.10f" % float(s)
    return ("-" if v < 0 else "") + sym + s


def cname(cc):
    return NAMES.get(cc, cc)


# Money and country names in the engine's sentences are TOKENS, drawn by the page in the viewer's currency ($ ⇄ ₹,
# Google Ads spend in the rupees it billed) and with the page's own country names; render_text writes them out for
# the Telegram / email message (the report currency). {m:v} per-install USD · {b:v} a USD total · {s:usd|src} a Google
# Ads spend total (src: the source currency it billed) · {q:usd|src} a per-install Google Ads cost · {p:v} back per
# 100 of ads · {c} the currency sign · {cc:XX} a country.
TOKEN_RE = re.compile(r"\{(m|b|s|q|p|cc|c)(?::([^{}]*))?\}")


def _tn(v):
    return "%.6g" % v


def t_m(v):
    return "—" if v is None else "{m:%s}" % _tn(v)


def t_b(v):
    return "—" if v is None else "{b:%s}" % _tn(v)


def t_s(v, src=None):
    return "—" if v is None else ("{s:%s|%s}" % (_tn(v), _tn(src)) if src is not None else "{s:%s}" % _tn(v))


def t_q(v, src=None):
    return "—" if v is None else ("{q:%s|%s}" % (_tn(v), _tn(src)) if src is not None else "{q:%s}" % _tn(v))


def t_p(v):
    return "—" if v is None else "{p:%s}" % _tn(v)


def t_cc(cc):
    return "{cc:%s}" % cc


T_C = "{c}"


def render_text(text, ccy="USD", usd_inr=None, src_ccy=None):
    """A sentence's tokens written out in the report currency (the Telegram / email message; the page draws its own)."""
    inr = ccy == "INR" and bool(usd_inr)
    sym = "₹" if inr else "$"
    mul = float(usd_inr) if inr else 1.0

    def one(m):
        k, a = m.group(1), m.group(2)
        if k == "c":
            return sym
        if k == "cc":
            return cname(a or "")
        parts = (a or "").split("|")
        try:
            v = float(parts[0])
            src = float(parts[1]) if len(parts) > 1 and parts[1] != "" else None
        except ValueError:
            return "—"
        if k in ("s", "q") and inr and src is not None and src_ccy == "INR":
            return (usd_big if k == "s" else usd)(src, sym)
        if k == "m" or k == "q":
            return usd(v * mul, sym)
        if k in ("b", "s"):
            return usd_big(v * mul, sym)
        return per100(v, sym)
    return TOKEN_RE.sub(one, text or "")


def _span(a, b, ref):
    return U.fmt_span(a, b, ref)


def _pct(x):
    return "%d%%" % int(round(100 * x))


# ── AdMob scale (§1.6) ──────────────────────────────────────────────────────────────────────────

def scale(ida, rev, tz, hs, S, ded_rate=None):
    """GA4 ad revenue per GA4 day (the ledger's Q-T `rev`, all install ages) vs AdMob all-source revenue on the same
    GA4 days → the scale k = ΣAdMob ÷ ΣGA4 per activity WEEK (a GA4-side step — a Firebase link, consent, an SDK —
    moves only its own week, never the rest of a month), clamped to K_CLAMP; a raw k outside K_OK makes what it scales ≈.
      * AdMob per GA4 day is Active's known-day rule (active._rev_series): a day is known with its row (or, for the
        network report, a day its account reported), or as a one-day hole between rows — a day with no row is never
        read as $0 (an account's stalled report is "not in yet", never "earned nothing").
      * A week needs ≥ K_WEEK_DAYS days with both sides and ≥ $20 on each: a thinner week is pooled with its ≤ ±4
        neighbours ("pool"); a week without AdMob days takes its nearest valid week ("near" — "nomob" and ≈ when GA4 has
        the days but AdMob does not); none at all: k = 1 ("none", ≈).
    Also the weekly GA4 ÷ AdMob line of the Data check (a week whose AdMob side is not in: admob / r null)."""
    days = (ida or {}).get("days") or {}
    src = "all" if (rev or {}).get("all_days") else ("network" if (rev or {}).get("days") else None)
    mult = (1.0 - ded_rate) if ded_rate else 1.0
    G, M = {}, {}
    span = []
    d = hs
    while d <= S:
        span.append(d)
        e = days.get(d.isoformat())
        if isinstance(e, dict) and e.get("rev") is not None:
            G[d] = float(e["rev"]) / 1e6
        d += ONE
    if src and span:
        vals, _ = act._rev_series(rev, "all_days" if src == "all" else "days", tz, span)
        for d, v in zip(span, vals or ()):
            if v is not None:
                M[d] = float(v) * mult
    acc = {}
    for d, g in G.items():
        m = M.get(d)
        if m is None:
            continue
        a = acc.setdefault(_mon(d), [0.0, 0.0, 0])
        a[0] += m
        a[1] += g
        a[2] += 1
    gdays = {}
    for d in G:
        gdays[_mon(d)] = gdays.get(_mon(d), 0) + 1

    def good(a):
        return a is not None and a[2] >= K_WEEK_DAYS and a[0] >= K_MIN_USD and a[1] >= K_MIN_USD and a[1] > 0
    weeks_all, W = [], _mon(hs)
    while W <= S:
        weeks_all.append(W)
        W += timedelta(days=7)
    valid = {W: acc[W][0] / acc[W][1] for W in weeks_all if good(acc.get(W))}
    kinfo = {}
    for i, W in enumerate(weeks_all):
        a = acc.get(W)
        if W in valid:
            raw, flag = valid[W], "ok"
        else:
            raw, flag = None, None
            if a is not None and a[2] >= K_WEEK_DAYS:          # both sides there, only thin: pool with neighbours
                for r in range(1, K_POOL_WEEKS + 1):
                    pool = [acc[x] for x in weeks_all[max(0, i - r):i + r + 1] if x in acc]
                    tot = [sum(p[0] for p in pool), sum(p[1] for p in pool), sum(p[2] for p in pool)]
                    if good(tot):
                        raw, flag = tot[0] / tot[1], "pool"
                        break
            if raw is None and valid:
                near = min(valid, key=lambda v: (abs((v - W).days), v))
                nomob = gdays.get(W, 0) >= K_WEEK_DAYS and (a is None or a[2] < K_WEEK_DAYS)
                raw, flag = valid[near], ("nomob" if nomob else "near")
            if raw is None:
                tot = [sum(p[0] for p in acc.values()), sum(p[1] for p in acc.values()), sum(p[2] for p in acc.values())]
                if good(tot):
                    raw, flag = tot[0] / tot[1], "pool"
                else:
                    raw, flag = 1.0, "none"
        k = min(max(raw, K_CLAMP[0]), K_CLAMP[1])
        kinfo[W] = (k, flag, flag in ("none", "nomob") or not (K_OK[0] <= raw <= K_OK[1]), raw)
    first_w, last_w = weeks_all[0], weeks_all[-1]

    def kf(day):
        W = _mon(day)
        return kinfo[min(max(W, first_w), last_w)]
    weeks = []
    W = _mon(hs)
    while W + timedelta(days=6) <= S:
        if W >= hs:
            ds = [W + timedelta(days=i) for i in range(7)]
            if all(x in G for x in ds):
                g = sum(G[x] for x in ds)
                m = sum(M[x] for x in ds) if all(x in M for x in ds) else None
                weeks.append({"from": _iso(W), "to": _iso(W + timedelta(days=6)), "ga4": _m6(g), "admob": _m6(m),
                              "r": _g4(g / m) if m else None})
        W += timedelta(days=7)
    recent = [kinfo[W] for W in weeks_all[-13:]]
    st = "none" if not valid else ("est" if any(v[2] for v in recent) else "ok")
    double = sum(1 for w in weeks[-SCALE_WEEKS:] if w["r"] is not None and w["r"] >= DOUBLE_LOG) >= DOUBLE_WEEKS
    return {"kf": kf, "kinfo": kinfo, "weeks_all": weeks_all, "G": G, "M": M, "weeks": weeks, "st": st, "src": src,
            "double": double, "valid": bool(valid), "m_last": max(M) if M else None}


def k_est(sc, a, b):
    """Any activity week in [a, b] scaled with a k outside K_OK (or without AdMob): what it feeds is ≈."""
    if a is None or b is None:
        return False
    W = _mon(a)
    while W <= b:
        v = sc["kinfo"].get(W)
        if v is not None and v[2]:
            return True
        W += timedelta(days=7)
    return False


# ── the per-app data: install days → install weeks (§2.2) ───────────────────────────────────────

class _Pre:
    """Prefix sums over the activity days [hs, S]: complete / ≈ / ok checks in O(1)."""

    def __init__(self, hs, S, days, win_check):
        self.hs, self.S = hs, S
        n = (S - hs).days + 1
        self.n = n
        z = [0] * (n + 1)
        self.g, self.q, self.ok, self.c, self.cs, self.cg = (list(z) for _ in range(6))
        self.win = [None] * n if win_check else None
        for i in range(n):
            e = days.get(_iso(hs + timedelta(days=i)))
            e = e if isinstance(e, dict) else {}
            st, cst = e.get("st"), e.get("cst")
            self.g[i + 1] = self.g[i] + (st in GOOD)
            self.q[i + 1] = self.q[i] + (st == "q")
            self.ok[i + 1] = self.ok[i] + (st in ("ok", "empty"))
            self.c[i + 1] = self.c[i] + (cst in CGOOD)
            self.cs[i + 1] = self.cs[i] + (cst == "smp")
            self.cg[i + 1] = self.cg[i] + (cst == "gap")
            if win_check:
                self.win[i] = e.get("win")

    def _ix(self, a, b):
        a = max(a, self.hs)
        if b > self.S or b < a:
            return None
        return (a - self.hs).days, (b - self.hs).days

    def all(self, arr, a, b):
        ix = self._ix(a, b)
        if ix is None:
            return False
        i, j = ix
        return arr[j + 1] - arr[i] == j - i + 1

    def any(self, arr, a, b):
        ix = self._ix(a, b)
        if ix is None:
            return False
        i, j = ix
        return arr[j + 1] - arr[i] > 0

    def share(self, arr, a, b):
        ix = self._ix(a, b)
        if ix is None:
            return 0.0
        i, j = ix
        return (arr[j + 1] - arr[i]) / (j - i + 1)

    def win_ok(self, first, a, b):
        """flags.qb_win: every activity day D in [a, b] reached lag D − first (a shrunken Q-B window is never read as
        zeros)."""
        if self.win is None:
            return True
        ix = self._ix(a, b)
        if ix is None:
            return False
        for i in range(ix[0], ix[1] + 1):
            w = self.win[i]
            if w is not None and w < (self.hs + timedelta(days=i) - first).days:
                return False
        return True


def settled_day(ida, hs):
    """S_v: the newest activity day whose Q-B read was folded (st ok / q / empty), at or before the ledger's `to` — the
    fetch's `to` is its cursor (the newest day in the ledger, a failed or short read included), so a day it could not
    read yet is never shown as "data till". None when no day at or after `hs` is folded yet."""
    days = (ida or {}).get("days") or {}
    try:
        d, lo = _d(ida["to"]), max(_d(ida.get("from") or ida["to"]), hs)
    except (KeyError, TypeError, ValueError):
        return None
    while d >= lo:
        e = days.get(_iso(d))
        if isinstance(e, dict) and e.get("st") in GOOD:
            return d
        d -= ONE
    return None


def _prep(store, ida, rev, ded_rate, S=None):
    hs = _d(store["history_start"])
    S = S if S is not None else settled_day(ida, hs)
    tz = store.get("time_zone") or ida.get("tz") or "UTC"
    days = ida.get("days") or {}
    flags = ida.get("flags") or {}
    pre = _Pre(hs, S, days, bool(flags.get("qb_win")))
    sc = scale(ida, rev, tz, hs, S, ded_rate)
    kf = sc["kf"]
    xs = {}
    for k, v in (ida.get("x") or {}).items():
        try:
            X = _d(k)
        except (TypeError, ValueError):
            continue
        if X < hs or X > S or not isinstance(v, dict):
            continue
        r, p = _pad(v.get("r"), 10), _pad(v.get("p"), 10)
        cum, est, raw, cp = [], [], [], []
        a = ar = ap = 0.0
        e = False
        for b, (lo, hi) in enumerate(RBANDS):
            kk, _, ke, _ = kf(X + timedelta(days=(lo + hi) // 2))
            ar += r[b] / 1e6
            a += r[b] / 1e6 * kk
            ap += p[b] / 1e6
            e = e or ke
            cum.append(a)
            est.append(e)
            raw.append(ar)
            cp.append(ap)
        xs[X] = {"n": int(v.get("n") or 0), "u": _pad(v.get("u"), 13), "R": cum, "E": est, "Rr": raw, "P": cp}
    weeks, W = [], _mon(hs)
    while W <= S:
        first, last = max(W, hs), W + timedelta(days=6)
        w = {"W": W, "first": first, "last": last, "n": 0, "R": [0.0] * 10, "Rr": [0.0] * 10, "P": [0.0] * 10,
             "E": [False] * 10, "u": [0] * 13}
        X = first
        while X <= min(last, S):
            c = xs.get(X)
            if c:
                w["n"] += c["n"]
                for j in range(10):
                    w["R"][j] += c["R"][j]
                    w["Rr"][j] += c["Rr"][j]
                    w["P"][j] += c["P"][j]
                    w["E"][j] = w["E"][j] or c["E"][j]
                for j in range(13):
                    w["u"][j] += c["u"][j]
            X += ONE
        w["cj"] = [pre.all(pre.g, first, last + timedelta(days=t)) and pre.win_ok(first, first, last + timedelta(days=t))
                   for t in T]
        w["q"] = [pre.any(pre.q, first, last + timedelta(days=t)) for t in T]
        w["okf"] = [pre.share(pre.ok, first, last + timedelta(days=t)) >= OK_SHARE for t in T]
        weeks.append(w)
        W += timedelta(days=7)
    return {"hs": hs, "S": S, "tz": tz, "pre": pre, "sc": sc, "xs": xs, "weeks": weeks, "flags": flags,
            "wk": {w["W"]: w for w in weeks}}


def _fx_fn(fx, ccy):
    """→ fn(day) → USD per 1 unit of the spend currency (the week's own dated rate; weekends / holidays take the
    previous business day; before the series, its first rate), and the mode ("dated" | "one")."""
    if (ccy or "USD") == "USD":
        return (lambda d: 1.0), "dated"
    fx = fx or {}
    series = sorted((k, float(v)) for k, v in ((fx.get("series") or {}).items()) if v)
    now = fx.get("now")
    if not series:
        return (lambda d: now), "one"
    keys = [k for k, _ in series]

    def f(d):
        i = bisect.bisect_right(keys, d.isoformat()) - 1
        return series[max(i, 0)][1]
    return f, "dated"


def _spend_weeks(P, spend, fx):
    """Google Ads spend (USD at each day's rate, and in the currency it billed) and installs per install week (Ads
    dates, account timezone — at week grain the ~5.5 h offset moves ~3% of a week across the boundary: accepted).
    A week's spend is KNOWN only when the whole week lies inside the spend cache's fetched span [first, till] (till =
    the last day a Google Ads fetch went through — a stale cache never reads as $0): otherwise spend / cost / paid share
    are None and the week is never judged (why "wait": not in yet; "unknown": before the cache). No cache at all:
    why "nospend" (Google Ads not connected)."""
    sp = spend or {}
    daily, inst = sp.get("daily") or {}, sp.get("installs") or {}
    f, mode = _fx_fn(fx, sp.get("ccy") or "USD")
    first, till = sp.get("first"), sp.get("till")
    for w in P["weeks"]:
        W, last = w["first"], w["W"] + timedelta(days=6)          # the week's install days (history's first week:
        have = bool(spend) and first is not None and till is not None      # from history_start)
        known = have and _iso(W) >= first and _iso(last) <= till
        s = a = src = 0.0
        miss = False
        if known:
            d = W
            while d <= last:
                k = d.isoformat()
                v = daily.get(k)
                if v:
                    r = f(d)
                    if r is None:
                        miss = True
                    else:
                        s += float(v) / 1e6 * r
                    src += float(v) / 1e6
                a += float(inst.get(k) or 0)
                d += ONE
        w["spend"] = _m6(s) if known and not miss else None
        w["spend_src"] = _m6(src) if known else None
        w["n_ads"] = _int(a) if known else None
        n = w["n"]
        sw = w["spend"]
        w["ecpi"] = sw / n if (sw and n) else None
        w["cpi_ads"] = sw / a if (sw and a) else None
        w["paid"] = min(1.0, a / n) if (known and n) else None
        w["judged"] = bool(sw is not None and sw >= SPEND_MIN_WEEK and n >= N_MIN_WEEK and w["cj"][0])
        if w["judged"]:
            w["why"] = None
        elif not have:
            w["why"] = "nospend"
        elif not known:
            w["why"] = "wait" if _iso(last) > till else "unknown"
        elif miss:
            w["why"] = "wait"
        else:
            w["why"] = "nospend" if not sw else "thin"
    return mode


# ── the not-yet-known tail (§2.3) and money back (§2.4) ────────────────────────────────────────

def _L(w, j):
    return w["R"][j] / w["n"] if (w["cj"][j] and w["n"] > 0) else None


def _t_o(w):
    jo = None
    for j in range(10):
        if w["cj"][j] and w["n"] > 0:
            jo = j
    return jo


class _Shapes:
    """g = L(t) ÷ L(t_o) over the app's reference weeks (newest REF_WEEKS with L(t) complete, N ≥ REF_MIN_N, no ≈
    day, ≥ 90% ok days) → (median, q20, q80, count) per (t_o, t); the portfolio's when the app has < REF_MIN."""

    def __init__(self, weeks, portfolio):
        self.weeks, self.port, self.memo = weeks, portfolio or {}, {}

    def app(self, jo, j):
        k = (jo, j)
        if k not in self.memo:
            g = []
            for w in reversed(self.weeks):
                if not w["cj"][j] or w["n"] < REF_MIN_N or w["q"][j] or not w["okf"][j]:
                    continue
                if w["R"][jo] <= 0:
                    continue
                g.append(w["R"][j] / w["R"][jo])
                if len(g) >= REF_WEEKS:
                    break
            self.memo[k] = ((_med(g), _quant(g, BAND_Q[0]), _quant(g, BAND_Q[1]), len(g))
                            if len(g) >= REF_MIN else (None, None, None, len(g)))
        return self.memo[k]

    def get(self, jo, j):
        a = self.app(jo, j)
        if a[0] is not None:
            return a[:3], "app"
        p = self.port.get("%d→%d" % (T[jo], T[j]))
        if isinstance(p, (list, tuple)) and len(p) == 3 and all(isinstance(x, (int, float)) for x in p):
            return tuple(p), "portfolio"
        return None, None


def _project(w, shapes):
    """→ (observed L[10], med[10], lo[10], hi[10], t_o index, shape source) per install (USD). Beyond t_o the median
    and the 20–80% band come from g; each curve only rises (a running maximum: money back never shrinks)."""
    jo = _t_o(w)
    L = [_L(w, j) for j in range(10)]
    med, lo, hi = [None] * 10, [None] * 10, [None] * 10
    src = None
    if jo is None:
        return L, med, lo, hi, None, None
    base = L[jo]
    for j in range(jo + 1, 10):
        s, how = shapes.get(jo, j)
        if s is None:
            break
        med[j], lo[j], hi[j] = base * s[0], base * s[1], base * s[2]
        src = "portfolio" if (how == "portfolio" or src == "portfolio") else "app"
    for arr in (med, lo, hi):
        top = base
        for j in range(jo + 1, 10):
            if arr[j] is None:
                break
            top = max(top, arr[j])
            arr[j] = top
    return L, med, lo, hi, jo, src


def _cross(pts, c):
    """The first age where the curve reaches c (linear between points), or None."""
    prev = None
    for t, v in pts:
        if v is None:
            return None
        if v >= c:
            if prev is None or v <= prev[1]:
                return float(t)
            return prev[0] + (c - prev[1]) / (v - prev[1]) * (t - prev[0])
        prev = (t, v)
    return None


def _payback(L, med, lo, hi, jo, target):
    """Money back in N days for one judged week (§2.4) → {p, lo, hi, obs, never, pct365, hi_over, rough} or None
    (no projection yet)."""
    out = {"p": None, "lo": None, "hi": None, "obs": False, "never": False, "pct365": None, "hi_over": False,
           "rough": False, "shape": None}
    if jo is None or not target:
        return None
    obs = [(T[j], L[j]) for j in range(jo + 1)]
    p = _cross(obs, target)
    if p is not None:
        out.update(p=int(round(p)), obs=True)
        return out
    if jo == 9:
        out.update(obs=True, never=True, pct365=_g4(100 * L[9] / target))
        return out
    mp = [(T[j], med[j]) for j in range(jo + 1, 10) if med[j] is not None]
    if not mp:
        return None
    pm = _cross(obs + mp, target)
    if pm is None:
        if med[9] is None:
            return None                              # the projection stops before a year: not known yet
        out.update(never=True, pct365=_g4(100 * med[9] / target))
        return out
    plo = _cross(obs + [(T[j], hi[j]) for j in range(jo + 1, 10) if hi[j] is not None], target)
    phi = _cross(obs + [(T[j], lo[j]) for j in range(jo + 1, 10) if lo[j] is not None], target)
    out.update(p=int(round(pm)), lo=None if plo is None else int(round(plo)),
               hi=None if phi is None else int(round(phi)), hi_over=phi is None)
    out["rough"] = bool(phi is None or (plo is not None and (phi - plo) > 3 * max(pm, 1)))
    return out


def _pval(pay):
    """A payback as a number of days for medians / moves: never and "> 365" count as 366."""
    if not pay:
        return None
    if pay["never"]:
        return 366
    return pay["p"]


# ── countries (§2.5) ────────────────────────────────────────────────────────────────────────────

def _wilson(x, n, phi):
    if not n:
        return None, None, None
    ne = n / phi
    p = x / n
    z = WILSON_Z
    den = 1 + z * z / ne
    c = (p + z * z / (2 * ne)) / den
    h = z * math.sqrt(max(p * (1 - p) / ne + z * z / (4 * ne * ne), 0.0)) / den
    return p, max(c - h, 0.0), min(c + h, 1.0)


def _country_data(P, ida):
    """c[W][slot] → {W: {"rows": {cc: {n, u[7], R[8] scaled cum}}, "gap": {n, r[8] micros}, "Rr_gap"}}."""
    cset = [str(c) for c in (ida.get("cset") or [])]
    kf = P["sc"]["kf"]
    out = {}
    for wk, slots in (ida.get("c") or {}).items():
        try:
            W = _d(wk)
        except (TypeError, ValueError):
            continue
        if not isinstance(slots, dict):
            continue
        rows, gap = {}, {"n": 0, "r": [0] * 8}
        for sk, v in slots.items():
            if not isinstance(v, dict):
                continue
            if sk == "gap":
                gap = {"n": v.get("n") or 0, "r": _pad(v.get("r"), 8)}
                continue
            try:
                cc = cset[int(sk)]
            except (ValueError, IndexError):
                continue
            r = _pad(v.get("r"), 8)
            cum, a = [], 0.0
            for b, (lo, hi) in enumerate(CBANDS):
                a += r[b] / 1e6 * kf(W + timedelta(days=3 + (lo + hi) // 2))[0]
                cum.append(a)
            rows[cc] = {"n": int(v.get("n") or 0), "u": _pad(v.get("u"), 7), "R": cum}
        out[W] = {"rows": rows, "gap": gap}
    since = {}
    for cc, rngs in ((ida.get("cset_since") or {}).items()):
        try:
            since[cc] = [(_d(a), _d(b)) for a, b in rngs]
        except (TypeError, ValueError):
            since[cc] = []
    return cset, out, since


def _tj(t):
    return T.index(t)


class _Cty:
    """The country side of one app: which weeks are complete / clean for a horizon t, and pooled sums."""

    def __init__(self, P, ida):
        self.P = P
        self.cset, self.cw, self.since = _country_data(P, ida)
        self.cfrom = _d(ida["cfrom"]) if ida.get("cfrom") else None
        self.smp = bool((ida.get("flags") or {}).get("smp"))

    def complete(self, W, t):
        w = self.P["wk"].get(W)
        if w is None or W not in self.cw or self.cfrom is None or w["first"] < self.cfrom:
            return False
        pre = self.P["pre"]
        return w["cj"][_tj(t)] and pre.all(pre.c, w["first"], w["last"] + timedelta(days=t))

    def part(self, cc, W, t):
        """A slot added later (cset_since): a cell that needed one of the days folded before it is not shown."""
        rngs = self.since.get(cc)
        if not rngs:
            return False
        a, b = W, W + timedelta(days=6 + t)
        return any(not (b < x or a > y) for x, y in rngs)

    def gap_share(self, W, t):
        """(revenue share, installs share) of week W that GA4 did not assign to any country (the measured Q-B −
        Σ named countries), up to age t."""
        w, g = self.P["wk"][W], self.cw[W]["gap"]
        j = _tj(t)
        den = w["Rr"][j]
        num = abs(sum(g["r"][:j + 1])) / 1e6
        gr = num / den if den > 0 else (0.0 if num == 0 else 1.0)
        gn = abs(g["n"]) / w["n"] if w["n"] > 0 else (0.0 if not g["n"] else 1.0)
        return gr, gn

    def clean(self, W, t):
        gr, gn = self.gap_share(W, t)
        return gr <= GAP_MAX and gn <= GAP_MAX

    def weeks(self, t, n=None):
        """The complete weeks for age t, newest first (all of them, or the newest n)."""
        ws = [W for W in sorted(self.cw, reverse=True) if self.complete(W, t)]
        return ws if n is None else ws[:n]


def _cty_sums(C, cc, weeks, t, what):
    """Pooled over weeks: (numerator, installs) — what = "u" (returners at CLAGS age t) or "r" (revenue to t)."""
    x = n = 0.0
    for W in weeks:
        if cc == "All":
            w = C.P["wk"][W]
            n += w["n"]
            x += w["u"][ULAGS.index(t)] if what == "u" else w["R"][_tj(t)]
            continue
        c = C.cw[W]["rows"].get(cc)
        if c is None or C.part(cc, W, t):
            continue
        n += c["n"]
        x += c["u"][CLAGS.index(t)] if what == "u" else c["R"][_tj(t)]
    return x, n


def _phi(C, t, weeks12):
    """Overdispersion φ for the D-t rates: the median over countries (≥ 300 installs a week, ≥ PHI_MIN_WEEKS such
    weeks in the last 12) of Pearson χ² / (m − 1), clamped to [1, PHI_CAP]; PHI_DEFAULT otherwise."""
    vals = []
    for cc in C.cset:
        if cc in ("--", "ZZ"):
            continue
        each = []
        for W in weeks12:
            c = C.cw[W]["rows"].get(cc)
            if c and c["n"] >= CTY_JUDGE and not C.part(cc, W, t):
                each.append((c["u"][CLAGS.index(t)], c["n"]))
        if len(each) < PHI_MIN_WEEKS:
            continue
        x, n = sum(e[0] for e in each), sum(e[1] for e in each)
        p = x / n if n else 0
        if not 0 < p < 1:
            continue
        chi = sum((xw - nw * p) ** 2 / (nw * p * (1 - p)) for xw, nw in each)
        vals.append(chi / (len(each) - 1))
    if not vals:
        return PHI_DEFAULT
    return min(max(_med(vals), 1.0), PHI_CAP)


def _rpi_se(C, cc, t, weeks12, m_win):
    """The residual SE of a pooled earning per install (§2.5) from the last 12 complete weeks."""
    return _rpi_se2(C, cc, t, weeks12, m_win)[0]


def _rpi_se2(C, cc, t, weeks12, m_win):
    """→ (the residual SE, the number of weeks it came from)."""
    ys = []
    for W in weeks12:
        if cc == "All":
            w = C.P["wk"][W]
            ys.append((w["R"][_tj(t)], w["n"]))
            continue
        c = C.cw[W]["rows"].get(cc)
        if c and c["n"] > 0 and not C.part(cc, W, t):
            ys.append((c["R"][_tj(t)], c["n"]))
    ys = [(y, n) for y, n in ys if n > 0]
    if len(ys) < 2 or not m_win:
        return None, len(ys)
    R12 = sum(y for y, _ in ys) / sum(n for _, n in ys)
    nbar = sum(n for _, n in ys) / len(ys)
    s2 = sum(((y - R12 * n) / nbar) ** 2 for y, n in ys) / (len(ys) - 1)
    return math.sqrt(s2) / math.sqrt(m_win), len(ys)


def _rpi_se_rest(C, cc, t, weeks12, m_win):
    """The same residual SE for the rest of the app (every install that is not country cc), week by week."""
    ys = []
    for W in weeks12:
        w = C.P["wk"][W]
        c = C.cw[W]["rows"].get(cc)
        if c is not None and C.part(cc, W, t):
            continue
        y, n = w["R"][_tj(t)] - (c["R"][_tj(t)] if c else 0.0), w["n"] - (c["n"] if c else 0)
        if n > 0:
            ys.append((y, n))
    if len(ys) < 2 or not m_win:
        return None, 0
    R12 = sum(y for y, _ in ys) / sum(n for _, n in ys)
    nbar = sum(n for _, n in ys) / len(ys)
    s2 = sum(((y - R12 * n) / nbar) ** 2 for y, n in ys) / (len(ys) - 1)
    return math.sqrt(s2) / math.sqrt(m_win), len(ys)


def _betacf(a, b, x):
    """The continued fraction of the regularized incomplete beta function (Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-12:
            break
    return h


def _ibeta(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lb) * _betacf(b, a, 1 - x) / b


def t_cdf(t, df):
    """Student's t distribution function."""
    x = df / (df + t * t)
    tail = 0.5 * _ibeta(df / 2.0, 0.5, x)
    return 1.0 - tail if t >= 0 else tail


def t_quant(p, df):
    """The p-quantile of Student's t with df degrees of freedom (bisection; p in (0.5, 1))."""
    lo, hi = 0.0, 1.0
    while t_cdf(hi, df) < p and hi < 1e6:
        hi *= 2
    for _ in range(100):
        mid = (lo + hi) / 2
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _shape_to(shapes, t_from, t_to):
    """App curve g from age t_from to t_to (or the portfolio's)."""
    if t_to == t_from:
        return (1.0, 1.0, 1.0), "app"
    return shapes.get(_tj(t_from), _tj(t_to))


def _countries(P, ida, shapes, H, geo, app_name, prev_sets=None):
    """Countries (§2.5). prev_sets = the Top / Low countries of the previous weekly evaluation: a country is named
    Best / Weakest only when it holds two weekly evaluations in a row."""
    C = _Cty(P, ida)
    G = geo if isinstance(geo, _Geo) else _Geo(geo)
    out = {"win": None, "geo": G.on(), "smp": C.smp, "app": None, "rows": [],
           "small": {"countries": 0, "n": 0, "zz": 0}, "unknown": {"n": 0}, "unassigned": {"n": 0, "rev_share": None},
           "state": "wait", "phi": {}}
    if G.env():                                   # the week envelope (GADS_GEO): why a cost is (not) shown
        out.update(geo_why=None, geo_cov=None, cost=None)
    if not C.cw or C.cfrom is None:
        return out, C, None
    # the window: 4 settled weeks per metric (12 when fewer than RANK_MIN countries have CTY_JUDGE installs)
    nw = WIN_WEEKS
    w1 = C.weeks(1, nw)
    if not w1:
        return out, C, None
    ranked = [cc for cc in C.cset if cc not in ("--", "ZZ") and _cty_sums(C, cc, w1, 1, "u")[1] >= CTY_JUDGE]
    if len(ranked) < RANK_MIN:
        nw = WIN_WEEKS_SMALL
    win = {t: C.weeks(t, nw) for t in (1, 7, 30, 60, 90)}
    w12 = {t: C.weeks(t, TREND_WEEKS) for t in (1, 7, 30, 60, 90)}
    phis = {t: _phi(C, t, [W for W in w12[t] if C.clean(W, t)]) for t in (1, 7, 30)}
    out["phi"] = {str(t): _g4(v) for t, v in phis.items()}
    wd = win[1]
    out["win"] = {"from": _iso(min(wd)), "to": _iso(max(wd) + timedelta(days=6)), "weeks": len(wd),
                  "from30": _iso(min(win[30])) if win[30] else None,
                  "to30": _iso(max(win[30]) + timedelta(days=6)) if win[30] else None, "size": nw}
    n_all = sum(P["wk"][W]["n"] for W in wd)
    clean = {t: all(C.clean(W, t) for W in win[t]) for t in (1, 7, 30, 60, 90)}
    gwhy = G.why(wd) if G.env() else None         # the envelope: country cost over exactly the D1 window's weeks
    xx_big = False                                # a material unmapped part: "no cost here" is not known
    if gwhy == "ok":
        tot = G.total(wd)
        xx_big = tot > 0 and G.cost(UNMAPPED, wd)[0] / tot > GEO_XX_NOADS

    def dmet(cc, N):
        ws = win[N]
        x, n = _cty_sums(C, cc, ws, N, "u")
        if not ws or not n:
            return {"v": None, "lo": None, "hi": None, "n": 0, "st": "none", "ret": 0}
        p, lo, hi = _wilson(x, n, phis[N])
        half = 100 * (hi - lo) / 2
        st = "ok"
        if not clean[N] and cc != "All":
            st = "wait"
        elif cc in ("--", "ZZ") or (cc != "All" and (n < CTY_JUDGE or x < CTY_MIN_RET
                                                      or half > {1: 5, 7: 3, 30: 2}[N])):
            st = "few"
        return {"v": _g4(100 * p), "lo": _g4(100 * lo), "hi": _g4(100 * hi), "n": int(n), "st": st, "ret": int(x),
                "half": half}

    def rmet(cc, t):
        ws = win[t]
        y, n = _cty_sums(C, cc, ws, t, "r")
        if not ws or not n:
            return None
        R = y / n
        se = _rpi_se(C, cc, t, w12[t], len(ws))
        half = None if se is None else WILSON_Z * se
        est = half is None or half > EST_HALF * R or C.smp or (not clean[t] and cc != "All")
        return {"v": _m6(R), "lo": _m6(max(R - half, 0.0)) if half is not None else None,
                "hi": _m6(R + half) if half is not None else None, "est": bool(est), "n": int(n), "y": y,
                "half": half, "proj": False}

    def at_h(cc, obs):
        """Earning per install at the target H (observed when complete, else ≈ projected with the app's curve) →
        {v, lo, hi, proj}."""
        tt = [t for t in (90, 60, 30, 7, 1) if obs.get(t)]
        if H <= 90 and obs.get(H):
            o = obs[H]
            return {"v": o["v"], "lo": o["lo"], "hi": o["hi"], "proj": False, "from": H}
        base = next((t for t in tt if t <= H), None)
        if base is None:
            return None
        s, how = _shape_to(shapes, base, H)
        if s is None:
            return None
        o = obs[base]
        return {"v": _m6(o["v"] * s[0]), "lo": _m6((o["lo"] if o["lo"] is not None else o["v"]) * s[1]),
                "hi": _m6((o["hi"] if o["hi"] is not None else o["v"]) * s[2]), "proj": True, "from": base,
                "shape": how}

    rows, app_obs = [], {t: rmet("All", t) for t in (1, 7, 30, 60, 90)}
    app_d = {N: dmet("All", N) for N in (1, 7, 30)}
    app_h = at_h("All", app_obs)
    hs_by_cc = {}
    for cc in C.cset:
        n = _cty_sums(C, cc, wd, 1, "u")[1]
        if cc == "--":
            out["unknown"]["n"] = int(n)
            continue
        if cc == "ZZ":
            out["small"]["zz"] = int(n)
            out["small"]["n"] += int(n)
            continue
        if n < CTY_SHOW:
            if n > 0:
                out["small"]["countries"] += 1
                out["small"]["n"] += int(n)
            continue
        d = {N: dmet(cc, N) for N in (1, 7, 30)}
        obs = {t: rmet(cc, t) for t in (1, 7, 30, 60, 90)}
        h = at_h(cc, obs)
        hs_by_cc[cc] = h
        r90 = obs[90]
        if r90 is None:                               # beyond the observed ages: always ≈ projected (app's curve)
            bt = next((t for t in (60, 30, 7, 1) if obs.get(t)), None)
            s = _shape_to(shapes, bt, 90)[0] if bt else None
            if s is not None:
                o = obs[bt]
                r90 = {"v": _m6(o["v"] * s[0]), "lo": _m6((o["lo"] if o["lo"] is not None else o["v"]) * s[1]),
                       "hi": _m6((o["hi"] if o["hi"] is not None else o["v"]) * s[2]), "est": True, "proj": True}
        cln = all(clean[t] for t in (1, 7, 30)) and (clean[90] if obs[90] else True)
        row = {"cc": cc, "n": int(n), "share": _g4(n / n_all) if n_all else None, "few": n < CTY_JUDGE,
               "rank": None, "clean": bool(cln),
               "d1": {k: v for k, v in d[1].items() if k in ("v", "lo", "hi", "n", "st")},
               "d7": {k: v for k, v in d[7].items() if k in ("v", "lo", "hi", "n", "st")},
               "d30": {k: v for k, v in d[30].items() if k in ("v", "lo", "hi", "n", "st")},
               "rpi": {str(t): ({"v": o["v"], "lo": o["lo"], "hi": o["hi"], "est": o["est"]} if o else None)
                       for t, o in ((1, obs[1]), (7, obs[7]), (30, obs[30]))},
               "cpi": None, "pay": None, "be": h["v"] if h else None,
               "be_lo": h["lo"] if h else None, "be_hi": h["hi"] if h else None, "be_proj": bool(h and h["proj"]),
               "verdict": "few", "why": None, "sure": False, "text": None, "_obs": obs, "_h": h}
        row["rpi"]["90"] = ({"v": r90["v"], "lo": r90["lo"], "hi": r90["hi"], "proj": bool(r90.get("proj")),
                             "est": bool(r90.get("est"))} if r90 else None)
        if G.env():                                   # the week envelope: only when every window week is covered
            if gwhy == "ok" and n:
                cost, dl = G.cost(cc, wd)
                csrc = G.cost_src(cc, wd)
                if cost > 0:
                    cpi = cost / n
                    row["cpi"] = {"v": _m6(cpi), "ads": _m6(cost / dl) if dl else None, "spend": _m6(cost),
                                  "dl": _m6(dl), "paid": _g4(min(1.0, dl / n)) if dl is not None else None}
                    if csrc is not None:              # the billed currency (the ₹ view: exactly what Ads billed)
                        row["cpi"].update(src=_m6(csrc / n), spend_src=_m6(csrc),
                                          ads_src=_m6(csrc / dl) if dl else None)
                    thin = _geo_thin(cost, dl, n, len(wd))
                    if thin:                          # a trickle of ads: shown, never judged (no-cost verdict)
                        row["cpi"]["thin"] = thin
                    else:
                        row["pay"] = _cty_pay(obs, shapes, cpi, env=True)
                        row["back"], same = _geo_back(C, G, cc, obs, row["rpi"]["90"], win, cpi)
                        if row["pay"] is not None:
                            p = row["pay"]["p"]
                            ts = [t for t in (1, 7, 30, 60, 90) if obs.get(t)]
                            upto = next((t for t in ts if p is not None and t >= p), None)
                            row["pay"]["obs"] = _pay_obs(obs, p) and same(upto)
                elif xx_big:                          # cost Google Ads could not place: this one's may be in it
                    row["cpi"] = {"v": None, "spend": None, "unknown": True}
                else:                                 # no Google Ads cost there: organic installs, never "cheapest"
                    row["cpi"] = {"v": None, "spend": 0.0, "noads": True}
            if "back" not in row:
                row["back"] = None
        else:
            cost, dl = _geo_sum((G.raw or {}).get(cc), wd)
            if cost and n:                            # the cost over exactly the weeks of its installs
                row["cpi"] = {"v": _m6(cost / n), "ads": _m6(cost / dl) if dl else None, "spend": _m6(cost)}
                row["pay"] = _cty_pay(obs, shapes, cost / n)
        rows.append(row)
    # the verdict: the country's earning per install vs the REST of the app (the app without it) at the same age, as
    # two samples — each with its own residual SE over the last 12 weeks — judged with a t-quantile (m − 1 degrees of
    # freedom, ≥ CTY_MIN_DF) and Bonferroni over every country judged; the value's OWN window gates it (a country whose
    # installs just jumped is judged on the older, smaller weeks its value comes from — never on the new count)
    cand = []
    for row in rows:
        h, obs = row["_h"], row["_obs"]
        if h is not None:
            bt = h["from"]
            s = _shape_to(shapes, bt, H)[0] if bt != H else (1.0, 1.0, 1.0)
            cv = h["v"]
        else:
            bt, s = 30, (1.0, 1.0, 1.0)
            o = obs.get(30)
            cv = o["v"] if o else None
        a, o = app_obs.get(bt), obs.get(bt)
        n_val = int(o["n"]) if o else 0
        row["n_val"] = n_val
        row["_bt"], row["_o"], row["_cv"] = bt, o, cv
        excl = None
        if a and o and a["n"] > o["n"] and s is not None:
            excl = (a["y"] - o["y"]) / (a["n"] - o["n"]) * s[0]
        row["_excl"] = excl
        if not row["clean"]:
            row["verdict"], row["why"] = "wait", "gap"
        elif row["n"] < CTY_JUDGE or n_val < CTY_JUDGE:
            row["verdict"], row["why"] = "few", ("few_val" if row["n"] >= CTY_JUDGE else None)
        elif cv is None or excl is None:              # enough installs, the earnings not old enough yet
            row["verdict"], row["why"] = "wait", "young"
        elif (row["cpi"] or {}).get("v") is not None and not row["cpi"].get("thin"):
            row["verdict"] = _cost_verdict(row, H, env=G.env())
            if row["verdict"] == "wait":                  # earnings not old enough for a money back, no curve yet
                row["why"] = "young"
        else:
            se_c, m_c = _rpi_se2(C, row["cc"], bt, w12[bt], len(win[bt]))
            se_r, m_r = _rpi_se_rest(C, row["cc"], bt, w12[bt], len(win[bt]))
            df = min(m_c, m_r) - 1
            if se_c is None or se_r is None or df < CTY_MIN_DF:
                row["verdict"], row["why"] = "wait", "young"
            else:
                rc = o["y"] / o["n"]
                rr = (a["y"] - o["y"]) / (a["n"] - o["n"])
                se = math.sqrt(se_c * se_c + se_r * se_r)
                row["_zt"] = (rc - rr) / se if se > 0 else 0.0
                row["_df"] = df
                cand.append(row)
    for row in cand:
        crit = t_quant(1 - CTY_ALPHA / len(cand), row["_df"])
        row["verdict"] = "top" if row["_zt"] >= crit else ("low" if row["_zt"] <= -crit else "avg")
    rankable = []
    for row in rows:
        o = row["_o"]
        if (row["verdict"] not in ("few", "wait") and row["n_val"] >= CTY_RPI_RANK and o and o["half"] is not None
                and o["half"] <= RANK_HALF * (o["v"] or 0)):
            row["_key"] = row["_cv"]
            rankable.append(row)
    rankable.sort(key=lambda r: (-r["_key"], r["cc"]))
    for i, row in enumerate(rankable):
        row["rank"] = i + 1
    top_now = sorted(r["cc"] for r in rankable if r["verdict"] in ("top", "keep"))
    low_now = sorted(r["cc"] for r in rankable if r["verdict"] in ("low", "costly"))
    pt, pl = set((prev_sets or {}).get("top") or ()), set((prev_sets or {}).get("low") or ())
    best = [r["cc"] for r in rankable if r["verdict"] in ("top", "keep") and r["cc"] in pt][:3]
    weak = [r["cc"] for r in reversed(rankable) if r["verdict"] in ("low", "costly") and r["cc"] in pl][:3]
    for row in rows:
        row["text"] = country_text(row, app_d[1]["v"], H, best, weak)
        row["trend"] = _trend(C, row["cc"], w12)
        if G.env():                                   # cost per install per week (12 weeks): covered weeks only
            row["trend"]["cpi"], src = _trend_cpi(C, G, row["cc"], w12[1])
            if src is not None:                       # … and as billed (the ₹ view)
                row["trend"]["cpi_src"] = src
    # the "All" row and the unassigned part
    out["app"] = {"cc": "All", "n": int(n_all), "share": 1.0 if n_all else None, "clean": all(clean[t] for t in (1, 7, 30)),
                  "d1": {k: v for k, v in app_d[1].items() if k in ("v", "lo", "hi", "n", "st")},
                  "d7": {k: v for k, v in app_d[7].items() if k in ("v", "lo", "hi", "n", "st")},
                  "d30": {k: v for k, v in app_d[30].items() if k in ("v", "lo", "hi", "n", "st")},
                  "rpi": {str(t): ({"v": o["v"], "lo": o["lo"], "hi": o["hi"], "est": o["est"]} if o else None)
                          for t, o in ((1, app_obs[1]), (7, app_obs[7]), (30, app_obs[30]))},
                  "be": app_h["v"] if app_h else None, "be_proj": bool(app_h and app_h["proj"])}
    out["app"]["rpi"]["90"] = ({"v": app_obs[90]["v"], "lo": app_obs[90]["lo"], "hi": app_obs[90]["hi"],
                                "proj": False, "est": app_obs[90]["est"]} if app_obs[90] else None)
    gn = sum(abs(C.cw[W]["gap"]["n"]) for W in wd)
    gw = win[30] or wd
    t_g = 30 if win[30] else 1
    num = sum(abs(sum(C.cw[W]["gap"]["r"][:_tj(t_g) + 1])) for W in gw) / 1e6
    den = sum(P["wk"][W]["Rr"][_tj(t_g)] for W in gw)
    out["unassigned"] = {"n": int(gn), "rev_share": _g4(num / den) if den > 0 else None,
                         "n_share": _g4(gn / n_all) if n_all else None}
    for row in rows:
        for k in [k for k in row if k.startswith("_")]:
            row.pop(k)
    rows.sort(key=lambda r: (-r["n"], r["cc"]))
    out["rows"] = rows
    out["state"] = "ok" if any(r["verdict"] not in ("few", "wait") for r in rows) else "low"
    out["best"], out["weak"] = best, weak
    out["sets"] = {"top": top_now, "low": low_now}
    out["judged"] = sum(1 for r in rows if r["verdict"] not in ("few", "wait"))
    out["gap_weeks"] = sum(1 for W in w12[1] if not C.clean(W, 1))
    g12 = sorted((W for W in C.cw if W in P["wk"] and P["wk"][W]["cj"][0]), reverse=True)[:GAP_WEEKS]
    gr = sum(abs(sum(C.cw[W]["gap"]["r"])) for W in g12) / 1e6
    dr = sum(P["wk"][W]["Rr"][_tj(90)] for W in g12)
    gn12 = sum(abs(C.cw[W]["gap"]["n"]) for W in g12)
    dn = sum(P["wk"][W]["n"] for W in g12)
    out["gap12"] = {"rev": _g4(gr / dr) if dr > 0 else None, "n": _g4(gn12 / dn) if dn else None, "weeks": len(g12)}
    if G.env():
        gf = _geo_fields(G, gwhy, wd, rows, out["small"]["n"], P["S"])
        out["small"]["cost"], out["small"]["cpi"] = gf.pop("small_cost", None), gf.pop("small_cpi", None)
        ex = gf.pop("small_extra", None)
        if ex:                                        # its share of the cost, its Google Ads downloads, ₹ billed
            out["small"].update(ex)
        out.update(gf)
        if gwhy == "ok":                              # the tile's Keep / Costly: rankable, held two evaluations
            vd = {r["cc"]: r["verdict"] for r in rows}
            out["keep"] = [cc for cc in best if vd.get(cc) == "keep"]
            out["costly"] = [cc for cc in weak if vd.get(cc) == "costly"]
    return out, C, {"win": win, "w12": w12, "phis": phis, "clean": clean, "app_obs": app_obs, "app_d": app_d,
                     "h": hs_by_cc, "geo": G, "geo_why": gwhy, "app_h": app_h}


def _geo_sum(g, weeks):
    """A country's Google Ads cost (USD) and downloads over exactly the install weeks `weeks` — the same days as the
    installs they are divided by (a 28-day cost over a 12-week install window would read ~3× too cheap) → (cost, dl).
    A plain total {cost, dl} (no days) is taken as it is."""
    if not g:
        return 0.0, 0.0
    if isinstance(g.get("daily"), dict):
        c = dl = 0.0
        for W in weeks or ():
            for i in range(7):
                v = g["daily"].get(_iso(W + timedelta(days=i)))
                if v:
                    c += float(v[0] or 0)
                    dl += float(v[1] or 0)
        return c, dl
    return float(g.get("cost") or 0), float(g.get("dl") or 0)


class _Geo:
    """The Google Ads country cost the engine is handed (GADS_GEO), whatever its shape:
      * None / {} → off;
      * the legacy per-country shapes {cc: {cost, dl}} / {cc: {"daily": {day: [usd, dl]}}} → exactly the behaviour
        before the week envelope (every week taken as it is, no coverage fields in the output);
      * the week envelope of value_build._app_geo ({"v": 2, "first", "till", "weeks": {Monday: {whole, cov, spend, geo,
        rate, dl_ok, by: {cc: [usd, dl | None]}}}}) → per install week, gated by Google Ads' own coverage (Σ country
        cost ÷ campaign cost in [GEO_COV_MIN, GEO_COV_MAX], or off by ≤ GEO_COV_ABS USD in a trickle week); a week
        that is not whole or not covered hides every
        country's cost, honestly (never a partial cost read as a cheap country)."""

    def __init__(self, geo):
        self.raw = geo if isinstance(geo, dict) and geo else None
        self.is_env = bool(self.raw) and self.raw.get("v") == 2
        self.wk = {}
        if self.is_env:
            for k, v in (self.raw.get("weeks") or {}).items():
                try:
                    self.wk[_d(k)] = v if isinstance(v, dict) else {}
                except (TypeError, ValueError):
                    continue

    def on(self):
        return self.raw is not None

    def env(self):
        return self.is_env

    @staticmethod
    def _tol(e):
        """The USD a week's country total may miss its campaign cost by through the cache's rounding alone."""
        t = e.get("tol")
        return max(GEO_COV_ABS, float(t)) if isinstance(t, (int, float)) else GEO_COV_ABS

    @staticmethod
    def _xx(e):
        v = ((e.get("by") or {}).get(UNMAPPED) or [0])[0]
        return float(v or 0)

    def week_ok(self, W):
        if not self.is_env:
            return self.on()
        e = self.wk.get(W)
        cov = (e or {}).get("cov")
        if not e or not e.get("whole") or cov is None:
            return False
        sp, g = e.get("spend"), e.get("geo")
        tol = self._tol(e)
        if not GEO_COV_MIN <= cov <= GEO_COV_MAX:          # a trickle week: off by no more than the rounding
            if sp is None or g is None or abs(float(g) - float(sp)) > tol:
                return False
        xx = self._xx(e)                                    # cost Google Ads put in no country (a failed map): the
        if xx > 0 and sp:                                   # countries' own part must still cover the campaign
            if float(g or 0) - xx < GEO_COV_MIN * float(sp) and float(sp) - (float(g or 0) - xx) > tol:
                return False
        return True

    def why(self, weeks):
        """"ok" | "wait" (a week not whole: Google Ads' country data not in yet) | "cov" (a whole week whose country
        cost does not add up to its campaign cost) | "nostore" (the app spent but none of its stores is in the country
        cache — the envelope's in_cache = 0 says so directly; without that key, every whole week with spend has no
        country cost) | "noads" (every week ok, nothing spent); None when off or without weeks."""
        if not self.on() or not weeks:
            return None
        if not self.is_env:
            return "ok"
        es = [self.wk.get(W) for W in weeks]
        if self.raw.get("till") and self.raw.get("in_cache") == 0 and any(e and (e.get("spend") or 0) > 0 for e in es):
            return "nostore"                              # (a cache with nothing committed yet is "wait", below)
        spw = [e for e in es if e and e.get("whole") and (e.get("spend") or 0) > 0]
        if spw and all(e.get("cov") is None and not (e.get("geo") or 0) for e in spw):
            return "nostore"
        if any(not e or not e.get("whole") for e in es):
            return "wait"
        if not all(self.week_ok(W) for W in weeks):
            return "cov"
        if sum(float(e.get("spend") or 0) for e in es) <= 0:
            return "noads"
        return "ok"

    def cost(self, cc, weeks):
        """(USD, downloads | None) of country cc over the install weeks — legacy: _geo_sum as it always was."""
        if not self.on():
            return 0.0, 0.0
        if not self.is_env:
            return _geo_sum(self.raw.get(cc), weeks)
        c = dl = 0.0
        known = True
        for W in weeks or ():
            e = self.wk.get(W) or {}
            if e.get("dl_ok") is False:
                known = False
            v = (e.get("by") or {}).get(cc)
            if not v:
                continue
            c += float(v[0] or 0)
            if len(v) < 2 or v[1] is None:
                known = False
            else:
                dl += float(v[1])
        return c, (dl if known else None)

    def cost_src(self, cc, weeks):
        """The same cost in the billed (base) currency — the ₹ view shows exactly what Google Ads billed — or None
        when a week does not carry it (an envelope from before)."""
        if not self.is_env:
            return None
        s = 0.0
        for W in weeks or ():
            v = ((self.wk.get(W) or {}).get("by") or {}).get(cc)
            if not v:
                continue
            if len(v) < 3 or v[2] is None:
                return None
            s += float(v[2])
        return s

    def total_src(self, weeks):
        tot = 0.0
        for W in weeks or ():
            for v in (((self.wk.get(W) or {}).get("by") or {}).values()):
                if not v:
                    continue
                if len(v) < 3 or v[2] is None:
                    return None
                tot += float(v[2])
        return tot

    def ccs(self, weeks=None):
        if not self.on():
            return set()
        if not self.is_env:
            return set(self.raw)
        out = set()
        for W in (weeks if weeks is not None else self.wk):
            out |= set(((self.wk.get(W) or {}).get("by") or {}))
        return out

    def total(self, weeks):
        """Every country's cost over the weeks, the unmapped part included."""
        if not self.is_env:
            return sum(_geo_sum(g, weeks)[0] for g in (self.raw or {}).values())
        return sum(float(v[0] or 0) for W in weeks or () for v in (((self.wk.get(W) or {}).get("by") or {}).values())
                   if v)

    def sums(self, weeks):
        """(Σ campaign spend, Σ country cost) in USD over the weeks the envelope holds."""
        es = [self.wk.get(W) for W in weeks or ()]
        return (sum(float(e.get("spend") or 0) for e in es if e), sum(float(e.get("geo") or 0) for e in es if e))

    def mapped(self, weeks):
        """Σ country cost placed in a real country (the unmapped part left out), USD."""
        es = [self.wk.get(W) for W in weeks or ()]
        return sum(float(e.get("geo") or 0) - self._xx(e) for e in es if e)


def _geo_fields(G, gwhy, wd, rows, small_n, S):
    """The envelope's extra Countries keys (GADS_GEO on, week envelope): geo_why, geo_cov, cost, small.cost / cpi —
    and, privately, the not-covered weeks the Data check names."""
    sp, gs = G.sums(wd)
    covs = [G.wk[W]["cov"] for W in wd if W in G.wk and G.wk[W].get("cov") is not None]
    v = (gs / sp) if sp > 0 else (1.0 if (wd and gs == 0 and all(W in G.wk for W in wd)) else None)
    out = {"geo_why": gwhy,
           "geo_cov": {"v": _g4(v), "min": _g4(min(covs)) if covs else None, "weeks": len(wd),
                       "from": _iso(min(wd)) if wd else None, "to": _iso(max(wd) + timedelta(days=6)) if wd else None,
                       "till": G.raw.get("till")},
           "cost": None, "_gbad": None}
    bad = [W for W in wd if not G.week_ok(W)]
    if bad:
        bs, bg = G.sums(bad)
        bm = G.mapped(bad)                                # the part placed in a real country (a failed map says so)
        out["_gbad"] = {"from": min(bad), "to": max(bad) + timedelta(days=6),
                        "v": (min(bg, bm) / bs) if bs > 0 else None}
    if gwhy == "ok":
        total = G.total(wd)
        unm = G.cost(UNMAPPED, wd)[0]
        own = sum(((r.get("cpi") or {}).get("spend") or 0) for r in rows)
        small = max(0.0, total - own - unm)
        tsrc, usrc = G.total_src(wd), G.cost_src(UNMAPPED, wd)
        osrc = sum(((r.get("cpi") or {}).get("spend_src") or 0) for r in rows)
        ssrc = max(0.0, tsrc - osrc - (usrc or 0)) if tsrc is not None else None
        # the small countries' Google Ads downloads (their ads-only cost per install) — unknown when any is unknown
        mine = {r["cc"] for r in rows}
        sdl = 0.0
        for cc in G.ccs(wd):
            if cc in mine or cc == UNMAPPED:
                continue
            c, d = G.cost(cc, wd)
            if c > 0 and d is None:
                sdl = None
                break
            sdl += d or 0
        out["cost"] = {"total": _m6(total), "rows": _m6(own), "small": _m6(small), "unmapped": _m6(unm),
                       "unmapped_share": _g4(unm / total) if total > 0 else None, "spend": _m6(sp)}
        if tsrc is not None:                              # the billed (base) currency: the ₹ view's own amounts
            out["cost"].update(total_src=_m6(tsrc), small_src=_m6(ssrc), unmapped_src=_m6(usrc))
        out["small_cost"] = _m6(small)
        out["small_cpi"] = _m6(small / small_n) if (small > 0 and small_n) else None
        ads_ok = bool(sdl and sdl >= GEO_DL_MIN and small > 0)
        out["small_extra"] = {"share": _g4(small / total) if total > 0 else None,
                              "dl": _m6(sdl) if sdl is not None else None,
                              "cpi_ads": _m6(small / sdl) if ads_ok else None,
                              "cost_src": _m6(ssrc) if ssrc is not None else None,
                              "cpi_ads_src": _m6(ssrc / sdl) if (ads_ok and ssrc is not None) else None}
    return out


def _geo_thin(cost, dl, n, nweeks):
    """Why a country's Google Ads cost is too thin to judge — "spend" (under SPEND_MIN_WEEK USD a window week on
    average), "dl" (under GEO_DL_MIN Google Ads downloads) or "paid" (ads bring under GEO_PAID_MIN of its new users) —
    or None: judged. Unknown downloads (Q-G2 failed) leave only the spend rule."""
    if cost < SPEND_MIN_WEEK * max(nweeks, 1):
        return "spend"
    if dl is not None:
        if dl < GEO_DL_MIN:
            return "dl"
        if n and dl / n < GEO_PAID_MIN:
            return "paid"
    return None


def _geo_back(C, G, cc, obs, r90, win, cpi):
    """₹ back per ₹100 of Google Ads in the country after 7 / 30 / 90 days: the earnings of the install weeks each
    age is measured on ÷ THOSE weeks' own Google Ads cost (never a newer cost over older earnings); ≈ ("t_est") when
    those weeks' cost is not all covered (then the window's cost per install stands in). → (back, same(t)): same(t)
    = the weeks of age t cost within ±GEO_BACK_REL of the window's cost per install (a money back "seen")."""
    back, own = {}, {}
    for t in (7, 30, 60, 90):
        o = obs.get(t)
        if o is None:
            continue
        ws = [W for W in win[t] if C.cw[W]["rows"].get(cc) is not None and not C.part(cc, W, t)]
        if ws and all(G.week_ok(W) for W in ws):
            c = G.cost(cc, ws)[0]
            if c > 0 and o["n"]:
                own[t] = c / o["n"]
    for t in (7, 30):
        o = obs.get(t)
        if o is None:
            back[str(t)], back["%d_est" % t] = None, False
        elif t in own:
            back[str(t)], back["%d_est" % t] = _g4(100 * o["y"] / (own[t] * o["n"])), False
        else:
            back[str(t)], back["%d_est" % t] = _g4(100 * o["v"] / cpi), True
    v90 = (r90 or {}).get("v")
    if obs.get(90) and 90 in own:
        back["90"], back["90_est"] = _g4(100 * obs[90]["y"] / (own[90] * obs[90]["n"])), False
    else:
        back["90"], back["90_est"] = (_g4(100 * v90 / cpi) if v90 is not None else None), bool(v90 is not None
                                                                                              and obs.get(90))
    back["90_proj"] = bool((r90 or {}).get("proj"))

    def same(t):
        if t is None:
            return False
        if t == 1:                                    # the cost window itself
            return True
        c = own.get(t)
        return c is not None and abs(c / cpi - 1) <= GEO_BACK_REL
    return back, same


def _cty_pay(obs, shapes, cpi, env=False):
    """A country's money back against its own cost per install: its observed earning per install at 1…90 days, then
    the app's curve beyond → {p, lo, hi, never, q80_365} (days; None: not within a year). env (the week envelope):
    also `upto`, the last age the curve reaches (money back not within it → "Over {upto} days")."""
    ts = [t for t in (1, 7, 30, 60, 90) if obs.get(t)]
    if not ts or not cpi:
        return None
    med = [(t, obs[t]["v"]) for t in ts]
    lo = [(t, obs[t]["lo"] if obs[t]["lo"] is not None else obs[t]["v"]) for t in ts]
    hi = [(t, obs[t]["hi"] if obs[t]["hi"] is not None else obs[t]["v"]) for t in ts]
    tb = ts[-1]
    for t in (180, 365):
        s = _shape_to(shapes, tb, t)[0]
        if s is None:
            break
        med.append((t, obs[tb]["v"] * s[0]))
        lo.append((t, lo[len(ts) - 1][1] * s[1]))
        hi.append((t, hi[len(ts) - 1][1] * s[2]))
    for arr in (med, lo, hi):
        for i in range(1, len(arr)):
            arr[i] = (arr[i][0], max(arr[i][1], arr[i - 1][1]))
    p = _cross(med, cpi)
    q80 = hi[-1][1] if hi[-1][0] == 365 else None
    out = {"p": _int(p), "lo": _int(_cross(hi, cpi)), "hi": _int(_cross(lo, cpi)),
           "never": p is None and med[-1][0] == 365, "q80_365": _m6(q80)}
    if env:
        out["upto"] = med[-1][0]
    return out


def _cost_verdict(row, H, env=False):
    """With country cost (GADS_GEO, §2.5): keep (P̂ ≤ H; sure when even P_hi ≤ H) / slow (H < P̂ ≤ 2H, or the band
    straddles H) / costly (the q80 curve at 365 under the cost, or P_lo > 2H) / few. env (the week envelope): what the
    legacy shapes called "few" is said as it is — "late" (not paid back by the last age the curve reaches, ≥ H, with
    no curve beyond it: "Not paid back in {upto} days"), "wait" (not paid back yet and the earnings not H days old,
    no curve beyond) or "slow" (P̂ beyond 2H, not surely: the band reaches under 2H). "few" stays for few installs."""
    pay, cpi = row.get("pay"), (row.get("cpi") or {}).get("v")
    if not pay or not cpi:
        return "few"
    p, lo, hi = pay["p"], pay["lo"], pay["hi"]
    if (pay["q80_365"] is not None and pay["q80_365"] < cpi) or (lo is not None and lo > 2 * H) or \
            (lo is None and pay["never"]):
        return "costly"
    if p is not None and p <= H:
        row["sure"] = hi is not None and hi <= H
        return "keep"
    if (p is not None and p <= 2 * H) or (lo is not None and lo <= H < (hi if hi is not None else 366)):
        return "slow"
    if env:
        if p is None and not pay["never"]:
            return "late" if (pay.get("upto") or 0) >= H else "wait"
        return "slow"
    return "few"


def _trend(C, cc, w12):
    """Two 12-week sparklines (oldest → newest): next-day returners of 100 and earning per install at 7 days."""
    d1 = []
    for W in reversed(w12[1]):
        c = C.cw[W]["rows"].get(cc)
        d1.append(_g4(100 * c["u"][0] / c["n"]) if c and c["n"] >= CTY_SHOW and not C.part(cc, W, 1) else None)
    r7 = []
    for W in reversed(w12[7]):
        c = C.cw[W]["rows"].get(cc)
        r7.append(_m6(c["R"][_tj(7)] / c["n"]) if c and c["n"] >= CTY_SHOW and not C.part(cc, W, 7) else None)
    return {"d1": d1, "rpi7": r7}


def _trend_cpi(C, G, cc, weeks):
    """The third sparkline (oldest → newest): the country's Google Ads cost ÷ its installs per install week — a week
    whose country cost is not covered, a thin week, or a week without Google Ads cost there reads null (never 0)."""
    out, src, known = [], [], True
    for W in reversed(weeks):
        c = C.cw[W]["rows"].get(cc)
        v = vs = None
        if G.week_ok(W) and c and c["n"] >= CTY_SHOW and not C.part(cc, W, 1):
            cost = G.cost(cc, [W])[0]
            v = _m6(cost / c["n"]) if cost > 0 else None
            if v is not None:
                cs = G.cost_src(cc, [W])
                known = known and cs is not None
                vs = _m6(cs / c["n"]) if cs is not None else None
        out.append(v)
        src.append(vs)
    return out, (src if known else None)


def _pay_obs(obs, p):
    """A country's money back is OBSERVED when its crossing lies on its own observed points (1 … 90 days) and none of
    those points is ≈."""
    ts = [t for t in (1, 7, 30, 60, 90) if obs.get(t)]
    if p is None or not ts or p > ts[-1]:
        return False
    upto = next(t for t in ts if t >= p)
    return not any(obs[t].get("est") for t in ts if t <= upto)


def country_text(row, d1_app, H, best, weak):
    """The row's one Hinglish sentence (§2.8); money and the country's name are tokens (the page draws them)."""
    name = t_cc(row["cc"])
    if not row["clean"]:
        return "%s: in hafton ka country data GA4 ne poora nahi diya — abhi faisla nahi" % name
    if row.get("why") == "young":
        return "%s: %s installs — kamai ke kaafi hafte aane pe faisla" % (name, "{:,}".format(row["n"]))
    if row["verdict"] == "few":
        if row.get("why") == "few_val":               # many installs now, but the weeks its value comes from are small
            return ("%s: kamai wale (purane) hafton me sirf %s installs — faisla ke liye kam (%d chahiye)"
                    % (name, "{:,}".format(row.get("n_val") or 0), CTY_JUDGE))
        return "%s: abhi sirf %s installs — faisla ke liye kam (%d chahiye)" % (name, "{:,}".format(row["n"]), CTY_JUDGE)
    d1 = row["d1"]["v"]
    head = "%s: 100 me se %s agle din wapas (app me %s)" % (
        name, "—" if d1 is None else int(round(d1)), "—" if d1_app is None else int(round(d1_app)))
    K = row["cpi"] or {}
    if K.get("v") is not None and not K.get("thin"):
        pp = (row.get("pay") or {}).get("p")
        tail = {"keep": "paisa ~%s din me wapas, ads chalu rakh sakte ho" % (pp if pp is not None else H),
                "slow": "paisa wapas aane me ~%s din — dheere" % (pp if pp is not None else ">%d" % H),
                "costly": "ads yahan mehenge pad rahe",
                "late": "%s din me paisa wapas nahi aaya — aage ka andaza abhi nahi" % (
                    (row.get("pay") or {}).get("upto") or H)}.get(row["verdict"], "abhi faisla nahi")
        return "%s, %d din me kamai per install %s — install %s me pad raha, %s" % (
            head, H, t_m(row["be"]), t_q(row["cpi"]["v"]), tail)
    r30 = (row["rpi"].get("30") or {}).get("v")
    txt = "%s, 30 din me kamai per install %s" % (head, t_m(r30))
    if row["be"] is not None:
        txt += " — install %s se sasta mile tabhi %d din me paisa wapas" % (t_m(row["be"]), H)
    if row["cc"] in best:
        txt += " — sabse zyada kamai walon me"
    elif row["cc"] in weak:
        txt += " — kam kamai walon me"
    if K.get("thin"):                                 # a trickle of Google Ads: its cost is shown, never judged
        txt += " — yahan %s, isliye ads ka faisla nahi" % {
            "spend": "Google Ads kharcha thoda",
            "dl": "Google Ads se sirf %s installs" % "{:,}".format(int(round(K.get("dl") or 0))),
            "paid": "ads se sirf ~%s%% installs" % _num1(100 * (K.get("paid") or 0))}[K["thin"]]
    return txt


# ── weekly alert conditions (§2.7) ──────────────────────────────────────────────────────────────

def _eval_end(S):
    """The settled week end for money back: the Sunday ≤ S − 7 (its install week's 7-day earnings are whole)."""
    e = S - timedelta(days=7)
    return e - timedelta(days=(e.weekday() + 1) % 7)


def _b7_at(weeks_by_W, e):
    """At week end e: the 2 newest install weeks (ending e and e − 7) vs the 8 before → (T, info) or None."""
    rec = [weeks_by_W.get(e - timedelta(days=6 + 7 * i)) for i in (1, 0)]
    if any(w is None or not w["judged"] or not w["cj"][_tj(7)] for w in rec):
        return None
    base = [weeks_by_W.get(e - timedelta(days=6 + 7 * i)) for i in range(PAY_BASE_WEEKS + 1, 1, -1)]
    base = [w for w in base if w is not None and w["judged"] and w["cj"][_tj(7)]]
    if len(base) < PAY_BASE_MIN:
        return None
    rs, ss = sum(w["R"][_tj(7)] for w in rec), sum(w["spend"] for w in rec)
    rb, sb = sum(w["R"][_tj(7)] for w in base), sum(w["spend"] for w in base)
    if rs <= 0 or rb <= 0 or ss <= 0 or sb <= 0:
        return None
    b7r, b70 = rs / ss, rb / sb
    return math.log(b7r / b70), {"rec": rec, "base": base, "b7r": b7r, "b70": b70,
                                 "wk": [w["R"][_tj(7)] / w["spend"] for w in rec]}


def _null_z(weeks_by_W, e, stat, fn=None):
    """z = stat ÷ σ over the same statistic at each of the PAY_NULL_WEEKS week ends before e (≥ PAY_NULL_MIN of
    them): σ = max(robust spread, PAY_SIGMA_FLOOR) — uncentred, as in Active. None without enough null."""
    fn = fn or _b7_at
    nul = []
    for i in range(1, PAY_NULL_WEEKS + 1):
        r = fn(weeks_by_W, e - timedelta(days=7 * i))
        if r is not None:
            nul.append(r[0])
    if len(nul) < PAY_NULL_MIN:
        return None
    sig = max(U.spread(nul, _med(nul)), PAY_SIGMA_FLOOR)
    return stat / sig


def _cpi_at(weeks_by_W, e):
    """The same shape of statistic for the cost per install (log of 2 newest ÷ 8 before, pooled)."""
    rec = [weeks_by_W.get(e - timedelta(days=6 + 7 * i)) for i in (1, 0)]
    if any(w is None or not w["judged"] for w in rec):
        return None
    base = [weeks_by_W.get(e - timedelta(days=6 + 7 * i)) for i in range(PAY_BASE_WEEKS + 1, 1, -1)]
    base = [w for w in base if w is not None and w["judged"]]
    if len(base) < PAY_BASE_MIN:
        return None
    c1 = sum(w["spend"] for w in rec) / sum(w["n"] for w in rec)
    c0 = sum(w["spend"] for w in base) / sum(w["n"] for w in base)
    s1 = sum(w.get("spend_src") or 0 for w in rec) / sum(w["n"] for w in rec)
    s0 = sum(w.get("spend_src") or 0 for w in base) / sum(w["n"] for w in base)
    return math.log(c1 / c0), {"c1": c1, "c0": c0, "s1": s1, "s0": s0, "rec": rec, "base": base}


def _sp_vpi(info, rec=None):
    """Money back per 100 spent (SPEC_SPLIT F7): value per install and cost per install on the base weeks of b7r / b70
    (_b7_at's base: 100 · vb ÷ cb = 100 · b70 exactly) and the after weeks `rec` — by default _b7_at's 2 newest (the
    pay_slow alert's b7r); the tile passes its own one week, so the split's after is the tile's number →
    ["vpi", vb, va, cb, ca]. Read-only."""
    def build():
        base = info["base"]
        ws = info["rec"] if rec is None else rec
        nr, nb = sum(w["n"] for w in ws), sum(w["n"] for w in base)
        return attrib.vpi(sum(w["R"][_tj(7)] for w in base) / nb, sum(w["R"][_tj(7)] for w in ws) / nr,
                          sum(w["spend"] for w in base) / nb, sum(w["spend"] for w in ws) / nr)
    return attrib.safe(build)


def _sp_spd(weeks, w0):
    """The ad spend's split on the cost tile's own window (SPEC_SPLIT F7): the tile's 4 calendar weeks w0 (installs a
    week, cost per install = the tile's number) vs the up to PAY_BASE_WEEKS weeks before them with spend and installs
    known → ["spd", installs / week before / after, cost per install before / after]; None with fewer than PAY_BASE_MIN
    such weeks (the tile shows no before either — as an earning tile without a before value)."""
    base = [w for w in weeks if w["W"] < w0[0]["W"] and w["spend"] is not None and w["cj"][_tj(0)]
            and w["n"] > 0][-PAY_BASE_WEEKS:]
    if len(base) < PAY_BASE_MIN or sum(w["spend"] for w in base) <= 0 or not sum(w["n"] for w in w0):
        return None

    def build():
        nb, na = sum(w["n"] for w in base), sum(w["n"] for w in w0)
        return attrib.spd(nb / len(base), na / len(w0), sum(w["spend"] for w in base) / nb,
                          sum(w["spend"] for w in w0) / na)
    return attrib.safe(build)


def _market_hit(market, dr, a, b):
    """A market-wide week (Active's market prepass: most apps' ad rate — eCPM — moved the same way that week) in
    direction dr overlapping [a, b] by ≥ 4 days → {from, to, apps, of}, else None."""
    for wk in (market or {}).get("weeks") or []:
        if not isinstance(wk, dict) or wk.get("dir") != dr:
            continue
        try:
            f, t = _d(wk["from"]), _d(wk["to"])
        except (KeyError, TypeError, ValueError):
            continue
        if (min(t, b) - max(f, a)).days + 1 >= 4:
            return {"from": _iso(f), "to": _iso(t), "apps": wk.get("apps"), "of": wk.get("of")}
    return None


def _tags(P, info, weeks_by_W, e, releases, act_alerts, ctyinfo=None):
    """Why money back moved (§2.7 tags) → (tags, release, cause text, mix_only). mix_only: the paid share moved while
    the ads-only cost per install (spend ÷ Google Ads installs) did not — organic installs came or went, the ads did
    not change: the mix leads, never "install sasta / mehenga"."""
    rec, base = info["rec"], info["base"]
    tags, cause, rel = [], None, None
    Tv = math.log(info["b7r"] / info["b70"])
    p1 = [w["paid"] for w in rec if w["paid"] is not None]
    p0 = [w["paid"] for w in base if w["paid"] is not None]
    mix = None
    if p1 and p0:
        a, b = _med(p0), sum(p1) / len(p1)
        if abs(b - a) * 100 >= INFO_PTS:
            mix = (a, b)
    na1, na0 = sum(w["n_ads"] or 0 for w in rec), sum(w["n_ads"] or 0 for w in base)
    ads_rel = None
    if na1 and na0:
        ads_rel = (sum(w["spend"] for w in rec) / na1) / (sum(w["spend"] for w in base) / na0) - 1
    mix_only = mix is not None and ads_rel is not None and abs(ads_rel) < TAG_REL
    if mix_only:
        tags.append("mix")
        cause = ("ads wale installs %d%% → %d%% — organic installs badle, ads ka kharcha per ads-install wahi"
                 % (round(100 * mix[0]), round(100 * mix[1])))
    c = _cpi_at(weeks_by_W, e)
    if c is not None and not mix_only:
        c_rel = c[1]["c1"] / c[1]["c0"] - 1
        if abs(c_rel) >= TAG_REL and abs(c[0]) >= 0.5 * abs(Tv) and (c[0] > 0) == (Tv < 0):
            tags.append("cpi")
            cause = cause or "install ka kharcha %s → %s (%s%s)" % (
                t_q(c[1]["c0"], c[1]["s0"]), t_q(c[1]["c1"], c[1]["s1"]), "+" if c_rel > 0 else "", _pct(c_rel))
    v1 = sum(w["R"][_tj(7)] for w in rec) / sum(w["n"] for w in rec)
    v0 = sum(w["R"][_tj(7)] for w in base) / sum(w["n"] for w in base)
    if v0 > 0 and abs(v1 / v0 - 1) >= TAG_REL and (v1 < v0) == (Tv < 0):
        tags.append("value")
        cause = cause or "kamai per install (7 din) %s → %s (%s%s)" % (
            t_m(v0), t_m(v1), "+" if v1 > v0 else "", _pct(v1 / v0 - 1))
    if mix is not None and not mix_only:
        tags.append("mix")
        cause = cause or "ads wale installs %d%% → %d%%" % (round(100 * mix[0]), round(100 * mix[1]))
    lo, hi = rec[0]["W"], rec[-1]["W"] + timedelta(days=6)
    for r in releases or []:
        try:
            rd = _d(r.get("date"))
        except (TypeError, ValueError, AttributeError):
            continue
        if lo <= rd <= hi:
            rel = {"date": _iso(rd), "version": r.get("version"), "kind": r.get("kind"), "key": r.get("key")}
    if rel:
        tags.append("update")
    if any(a.get("family") == "act_return" and a.get("dir") == "down" and a.get("metric") in ("d1", "d7")
           for a in act_alerts or []):
        tags.append("return")
        cause = cause or "naye users kam wapas aa rahe (Active users dekho)"
    return tags, rel, cause, mix_only


def _span_pay(ps):
    """One money-back figure for a span of weeks (the median of each week's; its range the median of theirs) — the
    same number wherever that span is named."""
    ps = [p for p in ps if p]
    if not ps:
        return None
    pv = [_pval(p) for p in ps]
    if any(v is None for v in pv):
        return None
    los = [p["p"] if p["obs"] else (p["lo"] if p["lo"] is not None else _pval(p)) for p in ps]
    his = [p["p"] if p["obs"] else (p["hi"] if p["hi"] is not None else 366) for p in ps]
    never = all(p["never"] for p in ps)
    return {"p": None if never else _int(_med(pv)), "lo": _int(_med(los)) if not never else None,
            "hi": _int(_med(his)) if not never else None, "obs": all(p["obs"] for p in ps), "never": never,
            "pct365": _g4(_med([p["pct365"] for p in ps if p["pct365"] is not None])) if never else None,
            "rough": any(p.get("rough") for p in ps), "hi_over": any(p.get("hi_over") for p in ps), "shape": None}


def _conditions(P, weeks, pays, H, E, ctyinfo, C, releases, act_alerts, geo, streak, app, market=None):
    """Every family's condition at week end E (the weekly evaluation) → [cond] (each with key, family, severity…).
    A money-back condition is SHOWN but never sent (seeded), never red, and ≈ when what it stands on is doubtful:
    the AdMob scale of its weeks is outside K_OK (a GA4-side change), the GA4 ÷ AdMob link dropped (iv_link), the move
    is the market's (every app's ad rate moved and the only cause is the earning per install), or an "up" move comes
    only from the paid share. A projection from other apps' curves (a young app) never opens one."""
    conds = []
    by_W = {w["W"]: w for w in weeks}
    sc = P["sc"]
    ap = {W: p for W, p in pays.items() if p.get("shape") != "portfolio"}
    # iv_link: GA4 ÷ AdMob fell to ≤ 0.7 × its median of the 8 weeks before, in each of the 2 newest weeks
    link = None
    sw = [w for w in sc["weeks"] if w["r"] is not None]
    if len(sw) >= 10:
        last2, before = sw[-2:], sw[-10:-2]
        m0 = _med([w["r"] for w in before])
        if m0 and all(w["admob"] >= LINK_MIN_REV and w["r"] <= LINK_DROP * m0 for w in last2):
            link = {"key": "%s|iv_link" % app["id"], "family": "iv_link", "metric": "link", "dir": "down",
                    "cc": None, "severity": "watch", "now": _g4(100 * last2[-1]["r"]), "before": _g4(100 * m0),
                    "rel": _g4(last2[-1]["r"] / m0 - 1), "z": None, "week_from": last2[0]["from"],
                    "week_to": last2[-1]["to"], "base_from": before[0]["from"], "base_to": before[-1]["to"],
                    "users": 0, "spend": None, "tags": [], "release": None}
    # pay_slow
    r = _b7_at(by_W, E)
    if r is not None:
        Tv, info = r
        rec = info["rec"]
        z = _null_z(by_W, E, Tv)
        base_ws = info["base"]
        p_rec = [ap.get(w["W"]) for w in rec]
        p_base = [_pval(ap.get(w["W"])) for w in base_ws if _pval(ap.get(w["W"])) is not None]
        P0 = _int(_med(p_base)) if p_base else None
        sp2 = _span_pay(p_rec) if all(p_rec) else None
        Pr = _pval(sp2) if sp2 else None
        big = all(w["n"] >= PAY_MIN_N for w in rec)
        if z is not None and big and Pr is not None and P0 is not None:
            wk = info["wk"]
            down = (Tv <= math.log(PAY_REL_DN) and z <= -PAY_Z and all(b <= (1 - PAY_WEEK_REL) * info["b70"] for b in wk)
                    and Pr - P0 >= max(PAY_MOVE_DAYS, PAY_MOVE_REL * P0))
            up = (Tv >= math.log(PAY_REL_UP) and z >= PAY_Z and all(b >= (1 + PAY_WEEK_REL) * info["b70"] for b in wk)
                  and P0 - Pr >= PAY_MOVE_DAYS)
            if down or up:
                tags, rel, cause, mix_only = _tags(P, info, by_W, E, releases, act_alerts, ctyinfo)
                dr = "up" if up else "down"
                never_now = sp2["never"]
                sev = "good" if up else ("warning" if ((P0 <= H < Pr) or (never_now and P0 < 366)) else "watch")
                kbad = k_est(sc, base_ws[0]["W"], rec[-1]["W"] + timedelta(days=13))
                mk = _market_hit(market, dr, rec[0]["W"], rec[-1]["W"] + timedelta(days=13))
                market_only = bool(mk) and set(tags) <= {"value"}
                if market_only:
                    tags.append("market_wide")
                    cause = (cause + " — " if cause else "") + "ad rate (eCPM) sab apps me %s" % (
                        "gira" if dr == "down" else "badha")
                held = bool(kbad or link or market_only)
                if held and sev == "warning":
                    sev = "watch"
                conds.append({"key": "%s|pay_slow|%s" % (app["id"], dr), "family": "pay_slow",
                              "metric": "b7", "dir": dr, "cc": None, "severity": sev,
                              "now": _g4(100 * info["b7r"]), "before": _g4(100 * info["b70"]),
                              "rel": _g4(info["b7r"] / info["b70"] - 1), "z": _g4(z), "p": Pr, "p0": P0,
                              "lo": sp2["lo"], "hi": sp2["hi"], "obs": sp2["obs"], "rough": sp2["rough"],
                              "never": never_now, "pct365": sp2["pct365"], "week_from": _iso(rec[0]["W"]),
                              "week_to": _iso(rec[-1]["W"] + timedelta(days=6)),
                              "base_from": _iso(base_ws[0]["W"]), "base_to": _iso(base_ws[-1]["W"] + timedelta(days=6)),
                              "users": sum(w["n"] for w in rec), "spend": _m6(sum(w["spend"] for w in rec) / 2),
                              "spend_src": _m6(sum(w.get("spend_src") or 0 for w in rec) / 2),
                              "tags": tags, "release": rel, "cause": cause, "market": mk if market_only else None,
                              "_force_seed": held or (up and mix_only), "_est": bool(kbad or link),
                              "sp": _sp_vpi(info)})
    # pay_loss (a state): the 2 newest judged weeks with t_o ≥ 7 both miss the target even on the good band — only
    # while the app still spends (the newest judged week ended ≤ ADS_STALE_DAYS before E: stopped ads close it)
    jw = [w for w in weeks if w["judged"] and w["cj"][_tj(7)] and w["W"] + timedelta(days=6) <= E
          and ap.get(w["W"]) is not None][-2:]
    later = [w for w in weeks if jw and jw[-1]["W"] < w["W"] and w["W"] + timedelta(days=6) <= E]
    fresh = bool(jw) and ((E - (jw[-1]["W"] + timedelta(days=6))).days <= ADS_STALE_DAYS
                          or all(w["spend"] is None for w in later))     # spend not in yet ≠ stopped: kept
    if len(jw) == 2 and fresh and all(w["spend"] >= SPEND_MIN_WEEK for w in jw):
        def miss(w):
            p = ap[w["W"]]
            if p["never"]:
                return True
            if p["obs"]:
                return p["p"] is not None and p["p"] > H
            return (p["lo"] if p["lo"] is not None else 366) > H
        if all(miss(w) for w in jw):
            hard = all((w["_proj"][3][9] is not None and w["_proj"][3][9] < w["ecpi"]) or
                       (w["_proj"][0][9] is not None and w["_proj"][0][9] < w["ecpi"]) for w in jw)
            sp = sum(w["spend"] for w in jw) / 2
            pw = _span_pay([ap[w["W"]] for w in jw])
            base = [w for w in weeks if w["judged"] and w["W"] < jw[0]["W"]][-PAY_BASE_WEEKS:]
            tags = []
            if len(base) >= PAY_BASE_MIN:
                c1 = sum(w["spend"] for w in jw) / sum(w["n"] for w in jw)
                c0 = sum(w["spend"] for w in base) / sum(w["n"] for w in base)
                if c1 / c0 - 1 >= TAG_REL:
                    tags.append("cpi")
            kbad = k_est(sc, jw[0]["W"], P["S"])
            mk = _market_hit(market, "down", jw[0]["W"], jw[-1]["W"] + timedelta(days=13))
            market_only = bool(mk) and "cpi" not in tags
            if market_only:
                tags.append("market_wide")
            held = bool(kbad or link or market_only)
            sev = "warning" if (hard and sp >= LOSS_BIG_SPEND and not held) else "watch"
            conds.append({"key": "%s|pay_loss" % app["id"], "family": "pay_loss", "metric": "pay", "dir": "down",
                          "cc": None, "severity": sev, "now": _pval(pw), "before": None, "rel": None, "z": None,
                          "p": pw["p"], "p0": None, "never": pw["never"], "pct365": pw["pct365"],
                          "lo": pw["lo"], "hi": pw["hi"], "obs": pw["obs"], "hi_over": pw["hi_over"],
                          "rough": pw["rough"], "week_from": _iso(jw[0]["W"]),
                          "week_to": _iso(jw[-1]["W"] + timedelta(days=6)), "base_from": None, "base_to": None,
                          "users": sum(w["n"] for w in jw), "spend": _m6(sp),
                          "spend_src": _m6(sum(w.get("spend_src") or 0 for w in jw) / 2), "tags": tags,
                          "release": None, "market": mk if market_only else None,
                          "_force_seed": held, "_est": bool(kbad or link)})
    if link is not None:
        conds.append(link)
    # geo_move (and geo_cost with country cost) — one episode per country and direction: when both hold for the same
    # country the cost leads, the move rides along (also / move); an already-open geo_move closes by itself
    if C is not None and ctyinfo is not None:
        gm = _geo_conds(P, C, ctyinfo, act_alerts, app)
        gc = _geo_cost_conds(C, ctyinfo, geo, H, streak, app) if geo else []
        for c in gc:
            mv = next((m for m in gm if m["cc"] == c["cc"] and m["dir"] == c["dir"]), None)
            if mv is not None:
                gm.remove(mv)
                c["also"] = [mv["metric"]] + [x for x in mv.get("also") or [] if x != mv["metric"]]
                c["move"] = {"metric": mv["metric"], "now": mv["now"], "before": mv["before"]}
        conds += gm + gc
    return conds


def _geo_conds(P, C, ci, act_alerts, app):
    """geo_move (§2.7): a top country's D1 / D7 / D30 / earning at 7 days moved vs its 8 weeks before, in each of
    the 2 newest weeks, clean weeks only, not app-wide — one condition per country and direction (the strongest
    metric leads, the rest in `also`)."""
    found = {}
    phis = ci["phis"]
    for met, t in (("d1", 1), ("d7", 7), ("d30", 30), ("rpi7", 7)):
        ws = C.weeks(t, 2 + PAY_BASE_WEEKS)
        if len(ws) < 2 + PAY_BASE_WEEKS or not all(C.clean(W, t) for W in ws):
            continue
        rec, base = ws[:2], ws[2:]
        tot_base = sum(C.P["wk"][W]["n"] for W in base)
        top = sorted(((cc, _cty_sums(C, cc, base, t, "u" if met != "rpi7" else "r")[1]) for cc in C.cset
                      if cc not in ("--", "ZZ")), key=lambda x: (-x[1], x[0]))[:GEO_TOPK]
        for cc, nb in top:
            if not tot_base or nb / tot_base < GEO_MIN_SHARE or nb < GEO_MIN_WEEK_N:
                continue
            wk = [C.cw[W]["rows"].get(cc) for W in rec]
            if any(c is None or c["n"] < GEO_MIN_WEEK_N or C.part(cc, W, t) for c, W in zip(wk, rec)):
                continue
            what = "r" if met == "rpi7" else "u"
            x1, n1 = _cty_sums(C, cc, rec, t, what)
            x0, n0 = _cty_sums(C, cc, base, t, what)
            ax1, an1 = _cty_sums(C, "All", rec, t, what)
            ax0, an0 = _cty_sums(C, "All", base, t, what)
            if not (n1 and n0 and an1 > n1 and an0 > n0):
                continue
            share = nb / tot_base
            if met == "rpi7":
                R1, R0 = x1 / n1, x0 / n0
                if R0 <= 0:
                    continue
                rel = R1 / R0 - 1
                se = _rpi_se(C, cc, t, C.weeks(t, TREND_WEEKS), 1)
                if not se:
                    continue
                z = (R1 - R0) / (se * math.sqrt(1 / 2 + 1 / PAY_BASE_WEEKS))
                each = [(c["R"][_tj(7)] / c["n"]) / R0 - 1 for c in wk]
                ex1 = (ax1 - x1) / (an1 - n1)
                ex0 = (ax0 - x0) / (an0 - n0)
                app_rel = ex1 / ex0 - 1 if ex0 > 0 else 0
                thr = GEO_RPI_REL
                for dr, sg in (("down", -1), ("up", 1)):
                    if (sg * rel >= thr and sg * z >= GEO_Z and all(sg * e >= thr / 2 for e in each)
                            and not (sg * app_rel >= GEO_APPWIDE * abs(rel))):
                        warn = sg < 0 and rel <= -2 * thr and share >= GEO_WARN_SHARE and z <= -GEO_WARN_Z
                        found.setdefault((cc, dr), []).append(
                            {"metric": met, "t": t, "z": z, "now": _m6(R1), "before": _m6(R0), "rel": _g4(rel),
                             "delta": None, "share": share, "n": n1, "warn": warn, "rec": rec, "base": base,
                             "sp": attrib.safe(lambda: attrib.ir(n0 / len(base), n1 / len(rec)))})
                continue
            p1, p0 = x1 / n1, x0 / n0
            delta = 100 * (p1 - p0)
            rel = p1 / p0 - 1 if p0 > 0 else 0
            se = 100 * math.sqrt(phis.get(t, PHI_DEFAULT) * (p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0))
            if not se:
                continue
            z = delta / se
            each = [100 * (c["u"][CLAGS.index(t)] / c["n"] - p0) for c in wk]
            ex = 100 * ((ax1 - x1) / (an1 - n1) - (ax0 - x0) / (an0 - n0))
            thr = GEO_MINPP[t]
            for dr, sg in (("down", -1), ("up", 1)):
                if (sg * delta >= thr and sg * rel >= GEO_MINREL and sg * z >= GEO_Z
                        and all(sg * e >= thr / 2 for e in each) and not (sg * ex >= GEO_APPWIDE * abs(delta))):
                    if sg < 0 and any(a.get("family") == "act_return" and a.get("dir") == "down"
                                      and a.get("metric") == "d%d" % t for a in act_alerts or []):
                        app_d = 100 * ((ax1 / an1) - (ax0 / an0))
                        if abs(delta) < 2 * abs(app_d):
                            continue
                    warn = sg < 0 and delta <= -2 * thr and share >= GEO_WARN_SHARE and z <= -GEO_WARN_Z
                    found.setdefault((cc, dr), []).append(
                        {"metric": met, "t": t, "z": z, "now": _g4(100 * p1), "before": _g4(100 * p0),
                         "rel": _g4(rel), "delta": _g4(delta), "share": share, "n": n1, "warn": warn, "rec": rec,
                         "base": base,       # (the split: installs a DAY, as the rate's per-day words read it)
                         "sp": attrib.safe(lambda: attrib.rate("rr", n0 / (7 * len(base)), n1 / (7 * len(rec))))})
    out = []
    for (cc, dr), hits in sorted(found.items()):
        hits.sort(key=lambda h: -abs(h["z"]))
        h = hits[0]
        sev = "good" if dr == "up" else ("warning" if h["warn"] else "watch")
        out.append({"key": "%s|geo_move|%s|%s" % (app["id"], cc, dr), "family": "geo_move", "metric": h["metric"],
                    "dir": dr, "cc": cc, "severity": sev, "now": h["now"], "before": h["before"], "rel": h["rel"],
                    "delta_pp": h["delta"], "z": _g4(h["z"]), "share": _g4(h["share"]),
                    "also": [x["metric"] for x in hits[1:]], "week_from": _iso(min(h["rec"])),
                    "week_to": _iso(max(h["rec"]) + timedelta(days=6)), "base_from": _iso(min(h["base"])),
                    "base_to": _iso(max(h["base"]) + timedelta(days=6)), "users": int(h["n"]), "spend": None,
                    "tags": [], "release": None})
        if h.get("sp") is not None:                    # the lead metric's split (SPEC_SPLIT F5 / F7)
            out[-1]["sp"] = h["sp"]
    return out


def _geo_cost_conds(C, ci, geo, H, streak, app):
    """geo_cost (only with country cost): the country's q80 earning at H stays under its cost per install for two
    weekly evaluations, or its observed 30-day earning is under 0.3 × its cost. With the week envelope also: never for
    a country whose ads are a trickle (_geo_thin), never for one no worse than the whole app when the app itself does
    not pay back (that is the app's cost — pay_loss / pay_slow say it once, not once per country), a streak ends when
    its country stops qualifying (only a window whose data is not whole freezes it), and the strongest leads (the
    episodes' dedupe sends one per app and 7 days)."""
    G = geo if isinstance(geo, _Geo) else _Geo(geo)
    env = G.env()
    out = []
    ws = ci["win"][1]
    if env and G.why(ws) != "ok":                     # a window week not covered: nothing judged, streaks kept
        return out
    if env and not all(C.clean(W, 30) for W in ci["win"][30] or []):
        return out                                    # GA4's 30-day weeks not whole: nothing judged, streaks kept
    total = G.total(ws)                               # every country's cost, the unmapped part included
    app_ratio = None                                  # the whole app: its cost per install ÷ its q80 earning at H
    if env and total > 0:
        n_all = sum(C.P["wk"][W]["n"] for W in ws)
        ah = (ci.get("app_h") or {}).get("hi")
        if n_all and ah:
            app_ratio = (total / n_all) / ah
    seen = set()
    for cc in sorted(G.ccs(ws)):
        if cc in (UNMAPPED, "--", "ZZ"):
            continue
        k = "geo_cost|%s" % cc
        seen.add(k)
        cost, dl = G.cost(cc, ws)
        _, n = _cty_sums(C, cc, ws, 1, "u")
        if not n or cost < max(GEOCOST_MIN_SPEND, GEOCOST_SHARE * total) or n < CTY_JUDGE:
            if env:
                streak[k] = 0
            continue
        if not env and not all(C.clean(W, 30) for W in ci["win"][30] or []):
            continue
        if env and _geo_thin(cost, dl, n, len(ws)):
            streak[k] = 0
            continue
        cpi = cost / n
        y30, n30 = _cty_sums(C, cc, ci["win"][30], 30, "r")
        r30 = y30 / n30 if n30 else None
        hi = ((ci.get("h") or {}).get(cc) or {}).get("hi")
        if env and app_ratio is not None and app_ratio > 1 and hi and cpi / hi <= (1 + GEO_APPWIDE) * app_ratio:
            streak[k] = 0                             # no worse than the app, which does not pay back as a whole
            continue
        now_bad = (hi is not None and hi < cpi)
        streak[k] = (streak.get(k, 0) + 1) if now_bad else 0
        if streak[k] >= 2 or (r30 is not None and r30 < 0.3 * cpi):
            share = cost / total if total else 0
            sev = "warning" if (share >= GEOCOST_WARN_SHARE and hi is not None and hi < 0.5 * cpi) else "watch"
            out.append({"key": "%s|geo_cost|%s" % (app["id"], cc), "family": "geo_cost", "metric": "cost",
                        "dir": "down", "cc": cc, "severity": sev, "now": _m6(cpi), "before": _m6(hi), "rel": None,
                        "z": None, "share": _g4(share), "week_from": _iso(min(ws)),
                        "week_to": _iso(max(ws) + timedelta(days=6)), "base_from": None, "base_to": None,
                        "users": int(n), "spend": _m6(cost / max(len(ws), 1)), "tags": [], "release": None})
    if env:
        for k in [k for k in streak if k.startswith("geo_cost|") and k not in seen]:
            streak[k] = 0                             # a country no longer in the window's cost: its streak ends
        out.sort(key=lambda c: (SEV_ORDER[c["severity"]], -(c["share"] or 0), c["cc"]))   # the one sent: the biggest
    return out


# ── episodes (§2.7: seeding, burn-in, closing, dedupe) ──────────────────────────────────────────

def _snap(c):
    out = {}
    for k, v in c.items():
        if k.startswith("_") or k in ("key", "seed"):
            continue
        if isinstance(v, float):
            v = round(v, 6)
        out[k] = v
    return out


def _eid(app_id, c, opened, extra=""):
    return fingerprint(app_id, "value_%s_%s" % (c["family"], c["metric"]), c.get("cc") or c.get("ver"), c["dir"],
                       opened + extra)


def episodes(st, app_id, E, conds, advanced, now, close=()):
    """Open / refresh / close this app's value episodes from this week's conditions (each carrying `seed`). Pure:
    returns the new {episodes, closed}. Nothing changes unless the week end advanced (hourly re-runs are no-ops).
    close = episode keys that close now (a version that left the newest ones C judges), if not true this week.
    Dedupe (DEDUP): one notification per app, family group (pay_* / ver_ret / long_ret) and direction per N days.
    SPEC_SIMPLIFY (shown only): a new episode keeps opened_at = now and week_from0 (its first changed week, the earliest
    over its refreshes); a close adds closed_at = now and close_reason (recovered: the condition went away; window_end:
    a version C no longer judges — evaluate_app also marks a pay_loss closed because the ads stopped)."""
    eps = {k: dict(e) for k, e in (st.get("episodes") or {}).items()}
    closed = [dict(e) for e in st.get("closed") or []]
    just_closed = []
    if advanced:
        E_iso, hit, pay_now = _iso(E), set(), set()
        for c in conds:
            key, snap = c["key"], _snap(c)
            ep = eps.get(key)
            if ep is None:
                seed = bool(c["seed"])
                keep = REOPEN_SEED_DAYS.get(c["family"])
                if not seed and keep:                     # the same episode back soon after it closed (a state that
                    for e in closed:                      # flaps near its line, a country's slower 30-day echo of a
                        if (e["family"] == c["family"] and e.get("cc") == c.get("cc") and e["dir"] == c["dir"]
                                and 0 <= (E - _d(e["closed"])).days <= keep):   # drop already told): shown, not sent
                            seed = True
                grp = DEDUP_OF.get(c["family"])
                if not seed and grp:                      # one notification per app, group and direction per N days
                    fams, days = DEDUP[grp]
                    seed = (grp, c["dir"]) in pay_now
                    for e in list(eps.values()) + closed:
                        if (e["family"] in fams and e["dir"] == c["dir"] and not e.get("seeded")
                                and e.get("notified_at") and (_d(now) - _d(e["notified_at"])).days < days):
                            seed = True
                    if not seed:
                        pay_now.add((grp, c["dir"]))
                ep = {"id": _eid(app_id, c, E_iso), "app_id": app_id, "family": c["family"], "metric": c["metric"],
                      "cc": c.get("cc"), "dir": c["dir"], "opened": E_iso, "last_true": E_iso, "misses": 0,
                      "notified_at": now if seed else None, "notified_dry": False, "seeded": seed, "last": snap,
                      "opened_at": now}                   # the run that opened it (never rewritten)
                if snap.get("week_from"):
                    ep["week_from0"] = snap["week_from"]     # its first changed week ("Shuru" — shown only)
                eps[key] = ep
            else:
                was = ep["last"].get("severity")
                ep.update(last_true=E_iso, misses=0, last=snap)
                if snap.get("week_from"):                     # the earliest changed week this episode told
                    ep["week_from0"] = min(ep.get("week_from0") or snap["week_from"], snap["week_from"])
                if (snap.get("severity") == "warning" and was != "warning" and ep.get("notified_at") is not None
                        and not ep.get("seeded")):
                    ep["id"] = _eid(app_id, c, ep["opened"], "|warning")      # a watch that turned red: sent again
                    ep["notified_at"] = now if c["seed"] else None
                    ep["notified_dry"], ep["seeded"] = False, bool(c["seed"])
                elif c["seed"] and ep.get("notified_at") is None:
                    ep.update(notified_at=now, seeded=True)
            hit.add(key)
        for key in [k for k in eps if k not in hit]:
            ep = eps[key]
            ep["misses"] = ep.get("misses", 0) + 1
            gone = ep["misses"] >= (1 if ep["family"] == "pay_loss" else CLOSE_WEEKS)
            if gone or key in close:                       # (a version C no longer judges: its window ended)
                done = U.close_ep(eps.pop(key), E_iso, now, "recovered" if gone else "window_end")
                closed.append(done)
                just_closed.append(done)
        keep = E - timedelta(days=CLOSED_KEEP_DAYS)
        closed = [e for e in closed if _d(e["closed"]) >= keep]
    return {"episodes": eps, "closed": closed}, just_closed


def _range_txt(s):
    """" (andaza lo–hi)" for a projected figure with a real range, else ""."""
    if s.get("obs") or s.get("never"):
        return ""
    if s.get("rough"):
        return " (andaza kaafi kaccha)"
    lo, hi = s.get("lo"), s.get("hi")
    if lo is None or hi is None or lo == hi:
        return ""
    return " (andaza %s–%s)" % (lo, ">365" if hi >= 366 else hi)


def alert_text(s, app_name, H, ref):
    """An episode's snapshot → its Hinglish sentence (§2.8); money and countries as tokens (the page draws them)."""
    fam = s["family"]
    wk = _span(s["week_from"], s["week_to"], ref) if s.get("week_from") else ""
    if fam == "pay_slow":
        pp = "%s din" % (">365" if (s.get("p") or 0) >= 366 else s.get("p"))
        p0 = "%s din" % (">365" if (s.get("p0") or 0) >= 366 else s.get("p0"))
        head = "Ads ka paisa %s: %s ke installs ~%s%s (pehle ~%s)" % (
            "jaldi wapas" if s["dir"] == "up" else "wapas aane me der", wk, pp, _range_txt(s), p0)
        cause = s.get("cause") or ("%s100 pe 7 din me %s, pehle %s" % (T_C, t_p(s.get("now")), t_p(s.get("before"))))
        txt = head + " — " + cause
        if s.get("release"):
            txt += " · %s ke baad" % (("v" + str(s["release"]["version"])) if s["release"].get("version")
                                      else "App update")
        return txt
    if fam == "pay_loss":
        txt = "%s ke installs %d din me paisa wapas nahi karte (%s) — ads ka kharcha %s/hafta" % (
            wk, H, p_phrase(s).replace(" (", ", ").rstrip(")"), t_s(s.get("spend"), s.get("spend_src")))
        if "market_wide" in (s.get("tags") or []):
            txt += " · ad rate (eCPM) sab apps me gira"
        return txt
    if fam == "geo_move":
        name = t_cc(s["cc"])
        if s["metric"] == "rpi7":
            return "%s me kamai per install (7 din) %s: %s, pehle %s (%s%s, 2 hafte se)" % (
                name, "kam" if s["dir"] == "down" else "zyada", t_m(s["now"]), t_m(s["before"]),
                "+" if (s.get("rel") or 0) > 0 else "", _pct(s.get("rel") or 0))
        n = int(s["metric"][1:])
        return "%s me %s wapas aane wale %s: 100 me %s, pehle %s (2 hafte se) — %s = installs ka %s" % (
            name, NWORD[n], "kam" if s["dir"] == "down" else "zyada", _int(s["now"]), _int(s["before"]), name,
            _pct(s.get("share") or 0))
    if fam == "geo_cost":
        name = t_cc(s["cc"])
        pct = _pct((s["before"] or 0) / s["now"]) if s.get("now") else "—"
        return "%s me ads mehenge: install %s ka, %d din me kamai sirf %s (%s wapas) — kharcha %s/hafta" % (
            name, t_q(s["now"]), H, t_m(s.get("before")), pct, t_s(s.get("spend")))
    if fam == "iv_link":
        return ("GA4 me AdMob ki kamai ka sirf %s%% dikh raha (pehle %s%%) — Firebase–AdMob link check karo; is tab ki "
                "kamai AdMob ke hisaab se ≈" % (_int(s.get("now")), _int(s.get("before"))))
    if fam in ("ver_ret", "long_ret"):                # C / D (VALUE_CD): their own module's sentences
        from . import value_cd as VC
        return VC.ver_alert_text(s) if fam == "ver_ret" else VC.long_alert_text(s)
    return ""


def p_phrase(p):
    """ "{P} din me" / "~{P} din me (andaza lo–hi)" / "saal bhar me bhi nahi (≈x% wapas)" / "abhi pata nahi"."""
    if not p:
        return "abhi pata nahi"
    if p.get("never"):
        return "saal bhar me bhi nahi (≈%s%% wapas)" % _int(p.get("pct365"))
    if p.get("p") is None:
        return "abhi pata nahi"
    if p.get("obs"):
        return "%d din me" % p["p"]
    if p.get("shape") == "portfolio":
        return "~%d din me (andaza kaafi kaccha, dusre apps ke hisaab se)" % p["p"]
    if p.get("rough"):
        return "~%d din me (andaza kaafi kaccha)" % p["p"]
    lo, hi = p.get("lo"), p.get("hi")
    if lo is not None and hi is not None and lo == hi:
        return "~%d din me" % p["p"]                     # a range of zero width says nothing: left out
    return "~%d din me (andaza %s–%s)" % (p["p"], lo if lo is not None else "?", hi if hi is not None else ">365")


def started_of(ep):
    """A value episode → its "Shuru" (SPEC_SIMPLIFY §1.2, shown only): the first install week of the change — the
    earliest changed week the episode told (week_from0), else its snapshot's week_from (ver_ret: the new version's first
    compared install day; long_ret: the first day of its first month)."""
    wf = (ep.get("last") or {}).get("week_from")
    w0 = ep.get("week_from0")
    return min(w0, wf) if (w0 and wf) else (w0 or wf)


def alert_obj(ep, app_name, E, H, S=None, src_ccy=None):
    """Episode → the alert object (Active's alert keys + the value ones). Rebuilt every build. `text` carries money /
    country tokens (the page draws them in the viewer's currency); `message` (Telegram / email) is written out in USD,
    the report currency. data_till = S, the newest install-day data the tab has read.
    SPEC_SIMPLIFY (shown only): started (started_of) / started_cap (always False here), seeded, opened_at (None: opened
    before it was kept) and, closed, closed_at / close_reason (None: closed before they were kept)."""
    s = dict(ep["last"], family=ep["family"], dir=ep["dir"], cc=ep.get("cc"))
    text = alert_text(s, app_name, H, E)
    out = {"id": ep["id"], "source": "value", "app_id": ep["app_id"], "app": app_name, "family": ep["family"],
           "metric": s.get("metric", ep["metric"]), "cc": ep.get("cc"), "also": list(s.get("also") or []),
           "dir": ep["dir"], "severity": s.get("severity") or "watch",
           "unit": "usd" if s.get("metric") == "rpi7" else UNIT.get(ep["family"], "num"),
           "now": s.get("now"), "before": s.get("before"), "rel": s.get("rel"), "delta_pp": s.get("delta_pp"),
           "z": s.get("z"), "p": s.get("p"), "p0": s.get("p0"), "since": s.get("week_from"), "day": None,
           "installs_from": s.get("week_from"), "installs_to": s.get("week_to"),
           "week_from": s.get("week_from"), "week_to": s.get("week_to"), "base_from": s.get("base_from"),
           "base_to": s.get("base_to"), "users": int(s.get("users") or 0), "spend": s.get("spend"),
           "opened": ep["opened"], "last_seen": ep["last_true"],
           "fresh": (E - _d(ep["opened"])).days < FRESH_DAYS, "notify": ep.get("notified_at") is None,
           "provisional": False, "estimate": bool(s.get("est")), "tags": sorted(set(s.get("tags") or [])),
           "release": dict(s["release"]) if s.get("release") else None, "linked": False,
           "market": dict(s["market"]) if s.get("market") else None,
           "data_till": _iso(S or E), "text": text, "message": "%s: %s" % (app_name, render_text(text))}
    if s.get("metric") in RPI_METRICS:
        out["unit"] = "usd"
    if ep["family"] in ("ver_ret", "long_ret"):        # C / D: the version / months the alert is about
        out["linked"] = bool(s.get("linked"))
        for k in ("ver", "ver_label", "pver_label", "months"):
            if k in s:
                out[k] = list(s[k]) if isinstance(s[k], list) else s[k]
    if s.get("move"):                                  # geo_cost that carries the same country's geo_move
        out["move"] = dict(s["move"])
    if s.get("sp") is not None and attrib.ON:         # the change's split (SPEC_SPLIT) — only when there is one
        out["sp"] = s["sp"]
    out.update(started=started_of(ep), started_cap=False, seeded=bool(ep.get("seeded")), opened_at=ep.get("opened_at"))
    if "closed" in ep:
        out.update(closed=ep["closed"], fresh=False, notify=False, closed_at=ep.get("closed_at"),
                   close_reason=ep.get("close_reason"))
    return out


def sort_alerts(alerts):
    """warning, watch, good; the newest start ("started") first; then app, id (never fresh / opened: SPEC_SIMPLIFY)."""
    return U.sort_alerts(alerts)


# ── tiles, info rows, summary (§2.6, §2.8) ──────────────────────────────────────────────────────

def _M(**kw):
    out = {"v": None, "base": None, "rel": None, "z": None, "usual": None, "st": "wait", "why": None, "est": False,
           "from": None, "to": None, "bfrom": None, "bto": None}
    out.update(kw)
    return out


def _alert_st(alerts, fams, metric=None):
    best = None
    for a in alerts:
        if a["family"] not in fams:
            continue
        st = "better" if a["dir"] == "up" else ("worse" if a["severity"] == "warning" else "watch")
        rank = ("worse", "watch", "better").index(st)
        if best is None or rank < best[0]:
            best = (rank, st)
    return best[1] if best else None


def _win(weeks, t):
    """The TILE_WEEKS newest settled CALENDAR weeks whose installs (and earnings to age t) are complete and whose Google
    Ads spend is known — the 4 weeks up to the newest such week, judged or not (a stopped app's months-old ads weeks
    are never "the last 4 weeks"; a thin or zero week counts as what it spent)."""
    ok = [w for w in weeks if w["cj"][_tj(t)] and w["spend"] is not None]
    if not ok:
        return []
    last = ok[-1]["W"]
    return [w for w in ok if w["W"] >= last - timedelta(days=7 * (TILE_WEEKS - 1))]


def _ads_state(weeks, pays, E, have_spend):
    """Is the app spending on Google Ads now? → (state, the newest judged week with 7 days of earnings (or None), the
    newest week that had any spend (or None)). state: "on" (that week ended ≤ ADS_STALE_DAYS before E), "none" (no
    Google Ads data at all), "spend_wait" (the newest weeks' spend is not in yet), "stopped" (spend known and zero in the
    last 4 settled weeks, after earlier spend), "noads" (never any), "thin", "new" (ads just started: no judged week has
    7 days yet)."""
    j7 = [w for w in weeks if w["judged"] and w["cj"][_tj(7)] and w["W"] + timedelta(days=6) <= E]
    n7 = j7[-1] if j7 else None
    last_sp = next((w for w in reversed(weeks) if w["spend"]), None)
    if n7 is not None and (E - (n7["W"] + timedelta(days=6))).days <= ADS_STALE_DAYS:
        return "on", n7, last_sp
    if not have_spend:
        return "none", n7, last_sp
    w0 = _win(weeks, 0)
    rec = [w for w in weeks if w["W"] + timedelta(days=6) <= E][-3:]
    if not w0 or any(w["why"] == "wait" for w in rec):
        return "spend_wait", n7, last_sp
    sp0 = sum(w["spend"] for w in w0)
    if sp0 <= 0:
        return ("stopped" if last_sp is not None else "noads"), n7, last_sp
    if any(w["judged"] for w in w0):
        return "new", n7, last_sp
    return "thin", n7, last_sp


def _stop_note(weeks, pays, last_sp, ref):
    """"{since} se Google Ads kharcha nahi — aakhri ads hafte ({span}): paisa {P_phrase} wapas"."""
    since = last_sp["W"] + timedelta(days=7)
    lj = next((w for w in reversed(weeks) if w["judged"] and pays.get(w["W"])), None)
    txt = "%s se Google Ads kharcha nahi" % U.fmt_day(since, ref)
    if lj is not None:
        p = pays[lj["W"]]
        sp = _span(lj["W"], lj["W"] + timedelta(days=6), ref)
        if p.get("never"):
            txt += " — aakhri ads hafte (%s) ke installs saal bhar me bhi paisa wapas nahi karte (≈%s%% wapas)" % (
                sp, _int(p.get("pct365")))
        else:
            txt += " — aakhri ads hafte (%s) ke installs %s paisa wapas" % (sp, p_phrase(p))
    return txt


def _tiles(P, weeks, pays, alerts, E, cty, H, have_spend=True):
    by_W = {w["W"]: w for w in weeks}
    S = P["S"]
    pay_al = _alert_st(alerts, ("pay_slow", "pay_loss"))
    r = _b7_at(by_W, E)
    z = _null_z(by_W, E, r[0]) if r else None
    maybe = None
    if r and z is not None and abs(z) >= MAYBE_Z and abs(math.exp(r[0]) - 1) >= MAYBE_REL:
        maybe = "maybe_dn" if r[0] < 0 else "maybe_up"
    state, n7, last_sp = _ads_state(weeks, pays, E, have_spend)
    note = None
    if state == "stopped":
        note = _stop_note(weeks, pays, last_sp, S)
    elif state == "spend_wait":
        tl = max((w["W"] + timedelta(days=6) for w in weeks if w["spend"] is not None), default=None)
        note = ("Google Ads kharcha %s se abhi nahi aaya — naye hafton ka paisa-wapas uske baad" %
                U.fmt_day(tl + ONE, S)) if tl else "Google Ads kharcha abhi nahi aaya"
    elif state == "new":
        note = "Ads shuru hue — andaza hafte ke installs ke 7 din pure hone ke ~5 din baad"
    elif state == "none":
        note = "Google Ads kharcha nahi mila"
    elif state == "noads":
        note = "Is app pe Google Ads kharcha nahi"
    idle = {"stopped": "nospend", "none": "nospend", "noads": "nospend", "thin": "thin", "spend_wait": "wait",
            "new": "wait"}
    # money back: the newest judged week with 7 days of earnings — only while the app spends
    p = pays.get(n7["W"]) if (state == "on" and n7 is not None) else None
    if state != "on":
        pay_t = _M(st=pay_al or idle[state], why=state, note=note)
    elif p is None:                                   # judged, 7 days in, but no curve to reach the target yet
        note = _curve_note(n7)
        lk = next((w for w in reversed(weeks) if w["judged"] and pays.get(w["W"]) and w["W"] < n7["W"]
                   and pays[w["W"]].get("shape") != "portfolio"), None)
        if lk is not None:                            # the newest week that IS known, named as such
            note += " · pichhla pata: %s ke installs %s" % (_span(lk["W"], lk["W"] + timedelta(days=6), S),
                                                             p_phrase(pays[lk["W"]]))
        pay_t = _M(st=pay_al or "wait", why="curve", note=note, **{
            "from": _iso(n7["W"]), "to": _iso(n7["W"] + timedelta(days=6))})
    else:
        i = weeks.index(n7)
        before = [pays[w["W"]] for w in weeks[:i] if w["judged"] and pays.get(w["W"])][-PAY_BASE_WEEKS:]
        p0 = _int(_med([_pval(x) for x in before])) if before else None
        st = pay_al or ("never" if p["never"] else (maybe or ("normal" if p0 is not None else "low")))
        pv = _pval(p)
        pay_t = _M(v=pv, base=p0, rel=_g4(pv / p0 - 1) if (p0 and pv is not None) else None, z=_g4(z), st=st,
                   est=not p["obs"], lo=p["lo"], hi=p["hi"], obs=p["obs"], never=p["never"], pct365=p["pct365"],
                   hi_over=p["hi_over"], rough=p["rough"], shape=p.get("shape"), why="on")
        pay_t["from"], pay_t["to"] = _iso(n7["W"]), _iso(n7["W"] + timedelta(days=6))
    # back in 7 days per 100 — the same week; its 30-day value that week's own (observed, else ≈ projected)
    if state == "on":
        w = n7
        v = 100 * w["R"][_tj(7)] / w["spend"]
        base = r[1]["b70"] * 100 if r else None
        v30, e30 = None, False
        if w["cj"][_tj(30)]:
            v30 = 100 * w["R"][_tj(30)] / w["spend"]
        elif w["_proj"][1][_tj(30)] is not None and w["ecpi"]:
            v30, e30 = 100 * w["_proj"][1][_tj(30)] / w["ecpi"], True
        b7_t = _M(v=_g4(v), base=_g4(base), rel=_g4(v / base - 1) if base else None, z=_g4(z),
                  st=pay_al or (maybe or ("normal" if base else "low")), est=any(w["E"][:4]),
                  v30=_g4(v30), v30_est=e30, **{"from": _iso(w["W"]), "to": _iso(w["W"] + timedelta(days=6))})
        if base:
            b7_t["bfrom"], b7_t["bto"] = _iso(r[1]["base"][0]["W"]), _iso(r[1]["base"][-1]["W"] + timedelta(days=6))
        if r:                                         # the split of money back per 100 (SPEC_SPLIT F7): the base
            x = _sp_vpi(r[1], [w])                    # weeks the tile's base is, after = the tile's own week
            if x is not None:
                b7_t["sp"] = x
    else:
        b7_t = _M(st=pay_al or idle[state], why=state, note=note)
    # earning per install (30 days, newest 4 complete weeks)
    c30 = [w for w in weeks if w["cj"][_tj(30)] and w["n"] > 0][-TILE_WEEKS:]
    if c30:
        n = sum(w["n"] for w in c30)
        v = sum(w["R"][_tj(30)] for w in c30) / n
        sub = {}
        for t in (1, 7):
            ws = [w for w in weeks if w["cj"][_tj(t)] and w["n"] > 0][-TILE_WEEKS:]
            sub[str(t)] = _m6(sum(w["R"][_tj(t)] for w in ws) / sum(w["n"] for w in ws)) if ws else None
        w90 = [w for w in weeks if w["cj"][_tj(90)] and w["n"] > 0][-TILE_WEEKS:]
        sub["90"] = _m6(sum(w["R"][_tj(90)] for w in w90) / sum(w["n"] for w in w90)) if w90 else None
        prev = [w for w in weeks if w["cj"][_tj(30)] and w["n"] > 0][-3 * TILE_WEEKS:-TILE_WEEKS]
        base = sum(w["R"][_tj(30)] for w in prev) / sum(w["n"] for w in prev) if prev else None
        rel = v / base - 1 if base else None
        st = "normal" if base else "low"
        if rel is not None and abs(rel) >= MAYBE_REL * 2:
            st = "maybe"
        rpi_t = _M(v=_m6(v), base=_m6(base), rel=_g4(rel), st=st, est=any(w["E"][_tj(30)] or w["q"][_tj(30)] for w in c30),
                   sub=sub, d90_obs=True, d90_est=any(w["E"][_tj(90)] or w["q"][_tj(90)] for w in w90),
                   **{"from": _iso(c30[0]["W"]), "to": _iso(c30[-1]["W"] + timedelta(days=6))})
        if base:                                      # the split: installs per week × earning per install (F7) —
            x = attrib.safe(lambda: attrib.ir(sum(w["n"] for w in prev) / len(prev), n / len(c30)))
            if x is not None:
                rpi_t["sp"] = x
    else:
        rpi_t = _M(st="wait")
    # cost per install: the last 4 settled CALENDAR weeks (the same window as the All-apps row and the pooled spend)
    w0 = _win(weeks, 0)
    sp0 = sum(w["spend"] for w in w0) if w0 else None
    if sp0:
        n = sum(w["n"] for w in w0)
        na = sum(w["n_ads"] or 0 for w in w0)
        src = sum(w.get("spend_src") or 0 for w in w0)
        cr = _cpi_at(by_W, E)
        cz = _null_z(by_W, E, cr[0], _cpi_at) if cr else None
        st = "normal"
        if cr and cz is not None and abs(cz) >= MAYBE_Z and abs(math.exp(cr[0]) - 1) >= MAYBE_REL:
            st = "maybe_dn" if cr[0] > 0 else "maybe_up"          # dn = the worse way: cost went UP
        jn = [w for w in w0 if w["judged"]]
        if st == "normal" and jn:                     # one week's big jump shows at once (never red: no alert yet)
            bw = [w for w in weeks if w["judged"] and w["W"] < jn[-1]["W"]][-PAY_BASE_WEEKS:]
            if len(bw) >= PAY_BASE_MIN:
                c0 = sum(w["spend"] for w in bw) / sum(w["n"] for w in bw)
                jr = jn[-1]["ecpi"] / c0 if c0 else None
                if jr is not None and jr >= CPI_JUMP:
                    st = "maybe_dn"
                elif jr is not None and jr <= 1 / CPI_JUMP:
                    st = "maybe_up"
        if pay_al and "cpi" in {t for a in alerts if a["family"] == "pay_slow" for t in a.get("tags") or []}:
            st = "worse" if pay_al == "worse" else ("watch" if pay_al == "watch" else st)
        cpi_t = _M(v=_m6(sp0 / n) if n else None, v_src=_m6(src / n) if n else None, ads=_m6(sp0 / na) if na else None,
                   ads_src=_m6(src / na) if na else None, paid_share=_g4(min(1.0, na / n)) if n else None,
                   spend4=_m6(sp0), spend4_src=_m6(src), n4=n, nw=len(w0), st=st, z=_g4(cz),
                   **{"from": _iso(w0[0]["W"]), "to": _iso(w0[-1]["W"] + timedelta(days=6))})
        if state == "on":                             # the split of the ad spend: installs × cost per install on
            x = _sp_spd(weeks, w0)                    # the tile's own 4 weeks vs the weeks before (F7)
            if x is not None:
                cpi_t["sp"] = x
    elif w0:                                          # known: nothing spent in these 4 weeks
        cpi_t = _M(st="nospend", why=state, note=note, spend4=0.0, spend4_src=0.0, n4=sum(w["n"] for w in w0),
                   nw=len(w0), **{"from": _iso(w0[0]["W"]), "to": _iso(w0[-1]["W"] + timedelta(days=6))})
    else:
        cpi_t = _M(st="nospend" if state in ("none", "noads") else "wait", why=state, note=note)
    rows = (cty or {}).get("rows") or []
    judged = [r_ for r_ in rows if r_.get("verdict") not in ("few", "wait", None)]
    ct = {"best": (cty or {}).get("best") or [], "weak": (cty or {}).get("weak") or [],
          "judged": len(judged), "of": len(rows), "all_avg": bool(judged) and all(r_["verdict"] == "avg" for r_ in judged),
          "st": ("wait" if not cty or not cty.get("win") else ("ok" if judged else "low"))}
    if cty and "keep" in cty:                        # country cost (the week envelope, every window week covered)
        ct["keep"], ct["costly"] = list(cty["keep"]), list(cty["costly"])
    return {"pay": pay_t, "b7": b7_t, "rpi": rpi_t, "cpi": cpi_t, "cty": ct, "ads": state}


def _curve_note(w):
    """Why a judged week with 7 days of earnings has no money-back estimate yet: the curve beyond its age."""
    med, jo = w["_proj"][1], w["_proj"][4]
    stop = next((T[j] for j in range(jo + 1, 10) if med[j] is None), 365) if jo is not None else 7
    return ("abhi andaza nahi (curve ke liye is app ke %d aise hafte chahiye jinke %d din pure ho chuke)"
            % (REF_MIN, stop))


def _ads_stale(weeks, pays, E):
    """No judged ads week within ADS_STALE_DAYS of E (_info's "ab Google Ads kharcha nahi"): the ads stopped."""
    jw = [w for w in weeks if w["judged"] and w["cj"][_tj(7)] and pays.get(w["W"])]
    return not jw or (E - (jw[-1]["W"] + timedelta(days=6))).days > ADS_STALE_DAYS


def _info(P, weeks, C, ci, just_closed, pays, E, spend_known, alerts=None):
    """Info rows (never alerts, never counted, never coloured)."""
    out = []
    ref = P["S"]
    # spend started / stopped (≥ 2 weeks)
    sw = [w for w in weeks if w["W"] + timedelta(days=6) <= E and w["spend"] is not None]
    if len(sw) >= 4:
        a, b = sw[-4:-2], sw[-2:]
        if all(w["spend"] for w in a) and not any(w["spend"] for w in b):
            out.append({"kind": "spend", "from": _iso(b[0]["W"]), "to": None,
                        "text": "%s se Google Ads kharcha band" % U.fmt_day(b[0]["W"], ref)})
        elif not any(w["spend"] for w in a) and all(w["spend"] for w in b):
            out.append({"kind": "spend", "from": _iso(b[0]["W"]), "to": None,
                        "text": "%s se Google Ads kharcha shuru" % U.fmt_day(b[0]["W"], ref)})
    # paid share
    pw = [w for w in weeks if w["paid"] is not None and w["cj"][0]]
    if len(pw) >= 10:
        a = _med([w["paid"] for w in pw[-10:-2]])
        b = sum(w["paid"] for w in pw[-2:]) / 2
        if abs(b - a) * 100 >= INFO_PTS:
            out.append({"kind": "paid", "from": _iso(pw[-2]["W"]), "to": _iso(pw[-1]["W"] + timedelta(days=6)),
                        "text": "Ads wale installs ka hissa %d%% → %d%%" % (round(100 * a), round(100 * b))})
    # the scale
    kin, wa = P["sc"]["kinfo"], P["sc"]["weeks_all"]
    rec_k = [kin[W] for W in wa if W + timedelta(days=6) <= P["S"]][-4:]
    bad = [v for v in rec_k if v[1] not in ("none", "nomob") and v[2]]
    if bad:
        raw = _med([v[3] for v in bad])
        out.append({"kind": "k", "from": None, "to": None,
                    "text": "GA4 me AdMob ki kamai ka %d%% dikhta — install-wise kamai AdMob ke hisaab se scale ki (≈)"
                    % int(round(100 / raw))})
    # countries: mix, new in the top 8, a week not clean
    if C is not None and ci is not None:
        ws = C.weeks(1, 10)
        if len(ws) >= 10:
            rec, base = ws[:2], ws[2:]
            nr = sum(C.P["wk"][W]["n"] for W in rec)
            nb = sum(C.P["wk"][W]["n"] for W in base)
            top_b = sorted((cc for cc in C.cset if cc not in ("--", "ZZ")),
                           key=lambda cc: (-_cty_sums(C, cc, base, 1, "u")[1], cc))[:GEO_TOPK]
            top_r = sorted((cc for cc in C.cset if cc not in ("--", "ZZ")),
                           key=lambda cc: (-_cty_sums(C, cc, rec, 1, "u")[1], cc))[:GEO_TOPK]
            for cc in top_b:
                s0 = _cty_sums(C, cc, base, 1, "u")[1] / nb if nb else 0
                s1 = _cty_sums(C, cc, rec, 1, "u")[1] / nr if nr else 0
                if abs(s1 - s0) * 100 >= INFO_PTS:
                    out.append({"kind": "mix", "cc": cc, "from": _iso(min(rec)), "to": _iso(max(rec) + timedelta(days=6)),
                                "text": "%s ke installs ka hissa %d%% → %d%% — campaign/country targeting badli?"
                                % (cname(cc), round(100 * s0), round(100 * s1))})
            for cc in top_r:
                if cc not in top_b and _cty_sums(C, cc, rec, 1, "u")[1] >= CTY_JUDGE:
                    out.append({"kind": "new_cty", "cc": cc, "from": _iso(min(rec)), "to": None,
                                "text": "%s ab top %d countries me (installs ke hisaab se)" % (cname(cc), GEO_TOPK)})
        for W in C.weeks(1, WIN_WEEKS):
            if not C.clean(W, 1):
                out.append({"kind": "gap", "from": _iso(W), "to": _iso(W + timedelta(days=6)),
                            "text": "Is hafte ka country data GA4 ne poora nahi baanta — countries ka faisla ruka."})
                break
    for ep in just_closed:
        if ep["family"] == "pay_loss":
            jw = [w for w in weeks if w["judged"] and w["cj"][_tj(7)] and pays.get(w["W"])]
            p = pays[jw[-1]["W"]] if jw else None
            stale = not jw or (E - (jw[-1]["W"] + timedelta(days=6))).days > ADS_STALE_DAYS
            txt = ("✅ ab Google Ads kharcha nahi — paisa-wapas ka alert band" if stale else
                   "✅ ab paisa ~%s din me wapas" % (_pval(p) if p and _pval(p) is not None else "?"))
            out.append({"kind": "closed", "from": ep["opened"], "to": ep["closed"], "text": txt})
    for a in alerts or []:                            # the market's move, said once (never an app's own alert)
        mk = a.get("market")
        if mk and "market_wide" in (a.get("tags") or []):
            out.append({"kind": "market", "from": mk.get("from"), "to": mk.get("to"),
                        "text": "Ad rate (eCPM) sab apps me %s — %s me se %s apps me; isliye is app ka paisa-wapas "
                                "alert sirf dikhaya, bheja nahi" % ("gira" if a["dir"] == "down" else "badha",
                                                                   mk.get("apps") or "?", mk.get("of") or "?")})
            break
    return out


def _summary(tiles, alerts, weeks, pays, ida_state, ida_pct, ida_left, E, ref):
    """The one line on top (§2.8), in order: an open warning / watch / good alert; else the newest week AS IT IS —
    "✅ … normal jaisa" only when it pays back within the year and looks like the weeks before; "💸 … saal bhar me
    ≈x% hi wapas" (no alert yet); no ads now (stopped, with its last ads weeks); data still coming — each with its
    own reason."""
    worse = [a for a in alerts if a["severity"] == "warning"]
    if worse:
        more = len(alerts) - 1
        return {"kind": "worse", "text": "⚠️ " + worse[0]["text"] + (" (+%d aur — neeche dekho)" % more if more else "")}
    watch = [a for a in alerts if a["severity"] == "watch"]
    if watch:
        return {"kind": "watch", "text": "🟡 " + watch[0]["text"]}
    good = [a for a in alerts if a["severity"] == "good"]
    if good:
        return {"kind": "better", "text": "🟢 " + good[0]["text"]}
    pt = tiles["pay"]
    state = tiles.get("ads")
    if state == "on" and pt.get("v") is not None:
        span = _span(pt["from"], pt["to"], ref)
        p0 = pt.get("base")
        before = ((" (pehle saal bhar me bhi nahi)" if p0 >= 366 else " (pehle ~%s din)" % p0)
                  if p0 is not None else "")
        port = pt.get("shape") == "portfolio"            # projected from the other apps' curves: the pay alerts never
        alert = "" if port else "2 hafte aisa raha to alert"    # judge such a week (_conditions) — no alert promised
        if pt["st"] == "never" or pt.get("never"):
            return {"kind": "never", "text": "💸 Is hafte (%s) ke installs saal bhar me ≈%s%% hi ads ka paisa wapas "
                                             "karte%s%s%s." % (span, _int(pt.get("pct365")),
                                                               " (andaza dusre apps ke hisaab se)" if port else "",
                                                               before, " — " + alert if alert else "")}
        ph = p_phrase(dict({k: pt.get(k) for k in ("lo", "hi", "obs", "never", "pct365", "rough", "shape")},
                           p=pt["v"]))
        if pt["st"] in ("maybe_dn", "maybe_up"):
            return {"kind": "maybe", "text": "🔵 Is hafte (%s) ke installs %s ads ka paisa wapas%s — shayad %s%s." % (
                span, ph, before, "dheere" if pt["st"] == "maybe_dn" else "jaldi", ", " + alert if alert else "")}
        if pt["st"] == "normal":
            return {"kind": "ok", "text": "✅ Is hafte (%s) ke installs %s ads ka paisa wapas — normal jaisa%s." % (
                span, ph, before)}
        return {"kind": "ok", "text": "✅ Is hafte (%s) ke installs %s ads ka paisa wapas (pehle ke hafte abhi kam — "
                                      "normal baad me)." % (span, ph)}
    if not weeks:
        return {"kind": "wait", "text": "⏳ Install-wise kamai ka data aa raha — abhi koi poora install-hafta nahi."}
    r30 = tiles["rpi"]["v"]
    if state == "none":
        return {"kind": "nospend", "text": "ℹ️ Google Ads kharcha abhi nahi mila — 30 din me kamai per install %s."
                % t_m(r30)}
    if state in ("stopped", "noads"):
        return {"kind": "nospend", "text": "ℹ️ %s. 30 din me kamai per install %s." % (
            pt.get("note") or "Google Ads kharcha nahi", t_m(r30))}
    if ida_state != "whole":
        return {"kind": "wait", "text": "⏳ Install-wise kamai ka data aa raha — %d%% history aa gayi, ~%d din me poora." % (
            ida_pct or 0, ida_left or 0)}
    if state == "spend_wait":
        return {"kind": "wait", "text": "⏳ %s." % (pt.get("note") or "Google Ads kharcha abhi nahi aaya")}
    if state == "new":
        return {"kind": "wait", "text": "⏳ %s." % pt.get("note")}
    if state == "on":                                  # judged, 7 days in, no curve yet
        return {"kind": "wait", "text": "⏳ Ads ka paisa kitne din me wapas — %s." % (pt.get("note") or "abhi andaza nahi")}
    return {"kind": "thin", "text": "ℹ️ Google Ads kharcha thoda — paisa-wapas ka faisla nahi (hafte me %s aur %d "
                                    "installs chahiye)." % (t_b(SPEND_MIN_WEEK), N_MIN_WEEK)}


def _ida_state(ida, hs, S):
    """wait / filling / whole + the share of the history folded and a rough "~n days to go"."""
    fr = ida.get("from")
    if not fr or not ida.get("to"):
        return "wait", 0, None
    span = max((S - hs).days + 1, 1)
    have = (S - max(_d(fr), hs)).days + 1
    pct = int(min(100, max(0, round(100 * have / span))))
    if ida.get("done"):
        return "whole", 100, 0
    left = max(0, (_d(fr) - hs).days)
    return "filling", pct, int(math.ceil(left / DAYS_PER_FETCH)) if left else 0


# ── one app ─────────────────────────────────────────────────────────────────────────────────────

def _inputs_seen(ev_inputs, E, weeks, cty_clean_weeks, kvalid, spend_seen, geo_on, cd=None):
    """inputs[x] = the week end E when input x was first seen (never now) — the burn-in anchor. cd (VALUE_CD on) =
    {"ver": seen, "long": seen}: the C / D inputs (their keys exist only then — the state is unchanged while it is
    off)."""
    inp = dict(ev_inputs or {})
    E_iso = _iso(E)
    if inp.get("iday") is None and sum(1 for w in weeks if w["cj"][_tj(7)] and w["n"] > 0) >= INPUT_IDAY_WEEKS:
        inp["iday"] = E_iso
    if inp.get("cty") is None and cty_clean_weeks >= INPUT_CTY_WEEKS:
        inp["cty"] = E_iso
    if inp.get("spend") is None and spend_seen:
        inp["spend"] = E_iso
    if inp.get("geo") is None and geo_on:
        inp["geo"] = E_iso
    if inp.get("k") is None and kvalid:
        inp["k"] = E_iso
    for k in ("iday", "cty", "spend", "geo", "k"):
        inp.setdefault(k, None)
    if cd is not None:
        for k in ("ver", "long"):
            if inp.get(k) is None and cd.get(k):
                inp[k] = E_iso
            inp.setdefault(k, None)
    return inp


def _seed_keys(c):
    """The inputs a condition stands on: its family's, plus the AdMob scale when an earning metric leads C / D."""
    keys = INPUTS[c["family"]]
    if c["family"] in ("ver_ret", "long_ret") and c.get("metric") in RPI_METRICS:
        keys = keys + ("k",)
    return keys


def _seed(fam, inputs, E, first, keys=None):
    if first:
        return True
    for k in (keys or INPUTS[fam]):
        v = inputs.get(k)
        if v is None or (E - _d(v)).days < BURNIN_DAYS:
            return True
    return False


def empty_state():
    return {"eval": None, "episodes": {}, "closed": []}


def evaluate_app(store, ida, rev, spend, fx, udet_releases, st_app, portfolio_shape, cfg, now_iso, *, app_id, app,
                 key=None, act_alerts=None, geo=None, ded=None, market=None, impact=None):
    """One app → (detail, row, new_state). market = Active's market prepass (engine.active.market: the weeks most
    apps' ad rate moved together) — a money-back move that is only the market's is shown, never sent. impact =
    value_build.release_impact (version → its Update impact verdict), read by C only (cfg["cd"], VALUE_CD). geo = the
    Google Ads country cost (GADS_GEO): None, a legacy per-country shape or the week envelope (_Geo). `st_app` = this
    app's slice of the value state {eval, episodes, closed} (never changed: the new slice is returned). detail = the lazy value_<key>.json.gz, row = its summary row in
    dashboard["value"]["apps"] (with "_alerts" / "_shape" for value_build.finish to take off)."""
    cfg = cfg or {}
    H = cfg.get("payback_days") or H_DEFAULT
    H = H if H in H_ALLOWED else H_DEFAULT
    st_app = st_app or empty_state()
    ded_rate = (ded or {}).get("rate") if cfg.get("deduct", True) else None
    hs = _d(store["history_start"])
    src = [str(store.get("property_id") or ""), str(store.get("stream_id") or "")]
    S0 = settled_day(ida, hs) if ida and ida.get("to") else None
    if S0 is None:                                  # no install-day file yet, or not one day of it folded yet
        return _wait_detail(store, ida, app_id, app, key, H, hs), _wait_row(app_id, app, key, ida, hs), st_app
    P = _prep(store, ida, rev, ded_rate, S0)
    S = P["S"]
    fx_mode = _spend_weeks(P, spend, fx)
    weeks = [w for w in P["weeks"] if w["cj"][0] and w["n"] > 0]
    shapes = _Shapes(weeks, portfolio_shape)
    pays = {}
    for w in weeks:
        L, med, lo, hi, jo, how = _project(w, shapes)
        w["_proj"] = (L, med, lo, hi, jo, how)
        if w["judged"]:
            p = _payback(L, med, lo, hi, jo, w["ecpi"])
            if p is not None:
                if how == "portfolio" and not p["obs"]:
                    p.update(rough=True, shape="portfolio")      # other apps' curves: kaafi kaccha, never alerted
                pays[w["W"]] = p
    E = _eval_end(S)
    # ── the weekly evaluation ──
    ev = st_app.get("eval")
    first = ev is None or ev.get("src") != src
    base_st = empty_state() if (ev is not None and ev.get("src") != src) else st_app
    if ev is not None and ev.get("src") != src:
        ev = None
    advanced = ev is None or ev.get("end_week") is None or _iso(E) > ev["end_week"]
    cs = (ev or {}).get("cty_sets") or {}
    prev_sets = cs.get("cur") if advanced else cs.get("prev")      # the Top / Low of the weekly evaluation before
    try:
        cty, C, ci = _countries(P, ida, shapes, H, geo, app, prev_sets)
    except ZeroDivisionError:
        cty, C, ci = None, None, None
    cty_clean = len([W for W in C.weeks(30) if C.clean(W, 30)]) if C is not None else 0
    spend_seen = any(w["judged"] for w in weeks)
    streak = dict((ev or {}).get("streak") or {})
    app_ref = {"id": app_id, "name": app}
    # C (new users by the app version they installed) and D (long-term by install month) — VALUE_CD only, each its own
    # try: a failure costs that part ("error"), never the app
    byv = lng = None
    cd_conds, cd_info, close_now, cd_seen = [], [], set(), None
    if cfg.get("cd"):
        from . import value_cd as VC
        cd_seen = {"ver": False, "long": False}
        try:
            st2 = dict(streak)
            byv, vconds = VC.versions(P, store, udet_releases, impact, E, advanced, st2, app_ref, market, spend)
            streak = st2
            cd_conds += vconds
            cd_info += byv.pop("_info", None) or []
            cd_seen["ver"] = bool(byv.pop("_seen", False))
            live = byv.pop("_live", None)
            if live is not None:
                close_now = {k for k, e in (base_st.get("episodes") or {}).items()
                             if e.get("family") == "ver_ret" and (e.get("last") or {}).get("ver") not in live}
        except Exception:
            byv = {"state": "error", "rows": [], "text": None}
        try:
            lng, lconds = VC.long_term(P, shapes, spend, fx, udet_releases, ida, E, advanced, app_ref)
            cd_conds += lconds
            cd_info += lng.pop("_info", None) or []
            cd_seen["long"] = bool(lng.pop("_seen", False))
        except Exception:
            lng = {"state": "error", "rows": [], "text": None}
    G = _Geo(geo)                                   # the country cost input: seen once its window is covered
    geo_seen = G.on() and (not G.env() or (ci or {}).get("geo_why") == "ok")
    inputs = _inputs_seen((ev or {}).get("inputs") if ev and ev.get("iday_v") == ida.get("v") else None, E, weeks,
                          cty_clean, P["sc"]["valid"], spend_seen, geo_seen, cd_seen)
    if not G.on():                                  # GADS_GEO off (or no cost for this app): switched on again later
        inputs["geo"] = None                        # is a new input with a new burn-in — and a new 2-evaluation streak
        for k in [k for k in streak if k.startswith("geo_cost|")]:
            del streak[k]
    if not cfg.get("cd"):                           # VALUE_CD off: the same for C / D (a state switched on → off is
        inputs.pop("ver", None)                     # then exactly one that was never on; on again = a new burn-in
        inputs.pop("long", None)                    # and new streaks)
        for k in [k for k in streak if k.startswith("ver_ret|")]:
            del streak[k]
    conds = (_conditions(P, weeks, pays, H, E, ci, C, udet_releases, act_alerts, geo, streak, app_ref, market)
             + cd_conds if advanced else [])
    for c in conds:
        c["seed"] = _seed(c["family"], inputs, E, first, _seed_keys(c)) or bool(c.pop("_force_seed", False))
        c["est"] = P["sc"]["st"] != "ok" or bool(c.pop("_est", False))
    new_st, just_closed = episodes(base_st, app_id, E, conds, advanced, now_iso, close=close_now)
    for ep in just_closed:                           # a pay_loss closed because the ads stopped: its window ended, the
        if ep["family"] == "pay_loss" and _ads_stale(weeks, pays, E):          # money never came back (shown only)
            ep["close_reason"] = "window_end"
    if advanced:
        new_ev = {"end_week": _iso(E), "src": src, "iday_v": ida.get("v"), "inputs": inputs,
                  "streak": {k: v for k, v in sorted(streak.items()) if v},
                  "cty_sets": {"cur": (cty or {}).get("sets") or {"top": [], "low": []}, "prev": cs.get("cur")}}
    else:
        new_ev = ev
    new_st["eval"] = new_ev
    src_ccy = (spend or {}).get("ccy") if spend else None
    open_eps = sorted(new_st["episodes"].values(), key=lambda e: e["id"])
    alerts = sort_alerts([alert_obj(e, app, E, H, S, src_ccy) for e in open_eps])
    closed = U.legacy_order([alert_obj(e, app, E, H, S, src_ccy) for e in new_st["closed"]])   # (history: its order)
    tiles = _tiles(P, weeks, pays, alerts, E, cty, H, have_spend=bool(spend))
    info = _info(P, weeks, C, ci, just_closed, pays, E, spend is not None, U.legacy_order(alerts)) + cd_info
    for r in info:                                   # "Shuru" (SPEC_SIMPLIFY, shown only): its since, else from
        r["started"] = r.get("since") or r.get("from")
    ida_state, ida_pct, ida_left = _ida_state(ida, hs, S)
    summary = _summary(tiles, U.legacy_order(alerts), weeks, pays, ida_state, ida_pct, ida_left, E, S)
    ads_state = tiles.pop("ads", None)
    detail = _detail(store, ida, P, weeks, pays, shapes, cty, alerts, closed, info, tiles, summary, fx_mode, fx, H,
                     app_id, app, key, ida_state, ida_pct, ded, udet_releases, left=ida_left,
                     spend_till=(spend or {}).get("till") if spend else None,
                     rev_till=(rev or {}).get("till"), src_ccy=src_ccy, by_version=byv, long=lng)
    detail["ads"] = ads_state                        # on / stopped / noads / none / spend_wait / thin / new
    row = _row(detail, weeks, pays, alerts, tiles, cty, ida_state, ida_pct, app_id, app, key, H)
    row["_alerts"] = alerts
    row["_closed"] = closed                          # every closed one (value_build.finish: the last 7 days' go up)
    own = {}
    for jo in range(9):
        for j in range(jo + 1, 10):
            g = shapes.app(jo, j)
            if g[0] is not None:
                own["%d→%d" % (T[jo], T[j])] = [g[0], g[1], g[2]]
    row["_shape"] = own
    return detail, row, new_st


def _curve_out(weeks, shapes):
    """The chart's "Normal (older weeks)" line: per ₹100, the median over the last 26 judged weeks complete at t."""
    normal = []
    for j in range(10):
        vals = [100 * w["R"][j] / w["spend"] for w in weeks if w["judged"] and w["cj"][j]][-REF_WEEKS:]
        normal.append(_g4(_med(vals)) if vals else None)
    jo = _tj(7)
    refs = shapes.app(jo, _tj(90))[3]
    src = "none"
    for w in weeks:
        if w["_proj"][5]:
            src = w["_proj"][5] if src != "portfolio" else src
    return {"shape": src, "ref": refs, "normal": normal}


def _week_out(w, pay, releases):
    L, med, lo, hi, jo, how = w["_proj"]
    judged = w["judged"]
    e = w["ecpi"]

    def per100(v):
        return _g4(100 * v / e) if (v is not None and judged and e) else None
    iap = [(_m6(w["P"][j] / w["n"]) if (w["cj"][j] and w["n"]) else None) for j in range(10)]
    iap_on = any(v and L[j] and v >= IAP_SHOW * L[j] for j, v in enumerate(iap))
    rel = None
    for r in releases or []:
        try:
            rd = _d(r.get("date"))
        except (TypeError, ValueError, AttributeError):
            continue
        if w["W"] <= rd <= w["W"] + timedelta(days=6):
            rel = {"date": _iso(rd), "version": r.get("version"), "kind": r.get("kind"), "key": r.get("key")}
    return {"from": _iso(w["W"]), "to": _iso(w["W"] + timedelta(days=6)), "n": w["n"], "n_ads": w["n_ads"],
            "spend": w["spend"], "ecpi": _m6(e), "cpi_ads": _m6(w["cpi_ads"]), "paid": _g4(w["paid"]),
            "spend_src": w.get("spend_src"),
            "ecpi_src": _m6(w["spend_src"] / w["n"]) if (w.get("spend_src") and w["n"]) else None,
            "cpi_ads_src": _m6(w["spend_src"] / w["n_ads"]) if (w.get("spend_src") and w["n_ads"]) else None,
            "judged": judged, "rpi": [_m6(v) for v in L], "L": [per100(v) for v in L],
            "Lq": [bool(w["q"][j] and L[j] is not None) for j in range(10)],
            "est": [bool(w["E"][j] and L[j] is not None) for j in range(10)],
            "Lp": [per100(v) for v in med], "Llo": [per100(v) for v in lo], "Lhi": [per100(v) for v in hi],
            "rpip": [_m6(v) for v in med], "iap": iap if iap_on else None, "t_o": T[jo] if jo is not None else None,
            "shape": how, "pay": pay, "why": w["why"] if not judged else (None if pay else "noproj"),
            "release": rel}


def _detail(store, ida, P, weeks, pays, shapes, cty, alerts, closed, info, tiles, summary, fx_mode, fx, H, app_id,
            app, key, ida_state, ida_pct, ded, releases, left=None, spend_till=None, rev_till=None, src_ccy=None,
            by_version=None, long=None):
    days = ida.get("days") or {}
    gbad = cty.pop("_gbad", None) if isinstance(cty, dict) else None
    cnt = {"ok": 0, "q": 0, "retry": 0, "empty": 0, "err": 0}
    cc = {"ok": 0, "smp": 0, "gap": 0, "retry": 0}
    for e in days.values():
        if isinstance(e, dict):
            if e.get("st") in cnt:
                cnt[e["st"]] += 1
            if e.get("cst") in cc:
                cc[e["cst"]] += 1
    S = P["S"]
    txt = []
    if (ida.get("flags") or {}).get("qb_win"):
        txt.append("GA4 me purane users ka data kam dikh raha — property ki data retention setting check karo")
    if ida.get("edge"):
        txt.append("GA4 me %s se pehle ka install-wise data nahi mila — history wahin se" % U.fmt_day(ida["edge"], S))
    sc = P["sc"]
    last12 = [d for d in sc["G"] if d > S - timedelta(days=84)]
    tot = sum((days.get(_iso(d)) or {}).get("rev") or 0 for d in last12)
    old = sum((days.get(_iso(d)) or {}).get("rb_old") or 0 for d in last12)
    g12 = (cty or {}).get("gap12") or {}
    wk_out = [_week_out(w, pays.get(w["W"]), releases) for w in reversed(weeks)]
    return {"v": VALUE_V, "app_id": app_id, "app": app, "key": key, "tz": P["tz"], "currency": "USD", "horizon": H,
            "settled_till": _iso(S), "fetched_at": store.get("fetched_at"),
            "spend_till": spend_till, "rev_till": rev_till,          # the header's "Google Ads till · AdMob till"
            "iday": {"from": ida.get("from"), "to": ida.get("to"), "cfrom": ida.get("cfrom"), "state": ida_state,
                     "pct": ida_pct, "left_days": left if ida_state == "filling" else None,
                     "days": sum(cnt.values()), "ok": cnt["ok"] + cnt["empty"], "q": cnt["q"],
                     "retry": cnt["retry"] + cnt["err"], "edge": ida.get("edge"),
                     "qb_win": bool((ida.get("flags") or {}).get("qb_win")), "cty": cc, "text": txt},
            "scale": {"k_weeks": [[_iso(W), _g4(v[0]), v[1] if not v[2] or v[1] in ("none", "nomob") else "est"]
                                  for W, v in sorted(sc["kinfo"].items())][-SCALE_WEEKS:],
                      "weeks": sc["weeks"][-SCALE_WEEKS:], "src": sc["src"],
                      "old_rev": _g4(old / tot) if tot else None,
                      "cty_gap": {"rev": g12.get("rev"), "n": g12.get("n")},
                      "st": sc["st"], "double": sc["double"],
                      "ded": ({"rate": _g4(ded["rate"]), "src": ded.get("src")} if ded and ded.get("rate") else None),
                      "text": _check_text(sc, g12, old / tot if tot else None, ded, fx_mode, S, src_ccy)
                      + _geo_check_text(cty, gbad, S)},
            "fx": {"mode": fx_mode, "now": (fx or {}).get("now"), "src": src_ccy},
            "tiles": tiles, "summary": summary, "weeks": wk_out, "curve": _curve_out(weeks, shapes),
            "countries": cty or {"win": None, "geo": False, "smp": False, "app": None, "rows": [],
                                 "small": {"countries": 0, "n": 0, "zz": 0}, "unknown": {"n": 0},
                                 "unassigned": {"n": 0, "rev_share": None}, "state": "wait"},
            "changes": {"open": alerts, "closed": closed[-20:], "info": info, "older": []},
            "by_version": by_version if by_version is not None else [], "long": long if long is not None else []}


def _geo_check_text(cty, gbad, S):
    """The Data check's Google Ads country lines — only with the week envelope (GADS_GEO); [] otherwise."""
    if not isinstance(cty, dict) or "geo_why" not in cty:
        return []
    out = []
    why, gc = cty.get("geo_why"), cty.get("geo_cov") or {}
    if why == "ok":
        t = "Google Ads country-wise kharcha: campaign kharche ka %s%% country me mila (last %d weeks)" % (
            _num1(100 * gc["v"]) if gc.get("v") is not None else "—", gc.get("weeks") or 0)
        us = (cty.get("cost") or {}).get("unmapped_share")
        if us is not None and us >= 0.0005:
            t += "; kisi country se match nahi hua: %s%%" % _num1(100 * us)
        out.append(t)
    elif why == "cov" and gbad:
        cov = " (%s%%)" % _num1(100 * gbad["v"]) if gbad.get("v") is not None else ""
        out.append("⚠️ Google Ads country-wise kharcha %s me poora nahi mila%s — un hafton ka country cost nahi dikhaya"
                   % (_span(gbad["from"], gbad["to"], S), cov))
    elif why == "wait":
        till = gc.get("till")
        out.append("Google Ads country-wise kharcha %s — naye hafton ka country cost uske baad" % (
            "%s tak aaya" % U.fmt_day(till, S) if till else "abhi aa raha"))
    elif why == "nostore":
        out.append("Is app ke Google Ads account ka country-wise data nahi mila — country cost nahi dikhaya")
    out.append("Country: Google Ads me jahan user ad dekhte waqt tha, GA4 me install ke din jahan tha — lagbhag same")
    return out


def _check_text(sc, g12, old, ded, fx_mode, S=None, src_ccy=None):
    """The Data check's sentences (§1.6, §4.2 item 6) — the GA4 ÷ AdMob line from the NEWEST weeks (an AdMob side that
    stopped coming is said plainly, never hidden behind older weeks that matched)."""
    out = []
    ml, G = sc.get("m_last"), sc.get("G") or {}
    gl = max(G) if G else None
    if sc["src"] and gl is not None and S is not None and (ml is None or ml < min(gl, S) - timedelta(days=6)):
        since = (ml + ONE) if ml is not None else min(G)
        out.append("⚠️ AdMob ki kamai %s se nahi aayi — naye hafton ki install-wise kamai purane hafton ke hisaab se "
                   "scale ki (≈)" % U.fmt_day(since, S))
    else:
        ws = [w for w in sc["weeks"][-4:] if w["r"] is not None]
        if ws:
            r = _med([w["r"] for w in ws])
            if 0.9 <= r <= 1.1:
                out.append("✅ GA4 aur AdMob ki kamai mel khati (±10%)")
            else:
                out.append("GA4 me AdMob ki kamai ka %d%% dikhta — install-wise kamai AdMob ke hisaab se scale ki (≈)"
                           % int(round(100 * r)))
        elif sc["st"] == "none" or not sc["src"]:
            out.append("AdMob ki kamai abhi GA4 ke dino se nahi mili — kamai GA4 ke hisaab se (≈)")
        else:
            out.append("GA4 aur AdMob ki tulna ke liye naye hafte abhi poore nahi")
    if sc["double"]:
        out.append("shayad ad revenue do baar log ho raha (Firebase link + app ka apna code) — developer se check karwao")
    if sc["src"] == "network":
        out.append("AdMob ki kamai sirf AdMob network se (mediation ke baaki networks nahi) — isliye thodi kam dikh sakti")
    if g12 and g12.get("rev") is not None:
        out.append("Country me na baanta gaya hissa: kamai ka %s%%, installs ka %s%% (last %d weeks)" % (
            _num1(100 * g12["rev"]), _num1(100 * (g12.get("n") or 0)), g12.get("weeks") or GAP_WEEKS))
    if old is not None:
        out.append("Purane users (14 mahine se pehle install) ki kamai: %s%% — ye install-week me nahi ginte"
                   % _num1(100 * old))
    if not (ded and ded.get("rate")):
        out.append("Kamai deduction se pehle, isliye Marketing ROAS se thoda zyada")
    if fx_mode == "one":
        out.append("Google Ads kharcha: purane hafte aaj ke rate pe (₹→$)")
    elif src_ccy and src_ccy != "USD":
        out.append("Google Ads kharcha: har hafta apne rate pe $ me — isliye $ me Marketing ROAS se thoda alag; ₹ view me "
                   "bilkul utna jitna Google Ads ne liya")
    out.append("GA4 din property ke time me, AdMob / Google Ads India time me — hafte me milaya")
    return out


def _num1(x):
    return ("%.1f" % x).rstrip("0").rstrip(".")


def _row(detail, weeks, pays, alerts, tiles, cty, ida_state, ida_pct, app_id, app, key, H):
    pt = tiles["pay"]
    w7, w30 = _win(weeks, 7), _win(weeks, 30)
    j7 = [w for w in w7 if w["judged"]]
    j30 = [w for w in w30 if w["judged"]]
    rev7, sp7 = (sum(w["R"][_tj(7)] for w in j7), sum(w["spend"] for w in j7)) if j7 else (None, None)
    rev30, sp30 = (sum(w["R"][_tj(30)] for w in j30), sum(w["spend"] for w in j30)) if j30 else (None, None)
    b7 = _g4(100 * rev7 / sp7) if sp7 else None           # the All-apps "Back in": the SAME last-4-weeks window as
    b30 = _g4(100 * rev30 / sp30) if sp30 else None        # the pooled tiles (ratio of sums), never one week
    e7, e30 = any(w["E"][_tj(7)] for w in j7), any(w["E"][_tj(30)] for w in j30)
    if pt.get("v") is not None:
        pay = {"from": pt["from"], "to": pt["to"], "p": pt["v"] if not pt.get("never") else None, "lo": pt.get("lo"),
               "hi": pt.get("hi"), "obs": bool(pt.get("obs")), "never": bool(pt.get("never")),
               "pct365": pt.get("pct365"), "p0": pt.get("base"), "st": pt["st"], "why": None, "rough": bool(pt.get("rough")),
               "shape": pt.get("shape"), "b7": b7, "b30": b30, "b7_est": e7, "b30_est": e30,
               "b7_0": tiles["b7"].get("base")}
    else:
        pay = {"from": pt.get("from"), "to": pt.get("to"), "p": None, "lo": None, "hi": None, "obs": False,
               "never": False, "pct365": None, "p0": None, "st": pt["st"], "why": pt.get("why") or pt["st"],
               "note": pt.get("note"), "b7": b7 if pt["st"] not in ("nospend",) else None,
               "b30": b30 if pt["st"] not in ("nospend",) else None, "b7_est": e7, "b30_est": e30, "b7_0": None}
    sub = tiles["rpi"].get("sub") or {}
    c = tiles["cpi"]
    ac = {"warning": 0, "watch": 0, "good": 0}
    for a in alerts:
        ac[a["severity"]] += 1
    ct = detail["countries"]
    return {"app_id": app_id, "app": app, "key": key, "file": None, "sig": None, "status": "ok",
            "settled_till": detail["settled_till"],
            "iday": {"from": detail["iday"]["from"], "to": detail["iday"]["to"], "cfrom": detail["iday"]["cfrom"],
                     "state": ida_state, "pct": ida_pct},
            "pay": pay, "rpi": {"d1": sub.get("1"), "d7": sub.get("7"), "d30": tiles["rpi"]["v"],
                                "est": bool(tiles["rpi"].get("est"))},
            "cpi": {"v": c.get("v"), "v_src": c.get("v_src"), "ads": c.get("ads"), "paid_share": c.get("paid_share"),
                    "spend4": c.get("spend4"), "spend4_src": c.get("spend4_src"), "n4": c.get("n4"), "nw": c.get("nw"),
                    "from": c.get("from"), "to": c.get("to"), "st": c["st"]},
            "cty": {"best": tiles["cty"]["best"], "weak": tiles["cty"]["weak"], "judged": tiles["cty"]["judged"],
                    "of": tiles["cty"]["of"], "all_avg": tiles["cty"]["all_avg"],
                    "win_weeks": ((ct or {}).get("win") or {}).get("weeks") or 0,
                    "geo": bool((ct or {}).get("geo")) and (ct or {}).get("geo_why", "ok") == "ok",
                    "smp": bool((ct or {}).get("smp")),
                    "clean": bool(((ct or {}).get("app") or {}).get("clean", True))},
            "alerts": ac, "summary": detail["summary"], "src_ccy": (detail.get("fx") or {}).get("src"),
            # the portfolio's pooling sums — ratios of sums over the last 4 settled CALENDAR weeks (the cost tile's and
            # the "Ads spend (4 wks)" column's window: spend4 is ALL spend in it, known zeros included; the Back-in sums
            # its judged weeks); null — never 0 — when unknown (no spend data, earnings not complete yet)
            "s": {"spend4": c.get("spend4"), "spend4_src": c.get("spend4_src"), "n4": c.get("n4"), "nw": c.get("nw"),
                  "rev7_4": _m6(rev7), "spend7_4": _m6(sp7), "n7_4": sum(w["n"] for w in j7) if j7 else None,
                  "rev30_4": _m6(rev30), "n30_4": sum(w["n"] for w in j30) if j30 else None, "spend30_4": _m6(sp30)}}


def _wait_detail(store, ida, app_id, app, key, H, hs):
    return None


def _wait_row(app_id, app, key, ida, hs):
    """An app whose install-day data has not arrived yet: listed, "⏳ data aa raha"."""
    return {"app_id": app_id, "app": app, "key": key, "file": None, "sig": None, "status": "wait",
            "settled_till": None, "iday": {"from": None, "to": None, "cfrom": None, "state": "wait", "pct": 0},
            "pay": None, "rpi": None, "cpi": None, "cty": None, "alerts": {"warning": 0, "watch": 0, "good": 0},
            "summary": {"kind": "wait", "text": "⏳ Install-wise kamai ka data aa raha — agle fetch me."},
            "s": {"spend4": None, "spend4_src": None, "n4": None, "nw": None, "rev7_4": None, "spend7_4": None,
                  "n7_4": None, "rev30_4": None, "n30_4": None, "spend30_4": None}}


# ── the All-apps lists in dashboard.json (SPEC_SIMPLIFY D10: they never depend on which per-app files were opened) ──

INFO_PER_APP = act.INFO_PER_APP              # dashboard["value"]["info"]: ≤ 5 rows per app, newest first, none that
INFO_MAX_DAYS = act.INFO_MAX_DAYS            # ended > 90 days before the app's settled day
CLOSED_RECENT_DAYS = act.CLOSED_RECENT_DAYS  # dashboard["value"]["closed"]: closed ≤ 7 days before the settled day


def compact_info(detail, keep=INFO_PER_APP, max_days=INFO_MAX_DAYS):
    """A value detail's info (+ older, always empty here) rows → the compact rows dashboard["value"]["info"] lists:
    {app_id, src, kind, from, to, text, cc (when the row has one), release (when it has one), started} — at most `keep`
    per app, newest first (by to, else from; an undated row — the AdMob scale note — counts as current), none that
    ended more than max_days before the app's settled day. Shown only."""
    S = detail.get("settled_till")
    ch = detail.get("changes") or {}
    rows = []
    for si, src in enumerate(("info", "older")):
        for j, r in enumerate(ch.get(src) or []):
            day = r.get("to") or r.get("from")
            age = act._age_days(S, day) if day else 0
            if age is not None and age > max_days:
                continue
            row = {"app_id": detail.get("app_id"), "src": src, "kind": r.get("kind"), "from": r.get("from"),
                   "to": r.get("to"), "text": r.get("text"), "started": r.get("started", r.get("since") or r.get("from"))}
            if "cc" in r:
                row["cc"] = r["cc"]
            if "release" in r:
                row["release"] = dict(r["release"]) if isinstance(r["release"], dict) else r["release"]
            rows.append((age or 0, si, j, row))
    rows.sort(key=lambda x: x[:3])
    return [x[3] for x in rows[:keep]]


def recent_closed(closed, S, days=CLOSED_RECENT_DAYS):
    """The closed value alerts (alert objects) closed ≤ `days` before the settled day S. Shown only."""
    out = []
    for a in closed or []:
        age = act._age_days(S, a.get("closed"))
        if age is not None and 0 <= age <= days:
            out.append(a)
    return out


def portfolio_shape(shapes):
    """Every app's own curve g per (t_o → t) (apps with ≥ REF_MIN reference weeks: [median, q20, q80]) → the
    portfolio's, where ≥ PORTF_MIN_APPS apps have it: the median of the apps' medians, and a band as wide as the apps
    differ from EACH OTHER — from the lowest app q20 to the highest app q80 (a young app's curve may be any of theirs;
    one app's own week-to-week noise would be a falsely narrow range). A projection from it is always "kaafi kaccha"
    and never opens or sends a money-back alert."""
    acc = {}
    for s in shapes:
        for k, v in (s or {}).items():
            acc.setdefault(k, []).append(v)
    return {k: [_g4(_med([x[0] for x in v])), _g4(min(min(x[1], x[0]) for x in v)), _g4(max(max(x[2], x[0]) for x in v))]
            for k, v in sorted(acc.items()) if len(v) >= PORTF_MIN_APPS}
