"""Daily App Review — the "ads" feature follows the 📉 CPI vs eCPM alarm (one verdict everywhere: the Review card, the
hub's Marketing ROAS card and the CPI screen never disagree).

The verdict is this build's pointer, dashboard["cpi"] (admob_iq.cpi_build — the step runs BEFORE the review in
build_static): per app id its default-view status (st: alarm / watch / fixed / ok / new / paused = Last 14 days ending
the pointer's data day t), since, to (a Fixed alarm's last day), open episodes, the normal per family (nrm) and the
money lost (lost). The "now" numbers are the CPI screen's own: ratio of sums over the same 14 days from the same
dashboard keys (roas.by_app daily / installs_daily / convval_day1_daily, placements), as its sums() reads them. An app
without a pointer row (no Google Ads spend) keeps the 7-vs-7 rule in rows._ads_row."""

from datetime import timedelta

from .fmt import D, fd, fr

# the pointer's status → the Review's state (its own words: red Worse · amber Watch · green Better · normal · wait
# Too early · na N/A)
TIER = {"alarm": "red", "watch": "amber", "fixed": "green", "ok": "normal", "new": "wait", "paused": "na"}
WORD = {"alarm": "Alarm", "watch": "Watch", "fixed": "Fixed"}
# (never "D0" / "CPI vs eCPM" in a Review text: the page reads \bD<n>\b as an uninstall day and eCPM as "ad rate" —
# smpCompat; "Day-0 ROAS" is the CPI screen's D0 ROAS)
FAMW = {"CPI": "CPI", "ECPM": "eCPM", "ROAS_G": "Day-0 ROAS"}
OPW = {"SUDDEN": "Sudden step", "DRIFT": "Slow drift", "ABSOLUTE": "Below the usual"}
FAMS = ("CPI", "ECPM", "ROAS_G")
WIN = 14                       # the CPI screen's default view: Last 14 days ending t


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def pointer(db, apps):
    """dashboard["cpi"] → ({app id: pointer row} for the review's apps, its data day t) — ({}, None) when the pointer
    is missing or not the v1 shape (the ads feature then keeps its 7-vs-7 rule for every app)."""
    p = db.get("cpi") if isinstance(db, dict) else None
    if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("apps"), dict):
        return {}, None
    try:
        t = D(p.get("t"))
    except (TypeError, ValueError):
        return {}, None
    if t is None:
        return {}, None
    rows = {k: v for k, v in p["apps"].items()
            if k in apps and isinstance(v, dict) and v.get("st") in TIER}
    return rows, t


def span(t):
    """The default view's [lo, t] (dates)."""
    return t - timedelta(WIN - 1), t


def now3(ctx, a, lo, hi):
    """{CPI (₹), ECPM ($), ROAS_G} over [lo, hi] — the CPI screen's sums(): spend in ₹ ÷ Google Ads installs, AdMob
    earnings ÷ impressions × 1000 (every placement row of the app), Google's D0 value ÷ spend (the days ≤ t only:
    hi is t here). None without volume or without the ₹ rate."""
    db = ctx.db
    e = ctx.ro.get(a["dname"]) or {}
    los, his = lo.isoformat(), hi.isoformat()
    roas = db.get("roas") if isinstance(db.get("roas"), dict) else {}
    fx = (roas.get("fx") or {}).get("INR") if isinstance(roas.get("fx"), dict) else None
    cur = db.get("currency") or "USD"
    usd_inr = db.get("usd_inr")

    def inr(v):                                    # ₹ of a micros amount in the dashboard's base currency
        if cur == "INR":
            return v / 1e6
        if _num(fx) and fx > 0:
            return v / 1e6 / fx
        if _num(usd_inr) and usd_inr > 0:
            return v / 1e6 * usd_inr
        return None

    one, ins, cv = e.get("daily") or {}, e.get("installs_daily") or {}, e.get("convval_day1_daily") or {}
    spi, n, sp1, v1, rate_ok = 0.0, 0.0, 0.0, 0.0, True
    for x, v in one.items():
        if not (los <= x <= his):
            continue
        v = float(v or 0)
        sp1 += v
        v1 += float(cv.get(x) or 0) * 1e6
        i = inr(v)
        if i is None:
            rate_ok = False
        else:
            spi += i
        n += float(ins.get(x) or 0)
    rev, imp = 0.0, 0.0
    for q in db.get("placements") or []:
        if not isinstance(q, dict) or q.get("app") != a["dname"]:
            continue
        for r in q.get("daily") or []:
            if los <= str(r[0])[:10] <= his:
                rev += float(r[1] or 0) / 1e6
                imp += float(r[2] or 0)
    return {"CPI": spi / n if (rate_ok and n > 0 and spi > 0) else None,
            "ECPM": rev / imp * 1000 if imp > 0 else None,
            "ROAS_G": v1 / sp1 if sp1 > 0 else None}


