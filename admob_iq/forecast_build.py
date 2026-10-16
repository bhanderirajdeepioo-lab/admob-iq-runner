"""🔮 Forecast — the build step, inside the ROI step (roi_build.app_step hands it the app's install days, AdMob revenue,
Google Ads spend and the install-day file it already has). Owner, 14 Oct 2026: revenue / spend / profit / breakeven for
the next months from the app's own past, AI back-testing that learns from its misses, the start of the real run picked
by itself (the trial / organic first days left out) and changeable from the dashboard (config/forecast_starts.json).

The engine: FORECAST_ENGINE=vd (default; engine/forecast_vd.py, the forecast tournament's winner) or v0 (engine/forecast.py,
the earlier one) — a rollback is that one variable. Each stored file says which engine made it (v 2 = vd, v 1 = v0); a
file of the other engine is kept (and recomputed with its own engine) until this one has re-made it.

Per app, every build: the forecast with the stored settings on today's data (cheap). At most once a day (EVERY_H) and
within the build's BUDGET_SEC, the settings are re-tuned on back-tests from the newest year of origins (vd: only its
three mix weights, and only when the budget left is > TUNE_MARGIN × the app's last tune seconds; an app left over keeps
its stored settings) → calibrate (bias, P10–P90, accuracy of every test and of the normal ones, how often a sudden
change hit) → the forecast from the last complete day, 180 days, in three parts (old users / organic installs / paid
installs at the last 7 days' spend) so the page's spend slider is exact; the bias correction folded into the days.
🔎 The verified horizon (vd; owner, 15 Oct: "verified horizon, khud badhe"): the chosen setting is also back-tested on
the horizon grid (forecast_vd.HG: every 14 days from 30 to 352, + 90 / 180 / 365; the tune's fits reused, its origins
+ the two before them for 352 / 365 only), each grid horizon calibrated on its own tests; N = the longest with
≥ MIN_TESTS (grows ~14 days every 2 weeks as the app ages); the page's chips = the standard 30 / 90 / 180 / 365 below N
+ N; the forecast then reaches max(180, N) days and every chip's total is corrected by its own bias (30 / 90 / 180 and
their numbers exactly as before: the tune and its objective are untouched); fc["hz"] = N, the chips, the day each
locked horizon unlocks, the chart's monotone band across horizons, each chip's tests (horizon()).
Kept for good in the private repo (data/forecast/<key>.json): the settings, the learning log (what changed and why, the
newest LOG_KEEP), and every day's own forecast of the next 30 / 90 / 180 days (+ its other chips, "px") — once those
days have happened the page shows that live error too (the real check, beyond the back-tests).
Engine vd with the app's Google Ads country weeks (roi_build hands them over, + every store's country block pairs once
per build): the page's "Budget by country" planner (fc.plan: each country's installs per $ and CPI rise; revenue per $
at 30 / 90 days each country's own from GA4's paid cells where it won the app's own back-test, scaled to the
forecast's own total; past 90 one value) — the
forecast's own paid installs stay spend × per_usd (STRUCT cs 0: the country model did not win there at the shares a
forecast can know).
📅 The eCPM calendar (build_static hands its seasons over through roi_build.start(cal=…)): engine vd's STRUCT cal decides
whether the forecast uses it (held off: it did not win the Nov–Feb back-test); the page gets the coming event weeks
with their measured effects either way (fc["fcal"]), Ramadan / Diwali measured once (shown, never in the forecast), and
each app's weekday rhythm per ad trigger on its daily line (fcal["wk"]; every 30 / 90 / 180-day total unchanged — the
daily forecast came closer on most apps with it, lab 9).
data/forecast/state.json, refreshed at the end: the portfolio's month-of-year season and band ratios ("bandr": each GA4
install-age band's revenue per active user ÷ the band before's, the median over the apps, per Monday — engine vd's prior
for a band an app has few users in) + the engine's fixed structure ("vd_struct").
"""
import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone

from .engine import fc_calendar as FC
from .engine import forecast as F
from .engine import forecast_vd as VD

DIR = "forecast"
V = 2                                   # the stored files' version = the engine that made them: 2 vd, 1 v0
ENGINES = {1: F, 2: VD}
BUDGET_SEC = 120
EVERY_H = 20
TUNE_MARGIN = 1.3                       # vd: a re-tune starts only with > this × the app's last tune seconds left
TUNE_GUESS_SEC = 30.0                   # … (its first tune: this guess)
LOG_KEEP = 30
LIVE_KEEP = 400
CHECK_KEEP = 20                         # the page's live checks: the newest this many per horizon
FIT_MIN = 0.05                          # a chip outside 30 / 90 / 180: the lowest day factor its correction may use
FIT_TOL = 1e-6                          # … and how close its shown total must be to its calibration (else dropped)
HIST_DAYS = 180
ULAG_INDEX = {L: i for i, L in enumerate(F.ULAGS)}


def _d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def _iso(d):
    return d.isoformat()


def _r(v, n=4):
    return None if v is None else round(float(v), n)


def _path(data_dir, *p):
    return os.path.join(data_dir, DIR, *p)


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def starts(data_dir):
    """The owner's start dates (config/forecast_starts.json next to data/): {app id: date}."""
    raw = _read(os.path.join(os.path.dirname(os.path.abspath(data_dir)), "config", "forecast_starts.json"), {})
    out = {}
    for k, v in (raw if isinstance(raw, dict) else {}).items():
        try:
            out[str(k)] = date.fromisoformat(str(v))
        except ValueError:
            continue
    return out


def engine(env=None):
    """FORECAST_ENGINE: "v0" the earlier engine (the rollback), anything else "vd"."""
    v = ((os.environ if env is None else env).get("FORECAST_ENGINE") or "").strip().lower()
    return "v0" if v == "v0" else "vd"


