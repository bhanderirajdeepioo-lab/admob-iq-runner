"""Server-side half of the GA4 consent, run by .github/workflows/ga4-auth.yml.

Lets the owner authorize GA4 without anyone ever seeing the OAuth client secret: the secret stays in
GitHub Actions secrets, and only a one-time authorization code travels (as a GitHub secret, never
printed). This repo's Actions logs are PUBLIC — print only generic status and counts.

  MODE=client-id  store GOOGLE_CLIENT_ID (public by nature: it appears in every consent URL) in the
                  PRIVATE repo at ga4/oauth_client_id.txt, so the consent URL uses the very same client.
  MODE=exchange   swap secret GA4_AUTH_CODE (+ REDIRECT_URI) for a refresh token with GOOGLE_CLIENT_ID/
                  SECRET, prove it reads GA4, save GA4_REFRESH_TOKEN + GA4_CLIENT_ID/SECRET as Actions
                  secrets, delete GA4_AUTH_CODE, and write counts-only ga4/auth_status.json privately.
"""

import base64
import json
import os
import sys
import time

import requests

from admob_iq.fetch.authorize import ga4_visible_counts, save_github_secret


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


def _delete_secret(name, repo, tok):
    requests.delete("https://api.github.com/repos/%s/actions/secrets/%s" % (repo, name), timeout=30,
                    headers={"Authorization": "token " + tok, "Accept": "application/vnd.github+json"})


def main():
    mode = os.environ.get("MODE", "")
    cid, csec = os.environ.get("GOOGLE_CLIENT_ID", ""), os.environ.get("GOOGLE_CLIENT_SECRET", "")
    if not cid or not csec:
        sys.exit("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET secrets are missing")

    if mode == "client-id":
        _put_private_file("ga4/oauth_client_id.txt", cid + "\n", "ga4 auth: oauth client id")
        print("client id stored in the private repo")
        return

    if mode != "exchange":
        sys.exit("MODE must be client-id or exchange")
    repo, gh = os.environ["REPO"], os.environ["DATA_REPO_TOKEN"]
    code, redirect = os.environ.get("GA4_AUTH_CODE", ""), os.environ.get("REDIRECT_URI", "")
    if not code or not redirect:
        sys.exit("GA4_AUTH_CODE secret or REDIRECT_URI input is missing")
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "code": code, "client_id": cid, "client_secret": csec,
        "redirect_uri": redirect, "grant_type": "authorization_code"})
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    _delete_secret("GA4_AUTH_CODE", repo, gh)            # one-time code: useless now either way
    if r.status_code != 200 or not j.get("refresh_token"):
        err = j.get("error", "HTTP %s" % r.status_code)  # e.g. invalid_grant — a code, not a secret
        _put_private_file("ga4/auth_status.json", json.dumps({"ok": False, "error": err,
                          "detail": j.get("error_description", "")}), "ga4 auth: failed")
        sys.exit("token exchange failed: %s" % err)
    print("::add-mask::" + j["refresh_token"])            # belt and braces: never let it reach the log
    print("::add-mask::" + j.get("access_token", ""))
    try:
        accounts, properties = ga4_visible_counts(j["access_token"])
    except RuntimeError as e:
        msg = str(e)
        hint = "admin_api_disabled" if ("SERVICE_DISABLED" in msg or "has not been used" in msg) else "ga4_check_failed"
        _put_private_file("ga4/auth_status.json", json.dumps({"ok": False, "error": hint, "detail": msg[:300]}),
                          "ga4 auth: check failed")
        sys.exit("GA4 check failed: %s (details in the private repo)" % hint)
    save_github_secret("GA4_REFRESH_TOKEN", j["refresh_token"], repo=repo, gh_token=gh)
    save_github_secret("GA4_CLIENT_ID", cid, repo=repo, gh_token=gh)
    save_github_secret("GA4_CLIENT_SECRET", csec, repo=repo, gh_token=gh)
    _put_private_file("ga4/auth_status.json", json.dumps({
        "ok": True, "accounts": accounts, "properties": properties,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}), "ga4 auth: ok")
    print("GA4 token saved: %d account(s), %d propert(y/ies) visible" % (accounts, properties))


if __name__ == "__main__":
    main()
