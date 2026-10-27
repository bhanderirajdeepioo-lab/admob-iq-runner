"""Google Ads D0 ("D0 rev": the value of conversions within 24 h of the click — the day-1 lag bucket) FIXED once
complete (owner: "fix D0 ye panel me", Google Ads reports ~3-4 h late). Click date X (the account's time zone) is
final from (X+2 00:00 local) + GADS_D0_LAG_HOURS on (google_ads.d0_final); fetch_app_spend says which dates are final
for its read (and whether every asked account answered the day-1 query); merge_spend keeps a fixed date's number for
good, measures how far Google's later number drifts (a percentage only), and logs counts only; build_roas carries
"d0" to the page; the per-campaign store compares day-1 only on the days not fixed yet. Frontend: the Overview
"Revenue by app" table's "D0 rev" column (number, D0 ROAS = Σ D0 ÷ Σ one-rate spend, "⏳ filling" + the Hinglish
tooltip) run for real by tests/roas_fx_frontend.js. Every name, id, rate and amount is SYNTHETIC; the expected
numbers are worked out by hand below."""

import json
import os
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.build_static import _spend_daily_dated, _spend_to_usd
from admob_iq.engine.roas import build_roas
from admob_iq.fetch import gads_campaign_day as gcd
from admob_iq.fetch import google_ads
from tests.gads_fake import A1, A2, A3, SETTINGS, TOK, FakeAds
from tests.test_roas_fx_dated import CATALOG, DAYS, IDS, NOW, SERIES, TODAY, _dash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
TAG = re.compile(r"<[^>]*>")
IST, LA = {"tz": "Asia/Calcutta"}, {"tz": "America/Los_Angeles"}
LINE = re.compile(r"^roas: D0 fixed till (\d{4}-\d{2}-\d{2}|none) · \d+ store-days fixed this run"
                  r"( · \d+ store-days still open)?( \(day-1 read incomplete: not moved\))?$")


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _lag(monkeypatch):
    monkeypatch.delenv("GADS_D0_LAG_HOURS", raising=False)


# ── 1. when a click date's D0 is final ────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("acc, boundary", [
    (IST, "2026-01-02T22:30"),        # 1 Jan's last click: 24 h till 3 Jan 00:00 IST (= 2 Jan 18:30 UTC) + 4 h
    (LA, "2026-01-03T12:00"),         # 3 Jan 00:00 PST (UTC−8) = 08:00 UTC + 4 h
    ({}, "2026-01-03T16:00"),         # no time zone → UTC−12 (the latest-ending day): 3 Jan 12:00 UTC + 4 h
    ({"tz": "Not/AZone"}, "2026-01-03T16:00"),     # a zone name nobody knows → the same conservative zone
])
def test_final_till_one_minute_before_and_after_the_boundary(acc, boundary):
    b = utc(boundary)
    before = google_ads.d0_final([acc], b - timedelta(minutes=1))
    after = google_ads.d0_final([acc], b + timedelta(minutes=1))
    assert before["final_till"] == "2025-12-31" and after["final_till"] == "2026-01-01"
    assert google_ads.d0_final([acc], b)["final_till"] == "2026-01-01"          # from the boundary on
    assert before["next_fix_utc"] == b.strftime("%Y-%m-%dT%H:%M:%SZ")             # the moment it moves on
    assert after["next_fix_utc"] == (b + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert before["lag_h"] == after["lag_h"] == 4


def test_summer_time_is_the_zones_own():
    b = utc("2026-07-03T11:00")                       # 3 Jul 00:00 PDT (UTC−7) = 07:00 UTC + 4 h
    assert google_ads.d0_final([LA], b - timedelta(minutes=1))["final_till"] == "2026-06-30"
    assert google_ads.d0_final([LA], b + timedelta(minutes=1))["final_till"] == "2026-07-01"


@pytest.mark.parametrize("acc, x, boundary", [
    # 7 Mar's last click (23:59 PST): its 24 h end 9 Mar 08:00 UTC (01:00 PDT — 8 Mar has 23 h), not 07:00 UTC + 4 h
    (LA, "2026-03-07", "2026-03-09T12:00"),
    # Paris, 28 Mar: 29 Mar 00:00 CET = 28 Mar 23:00 UTC + 24 h = 29 Mar 23:00 UTC (01:00 CEST) + 4 h
    ({"tz": "Europe/Paris"}, "2026-03-28", "2026-03-30T03:00"),
    # summer time ending (a 25-hour day after it): x+2 00:00 local is the later one, as before — 1 Nov 00:00 PDT = 07:00 UTC
    # + 24 h = 2 Nov 07:00 UTC < 2 Nov 00:00 PST = 08:00 UTC + 4 h
    (LA, "2026-10-31", "2026-11-02T12:00"),
])
def test_a_23_hour_day_after_the_click_date_ends_its_24_hours_an_hour_later(acc, x, boundary):
    b = utc(boundary)
    prev = (date.fromisoformat(x) - timedelta(days=1)).isoformat()
    assert google_ads.d0_final([acc], b - timedelta(minutes=1))["final_till"] == prev
    assert google_ads.d0_final([acc], b)["final_till"] == x
    assert google_ads.d0_final([acc], b - timedelta(minutes=1))["next_fix_utc"] == b.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_the_moment_is_exact_and_never_before_the_24_hours_through_summer_time_changes():
    """Every 30 min through the 2026 changes of a few zones: final_till moves on exactly at next_fix_utc, by one day, and
    never before the last click's 24 h (from x+1 00:00 local, absolute) + the lag."""
    from zoneinfo import ZoneInfo
    for tz, starts in (("America/Los_Angeles", ("2026-03-04", "2026-10-29")), ("Europe/Paris", ("2026-03-25", "2026-10-22")),
                       ("Australia/Lord_Howe", ("2026-04-01", "2026-09-30")), ("America/Santiago", ("2026-04-01", "2026-09-02"))):
        acc, z = [{"tz": tz}], ZoneInfo(tz)
        for st in starts:
            t = utc(st + "T00:00")
            for _ in range(8 * 48):
                r = google_ads.d0_final(acc, t)
                nf = utc(r["next_fix_utc"][:-1])
                nxt = (date.fromisoformat(r["final_till"]) + timedelta(days=1))
                assert nf > t and google_ads.d0_final(acc, nf - timedelta(minutes=1))["final_till"] == r["final_till"]
                assert google_ads.d0_final(acc, nf)["final_till"] == nxt.isoformat(), (tz, t)
                end = datetime.combine(nxt + timedelta(days=1), datetime.min.time(), tzinfo=z).astimezone(timezone.utc)
                assert nf >= end + timedelta(hours=24 + 4), (tz, t)
                t += timedelta(minutes=30)


def test_several_accounts_the_earliest_wins_and_the_next_fix_is_the_last_one():
    now = utc("2026-01-03T00:00")                    # IST already has 1 Jan final, LA not yet
    assert google_ads.d0_final([IST], now)["final_till"] == "2026-01-01"
    got = google_ads.d0_final([IST, LA, IST], now)
    assert got["final_till"] == "2025-12-31"
    assert got["next_fix_utc"] == "2026-01-03T12:00:00Z"      # LA's moment for 1 Jan (IST's was 2 Jan 22:30, past)
    assert google_ads.d0_final([], now) == google_ads.d0_final([{}], now)        # nobody asked: the conservative zone


def test_lag_hours_from_the_environment(monkeypatch):
    b = utc("2026-01-02T22:30")
    monkeypatch.setenv("GADS_D0_LAG_HOURS", "3")
    got = google_ads.d0_final([IST], b - timedelta(minutes=59))      # 21:31: an hour earlier with 3 h
    assert got["final_till"] == "2026-01-01" and got["lag_h"] == 3
    monkeypatch.setenv("GADS_D0_LAG_HOURS", "x")
    assert google_ads.d0_final([IST], b - timedelta(minutes=1))["lag_h"] == 4
    assert google_ads.d0_final([IST], b, lag_h=6)["final_till"] == "2025-12-31"


# ── 2. fetch_app_spend: the read's finality, complete or not ──────────────────────────────────────────────────────────
def _fetch(monkeypatch, fake, now, start="2026-01-01", end="2026-01-12"):
    monkeypatch.setattr(google_ads, "_search", fake.search)
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: TOK)
    monkeypatch.setattr(google_ads, "_fx_to_usd", {"INR": 0.012, "USD": 1.0}.get)
    return google_ads.fetch_app_spend(dict(SETTINGS, gads_archive=False), start, end, mode="live", now=now)


