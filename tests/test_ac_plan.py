"""Ad-unit × country pull with fewer AdMob calls (AcPlan: A' skip pieces before the first kept day, B'' split a piece
predicted far over the cap without the over-cap call; C accounts side by side) — replayed against the plain splitter
on a synthetic AdMob: the monthly rollup and the daily file come out as the SAME text (same rows, same order), the
truncation records are the same, and the calls made are a subset of the old ones. Synthetic data only; the cap is
lowered so the splits happen at the real shapes."""

import collections
import copy
import json
import zlib
from datetime import date, timedelta

import pytest

from admob_iq.db import InMemoryRepo
from admob_iq.engine.rollup import RollupAccumulator, first_kept_day
from admob_iq.fetch import admob_client, fetcher
from admob_iq.fetch.admob_client import AdMobClient

CAP = 1000
COUNTRIES = ["C%02d" % i for i in range(40)]


def _h(*parts):
    return zlib.crc32("|".join(map(str, parts)).encode())


class World:
    """A fixed synthetic AdMob: per account, apps × units × countries, each combo active on a day by a hash — so the
    rows of any date range are fixed — answered in an order that depends on the RANGE asked (as AdMob's own order
    is not by date): any change in which call returns a kept row would change the row order and fail the test."""

    def __init__(self, accounts, big=None):
        self.accounts = accounts                  # acct -> (apps, units per app, density %)
        self.big = big or {}                      # (acct, app, date) -> extra combos that day (an over-cap app-day)
        self.calls = []
        self.fail = set()                         # (acct, start, end) answered with an error, once
        self._cache = {}

    def rows(self, acct, d):
        k = (acct, d)
        if k not in self._cache:
            apps, units, dens = self.accounts[acct]
            out = []
            for a in range(apps):
                app = "%s~app%d" % (acct, a)
                for u in range(units):
                    unit = "%s/u%d" % (app, u)
                    for c in COUNTRIES:
                        if _h(acct, unit, c, d) % 100 < dens:
                            out.append((app, unit, c))
                for x in range(self.big.get((acct, app, d), 0)):
                    out.append((app, "%s/big%d" % (app, x % 50), "X%04d" % x))
            self._cache[k] = out
        return self._cache[k]

    def answer(self, acct, spec):
        rs = spec["reportSpec"]
        s, e = (date(v["year"], v["month"], v["day"]) for v in (rs["dateRange"]["startDate"], rs["dateRange"]["endDate"]))
        apps = None
        for f in rs.get("dimensionFilters", []) or []:
            if f.get("dimension") == "APP":
                apps = set(f["matchesAny"]["values"])
        self.calls.append((acct, s, e, tuple(rs["dimensions"]), tuple(sorted(apps)) if apps else None))
        if (acct, s, e) in self.fail:
            self.fail.discard((acct, s, e))
            raise RuntimeError("synthetic 503")
        days = [s + timedelta(days=i) for i in range((e - s).days + 1)]
        if rs["dimensions"] == ["APP"]:                                   # _app_ids_for: the apps with data that day
            seen = sorted({app for app, _u, _c in self.rows(acct, s)})
            return [{"app_id": a, "report_date": s} for a in seen], len(seen)
        found = []
        for d in days:
            for app, unit, c in self.rows(acct, d):
                if apps is None or app in apps:
                    found.append((_h(unit, c, d, s, e, apps and sorted(apps)), d, app, unit, c))
        found.sort()
        cap = int(rs["maxReportRows"])
        out = [{"report_date": d, "app_id": app, "app_name": app.upper(), "ad_unit_id": unit, "unit_name": unit[-4:],
                "country": c, "ad_requests": k % 997 + 5, "matched_requests": k % 991 + 3, "impressions": k % 977 + 1,
                "clicks": k % 13, "estimated_earnings_micros": k % 99991}
               for k, d, app, unit, c in found[:cap]]
        return out, min(len(found), cap)                  # AdMob caps matchingRowCount at maxReportRows


