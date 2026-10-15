"""📅 The eCPM calendar of the 🔮 forecast (pure: no I/O, no clock, no prints) — ROI_DRIVERS §5.1 rule 6 / module D:
measured week and event effects of the ad market's price, from a like-for-like daily price index, instead of a month
of the year. Lab: forecast_lab9 (calidx.py, vd_cal.py); the back-test decides what is used (forecast_vd STRUCT).

The index (the AdMob ad-unit report: every app in the accounts, Android, all ad sources summed per ad unit × day):
  a unit-day counts with ≥ MIN_IMP impressions and revenue > 0. Season y (TG = Thanksgiving, the 4th Thursday of
  November of year y): its base = the 3 weeks before TG week, [TG − 24, TG − 4]. A unit enters with ≥ MIN_BASE_DAYS
  counted base days and ≥ MIN_BASE_REV USD of base revenue, weighing √(its app's base revenue) × its share of that
  app's base revenue (no single app decides). I_y(d) = Σ w·(log x_u(d) − the unit's mean log x over its base) ÷ Σ w
  over the units counted on d (a day whose units carry < MIN_COVER of the base weight is missing); x = eCPM, CTR
  (clicks ÷ impressions) or revenue per click — the same ad unit against itself, so app / country / format mix moves
  nothing.
The events of season y (each the mean of I_y over its days):
  bf     Black Friday week, Mon..Sun around TG        cyber  Cyber week, the 7 days after
  dec    the rest of December to the 21st             xmas   Christmas – New Year, Dec 22 – 31
  j1..j6 the January slide, 7-day weeks from January 1 of y + 1
  after week 6 the level HOLDS at j6: the slide is a step (in every season measured, Feb–Mar stayed at the week-6
  level), so the calendar's level c(d) counts every past January's j6 — a staircase whose differences are all the
  forecast ever uses.
A season counts once its week 6 is over (its index read to that day only). The profile at an origin T = the mean over
the seasons complete by T, each effect × n ÷ (n + SHRINK) (n of them: few seasons, so it leans toward no effect)."""
import math
from datetime import date, timedelta

ONE = timedelta(days=1)
MIN_IMP = 500
MIN_BASE_DAYS = 15
MIN_BASE_REV = 20.0
MIN_COVER = 0.5
FIRST = 2022                       # the first season looked for (the unit report starts mid-2023)
EVENTS = ("bf", "cyber", "dec", "xmas", "j1", "j2", "j3", "j4", "j5", "j6")
SLIDE = EVENTS[4:]
METRIC = {"ecpm": 0, "ctr": 1, "rpc": 2}


# ── the calendar's days ─────────────────────────────────────────────────────────────────────────────────────────────
def thanksgiving(y):
    d = date(y, 11, 1)
    while d.weekday() != 3:
        d += ONE
    return d + timedelta(days=21)


def base_window(y):
    tg = thanksgiving(y)
    return tg - timedelta(days=24), tg - timedelta(days=4)


def event_days(y, ev):
    """(first, last) day of season y's event."""
    tg = thanksgiving(y)
    if ev == "bf":
        return tg - timedelta(days=3), tg + timedelta(days=3)
    if ev == "cyber":
        return tg + timedelta(days=4), tg + timedelta(days=10)
    if ev == "dec":
        return tg + timedelta(days=11), date(y, 12, 21)
    if ev == "xmas":
        return date(y, 12, 22), date(y, 12, 31)
    s = date(y + 1, 1, 1) + timedelta(days=7 * (int(ev[1:]) - 1))
    return s, s + timedelta(days=6)


def hold_start(y):
    """The first day after season y's January week 6 (the slide's step holds from here)."""
    return event_days(y, "j6")[1] + ONE


def sliding(d):
    """Is day d inside its season's January slide (weeks 1–6)?"""
    y = season_of(d)
    return event_days(y, "j1")[0] <= d < hold_start(y)


def season_of(d):
    """The season y with base start ≤ d < the next season's base start."""
    y = d.year
    return y - 1 if d < base_window(y)[0] else y


