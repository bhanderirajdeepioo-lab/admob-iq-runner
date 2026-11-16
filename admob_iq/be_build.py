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
  (fewer: uncovered, never estimated); the log CPI / log eCPM_fs range of its usable days (a later judged day outside
  it is answered at the range's edge and moved by the ratio past it — _edge; a smaller row outside it is not answered:
  _answers; K3's own chances only inside it). K3: log(BE + 1)
  = a + b·log CPI + c·log eCPM_fs + σ·ε, right-censored normal errors (Schmee–Hahn EM). Its ROAS curve: per GRID age, Huber → bot → Huber of log ROAS(age) on the same inputs over
  the days that reached that age (the kept residuals' 10 / 90 % = its range), up to the first age with < 20 kept days
  (the curve's limit). Each curve entry also stores the country's median of log ROAS(age) over its usable past days
  (rmed): the card's benchmark is built from these, per country (see the card below). "bm" (fits[cc]["bm"] = [bCPI,
  beCPM_fs, bBE | null, bLim]) = the countries table's "B" (the card does not use it), from K3's OWN training set at O (the bot-kept real-BE days
  as events at their BE day + the not-yet days censored at their age): bCPI = exp(median log CPI), beCPM_fs = exp(median
  log eCPM_fs), bBE = the Kaplan–Meier median (S(t) = Π (1 − d_i / n_i) over the event times, n_i = days at risk at t_i;
  the first event time with S ≤ 0.5; null = beyond what the data watched, the page: "B > bLim days"), bLim = round(tmax).
  The fits body carries "fv" (FV = 2): a cache without it (or older) is refitted at once, so the triple is there on the
  first build after the change, not a day later.
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
  predict (every build, from the caches only): per install day each covered country with a CPI and an eCPM_fs that day
  (_answers): its curve at them (made non-decreasing in age; past its learned range the edge's curve moved by the ratio,
  _edge),
  weighted by its share of the day's covered spend and summed = the app's ROAS
  curve (a country whose curve stops earlier keeps its last value: a lower bound) — the owner's rule, never an average
  of the countries' BE days — → app BE = where it first reaches 100 % (linear between grid ages), the band and its
  crossings (the page reads ROAS at 30 / 90 / 180 off this same curve: one curve, one answer — a separately
  calibrated P beside it contradicted its BE day); per covered country its calibrated
  K3 P's (null when its CPI / eCPM_fs is outside its learned range: K3 answers only inside it) and days (null past the
  longest age its data watched, that limit beside it); the uncovered countries as their
  spend share (no benchmark, no CPI / eCPM_fs that day, or a row under $5 / 30 new users outside its learned range:
  "x % spend: data kam"; the ones under 0.5 % as one "…"
  rest); the card: ROAS so far at days 1, 2, 3, 4,
  7, 14 against the countries' own median past ROAS joined by the day's spend (below). A day under 4 days old (age < 4)
  is provisional: GA4's country and first-session reads are not final yet, and neither are Google Ads' installs (the
  CPI: installs read at age 0–1 were a median 0.91 of their final count, ≈ 1.00 from age 2; the back-test answers
  with final inputs) — the page marks it. The grid ages a day has lived carry its REAL cumulative ROAS (never the
  model's: an old install day's ROAS at 30 / 90 / 180 is what it made); past them its ROAS so far floors the curve (a
  cumulative ROAS never falls; from its real BE day on it is ≥ 100 %) and caps any unlived age before it; a day that
  already broke even answers its real day (no range); the 80 % range only as far as the band reaches (beyond it: no
  end, never the median line).
  the card (owner, 15 Nov 2026: "haan dono karo"): one country set S per card = the day's COVERED countries (the "cty"
  ones, small rows too) with a curve entry at every card day (GRID index 0–5; a cumulative ROAS must not fall because the
  set changed); roas[j] = Σ cumulative revenue ÷ Σ spend over S, null where a country of S has no cell at j yet; bench[j]
  = Σ spend × exp(the country's stored curve median at j) ÷ Σ spend (each country's own benchmark, joined by the day's
  spend share — both lines from the same countries); fin[j] = 1 when every country of S has a FINAL cell at j and that
  date is at least CLAG days old; cv = S's spend ÷ the day's whole country spend (the rest is "x % spend: data kam");
  chk[j] = 1 when a PACK-GAP date lies in [install day, + GRID[j]] (below). No card day with a value: "card" is null and
  "cw" says why ("j" under $5 / 30 new users, "k" no country spend split, "c" no covered country, "r" their ROAS has not
  arrived yet).
  PACK GAPS (load, pack_gaps): the country packs come from the GA4 cube, which folds an activity date once, at D+3; for
  a date it can be nearly empty while the app's All rows are whole, and a cumulative ROAS built from the countries is then
  low. S_all[D] = the All rows' FINAL daily revenue at activity date D, S_cty[D] = the same over EVERY country row in
  every pack ("--" / "XX" / "ZZ" too: the All row includes them), streamed while load reads (nothing kept per row). D is a
  gap when D ≤ newest − CLAG, S_all[D] ≥ PACK_MIN (1 USD: a smaller total says nothing) and S_cty[D] < PACK_GAP (0.35) ×
  S_all[D], and D ≤ the packs' own final edge (cd["fthru"]: a later date is not folded yet); no packs: no gap. The set
  rides in the pin (pin[4]) to predict.
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
                          [[cc, share, CPI, eCPM_fs, P30, P90, P180, median, low, high, lim, rk, bm], …] (P30 / P90 /
                          P180 null outside the country's learned range; bm = [bCPI (USD, 4 dp), beCPM_fs
                          (USD, 3 dp), bBE (days, 1 dp, or null: beyond bLim), bLim] — the country's benchmark, or null
                          for an old fits cache; rk 1 / 2 / 3:
                          the country broke even — median = its real day: exact / "≤" / not final yet; 0: off its
                          own curve (shifted to its own final read when it has one) given it has not broken even by its
                          own so-far age; 4: ≤ a 30-day column not final yet;
                          5 / 6: it lived past K3's limit without breaking even — median = its so-far age, final /
                          not final yet), "jd" 0 (only on a day under $5 / 30 new users: no model, no countries — its
                          real numbers only), "card": {"roas", "bench", "fin" (1 final / 0 not final yet), "cv" (S_j's share of the day's country spend), "chk"
                          (1: a pack-gap date inside the window; the point is low by what the data lost)}, "now": ["be", BE day, kind ("x" exact / "nf" not final
                          / "b" ≤ a column / "s" ≤ its so far), so-far age, ROAS so far] (the ROI row's own) | ["no",
                          so-far age, ROAS so far, final? (1: older than LAG days)]}]} (every install day with
                          spend, oldest first)
  dashboard["be"]        {"v", "origin", "calib", "apps": {app id: {"key", "file", "v", "n", "cov"}}}

