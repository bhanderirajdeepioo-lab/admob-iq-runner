"""Daily multi-account pull: network + mediation, derive metrics, upsert facts,
and append earnings snapshots (deduction tracking).

`run_once` takes an injected client factory + repo so it is fully testable with
the mock client and an in-memory repo (no creds, no DB)."""

from datetime import date, timedelta
from typing import Dict, List

from ..engine import metrics
from .admob_client import MockAdMobClient, AdMobClient


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


def run_once(accounts: List[Dict], repo, *, today: date, mode="mock",
             rolling_days=7, country_days=None, adunit_country_days=None,
             ac_full_history=False, client_id=None, client_secret=None, currency="USD") -> Dict:
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
    for acct in accounts:
        client = make_client(acct, mode, client_id, client_secret, currency)
        # Per-account isolation: a bad/expired token or auth error on ONE account (which surfaces
        # on its first API call) must NOT crash the whole run and freeze every other account's data.
        # Log it and move on — that account simply gets no fresh data this run; its old data stays.
        try:
            for raw in client.network_report(start, end):
                repo.upsert_network(build_network_row(raw))
                repo.append_snapshot(build_snapshot(raw, today))
                totals["network"] += 1
                totals["snapshots"] += 1
            for raw in client.mediation_report(start, end):
                repo.upsert_mediation(build_mediation_row(raw))
                totals["mediation"] += 1
        except Exception as e:
            import sys
            print(f"account {acct.get('account_id')} skipped this run (auth/report error): {e}", file=sys.stderr)
            totals.setdefault("account_errors", []).append({"account_id": acct.get("account_id"), "error": str(e)[:200]})
            continue
        # Country breakdown is a SEPARATE, additive report. Pull it in <=90-day chunks so a
        # long history backfill never rides on one huge request, and a transient failure on
        # one chunk doesn't lose the rest (each chunk is best-effort). Never let a hiccup
        # here break the core revenue pull.
        cs = c_start
        while cs <= c_end:
            ce = min(cs + timedelta(days=59), c_end)     # 60-day chunks: ~countries×apps×60 rows, safely < 100k cap
            try:
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
            for raw in client.placement_country_report(pc_start, end):
                repo.upsert_placement_country(build_pc_row(raw))
                totals["pc"] = totals.get("pc", 0) + 1
        except Exception as e:
            import sys
            print(f"placement-country report skipped for {acct.get('account_id')}: {e}", file=sys.stderr)
        # ad-unit × country × daily → streamed straight into the rollup accumulator (no big list).
        # Pull in 30-day windows (each still safe-split further under the 100k cap) so one bad
        # window can't lose the whole backfill, and a transient error is isolated per chunk.
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
                    for raw in client.adunit_country_report(cs, ce):
                        ac_acc.add(build_ac_row(raw))
                        totals["adunit_country"] = totals.get("adunit_country", 0) + 1
                except Exception as e:
                    import sys
                    print(f"adunit-country chunk {cs}..{ce} skipped for {acct.get('account_id')}: {e}", file=sys.stderr)
                cs = ce + timedelta(days=1)
        # surface any slice the safe-fetch layer could not fully split (real client only)
        truncations.extend(getattr(client, "truncations", []))
    # persist the ad-unit×country baseline: completed months → rollup (upsert), current month → daily (replace)
    if ac_acc is not None:
        # full-history backfill: NO coverage guard (window_start=None) so EVERY month present rolls
        # up, including the account's genuinely-partial FIRST month. Ongoing runs guard on the
        # window start so a clipped past month isn't half-rolled over its complete rollup.
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
