"""Google Ads D0 ("D0 rev": the value of conversions within 24 h of the click — the day-1 lag bucket) FIXED once
complete (owner: "fix D0 ye panel me", Google Ads reports ~3-4 h late). Click date X (the account's time zone) is
final from (X+2 00:00 local) + GADS_D0_LAG_HOURS on (google_ads.d0_final); fetch_app_spend says which dates are final
for its read (and whether every asked account answered the day-1 query); merge_spend keeps a fixed date's number for
good, measures how far Google's later number drifts (a percentage only), and logs counts only; build_roas carries
"d0" to the page; the per-campaign store compares day-1 only on the days not fixed yet. Frontend: the Overview
"Revenue by app" table's "D0 rev" column (number, D0 ROAS = Σ D0 ÷ Σ one-rate spend, "⏳ filling" + the Hinglish
tooltip) run for real by tests/roas_fx_frontend.js. Its second line ("Do line, ek box"): the install-day "Day" D0 —
Google Ads' same <1-day value as it stood the next morning ((date+1 00:00) + the lag: google_ads.d0_day), taken ONCE by
merge_spend from the first complete read at most GADS_D0_DAY_MAX_LATE_H after it and never changed (sections 8-9).
Every name, id, rate and amount is SYNTHETIC; the expected numbers are worked out by hand below."""

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
from tests.gads_fake import A1, A2, A3, S1, S2, SETTINGS, TOK, FakeAds
from tests.test_roas_fx_dated import CATALOG, DAYS, IDS, NOW, SERIES, TODAY, _dash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
TAG = re.compile(r"<[^>]*>")
IST, LA = {"tz": "Asia/Calcutta"}, {"tz": "America/Los_Angeles"}
LINE = re.compile(r"^roas: D0 fixed till (\d{4}-\d{2}-\d{2}|none) · \d+ store-days fixed this run"
                  r"( · \d+ store-days still open)?( · Day \d{4}-\d{2}-\d{2} captured: \d+ stores)*"
                  r"( \(day-1 read incomplete: not moved\))?$")


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _lag(monkeypatch):
    monkeypatch.delenv("GADS_D0_LAG_HOURS", raising=False)
    monkeypatch.delenv("GADS_D0_DAY_MAX_LATE_H", raising=False)


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


def test_an_account_with_no_click_left_to_wait_for_holds_nobody_back():
    """last: {account: its last click day}. An account in a later zone that stopped spending before its own final
    day has no D0 left to wait for: the earlier zone's dates are fixed on time (else one idle account in a later zone
    would hold every earlier-zone app back by hours). It counts again as soon as it has a click on a date not final in
    its zone; an account missing from `last` (no click in the read) counts for nothing; nobody left: the accounts with
    the latest click day; no click anywhere: all of them."""
    now = utc("2026-01-03T00:00")                    # IST has 1 Jan final, LA not yet
    ist, la = dict(IST, id="1"), dict(LA, id="2")
    got = google_ads.d0_final([ist, la], now, last={"1": "2026-01-02", "2": "2025-12-20"})
    assert got["final_till"] == "2026-01-01" and got["zones"] == ["Asia/Calcutta"]
    assert got["ended"] == ["America/Los_Angeles"]
    assert got["next_fix_utc"] == "2026-01-03T22:30:00Z"                       # IST's moment for 2 Jan
    late = google_ads.d0_final([ist, la], now, last={"1": "2026-01-02", "2": "2026-01-01"})   # LA clicked on 1 Jan
    assert late["final_till"] == "2025-12-31" and late["zones"] == ["America/Los_Angeles", "Asia/Calcutta"]
    assert "ended" not in late
    assert google_ads.d0_final([ist, la], now, last={"1": "2026-01-02"}) == got                # LA: no cost at all
    assert google_ads.d0_final([ist, la], now, last={}) == google_ads.d0_final([ist, la], now)   # no click: all of them
    assert google_ads.d0_final([ist, la], now, last=None)["final_till"] == "2025-12-31"
    # IST's last click (1 Jan) is final too: nobody waits — IST's zone still decides, not LA's (which ends later)
    assert google_ads.d0_final([ist, la], now, last={"1": "2026-01-01", "2": "2025-12-20"}) == got


def test_the_promised_moment_is_kept_when_the_last_waiting_account_stops():
    """The IST account stops after 8 Jan, the New York one stopped on 2 Jan. The read before IST's moment for 8 Jan
    promises it (next_fix_utc); with no new data, the read at that moment fixes 8 Jan — the idle New York zone does
    not come back and hold it until 10 Jan 09:00 UTC (an account that stops is not fixed later than one that goes on)."""
    accs = [{"id": "i", "tz": "Asia/Calcutta"}, {"id": "n", "tz": "America/New_York"}]
    last = {"i": "2026-01-08", "n": "2026-01-02"}
    before = google_ads.d0_final(accs, utc("2026-01-09T22:00"), 4, last=last)
    assert before["final_till"] == "2026-01-07" and before["next_fix_utc"] == "2026-01-09T22:30:00Z"
    at = google_ads.d0_final(accs, utc("2026-01-09T22:30"), 4, last=last)
    assert at["final_till"] == "2026-01-08" and at["zones"] == ["Asia/Calcutta"]
    assert at == google_ads.d0_final(accs, utc("2026-01-09T22:30"), 4, last=dict(last, i="2026-01-09"))
    fresh = _fresh({}, final=before["final_till"], **{"d1_" + k: v for k, v in before.items() if k != "final_till"})
    m = google_ads.merge_spend(None, fresh, "2026-01-01")
    assert m["d1_next_fix_utc"] == m["d1_fix_at"]["2026-01-08"] == "2026-01-09T22:30:00Z"


@pytest.mark.parametrize("zones", [("Asia/Calcutta", "America/New_York"), ("Pacific/Kiritimati", "Pacific/Pago_Pago"),
                                   ("Pacific/Auckland", "Pacific/Honolulu"), ("Asia/Calcutta", None)])
def test_with_last_the_moment_is_exact_and_the_date_never_moves_back(zones):
    """No new data, every 50 min over 6 days, accounts stopping on the way: final_till moves on exactly at next_fix_utc
    (by one day, not a minute before) and never back."""
    accs = [{"id": str(i), "tz": z} for i, z in enumerate(zones)]
    for last in ({"0": "2026-01-05", "1": "2025-12-30"}, {"0": "2026-01-04", "1": "2026-01-06"},
                 {"0": "2026-01-06"}, {"0": "2025-12-30", "1": "2025-12-30"}, {"0": "9999-12-31", "1": "2025-12-30"}):
        t, prev = utc("2026-01-03T00:00"), None
        while t < utc("2026-01-09T00:00"):
            r = google_ads.d0_final(accs, t, 4, last=last)
            nf, nxt = utc(r["next_fix_utc"][:-1]), date.fromisoformat(r["final_till"]) + timedelta(days=1)
            assert nf > t and google_ads.d0_final(accs, nf - timedelta(minutes=1), 4, last=last)["final_till"] == \
                r["final_till"], (zones, last, t)
            assert google_ads.d0_final(accs, nf, 4, last=last)["final_till"] == nxt.isoformat(), (zones, last, t)
            assert prev is None or r["final_till"] >= prev, (zones, last, t)
            prev = r["final_till"]
            t += timedelta(minutes=50)


def test_a_left_out_zone_a_day_behind_still_caps_the_date_until_its_day_ended_lag_hours_ago():
    """Kiritimati (UTC+14) spends, Pago Pago (UTC−11, 25 h behind) has been idle. "No cost row" stands for "no click"
    only once a late cost row would show: 8 Jan is fixed once it ended in Pago Pago lag h ago (9 Jan 15:00 UTC), not at
    Kiritimati's moment (14:00 UTC, before Pago Pago's 8 Jan has ended + 4 h). merge_spend's moments follow it."""
    accs = [{"id": "k", "tz": "Pacific/Kiritimati"}, {"id": "p", "tz": "Pacific/Pago_Pago"}]
    last = {"k": "9999-12-31", "p": "2025-12-20"}
    r = google_ads.d0_final(accs, utc("2026-01-09T14:30"), 4, last=last)
    assert google_ads.d0_final(accs[:1], utc("2026-01-09T14:30"), 4)["final_till"] == "2026-01-08"
    assert r["final_till"] == "2026-01-07" and r["zones"] == ["Pacific/Kiritimati"]
    assert r["ended"] == ["Pacific/Pago_Pago"]
    assert r["next_fix_utc"] == "2026-01-09T15:00:00Z"
    assert google_ads.d0_final(accs, utc("2026-01-09T15:00"), 4, last=last)["final_till"] == "2026-01-08"
    lag0 = google_ads.d0_final(accs, utc("2026-01-09T10:30"), 0, last=last)        # no lag: not before the day ended
    assert lag0["final_till"] == "2026-01-07" and lag0["next_fix_utc"] == "2026-01-09T11:00:00Z"
    fresh = _fresh({}, final=r["final_till"], **{"d1_" + k: v for k, v in r.items() if k != "final_till"})
    m = google_ads.merge_spend(_cache({}, fixed="2026-01-07"), fresh, "2026-01-01")
    assert m["d1_next_fix_utc"] == m["d1_fix_at"]["2026-01-08"] == "2026-01-09T15:00:00Z"
    assert m["d1_fix_at"]["2026-01-09"] == "2026-01-10T15:00:00Z"
    # IST + New York (9.5-10.5 h apart): the cap never binds — the rule as without it
    ist_ny = [{"id": "i", "tz": "Asia/Calcutta"}, {"id": "n", "tz": "America/New_York"}]
    t = utc("2026-01-05T00:00")
    while t < utc("2026-01-07T00:00"):
        assert google_ads.d0_final(ist_ny, t, 4, last={"i": "9999-12-31", "n": "2025-12-20"})["final_till"] == \
            google_ads.d0_final(ist_ny[:1], t, 4)["final_till"]
        t += timedelta(minutes=30)


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