def test_fetch_says_which_dates_are_final_over_the_accounts_asked(monkeypatch):
    fake = FakeAds()
    fake.accounts[A3]["tz"] = "Pacific/Pago_Pago"     # not enabled → never asked: its (later) zone does not count
    now = utc("2026-01-10T23:00")                     # 11 Jan 04:30 IST − 4 h = 11 Jan 00:30 → final till 9 Jan
    out = _fetch(monkeypatch, fake, now)
    assert out["d1_ok"] is True and out["d1_final_till"] == "2026-01-09" and out["d1_lag_h"] == 4
    assert out["d1_next_fix_utc"] == "2026-01-11T22:30:00Z"
    assert out["convval_day1"] and out["daily"]
    fake.accounts[A1]["tz"] = "America/Los_Angeles"   # an asked account whose day ends later: it holds the date back
    assert _fetch(monkeypatch, fake, now)["d1_final_till"] == "2026-01-08"


def test_one_accounts_day1_error_makes_the_read_incomplete(monkeypatch, capsys):
    fake = FakeAds()
    fake.fail = lambda acct, kind, q: "HTTP 500: synthetic" if kind == "D1" and acct == A2 else None
    out = _fetch(monkeypatch, fake, utc("2026-01-10T23:00"))
    assert out["d1_ok"] is False and out["d1_final_till"] == "2026-01-09"
    assert out["daily"] and out["convval_day1"]       # spend and the other account's D0 are still there
    fake.fail = lambda acct, kind, q: "HTTP 500: synthetic" if kind == "INST" and acct == A2 else None
    assert _fetch(monkeypatch, fake, utc("2026-01-10T23:00"))["d1_ok"] is True     # only the day-1 query counts
    assert "D0" not in capsys.readouterr().err        # the fetch adds no line of its own


@pytest.mark.parametrize("fail, ok", [
    # an ENABLED account that cannot answer at all (any 403 on cost too, e.g. USER_PERMISSION_DENIED): it must not block
    # the fixing of every app for good — it is "unread" instead, and only ITS stores wait (merge_spend)
    (lambda acct, kind, q: "HTTP 403: authorizationError=USER_PERMISSION_DENIED — synthetic" if acct == A2 else None,
     True),
    # a passing failure (HTTP 500) on cost AND day-1: its part may be missing → incomplete
    (lambda acct, kind, q: "HTTP 500: synthetic" if acct == A2 and kind in ("SPEND", "D1") else None, False),
    # cost failed but day-1 answered: the D0 read itself is complete
    (lambda acct, kind, q: "HTTP 500: synthetic" if acct == A2 and kind == "SPEND" else None, True),
])
def test_an_account_that_cannot_answer_does_not_block_fixing(monkeypatch, fail, ok):
    fake = FakeAds()
    fake.fail = fail
    out = _fetch(monkeypatch, fake, utc("2026-01-10T23:00"))
    assert out["d1_ok"] is ok and out["daily"]
    assert out.get("d1_unread") == ([A2] if "403" in (fail(A2, "SPEND", "") or "") else None)


def test_the_finality_clock_is_read_before_the_d0_numbers(monkeypatch):
    """now=None (the build): d0_final gets the clock read BEFORE the day-1 queries — a date its moment passes while the
    queries run is not called final on numbers read before that moment."""
    fake, seen = FakeAds(), {"q": [], "final": []}
    monkeypatch.setattr(google_ads, "_search", fake.search)
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: TOK)
    monkeypatch.setattr(google_ads, "_fx_to_usd", {"INR": 0.012, "USD": 1.0}.get)
    real_lag, real_final = google_ads._app_convval_lag_for, google_ads.d0_final

    def lag_for(*a, **k):
        seen["q"].append(datetime.now(timezone.utc))
        return real_lag(*a, **k)

    def final(acc, now=None, lag_h=None):
        seen["final"].append(now)
        return real_final(acc, now, lag_h)
    monkeypatch.setattr(google_ads, "_app_convval_lag_for", lag_for)
    monkeypatch.setattr(google_ads, "d0_final", final)
    google_ads.fetch_app_spend(dict(SETTINGS, gads_archive=False), "2026-01-01", "2026-01-12", mode="live")
    assert seen["q"] and len(seen["final"]) == 1 and seen["final"][0] is not None
    assert seen["final"][0] <= min(seen["q"])


def test_an_account_without_a_click_in_the_window_does_not_block_fixing(monkeypatch):
    fake = FakeAds()
    fake.camps[A2]["21"]["lo"] = "2030-01-01"          # A2 answers cost with no row: no click, so no D0 to miss
    fake.fail = lambda acct, kind, q: "HTTP 500: synthetic" if kind == "D1" and acct == A2 else None
    assert _fetch(monkeypatch, fake, utc("2026-01-10T23:00"))["d1_ok"] is True
    fake.fail = lambda acct, kind, q: "HTTP 500: synthetic" if kind == "D1" and acct == A1 else None
    assert _fetch(monkeypatch, fake, utc("2026-01-10T23:00"))["d1_ok"] is False      # A1 has clicks: incomplete


def test_mock_and_empty_reads_never_fix(monkeypatch):
    mock = google_ads.fetch_app_spend({}, "2026-01-01", "2026-01-03", mode="mock")
    assert not mock.get("d1_ok")
    fake = FakeAds(lo="2030-01-01")                   # connected, no app-campaign spend in the window
    del fake.accounts[A3]                             # (a not-enabled account's refusal alone would be an error read)
    empty = _fetch(monkeypatch, fake, utc("2026-01-10T23:00"))
    assert empty["daily"] == {} and not empty.get("d1_ok")
    cached = _cache({"com.x.a": {"2026-01-01": 5.0}}, fixed="2026-01-01")
    m = google_ads.merge_spend(cached, empty, "2026-01-01")
    assert m["d1_fixed_till"] == "2026-01-01" and m["convval_day1"] == cached["convval_day1"]


# ── 3. merge_spend: fixed once, never again ───────────────────────────────────────────────────────────────────────────
def _cache(d1, fixed=None, **kw):
    c = {"v": 2, "daily": {"com.x.a": {"2026-01-01": 100, "2026-01-05": 500}}, "installs": {"com.x.a": {"2026-01-01": 3}},
         "convval": {"com.x.a": {"2026-01-01": 7.0}}, "convval_day1": d1, "campaigns": {}, "currency_src": "INR",
         "fx": {}}
    if fixed:
        c["d1_fixed_till"] = fixed
    c.update(kw)
    return c


def _fresh(d1, final="2026-01-04", ok=True, **kw):
    f = {"v": 2, "daily": {"com.x.a": {"2026-01-01": 120, "2026-01-06": 600}}, "installs": {"com.x.a": {"2026-01-01": 4}},
         "convval": {"com.x.a": {"2026-01-01": 9.0}}, "convval_day1": d1, "campaigns": {}, "currency_src": "INR",
         "fx": {}, "d1_final_till": final, "d1_next_fix_utc": "2026-01-05T22:30:00Z", "d1_lag_h": 4, "d1_ok": ok}
    f.update(kw)
    return f


def test_a_fixed_date_keeps_its_number_and_this_read_fixes_the_next_ones():
    cached = _cache({"com.x.a": {"2026-01-01": 10.0, "2026-01-02": 20.0, "2026-01-03": 30.0}}, fixed="2026-01-02")
    fresh = _fresh({"com.x.a": {"2026-01-01": 11.0, "2026-01-02": 21.0, "2026-01-03": 33.0, "2026-01-04": 40.0,
                                "2026-01-05": 5.0}})
    m = google_ads.merge_spend(cached, fresh, "2026-01-01")
    assert m["convval_day1"]["com.x.a"] == {"2026-01-01": 10.0, "2026-01-02": 20.0,    # fixed before: kept
                                            "2026-01-03": 33.0, "2026-01-04": 40.0,    # fixed by this read
                                            "2026-01-05": 5.0}                         # still live
    assert m["d1_fixed_till"] == "2026-01-04"
    assert m["d1_next_fix_utc"] == "2026-01-05T22:30:00Z" and m["d1_lag_h"] == 4
    # every other key: the overlay exactly as before (fresh over cached, fixed dates or not)
    assert m["daily"]["com.x.a"] == {"2026-01-01": 120, "2026-01-05": 500, "2026-01-06": 600}
    assert m["installs"]["com.x.a"] == {"2026-01-01": 4} and m["convval"]["com.x.a"] == {"2026-01-01": 9.0}
    # the next run: Google's numbers moved on — the fixed ones stay, 5 Jan is fixed at this read's number
    fresh2 = _fresh({"com.x.a": {"2026-01-03": 35.0, "2026-01-04": 44.0, "2026-01-05": 7.0, "2026-01-06": 1.0}},
                    final="2026-01-05", d1_next_fix_utc="2026-01-06T22:30:00Z")
    m2 = google_ads.merge_spend(m, fresh2, "2026-01-03")
    assert m2["convval_day1"]["com.x.a"] == {"2026-01-01": 10.0, "2026-01-02": 20.0, "2026-01-03": 33.0,
                                             "2026-01-04": 40.0, "2026-01-05": 7.0, "2026-01-06": 1.0}
    assert m2["d1_fixed_till"] == "2026-01-05" and m2["d1_next_fix_utc"] == "2026-01-06T22:30:00Z"
    m3 = google_ads.merge_spend(m2, _fresh({"com.x.a": {"2026-01-05": 9.0, "2026-01-06": 2.0}}, final="2026-01-05"),
                                "2026-01-05")
    assert m3["convval_day1"]["com.x.a"]["2026-01-05"] == 7.0 and m3["convval_day1"]["com.x.a"]["2026-01-06"] == 2.0


