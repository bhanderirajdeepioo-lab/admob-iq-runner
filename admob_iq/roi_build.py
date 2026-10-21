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
       day: [day, exact?] or null), st (status: Worse / Watch / Better / Normal / Too early / N/A), q (≈: bit 1 = a day
       of it did not tie to the install-day read, or its D0 … D30 read kept revenue in GA4's "(other)" / was flagged
       with nothing to measure it by — fetch.ga4_cohort "lo" / "lf" —, bit 2 = a day its m used still carries revenue
       GA4 gave no install day: ages ≤ 420 on a week not read whole yet, past 420 on a week with loss there),
       spi (spend as billed), and — only on a row that has them — m (cumulative revenue at day 60, 90, 120 … every
       30 days up to the install day's age: the cohort cube, see below), mf (how many of m are final)]
       (q bit 4 = a day its m used GA4 flagged with nothing to measure it by: thresholding / sampling / a cut read)
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
  * late — only when the app's cube is used: {"days" of it (folded + hot), "oth" days with revenue GA4 left
    "(other)" / gave no install day even after the country split (the cube's loss), "omax" the largest such share of a
    day's revenue (6 decimals, measured), "loss" days GA4 flagged with nothing to measure it by, "from", "till", "thru"
    the last day with every activity day from the history start read (a stalled walk: the page says the newest columns
    wait for it); only once q files exist (fetch.ga4_cube q, below): "ql" USD × k GA4 gave no install day past age 420
    on the weeks read whole (exact, no install day: never spread), "qd" days on q, "qwait" days with loss still on the
    cube's cells (q not read yet / "fl"), "qneg" / "qpos" weeks whose whole read held more / less than the cube
    (beyond the cube's own measured loss): read-time drift, counted, never loss} (the page's ≈ note); while the cube's first walk is still on its way: {"busy": 1, "from",
    "next", "at" the walk's last step (UTC day; absent before its first)} only (no column yet, the page says so and
    since when).
Past day 30 (owner, 20 Oct 2026: "jitna purana app utna date"): fetch.ga4_cube (GA4_CUBE) keeps every install day's GA4
ad revenue by activity day × country from the history start (with countryId GA4 answers every install day; the
[date, firstSessionDate] shape stops at about 15 months). Per install day X its 30-day buckets B[j] (ages 30j+1 …
30j+30, j ≥ 1) = Σ over the activity months (+ the hot days) of the cube's "b"[X][j][W] micros × kf(W) — the SAME
weekly AdMob ÷ GA4 scale k as the D0 … D30 cells — and m = [base + B[1], base + B[1] + B[2], …] with base = d[30]
when final through 30, else the D30 checkpoint (as t's D60+); m[j] only while EVERY activity day of buckets 1 … j is
folded or hot (a hole stops it), final while every one is folded. WHOLE past D30 (21 Oct 2026, owner: real data only —
GA4 folds the country "(other)" before any filter, so the cube's own cells lose it): fetch.ga4_cube's q is a whole
no-country read of each activity day (ages to 427); a week inside an activity month is "on q" only when every day of it
has a q with qs "ok" (and q holds no other day of it) — there buckets j ≤ QJ (13: ages ≤ 420) come from q, j > 13 from
"b"; a hot day uses its q (read in the same run) when it has one; else everything from "b" (no q file: every byte as
before). The loss still left on a week on q is ql = Σ t − Σ qt − Σ b[j > 13] (exact, no install day: said as its size;
never more than the cube's own measured loss of the week — past it, drift).
q bit 4 from the cube's ledger (flagged); bit 2 only on a day whose loss the row still carries (_late's q_bits with the
row's m length). Breakeven and so far also look through m (breakeven by age: the exact days, the checkpoints
through D30 they do not cover, m, the checkpoints past m). Only with the switch on (GA4_CUBE:
start(cube=True)), the cube of the app's stream, and once its walk reached the final edge the first time (done: the
columns come in one go, never a half-read store's few; until then only the "late" busy note); with the switch off,
without a cube or with another stream's, every byte of the file is as before.
🌍 The install-day table by COUNTRY (owner, 20 Oct 2026: "manlo me USA select kru to date wise country ka aa jayega konsa
din kaha pahocha"): the same rows for ONE country, from the same cube pass (_late's visit: no extra read of the month
files) — only with the switch on, the app's cube walked through (done) and any country in it; otherwise not a byte of
the file changes. Per country (every one GA4 names, "--" = GA4's "(not set)" = "Unknown country", nothing pooled or cut):
  * n = Σ the cube's "e" u0 (that country's installs, ads + organic); d / df / m / mf / s / sd / be through _cohorts
    itself (the same code as the All row): d[L] = Σ "e" r_L × k_c(cc, month of the activity day), m from "c" buckets
    × k_c the same way as _late's "b"; completeness / finality = _late's own (every day read / folded; d stops at the
    last day every activity day from the history start was read, df at the last one folded); t at D0 … D30 from d,
    D60 / D90 / D180 from m once final; st by _statuses on the country's own rows (≥ $5 Ads and ≥ 30 installs, else N/A);
    q bits: 2 / 4 = a day of the row the cube measured loss on / GA4 flagged (the country cells are the cube's own: no
    q), 8 = a k_c outside 0.8 – 1.25, 16 = a month on the app's k, 64 = a month whose GA4 revenue without a country is
    > UNP_LIM of it (see k_c) — on a row with installs, revenue, Ads spend or Ads downloads (a row with none of them:
    no bit, nothing of it to be off). (32, a borrowed k_c, is gone with the borrowing.)
  * k_c (each country's AdMob ÷ GA4 per ACTIVITY month, like engine.value.scale): AdMob = the country report (every ad
    source) of the app's AdMob ids × (1 − deduction); GA4 = Σ that month's "e" r + "c" of the country (every install
    age); a month is measured on its own only when both sides cover it whole (every day folded / every day with an
    AdMob row, a one-day hole between rows read as a real 0) and both ≥ K_MIN_USD ("own"); a whole month below that is
    pooled with the whole months ≤ ±KC_POOL around it ("pool"); clamped to K_CLAMP; raw outside K_OK → ≈; none — a
    thin month, or a month not whole on both sides (the current one, the history start's, a hole, every month before
    the AdMob country report starts): never another month's k_c borrowed (owner: real data only — a borrowed one
    carries other months' loss) → the app's own k of that month (its weekly kf weighted by GA4 revenue), "app k", ≈.
    "--" always on the app's k. GA4's revenue without a country — "(not set)" ("--") and the cube's measured "(other)"
    loss — is in no country's GA4 side, while AdMob's country report counts those users under a real country: each
    month's share of it (u, of the ledger's t) is measured and written ("kc" "unp"); a month above UNP_LIM marks its
    cells ≈ (bit 64), and the "--" row's revenue is ALSO inside the named countries' k_c (never added to them: "diff"
    says how much). Σ countries ≠ the All row exactly (All: the weekly k and another GA4 read; that u; the "--" row)
    — "diff" says by how much (D30, measured).
  * GA4: country not given ("ng"), per ACTIVITY month: All − Σ countries at the cells' source = the app's k × GA4's
    every row of the month (the ledger's t, "(other)" included) − Σ every country (k_c × its GA4 cells, "--" on the
    app's k), USD, signed — "own" when most of the month's named GA4 revenue is on an own / pooled k_c (AdMob's country
    report already placed it in the countries: ≈ 0 left), else "app" (GA4 × the app's k: that part is in no country
    row). Measured, never spread to a country.
  * spend = Google Ads by country × day (fetch.gads_geo_day, read per app: only its own stores) of the app's own spend
    store ids (value_build.app_sids), USD at that day's rate (the same FX series); a day is known only when every one
    of those stores either did not spend (spend cache) or has a committed geo day whose Σ over countries (+ "XX") ties
    to the spend cache's cost within GEO_TIE_REL / GEO_TIE_ABS — else unknown (null: '—', never a weekly cell spread
    over days; "untied_days" counts the ones with a split that did not tie). Ads "XX" (unmapped) → "Not split" (its
    spend per install day; revenue none). The Ads day is the Ads ACCOUNT's day (its time zone, from the hourly store's
    accounts of the app's stores): "geo" "tzh" = hours GA4's day starts before it (null: unknown / zones mixed).
  * rows: EVERY install day from the history start to the last day read through; a day with no installs, no revenue
    and nothing else of its own is written [X] (the page makes the same row of it: _zrow).
Files: roi_<key>_c<NN>.json.gz = {"v", "b", "key", "ix", "c": {cc: rows}} (countries by installs, then spend, then
code; filled in turn up to PACK_MAX raw bytes; a bigger country alone) and in roi_<key>.json.gz "cd" = {"v", "b" (the
build of the packs: sha1-12 of every country's rows — each pack carries the same "b", so the page knows a pack of
another build from the one its index names: a pack file is served as its newest copy whatever ?v= says), "packs":
[[file, sha1-12 of its JSON]], "c": [[cc, installs, spend USD, spend as billed, pack, N/A days, revenue share on the
app's k]], "from", "to", "thru", "fthru", "newest", "kc": {own / pool / app / est months, "tzh" hours AdMob's day is
off GA4's, "unp" {month: GA4 revenue share without a country}, "unp_all" (all
months), "unp_lim"}, "geo": {"from", "till", "known_days", "unknown_days", "untied_days", "unk" ranges, "xx_share",
"cov", "billed", "tzh", "tzs" (Ads time zones of the app's stores)}, "loss": {"days", "max_share", "flag_days",
"usd"}, "diff" (+ "unk": the "--" row's part of "cty"), "ng": {"m": {month: [USD, its "unp", "own" | "app"]}, "usd"
(Σ), "all" (Σ All), "rel"}}. Any failure of it: no "cd", every other byte as without it
(counted; the Ads split's read failing: every day unknown, counted too).
roi.json.gz — every app's summary row (with its f4), the portfolio lifetime P/L and the portfolio install days (apps
with spend), and the ranges the forms used (f4c).
Pointer: dashboard["roi"] = {"file", "v", "apps": {app_id: {"file", "st", "r7", "u7", "pb", "lp"}}}.
⚙️ Ad setting changes (adcfg_build, before the forecast: build_static's adcfg.Source = the unit + country reports it
already read; ids = the AdMob apps on the app's Play package): the app's events kept in data/adcfg/<key>.json, the
material ones handed to the forecast (its back-tests label them; forecast_vd.AX decides whether they count, held off),
and the page block in the forecast's file as fc["acfg"] (the forecast's "why": "Ad setting badlav") — every other field
of the file exactly as without it.
One splat header rule (/roi*: the country packs too). Failure-isolated per app (counted) and as a whole; ONE
counts-only line.
"""
import gzip
import hashlib
import json
import os
import re
import sys
from array import array
from datetime import date, datetime, timedelta, timezone

from . import stage_clock as _sc
from .db import write_gz_stable, write_json_gz_stable
from .engine import value as val
from .fetch import ga4_cohort as gco
from .fetch import ga4_cube as gcu
from .fetch import ga4_uninstall as gu

ALL_FILE = "roi.json.gz"
PREFIX = "roi_"
FILE_RE = re.compile(r"^roi_[0-9a-f]{12}\.json\.gz$")
PACK_RE = re.compile(r"^roi_[0-9a-f]{12}_c\d{2,3}\.json\.gz$")     # 🌍 the country packs (the page checks the same)
HEADER_PATHS = ["/roi*"]
CD_V = 1
PACK_MAX = 1_500_000                        # raw JSON bytes a country pack (a bigger country gets one of its own)
KC_POOL = 2                                 # a thin / partly covered month: pooled with the whole months ≤ ±2 around it
UNP_LIM = 0.02                              # a month whose GA4 revenue without a country ("(not set)" + "(other)") is
                                            # > 2% of it: its k_c carries that share (AdMob places those users) → ≈
GEO_TIE_REL, GEO_TIE_ABS = 0.01, 1_000_000  # a store-day's country split ties to the spend cache: within 1% or 1 unit
NO_CC, NOT_SPLIT = "--", "XX"               # GA4's "(not set)"; Google Ads' unmapped ("Not split")
V = 1
T = val.T                                   # 0, 1, 3, 7, 14, 30, 60, 90, 180, 365
J7 = T.index(7)
J30 = T.index(30)
LATE_STEP = 30                              # past D30 the install-day table goes on every 30 days (D60, D90 …)
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
        self.cal = None                             # 📅 its eCPM calendar (fc_calendar.seasons), if the build made one
        self.beta = None                            # ⚖️ per-app beta ranges (config/roi_beta.json), read on the first app
        self.f4m = 0                                # ⚖️ apps whose forms use GA4's measured paid share + premium
        self.adsrc = None                           # ⚙️ the AdMob reports for the ad setting changes (adcfg.Source)
        self.ac = None                              # … their run (adcfg_build), made on the first app
        self.cube = False                           # 🧊 GA4_CUBE: the 30-day columns past D30 (fetch.ga4_cube)
        self.cmon = None                            # 🌍 AdMob by country × month (build_static.admob_country_months)
        self.adtz = None                            # … Google Ads store → its accounts' time zones (read once)
        self.packs = set()                          # … the country packs written this build (kept by _clean)
        self.cdn = {"apps": 0, "countries": 0, "packs": 0, "failed": 0, "geo_failed": 0}


def start(cal=None, adsrc=None, cube=False, cmon=None):
    """cal: the forecast's eCPM calendar (fc_calendar.seasons, from build_static), handed to the forecast's run;
    adsrc: the ⚙️ ad setting changes' reports (engine.adcfg.Source, from build_static); cube: GA4_CUBE (off: the cube
    is never read, the file as without it); cmon: AdMob by country × month (the country filter's AdMob ÷ GA4 match)."""
    acc = Acc()
    acc.cal = cal
    acc.adsrc = adsrc
    acc.cube = bool(cube)
    acc.cmon = cmon if isinstance(cmon, dict) else None
    return acc


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


def _late(data_dir, aid, sid, P, visit=None):
    """The app's cohort cube (fetch.ga4_cube, GA4_CUBE) folded month by month (one month in memory at a time, with its q
    file) + its hot days → {"B": {X: {j: USD}} the 30-day buckets (AdMob-matched with kf of each activity week; j ≤ QJ
    from q on a week read whole), "full" (lo, hi): every activity day lo … hi folded or hot, "fin" (lo, hi): every one
    folded, "q" (lo, hi, jmax=None): q bits of them (2: revenue GA4 left "(other)" / gave no install day — with jmax,
    only what the row still carries; 4: GA4 flagged with nothing to measure it by), "info" (the file's "late")}
    — None without a cube of the stream `sid` or with no day; before its walk first reached the final edge (done) only
    {"info": {"busy": 1, "from", "next", "at"}} (the page says the columns are on their way, none shown).
    visit("m", YYYY-MM, month file) / visit("h", D, hot record): the 🌍 country filter's read riding this one pass over
    the files (each month and each hot day this uses, as it uses them); a visit that raises is dropped — never these
    columns."""
    def seen(*args):
        nonlocal visit
        if visit is not None:
            try:
                visit(*args)
            except Exception:
                try:                                # its reader knows it missed a part (never half a country)
                    visit.__self__.failed = True
                except Exception:
                    pass
                visit = None
    h = gcu.load_head(data_dir, aid)
    if not h or str(h.get("stream_id") or "") != str(sid or ""):
        return None
    if not h.get("done"):
        info = {"busy": 1, "from": h.get("from"), "next": h.get("next")}
        if h.get("walk_at"):
            info["at"] = str(h["walk_at"])[:10]     # the walk's last step (UTC day): a stalled walk shows its age
        return {"info": info}
    kf, hs = P["sc"]["kf"], P["hs"]
    B, fin, hot, oth, flg, omax, ks = {}, set(), set(), set(), set(), 0.0, {}
    lb, zq = set(), set()       # q: days whose loss is still in the cube's cells / loss past age QL on a whole week
    qi = {"ql": 0.0, "qd": 0, "qwait": 0, "qneg": 0, "qpos": 0, "on": False}

    def k_of(W):
        if W not in ks:
            ks[W] = kf(_d(W))[0]
        return ks[W]

    def add(b, onq=()):
        """The cube's cells, but a bucket j ≤ QJ of a week read whole (onq: q's cells instead)."""
        for X, js in (b or {}).items():
            e = B.setdefault(X, {})
            for j, ws in (js or {}).items():
                jj = int(j)
                e[jj] = e.get(jj, 0.0) + sum(v / 1e6 * k_of(W) for W, v in (ws or {}).items()
                                             if not (jj <= gcu.QJ and W in onq))

    def add_q(q, onq):
        for X, js in (q or {}).items():
            for j, ws in (js or {}).items():
                jj = int(j)
                s = sum(v / 1e6 * k_of(W) for W, v in (ws or {}).items() if W in onq) if jj <= gcu.QJ else 0.0
                if s:
                    e = B.setdefault(X, {})
                    e[jj] = e.get(jj, 0.0) + s

    def past(b):
        """{W: micros of the cube's buckets past QJ} (ages 421 + — never on q)."""
        out = {}
        for js in (b or {}).values():
            for j, ws in (js or {}).items():
                if int(j) > gcu.QJ:
                    for W, v in (ws or {}).items():
                        out[W] = out.get(W, 0) + int(v or 0)
        return out

    def gap(W, t, rows, qt, qr, b14, lo, ds, hot=False):
        """ql of a week read whole: Σ t − Σ qt − Σ b (j > QJ) = the loss with no install day past age QL (exact),
        beyond rounding (½ micro a row + 1 ppm) — never more than the cube's own measured loss of those days (lo): what
        is past it is read-time drift the other way (the cube's read held more: "qpos"); below 0: drift ("qneg").
        Drift is counted, never loss (a hot day: not counted — GA4 still adds to it between its two reads)."""
        g, tol = t - qt - b14, (rows + qr) // 2 + 1 + t // 1_000_000
        if g > tol:
            lq = min(g, lo)
            if lq > tol:
                qi["ql"] += lq / 1e6 * k_of(W)
                zq.update(ds)
            if g - lo > tol and not hot:
                qi["qpos"] += 1
        elif g < -tol and not hot:
            qi["qneg"] += 1

    def note(Dd, led, onq=False):
        nonlocal omax
        lo, t = int(led.get("loss") or 0), int(led.get("t") or 0)
        if lo > 0:
            oth.add(Dd)
            omax = max(omax, min(1.0, lo / t) if t > 0 else 1.0)
            if not onq:
                lb.add(Dd)
                qi["qwait"] += Dd >= hs
        if onq:
            qi["qd"] += Dd >= hs
        if led.get("fl"):
            flg.add(Dd)
    for mk, mo in gcu.months(data_dir, aid, sid):
        qm = gcu.load_q(data_dir, aid, sid, mk)     # q: the month's whole reads (a week on q only when every day is)
        onq, by = set(), {}
        if qm is not None:
            qi["on"] = True
            qd, qw = qm["days"], {}
            for D in mo["days"]:
                by.setdefault(_iso(gcu._mon(_d(D))), []).append(D)
            for D in qd:
                qw.setdefault(_iso(gcu._mon(_d(D))), set()).add(D)
            for W, ds in by.items():
                if qw.get(W) == set(ds) and all(isinstance(qd[D], dict) and qd[D].get("qs") == "ok" for D in ds):
                    onq.add(W)
            b14 = past(mo["b"]) if onq else {}
            for W in sorted(onq):
                ds, leds = by[W], [mo["days"][D] if isinstance(mo["days"][D], dict) else {} for D in by[W]]
                gap(W, sum(int(v.get("t") or 0) for v in leds), sum(int(v.get("rows") or 0) for v in leds),
                    sum(int(qd[D].get("qt") or 0) for D in ds), sum(int(qd[D].get("qr") or 0) for D in ds),
                    b14.get(W, 0), sum(int(v.get("loss") or 0) for v in leds), {_d(D) for D in ds})
        for D, led in mo["days"].items():
            Dd = _d(D)
            fin.add(Dd)
            note(Dd, led if isinstance(led, dict) else {}, _iso(gcu._mon(Dd)) in onq)
        add(mo["b"], onq)
        if onq:
            add_q(qm["q"], onq)
        seen("m", mk, mo)
    for D, rec in (h.get("d") or {}).items():
        Dd = _d(D)
        if Dd in fin or not isinstance(rec, dict):
            continue
        hot.add(Dd)
        qi["on"] = qi["on"] or "qs" in rec
        onq = {_iso(gcu._mon(Dd))} if rec.get("qs") == "ok" and isinstance(rec.get("q"), dict) else set()
        if onq:                                     # a hot day's q (read in the same run as its cube cells)
            W = next(iter(onq))
            gap(W, int(rec.get("t") or 0), int(rec.get("rows") or 0), int(rec.get("qt") or 0),
                int(rec.get("qr") or 0), past(rec.get("b")).get(W, 0), int(rec.get("loss") or 0), {Dd}, True)
        note(Dd, rec, bool(onq))
        add(rec.get("b"), onq)
        if onq:
            add_q(rec["q"], onq)
        seen("h", D, rec)
    have = {D for D in fin | hot if D >= hs}
    if not have:
        return None
    last = max(have)
    n = (last - hs).days + 1
    thru = hs - timedelta(days=1)                   # every activity day hs … thru read (folded or hot): the page says
    while thru + timedelta(days=1) in have:         # how far, when a stalled walk stops the newest columns there
        thru += timedelta(days=1)
    pr, pf, po, pl = [0] * (n + 1), [0] * (n + 1), [0] * (n + 1), [0] * (n + 1)
    pb, pz = [0] * (n + 1), [0] * (n + 1)
    for i in range(n):
        D = hs + timedelta(days=i)
        pr[i + 1] = pr[i] + (D in have)
        pf[i + 1] = pf[i] + (D in fin)
        po[i + 1] = po[i] + (D in oth)
        pl[i + 1] = pl[i] + (D in flg)
        pb[i + 1] = pb[i] + (D in lb)
        pz[i + 1] = pz[i] + (D in lb or D in zq)

    def span(lo, hi):
        i0, i1 = (lo - hs).days, (hi - hs).days
        return (i0, i1) if 0 <= i0 <= i1 < n else None

    def full(lo, hi):
        s_ = span(lo, hi)
        return bool(s_) and pr[s_[1] + 1] - pr[s_[0]] == s_[1] - s_[0] + 1

    def final(lo, hi):
        s_ = span(lo, hi)
        return bool(s_) and pf[s_[1] + 1] - pf[s_[0]] == s_[1] - s_[0] + 1

    def q_bits(lo, hi, jmax=None):
        """The ≈ bits of the activity days lo … hi: 4 = a day GA4 flagged; 2 = a day with measured loss (jmax None:
        the cube's cells — the 🌍 country rows); with jmax (an All row's m: install day X = hi − 30 (jmax + 1)) only a
        day whose loss the row still carries: ages ≤ QL on a week still on the cube's cells, past QL on any week with
        loss there (on the cube's cells, or ql > 0 on a week read whole)."""
        s_ = span(lo, hi)
        if not s_:
            return 0
        i0, i1 = s_
        bits = 4 if pl[i1 + 1] - pl[i0] > 0 else 0
        if jmax is None:
            return bits | (2 if po[i1 + 1] - po[i0] > 0 else 0)
        ic = min(i1, (hi - timedelta(days=LATE_STEP * (jmax + 1) - gcu.QL) - hs).days)   # X + QL: q's last age
        if (ic >= i0 and pb[ic + 1] - pb[i0] > 0) or (ic < i1 and pz[i1 + 1] - pz[max(i0, ic + 1)] > 0):
            bits |= 2
        return bits
    info = {"days": len(have), "oth": len({D for D in oth if D >= hs}), "omax": _r(omax, 6),
            "loss": len({D for D in flg if D >= hs}), "from": _iso(min(have)), "till": _iso(last),
            "thru": _iso(thru) if thru >= hs else None}
    if qi["on"]:                                    # only with q files (without them: the file as before, byte by byte)
        info.update(ql=_r(qi["ql"], 2), qd=qi["qd"], qwait=qi["qwait"], qneg=qi["qneg"], qpos=qi["qpos"])
    return {"B": B, "full": full, "fin": final, "q": q_bits, "info": info}


def _cohorts(P, spend, fxf, co, today, late=None, edge=None):
    """Every install day → its row (see the module doc) — oldest first. late: _late's buckets (None: no m). edge: the
    last day every exact cell is final through (None: read_today − FINAL_LAG — the exact store's own rule; the 🌍
    country rows: the cube's last day folded through, read_today being the last day read through)."""
    pr, kf, xs, S, hs = P["pre"], P["sc"]["kf"], P["xs"], P["S"], P["hs"]
    co_x = (co or {}).get("x") or {}
    newest = _d(co["read_today"]) if co and co.get("read_today") else None
    C = newest - timedelta(days=gco.FINAL_LAG) if newest else None
    if edge is not None:
        C = edge
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
        # past day 30, every 30 days (the cohort cube): from the row's own D30 on, while every activity day is there
        m, mf, qo = None, 0, 0
        if late is not None:
            base = d[30] if (d is not None and df > 30) else (e["R"][J30] if t[J30] is not None else None)
            if base is not None:
                B, vals, cum, j = late["B"].get(_iso(X)) or {}, [], base, 1
                while late["full"](X + timedelta(days=LATE_STEP * j + 1), X + timedelta(days=LATE_STEP * (j + 1))):
                    cum += B.get(j, 0.0)
                    vals.append(_r(cum))
                    j += 1
                if vals:
                    m = vals
                    while mf < len(m) and late["fin"](X + timedelta(days=gco.LAGS),
                                                      X + timedelta(days=LATE_STEP * (mf + 2))):
                        mf += 1
                    qo = late["q"](X + timedelta(days=gco.LAGS), X + timedelta(days=LATE_STEP * (len(m) + 1)),
                                   len(m))
        # so far: the read that reaches furthest (the install-day read through S, this store through `newest`)
        s = sd = None
        if e and X <= S:
            base = d[30] if (d is not None and df > 30) else None
            s = _r(base + e["R"][9] - e["R"][5]) if base is not None else _r(e["R"][9])
            sd = _iso(S)
        if d is not None and (sd is None or X + timedelta(days=len(d) - 1) > _d(sd)):
            s, sd = d[-1], _iso(X + timedelta(days=len(d) - 1))
        if m:                                       # … or m's last column (the install-day read stops at day 365)
            mA = X + timedelta(days=LATE_STEP * (len(m) + 1))
            if sd is None or mA > min(_d(sd), X + timedelta(days=T[-1])):
                s, sd = m[-1], _iso(mA)
        be = None
        if sp and sp > 0:                           # by age: the exact days, the checkpoints through D30 they do not
            for L, v in enumerate(d or []):         # cover, the 30-day columns, the checkpoints past them
                if v is not None and v >= sp:
                    be = [L, L < df]
                    break
            lim = max(LATE_STEP * (len(m) + 1) if m else -1, LATE_STEP)
            ts = [a for j, a in enumerate(T) if t[j] is not None and t[j] >= sp and not (d is not None and a < len(d))]
            if be is None and ts and ts[0] <= LATE_STEP:
                be = [ts[0], False]
            if be is None and m:                    # the first 30-day column ≥ spend: "≤ that day"
                for i, v in enumerate(m):
                    if v is not None and v >= sp:
                        be = [LATE_STEP * (i + 2), False]
                        break
            if be is None:
                ts = [a for a in ts if a > lim]
                be = [ts[0], False] if ts else None
        iu = {L: int(e["u"][i]) for L, i in ULAG_IX.items()
              if e and pr.all(pr.g, X, X + timedelta(days=L))} if e else {}
        row = {"X": X, "n": n, "na": n_ads, "sp": sp, "spi": spi, "d": d, "df": df, "u": u, "t": t, "s": s,
               "sd": sd, "be": be, "e": e, "iu": iu}
        if m:
            row.update(m=m, mf=mf, qo=qo)
        rows.append(row)
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
    when the app has no paid cells yet. Ages 180 / 365 (the legacy cells stop at 90): every install's revenue adds
    IDAY_EXT's late cells (c2: ages 91–180, 181–365), whose days must be folded too (c2st); off a band edge: no p."""
    cp, d2 = ida.get("cp") or {}, ida.get("d2") or {}
    if not isinstance(cp, dict) or not isinstance(d2, dict) or not d2:
        return None
    c, days, c2 = ida.get("c") or {}, ida.get("days") or {}, ida.get("c2") or {}
    fold = ("ok", "smp", "gap")                     # ga4_iday_ext.FOLDED / engine.value.CGOOD

    def whole(D, i=0, lt=False):                    # i: the day from the week's start; lt: the late cells are used
        k = _iso(D)                                 # (their days — ages ≥ 91 — need c2st, the legacy ones cst)
        e = d2.get(k) or {}
        return (e.get("cpst") in fold and (i > 96 or (days.get(k) or {}).get("cst") in fold)
                and (not lt or i < 91 or e.get("c2st") in fold))
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

    def late(slots, k):                             # Σ c2 r2 of the first k late bands (the gap row left out)
        return sum(int(x or 0) for kk, v in (slots or {}).items() if kk != "gap" and isinstance(v, dict)
                   for x in (v.get("r2") or [])[:k])
    prem = {}
    for a in ages:
        nb = [i + 1 for i, (lo, hi) in enumerate(val.CBANDS) if hi == a]
        nl = {180: 1, 365: 2}.get(a, 0)            # late bands of every install's revenue (c2), cp: bands to a
        if not nb and not nl:
            continue
        nbp = nb[0] if nb else len(val.CBANDS) + nl
        weeks = []
        for W in sorted(set(cp) & set(c), reverse=True):
            try:
                w0 = _d(W)
            except ValueError:
                continue
            if all(whole(w0 + timedelta(days=i), i, nl > 0) for i in range(7 + a)):
                weeks.append(W)
                if len(weeks) >= F4_PW:
                    break
        if not weeks:
            continue
        np_ = na_ = rp = ra = 0
        for W in weeks:
            n1, r1 = tot(cp[W], nbp)
            n2, r2 = tot(c[W], nb[0] if nb else len(val.CBANDS))
            r2 += late(c2.get(W), nl) if nl else 0
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
    out = [_iso(r["X"]), r["n"], _r(r["na"], 2), _r(r["sp"]), r["d"], r["df"], r["u"], r["t"], r["s"], r["sd"],
           r["be"], r.get("st"), (1 if r.get("q") else 0) | (r.get("qo") or 0), _r(r.get("spi"), 2)]
    if r.get("m"):                                  # the 30-day columns past D30: new trailing fields only
        out += [r["m"], r["mf"]]
    return out


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


# ── 🌍 the install-day table by country (the cohort cube's "e" / "c", each country's own AdMob match) ───────────────
ONE = timedelta(days=1)


class _Cty:
    """The country filter's read of the cohort cube, riding _late's one pass (its visit): per country the raw GA4
    micros of every install day X ≥ hs by age 0 … 30 ("e" r of every activity month added up — an age is in exactly
    one), its installs (u0), its 30-day buckets by (j, activity month) ("c": a month's k_c is known only once every
    month is read), the GA4 total per activity month (each country's AdMob ÷ GA4 match: every install day, every age),
    the folded days of each month and the measured loss (GA4 "(other)") per month. Never raises: a part it could not
    read → failed (the country filter stays off for the app, counted)."""

    def __init__(self, hs, clock=None):
        self.hs = _iso(hs)
        self.E, self.N, self.C, self.G = {}, {}, {}, {}
        self.mdays, self.loss, self.tot = {}, {}, {}  # folded days / measured loss / every row (ledger "t") a month
        self.mi, self.ms = {}, []                   # activity month ↔ its number in C's keys
        self.failed = False
        self.clock, self.sec = clock, 0.0           # the time its reads took (the forecast's budget never pays it)

    def visit(self, kind, k, rec):
        if self.failed:
            return
        t0 = self.clock() if self.clock else None
        try:
            M = str(k)[:7]
            if kind == "m":
                days = {D: v for D, v in (rec.get("days") or {}).items() if isinstance(v, dict)}
                self.mdays[M] = len(days)
                lo = sum(int(v.get("loss") or 0) for D, v in days.items() if D >= self.hs)
                tt = sum(int(v.get("t") or 0) for D, v in days.items() if D >= self.hs)
            else:
                lo = int(rec.get("loss") or 0) if str(k) >= self.hs else 0
                tt = int(rec.get("t") or 0) if str(k) >= self.hs else 0
            if lo:
                self.loss[M] = self.loss.get(M, 0) + lo
            if tt:
                self.tot[M] = self.tot.get(M, 0) + tt
            self._e(M, rec.get("e") or {})
            self._c(M, rec.get("c") or {})
        except Exception:
            self.failed = True
            self.E = self.N = self.C = self.G = None
        finally:
            if t0 is not None:
                self.sec += max(0.0, self.clock() - t0)

    def _g(self, cc, M, g):
        if g:
            gm = self.G.setdefault(cc, {})
            gm[M] = gm.get(M, 0) + g

    def _e(self, M, e):
        hs = self.hs
        for cc, xs in e.items():
            g = 0
            Ec, Nc = self.E.setdefault(cc, {}), self.N.setdefault(cc, {})
            for X, arr in (xs or {}).items():
                if not arr:
                    continue
                r = [int(v or 0) for v in arr[1:]]
                g += sum(r)
                if X < hs:
                    continue
                if arr[0]:
                    Nc[X] = Nc.get(X, 0) + int(arr[0])
                cur = Ec.get(X)
                if cur is None:
                    Ec[X] = array("q", r)
                    continue
                if len(cur) < len(r):
                    cur.extend([0] * (len(r) - len(cur)))
                for i, v in enumerate(r):
                    if v:
                        cur[i] += v
            self._g(cc, M, g)

    def _c(self, M, c):
        """C[cc][X] = a flat array of (month number × 4096 + j, micros) pairs (a big app has millions of them)."""
        hs = self.hs
        if M not in self.mi:
            self.mi[M] = len(self.ms)
            self.ms.append(M)
        mk = self.mi[M] * 4096
        for cc, xs in c.items():
            g = 0
            Cc = self.C.setdefault(cc, {})
            for X, js in (xs or {}).items():
                for j, v in (js or {}).items():
                    v = int(v or 0)
                    if not v:
                        continue
                    g += v
                    if X >= hs:
                        cx = Cc.get(X)
                        if cx is None:
                            cx = Cc[X] = array("q")
                        cx.append(mk + int(j))
                        cx.append(v)
            self._g(cc, M, g)

    def pairs(self, cx):
        """C's pairs → (j, activity month, micros)."""
        for i in range(0, len(cx or ()), 2):
            yield cx[i] % 4096, self.ms[cx[i] // 4096], cx[i + 1]


def _mkey(d):
    return "%04d-%02d" % (d.year, d.month)


def _month_days(M):
    y, m = int(M[:4]), int(M[5:7])
    return date(y, m, 1), date(y + (m == 12), m % 12 + 1, 1) - ONE


def _month_list(a, b):
    out, M = [], _mkey(a)
    while M <= _mkey(b):
        out.append(M)
        M = _mkey(_month_days(M)[1] + ONE)
    return out


def _ranges(ds):
    """Sorted days → [[from, to]] runs (ISO)."""
    out = []
    for d in ds:
        if out and _d(out[-1][1]) + ONE == d:
            out[-1][1] = _iso(d)
        else:
            out.append([_iso(d), _iso(d)])
    return out


def _admob_side(cmon, ids, mult):
    """The app's AdMob ids (its own + the same-package ones) → ({cc: {month: USD × (1 − deduction)}}, {month: the
    days with a row, as one mask})."""
    A, mask = {}, {}
    m, dm = (cmon or {}).get("m") or {}, (cmon or {}).get("d") or {}
    for aid in ids:
        for M, by in (m.get(aid) or {}).items():
            for cc, v in (by or {}).items():
                e = A.setdefault(cc, {})
                e[M] = e.get(M, 0.0) + int(v or 0) / 1e6 * mult
        for M, b in (dm.get(aid) or {}).items():
            mask[M] = mask.get(M, 0) | int(b or 0)
    return A, mask


def _admob_whole(mask, M):
    """Every day of month M known on the AdMob side: a row, or a one-day hole between two rows (a real 0 — the known-day
    rule of active._rev_series; a day after the report's last row is never known)."""
    first, last = _month_days(M)

    def has(d):
        return bool(mask.get(_mkey(d), 0) >> (d.day - 1) & 1)
    d = first
    while d <= last:
        if not has(d) and not (has(d - ONE) and has(d + ONE)):
            return False
        d += ONE
    return True


def _appk(P, months):
    """The app's own AdMob ÷ GA4 scale per month: its weekly kf weighted by the GA4 revenue of each day (no GA4 day in
    the month: kf at its middle)."""
    kf = P["sc"]["kf"]
    num, den = {}, {}
    for d, g in (P["sc"].get("G") or {}).items():
        M = _mkey(d)
        if g:
            num[M] = num.get(M, 0.0) + g * kf(d)[0]
            den[M] = den.get(M, 0.0) + g
    out = {}
    for M in months:
        if den.get(M, 0) > 0:
            out[M] = num[M] / den[M]
        else:
            a, b = _month_days(M)
            out[M] = kf(a + (b - a) / 2)[0]
    return out


def _kc(G, A, whole, months, appk):
    """{cc: {month: (k_c, src, ≈ of the raw ratio)}} — each country's AdMob ÷ GA4 per activity month (see the module
    doc): its own whole month ("own"), else a whole month pooled with the whole months ≤ ±KC_POOL ("pool"), else — a
    thin month, or one not whole on both sides (never another month's k_c borrowed: owner, 21 Oct 2026, real data only)
    — the app's k ("app", ≈); GA4's "(not set)" always the app's."""
    lo, hi = val.K_CLAMP
    okl, okh = val.K_OK
    out = {}
    for cc, g0 in G.items():
        g, a, tab = {M: v / 1e6 for M, v in g0.items()}, A.get(cc) or {}, {}
        for i, M in enumerate(months):
            raw = src = None
            if cc != NO_CC and M in whole:
                for r in range(KC_POOL + 1):
                    ms = [x for x in months[max(0, i - r):i + r + 1] if x in whole]
                    sa, sg = sum(a.get(x, 0.0) for x in ms), sum(g.get(x, 0.0) for x in ms)
                    if ms and sa >= val.K_MIN_USD and sg >= val.K_MIN_USD:
                        raw, src = sa / sg, ("own" if r == 0 else "pool")
                        break
            tab[M] = (appk[M], "app", True) if raw is None else (min(max(raw, lo), hi), src, not okl <= raw <= okh)
        out[cc] = tab
    return out


def _geo_app(geo, sids, sdaily, spend, days, has_spend=True):
    """Google Ads cost by country × install day of the app's own spend stores → ({cc: {X: (base micros, downloads |
    None)}}, the days whose split is unknown (outside the spend cache's span, a store spent that day with no committed
    geo day, or a store whose committed split does not tie to the spend cache's cost of that day), the "geo" stats)."""
    gd = (geo or {}).get("days") or {}
    first = _d(spend["first"]) if has_spend and spend and spend.get("first") else None
    till = _d(spend["till"]) if has_spend and spend and spend.get("till") else None
    cost, unk, seen = {}, [], []
    tot = xx = sp = untied = 0

    def tie(s, k):
        """None: the store's day is known (no spend, or a split that ties); "none": spent, no split; "off": a split
        that does not tie (a store-day committed {} while it spent, an account not asked, the cost restated since)."""
        c = int((sdaily.get(s) or {}).get(k) or 0)
        ent = (gd.get(s) or {}).get(k)
        if ent is None:
            return "none" if c else None
        g = sum(int(v[0] or 0) for v in ent.values() if isinstance(v, list) and v)
        return "off" if abs(g - c) > max(GEO_TIE_REL * abs(c), GEO_TIE_ABS) else None
    for X in days:
        k = _iso(X)
        why = {tie(s, k) for s in sids} if first and till and first <= X <= till else {"span"}
        if why - {None}:
            unk.append(X)
            untied += "off" in why
            continue
        agg = {}
        for s in sids:
            sp += int((sdaily.get(s) or {}).get(k) or 0)
            ent = (gd.get(s) or {}).get(k)
            if ent is None:
                continue
            seen.append(X)
            for cc, v in ent.items():
                if not isinstance(v, list) or not v:
                    continue
                e = agg.setdefault(cc, [0, 0.0, False])
                e[0] += int(v[0] or 0)
                if len(v) > 1 and v[1] is not None:
                    e[1] += float(v[1])
                else:
                    e[2] = True
        for cc, (c, dl, dln) in agg.items():
            tot += c
            xx += c if cc == NOT_SPLIT else 0
            cost.setdefault(cc, {})[X] = (c, None if dln else round(dl, 2))
    st = {"from": _iso(min(seen)) if seen else None, "till": _iso(max(seen)) if seen else None,
          "known_days": len(days) - len(unk), "unknown_days": len(unk), "untied_days": untied, "unk": _ranges(unk),
          "xx_share": _r(xx / tot) if tot else None, "cov": _r(tot / sp) if sp else None}
    return cost, set(unk), st


def _zrow(X, thru, fthru, unk, cc, billed=True):
    """The row the page makes of a short [X] (roi_frontend's zx — the same rule): a day of a country with no installs,
    no revenue and no Ads cost (spend 0 on a known day, null on an unknown one / "Unknown country"), its cells 0 as far
    as the cube read through (final as far as it folded through); "Not split": spend only. The build writes [X] only
    when the row it made is exactly this one."""
    t = [None] * len(T)
    if cc == NOT_SPLIT:
        sp = None if unk else 0.0
        return {"X": X, "n": None, "na": None, "sp": sp, "spi": sp if billed else None, "d": None, "df": 0, "u": None,
                "t": t, "s": None, "sd": None, "be": None, "st": "N/A", "q": False, "qo": 0}
    obs = min(gco.LAGS - 1, (thru - X).days)
    df = max(0, min(obs, (fthru - X).days) + 1)
    for j, a in enumerate(T):
        if a <= 30 and a < df:
            t[j] = 0.0
    m = []
    if df > 30:
        while X + timedelta(days=LATE_STEP * (len(m) + 2)) <= thru:
            m.append(0.0)
    mf = 0
    while mf < len(m) and X + timedelta(days=LATE_STEP * (mf + 2)) <= fthru:
        mf += 1
    for a in (60, 90, 180):
        if a // LATE_STEP - 2 < mf:
            t[T.index(a)] = 0.0
    sd = X + timedelta(days=obs)
    if m and X + timedelta(days=LATE_STEP * (len(m) + 1)) > min(sd, X + timedelta(days=T[-1])):
        sd = X + timedelta(days=LATE_STEP * (len(m) + 1))
    sp = None if (unk or cc == NO_CC) else 0.0
    r = {"X": X, "n": 0, "na": None, "sp": sp, "spi": sp if billed else None, "d": [0.0] * (obs + 1), "df": df,
         "u": None, "t": t, "s": 0.0, "sd": _iso(sd), "be": None, "st": "N/A", "q": False, "qo": 0}
    if m:
        r.update(m=m, mf=mf)
    return r


def _tzh(tz_a, tz_g, M):
    """Hours GA4's day starts before AdMob's (the month's middle; None: a time zone unknown)."""
    try:
        from zoneinfo import ZoneInfo
        mid = datetime(int(M[:4]), int(M[5:7]), 15, 12, tzinfo=timezone.utc)
        oa, og = mid.astimezone(ZoneInfo(tz_a)).utcoffset(), mid.astimezone(ZoneInfo(tz_g)).utcoffset()
        return round((og - oa).total_seconds() / 3600, 2)
    except Exception:
        return None


def _ads_tz(data_dir):
    """Google Ads store → the time zones of the accounts its campaigns spend from (fetch.gads_hourly's month files: the
    account's zone + campaign → store; one month in memory at a time) — the zone the Ads day (segments.date) is in."""
    from .fetch import gads_hourly as gh
    mf, out = gh.months(data_dir), {}
    for m in mf.months():
        f = mf.peek(m)
        for acct, cs in (f.get("h") or {}).items():
            tz = (f.get("tz") or {}).get(acct)
            for cid in cs or {}:
                s = (f.get("camp") or {}).get(cid)
                if s:
                    out.setdefault(s, set()).add(tz or "")
        mf.got.pop(m, None)
    return out


def _json(x):
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))


def _cty(acc, cv, late, P, rows, spend, pre, a, store, rev, ded_rate, ids, key, out_dir, data_dir):
    """🌍 Every country's install-day rows (see the module doc) → the packs written + the file's "cd" (None: no country
    in the cube). Raises on a failure (the caller: no "cd", counted)."""
    from . import value_build as vb
    if cv.failed:
        raise RuntimeError("the cube's country cells were not all read")
    if not late.get("info", {}).get("thru") or not any(cv.E.values()) and not any(cv.N.values()) \
            and not any(cv.C.values()):
        return None                                 # no country GA4 named: no filter (Ads alone never makes one)
    hs, info = P["hs"], late["info"]
    thru = _d(info["thru"])
    fthru = hs - ONE
    while fthru < thru and late["fin"](hs, fthru + ONE):
        fthru += ONE
    days = [hs + timedelta(days=i) for i in range((thru - hs).days + 1)]
    months = _month_list(hs, max(thru, _d(info.get("till") or info["thru"])))
    # Google Ads by country × day: only the app's own spend stores read (one month file in memory at a time), the
    # spend cache's span; nothing kept for the next app
    sp_all = (pre or {}).get("spend") or {}
    sdaily = sp_all.get("daily") or {}
    sids = sorted(vb.app_sids(pre, a, store, sdaily)) if sp_all else []
    try:
        from .fetch import gads_geo_day as gdd
        geo = (gdd.load(data_dir, keep=set(sids)) or {}) if sids else {}
    except Exception:
        geo = {}                                    # unreadable: every day a store spent on is unknown ('—'), counted
        acc.cdn["geo_failed"] += 1
    gccy = geo.get("ccy") or (spend or {}).get("ccy") or "USD"
    fxg = val._fx_fn((pre or {}).get("fx"), gccy)[0]
    billed = bool(spend) and gccy == spend.get("ccy")
    cost, unk, gst = _geo_app(geo, sids, sdaily, spend, days)
    geo = None
    gst["billed"] = 1 if billed else 0
    if acc.adtz is None:                            # the Ads day's time zone: the accounts of the app's stores
        try:
            acc.adtz = _ads_tz(data_dir)
        except Exception:
            acc.adtz = {}
    zs = set().union(*[acc.adtz.get(s) or set() for s in sids]) if sids else set()
    gst["tzs"] = len(zs - {""})
    gst["tzh"] = (_tzh(next(iter(zs)), P["tz"], months[-1]) if len(zs) == 1 and "" not in zs and P.get("tz")
                  else None)
    # each country's AdMob ÷ GA4 per activity month
    mult = (1.0 - ded_rate) if ded_rate else 1.0
    A, mask = _admob_side(acc.cmon, list(ids or [a["app_id"]]), mult)
    whole = set()
    for M in months:
        f0, f1 = _month_days(M)
        if f0 >= hs and cv.mdays.get(M, 0) == f1.day and _admob_whole(mask, M):
            whole.add(M)
    appk = _appk(P, months)
    kc = _kc(cv.G, A, whole, months, appk)
    # GA4's revenue without a country per activity month ("(not set)" + the measured "(other)"), of every row
    unp = {}
    for M in months:
        if cv.tot.get(M, 0) > 0:
            unp[M] = min(1.0, ((cv.G.get(NO_CC) or {}).get(M, 0) + cv.loss.get(M, 0)) / cv.tot[M])
    ut = sum(cv.tot.get(M, 0) for M in unp)
    # GA4: country not given — per activity month, All (the app's k × GA4's every row of the month: the ledger's t)
    # − Σ every country row's revenue (k_c × that country's GA4 cells, "Unknown country" too), signed: in a month on
    # the countries' own AdMob match (most of its named GA4 revenue on an own / pooled k_c) AdMob's country report
    # already placed it (≈ 0 left); on the app's k it is GA4's measured "(other)" — in no country row
    ng, nga = {}, 0.0
    for M in months:
        if cv.tot.get(M, 0) <= 0:
            continue
        allm, s, named, mine = appk[M] * cv.tot[M] / 1e6, 0.0, 0, 0
        for cc in sorted(cv.G):
            g = (cv.G.get(cc) or {}).get(M, 0)
            if not g:
                continue
            k = (kc.get(cc) or {}).get(M) or (appk[M], "app", True)
            s += k[0] * g / 1e6
            if cc != NO_CC:
                named += g
                mine += g if k[1] in ("own", "pool") else 0
        ng[M] = [_r(allm - s, 2), _r(unp.get(M)), "own" if named and 2 * mine >= named else "app"]
        nga += allm
    ngs = sum(v[0] for v in ng.values())
    kst = {"own_months": 0, "pool_months": 0, "app_months": 0, "est_months": 0,
           "tzh": _tzh((rev or {}).get("tz"), P.get("tz"), months[-1]) if (rev or {}).get("tz") and P.get("tz") else None,
           "unp": {M: _r(v) for M, v in sorted(unp.items())}, "unp_lim": UNP_LIM,
           "unp_all": _r(sum(unp[M] * cv.tot[M] for M in unp) / ut) if ut else None}
    ccs = {cc for cc in set(cv.E) | set(cv.N) | set(cv.C)
           if (cv.E.get(cc) or cv.N.get(cc) or cv.C.get(cc))}
    ccs |= {cc for cc, xs in cost.items() if cc != NOT_SPLIT and any(c for c, _ in xs.values())}
    allr = {r["X"]: r for r in rows}
    s30, n30, u30 = {}, {}, {}
    out, meta = [], {}
    for cc in sorted(ccs):
        tab = kc.get(cc) or {}
        kM = {M: tab.get(M) or (appk[M], "app", True) for M in months}
        for M, g in (cv.G.get(cc) or {}).items():
            if g and M in kM:
                k = kM[M]
                kst[k[1] + "_months"] += 1
                kst["est_months"] += bool(k[2] and k[1] != "app")
        kfm = {(int(M[:4]), int(M[5:7])): (k[0], "ok", False, k[0]) for M, k in kM.items()}
        kl = kfm[(int(months[-1][:4]), int(months[-1][5:7]))]

        def kf_c(day, kfm=kfm, kl=kl):
            return kfm.get((day.year, day.month), kl)
        Ec, Nc, Cc = cv.E.get(cc) or {}, cv.N.get(cc) or {}, cv.C.get(cc) or {}
        co_x = {X: {"r": list(arr), "u": [Nc.get(X, 0)]} for X, arr in Ec.items()}
        for X, n in Nc.items():
            co_x.setdefault(X, {"r": [], "u": [n]})
        B = {}
        for X, cx in Cc.items():
            b = B.setdefault(X, {})
            co_x.setdefault(X, {"r": [], "u": [0]})
            for j, M, v in cv.pairs(cx):
                b[j] = b.get(j, 0.0) + v / 1e6 * (kM.get(M) or (kl[0],))[0]
        sc = (cost.get(cc) or {}) if cc != NO_CC else {}
        for X in sc:
            co_x.setdefault(_iso(X), {"r": [], "u": [0]})
        sp_c = None
        if cc != NO_CC and spend and spend.get("first") and spend.get("till"):
            sp_c = {"first": spend["first"], "till": spend["till"], "daily": {_iso(X): c for X, (c, _) in sc.items()},
                    "installs": {_iso(X): dl for X, (_, dl) in sc.items() if dl is not None}}
        Pc = {"pre": P["pre"], "sc": {"kf": kf_c}, "xs": {}, "S": P["S"], "hs": hs}
        got = _cohorts(Pc, sp_c, fxg, {"read_today": _iso(thru), "x": co_x}, thru,
                       {"B": B, "full": late["full"], "fin": late["fin"], "q": late["q"]}, edge=fthru)
        by = {}
        for r in got:
            X = r["X"]
            r["u"], r["q"] = None, False
            if X in unk or cc == NO_CC:
                r["sp"] = r["spi"] = r["na"] = r["be"] = None
            elif not billed:
                r["spi"] = None
            if r.get("m"):
                for a_ in (60, 90, 180):
                    if a_ // LATE_STEP - 2 < r["mf"]:
                        r["t"][T.index(a_)] = r["m"][a_ // LATE_STEP - 2]
            bits = 0
            if r["n"] or (r["s"] or 0) > 0 or (r["sp"] or 0) > 0 or r["na"]:   # ≈ only on a row with something of
                nd = len(r["d"] or [])                                          # its own to be off (never a short one)
                end = X + timedelta(days=max(nd - 1, LATE_STEP * (len(r["m"]) + 1) if r.get("m") else -1))
                bits = late["q"](X, end) if end >= X else 0
                used = {_mkey(X + timedelta(days=L)) for L, v in enumerate((Ec.get(_iso(X)) or [])[:nd]) if v}
                used |= {M for j, M, v in cv.pairs(Cc.get(_iso(X))) if v and j <= len(r.get("m") or [])}
                for M in used:
                    k = kM.get(M)
                    if k and k[1] == "app":
                        bits |= 16
                    else:
                        bits |= 8 if k and k[2] else 0
                    if cc != NO_CC and unp.get(M, 0) > UNP_LIM:
                        bits |= 64
            r["qo"] = bits
            by[X] = r
        full = [by.get(X) or dict(_zrow(X, thru, fthru, X in unk, cc, billed), z=1) for X in days]
        _statuses(full)
        rows_out, n_tot, sp_tot, spi_tot, known, na_days = [], 0, 0.0, 0.0, False, 0
        for r in full:
            X = r["X"]
            if r.get("z"):                          # a day the cube and Google Ads have nothing of: the page's row
                rows_out.append([_iso(X)])
            else:
                ro = _row_out(r)
                rows_out.append([ro[0]] if r["n"] == 0 and ro == _row_out(_zrow(X, thru, fthru, X in unk, cc, billed))
                                else ro)
            n_tot += r["n"] or 0
            na_days += r["st"] == "N/A"
            if r["sp"] is not None:
                known = True
                sp_tot += r["sp"]
                spi_tot += r["spi"] or 0
            if r["df"] > 30 and r["d"]:
                s30[X] = s30.get(X, 0.0) + r["d"][30]
                n30[X] = n30.get(X, 0) + (r["n"] or 0)
                if cc == NO_CC:
                    u30[X] = u30.get(X, 0.0) + r["d"][30]
        g = cv.G.get(cc) or {}
        gt = sum(g.values())

        def share(src, g=g, gt=gt, kM=kM):
            return _r(sum(v for M, v in g.items() if (kM.get(M) or ("", "app"))[1] == src) / gt) if gt else None
        out.append((cc, _json(rows_out)))
        meta[cc] = [cc, n_tot, _r(sp_tot) if known else None, _r(spi_tot, 2) if known and billed else None, None,
                    na_days, share("app")]
        del full, by, got, rows_out, co_x, B
        cv.E.pop(cc, None), cv.N.pop(cc, None), cv.C.pop(cc, None)     # its cells are in its JSON now: let them go
    # "Not split": Google Ads' unmapped cost by install day (GA4's "(other)" has no install day: the loss note)
    ns = cost.get(NOT_SPLIT) or {}
    if ns or cv.loss:
        rows_out, sp_tot, spi_tot, known = [], 0.0, 0.0, False
        for X in days:
            u = X in unk
            c, dl = ns.get(X, (0, None))
            spi = None if u else c / 1e6
            sp = None if u else spi * (fxg(X) or 0)
            r = {"X": X, "n": None, "na": None if u else dl, "sp": sp, "spi": spi if billed else None, "d": None,
                 "df": 0, "u": None, "t": [None] * len(T), "s": None, "sd": None, "be": None, "st": "N/A", "q": False,
                 "qo": 0}
            ro = _row_out(r)
            rows_out.append([ro[0]] if ro == _row_out(_zrow(X, thru, fthru, u, NOT_SPLIT, billed)) else ro)
            if sp is not None:
                known = True
                sp_tot += sp
                spi_tot += spi or 0
        out.append((NOT_SPLIT, _json(rows_out)))
        meta[NOT_SPLIT] = [NOT_SPLIT, None, _r(sp_tot) if known else None, _r(spi_tot, 2) if known and billed else None,
                           None, None, None]
    if not out:
        return None
    # packs: by installs, then spend, then code; filled in turn up to PACK_MAX (a bigger country alone)
    order = sorted(out, key=lambda x: (-(meta[x[0]][1] or 0), -(meta[x[0]][2] or 0), x[0]))
    groups, cur, size = [], [], 0
    for cc, js in order:
        s = len(js.encode("utf-8")) + len(cc) + 4
        if cur and size + s > PACK_MAX:
            groups.append(cur)
            cur, size = [], 0
        cur.append((cc, js))
        size += s
    if cur:
        groups.append(cur)
    bh = hashlib.sha1()                             # the packs' build: every country's rows (each pack says it too)
    for cc, js in order:
        bh.update((_json(cc) + ":" + js + "\n").encode("utf-8"))
    bid = bh.hexdigest()[:12]
    packs, names = [], []
    for i, grp in enumerate(groups):
        name = "%s%s_c%02d.json.gz" % (PREFIX, key, i)
        raw = (('{"b":%s,"c":{' % _json(bid)) + ",".join(_json(cc) + ":" + js for cc, js in sorted(grp))
               + '},"ix":%d,"key":%s,"v":%d}' % (i, _json(key), CD_V)).encode("utf-8")
        write_gz_stable(os.path.join(out_dir, name), raw)
        packs.append([name, hashlib.sha1(raw).hexdigest()[:12]])
        names.append(name)
        for cc, _ in grp:
            meta[cc][4] = i
    # Σ countries vs the All row (D30, the install days both have final): the measured gap of the two k's / reads
    dd = [X for X in days if X in s30 and X + timedelta(days=30) <= fthru and X in allr
          and allr[X]["t"][J30] is not None]
    sa, sc_ = sum(allr[X]["t"][J30] for X in dd), sum(s30[X] for X in dd)
    lusd = sum(v / 1e6 * appk.get(M, 1.0) for M, v in cv.loss.items())
    cd = {"v": CD_V, "b": bid, "packs": packs, "c": [meta[cc] for cc, _ in order], "from": _iso(hs), "to": _iso(thru),
          "thru": _iso(thru), "fthru": _iso(fthru), "newest": info.get("till"), "kc": kst, "geo": gst,
          "loss": {"days": info.get("oth") or 0, "max_share": info.get("omax"), "flag_days": info.get("loss") or 0,
                   "usd": _r(lusd, 2)},
          "diff": {"age": 30, "days": len(dd), "all": _r(sa, 2), "cty": _r(sc_, 2),
                   "rel": _r(sc_ / sa - 1) if sa else None, "n_all": sum(allr[X]["n"] for X in dd),
                   "n_cty": sum(n30.get(X, 0) for X in dd), "unk": _r(sum(u30.get(X, 0.0) for X in dd), 2)},
          "ng": {"m": ng, "usd": _r(ngs, 2), "all": _r(nga, 2), "rel": _r(ngs / nga) if nga else None}}
    acc.packs.update(names)
    acc.cdn["apps"] += 1
    acc.cdn["countries"] += len(order)
    acc.cdn["packs"] += len(packs)
    return cd


def app_step(acc, store, a, key, rev, pre, cfg, out_dir, data_dir, now=None, ids=None):
    """One app → roi_<key>.json.gz (+ its summary into acc). Never raises. ids: the AdMob apps on its Play package
    (the ⚙️ ad setting changes read their ad units together, as its revenue)."""
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
        fclk = getattr(acc.fc, "clock", None)          # 🌍 the country filter: its read rides the cube's one pass;
        cv = _Cty(P["hs"], clock=fclk) if acc.cube else None   # its time never counts in the forecast's budget
        try:                                            # the cohort cube (D60, D90 … the app's age; GA4_CUBE only):
            with _sc.stage("roi_cube"):                 # (⏱ measure only, stage_clock: summed over the apps)
                late = (_late(data_dir, aid, store.get("stream_id"), P, visit=cv.visit)   # a bad file costs only
                        if acc.cube else None)                                           # those columns
        except Exception:
            late = None
        rows = _cohorts(P, spend, fxf, co, today, late if late and "B" in late else None)
        off, checked = _tie_off(ida, (co or {}).get("x") or {}, ida.get("days"))
        olo = {str(k) for f in ("lo", "lf") for k in ((co or {}).get(f) or {})}   # the D0 … D30 read's "(other)"
        for r in rows:
            if r["d"]:
                r["q"] = any(_iso(r["X"] + timedelta(days=L)) in off or _iso(r["X"] + timedelta(days=L)) in olo
                             for L in range(len(r["d"])))
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
        sids = ()
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
        if late is not None:
            body["late"] = late["info"]
        if cv is not None and late is not None and "B" in late:   # 🌍 one country's install-day table (own try:
            t0 = fclk() if fclk else None                          # a failure costs only it — no "cd", counted)
            try:
                with _sc.stage("roi_country"):
                    cd = _cty(acc, cv, late, P, rows, spend, pre, a, store, rev, ded_rate, ids, key, out_dir, data_dir)
                if cd:
                    body["cd"] = cd
            except Exception:
                acc.cdn["failed"] += 1
            if t0 is not None:
                cv.sec += max(0.0, fclk() - t0)
        if cv is not None and fclk and acc.fc is not None:          # the forecast's clock (started on the first app)
            acc.fc.t0 += cv.sec                                     # skips what the country part took: its budget,
        cv = None                                                   # its re-tunes, its numbers as without it
        fcs = None
        ares = None
        try:                                            # ⚙️ the ad setting changes (before the forecast: its back-tests
            from . import adcfg_build as acb            # label them) — a failure costs only them
            if acc.adsrc is not None:
                if acc.ac is None:
                    acc.ac = acb.start(acc.adsrc, data_dir, now)
                with _sc.stage("adcfg"):
                    ares = acb.app_step(acc.ac, aid, key, store, ids)
        except Exception:
            ares = None
        try:                                            # 🔮 the forecast (its own budget and daily cadence; a failure
            from . import forecast_build as fob         # costs only it)
            if acc.fc is None:
                acc.fc = fob.start(data_dir, now, cal=acc.cal)
            decs = {x["cc"]: x["dec"] for x in cty["rows"]}
            eng = [dict(x, dec=decs.get(x.get("cc"))) for x in (((detail or {}).get("countries") or {}).get("rows") or [])]
            fgeo, pairs = None, None
            try:                                        # Google Ads country weeks → the "Budget by country" planner
                geo = (pre or {}).get("geo") or {}
                fgeo = fob.geo_weeks(geo.get("weeks") or {}, sids, fxf) if sids else None
                pairs = fob.cs_pairs(acc.fc, geo, fxf) if fgeo else None
            except Exception:
                fgeo, pairs = None, None
            with _sc.stage("forecast"):
                body["fc"] = fob.app_step(acc.fc, aid, key, rows, P, ida, life, body["life_till"], eng,
                                          rev_cty=(rev or {}).get("cty"), unst=store, geo=fgeo, cs_pairs=pairs,
                                          acfg=(ares or {}).get("steps"))
            fcs = fc_summary(body["fc"])
        except Exception:
            body["fc"] = None
        if body["fc"] and ares:                         # ⚙️ → the forecast's "why" (a block of its own: every other
            try:                                        # number of the file as it was)
                from . import adcfg_build as acb
                from .engine import forecast_vd as _vd
                blk = acb.page(ares, body["fc"], _vd.AX)
                if blk:
                    body["fc"] = dict(body["fc"], acfg=blk)
            except Exception:
                pass
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
    """The pointer's forecast line: next 30 / 90 / 180 days revenue (corrected), the accuracy, what is ready; + the
    verified horizon n (engine vd) with its revenue rn and accuracy en."""
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
    n = (fc.get("hz") or {}).get("n")                  # engine vd's verified horizon: the longest the app's data checks
    if n and len(tot) >= n:
        c = (fc.get("cal") or {}).get(str(n)) or {}
        out.update(n=n, rn=_r(sum(tot[:n]), 2),
                   en=c.get("mape_normal") if c.get("mape_normal") is not None else c.get("mape"))
    return out


def _clean(out_dir, keep):
    try:
        names = os.listdir(out_dir)
    except OSError:
        return
    for f in names:
        if ((FILE_RE.match(f) or PACK_RE.match(f)) and f not in keep) or (f == ALL_FILE and ALL_FILE not in keep):
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
        keys = {PREFIX + x["key"] + "_c" for x in acc.apps}     # 🌍 an app's packs live while its file does
        _clean(out_dir, {x["file"] for x in acc.apps} | {ALL_FILE} | {p for p in acc.packs if p[:len(PREFIX) + 14] in keys})
        sts = {}
        for x in acc.apps:
            sts[x["st"]] = sts.get(x["st"], 0) + 1
        LINE = ("roi: apps %d, worse %d, watch %d, better %d, normal %d, too early %d, n/a %d, skipped %d, failed %d, "
                "forms ga4 %d"
                % tuple([len(acc.apps)] + [sts.get(k, 0) for k in ("Worse", "Watch", "Better", "Normal", "Too early",
                                                                     "N/A")] + [acc.skipped, acc.fails, acc.f4m]))
        if acc.cube:                                    # 🌍 the country filter (counts only)
            c = acc.cdn
            LINE += "; countries: apps %d, countries %d, packs %d, failed %d, ads split unread %d" % (
                c["apps"], c["countries"], c["packs"], c["failed"], c["geo_failed"])
        if acc.fc is not None:
            from . import forecast_build as fob
            fob.finish(acc.fc)
            LINE += "; " + fob.line(acc.fc)
        if acc.ac is not None:
            from . import adcfg_build as acb
            LINE += "; " + acb.line(acc.ac)
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
