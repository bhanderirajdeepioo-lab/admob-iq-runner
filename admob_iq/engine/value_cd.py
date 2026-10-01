"""GA4 "💸 Install value" tab — C (new users by the app version of their install day) and D (long-term by install
month). Pure: no I/O, no prints, no clock of its own. SPEC_CD_GEO Parts C and D; read only by value.evaluate_app, and
only while VALUE_CD is on (cfg["cd"]) — with it off nothing here runs and every output is as before.

Both read what the value engine already built (no new GA4 call): the install-day grain x (Q-B: installs n, users at
the ULAGS ages, AdMob-scaled revenue per install to every T age — P["xs"]) and the activity-day ledger (P["pre"]: a
day complete / ≈). C adds the store's `vuse` (new users per app version per day) only to SPLIT install days by the
version they got: installs and returners always come from x, the same base as A, B and Active.

  C. versions(): install days grouped by their dominant version (≥ VER_DOM of the day's new users; rollout days left
     out and counted) → D1 / D7 / D30 and earning per install at 1 / 7 / 30 days per version, and each version vs the
     one before it at the same age (its first VER_WIN_DAYS complete days vs the previous one's last ones) → `ver_ret`.
  D. long_term(): install months (quarters for small apps) → the share still opening the app on day 30 / 60 / 90 /
     180 / 365 and earning per install at 30 / 90 / 180 / 365 days (≈ projected with the app's own curve when not old
     enough), ₹ back per ₹100 of ads in a year → `long_ret` (watch only).

A cell is either complete (every install day of it old enough, every activity day it needs in the ledger) or it is
"in N days" / "No data" — never a small number from part of its days. Every rate is a ratio of sums; unknown = None.
Dates in texts come from uninstall.fmt_day / fmt_month here (no date literal lives in this file).
"""

import math
from datetime import date, timedelta

from . import uninstall as U
from . import value as V

# ── C: new users by app version (SPEC_CD_GEO §C.5) ─────────────────────────────────────────────────
VER_DOM = 0.80                  # a day's dominant version holds ≥ 80% of its new users (else a rollout day: left out)
VER_SHOW_N = 100                # a version with fewer installs gets no row ("short-lived")
VER_JUDGE_N = 300               # … fewer than this: a row, grey "few installs", no verdict, no comparison
VER_ALERT_N = 1000              # each side of a ver_ret comparison
VER_MIN_DAYS = 3                # complete dominant days on each side
VER_WIN_DAYS = 28               # the new version's first / the previous version's last complete days compared
VER_MIN_RET = 10
VER_ALERT_RET = 30
VER_MINPP = {1: 3, 7: 2, 30: 1.5}
VER_MINREL = 0.10
VER_RPI_REL = 0.25
VER_Z = 3
VER_WARN_Z = 5
VER_ROWS = 8
VER_ALERT_DAYS = 56             # only versions whose first day is this recent can alert
VER_ALERT_TOP = 3               # … and only the newest 3
VER_PHI_DAYS = 180
VER_PHI_DAY_N = 50
VER_PHI_MIN_DAYS = 7
VER_PHI_CAP = 30
VER_DEDUP_DAYS = V.VER_DEDUP_DAYS
VER_MIX_PTS = 10
VER_MIX_INST = 2.0
INPUT_VER_N = 1000
VER_T = (1, 7, 30)

# ── D: long-term by install month (SPEC_CD_GEO §D.3) ───────────────────────────────────────────────
LONG_T = (30, 60, 90, 180, 365)
LONG_RT = (30, 90, 180, 365)
LONG_MIN_N = 1000
LONG_JUDGE_N = 3000
LONG_MIN_RET = 10
LONG_ALERT_RET = 30
LONG_ROWS = 18
LONG_QROWS = 8
LONG_BASE = 6
LONG_BASE_MIN = 4
LONG_MINPP = {60: 1.0, 90: 1.0}
LONG_MINREL = 0.20
LONG_RPI_REL = 0.20
LONG_Z = 3
LONG_PROJ_MIN_T = 30
LONG_DEDUP_DAYS = V.LONG_DEDUP_DAYS
INPUT_LONG_ROWS = 6
LONG_GRAIN_MONTHS = 12          # the grain: the median installs of the last 12 whole months …
LONG_GRAIN_QUARTERS = 4         # … else of the last 4 whole quarters

# merged into dashboard["value"]["consts"] only while VALUE_CD is on (value_build.consts); reopen_seed_days is the
# engine's whole table (geo_cost and long_ret included), which the base consts keep as it was before C / D
CONSTS = {k.lower(): (list(v) if isinstance(v, tuple) else ({str(a): b for a, b in v.items()} if isinstance(v, dict)
                                                             else v)) for k, v in dict(
    VER_DOM=VER_DOM, VER_SHOW_N=VER_SHOW_N, VER_JUDGE_N=VER_JUDGE_N, VER_ALERT_N=VER_ALERT_N, VER_MIN_DAYS=VER_MIN_DAYS,
    VER_WIN_DAYS=VER_WIN_DAYS, VER_MIN_RET=VER_MIN_RET, VER_ALERT_RET=VER_ALERT_RET, VER_MINPP=VER_MINPP,
    VER_MINREL=VER_MINREL, VER_RPI_REL=VER_RPI_REL, VER_Z=VER_Z, VER_WARN_Z=VER_WARN_Z, VER_ROWS=VER_ROWS,
    VER_ALERT_DAYS=VER_ALERT_DAYS, VER_PHI_DAYS=VER_PHI_DAYS, VER_PHI_DAY_N=VER_PHI_DAY_N,
    VER_PHI_MIN_DAYS=VER_PHI_MIN_DAYS, VER_PHI_CAP=VER_PHI_CAP, VER_DEDUP_DAYS=VER_DEDUP_DAYS, VER_MIX_PTS=VER_MIX_PTS,
    VER_MIX_INST=VER_MIX_INST, INPUT_VER_N=INPUT_VER_N, LONG_T=LONG_T, LONG_RT=LONG_RT, LONG_MIN_N=LONG_MIN_N,
    LONG_JUDGE_N=LONG_JUDGE_N, LONG_MIN_RET=LONG_MIN_RET, LONG_ALERT_RET=LONG_ALERT_RET, LONG_ROWS=LONG_ROWS,
    LONG_QROWS=LONG_QROWS, LONG_BASE=LONG_BASE, LONG_BASE_MIN=LONG_BASE_MIN, LONG_MINPP=LONG_MINPP,
    LONG_MINREL=LONG_MINREL, LONG_RPI_REL=LONG_RPI_REL, LONG_Z=LONG_Z, LONG_PROJ_MIN_T=LONG_PROJ_MIN_T,
    LONG_DEDUP_DAYS=LONG_DEDUP_DAYS, INPUT_LONG_ROWS=INPUT_LONG_ROWS, REOPEN_SEED_DAYS=V.REOPEN_SEED_DAYS).items()}

ONE = timedelta(days=1)
NOT_VER = ("_x", "_rest")       # vuse keys that are not a version ("(not set)" / "(other)", and the pooled small ones)
NWORD = {1: "back next day", 7: "back after 7 days", 30: "back after 30 days"}


# ── helpers ─────────────────────────────────────────────────────────────────────────────────────

def _iso(d):
    return d.isoformat() if d else None


def _g4(x):
    return V._g4(x)


def _m6(x):
    return V._m6(x)


def _n(x):
    return "{:,}".format(int(x or 0))


def _i(x):
    return "—" if x is None else str(int(round(x)))


def _ip(x):
    """A 0–100 share as its % text: 34.4 → "34%" ("—" when unknown)."""
    return "—" if x is None else "%d%%" % int(round(x))


def _p1(x):
    """A 0–100 share with one decimal as its % text: 4.25 → "4.3%" ("—" when unknown)."""
    return "—" if x is None else _num1(x) + "%"


def _num1(x):
    return "—" if x is None else ("%.1f" % x).rstrip("0").rstrip(".")


