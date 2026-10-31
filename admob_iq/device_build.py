"""📱 Devices — the "dev" block of an app's ROI file (roi_<key>.json.gz), built inside roi_build.app_step from the private
store of fetch.ga4_device (owner, 31 Oct 2026, approved as proposed: Device · Status · Installs (paid %) · Avg cost/install
≈ · ROAS 7d / 30d / 90d · Money back · Back next day, with a Country filter; beside 🌍 Countries).

Per phone model, for All countries and for each country with enough installs:
  installs      the 7-day window's install days (fetch.ga4_device.windows: the newest WIN days whose age 7 is complete)
  paid %        paid installs ÷ installs (GA4: a real Google Ads campaign id as the user's first campaign)
  cost          Google Ads cost by country × install day (the 🌍 Countries cost, roi_build._geo_app) spread over that
                day-country's GA4 paid installs, each model its share (cost per paid install of the cell × the model's
                paid installs) — an average of the cell, never measured per model (Google reports no model) → "≈"
  ROAS A        revenue to age A (AdMob-matched: × the app's own AdMob ÷ GA4 of the install month) ÷ cost, over the
                A-day window's install days (7: the newest, 30 / 90: older ones whose age is complete)
  money back    the first of 7 / 30 / 90 whose ROAS ≥ 100 %; else the app's own curve beyond 90 days (its install days'
                revenue at 180 / 365 ÷ at 90) → "≈ 180 din" / "≈ 1 saal" / "1 saal me nahi"
  back next day users of the 7-day window back on day 1 ÷ its installs
  status        Profit (money back by day 90) · No ads (no Google Ads cost on these installs) · Slow (not by 90, by a year on the app's curve — or no
                curve to tell) · Loss (not by a year on the app's curve) · Too little data (< JUDGE installs in the
                window judged on) — judged on the 90-day window, else the 30-day one (marked "≈30")
Coverage: each kind's Σ model rows ÷ the same read without the split, over its window (GA4 folds part of a day into
"(other)" on the biggest apps; the page warns under COV_OK). The cost of a cell is spread over its paid installs scaled
by the day's paid coverage, so a folded day does not raise the models' cost per install.
"""
from datetime import timedelta

from .fetch import ga4_device as gd
from .fetch import ga4_uninstall as gu

JUDGE = 300                         # installs in the window judged on before a status
MIN_ROW = 30                        # installs (7-day window) for a model's own row …
MIN_CC = 500                        # … a country's own device list needs this many installs
MAX_CC = 40                         # at most this many countries get a list (the biggest)
COV_OK = 0.98


def _r(v, n=4):
    return None if v is None else round(v, n)


def _xs(store, kind, a, b):
    """The install days of [a, b] that have the kind read → [(X date, record)]."""
    out = []
    for k, rec in (store.get("x") or {}).items():
        d = gu._d(k)
        if a <= d <= b and kind in (rec or {}):
            out.append((d, rec[kind]))
    return sorted(out, key=lambda t: t[0])


def coverage(recs, rev=False):
    """Σ split ÷ Σ truth over the records (rev: the revenue of an R read, else its first value)."""
    s = t = 0.0
    for _, rec in recs:
        tr = rec.get("t")
        if tr is None:
            continue
        tv = (tr[1] if rev else tr[0]) if isinstance(tr, list) else tr
        for cmap in (rec.get("m") or {}).values():
            for v in cmap.values():
                s += (v[1] if rev else v[0]) if isinstance(v, list) else v
        t += float(tv or 0)
    return _r(s / t) if t > 0 else None


class _Acc:
    """Sums of one window by (model, cc): installs, revenue, paid, cost, back next day."""

    def __init__(self):
        self.n, self.rev, self.p, self.cost, self.d1 = {}, {}, {}, {}, {}

    @staticmethod
    def add(d, key, v):
        d[key] = d.get(key, 0.0) + v


