"""⚖️ Breakeven — the cohort cube of GOOGLE ADS USERS only (owner, 16 Nov 2026: "haan sirf google ads wale users se
karo · google ads and organic dono ka alag alag dekh saku esa kar do"; "haan yahi chahiye, shuru karo"; "haan pehle
google ads organic wala karo"). Why: the Breakeven tab's ROAS is ALL new users' cohort revenue ÷ the Google Ads spend —
when the spend drops, organic users keep coming, and their revenue on a tiny spend made an early breakeven that never
was. The tab needs the revenue of the users Google Ads brought: their own cohort cube, read from GA4 itself — never a
split of totals.

GA4 marks those users by the FIRST-USER channel group: firstUserDefaultChannelGroup in ("Cross-network", "Paid Search")
— the owner's grouping (fetch.ga4_paid). Measured first (fetch/ga4_paid_probe.py, the cube's own request shape with that
filter): GA4 accepts the filtered read, it adds up with its complement to the unfiltered one, and its paid new users
match the Google Ads installs; the probe measured the filtered read whole on most apps — on the busiest ones GA4 flags
it as it flags the cube's own read ("(other)", dataLossFromOtherRow, sampling), which the cube's adaptive read (each day
alone, the recursive split, the day's own total) already handles.

The mechanism — the SAME code as fetch/ga4_cube.py, reused as it is: MOD is a second instance of that module
(ga4_paid.instance: its own module globals; never a copy, never a refactor), so the walk, the hot days, the adaptive
split, the day's total, the fold guard and the refold, and q's whole reads are the cube's own, and EVERY one of their
GA4 reads (each page too) carries one more filter expression, the paid in-list (its client: ga4_paid.App — AND-ed after
each read's own filters). What the cube's docstring says of its reads, files and rules holds here word for word, but:
  * the store: data/ga4_cube_paid/<key>/ in the private repo (key = ga4_uninstall.file_key(app id), as the cube's) —
    the cube's exact formats: the activity months <YYYY-MM>.json.gz, the head hot.json.gz, q's <YYYY-MM>.q.json.gz —
    and data/ga4_cube_paid/state.json; nothing of the cube's own store is read or written;
  * users OFF (U_ON / U_USE false: no u file, no users fill — the Breakeven tab reads revenue and installs only, and
    the users fills' GA4 calls are saved);
  * the repair OFF by default (GA4_CUBEP_REPAIR_CALLS, REPAIR_CALLS 0: a fresh walk already folds every day with the
    current split version — nothing to repair);
  * its own knobs (env, read at import; unset or empty: the default; the build step passes each from the repo variable
    of its name) — GA4_CUBEP_MAX_CALLS: an app's GA4 calls a run (the cube's MAX_CALLS); GA4_CUBEP_Q_CALLS /
    GA4_CUBEP_Q_SEC: q's history fill a run over every app (120 calls / 20 s: the cube's defaults, never its
    GA4_CUBE_Q_* setting); GA4_CUBEP_RF_CALLS: the calls a run may start refold days with (30; 0 = off — the cube's
    GA4_CUBE_RF_CALLS is never its own); GA4_CUBEP_REPAIR_CALLS (above). Everything else is the cube's — its module
    defaults and its GA4_CUBE_* env (the fold guard, q's settle and retry rules, the caps);
  * its budget: the build's (GA4_CUBEP_BUDGET_SEC), else BUDGET_SEC (the cube's); GA4_CUBEP_WORKERS: the properties
    read side by side (the cube's WORKERS unless set; each property has its own GA4 quota, so more only shortens a long
    history backfill — the owner, 16 Nov 2026: "fast karo aaj hi");
  * its quota: Screens' stricter floors (ga4_paid.App) — the build runs it after every other GA4 step (the Google Ads
    users' two light reads before it: fetch.ga4_nvr_paid, fetch.ga4_cohort_paid), so it takes only what they leave, in
    this build and the next (the paid history's backfill never starves a live feature);
  * a stuck app (ga4_paid.streak: failing FAIL_LINE runs in a row — the cube itself retries a failed app every
    RETRY_HOURS and never counts it) → counts "stuck": the build prints the health banner's line.
Switched by GA4_CUBEP. Never raises; never prints. PUBLIC LOG: counts only — log_line ("ga4 cube paid: apps …", the
cube's counts) never names an app, id, date, country or amount. The build reads the store through MOD (the cube's own
readers: months, load_head, load_q …) — no other API here.
"""
import os
from datetime import datetime, timezone

from . import ga4_cube
from . import ga4_paid


def _env(name, default, kind=int):
    """A knob from the environment (unset or empty: the default) — read once, at import (as the cube's own)."""
    return kind(os.environ.get(name) or default)


MOD = ga4_paid.instance(ga4_cube, "admob_iq.fetch._ga4_cube_paid_impl", DIR="ga4_cube_paid", APP=ga4_paid.App,
                        NAME="ga4 cube paid", U_ON=False, U_USE=False,
                        REPAIR_CALLS=_env("GA4_CUBEP_REPAIR_CALLS", 0),
                        MAX_CALLS=_env("GA4_CUBEP_MAX_CALLS", ga4_cube.MAX_CALLS),
                        Q_CALLS=_env("GA4_CUBEP_Q_CALLS", 120),
                        Q_SEC=_env("GA4_CUBEP_Q_SEC", 20, float),
                        RF_CALLS=_env("GA4_CUBEP_RF_CALLS", 30))
BUDGET_SEC = MOD.BUDGET_SEC
WORKERS = max(1, _env("GA4_CUBEP_WORKERS", ga4_cube.WORKERS))     # properties read side by side (each its own quota)


def refresh_all(cfg, data_dir, apps, now=None, clock=None, budget=None):
    """The cube's run (ga4_cube.refresh_all) on the paid store, every read held to Google Ads users, then the stuck
    rule (ga4_paid.streak) → {"counts" (+ "stuck"), "apps": {app id: fetched|fresh|failed|deferred|waiting}}
    (+ "error"). now None: the clock's UTC now (the cube's own default, taken here: the stuck rule's run time);
    budget None / 0: BUDGET_SEC; WORKERS properties side by side. Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    return ga4_paid.streak(MOD, data_dir, MOD.refresh_all(cfg, data_dir, apps, now, clock, budget=budget or BUDGET_SEC,
                                                          workers=WORKERS), now)


def log_line(status):
    """The build log's ONE line for this step — counts only ("ga4 cube paid: apps …")."""
    return MOD.log_line(status)
