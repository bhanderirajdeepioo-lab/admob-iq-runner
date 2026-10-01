"""Synthetic data for the "💸 Install value" tab — the engine tests, the build tests and the frontend fixture.

    python -m tests.value_synth          # rewrites tests/fixtures/value_sample.json (the real build code's output)

Everything here is made up: no real app, country mix, money or id. A made-up app is a closed-form model:
  * installs per day `new` (a weekday wave + deterministic noise), split over countries by fixed shares;
  * returners at age L ≥ 1: new × r1 × m_c × L^−0.45 (m_c: the country's retention multiplier), all at age 0;
  * ad revenue per active user per day: arpu_c (USD), half of it on the install day itself;
  * GA4 reads every activity day D in [from, to] once (the fetch's fold): Q-B → x[X] (all countries, lags ≤ 427),
    Q-C → c[week][slot] (lags ≤ 90) with the unassigned `gap` on lossy days, Q-T → days[D].rev (all ages);
  * AdMob all-source revenue = k × the GA4 day total (k per scenario), Google Ads spend = cpi × installs in INR at a
    dated USD/INR rate (weekdays only: weekends take the previous business day).

make_app(**kw) → {"store", "ida", "rev", "spend", "fx", "S"}: the engine's inputs for one app (cached; deep-copied).
"""

import bisect
import copy
import functools
import gzip
import json
import math
import os
import random
import sys
import zlib
from datetime import date, datetime, timedelta, timezone

END = date(2026, 9, 19)                 # the store's window_end (the build's settled GA4 day)
LATE = 3                                # ida["to"] = END − 3 (the install-day fetch reads a day once it is final)
ULAGS = (0, 1, 3, 7, 14, 30, 45, 60, 90, 120, 180, 270, 365)
RBANDS = ((0, 0), (1, 1), (2, 3), (4, 7), (8, 14), (15, 30), (31, 60), (61, 90), (91, 180), (181, 365))
CLAGS = (1, 3, 7, 14, 30, 60, 90)
QB_WIN = 427
R1 = 0.35
CTY = {"IN": (0.30, 0.90, 0.004), "US": (0.18, 1.20, 0.030), "BR": (0.14, 1.00, 0.008),
       "NG": (0.12, 0.80, 0.003), "ID": (0.10, 0.95, 0.005), "DE": (0.06, 1.15, 0.022),
       "--": (0.02, 1.00, 0.005), "ZZ": (0.08, 1.00, 0.006)}      # share, retention ×, USD per active user per day
FX0 = 0.0120                            # USD per INR at the start (drifts down slowly: dated rates matter)


def _band(L):
    for b, (lo, hi) in enumerate(RBANDS):
        if lo <= L <= hi:
            return b
    return None


def _mon(d):
    return d - timedelta(days=d.weekday())


def iso(d):
    return d.isoformat()


def fx_rate(d, hs):
    return FX0 * (1 - 0.00004 * (d - hs).days)


