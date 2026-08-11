"""QA for the universal safe-fetch layer (Step 1).

Proves the 100k-cap is never allowed to silently drop data:
  * a wide window that overflows is split by DATE until every chunk fits, and the
    UNION of all chunks is the COMPLETE row set (nothing lost);
  * a single day that still overflows is split by APP;
  * a slice that cannot be split further is RECORDED in client.truncations (never silent);
  * verify_coverage() independently catches missing/thin days.

We stub _run_report so no Google creds / network are needed — it simulates AdMob's
behaviour exactly: it returns the footer's true matchingRowCount even when the streamed
rows are truncated at the cap.
"""

from datetime import date, timedelta

from admob_iq.fetch.admob_client import AdMobClient
from admob_iq.fetch.coverage import verify_coverage, verify_entity_spans


APPS = ["app-A", "app-B"]


def _make_client(cap, rows_per_app_day):
    """AdMobClient wired with a fake AdMob backend. `rows_per_app_day` rows exist per
    (app, day); a request returns min(cap, true) of them plus the TRUE count as mrc."""
    c = AdMobClient("pub-x", "cid", "csec", "rtok")
    c.MAX_ROWS = cap
    calls = {"n": 0}

    def fake_run_report(method, spec):
        calls["n"] += 1
        rs = spec["reportSpec"]
        s = rs["dateRange"]["startDate"]; e = rs["dateRange"]["endDate"]
        start = date(s["year"], s["month"], s["day"])
        end = date(e["year"], e["month"], e["day"])
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        # APP-only probe (used by _app_ids_for): one row per app for the day
        if rs["dimensions"] == ["APP"]:
            rows = [{"app_id": a, "report_date": start} for a in APPS]
            return rows, len(rows)
        # which apps are in scope (a dimension filter narrows to one)
        apps = APPS
        for f in rs.get("dimensionFilters", []):
            if f.get("dimension") == "APP":
                apps = f["matchesAny"]["values"]
        # the TRUE, complete row set for this query (day-major so truncation drops later days)
        true_rows = []
        for d in days:
            for a in apps:
                for u in range(rows_per_app_day):
                    true_rows.append({"app_id": a, "report_date": d, "ad_unit_id": f"{a}/u{u}"})
        # AdMob CAPS matchingRowCount at maxReportRows — so a truncated request reports mrc==cap,
        # NOT the true total. This is the real behaviour that silently truncated the report; the
        # splitter must detect it from len(rows) hitting the cap, not from mrc.
        mrc = min(cap, len(true_rows))
        return true_rows[:cap], mrc

    c._run_report = fake_run_report
    c._calls = calls
    return c


def test_wide_window_splits_by_date_and_loses_nothing():
    # 6 days x 2 apps x 30 = 360 true rows, cap 100 -> must split by date repeatedly
    c = _make_client(cap=100, rows_per_app_day=30)
    start, end = date(2026, 1, 1), date(2026, 1, 6)
    got = list(c._fetch_range("networkReport", start, end,
                              ["DATE", "APP", "AD_UNIT"], ["IMPRESSIONS"]))
    assert len(got) == 6 * 2 * 30                      # COMPLETE — nothing dropped
    assert {r["report_date"] for r in got} == {start + timedelta(days=i) for i in range(6)}
    assert not c.truncations                           # everything fit after splitting


def test_high_cardinality_inner_dim_not_truncated():
    # THE regression for the real bug: a wide window truncates the later values of a
    # high-cardinality inner dimension (there it was country, alphabetically) while mrc==cap
    # hides it. Splitting by date must recover EVERY value, losing nothing.
    c = _make_client(cap=100, rows_per_app_day=40)     # 40 inner values per app-day
    start, end = date(2026, 1, 1), date(2026, 1, 10)
    got = list(c._fetch_range("networkReport", start, end,
                              ["DATE", "APP", "AD_UNIT"], ["IMPRESSIONS"]))
    inner = {r["ad_unit_id"] for r in got}
    expected = {f"{a}/u{u}" for a in APPS for u in range(40)}
    assert inner == expected                            # no inner value dropped
    assert len(got) == 10 * 2 * 40 and not c.truncations


def test_single_day_over_cap_splits_by_app():
    # one day, 2 apps x 70 = 140 rows > cap 100; per app 70 < cap -> APP split saves it
    c = _make_client(cap=100, rows_per_app_day=70)
    day = date(2026, 3, 10)
    got = list(c._fetch_range("networkReport", day, day,
                              ["DATE", "APP", "AD_UNIT"], ["IMPRESSIONS"]))
    assert len(got) == 2 * 70                           # both apps fully pulled
    assert {r["app_id"] for r in got} == set(APPS)
    assert not c.truncations


def test_unsplittable_slice_is_recorded_not_silent():
    # even ONE app-day (500) exceeds cap 100 and there is no more to split -> must be recorded
    c = _make_client(cap=100, rows_per_app_day=500)
    day = date(2026, 4, 1)
    got = list(c._fetch_range("networkReport", day, day,
                              ["DATE", "APP", "AD_UNIT"], ["IMPRESSIONS"]))
    assert c.truncations, "an unsplittable over-cap slice must be recorded"
    assert all(t["rows"] >= c.MAX_ROWS for t in c.truncations)   # recorded by rows-hit-cap
    assert len(got) > 0                                 # yields the partial rather than nothing


def test_verify_coverage_flags_missing_and_thin_days():
    base = date(2026, 5, 1)
    rows = []
    for i in range(5):
        n = 100 if i != 3 else 3                        # day index 3 is thin (truncation tell)
        rows += [{"report_date": base + timedelta(days=i), "country": "US"} for _ in range(n)]
    # drop day index 2 entirely -> a hard gap
    rows = [r for r in rows if r["report_date"] != base + timedelta(days=2)]
    rep = verify_coverage(rows, base, base + timedelta(days=4))
    assert not rep["ok"]
    assert (base + timedelta(days=2)).isoformat() in rep["missing_days"]
    assert (base + timedelta(days=3)).isoformat() in rep["thin_days"]


def test_verify_coverage_passes_on_complete_pull():
    base = date(2026, 6, 1)
    rows = []
    for i in range(7):
        rows += [{"report_date": base + timedelta(days=i)} for _ in range(50)]
    rep = verify_coverage(rows, base, base + timedelta(days=6))
    assert rep["ok"] and not rep["flags"]
    assert rep["covered_days"] == 7 and not rep["missing_days"]


def test_verify_entity_spans_surfaces_clipped_geo():
    # US spans 20 days, IN only 4 -> IN is a clipped suspect (classic truncation signature)
    base = date(2026, 2, 1)
    rows = []
    for i in range(20):
        rows.append({"report_date": base + timedelta(days=i), "country": "US"})
    for i in range(4):
        rows.append({"report_date": base + timedelta(days=i), "country": "IN"})
    rep = verify_entity_spans(rows, entity_key="country")
    assert rep["widest_days"] == 20
    assert "IN" in rep["clipped_suspects"] and "US" not in rep["clipped_suspects"]
