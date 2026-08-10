-- AdMob IQ — PostgreSQL schema
-- Money is stored in MICROS (value / 1e6 = currency). Ratios (match_rate, ctr,
-- show_rate) are stored as fractions in [0,1]. eCPM is NOT stored; it is derived
-- (earnings/impressions*1000) — see engine/metrics.py.

CREATE TABLE IF NOT EXISTS accounts (
    account_id      TEXT PRIMARY KEY,            -- pub-XXXXXXXXXXXXXXXX
    label           TEXT NOT NULL,
    currency_code   TEXT NOT NULL DEFAULT 'USD',
    reporting_tz    TEXT NOT NULL DEFAULT 'America/Los_Angeles',
    refresh_token   TEXT,                        -- encrypted at rest (see notify/secrets)
    connected       BOOLEAN NOT NULL DEFAULT FALSE,
    last_sync_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS apps (
    app_id          TEXT PRIMARY KEY,            -- AdMob app id
    account_id      TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    platform        TEXT,                        -- Android / iOS
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ad_units (
    ad_unit_id      TEXT PRIMARY KEY,            -- ca-app-pub-.../...
    app_id          TEXT NOT NULL REFERENCES apps(app_id) ON DELETE CASCADE,
    name            TEXT,
    format          TEXT,                        -- banner/native/interstitial/rewarded/app_open
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---- Network daily facts (one row per dimension tuple per day) ----
CREATE TABLE IF NOT EXISTS network_daily (
    report_date               DATE   NOT NULL,
    account_id                TEXT   NOT NULL,
    app_id                    TEXT   NOT NULL,
    ad_unit_id                TEXT   NOT NULL,
    country                   TEXT   NOT NULL,   -- CLDR code
    format                    TEXT   NOT NULL,
    platform                  TEXT   NOT NULL,
    ad_requests               BIGINT NOT NULL DEFAULT 0,
    matched_requests          BIGINT NOT NULL DEFAULT 0,
    impressions               BIGINT NOT NULL DEFAULT 0,
    clicks                    BIGINT NOT NULL DEFAULT 0,
    estimated_earnings_micros BIGINT NOT NULL DEFAULT 0,
    impression_rpm_micros     BIGINT NOT NULL DEFAULT 0,
    match_rate                DOUBLE PRECISION,
    show_rate                 DOUBLE PRECISION,
    impression_ctr            DOUBLE PRECISION,
    currency_code             TEXT   NOT NULL DEFAULT 'USD',
    is_finalized              BOOLEAN NOT NULL DEFAULT FALSE,
    pulled_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (report_date, account_id, app_id, ad_unit_id, country, format, platform)
);
CREATE INDEX IF NOT EXISTS ix_net_date      ON network_daily (report_date);
CREATE INDEX IF NOT EXISTS ix_net_unit_date ON network_daily (ad_unit_id, report_date);
CREATE INDEX IF NOT EXISTS ix_net_app_date  ON network_daily (app_id, report_date);

-- ---- Mediation daily facts (per ad source) ----
CREATE TABLE IF NOT EXISTS mediation_daily (
    report_date               DATE   NOT NULL,
    account_id                TEXT   NOT NULL,
    app_id                    TEXT   NOT NULL,
    ad_unit_id                TEXT   NOT NULL,
    ad_source                 TEXT   NOT NULL,   -- mediation-only
    mediation_group           TEXT   NOT NULL DEFAULT '',
    country                   TEXT   NOT NULL,
    format                    TEXT   NOT NULL,
    platform                  TEXT   NOT NULL,
    ad_requests               BIGINT NOT NULL DEFAULT 0,
    matched_requests          BIGINT NOT NULL DEFAULT 0,
    impressions               BIGINT NOT NULL DEFAULT 0,
    clicks                    BIGINT NOT NULL DEFAULT 0,
    estimated_earnings_micros BIGINT NOT NULL DEFAULT 0,
    observed_ecpm_micros      BIGINT NOT NULL DEFAULT 0,   -- third-party estimate
    match_rate                DOUBLE PRECISION,
    impression_ctr            DOUBLE PRECISION,
    currency_code             TEXT   NOT NULL DEFAULT 'USD',
    is_finalized              BOOLEAN NOT NULL DEFAULT FALSE,
    pulled_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (report_date, account_id, app_id, ad_unit_id, ad_source, mediation_group, country, format, platform)
);
CREATE INDEX IF NOT EXISTS ix_med_date       ON mediation_daily (report_date);
CREATE INDEX IF NOT EXISTS ix_med_source     ON mediation_daily (ad_source, report_date);

-- ---- Earnings snapshots (APPEND-ONLY) — revenue-deduction / decay tracking ----
-- Every pull writes a fresh row so we can see day D's estimate change over time:
-- D+1 = $100 -> D+3 = $88 -> finalized $80.
CREATE TABLE IF NOT EXISTS earnings_snapshots (
    snapshot_id               BIGSERIAL PRIMARY KEY,
    report_date               DATE   NOT NULL,   -- the day the revenue is FOR
    snapshot_date             DATE   NOT NULL,   -- the day we captured it
    account_id                TEXT   NOT NULL,
    app_id                    TEXT   NOT NULL,
    ad_unit_id                TEXT   NOT NULL,
    country                   TEXT   NOT NULL,
    format                    TEXT   NOT NULL,
    estimated_earnings_micros BIGINT NOT NULL DEFAULT 0,
    impressions               BIGINT NOT NULL DEFAULT 0,
    clicks                    BIGINT NOT NULL DEFAULT 0,
    pulled_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_date, snapshot_date, account_id, app_id, ad_unit_id, country, format)
);
CREATE INDEX IF NOT EXISTS ix_snap_key ON earnings_snapshots (ad_unit_id, country, report_date, snapshot_date);

-- ---- Alerts ----
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id     TEXT PRIMARY KEY,
    metric      TEXT NOT NULL,          -- requests/match_rate/show_rate/ctr/revenue/ecpm
    kind        TEXT NOT NULL,          -- zero / drop_pct / drop_pt / spike_x / improve_pct
    threshold   DOUBLE PRECISION,       -- e.g. 0.40 for 40%, 20 for 20pt, 3 for 3x
    severity    TEXT NOT NULL,          -- critical / warning / watch / good
    enabled     BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id     BIGSERIAL PRIMARY KEY,
    fingerprint  TEXT NOT NULL,         -- dedupe key (placement+metric+geo+kind+day)
    severity     TEXT NOT NULL,         -- critical/warning/watch/good
    metric       TEXT NOT NULL,
    account_id   TEXT,
    app_id       TEXT,
    ad_unit_id   TEXT,
    country      TEXT,                  -- NULL/'ALL' = global; else localized geo
    localized    BOOLEAN NOT NULL DEFAULT FALSE,
    current_val  DOUBLE PRECISION,
    baseline_val DOUBLE PRECISION,
    change_pct   DOUBLE PRECISION,
    message      TEXT,
    cause        TEXT,
    status       TEXT NOT NULL DEFAULT 'active',  -- active/acknowledged/snoozed/resolved
    snoozed_until TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_alert_status ON alerts (status, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS ux_alert_fp_open ON alerts (fingerprint) WHERE status = 'active';

-- ---- Load audit (observability) ----
CREATE TABLE IF NOT EXISTS load_audit (
    run_id        BIGSERIAL PRIMARY KEY,
    report_type   TEXT NOT NULL,       -- network / mediation
    account_id    TEXT,
    date_start    DATE,
    date_end      DATE,
    rows_returned INT,
    matching_rows INT,
    status        TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);
