"""📱 Devices — the "dev" block of an app's ROI file (roi_<key>.json.gz), built inside roi_build.app_step from the private
store of fetch.ga4_device (owner, 31 Oct 2026, approved as proposed: Device · Status · Installs (paid %) · Avg cost/install
≈ · ROAS 7d / 30d / 90d · Money back · Back next day, with a Country filter; beside 🌍 Countries).

PERIOD VIEW (owner, 31 Oct 2026: "7/30/90 esa nahi, uppar jo time period he uske hisab se"; picked: "us period ke
installs ki ab tak ki kamai"): per period of install days (Today · Yesterday · 7 / 30 days · This / Last month · 90
days, the app's own days) and per model — installs, paid installs, the Google Ads cost (as below), their revenue SO
FAR (fetch.ga4_device S: install day → today), back next day; the page shows CPI, revenue, revenue per install and it
÷ CPI. The verdict below (status, money back) stays the device's overall one, from the mature windows.

The verdict, per phone model, for All countries and for each country with enough installs:
  installs      the 7-day window's install days (fetch.ga4_device.windows: the newest WIN days whose age 7 is complete)
  paid %        paid installs ÷ installs (GA4: a real Google Ads campaign id as the user's first campaign)
  cost          Google Ads cost by country × install day (the 🌍 Countries cost, roi_build._geo_app) spread over that
                day-country's GA4 paid installs, each model its share (cost per paid install of the cell × the model's
                paid installs) — an average of the cell, never measured per model (Google reports no model) → "≈"
  ROAS A        revenue to age A (AdMob-matched: × the app's own AdMob ÷ GA4 of the install month) ÷ cost, over the
                A-day window's install days (7: the newest, 30 / 90: older ones whose age is complete)
  money back    the first of 7 / 30 / 90 whose ROAS ≥ 100 %; else the app's own curve beyond 90 days (its install days'
                revenue at 180 / 365 ÷ at 90) → "≈ 180 din" / "≈ 1 saal" / "1 saal me nahi"
  revenue       the 7-day window's installs' revenue to day 7; per user: each window's revenue to its age ÷ its installs
  back next day users of the 7-day window back on day 1 ÷ its installs
  KPI tiles     "tot" of each list (All countries, each country): every model's sums (the small ones too)
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
        self.pk = {}                                    # paid installs of the install days whose cost is known

    @staticmethod
    def add(d, key, v):
        d[key] = d.get(key, 0.0) + v


def _window(store, age, a, b, cost, unk, kmon, with_d1, rkind=None):
    """One window (or period: rkind "S", the revenue so far) → (_Acc, the install days, cost known for all of them?)."""
    acc = _Acc()
    days = set()
    for X, rec in _xs(store, rkind or "R%d" % age, a, b):
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
        if X in unk:                                    # Google Ads has not split this day's cost by country yet
            known = False
            continue
        for md, cmap in m.items():
            for cc, v in cmap.items():
                acc.add(acc.pk, (md, cc), float(v or 0))
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
    for name, d in (("n", acc.n), ("rev", acc.rev), ("p", acc.p), ("cost", acc.cost), ("d1", acc.d1), ("pk", acc.pk)):
        for (md, cc), v in d.items():
            if keep(cc):
                e = out.setdefault(md, {"n": 0.0, "rev": 0.0, "p": 0.0, "cost": 0.0, "d1": 0.0, "pk": 0.0})
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


# the owner's standard picker (3 Nov 2026), in his order — Custom is not offered here: a period's model × country sums are
# built per button (a free range would need every install day's model × country rows on the page)
PERIODS = (("today", "Today"), ("yday", "Yesterday"), ("7", "7 days"), ("tm", "This month"), ("lm", "Last month"),
           ("30", "30 days"), ("60", "60 days"), ("90", "90 days"), ("all", "All time"))
ROW_MIN = {"today": 5, "yday": 5, "7": 20}          # installs for a model's own row in a period (else MIN_ROW)
MONTHS_MAX = 12                                     # the month mover's calendar months (newest first)
MAX_ROWS, MAX_ROWS_CC = 800, 150                    # rows a period's list keeps (the rest summed in "rest")
MAX_ROWS_MON, MAX_ROWS_CC_MON = 300, 60             # … a calendar month's (12 of them: the file stays small)


def periods(today, first=None):
    """{period: (first install day, last install day)} — 7 / 30 / 60 / 90 days end yesterday (whole days); All time = the
    store's first install day (first; else 90 days back) … today."""
    m1 = today.replace(day=1)
    lm_end = m1 - timedelta(days=1)
    one = timedelta(days=1)
    out = {"today": (today, today), "yday": (today - one, today - one), "7": (today - 7 * one, today - one),
           "30": (today - 30 * one, today - one), "60": (today - 60 * one, today - one), "tm": (m1, today),
           "lm": (lm_end.replace(day=1), lm_end), "90": (today - 90 * one, today - one),
           "all": (min(first, today) if first else today - 90 * one, today)}
    # the month mover (owner, 4 Nov 2026: "picker me … month move <>"): every calendar month of the store, the newest
    # MONTHS_MAX ("mon:YYYY-MM" = its 1st … its last day; the current month: … today)
    m = m1
    for _ in range(MONTHS_MAX):
        if first and m < first.replace(day=1):
            break
        nxt = (m + timedelta(days=32)).replace(day=1)
        out["mon:%04d-%02d" % (m.year, m.month)] = (m, min(nxt - one, today))
        m = (m - one).replace(day=1)
    return out


