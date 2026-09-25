"""One-off, owner-requested: set Event data retention to 14 months on every GA4 property one owner account
can see. Run by .github/workflows/ga4-retention.yml, once per owner, right after that owner clicked Allow on
an analytics.edit consent.

Why: every property keeps event-level data only 2 months (the GA4 default). Reports that GA4 answers from
raw events — e.g. uninstalls split by install day on the big apps — then come back short for older days.
14 months keeps them answerable for longer. Nothing else is changed (updateMask = eventDataRetention only).

Safety: the analytics.edit token lives only in this job's memory — it is masked, used for this one setting
and never saved anywhere. The one-time code secret (GA4_EDIT_CODE) is deleted either way. This repo's logs
are PUBLIC: print counts only; per-property detail goes to the PRIVATE repo (ga4/retention_status.json).
"""

import json
import os
import sys
import time

import requests

from admob_iq.fetch import ga4
from admob_iq.fetch.ga4_auth_exchange import _consented_as, _delete_secret, _put_private_file

TARGET = "FOURTEEN_MONTHS"


def main():
    env = os.environ
    repo, gh = env["REPO"], env["DATA_REPO_TOKEN"]
    code, redirect = env.get("GA4_EDIT_CODE", ""), env.get("REDIRECT_URI", "")
    cid, csec = env.get("GA4_CLIENT_ID", ""), env.get("GA4_CLIENT_SECRET", "")
    if not (code and redirect and cid and csec):
        sys.exit("GA4_EDIT_CODE / REDIRECT_URI / GA4 client secrets missing")
    r = requests.post("https://oauth2.googleapis.com/token", timeout=30, data={
        "code": code, "client_id": cid, "client_secret": csec, "redirect_uri": redirect,
        "grant_type": "authorization_code"})
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    for t in (j.get("access_token"), j.get("refresh_token")):
        if t:
            print("::add-mask::" + t)
    _delete_secret("GA4_EDIT_CODE", repo, gh)            # one-time code: useless now either way
    if r.status_code != 200 or not j.get("access_token"):
        sys.exit("token exchange failed: %s" % j.get("error", "HTTP %s" % r.status_code))
    if "analytics.edit" not in (j.get("scope") or ""):
        sys.exit("the Allow did not grant analytics.edit — nothing changed")
    tok, who = j["access_token"], _consented_as(j)
    h = {"Authorization": "Bearer " + tok}
    props = ga4.list_properties(tok)
    res, n = {}, {"updated": 0, "already": 0, "failed": 0}
    for p in props:
        pid = p["property_id"]
        url = "%s/properties/%s/dataRetentionSettings" % (ga4.ADMIN, pid)
        cur = requests.get(url, headers=h, timeout=30)
        before = cur.json().get("eventDataRetention") if cur.status_code == 200 else None
        if before == TARGET:
            res[pid] = {"name": p.get("display_name"), "before": before, "after": before}
            n["already"] += 1
            continue
        up = requests.patch(url, headers=h, timeout=30, params={"updateMask": "eventDataRetention"},
                            json={"name": "properties/%s/dataRetentionSettings" % pid, "eventDataRetention": TARGET})
        ok = up.status_code == 200 and up.json().get("eventDataRetention") == TARGET
        res[pid] = {"name": p.get("display_name"), "before": before,
                    "after": up.json().get("eventDataRetention") if up.status_code == 200 else None,
                    "error": None if ok else up.text[:300]}
        n["updated" if ok else "failed"] += 1
        time.sleep(0.3)
    try:                                                  # merge with earlier owners' results
        old = requests.get("https://api.github.com/repos/%s/contents/ga4/retention_status.json" % env["DATA_REPO"],
                           headers={"Authorization": "token " + gh, "Accept": "application/vnd.github.raw"},
                           timeout=30).json()
    except Exception:
        old = {}
    old = old if isinstance(old, dict) else {}
    old[who or "unknown"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "counts": n,
                             "properties": res}
    _put_private_file("ga4/retention_status.json", json.dumps(old, indent=1, sort_keys=True), "ga4 retention")
    print("ga4 retention: %d updated, %d already 14 months, %d failed (edit token discarded)"
          % (n["updated"], n["already"], n["failed"]))


if __name__ == "__main__":
    main()
