"""A synthetic site for the 👥 Audience tab tests — made-up apps, ids, accounts and numbers only (no real data).

make_world(root) writes what admob_iq.audience_build reads, in the shapes the earlier build steps write them:
  * site/uninstall.json.gz (per app: key, launch, survival.all.left, flags.incomplete_days / estimated_days; no_ga4),
    site/uninstall_c_<key>.json.gz (install day × lag cells), site/active_portfolio.json.gz (a1 / new / rev per day);
  * data/ga4_uninstall/<key>.json.gz (history_start, daily new / un / a1 / a28, cohorts, ret, ret_from) and
    data/ga4_uninstall/iday/<key>.json.gz (x: install-day long-term opens, days: age bands on each activity day);
  * data/ga4_audience/<key>.json.gz — a COMPLETE tiered store for one app, a partial-only read for another;
  * site/active_<key>.json.gz — the Active users tab's per-app file, only the daily arrays the calculator reads (a1, rev,
    AdMob impressions, GA4 usage per new / returning / other slot; Demo Timer has incomplete usage days);
and returns the dashboard (in memory, as dashboard.json.gz would hold it).

  Demo Gallery · Studio Nine   500 days, a complete GA4 Audience store (tiered months)      → "ga4"
  Demo Notes                   420 days, no Audience store, install-day data (money its own) → "andaza"
  Demo Timer · A/c 77          210 days, a partial GA4 read only (no complete result yet)    → "andaza", being read
  Demo Young                   45 days, no install-day data (money from the all-apps typical) → "andaza"
  Demo Broken                  its cohort file is missing                                    → left out (counted)
"""

import gzip
import hashlib
import json
import math
import os
from datetime import date, timedelta

from admob_iq.engine import audience as aud_eng
from admob_iq.engine import uninstall as ueng

E = date(2026, 9, 20)                         # the Active users tab's settled day (the Audience day E)
GEN = "2026-09-23T06:30:00Z"
FX = 83.5
ULAGS = (0, 1, 3, 7, 14, 30, 45, 60, 90, 120, 180, 270, 365)
APPS = (
    # app id, name, account id, days of history, installs a day, has iday, audience store
    ("demo-9001~11", "Demo Gallery · Studio Nine", "demo-9001", 500, 900, True, "complete"),
    ("demo-9001~12", "Demo Notes", "demo-9001", 420, 400, True, None),
    ("demo-7700~21", "Demo Timer · A/c 77", "demo-7700", 210, 250, True, "partial"),
    ("demo-7700~22", "Demo Young", "demo-7700", 45, 120, False, None),
    ("demo-7700~23", "Demo Broken", "demo-7700", 120, 50, False, None),
)
NO_GA4 = [{"app": "Demo Clock", "app_id": "demo-7700~24", "reason": "no_package", "text": "made-up"}]


def key_of(app_id):
    return hashlib.sha1(app_id.encode()).hexdigest()[:12]


def iso(d):
    return d.isoformat()


def _wgz(p, body):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(body, f)


def un_share(lag):
    """Share of an install day's users who uninstall exactly `lag` days after install (≈ 55% within a year)."""
    if lag == 0:
        return 0.12
    return 0.10 * math.exp(-lag / 6.0) + 0.0012 * math.exp(-lag / 200.0)


def ret_rate(N):
    """Share of an install day's users who open the app on day N."""
    return 0.32 * N ** -0.55 if N else 1.0


def app_store(days, n0, seed):
    """The app's Uninstall store and its cells (install day × lag), all ending on E (+3 provisional days)."""
    hs = E - timedelta(days=days - 1)
    end = E + timedelta(days=3)
    daily, cohorts = {}, {}
    d = hs
    while d <= end:
        k = (d.toordinal() * 31 + seed) % 7
        daily[iso(d)] = {"new": int(n0 * (0.9 + 0.03 * k)), "un": 0, "a1": 0, "a28": 0, "un_ev": 0, "upd": 0}
        d += timedelta(days=1)
    for X, r in daily.items():
        Xd = date.fromisoformat(X)
        c = {}
        for lag in range(0, (end - Xd).days + 1):
            u = int(round(r["new"] * un_share(lag)))
            if u:
                c[str(lag)] = u
                daily[iso(Xd + timedelta(days=lag))]["un"] += u
        cohorts[X] = c
    # actives: day-N openers of every earlier install day (+ a steady old-user base)
    keys = sorted(daily)
    for i, D in enumerate(keys):
        a1 = 0
        for j in range(max(0, i - 400), i + 1):
            a1 += int(daily[keys[j]]["new"] * ret_rate(i - j))
        daily[D]["a1"] = a1
    for i, D in enumerate(keys):
        win = keys[max(0, i - 27):i + 1]
        daily[D]["a28"] = int(sum(daily[k]["new"] for k in win) * 0.95 + daily[D]["a1"] * 2.2)
    ret = {}
    for X in keys:
        Xd = date.fromisoformat(X)
        n = daily[X]["new"]
        ret[X] = {"ok": True, "t": n, "a": [n] + [int(n * ret_rate(N)) for N in range(1, 31)], "cov": 1.0}
    st = {"v": 3, "history_start": iso(hs), "window_end": iso(end), "daily": daily, "cohorts": cohorts, "ret": ret,
          "ret_from": iso(hs), "flags": {"incomplete_days": {}}, "unplaced": {}}
    return st


