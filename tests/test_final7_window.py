"""GA4_FINAL_DAYS (admob_iq.ga4_final; owner, 17 Nov 2026: "max to max 7 din me to aa hi jaata he") on the window
stores — each store's copy at another F (the final_days fixture, tests/conftest.py) beside the store at the pin
(final_days.pin: the session's own, or its copy at 3 in a session the caller runs at another F):
  * the windows at every F (3 … 14): ga4_nvr / ga4_nvr_paid / ga4_nvr_uc / ga4_newusers / ga4_source / ga4_source_cty
    re-read today … FINAL_LAG days back (the last read of a day made on day D + FINAL_LAG); ga4_firstopen keeps its 15
    days (≥ F + 1); ga4_firstopen_cc's window = FINAL_LAG (every day not final: its newest HOT_DAYS every refresh, the
    older ones at most once a UTC day); ga4_screens' recent window = FINAL_LAG, the page's period end (PU_LAG) the same
    at any F; at 3 each one exactly as before the knob;
  * F = 7: the 8-day windows (the day turning 7 old read, then never; the history from the day before; nvr's lone read
    of a sampled day once it left the window; an outage caught up), the day's last read whole where GA4 is still adding
    to it until 7 days old; firstopen_cc's older not-final days (once a UTC day, the final read at 7 under the held
    rule, a deploy's days read final at 3 … 6 days old read again, a collapsed answer never taking a stored read's
    place, a UTC day of hourly runs, "mid" gone at the pin); screens' edges (final today − 7, the recent window 7 days,
    a deploy's days final at 5 read as recent and then keeping that final record, a period final only once it ends ≤
    today − 7, the page's periods unchanged).
SYNTHETIC values only (this repo is public)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import ga4_final
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_firstopen_cc as fc
from admob_iq.fetch import ga4_newusers as gn
from admob_iq.fetch import ga4_nvr as gv
from admob_iq.fetch import ga4_nvr_paid as gvp
from admob_iq.fetch import ga4_nvr_uc as gvu
from admob_iq.fetch import ga4_screens as gs
from admob_iq.fetch import ga4_source as gsrc
from admob_iq.fetch import ga4_source_cty as gsc
from admob_iq.fetch import ga4_uninstall as gu
from tests import test_ga4_screens as tsc
from tests.test_ga4_firstopen_cc import STEPS, FakeGa

NOW = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 2)
WHOLE = {"AA": (60, 50, 30), "BB": (40, 30, 20)}          # first opens, splash, home: [107, 86, 55] with the 7 unnamed
LOW = {"AA": (2, 2, 1)}                                     # GA4 answering a day collapsed (with unnamed 1, 1, 1)


def ago(n, today=TODAY):
    return today - timedelta(days=n)


def _iso(d):
    return d.isoformat()


def _utc(day, h):
    return datetime(day.year, day.month, day.day, h, 30, tzinfo=timezone.utc)


# ── the windows at every F ──────────────────────────────────────────────────────────────────────────────────────────
def test_at_the_pin_every_window_is_the_one_before_the_knob(final_days):
    """GA4_FINAL_DAYS 3 (the pin, the rollback): each store's lag and window exactly as before the knob."""
    v, vp, vu, nu, src, sc, fo, cc, scr = final_days.pin(gv, gvp, gvu, gn, gsrc, gsc, gf, fc, gs)
    assert ga4_final.FINAL_DAYS == 3
    for m in (v, vp.MOD, vu, nu, src, sc):
        assert (m.FINAL_LAG, m.RECENT_DAYS) == (4, 5), m.__name__
    assert (fo.FINAL_LAG, fo.RECENT_DAYS) == (3, 15)
    assert (cc.HOT_DAYS, cc.FINAL_LAG, cc.RECENT_DAYS, cc.mid_days(TODAY)) == (3, 3, 3, [])
    assert (scr.FINAL_LAG, scr.RECENT_DAYS, scr.PU_LAG) == (5, 5, 2)


