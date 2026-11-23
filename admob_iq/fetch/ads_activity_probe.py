"""📡 Ads Activity report (alpha) probe — does AdMob still give us Meta's "Bids in auction"?

Owner, 23 Nov 2026: "bid in auction request add karo meta ki". AdMob shows "Bids in auction" only in its Ads Activity
report; the Mediation report its API gives (what the dashboard fetches) has no such metric. The Ads Activity report's API
(v1alpha accounts.adsActivityReport.generate) takes the admob.report scope our refresh tokens hold, but Google marks the
alpha "no longer supported" — it may answer only its old participants, or no one. His pick ("AdMob test pehle"): ask each
account with the tokens we already have — no new consent — and keep the answer.

Once a UTC day (the first build of the day), per account, two small reads of ONE complete day (the UTC day before
yesterday: every reporting time zone has closed it), in the publisher's time zone like the mediation report:
  1. by ad source: DATE × AD_SOURCE_ID × AD_SOURCE_NAME → BID_REQUEST, BIDS_IN_AUCTION, WINNING_BIDS, IMPRESSIONS;
  2. the same by app (APP_ID added) — only when 1 answered, so a refused account costs one call.
The answer goes to the PRIVATE data repo only (data/ads_activity_probe.json, pushed back with the rest of data/): per
account the HTTP status and the error's status / reason / message, or each row's metrics and the report's warnings — to
check against the mediation report's requests of the same day. Nothing reaches the page. The build log gets one word
(answered / refused / mixed …), never an id or a number (the log can be shown on a failure; the runner repo is public).

What counts as Google's answer: an HTTP status, or a failure of the token refresh / the connection (google-auth's and
requests' own errors). Anything else is a bug here: that account is marked "crash", the file is still written (so the
day's answers are kept and the next build says "done today"), and the first crash is raised for the build's
"ads activity probe skipped: <Type>" line (the page's red banner, once). Bounded: (10 s connect, 30 s read) per call, no
re-refresh on a 401 (that 401 IS the answer), and BUDGET_SEC for the whole probe — accounts not reached are "skipped"
(not "refused"). ADS_ACTIVITY_PROBE=false (repo variable) turns it off.
"""

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone

URL = "https://admob.googleapis.com/v1alpha/accounts/{acct}/adsActivityReport:generate"
TOKEN_URI = "https://oauth2.googleapis.com/token"
FILE = "ads_activity_probe.json"
METRICS = ["BID_REQUEST", "BIDS_IN_AUCTION", "WINNING_BIDS", "IMPRESSIONS"]
DIMS_SOURCE = ["DATE", "AD_SOURCE_ID", "AD_SOURCE_NAME"]
DIMS_APP = ["DATE", "APP_ID", "AD_SOURCE_ID", "AD_SOURCE_NAME"]
TIMEOUT = (10, 30)                  # (connect, read) seconds per call
BUDGET_SEC = 120                    # the whole probe: accounts not reached by then are skipped
MSG_MAX = 300


def _session(client_id, client_secret, refresh_token):
    """An authorized HTTP session for one account: the refresh token's OWN grant (no scopes= — a fixed scope the token
    was not granted fails the refresh; the AdMob client does the same), and no refresh-and-retry on a 401."""
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2.credentials import Credentials
    return AuthorizedSession(Credentials(token=None, refresh_token=refresh_token, token_uri=TOKEN_URI,
                                         client_id=client_id, client_secret=client_secret),
                             refresh_status_codes=())


def _answer_errors():
    """The exception types that are Google's answer (a refused / failed token refresh, a connection that failed)."""
    from google.auth.exceptions import GoogleAuthError
    from requests.exceptions import RequestException
    return (GoogleAuthError, RequestException)


def _body(day, dims):
    d = {"year": day.year, "month": day.month, "day": day.day}
    return {"reportSpec": {"dateRange": {"startDate": d, "endDate": d}, "dimensions": dims, "metrics": METRICS,
                           "localizationSettings": {"currencyCode": "USD", "languageCode": "en-US"},
                           "reportingTimeZone": "PUBLISHER_TIMEZONE"}}


def _num(v):
    """A metric value as the report gives it ({"integerValue": "27"} / {"doubleValue": 0.11} / {"microsValue": "…"});
    anything else, NaN or ±Infinity → None."""
    if not isinstance(v, dict):
        return None
    for k in ("integerValue", "doubleValue", "microsValue"):
        if k in v:
            try:
                x = float(v[k])
            except (TypeError, ValueError):
                return None
            if not math.isfinite(x):
                return None
            return int(x) if x.is_integer() else x
    return None


def _text(v):
    return v if isinstance(v, str) else (None if v is None else str(v))


