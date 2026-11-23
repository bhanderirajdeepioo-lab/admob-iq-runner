"""📡 The Ads Activity report (alpha) probe: does AdMob still give our accounts Meta's "Bids in auction"?

Once a UTC day, per account, one small read by ad source (and, when it answers, one by app) of the UTC day before
yesterday, in the publisher's time zone; the answer — HTTP status, the error's status / reason / message, or each row's
metrics and the report's warnings — goes to the private data/ads_activity_probe.json only; the build log gets a word,
never an id or a number. A token refresh / connection failure is Google's answer; anything else is a bug here (the file is
still written, then it raises for the page's banner). Fake HTTP sessions / adapters play Google's answers here: every
account id, source id and count is SYNTHETIC."""

import json
import os
import re
from datetime import datetime, timezone

import pytest
import requests
from google.auth.exceptions import RefreshError
from requests.adapters import BaseAdapter
from requests.models import Response

from admob_iq.fetch import ads_activity_probe as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 1, 10, 6, 30, tzinfo=timezone.utc)
A_OK, A_SCOPE, A_AUTH, A_NOTOKEN, A_STREAM, A_NET = (
    "pub-0000000000000001", "pub-0000000000000002", "pub-0000000000000003", "pub-0000000000000004",
    "pub-0000000000000005", "pub-0000000000000006")
ACCOUNTS = [{"account_id": A_OK, "refresh_token": "tok-ok"}, {"account_id": A_SCOPE, "refresh_token": "tok-scope"},
            {"account_id": A_AUTH, "refresh_token": "tok-auth"}, {"account_id": A_NOTOKEN, "refresh_token": ""},
            {"account_id": A_STREAM, "refresh_token": "tok-stream"}, {"account_id": A_NET, "refresh_token": "tok-net"}]


def _row(dims, req, bids, wins, impr):
    return {"dimensionValues": {k: {"value": v} for k, v in dims.items()},
            "metricValues": {"BID_REQUEST": {"integerValue": str(req)}, "BIDS_IN_AUCTION": {"integerValue": str(bids)},
                             "WINNING_BIDS": {"doubleValue": wins}, "IMPRESSIONS": {"integerValue": str(impr)}}}


SRC_ROWS = [_row({"DATE": "20260108", "AD_SOURCE_ID": "1001", "AD_SOURCE_NAME": "AdMob Network"}, 9000, 7000, 3000, 2500),
            _row({"DATE": "20260108", "AD_SOURCE_ID": "1003", "AD_SOURCE_NAME": "Meta Audience Network (bidding)"},
                 6000, 4000, 900, 600)]
APP_ROWS = [_row({"DATE": "20260108", "APP_ID": "ca-app-pub-0000000000000001~1000000001", "AD_SOURCE_ID": "1003",
                  "AD_SOURCE_NAME": "Meta Audience Network (bidding)"}, 6000, 4000, 900, 600)]
