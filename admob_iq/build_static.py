"""Daily static-site build — the WHOLE 'backend' for the free, no-code host.

One command:  python -m admob_iq.build_static

It (1) pulls AdMob for every account, (2) runs the full analysis engine,
(3) writes  site/dashboard.json  and copies the dashboard UI into  site/, and
(4) sends Telegram + Email alerts. History lives in flat JSON files (FileRepo),
so there is NO always-on server and NO database. A once-a-day schedule
(GitHub Actions or a hosting control-panel cron) runs this; the static  site/
folder is what gets served (Cloudflare Pages / BunnyCDN / your own hosting).

Accounts come from the ADMOB_ACCOUNTS_JSON secret if set (nothing committed),
else config/accounts.yaml, else a built-in mock so the very first deploy still
shows a working demo instead of crashing.
"""

import json
import os
import re
import shutil
import sys
from datetime import date, datetime, timezone, timedelta

from .config import settings, load_accounts
from .db import FileRepo
from .fetch import fetcher
from .fetch.coverage import verify_coverage, verify_entity_spans
from .api.dataservice import build_from_db, build_dashboard, empty_dashboard
from .alerting import notify as notifier

_ICON = {"critical": "🔴", "warning": "🟠", "watch": "🟡", "good": "🎉"}


def data_quality(repo, totals):
    """Post-fetch integrity check: confirm the stored data has no truncation holes.
    Runs verify_coverage over each report's OWN span (excluding the newest, partial day so a
    normal thin 'today' isn't flagged) and reports any slice the safe-fetch layer couldn't
    split. Attached to the dashboard so a gap is visible, never silent."""
    import sys
    from datetime import date as _date

    def _span_check(rows, label, entity_key=None):
        dates = sorted({str(r.get("report_date"))[:10] for r in rows if r.get("report_date")})
        if len(dates) < 2:
            return {"report": label, "ok": True, "note": "too little data to check"}
        lo = _date.fromisoformat(dates[0])
        hi = _date.fromisoformat(dates[-2])           # drop the newest (possibly partial) day
        rep = verify_coverage([r for r in rows if str(r.get("report_date"))[:10] <= dates[-2]], lo, hi)
        rep["report"] = label
        if entity_key:
            sp = verify_entity_spans(rows, entity_key=entity_key)
            rep["clipped_suspects"] = sp["clipped_suspects"][:10]
        for f in rep.get("flags", []):
            print(f"data-quality [{label}]: {f}", file=sys.stderr)
        return rep

    dq = {"truncations": totals.get("truncations", []), "reports": []}
    try:
        dq["reports"].append(_span_check(list(repo.fetch_network()), "network"))
    except Exception as e:
        print(f"data-quality network check skipped: {e}", file=sys.stderr)
    try:
        dq["reports"].append(_span_check(list(repo.fetch_country()), "country", entity_key="country"))
    except Exception as e:
        print(f"data-quality country check skipped: {e}", file=sys.stderr)
    dq["ok"] = not dq["truncations"] and all(r.get("ok", True) for r in dq["reports"])
    if dq["truncations"]:
        print(f"data-quality: {len(dq['truncations'])} UNSPLITTABLE truncation(s) — data incomplete!",
              file=sys.stderr)
    return dq


def _tz_label(tz: str) -> str:
    """Friendly label for the reporting timezone, shown in the UI so the user knows
    which clock the numbers are on (and why they match their AdMob app)."""
    t = (tz or "").lower()
    if "kolkata" in t or "calcutta" in t:
        return "India Standard Time (IST)"
    if "los_angeles" in t:
        return "US Pacific Time (PT)"
    if t in ("utc", "etc/utc"):
        return "UTC"
    return tz or "—"


def resolve_accounts():
    """Secret (JSON) > accounts.yaml > mock. Keeps secrets out of the repo."""
    raw = os.getenv("ADMOB_ACCOUNTS_JSON", "").strip()
    if raw:
        data = json.loads(raw)
        return data if isinstance(data, list) else data.get("accounts", [])
    return load_accounts()


def alert_lines(dashboard):
    """One notification line per alert item. Handles BOTH shapes: grouped alerts (one
    placement with a `metrics` list — the current build_from_db output) and the older
    flat per-metric item (a single `message`). Never KeyErrors on a missing field."""
    lines = []
    for a in dashboard.get("alerts", {}).get("items", []):
        icon = _ICON.get(a.get("severity"), "•")
        geo = a.get("country") or "all countries"
        place = a.get("place", "?")
        mets = a.get("metrics")
        desc = "; ".join(m.get("message", "") for m in mets) if mets else a.get("message", "")
        lost = a.get("lost")
        losttxt = f' (~${lost}/day)' if lost else ''
        sev = str(a.get("severity", "")).upper()
        lines.append(f'{icon} [{sev}] {place} — {desc}{losttxt} · {geo}')
    return lines


