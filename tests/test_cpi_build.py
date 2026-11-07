"""📉 CPI vs eCPM — the build step (admob_iq.cpi_build) on made-up apps whose truth is known (closed forms + ±1 %
deterministic noise, xorshift32): the files and the pointer in the shapes the page reads (tests/cpx_fixture.js), the
data day, the page-side sums equal the engine's inputs, money lost = the page's formula, unknown days stay null, the
alerts go out once (the first build seeds), byte-identical re-runs, the switch, failure isolation, one _headers splat
rule, the counts-only line and the build_static wiring. No real data: apps "Alpha App" … with synthetic ids.

  calendar: data 2025-10-01 … 2026-03-30 (today, IST); the build at 2026-03-30 10:52 IST → t = 2026-03-28 (today − 2)
  Alpha  ₹50,000 a day at ₹20 per install; from 2026-03-10 1,600 installs a day (CPI ₹31.25), D0 ROAS 40 % → 30 %,
         eCPM $6 → $5 (an Alarm); two campaigns, two countries + not split; GA4 + ROI site files
  Beta   ₹20,000 a day, steady (OK) · Delta first spend 2026-03-20 (New) · Epsilon stops after 2026-03-24 (Paused)
  Hidden not selected in Settings, and one store id with no AdMob app: both "not linked" spend
"""
import copy
import gzip
import json
import math
import os
import re
import zlib
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import build_static as bs
from admob_iq import cpi_build as cb
from admob_iq import health
from admob_iq.config import settings
from admob_iq.db import write_json_gz_stable
from admob_iq.deploy_guard import HEADERS_MAX_RULES, headers_cover, headers_rule_count
from admob_iq.engine import cpi_alarm as CA
from admob_iq.engine import level_agent as LA
from admob_iq.fetch import ga4_uninstall as gu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 3, 30, 5, 22, tzinfo=timezone.utc)            # 10:52 IST → t = 2026-03-28
DAY0, TODAY, T, C = "2025-10-01", "2026-03-30", "2026-03-28", "2026-03-10"
FX1 = 0.012                                                         # USD per ₹, the one rate (roas.fx.INR)
ACCT = "1110001111"
IDS = {k: "ca-app-pub-0000000000000000~%d" % (21 + i) for i, k in enumerate("abdeh")}
NAMES = {"a": "Alpha App", "b": "Beta App", "d": "Delta App", "e": "Epsilon App", "h": "Hidden App"}
SIDS = {k: "com.synth." + k for k in NAMES}
UNLINKED = "com.synth.unlinked"


def fxd(x):
    """The day's own rate: 0.0122 / 0.0118 on alternate days."""
    return 0.0122 if (date.fromisoformat(x) - date.fromisoformat(DAY0)).days % 2 == 0 else 0.0118


def days(a, b):
    out, d = [], date.fromisoformat(a)
    while d.isoformat() <= b:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def prng(seed):
    x = seed & 0xFFFFFFFF or 1
    while True:
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        yield (x / 0xFFFFFFFF) * 2.0 - 1.0


def model(k, x, g):
    """One app's day: ₹ cost, installs, ₹ D0 value, impressions, eCPM $, GA4 users (±1 % noise on the counts)."""
    f = (lambda: 1.0 + 0.01 * next(g))
    if k == "a":
        m = {"sp": 50000.0, "inst": 1600.0 if x >= C else 2500.0, "roas": 0.30 if x >= C else 0.40, "imp": 50000.0,
             "ecpm": 5.0 if x >= C else 6.0, "dau": 20000.0}
    elif k == "b":
        m = {"sp": 20000.0, "inst": 2000.0, "roas": 0.35, "imp": 20000.0, "ecpm": 3.0, "dau": 8000.0}
    elif k == "d":
        on = x >= "2026-03-20"
        m = {"sp": 8000.0 if on else 0.0, "inst": 400.0 if on else 0.0, "roas": 0.20, "imp": 4000.0 if on else 0.0,
             "ecpm": 2.0, "dau": 1000.0}
    elif k == "e":
        on = x <= "2026-03-24"
        m = {"sp": 6000.0 if on else 0.0, "inst": 400.0 if on else 0.0, "roas": 0.30, "imp": 3000.0, "ecpm": 2.5,
             "dau": 900.0}
    else:
        m = {"sp": 5000.0, "inst": 250.0, "roas": 0.30, "imp": 2000.0, "ecpm": 2.0, "dau": 500.0}
    m["inst"] = round(m["inst"] * f(), 2) if m["inst"] else 0.0
    m["d0"] = round(m["sp"] * m["roas"] * f(), 2) if m["sp"] else 0.0
    m["imp"] = int(m["imp"] * f()) if m["imp"] else 0
    m["rev"] = round(m["imp"] * m["ecpm"] / 1000.0 * f(), 2)
    m["dau"] = int(m["dau"] * f())
    return m


def make(tmp_path, fixed_till="2026-03-29", ok_till="2026-03-29", geo_till="2026-03-27", camp_till="2026-03-29",
         day0=DAY0, mdl=None):
    """→ (data dir, site dir, dashboard): the stores and this build's site files written, the dashboard in memory
    (day0 / mdl: an earlier first day and another model of the apps' days)."""
    data, site = tmp_path / "data", tmp_path / "site"
    data.mkdir(parents=True, exist_ok=True)
    site.mkdir(parents=True, exist_ok=True)
    ALL = days(day0, TODAY)
    M = {}
    for i, k in enumerate(NAMES):
        g = prng(101 + i)
        M[k] = {x: (mdl or model)(k, x, g) for x in ALL}
    cache = {"v": 2, "currency_src": "INR", "fx": {"USD": 1.0, "INR": FX1}, "daily": {}, "installs": {},
             "convval": {}, "convval_day1": {}, "campaigns": {}}
    by_app, placements, catalog, cdaily = {}, [], [], {}
    for k, nm in NAMES.items():
        sid = SIDS[k]
        cache["daily"][sid], cache["installs"][sid], cache["convval_day1"][sid] = {}, {}, {}
        e = {"store_id": sid, "daily": {}, "daily_dated": {}, "installs_daily": {}, "convval_day1_daily": {},
             "campaigns": []}
        rows = []
        for x in ALL:
            m = M[k][x]
            if m["sp"] > 0:
                cache["daily"][sid][x] = int(m["sp"] * 1e6)
                cache["installs"][sid][x] = m["inst"]
                cache["convval_day1"][sid][x] = m["d0"]
                e["daily"][x] = int(round(m["sp"] * FX1 * 1e6))
                e["daily_dated"][x] = int(round(m["sp"] * fxd(x) * 1e6))
                e["installs_daily"][x] = m["inst"]
                e["convval_day1_daily"][x] = round(m["d0"] * FX1, 6)
            if m["imp"] > 0:
                rows.append([x, int(round(m["rev"] * 1e6)), m["imp"], m["imp"] * 2, m["imp"] * 2, 10])
        by_app[nm] = e
        placements.append({"id": "ca-app-pub-0000000000000000/%d" % (1000 + len(placements)), "name": nm + " banner",
                           "app": nm, "account": "pub-0000000000000000", "format": "banner", "daily": rows})
        catalog.append({"account_id": "pub-0000000000000000", "app_id": IDS[k], "app_name": nm, "rev": 1,
                        "selected": k != "h", "account_decided": True})
    cache["daily"][UNLINKED] = {x: int(1000 * 1e6) for x in ALL}
    camps = {"9000000001": ("a", 0.7, "Alpha tROAS"), "9000000002": ("a", 0.3, "Alpha tCPA"),
             "9000000003": ("b", 1.0, "Beta tROAS")}
    for cid, (k, q, nm) in camps.items():
        cache["campaigns"].setdefault(SIDS[k], []).append({"id": cid, "name": nm, "status": "ENABLED",
                                                          "cost_micros": 1, "account": ACCT, "account_name": "Synth"})
    by_app[NAMES["a"]]["campaigns"] = cache["campaigns"][SIDS["a"]]
    by_app[NAMES["b"]]["campaigns"] = cache["campaigns"][SIDS["b"]]
    # AdMob country (gross): Alpha 60 % XA, 40 % XB
    cdaily[NAMES["a"]] = {cc: [[x, int(M["a"][x]["rev"] * q * 1e6), int(M["a"][x]["imp"] * q), 0, 0, 0]
                               for x in ALL] for cc, q in (("XA", 0.6), ("XB", 0.4))}
    with open(data / "roas_spend_cache.json", "w") as f:
        json.dump(cache, f)
    with open(data / "roas_spend_fetch.json", "w") as f:
        json.dump({"ok_till": ok_till}, f)
    with open(data / "fx_series.json", "w") as f:
        json.dump({"INR": {x: fxd(x) for x in ALL}}, f)
    # Google Ads campaign × day (raw INR) and country × day (INR, DOWNLOAD conversions)
    mon = {}
    for cid, (k, q, _) in camps.items():
        for x in ALL:
            m = M[k][x]
            f = mon.setdefault(x[:7], {"v": 1, "month": x[:7], "camp": {}, "ccy": {ACCT: "INR"}, "cost": {},
                                       "inst": {}, "cv": {}, "cv1": {}})
            f["camp"][cid] = {"s": SIDS[k], "a": ACCT}
            f["cost"].setdefault(cid, {})[x] = int(m["sp"] * q * 1e6)
            f["inst"].setdefault(cid, {})[x] = round(m["inst"] * q, 2)
            f["cv1"].setdefault(cid, {})[x] = round(m["d0"] * q, 2)
    cd = data / "ads_campaign_day"
    cd.mkdir(exist_ok=True)
    for m, f in mon.items():
        write_json_gz_stable(str(cd / (m + ".json.gz")), f)
    write_json_gz_stable(str(cd / "state.json.gz"), {"v": 1, "first": day0, "till": camp_till, "done": True})
    geo = {}
    for k, split in (("a", (("XA", 0.6), ("XB", 0.35), ("XX", 0.05))), ("b", (("XA", 1.0),))):
        for x in ALL:
            m = M[k][x]
            g = geo.setdefault(x[:7], {"v": 1, "month": x[:7], "ccy": "INR", "days": {}})
            g["days"].setdefault(SIDS[k], {})[x] = {cc: [int(m["sp"] * q * 1e6), round(m["inst"] * q, 2)]
                                                    for cc, q in split}
    gd = data / "ads_geo_day"
    gd.mkdir(exist_ok=True)
    for m, g in geo.items():
        write_json_gz_stable(str(gd / (m + ".json.gz")), g)
    write_json_gz_stable(str(gd / "state.json.gz"), {"v": 1, "ccy": "INR", "first": day0, "till": geo_till})
    # this build's GA4 / ROI site files (Alpha and Beta) + their pointers
    act, nvr, roi = [], {}, {}
    for k in ("a", "b"):
        aid, key = IDS[k], gu.file_key(IDS[k])
        till = "2026-03-27"
        a1 = [M[k][x]["dau"] for x in days(day0, till)]
        write_json_gz_stable(str(site / ("active_%s.json.gz" % key)), {"daily": {"start": day0, "a1": a1},
                                                                       "data_till": till})
        act.append({"app_id": aid, "key": key, "file": "active_%s.json.gz" % key})
        nd = []
        for x in days(day0, TODAY):
            m = M[k][x]
            fs = 0.3
            nd.append([x, [round(m["rev"] * fs * 0.8, 4), int(m["imp"] * fs), round(m["rev"] * (1 - fs * 0.8), 4),
                           int(m["imp"] * (1 - fs)), 0, 0], [100, int(m["inst"] * 1.1), 400, m["dau"]], {}, {}])
        write_json_gz_stable(str(site / ("nvr_%s.json.gz" % key)), {"days": nd, "final_till": till})
        nvr[aid] = {"file": "nvr_%s.json.gz" % key}
        rows = []
        for x in days(day0, "2026-03-29"):
            m = M[k][x]
            age = (date.fromisoformat(TODAY) - date.fromisoformat(x)).days
            df = max(0, min(31, age - 2))
            sp = round(m["sp"] * fxd(x), 2)
            r0 = round(sp * m["roas"] * 0.9, 4)
            cum = [round(r0 * q, 4) for q in (1.0, 1.2, 1.4, 1.5, 1.6, 1.7, 1.75, 1.8)]     # ages 0 … 7
            rows.append([x, int(m["inst"] * 1.1), m["inst"], sp, cum, df])
        write_json_gz_stable(str(site / ("roi_%s.json.gz" % key)), {"rows": rows})
        roi[aid] = {"file": "roi_%s.json.gz" % key}
    dash = {"usd_inr": 1 / FX1, "latest_complete": "2026-03-29", "today_date": TODAY, "apps_catalog": catalog,
            "placements": placements, "countries_daily": cdaily, "alerts": {"items": []},
            "roas": {"configured": True, "by_app": by_app, "currency_src": "INR", "fx": {"INR": FX1},
                     "spend_fx": "dated", "d0": {"fixed_till": fixed_till}},
            "active": {"apps": act}, "nvr": {"apps": nvr}, "roi": {"apps": roi}}
    return str(data), str(site), dash


@pytest.fixture(scope="module", autouse=True)
def agent_off():
    """Every test of this file keeps its meaning from before the level agent (mode "off"); the agent's own tests
    switch it on."""
    mp = pytest.MonkeyPatch()
    mp.setattr(cb, "agent_cfg", lambda: dict(CA.P_PROD["levels"]["agent"], mode="off"))
    yield
    mp.undo()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cpi")
    data, site, dash = make(tmp)
    (tmp / "site" / "cpi_0123456789ab.json.gz").write_bytes(b"stale")
    paths = cb.run(dash, data, site, {}, NOW)
    line = cb.pop_line()
    return {"data": data, "site": site, "dash": dash, "paths": paths, "line": line}


def load(site, fn):
    with gzip.open(os.path.join(site, fn), "rt", encoding="utf-8") as f:
        return json.load(f)