⚖️ GOOGLE ADS USERS ONLY (owner, 16 Nov 2026: "haan sirf google ads wale users se karo · google ads and organic dono ka
alag alag dekh saku esa kar do"; BE_PAID, s["be_paid"]): the ROAS above was EVERY new user's cohort revenue ÷ the Google
Ads spend — organic users keep earning when the spend drops, and on a tiny spend that made an early breakeven that never
was. Each app has one SOURCE a build:
  src "p" — roi_build's Google Ads users' pass is "ok" for it (roi_build.PAID: run_uninstall ran it earlier in this same
    process), its file is in that pass's scratch folder (roi_build.PAID_DIR) and their first-session store is there
    with its history read (without it no country of theirs has an eCPM_fs: no model at all; with its backfill not done
    yet the models would train on its recent days only — "busy" until then): load reads the paid All rows and the paid
    packs from there (GA4's own reads of the users whose FIRST-USER channel is Cross-network / Paid Search, never a split
    of totals), the first-session eCPM from fetch.ga4_nvr_paid's store (the same "c" "n" rows rule), AdMob's daily
    revenue for _holes from the all-users ROI file's "life" (AdMob has no source split; a hole is a date GA4 lost on
    every cohort while AdMob was normal — the same rule on these rows). PACK GAPS of src "p" (pack_gaps_p): the paid All
    row and the paid packs are ONE read — the paid cube's cells — so a date it folded near-empty sinks both and their
    ratio never moves; the paid packs' daily revenue is held against an INDEPENDENT read instead, the all-users All rows'
    final daily revenue (ga4_cohort's exact store): a date is a gap when that share falls under PACK_GAP × its median
    over the GAP_N dates before. Everything after it (fit, K3, the curves, the calibration, predict, the card, the
    countries table, the B columns) runs unchanged on these rows. The file: "src": "p", and on each day with an eCPM
    card "ecs": "a" beside it (be_ecpm's read stays every user's — its Google Ads users' split is not built).
  src "a" — any other app: the file of the step without the switch, byte for byte, + "src": "a" and "pw" (for the page's
    "Google Ads users ka data … abhi aa raha hai"): {"st": "busy" (+ "from" / "next" as the pass gave them: GA4's Google
    Ads users' history still being read; no "from" / "next": their first-session history still being read) | "none" (no
    paid store of the app, or nothing in it: GA4 has none of their reads) | "fail" (the pass raised, or here its file
    was gone, unreadable, its rows raised or its source could not be told — the "be paid" health line with its type,
    counted: never a silent switch back) | "off" (their data not made this build: no pass ran for the app — its cube
    or country part not there —, or nothing of their first-session store read yet — its read off, not run yet or of
    another version) | "cal" (no Google Ads users' calibration yet: too few of their breakeven days for one, or its
    first one failed)}.
  be_paid off: every file exactly as without it (no "src" key at all), no Organic file.
  The caches never mix: fits_<key>.json.gz / calib.json are src "a"'s, fitsp_<key>.json.gz / calib_p.json src "p"'s,
  each calibration made from its own source's apps only (the same once-a-UTC-day rule and CALV each; a source with no app
  that build: none of it made); predict reads its source's — an app that changes source refits from its own cache.
  calib.json made with be_paid on carries "bp": 1 (made from that build's src "a" apps only); one made in the other mode
  is made again at once, its growth bound never used for it (BE_PAID off the same UTC day: every app answered with a
  calibration of every app, never the switch-on one's; a calib.json never made with the switch on has no stamp — byte
  for byte as before). No calibration of a source yet and its first one failing costs only that source's apps this
  build (be_paid off: the whole step, as before). No Google Ads users' calibration yet and their back-test with no
  covered country at any month start (too few of their breakeven days — a STATE, not a failure): calib_p.json becomes a
  stub {"v", "tried", "apps"} (load_calib refuses it), the apps go on as src "a" ("cal": never counted as failed, no
  health line) and, every one of them tried then (none new, none that raised), nothing of them is read or tried again
  that UTC day (no paid load, no back-test, no Organic pass). A real exception there: its health line, counted, tried
  again the next build.
🌱 ORGANIC (src "p" apps only; the page's Google Ads | Organic switch): every new user who is NOT a Google Ads user = the
all-users cells − the Google Ads users' cells per country × install day, from the two cubes' own reads (the probe measured
the paid read + its complement = the whole read) — the all-users packs (out_dir, one at a time) and the paid packs
(scratch: the Google Ads users' cells collected while load() reads their packs — each pack read ONCE a build — and
held compactly, one array per country, until the app's src "p" file exists: the pass runs only for an app whose file
was made, its Organic file written with it), one app at a time, through the install day both cubes read through. Users
n_o = n_a − n_p; revenue cum_o = cum_a − cum_p at the card ages (GRID) from FINAL cells only (both rows final there).
USERS ARE FINAL ONLY on an install day whose day 0 BOTH cubes folded (X ≤ the older fthru): a younger day's two counts
are two reads made at different times (each cube's own hot read) — "n" null there, no benchmark set (no "s" values),
no users-drift test. A country-day whose Google Ads side is above the all-users one — its users (a final day), or a
cell by more than the rounding (_otol) — is DRIFT (two reads made at different times): left out of every organic number
and counted on its day ("dr"), never clamped to 0 (a difference inside the rounding is rounding: 0). The day's line:
users Σ every country ("--" / "ZZ" too; "XX" is Google Ads cost only), revenue Σ the named countries (null where a
country of it is not final) + "--" / "ZZ" COUNTED ONCE: on an activity month whose named GA4 revenue is mostly on own
/ pooled k_c (roi_build's own verdict per month, every user's cd "ng" "m": "own") AdMob already booked those users under
their real countries (roi_build: the "--" row's revenue is inside the named countries' k_c), so each step of their
revenue between two card ages whose days all lie in such months is left out (a step across both kinds is kept whole:
its split is not measured); a file without the verdicts: the day's named rows decide it (pack row bit 16 off on most of
their revenue so far: the day's "--" / "ZZ" revenue left out); their users always in n. Per user = revenue ÷ users, fin
1 where it is final and the date at least CLAG days old (a country cell 3 days old is often still empty — the card's
rule). Its benchmark (the owner's rule, as the card's, users in place of spend): per country and card age the median of cum_o ÷ n_o over its install days settled at the build's origin (X +
SETTLE ≤ O; n_o ≥ MIN_N; ≥ MIN_KEPT such days, else none at that age); the day's = Σ w × each country's benchmark, w =
its organic users share over the day's countries that have one at that age, beside the same countries' own per user
(both lines from one set), cv = that set's users ÷ the day's — at the card days 1 … 14 whatever the day has lived (the
page draws it ahead), past them where lived. A day a side's pack has as [X] (or not at all) is roi_build's own row of
it (_zrow; a Google Ads users' one on a day in their file's "unk": spend null — a file without "unk" as before).
  site/be_<key>_o.json.gz {"v", "key", "origin", "ages" (GRID through 30, then the 30-day columns the oldest day lived),
                           "days": [{"d", "age", "n" (organic users; null: not final yet), "r" (revenue USD at the ages,
                           AdMob-matched as the cells), "pu" (per user), "fin" (1 / 0), "s": {"pu" (the set's per user),
                           "b" (its benchmark per user), "cv"}, "dr": [country-days left out, their organic users] (only
                           when any)}]} (every install day with organic users or drift, oldest first; per-age lists
                           trailing nulls trimmed) — written only with a day in it; a failure costs only it (counted,
                           "be organic skipped: <Type>")
  dashboard["be"]["apps"][id] gains "org" (that file) only when written; its "v" then covers both files (the page fetches
  the Organic file with the app file's version: one build writes both).

run(dashboard, data_dir, out_dir, s, now) → HEADER_PATHS (["/be_*"], ONE splat rule) or [] (no app / a failure: the
files removed, no pointer). Never raises; any failure prints "be skipped: <ErrorType>" (the health banner) and one
app's costs only that app (counted). off(out_dir): the switch (BE_TAB=false). ONE counts-only line (pop_line); with
be_paid: + ", src p N a N, calib p yes|no, org N, org fail N" (+ ", paid failed N": apps whose Google Ads source failed).
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

from . import stage_clock as _sc
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
CALV = 4                             # calib.json content: 3 = with the shift's ranges + growth bound; 4 = a judged
                                     # country row past its range answered at the edge (_answers / _edge) (older: made again)
SHIFT_CV = 3                         # … the first content with the shift's parts: a remake that fails keeps one this new
                                     # shifting (an older one, or none, leaves the shift off)
CLAG = LAG + 1                       # a daily cell 3 days old is often still empty (a country's split lags: most
                                     # country cells dated 3 days ago carried no revenue yet, and a few small apps' own
                                     # rows — measured 15 Nov 2026): the shift reads a daily cell at least 4 days old
PACK_MIN = 1.0                       # a pack-gap date needs the app's final revenue of that date ≥ 1 USD (a smaller total
                                     # is noise: a ratio of two cents says nothing about a missing pack)
PACK_GAP = 0.35                      # … and the country packs' sum of it under 0.35 × the All rows' (GA4's cube folds a date
                                     # once, at D+3: it can be nearly empty while the app's All rows are whole)
FV = 2                               # the fits cache content: 2 = with each country's benchmark triple "bm" (older: refit)
SKIP_CC = frozenset(("--", "XX", "ZZ"))
# ⚖️ Google Ads users only (BE_PAID; see the module doc) and their complement, the Organic file
PPACK_RE = re.compile(r"^roi_[0-9a-f]{12}_p\d{2,3}\.json\.gz$")    # the Google Ads users' packs (roi_build.PAID_DIR)
ORG_RE = re.compile(r"^be_[0-9a-f]{12}_o\.json\.gz$")              # the Organic files
CALIB_P = "calib_p.json"             # the Google Ads users' calibration (src "p": made from its own apps only)
ORG_V = 1
NOT_SPLIT = "XX"                     # Google Ads' cost with no country (roi_build.NOT_SPLIT): no user, no revenue
OTOL_W = 1e-4                        # drift's rounding: the cells are written to 4 decimals (two values rounded once each
#                                      cross by one unit there; a 30-day column — ages past 30 — is rounded twice, on
#                                      top of its day-30 cell already written: two units) …
OTOL_K = 2.0                         # … ½ micro a GA4 row on each of the cell's days + 1 (fetch.ga4_cube's own rule) × the
#                                      AdMob scale the cells carry (≤ engine.value.K_CLAMP's 2) …
OTOL_R = 1e-6                        # … + 1 ppm of the cell
OBENCH = 13                          # the Organic benchmark ahead of a day it has not lived: the card days 1 … 14
K_APP = 16                           # a pack row's ≈ bit: a month of its revenue on the app's k (roi_build's k bits)
NAN = float("nan")                   # (a cell not final, in the Organic pass's compact arrays)
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
                 "sfv", "rbe", "dd", "kc", "kf")


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
        x.kc = x.kf = None                           # (the card reads cum / fin)
    else:
        x.cum = x.fin = x.dd = None
        at = dict(pts)                               # a small row (under $5 / 30 new users) is still a covered country's
        fa = _fin(r)                                 # row: its card days' cells (CARD_J) feed the card, nothing else
        x.kc = [None if at.get(GRID[j]) is None else round(at[GRID[j]], 4) for j in CARD_J]
        x.kf = [fa[j] for j in CARD_J]
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
    e hi], widened to the stored 6 decimals; None: no such day. A judged day outside it is answered at its edge (_edge);
    a smaller one is not (_answers)."""
    u = [r for r in rows if r.X + SETTLE <= O and _usable(r)]
    if not u:
        return None
    lo, hi = (lambda v: math.floor(v * 1e6) / 1e6), (lambda v: math.ceil(v * 1e6) / 1e6)
    return [lo(min(r.c for r in u)), hi(max(r.c for r in u)), lo(min(r.e for r in u)), hi(max(r.e for r in u))]


def _shifts(cal):
    """Does a calibration carry the shift's ranges and growth bound (cv ≥ SHIFT_CV)? A remake after CALV moved that
    fails keeps the last good one shifting, tried again every build until a new one is made."""
    v = (cal or {}).get("cv")
    return isinstance(v, int) and not isinstance(v, bool) and v >= SHIFT_CV


def _seen(g, x):
    """Whether a day's CPI and eCPM_fs lie inside a benchmark's learned range g (_rng; None: nothing learned) — K3's own
    chances only there (the curves answer a judged row past it too: _answers / _edge)."""
    return g is not None and g[0] <= x.c <= g[1] and g[2] <= x.e <= g[3]


def _answers(g, x):
    """Is a covered country's row answered that day? Its CPI and eCPM_fs are known, and they are inside the range its
    benchmark learned from (g), or the row is judged (≥ $5, ≥ 30 new users — _edge reads it past the range): a smaller
    row's CPI / eCPM_fs outside the range is a few installs' or impressions' noise, not a move, and on a day it alone is
    covered it would stand for the whole app — it stays "data kam", as before."""
    return x.c is not None and x.e is not None and (x.jd or _seen(g, x))


def _edge(g, x):
    """A day's CPI and eCPM_fs past the range its benchmark learned from (owner, 16 Nov 2026: "Cpi kitna bhi uppar jaye
    uspe vo rule mat lagao … benchmark se kitna plus hua he aur ecpm kitna benchmark se badla he"): the curve is read at
    the range's edge and moved by the ratio past it — ROAS = revenue ÷ spend, so a CPI twice the edge's halves it (half
    the edge's doubles it) and an eCPM_fs under the range lowers it as much. An eCPM_fs ABOVE the range moves it no further than the range's top: the
    back-test on every app's past days showed the later sessions do not keep such a first session (the ratio over-shot
    there; held at the top it did not) → (log CPI, log eCPM_fs) to read the curve at, and the log shift to add. Only a
    judged row is read past its range (_answers)."""
    c = min(max(x.c, g[0]), g[1])
    e = min(max(x.e, g[2]), g[3])
    return c, e, (min(x.e, g[3]) - e) - (x.c - c)


def curve_at(cf, g, x):
    """A country's curve for a day: curve_predict at its CPI / eCPM_fs, past its learned range g at the edge moved by
    the ratio (_edge) → (ages, log ROAS median, low, high), each non-decreasing in age."""
    c, e, d = _edge(g, x)
    ages, mid, lo, hi = curve_predict(cf, c, e)
    if d:
        mid, lo, hi = ([v + d for v in s] for s in (mid, lo, hi))
    return ages, mid, lo, hi


def _read(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _fday(S, r):
    """Adds one ROI row's FINAL daily revenue (its first r[5] cumulative cells: daily = d[a] − d[a−1], d[0] for a = 0)
    to S at its activity date (install day + a). Streaming: nothing about the row is kept."""
    d = r[4] if len(r) > 5 else None
    if not d or not isinstance(r[0], str):
        return
    n = min(int(r[5] or 0), len(d))
    X = date.fromisoformat(r[0]).toordinal()
    prev = 0.0
    for a in range(n):
        v = d[a]
        if not isinstance(v, (int, float)):
            break
        S[X + a] = S.get(X + a, 0.0) + v - (prev if a else 0.0)
        prev = v


def pack_gaps(S_all, S_cty, newest, fthru=None):
    """The activity dates (ordinals) on which the country packs lost revenue the All rows have: D ≤ newest − CLAG (the
    date's cells are final), the All rows' final revenue of it ≥ PACK_MIN, the packs' (every country row, "--" / "XX" /
    "ZZ" too — the All row includes them) under PACK_GAP × it. newest: ordinal. fthru (ordinal): the packs' own final edge
    (the cube folded through it): a later date is not folded yet, not a gap."""
    lim = newest - CLAG if fthru is None else min(newest - CLAG, fthru)
    return {D for D, v in S_all.items() if D <= lim and v >= PACK_MIN and S_cty.get(D, 0.0) < PACK_GAP * v}


def pack_gaps_p(S_ref, S_cty, newest, fthru=None, ref_newest=None):
    """⚖️ src "p": the activity dates (ordinals) on which the Google Ads users' packs lost revenue. Their All row is the
    same read as their packs (the paid cube's cells: a date folded near-empty sinks both, their ratio never moves), so
    the packs' FINAL daily revenue (S_cty) is held against an INDEPENDENT read — every user's All rows' final daily
    revenue (S_ref: ga4_cohort's exact store, re-read and whole): their share ρ[D] = S_cty[D] ÷ S_ref[D] on the dates D ≤
    newest − CLAG (≤ the packs' own final edge fthru, ≤ ref_newest − CLAG: both reads final there) with S_ref[D] ≥
    PACK_MIN. D is a gap when ρ[D] < PACK_GAP × the median ρ of the GAP_N dates before it that were not gaps (within 3 ×
    GAP_N days, ≥ 3 of them — _holes' rule: a long gap never sets its own baseline) and the packs usually carry ≥
    PACK_MIN of that date (median ρ × S_ref[D]: a share of a few cents says nothing). The share is the app's own (Google
    Ads users are 5 % of one app's revenue and 90 % of another's): only a fall from its own level is a gap."""
    lim = newest - CLAG if fthru is None else min(newest - CLAG, fthru)
    if ref_newest is not None:
        lim = min(lim, ref_newest - CLAG)
    out, ok = set(), []
    for D in sorted(D for D, v in S_ref.items() if D <= lim and v >= PACK_MIN):
        rho = S_cty.get(D, 0.0) / S_ref[D]
        prev = [q for x, q in ok[-GAP_N:] if x >= D - 3 * GAP_N]
        if len(prev) >= 3:
            m = _median(prev)
            if m > 0 and rho < PACK_GAP * m and m * S_ref[D] >= PACK_MIN:
                out.add(D)
                continue
        ok.append((D, rho))
    return out


def _nvp():
    """⚖️ fetch.ga4_nvr_paid's instance of ga4_nvr (the Google Ads users' first-session store: DIR, load_store)."""
    from .fetch import ga4_nvr_paid
    return ga4_nvr_paid.MOD


def load(out_dir, data_dir, key, fn, want_adm=False, paid=None, org=False):
    """One app → (newest, the All rows, {cc: rows}), spend > 0 only, by day — every day (the tab answers every judged
    install day). want_adm: (newest, app, cty, adm, gaps) — AdMob's daily revenue and the pack-gap dates (pack_gaps).
    paid: (folder, file) — ⚖️ src "p" (the module doc): the rows, packs, "newest" and final edge of roi_build's Google
    Ads users' file there, the first-session eCPM of fetch.ga4_nvr_paid's store; from the all-users ROI file fn: AdMob's
    daily revenue (AdMob has no source split) and its All rows — the pack gaps' independent read (pack_gaps_p). org
    (with paid): one more value at the end — the Organic pass's inputs (_OIn: the Google Ads users' cells collected here
    while their packs are read — each read once a build; None: a side without packs or edges, no Organic file)."""
    src_dir = out_dir if paid is None else paid[0]
    body = _read(os.path.join(src_dir, fn if paid is None else paid[1]))
    ab = body if paid is None else _read(os.path.join(out_dir, fn))      # (every user's ROI file)
    S_all, S_cty = {}, {}
    for r in ab.get("rows") or []:
        _fday(S_all, r)                          # (src "p": every user's All rows — the gaps' independent read)
    oi = _OIn.of(ab.get("cd") or {}, body) if paid is not None and org else None
    ref_nw = _od(ab.get("newest")) if paid is not None else None       # (every user's read: final through − CLAG)
    life = ab.get("life") if want_adm else None
    ab = None
    nvm = gv if paid is None else _nvp()
    st = nvm.load_store(os.path.join(data_dir, nvm.DIR, key + ".json.gz"))
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
    cd = (body.get("cd") or {}) if paid is None else {"packs": body.get("packs"), "fthru": body.get("fthru")}
    pre = PACK_RE if paid is None else PPACK_RE
    for pf, _ in (cd.get("packs") or []):
        if not isinstance(pf, str) or not pre.match(pf):
            raise ValueError("pack name")
        pk = _read(os.path.join(src_dir, pf))
        for cc, rows in pk["c"].items():
            if oi is not None:
                oi.add(cc, rows)                 # ⚖️ the Organic pass's Google Ads users' cells (its own failure: only it)
            if cc in SKIP_CC:
                for r in rows:
                    _fday(S_cty, r)          # (no country, but the All row includes them)
                continue
            ncc = nv_cc.get(cc) or {}
            for r in rows:
                _fday(S_cty, r)
                if len(r) < 14 or r[3] is None or r[3] <= 0:
                    continue
                v = ncc.get(r[0])
                e = v[0] / v[1] * 1000 if v and v[1] > 0 else None
                cty.setdefault(cc, []).append(_row(r, e, r[3] >= MIN_SP and (r[1] or 0) >= MIN_N))
        del pk
    for v in cty.values():
        v.sort(key=lambda r: r.X)
    newest = body.get("newest") or (app[-1].day if app else None)
    tail = (oi,) if paid is not None and org else ()
    if not want_adm:
        return (newest, app, cty) + tail
    del body
    adm = {}                              # AdMob's own revenue of every day (the ROI file's "life": [day, AdMob USD, …]):
    for e in life or []:                  # a GA4 hole is a date GA4 lost while AdMob did not
        try:
            if isinstance(e[1], (int, float)):
                adm[date.fromisoformat(e[0]).toordinal()] = float(e[1])
        except (TypeError, ValueError, IndexError):
            continue
    del life
    if not newest or not cd.get("packs"):
        return (newest, app, cty, adm, set()) + tail      # (no country packs: nothing to compare — no gap)
    try:
        ft = date.fromisoformat(cd["fthru"]).toordinal()
    except (KeyError, TypeError, ValueError):
        ft = None
    nw = date.fromisoformat(newest).toordinal()
    if paid is None:
        return newest, app, cty, adm, pack_gaps(S_all, S_cty, nw, ft)
    return (newest, app, cty, adm, pack_gaps_p(S_all, S_cty, nw, ft, ref_nw)) + tail


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


def km_median(obs):
    """The Kaplan–Meier median of [(time, event?)]: S(t) = Π (1 − d_i / n_i) over the event times t_i, n_i = the days at
    risk at t_i (every time ≥ t_i; a day censored at t_i is still at risk). The first event time with S ≤ 0.5; None when
    S never gets there (the median lies beyond what the data watched)."""
    ev = sorted({t for t, e in obs if e})
    if not ev:
        return None
    ts = sorted(t for t, _ in obs)
    s = 1.0
    for t in ev:
        n = len(ts) - bisect.bisect_left(ts, t)
        s *= 1.0 - sum(1 for tt, e in obs if e and tt == t) / n
        if s <= 0.5 + 1e-12:
            return t
    return None


def k3_fit(rows, O):
    """K3 at origin O on a country's usable days: the bot on the real-BE days, ≥ MIN_KEPT kept, the not-yet days as
    "BE > age so far" → {"beta", "s", "tmax" (the longest age the training set watched), "kept", "dropped", "cens",
    "bm" (the country's benchmark from this same training set: [median CPI, median eCPM_fs, the Kaplan–Meier median BE
    day or None, round(tmax)])} or None (uncovered)."""
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
    tmax = max(t for _, _, t in train)
    km = km_median([(t, k == "e") for _, k, t in train])
    bm = [math.exp(_median([r.c for r, _, _ in train])), math.exp(_median([r.e for r, _, _ in train])), km,
          round(tmax)]
    return {"beta": res[0], "s": res[1], "tmax": tmax, "kept": len(kept), "dropped": len(dropped), "cens": sum(cz),
            "bm": bm}


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
    """The daily fit at origin O → the fits cache body (rounded as stored: predict reads only this). Per country "bm" =
    [CPI, eCPM_fs, BE day | None, limit]: its benchmark from K3's own training set (the countries table's "B"; the card's
    benchmark is each country's curve median, "cv"[5])."""
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
                    "rng": g, "bm": [round(k3["bm"][0], 4), round(k3["bm"][1], 3), _r(k3["bm"][2], 1), k3["bm"][3]]}
    return {"v": V, "fv": FV, "origin": _iso(O), "fits": fits}


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
                if cc not in cov or not _answers(cov[cc][2], x):
                    continue
                k3, cf, g = cov[cc]
                b = k3["beta"]
                pa, mid, _, _ = curve_at(cf, g, x)                              # (past its range: at the edge)
                parts.append((x, pa, mid, b[0] + b[1] * x.c + b[2] * x.e if _seen(g, x) else None, k3))
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
                if x.jd and mu is not None:              # (K3's maps: only the days inside its range, as it answers)
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
                if cc not in cov or not _answers(cov[cc][2], x):
                    continue
                pa, mid, _, _ = curve_at(cov[cc][1], cov[cc][2], x)
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


def _pin(newest, app, cty, adm=None, gaps=None):
    """What predict needs of one app: every install day with spend (the judged ones get the model; the others only their
    real numbers), its countries' rows, AdMob's daily revenue and the pack-gap dates (load's, ordinals)."""
    rows = list(app)
    want = {r.day for r in rows}
    byday = {}
    for cc, rs in cty.items():
        for r in rs:
            if r.day in want:
                byday.setdefault(r.day, {})[cc] = r
    return newest, rows, byday, adm, frozenset(gaps or ())


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


def _bm(v):
    """A country's stored benchmark triple + limit → [CPI, eCPM_fs, BE day | None, limit]; None when missing / malformed
    (an old cache)."""
    ok = isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                     for x in (v[0], v[1], v[3])) and \
        (v[2] is None or (isinstance(v[2], (int, float)) and not isinstance(v[2], bool)))
    return list(v) if ok else None


def _cells(x, j):
    """A row's cumulative revenue and its FINAL cumulative revenue at card day j (an index of CARD_J, which is also the
    GRID index) — the judged rows' cum / fin, a small row's own card cells (kc / kf)."""
    if x.cum is not None:
        return x.cum[j], (x.fin[j] if x.fin else None)
    return (x.kc[j], x.kf[j]) if x.kc else (None, None)


def _card(r, cov, tot, gaps, nw):
    """The 14-day card of one install day at CARD_J: the owner's rule — each country's own median past ROAS, joined by
    the day's spend share, both lines from the SAME countries. S = the day's covered countries (small rows too) with a
    curve entry at every card day (one set for the whole card: a cumulative ROAS must not fall because the set changed).
    roas[j] = Σ cum ÷ Σ spend over S (null where a country of S has no cell at j yet); bench[j] = Σ spend × exp(its stored
    curve median at j) ÷ Σ spend; fin[j] = 1 when every country of S has a FINAL cell at j AND that date is at least CLAG
    days old (a country's cell 3 days old is often still empty); cv = S's spend ÷ the day's whole country spend; chk[j] =
    1 when a pack-gap date lies in [X, X + GRID[j]]. → (card | None, why): None when no card day has a value; why: "c" no
    covered country with a full curve, "r" their ROAS has not arrived."""
    S = []
    for cc, x, f, *_ in cov:
        ms = {e[0]: e[5] for e in f["cv"]}
        if all(j in ms for j in CARD_J):
            S.append((x, ms))
    sp = sum(x.sp for x, _ in S)
    if not S or sp <= 0:
        return None, "c"
    roas, bench, fin, chk = [], [], [], []
    for j in CARD_J:
        cl = [_cells(x, j) for x, _ in S]
        if all(c is not None for c, _ in cl):
            roas.append(_rr(sum(c for c, _ in cl) / sp))
            bench.append(_rr(sum(x.sp * math.exp(ms[j]) for x, ms in S) / sp))
            fin.append(1 if r.X + GRID[j] <= nw - CLAG and all(f is not None for _, f in cl) else 0)
        else:
            roas.append(None)
            bench.append(None)
            fin.append(0)
        chk.append(1 if any(r.X <= D <= r.X + GRID[j] for D in gaps) else 0)
    if all(v is None for v in roas):
        return None, "r"
    cvs = round(sp / tot, 4)
    return {"roas": roas, "bench": bench, "fin": fin, "cv": [None if v is None else cvs for v in roas], "chk": chk}, None


def predict(key, fc, cal, pin, sk=None):
    """One app's judged install days from its fits + the calibration → its be_<key>.json.gz body (see the module doc)."""
    newest, rows, byday = pin[:3]
    adm = pin[3] if len(pin) > 3 else None   # (AdMob's own daily revenue: tells a GA4 hole from a real outage)
    nw = date.fromisoformat(newest).toordinal()
    band = cal.get("band") or {}
    bandb = cal.get("bandb") or {}
    cbandb = cal.get("cbandb") or {}
    cmh = {H: _cal_xy((cal.get("cty") or {}).get(str(H))) for H in HS}         # (each map's arrays once, not per call)
    gaps = pin[4] if len(pin) > 4 else ()   # (pack-gap dates: the card's "data check")
    holes = _holes(rows, nw, adm)         # the calendar dates GA4 lost on every cohort while AdMob did not
    gr, cgr = _gq(cal.get("grow"), key, "app"), _gq(cal.get("grow"), key, "cty")
    ok = _shifts(cal)                     # the shift only with a calibration that has its ranges and bound (a failed first
    #                                       one after the shift shipped: the unshifted curve and its band, as before)

    def each():                           # every day's covered countries and its model curve, the shift's anchor (its
        for r in rows:                    # latest final grid age) — one day at a time
            cs = byday.get(r.day, {}) if r.jd else {}  # (a day under $5 / 30 new users: no model — only its real numbers)
            tot = sum(x.sp for x in cs.values()) or 1.0
            cov, unc, rest = [], [], 0.0
            for cc, x in sorted(cs.items(), key=lambda kv: -kv[1].sp):
                f = fc["fits"].get(cc)
                if not f or not _answers(f["rng"], x):
                    if x.sp / tot >= REST:
                        unc.append([cc, round(x.sp / tot, 4)])
                    else:
                        rest += x.sp / tot
                    continue
                cov.append((cc, x, f) + tuple(curve_at(f["cv"], f["rng"], x)))
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
            mu = b0 + b1 * x.c + b2 * x.e if _seen(f["rng"], x) else None     # (K3: only inside its range)
            pk = [iso_pred(cmh[H], p_le(mu, s_, H)) if cmh[H] and mu is not None else None
                  for H in HS]                   # (K3's chances: kept, not shown)
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
                         *days_, _bm(f.get("bm"))])
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
        out["card"], cw = _card(r, cov, tot, gaps, nw)
        if cw:
            out["cw"] = "j" if not r.jd else "k" if not ctys and not unc else cw   # why there is none (the page says it)
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


