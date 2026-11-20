"""⚖️ Breakeven — the FIRST-SESSION eCPM of GOOGLE ADS USERS by country (owner, 16 Nov 2026: "haan sirf google ads wale
users se karo · google ads and organic dono ka alag alag dekh saku esa kar do"; "haan pehle google ads organic wala
karo"). The Breakeven model's eCPM_fs — the install day's first-session eCPM by country — comes from fetch.ga4_nvr's
"c" read (its "new" rows); the Google Ads view needs the first session of the users Google Ads brought, not of every new
user: the same read held to them (fetch.ga4_cube_paid reads their cohort revenue the same way).

GA4 marks those users by the FIRST-USER channel group: firstUserDefaultChannelGroup in ("Cross-network", "Paid Search")
— the owner's grouping (fetch.ga4_paid; the filter the cube's probe measured, fetch/ga4_paid_probe.py).

The mechanism — the SAME code as fetch/ga4_nvr.py, reused as it is: MOD is a second instance of that module
(ga4_paid.instance: its own module globals; never a copy, never a refactor) whose PARTS is ("c",) — ONLY the country
read, ONE call a range:
  c   date × newVsReturning × countryId → totalAdRevenue, eventCount   (eventName == ad_impression)
(the ad-unit "u" and sessions "s" reads are not needed: no call is made for them), every read (each page too)
carrying the paid in-list after its own filters (its client: ga4_paid.App). What ga4_nvr's docstring says of the
recent window, the lone read again of a final day still marked sampled ("rr"), the backfill newest first and its merge
(a part read alone kept unless the chunk's is better: whole > thresholded > sampled) holds here with "c" alone, but:
  * the store: data/ga4_nvr_paid/<key>.json.gz in the private repo (key = ga4_uninstall.file_key(app id), as ga4_nvr's)
    — ga4_nvr's format, each day {"c": [[nvr, cc, revenue, impressions], …]} only; "mark" / "mp" (its "c" flag only) /
    "rr" / "backfill" as ga4_nvr's — and data/ga4_nvr_paid/state.json; nothing of ga4_nvr's own store is touched;
  * its knob (env, read at import; unset or empty: the default; the build step passes it from the repo variable of its
    name) — GA4_NVRP_MAX_CALLS: an app's GA4 calls a run (ga4_nvr's MAX_CALLS). Everything else is ga4_nvr's (the
    window, its refresh hours, the chunk);
  * its budget: the build's (GA4_NVRP_BUDGET_SEC), else BUDGET_SEC (60: one light read a chunk);
  * its quota: Screens' stricter floors (ga4_paid.App) — the build runs it after every other GA4 step, before the paid
    cube (the light one first), so it takes only what they leave, in this build and the next;
  * a FINAL day be_build's input guard found broken (data/be_tab/fsq_p.json: the Google Ads users' first-session share
    far under their day-0 cohort share that day) is read again alone through ga4_nvr's REREAD path — newest first, at most
    RQ_CAP days an app a run, each at most RQ_MAX times, RQ_GAP_H hours apart ("rq" in the store); no other day is;
  * a stuck app (ga4_paid.streak: failing FAIL_LINE runs in a row — ga4_nvr itself retries a failed app every
    RETRY_HOURS and never counts it) → counts "stuck": the build prints the health banner's line.
Switched by GA4_NVRP. Never raises; never prints. PUBLIC LOG: counts only — log_line ("ga4 nvr paid: apps …") never
names an app, id, date, country or amount. The build reads the store through MOD (ga4_nvr's own readers: store_path,
load_store) — no other API here.
"""
import os
import time
from datetime import datetime, timezone

from . import ga4_nvr
from . import ga4_paid

MOD = ga4_paid.instance(ga4_nvr, "admob_iq.fetch._ga4_nvr_paid_impl", DIR="ga4_nvr_paid", APP=ga4_paid.App,
                        NAME="ga4 nvr paid", PARTS=("c",), REREAD="be_tab/fsq_p.json",
                        MAX_CALLS=int(os.environ.get("GA4_NVRP_MAX_CALLS") or ga4_nvr.MAX_CALLS))
BUDGET_SEC = 60                     # seconds a run (one light read a chunk, where ga4_nvr makes three)


def refresh_all(cfg, data_dir, apps, now=None, clock=None, budget=None):
    """ga4_nvr's run (ga4_nvr.refresh_all) on the paid store, its country read only, every read held to Google Ads
    users, then the stuck rule (ga4_paid.streak) → {"counts" (+ "stuck"), "apps": {app id: fetched|fresh|failed|
    deferred|waiting}} (+ "error"). now None: the clock's UTC now (ga4_nvr's own default, taken here: the stuck rule's
    run time); clock None: the monotonic clock; budget None / 0: BUDGET_SEC. Never raises; never prints."""
    now = now or datetime.now(timezone.utc)
    return ga4_paid.streak(MOD, data_dir, MOD.refresh_all(cfg, data_dir, apps, now, clock or time.monotonic,
                                                          budget=budget or BUDGET_SEC), now)


def log_line(status):
    """The build log's ONE line for this step — counts only ("ga4 nvr paid: apps …")."""
    return MOD.log_line(status)
