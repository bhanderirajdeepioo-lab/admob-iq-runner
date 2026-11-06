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
import os
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import build_static as bs
from admob_iq import cpi_build as cb
from admob_iq.config import settings
from admob_iq.db import write_json_gz_stable
from admob_iq.deploy_guard import HEADERS_MAX_RULES, headers_cover, headers_rule_count
from admob_iq.engine import cpi_alarm as CA
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


def make(tmp_path, fixed_till="2026-03-29", ok_till="2026-03-29", geo_till="2026-03-27", camp_till="2026-03-29"):
    """→ (data dir, site dir, dashboard): the stores and this build's site files written, the dashboard in memory."""
    data, site = tmp_path / "data", tmp_path / "site"
    data.mkdir(parents=True, exist_ok=True)
    site.mkdir(parents=True, exist_ok=True)
    ALL = days(DAY0, TODAY)
    M = {}
    for i, k in enumerate(NAMES):
        g = prng(101 + i)
        M[k] = {x: model(k, x, g) for x in ALL}
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
    write_json_gz_stable(str(cd / "state.json.gz"), {"v": 1, "first": DAY0, "till": camp_till, "done": True})
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
    write_json_gz_stable(str(gd / "state.json.gz"), {"v": 1, "ccy": "INR", "first": DAY0, "till": geo_till})
    # this build's GA4 / ROI site files (Alpha and Beta) + their pointers
    act, nvr, roi = [], {}, {}
    for k in ("a", "b"):
        aid, key = IDS[k], gu.file_key(IDS[k])
        till = "2026-03-27"
        a1 = [M[k][x]["dau"] for x in days(DAY0, till)]
        write_json_gz_stable(str(site / ("active_%s.json.gz" % key)), {"daily": {"start": DAY0, "a1": a1},
                                                                       "data_till": till})
        act.append({"app_id": aid, "key": key, "file": "active_%s.json.gz" % key})
        nd = []
        for x in days(DAY0, TODAY):
            m = M[k][x]
            fs = 0.3
            nd.append([x, [round(m["rev"] * fs * 0.8, 4), int(m["imp"] * fs), round(m["rev"] * (1 - fs * 0.8), 4),
                           int(m["imp"] * (1 - fs)), 0, 0], [100, int(m["inst"] * 1.1), 400, m["dau"]], {}, {}])
        write_json_gz_stable(str(site / ("nvr_%s.json.gz" % key)), {"days": nd, "final_till": till})
        nvr[aid] = {"file": "nvr_%s.json.gz" % key}
        rows = []
        for x in days(DAY0, "2026-03-29"):
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
    assert sorted(p) == ["alerts", "apps", "at", "closed", "counts", "day0", "file", "fv", "t", "till", "unlinked", "v"]
    assert (p["v"], p["t"], p["file"], p["at"]) == (1, T, "cpi.json.gz", "2026-03-30T05:22:00Z")
    assert p["till"] == {"spend": "2026-03-29", "d0": "2026-03-29", "admob": "2026-03-29", "ga4": "2026-03-27"}
    assert re.fullmatch(r"[0-9a-f]{12}", p["fv"])
    assert sorted(p["apps"]) == sorted(IDS[k] for k in "abde")                     # Hidden: not on this screen
    for k, key in keys.items():
        a = p["apps"][IDS[k]]
        assert sorted(a) == ["file", "key", "lost", "name", "nrm", "open", "since", "st", "to", "v"]
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


def test_unlinked_spend_is_every_store_without_a_row(built):
    u = built["dash"]["cpi"]["unlinked"]
    a = addd(T, -13)
    inr = sum(1000.0 + 5000.0 for _ in days(a, T))                   # the store with no AdMob app + Hidden
    usd = sum((1000.0 + 5000.0) * fxd(x) for x in days(a, T))
    assert u["n"] == 2 and u["inr"] == pytest.approx(inr, abs=0.01) and u["usd"] == pytest.approx(usd, abs=0.01)


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
        assert sorted(f) == ["app_id", "camps", "ctys", "d", "day0", "ep", "key", "name", "notes", "nrm", "src", "t",
                             "v"]
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
            assert sorted(c) == ["cc", "d", "ep", "from"] and sorted(c["d"]) == ["dl", "imp", "rev", "sp_inr", "sp_usd"]
            assert all(len(v) == nd(c["from"], T) for v in c["d"].values())
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
    assert not [x for x in os.listdir(site) if x.startswith("cpi")] and cb.pop_line() == "cpi: apps 0"


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