@functools.lru_cache(maxsize=32)
def _make(weeks=60, end=END, base=2000, seed=1, spend=True, cpi=0.06, cpi_jump=None, k=1.0, k_from=None, k_after=None,
          smp=False, gap_days=(), gap_loss=0.05, drop=None, filling=None, cty_days=400, old_usd=40.0, iap=0.0,
          q_days=(), ads_share=0.87, spend_stop=None, countries=None, start=None, noise=0.04, ga4_drop=None, cnoise=0.0,
          cty_share=None, organic=None, versions=None, vsplit=True, ver_drop=None, long_drop=None):
    """ga4_drop = (day, f): GA4's ad revenue × f from that activity day (a Firebase link / consent / SDK change), AdMob —
    the truth — unchanged. cnoise: each country's install-day revenue × a lognormal with sd cnoise/√installs (a null of
    identical countries). cty_share = (cc, day, ×): that country's install share × from that install day (a campaign).
    organic = (from, to, ×): installs × on those days, Google Ads spend and its installs unchanged.
    C / D (VALUE_CD; none of these given: the output is exactly as before):
      versions = ((version, first day, ramp days[, last day]), …) → store["vuse"] (every day's new users split by the
        version they got: the newest version from its first day takes a share rising over `ramp` days (0: at once),
        the version before it the rest; a `last day` hands the day after back to the version before it — a hotfix
        pulled, or an A → B → A) plus a 1% "(not set)" slot, and store["flags"]["impact"]["vuse_split"] = vsplit
        (False: every user in the returning slots, as GA4 answers without newVsReturning);
      ver_drop = (version, ×): returners at ages 1–29 of the install days that version is dominant on × (D1 and D7
        of that version's new users, never its installs or earnings);
      long_drop = (first month (a date), months, ×): install days in those calendar months — returners at ages ≥ 45
        and revenue at ages ≥ 31 × (the long-term tail only)."""
    cty = dict(countries) if countries else dict(CTY)
    S = end - timedelta(days=LATE)
    hs = start or (end - timedelta(days=weeks * 7 - 1))
    frm = hs if filling is None else S - timedelta(days=filling - 1)
    cfrom = max(frm, S - timedelta(days=cty_days))
    names = [c for c in sorted(cty, key=lambda c: (-cty[c][0], c)) if c not in ("--", "ZZ")]
    cset = names + ["--", "ZZ"]
    slot = {c: str(i) for i, c in enumerate(cset)}
    gap_days = {d if isinstance(d, date) else date.fromisoformat(d) for d in gap_days}
    q_days = {d if isinstance(d, date) else date.fromisoformat(d) for d in q_days}
    ndays = (end - hs).days + 1
    drops = () if not drop else ((drop,) if isinstance(drop[0], str) else tuple(drop))
    new, A, B, n_c, a_c, b_c, ad, paid_n = {}, {}, {}, {}, {}, {}, {}, {}
    g4 = {}
    for i in range(ndays):                                              # each activity day's ad earnings wobble
        D = hs + timedelta(days=i)
        ad[D] = math.exp(random.Random(seed * 7919 + D.toordinal()).gauss(0, noise)) if noise else 1.0
        g4[D] = ga4_drop[1] if ga4_drop and D >= ga4_drop[0] else 1.0     # the GA4 side only
    for i in range(ndays):
        X = hs + timedelta(days=i)
        rnd = random.Random(seed * 1000003 + X.toordinal())             # keyed by date: any `end` agrees
        n = int(round(base * (1 + 0.08 * math.sin(2 * math.pi * X.weekday() / 7)) * math.exp(rnd.gauss(0, 0.03))))
        paid_n[X] = n
        if organic and organic[0] <= X <= organic[1]:
            n = int(round(n * organic[2]))
        new[X] = n
        n_c[X], a_c[X], b_c[X] = {}, {}, {}
        jump = bool(cty_share) and X >= cty_share[1]
        if jump:
            shs = {c: v[0] * (cty_share[2] if c == cty_share[0] else 1.0) for c, v in cty.items()}
            tot_sh = sum(shs.values())
        for c, (sh, m, arpu) in cty.items():
            if jump:
                sh = shs[c] / tot_sh
            mm = m
            for dc, dday, dfac in drops:
                if dc in (c, "*") and X >= dday:
                    mm = m * dfac
            n_c[X][c] = n * sh
            a_c[X][c] = n * sh * mm
            b_c[X][c] = n * sh * mm * arpu
        A[X] = sum(a_c[X].values())
        B[X] = sum(b_c[X].values())

    def ret(L):
        return R1 * L ** -0.45

    cn = {}

    def rev_c(X, c, L):                                     # USD
        f = ad.get(X + timedelta(days=L), 1.0) * g4.get(X + timedelta(days=L), 1.0)
        if cnoise:
            k = (c, X)
            if k not in cn:
                sd = cnoise / math.sqrt(max(n_c[X][c], 1.0))
                # keyed by a STABLE hash (zlib.crc32): Python's hash() of a str is salted per process (PYTHONHASHSEED),
                # so the same seed drew other noise on every run and the null-countries test was flaky
                key = zlib.crc32(("%s|%s|%d" % (seed, c, X.toordinal())).encode("utf-8"))
                cn[k] = math.exp(random.Random(key).gauss(-sd * sd / 2, sd))
            f *= cn[k]
        if L == 0:
            return n_c[X][c] * cty[c][2] * 0.5 * f
        return ret(L) * b_c[X][c] * f

    def users_c(X, c, L):
        return n_c[X][c] if L == 0 else ret(L) * a_c[X][c]
    vshare = _vshares(versions, hs, end) if versions else None
    vdrop = {}
    if ver_drop:
        for X, sh in (vshare or {}).items():
            if max(sh, key=lambda v: (sh[v], v)) == ver_drop[0] and max(sh.values()) * 0.99 >= 0.8:
                vdrop[X] = ver_drop[1]
    ldrop = set()
    if long_drop:
        m0 = long_drop[0].year * 12 + long_drop[0].month - 1
        ldrop = set(range(m0, m0 + long_drop[1]))

    def lmul(X, L, what):
        if ldrop and X.year * 12 + X.month - 1 in ldrop and ((what == "u" and L >= 45) or (what == "r" and L >= 31)):
            return long_drop[2]
        return 1.0
    x, cw, days = {}, {}, {}
    qb_rev = {}
    for i in range(ndays):
        X = hs + timedelta(days=i)
        if X > S:
            break
        e = {"n": 0, "u": [0] * 13, "r": [0] * 10, "p": [0] * 10}
        for L in range(0, min(QB_WIN, (S - X).days) + 1):
            D = X + timedelta(days=L)
            if D < frm:
                continue
            micros = {c: int(round(rev_c(X, c, L) * 1e6)) for c in cty}
            tot = sum(micros.values())
            qb_rev[D] = qb_rev.get(D, 0) + tot
            if L == 0:
                e["n"] += new[X]
            if L in ULAGS:
                um = (vdrop.get(X, 1.0) if 1 <= L < 30 else 1.0) * (lmul(X, L, "u") if ldrop else 1.0)
                e["u"][ULAGS.index(L)] += int(round(sum(users_c(X, c, L) for c in cty) * um))
            b = _band(L)
            if b is not None:
                e["r"][b] += int(round(tot * lmul(X, L, "r"))) if ldrop else tot
                if iap:
                    e["p"][b] += int(round(tot * iap))
            if L <= 90 and D >= cfrom:
                W = iso(_mon(X))
                wk = cw.setdefault(W, {})
                lossy = D in gap_days
                cb = _band(L)
                for c in cty:
                    s = slot[c]
                    cell = wk.setdefault(s, {"n": 0, "u": [0] * 7, "r": [0] * 8})
                    f = (1 - gap_loss) if lossy else 1.0
                    rv = int(round(micros[c] * f))
                    cell["r"][cb] += rv
                    if L in CLAGS:
                        cell["u"][CLAGS.index(L)] += int(round(users_c(X, c, L) * f))
                    if L == 0:
                        cell["n"] += int(round(n_c[X][c] * f))
                    if lossy:
                        g = wk.setdefault("gap", {"n": 0, "r": [0] * 8})
                        g["r"][cb] += micros[c] - rv
                        if L == 0:
                            g["n"] += int(round(n_c[X][c])) - int(round(n_c[X][c] * f))
        if any(e["u"]) or e["n"] or any(e["r"]):
            if not iap:
                e.pop("p")
            x[iso(X)] = e
    # day totals (Q-T): every install age, plus users installed before the history (old_usd a day)
    for i in range((S - frm).days + 1):
        D = frm + timedelta(days=i)
        old = old_usd
        for j in range(max(0, (D - hs).days - QB_WIN)):
            X = hs + timedelta(days=j)
            old += ret((D - X).days) * B[X] * ad.get(D, 1.0) * g4.get(D, 1.0)
        rev4 = qb_rev.get(D, 0)
        cst = "none" if D < cfrom else ("gap" if D in gap_days else ("smp" if smp else "ok"))
        days[iso(D)] = {"st": "q" if D in q_days else "ok", "tries": 0, "at": "2026-01-01T00:00:00Z",
                        "a4": 0, "n": new.get(D, 0), "rev4": rev4, "ncov": 1.0, "cov": 1.0, "win": QB_WIN,
                        "oth": False, "loss": False, "smp": False, "thr": False, "rows": 0, "tok": 1,
                        "a": 0, "nn": new.get(D, 0), "rev": rev4 + int(round(old * 1e6)),
                        "tot": rev4 + int(round(old * 1e6)), "rb_old": int(round(old * 1e6)),
                        "ab": [0] * 6, "rb": [0] * 6, "cst": cst, "ctries": 0, "crows": 0, "ctok": 1,
                        "closs": D in gap_days, "coth": False, "csmp": smp and D >= cfrom,
                        "smp_frac": 0.1 if smp and D >= cfrom else None, "tie_rev": 1.0, "tie_new": 1.0, "chk": None}
    ida = {"v": 1, "src": ["p1", "s1"], "tz": "UTC", "cur": "USD", "from": iso(frm), "to": iso(S),
           "cfrom": iso(cfrom), "edge": None, "done": filling is None,
           "flags": {"no_total": False, "iap": bool(iap), "smp": bool(smp), "qb_win": False},
           "cset": cset, "cset_since": {}, "days": days, "x": x, "c": cw}
    # AdMob all-source revenue on the same (UTC) days: k × the GA4 day total; the network report ~90% of it
    all_days, net = {}, {}
    for i in range((end - hs).days + 1):
        D = hs + timedelta(days=i)
        g = days.get(iso(D), {}).get("rev")
        if g is None:
            continue
        kk = k_after if (k_from and k_after is not None and D >= k_from) else k
        m = int(round(g / g4.get(D, 1.0) * kk))                       # AdMob: the truth, whatever GA4 shows
        all_days[iso(D)] = [m, int(m / 2000)]
        net[iso(D)] = [int(m * 0.9), int(m / 2200)]
    rev = {"tz": "UTC", "currency": "USD", "till": iso(end), "days": net, "all_days": all_days}
    sp = None
    if spend:
        daily, inst = {}, {}
        for i in range(ndays):
            d = hs + timedelta(days=i)
            if spend_stop and d >= spend_stop:
                continue
            c = cpi
            if cpi_jump and d >= cpi_jump[0] and (len(cpi_jump) < 3 or d < cpi_jump[2]):
                c = cpi * cpi_jump[1]
            usd = c * paid_n[d]
            daily[iso(d)] = int(round(usd / fx_rate(d, hs) * 1e6))
            inst[iso(d)] = round(paid_n[d] * ads_share, 1)
        sp = {"ccy": "INR", "daily": daily, "installs": inst, "first": iso(hs), "till": iso(end)}
    series = {iso(hs + timedelta(days=i)): round(fx_rate(hs + timedelta(days=i), hs), 7)
              for i in range(ndays) if (hs + timedelta(days=i)).weekday() < 5}
    fx = {"mode": "dated", "series": series, "now": round(fx_rate(end, hs), 7)}
    store = {"v": 3, "app_id": "ca-app-pub-0000000000000000~0000000009", "package": "com.synthetic.value",
             "property_id": "p1", "stream_id": "s1", "time_zone": "UTC", "history_start": iso(hs),
             "window_end": iso(end), "fetched_at": "2026-09-21T01:00:00Z",
             "daily": {iso(d): {"new": n, "a1": n * 5, "a28": n * 20, "un": 0, "un_ev": 0, "upd": 0}
                       for d, n in new.items()}}
    if versions:
        store["vuse"] = _vuse(vshare, new, vsplit)
        store["flags"] = {"impact": {"vuse_split": bool(vsplit)}}
    return {"store": store, "ida": ida, "rev": rev, "spend": sp, "fx": fx, "S": S, "hs": hs, "new": new}


