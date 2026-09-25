"""One-time OAuth consent → refresh token.

    python -m admob_iq.fetch.authorize                                  # AdMob (prints the token)
    python -m admob_iq.fetch.authorize --ga4 --save-secret GA4_REFRESH_TOKEN

Opens a browser, you consent with the Google account, and you get a refresh token.

--ga4          asks for Google Analytics READ-ONLY access (analytics.readonly) instead of AdMob.
               One token then reads every GA4/Firebase property that Google account can see.
--save-secret  never prints the token: it is verified, encrypted and written straight into this
               repo's GitHub Actions secret NAME (the data-fetch job runs in GitHub Actions; the
               Cloudflare Worker only triggers it), using your local git login for GitHub.

Client ID/secret come from GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET, or are asked for (the secret
is typed hidden). Publish your OAuth consent screen first, or the refresh token expires in 7 days.
"""

import argparse
import base64
import getpass
import json
import os
import re
import subprocess
import sys

ADMOB_SCOPES = ["https://www.googleapis.com/auth/admob.report"]
GA4_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
SCOPES = ADMOB_SCOPES                    # back-compat for anything importing SCOPES


def _client():
    cid = os.environ.get("GOOGLE_CLIENT_ID") or input("OAuth Client ID (…apps.googleusercontent.com): ").strip()
    csec = os.environ.get("GOOGLE_CLIENT_SECRET") or getpass.getpass("OAuth Client secret (hidden, paste + Enter): ").strip()
    if not cid.endswith(".apps.googleusercontent.com") or not csec:
        sys.exit("Client ID/secret missing or malformed — copy them from Google Cloud → APIs & Services → Credentials.")
    return cid, csec


def _consent(cid, csec, scopes):
    from google_auth_oauthlib.flow import InstalledAppFlow
    config = {"installed": {
        "client_id": cid, "client_secret": csec,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }}
    flow = InstalledAppFlow.from_client_config(config, scopes)
    # prompt=consent makes Google return a refresh token even if this account consented before
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not creds.refresh_token:
        sys.exit("Google returned no refresh token — run again and click Allow.")
    return creds


def ga4_visible_counts(access_token):
    """(accounts, properties) this token can read via the GA4 Admin API. Raises RuntimeError on API errors."""
    import requests
    h = {"Authorization": "Bearer " + access_token}
    accounts = properties = 0
    page = None
    while True:
        params = {"pageSize": 200}
        if page:
            params["pageToken"] = page
        r = requests.get("https://analyticsadmin.googleapis.com/v1beta/accountSummaries",
                         headers=h, params=params, timeout=30)
        if r.status_code != 200:
            raise RuntimeError("HTTP %s %s" % (r.status_code, r.text[:300]))
        j = r.json()
        for a in j.get("accountSummaries", []):
            accounts += 1
            properties += len(a.get("propertySummaries", []))
        page = j.get("nextPageToken")
        if not page:
            return accounts, properties


def _ga4_selfcheck(creds):
    """Prove the token works BEFORE saving it. Prints only counts — never names, ids or the token."""
    try:
        accounts, properties = ga4_visible_counts(creds.token)
    except RuntimeError as e:
        m = str(e)
        if "has not been used" in m or "is disabled" in m or "SERVICE_DISABLED" in m:
            sys.exit("❌ 'Google Analytics Admin API' is not enabled in this Google Cloud project. "
                     "Enable it (APIs & Services → Library) and run this again.")
        sys.exit("❌ GA4 check failed: %s" % m)
    if not properties:
        sys.exit("❌ Token works but this Google account sees NO GA4 properties. "
                 "Log in with the Gmail that owns the Firebase projects.")
    print("✅ Token works: %d GA4 account(s), %d propert(y/ies) visible." % (accounts, properties))


def _repo_slug():
    url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
    if not m:
        sys.exit("Could not find the GitHub repo from `git remote get-url origin`.")
    return m.group(1)


def _github_token():
    out = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                         capture_output=True, text=True).stdout
    tok = next((l.split("=", 1)[1] for l in out.splitlines() if l.startswith("password=")), "")
    if not tok:
        sys.exit("No GitHub login found in git credentials — cannot save the secret.")
    return tok


def save_github_secret(name, value, repo=None, gh_token=None):
    """Encrypt `value` with the repo's Actions public key and PUT it as secret `name`. Never prints it."""
    import requests
    from nacl import encoding, public
    repo = repo or _repo_slug()
    h = {"Authorization": "token " + (gh_token or _github_token()),
         "Accept": "application/vnd.github+json", "User-Agent": "admob-iq-authorize"}
    pk = requests.get("https://api.github.com/repos/%s/actions/secrets/public-key" % repo, headers=h, timeout=30)
    if pk.status_code != 200:
        sys.exit("❌ Could not read the repo's secret key: HTTP %s" % pk.status_code)
    pk = pk.json()
    sealed = public.SealedBox(public.PublicKey(pk["key"].encode(), encoding.Base64Encoder())).encrypt(value.encode())
    r = requests.put("https://api.github.com/repos/%s/actions/secrets/%s" % (repo, name), headers=h, timeout=30,
                     data=json.dumps({"encrypted_value": base64.b64encode(sealed).decode(), "key_id": pk["key_id"]}))
    if r.status_code not in (201, 204):
        sys.exit("❌ Saving GitHub secret failed: HTTP %s" % r.status_code)
    return r.status_code


def main(argv=None):
    ap = argparse.ArgumentParser(description="One-time OAuth consent → refresh token")
    ap.add_argument("--ga4", action="store_true", help="Google Analytics read-only instead of AdMob")
    ap.add_argument("--save-secret", metavar="NAME",
                    help="write the token into this repo's GitHub Actions secret NAME (never printed)")
    a = ap.parse_args(argv)

    cid, csec = _client()
    creds = _consent(cid, csec, GA4_SCOPES if a.ga4 else ADMOB_SCOPES)
    if a.ga4:
        _ga4_selfcheck(creds)
    if a.save_secret:
        st = save_github_secret(a.save_secret, creds.refresh_token)
        print("✅ Saved to GitHub secret %s (%s). The token was never displayed."
              % (a.save_secret, "created" if st == 201 else "updated"))
    else:
        print("\nREFRESH TOKEN (store securely):\n", creds.refresh_token)


if __name__ == "__main__":
    main()
