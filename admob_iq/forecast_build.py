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
Kept for good in the private repo (data/forecast/<key>.json): the settings, the learning log (what changed and why, the
newest LOG_KEEP), and every day's own forecast of the next 30 / 90 / 180 days — once those days have happened the page
shows that live error too (the real check, beyond the back-tests).
data/forecast/state.json, refreshed at the end: the portfolio's month-of-year season and band ratios ("bandr": each GA4
install-age band's revenue per active user ÷ the band before's, the median over the apps, per Monday — engine vd's prior
for a band an app has few users in) + the engine's fixed structure ("vd_struct").
"""
import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone

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
    def __init__(self, data_dir, now, clock):
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

    def left(self):
        return BUDGET_SEC - (self.clock() - self.t0)


def start(data_dir, now=None, clock=time.monotonic):
    return Run(data_dir, now or datetime.now(timezone.utc), clock)


# ── inputs ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def inputs(rows, P, ida, life, life_till, unst=None):
    """The engine's app: coh {X: {n, d, df, u, uf, t, ul}}, days {D: {rev, sp, spi, n, na, dau, un}}, last, cty {week:
    {slot: {n, r, u}}} (the install-day file's country cells), unc (the Uninstall store's cells); for engine vd also
    g4 {D: {rev: GA4 USD, rb: [USD by GA4 install-age band 0 | 1–6 | 7–29 | 30–89 | 90–364 | 365–427], ab: [active
    users by the same bands], k: AdMob ÷ GA4 that day}}, ida (the GA4 day ledger: read status, country slots), glag
    (days GA4 lands after AdMob, measured) and clag (days the newest install day's final data lags AdMob)."""
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
    return {"coh": coh, "days": days, "last": last, "cty": cty, "unc": unc, "g4": g4, "ida": ida or {},
            "glag": max(0, (last - max(g4)).days) if g4 else 0, "clag": max(0, (last - max(fin)).days) if fin else 0}


# ── the bias correction folded into the days ────────────────────────────────────────────────────────────────────────
def corrected(series, cal):
    """Per-day factors so the corrected cumulative sum at 30 / 90 / 180 days = raw ÷ (1 + that horizon's bias)."""
    tot = [a + b + c for a, b, c in zip(series["old"], series["org"], series["paid"])]
    fac = [1.0] * len(tot)
    prev_h, prev_raw, prev_cor, last_f = 0, 0.0, 0.0, 1.0
    for hz in F.HORIZONS:
        if hz > len(tot):
            break
        raw = sum(tot[:hz])
        b = (cal.get(hz) or {}).get("bias")
        target = raw / (1 + b) if b is not None else prev_cor + (raw - prev_raw) * last_f
        seg = raw - prev_raw
        f = (target - prev_cor) / seg if seg > 0 else last_f
        f = min(2.0, max(0.5, f))
        for i in range(prev_h, hz):
            fac[i] = f
        prev_h, prev_raw, prev_cor, last_f = hz, raw, prev_cor + seg * f, f
    for i in range(prev_h, len(tot)):
        fac[i] = last_f
    return fac


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
def series(app, p, cal, seas, E=F):
    """The forecast of engine E from the newest day with settings p (spend = the last F.SPEND_DAYS days' run-rate, the
    bias correction of cal) → the page's f + hist: revenue / active users / uninstalls by who (old users, organic,
    paid), installs, spend; the actual last HIST_DAYS days beside it."""
    last = app["last"]
    f = E.forecast(app, last, p, h=F.H, seas=seas)
    fac = corrected(f["rev"], cal)
    ser = {k: [_r(v * fac[i], 4) for i, v in enumerate(f["rev"][k])] for k in ("old", "org", "paid")}
    hist0 = last - timedelta(days=HIST_DAYS - 1)
    hd = [app["days"].get(hist0 + timedelta(days=i)) or {} for i in range(HIST_DAYS)]

    def run_rate(k, n):
        ds = [app["days"].get(last - timedelta(days=i)) or {} for i in range(n)]
        return sum(e.get(k) or 0 for e in ds) / float(n)
    out = {"f": {"d0": _iso(last + timedelta(days=1)), **ser, "dau": [_r(v, 1) for v in f["dau"]],
                 "dau_p": {k: [_r(v, 1) for v in f["dau_p"][k]] for k in ("old", "org", "paid")},
                 "un": {k: [_r(v, 1) for v in f["un"][k]] for k in ("old", "org", "paid")} if f.get("un") else None,
                 "n": [_r(v, 1) for v in f["n"]], "sp": [_r(v, 4) for v in f["sp"]],
                 "spi": _r(run_rate("spi", F.SPEND_DAYS), 2), "spd": F.SPEND_DAYS,
                 "spi30": _r(run_rate("spi", 30), 2), "sp30": _r(run_rate("sp", 30), 4)},
           "hist": {"d0": _iso(hist0), "rev": [_r(e.get("rev"), 4) for e in hd], "sp": [_r(e.get("sp"), 4) for e in hd],
                    "spi": [_r(e.get("spi"), 2) for e in hd], "dau": [e.get("dau") for e in hd],
                    "n": [e.get("n") for e in hd], "un": [e.get("un") for e in hd]}}
    return out, f, ser


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


def app_step(run, aid, key, rows, P, ida, life, life_till, cty_rows, rev_cty=None, unst=None):
    """→ the page's forecast for this app (None: nothing yet). Never raises."""
    try:
        app = inputs(rows, P, ida, life, life_till, unst)
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
            fresh = same and age_h is not None and age_h < EVERY_H     # tune once a day, if its seconds fit the budget
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
                        sr, f, _ = series(app, dict(Eo.DEFAULT, **old["p"]), cal, seas, Eo)
                        fc.update(sr)
                        fc["T"] = _iso(app["last"])
                        if Eo is VD:
                            fc["parts"] = _rx(f["parts"])
                except Exception:
                    pass
                return fc
            if not can:
                run.skipped += 1
                return None
        prev_p = old.get("p") if old.get("v") == Vr else None
        t0 = run.clock()
        p, bt, steps = E.tune(app, seas, start_p=prev_p)
        tune_sec = round(max(0.0, run.clock() - t0), 1)
        run.tune_sec.append(tune_sec)
        if Vr == 1:
            sc_prev = F.score(F.backtest(app, prev_p, seas)) if prev_p and prev_p != p else None
        else:                                            # vd tunes from the stored setting: its score is the first step
            sc_prev = steps[0]["score"] if prev_p and prev_p != p and steps else None
        cal = F.calibrate(bt)
        sr, f, ser = series(app, p, cal, seas, E)
        last = app["last"]
        # readiness: a horizon shows once enough tests could score it; else the day it will
        ready, ready_from = {}, {}
        for hz in F.HORIZONS:
            ok = hz in cal
            ready[str(hz)] = ok                         # string keys: the same after the JSON round trip
            if not ok:
                ready_from[str(hz)] = _iso(app["start"] + timedelta(days=F.MIN_HIST + hz + F.ORIGIN_STEP * (F.MIN_TESTS - 1) + 30))
        tot = [a + b + c for a, b, c in zip(ser["old"], ser["org"], ser["paid"])]
        snap = {"made": today, "T": _iso(last), "p30": _r(sum(tot[:30]), 2), "p90": _r(sum(tot[:90]), 2),
                "p180": _r(sum(tot[:180]), 2)}
        live = [x for x in (old.get("live") or []) if x.get("made") != today][-LIVE_KEEP + 1:] + [snap]
        checks = []
        for x in live:                                   # the live check: a forecast whose days have all happened
            T0 = _d(x["T"])
            for hz in F.HORIZONS:
                pv = x.get("p%d" % hz)
                if pv is None or T0 + timedelta(days=hz) > last:
                    continue
                act = sum((app["days"].get(T0 + timedelta(days=i)) or {}).get("rev") or 0 for i in range(1, hz + 1))
                if act > 0:
                    checks.append({"made": x["made"], "h": hz, "pred": pv, "act": _r(act, 2), "err": _r(pv / act - 1, 4)})
        att = F.attribution(bt)
        log = list(old.get("log") or [])
        if prev_p != p or not log:
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
              "log": log[-15:], "checks": checks[-60:], "drv": drivers(app, rows, ida, cty_rows, rev_cty),
              "parts": _rx(f["parts"])}
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
    ratios of engine vd (every app's GA4 data, per Monday; none this build: the last ones kept) and vd's structure."""
    try:
        seas = F.season(run.pool) if run.pool else None
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
    return "forecast %s: ran %d, kept %d, skipped %d; tune %.0fs (max %.0fs); %.0fs" % (
        run.eng, run.ran, run.kept, run.skipped, sum(ts), max(ts) if ts else 0.0, run.clock() - run.t0)