# ── ⚖️ Google Ads users only: an app's source, its Organic file (owner, 16 Nov 2026: "google ads and organic dono ka
# alag alag dekh saku esa kar do") ───────────────────────────────────────────────────────────────────────────────────

def _source(key, rbm, data_dir):
    """An app's source this build, be_paid on (the module doc) → ("p", (folder, file)): roi_build's Google Ads users'
    pass "ok" for it (rbm.PAID), its file in rbm.PAID_DIR and their first-session store there with its history read
    (fetch.ga4_nvr_paid: without it no country of theirs has an eCPM_fs — no model at all; a backfill not done yet would
    train the models on its recent days only) — or ("a", pw): the walk's progress for the page — or ("x", pw): "ok" but
    its file is not there (every user's, and the health banner: never a silent switch). Raises when the store cannot be
    read at all (the caller: that app only)."""
    e = (rbm.PAID if isinstance(rbm.PAID, dict) else {}).get(key)
    e = e if isinstance(e, dict) else {}
    st = e.get("st")
    if st == "ok":
        d, f = rbm.PAID_DIR, e.get("file")
        if not (isinstance(d, str) and d and f == "roi_%s_p.json.gz" % key and os.path.isfile(os.path.join(d, f))):
            return "x", {"st": "fail"}              # (its file gone: as a pass that failed)
        nm = _nvp()
        s = nm.load_store(os.path.join(data_dir, nm.DIR, key + ".json.gz"))
        if not isinstance(s, dict) or not s.get("days"):
            return "a", {"st": "off"}               # (nothing of their first-session reads yet: GA4_NVRP off, none yet,
            #                                          or a store of another version — read again by its fetch: their
            #                                          data not made this build — never "none", GA4 having none of them:
            #                                          their cube read them, its pass is "ok")
        if not (s.get("backfill") or {}).get("done"):
            return "a", {"st": "busy"}              # (their first-session history still being read back)
        return "p", (d, f)
    if st == "busy":
        return "a", dict({k: e[k] for k in ("from", "next") if k in e}, st="busy")
    return "a", {"st": st if st in ("none", "fail") else "off"}