def _vshares(versions, hs, end):
    """{day: {version: share of the day's new users}} for versions ((version, first, ramp[, last]), …): the first
    version holds every day before the next one; a version from its first day takes min(1, (day − first + 1) / ramp)
    of the new users from the version before it (all at once with ramp 0; a tuple of shares: those on its first days,
    then all) — until its `last` day, if any."""
    vs = sorted((tuple(v) for v in versions), key=lambda v: v[1])
    out = {}
    d = hs
    while d <= end:
        live = [v for v in vs if v[1] <= d and (len(v) < 4 or v[3] is None or d <= v[3])]
        if not live:
            out[d] = {vs[0][0]: 1.0}
        elif len(live) == 1:
            out[d] = {live[-1][0]: 1.0}
        else:
            cur, prev = live[-1], live[-2]
            i = (d - cur[1]).days
            if isinstance(cur[2], tuple):                   # explicit daily shares, then all of it
                s = cur[2][i] if i < len(cur[2]) else 1.0
            else:
                s = 1.0 if cur[2] <= 0 else min(1.0, (i + 1) / cur[2])
            out[d] = {cur[0]: s} if s >= 1 else {cur[0]: s, prev[0]: 1 - s}
        d += timedelta(days=1)
    return out


def _vuse(vshare, new, split):
    """store["vuse"] {day: {version: [aN, sN, tN, aR, sR, tR]}}: new users by the day's shares (+ 1% "_x"), and
    returning users 4× as many; unsplit (GA4 without newVsReturning): everything in the returning slots."""
    out = {}
    for d, sh in sorted(vshare.items()):
        n = new.get(d, 0)
        day = {}
        for v, s in sorted(sh.items()):
            a = int(round(n * 0.99 * s))
            r = int(round(n * 4 * s))
            day[v] = [a, 2 * a, 60 * a, r, 2 * r, 90 * r] if split else [0, 0, 0, a + r, 2 * (a + r), 90 * (a + r)]
        x = int(round(n * 0.01))
        day["_x"] = [x, x, 30 * x, 0, 0, 0] if split else [0, 0, 0, x, x, 30 * x]
        out[iso(d)] = day
    return out