def label(ver):
    """"v2.4.1" — unless the version already starts with v / V."""
    ver = str(ver)
    return ver if ver[:1] in ("v", "V") else "v" + ver


def fmt_month(d):
    """"Sep 2025" — the year is always written."""
    return "%s %d" % (U.MONTHS[d.month - 1], d.year)


def _quarter(d):
    return (d.month - 1) // 3 + 1


def _qlabel(d):
    q = _quarter(d)
    return "Q%d %d (%s–%s)" % (q, d.year, U.MONTHS[3 * q - 3], U.MONTHS[3 * q - 1])


def _span_months(a, b, grain="month"):
    """A span of install months: "Jun–Jul 2026", "Dec 2025–Jan 2026" (quarters: "Q1–Q2 2026")."""
    if grain == "quarter":
        qa, qb = "Q%d" % _quarter(a), "Q%d" % _quarter(b)
        if (a.year, qa) == (b.year, qb):
            return "%s %d" % (qa, a.year)
        return ("%s–%s %d" % (qa, qb, b.year)) if a.year == b.year else ("%s %d–%s %d" % (qa, a.year, qb, b.year))
    if (a.year, a.month) == (b.year, b.month):
        return fmt_month(a)
    if a.year == b.year:
        return "%s–%s %d" % (U.MONTHS[a.month - 1], U.MONTHS[b.month - 1], b.year)
    return "%s–%s" % (fmt_month(a), fmt_month(b))


def _complete(pre, X, t, S):
    """Install day X is complete at age t: X + t is settled and every activity day of [X, X + t] is folded (and Q-B's
    window reached lag t on each of them)."""
    return X + timedelta(days=t) <= S and pre.all(pre.g, X, X + timedelta(days=t)) and \
        pre.win_ok(X, X, X + timedelta(days=t))


def _pearson(each, cap):
    """Day-to-day overdispersion of rates [(returners, installs)] around their own pooled rate: χ² / (m − 1), clamped
    to [1, cap] — None when it cannot be measured."""
    x, n = sum(e[0] for e in each), sum(e[1] for e in each)
    if len(each) < 2 or not n:
        return None
    p = x / n
    if not 0 < p < 1:
        return None
    chi = sum((xw - nw * p) ** 2 / (nw * p * (1 - p)) for xw, nw in each if nw > 0)
    return min(max(chi / (len(each) - 1), 1.0), cap)


def _resid_se(ys):
    """The residual SE of a pooled per-install value over [(y, n)] (y = the sum, n = installs): e = (y − R·n)/n̄,
    s² = Σe² / (m − 1), SE = s / √m (m ≥ 3; else None)."""
    ys = [(y, n) for y, n in ys if n > 0]
    if len(ys) < 3:
        return None
    R = sum(y for y, _ in ys) / sum(n for _, n in ys)
    nbar = sum(n for _, n in ys) / len(ys)
    s2 = sum(((y - R * n) / nbar) ** 2 for y, n in ys) / (len(ys) - 1)
    return math.sqrt(s2) / math.sqrt(len(ys))


def _paid(spend, days, n):
    """The paid share π = Σ Google Ads installs ÷ Σ installs over the install days (None without Google Ads data)."""
    inst = (spend or {}).get("installs") or {}
    if not inst or not n:
        return None
    return min(1.0, sum(float(inst.get(_iso(X)) or 0) for X in days) / n)


# ── C: new users by app version ─────────────────────────────────────────────────────────────────

def _release_of(releases, ver):
    """The earliest release of this version ({date, version, kind, key}) — or None."""
    best = None
    for r in releases or []:
        v = str((r or {}).get("version") or "")
        if not v or (v != ver and v.lstrip("vV") != ver.lstrip("vV")):
            continue
        try:
            d = V._d(r.get("date"))
        except (TypeError, ValueError, AttributeError):
            continue
        if best is None or d < best[0]:
            best = (d, {"date": _iso(d), "version": r.get("version"), "kind": r.get("kind"), "key": r.get("key")})
    return best[1] if best else None


def _dominant(P, store):
    """→ (groups {version: [install days, oldest first]}, share {day: dominant share}, left_out, no_vuse, both, dom
    [(day, version)] every dominant day in order)."""
    vuse = store.get("vuse") or {}
    xs = P["xs"]
    groups, share, dom = {}, {}, []
    left = {"days": 0, "n": 0}
    nov = {"days": 0, "n": 0}
    both = 0
    for X in sorted(xs):
        n = xs[X]["n"]
        if n <= 0:
            continue
        vu = vuse.get(_iso(X))
        if not isinstance(vu, dict) or not vu:
            nov["days"] += 1
            nov["n"] += n
            continue
        tot, real = 0, {}
        for v, a in vu.items():
            try:
                u = int((a or [0])[0] or 0)
            except (TypeError, ValueError, IndexError):
                continue
            tot += u
            if v not in NOT_VER:
                real[str(v)] = u
        if tot <= 0 or not real:
            nov["days"] += 1
            nov["n"] += n
            continue
        both += 1
        v = max(real, key=lambda k: (real[k], k))
        s = real[v] / tot
        if s < VER_DOM:
            left["days"] += 1
            left["n"] += n
            continue
        groups.setdefault(v, []).append(X)
        share[X] = s
        dom.append((X, v))
    return groups, share, left, nov, both, dom


def _ver_phi(P, groups, t):
    """φ_t: the median over versions (≥ VER_PHI_MIN_DAYS complete days in the last VER_PHI_DAYS install days, each
    with ≥ VER_PHI_DAY_N installs) of the day-to-day Pearson χ² / (m − 1) — within-version noise (weekday, campaign
    mix), never the versions' own differences; clamped to [1, VER_PHI_CAP], PHI_DEFAULT without any."""
    S, pre, xs = P["S"], P["pre"], P["xs"]
    j = V.ULAGS.index(t)
    lo = S - timedelta(days=VER_PHI_DAYS)
    vals = []
    for v in sorted(groups):
        each = [(xs[X]["u"][j], xs[X]["n"]) for X in groups[v]
                if X >= lo and xs[X]["n"] >= VER_PHI_DAY_N and _complete(pre, X, t, S)]
        if len(each) < VER_PHI_MIN_DAYS:
            continue
        f = _pearson(each, VER_PHI_CAP)
        if f is not None:
            vals.append(f)
    return min(max(V._med(vals), 1.0), VER_PHI_CAP) if vals else V.PHI_DEFAULT