def test_a_date_the_read_lacks_is_fixed_at_the_cached_number():
    cached = _cache({"com.x.a": {"2026-01-03": 30.0}}, fixed="2026-01-02")
    m = google_ads.merge_spend(cached, _fresh({"com.x.a": {"2026-01-04": 40.0}}), "2026-01-03")
    assert m["convval_day1"]["com.x.a"] == {"2026-01-03": 30.0, "2026-01-04": 40.0} and m["d1_fixed_till"] == "2026-01-04"
    m2 = google_ads.merge_spend(m, _fresh({"com.x.a": {"2026-01-03": 99.0}}, final="2026-01-04"), "2026-01-03")
    assert m2["convval_day1"]["com.x.a"]["2026-01-03"] == 30.0


def test_an_incomplete_read_does_not_move_the_fixed_date():
    cached = _cache({"com.x.a": {"2026-01-01": 10.0, "2026-01-03": 30.0}}, fixed="2026-01-02")
    fresh = _fresh({"com.x.a": {"2026-01-01": 11.0, "2026-01-03": 33.0}}, final="2026-01-04", ok=False)
    m = google_ads.merge_spend(cached, fresh, "2026-01-01")
    assert m["d1_fixed_till"] == "2026-01-02" and m["d1_incomplete"] is True       # the page: no "next refresh" promise
    assert m["convval_day1"]["com.x.a"] == {"2026-01-01": 10.0, "2026-01-03": 33.0}   # 3 Jan: still the live overlay
    assert "d1_incomplete" not in google_ads.merge_spend(m, dict(fresh, d1_ok=True), "2026-01-01")   # a full read: gone
    m0 = google_ads.merge_spend(_cache({"com.x.a": {"2026-01-01": 10.0}}), fresh, "2026-01-01")   # never fixed + incomplete
    assert m0["d1_fixed_till"] is None and m0["convval_day1"]["com.x.a"] == {"2026-01-01": 11.0, "2026-01-03": 33.0}


def test_a_deeper_rebackfill_fills_old_dates_the_cache_never_held():
    cached = _cache({"com.x.a": {"2026-01-02": 20.0}}, fixed="2026-01-03")
    fresh = _fresh({"com.x.a": {"2025-12-20": 2.0, "2026-01-02": 25.0}, "com.x.b": {"2025-12-21": 4.0}})
    m = google_ads.merge_spend(cached, fresh, "2025-12-20")
    assert m["convval_day1"] == {"com.x.a": {"2026-01-02": 20.0, "2025-12-20": 2.0, "2026-01-01": 0.0},   # 1 Jan: cost,
                                 "com.x.b": {"2025-12-21": 4.0}}                                       # no D0 → 0
    m2 = google_ads.merge_spend(m, _fresh({"com.x.a": {"2025-12-20": 3.0}, "com.x.b": {"2025-12-21": 5.0}}), "2025-12-20")
    assert m2["convval_day1"] == m["convval_day1"]                                   # and from then on they stay


def test_a_cache_from_before_the_fix_is_fixed_by_the_first_complete_read():
    cached = _cache({"com.x.a": {"2025-10-01": 1.0, "2026-01-02": 20.0}})         # no d1_fixed_till: the old cache
    m = google_ads.merge_spend(cached, _fresh({"com.x.a": {"2026-01-02": 22.0, "2026-01-05": 5.0}}), "2026-01-01")
    assert m["convval_day1"]["com.x.a"] == {"2025-10-01": 1.0, "2026-01-01": 0.0, "2026-01-02": 22.0, "2026-01-05": 5.0}
    assert m["d1_fixed_till"] == "2026-01-04" and "d1_drift" not in m


def test_a_day_with_cost_and_no_d0_is_fixed_at_zero():
    """A store-day a complete read covered with cost but no D0 row (no conversion within 24 h) is fixed at 0: a late
    value Google adds afterwards never slips into a fixed date (it is measured as drift instead)."""
    cached = _cache({"com.x.a": {"2026-01-01": 10.0}}, fixed="2026-01-01",
                    daily={"com.x.a": {"2025-12-30": 50, "2026-01-01": 100, "2026-01-02": 200, "2026-01-03": 300}})
    fresh = _fresh({"com.x.a": {"2026-01-01": 10.0, "2026-01-03": 30.0}}, final="2026-01-02",
                   daily={"com.x.a": {"2026-01-02": 200, "2026-01-03": 300}})
    m = google_ads.merge_spend(cached, fresh, "2026-01-01")
    # 2 Jan: cost, no D0 in a complete read → 0.0; 3 Jan: not fixed yet; 30 Dec: before the read (never read) → absent
    assert m["convval_day1"]["com.x.a"] == {"2026-01-01": 10.0, "2026-01-02": 0.0, "2026-01-03": 30.0}
    late = _fresh({"com.x.a": {"2026-01-01": 10.0, "2026-01-02": 3.0, "2026-01-03": 31.0}}, final="2026-01-02")
    m2 = google_ads.merge_spend(m, late, "2026-01-01")
    assert m2["convval_day1"]["com.x.a"]["2026-01-02"] == 0.0                  # fixed: Google's late 3.0 not taken
    assert m2["d1_drift"] == {"days": 2, "from": "2026-01-01", "to": "2026-01-02", "pct": 30.0}   # 13 ÷ 10 − 1
    # an incomplete read fixes nothing at 0 (its missing part would freeze a false zero)
    part = google_ads.merge_spend(cached, dict(fresh, d1_ok=False), "2026-01-01")
    assert part["convval_day1"]["com.x.a"] == {"2026-01-01": 10.0, "2026-01-03": 30.0}
    first = google_ads.merge_spend(None, _fresh({"com.x.a": {"2026-01-06": 6.0}}), "2026-01-01")   # first run too
    assert first["convval_day1"]["com.x.a"] == {"2026-01-01": 0.0, "2026-01-06": 6.0}


def test_the_fixed_date_never_moves_back():
    """A complete read whose final_till is behind the cache's (GADS_D0_LAG_HOURS raised, or an asked account in a
    later time zone) leaves d1_fixed_till where it is, and the fixed number stays through the reads after it."""
    # IST; the cache's lag 4 h: 6 Jan is final at 8 Jan 00:00 IST + 4 h = 7 Jan 22:30 UTC. Raised to 8 h, the read
    # is behind: final till 4 Jan, its moment for 5 Jan = 7 Jan 00:00 IST + 8 h = 7 Jan 02:30 UTC
    cached = _cache({"com.x.a": {"2026-01-05": 10.0}}, fixed="2026-01-05", d1_next_fix_utc="2026-01-07T22:30:00Z")
    behind = _fresh({"com.x.a": {"2026-01-05": 12.0}}, final="2026-01-04", d1_next_fix_utc="2026-01-07T02:30:00Z",
                    d1_lag_h=8)
    m = google_ads.merge_spend(cached, behind, "2026-01-01")
    assert m["d1_fixed_till"] == "2026-01-05" and m["convval_day1"]["com.x.a"]["2026-01-05"] == 10.0
    assert m["d1_next_fix_utc"] == "2026-01-08T02:30:00Z"         # 6 Jan's moment with 8 h (the read's + 1 day)
    m2 = google_ads.merge_spend(m, _fresh({"com.x.a": {"2026-01-05": 13.0}}, final="2026-01-05",
                                          d1_next_fix_utc="2026-01-08T02:30:00Z", d1_lag_h=8), "2026-01-01")
    assert m2["d1_fixed_till"] == "2026-01-05" and m2["convval_day1"]["com.x.a"]["2026-01-05"] == 10.0