def make_app(**kw):
    """One made-up app's engine inputs (a fresh deep copy — tests may change it)."""
    for k in ("gap_days", "q_days"):
        if k in kw:
            kw[k] = tuple(sorted(kw[k]))
    for k in ("ga4_drop", "cty_share", "organic", "ver_drop", "long_drop"):
        if kw.get(k) is not None:
            kw[k] = tuple(kw[k])
    if kw.get("versions") is not None:
        kw["versions"] = tuple(tuple(tuple(x) if isinstance(x, list) else x for x in v) for v in kw["versions"])
    if isinstance(kw.get("countries"), dict):
        kw["countries"] = tuple(sorted(kw["countries"].items()))
    return copy.deepcopy(_make(**kw))


def iday_dir(data_dir):
    return os.path.join(data_dir, "ga4_uninstall", "iday")


def write_iday(data_dir, app_id, ida):
    """The fetch's files for one app, written by the fetch's OWN writer (gu.save_iday: data/ga4_uninstall/iday/<key>.json.gz
    + the frozen .old.json.gz part, whole months) — so the build reads exactly the layout production writes."""
    from admob_iq.fetch import ga4_uninstall as gu
    gu.save_iday(data_dir, app_id, ida)


def spend_cache(apps):
    """roas_spend_cache.json (v2, raw INR micros keyed by Play package) for [(package, spend)]."""
    daily, inst, conv = {}, {}, {}
    for pkg, sp in apps:
        if sp:
            daily[pkg] = dict(sp["daily"])
            inst[pkg] = dict(sp["installs"])
            conv[pkg] = {d: 0.0 for d in sp["installs"]}
    return {"v": 2, "currency_src": "INR", "daily": daily, "installs": inst, "convval": conv, "convval_day1": {},
            "campaigns": {}, "fx": {"USD": 1.0, "INR": FX0}, "note": None}


