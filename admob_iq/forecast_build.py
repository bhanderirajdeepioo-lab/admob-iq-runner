"""🔮 Forecast — the build step, inside the ROI step (roi_build.app_step hands it the app's install days, AdMob revenue,
Google Ads spend and the install-day file it already has). Owner, 14 Oct 2026: revenue / spend / profit / breakeven for
the next months from the app's own past, AI back-testing that learns from its misses, the start of the real run picked
by itself (the trial / organic first days left out) and changeable from the dashboard (config/forecast_starts.json).

Per app, at most once a day (EVERY_H) and within the build's BUDGET_SEC (an app left over keeps yesterday's run):
  inputs → engine.forecast: tune (back-tests from the newest year of origins) → calibrate (bias, P10–P90, accuracy of
  every test and of the normal ones, how often a sudden change hit) → the forecast from the last complete day, 180 days,
  in three parts (old users / organic installs / paid installs at the last 30 days' spend) so the page's spend slider is
  exact; the bias correction folded into the days.
Kept for good in the private repo (data/forecast/<key>.json): the parameters, the tests, the learning log (what changed
and why, the newest LOG_KEEP), and every day's own forecast of the next 30 / 90 / 180 days — once those days have
happened the page shows that live error too (the real check, beyond the back-tests).
The portfolio's month-of-year season (every app pooled) is kept in data/forecast/state.json, refreshed at the end.
"""
import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone

from .engine import forecast as F

DIR = "forecast"
V = 1
BUDGET_SEC = 120
EVERY_H = 20
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


class Run:
    def __init__(self, data_dir, now, clock):
        self.data_dir, self.now, self.clock, self.t0 = data_dir, now, clock, clock()
        st = _read(_path(data_dir, "state.json"), {})
        self.season = {int(k): float(v) for k, v in (st.get("season") or {}).items()} or None
        self.starts = starts(data_dir)
        self.pool = {}
        self.ran = self.kept = self.skipped = 0

    def left(self):
        return BUDGET_SEC - (self.clock() - self.t0)


def start(data_dir, now=None, clock=time.monotonic):
    return Run(data_dir, now or datetime.now(timezone.utc), clock)


# ── inputs ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def inputs(rows, P, ida, life, life_till):
    """The engine's app: coh {X: {n, d, df, u, uf, t, ul}}, days {D: {rev, sp, spi, n, na, dau}}, last."""
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
    return {"coh": coh, "days": days, "last": till or (max(days) if days else S)}


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


def drivers(app, rows, ida, cty_rows):
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
    return out


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


def app_step(run, aid, key, rows, P, ida, life, life_till, cty_rows):
    """→ the page's forecast for this app (None: nothing yet). Never raises."""
    try:
        app = inputs(rows, P, ida, life, life_till)
        for D, e in app["days"].items():                 # the portfolio season, pooled from every app
            if e.get("rev") and e.get("dau"):
                p = run.pool.setdefault(D, {"rev": 0.0, "dau": 0.0})
                p["rev"] += e["rev"]
                p["dau"] += e["dau"]
        with_n = {D: e for D, e in app["days"].items() if e.get("n") is not None}
        if not with_n:
            return None
        auto = F.auto_start(with_n)
        mine = run.starts.get(aid)
        app["start"] = mine if mine and auto and mine >= min(with_n) else auto
        path = _path(run.data_dir, key + ".json")
        old = _read(path, {})
        today = _iso(run.now.date())
        fresh = (old.get("v") == V and old.get("start") == _iso(app["start"]) and old.get("T") == _iso(app["last"])
                 and old.get("made_at") and (run.now - datetime.fromisoformat(old["made_at"])).total_seconds() < EVERY_H * 3600)
        if fresh or run.left() <= 0:
            if old.get("v") == V and old.get("fc"):
                run.kept += 1
                return old["fc"]
            if run.left() <= 0:
                run.skipped += 1
                return None
        seas = run.season or F.season(app["days"])
        prev_p = old.get("p") if old.get("v") == V else None
        p, bt, steps = F.tune(app, seas, start_p=prev_p)
        sc_prev = F.score(F.backtest(app, prev_p, seas)) if prev_p and prev_p != p else None
        cal = F.calibrate(bt)
        f = F.forecast(app, app["last"], p, h=F.H, seas=seas)
        fac = corrected(f["rev"], cal)
        ser = {k: [_r(v * fac[i], 4) for i, v in enumerate(f["rev"][k])] for k in ("old", "org", "paid")}
        last = app["last"]
        hist0 = last - timedelta(days=HIST_DAYS - 1)
        hd = [app["days"].get(hist0 + timedelta(days=i)) or {} for i in range(HIST_DAYS)]
        k30 = [app["days"].get(last - timedelta(days=i)) or {} for i in range(30)]
        spi_day = sum(e.get("spi") or 0 for e in k30) / 30.0
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
            log.append({"d": today, "p": p, "sc_old": _r(sc_prev, 4), "sc": _r(F.score(bt), 4),
                        "changed": sorted(k for k in p if (prev_p or {}).get(k) != p[k]) if prev_p else [],
                        "cause": cause, "bias30": _r((cal.get(30) or {}).get("bias"), 4)})
        log = log[-LOG_KEEP:]
        fc = {"v": V, "made": today, "T": _iso(last), "start": _iso(app["start"]), "start_auto": _iso(auto) if auto else None,
              "start_set": _iso(mine) if mine else None, "p": p, "ready": ready, "ready_from": ready_from,
              "cal": {str(h): {k: (_r(v, 4) if isinstance(v, float) else v) for k, v in c.items()} for h, c in cal.items()},
              "f": {"d0": _iso(last + timedelta(days=1)), **ser, "dau": [_r(v, 1) for v in f["dau"]],
                    "n": [_r(v, 1) for v in f["n"]], "sp": [_r(v, 4) for v in f["sp"]], "spi": _r(spi_day, 2)},
              "hist": {"d0": _iso(hist0), "rev": [_r(e.get("rev"), 4) for e in hd], "sp": [_r(e.get("sp"), 4) for e in hd],
                       "spi": [_r(e.get("spi"), 2) for e in hd], "dau": [e.get("dau") for e in hd],
                       "n": [e.get("n") for e in hd]},
              "bt": [[r["T"]] + [(_r(r["h"][hz]["err"], 4) if hz in r["h"] else None) for hz in F.HORIZONS]
                     + [sorted((r.get("ev") or {}).keys())] for r in bt],
              "events": _events(bt), "att": {k: _r(v, 3) for k, v in att.items()} if att else None,
              "log": log[-15:], "checks": checks[-60:], "drv": drivers(app, rows, ida, cty_rows),
              "parts": {k: _r(v, 6) if isinstance(v, float) else v for k, v in f["parts"].items()}}
        _write(path, {"v": V, "made_at": run.now.isoformat(), "start": _iso(app["start"]), "T": _iso(last), "p": p,
                      "log": log, "live": live, "fc": fc})
        run.ran += 1
        return fc
    except Exception:
        run.skipped += 1
        return None


def finish(run):
    """The portfolio season for tomorrow's runs (every app's revenue ÷ DAU by month, pooled)."""
    try:
        seas = F.season(run.pool) if run.pool else None
        if seas:
            _write(_path(run.data_dir, "state.json"), {"v": V, "season": {str(k): _r(v, 4) for k, v in seas.items()}})
    except Exception:
        pass


def line(run):
    return "forecast: ran %d, kept %d, skipped %d" % (run.ran, run.kept, run.skipped)
