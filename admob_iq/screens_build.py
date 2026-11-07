"""🖼️ Screens tab — the build step (owner, 4 Nov 2026: "per app, per Activity: visits, the ad impressions against them, the
ratio — a NEW tab"; "a score for every screen's views against its impressions … from it we see which screen has a problem
— requests low or show rate low — so we can send the developer a report and get a fix"). ALL the judgement lives here
(status, cause, the developer report): the page only windows numbers for the picked period.

Input: the private store of fetch.ga4_screens (read here with OUR OWN small readers — the §2.7 layout, never imported):
  data/ga4_screens/<key>.json.gz                    meta {"app_id", "package", "time_zone", "reads", "months", …}
  data/ga4_screens/<key>/recent.json.gz             {"days": {day: {read id: record}}}   (the re-read recent days)
  data/ga4_screens/<key>/<grp>_<YYYY-MM>.json.gz    {"days": {day: {read id: record}}}   (final days; grp core · small ·
                                                    ver · cc)
streamed: one app's core (t v w a) + ONE month of one layer group in memory at a time. The version / country groups'
derived month (per class, per dim) is cached in data/ga4_screens_cache/<key>/<grp>_<YYYY-MM>.json.gz under the store
file's sha1: an unchanged month is never parsed again ("cached N" in the line). AdMob comes from the dashboard this build
already holds (placements[].daily per ad unit per IST day, apps_catalog, latest_complete, report_tz) and
data/app_store_ids.json (sibling AdMob app ids of the same Play package). The app's daily users (Ads / user, owner 6 Nov
2026: "1 user ko kitna impression mila") come from the Uninstall store data/ga4_uninstall/<key>.json.gz: its "daily" a1
is GA4's activeUsers by date on the same Android stream filter — used only when its property, stream and time zone are
this store's (app_users).

Files (sorted compact JSON, deterministic gzip — no mtime / file name, level GZ_LEVEL — written only when their bytes
changed, known from the out-file index in the cache dir; day arrays from the app's first day d0, shards from the 1st of
their month; a month's shard is not even built while its inputs are unchanged):
  site/scr_all.json.gz          every app's day arrays over its display items + status words + the app's daily users
                                "au" ≤ ftU (the App total and All apps draw from this file alone; the tab's first load)
  site/scr_<key>.json.gz        the app page: screens, units, per-day core rows, AdMob per unit (blended), row details;
                                "U" the top screens' users per final day ≤ ftU ("Us" their screen indexes; only where
                                the users read, the views and the ads by screen are whole: users_by_day), "au" the
                                app's daily active users per final day ≤ ftU (app_users; else "auw" why)
  site/scr_l_<key>.json.gz      the app's layers: per-day small-group records, versions, month sums, shard list, the
                                developer report text (English, no money)
  site/scr_r_<key>_<YYYYMM>.json.gz / scr_c_<key>_<YYYYMM>.json.gz   one month of versions / countries over the display
                                items (the page loads only a picked period's edge months)
v 4 (owner, 8 Nov 2026: Firebase's own numbers and three signals — the v 4 section below): file 2 adds per day "m" (revenue
by screen, micros), "pw" (the periods the page offers), "pu" (their users, unique in the period: the fetch's
users.json.gz), "sig" (the signals per period and row), "fs4" / "fsd" (the full-screen rows from AdMob on its own days)
and "adt" (the app's AdMob total per day); a scr_all entry adds "rv" (per day [GA4's revenue, AdMob's]), "pt" (the app's
users per period) and "sg" (the signals' counts per period).
and the pointer dashboard["scr"] = {"v", "file", "fv", "apps": {app id: {"key", "v", "vl", "from", "ft"}}}. Write order:
shards → scr_l → scr_<key> → scr_all → pointer. A broken app loses its own files and pointer entry ("failed"); a broken
or too big shard costs only that month (listed in scr_l "failed" / "big"); file 2 and scr_all never depend on a shard.

Calendar: td = the property's today; ft = td − 2 (GA4 still adds to the last two days: "GA4 data till ft"). GA4 days are
the property's (UTC on every live property); AdMob days are the report zone's (IST): GA4 day D = the overlapped share of
AdMob days D and D+1 (0.7708 / 0.2292 for UTC vs IST), only when both are ≤ latest_complete.

Status (owner, 6–7 Nov 2026: "total user ke samne kitna impression mila vo imp hota he"; fixed window, the picker never
changes it — the First open precedent): IMPRESSIONS PER USER PER DAY. A screen row = its ads ÷ that screen's own users
(GA4 activeUsers by screen class, unique within one day and one screen: summed over days = user-days, never across
screens); a full-screen trigger (no screen) and the App row = ads ÷ the app's daily users ("per app user"). W = the 10
final days ending ftU, N = the 28 before; ftU = the last final day on which both the app's daily users and the screen
users read are in (one end per app: the word changes once a day). Days are counted by whole reads (a whole day with 0
users of the screen is a day that adds to no sum). The shipped thresholds on the per-user numbers + 4 holds: under 1 % of
the app's total imp / user ("small"), the app-wide fold (triggers only: app views per user moved), 2 final days in a row,
and the collapse rule (≤ 50, halves ≤ 60, z ≤ −2 → Worse). The App row is checked against AdMob per daily user: when GA4
and AdMob disagree it is judged on AdMob ("Worse (AdMob)"), N/A only when AdMob is incomplete. Screen rows count inline
ads, or every format (allf: 1 formats not recorded, 2 GA4 gave the screens without the format on most whole days of
W ∪ N — the full-screen share measured where it did ships beside it). Cause: the exact parts of the per-user change
(screen: views per user × time per view × ads per minute; trigger / App: app views per user × ads per app view), then
for the ad-logic part a stopped / changed ad unit first, else an exact LMDI split of the change in ads per visit over the
row's units — tie (GA4 ÷ AdMob), share of the unit on this screen, show rate, fill, requests per app visit, the screen's
share of visits — whose terms add up to the change exactly (no leftover is ever named a cause).

Absolute numbers (owner, 7 Nov 2026: "10.6 view ke samne 3.19 ads aayi … ye kam he na?" — the status above only says
"same as its own past": a screen that was always low read Normal): per screen row over W, Ads / view % (its ads ÷ its
views × 100, Imp / user / day's ads), Fill (AdMob matched ÷ requests) and Show rate (impressions ÷ matched) of its units,
each unit weighted by σ = the screen's share of the unit's GA4 ads (ab_side / ab_row; a shared unit's rates stay the
unit's). The words judge them against the SAME AdMob format across every built app's units (ab_bench: one vote per
AdMob unit id, unweighted quantiles, no benchmark under AB_MIN_N units; run() after the app loop) → Low (a part ≥ 20 %
under its format's p25) · Few ads · OK · Too few ads · Not measurable · No ads (ab_judge) in scr_all's status [7] – [9];
the vs-own-past word stays beside them. A full-screen trigger gets the same from its units (ab_tside / ab_trig: σ splits
an AdMob unit two GA4 units share; no views, so no Few ads; a format without a benchmark: No benchmark, the number
shown) and file 2's rows["t<n>"]["ab"]; scr_all's "lt" counts its Low triggers beside "lo" (an older file has no "lt":
its triggers ship "" and keep their own word). The page windows Fill / Show itself from file 2 (units, ufmt, adm, days).

run(dashboard, data_dir, out_dir, s) → the _headers no-store paths (["/scr_*"], ONE splat rule) or [] (no store / switched
off / a failure: every scr_ file removed, no pointer); only the apps the dashboard's apps_catalog selects (when it has
one). Failure-isolated; ONE counts-only line. A store month file that cannot be read or parsed is never skipped
silently: counted ("broken N"), ONE "scr store skipped: <Type>" health line per build, and the days it held ship the
state "x" (store file unreadable), never "not read yet". Read-only history check:
  python -m admob_iq.screens_build backtest <data_dir> [--dashboard <dashboard.json.gz>]
"""
import gzip
import hashlib
import io
import json
import math
import os
import re
import sys
import zlib
from datetime import date, datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

from .db import write_json_gz_stable
from .fetch import ga4_uninstall as gu

PREFIX = "scr_"
ALL_FILE = "scr_all.json.gz"
APP_RE = re.compile(r"^scr_(?:all|(?:[lrc]_)?[0-9a-f]{12}(?:_\d{6})?)\.json\.gz$")
HEADER_PATHS = ["/scr_*"]
V = 4                                  # 4: Firebase's numbers (the users of a period, revenue by screen, the
                                       # full-screen rows from AdMob) and the three signals (v 4 below); 3: absolute numbers (Ads / view · Fill · Show rate, the format benchmark); 2:
                                       # impressions per user per day (status / score / why changed, scr_all "au")
MAX_GZ = 8 * 1024 * 1024
STORE_DIR = "ga4_screens"
CACHE_DIR = "ga4_screens_cache"
CACHE_V = 4                            # 4: scr_l's small-group records carry _ch's state (a "skip" record "-"); 3: a
                                       # "skip" record (GA4 never asked) is cached as "-"; 2: a "p" day with GA4 grouped
                                       # ≤ FOLD_OK as "w" (older caches re-derived)
SMALL_V = 1                            # the small month cache's parts beside its day records ("u": the users by screen of
                                       # its whole users days): a cache without them / of another SMALL_V is encoded again
                                       # (a CACHE_V bump would derive every layer month again too)
GZ_LEVEL = 6                           # the scr_ files' gzip level (9 took ~4× the time for files under a tenth smaller)
IDX_V, IDX_APP, IDX_ALL = 1, "shards.json", "all.json"      # the out-file index (_idx_path)
SHARD_V = 1                            # bump when shard_body's output changes for the same inputs (a shard key part)
V_SHARD = 1                            # the shard files' own format version (unchanged by V 2: no shard is rewritten)
KEY_V = 3                              # the file-version part of every shard key, held at V 3: shard_body never reads
                                       # V, so a V bump keeps every shard (with V itself there, each V bump derived every
                                       # month of every app again — the step's slowest build — to write the same bytes)
GROUPS = {"core": ("t", "v", "w", "a", "m"), "small": ("k", "e", "uV", "uA", "s", "x", "nV", "nA"),
          "ver": ("rV", "rA"), "cc": ("cV", "cA")}
LATE_READS = frozenset(("m",))         # reads the fetch gained after stores began (m: 8 Nov 2026)
READ_IDS = ("t", "v", "w", "a", "m", "nV", "nA", "rV", "rA", "cV", "cA", "k", "e", "s", "x", "uV", "uA")
OK_ST = ("w", "p")                     # a record whose rows are usable (whole, or whole with a GA4 grouped part)
ST_CH = frozenset("wpost")             # the fetch's day states; the build adds "x" (its store month file cannot be read)
FOLD_OK = 0.02                         # a "p" day counts for status / cause only while GA4 grouped ≤ 2 % of it (§0.3: a
                                       # screen's ads moved into "(other)" would read as a drop; the tie tolerance)

# ── status (§3.2; thresholds change only here, then the backtest) ──
W_DAYS, N_DAYS, HALF = 10, 28, 5
MIN_A_W = 5                            # whole days of the row's ads in W, else N/A "Not whole" + why (WHY_PARTS)
# that why: the W days the row's series lacks, counted by the state each ships (App.day_why) — non-zero parts, in order
WHY_PARTS = (("s", "GA4 sampled"), ("o", "GA4 dropped rows"), ("p", "GA4 grouped"), ("t", "thresholding"),
             ("-", "not read yet"), ("f", "format not split"), ("x", "store file unreadable"), ("u", "users not in yet"))
MIN_N, MIN_W, MIN_VN, MIN_E = 14, 7, 300, 30
LOG_SHIFT, LOG_MAX = 0.05, 0.30        # unset-class / notset-format share: moved > 5 points or > 30 % in W
ALLF_SHARE = 0.05                      # notset formats above this in N or W: screen rows judged on all formats (allf 1)
ALLF_NOSPLIT = 0.5                     # … or, over W ∪ N, the whole ads-by-screen days without the format (grain c) above
                                       # this share of the whole ones (allf 2: GA4 sampled every screen × format split)
ALLF_FS_DAYS = 60                      # allf's why: the full-screen share on app screens over the newest ≤ 60 split days
MAT_SHARE = 0.01                       # a row is judged only holding ≥ 1 % of the app's ads of its kind in W or in N (a
                                       # ratio of near-zero rates is no finding: owner, 6 Nov)
PHI_MIN_E = 5
WATCH_Z = 3                            # Watch / Better need |z| ≥ 3 too (the real-store backtest: |z| 2–3 flagged too many
                                       # marginal rows); Worse: z ≤ −3 and score < 80
IMP_MAT = 0.01                         # a flag holds only at ≥ 1 % of the APP's total imp / user (impact, below)
OWN_FOLD = 90                          # triggers: the change net of the app-wide app-views-per-user change still < 90
COLLAPSE = (50, 60, 2.0)               # score ≤ 50, both halves ≤ 60, z ≤ −2 → Worse (a stop is never held by z)
CONFIRM_DAYS = 2                       # a flag shows from its 2nd final day in a row (3: the owner option)
DAU_MOVE = 0.25                        # the App row's why names a daily-users move above this (why only)
ADM_MIN_W, ADM_MIN_N = 7, 14           # the App row's AdMob check: AdMob-complete days in W / N
FLAGS = ("Worse", "Watch")
# the parts of a per-user change (exact LMDI, % of normal): screens views per user × time per view × ads per minute
# (or × ads per view without time); triggers and the App row app views per user × ads per app view
PART_NAME = {"vpu": "views per user", "tpv": "time per view", "apm": "ads per minute", "adv": "ads per view",
             "avu": "app views per user"}
PART_LABEL = {"vpu": "Users open it fewer times", "tpv": "Users stay shorter", "avu": "Users open fewer screens"}
PART_CHECK = {
    "Users open it fewer times": "This screen's own users open it fewer times a day: check its entry points and "
                                 "back-stack in the latest version.",
    "Users stay shorter": "Users leave this screen sooner, so refreshed banners show fewer times per view: content / "
                          "load time, not the ad code.",
    "Users open fewer screens": "Across the whole app users open fewer screens: user mix (see new vs returning), "
                                "retention or an app-wide flow change.",
    "Ads stopped": "No ads on this screen in the last 10 days.",
}
# ── cause (§3.3) ──
STOP_REQ, STOP_FRAC, STOP_SHARE = 50, 0.10, 0.50
TERM_MIN, MIXED = 0.10, 0.6
TIE_LO, TIE_HI, TIE_MIN_N = 0.8, 1.25, 100
UNTIED_SHARE = 0.5                     # units with no AdMob id + units whose tie is outside TIE_LO–TIE_HI hold more than
                                       # this share of the row's ads → not measurable, named by the bigger part
ADM_MIN_DAYS = 7
FU_MIN_W, FU_MIN_N = 7, 14
# ── absolute numbers (owner, 7 Nov 2026: "10.6 view ke samne 3.19 ads aayi … ye kam he na?" — a screen that was always
# low shows Low): Ads / view, Fill, Show rate of a screen against the same AdMob format across ALL apps' units ──
AB_REQ, AB_MT, AB_ADS = 1000, 300, 300  # volume floors: requests (fill) / matched (show) of a unit or a screen's part, a
                                       # screen's ads (Ads / view) — never thresholds: those are the measured quantiles
AB_MIN_N = 20                          # under 20 units (screens for Ads / view) in a sample: that format has no benchmark
AB_PART, AB_DOM = 0.2, 0.8             # a part (AdMob format) is judged from 20 % of the screen's unit ads; Ads / view
                                       # needs one part ≥ 80 %
AB_Q = (0.1, 0.25, 0.5, 0.75)          # p10 / p25 / median / p75, unweighted (one big unit would be the median), linear;
                                       # Low = under p25 (the owner's case sits between p10 and p25: p10 calls it fine)
SIG_MIN, SIG_N = 3, 28                 # σ from W's unit-split days; under 3 of them the newest 28 split days ≤ W's end
AB_TXT = {"fill": ("Fill", "requests not filled", "Lower fill"),
          "show": ("Show rate", "ads filled but not shown", "Lower show rate"),
          "av": ("Ads / view", "few ads per view", "Fewer ad requests")}       # label, cause, its CHECK text
FMT_NAME = {"appopen": "app open", "rewardedinterstitial": "rewarded interstitial"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
# ── duplicate ad_impression copies (§3.1) ──
DUP_SHARE, DUP_LO, DUP_HI, DUP_RUN, DUP_END = 0.10, 0.8, 1.25, 2, 2
CONF_LO, CONF_HI, DUP_FMT_MIN = 0.85, 1.15, 100
# ── items / triggers ──
TOP_SHARE, TOP_MONTH_VISITS = 0.90, 1000
SUFFIX_SHARE, SUFFIX_MIN_UNITS = 0.5, 4
BAD_RATE = 0.9

FULL = frozenset(("interstitial", "appopen", "rewarded", "rewardedinterstitial"))
FOLD = frozenset(("(other)", "other"))
UNSET = frozenset(("", "(not set)", "(none)", "not set"))
# the ad SDKs' own full-screen Activities: the SAME pattern as fetch/ga4_activity_probe.AD_SCREEN (a test pins it), kept
# here so the build never imports a probe module
AD_SCREEN = re.compile(r"(?:^|\.)(?:AdActivity|AdUnit\w*Activity|AudienceNetworkActivity|AppLovin\w*Activity|"
                       r"InMobiAdActivity|VungleActivity|CBImpressionActivity|MBRewardVideoActivity|MBCommonActivity|"
                       r"TTFullScreen\w*Activity|TTReward\w*Activity|TTAppOpenAd\w*Activity|Inneractive\w*Activity|"
                       r"FullScreenWebViewDisplay|\w*InterstitialActivity)$", re.I)
ID_RE = re.compile(r"ca-app-pub-\d+[/~]\d+|^[0-9a-f]{16}$|^\d{6,}$", re.I)
TEST_PUB = "ca-app-pub-3940256099942544"      # Google's published sample-ads publisher (its test unit ids)
TRIGGERS = (("Back press", ("back", "exit")),
            ("App resume", ("resume", "background", "foreground", "bg")),
            ("Splash", ("splash", "launch")),
            ("Notification", ("notif", "push")),
            ("Save / apply", ("save", "apply", "export", "download", "share")),
            ("Home", ("home", "main", "dashboard")),
            ("Onboarding", ("lang", "permission", "prmsn", "onboard", "intro", "tutorial")))
SECOND = ("Second / session", ("second", "session", "next"))
STOP = frozenset(("admob", "ad", "ads", "inter", "interstitial", "int", "app", "open", "appopen", "aoa", "rewarded",
                  "reward", "native", "banner", "high", "medium", "low", "floor", "ecpm", "id", "test", "with", "on",
                  "the", "screen", "activity"))
TERM_LABEL = {"tie": "GA4 logging changed", "share": "Ads moved to other screens", "show": "Lower show rate",
              "fill": "Lower fill", "req": "Fewer ad requests", "vis": "More visits, same ads",
              "units": "Ad units changed", "unmatched": "Units not in AdMob"}
TERMS = ("tie", "share", "show", "fill", "req", "vis", "units", "unmatched")
CHECK = {
    "Fewer ad requests": "The app requests fewer ads per visit. Check the ad is still loaded on this screen in the latest "
                         "version: code path, remote-config flags, frequency caps, consent gating, conditions before "
                         "load().",
    "Lower show rate": "Ads are filled but fewer are shown. Check the ad view is attached and visible, the ad is not loaded "
                       "too late (users leave before it renders), refresh/reload logic, and preloaded ads expiring before "
                       "show.",
    "Lower fill": "Networks returned fewer ads for the same requests. Usually mediation / demand, not app code: check this "
                  "unit's mediation groups and floors, adapter / SDK versions and the unit's status.",
    "Ads moved to other screens": "This screen now gets a smaller share of the unit's ads: check whether the ad was "
                                  "removed from this screen or the screen's layout changed.",
    "More visits, same ads": "This screen now gets a smaller share of the unit's ads: check whether the ad was removed "
                             "from this screen or the screen's layout changed.",
    "GA4 logging changed": "AdMob did not drop; GA4 logs fewer ad_impression events: check the analytics/ad SDK versions "
                           "and ad_impression logging.",
}
STATUS_RANK = {"Worse": 0, "Watch": 1, "Better": 2, "Normal": 3, "Too early": 4, "N/A": 5}
JUDGED = ("Worse", "Watch", "Better", "Normal")
LINE = None


def enabled(s):
    return bool((s or {}).get("screens_tab", True))


# ── small helpers ─────────────────────────────────────────────────────────────────────────────

def _d(s):
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


def _iso(d):
    return d.isoformat()


def _span(a, b):
    a, b = _d(a), _d(b)
    return [_iso(a + timedelta(days=i)) for i in range((b - a).days + 1)] if b >= a else []


def _raw(body):
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha(raw):
    return hashlib.sha1(raw).hexdigest()


# ── the scr_ files on disk: one deterministic writer + a content index (an unchanged file is never touched) ─────────

def _gz(raw):
    """write_json_gz_stable's container (no mtime, no file name) at GZ_LEVEL: the same raw bytes → the same file."""
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=GZ_LEVEL) as g:
        g.write(raw)
    return buf.getvalue()


def _write_gz(path, gz):
    """The one place a scr_ file reaches the disk: tmp + replace (a reader never sees half a file)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(gz)
    os.replace(tmp, path)


def _on_disk(path, e):
    """The file at `path` is the one index entry `e` describes: its size, and its gzip trailer's CRC-32 + length of the
    raw bytes (the last 8 bytes — never decompressed). A missing / changed / truncated file → False (written again)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            if f.tell() != e.get("n") or f.tell() < 18:
                return False
            f.seek(-8, 2)
            t = f.read(8)
    except (OSError, ValueError):
        return False
    return int.from_bytes(t[:4], "little") == e.get("c") and int.from_bytes(t[4:], "little") == e.get("r")


def _put(out_dir, fn, raw, idx, key=None):
    """One scr_ file from its raw JSON (_raw) → the sha1 hex of the raw bytes (the pointer's "v"), or None when it does
    not fit (raw and gzipped both over MAX_GZ; nothing written). Written only when idx[fn] holds another content hash or
    the file on disk is not the one written: an unchanged file is never compressed, decompressed or rewritten."""
    h = _sha(raw)
    p = os.path.join(out_dir, fn)
    e = idx.get(fn)
    if isinstance(e, dict) and e.get("h") == h and _on_disk(p, e):
        if key is not None and e.get("k") != key:
            idx[fn] = dict(e, k=key)
        return h
    gz = _gz(raw)
    if len(raw) > MAX_GZ and len(gz) > MAX_GZ:
        idx.pop(fn, None)
        return None
    _write_gz(p, gz)
    idx[fn] = dict({"h": h, "n": len(gz), "c": zlib.crc32(raw), "r": len(raw) & 0xFFFFFFFF},
                   **({"k": key} if key is not None else {}))
    return h


def _idx_path(data_dir, key=None):
    """The out-file index: per app data/ga4_screens_cache/<key>/shards.json (its shards, scr_l, file 2); scr_all's
    data/ga4_screens_cache/all.json. {file name: {"h" raw sha1, "n" gz size, "c" crc32, "r" raw length, "k" shard
    input key} | {"k", "big": 1}}."""
    return os.path.join(data_dir, CACHE_DIR, key, IDX_APP) if key else os.path.join(data_dir, CACHE_DIR, IDX_ALL)


def _idx_load(path):
    try:
        with open(path, encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        return {}
    files = j.get("files") if isinstance(j, dict) and j.get("v") == IDX_V else None
    return {k: v for k, v in files.items() if isinstance(v, dict)} if isinstance(files, dict) else {}


def _idx_save(path, files, old=None):
    """Saved only when it changed (sorted compact JSON: the same index → the same bytes)."""
    if files == old:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"v": IDX_V, "files": files}, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        pass


def _r(v, n=2):
    if v is None:
        return None
    v = round(float(v), n)
    return int(v) if v.is_integer() else v