def test_next_fix_is_always_the_moment_for_the_day_after_fixed_till():
    """d1_next_fix_utc belongs to d1_fixed_till + 1 (the page counts every later date from it): an incomplete read
    leaves fixed_till behind its own final_till, so its moment is moved back by those days — never days late."""
    # IST, lag 4 h: date X is final at (X+2) 00:00 IST + 4 h = (X+1) 22:30 UTC — 7 Jan's moment is 8 Jan 22:30 UTC
    cached = _cache({}, fixed="2026-01-06", d1_next_fix_utc="2026-01-08T22:30:00Z")
    # two days on, every read incomplete: the read's final_till is 8 Jan (its next moment: 9 Jan's, 10 Jan 22:30 UTC)
    part = _fresh({}, final="2026-01-08", ok=False, d1_next_fix_utc="2026-01-10T22:30:00Z")
    m = google_ads.merge_spend(cached, part, "2026-01-01")
    assert m["d1_fixed_till"] == "2026-01-06" and m["d1_next_fix_utc"] == "2026-01-08T22:30:00Z"   # 7 Jan's moment
    m2 = google_ads.merge_spend(m, dict(part, d1_final_till="2026-01-09", d1_next_fix_utc="2026-01-11T22:30:00Z"),
                                "2026-01-01")
    assert m2["d1_next_fix_utc"] == "2026-01-08T22:30:00Z"         # still 7 Jan's: it does not slide on
    done = google_ads.merge_spend(m2, _fresh({}, final="2026-01-09", d1_next_fix_utc="2026-01-11T22:30:00Z"),
                                  "2026-01-01")
    assert done["d1_fixed_till"] == "2026-01-09" and done["d1_next_fix_utc"] == "2026-01-11T22:30:00Z"
    never = google_ads.merge_spend(_cache({}), part, "2026-01-01")   # nothing fixed yet: no moment to count from
    assert never["d1_fixed_till"] is None and "d1_next_fix_utc" not in never
    first = google_ads.merge_spend(None, dict(part), "2026-01-01")
    assert first["d1_fixed_till"] is None and "d1_next_fix_utc" not in first


def _c(cid, acct):
    return {"id": cid, "name": "n", "status": "ENABLED", "cost_micros": 1, "account": acct}


def test_an_unread_accounts_stores_wait_and_the_rest_is_fixed():
    """Account "2" answers 403 to every query for two reads (d1_unread). Its own store (s.two) and the store it shares
    with account "1" (s.split) keep their dates live (d1_open, "wait") — never a partial number or a false 0.0 fixed for
    good — while account "1"'s own store is fixed as usual; the first read after "2" is back fixes them at Google's
    complete numbers. The split store keeps waiting although the merged campaigns no longer name "2"."""
    camps = {"s.one": [_c("c1", "1")], "s.two": [_c("c2", "2")], "s.split": [_c("c3", "1"), _c("c4", "2")]}
    cost = lambda *ds: {d: 100 for d in ds}
    cached = _cache({"s.one": {"2026-01-03": 5.0}, "s.two": {"2026-01-03": 3.0}, "s.split": {"2026-01-03": 40.0}},
                    fixed="2026-01-02", campaigns=camps,
                    daily={s: cost("2026-01-03", "2026-01-04") for s in camps})
    one = {"s.one": [_c("c1", "1")], "s.split": [_c("c3", "1")]}           # what account "1" answers
    r1 = _fresh({"s.one": {"2026-01-03": 6.0, "2026-01-04": 7.0}, "s.split": {"2026-01-03": 20.0, "2026-01-04": 21.0}},
                final="2026-01-04", campaigns=one, d1_unread=["2"],
                daily={"s.one": cost("2026-01-03", "2026-01-04"), "s.split": cost("2026-01-03", "2026-01-04")})
    m1 = google_ads.merge_spend(cached, r1, "2026-01-01")
    assert m1["d1_fixed_till"] == "2026-01-04"
    assert m1["convval_day1"]["s.one"] == {"2026-01-03": 6.0, "2026-01-04": 7.0}             # fixed
    assert m1["convval_day1"]["s.two"] == {"2026-01-03": 3.0}                                # live; 4 Jan: no false 0
    # 4 Jan of s.two: cost, no D0 yet — open too (the page must not call it fixed while its number can still come)
    assert m1["d1_open"] == {"s.two": {"days": ["2026-01-03", "2026-01-04"], "wait": ["2"]},
                             "s.split": {"days": ["2026-01-03", "2026-01-04"], "wait": ["2"]}}
    assert m1["campaigns"]["s.split"] == [_c("c3", "1")]                                     # campaigns: as before
    r2 = _fresh({"s.one": {"2026-01-03": 6.6, "2026-01-04": 7.7, "2026-01-05": 8.0}, "s.split": {"2026-01-05": 22.0}},
                final="2026-01-05", campaigns=one, d1_unread=["2"],
                daily={"s.one": cost("2026-01-05"), "s.split": cost("2026-01-05")})
    m2 = google_ads.merge_spend(m1, r2, "2026-01-01")
    assert m2["d1_open"]["s.split"] == {"days": ["2026-01-03", "2026-01-04", "2026-01-05"], "wait": ["2"]}
    assert m2["d1_open"]["s.two"] == {"days": ["2026-01-03", "2026-01-04"], "wait": ["2"]}
    assert m2["convval_day1"]["s.one"]["2026-01-05"] == 8.0 and "s.one" not in m2["d1_open"]
    assert m2["d1_drift"] == {"days": 2, "from": "2026-01-03", "to": "2026-01-04", "pct": 10.0}   # s.one only: 14.3 ÷ 13
    # "2" is back: its complete numbers are taken and fixed; nothing waits any more
    r3 = _fresh({"s.one": {"2026-01-05": 8.0}, "s.two": {"2026-01-03": 11.0, "2026-01-04": 9.0},
                 "s.split": {"2026-01-03": 40.0, "2026-01-04": 42.0, "2026-01-05": 44.0}},
                final="2026-01-06", campaigns=camps, daily={})
    m3 = google_ads.merge_spend(m2, r3, "2026-01-01")
    assert m3["convval_day1"]["s.two"] == {"2026-01-03": 11.0, "2026-01-04": 9.0}
    assert m3["convval_day1"]["s.split"] == {"2026-01-03": 40.0, "2026-01-04": 42.0, "2026-01-05": 44.0}
    assert "d1_open" not in m3 and m3["d1_fixed_till"] == "2026-01-06"
    r4 = _fresh({"s.two": {"2026-01-03": 12.0, "2026-01-04": 9.0}}, final="2026-01-06", campaigns=camps, daily={})
    assert google_ads.merge_spend(m3, r4, "2026-01-01")["convval_day1"]["s.two"]["2026-01-03"] == 11.0   # fixed for good


def test_a_cost_only_day_a_read_cannot_fix_stays_open_until_one_can():
    """A store-day up to d1_fixed_till with cost but no D0 row yet, that this read cannot fix (its store waits for an
    unread account), is live in d1_open — the page shows it filling, never "Fixed" at 0 — and the read after the account
    is back fixes it at Google's complete number (or at 0.0 when Google has none within 24 h)."""
    camps = {"s.split": [_c("c1", "1"), _c("c2", "2")]}
    cached = _cache({"s.split": {"2026-01-02": 9.0}}, fixed="2026-01-02", campaigns=camps,
                    daily={"s.split": {"2026-01-02": 100}})
    r1 = _fresh({}, final="2026-01-04", d1_unread=["2"], campaigns={"s.split": [_c("c1", "1")]},
                daily={"s.split": {"2026-01-03": 50, "2026-01-04": 50}})      # "1": cost, no D0 yet; "2": 403
    m1 = google_ads.merge_spend(cached, r1, "2026-01-01")
    assert m1["d1_fixed_till"] == "2026-01-04" and m1["convval_day1"]["s.split"] == {"2026-01-02": 9.0}
    assert m1["d1_open"] == {"s.split": {"days": ["2026-01-03", "2026-01-04"], "wait": ["2"]}}
    app = [{"app_id": "app-s", "app_name": "App S", "rev": 1}]
    e = build_roas(_spend_to_usd(m1, 0.01), {"app-s": "s.split"}, app)["by_app"]["App S"]
    assert e["d0_open"] == ["2026-01-03", "2026-01-04"] and e["d0_wait"] is True
    r2 = _fresh({"s.split": {"2026-01-03": 31.0}}, final="2026-01-05", campaigns=camps,
                daily={"s.split": {"2026-01-03": 100, "2026-01-04": 100}})    # "2" back: Google's complete D0
    m2 = google_ads.merge_spend(m1, r2, "2026-01-01")
    assert m2["convval_day1"]["s.split"] == {"2026-01-02": 9.0, "2026-01-03": 31.0, "2026-01-04": 0.0}
    assert "d1_open" not in m2
    later = _fresh({"s.split": {"2026-01-03": 33.0, "2026-01-04": 2.0}}, final="2026-01-05", campaigns=camps)
    assert google_ads.merge_spend(m2, later, "2026-01-01")["convval_day1"]["s.split"] == m2["convval_day1"]["s.split"]


