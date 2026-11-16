"""⚖️ Breakeven — the D0 … D30 cells of GOOGLE ADS USERS only (owner, 16 Nov 2026: "haan sirf google ads wale users se
karo · google ads and organic dono ka alag alag dekh saku esa kar do"; on the Google Ads users' All row: "pakka hi hota
he aur data hota hi he" — real data only). Why: the Google Ads users' All row (the app level of the Breakeven tab) was
the sum of the paid cohort cube's country cells (fetch.ga4_cube_paid). GA4's own response metadata, read on the
busiest app (fetch/ga4_flag_probe.py), says GA4 answers any read that holds install day × country together — the
cube's read, also with one country, one install day or the paid filter — from a sample on its busy days, while the
two-dimension reads (date × firstSessionDate, this store's shape, and date × countryId) come back whole. Every user's
All row comes from fetch.ga4_cohort's 2-D read; the Google Ads users' All row needs the same read of theirs — never
the cube's sampled cells summed.

GA4 marks those users by the FIRST-USER channel group: firstUserDefaultChannelGroup in ("Cross-network", "Paid Search")
— the owner's grouping (fetch.ga4_paid; the filter the cube's probe measured, fetch/ga4_paid_probe.py).

The mechanism — the SAME code as fetch/ga4_cohort.py, reused as it is: MOD is a second instance of that module
(ga4_paid.instance: its own module globals; never a copy, never a refactor), so the backfill from the history start,
the refresh of the recent days, a block with "(other)" read again day by day (the cube's split by install-day halves,
the day's every-install-day read when an in-list hid "(other)"), the "lo" / "lf" marks and the history check are
ga4_cohort's own, and EVERY one of their GA4 reads (each page too) carries one more filter expression, the paid in-list
(its client: ga4_paid.App — AND-ed after each read's own filters). What ga4_cohort's docstring says of its reads, files
and rules holds here word for word, but:
  * the store: data/ga4_cohort_paid/<key>.json.gz (+ <key>.old.json.gz, the older install days) in the private repo
    (key = ga4_uninstall.file_key(app id), as ga4_cohort's) — ga4_cohort's exact format — and
    data/ga4_cohort_paid/state.json; nothing of ga4_cohort's own store is read or written;
  * its knob (env, read at import; unset or empty: the default; the build step passes it from the repo variable of its
    name) — GA4_COHORTP_MAX_CALLS: an app's GA4 calls a run (ga4_cohort's MAX_CALLS). Everything else is ga4_cohort's
    (the block, the recent window and its refresh hours, the day's split cap, the history check);
  * its budget: the build's (GA4_COHORTP_BUDGET_SEC), else BUDGET_SEC (ga4_cohort's);
  * its quota: Screens' stricter floors (ga4_paid.App) — the build runs it after every live GA4 step and the Google
    Ads users' first-session read, BEFORE their cohort cube (a light read: about app age / 30 calls once, then a block
    an app every few hours — the cube's long walk never leaves it a property already under those floors), so it takes
    only what the live steps leave, in this build and the next;
  * a stuck app (ga4_paid.streak: failing FAIL_LINE runs in a row — ga4_cohort itself retries a failed app every
    RETRY_HOURS and never counts it) → counts "stuck": the build prints the health banner's line.
roi_build's Google Ads users' pass makes their All rows from this store (ga4_cohort's All-row rule: its own
completeness, its "lo" / "lf" marks) once its backfill is done and a refresh has read the recent days; until then the
pass is "busy" with this store's progress. Switched by GA4_COHORTP. Never raises; never prints. PUBLIC LOG: counts only
— log_line ("ga4 cohort paid: apps …", ga4_cohort's counts) never names an app, id, date, country or amount. The build
reads the store through MOD (ga4_cohort's own readers: store_path, load_store) — no other API here.
"""
import os
from datetime import datetime, timezone

from . import ga4_cohort
from . import ga4_paid


def _env(name, default, kind=int):
    """A knob from the environment (unset or empty: the default) — read once, at import (as ga4_cohort's own)."""
    return kind(os.environ.get(name) or default)


MOD = ga4_paid.instance(ga4_cohort, "admob_iq.fetch._ga4_cohort_paid_impl", DIR="ga4_cohort_paid", App=ga4_paid.App,
                        NAME="ga4 cohort paid", MAX_CALLS=_env("GA4_COHORTP_MAX_CALLS", ga4_cohort.MAX_CALLS))
BUDGET_SEC = MOD.BUDGET_SEC


def refresh_all(cfg, data_dir, apps, now=None, clock=None, budget=None):
    """ga4_cohort's run (ga4_cohort.refresh_all) on the paid store, every read held to Google Ads users, then the stuck
    rule (ga4_paid.streak) → {"counts" (+ "stuck"), "apps": {app id: fetched|fresh|failed|deferred|waiting}}
    (+ "error"). now None: the clock's UTC now (ga4_cohort's own default, taken here: the stuck rule's run time); clock
    None: the monotonic clock; budget None / 0: BUDGET_SEC. Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    return ga4_paid.streak(MOD, data_dir, MOD.refresh_all(cfg, data_dir, apps, now, clock,
                                                          budget=budget or BUDGET_SEC), now)


def log_line(status):
    """The build log's ONE line for this step — counts only ("ga4 cohort paid: apps …")."""
    return MOD.log_line(status)
