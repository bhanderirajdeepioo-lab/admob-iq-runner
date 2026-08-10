"""Baseline report — turns the ad-unit×country monthly rollup into the payload the UI shows:
for every placement (and each of its countries) the STANDARD RANGE + average of
CTR / match rate / show rate / eCPM across the months, the monthly trend (eCPM = the
"market rate"), and where the latest month sits vs that range (movement).

Range convention: the min→max of the MONTHLY AVERAGES (stable; a single odd day can't
blow it out). We also keep the widest daily extreme (min of monthly mins → max of monthly
maxes) so the UI can show "typical band" vs "ever seen". Nothing is excluded — every combo
gets a row; thin ones are LABELLED low_sample (impressions below a floor), never dropped.
"""

from . import metrics
from ..db import iter_monthly, daily_series, ACD_FIELDS

_METS = ("ctr", "match", "show", "ecpm")
LOW_SAMPLE_IMPR = 1000            # per-month impressions below this ⇒ flag (not exclude)
_GEO_ST = {"na": 0, "in": 0, "above": 1, "below": 2}   # status → int code for the compact geo file


def compact_geo(unit_geo):
    """Encode per-unit country rows as fixed-order arrays (~4x smaller) for baseline_geo.json:
      [country, months_n, rev, low, ctr_lo,ctr_hi,ctr_now,ctr_st,  match…,  show…,  ecpm…,  series]
    status codes: 0=in/na, 1=above, 2=below. Index 20 is the compact monthly series (or None) so the
    UI can recompute per-window ranges on drill; index 21 is the yesterday snapshot
    [ctr,match,show,ecpm,rev] (or None) for the culprit card's daily lens. Frontend decodes by order."""
    out = {}
    for uid, rows in unit_geo.items():
        arr = []
        for c in rows:
            r, l, st = c["range"], c["latest"], c["status"]
            row = [c["country"], c["months_n"], round(c["rev_total"]), 1 if c["low_sample"] else 0]
            for k in _METS:
                rg = r.get(k) or [None, None]
                row += [rg[0], rg[1], l.get(k), _GEO_ST.get(st.get(k), 0)]
            row.append(c.get("series"))            # index 20: monthly series for period recompute
            yd = c.get("yday")                     # index 21: yesterday snapshot [ctr,match,show,ecpm,rev] or None
            row.append([yd.get("ctr"), yd.get("match"), yd.get("show"), yd.get("ecpm"), yd.get("rev")] if yd else None)
            arr.append(row)
        out[uid] = arr
    return out


def _agg_month(cells):
    """Volume-weighted monthly averages + daily-extreme carry, from rollup cells that share a
    month (e.g. all countries of a unit in that month). Returns one synthetic monthly point."""
    s = {k: 0 for k in ("ad_requests", "matched_requests", "impressions", "clicks",
                         "estimated_earnings_micros", "days")}
    ext = {f"{m}_min": None for m in _METS}
    ext.update({f"{m}_max": None for m in _METS})
    for c in cells:
        for k in s:
            s[k] += c.get(k, 0) or 0
        for m in _METS:
            lo, hi = c.get(f"{m}_min"), c.get(f"{m}_max")
            if lo is not None:
                ext[f"{m}_min"] = lo if ext[f"{m}_min"] is None else min(ext[f"{m}_min"], lo)
            if hi is not None:
                ext[f"{m}_max"] = hi if ext[f"{m}_max"] is None else max(ext[f"{m}_max"], hi)
    impr = s["impressions"]
    avg = {
        "ctr": round(metrics.ctr(impr, s["clicks"]), 5),
        "match": round(metrics.match_rate(s["ad_requests"], s["matched_requests"]), 4),
        "show": round(metrics.show_rate(s["matched_requests"], impr), 4),
        "ecpm": round(metrics.ecpm(s["estimated_earnings_micros"], impr), 3),
    }
    return {"impr": impr, "rev": round(metrics.micros_to_currency(s["estimated_earnings_micros"]), 2),
            "avg": avg, "ext": ext}