WARN = [{"type": "DATA_DELAYED", "description": "synthetic warning"}]
SCOPE_ERR = {"error": {"code": 403, "message": "Request had insufficient authentication scopes.", "status": "PERMISSION_DENIED",
                       "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}
GRANT = RefreshError("invalid_grant: Token has been expired or revoked.",          # the shape google-auth raises
                     {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._b = status, body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        if isinstance(self._b, str):
            raise ValueError("not json")
        return self._b


class _Sess:
    """Google's answer for one account's token; every call is recorded."""

    def __init__(self, tok, calls, answers):
        self.tok, self.calls, self.answers = tok, calls, answers

    def post(self, url, json=None, timeout=None):
        self.calls.append((self.tok, url, json, timeout))
        a = self.answers(self.tok, json["reportSpec"]["dimensions"])
        if isinstance(a, BaseException):
            raise a
        return _Resp(*a)


def _google(tok, dims):
    if tok == "tok-ok":
        return 200, {"rows": APP_ROWS if "APP_ID" in dims else SRC_ROWS, "warnings": WARN}
    if tok == "tok-scope":
        return 403, SCOPE_ERR
    if tok == "tok-auth":
        return GRANT
    if tok == "tok-stream":                          # the other reports' header / row / footer stream shape
        return 200, [{"header": {}}] + [{"row": r} for r in SRC_ROWS] + [{"footer": {"matchingRowCount": "2"}}]
    if tok == "tok-net":
        return requests.exceptions.ConnectTimeout("synthetic connect timeout")
    raise AssertionError(tok)


def _run(tmp_path, accounts=ACCOUNTS, now=NOW, answers=_google, factory=None, clock=None):
    calls = []
    make = factory or (lambda tok: _Sess(tok, calls, answers))
    line = P.probe(accounts, "client-id", "client-secret", str(tmp_path), now=now, session_factory=make, clock=clock)
    path = tmp_path / P.FILE
    return line, (json.loads(path.read_text()) if path.exists() else None), calls


def test_each_account_answer_is_kept_in_the_private_file(tmp_path, capsys):
    line, rep, calls = _run(tmp_path)
    assert capsys.readouterr() == ("", "")                     # the probe prints nothing itself
    assert line == "ads activity probe: mixed" and not re.search(r"\d", line)   # a word: no id, no number
    assert rep["v"] == 2 and rep["probed_on"] == "2026-01-10" and rep["day"] == "2026-01-08"   # the UTC day before yesterday
    assert rep["metrics"] == ["BID_REQUEST", "BIDS_IN_AUCTION", "WINNING_BIDS", "IMPRESSIONS"]
    assert rep["time_zone"] == "PUBLISHER_TIMEZONE"
    by = {a["account"]: a for a in rep["accounts"]}
    assert set(by) == {A_OK, A_SCOPE, A_AUTH, A_STREAM, A_NET}             # an account without a token: not asked
    ok = by[A_OK]
    assert ok["source"]["ok"] is True and ok["source"]["http"] == 200 and ok["source"]["rows"] == 2
    assert ok["source"]["warnings"] == WARN
    meta = [r for r in ok["source"]["data"] if r["dims"]["AD_SOURCE_NAME"] == "Meta Audience Network (bidding)"][0]
    assert meta["metrics"] == {"BID_REQUEST": 6000, "BIDS_IN_AUCTION": 4000, "WINNING_BIDS": 900, "IMPRESSIONS": 600}
    assert ok["app"]["ok"] is True and ok["app"]["data"][0]["dims"]["APP_ID"].endswith("~1000000001")
    assert by[A_SCOPE] == {"account": A_SCOPE, "source": {"http": 403, "ok": False, "status": "PERMISSION_DENIED",
                                                          "message": "Request had insufficient authentication scopes.",
                                                          "reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}}   # one call, not two
    assert by[A_AUTH]["source"]["exc"] == "RefreshError" and "invalid_grant" in by[A_AUTH]["source"]["message"]
    assert by[A_STREAM]["source"]["ok"] and by[A_STREAM]["source"]["rows"] == 2       # the stream shape read too
    assert by[A_NET]["source"] == {"ok": False, "exc": "ConnectTimeout", "message": "synthetic connect timeout"}
    assert not any("crash" in a for a in rep["accounts"])


def test_the_request_is_the_documented_alpha_call(tmp_path):
    _, _, calls = _run(tmp_path, accounts=[ACCOUNTS[0]])
    assert len(calls) == 2                                                   # by source, then by app
    (tok, url, body, timeout), (_, url2, body2, _) = calls
    assert url == url2 == "https://admob.googleapis.com/v1alpha/accounts/%s/adsActivityReport:generate" % A_OK
    spec = body["reportSpec"]                                                # the reference's camelCase JSON
    assert spec["dateRange"] == {"startDate": {"year": 2026, "month": 1, "day": 8}, "endDate": {"year": 2026, "month": 1, "day": 8}}
    assert spec["dimensions"] == ["DATE", "AD_SOURCE_ID", "AD_SOURCE_NAME"]
    assert body2["reportSpec"]["dimensions"] == ["DATE", "APP_ID", "AD_SOURCE_ID", "AD_SOURCE_NAME"]
    assert spec["metrics"] == ["BID_REQUEST", "BIDS_IN_AUCTION", "WINNING_BIDS", "IMPRESSIONS"]
    assert spec["localizationSettings"] == {"currencyCode": "USD", "languageCode": "en-US"}
    assert spec["reportingTimeZone"] == "PUBLISHER_TIMEZONE" and timeout == (10, 30)


def test_odd_answers_never_break_it(tmp_path):
    odd = {"nan": {"rows": [{"metricValues": {"WINNING_BIDS": {"doubleValue": "NaN"}, "BID_REQUEST": {"doubleValue": "Infinity"},
                                             "BIDS_IN_AUCTION": {"doubleValue": 2.5}, "IMPRESSIONS": "7"}}]},
           "shapes": {"rows": ["x", {"dimensionValues": [{"value": "x"}], "metricValues": None},
                               {"dimensionValues": {"DATE": "20260108", "APP_ID": {"value": 7}}}]},
           "null": None, "list": [1, 2], "html": "<html>Not Found</html>",
           "errstr": {"error": "bad"}, "errdet": {"error": {"status": "INVALID_ARGUMENT", "details": "not a list"}}}
    codes = {"html": 404, "errstr": 400, "errdet": 400}
    for k, body in odd.items():
        line, rep, _ = _run(tmp_path / k, accounts=[{"account_id": A_OK, "refresh_token": k}],
                            answers=lambda tok, dims: (codes.get(tok, 200), odd[tok]))
        assert rep["accounts"][0].get("crash") is None, k
    src = lambda k: json.loads((tmp_path / k / P.FILE).read_text())["accounts"][0]["source"]
    assert src("nan")["data"][0]["metrics"] == {"WINNING_BIDS": None, "BID_REQUEST": None, "BIDS_IN_AUCTION": 2.5, "IMPRESSIONS": None}
    assert src("shapes")["rows"] == 2 and src("shapes")["data"][1]["dims"] == {"DATE": None, "APP_ID": "7"}
    assert src("null")["rows"] == 0 and src("list")["rows"] == 0
    assert src("html") == {"http": 404, "ok": False, "message": "<html>Not Found</html>"}
    assert src("errstr") == {"http": 400, "ok": False, "message": "bad"}
    assert src("errdet") == {"http": 400, "ok": False, "status": "INVALID_ARGUMENT", "message": ""}


def test_a_bug_here_keeps_the_days_answers_then_raises_once(tmp_path):
    def answers(tok, dims):
        if tok == "tok-bug":
            return TypeError("synthetic bug")            # not Google's answer: a bug here
        return _google(tok, dims)
    accts = [{"account_id": A_OK, "refresh_token": "tok-ok"}, {"account_id": A_NET, "refresh_token": "tok-bug"},
             {"account_id": A_SCOPE, "refresh_token": "tok-scope"}]
    with pytest.raises(TypeError):
        _run(tmp_path, accounts=accts, answers=answers)
    rep = json.loads((tmp_path / P.FILE).read_text())                     # written before it raised
    by = {a["account"]: a for a in rep["accounts"]}
    assert by[A_NET] == {"account": A_NET, "crash": "TypeError"}
    assert by[A_OK]["source"]["ok"] and by[A_SCOPE]["source"]["http"] == 403   # the others' answers kept
    assert _run(tmp_path, accounts=accts, answers=answers)[0] == "ads activity probe: done today"   # the banner once a day

    def bad_factory(tok):
        raise ValueError("synthetic session bug")
    with pytest.raises(ValueError):
        _run(tmp_path / "s", accounts=accts, factory=bad_factory)
    assert {a.get("crash") for a in json.loads((tmp_path / "s" / P.FILE).read_text())["accounts"]} == {"ValueError"}


def test_the_whole_probe_has_a_deadline(tmp_path):
    ticks = iter([0, 0, 1, 5, P.BUDGET_SEC + 1, P.BUDGET_SEC + 2, P.BUDGET_SEC + 3])
    accts = [ACCOUNTS[0], ACCOUNTS[1], ACCOUNTS[4]]
    line, rep, calls = _run(tmp_path, accounts=accts, clock=lambda: next(ticks))
    by = {a["account"]: a for a in rep["accounts"]}
    assert by[A_OK]["source"]["ok"] and "app" in by[A_OK] and by[A_SCOPE]["source"]["http"] == 403
    assert by[A_STREAM] == {"account": A_STREAM, "skipped": "deadline"}   # not reached: skipped, not refused
    assert line == "ads activity probe: mixed (some skipped)" and len(calls) == 3


def test_once_a_utc_day(tmp_path):
    _run(tmp_path)
    line, rep, calls = _run(tmp_path, now=NOW.replace(hour=23))              # the same UTC day: nothing asked again
    assert line == "ads activity probe: done today" and calls == [] and rep["probed_at"].startswith("2026-01-10T06:30")
    line, rep, calls = _run(tmp_path, now=datetime(2026, 1, 11, 0, 5, tzinfo=timezone.utc))   # the next day: again
    assert line == "ads activity probe: mixed" and calls and rep["day"] == "2026-01-09"
    (tmp_path / P.FILE).write_text("{not json")                             # a broken file: probed again, never a crash
    line, rep, _ = _run(tmp_path)
    assert rep["probed_on"] == "2026-01-10"


def test_the_log_word(tmp_path):
    assert _run(tmp_path / "a", accounts=[ACCOUNTS[0], ACCOUNTS[4]])[0] == "ads activity probe: answered"
    assert _run(tmp_path / "b", accounts=[ACCOUNTS[1], ACCOUNTS[2]])[0] == "ads activity probe: refused"
    assert _run(tmp_path / "c", accounts=[ACCOUNTS[3]])[0] == "ads activity probe: no account"


# ── the real google-auth session, offline (fake HTTP adapters play the token endpoint and the API) ────────────────────
class _Adapter(BaseAdapter):
    def __init__(self, answer, log):
        super().__init__()
        self.answer, self.log = answer, log

    def send(self, request, **kw):
        body = request.body.decode() if isinstance(request.body, bytes) else request.body
        self.log.append((request.method, request.url.split("?")[0], body, kw.get("timeout")))
        status, body = self.answer(request)
        r = Response()
        r.status_code, r.url, r.request = status, request.url, request
        r._content = json.dumps(body).encode()
        r.headers["Content-Type"] = "application/json"
        return r

    def close(self):
        pass


def _real(tmp_path, api_answer, token_answer=None):
    log = []
    token_answer = token_answer or (lambda req: (200, {"access_token": "synthetic-access", "expires_in": 3600,
                                                       "token_type": "Bearer"}))

    def factory(tok):
        s = P._session("client-id", "client-secret", tok)
        s.mount("https://", _Adapter(api_answer, log))
        s._auth_request.session.mount("https://", _Adapter(token_answer, log))
        return s
    line, rep, _ = _run(tmp_path, accounts=[{"account_id": A_OK, "refresh_token": "synthetic-refresh"}], factory=factory)
    return line, rep, log


def test_the_real_session_refreshes_with_the_tokens_own_grant(tmp_path):
    line, rep, log = _real(tmp_path, lambda req: (200, {"rows": SRC_ROWS}))
    token = [x for x in log if "oauth2" in x[1]]
    api = [x for x in log if "admob.googleapis.com" in x[1]]
    assert len(token) == 1 and "refresh_token=synthetic-refresh" in token[0][2] and "scope=" not in token[0][2]
    assert len(api) == 2 and api[0][3] == (10, 30) and json.loads(api[0][2])["reportSpec"]["metrics"] == P.METRICS
    assert line == "ads activity probe: answered" and rep["accounts"][0]["source"]["rows"] == 2


def test_a_401_is_the_answer_not_a_refresh_loop(tmp_path):
    line, rep, log = _real(tmp_path, lambda req: (401, {"error": {"code": 401, "status": "UNAUTHENTICATED", "message": "no"}}))
    assert len([x for x in log if "admob.googleapis.com" in x[1]]) == 1 and len([x for x in log if "oauth2" in x[1]]) == 1
    assert rep["accounts"][0]["source"] == {"http": 401, "ok": False, "status": "UNAUTHENTICATED", "message": "no"}
    assert line == "ads activity probe: refused"


def test_a_refused_token_is_the_answer(tmp_path):
    line, rep, log = _real(tmp_path, lambda req: (200, {"rows": []}),
                           token_answer=lambda req: (400, {"error": "invalid_grant", "error_description": "expired"}))
    src = rep["accounts"][0]["source"]
    assert src["exc"] == "RefreshError" and "invalid_grant" in src["message"] and line == "ads activity probe: refused"
    assert not [x for x in log if "admob.googleapis.com" in x[1]]             # no token: the API never asked


# ── the build's wiring ──────────────────────────────────────────────────────────────────────────────────────────────
def test_wired_into_the_build_behind_its_switch():
    with open(os.path.join(ROOT, "admob_iq", "build_static.py"), encoding="utf-8") as f:
        b = f.read()
    hook = b[b.index('if s.get("ads_activity_probe", True):'):]
    hook = hook[:hook.index('_sc.step("repo_flush")')]
    assert 'with _sc.stage("ads_activity_probe"):' in hook and "from .fetch.ads_activity_probe import probe" in hook
    assert 'print(f"ads activity probe skipped: {type(e).__name__}", file=sys.stderr)' in hook   # a bug: the red banner
    lines = b.splitlines()                                                   # live builds with credentials only:
    i = next(k for k, ln in enumerate(lines) if ln.strip() == 'if s.get("ads_activity_probe", True):')
    outer = next(lines[k] for k in range(i - 1, -1, -1)                      # the block it sits in (4-space level)
                 if lines[k].startswith("    ") and not lines[k].startswith("     ") and lines[k].strip())
    assert lines[i].startswith("        if ") and outer.strip() == 'if mode == "live" and has_creds:'
    from admob_iq import stage_clock
    assert "ads_activity_probe" in stage_clock.STAGES
    with open(os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        assert "ADS_ACTIVITY_PROBE:   ${{ vars.ADS_ACTIVITY_PROBE || 'true' }}" in f.read()


def test_the_switch(monkeypatch):
    from admob_iq.config import settings
    for v, on in ((None, True), ("", True), ("true", True), ("false", False), (" OFF ", False), ("0", False)):
        if v is None:
            monkeypatch.delenv("ADS_ACTIVITY_PROBE", raising=False)
        else:
            monkeypatch.setenv("ADS_ACTIVITY_PROBE", v)
        assert settings()["ads_activity_probe"] is on, v
