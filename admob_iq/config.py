"""Settings from env + accounts from YAML."""

import os


def _env(name, default=""):
    """os.getenv but treats an UNSET *and* an empty-string value the same.
    GitHub Actions passes unset secrets as "" (not absent), so `int(os.getenv(..,"587"))`
    would blow up on ""; `_env(.., "587")` returns the default instead."""
    v = os.getenv(name)
    return v if v not in (None, "") else default


def settings() -> dict:
    return {
        "database_url": _env("DATABASE_URL"),
        "fetch_mode": _env("FETCH_MODE", "mock"),
        "rolling_days": int(_env("ROLLING_REPULL_DAYS", "35")),   # cover a full 30-day range (+buffer) so 30d totals are complete, not half-filled
        "report_currency": _env("REPORT_CURRENCY", "USD"),
        "google_client_id": _env("GOOGLE_CLIENT_ID") or None,
        "google_client_secret": _env("GOOGLE_CLIENT_SECRET") or None,
        # Google Ads (MCC) — marketing spend for ROAS. Optional: absent → ROAS screen shows a setup hint.
        "google_ads_dev_token": _env("GOOGLE_ADS_DEVELOPER_TOKEN") or None,
        "google_ads_login_customer_id": _env("GOOGLE_ADS_LOGIN_CUSTOMER_ID").replace("-", "") or None,
        "google_ads_refresh_token": _env("GOOGLE_ADS_REFRESH_TOKEN") or None,
        # Optional: if the Google Ads refresh token was minted with a DIFFERENT OAuth client than
        # AdMob's, set these; otherwise the AdMob GOOGLE_CLIENT_ID/SECRET is used for Google Ads too.
        "google_ads_client_id": _env("GOOGLE_ADS_CLIENT_ID") or None,
        "google_ads_client_secret": _env("GOOGLE_ADS_CLIENT_SECRET") or None,
        "report_tz": _env("REPORT_TIMEZONE"),   # empty => auto-detect from the AdMob account
        "notify_dry_run": _env("NOTIFY_DRY_RUN", "true").lower() == "true",
        "telegram_token": _env("TELEGRAM_BOT_TOKEN"),
        "telegram_chat": _env("TELEGRAM_CHAT_ID"),
        "smtp": {"host": _env("SMTP_HOST"), "port": int(_env("SMTP_PORT", "587")),
                 "user": _env("SMTP_USER"), "pass": _env("SMTP_PASS"),
                 "to": _env("ALERT_EMAIL_TO")},
        # GA4 (uninstall tab). The OAuth client is taken as a PAIR — a refresh token only works with the
        # client that minted it: the GA4_* pair when GA4_CLIENT_ID is set, else the AdMob GOOGLE_* pair.
        "ga4_client_id": (_env("GA4_CLIENT_ID") or _env("GOOGLE_CLIENT_ID")) or None,
        "ga4_client_secret": (_env("GA4_CLIENT_SECRET") if _env("GA4_CLIENT_ID")
                              else _env("GOOGLE_CLIENT_SECRET")) or None,
        "ga4_refresh_tokens": _env("GA4_REFRESH_TOKENS"),    # JSON {owner email: refresh token}
        "ga4_refresh_token": _env("GA4_REFRESH_TOKEN"),      # older single token ("legacy")
        "ga4_enabled": _env("GA4_ENABLED", "true").lower() == "true",
        "ga4_min_hours": float(_env("GA4_MIN_HOURS", "20")),        # fetch each app at most once per ~day
        "ga4_retry_hours": float(_env("GA4_RETRY_HOURS", "3")),     # wait after a failed fetch
        "ga4_refetch_days": int(_env("GA4_REFETCH_DAYS", "14")),    # recent days re-pulled: Firebase adds data up to
                                                                    # ~7 days late, 14 re-reads each day to its end
        "ga4_late_days": int(_env("GA4_LATE_DAYS", "7")),           # the newest 7 days are PROVISIONAL (can still
                                                                    # grow): no "good news" alert from them
        "ga4_rebuild_days": int(_env("GA4_REBUILD_DAYS", "28")),    # full self-healing re-pull every ~4 weeks
        "ga4_max_history_days": int(_env("GA4_MAX_HISTORY_DAYS", "1300")),
        "ga4_run_budget_sec": int(_env("GA4_RUN_BUDGET_SEC", "900")),     # stop starting new apps after this
        "ga4_streams_ttl_hours": float(_env("GA4_STREAMS_TTL_HOURS", "168")),   # re-list GA4 streams weekly
        "ga4_active": _env("GA4_ACTIVE", "true").lower() == "true",    # the Active users tab (off: nothing of it
                                                                        # is read, written or printed)
        # the day the GA4 properties' data retention went from 2 to 14 months: a return-data edge 45–100 days before it
        # is said to be that ("none" or any non-date: the reason is never claimed)
        "ga4_retention_changed": _env("GA4_RETENTION_CHANGED", "2026-09-26"),
        # the 💸 Install value tab (SPEC_AB_FINAL §3.4). GA4_IDAY: the install-day GA4 fetch (Q-B / Q-C / Q-T) that
        # feeds it; GA4_VALUE: its engine, lazy files and dashboard key (off: nothing of it is read, written or
        # printed — and nothing is while no app has install-day data yet). Both off until their rollout step
        # (spec §6: 1 = the fetch, 3 = the tab, after the alert replay); refresh.yml passes the repo variables.
        "ga4_iday": _env("GA4_IDAY", "false").lower() == "true",       # rollout step 1 switches it on
        "ga4_value": _env("GA4_VALUE", "false").lower() == "true",     # rollout step 3 switches it on
        "impact_windows": _env("IMPACT_WINDOWS", "true").lower() == "true",  # the update card's 14 / 30 / 60-day
                                                                        # windows + late alerts (off: the 7-day card only)
        # 📦 compare any date: the update card for every day of the last year, precomputed (impact_any_<key>.json.gz;
        # never an alert) — off: none of its files, the site as without it
        "impact_any": _env("IMPACT_ANY", "true").lower() == "true",
        "impact_any_budget_sec": _int_env(("IMPACT_ANY_BUDGET_SEC",), 150),   # its computing per build at most
        "impact_any_workers": _int_env(("IMPACT_ANY_WORKERS",), 2),   # apps rebuilt side by side (0: in the build's
                                                                        # own process; the same files either way)
        # 🧭 Uninstall Studio: the Uninstall tab's All-apps view (uninstall_studio.json.gz, one lazy file; never an alert)
        # — off: no file, no pointer, the tab's older All-apps views exactly as before (a rollback without a code push)
        "uninstall_studio": _env("UNINSTALL_STUDIO", "true").lower() == "true",
        # 🧭 Active users Studio: the Active users tab's All-apps view (active_studio.json.gz, one lazy file; never an
        # alert) — off: no file, no pointer, the tab's older All-apps views exactly as before (a rollback without a code push)
        "active_studio": _env("ACTIVE_STUDIO", "true").lower() == "true",
        # 💸 Install value Studio: the Install value tab's All-apps view (value_studio.json.gz, one lazy file; never an
        # alert) — off: no file, no pointer, the tab's older All-apps views exactly as before (a rollback without a push)
        "value_studio": _env("VALUE_STUDIO", "true").lower() == "true",
        # 👥 Audience tab: who still has each app, who opens it, who went quiet and for how many months (audience.json.gz,
        # one lazy file; never an alert) — off: no file, no pointer, the page without the tab (a rollback without a push)
        "audience_tab": _env("AUDIENCE_TAB", "true").lower() == "true",
        # 🆕 First open tab: first_open → Splash → Home (and Language / Permission / Intro) per app per day, the strict GA4
        # funnel kept for good by fetch.ga4_firstopen (firstopen.json.gz, one lazy file) — off: no file, no pointer
        "firstopen_tab": _env("FIRSTOPEN_TAB", "true").lower() == "true",
        # 🗂 Review Studio: the Review tab's Studio (review/studio/<day>.json.gz, one lazy file per review day, frozen with
        # that day's cards; never an alert) — off: no file, no pointer, the older Review tab exactly as before
        "review_studio": _env("REVIEW_STUDIO", "true").lower() == "true",
        # every change split into "installs ki wajah se" / "asli badlaav" (SPEC_SPLIT): off → no split anywhere, no
        # Telegram tail, the page as before (a rollback without a code push)
        "split": _env("SPLIT", "true").lower() == "true",
        "value_payback_days": _int_env(("VALUE_PAYBACK_DAYS", "VALUE_TARGET_DAYS"), 90),  # H: 30/60/90/180/365
        "value_iap": _env("VALUE_IAP", "false").lower() == "true",      # in-app purchases in "money back"
        "value_cpi": _env("VALUE_CPI", "blended"),                      # the main cost per install
        "value_deduct": _env("VALUE_DEDUCT", "true").lower() == "true", # a per-app deduction rate, when one exists
        "gads_geo": _env("GADS_GEO", "false").lower() == "true",        # Google Ads cost by country (after the probe)
        # 🗄 Google Ads archive (fetch.gads_archive, private data/ only, never shown): the daily settings + change-history
        # archive (ads_archive/), the rows per campaign × day (ads_campaign_day/), spend by hour (ads_hourly/) and, with
        # GADS_GEO, country × day (ads_geo_day/). Off: nothing of it is asked, written or printed; no existing number moves
        "gads_archive": _env("GADS_ARCHIVE", "false").lower() == "true",
        # the Install value tab's C (new users by app version) and D (long-term by install month) — no new GA4 call,
        # both read the install-day files; off: nothing of them is computed, written or shown (SPEC_CD_GEO §S.1)
        "value_cd": _env("VALUE_CD", "false").lower() == "true",
        "iday_max_calls": _int_env(("IDAY_MAX_CALLS",), 120),           # install-day GA4 calls per app fetch
        "iday_cty_days": _int_env(("IDAY_CTY_DAYS",), 400),             # how far back countries are read
        # the install-day fetch, extended (fetch.ga4_iday_ext; only with GA4_IDAY): Q-C read in full, late ages 91-427,
        # paid vs organic, ad units by install age, app_remove by country — new files only, every existing cell as it
        # was. IDAY_EXT=false: exactly the fetch without it (its files kept as they are)
        "iday_ext": _env("IDAY_EXT", "true").lower() == "true",
        # 👥 Audience: GA4 active users by install day over the trailing 1, 2, 3 … month windows (fetch.ga4_audience;
        # engine.audience turns them into dead users by months since their last open). Off: nothing of it is read,
        # written or printed. GA4_AUDIENCE_BUDGET_SEC = its own seconds per build (no app is started past it)
        "ga4_audience": _env("GA4_AUDIENCE", "false").lower() == "true",
        "ga4_audience_budget_sec": _int_env(("GA4_AUDIENCE_BUDGET_SEC",), 180),
        # 🆕 First open: GA4 funnel reads (fetch.ga4_firstopen: the screens weekly, a one-time backfill of what GA4 still
        # has, the last 15 days every 6 hours). Off: nothing of it is read, written or printed
        "ga4_firstopen": _env("GA4_FIRSTOPEN", "false").lower() == "true",
        "ga4_firstopen_budget_sec": _int_env(("GA4_FIRSTOPEN_BUDGET_SEC",), 150),
        # 🆕 First open BY COUNTRY: the same strict funnel per country per day, every country (fetch.ga4_firstopen_cc:
        # the backfill of what GA4 still has, the last 3 days every 6 hours). Off: nothing of it is read, written or
        # printed; GA4_FIRSTOPEN_CC_BUDGET_SEC = its own seconds per build (unset: 0 → the module's BUDGET_SEC)
        "ga4_firstopen_cc": _env("GA4_FIRSTOPEN_CC", "false").lower() == "true",
        "ga4_firstopen_cc_budget_sec": _int_env(("GA4_FIRSTOPEN_CC_BUDGET_SEC",), 0),
        # 📈 Day-wise ROI: every day 0 … 30 of each install day's GA4 ad revenue (fetch.ga4_cohort: a one-time backfill
        # from the GA4 history start, the last 35 days every 6 hours). Off: nothing of it is read, written or printed
        "ga4_cohort": _env("GA4_COHORT", "false").lower() == "true",
        "ga4_cohort_budget_sec": _int_env(("GA4_COHORT_BUDGET_SEC",), 150),
        # 🧊 The cohort cube: GA4 ad revenue by activity day × install day × country from the GA4 history start
        # (fetch.ga4_cube: final days folded once into activity-month files, the last 3 days every 6 hours) — the ROI
        # section's 30-day columns past D30 (D60, D90 … up to the app's age). Off: nothing of it is read, written or
        # printed, and the ROI build leaves its store unread (the page's file exactly as without it).
        # GA4_CUBE_BUDGET_SEC = its own seconds per build (no read is started past it)
        "ga4_cube": _env("GA4_CUBE", "false").lower() == "true",
        "ga4_cube_budget_sec": _int_env(("GA4_CUBE_BUDGET_SEC",), 150),
        # 📈 ROI in the Install value tab (roi_<key>.json.gz + roi.json.gz): day-wise ROI, countries keep / cut,
        # lifetime P/L — off: no file, no pointer (the tab exactly as before)
        "roi_tab": _env("ROI_TAB", "true").lower() == "true",
    }


def _int_env(names, default):
    """The first of `names` set to an integer (else `default`) — a bad value never breaks the build."""
    for n in names:
        v = _env(n)
        if v:
            try:
                return int(v)
            except ValueError:
                pass
    return default


def load_accounts(path: str = "config/accounts.yaml") -> list:
    if not os.path.exists(path):
        return [{"account_id": "pub-mock", "label": "Mock", "refresh_token": None}]
    import yaml
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("accounts", [])