def _series_stats(by_month):
    """by_month: {month: monthly-point}. The standard RANGE is min→max of the monthly avgs of the
    PRIOR months (all but the latest) — that is the 'normal' band the latest month is judged
    against, so a crashed/spiked latest month reads as out-of-range instead of silently widening
    its own range. `trend` still spans every month for the chart."""
    months = sorted(by_month)
    if not months:
        return None
    prior = months[:-1] if len(months) >= 2 else months     # baseline excludes the latest month
    rng, band, trend, avgs = {}, {}, {}, {}
    tot_impr = sum(by_month[m]["impr"] for m in months) or 1
    for k in _METS:
        vals = [by_month[m]["avg"][k] for m in prior if by_month[m]["impr"] > 0]
        if vals:
            rng[k] = [min(vals), max(vals)]
        lows = [by_month[m]["ext"][f"{k}_min"] for m in prior if by_month[m]["ext"][f"{k}_min"] is not None]
        highs = [by_month[m]["ext"][f"{k}_max"] for m in prior if by_month[m]["ext"][f"{k}_max"] is not None]
        if lows and highs:
            band[k] = [min(lows), max(highs)]
        trend[k] = [by_month[m]["avg"][k] for m in months]      # full series for the chart
        # volume-weighted overall average across ALL months
        avgs[k] = round(sum(by_month[m]["avg"][k] * by_month[m]["impr"] for m in months) / tot_impr,
                        5 if k == "ctr" else 4 if k in ("match", "show") else 3)
    latest = by_month[months[-1]]
    return {"months": months, "range": rng, "band": band, "trend": trend, "avg": avgs,
            "latest": {"month": months[-1], **latest["avg"]},
            "impr_total": sum(by_month[m]["impr"] for m in months),
            "rev_total": round(sum(by_month[m]["rev"] for m in months), 2),
            "months_n": len(months)}


GEO_SERIES_MONTHS = 13        # per-country series cap: covers 3m/6m/12m windows (All time uses the prebuilt range)
GEO_SERIES_TOP = 40           # only the top-N countries per unit (by revenue) carry a series — the tiny tail
                              # keeps its prebuilt all-time range (period recompute focuses on countries that matter)


def _series_from_agg(ser, cap=None):
    """Compact per-month series (already-aggregated monthly points) so the UI can recompute the
    standard range / latest / status / trend for ANY chosen window (3m / 6m / 12m / all) without a
    re-fetch. Short arrays keyed by metric + impressions + revenue per month. `cap` keeps only the
    most recent N months (used for the huge per-country geo file; units keep full history)."""
    ms = sorted(ser)
    if cap and len(ms) > cap:
        ms = ms[-cap:]
    return {"mo": ms,
            "ctr": [ser[m]["avg"]["ctr"] for m in ms],
            "match": [ser[m]["avg"]["match"] for m in ms],
            "show": [ser[m]["avg"]["show"] for m in ms],
            "ecpm": [ser[m]["avg"]["ecpm"] for m in ms],
            "impr": [ser[m]["impr"] for m in ms],
            "rev": [ser[m]["rev"] for m in ms]}


DAILY_MAX_DAYS = 403          # keep the full ~13-month daily history (covers the "all time" toggle)


