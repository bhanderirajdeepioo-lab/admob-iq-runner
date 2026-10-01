"""Compare any date — the "📦 Update impact" card for a date the owner picks ("15 Sep ko ad placement badla", "20 Sep se
notification shuru"), precomputed by the build for every app and every candidate date: the page only looks it up.

A chosen date X is evaluated as a PSEUDO-RELEASE by the engine's own code — nothing is re-derived here:
  * the block: kind "custom", label "Custom date", R = X, no version → no adoption, no version table (engine.impact
    treats any kind but "version" so: the After window starts the day after X, a0 = X + 1);
  * the 7-day window and rows: impact.block_rows (the very function impact_app runs for each update), then persist
    (stateless: the engine's FIRST evaluation — a worse / better row is shown as judged, no 2-day wait; nothing is
    sent), verdict, the notes and the installs vs per-user split (_split_rows) of impact_app;
  * the 14 / 30 / 60-day windows: impact._long_window, as for an update (running / judged / final, D30 at 30 / 60);
  * the app's REAL updates stay in the block list around X, so an update inside the windows is reported exactly as
    the engine reports one for a release: the 7-day After is cut by the next update (cut_by_next), one in the 7 days
    before is before_overlap, and at 14 / 30 / 60 the ones inside are "mixed" / "mixed_before" ("beech me v2.3
    update aaya"). An update released ON X is that date's own card (it is listed under "u": same day) and leaves the
    list (two blocks on one day would cut the window to nothing).
No alert, episode or notification ever comes from a custom date: the late-effect candidate and the "told" rows of a
long window are dropped, and no state is read or written.

CANDIDATE DATES: every day X from max(E − HISTORY_DAYS, launch + 7, first GA4 day + 7) to E − 1 (E = the app's data
till): the 7-day Before needs a launched week, the After at least one day. A window not complete yet is still there,
with the engine's own early / pending / ready_on / running status — never a guess.

SPEED (exact): a date's returning-DAU memos (_fast_dau) read the app's days as dense lists by ordinal — the same
expressions in the same order, so the same floats; a fully observed day's old-users level is shared across dates (it
reads no return rate); the pseudo-update loop runs over list slices (operator / map, no per-day date arithmetic) and
skips work whose only effect would be a memo entry no output reads. tests/test_impact_any.py checks every row of every
window of every date is byte-identical to the engine's own memos (impact._dau_memo / _dau_nulls).

OUTPUT: build_app → the per-app lazy file, read back by decode (CONTRACT at the bottom); the build step, its cache
and time budget: admob_iq.impact_any_build."""

import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from math import exp, log
from operator import add, itemgetter, mul, truediv

from . import attrib
from . import impact as I
from . import uninstall as U

V = 1                     # file format (a reader checks it)
HISTORY_DAYS = 365        # candidate dates: the last year (or the app's history when shorter)
KIND, LABEL = "custom", "Custom date"
WINDOWS = I.WINDOWS       # 7 / 14 / 30 / 60 — the update card's
ROWS7 = I.ROWS            # the 7 / 14-day rows; the 30 / 60-day windows add new_d30 (I.ROWS_LONG)
LEVELS = (None, "continue", "win", "hold", "halt")
STATES = I.STATES         # running / judged / final (14 / 30 / 60)
BASIS = I.BASIS           # expected / plain / rate


def _d(s):
    return U._d(s)


# ── the inputs impact_app gets from uninstall.evaluate_app (the same engine calls, a test checks they match) ────────

def prepare(store, late):
    """One app's store (as run_uninstall passes it to evaluate_app) → the arguments evaluate_app hands impact_app:
    (store, ds, cd, whole, i0, rels, E, late)."""
    store = U.fill_days(store)
    E = _d(store["window_end"])
    late = max(0, int(late or 0))
    whole = U.cohort_data(store, E)
    L = U.launch_day(whole["n"])
    i0 = L if sum(whole["n"][:L]) else 0
    ds = U.daily_series(store, E, whole, late, i0)
    U.mark_breaks(whole, ds["broken"])
    cd = U.mark_breaks(U.cut_cohorts(whole, i0), ds["broken"][i0:]) if i0 else whole
    rels = U.releases(store, ds)
    return store, ds, cd, whole, i0, rels, E, late


def date_range(cx, E):
    """(first, last) candidate date, or None when the app has none yet."""
    first_daily = (cx.get("first") or {}).get("daily")
    lo = [E - timedelta(days=HISTORY_DAYS), cx["launch"] + timedelta(days=7)]
    if first_daily is not None:
        lo.append(first_daily + timedelta(days=7))
    first, last = max(lo), E - timedelta(days=1)
    return (first, last) if first <= last else None


# ── exact returning-DAU memos over day ordinals (impact._dau_memo / _dau_nulls, the same floats) ────────────────────