def test_every_window_derives_from_the_knob(final_days):
    """Each store's copy at every F the knob allows (a store copied before the ones that import it)."""
    for f in range(ga4_final.LO, ga4_final.HI + 1):
        v, vp, src, vu, nu, sc, cc, scr, fo = final_days(f, gv, gvp, gsrc, gvu, gn, gsc, fc, gs, gf)
        assert ga4_final.FINAL_DAYS == f
        for m in (v, vp.MOD, vu, nu, src, sc):                       # pattern B: the day turning final read in it
            assert (m.FINAL_LAG, m.RECENT_DAYS) == (max(4, f), max(4, f) + 1), (f, m.__name__)
        assert vp.MOD.PARTS == ("c",) and vu.gv is v                 # (the paid instance and nvr_uc on nvr's copy)
        assert (fo.FINAL_LAG, fo.RECENT_DAYS) == (f, 15) and fo.RECENT_DAYS >= fo.FINAL_LAG + 1
        assert (cc.HOT_DAYS, cc.FINAL_LAG, cc.RECENT_DAYS) == (3, f, f) and cc.FINAL_LAG == fo.FINAL_LAG
        assert cc.mid_days(TODAY) == [ago(i) for i in range(3, f)]
        assert (scr.FINAL_LAG, scr.RECENT_DAYS, scr.PU_LAG) == (max(5, f), max(5, f), 2)
        assert scr.pu_wanted(TODAY, ago(200)) == gs.pu_wanted(TODAY, ago(200))   # the page's periods: any F


# ── pattern B: the 8-day windows ────────────────────────────────────────────────────────────────────────────────────
class Ranges:
    """report_all as ga4.Ga4App's: GA4 names nothing (no rows); every date range asked kept, in order."""

    def __init__(self):
        self.calls, self.tok, self.asked, self.last_metas = 0, 0, [], [{}]

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        self.calls += 1
        r = body["dateRanges"][0]
        self.asked.append((r["startDate"], r["endDate"]))
        return []


MODS = {"ga4_nvr": gv, "ga4_newusers": gn, "ga4_source": gsrc, "ga4_nvr_uc": gvu, "ga4_source_cty": gsc}
MONTHLY = ("ga4_nvr_uc", "ga4_source_cty")                  # (step_app on the month files: data_dir, app id)
PER_RANGE = {"ga4_nvr": 3, "ga4_nvr_paid": 1, "ga4_newusers": 2, "ga4_source": 1, "ga4_nvr_uc": 1, "ga4_source_cty": 1}


def _at7(final_days, name):
    if name == "ga4_nvr_paid":
        return final_days(7, gv, gvp)[1].MOD
    return final_days(7, MODS[name])


def _step(name, m, ga, st, today, hs, now, root):
    if name in MONTHLY:
        return m.step_app(ga, st, root, "app-1", today, hs, now)
    return m.step_app(ga, st, today, hs, now)


@pytest.mark.parametrize("name", sorted(PER_RANGE))
def test_a_window_store_reads_today_and_7_days_back_and_the_history_from_the_day_before(final_days, tmp_path, name):
    m, per, root, hs = _at7(final_days, name), PER_RANGE[name], str(tmp_path), ago(40)
    assert (m.FINAL_LAG, m.RECENT_DAYS) == (7, 8)
    ga, st = Ranges(), {"v": m.STORE_V}
    assert _step(name, m, ga, st, TODAY, hs, NOW, root) == "fetched"
    rng = ga.asked[::per]
    assert rng[0] == (_iso(ago(7)), _iso(TODAY))                     # the day turning 7 old … today
    assert rng[1][1] == _iso(ago(8)) and min(a for a, _ in rng[1:]) == _iso(hs)   # the history: from the day before
    assert st["backfill"] == {"oldest": _iso(hs), "done": True}
    ga = Ranges()                                                    # its next refresh: the same 8 days again
    _step(name, m, ga, st, TODAY, hs, NOW + timedelta(hours=m.REFRESH_HOURS), root)
    assert ga.asked[::per] == [(_iso(ago(7)), _iso(TODAY))]
    nxt, ga = TODAY + timedelta(days=1), Ranges()                    # a day on: the 7-day-old day had its last read
    _step(name, m, ga, st, nxt, hs, NOW + timedelta(days=1), root)
    assert ga.asked[::per] == [(_iso(ago(6)), _iso(nxt))]