def send_alerts(dashboard, s):
    """Telegram gets the urgent ones live; email gets the full daily digest.
    dry_run (the default until creds are set) just formats — nothing leaks."""
    lines = alert_lines(dashboard)
    # out-of-range (approved-range breach) alerts — separate list, folded into the digest
    for a in dashboard.get("range_alerts", []):
        icon = _ICON.get(a.get("severity"), "•")
        sev = str(a.get("severity", "")).upper()
        geo = a.get("country") or "all countries"
        lines.append(f'{icon} [{sev}] {a.get("place", "?")} — {a.get("message", "")} · approved-range breach · {geo}')
    if not lines:
        return []
    dry = s["notify_dry_run"]
    results = []
    urgent = [l for l in lines if "[CRITICAL]" in l or "[WARNING]" in l or l.startswith("🎉")]
    if urgent:
        results.append(notifier.send_telegram("\n".join(urgent), s["telegram_token"],
                                               s["telegram_chat"], dry))
    results.append(notifier.send_email("AdMob IQ — daily alerts", "\n".join(lines),
                                        s["smtp"], dry))
    return results


class _AppFilteredRepo:
    """Read-only wrapper that hides every row/unit whose app_id was UNSELECTED by the user, so the
    built dashboard + baseline exclude those apps EVERYWHERE (KPIs, placements, movers, countries,
    deductions, recommendations, health…) — consistently, from one choke point. Stored data is
    untouched (flush() uses the real repo), and the apps catalog/picker still lists every app. Any
    method not overridden passes straight through to the wrapped repo."""

    def __init__(self, repo, hidden_ids):
        self._r = repo
        self._h = set(hidden_ids or ())

    def __getattr__(self, name):
        return getattr(self._r, name)

    def _flat(self, rows):
        return [r for r in rows if r.get("app_id") not in self._h]

    def fetch_network(self):
        return self._flat(self._r.fetch_network())

    def fetch_mediation(self):
        return self._flat(self._r.fetch_mediation())

    def fetch_country(self):
        return self._flat(self._r.fetch_country())

    def fetch_placement_country(self):
        return self._flat(self._r.fetch_placement_country())

    def fetch_snapshots(self):
        return self._flat(self._r.fetch_snapshots())

    def _nested(self, nested):
        # ad-unit×country structures are keyed by ad_unit_id; units[uid][0] is the app_id.
        if not isinstance(nested, dict) or "units" not in nested:
            return nested
        units = nested.get("units", {})
        keep = {u for u, m in units.items() if (m or [None])[0] not in self._h}
        return {**nested,
                "units": {u: m for u, m in units.items() if u in keep},
                "data": {u: d for u, d in (nested.get("data") or {}).items() if u in keep}}

    def fetch_adunit_country_monthly(self):
        return self._nested(self._r.fetch_adunit_country_monthly())

    def fetch_adunit_country_daily(self):
        return self._nested(self._r.fetch_adunit_country_daily())


