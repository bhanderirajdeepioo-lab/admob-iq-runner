"""📅 The forecast's eCPM calendar (admob_iq.engine.fc_calendar) on made-up ad-unit rows whose events are known: the
calendar's days (Thanksgiving, the base, the events, the hold), the like-for-like index (each unit against its own
base; √ of an app's revenue so no single app decides; iOS, thin and short units left out), the seasons a day may use
(no look-ahead: a season counts once its January week 6 is over, read only to that day), the shrink toward no effect,
the staircase level and the closed slide. No real data."""
import math
from datetime import date, timedelta

from admob_iq.engine import fc_calendar as FC

ONE = timedelta(days=1)


def test_the_calendar_days():
    assert [FC.thanksgiving(y) for y in (2023, 2024, 2025, 2026)] == [
        date(2023, 11, 23), date(2024, 11, 28), date(2025, 11, 27), date(2026, 11, 26)]
    assert FC.base_window(2025) == (date(2025, 11, 3), date(2025, 11, 23))           # the 3 weeks before TG week
    assert FC.event_days(2025, "bf") == (date(2025, 11, 24), date(2025, 11, 30))
    assert FC.event_days(2025, "cyber") == (date(2025, 12, 1), date(2025, 12, 7))
    assert FC.event_days(2025, "dec") == (date(2025, 12, 8), date(2025, 12, 21))
    assert FC.event_days(2025, "xmas") == (date(2025, 12, 22), date(2025, 12, 31))
    assert FC.event_days(2025, "j1") == (date(2026, 1, 1), date(2026, 1, 7))
    assert FC.event_days(2025, "j6") == (date(2026, 2, 5), date(2026, 2, 11))
    assert FC.hold_start(2025) == date(2026, 2, 12)
    assert FC.season_of(date(2026, 1, 10)) == 2025 and FC.season_of(date(2026, 10, 15)) == 2025
    assert FC.season_of(date(2026, 11, 2)) == 2026 and FC.season_of(date(2025, 11, 2)) == 2024
    assert FC.event_of(2025, date(2025, 11, 2)) is None and FC.event_of(2025, date(2025, 11, 10)) == "base"
    assert FC.event_of(2025, date(2025, 11, 27)) == "bf" and FC.event_of(2025, date(2026, 1, 15)) == "j3"
    assert FC.event_of(2025, date(2026, 2, 12)) == "hold" and FC.event_of(2025, date(2026, 10, 1)) == "hold"


def _rows(seasons=(2023, 2024), ios=True):
    """2 apps × 2 units, 10,000 impressions a day at $2 eCPM and 2 % CTR from Oct 1 to Mar 31 of every season; app "A"
    (9× app "B"'s revenue) has eCPM ×1.5 in Black Friday week (CTR ×1.25, revenue per click ×1.2), app "B" none; every
    unit ×0.8 from Jan 1 on (revenue per click). + an iOS unit and a unit with only 10 base days (both left out)."""
    rows = []

    def add(app, unit, d, ecpm, ctr=0.02, imp=10000, plat="Android"):
        rows.append({"app_id": app, "ad_unit_id": unit, "platform": plat, "report_date": d.isoformat(),
                     "impressions": imp, "estimated_earnings_micros": round(ecpm * imp / 1000 * 1e6),
                     "clicks": round(imp * ctr)})
    for y in seasons:
        tg = FC.thanksgiving(y)
        d = date(y, 10, 1)
        while d <= date(y + 1, 3, 31):
            bf = tg - 3 * ONE <= d <= tg + 3 * ONE
            jan = d >= date(y + 1, 1, 1)
            for unit, app, scale in (("a1", "A", 4.5), ("a2", "A", 4.5), ("b1", "B", 0.5), ("b2", "B", 0.5)):
                e, c = 2.0 * scale, 0.02
                if bf and app == "A":
                    e, c = e * 1.5, c * 1.25
                if jan:
                    e *= 0.8
                add(app, unit, d, e, c)
            if ios:
                add("A", "ios", d, 50.0, plat="iOS")                     # an iOS unit: never in the index
            if d >= date(y, 11, 14):
                add("B", "short", d, 99.0)                                 # 10 base days only: left out
            d += ONE
    return rows