class Filling(Ranges):
    """GA4 still adding to a day until it is 7 days old: the country read's ad revenue of a day read at age a (by the
    run's today) is min(a + 1, 8) — whole (8) only from 7 days old on."""

    def __init__(self, today):
        super().__init__()
        self.today = today

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        super().report_all(body, event, events, extra, page_rows)
        if "countryId" not in [x["name"] for x in body["dimensions"]]:
            return []
        a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
        rows, d = [], a
        while d <= b:
            rows.append({"date": d.strftime("%Y%m%d"), "newVsReturning": "new", "countryId": "XA",
                         "totalAdRevenue": min((self.today - d).days + 1, 8), "eventCount": 80})
            d += timedelta(days=1)
        return rows


@pytest.mark.parametrize("f, kept", [(3, 5), (7, 8)])
def test_a_days_last_read_is_made_final_lag_days_on(final_days, f, kept):
    """A run every day: a day that left the window keeps the read made FINAL_LAG days after it — at the pin 4 days on,
    before GA4 finished adding to it (5 of 8); at 7, whole."""
    v = final_days(f, gv)
    hs, store = ago(v.RECENT_DAYS - 1), {"v": v.STORE_V}          # (no history before the first window)
    for i in range(12):
        today = TODAY + timedelta(days=i)
        v.step_app(Filling(today), store, today, hs, NOW + timedelta(days=i))
    last = TODAY + timedelta(days=11)
    gone = [d for d in store["days"] if (last - date.fromisoformat(d)).days >= v.RECENT_DAYS]   # left the window
    assert len(gone) == 11 and all(store["days"][d]["c"] == [["n", "XA", kept, 80]] for d in gone)
    young = _iso(last - timedelta(days=v.FINAL_LAG))                # read today, its last read: final
    assert store["days"][young]["c"] == [["n", "XA", min(v.FINAL_LAG + 1, 8), 80]]
    assert store["days"][_iso(last)]["c"] == [["n", "XA", 1, 80]]   # today: GA4 still adding


def test_nvr_reads_a_sampled_day_alone_only_once_it_left_the_8_day_window(final_days):
    v = final_days(7, gv)

    class Raw(Ranges):                                              # GA4 samples a range reaching into the window
        def __init__(self, today):
            super().__init__()
            self.today = today

        def report_all(self, body, **kw):
            rows = super().report_all(body, **kw)
            b = date.fromisoformat(body["dateRanges"][0]["endDate"])
            self.last_metas = ([{"samplingMetadatas": [{"samplesReadCount": "1"}]}]
                               if b > self.today - timedelta(days=v.RECENT_DAYS) else [{}])
            return rows
    hs, store = ago(20), {"v": v.STORE_V}
    v.step_app(Raw(TODAY), store, TODAY, hs, NOW)
    assert sorted(store["mark"]) == [_iso(ago(i)) for i in range(7, -1, -1)] and store["rr"] == {}
    nxt, ga = TODAY + timedelta(days=1), Raw(TODAY + timedelta(days=1))
    v.step_app(ga, store, nxt, hs, NOW + timedelta(days=1))
    assert ga.asked[::3] == [(_iso(ago(6)), _iso(nxt)), (_iso(ago(7)), _iso(ago(7)))]   # the window, then the day
    assert store["rr"] == {_iso(ago(7)): 1} and _iso(ago(7)) not in store["mark"]       # that left it, alone, whole


