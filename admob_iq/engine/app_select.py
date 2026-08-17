"""Per-account APP selection — which apps the user wants shown (and, in Phase B, fetched).

Stored in config/selected_apps.json (git-committed, editable from the dashboard via the GitHub API,
same mechanism as approved_ranges). Shape:

  {"accounts": {
     "<account_id>": {"decided": true, "selected": ["<app_id>", ...]}
  }}

Rules (backward compatible — an absent/empty file changes NOTHING):
  * account NOT in the file, or "decided" false  -> UNDECIDED: every app visible (and fetched as
    today). The existing account keeps working untouched until the user actually picks.
  * "decided": true  -> only the app_ids in "selected" are visible (and, Phase B, fetched); the rest
    are hidden. Already-fetched data is never deleted, so re-ticking an app brings it right back.
"""

import json
import os


def load_selection(path):
    """Read selected_apps.json (or an empty set if absent/broken — never crash the build)."""
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("accounts", {})
            return data
        except Exception:
            pass
    return {"accounts": {}}


def _acct(sel, account_id):
    return (sel.get("accounts") or {}).get(account_id or "") or {}


def account_decided(sel, account_id):
    """Has the user made an explicit app selection for this account?"""
    a = _acct(sel, account_id)
    return bool(a.get("decided"))


def selected_ids(sel, account_id):
    """The set of app_ids kept for a DECIDED account (empty set = none), or None if undecided."""
    a = _acct(sel, account_id)
    if not a.get("decided"):
        return None
    return set(a.get("selected") or [])


def load_known_accounts(path):
    """Set of GRANDFATHERED account_ids (the accounts that existed when opt-in was enabled). Returns
    None if the file is absent -> opt-in disabled, every undecided app visible (backward compatible).
    When present, a brand-NEW account (not in this set, still undecided) defaults to HIDDEN, so adding
    an account can't auto-pull all its apps and bloat the build — the user opts its apps in."""
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            ids = data.get("accounts") if isinstance(data, dict) else data
            return set(ids or [])
        except Exception:
            pass
    return None


def app_visible(sel, account_id, app_id, known=None):
    """True if this app should be shown/fetched.
      - DECIDED account   -> only its selected app_ids.
      - UNDECIDED account -> visible if it's a grandfathered (known) account; a brand-NEW account
        (not in `known`) defaults to HIDDEN (opt-in). `known=None` disables this and keeps every
        undecided app visible (backward compatible — no known-accounts file)."""
    ids = selected_ids(sel, account_id)
    if ids is not None:
        return app_id in ids
    if known is None:                       # opt-in disabled -> undecided means every app visible
        return True
    return (account_id or "") in known      # undecided: only grandfathered accounts stay visible