class _DisambiguatedRepo:
    """Read-only wrapper that decides the app NAME every view shows.

    Two jobs, in this order:
      1. the user's OWN name for an app (config/app_names.json, typed via the pencil next to the
         app title on the dashboard) replaces whatever AdMob reports;
      2. AdMob then still allows two different apps to carry the SAME display name, so an alert, a
         mover or a deduction row is impossible to trace back to the right app. Where a name is
         still shared by more than one app_id we append the owning account ("<name> · pub-1234…").

    Done here, at one choke point, so EVERY view (KPIs, alerts, movers, mediation, deductions,
    baseline, ROAS, apps catalog) shows the same name — and, unlike renaming the app inside AdMob,
    it also fixes ALL historical rows instead of splitting an app's history in two. Names that are
    already unique and uncustomised are left exactly as they are.
    """

    SEP = " · "

    def __init__(self, repo, account_names=None, app_names=None):
        self._r = repo
        self._names = account_names or {}                # pub-id -> friendly account name
        self._custom = app_names or {}                   # app_id -> the name the user typed
        self._map = {}                                   # app_id -> final display name
        self._orig = {}                                  # AdMob's own name -> {final names}
        try:
            rows = repo.fetch_network()
            self._map = self._build_map(rows, self._names, self._custom)
            for r in rows:                               # so config written against AdMob's name
                aid, nm = r.get("app_id"), r.get("app_name")   # can follow the rename — see
                if aid and nm:                                 # rename_candidates. EVERY app that
                    self._orig.setdefault(nm, set()).add(self._map.get(aid) or nm)   # shared that
                                                               # name is a candidate, renamed or not
            if self._map:
                n_c = sum(1 for a in self._map if a in self._custom)
                print("app names: %d renamed (%d custom, %d duplicate-name tags)"
                      % (len(self._map), n_c, len(self._map) - n_c), file=sys.stderr)
        except Exception as e:
            print(f"app-name disambiguation skipped: {e}", file=sys.stderr)

    def rename_candidates(self, name):
        """Final display name(s) for the app AdMob calls `name` — [name] if nothing renamed it.
        Config keyed by the raw AdMob name (the ROAS store-id aliases) resolves through this, so a
        rename can't silently drop that app's spend into 'unmatched'."""
        return sorted(self._orig.get(name) or [name])

    @staticmethod
    def _account_of(app_id, account_id):
        acc = str(account_id or "")
        if not acc:                                      # fall back to the pub- prefix of the app id
            m = re.match(r"ca-app-(pub-\d+)~", str(app_id or ""))
            acc = m.group(1) if m else ""
        return acc

    @classmethod
    def _build_map(cls, rows, names=None, custom=None):
        names, custom = names or {}, custom or {}
        by_name, seen = {}, set()                        # effective name -> {app_id: account_id}
        for r in rows:
            aid, nm = r.get("app_id"), r.get("app_name")
            if aid and nm:
                seen.add(aid)
                eff = custom.get(aid) or nm              # the user's own name wins over AdMob's
                by_name.setdefault(eff, {}).setdefault(aid, cls._account_of(aid, r.get("account_id")))
        # every custom name applies, clash or not; ids no longer in the data are simply ignored
        out = {aid: nm for aid, nm in custom.items() if aid in seen and nm}
        for nm, apps in by_name.items():
            if len(apps) < 2:
                continue                                 # already unique — leave it alone
            # prefer the human account name from config/account_names.json; fall back to the pub id
            short = {aid: (names.get(acc) or (acc[:8] + "…" if len(acc) > 9 else acc))
                     for aid, acc in apps.items()}
            if len(set(short.values())) < len(apps):     # shortened accounts clash — use them in full
                short = dict(apps)
            if len(set(short.values())) < len(apps):     # same name AND same account — use the app id
                short = {aid: str(aid).split("~")[-1][-6:] for aid in apps}
            for aid, tag in short.items():
                if tag:
                    out[aid] = nm + cls.SEP + tag
        return out

    def __getattr__(self, name):
        return getattr(self._r, name)

    def _rows(self, rows):
        if not self._map:
            return rows
        return [({**r, "app_name": self._map[r["app_id"]]}
                 if r.get("app_id") in self._map and r.get("app_name") else r) for r in rows]

    def fetch_network(self):
        return self._rows(self._r.fetch_network())

    def fetch_mediation(self):
        return self._rows(self._r.fetch_mediation())

    def fetch_country(self):
        return self._rows(self._r.fetch_country())

    def fetch_placement_country(self):
        return self._rows(self._r.fetch_placement_country())

    def fetch_snapshots(self):
        return self._rows(self._r.fetch_snapshots())

    def _nested(self, nested):
        # units[uid] = [app_id, unit_name, app_name, currency]
        if not self._map or not isinstance(nested, dict) or "units" not in nested:
            return nested
        units = {}
        for u, meta in (nested.get("units") or {}).items():
            nn = self._map.get((meta or [None])[0])
            if nn and isinstance(meta, (list, tuple)) and len(meta) > 2:
                meta = list(meta)
                meta[2] = nn
            units[u] = meta
        return {**nested, "units": units}

    def fetch_adunit_country_monthly(self):
        return self._nested(self._r.fetch_adunit_country_monthly())

    def fetch_adunit_country_daily(self):
        return self._nested(self._r.fetch_adunit_country_daily())


def _account_names(data_dir):
    """Friendly labels for AdMob accounts, from config/account_names.json — e.g.
    {"pub-1234567890123456": "Helsy Main"}. Used to tag apps whose display name is shared by more
    than one app, so the tag reads "Gallery · Helsy Main" instead of "Gallery · pub-1234…".
    Optional: any account missing here just falls back to its shortened publisher id."""
    path = os.path.join(os.path.dirname(data_dir) or ".", "config", "account_names.json")
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                raw = json.load(f) or {}
            out = {str(k).strip(): str(v).strip() for k, v in raw.items() if str(v or "").strip()}
            if out:
                print("account names: %d label(s) loaded" % len(out), file=sys.stderr)
            return out
    except Exception as e:
        print(f"account names skipped: {e}", file=sys.stderr)
    return {}


def _app_names(data_dir):
    """The user's OWN names for apps, from config/app_names.json — {app_id: "Gallery (Main)"}.
    Written by the pencil next to the app title on the dashboard's App Report screen.

    Keyed by app_id, never by name, so the name can be edited again later and so every historical
    row follows it. Applied BEFORE duplicate-name tagging, so a renamed app only keeps a "· account"
    tag if the NEW name still collides with another app."""
    path = os.path.join(os.path.dirname(data_dir) or ".", "config", "app_names.json")
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                raw = json.load(f) or {}
            out = {str(k).strip(): str(v).strip()[:80] for k, v in raw.items()
                   if str(k or "").strip() and str(v or "").strip()}
            if out:
                print("custom app names: %d loaded" % len(out), file=sys.stderr)
            return out
    except Exception as e:
        print(f"custom app names skipped: {e}", file=sys.stderr)
    return {}


def _hidden_app_ids(repo, data_dir):
    """The set of app_ids the user has UNSELECTED (decided accounts only). Derived from the network
    report (which carries account_id + app_id) + config/selected_apps.json. Empty if no selection."""
    try:
        from .engine.app_select import load_selection, app_visible
        sel = load_selection(os.path.join(os.path.dirname(data_dir) or ".", "config", "selected_apps.json"))
        if not (sel.get("accounts") or {}):
            return set()
        return {r["app_id"] for r in repo.fetch_network()
                if r.get("app_id") and not app_visible(sel, r.get("account_id"), r.get("app_id"))}
    except Exception as e:
        print(f"hidden-app filter skipped: {e}", file=sys.stderr)
        return set()