def test_fetch_an_account_that_stopped_spending_in_a_later_zone_holds_nobody_back(monkeypatch):
    fake = FakeAds()
    fake.accounts[A1]["tz"] = "America/Los_Angeles"
    for c in fake.camps[A1].values():
        c["hi"] = "2026-01-04"                        # A1's last click: 4 Jan, long final in its own zone
    now = utc("2026-01-10T23:00")
    out = _fetch(monkeypatch, fake, now)
    assert out["d1_final_till"] == "2026-01-09" and out["d1_zones"] == ["Asia/Calcutta"]
    for c in fake.camps[A1].values():
        c["hi"] = "2026-12-31"                        # A1 clicks again: its later zone holds the date back
    assert _fetch(monkeypatch, fake, now)["d1_final_till"] == "2026-01-08"
    fake.fail = lambda acct, kind, q: "HTTP 500: synthetic" if acct == A1 and kind == "SPEND" else None
    assert _fetch(monkeypatch, fake, now)["d1_final_till"] == "2026-01-08"      # its clicks unknown: it counts


@pytest.mark.parametrize("hide, zero, final", [
    (("SPEND",), (), "2026-01-08"),                   # its D0 and installs rows go on past its last cost row
    (("SPEND", "D1"), (), "2026-01-08"),              # installs / conversion value alone: a click too
    (("SPEND", "INST"), (), "2026-01-08"),            # D0 alone
    (("SPEND", "D1"), ("INST",), "2026-01-09"),       # an installs row with nothing in it is no click
    (("SPEND", "D1", "INST"), (), "2026-01-09"),      # nothing after 4 Jan: it holds nobody back
])
def test_fetch_a_conversion_on_a_date_without_a_cost_row_is_a_click_too(monkeypatch, hide, zero, final):
    """A later-zone account's last cost row is 4 Jan, but Google shows D0 / installs on later click dates (a cost row
    late or never there): those dates count as its clicks, so its zone holds them back as for any spending account."""
    fake = FakeAds()
    fake.accounts[A1]["tz"] = "America/Los_Angeles"
    rows = fake.metric_rows

    def metric_rows(acct, kind, a, b):
        out = rows(acct, kind, a, b)
        if acct != A1:
            return out
        if kind in zero:
            out = [dict(r, metrics={k: 0 for k in r["metrics"]}) if r["segments"]["date"] > "2026-01-04" else r
                   for r in out]
        return [r for r in out if kind not in hide or r["segments"]["date"] <= "2026-01-04"]
    monkeypatch.setattr(fake, "metric_rows", metric_rows)
    out = _fetch(monkeypatch, fake, utc("2026-01-10T23:00"))
    assert out["d1_ok"] is True and out["d1_final_till"] == final
    assert out["d1_zones"] == (["America/Los_Angeles", "Asia/Calcutta"] if final == "2026-01-08" else ["Asia/Calcutta"])


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

    def final(acc, now=None, lag_h=None, last=None):
        seen["final"].append(now)
        return real_final(acc, now, lag_h, last)
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


# the install-day ("Day") D0 the cache took on earlier mornings (₹): Demo's 2 and 4 Jan were not taken (its store waited
# for an unread account then), Puzzle has every one of its spend days; each date's read: X+1 04:0i IST
DAY_CACHE = {DEMO: {"2026-01-03": 2_430.0, "2026-01-05": 2_520.0},
             PUZ: {"2026-01-02": 1_620.0, "2026-01-03": 1_710.0, "2026-01-04": 1_530.0, "2026-01-05": 1_440.0}}
DAY_READ = {"2026-01-0%d" % i: "2026-01-0%dT22:3%d:00Z" % (i, i) for i in range(2, 6)}


def _roas_day(tmp, final, next_fix, day_next, taken=True):
    """_roas's real build path with the Day D0: the cache holds DAY_CACHE / DAY_READ, and this read is 6 Jan's
    morning read (complete and on time: Demo's ₹2,700 is taken; Puzzle has no 6 Jan). day_next: 7 Jan's Day moment (the
    page runs on the real clock). taken False: nothing taken yet — no Day number in the cache, and this read is too late
    for 6 Jan (the page's "Day number abhi shuru nahi hua")."""
    d = tmp / "data"
    d.mkdir(exist_ok=True)
    (d / "fx_series.json").write_text(json.dumps({"INR": SERIES, "_ts": 1}))
    cache = _raw(fixed="2026-01-04", **({"convval_d0day": DAY_CACHE, "d1_day_read": DAY_READ} if taken else {}))
    e = {"date": "2026-01-06", "at": "2026-01-06T22:30:00Z", "next": _iso(day_next), "ok": taken}
    day = dict(e, late_h=3, read="2026-01-06T22:41:00Z", stores={DEMO: dict(e), PUZ: dict(e)})
    sp = google_ads.merge_spend(cache, _raw(plus=0.01, d1_final_till=final, d1_ok=True, d1_next_fix_utc=next_fix,
                                            d1_lag_h=4, d1_day=day), DAYS[0])
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
# 7 Jan's Day moment passed an hour ago (its morning read can still come: the limit is 3 h) / 4 h ago (missed)
DAY_LATE, DAY_MISS = (PART_NEXT - timedelta(hours=h) for h in (13, 16))


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
          "waitfwd": _waitfwd(fill),
          # the Day D0 (_roas_day): 24h filling as "fill" + 7 Jan's Day still to come; 24h fixed + 7 Jan's Day to come,
          # its moment passed but the morning read can still come, or missed; no Day number taken yet
          "day": _dash(_roas_day(tmp, "2026-01-05", "2099-01-06T22:30:00Z", PART_NEXT)),
          "dayfixed": _dash(_roas_day(tmp, "2026-01-07", "2026-01-08T22:30:00Z", PART_NEXT)),
          "daylate": _dash(_roas_day(tmp, "2026-01-07", "2026-01-08T22:30:00Z", DAY_LATE)),
          "daymiss": _dash(_roas_day(tmp, "2026-01-07", "2026-01-08T22:30:00Z", DAY_MISS)),
          "nostart": _dash(_roas_day(tmp, "2026-01-05", "2099-01-06T22:30:00Z", PART_NEXT, taken=False))}
    # Day: Demo with 5 Jan not taken too (4 missed dates, not in a row); Demo's stores in a later zone (its own moment
    # for 7 Jan still ahead) while every account's passed; realistic zones' moments (a later zone; one ahead of IST)
    fx["dayholes"] = json.loads(json.dumps(fx["daymiss"]))
    del fx["dayholes"]["roas"]["by_app"]["Demo Gallery"]["convval_d0day_daily"]["2026-01-05"]
    fx["dayzone"] = json.loads(json.dumps(fx["daymiss"]))
    fx["dayzone"]["roas"]["by_app"]["Demo Gallery"]["d0day_next"] = {"date": "2026-01-07", "at": _iso(PART_NEXT)}
    fx["daylater"] = json.loads(json.dumps(fx["daymiss"]))
    by = fx["daylater"]["roas"]["by_app"]
    by["Demo Gallery"]["d0day_next"] = {"date": "2026-01-07", "at": "2026-01-08T12:00:00Z"}     # 17:30 IST, 8 Jan
    by["Puzzle Quest"]["d0day_next"] = {"date": "2026-01-06", "at": "2026-01-06T17:00:00Z"}     # 22:30 IST, 6 Jan
    assert "d0" not in fx["nod0"]["roas"] and fx["fill"]["roas"]["d0"]["drift"]["pct"] == 1.0
    assert fx["nofixed"]["roas"]["d0"] == {"lag_h": 4, "incomplete": True}
    assert "incomplete" not in fx["fill"]["roas"]["d0"] and fx["partial"]["roas"]["d0"]["incomplete"] is True
    assert fx["partial"]["roas"]["d0"]["fixed_till"] == "2026-01-02"
    assert fx["partial"]["roas"]["d0"]["next_fix_utc"] == _iso(PART_NEXT - timedelta(days=3))     # 3 Jan's moment
    assert not any(k.startswith("day_") for k in fx["fill"]["roas"]["d0"])                       # no Day number yet
    assert fx["day"]["roas"]["d0"]["day_since"] == "2026-01-02" and "day_read" not in fx["nostart"]["roas"]["d0"]
    assert fx["nostart"]["roas"]["d0"]["day_next"] == {"date": "2026-01-07", "at": _iso(PART_NEXT), "late_h": 3}
    assert fx["day"]["roas"]["by_app"]["Demo Gallery"]["d0day_next"] == {"date": "2026-01-07", "at": _iso(PART_NEXT)}
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


PRE = "24h = har install ke click ke 24 ghante ki value (Google Ads). "        # the tooltip's 24h part starts so
DAY_PRE = "Day = install ke din raat 12 baje tak — agle din subah ka Google Ads number."   # (no Day read time known)


def _t24(tip):
    """The tooltip's 24h part (its first line)."""
    return tip.split("\n")[0]


def _tday(tip):
    """The tooltip's Day part (its last line)."""
    return tip.split("\n")[-1]


def _d0_roas(fx, app):
    e = fx["roas"]["by_app"][app]
    return sum(e["convval_day1_daily"].get(d, 0) for d in WIN) / (sum(e["daily"].get(d, 0) for d in WIN) / 1e6)


def test_overview_heads_say_d0(ov):
    for k, sub in (("fill", "24h / Day"), ("day", "24h / Day"), ("nod0", "first 24h")):     # data before the D0 fix:
        for view in ("USD", "INR"):                                                         # as before
            h = ov[f"{k}|{view}"]
            assert "<th>D0 rev<div" in h and ">Google Ads · %s</div>" % sub in h
            assert "Day-1" not in h and "frozen" not in h
            assert h.count("Rev − D0") == 3            # the Old revenue tile, the app table, the date-wise table