class Run:
    def __init__(self, data_dir, now, clock, cal=None):
        self.data_dir, self.now, self.clock, self.t0 = data_dir, now, clock, clock()
        st = _read(_path(data_dir, "state.json"), {})
        self.season = {int(k): float(v) for k, v in (st.get("season") or {}).items()} or None
        self.bandr = st.get("bandr") if isinstance(st.get("bandr"), dict) else {}
        self.starts = starts(data_dir)
        self.eng = engine()
        self.V = 1 if self.eng == "v0" else 2
        self.E = ENGINES[self.V]
        self.pool, self.pool_b = {}, {}
        self.ran = self.kept = self.skipped = 0
        self.tune_sec = []                  # seconds of each re-tune this build (counts only in the log line)
        self.gx = [0, 0]                    # vd re-tunes whose back-test chose GA4's late country cells / paid cells
        self.cs = None                      # every Google Ads store's country block pairs (engine vd's e), once
        self.plans = 0                      # apps whose page got the "Budget by country" planner
        self.cal = cal if isinstance(cal, dict) and any(cal.get(k) for k in ("s", "wk", "hol")) else None  # 📅 (+ the
        # weekday rhythm / holidays even before a first complete season: no season → no event weeks, the engine as without)

    def left(self):
        return BUDGET_SEC - (self.clock() - self.t0)


def start(data_dir, now=None, clock=time.monotonic, cal=None):
    return Run(data_dir, now or datetime.now(timezone.utc), clock, cal)


# ── inputs ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def inputs(rows, P, ida, life, life_till, unst=None):
    """The engine's app: coh {X: {n, d, df, u, uf, t, ul}}, days {D: {rev, sp, spi, n, na, dau, un}}, last, cty {week:
    {slot: {n, r, u}}} (the install-day file's country cells), unc (the Uninstall store's cells); for engine vd also
    g4 {D: {rev: GA4 USD, rb: [USD by GA4 install-age band 0 | 1–6 | 7–29 | 30–89 | 90–364 | 365–427], ab: [active
    users by the same bands], k: AdMob ÷ GA4 that day}}, ida (the GA4 day ledger: read status, country slots), glag
    (days GA4 lands after AdMob, measured), clag (days the newest install day's final data lags AdMob) and tlag (days
    the newest checkpoint after day 30 — 60 / 90 / 180 / 365 — lags AdMob)."""
    S = P["S"]
    till = _d(life_till) if life_till else None
    days, coh = {}, {}
    for x in life or []:
        D = _d(x[0])
        if till and D > till:
            continue
        days.setdefault(D, {})["rev"] = x[1] or 0.0
    for r in rows:
        X = r["X"]
        e = days.setdefault(X, {})
        e["n"], e["na"], e["sp"], e["spi"] = r["n"], r["na"], r["sp"] or 0.0, r.get("spi") or 0.0
        ul = None
        ie = r.get("e")
        if ie and ie.get("u"):
            lim = (S - X).days
            ul = [v if L <= lim else None for L, v in zip(F.ULAGS, ie["u"])]
        coh[X] = {"n": r["n"], "d": r["d"], "df": r["df"], "u": r["u"], "uf": r["df"], "t": r["t"], "ul": ul}
    for k, v in ((ida or {}).get("days") or {}).items():
        if isinstance(v, dict) and v.get("a"):
            D = _d(k)
            if not till or D <= till:
                days.setdefault(D, {})["dau"] = v["a"]
    cty = {}
    for w, cells in ((ida or {}).get("c") or {}).items():          # the install-week country cells → the country mix
        if isinstance(cells, dict) and cells:
            cty[_d(w)] = {k: e for k, e in cells.items() if isinstance(e, dict)}
    unc = {}
    for k, cells in ((unst or {}).get("cohorts") or {}).items():    # the Uninstall store: install day × lag uninstalls
        try:
            unc[_d(k)] = {int(L): int(v or 0) for L, v in (cells or {}).items()}
        except (ValueError, TypeError):
            continue
    for k, v in ((unst or {}).get("daily") or {}).items():           # … and each day's uninstalls (app_remove users)
        if isinstance(v, dict) and v.get("un") is not None:
            D = _d(k)
            if not till or D <= till:
                days.setdefault(D, {})["un"] = v["un"]
    g4 = {}
    for k, v in ((ida or {}).get("days") or {}).items():            # the GA4 day ledger: revenue / users by install age
        if not isinstance(v, dict) or not v.get("rev") or not v.get("rb"):
            continue
        D = _d(k)
        if till and D > till:
            continue
        A = (days.get(D) or {}).get("rev")
        G = v["rev"] / 1e6
        g4[D] = {"rev": G, "rb": [x / 1e6 for x in v["rb"]], "ab": list(v.get("ab") or []),
                 "k": (A / G) if A and G > 0 else None}
    last = till or (max(days) if days else S)
    fin = [X + timedelta(days=(c.get("df") or 0) - 1) for X, c in coh.items() if c.get("df")]
    tfin = [X + timedelta(days=F.T_AGES[j]) for X, c in coh.items() for j, v in enumerate(c.get("t") or [])
            if v is not None and j < len(F.T_AGES) and F.T_AGES[j] > 30]
    return {"coh": coh, "days": days, "last": last, "cty": cty, "unc": unc, "g4": g4, "ida": ida or {},
            "glag": max(0, (last - max(g4)).days) if g4 else 0, "clag": max(0, (last - max(fin)).days) if fin else 0,
            "tlag": max(0, (last - max(tfin)).days) if tfin else 0}


def geo_weeks(gw, sids, fxf):
    """The app's Google Ads country weeks for engine vd's country model: gw = the geo cache's weeks {store id: {Monday:
    {cc: [cost micros (billed currency), downloads or null]}}}, the app's store ids, fxf (day → USD per billed unit) →
    {Monday: {cc: [USD at the week's rate (Monday + 3, as the ROI section's country months), downloads or None]}}."""
    out = {}
    for sid in sorted(sids or ()):
        for W, cs in ((gw or {}).get(sid) or {}).items():
            try:
                Wd = _d(W)
            except ValueError:
                continue
            rate = fxf(Wd + timedelta(days=3)) or 0
            e = out.setdefault(Wd, {})
            for cc, v in (cs or {}).items():
                if not isinstance(v, list) or not v:
                    continue
                c = e.setdefault(cc, [0.0, 0.0])
                c[0] += (v[0] or 0) / 1e6 * rate
                if len(v) > 1 and v[1] is not None and c[1] is not None:
                    c[1] += float(v[1])
                else:
                    c[1] = None
    return out


def cs_pairs(run, geo, fxf):
    """Every store's country block pairs (engine vd's pooled e), made once per build from the geo cache; None without."""
    if run.cs is None:
        run.cs = False
        try:
            if geo and geo.get("weeks") and geo.get("till"):
                stores = {sid: geo_weeks(geo["weeks"], [sid], fxf) for sid in geo["weeks"]}
                run.cs = VD.cs_pairs(stores, _d(geo["till"]))
        except Exception:
            run.cs = False
    return run.cs or None