class _AppDays:
    """The app's per-day numbers the returning-DAU memos read, keyed by day ordinal (built once per app): rd =
    _ret_dau, new = _dv(new) or 0, coh = a cohort's day-k actives when it is "ok" (impact reads it only then), the
    old-users level of a FULLY observed day by (day, K) — it reads no return rate, so every date shares it — and the
    same rd / new as dense lists from `base` (PAD days before the first day; a day outside = missing / 0)."""

    PAD = 800                                         # > the 60-day pseudo-updates' reach back (~640 days) + K

    def __init__(self, cx):
        self.rd, self.new, self.coh, self.ycache = {}, {}, {}, {}
        for k, r in cx["daily"].items():
            if r is None:
                continue
            o = _d(k).toordinal()
            a, n = int(r.get("a1") or 0), int(r.get("new") or 0)
            self.rd[o], self.new[o] = a - n, n
        for k, e in cx["ret"].items():
            if e and e.get("ok"):
                self.coh[_d(k).toordinal()] = e.get("a") or []
        lo = min(list(self.rd) + list(self.coh) + [cx["E"].toordinal()])
        self.base = lo - self.PAD
        top = cx["E"].toordinal() + 2
        self.RDL = [self.rd.get(o) for o in range(self.base, top + 1)]
        self.NEWL = [self.new.get(o, 0) for o in range(self.base, top + 1)]


