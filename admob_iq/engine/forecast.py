"""🔮 Revenue forecast — the engine (pure: no I/O, no clock, no prints). Owner, 14 Oct 2026: "app 6 month ka he to next 6
month ka prediction … retention, day1, country wise … AI back testing … agar result alag milta he to AI khud learn
karega" — and his triangle: the install day 180 days old has every day observed; the one 179 days old gets its day 180
from the users who already reached it; the one 178 days old its days 179 and 180, and so on.

The model (everything from the app's own measured data; nothing typed in):
  revenue(D) = level(D) × Σ_install-days X  installs(X) × scale(X) × a(D − X)
    a(age)   — revenue per install on day `age` of an install day, learnt from the install days that REACHED that age
               (exact day by day to day 30, then the 31–60 / 61–90 / 91–180 / 181–365 bands, then a power-law tail),
               newer install days weighted more (half-life `hl`) — the triangle;
    scale(X) — what install day X really earned so far vs the curve, trusted more the older X is (credibility `K`):
               an install day that did better keeps doing better;
    level(D) — actual AdMob revenue ÷ the model on recent days (eCPM, the users older than the tracked install days):
               its median over the last `w` days, times the month-of-year eCPM season (strength `g`);
    installs — future installs = organic + Google Ads spend ÷ the recent cost of a paid install (window `W` days);
    country  — (c on) each install day on ITS countries' own curves (revenue per install to day 90 and users at each lag,
               per country, from the GA4 install-week country cells), the installs still to come on the newest mix —
               owner: "achhe ecpm vali country me install jyada aaye … us country ka life time back data ke curve pe";
    lift     — (r) the newest 14 install days' own lift vs the curve carried to the installs still to come (an app
               change that raised day-1 revenue shows at once).
  DAU the same way with the retention curve (users active on day `age` per install) → ARPDAU = revenue ÷ DAU.
Forecast = three parts, so a spend change is exact: old users + organic installs + paid installs (× spend multiplier).

Back-testing ("AI back testing"): from every ORIGIN_STEP-th past day (the newest MAX_ORIGINS), the whole model is rebuilt
with ONLY the data known that day, forecasts the next 30 / 90 / 180 days with the spend that really happened, and is
compared with the real revenue. The parameters (hl, K, w, g, W) are chosen by those tests (coordinate descent, newer
tests weigh more), then a measured bias correction; the misses are split into installs, retention (DAU) and ARPDAU
(eCPM) — what changed. The bands (P10–P90) are the tests' own error spread. A horizon is shown only once enough tests
exist for it (readiness) — the model decides, per app, from its own data.
"""
import bisect
import math
from datetime import date, timedelta

T_AGES = (0, 1, 3, 7, 14, 30, 60, 90, 180, 365)
BANDS = ((31, 60, 6), (61, 90, 7), (91, 180, 8), (181, 365, 9))      # (from, to, the T index of its end)
ULAGS = (0, 1, 3, 7, 14, 30, 45, 60, 90, 120, 180, 270, 365)
MAX_AGE = 900                         # ages beyond: 0 (the tail)
H = 180
HORIZONS = (30, 90, 180)
ORIGIN_STEP = 14
MAX_ORIGINS = 26                      # the newest ~year of tests
MIN_TESTS = 4                         # a horizon is shown once this many tests could score it
MIN_HIST = 42                         # days after the start before the first test origin
GRID = {"m": ("ratio", "split"), "hl": (45, 90, 180, 100000), "K": (7, 30, 90), "w": (3, 7, 14, 28), "g": (0.0, 1.0),
        "W": (14, 28), "r": (0.0, 0.5, 1.0), "c": (0, 1)}
DEFAULT = {"m": "ratio", "hl": 90, "K": 30, "w": 14, "g": 1.0, "W": 28, "r": 0.0, "c": 0}
RECENT = 14            # r — the newest install days' own lift (revenue and users vs the curve, pooled) carried to the
                       #     installs still to come: 0 none, 0.5 half, 1 all (an app change / a better country mix shows
                       #     at once, not only as the curve slowly learns it)
# m — how the users the install-day model does not cover (installed before the start / the GA4 history, very old)
#     are carried: "ratio" = revenue ÷ model on recent days, kept flat; "split" = their own revenue (actual − model),
#     decaying at its measured pace (the last 90 days' slope, never growing)
# c — country mix (1 on): every install day's revenue and users follow ITS countries' own curves (from the GA4
#     install-week country cells: each country's revenue per install in each band to day 90 and its users at each lag,
#     ÷ every install's) — so a day with more installs from a high-eCPM country earns more along that country's curve,
#     and the installs still to come take the newest two weeks' country mix. Past day 90 a country keeps its 61–90
#     standing. The curve a(age) is learnt mix-free (each install day ÷ its own mix), so old and new mixes compare.
CB = ((0, 0), (1, 1), (2, 3), (4, 7), (8, 14), (15, 30), (31, 60), (61, 90))   # the cells' revenue bands
CL = (1, 3, 7, 14, 30, 60, 90)                                                   # … and their users' lags
CKC = 1000.0                          # installs a country needs before its own figures are trusted half-way
BIX = [next((i for i, (lo, hi) in enumerate(CB) if lo <= L <= hi), len(CB) - 1) for L in range(MAX_AGE + 1)]
UIX = [-1 if L == 0 else max(i for i, g in enumerate(CL) if g <= L) for L in range(MAX_AGE + 1)]
HW = {30: 0.5, 90: 0.3, 180: 0.2}     # the objective's horizon weights
SPEND_DAYS = 7                        # the live forecast's spend: today's run-rate = the mean of the last 7 days
UBANDS = ((31, 60), (61, 90), (91, 180), (181, 365), (366, 730))   # uninstall curve: daily to 30, then these bands
UN_HL = 90                            # … newer install days weigh more (half-life, days)
ONE = timedelta(days=1)