class Sampling(Ranges):
    """GA4 sampling a range that reaches into the newest `window` days (a busy app's still-changing days), every other
    read whole."""

    def __init__(self, today, window):
        super().__init__()
        self.today, self.window = today, window

    def report_all(self, body, **kw):
        rows = super().report_all(body, **kw)
        b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        self.last_metas = ([{"samplingMetadatas": [{"samplesReadCount": "1"}]}]
                           if b > self.today - timedelta(days=self.window) else [{}])
        return rows


@pytest.mark.parametrize("paid", (False, True))
def test_nvr_a_day_read_alone_under_the_pins_window_is_read_alone_again_once_it_left_the_8_day_one(final_days, paid):
    """The pin read the days that left its 5-day window alone, whole ("rr"); at 7 the 8-day window reads the youngest
    of them again (sampled: a range reaching into it) — they leave "rr", so each is read alone, whole, once it leaves
    that window too; never left sampled for good. The paid instance the same."""
    v3, vp3 = final_days.pin(gv, gvp)
    v, hs, store = (vp3.MOD if paid else v3), ago(20), {}
    store["v"] = v.STORE_V
    for i in (3, 2, 1, 0):                                          # the pin: a day a run
        T = ago(i)
        v.step_app(Sampling(T, v.RECENT_DAYS), store, T, hs, NOW - timedelta(days=i))
    assert sorted(store["rr"]) == [_iso(ago(i)) for i in (7, 6, 5)] and not {_iso(ago(i)) for i in (7, 6, 5)} & set(
        store["mark"])
    v7 = final_days(7, gv, gvp)[1].MOD if paid else final_days(7, gv)
    for i in (1, 2, 3):                                             # at 7, a day a run
        T = TODAY + timedelta(days=i)
        ga = Sampling(T, v7.RECENT_DAYS)
        v7.step_app(ga, store, T, hs, NOW + timedelta(days=i))
        if i == 1:                                                  # the 8-day window: ago(6), ago(5) read again,
            assert ga.asked[::len(v7.PARTS)] == [(_iso(ago(6)), _iso(T))]          # sampled — out of "rr"
            assert store["mark"][_iso(ago(6))] == store["mark"][_iso(ago(5))] == "s"
            assert sorted(store["rr"]) == [_iso(ago(7))]
        else:                                                       # … each read alone once it left it
            gone = _iso(ago(8, T))
            assert ga.asked[::len(v7.PARTS)][1:] == [(gone, gone)] and gone in store["rr"], i
    for d in (ago(6), ago(5)):
        assert _iso(d) not in store["mark"] and store["mp"][_iso(d)] == {}


@pytest.mark.parametrize("name", MONTHLY)
def test_an_outage_is_caught_up_to_the_8_day_window(final_days, tmp_path, name):
    m, hs, root = final_days(7, MODS[name]), ago(30), str(tmp_path)
    meta = {"v": m.STORE_V}
    m.step_app(Ranges(), meta, root, "app-1", TODAY, hs, NOW)
    back, ga = TODAY + timedelta(days=10), Ranges()                 # ten days without a run
    m.step_app(ga, meta, root, "app-1", back, hs, NOW + timedelta(days=10))
    assert ga.asked == [(_iso(TODAY + timedelta(days=1)), _iso(ago(8, back))), (_iso(ago(7, back)), _iso(back))]
    assert meta["upto"] == _iso(back)


# ── ga4_firstopen_cc: the newest 3 days every refresh, the older not-final ones once a UTC day ──────────────────────
def _days_read(ga):
    """The days a run read, in order (each day's total: the funnel broken down by date)."""
    return [date.fromisoformat(b["dateRanges"][0]["startDate"]) for b in ga.bodies
            if b["funnelBreakdown"]["breakdownDimension"]["name"] == "date"]


