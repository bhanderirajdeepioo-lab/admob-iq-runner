"""Daily App Review — chart DATA for a feature's "Detail →" (the page draws it; no SVG here).

CHART = {"cap", "labels", "vals", "fmt": usd|n|p100|r1, "tips", "before", "after_idx", "marks": [[i, text], …]} —
the same meaning as the demo's svg_bars() arguments (p100 values are already ×100)."""

from datetime import timedelta

from .fmt import D, back_w, cap, days_back, fd, fr, gone_w, p100, ver_of
from .series import day_series, idx_of_day, idx_of_week, rel_update, ret_weeks, un_weeks


def _num(v):
    return None if v is None else round(float(v), 4) + 0.0


def bars(labels, vals, fmt, cap, tips=None, before=None, marks=(), after_idx=None):
    """-> CHART, or None when there is nothing to draw (no bar has a value)."""
    if not vals or all(v is None for v in vals):
        return None
    return {"cap": cap, "labels": list(labels), "vals": [_num(v) for v in vals], "fmt": fmt,
            "tips": list(tips) if tips else None, "before": _num(before), "after_idx": after_idx,
            "marks": [[i, t] for i, t in marks if i is not None]}


def chart_for(ctx, r):
    """The chart of a feature's head row, or None."""
    aid, k = r["app"], r["kind"]
    rel_ = r.get("release") or rel_update(ctx, aid, r["started"], 3)
    rl = ver_of(rel_["label"]) if rel_ else None
    if rl == "App update":
        rl = "update"
    if k in ("ivt", "unit_drop", "kamai_drop", "kamai_up"):
        days = days_back(ctx.admob_till, 14)
        if k == "ivt":
            ser, fmt, cap = day_series(ctx, aid, "clicks", r["unit_id"]), "n", f"{r['unit']} · clicks/day"
            before = r["cb"]
        elif k == "unit_drop":
            ser, fmt, cap = day_series(ctx, aid, "rev", r["unit_id"]), "usd", f"{r['unit']} ad unit revenue · $/day"
            before = r["before"]
        else:
            ser, fmt, cap = day_series(ctx, aid, "kamai"), "usd", "App AdMob revenue · $/day"
            before = r["before"]
        vals = [ser.get(x) for x in days]
        si = idx_of_day(days, r["started"])
        ri = idx_of_day(days, rel_["date"]) if rel_ else None
        marks = [(si, "Started" + (f" · {rl}" if ri == si and rl else ""))]
        if ri is not None and ri != si and rl:
            marks.append((ri, rl))
        return bars([fd(ctx, x) for x in days], vals, fmt, f"{cap} · {fr(ctx, days[0], days[-1])}", before=before,
                    marks=marks, after_idx=si)
    if k == "rate":
        ua = ctx.uapp.get(aid) or {}
        dl = ua.get("daily") or {}
        st = D(dl.get("start"))
        days = days_back(ctx.ga4_till, 14)
        vals = []
        for x in days:
            i = (D(x) - st).days
            vals.append(dl["rate"][i] if 0 <= i < len(dl.get("rate") or []) else None)
        si = idx_of_day(days, r["started"])
        return bars([fd(ctx, x) for x in days], vals, "r1",
                    f"Uninstall rate (% of daily active users) · {fr(ctx, days[0], days[-1])}", before=r["before"],
                    marks=[(si, "Started")], after_idx=si)
    if k in ("cohort", "act_return", "impact"):
        if k == "cohort":
            wk = un_weeks(ctx, aid, r["n"], r["inst"][1])
            what = cap(gone_w(r["n"]))
        elif k == "act_return":
            N = int(r["metric"].split("d")[-1])
            wk = ret_weeks(ctx, aid, N, r["inst"][1])
            what = cap(back_w(N))
        else:
            rd = D(r["release"]["date"])
            if r["metric"] == "un_d0":
                lim, fn, what = ctx.ga4_till, (lambda e: un_weeks(ctx, aid, 0, e)), cap(gone_w(0))
            else:
                N = 1 if r["metric"] == "ret_d1" else 7
                lim, fn = ctx.ga4_till - timedelta(N), (lambda e, N=N: ret_weeks(ctx, aid, N, e))
                what = cap(back_w(N))
            e = rd + timedelta(6)
            while e + timedelta(7) <= lim:
                e += timedelta(7)
            wk = fn(e)
        wk = [w for i, w in enumerate(wk) if i == 0 or w["mature"]][:6][::-1]
        wk = [w for w in wk if w["n"] >= 30 and w["p"] is not None]
        if not wk:
            return None
        vals = [w["p"] * 100 for w in wk]
        tips = [f"Installs {fr(ctx, w['s'], w['e'])}: {round(w['n'] * w['p']):,} ({p100(w['p'])}%) · {w['n']:,} installs"
                for w in wk]
        si = idx_of_week(wk, r["started"])
        ri = idx_of_week(wk, rel_["date"]) if rel_ else None
        marks = [(si, "Started" + (f" · {rl}" if ri == si and rl else ""))]
        if ri is not None and ri != si and rl:
            marks.append((ri, rl))
        return bars([fd(ctx, w["s"]) for w in wk], vals, "p100",
                    f"{what} · % · install weeks {fr(ctx, wk[0]['s'], wk[-1]['e'])}", tips=tips,
                    before=r["before"] * 100, marks=marks, after_idx=si)
    return None


def kamai14(ctx, aid):
    """App kamai, 14 days, dotted line = the 7 days before's average."""
    ser = day_series(ctx, aid, "kamai")
    d14, p7 = ctx.d14, ctx.p7
    return bars([fd(ctx, x) for x in d14], [ser.get(x, 0) for x in d14], "usd",
                f"App AdMob revenue · $/day · {fr(ctx, d14[0], d14[-1])} (dotted = avg of {fr(ctx, p7[0], p7[-1])})",
                before=ctx.apps[aid]["kp7"], marks=[(7, "last 7 days")], after_idx=7)


def ads14(ctx, aid):
    """Google Ads spend, 14 days, dotted line = the 7 days before's average."""
    dl = (ctx.ro.get(ctx.apps[aid]["dname"]) or {}).get("daily") or {}
    d14, p7 = ctx.d14, ctx.p7
    return bars([fd(ctx, x) for x in d14], [dl.get(x, 0) / 1e6 for x in d14], "usd",
                f"Google Ads spend · $/day · {fr(ctx, d14[0], d14[-1])} (dotted = avg of {fr(ctx, p7[0], p7[-1])})",
                before=ctx.ads[aid]["spp"] or None, marks=[(7, "last 7 days")], after_idx=7)