def _i(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return int(float(v or 0))


def _ok(rec):
    return isinstance(rec, dict) and rec.get("st") in OK_ST


def _whole(rec):
    """A usable record that is whole enough to JUDGE on: "w", or "p" with its GA4 grouped share ≤ FOLD_OK (a "p" kept for
    thresholding with no share stored tied to its truth, so it counts)."""
    if not _ok(rec):
        return False
    if rec.get("st") == "w":
        return True
    try:
        return float(rec.get("f") or 0) <= FOLD_OK
    except (TypeError, ValueError):
        return False


def _ch(rec):
    """A record's day state for the shipped state strings: a "p" whose GA4 grouped share is ≤ FOLD_OK is whole enough to
    judge on (_whole) and ships "w" — the page's coverage counts exactly the days the build judges on; above it, "p". A
    record with "skip" that is not usable (the fetch never asked GA4 that day: its shape dead, or the volume gate) ships
    "-" (not read yet), never the "s" / "o" it is stored with: GA4 did not sample or drop that day."""
    if isinstance(rec, dict) and "skip" in rec and not _ok(rec):
        return "-"
    st = rec.get("st") if isinstance(rec, dict) else None
    if st == "p" and _whole(rec):
        return "w"
    return st if st in ST_CH else "-"


def _today(meta, now):
    try:
        return now.astimezone(ZoneInfo(meta.get("time_zone") or "UTC")).date()
    except Exception:
        return now.date()


_FMT_MEMO, _KIND_MEMO = {}, {}             # fmt / kind of a string: pure functions, called per row (millions a build)


def fmt(raw):
    """An ad format, GA4's / AdMob's / an app's own spelling → one name (letters only, lower case): rewardedinterstitial,
    rewarded, appopen, interstitial, native, banner (incl. mrec / adaptive), notset ("Format not recorded"), fold (GA4
    grouped "(other)"); anything else is kept as it is (counted INLINE)."""
    if type(raw) is str:
        f = _FMT_MEMO.get(raw)
        if f is None:
            f = _fmt(raw)
            if len(_FMT_MEMO) < 50000:
                _FMT_MEMO[raw] = f
        return f
    return _fmt(raw)


def _fmt(raw):
    s = re.sub(r"[^a-z]", "", str(raw or "").lower())
    if "rewardedinter" in s:
        return "rewardedinterstitial"
    if "rewarded" in s:
        return "rewarded"
    if "appopen" in s or s == "aoa":
        return "appopen"
    if "interstitial" in s or s.startswith("inter"):
        return "interstitial"
    if "native" in s:
        return "native"
    if "banner" in s or "mrec" in s or "adaptive" in s:
        return "banner"
    if s in ("", "notset", "none"):
        return "notset"
    if s == "other":
        return "fold"
    return s


def fgroup(f):
    """A normalized format → its bucket: 0 inline, 1 full-screen, 2 not recorded, None GA4 grouped."""
    return 2 if f == "notset" else 1 if f in FULL else None if f == "fold" else 0


def kind(cls):
    """A screen class → "ns" (not recorded), "g" (GA4 grouped), "ad" (an ad SDK's own Activity) or "s" (a screen)."""
    if type(cls) is str:
        k = _KIND_MEMO.get(cls)
        if k is None:
            k = _kind(cls)
            if len(_KIND_MEMO) < 200000:
                _KIND_MEMO[cls] = k
        return k
    return _kind(cls)


def _kind(cls):
    c = str(cls or "").strip()
    if c.lower() in UNSET:
        return "ns"
    if c.lower() in FOLD:
        return "g"
    return "ad" if AD_SCREEN.search(c) else "s"


def unit_unset(u):
    return str(u or "").strip().lower() in UNSET


def is_id_name(u):
    """A unit name that is an id (an AdMob ca-app-pub id, a 16-hex hash, a long number), not a readable name."""
    return bool(ID_RE.search(str(u or "").strip()))


# ── the store, our own small readers (§2.7) ──────────────────────────────────────────────────

def _read_gz_bytes(path):
    try:
        with open(path, "rb") as f:
            return gzip.decompress(f.read())
    except (OSError, EOFError, ValueError, zlib.error):
        return None


def _json(raw):
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (ValueError, AttributeError, UnicodeDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def store_keys(data_dir):
    """The 12-hex keys with a meta file, sorted."""
    try:
        names = os.listdir(os.path.join(data_dir, STORE_DIR))
    except OSError:
        return []
    return sorted(n[:12] for n in names if re.match(r"^[0-9a-f]{12}\.json\.gz$", n))


def load_meta(data_dir, key):
    raw = _read_gz_bytes(os.path.join(data_dir, STORE_DIR, key + ".json.gz"))
    m = _json(raw) if raw is not None else None
    return m if m and m.get("app_id") else None


def load_recent(data_dir, key):
    raw = _read_gz_bytes(os.path.join(data_dir, STORE_DIR, key, "recent.json.gz"))
    body = _json(raw) if raw is not None else None
    days = (body or {}).get("days")
    return days if isinstance(days, dict) else {}


def _months(data_dir, key, grp, meta=None):
    """The months of a group: the meta list ∪ the month files on disk (a meta behind its files never hides one)."""
    out = set((((meta or {}).get("months") or {}).get(grp)) or [])
    try:
        for n in os.listdir(os.path.join(data_dir, STORE_DIR, key)):
            m = re.match(r"^%s_(\d{4}-\d{2})\.json\.gz$" % re.escape(grp), n)
            if m:
                out.add(m.group(1))
    except OSError:
        pass
    return sorted(m for m in out if re.match(r"^\d{4}-\d{2}$", str(m)))


def _month_path(data_dir, key, grp, m):
    return os.path.join(data_dir, STORE_DIR, key, "%s_%s.json.gz" % (grp, m))


def _parse_month(b):
    """A month file's bytes → its {day: {read id: record}}; raises when they are not a store month file (not gzip, not
    UTF-8 JSON, not {"days": {…}})."""
    body = json.loads(gzip.decompress(b).decode("utf-8"))
    days = body.get("days") if isinstance(body, dict) else None
    if not isinstance(days, dict):
        raise ValueError("not a store month file")
    return days


def iter_months(data_dir, key, grp, meta=None, broken=None):
    """→ (YYYY-MM, sha1 of the file bytes, {day: {id: rec}}) one month at a time, oldest first. A month the store has (its
    meta or its disk) whose file cannot be read or parsed is skipped, never silently: `broken` (a list) gets (grp, month,
    error type) — the build counts it ("broken N"), prints its one health line and marks its days "x"."""
    for m in _months(data_dir, key, grp, meta):
        try:
            with open(_month_path(data_dir, key, grp, m), "rb") as f:
                b = f.read()
            days = _parse_month(b)
        except Exception as e:
            if broken is not None:
                broken.append((grp, m, type(e).__name__))
            continue
        yield m, _sha(b), days


def _better(old, new):
    """Two records of one (day, read): a usable one is never replaced by an unusable one; else the newer wins."""
    if _ok(old) and not _ok(new):
        return old
    return new


def _read_of(meta, i):
    """Read i's entry of the meta's reads ({} when there is none)."""
    reads = meta.get("reads") if isinstance(meta, dict) else None
    r = reads.get(i) if isinstance(reads, dict) else None
    return r if isinstance(r, dict) else {}


def _oldest(meta, i):
    """Read i's oldest filled day (the fetch's backfill cursor in meta reads), or None."""
    o = _read_of(meta, i).get("oldest")
    return o if isinstance(o, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", o) else None


def _bf(r):
    """A meta reads entry → its history cell [oldest, complete]: complete = the backfill reached the history start
    ("done") and no skip day from before is still being read again ("redo", a list: non-empty = not complete)."""
    redo = r.get("redo")
    return [r.get("oldest"), bool(r.get("done")) and not (isinstance(redo, list) and redo)]


def lost_span(meta, i, m, td):
    """The days [first, last] that a store month file `m` which cannot be read may have held for read i, or None: month
    files hold FINAL days only (≤ the property's today − 5), none before the read's oldest filled day (unknown: the 1st)."""
    try:
        a = _iso(date.fromisoformat(m + "-01"))
        b = min(_month_end(m), _iso(_d(td) - timedelta(days=5)))
    except (TypeError, ValueError):
        return None
    o = _oldest(meta, i)
    if o and o > a:
        a = o
    return (a, b) if a <= b else None


def lost_ids(meta, grp):
    """The reads of group `grp` a broken month file may have held: every one, but a read added to the fetch after the
    store began (LATE_READS) only once the meta holds it — never fetched, it wrote no record (its unknown oldest day
    must not stretch the history back to the month's 1st)."""
    return tuple(i for i in GROUPS.get(grp, ()) if i not in LATE_READS or _oldest(meta, i))


def mark_lost(app, broken, st_of):
    """State "x" (store file unreadable) on the days a broken store month file may have held — only where no other
    record (the recent window) gave the day its own state: the page says why, never "not read yet"."""
    for grp, m in sorted({(g, m) for g, m, _ in broken or ()}):
        for i in lost_ids(app.meta, grp):
            sp = lost_span(app.meta, i, m, app.td)
            if sp:
                st = st_of(i)
                for d in _span(max(sp[0], app.d0), sp[1]):
                    st.setdefault(d, "x")


# ── AdMob: the unit join and the blend ───────────────────────────────────────────────────────

def admob_ids(meta, by_id):
    """The AdMob app ids of a store: its app_id + by_id ids whose package == the STORE's package (both stripped,
    non-empty). A package is never taken from by_id, so a blank package shared by many ids joins nothing."""
    aid = str(meta.get("app_id") or "")
    pkg = str(meta.get("package") or "").strip()
    ids = [aid]
    if pkg:
        ids += sorted(a for a, p in (by_id or {}).items() if str(p or "").strip() == pkg and a != aid)
    return ids


def app_placements(dashboard, ids):
    """The placements of these AdMob app ids via apps_catalog (account_id, app_name) == placement (account, app)."""
    ids = set(ids)
    pairs = {(str(c.get("account_id")), str(c.get("app_name"))) for c in dashboard.get("apps_catalog") or []
             if str(c.get("app_id")) in ids}
    return [p for p in dashboard.get("placements") or []
            if (str(p.get("account")), str(p.get("app"))) in pairs]


def unmapped_pairs(dashboard):
    cat = {(str(c.get("account_id")), str(c.get("app_name"))) for c in dashboard.get("apps_catalog") or []}
    return len({(str(p.get("account")), str(p.get("app"))) for p in dashboard.get("placements") or []} - cat)


_SHARE_MEMO = {}


def shares(day, tz_ga4, tz_admob):
    """{AdMob day: share} of one GA4 day D (the overlap of the two zones' days, DST-aware): UTC vs IST → D 0.7708,
    D+1 0.2292."""
    k = (day, tz_ga4, tz_admob)
    if k in _SHARE_MEMO:
        return _SHARE_MEMO[k]
    try:
        zg, za = ZoneInfo(tz_ga4 or "UTC"), ZoneInfo(tz_admob or "UTC")
    except Exception:
        zg = za = ZoneInfo("UTC")
    d = _d(day)
    s = datetime.combine(d, dtime(0), zg).astimezone(timezone.utc)
    e = datetime.combine(d + timedelta(days=1), dtime(0), zg).astimezone(timezone.utc)
    tot, cur, out = (e - s).total_seconds(), s, {}
    while cur < e:
        la = cur.astimezone(za)
        nxt = datetime.combine(la.date() + timedelta(days=1), dtime(0), za).astimezone(timezone.utc)
        seg = min(e, nxt)
        out[_iso(la.date())] = out.get(_iso(la.date()), 0.0) + (seg - cur).total_seconds() / tot
        cur = seg
    if len(_SHARE_MEMO) > 200000:
        _SHARE_MEMO.clear()
    _SHARE_MEMO[k] = out
    return out


class Adm:
    """An app's AdMob side: per ad unit id {IST day: [req, matched, imp, revenue micros]}, blended onto GA4 days (the
    status's rates) or summed on AdMob's own days (v 4's full-screen rows and the app's total: never blended)."""

    def __init__(self, placements, tz_ga4, report_tz, latest, tz_by_account=None):
        self.ids, self.first, self.latest, self.tz_ga4 = {}, None, str(latest or ""), tz_ga4 or "UTC"
        self.assumed = False
        for p in placements:
            pid = str(p.get("id") or "")
            if not pid:
                continue
            acct_tz = (tz_by_account or {}).get(str(p.get("account")))
            if not acct_tz:
                self.assumed = True
            e = self.ids.setdefault(pid, {"name": str(p.get("name") or ""), "fmt": fmt(p.get("format")),
                                          "tz": acct_tz or report_tz or "UTC", "d": {}})
            for row in p.get("daily") or []:
                try:
                    dd = str(row[0])[:10]
                    v = [_i(row[3]), _i(row[4]), _i(row[2]), _i(row[1])]
                except (IndexError, TypeError, ValueError):
                    continue
                x = e["d"].setdefault(dd, [0, 0, 0, 0])
                for j in range(4):
                    x[j] += v[j]
                if self.first is None or dd < self.first:
                    self.first = dd
        self._memo = {}

    def __bool__(self):
        return bool(self.ids)

    def blend(self, ids, day):
        """[req, matched, imp] of these unit ids on GA4 day `day`, or None (an AdMob day it needs is not complete yet,
        or before AdMob's first day). A missing placement row inside the history = 0."""
        k = (tuple(ids), day)
        if k in self._memo:
            return self._memo[k]
        out = [0.0, 0.0, 0.0]
        if not self.first:
            return None
        for pid in ids:
            e = self.ids.get(pid)
            if not e:
                continue
            for ad, sh in shares(day, self.tz_ga4, e["tz"]).items():
                if sh <= 1e-9:
                    continue
                if ad > self.latest or ad < self.first:
                    self._memo[k] = None
                    return None
                v = e["d"].get(ad)
                if v:
                    for j in range(3):
                        out[j] += sh * v[j]
        self._memo[k] = out
        return out

    def complete(self, day):
        """Every AdMob day GA4 day `day` overlaps is ≤ latest_complete (and ≥ AdMob's first day)."""
        if not self.first:
            return False
        tzs = {e["tz"] for e in self.ids.values()} or {"UTC"}
        for tz in tzs:
            for ad, sh in shares(day, self.tz_ga4, tz).items():
                if sh > 1e-9 and (ad > self.latest or ad < self.first):
                    return False
        return True

    def fmt_imp(self, day):
        """{format: blended impressions} of every unit of the app on GA4 day `day`, or None (not complete)."""
        if not self.complete(day):
            return None
        out = {}
        for pid, e in self.ids.items():
            v = self.blend([pid], day)
            if v:
                out[e["fmt"]] = out.get(e["fmt"], 0.0) + v[2]
        return out


# ── trigger labels for full-screen units ─────────────────────────────────────────────────────

def _tokens(name):
    low = str(name or "").lower().replace("2nd", " second ")
    return re.findall(r"[a-z]+", low)


def suffix_tokens(names):
    """Tokens on ≥ 50 % of the app's unit names (across formats): suffixes (tiers, ids), never a trigger. Only for an app
    with ≥ SUFFIX_MIN_UNITS names."""
    names = sorted({str(n) for n in names if n and not is_id_name(n) and not unit_unset(n)})
    if len(names) < SUFFIX_MIN_UNITS:
        return frozenset()
    cnt = {}
    for n in names:
        for t in set(_tokens(n)):
            cnt[t] = cnt.get(t, 0) + 1
    return frozenset(t for t, c in cnt.items() if c >= SUFFIX_SHARE * len(names))


def trigger_label(name, admob_name="", how="", suffixes=frozenset()):
    """A full-screen unit → its trigger label: the FIRST trigger keyword by position in the name (inside compound tokens
    too: "appresume" → App resume); "Second / session" only when no other keyword is there; else "Feature: <word>"; an
    id / hash name with no AdMob name → "Unknown (unit id)". The AdMob name is used when the unit was matched by id or the
    GA4 name is an id."""
    src = str(name or "")
    if unit_unset(src):
        return "Unit not recorded"
    if how == "id" or is_id_name(src):
        src = str(admob_name or "")
        if not src or is_id_name(src):
            return "Unknown (unit id)"
    toks = [t for t in _tokens(src) if t not in suffixes]
    best = None
    for ti, t in enumerate(toks):
        for label, kws in TRIGGERS:
            for kw in kws:
                p = t.find(kw)
                if p >= 0:
                    cand = (ti, p, -len(kw), label)
                    best = cand if best is None or cand < best else best
        if best is not None:
            return best[3]
    if any(kw in t for t in toks for kw in SECOND[1]):
        return SECOND[0]
    for t in toks:
        if len(t) >= 2 and t not in STOP:
            return "Feature: %s" % t
    return "Other trigger"


# ── per-day quantities ───────────────────────────────────────────────────────────────────────

def a_day(rec):
    """An ads-by-screen record → {"g", "cls": {class: [inline, full, notset]} (fu/f; None at c), "tot": {class: all},
    "cu": {(class, unit, fmt): n} (fu only)}, or None (not usable). What each grain can give: fu → inline per screen,
    full per unit, notset per screen; f → inline / notset per screen, no units; c → nothing per format."""
    if not _ok(rec):
        return None
    g = rec.get("g") or "fu"
    cls, tot, cu = ({} if g in ("fu", "f") else None), {}, ({} if g == "fu" else None)
    for row in rec.get("r") or []:
        try:
            if g == "fu":
                c, fr, u, n = row[0], row[1], row[2], _i(row[3])
            elif g == "f":
                c, fr, n = row[0], row[1], _i(row[2])
                u = None
            else:
                c, n = row[0], _i(row[1])
                fr = u = None
        except (IndexError, TypeError):
            continue
        c = str(c or "")
        tot[c] = tot.get(c, 0) + n
        if cls is not None:
            f = fmt(fr)
            b = fgroup(f)
            x = cls.setdefault(c, [0, 0, 0])
            if b is not None:
                x[b] += n
            else:
                x[0] += n                       # a GA4 grouped format: unknown kind, counted with inline
        if cu is not None:
            k = (c, str(u if u is not None else ""), fmt(fr))
            cu[k] = cu.get(k, 0) + n
    return {"g": g, "cls": cls, "tot": tot, "cu": cu}


def w_day(rec):
    """Units without screen → {(unit, fmt): n}, or None."""
    if not _ok(rec):
        return None
    out = {}
    for row in rec.get("r") or []:
        try:
            k = (str(row[1] if row[1] is not None else ""), fmt(row[0]))
            out[k] = out.get(k, 0) + _i(row[2])
        except (IndexError, TypeError):
            continue
    return out


def t_day(rec):
    """Truth → ({format: ad_impression}, [views, eng], events) or None parts."""
    if not isinstance(rec, dict) or rec.get("st") not in (None,) + OK_ST:
        return None, None, None
    ta = {}
    for row in rec.get("a") or []:
        try:
            f = fmt(row[0])
            ta[f] = ta.get(f, 0) + _i(row[1])
        except (IndexError, TypeError):
            continue
    v = rec.get("v")
    return (ta if rec.get("a") is not None else None), (list(v) if isinstance(v, list) else None), rec.get("ev")


def v_day(rec):
    if not _ok(rec):
        return None
    out = {}
    for row in rec.get("r") or []:
        try:
            c = str(row[0] or "")
            x = out.setdefault(c, [0, 0])
            x[0] += _i(row[1])
            x[1] += _i(row[2])
        except (IndexError, TypeError):
            continue
    return out


def m_day(rec):
    """A revenue record (the fetch's m: totalRevenue, totalAdRevenue by class, micros) → {class: [revenue, ad
    revenue]}, or None (not usable)."""
    if not _ok(rec):
        return None
    out = {}
    for row in rec.get("r") or []:
        try:
            c = str(row[0] or "")
            x = out.setdefault(c, [0, 0])
            x[0] += _i(row[1])
            x[1] += _i(row[2])
        except (IndexError, TypeError):
            continue
    return out


# ── duplicates ───────────────────────────────────────────────────────────────────────────────

def dup_pattern(w, ta):
    """One day → (matches the copy pattern: True / False / None unknown, notset ÷ labelled). The pattern: notset (format
    AND unit unset, from w) ≥ 10 % of the truth's ads AND 0.8 ≤ notset ÷ labelled ≤ 1.25."""
    if w is None or ta is None:
        return None, None
    tot = sum(ta.values())
    ns = sum(n for (u, f), n in w.items() if f == "notset" and unit_unset(u))
    lab = sum(n for (u, f), n in w.items() if f not in ("notset", "fold"))
    ratio = ns / lab if lab else None
    if tot <= 0:
        return False, ratio
    return bool(ns >= DUP_SHARE * tot and ratio is not None and DUP_LO <= ratio <= DUP_HI), ratio


def dup_runs(pattern, final_days):
    """Runs of copy days over the final days (ascending): ≥ 2 matching days in a row start one, 2 non-matching days in a
    row end it (unknown days change nothing). → [{"a", "b", "days", "open"}]."""
    runs, cur, pend, miss = [], None, [], 0
    for d in final_days:
        m = pattern.get(d, (None, None))[0]
        if m is None:
            continue
        if cur is None:
            if m:
                pend.append(d)
                if len(pend) >= DUP_RUN:
                    cur = {"a": pend[0], "b": pend[-1], "days": list(pend), "open": True}
                    runs.append(cur)
                    pend, miss = [], 0
            else:
                pend = []
        elif m:
            cur["days"].append(d)
            cur["b"], miss = d, 0
        else:
            miss += 1
            if miss >= DUP_END:
                cur["open"], cur, miss = False, None, 0
    return runs


def confirm_run(run, w_by_day, adm):
    """A run is CONFIRMED when, pooled over its days with complete AdMob, every labelled format (≥ DUP_FMT_MIN events
    either side) has GA4 ÷ AdMob within 0.85–1.15. No AdMob (no placements / no complete day) → not confirmed."""
    if not adm:
        return False
    g, a, n = {}, {}, 0
    for d in run["days"]:
        fi = adm.fmt_imp(d)
        w = w_by_day.get(d)
        if fi is None or w is None:
            continue
        n += 1
        for (u, f), c in w.items():
            if f not in ("notset", "fold"):
                g[f] = g.get(f, 0) + c
        for f, c in fi.items():
            a[f] = a.get(f, 0.0) + c
    if not n:
        return False
    checked = 0
    for f in set(g) | set(a):
        if g.get(f, 0) < DUP_FMT_MIN and a.get(f, 0) < DUP_FMT_MIN:
            continue
        checked += 1
        if not a.get(f) or not CONF_LO <= g.get(f, 0) / a[f] <= CONF_HI:
            return False
    return checked > 0


# ── the app's derived core ───────────────────────────────────────────────────────────────────

class App:
    """One app's core days, derived: calendar, visits, ads per grain, duplicates, the unit join, AdMob per unit, items."""

    def __init__(self, meta, days, now, dashboard=None, by_id=None, broken=None):
        dashboard = dashboard or {}
        self.meta, self.aid, self.key = meta, str(meta["app_id"]), gu.file_key(str(meta["app_id"]))
        self.td = _today(meta, now)
        self.ft = self.td - timedelta(days=2)
        # the users beside the ads (set_users): app daily users {day: n} and screen users {day: {class: n}} on final
        # days ≤ ftU, the Uninstall store's why when it gave none, and ftU (every status window ends there)
        self.au, self.su, self.auw, self.ftu = {}, {}, None, self.ft
        real = sorted(d for d, r in days.items() if r)
        self.d0 = real[0] if real else None
        # a core month file that cannot be read (broken: [(grp, month, error type)]) keeps its days on the calendar
        # (state "x"), from the reads' oldest filled day: the history never silently starts later
        for grp, m, _ in broken or ():
            if grp != "core":
                continue
            for i in lost_ids(meta, "core"):
                sp = lost_span(meta, i, m, self.td)
                if sp and (self.d0 is None or sp[0] < self.d0):
                    self.d0 = sp[0]
        self.days = _span(self.d0, self.td) if self.d0 else []
        self.final = [d for d in self.days if _d(d) <= self.ft]
        self.st = {i: {} for i in READ_IDS}
        self.ta, self.tv, self.vis, self.views, self.ads, self.w, self.rev = {}, {}, {}, {}, {}, {}, {}
        self.whole = {"v": set(), "a": set(), "w": set(), "m": set()}   # days a status row may use (GA4 grouped ≤
        #                                                                 FOLD_OK)
        for d in self.days:
            r = days.get(d) or {}
            for i in GROUPS["core"]:
                if i in r:
                    self.st[i][d] = _ch(r[i])
            for i in self.whole:
                if _whole(r.get(i)):
                    self.whole[i].add(d)
            ta, tv, _ = t_day(r.get("t"))
            if ta is not None:
                self.ta[d] = ta
            if tv is not None:
                self.tv[d] = tv
            v = v_day(r.get("v"))
            if v is not None:
                self.views[d] = v
                self.vis[d] = sum(x[0] for c, x in v.items() if kind(c) != "ad")
            a = a_day(r.get("a"))
            if a is not None:
                self.ads[d] = a
            w = w_day(r.get("w"))
            if w is not None:
                self.w[d] = w
            m = m_day(r.get("m"))
            if m is not None:
                self.rev[d] = m
        # … and those days are "x" before any row is judged: a status row's N/A names them, never "not read yet"
        mark_lost(self, [b for b in broken or () if b[0] == "core"], lambda i: self.st[i])
        # AdMob
        ids = admob_ids(meta, by_id)
        self.placements = app_placements(dashboard, ids)
        self.adm = Adm(self.placements, meta.get("time_zone") or "UTC", dashboard.get("report_tz") or "UTC",
                       dashboard.get("latest_complete") or "", dashboard.get("tz_by_account") or None)
        self._dups()
        self._units()
        self._classes()

    # duplicates
    def _dups(self):
        pat = {d: dup_pattern(self.w.get(d), self.ta.get(d)) for d in self.days}
        self.pattern = pat
        ftiso = _iso(self.ft)
        self.runs = dup_runs(pat, [d for d in self.final])
        for run in self.runs:
            run["ok"] = confirm_run(run, self.w, self.adm)
        self.dup = {}
        for run in self.runs:
            for d in run["days"]:
                self.dup[d] = 1 if run["ok"] else 2
        last_ok = bool(self.runs and self.runs[-1]["ok"])
        for d in self.days:
            if d > ftiso and pat[d][0]:                 # recent: provisional, that day's pattern only
                self.dup[d] = 1 if last_ok else 2
        self.removed = {}
        for d, stv in self.dup.items():
            if stv != 1:
                continue
            w = self.w.get(d)
            rm = 0
            if w is not None:
                for k in [k for k in w if k[1] == "notset" and unit_unset(k[0])]:
                    rm += w.pop(k)
            self.removed[d] = rm
            a = self.ads.get(d)
            if a is None:
                continue
            if a["g"] == "fu":
                for k in [k for k in a["cu"] if k[2] == "notset" and unit_unset(k[1])]:
                    n = a["cu"].pop(k)
                    a["cls"][k[0]][2] -= n
                    a["tot"][k[0]] -= n
            elif a["g"] == "f":
                for c, x in a["cls"].items():
                    a["tot"][c] -= x[2]
                    x[2] = 0
            else:
                a["tot"] = None                       # a copy cannot be told apart without a format
            if d in self.ta and "notset" in self.ta[d]:
                self.ta[d] = dict(self.ta[d], notset=max(0, self.ta[d]["notset"] - rm))

    # units: GA4 (name, fmt) ∪ AdMob-only, joined by name then id
    def _units(self):
        seen = set()
        for w in self.w.values():
            seen.update(w)
        for a in self.ads.values():
            if a["cu"]:
                seen.update((u, f) for (_, u, f) in a["cu"])
        by_name, by_id = {}, {}
        for pid, e in self.adm.ids.items():
            by_name.setdefault(e["name"].lower(), []).append(pid)
            by_id[pid] = e
        names = [u for u, _ in seen] + [e["name"] for e in self.adm.ids.values()]
        self.suffixes = suffix_tokens(names)
        units, used = [], set()
        for u, f in sorted(seen):
            ids, an, how = [], "", ""
            if not unit_unset(u) and u.lower() not in FOLD:
                if u.lower() in by_name:
                    ids, how = sorted(by_name[u.lower()]), "name"
                    an = by_id[ids[0]]["name"]
                elif u in by_id:
                    ids, how, an = [u], "id", by_id[u]["name"]
            used.update(ids)
            trig = trigger_label(u, an, how, self.suffixes) if f in FULL else ""
            units.append([u, f, ids, an, how, trig])
        left = {}
        for pid, e in sorted(by_id.items()):
            if pid not in used:
                left.setdefault((e["name"].lower(), e["fmt"]), []).append(pid)
        for (nm, f), ids in sorted(left.items()):
            an = by_id[ids[0]]["name"]
            units.append(["", f, sorted(ids), an, "admob", trigger_label(an, an, "name", self.suffixes)
                          if f in FULL else ""])
        self.units = units
        self.uix = {(u[0], u[1]): i for i, u in enumerate(units) if u[4] != "admob"}
        trig = {}
        for i, u in enumerate(units):
            if u[1] in FULL and u[4] != "admob":
                trig.setdefault((u[1], u[5]), []).append(i)
        self.trig = [[f, lab, ix] for (f, lab), ix in sorted(trig.items())]

    def unit_adm(self, ui, day):
        ids = self.units[ui][2]
        return self.adm.blend(ids, day) if ids and self.adm else None

    # screens / items
    def _classes(self):
        cls = set()
        for v in self.views.values():
            cls.update(v)
        for a in self.ads.values():
            cls.update(a["tot"] or {})
            cls.update(a["cls"] or {})
        for m in self.rev.values():
            cls.update(m)
        self.screens = sorted(cls)
        self.six = {c: i for i, c in enumerate(self.screens)}
        # top screens: the top 90 % of s-views in any calendar month with ≥ 1,000 app visits, or in the last 28 final days
        top = set()
        months = {}
        for d, v in self.views.items():
            months.setdefault(d[:7], []).append(d)

        def top90(ds):
            tot = {}
            for d in ds:
                for c, x in self.views[d].items():
                    if kind(c) == "s":
                        tot[c] = tot.get(c, 0) + x[0]
            s, cum, out = sum(tot.values()), 0, set()
            for c, n in sorted(tot.items(), key=lambda kv: (-kv[1], kv[0])):
                if s <= 0 or cum >= TOP_SHARE * s:
                    break
                out.add(c)
                cum += n
            return out
        for m, ds in months.items():
            if sum(self.vis.get(d, 0) for d in ds) >= TOP_MONTH_VISITS:
                top |= top90(ds)
        last = [d for d in _span(self.ft - timedelta(days=27), self.ft) if d in self.views]
        top |= top90(last)
        # by class name, never by the moving window's views: two screens swapping rank must not shift the item indexes
        # (every month's shard and summary would change); the page sorts rows by the period's views itself
        self.top = sorted(top)
        self.items = [[c, "s", "in"] for c in self.top] + [["Other screens", "o", "in"], ["Not recorded", "ns", "in"],
                                                           ["Ad screens", "ad", "in"], ["GA4 grouped", "g", "in"]]
        self.fs0 = len(self.items)
        self.items += [[lab, "fs", f] for f, lab, _ in self.trig]
        self.ditems = [[c, "s"] for c in self.top] + [["Other screens", "o"], ["Not recorded", "ns"], ["Ad screens", "ad"],
                                                      ["GA4 grouped", "g"]]
        self.dmap = {}
        n = len(self.top)
        tix = {c: i for i, c in enumerate(self.top)}
        for c in self.screens:
            k = kind(c)
            self.dmap[c] = tix[c] if c in tix else n + {"s": 0, "ns": 1, "ad": 2, "g": 3}[k]

    def item_of(self, c):
        """A class → its display item index (top screens, then Other / Not recorded / Ad screens / GA4 grouped)."""
        if c in self.dmap:
            return self.dmap[c]
        return len(self.top) + {"s": 0, "ns": 1, "ad": 2, "g": 3}[kind(c)]

    # windows
    def windows(self, ft=None):
        """W = the W_DAYS final days ending ft (default ftU: the last final day with both user reads), N the N_DAYS before."""
        ft = _d(ft or self.ftu)
        w = _span(ft - timedelta(days=W_DAYS - 1), ft)
        n = _span(ft - timedelta(days=W_DAYS + N_DAYS - 1), ft - timedelta(days=W_DAYS))
        return w, n

    def allf(self, ft=None):
        """Screen rows judged on ALL formats → 1: notset formats above 5 % of the app's ads in N or W (copy days
        included: an unconfirmed copy is the "Format not recorded" bucket, judged with the rest); else 2: over W ∪ N the
        whole ads-by-screen days GA4 gave without the format (grain c — on the biggest apps every screen × format
        split comes sampled, the screen totals whole) are more than ALLF_NOSPLIT of the whole ones (on app screens
        full-screen ads are a fraction of a percent of a screen's ads where the split is whole — allf_share — so a
        screen's all-format ads are its inline ads within that share); else 0."""
        w, n = self.windows(ft)
        if any((self._ns_fmt(ds, dup=True) or 0) > ALLF_SHARE for ds in (w, n)):
            return 1
        ds = [d for d in w + n if d in self.whole["a"] and d in self.ads]
        return 2 if ds and sum(1 for d in ds if self.ads[d]["g"] == "c") > ALLF_NOSPLIT * len(ds) else 0

    def allf_share(self, ft=None):
        """The measured full-screen share of all ads on app screens (kind "s") over the newest ≤ ALLF_FS_DAYS final
        days whose ads by screen are whole WITH the format (fu / f), 4 places; None when there is none."""
        ft, n, fs, tot = _iso(_d(ft or self.ftu)), 0, 0, 0
        for d in reversed(self.days):
            a = self.ads.get(d)
            if d > ft or d not in self.whole["a"] or not a or a["cls"] is None:
                continue
            for c, x in a["cls"].items():
                if kind(c) == "s":
                    fs += x[1]
                    tot += x[0] + x[1] + x[2]
            n += 1
            if n >= ALLF_FS_DAYS:
                break
        return _r(fs / tot, 4) if tot else None

    def _ns_fmt(self, ds, dup=False):
        """The notset-format share of the truth's ads over days ds; dup=False leaves out the duplicate-copy days (a
        steady copy is ~50 % notset by itself: its own start / end is what the guard watches, never its size)."""
        tot = ns = 0
        for d in ds:
            ta = self.ta.get(d)
            if ta and (dup or not self.dup.get(d)):
                tot += sum(ta.values())
                ns += ta.get("notset", 0)
        return ns / tot if tot else None

    def _cls_share(self, ds, k):
        tot = ns = 0
        for d in ds:
            a = self.ads.get(d)
            if a and a["tot"] is not None:
                for c, n in a["tot"].items():
                    tot += n
                    ns += n if kind(c) == k else 0
        return ns / tot if tot else None

    def _ns_cls(self, ds):
        """The unset-class share of the app's ads by screen."""
        return self._cls_share(ds, "ns")

    def _g_cls(self, ds):
        """The GA4 grouped "(other)" class share of the app's ads by screen (a screen's ads GA4 folded away)."""
        return self._cls_share(ds, "g")

    def guard(self, ft=None, screen=True):
        """The logging guard → why (N/A "Logging changed") or None: the unset-class share, the GA4 grouped class share
        (screen rows) or the notset-format share (outside duplicate-copy days) of the app's ads moved > 5 points between
        N and W, or is > 30 % in W, or a duplicate run starts / ends inside W ∪ N. Trigger rows keep the notset-format
        test: full-screen ads that lose their format leave the trigger groups."""
        w, n = self.windows(ft)
        tests = [("format not recorded", self._ns_fmt)] + ([("screen not recorded", self._ns_cls),
                                                            ("screen grouped by GA4", self._g_cls)] if screen else [])
        for what, fn in tests:
            sw, sn = fn(w), fn(n)
            if sw is not None and sw > LOG_MAX:
                return "Logging changed — %s %d%%" % (what, round(100 * sw))
            if sw is not None and sn is not None and abs(sw - sn) > LOG_SHIFT:
                return "Logging changed — %s %d%% → %d%%" % (what, round(100 * sn), round(100 * sw))
        a, b = n[0], w[-1]
        for run in self.runs:
            if a <= run["a"] <= b:
                return "Logging changed — duplicate ad_impression logging started %s" % run["a"]
            if not run["open"] and a <= run["b"] <= b:
                return "Logging changed — duplicate ad_impression logging ended %s" % run["b"]
        return None

    # a row's daily series
    def screen_series(self, c, allf):
        """{day: (views, ads)} of one screen class over the days its quantity exists (inline needs fu / f; all formats
        any grain; views need a usable visits read). Only days whose visits and ads-by-screen reads are whole (GA4
        grouped ≤ FOLD_OK): a screen's share GA4 folded into "(other)" is not on the screen that day (§0.3)."""
        out = {}
        for d in self.days:
            v, a = self.views.get(d), self.ads.get(d)
            if v is None or a is None or d not in self.whole["v"] or d not in self.whole["a"]:
                continue
            if allf:
                if a["tot"] is None:
                    continue
                q = a["tot"].get(c, 0)
            else:
                if a["cls"] is None:
                    continue
                q = a["cls"].get(c, [0, 0, 0])[0]
            out[d] = (v.get(c, [0, 0])[0], q)
        return out

    def trig_series(self, gi):
        """{day: (app visits, the group's ads)} over the days the units read is whole (GA4 grouped units ≤ FOLD_OK; app
        visits count every class, the grouped one too)."""
        uis = self.trig[gi][2]
        out = {}
        for d in self.days:
            w, vis = self.w.get(d), self.vis.get(d)
            if w is None or vis is None or d not in self.whole["w"]:
                continue
            out[d] = (vis, sum(w.get((self.units[u][0], self.units[u][1]), 0) for u in uis))
        return out

    # the app's ads of a row's kind per day: the materiality's whole (judge takes them over the row's own series days)
    def kind_ads(self, allf):
        """{day: the app's ads by screen} — every class's inline ads (a GA4 grouped format with them), or every format's
        when screen rows are judged on all formats — on the days the ads-by-screen read gives that quantity."""
        out = {}
        for d, a in self.ads.items():
            if allf and a["tot"] is not None:
                out[d] = sum(a["tot"].values())
            elif not allf and a["cls"] is not None:
                out[d] = sum(x[0] for x in a["cls"].values())
        return out

    def fmt_ads(self, f):
        """{day: the units read's ads of format f} (every trigger group of that format)."""
        return {d: sum(n for (u, g), n in w.items() if g == f) for d, w in self.w.items()}

    def day_why(self, d, fs=False):
        """Why a row's series lacks day d, from the day states this build ships: the first of the row's reads it cannot
        use gives its state — visits (whole; a full-screen row takes GA4 grouped visits too), then ads by screen / the
        units read (whole): "p" GA4 grouped, "s", "o", "t", "x" or "-" not read yet; a "-" under a truth that is not
        whole takes the truth's s / o / t / x (a split is read only after its truth); both usable → "f" (format not
        split: ads by screen without the format have no inline ads, nor all-format ones on a confirmed copy day). None
        (left out of the parts): no day of the row — before the app's first day d0 (where the page's coverage starts
        too), or a "-" before the read's history start once that read's history is done (GA4 has nothing to give)."""
        if not self.d0 or d < self.d0:
            return None
        for i in ("v", "w" if fs else "a"):
            s = self.st[i].get(d, "-")
            if s == "w" or fs and i == "v" and s == "p":
                continue
            if s == "-":
                t = self.st["t"].get(d, "-")
                if t in ("s", "o", "t", "x"):
                    return t
                o = _oldest(self.meta, i)
                if o and d < o and _read_of(self.meta, i).get("done"):
                    return None
            return s
        return "f"


# ── status (§3.2) ────────────────────────────────────────────────────────────────────────────

def _score(a, v, rn):
    return round(100 * (a / v) / rn) if v and rn else None


def _parts(states):
    """The states of the W days a row's series lacks → " (GA4 sampled 8 · not read yet 2)": the non-zero WHY_PARTS in
    their order ("" for none; None, no day of the row, is never counted)."""
    s = " · ".join("%s %d" % (lab, states.count(c)) for c, lab in WHY_PARTS if c in states)
    return " (%s)" % s if s else ""


def judge(series, w_days, n_days, guard=None, what="inline", full=False, miss=None, tot=None):
    """A row's {day: (V, A)} → its status {word, why, score, z, h, VW, AW, VN, AN, dW, dN, rw, rn}. First that applies:
    N/A Not whole · N/A Logging changed · N/A No ads · N/A Ads started · N/A Too few ads · Too early · Worse (score < 80,
    z ≤ −3, both halves < 90) · Watch (score < 90, z ≤ −WATCH_Z, both halves < 95) · Better (score > 110, z ≥ WATCH_Z,
    both halves > 105) · Normal. miss(day) → why the series lacks a W day (App.day_why): "Not whole" counts them by
    part. tot {day: the app's ads of the row's kind}: "Too few ads" when the row's share of them over its own series
    days stays under MAT_SHARE in W and in N (a row material in N that fell to 0 in W is still judged); "mat" = the
    larger share."""
    W = [(d, series[d]) for d in w_days if d in series]
    N = [(d, series[d]) for d in n_days if d in series]
    VW, AW = sum(v for _, (v, a) in W), sum(a for _, (v, a) in W)
    VN, AN = sum(v for _, (v, a) in N), sum(a for _, (v, a) in N)
    rw = AW / VW if VW else None
    rn = AN / VN if VN else None
    out = {"VW": VW, "AW": AW, "VN": VN, "AN": AN, "dW": len(W), "dN": len(N), "rw": rw, "rn": rn, "score": None,
           "z": None, "h": [None, None]}

    def done(word, why):
        out.update(word=word, why=why)
        return out
    if len(W) < MIN_A_W:
        parts = _parts([miss(d) for d in w_days if d not in series]) if miss else ""
        return done("N/A", "Not whole — %d whole days of %s ads in the last %d%s" % (len(W), what, W_DAYS, parts))
    if guard:
        return done("N/A", guard)
    noun = "full-screen" if full else what
    if AN == 0 and AW == 0:
        return done("N/A", "No %s ads" % noun)
    if AN == 0:
        return done("N/A", "Ads started — no %s ads in the %d days before" % (noun, N_DAYS))
    if tot is not None:
        sw, sn = sum(tot.get(d, 0) for d, _ in W), sum(tot.get(d, 0) for d, _ in N)
        out["mat"] = mat = max(AW / sw if sw else 0.0, AN / sn if sn else 0.0)
        if mat < MAT_SHARE:                      # (shown cut, never rounded up to the 1 % it is under; under 0.1 %
            pct = ("%.1f%%" % (math.floor(1000 * mat) / 10)) if mat >= 0.001 else "under 0.1%"    # never "0.0%")
            return done("N/A", "Too few ads — %s of the app's %s ads" % (pct, what))
    E = rn * VW if rn is not None else 0.0
    if len(N) < MIN_N:
        return done("Too early", "normal has %d whole days (needs %d)" % (len(N), MIN_N))
    if len(W) < MIN_W:
        return done("Too early", "last %d days have %d whole days (needs %d)" % (W_DAYS, len(W), MIN_W))
    if VN < MIN_VN:
        return done("Too early", "%d visits in the normal (needs %d)" % (VN, MIN_VN))
    if E < MIN_E:
        return done("Too early", "%d ads expected (needs %d)" % (round(E), MIN_E))
    ex = [(a - rn * v) ** 2 / (rn * v) for _, (v, a) in N if rn * v >= PHI_MIN_E]
    phi = max(1.0, sum(ex) / len(ex)) if ex else 1.0
    z = (AW - E) / math.sqrt(E * phi)
    score = _score(AW, VW, rn)
    halves = []
    w1 = [x for x in W if x[0] in set(w_days[:HALF])]
    w2 = [x for x in W if x[0] in set(w_days[HALF:])]
    for part in (w1, w2):
        v = sum(x[1][0] for x in part)
        halves.append(_score(sum(x[1][1] for x in part), v, rn) if v else None)
    out.update(score=score, z=round(z, 2), h=halves, phi=round(phi, 2))
    hs = [h for h in halves if h is not None]
    both = len(hs) == 2
    line = "ads/100 %s → %s · z %+.1f" % (_fmt100(rn), _fmt100(rw), z)
    if score < 80 and z <= -3 and both and all(h < 90 for h in hs):
        return done("Worse", line)
    if score < 90 and z <= -WATCH_Z and both and all(h < 95 for h in hs):
        return done("Watch", line)
    if score > 110 and z >= WATCH_Z and both and all(h > 105 for h in hs):
        return done("Better", line)
    return done("Normal", line)


def _fmt100(r):
    return "—" if r is None else ("%.1f" % (100 * r))


# ── status v2: impressions per user per day (owner, 6–7 Nov 2026) ─────────────────────────────────
# Kept above: judge() (ads per 100 visits, the previous status) for the backtest's comparison only.

def _q(v):
    """A per-user number as printed: three figures (4.52 · 0.318 · 12.4 · 1,234)."""
    if v is None:
        return "—"
    a = abs(v)
    if a >= 100:
        return "{:,}".format(int(round(v)))
    return ("%.1f" if a >= 10 else "%.2f" if a >= 1 else "%.3f") % v


def _sgn(x, fmt_="%.0f"):
    """A signed number with a real minus ("−12", "+2.4")."""
    t = fmt_ % abs(x)
    return ("−" if x < 0 and t.strip("0.") else "+") + t


def _pc(x, dp=0):
    """A change (a ratio − 1) as a signed percent: "−12%", "+2.0%"."""
    return "—" if x is None else _sgn(100 * x, "%%.%df" % dp) + "%"


def _ft(sec):
    """Seconds as the page prints them: "40s", "2m 10s", "1h 05m"."""
    if sec is None:
        return "—"
    t = int(round(sec))
    if t < 60:
        return "%ds" % t
    if t < 3600:
        return "%dm %02ds" % (t // 60, t % 60)
    m = int(round(sec / 60))
    return "%dh %02dm" % (m // 60, m % 60)


def _base_word(score, z, h):
    """The shipped thresholds on a per-user score, plus the collapse rule (a stop is never held by z alone)."""
    hs = [x for x in h if x is not None]
    both = len(hs) == 2
    if score < 80 and z <= -3 and both and all(x < 90 for x in hs):
        return "Worse"
    if score < 90 and z <= -WATCH_Z and both and all(x < 95 for x in hs):
        return "Watch"
    if score > 110 and z >= WATCH_Z and both and all(x > 105 for x in hs):
        return "Better"
    if score <= COLLAPSE[0] and z <= -COLLAPSE[2] and both and all(x <= COLLAPSE[1] for x in hs):
        return "Worse"
    return "Normal"


ROW_NOUN = {"s": "imp/screen user", "t": "imp/app user", "a": "imp/user"}


def _lm(x, y):
    """ln(x / y), or None unless both are > 0."""
    return math.log(x / y) if x and y and x > 0 and y > 0 else None


def _parts_of(kind, rw, rn, f):
    """The exact parts of rw − rn in % of rn (they add up to 100 × (rw / rn − 1)): f = {part: (W value, N value)} whose
    product is the rate. None when a factor is 0 on a side (the LMDI weight needs both)."""
    if not rw or not rn or any(_lm(a, b) is None for a, b in f.values()):
        return None
    L = _L(rw, rn)
    return {k: round(100 * L * _lm(a, b) / rn, 1) for k, (a, b) in f.items()}


def judge_u(series, w_days, n_days, guard=None, what="inline", kind="s", app_rn=None, au=None, vapp=None, miss=None,
            tot=None, eng=None):
    """A row's {day: (views, ads, users)} on its whole days → its status (dict). users = the screen's own users (kind
    "s"), the app's daily users for a trigger ("t") and the App row ("a"); a whole day with 0 users is (0, 0, 0): a day
    that adds to no sum. First that applies: N/A Not whole (< MIN_A_W whole days in W; why by part, "u" users not in
    yet) · N/A the guard · N/A No ads / Ads started · N/A Too few ads (tot) · N/A No visits in the last 10 days (ads in
    N, no users in W) · Too early · the base word (_base_word). Then held as Normal: "small" (|impact| under IMP_MAT of
    the APP's total imp / user: impact = (AW − rn·UW) ÷ (app_rn · the app's daily users over the row's W days); screens
    and triggers) · "app-wide" (triggers only: the score net of the app-wide app-views-per-user change, own, ≥ OWN_FOLD
    for a down word, ≤ 200 − OWN_FOLD for Better). The 2-day confirm is statuses'. eng {day: engagement seconds}: a
    screen's time parts."""
    au, vapp = au or {}, vapp or {}
    W = [(d,) + tuple(series[d]) for d in w_days if d in series]
    N = [(d,) + tuple(series[d]) for d in n_days if d in series]
    VW, AW, UW = (sum(x[j] for x in W) for j in (1, 2, 3))
    VN, AN, UN = (sum(x[j] for x in N) for j in (1, 2, 3))
    out = {"VW": VW, "AW": AW, "UW": UW, "VN": VN, "AN": AN, "UN": UN, "dW": len(W), "dN": len(N), "rw": None,
           "rn": None, "score": None, "z": None, "h": [None, None], "imp": None, "own": None, "reach": None,
           "parts": None, "base": None, "hold": None, "kind": kind}

    def done(word, why, base=None):
        out.update(word=word, why=why, base=base or word)
        return out
    if len(W) < MIN_A_W:
        parts = _parts([miss(d) for d in w_days if d not in series]) if miss else ""
        noun = ("%s " % what) if what else ""
        return done("N/A", "Not whole — %d whole days of %sads in the last %d%s" % (len(W), noun, W_DAYS, parts))
    if guard:
        return done("N/A", guard)
    noun = "full-screen " if kind == "t" else ("%s " % what if what else "")
    if AN == 0 and AW == 0:
        return done("N/A", "No %sads" % noun)
    if AN == 0:
        return done("N/A", "Ads started — no %sads in the %d days before" % (noun, N_DAYS))
    if tot is not None:
        sw, sn = sum(tot.get(x[0], 0) for x in W), sum(tot.get(x[0], 0) for x in N)
        out["mat"] = mat = max(AW / sw if sw else 0.0, AN / sn if sn else 0.0)
        if mat < MAT_SHARE:
            pct = ("%.1f%%" % (math.floor(1000 * mat) / 10)) if mat >= 0.001 else "under 0.1%"
            return done("N/A", "Too few ads — %s of the app's %s ads" % (pct, what))
    if not UW:
        return done("N/A", "No visits in the last %d days" % W_DAYS)
    if not UN:
        return done("N/A", "No visits in the %d days before" % N_DAYS)
    rn, rw = AN / UN, AW / UW
    E = rn * UW
    out.update(rn=rn, rw=rw)
    if len(N) < MIN_N:
        return done("Too early", "normal has %d whole days (needs %d)" % (len(N), MIN_N))
    if len(W) < MIN_W:
        return done("Too early", "last %d days have %d whole days (needs %d)" % (W_DAYS, len(W), MIN_W))
    if VN < MIN_VN:
        return done("Too early", "%d views in the normal (needs %d)" % (VN, MIN_VN))
    if E < MIN_E:
        return done("Too early", "%d ads expected (needs %d)" % (round(E), MIN_E))
    ex = [(a - rn * u) ** 2 / (rn * u) for _, v, a, u in N if rn * u >= PHI_MIN_E]
    phi = max(1.0, sum(ex) / len(ex)) if ex else 1.0
    z = (AW - E) / math.sqrt(E * phi)
    score = round(100 * rw / rn)
    halves = []
    for part in (set(w_days[:HALF]), set(w_days[HALF:])):
        pu = sum(x[3] for x in W if x[0] in part)
        pa = sum(x[2] for x in W if x[0] in part)
        halves.append(round(100 * (pa / pu) / rn) if pu else None)
    out.update(score=score, z=round(z, 2), h=halves, phi=round(phi, 2))
    # the app's daily users and app views on the row's own days: impact, the fold, reach, the parts
    DW, DN = sum(au.get(x[0], 0) for x in W), sum(au.get(x[0], 0) for x in N)
    PW, PN = sum(vapp.get(x[0], 0) for x in W), sum(vapp.get(x[0], 0) for x in N)
    if kind == "a":
        imp = rw / rn - 1
    else:
        imp = (AW - rn * UW) / (app_rn * DW) if app_rn and DW else None
    out["imp"] = None if imp is None else round(imp, 5)
    depth = _lm(PW / DW, PN / DN) if DW and DN and PW and PN else None
    if kind == "t" and depth is not None:
        out["own"] = round(score / math.exp(depth))
    if kind == "s" and DW and DN:
        out["reach"] = [round(UW / DW, 4), round(UN / DN, 4)]
    if kind == "s":
        GW = sum((eng or {}).get(x[0], 0) for x in W)
        GN = sum((eng or {}).get(x[0], 0) for x in N)
        if GW > 0 and GN > 0 and VW and VN:
            f = {"vpu": (VW / UW, VN / UN), "tpv": (GW / VW, GN / VN), "apm": (60 * AW / GW, 60 * AN / GN)}
            out["G"] = [GW, GN]
        else:
            f = {"vpu": (VW / UW, VN / UN), "adv": (AW / VW if VW else 0, AN / VN if VN else 0)}
    else:
        f = {"avu": (PW / UW, PN / UN), "adv": (AW / PW if PW else 0, AN / PN if PN else 0)}
    out["parts"] = _parts_of(kind, rw, rn, f)
    base = _base_word(score, z, halves)
    line = "%s %s → %s (%s) · z %s" % (ROW_NOUN[kind], _q(rn), _q(rw), _pc(rw / rn - 1), _sgn(z, "%.1f"))
    word, why = base, line
    if base in ("Worse", "Watch", "Better") and kind != "a":
        down = base != "Better"
        if imp is not None and (imp > -IMP_MAT if down else imp < IMP_MAT):
            word, why, out["hold"] = "Normal", line + " · small — %s of the app's imp / user" % _pc(imp, 1), "small"
        elif out["own"] is not None and (out["own"] >= OWN_FOLD if down else out["own"] <= 200 - OWN_FOLD):
            word, why, out["hold"] = ("Normal", line + " · app-wide — users open %s screens (see App total)"
                                      % ("fewer" if down else "more"), "fold")
    return done(word, why, base)


def _fam(w):
    return "F" if w in FLAGS else "B" if w == "Better" else None


def _confirm(st, prev):
    """The 2-day confirm: a flag (Worse / Watch, or Better) shows only when the same family stood on each of the
    CONFIRM_DAYS − 1 final days before (their words after the holds) — else Normal "first day — confirms tomorrow"."""
    f = _fam(st["word"])
    if f and any(_fam(p) != f for p in prev):
        st = dict(st, word="Normal", why=st["why"] + " · first day — confirms tomorrow", hold="confirm")
    return st


# ── the users beside the ads ─────────────────────────────────────────────────────────────────

def screen_users(app, data_dir, recent):
    """The users by screen → {day: {class: users}} on the final days whose uV record is whole (GA4's activeUsers by
    screen class: unique within one day and one screen). Read beside small_days, never through it: each small month's
    cache "u" + "cls" / "map" when the cache is that store file's (its sha1), else that month's uV records only; then
    recent.json the way small_days takes it (a recent record replaces the month's: whole or not). Registers NO class
    (app.six untouched: small_days' registration order — and the shards' screen indexes — stay as they are)."""
    out, ft = {}, _iso(app.ft)
    if not app.d0:
        return out
    td = _iso(app.td)
    for m in _months(data_dir, app.key, "small", app.meta):
        try:
            with open(_month_path(data_dir, app.key, "small", m), "rb") as f:
                b = f.read()
        except OSError:
            continue                                   # (small_days counts it: one health line per build)
        lo, hi = max(app.d0, m + "-01"), min(_month_end(m), td)
        c = _cache_get(data_dir, app.key, "small", m, _sha(b))
        if c is not None and c.get("sv") == SMALL_V and [c.get("lo"), c.get("hi")] == [lo, hi] \
                and isinstance(c.get("u"), dict) and len(c.get("cls") or ()) == len(c.get("map") or ()):
            inv = dict(zip(c["map"], c["cls"]))
            if all(si in inv for rows in c["u"].values() for si, _ in rows):
                for d, rows in c["u"].items():
                    out[d] = {inv[si]: n for si, n in rows}
                continue
        try:
            days = _parse_month(b)
        except Exception:
            continue
        for d, recs in days.items():
            if isinstance(recs, dict) and lo <= d <= hi and _whole(recs.get("uV")):
                out[d] = _uv_rows(recs["uV"])
    for d, recs in recent.items():
        if not isinstance(recs, dict) or not app.d0 <= d <= td or "uV" not in recs:
            continue
        if _whole(recs["uV"]):
            out[d] = _uv_rows(recs["uV"])
        else:
            out.pop(d, None)
    return {d: u for d, u in out.items() if d <= ft}


def _uv_rows(rec):
    out = {}
    for r in rec.get("r") or []:
        try:
            out[str(r[0] or "")] = _i(r[2])
        except (IndexError, TypeError, ValueError):
            continue
    return out


def set_users(app, au, auw, su):
    """ftU = the last final day on which both the app's daily users and a whole screen users read are in (≤ ft; one
    end per app: every status window, the confirm and every per-user period end there); app.au / app.su cut to it."""
    ft = _iso(app.ft)
    a = [d for d, n in (au or {}).items() if d <= ft and n]
    s = [d for d in (su or {}) if d <= ft]
    ends = [max(x) for x in (a, s) if x]
    app.ftu = _d(min(ends)) if ends else app.ft
    f = _iso(app.ftu)
    app.au = {d: n for d, n in (au or {}).items() if d <= f and n}
    app.su = {d: u for d, u in (su or {}).items() if d <= f}
    app.auw = None if app.au else (auw or "none")
    return app.ftu


def stale_users(app):
    """True when the users behind this app's numbers are late or missing: no daily users (none / another stream / GA4
    cut the report), ftU more than a day before ft (the users read stopped), or daily users but no whole screen users
    day at all once the app has 3 final days (a new read, or one always thresholded / sampled: ftU then ends on the
    last daily users day, so no lag shows, yet every screen row is N/A)."""
    return not app.au or (app.ft - app.ftu).days > 1 or (not app.su and len(app.final) >= 3)


def screen_series_u(app, c, allf):
    """{day: (views, ads, users)} of one screen class on its whole days ≤ ftU (screen_series' days whose users read is
    whole too; a whole day without users of the screen → (0, 0, 0)), and screen_series' own days (the "u" why)."""
    base = app.screen_series(c, allf)
    out = {}
    for d, (v, a) in base.items():
        u = app.su.get(d)
        if u is None:
            continue
        n = u.get(c, 0)
        out[d] = (v, a, n) if n > 0 else (0, 0, 0)
    return out, base


def trig_series_u(app, gi):
    """{day: (app visits, the trigger group's ads, the app's daily users)} on the units read's whole days with users."""
    base = app.trig_series(gi)
    return {d: (v, a, app.au[d]) for d, (v, a) in base.items() if d in app.au}, base


def app_series(app):
    """The App row: {day: (app visits, GA4's ads — inline + full-screen + not recorded, not recorded left out on copy
    days AdMob did not confirm, dup 2 — , the app's daily users)} and {day: (inline, full, counted not recorded)}."""
    ser, fm = {}, {}
    for d, t in app.ta.items():
        if d not in app.vis or d not in app.au:
            continue
        il = sum(n for f, n in t.items() if fgroup(f) == 0)
        fl = sum(n for f, n in t.items() if fgroup(f) == 1)
        ns = t.get("notset", 0) if app.dup.get(d) != 2 else 0
        ser[d] = (app.vis[d], il + fl + ns, app.au[d])
        fm[d] = (il, fl, ns)
    return ser, fm


def _app_guard(app, w, n):
    """The App row's guard: a duplicate ad_impression run starting / ending inside W ∪ N only."""
    a, b = n[0], w[-1]
    for run in app.runs:
        if a <= run["a"] <= b:
            return "Logging changed — duplicate ad_impression logging started %s" % run["a"]
        if not run["open"] and a <= run["b"] <= b:
            return "Logging changed — duplicate ad_impression logging ended %s" % run["b"]
    return None


def _adm_fmt(app):
    """{GA4 day: (AdMob inline, AdMob full-screen impressions)} on the final days AdMob is complete for."""
    out = {}
    if not app.adm:
        return out
    for d in app.final:
        m = app.adm.fmt_imp(d)
        if m is not None:
            out[d] = (sum(v for f, v in m.items() if f not in FULL), sum(v for f, v in m.items() if f in FULL))
    return out


def app_judge(app, w, n, aser, gfmt, afmt):
    """The App row at one anchor: judge_u on GA4 ÷ the app's daily users (guard: duplicate runs only), then the AdMob
    check on a flagged word — the driving format (the one that moved most toward the word), its AdMob change per daily
    user put in GA4's place: still < 90 (Worse / Watch) or > 110 (Better) → the word stands ("AdMob agrees"); else the
    row is judged on AdMob per daily user (inline + full-screen, AdMob-complete days) with the same rules — "(AdMob)",
    why "GA4 +x% ≠ AdMob −y%" — and only when that cannot be judged N/A "Not measurable (GA4 ≠ AdMob)". Fewer than
    ADM_MIN_W / ADM_MIN_N AdMob days: the word stands, "AdMob not checked". → the status (+ "adm")."""
    miss = lambda d: "u" if d in app.ta and d in app.vis else app.st["t"].get(d, "-")
    st = judge_u(aser, w, n, _app_guard(app, w, n), "", "a", None, app.au, app.vis, miss)
    Wd, Nd = [d for d in w if d in aser], [d for d in n if d in aser]
    U_ = {s: sum(aser[d][2] for d in ds) for s, ds in (("W", Wd), ("N", Nd))}
    G = {s: [sum(gfmt[d][j] for d in ds) for j in range(3)] for s, ds in (("W", Wd), ("N", Nd))}
    dW, dN = len(Wd), len(Nd)
    st["dau"] = round((U_["W"] / dW) / (U_["N"] / dN) - 1, 4) if dW and dN and U_["W"] and U_["N"] else None
    if st["score"] is not None and st["dau"] is not None and abs(st["dau"]) > DAU_MOVE:
        x = 1 + st["dau"]
        st["why"] += " · daily users ×%s" % (("%.1f" if x >= 1 else "%.2f") % x)
    aw, an = [d for d in Wd if d in afmt], [d for d in Nd if d in afmt]
    Ua = {"W": sum(aser[d][2] for d in aw), "N": sum(aser[d][2] for d in an)}
    gA = {s: [sum(gfmt[d][j] for d in ds) for j in range(3)] for s, ds in (("W", aw), ("N", an))}   # (+ not recorded)
    aA = {s: [sum(afmt[d][j] for d in ds) for j in range(2)] for s, ds in (("W", aw), ("N", an))}
    ok = len(aw) >= ADM_MIN_W and len(an) >= ADM_MIN_N and Ua["W"] and Ua["N"]
    ch = lambda X, j: ((X["W"][j] / Ua["W"]) / (X["N"][j] / Ua["N"]) - 1) if ok and X["N"][j] else None
    tot = lambda X: ((sum(X["W"]) / Ua["W"]) / (sum(X["N"]) / Ua["N"]) - 1) if ok and sum(X["N"]) else None
    adm = {"st": "none" if not app.adm else "short" if not ok else "ok", "gt": _r(tot(gA), 4), "mt": _r(tot(aA), 4)}
    st["adm"] = adm
    if st["base"] not in ("Worse", "Watch", "Better"):
        return st
    if not ok:
        st["why"] += " · AdMob not checked"
        adm["st"] = "unchecked"
        return st
    down = st["base"] != "Better"
    dI = G["W"][0] / U_["W"] - G["N"][0] / U_["N"]
    dF = G["W"][1] / U_["W"] - G["N"][1] / U_["N"]
    drv = (0 if dI <= dF else 1) if down else (0 if dI >= dF else 1)
    g, m = ch(gA, drv), ch(aA, drv)
    adm.update(f="inline" if drv == 0 else "full", g=_r(g, 4), m=_r(m, 4))
    if g is None or m is None:
        st["why"] += " · AdMob not checked"
        adm["st"] = "unchecked"
        return st
    tw, tn = sum(G["W"]) / U_["W"], sum(G["N"]) / U_["N"]
    sa = 100 * (tw - G["W"][drv] / U_["W"] + G["N"][drv] / U_["N"] * (1 + m)) / tn
    adm["sa"] = round(sa)
    if sa < 90 if down else sa > 110:
        adm["st"] = "agree"
        st["why"] += " · AdMob agrees (%s %s)" % (adm["f"], _pc(m))
        return st
    # GA4 ≠ AdMob: the App row on AdMob per daily user (inline + full-screen), the same rules
    gt, mt = adm["gt"], adm["mt"]
    tail = "GA4 %s ≠ AdMob %s — GA4 logging changed" % (_pc(gt), _pc(mt))
    aser2 = {d: (aser[d][0], afmt[d][0] + afmt[d][1], aser[d][2]) for d in aser if d in afmt}
    s2 = judge_u(aser2, w, n, None, "", "a", None, app.au, app.vis)
    if s2["word"] in JUDGED:
        s2.update(why="AdMob " + s2["why"] + " · " + tail, adm=dict(adm, st="admob"), dau=st["dau"], ga4=st)
        return s2
    st.update(word="N/A", why="Not measurable (GA4 ≠ AdMob) — " + tail, adm=dict(adm, st="na"))
    return st


# ── cause (§3.3) ─────────────────────────────────────────────────────────────────────────────

def _L(a, b):
    """The logarithmic mean (LMDI-I weight)."""
    if a == b:
        return a
    return (a - b) / (math.log(a) - math.log(b))


def lmdi(units, vapp, vrow):
    """An exact split of Δrate = rate_W − rate_N of one row over its units.
    units: {u: {"W": {"g", "G", "imp", "mt", "req"}, "N": {…}, "admob": bool}}; vapp / vrow: {"W": visits, "N": visits}.
    rate_u = g / V_row = tie × σ × show × fill × (req / V_app) × (V_app / V_row) with tie = G ÷ imp, σ = g ÷ G,
    show = imp ÷ matched, fill = matched ÷ req. Term k = Σ_u L(rate_u^W, rate_u^N) × ln(x_k^W ÷ x_k^N). A unit that is not
    in both windows (or has a zero factor) goes whole into "units"; a unit with no AdMob id into "unmatched". The terms
    add up to Δrate exactly. → (terms, Δrate, rate_W, rate_N)."""
    terms = {k: 0.0 for k in TERMS}
    rw = sum(u["W"]["g"] for u in units.values()) / vrow["W"] if vrow["W"] else 0.0
    rn = sum(u["N"]["g"] for u in units.values()) / vrow["N"] if vrow["N"] else 0.0
    for u in units.values():
        x = {}
        for s in ("W", "N"):
            q = u[s]
            x[s] = q["g"] / vrow[s] if vrow[s] else 0.0
        if not u.get("admob"):
            terms["unmatched"] += x["W"] - x["N"]
            continue
        f = {}
        okf = vrow["W"] and vrow["N"] and vapp["W"] and vapp["N"]
        for s in ("W", "N"):
            q = u[s]
            vals = [q["G"] / q["imp"] if q["imp"] else 0, q["g"] / q["G"] if q["G"] else 0,
                    q["imp"] / q["mt"] if q["mt"] else 0, q["mt"] / q["req"] if q["req"] else 0,
                    q["req"] / vapp[s] if vapp[s] else 0, vapp[s] / vrow[s] if vrow[s] else 0]
            f[s] = vals
            okf = okf and all(v > 0 for v in vals) and x[s] > 0
        if not okf:
            terms["units"] += x["W"] - x["N"]
            continue
        L = _L(x["W"], x["N"])
        for k, a, b in zip(("tie", "share", "show", "fill", "req", "vis"), f["W"], f["N"]):
            terms[k] += L * math.log(a / b)
    return terms, rw - rn, rw, rn


def cause_label(terms, rn):
    """The most negative term if ≤ −10 % of rate_N; "Mixed: A + B" when the second is ≤ −10 % and ≥ 0.6 × the first in
    size; else "No single cause"."""
    if not rn:
        return "No single cause"
    neg = sorted(((v / rn, k) for k, v in terms.items() if v / rn <= -TERM_MIN), key=lambda t: t[0])
    if not neg:
        return "No single cause"
    if len(neg) > 1 and abs(neg[1][0]) >= MIXED * abs(neg[0][0]):
        return "Mixed: %s + %s" % (TERM_LABEL[neg[0][1]], TERM_LABEL[neg[1][1]])
    return TERM_LABEL[neg[0][1]]


def row_units(app, row, days):
    """The row's units over days → {ui: [GA4 ads on the row, GA4 ads of the unit (all screens)]} and the row's visits."""
    out, vrow, vapp = {}, 0, 0
    for d in days:
        w = app.w.get(d)
        if row[0] == "s":
            a, v = app.ads.get(d), app.views.get(d)
            vrow += v.get(row[1], [0, 0])[0]
            for (c, u, f), n in a["cu"].items():
                if c == row[1] and fgroup(f) in ((0,) if not row[2] else (0, 1, 2)):
                    ui = app.uix.get((u, f))
                    if ui is not None:
                        out.setdefault(ui, [0, 0])[0] += n
        else:
            vrow += app.vis.get(d, 0)
            for ui in app.trig[row[1]][2]:
                out.setdefault(ui, [0, 0])[0] += w.get((app.units[ui][0], app.units[ui][1]), 0)
        vapp += app.vis.get(d, 0)
    for ui in out:
        u = app.units[ui]
        out[ui][1] = sum((app.w.get(d) or {}).get((u[0], u[1]), 0) for d in days)
    return out, vrow, vapp


def cause(app, row, st, ft=None):
    """A judged row → {"cause", "terms" (% of rate_N), "abs", "units": [[ui, reqW/day, reqN/day, fillW, fillN, showW,
    showN, tieW, tieN]], "dr", "rn"}. row = ("s", class, allf) | ("t", trigger index)."""
    w_days, n_days = app.windows(ft)
    out = {"cause": "", "terms": None}
    if not app.adm:
        out["cause"] = "Not measurable (no AdMob data)"
        return out
    cw = [d for d in w_days if app.adm.complete(d)]
    if len(cw) < ADM_MIN_DAYS:
        out["cause"] = "Waiting for AdMob data"
        return out
    cn = [d for d in n_days if app.adm.complete(d)]

    def usable(d):                                    # the status rows' whole days (GA4 grouped ≤ FOLD_OK)
        if d not in app.w or d not in app.vis or d not in app.whole["w"]:
            return False
        if row[0] == "s":
            a = app.ads.get(d)
            return bool(a and a["g"] == "fu" and d in app.views and d in app.whole["a"] and d in app.whole["v"])
        return True
    W = [d for d in cw if usable(d)]
    N = [d for d in cn if usable(d)]
    if row[0] == "s" and (len(W) < FU_MIN_W or len(N) < FU_MIN_N):
        out["cause"] = "Not measurable (units not split)"
        return out
    gw, vrw, vaw = row_units(app, row, W)
    gn, vrn, van = row_units(app, row, N)
    uis = sorted(set(gw) | set(gn))

    def adm_sum(ui, days):
        s = [0.0, 0.0, 0.0]
        for d in days:
            v = app.unit_adm(ui, d)
            if v:
                for j in range(3):
                    s[j] += v[j]
        return s
    units, stats, bad, unm, rows_ads = {}, [], 0, 0, 0
    reqd = {}
    for ui in uis:
        q = {}
        for s, gg, ds in (("W", gw, W), ("N", gn, N)):
            req, mt, imp = adm_sum(ui, ds)
            q[s] = {"g": gg.get(ui, [0, 0])[0], "G": gg.get(ui, [0, 0])[1], "req": req, "mt": mt, "imp": imp}
        units[ui] = dict(q, admob=bool(app.units[ui][2]))
        rw_, rn_ = adm_sum(ui, cw)[0] / len(cw), (adm_sum(ui, cn)[0] / len(cn) if cn else 0.0)
        reqd[ui] = (rw_, rn_)
        ties = []
        for s in ("W", "N"):
            g_, imp = q[s]["G"], q[s]["imp"]
            ties.append(None if g_ + imp < TIE_MIN_N else (g_ / imp if imp else float("inf")))
        tot = q["W"]["g"] + q["N"]["g"]
        rows_ads += tot
        if not units[ui]["admob"]:
            unm += tot                                 # no AdMob id: GA4's unit name found no AdMob unit (no tie)
        elif any(t is not None and not TIE_LO <= t <= TIE_HI for t in ties):
            bad += tot
        f = lambda a, b: _r(a / b, 3) if b else None
        stats.append([ui, _r(rw_, 1), _r(rn_, 1), f(q["W"]["mt"], q["W"]["req"]), f(q["N"]["mt"], q["N"]["req"]),
                      f(q["W"]["imp"], q["W"]["mt"]), f(q["N"]["imp"], q["N"]["mt"]),
                      None if ties[0] in (None, float("inf")) else _r(ties[0], 3),
                      None if ties[1] in (None, float("inf")) else _r(ties[1], 3)])
    out["units"] = stats
    if rows_ads and unm + bad > UNTIED_SHARE * rows_ads:
        out["cause"] = ("Not measurable (GA4 unit names don't match AdMob)" if unm > bad else
                        "Not measurable (GA4 and AdMob disagree for these units)")
        return out
    # 1. unit changes first
    an = sum(u["N"]["g"] for u in units.values())
    stopped = [ui for ui, (w_, n_) in reqd.items() if n_ >= STOP_REQ and w_ < STOP_FRAC * n_]
    started = [ui for ui, (w_, n_) in reqd.items() if n_ < STOP_FRAC * w_ and w_ >= STOP_REQ]
    if stopped and an and sum(units[u]["N"]["g"] for u in stopped) >= STOP_SHARE * an:
        top = max(stopped, key=lambda u: units[u]["N"]["g"])
        nm = lambda u: app.units[u][0] or app.units[u][3]
        repl = [u for u in started if app.units[u][1] == app.units[top][1] and units[u]["W"]["g"] > 0]
        out["cause"] = ("Ad unit changed: %s → %s" % (nm(top), nm(repl[0]))) if repl else "Ad unit stopped: %s" % nm(top)
        out["stopped"], out["started"] = stopped, started
        stop = None                                    # the first day from which its requests stay < 10 % of N's
        for d in reversed(sorted(cn + cw)):
            v = app.unit_adm(top, d)
            if v is not None and v[0] < STOP_FRAC * reqd[top][1]:
                stop = d
            elif v is not None:
                break
        out["stop_day"] = stop
    # 2. the exact split
    terms, dr, rw, rn = lmdi(units, {"W": vaw, "N": van}, {"W": vrw, "N": vrn})
    out.update(abs={k: _r(v, 8) for k, v in terms.items()}, dr=_r(dr, 8), rn=_r(rn, 8), rw=_r(rw, 8),
               terms={k: (_r(100 * v / rn, 1) if rn else None) for k, v in terms.items()})
    if not out["cause"]:
        out["cause"] = cause_label(terms, rn)
    return out


def cause_u(st, cz):
    """A judged row's cause: the most negative part of its per-user change (≤ −10 % of normal) → its label (views per
    user "Users open it fewer times" · time per view "Users stay shorter" · app views per user "Users open fewer
    screens"); the ad-logic part (ads per minute / per view) → the AdMob cause of `cause()` (cz: a stopped / changed
    unit, the exact per-visit split, or why it cannot be measured); no ads in W → "Ads stopped" (or the stopped unit)."""
    cz = cz or {}
    c = cz.get("cause") or ""
    if st.get("rn") and not st["AW"]:
        return c if c.startswith("Ad unit") else "Ads stopped"
    neg = sorted((v, k) for k, v in (st.get("parts") or {}).items() if v <= -100 * TERM_MIN)
    if not neg:
        return "No single cause"
    k = neg[0][1]
    if k in PART_LABEL:
        return PART_LABEL[k]
    if st.get("kind") == "a":
        return ""
    return c or "No single cause"


def cause_group(label):
    """The Needs attention group of a cause label: "Mixed: A + B" → A, "Ad unit stopped: x" → "Ad unit stopped"."""
    label = label or ""
    if label.startswith("Mixed: "):
        return label[7:].split(" + ")[0]
    return label.split(":")[0] if ":" in label else label


def first_bad_day(series, final_days, rn):
    """The first final day from which the daily rate per user stays < 90 % of the normal (to the row's last day with
    users), or None. series {day: (views, ads, users)}; a day without users is skipped."""
    if not rn:
        return None
    fb = None
    for d in reversed(final_days):
        if d not in series:
            continue
        v, a, u = series[d]
        if not u:
            continue
        if a / u < BAD_RATE * rn:
            fb = d
        else:
            break
    return fb


# ── the developer report (§3.4: English, no money) ───────────────────────────────────────────

def _n(v):
    return "—" if v is None else "{:,}".format(int(round(v)))


def _p(v):
    return "—" if v is None else "%.2f" % v


def _part_line(st):
    """ "views per user −12.0 (4.10 → 3.60) · time per view +2.4 (2m 10s → 2m 15s) · ads per minute −20.0 (…)" """
    p = st.get("parts") or {}
    VW, VN, UW, UN, AW, AN = (st[k] for k in ("VW", "VN", "UW", "UN", "AW", "AN"))
    G = st.get("G") or [0, 0]
    val = {"vpu": (VN / UN, VW / UW, _q), "tpv": (G[1] / VN if VN else None, G[0] / VW if VW else None, _ft),
           "apm": (60 * AN / G[1] if G[1] else None, 60 * AW / G[0] if G[0] else None, _q),
           "adv": (AN / VN if VN else None, AW / VW if VW else None, _q)}
    out = []
    for k in ("vpu", "tpv", "apm", "adv", "avu"):
        if k not in p:
            continue
        if k in val:
            n, w, f = val[k]
            out.append("%s %s (%s → %s)" % (PART_NAME[k], _sgn(p[k], "%.1f"), f(n), f(w)))
        else:
            out.append("%s %s" % (PART_NAME[k], _sgn(p[k], "%.1f")))
    return " · ".join(out)


def row_report(app, label, what, st, cz, series, fbd, ver=None, cc=None, versions=None, ab=None):
    """One judged row → its report block (text, English, no money). label: the Activity class or "format · trigger";
    what: "screen" / "full-screen trigger". The numbers are impressions per user per day: the screen's own users, or the
    app's daily users for a trigger; versions and countries stay per 100 visits (GA4 gives no users by them here)."""
    w, n = app.windows()
    rn, rw = st.get("rn"), st.get("rw")
    scr = what == "screen"
    noun = "impressions per screen user per day (this screen's ads ÷ this screen's own daily users)" if scr else \
        "impressions per app user per day (this trigger's ads ÷ the app's daily users)"
    out = ["== %s (%s) ==" % (label, what),
           "Status: %s — %s (score %s)" % (st["word"], st["why"], st["score"] if st["score"] is not None else "—"),
           "Window W %s – %s, normal N %s – %s (GA4 days, UTC)" % (w[0], w[-1], n[0], n[-1]),
           "%s: W %s · N %s" % (noun[0].upper() + noun[1:], _q(rw), _q(rn))]
    if st.get("imp") is not None:
        out.append("  = %s of the app's impressions per user" % _pc(st["imp"], 1))
    dw, dn = st.get("dW") or 0, st.get("dN") or 0
    if scr:
        rc = st.get("reach")
        out.append("Screen users: W %s/day · N %s/day%s" % (
            _n(st["UW"] / dw if dw else None), _n(st["UN"] / dn if dn else None),
            " · reach W %d%% · N %d%% of the app's daily users" % (round(100 * rc[0]), round(100 * rc[1])) if rc else ""))
    else:
        out.append("App daily users: W %s/day · N %s/day" % (_n(st["UW"] / dw if dw else None),
                                                            _n(st["UN"] / dn if dn else None)))
    if st.get("parts"):
        out.append("Why it moved (%% of normal, adds up to %s): %s" % (
            _sgn(sum(st["parts"].values()), "%.1f"), _part_line(st)))
    out.append("Ads per 100 visits: W %s · N %s · First bad day: %s" % (
        _fmt100(st["AW"] / st["VW"] if st["VW"] else None), _fmt100(st["AN"] / st["VN"] if st["VN"] else None),
        fbd or "—"))
    out.append("Last 14 GA4 days (date, %s, visits, ads, imp/%s user, ads/100):" % (
        "screen users" if scr else "app daily users", "screen" if scr else "app"))
    for d in _span(app.ftu - timedelta(days=13), app.ftu):
        v, a, u = series.get(d, (None, None, None))
        out.append("  %s  %s  %s  %s  %s  %s" % (d, _n(u), _n(v), _n(a), _q(a / u) if u else "—",
                                                 _fmt100(a / v) if v else "—"))
    if ab is not None:                                 # numbers only: the benchmark needs every app (the page has it)
        out.append("Absolute (last %d days): %sFill %s, Show rate %s%s%s" % (
            W_DAYS, "Ads / view %s, " % _pa(ab["av"]) if scr else "", _pf(ab["fill"]), _pf(ab["show"]), "".join(
                " · %s %s of the unit ads (fill %s, show %s)" % (FMT_NAME.get(f, f), _pf(p[0]),
                                                                 _pf(p[2] / p[1] if p[1] else None),
                                                                 _pf(p[3] / p[2] if p[2] else None))
                for f, p in sorted(ab["p"].items(), key=lambda kv: (-kv[1][0], kv[0]))),
            " — %s" % ab["why"] if ab["why"] else ""))
    if ver:
        out.append("Version: %s (per 100 visits — GA4 gives no users by version or country here)" % ver)
    if cc:
        out.append("Countries (top 3 by change, per 100 visits): %s" % cc)
    if cz.get("units"):
        out.append("Units, normal N → last 10 days W (AdMob requests/day · fill · show · GA4 ÷ AdMob):")
        for ui, rqw, rqn, fw, fn, sw, sn, tw, tn in cz["units"]:
            u = app.units[ui]
            out.append("  %s (%s) %s · requests/day %s → %s · fill %s → %s · show %s → %s · GA4 ÷ AdMob %s → %s" % (
                u[0] or u[3], ", ".join(u[2]) or "no AdMob id", u[1], _n(rqn), _n(rqw), _p(fn), _p(fw), _p(sn), _p(sw),
                _p(tn), _p(tw)))
    lab = st.get("cause") or ""
    out.append("Cause: %s%s" % (lab or "—", (" · ad logic: %s" % cz["cause"]) if cz.get("cause") and
                                cz["cause"] != lab and lab in PART_LABEL.values() else ""))
    if cz.get("terms"):
        out.append("  Ad logic terms (%% of normal ads per visit): %s" % " · ".join(
            "%s %+.1f" % (TERM_LABEL[k], cz["terms"][k]) for k in TERMS if cz["terms"].get(k)))
    checks = []
    c = cz.get("cause") or ""
    if lab in PART_CHECK:
        checks.append(PART_CHECK[lab])
    for lab_, txt in CHECK.items():
        if lab_ in c and txt not in checks and lab not in PART_CHECK:
            checks.append(txt)
    if c.startswith("Ad unit"):
        st_ = (cz.get("stopped") or [None])[0]
        sname = (app.units[st_][0] or app.units[st_][3]) if st_ is not None else "?"
        rep = c.split("→", 1)[1].strip() if "→" in c else None
        day = cz.get("stop_day") or fbd or w[0]
        live = [v for v, f in (versions or {}).items() if f <= day]
        vtxt = " (version %s)" % max(live, key=lambda v: (versions[v], v)) if live else ""
        checks.append("Unit %s stopped requesting from %s%s: check it is still created and loaded%s." % (
            sname, day, vtxt,
            ("; if it was replaced by %s, check %s is placed on the same screens" % (rep, rep)) if rep else ""))
    if checks:
        out.append("What to check: " + " ".join(checks))
    if rn:
        acc = "Acceptance check: after the fix ships, for 3 final days: impressions per %s user per day on %s ≥ %s " \
              "(0.9 × normal)" % ("screen" if scr else "app", label, _q(0.9 * rn))
        p = st.get("parts") or {}
        G = st.get("G") or [0, 0]
        if lab == "Users open it fewer times" and st["UN"]:
            acc += " and views per user ≥ %s" % _q(0.9 * st["VN"] / st["UN"])
        elif lab == "Users stay shorter" and st["VN"] and G[1]:
            acc += " and time per view ≥ %s" % _ft(0.9 * G[1] / st["VN"])
        elif "apm" in p and G[1]:
            acc += " and ads per minute ≥ %s (0.9 × %s)" % (_q(0.9 * 60 * st["AN"] / G[1]), _q(60 * st["AN"] / G[1]))
        out.append(acc)
    return "\n".join(out)


def dq_items(app, clicks=None):
    """Data-quality codes + their report lines. clicks: {"seen": whole click reads, "n": ad_click events} (None: the
    clicks read is not known)."""
    codes, lines = [], []
    last = _span(app.ft - timedelta(days=27), app.ft)
    ns = app._ns_cls(last)
    if ns is not None and ns >= 0.02:
        codes.append("ns" if ns < 0.5 else "no_screens")
        lines.append("%d%% of ad events have no screen class (last 28 GA4 days)%s." % (
            round(100 * ns), " — the app has no screen tracking for ads" if ns >= 0.5 else ""))
    if app.runs:
        codes.append("dup")
        r = app.runs[-1]
        lines.append("Duplicate ad_impression logging: a second copy without ad_format / ad_unit_name on %d days "
                     "(latest run %s – %s, %s)." % (sum(len(x["days"]) for x in app.runs), r["a"], r["b"],
                                                    "confirmed against AdMob" if r["ok"] else "pattern only"))
    um = [u for u in app.units if u[4] == "" and not unit_unset(u[0]) and u[0].lower() not in FOLD]
    if um:
        codes.append("unmatched")
        lines.append("GA4 unit names not found in AdMob: %s." % ", ".join(sorted({u[0] for u in um})[:20]))
    idl = [u for u in app.units if u[4] == "id"]
    if idl:
        codes.append("ids")
        lines.append("GA4 logs AdMob unit ids instead of names on %d units." % len(idl))
    tst = [u for u in app.units if str(u[0]).startswith(TEST_PUB)]
    if tst:
        codes.append("test_ids")
        lines.append("Google test unit ids are logged in production (%d units)." % len(tst))
    if app.adm:
        lc = [d for d in last if app.adm.complete(d)]
        for i, u in enumerate(app.units):
            if u[4] == "admob" and lc:
                imp = sum((app.unit_adm(i, d) or [0, 0, 0])[2] for d in lc) / len(lc)
                if imp >= 100:
                    if "admob_only" not in codes:
                        codes.append("admob_only")
                    lines.append("AdMob unit %s (%s) is never logged in GA4: %s AdMob impressions per day." % (
                        u[3], ", ".join(u[2]), _n(imp)))
    ads = sum(sum(t.values()) for t in app.ta.values())
    if clicks and clicks["seen"] and not clicks["n"] and ads:
        codes.append("no_click")
        lines.append("ad_click is not logged in GA4 (%d days read, %s ad impressions)." % (clicks["seen"], _n(ads)))
    return codes, lines


# ── layers: small (records), ver / cc (month cache, shards, month sums, window sums) ─────────

def _layer_derive(days, vid, aid):
    """A layer group's days → {day: {"V": [st, g], "A": [st, g], "r": [[dim, class, views|None, inline, full, notset,
    unsplit]]}} (rows per (dim, class); class "" = app level). Not usable reads keep their state only."""
    out = {}
    for d, recs in days.items():
        if not isinstance(recs, dict) or (vid not in recs and aid not in recs):
            continue
        rows, e = {}, {}
        vr, ar = recs.get(vid), recs.get(aid)
        e["V"] = [_ch(vr), (vr or {}).get("g")] if vr is not None else ["-", None]
        e["A"] = [_ch(ar), (ar or {}).get("g")] if ar is not None else ["-", None]

        def slot(dim, c):
            return rows.setdefault((str(dim), str(c)), [None, 0, 0, 0, 0])
        if _ok(vr):
            g = vr.get("g") or "c"
            for row in vr.get("r") or []:
                try:
                    if g == "c":
                        x = slot(row[0], row[1] or "")
                        x[0] = (x[0] or 0) + _i(row[2])
                    else:
                        x = slot(row[0], "")
                        x[0] = (x[0] or 0) + _i(row[1])
                except (IndexError, TypeError):
                    continue
        if _ok(ar):
            g = ar.get("g") or "cf"
            for row in ar.get("r") or []:
                try:
                    if g == "cf":
                        x, f, n = slot(row[0], row[1] or ""), fmt(row[2]), _i(row[3])
                    elif g == "f":
                        x, f, n = slot(row[0], ""), fmt(row[1]), _i(row[2])
                    else:
                        x, f, n = slot(row[0], ""), None, _i(row[1])
                except (IndexError, TypeError):
                    continue
                if f is None:
                    x[4] += n
                else:
                    b = fgroup(f)
                    x[1 + (b if b is not None else 0)] += n
        e["r"] = [[k[0], k[1]] + v for k, v in sorted(rows.items())]
        out[d] = e
    return out


def _cache_path(data_dir, key, grp, m):
    return os.path.join(data_dir, CACHE_DIR, key, "%s_%s.json.gz" % (grp, m))


def _cache_get(data_dir, key, grp, m, src):
    raw = _read_gz_bytes(_cache_path(data_dir, key, grp, m))
    body = _json(raw) if raw is not None else None
    if body and body.get("v") == CACHE_V and body.get("src") == src and isinstance(body.get("days"), dict):
        return body
    return None


def _cache_put(data_dir, key, grp, m, body):
    try:
        p = _cache_path(data_dir, key, grp, m)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        write_json_gz_stable(p, body)
    except OSError:
        pass


def _apply_dup(app, d, e):
    """A confirmed copy day: notset dropped from rows with a format; ads at the shape without format → null."""
    if app.dup.get(d) != 1:
        return e
    rows = []
    if e["A"][1] == "a":
        for r in e["r"]:
            rows.append(r[:3] + [0, 0, 0, None])
    else:
        for r in e["r"]:
            rows.append(r[:5] + [0, r[6]])
    return dict(e, r=rows, dup=1)


def shard_body(app, m, merged):
    """One month's day rows over the display items → the shard body (day index from the 1st of the month)."""
    days = _span(m + "-01", min(_d(_month_end(m)), app.td))
    dims = sorted({r[0] for d in days if d in merged for r in merged[d]["r"]})
    dix = {x: i for i, x in enumerate(dims)}
    out = []
    for d in days:
        e = merged.get(d)
        if e is None:
            out.append(None)
            continue
        vg, ag = e["V"][1], e["A"][1]
        vr, ar = {}, {}
        for dim, c, views, inl, full, ns, uns in e["r"]:
            di = dix[dim]
            ii = app.item_of(c) if c != "" else -1
            if views is not None:
                k = (di, ii)
                vr[k] = vr.get(k, 0) + views
            if e["A"][0] in OK_ST and (inl or full or ns or uns):
                k = (di, ii)
                x = ar.setdefault(k, [0, 0, 0, 0])
                x[0] += inl
                x[1] += full
                x[2] += ns
                x[3] += uns or 0
        vd = {"st": e["V"][0], "g": vg}               # per-day parts: never named V (the module's file version)
        if e["V"][0] in OK_ST:
            vd["r"] = [[di, ii, n] if ii >= 0 else [di, n] for (di, ii), n in sorted(vr.items())]
        ad = {"st": e["A"][0], "g": ag}
        if e["A"][0] in OK_ST:
            if e.get("dup") and ag == "a":
                ad["r"], ad["dup"] = None, 1
            elif ag == "cf":
                ad["r"] = [[di, ii] + x[:3] for (di, ii), x in sorted(ar.items()) if ii >= 0]
            elif ag == "f":
                ad["r"] = [[di] + x[:3] for (di, ii), x in sorted(ar.items())]
            else:
                ad["r"] = [[di, x[3]] for (di, ii), x in sorted(ar.items())]
        out.append({"V": vd, "A": ad})
    return {"v": V_SHARD, "key": app.key, "m": m, "dims": dims, "items": app.ditems, "days": out}


def _month_end(m):
    y, mo = int(m[:4]), int(m[5:7])
    nxt = date(y + (mo == 12), mo % 12 + 1, 1)
    return _iso(nxt - timedelta(days=1))


class Layer:
    """One layer group of one app streamed month by month: state chars, month sums, shards, the window sums the report
    needs (per Worse / Watch row, per dim, W and N) and, for versions, first / last / same days. A month whose store file,
    copy days and display items are unchanged and that lies outside W ∪ N (and has no recent day) is served from its
    cached summary — its rows are never loaded. A month's shard is built only when its input key (_shard_key) differs
    from the app's out-file index `idx` or its file on disk is not the one indexed: an unchanged month never builds,
    serializes or writes its shard. A month file the store has but that cannot be read or parsed is listed in `broken`
    (month → error type) and never cached: every build counts it again."""

    def __init__(self, app, grp, data_dir, out_dir, recent, report_rows, counts, idx=None):
        self.app, self.grp, self.data_dir, self.out_dir = app, grp, data_dir, out_dir
        self.idx = {} if idx is None else idx      # the app's out-file index (_idx_path), shared with the caller
        self.seen, self.old = set(), {}            # shard names of this build; month → its summary as read
        self.mk = _sha(_raw(app.ditems))[:16]      # the display items a summary's month sums ("ms") were mapped on
        self.vid, self.aid = GROUPS[grp]
        self.letter = "r" if grp == "ver" else "c"
        self.recent = _layer_derive(recent, self.vid, self.aid)
        self.rows = report_rows
        self.counts = counts
        self.st = {self.vid: {}, self.aid: {}}
        self.csum, self.shards, self.big, self.failed, self.keep = {}, {}, [], [], set()
        self.summ, self.src = {}, {}
        w, n = app.windows()
        self.win = (n[0], w[-1])
        self.wset, self.nset = set(w), set(n)
        self.wsum = {}                     # row id → {dim: [VW, AW, VN, AN]}
        self.first, self.last = {}, {}
        self.listed = set(_months(data_dir, app.key, grp, app.meta))      # the months the store has (meta ∪ disk)
        self.ms = sorted(self.listed | {d[:7] for d in self.recent})
        self.broken = {}                   # month → error type: a month file the store has that cannot be read / parsed

    def _file(self, m):
        try:
            with open(_month_path(self.data_dir, self.app.key, self.grp, m), "rb") as f:
                b = f.read()
            return b, _sha(b)
        except OSError as e:
            if m in self.listed:           # (a month of recent days only has no file yet: not broken)
                self.broken.setdefault(m, type(e).__name__)
            return None, None

    def _rows(self, m, src, b=None, count=True):
        """The month FILE's derived day rows: the cached ones when the store file is unchanged, else derived (cached).
        b: the file's bytes when the caller holds them; else the file is read again only on a cache miss (the raw month
        bytes are never kept between months: one month of one layer group in memory)."""
        if src is None:
            return {}
        hit = _cache_get(self.data_dir, self.app.key, self.grp, m, src)
        if hit is not None:
            self.counts["cached"] += 1 if count else 0
            return hit["days"]
        if b is None:
            b, src2 = self._file(m)
            if b is None:
                return {}
            src = src2
        try:
            days = _parse_month(b)
        except Exception as e:                       # counted and marked; never cached, so every build sees it again
            self.broken.setdefault(m, type(e).__name__)
            return {}
        rows = _layer_derive(days, self.vid, self.aid)
        _cache_put(self.data_dir, self.app.key, self.grp, m, {"v": CACHE_V, "src": src, "days": rows})
        return rows

    def _merged(self, m, rows):
        app = self.app
        merged = dict(rows)
        for d, e in self.recent.items():
            if d[:7] == m:
                merged[d] = e
        return {d: _apply_dup(app, d, e) for d, e in merged.items() if app.d0 and app.d0 <= d <= _iso(app.td)}

    def _has_recent(self, m):
        return any(d[:7] == m for d in self.recent)

    def _in_win(self, m):
        return not (_month_end(m) < self.win[0] or m + "-01" > self.win[1])

    def _fn(self, m):
        return "%s%s_%s_%s.json.gz" % (PREFIX, self.letter, self.app.key, m.replace("-", ""))

    def run(self):
        app = self.app
        for m in self.ms:
            b, src = self._file(m)
            self.src[m] = src                          # the sha only; the bytes go with this iteration
            rec, fn = self._has_recent(m), self._fn(m)
            self.seen.add(fn)
            dk = "".join(str(app.dup.get(d, 0)) for d in _span(m + "-01", _month_end(m)))
            shk = self._shard_key(m, src, dk)
            summ = None if rec or src is None or m in self.broken else _sum_get(self.data_dir, app.key, self.grp, m, src)
            self.old[m] = summ
            if summ and summ.get("dk") == dk and not self._win_needed(m) and self._shard_ok(fn, shk):
                self.counts["cached"] += 1
                summ = self._with_ms(summ)
                self._keep_summ(m, summ)
                self._take(m, summ, self._shard_entry(fn))
                if self.grp != "ver":
                    self._save_summ(m, summ)
                continue
            merged = self._merged(m, self._rows(m, src, b))
            b = None
            st, csum, first, last = {self.vid: {}, self.aid: {}}, {}, {}, {}
            for d, e in sorted(merged.items()):
                st[self.vid][d], st[self.aid][d] = e["V"][0], e["A"][0]
                vok, aok = e["V"][0] in OK_ST, e["A"][0] in OK_ST
                for dim, c, views, inl, full, ns, uns in e["r"]:
                    x = csum.setdefault((dim, c), [0, 0, 0, 0])
                    if vok and views is not None:
                        x[0] += views
                    if aok:
                        x[1] += inl
                        x[2] += full
                        x[3] += uns or 0
                    if self.grp == "ver" and (vok and views or aok and (inl or full or uns)):
                        first[dim] = min(first.get(dim, d), d)
                        last[dim] = max(last.get(dim, d), d)
                if self.win[0] <= d <= self.win[1] and vok and aok:
                    self._window(d, e)
            summ = self._with_ms({"v": CACHE_V, "src": src, "dk": dk, "st": st,
                                  "sum": [[dim, c] + x for (dim, c), x in sorted(csum.items())], "first": first,
                                  "last": last})
            sh = self._shard(m, merged, shk)
            self._keep_summ(m, summ)
            self._take(m, summ, sh)
            if self.grp != "ver":                       # (versions: saved by versions(), with its same-days part)
                self._save_summ(m, summ)
        return self

    def _save_summ(self, m, summ):
        """A month's summary to the cache — only a store month file's (no recent day, readable) and only when it changed."""
        if summ.get("src") and not self._has_recent(m) and m not in self.broken and summ != self.old.get(m):
            _sum_put(self.data_dir, self.app.key, self.grp, m, summ)
            self.old[m] = summ

    def _win_needed(self, m):
        """A month whose rows must be read for the report: inside W ∪ N while the app has a Worse / Watch row (its
        window sums and same days); every other month can be served from its summary."""
        return bool(self.rows) and self._in_win(m)

    def _with_ms(self, summ):
        """The summary with its month sums over the display items ("ms", mapped on the display items "mk"): the same
        dict when they are there for these items, else a new one."""
        if summ.get("mk") == self.mk and isinstance(summ.get("ms"), list):
            return summ
        acc = {}
        for dim, c, v, inl, full, uns in summ.get("sum") or []:
            x = acc.setdefault((dim, self.app.item_of(c) if c != "" else -1), [0, 0, 0, 0])
            x[0] += v
            x[1] += inl
            x[2] += full
            x[3] += uns
        out = dict(summ, mk=self.mk, ms=[[dim, ii] + x for (dim, ii), x in sorted(acc.items())])
        out.pop("shard", None)                         # (an older summary's shard entry: the out-file index has it now)
        return out

    def _shard_key(self, m, src, dk):
        """Everything a month's shard body depends on: its store month file, its recent days, its copy days, the display
        items, its day span (d0 … today), the cache / shard-code versions (KEY_V: the file version held, never V's
        bumps) and the size limit."""
        app = self.app
        rk = _sha(_raw({d: e for d, e in self.recent.items() if d[:7] == m})) if self._has_recent(m) else ""
        lo, hi = max(app.d0 or "", m + "-01"), min(_month_end(m), _iso(app.td))
        return _sha(_raw([KEY_V, CACHE_V, SHARD_V, MAX_GZ, self.grp, m, src, rk, dk, app.ditems, lo, hi]))[:20]

    def _shard_ok(self, fn, shk):
        """The index knows this shard for these inputs: too big, or written and still the file on disk."""
        e = self.idx.get(fn)
        return isinstance(e, dict) and e.get("k") == shk and (
            bool(e.get("big")) or bool(e.get("h")) and _on_disk(os.path.join(self.out_dir, fn), e))

    def _shard_entry(self, fn):
        e = self.idx[fn]
        return {"big": True} if e.get("big") else {"v": e["h"][:12]}

    def _keep_summ(self, m, summ):
        """Versions keep each month's summary for pass 2 (versions()); countries need nothing after _take."""
        if self.grp == "ver":
            self.summ[m] = summ

    def _take(self, m, summ, sh):
        for i in (self.vid, self.aid):
            self.st[i].update((summ.get("st") or {}).get(i) or {})
        self.csum[m] = summ.get("ms") or []
        for v, d in (summ.get("first") or {}).items():
            self.first[v] = min(self.first.get(v, d), d)
        for v, d in (summ.get("last") or {}).items():
            self.last[v] = max(self.last.get(v, d), d)
        mm = m.replace("-", "")
        if sh.get("big"):
            self.big.append(mm)
        elif sh.get("v"):
            self.shards[mm] = sh["v"]
            self.keep.add(self._fn(m))

    def msum(self):
        """{YYYY-MM: [[dim, display item | −1, views, inline, full, unsplit]]} over the display items (each month's
        mapped once and kept in its summary: _with_ms)."""
        return {m: rows for m, rows in self.csum.items()}

    def _window(self, d, e):
        side = 0 if d in self.wset else 2 if d in self.nset else None
        if side is None:
            return
        for rid, row in self.rows.items():
            if row[0] == "s" and (e["V"][1] != "c" or e["A"][1] != "cf"):
                continue                             # a screen row needs both splits by class
            if row[0] == "t" and e["A"][1] not in ("cf", "f"):
                continue                             # a trigger row needs the format
            acc = self.wsum.setdefault(rid, {})
            for dim, c, views, inl, full, ns, uns in e["r"]:
                if row[0] == "s":
                    if c != row[1]:
                        continue
                    q = inl + (full + ns if row[2] else 0)
                else:                                # app level per dim: every class, full-screen ads (all triggers)
                    q = full
                v = 0 if row[0] == "t" and c != "" and kind(c) == "ad" else views or 0
                x = acc.setdefault(dim, [0, 0, 0, 0])
                x[side] += v
                x[side + 1] += q

    def _shard(self, m, merged, shk):
        """→ the month's shard {"v"} / {"big": True} / {} (failed: tried again next build). Built only when the index
        does not know it for these inputs (or its file is gone / changed); written only when its bytes changed."""
        fn, mm = self._fn(m), m.replace("-", "")
        if self._shard_ok(fn, shk):
            return self._shard_entry(fn)
        try:
            h = _put(self.out_dir, fn, _raw(shard_body(self.app, m, merged)), self.idx, key=shk)
            if h is None:
                self.idx[fn] = {"k": shk, "big": 1}
                return {"big": True}
            return {"v": h[:12]}
        except Exception as e:                       # one month lost, never the app
            self.idx.pop(fn, None)
            self.failed.append(mm)
            print("scr shard skipped: %s" % type(e).__name__, file=sys.stderr)
            return {}

    def versions(self):
        """Pass 2 (versions only): per version {first, last, prev, items: {si: [views, inline, full]}, same_days: {si:
        [this views, this ads, prev views, prev ads]}} over the whole life (a month's part cached under the version
        order), and the window same days per report row (wsame: {version: {si | "*": [this views, inline, full, prev
        views, inline, full]}})."""
        app = self.app
        order = sorted(self.first, key=lambda v: (self.first[v], v))
        prev = {v: (order[i - 1] if i else None) for i, v in enumerate(order)}
        pk = _sha(_raw(sorted(prev.items(), key=lambda kv: kv[0])))[:16]
        items, same, wsame = {}, {}, {}
        for m in self.ms:
            summ = self.summ.get(m)
            part = (summ or {}).get("same")
            if not (part and part.get("pk") == pk and not self._has_recent(m) and not self._win_needed(m)):
                part = self._same(self._merged(m, self._rows(m, self.src.get(m), count=False)), prev, wsame)
                part["pk"] = pk
                if summ is not None:                   # a new dict: the summary as read stays the one compared with
                    summ = self.summ[m] = dict(summ, same=part)
            if summ is not None:
                self._save_summ(m, summ)
            for tgt, k in ((items, "items"), (same, "sd")):
                for v, by in (part.get(k) or {}).items():
                    for c, x in by.items():
                        y = tgt.setdefault(v, {}).setdefault(c, [0] * len(x))
                        for j, val in enumerate(x):
                            y[j] += val
        out = {}
        for v in order:
            out[v] = {"first": self.first[v], "last": self.last[v], "prev": prev[v],
                      "items": {str(_si(app, c) if c != "" else -1): x for c, x in sorted((items.get(v) or {}).items())},
                      "same_days": {str(_si(app, c) if c != "" else -1): x
                                    for c, x in sorted((same.get(v) or {}).items())}}
        wout = {v: {(_si(app, c) if c not in ("", "*") else (-1 if c == "" else "*")): x for c, x in by.items()}
                for v, by in wsame.items()}
        return out, order, wout

    def _same(self, merged, prev, wsame):
        """One month's per-version items and same days (class names; "" = app level) + the window part into wsame."""
        items, sd = {}, {}
        for d, e in merged.items():
            if e["V"][0] not in OK_ST or e["A"][0] not in OK_ST:
                continue
            per = {}
            for dim, c, views, inl, full, ns, uns in e["r"]:
                for k_ in (c, "*"):
                    x = per.setdefault(dim, {}).setdefault(k_, [0, 0, 0])
                    x[0] += 0 if k_ == "*" and c != "" and kind(c) == "ad" else views or 0
                    x[1] += inl
                    x[2] += full
                y = items.setdefault(dim, {}).setdefault(c, [0, 0, 0])
                y[0] += views or 0
                y[1] += inl
                y[2] += full
            for v, by in per.items():
                p = prev.get(v)
                if not p or p not in per:
                    continue
                for c, x in by.items():
                    y = per[p].get(c)
                    if not y or not x[0] or not y[0]:
                        continue
                    if self.win[0] <= d <= self.win[1]:
                        k = wsame.setdefault(v, {}).setdefault(c, [0, 0, 0, 0, 0, 0])
                        for j, val in enumerate(x + y):
                            k[j] += val
                    if c == "*":
                        continue
                    z = sd.setdefault(v, {}).setdefault(c, [0, 0, 0, 0])
                    z[0] += x[0]
                    z[1] += x[1]
                    z[2] += y[0]
                    z[3] += y[1]
        return {"items": items, "sd": sd}


def _sum_path(data_dir, key, grp, m):
    return os.path.join(data_dir, CACHE_DIR, key, "%s_%s.sum.json.gz" % (grp, m))


def _sum_get(data_dir, key, grp, m, src):
    raw = _read_gz_bytes(_sum_path(data_dir, key, grp, m))
    body = _json(raw) if raw is not None else None
    return body if body and body.get("v") == CACHE_V and body.get("src") == src else None


def _sum_put(data_dir, key, grp, m, body):
    try:
        p = _sum_path(data_dir, key, grp, m)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        write_json_gz_stable(p, body)
    except OSError:
        pass


def _ver_line(app, row, order, wsame, prev):
    """The first version (by first day seen) whose ads per 100 visits on the row's same days with the previous version
    are < 90 % of the previous version's."""
    si = app.six.get(row[1]) if row[0] == "s" else "*"
    for v in order:
        p = prev.get(v)
        k = (wsame.get(v) or {}).get(si)
        if not p or not k:
            continue
        tv, ta, tf, pv, pa, pf = k
        if row[0] == "t":
            ta, pa = tf, pf
        if tv >= 100 and pv >= 100 and pa and ta / tv < BAD_RATE * pa / pv:
            return "%s: ads/100 %s on %s visits vs %s: %s on %s visits (same days)" % (
                v, _fmt100(ta / tv), _n(tv), p, _fmt100(pa / pv), _n(pv))
    return "no version shows the drop on the same days as its previous version"


def _cc_line(acc):
    """Top 3 countries by change: ads lost vs the normal rate (most negative first)."""
    rows = []
    for cc, (vw, aw, vn, an) in (acc or {}).items():
        if vn < 100 or not vw:
            continue
        rows.append((aw - (an / vn) * vw, cc, an / vn, aw / vw, vw))
    rows.sort()
    if not rows:
        return None
    return " · ".join("%s %s → %s (visits %s)" % (cc, _fmt100(rn), _fmt100(rw), _n(vw)) for _, cc, rn, rw, vw in rows[:3])


def _clicks(rec):
    """ad_click events of a whole clicks record's truth."""
    n, t = 0, rec.get("t")
    for row in (t.items() if isinstance(t, dict) else t or []):
        try:
            n += _i(row[1]) if str(row[0]) == "ad_click" else 0
        except (IndexError, TypeError):
            pass
    return n


def _users(e):
    """An encoded uV record (_enc: rows [screen index, sessions, users]) → [[screen index, users]] (its rows' order)."""
    return [[r[0], r[2]] for r in e.get("r") or ()]


def small_days(app, data_dir, recent, broken=None, counts=None):
    """The small group per day as scr_l's day records — each day's sorted compact JSON (bytes: classes → file 2 screen
    indexes, layer ads without a format on a confirmed copy day → null; spliced into scr_l unparsed) — its state chars,
    the click tally (a month file that cannot be read → `broken`) and the users by screen ({day: {screen index: users}},
    only the days whose uV record is whole: GA4's activeUsers, unique within one day and one screen — users_by_day). A
    store month is encoded once: its day records, states, clicks and users are cached under the store file's sha1
    (data/ga4_screens_cache/<key>/small_<YYYY-MM>.json.gz) with its classes in the order the encoding met them and the
    screen indexes they got; a cached month registers those classes in that order — the indexes an uncached build
    gives — and is used only when they match (else encoded again)."""
    ids = GROUPS["small"]
    frag, st, users = {}, {i: {} for i in ids}, {}
    clicks = {"seen": 0, "n": 0}
    td = _iso(app.td)
    for m in _months(data_dir, app.key, "small", app.meta) if app.d0 else ():
        try:
            with open(_month_path(data_dir, app.key, "small", m), "rb") as f:
                b = f.read()
        except OSError as e:
            if broken is not None:
                broken.append(("small", m, type(e).__name__))
            continue
        src = _sha(b)
        lo, hi = max(app.d0, m + "-01"), min(_month_end(m), td)
        dk = "".join(str(app.dup.get(d, 0)) for d in _span(m + "-01", _month_end(m)))
        c = _cache_get(data_dir, app.key, "small", m, src)
        if c is not None and [c.get("dk"), c.get("lo"), c.get("hi"), c.get("sv")] == [dk, lo, hi, SMALL_V]:
            cls = c.get("cls") or []
            for x in cls:
                _si(app, x)
            if [app.six.get(x) for x in cls] == c.get("map"):
                frag.update((d, t.encode("utf-8")) for d, t in c["days"].items())
                for i, by in (c.get("st") or {}).items():
                    st.setdefault(i, {}).update(by)
                users.update((d, {si: n for si, n in rows}) for d, rows in (c.get("u") or {}).items())
                clicks["seen"] += c["ck"][0]
                clicks["n"] += c["ck"][1]
                if counts is not None:
                    counts["cached"] += 1
                continue
        try:
            days = _parse_month(b)
        except Exception as e:
            if broken is not None:
                broken.append(("small", m, type(e).__name__))
            continue
        seen, mf, mst, ck, mu = {}, {}, {i: {} for i in ids}, [0, 0], {}
        for d, recs in days.items():
            if not isinstance(recs, dict) or not lo <= d <= hi:
                continue
            e = {}
            for i in ids:
                rec = recs.get(i)
                if rec is None:
                    continue
                mst[i][d] = _ch(rec)
                e[i] = _enc(app, d, i, rec, seen)
                if i == "k" and _ok(rec):
                    ck[0] += 1
                    ck[1] += _clicks(rec)
                elif i == "uV" and _whole(rec):
                    mu[d] = _users(e[i])
            if e:
                mf[d] = _raw(e)
        _cache_put(data_dir, app.key, "small", m, {"v": CACHE_V, "sv": SMALL_V, "src": src, "dk": dk, "lo": lo,
                                                   "hi": hi, "cls": list(seen), "map": [app.six[x] for x in seen],
                                                   "st": mst, "ck": ck, "u": mu,
                                                   "days": {d: t.decode("utf-8") for d, t in mf.items()}})
        frag.update(mf)
        for i, by in mst.items():
            st[i].update(by)
        users.update((d, {si: n for si, n in rows}) for d, rows in mu.items())
        clicks["seen"] += ck[0]
        clicks["n"] += ck[1]
    # the recent days (re-read on refresh: never cached) over the month's records of the same day, read by read
    for d, recs in recent.items():
        if not isinstance(recs, dict) or not app.d0 or not (app.d0 <= d <= td):
            continue
        e = None
        for i in ids:
            rec = recs.get(i)
            if rec is None:
                continue
            if e is None:
                e = json.loads(frag[d]) if d in frag else {}
            st[i][d] = _ch(rec)
            e[i] = _enc(app, d, i, rec)
            if i == "k" and _ok(rec):
                clicks["seen"] += 1
                clicks["n"] += _clicks(rec)
            elif i == "uV":                              # (a recent record replaces the month's: whole or not)
                if _whole(rec):
                    users[d] = {si: n for si, n in _users(e[i])}
                else:
                    users.pop(d, None)
        if e:
            frag[d] = _raw(e)
    return frag, st, clicks, users


_SPLICE = "\u0000scr-days\u0000"     # scr_l's "days" while serialized: replaced by the day records' own JSON


def _splice(body, frags):
    """_raw(body) with body["days"] = the day records already serialized (bytes or None per day): the same bytes
    json.dumps gives for the parsed records (sorted compact JSON), without parsing or dumping them again."""
    raw, tok = _raw(body), _raw(_SPLICE)
    if raw.count(tok) == 1:
        return raw.replace(tok, b"[" + b",".join(f if f is not None else b"null" for f in frags) + b"]")
    return _raw(dict(body, days=[json.loads(f) if f is not None else None for f in frags]))


def _si(app, c):
    c = str(c or "")
    if c not in app.six:
        app.six[c] = len(app.screens)
        app.screens.append(c)
    return app.six[c]


def _enc(app, d, i, rec, seen=None):
    """A small-group record → the same record with classes as screen indexes (formats normalized) and the state scr_all
    ships for it (_ch: a "skip" record "-", not read yet — scr_l and scr_all agree). seen (a dict): gets each class in
    the order met (the small cache's registration order)."""
    e = dict({k: v for k, v in rec.items() if k != "r"}, st=_ch(rec))     # scr_all's state ("skip": "-", never "s")
    if not _ok(rec):
        return e
    if seen is None:
        si = lambda c: _si(app, c)
    else:
        def si(c):
            seen.setdefault(str(c or ""), None)
            return _si(app, c)
    g, rows = rec.get("g"), []
    for r in rec.get("r") or []:
        try:
            if i in ("k", "x"):
                rows.append([si(r[0]), str(r[1]), _i(r[2])])
            elif i == "e":
                rows.append([si(r[0]), _i(r[1])])
            elif i == "uV":
                rows.append([si(r[0]), _i(r[1]), _i(r[2])])
            elif i == "uA":
                rows.append([si(r[0]), _i(r[1])] if g != "a" else [_i(r[0])])
            elif i == "s":
                rows.append([fmt(r[0]), str(r[1]), _i(r[2])])
            elif i == "nV":
                rows.append([str(r[0]), si(r[1]), _i(r[2])] if g != "a" else [str(r[0]), _i(r[1])])
            elif i == "nA":
                if g == "cf":
                    rows.append([str(r[0]), si(r[1]), fmt(r[2]), _i(r[3])])
                elif g == "f":
                    rows.append([str(r[0]), fmt(r[1]), _i(r[2])])
                else:
                    rows.append([str(r[0]), _i(r[1])])
        except (IndexError, TypeError):
            continue
    if i == "nA" and app.dup.get(d) == 1:
        if g == "a":
            e["dup"] = 1
            e["r"] = None
            return e
        rows = [r for r in rows if r[-2] != "notset"]
    try:
        rows.sort()                   # one record's rows share one shape (same read, same grain): a natural total order
    except TypeError:                 # (never per row json — that was 2.4M dumps a build)
        rows.sort(key=lambda r: json.dumps(r))
    e["r"] = rows
    return e


# ── one app ──────────────────────────────────────────────────────────────────────────────────

def core_days(data_dir, key, meta, recent, broken=None):
    days = {}
    for _, _, body in iter_months(data_dir, key, "core", meta, broken):
        for d, recs in body.items():
            if isinstance(recs, dict):
                days.setdefault(d, {}).update({i: r for i, r in recs.items() if i in GROUPS["core"]})
    for d, recs in recent.items():
        if isinstance(recs, dict):
            x = days.setdefault(d, {})
            for i in GROUPS["core"]:
                if i in recs:
                    x[i] = _better(x.get(i), recs[i])
    return days


def _rows_at(app, ft, memo):
    """Every row of the app judged at one anchor ft (post-holds, before the confirm) → (rows, the App row's status)."""
    w, n = app.windows(ft)
    allf = app.allf(ft)
    af = bool(allf)
    gs, gt = app.guard(ft, True), app.guard(ft, False)
    if "app" not in memo:
        memo["app"], memo["afmt"] = app_series(app), _adm_fmt(app)
    aser, gfmt = memo["app"]
    ast = app_judge(app, w, n, aser, gfmt, memo["afmt"])
    UN, AN = sum(aser[d][2] for d in n if d in aser), sum(aser[d][1] for d in n if d in aser)
    app_rn = AN / UN if UN else None
    tix = {c: i for i, c in enumerate(app.top)}
    sa = memo.get(("k", af))
    if sa is None:
        sa = memo[("k", af)] = app.kind_ads(allf)
    what = "all-format" if allf else "inline"
    out = []
    for c in app.screens:
        if kind(c) != "s":
            continue
        k = ("s", c, af)
        if k not in memo:
            ser, base = screen_series_u(app, c, allf)
            eng = {d: app.views[d].get(c, [0, 0])[1] for d, x in ser.items() if x[2] > 0 and d in app.views}
            memo[k] = (ser, base, eng)
        ser, base, eng = memo[k]
        st = judge_u(ser, w, n, gs, what, "s", app_rn, app.au, app.vis,
                     miss=lambda d, b=base: "u" if d in b else app.day_why(d), tot=sa, eng=eng)
        out.append(("s%d" % app.six[c], ("s", c, allf), c, "s", tix.get(c), ser, st))
    for gi, (f, lab, _) in enumerate(app.trig):
        k = ("t", gi)
        if k not in memo:
            memo[k] = trig_series_u(app, gi)
        ser, base = memo[k]
        if ("f", f) not in memo:
            memo[("f", f)] = app.fmt_ads(f)
        st = judge_u(ser, w, n, gt, f, "t", app_rn, app.au, app.vis,
                     miss=lambda d, b=base: "u" if d in b else app.day_why(d, True), tot=memo[("f", f)])
        out.append(("t%d" % gi, ("t", gi), "%s · %s" % (f, lab), "fs", app.fs0 + gi, ser, st))
    return out, ast


def app_list(ast, rows):
    """scr_all's "app": [word, why, worse n, watch n, score, cause, parts, daily users move, AdMob check]."""
    worse = sum(1 for r in rows if r[6]["word"] == "Worse")
    watch = sum(1 for r in rows if r[6]["word"] == "Watch")
    adm = ast.get("adm")
    cz = "" if ast["word"] not in FLAGS else (
        "GA4 logging changed" if (adm or {}).get("st") == "admob" else cause_u(ast, None))
    return [ast["word"], ast["why"], worse, watch, ast.get("score"), cz, ast.get("parts"), ast.get("dau"), adm]


def statuses(app, ft=None):
    """Every row of the app → ([(row id, row, label, kind, item index | None, series, status)], the App row's status):
    the words at ft (default ftU) after the holds and the CONFIRM_DAYS confirm (the words on the days before)."""
    ft = _d(ft or app.ftu)
    memo = {}
    rows, ast = _rows_at(app, ft, memo)
    prev = [_rows_at(app, ft - timedelta(days=k), memo) for k in range(1, CONFIRM_DAYS)]
    pw = [{r[0]: r[6]["word"] for r in p[0]} for p in prev]
    out = []
    for rid, row, label, k, ii, ser, st in rows:
        before = [p.get(rid) for p in pw]
        st = _confirm(st, before)
        st["bases"] = [st["base"] if st.get("hold") == "confirm" else st["word"]] + before
        out.append((rid, row, label, k, ii, ser, st))
    before = [p[1]["word"] for p in prev]
    ast = _confirm(ast, before)
    ast["bases"] = [ast["word"] if ast.get("hold") != "confirm" else ast["base"]] + before
    return out, ast


# ── the users beside the ads in the files ─────────────────────────────────────────────────────

def users_by_day(app):
    """File 2's "Us" + "U": the top screens (app.top's order) as file 2 screen indexes, and per app day their users —
    only on final days ≤ ftU whose users read (uV), screen views AND ads by screen are whole (the build's own per-user
    days), else None; a top screen with no uV row that day has 0. Never Today / Yesterday: their users (a layer read,
    re-read every 12 h) and their ads (core, every 3 h) are snapshots hours apart while GA4 still adds to both. GA4's
    users are unique within ONE day and ONE screen: the page divides a period's Σ of a row's ads by the Σ of these, and
    no row ever gets users added across screens — an aggregate row (Other screens, Not recorded, Ad screens, GA4
    grouped) has none. → (Us, U), or None when no day has any (that app ships neither)."""
    six = [app.six[c] for c in app.top]
    ft = _iso(app.ftu)
    out = [None if d > ft or d not in app.su or d not in app.whole["a"] or d not in app.whole["v"] else
           [app.su[d].get(c, 0) for c in app.top] for d in app.days]
    return (six, out) if six and any(x is not None for x in out) else None


def daily_users(app):
    """The app's daily active users per app day — final days ≤ ftU only (as users_by_day, never Today / Yesterday),
    else None (never 0) — or None when no day has any. Shipped in scr_all ("au": the App total and All apps) and file 2."""
    out = [app.au.get(d) for d in app.days]
    return out if any(v is not None for v in out) else None


def app_users(meta, data_dir):
    """The app's GA4 daily active users → ({day: users}, None) from the Uninstall store (data/ga4_uninstall/<key>.json.gz,
    its "daily" a1: GA4's activeUsers by date, read with the same Android stream filter as this store's reads), or
    ({}, why): "none" (no store, not readable, or no day with users), "stream" (its app, property, stream or time zone
    is not this store's: another stream's users, or days on another calendar), "cut" (GA4 cut its daily report). A day
    without users (0 / missing) is left out, never 0 — so a store flagged "thresholded" is still used: GA4's
    thresholding only withholds rows (on a date-only report a whole day, which reads 0), never changes a number."""
    aid = str(meta.get("app_id") or "")
    raw = _read_gz_bytes(gu.store_path(data_dir, aid))
    u = _json(raw) if raw is not None else None
    if not u:
        return {}, "none"
    pid, sid = str(meta.get("property_id") or ""), str(meta.get("stream_id") or "")
    if not (pid and sid and str(u.get("app_id") or "") == aid and str(u.get("property_id") or "") == pid
            and str(u.get("stream_id") or "") == sid
            and str(u.get("time_zone") or "UTC") == str(meta.get("time_zone") or "UTC")):
        return {}, "stream"
    fl = u.get("flags") if isinstance(u.get("flags"), dict) else {}
    if "daily" in (fl.get("truncated") if isinstance(fl.get("truncated"), list) else ()):
        return {}, "cut"
    out = {}
    daily = u.get("daily") if isinstance(u.get("daily"), dict) else {}
    for d, e in daily.items():
        try:
            n = _i(e.get("a1"))
        except (AttributeError, TypeError, ValueError):
            continue
        if n > 0 and re.match(r"^\d{4}-\d{2}-\d{2}$", str(d)):
            out[str(d)] = n
    return (out, None) if out else ({}, "none")


def nvr_split(app, frags, w, n, ast):
    """The App row's users mix, measured (critic S1): ads per 100 app views W vs N split exactly (LMDI) into the new-user
    share of views ("mix") and each group's own ads per view ("within"), on the days both the New vs returning reads
    (nV / nA, scr_l's day records) are whole — plus the App row's views per user change, which this layer cannot split
    (GA4 gives no users by new / returning here): the app's views on every W / N day with daily users ÷ the GA4 judge's
    users of those same days (an App row judged on AdMob carries the AdMob judge's sums, AdMob-complete days only: its
    GA4 judge is "ga4", as in report_head). % of normal; None when either window has no such day."""
    def acc(ds):
        v, a, nd = {}, {}, 0
        for d in ds:
            f = frags.get(d)
            if not f:
                continue
            try:
                e = json.loads(f)
            except ValueError:
                continue
            nv, na = e.get("nV") or {}, e.get("nA") or {}
            if nv.get("st") != "w" or na.get("st") != "w" or na.get("r") is None:
                continue
            nd += 1
            for q in nv.get("r") or []:
                v[q[0]] = v.get(q[0], 0) + _i(q[-1])
            for q in na.get("r") or []:
                a[q[0]] = a.get(q[0], 0) + _i(q[-1])
        return v, a, nd
    vw, aw, ndw = acc(w)
    vn, an, ndn = acc(n)
    VW, VN, AW, AN = sum(vw.values()), sum(vn.values()), sum(aw.values()), sum(an.values())
    if not (ndw and ndn and VW and VN and AW and AN):
        return None
    rw, rn = AW / VW, AN / VN
    mix = within = 0.0
    grp = {}
    for g in sorted(set(vw) | set(vn)):
        if not (vw.get(g) and vn.get(g) and aw.get(g) and an.get(g)):
            continue
        sW, sN, qW, qN = vw[g] / VW, vn[g] / VN, aw[g] / vw[g], an[g] / vn[g]
        L = _L(sW * qW, sN * qN)
        mix += L * math.log(sW / sN)
        within += L * math.log(qW / qN)
        grp[str(g)] = [_r(100 * qN, 1), _r(100 * qW, 1)]
    vpu = None
    g = ast.get("ga4") or ast
    if g.get("parts") is not None and g.get("UW") and g.get("UN"):
        PW = sum(app.vis.get(d, 0) for d in w if d in app.au and d in app.ta)
        PN = sum(app.vis.get(d, 0) for d in n if d in app.au and d in app.ta)
        vpu = _r(100 * ((PW / g["UW"]) / (PN / g["UN"]) - 1), 1) if PW and PN else None
    return {"mix": _r(100 * mix / rn, 1), "within": _r(100 * within / rn, 1), "ch": _r(100 * (rw / rn - 1), 1),
            "g": grp, "vpu": vpu, "d": [ndw, ndn]}


def attn_groups(rows):
    """The flagged rows grouped as Needs attention shows them: (word family, cause group) → [rows, ≈ Σ impact] (the
    impacts are in the app's units, so they add; the rows sit on their own day sets: "≈")."""
    out = {}
    for rid, row, label, k, ii, ser, st in rows:
        if st["word"] not in FLAGS:
            continue
        g = out.setdefault((st["word"], st.get("group") or ""), [[], 0.0])
        g[0].append(label)
        g[1] += st.get("imp") or 0.0
    return out


def report_head(app, key, alist, ast, nvr, rows):
    """The developer report's head (§5.8): the App row on impressions per user per day, its daily users, the users mix
    (S1 wording: measured parts only, never "not the cause"; labelled "GA4, logging changed" when GA4 ≠ AdMob — the row
    judged on AdMob or not measurable: its ads per 100 views come from that GA4 logging), GA4 vs AdMob, the causes with
    ≈ Σ impact."""
    adm = alist[8] or {}
    word = alist[0] + (" (AdMob)" if adm.get("st") == "admob" else "")
    head = ["Screens report · app %s · GA4 data till %s · users till %s (GA4 days, UTC)" % (key, _iso(app.ft),
                                                                                         _iso(app.ftu)),
            "Status: %s — %s (%d Worse, %d Watch)" % (word, alist[1], alist[2], alist[3])]
    g = ast.get("ga4") or ast
    if g.get("dW") and g.get("dN") and g.get("UW") and g.get("UN"):
        a, b = g["UW"] / g["dW"], g["UN"] / g["dN"]
        head.append("Daily users (GA4 active users, same stream): W %s/day · N %s/day (×%s)" % (
            _n(a), _n(b), ("%.1f" if a >= b else "%.2f") % (a / b)))
    if nvr:
        rt = nvr["g"].get("returning")
        head.append("  New vs returning (ads per 100 views%s): new-user mix %s · within groups %s%s · views per user %s "
                    "(not split: GA4 gives no new / returning users here)" % (
                        "; GA4, logging changed" if adm.get("st") in ("admob", "na") else "",
                        _sgn(nvr["mix"], "%.1f") + "%", _sgn(nvr["within"], "%.1f") + "%",
                        " (returning %s → %s)" % (rt[0], rt[1]) if rt else "",
                        "—" if nvr["vpu"] is None else _sgn(nvr["vpu"], "%.1f") + "%"))
    if adm.get("g") is not None and adm.get("m") is not None:
        head.append("GA4 vs AdMob, per daily user, %s: GA4 %s · AdMob %s — %s" % (
            adm.get("f"), _pc(adm["g"]), _pc(adm["m"]), "agree" if adm.get("st") == "agree" else "disagree"))
    elif adm.get("gt") is not None and adm.get("mt") is not None:
        head.append("GA4 vs AdMob, per daily user, inline + full-screen: GA4 %s · AdMob %s" % (
            _pc(adm["gt"]), _pc(adm["mt"])))
    gr = attn_groups(rows)
    if gr:
        head.append("Causes: " + " · ".join(
            "%s%s — %d row%s (≈ %s of the app's impressions per user)" % (
                "" if w_ == "Worse" else "Watch: ", gk or "No single cause", len(v[0]), "" if len(v[0]) == 1 else "s",
                _pc(v[1])) for (w_, gk), v in sorted(gr.items(), key=lambda kv: (STATUS_RANK[kv[0][0]], kv[1][1]))))
    return head


# ── absolute numbers: Ads / view, Fill, Show rate (owner, 7 Nov 2026) ──────────────────────────

def ab_side(app, w, allf):
    """The app's absolute side over window w (W): σ's source days S (W's whole unit-split days — the shipped day
    states, so the page finds the same days; under SIG_MIN of them the newest SIG_N such days ≤ W's end: GA4 gives
    some apps the screen × unit split only on some days), g {class: {unit: its GA4 ads on the class over S}} on Imp /
    user / day's basis (inline, every format when allf), G {unit: its GA4 ads on all screens over S}, X {unit with an
    AdMob id: AdMob [req, matched, imp] over W's complete days K}, ufmt (per unit its AdMob format; ids of mixed formats
    GA4's; None without an id) and bu (per unit's AdMob ids of one format [ids, format, req, matched, imp] over K: the
    benchmark's votes — one per unit as the screens see it, a name on two AdMob apps' ids is one unit)."""
    fu = [d for d in app.days if d <= w[-1] and d in app.whole["a"] and (app.ads.get(d) or {}).get("g") == "fu"]
    sw = [d for d in fu if d >= w[0]]
    S, src = (sw, "W") if len(sw) >= SIG_MIN else (fu[-SIG_N:], "new")
    g, G = {}, {}
    for d in S:
        for (c, u, f), n in app.ads[d]["cu"].items():
            if n and (allf or fgroup(f) != 1 and fgroup(f) != 2) and kind(c) == "s" and (u, f) in app.uix:
                x = g.setdefault(c, {})
                ui = app.uix[(u, f)]
                x[ui] = x.get(ui, 0) + n
        for k, n in (app.w.get(d) or {}).items():
            if k in app.uix:
                G[app.uix[k]] = G.get(app.uix[k], 0) + n
    K = [d for d in w if app.adm and app.adm.complete(d)]
    X, ufmt, bu = {}, [], []
    for ui, u in enumerate(app.units):
        fs = {app.adm.ids[i]["fmt"] for i in u[2] if i in app.adm.ids}
        ufmt.append((next(iter(fs)) if len(fs) == 1 else u[1]) if fs else None)
        if ufmt[-1]:                          # file 2's day values (1 place): the page sums the very same numbers
            s = [0.0, 0.0, 0.0]
            for d in K:
                v = app.unit_adm(ui, d)
                for j in range(3):
                    s[j] += _r(v[j], 1) if v else 0
            X[ui] = s
            if len(fs) == 1:
                bu.append([tuple(u[2]), ufmt[-1]] + s)
    return {"S": S, "sig": [src, len(S), S[0], S[-1]] if S else None, "g": g, "G": G, "K": K, "X": X, "ufmt": ufmt,
            "bu": bu}


def ab_row(app, side, c, w, allf):
    """One screen class's absolute numbers over W, exact: Ads / view % (its ads ÷ its views × 100 on the W days with
    both — the page's sumItem days, Imp / user / day's ads), and its AdMob side Σ σ_u × X_u over its units (σ_u =
    min(1, g_u ÷ G_u): a unit shared by screens gives each its share, the rates stay the unit's) → Fill = matched ÷
    requests, Show rate = impressions ÷ matched; per AdMob format p [share of the class's unit ads (unmatched in the
    whole), req, matched, imp]; unm the unmatched share (no AdMob id, or G 0: never in a rate); why "" or the reason a
    number is "—" (never a silent 0); nm: not measurable (no matched unit, or no complete AdMob day in W). No ads of
    its own in W: no Fill / Show rate and no parts (σ from older split days would lend it its units' rates)."""
    v = a = 0
    for d in w:
        vd, ad = app.views.get(d), app.ads.get(d)
        q = None if ad is None else ad["tot"] if allf else ad["cls"]
        if vd is None or q is None:
            continue
        v += vd.get(c, (0, 0))[0]
        a += q.get(c, 0) if allf else q.get(c, (0,))[0]
    if not a:
        return {"ads": a, "views": v, "av": 100 * a / v if v > 0 else None, "fill": None, "show": None, "p": {},
                "unm": None, "why": "is period me is screen pe koi ad nahi", "nm": True}
    gc = side["g"].get(c) or {}
    tot = sum(gc.values())
    parts, unm = {}, 0
    for ui, n in sorted(gc.items()):
        if ui not in side["X"] or not side["G"].get(ui):
            unm += n
            continue
        s = min(1.0, n / side["G"][ui])
        p = parts.setdefault(side["ufmt"][ui], [0.0, 0.0, 0.0, 0.0])
        p[0] += n
        for j in range(3):
            p[j + 1] += s * side["X"][ui][j]
    T = [sum(p[j] for p in parts.values()) for j in (1, 2, 3)]
    why = ("AdMob data nahi" if not app.adm else
           "GA4 ne is app ke ads screen × unit ke saath nahi diye" if not side["S"] else
           "GA4 ne is screen ke ads unit ke saath nahi diye" if not tot else
           "GA4 unit names AdMob me nahi mile (unmatched 100 %)" if not parts else
           "AdMob ~1–2 din baad pura hota hai" if not side["K"] else
           "koi ad fill nahi hua" if T[0] and not T[1] else "")
    return {"ads": a, "views": v, "av": 100 * a / v if v > 0 else None, "fill": T[1] / T[0] if T[0] else None,
            "show": T[2] / T[1] if T[1] else None, "p": {f: [p[0] / tot] + p[1:] for f, p in parts.items()},
            "unm": unm / tot if tot else None, "why": why, "nm": not parts or not side["K"]}


def ab_tside(app, w):
    """The full-screen triggers' σ side over window w (W): σ's source days S = W's whole units-read days (the shipped "w"
    state; under SIG_MIN of them the newest SIG_N such days ≤ W's end), g {unit: its GA4 ads over S} and G {AdMob ids
    tuple: the GA4 ads over S of every GA4 unit with those ids} — an AdMob unit two GA4 units share (a name in two cases,
    two GA4 formats) is split between them as a screen's σ splits a unit."""
    ok = [d for d in app.days if d <= w[-1] and d in app.whole["w"] and d in app.w]
    sw = [d for d in ok if d >= w[0]]
    S, src = (sw, "W") if len(sw) >= SIG_MIN else (ok[-SIG_N:], "new")
    g, G = {}, {}
    for d in S:
        for k, n in app.w[d].items():
            ui = app.uix.get(k)
            if ui is not None and n:
                g[ui] = g.get(ui, 0) + n
                if app.units[ui][2]:
                    t = tuple(app.units[ui][2])
                    G[t] = G.get(t, 0) + n
    return {"S": S, "sig": [src, len(S), S[0], S[-1]] if S else None, "g": g, "G": G}


def ab_trig(app, side, ts, gi, w):
    """One full-screen trigger's absolute numbers over W, the screens' rule (ab_row) on its units: its ads (the units
    read on W's days with app visits — the page's sumItem days), then per AdMob unit (its ids tuple, once) of the trigger
    σ = min(1, the trigger's GA4 ads on it ÷ every GA4 unit's on it) over ts's days × its AdMob [req, matched, imp] on
    W's complete days → Fill = matched ÷ requests, Show rate = impressions ÷ matched; per AdMob format p [share of the
    trigger's GA4 ads (unmatched in the whole), req, matched, imp]; unm the share of units with no AdMob id (or no GA4
    ads anywhere): never in a rate; sh the shared units [name, σ] (σ < 0.95); why "" or why a number is "—"."""
    uis = app.trig[gi][2]
    keys = [(app.units[u][0], app.units[u][1]) for u in uis]
    a = nd = 0
    for d in w:
        wd = app.w.get(d)
        if wd is None or app.vis.get(d) is None:
            continue
        nd += 1
        a += sum(wd.get(k, 0) for k in keys)
    if not a:
        return {"ads": a, "av": None, "fill": None, "show": None, "p": {}, "unm": None, "sh": [], "nm": True,
                "why": "is period me is trigger ke koi ad nahi" if nd else "is period me units ka data nahi"}
    tot = sum(ts["g"].get(u, 0) for u in uis)
    by, unm = {}, 0
    for u in uis:
        n = ts["g"].get(u, 0)
        if not n:
            continue
        t = tuple(app.units[u][2])
        if not t or u not in side["X"] or not ts["G"].get(t):
            unm += n
            continue
        by.setdefault(t, [u, 0])[1] += n
    parts, sh = {}, []
    for t, (u, n) in sorted(by.items()):
        s = min(1.0, n / ts["G"][t])
        p = parts.setdefault(side["ufmt"][u], [0.0, 0.0, 0.0, 0.0])
        p[0] += n
        for j in range(3):
            p[j + 1] += s * side["X"][u][j]
        if s < 0.95:
            sh.append([app.units[u][0] or app.units[u][3], _r(s, 4)])
    T = [sum(p[j] for p in parts.values()) for j in (1, 2, 3)]
    why = ("AdMob data nahi" if not app.adm else
           "GA4 ne is app ke units whole nahi diye" if not ts["S"] else
           "GA4 ne is trigger ke ads unit ke saath nahi diye" if not tot else
           "GA4 unit names AdMob me nahi mile (unmatched 100 %)" if not parts else
           "AdMob ~1–2 din baad pura hota hai" if not side["K"] else
           "koi ad fill nahi hua" if T[0] and not T[1] else "")
    return {"ads": a, "av": None, "fill": T[1] / T[0] if T[0] else None, "show": T[2] / T[1] if T[1] else None,
            "p": {f: [p[0] / tot] + p[1:] for f, p in parts.items()}, "unm": unm / tot if tot else None, "sh": sh,
            "why": why, "nm": not parts or not side["K"]}


def ab_ship(ab, sig):
    """File 2's rows[rid]["ab"]: shares / rates 4 places, sums 1, Ads / view % 2."""
    return {"av": _r(ab["av"], 2), "fill": _r(ab["fill"], 4), "show": _r(ab["show"], 4),
            "p": {f: [_r(p[0], 4), _r(p[1], 1), _r(p[2], 1), _r(p[3], 1)] for f, p in sorted(ab["p"].items())},
            "sig": sig, "unm": _r(ab["unm"], 4), "why": ab["why"]}


def _qs(xs, qs):
    """Unweighted linear-interpolation quantiles of xs + their n, or None under AB_MIN_N values."""
    if len(xs) < AB_MIN_N:
        return None
    xs, out = sorted(xs), []
    for p in qs:
        k = (len(xs) - 1) * p
        i = int(k)
        j = min(i + 1, len(xs) - 1)
        out.append(xs[i] + (xs[j] - xs[i]) * (k - i))
    return out + [len(xs)]


def ab_bench(apps):
    """The format benchmark over every built app, {app id: (bu, {item: (vs-own-past word, ab_row)}, sig)} → per AdMob
    format: the units' Fill (requests ≥ AB_REQ) and Show rate (matched ≥ AB_MT), one vote per unit (its AdMob ids, once)
    over its app's W; Ads / view over the top screens with ≥ AB_ADS ads whose dominant part is ≥ AB_DOM (the measured
    population: a row's vs-own-past word is about its own past, not its level); nall = the format's units (the ones
    left out are the small ones: counted, never dropped silently). Exact (ab_bench_ship rounds)."""
    units, seen, av, k = {}, set(), {}, 0
    for aid in sorted(apps):
        bu, rows, _ = apps[aid]
        k += 1 if bu else 0
        for pid, f, rq, mt, im in bu:
            if pid not in seen:
                seen.add(pid)
                units.setdefault(f, []).append((rq, mt, im))
        for word, ab in rows.values():
            if ab["p"] and ab["av"] is not None and ab["ads"] >= AB_ADS:
                f, p = max(sorted(ab["p"].items()), key=lambda kv: kv[1][0])
                if p[0] >= AB_DOM:
                    av.setdefault(f, []).append(ab["av"])
    fm = {}
    for f in sorted(set(units) | set(av)):
        us = units.get(f) or []
        fm[f] = {"fill": _qs([mt / rq for rq, mt, _ in us if rq >= AB_REQ], AB_Q),
                 "show": _qs([im / mt for _, mt, im in us if mt >= AB_MT], AB_Q),
                 "av": _qs(av.get(f) or [], AB_Q[:3]), "nall": len(us)}
    return {"fmt": fm, "min": {"req": AB_REQ, "mt": AB_MT, "ads": AB_ADS, "n": AB_MIN_N}, "apps": k}


def ab_bench_ship(B):
    """scr_all's "bench": rates 4 places, Ads / view % 2, n as is; null = under AB_MIN_N; check = the developer texts."""
    def q(x, n):
        return None if x is None else [_r(v, n) for v in x[:-1]] + [x[-1]]
    return {"fmt": {f: {"fill": q(b["fill"], 4), "show": q(b["show"], 4), "av": q(b["av"], 2), "nall": b["nall"]}
                    for f, b in B["fmt"].items()}, "min": B["min"], "apps": B["apps"],
            "check": {k: CHECK[t[2]] for k, t in AB_TXT.items()}}


def _dm(s, ref):
    d = _d(s)
    return "%d %s%s" % (d.day, MONTHS[d.month - 1], "" if d.year == ref.year else " %d" % d.year)


def ab_judge(word, ab, B, sig, trig=False):
    """A top screen row's absolute status → [word, cause, weak [[k, format, value, median, p25], …] weakest first]: a
    vs-own-past word not judged stays (N/A, Too early); No ads; Not measurable (why); Low (a part ≥ AB_PART with fill
    under its format's p25 on ≥ AB_REQ requests, or show under p25 on ≥ AB_MT matched); Too few ads (no such part with
    ≥ AB_MT matched); Few ads (the dominant part ≥ AB_DOM, Ads / view under its format's p25); else OK. Cause: up to 2
    weak numbers, weakest (value ÷ median) first; a σ from older split days names them. trig: a full-screen trigger
    (ab_trig: no views, so no Few ads) — OK when a part ≥ AB_PART has a number its format's benchmark judges (≥ the
    floors), else No benchmark when such a part has the volume but its format no benchmark (under AB_MIN_N units: the
    number is shown, never judged), else Too few ads."""
    if word not in JUDGED:
        return [word, "", []]
    if not ab["ads"]:
        return ["No ads", "10 din me is %s koi ad nahi" % ("trigger ke" if trig else "screen pe"), []]
    if ab["nm"]:
        return ["Not measurable", ab["why"], []]
    fm, weak = B["fmt"], []
    for f, p in sorted(ab["p"].items(), key=lambda kv: (-kv[1][0], kv[0])):
        b = fm.get(f) or {}
        if p[0] < AB_PART:
            continue
        if b.get("fill") and p[1] >= AB_REQ and p[2] / p[1] < b["fill"][1]:
            weak.append(["fill", f, p[2] / p[1], b["fill"][2], b["fill"][1]])
        if b.get("show") and p[2] >= AB_MT and p[3] / p[2] < b["show"][1]:
            weak.append(["show", f, p[3] / p[2], b["show"][2], b["show"][1]])
    out = "Low"
    if not weak and trig:
        big = [(f, p, fm.get(f) or {}) for f, p in sorted(ab["p"].items()) if p[0] >= AB_PART]
        if any(b.get("fill") and p[1] >= AB_REQ or b.get("show") and p[2] >= AB_MT for f, p, b in big):
            return ["OK", "", []]
        nob = [f for f, p, b in big if not b.get("fill") and not b.get("show") and (p[1] >= AB_REQ or p[2] >= AB_MT)]
        if nob:
            return ["No benchmark", "%s: no benchmark (n < %d)" % (", ".join(FMT_NAME.get(f, f) for f in nob), AB_MIN_N),
                    []]
        return ["Too few ads", "har bade part pe AdMob matched %d se kam" % AB_MT, []]
    if not weak:
        if not any(p[0] >= AB_PART and p[2] >= AB_MT for p in ab["p"].values()):
            return ["Too few ads", "har bade part pe AdMob matched %d se kam" % AB_MT, []]
        f, p = max(sorted(ab["p"].items()), key=lambda kv: kv[1][0])
        a = (fm.get(f) or {}).get("av") if p[0] >= AB_DOM else None
        if not (a and ab["av"] is not None and ab["ads"] >= AB_ADS and ab["av"] < a[1]):
            return ["OK", "", []]
        out, weak = "Few ads", [["av", f, ab["av"], a[2], a[1]]]
    weak.sort(key=lambda x: x[2] / x[3] if x[3] else 0.0)
    cz = "; ".join("%s %d %% (%s median %d %%): %s" % (
        AB_TXT[k][0], round(v if k == "av" else 100 * v), FMT_NAME.get(f, f), round(m if k == "av" else 100 * m),
        AB_TXT[k][1]) for k, f, v, m, _ in weak[:2])
    if sig and sig[0] == "new":
        cz += " · unit mix from %s – %s" % (_dm(sig[2], _d(sig[3])), _dm(sig[3], _d(sig[3])))
    return [out, cz, [[k, f] + [_r(x, 2 if k == "av" else 4) for x in (v, m, q)] for k, f, v, m, q in weak]]


def _pf(v):
    return "—" if v is None else "%d %%" % round(100 * v)


def _pa(v):
    return "—" if v is None else ("%.1f %%" % v) if v < 10 else "%d %%" % round(v)


# ── v 4: Firebase's numbers and three signals (owner, 8 Nov 2026) ────────────────────────────────────────────────────
# The owner put Firebase's own "Pages and screens" export beside the tab: "data me gadbad lag rahi he … logic jo hamne easy
# analysis banane ke liye banaya he vo usefull nahi lag raha he". Approved: Firebase's numbers (Users, Views, Time / user,
# Ads, Revenue and its share), the full-screen rows from AdMob, and three plain signals instead of the old words.
#   * the page sums Views, Ads and Revenue (GA4 m, by screen) for ANY period; the users of a period are unique within it
#     (never a sum of days): the fetch reads them for the periods the page offers (pwin), file 2's "pu";
#   * full-screen rows: every AdMob unit of a full-screen format by its trigger label (trig4), summed on AdMob's OWN days
#     (the report zone's: never blended onto GA4 days) — file 2's "fs4", the app's AdMob total "adt";
#   * the signals, judged here for every period of pwin (file 2's "sig", scr_all's "sg" counts):
#       💡 b  Ads ki jagah — a screen with ≥ SIG_TIME of the app's screen time whose ads per minute are ≤ SIG_RATE of
#             the app's (final days whose views and ads by screen are whole; the screens' basis: inline, all formats
#             when allf);
#       ⚠️ w  Ads waste — a row whose AdMob units show under SIG_SHOW of what they fill, the filled-not-shown being
#             ≥ SIG_WASTE of the app's fills (screens: each unit's share σ of its GA4 ads on the screen, as ab_side;
#             full-screen rows: their AdMob units; AdMob's own complete days);
#       🔻 d  Gira — Imp / user / day ≥ SIG_DROP under the period before (a month: the month before; else the same
#             length just before), the row holding ≥ SIG_MAT of the app's ads, ≥ SIG_DAYS days with users on each side
#             (screens: Σ ads ÷ Σ the screen's daily users, users_by_day's days; full-screen: AdMob impressions ÷ the
#             app's daily users). Not for All time (nothing before it).
SIG_TIME, SIG_RATE = 0.10, 0.20
SIG_SHOW, SIG_WASTE = 0.50, 0.20
SIG_DROP, SIG_MAT, SIG_DAYS = 0.20, 0.05, 7
PW_ROLL = (7, 30, 60, 90)
USERS_FILE = "users.json.gz"


def _mlast(d):
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def pwin(td, d0):
    """The periods the page offers (its rng(): the property's calendar, ft = td − 2) → [(key, lo, hi, kind)]: today,
    yesterday, the last 7 / 30 / 60 / 90 days ending ft, this month (… today), all time (d0 … today), then every
    calendar month from d0's, newest first (the first from d0); lo never before d0; key "<lo>_<hi>". The fetch's
    pu_wanted, our own copy (never imported: a test keeps the two equal)."""
    td, d0 = _d(td), _d(d0)
    ft = td - timedelta(days=2)
    out, seen = [], set()

    def add(lo, hi, kd):
        lo = max(lo, d0)
        k = "%s_%s" % (_iso(lo), _iso(hi))
        if lo <= hi and k not in seen:
            seen.add(k)
            out.append((k, _iso(lo), _iso(hi), kd))
    add(td, td, "day")
    add(td - timedelta(days=1), td - timedelta(days=1), "day")
    for n in PW_ROLL:
        add(ft - timedelta(days=n - 1), ft, "roll")
    add(td.replace(day=1), td, "day")
    add(d0, td, "all")
    m = td.replace(day=1)
    while True:
        m = (m - timedelta(days=1)).replace(day=1)
        if _mlast(m) < d0:
            break
        add(m, _mlast(m), "month")
    return out


def period_users(data_dir, key):
    """The fetch's users of a period file (<key>/users.json.gz) → its dict, or {} (missing / unreadable: no Users)."""
    raw = _read_gz_bytes(os.path.join(data_dir, STORE_DIR, key, USERS_FILE))
    j = _json(raw) if raw is not None else None
    return j if isinstance(j, dict) and isinstance(j.get("w"), dict) else {}


def pu_ship(app, uf, wins):
    """File 2's "pu": {key: {"st", "u": [[screen index, users]], "tot", "fold", "thr"}} for the periods of `wins` the
    fetch has read (a class the build does not know is left out; a sampled / cut period ships its state only)."""
    out = {}
    for key, lo, hi, kd in wins:
        rec = (uf.get("w") or {}).get(key)
        if not isinstance(rec, dict) or rec.get("lo") != lo or rec.get("hi") != hi:
            continue
        e = {"st": rec.get("st") if rec.get("st") in ST_CH else "-"}
        if e["st"] in OK_ST:
            e["u"] = sorted([app.six[c], _i(n)] for c, n in (rec.get("r") or []) if c in app.six)
            e["tot"] = _i(rec.get("tot"))
            for k in ("fold", "thr"):
                if rec.get(k):
                    e[k] = _i(rec[k])
        out[key] = e
    return out


def trig4(app):
    """The full-screen rows from AdMob ("full-screen triggers AdMob se"): every AdMob unit of a full-screen format,
    grouped by its trigger label (trigger_label of its AdMob name) → [[format, label, [AdMob unit id, …]]] sorted; each
    AdMob unit in exactly one row — no GA4 read needed, so GA4's sampling never leaves one "—"."""
    by = {}
    for pid, e in sorted((app.adm.ids if app.adm else {}).items()):
        if e["fmt"] in FULL:
            by.setdefault((e["fmt"], trigger_label(e["name"], e["name"], "name", app.suffixes)), []).append(pid)
    return [[f, lab, pids] for (f, lab), pids in sorted(by.items())]


def adm_days(app, pids):
    """These AdMob units per app day, summed on AdMob's own days → [[req, matched, imp, revenue micros] or None per
    day] (None before AdMob's first day or after latest_complete: not complete yet)."""
    out = []
    for d in app.days:
        if not app.adm or not app.adm.first or d < app.adm.first or d > app.adm.latest:
            out.append(None)
            continue
        x = [0, 0, 0, 0]
        for pid in pids:
            v = ((app.adm.ids.get(pid) or {}).get("d") or {}).get(d)
            if v:
                for j in range(4):
                    x[j] += v[j]
        out.append(x)
    return out


def _prev(lo, hi, kd):
    """The period just before [lo, hi]: the month before for a month, else the same number of days before."""
    a, b = _d(lo), _d(hi)
    if kd == "month" or (kd == "day" and a.day == 1 and b != a) or (a.day == 1 and b == _mlast(a)):
        p = (a - timedelta(days=1)).replace(day=1)
        return _iso(p), _iso(_mlast(p))
    n = (b - a).days + 1
    return _iso(a - timedelta(days=n)), _iso(a - timedelta(days=1))


class _Pre:
    """Prefix sums over the app's days: rows of numbers per day (None or missing = nothing that day) → the Σ of any
    [lo, hi] (clamped to the app's days) in O(1)."""

    def __init__(self, app, rows, width):
        self.d0, self.n, self.w = _d(app.d0), len(app.days), width
        acc, run = [[0] * width], [0] * width
        for v in rows:
            if v:
                run = [run[j] + v[j] for j in range(width)]
            acc.append(run)
        self.acc = acc

    def sum(self, lo, hi):
        a, b = max(0, (_d(lo) - self.d0).days), min(self.n - 1, (_d(hi) - self.d0).days)
        if b < a:
            return [0] * self.w
        P, Q = self.acc[a], self.acc[b + 1]
        return [Q[j] - P[j] for j in range(self.w)]


def signals4(app, allf, wins, fs4, fsd):
    """The three signals for every period of `wins` → ({key: {row id: [[code, …], …]}}, {key: [💡, ⚠️, 🔻]}): row ids
    "s<screen index>" (screens) and "f<n>" (fs4's rows). 💡 ["b", time share, ads share]; ⚠️ ["w", unit, shown ÷
    filled, not shown ÷ the app's fills, filled, shown]; 🔻 ["d", before, now, before's lo, before's hi] (Imp / user /
    day). A screen's units are its AdMob unit ids (one AdMob unit two GA4 names share — two cases, with and without a
    format — is ONE unit: σ per ids, as ab_tside) with σ = min(1, its GA4 ads on the screen ÷ the units read's GA4 ads
    on those ids) over the period's whole unit-split days (under SIG_MIN: the newest SIG_N up to its end); a full-screen
    row's: its AdMob units, each once. 🔻's materiality: the row's share of its kind's ads (screens: the screens' ads;
    full-screen: the full-screen rows') in the period or in the one before, whichever is larger — a row whose ads
    stopped is the one to flag. Sums over periods are prefix sums (_Pre): the build's time grows with the days, never
    with days × periods."""
    ft, n_days = _iso(app.ft), len(app.days)
    scr = [c for c in app.screens if kind(c) == "s"]
    ci = {c: j for j, c in enumerate(scr)}
    # 💡 / 🔻's days: final, views and ads by screen whole → per screen class [engagement, ads] per day
    rows_e, rows_a, ok_d = [], [], []
    for d in app.days:
        v, a = app.views.get(d), app.ads.get(d)
        q = None if a is None else (a["tot"] if allf else a["cls"])
        if d > ft or v is None or q is None or d not in app.whole["v"] or d not in app.whole["a"]:
            rows_e.append(None)
            rows_a.append(None)
            ok_d.append(None)
            continue
        e_, a_ = [0] * len(scr), [0] * len(scr)
        for c, j in ci.items():
            e_[j] = (v.get(c) or [0, 0])[1]
            a_[j] = q.get(c, 0) if allf else (q.get(c) or [0])[0]
        rows_e.append(e_)
        rows_a.append(a_)
        ok_d.append([1])
    PE, PA, PD = _Pre(app, rows_e, len(scr)), _Pre(app, rows_a, len(scr)), _Pre(app, ok_d, 1)
    # the screens' Imp / user / day days (users_by_day's: final ≤ ftU, users read and both whole): per top screen
    # [its ads, its users, 1] on the days it has users
    fu_, tops = _iso(app.ftu), [c for c in app.top if kind(c) == "s"]
    rows_u = []
    for k, d in enumerate(app.days):
        x = app.su.get(d) if d <= fu_ else None
        if x is None or rows_a[k] is None:
            rows_u.append(None)
            continue
        r = []
        for c in tops:
            u = x.get(c, 0)
            r += [rows_a[k][ci[c]], u, 1] if u > 0 else [0, 0, 0]
        rows_u.append(r)
    PU = _Pre(app, rows_u, 3 * len(tops))
    # σ's inputs per whole unit-split day: [(class, AdMob ids, its GA4 ads)] on the screens' basis, and the units read's
    # GA4 ads per AdMob ids
    fu, fuu, fug = [], {}, {}
    for d in app.days:
        a = app.ads.get(d)
        if not a or a.get("g") != "fu" or d not in app.whole["a"] or d not in app.whole["w"] or d not in app.w:
            continue                             # (σ's numerator and its denominator from the same days)
        fu.append(d)
        r = []
        for (c, u, f), n in a["cu"].items():
            if n and (allf or fgroup(f) not in (1, 2)) and kind(c) == "s" and (u, f) in app.uix:
                ids = tuple(app.units[app.uix[(u, f)]][2])
                if ids:
                    r.append((c, ids, n))
        fuu[d] = r
        g = {}
        for k2, n in (app.w.get(d) or {}).items():
            ui = app.uix.get(k2)
            ids = tuple(app.units[ui][2]) if ui is not None else ()
            if ids and n:
                g[ids] = g.get(ids, 0) + n
        fug[d] = g
    # AdMob per unit id, on its own days ([req, matched, imp, revenue]); the full-screen rows per day (+ the app's daily
    # users) for their Imp / app user / day
    pids = sorted(app.adm.ids) if app.adm else []
    PX = {pid: _Pre(app, adm_days(app, [pid]), 4) for pid in pids}
    PF = []
    for n_ in range(len(fs4)):
        arr = fsd[n_] if n_ < len(fsd) else []
        PF.append(_Pre(app, [[v[2], app.au[d], 1] if v is not None and k < len(arr) and app.au.get(d) else None
                             for k, (d, v) in enumerate(zip(app.days, arr + [None] * (n_days - len(arr))))], 3))
    names = {}
    for u in app.units:
        if u[2] and u[4] != "admob":
            names.setdefault(tuple(u[2]), u[0] or u[3])
    out, cnt = {}, {}
    for key, lo, hi, kd in wins:
        sig = {}
        hi_f = min(hi, ft)
        E = PE.sum(lo, hi_f) if lo <= hi_f else [0] * len(scr)
        A = PA.sum(lo, hi_f) if lo <= hi_f else [0] * len(scr)
        te, ta = sum(E), sum(A)
        if te > 0 and ta > 0:                    # 💡
            for c, j in ci.items():
                if E[j] and E[j] / te >= SIG_TIME and A[j] / E[j] <= SIG_RATE * ta / te:
                    sig.setdefault("s%d" % app.six[c], []).append(["b", _r(E[j] / te, 4), _r(A[j] / ta, 4)])
        # ⚠️
        X = {pid: PX[pid].sum(lo, hi) for pid in pids}
        fills = sum(x[1] for x in X.values())
        if fills > 0:
            sw = [d for d in fu if lo <= d <= hi]
            S = sw if len(sw) >= SIG_MIN else [d for d in fu if d <= hi][-SIG_N:]
            g, G = {}, {}
            for d in S:
                for c, ids, n in fuu[d]:
                    gc = g.setdefault(c, {})
                    gc[ids] = gc.get(ids, 0) + n
                for ids, n in fug[d].items():
                    G[ids] = G.get(ids, 0) + n
            old_mix = [S[0], S[-1]] if S and S is not sw else None
            for c in sorted(g):
                if c not in ci or not A[ci[c]]:
                    continue
                mt = im = 0.0
                best, bw = None, -1.0
                for ids, n in sorted(g[c].items()):
                    if not G.get(ids):
                        continue
                    sg = min(1.0, n / G[ids])
                    xm = sum(X[p][1] for p in ids if p in X)
                    xi = sum(X[p][2] for p in ids if p in X)
                    mt += sg * xm
                    im += sg * xi
                    if sg * (xm - xi) > bw:
                        best, bw = ids, sg * (xm - xi)
                if mt > 0 and im / mt < SIG_SHOW and mt - im >= SIG_WASTE * fills and best is not None:
                    sig.setdefault("s%d" % app.six[c], []).append(
                        ["w", names.get(best) or app.adm.ids[best[0]]["name"], _r(im / mt, 4), _r((mt - im) / fills, 4),
                         round(mt), round(im)] + (old_mix or []))       # (+ the unit mix's days when not the period's)
            for n_, (f, lab, ps) in enumerate(fs4):
                mt, im = sum(X[p][1] for p in ps if p in X), sum(X[p][2] for p in ps if p in X)
                if mt > 0 and im / mt < SIG_SHOW and mt - im >= SIG_WASTE * fills:
                    big = max((p for p in ps if p in X), key=lambda p: (X[p][1] - X[p][2], p))
                    sig.setdefault("f%d" % n_, []).append(
                        ["w", app.adm.ids[big]["name"], _r(im / mt, 4), _r((mt - im) / fills, 4), mt, im])
        if kd != "all":                          # 🔻
            plo, phi = _prev(lo, hi, kd)
            phi_f = min(phi, ft)
            Ap = PA.sum(plo, phi_f) if plo <= phi_f else [0] * len(scr)
            tap = sum(Ap)
            U1, U0 = PU.sum(lo, hi_f) if lo <= hi_f else [0] * (3 * len(tops)), PU.sum(plo, phi_f) if plo <= phi_f \
                else [0] * (3 * len(tops))
            for t_, c in enumerate(tops):
                j = ci[c]
                mat = max(A[j] / ta if ta > 0 else 0, Ap[j] / tap if tap > 0 else 0)
                a1, u1, n1 = U1[3 * t_:3 * t_ + 3]
                a0, u0, n0 = U0[3 * t_:3 * t_ + 3]
                if mat < SIG_MAT or n1 < SIG_DAYS or n0 < SIG_DAYS or not u1 or not u0:
                    continue
                cur, pre = a1 / u1, a0 / u0
                if pre > 0 and cur <= (1 - SIG_DROP) * pre:
                    sig.setdefault("s%d" % app.six[c], []).append(["d", _r(pre, 4), _r(cur, 4), plo, phi])
            T1 = [PF[n_].sum(lo, hi) for n_ in range(len(fs4))]
            T0 = [PF[n_].sum(plo, phi) for n_ in range(len(fs4))]
            t1, t0 = sum(x[0] for x in T1), sum(x[0] for x in T0)
            for n_ in range(len(fs4)):
                (a1, u1, n1), (a0, u0, n0) = T1[n_], T0[n_]
                mat = max(a1 / t1 if t1 > 0 else 0, a0 / t0 if t0 > 0 else 0)
                if mat < SIG_MAT or n1 < SIG_DAYS or n0 < SIG_DAYS or not u1 or not u0:
                    continue
                cur, pre = a1 / u1, a0 / u0
                if pre > 0 and cur <= (1 - SIG_DROP) * pre:
                    sig.setdefault("f%d" % n_, []).append(["d", _r(pre, 4), _r(cur, 4), plo, phi])
        if sig:
            out[key] = sig
        c3 = [0, 0, 0]
        for xs in sig.values():
            for x in xs:
                c3["bwd".index(x[0])] += 1
        # (not judged: no final whole day for 💡 · no AdMob fill for ⚠️ · All time, or under SIG_DAYS final days for 🔻)
        days_f = PD.sum(lo, hi_f)[0] if lo <= hi_f else 0
        if not days_f:
            c3[0] = None
        if fills <= 0:
            c3[1] = None
        if kd == "all" or days_f < SIG_DAYS:
            c3[2] = None
        cnt[key] = c3
    return out, cnt


def build_app(meta, data_dir, out_dir, now, dashboard, by_id, counts, broken=None, idx=None):
    """One app → (file-2 name, its raw bytes, scr_l name, its raw bytes, the scr_all entry, kept shard names, counts) —
    the shards and scr_l written here; file 2 written by the caller after this returns (write order). broken (a list):
    gets (group, month, error type) of every store month file of the app that cannot be read or parsed — its days ship
    the state "x" (store file unreadable). idx: the app's out-file index (_idx_path), updated in place."""
    key = gu.file_key(str(meta["app_id"]))
    broken = [] if broken is None else broken
    recent = load_recent(data_dir, key)
    app = App(meta, core_days(data_dir, key, meta, recent, broken), now, dashboard, by_id, broken)
    if not app.d0:
        return None
    # the users beside the ads, BEFORE the statuses: the app's daily users (Uninstall store) and the users by screen
    # (the small group's uV, read without registering a class); ftU = the last final day with both
    au, auw = app_users(meta, data_dir)
    set_users(app, au, auw, screen_users(app, data_dir, recent))
    rows, ast = statuses(app)
    report_rows = {rid: row for rid, row, _, _, _, _, st in rows if st["word"] in ("Worse", "Watch")}
    causes = {}
    for rid, row, label, k, ii, ser, st in rows:
        if st["word"] in JUDGED:
            causes[rid] = cause(app, row, st)
            st["cause"] = cause_u(st, causes[rid])
            st["group"] = cause_group(st["cause"])
    alist = app_list(ast, rows)
    # layers: shards first (write order), then scr_l
    keep = set()
    lay = {}
    for grp in ("ver", "cc"):
        L = Layer(app, grp, data_dir, out_dir, recent, report_rows, counts, idx).run()
        lay[grp] = L
        keep |= L.keep
    ver, order, wsame = lay["ver"].versions()
    for grp in ("ver", "cc"):
        broken += [(grp, m, t) for m, t in sorted(lay[grp].broken.items())]
    prev = {v: ver[v]["prev"] for v in ver}
    sdays, sst, clicks, users = small_days(app, data_dir, recent, broken, counts)
    # a store month file that cannot be read: its days ship "x" (file 2's day states and scr_all's state strings)
    mark_lost(app, broken, lambda i: app.st[i] if i in GROUPS["core"] else sst[i] if i in GROUPS["small"] else
              lay["ver"].st[i] if i in GROUPS["ver"] else lay["cc"].st[i])
    w, n = app.windows()
    allf = app.allf()
    # v 4: the periods the page offers, their users (the fetch's), the full-screen rows from AdMob on its own days, the
    # app's AdMob total, and the three signals for every one of those periods
    try:
        wins = pwin(app.td, app.d0)
        fs4 = trig4(app)
        fsd = [adm_days(app, ps) for _, _, ps in fs4]
        adt = adm_days(app, sorted(app.adm.ids)) if app.adm else []
        sig4, sg4 = signals4(app, allf, wins, fs4, fsd)
        uf4 = period_users(data_dir, key)
        pu4 = pu_ship(app, uf4, wins)
        cur4 = str(((uf4.get("prop") or {}).get("currency")) or "USD")
    except Exception as e:                       # v 4's numbers never cost the app its files: counted, ONE health line
        counts["v4"] = counts.get("v4", 0) + 1   # per build (run), the app ships without them ("—" with the why)
        counts.setdefault("v4_err", type(e).__name__)
        wins, fs4, fsd, adt, sig4, sg4, pu4, cur4 = [], [], [], [], {}, {}, {}, "USD"
    # the absolute numbers over W (every screen row; the words need every app's benchmark: run() after the app loop)
    side = ab_side(app, w, allf)
    abr = {rid: ab_row(app, side, row[1], w, allf) for rid, row, *_ in rows if row[0] == "s"}
    # … and every full-screen trigger's (its units, σ on its own side: the units read)
    ts = ab_tside(app, w)
    abt = {rid: ab_trig(app, side, ts, row[1], w) for rid, row, *_ in rows if row[0] == "t"}
    fbd, rtext = {}, {}
    for rid, row, label, k, ii, ser, st in rows:
        if st["word"] in JUDGED:
            fbd[rid] = first_bad_day(ser, app.final, st["rn"])
        if rid in report_rows:
            rtext[rid] = row_report(app, label, "screen" if row[0] == "s" else "full-screen trigger", st,
                                    causes.get(rid) or {}, ser, fbd.get(rid), _ver_line(app, row, order, wsame, prev),
                                    _cc_line(lay["cc"].wsum.get(rid)), {v: ver[v]["first"] for v in ver},
                                    abr.get(rid) or abt.get(rid))
    dq, dql = dq_items(app, clicks)
    nvr = nvr_split(app, sdays, w, n, ast)
    head = report_head(app, key, alist, ast, nvr, rows)
    if dql:
        head += ["Data quality:"] + ["  - " + x for x in dql]
    app_text = "\n\n".join(["\n".join(head)] + [rtext[r] for r, *_ in rows if r in rtext])
    # file 2
    days2, adm = [], {}
    for d in app.days:
        e = {}
        v = app.views.get(d)
        if v is not None:
            e["v"] = [[app.six[c], x[0], x[1]] for c, x in sorted(v.items())]
        a = app.ads.get(d)
        if a is not None:
            if a["g"] == "fu":
                r_ = [[app.six[c], app.uix[(u, f)], n_] for (c, u, f), n_ in sorted(a["cu"].items())
                      if (u, f) in app.uix]
            elif a["g"] == "f":
                r_ = [[app.six[c]] + x for c, x in sorted(a["cls"].items())]
            else:
                r_ = None if a["tot"] is None else [[app.six[c], n_] for c, n_ in sorted(a["tot"].items())]
            e["a"] = {"g": a["g"], "r": r_}
        wd = app.w.get(d)
        if wd is not None:
            e["w"] = [[app.uix[k], n_] for k, n_ in sorted(wd.items()) if k in app.uix]
        mr = app.rev.get(d)
        if mr is not None:
            e["m"] = [[app.six[c], x[0], x[1]] for c, x in sorted(mr.items())]
        if d in app.ta:
            e["ta"] = [[f, n_] for f, n_ in sorted(app.ta[d].items())]
        if d in app.pattern and app.pattern[d][1] is not None or app.dup.get(d):
            e["dup"] = [app.dup.get(d, 0), _r((app.pattern.get(d) or (None, None))[1], 3)]
        stc = {i: app.st[i][d] for i in GROUPS["core"] if d in app.st[i]}
        if stc:
            e["st"] = stc
        days2.append(e or None)
    if app.adm:
        for ui, u in enumerate(app.units):
            if u[2]:
                adm[str(ui)] = [None if (x := app.unit_adm(ui, d)) is None else [_r(x[0], 1), _r(x[1], 1), _r(x[2], 1)]
                                for d in app.days]
    rows2 = {}
    for rid, row, label, k, ii, ser, st in rows:
        cz = causes.get(rid) or {}
        rows2[rid] = {"st": [st["word"], st["why"], st["score"]], "z": st["z"], "h": st["h"],
                      "W": [st["VW"], st["AW"], st["dW"]], "N": [st["VN"], st["AN"], st["dN"]],
                      "U": [st["UW"], st["UN"]], "imp": st["imp"], "own": st["own"], "parts": st["parts"],
                      "reach": st["reach"], "base": st.get("bases"), "group": st.get("group", ""),
                      "cause": cz.get("cause", ""), "terms": cz.get("terms"), "units": cz.get("units"),
                      "fbd": fbd.get(rid)}
        if rid in abr:
            rows2[rid]["ab"] = ab_ship(abr[rid], side["sig"])
        elif rid in abt:
            rows2[rid]["ab"] = ab_ship(abt[rid], ts["sig"])
    allfs = app.allf_share() if allf else None
    notes = {"zone": "assumed" if app.adm.assumed else ("account" if app.adm else "none"),
             "admob": "ok" if app.adm else "none", "allf": allf, "allfs": allfs,
             "runs": [[r["a"], r["b"], 1 if r["ok"] else 0, 1 if r["open"] else 0] for r in app.runs],
             "w": [w[0], w[-1]], "n": [n[0], n[-1]], "dq": dq, "ftu": _iso(app.ftu), "nvr": nvr}
    # scr_l (after the shards; the screens list is final once the small records are encoded)
    lbody = {"v": V, "key": key, "app_id": app.aid, "d0": app.d0, "items": app.ditems, "days": _SPLICE,
             "ver": ver, "ver_order": order, "ver_m": lay["ver"].msum(), "cc_m": lay["cc"].msum(),
             "shards": {"r": lay["ver"].shards, "c": lay["cc"].shards},
             "big": {"r": sorted(lay["ver"].big), "c": sorted(lay["cc"].big)},
             "failed": {"r": sorted(lay["ver"].failed), "c": sorted(lay["cc"].failed)},
             "report": {"app": app_text, "rows": rtext}}
    body2 = {"v": V, "key": key, "app_id": app.aid, "ft": _iso(app.ft), "td": _iso(app.td), "d0": app.d0,
             "screens": [[c, kind(c)] for c in app.screens], "units": app.units, "trig": app.trig, "days": days2,
             "adm": adm, "rows": rows2, "notes": notes, "ufmt": side["ufmt"],
             "pw": [list(x) for x in wins], "pu": pu4, "sig": sig4,
             "fs4": [[f, lab, [app.adm.ids[p]["name"] for p in ps]] for f, lab, ps in fs4], "fsd": fsd, "adt": adt}
    if cur4 != "USD":                                # GA4's revenue in another currency: shipped, the page says so
        body2["cur"] = cur4
    # the users beside the ads: the top screens' users per final day ≤ ftU ("U", their screen indexes "Us": the screen
    # rows) and the app's daily active users per final day ≤ ftU ("au": GA4's own, the same stream; also in scr_all) —
    # or why the app has none ("auw": none · stream · cut)
    uu = users_by_day(app)
    if uu is not None:
        body2["Us"], body2["U"] = uu
    aul = daily_users(app)
    if aul is not None:
        body2["au"] = aul
    else:
        body2["auw"] = app.auw or "none"
    # scr_all entry
    vis, V_, A_, ta = [], [], [], []
    ni = len(app.items)
    for d in app.days:
        vis.append(app.vis.get(d))
        v = app.views.get(d)
        if v is None:
            V_.append(None)
        else:
            x = [0] * ni
            for c, y in v.items():
                x[app.item_of(c)] += y[0]
            V_.append([x[i] if i < app.fs0 else None for i in range(ni)])
        a, wd = app.ads.get(d), app.w.get(d)
        if a is None and wd is None:
            A_.append(None)
        else:
            x = [None] * ni
            src = None if a is None else (a["tot"] if allf else ({c: q[0] for c, q in a["cls"].items()}
                                                                   if a["cls"] is not None else None))
            if src is not None:
                for i in range(app.fs0):
                    x[i] = 0
                for c, q in src.items():
                    x[app.item_of(c)] += q
            if wd is not None:
                for gi, (f, lab, uis) in enumerate(app.trig):
                    x[app.fs0 + gi] = sum(wd.get((app.units[u][0], app.units[u][1]), 0) for u in uis)
            A_.append(x)
        t = app.ta.get(d)
        ta.append(None if t is None else [sum(n_ for f, n_ in t.items() if fgroup(f) == 0),
                                         sum(n_ for f, n_ in t.items() if fgroup(f) == 1), t.get("notset", 0)])
    stall = {}
    for i in READ_IDS:
        src = app.st.get(i) if i in GROUPS["core"] else (sst.get(i) if i in GROUPS["small"] else
                                                       (lay["ver"].st.get(i) if i in GROUPS["ver"] else lay["cc"].st.get(i)))
        stall[i] = "".join((src or {}).get(d, "-") for d in app.days)
    # per display item: [word, why, score, cause, its Needs attention group, impact, W days] — the W days (its whole days
    # of the last W_DAYS) here, not only in file 2: Needs attention's "n/10 days" is drawn from scr_all alone — + [the
    # absolute word, its cause, the weak numbers]: "", "", [] until run() judges them on every app's benchmark
    status, abj, abjt = {}, {}, {}
    for rid, row, label, k, ii, ser, st in rows:
        if ii is not None:
            cz = causes.get(rid) or {}
            status[str(ii)] = [st["word"], st["why"], st["score"],
                               st.get("cause", "") if st["word"] in FLAGS else "",
                               st.get("group", "") if st["word"] in FLAGS else "", st["imp"], st["dW"], "", "", []]
            if rid in abr:
                abj[str(ii)] = (st["word"], abr[rid])
            elif rid in abt:
                abjt[str(ii)] = (st["word"], abt[rid])
    bf = {i: _bf(r) for i, r in ((meta.get("reads") or {}).items()) if isinstance(r, dict)}
    entry = {"key": key, "ft": _iso(app.ft), "td": _iso(app.td), "d0": app.d0, "items": app.items, "vis": vis,
             "V": V_, "A": A_, "ta": ta, "st": stall, "bf": bf, "status": status, "app": alist, "dq": dq,
             "ftu": _iso(app.ftu), "dk": "".join(str(app.dup.get(d, 0)) for d in app.days), "lo": None, "lt": None}
    # the App total and All apps from this file alone: the app's daily users per day ≤ ftU (null else) — or why none
    if aul is not None:
        entry["au"] = aul
    else:
        entry["auw"] = app.auw or "none"
    if nvr:
        entry["nvr"] = {k: nvr[k] for k in ("mix", "within", "vpu")}
    # v 4: per day [GA4's revenue on every screen, AdMob's app total] (micros; None where missing), the app's users per
    # period ("pt", the fetch's), the signals' counts per period ("sg")
    entry["rv"] = [None if (g_ is None and (k_ >= len(adt) or adt[k_] is None)) else
                   [None if g_ is None else sum(x[0] for x in g_.values()),
                    None if k_ >= len(adt) or adt[k_] is None else adt[k_][3]]
                   for k_, g_ in enumerate(app.rev.get(d) for d in app.days)]
    entry["pt"] = {k_: e_["tot"] for k_, e_ in pu4.items() if "tot" in e_}
    entry["sg"] = sg4
    if allf:                                         # why the screens count every format: 1 format not recorded, 2 no
        entry["allf"], entry["allfs"] = allf, allfs  # split from GA4; allfs its measured full-screen share on screens
    c = counts
    c["rows"] += len(rows)
    c["judged"] += sum(1 for r in rows if r[6]["word"] in JUDGED)
    c["worse"] += alist[2]
    c["watch"] += alist[3]
    c["users"] += 1 if app.au and app.su else 0
    c["stale"] += 1 if stale_users(app) else 0
    return {"app": app, "body2": body2, "lraw": _splice(lbody, [sdays.get(d) for d in app.days]), "entry": entry,
            "keep": keep,
            "seen": lay["ver"].seen | lay["cc"].seen, "ab": (side["bu"], abj, side["sig"]), "abt": (abjt, ts["sig"])}


# ── run ──────────────────────────────────────────────────────────────────────────────────────

def _clean(out_dir, keep):
    try:
        for nm in os.listdir(out_dir):
            if APP_RE.match(nm) and nm not in keep:
                try:
                    os.remove(os.path.join(out_dir, nm))
                except OSError:
                    pass
    except OSError:
        pass


def _by_id(data_dir):
    try:
        with open(os.path.join(data_dir, "app_store_ids.json"), encoding="utf-8") as f:
            v = json.load(f).get("by_id") or {}
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def selected(dashboard):
    """The app ids selected in the dashboard's apps_catalog (rows with "selected" true), or None when there is no
    catalog (every store app is built). A store app the catalog does not select is not built (the history job may
    have fetched it): its files go with the stale ones."""
    cat = [c for c in dashboard.get("apps_catalog") or [] if isinstance(c, dict)]
    return {str(c.get("app_id")) for c in cat if c.get("selected")} if cat else None


def run(dashboard, data_dir, out_dir, s=None, now=None):
    """This build's files → HEADER_PATHS, or [] (no store yet / a failure: the files removed, no pointer). Never raises."""
    global LINE
    LINE = None
    if not isinstance(dashboard, dict):
        return []
    dashboard.pop("scr", None)
    try:
        now = now or datetime.now(timezone.utc)
        by_id = _by_id(data_dir)
        counts = {"rows": 0, "judged": 0, "worse": 0, "watch": 0, "big": 0, "failed": 0, "cached": 0, "users": 0,
                  "stale": 0}
        apps, entries, keep, abx, abt = {}, {}, set(), {}, {}
        bad = []                                    # (key, group, month, error type): store month files not readable
        sel = selected(dashboard)
        for key in store_keys(data_dir):
            meta = load_meta(data_dir, key)
            if not meta or gu.file_key(str(meta["app_id"])) != key:
                continue
            aid = str(meta["app_id"])
            if sel is not None and aid not in sel:
                continue                            # not selected: never built (no counter of the line fits it)
            mine, bk = set(), []
            ip = _idx_path(data_dir, key)
            idx = _idx_load(ip)
            idx0 = {k: dict(v) for k, v in idx.items()}
            try:
                res = build_app(meta, data_dir, out_dir, now, dashboard, by_id, counts, broken=bk, idx=idx)
                if res is None:
                    continue
                mine |= res["keep"]
                ln = "%sl_%s.json.gz" % (PREFIX, key)
                hl = _put(out_dir, ln, res["lraw"], idx)
                if hl is None:
                    counts["big"] += 1
                else:
                    mine.add(ln)
                fn = "%s%s.json.gz" % (PREFIX, key)
                h2 = _put(out_dir, fn, _raw(res["body2"]), idx)
                if h2 is None:
                    counts["big"] += 1
                    continue
                mine.add(fn)
                keep |= mine
                entries[aid] = res["entry"]
                abx[aid] = res["ab"]
                abt[aid] = res["abt"]
                apps[aid] = {"key": key, "v": h2[:12], "vl": hl[:12] if hl else None,
                             "from": res["entry"]["d0"], "ft": res["entry"]["ft"]}
            except Exception as e:                  # a broken app: its own files and pointer entry gone
                counts["failed"] += 1
                print("scr app skipped: %s" % type(e).__name__, file=sys.stderr)
            else:                                   # the index: this build's files (+ the shard months known too big)
                seen = res["seen"] if res else set()
                _idx_save(ip, {k: v for k, v in idx.items() if k in mine or v.get("big") and k in seen}, idx0)
            finally:                                # (an app that failed later still counts its unreadable files)
                bad += [(key,) + tuple(b) for b in bk]
        nbad = len({b[:3] for b in bad})
        if nbad:                                    # ONE health line per build (the red banner), the type only
            print("scr store skipped: %s" % bad[0][3], file=sys.stderr)
        if counts["stale"]:                         # ONE line too: an app's users are late or missing (its rows say
            print("scr users skipped: StaleUsersWarning", file=sys.stderr)      # "users not in yet")
        if counts.get("v4"):                        # … and v 4's numbers failing on an app (its type only)
            print("scr v4 skipped: %s" % counts["v4_err"], file=sys.stderr)
        bench = None
        if apps:                                    # the absolute words: every app's units make the benchmark
            try:
                B = ab_bench(abx)
                js = {aid: {ii: ab_judge(word, ab, B, sig) for ii, (word, ab) in rws.items()}
                      for aid, (_, rws, sig) in abx.items()}
                jt = {aid: {ii: ab_judge(word, ab, B, sig, trig=True) for ii, (word, ab) in rws.items()}
                      for aid, (rws, sig) in abt.items()}
                bench = ab_bench_ship(B)
            except Exception as e:                  # the words ship "" (the page: "—", benchmark nahi bana)
                js, jt = {}, {}
                print("scr bench skipped: %s" % type(e).__name__, file=sys.stderr)
            for aid, jj in js.items():
                for ii, j in jj.items():
                    entries[aid]["status"][ii][7:10] = j
                entries[aid]["lo"] = sum(1 for j in jj.values() if j[0] == "Low")
            for aid, jj in jt.items():                # the triggers: "lt" their Low count (the key says the file judges
                for ii, j in jj.items():            # them: an older file's triggers ship "" — the page shows their own word)
                    entries[aid]["status"][ii][7:10] = j
                entries[aid]["lt"] = sum(1 for j in jj.values() if j[0] == "Low")
        fv = None
        if apps:
            ia = _idx_path(data_dir)
            aidx = _idx_load(ia)
            aidx0 = {k: dict(v) for k, v in aidx.items()}
            ha = _put(out_dir, ALL_FILE, _raw({"v": V, "apps": entries, "bench": bench}), aidx)
            if ha is None:
                counts["big"] += 1
                apps = {}
            else:
                keep.add(ALL_FILE)
                fv = ha[:12]
            _idx_save(ia, {k: v for k, v in aidx.items() if k == ALL_FILE}, aidx0)
        _clean(out_dir, keep)
        line = "scr: apps %d, users %d, rows %d, judged %d, worse %d, watch %d, files %d, too big %d, failed %d, " \
               "broken %d, unmapped %d, cached %d" % (
                   len(apps), counts["users"], counts["rows"], counts["judged"], counts["worse"], counts["watch"],
                   len(keep), counts["big"], counts["failed"], nbad, unmapped_pairs(dashboard), counts["cached"])
        LINE = line
        if not apps:
            return []
        dashboard["scr"] = {"v": V, "file": ALL_FILE, "fv": fv, "apps": apps}
        return list(HEADER_PATHS)
    except Exception as e:
        dashboard.pop("scr", None)
        _clean(out_dir, set())
        LINE = None
        print("scr skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    global LINE
    LINE = None
    _clean(out_dir, set())


def pop_line():
    global LINE
    line, LINE = LINE, None
    return line


# ── the backtest (read-only; impressions per user per day, every final day) ───────────────────────

def _site_au(site, key):
    """{day: daily users} from a built site's file 2 ("au" from its d0), or {} (the --users fallback)."""
    raw = _read_gz_bytes(os.path.join(site, "%s%s.json.gz" % (PREFIX, key)))
    f2 = _json(raw) if raw is not None else None
    if not f2 or not isinstance(f2.get("au"), list) or not f2.get("d0"):
        return {}
    d0 = _d(f2["d0"])
    return {_iso(d0 + timedelta(days=k)): v for k, v in enumerate(f2["au"]) if v}


def backtest(data_dir, dashboard=None, now=None, out=None, users=None):
    """Every final day of each app's history with W + N inside it replayed as "today" (only data ≤ that day in any
    window): the rows' words after the holds and the confirm (statuses' rules, the confirm over the days in order) →
    per app: judged row-days, Worse / Watch / Better, the holds (small · app-wide · first day), flag episodes, row-months
    flagged, and the App row's words. The users: the Uninstall store in data_dir (or `users`: a built site's file 2
    "au"), the screen users from the store. Reads only; prints 12-hex keys and counts. → {key: {...}}."""
    out = out or sys.stdout
    now = now or datetime.now(timezone.utc)
    by_id = _by_id(data_dir)
    res = {}
    for key in store_keys(data_dir):
        meta = load_meta(data_dir, key)
        if not meta:
            continue
        recent = load_recent(data_dir, key)
        app = App(meta, core_days(data_dir, key, meta, recent), now, dashboard or {}, by_id)
        if not app.d0:
            continue
        au, auw = (_site_au(users, key), None) if users else app_users(meta, data_dir)
        set_users(app, au, auw, screen_users(app, data_dir, recent))
        ftu, d0 = _iso(app.ftu), _d(app.d0)
        anchors = [d for d in app.final if d <= ftu and _d(d) - timedelta(days=W_DAYS + N_DAYS - 1) >= d0]
        memo, last, c = {}, {}, {}
        rmj, rmf, eps, run = set(), set(), [], {}
        for a in anchors:
            rows, ast = _rows_at(app, a, memo)
            for rid, row, label, k, ii, ser, st in rows + [("app", None, "", "a", None, None, ast)]:
                prev = last.get(rid, [])[-(CONFIRM_DAYS - 1):] if CONFIRM_DAYS > 1 else []
                fin = _confirm(st, prev + [None] * (CONFIRM_DAYS - 1 - len(prev)))
                last.setdefault(rid, []).append(st["word"])
                w_ = fin["word"]
                tag = "app " if rid == "app" else ""
                c[tag + w_] = c.get(tag + w_, 0) + 1
                if fin.get("hold"):
                    c[tag + "hold " + fin["hold"]] = c.get(tag + "hold " + fin["hold"], 0) + 1
                if rid == "app":
                    continue
                if w_ in JUDGED:
                    rmj.add((rid, a[:7]))
                if w_ in FLAGS:
                    rmf.add((rid, a[:7]))
                    run[rid] = run.get(rid, 0) + 1
                elif run.get(rid):
                    eps.append(run.pop(rid))
        eps += [n_ for n_ in run.values() if n_]
        eps.sort()
        r = {"days": len(anchors), "judged": sum(c.get(w_, 0) for w_ in JUDGED),
             "worse": c.get("Worse", 0), "watch": c.get("Watch", 0), "better": c.get("Better", 0),
             "small": c.get("hold small", 0), "fold": c.get("hold fold", 0), "confirm": c.get("hold confirm", 0),
             "episodes": len(eps), "median": eps[len(eps) // 2] if eps else None, "row_months": [len(rmf), len(rmj)],
             "app": [c.get("app " + w_, 0) for w_ in ("Worse", "Watch", "Better", "Normal", "N/A")],
             "ftu": ftu, "users": bool(app.au and app.su)}
        res[key] = r
        print("%s  days %d  judged %d  worse %d  watch %d  better %d  held small %d fold %d first day %d  episodes %d "
              "(median %s)  row-months %d/%d  app worse %d watch %d better %d normal %d na %d" % (
                  key, r["days"], r["judged"], r["worse"], r["watch"], r["better"], r["small"], r["fold"], r["confirm"],
                  r["episodes"], r["median"], r["row_months"][0], r["row_months"][1], *r["app"]), file=out)
    return res


def main(argv):
    if not argv or argv[0] != "backtest" or len(argv) < 2:
        print("usage: python -m admob_iq.screens_build backtest <data_dir> [--dashboard <dashboard.json.gz>] "
              "[--users <site dir>]", file=sys.stderr)
        return 2
    dash = None
    if "--dashboard" in argv:
        p = argv[argv.index("--dashboard") + 1]
        raw = _read_gz_bytes(p) if p.endswith(".gz") else open(p, "rb").read()
        dash = _json(raw) if raw else None
    users = argv[argv.index("--users") + 1] if "--users" in argv else None
    backtest(argv[1], dash, users=users)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