def nd(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days + 1


def at(arr, day0, x):
    i = (date.fromisoformat(x) - date.fromisoformat(day0)).days
    return arr[i] if 0 <= i < len(arr) else None


def addd(x, k):
    return (date.fromisoformat(x) + timedelta(days=k)).isoformat()


# ── files + pointer ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_run_writes_files_pointer_and_removes_stale(built):
    site, p = built["site"], built["dash"]["cpi"]
    assert built["paths"] == ["/cpi*"] == cb.HEADER_PATHS
    keys = {k: gu.file_key(IDS[k]) for k in "abde"}
    files = sorted(f for f in os.listdir(site) if f.startswith("cpi"))
    assert files == sorted(["cpi.json.gz"] + ["cpi_%s.json.gz" % v for v in keys.values()])      # stale one gone
    assert sorted(p) == ["alerts", "apps", "at", "closed", "counts", "day0", "file", "fv", "la", "t", "till", "unlinked",
                         "v"]
    assert p["la"] is None                                                          # no owner action read
    assert (p["v"], p["t"], p["file"], p["at"]) == (1, T, "cpi.json.gz", "2026-03-30T05:22:00Z")
    assert p["till"] == {"spend": "2026-03-29", "d0": "2026-03-29", "admob": "2026-03-29", "ga4": "2026-03-27"}
    assert re.fullmatch(r"[0-9a-f]{12}", p["fv"])
    assert sorted(p["apps"]) == sorted(IDS[k] for k in "abde")                     # Hidden: not on this screen
    for k, key in keys.items():
        a = p["apps"][IDS[k]]
        assert sorted(a) == ["file", "key", "lost", "lp", "name", "nrm", "open", "since", "st", "to", "v"]
        assert (a["name"], a["key"], a["file"]) == (NAMES[k], key, "cpi_%s.json.gz" % key)
        assert re.fullmatch(r"[0-9a-f]{12}", a["v"])
    st = {k: p["apps"][IDS[k]]["st"] for k in "abde"}
    assert st == {"a": "alarm", "b": "ok", "d": "new", "e": "paused"}
    assert p["counts"] == {"alarm": 1, "watch": 0, "fixed": 0, "ok": 1, "new": 1, "paused": 1}
    a = p["apps"][IDS["a"]]
    assert C <= a["since"] <= addd(C, 3)
    fams = {o[0]: o for o in a["open"]}
    assert "ROAS_G" in fams and fams["ROAS_G"][2] == "ALERT" and len(fams["ROAS_G"]) == 6
    assert fams["ROAS_G"][5] == pytest.approx(0.40, abs=0.01)                     # a PLAIN baseline (ratio)
    assert a["nrm"]["ROAS_G"] == pytest.approx(0.40, abs=0.01)                     # open: the frozen B
    assert a["nrm"]["CPI"] == pytest.approx(20.0, rel=0.03)                        # ₹ per install
    assert a["nrm"]["ECPM"] == pytest.approx(6.0, rel=0.03)                        # $ per 1000
    b = p["apps"][IDS["b"]]
    assert b["open"] == [] and b["since"] is None and b["lost"] is None
    assert b["nrm"]["CPI"] == pytest.approx(10.0, rel=0.02) and b["nrm"]["ROAS_G"] == pytest.approx(0.35, rel=0.02)
    d = p["apps"][IDS["d"]]
    assert d["nrm"] == {"CPI": None, "ECPM": None, "ROAS_G": None}


def test_unlinked_spend_is_shipped_per_day_for_the_period_picked(built):
    """Every store id without a row (no AdMob app + Hidden): ₹ per day and $ at each day's own rate from the first day
    with such spend, the number of store ids, and each store id's runs of days — the page sums any period."""
    u = built["dash"]["cpi"]["unlinked"]
    assert sorted(u) == ["d0", "inr", "n", "runs", "usd"] and u["n"] == 2 and u["d0"] == DAY0
    assert len(u["inr"]) == len(u["usd"]) == nd(DAY0, T) and u["runs"] == [[[0, nd(DAY0, T) - 1]]] * 2
    for a, b in ((addd(T, -13), T), (addd(T, -29), addd(T, -15)), ("2025-12-01", "2025-12-31")):
        i0, i1 = nd(DAY0, a) - 1, nd(DAY0, b)
        assert sum(u["inr"][i0:i1]) == pytest.approx(6000.0 * nd(a, b), abs=0.01)         # whichever period is picked
        assert sum(u["usd"][i0:i1]) == pytest.approx(sum(6000.0 * fxd(x) for x in days(a, b)), abs=0.01 * nd(a, b))


def test_unlinked_spend_starts_at_its_first_day_and_keeps_each_store_ids_runs(tmp_path):
    data, site, dash = make(tmp_path)
    cache = json.load(open(os.path.join(data, "roas_spend_cache.json")))
    cache["daily"][UNLINKED] = {x: int(1000 * 1e6) for x in days("2026-03-01", "2026-03-10") + days("2026-03-20", T)}
    cache["daily"][SIDS["h"]] = {}
    cache["daily"]["com.synth.late"] = {x: int(500 * 1e6) for x in days("2026-03-05", "2026-03-06")}
    json.dump(cache, open(os.path.join(data, "roas_spend_cache.json"), "w"))
    cb.run(dash, data, site, {}, NOW)
    cb.pop_line()
    u = dash["cpi"]["unlinked"]
    assert u["d0"] == "2026-03-01" and len(u["inr"]) == nd("2026-03-01", T) and u["n"] == 2
    assert sorted(u["runs"]) == [[[0, 9], [19, nd("2026-03-01", T) - 1]], [[4, 5]]]       # a gap = two runs
    assert u["inr"][4] == 1500 and u["inr"][10] == 0 and u["inr"][19] == 1000
    for d in ({"d0": T, "inr": [], "usd": [], "n": 0, "runs": []},):                       # nothing unlinked at all
        cache["daily"] = {k: v for k, v in cache["daily"].items() if k.startswith("com.synth.") and k not in
                          (UNLINKED, SIDS["h"], "com.synth.late")}
        json.dump(cache, open(os.path.join(data, "roas_spend_cache.json"), "w"))
        dash2 = copy.deepcopy(dash)
        cb.run(dash2, data, site, {}, NOW)
        cb.pop_line()
        assert dash2["cpi"]["unlinked"] == d


def test_the_shapes_the_page_reads(built):
    site, p = built["site"], built["dash"]["cpi"]
    allb = load(site, "cpi.json.gz")
    assert sorted(allb) == ["apps", "day0", "t", "v"] and (allb["v"], allb["t"], allb["day0"]) == (1, T, p["day0"])
    n = nd(allb["day0"], T)
    for aid, x in allb["apps"].items():
        assert sorted(x) == ["ep", "h"] and sorted(x["h"]) == ["CPI", "ECPM", "ROAS_G"]
        assert all(len(v) == n and all(z is None or isinstance(z, int) for z in v) for v in x["h"].values())
        assert all(len(e) == 9 for e in x["ep"])                               # … the 9th: the baseline shown
    ha = allb["apps"][IDS["a"]]["h"]
    i = nd(allb["day0"], "2026-02-15") - 1
    assert ha["CPI"][i] == pytest.approx(2000, rel=0.03) and ha["ECPM"][i] == pytest.approx(60000, rel=0.03)
    assert ha["ROAS_G"][i] == pytest.approx(4000, rel=0.03)                     # scaled ints: ₹×100, $×10000, ×10000
    roas = [e for e in allb["apps"][IDS["a"]]["ep"] if e[0] == "ROAS_G"]
    assert roas and roas[-1][7] == pytest.approx(0.40, abs=0.01) and roas[-1][5] is None    # a plain base, open
    for k in "abde":
        a = p["apps"][IDS[k]]
        f = load(site, a["file"])
        assert sorted(f) == ["app_id", "camps", "ctys", "d", "day0", "ep", "key", "la", "lp", "lv", "name", "notes", "nrm",
                             "src", "t", "v"]
        assert (f["v"], f["app_id"], f["name"], f["key"], f["t"]) == (1, IDS[k], NAMES[k], a["key"], T)
        n = nd(f["day0"], T)
        assert sorted(f["d"]) == sorted(cb.ROWS) and all(len(v) == n for v in f["d"].values())
        assert sorted(f["nrm"]) == sorted(CA.OUT_FAMS) and all(len(v) == n for v in f["nrm"].values())
        assert all(isinstance(e, dict) and e["kind"] == "app" and e["id"] == IDS[k] for e in f["ep"])
        for c in f["camps"]:
            assert sorted(c) == ["bid", "d", "ep", "from", "id", "name", "status", "troas"]
            assert sorted(c["d"]) == ["d0_inr", "inst", "sp_inr", "sp_usd"]
            assert all(len(v) == nd(c["from"], T) for v in c["d"].values())
        for c in f["ctys"]:
            assert sorted(c) == ["cc", "d", "ep", "from", "nrm"] and sorted(c["d"]) == ["dl", "imp", "rev", "sp_inr", "sp_usd"]
            assert all(len(v) == nd(c["from"], T) for v in c["d"].values())
            assert sorted(c["nrm"]) == (["CPI", "ECPM"] if k == "a" else ["CPI"])   # (Beta: no AdMob country rows; no cube: no ROAS)
            assert all(len(v) == nd(c["from"], T) for v in c["nrm"].values())
        assert f["src"] == [] and "src" in f["notes"]
    fa = load(site, p["apps"][IDS["a"]]["file"])
    assert fa["day0"] == DAY0                                         # (first spend − 28 days, never before the data)
    assert [c["id"] for c in fa["camps"]] == ["9000000001", "9000000002"]           # most spend first
    assert [c["cc"] for c in fa["ctys"]] == ["XA", "XB"]                            # "XX" (not split) left to the rest
    assert fa["camps"][0]["name"] == "Alpha tROAS" and fa["camps"][0]["status"] == "ENABLED"
    i = nd(fa["day0"], "2026-02-15") - 1
    assert fa["nrm"]["CPI"][i] == pytest.approx(20.0, rel=0.03)                    # plain values
    roas_open = [e for e in fa["ep"] if e["fam"] == "ROAS_G" and e["closed"] is None][0]
    assert 0 < roas_open["max_worse"] < 1 and roas_open["tier"] == "ALERT"          # a relative fraction
    assert roas_open["money"]["since_c_inr"] > 0
    fd = load(site, p["apps"][IDS["d"]]["file"])
    assert fd["day0"] == addd("2026-03-20", -28)


def test_the_page_side_sums_equal_the_engine_inputs(built):
    """The page sums CPI / eCPM / D0 ROAS over a window from DATA (roas.by_app + placements); the build's per-day
    series (the engine's inputs, the per-app file) give the same sums."""
    site, dash, p = built["site"], built["dash"], built["dash"]["cpi"]
    a0, b0 = addd(T, -13), T
    for k in "abde":
        nm, f = NAMES[k], load(site, p["apps"][IDS[k]]["file"])
        e = dash["roas"]["by_app"][nm]
        win = [x for x in days(a0, b0)]
        page_inr = sum(e["daily"].get(x, 0) for x in win) / 1e6 / dash["roas"]["fx"]["INR"]     # ₹ as billed
        page_usd = sum(e["daily_dated"].get(x, 0) for x in win) / 1e6
        page_inst = sum(e["installs_daily"].get(x, 0) for x in win)
        page_v = sum(e["convval_day1_daily"].get(x, 0) for x in win) / dash["roas"]["fx"]["INR"]
        rev = sum(r[1] for q in dash["placements"] if q["app"] == nm for r in q["daily"] if a0 <= r[0] <= b0) / 1e6
        imp = sum(r[2] for q in dash["placements"] if q["app"] == nm for r in q["daily"] if a0 <= r[0] <= b0)

        def tot(key):
            return sum(at(f["d"][key], f["day0"], x) or 0 for x in win)
        assert tot("sp_inr") == pytest.approx(page_inr, rel=1e-6)
        assert tot("sp_usd") == pytest.approx(page_usd, rel=1e-6)
        assert tot("inst") == pytest.approx(page_inst, rel=1e-6)
        assert tot("d0_inr") == pytest.approx(page_v, rel=1e-5)
        assert tot("rev") == pytest.approx(rev, abs=0.01 * len(win)) and tot("imp") == imp
        w = cb.window({kk: f["d"][kk] for kk in ("sp_inr", "sp_usd", "inst", "rev", "imp", "d0_inr")},
                      date.fromisoformat(f["day0"]), a0, b0)
        if page_inst:
            assert w["CPI"] == pytest.approx(page_inr / page_inst, rel=1e-6)
            assert w["ROAS_G"] == pytest.approx(page_v / page_inr, rel=1e-5)
        if imp:
            assert w["ECPM"] == pytest.approx(rev / imp * 1000, rel=1e-3)


def test_money_lost_is_the_page_formula(built):
    """Σ over the days of [t − 13, t] inside the D0 ROAS alarm of cost − D0 value ÷ B: ₹ as billed, $ at each day's own
    rate (the bill's sp_usd ÷ sp_inr); "since c" = the same from the change start."""
    site, p = built["site"], built["dash"]["cpi"]
    a = p["apps"][IDS["a"]]
    f = load(site, a["file"])
    ep = [e for e in f["ep"] if e["fam"] == "ROAS_G" and e["closed"] is None][0]
    B = ep["base"]
    lo = max(addd(T, -13), ep["c"])

    def loss(a0):
        inr = usd = 0.0
        for x in days(a0, T):
            sp, su, v = (at(f["d"][kk], f["day0"], x) for kk in ("sp_inr", "sp_usd", "d0_inr"))
            inr += sp - v / B
            usd += su - v * (su / sp) / B
        return inr, usd
    inr, usd = loss(lo)
    assert a["lost"]["from"] == ep["c"] and a["lost"]["inr"] == pytest.approx(inr, rel=1e-4)
    assert a["lost"]["usd"] == pytest.approx(usd, rel=1e-4) and inr > 0
    sinr, susd = loss(ep["c"])
    assert a["lost"]["sc"]["inr"] == pytest.approx(sinr, rel=1e-4) and a["lost"]["sc"]["usd"] == pytest.approx(
        susd, rel=1e-4)
    # one model: 25 % less D0 value against a 40 % baseline → a quarter of the cost lost each day
    assert inr == pytest.approx(0.25 * 50000 * nd(lo, T), rel=0.05)


def test_unknown_days_after_the_last_good_fetch_stay_null(tmp_path):
    data, site, dash = make(tmp_path, ok_till="2026-03-25", geo_till="2026-03-22", camp_till="2026-03-24")
    assert cb.spend_ok_till(data, {}) == "2026-03-25" and cb.spend_ok_till(data, {"roas_spend_ok_till": "2026-03-26"}) \
        == "2026-03-26"                                                         # this build's own fetch wins
    cb.run(dash, data, site, {}, NOW)
    cb.pop_line()
    p = dash["cpi"]
    assert p["t"] == "2026-03-25" and p["till"]["spend"] == "2026-03-25"          # t never runs past the fetch
    f = load(site, p["apps"][IDS["a"]]["file"])
    assert f["t"] == "2026-03-25" and len(f["d"]["sp_inr"]) == nd(f["day0"], "2026-03-25")
    c = f["camps"][0]
    assert at(c["d"]["sp_inr"], c["from"], "2026-03-24") > 0
    assert at(c["d"]["sp_inr"], c["from"], "2026-03-25") is None                   # after the campaign store's till
    k = f["ctys"][0]
    assert at(k["d"]["sp_inr"], k["from"], "2026-03-22") > 0
    assert [at(k["d"][x], k["from"], "2026-03-23") for x in ("sp_inr", "sp_usd", "dl")] == [None] * 3
    assert f["notes"]["geo_till"] == "2026-03-22" and f["notes"]["camp_till"] == "2026-03-24"
    # the spend series itself: every day after the last good fetch null, never 0
    D = cb._Days(date(2026, 3, 20), date(2026, 3, 28))
    s = cb._spend(D, json.load(open(os.path.join(data, "roas_spend_cache.json"))), SIDS["a"], "2026-03-25",
                  [FX1] * D.n, None)
    assert [v is None for v in s["sp_inr"]] == [False] * 6 + [True] * 3 and s["inst"][-1] is None
    # no data day (a side unknown) → no tab
    dash2 = copy.deepcopy(dash)
    dash2["roas"]["d0"] = {}
    assert cb.run(dash2, data, site, {}, NOW) == [] and "cpi" not in dash2
    assert not [x for x in os.listdir(site) if x.startswith("cpi")] and cb.pop_line() == "cpi skipped: NoDataDay"
    assert health.SKIP.search("cpi skipped: NoDataDay")                         # (the red banner reads it)


def test_the_troas_target_from_the_archive(tmp_path):
    """data/ads_archive: daily snapshots (versions) + change events; before the first snapshot an UPDATE's old value
    holds from the archive's first event day; an ad group's event is not the campaign's target."""
    data, site, dash = make(tmp_path)
    ev1 = {"t": "2026-03-05 10:00:00", "rt": "CAMPAIGN", "op": "UPDATE", "f": ["status"], "c": "9000000002"}
    ev2 = {"t": "2026-03-12 09:00:00", "rt": "CAMPAIGN", "op": "UPDATE", "f": ["targetRoas.targetRoas"],
           "c": "9000000001", "old": {"targetRoas.targetRoas": 0.45}, "new": {"targetRoas.targetRoas": 0.55}}
    ev3 = dict(ev2, t="2026-03-13 09:00:00", rt="AD_GROUP", new={"targetRoas.targetRoas": 9.0})
    ev1["f"] = ["targetRoas.targetRoas"]
    arch = {"v": 1, "month": "2026-03", "acct": {ACCT: {
        "ver": {"camp/9000000001": [["2026-03-15", {"status": "ENABLED", "bidding_strategy_type": "TARGET_ROAS",
                                                    "target_roas.target_roas": 0.55, "name": "Alpha tROAS"}],
                                    ["2026-03-20", {"status": "ENABLED", "bidding_strategy_type": "TARGET_ROAS",
                                                    "target_roas.target_roas": 0.6, "name": "Alpha tROAS"}]],
                "camp/9000000002": [["2026-03-15", {"status": "PAUSED", "bidding_strategy_type": "TARGET_CPA"}]]},
        "days": {"2026-03-05": {"ev": [ev1]}, "2026-03-12": {"ev": [ev2]}, "2026-03-13": {"ev": [ev3]}}}}}
    os.makedirs(os.path.join(data, "ads_archive"))
    write_json_gz_stable(os.path.join(data, "ads_archive", "2026-03.json.gz"), arch)
    cb.run(dash, data, site, {}, NOW)
    cb.pop_line()
    f = load(site, dash["cpi"]["apps"][IDS["a"]]["file"])
    c1, c2 = f["camps"]
    assert c1["troas"] == [["2026-03-05", 0.45], ["2026-03-12", 0.55], ["2026-03-20", 0.6]]
    assert c1["bid"] == "TARGET_ROAS"
    assert c2["troas"] == [] and c2["bid"] == "TARGET_CPA" and c2["status"] == "ENABLED"    # (the spend cache's status)
    assert f["notes"]["troas_from"] == "2026-03-05"


def test_no_google_ads_no_tab(tmp_path):
    data, site, dash = make(tmp_path)
    (tmp_path / "site" / "cpi.json.gz").write_bytes(b"old")
    for d in ({}, {"roas": {"configured": False, "by_app": {}}}, dict(dash, roas={"configured": True, "by_app": {}})):
        assert cb.run(d, data, site, {}, NOW) == [] and "cpi" not in d
        assert cb.pop_line() == "cpi: apps 0" and not [x for x in os.listdir(site) if x.startswith("cpi")]


# ── alerts (sent once) ──────────────────────────────────────────────────────────────────────────────────────────────

def _live():
    return dict(settings(), notify_dry_run=False, telegram_token="tok", telegram_chat="chat", smtp={})


def _at(t):
    """The build's clock for data day t (today − 2 in IST)."""
    return datetime.fromisoformat(addd(t, 2) + "T05:22:00+00:00")


def test_the_first_build_seeds_and_a_new_alarm_goes_out_once(tmp_path, monkeypatch):
    data, site, dash0 = make(tmp_path)
    # where the D0 ROAS alarm opens (the replay never looks past t, so an earlier build sees it open that day)
    d = copy.deepcopy(dash0)
    cb.run(d, data, site, {}, NOW)
    opened = [o for o in d["cpi"]["apps"][IDS["a"]]["open"] if o[0] == "ROAS_G"][0][4]
    os.remove(cb.state_path(data))
    sent = []
    monkeypatch.setattr(bs.notifier, "send_telegram",
                        lambda text, tok, chat, dry: (sent.append(text), {"channel": "telegram", "status": 200,
                                                                          "dry_run": False})[1])
    monkeypatch.setattr(bs.notifier, "send_email", lambda subj, body, smtp, dry: {"channel": "email",
                                                                                  "status": "skipped"})
    s = _live()

    def build(t, minutes=0):
        dd = copy.deepcopy(dash0)
        cb.run(dd, data, site, s, _at(t) + timedelta(minutes=minutes))
        cb.pop_line()
        res = bs.send_alerts(dd, s)
        bs._uninstall_mark_sent(dd, data, s, res)
        return dd
    d1 = build(addd(C, -5))                                        # the first build: nothing open yet → seeds nothing
    assert d1["cpi"]["apps"][IDS["a"]]["st"] == "ok" and not sent
    d2 = build(addd(opened, -1))
    assert not any(a["notify"] for a in d2["cpi"]["alerts"] if a["severity"] == "warning")
    d3 = build(opened)                                             # the opening day: one push for the app
    al = [a for a in d3["cpi"]["alerts"] if a["app_id"] == IDS["a"]]
    assert len(al) == 1 and al[0]["severity"] == "warning" and al[0]["notify"] and not al[0]["seeded"]
    assert al[0]["source"] == "cpi" and al[0]["id"].startswith("cpi_")
    lines = [ln for txt in sent for ln in txt.split("\n") if ln.endswith(" · ads cost vs earning (Google Ads + AdMob)")]
    assert len(lines) == 1 and lines[0].startswith("🟠 [WARNING] Alpha App: ")
    for t, m in ((opened, 30), (opened, 60), (addd(opened, 1), 0), (addd(opened, 2), 0)):   # re-runs, next days
        dd = build(t, m)
        assert not any(a["notify"] for a in dd["cpi"]["alerts"])
    assert len([ln for txt in sent for ln in txt.split("\n") if "ads cost vs earning" in ln]) == 1
    st = json.load(open(cb.state_path(data)))
    assert st["push"] == {IDS["a"]: opened}


def test_the_first_build_with_open_alarms_shows_them_and_sends_nothing(tmp_path):
    data, site, dash = make(tmp_path)
    cb.run(dash, data, site, {}, NOW)
    cb.pop_line()
    al = dash["cpi"]["alerts"]
    assert al and all(a["seeded"] and not a["notify"] for a in al)
    a = [x for x in al if x["app_id"] == IDS["a"]][0]
    assert set(a) >= {"id", "source", "app_id", "app", "family", "severity", "opened", "opened_at", "alert_at", "since",
                      "now", "before", "rel", "notify", "seeded", "text", "message"}
    assert a["family"] == "ROAS_G" and a["severity"] == "warning" and a["before"] == pytest.approx(0.40, abs=0.01)
    assert "se normal se neeche" in a["text"] and "zyada kharch hua" in a["text"] and "₹" in a["message"]
    assert a["message"].startswith("Alpha App: D0 ROAS below normal since ")
    assert bs.send_alerts(dash, _live()) == []


def test_a_notice_whose_day_moved_with_restated_data_is_the_same_notice(tmp_path):
    st = {"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}}
    ep = {"kind": "app", "id": IDS["a"], "app": IDS["a"], "fam": "ROAS_G", "tier": "ALERT", "c": "2026-03-10",
          "opened": "2026-03-14", "closed": None, "why": None, "base": 0.4, "esc": []}
    apps = [{"app_id": IDS["a"], "view": {"eps": [ep]}}]
    led = cb._ledger(st, False, apps, date(2026, 3, 14), NOW)
    k, due = led[(IDS["a"], "ROAS_G", "2026-03-14")]
    assert due == ["open"]
    st["eps"][k]["notices"]["open"]["notified_at"] = "2026-03-16T05:00:00Z"
    ep2 = dict(ep, opened="2026-03-17", esc=[["2026-04-02", "step"]])                    # the opening moved 3 days
    led = cb._ledger(st, False, [{"app_id": IDS["a"], "view": {"eps": [ep2]}}], date(2026, 4, 2), NOW)
    k2, due = led[(IDS["a"], "ROAS_G", "2026-03-17")]
    assert k2 == k and due == ["2026-04-02"]                                             # only the re-notice is new
    st["eps"][k]["notices"]["2026-04-02"]["notified_at"] = "2026-04-04T05:00:00Z"
    ep3 = dict(ep2, esc=[["2026-04-04", "step"]])
    led = cb._ledger(st, False, [{"app_id": IDS["a"], "view": {"eps": [ep3]}}], date(2026, 4, 4), NOW)
    assert led[(IDS["a"], "ROAS_G", "2026-03-17")][1] == []                              # the same re-notice, moved
    old = dict(ep, closed="2026-03-20", why="recovered")                                 # a new episode after a close
    new = dict(ep, opened="2026-03-21")
    st2 = {"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}}
    cb._ledger(st2, False, [{"app_id": IDS["a"], "view": {"eps": [old]}}], date(2026, 3, 20), NOW)
    led = cb._ledger(st2, False, [{"app_id": IDS["a"], "view": {"eps": [new]}}], date(2026, 3, 23), NOW)
    assert led[(IDS["a"], "ROAS_G", "2026-03-21")] == ("%s|ROAS_G|2026-03-21" % IDS["a"], ["open"])    # its own push
    led = cb._ledger(st2, False, [{"app_id": IDS["a"], "view": {"eps": [dict(new, opened="2026-03-12")]}}],
                     date(2026, 3, 23), NOW)
    assert led[(IDS["a"], "ROAS_G", "2026-03-12")][1] == []        # first seen 11 days after its day: shown, never sent


# ── the step: re-runs, switch, failure, headers, log, wiring ────────────────────────────────────────────────────────

def test_re_runs_leave_every_file_byte_identical(tmp_path):
    data, site, dash = make(tmp_path)
    cb.run(dash, data, site, {}, NOW)
    cb.pop_line()

    def snap():
        out = {f: open(os.path.join(site, f), "rb").read() for f in os.listdir(site) if f.startswith("cpi")}
        out["state"] = open(cb.state_path(data), "rb").read()
        return out
    a, p1 = snap(), copy.deepcopy(dash["cpi"])
    _, _, dash2 = make(tmp_path)
    cb.run(dash2, data, site, {}, NOW + timedelta(minutes=30))
    cb.pop_line()
    assert snap() == a
    p2 = dash2["cpi"]
    assert {k: v for k, v in p1.items() if k != "at"} == {k: v for k, v in p2.items() if k != "at"}


def test_the_log_line_names_nothing(built):
    line = built["line"]
    assert re.fullmatch(r"cpi: apps \d+, alarm \d+, watch \d+, ok \d+, new \d+, paused \d+, episodes \d+, "
                        r"campaigns \d+, countries \d+", line), line
    assert line.startswith("cpi: apps 4, alarm 1, watch 0, ok 1, new 1, paused 1, ")
    for bad in list(NAMES.values()) + list(IDS.values()) + list(SIDS.values()) + ["₹", "$", "2026", "X"]:
        assert bad not in line


def test_any_failure_costs_this_tab_only(tmp_path, monkeypatch, capsys):
    data, site, dash = make(tmp_path)
    cb.run(dash, data, site, {}, NOW)
    cb.pop_line()
    other = os.path.join(site, "roi_%s.json.gz" % gu.file_key(IDS["a"]))
    before = open(other, "rb").read()
    monkeypatch.setattr(cb, "compute", lambda *a, **k: 1 / 0)
    d = copy.deepcopy(dash)
    assert cb.run(d, data, site, {}, NOW) == [] and "cpi" not in d and cb.pop_line() is None
    assert "cpi skipped: ZeroDivisionError" in capsys.readouterr().err
    assert not [x for x in os.listdir(site) if x.startswith("cpi")] and open(other, "rb").read() == before
    assert {k: v for k, v in d.items()} == {k: v for k, v in dash.items() if k != "cpi"}
    monkeypatch.setattr(cb, "run", lambda *a, **k: 1 / 0)
    d = {"cpi": {"v": 1}}
    assert bs._cpi_step(d, data, site, {}) == [] and "cpi" not in d
    assert "cpi skipped: ZeroDivisionError" in capsys.readouterr().err


def test_a_broken_campaign_store_costs_the_campaign_lines_only(tmp_path, monkeypatch, capsys):
    data, site, dash = make(tmp_path)
    from admob_iq.fetch import gads_campaign_day as gcd
    monkeypatch.setattr(gcd, "load", lambda *a, **k: 1 / 0)
    assert cb.run(dash, data, site, {}, NOW) == ["/cpi*"]
    assert "cpi campaigns skipped: ZeroDivisionError" in capsys.readouterr().err
    assert dash["cpi"]["apps"][IDS["a"]]["st"] == "alarm" and cb.pop_line().endswith("campaigns 0, countries 3")


def test_switched_off_the_site_is_exactly_as_without_the_tab(tmp_path):
    data, site, dash = make(tmp_path)
    before = {f: open(os.path.join(site, f), "rb").read() for f in os.listdir(site)}
    s = dict(settings(), cpi_tab=True)
    assert bs._cpi_step(dash, data, site, s) == ["/cpi*"] and "cpi" in dash
    d2 = {k: v for k, v in dash.items() if k != "cpi"}
    assert bs._cpi_step(d2, data, site, dict(s, cpi_tab=False)) == [] and "cpi" not in d2
    assert {f: open(os.path.join(site, f), "rb").read() for f in os.listdir(site)} == before
    assert cb.enabled({}) and not cb.enabled({"cpi_tab": False}) and cb.pop_line() is None


def test_headers_one_splat_rule_covers_the_files(built):
    base = bs.headers_text(["uninstall.json.gz"], built["dash"])
    text = bs.headers_text(["uninstall.json.gz"], built["dash"], extra=built["paths"])
    assert headers_rule_count(text) == headers_rule_count(base) + 1 <= HEADERS_MAX_RULES
    assert headers_cover(text, "cpi.json.gz") and headers_cover(text, "cpi_0123456789ab.json.gz")
    assert not headers_cover(base, "cpi.json.gz")
    assert "/cpi*\n  Cache-Control: no-store" in text


def test_settings_and_workflow_pass_the_switch(monkeypatch):
    y = open(os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8").read()
    assert "CPI_TAB:              ${{ vars.CPI_TAB || 'true' }}" in y
    monkeypatch.delenv("CPI_TAB", raising=False)
    assert settings()["cpi_tab"] is True
    monkeypatch.setenv("CPI_TAB", "false")
    assert settings()["cpi_tab"] is False and cb.enabled(settings()) is False


def test_build_static_runs_the_step_after_screens_and_before_health_and_alerts():
    src = open(os.path.join(ROOT, "admob_iq", "build_static.py"), encoding="utf-8").read()
    body = src[src.index("def build("):]
    i_s, i_c = body.index("_screens_step(dashboard"), body.index("aud_paths = aud_paths + _cpi_step(dashboard")
    i_h, i_d = body.index("health.attach(dashboard)"), body.index('_shipgz(out_dir, "dashboard.json", dashboard)')
    i_x, i_a = body.index("headers_text(uni_files"), body.index("send_alerts(dashboard, s)")
    assert i_s < i_c < i_h < i_d < i_x < i_a and "+ aud_paths + any_paths" in body
    assert '@_sc.timed("cpi_tab")' in src and "cpi_tab" in __import__("admob_iq.stage_clock").stage_clock.STAGES
    # the last good spend fetch day: recorded on every build (not only with the Install value tab on)
    i_r = body.index("s[\"roas_spend_ok_till\"] = record_spend_fetch(data_dir, today)")
    gate = body[body.rindex("\n", 0, body.rindex("if ", 0, i_r)):i_r]
    assert "ga4_value" not in gate and "not fresh_spend.get(\"error\")" in gate
    # the alerts: one more block in send_alerts, one more mark after it
    sa = src[src.index("def send_alerts("):src.index("def uninstall_delivered(")]
    assert "(dashboard.get(\"cpi\") or {}).get(\"alerts\", [])" in sa
    assert " · ads cost vs earning (Google Ads + AdMob)" in sa
    mk = src[src.index("def _uninstall_mark_sent("):src.index("class _AppFilteredRepo")]
    assert "mark_notified_cpi(data_dir, dashboard[\"cpi\"], dry=s[\"notify_dry_run\"], ids=ids)" in mk


def test_normal_follows_the_engine_and_falls_back_inside_the_period():
    """An episode counts as open until its close whatever the reason (settled too, as the engine's own normal); with
    none open at b, H on the day before a; a period that starts before H exists takes the first known H inside it."""
    d0 = date(2026, 1, 1)
    h = {"CPI": [None] * 40 + [20.0] * 60}
    ep = {"fam": "CPI", "opened": "2026-02-01", "closed": "2026-03-01", "why": "settled", "base": 15.0}
    assert cb.normal_at("CPI", [ep], h, d0, "2026-02-10", "2026-02-20") == 15.0       # open at b (settles later)
    assert cb.normal_at("CPI", [ep], h, d0, "2026-03-05", "2026-03-18") == 20.0       # closed by b → H(a − 1)
    assert cb.normal_at("CPI", [], h, d0, "2026-01-05", "2026-03-18") == 20.0         # H(a − 1) unknown → first inside
    assert cb.normal_at("CPI", [], h, d0, "2026-01-05", "2026-01-20") is None         # truly no healthy level yet


def test_money_lost_comes_from_the_d0_roas_alarm_only():
    """The list's money is the Google D0 ROAS alarm's (cost − D0 value ÷ B); an AdMob install-day (ROAS_C0) episode
    alone gives no money here — it is shown only in the details' Loss math."""
    d0 = date(2026, 1, 1)
    n = 30
    s = {"sp_inr": [1000.0] * n, "sp_usd": [10.0] * n, "d0_inr": [300.0] * n, "c_sp": [10.0] * n, "c_r0": [3.0] * n}
    c0 = {"fam": "ROAS_C0", "c": "2026-01-10", "closed": None, "base": 0.4, "tier": "LINE"}
    assert cb.money_lost([c0], s, [0.01] * n, d0, "2026-01-17", "2026-01-30", "2026-01-30") is None
    g = dict(c0, fam="ROAS_G", tier="ALERT")
    m = cb.money_lost([g, c0], s, [0.01] * n, d0, "2026-01-17", "2026-01-30", "2026-01-30")
    assert m["fam"] == "ROAS_G" and m["inr"] == pytest.approx(14 * (1000 - 300 / 0.4))
    assert m["sc"]["inr"] == pytest.approx(21 * (1000 - 300 / 0.4)) and m["from"] == "2026-01-10"


def test_an_alarm_that_closed_inside_the_period_is_fixed_not_alarm():
    """Alarm / Watch need an episode still open at the period's end; an ALERT that closed inside the period is "fixed"
    (shown with its span); a closed WATCH leaves the row ok; an episode opened after the period's end is not known
    then."""
    d0 = date(2026, 1, 1)
    s = {"sp_inr": [100.0] * 60}
    nrm = {"CPI": 10.0, "ROAS_G": 0.4}
    shut = {"tier": "ALERT", "fam": "ROAS_G", "c": "2026-02-01", "opened": "2026-02-04", "closed": "2026-02-10"}
    watch = {"tier": "WATCH", "fam": "ECPM", "c": "2026-02-02", "opened": "2026-02-05", "closed": None}
    late = {"tier": "ALERT", "fam": "CPI", "c": "2026-02-12", "opened": "2026-02-20", "closed": None}
    a, b, t = "2026-02-01", "2026-02-14", "2026-02-28"
    assert cb.status_of([shut], s, nrm, d0, a, b, t) == ("fixed", "2026-02-01")
    assert cb.status_of([shut, watch], s, nrm, d0, a, b, t) == ("watch", "2026-02-02")      # open Watch beats Fixed
    assert cb.status_of([shut, watch, late], s, nrm, d0, a, b, t) == ("watch", "2026-02-02")  # late: not opened by b
    assert cb.status_of([shut, watch, late], s, nrm, d0, a, "2026-02-28", t) == ("alarm", "2026-02-12")
    assert cb.status_of([dict(watch, closed="2026-02-09")], s, nrm, d0, a, b, t) == ("ok", None)


def test_a_baseline_that_was_a_peak_gives_way_to_the_healthy_level():
    """An open episode is shown against its frozen B unless B was more than 25 % better than the healthy level before
    the change (the 14 days before it were a peak) — then that H, for the row's normal and its money alike."""
    d0 = date(2026, 1, 1)
    h = {"ECPM": [9.0] * 90, "CPI": [20.0] * 90, "ROAS_G": [0.40] * 90}
    peak = {"fam": "ECPM", "c": "2026-02-20", "opened": "2026-02-24", "closed": None, "base": 20.0}
    fine = dict(peak, base=10.5)
    assert cb.base_of(peak, h, d0) == 9.0 and cb.base_of(fine, h, d0) == 10.5
    assert cb.base_of(dict(peak, fam="CPI", base=14.0), h, d0) == 20.0           # CPI: a cheap fortnight was a peak too
    assert cb.base_of(dict(peak, fam="CPI", base=17.0), h, d0) == 17.0
    assert cb.normal_at("ECPM", [peak], h, d0, "2026-03-01", "2026-03-14") == 9.0
    roas = dict(peak, fam="ROAS_G", base=0.60, tier="ALERT")                        # money against H, not the peak
    n = 31
    s = {"sp_inr": [1000.0] * n, "sp_usd": [10.0] * n, "d0_inr": [380.0] * n}
    m = cb.money_lost([roas], s, [0.01] * n, d0, "2026-01-18", "2026-01-31", "2026-01-31", h, d0)
    assert m is None                                                               # (c after b: nothing overlaps)
    roas2 = dict(roas, c="2026-01-20", opened="2026-01-23")
    m = cb.money_lost([roas2], s, [0.01] * n, d0, "2026-01-18", "2026-01-31", "2026-01-31", h, d0)
    assert m["inr"] == pytest.approx(12 * (1000 - 380 / 0.40))


def test_money_needs_the_alarm_opened_by_the_period_end_and_one_baseline_everywhere():
    """A period that ends before the D0 ROAS alarm opened shows no money (its status is ok then); every place that
    prices an episode uses the one shown baseline (_ep_row's 9th element, _ep_full's base_show)."""
    d0 = date(2026, 1, 1)
    n = 40
    s = {"sp_inr": [1000.0] * n, "sp_usd": [10.0] * n, "d0_inr": [300.0] * n}
    g = {"fam": "ROAS_G", "c": "2026-01-10", "opened": "2026-01-25", "closed": None, "base": 0.4, "tier": "ALERT"}
    assert cb.money_lost([g], s, [0.01] * n, d0, "2026-01-05", "2026-01-20", "2026-02-09") is None    # not opened yet
    assert cb.money_lost([g], s, [0.01] * n, d0, "2026-01-05", "2026-01-25", "2026-02-09")["inr"] > 0
    ep = dict(g, opener="SUDDEN", why=None, seen="2026-01-27", base_src="before", confirm=None, thr_open=0.12,
              max_worse=0.2, esc=[], ctx={}, money=None, stake=[], kind="app", id="x", app="x", base_show=0.35)
    assert cb._ep_row(ep)[7:] == [0.4, 0.35] and cb._ep_full(ep)["base_show"] == 0.35
    assert cb._ep_row({k: v for k, v in ep.items() if k != "base_show"})[8] == 0.4               # (no shown one: B)


# ── hardening (review findings) ─────────────────────────────────────────────────────────────────────────────────────

def _alert_app(roi_rows, fam="ROAS_G", confirm="no_data", opened="2026-03-27", esc=(), closed=None, tier="ALERT"):
    ep = {"kind": "app", "id": IDS["a"], "app": IDS["a"], "fam": fam, "tier": tier, "c": "2026-03-24", "opened": opened,
          "closed": closed, "why": None, "base": 0.4, "esc": [list(e) for e in esc], "confirm": confirm}
    return {"app_id": IDS["a"], "name": NAMES["a"], "notes": {"roi_rows": roi_rows},
            "view": {"eps": [ep], "w": {"CPI": None, "ECPM": None, "ROAS_G": 0.3}, "nrm": {}, "lost": None}}


def test_a_new_d0_roas_alarm_without_roi_rows_is_seeded_and_provisional():
    """An app with no ROI rows in this build has nothing to confirm a D0 ROAS alarm against: its NEW alarm is shown,
    never sent (seeded) and its alert item is provisional; with ROI rows (or another family) it is due as before."""
    t = date(2026, 3, 28)
    st = {"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}}
    al, _ = cb.alerts(st, False, [_alert_app(0)], t, NOW)
    assert len(al) == 1 and al[0]["provisional"] is True and al[0]["seeded"] is True and al[0]["notify"] is False
    assert st["due"] == {} and all(n.get("seeded") for r in st["eps"].values() for n in r["notices"].values())
    al, _ = cb.alerts(st, False, [_alert_app(0)], date(2026, 3, 29), NOW)                      # the next build: still not due
    assert al[0]["notify"] is False and st["due"] == {}
    st = {"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}}
    al, _ = cb.alerts(st, False, [_alert_app(120)], t, NOW)                                    # ROI rows: checked → due
    assert al[0]["provisional"] is False and al[0]["seeded"] is False and al[0]["notify"] is True and st["due"]
    st = {"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}}
    al, _ = cb.alerts(st, False, [_alert_app(0, confirm="confirmed")], t, NOW)                 # (confirmed = had data)
    assert al[0]["notify"] is True and al[0]["provisional"] is False
    al, _ = cb.alerts({"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}}, False,
                      [_alert_app(0, fam="CPI", confirm=None)], t, NOW)                        # other families unchanged
    assert al[0]["notify"] is True and al[0]["provisional"] is False


def test_a_seeded_opening_day_is_the_push_day_and_a_seeded_episode_is_never_re_noticed():
    """(a) an opening shown but not sent (first seen late) counts as the push day: its first re-notice a few days later
    joins it instead of going out as new; (b) every re-notice of a seeded episode (first build) is shown, never sent."""
    t = date(2026, 3, 20)
    st = {"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}}
    late = _alert_app(120, opened="2026-03-12", esc=[["2026-03-18", "step"]])                  # opened 8 days before t
    led = cb._ledger(st, False, [late], t, NOW)
    k, due = led[(IDS["a"], "ROAS_G", "2026-03-12")]
    n = st["eps"][k]["notices"]
    assert due == [] and n["open"] == {"day": "2026-03-12", "seeded": True} and st["eps"][k]["seeded"] is False
    assert n["2026-03-18"] == {"day": "2026-03-18", "joined": "2026-03-12"}                    # 6 days after its opening
    far = _alert_app(120, opened="2026-03-08", esc=[["2026-03-19", "step"]])                   # 11 days after: its own push
    st = {"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}}
    cb._ledger(st, False, [dict(far, view=dict(far["view"], eps=[dict(far["view"]["eps"][0], esc=[])]))],
               date(2026, 3, 18), NOW)                                                          # (the opening seen late)
    led = cb._ledger(st, False, [far], date(2026, 3, 19), NOW)
    assert led[(IDS["a"], "ROAS_G", "2026-03-08")][1] == ["2026-03-19"]
    # (b) the first build seeds the open episode; a re-notice 4 days later is shown only
    st = {"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}}
    first = _alert_app(120, opened="2026-03-16")
    cb._ledger(st, True, [first], date(2026, 3, 17), NOW)
    again = _alert_app(120, opened="2026-03-16", esc=[["2026-03-20", "step"]])
    led = cb._ledger(st, False, [again], date(2026, 3, 20), NOW)
    k, due = led[(IDS["a"], "ROAS_G", "2026-03-16")]
    assert due == [] and st["eps"][k]["notices"]["2026-03-20"] == {"day": "2026-03-20", "seeded": True}
    al, _ = cb.alerts(st, False, [again], date(2026, 3, 20), NOW)
    assert al[0]["notify"] is False and al[0]["seeded"] is True and st["due"] == {}


def test_d0_is_final_per_store_open_days_and_a_waiting_store_are_null():
    """by_app d0_open days are null in d0_inr (spend, installs stay); a store whose D0 waits for an account that cannot
    answer is null after its own last good D0 day; the window's D0 ROAS counts only the days D0 is final."""
    D = cb._Days(date(2026, 3, 1), date(2026, 3, 10))
    cache = {"daily": {"s": {x: 100 * 1000000 for x in days("2026-03-01", "2026-03-10")}}, "installs": {},
             "convval_day1": {"s": {x: 40.0 for x in days("2026-03-01", "2026-03-07")}}}
    R = [0.01] * D.n

    def nulls(s):
        return [i + 1 for i, v in enumerate(s["d0_inr"]) if v is None]
    plain = cb._spend(D, cache, "s", None, R, None)
    assert nulls(plain) == []                                                                  # (0 = fixed, no value)
    opened = cb._spend(D, cache, "s", None, R, None, d0_open=["2026-03-04", "2026-03-06", "2025-01-01"])
    assert nulls(opened) == [4, 6] and all(v == 100.0 for v in opened["sp_inr"])               # a day outside is ignored
    waiting = cb._spend(D, cache, "s", None, R, None, d0_wait=True)
    assert nulls(waiting) == [8, 9, 10] and waiting["d0_inr"][6] == 40.0                       # after its own last good day
    both = cb._spend(D, cache, "s", None, R, None, d0_open=["2026-03-07"], d0_wait=True)
    assert nulls(both) == [7, 8, 9, 10]                                                         # an open day is not "good"
    none_yet = cb._spend(D, {"daily": cache["daily"], "installs": {}, "convval_day1": {}}, "s", None, R, None,
                         d0_wait=True)
    assert nulls(none_yet) == list(range(1, 11))
    s = {"sp_inr": [100.0] * 10, "d0_inr": [40.0, 40.0, None, None, 40.0, 40.0, 40.0, 40.0, 40.0, 40.0]}
    w = cb.window(dict(s, sp_usd=[1.0] * 10, inst=[10.0] * 10, rev=[1.0] * 10, imp=[1000] * 10), date(2026, 3, 1),
                  "2026-03-01", "2026-03-10")
    assert w["ROAS_G"] == pytest.approx(0.4) and w["sp_inr"] == 1000.0                          # 8 final days: 320 ÷ 800
    # in the files: an app whose D0 days are open ships them null (the engine skips those windows)


def test_open_d0_days_reach_the_app_file_as_null(tmp_path):
    data, site, dash = make(tmp_path)
    e = dash["roas"]["by_app"][NAMES["b"]]
    e["d0_open"] = [T, addd(T, -1)]
    e["d0_wait"] = False
    cb.run(dash, data, site, {}, NOW)
    cb.pop_line()
    f = load(site, dash["cpi"]["apps"][IDS["b"]]["file"])
    assert at(f["d"]["d0_inr"], f["day0"], T) is None and at(f["d"]["d0_inr"], f["day0"], addd(T, -1)) is None
    assert at(f["d"]["d0_inr"], f["day0"], addd(T, -2)) > 0 and at(f["d"]["sp_inr"], f["day0"], T) == 20000
    g = load(site, dash["cpi"]["apps"][IDS["a"]]["file"])                                       # another app: untouched
    assert at(g["d"]["d0_inr"], g["day0"], T) > 0


def test_the_last_good_spend_fetch_day_is_recorded_after_the_cache_is_written():
    src = open(os.path.join(ROOT, "admob_iq", "build_static.py"), encoding="utf-8").read()
    body = src[src.index("def build("):]
    i_w, i_c = body.index("json.dump(spend, _cf)"), body.index("cache_written = True")
    i_r = body.index("s[\"roas_spend_ok_till\"] = record_spend_fetch(data_dir, today)")
    assert i_w < i_c < i_r
    gate = body[body.rindex("\n", 0, body.rindex("if ", 0, i_r)):i_r]
    assert "cache_written" in gate and "not fresh_spend.get(\"error\")" in gate and "ga4_value" not in gate
    assert body.index("cache_written = False") < i_w


def test_a_day_before_a_stores_own_first_day_is_unknown_never_zero(tmp_path):
    data, site, dash = make(tmp_path)
    first = "2026-03-10"
    for sub, fld in (("ads_campaign_day", {"v": 1, "first": first, "till": "2026-03-29", "done": True}),
                     ("ads_geo_day", {"v": 1, "ccy": "INR", "first": first, "till": "2026-03-27"})):
        write_json_gz_stable(os.path.join(data, sub, "state.json.gz"), fld)
    # one geo cell whose download count is unknown (null), the next one a real 0
    gm = os.path.join(data, "ads_geo_day", "2026-03.json.gz")
    g = load(os.path.dirname(gm), "2026-03.json.gz")
    g["days"][SIDS["a"]]["2026-03-12"]["XA"][1] = None
    g["days"][SIDS["a"]]["2026-03-13"]["XA"][1] = 0.0
    write_json_gz_stable(gm, g)
    D = cb._Days(date(2026, 3, 1), date(2026, 3, 28))
    R = [FX1] * D.n
    camps = cb._camps(D, data, {SIDS["a"]: IDS["a"]}, {}, R, [None])
    for c in camps.values():
        for k, arr in c["s"].items():
            assert arr[:9] == [None] * 9 and all(v is not None for v in arr[9:]), k              # 1–9 Mar unknown, 10 Mar on
        assert c["s"]["sp_inr"][9] > 0
    geo = cb._geo(D, data, {SIDS["a"]: IDS["a"]}, R, [None])
    xa = geo[IDS["a"]]["XA"]
    for k, arr in xa.items():
        assert arr[:9] == [None] * 9 and arr[9] is not None, k
    assert xa["sp_inr"][11] > 0 and xa["dl"][11] is None                                          # unknown stays unknown
    assert xa["dl"][12] == 0.0 and xa["dl"][10] > 0 and xa["dl"][13] > 0                         # a real 0 stays 0
    assert xa["dl"][-1] is None                                                                  # after the store's till
    # the engine entity carries the unknowns as null (not 0 installs)
    a = {"app_id": IDS["a"], "name": "x", "s": {k: D.zeros() for k in cb.ENG}}
    a["s"]["sp_usd"] = [1.0] * D.n
    ent = [e for e in cb.entities([a], {}, {IDS["a"]: {"XA": xa}}, D) if e.kind == "country"][0]
    assert ent.s["inst"][11] is None and ent.s["inst"][12] == 0.0


def test_a_damaged_gz_costs_only_that_file(tmp_path, monkeypatch):
    raw = bytearray(gzip.compress(json.dumps({"a": list(range(2000))}).encode()))
    raw[20:30] = b"\xff" * 10
    bad = tmp_path / "bad.json.gz"
    bad.write_bytes(bytes(raw))
    with pytest.raises(zlib.error):
        gzip.open(str(bad), "rt").read()                                       # (the failure this guards against)
    assert cb._load_json(str(bad)) is None
    short = tmp_path / "short.json.gz"
    short.write_bytes(gzip.compress(json.dumps({"a": list(range(2000))}).encode())[:40])
    assert cb._load_json(str(short)) is None                                   # truncated: EOFError
    good = tmp_path / "good.json.gz"
    good.write_bytes(gzip.compress(b'{"a":1}'))
    assert cb._load_json(str(good)) == {"a": 1}
    # a whole step with one damaged site file: the tab is still built (that app just has no GA4 users)
    data, site, dash = make(tmp_path / "t")
    key = gu.file_key(IDS["a"])
    (tmp_path / "t" / "site" / ("active_%s.json.gz" % key)).write_bytes(bytes(raw))
    assert cb.run(dash, data, site, {}, NOW) == ["/cpi*"] and "cpi" in dash and cb.pop_line().startswith("cpi: apps 4")
    f = load(site, dash["cpi"]["apps"][IDS["a"]]["file"])
    assert all(v is None for v in f["d"]["dau"])


def test_an_app_whose_file_is_too_big_is_not_counted(tmp_path, monkeypatch):
    data, site, dash = make(tmp_path)
    monkeypatch.setattr(cb, "_fits", lambda raw: b'"name":"Beta App"' not in raw)
    assert cb.run(dash, data, site, {}, NOW) == ["/cpi*"]
    p = dash["cpi"]
    assert IDS["b"] not in p["apps"] and sorted(p["apps"]) == sorted(IDS[k] for k in "ade")
    assert p["counts"] == {"alarm": 1, "watch": 0, "fixed": 0, "ok": 0, "new": 1, "paused": 1}      # Beta (ok) not counted
    assert sum(p["counts"].values()) == len(p["apps"]) and cb.pop_line().endswith(", too big 1")


# ── 🌍 the Chart tab's country view: each country's AdMob-matched D0 (the cohort cube's share × the app's c_r0) ────────
CUBE_SHARE = {"XA": 0.5, "XB": 0.3, "--": 0.2}       # of GA4's age-0 revenue; GA4 = 0.8 × AdMob (the scale k = 1.25)


def _cube(data, aid, skip=(), loss=()):
    """A synthetic cohort cube for one app: month files 2025-10 … 2026-03 (every day folded, but `skip`), age-0 revenue
    of install day X = 0.8 × the ROI fixture's r0 split by CUBE_SHARE (+ an age-1 value that must be ignored), and a
    hot day 2026-03-30 (not folded)."""
    from admob_iq.fetch import ga4_cube as gcu
    folder = gcu.app_dir(data, aid)
    os.makedirs(folder, exist_ok=True)
    roi = load(os.path.join(os.path.dirname(data), "site"), "roi_%s.json.gz" % gu.file_key(aid))
    r0 = {row[0]: row[4][0] for row in roi["rows"]}
    mon = {}
    for x in days(DAY0, "2026-03-29"):
        if x in skip:
            continue
        m = mon.setdefault(x[:7], {"v": gcu.V, "stream_id": "s1", "days": {}, "b": {}, "c": {}, "e": {}, "t": {},
                                   "loss": {}})
        m["days"][x] = {"st": "loss" if x in loss else "ok", "loss": 5 if x in loss else 0, "t": 1}
        for cc, q in CUBE_SHARE.items():
            m["e"].setdefault(cc, {})[x] = [10, int(round(r0[x] * 0.8 * q * 1e6)), 999]
    for k, m in mon.items():
        write_json_gz_stable(os.path.join(folder, k + ".json.gz"), m)
    write_json_gz_stable(os.path.join(folder, "hot.json.gz"),
                         {"v": gcu.V, "stream_id": "s1", "d": {"2026-03-30": {"st": "ok", "e": {"XA": {"2026-03-30": [1, 5]}}}}})


def test_country_d0_adds_up_to_the_app_and_ships_its_normals(tmp_path):
    data, site, dash = make(tmp_path)
    _cube(data, IDS["a"], skip=("2026-01-15",), loss=("2026-02-10",))
    assert cb.run(dash, data, site, {"ga4_cube": True}, NOW) == ["/cpi*"]
    cb.pop_line()
    f = load(site, dash["cpi"]["apps"][IDS["a"]]["file"])
    C = {c["cc"]: c for c in f["ctys"]}
    assert sorted(C) == ["XA", "XB"] and all(sorted(c["d"]) == ["dl", "imp", "r0", "rev", "sp_inr", "sp_usd"]
                                             for c in C.values())
    n_day = 0
    for i, a in enumerate(f["d"]["c_r0"]):
        x = addd(f["day0"], i)
        xa, xb = at(C["XA"]["d"]["r0"], C["XA"]["from"], x), at(C["XB"]["d"]["r0"], C["XB"]["from"], x)
        if a is None or x == "2026-01-15":                 # not matured / the cube does not hold that install day
            assert xa is None and xb is None
            continue
        n_day += 1                                         # k_X = c_r0 ÷ Σ every cube country: the "(not set)" too
        assert xa == pytest.approx(a * 0.5, abs=0.006) and xb == pytest.approx(a * 0.3, abs=0.006)
        assert xa + xb + a * 0.2 == pytest.approx(a, abs=0.011)
    assert n_day > 100
    assert f["notes"]["cty_r0"] == {"from": f["day0"], "loss_days": 1}
    # the normals: CPI ₹ / eCPM $ = the engine's (its own episode's B while open, else H) · D0 ROAS = the healthy rule
    res = cb.compute(copy.deepcopy(dash), data, site, {"ga4_cube": True}, NOW)[5]
    hl = res["healthy"][("country", IDS["a"] + "|XA")]
    for c in C.values():
        assert sorted(c["nrm"]) == ["CPI", "ECPM", "ROAS"] and all(len(v) == nd(c["from"], T) for v in c["nrm"].values())
    xa = C["XA"]
    i = nd(xa["from"], "2026-02-20") - 1
    assert xa["nrm"]["CPI"][i] == pytest.approx(20.0, rel=0.03) and xa["nrm"]["ECPM"][i] == pytest.approx(6.0, rel=0.03)
    assert xa["nrm"]["ECPM"][i] == pytest.approx(round(hl["ECPM"][(date(2026, 2, 20) - date(2025, 10, 1)).days], 4))
    r = [at(xa["d"]["r0"], xa["from"], x) for x in days("2026-01-16", "2026-01-29")]
    sp = [at(xa["d"]["sp_usd"], xa["from"], x) for x in days("2026-01-16", "2026-01-29")]
    q = 0.40 * 0.9 * 0.5 / 0.6                          # XA: 50 % of the D0 revenue on 60 % of the cost (before C)
    assert xa["nrm"]["ROAS"][i] == pytest.approx(q, rel=0.02)                   # AdMob-matched D0 ÷ $ cost
    assert q * 0.98 < sum(r) / sum(sp) < q * 1.02                    # (a window after the day the cube lacks)
    # the roas_h rule itself: windows ending d−14, d−21 … with every day known and ≥ $10 a day, ≥ 4 of them
    H = cb.roas_h([1.0] * 60, [20.0] * 60)
    assert H[40] is None and H[48] == pytest.approx(0.05) and H[59] == pytest.approx(0.05)
    H2 = cb.roas_h([1.0] * 60, [5.0] * 60)                                      # $5 a day: no window counts
    assert all(v is None for v in H2)


def test_country_d0_needs_the_cube_switch_and_a_bad_cube_costs_only_it(tmp_path, monkeypatch, capsys):
    data, site, dash = make(tmp_path)
    _cube(data, IDS["a"])
    d0 = copy.deepcopy(dash)
    cb.run(d0, data, site, {}, NOW)                         # GA4_CUBE off: the store unread
    cb.pop_line()
    f = load(site, d0["cpi"]["apps"][IDS["a"]]["file"])
    assert all("r0" not in c["d"] and "ROAS" not in c["nrm"] for c in f["ctys"]) and f["notes"]["cty_r0"] is None
    monkeypatch.setattr(cb, "cty_d0", lambda *a, **k: 1 / 0)
    d1 = copy.deepcopy(dash)
    assert cb.run(d1, data, site, {"ga4_cube": True}, NOW) == ["/cpi*"]
    assert "cpi country d0 skipped: ZeroDivisionError" in capsys.readouterr().err
    assert health.SKIP.search("cpi country d0 skipped: ZeroDivisionError")
    assert d1["cpi"]["apps"] == d0["cpi"]["apps"]          # everything else as without it


# ── levels: history ledger + the owner's actions (config/cpi_levels.json) ───────────────────────────────────────────
AT = "2026-03-30T04:00:00Z"


def write_actions(tmp_path, acts):
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    (cfg / "cpi_levels.json").write_text(json.dumps({"v": 1, "actions": acts}))


def act(n, kind, fam="CPI", app="a", **kw):
    a = {"id": "a-%012x" % n, "at": "2026-03-30T04:%02d:00Z" % n, "by": "owner@example.com", "app": IDS[app],
         "fam": fam, "act": kind}
    a.update(kw)
    return a


def build(tmp_path, acts=None, data=None):
    if data is None:
        data, site, dash = make(tmp_path)
    else:
        data, site, dash = data
    if acts is not None:
        write_actions(tmp_path, acts)
    cb.run(dash, data, site, {}, NOW)
    cb.pop_line()
    files = {k: load(site, dash["cpi"]["apps"][IDS[k]]["file"]) for k in "ab"}
    return (data, site, dash), files


def eps_of(f, fam):
    return [e for e in f["ep"] if e["fam"] == fam]


def test_levels_without_actions_ship_the_exact_history(tmp_path):
    (data, site, dash), f = build(tmp_path)
    a = f["a"]
    assert a["la"] == [] and a["lp"] == [] and dash["cpi"]["la"] is None
    cpi = a["lv"]["CPI"]
    assert [(r["src"], r["st"]) for r in cpi] == [("alarm", "now"), ("first", "rest")]       # newest first
    assert [(r["src"], r["st"]) for r in f["b"]["lv"]["CPI"]] == [("first", "now")]
    d0 = a["day0"]
    for fam, rows in a["lv"].items():
        for r in rows:
            assert re.fullmatch(r"L-[0-9a-f]{10}", r["id"]) and r["seen"] == "2026-03-30T05:22:00Z"
            i0, i1 = nd(d0, r["days"][0]) - 1, nd(d0, r["days"][1]) - 1
            for k, v in r["sums"].items():                 # the page's own sums of d over the named days (₹ and $)
                tot = sum(x for x in a["d"][k][i0:i1 + 1] if x is not None)
                assert tot == pytest.approx(v, abs=0.006 * (i1 - i0 + 1) + 1e-6), (fam, k)
            assert CA.level_of(fam, r["sums"], i1 - i0 + 1, CA.P_PROD) == pytest.approx(r["v"], rel=1e-6), fam
    alarm = cpi[0]
    ep = eps_of(a, "CPI")[0]
    assert (alarm["v"], alarm["days"], alarm["from"]) == (pytest.approx(ep["base"], rel=1e-6), ep["bspan"], ep["opened"])
    led = json.load(open(cb.levels_path(data)))
    assert led["v"] == 1 and led["rule"] == "L1" and set(led["apps"]) <= {IDS[k] for k in "abde"}
    assert {x["what"] for x in led["log"]} == {"new"}


def test_levels_ledger_is_stable_across_re_runs_and_records_restated_values(tmp_path):
    got, f1 = build(tmp_path)
    data = got[0]
    first = open(cb.levels_path(data), "rb").read()
    got2, f2 = build(tmp_path, data=make(tmp_path))
    assert open(cb.levels_path(data), "rb").read() == first and f2["a"]["lv"] == f1["a"]["lv"]
    # Google restates Beta's installs on two days inside its first CPI level's fortnight: same id, the value recorded
    r1 = f1["b"]["lv"]["CPI"][0]
    data, site, dash = make(tmp_path)
    cache = json.load(open(os.path.join(data, "roas_spend_cache.json")))
    for x in r1["days"][:2]:
        cache["installs"][SIDS["b"]][x] = round(cache["installs"][SIDS["b"]][x] * 1.2, 2)
    json.dump(cache, open(os.path.join(data, "roas_spend_cache.json"), "w"))
    _, f3 = build(tmp_path, data=(data, site, dash))
    r3 = [r for r in f3["b"]["lv"]["CPI"] if r["src"] == "first"][0]
    assert r3["id"] == r1["id"] and r3["seen"] == r1["seen"] and r3["v"] < r1["v"]
    assert r3["rs"]["v_old"] == r1["v"] and r3["rs"]["v_new"] == r3["v"]
    led = json.load(open(cb.levels_path(data)))
    assert [x["what"] for x in led["log"] if x["id"] == r1["id"]] == ["new", "restated"]


def test_levels_a_saved_level_no_longer_produced_is_kept_as_gone(tmp_path):
    data, site, dash = make(tmp_path)
    os.makedirs(os.path.join(data, "cpi"), exist_ok=True)
    old = {"v": 1, "rule": "L1", "proposals": {}, "log": [], "apps": {IDS["b"]: {"CPI": [
        {"id": "L-00000000aa", "from": "2025-11-01", "to": None, "v": 12.5, "days": None, "sums": None, "src": "auto",
         "ep": None, "act": None, "seen": "2026-03-01T00:00:00Z", "restated": [], "gone": None, "rejected": None}]}}}
    json.dump(old, open(cb.levels_path(data), "w"))
    _, f = build(tmp_path, data=(data, site, dash))
    g = [r for r in f["b"]["lv"]["CPI"] if r["id"] == "L-00000000aa"][0]
    assert g["st"] == "gone" and g["gone"] == "2026-03-30T05:22:00Z" and g["v"] == 12.5
    assert [r["st"] for r in f["b"]["lv"]["CPI"] if r["src"] == "first"] == ["now"]


def test_levels_set_by_days_closes_the_open_alarm_from_the_data_day(tmp_path):
    days_ = [C, "2026-03-28"]                                                      # the days after the change
    (data, site, dash), f = build(tmp_path, [act(1, "set", **{"from": T, "days": days_, "note": "naya normal"})])
    a = f["a"]
    ep = eps_of(a, "CPI")[0]
    assert (ep["closed"], ep["why"]) == (T, "owner")
    man = [r for r in a["lv"]["CPI"] if r["src"] == "manual"][0]
    assert (man["from"], man["days"], man["act"], man["st"]) == (T, days_, "a-000000000001", "now")
    i0, i1 = nd(a["day0"], days_[0]) - 1, nd(a["day0"], days_[1]) - 1
    want = sum(a["d"]["sp_inr"][i0:i1 + 1]) / sum(a["d"]["inst"][i0:i1 + 1])
    assert man["v"] == pytest.approx(want, rel=1e-6) and man["v"] == pytest.approx(31.25, rel=0.03)
    assert [(x["id"], x["st"], x["note"], x["days"]) for x in a["la"]] == [("a-000000000001", "applied", "naya normal",
                                                                             days_)]
    assert "by" not in a["la"][0]                                                   # never the email on the page
    assert dash["cpi"]["la"] == "2026-03-30T04:01:00Z"
    assert dash["cpi"]["apps"][IDS["a"]]["st"] == "alarm"                           # D0 ROAS still open


def test_levels_typed_value_rollback_accept_auto(tmp_path):
    _, f0 = build(tmp_path)
    first = [r for r in f0["a"]["lv"]["CPI"] if r["src"] == "first"][0]
    acts = [act(1, "set", fam="ECPM", **{"from": T, "value": 5.0}),
            act(2, "rollback", level=first["id"], **{"from": T}),
            act(3, "accept", fam="ROAS_G", proposal={"day": T, "days": [C, "2026-03-28"]}, **{"from": T}),
            act(4, "auto", fam="GAP", **{"from": T})]
    (data, site, dash), f = build(tmp_path, acts, data=make(tmp_path))
    a = f["a"]
    assert [(x["id"], x["st"]) for x in a["la"]] == [("a-%012x" % n, "applied") for n in (4, 3, 2, 1)]
    ec = [r for r in a["lv"]["ECPM"] if r["src"] == "manual"][0]
    assert (ec["v"], ec["days"], ec["sums"]) == (5.0, None, None)
    rb = [r for r in a["lv"]["CPI"] if r["src"] == "rollback"][0]
    assert rb["days"] == first["days"] and rb["v"] == pytest.approx(first["v"], rel=1e-12)
    ac = [r for r in a["lv"]["ROAS_G"] if r["src"] == "accepted_owner"][0]
    assert ac["v"] == pytest.approx(0.30, rel=0.03) and ac["st"] == "now"
    for fam in ("ECPM", "CPI", "ROAS_G"):
        assert [(e["closed"], e["why"]) for e in eps_of(a, fam)][-1] == (T, "owner"), fam
    assert [(e["closed"], e["why"]) for e in eps_of(a, "GAP")][-1] == (None, None)      # "auto": no pin, still open


def test_levels_undo_drops_the_action_as_if_it_never_was(tmp_path):
    _, f0 = build(tmp_path)
    acts = [act(1, "set", **{"from": T, "days": ["2026-03-01", "2026-03-28"]}),
            {"id": "a-%012x" % 2, "at": "2026-03-30T04:02:00Z", "act": "undo", "ref": "a-%012x" % 1}]
    _, f = build(tmp_path, acts, data=make(tmp_path))
    assert [(x["id"], x["st"]) for x in f["a"]["la"]] == [("a-000000000002", "applied"), ("a-000000000001", "undone")]
    assert f["a"]["ep"] == f0["a"]["ep"] and f["a"]["lv"] == f0["a"]["lv"]


def test_levels_a_bad_action_costs_only_itself(tmp_path, capsys):
    good = act(1, "set", fam="ECPM", **{"from": T, "value": 5.0})
    bad = [act(2, "rollback", level="L-ffffffffff", **{"from": T}),
           act(3, "set", **{"from": T, "days": ["2026-03-25", "2026-03-28"]}),             # 4 days: too few
           act(4, "set", app="h", **{"from": T, "value": 9.0}),                             # not on this screen
           act(5, "reject", level=None),
           {"id": "a-%012x" % 6, "at": "2026-03-30T04:06:00Z", "act": "undo", "ref": "a-0000000000ff"}]
    capsys.readouterr()
    _, f = build(tmp_path, [good] + bad)
    err = capsys.readouterr().err
    st = {x["id"]: (x["st"], x.get("why")) for x in f["a"]["la"]}
    assert st["a-000000000001"] == ("applied", None)
    assert st["a-000000000002"] == ("bad", "UnknownLevel") and st["a-000000000003"] == ("bad", "BadDays")
    assert st["a-000000000005"] == ("bad", "UnknownLevel")
    for why in ("UnknownLevel", "BadDays", "UnknownApp", "UnknownRef"):
        line = "cpi level action skipped: %s" % why
        assert line in err and health.SKIP.search(line)
    assert [e["why"] for e in eps_of(f["a"], "ECPM")] == ["owner"]


def test_levels_reject_marks_the_accepted_row_and_waits_on_a_later_day(tmp_path):
    data, site, dash = make(tmp_path)
    os.makedirs(os.path.join(data, "cpi"), exist_ok=True)
    row = {"id": "L-00000000bb", "from": "2026-01-10", "to": None, "v": 21.0, "days": ["2025-12-14", "2026-01-10"],
           "sums": None, "src": "accepted", "ep": {"opened": "2025-11-15", "old": 20.0}, "act": None,
           "seen": "2026-03-01T00:00:00Z", "restated": [], "gone": None, "rejected": None}
    json.dump({"v": 1, "rule": "L1", "proposals": {}, "log": [], "apps": {IDS["a"]: {"CPI": [row]}}},
              open(cb.levels_path(data), "w"))
    acts = [act(1, "reject", level="L-00000000bb"), act(2, "set", fam="IPU", **{"from": "2026-03-29", "value": 3.0})]
    _, f = build(tmp_path, acts, data=(data, site, dash))
    r = [x for x in f["a"]["lv"]["CPI"] if x["id"] == "L-00000000bb"][0]
    assert r["st"] == "rejected" and r["rejected"] == "2026-03-30T04:01:00Z" and r["gone"] is None
    assert {x["id"]: x["st"] for x in f["a"]["la"]} == {"a-000000000001": "applied", "a-000000000002": "waiting"}
    led = json.load(open(cb.levels_path(data)))
    assert [x["what"] for x in led["log"] if x["id"] == "L-00000000bb"] == ["rejected"]


def test_levels_failures_cost_the_levels_only(tmp_path, monkeypatch, capsys):
    data, site, dash = make(tmp_path)
    write_actions(tmp_path, [])
    (tmp_path / "config" / "cpi_levels.json").write_text("{broken")
    capsys.readouterr()
    _, f = build(tmp_path, data=(data, site, dash))
    assert "cpi levels skipped: JSONDecodeError" in capsys.readouterr().err
    assert "lv" not in f["a"] and "la" not in dash["cpi"] and f["a"]["ep"]                # the tab, automatic only
    assert not os.path.exists(cb.levels_path(data))

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(cb, "merge_ledger", boom)
    write_actions(tmp_path, [])
    _, f = build(tmp_path, data=make(tmp_path))
    assert "cpi levels skipped: RuntimeError" in capsys.readouterr().err and "lv" not in f["a"]


def test_levels_a_level_that_is_not_exact_is_never_shipped(tmp_path, monkeypatch, capsys):
    real = CA.measure

    def off(ent, P, fam, a, b):
        m = real(ent, P, fam, a, b)
        if m and fam == "CPI" and ent.id == IDS["b"]:
            m = dict(m, v=m["v"] * 1.01)
        return m
    monkeypatch.setattr(CA, "measure", off)
    capsys.readouterr()
    _, f = build(tmp_path)
    assert "cpi levels skipped: LevelMismatch" in capsys.readouterr().err
    assert f["b"]["lv"] == {} and f["a"]["lv"]["CPI"]                              # Beta: its saved history only (none)


# ── levels: review fixes — a level worth 0, one bad app, rows / a history file / actions that cannot be read ─────────

def zero_rev(dash, app, window):
    """The app's AdMob revenue is 0 on the window's days (the impressions stay): its eCPM over them is exactly 0."""
    for p in dash["placements"]:
        if p["app"] == NAMES[app]:
            for r in p["daily"]:
                if r[0] in window:
                    r[1] = 0


def skipped(err, what="cpi levels skipped"):
    return [ln for ln in err.splitlines() if ln.startswith(what)]


def lv_row(**kw):
    """A saved history row as the build writes it (typed level, no named days)."""
    row = {"id": "L-00000000aa", "from": "2025-11-01", "to": None, "v": 12.5, "days": None, "sums": None, "src": "auto",
           "ep": None, "act": None, "seen": "2026-03-01T00:00:00Z", "restated": [], "gone": None, "rejected": None}
    row.update(kw)
    return row


def test_levels_a_level_worth_zero_is_a_bad_action_never_a_crash(tmp_path, capsys):
    """eCPM over days without revenue is exactly 0. Set / accept onto those days is ZeroLevel (listed bad, never
    pinned). It used to pin 0, divide by it in the exactness check, drop EVERY app's history on every build and hide
    Undo; now the other apps and the other action are untouched."""
    data, site, dash = make(tmp_path)
    win = ["2025-12-01", "2025-12-28"]
    zero_rev(dash, "b", set(days(*win)))
    acts = [act(1, "set", fam="ECPM", app="b", **{"from": T, "days": win}),
            act(2, "accept", fam="ECPM", app="b", proposal={"day": T, "days": win}, **{"from": T}),
            act(3, "set", fam="CPI", app="a", **{"from": T, "value": 30.0})]
    capsys.readouterr()
    (data, site, dash), f = build(tmp_path, acts, data=(data, site, dash))
    err = capsys.readouterr().err
    assert err.count("cpi level action skipped: ZeroLevel") == 2 and skipped(err) == []      # no crash, nothing else
    assert health.SKIP.search("cpi level action skipped: ZeroLevel")
    assert {x["id"]: (x["st"], x.get("why")) for x in f["b"]["la"]} == {"a-000000000001": ("bad", "ZeroLevel"),
                                                                        "a-000000000002": ("bad", "ZeroLevel")}
    assert [x["st"] for x in f["a"]["la"]] == ["applied"] and f["a"]["lv"]["CPI"][0]["src"] == "manual"
    assert f["b"]["lv"]["CPI"] and not [r for r in f["b"]["lv"].get("ECPM", []) if r["src"] in ("manual", "accepted_owner")]
    assert all(r["v"] > 0 for fams in (f["a"]["lv"], f["b"]["lv"]) for rows in fams.values() for r in rows)
    assert dash["cpi"]["la"] == "2026-03-30T04:03:00Z" and os.path.exists(cb.levels_path(data))


def test_levels_exact_is_a_mismatch_for_a_level_worth_zero_never_a_division(monkeypatch):
    row = lambda v: {"v": v, "days": ["2025-12-01", "2025-12-14"]}                  # noqa: E731
    monkeypatch.setattr(CA, "measure", lambda ent, P, fam, a, b: {"v": 0.0, "sums": {"rev": 0.0, "imp": 280000.0},
                                                                  "days": [a, b], "n": 14})
    for v in (0.0, -2.0, float("nan"), float("inf"), None):
        with pytest.raises(cb.LevelMismatch):
            cb._exact(None, "ECPM", row(v))
    monkeypatch.setattr(CA, "measure", lambda ent, P, fam, a, b: None)               # days that cannot be measured
    with pytest.raises(cb.LevelMismatch):
        cb._exact(None, "ECPM", row(5.0))


def test_levels_a_rollback_to_a_saved_level_worth_zero_is_bad(monkeypatch, capsys):
    ent = {IDS["a"]: object()}
    led = {"apps": {IDS["a"]: {"CPI": [lv_row(id="L-00000000c1", v=0.0),                     # typed, no days
                                       lv_row(id="L-00000000c2", v=9.0, days=["2025-12-01", "2025-12-14"])]}}}
    monkeypatch.setattr(CA, "measure", lambda e, P, fam, a, b: {"v": 0.0, "sums": {}, "days": [a, b], "n": 14})
    acts = [act(1, "rollback", level="L-00000000c1", **{"from": T}), act(2, "rollback", level="L-00000000c2", **{"from": T})]
    owner, la, rej, seen = cb.resolve_actions(acts, ent, led, T)
    assert owner == {} and rej == {} and [x["why"] for x in sorted(la[IDS["a"]], key=lambda x: x["id"])] == ["ZeroLevel"] * 2
    assert capsys.readouterr().err.count("cpi level action skipped: ZeroLevel") == 2


def test_levels_one_app_that_cannot_merge_costs_only_itself(tmp_path, monkeypatch, capsys):
    (data, site, dash), f0 = build(tmp_path)
    led0 = json.load(open(cb.levels_path(data)))
    real = cb._fresh

    def boom(ent, key, res, eps):
        if ent.id == IDS["b"]:
            raise KeyError("x")                      # anything, not only a LevelMismatch
        return real(ent, key, res, eps)
    monkeypatch.setattr(cb, "_fresh", boom)
    write_actions(tmp_path, [act(1, "set", **{"from": T, "value": 30.0})])
    capsys.readouterr()
    _, f1 = build(tmp_path, data=(data, site, dash))
    err = capsys.readouterr().err
    assert skipped(err) == ["cpi levels skipped: KeyError"] and health.SKIP.search(skipped(err)[0])    # ONE line
    led1 = json.load(open(cb.levels_path(data)))
    assert led1["apps"][IDS["b"]] == led0["apps"][IDS["b"]] and f1["b"]["lv"] == f0["b"]["lv"]         # Beta: as it was
    assert [x for x in led1["log"] if x["app"] == IDS["b"]] == [x for x in led0["log"] if x["app"] == IDS["b"]]
    assert f1["a"]["lv"]["CPI"][0]["src"] == "manual" and [x["st"] for x in f1["a"]["la"]] == ["applied"]   # Alpha: merged


def test_levels_rows_that_cannot_be_read_are_dropped_and_counted_never_the_tab(tmp_path, capsys):
    data, site, dash = make(tmp_path)
    os.makedirs(os.path.join(data, "cpi"), exist_ok=True)
    good = lv_row()
    bad = [{k: v for k, v in good.items() if k != d} for d in ("id", "src", "from", "v")]
    bad += [lv_row(**{"from": "soon"}), lv_row(v="12"), lv_row(v=True), "junk", 7]
    json.dump({"v": 1, "rule": "L1", "proposals": [], "log": {}, "apps": {IDS["b"]: {"CPI": [good] + bad, "ECPM": "oops"},
                                                                         IDS["a"]: ["nope"]}},
              open(cb.levels_path(data), "w"))
    capsys.readouterr()
    paths = cb.run(dash, data, site, {}, NOW)
    cb.pop_line()
    err = capsys.readouterr().err
    assert paths == ["/cpi*"] and set(dash["cpi"]["apps"]) == {IDS[k] for k in "abde"}       # the tab stays, every app
    assert skipped(err) == ["cpi levels skipped: BadRow (11 dropped)"]                       # 9 rows + a fam + an app
    assert health.SKIP.search(skipped(err)[0])
    f = {k: load(site, dash["cpi"]["apps"][IDS[k]]["file"]) for k in "ab"}
    assert [r["id"] for r in f["b"]["lv"]["CPI"] if r["id"] == "L-00000000aa"] == ["L-00000000aa"]   # the readable row stays
    assert all(r["id"].startswith("L-") for fams in (f["a"]["lv"], f["b"]["lv"]) for rows in fams.values() for r in rows)
    led = json.load(open(cb.levels_path(data)))                                              # … and is saved without the rest
    assert all(isinstance(r, dict) and {"id", "src", "from", "v"} <= set(r) for fams in led["apps"].values()
               for rows in fams.values() for r in rows)
    assert isinstance(led["proposals"], dict) and isinstance(led["log"], list)


def test_levels_a_row_nobody_foresaw_costs_that_apps_history_block_only(tmp_path, monkeypatch, capsys):
    data, site, dash = make(tmp_path)
    real = cb.ship_levels

    def boom(led, aid):
        if aid == IDS["b"]:
            raise KeyError("src")
        return real(led, aid)
    monkeypatch.setattr(cb, "ship_levels", boom)
    write_actions(tmp_path, [act(1, "set", app="b", **{"from": T, "value": 30.0})])
    capsys.readouterr()
    paths = cb.run(dash, data, site, {}, NOW)
    cb.pop_line()
    assert paths == ["/cpi*"] and skipped(capsys.readouterr().err) == ["cpi levels skipped: KeyError"]
    a, b = (load(site, dash["cpi"]["apps"][IDS[k]]["file"]) for k in "ab")
    assert a["lv"]["CPI"] and "lv" not in b and b["ep"] is not None                          # Beta: no history block …
    assert [x["st"] for x in b["la"]] == ["applied"] and b["lp"] == []                       # … its owner actions still listed


def test_levels_a_hand_edited_action_with_a_list_or_object_is_bad_the_rest_apply(tmp_path, capsys):
    data, site, dash = make(tmp_path)
    os.makedirs(os.path.join(data, "cpi"), exist_ok=True)
    acc = lv_row(id="L-00000000bb", **{"from": "2026-01-10"}, v=21.0, days=["2025-12-14", "2026-01-10"], src="accepted",
                 ep={"opened": "2025-11-15", "old": 20.0})
    json.dump({"v": 1, "rule": "L1", "proposals": {}, "log": [], "apps": {IDS["a"]: {"CPI": [acc]}}},
              open(cb.levels_path(data), "w"))
    A = IDS["a"]
    odd = [dict(act(3, "undo"), ref=["a-000000000001"]),                              # ref: a list
           dict(act(4, "set", **{"from": T, "value": 9.0}), app=[A]),                 # app: a list
           dict(act(5, "set", **{"from": T, "value": 9.0}), app={"id": A}),           # app: an object
           act(6, "rollback", level={"id": "L-00000000bb"}, **{"from": T}),           # level: an object
           act(7, "set", **{"from": T, "days": [["2026-03-01"], T]}),                 # days: nested
           dict(act(8, "set", **{"from": T, "value": 9.0}), fam=["CPI"]),             # fam: a list
           act(9, "auto", **{"from": {"d": 1}}),                                      # from: an object
           dict(act(10, "set", **{"from": T, "value": 9.0}), act=["set"]),            # act: a list
           dict(act(11, "set", **{"from": T, "value": 9.0}), id=["a-000000000011"])]  # id: a list
    acts = [act(1, "set", fam="ECPM", **{"from": T, "value": 5.0}),
            dict(act(2, "reject", level="L-00000000bb"), **{"from": ["2026-03-29"]})] + odd   # a reject needs no day
    capsys.readouterr()
    (data, site, dash), f = build(tmp_path, acts, data=(data, site, dash))
    err = capsys.readouterr().err
    assert skipped(err) == []                                                         # no TypeError: nothing dropped
    got = sorted((str(x["id"]), x["st"], x.get("why")) for x in f["a"]["la"])
    assert got == [("['a-000000000011']", "bad", "BadAction"), ("a-000000000001", "applied", None),
                   ("a-000000000002", "applied", None), ("a-000000000003", "bad", "UnknownRef"),
                   ("a-000000000006", "bad", "UnknownLevel"), ("a-000000000007", "bad", "BadDays"),
                   ("a-000000000008", "bad", "UnknownFam"), ("a-000000000009", "bad", "BadDate"),
                   ("a-00000000000a", "bad", "BadAction")]
    for why in ("UnknownApp", "UnknownRef", "UnknownLevel", "BadDays", "UnknownFam", "BadDate", "BadAction"):
        assert "cpi level action skipped: %s" % why in err
    assert [e["why"] for e in eps_of(f["a"], "ECPM")] == ["owner"]                    # the good action reached the engine
    r = [x for x in f["a"]["lv"]["CPI"] if x["id"] == "L-00000000bb"][0]
    assert r["st"] == "rejected"                                                      # … and so did the reject


def test_levels_a_history_file_that_cannot_be_read_keeps_the_owners_set_and_accept_levels(tmp_path, capsys):
    """A damaged data/cpi/levels.json used to drop the whole levels part: the owner's levels silently stopped. Now
    set / accept (no saved level needed) still reach the replay, rollback / reject are bad (NoLedger), the file is
    never overwritten, no history is shipped, and the actions are still listed (so Undo stays on the page)."""
    acts = [act(1, "set", fam="ECPM", **{"from": T, "value": 5.0}),
            act(2, "accept", fam="ROAS_G", proposal={"day": T, "days": [C, "2026-03-28"]}, **{"from": T}),
            act(3, "rollback", level="L-00000000aa", **{"from": T}),
            act(4, "reject", level="L-00000000bb")]
    data, site, dash = make(tmp_path)
    os.makedirs(os.path.join(data, "cpi"), exist_ok=True)
    with open(cb.levels_path(data), "w") as fh:
        fh.write("{broken")
    capsys.readouterr()
    (data, site, dash), f = build(tmp_path, acts, data=(data, site, dash))
    err = capsys.readouterr().err
    assert skipped(err) == ["cpi levels skipped: JSONDecodeError"] and err.count("cpi level action skipped: NoLedger") == 2
    a = f["a"]
    assert {x["id"]: (x["st"], x.get("why")) for x in a["la"]} == {
        "a-000000000001": ("applied", None), "a-000000000002": ("applied", None),
        "a-000000000003": ("bad", "NoLedger"), "a-000000000004": ("bad", "NoLedger")}
    for fam in ("ECPM", "ROAS_G"):                                                    # the owner's levels reached the replay
        assert [(e["closed"], e["why"]) for e in eps_of(a, fam)][-1] == (T, "owner"), fam
    assert "lv" not in a and "lp" in a and "lv" not in f["b"] and dash["cpi"]["la"] == "2026-03-30T04:04:00Z"
    assert open(cb.levels_path(data)).read() == "{broken"                             # never overwritten
    clean = tmp_path / "clean"                                                        # the same two actions, a healthy history
    _, g = build(clean, acts[:2], data=make(clean))
    assert a["ep"] == g["a"]["ep"] and a["nrm"] == g["a"]["nrm"]


def test_levels_a_row_keeps_its_last_ten_restated_values():
    saved = [lv_row(v=10.0)]
    log, v = [], 10.0
    for i in range(14):
        v *= 1.01
        saved = cb._merge_fam("app", "CPI", saved, [{"from": "2025-11-01", "v": v, "days": None, "sums": None, "src": "auto",
                                                     "ep": None, "act": None}], {}, "2026-03-%02dT00:00:00Z" % (i + 1),
                              {"L-00000000aa"}, log)
    r = saved[0]
    assert r["id"] == "L-00000000aa" and len(r["restated"]) == cb.RESTATED_MAX == 10
    assert [x["at"][8:10] for x in r["restated"]] == ["%02d" % d for d in range(5, 15)]       # the newest ten
    assert r["restated"][-1]["v_new"] == pytest.approx(v) and r["restated"][0]["v_old"] == pytest.approx(10.0 * 1.01 ** 4)
    assert len([x for x in log if x["what"] == "restated"]) == 14                             # the log keeps all (its own cap)


# ── the level agent (D-a … D-j): synthetic apps on the engine's entities, replayed by levels_run ─────────────────────
AG0, AGN = "2024-01-02", 480                     # AG0 on the engine's weekly phase: phase days are multiples of 7
A1 = "ca-app-pub-0000000000000000~41"            # the app the questions are about
OTH = ["ca-app-pub-0000000000000000~%d" % (42 + i) for i in range(3)]


@pytest.fixture
def agent_on(monkeypatch):
    cfg = dict(CA.P_PROD["levels"]["agent"])
    assert cfg["mode"] == "on"
    monkeypatch.setattr(cb, "agent_cfg", lambda: cfg)
    return cfg


def ag_day(i):
    return (date.fromisoformat(AG0) + timedelta(days=i)).isoformat()


def ag_series(seed, sp=1000.0, cpi=20.0, ecpm=5.0, ipu=5.0, dau=200000.0, roas=0.40, n=AGN):
    """One app's days: $ cost (₹ at 94.5), ₹ per install, eCPM, ads per user, D0 ROAS; ±1 % noise."""
    g = prng(seed)
    s = {k: [0.0] * n for k in ("sp_usd", "sp_inr", "inst", "d0_inr", "rev", "imp", "dau")}
    for d in range(n):
        f = (lambda: 1.0 + 0.01 * next(g))
        spd = sp * f()
        s["sp_usd"][d], s["sp_inr"][d] = spd, spd * 94.5
        s["inst"][d] = spd * 94.5 / cpi * f()
        s["d0_inr"][d] = spd * 94.5 * roas * f()
        s["dau"][d] = dau * f()
        s["imp"][d] = s["dau"][d] * ipu * f()
        s["rev"][d] = s["imp"][d] * ecpm / 1000.0 * f()
    return s


def ag_mul(s, key, a, b, k):
    for d in range(a, min(b, len(s[key]))):
        if s[key][d] is not None:
            s[key][d] *= k


def ag_world(own, others=None, camps=(0.6, 0.4)):
    """[the app, its campaigns (shares of every day), the other apps] as engine entities."""
    out = [CA.Ent("app", A1, A1, "Alpha App", AG0, own)]
    for i, s in enumerate(others or []):
        out.append(CA.Ent("app", OTH[i], OTH[i], "Other App %d" % i, AG0, s))
    for i, q in enumerate(camps):
        out.append(CA.Ent("camp", "90000000%02d" % i, A1, "Campaign %d" % i, AG0,
                          {k: [x * q for x in own[k]] for k in ("sp_usd", "sp_inr", "inst")}))
    return out


def market_apps(step=None, k=1.6, n=3):
    """Small other apps (no alarm of their own: under the money floor) whose CPI moves by k from day `step`."""
    out = []
    for i in range(n):
        s = ag_series(60 + i, sp=15.0, cpi=2.0)
        if step is not None:
            ag_mul(s, "inst", step, AGN, 1 / k)
        out.append(s)
    return out


def ag_build(tmp, ents, t_ix, acts=None, now=None, geo=None, cd=None):
    """One build's levels step (the agent on the saved history) → (engine result, levels part); the history saved."""
    data = tmp / "data"
    data.mkdir(parents=True, exist_ok=True)
    if acts is not None:
        write_actions(tmp, acts)
    t = date.fromisoformat(ag_day(t_ix))
    extra = {"D": cb._Days(date.fromisoformat(AG0), t), "geo": geo or {}, "cd": cd or {},
             "names": {e.id: e.label for e in ents if e.kind == "app"}}
    now = now or datetime(t.year, t.month, t.day, 5, 22, tzinfo=timezone.utc) + timedelta(days=2)
    res, part = cb.levels_run(ents, str(data), t, now, extra)
    if part is not None and part["ledger"] is not None:
        cb.save_ledger(str(data), part["ledger"])
    return res, part


def app_eps(res, fam, aid=A1):
    return [e for e in res["episodes"] if e["kind"] == "app" and e["id"] == aid and e["fam"] == fam]


def rows_of(part, fam=None, aid=A1):
    return [r for r in part["ledger"]["agent"]["rows"] if r["app"] == aid and (fam is None or r["fam"] == fam)]


def scale_up():
    """CPI ×1.5 from day 300 on the same spend, then spend ×3 from day 315 (installs ×3: CPI unchanged)."""
    s = ag_series(1)
    ag_mul(s, "inst", 300, AGN, 1 / 1.5)
    for k in ("sp_usd", "sp_inr", "inst", "d0_inr"):
        ag_mul(s, k, 315, AGN, 3.0)
    return s


def market_move(ramp=False):
    """CPI ×1.6 from day 300 on the app and the other apps (ramp: ×1.3 → ×1.7 over 60 days: settles ~110 days later)."""
    def shape(s):
        for d in range(300, AGN):
            s["inst"][d] /= (1.3 + 0.4 * min(1.0, (d - 300) / 60.0)) if ramp else 1.6
    own = ag_series(1)
    shape(own)
    others = [ag_series(60 + i, sp=15.0, cpi=2.0) for i in range(3)]
    for s in others:
        shape(s)
    return own, others


def test_splice_is_the_full_replay_with_the_same_primitives():
    own = scale_up()
    ents = ag_world(own, market_apps(300))
    ts = ag_day(AGN - 1)
    res0 = CA.run(ents, CA.P_PROD, ts)
    ep = app_eps(res0, "CPI")[0]
    prims = {(A1, "CPI"): [{"act": "agent_veto", "ep_open": ep["opened"], "id": "D-1"}],
             (A1, "GAP"): [{"act": "agent_veto", "ep_open": app_eps(res0, "GAP")[0]["opened"], "id": "D-2"}]}
    runs = {A1: CA.run([e for e in ents if e.id == A1], CA.P_PROD, ts, owner=prims)}
    sp = cb.splice(res0, runs, ents)
    full = CA.run(ents, CA.P_PROD, ts, owner=prims)

    def canon(r):
        return json.dumps({k: (v if k == "episodes" else {"%s|%s" % kk: vv for kk, vv in v.items()})
                           for k, v in r.items()}, sort_keys=True)
    assert canon(sp) == canon(full) and canon(sp) != canon(res0)
    assert app_eps(res0, "CPI")[0]["why"] == "settled" and app_eps(sp, "CPI")[0]["why"] is None


def test_dj_a_cpi_settle_seen_with_a_spend_scale_up_is_blocked_and_reopened(tmp_path, agent_on):
    ents = ag_world(scale_up(), market_apps())
    res0 = CA.run(ents, CA.P_PROD, ag_day(AGN - 1))
    s0 = app_eps(res0, "CPI")[0]
    assert s0["why"] == "settled"
    res, part = ag_build(tmp_path, ents, AGN - 1)
    ep = app_eps(res, "CPI")[0]
    assert (ep["opened"], ep["c"], ep["base"], ep["closed"]) == (s0["opened"], s0["c"], s0["base"], None)
    assert ep["suggest"][1] == "open"                                         # open 120+ days now: the same row
    r = rows_of(part, "CPI")[0]
    assert (r["why"], r["dec"], r["branch"]) == ("settle", "keep", "spend_scaled")
    assert r["cause"] == "seen with spend ×3.0 since the old level (your lever)"
    assert [(a["d"], a["on"]) for a in r["asks"]] == [(s0["closed"], "settle"), (ag_day(AGN - 1), "reask")]
    assert r["applied"] == {"veto": {"since_t": ag_day(AGN - 1)}, "accept": None}
    assert r["next"] == LA.next_phase(ag_day(AGN - 1))
    lv = cb.ship_levels(part["ledger"], A1, agent_on=True)["CPI"]
    blk = [x for x in lv if x["st"] == "blocked"]
    assert len(blk) == 1 and blk[0]["src"] == "accepted" and blk[0]["from"] == s0["closed"]
    assert blk[0]["ag"]["dec"] == r["id"] and blk[0]["ag"]["cause"] == r["cause"]
    assert [x["src"] for x in lv if x["st"] == "rest"] == ["first"]              # the old level stays the resting one
    assert "blocked" in [x["what"] for x in part["ledger"]["log"]]
    ag = part["agent"]["ag"]
    assert ag.ship_data[A1]["tag"]["st"] == "blocked" and ag.ship_data[A1]["tag"]["more"] == 1   # CPI and GAP
    assert ag.board["settle"] == {"checked": 2, "passed": 0, "blocked": 2, "hold": 0, "later": 0}
    row = [x for x in ag.ship_data[A1]["rows"] if x["fam"] == "CPI"][0]
    assert row["st"] == "blocked" and row["level"] == blk[0]["id"] and row["xp"]["inr"] > 0
    assert row["h"] == [[s0["closed"], ag_day(AGN - 1), 2, "keep", "spend_scaled", None, r["short"]]]
    # its notices: seeded, never pushed (the alarm was shown closed; it re-opens)
    q = part["agent"]["quiet"]
    assert q[(A1, "CPI", ep["opened"])] == ag_day(AGN - 1)
    st = {"v": 1, "eps": {}, "push": {}, "due": {}}
    apps = [{"app_id": A1, "name": "Alpha App", "notes": {"roi_rows": 1},
             "view": {"eps": [dict(e, tier="ALERT") for e in app_eps(res, "CPI") + app_eps(res, "GAP")]}}]
    got = cb._ledger(st, False, apps, date.fromisoformat(ag_day(AGN - 1)), NOW, quiet=q)
    assert got and all(due == [] for _, due in got.values())
    assert any(n.get("seeded") for rec in st["eps"].values() for n in rec["notices"].values())
    noisy = cb._ledger({"v": 1, "eps": {}, "push": {}, "due": {}}, False, apps,
                       date.fromisoformat(ag_day(AGN - 1)), NOW)
    assert sum(len(d) for _, d in noisy.values()) >= sum(len(d) for _, d in got.values())


def test_dj_a_market_wide_settle_passes_and_stands_as_today(tmp_path, agent_on):
    own, others = market_move(ramp=True)
    ents = ag_world(own, others)
    res0 = CA.run(ents, CA.P_PROD, ag_day(AGN - 1))
    res, part = ag_build(tmp_path, ents, AGN - 1)
    for fam in ("CPI", "GAP"):
        assert app_eps(res, fam) == app_eps(res0, fam) and app_eps(res, fam)[0]["why"] == "settled", fam
        r = rows_of(part, fam)[0]
        assert (r["dec"], r["branch"], r["asks"][0]["on"]) == ("accept", "cpi_market", "settle"), fam
        assert r["applied"] == {"veto": None, "accept": None} and r["next"] is None
    assert res["levels"][("app", A1)] == res0["levels"][("app", A1)]
    lv = cb.ship_levels(part["ledger"], A1, agent_on=True)["CPI"]
    acc = [x for x in lv if x["src"] == "accepted"][0]
    assert acc["st"] == "now" and acc["ag"]["st"] == "passed"
    net = {x["fam"]: x for x in part["ledger"]["agent"]["net"]}
    assert net["CPI"]["src"] == "settle" and net["CPI"]["row"] == rows_of(part, "CPI")[0]["id"]
    assert net["CPI"]["fired"] is None and net["CPI"]["r2"] and net["CPI"]["r3"]["why"] is None
    assert part["agent"]["ag"].board["settle"]["passed"] == 2


def test_dj_a_waiting_settle_is_asked_weekly_and_a_later_accept_closes_it_even_in_trial(tmp_path, agent_on):
    own, others = market_move()
    ents = ag_world(own, others)
    s0 = app_eps(CA.run(ents, CA.P_PROD, ag_day(AGN - 1)), "CPI")[0]
    s_ix = (date.fromisoformat(s0["closed"]) - date.fromisoformat(AG0)).days
    first = s_ix + (7 - s_ix % 7)                                             # the first phase day after the settle
    seen = []
    for t_ix in (s_ix, first, first + 7, first + 14, first + 21, first + 28):
        res, part = ag_build(tmp_path, ents, t_ix)
        r = rows_of(part, "CPI")[0]
        seen.append((t_ix, r["dec"], r["branch"], len(r["asks"]), part["ledger"]["agent"]["trial"]["st"]))
        if r["dec"] == "accept":
            break
    assert seen[0][1:4] == ("wait", "unmeasured", 1) and len(seen) >= 3     # as of the settle day: too young
    assert all(x[4] == "trial" for x in seen)
    t_acc = seen[-1][0]
    assert seen[-1][1:3] == ("accept", "cpi_market") and t_acc > s_ix
    assert [x[3] for x in seen] == list(range(1, len(seen) + 1))             # one ask per weekly phase day
    r = rows_of(part, "CPI")[0]
    assert r["applied"]["veto"] == {"since_t": ag_day(s_ix)}
    assert r["applied"]["accept"]["day"] == ag_day(t_acc) and r["asks"][-1]["trial"] is False
    ep = app_eps(res, "CPI")[0]
    assert (ep["closed"], ep["why"]) == (ag_day(t_acc), "agent")
    row = [x for x in res["levels"][("app", A1)]["CPI"] if x["src"] == "accepted_agent"][0]
    m = CA.measure(ents[0], CA.P_PROD, "CPI", *r["applied"]["accept"]["days"])
    assert row["day"] == ag_day(t_acc) and abs(row["v"] / m["v"] - 1) < 1e-12 and row["act"] == r["id"]
    lv = cb.ship_levels(part["ledger"], A1, agent_on=True)["CPI"]
    assert [x["st"] for x in lv if x["src"] == "accepted"] == ["hold"]          # the settle the agent held
    assert [x["ag"]["st"] for x in lv if x["src"] == "accepted_agent"] == ["agent"]
    assert part["agent"]["ag"].board["settle"]["later"] == 2


def test_dj_the_first_build_asks_every_settle_in_force_as_of_its_day_and_only_those(tmp_path, agent_on):
    s = ag_series(1)
    ag_mul(s, "inst", 150, AGN, 1 / 1.5)                                      # a CPI settle ~day 215 …
    ag_mul(s, "inst", 330, AGN, 1 / 1.1)                                      # … replaced by a +10 % auto level later
    ag_mul(s, "rev", 200, AGN, 0.7)                                           # an eCPM settle (never asked)
    ents = ag_world(s, market_apps())
    res0 = CA.run(ents, CA.P_PROD, ag_day(AGN - 1))
    lv = res0["levels"][("app", A1)]
    assert [x["src"] for x in lv["CPI"]][-1] == "auto" and "accepted" in [x["src"] for x in lv["CPI"]]
    assert [e["why"] for e in app_eps(res0, "ECPM")] == ["settled"]
    gap = app_eps(res0, "GAP")
    res, part = ag_build(tmp_path, ents, AGN - 1)
    asked = sorted({r["fam"] for r in part["ledger"]["agent"]["rows"]})
    assert "CPI" not in asked and "ECPM" not in asked                         # replaced: history; eCPM: never
    assert asked == (["GAP"] if gap and gap[-1]["why"] == "settled" and
                     lv["GAP"][-1]["src"] == "accepted" else [])
    # a settle in force on the first build: asked as of its settle day, from data cut there
    ents2 = ag_world(scale_up(), market_apps())
    _, part2 = ag_build(tmp_path / "b", ents2, AGN - 1)
    a = rows_of(part2, "CPI")[0]["asks"][0]
    d = a["d"]
    assert a["on"] == "settle" and d < ag_day(AGN - 1) and a["ri"]["d"] == d
    app = ents2[0]
    lim = (date.fromisoformat(d) - date.fromisoformat(AG0)).days

    def poison(e):
        return CA.Ent(e.kind, e.id, e.app, e.label, e.day0, {k: [x if i <= lim - LA.LAGS.get(k, 0) else x * 9.0 + 7.0
                                                                 for i, x in enumerate(v)] for k, v in e.s.items()})
    ep = {"fam": "CPI", "opened": a["ri"]["ep"]["opened"], "c": a["ri"]["ep"]["c"], "base": a["ri"]["old"]["v"],
          "bspan": a["ri"]["old"]["days"], "base_src": "before"}
    camps = [poison(e) for e in ents2 if e.kind == "camp"]
    ri = LA.evidence(poison(app), camps, [], ep, a["days"], d, "settle", CA.P_PROD)
    assert json.dumps(ri, sort_keys=True) == json.dumps(a["ri"], sort_keys=True)
    mkt = LA.market(ri, poison(app), [poison(e) for e in ents2 if e.kind == "app" and e.id != A1])
    assert json.dumps(mkt, sort_keys=True) == json.dumps(a["mkt"], sort_keys=True)


def settle_ix(res, fam):
    return (date.fromisoformat(app_eps(res, fam)[0]["closed"]) - date.fromisoformat(AG0)).days


def test_revert_r3_an_agent_accept_whose_level_comes_back_is_reverted(tmp_path, agent_on):
    own, others = market_move()
    for d in range(400, AGN):
        own["inst"][d] *= 1.6                                                  # CPI back at the old level from day 400
    ents = ag_world(own, others)
    s_ix = settle_ix(CA.run(ents, CA.P_PROD, ag_day(399)), "CPI")
    first = s_ix + (7 - s_ix % 7)
    for t_ix in (s_ix, first, first + 7, first + 14):
        res, part = ag_build(tmp_path, ents, t_ix)
    r = rows_of(part, "CPI")[0]
    acc = r["applied"]["accept"]["day"]
    assert app_eps(res, "CPI")[0]["why"] == "agent"
    res, part = ag_build(tmp_path, ents, 430)
    r = rows_of(part, "CPI")[0]
    ep = app_eps(res, "CPI")[0]
    assert r["rev"]["by"] == "r3" and acc <= r["rev"]["day"] <= ag_day(430) and r["rev"]["t"] == ag_day(430)
    assert (ep["why"], ep["closed"]) == ("recovered", r["rev"]["day"])         # re-opened from c, closed on its day
    assert ep["c"] == r["ep"]["c"] and (r["vd"], r["ve"]) == ("wrong", "wrong")
    lv = cb.ship_levels(part["ledger"], A1, agent_on=True)["CPI"]
    rv = [x for x in lv if x["src"] == "accepted_agent"]
    assert [x["st"] for x in rv] == ["reverted"] and rv[0]["from"] == acc
    ag = part["agent"]["ag"]
    assert ag.board["n"]["reverted"] >= 1 and ag.ship_data[A1]["tag"]["st"] == "reverted"
    assert part["agent"]["quiet"][(A1, "CPI", ep["opened"])] == ag_day(430)
    net = [x for x in part["ledger"]["agent"]["net"] if x["fam"] == "CPI"][0]
    assert net["fired"] == {"by": "r3", "day": r["rev"]["day"]} and net["done"]
    res2, part2 = ag_build(tmp_path, ents, 437)                                # a revert is final: never asked again
    r2 = rows_of(part2, "CPI")[0]
    assert r2["rev"] == r["rev"] and len(r2["asks"]) == len(r["asks"])


def test_revert_r2_alone_reverts_an_engine_settle_nobody_asked(tmp_path, agent_on):
    s = ag_series(1)
    for k in ("sp_usd", "sp_inr", "inst", "d0_inr"):
        ag_mul(s, k, 300, AGN, 0.4)                                           # spend −60 %, held: a SPEND settle
        ag_mul(s, k, 380, AGN, 0.85 / 0.4)                                    # then back to 85 % of the old spend
    ents = ag_world(s, market_apps())
    s_ix = settle_ix(CA.run(ents, CA.P_PROD, ag_day(379)), "SPEND")
    res, part = ag_build(tmp_path, ents, s_ix + 70)
    r = rows_of(part, "SPEND")[0]
    assert (r["why"], r["dec"], r["branch"], r["asks"]) == ("revert", "revert", "revert_r2", [])
    assert r["rev"]["by"] == "r2" and (r["vd"], r["ve"]) == ("wrong", "wrong")
    net = [x for x in part["ledger"]["agent"]["net"] if x["fam"] == "SPEND"][0]
    assert net["src"] == "settle" and net["row"] == r["id"] and net["r3"]["why"] is None    # no recovery: R2 alone
    assert [c[2] for c in net["r2"]][:2] == [False, False] and net["r2"][-1][2] is True
    ep = app_eps(res, "SPEND")[0]
    assert ep["why"] is None and ep["c"] == r["ep"]["c"]                       # the alarm goes on from its change start
    assert "back at the old level: two 28-day checks in a row" in r["cause"]


def test_revert_an_ecpm_settle_that_comes_back(tmp_path, agent_on):
    s = ag_series(1)
    ag_mul(s, "rev", 200, 290, 0.7)                                           # eCPM −30 %: settled, then back at day 290
    ents = ag_world(s, market_apps())
    res0 = CA.run(ents, CA.P_PROD, ag_day(330))
    e0 = app_eps(res0, "ECPM")[0]
    assert e0["why"] == "settled"
    res, part = ag_build(tmp_path, ents, 330)
    r = rows_of(part, "ECPM")[0]
    ep = app_eps(res, "ECPM")[0]
    assert (r["why"], r["rev"]["by"], r["branch"]) == ("revert", "r3", "revert_r3")
    assert (ep["opened"], ep["why"], ep["closed"]) == (e0["opened"], "recovered", r["rev"]["day"])
    assert ep["closed"] > e0["closed"] and r["short"] == "back at old level: reverted"


def waves():
    """CPI ×2 from day 200 with ±25 % waves: open 120+ days, never steady; the other apps flat → own campaigns."""
    s = ag_series(1)
    for d in range(200, AGN):
        s["inst"][d] /= 2.0 * (1 + 0.25 * math.sin(2 * math.pi * (d - 200) / 112))
    return s


def test_proposal_asks_first_day_then_the_weekly_phase_frozen_against_restated_data(tmp_path, agent_on, monkeypatch):
    own = waves()
    ents = ag_world(own, market_apps())
    p_day = app_eps(CA.run(ents, CA.P_PROD, ag_day(AGN - 1)), "CPI")[0]["suggest"][0]
    p_ix = (date.fromisoformat(p_day) - date.fromisoformat(AG0)).days
    nxt = p_ix + (7 - p_ix % 7)
    _, part = ag_build(tmp_path, ents, p_ix)
    r = rows_of(part, "CPI")[0]
    assert (r["why"], r["dec"], r["branch"], r["first"], r["n"]) == ("open", "keep", "own_campaigns", p_day, 1)
    assert r["next"] == ag_day(nxt) and r["asks"][0]["on"] == "proposal"
    first = {k: v for k, v in r["asks"][0].items() if k != "vin"}             # (vin: its later vintage re-asks)
    _, part = ag_build(tmp_path, ents, p_ix + 1)                              # not a phase day: not asked
    assert rows_of(part, "CPI")[0]["n"] == 1
    _, part = ag_build(tmp_path, ents, nxt)
    assert [a["d"] for a in rows_of(part, "CPI")[0]["asks"]] == [p_day, ag_day(nxt)]
    for d in range(p_ix - 20, p_ix - 10):                                     # Google restates installs in its window
        own["inst"][d] *= 1.2
    _, part = ag_build(tmp_path, ag_world(own, market_apps()), nxt + 10)      # a missed phase day: asked on this build
    r = rows_of(part, "CPI")[0]
    assert [a["d"] for a in r["asks"]] == [p_day, ag_day(nxt), ag_day(nxt + 10)] and r["n"] == 3
    assert {k: v for k, v in r["asks"][0].items() if k != "vin"} == first     # a frozen answer is never rewritten
    assert r["next"] == LA.next_phase(ag_day(nxt + 10)) and r["dec"] == "keep"
    real = LA.decide

    def other(ri, mkt, cfg, flags=None, **kw):
        out = real(ri, mkt, cfg, flags, **kw)
        return dict(out, decision="wait", branch="narrow", short="narrow: campaigns 50%") if ri["d"] == ag_day(
            nxt + 17) else out
    monkeypatch.setattr(LA, "decide", other)
    _, part = ag_build(tmp_path, ag_world(own, market_apps()), nxt + 17)
    r = rows_of(part, "CPI")[0]
    assert (r["dec"], r["branch"], r["n"]) == ("wait", "narrow", 4)
    assert {k: v for k, v in r["asks"][0].items() if k != "vin"} == first
    assert [x[3:5] for x in part["agent"]["ag"].ship_data[A1]["rows"][0]["h"]] == [["wait", "narrow"],
                                                                                    ["keep", "own_campaigns"]]


def ecpm_world():
    """eCPM −30 % from day 200 on the app and on 3 other apps (too small to buy users: no alarm of their own)."""
    own = ag_series(1)
    ag_mul(own, "rev", 200, AGN, 0.7)
    others = []
    for i in range(3):
        s = ag_series(60 + i, sp=5.0, cpi=2.0, dau=2000.0)
        ag_mul(s, "rev", 200, AGN, 0.7)
        others.append(s)
    return own, others


@pytest.fixture
def no_ecpm_settle(monkeypatch):
    """The engine without its own eCPM settle: the only way an eCPM proposal can stand until the agent accepts it."""
    monkeypatch.setitem(CA.P_PROD["settle"], "fams", ["CPI", "GAP", "IPU", "SPEND"])


def test_trial_an_accept_is_recorded_not_applied_until_a_clean_28_day_trial(tmp_path, agent_on, no_ecpm_settle,
                                                                            monkeypatch):
    own, others = ecpm_world()
    ents = ag_world(own, others)
    res0 = CA.run(ents, CA.P_PROD, ag_day(AGN - 1))
    p_ix = (date.fromisoformat(app_eps(res0, "ECPM")[0]["suggest"][0]) - date.fromisoformat(AG0)).days
    res, part = ag_build(tmp_path, ents, p_ix)
    r = rows_of(part, "ECPM")[0]
    assert (r["dec"], r["branch"], r["asks"][0]["trial"], r["applied"]["accept"]) == ("accept", "ecpm_market", True,
                                                                                      None)
    assert app_eps(res, "ECPM") == app_eps(CA.run(ents, CA.P_PROD, ag_day(p_ix)), "ECPM")       # nothing applied
    assert [p["fam"] for p in part["props"][A1]] == ["ECPM"]                    # the owner's Accept stays
    ag = part["agent"]["ag"]
    assert ag.ship_data[A1]["tag"]["st"] == "trial" and ag.board["trial"]["st"] == "trial"
    sts = []
    for t_ix in (p_ix + 7, p_ix + 14, p_ix + 21, p_ix + 28):
        res, part = ag_build(tmp_path, ents, t_ix)
        sts.append(part["ledger"]["agent"]["trial"]["st"])
        assert app_eps(res, "ECPM")[0]["closed"] is None
    blk = part["ledger"]["agent"]
    assert sts == ["trial", "trial", "trial", "live"] and blk["trial"]["exit"] == ag_day(p_ix + 28)
    assert blk["vintage"]["done7"] >= 1 and blk["vintage"]["done28"] >= 1 and blk["vintage"]["accept_flips"] == 0
    assert blk["parity"]["bad"] == 0 and blk["parity"]["checked"] > 0
    assert all(a["trial"] for a in rows_of(part, "ECPM")[0]["asks"])        # a trial accept is never applied later
    res, part = ag_build(tmp_path, ents, p_ix + 35)                           # the next ask applies
    r = rows_of(part, "ECPM")[0]
    ep = app_eps(res, "ECPM")[0]
    assert r["asks"][-1]["trial"] is False and r["applied"]["accept"]["day"] == ag_day(p_ix + 35)
    assert (ep["why"], ep["closed"]) == ("agent", ag_day(p_ix + 35))
    row = [x for x in res["levels"][("app", A1)]["ECPM"] if x["src"] == "accepted_agent"][0]
    assert abs(row["v"] / CA.measure(ents[0], CA.P_PROD, "ECPM", *row["days"])["v"] - 1) < 1e-12
    ag = part["agent"]["ag"]
    assert ag.ship_data[A1]["tag"] == {"st": "accepted", "fam": "ECPM", "short": "eCPM market move",
                                       "day": ag_day(p_ix + 35), "more": 1}             # (+ the GAP settle on hold)
    assert rows_of(part, "GAP")[0]["applied"]["veto"] and rows_of(part, "GAP")[0]["dec"] == "wait"
    assert ag.board["n"]["accepted"] == 1 and ag.board["n"]["pending"] == 1
    assert ag.board["trial"]["st"] == "live" and ag.board["trial"]["exit"] == ag_day(p_ix + 28)
    real = LA.decide                                                          # live → trial again on a mismatch

    def off_by_one(ri, mkt, cfg, flags=None, **kw):
        out = real(ri, mkt, cfg, flags, **kw)
        return dict(out, branch="app_only") if ri["d"] == ag_day(p_ix) else out
    monkeypatch.setattr(LA, "decide", off_by_one)
    _, part = ag_build(tmp_path, ents, p_ix + 42)
    tr = part["ledger"]["agent"]["trial"]
    assert (tr["st"], tr["why"], tr["since"], tr["exit"]) == ("trial", "parity", ag_day(p_ix + 42), None)
    assert tr["log"][-2:] == [[ag_day(p_ix + 28), "live", "clean"], [ag_day(p_ix + 42), "trial", "parity"]]


def test_trial_a_vintage_flip_a_parity_mismatch_or_a_rule_change_start_it_again(tmp_path, agent_on, no_ecpm_settle,
                                                                                monkeypatch):
    own, others = ecpm_world()
    ents = ag_world(own, others)
    p_ix = (date.fromisoformat(app_eps(CA.run(ents, CA.P_PROD, ag_day(AGN - 1)), "ECPM")[0]["suggest"][0])
            - date.fromisoformat(AG0)).days
    ag_build(tmp_path, ents, p_ix)
    own2 = {k: list(v) for k, v in own.items()}
    own2["rev"][p_ix - 5] *= 3.0                                              # a restated day inside the ask's window
    ents2 = ag_world(own2, others)
    _, part = ag_build(tmp_path, ents2, p_ix + 7)
    blk = part["ledger"]["agent"]
    a0 = rows_of(part, "ECPM")[0]["asks"][0]
    assert a0["vin"]["7"]["acc_flip"] and a0["vin"]["7"]["dec"] == "wait" and a0["dec"] == "accept"
    assert blk["vintage"]["accept_flips"] == 1 and blk["trial"] == dict(blk["trial"], st="trial", why="vintage",
                                                                         since=ag_day(p_ix + 7))
    for t_ix in (p_ix + 14, p_ix + 21, p_ix + 28):
        _, part = ag_build(tmp_path, ents2, t_ix)
    assert part["ledger"]["agent"]["trial"]["st"] == "trial"                  # no exit 28 days after the start
    real = LA.decide

    def off_by_one(ri, mkt, cfg, flags=None, **kw):
        out = real(ri, mkt, cfg, flags, **kw)
        return dict(out, branch="app_only") if ri["d"] == ag_day(p_ix) else out
    monkeypatch.setattr(LA, "decide", off_by_one)
    _, part = ag_build(tmp_path, ents2, p_ix + 35)
    blk = part["ledger"]["agent"]
    assert blk["parity"]["bad"] >= 1 and blk["parity"]["last_bad"] == ag_day(p_ix + 35)
    assert (blk["trial"]["why"], blk["trial"]["since"]) == ("parity", ag_day(p_ix + 35))
    monkeypatch.setattr(LA, "decide", real)
    checked = blk["parity"]["checked"]
    old_th = [a["th"] for a in rows_of(part, "ECPM")[0]["asks"]]
    monkeypatch.setattr(cb, "agent_cfg", lambda: dict(agent_on, move_bands=2.5))
    _, part = ag_build(tmp_path, ents2, p_ix + 42)
    blk = part["ledger"]["agent"]
    asks = rows_of(part, "ECPM")[0]["asks"]
    assert (blk["trial"]["why"], blk["trial"]["since"]) == ("rule", ag_day(p_ix + 42)) and blk["th"] != old_th[0]
    assert [a["th"] for a in asks[:-1]] == old_th and asks[-1]["th"] == blk["th"]   # old asks: not rewritten …
    new = sum(1 for r in blk["rows"] for a in r["asks"] if a["th"] == blk["th"])
    assert 1 <= new and blk["parity"]["checked"] - checked == new             # … and not compared
    whys = [x[2] for x in blk["trial"]["log"]]
    assert all(x[1] == "trial" for x in blk["trial"]["log"]) and whys[0] == "start" and whys[-2:] == ["parity", "rule"]
    assert set(whys[1:-2]) == {"vintage"}                                     # (the +28 re-ask flipped again)


def ag_act(n, kind, at, fam="CPI", **kw):
    a = {"id": "a-%012x" % n, "at": at, "by": "owner@example.com", "app": A1, "fam": fam, "act": kind}
    a.update(kw)
    return a


def later_than(part, k=1):
    """An owner action time after this build's agent rows were first seen."""
    seen = max(r["seen"] for r in part["ledger"]["agent"]["rows"])
    return (datetime.strptime(seen, "%Y-%m-%dT%H:%M:%SZ") + timedelta(minutes=k)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_owner_accept_on_a_kept_proposal_overrides_and_holds_the_family(tmp_path, agent_on):
    ents = ag_world(waves(), market_apps())
    p_ix = (date.fromisoformat(app_eps(CA.run(ents, CA.P_PROD, ag_day(AGN - 1)), "CPI")[0]["suggest"][0])
            - date.fromisoformat(AG0)).days
    _, part = ag_build(tmp_path, ents, p_ix)
    r = rows_of(part, "CPI")[0]
    assert r["dec"] == "keep"
    acts = [ag_act(1, "accept", later_than(part), proposal={"day": ag_day(p_ix), "days": [ag_day(p_ix - 27),
                                                                                         ag_day(p_ix)]},
                   **{"from": ag_day(p_ix + 7)})]
    for t_ix in (p_ix + 7, p_ix + 14):
        res, part = ag_build(tmp_path, ents, t_ix, acts=acts)
        r = rows_of(part, "CPI")[0]
        assert (app_eps(res, "CPI")[0]["closed"], app_eps(res, "CPI")[0]["why"]) == (ag_day(p_ix + 7), "owner")
        assert r["n"] == 1                                                     # never asked while the owner holds it
        row = [x for x in part["agent"]["ag"].ship_data[A1]["rows"] if x["fam"] == "CPI"][0]
        assert row["st"] == "overridden" and row["ovr"] == {"at": acts[0]["at"], "act": "accept"}
    assert part["agent"]["ag"].board["n"]["overridden"] == 1


def test_owner_pin_holds_a_family_until_back_to_auto(tmp_path, agent_on):
    own = waves()
    ents = ag_world(own, market_apps())
    first = CA.measure(ents[0], CA.P_PROD, "CPI", ag_day(100), ag_day(127))
    p_ix = (date.fromisoformat(app_eps(CA.run(ents, CA.P_PROD, ag_day(AGN - 1)), "CPI")[0]["suggest"][0])
            - date.fromisoformat(AG0)).days
    pin = ag_act(1, "set", "2024-01-03T00:00:00Z", days=[ag_day(100), ag_day(127)], **{"from": ag_day(150)})
    res, part = ag_build(tmp_path, ents, p_ix, acts=[pin])
    assert first and app_eps(res, "CPI")[0]["suggest"][1] == "open" and rows_of(part, "CPI") == []   # held: no ask
    auto = ag_act(2, "auto", "2024-01-04T00:00:00Z", **{"from": ag_day(p_ix + 3)})
    _, part = ag_build(tmp_path, ents, p_ix + 7, acts=[pin, auto])
    assert [(r["dec"], r["asks"][0]["d"]) for r in rows_of(part, "CPI")] == [("keep", ag_day(p_ix + 7))]


def test_owner_reject_of_an_agent_level_holds_it_and_undo_gives_the_agents_answer_back(tmp_path, agent_on):
    own, others = market_move()
    ents = ag_world(own, others)
    s_ix = settle_ix(CA.run(ents, CA.P_PROD, ag_day(AGN - 1)), "CPI")
    first = s_ix + (7 - s_ix % 7)
    for t_ix in (s_ix, first, first + 7, first + 14):
        res, part = ag_build(tmp_path, ents, t_ix)
    r = rows_of(part, "CPI")[0]
    acc = r["applied"]["accept"]["day"]
    lid = [x for x in part["ledger"]["apps"][A1]["CPI"] if x["src"] == "accepted_agent"][0]["id"]
    rej = ag_act(1, "reject", later_than(part), level=lid)
    res, part = ag_build(tmp_path, ents, first + 21, acts=[rej])
    ep = app_eps(res, "CPI")[0]
    assert ep["closed"] is None and ep["suggest"][1] == "held"                # the owner's veto: no agent close
    row = [x for x in part["agent"]["ag"].ship_data[A1]["rows"] if x["fam"] == "CPI"][0]
    assert row["st"] == "held" and row["ovr"]["act"] == "reject"
    assert rows_of(part, "CPI")[0]["applied"]["accept"]["day"] == acc         # the frozen answer stays
    undo = {"id": "a-%012x" % 2, "at": later_than(part, 2), "act": "undo", "ref": rej["id"]}
    res, part = ag_build(tmp_path, ents, first + 28, acts=[rej, undo])
    ep = app_eps(res, "CPI")[0]
    assert (ep["closed"], ep["why"]) == (acc, "agent")
    assert [x for x in part["agent"]["ag"].ship_data[A1]["rows"] if x["fam"] == "CPI"][0]["st"] == "accepted"


def test_owner_use_this_level_on_a_blocked_settle_overrides_the_agent(tmp_path, agent_on):
    ents = ag_world(scale_up(), market_apps())
    _, part = ag_build(tmp_path, ents, AGN - 8)
    blocked = [x for x in part["ledger"]["apps"][A1]["CPI"] if (x.get("ag") or {}).get("st") == "blocked"][0]
    n0 = rows_of(part, "CPI")[0]["n"]
    rb = ag_act(1, "rollback", later_than(part), level=blocked["id"], **{"from": ag_day(AGN - 3)})
    res, part = ag_build(tmp_path, ents, AGN - 1, acts=[rb])
    ep = app_eps(res, "CPI")[0]
    assert (ep["closed"], ep["why"]) == (ag_day(AGN - 3), "owner")
    pin = [x for x in res["levels"][("app", A1)]["CPI"] if x["src"] == "rollback"][0]
    assert pin["days"] == blocked["days"] and abs(pin["v"] / blocked["v"] - 1) < 1e-12
    row = [x for x in part["agent"]["ag"].ship_data[A1]["rows"] if x["fam"] == "CPI"][0]
    assert row["st"] == "overridden" and row["ovr"]["act"] == "rollback" and rows_of(part, "CPI")[0]["n"] == n0


def money_drop():
    s = ag_series(1)
    ag_mul(s, "d0_inr", 250, AGN, 0.75)                                       # D0 ROAS 40 % → 30 %, held
    return s


def test_money_a_forced_accept_is_a_wait_and_an_agent_money_level_is_refused(tmp_path, agent_on, monkeypatch, capsys):
    ents = ag_world(money_drop(), market_apps())
    res0 = CA.run(ents, CA.P_PROD, ag_day(AGN - 1))
    assert [p["why"] for p in res0["proposals"][("app", A1)] if p["fam"] == "ROAS_G"] == ["money"]
    real = LA._c1

    def yes(ri, mkt, th):
        out = real(ri, mkt, th)
        return dict(out, dec="accept", ext=out["cause"], ext_branch="cpi_market", branch="cpi_market")
    monkeypatch.setattr(LA, "_c1", yes)
    res, part = ag_build(tmp_path, ents, AGN - 1)
    r = rows_of(part, "ROAS_G")[0]
    assert (r["why"], r["dec"], r["branch"], r["applied"]) == ("money", "wait", "money_guard",
                                                                {"veto": None, "accept": None})
    assert app_eps(res, "ROAS_G") == app_eps(res0, "ROAS_G")                  # nothing applied
    monkeypatch.setattr(LA, "_c1", real)
    led = json.load(open(cb.levels_path(str(tmp_path / "data"))))
    for x in led["agent"]["rows"]:
        if x["fam"] == "ROAS_G":
            x["applied"]["accept"] = {"day": ag_day(AGN - 1), "days": [ag_day(AGN - 28), ag_day(AGN - 1)],
                                      "since_t": ag_day(AGN - 1)}
    json.dump(led, open(cb.levels_path(str(tmp_path / "data")), "w"))
    capsys.readouterr()
    res, part = ag_build(tmp_path, ents, AGN - 1)
    err = capsys.readouterr().err
    assert skipped(err, "cpi agent skipped") == ["cpi agent skipped: AgentMoneyError"]
    assert app_eps(res, "ROAS_G") == app_eps(res0, "ROAS_G") and part["agent"] is None
    assert part["ledger"]["agent"] == led["agent"]                             # written back unchanged


def test_failure_costs_the_agent_only_the_block_written_back_unchanged(tmp_path, agent_on, monkeypatch, capsys):
    ents = ag_world(scale_up(), market_apps())
    _, part = ag_build(tmp_path, ents, AGN - 8)
    saved = open(cb.levels_path(str(tmp_path / "data"))).read()
    blk = json.loads(saved)["agent"]

    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(cb, "agent_run", boom)
    capsys.readouterr()
    res, part = ag_build(tmp_path, ents, AGN - 1)
    err = capsys.readouterr().err
    assert skipped(err, "cpi agent") == ["cpi agent skipped: RuntimeError"] and health.SKIP.search(err)
    assert app_eps(res, "CPI") == app_eps(CA.run(ents, CA.P_PROD, ag_day(AGN - 1)), "CPI")      # the automatic result
    assert part["agent"] is None and json.dumps(part["ledger"]["agent"], sort_keys=True) == json.dumps(blk,
                                                                                                  sort_keys=True)
    assert "ag" not in json.dumps(cb.ship_levels(part["ledger"], A1))         # marks kept, not shipped


def test_a_timeout_keeps_the_answers_made_and_applies_nothing(tmp_path, agent_on, monkeypatch, capsys):
    ents = ag_world(scale_up(), market_apps())
    calls = []

    def clock():
        calls.append(1)
        return 0.0 if len(calls) <= 3 else 1000.0                            # past budget after the two settle asks
    monkeypatch.setattr(cb, "_clock", clock)
    capsys.readouterr()
    res, part = ag_build(tmp_path, ents, AGN - 1)
    assert skipped(capsys.readouterr().err, "cpi agent") == ["cpi agent skipped: AgentTimeout"]
    assert app_eps(res, "CPI")[0]["why"] == "settled" and part["agent"] is None
    rows = json.load(open(cb.levels_path(str(tmp_path / "data"))))["agent"]["rows"]
    assert sorted((r["fam"], len(r["asks"]), r["applied"]["veto"]) for r in rows) == [("CPI", 1, None), ("GAP", 1, None)]
    monkeypatch.setattr(cb, "_clock", lambda: 0.0)
    res, part = ag_build(tmp_path, ents, AGN - 1)                             # the next build goes on from there
    r = rows_of(part, "CPI")[0]
    assert r["applied"]["veto"] == {"since_t": ag_day(AGN - 1)} and app_eps(res, "CPI")[0]["closed"] is None
    assert r["asks"][0]["on"] == "settle" and len(r["asks"]) == 2


def test_no_history_file_and_a_bad_backtest_file(tmp_path, agent_on, capsys):
    ents = ag_world(scale_up(), market_apps())
    (tmp_path / "data" / "cpi").mkdir(parents=True)
    open(cb.levels_path(str(tmp_path / "data")), "w").write("{broken")
    capsys.readouterr()
    res, part = ag_build(tmp_path, ents, AGN - 1)
    err = capsys.readouterr().err
    assert skipped(err, "cpi agent") == ["cpi agent skipped: NoLedger"] and part["agent"] is None
    good = {"v": 1, "years": 2.5,
            "proposals": {"moments": 10, "c1_accept": 1, "c1_right": 1, "c1_wrong": 0, "accept": 0},
            "settles": {"checked": 4, "passed": 0, "blocked": 3, "hold": 1, "level_held": 1}, "note": "synthetic"}
    for i, bad in enumerate((dict(good, years=60), dict(good, note="x" * 201), dict(good, note="a\u202eb"),
                             dict(good, settles=dict(good["settles"], hold=-1)), dict(good, extra=1), "[1")):
        tmp = tmp_path / ("b%d" % i)
        (tmp / "data" / "cpi").mkdir(parents=True)
        open(cb.backtest_path(str(tmp / "data")), "w").write(bad if isinstance(bad, str) else json.dumps(bad))
        _, part = ag_build(tmp, ents, AGN - 1)
        assert skipped(capsys.readouterr().err, "cpi agent backtest") == [
            "cpi agent backtest skipped: %s" % ("JSONDecodeError" if isinstance(bad, str) else "ValueError")]
        assert part["agent"]["ag"].board["bt"] is None
    tmp = tmp_path / "ok"
    (tmp / "data" / "cpi").mkdir(parents=True)
    json.dump(good, open(cb.backtest_path(str(tmp / "data")), "w"))
    _, part = ag_build(tmp, ents, AGN - 1)
    assert part["agent"]["ag"].board["bt"] == good and capsys.readouterr().err == ""


def test_the_agent_block_keeps_rule_inputs_on_the_asks_that_matter_and_stays_bounded():
    t = date(2026, 3, 28)
    asks = []
    for i in range(300):
        d = (t - timedelta(days=7 * (299 - i))).isoformat()
        dec = "keep" if (i // 50) % 2 == 0 else "wait"
        asks.append({"d": d, "t": d, "dec": dec, "branch": dec + "_b", "part": None, "k": {"old": 1.0},
                     "ri": {"pad": "x" * 9000, "i": i}, "mkt": {"n": i}})
    blk = {"rows": [{"asks": asks}], "net": []}
    cb._ag_trim(blk, t, CA.P_PROD["levels"]["agent"])
    kept = [i for i, a in enumerate(asks) if a["ri"] is not None]
    changes = [0] + [i for i in range(1, 300) if asks[i]["dec"] != asks[i - 1]["dec"]]
    recent = [i for i, a in enumerate(asks) if a["t"] >= (t - timedelta(days=35)).isoformat()]
    assert kept == sorted(set(changes) | set(range(295, 300)) | set(recent))
    assert all(a["k"] == {"old": 1.0} for a in asks) and len(asks) == 300
    big = {"rows": [{"asks": [dict(a, ri={"pad": "y" * 9000}, t=t.isoformat()) for a in asks]}], "net": []}
    cb._ag_trim(big, t, CA.P_PROD["levels"]["agent"])
    size = len(json.dumps(big, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    assert size <= cb.AG_MAX_BYTES and len(big["rows"][0]["asks"]) == 300
    assert big["rows"][0]["asks"][-1]["ri"] is not None and big["rows"][0]["asks"][0]["ri"] is None   # oldest first


def test_money_a_reopened_cpi_alarm_never_adds_to_the_money_lost(tmp_path, agent_on):
    own = scale_up()
    ag_mul(own, "d0_inr", 300, AGN, 0.75)                                     # and an open D0 ROAS alarm
    ents = ag_world(own, market_apps())
    res0 = CA.run(ents, CA.P_PROD, ag_day(AGN - 1))
    res, part = ag_build(tmp_path, ents, AGN - 1)
    assert app_eps(res, "CPI")[0]["closed"] is None and app_eps(res0, "CPI")[0]["why"] == "settled"
    assert app_eps(res, "ROAS_G") == app_eps(res0, "ROAS_G") and app_eps(res, "ROAS_G")[0]["closed"] is None
    D = cb._Days(date.fromisoformat(AG0), date.fromisoformat(ag_day(AGN - 1)))
    s = {k: list(v) for k, v in own.items()}
    R = [1 / 94.5] * D.n
    ts = ag_day(AGN - 1)

    def lost(r):
        eps = [e for e in r["episodes"] if e["kind"] == "app" and e["id"] == A1]
        return [cb.money_lost(eps, s, R, D.d0, a, ts, ts) for a in (ag_day(AGN - 14), ag_day(100))]
    assert lost(res) == lost(res0) and lost(res)[0]["fam"] == "ROAS_G"
    cpi = app_eps(res, "CPI")[0]
    assert cpi["money"]["what"] == "extra_paid" and cpi["money"]["since_c_inr"] > 0
    row = [x for x in part["agent"]["ag"].ship_data[A1]["rows"] if x["fam"] == "CPI"][0]
    assert row["xp"]["inr"] > 0 and row["xp"]["from"] == row["first"]
    assert "lost" not in json.dumps(part["agent"]["ag"].board)


# ── the agent in the whole step: mode off exactly as before, mode on through the real files ──────────────────────────

def site_bytes(site):
    out = {}
    for fn in sorted(os.listdir(site)):
        if fn.startswith("cpi"):
            with gzip.open(os.path.join(site, fn), "rb") as f:
                out[fn] = f.read()
    return out


def test_mode_off_runs_no_agent_code_and_carries_a_saved_block_unchanged(tmp_path, monkeypatch, capsys):
    a_dir, b_dir = tmp_path / "a", tmp_path / "b"
    (da, sa, dash_a), (db, sb, dash_b) = make(a_dir), make(b_dir)
    cb.run(dash_a, da, sa, {}, NOW)
    cb.pop_line()
    blk0 = cb._new_block(T, "2026-03-29T05:22:00Z", CA.P_PROD["levels"]["agent"])     # one an earlier "on" build wrote
    calls = []

    def trap(name):
        def f(*a, **k):
            calls.append(name)
            raise AssertionError(name)
        return f
    for mod, name in ((cb, "agent_run"), (cb, "load_backtest"), (cb, "_Agent"), (LA, "evidence"), (LA, "decide"),
                      (LA, "market"), (LA, "th_sha")):
        monkeypatch.setattr(mod, name, trap(name))
    capsys.readouterr()
    cb.run(dash_b, db, sb, {}, NOW)
    cb.pop_line()
    assert calls == [] and "cpi agent" not in capsys.readouterr().err
    assert site_bytes(sa) == site_bytes(sb)
    assert json.dumps(dash_a["cpi"], sort_keys=True) == json.dumps(dash_b["cpi"], sort_keys=True)
    assert open(cb.levels_path(da), "rb").read() == open(cb.levels_path(db), "rb").read()
    assert "agent" not in dash_b["cpi"] and "agent" not in json.load(open(cb.levels_path(db)))
    led = json.load(open(cb.levels_path(db)))
    led["agent"] = blk0
    led["agent"]["rows"].append({"id": "D-00000000aa", "app": IDS["a"], "fam": "CPI", "why": "open",
                                 "ep": {"opened": "2026-03-12", "c": "2026-03-10"}, "asks": [], "dec": "keep",
                                 "applied": {"veto": None, "accept": None}})
    row = led["apps"][IDS["a"]]["CPI"][0]
    row["ag"] = {"st": "blocked", "dec": "D-00000000aa", "short": "x", "cause": "x", "next": None}
    json.dump(led, open(cb.levels_path(db), "w"))
    want = json.dumps(led["agent"], sort_keys=True)
    cb.run(dash_b, db, sb, {}, NOW)
    cb.pop_line()
    got = json.load(open(cb.levels_path(db)))
    assert json.dumps(got["agent"], sort_keys=True) == want and calls == []
    assert [r.get("ag") for r in got["apps"][IDS["a"]]["CPI"] if r["id"] == row["id"]] == [row["ag"]]
    f = load(sb, dash_b["cpi"]["apps"][IDS["a"]]["file"])
    assert "ag" not in f and "ag" not in json.dumps(f["lv"]) and "agent" not in dash_b["cpi"]


def test_mode_on_the_whole_step_on_the_synthetic_site(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cb, "agent_cfg", lambda: dict(CA.P_PROD["levels"]["agent"]))
    data, site, dash = make(tmp_path)
    capsys.readouterr()
    assert cb.run(dash, data, site, {}, NOW) == ["/cpi*"]
    line = cb.pop_line()
    assert "cpi agent" not in capsys.readouterr().err and line.startswith("cpi: apps 4,")
    p = dash["cpi"]
    assert p["agent"]["mode"] == "on" and p["agent"]["since"] == T and p["agent"]["trial"]["st"] == "trial"
    assert sorted(p["agent"]) == ["bt", "mode", "ms", "n", "parity", "rule", "settle", "since", "th", "trial", "v",
                                  "vintage"]
    for k in "abde":
        raw = open(os.path.join(site, p["apps"][IDS[k]]["file"]), "rb").read()
        assert len(raw) < cb.MAX_GZ
        f = load(site, p["apps"][IDS[k]]["file"])
        assert isinstance(f["ag"]["rows"], list) and all("ag" in x for x in f["lp"])
        assert all("ag" in r for rows in f["lv"].values() for r in rows)
    assert "agent" in json.load(open(cb.levels_path(data)))


def dj_model(k, x, g):
    """Alpha: CPI ₹20 → ₹30 from 2025-10-01 with D0 ROAS 40 % → 30 %, then spend ×3 from 2025-10-15 (installs ×3);
    the others as model()."""
    if k != "a":
        return model(k, x, g)
    f = (lambda: 1.0 + 0.01 * next(g))
    up = 3.0 if x >= "2025-10-15" else 1.0
    m = {"sp": 50000.0 * up, "inst": 2500.0 * up / (1.5 if x >= "2025-10-01" else 1.0),
         "roas": 0.30 if x >= "2025-10-01" else 0.40, "imp": 50000.0, "ecpm": 6.0, "dau": 20000.0}
    m["inst"] = round(m["inst"] * f(), 2)
    m["d0"] = round(m["sp"] * m["roas"] * f(), 2)
    m["imp"] = int(m["imp"] * f())
    m["rev"] = round(m["imp"] * m["ecpm"] / 1000.0 * f(), 2)
    m["dau"] = int(m["dau"] * f())
    return m


def test_dj_through_the_real_files_blocked_settle_tag_money_and_no_push(tmp_path, monkeypatch):
    data, site, dash = make(tmp_path, day0="2025-01-01", mdl=dj_model)
    cb.run(dash, data, site, {}, NOW)                                          # mode off first: today's site, seeded
    cb.pop_line()
    off = copy.deepcopy(dash["cpi"])
    f_off = load(site, off["apps"][IDS["a"]]["file"])
    assert [e["why"] for e in eps_of(f_off, "CPI")][0] == "settled"
    monkeypatch.setattr(cb, "agent_cfg", lambda: dict(CA.P_PROD["levels"]["agent"]))
    dash2 = copy.deepcopy(dash)
    cb.run(dash2, data, site, {}, NOW)
    cb.pop_line()
    p = dash2["cpi"]
    a = p["apps"][IDS["a"]]
    f = load(site, a["file"])
    cpi = eps_of(f, "CPI")[0]
    assert cpi["closed"] is None and cpi["c"] == eps_of(f_off, "CPI")[0]["c"]  # re-opened from its own change start
    row = [x for x in f["ag"]["rows"] if x["fam"] == "CPI"][0]
    assert (row["st"], row["branch"], row["why"]) == ("blocked", "spend_scaled", "settle")
    assert row["cause"] == "seen with spend ×3.0 since the old level (your lever)" and row["xp"]["inr"] > 0
    lv = [x for x in f["lv"]["CPI"] if x["st"] == "blocked"]
    assert len(lv) == 1 and lv[0]["ag"]["dec"] == row["id"] and row["level"] == lv[0]["id"]
    assert a["ag"]["st"] in ("blocked", "kept") and p["agent"]["settle"]["blocked"] >= 1
    assert a["lost"] == off["apps"][IDS["a"]]["lost"] and a["lost"]["inr"] > 0 # the money stays the D0 ROAS one
    assert [x["lost"] for x in p["alerts"] if x["app_id"] == IDS["a"]] == \
        [x["lost"] for x in off["alerts"] if x["app_id"] == IDS["a"]]
    assert not any(x["notify"] for x in p["alerts"])                          # re-opened: seeded, never pushed
    assert all("ag" in x for x in f["lp"]) and [x["ag"]["st"] for x in f["lp"] if x["fam"] == "CPI"] == ["blocked"]
    led = json.load(open(cb.levels_path(data)))
    assert any(x["what"] == "blocked" for x in led["log"]) and led["agent"]["rows"]