def _rec(t, fin, at="2026-11-01T06:00:00Z"):
    return {"c": {"AA": [t[0] - 7, t[1] - 6, t[2] - 5]}, "t": list(t), "smp": None, "fin": fin, "sg": fc.sig(STEPS),
            "at": at}


def test_firstopen_cc_hot_days_every_refresh_older_not_final_days_once_a_utc_day_final_at_7(final_days):
    c = final_days(7, fc)
    first, store = ago(9), {"v": c.STORE_V}                         # (the First open store's day 1)
    ga = FakeGa()
    assert c.step_app(ga, store, STEPS, TODAY, NOW, first) == "fetched"
    # the newest 3, the older not-final ones (3 … 6 days old), then the backfill to the newest final day (7 old)
    assert _days_read(ga) == [ago(i) for i in range(7)] + [ago(9), ago(8), ago(7)]
    assert [store["days"][_iso(ago(i))]["fin"] for i in range(10)] == [False] * 7 + [True] * 3
    assert store["mid"] == {_iso(ago(i)): "2026-11-02T06:00:00Z" for i in range(3, 7)}
    assert store["recent_at"] == "2026-11-02T06:00:00Z"
    ga = FakeGa()                                                   # 6 h on, the same UTC day: the newest 3 only
    c.step_app(ga, store, STEPS, TODAY, NOW + timedelta(hours=6), first)
    assert _days_read(ga) == [ago(i) for i in range(3)]
    ga = FakeGa()                                                   # an hour on: nothing
    assert c.step_app(ga, store, STEPS, TODAY, NOW + timedelta(hours=7), first) == "fresh" and ga.calls == 0
    nxt, ga = TODAY + timedelta(days=1), FakeGa()                   # the next UTC day: the day turning 7 old read
    c.step_app(ga, store, STEPS, nxt, _utc(nxt, 2), first)          # final (before them), each older one once more
    assert _days_read(ga) == [ago(i, nxt) for i in (0, 1, 2, 7, 3, 4, 5, 6)]
    assert store["days"][_iso(ago(7, nxt))]["fin"] is True and store["days"][_iso(ago(6, nxt))]["fin"] is False
    assert sorted(store["mid"]) == sorted(_iso(ago(i, nxt)) for i in range(3, 7))       # (the final one left it)


def test_a_utc_day_of_hourly_runs_reads_each_older_not_final_day_once(final_days):
    """The cost rule: over one UTC day the newest 3 days are read every 6 h, each older not-final day once, the day
    turning final once — at the pin the same runs read the newest 3 and the day turning final (3 days old) only."""
    def day_of_runs(mod):
        store, first = {"v": mod.STORE_V}, ago(12)
        mod.step_app(FakeGa(), store, STEPS, ago(1), datetime(2026, 11, 1, 20, tzinfo=timezone.utc), first)
        reads = {}
        for h in range(24):
            ga = FakeGa()
            mod.step_app(ga, store, STEPS, TODAY, _utc(TODAY, h), first)
            for d in _days_read(ga):
                reads[(TODAY - d).days] = reads.get((TODAY - d).days, 0) + 1
        return reads
    assert day_of_runs(final_days.pin(fc)) == {0: 4, 1: 4, 2: 4, 3: 1}
    assert day_of_runs(final_days(7, fc)) == {0: 4, 1: 4, 2: 4, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1}