def cells(st):
    """The Uninstall tab's cohort file of a store (fill_days-filled, the tab's own file shape)."""
    f = ueng.fill_days(st)
    hs = date.fromisoformat(st["history_start"])
    keys = sorted(k for k in f["daily"] if k >= st["history_start"])
    return {"v": 2, "start": iso(hs), "end": keys[-1], "new": [f["daily"][k]["new"] for k in keys],
            "lags": [sorted([int(L), int(u)] for L, u in (f["cohorts"].get(k) or {}).items()) for k in keys],
            "unplaced": {}}


def survival(st):
    """survival.all.left[N]: share of installs still installed N days after install (install days old enough)."""
    left, ns = [], []
    for N in range(0, 400):
        num = den = 0
        for X, c in st["cohorts"].items():
            Xd = date.fromisoformat(X)
            if Xd + timedelta(days=N) > E:
                continue
            n = st["daily"][X]["new"]
            den += n
            num += sum(u for L, u in c.items() if int(L) <= N)
        if not den:
            break
        left.append(round(1 - num / den, 5))
        ns.append(den)
    return {"all": {"left": left, "n": ns}}


def iday_file(st, seed):
    """x: install day → {n, u[lag of ULAGS]} (opens at that lag); days: activity day → age bands of its actives."""
    x = {}
    for X, r in st["daily"].items():
        n = r["new"]
        x[X] = {"n": n, "u": [int(n * ret_rate(L)) for L in ULAGS]}
    days = {}
    keys = sorted(st["daily"])
    for D in keys[-60:]:
        a = st["daily"][D]["a1"]
        ab = [int(a * f) for f in (0.30, 0.10, 0.10, 0.20, 0.15, 0.10)]
        rev = 0.002 * a
        rb = [rev * f for f in (0.25, 0.10, 0.10, 0.22, 0.18, 0.15)]
        days[D] = {"a": a, "a4": int(a * 0.95), "ab": ab, "rb": rb, "rb_old": 0.0, "rev": rev}
    return {"x": x, "days": days, "to": iso(E)}


def audience_store(st, complete=True):
    """A GA4 Audience store consistent with the app's cells: per install day, alive(N) = installed × a rising share,
    act = alive + the window's uninstalls (every 7th day: fewer openers than window uninstallers — a clean-up clamp)."""
    f = ueng.fill_days(st)
    hs = date.fromisoformat(st["history_start"])
    months = aud_eng.tier_months((E - hs).days + 1)
    wins = [aud_eng.window_days(m) for m in months]
    by, dau = {}, {}
    for X, r in sorted(f["daily"].items()):
        Xd = date.fromisoformat(X)
        if Xd > E or Xd < hs:
            continue
        n, age = r["new"], (E - Xd).days
        lags = [(int(L), int(u)) for L, u in (f["cohorts"].get(X) or {}).items()]
        inst = n - sum(u for L, u in lags if L <= age)
        row = []
        for m, w in zip(months, wins):
            un_in = sum(u for L, u in lags if age - w + 1 <= L <= age)
            if age < w:
                row.append(n)
                continue
            alive = int(inst * min(1.0, 0.18 + 0.045 * m))
            act = alive + un_in
            if Xd.toordinal() % 7 == 0:
                act = max(0, un_in - 3)
            row.append(act)
        by[X] = row
        dau[X] = int(inst * (0.6 if age < 30 else 0.04))
    body = {"v": 2, "E": iso(E), "history_start": iso(hs), "months": months, "windows": wins, "by_fsd": by,
            "total": [sum(r[i] for r in by.values()) for i in range(len(wins))], "other": [0] * len(wins),
            "not_set": [0] * len(wins), "dau_by_fsd": dau, "dau": {"total": sum(dau.values()), "other": 0, "not_set": 0},
            "flags": {}, "calls": 3, "tokens": 40}
    if complete:
        return dict(body, complete=True)
    return {"v": 2, "partial": dict({k: body[k] for k in ("E", "history_start", "months", "windows")}, ranges={},
                                    calls=1, tokens=10, units=100, runs=1, started_at=GEN)}


