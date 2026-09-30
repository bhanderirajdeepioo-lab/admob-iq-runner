"""Daily App Review — series helpers: install-week shares, walk-back of a change's start, day series, releases."""

from datetime import timedelta

from .const import ECPM_MIN_IMPR
from .fmt import D


def un_weeks(ctx, aid, n, end):
    """Weekly day-n uninstall share by install week, newest first, weeks ending on `end`, `end`-7, ..."""
    c = ctx.cfile(aid)
    if not c:
        return []
    st, cend = D(c["start"]), D(c["end"])
    new, lags = c["new"], c["lags"]
    un = [sum(cnt for lag, cnt in (day or []) if lag <= n) for day in lags]
    out, e = [], D(end)
    while e - timedelta(6) >= st:
        s = e - timedelta(6)
        i0, i1 = (s - st).days, (e - st).days
        if i1 < len(new):
            nw, uu = sum(new[i0:i1 + 1]), sum(un[i0:i1 + 1])
            out.append({"s": s, "e": e, "n": nw, "p": (uu / nw) if nw else None,
                        "mature": e + timedelta(n) <= cend})
        e -= timedelta(7)
    return out


def ret_weeks(ctx, aid, N, end):
    """Weekly N-day return share by install week from the Active file (coh.dN / new), newest first."""
    f = ctx.afile(aid)
    if not f:
        return []
    dl = f["daily"]
    st, new, coh = D(dl["start"]), dl["new"], (dl.get("coh") or {}).get(f"d{N}") or []
    out, e = [], D(end)
    while e - timedelta(6) >= st:
        s = e - timedelta(6)
        i0, i1 = (s - st).days, (e - st).days
        if i1 < len(new) and i1 < len(coh):
            vals = [(new[i], coh[i]) for i in range(i0, i1 + 1) if coh[i] is not None]
            nw = sum(x for x, _ in vals)
            out.append({"s": s, "e": e, "n": nw, "p": (sum(y for _, y in vals) / nw) if nw else None,
                        "mature": len(vals) == 7})
        e -= timedelta(7)
    return out


def walk_back(weeks, before, now, min_n=50):
    """Step back while a week is closer to `now` than to `before`. -> (shuru, capped)"""
    if not weeks:
        return None, False
    earliest = weeks[0]["s"]
    for i, w in enumerate(weeks[1:], 1):
        if i > 26:
            return earliest, True
        if w["p"] is None or w["n"] < min_n or not w["mature"]:
            continue
        if abs(w["p"] - now) < abs(w["p"] - before):
            earliest = w["s"]
        else:
            break
    return earliest, False


def day_series(ctx, aid, metric, unit_id=None):
    """-> dict date -> value for 'kamai' (app), or ad unit 'rev'/'ctr'/'clicks'/'impr'/'match'."""
    if metric == "kamai":
        return dict(ctx.rev[aid])
    p = ctx.unit.get(unit_id) or {}
    out = {}
    for r in p.get("daily") or []:
        d_, e, im, rq, ma, ck = r[:6]
        out[d_] = {"rev": e / 1e6, "impr": im, "req": rq, "match": (ma / rq) if rq else None,
                   "clicks": ck, "ctr": (ck / im) if im else None}[metric]
    return out


def cross_start(series, last, before, now, max_back=28):
    """First day of the latest run of days on the 'now' side of the halfway point (walking back from `last`)."""
    half = (before + now) / 2
    down = now < before
    d_, start = D(last), None
    for _ in range(max_back):
        v = series.get(d_.isoformat())
        if v is None:
            break
        if (v <= half) if down else (v >= half):
            start = d_
            d_ -= timedelta(1)
        else:
            break
    return start


def avg(series, days):
    vals = [series.get(x) for x in days if series.get(x) is not None]
    return sum(vals) / len(vals) if vals else None


def rel_update(ctx, aid, day, before_days=3):
    """The release that came out on `day` or up to `before_days` earlier (latest first)."""
    best = None
    for u in (ctx.ud.get(aid) or {}).get("updates") or []:
        g = (D(day) - D(u["date"])).days
        if 0 <= g <= before_days and (best is None or u["date"] > best["date"]):
            best = u
    return best


def rel_near(ctx, aid, day, days=14):
    best = None
    for u in (ctx.ud.get(aid) or {}).get("updates") or []:
        g = (D(day) - D(u["date"])).days
        if 0 <= g <= days and (best is None or u["date"] > best["date"]):
            best = u
    return best


def late_days(ctx, aid, src):
    if src == "active":
        f = ctx.afile(aid) or {}
        return int(f.get("act_late_days") or 3)
    return int((ctx.uapp.get(aid) or {}).get("late_days") or 7)


def ecpm(ctx, aid, days):
    """Ad rate (per 1,000 impressions) over `days` — None under ECPM_MIN_IMPR impressions (noise)."""
    ad = ctx.ad.get(aid) or {}
    e = sum(ad[d][0] for d in days if d in ad)
    i = sum(ad[d][1] for d in days if d in ad)
    return (e / i * 1000) if i >= ECPM_MIN_IMPR else None


def month_run(ctx, uid, metric, lo, hi, below):
    """-> (first month 'YYYY-MM' of the latest run outside the range, reached_first_month)"""
    s = (ctx.bunit.get(uid) or {}).get("series") or {}
    mo, vals = s.get("mo") or [], s.get(metric) or []
    i, start = len(vals) - 1, None
    while i >= 0 and vals[i] is not None and ((vals[i] < lo) if below else (vals[i] > hi)):
        start, i = i, i - 1
    return (mo[start], start == 0) if start is not None else (None, False)


def idx_of_day(days, d_):
    d_ = D(d_).isoformat() if d_ else None
    return days.index(d_) if d_ in days else None


def idx_of_week(weeks, d_):
    if not d_:
        return None
    for i, w in enumerate(weeks):
        if w["s"] <= D(d_) <= w["e"]:
            return i
    return None