def _fast_dau(cx, blk, days):
    """impact._dau_memo's dict for block blk, over ordinals (memo / touched keyed by ordinal: dau_row only reads
    memo[d] for d in touched), + "nulls": impact._dau_nulls over dense per-day lists. Same memo keys, same calls in the
    same order, same expressions (int × float, the same sum()) → the same floats, imputed_share included."""
    rho, Kx = I._rho(cx, blk["R"])
    raw = Kx < 7
    K = 0 if raw else Kx
    RD, NEW, COH, YC = days.rd, days.new, days.coh, days.ycache
    RDL, NEWL, base = days.RDL, days.NEWL, days.base
    nL = len(RDL)
    memo, rmemo, omemo, wmemo, mumemo, btmemo, touched = {}, {}, {}, {}, {}, {}, {}
    H = I.TREND_HORIZON_WEEKS
    _log = I._log
    rhov = [rho[k] for k in range(1, K + 1)]
    OML, RCL = [None] * nL, [None] * nL               # Om / recent by index (filled on demand: ensure)
    filled = [None, None]

    def Yo(o):
        v = memo.get(o)
        if v is None:
            c = YC.get((o, K))
            if c is not None:
                v = (c, 0.0)
            else:
                y = yi = 0.0
                full = True
                for k in range(1, K + 1):
                    a = COH.get(o - k)
                    if a is not None and len(a) > k:
                        y += a[k]
                    else:                             # ρ̂ is per GA4 new user: no cohort scale
                        x = NEW.get(o - k, 0) * rho[k]
                        y, yi = y + x, yi + x
                        full = False
                if full:
                    YC[(o, K)] = y
                v = (y, yi)
            memo[o] = v
        return v[0]

    def Om_fill(o):
        r = RD.get(o)
        omemo[o] = v = None if r is None else r - Yo(o)
        return v

    def Omo(o):
        if o not in omemo:
            Om_fill(o)
        if o in memo and o not in touched:
            touched[o] = True
        return omemo[o]

    def reco(o):
        if o not in rmemo:
            rmemo[o] = sum(NEW.get(o - k, 0) * rho[k] for k in range(1, K + 1))
        return rmemo[o]

    def wowo(u):
        if u not in wmemo:
            wmemo[u] = _log(Omo(u), Omo(u - 7))
        return wmemo[u]

    def mu_refo(e):
        if e not in mumemo:
            v = [wowo(u) for u in range(e - 20, e + 1)]
            v = [x for x in v if x is not None]
            mumemo[e] = U.median(v) if v else 0.0
        return mumemo[e]

    def expdo(d, b, w, mu):
        o = Omo(b)
        return None if o is None or o <= 0 else o * math.exp(mu * min(w, H)) + reco(d)

    def backtesto(e):
        if e not in btmemo:
            mu, bt = mu_refo(e), []
            for t in range(e - 13, e + 1):
                x = _log(RD.get(t), expdo(t, t - 7, 1, mu))
                if x is not None:
                    bt.append(x)
            btmemo[e] = bt
        return btmemo[e]

    def ensure(lo, hi):
        """OML / RCL filled for the days lo..hi (ordinals): Om = rd − Y only where rd exists (Y is never read for a
        day without rd — Om's own rule, so memo keeps the engine's days), recent = Σ new(t−k) · ρ̂_k, k = 1..K, in
        that order (the same sum())."""
        a, b = lo - base, hi - base
        if filled[0] is not None:
            f0, f1 = filled
            if a >= f0 and b <= f1:
                return
            a, b = min(a, f0), max(b, f1)                # (one span: a gap between the two is filled too)
            rng = [i for i in range(a, b + 1) if not f0 <= i <= f1]
            filled[0], filled[1] = a, b
        else:
            rng = range(a, b + 1)
            filled[0], filled[1] = a, b
        for i in rng:
            o = i + base
            if o in omemo:
                OML[i] = omemo[o]
            else:
                r = RDL[i]
                OML[i] = omemo[o] = None if r is None else r - Yo(o)
            if o in rmemo:
                RCL[i] = rmemo[o]
            else:
                RCL[i] = rmemo[o] = sum(map(mul, NEWL[i - K:i][::-1], rhov)) if K else 0

    def bt_fast(e, mu):
        """backtest(e) from the dense lists — the same values (memoized under the same key)."""
        if e not in btmemo:
            f = math.exp(mu * 1)
            bt = []
            i0 = e - base
            for i in range(i0 - 13, i0 + 1):
                o, r = OML[i - 7], RDL[i]
                if o is None or o <= 0:
                    continue
                ee = o * f + RCL[i]
                if r and ee and r > 0 and ee > 0:
                    bt.append(log(r / ee))
            btmemo[e] = bt
        return btmemo[e]

    def nulls(cx_, dm_, R, N, used, pat):
        # impact._dau_nulls: per shift the same mu_ref / backtest calls (their memos decide which old-users days a
        # later row reads: imputed_share), then x for every After day — all valid or the shift is left out
        Ro, lag = R.toordinal(), N + 1
        shifts = I._shifts(R, used, N)
        Do = [d.toordinal() for d, _, _ in pat]
        Bo = [b.toordinal() for _, b, _ in pat]
        Ws = [min(w, H) for _, _, w in pat]
        dmin, dmax, bmin, bmax = min(Do), max(Do), min(Bo), max(Bo)
        lo = min(dmin, bmin, Ro - lag - 20 - 7) - shifts[-1]
        hi = max(dmax, bmax) - shifts[0]
        if lo - base < K + 1 or hi - base >= nL:      # (outside the dense lists: never on live data)
            return slow(cx_, dm_, R, N, used, pat)
        ensure(lo, hi)
        n = len(pat)

        def getter(idx):
            g = itemgetter(*idx)
            return g if len(idx) > 1 else (lambda seq: (g(seq),))
        gD, gB, gW = getter([d - dmin for d in Do]), getter([b - bmin for b in Bo]), getter(Ws)
        out, steep_n = [], 0
        for dl in shifts:
            e = Ro - dl - lag
            mq = mu_refo(e)
            bq = bt_fast(e, mq)
            if len(bq) < 10:
                continue
            i0 = dmin - dl - base
            j0 = bmin - dl - base
            o_s = gB(OML[j0:j0 + bmax - bmin + 1])
            if None in o_s or min(o_s) <= 0:
                continue
            r_s = gD(RDL[i0:i0 + dmax - dmin + 1])
            if None in r_s or min(r_s) <= 0:
                continue
            ee = list(map(add, map(mul, o_s, gW([exp(mq * w) for w in range(H + 1)])),
                          gD(RCL[i0:i0 + dmax - dmin + 1])))
            if min(ee) <= 0:
                continue
            if I._steep(mq):                          # the test would not run there (TREND_MAX_WEEK)
                steep_n += 1
                continue
            out.append(I._mean(list(map(log, map(truediv, r_s, ee)))) - U.median(bq))
        I._count(cx, ("dau", N), 2 * n * len(shifts))
        return out, steep_n

    def slow(cx_, dm_, R, N, used, pat):
        Ro, lag = R.toordinal(), N + 1
        P2 = [(d.toordinal(), b.toordinal(), min(w, H)) for d, b, w in pat]
        out, steep_n, cnt = [], 0, 0
        for dl in I._shifts(R, used, N):
            e = Ro - dl - lag
            mq = mu_refo(e)
            bq = backtesto(e)
            cnt += 2 * len(pat)
            if len(bq) < 10:
                continue
            xq = []
            for do, bo, w in P2:
                t, bb = do - dl, bo - dl
                o = omemo[bb] if bb in omemo else Om_fill(bb)
                if o is None or o <= 0:
                    break
                ee = o * exp(mq * w) + (rmemo[t] if t in rmemo else reco(t))
                r = RD.get(t)
                if not (r and ee and r > 0 and ee > 0):
                    break
                xq.append(log(r / ee))
            if len(xq) < len(P2):
                continue
            if I._steep(mq):
                steep_n += 1
                continue
            out.append(I._mean(xq) - U.median(bq))
        I._count(cx, ("dau", N), cnt)
        return out, steep_n

    def o_(f):
        return lambda d: f(d.toordinal())
    return {"rho": rho, "Kx": Kx, "K": K, "raw": raw, "memo": memo, "touched": touched, "Om": o_(Omo), "Y": o_(Yo),
            "recent": o_(reco), "mu_ref": o_(mu_refo),
            "expd": lambda d, b, w, mu: expdo(d.toordinal(), b.toordinal(), w, mu),
            "backtest": o_(backtesto), "nulls": nulls}


