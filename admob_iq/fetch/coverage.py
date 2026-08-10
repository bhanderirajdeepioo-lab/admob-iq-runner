"""Coverage verification — the QA safety net for every AdMob pull.

The 100k row cap is the one place data can silently disappear. `_fetch_range` now
splits requests so that never happens, and THIS module is the independent check that
proves it: after a pull we confirm the rows actually cover the whole window with no
holes. It catches (a) whole missing days and (b) days with far fewer rows than their
neighbours — the exact signature of a request that overflowed and got truncated.

Pure functions over already-fetched rows: no API calls, trivially testable.
"""

from datetime import date, timedelta
from statistics import median


def _dstr(v):
    """Normalize a report_date (date obj or 'YYYY-MM-DD' string) to a string."""
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:10] if v else ""


def _expected_days(start, end):
    days, d = [], start
    while d <= end:
        days.append(d.isoformat())
        d += timedelta(days=1)
    return days


def verify_coverage(rows, start: date, end: date, *, low_ratio: float = 0.10):
    """Check that `rows` cover every day in [start, end] without truncation holes.

    Returns a report dict:
      ok            – True when no missing days and no suspiciously-thin days
      covered_days  – distinct days that actually have rows
      expected_days – days in the requested window
      missing_days  – days in the window with ZERO rows (hard gap)
      thin_days     – days whose row count is < low_ratio * median (likely truncated/partial)
      per_day_median– median rows/day (context)
      flags         – human-readable warnings (empty when ok)

    `low_ratio` guards against false alarms from a normal partial 'today'; the caller
    can exclude the live day before verifying, or accept one thin day at the tail.
    """
    per_day = {}
    for r in rows:
        d = _dstr(r.get("report_date"))
        if d:
            per_day[d] = per_day.get(d, 0) + 1

    expected = _expected_days(start, end)
    covered = sorted(per_day)
    missing = [d for d in expected if d not in per_day]

    counts = [per_day[d] for d in covered]
    med = median(counts) if counts else 0
    thin = [d for d in covered if med and per_day[d] < low_ratio * med]

    flags = []
    if missing:
        flags.append(f"{len(missing)} day(s) with NO rows in [{start}..{end}] "
                     f"(first gap {missing[0]}) — a fetch hole, not real history")
    if thin:
        flags.append(f"{len(thin)} day(s) with <{int(low_ratio*100)}% of the median "
                     f"({med:.0f}) rows — possible truncation/partial (e.g. {thin[0]})")

    return {
        "ok": not missing and not thin,
        "covered_days": len(covered),
        "expected_days": len(expected),
        "missing_days": missing,
        "thin_days": thin,
        "per_day_median": med,
        "flags": flags,
    }


def verify_entity_spans(rows, *, entity_key: str, min_active_days: int = 3):
    """Per-entity coverage summary (e.g. entity_key='country' or 'ad_unit_id').

    This does NOT flag short spans as errors — a placement or geo can legitimately be
    new or dormant. It returns each entity's date span so the caller (and a human) can
    eyeball the classic truncation tell: some entities spanning the full history while
    others of similar size are mysteriously clipped to only recent dates.
    """
    spans = {}
    for r in rows:
        k = r.get(entity_key)
        d = _dstr(r.get("report_date"))
        if not k or not d:
            continue
        s = spans.setdefault(k, {"first": d, "last": d, "days": set()})
        s["first"] = min(s["first"], d)
        s["last"] = max(s["last"], d)
        s["days"].add(d)
    out = {}
    for k, s in spans.items():
        out[k] = {"first": s["first"], "last": s["last"], "days": len(s["days"])}
    # entities active (>= min_active_days) but whose window is clipped well short of the
    # widest entity's window are the ones worth a human look.
    widest = max((v["days"] for v in out.values()), default=0)
    suspects = sorted(
        (k for k, v in out.items()
         if v["days"] >= min_active_days and widest and v["days"] < 0.5 * widest),
        key=lambda k: out[k]["days"],
    )
    return {"spans": out, "widest_days": widest, "clipped_suspects": suspects}