class FakeClient(AdMobClient):
    MAX_ROWS = CAP

    def __init__(self, world, acct):
        super().__init__(acct, "cid", "csec", "rtok")
        self.world = world

    def _run_report(self, method, spec):
        return self.world.answer(self.account_id, spec)

    def network_report(self, start, end, dim_filters=None):
        return iter(())

    def mediation_report(self, start, end, dim_filters=None):
        return iter(())

    def mediation_unit_report(self, start, end, dim_filters=None):
        return iter(())

    def country_report(self, start, end):
        return iter(())

    def placement_country_report(self, start, end):              # the unit → account map the plan reads
        apps, units, _ = self.world.accounts[self.account_id]
        for a in range(apps):
            app = "%s~app%d" % (self.account_id, a)
            for u in range(units):
                yield {"account_id": self.account_id, "app_id": app, "ad_unit_id": "%s/u%d" % (app, u),
                       "country": "All", "currency_code": "USD", "impressions": 1}


ACCOUNTS = {"pub-a": (3, 10, 50),      # ≈600 rows a day: 30-day pieces split four levels deep
            "pub-b": (2, 5, 50),       # ≈200 a day
            "pub-c": (1, 3, 50),       # ≈60 a day: one split
            "pub-d": (1, 1, 5)}        # ≈2 a day: never split


def _run(world, repo, today, monkeypatch, **env):
    for k in ("AC_SKIP_DROPPED", "AC_PRESPLIT", "AC_ACCOUNT_WORKERS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(fetcher, "make_client", lambda a, *x, **k: FakeClient(world, a["account_id"]))
    world.calls = []
    totals = fetcher.run_once([{"account_id": a} for a in world.accounts], repo, today=today, mode="live",
                              rolling_days=35, adunit_country_days=45, client_id="x", client_secret="y")
    return totals, list(world.calls)


OLD = {"AC_SKIP_DROPPED": "false", "AC_PRESPLIT": "false"}


def _warm(world, base, today, monkeypatch):
    """The stored state runs before `today` leave (all made the old way): the last run whose window started on the 1st
    of the month the window of `today` starts in (it stored that month's full rollup, which A' reads), then the run
    of the day before."""
    cover = (today - timedelta(days=45)).replace(day=1) + timedelta(days=45)
    if cover < today - timedelta(days=1):
        _run(world, base, cover, monkeypatch, **OLD)
    _run(world, base, today - timedelta(days=1), monkeypatch, **OLD)


def _replay(today, monkeypatch, world=None, new_env=None, warm=True):
    """(old run, new run) from the same starting repo: the stored state the runs before `today` left."""
    world = world or World(ACCOUNTS)
    base = InMemoryRepo()
    if warm:
        _warm(world, base, today, monkeypatch)
    a, b = copy.deepcopy(base), copy.deepcopy(base)
    ta, ca = _run(world, a, today, monkeypatch, **OLD)
    tb, cb = _run(world, b, today, monkeypatch, **(new_env or {}))
    return (a, ta, ca), (b, tb, cb)


def _same_output(old, new):
    (a, ta, _), (b, tb, _) = old, new
    assert json.dumps(a.acm) == json.dumps(b.acm)                 # same monthly rollup, same order
    assert json.dumps(a.acd, default=str) == json.dumps(b.acd, default=str)   # same daily file, same order
    assert ta["truncations"] == tb["truncations"]
    assert ta["acm"] == tb["acm"] and ta["acd"] == tb["acd"]


def _subset(new_calls, old_calls):
    return not (collections.Counter(new_calls) - collections.Counter(old_calls))


DAYS = [date(2026, 10, 1), date(2026, 10, 5), date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17),
        date(2026, 10, 21), date(2026, 10, 31), date(2026, 2, 28), date(2028, 2, 29)]


@pytest.mark.parametrize("today", DAYS, ids=str)
def test_kept_rows_order_and_truncations_identical_and_calls_a_subset(today, monkeypatch):
    old, new = _replay(today, monkeypatch)
    _same_output(old, new)
    assert _subset(new[2], old[2])
    assert len(new[2]) < len(old[2])                             # and fewer calls on every one of these days


