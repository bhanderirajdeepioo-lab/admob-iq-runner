"""A synthetic site for the 💸 Install value Studio tests — made by the REAL build code from synthetic GA4 / AdMob /
Google Ads inputs, no network, no real data (every app, name, package, id and amount is made up).

make_site(root) seeds tests.value_synth's three made-up apps (with their versions), runs the Google Ads country step
(admob_iq.fetch.gads_geo.geo_step against tests.test_gads_geo's fake API — each store's spend split over four countries
plus a small unmapped id) and then the build's own Uninstall + Install value step (build_static._uninstall_step, Active
users + Install value + versions + country cost on), and writes what the Studio step reads — value_<key>.json.gz and
the dashboard — plus dashboard.json.gz and the two names files, so the frozen demo reference
(tests/value_studio_reference.py) reads the very same inputs:

  * Demo Spend App · Studio Two         Google Ads spend (its cost per install jumps ×1.6), country cost on (geo), versions;
  * Demo Organic App · Studio Two       no Google Ads spend (organic), GA4 sample;
  * Demo Young App · Studio Two         a young app;
  * Demo Spend App · Studio Two         a second AdMob app with the SAME store name in the same account, no Play package →
    (no GA4)                            the GA4 one then reads "Demo Spend App (2026 wala) · Studio Two";
  * Demo Clock · A/c 3003               no Play package → "Lagu nahi" (no account name: the short publisher id).
The dashboard also carries made-up AdMob earnings per app (placements: the size class) and the Marketing ROAS daily
spend (roas.by_app — the KPI's daily spend line).
"""

import contextlib
import copy
import gzip
import io
import json
import os
import shutil
from datetime import timedelta
from unittest import mock

from admob_iq import build_static
from admob_iq import value_build as vb
from admob_iq.config import settings
from admob_iq.fetch import gads_geo as gg
from admob_iq.fetch import ga4_uninstall as gu
from tests import value_synth as vs

RUN = vs.RUNS[-1]
P1, P2 = "pub-7007000000000007", "pub-3003000000000003"
SPEND, ORG, YOUNG = (aid for aid, _, _, _ in vs.FIX_APPS)
TWIN, CLOCK = "ca-app-%s~201" % P1, "ca-app-%s~202" % P2
NAMES = {SPEND: "Demo Spend App", ORG: "Demo Organic App", YOUNG: "Demo Young App", TWIN: "Demo Spend App", CLOCK: "Demo Clock"}
ACCOUNT_NAMES = {P1: "Studio Two"}
APP_NAMES = {YOUNG: "Demo Young App"}
FX = 83.3
SHARE = {"2840": 0.30, "2356": 0.25, "2076": 0.20, "2826": 0.247, "9990001": 0.003}   # 9990001: no country → "XX"
EARN = {SPEND: 410.0, ORG: 36.0, YOUNG: 3.0}            # AdMob earnings a day (USD): the size classes


def _status(catalog):
    return {"counts": {"selected": len(catalog), "with_ga4": 3, "fetched": 0, "full": 0, "fresh": 3, "failed": 0,
                       "deferred": 0, "no_ga4": len(catalog) - 3}, "apps": {}, "no_ga4": {}, "discovery": None}


def _catalog():
    return [{"app_id": a, "app_name": NAMES[a] + (" · Studio Two" if a == TWIN else ""),
             "account_id": P2 if a == CLOCK else P1, "selected": True} for a in (SPEND, ORG, YOUNG, TWIN, CLOCK)]


def _updates(data, end):
    """The Spend app's GA4 store gets its app versions by day (two updates: 2.2 eleven weeks back, 2.3 five weeks back)
    → the build finds the releases (📦 on the Studio's timeline, the drawer's week table)."""
    from tests.uninstall_synth import rollout
    shares = rollout("2.1", [(end - timedelta(days=77), "2.2", 0.25), (end - timedelta(days=35), "2.3", 0.25)])
    path = gu.store_path(data, SPEND)
    st = gu.load_store(path)
    st["versions"] = {d: {v: int(x * (st["daily"][d].get("a1") or 0)) for v, x in shares(vs.date.fromisoformat(d)).items()}
                      for d in sorted(st["daily"])}
    gu.save_store(path, st)