# ── the bias correction folded into the days ────────────────────────────────────────────────────────────────────────
def _anchors(hs):
    """The horizons whose totals the page shows exactly: 30 / 90 / 180 (always, as before) + the app's chips hs."""
    return sorted(set(F.HORIZONS) | {int(h) for h in (hs or ())})


def corrected(series, cal, hs=None):
    """Per-day factors so the corrected cumulative sum at 30 / 90 / 180 days (+ each horizon in hs: the page's chips)
    = raw ÷ (1 + that horizon's bias); a horizon without one carries the factor before it on (as it is). 30 / 90 / 180:
    the factor held in [0.5, 2] as always (their numbers exactly as before); a chip outside them: only ≥ FIT_MIN, so
    its total is exactly its own calibration (_fit drops a chip whose bias asks for less than that)."""
    tot = [a + b + c for a, b, c in zip(series["old"], series["org"], series["paid"])]
    fac = [1.0] * len(tot)
    prev_h, prev_raw, prev_cor, last_f = 0, 0.0, 0.0, 1.0
    for hz in _anchors(hs):
        if hz > len(tot):
            break
        raw = sum(tot[:hz])
        b = (cal.get(hz) or {}).get("bias")
        target = raw / (1 + b) if b is not None else prev_cor + (raw - prev_raw) * last_f
        seg = raw - prev_raw
        f = (target - prev_cor) / seg if seg > 0 else last_f
        if b is not None:                                # (a carried factor stays as it was: no step where no bias)
            f = min(2.0, max(0.5, f)) if hz in F.HORIZONS else max(FIT_MIN, f)
        for i in range(prev_h, hz):
            fac[i] = f
        prev_h, prev_raw, prev_cor, last_f = hz, raw, prev_cor + seg * f, f
    for i in range(prev_h, len(tot)):
        fac[i] = last_f
    return fac


def _fit(rev, cal, hs):
    """corrected() with the chips hs it can show exactly → (factors, the chips kept, the chips dropped): a chip outside
    30 / 90 / 180 whose corrected total still misses raw ÷ (1 + its bias) by more than FIT_TOL (its bias asks for less
    than the days before it already add up to: the days in between would earn ~nothing) is dropped with every longer
    one — the page never shows a chip's total that its own back-tests do not give."""
    hs = [int(h) for h in (hs or ())]
    tot = [a + b + c for a, b, c in zip(rev["old"], rev["org"], rev["paid"])]
    drop = []
    while True:
        fac = corrected(rev, cal, hs)
        bad = None
        for h in hs:
            if h in F.HORIZONS or h > len(tot) or (cal.get(h) or {}).get("bias") is None:
                continue
            want = sum(tot[:h]) / (1 + cal[h]["bias"])
            got = sum(t * x for t, x in zip(tot[:h], fac[:h]))
            if abs(got - want) > FIT_TOL * max(abs(want), 1e-12):
                bad = h
                break
        if bad is None:
            return fac, hs, drop
        drop += [h for h in hs if h >= bad]
        hs = [h for h in hs if h < bad]


# ── drivers: now vs the app's usual ("X") ───────────────────────────────────────────────────────────────────────────
def _avg(days, a, b, key, per=None):
    num = den = 0.0
    D = a
    while D <= b:
        e = days.get(D) or {}
        v = e.get(key)
        if v is not None:
            if per:
                q = e.get(per)
                if q:
                    num += v
                    den += q
            else:
                num += v
                den += 1
        D += timedelta(days=1)
    return (num / den) if den else None


def split(app, rev_cty, a_now, b_now, a_x, b_x):
    """Why the revenue per day moved, the last 14 days vs X (the 8 weeks before) — four factors that multiply back to
    the revenue change exactly: users (GA4 DAU) × ad impressions per user × the country mix (more of the impressions
    from high-eCPM countries, at X's eCPMs) × each country's own eCPM (now vs X, at today's mix). AdMob country report;
    None without enough days. + the countries that moved the mix / their eCPM most."""
    if not rev_cty:
        return None

    def win(a, b):
        by, k, A, nd = {}, 0, 0.0, 0
        D = a
        while D <= b:
            x = rev_cty.get(D.isoformat())
            if x:
                k += 1
                for cc, v in x.items():
                    e = by.setdefault(cc, [0.0, 0.0])
                    e[0] += v[0] / 1e6
                    e[1] += v[1]
            dau = (app["days"].get(D) or {}).get("dau")
            if dau:
                A += dau
                nd += 1
            D += timedelta(days=1)
        return by, k, (A / nd if nd else None)
    bn, kn, An = win(a_now, b_now)
    bx, kx, Ax = win(a_x, b_x)
    En, In = sum(v[0] for v in bn.values()), sum(v[1] for v in bn.values())
    Ex, Ix = sum(v[0] for v in bx.values()), sum(v[1] for v in bx.values())
    if kn < 7 or kx < 28 or En <= 0 or Ex <= 0 or In <= 0 or Ix <= 0:
        return None
    ex = Ex / Ix
    ecx = {cc: (v[0] / v[1] if v[1] > 0 else ex) for cc, v in bx.items()}
    at_x = sum(v[1] / In * ecx.get(cc, ex) for cc, v in bn.items())       # today's mix at X's eCPMs
    out = {"rev": [_r(En / kn, 4), _r(Ex / kx, 4)], "imp": [_r(In / kn, 1), _r(Ix / kx, 1)],
           "ecpm": [_r(En / In * 1000, 4), _r(ex * 1000, 4)],
           "mix": _r(at_x / ex - 1, 4), "rate": _r((En / In) / at_x - 1, 4) if at_x > 0 else None}
    if An and Ax:
        out["users"] = _r(An / Ax - 1, 4)
        out["ipu"] = _r(((In / kn) / An) / ((Ix / kx) / Ax) - 1, 4)
    else:                                                # no DAU: users and ads per user stay one "impressions" factor
        out["imps"] = _r((In / kn) / (Ix / kx) - 1, 4)
    mv, rt = [], []
    for cc in set(bn) | set(bx):
        sn = bn.get(cc, [0, 0])[1] / In
        sx = bx.get(cc, [0, 0])[1] / Ix
        mv.append((cc, (sn - sx) * (ecx.get(cc, ex) - ex) / ex, sn, sx))
        if cc in bn and bn[cc][1] > 0 and cc in bx and bx[cc][1] > 0:
            rt.append((cc, sn * (bn[cc][0] / bn[cc][1] - ecx[cc]) / at_x, bn[cc][0] / bn[cc][1], ecx[cc]))
    mv.sort(key=lambda t: -abs(t[1]))
    rt.sort(key=lambda t: -abs(t[1]))
    out["mix_top"] = [[cc, _r(x, 4), _r(sn, 4), _r(sx, 4), _r(ecx.get(cc, ex) * 1000, 4)] for cc, x, sn, sx in mv[:4]
                      if abs(x) >= 0.005]
    out["rate_top"] = [[cc, _r(x, 4), _r(e1 * 1000, 4), _r(e0 * 1000, 4)] for cc, x, e1, e0 in rt[:4] if abs(x) >= 0.005]
    out["by"] = {cc: [_r(v[0] / v[1] * 1000, 4) if v[1] else None,
                      _r(bx[cc][0] / bx[cc][1] * 1000, 4) if cc in bx and bx[cc][1] else None] for cc, v in bn.items()}
    return out