def _plist(acc, keep, min_row, cap, d1n):
    """A period's (model, cc) sums → its rows [model, installs, paid, cost USD, revenue USD, back next day | None, paid
    installs of the days whose cost is known (the CPI's base)], the small models' rest and the list's totals."""
    by = _sum_by(acc, keep)
    dn = {}
    for (md, cc), v in d1n.items():
        if keep(cc):
            dn[md] = dn.get(md, 0.0) + v
    rows, tot = [], {"n": 0.0, "p": 0.0, "cost": 0.0, "rev": 0.0, "d1": 0.0, "dn": 0.0, "pk": 0.0}
    for md, e in by.items():
        for k in ("n", "p", "cost", "rev", "d1", "pk"):
            tot[k] += e[k]
        tot["dn"] += dn.get(md, 0.0)
        if md in ("(other)", "(not set)"):
            continue
        rows.append([md, int(round(e["n"])), int(round(e["p"])), _r(e["cost"], 2), _r(e["rev"], 2),
                     _r(e["d1"] / dn[md]) if dn.get(md) else None, int(round(e["pk"]))])
    rows.sort(key=lambda x: -x[1])
    keep_rows = [x for x in rows if x[1] >= min_row][:cap]
    shown = sum(x[1] for x in keep_rows)
    rest_n = tot["n"] - shown
    out_tot = {"n": int(round(tot["n"])), "p": int(round(tot["p"])), "cost": _r(tot["cost"], 2), "rev": _r(tot["rev"], 2),
               "d1": _r(tot["d1"] / tot["dn"]) if tot["dn"] else None, "pk": int(round(tot["pk"]))}
    return keep_rows, {"n": int(round(rest_n)), "models": len(rows) - len(keep_rows),
                       "share": _r(rest_n / tot["n"]) if tot["n"] else None}, out_tot


def _verdicts(W, keep, curve):
    """{model: [status, judged on, money back, projected?]} of a list — the device's overall verdict (mature installs:
    the 30 / 90-day windows), the same in every period."""
    s7, s30, s90 = (_sum_by(W[a][0], keep) for a in gd.AGES)
    out = {}
    for md in set(s7) | set(s30) | set(s90):
        if md in ("(other)", "(not set)"):
            continue
        e7, e30, e90 = s7.get(md), s30.get(md), s90.get(md)
        r7, r30, r90 = _roas(e7), _roas(e30), _roas(e90)
        st, on = status(e30, e90, r30, r90, curve)
        pb, proj = payback(r7, r30, r90, curve)
        out[md] = [st, on, pb, proj]
    return out