def test_the_index_like_for_like_and_no_app_decides():
    cal = FC.seasons(_rows(), date(2025, 3, 1))
    assert sorted(cal["s"]) == ["2023", "2024"] and cal["till"] == "2025-03-01"
    s = cal["s"]["2024"]
    assert s["units"] == 4 and s["apps"] == 2                           # iOS and the short unit are out
    ev = s["ev"]
    # app A 9× app B's revenue: weights √9 : √1 = 3 : 1 (revenue weights would be 9 : 1)
    assert abs(ev["bf"][0] - 0.75 * math.log(1.5)) < 1e-9
    assert abs(ev["bf"][1] - 0.75 * math.log(1.25)) < 2e-9 and abs(ev["bf"][2] - 0.75 * math.log(1.2)) < 2e-9
    assert all(abs(ev[k][0]) < 1e-9 for k in ("cyber", "dec", "xmas"))
    assert all(abs(ev["j%d" % k][0] - math.log(0.8)) < 1e-9 and abs(ev["j%d" % k][1]) < 1e-9 for k in range(1, 7))
    assert abs(ev["bf"][0] - (ev["bf"][1] + ev["bf"][2])) < 1e-12              # eCPM = CTR × revenue per click


def test_no_look_ahead_a_season_counts_once_its_week_6_is_over():
    rows = _rows()
    def done(c):
        return sorted(y for y, s in c["s"].items() if "ev" in s)
    early = FC.seasons(rows, date(2025, 2, 11))
    assert done(early) == ["2023"] and sorted(early["s"]) == ["2023", "2024"]       # 2024's week 6 ends Feb 11, 2025:
    assert max(early["s"]["2024"]["idx"]) == "2025-02-11"                          # in progress, its index so far
    assert done(FC.seasons(rows, date(2025, 2, 12))) == ["2023", "2024"]
    assert sorted(FC.seasons(rows, date(2024, 11, 23))["s"]) == ["2023"]            # 2024's base not over yet
    assert FC.profile(early, date(2025, 2, 11))[1] == 1
    # a season is read only to its own week 6: what comes after (here: a crash) changes nothing
    late = [dict(r, estimated_earnings_micros=1) if r["report_date"] >= "2025-02-12" else r for r in rows]
    assert FC.seasons(late, date(2025, 3, 1))["s"] == FC.seasons(rows, date(2025, 3, 1))["s"]
    cal = FC.seasons(rows, date(2025, 3, 1))
    assert FC.profile(cal, date(2025, 2, 11))[1] == 1 and FC.profile(cal, date(2025, 2, 12))[1] == 2
    assert FC.profile(cal, date(2024, 2, 11)) == (None, 0)


def test_the_profile_shrinks_toward_no_effect():
    cal = FC.seasons(_rows(), date(2025, 3, 1))
    raw, n = FC.profile(cal, date(2025, 6, 1), "ecpm", 0.0)
    sh, _ = FC.profile(cal, date(2025, 6, 1), "ecpm", 1.0)
    rpc, _ = FC.profile(cal, date(2025, 6, 1), "rpc", 0.0)
    assert n == 2 and all(abs(sh[e] - raw[e] * 2 / 3) < 1e-12 for e in FC.EVENTS)
    assert abs(raw["j3"] - math.log(0.8)) < 1e-9 and abs(rpc["bf"] - 0.75 * math.log(1.2)) < 2e-9
    # the page's range: the lowest / highest season (both alike here) + each season's apps; none before a season
    sp, ys = FC.spread(cal, date(2025, 6, 1))
    assert ys == [(2023, 2), (2024, 2)] and all(abs(sp[e][0] - raw[e]) < 1e-12 and abs(sp[e][1] - raw[e]) < 1e-12
                                                 for e in FC.EVENTS)
    assert FC.spread(cal, date(2024, 2, 11)) == (None, [])
    two = {"s": {"2023": {"ev": {e: [0.1, 0, 0] for e in FC.EVENTS}, "apps": 3},
                 "2024": {"ev": {e: [-0.2, 0, 0] for e in FC.EVENTS}, "apps": 5}}}
    sp, ys = FC.spread(two, date(2025, 6, 1))
    assert sp["bf"] == (-0.2, 0.1) and ys == [(2023, 3), (2024, 5)] and FC.spread(two, date(2025, 2, 11))[1] == [(2023, 3)]


