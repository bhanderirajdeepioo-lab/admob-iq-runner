"""Daily multi-account pull: network + mediation, derive metrics, upsert facts,
and append earnings snapshots (deduction tracking).

`run_once` takes an injected client factory + repo so it is fully testable with
the mock client and an in-memory repo (no creds, no DB)."""

import os
import queue
import sys
import threading
from datetime import date, timedelta
from typing import Dict, List

from .. import stage_clock as _sc
from ..engine import metrics
from .admob_client import MockAdMobClient, AdMobClient, AcPlan


def build_network_row(raw: Dict) -> Dict:
    row = dict(raw)
    row["match_rate"] = metrics.match_rate(raw["ad_requests"], raw["matched_requests"])
    row["show_rate"] = metrics.show_rate(raw["matched_requests"], raw["impressions"])
    row["impression_ctr"] = metrics.ctr(raw["impressions"], raw["clicks"])
    # eCPM/RPM in MICROS: ecpm() returns currency, so scale by 1e6 (not 1e3).
    row["impression_rpm_micros"] = raw.get("impression_rpm_micros") or \
        int(metrics.ecpm(raw["estimated_earnings_micros"], raw["impressions"]) * metrics.MICROS)
    row.setdefault("currency_code", "USD")
    return row


def build_mediation_row(raw: Dict) -> Dict:
    row = dict(raw)
    row["match_rate"] = metrics.match_rate(raw["ad_requests"], raw["matched_requests"])
    row["impression_ctr"] = metrics.ctr(raw["impressions"], raw["clicks"])
    row.setdefault("observed_ecpm_micros", 0)
    return row


def build_mediation_unit_row(raw: Dict) -> Dict:
    """Ad-unit totals for one day from the mediation report WITHOUT AD_SOURCE — the ad unit's own
    requests / matched requests (the source of truth for its match and show rate). Lean on purpose:
    only the keys the readers need, since the table spans the whole history."""
    return {"report_date": raw["report_date"], "account_id": raw.get("account_id"),
            "app_id": raw.get("app_id"), "app_name": raw.get("app_name"),
            "ad_unit_id": raw.get("ad_unit_id"), "unit_name": raw.get("unit_name"),
            "format": raw.get("format"), "platform": raw.get("platform"),
            "ad_requests": raw.get("ad_requests", 0) or 0,
            "matched_requests": raw.get("matched_requests", 0) or 0,
            "impressions": raw.get("impressions", 0) or 0, "clicks": raw.get("clicks", 0) or 0,
            "estimated_earnings_micros": raw.get("estimated_earnings_micros", 0) or 0,
            "currency_code": raw.get("currency_code", "USD")}


def pull_mediation_unit(client, repo, start: date, end: date, dim_filters=None) -> int:
    """Pull the ad-unit mediation report (no AD_SOURCE) for [start, end] into the repo. Returns the
    row count. A client or repo without it (an older test double) is a no-op, never an error."""
    fetch = getattr(client, "mediation_unit_report", None)
    put = getattr(repo, "upsert_mediation_unit", None)
    if fetch is None or put is None:
        return 0
    n = 0
    rows = fetch(start, end, dim_filters=dim_filters) if dim_filters else fetch(start, end)
    for raw in rows:
        put(build_mediation_unit_row(raw))
        n += 1
    return n


def build_pc_row(raw: Dict) -> Dict:
    return {"account_id": raw.get("account_id"), "app_id": raw.get("app_id"),
            "app_name": raw.get("app_name"), "ad_unit_id": raw.get("ad_unit_id"),
            "unit_name": raw.get("unit_name"), "country": raw.get("country") or "All",
            "ad_requests": raw.get("ad_requests", 0),
            "matched_requests": raw.get("matched_requests", 0),
            "impressions": raw.get("impressions", 0), "clicks": raw.get("clicks", 0),
            "estimated_earnings_micros": raw.get("estimated_earnings_micros", 0),
            "currency_code": raw.get("currency_code", "USD")}