def test_a_wait_survives_an_incomplete_read():
    """403 → a passing non-403 failure (HTTP 500: the read is incomplete and the account is not "unread") → 403 again →
    back. The split store keeps waiting through the incomplete read (it does not show the account answered) and is
    fixed only at Google's complete numbers, never at the readable account's part."""
    camps, one = {"s.split": [_c("c1", "1"), _c("c2", "2")]}, {"s.split": [_c("c1", "1")]}
    part = {"s.split": {"2026-01-03": 14.0, "2026-01-04": 15.0}}                # account "1"'s part only
    cached = _cache({"s.split": {"2026-01-03": 30.0}}, fixed="2026-01-02", campaigns=camps, daily={})
    held = {"s.split": {"days": ["2026-01-03", "2026-01-04"], "wait": ["2"]}}
    a = google_ads.merge_spend(cached, _fresh(part, final="2026-01-04", d1_unread=["2"], campaigns=one, daily={}),
                               "2026-01-01")
    assert a["d1_open"] == held and a["campaigns"]["s.split"] == one["s.split"]
    b = google_ads.merge_spend(a, _fresh(part, final="2026-01-04", ok=False, campaigns=one, daily={}), "2026-01-01")
    assert b["d1_open"] == held
    c = google_ads.merge_spend(b, _fresh(part, final="2026-01-05", d1_unread=["2"], campaigns=one, daily={}),
                               "2026-01-01")
    assert c["d1_open"] == held and c["convval_day1"]["s.split"] == part["s.split"]          # live, not fixed
    d = google_ads.merge_spend(c, _fresh({"s.split": {"2026-01-03": 30.5, "2026-01-04": 31.0}}, final="2026-01-05",
                                         campaigns=camps, daily={}), "2026-01-01")
    assert d["convval_day1"]["s.split"] == {"2026-01-03": 30.5, "2026-01-04": 31.0} and "d1_open" not in d


@pytest.mark.parametrize("odd", [
    {"convval_day1": {"com.x.a": {"2026-01-01": None, "2026-01-02": "5", "2026-01-03": float("nan")}}},
    {"convval_day1": {"com.x.a": ["2026-01-01"]}},
    {"d1_open": {"com.x.a": ["2026-01-02"]}},
    {"d1_open": ["com.x.a"]},
    {"d1_open": {"com.x.a": {"days": 5, "wait": 7}}},
    {"d1_fixed_till": 5},
    {"d1_fixed_till": "x"},
    {"campaigns": {"com.x.a": 5}},
])
def test_an_odd_cache_value_never_raises(odd):
    """A corrupt / hand-edited cache never makes the merge raise (a raise would skip ROAS on every run after it): an odd
    D0 value or field counts as absent."""
    cached = _cache({"com.x.a": {"2026-01-01": 10.0, "2026-01-02": 20.0}}, fixed="2026-01-02")
    cached.update(odd)
    m = google_ads.merge_spend(cached, _fresh({"com.x.a": {"2026-01-01": 11.0, "2026-01-02": 21.0, "2026-01-03": 30.0}}),
                               "2026-01-01")
    json.dumps(m, allow_nan=False)
    assert m["d1_fixed_till"] == "2026-01-04" and m["convval_day1"]["com.x.a"]["2026-01-03"] == 30.0
    gone = "convval_day1" in odd or "d1_fixed_till" in odd             # no usable fixed number: the read's is taken
    assert m["convval_day1"]["com.x.a"]["2026-01-01"] == (11.0 if gone else 10.0)
    if "campaigns" not in odd:                                          # (an odd campaign list fails build_roas as before)
        build_roas(_spend_to_usd(m, 0.01), {"app-a": "com.x.a"}, [{"app_id": "app-a", "app_name": "App A", "rev": 1}])


def test_an_unread_account_with_nothing_unfixed_holds_nothing():
    """A 403 account whose stores have no date after d1_fixed_till (no recent click) changes nothing: idle."""
    cached = _cache({"s.two": {"2026-01-01": 3.0}}, fixed="2026-01-02", campaigns={"s.two": [_c("c2", "2")]},
                    daily={"s.two": {"2026-01-01": 100}})
    m = google_ads.merge_spend(cached, _fresh({}, final="2026-01-04", d1_unread=["2"], daily={}), "2026-01-01")
    assert m["d1_fixed_till"] == "2026-01-04" and m["convval_day1"]["s.two"] == {"2026-01-01": 3.0}
    assert m["d1_open"] == {"s.two": {"days": [], "wait": ["2"]}}       # remembered while "2" cannot answer
    assert "d1_open" not in google_ads.merge_spend(m, _fresh({}, final="2026-01-04", daily={}), "2026-01-01")


def test_a_read_behind_fixed_till_fixes_only_what_is_final_for_it():
    """An account in a later time zone joins after IST fixed 5 Jan: its read's own final_till is 4 Jan. Its new store's
    5 Jan (still filling for it) is NOT fixed — it stays live in d1_open, no false 0.0 either — until a read whose
    final_till covers it; the dates ≤ 4 Jan are fixed at once."""
    ist = {"s.ist": {"2026-01-0%d" % i: 1.0 for i in range(1, 6)}}
    cached = _cache(dict(ist), fixed="2026-01-05", daily={"s.ist": {"2026-01-0%d" % i: 10 for i in range(1, 6)}})
    la = {"2026-01-01": 5.0, "2026-01-02": 5.0, "2026-01-03": 5.0, "2026-01-04": 5.0, "2026-01-05": 2.0}
    cost = {"s.la": {"2026-01-0%d" % i: 20 for i in range(1, 7)}, "s.la2": {"2026-01-05": 30}}
    behind = _fresh(dict(ist, **{"s.la": la}), final="2026-01-04", daily=cost)
    m = google_ads.merge_spend(cached, behind, "2026-01-01")
    assert m["d1_fixed_till"] == "2026-01-05" and m["convval_day1"]["s.la"] == la
    # s.la2's 5 Jan: cost, no D0 yet — not a final 0 for it, and open (the page shows it filling, not fixed)
    assert m["d1_open"] == {"s.la": {"days": ["2026-01-05"], "wait": []}, "s.la2": {"days": ["2026-01-05"], "wait": []}}
    assert "s.la2" not in m["convval_day1"]
    done = _fresh({"s.la": dict(la, **{"2026-01-05": 5.0})}, final="2026-01-05", daily=cost)
    m2 = google_ads.merge_spend(m, done, "2026-01-01")
    assert m2["convval_day1"]["s.la"]["2026-01-05"] == 5.0 and m2["convval_day1"]["s.la2"] == {"2026-01-05": 0.0}
    assert "d1_open" not in m2
    m3 = google_ads.merge_spend(m2, _fresh({"s.la": {"2026-01-05": 6.0}}, final="2026-01-05"), "2026-01-01")
    assert m3["convval_day1"]["s.la"]["2026-01-05"] == 5.0
    # an incomplete read's date ≤ fixed_till that the cache never held: live in d1_open too, never fixed by it
    part = google_ads.merge_spend(cached, _fresh({"s.new": {"2026-01-02": 4.0}}, ok=False), "2026-01-01")
    assert part["convval_day1"]["s.new"] == {"2026-01-02": 4.0}
    # (com.x.a: the read's 1 Jan cost, never fixed by a read that saw it — open as well)
    assert part["d1_open"] == {"s.new": {"days": ["2026-01-02"], "wait": []}, "com.x.a": {"days": ["2026-01-01"], "wait": []}}


def test_next_fix_and_fix_at_from_the_reads_zones_exact_across_summer_time():
    """A complete read behind fixed_till across the US summer-time end: d1_next_fix_utc is 31 Oct's own moment (12:00
    UTC), not the read's moment for 30 Oct moved by 24 h (11:00 UTC); d1_fix_at lists each date's own moment."""
    now = utc("2026-11-01T10:00")
    read = google_ads.d0_final([LA], now)
    assert read["final_till"] == "2026-10-29" and read["zones"] == ["America/Los_Angeles"]
    fresh = _fresh({}, ok=True, **{"d1_" + k: v for k, v in read.items()})
    m = google_ads.merge_spend(_cache({}, fixed="2026-10-30"), fresh, "2026-10-01")
    assert m["d1_fixed_till"] == "2026-10-30" and m["d1_next_fix_utc"] == "2026-11-02T12:00:00Z"
    assert google_ads.d0_final([LA], utc("2026-11-02T11:59"))["final_till"] == "2026-10-30"
    assert m["d1_fix_at"]["2026-10-31"] == "2026-11-02T12:00:00Z" and m["d1_fix_at"]["2026-11-01"] == "2026-11-03T12:00:00Z"
    assert min(m["d1_fix_at"]) == "2026-10-31" and max(m["d1_fix_at"]) == "2026-11-03"
    for d, at in m["d1_fix_at"].items():                      # each one: the moment d0_final moves past that date
        t = utc(at[:-1])
        assert google_ads.d0_final([LA], t)["final_till"] >= d > google_ads.d0_final([LA], t - timedelta(minutes=1))["final_till"]
    first = google_ads.merge_spend(None, dict(fresh), "2026-10-01")
    assert first["d1_next_fix_utc"] == read["next_fix_utc"] and min(first["d1_fix_at"]) == "2026-10-30"