def test_the_level_is_a_staircase_and_the_closed_slide():
    prof = {e: 0.0 for e in FC.EVENTS}
    prof.update(bf=0.1, cyber=0.05, xmas=-0.05, j1=-0.1, j2=-0.15, j3=-0.2, j4=-0.2, j5=-0.25, j6=-0.3)
    c = FC.Level(prof)
    base = c(date(2025, 10, 10))
    assert abs(c(date(2025, 11, 26)) - base - 0.1) < 1e-12 and abs(c(date(2025, 11, 10)) - base) < 1e-12
    assert abs(c(date(2026, 1, 16)) - base + 0.2) < 1e-12 and abs(c(date(2026, 2, 11)) - base + 0.3) < 1e-12
    assert abs(c(date(2026, 2, 12)) - base + 0.3) < 1e-12 and abs(c(date(2026, 10, 1)) - base + 0.3) < 1e-12   # held
    assert abs(c(date(2026, 11, 27)) - c(date(2026, 10, 1)) - 0.1) < 1e-12           # next season: from the held level
    # the slide over by TG: a reference window over January counts at the held level (no further drop expected)
    TG = date(2026, 2, 20)
    cr = FC.closed(c, TG)
    assert cr(date(2026, 1, 20)) == c(date(2026, 2, 12)) and cr(date(2025, 12, 25)) == c(date(2025, 12, 25))
    assert FC.closed(c, date(2026, 2, 10)) is c
    assert abs(FC.ref(cr, TG, 50) - c(TG)) < 1e-12 and FC.ref(c, TG, 50) > c(TG) + 0.05   # Jan 2 – Feb 20: all held
    assert abs(FC.ref(c, date(2025, 11, 30), 7) - c(date(2025, 11, 27))) < 1e-12
    r = FC.ref(c, date(2025, 12, 3), 7)                                               # 4 bf days + 3 cyber days
    assert abs(r - (base + math.log((4 * math.exp(0.1) + 3 * math.exp(0.05)) / 7))) < 1e-12


def test_the_coming_weeks():
    out = FC.coming(date(2025, 11, 25), 90)
    assert [x[0] for x in out] == ["bf", "cyber", "dec", "xmas", "j1", "j2", "j3", "j4", "j5", "j6", "hold"]
    assert out[0][1] == date(2025, 11, 24) and out[0][3][0] == date(2025, 11, 26)   # only its days inside the horizon
    out = FC.coming(date(2026, 1, 20), 60)
    assert [x[0] for x in out] == ["j3", "j4", "j5", "j6", "hold"] and out[-1][1] == date(2026, 2, 12)
    assert FC.coming(date(2026, 3, 1), 180) == [] and FC.coming(date(2026, 10, 15), 30) == []


def test_the_holiday_measure_is_a_gap_with_both_parts_kept():
    """Diwali 2025 on made-up country rows: India's eCPM +9 % and every other country's −3 % over the event days (each
    cell against its own base weeks) → x = the gap (log 1.09 − log 0.97), xt / xc = each group's own change; a move of
    the whole world on those days moves both parts but not the gap; holidays_coming hands both parts on (e^x − 1), and
    a measure made before the parts existed gives None for them."""
    bs, be, a, b = FC.holiday_windows("diwali", 2025)

    def rows(world):
        out, day = [], bs
        while day <= b:
            for app, cc, imp in (("a1", "IN", 30000), ("a1", "US", 20000), ("a2", "BR", 40000), ("a2", "IN", 25000),
                                  ("a3", "IN", 35000)):
                f = world * (1.09 if cc == "IN" else 0.97) if a <= day <= b else 1.0
                out.append({"report_date": day.isoformat(), "app_id": app, "country": cc, "impressions": imp,
                            "estimated_earnings_micros": round(imp * 0.002 * f * 1e6)})
            day += ONE
        return out
    till = date(2025, 11, 1)
    h = FC.holidays(rows(1.0), till)
    assert set(h) == {"diwali"} and h["diwali"]["y"] == 2025 and h["diwali"]["cells"] == [3, 2]
    m = h["diwali"]
    assert abs(m["xt"] - math.log(1.09)) < 1e-6 and abs(m["xc"] - math.log(0.97)) < 1e-6
    assert abs(m["x"] - (m["xt"] - m["xc"])) < 1e-12
    w = FC.holidays(rows(0.9), till)["diwali"]                                  # the whole world −10 % on those days
    assert abs(w["x"] - m["x"]) < 1e-6
    assert abs(w["xt"] - math.log(1.09 * 0.9)) < 1e-6 and abs(w["xc"] - math.log(0.97 * 0.9)) < 1e-6
    ev = FC.holidays_coming(h, date(2026, 10, 1), 90, {"diwali": 0.2})
    assert [e["k"] for e in ev] == ["diwali"] and ev[0]["a"] == "2026-11-01" and ev[0]["c"] == [3, 2]
    assert abs(ev[0]["xt"] - 0.09) < 1e-6 and abs(ev[0]["xc"] + 0.03) < 1e-6
    assert abs(ev[0]["x"] - (1.09 / 0.97 - 1)) < 1e-6 and abs(ev[0]["app"] - 0.2 * ev[0]["x"]) < 1e-12
    old = FC.holidays_coming({"diwali": {"y": 2025, "x": m["x"], "cells": [3, 2]}}, date(2026, 10, 1), 90, {})
    assert old[0]["xt"] is None and old[0]["xc"] is None and old[0]["s"] is None and old[0]["app"] is None