def drivers(app, rows, ida, cty_rows, rev_cty=None):
    days, last = app["days"], app["last"]
    a_now, b_now = last - timedelta(days=13), last
    a_x, b_x = last - timedelta(days=69), last - timedelta(days=14)
    out = {}
    for key, kk, per in (("installs", "n", None), ("spend", "sp", None), ("dau", "dau", None),
                         ("arpdau", "rev", "dau"), ("cpi", "sp", "n")):
        out[key] = [_r(_avg(days, a_now, b_now, kk, per), 6), _r(_avg(days, a_x, b_x, kk, per), 6)]

    def ret(lag, a, b):
        n = u = 0.0
        for r in rows:
            if a <= r["X"] <= b and r["n"]:
                v = None
                if r["u"] is not None and lag < r["df"]:
                    v = r["u"][lag]
                elif r.get("iu") and lag in r["iu"]:
                    v = r["iu"][lag]
                if v is not None:
                    n += r["n"]
                    u += v
        return (u / n) if n else None
    for lag in (1, 7):
        out["d%d" % lag] = [_r(ret(lag, a_now - timedelta(days=lag + 3), b_now - timedelta(days=lag + 3)), 4),
                            _r(ret(lag, a_x - timedelta(days=lag + 3), b_x - timedelta(days=lag + 3)), 4)]
    # countries: install share (last 4 install weeks vs the 8 before), next-day returners, earning by day 7, CPI
    cset = (ida or {}).get("cset") or []
    weeks = sorted((ida or {}).get("c") or {})
    now_w, x_w = weeks[-4:], weeks[-12:-4]

    def share(ws):
        tot, by = 0.0, {}
        for W in ws:
            for sk, cell in ((ida.get("c") or {}).get(W) or {}).items():
                if sk == "gap" or not isinstance(cell, dict):
                    continue
                try:
                    cc = cset[int(sk)]
                except (ValueError, IndexError, TypeError):
                    continue
                n = int(cell.get("n") or 0)
                tot += n
                by[cc] = by.get(cc, 0) + n
        return {k: v / tot for k, v in by.items()} if tot else {}
    sn, sx = share(now_w), share(x_w)
    cty = []
    for r in cty_rows or []:
        cc = r.get("cc")
        if not cc or cc in ("--", "ZZ"):
            continue
        tr = r.get("trend") or {}

        def nx(arr):
            a = [v for v in (arr or [])[-4:] if v is not None]
            b = [v for v in (arr or [])[-12:-4] if v is not None]
            return [_r(sum(a) / len(a), 6) if a else None, _r(sum(b) / len(b), 6) if b else None]
        cty.append({"cc": cc, "share": [_r(sn.get(cc), 4), _r(sx.get(cc), 4)], "d1": nx(tr.get("d1")),
                    "rpi7": nx(tr.get("rpi7")), "cpi": nx(tr.get("cpi")), "dec": r.get("dec")})
    cty.sort(key=lambda c: -((c["share"][0] or 0) + (c["share"][1] or 0)))
    out["cty"] = cty[:12]
    try:
        sp = split(app, rev_cty, a_now, b_now, a_x, b_x)
    except Exception:
        sp = None
    if sp:
        by = sp.pop("by")
        for c in out["cty"]:
            c["ecpm"] = by.get(c["cc"])
        out["split"] = sp
    return out


# ── the page's series (a full model run and a kept one alike) ───────────────────────────────────────────────────────
def plan_out(pl, f, fac, hs=None):
    """The engine's planner inputs (forecast_vd.cs_plan) → the page's "Budget by country" card: per row its spend, its
    installs per $ (ppu) at the training level sb and its measured spend range; its revenue per $ of spend within each
    horizon (r) — at 30 / 90 days, where they won this app's own back-test, each row's own (cs_rpd: its paid users' GA4
    revenue ÷ its spend, "rs" "cp" its own GA4 slot / "pool" the countries without one, measured together; "rt" how
    much of it is the row's own data, S ÷ (S + CS_RK), the rest the app's average), scaled so today's plan gives the
    forecast's own paid-install revenue (bias-corrected, at today's spend) exactly; past 90 days (or without enough
    paid cells, or where the app's own back-test did not win) the forecast's own ÷ today's spend, the SAME for every
    row ("rs" / "rt" None); at any spend (revenue follows the money: the ROI forms' β on top did not win the back-test)
    + the old users' and organic installs' revenue (corrected) the plan does not move; "rw" the install weeks (first
    Monday … last Sunday) and paid installs each horizon's own values come from; "rbt" {H: n origins, b better, w worse,
    need} the app's own back-test at every horizon it ran (cs_bt). fc_cs: the forecast's own paid installs follow the
    country model too (STRUCT cs 1) — the page's spend slider then moves installs × m^(1 − e), else × m."""
    if not pl or not pl.get("rows") or not pl.get("s"):
        return None

    def csum(k, hz):
        return sum(v * fac[i] for i, v in enumerate(f["rev"][k][:hz]))
    hs = [h for h in _anchors(hs) if h <= len(fac)] if hs else VD.CS_H     # (+ the page's chips: its horizons)
    paid = [csum("paid", hz) for hz in hs]
    s0 = [x["s0"] for x in pl["rows"]]
    rpd = pl.get("rpd") or {}
    rs, rr, rt = [], [], []                              # per horizon: each row's source, revenue per $ and trust
    for hz, v in zip(hs, paid):
        q = rpd.get(hz)
        mix = sum(a * b for a, b in zip(s0, q["rho"])) / pl["s"] if q and len(q["rho"]) == len(s0) else 0.0
        if mix > 0:
            rr.append([_r(v / pl["s"] * x / mix, 6) for x in q["rho"]])
            rs.append(list(q["src"]))
            rt.append([_r(x, 3) for x in (q.get("t") or [None] * len(s0))])
        else:
            rr.append([_r(v / pl["s"], 6)] * len(s0))
            rs.append([None] * len(s0))
            rt.append([None] * len(s0))
    rows = [{"cc": x["cc"], "s0": _r(x["s0"], 4), "sb": _r(x["sb"], 4), "ppu": _r(pl["pu"] * x["rho"], 6),
             "lo": _r(x["lo"], 4), "hi": _r(x["hi"], 4), "r": [rr[j][i] for j in range(len(hs))],
             "rs": [rs[j][i] for j in range(len(hs))], "rt": [rt[j][i] for j in range(len(hs))]}
            for i, x in enumerate(pl["rows"])]
    rw = {str(hz): {"w": [q["w"][0], (date.fromisoformat(q["w"][-1]) + timedelta(days=6)).isoformat()],
                    "n": len(q["w"]), "np": int(round(q["np"]))}
          for hz, q in sorted(rpd.items()) if hz in hs and q.get("w")}
    rbt = {str(hz): {"n": b[0], "b": b[1], "w": b[2], "need": VD.CS_BTN}
           for hz, b in sorted((pl.get("rbt") or {}).items()) if hz in hs and b}
    return {"v": 2, "weeks": pl["weeks"], "e": _r(pl["e"], 4), "en": pl["en"], "s": _r(pl["s"], 4),
            "org": _r(pl["org"], 2), "n0": _r(pl["n0"], 2), "fc_cs": 1 if pl.get("fc") else 0,
            "old": [_r(csum("old", hz), 2) for hz in hs], "orgr": [_r(csum("org", hz), 2) for hz in hs],
            "paid": [_r(v, 2) for v in paid], "h": list(hs), "rows": rows, "rw": rw, "rbt": rbt}