def _fx_at(series, d):
    """The dated USD rate the engine reads for day d (a weekend / holiday: the business day before)."""
    keys = sorted(series)
    i = bisect.bisect_right(keys, iso(d)) - 1
    return series[keys[max(i, 0)]]


def geo_envelope(m, cov=1.0, noads=(), xx=0.0, mult=None, small=None, till=None, dl=0.87, dl_null=(), days=120):
    """A GADS_GEO week envelope (value_build._app_geo's engine input, SPEC_CD_GEO §G.8) for make_app output m: every
    Monday of [Monday(S − days), Monday(S)]; a week's covered cost (cov × its Google Ads spend in USD) is shared over
    the countries by their installs × mult[cc] (default 1) — so with no mult every country's cost per install is the
    same — minus the `xx` share, which goes to "XX" (Google Ads could not place it in a country).
      cov: one coverage for every week, or {Monday iso: cov}; noads: countries with no Google Ads cost; small: {cc:
      installs-equivalent weight} for countries the app has no row for; till: the cache's last day (a week past it is
      not whole); dl: Google Ads downloads per install; dl_null: countries whose downloads are unknown; xx: one
      unmapped share for every week, or {Monday iso: share}. Each country carries its cost in the billed currency too
      ([usd, dl, billed], as value_build writes it)."""
    S, hs, sp, ida = m["S"], m["hs"], m["spend"], m["ida"]
    till = till or S
    series = m["fx"]["series"]
    cset = ida["cset"]
    W, last = _mon(S - timedelta(days=days)), _mon(S)
    weeks = {}
    while W <= last:
        ds = [W + timedelta(days=i) for i in range(7)]
        src = sum(((sp or {}).get("daily") or {}).get(iso(d), 0) for d in ds)
        usd = sum(((sp or {}).get("daily") or {}).get(iso(d), 0) / 1e6 * _fx_at(series, d) for d in ds)
        cells = ida["c"].get(iso(W)) or {}
        n_c = {cset[int(k)]: v["n"] for k, v in cells.items() if k != "gap"}
        wts = {cc: n * (mult or {}).get(cc, 1.0) for cc, n in n_c.items()
               if cc not in noads and cc not in ("--", "ZZ") and n > 0}
        wts.update(small or {})
        cv = cov.get(iso(W), 1.0) if isinstance(cov, dict) else cov
        xw = xx.get(iso(W), 0.0) if isinstance(xx, dict) else xx
        total = cv * usd
        tw = sum(wts.values())
        rate = (usd / src * 1e6) if src else _fx_at(series, W)
        by = {}
        for cc, w in sorted(wts.items()):
            c = total * (1 - xw) * w / tw
            by[cc] = [c, None if cc in dl_null else round(dl * n_c.get(cc, w), 2), c / rate]
        if xw and total:
            by["XX"] = [total * xw, 0.0, total * xw / rate]
        weeks[iso(W)] = {"whole": W >= hs and W + timedelta(days=6) <= till,
                         "cov": (cv if src > 0 else (1.0 if not total else None)), "spend": usd, "geo": total,
                         "rate": rate, "dl_ok": not dl_null, "by": by}
        W += timedelta(days=7)
    return {"v": 2, "ccy": "INR", "first": iso(hs), "till": iso(till), "weeks": weeks}