def dev_block(store, cost, unk, kmon, curve):
    """The app's device store + Google Ads cost {cc: {X date: USD}} (unk: install days whose country split is unknown)
    + kmon(X) (AdMob ÷ GA4 of the install day's month) + curve {"90_180", "90_365", "30_180", "30_365": the app's own
    revenue ratio} → the "dev" block, or None (no read yet).
    Per PERIOD of install days (owner, 31 Oct 2026: the period picker, not 7 / 30 / 90): installs, paid, Google Ads cost,
    their revenue SO FAR, back next day — for All countries and each country with enough installs; the verdict (status,
    money back) per model from the mature windows, the same in every period."""
    if not store or not store.get("F") or not store.get("x"):
        return None
    f = gu._d(store["F"])
    today = gu._d(store["today"]) if store.get("today") else f
    win = gd.windows(f)
    W = {}
    for age, (a, b) in win.items():
        acc, days, known = _window(store, age, a, b, cost, unk, kmon, with_d1=(age == 7))
        W[age] = (acc, days, known, bool(_xs(store, "D1", a, b)))
    xd = [gu._d(k) for k in (store.get("x") or {})]
    pr = periods(today, min(xd) if xd else None)
    Pacc = {}
    for pid, (a, b) in pr.items():
        acc, days, known = _window(store, None, a, b, cost, unk, kmon, with_d1=True, rkind="S")
        d1n = {}                                        # installs of the install days with a back next day read
        dd = {X for X, _ in _xs(store, "D1", a, b)} & days
        for X, rec in _xs(store, "S", a, b):
            if X in dd:
                for md, cmap in (rec.get("m") or {}).items():
                    for cc, v in cmap.items():
                        d1n[(md, cc)] = d1n.get((md, cc), 0.0) + float(v[0] or 0)
        Pacc[pid] = (acc, days, known, d1n)
    if not any(Pacc[p][1] for p in Pacc) and not any(W[a][1] for a in gd.AGES):
        return None
    cov = {}
    for age, (a, b) in win.items():
        cov["R%d" % age] = coverage(_xs(store, "R%d" % age, a, b), rev=True)
    a30, b30 = pr["30"]
    cov["S"] = coverage(_xs(store, "S", a30, b30), rev=True)
    cov["n"] = coverage(_xs(store, "S", a30, b30))
    cov["P"] = coverage(_xs(store, "P", a30, b30))
    by_cc = {}                                          # the countries' order and lists: by the 30 days' installs
    for (md, cc), v in Pacc["30"][0].n.items():
        by_cc[cc] = by_cc.get(cc, 0.0) + v
    ccs = [cc for cc, n in sorted(by_cc.items(), key=lambda t: -t[1])
           if n >= MIN_CC and cc not in ("(other)", "(not set)")][:MAX_CC]
    out_p, used = {}, set()
    for pid, (acc, days, known, d1n) in Pacc.items():
        mr = ROW_MIN.get(pid, MIN_ROW)
        mon = pid.startswith("mon:")
        rows, rest, tot = _plist(acc, lambda c: True, mr, MAX_ROWS_MON if mon else MAX_ROWS, d1n)
        by = {}
        for cc in ccs:
            r, rs, tt = _plist(acc, lambda c, cc=cc: c == cc, mr, MAX_ROWS_CC_MON if mon else MAX_ROWS_CC, d1n)
            by[cc] = {"rows": r, "rest": rs, "tot": tt}
            used.update(x[0] for x in r)
        used.update(x[0] for x in rows)
        nounk = sum(1 for X in days if X in unk)
        out_p[pid] = {"rows": rows, "rest": rest, "tot": tot, "by": by, "days": len(days), "known": known, "nocost": nounk,
                      "from": pr[pid][0].isoformat(), "to": pr[pid][1].isoformat()}
    V = _verdicts(W, lambda c: True, curve)
    Vc = {cc: {m: v for m, v in _verdicts(W, lambda c, cc=cc: c == cc, curve).items() if m in used} for cc in ccs}
    names = store.get("names") or {}
    return {"v": 2, "F": store["F"], "today": today.isoformat(),
            "win": {str(a): [w[0].isoformat(), w[1].isoformat()] for a, w in win.items()},
            "wdays": {str(a): len(W[a][1]) for a in gd.AGES}, "cov": cov, "cov_ok": COV_OK, "judge": JUDGE,
            "periods": [[pid, lab] for pid, lab in PERIODS], "P": out_p,
            "V": {m: v for m, v in V.items() if m in used}, "Vc": Vc,
            "vcount": {k: sum(1 for v in V.values() if v[0] == k) for k in ("Loss", "Slow", "Profit", "No ads",
                                                                         "Too little data")},
            "cc": [[cc, int(round(by_cc[cc]))] for cc in ccs],
            "names": {m: names[m] for m in sorted(used) if m in names},
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


# ═══ v3 (owner, 6 Nov 2026: "muje all time ka chahiye jab se app start hui he") ══════════════════════════════════════
# Every install day since the app's first one (the store v2: recent + month files; the history job fills the old ones)
# for ANY window: the build sums per-install-day CELLS (model × country) — never a cap before the sum — so every
# standard button, All time, the month mover and Custom come out exact.
#   cell  [installs n, paid p, cost USD, revenue so far USD (× the install month's AdMob ÷ GA4), back next day d1,
#          installs of the days with a D1 read dn, paid installs of the days whose Google Ads cost is known pk]
#         — the same rules as _window, one install day at a time
#   unit  U: per install day / month / period — calendar days y (first … today), days filled d (S and P read, and D1
#         unless the day is today), days with S s, days without a Google Ads country split nc, days whose install month
#         has no AdMob match kq, the oldest "to" of their revenue so far, and the coverage sums (S revenue / installs
#         and P: Σ split, Σ truth)
# Files (all under the /roi* header rule):
#   roi_<key>_dv.json.gz          the 9 standard buttons (capped lists + rest + totals, All countries and each country
#                                 offered), the verdicts, the countries (by All time installs), every model's name, the
#                                 months' units and their files' sha1-12, the history job's state — read when 📱 Devices
#                                 opens; the ROI file's "dev" is a stub pointing at it
#   roi_<key>_dvm_<YYYY-MM>.json.gz  the month's cells (every model × country, uncapped) — the mover / Custom
#   roi_<key>_dvd_<YYYY-MM>.json.gz  the month's cells per install day — Custom's partial edge months only
# The month cache (private, data/ga4_device/<key>/agg.json.gz): a month older than the hourly fetch's window is built
# again only when its key changes (its month file's sha1 + size, its recent days' read times, its cost slice, unknown
# days, AdMob factor and match, the first day, CODE_V); the cold months' cells are summed once into "tot" (All time =
# tot + the hot months). A file over MAX_GZ is not written (the month's last good copy stays whole; no copy: the
# index marks the month as a gap, the page warns; "devices skipped: TooBigError"); an unreadable store month the same
# ("devices skipped: StoreError"), never built as an empty month.
import gzip as _gzip
import hashlib as _hashlib
import io as _io
import json as _json
import os as _os
import sys as _sys

DV_V = 3
AGG_V = 1
CODE_V = 1                          # the cells' / units' rules or the files' shape: a change builds every month again (once)
MAX_GZ = 20 * 1024 * 1024           # a site file larger than this is not written (the deploy guard's limit is 25 MiB)
STD = (("today", "Today"), ("yday", "Yesterday"), ("7", "Last 7 days"), ("tm", "This month"), ("lm", "Last month"),
       ("30", "Last 30 days"), ("60", "Last 60 days"), ("90", "Last 90 days"), ("all", "All time"), ("cus", "Custom"))
U = ("y", "d", "s", "nc", "kq", "to", "sr", "tr", "sn", "tn", "sp", "tp")
NUM = 7
FOLDS = ("(other)", "(not set)")


class TooBigError(Exception):
    """A Devices site file over MAX_GZ: not written (the page keeps the last good copy)."""


def _sha12(raw):
    return _hashlib.sha1(raw).hexdigest()[:12]


def _dumps(obj):
    return _json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _gz(raw):
    """Deterministic gzip (no name, no time) at level 6: the current month's files are written again every build — a
    few % bigger than level 9 at a third of its time."""
    buf = _io.BytesIO()
    with _gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=6) as g:
        g.write(raw)
    return buf.getvalue()


def _gz_new(path, raw):
    """(gzip of raw, None) — or (None, gz bytes on disk) when `path` already holds exactly raw."""
    try:
        with open(path, "rb") as fh:
            old = fh.read()
        if _gzip.decompress(old) == raw:
            return None, len(old)
    except Exception:
        pass
    return _gz(raw), None


