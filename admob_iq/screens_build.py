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
data/app_store_ids.json (sibling AdMob app ids of the same Play package).

Files (sorted compact JSON, deterministic gzip — no mtime / file name, level GZ_LEVEL — written only when their bytes
changed, known from the out-file index in the cache dir; day arrays from the app's first day d0, shards from the 1st of
their month; a month's shard is not even built while its inputs are unchanged):
  site/scr_all.json.gz          every app's day arrays over its display items + status words (the tab's first load)
  site/scr_<key>.json.gz        the app page: screens, units, per-day core rows, AdMob per unit (blended), row details
  site/scr_l_<key>.json.gz      the app's layers: per-day small-group records, versions, month sums, shard list, the
                                developer report text (English, no money)
  site/scr_r_<key>_<YYYYMM>.json.gz / scr_c_<key>_<YYYYMM>.json.gz   one month of versions / countries over the display
                                items (the page loads only a picked period's edge months)
and the pointer dashboard["scr"] = {"v", "file", "fv", "apps": {app id: {"key", "v", "vl", "from", "ft"}}}. Write order:
shards → scr_l → scr_<key> → scr_all → pointer. A broken app loses its own files and pointer entry ("failed"); a broken
or too big shard costs only that month (listed in scr_l "failed" / "big"); file 2 and scr_all never depend on a shard.

Calendar: td = the property's today; ft = td − 2 (GA4 still adds to the last two days: "GA4 data till ft"). GA4 days are
the property's (UTC on every live property); AdMob days are the report zone's (IST): GA4 day D = the overlapped share of
AdMob days D and D+1 (0.7708 / 0.2292 for UTC vs IST), only when both are ≤ latest_complete.

Status (fixed window, the picker never changes it — the First open precedent): W = the 10 final days ending ft, N = the
28 final days before W; the z gate allows for each row's own day-to-day spread (overdispersion from N) and both halves of
W must agree. Cause: a stopped / changed ad unit first, else an exact LMDI split of the change in ads per visit over the
row's units — tie (GA4 ÷ AdMob), share of the unit on this screen, show rate, fill, requests per app visit, the screen's
share of visits — whose terms add up to the change exactly (no leftover is ever named a cause).

run(dashboard, data_dir, out_dir, s) → the _headers no-store paths (["/scr_*"], ONE splat rule) or [] (no store / switched
off / a failure: every scr_ file removed, no pointer). Failure-isolated; ONE counts-only line. A store month file that
cannot be read or parsed is never skipped silently: counted ("broken N"), ONE "scr store skipped: <Type>" health line per
build, and the days it held ship the state "x" (store file unreadable), never "not read yet". Read-only history check:
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
V = 1
MAX_GZ = 8 * 1024 * 1024
STORE_DIR = "ga4_screens"
CACHE_DIR = "ga4_screens_cache"
CACHE_V = 2                            # 2: a "p" day with GA4 grouped ≤ FOLD_OK is cached as "w" (older caches re-derived)
GZ_LEVEL = 6                           # the scr_ files' gzip level (9 took ~4× the time for files under a tenth smaller)
IDX_V, IDX_APP, IDX_ALL = 1, "shards.json", "all.json"      # the out-file index (_idx_path)
SHARD_V = 1                            # bump when shard_body's output changes for the same inputs (a shard key part)
GROUPS = {"core": ("t", "v", "w", "a"), "small": ("k", "e", "uV", "uA", "s", "x", "nV", "nA"),
          "ver": ("rV", "rA"), "cc": ("cV", "cA")}
READ_IDS = ("t", "v", "w", "a", "nV", "nA", "rV", "rA", "cV", "cA", "k", "e", "s", "x", "uV", "uA")
OK_ST = ("w", "p")                     # a record whose rows are usable (whole, or whole with a GA4 grouped part)
ST_CH = frozenset("wpost")             # the fetch's day states; the build adds "x" (its store month file cannot be read)
FOLD_OK = 0.02                         # a "p" day counts for status / cause only while GA4 grouped ≤ 2 % of it (§0.3: a
                                       # screen's ads moved into "(other)" would read as a drop; the tie tolerance)

# ── status (§3.2; thresholds change only here, then the backtest) ──
W_DAYS, N_DAYS, HALF = 10, 28, 5
MIN_A_W = 5                            # whole days of the row's ads in W, else N/A "GA4 sampled"
MIN_N, MIN_W, MIN_VN, MIN_E = 14, 7, 300, 30
LOG_SHIFT, LOG_MAX = 0.05, 0.30        # unset-class / notset-format share: moved > 5 points or > 30 % in W
ALLF_SHARE = 0.05                      # notset formats above this in N or W: screen rows judged on all formats
APP_SHARE = 0.03                       # a row counts for the app status with ≥ 3 % of its kind's N ads
PHI_MIN_E = 5
WATCH_Z = 3                            # Watch / Better need |z| ≥ 3 too (the real-store backtest: |z| 2–3 flagged too many
                                       # marginal rows); Worse: z ≤ −3 and score < 80
# ── cause (§3.3) ──
STOP_REQ, STOP_FRAC, STOP_SHARE = 50, 0.10, 0.50
TERM_MIN, MIXED = 0.10, 0.6
TIE_LO, TIE_HI, TIE_MIN_N = 0.8, 1.25, 100
UNTIED_SHARE = 0.5                     # units with no AdMob id + units whose tie is outside TIE_LO–TIE_HI hold more than
                                       # this share of the row's ads → not measurable, named by the bigger part
ADM_MIN_DAYS = 7
FU_MIN_W, FU_MIN_N = 7, 14
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
    judge on (_whole) and ships "w" — the page's coverage counts exactly the days the build judges on; above it, "p"."""
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


def _oldest(meta, i):
    """Read i's oldest filled day (the fetch's backfill cursor in meta reads), or None."""
    reads = meta.get("reads") if isinstance(meta, dict) else None
    r = reads.get(i) if isinstance(reads, dict) else None
    o = r.get("oldest") if isinstance(r, dict) else None
    return o if isinstance(o, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", o) else None


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


def mark_lost(app, broken, st_of):
    """State "x" (store file unreadable) on the days a broken store month file may have held — only where no other
    record (the recent window) gave the day its own state: the page says why, never "not read yet"."""
    for grp, m in sorted({(g, m) for g, m, _ in broken or ()}):
        for i in GROUPS.get(grp, ()):
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
    """An app's AdMob side: per ad unit id {IST day: [req, matched, imp]}, blended onto GA4 days."""

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
                    v = [_i(row[3]), _i(row[4]), _i(row[2])]
                except (IndexError, TypeError, ValueError):
                    continue
                x = e["d"].setdefault(dd, [0, 0, 0])
                for j in range(3):
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
        real = sorted(d for d, r in days.items() if r)
        self.d0 = real[0] if real else None
        # a core month file that cannot be read (broken: [(grp, month, error type)]) keeps its days on the calendar
        # (state "x"), from the reads' oldest filled day: the history never silently starts later
        for grp, m, _ in broken or ():
            if grp != "core":
                continue
            for i in GROUPS["core"]:
                sp = lost_span(meta, i, m, self.td)
                if sp and (self.d0 is None or sp[0] < self.d0):
                    self.d0 = sp[0]
        self.days = _span(self.d0, self.td) if self.d0 else []
        self.final = [d for d in self.days if _d(d) <= self.ft]
        self.st = {i: {} for i in READ_IDS}
        self.ta, self.tv, self.vis, self.views, self.ads, self.w = {}, {}, {}, {}, {}, {}
        self.whole = {"v": set(), "a": set(), "w": set()}       # days a status row may use (GA4 grouped ≤ FOLD_OK)
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
        ft = _d(ft or self.ft)
        w = _span(ft - timedelta(days=W_DAYS - 1), ft)
        n = _span(ft - timedelta(days=W_DAYS + N_DAYS - 1), ft - timedelta(days=W_DAYS))
        return w, n

    def allf(self, ft=None):
        """Notset formats above 5 % of the app's ads in N or W → screen rows are judged on ALL formats (copy days
        included: an unconfirmed copy is the "Format not recorded" bucket, judged with the rest)."""
        w, n = self.windows(ft)
        return any((self._ns_fmt(ds, dup=True) or 0) > ALLF_SHARE for ds in (w, n))

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


# ── status (§3.2) ────────────────────────────────────────────────────────────────────────────

def _score(a, v, rn):
    return round(100 * (a / v) / rn) if v and rn else None


def judge(series, w_days, n_days, guard=None, what="inline", full=False):
    """A row's {day: (V, A)} → its status {word, why, score, z, h, VW, AW, VN, AN, dW, dN, rw, rn}. First that applies:
    N/A GA4 sampled · N/A Logging changed · N/A No ads · N/A Ads started · Too early · Worse (score < 80, z ≤ −3, both
    halves < 90) · Watch (score < 90, z ≤ −WATCH_Z, both halves < 95) · Better (score > 110, z ≥ WATCH_Z, both halves
    > 105) · Normal."""
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
        return done("N/A", "GA4 sampled — %d whole days of %s ads in the last %d" % (len(W), what, W_DAYS))
    if guard:
        return done("N/A", guard)
    noun = "full-screen" if full else what
    if AN == 0 and AW == 0:
        return done("N/A", "No %s ads" % noun)
    if AN == 0:
        return done("N/A", "Ads started — no %s ads in the %d days before" % (noun, N_DAYS))
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


def app_status(rows):
    """rows: [(status, kind, N-window ads)] → [word, why, worse n, watch n]: the worst (Worse, Watch, Better, Normal)
    among judged rows holding ≥ 3 % of their kind's N ads; else Too early / N/A."""
    tot = {}
    for st, k, an in rows:
        tot[k] = tot.get(k, 0) + (an or 0)
    worse = sum(1 for st, k, an in rows if st["word"] == "Worse")
    watch = sum(1 for st, k, an in rows if st["word"] == "Watch")
    elig = [st for st, k, an in rows if st["word"] in JUDGED and tot.get(k) and (an or 0) >= APP_SHARE * tot[k]]
    if elig:
        best = min(elig, key=lambda s: STATUS_RANK[s["word"]])
        n = sum(1 for s in elig if s["word"] == best["word"])
        return [best["word"], "%d row%s %s" % (n, "" if n == 1 else "s", best["word"]), worse, watch]
    if any(st["word"] == "Too early" for st, k, an in rows):
        return ["Too early", "history still short", worse, watch]
    if rows:
        return ["N/A", rows[0][0]["why"], worse, watch]
    return ["N/A", "no screens yet", worse, watch]


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


def first_bad_day(series, final_days, rn):
    """The first final day from which the daily rate stays < 90 % of rate_N (to the last final day), or None."""
    if not rn:
        return None
    fb = None
    for d in reversed(final_days):
        if d not in series:
            continue
        v, a = series[d]
        if v and a / v < BAD_RATE * rn:
            fb = d
        else:
            break
    return fb


# ── the developer report (§3.4: English, no money) ───────────────────────────────────────────

def _n(v):
    return "—" if v is None else "{:,}".format(int(round(v)))


def _p(v):
    return "—" if v is None else "%.2f" % v


def row_report(app, label, what, st, cz, series, fbd, ver=None, cc=None, versions=None):
    """One judged row → its report block (text). label: the Activity class or "format · trigger"; what: "screen" /
    "full-screen trigger"."""
    w, n = app.windows()
    rn, rw = st.get("rn"), st.get("rw")
    out = ["== %s (%s) ==" % (label, what),
           "Status: %s — %s (score %s)" % (st["word"], st["why"], st["score"] if st["score"] is not None else "—"),
           "Window W %s – %s, normal N %s – %s (GA4 days, UTC)" % (w[0], w[-1], n[0], n[-1]),
           "Visits: W %s · N %s" % (_n(st["VW"]), _n(st["VN"])),
           "Ads per 100 visits: W %s · N %s" % (_fmt100(rw), _fmt100(rn)),
           "First bad day: %s" % (fbd or "—"),
           "Last 14 GA4 days (date, visits, ads, ads/100):"]
    for d in _span(app.ft - timedelta(days=13), app.ft):
        v, a = series.get(d, (None, None))
        out.append("  %s  %s  %s  %s" % (d, _n(v), _n(a), _fmt100(a / v) if v else "—"))
    if ver:
        out.append("Version: %s" % ver)
    if cc:
        out.append("Countries (top 3 by change): %s" % cc)
    if cz.get("units"):
        out.append("Units, normal N → last 10 days W (AdMob requests/day · fill · show · GA4 ÷ AdMob):")
        for ui, rqw, rqn, fw, fn, sw, sn, tw, tn in cz["units"]:
            u = app.units[ui]
            out.append("  %s (%s) %s · requests/day %s → %s · fill %s → %s · show %s → %s · GA4 ÷ AdMob %s → %s" % (
                u[0] or u[3], ", ".join(u[2]) or "no AdMob id", u[1], _n(rqn), _n(rqw), _p(fn), _p(fw), _p(sn), _p(sw),
                _p(tn), _p(tw)))
    out.append("Cause: %s" % (cz.get("cause") or "—"))
    if cz.get("terms"):
        out.append("  Terms (%% of normal ads per visit): %s" % " · ".join(
            "%s %+.1f" % (TERM_LABEL[k], cz["terms"][k]) for k in TERMS if cz["terms"].get(k)))
    checks = []
    c = cz.get("cause") or ""
    for lab, txt in CHECK.items():
        if lab in c and txt not in checks:
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
        out.append("Acceptance check: After the fix ships: ads per 100 visits on %s ≥ %.1f for 3 final days."
                   % (label, 0.9 * rn * 100))
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
    return {"v": V, "key": app.key, "m": m, "dims": dims, "items": app.ditems, "days": out}


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
        items, its day span (d0 … today), the file / cache / shard-code versions and the size limit."""
        app = self.app
        rk = _sha(_raw({d: e for d, e in self.recent.items() if d[:7] == m})) if self._has_recent(m) else ""
        lo, hi = max(app.d0 or "", m + "-01"), min(_month_end(m), _iso(app.td))
        return _sha(_raw([V, CACHE_V, SHARD_V, MAX_GZ, self.grp, m, src, rk, dk, app.ditems, lo, hi]))[:20]

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


def small_days(app, data_dir, recent, broken=None, counts=None):
    """The small group per day as scr_l's day records — each day's sorted compact JSON (bytes: classes → file 2 screen
    indexes, layer ads without a format on a confirmed copy day → null; spliced into scr_l unparsed) — its state chars
    and the click tally (a month file that cannot be read → `broken`). A store month is encoded once: its day records,
    states and clicks are cached under the store file's sha1 (data/ga4_screens_cache/<key>/small_<YYYY-MM>.json.gz) with
    its classes in the order the encoding met them and the screen indexes they got; a cached month registers those
    classes in that order — the indexes an uncached build gives — and is used only when they match (else encoded again)."""
    ids = GROUPS["small"]
    frag, st = {}, {i: {} for i in ids}
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
        if c is not None and [c.get("dk"), c.get("lo"), c.get("hi")] == [dk, lo, hi]:
            cls = c.get("cls") or []
            for x in cls:
                _si(app, x)
            if [app.six.get(x) for x in cls] == c.get("map"):
                frag.update((d, t.encode("utf-8")) for d, t in c["days"].items())
                for i, by in (c.get("st") or {}).items():
                    st.setdefault(i, {}).update(by)
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
        seen, mf, mst, ck = {}, {}, {i: {} for i in ids}, [0, 0]
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
            if e:
                mf[d] = _raw(e)
        _cache_put(data_dir, app.key, "small", m, {"v": CACHE_V, "src": src, "dk": dk, "lo": lo, "hi": hi,
                                                   "cls": list(seen), "map": [app.six[x] for x in seen], "st": mst,
                                                   "ck": ck, "days": {d: t.decode("utf-8") for d, t in mf.items()}})
        frag.update(mf)
        for i, by in mst.items():
            st[i].update(by)
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
        if e:
            frag[d] = _raw(e)
    return frag, st, clicks


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
    """A small-group record → the same record with classes as screen indexes (formats normalized). seen (a dict): gets
    each class in the order met (the small cache's registration order)."""
    e = {k: v for k, v in rec.items() if k != "r"}
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


def statuses(app, ft=None):
    """Every row of the app → [(row id, row, label, kind, item index | None, series, status)] and the app status."""
    w, n = app.windows(ft)
    allf = app.allf(ft)
    gs, gt = app.guard(ft, True), app.guard(ft, False)
    tix = {c: i for i, c in enumerate(app.top)}
    out = []
    for c in app.screens:
        if kind(c) != "s":
            continue
        row = ("s", c, allf)
        ser = app.screen_series(c, allf)
        st = judge(ser, w, n, gs, "all-format" if allf else "inline")
        out.append(("s%d" % app.six[c], row, c, "s", tix.get(c), ser, st))
    for gi, (f, lab, _) in enumerate(app.trig):
        ser = app.trig_series(gi)
        st = judge(ser, w, n, gt, f, full=True)
        out.append(("t%d" % gi, ("t", gi), "%s · %s" % (f, lab), "fs", app.fs0 + gi, ser, st))
    ast = app_status([(st, k, st["AN"]) for _, _, _, k, _, _, st in out])
    return out, ast


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
    rows, ast = statuses(app)
    report_rows = {rid: row for rid, row, _, _, _, _, st in rows if st["word"] in ("Worse", "Watch")}
    causes = {}
    for rid, row, label, k, ii, ser, st in rows:
        if st["word"] in JUDGED:
            causes[rid] = cause(app, row, st)
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
    sdays, sst, clicks = small_days(app, data_dir, recent, broken, counts)
    # a store month file that cannot be read: its days ship "x" (file 2's day states and scr_all's state strings)
    mark_lost(app, broken, lambda i: app.st[i] if i in GROUPS["core"] else sst[i] if i in GROUPS["small"] else
              lay["ver"].st[i] if i in GROUPS["ver"] else lay["cc"].st[i])
    w, n = app.windows()
    fbd, rtext = {}, {}
    for rid, row, label, k, ii, ser, st in rows:
        if st["word"] in JUDGED:
            fbd[rid] = first_bad_day(ser, app.final, st["rn"])
        if rid in report_rows:
            rtext[rid] = row_report(app, label, "screen" if row[0] == "s" else "full-screen trigger", st,
                                    causes.get(rid) or {}, ser, fbd.get(rid), _ver_line(app, row, order, wsame, prev),
                                    _cc_line(lay["cc"].wsum.get(rid)), {v: ver[v]["first"] for v in ver})
    dq, dql = dq_items(app, clicks)
    head = ["Screens report · app %s · GA4 data till %s (GA4 days, UTC)" % (key, _iso(app.ft)),
            "Status: %s — %s (%d Worse, %d Watch)" % tuple(ast)]
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
                      "cause": cz.get("cause", ""), "terms": cz.get("terms"), "units": cz.get("units"),
                      "fbd": fbd.get(rid)}
    notes = {"zone": "assumed" if app.adm.assumed else ("account" if app.adm else "none"),
             "admob": "ok" if app.adm else "none", "allf": 1 if app.allf() else 0,
             "runs": [[r["a"], r["b"], 1 if r["ok"] else 0, 1 if r["open"] else 0] for r in app.runs],
             "w": [w[0], w[-1]], "n": [n[0], n[-1]], "dq": dq}
    # scr_l (after the shards; the screens list is final once the small records are encoded)
    lbody = {"v": V, "key": key, "app_id": app.aid, "d0": app.d0, "items": app.ditems, "days": _SPLICE,
             "ver": ver, "ver_order": order, "ver_m": lay["ver"].msum(), "cc_m": lay["cc"].msum(),
             "shards": {"r": lay["ver"].shards, "c": lay["cc"].shards},
             "big": {"r": sorted(lay["ver"].big), "c": sorted(lay["cc"].big)},
             "failed": {"r": sorted(lay["ver"].failed), "c": sorted(lay["cc"].failed)},
             "report": {"app": app_text, "rows": rtext}}
    body2 = {"v": V, "key": key, "app_id": app.aid, "ft": _iso(app.ft), "td": _iso(app.td), "d0": app.d0,
             "screens": [[c, kind(c)] for c in app.screens], "units": app.units, "trig": app.trig, "days": days2,
             "adm": adm, "rows": rows2, "notes": notes}
    # scr_all entry
    allf = app.allf()
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
    status = {}
    for rid, row, label, k, ii, ser, st in rows:
        if ii is not None:
            cz = causes.get(rid) or {}
            status[str(ii)] = [st["word"], st["why"], st["score"],
                               cz.get("cause", "") if st["word"] in ("Worse", "Watch") else ""]
    bf = {i: [r.get("oldest"), bool(r.get("done"))] for i, r in ((meta.get("reads") or {}).items())
          if isinstance(r, dict)}
    entry = {"key": key, "ft": _iso(app.ft), "td": _iso(app.td), "d0": app.d0, "items": app.items, "vis": vis,
             "V": V_, "A": A_, "ta": ta, "st": stall, "bf": bf, "status": status, "app": ast, "dq": dq}
    if allf:
        entry["allf"] = 1
    c = counts
    c["rows"] += len(rows)
    c["judged"] += sum(1 for r in rows if r[6]["word"] in JUDGED)
    c["worse"] += ast[2]
    c["watch"] += ast[3]
    return {"app": app, "body2": body2, "lraw": _splice(lbody, [sdays.get(d) for d in app.days]), "entry": entry,
            "keep": keep,
            "seen": lay["ver"].seen | lay["cc"].seen}


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
        counts = {"rows": 0, "judged": 0, "worse": 0, "watch": 0, "big": 0, "failed": 0, "cached": 0}
        apps, entries, keep = {}, {}, set()
        bad = []                                    # (key, group, month, error type): store month files not readable
        for key in store_keys(data_dir):
            meta = load_meta(data_dir, key)
            if not meta or gu.file_key(str(meta["app_id"])) != key:
                continue
            aid = str(meta["app_id"])
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
        fv = None
        if apps:
            ia = _idx_path(data_dir)
            aidx = _idx_load(ia)
            aidx0 = {k: dict(v) for k, v in aidx.items()}
            ha = _put(out_dir, ALL_FILE, _raw({"v": V, "apps": entries}), aidx)
            if ha is None:
                counts["big"] += 1
                apps = {}
            else:
                keep.add(ALL_FILE)
                fv = ha[:12]
            _idx_save(ia, {k: v for k, v in aidx.items() if k == ALL_FILE}, aidx0)
        _clean(out_dir, keep)
        line = "scr: apps %d, rows %d, judged %d, worse %d, watch %d, files %d, too big %d, failed %d, broken %d, " \
               "unmapped %d, cached %d" % (len(apps), counts["rows"], counts["judged"], counts["worse"],
                                           counts["watch"], len(keep), counts["big"], counts["failed"], nbad,
                                           unmapped_pairs(dashboard), counts["cached"])
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


# ── the backtest (§3.6, read-only) ───────────────────────────────────────────────────────────

def backtest(data_dir, dashboard=None, now=None, out=None):
    """For every week of each app's filled history: the §3.2 rule at that week's end → Worse / Watch / Better counts per
    app per week + the status flip rate (rows whose word changed from the week before). Reads only; prints a table
    (12-hex keys and counts) and returns {key: {"weeks": [[ft, worse, watch, better, judged]], "flip": rate}}."""
    out = out or sys.stdout
    now = now or datetime.now(timezone.utc)
    by_id = _by_id(data_dir)
    res = {}
    for key in store_keys(data_dir):
        meta = load_meta(data_dir, key)
        if not meta:
            continue
        app = App(meta, core_days(data_dir, key, meta, load_recent(data_dir, key)), now, dashboard or {}, by_id)
        if not app.d0:
            continue
        weeks, prev, flips, comps = [], None, 0, 0
        ft = app.ft
        anchors = []
        while ft - timedelta(days=W_DAYS + N_DAYS - 1) >= _d(app.d0):
            anchors.append(ft)
            ft -= timedelta(days=7)
        for a in reversed(anchors):
            rows, _ = statuses(app, a)
            words = {rid: st["word"] for rid, *_, st in rows}
            cnt = [sum(1 for w in words.values() if w == x) for x in ("Worse", "Watch", "Better")]
            weeks.append([_iso(a)] + cnt + [sum(1 for w in words.values() if w in JUDGED)])
            if prev is not None:
                for rid, w_ in words.items():
                    if rid in prev:
                        comps += 1
                        flips += prev[rid] != w_
            prev = words
        res[key] = {"weeks": weeks, "flip": round(flips / comps, 4) if comps else None}
        print("%s  weeks %d  flip %s" % (key, len(weeks), res[key]["flip"]), file=out)
        for wk in weeks:
            print("  %s  worse %d  watch %d  better %d  judged %d" % tuple(wk), file=out)
    return res


def main(argv):
    if not argv or argv[0] != "backtest" or len(argv) < 2:
        print("usage: python -m admob_iq.screens_build backtest <data_dir> [--dashboard <dashboard.json.gz>]",
              file=sys.stderr)
        return 2
    dash = None
    if "--dashboard" in argv:
        p = argv[argv.index("--dashboard") + 1]
        raw = _read_gz_bytes(p) if p.endswith(".gz") else open(p, "rb").read()
        dash = _json(raw) if raw else None
    backtest(argv[1], dash)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