def test_d0_number_and_roas_in_both_views(ov):
    for k in ("fill", "fixed", "day", "nod0"):
        fx = ov["_fx"][k]
        usd, inr = _cells(ov[f"{k}|USD"]), _cells(ov[f"{k}|INR"])
        # by hand (₹90 a dollar): Demo ₹2,700 × 8 days = ₹21,600 ($240) ÷ ₹72,000 spend → 0.30×; Puzzle ₹1,800 × 4 =
        # ₹7,200 ($80) ÷ ₹18,000 → 0.40× — Google Ads' own ₹ ÷ ₹, in both views. Line 1 ("24h"); before the D0 fix
        # (nod0): the number and the ROAS on lines of their own, as before
        one = (lambda c, a: c[a][1][:2]) if k == "nod0" else (lambda c, a: c[a][1][0].split(" ")[1::2])
        assert one(usd, "Demo Gallery") == ["$240", "0.30×"] and one(inr, "Demo Gallery") == ["₹21,600", "0.30×"]
        assert one(usd, "Puzzle Quest") == ["$80", "0.40×"] and one(inr, "Puzzle Quest") == ["₹7,200", "0.40×"]
        for app in ("Demo Gallery", "Puzzle Quest"):
            assert one(usd, app)[1] == "%.2f×" % _d0_roas(fx, app)                 # Σ D0 ÷ Σ one-rate spend
            if k != "nod0":
                assert usd[app][1][0] == "24h %s · %s" % tuple(one(usd, app))
    # the Spend + ROAS cell in $ reads the dated view (each day at its own rate: another ROAS); the D0 ROAS does not
    spend_roas = lambda h: re.search(r'<td style="font-weight:700">[^<]*<div class="(?:up|down)"[^>]*>([\d.]+×)</div>', h).group(1)
    assert spend_roas(ov["fill|USD"]) != spend_roas(ov["fill|INR"])
    assert re.search(r'<span class="muted" style="font-size:11px">· 0\.30×</span>', ov["fill|USD"])    # neutral
    assert re.search(r'<div class="muted" style="font-size:11px;margin-top:2px">0\.30×</div>', ov["nod0|USD"])


def test_filling_line_and_tooltip(ov):
    c = _cells(ov["fill|USD"])
    tip, lines = c["Demo Gallery"]
    assert lines[1:] == ["Day —", "⏳ 24h filling"]                # data without a Day number yet: only 24h fills
    assert _t24(tip) == (PRE + "2 din (6 Jan–7 Jan) abhi bhar raha hai — "
                         "~8 Jan, 04:00 IST ke baad fix, phir ye number nahi badlega.")
    # data from before the Day number (no moment, nothing taken): no date named — today's still has its morning ahead
    assert _tday(tip) == (DAY_PRE + " Day number abhi shuru nahi hua (Google Ads subah wala purana number nahi rakhta) "
                          "— pehla number agli subah ke read se aayega.")
    tip, lines = c["Puzzle Quest"]                                  # its dates end 5 Jan: all fixed
    # the drift is all apps' together (merge_spend measures it so) — the tooltip says so, never as this app's own
    assert lines == ["24h $80 · 0.40×", "Day —"] and _t24(tip) == (
        PRE + "Fixed — ye number ab nahi badlega. Fix ke baad Google Ads ne (sab apps milake, "
        "pichhle 5 fixed din) +1.0% aur joda (late events); fix wala number nahi badla.")
    assert _cells(ov["fill|INR"])["Demo Gallery"] == (c["Demo Gallery"][0], ["24h ₹21,600 · 0.30×", "Day —",
                                                                             "⏳ 24h filling"])
    late = _cells(ov["late|USD"])["Demo Gallery"]
    assert late[1][2:] == ["⏳ 24h filling"]
    assert _t24(late[0]).endswith("abhi bhar raha hai — agle refresh me fix, phir ye number nahi badlega.")


def test_all_fixed_and_no_d0_payload(ov):
    for view in ("USD", "INR"):
        c = _cells(ov[f"fixed|{view}"])
        for app in ("Demo Gallery", "Puzzle Quest"):
            assert len(c[app][1]) == 2 and c[app][0].startswith(PRE + "Fixed — ye number ab nahi badlega.")
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
        assert c["Demo Gallery"][1][2:] == ["⏳ 24h filling"] and c["Puzzle Quest"][0].startswith(PRE + "Fixed")


def test_an_incomplete_read_never_puts_the_fix_time_days_late(ov):
    c = _cells(ov["partial|USD"])
    tip, lines = c["Puzzle Quest"]                  # 3–5 Jan pending, all final by Google's clock already
    assert lines[2:] == ["⏳ 24h filling"]
    # … but the latest read fixed nothing (incomplete): no "agle refresh me fix" promise — only with a full read
    assert _t24(tip) == (PRE + "3 din (3 Jan–5 Jan) abhi bhar raha hai — "
                         "pichhle refresh me Google Ads ka poora D0 read nahi mila; poora read milte hi fix, phir ye "
                         "number nahi badlega.")
    at = PART_NEXT + timedelta(days=1, hours=5, minutes=30)            # 7 Jan's moment (6 Jan's + 1 day), in IST
    tip, lines = c["Demo Gallery"]
    assert lines[2:] == ["⏳ 24h filling"]
    assert _t24(tip) == (PRE + "5 din (3 Jan–7 Jan) abhi bhar raha hai — "
                         "~%d %s, %s IST ke baad fix, phir ye number nahi badlega." % (at.day, at.strftime("%b"),
                                                                                      at.strftime("%H:%M")))


def test_nothing_fixed_yet_says_so(ov):
    """roas.d0 without fixed_till (every read so far incomplete): Google's live number, '⏳ filling' on every app with a
    D0 or spend day in the period, and a tooltip that claims no fixing time."""
    for view in ("USD", "INR"):
        h = ov[f"nofixed|{view}"]
        c = _cells(h)
        assert _t24(c["Puzzle Quest"][0]) == (PRE + "Abhi tak koi din fix nahi hua (Google Ads ka poora read abhi "
                                              "nahi mila) — 4 din (2 Jan–5 Jan) ka number abhi badal sakta hai.")
        assert all(lines[2:] == ["⏳ 24h filling"] for _, lines in c.values()), c
        assert "Fixed" not in h and "ke baad fix" not in h


def test_a_paid_app_fixed_at_zero_shows_zero(ov):
    for view, z in (("USD", "$0"), ("INR", "₹0")):
        c = _cells(ov[f"zero|{view}"])
        tip, lines = c["Puzzle Quest"]
        assert lines == ["24h %s · 0.00×" % z, "Day —"]
        assert _t24(tip) == (PRE + "Fixed — ye number ab nahi badlega. Fix ke baad Google Ads ka number (sab apps "
                             "milake, pichhle 5 fixed din) nahi badla.")
    org = _cells(ov["organic|USD"])[SOLO]
    assert org == (None, ["—"])                                     # no spend: '—' as before


def test_open_dates_a_waiting_account_and_the_backends_moment(ov):
    for view in ("USD", "INR"):
        c = _cells(ov[f"wait|{view}"])
        tip, lines = c["Demo Gallery"]                              # 4–5 Jan ≤ fixed_till but still open for it
        assert lines[2:] == ["⏳ 24h filling"]
        assert _t24(tip) == (PRE + "4 din (4 Jan–7 Jan) abhi bhar raha hai — "
                             "~8 Jan, 05:00 IST ke baad fix, phir ye number nahi badlega.")   # fix_at, not 24 h step
        tip, lines = c["Puzzle Quest"]
        assert lines[2:] == ["⏳ 24h filling"]
        assert _t24(tip) == (PRE + "5 Jan abhi bhar raha hai — is app ka ek Google Ads account abhi read nahi ho raha "
                             "(access); wapas read hote hi fix, phir ye number nahi badlega.")
    assert "~8 Jan, 04:00 IST ke baad fix" in _cells(ov["fill|USD"])["Demo Gallery"][0]    # no fix_at: the 24 h step


def test_a_waiting_app_with_a_date_not_final_yet_gives_its_time(ov):
    """A waiting app's last pending date after fixed_till is fixed only at its own moment, not as soon as the account is
    read again: the tooltip says both. Puzzle (its last date's moment passed): "wapas read hote hi fix" as before."""
    for view in ("USD", "INR"):
        c = _cells(ov[f"waitfwd|{view}"])
        tip, lines = c["Demo Gallery"]
        assert lines[2:] == ["⏳ 24h filling"]
        assert _t24(tip) == (PRE + "4 din (4 Jan–7 Jan) abhi bhar raha hai — is app ka ek Google Ads account abhi "
                             "read nahi ho raha (access); account wapas read hone par aur ~8 Jan, 05:00 IST ke baad "
                             "fix, phir ye number nahi badlega.")
        assert _t24(c["Puzzle Quest"][0]).endswith("(access); wapas read hote hi fix, phir ye number nahi badlega.")