def active_detail(st, pa, seed, inc_every=None):
    """The Active users tab's per-app file (engine.active's daily shape), only what the Audience calculator reads: a1 /
    new / rev / imp (its own eCPM) and GA4 usage per slot (u, s: new / returning / other). Every inc_every-th day's usage
    is incomplete: all its slots null (the tab's rule)."""
    keys = sorted(k for k in st["daily"] if k <= iso(E + timedelta(days=3)))
    ecpm = 3.0 + 0.7 * seed                       # $ per 1,000 impressions
    a1, new = pa["a1"], pa["new"]
    u = {g: [] for g in "nro"}
    s = {g: [] for g in "nro"}
    for i in range(len(keys)):
        if inc_every and i % inc_every == 0:
            for g in "nro":
                u[g].append(None)
                s[g].append(None)
            continue
        nu, ru, ou = new[i], max(0, a1[i] - new[i]), a1[i] // 50
        for g, v, per in (("n", nu, 2.6), ("r", ru, 1.7 + 0.1 * seed), ("o", ou, 1.0)):
            u[g].append(v)
            s[g].append(int(round(v * per)))
    return {"app_id": pa["app_id"], "app": pa["app"], "key": pa["key"], "history_start": keys[0],
            "daily": {"start": keys[0], "a1": a1, "new": new, "rev": pa["rev"],
                      "imp": [int(round(r / ecpm * 1000)) for r in pa["rev"]], "u": u, "s": s}}


def make_world(root):
    """→ (data dir, site dir, dashboard)."""
    data, site = os.path.join(root, "data"), os.path.join(root, "site")
    os.makedirs(site, exist_ok=True)
    uapps, papps, rows, cat = [], [], [], []
    p_from = None
    for i, (aid, name, acc, days, n0, has_iday, aud) in enumerate(APPS):
        key = key_of(aid)
        st = app_store(days, n0, i + 1)
        _wgz(os.path.join(data, "ga4_uninstall", key + ".json.gz"), st)
        if name != "Demo Broken":
            _wgz(os.path.join(site, "uninstall_c_%s.json.gz" % key), cells(st))
        if has_iday:
            _wgz(os.path.join(data, "ga4_uninstall", "iday", key + ".json.gz"), iday_file(st, i))
        if aud:
            _wgz(os.path.join(data, "ga4_audience", key + ".json.gz"), audience_store(st, aud == "complete"))
        flags = {"incomplete_days": {}, "estimated_days": {}}
        if name == "Demo Notes":                    # one flagged day each way (day-wise flags)
            flags["incomplete_days"][iso(E - timedelta(days=100))] = 0.5
            flags["estimated_days"][iso(E - timedelta(days=200))] = 0.8
        uapps.append({"key": key, "app": name, "app_id": aid, "launch": {"day": st["history_start"], "hidden": False},
                      "survival": survival(st), "flags": flags, "lifetime": {"p": 0.5}})
        keys = sorted(k for k in st["daily"] if k <= iso(E + timedelta(days=3)))
        a1 = [st["daily"][k]["a1"] for k in keys]
        papps.append({"key": key, "app": name, "app_id": aid, "start": keys[0], "currency": "USD", "a1": a1,
                      "new": [st["daily"][k]["new"] for k in keys], "rev": [round(v * 0.0021, 4) for v in a1]})
        if name != "Demo Broken":
            _wgz(os.path.join(site, "active_%s.json.gz" % key),
                 active_detail(st, papps[-1], i + 1, inc_every=5 if name == "Demo Timer · A/c 77" else None))
        p_from = min(p_from or keys[0], keys[0])
        rows.append({"key": key, "app": name, "app_id": aid, "file": "active_%s.json.gz" % key,
                     "settled_till": iso(E), "data_till": iso(E + timedelta(days=3)), "status": "ok"})
        cat.append({"app_id": aid, "app_name": name, "account_id": acc, "selected": True})
    _wgz(os.path.join(site, "uninstall.json.gz"), {"v": 1, "apps": uapps, "no_ga4": NO_GA4, "consts": {"lag_days": 2}})
    _wgz(os.path.join(site, "active_portfolio.json.gz"), {"v": 1, "currency": "USD", "from": p_from, "apps": papps})
    dash = {"generated_at": GEN, "usd_inr": FX, "currency": "USD", "apps_catalog": cat,
            "apps": [{"name": c["app_name"], "account": c["account_id"]} for c in cat],
            "active": {"apps": rows, "portfolio": {"file": "active_portfolio.json.gz", "sig": "s1"}},
            "uninstall": {"asset": "uninstall.json.gz", "asset_v": "u1"}}
    return data, site, dash