def test_first_run_error_and_not_configured():
    fresh = _fresh({"com.x.a": {"2026-01-02": 22.0}})
    assert google_ads.merge_spend(None, fresh, "2026-01-01") is fresh and fresh["d1_fixed_till"] == "2026-01-04"
    bad = _fresh({}, ok=False)
    assert google_ads.merge_spend(None, bad, "2026-01-01")["d1_fixed_till"] is None
    cached = _cache({"com.x.a": {"2026-01-02": 20.0}}, fixed="2026-01-02")
    # a failed fetch keeps the cache; with dates fixed it says the latest read fixed nothing (the page: no "next refresh")
    assert google_ads.merge_spend(cached, {"error": "boom"}, "2026-01-01") == dict(cached, d1_incomplete=True)
    assert "d1_incomplete" not in cached
    never = _cache({})
    assert google_ads.merge_spend(never, {"error": "boom"}, "2026-01-01") is never
    assert google_ads.merge_spend(None, {"error": "boom"}, "2026-01-01") == {"error": "boom"}
    assert google_ads.merge_spend(cached, None, "2026-01-01") is None


def test_lag_and_next_fix_come_from_the_read_else_the_cache():
    cached = _cache({}, fixed="2026-01-02", d1_next_fix_utc="2026-01-03T22:30:00Z", d1_lag_h=3,
                    d1_drift={"days": 1, "from": "2026-01-01", "to": "2026-01-01", "pct": 0.5})
    plain = {k: v for k, v in _fresh({}).items() if not k.startswith("d1_")}       # a read without the D0 keys
    m = google_ads.merge_spend(cached, plain, "2026-01-01")
    assert (m["d1_fixed_till"], m["d1_next_fix_utc"], m["d1_lag_h"]) == ("2026-01-02", "2026-01-03T22:30:00Z", 3)
    assert m["d1_drift"] == cached["d1_drift"]                                    # nothing to measure: kept


# ── 4. the measured late drift (a percentage, never an amount) ────────────────────────────────────────────────────────
def test_drift_over_the_latest_30_fixed_dates_the_read_also_has():
    d0 = date(2025, 11, 1)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range(40)]           # 1 Nov … 10 Dec, all fixed
    cached = _cache({"com.x.a": {d: 10.0 for d in days}, "com.x.b": {d: 30.0 for d in days}}, fixed=days[-1])
    # Google now: the 10 oldest doubled (outside the latest 30: not measured), the latest 30 +10 %, one more date the
    # cache never held (not a fixed number: not measured)
    now = {"com.x.a": {d: (20.0 if i < 10 else 11.0) for i, d in enumerate(days)},
           "com.x.b": {d: (60.0 if i < 10 else 33.0) for i, d in enumerate(days)}}
    now["com.x.a"]["2025-10-01"] = 500.0
    m = google_ads.merge_spend(cached, _fresh(now, final=days[-1]), "2025-10-01")
    assert m["d1_drift"] == {"days": 30, "from": days[10], "to": days[-1], "pct": 10.0}
    assert m["convval_day1"]["com.x.a"][days[-1]] == 10.0                         # measured, never taken


def test_drift_small_case_by_hand():
    cached = _cache({"com.x.a": {"2026-01-01": 10.0, "2026-01-02": 20.0}}, fixed="2026-01-02")
    m = google_ads.merge_spend(cached, _fresh({"com.x.a": {"2026-01-01": 11.0, "2026-01-02": 21.0}}), "2026-01-01")
    assert m["d1_drift"] == {"days": 2, "from": "2026-01-01", "to": "2026-01-02", "pct": 6.67}    # 32 ÷ 30 − 1
    # an incomplete read (an account's day-1 query failed) is not measured: a store missing its part is no drift
    part = google_ads.merge_spend(m, _fresh({"com.x.a": {"2026-01-01": 5.0}}, ok=False), "2026-01-01")
    assert part["d1_drift"] == m["d1_drift"]
    assert "d1_drift" not in google_ads.merge_spend(cached, _fresh({"com.x.a": {"2026-01-01": 5.0}}, ok=False), "2026-01-01")


# ── 5. the public runner's log: dates and counts only ─────────────────────────────────────────────────────────────────
def test_log_lines_are_counts_only(capsys):
    cached = _cache({"com.x.a": {"2026-01-01": 12345.67, "2026-01-03": 23456.78}}, fixed="2026-01-02")
    fresh = _fresh({"com.x.a": {"2026-01-01": 13579.24, "2026-01-03": 24680.13, "2026-01-04": 34567.89},
                    "com.x.b": {"2026-01-04": 45678.9}})
    google_ads.merge_spend(cached, fresh, "2026-01-01")
    google_ads.merge_spend(cached, dict(fresh, d1_ok=False), "2026-01-01")
    google_ads.merge_spend(None, json.loads(json.dumps(fresh)), "2026-01-01")
    lines = capsys.readouterr().err.splitlines()
    assert lines == ["roas: D0 fixed till 2026-01-04 · 3 store-days fixed this run",
                     "roas: D0 fixed till 2026-01-02 · 0 store-days fixed this run (day-1 read incomplete: not moved)",
                     "roas: D0 fixed till 2026-01-04 · 4 store-days fixed this run"]
    for ln in lines:
        assert LINE.match(ln), ln
        rest = re.sub(r"\d{4}-\d{2}-\d{2}", "", ln)          # the date is the only long number a line may carry
        assert "%" not in ln and "com.x" not in ln and not re.search(r"\d{3,}|\d\.\d", rest), ln


# ── 6. to the page ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_spend_to_usd_and_build_roas_carry_d0():
    cached = _cache({"com.x.a": {"2026-01-01": 900.0}}, fixed="2026-01-01")
    m = google_ads.merge_spend(cached, _fresh({"com.x.a": {"2026-01-01": 990.0, "2026-01-05": 90.0}}), "2026-01-01")
    usd = _spend_to_usd(m, 0.01)
    assert usd["d1_fixed_till"] == "2026-01-04" and usd["d1_drift"] == m["d1_drift"]
    assert usd["convval_day1"]["com.x.a"] == {"2026-01-01": 9.0, "2026-01-05": 0.9}
    r = build_roas(usd, {"app-a": "com.x.a"}, [{"app_id": "app-a", "app_name": "App A", "rev": 1}])
    assert r["d0"] == {"fixed_till": "2026-01-04", "next_fix_utc": "2026-01-05T22:30:00Z", "lag_h": 4,
                       "drift": {"days": 1, "from": "2026-01-01", "to": "2026-01-01", "pct": 10.0}}
    assert r["by_app"]["App A"]["convval_day1_daily"] == {"2026-01-01": 9.0, "2026-01-05": 0.9}
    assert "d0" not in build_roas(_spend_to_usd(_cache({}), 0.01), {}, [])                 # a cache without D0 keys
    part = build_roas(_spend_to_usd(_cache({}, d1_lag_h=4, d1_fixed_till=None), 0.01), {}, [])
    assert part["d0"] == {"lag_h": 4}
    held = dict(m, d1_open={"com.x.a": {"days": ["2026-01-03"], "wait": ["acct-synth-9"]}}, d1_fix_at={"2026-01-05": "x"})
    r = build_roas(_spend_to_usd(held, 0.01), {"app-a": "com.x.a"}, [{"app_id": "app-a", "app_name": "App A", "rev": 1}])
    assert r["by_app"]["App A"]["d0_open"] == ["2026-01-03"] and r["by_app"]["App A"]["d0_wait"] is True
    assert r["d0"]["fix_at"] == {"2026-01-05": "x"} and "acct-synth-9" not in json.dumps(r)     # no account id to the page
    assert "d0_open" not in build_roas(_spend_to_usd(m, 0.01), {"app-a": "com.x.a"},
                                       [{"app_id": "app-a", "app_name": "App A", "rev": 1}])["by_app"]["App A"]


def test_the_campaign_store_compares_day1_only_on_days_not_fixed(tmp_path):
    mf = gcd.months(str(tmp_path))
    days = ["2026-01-0%d" % i for i in range(1, 5)]
    gcd.overlay(mf, "cv1", [{"campaign_id": "1", "store_id": "com.x.a", "date": d, "convval": 5.0, "account": "1"}
                            for d in days], {"1": "INR"})
    spend = {"currency_src": "INR", "fx": {}, "daily": {},
             "convval_day1": {"com.x.a": {"2026-01-01": 4.0, "2026-01-02": 5.0, "2026-01-03": 5.0, "2026-01-04": 5.0}}}
    assert gcd.ties(mf, spend, days[0], days[-1])["cv1"] == [3, 4]             # 1 Jan: fixed at 4, Google now 5
    assert gcd.ties(mf, dict(spend, d1_fixed_till="2026-01-02"), days[0], days[-1])["cv1"] == [2, 2]