def _otol(a, v):
    """How far two reads of one cell (age a; v: its larger value, USD) differ by rounding alone — the cube's own rule
    (fetch.ga4_cube: ½ micro a GA4 row + 1, + 1 ppm) on the cells as the packs carry them: the micros of its a + 1 days
    × the AdMob scale (≤ OTOL_K), written to 4 decimals (OTOL_W: two values rounded once each cross by one unit there;
    a 30-day column, any age past 30, is rounded twice — its day-30 cell was written first —: two units)."""
    return OTOL_W * (2 if a > 30 else 1) + OTOL_K * (0.5e-6 * (a + 1) + 1e-6) + OTOL_R * abs(v)


def _od(s):
    """An ISO day → its ordinal (None: not one)."""
    try:
        return date.fromisoformat(s).toordinal()
    except (TypeError, ValueError):
        return None


def _packs_of(folder, packs, pre):
    """(cc, rows) of every country of a pass's packs [[file, sha1-12]] — one pack in memory at a time (a country in two
    packs is no pack set of roi_build's: raises)."""
    seen = set()
    for pf, _ in packs or []:
        if not isinstance(pf, str) or not pre.match(pf):
            raise ValueError("pack name")
        pk = _read(os.path.join(folder, pf))
        for cc, rows in (pk.get("c") or {}).items():
            if cc in seen:
                raise ValueError("pack country")
            seen.add(cc)
            yield cc, rows
        del pk