def _ver_cell(P, days, t, phi, row_n, first, last, what):
    """One version's cell at age t over its install days: wait (no day old enough: `in` days) / nodata (old enough,
    not in the ledger) / few / part (only some days old enough: the value over those, `days` of `of`) / ok."""
    S, pre, xs = P["S"], P["pre"], P["xs"]
    comp = [X for X in days if _complete(pre, X, t, S)]
    pend = [X for X in days if X + timedelta(days=t) > S]
    of = len(days)
    if not comp:
        if len(pend) == of:
            st, inn = "wait", max(1, (first + timedelta(days=t) - S).days)
        else:
            st, inn = "nodata", None
        if what == "d":
            return {"v": None, "lo": None, "hi": None, "n": 0, "ret": None, "st": st, "days": 0, "of": of, "in": inn,
                    "q": False}
        return {"v": None, "lo": None, "hi": None, "est": False, "n": 0, "st": st, "days": 0, "of": of, "in": inn}
    n = sum(xs[X]["n"] for X in comp)
    q = any(pre.any(pre.q, X, X + timedelta(days=t)) for X in comp)
    inn = max(1, (max(pend) + timedelta(days=t) - S).days) if pend else None
    if what == "d":
        x = sum(xs[X]["u"][V.ULAGS.index(t)] for X in comp)
        p, lo, hi = V._wilson(x, n, phi)
        if row_n < VER_JUDGE_N:
            st = "few"
        elif len(comp) < of:
            st = "part"
        elif n < VER_JUDGE_N or x < VER_MIN_RET:
            st = "few"
        else:
            st = "ok"
        out = {"v": _g4(100 * p) if p is not None else None, "lo": _g4(100 * lo) if lo is not None else None,
               "hi": _g4(100 * hi) if hi is not None else None, "n": int(n), "ret": int(x), "st": st,
               "days": len(comp), "of": of, "in": inn if st == "part" else None, "q": bool(q)}
        if st == "part" and (n < VER_JUDGE_N or x < VER_MIN_RET):
            out["few"] = True                        # only some days old enough, and those few: grey, never settled
        return out
    j = V.T.index(t)
    y = sum(xs[X]["R"][j] for X in comp)
    R = y / n if n else None
    se = _resid_se([(xs[X]["R"][j], xs[X]["n"]) for X in comp])
    half = V.WILSON_Z * se if se is not None else None
    est = q or se is None or any(xs[X]["E"][j] for X in comp)
    if row_n < VER_JUDGE_N:
        st = "few"
    elif len(comp) < of:
        st = "part"
    elif n < VER_JUDGE_N:
        st = "few"
    else:
        st = "ok"
    out = {"v": _m6(R), "lo": _m6(max(R - half, 0.0)) if (half is not None and R is not None) else None,
           "hi": _m6(R + half) if (half is not None and R is not None) else None, "est": bool(est), "n": int(n),
           "st": st, "days": len(comp), "of": of, "in": inn if st == "part" else None}
    if st == "part" and n < VER_JUDGE_N:
        out["few"] = True
    return out


def _side_rate(P, days, t):
    xs = P["xs"]
    j = V.ULAGS.index(t)
    return sum(xs[X]["u"][j] for X in days), sum(xs[X]["n"] for X in days)


def _short_st(c1, c0, pend):
    """Either side under VER_MIN_DAYS complete days: "wait" while a side still has install days getting old enough,
    "short" when it never will (a finished one- or two-day hotfix: too short to compare, however many installs)."""
    return "wait" if pend else "short"


def _vs_d(P, c1, c0, t, phi, pend=True):
    """The same-age comparison of D-t: recent = the new version's first VER_WIN_DAYS complete days, base = the
    previous version's last VER_WIN_DAYS — next to each other in time (season and campaign drift stay out). pend:
    a side still has install days that are not old enough yet."""
    x1, n1 = _side_rate(P, c1, t)
    x0, n0 = _side_rate(P, c0, t)
    out = {"v0": _g4(100 * x0 / n0) if n0 else None, "v1": _g4(100 * x1 / n1) if n1 else None, "delta": None,
           "rel": None, "z": None, "n0": int(n0), "n1": int(n1), "ret0": int(x0), "ret1": int(x1),
           "days0": len(c0), "days1": len(c1), "from0": _iso(min(c0)) if c0 else None,
           "to0": _iso(max(c0)) if c0 else None, "from1": _iso(min(c1)) if c1 else None,
           "to1": _iso(max(c1)) if c1 else None, "st": "wait"}
    if len(c1) < VER_MIN_DAYS or len(c0) < VER_MIN_DAYS:
        out["st"] = _short_st(c1, c0, pend)
        return out
    if n1 < VER_JUDGE_N or n0 < VER_JUDGE_N or x1 < VER_MIN_RET or x0 < VER_MIN_RET:
        out["st"] = "few"
        return out
    p1, p0 = x1 / n1, x0 / n0
    se = math.sqrt(phi * (p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0))
    z = (p1 - p0) / se if se > 0 else 0.0
    delta = 100 * (p1 - p0)
    rel = p1 / p0 - 1 if p0 > 0 else None
    out.update(delta=_g4(delta), rel=_g4(rel), z=_g4(z))
    thr = VER_MINPP[t]
    if rel is not None and delta <= -thr and rel <= -VER_MINREL and z <= -VER_Z:
        out["st"] = "worse"
    elif rel is not None and delta >= thr and rel >= VER_MINREL and z >= VER_Z:
        out["st"] = "better"
    else:
        out["st"] = "same"
    return out


def _vs_rpi(P, c1, c0, t=7, pend=True):
    xs = P["xs"]
    j = V.T.index(t)
    y1, n1 = sum(xs[X]["R"][j] for X in c1), sum(xs[X]["n"] for X in c1)
    y0, n0 = sum(xs[X]["R"][j] for X in c0), sum(xs[X]["n"] for X in c0)
    R1, R0 = (y1 / n1 if n1 else None), (y0 / n0 if n0 else None)
    out = {"v0": _m6(R0), "v1": _m6(R1), "rel": None, "z": None, "n0": int(n0), "n1": int(n1), "days0": len(c0),
           "days1": len(c1), "from0": _iso(min(c0)) if c0 else None, "to0": _iso(max(c0)) if c0 else None,
           "from1": _iso(min(c1)) if c1 else None, "to1": _iso(max(c1)) if c1 else None,
           "est": any(xs[X]["E"][j] for X in list(c1) + list(c0)), "st": "wait"}
    if len(c1) < VER_MIN_DAYS or len(c0) < VER_MIN_DAYS:
        out["st"] = _short_st(c1, c0, pend)
        return out
    se1 = _resid_se([(xs[X]["R"][j], xs[X]["n"]) for X in c1])
    se0 = _resid_se([(xs[X]["R"][j], xs[X]["n"]) for X in c0])
    if n1 < VER_JUDGE_N or n0 < VER_JUDGE_N or se1 is None or se0 is None or not R0:
        out["st"] = "few"
        return out
    se = math.sqrt(se1 * se1 + se0 * se0)
    z = (R1 - R0) / se if se > 0 else 0.0
    rel = R1 / R0 - 1
    out.update(rel=_g4(rel), z=_g4(z))
    if rel <= -VER_RPI_REL and z <= -VER_Z:
        out["st"] = "worse"
    elif rel >= VER_RPI_REL and z >= VER_Z:
        out["st"] = "better"
    else:
        out["st"] = "same"
    return out


def _row_verdict(vs):
    a, b = vs["d1"]["st"], vs["d7"]["st"]
    if "worse" in (a, b):
        return "worse"
    if "better" in (a, b):
        return "better"
    if "same" in (a, b):
        return "same"
    if a == "wait" and b == "wait":
        return "wait"
    if "short" in (a, b):                            # finished in under VER_MIN_DAYS days: never comparable
        return "short"
    return "few"


def _ver_row_text(r):
    lab = r["label"]
    if r["verdict"] == "few" and r["vs"] is None:
        return "%s: sirf %s installs — tulna ke liye kam (%d chahiye)" % (lab, _n(r["n"]), VER_JUDGE_N)
    if r["verdict"] == "short":
        d1 = r["d1"]
        return "%s: %s installs, sirf %s din naye users isi version pe aaye%s — tulna ke liye %d+ din chahiye" % (
            lab, _n(r["n"]), _n(r["days"]),
            (" (back next day %s)" % _ip(d1["v"])) if d1.get("v") is not None and d1["st"] != "wait" else "",
            VER_MIN_DAYS)
    d1, d7 = r["d1"], r["d7"]
    if d1["st"] in ("wait", "nodata"):
        return "%s: %s installs — back next day ka number %s" % (
            lab, _n(r["n"]), ("%d din me" % d1["in"]) if d1.get("in") else "abhi nahi mila")
    vs = r["vs"] or {}
    a1 = (vs.get("d1") or {}).get("v1") if vs else None
    b1 = (vs.get("d1") or {}).get("v0") if vs else None
    a7 = (vs.get("d7") or {}).get("v1") if vs else None
    b7 = (vs.get("d7") or {}).get("v0") if vs else None
    a1 = a1 if a1 is not None else d1["v"]
    a7 = a7 if a7 is not None else d7["v"]
    txt = "%s: %s back next day" % (lab, _ip(a1))
    if d7["st"] in ("wait", "nodata") or a7 is None:
        txt += ", back after 7 days ka number %s" % (("%d din me" % d7["in"]) if d7.get("in") else "abhi nahi")
    else:
        txt += ", %s back after 7 days" % _ip(a7)
    if vs and b1 is not None:
        txt += " (pichhla %s: %s%s)" % (vs["label"], _ip(b1), (", %s" % _ip(b7)) if b7 is not None else "")
    r30 = (r["rpi"].get("30") or {}).get("v")
    if r30 is not None:
        txt += " — 30 din me earning per install %s%s" % ("≈" if r["rpi"]["30"].get("est") else "", V.t_m(r30))
    if r["verdict"] == "worse":
        txt += " — naye users kam ruk rahe"
    elif r["verdict"] == "better":
        txt += " — naye users zyada ruk rahe"
    return txt