# ── the frontend fixture: 3 made-up apps through the REAL build code ──────────────────────────────

FIX_START = {"spend": END - timedelta(days=60 * 7 - 1), "organic": END - timedelta(days=40 * 7 - 1),
             "young": END - timedelta(days=10 * 7 - 1)}
DROP_DAY = date(2026, 8, 31)            # installs from here: Nigeria's users come back less (D1 26% → 16%)
CPI_DAY = date(2026, 8, 24)             # Google Ads cost per install ×1.6 from here
FIX_APPS = (
    # app id, name, package, scenario
    ("ca-app-pub-5555555555555555~101", "Demo Spend App", "com.demo.value.spend",
     dict(start=FIX_START["spend"], seed=11, drop=("NG", DROP_DAY, 0.6), cpi_jump=(CPI_DAY, 1.6), gap_days=tuple(
         END - timedelta(days=LATE + 200 + i) for i in range(7)))),
    ("ca-app-pub-5555555555555555~102", "Demo Organic App", "com.demo.value.organic",
     dict(start=FIX_START["organic"], seed=12, spend=False, smp=True, base=900,
          gap_days=tuple(END - timedelta(days=LATE + 3 + i) for i in range(12)))),
    ("ca-app-pub-5555555555555555~103", "Demo Young App", "com.demo.value.young",
     dict(start=FIX_START["young"], seed=13, filling=30, base=600)),
)
# C / D (VALUE_CD): each app's versions — only seed_build(cd=True) (the committed fixture) puts them in the stores.
# Made-up version strings (never the release synth's). (a) 2.0 → 2.1 → a one-day hotfix 2.1.1 (pulled) → 2.2 after 3
# rollout days at 40 / 60 (left out) → 2.3, 5 days old (its week not in yet); every version's users behave alike (no
# ver_ret). (b) GA4 does not split its new users by version (nosplit). (c) one version (single).
FIX_VERSIONS = {
    "ca-app-pub-5555555555555555~101": dict(versions=(("2.0", FIX_START["spend"], 0), ("2.1", date(2026, 4, 6), 0),
                                                      ("2.1.1", date(2026, 6, 28), 0, date(2026, 6, 28)),
                                                      ("2.2", date(2026, 6, 29), (0.4, 0.4, 0.4)),
                                                      ("2.3", date(2026, 9, 12), 0))),
    "ca-app-pub-5555555555555555~102": dict(versions=(("5.0", FIX_START["organic"], 0),), vsplit=False),
    "ca-app-pub-5555555555555555~103": dict(versions=(("3.0", FIX_START["young"], 0),)),
}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "value_sample.json")
RUNS = tuple(datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc) - timedelta(days=7 * k) for k in range(5, -1, -1))