# ── one date ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _pseudo(X):
    return {"rels": [], "R": X, "_last": X, "versions": [], "kind": KIND, "label": LABEL,
            "key": "custom@%s" % X.isoformat(), "rel_keys": []}


def evaluate_date(cx, blocks, X, app_id, E, days=None):
    """Date X as a pseudo-release among the app's real update blocks → {"same": [real blocks released on X],
    "7": the 7-day card (windows, rows, verdict, notes — as impact_app's block), "14" / "30" / "60": as by_window[N]
    (late / told / told_by dropped: never alerted), "failed": windows that raised (counted, left out)}.
    days: _AppDays (the exact fast returning-DAU memos) or None (the engine's own)."""
    same = [b for b in blocks if b["R"] == X]
    lst = [b for b in blocks if b["R"] < X]
    j = len(lst)
    blk = _pseudo(X)
    lst = lst + [blk] + [b for b in blocks if b["R"] > X]
    if days is not None:
        blk["_m"] = {"dau": _fast_dau(cx, blk, days)}
    rows, vc = I.block_rows(cx, blk, lst, j, [])
    vrows, win = vc["rows"], blk["win"]
    final_pre = (bool(win["days_a"]) and len(win["settled"]) == len(win["days_a"])
                 and rows["new_d7"]["status"] != "pending")
    I.persist(dict(rows, **vrows), {}, True, final_pre, True)     # stateless: the engine's first evaluation
    vd = I.verdict(blk, rows, vrows, cx)
    notes = I._notes(cx, blk, rows, vrows)
    blk["_vd7"] = vd
    I._split_rows(cx, rows, I.WIN_DAYS)
    out = {"same": [{"key": b["key"], "label": b["label"], "date": b["R"].isoformat()} for b in same],
           "7": {"windows": I._win_out(blk), "rows": {k: I._round_row(rows[k]) for k in I.ROWS}, "verdict": vd,
                 "notes": notes}, "failed": 0}
    for N in WINDOWS[1:]:
        try:
            W, _ = I._long_window(cx, blk, lst, j, N, {}, app_id, E)
        except Exception:
            out["failed"] += 1
            continue
        for k in ("late", "told", "told_by"):
            W["verdict"].pop(k, None)
        out[str(N)] = W
    return out


def setup(store, revenue, late, fast=True):
    """One app → its context {cx, E, blocks (the real updates), rng (first, last) or None, days}: impact_app's own cx
    (_context, the windows' noise on every row as IMPACT_WINDOWS on). store = what run_uninstall hands evaluate_app;
    revenue = the app's AdMob revenue (None: no ARPDAU row); fast False: the engine's own returning-DAU memos (the
    parity tests' reference)."""
    store, ds, cd, whole, i0, rels, E, late = prepare(store, late)
    cx = I._context(store, cd, whole, i0, revenue, E, late)
    cx["_noise_all"] = True
    return {"cx": cx, "E": E, "blocks": I.make_blocks(rels, cx["launch"]), "rng": date_range(cx, E),
            "days": _AppDays(cx) if fast else None, "failed": 0}


def each_date(ctx, app_id, dates=None):
    """→ (X, evaluate_date) for every candidate date (or only `dates`), oldest first; a date that raised is left out
    and counted in ctx["failed"] (with the windows that raised)."""
    if ctx["rng"] is None:
        return
    X = ctx["rng"][0]
    while X <= ctx["rng"][1]:
        if dates is None or X in dates:
            try:
                r = evaluate_date(ctx["cx"], ctx["blocks"], X, app_id, ctx["E"], ctx["days"])
            except Exception:
                ctx["failed"] += 1
            else:
                ctx["failed"] += r.pop("failed")
                yield X, r
        X += timedelta(days=1)


# ── wording: the card's texts say "update"; a custom date is not one ──────────────────────────────────────────────

CUSTOM_TEXT = (
    (": rollout chalne do", ""), (" — rollout chalne do", ""),
    ("Update se pehle", "Is date se pehle"), (" is update se pehle", " is date se pehle"),
    ("Update se ~", "Is date se ~"),
    ("App launch ke turant baad ka update", "App launch ke turant baad ki date"),
    ("bazaar ka asar, update ka nahi", "bazaar ka asar, is badlaav ka nahi"),
    ("revenue per user ka farak update ka hai ya bazaar ka", "revenue per user ka farak is badlaav ka hai ya bazaar ka"),
    ("market ka asar, update ka nahi", "market ka asar, is badlaav ka nahi"),           # (texts built before the
    ("kamai ka farak update ka hai ya market ka", "kamai ka farak is badlaav ka hai ya market ka"),   # wording change)
    (" aur update)", " update)"), (" aur updates)", " updates)"),
)


def custom_text(s):
    """An engine text as a custom date's card says it ("Update se pehle …" → "Is date se pehle …", no "rollout chalne
    do"). Plain phrase swaps — the numbers in it are the engine's."""
    if not s:
        return s
    for a, b in CUSTOM_TEXT:
        s = s.replace(a, b)
    if "Update app launch ke " in s:                  # NA_YOUNG_N ("… ke %d din ke andar aaya …")
        s = s.replace("Update app launch ke ", "Ye date app launch ke ")
        s = s.replace(" din ke andar aaya", " din ke andar hai")
    return s