def _ver_summary(rows, S):
    lead = next((r for r in rows if r.get("vs") and r["verdict"] != "short"), None) or \
        next((r for r in rows if r.get("vs")), None)
    if lead is None:
        r = rows[0]
        return "%s (%s se, %s installs): tulna ke liye installs kam." % (r["label"], U.fmt_day(V._d(r["from"]), S),
                                                                        _n(r["n"]))
    vs = lead["vs"]
    head = "%s (%s se, %s installs)" % (lead["label"], U.fmt_day(V._d(lead["from"]), S), _n(lead["n"]))
    d1, d7 = vs["d1"], vs["d7"]
    if d1["st"] != "wait" and d1["v1"] is not None and d1["v0"] is not None:
        txt = "%s: back next day %s — pichhle %s me %s" % (head, _ip(d1["v1"]), vs["label"], _ip(d1["v0"]))
        if d7["st"] != "wait" and d7["v1"] is not None and d7["v0"] is not None:
            txt += "; back after 7 days %s vs %s" % (_ip(d7["v1"]), _ip(d7["v0"]))
    else:
        txt = "%s: pichhle %s se tulna abhi nahi" % (head, vs["label"])
    v = lead["verdict"]
    if v == "worse":
        txt += ". Naye users kam ruk rahe."
    elif v == "better":
        txt += ". Naye users zyada ruk rahe."
    elif v == "same":
        txt += ". Pichhle jaisa."
    elif v == "wait":
        inn = next((lead[k]["in"] for k in ("d1", "d7") if lead[k].get("in")), None)
        txt += (". Pakka number %d din me." % inn) if inn else ". Pakka number jaldi."
    elif v == "short":
        txt += ". Sirf %s din ka version — tulna ke liye %d+ din chahiye." % (_n(lead["days"]), VER_MIN_DAYS)
    else:
        txt += ". Tulna ke liye installs kam."
    return txt


def versions(P, store, releases, impact, E, advanced, streak, app, market=None, spend=None):
    """C (SPEC_CD_GEO §C.2–C.7) → (by_version, conditions). `streak` (the value evaluation's) is updated in place only
    when the weekly evaluation advanced. by_version carries three private keys evaluate_app takes off: _info (info
    rows), _seen (the `ver` input: ≥ 2 versions with ≥ INPUT_VER_N installs complete at D1), _live (the versions that
    may alert: an open ver_ret of any other version closes)."""
    S = P["S"]
    out = {"state": "ok", "text": None, "dom_min": VER_DOM, "left_out": {"days": 0, "n": 0},
           "no_vuse": {"days": 0, "n": 0}, "phi": {}, "short": {"versions": 0, "n": 0}, "older": 0, "rows": [],
           "_info": [], "_seen": False, "_live": None}
    split = ((store.get("flags") or {}).get("impact") or {}).get("vuse_split") is not False
    if not split:
        out.update(state="nosplit", text="GA4 is app ke naye users ka version alag nahi deta — version-wise data nahi.")
        return out, []
    groups, share, left, nov, both, dom = _dominant(P, store)
    out["left_out"], out["no_vuse"] = left, nov
    if not both:
        out.update(state="nodata", text="⏳ Version-wise data aa raha.")
        return out, []
    xs = P["xs"]
    phi = {t: _ver_phi(P, groups, t) for t in VER_T}
    out["phi"] = {str(t): _g4(v) for t, v in phi.items()}
    info = []
    # every version (short ones too: a short hotfix is named where it is skipped)
    allv = []
    for v, days in groups.items():
        n = sum(xs[X]["n"] for X in days)
        allv.append({"ver": v, "days": days, "from": days[0], "to": days[-1], "n": n})
    allv.sort(key=lambda a: (a["from"], a["ver"]))
    newest = dom[-1][1] if dom else None
    rows = []
    for a in allv:
        if a["n"] < VER_SHOW_N:
            out["short"]["versions"] += 1
            out["short"]["n"] += int(a["n"])
            continue
        days = a["days"]
        others = {v for X, v in dom if a["from"] < X < a["to"] and v != a["ver"]}
        r = {"ver": a["ver"], "label": label(a["ver"]), "from": _iso(a["from"]), "to": _iso(a["to"]),
             "days": len(days), "n": int(a["n"]),
             "share_dom": _g4(sum(share[X] * xs[X]["n"] for X in days) / a["n"]) if a["n"] else None,
             "current": a["ver"] == newest, "gaps": bool(others),
             "release": _release_of(releases, a["ver"])}
        for t in VER_T:
            r["d%d" % t] = _ver_cell(P, days, t, phi[t], a["n"], a["from"], a["to"], "d")
        r["rpi"] = {str(t): _ver_cell(P, days, t, phi[t], a["n"], a["from"], a["to"], "r") for t in VER_T}
        r["vs"], r["verdict"], r["text"] = None, ("few" if a["n"] < VER_JUDGE_N else None), None
        r["_a"] = a
        rows.append(r)
    if not rows:
        out.update(state="low", text="Kisi version pe %d+ installs nahi — version-wise faisla nahi." % VER_SHOW_N,
                   _live=set())
        return out, []
    # the previous version: the newest one before it with ≥ VER_JUDGE_N installs on ≥ VER_MIN_DAYS dominant days
    for r in rows:
        a = r["_a"]
        if a["n"] < VER_JUDGE_N:
            continue
        prev = [b for b in allv if b["from"] < a["from"] and b["n"] >= VER_JUDGE_N and len(b["days"]) >= VER_MIN_DAYS]
        if not prev:
            continue
        p = prev[-1]
        skipped = [b["ver"] for b in allv if p["from"] < b["from"] < a["from"]]
        vs = {"ver": p["ver"], "label": label(p["ver"]), "skipped": skipped}
        r["_sides"] = {}
        for t in VER_T:
            c1 = [X for X in a["days"] if _complete(P["pre"], X, t, S)][:VER_WIN_DAYS]
            c0 = [X for X in p["days"] if _complete(P["pre"], X, t, S)][-VER_WIN_DAYS:]
            pend = a["ver"] == newest or any(X + timedelta(days=t) > S for X in a["days"] + p["days"])
            r["_sides"][t] = (c1, c0)
            vs["d%d" % t] = _vs_d(P, c1, c0, t, phi[t], pend)
            if t == 7:
                vs["rpi7"] = _vs_rpi(P, c1, c0, 7, pend)
        r["vs"] = vs
        r["verdict"] = _row_verdict(vs)
    for r in rows:
        r["text"] = _ver_row_text(r)
    rows.sort(key=lambda r: (r["from"], r["ver"]), reverse=True)            # newest first
    out["older"] = max(0, len(rows) - VER_ROWS)
    shown = rows[:VER_ROWS]
    out["state"] = "single" if len(rows) == 1 else "ok"
    if out["state"] == "single":
        out["text"] = "Abhi ek hi version (%s) — tulna ke liye agla update chahiye." % rows[0]["label"]
    else:
        out["text"] = _ver_summary(shown, S)
    # the `ver` input: ≥ 2 versions with ≥ INPUT_VER_N installs complete at D1
    out["_seen"] = sum(1 for r in rows if r["d1"]["n"] >= INPUT_VER_N) >= 2
    # alerts: the newest VER_ALERT_TOP versions that can be judged — ≥ VER_ALERT_N installs over ≥ VER_MIN_DAYS dominant
    # days (a short hotfix never takes a place) — and began within VER_ALERT_DAYS of E; plus any such version whose
    # condition held at the evaluation before (streak 1): a bad release followed fast by hotfixes / a quick next
    # version still gets its second evaluation instead of being pushed out after one
    recent = [r for r in rows if V._d(r["from"]) >= E - timedelta(days=VER_ALERT_DAYS)]
    cands = [r for r in recent if r["n"] >= VER_ALERT_N and r["days"] >= VER_MIN_DAYS][:VER_ALERT_TOP]
    pending = {k.split("|")[1] for k, v in streak.items() if k.startswith("ver_ret|") and v == 1}
    cands += [r for r in recent if r not in cands and r["ver"] in pending]
    out["_live"] = {r["ver"] for r in cands}
    byver = {r["ver"]: r for r in rows}
    conds = []
    touched = set()
    # … and the newest VER_ALERT_TOP recent rows too, for the info row only: a worse version too small to alert is
    # said (ver_mix) — its sides can never reach VER_ALERT_N, so no streak of it ever counts
    for r in cands + [r for r in recent[:VER_ALERT_TOP] if r not in cands]:
        vs = r["vs"]
        if not vs:
            continue
        # a recovery: the version before was itself worse than ITS previous — "higher" than a bad release is no news
        recovery = (byver.get(vs["ver"]) or {}).get("verdict") == "worse"
        hits = {"down": [], "up": []}
        for met, t in (("d1", 1), ("d7", 7)):
            s = vs[met]
            big = (s["st"] in ("worse", "better") and min(s["n0"], s["n1"]) >= VER_ALERT_N
                   and min(s["ret0"], s["ret1"]) >= VER_ALERT_RET and min(s["days0"], s["days1"]) >= VER_MIN_DAYS)
            for dr, want in (("down", "worse"), ("up", "better")):
                k = "ver_ret|%s|%s|%s" % (r["ver"], met, dr)
                true_now = big and s["st"] == want and not (dr == "up" and recovery)
                if advanced:
                    streak[k] = (streak.get(k, 0) + 1) if true_now else 0
                    touched.add(k)
                if true_now and streak.get(k, 0) >= 2:
                    hits[dr].append({"metric": met, "t": t, "s": s, "z": s["z"] or 0})
                elif want == "worse" and s["st"] == "worse" and not big and not any(
                        i["ver"] == r["ver"] for i in info if i["kind"] == "ver_mix"):   # one row per version
                    info.append({"kind": "ver_mix", "ver": r["ver"], "from": s["from1"], "to": s["to1"],
                                 "text": "%s ke baad naye users %s kam dikhte (%s, pichhle %s me %s) — "
                                         "installs abhi kam, isliye alert nahi" % (
                                             r["label"], NWORD[t], _ip(s["v1"]), vs["label"], _ip(s["v0"]))})
        s = vs["rpi7"]
        big = (s["st"] == "worse" and min(s["n0"], s["n1"]) >= VER_ALERT_N
               and min(s["days0"], s["days1"]) >= VER_MIN_DAYS)
        k = "ver_ret|%s|rpi7|down" % r["ver"]
        if advanced:
            streak[k] = (streak.get(k, 0) + 1) if big else 0
            touched.add(k)
        if big and streak.get(k, 0) >= 2:
            hits["down"].append({"metric": "rpi7", "t": 7, "s": s, "z": s["z"] or 0})
        for dr in ("down", "up"):
            hs = sorted(hits[dr], key=lambda h: (-abs(h["z"]), h["metric"]))
            if hs:
                conds.append(_ver_cond(P, r, vs, dr, hs, impact, market, spend, app))
    if advanced:                                     # a version no longer judged: its streaks end
        for k in list(streak):
            if k.startswith("ver_ret|") and k not in touched:
                streak[k] = 0
    # info rows: a version's 30-day return moved (never an alert, never counted, never coloured)
    for r in rows[:VER_ALERT_TOP]:
        s = (r["vs"] or {}).get("d30")
        if s and s["st"] in ("worse", "better"):
            info.append({"kind": "ver_d30", "ver": r["ver"], "from": s["from1"], "to": s["to1"],
                         "text": "%s ke naye users back after 30 days %s: %s, pichhle %s me %s" % (
                             r["label"], "kam" if s["st"] == "worse" else "zyada", _p1(s["v1"]), r["vs"]["label"],
                             _p1(s["v0"]))})
    for r in rows:
        r.pop("_a", None)
        r.pop("_sides", None)
    # every version row, newest first: the page shows the newest VER_ROWS and folds the `older` rest ("Older versions
    # (k)" opens them; a 📦 / 🧬 link to an older version opens the fold) — at most a year of versions (vuse)
    out["rows"] = rows
    out["_info"] = info
    return out, conds


