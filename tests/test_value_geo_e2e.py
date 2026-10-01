"""Google Ads cost by country END TO END (SPEC_CD_GEO Part G): the three parts meet. The geo fetch (fetch.gads_geo.geo_step,
against the fake Google Ads API of tests/test_gads_geo.py — each synthetic store's daily spend split over four countries
plus a small unmapped id) writes its real cache files; the value build reads them (prepass → value_build._app_geo's week
envelope → the engine) with GADS_GEO on; the page (frontend/index.html's own script, tests/value_cd_frontend.js) draws the
detail files it wrote. Checked: the country cost adds up to the campaign cost (coverage 1, the unmapped part counted), a
country without Google Ads cost is "No ads here", the organic app says "noads", the gate's constants are exported, and the
page shows the cost columns and the opened row with no error, no undefined / NaN and no Devanagari. All data is synthetic
(tests.value_synth's made-up apps); no network."""

import contextlib
import gzip
import io
import json
import os
import re
import shutil
import subprocess
from datetime import timedelta
from unittest import mock

import pytest

from admob_iq import build_static
from admob_iq import value_build as vb
from admob_iq.config import settings
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch import gads_geo as gg
from tests import value_synth as vs
from tests.test_gads_geo import COUNTRY, FX, LINE, M, SETTINGS, TOK, Clock, FakeAds

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
SHARE = {"2840": 0.30, "2356": 0.25, "2076": 0.20, "2826": 0.247, "9990001": 0.003}   # 9990001: no country → "XX"
# (a trickle unmapped, under GEO_XX_NOADS: a country without cost of its own is "No ads here", not "unknown")
RUN = vs.RUNS[-1]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("geo_e2e"))
    data_dir, out_dir = os.path.join(tmp, "data"), os.path.join(tmp, "site")
    today = RUN.date()
    rev, _ = vs.seed_build(data_dir, end=today - timedelta(days=2))
    sp_path = os.path.join(data_dir, vb.SPEND_FILE)
    with open(sp_path, encoding="utf-8") as f:
        spend = json.load(f)
    plan = {}
    for k, sid in enumerate(sorted(spend["daily"])):      # each store's campaigns in its own (made-up) account
        acct = "22200022%02d" % (31 + k)
        spend["campaigns"][sid] = [{"id": "c%d" % k, "name": "n", "status": "ENABLED", "cost_micros": 1,
                                    "account": acct, "account_name": ""}]
        dd = spend["daily"][sid]
        plan[acct] = {sid: {c: (lambda d, dd=dd, c=c: dd.get(d, 0) / M * SHARE[c]) for c in SHARE}}
    with open(sp_path, "w", encoding="utf-8") as f:
        json.dump(spend, f)
    fake = FakeAds(plan)
    line = gg.geo_step(SETTINGS, data_dir, spend, today, now=lambda: 1_800_000_000, clock=Clock(), search=fake.search,
                       token=TOK, fx_fn=FX.get)
    s = dict(settings(), ga4_enabled=True, ga4_client_id="demo-cid", ga4_client_secret="demo-sec",
             ga4_refresh_tokens=json.dumps({"owner@example.test": "rt-demo"}), ga4_refresh_token="",
             notify_dry_run=True, ga4_active=True, ga4_value=True, gads_geo=True, value_cd=False)
    catalog = [{"app_id": aid, "app_name": name, "account_id": "pub-demo", "selected": True}
               for aid, name, _, _ in vs.FIX_APPS]
    status = {"counts": {"selected": 3, "with_ga4": 3, "fetched": 0, "full": 0, "fresh": 3, "failed": 0,
                         "deferred": 0, "no_ga4": 0}, "apps": {}, "no_ga4": {}, "discovery": None}
    dashboard = {"apps_catalog": catalog, "kpis": {"revenue": 1.0}, "alerts": {"items": []}, "usd_inr": 83.3}
    log = io.StringIO()
    with mock.patch.object(gu, "refresh_all", lambda *a, **k: json.loads(json.dumps(status))), \
            contextlib.redirect_stderr(log):
        build_static._uninstall_step(dashboard, data_dir, out_dir, s, revenue=rev, now=RUN)
    files = {}
    for r in dashboard["value"]["apps"]:
        if r.get("file"):
            with gzip.open(os.path.join(out_dir, r["file"]), "rt", encoding="utf-8") as f:
                files[r["key"]] = json.load(f)
    fx_path = os.path.join(tmp, "value_geo_e2e.json")
    with open(fx_path, "w", encoding="utf-8") as f:
        json.dump({"dashboard_value": dashboard["value"], "app_files": files}, f, ensure_ascii=False)
    return {"line": line, "value": dashboard["value"], "files": files, "log": log.getvalue(), "fixture": fx_path,
            "cache": gg.load_geo(data_dir)}