def _window(store, age, a, b, cost, unk, kmon, with_d1):
    """One window → (_Acc, the install days, cost known for all of them?)."""
    acc = _Acc()
    days = set()
    for X, rec in _xs(store, "R%d" % age, a, b):
        days.add(X)
        k = kmon(X) or 1.0
        for md, cmap in (rec.get("m") or {}).items():
            for cc, v in cmap.items():
                acc.add(acc.n, (md, cc), float(v[0] or 0))
                acc.add(acc.rev, (md, cc), float(v[1] or 0) * k)
    known = True
    for X, rec in _xs(store, "P", a, b):
        if X not in days:
            continue
        m = rec.get("m") or {}
        tot = {}
        for md, cmap in m.items():
            for cc, v in cmap.items():
                acc.add(acc.p, (md, cc), float(v or 0))
                tot[cc] = tot.get(cc, 0.0) + float(v or 0)
        tr = rec.get("t")
        s = sum(tot.values())
        cov = (s / float(tr)) if tr else 1.0
        cov = cov if 0 < cov < 1 else 1.0               # a folded day: the cell's paid installs scaled back up
        if X in unk:
            known = False
            continue
        for cc, ptot in tot.items():
            c = (cost.get(cc) or {}).get(X)
            if not c or ptot <= 0:
                continue
            cpi = c / (ptot / cov)
            for md, cmap in m.items():
                pv = float(cmap.get(cc) or 0)
                if pv:
                    acc.add(acc.cost, (md, cc), pv * cpi)
    if with_d1:
        for X, rec in _xs(store, "D1", a, b):
            if X not in days:
                continue
            for md, cmap in (rec.get("m") or {}).items():
                for cc, v in cmap.items():
                    acc.add(acc.d1, (md, cc), float(v or 0))
    return acc, days, known


def _sum_by(acc, keep):
    """(model, cc) sums → the model's, over the countries keep(cc) says yes to: {model: {n, rev, p, cost, d1}}."""
    out = {}
    for name, d in (("n", acc.n), ("rev", acc.rev), ("p", acc.p), ("cost", acc.cost), ("d1", acc.d1)):
        for (md, cc), v in d.items():
            if keep(cc):
                e = out.setdefault(md, {"n": 0.0, "rev": 0.0, "p": 0.0, "cost": 0.0, "d1": 0.0})
                e[name] += v
    return out


def _roas(e):
    return (e["rev"] / e["cost"]) if e and e["cost"] > 0 else None


def payback(r7, r30, r90, curve):
    """→ (label code, projected?): "7" / "30" / "90" (paid back by that age), "180" / "365" (≈, the app's curve), "never"
    (not by a year on the curve), None (not known)."""
    for age, r in ((7, r7), (30, r30), (90, r90)):
        if r is not None and r >= 1:
            return str(age), False
    base = r90 if r90 is not None else r30
    src = 90 if r90 is not None else 30
    if base is None or not curve:
        return None, False
    for age in (180, 365):
        m = curve.get("%d_%d" % (src, age))
        if m is None:
            return None, False
        if base * m >= 1:
            return str(age), True
    return "never", True


def status(e30, e90, r30, r90, curve):
    """→ (status, judged on: "90" | "30" | None)."""
    on = "90" if e90 and e90["n"] >= JUDGE else ("30" if e30 and e30["n"] >= JUDGE else None)
    if on is None:
        return "Too little data", None
    e, r = (e90, r90) if on == "90" else (e30, r30)
    if e["cost"] <= 0:                              # no Google Ads cost on these installs: nothing to pay back
        return "No ads", on
    if r is not None and r >= 1:
        return "Profit", on
    m = (curve or {}).get("%s_365" % on)
    if m is None:
        return "Slow", on
    return ("Slow" if r * m >= 1 else "Loss"), on


def _rows(W, keep, curve, min_row):
    s7, s30, s90 = (_sum_by(W[a][0], keep) for a in gd.AGES)
    rows, rest_n, rest_m, tot_n = [], 0.0, 0, 0.0
    for md in sorted(set(s7) | set(s30) | set(s90)):
        e7, e30, e90 = s7.get(md), s30.get(md), s90.get(md)
        n7 = e7["n"] if e7 else 0.0
        tot_n += n7
        if n7 < min_row or md in ("(other)", "(not set)"):
            rest_n += n7
            rest_m += 1 if n7 > 0 else 0
            continue
        r7, r30, r90 = _roas(e7), _roas(e30), _roas(e90)
        st, on = status(e30, e90, r30, r90, curve)
        pb, proj = payback(r7, r30, r90, curve)
        rows.append({"m": md, "n": int(round(n7)), "ps": _r(e7["p"] / n7) if n7 else None,
                     "cpi": _r(e7["cost"] / e7["p"]) if e7 and e7["p"] > 0 and e7["cost"] > 0 else None,
                     "cost": _r(e7["cost"], 2) if e7 else None, "rev": _r(e7["rev"], 2) if e7 else None,
                     "r7": _r(r7), "r30": _r(r30), "r90": _r(r90),
                     "n30": int(round(e30["n"])) if e30 else 0, "n90": int(round(e90["n"])) if e90 else 0,
                     "d1": _r(e7["d1"] / n7) if e7 and n7 and W[7][3] else None,
                     "pb": pb, "px": proj, "st": st, "on": on})
    rows.sort(key=lambda x: -x["n"])
    return rows, {"n": int(round(rest_n)), "models": rest_m, "share": _r(rest_n / tot_n) if tot_n else None}