def event_of(y, d):
    """Season y's event on day d ("base": the base and the days of the season with no event; "hold": after week 6;
    None: before the season's base)."""
    bs, be = base_window(y)
    if d < bs:
        return None
    if d <= be:
        return "base"
    for ev in EVENTS:
        a, b = event_days(y, ev)
        if a <= d <= b:
            return ev
    return "hold" if d >= hold_start(y) else "base"


# ── the index ───────────────────────────────────────────────────────────────────────────────────────────────────────
def units(rows, spans=None):
    """The ad-unit report's rows → ({unit: {day: [impressions, revenue USD, clicks]}}, {unit: app id}) — Android only;
    spans: [(first iso day, last iso day)] — only the days inside one of them (the seasons' days: a small dict)."""
    U, app_of = {}, {}
    for r in rows or []:
        if r.get("platform") != "Android":
            continue
        ds = str(r.get("report_date"))[:10]
        if spans is not None and not any(a <= ds <= b for a, b in spans):
            continue
        u = r.get("ad_unit_id")
        try:
            d = date.fromisoformat(ds)
        except ValueError:
            continue
        x = U.setdefault(u, {}).setdefault(d, [0, 0.0, 0])
        x[0] += r.get("impressions") or 0
        x[1] += (r.get("estimated_earnings_micros") or 0) / 1e6
        x[2] += r.get("clicks") or 0
        app_of[u] = r.get("app_id")
    return U, app_of


def _ok(v):
    return v is not None and v[0] >= MIN_IMP and v[1] > 0


def _logs(v):
    c = max(v[2], 1)
    return (math.log(v[1] / v[0]), math.log(c / v[0]), math.log(v[1] / c))


def season_index(U, app_of, y, till):
    """Season y's index {day: (eCPM, CTR, revenue per click) log index} for its base start ≤ day ≤ till, + how many
    units and apps carry it (None: the base not over by till, or no unit)."""
    bs, be = base_window(y)
    if till < be:
        return None
    ulist, arev = [], {}
    for u, dd in U.items():
        base = [v for d, v in dd.items() if bs <= d <= be and _ok(v)]
        if len(base) < MIN_BASE_DAYS:
            continue
        rev = sum(v[1] for v in base)
        if rev < MIN_BASE_REV:
            continue
        lg = [_logs(v) for v in base]
        ulist.append((u, rev, tuple(sum(x[k] for x in lg) / len(lg) for k in range(3))))
        a = app_of.get(u)
        arev[a] = arev.get(a, 0.0) + rev
    if not ulist:
        return None
    num, den, wtot = {}, {}, 0.0
    for u, rev, m in ulist:
        a = app_of.get(u)
        w = math.sqrt(arev[a]) * rev / arev[a]
        wtot += w
        dd = U[u]
        d = bs
        while d <= till:
            v = dd.get(d)
            if _ok(v):
                x = _logs(v)
                acc = num.setdefault(d, [0.0, 0.0, 0.0])
                for k in range(3):
                    acc[k] += w * (x[k] - m[k])
                den[d] = den.get(d, 0.0) + w
            d += ONE
    idx = {d: tuple(num[d][k] / den[d] for k in range(3)) for d in num if den[d] >= MIN_COVER * wtot}
    return {"idx": idx, "units": len(ulist), "apps": len(arev)}


def season_events(si, y):
    """{event: (eCPM, CTR, revenue per click)} — the mean index over the event's days with data (None: no day)."""
    out = {}
    for ev in EVENTS:
        a, b = event_days(y, ev)
        v, d = [], a
        while d <= b:
            if d in si["idx"]:
                v.append(si["idx"][d])
            d += ONE
        out[ev] = tuple(sum(x[k] for x in v) / len(v) for k in range(3)) if v else None
    return out