def test_both_parts_are_needed_for_the_saving_and_each_alone_is_exact(monkeypatch):
    today = date(2026, 10, 21)
    old, both = _replay(today, monkeypatch)
    for env in ({"AC_PRESPLIT": "false"}, {"AC_SKIP_DROPPED": "false"}):
        _o, alone = _replay(today, monkeypatch, new_env=env)
        _same_output(old, alone)
        assert _subset(alone[2], old[2]) and len(both[2]) < len(alone[2]) < len(old[2])


def test_a_skipped_piece_holds_only_rows_the_rollup_drops(monkeypatch):
    """What A' leaves out is exactly the old run's calls that END before the first kept day."""
    today = date(2026, 10, 21)
    old, new = _replay(today, monkeypatch, new_env={"AC_PRESPLIT": "false"})
    kf = first_kept_day(today - timedelta(days=45), today)
    gone = collections.Counter(old[2]) - collections.Counter(new[2])
    assert gone and all(e < kf for _a, _s, e, _d, _f in gone)


def _kept_days(ws, today):
    """The days whose rows RollupAccumulator(today).finish(ws) keeps, by feeding it one row a day from ws to today."""
    acc = RollupAccumulator(today)
    d = ws
    while d <= today:
        acc.add({"report_date": d.isoformat(), "account_id": "a", "app_id": "p", "ad_unit_id": "u", "country": "C",
                 "ad_requests": 2, "matched_requests": 2, "impressions": 1, "clicks": 0,
                 "estimated_earnings_micros": 1})
        d += timedelta(days=1)
    rollups, daily = acc.finish(ws)
    months = {r["month"] for r in rollups}
    out, d = [], ws
    while d <= today:
        if d.isoformat()[:7] in months or d.isoformat() in {r["report_date"] for r in daily}:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_first_kept_day_agrees_with_the_rollup_for_every_window_start():
    """Every day from first_kept_day(ws, today) on is kept, every day before it dropped — for window starts on and
    after the 1st of their month, months and years before today, and INSIDE today's own month (whose rows are always
    kept: the day the window starts in today's month is never pushed to the next month)."""
    for today in (date(2026, 10, 21), date(2026, 10, 1), date(2026, 10, 31), date(2028, 2, 29), date(2027, 1, 2)):
        d = date(today.year - 1, today.month, 1)
        while d <= today:
            for ws in {d, d + timedelta(days=1), d + timedelta(days=14), d + timedelta(days=27)}:
                if ws > today:
                    continue
                kf = first_kept_day(ws, today)
                kept = _kept_days(ws, today)
                assert kf.day == 1 and kf <= today and kept, (ws, today)
                assert kept[0] == max(ws, kf) and kept == [ws + timedelta(days=i) for i in range((kept[0] - ws).days,
                                                                                            (today - ws).days + 1)]
            d = (d + timedelta(days=32)).replace(day=1)
    assert first_kept_day(None, date(2026, 10, 21)) is None
    assert RollupAccumulator(date(2030, 1, 1)).finish(None)[0] == []