def _kw(kw, end):
    kw = dict(kw)
    if kw.get("filling"):                               # the young app's backfill: 30 days at the last run
        kw["filling"] = max(8, kw["filling"] - (END - end).days)
    return kw


def seed_build(data_dir, apps=FIX_APPS, end=END, write=True, cd=False):
    """Stores (tests.uninstall_synth.make_store) + install-day files + the spend cache + FX series for `apps` →
    (revenue for run_uninstall, {app id: make_app output}). write False: the revenue only (nothing on disk changes).
    cd True: each app's FIX_VERSIONS go into its install-day model and its store gets their `vuse` / vuse_split (the
    stores and files are otherwise the same)."""
    from admob_iq.fetch import ga4_uninstall as gu
    from tests.uninstall_synth import make_store

    def _kw_cd(aid, kw):
        return dict(kw, **FIX_VERSIONS.get(aid, {})) if cd else kw
    if not write:
        made = {aid: make_app(end=end, **_kw_cd(aid, _kw(kw, end))) for aid, _, _, kw in apps}
        return ({"tz": "UTC", "currency": "USD", "till": iso(end),
                 "apps": {aid: m["rev"]["days"] for aid, m in made.items()},
                 "all_apps": {aid: m["rev"]["all_days"] for aid, m in made.items()}}, made)
    os.makedirs(os.path.join(data_dir, "ga4_uninstall"), exist_ok=True)
    with open(os.path.join(data_dir, "app_store_ids.json"), "w", encoding="utf-8") as f:
        json.dump({"by_id": {aid: pkg for aid, _, pkg, _ in apps}}, f)
    made, sp = {}, []
    rev = {"tz": "UTC", "currency": "USD", "till": iso(end), "apps": {}, "all_apps": {}}
    for aid, name, pkg, kw in apps:
        kw = _kw_cd(aid, _kw(kw, end))
        m = make_app(end=end, **kw)
        made[aid] = m
        news = m["new"]
        st = make_store((end - m["hs"]).days + 1, new_per_day=lambda d, news=news: news.get(d, 0), end=end,
                        app_id=aid, package=pkg)
        st.update(property_id="p-" + pkg.rsplit(".", 1)[-1], stream_id="s-" + pkg.rsplit(".", 1)[-1],
                  time_zone="UTC")
        if cd and "vuse" in m["store"]:
            st["vuse"] = m["store"]["vuse"]
            st.setdefault("flags", {})["impact"] = dict(m["store"]["flags"]["impact"])
        gu.save_store(gu.store_path(data_dir, aid), st)
        ida = dict(m["ida"], src=[st["property_id"], st["stream_id"]])
        write_iday(data_dir, aid, ida)
        rev["apps"][aid] = m["rev"]["days"]
        rev["all_apps"][aid] = m["rev"]["all_days"]
        sp.append((pkg, m["spend"]))
    with open(os.path.join(data_dir, "roas_spend_cache.json"), "w", encoding="utf-8") as f:
        json.dump(spend_cache(sp), f)
    series = next(iter(made.values()))["fx"]["series"]
    with open(os.path.join(data_dir, "fx_series.json"), "w", encoding="utf-8") as f:
        json.dump({"INR": series, "_ts": 0}, f)
    state = gu._state_default()
    state["routes"].update(fetched_at="2026-09-19T01:00:00Z", by_package={
        pkg: {"property_id": "p", "stream_id": "s", "owner": "owner@example.test"} for _, _, pkg, _ in apps})
    gu.save_state(data_dir, state)
    return rev, made