# ── the compact per-app file (CONTRACT at the bottom) ─────────────────────────────────────────────────────────────

# per row: the numbers the card SHOWS (short key, engine key[, decimals]) — tooltip-only ones (noise, z, all users'
# sessions / time, mu_week, swing) stay out (size)
VAL = (("b", "before"), ("a", "after"), ("x", "expected"), ("p", "after_prov"))       # in the row's unit (VAL_DP)
CHG = (("c", "change"), ("q", "need"))                                                # in its change unit (CHG_DP)
EXTRA = {"returning_dau": (("rc", "raw_change", 3), ("is", "imputed_share", 3)),
         "new_d1": (("ib", "installs_before", 0), ("ia", "installs_after", 0), ("cb", "cohorts_before", 0),
                    ("ca", "cohorts_after", 0)),
         "sessions": (("ac", "adj_change", 3),),
         "arpdau": (("ij", "imp_adj", 3), ("ic", "imp_change", 3), ("ec", "ecpm_change", 3), ("it", "imp_after", 3),
                    ("ie", "imp_expected", 3), ("nb", "newshare_before", 3), ("na", "newshare_after", 3)),
         "uninstall_d0": ()}
EXTRA["new_d7"] = EXTRA["new_d30"] = EXTRA["new_d1"]
EXTRA["time"] = EXTRA["sessions"]
# the decimals by unit = the engine's own (impact.DP), so a chosen date's card shows exactly the numbers an update card
# shows for the same date (one decimal less made ~3% of cells differ in the last digit); changes: rel 4 dp, points 2 dp
VAL_DP = dict(I.DP)
CHG_DP = {"rel": 4, "pp": 2}


def _num(v, dp):
    if v is None:
        return None
    v = round(float(v), dp) + 0.0
    return int(v) if dp == 0 or v == int(v) else v


def _cu(key):
    return "pp" if I.UNIT[key] == "pct" else "rel"


def _default_basis(key, N):
    """The basis a row has unless it says otherwise: D1 / D7 / D30 / install day "rate"; returning DAU "expected";
    sessions / time / ad revenue "expected" at 7 days, "plain" at 14 / 30 / 60."""
    u = I.UNIT[key]
    if u == "pct":
        return "rate"
    if u == "users" or N == I.WIN_DAYS:
        return "expected"
    return "plain"


def _keys(N):
    return I.ROWS_LONG if N >= I.LATE_WINDOW else ROWS7


class _Packer:
    """The file's shared tables: texts (reasons, verdict lines — custom wording applied) and the app's real updates
    (ordered by date; mixed / overlap / cut-by / same-day refer to them by index)."""

    def __init__(self, blocks=()):
        self.text, self._ti = [], {}
        self.upd, self._ui = [], {}
        for b in blocks:
            self.u({"key": b["key"], "label": b["label"], "date": b["R"].isoformat()})

    def t(self, s):
        if s is None or s == "":
            return None
        s = custom_text(s)
        if s not in self._ti:
            self._ti[s] = len(self.text)
            self.text.append(s)
        return self._ti[s]

    def u(self, ref):
        k = (ref.get("date"), ref.get("label"))
        if k not in self._ui:
            self._ui[k] = len(self.upd)
            self.upd.append({"key": ref.get("key"), "label": ref.get("label"), "date": ref.get("date")})
        return self._ui[k]


def _off(X, iso):
    return None if iso is None else (_d(iso) - X).days


def _row(pk, X, key, r, N, wspan):
    """One engine row (rounded; sparse at 14 / 30 / 60) → its cells {short key: value} (None left out)."""
    out = {"s": I.STATUSES.index(r.get("status") or "na")}
    unit, cu = I.UNIT[key], _cu(key)
    for short, k in VAL:
        out[short] = _num(r.get(k), VAL_DP[unit])
    for short, k in CHG:
        out[short] = _num(r.get(k), CHG_DP[cu])
    out["r"] = pk.t(r.get("reason"))
    out["ro"] = _off(X, r.get("ready_on"))
    bs = r.get("basis") or I.BASIS_LONG.get(unit)
    out["bs"] = BASIS.index(bs) if bs != _default_basis(key, N) else None
    out["e"] = 1 if r.get("est") else None
    out["pv"] = 1 if r.get("prov") else None
    out["nb"], out["na"] = r.get("n_before") or None, r.get("n_after") or None
    for short, k, w in (("fb", "from_b", wspan[0]), ("tb", "to_b", wspan[1]), ("fa", "from_a", wspan[2]),
                        ("ta", "to_a", wspan[3])):
        o = _off(X, r.get(k))
        out[short] = o if o is not None and o != w else None
    out["sp"] = r.get("sp")
    ex = r.get("extra") or {}
    for short, k, dp in EXTRA[key]:
        v = _num(ex.get(k), dp)
        out["x" + short] = None if v is None or (k == "imputed_share" and v == 0) else v
    if key == "returning_dau" and ex.get("mode") == "raw":
        out["xraw"] = 1
    return {k: v for k, v in out.items() if v is not None}