def test_a_deploy_reads_the_days_read_final_at_3_again_until_they_are_7_days_old(final_days):
    """A store as the pin kept it (days 3 … 11 days old read final at 3): the ones younger than 7 are read again as not
    final, the older ones kept as they were; the next UTC day the one turning 7 gets its final read — GA4 answering it
    collapsed, its earlier read is held."""
    c = final_days(7, fc)
    whole = (107, 86, 55)
    store = {"v": c.STORE_V, "recent_at": "2026-11-01T23:00:00Z",
             "days": {_iso(ago(i)): _rec(whole, i >= 3) for i in range(12)}}
    ga = FakeGa(data=WHOLE)
    c.step_app(ga, store, STEPS, TODAY, NOW, ago(11))
    assert _days_read(ga) == [ago(i) for i in range(7)]
    assert [store["days"][_iso(ago(i))]["fin"] for i in range(12)] == [False] * 7 + [True] * 5
    assert all(store["days"][_iso(ago(i))]["at"] == "2026-11-01T06:00:00Z" for i in range(7, 12))
    nxt, tally = TODAY + timedelta(days=1), {}
    ga = FakeGa(data=LOW, unnamed=(1, 1, 1))
    c.step_app(ga, store, STEPS, nxt, _utc(nxt, 2), ago(11), tally=tally)
    k = _iso(ago(6))                                                # 7 days old now: its final read, collapsed
    assert store["days"][k]["fin"] is True and store["days"][k]["ho"] == 1 and store["days"][k]["t"] == list(whole)
    assert tally == {"held": 1}
    for i in range(2, 6):                                           # the older not-final ones keep their reads
        assert store["days"][_iso(ago(i))]["t"] == list(whole) and store["days"][_iso(ago(i))]["fin"] is False


def test_a_deploy_with_no_read_due_before_utc_midnight_still_gives_each_young_day_its_read_at_7(final_days, tmp_path,
                                                                                                monkeypatch):
    """The deploy two and a half hours after the pin's last refresh, before UTC midnight: no read is due in its runs,
    yet the days the pin kept final at D+3 that are not 7 days old are made not final at once — the store written with
    no call made — so the one turning 7 at midnight gets its final read (never left as read at D+3); a held day stays."""
    from admob_iq.db import write_json_gz_stable
    c = final_days(7, fc)
    aid, whole = "ca-app-pub-0~a", (107, 86, 55)
    data = str(tmp_path)
    days = {_iso(ago(i)): _rec(whole, i >= 3) for i in range(7)}
    days[_iso(ago(5))].update(ho=1)                                 # (held at its D+3 read: the short days' rule)
    write_json_gz_stable(c.store_path(data, aid), {"v": c.STORE_V, "recent_at": "2026-11-02T19:00:00Z", "days": days})
    write_json_gz_stable(gf.store_path(data, aid), {"v": gf.STORE_V, "app_id": aid, "steps": STEPS, "time_zone": "UTC",
                                                    "days": {_iso(ago(i)): {"first_open": 107} for i in range(7)}})
    calls = []
    monkeypatch.setattr(gf, "App", lambda tok, pid, sid, prop, over=None, max_calls=gf.MAX_CALLS:
                        calls.append(pid) or type("A", (), {"calls": 0, "tok": 0, "property_id": pid})())
    monkeypatch.setattr(c.ga4, "access_token", lambda *a: "tok")
    monkeypatch.setattr(c.ga4_probe, "owner_tokens", lambda env: ([("o", "rt")], None))
    monkeypatch.setattr(gu, "load_state", lambda d: {"routes": {"by_package": {"pkg.a": {
        "property_id": "P1", "stream_id": "s", "owner": "o"}}}, "tz": {}})
    out = c.refresh_all({"client_id": "c", "client_secret": "s", "refresh_tokens": "x"}, data,
                        [{"app_id": aid, "package": "pkg.a"}], now=datetime(2026, 11, 2, 21, 30, tzinfo=timezone.utc),
                        workers=1)
    assert out["apps"][aid] == "fresh" and calls == ["P1"] and out["counts"]["calls"] == 0     # nothing read …
    st = c.load_store(c.store_path(data, aid))
    assert [st["days"][_iso(ago(i))]["fin"] for i in (3, 4, 5, 6)] == [False, False, True, False]   # … all the same
    nxt = TODAY + timedelta(days=1)
    ga = FakeGa(data=WHOLE)                                         # 00:30 UTC: the day the pin read at D+3 when 3
    c.step_app(ga, st, STEPS, nxt, _utc(nxt, 0), ago(6))            # days old is 7 now — its final read
    assert _days_read(ga) == [ago(6)] and st["days"][_iso(ago(6))]["fin"] is True
    assert st["days"][_iso(ago(6))]["at"] == "2026-11-03T00:30:00Z" and st["days"][_iso(ago(5))] == days[_iso(ago(5))]