def build_fixture(tmp):
    import contextlib
    import io
    from unittest import mock
    from admob_iq import build_static
    from admob_iq.config import settings
    from admob_iq.fetch import ga4_uninstall as gu
    data_dir, out_dir = os.path.join(tmp, "data"), os.path.join(tmp, "site")
    s = dict(settings(), ga4_enabled=True, ga4_client_id="demo-cid", ga4_client_secret="demo-sec",
             ga4_refresh_tokens=json.dumps({"owner@example.test": "rt-demo"}), ga4_refresh_token="",
             notify_dry_run=True, ga4_active=True, ga4_value=True, value_cd=True, gads_geo=False)
    catalog = [{"app_id": aid, "app_name": name, "account_id": "pub-demo", "selected": True}
               for aid, name, _, _ in FIX_APPS]
    status = {"counts": {"selected": len(catalog), "with_ga4": len(catalog), "fetched": 0, "full": 0,
                         "fresh": len(catalog), "failed": 0, "deferred": 0, "no_ga4": 0}, "apps": {}, "no_ga4": {},
              "discovery": None}
    sent = []
    with contextlib.ExitStack() as st_:
        st_.enter_context(mock.patch.object(gu, "refresh_all", lambda *a, **k: json.loads(json.dumps(status))))
        log = st_.enter_context(contextlib.redirect_stderr(io.StringIO()))
        for i, now in enumerate(RUNS):
            rev, _ = seed_build(data_dir, end=now.date() - timedelta(days=2), cd=True)   # GA4 till now − 2
            dashboard = {"apps_catalog": catalog, "kpis": {"revenue": 1.0}, "alerts": {"items": []}, "usd_inr": 83.3}
            build_static._uninstall_step(dashboard, data_dir, out_dir, s, revenue=rev, now=now)
            res = build_static.send_alerts(dashboard, s)
            sent.append({"run": now.strftime("%Y-%m-%dT%H:%MZ"),
                         "telegram": next((r["text"] for r in res if r["channel"] == "telegram"), None),
                         "email": next((r["body"] for r in res if r["channel"] == "email"), None)})
            if i < len(RUNS) - 1:
                build_static._uninstall_mark_sent(dashboard, data_dir, s, res)
        lines = [l for l in log.getvalue().splitlines() if l.startswith("ga4 value")]
    files = {}
    for r in dashboard["value"]["apps"]:
        if r.get("file"):
            with gzip.open(os.path.join(out_dir, r["file"]), "rt", encoding="utf-8") as f:
                files[r["key"]] = json.load(f)
    return {"dashboard_value": dashboard["value"], "app_files": files, "sent": sent, "public_log": lines}


def fixture_json(fx):
    body = {"_about": "Synthetic Install-value-tab data written by the real build code (python -m tests.value_synth). "
                      "dashboard_value = dashboard.json's \"value\" key; app_files = site/value_<key>.json.gz by key; "
                      "sent = what each daily run would notify (dry run); public_log = the tab's build-log lines. "
                      "Made-up apps, countries and money only.",
            "dashboard_value": fx["dashboard_value"], "app_files": fx["app_files"], "sent": fx["sent"],
            "public_log": fx["public_log"]}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        text = fixture_json(build_fixture(tmp))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s (%d KB)" % (os.path.relpath(OUT), len(text.encode("utf-8")) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