def _window(pk, X, N, W):
    """One window (the 7-day card, or by_window[N]) → (its cells, its rows' cells)."""
    seven = N == I.WIN_DAYS
    aw = W["windows"]["after"] if seven else W["after"]
    vd = W["verdict"]
    ae = _off(X, aw["to"])
    out = {"lv": LEVELS.index(vd.get("level")), "ns": aw["settled"], "ae": ae if ae != N else None,
           "st": None if seven else STATES.index(W["state"]), "f": 1 if vd.get("final") else None,
           "w": pk.t(vd.get("why")), "ro": _off(X, vd.get("ready_on")),
           "nt": sum(1 << I.NOTES_LONG.index(n) for n in W["notes"] if n in I.NOTES_LONG) or None}
    if seven:
        ov, cb = W["windows"].get("overlap_before"), aw.get("cut_by")
        out["ov"], out["cb"] = (pk.u(ov) if ov else None), (pk.u(cb) if cb else None)
    else:
        out["mx"] = [pk.u(x) for x in W.get("mixed") or []] or None
        out["mb"] = [pk.u(x) for x in W.get("mixed_before") or []] or None
    wspan = (-N, -1, 1, ae)
    return ({k: v for k, v in out.items() if v is not None},
            [_row(pk, X, k, W["rows"][k], N, wspan) for k in _keys(N)])


class _Columns:
    """Every date's cells → one array per field over the date axis (day i = first + i): the per-app file's "w"."""

    def __init__(self, n):
        self.n, self.u = n, [None] * n
        self.w = {str(N): {"c": {}, "r": [{} for _ in _keys(N)]} for N in WINDOWS}

    def _put(self, cols, f, i, v):
        if f not in cols:
            cols[f] = [None] * self.n
        cols[f][i] = v

    def add(self, pk, i, X, r):
        for N in WINDOWS:
            W = r.get(str(N))
            if W is None:
                continue
            cells, rows = _window(pk, X, N, W)
            slot = self.w[str(N)]
            for f, v in cells.items():
                self._put(slot["c"], f, i, v)
            for j, rc in enumerate(rows):
                for f, v in rc.items():
                    self._put(slot["r"][j], f, i, v)
        if r.get("same"):
            self.u[i] = [pk.u(b) for b in r["same"]]

    def out(self):
        return {N: dict(slot["c"], r=slot["r"]) for N, slot in self.w.items()}


def body(app_id, key, sig, cx, E, rng, pk, cols):
    """The per-app file (CONTRACT)."""
    n = (rng[1] - rng[0]).days + 1 if rng else 0
    return {"v": V, "app_id": app_id, "key": key, "sig": sig, "data_till": E.isoformat(),
            "settled_till": cx["S_act"].isoformat(), "un_settled_till": cx["S_un"].isoformat(),
            "first": rng[0].isoformat() if rng else None, "last": rng[1].isoformat() if rng else None, "n": n,
            "currency": cx["currency"], "windows": list(WINDOWS), "rows": list(I.ROWS_LONG),
            "status": list(I.STATUSES), "levels": list(LEVELS), "states": list(STATES), "notes": list(I.NOTES_LONG),
            "basis": list(BASIS), "text": pk.text, "updates": pk.upd, "u": cols.u, "w": cols.out()}


def build_app(store, revenue, app_id, key, sig, late):
    """One app → (its file body, failed windows / dates): every candidate date evaluated and packed at once (one
    date's full rows in memory at a time)."""
    ctx = setup(store, revenue, late)
    rng = ctx["rng"]
    pk = _Packer(ctx["blocks"])
    cols = _Columns((rng[1] - rng[0]).days + 1 if rng else 0)
    for X, r in each_date(ctx, app_id):
        cols.add(pk, (X - rng[0]).days, X, r)
    return body(app_id, key, sig, ctx["cx"], ctx["E"], rng, pk, cols), ctx["failed"]


# ── reading it back (the page's decoder, in Python: the tests' and the contract's reference) ────────────────────────