# ── 8. the install-day ("Day") D0: Google Ads' same <1-day value as it stood the next morning, taken once ─────────────
def _z(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.parametrize("acc, moment, ok", [
    (IST, "2026-01-01T22:30", True),  # 1 Jan's install day ends 2 Jan 00:00 IST (= 1 Jan 18:30 UTC) + 4 h = 04:00 IST
    (LA, "2026-01-02T12:00", True),   # 2 Jan 00:00 PST (UTC−8) = 08:00 UTC + 4 h
    # no time zone → UTC−12 (2 Jan 12:00 UTC + 4 h): a guess, hours after the real morning maybe — never "ok"
    ({}, "2026-01-02T16:00", False),
    ({"tz": "Not/AZone"}, "2026-01-02T16:00", False),
])
def test_day_moment_one_minute_before_and_after(acc, moment, ok):
    b = utc(moment)
    before, at = google_ads.d0_day([acc], b - timedelta(minutes=1)), google_ads.d0_day([acc], b)
    assert before["date"] == "2025-12-31" and at["date"] == "2026-01-01"
    assert at["at"] == before["next"] == _z(b) and at["next"] == _z(b + timedelta(days=1))
    assert at["ok"] is ok and at["late_h"] == 3
    # the 24 h D0 of the same date is final a day later (its last click's 24 h): the Day number comes first
    assert google_ads.d0_final([acc], b)["final_till"] == "2025-12-31"


def test_day_moment_is_the_zones_own_through_summer_time():
    b = utc("2026-07-02T11:00")                       # 2 Jul 00:00 PDT (UTC−7) = 07:00 UTC + 4 h
    assert google_ads.d0_day([LA], b - timedelta(minutes=1))["date"] == "2026-06-30"
    assert google_ads.d0_day([LA], b)["date"] == "2026-07-01"
    # every 30 min through the 2026 changes of a few zones (Santiago's at midnight): the date moves on exactly at "next"
    for tz, st in (("America/Los_Angeles", "2026-03-05"), ("Europe/Paris", "2026-03-26"),
                   ("America/Los_Angeles", "2026-10-29"), ("America/Santiago", "2026-09-03")):
        t = utc(st + "T00:00")
        for _ in range(6 * 48):
            r = google_ads.d0_day([{"tz": tz}], t)
            nxt = utc(r["next"][:-1])
            assert utc(r["at"][:-1]) <= t < nxt, (tz, t)
            assert google_ads.d0_day([{"tz": tz}], nxt - timedelta(minutes=1))["date"] == r["date"], (tz, t)
            assert google_ads.d0_day([{"tz": tz}], nxt)["date"] == \
                (date.fromisoformat(r["date"]) + timedelta(days=1)).isoformat(), (tz, t)
            t += timedelta(minutes=30)


def test_day_moment_over_the_accounts_that_count():
    """d0_final's accounts that count (the "last" rule) — fetch_app_spend asks per store, over the accounts that own it:
    an idle account in a later zone does not hold the morning read back; a store whose counted accounts are in two
    zones: its install day ends at the later zone's midnight (the latest moment wins, as in d0_final). An account
    without a known time zone that counts: never "ok"; idle: it does not matter."""
    ist, la = dict(IST, id="1"), dict(LA, id="2")
    now = utc("2026-01-02T00:00")                     # IST's moment for 1 Jan (1 Jan 22:30 UTC) passed 1.5 h ago
    got = google_ads.d0_day([ist, la], now, last={"1": "2026-01-02", "2": "2025-12-20"})
    assert got == google_ads.d0_day([ist], now) and got["date"] == "2026-01-01" and got["ok"] is True
    assert got["at"] == "2026-01-01T22:30:00Z" and got["next"] == "2026-01-02T22:30:00Z"
    assert google_ads.d0_day([ist, la], now, last={"1": "2026-01-02"}) == got      # LA: no click at all
    both = {"1": "2026-01-02", "2": "2026-01-02"}                                  # LA clicks too
    assert google_ads.d0_day([ist, la], now, last=both)["date"] == "2025-12-31"
    late = google_ads.d0_day([ist, la], utc("2026-01-02T12:00"), last=both)
    assert late["date"] == "2026-01-01" and late["at"] == "2026-01-02T12:00:00Z" and late["ok"] is True
    assert google_ads.d0_day([ist, la], utc("2026-01-02T15:01"), last=both)["ok"] is False      # 3 h 1 min late
    assert google_ads.d0_day([ist, la], now)["date"] == "2025-12-31"               # last None: every account counts
    assert google_ads.d0_day([ist, dict(IST, id="3")], now, last={"1": "2026-01-02", "3": "2026-01-02"}) == got
    nz = {"id": "4"}                                                               # no time zone
    assert google_ads.d0_day([ist, nz], now, last={"1": "2026-01-02", "4": "2026-01-02"})["ok"] is False
    assert google_ads.d0_day([ist, nz], now, last={"1": "2026-01-02", "4": "2025-12-20"}) == got   # idle: no matter


def test_each_store_at_its_own_accounts_morning():
    """_d0_day_stores: a store is read at the Day moment of the accounts that clicked it on its date — an IST store at
    04:00 IST, a store of an account in a later zone at that zone's morning, a store both click at the later one — so
    a busy account in a later zone never holds another store's morning read back (nor blocks it)."""
    ist, la, ist2 = dict(IST, id="1"), dict(LA, id="2"), dict(IST, id="3")
    d = {"2026-01-01"}
    own = {"s.i": {"1": d}, "s.l": {"2": d}, "s.both": {"1": d, "2": d}, "s.ii": {"1": d, "3": d}, "s.gone": {"9": d}}
    at_ist = google_ads._d0_day_stores([ist, la, ist2], own, utc("2026-01-01T23:00"))
    assert set(at_ist) == {"s.i", "s.l", "s.both", "s.ii"}                      # an account not asked: no moment
    assert at_ist["s.i"] == at_ist["s.ii"] == {"date": "2026-01-01", "at": "2026-01-01T22:30:00Z",
                                               "next": "2026-01-02T22:30:00Z", "ok": True}
    assert at_ist["s.l"] == at_ist["s.both"] == {"date": "2025-12-31", "at": "2026-01-01T12:00:00Z",
                                                 "next": "2026-01-02T12:00:00Z", "ok": False}   # 11 h late
    at_la = google_ads._d0_day_stores([ist, la, ist2], own, utc("2026-01-02T12:30"))
    assert at_la["s.l"] == at_la["s.both"] == {"date": "2026-01-01", "at": "2026-01-02T12:00:00Z",
                                               "next": "2026-01-03T12:00:00Z", "ok": True}
    assert at_la["s.i"]["date"] == "2026-01-01" and at_la["s.i"]["ok"] is False  # IST's 1 Jan: 14 h ago
    # the later-zone account has no click OF THIS STORE on 1 Jan (it left it, or clicks it again only on 2 Jan; its
    # other stores do not matter): the store is IST's that day; nobody clicked it on 1 Jan: the ones with its latest row
    gone = {"s.both": {"1": d, "2": {"2025-12-20"}}, "s.old": {"1": {"2025-12-01"}, "2": {"2025-12-20"}},
            "s.skip": {"1": d, "2": {"2025-12-31", "2026-01-02"}}}
    got = google_ads._d0_day_stores([ist, la], gone, utc("2026-01-01T23:00"))
    assert got["s.both"] == got["s.skip"] == at_ist["s.i"] and got["s.old"] == at_ist["s.l"]
    assert google_ads._d0_day_stores([ist, la], gone, utc("2026-01-02T12:30"))["s.skip"]["ok"] is False


def _at(x, tz):
    """(x + 1 day, 00:00 in tz) + 4 h, ISO UTC "Z": click date x's Day moment in zone tz."""
    from zoneinfo import ZoneInfo
    m = datetime.combine(date.fromisoformat(x) + timedelta(days=1), datetime.min.time(), ZoneInfo(tz))
    return _z((m + timedelta(hours=4)).astimezone(timezone.utc))


@pytest.mark.parametrize("b_days", [
    ("2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"),     # the later-zone account stops after 29 Oct
    ("2026-10-28",),                                             # clicks the store one day only
    ("2026-10-26", "2026-10-28", "2026-10-30", "2026-11-01"),     # every other day (US summer time ends 1 Nov)
    (),                                                          # left the store long ago (clicks other stores)
])
@pytest.mark.parametrize("tz", ["America/Los_Angeles", "America/New_York"])
def test_a_shared_store_takes_every_date_once_at_its_clickers_moment(b_days, tz):
    """An IST account clicks the store every day, a later-zone one only on b_days: read every 30 min, each date is on
    time in exactly one window — at the later zone's morning on its click days, else at 04:00 IST (the "last" rule
    over every store of the account flipped between the two and missed the first date after it stopped)."""
    from zoneinfo import ZoneInfo
    ist, b = dict(IST, id="1"), {"tz": tz, "id": "2"}
    seen, t = {}, utc("2026-10-25T00:00")
    while t < utc("2026-11-04T00:00"):
        bl, il = (t.astimezone(ZoneInfo(z)).date().isoformat() for z in (tz, "Asia/Calcutta"))
        every = ((date(2026, 10, 1) + timedelta(days=i)).isoformat() for i in range(40))
        own = {"s": {"1": {x for x in every if x <= il}, "2": {x for x in b_days if x <= bl} | {"2026-10-01"}}}
        r = google_ads._d0_day_stores([ist, b], own, t)["s"]
        if r["ok"]:
            seen.setdefault(r["date"], set()).add(r["at"])
        t += timedelta(minutes=30)
    for i in range(8):
        x = (date(2026, 10, 25) + timedelta(days=i)).isoformat()
        assert seen.get(x) == {_at(x, tz if x in b_days else "Asia/Calcutta")}, x


def test_day_ok_only_up_to_the_late_limit(monkeypatch):
    b = utc("2026-01-01T22:30")
    on = google_ads.d0_day([IST], b + timedelta(hours=3))
    off = google_ads.d0_day([IST], b + timedelta(hours=3, minutes=1))
    assert on["ok"] is True and off["ok"] is False and on["date"] == off["date"] == "2026-01-01"
    assert google_ads.d0_day([IST], b, late_h=0)["ok"] is True
    assert google_ads.d0_day([IST], b + timedelta(minutes=1), late_h=0)["ok"] is False
    monkeypatch.setenv("GADS_D0_DAY_MAX_LATE_H", "5")
    got = google_ads.d0_day([IST], b + timedelta(hours=5))
    assert got["ok"] is True and got["late_h"] == 5
    monkeypatch.setenv("GADS_D0_DAY_MAX_LATE_H", "x")
    assert google_ads.d0_day([IST], b)["late_h"] == 3
    monkeypatch.setenv("GADS_D0_LAG_HOURS", "3")                                  # the lag moves the moment too
    assert google_ads.d0_day([IST], b - timedelta(hours=1))["at"] == "2026-01-01T21:30:00Z"


def test_fetch_carries_the_day_of_its_read(monkeypatch):
    from zoneinfo import ZoneInfo
    now = datetime(2026, 1, 11, 4, 30, tzinfo=ZoneInfo("Asia/Calcutta"))         # 10 Jan's moment (04:00 IST) + 30 min
    out = _fetch(monkeypatch, FakeAds(), now)
    ist = {"date": "2026-01-10", "at": "2026-01-10T22:30:00Z", "next": "2026-01-11T22:30:00Z", "ok": True}
    assert out["d1_day"] == dict(ist, late_h=3, read="2026-01-10T23:00:00Z", stores={S1: ist, S2: ist})
    assert out["d1_final_till"] == "2026-01-09"                                   # the 24 h D0: a day behind
    late = _fetch(monkeypatch, FakeAds(), utc("2026-01-11T01:31"))["d1_day"]      # 3 h 1 min late
    assert late["ok"] is False and not any(e["ok"] for e in late["stores"].values())
    # A2 in a later zone, clicking every day: its store at its own morning, A1's at 04:00 IST as before
    fake = FakeAds()
    fake.accounts[A2]["tz"] = "America/Los_Angeles"
    out = _fetch(monkeypatch, fake, now)
    assert out["d1_day"]["stores"] == {S1: ist, S2: {"date": "2026-01-09", "at": "2026-01-10T12:00:00Z",
                                                      "next": "2026-01-11T12:00:00Z", "ok": False}}
    assert out["d1_day"]["date"] == "2026-01-09"                                  # every account: the page's fallback
    at_la = _fetch(monkeypatch, fake, utc("2026-01-11T12:30"))["d1_day"]["stores"]
    assert at_la[S2] == {"date": "2026-01-10", "at": "2026-01-11T12:00:00Z", "next": "2026-01-12T12:00:00Z", "ok": True}
    assert at_la[S1]["ok"] is False                                               # IST's 10 Jan: 14 h ago


@pytest.mark.parametrize("hi", ["2026-01-09", "2026-01-03"])
def test_fetch_a_store_the_later_zone_account_left_is_read_at_ist_morning(monkeypatch, hi):
    """A2 (New York) clicks its own store every day and A1's store S1 too up to `hi` (it stopped / left it long ago):
    S1 is read at 04:00 IST from the first date A2 has no click of it on — not at New York's morning 9.5 h later
    (A2's clicks on other stores do not matter); a date A2 clicked S1 on: at New York's morning."""
    fake = FakeAds()
    fake.accounts[A2]["tz"] = "America/New_York"
    fake.camps[A2]["22"] = dict(fake.camp("22", S1, 7), hi=hi)
    ist = {"date": "2026-01-10", "at": "2026-01-10T22:30:00Z", "next": "2026-01-11T22:30:00Z", "ok": True}
    ny9 = {"date": "2026-01-09", "at": "2026-01-10T09:00:00Z", "next": "2026-01-11T09:00:00Z"}
    st = _fetch(monkeypatch, fake, utc("2026-01-10T22:40"))["d1_day"]["stores"]
    assert st == {S1: ist, S2: dict(ny9, ok=False)}
    at9 = _fetch(monkeypatch, fake, utc("2026-01-10T09:30"))["d1_day"]["stores"]   # NY's morning of 9 Jan
    assert at9[S2] == dict(ny9, ok=True)
    assert at9[S1] == (dict(ny9, ok=True) if hi == "2026-01-09" else
                       {"date": "2026-01-09", "at": "2026-01-09T22:30:00Z", "next": "2026-01-10T22:30:00Z",
                        "ok": False})


DAY_STORES = ("s.a", "s.b", "s.c", "s.d", "s.e", "s.a2", "s.one", "s.two", "s.split", "com.x.a", "com.x.b")


def _day(x="2026-01-05", ok=True, read=None, nxt=None, late_h=3, stores=DAY_STORES):
    """A read's d1_day for click date x (IST, lag 4 h: its moment is x 22:30 UTC); stores: the ones with a row in the
    read (each owned by IST accounts only: the same moment)."""
    n = (date.fromisoformat(x) + timedelta(days=1)).isoformat()
    e = {"date": x, "at": x + "T22:30:00Z", "next": nxt or n + "T22:30:00Z", "ok": ok}
    return dict(e, late_h=late_h, read=read or x + "T22:40:00Z", stores={s: dict(e) for s in stores})


DAY_KEYS = ("convval_d0day", "d1_day_read", "d1_day_next", "d1_day_at")


def _no_day(m):
    return {k: v for k, v in m.items() if k not in DAY_KEYS + ("d1_day",)}


def test_day_is_taken_once_and_never_changed():
    cost = {"s.a": {"2026-01-05": 100, "2026-01-06": 30}, "s.b": {"2026-01-05": 50}}
    cached = _cache({}, fixed="2026-01-03", daily={"s.a": {"2026-01-04": 100}})
    fresh = _fresh({"s.a": {"2026-01-05": 7.5, "2026-01-06": 1.0}, "s.c": {"2026-01-05": 2.0}}, daily=cost,
                   d1_day=_day("2026-01-05"))
    m = google_ads.merge_spend(json.loads(json.dumps(cached)), fresh, "2026-01-01")
    # s.b: cost on 5 Jan and no D0 row → 0.0 (no value within the install day); s.c: a D0 row without cost: its value
    assert m["convval_d0day"] == {"s.a": {"2026-01-05": 7.5}, "s.b": {"2026-01-05": 0.0}, "s.c": {"2026-01-05": 2.0}}
    assert m["d1_day_read"] == {"2026-01-05": "2026-01-05T22:40:00Z"}
    assert m["d1_day_next"] == {"date": "2026-01-06", "at": "2026-01-06T22:30:00Z", "late_h": 3}
    assert m["d1_day_at"] == {s: {"date": "2026-01-06", "at": "2026-01-06T22:30:00Z"} for s in DAY_STORES}
    # every other key: exactly the merge without the Day read
    plain = google_ads.merge_spend(json.loads(json.dumps(cached)), {k: v for k, v in fresh.items() if k != "d1_day"},
                                   "2026-01-01")
    assert json.dumps(_no_day(m), sort_keys=True) == json.dumps(plain, sort_keys=True)
    assert not any(k in plain for k in DAY_KEYS)                                    # nothing to keep: no key at all
    # later reads the same morning and after: Google's <1-day value of 5 Jan grows (later revenue) — a taken number
    # stays (a read still on time for it included); a store-day not taken yet (s.d: its first row now) is taken by a
    # read still on time for its store, never by a late one (s.e)
    on = _fresh({"s.a": {"2026-01-05": 9.9}, "s.b": {"2026-01-05": 4.0}, "s.d": {"2026-01-05": 1.5}},
                final="2026-01-05", daily=cost, d1_day=_day("2026-01-05", read="2026-01-06T00:10:00Z"))
    m2 = google_ads.merge_spend(m, on, "2026-01-01")
    assert m2["convval_d0day"] == dict(m["convval_d0day"], **{"s.d": {"2026-01-05": 1.5}})
    assert m2["d1_day_read"] == m["d1_day_read"]                                    # the first read that took 5 Jan
    off = _fresh({"s.a": {"2026-01-05": 12.0}, "s.e": {"2026-01-05": 3.0}}, final="2026-01-05", daily=cost,
                 d1_day=_day("2026-01-05", ok=False, read="2026-01-06T01:31:00Z"))
    assert google_ads.merge_spend(m2, off, "2026-01-01")["convval_d0day"] == m2["convval_d0day"]
    # the next morning: 6 Jan is taken, 5 Jan kept
    m3 = google_ads.merge_spend(m2, _fresh({"s.a": {"2026-01-05": 13.0, "2026-01-06": 3.0}}, final="2026-01-05",
                                           daily=cost, d1_day=_day("2026-01-06")), "2026-01-01")
    assert m3["convval_d0day"] == {"s.a": {"2026-01-05": 7.5, "2026-01-06": 3.0}, "s.b": {"2026-01-05": 0.0},
                                   "s.c": {"2026-01-05": 2.0}, "s.d": {"2026-01-05": 1.5}}
    assert m3["d1_day_read"] == {"2026-01-05": "2026-01-05T22:40:00Z", "2026-01-06": "2026-01-06T22:40:00Z"}
    assert m3["d1_day_next"]["date"] == "2026-01-07"
    # a read without a Day part (an older build) or a mock read: copied forward as it is
    old = google_ads.merge_spend(m3, _fresh({"s.a": {"2026-01-07": 1.0}}, final="2026-01-05"), "2026-01-01")
    assert {k: old[k] for k in DAY_KEYS} == {k: m3[k] for k in DAY_KEYS}


def test_a_late_read_takes_no_day_number():
    """No complete read within the late limit after 5 Jan's moment: 5 Jan gets no Day number at all (a late read holds
    later revenue — never a wrong number); the next morning's read takes 6 Jan as usual."""
    cost = {"s.a": {"2026-01-05": 100, "2026-01-06": 100}}
    late = google_ads.merge_spend(_cache({}, fixed="2026-01-03"),
                                  _fresh({"s.a": {"2026-01-05": 7.5}}, daily=cost, d1_day=_day("2026-01-05", ok=False)),
                                  "2026-01-01")
    assert not any(k in late for k in ("convval_d0day", "d1_day_read"))
    assert late["d1_day_next"] == {"date": "2026-01-06", "at": "2026-01-06T22:30:00Z", "late_h": 3}   # the page's
    m = google_ads.merge_spend(late, _fresh({"s.a": {"2026-01-05": 9.0, "2026-01-06": 4.0}}, final="2026-01-05",
                                            daily=cost, d1_day=_day("2026-01-06")), "2026-01-01")
    assert m["convval_d0day"] == {"s.a": {"2026-01-06": 4.0}} and list(m["d1_day_read"]) == ["2026-01-06"]


def test_an_incomplete_read_takes_nothing_and_a_complete_one_in_time_does():
    cost = {"s.a": {"2026-01-05": 100}, "s.b": {"2026-01-05": 100}}
    part = _fresh({"s.a": {"2026-01-05": 7.5}}, ok=False, daily=cost, d1_day=_day("2026-01-05"))
    m = google_ads.merge_spend(_cache({}, fixed="2026-01-03", daily=cost), part, "2026-01-01")
    assert "convval_d0day" not in m and "d1_day_read" not in m                    # s.b's part may be missing: no 0.0
    m2 = google_ads.merge_spend(m, _fresh({"s.a": {"2026-01-05": 7.9}, "s.b": {"2026-01-05": 2.0}}, daily=cost,
                                          d1_day=_day("2026-01-05", read="2026-01-06T00:50:00Z")), "2026-01-01")
    assert m2["convval_d0day"] == {"s.a": {"2026-01-05": 7.9}, "s.b": {"2026-01-05": 2.0}}
    assert m2["d1_day_read"] == {"2026-01-05": "2026-01-06T00:50:00Z"}


def test_a_store_waiting_for_an_unread_account_gets_no_day_number():
    """Account "2" answers 403 to every query (d1_unread): its own store and the store it shares with "1" get no Day
    number from that read (it would miss "2"'s part); "1"'s own store is taken. "2" back while still on time for the
    date: its stores are taken then (Google's number at that read); back only after the limit: never. A first run (no
    cache campaigns: which stores "2" shares is unknown) with an unread account takes nothing."""
    camps = {"s.one": [_c("c1", "1")], "s.two": [_c("c2", "2")], "s.split": [_c("c3", "1"), _c("c4", "2")]}
    cost = {s: {"2026-01-05": 100} for s in camps}
    one = {"s.one": [_c("c1", "1")], "s.split": [_c("c3", "1")]}
    r1 = _fresh({"s.one": {"2026-01-05": 6.0}, "s.split": {"2026-01-05": 3.0}}, campaigns=one, d1_unread=["2"],
                daily={s: cost[s] for s in one}, d1_day=_day("2026-01-05", stores=("s.one", "s.split")))
    m = google_ads.merge_spend(_cache({}, fixed="2026-01-03", campaigns=camps, daily=cost), r1, "2026-01-01")
    assert m["convval_d0day"] == {"s.one": {"2026-01-05": 6.0}} and list(m["d1_day_read"]) == ["2026-01-05"]
    back = lambda **kw: _fresh({"s.one": {"2026-01-05": 6.5}, "s.two": {"2026-01-05": 4.0},
                                "s.split": {"2026-01-05": 5.0}}, campaigns=camps, daily=cost,
                               d1_day=_day("2026-01-05", stores=tuple(camps), **kw))
    on = google_ads.merge_spend(m, back(read="2026-01-06T00:00:00Z"), "2026-01-01")
    assert on["convval_d0day"] == {"s.one": {"2026-01-05": 6.0}, "s.two": {"2026-01-05": 4.0},
                                   "s.split": {"2026-01-05": 5.0}}
    assert on["d1_day_read"] == m["d1_day_read"]
    late = google_ads.merge_spend(m, back(ok=False, read="2026-01-06T01:31:00Z"), "2026-01-01")
    assert late["convval_d0day"] == m["convval_d0day"]
    first = google_ads.merge_spend(None, json.loads(json.dumps(dict(r1, campaigns=camps))), "2026-01-01")
    assert first["convval_day1"] and "convval_d0day" not in first and "d1_day_read" not in first
    assert first["d1_day_next"]["date"] == "2026-01-06" and set(first["d1_day_at"]) == {"s.one", "s.split"}


def test_day_on_the_first_run_and_through_a_failed_fetch():
    fresh = _fresh({"com.x.a": {"2026-01-05": 7.5}}, daily={"com.x.a": {"2026-01-05": 100}}, d1_day=_day("2026-01-05"))
    first = google_ads.merge_spend(None, fresh, "2026-01-01")
    assert first is fresh and first["convval_d0day"] == {"com.x.a": {"2026-01-05": 7.5}}
    assert first["d1_day_read"] == {"2026-01-05": "2026-01-05T22:40:00Z"}
    assert first["d1_day_next"]["date"] == "2026-01-06"
    assert "convval_d0day" not in google_ads.merge_spend(None, _fresh({}, d1_day=_day(ok=False)), "2026-01-01")
    # a failed fetch keeps the cache whole — the Day numbers with it (whether anything was fixed or not)
    assert google_ads.merge_spend(first, {"error": "boom"}, "2026-01-01") == dict(first, d1_incomplete=True)
    never = {k: v for k, v in first.items() if k != "d1_fixed_till"}
    assert google_ads.merge_spend(never, {"error": "boom"}, "2026-01-01") is never
    m = google_ads.merge_spend(first, _fresh({}, ok=False), "2026-01-01")        # an incomplete read: kept
    assert {k: m[k] for k in DAY_KEYS} == {k: first[k] for k in DAY_KEYS}


@pytest.mark.parametrize("odd", [
    {"convval_d0day": {"com.x.a": {"2026-01-02": None, "2026-01-03": "5", "2026-01-04": float("nan")}}},
    {"convval_d0day": {"com.x.a": ["2026-01-02"]}},
    {"convval_d0day": ["com.x.a"]},
    {"d1_day_read": {"x": "y", "2026-01-02": 5}},
    {"d1_day_read": ["2026-01-02"]},
    {"d1_day_next": "2026-01-06"},
    {"d1_day_at": {"com.x.b": "x", "com.x.c": {"date": "bad", "at": 5}, "com.x.d": {"date": "2026-01-02"}}},
    {"d1_day_at": ["com.x.a"]},
])
def test_an_odd_day_value_in_the_cache_never_raises(odd):
    cached = _cache({}, fixed="2026-01-02", convval_d0day={"com.x.b": {"2026-01-01": 4.0}},
                    d1_day_read={"2026-01-01": "2026-01-01T22:40:00Z"})
    cached.update(odd)
    m = google_ads.merge_spend(cached, _fresh({"com.x.a": {"2026-01-05": 7.5}}, daily={"com.x.a": {"2026-01-05": 1}},
                                              d1_day=_day("2026-01-05")), "2026-01-01")
    json.dumps(m, allow_nan=False)
    assert m["convval_d0day"]["com.x.a"] == {"2026-01-05": 7.5} and "2026-01-05" in m["d1_day_read"]
    if "convval_d0day" not in odd:
        assert m["convval_d0day"]["com.x.b"] == {"2026-01-01": 4.0}                 # the good ones stay
    build_roas(_spend_to_usd(m, 0.01), {"app-a": "com.x.a"}, [{"app_id": "app-a", "app_name": "App A", "rev": 1}])


def test_day_log_lines_are_counts_only(capsys):
    cost = {"com.x.a": {"2026-01-05": 100}, "com.x.b": {"2026-01-05": 100}}
    fresh = _fresh({"com.x.a": {"2026-01-05": 12345.67}}, daily=cost, d1_day=_day("2026-01-05"))
    m = google_ads.merge_spend(_cache({}, fixed="2026-01-03", daily=cost), fresh, "2026-01-01")
    google_ads.merge_spend(m, fresh, "2026-01-01")                                  # taken already: no Day part
    google_ads.merge_spend(None, json.loads(json.dumps(fresh)), "2026-01-01")
    two = _fresh({"com.x.a": {"2026-01-05": 1.5}, "com.x.b": {"2026-01-04": 2.5}}, daily=cost,
                 d1_day=_day("2026-01-05"))
    two["d1_day"]["stores"]["com.x.b"]["date"] = "2026-01-04"                      # a store in another zone
    google_ads.merge_spend(_cache({}, fixed="2026-01-03", daily=cost), two, "2026-01-01")
    lines = capsys.readouterr().err.splitlines()
    assert lines == ["roas: D0 fixed till 2026-01-04 · 0 store-days fixed this run · Day 2026-01-05 captured: 2 stores",
                     "roas: D0 fixed till 2026-01-04 · 0 store-days fixed this run",
                     "roas: D0 fixed till 2026-01-04 · 0 store-days fixed this run · Day 2026-01-05 captured: 2 stores",
                     "roas: D0 fixed till 2026-01-04 · 1 store-days fixed this run · Day 2026-01-04 captured: 1 stores"
                     " · Day 2026-01-05 captured: 1 stores"]
    for ln in lines:
        assert LINE.match(ln), ln
        rest = re.sub(r"\d{4}-\d{2}-\d{2}", "", ln)
        assert "%" not in ln and "com.x" not in ln and not re.search(r"\d{3,}|\d\.\d", rest), ln


def test_day_to_usd_and_to_the_page():
    cost = {"s.a": {"2026-01-05": 100}, "s.a2": {"2026-01-05": 100, "2026-01-06": 100}, "s.b": {"2026-01-05": 100}}
    camps = {"s.a": [_c("c1", "acct-synth-7")]}
    m = google_ads.merge_spend(_cache({}, fixed="2026-01-03", daily=cost, campaigns=camps),
                               _fresh({"s.a": {"2026-01-05": 750.0}, "s.a2": {"2026-01-05": 250.0}, "s.b": {}},
                                      daily=cost, d1_day=_day("2026-01-05")), "2026-01-01")
    m = google_ads.merge_spend(m, _fresh({"s.a2": {"2026-01-06": 90.0}}, final="2026-01-05", daily=cost,
                                         d1_day=_day("2026-01-06", stores=("s.a2", "s.b"))), "2026-01-01")
    m["d1_day_at"]["s.a2"] = {"date": "2026-01-07", "at": "2026-01-08T09:00:00Z"}    # s.a2 in a later zone
    usd = _spend_to_usd(m, 0.01)                       # the same ONE rate as convval_day1, 2 decimals
    assert usd["convval_d0day"] == {"s.a": {"2026-01-05": 7.5}, "s.a2": {"2026-01-05": 2.5, "2026-01-06": 0.9},
                                    "s.b": {"2026-01-05": 0.0}}
    assert m["convval_d0day"]["s.a"] == {"2026-01-05": 750.0}                      # the cache itself stays RAW
    cat = [{"app_id": "app-a", "app_name": "App A", "rev": 2}, {"app_id": "app-b", "app_name": "App B", "rev": 1}]
    r = build_roas(usd, {"app-a": "s.a", "app-b": "s.b"}, cat, aliases={"s.a2": "App A"})
    assert r["by_app"]["App A"]["convval_d0day_daily"] == {"2026-01-05": 10.0, "2026-01-06": 0.9}   # its two stores
    assert r["by_app"]["App B"]["convval_d0day_daily"] == {"2026-01-05": 0.0}
    assert r["d0"]["day_read"] == {"2026-01-05": "2026-01-05T22:40:00Z", "2026-01-06": "2026-01-06T22:40:00Z"}
    assert r["d0"]["day_since"] == "2026-01-05"
    assert r["d0"]["day_next"] == {"date": "2026-01-07", "at": "2026-01-07T22:30:00Z", "late_h": 3}
    # each app's own next Day moment: its stores' latest (App A's s.a2 is in a later zone)
    assert r["by_app"]["App A"]["d0day_next"] == {"date": "2026-01-07", "at": "2026-01-08T09:00:00Z"}
    assert r["by_app"]["App B"]["d0day_next"] == {"date": "2026-01-07", "at": "2026-01-07T22:30:00Z"}
    assert not re.search(r"acct|s\.a|s\.b", json.dumps(r["d0"]))                       # dates and times only
    assert not re.search(r"acct|s\.a|s\.b", json.dumps([e["d0day_next"] for e in r["by_app"].values()]))
    # a cache without Day keys: the payload exactly as before (no key at all)
    plain = build_roas(_spend_to_usd(_no_day(m), 0.01), {"app-a": "s.a", "app-b": "s.b"}, cat,
                       aliases={"s.a2": "App A"})
    assert "convval_d0day" not in _spend_to_usd(_no_day(m), 0.01)
    assert not any(k.startswith("day_") for k in plain["d0"])
    assert all("convval_d0day_daily" not in e and "d0day_next" not in e for e in plain["by_app"].values())
    strip = lambda p: {**{k: v for k, v in p.items() if k != "d0"},
                       "by_app": {a: {k: v for k, v in e.items() if k not in ("convval_d0day_daily", "d0day_next")}
                                  for a, e in p["by_app"].items()}}
    assert json.dumps(strip(r), sort_keys=True) == json.dumps(strip(plain), sort_keys=True)


def test_an_app_date_a_store_of_it_was_not_taken_for_is_not_covered():
    """An app with two stores (an alias) where one store with cost on 5 Jan got no Day number (it waited for an unread
    account at its morning read): 5 Jan is not covered for the app (Σ of one store over both stores' spend would read
    as a low ROAS for good) — the page counts it as missing; 6 Jan (only s.a has cost) is. An app with no date left:
    no key."""
    usd = {"daily": {"s.a": {"2026-01-05": 100_000_000, "2026-01-06": 100_000_000}, "s.b": {"2026-01-05": 50_000_000},
                     "s.c": {"2026-01-05": 100_000_000}, "s.c2": {"2026-01-05": 100_000_000}},
           "convval_d0day": {"s.a": {"2026-01-05": 20.0, "2026-01-06": 10.0}, "s.c": {"2026-01-05": 5.0}},
           "d1_day_at": {"s.a": {"date": "2026-01-07", "at": "2026-01-07T22:30:00Z"}, "s.b": "odd"}}
    cat = [{"app_id": "app-a", "app_name": "App A", "rev": 2}, {"app_id": "app-c", "app_name": "App C", "rev": 1}]
    r = build_roas(usd, {"app-a": "s.a", "app-c": "s.c"}, cat, aliases={"s.b": "App A", "s.c2": "App C"})
    assert r["by_app"]["App A"]["convval_d0day_daily"] == {"2026-01-06": 10.0}
    assert r["by_app"]["App A"]["d0day_next"] == {"date": "2026-01-07", "at": "2026-01-07T22:30:00Z"}   # odd: absent
    assert "convval_d0day_daily" not in r["by_app"]["App C"] and "d0day_next" not in r["by_app"]["App C"]


def test_two_zones_each_store_is_taken_at_its_own_morning(monkeypatch):
    """A1 in IST and A2 in Los Angeles, both clicking every day, read every 30 min for 3 days through the real
    fetch_app_spend → merge_spend → build_roas: each store's date is taken once, by the first read at or after ITS OWN
    accounts' Day moment (A1's store at 04:00 IST = 22:30 UTC, A2's at 04:00 Los Angeles time = 12:00 UTC) — the busy
    later zone never blocks or delays the IST store, and a date whose first read came over 3 h late (7 Jan, both) is
    never taken. The number is that read's D0; each app's next moment is its own."""
    from zoneinfo import ZoneInfo
    fake = FakeAds()
    fake.accounts[A2]["tz"] = "America/Los_Angeles"
    zone = {A1: ZoneInfo("Asia/Calcutta"), A2: ZoneInfo("America/Los_Angeles")}
    t, cache, first, d1 = utc("2026-01-08T15:10"), None, {}, {}
    while t < utc("2026-01-11T15:10"):
        for a, z in zone.items():                                               # clicks up to its own today
            for c in fake.camps[a].values():
                c["hi"] = t.astimezone(z).date().isoformat()
        fresh = _fetch(monkeypatch, fake, t, end=t.astimezone(zone[A1]).date().isoformat())
        took = {(s, x): v for s, dd in (fresh.get("convval_day1") or {}).items() for x, v in dd.items()}
        cache = google_ads.merge_spend(cache, fresh, "2026-01-01")
        for s, dd in cache.get("convval_d0day", {}).items():
            for x, v in dd.items():
                if (s, x) not in first:
                    first[s, x], d1[s, x] = t, took[s, x]
        t += timedelta(minutes=30)
    assert {k: _z(v) for k, v in first.items()} == {
        (S1, "2026-01-08"): "2026-01-08T22:40:00Z", (S1, "2026-01-09"): "2026-01-09T22:40:00Z",
        (S1, "2026-01-10"): "2026-01-10T22:40:00Z", (S2, "2026-01-08"): "2026-01-09T12:10:00Z",
        (S2, "2026-01-09"): "2026-01-10T12:10:00Z", (S2, "2026-01-10"): "2026-01-11T12:10:00Z"}
    assert all(cache["convval_d0day"][s][x] == v > 0 for (s, x), v in d1.items())      # the D0 that read had
    assert cache["d1_day_read"] == {d: d + "T22:40:00Z" for d in ("2026-01-08", "2026-01-09", "2026-01-10")}
    cat = [{"app_id": "app-1", "app_name": "App One", "rev": 2}, {"app_id": "app-2", "app_name": "App Two", "rev": 1}]
    by = build_roas(_spend_to_usd(cache, 0.012), {"app-1": S1, "app-2": S2}, cat)["by_app"]
    assert by["App One"]["d0day_next"] == {"date": "2026-01-11", "at": "2026-01-11T22:30:00Z"}
    assert by["App Two"]["d0day_next"] == {"date": "2026-01-11", "at": "2026-01-12T12:00:00Z"}
    assert sorted(by["App Two"]["convval_d0day_daily"]) == ["2026-01-08", "2026-01-09", "2026-01-10"]


def test_the_campaign_store_never_reads_the_day_keys(tmp_path):
    mf = gcd.months(str(tmp_path))
    days = ["2026-01-0%d" % i for i in range(1, 5)]
    gcd.overlay(mf, "cv1", [{"campaign_id": "1", "store_id": "com.x.a", "date": d, "convval": 5.0, "account": "1"}
                            for d in days], {"1": "INR"})
    spend = {"currency_src": "INR", "fx": {}, "daily": {}, "d1_fixed_till": "2026-01-02",
             "convval_day1": {"com.x.a": {"2026-01-01": 4.0, "2026-01-02": 5.0, "2026-01-03": 5.0, "2026-01-04": 5.0}}}
    day = dict(spend, convval_d0day={"com.x.a": {d: 1.0 for d in days}}, d1_day_read={d: "x" for d in days},
               d1_day_next={"date": "2026-01-05", "at": "x"}, d1_day_at={"com.x.a": {"date": "2026-01-05", "at": "x"}})
    assert gcd.ties(mf, day, days[0], days[-1]) == gcd.ties(mf, spend, days[0], days[-1])


# ── 9. the Day line on the page, run for real ─────────────────────────────────────────────────────────────────────────
def _day_tip(hh, rest, when="agle din"):
    h = int(hh[:2])
    return "Day = install ke din raat 12 baje tak — %s%s ~%s IST ka Google Ads number.%s" % (
        when, " subah" if 4 <= h < 12 else " raat" if h < 4 or h >= 21 else "", hh, rest)


def _hh(t):
    """t's IST clock time (the page's moments run on the real clock, so a test's moment is relative to it)."""
    return (t + timedelta(hours=5, minutes=30)).strftime("%H:%M")


def _ist(t):
    t += timedelta(hours=5, minutes=30)
    return "%d %s, %s IST" % (t.day, t.strftime("%b"), t.strftime("%H:%M"))


OLD = (" Day number 2 Jan se hai (Google Ads subah wala purana number nahi rakhta) — 2 din (31 Dec 2025–1 Jan 2026)"
       " ka nahi hai.")
GONE = " — us subah Google Ads ka poora read nahi mila, isliye Day number nahi hai."   # any cause: no run, late, an
                                                                                        # incomplete or unread account


def test_day_two_lines_and_roas_in_both_views(ov):
    """By hand (₹90 a dollar): Demo's Day numbers 3, 5, 6 Jan = ₹2,430 + ₹2,520 + ₹2,700 = ₹7,650 ($85) over those 3
    of its 8 spend days (₹27,000) → 0.28×, "· 3/8 days"; Puzzle's 2–5 Jan = ₹1,620 + ₹1,710 + ₹1,530 + ₹1,440 = ₹6,300
    ($70) over all 4 spend days (₹18,000) → 0.35×. Line 1 (24h) as before; both ROAS the same in ₹ and $."""
    for k in ("day", "dayfixed"):
        usd, inr = _cells(ov[f"{k}|USD"]), _cells(ov[f"{k}|INR"])
        assert usd["Demo Gallery"][1][:2] == ["24h $240 · 0.30×", "Day $85 · 0.28× · 3/8 days"]
        assert inr["Demo Gallery"][1][:2] == ["24h ₹21,600 · 0.30×", "Day ₹7,650 · 0.28× · 3/8 days"]
        assert usd["Puzzle Quest"][1] == ["24h $80 · 0.40×", "Day $70 · 0.35×"]
        assert inr["Puzzle Quest"][1] == ["24h ₹7,200 · 0.40×", "Day ₹6,300 · 0.35×"]
        for app, n in (("Demo Gallery", 3), ("Puzzle Quest", 4)):                 # Σ Day ÷ Σ one-rate spend, same dates
            e = ov["_fx"][k]["roas"]["by_app"][app]
            got = [d for d in WIN if d in e["convval_d0day_daily"]]
            assert len(got) == n
            r = sum(e["convval_d0day_daily"][d] for d in got) / (sum(e["daily"][d] for d in got) / 1e6)
            assert usd[app][1][1].split(" ")[3] == "%.2f×" % r
    assert ov["_fx"]["day"]["roas"]["by_app"]["Demo Gallery"]["convval_d0day_daily"]["2026-01-06"] == 30.0   # taken now


def test_day_line_wraps_only_between_its_parts(ov):
    """Each part of a line ("Day $85", "· 0.28×", "· 3/8 days") is unbreakable, the line is not: a whole-line nowrap
    widened the D0 column by ~95 px and pushed the table into a horizontal scroll at 1366–1440 px."""
    nw = '<span style="white-space:nowrap">%s</span>'
    sm = '<span class="%s" style="font-size:%dpx">%s</span>'
    for k in ("day", "fill", "dayfixed"):
        for view in ("USD", "INR"):
            tr = next(t for t in re.findall(r'<tr class="clk"[^>]*>(.*?)</tr>', ov[f"{k}|{view}"], re.S)
                      if "Demo Gallery" in t)
            td = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)[4]
            assert "nowrap;" not in td and '<div style="white-space:nowrap' not in td   # (the td is nowrap: CSS)
            assert td.startswith('<div style="white-space:normal"><span style="white-space:nowrap">'
                                 + sm % ("faint", 10, "24h") + " ")
            assert nw % (sm % ("muted", 11, "· 0.30×")) in td
    td = re.findall(r"<td[^>]*>(.*?)</td>", next(t for t in re.findall(r'<tr class="clk"[^>]*>(.*?)</tr>',
                                                                      ov["day|USD"], re.S) if "Demo Gallery" in t))[4]
    assert ('<div style="white-space:normal;margin-top:2px">' + nw % (sm % ("faint", 10, "Day") + " $85") + " "
            + nw % (sm % ("muted", 11, "· 0.28×")) + " " + nw % (sm % ("faint", 10, "· 3/8 days")) + "</div>") in td


