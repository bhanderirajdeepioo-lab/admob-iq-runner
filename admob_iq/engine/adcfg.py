"""⚙️ Ad setting changes ("Ad setting badlav") — found in the AdMob reports, never read from Remote Config (pure: no
I/O, no clock, no prints). Owner, 16 Oct 2026: "aaj se start karo naapna" — frequency caps, splash / app-open rules,
after-call ads … changed, and the forecast missed them. Remote Config may not be read, so every change is measured
from the data the build already reads: the AdMob mediation ad-unit report (every ad source, per ad unit × day:
requests, matched requests, impressions, earnings), the AdMob country report and GA4's daily active users (DAU),
app versions and app_update users (the Uninstall store). Lab: ROI_DRIVERS V3.2a, research 5 §6 (step changes).

The series (per app; app = its AdMob app id + every selected app on the same Play package, GA4 DAU of its stream):
  per format and per material ad unit, every day d with DAU ≥ MIN_DAU and an AdMob row of the app, log scale:
      imp    impressions ÷ DAU (ads per user)          req   ad requests ÷ DAU
      match  matched ÷ requests (fill)                 show  impressions ÷ matched (preloaded ads actually shown)
  (imp = req × match × show). A unit is scanned when it carried ≥ UNIT_SHARE of the app's revenue or ≥ UNIT_FMT of
  its format's impressions in some 28-day window and lived ≥ WIN days; a step counts when its format (or unit) has
  ≥ FMT_SHARE of the app's revenue in the windows around it. The app's first SKIP_LAUNCH days are left out.
A step on day t (research 5 §6, the rule measured there): B = the WIN days before t, A1 = t … t + WIN − 1, A2 = the WIN
days after A1 (each ≥ MIN_VALID valid days); j = median(A1) − median(B), j2 = median(A2) − median(B):
      |j| ≥ ln 1.3, j2 the same sign and |j2| ≥ ln 1.2 with ≥ HOLD_FRAC of A2's days ≥ half of that (it HOLDS weeks
      3–4), |j| ≥ MAD_K × the median absolute deviation of B (not one noisy day), DAU ≥ MIN_DAU on average over B
  → "confirmed". A step whose A2 is not complete yet (t within the newest 4 weeks) needs ≥ EARLY days after it (≥
  EARLY_VALID valid, ≥ EARLY_FRAC of them ≥ half of ln 1.2 away) and the newest 3 valid days still ≥ ln 1.2 the same
  way → "checking" (naapna jaari: it becomes confirmed or reverted as the days come in). Every day that jumps is moved
  to the split that fits two flat levels best (least absolute deviation over the WIN days each side — the step's own
  day; a day whose windows straddle the step never stands for it), the hold is judged there, and one step per ±SEP days
  is kept (the largest |j|). Steps of one app within MERGE days of each other are ONE event (one setting moves several
  formats / metrics).
Causes the data explains are kept apart:
  * a release (GA4 appVersion; the Uninstall tab's 📦 markers): a version whose REL_FULL day (≥ 30 % of the day's
    active users) is within t − REL_BEFORE … t + REL_AFTER, and whose adoption the series follows at least as well as
    a sharp step (a remote setting flips in a day or two; an update ramps with its users) → "with update vX" (an ad
    change shipped in the update); an update on the same days that the shape does not follow is only noted ("near");
    an app_update surge (no version to test) on t − 3 … t + 5 counts as the cause;
  * the country mix: with the AdMob country report over both windows — a setting moves every country's ad requests
    alike, a shift in where the users are (a campaign, a store feature) moves the countries' shares of them (GA4 has
    no daily users per country). Shares moved ≥ MIX_PP (half the L1 distance) and ≥ MIX_X × their usual move → the
    step is the mix, not an ad setting: dropped. Without country rows for the windows: "n/a" (said on the event);
  * the new users (GA4's daily "new", read with the DAU): onboarding / language / permission ads are shown to NEW
    users, so an install surge lifts ads per daily user with no setting moved. An ads / requests per user step is the
    new users' when their share of DAU moved ≥ NEW_SH the way the step went AND the units of the series whose ads per
    NEW user stayed within ±NEW_FLAT and follow the new users day by day (_follows_new) carry it (the rest of the
    series moved < JUMP): kept out (dropped, cause "new users");
  * GA4's users count: when DAU moved ≥ USR_MOVE while the app's ads (every format) moved < USR_ADS or the same way
    but less (≥ USR_MOVE apart), the users count moved, not the ads — an ads / requests per user step there stands only
    when its own count, against the app's ads, moved ≥ JUMP the same way; else it is kept out (dropped, cause "GA4
    users"; a fill / show rate step, which DAU is not in, still stands). A per-user step that moved WITH the event
    counts towards its confidence only when its own count moved ≥ CORR_MIN (not just the DAU under it);
  * an eCPM-only move: eCPM is never scanned, so a price move alone is never an event (ads per user, fill and show
    rate are what a setting changes).
  The steps of an event the new users or GA4's users count explain are left out of it (recorded in dropped, "why");
  none left → no event.
The app's history starts at its first DENSE days with ≥ DENSE_MIN days of both AdMob rows and GA4 users (a few stray
report days long before do not start it, nor use up the launch skip).
Each event: date, format (+ the unit and its trigger: after-call / cold start / resume … — fc_calendar.trigger),
before → after of ads per user, requests per user, fill, show rate, the format's revenue per user and eCPM (medians of
the measured days), size, the share of the app's revenue per user it moved (rx), kind, confidence, release, country
check, status. Kind — the step's own decomposition (Δimp = Δreq + Δmatch + Δshow, at the event):
      "new placement"      units of the format turned on (ads per user before ≤ ONOFF × after) carry ≥ half the rise
      "removed placement"  units turned off (after ≤ ONOFF × before) carry ≥ half the fall
      "cap"                requests or show rate carry the change (how often an ad is asked for / shown: frequency
                           caps, splash / app-open / after-call rules)
      "SDK"                the fill (match rate) carries it (SDK, mediation, adapters, floors)
Confidence (rule-based, every input measured; the synthetic check in tests/test_adcfg_engine.py measures how often each
level is a real step): size vs the day-to-day noise (z), how well it held weeks 3–4, how many other formats / metrics /
units stepped with it, how sharp it was (a setting flips in a day or two, an update ramps over a week) − a release −
many apps on the same days → "High" ≥ CONF_HIGH, "Medium" ≥ CONF_MED, else "Low".
For the 🔮 forecast: fc_steps() = the confirmed events that moved ≥ MATERIAL of the app's revenue per user (measured:
the format's revenue per user after − before ÷ the app's before) — its back-tests label them (labels(); forecast_vd.AX
decides whether they also count as its sudden changes, held off until a back-test shows a win)."""
import math
from datetime import date, timedelta