def _ver_cond(P, r, vs, dr, hs, impact, market, spend, app):
    lead = hs[0]
    s = lead["s"]
    met = lead["metric"]
    d1, d0 = r["_sides"][lead["t"]]                  # the exact install days each side was measured on
    xs = P["xs"]
    n1, n0 = sum(xs[X]["n"] for X in d1), sum(xs[X]["n"] for X in d0)
    tags, mix = [], None
    p1, p0 = _paid(spend, d1, n1), _paid(spend, d0, n0)
    if p1 is not None and p0 is not None and abs(p1 - p0) * 100 >= VER_MIX_PTS:
        mix = {"p0": _g4(p0), "p1": _g4(p1)}
    i1 = n1 / len(d1) if d1 else None
    i0 = n0 / len(d0) if d0 else None
    if mix is None and i1 and i0 and (i1 / i0 >= VER_MIX_INST or i1 / i0 <= 1 / VER_MIX_INST):
        mix = {"i0": _g4(i0), "i1": _g4(i1)}
    if mix is not None:
        tags.append("mix")
    if r.get("release"):
        tags.append("update")
    blk = (impact or {}).get(r["ver"]) or {}
    lst = blk.get("worse" if dr == "down" else "better") or []
    linked = any(("new_d%d" % h["t"]) in lst for h in hs if h["metric"] in ("d1", "d7"))
    held, kbad, mk = False, False, None
    if met == "rpi7":
        a, b = V._d(s["from1"]), V._d(s["to1"]) + timedelta(days=7)
        mk = V._market_hit(market, dr, a, b)
        kbad = V.k_est(P["sc"], V._d(s["from0"]), b)
        if mk:
            tags.append("market_wide")
        held = bool(mk or kbad)
    sev = "good" if dr == "up" else "watch"
    if dr == "down" and r.get("current") and mix is None and not linked:
        for h in hs:
            x = h["s"]
            if (h["metric"] in ("d1", "d7") and x["delta"] is not None and x["delta"] <= -2 * VER_MINPP[h["t"]]
                    and (x["z"] or 0) <= -VER_WARN_Z and x["n1"] >= 3 * VER_ALERT_N):
                sev = "warning"
    if held and sev == "warning":
        sev = "watch"
    return {"key": "%s|ver_ret|%s|%s" % (app["id"], r["ver"], dr), "family": "ver_ret", "metric": met, "dir": dr,
            "cc": None, "ver": r["ver"], "ver_label": r["label"], "pver_label": vs["label"], "severity": sev,
            "now": s["v1"], "before": s["v0"], "rel": s.get("rel"), "delta_pp": s.get("delta"), "z": s.get("z"),
            "also": [h["metric"] for h in hs[1:]], "week_from": s["from1"], "week_to": s["to1"],
            "base_from": s["from0"], "base_to": s["to0"], "users": int(s["n1"]), "spend": None, "tags": tags,
            "release": dict(r["release"]) if r.get("release") else None, "linked": bool(linked), "mix": mix,
            "market": mk, "_force_seed": bool(linked or held), "_est": bool(kbad)}