def test_day_the_three_filling_lines(ov):
    assert _cells(ov["day|USD"])["Demo Gallery"][1][2:] == ["⏳ filling"]           # 24h 6–7 Jan + Day 7 Jan
    assert _cells(ov["fill|USD"])["Demo Gallery"][1][2:] == ["⏳ 24h filling"]      # no Day number to wait for
    assert _cells(ov["dayfixed|USD"])["Demo Gallery"][1][2:] == ["⏳ Day filling"]  # 24h all fixed
    assert _cells(ov["daylate|INR"])["Demo Gallery"][1][2:] == ["⏳ Day filling"]   # its morning read can still come
    assert len(_cells(ov["daymiss|USD"])["Demo Gallery"][1]) == 2                  # missed: nothing filling
    for k in ("day", "dayfixed", "daylate", "daymiss"):
        assert len(_cells(ov[f"{k}|USD"])["Puzzle Quest"][1]) == 2                 # every date taken, 24h fixed


def test_day_tooltip_says_what_each_line_is_and_when_it_fixes(ov):
    for view in ("USD", "INR"):
        c = _cells(ov[f"day|{view}"])
        tip = c["Demo Gallery"][0]
        assert tip.split("\n")[0] == _t24(_cells(ov[f"fill|{view}"])["Demo Gallery"][0])    # the 24h part as before
        # the clock time: the app's Day moment (its stores' zone; the same each day); 7 Jan fixes at its moment; the
        # missed 2 and 4 Jan named (3 Jan has a number)
        assert _tday(tip) == _day_tip(_hh(PART_NEXT), " 3/8 din ka number fixed hai. 7 Jan abhi bhar raha hai — ~%s ke "
                                      "baad fix, phir ye number nahi badlega.%s 2 Jan, 4 Jan%s"
                                      % (_ist(PART_NEXT), OLD, GONE))
        assert _tday(c["Puzzle Quest"][0]) == _day_tip(_hh(PART_NEXT), " Fixed — ye number ab nahi badlega.")
        assert len(c["Puzzle Quest"][0].split("\n")) == 2
    late = _tday(_cells(ov["daylate|USD"])["Demo Gallery"][0])
    assert late == _day_tip(_hh(DAY_LATE), " 3/8 din ka number fixed hai. 7 Jan abhi bhar raha hai — agle refresh me "
                            "fix (~%s tak), phir ye number nahi badlega.%s 2 Jan, 4 Jan%s"
                            % (_ist(DAY_LATE + timedelta(hours=3)), OLD, GONE))
    miss = _tday(_cells(ov["daymiss|USD"])["Demo Gallery"][0])
    assert miss == _day_tip(_hh(DAY_MISS), " 3/8 din ka number fixed hai.%s 2 Jan, 4 Jan, 7 Jan%s" % (OLD, GONE))
    # more than 3 dates that do not follow each other: counted, "me se"
    holes = _tday(_cells(ov["dayholes|USD"])["Demo Gallery"][0])
    assert holes == _day_tip(_hh(DAY_MISS), " 2/8 din ka number fixed hai.%s 4 din (2 Jan–7 Jan me se)%s"
                             % (OLD, GONE))