def weekly(ser, d0, W, hs=None):
    """The after-call weekday rhythm on the page's daily forecast (W: fc_calendar.weekday, Mon..Sun): each part's days
    × W of their weekday, rescaled inside every horizon block (days 1–30, 31–90, 91–180, + the page's chips hs) so each
    part's block total — every total the page shows, at any spend slider — stays the forecast's. None: the series as
    it was."""
    if not W:
        return ser
    out = {}
    for k, v in ser.items():
        fac = [W[(d0 + timedelta(days=i)).weekday()] for i in range(len(v))]
        o, prev = list(v), 0
        for hz in tuple(_anchors(hs)) + (len(v),):
            hi = min(hz, len(v))
            raw = sum(x or 0.0 for x in v[prev:hi])
            sh = sum((x or 0.0) * f for x, f in zip(v[prev:hi], fac[prev:hi]))
            kk = raw / sh if sh > 0 else 1.0
            for i in range(prev, hi):
                o[i] = None if v[i] is None else _r(v[i] * fac[i] * kk, 4)
            prev = hi
        out[k] = o
    return out


def series(app, p, cal, seas, E=F, hs=None, reach=None):
    """The forecast of engine E from the newest day with settings p (spend = the last F.SPEND_DAYS days' run-rate, the
    bias correction of cal) → the page's f + hist: revenue / active users / uninstalls by who (old users, organic,
    paid), installs, spend; the actual last HIST_DAYS days beside it; + "plan" (engine vd with country data: the
    "Budget by country" planner, plan_out). hs: the page's chips (engine vd's verified horizons, VD.chips) — the page
    reaches the longest (≥ F.H days) and each one's total is bias-corrected by its own back-tests (_fit: a chip it can
    not show exactly is dropped). reach: the days the forecast itself goes (engine vd, the day's snapshot: VD.HMAX, so
    every grid horizon's total is kept for its live check) — the page's lists stop at max(F.H, the longest chip), the
    same numbers either way. → (out, f, ser: the corrected days as far as the forecast reaches, the chips shown)."""
    last = app["last"]
    hs = [int(h) for h in (hs or ())]
    L = max([F.H] + hs)                                  # the page's days
    hf = max(L, int(reach or 0))                         # the forecast's
    f = E.forecast(app, last, p, h=hf, seas=seas, **({"hc": L} if hf > L else {}))
    fac, hs, _ = _fit(f["rev"], cal, hs)
    L = max([F.H] + hs)
    ser = {k: [_r(v * fac[i], 4) for i, v in enumerate(f["rev"][k])] for k in ("old", "org", "paid")}
    ser = weekly(ser, last + timedelta(days=1), app.get("wk"), hs)     # 📅 the after-call weekday rhythm (page only)
    hist0 = last - timedelta(days=HIST_DAYS - 1)
    hd = [app["days"].get(hist0 + timedelta(days=i)) or {} for i in range(HIST_DAYS)]

    def run_rate(k, n):
        ds = [app["days"].get(last - timedelta(days=i)) or {} for i in range(n)]
        return sum(e.get(k) or 0 for e in ds) / float(n)
    out = {"f": {"d0": _iso(last + timedelta(days=1)), **{k: v[:L] for k, v in ser.items()},
                 "dau": [_r(v, 1) for v in f["dau"][:L]],
                 "dau_p": {k: [_r(v, 1) for v in f["dau_p"][k][:L]] for k in ("old", "org", "paid")},
                 "un": {k: [_r(v, 1) for v in f["un"][k][:L]] for k in ("old", "org", "paid")} if f.get("un") else None,
                 "n": [_r(v, 1) for v in f["n"][:L]], "sp": [_r(v, 4) for v in f["sp"][:L]],
                 "spi": _r(run_rate("spi", F.SPEND_DAYS), 2), "spd": F.SPEND_DAYS,
                 "spi30": _r(run_rate("spi", 30), 2), "sp30": _r(run_rate("sp", 30), 4)},
           "hist": {"d0": _iso(hist0), "rev": [_r(e.get("rev"), 4) for e in hd], "sp": [_r(e.get("sp"), 4) for e in hd],
                    "spi": [_r(e.get("spi"), 2) for e in hd], "dau": [e.get("dau") for e in hd],
                    "n": [e.get("n") for e in hd], "un": [e.get("un") for e in hd]}}
    try:                                                 # only the planner would miss it: never the forecast
        out["plan"] = plan_out(f.get("plan"), f, fac, hs)
    except Exception:
        out["plan"] = None
    out["fcal"] = _rx(f.get("cal"), 4) if f.get("cal") else None    # 📅 the coming event weeks (engine vd)
    if app.get("wk"):
        out["fcal"] = dict(out["fcal"] or {"ev": []}, wk=_rx(list(app["wk"]), 4))
    return out, f, ser, hs


