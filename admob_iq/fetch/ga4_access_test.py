"""One-off check, run by .github/workflows/ga4-access-test.yml: can the GA4 token read a property it does
not see in accountSummaries (e.g. access inherited from a Firebase project role)?

The property ids to try live in the PRIVATE repo at ga4/test_properties.txt (one per line), never in this
public repo or its logs. The public log prints only HTTP status + error status per call (no ids, no numbers);
full detail goes to the private repo at ga4/access_test.json.
"""

import json
import os
import sys
import time

import requests

from admob_iq.fetch.ga4_auth_exchange import _put_private_file


def _private_text(path):
    r = requests.get("https://api.github.com/repos/%s/contents/%s" % (os.environ["DATA_REPO"], path), timeout=30,
                     headers={"Authorization": "token " + os.environ["DATA_REPO_TOKEN"],
                              "Accept": "application/vnd.github.raw", "User-Agent": "admob-iq-ga4-test"})
    if r.status_code != 200:
        sys.exit("could not read %s from the private repo (HTTP %s)" % (path, r.status_code))
    return r.text


def _access_token():
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "client_id": os.environ["GA4_CLIENT_ID"], "client_secret": os.environ["GA4_CLIENT_SECRET"],
        "refresh_token": os.environ["GA4_REFRESH_TOKEN"], "grant_type": "refresh_token"})
    if r.status_code != 200:
        sys.exit("token refresh failed: %s" % r.json().get("error", r.status_code))
    tok = r.json()["access_token"]
    print("::add-mask::" + tok)
    return tok


def _call(method, url, tok, body=None):
    r = requests.request(method, url, headers={"Authorization": "Bearer " + tok}, json=body, timeout=60)
    err = {}
    if r.status_code != 200:
        try:
            err = r.json().get("error", {})
        except ValueError:
            pass
    rows = None
    if r.status_code == 200 and "runReport" in url:
        rows = int(r.json().get("rowCount") or 0)
    return {"http": r.status_code, "status": err.get("status", ""), "message": (err.get("message") or "")[:300],
            "rows": rows}


def main():
    tok = _access_token()
    props = [p.strip() for p in _private_text("ga4/test_properties.txt").splitlines() if p.strip().isdigit()]
    out = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "properties": {}}
    s = _call("GET", "https://analyticsadmin.googleapis.com/v1beta/accountSummaries?pageSize=200", tok)
    print("accountSummaries: HTTP %s" % s["http"])
    for n, pid in enumerate(props, 1):
        res = {
            "admin_get_property": _call("GET", "https://analyticsadmin.googleapis.com/v1beta/properties/%s" % pid, tok),
            "data_metadata": _call("GET", "https://analyticsdata.googleapis.com/v1beta/properties/%s/metadata" % pid, tok),
            "data_runReport": _call("POST", "https://analyticsdata.googleapis.com/v1beta/properties/%s:runReport" % pid, tok,
                                    {"dateRanges": [{"startDate": "7daysAgo", "endDate": "yesterday"}],
                                     "dimensions": [{"name": "eventName"}], "metrics": [{"name": "eventCount"}],
                                     "limit": 50}),
        }
        out["properties"][pid] = res
        # public log: status only — no id, no row counts
        print("property #%d: " % n + " | ".join("%s HTTP %s %s" % (k, v["http"], v["status"]) for k, v in res.items()))
    _put_private_file("ga4/access_test.json", json.dumps(out, indent=1), "ga4 access test")
    print("detail written to the private repo")


if __name__ == "__main__":
    main()
