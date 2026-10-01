"""A synthetic site for the 🧭 Active users Studio tests — made by the REAL build code from a synthetic GA4, no network,
no real data (every app, name, account and id is made up).

make_site(root) runs admob_iq.uninstall_build.run_uninstall (Active users on, AdMob revenue passed in, like the hourly
build) on these apps and writes what the Studio step reads — active_<key>.json.gz, active_portfolio.json.gz,
uninstall.json.gz — plus dashboard.json.gz and the two names files, so the frozen demo reference
(tests/active_studio_reference.py) reads the very same inputs:

  * Demo Photos · Studio One      big (kamai + ads kharcha $300+/din); its older users fall −14% for the newest 16 days
                                  → a real loss (asli badlaav) and the engine's returning-users alert; an update 2.1
  * Demo Notes · Studio One       its older users rise +12% for the newest 16 days → a real gain
  * Demo Torch · A/c 4004         older users steady, its installs double for the newest 16 days → the change is mostly
                                  "installs ki wajah se"
  * Demo Young · A/c 4004         60 days of history: no normal before a 60-day range (naya app)
  * Demo Photos · Studio One      a second AdMob app with the SAME store name in the same account, no Play package →
    (no GA4)                      "Lagu nahi"; the GA4 one then reads "Demo Photos (2025 wala) · Studio One"
  * Demo Clock · A/c 4004         no Play package → "Lagu nahi"
"""

import copy
import gzip
import json
import os
import shutil
from datetime import datetime, timedelta, timezone

from admob_iq import uninstall_build as ub
from admob_iq.config import settings
from admob_iq.fetch import ga4_uninstall as gu
from tests.uninstall_synth import END, make_active_store, rollout

NOW = datetime(END.year, END.month, END.day, 6, 30, tzinfo=timezone.utc) + timedelta(days=2)
PID, SID, EMAIL = "777000777", "5550001111", "owner@activestudio.example.test"
A1, A2 = "demo-3003", "demo-4004"        # two made-up AdMob accounts (publisher ids)
G1, N1, T1, Y1, G2, C1 = ("%s~%d" % (a, n) for a, n in ((A1, 31), (A1, 32), (A2, 41), (A2, 42), (A1, 33), (A2, 43)))
PKG = {G1: "com.activestudio.photos", N1: "com.activestudio.notes", T1: "com.activestudio.torch",
       Y1: "com.activestudio.young"}
NAMES = {G1: "Demo Photos", N1: "Demo Notes", T1: "Demo Torch", Y1: "Demo Young", G2: "Demo Photos", C1: "Demo Clock"}
ACCOUNT_NAMES = {A1: "Studio One"}
APP_NAMES = {T1: "Demo Torch"}
FX = 83.2
JUMP = END - timedelta(days=15)               # the newest 16 days


def stores():
    out = {}
    specs = (
        (G1, dict(days=300, new=900, old=lambda d: 30000 * (0.86 if d >= JUMP else 1.0), seed=31,
                  versions=rollout("2.0", [(END - timedelta(days=17), "2.1", 0.25)]))),
        (N1, dict(days=300, new=700, old=lambda d: 18000 * (1.12 if d >= JUMP else 1.0), seed=32)),
        (T1, dict(days=300, new=lambda d: 1200 if d >= JUMP else 600, old=9000, seed=33)),
        (Y1, dict(days=60, new=300, old=2500, seed=34)),
    )
    for aid, kw in specs:
        days = kw.pop("days")
        st, rv = make_active_store(days, noise=0.01, hll=0.01, rev_tz="America/Los_Angeles", **kw)
        st.update(app_id=aid, package=PKG[aid], property_id=PID, stream_id=SID)
        out[aid] = (st, rv)
    return out