def test_anchored_reference_reads_the_season_in_progress_to_t_only():
    rows = _rows(seasons=(2023, 2024))
    cal = FC.seasons(rows, date(2024, 12, 20))                    # 2024 in progress: its index to Dec 20
    prof = {e: 0.0 for e in FC.EVENTS}
    prof.update(bf=0.3, j6=-0.2)
    c = FC.Level(prof)
    T, TG = date(2024, 12, 10), date(2024, 12, 5)
    a = FC.anchored(c, c, cal, T, TG)
    bf = date(2024, 11, 27)
    assert abs(a(bf) - (c(FC.base_window(2024)[0]) + 0.75 * math.log(1.5))) < 1e-9     # its own measured BF, not 0.3
    assert a(date(2024, 12, 12)) == c(date(2024, 12, 12))                             # after T: the profile
    assert a(date(2024, 10, 1)) == c(date(2024, 10, 1))                               # before its base: the profile
    assert FC.anchored(c, c, cal, T, date(2025, 2, 20)) is c                          # slide over by TG: as before
    assert FC.anchored(c, c, cal, date(2024, 11, 20), date(2024, 11, 15)) is c        # base not over by T


def test_the_weekday_rhythm_per_trigger():
    """An app whose after-call units (named as such) earn 40 % and dip 10 % on Sundays and whose splash units earn 10 %
    and peak 20 % on Mondays: each named trigger's own rhythm × its share (the in-feature rest flat), mean 1 over the
    week; too small a share, too few weeks, or only in-feature units: none."""
    rows, d = [], date(2026, 5, 1)
    while d <= date(2026, 10, 15):
        wd = d.weekday()
        for unit, name, rev in (("u1", "Home_inter", 50.0), ("u2", "CDO_native_after_call", 40.0 * (0.9 if wd == 6 else 1.0)),
                                ("u3", "Splash_open", 10.0 * (1.2 if wd == 0 else 1.0))):
            rows.append({"app_id": "A", "ad_unit_id": unit, "unit_name": name, "platform": "Android",
                         "report_date": d.isoformat(), "estimated_earnings_micros": rev * 1e6, "impressions": 1000})
        rows.append({"app_id": "B", "ad_unit_id": "u4", "unit_name": "Home_banner", "platform": "Android",
                     "report_date": d.isoformat(), "estimated_earnings_micros": 5e6, "impressions": 1000})
        d += ONE
    td = FC.trigger_days(rows, "2026-05-01", "2026-10-15")
    assert sorted(td["A"]) == ["after-call", "cold start", "in-feature"] and sorted(td["B"]) == ["in-feature"]
    T = date(2026, 10, 14)
    W = FC.weekday(td["A"], T)
    assert len(W) == 7 and abs(sum(W) / 7 - 1) < 1e-12

    def share(t):
        win = [k for k in td["A"][t] if "2026-08-20" <= k <= "2026-10-14"]
        return sum(td["A"][t][k] for k in win) / sum(td["A"][x][k] for x in td["A"] for k in win)
    sa, ss = share("after-call"), share("cold start")
    da, ds = math.log(0.9) * 6 / 7, math.log(1.2) * 6 / 7       # a weekday's log deviation from its centred week
    raw = [sa * math.exp(da if k == 6 else -da / 6) + ss * math.exp(ds if k == 0 else -ds / 6) + (1 - sa - ss)
           for k in range(7)]
    want = [x / (sum(raw) / 7) for x in raw]
    assert all(abs(a - b) < 1e-9 for a, b in zip(W, want)) and W[6] < 0.97 and W[0] > 1.0
    assert FC.weekday(td["B"], T) is None and FC.weekday(None, T) is None    # only in-feature units: flat
    assert FC.weekday(td["A"], date(2026, 6, 15)) is None                    # fewer than 8 weeks of each weekday
    assert [FC.trigger(n) for n in ("CDO_banner", "caller id inter", "Home_inter", "notif_open", "lang_native",
                                    "exit_inter", "resume_open")] == [
        "after-call", "after-call", "in-feature", "notification", "onboarding", "exit/back", "resume/bg"]