def _holidays(run, sr, last, rev_cty, h=None):
    """+ sr["fcal"]["hol"]: Ramadan / Diwali inside the next h days — measured once each (fc_calendar.holidays), NOT in
    the forecast (no back-test could show they help yet): the measured eCPM gap (those countries minus the others, and
    each part) × the app's own share of revenue in those countries over its newest 28 days (rev_cty: {day: {country:
    [earnings micros, impressions]}})."""
    try:
        hol = (run.cal or {}).get("hol")
        if not hol:
            return
        h = h or len((sr.get("f") or {}).get("old") or ()) or F.H
        tot, mus, ind = 0.0, 0.0, 0.0
        for d in sorted(rev_cty or {})[-28:]:
            for cc, v in (rev_cty[d] or {}).items():
                x = float((v or [0])[0] or 0)
                tot += x
                mus += x if cc in FC.MUSLIM else 0.0
                ind += x if cc == "IN" else 0.0
        sh = {"ramadan": mus / tot, "diwali": ind / tot} if tot > 0 else {}
        ev = FC.holidays_coming(hol, last, h, sh)
        if ev:
            sr["fcal"] = dict(sr.get("fcal") or {"ev": []}, hol=_rx(ev, 4))
    except Exception:
        pass


# ── one app ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _events(bt):
    seen, out = [], []
    for r in bt:
        for hz, ev in sorted((r.get("ev") or {}).items()):
            at = ev.get("at")
            if not at or any(abs((_d(at) - _d(s)).days) < 21 for s in seen):
                continue
            seen.append(at)
            out.append({"at": at, "kind": ev["kind"], "x": ev["x"]})
    return sorted(out, key=lambda e: e["at"])


def _rx(v, n=6):
    """Floats rounded (inside lists / dicts too) — the parts the page's "why" shows."""
    if isinstance(v, float):
        return _r(v, n)
    if isinstance(v, (list, tuple)):
        return [_rx(x, n) for x in v]
    if isinstance(v, dict):
        return {k: _rx(x, n) for k, x in v.items()}
    return v


def _unlock(E, start, last, lag, hz):
    """The day horizon hz shows (its MIN_TESTS-th back-test exists: E.unlock) — on the build calendar (+ lag, the days
    the newest data day trails the build); a day already past whose tests are not all there (a test without revenue):
    the next origin's. None: never (past GRID_ORIGINS)."""
    u = E.unlock(start, hz)
    if u is None:
        return None
    while u <= last:
        u += timedelta(days=F.ORIGIN_STEP)
    return _iso(u + timedelta(days=lag))


def horizon(E, start, last, lag, cal, gbt, hs, full=None):
    """Engine vd's verified horizon for the page: n = the longest grid horizon with ≥ MIN_TESTS back-tests (None: not
    even 30 days yet), chips = the page's horizons (E.chips), lock = the day each standard 30 / 90 / 180 / 365 not yet
    verified shows, next = [the next longer horizon, its day] (the longest of those that unlock together: one more
    origin), band = the chart's monotone 80 % band across the chips (E.band), x = tests from the origins before the tune's
    (352 / 365 days: GRID_ORIGINS), btx = each chip outside 30 / 90 / 180: its tests [T, error, sudden change 0/1, an
    older origin 0/1]. full: the chips before series()' _fit (hs: the ones it shows) — drop = verified but not shown
    (its calibrated total can not be shown), n then the longest shown."""
    full = list(hs or ()) if full is None else list(full)
    drop = [h for h in full if h not in (hs or ())]
    top = max(cal) if cal else None
    n = (hs[-1] if hs else None) if drop else top
    lock = {str(h): _unlock(E, start, last, lag, h) for h in E.STD if h not in cal}
    later = {h: _unlock(E, start, last, lag, h) for h in E.HG if top is None or h > top}
    later = {h: d for h, d in later.items() if d}
    nxt = None
    if later:
        d0 = min(later.values())
        nxt = [max(h for h, d in later.items() if d == d0), d0]
    btx = {}
    for h in full:
        if h not in F.HORIZONS:
            btx[str(h)] = [[r["T"], _r(r["h"][h]["err"], 4), 1 if h in (r.get("ev") or {}) else 0,
                            1 if r.get("x") else 0] for r in E.grid_tests(gbt, h)]
    used = {r["T"] for h in (hs or ()) for r in E.grid_tests(gbt, h) if r.get("x")}
    return {"n": n, "chips": list(hs or ()), "drop": drop, "lock": lock, "next": nxt, "x": len(used),
            "band": _rx(E.band({h: cal[h] for h in (hs or ()) if h in cal}), 4),
            "btx": btx, "lag": lag}


def _rechip(hz, cal, full, hs):
    """A kept forecast whose chips today (series' _fit on today's data) differ from its file's: the page's chips, n,
    drop and band follow (cal: the page's calibration, string keys)."""
    return dict(hz, chips=list(hs), n=hs[-1] if hs else hz.get("n"), drop=[h for h in full if h not in hs],
                band=_rx(VD.band({h: cal[str(h)] for h in hs if str(h) in cal}), 4))


def _first_checks(live, hs, have, lag, today, HMAX):
    """{horizon: the build day its first live check shows} for each chip without one yet (+ HMAX, where the longest
    chip stops growing): the oldest kept day's forecast that holds that horizon's total + the horizon + lag (a day
    already past: none — that check had no revenue)."""
    out = {}
    for h in sorted(set(hs or ()) | {HMAX}):
        if h in have:
            continue
        ts = [x["T"] for x in live
              if (x.get("p%d" % h) is not None if h in F.HORIZONS else str(h) in (x.get("px") or {}))]
        if ts:
            d = _d(min(ts)) + timedelta(days=h + lag)
            if d > today:
                out[str(h)] = _iso(d)
    return out


def _newest(checks, k=CHECK_KEEP):
    """The live checks kept for the page: the newest k of each horizon (a long one's are older: never crowded out by
    the 30-day ones), in their order."""
    seen, keep = {}, []
    for c in reversed(checks):
        if seen.get(c["h"], 0) < k:
            seen[c["h"]] = seen.get(c["h"], 0) + 1
            keep.append(c)
    return keep[::-1]


