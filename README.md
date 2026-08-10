# AdMob IQ — runner

Code-only runner for a self-hosted AdMob revenue-intelligence dashboard.

It pulls AdMob reporting (and, optionally, Google Ads campaign spend for ROAS),
computes the analysis, and writes a static dashboard.

## Why this repo holds no data

This repository contains **only source code**. It is deliberately public so the
scheduled job can use GitHub's free Actions minutes for public repositories.

All account data, reporting output, and configuration live in a **separate
private repository**. The workflow clones that private repo at runtime, builds,
and pushes the results back to it. Nothing from it is ever committed here.

Privacy measures in `.github/workflows/refresh.yml`:

- `data/`, `site/`, and `config/*.json` are git-ignored here and are never
  committed to this repository.
- The workflow has `permissions: contents: read` — it cannot write to this repo.
- Build output is written to a file rather than the job log, because Actions logs
  on a public repository are world-readable. On failure only the tail is shown,
  with long digit runs masked.
- No build artifacts are uploaded.

Credentials are stored as GitHub Actions secrets. GitHub does not expose secrets
to forks or pull requests, and this workflow runs only on a schedule or a manual
run started by someone with write access.

## Setup

See `SETUP-GUIDE.md`.

## Layout

    admob_iq/      analysis engine, AdMob + Google Ads fetchers, static builder
    frontend/      dashboard UI (single self-contained HTML file)
    config/        example config only; real config lives in the private repo