from . import fc_calendar as FC

ONE = timedelta(days=1)
FMTS = ("app_open", "interstitial", "rewarded", "rewarded_interstitial", "banner", "native")
METRICS = ("imp", "req", "match", "show")
WIN = 14                      # days each side of a step (research 5 §6)
MIN_VALID = 10                # … valid days a window needs
EARLY = 7                     # a step in the newest 4 weeks: days after it before it shows ("checking")
EARLY_VALID = 5
JUMP = math.log(1.3)          # |median after ÷ median before| ≥ 30 %
HOLD = math.log(1.2)          # … still ≥ 20 % the same way in weeks 3–4 (and in the newest 3 days while checking)
HOLD_FRAC = 0.6               # … with ≥ 60 % of the days of weeks 3–4 ≥ half of that away (not a half-held window)
EARLY_FRAC = 0.8              # a "checking" step: ≥ 80 % of the days after it that far (a day before a step can not pass)
MAD_K = 3.0                   # |jump| ≥ 3 × the before window's median absolute deviation
SEP = 10                      # one step per ±10 days of a series (the largest)
REFINE = 7                    # the step's day re-fitted within ±7 days
MERGE = 3                     # steps of one app within 3 days = one event
SPAN = 7                      # … an event spans at most 7 days
MIN_DAU = 1000                # mean DAU over the before window
SKIP_LAUNCH = 42              # the app's first days (launch, test installs) are not scanned
MIN_REQ = 100                 # a rate's day needs ≥ 100 requests / matched
FMT_SHARE = 0.03              # a format's step counts when it carries ≥ 3 % of the app's revenue (before or after)
UNIT_SHARE = 0.05             # a material unit: ≥ 5 % of the app's revenue over its life …
UNIT_FMT = 0.15               # … or ≥ 15 % of its format's impressions
UNIT_MIN_IMP = 100            # a unit's first / last day: ≥ this many impressions (and ≥ 1 % of its daily median)
REL_SHARE = 0.05              # a version is out once ≥ 5 % of the day's active users run it (the Uninstall tab's rule)
REL_FULL = 0.30               # … and full once ≥ 30 % (research 5: the adoption a release's effect shows by)
REL_BEFORE, REL_AFTER = 5, 7  # a version's 30 % day within t − 5 … t + 7 of a step coincides with it (research 5)
REL_PAD = 21                  # the version's share kept REL_PAD days around its release (the shape test)
REL_FIT = 1.1                 # … it explains the step when its adoption fits ≤ 1.1 × a sharp step's squared error
UPD_SURGE, UPD_MIN = 3.0, 100  # an app_update surge: ≥ 3 × its 28-day median and ≥ 100 users (the Uninstall rule)
ONOFF = 0.05                  # a unit turned on / off: its ads per user before ≤ 5 % of after (or after ≤ 5 % of before)
MIX_PP = 0.10                 # country mix: the countries' shares of ad requests moved ≥ 10 points …
MIX_X = 2.5                   # … and ≥ 2.5 × their usual move between two windows before
NEW_SH = math.log(1.2)        # new users: their share of DAU moved ≥ 20 % the way the step went …
NEW_FLAT = math.log(1.15)     # … and the ads per NEW user of the units carrying the step within ±15 %
USR_MOVE = math.log(1.25)     # GA4 users count: DAU moved ≥ 25 % …
USR_ADS = math.log(1.1)       # … while the app's ads (all formats) moved < 10 % (or less, same way)
CORR_MIN = math.log(1.15)     # a co-moving per-user step counts in the confidence when its own count moved ≥ 15 %
DENSE, DENSE_MIN = 28, 21     # the history starts at the first 28 days with ≥ 21 days of AdMob rows + GA4 users
MATERIAL = 0.10               # a forecast sudden change: the format's revenue per user moved ≥ 10 % of the app's
WIDE = 3                      # ≥ 3 other apps stepped the same way within MERGE days: "many apps"
CONF_HIGH, CONF_MED = 0.65, 0.40
TRIG = {"after-call": "after-call", "cold start": "splash", "resume/bg": "resume", "onboarding": "onboarding",
        "notification": "notification", "exit/back": "exit", "in-feature": "in-app"}


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def _iso(d):
    return d.isoformat()


def _r(v, n=4):
    return None if v is None else round(float(v), n)


def med(v):
    v = sorted(v)
    n = len(v)
    if not n:
        return None
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


# ── the reports, indexed once (no copy of the rows) ─────────────────────────────────────────────────────────────────
class Source:
    """The build's own report rows (the mediation ad-unit report, the country report) and the last complete AdMob day
    `till` (iso) — each app's slice gathered on demand (one index of row numbers per report, made on first use)."""

    def __init__(self, mu_rows, cty_rows=None, till=None):
        self.mu, self.cty, self.till = mu_rows or [], cty_rows or [], str(till)[:10] if till else None
        self._ix = {}

    def _index(self, name, rows):
        if name not in self._ix:
            ix = {}
            for i, r in enumerate(rows):
                ix.setdefault(r.get("app_id"), []).append(i)
            self._ix[name] = ix
        return self._ix[name]

    def app(self, ids):
        """→ {"f": {format: {iso day: [requests, matched, impressions, earnings USD]}}, "u": {unit id: {"fmt", "name",
        "d": {iso day: [the same]}}}, "days": the iso days with any row} for the AdMob apps `ids`, days ≤ till."""
        ix = self._index("mu", self.mu)
        F, U, days = {}, {}, set()
        for aid in ids:
            for i in ix.get(aid, ()):
                r = self.mu[i]
                ds = str(r.get("report_date") or "")[:10]
                if not ds or (self.till and ds > self.till):
                    continue
                f = r.get("format") or "?"
                v = (int(r.get("ad_requests") or 0), int(r.get("matched_requests") or 0), int(r.get("impressions") or 0),
                     (r.get("estimated_earnings_micros") or 0) / 1e6)
                x = F.setdefault(f, {}).setdefault(ds, [0, 0, 0, 0.0])
                u = U.setdefault(r.get("ad_unit_id"), {"fmt": f, "name": r.get("unit_name"), "d": {}})
                y = u["d"].setdefault(ds, [0, 0, 0, 0.0])
                for k in range(4):
                    x[k] += v[k]
                    y[k] += v[k]
                days.add(ds)
        return {"f": F, "u": U, "days": days}

    def country(self, ids):
        """→ {iso day: {country: [requests, matched, impressions]}} for the AdMob apps `ids`, days ≤ till."""
        ix = self._index("cty", self.cty)
        out = {}
        for aid in ids:
            for i in ix.get(aid, ()):
                r = self.cty[i]
                ds, cc = str(r.get("report_date") or "")[:10], r.get("country")
                if not ds or not cc or (self.till and ds > self.till):
                    continue
                x = out.setdefault(ds, {}).setdefault(cc, [0, 0, 0])
                x[0] += int(r.get("ad_requests") or 0)
                x[1] += int(r.get("matched_requests") or 0)
                x[2] += int(r.get("impressions") or 0)
        return out