def _tuned_now(E, p):
    """Could the current engine's tune have stored setting p? Every setting it tunes is there (a setting stored before a
    switch existed has never been tested with it) and on its grid (a switch the engine now holds at one value)."""
    p = p or {}
    return set(E.DEFAULT) <= set(p) and all(p[k] in vals for k, vals in getattr(E, "GRID", {}).items())


def app_step(run, aid, key, rows, P, ida, life, life_till, cty_rows, rev_cty=None, unst=None, geo=None, cs_pairs=None):
    """→ the page's forecast for this app (None: nothing yet). Never raises. geo: the app's Google Ads country weeks
    (geo_weeks), cs_pairs: every store's country block pairs (the run's cs_pairs) — engine vd's "Budget by country"
    planner (and its paid installs by country, with STRUCT cs 1)."""
    try:
        app = inputs(rows, P, ida, life, life_till, unst)
        app["geo"], app["cs_pairs"] = geo or {}, cs_pairs
        app["cal"] = run.cal                             # 📅 the eCPM calendar's seasons (engine vd, STRUCT cal)
        try:                                             # … and this app's after-call weekday rhythm (page only)
            app["wk"] = FC.weekday(((run.cal or {}).get("wk") or {}).get(aid), app["last"]) if app.get("last") else None
        except Exception:
            app["wk"] = None
        app["port"] = {"bandr": run.bandr}               # the portfolio's band ratios (state.json, the last build's)
        for D, e in app["days"].items():                 # the portfolio season, pooled from every app
            if e.get("rev") and e.get("dau"):
                p = run.pool.setdefault(D, {"rev": 0.0, "dau": 0.0})
                p["rev"] += e["rev"]
                p["dau"] += e["dau"]
        try:                                             # … and its band ratios (made in finish())
            pb = VD.port_pre(app)
            if pb:
                run.pool_b[aid] = pb
        except Exception:
            pass
        with_n = {D: e for D, e in app["days"].items() if e.get("n") is not None}
        if not with_n:
            return None
        auto = F.auto_start(with_n)
        mine = run.starts.get(aid)
        app["start"] = mine if mine and auto and mine >= min(with_n) else auto
        path = _path(run.data_dir, key + ".json")
        old = _read(path, {})
        today = _iso(run.now.date())
        E, Vr = run.E, run.V
        made = old.get("made_at")
        age_h = (run.now - datetime.fromisoformat(made)).total_seconds() / 3600 if made else None
        same = old.get("v") == Vr and old.get("start") == _iso(app["start"])
        if Vr == 1:                                      # v0: re-made once a day and with a new day of data
            fresh = same and old.get("T") == _iso(app["last"]) and age_h is not None and age_h < EVERY_H
            can = run.left() > 0
        else:                                            # vd: the forecast is re-made every build below (cheap); the
            fresh = (same and age_h is not None and age_h < EVERY_H    # tune once a day, if its seconds fit the budget,
                     and _tuned_now(E, old.get("p"))                   # at once for a setting it can't make or a file
                     and "hz" in (old.get("fc") or {}))                # made before the verified horizon
            last_sec = old.get("tune_sec") if old.get("v") == Vr else None
            can = run.left() > TUNE_MARGIN * float(last_sec or TUNE_GUESS_SEC)
        seas = run.season or F.season(app["days"])
        if fresh or not can:
            if old.get("fc") and old.get("v") in ENGINES:
                run.kept += 1
                fc = dict(old["fc"])
                try:                                     # the "why" is cheap: today's data even between model runs
                    fc["drv"] = drivers(app, rows, ida, cty_rows, rev_cty)
                except Exception:
                    pass
                try:                                     # … and so is one forecast with the kept settings: today's data
                    if old.get("p") and app["last"] >= _d(old["T"]):    # and spend run-rate, users and uninstalls
                        Eo = ENGINES[old["v"]]           # (by the engine that made the file)
                        cal = {int(h): {"bias": b} for h, b in (old.get("bias") or {}).items()} or \
                            {int(h): c for h, c in (fc.get("cal") or {}).items()}
                        hs = Eo.chips(cal) if Eo is VD and "hz" in fc else None     # (a file made before: as it was)
                        sr, f, _, hs2 = series(app, dict(Eo.DEFAULT, **old["p"]), cal, seas, Eo, hs)
                        _holidays(run, sr, app["last"], rev_cty)
                        if hs is not None and hs2 != list(fc["hz"].get("chips") or ()):
                            fc["hz"] = _rechip(fc["hz"], fc.get("cal") or {}, hs, hs2)
                        fc.update(sr)
                        fc["T"] = _iso(app["last"])
                        if Eo is VD:
                            fc["parts"] = _rx(f["parts"])
                except Exception:
                    pass
                run.plans += 1 if fc.get("plan") else 0
                return fc
            if not can:
                run.skipped += 1
                return None
        prev_p = old.get("p") if old.get("v") == Vr else None
        t0 = run.clock()
        fits = {}
        p, bt, steps = E.tune(app, seas, start_p=prev_p, fits=fits) if Vr == 2 else E.tune(app, seas, start_p=prev_p)
        moved = (dict(E.DEFAULT, **prev_p) if Vr == 2 and prev_p else prev_p) != p   # vd: a setting stored before a
                                                                                       # switch existed = it at its default
        cal = F.calibrate(bt)
        gbt = []
        if Vr == 2:                                      # the verified horizon: the chosen setting on the horizon grid
            gbt = E.grid_backtest(app, p, seas, fits)    # (the tune's fits reused; ≤ 2 older origins for 352 / 365)
            for h, c in E.grid_cal(gbt).items():
                cal.setdefault(h, c)                     # (30 / 90 / 180: the very rows, so the very numbers)
        fits = None
        tune_sec = round(max(0.0, run.clock() - t0), 1)
        run.tune_sec.append(tune_sec)
        run.gx[0] += 1 if p.get("gc") else 0
        run.gx[1] += 1 if p.get("pc") else 0
        if Vr == 1:
            sc_prev = F.score(F.backtest(app, prev_p, seas)) if prev_p and prev_p != p else None
        else:                                            # vd tunes from the stored setting: its score is the first step
            sc_prev = steps[0]["score"] if prev_p and moved and steps else None
        full = E.chips(cal) if Vr == 2 else None
        sr, f, ser, hs = series(app, p, cal, seas, E, full, reach=E.HMAX if Vr == 2 else None)
        _holidays(run, sr, app["last"], rev_cty)
        last = app["last"]
        # readiness: a horizon shows once enough tests could score it; else the day it will
        ready, ready_from, hz_out = {}, {}, None
        if Vr == 2:                                      # engine vd: the verified horizon (30 / 90 / 180 / 365 + N)
            hz_out = horizon(E, app["start"], last, max(0, (run.now.date() - last).days), cal, gbt, hs, full)
            for hz in E.STD:
                ready[str(hz)] = hz in cal               # string keys: the same after the JSON round trip
                if hz not in cal and hz_out["lock"].get(str(hz)):
                    ready_from[str(hz)] = hz_out["lock"][str(hz)]
        else:
            for hz in F.HORIZONS:
                ok = hz in cal
                ready[str(hz)] = ok
                if not ok:
                    ready_from[str(hz)] = _iso(app["start"] + timedelta(days=F.MIN_HIST + hz + F.ORIGIN_STEP * (F.MIN_TESTS - 1) + 30))
        tot = [a + b + c for a, b, c in zip(ser["old"], ser["org"], ser["paid"])]
        snap = {"made": today, "T": _iso(last), "p30": _r(sum(tot[:30]), 2), "p90": _r(sum(tot[:90]), 2),
                "p180": _r(sum(tot[:180]), 2)}
        px = {str(h): _r(sum(tot[:h]), 2) for h in (E.HG if Vr == 2 else ()) if h not in F.HORIZONS and h <= len(tot)}
        if px:                                           # (every grid horizon outside 30 / 90 / 180 the forecast
            snap["px"] = px                              # reaches: the chips' live checks, whatever N is by then)
        live = [x for x in (old.get("live") or []) if x.get("made") != today][-LIVE_KEEP + 1:] + [snap]
        checks, shown = [], set(F.HORIZONS) | set(hs or ())
        for x in live:                                   # the live check: a forecast whose days have all happened
            T0 = _d(x["T"])                              # (the page's horizons: 30 / 90 / 180 + its chips)
            for hz in F.HORIZONS + tuple(sorted(int(h) for h in (x.get("px") or {}) if int(h) in shown)):
                pv = x.get("p%d" % hz) if hz in F.HORIZONS else x["px"][str(hz)]
                if pv is None or T0 + timedelta(days=hz) > last:
                    continue
                act = sum((app["days"].get(T0 + timedelta(days=i)) or {}).get("rev") or 0 for i in range(1, hz + 1))
                if act > 0:
                    checks.append({"made": x["made"], "h": hz, "pred": pv, "act": _r(act, 2), "err": _r(pv / act - 1, 4)})
        att = F.attribution(bt)
        log = list(old.get("log") or [])
        if moved or not log:
            cause = max(att, key=att.get) if att else None
            if prev_p:
                changed = sorted(k for k in p if dict(E.DEFAULT, **prev_p).get(k) != p[k])
            else:                                        # the first run, or the first of this engine: all its settings
                changed = sorted(p) if log else []       # are new (never "settings wahi" at an engine switch)
            log.append({"d": today, "eng": run.eng, "p": p, "sc_old": _r(sc_prev, 4), "sc": _r(E.score(bt), 4),
                        "changed": changed, "cause": cause, "bias30": _r((cal.get(30) or {}).get("bias"), 4)})
        log = log[-LOG_KEEP:]
        fc = {"v": Vr, "eng": run.eng, "made": today, "T": _iso(last), "start": _iso(app["start"]),
              "start_auto": _iso(auto) if auto else None,
              "start_set": _iso(mine) if mine else None, "p": p, "ready": ready, "ready_from": ready_from,
              "cal": {str(h): {k: (_r(v, 4) if isinstance(v, float) else v) for k, v in c.items()} for h, c in cal.items()},
              **sr,
              "bt": [[r["T"]] + [(_r(r["h"][hz]["err"], 4) if hz in r["h"] else None) for hz in F.HORIZONS]
                     + [sorted((r.get("ev") or {}).keys())] for r in bt],
              "events": _events(bt), "att": {k: _r(v, 3) for k, v in att.items()} if att else None,
              "log": log[-15:], "checks": _newest(checks), "drv": drivers(app, rows, ida, cty_rows, rev_cty),
              "parts": _rx(f["parts"])}
        if hz_out is not None:                           # when each chip's first live check shows (none yet)
            hz_out["chk"] = _first_checks(live, hs, {c["h"] for c in checks}, hz_out["lag"], run.now.date(), E.HMAX)
            fc["hz"] = hz_out
        run.plans += 1 if fc.get("plan") else 0
        _write(path, {"v": Vr, "eng": run.eng, "made_at": run.now.isoformat(), "start": _iso(app["start"]),
                      "T": _iso(last), "p": p, "tune_sec": tune_sec,
                      "bias": {str(h): c.get("bias") for h, c in cal.items()},
                      "log": log, "live": live, "fc": fc})
        run.ran += 1
        return fc
    except Exception:
        run.skipped += 1
        return None