def _ocells(r):
    """One pack row → (users, its FINAL cumulative revenue at the GRID ages: _fin); None for a short [X] (no user,
    nothing — the same as a day the pack never wrote). Raises on a row of no known shape."""
    if len(r) == 1:
        return None
    if len(r) < 14:
        raise ValueError("pack row")
    return int(r[1] or 0), tuple(_fin(r))


def _ranges_of(v):
    """[[first, last], …] inclusive ISO ranges (roi_build's _ranges) → their days (ordinals); None: no list (a file of
    the format before it); a malformed entry is no day."""
    if not isinstance(v, list):
        return None
    out = set()
    for e in v:
        a, b = (_od(e[0]), _od(e[1])) if isinstance(e, list) and len(e) == 2 else (None, None)
        if a is not None and b is not None and b - a <= 4000:
            out.update(range(a, b + 1))
    return out


def _ng_own(cd):
    """roi_build's verdict per activity month (every user's "cd" "ng" "m": [USD, its unp, "own" | "app"] — "own" when
    most of the month's named GA4 revenue is on an own / pooled k_c: AdMob's country report already placed the users
    GA4 has no country for in those countries) → {(year, month): …} of the "own" months; None: no verdicts written."""
    m = (cd.get("ng") or {}).get("m") if isinstance(cd.get("ng"), dict) else None
    if not isinstance(m, dict) or not m:
        return None
    out = set()
    for M, v in m.items():
        if isinstance(M, str) and len(M) == 7 and isinstance(v, list) and len(v) > 2 and v[2] == "own":
            try:
                out.add((int(M[:4]), int(M[5:7])))
            except ValueError:
                continue
    return out


def _all_own(lo, hi, own):
    """Is every activity day lo … hi (ordinals) in a month of `own`?"""
    a, b = date.fromordinal(lo), date.fromordinal(hi)
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        if (y, m) not in own:
            return False
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return True


def _once(X, cum, own):
    """A "--" / "ZZ" country-day's organic revenue at the GRID ages counted ONCE: each step between two known ages (its
    activity days X + the earlier age + 1 … X + the later age) left out when every one of its days is in an own month
    (_ng_own: AdMob booked those users under their real countries — inside the named countries' k_c), kept otherwise (a
    step across both kinds: its split is not measured — kept whole, as before). None where cum is."""
    out, drop, prev, last = [], 0.0, 0.0, -1
    for j, a in enumerate(GRID):
        v = cum[j]
        if v is None:
            out.append(None)
            continue
        if _all_own(X + last + 1, X + a, own):
            drop += v - prev
        prev, last = v, a
        out.append(v - drop)
    return out


class _OIn:
    """⚖️ What the Organic pass of one src "p" app reads besides every user's packs (organic()): both cubes' edges — ta /
    fa (every user's "cd": read / folded through), tp / fp (the Google Ads users' file's), nw (the older newest day: the
    ages), lim (the install days both read through) —, every user's packs, the Google Ads users' [X] rows' unknown
    spend days ("unk" of their file: None for a file without it) and "billed", own (_ng_own), and their cells (users, the final
    cumulative revenue at the GRID ages: _ocells) of every country × install day ≤ lim with something in it — added
    while load() reads their packs (each pack read once a build), held compactly (three arrays a country: an app's may
    wait for the day's calibration); err: what adding them raised (organic() raises it: only the Organic file lost)."""
    __slots__ = ("ta", "fa", "tp", "fp", "nw", "lim", "apacks", "unk", "billed", "own", "cells", "err")

    @classmethod
    def of(cls, cd, pb):
        """Every user's "cd" + the Google Ads users' file → an empty holder, or None: a side without packs or edges."""
        ta, fa, tp, fp = (_od(x) for x in (cd.get("thru"), cd.get("fthru"), pb.get("thru"), pb.get("fthru")))
        if not cd.get("packs") or not pb.get("packs") or None in (ta, fa, tp, fp):
            return None
        o = cls()
        o.ta, o.fa, o.tp, o.fp = ta, fa, tp, fp
        o.lim = min(ta, tp)                       # (the install days both cubes read through: a later one, no organic)
        o.nw = min(_od(cd.get("newest")) or ta, _od(pb.get("newest")) or tp)
        o.apacks = cd["packs"]
        o.unk, o.billed = _ranges_of(pb.get("unk")), bool(pb.get("billed", True))
        o.own = _ng_own(cd)
        o.cells, o.err = {}, None
        return o

    def add(self, cc, rows):
        """One country's Google Ads users' rows of a pack (a country in two packs, or a row of no known shape: err)."""
        if self.err is not None or cc == NOT_SPLIT:   # (Google Ads' cost with no country: no user, no revenue)
            return
        try:
            if cc in self.cells:
                raise ValueError("pack country")
            xs, ns, cs = array("l"), array("l"), array("d")
            for r in rows:
                X = _od(r[0] if r else None)
                if X is None:
                    raise ValueError("pack row")
                c = _ocells(r)
                if c is not None and X <= self.lim:
                    xs.append(X)
                    ns.append(c[0])
                    cs.extend(NAN if v is None else v for v in c[1])
            self.cells[cc] = (xs, ns, cs) if xs else None
        except Exception as e:
            self.err, self.cells = e, {}

    def pop(self, cc):
        """A country's cells → {X: (users, cells)} (let go here; {}: none)."""
        v = self.cells.pop(cc, None)
        if not v:
            return {}
        xs, ns, cs = v
        G = len(GRID)
        return {X: (ns[i], tuple(None if c != c else c for c in cs[i * G:(i + 1) * G])) for i, X in enumerate(xs)}

    def rest(self):
        """The countries not popped yet that have cells (sorted)."""
        return sorted(cc for cc, v in self.cells.items() if v)