# ── GA4: users and releases (the Uninstall store) ───────────────────────────────────────────────────────────────────
def dau_of(store):
    """{iso day: GA4 active users} — the store's daily a1, its incomplete days left out."""
    inc = set(((store or {}).get("flags") or {}).get("incomplete_days") or {})
    return {d: int(v["a1"]) for d, v in ((store or {}).get("daily") or {}).items()
            if isinstance(v, dict) and v.get("a1") and d not in inc}


def new_of(store):
    """{iso day: GA4 new users} — the store's daily "new" (already read with a1), its incomplete days left out."""
    inc = set(((store or {}).get("flags") or {}).get("incomplete_days") or {})
    return {d: int(v["new"]) for d, v in ((store or {}).get("daily") or {}).items()
            if isinstance(v, dict) and v.get("new") and d not in inc}


def dense_start(days):
    """The first iso day of the first DENSE-day span holding ≥ DENSE_MIN of `days` (sorted iso days with both AdMob
    rows and GA4 users) — None when no span is that full."""
    ds = [_d(x) for x in days]
    k = 0
    for i, a in enumerate(ds):
        while k < len(ds) and (ds[k] - a).days < DENSE:
            k += 1
        if k - i >= DENSE_MIN:
            return days[i]
    return None


def releases_of(store):
    """The app's releases, oldest first: {"d": the first day a version reached REL_SHARE of that day's active users,
    "full": its first day at REL_FULL (None: never), "v": the version, "sh": {iso day: its share of the day's active
    users} from REL_PAD days before "d" to REL_PAD after "full" (the shape test)} — a version already out on the
    store's first day is no release — + {"d", "full": None, "v": None} for an app_update surge (≥ UPD_SURGE × its
    28-day median and ≥ UPD_MIN users, the Uninstall tab's rule) outside every version's rollout (3 days before its
    "d" … REL_AFTER after its "full") and more than REL_AFTER days after the surge before (one surge, one update)."""
    from .uninstall import NOT_SET
    vers, daily = (store or {}).get("versions") or {}, (store or {}).get("daily") or {}
    days = sorted(vers)
    first, full, tot = {}, {}, {}
    for d in days:
        t = (daily.get(d) or {}).get("a1") or sum((vers[d] or {}).values())
        tot[d] = t
        if not t:
            continue
        for v, u in (vers[d] or {}).items():
            if v in NOT_SET:
                continue
            if v not in first and u / t >= REL_SHARE:
                first[v] = d
            if v not in full and u / t >= REL_FULL:
                full[v] = d
    out = []
    for v, d in first.items():
        if days and d == days[0]:
            continue
        a, b = _d(d) - timedelta(days=REL_PAD), _d(full.get(v) or d) + timedelta(days=REL_PAD)
        sh = {}
        x = a
        while x <= b:
            k = _iso(x)
            if tot.get(k):
                sh[k] = round(((vers.get(k) or {}).get(v) or 0) / tot[k], 4)
            x += ONE
        out.append({"d": d, "full": full.get(v), "v": v, "sh": sh})
    spans = [(_d(r["d"]) - timedelta(days=3), _d(r["full"] or r["d"]) + timedelta(days=REL_AFTER)) for r in out]
    ud = sorted(d for d, v in daily.items() if isinstance(v, dict))
    hist, last = [], None
    for d in ud:
        u = daily[d].get("upd")
        prior = [x for x in hist[-28:] if x is not None]
        hist.append(u)
        if u is None or len(prior) < 14 or u < UPD_MIN or u < UPD_SURGE * (med(prior) or 0):
            continue
        D = _d(d)
        if any(a <= D <= b for a, b in spans) or (last and (D - last).days <= REL_AFTER):
            last = D if last and (D - last).days <= REL_AFTER else last
            continue                                     # a version's own rollout, or the same surge going on
        out.append({"d": d, "full": None, "v": None, "sh": None})
        last = D
    return sorted(out, key=lambda r: (r["d"], r["v"] or ""))