def test_a_window_inside_the_current_month_keeps_its_rows(monkeypatch):
    """A window that starts inside today's month (adunit_country_days short): its rows are the current month's daily
    rows, never skipped — the same daily file as the old pull."""
    world = World(ACCOUNTS)
    today = date(2026, 10, 21)
    outs = []
    for env in (OLD, {}):
        base = InMemoryRepo()
        for k in ("AC_SKIP_DROPPED", "AC_PRESPLIT", "AC_ACCOUNT_WORKERS"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setattr(fetcher, "make_client", lambda a, *x, **k: FakeClient(world, a["account_id"]))
        for day, days in ((today - timedelta(days=1), 45), (today, 10)):
            for k, v in env.items():
                monkeypatch.setenv(k, v)
            t = fetcher.run_once([{"account_id": a} for a in world.accounts], base, today=day, mode="live",
                                 rolling_days=10, adunit_country_days=days, client_id="x", client_secret="y")
        outs.append((base, t))
    assert outs[0][1]["acd"] > 0 and outs[0][1]["acd"] == outs[1][1]["acd"]
    assert json.dumps(outs[0][0].acd, default=str) == json.dumps(outs[1][0].acd, default=str)
    assert json.dumps(outs[0][0].acm) == json.dumps(outs[1][0].acm)


def test_truncation_in_the_kept_days_is_recorded_the_same(monkeypatch):
    big = {("pub-c", "pub-c~app0", date(2026, 10, 10)): CAP + 100}    # one app-day over the cap, inside the month
    world = World(ACCOUNTS, big=big)
    old, new = _replay(date(2026, 10, 21), monkeypatch, world=world)
    assert [t["date"] for t in old[1]["truncations"]] == ["2026-10-10"]      # (one app: no per-app split possible)
    _same_output(old, new)          # (that one huge day also skews the account's prediction: extra calls, same rows)


def test_a_big_account_keeps_its_old_pieces_so_no_truncation_record_can_go(monkeypatch):
    """An account with an over-cap app-day in the days the rollup drops: its stored rollup of that month holds at least
    the cap's entries for that app, so A' leaves its pieces alone — the record stays the same."""
    big = {("pub-c", "pub-c~app0", date(2026, 9, 10)): CAP + 100,     # dropped by the rollup (window starts 6 Sep)
           ("pub-c", "pub-c~app0", date(2026, 10, 12)): int(CAP * 0.9)}   # its current month: a day near the cap
    world = World(ACCOUNTS, big=big)
    old, new = _replay(date(2026, 10, 21), monkeypatch, world=world)
    assert [t["date"] for t in old[1]["truncations"]] == ["2026-09-10"]
    _same_output(old, new)


def test_a_truncation_only_in_dropped_days_of_a_small_account_is_recorded_the_same(monkeypatch):
    """An over-cap app-day that exists ONLY in days the rollup throws away, in an account whose other days are all far
    under the cap (the edge the stored current-month daily file could not see): the month's stored rollup shows it,
    so its record stays, with every kept row."""
    big = {("pub-d", "pub-d~app0", date(2026, 9, 10)): CAP + 100}
    world = World(ACCOUNTS, big=big)
    old, new = _replay(date(2026, 10, 21), monkeypatch, world=world)
    assert [t["date"] for t in old[1]["truncations"]] == ["2026-09-10"]
    _same_output(old, new)
    assert _subset(new[2], old[2]) and len(new[2]) < len(old[2])        # the other accounts still skip


def test_the_second_run_on_the_first_of_a_month(monkeypatch):
    """1 Nov, second run: the stored daily file holds only a part of 1 Nov, so it says nothing about the dropped days of
    17-30 Sep. A' reads September's stored rollup instead: the big account's over-cap app-day there keeps its
    record, the small accounts still skip."""
    big = {("pub-c", "pub-c~app0", date(2026, 9, 20)): CAP + 100,
           ("pub-c", "pub-c~app0", date(2026, 10, 12)): int(CAP * 0.9)}
    world = World(ACCOUNTS, big=big)
    today = date(2026, 11, 1)
    base = InMemoryRepo()
    _run(world, base, date(2026, 10, 16), monkeypatch, **OLD)           # the last run that stored September whole
    _run(world, base, today, monkeypatch, **OLD)                        # the first run of 1 Nov
    assert base.acd["dates"] == ["2026-11-01"]
    a, b = copy.deepcopy(base), copy.deepcopy(base)
    ta, ca = _run(world, a, today, monkeypatch, **OLD)
    tb, cb = _run(world, b, today, monkeypatch)
    assert [t["date"] for t in ta["truncations"]] == ["2026-09-20"]
    _same_output((a, ta, ca), (b, tb, cb))
    assert _subset(cb, ca) and any(c[0] == "pub-a" and c[2] < date(2026, 10, 1) for c in collections.Counter(ca) -
                                   collections.Counter(cb))
    assert not [c for c in collections.Counter(ca) - collections.Counter(cb)
                if c[0] == "pub-c" and c[2] < date(2026, 10, 1)]              # pub-c: none of its old pieces skipped


def test_the_skip_needs_the_month_stored_and_every_big_app_placed(monkeypatch):
    """No stored rollup of the month → no account skips. A big app of the month whose account is unknown → no account
    skips (it could be anyone's). An account with no entry in the month → it does not skip."""
    today = date(2026, 10, 21)
    world = World(ACCOUNTS)
    base = InMemoryRepo()
    _run(world, base, today - timedelta(days=1), monkeypatch, **OLD)      # September never stored whole
    assert fetcher._ac_old_month_max(base, "2026-09") == {}
    _warm(world, base, today, monkeypatch)
    got = fetcher._ac_old_month_max(base, "2026-09")
    assert set(got) == set(ACCOUNTS) | {None} and got[None] == 0 and 0 < got["pub-d"] < got["pub-c"] < got["pub-a"]
    base.acm["units"]["stray/u0"] = ["stray~app", "u0", "STRAY", "USD"]  # an app no placement row names
    base.acm["data"]["stray/u0"] = {"C%02d" % i: {"2026-09": [1] * 18} for i in range(10)}
    assert fetcher._ac_old_month_max(base, "2026-09")[None] == 10        # small: every account may still skip
    base.acm["data"]["stray/u0"] = {"X%04d" % i: {"2026-09": [1] * 18} for i in range(CAP)}
    assert fetcher._ac_old_month_max(base, "2026-09")[None] == CAP
    old, new = (copy.deepcopy(base), None), (copy.deepcopy(base), None)
    ta, ca = _run(world, old[0], today, monkeypatch, **OLD)
    tb, cb = _run(world, new[0], today, monkeypatch, AC_PRESPLIT="false")
    _same_output((old[0], ta, ca), (new[0], tb, cb))
    assert collections.Counter(ca) == collections.Counter(cb)           # a big unplaced app: nobody skips
    for acct in ACCOUNTS:
        c = FakeClient(world, acct)
        plan = admob_client.AcPlan(keep_from=date(2026, 10, 1), old_max=None)
        list(c.adunit_country_report(date(2026, 9, 6), date(2026, 10, 5), plan=plan))
        assert plan.skipped == 0                                         # no entry in the month: no skip


@pytest.mark.parametrize("factor", [25.0, 3.0, 0.02])
def test_a_wrong_prediction_costs_calls_never_a_row(monkeypatch, factor):
    real = fetcher._ac_day_counts
    monkeypatch.setattr(fetcher, "_ac_day_counts", lambda repo: {a: r * factor for a, r in real(repo).items()})
    for today in (date(2026, 10, 21), date(2026, 10, 5), date(2028, 2, 29)):
        old, new = _replay(today, monkeypatch)
        _same_output(old, new)


def test_no_stored_daily_file_runs_as_before(monkeypatch):
    old, new = _replay(date(2026, 10, 21), monkeypatch, warm=False)     # first run: no hints at all
    _same_output(old, new)
    assert collections.Counter(new[2]) == collections.Counter(old[2])


def test_a_full_history_pull_never_uses_the_plan(monkeypatch):
    world = World(ACCOUNTS)
    seen = []
    real = AdMobClient.adunit_country_report

    def spy(self, start, end, dim_filters=None, plan=None):
        seen.append(plan)
        return real(self, start, end, dim_filters=dim_filters, plan=plan)
    monkeypatch.setattr(FakeClient, "adunit_country_report", spy)
    monkeypatch.setattr(FakeClient, "data_start", lambda self, end, max_lookback=0, dim_filters=None: end - timedelta(70))
    monkeypatch.setattr(fetcher, "make_client", lambda a, *x, **k: FakeClient(world, a["account_id"]))
    fetcher.run_once([{"account_id": "pub-c"}], InMemoryRepo(), today=date(2026, 10, 21), mode="live",
                     rolling_days=35, adunit_country_days=1300, ac_full_history=True)
    assert seen and all(p is None for p in seen)


@pytest.mark.parametrize("today", [date(2026, 10, 21), date(2026, 10, 1)], ids=str)
def test_accounts_side_by_side_fold_in_the_same_order(today, monkeypatch):
    world = World(ACCOUNTS, big={("pub-b", "pub-b~app1", today): CAP + 20})
    seq, par = _replay(today, monkeypatch, world=world, new_env={"AC_ACCOUNT_WORKERS": "3"})
    _same_output(seq, par)                                        # vs the plain splitter one after another
    _o, plan_seq = _replay(today, monkeypatch, world=world)       # vs A' + B'' one after another
    _same_output(plan_seq, par)
    assert collections.Counter(plan_seq[2]) == collections.Counter(par[2])     # the very same calls


def test_accounts_side_by_side_with_a_failing_chunk(monkeypatch):
    today = date(2026, 10, 21)
    outs = []
    # one 503 on a whole chunk (a small account: its chunk is one call) and one in the middle of a big account's chunk
    # (after rows of that chunk were already folded): both ways keep exactly the rows folded before each error
    fails = {("pub-c", date(2026, 10, 6), date(2026, 10, 21)), ("pub-a", date(2026, 10, 10), date(2026, 10, 11))}
    for workers in ("1", "3"):
        world = World(ACCOUNTS)
        base = InMemoryRepo()
        _run(world, base, today - timedelta(days=1), monkeypatch, **OLD)
        world.fail = set(fails)
        r = copy.deepcopy(base)
        t, c = _run(world, r, today, monkeypatch, AC_ACCOUNT_WORKERS=workers)
        assert not world.fail                                      # both errors happened
        outs.append((r, t, c))
    _same_output(outs[0], outs[1])
    full = InMemoryRepo()
    _run(World(ACCOUNTS), full, today, monkeypatch)
    assert json.dumps(full.acd, default=str) != json.dumps(outs[0][0].acd, default=str)   # (rows were really lost)


def test_the_mock_client_accepts_the_plan_and_ignores_it(monkeypatch):
    for k in ("AC_SKIP_DROPPED", "AC_PRESPLIT", "AC_ACCOUNT_WORKERS"):
        monkeypatch.delenv(k, raising=False)
    out = []
    for env in (OLD, {}):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        repo = InMemoryRepo()
        fetcher.run_once([{"account_id": "pub-mock"}], repo, today=date(2026, 10, 21), mode="mock",
                         rolling_days=10, adunit_country_days=45)
        out.append((json.dumps(repo.acm), json.dumps(repo.acd, default=str)))
        for k in env:
            monkeypatch.delenv(k)
    assert out[0] == out[1]


def test_planned_path_only_for_account_wide_calls():
    c = FakeClient(World(ACCOUNTS), "pub-c")
    plan = admob_client.AcPlan(keep_from=date(2026, 10, 1), rows_per_day=10 ** 6, old_max=1)
    flt = [admob_client._app_filter("pub-c~app0")]
    rows = list(c.adunit_country_report(date(2026, 9, 6), date(2026, 9, 7), dim_filters=flt, plan=plan))
    assert rows and plan.calls == 0 and plan.skipped == 0         # an app-scoped pull never takes the plan


def test_an_api_error_stops_a_chunk_at_a_call_boundary_like_before():
    """With an AdMob error on any one call, the rows a chunk yielded before the error are the first rows of what it
    yields without errors (in the same order) — as with the old splitter: an error only cuts a chunk short."""
    world = World(ACCOUNTS)
    s, e = date(2026, 9, 6), date(2026, 10, 5)
    hint = {"pub-a": (600.0, 640), "pub-b": (200.0, 230)}

    def plan(acct):
        return admob_client.AcPlan(keep_from=date(2026, 10, 1), rows_per_day=hint[acct][0], old_max=hint[acct][1])
    for acct in hint:
        full = list(FakeClient(world, acct).adunit_country_report(s, e))                 # old splitter, no error
        kept = [r for r in full if r["report_date"] >= date(2026, 10, 1)]
        world.calls = []
        planned = list(FakeClient(world, acct).adunit_country_report(s, e, plan=plan(acct)))
        assert [r for r in planned if r["report_date"] >= date(2026, 10, 1)] == kept
        for k, call in enumerate(list(world.calls)):
            world.fail = {(call[0], call[1], call[2])}
            got = []
            with pytest.raises(RuntimeError):
                for r in FakeClient(world, acct).adunit_country_report(s, e, plan=plan(acct)):
                    got.append(r)
            got_kept = [r for r in got if r["report_date"] >= date(2026, 10, 1)]
            assert got_kept == kept[:len(got_kept)], (acct, k)


def _pull(world, acct, s, e, plan, fail):
    """One chunk through the client with `fail` answered by one AdMob error: (rows before the error, truncations)."""
    world.fail = set(fail)
    world.calls = []
    c = FakeClient(world, acct)
    got = []
    try:
        for r in c.adunit_country_report(s, e, plan=plan):
            got.append(r)
    except RuntimeError:
        pass
    return got, c.truncations


@pytest.mark.parametrize("chunk", [(date(2026, 10, 1), date(2026, 10, 21)), (date(2026, 9, 21), date(2026, 10, 20)),
                                   (date(2026, 9, 6), date(2026, 10, 5))], ids=str)
def test_one_admob_error_on_any_call_keeps_exactly_the_old_rows(chunk):
    """The plain splitter folds the rows it got before an AdMob error and drops the rest of the chunk. With A' + B'',
    one error (once, as a 503 is) on ANY call the new pull makes must leave exactly the same kept rows as the plain
    splitter with that error, in the same order, with the same truncation records — for predictions far under, near
    and far over the real row counts (a too-high one asks halves the plain splitter never asks: an error there gives
    the plain splitter's rows without an error). An error on a call only the plain splitter makes (a skipped piece,
    an over-cap call B'' leaves out) cannot cost the new pull a row."""
    s, e = chunk
    kf = date(2026, 10, 1)
    big = {("pub-b", "pub-b~app1", date(2026, 10, 3)): CAP + 30}           # an over-cap app-day too
    world = World(ACCOUNTS, big=big)
    real = {"pub-a": 600.0, "pub-b": 200.0, "pub-c": 60.0}

    def kept(rows):
        return [r for r in rows if r["report_date"] >= kf]
    both = only_old = 0
    for acct, rpd in real.items():
        for factor in (0.7, 1.5, 3.0):
            def mk():
                return admob_client.AcPlan(keep_from=kf, rows_per_day=rpd * factor, old_max=int(rpd * 0.5))
            full, full_tr = _pull(world, acct, s, e, None, ())
            old_calls = {c[:3] for c in world.calls}
            _pull(world, acct, s, e, mk(), ())
            new_calls = {c[:3] for c in world.calls}
            for key in sorted(old_calls | new_calls):
                o_rows, o_tr = _pull(world, acct, s, e, None, {key})
                n_rows, n_tr = _pull(world, acct, s, e, mk(), {key})
                if key in new_calls:
                    assert kept(n_rows) == kept(o_rows) and n_tr == o_tr, (acct, factor, key)
                    both += key in old_calls
                else:
                    assert kept(n_rows) == kept(full) and n_tr == full_tr, (acct, factor, key)
                    assert kept(o_rows) == kept(full)[:len(kept(o_rows))]
                    only_old += 1
    assert both >= 40 and only_old >= 60                      # (calls both make / only the plain splitter makes)


def test_an_admob_error_mid_chunk_gives_the_same_stored_files(monkeypatch):
    """Through run_once: one 503 in the middle of the big account's current-month chunk (rows of that chunk already
    folded) and one on a small account's whole chunk: the old pull and A' + B'' store the same files."""
    today = date(2026, 10, 21)
    outs = []
    for env in (OLD, {}):
        world = World(ACCOUNTS)
        base = InMemoryRepo()
        _warm(world, base, today, monkeypatch)
        world.fail = {("pub-a", date(2026, 10, 11), date(2026, 10, 13)), ("pub-c", date(2026, 10, 6), date(2026, 10, 21)),
                      ("pub-b", date(2026, 10, 14), date(2026, 10, 17))}
        t, c = _run(world, base, today, monkeypatch, **env)
        outs.append((base, t, c, set(world.fail)))
    assert outs[0][3] == outs[1][3] and len(outs[0][3]) < 3                   # the same errors happened both ways
    _same_output(outs[0][:3], outs[1][:3])