def test_a_collapsed_answer_of_an_older_not_final_day_keeps_its_stored_read(final_days):
    c = final_days(7, fc)
    k = _iso(ago(4))
    prev = _rec((104, 83, 53), True, at="2026-10-31T00:01:00Z")    # read final at 3 days old (the pin's rule)
    store = {"v": c.STORE_V, "recent_at": "2026-11-01T23:00:00Z", "days": {k: dict(prev)}}
    c.step_app(FakeGa(data=LOW, unnamed=(1, 1, 1)), store, STEPS, TODAY, NOW, ago(4))
    assert store["days"][k] == dict(prev, fin=False)                # its read stays, not final: read again at 7
    assert store["mid"][k] == "2026-11-02T06:00:00Z"
    ga = FakeGa(data=WHOLE)
    c.step_app(ga, store, STEPS, TODAY, NOW + timedelta(hours=6), ago(4))
    assert ago(4) not in _days_read(ga) and store["days"][k] == dict(prev, fin=False)   # once a UTC day
    nxt = TODAY + timedelta(days=1)                                 # the next UTC day GA4 answers it whole: taken
    c.step_app(FakeGa(data=WHOLE), store, STEPS, nxt, _utc(nxt, 2), ago(4))
    assert store["days"][k]["t"] == [107, 86, 55] and store["days"][k]["fin"] is False
    assert store["days"][k]["at"] == "2026-11-03T02:30:00Z"


def test_a_not_final_day_ga4_names_no_country_for_is_never_stored_as_none(final_days):
    class Empty(FakeGa):
        def report_all(self, body, event=None, **k):
            return []
    c, store = final_days(7, fc), {}
    assert c.step_app(Empty(), store, STEPS, TODAY, NOW, ago(9)) == "fetched"
    assert {k for k in store["days"]} == {_iso(ago(i)) for i in (7, 8, 9)}      # the final ones only
    assert store["days"][_iso(ago(7))] == {"none": True, "at": "2026-11-02T06:00:00Z"}
    assert sorted(store["mid"]) == sorted(_iso(ago(i)) for i in range(3, 7))    # (asked: not again today)


def test_at_the_pin_a_store_never_gets_mid_and_a_rollback_drops_it(final_days):
    c = final_days.pin(fc)
    store = {"v": c.STORE_V}
    c.step_app(FakeGa(), store, STEPS, TODAY, NOW, ago(5))
    assert "mid" not in store and sorted(store["days"]) == [_iso(ago(i)) for i in range(5, -1, -1)]
    store = {"v": c.STORE_V, "mid": {_iso(ago(4)): "2026-11-01T06:00:00Z", _iso(ago(1)): "x"}}    # kept at 7
    c.step_app(FakeGa(), store, STEPS, TODAY, NOW, ago(5))
    assert "mid" not in store


# ── ga4_screens: the edges at 7 ─────────────────────────────────────────────────────────────────────────────────────
def _job(mod, tmp_path, ga, now=tsc.NOW):
    job = mod.Job(str(tmp_path / "data" / mod.DIR), tsc._it(), now, ga, lambda: ga.clock[0])
    job.meta["events"] = {"at": gu._now_iso(now), "names": []}     # (the event list fresh: no read of it)
    return job