def finish(run):
    """state.json for tomorrow's runs: the portfolio season (every app's revenue ÷ DAU by month, pooled), the band
    ratios of engine vd (every app's GA4 data, per Monday) and vd's structure — a part this build could not make keeps
    the last one."""
    try:
        seas = (F.season(run.pool) if run.pool else None) or run.season
        br = None
        try:
            br = VD.bandr(list(run.pool_b.values())) if run.pool_b else None
        except Exception:
            br = None
        br = br or run.bandr
        if seas or br:
            st = {"v": 1, "vd_struct": {"v": VD.STRUCT_VERSION, "p": VD.STRUCT}}
            if seas:
                st["season"] = {str(k): _r(v, 4) for k, v in seas.items()}
            if br:
                st["bandr"] = br                        # full precision: the engine reads them back exactly
            _write(_path(run.data_dir, "state.json"), st)
    except Exception:
        pass


def line(run):
    """The build log's line: counts and seconds only."""
    ts = run.tune_sec
    return ("forecast %s: ran %d, kept %d, skipped %d; tune %.0fs (max %.0fs); %.0fs; GA4 late cells %d, paid cells %d; "
            "budget planner %d" % (run.eng, run.ran, run.kept, run.skipped, sum(ts), max(ts) if ts else 0.0,
                                   run.clock() - run.t0, run.gx[0], run.gx[1], run.plans))
