"""One-off GA4 ACTIVITY probe (v2), run by .github/workflows/ga4-activity-probe.yml: before an Activity tab is built
(owner, 4 Nov 2026: per app and Activity, its visits, the ad impressions shown against them and the ratio), measure what
GA4 really gives per screen class (unifiedScreenClass): visits (screen_view), users, sessions and engagement time; the ad
impressions logged there, counted as ad_impression EVENTS (eventCount: the publisher impressions metric folds into
"(other)" at high cardinality while the event counts came back whole), by ad format and ad unit; its ad clicks and
rewards; where the full-screen formats land (the ad SDK's own Activity such as AdActivity, or the screen that showed
them); and whether each split is WHOLE — tied to its truth (the same read without the split) and key by key to the read
one dimension up, unsampled, uncut, untruncated and without fold rows — over the 28 final days, day by day, for the 5
newest days (Today / Yesterday: bracketed by the truth read just before and just after) and over the whole history.
Offline, GA4's impressions / revenue / clicks against AdMob's own (the clone's mediation ad-unit report, every source).

READ-ONLY with the existing analytics.readonly access (nothing to set up, nothing registered): Data API runReport /
getMetadata / checkCompatibility, the Admin API's dataRetentionSettings, the PRIVATE repo's clone. The only write is
ga4/activity_probe.json in the PRIVATE repo.

WINDOWS per app, in its property's zone: F = today − 5 (E − LATE, E = today − 2: the newest final day); W = the 28 days
to F (never before the app's history start), W7 = its last 7; R = F + 1 … today (not final yet); H = the history start
… F (no cap; F − 729 without a start); d* = AUD's worst day; Bv / Ba = 7-day blocks before W picked from VDH / AUDH.

READS: the READS table below — id, tier, span, dimensions, metrics, eventName filter, and for a conditional read when it
runs (a read that is not needed is recorded {"skip": reason} and never counted as a read). SCA is the ad reads' screen
dimension: the screen class, or the page path once GA4 refused the class with the ad format / unit and accepted the page
path (on app streams both hold the class); views reads always use the class. Each record: accepted or its HTTP class,
rows, pages, the fold ("(other)" / "other") and "(not set)" shares, GA4's flags (thresholding, sampling and its space,
truncation, restricted metrics), the tie to its truth (within 2 % or 1 event / $0.001), the keys tie, the bracket (R
reads), a per-day map (daily reads) and a state: whole | lossy | sampled | unknown (a truth it needs was not whole).
"facts", "admob", "verdict" per app and the portfolio "summary": private, in the report only.

PUBLIC LOG: a counts-only heartbeat and ONE counts-only result line — no names, ids, dates, amounts or error text;
stderr is hidden by the workflow.
"""

import os
import re
import sys
import threading
import time
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from admob_iq import ga4_probe
from admob_iq import tz_check
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience_probe as ap
from admob_iq.fetch import ga4_country_probe as cp
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_device_probe as dp
from admob_iq.fetch import ga4_shape_probe as sp
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch.ga4_d1d7_probe import Stop

LATE = gu.IDAY_LATE                 # F = E − 3 = today − 5: the newest final day
DAYS = 28                           # W
W7_DAYS = 7                         # W7: the country reads
HIST_DAYS = 730                     # H without a history start: this many days to F (with one: no cap)
BLOCK_DAYS = 7                      # OV / OA blocks
TIE_REL = 0.02                      # within: |got − want| ≤ max(2 % of want, FLOOR) …
FLOOR_N = 1                         # … 1 event / view / second …
FLOOR_USD = 0.001                   # … or $0.001
TIE_OK = 0.98                       # a keys tie holds when the truth's keys that are within hold ≥ 98 % of it
DATA_MAX = 3000                     # a KEEP read keeps its rows ("data") when it has at most this many
TABLE_MAX = 80                      # Activity rows by views (+ every ad / ad-like class and ≥ 1 % of impressions)
UNITS_MAX = 60
TOP_N = 20
EVENTS_MAX = 100
XC_MAX = 20                         # the apps' own ad-like events read by screen at most
OFF_DAYS_MAX = 50
MONTHS_MAX = 60
UNIT_DAYS = 60                      # AdMob per-unit days kept (W ends 5 days back and spans 28)
MAX_CALLS = 2000
APP_CALLS = 75                      # 37 planned + ≤ 15 conditional an app: the rest is room for pages
WORKERS = 4
BUDGET_SEC = 20 * 60                # no new call after 20 min (the job's timeout is 45)
TICK_SEC = 20
PAGE_ROWS = 100000
SIZE_MAX = 20 * 1024 * 1024         # report text; over it the biggest "data" go first, then VDH / AUDH day maps
DATA_DIR = "_private"
OUT_PATH = "ga4/activity_probe.json"

SC, PS, SN = "unifiedScreenClass", "unifiedPagePathScreen", "unifiedScreenName"
FMT, UNIT, SRC = "adFormat", "adUnitName", "adSourceName"
NVR, VER, CTY, EVN = "newVsReturning", "appVersion", "countryId", "eventName"
SCA = "@SCA"                        # the ad reads' screen dimension, resolved per app: SC, or PS
PREV = "@PREV"                      # META's API name of a registered firebase_previous_class
PREV_KEY = "prev"
IMP = "ad_impression"
EVM = ("eventCount", "totalAdRevenue")
VIEW = ("screenPageViews", "activeUsers", "userEngagementDuration")
VDM = ("screenPageViews", "userEngagementDuration")
PUB = ("publisherAdImpressions", "totalAdRevenue")
X_EVENTS = ("ad_click", "ad_reward")
HEV = ("screen_view", IMP)
NON_ADD = frozenset(("activeUsers", "sessions"))    # not additive over screens / days: never tied
USD_METS = frozenset(("totalAdRevenue",))
FOLD = frozenset(("(other)", "other"))              # GA4's fold labels (case-insensitive)
UNSET = frozenset(("", "(not set)", "(none)"))
FULL = frozenset(("interstitial", "rewarded", "rewardedinterstitial", "appopen"))
# ad formats, GA4's and AdMob's spellings (letters only, lower case) → one name, first prefix that matches; a fold label
# → "fold"; anything else is kept as it is and listed (facts.fmt raw / admob raw)
FMT_ALIASES = (("rewardedinter", "rewardedinterstitial"), ("rewarded", "rewarded"), ("appopen", "appopen"),
               ("interstitial", "interstitial"), ("banner", "banner"), ("native", "native"))
# the ad SDKs' own full-screen Activities (generic SDK names, never an app's), ANCHORED on the simple name: the First open
# fetch's looser pattern also matches ordinary app screens (a download / read / thread screen), so it is not reused
AD_SCREEN = re.compile(r"(?:^|\.)(?:AdActivity|AdUnitActivity|AudienceNetworkActivity|AppLovin\w*Activity|"
                       r"InMobiAdActivity|VungleActivity|CBImpressionActivity|MBRewardVideoActivity|MBCommonActivity|"
                       r"TTFullScreen\w*Activity|TTReward\w*Activity|TTAppOpenAd\w*Activity|FullScreenWebViewDisplay|"
                       r"\w*InterstitialActivity)$", re.I)
# an app's own ad-like event (a review list, never an ad count): snake_case tokens or camelCase pieces of ad words
AD_EVENT_RE = re.compile(r"(?:^|_)(?:ads?|inter|interstitial|rewarded|reward|banner|native|app_?open|aoa|full_?screen)"
                         r"(?:_|$)|interstitial|rewarded|appopen|nativead|bannerad|interad|rewardad", re.I)
STD_AD_EVENTS = frozenset(("ad_impression", "ad_click", "ad_reward", "ad_exposure", "ad_query", "ad_activeview"))
OBF_RE = re.compile(r"(?:^|\.)[A-Za-z]{1,2}$")     # an obfuscated class: a 1–2 letter simple name (a.b.c too)
PLACE_RE = re.compile(r"placement|screen|slot|position|location|page|where|ad_?unit|ad_?format|ad_?source|ad_?place",
                      re.I)
META_DIMS = (SC, PS, SN, FMT, UNIT, SRC, NVR, VER, CTY)
META_METS = ("screenPageViews", "userEngagementDuration", "sessions", "activeUsers", "eventCount",
             "publisherAdImpressions", "publisherAdClicks", "totalAdRevenue", "adUnitExposure")
SCREEN_PARAMS = ("firebase_previous_class", "firebase_previous_screen", "firebase_screen_class", "firebase_screen",
                 "ad_unit_name", "ad_format", "ad_source")
CC_FIELDS = (FMT, UNIT, SRC, PS, CTY, NVR, VER, "date", "totalAdRevenue", "publisherAdImpressions", "publisherAdClicks",
             "adUnitExposure", "activeUsers", "sessions")
TRUNC_PROPERTY = "DATA_TRUNCATION_TYPE_PROPERTY"
SKIPS = ("whole", "young", "not_registered", "no_shape", "no_events", "no_base", "same")

Read = namedtuple("Read", "id prio span dims mets filt when")
# EXECUTION ORDER: every truth before the reads tied to it; a conditional read right after the read that decides it; the
# heavy reads late in their tier, so a stop drops the tail first. filt: None | one eventName | a tuple (inList) | "XC".
READS = (
    # P1 — can the tab be built
    Read("META", "P1", "-", (), (), None, None),
    Read("T", "P1", "W", (), EVM, IMP, None),
    Read("T2", "P1", "W", (), ("publisherAdImpressions", "publisherAdClicks", "totalAdRevenue"), None, None),
    Read("V0", "P1", "W", (), VIEW + ("sessions",), None, None),
    Read("EV", "P1", "W", (EVN,), EVM, None, None),
    Read("V", "P1", "W", (SC,), VIEW, None, None),
    Read("A", "P1", "W", (SC,), EVM, IMP, None),
    Read("F", "P1", "W", (FMT,), EVM, IMP, None),
    Read("AF", "P1", "W", (SCA, FMT), EVM, IMP, None),
    Read("AFP", "P1", "W", (PS, FMT), EVM, IMP, "AF refused"),
    Read("U", "P1", "W", (FMT, UNIT), EVM, IMP, None),
    Read("AU", "P1", "W", (SCA, FMT, UNIT), EVM, IMP, None),
    Read("AUP", "P1", "W", (PS, FMT, UNIT), EVM, IMP, "AU refused or not whole"),
    Read("CC", "P1", "-", (SC,), ("eventCount",), IMP, "AF or AU refused (checkCompatibility, once)"),
    Read("X", "P1", "W", (SCA, FMT, EVN), ("eventCount",), X_EVENTS, None),
    Read("VN", "P1", "W", (SC, SN), ("screenPageViews",), None, None),
    Read("XC", "P1", "W", (SC, EVN), ("eventCount",), "XC", "EV has custom ad-like events"),
    Read("PV", "P1", "W", (SC, PREV), ("screenPageViews",), "screen_view", "firebase_previous_class registered"),
    # P2 — the daily store, Today / Yesterday, the whole history
    Read("VD0", "P2", "W", ("date",), VDM, None, None),
    Read("VD", "P2", "W", ("date", SC), VDM, None, None),
    Read("FD", "P2", "W", ("date", FMT), EVM, IMP, None),
    Read("AUD", "P2", "W", ("date", SCA, FMT, UNIT), EVM, IMP, None),
    Read("AUD1", "P2", "D*", ("date", SCA, FMT, UNIT), EVM, IMP, "AUD lossy or sampled"),
    Read("AUDS", "P2", "W", ("date", SCA, FMT), EVM, IMP, "AUD lossy"),
    Read("RV0", "P2", "R", ("date",), VDM, None, None),
    Read("RV", "P2", "R", ("date", SC), VDM, None, None),
    Read("RV0b", "P2", "R", ("date",), VDM, None, None),
    Read("RF", "P2", "R", ("date", FMT), EVM, IMP, None),
    Read("RAU", "P2", "R", ("date", SCA, FMT, UNIT), EVM, IMP, None),
    Read("RFb", "P2", "R", ("date", FMT), EVM, IMP, None),
    Read("HD0", "P2", "H", ("date", EVN), EVM, HEV, None),
    Read("VDH", "P2", "H", ("date", SC), VDM, None, None),
    Read("OV", "P2", "Bv", ("date", SC), ("screenPageViews",), None, "VDH not whole before W"),
    Read("AUDH", "P2", "H", ("date", SCA, FMT, UNIT), EVM, IMP, None),
    Read("OA", "P2", "Ba", ("date", SCA, FMT, UNIT), EVM, IMP, "AUDH not whole before W"),
    Read("OAS", "P2", "Ba", ("date", SCA, FMT), EVM, IMP, "OA not whole"),
    Read("OAP0", "P2", "Ba", ("date",), PUB, None, "OA not whole"),
    Read("OAP", "P2", "Ba", ("date", PS, FMT, UNIT), PUB, None, "OA not whole"),
    # P3 — the advanced layers
    Read("VS", "P3", "W", (SC,), ("sessions",), None, None),
    Read("AR", "P3", "W", (SCA, FMT), ("activeUsers",), IMP, None),
    Read("XE0", "P3", "W", (), ("adUnitExposure",), None, None),
    Read("XE", "P3", "W", (SC,), ("adUnitExposure",), None, None),
    Read("XEP", "P3", "W", (PS,), ("adUnitExposure",), None, "XE refused"),
    Read("S", "P3", "W", (FMT, SRC), EVM, IMP, None),
    Read("NVD", "P3", "W", ("date", NVR, SC), ("screenPageViews",), None, None),
    Read("NAD", "P3", "W", ("date", NVR, SCA, FMT), EVM, IMP, None),
    Read("AVD", "P3", "W", ("date", VER, SC), ("screenPageViews",), None, None),
    Read("AAD", "P3", "W", ("date", VER, SCA, FMT), EVM, IMP, None),
    Read("CVD", "P3", "W7", ("date", SC, CTY), ("screenPageViews",), None, None),
    Read("CV", "P3", "W", (SC, CTY), ("screenPageViews",), None, "CVD not whole"),
    Read("CAD", "P3", "W7", ("date", SCA, FMT, CTY), EVM, IMP, None),
    Read("CA", "P3", "W", (SCA, FMT, CTY), EVM, IMP, "CAD not whole"),
)
SPEC = {r.id: r for r in READS}
# the total tie: Σ split ÷ Σ truth over the same span (metrics both have, minus NON_ADD)
TIE = {"V": "V0", "A": "T", "F": "T", "AF": "T", "AFP": "T", "U": "T", "AU": "T", "AUP": "T", "VN": "V0", "PV": "V0",
       "VD0": "V0", "VD": "V0", "FD": "T", "AUD": "T", "AUDS": "T", "XE": "XE0", "XEP": "XE0", "S": "T", "NVD": "V0",
       "NAD": "T", "AVD": "V0", "AAD": "T", "CV": "V0", "CA": "T"}
