"""Ad-unit × country baseline store: split daily rows into monthly rollups (history)
and current-month daily (recent), so the whole thing fits a free git host yet keeps
full analytical power.

  * COMPLETED months  -> one rollup row per (account, app, ad_unit, country, month):
      month sums (for volume-weighted averages) + the daily MIN/MAX of each metric
      (the "standard range" the user wants) + day count + total impressions (so the
      UI can label low-sample combos WITHOUT ever excluding them).
  * CURRENT month      -> kept as raw daily rows for anomaly detection + day-level drill.

Streaming: `RollupAccumulator.add(row)` folds each row in as it arrives, so an all-time
backfill (millions of rows) never has to be held in memory — only the bounded aggregate
(~combos × months) and the current month's daily rows are retained.

Coverage guard: a month is only rolled up when the FETCH WINDOW actually covered it
(window_start <= month's first day). A short ongoing window that clips an old month is
skipped — its full rollup already exists from the backfill — so a partial pull can never
corrupt a month's range. The account's genuinely-partial FIRST month is still included
(the window covers it; the data just starts mid-month).
"""

from . import metrics

_METS = ("ctr", "match", "show", "ecpm")


def _daily_metrics(r):
    return (
        metrics.ctr(r["impressions"], r["clicks"]),
        metrics.match_rate(r["ad_requests"], r["matched_requests"]),
        metrics.show_rate(r["matched_requests"], r["impressions"]),
        metrics.ecpm(r["estimated_earnings_micros"], r["impressions"]),
    )


class RollupAccumulator:
    """Fold ad-unit×country daily rows into monthly aggregates as they stream in."""

    def __init__(self, today):
        self.cur_month = today.isoformat()[:7]
        self.agg = {}
        self.current_daily = []

    def add(self, r):
        d = str(r.get("report_date"))[:10]
        if not d:
            return
        mo = d[:7]
        if mo >= self.cur_month:            # current month (or future-dated) -> keep raw daily
            self.current_daily.append(r)
            return
        key = (r.get("account_id"), r.get("app_id"), r.get("ad_unit_id"),
               r.get("country") or "All", mo)
        a = self.agg.get(key)
        if a is None:
            a = self.agg[key] = dict(
                account_id=r.get("account_id"), app_id=r.get("app_id"),
                app_name=r.get("app_name"), ad_unit_id=r.get("ad_unit_id"),
                unit_name=r.get("unit_name"), country=r.get("country") or "All",
                month=mo, days=0, ad_requests=0, matched_requests=0, impressions=0,
                clicks=0, estimated_earnings_micros=0,
                currency_code=r.get("currency_code", "USD"),
                **{f"{m}_min": None for m in _METS}, **{f"{m}_max": None for m in _METS},
            )
        a["days"] += 1
        a["ad_requests"] += r.get("ad_requests", 0)
        a["matched_requests"] += r.get("matched_requests", 0)
        a["impressions"] += r.get("impressions", 0)
        a["clicks"] += r.get("clicks", 0)
        a["estimated_earnings_micros"] += r.get("estimated_earnings_micros", 0)
        for m, val in zip(_METS, _daily_metrics(r)):
            lo, hi = a[f"{m}_min"], a[f"{m}_max"]
            a[f"{m}_min"] = val if lo is None else min(lo, val)
            a[f"{m}_max"] = val if hi is None else max(hi, val)

    def finish(self, window_start=None):
        """Return (monthly_rollups, current_month_daily). `window_start` (a date) drops any
        month the fetch window began after (already fully rolled up from a prior run)."""
        ws = window_start.isoformat() if window_start else None
        rollups = []
        for (acct, app, unit, country, mo), a in self.agg.items():
            if ws and ws > f"{mo}-01":       # window clipped this month -> its full rollup exists already
                continue
            rollups.append(_finish(a))
        return rollups, self.current_daily


def rollup_adunit_country(daily_rows, today, window_start=None):
    """Convenience wrapper over RollupAccumulator for callers/tests holding a full list."""
    acc = RollupAccumulator(today)
    for r in daily_rows:
        acc.add(r)
    return acc.finish(window_start)


def _finish(a):
    """Round the range/avg fields for a compact, JSON-friendly rollup row."""
    impr = a["impressions"]
    a["ctr_avg"] = round(metrics.ctr(impr, a["clicks"]), 5)
    a["match_avg"] = round(metrics.match_rate(a["ad_requests"], a["matched_requests"]), 4)
    a["show_avg"] = round(metrics.show_rate(a["matched_requests"], impr), 4)
    a["ecpm_avg"] = round(metrics.ecpm(a["estimated_earnings_micros"], impr), 3)
    for m in _METS:
        for b in ("min", "max"):
            v = a[f"{m}_{b}"]
            if v is not None:
                a[f"{m}_{b}"] = round(v, 5 if m == "ctr" else 4 if m in ("match", "show") else 3)
    return a