def _put_gz(path, z):
    _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
    with open(path + ".tmp", "wb") as fh:
        fh.write(z)
    _os.replace(path + ".tmp", path)


def put_file(path, raw, max_gz=None):
    """raw JSON bytes → `path` as deterministic gzip, only when the content changed → (sha1-12, gz bytes on disk).
    TooBigError (nothing written) when its gzip is over max_gz (MAX_GZ)."""
    z, n = _gz_new(path, raw)
    if z is None:
        return _sha12(raw), n
    if len(z) > (MAX_GZ if max_gz is None else max_gz):
        raise TooBigError()
    _put_gz(path, z)
    return _sha12(raw), len(z)


def _num(v):
    v = round(float(v), 4)
    return int(v) if v.is_integer() else v


def unit0(y=0):
    return [y, 0, 0, 0, 0, None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def unit_add(a, b):
    """Σ of two units (to: the older)."""
    out = list(a)
    for i, v in enumerate(b):
        if i == 5:
            if v and (out[5] is None or v < out[5]):
                out[5] = v
        else:
            out[i] = out[i] + (v or 0)
    return out


def unit_out(u):
    return [u[0], u[1], u[2], u[3], u[4], u[5]] + [_num(v) for v in u[6:]]


def day_cells(recs, X, cost, unk, k, today, kq):
    """One install day's records → ({(model, cc): cell}, its unit) — _window's rules for one day (cost of a cell spread
    over its paid installs, scaled back up on a folded day; no cost and no pk on a day Google Ads has not split).
    Counts stay GA4's numbers; cost and revenue are rounded to 4 decimals (USD 0.0001) — what the files carry."""
    u = unit0(1)
    S = recs.get("S") if isinstance(recs, dict) else None
    if not isinstance(S, dict):
        return {}, u
    P, D = recs.get("P"), recs.get("D1")
    P = P if isinstance(P, dict) else None
    D = D if isinstance(D, dict) else None
    out = {}
    sr = sn = 0.0
    wd = D is not None
    for md, cmap in (S.get("m") or {}).items():
        for cc, v in (cmap or {}).items():
            n, rv = v[0] or 0, v[1] or 0
            out[(md, cc)] = [n, 0, 0.0, rv * k, 0, n if wd else 0, 0]
            sr += rv
            sn += n
    t = S.get("t")
    if isinstance(t, list) and len(t) == 2:
        u[6], u[7], u[8], u[9] = sr, float(t[1] or 0), sn, float(t[0] or 0)
    if P is not None:
        m = P.get("m") or {}
        tot = {}
        cells = []
        for md, cmap in m.items():
            for cc, v in (cmap or {}).items():
                pv = v or 0
                e = out.get((md, cc))
                if e is None:
                    e = out[(md, cc)] = [0, 0, 0.0, 0.0, 0, 0, 0]
                e[1] += pv
                tot[cc] = tot.get(cc, 0) + pv
                cells.append((e, cc, pv))
        s = sum(tot.values())
        tr = P.get("t")
        if tr is not None:
            u[10], u[11] = float(s), float(tr or 0)
        cov = (s / float(tr)) if tr else 1.0
        cov = cov if 0 < cov < 1 else 1.0
        if X not in unk:
            cpi = {}
            for cc, ptot in tot.items():
                c = (cost.get(cc) or {}).get(X)
                if c and ptot > 0:
                    cpi[cc] = c / (ptot / cov)
            for e, cc, pv in cells:
                e[6] += pv
                if pv and cc in cpi:
                    e[2] += pv * cpi[cc]
    if D is not None:
        for md, cmap in (D.get("m") or {}).items():
            for cc, v in (cmap or {}).items():
                e = out.get((md, cc))
                if e is None:
                    e = out[(md, cc)] = [0, 0, 0.0, 0.0, 0, 0, 0]
                e[4] += v or 0
    for e in out.values():
        e[2] = round(e[2], 4)
        e[3] = round(e[3], 4)
    u[1] = 1 if P is not None and (D is not None or X >= today) else 0
    u[2] = 1
    u[3] = 1 if X in unk else 0
    u[4] = 1 if kq else 0
    u[5] = S.get("to")
    return out, u


def cells_add(acc, cells):
    for k, e in cells.items():
        a = acc.get(k)
        if a is None:
            acc[k] = list(e)
        else:
            for i in range(NUM):
                a[i] += e[i]
    return acc


def cells_round(cells):
    """A sum of cells → cost / revenue to 4 decimals again (counts are whole on GA4 data; a float sum of halves on
    made-up data is rounded the same way)."""
    for e in cells.values():
        e[2] = round(e[2], 4)
        e[3] = round(e[3], 4)
        for i in (0, 1, 4, 5, 6):
            v = e[i]
            if v.__class__ is float:
                e[i] = _num(v)
    return cells


class Dict:
    """Model / country dictionaries of one file (cells as [model index, country index, …])."""

    def __init__(self):
        self.md, self.cc, self.im, self.ic = [], [], {}, {}

    def enc(self, cells):
        out = []
        for (md, cc), e in cells.items():                # (the cells' own order: deterministic, as their records)
            i = self.im.get(md)
            if i is None:
                i = self.im[md] = len(self.md)
                self.md.append(md)
            j = self.ic.get(cc)
            if j is None:
                j = self.ic[cc] = len(self.cc)
                self.cc.append(cc)
            out.append([i, j] + list(e))
        return out


def dec(j, rows):
    """A file's cells back → {(model, cc): cell}."""
    md, cc = j.get("md") or [], j.get("cc") or []
    out = {}
    for r in rows or []:
        out[(md[r[0]], cc[r[1]])] = list(r[2:2 + NUM])
    return out


def _list(by, tot, min_row, cap):
    rows = [(md, e) for md, e in by.items() if md not in FOLDS]
    big = sorted(((md, e) for md, e in rows if e[0] >= min_row), key=lambda t: (-t[1][0], t[0]))[:cap]
    keep = [[md] + [_num(v) for v in e] for md, e in big]
    rest_n = tot[0] - sum(r[1] for r in keep)
    t = {k: _num(tot[i]) for i, k in enumerate(("n", "p", "cost", "rev", "d1", "dn", "pk"))}
    return keep, {"n": _num(rest_n), "models": len(rows) - len(keep), "share": _r(rest_n / tot[0]) if tot[0] else None}, t


def plists(cells, ccs, min_row=MIN_ROW, cap=MAX_ROWS, cap_cc=MAX_ROWS_CC):
    """A period's cells → All countries' (rows [model, n, p, cost, rev, d1, dn, pk] by installs, the rest {n, models,
    share}, the totals {n, p, cost, rev, d1, dn, pk}) and the same for each country of ccs — ONE pass over the cells;
    "(other)" / "(not set)" models count in the totals and the rest only. The page's Custom does the same (devList)."""
    want = set(ccs or ())
    by, tot, byc, totc = {}, [0.0] * NUM, {}, {}
    for (md, c), e in cells.items():
        a = by.get(md)
        if a is None:
            by[md] = list(e)
        else:
            for i in range(NUM):
                a[i] += e[i]
        for i in range(NUM):
            tot[i] += e[i]
        if c in want:
            d = byc.setdefault(c, {})
            a = d.get(md)
            if a is None:
                d[md] = list(e)
            else:
                for i in range(NUM):
                    a[i] += e[i]
            t = totc.get(c)
            if t is None:
                t = totc[c] = [0.0] * NUM
            for i in range(NUM):
                t[i] += e[i]
    out = {c: _list(byc.get(c) or {}, totc.get(c) or [0.0] * NUM, min_row, cap_cc) for c in ccs or ()}
    return _list(by, tot, min_row, cap), out


def plist(cells, cc=None, min_row=MIN_ROW, cap=MAX_ROWS):
    """One list of a period's cells (All countries, or one country) — plists' rules."""
    if cc is None:
        return plists(cells, (), min_row, cap)[0]
    return plists(cells, (cc,), min_row, cap, cap)[1][cc]


def _sum_by_cc(acc, ccs):
    """_sum_by for every country of ccs in ONE pass → {cc: {model: {n, rev, p, cost, d1, pk}}}."""
    want, out = set(ccs), {}
    for name, d in (("n", acc.n), ("rev", acc.rev), ("p", acc.p), ("cost", acc.cost), ("d1", acc.d1), ("pk", acc.pk)):
        for (md, cc), v in d.items():
            if cc in want:
                e = out.setdefault(cc, {}).setdefault(md, {"n": 0.0, "rev": 0.0, "p": 0.0, "cost": 0.0, "d1": 0.0,
                                                           "pk": 0.0})
                e[name] += v
    return out


def verdicts_cc(W, ccs, curve):
    """_verdicts of each country of ccs (one pass a window) → {cc: {model: [status, judged on, money back, projected?]}}."""
    by = [_sum_by_cc(W[a][0], ccs) for a in gd.AGES]
    out = {}
    for cc in ccs:
        s7, s30, s90 = (b.get(cc) or {} for b in by)
        v = {}
        for md in set(s7) | set(s30) | set(s90):
            if md in FOLDS:
                continue
            e7, e30, e90 = s7.get(md), s30.get(md), s90.get(md)
            r7, r30, r90 = _roas(e7), _roas(e30), _roas(e90)
            st, on = status(e30, e90, r30, r90, curve)
            pb, proj = payback(r7, r30, r90, curve)
            v[md] = [st, on, pb, proj]
        out[cc] = v
    return out


def _mon(d):
    return "%04d-%02d" % (d.year, d.month)


def _mdays(m):
    from datetime import date as _date
    a = _date(int(m[:4]), int(m[5:7]), 1)
    b = (a + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return a, b


def month_list(a, b):
    out, m = [], a.replace(day=1)
    while m <= b:
        out.append(_mon(m))
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def std_periods(today, first):
    """The owner's standard buttons → {key: (first install day, last)} — Last N days end yesterday (whole days); All time
    = the app's first install day … today."""
    p = periods(today, first)
    return {k: p[k] for k, _ in STD if k != "cus"}


def dv_name(key, kind, m=None):
    return "roi_%s_%s%s.json.gz" % (key, kind, ("_" + m) if m else "")


def cost_sigs(cost, unk):
    """The cost slice of every install month (+ its days without a split) → {YYYY-MM: sha1-12} (a month's cache key
    part; one pass over the cost)."""
    sl = {}
    for cc, byx in cost.items():
        for X, c in byx.items():
            if c:
                sl.setdefault(_mon(X), {}).setdefault(cc, {})[X.isoformat()] = round(c, 6)
    un = {}
    for X in unk:
        un.setdefault(_mon(X), []).append(X.isoformat())
    return {m: _sha12(_dumps([sl.get(m) or {}, sorted(un.get(m) or [])])) for m in set(sl) | set(un)}


def _read_json_gz(path):
    try:
        with _gzip.open(path, "rt", encoding="utf-8") as fh:
            return _json.load(fh)
    except Exception:
        return None


def agg_path(data_dir, key):
    return _os.path.join(data_dir, gd.DIR, key, "agg.json.gz")


def build_app(data_dir, key, cost, unk, kmon, kq, curve, first, out_dir, info=None, fkey=None):
    """The app's device store (v2 or v1; key: its file key) + Google Ads cost {cc: {X: USD}} (unk: days without a
    country split) + kmon(X) (AdMob ÷ GA4 of the install month) + kq(X) (that month has no AdMob match) + the app's
    curve + first (its first install day) → (the "dev" stub of the ROI file, the files written), or None (nothing read
    yet). fkey: the site files' key (the ROI file's; default key). info: counts gathered ({"rows", "months",
    "cached", "kb", "toobig", "changed"})."""
    from datetime import date as _date
    info = info if isinstance(info, dict) else {}
    skey, key = key, (fkey or key)
    root = _os.path.join(data_dir, gd.DIR)
    st = gd.Store(root, skey, strict=False)
    if st.meta is not None:
        view, mfiles = st.view(), st.months()
    else:
        view, mfiles = gd.load_v1(_os.path.join(root, skey + ".json.gz")) or {}, []
    if not view.get("F") or (not view.get("x") and not mfiles):
        return None
    f = gu._d(view["F"])
    today = gu._d(view["today"]) if view.get("today") else f
    recent = view.get("x") or {}
    rdays = sorted(recent)
    cands = [first] if first else []                    # the app's first install day (ROI's), or the store's
    s_days = [k for k in rdays if isinstance(recent[k], dict) and recent[k].get("S")]
    if s_days:
        cands.append(gu._d(s_days[0]))
    if not cands and mfiles:
        cands.append(_date(int(mfiles[0][:4]), int(mfiles[0][5:7]), 1))
    first = min(min(cands) if cands else (gu._d(rdays[0]) if rdays else today), today)
    # the verdict windows (mature installs): as v2
    win = gd.windows(f)
    W = {}
    for age, (a, b) in win.items():
        acc, days, known = _window(view, age, a, b, cost, unk, kmon, with_d1=(age == 7))
        W[age] = (acc, days, known, bool(_xs(view, "D1", a, b)))
    cov = {"R%d" % age: coverage(_xs(view, "R%d" % age, a, b), rev=True) for age, (a, b) in win.items()}
    hot0 = (today - timedelta(days=gd.RANGE_DAYS)).replace(day=1)       # months built fresh every build
    months = month_list(first, today)
    for m in mfiles + [k[:7] for k in rdays]:
        if m not in months and m >= _mon(first) and m <= _mon(today):
            months.append(m)
    months = sorted(set(months))
    rby = {}
    for k in rdays:
        rby.setdefault(k[:7], []).append(k)

    def kf(X):
        v = kmon(X)
        return v if v else 1.0

    def kqf(X):
        try:
            return bool(kq(X))
        except Exception:
            return False

    def month_days(m, recs):
        """A month's records → ({X: (cells, unit)}, month cells, month unit)."""
        a, b = _mdays(m)
        a, b = max(a, first), min(b, today)
        dd, mc, mu = {}, {}, unit0(0)
        X = a
        while X <= b:
            r = recs.get(X.isoformat())
            c, u = day_cells(r or {}, X, cost, unk, kf(X), today, kqf(X))
            dd[X.isoformat()] = (c, u)
            cells_add(mc, c)
            mu = unit_add(mu, u)
            X += timedelta(days=1)
        return dd, cells_round(mc), mu

    bad = []

    def mrecs(m):
        """A store month's records ({} when it has no file); None (counted, "devices skipped: StoreError" once) when
        its file is there but unreadable — never built (nor cached) as an empty month."""
        if m not in mfiles:
            return {}
        mp_ = gd.month_path(root, skey, m)
        j = gd._read_gz(mp_)
        if j is None and _os.path.exists(mp_):
            if not bad:
                print("devices skipped: StoreError", file=_sys.stderr)
            if m not in bad:
                bad.append(m)
                info["bad"] = info.get("bad", 0) + 1
            return None
        return dict((j or {}).get("x") or {})

    def mfile_cells(m, sha):
        """A month's cells back from its own dvm file (None: no file, or not the one of `sha`)."""
        j = _read_json_gz(_os.path.join(out_dir, dv_name(key, "dvm", m))) if sha else None
        return dec(j, j.get("c")) if j and _sha12(_dumps(j)) == sha else None

    csig = cost_sigs(cost, unk)
    agg = _read_json_gz(agg_path(data_dir, skey)) or {}
    if agg.get("v") != AGG_V or agg.get("code") != CODE_V or agg.get("first") != first.isoformat():
        agg = {}
    old = agg.get("months") or {}
    new_months, mcells, dcache, files, changed = {}, {}, {}, [], []
    kb = 0
    for m in months:
        a, b = _mdays(m)
        hot = a >= hot0
        recs_r = {k: recent[k] for k in rby.get(m, [])}
        fp = _sha12(_dumps(sorted((k, kd, (v or {}).get("at")) for k, rv in recs_r.items()
                                  for kd, v in (rv or {}).items() if kd in ("S", "P", "D1"))))
        msha = ((st.meta or {}).get("months") or {}).get(m)
        mp = gd.month_path(root, skey, m)
        size = _os.path.getsize(mp) if m in mfiles and _os.path.exists(mp) else 0
        k_m = _sha12(_dumps([msha, size, fp, csig.get(m), round(kf(max(a, first)), 6), kqf(max(a, first)),
                             first.isoformat(), today.isoformat() if b >= today else None, CODE_V]))
        e = old.get(m)
        pm, pd = _os.path.join(out_dir, dv_name(key, "dvm", m)), _os.path.join(out_dir, dv_name(key, "dvd", m))
        same = bool(e and e.get("k") == k_m and (not e.get("sm") or _os.path.exists(pm))
                    and (not e.get("sd") or _os.path.exists(pd)))
        if same and not hot:
            new_months[m] = e
            for nm, ok in ((dv_name(key, "dvm", m), e.get("sm")), (dv_name(key, "dvd", m), e.get("sd"))):
                if ok:
                    files.append(nm)
            info["cached"] = info.get("cached", 0) + 1
            continue
        recs = mrecs(m)
        broken = recs is None
        if broken and e and all(not e.get(sl) or _os.path.exists(pp) for sl, pp in (("sm", pm), ("sd", pd))):
            new_months[m] = dict(e, k=None)             # an unreadable store month: its last good files stay (never
            for nm, ok in ((dv_name(key, "dvm", m), e.get("sm")), (dv_name(key, "dvd", m), e.get("sd"))):
                if ok:                                  # cached as built; a cold one's cells: read back for "tot")
                    files.append(nm)
            if hot:
                mcells[m] = mfile_cells(m, e.get("sm")) or {}
            continue
        recs = recs or {}
        recs.update(recs_r)                             # (a day in both: the recent copy, as every reader)
        dd, mc, mu = month_days(m, recs)
        if hot:                                         # (a cold month's cells are read back from its file for "tot":
            dcache.update({X: v for X, v in dd.items()})        # every month's never held at once)
            mcells[m] = mc
        if same and not broken:                         # a hot month whose records did not change: its files stay
            new_months[m] = e
            for nm, ok in ((dv_name(key, "dvm", m), e.get("sm")), (dv_name(key, "dvd", m), e.get("sd"))):
                if ok:
                    files.append(nm)
            continue
        ent = {"k": None if broken else k_m, "u": unit_out(mu), "sm": None, "sd": None, "n": len(mc)}
        if broken:
            ent["gap"] = True                           # (the page: "this month's data is missing", never 0 in silence)
        if mc or any(u[2] for _, u in dd.values()):
            dz = Dict()
            dbody = {"v": DV_V, "key": key, "M": m, "u": unit_out(mu),
                     "X": {X: {"c": dz.enc(c), "u": unit_out(u)} for X, (c, u) in sorted(dd.items()) if u[2]}}
            dbody.update(md=dz.md, cc=dz.cc)
            mz = Dict()
            mbody = {"v": DV_V, "key": key, "M": m, "c": mz.enc(mc), "u": unit_out(mu)}
            mbody.update(md=mz.md, cc=mz.cc)
            prep = []                                   # both files checked before either is written
            for kind, body_, slot in (("dvd", dbody, "sd"), ("dvm", mbody, "sm")):
                nm = dv_name(key, kind, m)
                raw_ = _dumps(body_)
                z, n0 = _gz_new(_os.path.join(out_dir, nm), raw_)
                prep.append((nm, slot, _sha12(raw_), z, n0))
            dbody = mbody = body_ = raw_ = None
            if any(z is not None and len(z) > MAX_GZ for _, _, _, z, _ in prep):
                info["toobig"] = info.get("toobig", 0) + 1
                if e and all(not e.get(sl) or _os.path.exists(_os.path.join(out_dir, nm)) for nm, sl, _, _, _ in prep):
                    ent = dict(e, k=None)               # the last good copy stays WHOLE (its unit with its files);
                    for nm, sl, _, _, _ in prep:        # tried again next build, never cached as built
                        if ent.get(sl):
                            files.append(nm)
                else:                                   # no copy: the page says so (never 0 installs in silence)
                    ent.update(k=None, gap=True)
                    if not hot:
                        mcells[m] = mc                  # ("tot" has no file to read it back from)
            else:
                for nm, slot, sha, z, n0 in prep:
                    if z is not None:
                        _put_gz(_os.path.join(out_dir, nm), z)
                    ent[slot] = sha
                    kb += len(z) if z is not None else n0
                    files.append(nm)
            prep = None
        elif broken and not hot:
            mcells[m] = mc                              # (no file to read back: an empty month)
        new_months[m] = ent
        if not hot:
            changed.append(m)
    # All time = the cold months' cells (tot, kept summed in the cache) + the hot months'
    cold = [m for m in months if _mdays(m)[0] < hot0]
    of = [[m, new_months[m].get("sm"), new_months[m].get("k")] for m in cold]
    tot = None
    t0 = agg.get("tot") or {}
    if t0.get("of") == of:
        tot = dec(t0, t0.get("c"))
    else:
        tot = {}
        for m in cold:
            c = mcells.get(m)
            if c is None:                               # a cold month: its cells from its own file
                sm = new_months[m].get("sm")
                c = mfile_cells(m, sm) if sm else {}
                if c is None:
                    recs = mrecs(m) or {}
                    recs.update({k: recent[k] for k in rby.get(m, [])})
                    _, c, _ = month_days(m, recs)
            cells_add(tot, c)
        cells_round(tot)
    allc = {k: list(v) for k, v in tot.items()}
    for m in months:
        if _mdays(m)[0] >= hot0:
            cells_add(allc, mcells.get(m) or {})
    cells_round(allc)
    # the buttons
    pr = std_periods(today, first)
    by_cc = {}
    for (md, cc), e in allc.items():
        by_cc[cc] = by_cc.get(cc, 0.0) + e[0]
    ccs = [cc for cc, n in sorted(by_cc.items(), key=lambda t: (-t[1], t[0]))
           if n >= MIN_CC and cc not in FOLDS][:MAX_CC]
    def day(X):
        if X < first:
            return {}, unit0(0)
        got = dcache.get(X.isoformat())
        return got if got is not None else day_cells(recent.get(X.isoformat()) or {}, X, cost, unk, kf(X), today,
                                                     kqf(X))
    sums = {}                                           # the buttons' sums: a day, a whole month, or the running sum
    for pid in ("today", "yday"):                       # of the days back from yesterday
        c, u = day(pr[pid][0])
        sums[pid] = (c, list(u))
    for pid in ("tm", "lm"):                            # a whole calendar month (the current one: to today) = its
        sums[pid] = (mcells.get(_mon(pr[pid][0])) or {}, None)          # month's cells (a hot month: built above)
    run_c, run_u, marks = {}, unit0(0), {(today - pr[k][0]).days: k for k in ("7", "30", "60", "90")}
    for i in range(1, max(marks) + 1):
        c, u = day(today - timedelta(days=i))
        cells_add(run_c, c)
        run_u = unit_add(run_u, u)
        if i in marks:
            sums[marks[i]] = (cells_round({k: list(v) for k, v in run_c.items()}), list(run_u))
    out_p, used = {}, set()
    for pid, (a, b) in pr.items():
        if pid == "all":
            cells, u = allc, unit0(0)
            for m in months:
                u = unit_add(u, new_months[m]["u"])
        else:
            cells, u = sums[pid]
            if u is None:                               # (tm / lm: the units of their days)
                u, X = unit0(0), max(a, first)
                while X <= b:
                    u = unit_add(u, day(X)[1])
                    X += timedelta(days=1)
        mr = ROW_MIN.get(pid, MIN_ROW)
        (rows, rest, t), lists = plists(cells, ccs, mr, MAX_ROWS, MAX_ROWS_CC)
        by = {}
        for cc in ccs:
            r2, rs2, t2 = lists[cc]
            by[cc] = {"rows": r2, "rest": rs2, "tot": t2}
            used.update(x[0] for x in r2)
        used.update(x[0] for x in rows)
        out_p[pid] = {"rows": rows, "rest": rest, "tot": t, "by": by, "from": max(a, first).isoformat(),
                      "to": b.isoformat(), "u": unit_out(u)}
    V = _verdicts(W, lambda c: True, curve)
    Vc = {cc: {md: v for md, v in vs.items() if md in used} for cc, vs in verdicts_cc(W, ccs, curve).items()}
    names = view.get("names") or {}
    every = {md for md, _ in allc}
    bf = (view.get("bf") or {}) if isinstance(view.get("bf"), dict) else {}
    hist = {"on": bool(bf) and not ((bf.get("A") or {}).get("done") and (bf.get("B") or {}).get("done")),
            "at": bf.get("at"), "stale": gd.bf_stalled(bf)}
    body_ = {"v": DV_V, "key": key, "F": view["F"], "today": today.isoformat(), "first": first.isoformat(),
             "win": {str(a): [w[0].isoformat(), w[1].isoformat()] for a, w in win.items()},
             "wdays": {str(a): len(W[a][1]) for a in gd.AGES}, "cov": cov, "cov_ok": COV_OK, "judge": JUDGE,
             "periods": [[k, lab] for k, lab in STD], "P": out_p,
             "V": {md: v for md, v in V.items() if md in used}, "Vc": Vc,
             "vcount": {k: sum(1 for v in V.values() if v[0] == k) for k in ("Loss", "Slow", "Profit", "No ads",
                                                                         "Too little data")},
             "cc": [[cc, int(round(by_cc[cc]))] for cc in ccs],
             "names": {md: names[md] for md in sorted(every) if md in names},
             "curve": {k: _r(v) for k, v in (curve or {}).items()},
             "months": [[m, new_months[m]["u"], new_months[m].get("sm"), new_months[m].get("sd")]
                        + ([1] if new_months[m].get("gap") else []) for m in months],
             "rmin": MIN_ROW, "rcap": [MAX_ROWS, MAX_ROWS_CC], "U": list(U), "hist": hist,
             "hot": hot0.isoformat()}
    raw = _dumps(body_)
    nm = dv_name(key, "dv")
    sha, z = put_file(_os.path.join(out_dir, nm), raw)      # (TooBigError: the caller keeps the last stub)
    kb += z
    files.append(nm)
    # the cache (private): written after every site file it points at
    tz_ = Dict()
    agg2 = {"v": AGG_V, "code": CODE_V, "first": first.isoformat(), "months": new_months,
            "tot": {"of": of, "c": tz_.enc(tot)}}
    agg2["tot"].update(md=tz_.md, cc=tz_.cc)
    try:
        put_file(agg_path(data_dir, skey), _dumps(agg2), max_gz=10 ** 12)
    except Exception as e_:                             # (costs the next build time only: its months are built again)
        print("devices cache skipped: %s" % type(e_).__name__, file=_sys.stderr)
    info["rows"] = info.get("rows", 0) + len(out_p["all"]["rows"])
    info["months"] = info.get("months", 0) + len(months)
    info["kb"] = info.get("kb", 0) + kb // 1024
    info["changed"] = info.get("changed", 0) + len(changed)
    return ({"v": DV_V, "file": nm, "sha": sha, "vcount": body_["vcount"], "today": today.isoformat(),
             "first": first.isoformat()}, files)