def by_name(b):
    return {r["app"]: (r, b["files"].get(r["key"])) for r in b["value"]["apps"]}


def test_geo_step_writes_the_cache_the_value_build_reads(built):
    assert LINE.match(built["line"]) and ", errors 0," in built["line"] and ", unmapped 1" in built["line"]
    c = built["cache"]
    assert c and c["till"] and c["iso"].get("9990001") is None and set(COUNTRY.values()) <= set(c["iso"].values())
    assert any("XX" in cells for ws in c["weeks"].values() for cells in ws.values())
    assert "country cost on" in next(ln for ln in built["log"].splitlines() if ln.startswith("ga4 value:"))


def test_country_cost_adds_up_to_the_campaign_cost(built):
    apps = by_name(built)
    row, det = apps["Demo Spend App"]
    co = det["countries"]
    assert co["geo"] and co["geo_why"] == "ok" and row["cty"]["geo"]
    assert co["geo_cov"]["v"] == pytest.approx(1.0, abs=1e-3) and co["geo_cov"]["weeks"] == co["win"]["weeks"]
    assert co["cost"]["total"] == pytest.approx(co["cost"]["spend"], rel=1e-3)        # Σ countries (XX included) = cost
    assert co["cost"]["unmapped_share"] == pytest.approx(SHARE["9990001"], abs=1e-3)
    assert co["cost"]["total"] == pytest.approx(co["cost"]["rows"] + co["cost"]["small"] + co["cost"]["unmapped"],
                                                rel=1e-4)
    rows = {r["cc"]: r for r in co["rows"]}
    paid = [cc for cc in ("US", "IN", "BR", "GB") if cc in rows]
    assert paid and all(rows[cc]["cpi"]["v"] > 0 and rows[cc]["pay"] is not None for cc in paid)
    free = [r for r in co["rows"] if r["cc"] not in COUNTRY.values() and r["cc"] not in ("--", "ZZ")]
    assert free and all(r["cpi"] == {"v": None, "spend": 0.0, "noads": True} for r in free)
    assert all(r["verdict"] in ("top", "avg", "low", "few", "wait") for r in free)       # never "cheapest"
    assert any(t.startswith("Google Ads country-wise spend: campaign spend ka 100% country me mila")
               for t in det["scale"]["text"])


def test_organic_app_is_noads_and_counts_say_why(built):
    apps = by_name(built)
    _, det = apps["Demo Organic App"]
    assert det["countries"]["geo_why"] == "noads" and det["countries"]["cost"] is None
    v = built["value"]
    assert v["counts"]["geo"]["noads"] >= 1 and v["counts"]["geo"]["on"] >= 1
    assert {k: v["consts"][k] for k in ("geo_cov_min", "geo_cov_max", "geo_cov_abs", "geo_dl_min", "geo_paid_min")} == {
        "geo_cov_min": 0.97, "geo_cov_max": 1.03, "geo_cov_abs": 0.05, "geo_dl_min": 50, "geo_paid_min": 0.3}
    assert v["consts"]["reopen_seed_days"]["geo_cost"] == 42                    # GADS_GEO on, VALUE_CD off: said too


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_page_draws_the_engines_country_cost(built, tmp_path):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        js = max(re.findall(r"<script>(.*?)</script>", f.read(), re.S), key=len)
    path = str(tmp_path / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "value_cd_frontend.js"), path, built["fixture"]],
                         check=True, capture_output=True, text=True, timeout=300)
    rep = json.loads(out.stdout)
    assert rep["errors"] == []
    apps = rep["fixture"]["apps"]
    for name, a in apps.items():
        assert not a["bad"] and not a["deva"] and not a["tokens"], name
    s = apps["Demo Spend App"]
    assert s["geo_why"] == "ok" and s["cost_cols"] and s["noads"] >= 1 and not s["geo_note"] and not s["nogeo"]
    assert s["opened"] and s["opened"] >= 2                       # "$100 ke ads pe …" and the cost sparkline, both widths
    o = apps["Demo Organic App"]
    assert o["geo_why"] == "noads" and not o["cost_cols"] and o["geo_note"] and not o["nogeo"]