def ver_alert_text(s):
    """A ver_ret episode's snapshot → its Hinglish sentence (money as tokens)."""
    lab, plab = s.get("ver_label") or label(s.get("ver") or "?"), s.get("pver_label") or "pichhla version"
    if s.get("metric") == "rpi7":
        rel = s.get("rel")
        txt = "%s ke naye users ki earning (7 din) %s: %s per install, pichhle %s me %s%s" % (
            lab, "kam" if s.get("dir") == "down" else "zyada", V.t_m(s.get("now")), plab, V.t_m(s.get("before")),
            (" (%s%s)" % ("+" if rel > 0 else "", V._pct(rel))) if rel is not None else "")
    else:
        n = int(str(s.get("metric") or "d1")[1:] or 1)
        word = NWORD.get(n, "back after %d days" % n)
        if s.get("dir") == "down":
            txt = ("%s ke baad naye users kam ruk rahe: %s %s, pichhle %s me %s (%s installs, 2 hafte se)"
                   % (lab, word, _ip(s.get("now")), plab, _ip(s.get("before")), _n(s.get("users"))))
        else:
            txt = "%s ke baad naye users zyada ruk rahe: %s %s, pichhle %s me %s" % (
                lab, word, _ip(s.get("now")), plab, _ip(s.get("before")))
    mix = s.get("mix") or {}
    if s.get("dir") == "down" and mix.get("p0") is not None:
        txt += " — shayad installs ka mix badla (ads wale %d%% → %d%%)" % (
            round(100 * mix["p0"]), round(100 * mix["p1"]))
    elif s.get("dir") == "down" and mix.get("i0") is not None:
        txt += " — shayad installs ka mix badla (roz ke installs %s → %s)" % (_n(mix["i0"]), _n(mix["i1"]))
    if "market_wide" in (s.get("tags") or []):
        txt += " · ad rate sab apps me %s" % ("gira" if s.get("dir") == "down" else "badha")
    if s.get("linked"):
        txt += " (Update impact me bataya)"
    return txt


# ── D: long-term by install month ───────────────────────────────────────────────────────────────

def _month_start(d):
    return d.replace(day=1)


def _month_end(d):
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - ONE


def _quarter_start(d):
    return date(d.year, 3 * (_quarter(d) - 1) + 1, 1)


def _quarter_end(d):
    q = _quarter(d)
    nxt = date(d.year + (q == 4), (3 * q) % 12 + 1, 1)
    return nxt - ONE


def _periods(P, start, grain):
    """The install periods (months / quarters) from the one holding `start` to the last one wholly settled (the
    running period is never a row) → [{key, label, year, a (period start), from, to, part}]."""
    S = P["S"]
    first = _month_start if grain == "month" else _quarter_start
    last = _month_end if grain == "month" else _quarter_end
    out = []
    m = first(start)
    while m <= S:
        e = last(m)
        if e > S:
            break
        fr = max(m, start)
        key = "%04d-%02d" % (m.year, m.month) if grain == "month" else "%04d-Q%d" % (m.year, _quarter(m))
        out.append({"key": key, "label": fmt_month(m) if grain == "month" else _qlabel(m), "year": m.year, "a": m,
                    "from": fr, "to": e, "part": fr > m})
        m = e + ONE
    return out


def _grain(P, start):
    """month when the median installs of the last 12 whole months ≥ LONG_MIN_N, else quarter when that of the last 4
    whole quarters is, else None (low). Without a whole period yet: the installs per day so far × the period."""
    xs = P["xs"]

    def per(grain, k, days_per):
        ps = [p for p in _periods(P, start, grain) if not p["part"]]
        if ps:
            ns = [sum(xs[X]["n"] for X in xs if p["from"] <= X <= p["to"]) for p in ps[-k:]]
            return V._med(ns)
        span = [X for X in xs if X >= start]
        if not span:
            return 0
        return sum(xs[X]["n"] for X in span) / max(1, (P["S"] - start).days + 1) * days_per
    if per("month", LONG_GRAIN_MONTHS, 30.44) >= LONG_MIN_N:
        return "month"
    if per("quarter", LONG_GRAIN_QUARTERS, 91.31) >= LONG_MIN_N:
        return "quarter"
    return None


def _row_complete(P, row, t):
    S, pre = P["S"], P["pre"]
    a, b = row["from"], row["to"]
    if b + timedelta(days=t) > S or not pre.all(pre.g, a, b + timedelta(days=t)):
        return False
    if pre.win is None:
        return True
    X = a
    while X <= b:
        if not pre.win_ok(X, X, X + timedelta(days=t)):
            return False
        X += ONE
    return True


def _row_days(P, row):
    return [X for X in sorted(P["xs"]) if row["from"] <= X <= row["to"]]


def _spend_usd(spend, fx, a, b):
    """The app's Google Ads spend (USD at each day's rate) over [a, b] — None unless [a, b] lies inside the spend
    cache's fetched span (a stale cache never reads as $0) and every day with spend has a rate."""
    sp = spend or {}
    if not sp or not sp.get("first") or not sp.get("till") or _iso(a) < sp["first"] or _iso(b) > sp["till"]:
        return None
    f, _ = V._fx_fn(fx, sp.get("ccy") or "USD")
    s = 0.0
    d = a
    while d <= b:
        v = (sp.get("daily") or {}).get(_iso(d))
        if v:
            r = f(d)
            if r is None:
                return None
            s += float(v) / 1e6 * r
        d += ONE
    return s