def seasons(rows, till):
    """Every season complete by `till` (its week 6 over), each read only to its own week 6 → the compact calendar the
    forecast carries: {"v": 1, "till": iso, "s": {"2024": {"ev": {event: [eCPM, CTR, rev/click]}, "units": n,
    "apps": n, "idx": {iso day: [eCPM, CTR, rev/click] index}}}} (a complete season missing an event is left out; the
    season in progress — its base over by till — carries its index so far, no "ev")."""
    ys = [y for y in range(FIRST, till.year + 1) if base_window(y)[1] <= till]     # (+ the season in progress)
    end = {y: min(till, hold_start(y) - ONE) for y in ys}
    U, app_of = units(rows, [(base_window(y)[0].isoformat(), end[y].isoformat()) for y in ys])
    out = {}
    for y in ys:
        si = season_index(U, app_of, y, end[y])
        if si is None:
            continue
        x = {"units": si["units"], "apps": si["apps"],
             "idx": {d.isoformat(): list(v) for d, v in sorted(si["idx"].items())}}
        if hold_start(y) <= till:                       # complete: its events (the profile's input)
            ev = season_events(si, y)
            if any(ev[e] is None for e in EVENTS):
                continue
            x["ev"] = {e: list(v) for e, v in ev.items()}
        out[str(y)] = x
    return {"v": 1, "till": till.isoformat(), "s": out}


# ── the level as known at T ─────────────────────────────────────────────────────────────────────────────────────────
def profile(cal, T, metric="ecpm", shrink=1.0):
    """{event: log effect} — the mean over the seasons complete by T (week 6 over), × n ÷ (n + shrink); + n."""
    k = METRIC[metric]
    per = [s["ev"] for y, s in sorted(((cal or {}).get("s") or {}).items()) if hold_start(int(y)) <= T and s.get("ev")]
    if not per:
        return None, 0
    n = len(per)
    f = n / (n + shrink) if shrink else 1.0
    return {e: f * sum(p[e][k] for p in per) / n for e in EVENTS}, n


def spread(cal, T, metric="ecpm"):
    """How far the seasons complete by T differ — what the page shows next to the measured mean: ({event: (the lowest
    season's, the highest season's) log effect}, [(season, apps it was measured on)] oldest first); (None, []) without
    one."""
    k = METRIC[metric]
    per = [(int(y), s) for y, s in sorted(((cal or {}).get("s") or {}).items())
           if hold_start(int(y)) <= T and s.get("ev")]
    if not per:
        return None, []
    return ({e: (min(s["ev"][e][k] for _, s in per), max(s["ev"][e][k] for _, s in per)) for e in EVENTS},
            [(y, s.get("apps")) for y, s in per])


class Level:
    """c(d): the calendar's log price level on day d from a profile (only differences between days are ever used)."""

    def __init__(self, prof):
        self.e = prof
        self.j6 = prof["j6"]
        self.memo = {}

    def __call__(self, d):
        v = self.memo.get(d)
        if v is None:
            y = season_of(d)
            v = sum(1 for yy in range(FIRST, y + 1) if hold_start(yy) <= d) * self.j6
            ev = event_of(y, d)
            if ev in self.e:
                v += self.e[ev]
            self.memo[d] = v
        return v


def closed(c, TG):
    """c for a reference window ending at TG: once TG's season has passed its week 6, its January days count at the
    held level (the slide is over: the forecast expects no more drop)."""
    y = season_of(TG)
    hs = hold_start(y)
    if hs > TG:
        return c
    j1 = event_days(y, "j1")[0]
    held = c(hs)
    return lambda d: held if j1 <= d < hs else c(d)


def anchored(cr, c, cal, T, TG, metric="ecpm"):
    """cr for a reference window ending at TG, anchored: while TG's season is in its slide or before (its base over by
    T, its week 6 not over by TG), each of its days ≤ T counts at the season's OWN observed index (the level of its
    base + the measured deviation) instead of the profile's — the level the forecast's levels really measured."""
    y = season_of(TG)
    bs, be = base_window(y)
    hs = hold_start(y)
    s = ((cal or {}).get("s") or {}).get(str(y))
    if not s or be > T or hs <= TG or not s.get("idx"):
        return cr
    k, idx, c0 = METRIC[metric], s["idx"], c(bs)

    def f(d):
        v = idx.get(d.isoformat()) if bs <= d < hs and d <= T else None
        return cr(d) if v is None else c0 + v[k]
    return f