def _rows(j):
    """The report's rows, whatever the shape: {"rows": [...]} (this report) or a header / row / footer list (the others)."""
    if isinstance(j, dict):
        rows = j.get("rows")
    elif isinstance(j, list):
        rows = [x.get("row") for x in j if isinstance(x, dict)]
    else:
        rows = None
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        dv, mv = row.get("dimensionValues"), row.get("metricValues")
        out.append({"dims": {k: _text(v.get("value") if isinstance(v, dict) else None) for k, v in dv.items()}
                    if isinstance(dv, dict) else {},
                    "metrics": {k: _num(v) for k, v in mv.items()} if isinstance(mv, dict) else {}})
    return out


def _ask(sess, acct, day, dims, answer_errors):
    """One read → {"http": status, "ok": True, "rows": n, "data": [...], "warnings": [...]}, or the error's {"http",
    "status", "reason", "message"}, or — no answer came (the token refresh, the connection) — {"exc", "message"}.
    Raises only for a bug here (anything that is not one of answer_errors)."""
    try:
        r = sess.post(URL.format(acct=acct), json=_body(day, dims), timeout=TIMEOUT)
    except answer_errors as e:                                   # e.g. RefreshError invalid_grant, a timeout
        return {"ok": False, "exc": type(e).__name__, "message": str(e)[:MSG_MAX]}
    code = getattr(r, "status_code", None)
    out = {"http": code, "ok": code == 200}
    try:
        j = r.json()
    except ValueError:
        j = None
    if not out["ok"]:
        err = j.get("error") if isinstance(j, dict) else None
        if isinstance(err, dict):
            out["status"] = _text(err.get("status"))
            out["message"] = (_text(err.get("message")) or "")[:MSG_MAX]
            det = err.get("details")
            for d in det if isinstance(det, list) else []:       # e.g. ACCESS_TOKEN_SCOPE_INSUFFICIENT
                if isinstance(d, dict) and d.get("reason"):
                    out["reason"] = _text(d.get("reason"))
                    break
        else:
            out["message"] = (_text(err) or getattr(r, "text", "") or "")[:MSG_MAX]
        return out
    data = _rows(j)
    out["rows"] = len(data)
    out["data"] = data
    w = j.get("warnings") if isinstance(j, dict) else None
    if isinstance(w, list) and w:
        out["warnings"] = w[:20]
    return out


def probe(accounts, client_id, client_secret, data_dir, now=None, session_factory=None, clock=None):
    """Probe every account with a refresh token, at most once per UTC day; write data_dir/FILE. Returns the log line
    (a word: no id, no number). Google's answers never raise; a bug here raises AFTER the file is written."""
    now = now or datetime.now(timezone.utc)
    clock = clock or time.monotonic
    path = os.path.join(data_dir, FILE)
    today = now.date().isoformat()
    try:
        with open(path, encoding="utf-8") as f:
            prev = json.load(f)
        if isinstance(prev, dict) and prev.get("probed_on") == today:
            return "ads activity probe: done today"
    except (OSError, ValueError):
        pass
    day = now.date() - timedelta(days=2)
    errs = _answer_errors()
    make = session_factory or (lambda tok: _session(client_id, client_secret, tok))
    t0, res, crash = clock(), [], None
    for a in accounts or []:
        tok, acct = a.get("refresh_token"), a.get("account_id")
        if not tok or not acct:
            continue
        if clock() - t0 > BUDGET_SEC:
            res.append({"account": acct, "skipped": "deadline"})
            continue
        one = {"account": acct}
        try:
            sess = make(tok)
            one["source"] = _ask(sess, acct, day, DIMS_SOURCE, errs)
            if one["source"].get("ok") and clock() - t0 <= BUDGET_SEC:
                one["app"] = _ask(sess, acct, day, DIMS_APP, errs)
        except Exception as e:                                   # a bug here, not Google's answer
            one["crash"] = type(e).__name__
            crash = crash or e
        res.append(one)
    rep = {"v": 2, "probed_on": today, "probed_at": now.isoformat(timespec="seconds"), "day": day.isoformat(),
           "metrics": METRICS, "time_zone": "PUBLISHER_TIMEZONE", "accounts": res}
    os.makedirs(data_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    if crash is not None:
        raise crash
    asked = [x for x in res if "source" in x]
    ok = sum(1 for x in asked if x["source"].get("ok"))
    word = ("no account" if not res else "deadline" if not asked else
            "answered" if ok == len(asked) else "refused" if ok == 0 else "mixed")
    if asked and len(asked) < len(res):
        word += " (some skipped)"
    return "ads activity probe: " + word