def long_term(P, shapes, spend, fx, releases, ida, E, advanced, app):
    """D (SPEC_CD_GEO §D.2–D.5) → (long, conditions). long carries two private keys evaluate_app takes off: _info
    (long_up rows) and _seen (the `long` input: ≥ INPUT_LONG_ROWS complete whole rows at D60)."""
    S, hs, pre, xs = P["S"], P["hs"], P["pre"], P["xs"]
    edge = (ida or {}).get("edge")
    starts = [hs]
    for k in ((ida or {}).get("from"), edge):
        try:
            if k:
                starts.append(V._d(k))
        except (TypeError, ValueError):
            pass
    start = max(starts)
    out = {"state": "ok", "grain": None, "text": None, "note": None, "edge": edge,
           "phi": {str(t): None for t in LONG_T}, "rows": [], "base": {"60": None, "90": None, "rpi180": None},
           "_info": [], "_seen": False}
    grain = _grain(P, start)
    if grain is None:
        out.update(state="low", text="Is app me mahine ke install kam — lambi wapsi ka number pakka nahi.")
        return out, []
    out["grain"] = grain
    if grain == "quarter":
        out["note"] = "Is app me mahine ke install %s se kam — isliye 3-3 mahine milake." % _n(LONG_MIN_N)
    rows = _periods(P, start, grain)
    for r in rows:
        r["_days"] = _row_days(P, r)
        r["n"] = int(sum(xs[X]["n"] for X in r["_days"]))
        r["days"] = (r["to"] - r["from"]).days + 1
        r["_c"] = {t: _row_complete(P, r, t) for t in sorted(set(LONG_T) | set(LONG_RT) | {180})}
    # φ per age: the median over complete rows of their day-to-day Pearson χ² / (m − 1)
    phi = {}
    for t in LONG_T:
        j = V.ULAGS.index(t)
        vals = []
        for r in rows:
            if not r["_c"][t]:
                continue
            each = [(xs[X]["u"][j], xs[X]["n"]) for X in r["_days"] if xs[X]["n"] >= VER_PHI_DAY_N]
            if len(each) >= VER_PHI_MIN_DAYS:
                f = _pearson(each, VER_PHI_CAP)
                if f is not None:
                    vals.append(f)
        phi[t] = min(max(V._med(vals), 1.0), VER_PHI_CAP) if vals else V.PHI_DEFAULT
    out["phi"] = {str(t): _g4(phi[t]) for t in LONG_T}
    for r in rows:
        r["d"], qs = {}, False
        for t in LONG_T:
            j = V.ULAGS.index(t)
            if r["_c"][t] and r["n"] > 0:
                x = sum(xs[X]["u"][j] for X in r["_days"])
                p, lo, hi = V._wilson(x, r["n"], phi[t])
                qs = qs or pre.any(pre.q, r["from"], r["to"] + timedelta(days=t))
                r["d"][str(t)] = {"v": _g4(100 * p), "lo": _g4(100 * lo), "hi": _g4(100 * hi), "ret": int(x),
                                  "st": "few" if x < LONG_MIN_RET else "ok", "in": None}
            elif r["to"] + timedelta(days=t) > S:
                r["d"][str(t)] = {"v": None, "lo": None, "hi": None, "ret": None, "st": "wait",
                                  "in": (r["to"] + timedelta(days=t) - S).days}
            else:
                r["d"][str(t)] = {"v": None, "lo": None, "hi": None, "ret": None, "st": "nodata", "in": None}
        r["rpi"] = {}
        for t in LONG_RT:
            j = V.T.index(t)
            if r["_c"][t] and r["n"] > 0:
                y = sum(xs[X]["R"][j] for X in r["_days"])
                R = y / r["n"]
                q = pre.any(pre.q, r["from"], r["to"] + timedelta(days=t))
                qs = qs or q
                se = _resid_se([(xs[X]["R"][j], xs[X]["n"]) for X in r["_days"]])
                half = V.WILSON_Z * se if se is not None else None
                r["rpi"][str(t)] = {"v": _m6(R), "lo": _m6(max(R - half, 0.0)) if half is not None else None,
                                    "hi": _m6(R + half) if half is not None else None,
                                    "est": bool(q or any(xs[X]["E"][j] for X in r["_days"])), "proj": False,
                                    "shape": None, "st": "ok", "in": None}
                continue
            to = next((tt for tt in (180, 90, 60, 30) if tt < t and tt >= LONG_PROJ_MIN_T and r["_c"][tt]), None)
            cell = None
            if to is not None and r["n"] > 0:
                s, how = shapes.get(V.T.index(to), j) if shapes is not None else (None, None)
                if s is not None:
                    Ro = sum(xs[X]["R"][V.T.index(to)] for X in r["_days"]) / r["n"]
                    cell = {"v": _m6(Ro * s[0]), "lo": _m6(Ro * s[1]), "hi": _m6(Ro * s[2]), "est": True,
                            "proj": True, "shape": how, "st": "ok", "in": None, "from": to}
            if cell is None:
                if r["to"] + timedelta(days=t) > S:
                    cell = {"v": None, "lo": None, "hi": None, "est": False, "proj": False, "shape": None,
                            "st": "wait", "in": (r["to"] + timedelta(days=t) - S).days}
                else:
                    cell = {"v": None, "lo": None, "hi": None, "est": False, "proj": False, "shape": None,
                            "st": "nodata", "in": None}
            r["rpi"][str(t)] = cell
        r["q"] = bool(qs)
        r365 = r["rpi"]["365"]
        sp = _spend_usd(spend, fx, r["from"], r["to"]) if r365["v"] is not None else None
        # ₹ per ₹100 only for a month that really ran ads — B's own floor (SPEND_MIN_WEEK a week): a trickle of spend
        # (or a campaign that began on the 28th) against a whole month's installs is no return on ads
        floor = V.SPEND_MIN_WEEK * r["days"] / 7.0
        r["b365"] = _g4(100 * r365["v"] * r["n"] / sp) if (sp and sp >= floor) else None
        r["b365_thin"] = bool(sp is not None and 0 < sp < floor)
        r["b365_proj"] = bool(r["b365"] is not None and r365["proj"])
        r["release"] = []
        for rel in releases or []:
            try:
                rd = V._d(rel.get("date"))
            except (TypeError, ValueError, AttributeError):
                continue
            if r["from"] <= rd <= r["to"]:
                r["release"].append({"date": _iso(rd), "version": rel.get("version"), "key": rel.get("key")})
    # the long_ret statistic, the base line, long_up
    conds, info, hits, ups = [], [], [], []
    for t in (60, 90):
        got = _long_d(P, rows, t, phi[t])
        if got is None:
            continue
        out["base"][str(t)] = got["base_out"]
        if got["down"]:
            hits.append(got)
        elif got["up"]:
            ups.append(got)
    got = _long_rpi(P, rows, 180)
    if got is not None:
        out["base"]["rpi180"] = got["base_out"]
        if got["down"]:
            hits.append(got)
    if hits:
        conds.append(_long_cond(P, hits, rows, spend, releases, grain, app))
    for u in ups:
        info.append({"kind": "long_up", "from": _iso(u["rec"][0]["from"]), "to": _iso(u["rec"][-1]["to"]),
                     "text": "%s ke installs back after %d days zyada: %s, pehle %s" % (
                         _span_months(u["rec"][0]["a"], u["rec"][-1]["a"], grain), u["t"], _p1(u["now"]),
                         _p1(u["before"]))})
    whole60 = [r for r in rows if not r["part"] and r["_c"][60] and r["n"] > 0]
    out["_seen"] = len(whole60) >= INPUT_LONG_ROWS
    out["_info"] = info
    # the sentence
    done = [r for r in rows if r["_c"][60] and r["n"] > 0]
    if not done:
        first = rows[0] if rows else None
        if first is not None:
            inn = max(1, (first["to"] + timedelta(days=60) - S).days)
            lab = first["label"] if grain == "month" else _qlabel(first["a"])
        else:
            nxt = _month_end(S) if grain == "month" else _quarter_end(S)
            inn = max(1, (nxt + timedelta(days=60) - S).days)
            lab = fmt_month(S) if grain == "month" else _qlabel(S)
        out.update(state="young", text="⏳ Abhi koi %s 60 din purana nahi — pehla number %s ke installs ka, %d din me."
                   % ("mahina" if grain == "month" else "quarter", lab, inn))
    else:
        out["text"] = _long_text(rows, grain)
    for r in rows:
        r["from"], r["to"] = _iso(r["from"]), _iso(r["to"])
        for k in ("_days", "_c", "a"):
            r.pop(k, None)
    out["rows"] = list(reversed(rows))                     # newest first
    return out, conds


def _pool_d(rows, t):
    j = str(t)
    x = sum(r["d"][j]["ret"] for r in rows)
    n = sum(r["n"] for r in rows)
    return x, n


def _pick(rows, t, ok):
    """The 2 newest complete whole rows at t (recent) and up to LONG_BASE complete whole rows before them (base)."""
    good = [r for r in rows if not r["part"] and r["n"] > 0 and ok(r)]
    if len(good) < 2 + LONG_BASE_MIN:
        return None, None
    return good[-2:], good[-2 - LONG_BASE:-2]


def _long_d(P, rows, t, phi_t):
    rec, base = _pick(rows, t, lambda r: r["_c"][t])
    if rec is None:
        return None
    x1, n1 = _pool_d(rec, t)
    x0, n0 = _pool_d(base, t)
    if not n1 or not n0:
        return None
    p1, p0 = x1 / n1, x0 / n0
    got = {"t": t, "metric": "d%d" % t, "rec": rec, "base": base, "now": 100 * p1, "before": 100 * p0, "down": False,
           "up": False, "n": n1, "base_out": {"v": _g4(100 * p0), "rows": len(base), "from": _iso(base[0]["from"]),
                                              "to": _iso(base[-1]["to"])}}
    sized = all(r["n"] >= LONG_JUDGE_N and r["d"][str(t)]["ret"] >= LONG_ALERT_RET for r in rec + base)
    if not sized or not 0 < p0 < 1:
        return got
    chi = sum((r["d"][str(t)]["ret"] - r["n"] * p0) ** 2 / (r["n"] * p0 * (1 - p0)) for r in base)
    phi_m = max(V.PHI_DEFAULT, chi / (len(base) - 1)) if len(base) > 1 else V.PHI_DEFAULT
    se = math.sqrt(phi_m * (p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0))
    z = (p1 - p0) / se if se > 0 else 0.0
    delta = 100 * (p1 - p0)
    rel = p1 / p0 - 1
    thr = LONG_MINPP[t]
    each = [100 * r["d"][str(t)]["ret"] / r["n"] - 100 * p0 for r in rec]
    got.update(z=z, delta=delta, rel=rel, phi_m=phi_m)
    got["down"] = delta <= -thr and rel <= -LONG_MINREL and all(e <= -thr / 2 for e in each) and z <= -LONG_Z
    got["up"] = delta >= thr and rel >= LONG_MINREL and all(e >= thr / 2 for e in each) and z >= LONG_Z
    return got