def _d(s):
    return s if isinstance(s, date) else date.fromisoformat(s)


def _iso(d):
    return d.isoformat()


# ── the curve (per install) from the install days known at T ────────────────────────────────────────────────────────
def _known(c, X, T):
    """An install day's cumulative revenue known at T: [(age, cum USD)] ascending (exact final days, complete
    checkpoints)."""
    out = {}
    lim = (T - X).days
    d, df = c.get("d") or [], c.get("df") or 0
    for L in range(min(len(d), df, lim + 1)):
        if d[L] is not None:
            out[L] = d[L]
    t = c.get("t") or []
    for j, a in enumerate(T_AGES):
        if j < len(t) and t[j] is not None and a <= lim and (a > 30 or a not in out):
            out[a] = t[j]
    return sorted(out.items())


def _uknown(c, X, T):
    """An install day's active users known at T: {age: users} (exact final days, the install-day file's lags)."""
    out = {}
    lim = (T - X).days
    u, uf = c.get("u") or [], c.get("uf") or 0
    for L in range(min(len(u), uf, lim + 1)):
        out[L] = u[L]
    ul = c.get("ul") or []
    for j, a in enumerate(ULAGS):
        if j < len(ul) and ul[j] is not None and a <= lim and a not in out:
            out[a] = ul[j]
    return out


def _fill(points, maxage):
    """{age: per-day value at that age} sparse → a dense list 0..maxage: log-linear between points, a power-law tail
    after the last (fitted on ages ≥ 14, slope clipped), 0 before nothing is known."""
    ages = sorted(a for a, v in points.items() if v is not None and v > 0)
    out = [0.0] * (maxage + 1)
    if not ages:
        return out
    for a in range(0, ages[0] + 1):
        out[a] = points[ages[0]] if a == ages[0] else (points.get(a) or points[ages[0]])
    for i in range(len(ages) - 1):
        a0, a1 = ages[i], ages[i + 1]
        v0, v1 = points[a0], points[a1]
        for a in range(a0, a1 + 1):
            if a1 == a0:
                out[a] = v0
                continue
            x0, x1, x = math.log(a0 + 1), math.log(a1 + 1), math.log(a + 1)
            out[a] = math.exp(math.log(v0) + (math.log(v1) - math.log(v0)) * (x - x0) / (x1 - x0))
    last = ages[-1]
    tail = [a for a in ages if a >= 14]
    beta = 1.0
    if len(tail) >= 2:
        xs = [math.log(a + 1) for a in tail]
        ys = [math.log(points[a]) for a in tail]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        den = sum((x - mx) ** 2 for x in xs)
        if den > 0:
            beta = -sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    beta = min(2.0, max(0.3, beta))
    v = points[last]
    for a in range(last + 1, maxage + 1):
        out[a] = v * ((a + 1) / (last + 1)) ** (-beta)
    return out


def _fr(f, L):
    return f[0][BIX[L]] if f else 1.0


def _fu(f, L):
    return f[1][UIX[L]] if f and UIX[L] >= 0 else 1.0


def _wk(fx, X):
    return fx.get(X - timedelta(days=X.weekday())) if fx else None