def ref(c, end, n):
    """log mean e^c over the n days ending at `end` — the price level a level measured on those days carries."""
    s = 0.0
    for k in range(n):
        s += math.exp(c(end - timedelta(days=k)))
    return math.log(s / n)


def coming(T, h):
    """The event weeks that touch (T, T + h] → [(event, its first day, its last day, [its days inside the horizon])],
    in date order; + ("hold", first, None, …) when the horizon crosses a January week 6 (the held level after it)."""
    out = []
    end = T + timedelta(days=h)
    y0 = season_of(T + ONE)
    for y in (y0 - 1, y0, y0 + 1):
        for ev in EVENTS:
            a, b = event_days(y, ev)
            if b <= T or a > end:
                continue
            a2, b2 = max(a, T + ONE), min(b, end)
            out.append((ev, a, b, [a2 + timedelta(days=i) for i in range((b2 - a2).days + 1)]))
        hs = hold_start(y)
        if T < hs <= end:
            out.append(("hold", hs, None, [hs + timedelta(days=i) for i in range(min(7, (end - hs).days + 1))]))
    return sorted(out, key=lambda x: x[1])


# ── moving holidays: measured, shown, NOT in the forecast ──────────────────────────────────────────────────────────
# Ramadan (Muslim-majority countries) and Diwali (India) move every year and the AdMob country report (app × country ×
# day) has each only once so far — no back-test can show they help, so the forecast does not use them (the rule: a
# piece ships only after it wins). The measure is a gap: the treated countries' eCPM change minus the other countries'
# over the same days (both against their own base weeks), with each part kept so the page can show both. The page
# shows the gap, its two parts, and the gap × the app's own revenue share there.
RAMADAN = {2025: (date(2025, 3, 1), date(2025, 3, 30)), 2026: (date(2026, 2, 18), date(2026, 3, 19)),
           2027: (date(2027, 2, 8), date(2027, 3, 9)), 2028: (date(2028, 1, 28), date(2028, 2, 26))}
DIWALI = {2025: date(2025, 10, 20), 2026: date(2026, 11, 8), 2027: date(2027, 10, 29), 2028: date(2028, 10, 17)}
MUSLIM = frozenset(("ID", "PK", "BD", "EG", "SA", "AE", "TR", "MY", "DZ", "MA", "IQ", "JO", "KW", "QA", "OM", "BH",
                    "TN",
                    "AF", "UZ", "AZ", "SN", "LY", "YE", "SD"))
HOL_MIN = (20000, 20.0)            # a cell (app × country) needs ≥ these base impressions and USD


def holiday_windows(k, y):
    """(base first, base last, event first, event last) of holiday k in year y (None: no date known)."""
    if k == "ramadan":
        if y not in RAMADAN:
            return None
        a, b = RAMADAN[y]
        return a - timedelta(days=37), a - timedelta(days=10), a, b
    if y not in DIWALI:
        return None
    d = DIWALI[y]
    return d - timedelta(days=28), d - timedelta(days=8), d - timedelta(days=7), d + timedelta(days=3)


def _treated(k, cc):
    return cc in MUSLIM if k == "ramadan" else cc == "IN"