def test_day_each_app_at_its_own_moment(ov):
    """by_app[app].d0day_next (its stores' zone) over d0.day_next: Demo's stores in a later zone — 7 Jan's morning is
    still ahead for Demo although every account's moment passed 4 h ago ("daymiss"); a moment that is still the
    install date in IST: "usi din raat"; one in the IST evening: "agle din", no "subah"."""
    c = _cells(ov["dayzone|USD"])
    tip, lines = c["Demo Gallery"]
    assert lines[2:] == ["⏳ Day filling"]
    assert _tday(tip) == _day_tip(_hh(PART_NEXT), " 3/8 din ka number fixed hai. 7 Jan abhi bhar raha hai — ~%s ke "
                                  "baad fix, phir ye number nahi badlega.%s 2 Jan, 4 Jan%s"
                                  % (_ist(PART_NEXT), OLD, GONE))
    c = _cells(ov["daylater|USD"])
    assert _tday(c["Puzzle Quest"][0]) == _day_tip("22:30", " Fixed — ye number ab nahi badlega.", when="usi din")
    assert _tday(c["Demo Gallery"][0]).startswith("Day = install ke din raat 12 baje tak — agle din ~17:30 IST ka ")


def test_day_before_the_first_number(ov):
    """Day keys with nothing taken yet (just switched on): "Day —", 7 Jan filling at its moment, every earlier date
    "abhi shuru nahi hua"; the 24h line unchanged."""
    hh = (PART_NEXT + timedelta(hours=5, minutes=30)).strftime("%H:%M")
    for view in ("USD", "INR"):
        c = _cells(ov[f"nostart|{view}"])
        tip, lines = c["Demo Gallery"]
        assert lines[1:] == ["Day —", "⏳ filling"] and lines[0] == _cells(ov[f"fill|{view}"])["Demo Gallery"][1][0]
        assert _tday(tip) == _day_tip(hh, " 7 Jan abhi bhar raha hai — ~%s ke baad fix, phir ye number nahi badlega. "
                                      "Day number abhi shuru nahi hua (Google Ads subah wala purana number nahi "
                                      "rakhta) — 7 din (31 Dec 2025–6 Jan 2026) ka nahi hai." % _ist(PART_NEXT))
        tip, lines = c["Puzzle Quest"]
        assert lines == [lines[0], "Day —"] and _tday(tip) == _day_tip(
            hh, " Day number abhi shuru nahi hua (Google Ads subah wala purana number nahi rakhta) — 4 din "
                "(2 Jan–5 Jan) ka nahi hai.")
    for view in ("USD", "INR"):                                                    # no roas.d0: as before
        assert all(t is None and not any("Day" in x for x in ln) for t, ln in _cells(ov[f"nod0|{view}"]).values())
