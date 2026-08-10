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
    }


def load_accounts(path: str = "config/accounts.yaml") -> list:
    if not os.path.exists(path):
        return [{"account_id": "pub-mock", "label": "Mock", "refresh_token": None}]
    import yaml
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("accounts", [])