def _long_rpi(P, rows, t):
    rec, base = _pick(rows, t, lambda r: r["_c"][t])
    if rec is None:
        return None
    xs = P["xs"]
    j = V.T.index(t)

    def y(r):
        return sum(xs[X]["R"][j] for X in r["_days"])
    y1, n1 = sum(y(r) for r in rec), sum(r["n"] for r in rec)
    y0, n0 = sum(y(r) for r in base), sum(r["n"] for r in base)
    if not n1 or not n0 or y0 <= 0:
        return None
    R1, R0 = y1 / n1, y0 / n0
    got = {"t": t, "metric": "rpi%d" % t, "rec": rec, "base": base, "now": R1, "before": R0, "down": False,
           "n": n1, "base_out": {"v": _m6(R0), "rows": len(base), "from": _iso(base[0]["from"]),
                                 "to": _iso(base[-1]["to"])}}
    if not all(r["n"] >= LONG_JUDGE_N for r in rec + base) or len(base) < 2:
        return got
    nbar = n0 / len(base)
    s2 = sum(((y(r) - R0 * r["n"]) / nbar) ** 2 for r in base) / (len(base) - 1)
    s = math.sqrt(s2)
    se = math.sqrt(s * s / 2 + s * s / len(base))
    z = (R1 - R0) / se if se > 0 else 0.0
    rel = R1 / R0 - 1
    each = [y(r) / r["n"] / R0 - 1 for r in rec]
    got.update(z=z, rel=rel, delta=None)
    got["down"] = rel <= -LONG_RPI_REL and z <= -LONG_Z and all(e <= -LONG_RPI_REL / 2 for e in each)
    return got


def _long_cond(P, hits, rows, spend, releases, grain, app):
    hits = sorted(hits, key=lambda h: (-abs(h["z"]), h["metric"]))
    h = hits[0]
    rec, base = h["rec"], h["base"]
    a, b = rec[0]["from"], rec[-1]["to"]
    tags, cause, mix = [], None, None
    rd = [X for r in rec for X in r["_days"]]
    bd = [X for r in base for X in r["_days"]]
    n1, n0 = sum(r["n"] for r in rec), sum(r["n"] for r in base)
    p1, p0 = _paid(spend, rd, n1), _paid(spend, bd, n0)
    if p1 is not None and p0 is not None and abs(p1 - p0) * 100 >= VER_MIX_PTS:
        mix = {"p0": _g4(p0), "p1": _g4(p1)}
        cause = "shayad installs ka mix badla (ads wale %d%% → %d%%)" % (round(100 * p0), round(100 * p1))
    m1, m0 = n1 / len(rec), n0 / len(base)
    if mix is None and m0 and (m1 / m0 >= VER_MIX_INST or m1 / m0 <= 1 / VER_MIX_INST):
        mix = {"i0": _g4(m0), "i1": _g4(m1)}
        cause = "shayad installs ka mix badla (%s ke installs %s → %s)" % (
            "mahine" if grain == "month" else "quarter", _n(m0), _n(m1))
    if mix is not None:
        tags.append("mix")
    rel = None
    for x in releases or []:
        try:
            d = V._d(x.get("date"))
        except (TypeError, ValueError, AttributeError):
            continue
        if a <= d <= b:
            rel = {"date": _iso(d), "version": x.get("version"), "kind": x.get("kind"), "key": x.get("key")}
    if rel:
        tags.append("update")
    kbad = False
    if h["metric"].startswith("rpi"):                  # an earning move on a doubtful AdMob scale: shown, never sent
        kbad = V.k_est(P["sc"], a, min(P["S"], b + timedelta(days=h["t"])))
    return {"key": "%s|long_ret|down" % app["id"], "family": "long_ret", "metric": h["metric"], "dir": "down",
            "cc": None, "severity": "watch",
            "now": _g4(h["now"]) if not h["metric"].startswith("rpi") else _m6(h["now"]),
            "before": _g4(h["before"]) if not h["metric"].startswith("rpi") else _m6(h["before"]),
            "rel": _g4(h.get("rel")), "delta_pp": _g4(h.get("delta")), "z": _g4(h.get("z")),
            "also": [x["metric"] for x in hits[1:]], "week_from": _iso(a), "week_to": _iso(b),
            "base_from": _iso(base[0]["from"]), "base_to": _iso(base[-1]["to"]), "users": int(n1), "spend": None,
            "tags": tags, "release": rel, "months": [r["key"] for r in rec], "grain": grain, "base_rows": len(base),
            "span": _span_months(rec[0]["a"], rec[-1]["a"], grain), "cause": cause, "mix": mix,
            "_force_seed": bool(kbad), "_est": bool(kbad)}


def long_alert_text(s):
    """A long_ret episode's snapshot → its Hinglish sentence (money as tokens)."""
    span = s.get("span") or "Pichhle mahino"
    unit = "mahine" if s.get("grain", "month") == "month" else "quarter"
    if str(s.get("metric") or "").startswith("rpi"):
        rel = s.get("rel")
        return "%s ke installs ki 6 mahine ki earning per install kam: %s, pehle %s%s" % (
            span, V.t_m(s.get("now")), V.t_m(s.get("before")),
            (" (%s%s)" % ("+" if rel > 0 else "", V._pct(rel))) if rel is not None else "")
    t = str(s.get("metric") or "d60")[1:]
    txt = "%s ke installs back after %s days kam: %s, pehle %s (pichhle %s %s ka normal)" % (
        span, t, _p1(s.get("now")), _p1(s.get("before")), s.get("base_rows") or LONG_BASE, unit)
    if s.get("cause"):
        txt += " — " + s["cause"]
    return txt


def _long_text(rows, grain):
    """"{Mon YYYY} ke installs: back after 90 days {d90}% (pichhle 6 mahine, …: ~{base}%) · 1 saal me earning per
    install {≈}{rpi365}{ (andaza)}" — the newest row complete at 90 (else at 60)."""
    for t in (90, 60):
        done = [r for r in rows if r["_c"][t] and r["n"] > 0 and r["d"][str(t)]["v"] is not None]
        if done:
            break
    r = done[-1]
    i = rows.index(r)
    base = [b for b in rows[:i] if not b["part"] and b["_c"][t] and b["n"] > 0][-LONG_BASE:]
    lab = r["label"] if grain == "month" else _qlabel(r["a"])
    txt = "%s ke installs: back after %d days %s" % (lab, t, _p1(r["d"][str(t)]["v"]))
    if base:                                           # the months it is compared with, named (never another span's)
        x, n = _pool_d(base, t)
        if n:
            txt += " (pichhle %d %s, %s: ~%s)" % (len(base), "mahine" if grain == "month" else "quarter",
                                                  _span_months(base[0]["a"], base[-1]["a"], grain), _p1(100 * x / n))
    c = r["rpi"]["365"]
    if c["v"] is not None:
        txt += " · 1 saal me earning per install %s%s%s" % ("≈" if (c["est"] or c["proj"]) else "", V.t_m(c["v"]),
                                                          " (andaza)" if c["proj"] else "")
    return txt