KEEP = frozenset(("T", "T2", "V0", "EV", "V", "A", "F", "AF", "AFP", "U", "AU", "AUP", "X", "XC", "VN", "PV", "VS", "AR",
                  "XE0", "XE", "XEP", "S", "VD0", "FD", "RV0", "RV", "RV0b", "RF", "RFb", "HD0", "CV"))
DAY = frozenset(("VD", "AUD", "AUD1", "AUDS", "RV", "RAU", "VDH", "AUDH", "OV", "OA", "OAS", "OAP", "NVD", "NAD", "AVD",
                 "AAD", "CVD", "CAD"))
LONG = frozenset(("VDH", "AUDH", "OV", "OA", "OAS", "OAP", "NVD", "NAD", "AVD", "AAD", "CVD", "CAD"))  # kept as sums
KEY_SLOTS = ("keys", "keys_w", "keys_sv", "keys_ad")
RESULT_LINE = ("activity probe: apps %d, complete %d, zone missing %d, reads %d, ok %d, refused %d, off %d, other %d, "
               "sampled %d, truncated %d, skipped %d, calls %d, %ds, saved %s")
COUNT_KEYS = ("reads", "ok", "refused", "off", "other", "sampled", "trunc", "skipped")


class Run(dp.Run):
    """The run's clock, budget, call caps and its counts-only heartbeat (apps done / all, calls, seconds)."""

    def __init__(self, budget=BUDGET_SEC, clock=time.monotonic, max_calls=MAX_CALLS, total=0):
        super().__init__(budget, clock, max_calls)
        self.total, self.done = total, 0

    def pulse(self, count=False):
        with self.lock:
            if count:
                self.calls += 1
            now = self.clock()
            beat = now - self.beat >= pr.HEARTBEAT_SEC
            if beat:
                self.beat = now
            line = "activity progress: apps %d/%d, calls %d, %ds" % (self.done, self.total, self.calls,
                                                                     int(now - self.t0))
        if beat:
            self.say(line)


# ── names and small helpers ───────────────────────────────────────────────────────────────────

def _fmt(v):
    """An ad format, GA4's or AdMob's spelling → one name ("App open" / "APP_OPEN" → "appopen", "Native advanced" /
    "NATIVE" → "native", "(not set)" → "notset", a fold label → "fold"); an unknown spelling is kept (letters only)."""
    raw = str(v or "")
    if raw.strip().lower() in FOLD:
        return "fold"
    s = re.sub(r"[^a-z]", "", raw.lower())
    for pre, name in FMT_ALIASES:
        if s.startswith(pre):
            return name
    return s or "notset"


def is_ad_screen(c):
    return bool(AD_SCREEN.search(str(c or "")))


def is_obf(c):
    return bool(OBF_RE.search(str(c or "")))


def _isfold(v):
    return str(v or "").strip().lower() in FOLD


def _named(v):
    return str(v or "") not in UNSET and not _isfold(v)


def _cls(r):
    return str(r.get(SC) or "")


def _num(v):
    return dp._num(v)


def _n(v):
    """A sum for the report: an int when whole, else 4 decimals."""
    v = float(v or 0)
    return int(v) if v.is_integer() else round(v, 4)


def _is_ymd(s):
    return isinstance(s, str) and len(s) == 8 and s.isdigit()


def _ymd_date(s):
    return datetime.strptime(s, "%Y%m%d").date()


def _iso(d):
    return d.isoformat() if d else None


def _day(s):
    try:
        return gu._d(s) if s else None
    except (TypeError, ValueError):
        return None


def within(got, want, m):
    """|got − want| ≤ max(2 % of want, 1 event / view / second, or $0.001 for revenue)."""
    return abs(got - want) <= max(TIE_REL * abs(want), FLOOR_USD if m in USD_METS else FLOOR_N)


def _fold_row(r, dims):
    return any(_isfold(r.get(d)) for d in dims)


def _unset_row(r, dims):
    return any(str(r.get(d) or "") in UNSET for d in dims)


def _sum_by(rows, keys, m):
    out = {}
    for r in rows or []:
        k = "|".join(str(r.get(x) or "") for x in keys)
        out[k] = out.get(k, 0.0) + _num(r.get(m))
    return out


def _by(rows, key, m):
    return _sum_by(rows, (key,), m)


def _ok(rec):
    return bool(rec and rec.get("ok"))


def _refused(rec):
    """HTTP 4xx but 429: GA4 refused the request (asking again would not change it)."""
    return bool(rec and "skip" not in rec and not rec.get("ok") and cp._final(rec.get("err")))


def _state(rec):
    if not rec:
        return "absent"
    if "skip" in rec:
        return "skip"
    if not rec.get("ok"):
        return "refused" if _refused(rec) else "error"
    return rec.get("state") or "unknown"