def _backfill_missing_accounts_ac(accounts, repo, today, *, mode, client_id, client_secret,
                                  currency, max_lookback=1300, data_dir="data"):
    """One-time, PER APP: every VISIBLE app that has NO monthly (acm) baseline yet gets its full
    ad-unit×country history pulled and rolled up, so it appears in the Baseline. Detection is at the
    APP level (not the account), so NOTHING is missed — a freshly-added account, a brand-new app in
    an account that's already partly covered, or an app the user just un-hid are ALL caught. An app
    already in acm is skipped, so covered history is never re-pulled (idempotent, minimal AdMob load).

    'Visible' = a DECIDED account's selected app_ids (hidden apps are never fetched nor stored); an
    UNDECIDED account (no pick yet) contributes every app it has — a brand-new undecided account is
    pulled whole in one pass (so even an app with no recent traffic is captured), and a new app that
    later appears in an already-covered undecided account is caught from the network report. A DECIDED
    account with zero apps selected is skipped. Never crashes the build (best-effort)."""
    import re
    from collections import defaultdict
    from datetime import timedelta
    from .fetch.fetcher import make_client, build_ac_row
    from .fetch.admob_client import _app_filter
    from .engine.app_select import load_selection, selected_ids
    from .engine.rollup import RollupAccumulator
    try:
        acm = repo.fetch_adunit_country_monthly()
    except Exception:
        return 0

    def _acct(app_id):
        m = re.search(r"ca-app-pub-(\d+)", str(app_id) or "")
        return "pub-" + m.group(1) if m else None

    have_apps = {(m or [None])[0] for m in (acm.get("units") or {}).values()}
    have_apps.discard(None)                        # app_ids that ALREADY have baseline history
    have_accts = {_acct(x) for x in have_apps}     # accounts with ANY baseline so far
    have_accts.discard(None)

    # Each account's real apps, from THIS run's network pull — lets us enumerate an undecided
    # account's visible apps (a decided account uses its explicit pick instead).
    apps_by_acct = defaultdict(set)
    try:
        for r in repo.fetch_network():
            if r.get("account_id") and r.get("app_id"):
                apps_by_acct[r["account_id"]].add(r["app_id"])
    except Exception:
        pass

    sel = load_selection(os.path.join(os.path.dirname(data_dir) or ".", "config", "selected_apps.json"))

    # Split the work: whole-account pulls (brand-new undecided accounts) and per-app scoped pulls
    # (decided accounts' picked apps + new apps in already-covered accounts).
    todo_full, todo_apps = [], []                  # [account], [(account, [missing_app_ids])]
    for a in accounts:
        aid = a.get("account_id")
        if not aid:
            continue
        keep = selected_ids(sel, aid)              # None = undecided, set() = decided-but-none
        if keep is None:
            if aid not in have_accts:
                todo_full.append(a)                # new undecided account → pull every app in one pass
            else:
                want = sorted(apps_by_acct.get(aid, set()) - have_apps)   # only newly-appeared apps
                if want:
                    todo_apps.append((a, want))
        elif not keep:
            print(f"baseline backfill: {aid} has 0 apps selected → skipping", file=sys.stderr)
            continue
        else:
            want = sorted(app for app in keep if app not in have_apps)    # selected apps missing baseline
            if want:
                todo_apps.append((a, want))
    if not todo_full and not todo_apps:
        return 0

    acc = RollupAccumulator(today)

    def _pull(client, cs0, flt):
        cs = cs0
        while cs <= today:
            ce = min(cs + timedelta(days=29), today)
            for raw in client.adunit_country_report(cs, ce, dim_filters=flt):
                acc.add(build_ac_row(raw))
            cs = ce + timedelta(days=1)

    for a in todo_full:                            # whole brand-new undecided account (all apps)
        aid = a["account_id"]
        try:
            client = make_client(a, mode, client_id, client_secret, currency)
            ds = client.data_start(today, max_lookback=max_lookback)
            cs0 = ds or (today - timedelta(days=max_lookback))
            print(f"NEW-account baseline backfill: {aid} from {cs0} — all apps", file=sys.stderr)
            _pull(client, cs0, None)
        except Exception as e:
            print(f"new-account backfill failed for {aid}: {e}", file=sys.stderr)

    for a, want in todo_apps:                       # specific apps missing baseline (scoped per app)
        aid = a["account_id"]
        try:
            client = make_client(a, mode, client_id, client_secret, currency)
            print(f"NEW-app baseline backfill: {aid} — {len(want)} app(s) missing baseline", file=sys.stderr)
            for app_id in want:
                flt = [_app_filter(app_id)]
                ds = client.data_start(today, max_lookback=max_lookback, dim_filters=flt)
                if ds is None:                      # app has never earned yet → nothing to roll up
                    print(f"  {app_id}: no data yet → skip", file=sys.stderr)
                    continue
                print(f"  {app_id} from {ds}", file=sys.stderr)
                _pull(client, ds, flt)
        except Exception as e:
            print(f"new-app backfill failed for {aid}: {e}", file=sys.stderr)

    rollups, _ = acc.finish(window_start=None)     # full history → every COMPLETE month rolls up
    if rollups:
        repo.merge_adunit_country_monthly(rollups)
    return len(rollups)


