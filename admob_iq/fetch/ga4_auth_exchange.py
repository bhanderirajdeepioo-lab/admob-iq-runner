"""Server-side half of the GA4 consent, run by .github/workflows/ga4-auth.yml.

Lets the owner authorize GA4 without anyone ever seeing the OAuth client secret: the secret stays in
GitHub Actions secrets, and only a one-time authorization code travels (as a GitHub secret, never
printed). This repo's Actions logs are PUBLIC — print only generic status and counts.

  MODE=client-id  store GA4_CLIENT_ID (else GOOGLE_CLIENT_ID) — public by nature, it appears in every consent
                  URL — in the PRIVATE repo at ga4/oauth_client_id.txt, so the consent URL uses that very client.
  MODE=exchange   swap secret GA4_AUTH_CODE (+ REDIRECT_URI) for a refresh token with that same client, add it
                  to GA4_REFRESH_TOKENS under the consenting email, save that + GA4_REFRESH_TOKEN (latest token,
                  back-compat) + GA4_CLIENT_ID/SECRET as Actions secrets, delete GA4_AUTH_CODE, prove it reads GA4,
                  and write ga4/auth_status.json privately (counts + owner emails).

GA4_REFRESH_TOKENS is JSON {owner email: refresh_token}: the apps' GA4 accounts belong to several Google accounts,
so each one consents once and the probe reads with all of them. Each run adds or replaces ONE owner's entry.
"""

import base64
import json
import os
import sys
import time

import requests

from admob_iq.fetch.authorize import ga4_visible_counts, save_github_secret
from admob_iq.fetch.ga4 import parse_token_map


def _put_private_file(path, text, message):
    repo, tok = os.environ["DATA_REPO"], os.environ["DATA_REPO_TOKEN"]
    url = "https://api.github.com/repos/%s/contents/%s" % (repo, path)
    h = {"Authorization": "token " + tok, "Accept": "application/vnd.github+json", "User-Agent": "admob-iq-ga4-auth"}
    for _ in range(3):                         # the refresh job may commit in between → retry on sha race
        cur = requests.get(url, headers=h, timeout=30)
        body = {"message": message, "content": base64.b64encode(text.encode()).decode()}
        if cur.status_code == 200:
            body["sha"] = cur.json()["sha"]
        r = requests.put(url, headers=h, data=json.dumps(body), timeout=30)
        if r.status_code in (200, 201):
            return
        time.sleep(3)
    sys.exit("private repo write failed (HTTP %s)" % r.status_code)


def _consented_as(tok_response):
    """Email of the Google account that clicked Allow (from the id_token, present when the consent URL asked for
    `openid email`). Goes only to the PRIVATE status file — never to this public log."""
    idt = tok_response.get("id_token", "")
    try:
        payload = idt.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("email", "")
    except (IndexError, ValueError):
        return ""


def _mask(*values):
    """Tell Actions to redact these values from the log. GitHub masks each secret as a WHOLE, so a single token
    inside the GA4_REFRESH_TOKENS JSON would otherwise print in the clear if anything ever echoed it."""
    for v in values:
        if v:
            print("::add-mask::" + v)


def merge_owner_token(stored, legacy, who, refresh_token, now=None):
    """→ the new {owner: refresh_token} map: `stored` plus this consent, added or replacing that owner's old
    token. Keyed by the consenting email ("unknown-<UTC time>" when Google sent none). The single-token
    GA4_REFRESH_TOKEN (`legacy`) is about to be overwritten with this token and its owner's email was never
    recorded, so when the map does not hold it yet it is kept as "legacy" — never silently lost."""
    owners = dict(stored)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", now or time.gmtime())
    if legacy and legacy != refresh_token and legacy not in owners.values():
        owners["legacy" if "legacy" not in owners else "legacy-" + stamp] = legacy
    owners[(who or "").strip().lower() or "unknown-" + stamp] = refresh_token
    return owners


def _delete_secret(name, repo, tok):
    requests.delete("https://api.github.com/repos/%s/actions/secrets/%s" % (repo, name), timeout=30,
                    headers={"Authorization": "token " + tok, "Accept": "application/vnd.github+json"})