def _org_in(out_dir, fn, paid):
    """organic() called on its own: _OIn from the two files, the Google Ads users' packs read here (the build hands
    load()'s, where each is read once)."""
    pb = _read(os.path.join(paid[0], paid[1]))
    oi = _OIn.of(_read(os.path.join(out_dir, fn)).get("cd") or {}, pb)
    if oi is not None:
        for pf, _ in pb.get("packs") or []:
            if not isinstance(pf, str) or not PPACK_RE.match(pf):
                raise ValueError("pack name")
            for cc, rows in (_read(os.path.join(paid[0], pf)).get("c") or {}).items():
                oi.add(cc, rows)
    return oi


def _xrow(oi, side, X, cc):
    """The row roi_build writes as [X] (or not at all) for a day of a side's pack — its own _zrow: no user, the cells 0
    as far as that cube read through, final as far as it folded through; the spend null on "--" and, on the Google Ads
    users' side, on a day in their file's "unk" (their [X] rows' days of unknown spend; a file without "unk": null, as
    before it) — as a pack row (_row_out)."""
    from . import roi_build as rbm
    th, ft = (oi.ta, oi.fa) if side == "a" else (oi.tp, oi.fp)
    Xd, td, fd = date.fromordinal(X), date.fromordinal(th), date.fromordinal(ft)
    if side == "p" and oi.unk is not None:
        return rbm._row_out(rbm._zrow(Xd, td, fd, X in oi.unk, cc, oi.billed))
    return rbm._row_out(rbm._zrow(Xd, td, fd, False, rbm.NO_CC))


class _OD:
    """One install day's Organic sums: n its organic users (a day not final for users: its unread sum, never written),
    c its country-days counted (cn the named ones), r[i] the named countries' revenue at GRID[i] (None: one of them not
    final there), x the same of "--" / "ZZ" (counted once: _once), k / u the country-days left out as drift and their
    organic users; per card
    age the benchmark set's users S, Σ users × benchmark B and revenue R (None: a country of the set not final there)."""
    __slots__ = ("n", "c", "cn", "r", "x", "k", "u", "S", "B", "R")

    def __init__(self, g):
        self.n = self.c = self.cn = self.k = self.u = 0
        self.r, self.x, self.S, self.B, self.R = [0.0] * g, [0.0] * g, [0] * g, [0.0] * g, [0.0] * g


def organic(out_dir, key, fn, paid, O, oi=None):
    """⚖️ One src "p" app's Organic file body (the module doc) — or None: a side without country packs or their edges,
    or no install day with organic users. fn: its all-users ROI file in out_dir ("cd": its packs, thru / fthru /
    newest); paid: (folder, file) of roi_build's Google Ads users' file (its packs, thru / fthru / newest, "unk"); O: the
    build's day (ordinal: the benchmark's settled days); oi: load()'s _OIn of the app (None: read here). Raises on a
    failure (the caller: no Organic file, counted)."""
    if oi is None:
        oi = _org_in(out_dir, fn, paid)
        if oi is None:
            return None
    if oi.err is not None:
        raise oi.err
    lim, nw, f0 = oi.lim, oi.nw, min(oi.fa, oi.fp)     # f0: users final through it (both cubes folded day 0)
    G, zc = len(GRID), {}

    def zero(side, X, cc):
        """A day a side's pack has as [X] or not at all (a country it never named) → (users, its final cells): _xrow."""
        k = (side, X, side == "p" and oi.unk is not None and X in oi.unk, cc == "--")
        z = zc.get(k)
        if z is None:
            z = zc[k] = (0, tuple(_fin(_xrow(oi, side, X, cc))))
        return z

    acc, W = {}, {}

    def one(cc, got):
        """One country's install days [(X, all-users (users, final cells), Google Ads users' (…))] → organic users and
        revenue into each day's sums (a drift: left out, counted); a real country's benchmark from its own organic days
        (settled at O), then its part of each of its final days' benchmark set."""
        kept, sk = [], cc in SKIP_CC
        for X, (na, ca), (np_, cp) in got:
            d = acc.get(X)
            if d is None:
                d = acc[X] = _OD(G)
            young = X > f0                          # (its day 0 not folded on both: its users not final, no drift test)
            cum, bad = [], not young and np_ > na   # (more Google Ads users than users: two reads apart)
            for i in range(G):
                if bad:
                    break
                va, vp = ca[i], cp[i]
                if va is None or vp is None:
                    cum.append(None)                # (not final on a side: no organic number there)
                    continue
                v = va - vp
                if v < 0:
                    if -v > _otol(GRID[i], max(va, vp)):
                        bad = True                  # DRIFT, never clamped
                        break
                    v = 0.0                         # (inside the rounding: rounding)
                cum.append(v)
            if bad:
                d.k += 1
                d.u += max(0, na - np_)
                continue
            no = na - np_
            d.n += no
            d.c += 1
            t = d.x if sk else d.r                  # ("--" / "ZZ": counted once — _once, or W below)
            d.cn += not sk
            for i, v in enumerate(_once(X, cum, oi.own) if sk and oi.own is not None else cum):
                if v is None:
                    t[i] = None
                elif t[i] is not None:
                    t[i] += v
            if not sk and no > 0 and not young:
                kept.append((X, no, cum))
        if not kept:
            return
        bench = []                              # the median per user of its own settled days with ≥ MIN_N organic users
        for i in range(G):
            v = [c[i] / no for X, no, c in kept if X + SETTLE <= O and no >= MIN_N and c[i] is not None]
            bench.append(_median(v) if len(v) >= MIN_KEPT else None)
        for X, no, cum in kept:
            d = acc[X]
            for i, b in enumerate(bench):
                if b is not None:
                    d.S[i] += no
                    d.B[i] += no * b
                    d.R[i] = None if cum[i] is None or d.R[i] is None else d.R[i] + cum[i]

    for cc, rows in _packs_of(out_dir, oi.apacks, PACK_RE):
        if cc == NOT_SPLIT:
            continue
        mine, got, named = oi.pop(cc), [], cc not in SKIP_CC
        for r in rows:
            X = _od(r[0] if r else None)
            if X is None:
                raise ValueError("pack row")
            if X > lim:
                continue
            a, p = _ocells(r), mine.pop(X, None)
            if named and a is not None and oi.own is None:      # (no per-month verdicts: the day's named revenue so
                w = r[8] if isinstance(r[8], (int, float)) and r[8] > 0 else 0.0   # far, its part on own / pooled
                #                                                                   k_c — bit 16 off — decides it)
                if w:
                    e = W.setdefault(X, [0.0, 0.0])
                    e[1] += w
                    if not (r[12] if isinstance(r[12], int) else 0) & K_APP:
                        e[0] += w
            if a is None and p is None:
                continue                            # (nothing on either side)
            got.append((X, a or zero("a", X, cc), p or zero("p", X, cc)))
        got += [(X, zero("a", X, cc), p) for X, p in sorted(mine.items())]     # days only the Google Ads side has
        one(cc, got)
        del got, mine
    for cc in oi.rest():                            # countries only the Google Ads side names
        one(cc, [(X, zero("a", X, cc), p) for X, p in sorted(oi.pop(cc).items())])
    out, top = [], 0
    for X in sorted(acc):
        d = acc[X]
        if d.n <= 0 and not d.k:
            continue                                # (no organic user that day, nothing left out)
        age, young = nw - X, X > f0
        w = W.get(X)                                            # (W: only without per-month verdicts — then a day
        if w is not None and w[1] > 0 and 2 * w[0] >= w[1]:     # whose named revenue is mostly on own / pooled k_c
            r = [None if not d.cn else v for v in d.r]          # leaves its "--" / "ZZ" revenue out whole)
        else:
            r = [None if not d.c or v is None or x is None else v + x for v, x in zip(d.r, d.x)]
        while r and r[-1] is None:
            r.pop()
        n = None if young else d.n
        e = {"d": _iso(X), "age": age, "n": n, "r": [_r(v, 4) for v in r],
             "pu": [None if v is None or not n or n <= 0 else round(v / n, 6) for v in r],
             "fin": [1 if v is not None and X + GRID[i] <= nw - CLAG else 0 for i, v in enumerate(r)]}
        ahead = [d.S[i] > 0 and (GRID[i] <= OBENCH or GRID[i] <= age) for i in range(G)]
        s = {"pu": [round(d.R[i] / d.S[i], 6) if d.S[i] > 0 and d.R[i] is not None and GRID[i] <= age else None
                    for i in range(G)],
             "b": [round(d.B[i] / d.S[i], 6) if ahead[i] else None for i in range(G)],
             "cv": [round(d.S[i] / d.n, 4) if ahead[i] else None for i in range(G)]}
        for v in s.values():
            while v and v[-1] is None:
                v.pop()
        e["s"] = s
        if d.k:
            e["dr"] = [d.k, d.u]
        out.append(e)
        top = max(top, age)
    if not out:
        return None
    return {"v": ORG_V, "key": key, "origin": _iso(O), "ages": [a for a in GRID if a <= 30 or a <= top], "days": out}