def make_site(root):
    """→ (site dir, config dir, dashboard) — the dashboard exactly as dashboard.json.gz holds it."""
    from tests.test_gads_geo import FX as GFX, SETTINGS as GSET, TOK, Clock, FakeAds, M
    data, site, cfg = (os.path.join(root, x) for x in ("data", "site", "config"))
    for d in (site, cfg):
        os.makedirs(d, exist_ok=True)
    today = RUN.date()
    rev, made = vs.seed_build(data, end=today - timedelta(days=2), cd=True)
    _updates(data, today - timedelta(days=2))
    sp_path = os.path.join(data, vb.SPEND_FILE)
    with open(sp_path, encoding="utf-8") as f:
        spend = json.load(f)
    plan = {}
    for k, sid in enumerate(sorted(spend["daily"])):      # each store's campaigns in its own (made-up) account
        acct = "33300033%02d" % (31 + k)
        spend["campaigns"][sid] = [{"id": "c%d" % k, "name": "n", "status": "ENABLED", "cost_micros": 1,
                                    "account": acct, "account_name": ""}]
        dd = spend["daily"][sid]
        plan[acct] = {sid: {c: (lambda d, dd=dd, c=c: dd.get(d, 0) / M * SHARE[c]) for c in SHARE}}
    with open(sp_path, "w", encoding="utf-8") as f:
        json.dump(spend, f)
    with contextlib.redirect_stderr(io.StringIO()):
        gg.geo_step(GSET, data, spend, today, now=lambda: 1_800_000_000, clock=Clock(), search=FakeAds(plan).search,
                    token=TOK, fx_fn=GFX.get)
    s = dict(settings(), ga4_enabled=True, ga4_client_id="demo-cid", ga4_client_secret="demo-sec",
             ga4_refresh_tokens=json.dumps({"owner@studio.example.test": "rt-demo"}), ga4_refresh_token="",
             notify_dry_run=True, ga4_active=True, ga4_value=True, gads_geo=True, value_cd=True, impact_any=False)
    catalog = _catalog()
    lc = (today - timedelta(days=1)).isoformat()
    days = [(today - timedelta(days=1 + i)).isoformat() for i in range(10)]
    plc = [{"app": NAMES[a], "country": "All", "daily": [[d, int(EARN[a] * 1e6), 1000, 2000, 1800, 9] for d in days]}
           for a in (SPEND, ORG, YOUNG)]
    plc.append({"app": NAMES[SPEND], "country": "IN", "daily": [[days[0], int(999 * 1e6), 1, 1, 1, 0]]})   # never counted
    series = next(iter(made.values()))["fx"]["series"]
    by_app = {}
    for aid, m in made.items():
        dd = (m.get("spend") or {}).get("daily") or {}
        if dd:
            by_app[NAMES[aid]] = {"daily": {d: v * vs._fx_at(series, vs.date.fromisoformat(d)) for d, v in sorted(dd.items())}}
    dash = {"apps_catalog": catalog, "kpis": {"revenue": 1.0}, "alerts": {"items": []}, "placements": plc,
            "today_date": today.isoformat(), "latest_complete": lc, "generated_at": RUN.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "usd_inr": FX, "currency": "USD",
            "roas": {"configured": True, "by_app": by_app, "currency_src": "INR", "fx": {"INR": vs.FX0, "USD": 1.0}}}
    with mock.patch.object(gu, "refresh_all", lambda *a, **k: json.loads(json.dumps(_status(catalog)))), \
            contextlib.redirect_stderr(io.StringIO()):
        build_static._uninstall_step(dash, data, site, s, revenue=rev, now=RUN)
    dash = json.loads(json.dumps(dash))                    # as the file holds it
    for name, body in (("account_names.json", ACCOUNT_NAMES), ("app_names.json", APP_NAMES)):
        with open(os.path.join(cfg, name), "w", encoding="utf-8") as f:
            json.dump(body, f)
        shutil.copyfile(os.path.join(cfg, name), os.path.join(site, name))
    with gzip.open(os.path.join(site, "dashboard.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(dash, f)
    return site, cfg, dash


def copy_site(site, cfg, dash, root):
    """A fresh copy of a made site (each test may change it) → (site, cfg, dashboard)."""
    s2, c2 = os.path.join(root, "site"), os.path.join(root, "config")
    shutil.copytree(site, s2)
    shutil.copytree(cfg, c2)
    return s2, c2, copy.deepcopy(dash)