def holidays(rows, till):
    """The AdMob country report's rows (app × country × day) → {k: {"y": the newest occurrence over by till, "x": the
    log eCPM change of the treated countries minus that of the other countries (a gap, NOT the treated countries' own
    change; like for like: each app × country cell against its own base weeks, base-revenue weighted), "xt": the
    treated countries' own log change, "xc": the other countries' own log change (x = xt − xc), "cells": [treated,
    others]}} for k in ramadan / diwali (missing: none)."""
    need = []
    for k, tab in (("ramadan", RAMADAN), ("diwali", DIWALI)):
        ys = [y for y in tab if holiday_windows(k, y)[3] <= till]
        if ys:
            need.append((k, max(ys)))
    cells = {}
    spans = [(holiday_windows(k, y)[0].isoformat(), holiday_windows(k, y)[3].isoformat()) for k, y in need]
    for r in rows or []:
        ds = str(r.get("report_date") or "")[:10]
        if not any(a <= ds <= b for a, b in spans):
            continue
        i = r.get("impressions") or 0
        e = (r.get("estimated_earnings_micros") or 0) / 1e6
        if i <= 0 or e <= 0:
            continue
        x = cells.setdefault((r.get("app_id"), r.get("country")), {}).setdefault(date.fromisoformat(ds), [0, 0.0])
        x[0] += i
        x[1] += e
    out = {}
    for k, y in need:
        bs, be, a, b = holiday_windows(k, y)
        nb = (be - bs).days + 1
        idx = {True: [{}, {}], False: [{}, {}]}            # group → [Σ w·dev by day, Σ w by day]
        n = {True: 0, False: 0}
        for (app, cc), dd in cells.items():
            base = [v for d, v in dd.items() if bs <= d <= be]
            if len(base) < 0.8 * nb or sum(v[0] for v in base) < HOL_MIN[0] or sum(v[1] for v in base) < HOL_MIN[1]:
                continue
            m = sum(math.log(v[1] / v[0]) for v in base) / len(base)
            w = sum(v[1] for v in base)
            g = _treated(k, cc)
            n[g] += 1
            for d, v in dd.items():
                if bs <= d <= be or a <= d <= b:
                    s, t = idx[g]
                    s[d] = s.get(d, 0.0) + w * (math.log(v[1] / v[0]) - m)
                    t[d] = t.get(d, 0.0) + w
        if not n[True] or not n[False]:
            continue

        def mean(g, lo, hi):
            s, t = idx[g]
            v = [s[d] / t[d] for d in s if lo <= d <= hi and t[d] > 0]
            return sum(v) / len(v) if v else None
        mt, mc = mean(True, a, b), mean(False, a, b)
        bt, bc = mean(True, bs, be), mean(False, bs, be)
        if None in (mt, mc, bt, bc):
            continue
        out[k] = {"y": y, "x": (mt - mc) - (bt - bc), "xt": mt - bt, "xc": mc - bc, "cells": [n[True], n[False]]}
    return out


def holidays_coming(hol, T, h, shares):
    """The measured holidays whose event days touch (T, T + h] → [{"k", "a", "b", "x": the measured eCPM gap, treated
    minus the other countries (e^x − 1; NOT the treated countries' own change), "xt" / "xc": the treated / the other
    countries' own measured eCPM change (e^x − 1 each; None when the measure predates them), "y": the year measured,
    "s": the app's revenue share in the treated countries, "app": s × the gap (vs the other countries), "c": [treated
    cells, other cells] it was measured on}] — shares: {"ramadan": share, "diwali": share} of the app's own revenue."""
    out = []
    end = T + timedelta(days=h)
    for k in ("ramadan", "diwali"):
        m = (hol or {}).get(k)
        if not m:
            continue
        for y in range(T.year, end.year + 1):
            w = holiday_windows(k, y)
            if not w or w[3] <= T or w[2] > end:
                continue
            s = (shares or {}).get(k)
            x = math.exp(m["x"]) - 1.0
            xt = math.exp(m["xt"]) - 1.0 if m.get("xt") is not None else None
            xc = math.exp(m["xc"]) - 1.0 if m.get("xc") is not None else None
            out.append({"k": k, "a": w[2].isoformat(), "b": w[3].isoformat(), "x": x, "xt": xt, "xc": xc, "y": m["y"],
                        "s": s, "app": None if s is None else s * x, "c": list(m.get("cells") or [])})
    return sorted(out, key=lambda e: e["a"])