# ── the caches ──────────────────────────────────────────────────────────────────────────────────────────────────────

def cache_dir(data_dir):
    return os.path.join(data_dir, DIR)


def _fits_path(data_dir, key, src="a"):
    """An app's fits cache — src "a" (every user's rows): fits_<key>.json.gz; ⚖️ src "p" (Google Ads users'):
    fitsp_<key>.json.gz (the two never mix: an app that changes source refits from its own)."""
    return os.path.join(cache_dir(data_dir), "fits%s_%s.json.gz" % ("p" if src == "p" else "", key))


def _raw(body):
    """Sorted compact JSON bytes; NaN / ∞ raise (the page could not read them)."""
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")


def load_fits(data_dir, key, src="a"):
    """The cached fits of an app (None: none, unreadable or another version → refit); src: its source's cache."""
    try:
        f = _read(_fits_path(data_dir, key, src))
    except (OSError, ValueError, EOFError, zlib.error):
        return None
    ok = isinstance(f, dict) and f.get("v") == V and isinstance(f.get("origin"), str) and \
        isinstance(f.get("fits"), dict) and all(isinstance(v, dict) and isinstance(v.get("rng"), list) and
                                                len(v["rng"]) == 4 for v in f["fits"].values())
    return f if ok else None


def save_fits(data_dir, key, fc, src="a"):
    write_gz_stable(_fits_path(data_dir, key, src), _raw(fc))


def _calib_name(src):
    """A source's calibration file: calib.json (src "a"), ⚖️ calib_p.json (src "p": its own apps only)."""
    return CALIB_P if src == "p" else CALIB


