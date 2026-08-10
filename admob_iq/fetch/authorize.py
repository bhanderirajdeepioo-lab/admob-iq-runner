"""One-time OAuth: run locally per AdMob account to get a refresh token.

    python -m admob_iq.fetch.authorize

Opens a browser, you consent with the Google account that owns the AdMob account,
and it prints the refresh token to paste into config/accounts.yaml (or the DB).
Publish your OAuth consent screen first, or the refresh token expires in 7 days.
"""

import os

SCOPES = ["https://www.googleapis.com/auth/admob.report"]


def main():
    from google_auth_oauthlib.flow import InstalledAppFlow
    client_id = os.environ["GOOGLE_CLIENT_ID"]
    client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
    config = {"installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }}
    flow = InstalledAppFlow.from_client_config(config, SCOPES)
    creds = flow.run_local_server(port=0)
    print("\nREFRESH TOKEN (store securely):\n", creds.refresh_token)


if __name__ == "__main__":
    main()