def _ols_sse(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    b = sxy / sxx if sxx > 0 else 0.0
    return sum((yy - my - b * (xx - mx)) ** 2 for xx, yy in zip(x, y))


def _release(rels, s, v, day_list, i, na):
    """The release that explains a step at day index i (date s) of series v: (release, explained) or (None, False).
    A version qualifies when it reached REL_FULL within s − REL_BEFORE … s + REL_AFTER (research 5: the 30 % day within
    t − 5 … t + 7 of the step); it EXPLAINS the step when the series follows its adoption at least as well
    as a sharp step does (least squares over the WIN days before and the days after: v ~ a + b · share ≤ REL_FIT × the
    two flat levels' — a remote setting flips in a day or two, an update ramps with its users). An app_update surge
    (no version) within [s − 3, s + 5] can not be shape-tested: it counts as the cause."""
    best = None
    for r in rels or ():
        if r.get("v"):
            if not r.get("full"):
                continue
            f = _d(r["full"])
            if not (s - timedelta(days=REL_BEFORE) <= f <= s + timedelta(days=REL_AFTER)):
                continue
            gap = abs((f - s).days)
        else:
            a = _d(r["d"])
            if not (a - timedelta(days=3) <= s <= a + timedelta(days=5)):
                continue
            gap = abs((a - s).days)
        key = (0 if r.get("v") else 1, gap)            # a version (shape-tested) before a bare update surge
        if best is None or key < best[0]:
            best = (key, r)
    if not best:
        return None, False
    r = best[1]
    if not r.get("v") or not r.get("sh"):
        return r, True
    xs, ys, L, R = [], [], [], []
    for k in range(max(0, i - WIN), min(len(day_list), i + na)):
        y = v[k]
        if y is None:
            continue
        xs.append(r["sh"].get(day_list[k], 0.0))
        ys.append(y)
        (L if k < i else R).append(y)
    if len(L) < MIN_VALID or len(R) < EARLY_VALID:
        return r, True
    mL, mR = sum(L) / len(L), sum(R) / len(R)
    step = sum((y - mL) ** 2 for y in L) + sum((y - mR) ** 2 for y in R)
    return r, _ols_sse(xs, ys) <= REL_FIT * step


# ── the scan ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _lg(num, den, floor=1.0):
    return math.log((num + floor) / den) if den > 0 else None


def _vals(seq, i, j):
    return [x for x in seq[max(0, i):max(0, j)] if x is not None]


def _frac(w, mb, j):
    """The share of the days of w beyond half of HOLD from mb, the way j went."""
    if not w:
        return 0.0
    return sum(1 for x in w if (x - mb) * (1 if j > 0 else -1) >= HOLD / 2) / len(w)


def _stat(v, i, n):
    """(mb, mad, j, j2 or None, early, (newest 3 days' median − mb) or None, the share of the held window's days
    beyond half of HOLD) at day index i, or None when the windows are short."""
    b = _vals(v, i - WIN, i)
    if len(b) < MIN_VALID:
        return None
    mb = med(b)
    mad = med([abs(x - mb) for x in b])
    a1 = _vals(v, i, i + WIN)
    if i + 2 * WIN <= n:
        a2 = _vals(v, i + WIN, i + 2 * WIN)
        if len(a1) < MIN_VALID or len(a2) < MIN_VALID:
            return None
        j = med(a1) - mb
        return mb, mad, j, med(a2) - mb, False, None, _frac(a2, mb, j)
    if i + EARLY > n or len(a1) < EARLY_VALID:
        return None
    tail = _vals(v, n - 6, n)[-3:]
    j = med(a1) - mb
    return mb, mad, j, None, True, (med(tail) - mb) if len(tail) == 3 else None, _frac(a1, mb, j)


def _jumps(st):
    """The jump test: |j| ≥ JUMP and ≥ MAD_K × the before window's MAD."""
    return abs(st[2]) >= JUMP and abs(st[2]) >= MAD_K * st[1]


def _holds(st):
    """The hold test, on a step's own (refined) day."""
    mb, mad, j, j2, early, tail, fr = st
    if early:                                            # every day after it (but noise) moved, the newest still
        return fr >= EARLY_FRAC and tail is not None and tail * j > 0 and abs(tail) >= HOLD
    return j2 * j > 0 and abs(j2) >= HOLD and fr >= HOLD_FRAC   # weeks 3–4: the median AND most days held


def _passes(st):
    return _jumps(st) and _holds(st)


def _fit(v, s):
    L, R = _vals(v, s - WIN, s), _vals(v, s, s + WIN)
    if len(L) < MIN_VALID or len(R) < 3:
        return None
    mL, mR = med(L), med(R)
    return sum(abs(x - mL) for x in L) + sum(abs(x - mR) for x in R)


def _refine(v, i, ok, n):
    """The step's own day near a jumping day i (ok: {day index: its stats}): the split within ±REFINE days (the same
    direction) that fits two flat levels best (least absolute deviation, WIN days each side; ties: the nearest to i).
    A day just before a step jumps too (its after window straddles the step) — the fit puts the step on its own day.
    → that day when it jumps; None when it is a day with fewer than EARLY days after it (too fresh: shown once it has
    them); else the best-fitting jumping day."""
    sg = ok[i][2] > 0
    best = best_ok = None
    for s in range(i - REFINE, i + REFINE + 1):
        st = ok.get(s)
        if st is not None and (st[2] > 0) != sg:
            continue
        c = _fit(v, s)
        if c is None:
            continue
        key = (round(c, 9), abs(s - i))
        if best is None or key < best[0]:
            best = (key, s)
        if st is not None and (best_ok is None or key < best_ok[0]):
            best_ok = (key, s)
    if best is not None and best[1] not in ok and n - best[1] < EARLY:
        return None
    return best_ok[1] if best_ok else i


def scan(v, lo=0, dau_ok=None):
    """The steps of one daily log series v (None = no value) → [(day index, j, j2 or None, mad, early)] — research 5's
    rule (module docstring): every day that jumps moved to its best-fitting jumping split (_refine: the step's own
    day), that day must HOLD (weeks 3–4, or the days so far while checking — judged there, never on a day whose
    windows straddle the step), then one per ±SEP days (confirmed before checking, then the largest |j|)."""
    n = len(v)
    ok = {}
    for i in range(max(lo, WIN), n):
        if dau_ok is not None and not dau_ok(i):
            continue
        st = _stat(v, i, n)
        if st is not None and _jumps(st):
            ok[i] = st
    cand = {s for s in {_refine(v, i, ok, n) for i in ok} if s is not None and _holds(ok[s])}
    keep = []
    for s in sorted(cand, key=lambda c: (ok[c][4], -abs(ok[c][2]), c)):
        if all(abs(s - k) > SEP for k in keep):
            keep.append(s)
    return [(s, ok[s][2], ok[s][3], ok[s][1], ok[s][4]) for s in sorted(keep)]


def _ramp(v, s, j, mb):
    """Days in transition around a step at s: of the 3-day medians on s − REFINE … s + REFINE, how many sit between
    20 % and 80 % of the way from the old level to the new (a remote setting flips in 1–2, an update ramps)."""
    k = 0
    for i in range(s - REFINE, s + REFINE + 1):
        w = _vals(v, i - 1, i + 2)
        if len(w) < 2:
            continue
        x = (med(w) - mb) / j if j else 0.0
        k += 1 if 0.2 < x < 0.8 else 0
    return k


# ── one app ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _series(day_list, dau, by_day, metrics=METRICS):
    """by_day {iso: [req, mat, imp, earn]} → {metric: [log value or None per day of day_list]}."""
    out = {m: [] for m in metrics}
    for ds in day_list:
        u = dau.get(ds)
        x = by_day.get(ds)
        if not u:
            for m in metrics:
                out[m].append(None)
            continue
        req, mat, imp = (x[0], x[1], x[2]) if x else (0, 0, 0)
        for m in metrics:
            if m == "imp":
                out[m].append(_lg(imp, u))
            elif m == "req":
                out[m].append(_lg(req, u))
            elif m == "match":
                out[m].append(_lg(mat, req, 0.5) if req >= MIN_REQ else None)
            else:
                out[m].append(_lg(imp, mat, 0.5) if mat >= MIN_REQ else None)
    return out


def _window_sums(day_list, dau, by_day, i0, i1):
    """Per-day medians over day_list[i0:i1] (days with DAU): ads, requests per user, fill, show, revenue per user,
    eCPM → dict (None when no day)."""
    ipu, rpu, fl, sh, rv, ec = [], [], [], [], [], []
    for ds in day_list[max(0, i0):max(0, i1)]:
        u = dau.get(ds)
        if not u:
            continue
        x = by_day.get(ds) or [0, 0, 0, 0.0]
        ipu.append(x[2] / u)
        rpu.append(x[0] / u)
        rv.append(x[3] / u)
        if x[0] >= MIN_REQ:
            fl.append(x[1] / x[0])
        if x[1] >= MIN_REQ:
            sh.append(x[2] / x[1])
        if x[2] >= 200 and x[3] > 0:
            ec.append(x[3] / x[2] * 1000)
    if not ipu:
        return None
    return {"imp": med(ipu), "req": med(rpu), "match": med(fl) if fl else None, "show": med(sh) if sh else None,
            "rev": med(rv), "ecpm": med(ec) if ec else None}


def _life(by_day):
    """A unit's (first, last) iso day with ≥ UNIT_MIN_IMP impressions and ≥ 1 % of its daily median."""
    imps = [x[2] for x in by_day.values() if x[2] > 0]
    if not imps:
        return None, None
    floor = max(UNIT_MIN_IMP, 0.01 * med(imps))
    ds = sorted(d for d, x in by_day.items() if x[2] >= floor)
    return (ds[0], ds[-1]) if ds else (None, None)


def _units(ad, day_list, du, rev_day):
    """The material units: {unit: {fmt, name, d, first, last, share}} — ≥ UNIT_SHARE of the app's revenue or ≥ UNIT_FMT
    of its format's impressions in some 28-day window (every 7 days; share = the largest revenue share), alive ≥ WIN
    days."""
    F = ad.get("f") or {}
    idx = [ds for ds in day_list if ds in du]
    blocks = [idx[k:k + 28] for k in range(0, max(1, len(idx) - 27), 7)] or [idx]
    arev = [sum(rev_day.get(ds, 0.0) for ds in bl) for bl in blocks]
    fimp = {f: [sum((by.get(ds) or (0, 0, 0))[2] for ds in bl) for bl in blocks] for f, by in F.items()}
    out = {}
    for uid, u in (ad.get("u") or {}).items():
        d = u["d"]
        first, last = _life(d)
        if not first or (_d(last) - _d(first)).days + 1 < WIN:
            continue
        share = fsh = 0.0
        for k, bl in enumerate(blocks):
            r = sum((d.get(ds) or (0, 0, 0, 0.0))[3] for ds in bl)
            m = sum((d.get(ds) or (0, 0, 0, 0.0))[2] for ds in bl)
            if arev[k] > 0:
                share = max(share, r / arev[k])
            fi = fimp.get(u["fmt"], [0] * len(blocks))[k]
            if fi > 0:
                fsh = max(fsh, m / fi)
        if share >= UNIT_SHARE or fsh >= UNIT_FMT:
            out[uid] = dict(u, first=first, last=last, share=share)
    return out


def _shares(cty, days):
    """The countries' shares of the app's ad requests over days (those with country rows) → ({country: share}, days)."""
    by, k = {}, 0
    for d in days:
        x = cty.get(d)
        if not x:
            continue
        k += 1
        for cc, v in x.items():
            by[cc] = by.get(cc, 0) + v[0]
    tot = sum(by.values())
    return ({cc: v / tot for cc, v in by.items()} if tot > 0 else {}), k


def _half_l1(p, q):
    return 0.5 * sum(abs(p.get(c, 0.0) - q.get(c, 0.0)) for c in set(p) | set(q))


def _mix(cty, day_list, s_i, n_after):
    """The country check of a step at day index s_i: (state, shift, usual) — state "mix" when, at some split within
    ±REFINE days of it (a users' move need not land on the very day a series shows it), the countries' shares of the
    app's ad requests moved by ≥ MIX_PP between the WIN days before and the WIN days after (half the L1 distance) AND
    by ≥ MIX_X × their usual move (the two WIN-day windows before that split; none: MIX_PP alone); "ok" else; None
    without country rows for both windows. Requests follow users (a setting moves every country's requests alike; a
    campaign or a store feature moves the countries' shares) — GA4 has no daily users per country, so this is the
    test."""
    best = None
    for t in range(s_i - REFINE, s_i + REFINE + 1):
        if t < 0 or t >= len(day_list):
            continue
        na = min(WIN, n_after + (s_i - t)) if t > s_i else min(WIN, len(day_list) - t)
        qb, kb = _shares(cty, day_list[max(0, t - WIN):t])
        qa, ka = _shares(cty, day_list[t:t + na])
        if kb < MIN_VALID or ka < min(MIN_VALID, max(EARLY_VALID, na - 2)) or not qb or not qa:
            continue
        shift = _half_l1(qb, qa)
        qp, kp = _shares(cty, day_list[max(0, t - 2 * WIN):max(0, t - WIN)])
        usual = _half_l1(qp, qb) if kp >= MIN_VALID and qp else None
        mix = shift >= MIX_PP and (usual is None or shift >= MIX_X * usual)
        key = (mix, shift)
        if best is None or key > best[0]:
            best = (key, shift, usual)
    if best is None:
        return None, None, None
    return ("mix" if best[0][0] else "ok"), best[1], best[2]


def detect(ad, dau, rels=(), cty=None, start=None, dropped=None, new=None):
    """One app → its ad setting events, oldest first (module docstring). ad: Source.app(), dau: dau_of(), rels:
    releases_of(), cty: Source.country() (or None), start: the first iso day to scan (else the app's own first day +
    SKIP_LAUNCH), new: new_of() (or None: no new-user check); dropped: a list that gets the events the country mix,
    the new users or GA4's users count explain ("why"; kept out of the events)."""
    F = ad.get("f") or {}
    have = sorted(set(ad.get("days") or ()) & set(dau))
    if not have:
        return []
    ds0 = dense_start(have) or have[0]                 # (stray report days long before do not start the history)
    have = {x for x in have if x >= ds0}
    d0, d1 = _d(min(have)), _d(max(have))
    day_list = [_iso(d0 + timedelta(days=i)) for i in range((d1 - d0).days + 1)]
    n = len(day_list)
    du = {ds: dau[ds] for ds in day_list if ds in have}       # a day counts with GA4 users AND an AdMob row
    lo = max(SKIP_LAUNCH, (_d(start) - d0).days) if start else SKIP_LAUNCH
    dv = [du.get(ds) or 0 for ds in day_list]
    pre = [0]
    for x in dv:
        pre.append(pre[-1] + x)

    def dau_ok(i):
        k = sum(1 for x in dv[max(0, i - WIN):i] if x)
        return k and (pre[i] - pre[max(0, i - WIN)]) / k >= MIN_DAU
    rev_day = {}
    for f, by in F.items():
        for ds, x in by.items():
            rev_day[ds] = rev_day.get(ds, 0.0) + x[3]
    units = _units(ad, day_list, du, rev_day)
    ser = {}
    for f, by in F.items():
        ser[("f", f)] = (by, _series(day_list, du, by))
    for uid, u in units.items():
        ser[("u", uid)] = (u["d"], _series(day_list, du, u["d"], ("imp",)))

    def share(by, i0, i1):
        r = a = 0.0
        for ds in day_list[max(0, i0):max(0, i1)]:
            if ds in du:
                r += (by.get(ds) or [0, 0, 0, 0.0])[3]
                a += rev_day.get(ds, 0.0)
        return r / a if a > 0 else 0.0
    allu = ad.get("u") or {}
    nu = {ds: new[ds] for ds in du if new and new.get(ds)}
    acnt = {0: {}, 2: {}}                               # the app's requests / impressions per day (every format)
    for by in F.values():
        for ds, x in by.items():
            if ds in du:
                acnt[0][ds] = acnt[0].get(ds, 0) + x[0]
                acnt[2][ds] = acnt[2].get(ds, 0) + x[2]

    def wmed(f, i0, i1):
        return med([y for y in (f(ds) for ds in day_list[max(0, i0):max(0, i1)] if ds in du) if y is not None])

    def ratio(f, s, na, k=EARLY_VALID):
        """log(median over the na days from s ÷ median over the WIN days before), None when either has < k days."""
        b = [y for y in (f(ds) for ds in day_list[max(0, s - WIN):s] if ds in du) if y is not None]
        a = [y for y in (f(ds) for ds in day_list[s:s + na] if ds in du) if y is not None]
        if len(b) < k or len(a) < k:
            return None
        mb, ma = med(b), med(a)
        return math.log(ma / mb) if mb and ma and mb > 0 and ma > 0 else (0.0 if not mb and not ma else None)

    def users_break(m, s, na):
        """GA4's users count moved, not the ads: DAU moved ≥ USR_MOVE while the app's ads (every format: impressions
        for an ads per user step, requests for a requests one) moved < USR_ADS, or the same way but less, ≥ USR_MOVE
        apart → (the DAU's, the app ads' log move), else None."""
        k = MIN_VALID if na >= WIN else EARLY_VALID       # (a step still checking: the days after it so far)
        u, r = ratio(du.get, s, na, k), ratio(acnt[2 if m == "imp" else 0].get, s, na, k)
        if u is None or r is None or abs(u) < USR_MOVE or abs(u - r) < USR_MOVE:
            return None
        return (u, r) if abs(r) < USR_ADS or (r * u > 0 and abs(r) < abs(u)) else None

    def new_users(lvl, key, m, s, na, j):
        """The new users carry a step: (their share's log move, the series' ads per new user's log move) when their
        share of DAU moved ≥ NEW_SH the way j went and the units of the series flat (±NEW_FLAT) per NEW user carry it
        (the rest of the series moved < JUMP) → (sh, per_new, True); measured but not theirs → (sh, per_new, False);
        None without new-user days."""
        if not nu or m not in ("imp", "req"):
            return None
        col = 2 if m == "imp" else 0
        sh = ratio(lambda ds: nu[ds] / du[ds] if ds in nu else None, s, na)
        by = (F.get(key) or {}) if lvl == "f" else units[key]["d"]
        per = ratio(lambda ds: (by.get(ds) or (0, 0, 0, 0.0))[col] / nu[ds] if ds in nu else None, s, na)
        if sh is None or per is None:
            return None
        if abs(sh) < NEW_SH or sh * j <= 0:
            return sh, per, False
        us = [u for u, x in allu.items() if x["fmt"] == key] if lvl == "f" else [key]
        flat = []
        for u in us:
            d = allu[u]["d"]
            r = ratio(lambda ds: (d.get(ds) or (0, 0, 0, 0.0))[col] / nu[ds] if ds in nu else None, s, na)
            b = wmed(lambda ds: (d.get(ds) or (0, 0, 0, 0.0))[col], s - WIN, s)
            if r is not None and b and abs(r) < NEW_FLAT and _follows_new(d, col, day_list, du, nu, s, na):
                flat.append(d)
        if not flat:
            return sh, per, False
        rest = ratio(lambda ds: max(0, (by.get(ds) or (0, 0, 0, 0.0))[col]
                                    - sum((d.get(ds) or (0, 0, 0, 0.0))[col] for d in flat)) / du[ds], s, na)
        return sh, per, rest is not None and abs(rest) < JUMP
    steps = []
    for (lvl, key), (by, sm) in ser.items():
        for m, v in sm.items():
            for s, j, j2, mad, early in scan(v, lo, dau_ok):
                na = min(WIN, n - s)
                sh = max(share(by, s - WIN, s), share(by, s, s + na))
                if lvl == "f" and sh < FMT_SHARE:
                    continue
                if lvl == "u" and sh < FMT_SHARE:              # a unit's own step: ≥ 3 % of the app's revenue there
                    continue
                st = {"lvl": lvl, "key": key, "m": m, "i": s, "j": j, "j2": j2, "mad": mad, "early": early,
                      "sh": sh, "ramp": _ramp(v, s, j, med(_vals(v, s - WIN, s))), "v": v, "why": None,
                      "u": ratio(du.get, s, na, MIN_VALID if na >= WIN else EARLY_VALID), "nu": None}
                if m in ("imp", "req"):
                    brk = users_break(m, s, na)
                    nw = new_users(lvl, key, m, s, na, j)
                    st["nu"] = [_r(math.exp(nw[0]), 3), _r(math.exp(nw[1]), 3)] if nw else None
                    if brk is not None:                  # the users count broke: the step stands only when its own
                        st["brk"] = brk                  # count (against the app's ads) moved ≥ JUMP the same way
                        own = j + brk[0] - brk[1]
                        if own * j <= 0 or abs(own) < JUMP:
                            st["why"] = "GA4 users"
                    if not st["why"] and nw and nw[2]:
                        st["why"] = "new users"
                steps.append(st)
    steps.sort(key=lambda x: (x["i"], x["lvl"], str(x["key"]), x["m"]))
    clusters = []
    for st in steps:
        c = clusters[-1] if clusters else None
        if c and st["i"] - c[-1]["i"] <= MERGE and st["i"] - c[0]["i"] <= SPAN:
            c.append(st)
        else:
            clusters.append([st])
    out = []
    for c in clusters:
        real = [x for x in c if not x["why"]]          # the steps the new users / GA4's users count do not explain
        gone = [x for x in c if x["why"]]
        if gone and dropped is not None and real:      # (kept out, for the record, beside the event that stands)
            ev = _event(gone, day_list, du, F, units, allu, rev_day, rels, cty, n)
            if ev is not None:
                dropped.append(dict(ev, why=ev["why"]))
        ev = _event(real or c, day_list, du, F, units, allu, rev_day, rels, cty, n)
        if ev is None:
            continue
        why = None if real else ev["why"]
        if real and ev["cty"] == "mix":                  # the country mix explains it: no ad setting
            why = "country mix"
        if why:
            if dropped is not None:
                dropped.append(dict(ev, why=why))
            continue
        out.append(ev)
    return out


def _follows_new(d, col, day_list, du, nu, s, na):
    """The shape test of the new-user check: a unit's ads (col: 2 impressions, 0 requests) follow the new users day by
    day — ads per NEW user flat over the WIN days before and the na after fits at least as well as a step in ads per
    daily user (two flat levels; squared error ≤ REL_FIT × it). An onboarding ad moves with every day's new users; a
    setting step on a unit every user sees is flat on each side whatever the new users did (the level test alone now
    and then calls a real step that happens to land on a new-users move "new users"; with this, almost never — and an
    onboarding unit is caught as often as before)."""
    yb, ya, yn = [], [], []
    for k in range(max(0, s - WIN), min(len(day_list), s + na)):
        ds = day_list[k]
        x = (d.get(ds) or (0, 0, 0, 0.0))[col]
        if ds not in nu or ds not in du or x <= 0:
            continue
        yn.append(math.log(x / nu[ds]))
        (yb if k < s else ya).append(math.log(x / du[ds]))
    if len(yb) < EARLY_VALID or len(ya) < EARLY_VALID:
        return False
    mn, mb, ma = sum(yn) / len(yn), sum(yb) / len(yb), sum(ya) / len(ya)
    step = sum((y - mb) ** 2 for y in yb) + sum((y - ma) ** 2 for y in ya)
    return sum((y - mn) ** 2 for y in yn) <= REL_FIT * step


def _event(c, day_list, du, F, units, allu, rev_day, rels, cty, n):
    fsteps = [x for x in c if x["lvl"] == "f"]
    if fsteps:                                            # the headline: ads per user of the format that moved the
        imp = [x for x in fsteps if x["m"] == "imp"]      # most revenue, else the biggest format step
        head = max(imp or fsteps, key=lambda x: (x["sh"] * abs(x["j"]), abs(x["j"])))
        fmt = head["key"]
    else:                                                 # a unit alone: its format did not move (ads per user the
        head = max(c, key=lambda x: (x["sh"] * abs(x["j"]), abs(x["j"])))   # same) — a placement moved inside it
        fmt = units[head["key"]]["fmt"]
        if _swap(c, units, day_list, du, F, head):
            return None
    s = head["i"]
    S = _d(day_list[s])
    na = min(WIN, n - s)
    by = (F.get(fmt) or {}) if head["lvl"] == "f" else units[head["key"]]["d"]
    wb = _window_sums(day_list, du, by, s - WIN, s)
    wa = _window_sums(day_list, du, by, s, s + na)
    if wb is None or wa is None:
        return None
    app_b = _window_sums(day_list, du, {d: [0, 0, 0, rev_day.get(d, 0.0)] for d in day_list}, s - WIN, s)
    arp_b = app_b["rev"] if app_b else None
    lg = lambda a, b: math.log(a / b) if a and b and a > 0 and b > 0 else None      # noqa: E731
    dl = {m: lg(wa[m], wb[m]) for m in METRICS}
    # the units turned on / off with it (a unit's ads per user before ≤ ONOFF × after, or after ≤ ONOFF × before)
    on, off = [], []
    for u, x in sorted(allu.items()):
        if x["fmt"] != fmt or (head["lvl"] == "u" and u != head["key"]):
            continue
        ub = _window_sums(day_list, du, x["d"], s - WIN, s)
        ua = _window_sums(day_list, du, x["d"], s, s + na)
        b0, a0 = (ub or {}).get("imp") or 0.0, (ua or {}).get("imp") or 0.0
        if a0 > 0 and b0 <= ONOFF * a0:
            on.append((a0 - b0, u))
        elif b0 > 0 and a0 <= ONOFF * b0:
            off.append((b0 - a0, u))
    on.sort(reverse=True)
    off.sort(reverse=True)
    dF = (wa["imp"] or 0.0) - (wb["imp"] or 0.0)
    big = abs(dl["imp"] or 0.0) >= JUMP / 2 or not wb["imp"] or not wa["imp"]   # (ads per user moved itself)
    if big and dF > 0 and on and sum(x for x, _ in on) >= 0.5 * dF:
        kind = "new placement"
    elif big and dF < 0 and off and sum(x for x, _ in off) >= -0.5 * dF:
        kind = "removed placement"
    else:
        part = {k: abs(dl[k] or 0.0) for k in ("req", "match", "show")}
        kind = "SDK" if max(part, key=part.get) == "match" else "cap"
    unit = None
    ustep = [x for x in c if x["lvl"] == "u" and units[x["key"]]["fmt"] == fmt]
    if head["lvl"] == "u":
        unit = head["key"]
    elif kind in ("new placement", "removed placement"):
        unit = (on if kind == "new placement" else off)[0][1]
    elif ustep:
        unit = max(ustep, key=lambda x: abs(x["j"]) * units[x["key"]]["share"])["key"]
    mstate, mixp, usual = _mix(cty, day_list, s, na) if cty else (None, None, None)
    rel, why = _release(rels, S, head["v"], day_list, s, na)
    near = rel if rel and not why else None
    rel = rel if why else None
    # the steps that moved with it (another format / metric / unit) — a per-user one only when its own count moved ≥
    # CORR_MIN (j + the DAU's move): every per-user series steps together when only the users count moved
    corr = len({(x["lvl"], x["key"], x["m"]) for x in c
                if x["m"] not in ("imp", "req") or x.get("u") is None or abs(x["j"] + x["u"]) >= CORR_MIN}
               - {(head["lvl"], head["key"], head["m"])})
    z = abs(head["j"]) / max(1.4826 * head["mad"], 0.02)
    s1 = min(1.0, max(0.0, (z - MAD_K) / 9.0))
    s2 = 0.5 if head["early"] else min(1.0, max(0.0, head["j2"] / head["j"]))
    s3 = 1.0 if corr >= 2 else 0.5 if corr == 1 else 0.0
    s4 = 1.0 if head["ramp"] <= 2 else 0.5 if head["ramp"] <= 5 else 0.0
    score = 0.35 * s1 + 0.25 * s2 + 0.2 * s3 + 0.2 * s4 - (0.2 if rel else 0.0)
    rx = ((wa["rev"] - wb["rev"]) / arp_b) if arp_b else None
    nm = allu[unit]["name"] if unit else None
    items = []
    for x in sorted(c, key=lambda x: -abs(x["j"])):
        lab = x["key"] if x["lvl"] == "f" else (units[x["key"]]["name"] or "unit")
        items.append([x["lvl"], lab, x["m"], _r(math.exp(x["j"]) - 1, 4)])
    return {"d": _iso(S), "lvl": head["lvl"], "fmt": fmt, "unit": nm, "uid": unit,
            "trig": TRIG.get(FC.trigger(nm)) if nm else None,
            "m": head["m"], "j": _r(math.exp(head["j"]) - 1, 4),
            "j2": _r(math.exp(head["j2"]) - 1, 4) if head["j2"] is not None else None,
            "st": "checking" if head["early"] else "confirmed",
            "b": {k: _r(v, 6) for k, v in wb.items()}, "a": {k: _r(v, 6) for k, v in wa.items()},
            "na": na, "sh": _r(head["sh"], 4), "rx": _r(rx, 4), "kind": kind,
            "on": [allu[u]["name"] for _, u in on], "off": [allu[u]["name"] for _, u in off],
            "rel": {"d": rel["d"], "v": rel["v"], "full": rel.get("full")} if rel else None,
            "near": {"d": near["d"], "v": near["v"], "full": near.get("full")} if near else None,
            "cty": mstate or "n/a",
            "mix": [_r(mixp, 4), _r(usual, 4)] if mixp is not None else None, "z": _r(z, 2), "ramp": head["ramp"],
            "corr": corr, "score": _r(score, 3), "items": items[:8], "why": head.get("why"),
            "nu": head.get("nu"), "du": _r(math.exp(head["u"]), 3) if head.get("u") is not None else None,
            "brk": [_r(math.exp(x), 3) for x in head["brk"]] if head.get("brk") else None}


def _swap(c, units, day_list, du, F, head):
    """A unit step whose format did not step: True when the format's ads per user stayed within ±JUMP across it (one
    unit replaced another — the same ads, a new id) and another unit of the format stepped the other way in the same
    event; such a swap is no setting change."""
    u = units[head["key"]]
    other = [x for x in c if x["lvl"] == "u" and x["key"] != head["key"] and units[x["key"]]["fmt"] == u["fmt"]
             and x["j"] * head["j"] < 0]
    if not other:
        return False
    s = head["i"]
    by = F.get(u["fmt"]) or {}
    wb = _window_sums(day_list, du, by, s - WIN, s)
    wa = _window_sums(day_list, du, by, s, s + WIN)
    if not wb or not wa or not wb["imp"] or not wa["imp"]:
        return False
    x = math.log(wa["imp"] / wb["imp"])
    if head.get("brk"):                                  # the users count broke: the format's own count against the
        x += head["brk"][0] - head["brk"][1]             # app's ads (its per-user move is the users')
    return abs(x) < JUMP


# ── confidence, many apps, statuses (the build hands the other apps' events over) ───────────────────────────────────
def finish(events, others=()):
    """Each event's "wide" (how many other apps stepped the same way within MERGE days: others = [(iso day, sign)]) and
    its confidence word (the score − 0.1 when ≥ WIDE other apps did)."""
    for e in events:
        S, sg = _d(e["d"]), (e["j"] or 0) > 0
        w = sum(1 for d, up in others if up == sg and abs((_d(d) - S).days) <= MERGE)
        e["wide"] = w
        sc = (e.get("score") or 0.0) - (0.1 if w >= WIDE else 0.0)
        e["conf"] = "High" if sc >= CONF_HIGH else "Medium" if sc >= CONF_MED else "Low"
    return events


def fc_steps(events):
    """The forecast's ad setting changes: the confirmed events that moved ≥ MATERIAL of the app's revenue per user →
    [{"at": iso day, "x": rx, "fmt"}], oldest first."""
    return [{"at": e["d"], "x": e["rx"], "fmt": e["fmt"]} for e in events
            if e.get("st") == "confirmed" and e.get("rx") is not None and abs(e["rx"]) >= MATERIAL]


def labels(origins, steps, horizons):
    """Which back-tests an ad setting change fell inside: {origin iso: {horizon: the first step's iso day}} — a step on
    day s is inside the test from T over h days when T < s ≤ T + h."""
    out = {}
    ss = sorted(_d(x["at"]) for x in steps or ())
    for T in origins:
        Td = _d(T)
        for h in horizons:
            hit = next((s for s in ss if Td < s <= Td + timedelta(days=int(h))), None)
            if hit is not None:
                out.setdefault(T, {})[int(h)] = _iso(hit)
    return out


def weekly(ad, dau, fmts=None):
    """The page's chart: ads per user (impressions ÷ DAU) per format by week (Monday), every week with ≥ 4 days of
    both, from the history's start (dense_start: stray report days before it left out), the empty weeks at either end
    trimmed → {"d0": the first Monday with a value, "f": {format: [value or None per week]}} (None: no week)."""
    F = ad.get("f") or {}
    days = sorted(set(ad.get("days") or ()) & set(dau))
    if not days:
        return None
    ds0 = dense_start(days) or days[0]
    days = [x for x in days if x >= ds0]
    m0 = _d(days[0]) - timedelta(days=_d(days[0]).weekday())
    nw = (_d(days[-1]) - m0).days // 7 + 1
    out = {}
    for f in (fmts or sorted(F)):
        by = F.get(f) or {}
        num, den, k = [0.0] * nw, [0.0] * nw, [0] * nw
        for ds in days:
            w = (_d(ds) - m0).days // 7
            num[w] += (by.get(ds) or [0, 0, 0, 0.0])[2]
            den[w] += dau[ds]
            k[w] += 1
        out[f] = [_r(num[w] / den[w], 4) if k[w] >= 4 and den[w] > 0 else None for w in range(nw)]
    full = [w for w in range(nw) if any(v[w] is not None for v in out.values())]
    if not full:
        return None
    a, b = full[0], full[-1] + 1
    return {"d0": _iso(m0 + timedelta(days=7 * a)), "f": {f: v[a:b] for f, v in out.items()}}