def dashboard():
    cat = [{"app_id": a, "app_name": NAMES[a] + (" · Studio One" if a == G2 else ""),
            "account_id": A1 if a in (G1, N1, G2) else A2, "selected": True} for a in (G1, N1, T1, Y1, G2, C1)]
    lc = (END + timedelta(days=1)).isoformat()
    days = [(END + timedelta(days=1 - i)).isoformat() for i in range(10)]
    earn = {G1: 260.0, N1: 45.0, T1: 4.0}                  # USD a day (AdMob)
    plc = [{"app": NAMES[a], "country": "All", "daily": [[d, int(earn[a] * 1e6), 1000, 2000, 1800, 9] for d in days]}
           for a in (G1, N1, T1)]
    plc.append({"app": NAMES[G1], "country": "IN", "daily": [[days[0], int(999 * 1e6), 1, 1, 1, 0]]})   # never counted
    return {"apps_catalog": cat, "kpis": {"revenue": 1.0}, "alerts": {"items": []}, "placements": plc,
            "today_date": (END + timedelta(days=2)).isoformat(), "latest_complete": lc,
            "generated_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "usd_inr": FX, "currency": "USD",
            "value": {"spend_ccy": "INR", "apps": [{"app_id": G1, "src_ccy": "INR", "cpi": {"spend4_src": 28 * 60 * FX}},
                                                    {"app_id": N1, "cpi": {"spend4_src": 0}}]}}


def settings_on(**kw):
    s = dict(settings(), ga4_enabled=True, ga4_client_id="cid", ga4_client_secret="sec",
             ga4_refresh_tokens=json.dumps({EMAIL: "rt-x"}), ga4_refresh_token="", notify_dry_run=True,
             ga4_active=True, ga4_value=False, impact_any=False)
    s.update(kw)
    return s


def make_site(root):
    """→ (site dir, config dir, dashboard) — the dashboard exactly as dashboard.json.gz holds it."""
    data, site, cfg = (os.path.join(root, x) for x in ("data", "site", "config"))
    for d in (os.path.join(data, "ga4_uninstall"), site, cfg):
        os.makedirs(d, exist_ok=True)
    with open(os.path.join(data, "app_store_ids.json"), "w", encoding="utf-8") as f:
        json.dump({"by_id": PKG}, f)
    S = stores()
    for aid, (st, _) in S.items():
        gu.save_store(gu.store_path(data, aid), st)
    state = gu._state_default()
    state["routes"].update(fetched_at="2026-09-20T01:00:00Z", by_package={
        p: {"property_id": PID, "stream_id": SID, "owner": EMAIL} for p in PKG.values()})
    state["tz"] = {PID: "Asia/Kolkata"}
    state["eval"] = {a: {"end": (END - timedelta(days=1)).isoformat(), "stage": "stable", "stable_hold": 0,
                         "streak": {"cohort|up": 1, "cohort|down": 1, "drift|up": 3, "drift|down": 3}} for a in S}
    gu.save_state(data, state)
    status = {"counts": {"selected": 6, "with_ga4": 4, "fetched": 0, "full": 0, "fresh": 4, "failed": 0, "deferred": 0,
                         "no_ga4": 2}, "apps": {a: "fresh" for a in S}, "no_ga4": {}, "discovery": None}
    old = gu.refresh_all
    gu.refresh_all = lambda *a, **k: copy.deepcopy(status)
    try:
        till = (END + timedelta(days=1)).isoformat()
        rev = {"tz": "America/Los_Angeles", "currency": "USD", "till": till,
               "apps": {a: {k: v for k, v in rv["days"].items() if k <= till} for a, (_, rv) in S.items()}}
        dash = dashboard()
        ub.run_uninstall(dash, data, site, settings_on(), now=NOW, revenue=rev)
    finally:
        gu.refresh_all = old
    dash = json.loads(json.dumps(dash))                    # as the file holds it
    for name, body in (("account_names.json", ACCOUNT_NAMES), ("app_names.json", APP_NAMES)):
        with open(os.path.join(cfg, name), "w", encoding="utf-8") as f:
            json.dump(body, f)
        shutil.copyfile(os.path.join(cfg, name), os.path.join(site, name))
    with gzip.open(os.path.join(site, "dashboard.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(dash, f)
    return site, cfg, dash