def build_daily_series(network_rows, keep_ids=None):
    """Per-placement DAILY series for the placement-page chart, straight from the network report
    (already fetched hourly — this adds ZERO extra AdMob API load). One point per ad_unit×day:
    revenue, ad-requests and all four rates (CTR / match / show / eCPM), each DERIVED from the raw
    daily counts exactly like the monthly baseline, so daily and monthly line up. A rate is null on
    a day whose denominator is 0 (e.g. no impressions ⇒ no eCPM/CTR) — the chart shows a gap, never
    a fake 0. `keep_ids` (the active baseline placements) limits the file to reachable units.

    Output per unit: {d:[dates], rev, req, ctr, match, show, ecpm} — parallel arrays, dates ascending.
    Kept OUT of the always-loaded payloads; the UI lazy-fetches baseline_daily.json on first drill."""
    agg = {}          # unit_id -> date -> summed raw counts
    names = {}        # unit_id -> (unit_name, app_name)
    for r in network_rows:
        uid = r.get("ad_unit_id")
        day = r.get("report_date")
        if not uid or not day:
            continue
        if keep_ids is not None and uid not in keep_ids:
            continue
        d = agg.setdefault(uid, {})
        s = d.get(day)
        if s is None:
            s = d[day] = {"ad_requests": 0, "matched_requests": 0, "impressions": 0,
                          "clicks": 0, "estimated_earnings_micros": 0}
        for k in s:
            s[k] += r.get(k, 0) or 0
        if uid not in names:
            names[uid] = (r.get("unit_name"), r.get("app_name"))
    out = {}
    for uid, days in agg.items():
        ds = sorted(days)[-DAILY_MAX_DAYS:]
        rec = {"d": ds, "name": names.get(uid, (None, None))[0], "app": names.get(uid, (None, None))[1],
               "rev": [], "req": [], "ctr": [], "match": [], "show": [], "ecpm": []}
        for day in ds:
            s = days[day]
            impr = s["impressions"]
            rec["rev"].append(round(metrics.micros_to_currency(s["estimated_earnings_micros"]), 2))
            rec["req"].append(s["ad_requests"])
            rec["ctr"].append(round(metrics.ctr(impr, s["clicks"]), 5) if impr else None)
            rec["match"].append(round(metrics.match_rate(s["ad_requests"], s["matched_requests"]), 4)
                                if s["ad_requests"] else None)
            rec["show"].append(round(metrics.show_rate(s["matched_requests"], impr), 4)
                               if s["matched_requests"] else None)
            rec["ecpm"].append(round(metrics.ecpm(s["estimated_earnings_micros"], impr), 3) if impr else None)
        out[uid] = rec
    return out


def build_country_yday(acd):
    """Per-placement × country snapshot for the most recent COMPLETE day ('yesterday'), from the
    current-month daily file (acd — already fetched, so no extra AdMob call). Lets the culprit card
    show which countries broke their band *yesterday* (fresh) as an alternative to the monthly view.
    Returns (yday_date, {uid: {country: {ctr,match,show,ecpm,rev}}}); a rate is None if that day had
    no impressions (undefined), rev is always the day's earnings."""
    dates = acd.get("dates") or []
    if not dates:
        return "", {}
    yi = len(dates) - 2 if len(dates) >= 2 else len(dates) - 1     # last element is today (partial)
    yday = dates[yi]
    R = ACD_FIELDS.index("ad_requests") + 1
    M = ACD_FIELDS.index("matched_requests") + 1
    I = ACD_FIELDS.index("impressions") + 1
    C = ACD_FIELDS.index("clicks") + 1
    E = ACD_FIELDS.index("estimated_earnings_micros") + 1
    out = {}
    for uid, cc in (acd.get("data") or {}).items():
        cm = {}
        for c, arrs in cc.items():
            row = next((a for a in arrs if a and a[0] == yi), None)
            if not row:
                continue
            req, matched, impr, clicks, earn = row[R], row[M], row[I], row[C], row[E]
            cm[c] = {
                "ctr": round(metrics.ctr(impr, clicks), 5) if impr else None,
                "match": round(metrics.match_rate(req, matched), 4) if req else None,
                "show": round(metrics.show_rate(matched, impr), 4) if matched else None,
                "ecpm": round(metrics.ecpm(earn, impr), 3) if impr else None,
                "rev": round(metrics.micros_to_currency(earn or 0), 2),
            }
        if cm:
            out[uid] = cm
    return yday, out


def _status(latest_val, rng):
    """Where the latest month sits vs the standard range: below / in / above (with a small
    tolerance so a value right at the edge isn't flagged)."""
    if not rng or latest_val is None:
        return "na"
    lo, hi = rng
    span = (hi - lo) or (abs(hi) * 0.05 + 1e-9)
    if latest_val < lo - 0.05 * span:
        return "below"
    if latest_val > hi + 0.05 * span:
        return "above"
    return "in"


