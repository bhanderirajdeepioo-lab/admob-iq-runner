"""Settings saves through the dashboard Worker (SPEC_CONFIG_SAVE), frontend side. tests/config_save_frontend.js runs the
page's own script (frontend/index.html's largest <script>, after `node --check`) in a node vm with a scripted fetch and
reports what ghCommitFile / ghCommit did. Checked here: the error texts (API errors carry the API's Hinglish message
and the HTTP status; the browser-token fallback says 401 → token expire/galat, 403/404 → permission nahi, 409/422 →
one retry with a fresh sha, then "kisi aur ne abhi save kiya"); the path choice (POST /api/config/save first, the
browser token ONLY when the API is unreachable: 404 or a network error); approvals go the same way; the Settings screen
hides the GitHub-token box when the server saves and turns the save buttons off for a non-admin. Skipped where node is
not installed."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
SERVER_NOTE = "Save dashboard ke server se hota hai (aapke login se) — GitHub token ki zaroorat nahi"
ADMIN_ONLY = "Sirf admin settings badal sakta hai"
OK = "OK-MSG"
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


@pytest.fixture(scope="module")
def rep(tmp_path_factory):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("cfgfe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "config_save_frontend.js"), path],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def F(rep, name):
    assert name in rep["flows"], (name, rep["errors"])
    return rep["flows"][name]


def urls(flow):
    return [(c["method"], c["url"]) for c in flow["calls"]]


def gh_calls(flow):
    return [c for c in flow["calls"] if c["url"].startswith("GH:")]


def test_page_functions_exist_and_run_cleanly(rep):
    assert rep["errors"] == []
    for f in ("ghCommitFile", "ghCommit", "cfgFileKey", "cfgStatusOf", "cfgApiErrMsg", "ghErrMsg", "cfgStatus",
              "renderSettings"):
        assert rep["fns"][f] == "function", f


def test_path_to_file_key_mapping(rep):
    assert rep["pure"]["file_keys"] == ["account_names", "app_names", "selected_apps", "approved_ranges",
                                        None, None, None, None, None]


def test_status_answer_decides_reachability(rep):
    s = rep["pure"]["status_of"]
    assert s[0] == {"reach": False}                                    # network error
    assert s[1] == {"reach": False}                                    # 404: no config API behind this host
    assert s[2] == {"reach": True, "server_save": True, "admin": True}
    assert s[3] == {"reach": True, "server_save": False, "admin": False}
    assert s[4] == {"reach": False} and s[5] == {"reach": False}       # a 200 that is not the API's JSON
    assert s[6]["reach"] is True and s[6]["admin"] is None and s[6]["status"] == 401
    assert s[7]["reach"] is True and s[7]["server_save"] is False


def test_api_error_text_is_the_hinglish_message_plus_the_status(rep):
    assert rep["pure"]["api_err"] == [
        "❌ Save fail — Sirf admin settings badal sakta hai (HTTP 403)",
        "❌ Save fail — GitHub token abhi Cloudflare me nahi daala (HTTP 503)",
        "❌ Save fail — GitHub token expire/galat (HTTP 502 · GitHub 401)",
        "❌ Save fail — Token ko repo me likhne ki permission nahi (HTTP 502 · GitHub 403)",
        "❌ Save fail — Kisi aur ne abhi save kiya — dobara try karo (HTTP 409 · GitHub 409)",
        "❌ Save fail — Account id galat (HTTP 400)",
        "❌ Save fail — Login zaroori — page reload karo (HTTP 401)",
        "❌ Save fail — Server me dikkat — thodi der baad try karo (HTTP 500)",
        "❌ Save fail — x (HTTP 502)",
    ]


def test_fallback_error_text_per_github_status(rep):
    assert rep["pure"]["gh_err"] == [
        "❌ Save fail — GitHub token expire/galat (HTTP 401). Naya token daalo.",
        "❌ Save fail — is token ko admob-iq repo me likhne ki permission nahi (HTTP 403)",
        "❌ Save fail — is token ko admob-iq repo me likhne ki permission nahi (HTTP 404)",
        "❌ Save fail — kisi aur ne abhi save kiya, dobara try karo",
        "❌ Save fail — kisi aur ne abhi save kiya, dobara try karo",
        "❌ Save fail — GitHub se dikkat (HTTP 500), dobara try karo",
        "❌ Save fail — GitHub se dikkat (HTTP 0), dobara try karo",
    ]


def test_server_save_first_and_no_browser_token_when_the_api_answers(rep):
    f = F(rep, "server_ok")
    assert f["ret"] is True and f["toasts"][-1] == OK
    assert urls(f) == [("GET", "/api/config/status"), ("POST", "/api/config/save")]
    assert f["calls"][1]["body"] == {"file": "selected_apps",
                                     "content": {"accounts": {"pub-1001": {"decided": True,
                                                                           "selected": ["ca-app-pub-1001~1"]}}}}
    # API errors are shown, never retried through the browser token (even though one is set in these scenarios)
    for name, toast in (("server_gh401", "❌ Save fail — GitHub token expire/galat (HTTP 502 · GitHub 401)"),
                        ("server_admin403", "❌ Save fail — Sirf admin settings badal sakta hai (HTTP 403)"),
                        ("server_no_token503", "❌ Save fail — GitHub token abhi Cloudflare me nahi daala (HTTP 503)"),
                        ("server_auth401", "❌ Save fail — Login zaroori — page reload karo (HTTP 401)")):
        f = F(rep, name)
        assert f["ret"] is False, name
        assert f["toasts"][-1] == toast, name
        assert gh_calls(f) == [], name


def test_status_is_asked_once_per_page(rep):
    f = F(rep, "status_cached")
    assert urls(f) == [("GET", "/api/config/status"), ("POST", "/api/config/save"), ("POST", "/api/config/save")]


def test_an_unreachable_api_is_asked_again_on_the_next_save(rep):
    f = F(rep, "reask_after_unreachable")
    assert f["ret"] == [True, True]
    assert [(m, u) for m, u in urls(f) if not u.startswith("GH:")] == [
        ("GET", "/api/config/status"), ("GET", "/api/config/status"), ("POST", "/api/config/save")]
    assert [c["method"] for c in gh_calls(f)] == ["GET", "PUT"]            # only the first save used the fallback
    assert f["st"] == {"reach": True, "server_save": True, "admin": True}


def test_fallback_only_when_the_api_is_unreachable(rep):
    for name in ("fallback_404_ok", "fallback_net_ok_new_file", "fallback_html_status", "save_net_then_fallback",
                 "save_404_then_fallback"):
        f = F(rep, name)
        assert f["ret"] is True and f["toasts"][-1] == OK, name
        assert f["st"] == {"reach": False}, name
        g = gh_calls(f)
        assert [c["method"] for c in g] == ["GET", "PUT"], name
        assert g[0]["cache"] == "no-store", "a cached GET would hand back an old sha"
        assert all(c["auth"] == "Bearer test-browser-token" for c in g)
        put = g[1]["body"]
        assert put["message"] == "select apps"
        assert json.loads(put["content"]) == {"accounts": {"pub-1001": {"decided": True, "selected": ["ca-app-pub-1001~1"]}}}
        assert put["content"].startswith('{\n "accounts"'), "indent 1, like the server"
    assert gh_calls(F(rep, "fallback_404_ok"))[1]["body"]["sha"] == "s1"
    assert gh_calls(F(rep, "fallback_net_ok_new_file"))[1]["body"]["sha"] is None      # GET 404 = a new file
    f = F(rep, "fallback_no_token")
    assert f["toasts"][-1] == "Pehle 🔑 GitHub token daalo (Settings → Accounts & Apps)" and gh_calls(f) == []


def test_fallback_error_statuses(rep):
    cases = {
        "fallback_put401": ("❌ Save fail — GitHub token expire/galat (HTTP 401). Naya token daalo.", ["GET", "PUT"]),
        "fallback_get401": ("❌ Save fail — GitHub token expire/galat (HTTP 401). Naya token daalo.", ["GET"]),
        "fallback_put403": ("❌ Save fail — is token ko admob-iq repo me likhne ki permission nahi (HTTP 403)", ["GET", "PUT"]),
        "fallback_put404": ("❌ Save fail — is token ko admob-iq repo me likhne ki permission nahi (HTTP 404)", ["GET", "PUT"]),
        "fallback_500": ("❌ Save fail — GitHub se dikkat (HTTP 500), dobara try karo", ["GET", "PUT"]),
    }
    for name, (toast, methods) in cases.items():
        f = F(rep, name)
        assert f["ret"] is False, name
        assert f["toasts"][-1] == toast, name
        assert [c["method"] for c in gh_calls(f)] == methods, name


def test_fallback_409_422_retry_once_with_a_fresh_sha(rep):
    f = F(rep, "fallback_409_retry_ok")
    assert f["ret"] is True and f["toasts"][-1] == OK
    g = gh_calls(f)
    assert [c["method"] for c in g] == ["GET", "PUT", "GET", "PUT"]
    assert [g[1]["body"]["sha"], g[3]["body"]["sha"]] == ["s1", "s2"]
    f = F(rep, "fallback_422_twice")
    assert f["ret"] is False
    assert f["toasts"][-1] == "❌ Save fail — kisi aur ne abhi save kiya, dobara try karo"
    assert [c["method"] for c in gh_calls(f)] == ["GET", "PUT", "GET", "PUT"]


def test_approvals_use_the_same_save_path(rep):
    f = F(rep, "approvals_server")
    assert f["ret"] is True and f["toasts"][-1] == "✅ Saved to GitHub (robot agle run me apply karega)"
    assert f["calls"][1]["body"] == {"file": "approved_ranges",
                                     "content": {"placements": {"ca-app-pub-1001/2001": {"metrics": {}}}}}
    assert F(rep, "approvals_fallback_no_token")["toasts"][-1] == "Pehle 🔑 GitHub token daalo (upar)"
    f = F(rep, "approvals_fallback_ok")
    g = gh_calls(f)
    assert g[1]["url"] == "GH:config/approved_ranges.json"
    assert g[1]["body"]["message"] == "approvals: approve X · eCPM"
    assert json.loads(g[1]["body"]["content"]) == {"placements": {}}


def test_settings_screen_token_box_and_admin_lock(rep):
    r = rep["render"]
    tok_box = "Selection save karne ke liye GitHub token"
    for k in ("server_admin", "server_admin_tok", "server_team", "server_team_tok"):
        assert SERVER_NOTE in r[k], k
        assert tok_box not in r[k] and 'id="astok"' not in r[k] and "token set ✓" not in r[k], k
    for k in ("none", "none_tok", "unreachable", "unreachable_tok", "noserver_admin", "noserver_admin_tok",
              "auth_unknown", "auth_unknown_tok"):
        assert SERVER_NOTE not in r[k], k
        assert tok_box in r[k], k                                      # unchanged: the old token box
    assert 'id="astok"' in r["none"] and "token set ✓" in r["none_tok"]
    for k in ("server_team", "server_team_tok", "noserver_team", "noserver_team_tok"):
        assert ADMIN_ONLY in r[k], k
        assert 'onclick="appPickSave()"' not in r[k] and 'onclick="accNameSave()"' not in r[k], k
        assert "<button disabled" in r[k] and r[k].count('aria-disabled="true"') == 2, k
    for k in ("none", "unreachable", "server_admin", "noserver_admin", "auth_unknown"):
        assert ADMIN_ONLY not in r[k], k
        assert 'onclick="appPickSave()"' in r[k] and 'onclick="accNameSave()"' in r[k], k
        assert "aria-disabled" not in r[k], k


def test_roman_script_only(rep):
    blob = json.dumps(rep, ensure_ascii=False)
    assert re.search(r"[\u0900-\u097F]", blob) is None