def fmt(f, v):
    """As the CPI screen prints it (₹ view for CPI: judged in ₹, FX-free)."""
    if not _num(v):
        return "—"
    if f == "CPI":
        return "₹" + (f"{v:.2f}" if v < 10 else f"{v:.1f}")
    if f == "ECPM":
        return f"${v:.2f}"
    return f"{v * 100:.1f}%"


def fp(r):
    """The CPI screen's move: +12% / −8% / ±0%."""
    if not _num(r):
        return "—"
    return ("+" if r > 0.0005 else "−" if r < -0.0005 else "±") + f"{round(abs(r) * 100)}%"


def move(f, now, nrm):
    n, v = nrm.get(f), now.get(f)
    return v / n - 1 if (_num(n) and n and _num(v)) else None


def moves(now, nrm, first=None):
    """'Day-0 ROAS 40.0% → 28.5%, CPI ₹20.0 → ₹26.0' — normal → now, the alarm's family first, then CPI and Day-0 ROAS
    (the pair the alarm money is about; eCPM only when it is the alarm's)."""
    order = [first] if first in FAMS else []
    order += [f for f in ("CPI", "ROAS_G") if f not in order]
    out = [f"{FAMW[f]} {fmt(f, nrm[f])} → {fmt(f, now[f])}" for f in order if _num(nrm.get(f)) and _num(now.get(f))]
    return ", ".join(out)


def levels(now, nrm):
    """'CPI ₹20.5 (+2%) · eCPM $6.00 (−1%) · Day-0 ROAS 39.5% (−1%)' — the hub 📉 card's numbers."""
    out = []
    for f in FAMS:
        d = move(f, now, nrm)
        out.append(f"{FAMW[f]} {fmt(f, now.get(f))}" + (f" ({fp(d)})" if d is not None else ""))
    return " · ".join(out)


def episode(c):
    """The open episode behind an Alarm / Watch: of the pointer's open ones with that tier, the one whose change start
    is the row's since (else the earliest) → [fam, opener, tier, c, opened, base] or None."""
    tier = {"alarm": "ALERT", "watch": "WATCH"}.get(c.get("st"))
    eps = [x for x in c.get("open") or [] if isinstance(x, list) and len(x) >= 5 and x[2] == tier]
    if not eps:
        return None
    return next((x for x in eps if x[3] == c.get("since")), min(eps, key=lambda x: str(x[3])))


def fact(ctx, c, now, nrm, ep):
    """The feature's one line for Alarm / Watch / Fixed."""
    st = c["st"]
    since, to = D(c.get("since")), D(c.get("to"))
    nums = moves(now, nrm, ep[0] if ep else None)
    if st == "fixed":
        when = fr(ctx, since, to) if (since and to) else (f"since {fd(ctx, since)}" if since else "")
        head = "Fixed" + (f" (alarm {when} is over)" if when else " (alarm is over)")
        return head + (f": {nums}" if nums else "")
    why = f" ({OPW.get(ep[1], 'Change')} in {FAMW.get(ep[0], ep[0])})" if ep else ""
    return f"{WORD[st]}{why}" + (f": {nums}" if nums else "") + (f", since {fd(ctx, since)}" if since else "")


def line(ctx, c, now, nrm, t):
    """(state, line) for OK / New / Paused (no row drives the feature)."""
    st = c["st"]
    lo, hi = span(t)
    if st in WORD:                                 # (Alarm / Watch / Fixed always come as a row: rows._cpx_row)
        return "nodata", "📉 CPI screen ka data padh nahi paye"
    if st == "new":
        return "wait", "⏳ Too early — 📉 CPI screen: is app ka normal abhi nahi bana (spend naya hai)"
    if st == "paused":
        return "na", f"Google Ads spend paused (no spend {fr(ctx, t - timedelta(2), t)}) · 📉 CPI screen"
    return "normal", f"📉 CPI screen: OK · {levels(now, nrm)} ({fr(ctx, lo, hi)})"