def build_baseline(acm, acd, *, active_since=None, top_countries=12):
    """Full baseline payload. `active_since` (a 'YYYY-MM' string) keeps only units whose LATEST
    month is >= it (focus the report on live placements); None = all. Per unit we ship the
    all-country baseline + its top `top_countries` geos by revenue (the long tail stays in
    storage, reachable on drill-down)."""
    rows = list(iter_monthly(acm))
    # Current (partial) month revenue per unit + per app, from the DAILY file. The monthly rollup
    # only holds COMPLETE months, so the current month is excluded from ranges/totals — but AdMob's
    # live lifetime number DOES include it. We ship it so the UI can show complete + current = AdMob.
    _ei = ACD_FIELDS.index("estimated_earnings_micros") + 1
    cur_unit, cur_app = {}, {}
    for uid, cc in (acd.get("data") or {}).items():
        tot = sum((r[_ei] or 0) for c in cc.values() for r in c)
        if tot:
            cur_unit[uid] = tot
            ap = (acd.get("units", {}).get(uid) or [None, None, None])[2] or "—"
            cur_app[ap] = cur_app.get(ap, 0) + tot
    # complete-months revenue + month coverage per app across ALL units (retired included → accurate
    # app total), plus the global data range for the "which months" label.
    app_rev_full, app_months, all_months = {}, {}, set()
    for r in rows:
        ap = r.get("app_name") or "—"
        app_rev_full[ap] = app_rev_full.get(ap, 0) + (r.get("estimated_earnings_micros", 0) or 0)
        app_months.setdefault(ap, set()).add(r["month"])
        all_months.add(r["month"])
    by_unit = {}
    for r in rows:
        by_unit.setdefault(r["ad_unit_id"], []).append(r)
    # yesterday (last complete day) per placement × country — for the culprit card's daily lens
    yday_date, yday_map = build_country_yday(acd)

    def _country_row(c, cst):
        """Slim country baseline row: only what the UI table shows (range → now + status)."""
        return {"country": c, "months_n": cst["months_n"], "range": cst["range"],
                "latest": cst["latest"], "rev_total": cst["rev_total"],
                "low_sample": (cst["impr_total"] / max(1, cst["months_n"])) < LOW_SAMPLE_IMPR,
                "status": {k: _status(cst["latest"].get(k), cst["range"].get(k)) for k in _METS}}

    def _country_list(country_month_cells, with_series=False):
        """Country baseline rows for a {country: {month: [cells]}} map (app-level A + unit-level).
        `with_series` attaches the (capped) monthly series to the TOP `GEO_SERIES_TOP` countries by
        revenue only — the tiny tail keeps its prebuilt all-time range, so the geo file stays lean."""
        tmp = []
        for c, months_cells in country_month_cells.items():
            ser = {m: _agg_month(cells) for m, cells in months_cells.items()}
            cst = _series_stats(ser)
            if cst:
                tmp.append((_country_row(c, cst), ser))
        tmp.sort(key=lambda x: -x[0]["rev_total"])
        if with_series:
            for i, (row, ser) in enumerate(tmp):
                if i < GEO_SERIES_TOP:
                    row["series"] = _series_from_agg(ser, cap=GEO_SERIES_MONTHS)
        return [row for row, _ in tmp]

    units_out = []
    unit_geo = {}             # uid -> [all-country baseline rows]  (shipped separately, lazy-loaded on drill)
    market_by_month = {}
    market_by_app = {}
    app_country = {}          # {app: {country: {month: [cells across all its units]}}} for the app-level (A) view
    for uid, urows in by_unit.items():
        by_month_all, by_country = {}, {}
        for r in urows:
            by_month_all.setdefault(r["month"], []).append(r)
            by_country.setdefault(r["country"], {}).setdefault(r["month"], []).append(r)
            market_by_month.setdefault(r["month"], []).append(r)
            app = r.get("app_name") or "—"
            market_by_app.setdefault(app, {}).setdefault(r["month"], []).append(r)
            app_country.setdefault(app, {}).setdefault(r["country"], {}).setdefault(r["month"], []).append(r)
        unit_ser = {m: _agg_month(cells) for m, cells in by_month_all.items()}
        st = _series_stats(unit_ser)
        if not st:
            continue
        if active_since and st["latest"]["month"] < active_since:
            continue
        meta = acm.get("units", {}).get(uid) or [None, None, None, "USD"]
        countries = _country_list(by_country, with_series=True)   # ALL countries + series for period recompute
        ym = yday_map.get(uid, {})
        for cr in countries:
            cr["yday"] = ym.get(cr["country"])                    # yesterday snapshot (or None) per country
        unit_geo[uid] = countries
        units_out.append({
            "id": uid, "app_id": meta[0], "name": meta[1] or uid.split("/")[-1],
            "app": meta[2], "months_n": st["months_n"], "range": st["range"], "latest": st["latest"],
            "rev_total": st["rev_total"],
            "countries_n": len(countries),
            "low_sample": (st["impr_total"] / max(1, st["months_n"])) < LOW_SAMPLE_IMPR,
            "status": {k: _status(st["latest"].get(k), st["range"].get(k)) for k in _METS},
            "series": _series_from_agg(unit_ser),
            "cur_rev": round(metrics.micros_to_currency(cur_unit.get(uid, 0)), 2),   # current partial month
        })
    units_out.sort(key=lambda x: -x["rev_total"])

    # market = monthly trend (volume-weighted) — "what eCPM is doing". Portfolio-wide, plus a
    # per-app version so the tab's App filter shows that app's own market trend.
    def _market(by_mo):
        ser = {m: _agg_month(cells) for m, cells in by_mo.items()}
        ms = sorted(ser)
        return {"months": ms,
                "ecpm": [ser[m]["avg"]["ecpm"] for m in ms],
                "ctr": [ser[m]["avg"]["ctr"] for m in ms],
                "match": [ser[m]["avg"]["match"] for m in ms],
                "show": [ser[m]["avg"]["show"] for m in ms],
                "revenue": [ser[m]["rev"] for m in ms]}
    active_apps = {u["app"] for u in units_out}          # only the apps actually shown in the report
    # per-app country-wise view (option A): this app's countries, aggregated across ALL its ad-units
    apps_out = {}
    for a, cm in app_country.items():
        if a not in active_apps:
            continue
        cl = _country_list(cm)
        apps_out[a] = {"by_country": cl, "countries_n": len(cl)}
    # per-app revenue reconciliation: complete-months total (all units) + current partial month
    cur_dates = acd.get("dates") or []
    apps_meta = {a: {"rev": round(metrics.micros_to_currency(app_rev_full.get(a, 0)), 2),
                     "cur": round(metrics.micros_to_currency(cur_app.get(a, 0)), 2),
                     "first": (min(app_months[a]) if app_months.get(a) else ""),
                     "last": (max(app_months[a]) if app_months.get(a) else ""),
                     "n": len(app_months.get(a, ()))}
                 for a in active_apps}
    data_range = {"first": (min(all_months) if all_months else ""),
                  "last": (max(all_months) if all_months else ""),
                  "months_n": len(all_months),
                  "current_month": acd.get("month", ""),
                  "current_end": (cur_dates[-1] if cur_dates else ""),
                  "yday_date": yday_date,           # last complete day — the culprit card's 'yesterday'
                  "cur_rev_total": round(metrics.micros_to_currency(sum(cur_app.values())), 2)}
    return {"units": units_out, "market": _market(market_by_month),
            "market_by_app": {a: _market(bm) for a, bm in market_by_app.items() if a in active_apps},
            "apps": apps_out,                 # option A: per-app country-wise view (small)
            "apps_meta": apps_meta,           # per-app revenue reconciliation (complete + current)
            "data_range": data_range,         # which months the numbers cover + current partial month
            "unit_geo": unit_geo,             # per-ad-unit ALL countries → build_static ships as baseline_geo.json
            "current_month": acd.get("month", ""),
            "low_sample_impr": LOW_SAMPLE_IMPR}