def _natural(v):
    return tuple((0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.findall(r"\d+|\D+", str(v)))


def fmt_guess(name):
    """An app's own ad-like event name → the ad format it most likely counts (None when nothing says)."""
    s = re.sub(r"[^a-z]", "", str(name or "").lower())
    if "rewardedinter" in s:
        return "rewardedinterstitial"
    if "reward" in s:
        return "rewarded"
    if "appopen" in s or re.search(r"(?:^|_)aoa(?:_|$)", str(name or "").lower()):
        return "appopen"
    if "inter" in s:
        return "interstitial"
    if "banner" in s:
        return "banner"
    if "native" in s:
        return "native"
    return None


def custom_ad_events(ev_rows):
    """EV rows → [(name, count)] of the app's own ad-like events, most first (the standard ad events excluded)."""
    by = _by(ev_rows, EVN, "eventCount")
    out = [(k, v) for k, v in by.items() if k not in STD_AD_EVENTS and AD_EVENT_RE.search(k) and v > 0]
    return sorted(out, key=lambda kv: (-kv[1], kv[0]))


# ── the plan, the spans, the requests ─────────────────────────────────────────────────────────

def plan_of(u, now):
    """One app's days in its property's zone: today, F = today − 5, W = [a, F] (DAYS, never before the history start),
    W7 = [a7, F], R = [F + 1, today], H = [h0, F] (h0 = the history start, else F − HIST_DAYS + 1); None when W is
    empty."""
    tz = u.get("tz") or "UTC"
    today = ga4.window_end_in(tz, now, lag=0)
    f = ga4.window_end_in(tz, now) - timedelta(days=LATE)
    hs = _day(u.get("history_start"))
    a, a7 = f - timedelta(days=DAYS - 1), f - timedelta(days=W7_DAYS - 1)
    if hs:
        a, a7 = max(a, hs), max(a7, hs)
    if a > f:
        return None
    return {"today": today, "F": f, "a": a, "a7": a7, "r0": f + timedelta(days=1),
            "h0": hs or f - timedelta(days=HIST_DAYS - 1), "days": (f - a).days + 1}


def win_of(p):
    return {"today": _iso(p["today"]), "F": _iso(p["F"]), "W": [_iso(p["a"]), _iso(p["F"])],
            "W7": [_iso(p["a7"]), _iso(p["F"])], "R": [_iso(p["r0"]), _iso(p["today"])],
            "H": [_iso(p["h0"]), _iso(p["F"])], "days": p["days"]}


def span(kind, c):
    s, p = SPEC[kind].span, c.p
    if s == "W":
        return p["a"], p["F"]
    if s == "W7":
        return p["a7"], p["F"]
    if s == "R":
        return p["r0"], p["today"]
    if s == "H":
        return p["h0"], p["F"]
    if s == "D*":
        return c.dstar, c.dstar
    if s == "Bv":
        return tuple(c.bv)
    if s == "Ba":
        return tuple(c.ba)
    raise KeyError(kind)


def request(kind, c):
    """kind → (Data API body, eventName, eventName list, the dimensions asked): ga4.Ga4App adds the Android + stream
    filter (and the eventName one), report_all the paging, returnPropertyQuota and one total order."""
    r = SPEC[kind]
    a, b = span(kind, c)
    dims = tuple(c.sca if d == SCA else c.prev if d == PREV else d for d in r.dims)
    event = events = None
    if r.filt == "XC":
        events = list(c.xc_events)
    elif isinstance(r.filt, tuple):
        events = list(r.filt)
    elif r.filt:
        event = r.filt
    return dp._body(a, b, dims, r.mets), event, events, dims


def _ndims(kind):
    """A read's dimensions as its rows hold them once normalised (the page path / SCA → the class key)."""
    return tuple(SC if d in (SCA, PS) else PREV_KEY if d == PREV else d for d in SPEC[kind].dims)


def _norm(rows, prev):
    """The page path is stored under the class key (on app streams it holds the class), the registered previous-class
    dimension under "prev"."""
    for r in rows:
        if PS in r:
            r[SC] = r.pop(PS)
        if prev and prev in r:
            r[PREV_KEY] = r.pop(prev)
    return rows


# ── the per-app context ───────────────────────────────────────────────────────────────────────

class Ctx:
    """One app's reads in flight: records, rows (or their sums), the checks, the screen dimension of the ad reads."""

    def __init__(self, ga, run, u, p, res):
        self.ga, self.run, self.u, self.p, self.res = ga, run, u, p, res
        self.recs, self.got, self.chk = res["reads"], {}, {}
        self.sca, self.no_fmt, self.no_unit = SC, False, False
        self.prev, self.xc_events = None, []
        self.dstar = self.dstar_loss = self.bv = self.ba = None
        self.block_skip = {}

    def ok(self, k):
        return _ok(self.recs.get(k))

    def st(self, k):
        return _state(self.recs.get(k))

    def rows(self, k):
        v = self.got.get(k)
        return v if isinstance(v, list) else None

    def role(self, k):
        """The read holding the screen × format (AF) / screen × format × unit (AU) answer: the page-path twin when the
        class read was refused and the twin accepted."""
        twin = {"AF": "AFP", "AU": "AUP"}[k]
        return twin if _refused(self.recs.get(k)) and self.ok(twin) else k


# ── the record of one read ────────────────────────────────────────────────────────────────────

def shares(rows, dims, mets):
    """Σ per metric and the share of it in fold rows / in "(not set)" rows."""
    out = {}
    for m in mets:
        t = dp._tot(rows, m)
        fo = sum(_num(r.get(m)) for r in rows if _fold_row(r, dims))
        un = sum(_num(r.get(m)) for r in rows if not _fold_row(r, dims) and _unset_row(r, dims))
        out[m] = {"sum": round(t, 4), "fold": pr._ratio(fo, t), "unset": pr._ratio(un, t)}
    return out


def p_rows(dims, mets, keep):
    def parse(rows):
        rec = {"rows": len(rows), "s": shares(rows, dims, mets),
               "fold_rows": sum(1 for r in rows if _fold_row(r, dims))}
        if keep and len(rows) <= DATA_MAX:
            rec["data"] = [[str(r.get(d) or "") for d in dims] + [round(_num(r.get(m)), 6) for m in mets]
                           for r in rows]
        return rec, rows
    return parse


def page_meta(ga, rows):
    """GA4's per-page response metadata of the last report_all → pages, cut (rows < rowCount), smp (samplesReadCount /
    samplingSpaceSize: the largest a page reported — each page is the same query), trunc [[type, date, ranges]],
    restricted metrics, empty (emptyReason set) and the UTC time at the read's end."""
    out = {"pages": ga.last_pages, "cut": bool(ga.truncated(rows)),
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rd = sz = None
    trunc, restricted, empty = [], set(), False
    for m in ga.last_metas or []:
        m = m or {}
        for s in m.get("samplingMetadatas") or []:
            rd = max(rd or 0, pr._int((s or {}).get("samplesReadCount")))
            sz = max(sz or 0, pr._int((s or {}).get("samplingSpaceSize")))
        for t in m.get("dataTruncationReasons") or []:
            t = t or {}
            e = [t.get("dataTruncationType"), t.get("dataTruncationDate"),
                 [[x.get("startDate"), x.get("endDate")] for x in t.get("dataTruncationDateRanges") or []
                  if isinstance(x, dict)]]
            if e not in trunc:
                trunc.append(e)
        for x in (m.get("schemaRestrictionResponse") or {}).get("activeMetricRestrictions") or []:
            if isinstance(x, dict) and x.get("metricName"):
                restricted.add(str(x["metricName"]))
        empty |= bool(m.get("emptyReason"))
    if sz is not None:
        out["smp"] = {"read": rd, "space": sz}
    if trunc:
        out["trunc"] = trunc
    if restricted:
        out["restricted"] = sorted(restricted)
    if empty:
        out["empty"] = True
    return out


def keys_tie(got, want, keys, mets):
    """Per key (the `keys` values joined) of a split vs its truth, per metric: the overall ratio, the spread, off2 (truth
    keys not within, with the floors) and w2 (the truth's share held by keys that are within)."""
    out = {}
    for m in mets:
        g, w = _sum_by(got, keys, m), _sum_by(want, keys, m)
        rs = [g.get(k, 0.0) / v for k, v in w.items() if v]
        bad = {k for k, v in w.items() if not within(g.get(k, 0.0), v, m)}
        tot = sum(v for v in w.values() if v > 0)
        out[m] = {"all": dp.tie(sum(g.values()), sum(w.values())), "keys": len(w), "p10": sp._pct(rs, 0.1),
                  "p90": sp._pct(rs, 0.9), "off2": len(bad),
                  "w2": pr._ratio(sum(v for k, v in w.items() if v > 0 and k not in bad), tot)}
    return out


def _main(mets):
    for m in ("screenPageViews", "eventCount", "publisherAdImpressions"):
        if m in mets:
            return m
    return mets[0]


def day_map(rows, truth, dims, main, rev):
    """{date: [Σ main, truth main, fold share, "(not set)" share, within main, within revenue]} — a folded date (GA4's
    fold row carries a fold label in every dimension) is its own key."""
    oth = [d for d in dims if d != "date"]
    by = {}
    for r in rows:
        e = by.setdefault(str(r.get("date") or ""), [0.0, 0.0, 0.0, 0.0])
        v = _num(r.get(main))
        e[0] += v
        if _fold_row(r, oth):
            e[1] += v
        elif _unset_row(r, oth):
            e[2] += v
        if rev:
            e[3] += _num(r.get(rev))
    tm = _by(truth, "date", main) if truth is not None else {}
    tr = _by(truth, "date", rev) if truth is not None and rev else {}
    out = {}
    for d in sorted(set(by) | set(tm)):
        e = by.get(d) or [0.0] * 4
        t = tm.get(d, 0.0 if truth is not None and _is_ymd(d) else None)
        out[d] = [_n(e[0]), None if t is None else _n(t), pr._ratio(e[1], e[0]) or 0.0, pr._ratio(e[2], e[0]) or 0.0,
                  None if t is None else within(e[0], t, main),
                  None if not rev or t is None else within(e[3], tr.get(d, 0.0), rev)]
    return out


def hd0_rows(c, ev):
    """HD0 restricted to one event, with the metric names of the reads tied to it."""
    hd = c.rows("HD0")
    if hd is None:
        return None
    out = []
    for r in hd:
        if r.get(EVN) != ev:
            continue
        n = _num(r.get("eventCount"))
        if ev == "screen_view":
            out.append({"date": r.get("date"), "screenPageViews": n})
        else:
            out.append({"date": r.get("date"), "eventCount": n, "totalAdRevenue": _num(r.get("totalAdRevenue")),
                        "publisherAdImpressions": n})
    return out


def checks(kind, c):
    """The ties of one read: [{tid, truth rows (None: the truth is not there), keys (() = the total tie), metrics the
    truth has, primary (decides the state), slot, span (restricts both sides), sel (restricts the split)}]."""
    out = []

    def add(tid, truth, keys=(), mets=None, primary=True, slot="keys", sp_=None, sel=None):
        out.append({"tid": tid, "truth": truth, "keys": tuple(keys), "mets": SPEC[tid].mets if mets is None else mets,
                    "primary": primary, "slot": slot, "span": sp_, "sel": sel})

    if kind in TIE:
        add(TIE[kind], c.rows(TIE[kind]))
    w = (pr._ymd(c.p["a"]), pr._ymd(c.p["F"]))
    if kind in ("AF", "AFP", "U", "S"):
        add("F", c.rows("F"), (FMT,))
    elif kind in ("AU", "AUP"):
        add("U", c.rows("U"), (FMT, UNIT))
    elif kind in ("X", "XC"):
        names, ev = set(X_EVENTS if kind == "X" else c.xc_events), c.rows("EV")
        add("EV", None if ev is None else [r for r in ev if r.get(EVN) in names], (EVN,), mets=("eventCount",))
    elif kind in ("VN", "PV", "CV"):
        add("V", c.rows("V"), (SC,))
    elif kind == "VD":
        add("VD0", c.rows("VD0"), ("date",))
    elif kind in ("AUD", "AUDS"):
        add("FD", c.rows("FD"), ("date", FMT))
    elif kind == "AUD1":
        add("FD", c.rows("FD"))
        add("FD", c.rows("FD"), ("date", FMT))
    elif kind == "HD0":
        vd0 = c.rows("VD0")
        add("VD0", None if vd0 is None else [{"date": r.get("date"), "eventCount": r.get("screenPageViews")}
                                             for r in vd0],
            ("date",), mets=("eventCount",), slot="keys_sv", sp_=w, sel=lambda r: r.get(EVN) == "screen_view")
        add("FD", c.rows("FD"), ("date",), mets=EVM, slot="keys_ad", sp_=w, sel=lambda r: r.get(EVN) == IMP)
    elif kind in ("VDH", "OV"):
        add("HD0", hd0_rows(c, "screen_view"), ("date",), mets=("screenPageViews",))
        if kind == "VDH":
            add("VD", c.rows("VD"), ("date", SC), primary=False, slot="keys_w", sp_=w)
    elif kind in ("AUDH", "OA", "OAS"):
        add("HD0", hd0_rows(c, IMP), ("date",), mets=EVM)
        if kind == "AUDH":
            add("AUD", c.rows("AUD"), ("date", SC, FMT, UNIT), primary=False, slot="keys_w", sp_=w)
    elif kind == "OAP0":
        add("HD0", hd0_rows(c, IMP), ("date",), mets=PUB, primary=False, slot="vs")
    elif kind == "OAP":
        add("OAP0", c.rows("OAP0"), ("date",))
    elif kind in ("NVD", "AVD", "CVD"):
        add("VD", c.rows("VD"), ("date", SC))
    elif kind in ("NAD", "AAD", "CAD"):
        if c.st("AUD") == "whole":                   # AUD summed to date|class|format; FD's date|format when it is not
            add("AUD", c.rows("AUD"), ("date", SC, FMT))
        else:
            add("FD", c.rows("FD"), ("date", FMT))
    elif kind == "CA":
        k = c.role("AF")
        add(k, c.rows(k), (SC, FMT))
    return out


def apply_checks(c, kind, rec, rows):
    lo, hi = (pr._ymd(x) for x in span(kind, c))
    mine, truths, day_truth = SPEC[kind].mets, {}, None
    for ck in checks(kind, c):
        st = c.st(ck["tid"])
        truths[ck["tid"]] = st
        tr = ck["truth"]
        if tr is None:
            if ck["primary"]:
                c.chk[kind].append((False, True))
            continue
        a, b = ck["span"] or (lo, hi)
        sr = [r for r in rows if (ck["sel"] is None or ck["sel"](r))
              and (ck["span"] is None or a <= str(r.get("date") or "") <= b)]
        tr = [r for r in tr if "date" not in r or a <= str(r.get("date") or "") <= b]
        mets = [m for m in mine if m in ck["mets"] and m not in NON_ADD]
        if not ck["keys"]:
            g, t = {m: dp._tot(sr, m) for m in mets}, {m: dp._tot(tr, m) for m in mets}
            rec["tie"] = {m: dp.tie(g[m], t[m]) for m in mets}
            rec["tie_in"] = {m: within(g[m], t[m], m) for m in mets}
            passed = all(rec["tie_in"].values())
        else:
            stats = keys_tie(sr, tr, ck["keys"], mets)
            rec[ck["slot"]] = stats
            passed = all(v["w2"] is None or v["w2"] >= TIE_OK for v in stats.values())
            if day_truth is None and ck["primary"] and "date" in ck["keys"]:
                day_truth = tr
        if ck["primary"]:
            c.chk[kind].append((st == "whole", passed))
    rec["truths"] = truths
    if kind in DAY:
        rec["day"] = day_map(rows, day_truth, _ndims(kind), _main(mine),
                             "totalAdRevenue" if "totalAdRevenue" in mine else None)


def ev_ties(c, rec, rows):
    """EV's ad_impression row vs T (count, revenue) and its screen_view row vs V0's views."""
    tie, tin = {}, {}
    for tid, ev, pairs in (("T", IMP, (("eventCount", "eventCount"), ("totalAdRevenue", "totalAdRevenue"))),
                           ("V0", "screen_view", (("eventCount", "screenPageViews"),))):
        t = c.rows(tid)
        if t is None:
            c.chk["EV"].append((False, True))
            continue
        oks = []
        for me, mt in pairs:
            g, w = sum(_num(r.get(me)) for r in rows if r.get(EVN) == ev), dp._tot(t, mt)
            k = "%s.%s" % (ev, mt)
            tie[k], tin[k] = dp.tie(g, w), within(g, w, mt)
            oks.append(tin[k])
        c.chk["EV"].append((c.st(tid) == "whole", all(oks)))
    rec["tie"], rec["tie_in"], rec["truths"] = tie, tin, {"T": c.st("T"), "V0": c.st("V0")}


def _off(rec):
    """A tie, a key or a bracket outside, or a keys tie under TIE_OK."""
    if any(v is False for v in (rec.get("tie_in") or {}).values()):
        return True
    for slot in KEY_SLOTS:
        for v in (rec.get(slot) or {}).values():
            if v.get("off2") or (v.get("w2") is not None and v["w2"] < TIE_OK):
                return True
    return any(v.get("off") for v in (rec.get("bracket") or {}).values())


def judge(c, kind, rec):
    """whole = no fold row of its own, not cut, not truncated, every primary tie within and keys tie ≥ TIE_OK (against
    truths that are whole), not sampled; lossy = a fold row, a cut, a truncation or a tie / keys / bracket outside;
    sampled; unknown = a truth it needs is not whole (refused, sampled, missing or lossy)."""
    ch = c.chk.get(kind) or []
    own = bool(rec.get("fold_rows") or rec.get("cut") or rec.get("trunc"))
    fail = any(t_ok and not passed for t_ok, passed in ch)
    bad = any(not t_ok for t_ok, _ in ch)
    rec["state"] = "lossy" if own or fail else "sampled" if rec.get("sampled") else "unknown" if bad else "whole"
    rec["off"] = _off(rec)


def bracket(c, kind, before, after, keys):
    """An R read vs its truth read just before and just after it (late events only add): key k is within when
    before(k)·0.98 − floor ≤ Σ split(k) ≤ after(k)·1.02 + floor; drift = after ÷ before per date."""
    rec = c.recs.get(kind)
    if not _ok(rec):
        return
    ch = c.chk.setdefault(kind, [])
    rows, b, a = c.rows(kind) or [], c.rows(before), c.rows(after)
    rec["truths"] = {before: c.st(before), after: c.st(after)}
    mets = [m for m in SPEC[kind].mets if m not in NON_ADD]
    main, rev = _main(mets), "totalAdRevenue" if "totalAdRevenue" in mets else None
    if b is None or a is None:
        ch.append((False, True))
        judge(c, kind, rec)
        return
    out, ins = {}, {}
    for m in mets:
        fl = FLOOR_USD if m in USD_METS else FLOOR_N
        g, lo, hi = _sum_by(rows, keys, m), _sum_by(b, keys, m), _sum_by(a, keys, m)
        ks = set(lo) | set(hi)
        inside = {k for k in ks if lo.get(k, 0.0) * (1 - TIE_REL) - fl <= g.get(k, 0.0) <= hi.get(k, 0.0) * (1 + TIE_REL)
                  + fl}
        tot = sum(v for v in hi.values() if v > 0)
        out[m] = {"keys": len(ks), "off": len(ks) - len(inside),
                  "w2": pr._ratio(sum(v for k, v in hi.items() if v > 0 and k in inside), tot)}
        ins[m] = (ks, inside)
    rec["bracket"] = out
    ch.append((c.st(before) == "whole" and c.st(after) == "whole", all(v["off"] == 0 for v in out.values())))
    day = day_map(rows, a, _ndims(kind), main, rev)
    for d, e in day.items():
        if not _is_ymd(d):
            continue
        for i, m in ((4, main), (5, rev)):
            if m:
                ks, inside = ins[m]
                mine = [k for k in ks if k.split("|")[0] == d]
                e[i] = all(k in inside for k in mine)
    rec["day"] = day
    lo, hi = _by(b, "date", main), _by(a, "date", main)
    rec["drift"] = {d: pr._ratio(hi.get(d, 0.0), v) for d, v in sorted(lo.items()) if v}
    judge(c, kind, rec)


def pick_dstar(c):
    """d* = the W day with the largest max(1 − Σ non-fold AUD(d) ÷ FD(d), fold share of AUD(d)) on eventCount, the latest
    on a tie; F when AUD is only sampled."""
    rec = c.recs.get("AUD") or {}
    if not rec.get("ok"):
        return None, None
    if rec.get("state") == "sampled":
        return c.p["F"], None
    fd = _by(c.rows("FD") or [], "date", "eventCount")
    nf, fo, tot = {}, {}, {}
    for r in c.rows("AUD") or []:
        d, v = str(r.get("date") or ""), _num(r.get("eventCount"))
        tot[d] = tot.get(d, 0.0) + v
        tgt = fo if _fold_row(r, (SC, FMT, UNIT)) else nf
        tgt[d] = tgt.get(d, 0.0) + v
    best = None
    for i in range(c.p["days"]):
        d = c.p["a"] + timedelta(days=i)
        k = pr._ymd(d)
        loss = max(1 - nf.get(k, 0.0) / fd[k] if fd.get(k) else 0.0, fo.get(k, 0.0) / tot[k] if tot.get(k) else 0.0)
        if best is None or loss >= best[1]:
            best = (d, loss)
    return best[0], round(best[1], 4)


def pick_block(c, hk):
    """OV / OA's 7 days: VDH / AUDH sampled → [h0, h0 + 6]; else the 7 days ending at the newest day before W that is not
    within (never before h0). → (block, None) or (None, skip reason)."""
    p = c.p
    if p["h0"] >= p["a"]:
        return None, "young"
    rec = c.recs.get(hk) or {}
    if not rec.get("ok"):
        return None, "no_shape" if rec.get("skip") == "no_shape" else "no_base"
    last = p["a"] - timedelta(days=1)
    if rec.get("sampled"):
        return [p["h0"], min(p["h0"] + timedelta(days=BLOCK_DAYS - 1), last)], None
    if rec.get("state") == "whole":
        return None, "whole"
    a = pr._ymd(p["a"])
    bad = sorted(d for d, e in (rec.get("day") or {}).items() if _is_ymd(d) and d < a and (e[4] is False
                                                                                          or e[5] is False))
    if not bad:
        return None, "whole"
    d = _ymd_date(bad[-1])
    return [max(d - timedelta(days=BLOCK_DAYS - 1), p["h0"]), d], None


# ── the reads ─────────────────────────────────────────────────────────────────────────────────

def meta_parse(j):
    """The metadata answer → the watched dimensions / metrics (booleans), the custom-dimension count, the registered
    SCREEN_PARAMS (param → API name) and the placement-like custom dimensions (their API names: private)."""
    dims = {str(x["apiName"]): bool(x.get("customDefinition")) for x in (j or {}).get("dimensions") or []
            if isinstance(x, dict) and x.get("apiName")}
    mets = {str(x["apiName"]) for x in (j or {}).get("metrics") or [] if isinstance(x, dict) and x.get("apiName")}
    low = {k.lower(): k for k in dims}
    return {"ok": bool(dims), "dims": len(dims), "custom": sum(1 for v in dims.values() if v),
            "has": {k: k in dims for k in META_DIMS}, "mets": {k: k in mets for k in META_METS},
            "custom_screen": {p: low["customevent:" + p] for p in SCREEN_PARAMS if "customevent:" + p in low},
            "placement": sorted(k for k, cust in dims.items() if cust and PLACE_RE.search(k))}


def read_meta(ga):
    """GET properties/<id>/metadata (cp.App.metadata: the same stops, counts and pause as a report; Core quota)."""
    ga.kind = "META"
    c0, s0 = ga.calls, ga.sec
    try:
        j = ga.metadata()
    except Stop:
        raise
    except Exception as e:
        rec = {"ok": False, "err": pr._err(e)}
    else:
        rec = pr._safely(meta_parse, j, fallback={"ok": False})
    rec.update(calls=ga.calls - c0, sec=round(ga.sec - s0, 2))
    return rec


def cc_parse(j):
    out = {}
    for key, meta in (("dimensionCompatibilities", "dimensionMetadata"), ("metricCompatibilities", "metricMetadata")):
        for x in (j or {}).get(key) or []:
            n = ((x or {}).get(meta) or {}).get("apiName")
            if n in CC_FIELDS:
                out[n] = x.get("compatibility")
    return {"fields": out}, None


def read_cc(c):
    """checkCompatibility (once, when AF or AU was refused): which watched fields GA4 lets join the screen class with
    eventCount on this stream's ad_impression events. No returnPropertyQuota on this method: a plain _post."""
    ga = c.ga
    body = {"dimensions": [{"name": SC}], "metrics": [{"name": "eventCount"}],
            "dimensionFilter": ga4.stream_filter(ga.stream_id, event=IMP)}
    rec, _ = cp._read(ga, "CC", lambda: ga._post("checkCompatibility", body), cc_parse)
    return rec


def read_ret(c, token, prop):
    """The property's data-retention SETTING (Admin API, read-only; once per property, cached; not a Data API call)."""
    if "ret" not in prop:
        if prop.get("stop") or c.run.over():
            return {"skip": "stopped"}
        prop["ret"] = pr.retention(token, c.u["property_id"])
    return prop["ret"]


def skip_of(kind, c):
    """Why a read is not asked now (None: ask it)."""
    r = SPEC[kind]
    if SCA in r.dims and (c.sca is None or (UNIT in r.dims and c.no_unit)):
        return "no_shape"
    if kind == "AFP":
        af = c.recs.get("AF")
        return None if _refused(af) else "whole" if _ok(af) else "no_base"
    if kind == "AUP":
        au = c.recs.get("AU") or {}
        if c.no_fmt or au.get("skip") == "no_shape":
            return "no_shape"
        if "skip" in au or not au:
            return "no_base"
        if PS in (au.get("dims") or ()):
            return "same"                            # AU already asked the page path
        if _refused(au) or (au.get("ok") and au.get("state") != "whole"):
            return None
        return "whole" if au.get("ok") else "no_base"
    if kind == "CC":
        return None if _refused(c.recs.get("AF")) or _refused(c.recs.get("AU")) else "whole"
    if kind == "XC":
        return "no_base" if not c.ok("EV") else None if c.xc_events else "no_events"
    if kind == "PV":
        return None if c.prev else "not_registered"
    if kind in ("AUD1", "AUDS"):
        s = c.st("AUD")
        if s in ("absent", "skip", "refused", "error", "unknown"):
            return "no_base"                         # AUD was not read, or its truth (T / FD) was not whole
        if kind == "AUD1":
            return None if s in ("lossy", "sampled") and c.dstar else "whole"
        return None if s == "lossy" else "whole"
    if kind in ("OV", "OA"):
        return c.block_skip.get(kind, "no_base")
    if kind in ("OAS", "OAP0", "OAP"):
        oa = c.recs.get("OA") or {}
        if "skip" in oa:
            return oa["skip"]
        if not oa.get("ok"):
            return "no_base"
        return "whole" if oa.get("state") == "whole" else None
    if kind == "XEP":
        xe = c.recs.get("XE")
        return None if _refused(xe) else "whole" if _ok(xe) else "no_base"
    if kind in ("CV", "CA"):
        rec = c.recs.get("CVD" if kind == "CV" else "CAD") or {}
        if "skip" in rec:
            return rec["skip"]
        return "whole" if rec.get("state") == "whole" else None
    return None


def after(kind, c):
    """What a read decides for the reads after it."""
    rec = c.recs.get(kind) or {}
    if kind == "META":
        c.prev = (rec.get("custom_screen") or {}).get("firebase_previous_class") if rec.get("ok") else None
    elif kind == "AFP" and "skip" not in rec:
        if rec.get("ok"):
            c.sca = PS                               # SC × format refused, the page path accepted
        else:
            c.sca, c.no_fmt = None, True             # no screen × ad format shape at all
    elif kind == "AUP" and _refused(c.recs.get("AU")):
        if rec.get("ok"):
            c.sca = PS
        else:
            c.no_unit = True                         # no screen × ad unit shape (AUP refused, or AU was the page path)
    elif kind == "EV" and rec.get("ok"):
        c.xc_events = [k for k, _ in custom_ad_events(c.rows("EV"))[:XC_MAX]]
    elif kind == "AUD":
        c.dstar, c.dstar_loss = pick_dstar(c)
    elif kind == "VDH":
        c.bv, c.block_skip["OV"] = pick_block(c, "VDH")
    elif kind == "AUDH":
        c.ba, c.block_skip["OA"] = pick_block(c, "AUDH")
    elif kind == "RV0b":
        bracket(c, "RV", "RV0", "RV0b", ("date",))
    elif kind == "RFb":
        bracket(c, "RAU", "RF", "RFb", ("date", FMT))


def reduce_long(kind, rows):
    """A long read's rows → the sums the facts need (its record already holds its ties and its day map)."""
    out = {"rows": len(rows)}
    if kind == "VDH":
        mon, mcls = {}, {}
        for r in rows:
            d = str(r.get("date") or "")
            if not _is_ymd(d):
                continue
            ym, v, k = d[:6], _num(r.get("screenPageViews")), _cls(r)
            e = mon.setdefault(ym, [0.0, 0.0])
            e[0] += v
            if _named(k):
                e[1] += v
                mc = mcls.setdefault(ym, {})
                mc[k] = mc.get(k, 0.0) + v
        out.update(month=mon, mcls=mcls)
    elif kind == "AUDH":
        mon = {}
        for r in rows:
            d = str(r.get("date") or "")
            if not _is_ymd(d):
                continue
            e = mon.setdefault(d[:6], [0.0, 0.0, 0.0])
            v = _num(r.get("eventCount"))
            e[0] += v
            if _named(_cls(r)):
                e[1] += v
            e[2] += _num(r.get("totalAdRevenue"))
        out["month"] = mon
    elif kind in ("NVD", "NAD", "AAD"):
        key = NVR if kind != "AAD" else VER
        out["by"] = _by(rows, key, "screenPageViews" if kind == "NVD" else "eventCount")
    elif kind == "AVD":
        vc, first = {}, {}
        for r in rows:
            v, d, k = str(r.get(VER) or ""), str(r.get("date") or ""), _cls(r)
            e = vc.setdefault(v, {})
            e[k] = e.get(k, 0.0) + _num(r.get("screenPageViews"))
            if _is_ymd(d) and (v not in first or d < first[v]):
                first[v] = d
        out.update(vc=vc, first=first)
    elif kind in ("CVD", "CAD"):
        out["countries"] = len({str(r.get(CTY)) for r in rows if _named(r.get(CTY))})
    return out


def post(c, kind, rec, rows):
    """An accepted read's ties, keys, day map and state; a long read is then kept as sums only."""
    c.chk[kind] = []
    try:
        if kind == "EV":
            ev_ties(c, rec, rows)
        elif kind not in ("RV", "RAU"):
            apply_checks(c, kind, rec, rows)
    except Exception as e:                       # a bug in the bookkeeping: the call is spent, the record stays
        rec["bug"] = type(e).__name__
        c.chk[kind].append((False, True))
    if kind in ("RV", "RAU"):
        rec.update(state="unknown", off=False)  # judged once the truth after it is read (bracket)
    else:
        judge(c, kind, rec)
    if kind in LONG:
        c.got[kind] = pr._safely(reduce_long, kind, rows, fallback={})


def do_read(c, kind):
    why = skip_of(kind, c)
    if why:
        c.recs[kind] = {"skip": why}
    elif kind == "META":
        c.recs[kind] = read_meta(c.ga)
    elif kind == "CC":
        c.recs[kind] = read_cc(c)
    else:
        body, event, events, dims = request(kind, c)
        ga = c.ga
        rec, rows = cp._read(ga, kind, lambda: ga.report_all(body, event=event, events=events, page_rows=PAGE_ROWS),
                             p_rows(dims, SPEC[kind].mets, kind in KEEP))
        if tuple(dims) != SPEC[kind].dims:
            rec["dims"] = list(dims)
        if rec.get("ok"):
            rec.update(pr._safely(page_meta, ga, rows, fallback={}))
            c.got[kind] = _norm(rows, c.prev)
            post(c, kind, rec, c.got[kind])
        c.recs[kind] = rec
    after(kind, c)


# ── the facts (private: screen, unit and event names live only here) ──────────────────────────

def base(c):
    """The W reads summed per class / format, and the ad-like classes."""
    views, users, eng = {}, {}, {}
    for r in c.rows("V") or []:
        k = _cls(r)
        views[k] = views.get(k, 0.0) + _num(r.get("screenPageViews"))
        users[k] = users.get(k, 0.0) + _num(r.get("activeUsers"))
        eng[k] = eng.get(k, 0.0) + _num(r.get("userEngagementDuration"))
    imps, rev = _by(c.rows("A") or [], SC, "eventCount"), _by(c.rows("A") or [], SC, "totalAdRevenue")
    fm = {}
    for r in c.rows(c.role("AF")) or []:
        e = fm.setdefault(_cls(r), {})
        f = _fmt(r.get(FMT))
        e[f] = e.get(f, 0.0) + _num(r.get("eventCount"))
    ftot, frev, raw = {}, {}, {}
    for r in c.rows("F") or []:
        f = _fmt(r.get(FMT))
        ftot[f] = ftot.get(f, 0.0) + _num(r.get("eventCount"))
        frev[f] = frev.get(f, 0.0) + _num(r.get("totalAdRevenue"))
        raw.setdefault(f, set()).add(str(r.get(FMT) or ""))
    like = set()
    for k, fx in fm.items():
        if not _named(k) or is_ad_screen(k):
            continue
        t, fs = sum(fx.values()), sum(v for f, v in fx.items() if f in FULL)
        if t > 0 and fs / t >= 0.9 and (not views.get(k) or fs / views[k] >= 0.5):
            like.add(k)
    return {"views": views, "users": users, "eng": eng, "imps": imps, "rev": rev, "fm": fm, "ftot": ftot,
            "frev": frev, "raw": raw, "like": like}


def _kind_of(k, b):
    return "ad" if is_ad_screen(k) else "like" if k in b["like"] else "no"


def f_table(c, b):
    """[class, ad | like | no, views, users, sessions | None, engagement s, impressions, ad revenue, {format:
    impressions}, clicks, rewards, {format: reach users} | None, exposure s | None, impressions a view, revenue per 1000
    views] — the TABLE_MAX classes with the most views, every ad / ad-like class and every class with ≥ 1 % of the
    impressions."""
    ses = _by(c.rows("VS"), SC, "sessions") if c.ok("VS") else None
    clk, rwd = {}, {}
    for r in c.rows("X") or []:
        tgt = clk if r.get(EVN) == "ad_click" else rwd if r.get(EVN) == "ad_reward" else None
        if tgt is not None:
            tgt[_cls(r)] = tgt.get(_cls(r), 0.0) + _num(r.get("eventCount"))
    reach = None
    if c.ok("AR"):
        reach = {}
        for r in c.rows("AR") or []:
            reach.setdefault(_cls(r), {})[_fmt(r.get(FMT))] = int(_num(r.get("activeUsers")))
    xk = "XE" if c.ok("XE") else "XEP" if c.ok("XEP") else None
    expo = _by(c.rows(xk), SC, "adUnitExposure") if xk else None
    tot_imp = sum(b["imps"].values())
    rows = []
    for k in set(b["views"]) | set(b["imps"]):
        v, n, rv = b["views"].get(k, 0.0), b["imps"].get(k, 0.0), b["rev"].get(k, 0.0)
        rows.append([k, _kind_of(k, b), int(v), int(b["users"].get(k, 0.0)),
                     int(ses.get(k, 0.0)) if ses is not None else None, round(b["eng"].get(k, 0.0), 1), int(n),
                     round(rv, 4), {f: int(x) for f, x in sorted((b["fm"].get(k) or {}).items())},
                     int(clk.get(k, 0.0)), int(rwd.get(k, 0.0)),
                     (reach.get(k) or {}) if reach is not None else None,
                     round(expo.get(k, 0.0) / 1000.0, 1) if expo is not None else None,   # GA4 gives milliseconds
                     pr._ratio(n, v), round(rv / v * 1000, 4) if v else None])
    rows.sort(key=lambda x: (-x[2], -x[6], x[0]))
    keep = {x[0] for x in rows[:TABLE_MAX]} | {x[0] for x in rows if x[1] != "no"} | \
        {x[0] for x in rows if tot_imp and x[6] >= 0.01 * tot_imp}
    return [x for x in rows if x[0] in keep]


def f_screens(c, b):
    tot = dp._tot(c.rows("V") or [], "screenPageViews")
    named = {k: v for k, v in b["views"].items() if _named(k) and v > 0}
    return {"classes": len(named), "top1": pr._ratio(max(named.values()), tot) if named else None,
            "c90": dp.cover(list(named.values()), (0.9,))["0.9"],
            "ad_screens": sorted(k for k in named if is_ad_screen(k)),
            "sca": "SC" if c.sca == SC else "PS" if c.sca == PS else "none", "sca_units": not c.no_unit}


def names_facts(rows):
    """VN rows (class × screen name) → share named, distinct names, most names in one class, classes split by names,
    and mixed classes (named and "(not set)" names each ≥ 30 % of the class's views: a screen_view logged twice?)."""
    per, names, tot, named = {}, set(), 0.0, 0.0
    for r in rows or []:
        k, nm, v = _cls(r), str(r.get(SN) or ""), _num(r.get("screenPageViews"))
        e = per.setdefault(k, {"t": 0.0, "n": 0.0, "u": 0.0, "names": set()})
        tot += v
        e["t"] += v
        if _named(nm):
            named += v
            e["n"] += v
            e["names"].add(nm)
            names.add(nm)
        elif not _isfold(nm):
            e["u"] += v
    mixed = sorted(k for k, e in per.items() if e["t"] > 0 and e["n"] / e["t"] >= 0.3 and e["u"] / e["t"] >= 0.3)
    return {"share": pr._ratio(named, tot), "n": len(names),
            "max_per_class": max((len(e["names"]) for e in per.values()), default=0),
            "classes_split": sum(1 for e in per.values() if len(e["names"]) > 1), "mixed": mixed[:TOP_N],
            "mixed_n": len(mixed)}


def f_names(c, b):
    return names_facts(c.rows("VN")) if c.ok("VN") else None


def f_obf(c, b):
    tot = dp._tot(c.rows("V") or [], "screenPageViews")
    return pr._ratio(sum(v for k, v in b["views"].items() if is_obf(k)), tot)


def fmt_facts(fm, ftot, raw, like):
    """Per format f, over F(f) (the format's truth): its share of the app, on ad screens / ad-like / "(not set)" / host
    screens, lost = the rest (folded or missing in the split), the top host [class, share] and GA4's spellings."""
    all_ = sum(ftot.values())
    out = {}
    for f, t in sorted(ftot.items()):
        if t <= 0:
            continue
        on, hosts = {"ad": 0.0, "like": 0.0, "unset": 0.0, "host": 0.0}, {}
        for k, fx in fm.items():
            n = fx.get(f, 0.0)
            if not n or _isfold(k):
                continue
            if is_ad_screen(k):
                on["ad"] += n
            elif k in like:
                on["like"] += n
            elif not _named(k):
                on["unset"] += n
            else:
                on["host"] += n
                hosts[k] = n
        top = max(hosts.items(), key=lambda kv: (kv[1], kv[0])) if hosts else None
        out[f] = {"share": pr._ratio(t, all_), "on_ad": pr._ratio(on["ad"], t), "on_like": pr._ratio(on["like"], t),
                  "on_unset": pr._ratio(on["unset"], t), "on_host": pr._ratio(on["host"], t),
                  "lost": round(1 - sum(on.values()) / t, 4), "top_host": [top[0], pr._ratio(top[1], t)] if top else None,
                  "raw": sorted(raw.get(f) or ())}
    return out


def f_fmt(c, b):
    return fmt_facts(b["fm"], b["ftot"], b["raw"], b["like"])


def fs_code(x):
    """A full-screen format's verdict, the first that applies: small (< 0.5 % of the app) | lost (> 2 % not placed) |
    sdk (≥ 95 % on the SDK's own screen) | host (≤ 5 % off the app's screens) | unset (≥ 50 % "(not set)") | check
    (≥ 5 % on ad-like classes) | mixed."""
    if not x or x.get("share") is None or x["share"] < 0.005:
        return "small"
    if (x.get("lost") or 0) > 0.02:
        return "lost"
    ad, like, unset = x.get("on_ad") or 0, x.get("on_like") or 0, x.get("on_unset") or 0
    if ad >= 0.95:
        return "sdk"
    if ad + like + unset <= 0.05:
        return "host"
    if unset >= 0.5:
        return "unset"
    if like >= 0.05:
        return "check"
    return "mixed"


def f_like(c, b):
    return sorted(b["like"])


def f_adcheck(c, b):
    adv = sum(v for k, v in b["views"].items() if is_ad_screen(k))
    other = sum(v for k, v in b["views"].items() if _named(k) and not is_ad_screen(k))
    fs = sum(v for f, v in b["ftot"].items() if f in FULL)
    eng = sum(v for k, v in b["eng"].items() if is_ad_screen(k))
    return {"ad_views": int(adv), "ad_views_per_fs_imp": dp.tie(adv, fs), "ret_max": pr._ratio(adv, other),
            "ad_eng_per_view": round(eng / adv, 2) if adv else None}


def f_units(c, b):
    """The AU answer per ad unit: [unit, format, impressions, classes with ≥ 1 %, top class, its share, ad-screen share];
    per format the units and the share of its impressions on units that sit ≥ 99 / 95 % on one screen (one99 / one95,
    over F(f)); per top class the units holding ≥ 1 % of it."""
    rows = c.rows(c.role("AU"))
    if rows is None:
        return None
    by, per_cls = {}, {}
    for r in rows:
        un, f, k, n = str(r.get(UNIT) or ""), _fmt(r.get(FMT)), _cls(r), _num(r.get("eventCount"))
        if _isfold(un) or f == "fold" or _isfold(k):
            continue
        cs = by.setdefault((un, f), {})
        cs[k] = cs.get(k, 0.0) + n
        pc = per_cls.setdefault(k, {})
        pc[un] = pc.get(un, 0.0) + n
    units, umap = [], {}
    for (un, f), cs in by.items():
        t = sum(cs.values())
        if t <= 0:
            continue
        top = max(cs.items(), key=lambda kv: (kv[1], kv[0]))
        ts = top[1] / t
        units.append([un, f, int(t), sum(1 for v in cs.values() if v >= 0.01 * t), top[0], round(ts, 4),
                      pr._ratio(sum(v for k, v in cs.items() if is_ad_screen(k)), t)])
        e = umap.setdefault(f, [0, 0.0, 0.0, 0.0])
        e[0] += 1
        e[1] += t if ts >= 0.99 else 0.0
        e[2] += t if ts >= 0.95 else 0.0
        e[3] += t
    units.sort(key=lambda x: (-x[2], x[0]))
    # over F(f), the format's truth: impressions the split folded or lost never count as "on one screen"
    unit_map = {f: {"units": e[0], "one99": pr._ratio(e[1], b["ftot"].get(f) or e[3]),
                    "one95": pr._ratio(e[2], b["ftot"].get(f) or e[3])} for f, e in sorted(umap.items())}
    class_units = {}
    for k, us in sorted(per_cls.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:TOP_N]:
        t = sum(us.values())
        class_units[k] = [[un, round(v / t, 4)] for un, v in sorted(us.items(), key=lambda kv: (-kv[1], kv[0]))
                          if t and v >= 0.01 * t]
    return {"units": units[:UNITS_MAX], "n": len(units), "unit_map": unit_map, "class_units": class_units}


def f_eng(c, b):
    tot = sum(b["eng"].values())
    pv = [b["eng"][k] / v for k, v in b["views"].items() if _named(k) and v > 0]
    return {"tie": ((c.recs.get("V") or {}).get("tie") or {}).get("userEngagementDuration"),
            "unset": pr._ratio(sum(v for k, v in b["eng"].items() if str(k) in UNSET), tot),
            "on_ad": pr._ratio(sum(v for k, v in b["eng"].items() if is_ad_screen(k)), tot),
            "per_view_p50": sp._pct(pv, 0.5)}


def _ev_counts(c):
    return _by(c.rows("EV") or [], EVN, "eventCount")


def f_clicks(c, b):
    ev = _ev_counts(c)
    clk = [r for r in c.rows("X") or [] if r.get(EVN) == "ad_click"]
    n = dp._tot(clk, "eventCount")
    t2 = dp._tot(c.rows("T2") or [], "publisherAdClicks") if c.ok("T2") else None
    return {"n": int(ev.get("ad_click", 0.0)),
            "on_ad": pr._ratio(sum(_num(r.get("eventCount")) for r in clk if is_ad_screen(_cls(r))), n),
            "fmt_named": pr._ratio(sum(_num(r.get("eventCount")) for r in clk
                                       if _fmt(r.get(FMT)) not in ("notset", "fold")), n),
            "tie": dp.tie(ev.get("ad_click", 0.0), t2) if t2 is not None else None}


def f_rewards(c, b):
    n = _ev_counts(c).get("ad_reward", 0.0)
    return {"n": int(n), "per_imp": pr._ratio(n, b["ftot"].get("rewarded", 0.0) + b["ftot"].get("rewardedinterstitial",
                                                                                                   0.0))}


def f_ev(c, b):
    t, t2, v0 = c.rows("T"), c.rows("T2"), c.rows("V0")
    ev = _ev_counts(c)
    out = {"ev_vs_imps": dp.tie(dp._tot(t, "eventCount"), dp._tot(t2, "publisherAdImpressions"))
           if t is not None and t2 is not None else None,
           "rev_on_imp": dp.tie(dp._tot(t, "totalAdRevenue"), dp._tot(t2, "totalAdRevenue"))
           if t is not None and t2 is not None else None,
           "views_tie": dp.tie(ev.get("screen_view", 0.0), dp._tot(v0, "screenPageViews"))
           if v0 is not None and c.ok("EV") else None}
    rv = _by(c.rows("EV") or [], EVN, "totalAdRevenue")
    out["rev_other"] = pr._ratio(sum(v for k, v in rv.items() if k != IMP), sum(rv.values()))   # ad revenue off it
    out["events"] = {k: int(v) for k, v in sorted(ev.items(), key=lambda kv: (-kv[1], kv[0]))[:EVENTS_MAX]}
    out["custom_ad_events"] = {k: int(v) for k, v in custom_ad_events(c.rows("EV") or [])[:XC_MAX]}
    return out


def f_xc(c, b):
    """The apps' own ad-like events by screen: count, the format the name suggests, count ÷ that format's impressions,
    the share on ad screens / on the app's own named screens (host), the top 5 hosts."""
    if not c.ok("XC"):
        return None
    per = {}
    for r in c.rows("XC") or []:
        e = per.setdefault(str(r.get(EVN) or ""), {})
        e[_cls(r)] = e.get(_cls(r), 0.0) + _num(r.get("eventCount"))
    out = {}
    for name, cs in sorted(per.items()):
        n = sum(cs.values())
        g = fmt_guess(name)
        host = {k: v for k, v in cs.items() if _named(k) and not is_ad_screen(k) and k not in b["like"]}
        out[name] = {"n": int(n), "fmt": g, "per_imp": pr._ratio(n, b["ftot"].get(g)) if g else None,
                     "on_ad": pr._ratio(sum(v for k, v in cs.items() if is_ad_screen(k)), n),
                     "host": pr._ratio(sum(host.values()), n),
                     "hosts": [[k, pr._ratio(v, n)] for k, v in sorted(cs.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]}
    return out


def f_meta_extra(c, b):
    return (c.recs.get("META") or {}).get("placement") or []


def ver_facts(vc, first):
    """AVD sums → versions, the top version's share of the views, the newest version (the latest first day), the classes
    only it has and the classes it no longer has (≤ TOP_N each, by views)."""
    named = [v for v in vc if _named(v)]
    tot = sum(sum(cs.values()) for cs in vc.values())
    per = {v: sum(vc[v].values()) for v in named}
    if not named:
        return {"versions": 0, "top_share": None, "newest": None, "classes_new": [], "classes_gone": []}
    newest = max(named, key=lambda v: (first.get(v, ""), _natural(v)))
    mine = {k: x for k, x in vc[newest].items() if _named(k) and x > 0}
    rest = {}
    for v in named:
        if v != newest:
            for k, x in vc[v].items():
                if _named(k) and x > 0:
                    rest[k] = rest.get(k, 0.0) + x
    return {"versions": len(named), "top_share": pr._ratio(max(per.values()), tot), "newest": newest,
            "classes_new": [k for k, _ in sorted(((k, x) for k, x in mine.items() if k not in rest),
                                                 key=lambda kv: (-kv[1], kv[0]))[:TOP_N]],
            "classes_gone": [k for k, _ in sorted(((k, x) for k, x in rest.items() if k not in mine),
                                                  key=lambda kv: (-kv[1], kv[0]))[:TOP_N]]}


def f_layers(c, b):
    W = lambda k: c.st(k) == "whole"   # noqa: E731
    out = {}
    v0 = c.rows("V0")
    out["sessions"] = {"accepted": c.ok("VS"),
                       "sum_ratio": dp.tie(dp._tot(c.rows("VS") or [], "sessions"), dp._tot(v0 or [], "sessions"))
                       if c.ok("VS") and v0 is not None else None}
    if c.ok("AR"):
        users = {}
        for r in c.rows("AR") or []:
            users[(_cls(r), _fmt(r.get(FMT)))] = _num(r.get("activeUsers"))
        reach = {}
        for f in sorted(b["ftot"]):
            top = sorted(((k, fx.get(f, 0.0)) for k, fx in b["fm"].items() if fx.get(f)), key=lambda kv: -kv[1])[:5]
            reach[f] = [[k, int(users.get((k, f), 0.0)), pr._ratio(n, users.get((k, f)))] for k, n in top]
        out["reach"] = reach
    xk = "XE" if c.ok("XE") else "XEP" if c.ok("XEP") else None
    if xk and c.ok("XE0"):
        banner_views = sum(b["views"].get(k, 0.0) for k, fx in b["fm"].items() if fx.get("banner"))
        out["exposure"] = {"read": xk, "tie": ((c.recs.get(xk) or {}).get("tie") or {}).get("adUnitExposure"),
                           "s_per_banner_view": pr._ratio(dp._tot(c.rows("XE0"), "adUnitExposure") / 1000.0,
                                                          banner_views)}
    nv, na = c.got.get("NVD") or {}, c.got.get("NAD") or {}
    if nv or na:
        out["nvr"] = {"views_new": pr._ratio((nv.get("by") or {}).get("new", 0.0), sum((nv.get("by") or {}).values())),
                      "imps_new": pr._ratio((na.get("by") or {}).get("new", 0.0), sum((na.get("by") or {}).values())),
                      "daily_whole": W("NVD") and W("NAD")}
    av = c.got.get("AVD") or {}
    if av.get("vc") is not None:
        out["ver"] = dict(ver_facts(av["vc"], av.get("first") or {}), daily_whole=W("AVD") and W("AAD"))
    cv, ca = c.got.get("CVD") or {}, c.got.get("CAD") or {}
    w7 = (c.p["F"] - c.p["a7"]).days + 1
    out["country"] = {"countries": cv.get("countries"),
                      "rows_day": {"cvd": pr._ratio(cv.get("rows"), w7), "cad": pr._ratio(ca.get("rows"), w7)},
                      "whole": W("CVD") and W("CAD"), "window_whole": W("CV") and W("CA")}
    if c.ok("S"):
        src = {}
        for r in c.rows("S") or []:
            e = src.setdefault(_fmt(r.get(FMT)), {})
            s = str(r.get(SRC) or "")
            e[s] = e.get(s, 0.0) + _num(r.get("eventCount"))
        out["sources"] = {f: {s: pr._ratio(v, sum(e.values())) for s, v in sorted(e.items(), key=lambda kv: -kv[1])}
                          for f, e in sorted(src.items())}
    if c.ok("PV"):
        pv = {}
        for r in c.rows("PV") or []:
            k = _cls(r)
            if is_ad_screen(k):
                e = pv.setdefault(k, {})
                p = str(r.get(PREV_KEY) or "")
                e[p] = e.get(p, 0.0) + _num(r.get("screenPageViews"))
        out["pv"] = {k: [[p, pr._ratio(v, sum(e.values()))] for p, v in sorted(e.items(), key=lambda kv: -kv[1])[:TOP_N]]
                     for k, e in sorted(pv.items())}
    return out


def f_daily(c, b):
    aud, days = c.recs.get("AUD") or {}, c.p["days"]
    ev = c.rows("EV")
    lossy = sum(1 for d, e in (aud.get("day") or {}).items() if _is_ymd(d) and (e[4] is False or e[5] is False))
    return {"vd_rows_day": pr._ratio((c.recs.get("VD") or {}).get("rows"), days),
            "aud_rows_day": pr._ratio(aud.get("rows"), days),
            "auds_rows_day": pr._ratio((c.recs.get("AUDS") or {}).get("rows"), days),
            "aud_days_lossy": lossy if aud.get("ok") else None,
            "aud_worst": [_iso(c.dstar), c.dstar_loss] if c.dstar else None, "sampled": bool(aud.get("sampled")),
            "smp_space": (aud.get("smp") or {}).get("space"),
            "events_day": pr._ratio(dp._tot(ev, "eventCount"), days) if ev is not None else None}


def recent_state(x):
    if x["views_truth"] == 0 and not x["imps_truth"]:
        return "empty"
    if x["views_in"] is None or x["imps_in"] is None:
        return "unknown"
    return "whole" if x["views_in"] and x["imps_in"] and not x["fold"] else "folds"


def f_recent(c, b):
    """Per R day: views, within the bracket?, drift (after ÷ before), impressions, within?, the fold share — and its
    state (whole | folds | empty | unknown)."""
    rv, ra = c.recs.get("RV") or {}, c.recs.get("RAU") or {}
    out, d = {}, c.p["r0"]
    while d <= c.p["today"]:
        k = pr._ymd(d)
        ev, ea = (rv.get("day") or {}).get(k), (ra.get("day") or {}).get(k)
        x = {"views": ev[0] if ev else None, "views_truth": ev[1] if ev else None, "views_in": ev[4] if ev else None,
             "drift": (rv.get("drift") or {}).get(k), "imps": ea[0] if ea else None,
             "imps_truth": ea[1] if ea else None, "imps_in": (ea[4] and ea[5] is not False) if ea else None,
             "fold": max(ev[2] if ev else 0.0, ea[2] if ea else 0.0)}
        if ev is None and _ok(rv) and "day" in rv:
            x.update(views=0, views_truth=0, views_in=True)
        if ea is None and _ok(ra) and "day" in ra:
            x.update(imps=0, imps_truth=0, imps_in=True)
        x["state"] = recent_state(x)
        out[_iso(d)] = x
        d += timedelta(days=1)
    return out


def own_edge(rec):
    """The newest dataTruncationDate of a PROPERTY truncation on this read (its event data before that day is gone)."""
    ds = [t[1] for t in (rec or {}).get("trunc") or [] if t and t[0] == TRUNC_PROPERTY and t[1]]
    return _day(max(ds)) if ds else None


def prop_edge(c):
    """The same over every read of the app."""
    ds = [own_edge(rec) for rec in c.recs.values() if isinstance(rec, dict)]
    ds = [d for d in ds if d]
    return max(ds) if ds else None


def from_day(rec, h0, f, edge=None, rev=False):
    """The earliest day from which every day to F is within (a day neither side has is 0 = 0: within); never before a
    property truncation's date."""
    if not _ok(rec) or "day" not in rec:
        return None
    day, d, first = rec["day"], f, None
    while d >= h0:
        e = day.get(pr._ymd(d))
        good = e is None or (e[4] is True and (not rev or e[5] is not False))
        if not good or (edge and d < edge):
            break
        first, d = d, d - timedelta(days=1)
    return first


def cause(c, hk, bk):
    """Why the history read is not whole: whole | range (a shorter read of the same days is whole: backfill in chunks) |
    age (old days short even in a 7-day read, or a property truncation) | unknown."""
    rec = c.recs.get(hk) or {}
    if not rec.get("ok"):
        return "unknown"
    s = rec.get("state")
    if s in ("whole", "unknown"):
        return s
    blk = c.recs.get(bk) or {}
    if blk.get("ok"):
        return {"whole": "range", "lossy": "age"}.get(blk.get("state"), "unknown")
    if any(t and t[0] == TRUNC_PROPERTY for t in rec.get("trunc") or []):
        return "age"
    if blk.get("skip") in ("whole", "young"):
        return "range"                               # the loss sits in W's days only: the long range itself
    return "unknown"


def old_split(c):
    """When OA (old days, 7-day read) is not whole: format (class × format holds: OAS) | publisher (the Publisher ads
    report's own shape holds: OAP) | none."""
    oa = c.recs.get("OA") or {}
    if not oa.get("ok") or oa.get("state") == "whole":
        return None
    if c.st("OAS") == "whole":
        return "format"
    if c.st("OAP") == "whole":
        return "publisher"
    return "none"


def f_hist(c, b):
    p, out = c.p, {}
    hd = c.rows("HD0")
    first = {}
    if hd is not None:
        days = set()
        for r in hd:
            d, e = str(r.get("date") or ""), str(r.get(EVN) or "")
            if _is_ymd(d) and _num(r.get("eventCount")) > 0:
                days.add(d)
                if e not in first or d < first[e]:
                    first[e] = d
        out["first_day"] = {e: _iso(_ymd_date(first[e])) if e in first else None for e in HEV}
        out["days"] = len(days)
        if days:
            d0 = _ymd_date(min(days))
            out["gaps"] = sum(1 for i in range((p["F"] - d0).days + 1) if pr._ymd(d0 + timedelta(days=i)) not in days)
    out["edge"] = _iso(prop_edge(c))
    for name, hk, ev, rev in (("views", "VDH", "screen_view", False), ("ads", "AUDH", IMP, True)):
        fd = from_day(c.recs.get(hk), p["h0"], p["F"], own_edge(c.recs.get(hk)), rev)
        if fd and ev in first:
            fd = max(fd, _ymd_date(first[ev]))       # never before the event's first day
        out[name + "_from"] = _iso(fd)
    off = {}
    for name, hk in (("views", "VDH"), ("ads", "AUDH")):
        day = (c.recs.get(hk) or {}).get("day") or {}
        bad = [[d, pr._ratio(e[0], e[1])] for d, e in sorted(day.items(), reverse=True)
               if _is_ymd(d) and (e[4] is False or e[5] is False)]
        off[name] = bad[:OFF_DAYS_MAX]
    out["off_days"] = off
    out["w_range"] = {"views": (((c.recs.get("VDH") or {}).get("keys_w") or {}).get("screenPageViews") or {}).get("w2"),
                      "ads": (((c.recs.get("AUDH") or {}).get("keys_w") or {}).get("eventCount") or {}).get("w2")}
    h0r = c.recs.get("HD0") or {}
    out["hd0_w"] = {"screen_view": ((h0r.get("keys_sv") or {}).get("eventCount") or {}).get("all"),
                    "ad_impression": ((h0r.get("keys_ad") or {}).get("eventCount") or {}).get("all")}
    out["cause"] = {"views": cause(c, "VDH", "OV"), "ads": cause(c, "AUDH", "OA")}
    out["old_split"] = old_split(c)
    out["per_month"], out["top_month"] = per_month(c)
    out["rows_total"] = {"vdh": (c.recs.get("VDH") or {}).get("rows"), "audh": (c.recs.get("AUDH") or {}).get("rows")}
    return out


def per_month(c):
    """[yearMonth, views, impressions (HD0), the named-class share of each (VDH / AUDH), Σ VDH ÷ HD0, Σ AUDH ÷ HD0] (the
    newest MONTHS_MAX) and the TOP_N classes by views per month."""
    hm = {}
    for r in c.rows("HD0") or []:
        d = str(r.get("date") or "")
        if _is_ymd(d):
            e = hm.setdefault(d[:6], [0.0, 0.0])
            e[0 if r.get(EVN) == "screen_view" else 1] += _num(r.get("eventCount"))
    vm = (c.got.get("VDH") or {}).get("month") or {}
    am = (c.got.get("AUDH") or {}).get("month") or {}
    rows = []
    for ym in sorted(set(hm) | set(vm) | set(am)):
        hv, ha = hm.get(ym, [0.0, 0.0])
        v, a = vm.get(ym), am.get(ym)
        rows.append([ym, _n(hv), _n(ha), pr._ratio(v[1], hv) if v else None, pr._ratio(a[1], ha) if a else None,
                     dp.tie(v[0], hv) if v else None, dp.tie(a[0], ha) if a else None])
    mcls = (c.got.get("VDH") or {}).get("mcls") or {}
    top = {ym: [[k, _n(v)] for k, v in sorted(cs.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]]
           for ym, cs in sorted(mcls.items())[-MONTHS_MAX:]}
    return rows[-MONTHS_MAX:], top


FACTS = (("table", f_table), ("screens", f_screens), ("names", f_names), ("obf", f_obf), ("ad_like", f_like),
         ("fmt", f_fmt), ("adcheck", f_adcheck), ("units", f_units), ("eng", f_eng), ("clicks", f_clicks),
         ("rewards", f_rewards), ("ev", f_ev), ("xc", f_xc), ("meta_extra", f_meta_extra), ("layers", f_layers),
         ("daily", f_daily), ("recent", f_recent), ("hist", f_hist))


def facts(c):
    b = base(c)
    return {name: pr._safely(fn, c, b, fallback={}) for name, fn in FACTS}


# ── AdMob's own numbers (OFFLINE: the clone's report, no API call) ────────────────────────────

def load_admob(root, units, now=None):
    """The clone's AdMob mediation ad-unit report (data/mediation_unit.json[.gz]: every ad source, per AdMob app, unit,
    format and day) → {"state": "ok", "tz": the AdMob report zone (site/dashboard.json "report_tz") or None, "apps":
    {key: {"ids", "cur": [currencies], "raw": {format: [spellings]}, "f": {format: {day: [impressions, clicks,
    micros]}}, "u": {unit id: {"name", "fmt", "d": {day: [impressions, clicks, micros, requests, matched]}}}}}} — every
    AdMob app id of the unit (its app_ids + data/app_store_ids.json's ids of the same package); unit days only for the
    last UNIT_DAYS. {"state": "absent"} without a clone."""
    dd = os.path.join(root or "", "data")
    if not root or not os.path.isdir(dd):
        return {"state": "absent"}
    from admob_iq.db import FileRepo, _read_json_any
    dash = _read_json_any(os.path.join(root, "site", "dashboard.json")) or {}
    by_id = ((_read_json_any(os.path.join(dd, "app_store_ids.json")) or {}).get("by_id")) or {}
    now = now or datetime.now(timezone.utc)
    cut = (now.date() - timedelta(days=UNIT_DAYS)).isoformat()
    key_of, n_ids = {}, {}
    for u in units:
        ids = list(u.get("app_ids") or [u["app_id"]])
        ids += sorted(a for a, pk in by_id.items() if str(pk or "").strip() == u.get("package") and a not in ids)
        n_ids[u["key"]] = len(ids)
        for a in ids:
            key_of.setdefault(a, u["key"])
    apps = {}
    for r in FileRepo(dd).fetch_mediation_unit():
        k, d = key_of.get(r.get("app_id")), str(r.get("report_date") or "")[:10]
        if not k or not d:
            continue
        e = apps.setdefault(k, {"ids": n_ids[k], "cur": set(), "raw": {}, "f": {}, "u": {}})
        e["cur"].add(str(r.get("currency_code") or "USD"))
        f = _fmt(r.get("format"))
        e["raw"].setdefault(f, set()).add(str(r.get("format") or ""))
        v = [pr._int(r.get("impressions")), pr._int(r.get("clicks")), pr._int(r.get("estimated_earnings_micros")),
             pr._int(r.get("ad_requests")), pr._int(r.get("matched_requests"))]
        x = e["f"].setdefault(f, {}).setdefault(d, [0, 0, 0])
        for i in range(3):
            x[i] += v[i]
        if d >= cut:
            y = e["u"].setdefault(str(r.get("ad_unit_id") or ""), {"name": str(r.get("unit_name") or ""), "fmt": f,
                                                                    "d": {}})
            z = y["d"].setdefault(d, [0, 0, 0, 0, 0])
            for i in range(5):
                z[i] += v[i]
    for e in apps.values():
        e["cur"] = sorted(e["cur"])
        e["raw"] = {f: sorted(s) for f, s in e["raw"].items()}
    return {"state": "ok", "tz": str(dash.get("report_tz") or "") or None, "apps": apps}


def trust(r):
    """GA4 ÷ AdMob → match (0.9–1.1) | high (to 1.5) | double (≥ 1.5) | short (0.7–0.9) | low (< 0.7) | absent."""
    if r is None:
        return "absent"
    return "double" if r >= 1.5 else "high" if r > 1.1 else "match" if r >= 0.9 else "short" if r >= 0.7 else "low"


def admob_tie(adm, u, c):
    """GA4 (ad_impression events, their revenue, ad_click events) vs AdMob on the same date labels: per format and all
    (F over W), revenue only when every AdMob row is USD, clicks, per ad unit (U; by name, else by id; requests and
    matched requests; duplicate AdMob names flagged), the daily ratio's spread (FD) and per month over H (HD0). Both zones
    are said, never corrected."""
    st = (adm or {}).get("state") or "absent"
    if st != "ok":
        return {"state": st}
    p = c.p
    me = (adm.get("apps") or {}).get(u["key"]) or {}
    wd = {_iso(p["a"] + timedelta(days=i)) for i in range(p["days"])}
    usd = me.get("cur") == ["USD"]
    fa = me.get("f") or {}

    def win(byd, i):
        return sum(v[i] for d, v in (byd or {}).items() if d in wd)
    mob = {f: win(byd, 0) for f, byd in fa.items()}
    mrev = {f: win(byd, 2) / 1e6 for f, byd in fa.items()}
    g, grev = {}, {}
    for r in c.rows("F") or []:
        f = _fmt(r.get(FMT))
        g[f] = g.get(f, 0.0) + _num(r.get("eventCount"))
        grev[f] = grev.get(f, 0.0) + _num(r.get("totalAdRevenue"))
    out = {"state": "ok", "tz_admob": adm.get("tz"), "tz_ga4": u.get("tz"), "ids": me.get("ids"), "days": len(wd),
           "admob_days": len({d for byd in fa.values() for d in byd if d in wd}), "cur": me.get("cur") or [],
           "raw": me.get("raw") or {},
           "fmt": {f: [int(g.get(f, 0.0)), int(mob.get(f, 0)), dp.tie(g.get(f, 0.0), mob.get(f, 0))]
                   for f in sorted(set(g) | set(mob))},
           "all": dp.tie(sum(g.values()), sum(mob.values()))}
    if usd:
        out["rev"] = {f: [round(grev.get(f, 0.0), 4), round(mrev.get(f, 0.0), 4), dp.tie(grev.get(f, 0.0),
                                                                                         mrev.get(f, 0.0))]
                      for f in sorted(set(grev) | set(mrev))}
        out["all_rev"] = dp.tie(sum(grev.values()), sum(mrev.values()))
    if c.ok("EV"):
        gc, mc = _ev_counts(c).get("ad_click", 0.0), sum(win(byd, 1) for byd in fa.values())
        out["clicks"] = [int(gc), int(mc), dp.tie(gc, mc)]
    um = me.get("u") or {}
    by_name = {}
    for uid, x in sorted(um.items()):
        if x.get("name"):
            by_name.setdefault(x["name"].lower(), []).append(uid)

    def agg(uids):
        s = [0, 0, 0, 0, 0]
        for uid in uids:
            for d, v in (um[uid].get("d") or {}).items():
                if d in wd:
                    for i in range(5):
                        s[i] += v[i]
        return s
    units, seen = [], set()
    for r in c.rows("U") or []:
        nm, f, n, rv = str(r.get(UNIT) or ""), _fmt(r.get(FMT)), _num(r.get("eventCount")), _num(r.get("totalAdRevenue"))
        uids, how = by_name.get(nm.lower()), "name"
        if not uids and nm in um:
            uids, how = [nm], "id"
        s = agg(uids) if uids else None
        seen.update(uids or [])
        units.append([nm, f, int(n), s[0] if s else None, dp.tie(n, s[0]) if s else None, round(rv, 4),
                      round(s[2] / 1e6, 4) if s and usd else None, dp.tie(rv, s[2] / 1e6) if s and usd else None,
                      s[3] if s else None, s[4] if s else None, how if uids else None, bool(uids and len(uids) > 1)])
    for uid, x in sorted(um.items()):
        if uid in seen:
            continue
        s = agg([uid])
        if s[0] or s[3]:                              # AdMob shows it in W, GA4 does not
            units.append([x.get("name") or uid, x.get("fmt"), 0, s[0], dp.tie(0, s[0]), 0.0,
                          round(s[2] / 1e6, 4) if usd else None, dp.tie(0, s[2] / 1e6) if usd else None, s[3], s[4],
                          "admob_only", len(by_name.get((x.get("name") or "").lower()) or []) > 1])
    units.sort(key=lambda z: (-max(z[2], z[3] or 0), str(z[0])))
    out["units"] = units[:UNITS_MAX]
    gd = _by(c.rows("FD") or [], "date", "eventCount")
    ad = {}
    for byd in fa.values():
        for d, v in byd.items():
            ad[d] = ad.get(d, 0) + v[0]
    rs = [gd.get(d.replace("-", ""), 0.0) / ad[d] for d in sorted(wd) if ad.get(d)]
    out["day"] = {"n": len(rs), "p10": sp._pct(rs, 0.1), "p50": sp._pct(rs, 0.5), "p90": sp._pct(rs, 0.9)}
    if c.ok("HD0"):
        h0, f_ = _iso(p["h0"]), _iso(p["F"])
        gm = {}
        for r in c.rows("HD0") or []:
            d = str(r.get("date") or "")
            if r.get(EVN) == IMP and _is_ymd(d):
                e = gm.setdefault(d[:6], [0.0, 0.0])
                e[0] += _num(r.get("eventCount"))
                e[1] += _num(r.get("totalAdRevenue"))
        am = {}
        for byd in fa.values():
            for d, v in byd.items():
                if h0 <= d <= f_:
                    e = am.setdefault(d[:4] + d[5:7], [0, 0, set()])
                    e[0] += v[0]
                    e[1] += v[2]
                    e[2].add(d)
        month = []
        for ym in sorted(set(gm) | set(am)):
            gv, av = gm.get(ym, [0.0, 0.0]), am.get(ym, [0, 0, set()])
            month.append([ym, int(gv[0]), av[0], dp.tie(gv[0], av[0]), round(gv[1], 4),
                          round(av[1] / 1e6, 4) if usd else None, dp.tie(gv[1], av[1] / 1e6) if usd else None,
                          len(av[2])])
        out["month"] = month[-MONTHS_MAX:]
        out["ga4_from"] = next((m[0] for m in month if m[3] is not None and m[3] >= 0.5), None)
    return out


# ── the verdict per app ───────────────────────────────────────────────────────────────────────

def daily_word(c):
    s = c.st("AUD")
    if s == "whole":
        return "whole"
    if s in ("lossy", "sampled") and c.st("AUD1") == "whole":
        return "day1"
    if c.st("AUDS") == "whole":
        return "no-units"
    if c.st("AUP") == "whole":
        return "page_path"                           # W as one only: the store is still "check"
    return "check"


def layers(c, fx):
    W = lambda k: c.st(k) == "whole"   # noqa: E731
    xk = "XE" if c.ok("XE") else "XEP" if c.ok("XEP") else None
    xr = (c.recs.get(xk) or {}) if xk else {}
    xt = (xr.get("tie") or {}).get("adUnitExposure")
    xs = ((xr.get("s") or {}).get("adUnitExposure") or {}).get("sum")
    xc = fx.get("xc") if isinstance(fx.get("xc"), dict) else {}
    return {"sessions": c.ok("VS"), "reach": c.ok("AR"),
            "exposure": bool(xk and xs and xt is not None and abs(xt - 1) <= 0.02),
            "nvr": W("NVD") and W("NAD"), "version": W("AVD") and W("AAD"),
            "country": "daily" if W("CVD") and W("CAD") else "window" if W("CV") and W("CA") else "no",
            "source": W("S"), "prev_class": c.ok("PV"),
            "app_events": c.ok("XC") and any((x.get("host") or 0) >= 0.9 for x in (xc or {}).values()
                                             if isinstance(x, dict))}


def verdict_word(v):
    """no-screens | use-names / one-screen | build | build-from | build-split | check — the first that applies."""
    if v.get("no_screens"):
        return "no-screens"
    if v.get("one_screen"):
        return v.get("screens") or "one-screen"
    base_ = v.get("imps_whole") and v.get("views_whole") and v.get("daily") == "whole"
    ca, af, first = (v.get("cause") or {}).get("ads"), v.get("ads_from"), v.get("first_ad")
    if base_ and ca == "whole" and af and af == first:
        return "build"
    if base_ and (ca == "range" or (ca in ("whole", "age") and af)):
        return "build-from"
    if v.get("daily") in ("day1", "no-units"):
        return "build-split"
    return "check"


def verdict(c, fx, adm, res):
    W = lambda k: c.st(k) == "whole"   # noqa: E731
    v = {"imps_whole": W("A") and W(c.role("AF")) and W(c.role("AU"))}
    sa = (((c.recs.get("A") or {}).get("s") or {}).get("eventCount") or {}) if c.ok("A") else {}
    v["named_imps"] = round(1 - (sa.get("unset") or 0) - (sa.get("fold") or 0), 4) if c.ok("A") else None
    v["unset_row"] = v["named_imps"] is not None and v["named_imps"] < 0.98    # "Screen not recorded" as its own row
    v["fs"] = {f: fs_code(x) for f, x in (fx.get("fmt") or {}).items() if f in FULL and isinstance(x, dict)}
    scr, names = fx.get("screens") or {}, fx.get("names") or {}
    top1, sh = scr.get("top1"), names.get("share")
    v["one_screen"] = top1 is not None and top1 >= 0.8
    v["screens"] = ("use-names" if (sh or 0) >= 0.5 else "one-screen") if v["one_screen"] else None
    v0 = dp._tot(c.rows("V0"), "screenPageViews") if c.ok("V0") else None
    sv = (((c.recs.get("V") or {}).get("s") or {}).get("screenPageViews") or {}) if c.ok("V") else {}
    v["no_screens"] = bool(v0 == 0 or (sv.get("unset") or 0) >= 0.5 or (sa.get("unset") or 0) >= 0.5)
    v["names"] = None if sh is None else "none" if sh < 0.1 else "some" if sh < 0.5 else "yes"
    v["names_split"], v["names_mixed"] = names.get("classes_split"), names.get("mixed_n")
    v["views_whole"] = W("V") and W("VN") and W("VD")
    v["daily"] = daily_word(c)
    rc = fx.get("recent") or {}
    labels = ["today", "yesterday"] + ["d%d" % i for i in range(2, 10)]
    days = sorted(rc, reverse=True)
    v["recent"] = {labels[i]: (rc[d] or {}).get("state") for i, d in enumerate(days) if i < len(labels)}
    v["newest_whole"] = next((d for d in days if (rc[d] or {}).get("state") == "whole"), None)
    h = fx.get("hist") or {}
    v["views_from"], v["ads_from"] = h.get("views_from"), h.get("ads_from")
    v["first_ad"] = (h.get("first_day") or {}).get(IMP)
    v["cause"], v["old_split"] = h.get("cause") or {}, h.get("old_split")
    um = (fx.get("units") or {}).get("unit_map") or {}
    v["units1"] = {f: (um.get(f) or {}).get("one99") for f in ("banner", "native")}
    eng, adc = fx.get("eng") or {}, fx.get("adcheck") or {}
    v["eng_ok"] = eng.get("tie") is not None and abs(eng["tie"] - 1) <= 0.02 and (eng.get("unset") or 0) <= 0.02
    v["eng_attr"] = "n/a" if (adc.get("ad_views") or 0) < 100 else \
        "ad-screen-time" if (adc.get("ad_eng_per_view") or 0) >= 1 else "no-ad-screen-time"
    ok_adm = (adm or {}).get("state") == "ok"
    v["trust"] = {"imps": trust(adm.get("all")) if ok_adm else "absent",
                  "rev": trust(adm.get("all_rev")) if ok_adm else "absent"}
    ev = fx.get("ev") or {}
    v["trust_note"] = [k for k in ("ev_vs_imps", "rev_on_imp") if ev.get(k) is not None and abs(ev[k] - 1) > 0.02]
    v["clicks"] = "yes" if _ev_counts(c).get("ad_click") else "no"
    ct = (adm or {}).get("clicks") if ok_adm else None
    v["click_tie"] = ct[2] if ct else None
    v["click_ok"] = v["click_tie"] is not None and 0.8 <= v["click_tie"] <= 1.25
    v["ret_note"] = (adc.get("ret_max") or 0) >= 0.1
    v["layers"] = layers(c, fx)
    v["retention"] = (res.get("retention") or {}).get("eventDataRetention")
    v["word"] = verdict_word(v)
    return v


# ── one app ───────────────────────────────────────────────────────────────────────────────────

def probe_app(run, u, token, now, prop, opts):
    p = plan_of(u, now)
    res = {"key": u["key"], "tz": u.get("tz"), "tz_ok": tz_check.loads(u.get("tz") or "UTC"), "reads": {}}
    if p is None:
        res.update(complete=True, empty=True)
        return res
    res["win"] = win_of(p)
    if not token:
        res.update(err={"type": "auth"}, complete=False)
        return res
    ga = cp.App(token, u["property_id"], u["stream_id"], run, prop, cap=opts.get("app_calls", APP_CALLS))
    c = Ctx(ga, run, u, p, res)
    try:
        for r in READS:
            try:
                do_read(c, r.id)
            except Stop:
                raise
            except Exception as e:                   # a bug in the bookkeeping costs this read only
                c.recs.setdefault(r.id, {"ok": False})["bug"] = type(e).__name__
            if r.id == "META":
                res["retention"] = read_ret(c, token, prop)
    except Stop as e:
        res["stopped"] = str(e)
    res["win"].update({"d*": _iso(c.dstar), "Bv": [_iso(x) for x in c.bv] if c.bv else None,
                       "Ba": [_iso(x) for x in c.ba] if c.ba else None})
    res["sca"] = "SC" if c.sca == SC else "PS" if c.sca == PS else "none"
    res["facts"] = pr._safely(facts, c, fallback={})
    res["admob"] = pr._safely(admob_tie, opts.get("admob"), u, c, fallback={})
    res["verdict"] = pr._safely(verdict, c, res["facts"], res["admob"], res, fallback={})
    res["complete"] = "stopped" not in res
    res.update(calls=ga.by_kind, tokens=ga.tok, sec=round(ga.sec, 2))
    return res


# ── the counts (public), the summary (private), the run ───────────────────────────────────────

def counts(apps, run):
    kinds, tot = {}, dict.fromkeys(COUNT_KEYS, 0)
    for a in apps.values():
        for kind, r in ((a or {}).get("reads") or {}).items():
            k = kinds.setdefault(kind, dict.fromkeys(("n",) + COUNT_KEYS[1:], 0))
            if "skip" in r:
                k["skipped"] += 1
                tot["skipped"] += 1
                continue
            k["n"] += 1
            tot["reads"] += 1
            if r.get("ok"):
                for key, hit in (("ok", True), ("off", r.get("off")), ("other", r.get("fold_rows")),
                                 ("sampled", r.get("sampled")), ("trunc", r.get("trunc"))):
                    if hit:
                        k[key] += 1
                        tot[key] += 1
            elif _refused(r):
                k["refused"] += 1
                tot["refused"] += 1
    return dict(tot, apps=len(apps), complete=sum(1 for a in apps.values() if (a or {}).get("complete")),
                tzbad=sum(1 for a in apps.values() if (a or {}).get("tz_ok") is False), calls=run.calls,
                seconds=run.elapsed(), kinds=kinds)


def public_line(c, saved):
    g = lambda k: pr._int((c or {}).get(k))   # noqa: E731
    return RESULT_LINE % (g("apps"), g("complete"), g("tzbad"), g("reads"), g("ok"), g("refused"), g("off"),
                          g("other"), g("sampled"), g("trunc"), g("skipped"), g("calls"), g("seconds"),
                          "yes" if saved else "no")


def _cnt(xs):
    out = {}
    for x in xs:
        out[str(x)] = out.get(str(x), 0) + 1
    return out


def summary(apps, per_property=None):
    """The portfolio in counts (private): verdict words, the full-screen placements, screens / names, the daily store,
    Today / Yesterday, the history, the AdMob trust, the layers, retention, zones — and one row per app (no names)."""
    vals = [a for a in apps.values() if isinstance(a, dict)]
    vs = [a.get("verdict") if isinstance(a.get("verdict"), dict) else {} for a in vals]
    fx = [a.get("facts") if isinstance(a.get("facts"), dict) else {} for a in vals]
    month = lambda d: d[:7] if d else None   # noqa: E731
    u1 = {f: [v["units1"][f] for v in vs if (v.get("units1") or {}).get(f) is not None] for f in ("banner", "native")}
    out = {"apps": len(vals), "complete": sum(1 for a in vals if a.get("complete")),
           "words": _cnt(v["word"] for v in vs if v.get("word")),
           "imps_whole": sum(1 for v in vs if v.get("imps_whole")),
           "views_whole": sum(1 for v in vs if v.get("views_whole")), "eng_ok": sum(1 for v in vs if v.get("eng_ok")),
           "core_ok": sum(1 for v in vs if v.get("imps_whole") and v.get("views_whole") and v.get("eng_ok")),
           "fs": {f: _cnt(v["fs"][f] for v in vs if f in (v.get("fs") or {})) for f in sorted(FULL)},
           "one_screen": sum(1 for v in vs if v.get("one_screen")), "no_screens": sum(1 for v in vs if v.get("no_screens")),
           "names": _cnt(v.get("names") for v in vs if v.get("names")),
           "names_split": sum(1 for v in vs if v.get("names_split")),
           "names_mixed": sum(1 for v in vs if v.get("names_mixed")),
           "obf": sum(1 for f in fx if isinstance(f.get("obf"), (int, float)) and f["obf"] >= 0.05),
           "sca": _cnt((f.get("screens") or {}).get("sca") for f in fx if (f.get("screens") or {}).get("sca")),
           "daily": _cnt(v.get("daily") for v in vs if v.get("daily")),
           "recent": {k: _cnt((v.get("recent") or {}).get(k) for v in vs if v.get("recent")) for k in ("today",
                                                                                                         "yesterday")},
           "hist_cause": {k: _cnt((v.get("cause") or {}).get(k) for v in vs if v.get("cause")) for k in ("views",
                                                                                                         "ads")},
           "old_split": _cnt(v.get("old_split") for v in vs if v.get("old_split")),
           "ads_from": _cnt(month(v.get("ads_from")) for v in vs if v.get("ads_from")),
           "views_from": _cnt(month(v.get("views_from")) for v in vs if v.get("views_from")),
           "units1": {f: pr._median(x) for f, x in u1.items()},
           "admob": _cnt((v.get("trust") or {}).get("imps") for v in vs if v.get("trust")),
           "admob_rev": _cnt((v.get("trust") or {}).get("rev") for v in vs if v.get("trust")),
           "clicks": _cnt(v.get("clicks") for v in vs if v.get("clicks")),
           "app_events": sum(1 for v in vs if (v.get("layers") or {}).get("app_events")),
           "layers": {k: sum(1 for v in vs if (v.get("layers") or {}).get(k) not in (None, False, "no"))
                      for k in ("sessions", "reach", "exposure", "nvr", "version", "country", "source", "prev_class",
                                "app_events")},
           "retention": _cnt(v.get("retention") for v in vs if v.get("retention")),
           "zones": _cnt(a.get("tz") for a in vals if a.get("tz")),
           "apps_per_property": per_property or {}}
    rows = []
    for a, v, f in zip(vals, vs, fx):
        scr, adm = f.get("screens") or {}, a.get("admob") if isinstance(a.get("admob"), dict) else {}
        rows.append([a.get("key"), v.get("word"), scr.get("classes"), scr.get("top1"),
                     ((((a.get("reads") or {}).get("A") or {}).get("tie")) or {}).get("eventCount"), v.get("named_imps"),
                     v.get("fs"), v.get("names"), v.get("daily"), (v.get("recent") or {}).get("today"),
                     v.get("ads_from"), (v.get("cause") or {}).get("ads"), (v.get("units1") or {}).get("banner"),
                     adm.get("all"), adm.get("all_rev"), v.get("retention")])
    out["rows"] = rows
    return out


def rules(admob_state):
    def lab(d):
        return "SCA" if d == SCA else "firebase_previous_class (registered)" if d == PREV else d

    def filt(x):
        return list(x) if isinstance(x, tuple) else "the app's own ad-like events (EV, at most %d)" % XC_MAX \
            if x == "XC" else x
    return {"days": DAYS, "w7": W7_DAYS, "late": LATE, "lag": ga4.LAG_DAYS, "hist_days": HIST_DAYS,
            "block_days": BLOCK_DAYS, "tie_rel": TIE_REL, "tie_ok": TIE_OK,
            "floors": {"count": FLOOR_N, "usd": FLOOR_USD}, "fold_labels": sorted(FOLD),
            "fmt_aliases": [list(x) for x in FMT_ALIASES], "full": sorted(FULL), "ad_screen": AD_SCREEN.pattern,
            "ad_event_re": AD_EVENT_RE.pattern, "obf_re": OBF_RE.pattern, "data_max": DATA_MAX, "skips": list(SKIPS),
            "admob": admob_state, "ret": "Admin API dataRetentionSettings, once per property, not counted",
            "max_calls": MAX_CALLS, "app_calls": APP_CALLS, "budget_sec": BUDGET_SEC, "page_rows": PAGE_ROWS,
            "reads": [[r.id, r.prio, r.span, [lab(d) for d in r.dims], list(r.mets), filt(r.filt), r.when]
                      for r in READS]}


def run_probe(units, cid, sec, tokens, opts, now=None, clock=time.monotonic, workers=WORKERS, tick=TICK_SEC):
    """Probe every unit → the report (dict). Never raises for one app; prints the counts-only heartbeat only."""
    run = Run(opts.get("budget") or BUDGET_SEC, clock, opts.get("max_calls") or MAX_CALLS, len(units))
    now = now or datetime.now(timezone.utc)
    rt, access = dict(tokens), {}
    for owner in sorted({u.get("owner") or "" for u in units}):
        try:
            access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
        except Exception:
            access[owner] = None
    out, props = {}, {u["property_id"]: pr.new_prop() for u in units}
    lock = threading.Lock()

    def one(group):
        for u in group:
            try:
                r = probe_app(run, u, access.get(u.get("owner") or ""), now, props[u["property_id"]], opts)
            except Exception as e:                   # a bug for one app must not cost the others
                r = {"key": u["key"], "crash": type(e).__name__, "complete": False}
            with lock:
                out[u["key"]] = r
            with run.lock:
                run.done += 1

    groups = pr._groups(units)
    with sp.Beat(run, tick):
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            list(ex.map(one, groups))
    per_prop = _cnt(len(g) for g in groups)
    c = pr._safely(counts, out, run, fallback={"apps": len(out), "calls": run.calls, "seconds": run.elapsed()})
    adm_state = (opts.get("admob") or {}).get("state") or "absent"
    return {"v": 2, "probe": "ga4_activity", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rules": rules(adm_state), "counts": c, "summary": pr._safely(summary, out, per_prop, fallback={}),
            "apps": out}


def dump_guarded(report, limit=SIZE_MAX):
    """The report's text; over `limit` the biggest reads' "data" are dropped first, then the VDH / AUDH day maps (their
    per-month rows stay), until it fits — report["trimmed"] = how many were dropped."""
    text = pr._dump(report)
    if len(text) <= limit:
        return text
    size, n = len(text), 0
    recs = [r for a in (report.get("apps") or {}).values() if isinstance(a, dict)
            for r in ((a.get("reads") or {}).values()) if isinstance(r, dict)]
    data = sorted(((len(pr._dump(r["data"])), r) for r in recs if "data" in r), key=lambda x: -x[0])
    days = [(len(pr._dump(r["day"])), r) for a in (report.get("apps") or {}).values() if isinstance(a, dict)
            for k, r in ((a.get("reads") or {}).items()) if k in ("VDH", "AUDH") and isinstance(r, dict) and "day" in r]
    for sz, r, key in [(s, r, "data") for s, r in data] + [(s, r, "day") for s, r in sorted(days, key=lambda x: -x[0])]:
        if size <= limit:
            break
        r.pop(key, None)
        size -= sz
        n += 1
    report["trimmed"] = n
    return pr._dump(report)


def main(env=None, now=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    want = ap.wanted(ap.event_inputs(env).get("apps") or env.get("ACTIVITY_APPS"))
    root = env.get("ACTIVITY_DATA_DIR") or DATA_DIR
    units = cp.units_from_state(sp.load_state(root))
    if want:
        units = [u for u in units if ap.matches(u, want) or u["key"] in want]
    if not units:
        sys.exit("no GA4 app routes in the private state (or none matched)")
    adm = pr._safely(load_admob, root, units, now, fallback={"state": "error"})
    report = run_probe(units, cid, sec, tokens, {"app_calls": APP_CALLS, "admob": adm}, now=now, clock=clock)
    saved = bool(pr.write_private(OUT_PATH, dump_guarded(report), "ga4 activity probe"))
    print(public_line(report.get("counts"), saved), flush=True)
    if not saved:
        sys.exit(1)                                  # the workflow says "failed"; details stay off the public log


if __name__ == "__main__":
    main()