def load_calib(data_dir, src="a"):
    """calib.json (None: none or unreadable). A file whose maps are missing is no calibration. src: its source's."""
    try:
        with open(os.path.join(cache_dir(data_dir), _calib_name(src)), encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        return None
    ok = isinstance(c, dict) and c.get("v") == V and isinstance(c.get("built"), str) and \
        all(isinstance(c.get(k), dict) for k in ("cty", "pit", "band"))
    return c if ok else None


def save_calib(data_dir, cal, src="a"):
    """Sorted JSON, written only when it changed (atomic). src: its source's file."""
    path = os.path.join(cache_dir(data_dir), _calib_name(src))
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
        if (APP_RE.match(nm) or ORG_RE.match(nm)) and nm not in keep:      # (⚖️ the Organic files too)
            try:
                os.remove(os.path.join(out_dir, nm))
            except OSError:
                pass


def _fail(e, step="be"):
    print("%s skipped: %s" % (step, type(e).__name__), file=sys.stderr)


def _tried_p(data_dir):
    """⚖️ calib_p.json while no Google Ads users' calibration exists — the stub {"v", "tried", "apps"}: the UTC day their
    first one was tried and found no covered country at any month start (too few of their breakeven days), and the apps
    it was tried with (load_calib refuses it: no maps) — or None."""
    try:
        with open(os.path.join(cache_dir(data_dir), CALIB_P), encoding="utf-8") as f:
            c = json.load(f)
    except (OSError, ValueError):
        return None
    return c if isinstance(c, dict) and c.get("v") == V and isinstance(c.get("tried"), str) else None


def run(dashboard, data_dir, out_dir, s=None, now=None):
    """This build's files → HEADER_PATHS, or [] (no app / a failure: the files removed, no pointer). Never raises.
    ⚖️ be_paid (the module doc): each app's source first (_source; its own try); the Google Ads users' apps as one pass
    of their own with their own caches and calibration (phase "p": an app whose Google Ads source fails there, or that
    has no calibration of them yet, goes on as src "a"), then every other app exactly as without the switch (phase "a",
    its calib.json stamped with the mode it was made in)."""
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
        paid = bool((s or {}).get("be_paid"))     # ⚖️ BE_PAID — off: not a byte of anything changes (no "src", no Organic)
        loc, pw, orgs, bodies = {}, {}, {}, {}
        n = {"refit": 0, "fail": 0, "ec": 0, "ec_fail": 0, "ec_stale": 0, "pfail": 0, "org_fail": 0}
        if paid:
            from . import roi_build as rbm       # (its PAID / PAID_DIR: run_uninstall ran its pass earlier, this process)
            for aid, key, _ in apps:
                try:
                    k, v = _source(key, rbm, data_dir)
                except Exception as e:          # its source not told (a store or module that cannot be read): that app
                    n["pfail"] += 1             # only — every user's, counted and said
                    pw[aid] = {"st": "fail"}
                    _fail(e, "be paid")
                    continue
                if k == "p":
                    loc[aid] = v
                else:
                    pw[aid] = v
                if k == "x":                    # its pass "ok", its file gone: every user's, counted and said
                    n["pfail"] += 1
                    print("be paid skipped: FileNotFoundError", file=sys.stderr)
        bec = None
        if (s or {}).get("ga4_cecpm_use") and (s or {}).get("ga4_cecpm"):   # the card's eCPM index (be_ecpm,
            from . import be_ecpm as bec                        # GA4_CECPM_USE with its reads on): off, nothing of it is
            #                                                     read or written

        def _predict(aid, key, fc, pin, cal, src):
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
            if src == "p":                                      # ⚖️ the Google Ads users' file — its eCPM card stays
                body["src"] = "p"                               # every user's read ("ecs": the page's "saare users")
                for d in body["days"]:
                    if "ec" in d:
                        d["ecs"] = "a"
            elif paid:
                body["src"], body["pw"] = "a", pw.get(aid) or {"st": "off"}
            unc = {cc for cs in pin[2].values() for cc in cs} - set(fc["fits"])      # (the folded ones too)
            bodies[aid] = (key, fc, body, len(unc))

        def _org(aid, key, fn, oi):
            """⚖️ A src "p" app's Organic file — only once its src "p" body exists (held as bytes: written with it); oi:
            load()'s inputs (None: a side without packs or edges, no file). Its own try: a failure costs only it. Timed
            as its own child of the tab (stage_clock "be_organic", summed over the apps: measure only)."""
            try:
                with _sc.stage("be_organic"):
                    ob = organic(out_dir, key, fn, loc[aid], O, oi) if oi is not None else None
                if ob is not None:
                    orgs[aid] = (PREFIX + key + "_o.json.gz", _raw(ob))
                del ob
            except Exception as e:
                orgs.pop(aid, None)
                n["org_fail"] += 1
                _fail(e, "be organic")

        def phase(src, group):
            """One source's apps → (its calibration, made this build?, [apps that go on as src "a": their Google Ads
            source failed, or no calibration of them yet]). src "a" with be_paid off: the step exactly as it was before
            the switch."""
            pa = src == "p"
            old = load_calib(data_dir, src)
            held, back, bad = [], [], set()
            if pa and old is None:                              # ⚖️ no Google Ads users' calibration yet: tried today
                tr = _tried_p(data_dir)                         # with these same apps and too few of their days → a
                if tr is not None and tr["tried"] == today and \
                        {k for _, k, _ in group} <= set(tr.get("apps") or ()):   # state: every user's ("cal"), nothing
                    for aid, key, fn in group:                  # of them read or tried again today
                        pw[aid] = {"st": "cal"}
                        back.append((aid, key, fn))
                    return None, False, back
            mine = pa or old is None or bool(old.get("bp")) == paid    # (calib.json made in this mode? "bp": with BE_PAID)
            need = old is None or old.get("cv") != CALV or (old.get("tried") or old["built"]) != today or not mine
            A, C = [], []                                       # (need: the first build of the UTC day, an older
            RB, CB, SKL, GA, GC, GK = {}, {}, {}, {}, {}, {}    # calibration's content, or one of the other mode)
            gq0 = (old or {}).get("grow") if mine else None     # (the other mode's growth bound: never)
            cal = old

            def lose(aid, key, fn, e=None, st="fail", count=True):     # ⚖️ an app's Google Ads source failed (or has no
                n["pfail"] += count                             # calibration yet): it goes on as src "a" (a failure:
                pw[aid] = {"st": st}                            # counted, its health line)
                back.append((aid, key, fn))
                if e is not None:
                    bad.add(key)
                    _fail(e, "be paid")

            for aid, key, fn in group:
                try:
                    fc = load_fits(data_dir, key, src)
                    refit = fc is None or fc["origin"] != today or fc.get("fv") != FV     # (fv: the benchmark triple)
                    oi = None
                    if pa:                                      # (oi: the Organic pass's inputs, collected while its
                        newest, app, cty, adm, gaps, oi = load(out_dir, data_dir, key, fn, True, loc[aid], True)   # packs
                    else:                                       # are read)
                        newest, app, cty, adm, gaps = load(out_dir, data_dir, key, fn, True)
                    if not newest:
                        if pa:                                  # (nothing of its Google Ads users: every user's)
                            pw[aid] = {"st": "none"}
                            back.append((aid, key, fn))
                        continue
                    if refit:
                        fc = fit(app, cty, O)
                        save_fits(data_dir, key, fc, src)
                        n["refit"] += 1
                    if bec is not None and (refit or fc.get("ec_v") != bec.stamp()):
                        try:                                    # the eCPM benchmark: with the day's fit (once; again
                            m = bec.load(data_dir, key, cty)    # when its rule changed)
                            if m is not None:
                                fc["ec"], fc["ec_v"] = bec.bench(cty, m, O, app), bec.stamp()
                                fc["ec_h"] = not m.get("done")  # (made while GA4's history was being read)
                                save_fits(data_dir, key, fc, src)
                            del m
                        except Exception as e:
                            n["ec_fail"] += 1
                            bec._fail(e)
                    if need:
                        F = {}                                 # (one fit per month start, shared by the two back-tests)
                        a_, c_ = backtest(key, newest, app, cty, F)
                        A += a_
                        C += c_
                        rb, cb, sk_, au_, n0, ga, gc = asof(key, newest, app, cty, F, gq0)
                        for E, e in ((RB, rb), (CB, cb), (GA, ga), (GC, gc)):
                            for kk, v in e.items():
                                E.setdefault(kk, array("d")).extend(v)
                        SKL[key] = skill2(sk_, au_, n0)
                        GK[key] = growth(ga, gc)              # (its own growth: its bound where it has enough days)
                        del F, rb, cb, sk_, au_, ga, gc
                    pin = _pin(newest, app, cty, adm, gaps)
                    del app, cty
                    if not pin[1]:
                        continue
                    if need:
                        held.append((aid, key, fn, fc, pin, oi))   # (answered once the calibration is made)
                    else:
                        _predict(aid, key, fc, pin, cal, src)
                        if pa:
                            _org(aid, key, fn, oi)             # ⚖️ its Organic file, now that its file exists
                    del oi
                except Exception as e:                       # one app's failure costs that app only (counted) — ⚖️ a
                    if pa:                                   # src "p" one's only its Google Ads source
                        lose(aid, key, fn, e)
                    else:
                        n["fail"] += 1
                        _fail(e)
            ran = False
            if need and pa and len(back) == len(group):
                need = False                             # (⚖️ every Google Ads users' app went on as every user's:
            if need:                                     # no app of this source this build — none of it made)
                thin = not C or not any(x.get("a") for x in A)
                try:
                    if thin and pa:                      # ⚖️ too few Google Ads users' breakeven days for a calibration:
                        if old is None:                  # a state — the stub (tried again tomorrow, or with an app not
                            save_calib(data_dir, {"v": V, "tried": today,    # tried: new, or one that raised), its apps
                                                  "apps": sorted({k for _, k, _ in group} - bad)}, src)   # every user's
                            for aid, key, fn, _, _, _ in held:
                                lose(aid, key, fn, st="cal", count=False)
                            held = []
                        else:                            # (the last one stays, as a failed remake: tried tomorrow)
                            cal = dict(old, tried=today)
                            if SKL and _shifts(old):
                                cal["skill"] = SKL
                            save_calib(data_dir, cal, src)
                    else:
                        if thin:
                            raise ValueError("empty back-test")      # (every app failed or unusable: not a calibration)
                        cal = calibrate(A, C, O, RB, CB, GA, GC)
                        cal["skill"] = SKL
                        cal["grow"]["apps"] = {k: v for k, v in GK.items() if v.get("app") or v.get("cty")}
                        if paid and not pa:
                            cal["bp"] = 1                # ⚖️ made with BE_PAID on: from its src "a" apps only
                        save_calib(data_dir, cal, src)
                        ran = True
                except Exception as e:                       # the last good calibration stays (tried again tomorrow)
                    _fail(e, "be paid" if pa else "be")
                    if old is None:
                        if not paid:
                            raise NoCalib()
                        for aid, key, fn, _, _, _ in held:   # ⚖️ be_paid: no calibration yet of this source costs
                            if pa:                           # only its apps — a Google Ads users' one goes on as src
                                lose(aid, key, fn, st="cal")     # "a" (tried again the next build), an every-user one
                            else:                                # has no file this build (counted), the other source's
                                n["fail"] += 1                   # files stand
                        held = []
                    else:
                        cal = dict(old, tried=today)         # (no cv stamped: a calibration without the shift's parts
                        if SKL and _shifts(old):             # stays unshifted and is tried again; over one that has
                            cal["skill"] = SKL               # them, this build's own skill — asof() / skill2() ran
                        #                                      before; an older content than CALV is tried again every
                        if paid and not pa:                  # build; ⚖️ stamped with this build's mode: a failed
                            cal["bp"] = 1                    # remake is tried again tomorrow, as any)
                        elif not pa:
                            cal.pop("bp", None)
                        save_calib(data_dir, cal, src)
                del A, C, RB, CB, GA, GC, GK
                for aid, key, fn, fc, pin, oi in held:
                    try:
                        _predict(aid, key, fc, pin, cal, src)
                    except Exception as e:
                        if pa:
                            lose(aid, key, fn, e)
                        else:
                            n["fail"] += 1
                            _fail(e)
                        continue
                    if pa:
                        _org(aid, key, fn, oi)               # ⚖️ its Organic file, now that its file exists
                held = None
            return cal, ran, back

        cals, ran, back = {}, {}, []
        grp = [x for x in apps if x[0] in loc]
        if grp:                                          # ⚖️ the Google Ads users' apps first: one whose source fails
            cals["p"], ran["p"], back = phase("p", grp)  # there joins the others, every user's
        grp = sorted([x for x in apps if x[0] not in loc] + back, key=lambda x: (x[1], x[0]))
        if grp:
            cals["a"], ran["a"], _ = phase("a", grp)
        del grp, back
        if bec is not None and n["ec_stale"]:                   # GA4's reads stopped for an app: the banner, once
            print("be ecpm skipped: StaleWarning", file=sys.stderr)
        os.makedirs(out_dir, exist_ok=True)
        ptr, keep, nd, cov, unc = {}, set(), 0, 0, 0
        ns = {"p": 0, "a": 0, "org": 0}
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
            og = orgs.pop(aid, None) if body.get("src") == "p" else None   # ⚖️ its Organic file: src "p" only, written
            if og is not None:                                             # with its file; "v" then covers both
                try:
                    write_gz_stable(os.path.join(out_dir, og[0]), og[1])
                    og = (og[0], hashlib.sha1(og[1]).digest())
                except Exception as e:
                    og = None
                    n["org_fail"] += 1
                    _fail(e, "be organic")
            ptr[aid] = {"key": key, "file": fn, "v": hashlib.sha1(raw + og[1] if og else raw).hexdigest()[:12],
                        "n": len(days), "cov": days[-1]["cov"] if days else None}
            if og:
                keep.add(og[0])
                ptr[aid]["org"] = og[0]
                ns["org"] += 1
            if paid:
                ns["p" if body.get("src") == "p" else "a"] += 1
            nd += len(days)
            cov += len(fc["fits"])
            unc += nu
        _clean(out_dir, keep)
        LINE = "be: apps %d, days %d, covered %d, uncovered %d, refit %s, calib %s%s%s%s" % (
            len(ptr), nd, cov, unc, "yes" if n["refit"] else "no", "yes" if ran.get("a") else "no",
            (", failed %d" % n["fail"]) if n["fail"] else "",
            (", ecpm apps %d, ecpm failed %d, ecpm stale %d" % (n["ec"], n["ec_fail"], n["ec_stale"]))
            if bec is not None else "",
            (", src p %d a %d, calib p %s, org %d, org fail %d%s" % (
                ns["p"], ns["a"], "yes" if ran.get("p") else "no", ns["org"], n["org_fail"],
                (", paid failed %d" % n["pfail"]) if n["pfail"] else "")) if paid else "")
        if not ptr:
            return []
        dashboard["be"] = {"v": V, "origin": today, "calib": (cals.get("a") or cals.get("p") or {}).get("built"),
                           "apps": ptr}
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