def dev_block(store, cost, unk, kmon, curve):
    """The app's device store + Google Ads cost {cc: {X date: USD}} (unk: install days whose country split is unknown)
    + kmon(X) (AdMob ÷ GA4 of the install day's month) + curve {"90_180", "90_365", "30_180", "30_365": the app's own
    revenue ratio} → the "dev" block, or None (no read yet)."""
    if not store or not store.get("F") or not store.get("x"):
        return None
    f = gu._d(store["F"])
    win = gd.windows(f)
    W = {}
    for age, (a, b) in win.items():
        acc, days, known = _window(store, age, a, b, cost, unk, kmon, with_d1=(age == 7))
        W[age] = (acc, days, known, bool(_xs(store, "D1", a, b)))
    if not any(W[a][1] for a in gd.AGES):
        return None
    cov = {}
    for age, (a, b) in win.items():
        cov["R%d" % age] = coverage(_xs(store, "R%d" % age, a, b), rev=True)
        cov["n%d" % age] = coverage(_xs(store, "R%d" % age, a, b))
    a7, b7 = win[7]
    cov["P"] = coverage(_xs(store, "P", a7, b7))
    cov["D1"] = coverage(_xs(store, "D1", a7, b7))
    rows, rest = _rows(W, lambda cc: True, curve, MIN_ROW)
    by_cc = {}
    for (md, cc), v in W[7][0].n.items():
        by_cc[cc] = by_cc.get(cc, 0.0) + v
    ccs = [cc for cc, n in sorted(by_cc.items(), key=lambda t: -t[1]) if n >= MIN_CC and cc not in ("(other)", "(not set)")]
    ccs = ccs[:MAX_CC]
    per = {}
    for cc in ccs:
        r, rs = _rows(W, lambda c, cc=cc: c == cc, curve, MIN_ROW)
        per[cc] = {"rows": r, "rest": rs, "n": int(round(by_cc[cc]))}
    names = store.get("names") or {}
    used = {x["m"] for x in rows} | {x["m"] for v in per.values() for x in v["rows"]}
    return {"F": store["F"], "win": {str(a): [w[0].isoformat(), w[1].isoformat()] for a, w in win.items()},
            "days": {str(a): len(W[a][1]) for a in gd.AGES}, "known": {str(a): W[a][2] for a in gd.AGES},
            "cov": cov, "cov_ok": COV_OK, "judge": JUDGE, "min_row": MIN_ROW,
            "names": {m: names[m] for m in sorted(used) if m in names},
            "rows": rows, "rest": rest, "cc": [[cc, per[cc]["n"]] for cc in ccs], "by": per,
            "curve": {k: _r(v) for k, v in (curve or {}).items()}}


def curve_of(rows, T):
    """The app's own revenue curve beyond 30 / 90 days from its ROI install-day rows (each r["t"]: revenue to the ages
    T): Σ revenue at 180 / 365 ÷ Σ at 30 / 90 over the install days that reached the later age → {"90_365": …}."""
    out = {}
    try:
        ix = {t: T.index(t) for t in (30, 90, 180, 365)}
    except ValueError:
        return out
    for src in (30, 90):
        for age in (180, 365):
            num = den = 0.0
            for r in rows or []:
                t = r.get("t") or []
                a, b = t[ix[src]] if len(t) > ix[src] else None, t[ix[age]] if len(t) > ix[age] else None
                if a is None or b is None or a <= 0:
                    continue
                num += b
                den += a
            if den > 0:
                out["%d_%d" % (src, age)] = max(1.0, num / den)
    return out