def build_ac_row(raw: Dict) -> Dict:
    """Raw (date, app, ad_unit, country) daily row for the baseline rollup — counts only
    (metrics are derived per-day inside the rollup, so nothing to precompute here)."""
    return {"report_date": raw["report_date"], "account_id": raw.get("account_id"),
            "app_id": raw.get("app_id"), "app_name": raw.get("app_name"),
            "ad_unit_id": raw.get("ad_unit_id"), "unit_name": raw.get("unit_name"),
            "country": raw.get("country") or "All",
            "ad_requests": raw.get("ad_requests", 0),
            "matched_requests": raw.get("matched_requests", 0),
            "impressions": raw.get("impressions", 0), "clicks": raw.get("clicks", 0),
            "estimated_earnings_micros": raw.get("estimated_earnings_micros", 0),
            "currency_code": raw.get("currency_code", "USD")}


def build_country_row(raw: Dict) -> Dict:
    return {"report_date": raw["report_date"], "account_id": raw.get("account_id"),
            "app_id": raw.get("app_id"), "app_name": raw.get("app_name"),
            "country": raw.get("country") or "All",
            "ad_requests": raw.get("ad_requests", 0),
            "matched_requests": raw.get("matched_requests", 0),
            "impressions": raw.get("impressions", 0), "clicks": raw.get("clicks", 0),
            "estimated_earnings_micros": raw.get("estimated_earnings_micros", 0),
            "currency_code": raw.get("currency_code", "USD")}


def build_snapshot(raw: Dict, snapshot_day: date) -> Dict:
    return {"report_date": raw["report_date"], "snapshot_date": snapshot_day,
            "account_id": raw["account_id"], "app_id": raw["app_id"],
            "ad_unit_id": raw["ad_unit_id"], "country": raw.get("country", "All"),
            "format": raw["format"],
            "estimated_earnings_micros": raw["estimated_earnings_micros"],
            "impressions": raw["impressions"], "clicks": raw["clicks"]}


def date_window(today: date, rolling_days: int):
    """Re-pull the last `rolling_days` INCLUDING today. Today is a live intraday
    estimate (AdMob refines it through the day); re-fetching it hourly is exactly
    what makes the dashboard feel 'live' — you watch today's earnings climb."""
    return today - timedelta(days=rolling_days), today


def make_client(account: Dict, mode="mock", client_id=None, client_secret=None,
                currency="USD"):
    if mode == "mock":
        return MockAdMobClient(account["account_id"])
    return AdMobClient(account["account_id"], client_id, client_secret,
                       account["refresh_token"],
                       tz=account.get("reporting_tz"),   # None => account's own timezone
                       currency=account.get("currency", currency))