def decode(body, X):
    """The per-app file's entry for date X → {"date", "same": [update], "7" / "14" / "30" / "60": window} with the
    engine's own field names (a window like impact's by_window[N] / the 7-day card: n, state, before, after, verdict,
    notes, mixed, mixed_before, overlap_before, cut_by, rows {key: row}) — None outside the file's dates. A window
    that failed for that date is left out."""
    if not body.get("n"):
        return None
    X = _d(X)
    i = (X - _d(body["first"])).days
    if not 0 <= i < body["n"]:
        return None
    T, UP = body["text"], body["updates"]

    def day(o):
        return None if o is None else (X + timedelta(days=o)).isoformat()

    out = {"date": X.isoformat(), "same": [UP[k] for k in body["u"][i] or []]}
    for N in body["windows"]:
        slot = body["w"][str(N)]

        def g(f, cols=slot):
            c = cols.get(f)
            return None if c is None else c[i]
        lv = g("lv")
        if lv is None:
            continue
        ns, ae = g("ns") or 0, g("ae")
        ae = N if ae is None else ae                  # (0: a 7-day After cut to nothing by the next day's update)
        keys = _keys(N)
        rows = {}
        for j, k in enumerate(keys):
            rc = slot["r"][j]

            def h(f, cols=rc):
                c = cols.get(f)
                return None if c is None else c[i]
            st = body["status"][h("s") if h("s") is not None else body["status"].index("na")]
            bs = h("bs")
            ex = {ek: h("x" + short) for short, ek, _ in EXTRA[k]}
            if k == "returning_dau":
                ex["mode"] = "raw" if h("xraw") else "cohort"
                if ex["imputed_share"] is None:
                    ex["imputed_share"] = 0.0
            rows[k] = {"status": st, "raw_status": st, "unit": I.UNIT[k], "change_unit": _cu(k),
                       "before": h("b"), "after": h("a"), "expected": h("x"), "after_prov": h("p"),
                       "change": h("c"), "need": h("q"), "z": None, "noise": None,
                       "reason": None if h("r") is None else T[h("r")], "ready_on": day(h("ro")),
                       "basis": body["basis"][bs] if bs is not None else _default_basis(k, N),
                       "est": bool(h("e")), "prov": bool(h("pv")), "n_before": h("nb") or 0, "n_after": h("na") or 0,
                       "from_b": day(h("fb") if h("fb") is not None else -N),
                       "to_b": day(h("tb") if h("tb") is not None else -1),
                       "from_a": day(h("fa") if h("fa") is not None else 1),
                       "to_a": day(h("ta") if h("ta") is not None else ae), "sp": h("sp"), "extra": ex}
        final = bool(g("f"))
        allk = list(keys)
        vd = {"level": body["levels"][lv], "early": not final, "final": final,
              "why": "" if g("w") is None else T[g("w")],
              "worse": [k for k in allk if rows[k]["status"] == "worse"],
              "better": [k for k in allk if rows[k]["status"] == "better"],
              "pending": [k for k in allk if rows[k]["status"] == "pending"], "ready_on": day(g("ro")),
              "settled_days": ns, "min_days": I.IMPACT_MIN_DAYS}
        nt = g("nt") or 0
        W = {"n": N, "state": None if g("st") is None else body["states"][g("st")],
             "before": {"from": day(-N), "to": day(-1), "days": N},
             "after": {"from": day(1), "to": day(ae), "days": ae, "settled": ns,
                       "settled_till": day(ns) if ns else None},
             "verdict": vd, "notes": [n for b, n in enumerate(body["notes"]) if nt >> b & 1],
             "mixed": [UP[k] for k in g("mx") or []], "mixed_before": [UP[k] for k in g("mb") or []],
             "overlap_before": None if g("ov") is None else UP[g("ov")],
             "cut_by": None if g("cb") is None else UP[g("cb")], "rows": rows}
        if N != I.WIN_DAYS:
            vd.update(n=N, state=W["state"], mixed=bool(W["mixed"]))
        out[str(N)] = W
    return out


# ── the input signature (an unchanged app keeps its file: most hourly builds compute nothing) ─────────────────────