# ── 7. the Overview "Revenue by app" table, run for real ──────────────────────────────────────────────────────────────
DEMO, PUZ = "com.example.demo", "com.example.puzzle"
RS = 1_000_000                                       # ₹1 in micros
WIN = DAYS[:-1]                                      # "All time": every complete day (31 Dec … 7 Jan; 8 Jan = today)


def _raw(fixed=None, plus=0.0, **kw):
    """The raw (₹) spend cache / read: Demo ₹9,000 spend + ₹2,700 D0 a day, every day; Puzzle ₹4,500 + ₹1,800, 2–5 Jan.
    plus: Google's later number on the dates up to 4 Jan (+1 % = what fixing leaves out)."""
    up = lambda d, v: round(v * (1 + plus), 2) if d <= "2026-01-04" else v
    sp = {"v": 2, "currency_src": "INR", "fx": {}, "note": None, "installs": {}, "convval": {},
          "daily": {DEMO: {d: 9_000 * RS for d in DAYS}, PUZ: {d: 4_500 * RS for d in DAYS[2:6]}},
          "convval_day1": {DEMO: {d: up(d, 2_700.0) for d in DAYS}, PUZ: {d: up(d, 1_800.0) for d in DAYS[2:6]}},
          "campaigns": {DEMO: [{"id": "c1", "name": "Demo one", "status": "ENABLED", "cost_micros": 81_000 * RS}],
                        PUZ: [{"id": "c2", "name": "Puzzle one", "status": "ENABLED", "cost_micros": 18_000 * RS}]}}
    if fixed:
        sp["d1_fixed_till"] = fixed
    sp.update(kw)
    return sp


def _roas(tmp, final=None, next_fix=None, fixed="2026-01-04", ok=True):
    """cache (fixed till `fixed`) + a read (complete when ok; Google +1 % on the dates up to 4 Jan) → merge_spend →
    _spend_to_usd → build_roas with the dated $ view: the real build path. final None: a payload from before the D0
    fix."""
    d = tmp / "data"
    d.mkdir(exist_ok=True)
    (d / "fx_series.json").write_text(json.dumps({"INR": SERIES, "_ts": 1}))
    if final is None:
        sp = _raw()
    else:
        sp = google_ads.merge_spend(_raw(fixed=fixed), _raw(plus=0.01, d1_final_till=final, d1_ok=ok,
                                                            d1_next_fix_utc=next_fix, d1_lag_h=4), DAYS[0])
    return build_roas(_spend_to_usd(sp, NOW), IDS, CATALOG, daily_dated=_spend_daily_dated(sp, str(d)))


SOLO = "Solo Notes"                                  # an organic app: AdMob revenue, no Google Ads at all


def _organic(dash):
    dash = json.loads(json.dumps(dash))
    dash["apps_catalog"].append({"app_id": "ca-app-pub-0000000000000001~1000000003", "app_name": SOLO, "rev": 50,
                                 "account_id": "pub-0000000000000001"})
    dash["apps"].append(dict(dash["apps"][0], name=SOLO))
    dash["placements"].append(dict(dash["placements"][0], id="ca-app-pub-0000000000000001/3333333333", app=SOLO))
    return dash


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _zero(dash):
    dash = json.loads(json.dumps(dash))
    e = dash["roas"]["by_app"]["Puzzle Quest"]
    e["convval_day1_daily"] = {d: 0.0 for d in e["convval_day1_daily"]}
    dash["roas"]["d0"]["drift"]["pct"] = 0.0
    return dash


def _held(dash):
    dash = json.loads(json.dumps(dash))
    by = dash["roas"]["by_app"]
    by["Demo Gallery"]["d0_open"] = ["2026-01-04", "2026-01-05"]
    by["Puzzle Quest"].update(d0_open=["2026-01-05"], d0_wait=True)
    dash["roas"]["d0"]["fix_at"] = {"2026-01-04": "2026-01-05T22:30:00Z", "2026-01-05": "2026-01-06T22:30:00Z",
                                    "2026-01-06": "2099-01-06T22:30:00Z", "2026-01-07": "2099-01-07T23:30:00Z"}
    return dash


def _waitfwd(dash):
    dash = _held(dash)
    dash["roas"]["by_app"]["Demo Gallery"]["d0_wait"] = True
    return dash


# the "partial" payload: the cache fixed till 2 Jan, the latest read incomplete (one account's day-1 failed) with its
# final_till 5 Jan; its moment for 6 Jan is 12 h from now → 3–5 Jan are final already (the next complete refresh
# fixes them), 7 Jan is final 36 h from now. The node page runs on the real clock, so the moments are relative to it.
PART_NEXT = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(hours=12)


@pytest.fixture(scope="module")
def ov(tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    tmp = tmp_path_factory.mktemp("d0")
    fill = _dash(_roas(tmp, "2026-01-05", "2099-01-06T22:30:00Z"))
    fixed = _dash(_roas(tmp, "2026-01-07", "2026-01-08T22:30:00Z"))
    fx = {"app": "Demo Gallery",
          "fill": fill,                                                      # 6–7 Jan filling, fixes in the future
          "late": _dash(_roas(tmp, "2026-01-05", "2026-01-06T22:30:00Z")),    # its moment already passed
          "fixed": _dash(_roas(tmp, "2026-01-07", "2026-01-08T22:30:00Z")),   # the whole period fixed
          "nod0": _dash(_roas(tmp)),                                         # built before the D0 fix
          "organic": _organic(_dash(_roas(tmp, "2026-01-05", "2099-01-06T22:30:00Z"))),
          "partial": _dash(_roas(tmp, "2026-01-05", _iso(PART_NEXT), fixed="2026-01-02", ok=False)),
          # a cache from before the D0 fix whose reads have all been incomplete: nothing fixed yet
          "nofixed": _dash(_roas(tmp, "2026-01-05", "2099-01-06T22:30:00Z", fixed=None, ok=False)),
          # Puzzle's D0 fixed at 0 on every day (spend, no value within 24 h); the drift measured at 0.0 %
          "zero": _zero(fixed),
          # Demo has dates ≤ fixed_till still open (an account in a later zone) and the backend's own moment for 7 Jan
          # (fix_at) an hour after the 24 h step; Puzzle waits for an account that cannot answer (d1_open "wait")
          "wait": _held(fill),
          # Demo waits for an unread account too, and its last pending date (7 Jan) is after fixed_till, not final yet
          "waitfwd": _waitfwd(fill)}
    assert "d0" not in fx["nod0"]["roas"] and fx["fill"]["roas"]["d0"]["drift"]["pct"] == 1.0
    assert fx["nofixed"]["roas"]["d0"] == {"lag_h": 4, "incomplete": True}
    assert "incomplete" not in fx["fill"]["roas"]["d0"] and fx["partial"]["roas"]["d0"]["incomplete"] is True
    assert fx["partial"]["roas"]["d0"]["fixed_till"] == "2026-01-02"
    assert fx["partial"]["roas"]["d0"]["next_fix_utc"] == _iso(PART_NEXT - timedelta(days=3))     # 3 Jan's moment
    (tmp / "fx.json").write_text(json.dumps(fx))
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        script = max(re.findall(r"<script>(.*?)</script>", f.read(), re.S), key=len)
    (tmp / "app.js").write_text(script, encoding="utf-8")
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "roas_fx_frontend.js"), str(tmp / "app.js"),
                          str(tmp / "fx.json")], check=True, capture_output=True, text=True, timeout=300)
    rep = json.loads(out.stdout)
    assert rep["errors"] == []
    return {k: v["ov"] for k, v in rep["other"].items()} | {"_fx": fx}


def _cells(h):
    """{app: (title attr | None, [line texts]) of the D0 rev cell} of the Revenue-by-app table."""
    out = {}
    for tr in re.findall(r'<tr class="clk"[^>]*>(.*?)</tr>', h, re.S):
        tds = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        name = next(n for n in ("Demo Gallery", "Puzzle Quest", SOLO) if n in TAG.sub("", tds[0][1]))
        attrs, body = tds[4]
        t = re.search(r'title="([^"]*)"', attrs)
        lines = [TAG.sub("", x).strip() for x in re.split(r"<div[^>]*>", body)]
        out[name] = (t.group(1) if t else None, [x for x in lines if x])
    return out


def _d0_roas(fx, app):
    e = fx["roas"]["by_app"][app]
    return sum(e["convval_day1_daily"].get(d, 0) for d in WIN) / (sum(e["daily"].get(d, 0) for d in WIN) / 1e6)


def test_overview_heads_say_d0(ov):
    for k in ("fill", "nod0"):
        for view in ("USD", "INR"):
            h = ov[f"{k}|{view}"]
            assert "<th>D0 rev<div" in h and ">Google Ads · first 24h</div>" in h
            assert "Day-1" not in h and "frozen" not in h
            assert h.count("Rev − D0") == 3            # the Old revenue tile, the app table, the date-wise table