def build(out_dir="site", data_dir="data", today=None, mode=None):
    s = settings()
    accounts = resolve_accounts()
    mode = mode or s["fetch_mode"]

    # Never crash a fresh, unconfigured deploy: fall back to the demo dataset if
    # live creds aren't in place yet.
    has_creds = bool(s["google_client_id"]) and any(a.get("refresh_token") for a in accounts)
    if mode == "live" and not has_creds:
        mode = "mock"

    # Reporting timezone: an explicit REPORT_TIMEZONE env wins; otherwise read the
    # ACCOUNT's own reporting timezone from the AdMob API so "today"/"yesterday" and
    # every range match the AdMob app the user sees; otherwise fall back to Pacific.
    report_tz = s.get("report_tz") or ""
    if not report_tz and mode == "live" and has_creds:
        try:
            from .fetch.admob_client import AdMobClient
            a0 = accounts[0]
            report_tz = (AdMobClient(a0["account_id"], s["google_client_id"],
                                     s["google_client_secret"], a0.get("refresh_token"))
                         .account_meta().get("reporting_tz") or "")
            if report_tz:
                print(f"using account reporting timezone: {report_tz}", file=sys.stderr)
        except Exception as e:
            print(f"could not read account timezone ({e}); falling back to Pacific", file=sys.stderr)
    report_tz = report_tz or "America/Los_Angeles"

    if today is None:
        # "today" in the REPORT timezone, not the CI runner's UTC (avoids an
        # off-by-one where the newest day looks empty).
        try:
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo(report_tz)).date()
        except Exception:
            today = datetime.now(timezone.utc).date()

    repo = FileRepo(data_dir)
    repo.init_schema()
    # One-time DEEP history backfill: the first run that finds no marker pulls a big window
    # (BACKFILL_DAYS) so 90d / All time / custom show the real depth; then it drops a marker
    # so every later run is the cheap 35-day refresh. AdMob keeps older finished days and
    # FileRepo never deletes them, so the deep history persists across the hourly runs.
    base_rolling = s["rolling_days"]                       # normal 35-day refresh
    backfill = int(os.getenv("BACKFILL_DAYS", "0") or "0")
    marker = os.path.join(data_dir, ".backfilled")
    did_backfill = mode == "live" and backfill > base_rolling and not os.path.exists(marker)
    rolling = backfill if did_backfill else base_rolling
    if did_backfill:
        print(f"one-time history backfill: pulling {rolling} days", file=sys.stderr)
    # Country report gets its OWN one-time deep backfill (separate marker), because the first
    # attempt's single 365-day request hit the 100k cap and AdMob truncated it — dropping older
    # rows for some geos (e.g. US had 37 days while IN had 292). The chunked pull (60-day pieces,
    # each safely under the cap) fills every geo. A distinct-date count can't detect this (the
    # union already spans a year), so gate on a dedicated marker, not on span.
    country_marker = os.path.join(data_dir, ".country_backfilled")
    do_country_backfill = mode == "live" and backfill > base_rolling and not os.path.exists(country_marker)
    country_days = backfill if do_country_backfill else rolling
    if do_country_backfill:
        print(f"country deep backfill (chunked): pulling {country_days} days", file=sys.stderr)
    # Ad-unit × country baseline: on the FIRST run for this data dir (marker absent) it pulls the
    # account's WHOLE history automatically — run_once probes each account's real start date, so a
    # brand-new app or a 3-year-old one is both fully captured with no day-count to guess. After
    # that, a ~45-day window each run (current month daily + the just-finished month to roll up).
    # No dependency on the user's backfill number, so this can never be under-set again.
    ac_marker = os.path.join(data_dir, ".ac_backfilled")
    do_ac_backfill = mode == "live" and not os.path.exists(ac_marker)
    ac_max_lookback = int(os.getenv("AC_MAX_LOOKBACK_DAYS", "1300"))   # cap the probe (~3.5yr; storage-safe)
    adunit_country_days = ac_max_lookback if do_ac_backfill else max(45, base_rolling)
    if do_ac_backfill:
        print(f"ad-unit×country FULL-HISTORY backfill (auto-detect start, ≤{ac_max_lookback}d)", file=sys.stderr)
    totals = fetcher.run_once(accounts, repo, today=today, mode=mode,
                              rolling_days=rolling, country_days=country_days,
                              adunit_country_days=adunit_country_days,
                              ac_full_history=do_ac_backfill,
                              client_id=s["google_client_id"],
                              client_secret=s["google_client_secret"],
                              currency=s["report_currency"])
    # Any account still missing its monthly baseline history (e.g. added after the global backfill)
    # gets a one-time per-account full-history pull so it appears in the Baseline. Idempotent.
    if mode == "live" and has_creds:
        try:
            _backfill_missing_accounts_ac(accounts, repo, today, mode=mode,
                                          client_id=s["google_client_id"], client_secret=s["google_client_secret"],
                                          currency=s["report_currency"], max_lookback=ac_max_lookback,
                                          data_dir=data_dir)
        except Exception as e:
            print(f"new-account baseline backfill skipped: {e}", file=sys.stderr)
    repo.flush()          # persist the refreshed history to disk (committed by CI)
    if did_backfill and repo.has_data():           # mark done only after a successful deep pull
        os.makedirs(data_dir, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(f"backfilled {rolling} days\n")
    if do_country_backfill and repo.has_data():    # chunked country deep pull ran → don't repeat
        os.makedirs(data_dir, exist_ok=True)
        with open(country_marker, "w", encoding="utf-8") as f:
            f.write(f"country backfilled {country_days} days (chunked)\n")
    if do_ac_backfill and repo.has_data():         # all-time ad-unit×country baseline pulled → don't repeat
        os.makedirs(data_dir, exist_ok=True)
        with open(ac_marker, "w", encoding="utf-8") as f:
            f.write(f"adunit_country backfilled {adunit_country_days} days\n")

    baseline_payload = None
    if repo.has_data():
        # Hide the user's UNSELECTED apps from EVERY built view (one choke point) — the real repo
        # still holds the data; the picker/catalog below still lists every app.
        # Make duplicate app names unique BEFORE anything is built, so every view (and the apps
        # catalog below) reads the same unambiguous name — including historical rows.
        repo = _DisambiguatedRepo(repo, _account_names(data_dir), _app_names(data_dir))
        hidden = _hidden_app_ids(repo, data_dir)
        frepo = _AppFilteredRepo(repo, hidden) if hidden else repo
        dashboard = build_from_db(frepo, today=today)   # real data (today = the live/partial day)
        # Build the ad-unit×country baseline report (standard ranges + market eCPM trend), but ship
        # it as a SEPARATE baseline.json the UI lazy-loads only when the Baseline tab opens — so it
        # never weighs down the always-fetched dashboard.json. Focus on placements active in the
        # last ~4 months; full history stays in storage for drill-down.
        try:
            acm = frepo.fetch_adunit_country_monthly()
            if acm.get("data"):
                from .engine.baseline_report import build_baseline
                from .engine.approvals import load_approved, apply_approvals, range_alerts
                active_since = (today - timedelta(days=120)).strftime("%Y-%m")
                baseline_payload = build_baseline(
                    acm, frepo.fetch_adunit_country_daily(), active_since=active_since)
                # layer approved ranges (git-persisted) so movement is judged vs the APPROVED range
                approved = load_approved(os.path.join(os.path.dirname(data_dir) or ".", "config",
                                                      "approved_ranges.json"))
                apply_approvals(baseline_payload, approved)
                # out-of-range alerts (approved ranges breached) — separate list for Alerts tab + notify
                dashboard["range_alerts"] = range_alerts(baseline_payload)
                dashboard["has_baseline"] = True
        except Exception as e:
            print(f"baseline report skipped: {e}", file=sys.stderr)
    elif mode == "mock":
        dashboard = build_dashboard()                   # rich demo preview (no creds yet)
    else:
        dashboard = empty_dashboard(len(accounts))      # live but 0 rows → honest empty state, never fake demo
    if mode == "mock":
        dashboard["is_demo"] = True                     # sample data (no real creds) → always flagged
    # Which clock the numbers are on — so the UI can label it and the user knows why
    # the dashboard now matches their AdMob app.
    dashboard["report_tz"] = report_tz
    dashboard["report_tz_label"] = _tz_label(report_tz)
    # Freshness stamp (UTC) so the UI can show "last updated X min ago".
    dashboard["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Data-integrity summary: proves the pull has no truncation holes (or names any it found).
    if repo.has_data():
        dashboard["data_quality"] = data_quality(repo, totals)

    # Apps catalog for the picker: every app each account has (from the network report already in
    # hand — no extra fetch), with revenue, plus its current selected state. The dashboard renders
    # this as per-account checkboxes; unselected apps are hidden client-side (Phase A).
    if repo.has_data():
        try:
            from .engine.app_select import load_selection, account_decided, app_visible
            sel_path = os.path.join(os.path.dirname(data_dir) or ".", "config", "selected_apps.json")
            _sel = load_selection(sel_path)
            _cat = {}
            for r in repo.fetch_network():
                pid = r.get("app_id")
                if not pid:
                    continue
                aid = r.get("account_id")
                e = _cat.setdefault((aid, pid), {"rev": 0, "name": None})
                e["rev"] += (r.get("estimated_earnings_micros") or 0)
                e["name"] = r.get("app_name") or e["name"]
            catalog = [{"account_id": k[0], "app_id": k[1], "app_name": v["name"] or k[1],
                        "rev": round(v["rev"] / 1e6, 2),
                        "selected": app_visible(_sel, k[0], k[1]),
                        "account_decided": account_decided(_sel, k[0])}
                       for k, v in _cat.items()]
            catalog.sort(key=lambda x: (x["account_id"] or "", -x["rev"]))
            dashboard["apps_catalog"] = catalog
        except Exception as e:
            print(f"apps catalog skipped: {e}", file=sys.stderr)

    # Real store icons per app (Play / App Store), resolved once & cached in data/app_icons.json —
    # a metadata lookup, SEPARATE from the reporting quota and zero ongoing load. Best-effort: any
    # app we can't resolve just keeps its letter-avatar in the UI.
    if mode == "live" and has_creds:
        try:
            from .fetch.app_icons import resolve_app_icons
            from .fetch.fetcher import make_client
            icons = resolve_app_icons(accounts, data_dir, dashboard.get("apps_catalog"),
                                      client_id=s["google_client_id"], client_secret=s["google_client_secret"],
                                      currency=s["report_currency"], make_client=make_client, mode=mode)
            if icons:
                nm = {c["app_name"]: icons[c["app_id"]] for c in (dashboard.get("apps_catalog") or [])
                      if c.get("app_id") in icons and c.get("app_name")}     # UI checks name then app_id
                dashboard["app_icons"] = {**icons, **nm}
                print(f"app icons: {len(icons)} apps resolved", file=sys.stderr)
        except Exception as e:
            print(f"app icons skipped: {e}", file=sys.stderr)

    # ROAS: Google Ads (MCC) marketing spend vs AdMob revenue, per app. OPTIONAL — only runs if the
    # GOOGLE_ADS_* secrets are set; otherwise the ROAS screen shows a setup hint. Separate API, so it
    # never touches the AdMob pull. Spend is fetched over a rolling window and converted to USD.
    if mode == "live" and has_creds and repo.has_data():
        try:
            from .fetch.google_ads import fetch_app_spend, resolve_store_ids
            from .fetch.fetcher import make_client
            from .engine.roas import build_roas
            roas_days = int(os.getenv("ROAS_SPEND_DAYS", "120"))
            spend = fetch_app_spend(s, (today - timedelta(days=roas_days)).isoformat(),
                                    today.isoformat(), mode="live")
            store_ids = resolve_store_ids(accounts, data_dir, dashboard.get("apps_catalog"),
                                          client_id=s["google_client_id"], client_secret=s["google_client_secret"],
                                          currency=s["report_currency"], make_client=make_client, mode="live")
            # manual store-id -> app-name aliases for apps whose AdMob store listing isn't linked
            roas_aliases = {}
            for _ap in ("config/roas_app_aliases.json",):
                if os.path.exists(_ap):
                    try:
                        with open(_ap, encoding="utf-8") as _f:
                            roas_aliases = json.load(_f) or {}
                    except Exception as _e:
                        print(f"roas aliases skipped: {_e}", file=sys.stderr)
            # an alias points at the app's AdMob name; if that app has since been renamed (custom
            # name, or a duplicate-name tag) the alias must follow it, otherwise this app's ENTIRE
            # marketing spend silently falls back to 'unmatched'.
            _rc = getattr(repo, "rename_candidates", None)
            if _rc and roas_aliases:
                roas_aliases = {sid: _rc(nm) for sid, nm in roas_aliases.items() if sid and nm}
            dashboard["roas"] = build_roas(spend, store_ids, dashboard.get("apps_catalog"), roas_aliases)
            if spend is not None:
                print(f"roas: spend for {len(dashboard['roas'].get('by_app', {}))} apps "
                      f"({spend.get('currency_src')}→USD)", file=sys.stderr)
        except Exception as e:
            print(f"roas build skipped: {e}", file=sys.stderr)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "dashboard.json"), "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False)
    # Separate, lazy-loaded baseline payload (kept OUT of dashboard.json to keep first load light).
    # Two tiers: baseline.json (summaries + app-level country view) loads when the tab opens;
    # baseline_geo.json (per-ad-unit ALL countries) loads only on the first ad-unit drill.
    if baseline_payload is not None:
        from .engine.baseline_report import compact_geo, build_daily_series
        # Per-placement DAILY series for the placement-page chart, from the already-fetched network
        # report (no extra AdMob calls). Third lazy tier: baseline_daily.json loads only on drill.
        try:
            keep_ids = {u["id"] for u in baseline_payload.get("units", [])}
            daily = build_daily_series(repo.fetch_network(), keep_ids=keep_ids)
            with open(os.path.join(out_dir, "baseline_daily.json"), "w", encoding="utf-8") as f:
                json.dump({"units": daily}, f, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            print(f"daily series skipped: {e}", file=sys.stderr)
        geo = compact_geo(baseline_payload.pop("unit_geo", {}))
        with open(os.path.join(out_dir, "baseline.json"), "w", encoding="utf-8") as f:
            json.dump(baseline_payload, f, ensure_ascii=False, separators=(",", ":"))
        with open(os.path.join(out_dir, "baseline_geo.json"), "w", encoding="utf-8") as f:
            json.dump(geo, f, ensure_ascii=False, separators=(",", ":"))
        # Ad-unit × country DAILY (current month) — ALREADY fetched for the baseline, so NO extra
        # AdMob call. Shipped (lazy, hidden apps excluded via frepo) so the per-placement country
        # table can window to the SELECTED period; older windows fall back to the lifetime mix.
        try:
            acd = frepo.fetch_adunit_country_daily()
            if acd and acd.get("units"):
                with open(os.path.join(out_dir, "adunit_country_daily.json"), "w", encoding="utf-8") as f:
                    json.dump(acd, f, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            print(f"acd ship skipped: {e}", file=sys.stderr)

    # Daily-by-source mediation (date × app × ad_source) — ALREADY fetched daily-by-source
    # (upsert_mediation), so NO extra AdMob call. Shipped as its own lazy file (hidden apps
    # excluded via frepo) so the Mediation screen can window to the SELECTED period.
    if mode == "live" and repo.has_data():
        try:
            from .api.dataservice import build_mediation_daily
            med_daily = build_mediation_daily(frepo)
            if med_daily.get("by_app"):
                with open(os.path.join(out_dir, "mediation_daily.json"), "w", encoding="utf-8") as f:
                    json.dump(med_daily, f, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            print(f"mediation daily ship skipped: {e}", file=sys.stderr)

        # Per-unit estimate DECAY (deductions) — 'pehle itna, ab itna' — from the already-stored
        # snapshots (zero new fetch). Lazy file; the Deductions screen windows it to any period.
        try:
            from .api.dataservice import build_deductions_daily
            ded_daily = build_deductions_daily(frepo)
            if ded_daily.get("data"):
                with open(os.path.join(out_dir, "deductions_daily.json"), "w", encoding="utf-8") as f:
                    json.dump(ded_daily, f, ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            print(f"deductions daily ship skipped: {e}", file=sys.stderr)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ui = os.path.join(root, "frontend", "index.html")
    if os.path.exists(ui):
        shutil.copyfile(ui, os.path.join(out_dir, "index.html"))

    # Serve the current approved ranges so the dashboard can show + edit them (it commits changes
    # back to config/approved_ranges.json via the GitHub API using the user's token).
    appr_src = os.path.join(os.path.dirname(data_dir) or ".", "config", "approved_ranges.json")
    with open(os.path.join(out_dir, "approved_ranges.json"), "w", encoding="utf-8") as f:
        f.write(open(appr_src, encoding="utf-8").read() if os.path.exists(appr_src) else '{"placements":{}}')

    # Serve the app selection (which apps the user kept) so the dashboard can show + edit it; the UI
    # commits changes back to config/selected_apps.json via the GitHub API (same as approvals).
    sel_src = os.path.join(os.path.dirname(data_dir) or ".", "config", "selected_apps.json")
    with open(os.path.join(out_dir, "selected_apps.json"), "w", encoding="utf-8") as f:
        f.write(open(sel_src, encoding="utf-8").read() if os.path.exists(sel_src) else '{"accounts":{}}')

    # Serve the friendly account names so the Accounts & Apps screen can show + edit them; the UI
    # commits changes back to config/account_names.json via the GitHub API (same as the two above).
    an_src = os.path.join(os.path.dirname(data_dir) or ".", "config", "account_names.json")
    with open(os.path.join(out_dir, "account_names.json"), "w", encoding="utf-8") as f:
        f.write(open(an_src, encoding="utf-8").read() if os.path.exists(an_src) else "{}")

    # Serve the user's own app names so the pencil on the App Report screen starts from what is
    # actually applied; the UI commits changes back to config/app_names.json (same as the above).
    apn_src = os.path.join(os.path.dirname(data_dir) or ".", "config", "app_names.json")
    with open(os.path.join(out_dir, "app_names.json"), "w", encoding="utf-8") as f:
        f.write(open(apn_src, encoding="utf-8").read() if os.path.exists(apn_src) else "{}")

    # Cloudflare cache policy (_headers is read by Cloudflare's static-asset host).
    # dashboard.json changes hourly, so it must NEVER be served from a stale cache
    # — no-store forces every request to fetch the freshest file from origin.
    with open(os.path.join(out_dir, "_headers"), "w", encoding="utf-8") as f:
        f.write("/dashboard.json\n  Cache-Control: no-store\n\n"
                "/baseline.json\n  Cache-Control: no-store\n\n"
                "/baseline_geo.json\n  Cache-Control: no-store\n\n"
                "/baseline_daily.json\n  Cache-Control: no-store\n\n"
                "/selected_apps.json\n  Cache-Control: no-store\n\n"
                "/account_names.json\n  Cache-Control: no-store\n\n"
                "/app_names.json\n  Cache-Control: no-store\n\n"
                "/index.html\n  Cache-Control: no-cache\n")

    alerts = send_alerts(dashboard, s)
    return {"mode": mode, "fetch": totals, "alerts_sent": len(alerts),
            "out": out_dir, "revenue": dashboard["kpis"]["revenue"]}


def main():
    print("build complete:", build())


if __name__ == "__main__":
    main()