def _switch(name, default=True):
    """A speed switch (repo variable, refresh.yml): false/0/no/off → False, true/1/yes/on → True, else `default`."""
    v = (os.getenv(name) or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return default


def _int_env(name, default):
    try:
        return int(os.getenv(name) or default)
    except ValueError:
        return default


def _ac_accounts(repo):
    """(ad unit → account, app → account) from the stored placement × country rows (each row names its account)."""
    u2a, a2a = {}, {}
    for r in (repo.fetch_placement_country() or []):
        acct = r.get("account_id")
        if acct:
            if r.get("ad_unit_id"):
                u2a[r["ad_unit_id"]] = acct
            if r.get("app_id"):
                a2a[r["app_id"]] = acct
    return u2a, a2a


def _ac_day_counts(repo):
    """{account_id: rows a day} of the ad-unit × country report, from the STORED current-month daily file (what the
    last run kept). B'' speed hint only, never data: a wrong hint costs calls, never a row; an account missing here
    just gets no hint (its pull runs as before). Any odd shape → {}."""
    try:
        acd = repo.fetch_adunit_country_daily() or {}
        dates = acd.get("dates") or []
        if not dates:
            return {}
        u2a, a2a = _ac_accounts(repo)
        units, nd, per = acd.get("units") or {}, len(dates), {}
        for uid, by_country in (acd.get("data") or {}).items():
            acct = u2a.get(uid) or a2a.get((units.get(uid) or [None])[0])
            if acct is None:
                continue
            for lst in by_country.values():
                per[acct] = per.get(acct, 0) + sum(1 for arr in lst if 0 <= arr[0] < nd)
        return {a: n / nd for a, n in per.items()}
    except Exception:
        return {}


def _ac_old_month_max(repo, month):
    """A' guard: {account_id: the most (ad unit, country) entries one of its apps has in `month` of the STORED monthly
    rollup}, plus None: the same for the apps no account could be found for (0 when there are none). One report row is
    one (ad unit, country) of an app-day, so no app-day of that month has more rows than its app's entries there; a
    run that hit the cap on an app-day of the month left at least the cap's entries for that app (entries are only
    ever added to a stored month). An account missing here (the month is not stored, or it has no entry in it) gets
    no skip. Read only, never data; any odd shape → {} (no account skips anything)."""
    try:
        acm = repo.fetch_adunit_country_monthly() or {}
        units = acm.get("units") or {}
        per_app, app_units = {}, {}
        for uid, by_country in (acm.get("data") or {}).items():
            n = sum(1 for by_month in by_country.values() if month in by_month)
            if n:
                app = (units.get(uid) or [None])[0]
                per_app[app] = per_app.get(app, 0) + n
                app_units.setdefault(app, []).append(uid)
        if not per_app:
            return {}
        u2a, a2a = _ac_accounts(repo)
        out = {None: 0}
        for app, n in per_app.items():
            acct = a2a.get(app) if app is not None else None
            if acct is None and app is not None:
                acct = next((u2a[u] for u in app_units[app] if u in u2a), None)
            out[acct] = max(out.get(acct, 0), n)          # an app without an account counts for every account
        return out
    except Exception:
        return {}


class _FeedStopped(Exception):
    pass


class _AcFeed:
    """C — AC_ACCOUNT_WORKERS ≥ 2 (default 1: off): the accounts' ad-unit × country pulls side by side, each on its own
    thread with its OWN client (a client is never shared between threads), while the build's thread folds the rows
    into the rollup strictly in account order, chunk order and row order — what one after another gives. An account
    hands its rows over in batches through a small bounded queue (bounded memory)."""
    BATCH = 20_000                    # rows per hand-over
    QUEUE = 4                         # hand-overs an account may fetch ahead of the fold

    def __init__(self, workers):
        from concurrent.futures import ThreadPoolExecutor
        self.ex = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ac-feed")
        self.stop = threading.Event()
        self.pending = []             # [(slot, queue)] in account order

    def submit(self, slot, job):
        q = queue.Queue(maxsize=self.QUEUE)

        def put(item):
            while not self.stop.is_set():
                try:
                    q.put(item, timeout=0.5)
                    return
                except queue.Full:
                    continue
            raise _FeedStopped()

        def run():
            truncs = []
            try:
                truncs = job(put)
            except _FeedStopped:
                return
            except Exception as e:     # never expected (chunk errors are handled in the job): the rows so far stay
                print(f"adunit-country pull stopped early: {type(e).__name__}: {e}", file=sys.stderr)
            try:
                put(("done", truncs or []))
            except _FeedStopped:
                pass
        self.pending.append((slot, q))
        self.ex.submit(run)

    def drain(self, fold, done, block):
        """Fold every batch already handed over (block=True: wait for all of them), oldest account first."""
        while self.pending:
            slot, q = self.pending[0]
            try:
                kind, val = q.get(block=block)
            except queue.Empty:
                return
            if kind == "rows":
                fold(val)
            else:
                done(slot, val)
                self.pending.pop(0)

    def close(self):
        self.stop.set()
        self.ex.shutdown(wait=False)


def _ac_job(acct, mode, client_id, client_secret, currency, *, today, ac_start, ac_end, ac_full_history,
            adunit_country_days, plan):
    """C: one account's ad-unit × country pull exactly as run_once makes it one account after another (the same
    chunks, the same per-chunk error handling), on its own client; returns that client's truncation records."""
    def job(put):
        client = make_client(acct, mode, client_id, client_secret, currency)
        if ac_full_history:
            try:
                ds = client.data_start(today, max_lookback=adunit_country_days or 2555)
            except Exception as e:
                print(f"data_start probe failed for {acct.get('account_id')}: {e}", file=sys.stderr)
                ds = None
            acs = ds or ac_start or (today - timedelta(days=2555))
        else:
            acs = ac_start
        cs = acs
        while cs <= ac_end:
            ce = min(cs + timedelta(days=29), ac_end)
            batch = []
            try:
                src = (client.adunit_country_report(cs, ce, plan=plan) if plan is not None
                       else client.adunit_country_report(cs, ce))
                for raw in src:
                    batch.append(raw)
                    if len(batch) >= _AcFeed.BATCH:
                        put(("rows", batch))
                        batch = []
            except _FeedStopped:
                raise
            except Exception as e:
                if batch:                 # the rows before the error were folded one after another too
                    put(("rows", batch))
                    batch = []
                print(f"adunit-country chunk {cs}..{ce} skipped for {acct.get('account_id')}: {e}", file=sys.stderr)
            if batch:
                put(("rows", batch))
            cs = ce + timedelta(days=1)
        if plan is not None:
            _plan_log(plan)
        return list(getattr(client, "truncations", []))
    return job


def _plan_log(plan):
    if not (plan.calls or plan.skipped):
        return                                          # (a client that does not use the plan, e.g. the mock)
    print(f"adunit-country plan: {plan.calls} call(s), {plan.skipped} piece(s) before the kept days skipped, "
          f"{plan.presplit} split without the over-cap call, {plan.unconfirmed} asked whole, "
          f"{plan.failed} error(s) while splitting first", file=sys.stderr)


def run_once(accounts: List[Dict], repo, *, today: date, mode="mock",
             rolling_days=7, country_days=None, adunit_country_days=None,
             ac_full_history=False, full_history=False, client_id=None, client_secret=None, currency="USD") -> Dict:
    start, end = date_window(today, rolling_days)
    # The country report can be backfilled DEEPER than network/mediation (its history often
    # lags), so it gets its own window.
    c_start, c_end = date_window(today, country_days if country_days else rolling_days)
    # Ad-unit×country baseline: rolled up as it streams. On a full-history backfill we probe
    # each account's real start (below); otherwise a fixed recent window (adunit_country_days).
    from ..engine.rollup import RollupAccumulator
    ac_end = today
    ac_start = today - timedelta(days=adunit_country_days) if adunit_country_days else None
    ac_acc = RollupAccumulator(today) if adunit_country_days else None
    totals = {"network": 0, "mediation": 0, "snapshots": 0, "country": 0}
    truncations = []          # any slice the safe-fetch layer could NOT make complete (should stay empty)
    # ⏱ Speed only: the rows the rollup keeps and their order stay exactly as before, and so do the truncation records
    # (see AcPlan; tests/test_ac_plan.py replays both ways, also with AdMob errors). On the ongoing window only (a
    # full-history pull keeps every row):
    #   AC_SKIP_DROPPED=false  also ask for split pieces that end before the first kept day (A' off: as before)
    #   AC_PRESPLIT=false      always make the call that comes back over the cap before splitting (B'' off: as before)
    #   AC_ACCOUNT_WORKERS=N   N ≥ 2: the accounts' pulls side by side, folded in account order (C; default 1: off)
    ac_hint, keep_from, old_max = None, None, {}
    if ac_acc is not None and not ac_full_history:
        from ..engine.rollup import first_kept_day
        skip_old, presplit = _switch("AC_SKIP_DROPPED"), _switch("AC_PRESPLIT")
        if skip_old or presplit:
            ac_hint = _ac_day_counts(repo) if presplit else {}
        if skip_old:
            keep_from = first_kept_day(ac_start, today)
            if keep_from > ac_start:              # the days dropped: ac_start .. keep_from - 1, all in ac_start's month
                old_max = _ac_old_month_max(repo, ac_start.isoformat()[:7])

    def ac_plan(acct):
        if ac_hint is None:
            return None
        aid = acct.get("account_id")
        own = old_max.get(aid)
        return AcPlan(keep_from=keep_from, rows_per_day=ac_hint.get(aid),
                      old_max=None if own is None else max(own, old_max.get(None, 0)))

    def ac_fold(rows):
        for raw in rows:
            ac_acc.add(build_ac_row(raw))
        totals["adunit_country"] = totals.get("adunit_country", 0) + len(rows)

    def ac_done(slot, truncs):
        slot.append(truncs)
    workers = _int_env("AC_ACCOUNT_WORKERS", 1)
    feed = _AcFeed(workers) if ac_acc is not None and workers >= 2 else None
    slots = []                # C: per account, its truncation records (main client, then its ad-unit × country client)
    try:
        for acct in accounts:
            client = make_client(acct, mode, client_id, client_secret, currency)
            # Full-history backfill: probe THIS account's real data start so network + country cover the
            # whole history automatically — no fixed day-count. Mirrors the ad-unit×country backfill below.
            n_start, cc_start = start, c_start
            if full_history:
                try:
                    _ds = client.data_start(today, max_lookback=adunit_country_days or 2555)
                except Exception as _e:
                    import sys; print(f"data_start (network) probe failed for {acct.get('account_id')}: {_e}", file=sys.stderr); _ds = None
                if _ds:
                    n_start = cc_start = _ds
            # Per-account isolation: a bad/expired token or auth error on ONE account (which surfaces
            # on its first API call) must NOT crash the whole run and freeze every other account's data.
            # Log it and move on — that account simply gets no fresh data this run; its old data stays.
            try:
                with _sc.stage("admob_network"):  # ⏱ measure only (stage_clock): each report summed over the accounts
                    for raw in client.network_report(n_start, end):
                        repo.upsert_network(build_network_row(raw))
                        repo.append_snapshot(build_snapshot(raw, today))
                        totals["network"] += 1
                        totals["snapshots"] += 1
                with _sc.stage("admob_mediation"):
                    for raw in client.mediation_report(start, end):
                        repo.upsert_mediation(build_mediation_row(raw))
                        totals["mediation"] += 1
            except Exception as e:
                import sys
                print(f"account {acct.get('account_id')} skipped this run (auth/report error): {e}", file=sys.stderr)
                totals.setdefault("account_errors", []).append({"account_id": acct.get("account_id"), "error": str(e)[:200]})
                continue
            # Ad-unit totals (mediation, NO AD_SOURCE) over the same window as the network report — the
            # ad unit's own requests / matched requests. Its own try: a failure here costs only these rows
            # (the readers then fall back to the network numbers for the days it has no row), never the
            # account's revenue pull. The older history is filled once by build_static's marked backfill.
            try:
                with _sc.stage("admob_mediation_unit"):
                    totals["mediation_unit"] = totals.get("mediation_unit", 0) + pull_mediation_unit(
                        client, repo, n_start, end)
            except Exception as e:
                import sys
                print(f"mediation ad-unit report skipped for {acct.get('account_id')}: {type(e).__name__}: {e}",
                      file=sys.stderr)
                totals.setdefault("mediation_unit_errors", []).append(acct.get("account_id"))
            # Country breakdown is a SEPARATE, additive report. Pull it in <=90-day chunks so a
            # long history backfill never rides on one huge request, and a transient failure on
            # one chunk doesn't lose the rest (each chunk is best-effort). Never let a hiccup
            # here break the core revenue pull.
            cs = cc_start
            while cs <= c_end:
                ce = min(cs + timedelta(days=59), c_end)     # 60-day chunks: ~countries×apps×60 rows, safely < 100k cap
                try:
                    with _sc.stage("admob_country"):
                        for raw in client.country_report(cs, ce):
                            repo.upsert_country(build_country_row(raw))
                            totals["country"] += 1
                except Exception as e:
                    import sys
                    print(f"country report chunk {cs}..{ce} skipped for {acct.get('account_id')}: {e}",
                          file=sys.stderr)
                cs = ce + timedelta(days=1)
            # per-placement × country over a SHORT 7-day window (aggregate) — geo mix per placement
            try:
                pc_start = max(start, end - timedelta(days=7))
                with _sc.stage("admob_placement_country"):
                    for raw in client.placement_country_report(pc_start, end):
                        repo.upsert_placement_country(build_pc_row(raw))
                        totals["pc"] = totals.get("pc", 0) + 1
            except Exception as e:
                import sys
                print(f"placement-country report skipped for {acct.get('account_id')}: {e}", file=sys.stderr)
            # ad-unit × country × daily → streamed straight into the rollup accumulator (no big list).
            # Pull in 30-day windows (each still safe-split further under the 100k cap) so one bad
            # window can't lose the whole backfill, and a transient error is isolated per chunk.
            plan = ac_plan(acct) if ac_acc is not None else None
            if ac_acc is not None and feed is not None:        # C: on its own thread; folded below in account order
                slot = [list(getattr(client, "truncations", []))]
                slots.append(slot)
                feed.submit(slot, _ac_job(acct, mode, client_id, client_secret, currency, today=today,
                                          ac_start=ac_start, ac_end=ac_end, ac_full_history=ac_full_history,
                                          adunit_country_days=adunit_country_days, plan=plan))
                with _sc.stage("admob_adunit_country"):
                    feed.drain(ac_fold, ac_done, block=False)
                continue
            if ac_acc is not None:
                if ac_full_history:
                    # probe THIS account's true start so any app age is fully covered automatically
                    try:
                        ds = client.data_start(today, max_lookback=adunit_country_days or 2555)
                    except Exception as e:
                        import sys
                        print(f"data_start probe failed for {acct.get('account_id')}: {e}", file=sys.stderr)
                        ds = None
                    acs = ds or ac_start or (today - timedelta(days=2555))
                else:
                    acs = ac_start
                cs = acs
                while cs <= ac_end:
                    ce = min(cs + timedelta(days=29), ac_end)
                    try:
                        with _sc.stage("admob_adunit_country"):
                            src = (client.adunit_country_report(cs, ce, plan=plan) if plan is not None
                                   else client.adunit_country_report(cs, ce))
                            for raw in src:
                                ac_acc.add(build_ac_row(raw))
                                totals["adunit_country"] = totals.get("adunit_country", 0) + 1
                    except Exception as e:
                        import sys
                        print(f"adunit-country chunk {cs}..{ce} skipped for {acct.get('account_id')}: {e}", file=sys.stderr)
                    cs = ce + timedelta(days=1)
                if plan is not None:
                    _plan_log(plan)
            # surface any slice the safe-fetch layer could not fully split (real client only)
            truncations.extend(getattr(client, "truncations", []))
        if feed is not None:                                   # C: the rest of the accounts' rows, in account order
            with _sc.stage("admob_adunit_country"):
                feed.drain(ac_fold, ac_done, block=True)
    finally:
        if feed is not None:
            feed.close()
    if feed is not None:
        for slot in slots:
            for part in slot:
                truncations.extend(part)
    # persist the ad-unit×country baseline: completed months → rollup (upsert), current month → daily (replace)
    if ac_acc is not None:
        # full-history backfill: NO coverage guard (window_start=None) so EVERY month present rolls
        # up, including the account's genuinely-partial FIRST month. Ongoing runs guard on the
        # window start so a clipped past month isn't half-rolled over its complete rollup.
        with _sc.stage("admob_rollup"):
            rollups, current_daily = ac_acc.finish(window_start=None if ac_full_history else ac_start)
            repo.merge_adunit_country_monthly(rollups)      # completed months → compact monthly rollup
            repo.replace_adunit_country_daily(current_daily)  # current month → compact daily
        totals["acm"] = len(rollups)
        totals["acd"] = len(current_daily)
    totals["truncations"] = truncations
    return totals


def finalize_month(accounts: List[Dict], repo, *, year: int, month: int,
                   mode="mock", client_id=None, client_secret=None) -> int:
    """Month-close pass: re-pull a whole past month and mark rows is_finalized=True
    (AdMob removes invalid traffic before finalizing). Run a few days into the
    next month."""
    import calendar
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    n = 0
    for acct in accounts:
        client = make_client(acct, mode, client_id, client_secret)
        for raw in client.network_report(start, end):
            row = build_network_row(raw)
            row["is_finalized"] = True
            repo.upsert_network(row)
            n += 1
    return n


def main():
    from ..config import settings, load_accounts
    from ..db import PgRepo
    s = settings()
    repo = PgRepo(s["database_url"])
    repo.init_schema()
    totals = run_once(load_accounts(), repo, today=date.today(),
                      mode=s["fetch_mode"], rolling_days=s["rolling_days"],
                      client_id=s["google_client_id"],
                      client_secret=s["google_client_secret"],
                      currency=s["report_currency"])
    print("fetch complete:", totals)


if __name__ == "__main__":
    main()