def code_sig():
    """The engine code a result depends on (the source bytes of impact, uninstall, attrib and this module) + V."""
    h = hashlib.sha1(("impact_any:%d" % V).encode())
    for m in (I, U, attrib, sys.modules[__name__]):
        with open(m.__file__, "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:16]


def rev_reach(E, tz_ga4, tz_rev):
    """The last AdMob day a GA4 day ≤ E overlaps (impact._revenue_fn reads no later one): E in one timezone, else the
    AdMob-timezone day of the instant just before GA4 day E ends (an unknown timezone is UTC, as there)."""
    from zoneinfo import ZoneInfo

    def zone(tz):
        try:
            return ZoneInfo(tz or "UTC")
        except Exception:
            return ZoneInfo("UTC")
    zg, zr = zone(tz_ga4), zone(tz_rev)
    if zg.key == zr.key:
        return E
    end = datetime(E.year, E.month, E.day, tzinfo=zg) + timedelta(days=1)
    return (end.astimezone(timezone.utc) - timedelta(microseconds=1)).astimezone(zr).date()


def input_sig(store_sig, revenue, E, late, code, tz_ga4=None):
    """Everything an app's results read: the store file (store_sig — its time zone, days, cohorts …), the AdMob revenue
    a GA4 day ≤ E can touch (the days ≤ rev_reach, `till` capped there, tz, currency, the first revenue day), late
    days and the code — the same signature, the same file."""
    rv = None
    if revenue:
        days = {k: v for k, v in (revenue.get("days") or {}).items() if v is not None}
        cap = rev_reach(E, tz_ga4, revenue.get("tz")).isoformat()
        till = revenue.get("till") or (max(days) if days else None)
        rv = [revenue.get("tz"), revenue.get("currency"), min(till, cap) if till else None,
              min(days) if days else None, sorted((k, v) for k, v in days.items() if k <= cap)]
    raw = json.dumps([store_sig, rv, E.isoformat(), int(late or 0), code], separators=(",", ":"), sort_keys=True,
                     default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def read_head(path):
    """An existing per-app file → its body (None: missing / damaged / another format)."""
    import gzip
    try:
        with open(path, "rb") as f:
            body = json.loads(gzip.decompress(f.read()))
        return body if isinstance(body, dict) and body.get("v") == V else None
    except Exception:
        return None


def index_entry(body, file):
    """The index's line for one app (the date picker's bounds; fresh: built from this build's inputs)."""
    n = sum(1 for x in ((body.get("w") or {}).get("7") or {}).get("lv") or [] if x is not None)
    return {"app_id": body["app_id"], "key": body["key"], "file": file, "sig": body["sig"], "first": body["first"],
            "last": body["last"], "dates": n, "data_till": body["data_till"], "settled_till": body["settled_till"],
            "fresh": True}


# ── CONTRACT (the page reads these two files; decode() above is the reference reader) ────────────────────────────
#
# impact_any_<key>.json.gz — one per app (key = the app's 12-hex file key, as uninstall_c_ / active_ / value_<key>):
#   v 1 · app_id · key · sig (input signature, opaque) · data_till (E: the GA4 data's last day) · settled_till (E − 3:
#   activity / revenue judged up to it) · un_settled_till (E − late: install-day uninstalls) · currency
#   first / last / n — the DATE AXIS: day i = first + i, 0 ≤ i < n (n = 0, first = last = null: no date yet)
#   windows [7, 14, 30, 60] · rows (the 8 row keys; 7 / 14 use the first 7, 30 / 60 all 8 — + new_d30)
#   status / levels / states / notes / basis — the code tables (an index into them is a code)
#   text — the reasons and verdict lines (custom-date wording), by index · updates — [{key, label, date}] the app's
#   real updates, by date
#   u — [n]: null, or the updates released ON that date (their own update card exists)
#   w — {"7" | "14" | "30" | "60": WIN}; WIN = window columns + "r": [ROW] (one per row, in `rows` order); every
#   column is an array over the date axis (length n), null = nothing; a column that is null on every date is left out
#   WIN columns: lv level (levels[lv]; null ⇔ the window is missing on that date: it failed) · f 1 = final (else
#     early) · ns After days settled (settled_till of the window = date + ns) · ae (7 only) After's last day as an
#     offset when cut by the next update (0–6; else N) · st (14 / 30 / 60) states index · w verdict line (text) · ro
#     verdict ready_on (offset) · nt notes bitmask (bit b = notes[b]) · ov / cb (7) overlap_before / cut_by (updates
#     index) · mx / mb (14 / 30 / 60) mixed / mixed_before ([updates index])
#   ROW columns: s status (null → "na") · b a x p before / after / expected / after_prov in the row's unit (users
#     whole · pct a 0–1 share, 4 dp · num sessions 2 dp · sec seconds whole · usd1k money per 1,000 users 3 dp) ·
#     c change, q need ("pakka" needs it) — in points (the pct rows) or a 0–1 relative change (the rest), 2 / 3 dp ·
#     r reason (text) · ro ready_on (offset) · bs basis index, only when not the default (pct "rate", returning_dau
#     "expected", sessions / time / arpdau "expected" at 7, "plain" at 14 / 30 / 60) · e 1 = estimate (≈) · pv 1 =
#     provisional · nb / na n_before / n_after · fb tb fa ta the row's own day span (offsets) when not the window's
#     (Before −N … −1, After 1 … ae) · sp the installs vs per-user split wire (engine.attrib) · extras x<k>:
#     returning_dau xrc raw_change, xis imputed_share, xraw 1 = no return cohorts; new_d1 / d7 / d30 xib / xia
#     installs_before / after, xcb / xca cohorts_before / after; sessions / time xac adj_change (the judged change);
#     arpdau xij imp_adj (judged: ads per user), xic imp_change, xec ecpm_change, xit / xie imp_after / imp_expected,
#     xnb / xna newshare_before / after
#   Offsets are days from the chosen date. Every custom date's Before is [date − N, date − 1] and its After starts the
#   day after (date + 1); verdict worse / better / pending = the rows with that status, in `rows` order.
#
# impact_any_index.json.gz — {v 1, file_v (the per-app v), history_days 365, windows, apps: [{app_id, key, file,
#   sig, first, last, dates, data_till, settled_till, fresh}]} — fresh false: the build's time budget ran out, the
#   file is from older inputs (its own data_till says how old); an app not built yet: {app_id, key, file: null,
#   pending: true}. Apps with GA4 data only; one that failed this build is left out (its file removed).