def main():
    mode = os.environ.get("MODE", "")
    # Prefer the dedicated GA4 client (Internal/External Desktop app) once it exists; the AdMob client is the fallback.
    cid = os.environ.get("GA4_CLIENT_ID") or os.environ.get("GOOGLE_CLIENT_ID", "")
    csec = os.environ.get("GA4_CLIENT_SECRET") or os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not cid or not csec:
        sys.exit("GA4_CLIENT_ID/SECRET (or GOOGLE_CLIENT_ID/SECRET) secrets are missing")

    if mode == "client-id":
        _put_private_file("ga4/oauth_client_id.txt", cid + "\n", "ga4 auth: oauth client id")
        print("client id stored in the private repo")
        return

    if mode != "exchange":
        sys.exit("MODE must be client-id or exchange")
    repo, gh = os.environ["REPO"], os.environ["DATA_REPO_TOKEN"]
    stored, map_problems = parse_token_map(os.environ.get("GA4_REFRESH_TOKENS"))
    legacy = os.environ.get("GA4_REFRESH_TOKEN", "").strip()
    _mask(legacy, *stored.values())                      # before anything else can print
    code, redirect = os.environ.get("GA4_AUTH_CODE", ""), os.environ.get("REDIRECT_URI", "")
    if not code or not redirect:
        sys.exit("GA4_AUTH_CODE secret or REDIRECT_URI input is missing")
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "code": code, "client_id": cid, "client_secret": csec,
        "redirect_uri": redirect, "grant_type": "authorization_code"})
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    _mask(j.get("refresh_token"), j.get("access_token"))  # belt and braces: never let them reach the log
    _delete_secret("GA4_AUTH_CODE", repo, gh)            # one-time code: useless now either way
    if r.status_code != 200 or not j.get("refresh_token"):
        err = j.get("error", "HTTP %s" % r.status_code)  # e.g. invalid_grant — a code, not a secret
        _put_private_file("ga4/auth_status.json", json.dumps({"ok": False, "error": err,
                          "detail": j.get("error_description", "")}), "ga4 auth: failed")
        sys.exit("token exchange failed: %s" % err)
    who = _consented_as(j)
    owners = merge_owner_token(stored, legacy, who, j["refresh_token"])
    # Save FIRST: the token is valid even if the GA4 APIs aren't enabled yet, so enabling them later
    # must not force the owner to click Allow again.
    save_github_secret("GA4_REFRESH_TOKENS", json.dumps(owners, sort_keys=True), repo=repo, gh_token=gh)
    save_github_secret("GA4_REFRESH_TOKEN", j["refresh_token"], repo=repo, gh_token=gh)   # latest: back-compat
    save_github_secret("GA4_CLIENT_ID", cid, repo=repo, gh_token=gh)
    save_github_secret("GA4_CLIENT_SECRET", csec, repo=repo, gh_token=gh)
    if map_problems:
        print("::warning::%d unreadable GA4_REFRESH_TOKENS entr(y/ies) were dropped" % map_problems)
    # counts below are THIS consent's; "owners" lists every Google account with a stored token
    status = {"consented_as": who, "owners": sorted(owners), "token_map_problems": map_problems,
              "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        accounts, properties = ga4_visible_counts(j["access_token"])
    except RuntimeError as e:
        msg = str(e)
        hint = "admin_api_disabled" if ("SERVICE_DISABLED" in msg or "has not been used" in msg) else "ga4_check_failed"
        _put_private_file("ga4/auth_status.json", json.dumps(dict(status, ok=False, token_saved=True, error=hint,
                          detail=msg[:300])), "ga4 auth: token saved, check failed")
        sys.exit("GA4 token saved (%d owner token(s) stored), but the check failed: %s (details in the private repo)"
                 % (len(owners), hint))
    _put_private_file("ga4/auth_status.json", json.dumps(dict(status, ok=True, accounts=accounts,
                      properties=properties)), "ga4 auth: ok")
    print("GA4 token saved: %d account(s), %d propert(y/ies) visible; %d owner token(s) stored"
          % (accounts, properties, len(owners)))


if __name__ == "__main__":
    main()