# ── the weekday rhythm per ad trigger (the daily chart only) ────────────────────────────────────────────────────────
# Each ad trigger has its own weekly rhythm: after-call ads follow phone calls (fewer on Sundays, every app measured),
# splash / resume / exit ads follow opens. An app's units are sorted into triggers by their names (the research's
# trigger inventory); each named trigger's own measured weekday shape × its share of the app's revenue gives the app's
# daily factors (the in-feature default bucket and unnamed units stay flat). The page's daily forecast takes them,
# scaled so every 30 / 90 / 180-day total stays exactly the forecast's (a weekly rhythm, not a level).
WK_WEEKS = 16                      # the newest complete weeks a shape is measured on
WK_MIN = 8                         # values a weekday needs
WK_SHARE = 0.02                    # a trigger earning no more than this share of the app's revenue: flat


def trigger(unit_name):
    """An ad unit's trigger from its name: after-call, notification, cold start, resume/bg, onboarding, exit/back, or
    the in-feature default."""
    n = (unit_name or "").lower().replace(" ", "_")
    if any(x in n for x in ("cad", "caller", "cdo", "after_call", "aftercall", "call_")):
        return "after-call"
    if "notif" in n:
        return "notification"
    if "splash" in n:
        return "cold start"
    if any(x in n for x in ("resume", "background", "_bg")):
        return "resume/bg"
    if any(x in n for x in ("language", "permission", "prmsn", "onboard", "intro", "lang")):
        return "onboarding"
    if any(x in n for x in ("exit", "back")):
        return "exit/back"
    return "in-feature"


def trigger_days(rows, lo, hi):
    """The ad-unit report's rows → {app id: {trigger: {iso day: revenue USD}}}, Android, lo ≤ day ≤ hi (iso)."""
    out = {}
    for r in rows or []:
        if r.get("platform") != "Android":
            continue
        ds = str(r.get("report_date") or "")[:10]
        if not lo <= ds <= hi:
            continue
        t = out.setdefault(r.get("app_id"), {}).setdefault(trigger(r.get("unit_name")), {})
        t[ds] = t.get(ds, 0.0) + (r.get("estimated_earnings_micros") or 0) / 1e6
    return out


def _shape(ser, T):
    """{weekday: log deviation} of one trigger's revenue from data ≤ T: log revenue − the centred 7-day mean of log
    revenue, the median per weekday over the newest WK_WEEKS weeks (≥ WK_MIN values each), centred to mean 0."""
    dv = {k: [] for k in range(7)}
    d = T - timedelta(days=WK_WEEKS * 7)
    while d <= T - timedelta(days=3):
        w = [ser.get((d + timedelta(days=i)).isoformat()) for i in range(-3, 4)]
        if all(x and x > 0 for x in w):
            dv[d.weekday()].append(math.log(w[3]) - sum(math.log(x) for x in w) / 7)
        d += ONE
    if any(len(v) < WK_MIN for v in dv.values()):
        return None
    m = {k: sorted(v)[len(v) // 2] for k, v in dv.items()}
    c = sum(m.values()) / 7
    return {k: v - c for k, v in m.items()}


def weekday(td, T):
    """An app's weekday factors [Mon..Sun] from its data ≤ T (None: no named trigger with a measurable rhythm): every
    named trigger's own shape × its share of the app's revenue over the newest 56 days, the rest flat; mean 1."""
    if not td:
        return None
    lo, hi = (T - timedelta(days=55)).isoformat(), T.isoformat()
    tot = sum(v for ser in td.values() for d, v in ser.items() if lo <= d <= hi)
    if tot <= 0:
        return None
    W, rest = [0.0] * 7, 1.0
    for t, ser in td.items():
        if t == "in-feature":
            continue
        s = sum(v for d, v in ser.items() if lo <= d <= hi) / tot
        if s <= WK_SHARE:
            continue
        w = _shape(ser, T)
        if w is None:
            continue
        rest -= s
        for k in range(7):
            W[k] += s * math.exp(w[k])
    if rest >= 0.999:
        return None
    W = [x + rest for x in W]
    m = sum(W) / 7
    return [x / m for x in W]