def test_screens_final_edge_and_recent_window_at_7(final_days, tmp_path):
    s, T = final_days(7, gs), tsc.TODAY
    ga = tsc.FakeGA()
    job = _job(s, tmp_path, ga)
    assert (job.final_end, job.recent_start) == (T - timedelta(days=7), T - timedelta(days=6))
    for rid in s.ORDER:                                             # every history read: the recent window only
        job.rd(rid).update(upto=_iso(job.final_end), oldest="2026-10-01", done=True)
    s.step_recent(job)
    assert {(q.a, q.b) for q in ga.asked} == {(T - timedelta(days=6), T)}
    assert sorted(s.load_recent(str(tmp_path / "data"), tsc.KEY)) == s._days(T - timedelta(days=6), T)


def test_screens_deploy_days_final_at_5_are_read_as_recent_then_keep_that_final_record(final_days, tmp_path):
    """The pin's store holds today − 6 and today − 5 read final (5 days old); at 7 they are inside the recent window:
    read again as recent — and the next day the one turning 7 old keeps its final record (read at 5), not read again."""
    T = tsc.TODAY
    ga = tsc.FakeGA()
    s3 = final_days.pin(gs)
    pin = _job(s3, tmp_path, ga)
    old = [_iso(T - timedelta(days=5)), _iso(T - timedelta(days=6))]
    for rid in s3.ORDER:                                            # (t first: the reads tie it)
        s3.fill(pin, rid, old, True)
        pin.rd(rid).update(upto=_iso(pin.final_end), oldest="2026-10-01", done=True)
    pin.store.save_meta()
    assert not any(pin.needs(rid, d) for rid in s3.ORDER for d in old)
    s = final_days(7, gs)
    ga = tsc.FakeGA()
    job = _job(s, tmp_path, ga)
    s.step_recent(job)
    assert {(q.a, q.b) for q in ga.asked} == {(T - timedelta(days=6), T)}
    assert all(job.rd(rid)["upto"] == _iso(T - timedelta(days=7)) for rid in s.ORDER)
    nxt = tsc.NOW + timedelta(days=1)
    ga = tsc.FakeGA()
    job = _job(s, tmp_path, ga, nxt)
    s.step_recent(job)
    assert {(q.a, q.b) for q in ga.asked} == {(T - timedelta(days=5), T + timedelta(days=1))}
    rec = tsc._final(tmp_path, "core", "2026-10")[old[1]]["v"]     # its final read (at 5), not the recent copy
    assert rec["st"] == "w" and "rc" not in rec and not job.needs("v", old[1])


def test_screens_a_period_is_final_only_once_it_ends_7_days_back_and_the_pages_periods_keep_their_end(final_days,
                                                                                                         tmp_path):
    s3 = final_days.pin(gs)
    s, T = final_days(7, gs), tsc.TODAY
    assert s.pu_wanted(T, date(2026, 8, 20)) == s3.pu_wanted(T, date(2026, 8, 20))
    roll = [hi for _, _, hi, kd in s.pu_wanted(T, date(2026, 8, 20)) if kd == "roll"]
    assert set(roll) == {T - timedelta(days=s3.PU_LAG)}             # td − 2: the page's latest day, at any F
    job, lo = _job(s, tmp_path, tsc.FakeGA()), T - timedelta(days=20)
    assert "fin" not in s.read_users(job, lo, T - timedelta(days=6))
    assert s.read_users(job, lo, T - timedelta(days=7))["fin"] == 1
    pin = _job(s3, tmp_path, tsc.FakeGA())
    assert s3.read_users(pin, lo, T - timedelta(days=6))["fin"] == 1   # (at the pin: final from 5 days back)
    rec = {"st": "w", "at": gu._now_iso(tsc.NOW - timedelta(hours=7))}
    assert s._pu_due(rec, "month", T - timedelta(days=6), job.final_end, tsc.NOW)         # not final: its 6 h
    assert not s._pu_due(rec, "month", T - timedelta(days=6), pin.final_end, tsc.NOW)     # final: once a day
