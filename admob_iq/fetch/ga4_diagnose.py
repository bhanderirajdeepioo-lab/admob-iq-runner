"""One-off GA4 diagnostic, run by .github/workflows/ga4-diagnose.yml: for a few apps, compare ways of asking
GA4 for app_remove users on OLD vs RECENT days, to find a report shape that is complete for old days too.

Why: firstSessionDate × date (the uninstall cohort cells) comes back complete for roughly the newest two
weeks, but far short for older days on some properties — even one day at a time. This asks the same days
several ways (and the cohortSpec API for a few install days) and writes every answer next to the date ×
eventName total, which is complete.

Input: the PRIVATE repo's ga4/diagnose_input.json {"packages": [...], "days": [...], "cohorts": [...]}.
Output: ga4/diagnose.json in the PRIVATE repo. The public log shows counts only.
"""

import json
import os
import sys
import time
from datetime import date, timedelta

import requests

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch.ga4_auth_exchange import _put_private_file


def _private_json(path):
    r = requests.get("https://api.github.com/repos/%s/contents/%s" % (os.environ["DATA_REPO"], path), timeout=30,
                     headers={"Authorization": "token " + os.environ["DATA_REPO_TOKEN"],
                              "Accept": "application/vnd.github.raw", "User-Agent": "admob-iq-ga4-diagnose"})
    if r.status_code != 200:
        sys.exit("could not read %s from the private repo (HTTP %s)" % (path, r.status_code))
    return r.json()


def _sum(rows, metric):
    return sum(r.get(metric) or 0 for r in rows)


def _try(fn):
    try:
        return fn()
    except Exception as e:                        # recorded privately, never printed
        return {"error": str(e)[:300]}


def _day(ga, d):
    rng = [{"startDate": d, "endDate": d}]
    wk = [{"startDate": (date.fromisoformat(d) - timedelta(days=6)).isoformat(), "endDate": d}]
    dims = lambda *n: [{"name": x} for x in n]
    out = {}
    out["events_date_eventName"] = _try(lambda: (lambda r: {"users": _sum(r, "totalUsers"), "events": _sum(r, "eventCount")})(
        ga.report_all({"dateRanges": rng, "dimensions": dims("date", "eventName"),
                       "metrics": dims("totalUsers", "eventCount")}, events=["app_remove"])))
    out["date_only"] = _try(lambda: {"users": _sum(ga.report_all(
        {"dateRanges": rng, "dimensions": dims("date"), "metrics": dims("totalUsers")}, event="app_remove"), "totalUsers")})
    out["fsd_x_date_users"] = _try(lambda: (lambda r: {"users": _sum(r, "totalUsers"), "rows": len(r)})(ga.report_all(
        {"dateRanges": rng, "dimensions": dims("firstSessionDate", "date"), "metrics": dims("totalUsers")}, event="app_remove")))
    out["fsd_x_date_events"] = _try(lambda: {"events": _sum(ga.report_all(
        {"dateRanges": rng, "dimensions": dims("firstSessionDate", "date"), "metrics": dims("eventCount")}, event="app_remove"),
        "eventCount")})
    out["fsd_only_users"] = _try(lambda: {"users": _sum(ga.report_all(
        {"dateRanges": rng, "dimensions": dims("firstSessionDate"), "metrics": dims("totalUsers")}, event="app_remove"),
        "totalUsers")})
    out["fsd_x_date_users_7d_range"] = _try(lambda: (lambda r: {"users_on_day": sum(x.get("totalUsers") or 0 for x in r
                                                                                   if str(x.get("date")) == d.replace("-", ""))})(
        ga.report_all({"dateRanges": wk, "dimensions": dims("firstSessionDate", "date"), "metrics": dims("totalUsers")},
                      event="app_remove")))
    out["thresholded"] = bool(ga.thresholded)
    return out


def _cohort(ga, c, event):
    body = {"dimensions": [{"name": "cohort"}, {"name": "cohortNthDay"}],
            "metrics": [{"name": "cohortActiveUsers"}, {"name": "cohortTotalUsers"}],
            "cohortSpec": {"cohorts": [{"name": "c", "dimension": "firstSessionDate",
                                        "dateRange": {"startDate": c, "endDate": c}}],
                           "cohortsRange": {"granularity": "DAILY", "startOffset": 0, "endOffset": 30}}}
    rows = ga.report(body, event=event)
    return {str(int(r.get("cohortNthDay") or 0)): [r.get("cohortActiveUsers"), r.get("cohortTotalUsers")] for r in rows}


def main():
    env = os.environ
    want = _private_json("ga4/diagnose_input.json")
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    paging = {}
    owners, props, readers = ga4_probe.discover_owners(cid, sec, tokens, paging)
    streams, token_of, errors, _ = ga4_probe.list_streams(props, readers, paging)
    by_pkg = {}
    for s in streams:
        by_pkg.setdefault(s.get("package"), s)
    out = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "apps": {},
           "discovery": {"tokens": len(tokens), "owners": owners, "properties": len(props), "streams": len(streams),
                         "stream_errors": errors, "packages_seen": sorted(by_pkg)}}
    if want.get("retention"):                  # each property's data-retention setting (Admin API, read-only)
        ret = {}
        for p in props:
            pid = p["property_id"]
            tok = token_of.get(pid) or (readers.get(pid) or [(None, None)])[0][1]
            r = requests.get("%s/properties/%s/dataRetentionSettings" % (ga4.ADMIN, pid), timeout=30,
                             headers={"Authorization": "Bearer " + tok})
            ret[pid] = {"http": r.status_code, "settings": r.json() if r.status_code == 200 else r.text[:200],
                        "packages": sorted(s.get("package") for s in streams if s.get("property_id") == pid)}
        out["retention"] = ret
    for pkg in want.get("packages") or []:
        s = by_pkg.get(pkg)
        if not s:
            out["apps"][pkg] = {"error": "no stream"}
            continue
        ga = ga4.Ga4App(token_of[s["property_id"]], s["property_id"], s["stream_id"])
        res = {"days": {d: _day(ga, d) for d in want.get("days") or []},
               "cohorts_app_remove": {c: _try(lambda c=c: _cohort(ga, c, "app_remove")) for c in want.get("cohorts") or []},
               "cohorts_active": {c: _try(lambda c=c: _cohort(ga, c, None)) for c in want.get("cohorts") or []}}
        out["apps"][pkg] = res
    _put_private_file("ga4/diagnose.json", json.dumps(out, indent=1, default=str), "ga4 diagnose")
    print("ga4 diagnose: %d app(s) checked, detail in the private repo" % len(out["apps"]))


if __name__ == "__main__":
    main()