def curve(coh, T, start, hl, fx=None):
    """(a, u, maxage): revenue per install and active users per install on each day of age, learnt from the install
    days ≥ start known at T (newer ones weigh more: half-life hl days). fx: the country mix by week (see mix) — then
    each install day counts as n × its mix factor, so a / u are an average install's."""
    num, den = {}, {}
    bnum, bden = {}, {}
    unum, uden = {}, {}
    maxage = 0
    for X, c in coh.items():
        if X < start or X > T or not c.get("n"):
            continue
        n = c["n"]
        w = 0.5 ** ((T - X).days / hl) if hl < 99999 else 1.0
        f = _wk(fx, X)
        k = _known(c, X, T)
        if not k:
            continue
        kd = dict(k)
        maxage = max(maxage, k[-1][0])
        for L in range(0, 31):                              # day by day (exact) — or a checkpoint band spread evenly
            if L in kd and (L == 0 or L - 1 in kd):
                inc = kd[L] - (kd[L - 1] if L else 0.0)
                num[L] = num.get(L, 0.0) + w * max(0.0, inc)
                den[L] = den.get(L, 0.0) + w * n * _fr(f, L)
        exact = any(L in kd for L in (2, 4, 5))
        if not exact:                                       # checkpoints only: 0, 1, 2–3, 4–7, 8–14, 15–30
            prev = None
            for a in (0, 1, 3, 7, 14, 30):
                if a in kd:
                    lo = 0 if prev is None else prev + 1
                    inc = kd[a] - (kd[prev] if prev is not None else 0.0)
                    for L in range(lo, a + 1):
                        num[L] = num.get(L, 0.0) + w * max(0.0, inc) / (a - lo + 1)
                        den[L] = den.get(L, 0.0) + w * n * _fr(f, L)
                    prev = a
                else:
                    break
        for lo, hi, j in BANDS:
            a0 = T_AGES[j - 1]
            if hi in kd and a0 in kd:
                inc = max(0.0, kd[hi] - kd[a0])
                bnum[(lo, hi)] = bnum.get((lo, hi), 0.0) + w * inc
                bden[(lo, hi)] = bden.get((lo, hi), 0.0) + w * n * (hi - lo + 1) * _fr(f, lo)
        uk = _uknown(c, X, T)
        for L, v in uk.items():
            unum[L] = unum.get(L, 0.0) + w * v
            uden[L] = uden.get(L, 0.0) + w * n * _fu(f, L)
    pts = {L: num[L] / den[L] for L in num if den.get(L)}
    for (lo, hi), v in bnum.items():
        if bden.get((lo, hi)):
            pts[(lo + hi) // 2] = v / bden[(lo, hi)]
    a = _fill(pts, MAX_AGE)
    for (lo, hi), v in bnum.items():                        # each band keeps its measured total
        if not bden.get((lo, hi)):
            continue
        want = v / bden[(lo, hi)] * (hi - lo + 1)
        have = sum(a[lo:hi + 1])
        if have > 0:
            f = want / have
            for L in range(lo, hi + 1):
                a[L] *= f
    upts = {L: unum[L] / uden[L] for L in unum if uden.get(L)}
    u = _fill(upts, MAX_AGE)
    return a, u, maxage


def _cum(a):
    cum = [0.0] * (len(a) + 1)
    for i, v in enumerate(a):
        cum[i + 1] = cum[i] + v
    return cum


def _cumf(cum, f, age):
    """Σ a(0..age) × the mix factor at each age (cum = _cum(a))."""
    age = min(age, len(cum) - 2)
    if not f:
        return cum[age + 1]
    tot = 0.0
    for b, (lo, hi) in enumerate(CB):
        if lo > age:
            break
        top = age if b == len(CB) - 1 else min(age, hi)
        tot += f[0][b] * (cum[top + 1] - cum[lo])
    return tot


def scales(coh, T, start, a, K, fx=None):
    """Each install day's scale: what it earned so far ÷ what the curve (× its country mix) says, trusted
    (age + 1) / (age + 1 + K)."""
    cum = _cum(a)
    out = {}
    for X, c in coh.items():
        if X < start or X > T or not c.get("n"):
            continue
        k = _known(c, X, T)
        if not k:
            out[X] = 1.0
            continue
        age, v = k[-1]
        exp = _cumf(cum, _wk(fx, X), age) * c["n"]
        raw = v / exp if exp > 0 else 1.0
        s = 1.0 + (raw - 1.0) * (age + 1) / (age + 1 + K)
        out[X] = min(5.0, max(0.2, s))
    return out


# ── installs, level, season ─────────────────────────────────────────────────────────────────────────────────────────
def installs_model(days, T, W):
    """(organic per day, paid installs per USD) from the last W days to T: organic = GA4 installs above the Google Ads
    ones; paid per USD = the rest ÷ spend."""
    n = sp = org = 0.0
    k = ko = 0
    D = T - timedelta(days=W - 1)
    while D <= T:
        e = days.get(D)
        if e and e.get("n") is not None:
            k += 1
            nd, na_d, spd = e.get("n") or 0, e.get("na"), e.get("sp") or 0
            n += nd
            sp += spd
            if na_d is not None or spd <= 0:            # a day without Google Ads installs: organic only if no spend
                org += max(0.0, nd - (na_d or 0))
                ko += 1
        D += ONE
    if not k:
        return 0.0, 0.0
    if sp <= 0:
        return n / k, 0.0
    org_d = org / ko if ko else 0.0
    paid = max(0.0, n - org_d * k)
    return org_d, paid / sp


def season_all(day_sets):
    """The portfolio's month-of-year index (every app's revenue ÷ DAU pooled) — steadier than one app's own."""
    pool = {}
    for days in day_sets:
        for D, e in days.items():
            r, u = e.get("rev"), e.get("dau")
            if r and u:
                x = pool.setdefault(D, {"rev": 0.0, "dau": 0.0})
                x["rev"] += r
                x["dau"] += u
    return season(pool)


def season(days):
    """Month-of-year index of the ARPDAU-like ratio revenue ÷ DAU (1 = average), from every full year in `days`
    (none: all 1)."""
    by = {}
    for D, e in days.items():
        r, u = e.get("rev"), e.get("dau")
        if r and u:
            by.setdefault((D.year, D.month), [0.0, 0.0])
            by[(D.year, D.month)][0] += r
            by[(D.year, D.month)][1] += u
    if len(by) < 13:
        return {m: 1.0 for m in range(1, 13)}
    yr = {}
    for (y, m), (r, u) in by.items():
        yr.setdefault(y, []).append(r / u)
    idx = {m: [] for m in range(1, 13)}
    for (y, m), (r, u) in by.items():
        base = sum(yr[y]) / len(yr[y])
        if len(yr[y]) >= 6 and base > 0:
            idx[m].append((r / u) / base)
    out = {}
    for m in range(1, 13):
        v = idx[m]
        out[m] = (sum(v) / len(v)) if len(v) >= 1 else 1.0
    mean = sum(out.values()) / 12
    return {m: out[m] / mean for m in out}


# ── one forecast from origin T ──────────────────────────────────────────────────────────────────────────────────────
def _model_day(coh, D, a, s, start, T, fx=None, users=False):
    tot = 0.0
    for X, c in coh.items():
        if X < start or X > D or X > T:
            continue
        age = (D - X).days
        if age < len(a):
            f = _wk(fx, X)
            tot += c["n"] * s.get(X, 1.0) * a[age] * (_fu(f, age) if users else _fr(f, age))
    return tot


def forecast(app, T, p, spend=None, h=H, seas=None):
    """The forecast from origin T with parameters p → {"rev": {old, org, paid}, "dau", "n", "sp"} lists of h days, plus
    the parts it used. spend: {day: USD} for the future days (None = the mean of the last SPEND_DAYS days, every day).
    + "dau_p" / "un" {old, org, paid}: active users and uninstalls a day by who they are (un: None without the
    Uninstall store's install day × lag cells)."""
    coh, days, start = app["coh"], app["days"], app["start"]
    fx_all, fnew_all = mix_at(app, T, p["hl"])
    fx, fnew = (fx_all, fnew_all) if p.get("c") else ({}, None)
    a, u, maxage = curve(coh, T, start, p["hl"], fx)
    s = scales(coh, T, start, a, p["K"], fx)
    # level: actual ÷ model on the last w days
    lv, ul = [], []
    D = T - timedelta(days=p["w"] - 1)
    while D <= T:
        e = days.get(D)
        if e and e.get("rev"):
            m = _model_day(coh, D, a, s, start, T, fx)
            if m > 0:
                lv.append(e["rev"] / m)
        if e and e.get("dau"):
            mu = _model_day(coh, D, u, {}, start, T, fx, True)
            if mu > 0:
                ul.append(e["dau"] / mu)
        D += ONE
    lvl = sorted(lv)[len(lv) // 2] if lv else 1.0
    ulv = sorted(ul)[len(ul) // 2] if ul else 1.0
    rest0, rho, urest0, urho = 0.0, 0.0, 0.0, 0.0
    if p.get("m") == "split":                           # the uncovered users: their own revenue, decaying
        lvl = 1.0
        pts, upts = [], []
        D = T - timedelta(days=89)
        while D <= T:
            e = days.get(D)
            if e and e.get("rev"):
                r = e["rev"] - _model_day(coh, D, a, s, start, T, fx)
                if r > 0:
                    pts.append(((D - T).days, math.log(r)))
            if e and e.get("dau"):
                q = e["dau"] - _model_day(coh, D, u, {}, start, T, fx, True)
                if q > 0:
                    upts.append(((D - T).days, math.log(q)))
            D += ONE

        def fit(pp):
            if len(pp) < 20:
                return 0.0, 0.0
            recent = sorted(v for x, v in pp if x > -p["w"])
            lvl0 = math.exp(recent[len(recent) // 2]) if recent else 0.0
            mx = sum(x for x, _ in pp) / len(pp)
            my = sum(v for _, v in pp) / len(pp)
            den = sum((x - mx) ** 2 for x, _ in pp)
            slope = sum((x - mx) * (v - my) for x, v in pp) / den if den else 0.0
            return lvl0, max(0.0, -slope)
        rest0, rho = fit(pts)
        urest0, urho = fit(upts)
        ulv = 1.0
    org, per_usd = installs_model(days, T, p["W"])
    lift, ulift = recent_lift(coh, T, start, a, u, fx) if p.get("r") else (1.0, 1.0)
    lift = 1.0 + p.get("r", 0.0) * (lift - 1.0)
    ulift = 1.0 + p.get("r", 0.0) * (ulift - 1.0)
    if spend is None:                                   # today's run-rate: the last SPEND_DAYS days' spend, with
        org, per_usd = installs_model(days, T, SPEND_DAYS)   # THEIR organic installs and cost per install (the same
        k, tot = 0, 0.0                                       # campaigns / countries — they move together)
        D = T - timedelta(days=SPEND_DAYS - 1)
        while D <= T:
            e = days.get(D)
            if e:
                k += 1
                tot += e.get("sp") or 0
            D += ONE
        base = tot / k if k else 0.0
        spend = {T + timedelta(days=i): base for i in range(1, h + 1)}
    seas = seas or {m: 1.0 for m in range(1, 13)}
    s0 = seas.get(T.month, 1.0) or 1.0
    old, orgr, paid, dau, nn, sp = [], [], [], [], [], []
    du_o, du_g, du_p = [], [], []
    q = uninstall_curve(app, T, start)
    un_o, un_g, un_p = [], [], []
    un_rest = un_rest0(app, T, start, q) if q else 0.0
    past = [(X, c["n"] * s.get(X, 1.0), c["n"], _wk(fx, X)) for X, c in coh.items() if start <= X <= T and c.get("n")]
    fut = []
    for i in range(1, h + 1):
        D = T + timedelta(days=i)
        g = (seas.get(D.month, 1.0) / s0) ** p["g"] if s0 else 1.0
        lvl_d = lvl * g
        o = 0.0
        du = 0.0
        uo = 0.0
        for X, ns, n0, f in past:
            age = (D - X).days
            if age < len(a):
                o += ns * a[age] * _fr(f, age)
                du += n0 * u[age] * _fu(f, age)
                if q:
                    uo += n0 * q[age]
        spd = spend.get(D, 0.0)
        fut.append((D, org, per_usd * spd))
        r_org = r_paid = u_org = u_paid = q_org = q_paid = 0.0
        for F, no, npd in fut:
            age = (D - F).days
            if age < len(a):
                fr = _fr(fnew, age) * lift
                r_org += no * a[age] * fr
                r_paid += npd * a[age] * fr
                fu = u[age] * ulift * _fu(fnew, age)
                u_org += no * fu
                u_paid += npd * fu
                if q:
                    q_org += no * q[age]
                    q_paid += npd * q[age]
        u_new = u_org + u_paid
        old.append(o * lvl_d + rest0 * math.exp(-rho * i) * g)
        orgr.append(r_org * lvl_d)
        paid.append(r_paid * lvl_d)
        dau.append((du + u_new) * ulv + urest0 * math.exp(-urho * i))
        du_o.append(du * ulv + urest0 * math.exp(-urho * i))
        du_g.append(u_org * ulv)
        du_p.append(u_paid * ulv)
        if q:
            un_o.append(uo + un_rest)
            un_g.append(q_org)
            un_p.append(q_paid)
        nn.append(org + per_usd * spd)
        sp.append(spd)
    return {"rev": {"old": old, "org": orgr, "paid": paid}, "dau": dau, "n": nn, "sp": sp,
            "dau_p": {"old": du_o, "org": du_g, "paid": du_p},
            "un": {"old": un_o, "org": un_g, "paid": un_p} if q else None,
            "parts": {"level": lvl, "ulevel": ulv, "rest": rest0, "rho": rho, "lift": lift, "ulift": ulift,
                      "mix": (_cumf(_cum(a), fnew_all, 90) / sum(a[:91])) if fnew_all and sum(a[:91]) > 0 else None,
                      "mix_on": bool(fnew), "org": org, "per_usd": per_usd, "maxage": maxage,
                      "a30": sum(a[:31]), "a90": sum(a[:91]), "a180": sum(a[:181]), "u1": u[1] if len(u) > 1 else None,
                      "u7": u[7] if len(u) > 7 else None}}


def recent_lift(coh, T, start, a, u, fx=None):
    """The newest RECENT install days, pooled: (revenue so far ÷ the curve's, active users ÷ the curve's) at each one's
    own known age — how much better / worse the installs of right now do than the curve (× their country mix) says
    (1 = the same)."""
    cum = _cum(a)
    obs = exp = uobs = uexp = 0.0
    lo = T - timedelta(days=RECENT - 1)
    for X, c in coh.items():
        if X < max(lo, start) or X > T or not c.get("n"):
            continue
        f = _wk(fx, X)
        k = _known(c, X, T)
        if k:
            age, v = k[-1]
            obs += v
            exp += _cumf(cum, f, age) * c["n"]
        for L, v in _uknown(c, X, T).items():
            if 1 <= L <= 30 and L < len(u):
                uobs += v
                uexp += u[L] * c["n"] * _fu(f, L)
    lift = min(3.0, max(0.33, obs / exp)) if exp > 0 else 1.0
    ulift = min(3.0, max(0.33, uobs / uexp)) if uexp > 0 else 1.0
    return lift, ulift


def mix(cty, T, hl, start):
    """The country mix at T from the install-week country cells {week Monday: {slot: {"n", "r": [revenue in each CB
    band], "u": [active users at each CL lag]}}} ("gap" = the installs / revenue no country was read for: average).
    m[country][band] = its revenue per install in the band ÷ every install's — from the weeks complete for that band at
    T only (newer weigh more: half-life hl), trusted n ÷ (n + CKC) — and its users per install at each lag likewise.
    A week's factor = Σ its countries' install shares × their m (1 = an average install).
    → ({week: (rf, uf)}, (rf, uf) of the newest two complete weeks — the installs still to come) — ({}, None) without
    cells."""
    weeks = sorted(W for W in (cty or {}) if start - timedelta(days=6) <= W <= T)
    if not weeks:
        return {}, None
    nb, nl = len(CB), len(CL)
    rs, us = {}, {}
    ra = [[0.0, 0.0] for _ in range(nb)]
    ua = [[0.0, 0.0] for _ in range(nl)]
    for W in weeks:
        wt = 0.5 ** ((T - W).days / hl) if hl < 99999 else 1.0
        end = W + timedelta(days=6)
        cells = cty[W]
        for b, (lo, hi) in enumerate(CB):
            if end + timedelta(days=hi) > T:
                break
            for k, e in cells.items():
                n, r = e.get("n") or 0, (e.get("r") or [0] * nb)[b]
                ra[b][0] += wt * r
                ra[b][1] += wt * n
                if k != "gap":
                    x = rs.setdefault(k, [[0.0, 0.0] for _ in range(nb)])
                    x[b][0] += wt * r
                    x[b][1] += wt * n
        for j, g in enumerate(CL):
            if end + timedelta(days=g) > T:
                break
            for k, e in cells.items():
                if k == "gap" or not e.get("u"):
                    continue
                n, v = e.get("n") or 0, e["u"][j]
                ua[j][0] += wt * v
                ua[j][1] += wt * n
                x = us.setdefault(k, [[0.0, 0.0] for _ in range(nl)])
                x[j][0] += wt * v
                x[j][1] += wt * n

    def rel(per, tot, nk):
        """{country: [m per band / lag]}: shrunk to 1, a band no week completed yet carries the one before, and
        normalised so the learning weeks' own mix averages exactly 1."""
        out = {k: [1.0] * nk for k in per}
        for b in range(nk):
            R, N = tot[b]
            if N <= 0 or R <= 0:
                for k in per:
                    out[k][b] = out[k][b - 1] if b else 1.0
                continue
            ref = 0.0
            for k, x in per.items():
                r, n = x[b]
                m = (r / n) / (R / N) if n > 0 else (out[k][b - 1] if b else 1.0)
                m = 1.0 + (m - 1.0) * (n / (n + CKC)) if n > 0 else m
                out[k][b] = min(10.0, max(0.05, m))
                ref += max(0.0, n) / N * out[k][b]
            ref += max(0.0, 1.0 - sum(max(0.0, x[b][1]) for x in per.values()) / N)      # the gap: 1
            if ref > 0:
                for k in per:
                    out[k][b] /= ref
        return out
    mr, mu = rel(rs, ra, nb), rel(us, ua, nl)

    def fac(cells_list):
        tot = sum(e.get("n") or 0 for cells in cells_list for e in cells.values())
        if tot <= 0:
            return None
        rf, uf = [0.0] * nb, [0.0] * nl
        for cells in cells_list:
            for k, e in cells.items():
                q = (e.get("n") or 0) / tot
                r, v = mr.get(k), mu.get(k)
                for b in range(nb):
                    rf[b] += q * (r[b] if r else 1.0)
                for j in range(nl):
                    uf[j] += q * (v[j] if v else 1.0)
        return [max(0.05, x) for x in rf], [max(0.05, x) for x in uf]
    fx = {}
    for W in weeks:
        f = fac([cty[W]])
        if f:
            fx[W] = f
    done = [W for W in weeks if W + timedelta(days=6) <= T][-2:]
    return fx, (fac([cty[W] for W in done]) if done else None)


def mix_at(app, T, hl):
    """mix() for this app at T, kept (tuning asks again and again)."""
    if not app.get("cty"):
        return {}, None
    memo = app.setdefault("_mix", {})
    k = (T, hl)
    if k not in memo:
        memo[k] = mix(app["cty"], T, hl, app["start"])
    return memo[k]


def _unc_prep(app):
    """The Uninstall store's install day × lag cells → per install day (daily lags 0..30, each UBANDS band's total, the
    newest lag it has) — once per app (every origin and setting reuses it)."""
    if "_uncp" not in app:
        out = {}
        for X, cells in (app.get("unc") or {}).items():
            dl = [0.0] * 31
            bs = [0.0] * len(UBANDS)
            for L, v in cells.items():
                if L <= 30:
                    dl[L] += v
                else:
                    for j, (lo, hi) in enumerate(UBANDS):
                        if lo <= L <= hi:
                            bs[j] += v
                            break
            out[X] = (dl, bs)
        app["_uncp"] = out
    return app["_uncp"]


def uninstall_curve(app, T, start):
    """q[age]: uninstalls per install on day `age` of an install day — the triangle again: each age learnt only from
    install days ≥ start that reached it by T (the Uninstall store's install day × lag cells; newer weigh more,
    half-life UN_HL), daily to day 30, then the UBANDS bands (each keeps its measured total), then a power-law tail.
    None without cells. Memoised per T."""
    memo = app.setdefault("_unq", {})
    if T in memo:
        return memo[T]
    pre = _unc_prep(app)
    if not pre:
        memo[T] = None
        return None
    num, den, bnum, bden = [0.0] * 31, [0.0] * 31, [0.0] * len(UBANDS), [0.0] * len(UBANDS)
    for X, (dl, bs) in pre.items():
        if X < start or X > T:
            continue
        n = (app["coh"].get(X) or {}).get("n")
        if not n:
            continue
        lim = (T - X).days
        w = 0.5 ** (lim / UN_HL)
        for L in range(0, min(30, lim) + 1):
            num[L] += w * dl[L]
            den[L] += w * n
        for j, (lo, hi) in enumerate(UBANDS):
            if hi <= lim:
                bnum[j] += w * bs[j]
                bden[j] += w * n * (hi - lo + 1)
    if not den[0]:
        memo[T] = None
        return None
    pts = {L: num[L] / den[L] for L in range(31) if den[L] and num[L] > 0}
    for j, (lo, hi) in enumerate(UBANDS):
        if bden[j] and bnum[j] > 0:
            pts[(lo + hi) // 2] = bnum[j] / bden[j]
    q = _fill(pts, MAX_AGE)
    for L in range(31):                                  # the measured days exactly (zero days stay zero)
        if den[L]:
            q[L] = num[L] / den[L]
    for j, (lo, hi) in enumerate(UBANDS):
        if bden[j]:
            want = bnum[j] / bden[j] * (hi - lo + 1)
            have = sum(q[lo:hi + 1])
            if have > 0:
                for L in range(lo, hi + 1):
                    q[L] *= want / have
    memo[T] = q
    return q


def un_rest0(app, T, start, q):
    """The uninstalls the install-day model does not place (install days before the start / outside the store, the
    store's unplaced ones): the median of actual − model over the last 14 days (never below 0), kept flat."""
    days, coh = app["days"], app["coh"]
    vals = []
    for i in range(14):
        D = T - timedelta(days=i)
        act = (days.get(D) or {}).get("un")
        if act is None:
            continue
        m = 0.0
        for X, c in coh.items():
            if X < start or X > D or not c.get("n"):
                continue
            age = (D - X).days
            if age < len(q):
                m += c["n"] * q[age]
        vals.append(max(0.0, act - m))
    return sorted(vals)[len(vals) // 2] if vals else 0.0


def _sum(lst, k):
    return sum(lst[:k])


# ── back-testing ────────────────────────────────────────────────────────────────────────────────────────────────────
def origins(app):
    """Test origins: every ORIGIN_STEP days back from the last actual day − 30, the newest MAX_ORIGINS, ≥ MIN_HIST
    days after the start."""
    last, start = app["last"], app["start"]
    out, T = [], last - timedelta(days=30)
    while T >= start + timedelta(days=MIN_HIST) and len(out) < MAX_ORIGINS:
        out.append(T)
        T -= timedelta(days=ORIGIN_STEP)
    return sorted(out)


def backtest(app, p, seas=None, ors=None):
    """[{T, h: {30: {pred, act, err, n_err, dau_err, arp_err}, …}}] — every forecast with the spend that really happened."""
    days, last = app["days"], app["last"]
    jumps = app.get("_jumps")
    if jumps is None:
        jumps = app["_jumps"] = {D: event(days, D) for D in days if event(days, D)}
    res = []
    for T in (ors if ors is not None else origins(app)):
        hmax = min(H, (last - T).days)
        if hmax < HORIZONS[0]:
            continue
        sp = {T + timedelta(days=i): (days.get(T + timedelta(days=i)) or {}).get("sp") or 0.0 for i in range(1, hmax + 1)}
        f = forecast(app, T, p, spend=sp, h=hmax, seas=seas)
        rev = [o + g + q for o, g, q in zip(f["rev"]["old"], f["rev"]["org"], f["rev"]["paid"])]
        row = {"T": _iso(T), "h": {}, "ev": {}}
        for hz in HORIZONS:
            if hz > hmax:
                continue
            act = [days.get(T + timedelta(days=i)) or {} for i in range(1, hz + 1)]
            ar = sum(e.get("rev") or 0 for e in act)
            if ar <= 0:
                continue
            pr = _sum(rev, hz)
            an = sum(e.get("n") or 0 for e in act)
            pn = _sum(f["n"], hz)
            au = sum(e.get("dau") or 0 for e in act)
            pu = _sum(f["dau"], hz)
            ev = None
            for k in range(0, hz - 29, 7):                  # an abrupt jump starting anywhere inside this horizon
                ev = jumps.get(T + timedelta(days=k))
                if ev:
                    ev = dict(ev, at=_iso(T + timedelta(days=k)))
                    break
            if ev:
                row["ev"][hz] = ev
            un_e = None
            if f.get("un"):
                aun = sum(e.get("un") or 0 for e in act)
                pun = sum(_sum(f["un"][k], hz) for k in ("old", "org", "paid"))
                if aun > 0 and all(e.get("un") is not None for e in act):
                    un_e = pun / aun - 1.0
            row["h"][hz] = {"pred": pr, "act": ar, "err": pr / ar - 1.0, "un_err": un_e,
                            "n_err": (pn / an - 1.0) if an else None, "dau_err": (pu / au - 1.0) if au else None,
                            "arp_err": ((pr / pu) / (ar / au) - 1.0) if pu and au else None}
        if row["h"]:
            res.append(row)
    return res


EV_N = (0.4, 2.5)      # installs over the next 30 days ÷ the 28 before, with spend within ×1.5 — organic jump / drop
EV_ARP = (0.6, 1.5)    # ARPDAU over the next 30 days ÷ the 28 before — eCPM / ads shock


def _win(days, a, b):
    n = sp = rev = dau = 0.0
    k = 0
    D = a
    while D <= b:
        e = days.get(D)
        if e:
            k += 1
            n += e.get("n") or 0
            sp += e.get("sp") or 0
            rev += e.get("rev") or 0
            dau += e.get("dau") or 0
        D += ONE
    return k, n, sp, rev, dau


def event(days, T):
    """A sudden change no model sees coming, measured AFTER the fact: installs ×2.5 / ×0.4 with spend not moving like
    it, or ARPDAU ×1.5 / ×0.6 → its words (None: a normal test)."""
    k0, n0, s0, r0, u0 = _win(days, T - timedelta(days=27), T)
    k1, n1, s1, r1, u1 = _win(days, T + ONE, T + timedelta(days=30))
    if not k0 or not k1:
        return None
    n0, n1, s0, s1 = n0 / k0, n1 / k1, s0 / k0, s1 / k1
    if n0 > 0:
        q = n1 / n0
        steady = (s0 <= 0 and s1 <= 0) or (s0 > 0 and 1 / 1.5 <= s1 / s0 <= 1.5)
        if steady and (q > EV_N[1] or q < EV_N[0]):
            return {"kind": "installs", "x": round(q, 2)}
    if u0 > 0 and u1 > 0 and r0 > 0:
        q = (r1 / u1) / (r0 / u0)
        if q > EV_ARP[1] or q < EV_ARP[0]:
            return {"kind": "arpdau", "x": round(q, 2)}
    return None


def normal(bt, hz=None):
    """The tests without a sudden change inside (per horizon: a test keeps its other horizons)."""
    out = []
    for r in bt:
        ev = r.get("ev") or {}
        h = {k: v for k, v in r["h"].items() if k not in ev and (hz is None or k == hz)}
        if h:
            out.append(dict(r, h=h))
    return out


EV_W = 0.3             # a test with a sudden change inside still teaches, at this weight


def score(bt):
    """The tuning objective: the weighted mean |error| (newer tests weigh more; horizons by HW; a sudden-change test
    at EV_W)."""
    tot = wsum = 0.0
    n = len(bt)
    for i, r in enumerate(bt):
        rw = 0.5 + 0.5 * (i + 1) / n
        ev = r.get("ev") or {}
        for hz, x in r["h"].items():
            w = HW.get(hz, 0.1) * rw * (EV_W if hz in ev else 1.0)
            tot += w * abs(x["err"])
            wsum += w
    return tot / wsum if wsum else None


def tune(app, seas=None, start_p=None, passes=2):
    """Coordinate descent over GRID on the back-test score → (best params, its back-test, every step tried)."""
    ors = origins(app)
    p = dict(DEFAULT, **{k: v for k, v in (start_p or {}).items() if k in DEFAULT})   # (a run saved before a setting
    if not ors:                                                                       #  existed starts it at default)
        return p, [], []
    cache = {}

    def run(q):
        key = tuple(sorted(q.items()))
        if key not in cache:
            bt = backtest(app, q, seas, ors)
            cache[key] = (score(bt), bt)
        return cache[key]
    best, bt = run(p)
    steps = [{"p": dict(p), "score": best}]
    for _ in range(passes):
        changed = False
        for k, vals in GRID.items():
            for v in vals:
                if v == p[k]:
                    continue
                q = dict(p, **{k: v})
                sc, b2 = run(q)
                if sc is not None and (best is None or sc < best - 1e-4):
                    p, best, bt, changed = q, sc, b2, True
                    steps.append({"p": dict(p), "score": sc, "changed": k})
        if not changed:
            break
    return p, bt, steps


def calibrate(bt):
    """Per horizon, from the tests: the bias correction (median error of the newer half of the NORMAL tests, shrunk by
    their count), the P10 / P90 band of the corrected normal errors (all tests when too few are normal), the mean
    |error| of every test and of the normal ones, and how often a sudden change hit → {h: {...}}."""
    out = {}
    for hz in HORIZONS:
        allr = [r for r in bt if hz in r["h"]]
        if len(allr) < MIN_TESTS:
            continue
        errs = [r["h"][hz]["err"] for r in allr]
        norm = [r["h"][hz]["err"] for r in allr if hz not in (r.get("ev") or {})]
        base = norm if len(norm) >= MIN_TESTS else errs
        recent = base[len(base) // 2:]
        med = sorted(recent)[len(recent) // 2]
        bias = med * len(recent) / (len(recent) + 3)
        corr = sorted((1 + e) / (1 + bias) - 1 for e in base)

        def q(p, v=corr):
            i = p * (len(v) - 1)
            lo = int(math.floor(i))
            hi = min(len(v) - 1, lo + 1)
            return v[lo] + (v[hi] - v[lo]) * (i - lo)
        ca = [abs((1 + e) / (1 + bias) - 1) for e in errs]
        cn = [abs((1 + e) / (1 + bias) - 1) for e in norm]
        ue = [abs(r["h"][hz]["un_err"]) for r in allr if r["h"][hz].get("un_err") is not None]
        out[hz] = {"bias": bias, "lo": q(0.1), "hi": q(0.9), "mape": sum(ca) / len(ca), "n": len(errs),
                   "un_mape": (sum(ue) / len(ue)) if ue else None, "un_n": len(ue),
                   "mape_normal": (sum(cn) / len(cn)) if cn else None, "n_normal": len(cn),
                   "ev_rate": 1 - len(norm) / len(errs)}
    return out


def attribution(bt, hz=30):
    """The misses of the newest tests split into installs, retention (DAU beyond installs) and ARPDAU (eCPM) — the share
    of the error's size each explains (log terms)."""
    parts = {"installs": 0.0, "retention": 0.0, "arpdau": 0.0}
    k = 0
    for r in bt[-8:]:
        x = r["h"].get(hz)
        if not x or x["dau_err"] is None or x["arp_err"] is None:
            continue
        ln_tot = math.log(max(1e-6, 1 + x["err"]))
        ln_d = math.log(max(1e-6, 1 + x["dau_err"]))
        ln_a = math.log(max(1e-6, 1 + x["arp_err"]))
        ln_n = math.log(max(1e-6, 1 + (x["n_err"] or 0.0))) * 0.3     # new users are a part of DAU over 30 days
        ln_r = ln_d - ln_n
        tot = abs(ln_n) + abs(ln_r) + abs(ln_a)
        if tot <= 0 or abs(ln_tot) < 1e-9:
            continue
        parts["installs"] += abs(ln_n) / tot
        parts["retention"] += abs(ln_r) / tot
        parts["arpdau"] += abs(ln_a) / tot
        k += 1
    if not k:
        return None
    return {key: v / k for key, v in parts.items()}


def auto_start(days, min_n=100):
    """The first day of the app's real run: the first 14 days in a row where installs stay ≥ max(min_n, 20% of the
    median of the next 60 days) on 12 of the 14 (the trial / test days before it are left out)."""
    ds = sorted(days)
    vals = [days[d].get("n") or 0 for d in ds]
    for i in range(len(ds)):
        nxt = sorted(vals[i:i + 60])
        if len(nxt) < 14:
            break
        floor = max(min_n, 0.2 * nxt[len(nxt) // 2])
        win = vals[i:i + 14]
        if sum(1 for v in win if v >= floor) >= 12 and vals[i] >= floor:
            return ds[i]
    return ds[0] if ds else None