def test_d0_number_and_roas_in_both_views(ov):
    for k in ("fill", "fixed", "nod0"):
        fx = ov["_fx"][k]
        usd, inr = _cells(ov[f"{k}|USD"]), _cells(ov[f"{k}|INR"])
        # by hand (₹90 a dollar): Demo ₹2,700 × 8 days = ₹21,600 ($240) ÷ ₹72,000 spend → 0.30×; Puzzle ₹1,800 × 4 =
        # ₹7,200 ($80) ÷ ₹18,000 → 0.40× — Google Ads' own ₹ ÷ ₹, in both views
        assert usd["Demo Gallery"][1][:2] == ["$240", "0.30×"] and inr["Demo Gallery"][1][:2] == ["₹21,600", "0.30×"]
        assert usd["Puzzle Quest"][1][:2] == ["$80", "0.40×"] and inr["Puzzle Quest"][1][:2] == ["₹7,200", "0.40×"]
        for app in ("Demo Gallery", "Puzzle Quest"):
            assert usd[app][1][1] == "%.2f×" % _d0_roas(fx, app)                 # Σ D0 ÷ Σ one-rate spend
    # the Spend + ROAS cell in $ reads the dated view (each day at its own rate: another ROAS); the D0 ROAS does not
    spend_roas = lambda h: re.search(r'<td style="font-weight:700">[^<]*<div class="(?:up|down)"[^>]*>([\d.]+×)</div>', h).group(1)
    assert spend_roas(ov["fill|USD"]) != spend_roas(ov["fill|INR"])
    assert re.search(r'<div class="muted" style="font-size:11px;margin-top:2px">0\.30×</div>', ov["fill|USD"])    # neutral


def test_filling_line_and_tooltip(ov):
    c = _cells(ov["fill|USD"])
    tip, lines = c["Demo Gallery"]
    assert lines[2:] == ["⏳ filling"]
    assert tip == ("Google Ads ka D0 = click ke pehle 24 ghante ki value. 2 din (6 Jan–7 Jan) abhi bhar raha hai — "
                   "~8 Jan, 04:00 IST ke baad fix, phir ye number nahi badlega.")
    tip, lines = c["Puzzle Quest"]                                  # its dates end 5 Jan: all fixed
    # the drift is all apps' together (merge_spend measures it so) — the tooltip says so, never as this app's own
    assert len(lines) == 2 and tip == ("Fixed — ye number ab nahi badlega. Fix ke baad Google Ads ne (sab apps milake, "
                                       "pichhle 5 fixed din) +1.0% aur joda (late events); fix wala number nahi badla.")
    assert _cells(ov["fill|INR"])["Demo Gallery"] == (c["Demo Gallery"][0], ["₹21,600", "0.30×", "⏳ filling"])
    late = _cells(ov["late|USD"])["Demo Gallery"]
    assert late[1][2:] == ["⏳ filling"] and late[0].endswith("abhi bhar raha hai — agle refresh me fix, phir ye number nahi badlega.")


def test_all_fixed_and_no_d0_payload(ov):
    for view in ("USD", "INR"):
        c = _cells(ov[f"fixed|{view}"])
        for app in ("Demo Gallery", "Puzzle Quest"):
            assert len(c[app][1]) == 2 and c[app][0].startswith("Fixed — ye number ab nahi badlega.")
        assert "⏳" not in ov[f"fixed|{view}"]
        n = _cells(ov[f"nod0|{view}"])
        assert all(t is None and len(lines) == 2 for t, lines in n.values())
        assert "⏳" not in ov[f"nod0|{view}"] and "ye number" not in ov[f"nod0|{view}"]


def test_a_plain_dash_gets_no_tooltip(ov):
    """No D0 and nothing filling (an organic app; a Google Ads app with no day in the period): '—' as before — no
    tooltip about Google Ads numbers the app does not have."""
    for view in ("USD", "INR"):
        h = ov[f"organic|{view}"]
        c = _cells(h)
        assert c[SOLO] == (None, ["—"])
        assert re.search(r'<td>—</td>', h)
        assert c["Demo Gallery"][1][2:] == ["⏳ filling"] and c["Puzzle Quest"][0].startswith("Fixed")


def test_an_incomplete_read_never_puts_the_fix_time_days_late(ov):
    c = _cells(ov["partial|USD"])
    tip, lines = c["Puzzle Quest"]                  # 3–5 Jan pending, all final by Google's clock already
    assert lines[2:] == ["⏳ filling"]
    # … but the latest read fixed nothing (incomplete): no "agle refresh me fix" promise — it holds only with a full read
    assert tip == ("Google Ads ka D0 = click ke pehle 24 ghante ki value. 3 din (3 Jan–5 Jan) abhi bhar raha hai — "
                   "pichhle refresh me Google Ads ka poora D0 read nahi mila; poora read milte hi fix, phir ye number "
                   "nahi badlega.")
    at = PART_NEXT + timedelta(days=1, hours=5, minutes=30)            # 7 Jan's moment (6 Jan's + 1 day), in IST
    tip, lines = c["Demo Gallery"]
    assert lines[2:] == ["⏳ filling"]
    assert tip == ("Google Ads ka D0 = click ke pehle 24 ghante ki value. 5 din (3 Jan–7 Jan) abhi bhar raha hai — "
                   "~%d %s, %s IST ke baad fix, phir ye number nahi badlega." % (at.day, at.strftime("%b"),
                                                                                at.strftime("%H:%M")))


def test_nothing_fixed_yet_says_so(ov):
    """roas.d0 without fixed_till (every read so far incomplete): Google's live number, '⏳ filling' on every app with a
    D0 or spend day in the period, and a tooltip that claims no fixing time."""
    for view in ("USD", "INR"):
        h = ov[f"nofixed|{view}"]
        c = _cells(h)
        assert c["Puzzle Quest"][0] == ("Google Ads ka D0 = click ke pehle 24 ghante ki value. Abhi tak koi din fix nahi "
                                        "hua (Google Ads ka poora read abhi nahi mila) — 4 din (2 Jan–5 Jan) ka number "
                                        "abhi badal sakta hai.")
        assert all(lines[2:] == ["⏳ filling"] for _, lines in c.values()), c
        assert "Fixed" not in h and "ke baad fix" not in h


def test_a_paid_app_fixed_at_zero_shows_zero(ov):
    for view, z in (("USD", "$0"), ("INR", "₹0")):
        c = _cells(ov[f"zero|{view}"])
        tip, lines = c["Puzzle Quest"]
        assert lines == [z, "0.00×"]
        assert tip == ("Fixed — ye number ab nahi badlega. Fix ke baad Google Ads ka number (sab apps milake, pichhle 5 "
                       "fixed din) nahi badla.")
    org = _cells(ov["organic|USD"])[SOLO]
    assert org == (None, ["—"])                                     # no spend: '—' as before


def test_open_dates_a_waiting_account_and_the_backends_moment(ov):
    for view in ("USD", "INR"):
        c = _cells(ov[f"wait|{view}"])
        tip, lines = c["Demo Gallery"]                              # 4–5 Jan ≤ fixed_till but still open for it
        assert lines[2:] == ["⏳ filling"]
        assert tip == ("Google Ads ka D0 = click ke pehle 24 ghante ki value. 4 din (4 Jan–7 Jan) abhi bhar raha hai — "
                       "~8 Jan, 05:00 IST ke baad fix, phir ye number nahi badlega.")       # fix_at, not the 24 h step
        tip, lines = c["Puzzle Quest"]
        assert lines[2:] == ["⏳ filling"]
        assert tip == ("Google Ads ka D0 = click ke pehle 24 ghante ki value. 5 Jan abhi bhar raha hai — is app ka ek "
                       "Google Ads account abhi read nahi ho raha (access); wapas read hote hi fix, phir ye number nahi "
                       "badlega.")
    assert "~8 Jan, 04:00 IST ke baad fix" in _cells(ov["fill|USD"])["Demo Gallery"][0]    # no fix_at: the 24 h step


def test_a_waiting_app_with_a_date_not_final_yet_gives_its_time(ov):
    """A waiting app's last pending date after fixed_till is fixed only at its own moment, not as soon as the account is
    read again: the tooltip says both. Puzzle (its last date's moment passed): "wapas read hote hi fix" as before."""
    for view in ("USD", "INR"):
        c = _cells(ov[f"waitfwd|{view}"])
        tip, lines = c["Demo Gallery"]
        assert lines[2:] == ["⏳ filling"]
        assert tip == ("Google Ads ka D0 = click ke pehle 24 ghante ki value. 4 din (4 Jan–7 Jan) abhi bhar raha hai — "
                       "is app ka ek Google Ads account abhi read nahi ho raha (access); account wapas read hone par aur "
                       "~8 Jan, 05:00 IST ke baad fix, phir ye number nahi badlega.")
        assert c["Puzzle Quest"][0].endswith("(access); wapas read hote hi fix, phir ye number nahi badlega.")
