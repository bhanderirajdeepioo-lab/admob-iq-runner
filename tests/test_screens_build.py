"""🖼️ Screens tab — the build (admob_iq.screens_build), on made-up stores written straight in the fetch's §2.7 layout (meta,
recent.json.gz, <grp>_<YYYY-MM>.json.gz month files) and a made-up dashboard (placements, apps_catalog, latest_complete,
report_tz): formats / kinds, what each grain gives, duplicate copies decided in runs, the package rule, the AdMob blend,
trigger labels, every status rule (N/A "Not whole": the missing W days counted by their state, the days with nothing to
read left out; N/A "Too few ads" under 1 % of the app's ads of the row's kind), screens judged on all formats when GA4
gives no screen × format split (allf 2 + the measured full-screen share), the exact LMDI split, unit stopped / changed,
the cause gates (units with no AdMob id their own gate), the developer report, the files / pointer / regex, only the
apps the catalog selects, the history cell (done and no skip day still read again), the write order and failure
isolation, the too-big guard, the month cache (a previous CACHE_V's caches derived again), a store month file that
cannot be read (counted, one health line, its days "x", never cached), a day the fetch never asked GA4 about ("skip":
shipped "-", not read yet — in scr_l too), the counts-only line and the backtest CLI."""
import gzip
import hashlib
import io
import json
import math
import os
import random
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import screens_build as sb
from admob_iq.db import write_json_gz_stable
from admob_iq.fetch import ga4_uninstall as gu

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 11, 4, 6, 0, tzinfo=timezone.utc)            # td 2026-11-04, ft 2026-11-02
AID = "ca-app-pub-0000000000000000~21"
AID2 = "ca-app-pub-0000000000000000~22"
KEY = gu.file_key(AID)
MAIN, EDIT, ADACT, NS = "x.y.MainActivity", "x.y.EditActivity", "com.google.android.gms.ads.AdActivity", "(not set)"
IDS = {"unit_a": "ca-app-pub-0000000000000000/1", "unit_n": "ca-app-pub-0000000000000000/2",
       "zz_back_1": "ca-app-pub-0000000000000000/3", "aoa_resume": "ca-app-pub-0000000000000000/4",
       "unit_b": "ca-app-pub-0000000000000000/5"}
FMT = {"unit_a": "banner", "unit_n": "native", "zz_back_1": "interstitial", "aoa_resume": "app_open",
       "unit_b": "banner"}
W0 = "2026-10-24"                                                  # the first day of W (ft − 9)


def _days(a, b):
    a, b = date.fromisoformat(a), date.fromisoformat(b)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def _j(d, k=3):
    """A deterministic small wiggle per day."""
    return int(hashlib.sha1(d.encode()).hexdigest(), 16) % (2 * k + 1) - k


def counts(d, sc):
    """One made-up GA4 day → views per class, ads per (class, format, unit), AdMob per unit [req, matched, imp]."""
    win = d >= W0
    views = {MAIN: 1000 + 5 * _j(d), EDIT: 2000 if sc.get("edit_from") and d >= sc["edit_from"] else 500, ADACT: 80,
             NS: 20}
    ads = {}
    main_unit, main_n = "unit_a", 200 + _j(d)
    if win and sc.get("swap"):
        main_unit, main_n = "unit_b", 100 + _j(d)
    if win and sc.get("show_w"):
        main_n = round(main_n * sc["show_w"])
    ads[(MAIN, "Banner", main_unit)] = main_n
    ads[(EDIT, "Native advanced", "unit_n")] = 50 + _j(d, 2)
    ads[(ADACT, "Interstitial", "zz_back_1")] = 30 + _j(d, 2)
    ads[(ADACT, "App open", "aoa_resume")] = 20
    ads[(NS, "Banner", "unit_a")] = 4 + (sc.get("ns_w", 0) if win else 0)
    gu_ = {}
    for (c, f, u), n in ads.items():
        gu_[u] = gu_.get(u, 0) + n
    tie = sc.get("tie", 1.0)
    adm = {}
    for u, g in gu_.items():
        base = g if not (u == "unit_a" and win and sc.get("show_w")) else round(g / sc["show_w"])
        imp = g / tie
        matched = base / tie / 0.6
        adm[u] = [matched / 0.9, matched, imp]
    if sc.get("swap") and not win:
        adm["unit_b"] = [0, 0, 0]
    if sc.get("swap") and win:
        adm["unit_a"] = [0, 0, 0]
    return views, ads, adm


def core_recs(d, sc):
    views, ads, _ = counts(d, sc)
    ta = {}
    w = {}
    for (c, f, u), n in ads.items():
        ta[f] = ta.get(f, 0) + n
        w[(f, u)] = w.get((f, u), 0) + n
    return {"t": {"st": "w", "v": [sum(views.values()), 10 * sum(views.values())], "a": [[f, n] for f, n in ta.items()],
                  "ev": 50000},
            "v": {"st": "w", "g": "c", "r": [[c, n, 10 * n] for c, n in views.items()]},
            "w": {"st": "w", "g": "u", "r": [[f, u, n] for (f, u), n in w.items()]},
            "a": {"st": "w", "g": "fu", "r": [[c, f, u, n] for (c, f, u), n in ads.items()]}}


def layer_recs(d, sc):
    views, ads, _ = counts(d, sc)
    ver = "1.0" if d < "2026-10-01" else "1.1"
    rv = [[ver, c, n] for c, n in views.items()]
    ra = [[ver, c, f, n] for (c, f, u), n in ads.items()]
    if "2026-09-25" <= d < "2026-10-05":                 # both versions live for ten days
        rv = [["1.0", c, n // 2] for c, n in views.items()] + [["1.1", c, n - n // 2] for c, n in views.items()]
        ra = [["1.0", c, f, n // 2] for (c, f, u), n in ads.items()] + \
             [["1.1", c, f, n - n // 2] for (c, f, u), n in ads.items()]
    cv = [["XA", c, n - n // 4] for c, n in views.items()] + [["XB", c, n // 4] for c, n in views.items()]
    ca = [["XA", c, f, n - n // 4] for (c, f, u), n in ads.items()] + [["XB", c, f, n // 4] for (c, f, u), n in ads.items()]
    return {"rV": {"st": "w", "g": "c", "r": rv}, "rA": {"st": "w", "g": "cf", "r": ra},
            "cV": {"st": "w", "g": "c", "r": cv}, "cA": {"st": "w", "g": "cf", "r": ca},
            "k": {"st": "w", "g": "c", "t": [["ad_click", 12]], "r": [[MAIN, "ad_click", 10], [EDIT, "ad_click", 2]]},
            "e": {"st": "w", "g": "c", "t": 9000, "r": [[MAIN, 6000], [EDIT, 3000]]},
            "uV": {"st": "w", "g": "c", "r": [[MAIN, 300, 200], [EDIT, 150, 100]]},
            "uA": {"st": "w", "g": "c", "r": [[MAIN, 150], [EDIT, 40]]},
            "s": {"st": "w", "g": "fs", "r": [["Banner", "Network A", 150], ["Banner", "Network B", 54]]},
            "x": {"st": "w", "ev": [], "t": [], "r": []},
            "nV": {"st": "w", "g": "c", "r": [["new", MAIN, 100], ["returning", MAIN, 900]]},
            "nA": {"st": "w", "g": "cf", "r": [["new", MAIN, "Banner", 20], ["returning", MAIN, "Banner", 180]]}}


def write_store(data, aid=AID, sc=None, first="2026-08-01", last="2026-11-04", package="x.y.app", now=NOW,
                tz="UTC", layers=True, day_fn=None):
    """A made-up store in the §2.7 layout: final days (≤ today − 5) in month files per group, the rest in recent."""
    sc = sc or {}
    key = gu.file_key(aid)
    cut = (now.date() - timedelta(days=4)).isoformat()
    groups = {"core": ("t", "v", "w", "a"), "small": ("k", "e", "uV", "uA", "s", "x", "nV", "nA"),
              "ver": ("rV", "rA"), "cc": ("cV", "cA")}
    files, recent = {}, {}
    for d in _days(first, last):
        recs = day_fn(d) if day_fn else core_recs(d, sc)
        if layers and not day_fn:
            recs.update(layer_recs(d, sc))
        if d >= cut:
            recent[d] = recs
            continue
        for g, ids in groups.items():
            part = {i: recs[i] for i in ids if i in recs}
            if part:
                files.setdefault((g, d[:7]), {})[d] = part
    base = os.path.join(str(data), "ga4_screens")
    os.makedirs(os.path.join(base, key), exist_ok=True)
    months = {}
    for (g, m), days in files.items():
        write_json_gz_stable(os.path.join(base, key, "%s_%s.json.gz" % (g, m)), {"v": 1, "days": days})
        months.setdefault(g, []).append(m)
    write_json_gz_stable(os.path.join(base, key, "recent.json.gz"), {"v": 1, "days": recent})
    meta = {"v": 1, "app_id": aid, "package": package, "property_id": "0", "stream_id": "0", "time_zone": tz,
            "reads": {"t": {"oldest": first, "done": True}, "a": {"oldest": first, "done": False}},
            "events": {"at": None, "names": []}, "months": {g: sorted(v) for g, v in months.items()}}
    write_json_gz_stable(os.path.join(base, key + ".json.gz"), meta)
    return key


def dashboard(sc=None, first="2026-07-01", last="2026-11-04", latest="2026-11-03", placements=True, aid=AID,
              app="App A", acct="pub-0"):
    sc = sc or {}
    daily = {u: [] for u in IDS}
    for d in _days(first, last):
        _, _, adm = counts(d, sc)
        for u, (req, mt, imp) in adm.items():
            daily[u].append([d, 0, round(imp), round(req), round(mt), 0])
    pl = [{"id": IDS[u], "name": u, "app": app, "account": acct, "format": FMT[u], "daily": daily[u]}
          for u in IDS if any(r[2] or r[3] for r in daily[u])] if placements else []
    return {"placements": pl, "apps_catalog": [{"account_id": acct, "app_id": aid, "app_name": app, "selected": True},
                                               {"account_id": acct, "app_id": AID2, "app_name": "App B",
                                                "selected": True}],
            "latest_complete": latest, "report_tz": "Asia/Calcutta"}


def app_of(tmp_path, sc=None, dash=None, aid=AID, **kw):
    data = tmp_path / "data"
    key = write_store(data, aid, sc, **kw)
    meta = sb.load_meta(str(data), key)
    rec = sb.load_recent(str(data), key)
    return sb.App(meta, sb.core_days(str(data), key, meta, rec), NOW, dash if dash is not None else dashboard(sc), {})


def gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


# ── formats, kinds, grains ──────────────────────────────────────────────────────────────────

def test_formats_and_screen_kinds():
    t = {"Banner": "banner", "MREC": "banner", "adaptive_banner": "banner", "Native advanced": "native",
         "zz_list_native": "native", "Interstitial": "interstitial", "inter": "interstitial", "App open": "appopen",
         "APP_OPEN": "appopen", "aoa": "appopen", "Rewarded": "rewarded", "Rewarded interstitial": "rewardedinterstitial",
         "rewarded_interstitial": "rewardedinterstitial", "(not set)": "notset", "": "notset", "none": "notset",
         "(other)": "fold", "custom_thing": "customthing"}
    assert {k: sb.fmt(k) for k in t} == t
    assert [sb.fgroup(sb.fmt(x)) for x in ("Banner", "custom_thing", "Interstitial", "(not set)", "(other)")] == \
        [0, 0, 1, 2, None]
    assert [sb.kind(c) for c in (MAIN, "", "(not set)", "(other)", ADACT, "x.y.AudienceNetworkActivity")] == \
        ["s", "ns", "ns", "g", "ad", "ad"]


def test_ad_screen_pattern_is_the_probes():
    from admob_iq.fetch import ga4_activity_probe as ap
    assert sb.AD_SCREEN.pattern == ap.AD_SCREEN.pattern and sb.AD_SCREEN.flags == ap.AD_SCREEN.flags


def test_what_each_grain_gives():
    fu = sb.a_day({"st": "w", "g": "fu", "r": [[MAIN, "Banner", "unit_a", 10], [MAIN, "Interstitial", "inter_x", 3],
                                             [MAIN, "(not set)", "(not set)", 2], [EDIT, "Native", "unit_n", 4]]})
    assert fu["cls"] == {MAIN: [10, 3, 2], EDIT: [4, 0, 0]} and fu["tot"] == {MAIN: 15, EDIT: 4}
    assert fu["cu"][(MAIN, "inter_x", "interstitial")] == 3
    f = sb.a_day({"st": "p", "f": 0.01, "g": "f", "r": [[MAIN, "Banner", 10], [MAIN, "App open", 5],
                                                      ["(other)", "Banner", 1]]})
    assert f["cls"] == {MAIN: [10, 5, 0], "(other)": [1, 0, 0]} and f["cu"] is None
    c = sb.a_day({"st": "w", "g": "c", "r": [[MAIN, 15]]})
    assert c["cls"] is None and c["tot"] == {MAIN: 15} and c["cu"] is None      # inline per screen: null that day
    assert sb.a_day({"st": "s", "smp": 0.2}) is None and sb.a_day({"st": "o", "cov": 0.7}) is None
    # a screen row's series: inline needs fu / f; all formats takes every grain
    app = sb.App.__new__(sb.App)
    app.days = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
    app.views = {d: {MAIN: [100, 0]} for d in app.days}
    app.ads = {"2026-10-01": fu, "2026-10-02": f, "2026-10-03": c, "2026-10-04": fu}
    app.whole = {"v": set(app.days), "a": set(app.days[:3]), "w": set(app.days)}   # 4 Oct: GA4 grouped > 2 %
    assert app.screen_series(MAIN, False) == {"2026-10-01": (100, 10), "2026-10-02": (100, 10)}
    assert app.screen_series(MAIN, True) == {"2026-10-01": (100, 15), "2026-10-02": (100, 15), "2026-10-03": (100, 15)}
    # a GA4 grouped day counts for status only while the grouped share is ≤ 2 % (the tie tolerance)
    assert sb._whole({"st": "w", "r": []}) and sb._whole({"st": "p", "f": 0.02, "r": []})
    assert sb._whole({"st": "p", "note": "thr", "r": []})              # thresholded, tie held: no grouped share
    assert not sb._whole({"st": "p", "f": 0.021, "r": []}) and not sb._whole({"st": "o", "cov": 0.9})


# ── duplicates ──────────────────────────────────────────────────────────────────────────────

def dup_day(d, lab, copy, ns_unit="(not set)"):
    """A day with `lab` labelled banner impressions and a `copy` of (not set) format AND unit."""
    return {"t": {"st": "w", "v": [1000, 9000], "a": [["Banner", lab], ["(not set)", copy]], "ev": 9000},
            "v": {"st": "w", "g": "c", "r": [[MAIN, 1000, 9000]]},
            "w": {"st": "w", "g": "u", "r": [["Banner", "unit_a", lab], ["(not set)", ns_unit, copy]]},
            "a": {"st": "w", "g": "fu", "r": [[MAIN, "Banner", "unit_a", lab], [MAIN, "(not set)", ns_unit, copy]]}}


def dup_dash(ratio_fn, latest="2026-11-03", today_imp=None):
    daily = [[d, 0, round(200 / ratio_fn(d)), 400, 350, 0] for d in _days("2026-07-01", "2026-11-03")]
    if today_imp is not None:
        daily.append(["2026-11-04", 0, today_imp, 40, 30, 0])          # the partial IST today
    return {"placements": [{"id": IDS["unit_a"], "name": "unit_a", "app": "App A", "account": "pub-0",
                            "format": "banner", "daily": daily}],
            "apps_catalog": [{"account_id": "pub-0", "app_id": AID, "app_name": "App A"}],
            "latest_complete": latest, "report_tz": "Asia/Calcutta"}


def dup_app(tmp_path, ratio_fn, copy_fn, today_imp=None, latest="2026-11-03"):
    data = tmp_path / "data"
    key = write_store(data, day_fn=lambda d: dup_day(d, 200, copy_fn(d)), first="2026-09-01")
    meta = sb.load_meta(str(data), key)
    return sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW,
                  dup_dash(ratio_fn, latest, today_imp), {})


def test_dup_a_copy_series_short_of_admob_is_still_a_dup_by_pattern(tmp_path):
    rng = random.Random(7)
    lab_ratio = {d: rng.uniform(0.82, 0.84) for d in _days("2026-06-01", "2026-11-05")}       # GA4 labelled ÷ AdMob
    copy = {d: round(200 * rng.uniform(0.86, 1.15)) for d in _days("2026-09-01", "2026-11-04")}
    app = dup_app(tmp_path, lambda d: lab_ratio[d], lambda d: copy[d])
    finals = [d for d in app.final if d >= "2026-09-01"]
    assert len(app.runs) == 1 and app.runs[0]["a"] == "2026-09-01" and app.runs[0]["open"]
    assert not app.runs[0]["ok"]                                       # pooled 0.82–0.84: not confirmed …
    assert all(app.dup[d] == 2 for d in finals)                        # … but every copy day is a dup by pattern
    d = finals[-1]
    assert app.w[d][("(not set)", "notset")] == copy[d]                # unconfirmed: kept as "Format not recorded"
    # a confirmed run (labelled ties AdMob): the copies are removed from w, a and the truth's notset
    app2 = dup_app(tmp_path / "b", lambda d: 1.0, lambda d: copy[d])
    assert app2.runs[0]["ok"] and all(app2.dup[d] == 1 for d in finals)
    assert ("(not set)", "notset") not in app2.w[d] and app2.ads[d]["cls"][MAIN] == [200, 0, 0]
    assert app2.ta[d]["notset"] == 0


def test_dup_runs_start_after_two_and_end_after_two():
    pat = {d: (m, 1.0) for d, m in zip(_days("2026-10-01", "2026-10-12"),
                                        [True, False, True, True, False, True, None, False, False, True, True, True])}
    runs = sb.dup_runs(pat, sorted(pat))
    assert [(r["a"], r["b"], r["open"]) for r in runs] == [("2026-10-03", "2026-10-06", False),
                                                           ("2026-10-10", "2026-10-12", True)]
    assert runs[0]["days"] == ["2026-10-03", "2026-10-04", "2026-10-06"]   # one miss (and an unknown day) do not end it


def test_partial_admob_today_never_flips_the_decision(tmp_path):
    copy = lambda d: 200
    a = dup_app(tmp_path / "a", lambda d: 1.0, copy, today_imp=3, latest="2026-11-03")
    b = dup_app(tmp_path / "b", lambda d: 1.0, copy, today_imp=900000, latest="2026-11-04")
    assert a.dup == b.dup and a.dup["2026-11-04"] == 1 and a.dup["2026-11-03"] == 1      # recent days: the pattern


def test_dup_pattern_needs_ten_percent_and_the_copy_ratio():
    w = {("unit_a", "banner"): 200, ("(not set)", "notset"): 150}
    assert sb.dup_pattern(w, {"banner": 200, "notset": 150}) == (False, 0.75)
    w[("(not set)", "notset")] = 210
    assert sb.dup_pattern(w, {"banner": 200, "notset": 210})[0] is True
    assert sb.dup_pattern({("unit_a", "banner"): 2000, ("(not set)", "notset"): 20}, {"banner": 2000})[0] is False
    assert sb.dup_pattern(None, {"banner": 1}) == (None, None)


# ── the unit join, the blend ────────────────────────────────────────────────────────────────

def test_package_rule_never_takes_a_package_from_by_id():
    by_id = {"ca-app-pub-0000000000000000~31": "", "ca-app-pub-0000000000000000~32": "",
             "ca-app-pub-0000000000000000~33": " ", "ca-app-pub-0000000000000000~34": "x.y.app",
             "ca-app-pub-0000000000000000~35": "x.y.other", AID: ""}
    assert sb.admob_ids({"app_id": AID, "package": "x.y.app"}, by_id) == [AID, "ca-app-pub-0000000000000000~34"]
    assert sb.admob_ids({"app_id": AID, "package": ""}, by_id) == [AID]            # blank: the blank ids never join
    assert sb.admob_ids({"app_id": AID, "package": "  "}, by_id) == [AID]
    assert sb.admob_ids({"app_id": AID}, by_id) == [AID]
    dash = {"apps_catalog": [{"account_id": "p0", "app_id": AID, "app_name": "A"},
                             {"account_id": "p0", "app_id": "ca-app-pub-0000000000000000~31", "app_name": "B"}],
            "placements": [{"id": "u1", "account": "p0", "app": "A"}, {"id": "u2", "account": "p0", "app": "B"},
                           {"id": "u3", "account": "p9", "app": "A"}]}
    assert [p["id"] for p in sb.app_placements(dash, [AID])] == ["u1"] and sb.unmapped_pairs(dash) == 1


def test_units_join_by_name_then_id_and_list_admob_only(tmp_path):
    def day(d):
        r = core_recs(d, {})
        r["w"]["r"] += [["Interstitial", IDS["zz_back_1"], 1], ["Banner", "Unit_N", 0],
                        ["Interstitial", "0123456789abcdef", 2]]
        return r
    data = tmp_path / "data"
    key = write_store(data, day_fn=day, first="2026-10-01")
    meta = sb.load_meta(str(data), key)
    dash = dashboard()
    dash["placements"].append({"id": "ca-app-pub-0000000000000000/9", "name": "unit_spare", "app": "App A",
                               "account": "pub-0", "format": "rewarded", "daily": [["2026-10-01", 0, 5, 9, 8, 0]]})
    app = sb.App(meta, sb.core_days(str(data), key, meta, {}), NOW, dash, {})
    by = {(u[0], u[1]): u for u in app.units}
    assert by[("unit_a", "banner")][2:5] == [[IDS["unit_a"]], "unit_a", "name"]
    assert by[("Unit_N", "banner")][4] == "name"                                      # case-insensitive
    assert by[(IDS["zz_back_1"], "interstitial")][2:6] == [[IDS["zz_back_1"]], "zz_back_1", "id", "Back press"]
    assert by[("0123456789abcdef", "interstitial")][4:6] == ["", "Unknown (unit id)"]
    assert by[("", "rewarded")][2:5] == [["ca-app-pub-0000000000000000/9"], "unit_spare", "admob"]


def test_blend_uses_only_complete_ist_days():
    sh = sb.shares("2026-10-10", "Etc/GMT", "Asia/Calcutta")
    assert set(sh) == {"2026-10-10", "2026-10-11"}
    assert abs(sh["2026-10-10"] - 18.5 / 24) < 1e-12 and abs(sh["2026-10-11"] - 5.5 / 24) < 1e-12
    pl = [{"id": "u1", "account": "p0", "format": "banner",
           "daily": [["2026-10-09", 0, 100, 1000, 500, 0], ["2026-10-10", 0, 100, 1000, 500, 0],
                     ["2026-10-12", 0, 300, 3000, 900, 0]]}]
    adm = sb.Adm(pl, "UTC", "Asia/Calcutta", "2026-10-12")
    assert adm.assumed
    v = adm.blend(["u1"], "2026-10-10")                                # D+1 missing inside the history = 0
    assert [round(x, 4) for x in v] == [round(1000 * 18.5 / 24, 4), round(500 * 18.5 / 24, 4), round(100 * 18.5 / 24, 4)]
    v = adm.blend(["u1"], "2026-10-11")
    assert round(v[2], 6) == round(300 * 5.5 / 24, 6)
    assert adm.blend(["u1"], "2026-10-12") is None and not adm.complete("2026-10-12")   # needs IST 13 Oct
    assert adm.blend(["u1"], "2026-10-08") is None                     # before AdMob's first day
    assert adm.complete("2026-10-11")


# ── trigger labels ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,admob,how,want", [
    ("zz_back_1", "", "name", "Back press"),
    ("aoa_appresume", "", "name", "App resume"),                       # compound token
    ("AppResumeOpen", "", "name", "App resume"),
    ("aoa_background", "", "name", "App resume"),
    ("zz_back_second", "", "name", "Back press"),                    # 'second' beside a trigger: not a trigger
    ("inter_second", "", "name", "Second / session"),
    ("inter_2nd_time", "", "name", "Second / session"),
    ("zz_splash_hi", "", "name", "Splash"),
    ("zz_lang_second", "", "name", "Onboarding"),
    ("inter_edit", "", "name", "Feature: edit"),
    ("inter_editsave", "", "name", "Save / apply"),
    ("zz_exit_main", "", "name", "Back press"),                     # the FIRST keyword by position wins
    ("zz_main_exit", "", "name", "Home"),
    ("notify_inter", "", "name", "Notification"),
    ("inter_with_on_the", "", "name", "Other trigger"),
    ("ca-app-pub-0000000000000000/77", "", "", "Unknown (unit id)"),
    ("0123456789abcdef", "", "", "Unknown (unit id)"),
    ("ca-app-pub-0000000000000000/77", "zz_splash_hi", "id", "Splash"),
    ("(not set)", "", "", "Unit not recorded"),
])
def test_trigger_labels(name, admob, how, want):
    assert sb.trigger_label(name, admob, how) == want


def test_a_suffix_on_half_the_units_is_ignored():
    names = ["inter_game_zz", "qq_main_zz", "native_list_zz", "aoa_resume_zz", "banner_x"]
    suf = sb.suffix_tokens(names)
    assert "zz" in suf and "game" not in suf
    assert sb.trigger_label("inter_zz_game", suffixes=suf) == "Feature: game"
    assert sb.trigger_label("inter_zz_game") == "Feature: zz"
    assert sb.suffix_tokens(["a_zz", "b_zz"]) == frozenset()            # too few units to call a suffix


# ── status ──────────────────────────────────────────────────────────────────────────────────

FT = date(2026, 11, 2)
WD = [(FT - timedelta(days=9 - i)).isoformat() for i in range(10)]
ND = [(FT - timedelta(days=37 - i)).isoformat() for i in range(28)]


def series(rate_n=0.2, rate_w=0.2, v=1000, n_days=None, w_days=None, n_rates=None, w_rates=None):
    s = {}
    for i, d in enumerate(n_days if n_days is not None else ND):
        r = n_rates[i % len(n_rates)] if n_rates else rate_n
        s[d] = (v, round(v * r))
    for i, d in enumerate(w_days if w_days is not None else WD):
        r = w_rates[i] if w_rates else rate_w
        s[d] = (v, round(v * r))
    return s


def test_status_rules_in_order():
    j = lambda s, **k: sb.judge(s, WD, ND, **k)
    st = j(series(w_days=WD[:4]))
    assert (st["word"], st["why"]) == ("N/A", "Not whole — 4 whole days of inline ads in the last 10")
    assert j(series(), guard="Logging changed — format not recorded 40%")["word"] == "N/A"
    assert j(series(rate_n=0, rate_w=0))["why"] == "No inline ads"
    assert j(series(rate_n=0, rate_w=0), full=True)["why"] == "No full-screen ads"
    assert j(series(rate_n=0, rate_w=0.1))["why"].startswith("Ads started")
    st = j(series(n_days=ND[:13]))
    assert (st["word"], st["why"]) == ("Too early", "normal has 13 whole days (needs 14)")
    st = j(series(w_days=WD[:6]))
    assert (st["word"], st["why"]) == ("Too early", "last 10 days have 6 whole days (needs 7)")
    assert j(series(v=10))["why"] == "280 visits in the normal (needs 300)"
    assert j(series(v=20, rate_n=0.1, rate_w=0.1))["why"] == "20 ads expected (needs 30)"
    st = j(series(rate_w=0.12))
    assert (st["word"], st["score"]) == ("Worse", 60) and st["z"] <= -3 and st["h"] == [60, 60]
    assert j(series(rate_w=0.17))["word"] == "Watch"
    assert j(series(rate_w=0.26))["word"] == "Better"
    assert j(series(rate_w=0.195))["word"] == "Normal"


def test_not_whole_counts_the_missing_days_by_their_state():
    # the N/A why counts the W days the series lacks by the state each ships (miss): non-zero parts, in a fixed order
    miss = dict(zip(WD[4:], "-xs-fo")).get
    st = sb.judge(series(w_days=WD[:4]), WD, ND, miss=miss)
    assert (st["word"], st["why"], st["dW"]) == (
        "N/A", "Not whole — 4 whole days of inline ads in the last 10 (GA4 sampled 1 · GA4 dropped rows 1 · not read "
               "yet 2 · format not split 1 · store file unreadable 1)", 4)
    st = sb.judge(series(w_days=WD[:2]), WD, ND, miss=dict(zip(WD[2:], "pppttt--")).get)
    assert st["why"] == ("Not whole — 2 whole days of inline ads in the last 10 (GA4 grouped 3 · thresholding 3 · not "
                         "read yet 2)")
    st = sb.judge(series(w_days=[]), WD, ND, what="interstitial", full=True, miss=lambda d: "s")
    assert st["why"] == "Not whole — 0 whole days of interstitial ads in the last 10 (GA4 sampled 10)"   # sampled only
    st = sb.judge(series(w_days=WD[:5]), WD, ND, miss=lambda d: "s")                # MIN_A_W (5) whole days: next rule
    assert (st["word"], st["why"]) == ("Too early", "last 10 days have 5 whole days (needs 7)")


def test_watch_and_better_need_a_z_of_3():
    # the real-store backtest flagged too many marginal rows: Watch / Better now need |z| ≥ 3 too (Worse unchanged)
    def mk(vw, aw):                              # N: 28 calm days at 20 ads / 100 visits (φ = 1); W: vw visits a day
        s = {d: (1000, 200) for d in ND}
        s.update({d: (vw, a) for d, a in zip(WD, aw)})
        return s
    j = lambda s: (lambda st: (st["score"], st["z"], st["h"], st["word"]))(sb.judge(s, WD, ND))
    assert j(mk(140, [24] * 8 + [23] * 2)) == (85, -2.51, [86, 84], "Normal")     # was Watch (z ≤ −2)
    assert j(mk(230, [40] + [39] * 9)) == (85, -3.22, [85, 85], "Watch")
    assert j(mk(139, [32] * 10)) == (115, 2.52, [115, 115], "Normal")             # was Better (z ≥ 2)
    assert j(mk(230, [53] * 9 + [52])) == (115, 3.22, [115, 115], "Better")
    assert sb.WATCH_Z == 3


def test_z_gate_allows_for_the_rows_own_spread():
    calm = sb.judge(series(rate_w=0.156), WD, ND)
    noisy = sb.judge(series(n_rates=[0.05, 0.35], rate_w=0.156), WD, ND)
    assert calm["word"] == "Worse" and calm["score"] == 78 and calm["phi"] == 1.0
    assert noisy["score"] == 78 and noisy["phi"] > 50 and noisy["z"] > -3 and noisy["word"] == "Normal"


def test_both_halves_must_agree():
    st = sb.judge(series(w_rates=[0.2] * 5 + [0.08] * 5), WD, ND)
    assert st["score"] == 70 and st["z"] < -3 and st["h"] == [100, 40] and st["word"] == "Normal"
    st = sb.judge(series(w_rates=[0.15] * 5 + [0.09] * 5), WD, ND)
    assert st["h"] == [75, 45] and st["word"] == "Worse"


TINY, BIG = "x.y.TinyActivity", "x.y.BigActivity"


def mat_day(d):
    """The fixture day + TinyActivity (600 visits, 4 banner ads a day; 24 in W: a sliver of the app's ads at 6× its
    rate), BigActivity (1,500 visits, 4,000 banner ads a day), EditActivity's native ads gone in W, and two more
    interstitial units on the ad SDK's Activity: zz_splash_1 (1 a day) and inter_bulk (300 a day)."""
    r = core_recs(d, {})
    win = d >= W0
    r["v"]["r"] += [[TINY, 600, 6000], [BIG, 1500, 15000]]
    if win:
        r["a"]["r"] = [x for x in r["a"]["r"] if x[2] != "unit_n"]
        r["w"]["r"] = [x for x in r["w"]["r"] if x[1] != "unit_n"]
        r["t"]["a"] = [x for x in r["t"]["a"] if x[0] != "Native advanced"]
    add = [[TINY, "Banner", "unit_tiny", 24 if win else 4], [BIG, "Banner", "unit_big", 4000],
           [ADACT, "Interstitial", "zz_splash_1", 1], [ADACT, "Interstitial", "inter_bulk", 300]]
    ta = {f: n for f, n in r["t"]["a"]}
    for c, f, u, n in add:
        r["a"]["r"].append([c, f, u, n])
        r["w"]["r"].append([f, u, n])
        ta[f] = ta.get(f, 0) + n
    r["t"]["a"] = [[f, n] for f, n in ta.items()]
    return r


def test_a_row_with_too_few_ads_is_not_judged(tmp_path):
    # owner, 6 Nov: screens holding a sliver of the app's ads showed scores many times 100 — ratios of near-zero rates.
    # A row is judged only while it holds ≥ 1 % of the app's ads of its kind (inline / all-format, a trigger's format)
    # in W or in N, its share taken over its own series days: else N/A "Too few ads"
    data = tmp_path / "data"
    write_store(data, day_fn=mat_day)
    meta = sb.load_meta(str(data), KEY)
    app = sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {})
    rows = {r[2]: r for r in sb.statuses(app)[0]}
    st = rows[TINY][6]
    assert (st["word"], st["why"], st["score"], st["z"]) == ("N/A", "Too few ads — 0.5% of the app's inline ads", None,
                                                              None)
    assert 0.0055 < st["mat"] < 0.006 and (st["AW"], st["AN"]) == (240, 112)      # W 24 / 4,228 a day; N 4 / 4,258
    alone = sb.judge(rows[TINY][5], WD, ND)                                        # the same row without the gate
    assert (alone["word"], alone["score"]) == ("Better", 600)
    st = rows[EDIT][6]                                                             # 1.2 % in N, nothing in W: judged
    assert (st["word"], st["AW"], st["score"]) == ("Worse", 0, 0) and 0.0115 < st["mat"] < 0.012
    assert rows[MAIN][6]["word"] == rows[BIG][6]["word"] == "Normal"
    st = rows["interstitial · Splash"][6]                                          # 1 of 331 interstitials a day
    assert (st["word"], st["why"]) == ("N/A", "Too few ads — 0.3% of the app's interstitial ads")
    assert rows["interstitial · Back press"][6]["word"] == "Normal"                # 30 of 331: 9 %
    assert sb.judge(series(), WD, ND, tot={d: 1000 for d in WD + ND})["mat"] == 0.2   # exactly the row's share
    st = sb.judge(series(), WD, ND, tot={d: 20000 for d in WD + ND})              # 200 of 20,000 a day: 1 % → judged
    assert st["word"] == "Normal" and st["mat"] == 0.01
    # the files: N/A in scr_all's status (Needs attention lists only Worse / Watch: never this row), no report block
    out = tmp_path / "site"
    (data / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    assert sb.run(dashboard(), str(data), str(out), {}, NOW) == ["/scr_*"]
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    st_of = {it[0]: one["status"].get(str(i)) for i, it in enumerate(one["items"])}
    assert st_of[TINY] == ["N/A", "Too few ads — 0.5% of the app's inline ads", None, ""]
    assert st_of["Splash"][:2] == ["N/A", "Too few ads — 0.3% of the app's interstitial ads"]
    assert st_of[EDIT][0] == "Worse" and one["app"][2:] == [1, 0]     # (the app's word: its rows with ≥ 3 % of N ads)
    f2, fl = gz(out / ("scr_%s.json.gz" % KEY)), gz(out / ("scr_l_%s.json.gz" % KEY))
    rid = {c: "s%d" % i for i, (c, k) in enumerate(f2["screens"])}
    assert rid[EDIT] in fl["report"]["rows"] and rid[TINY] not in fl["report"]["rows"]
    assert f2["rows"][rid[TINY]]["cause"] == "" and f2["rows"][rid[TINY]]["st"][2] is None


def test_app_status_is_the_worst_row_with_enough_ads():
    mk = lambda w: {"word": w, "why": w.lower()}
    rows = [(mk("Normal"), "s", 1000), (mk("Worse"), "s", 20), (mk("Watch"), "s", 300), (mk("Better"), "fs", 50)]
    assert sb.app_status(rows) == ["Watch", "1 row Watch", 1, 1]             # the Worse row holds < 3 % of N ads
    assert sb.app_status([(mk("Too early"), "s", 0)])[0] == "Too early"
    assert sb.app_status([])[0] == "N/A"


def test_logging_guard(tmp_path):
    app = app_of(tmp_path, sc={"ns_w": 60})
    assert app.guard() == "Logging changed — screen not recorded 1% → 18%" and app.guard(screen=False) is None
    rows, ast = sb.statuses(app)
    words = {r[2]: r[6]["word"] for r in rows}
    assert words[MAIN] == "N/A" and words["interstitial · Back press"] != "N/A"
    app2 = app_of(tmp_path / "b")
    assert app2.guard() is None


def fold_app(tmp_path, share, fold_days):
    """The fixture app with `share` of MainActivity's ads (and views) moved by GA4 into class "(other)" on fold_days:
    the reads say "p" with their grouped share f, and the tie still holds."""
    def day(d):
        r = core_recs(d, {})
        if d in fold_days:
            for part, ci, ni in (("a", 0, 3), ("v", 0, 1)):
                rows, moved = [], 0
                for x in r[part]["r"]:
                    if x[ci] == MAIN:
                        m = round(x[ni] * share)
                        moved += m
                        x = list(x)
                        x[ni] -= m
                        if part == "v":
                            x[2] = 10 * x[1]
                        rows.append(x)
                        g = list(x)
                        g[ci], g[ni] = "(other)", m
                        if part == "v":
                            g[2] = 10 * m
                        rows.append(g)
                    else:
                        rows.append(x)
                tot = sum(x[ni] for x in rows)
                r[part] = dict(r[part], st="p", f=round(moved / tot, 4), r=rows)
        return r
    data = tmp_path / "data"
    key = write_store(data, day_fn=day)
    meta = sb.load_meta(str(data), key)
    return sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dashboard(), {})


def test_ga4_grouped_days_never_read_as_a_drop(tmp_path):
    # every W day: 30 % of MainActivity folded into "(other)" → those days are not whole for the screen: never "Worse"
    app = fold_app(tmp_path / "a", 0.3, set(WD))
    st = _main_row(app)[6]
    assert (st["word"], st["why"], st["dW"]) == ("N/A", "Not whole — 0 whole days of inline ads in the last 10 (GA4 "
                                                        "grouped 10)", 0)
    assert not set(WD) & set(app.screen_series(MAIN, False))
    # 4 of the 10 W days folded: 6 whole days stay, the grouped class share moved 0 → 8 points → Logging changed
    app = fold_app(tmp_path / "b", 0.3, set(WD[:4]))
    assert app.guard() == "Logging changed — screen grouped by GA4 0% → 8%" and app.guard(screen=False) is None
    st = _main_row(app)[6]
    assert (st["word"], st["why"]) == ("N/A", app.guard()) and st["dW"] == 6
    # a small grouped part (≤ 2 %) is whole enough: the screen is judged as usual
    app = fold_app(tmp_path / "c", 0.01, set(WD))
    assert all(d in app.whole["a"] for d in WD) and app.guard() is None
    st = _main_row(app)[6]
    assert st["word"] == "Normal" and st["dW"] == 10
    # trigger rows: a units read with > 2 % grouped units drops that day from the trigger series
    app = fold_app(tmp_path / "d", 0.0, set())
    gi = next(i for i, t in enumerate(app.trig) if t[1] == "Back press")
    assert WD[0] in app.trig_series(gi)
    app.whole["w"].discard(WD[0])
    assert WD[0] not in app.trig_series(gi)


def test_a_small_grouped_part_ships_as_whole(tmp_path):
    # the shipped day states use the status rule: a "p" with GA4 grouped ≤ FOLD_OK is judged on → "w"; above it "p"
    recs = ({"st": "w"}, {"st": "p", "f": 0.02}, {"st": "p", "note": "thr"}, {"st": "p", "f": 0.021},
            {"st": "p", "f": "?"}, {"st": "o", "cov": 0.9}, {"st": "s"}, {"st": "t"}, {"st": "zz"}, None)
    assert [sb._ch(r) for r in recs] == ["w", "w", "w", "p", "p", "o", "s", "t", "-", "-"]
    assert [sb._whole(r) for r in recs[:5]] == [True, True, True, False, False]
    small, big, rec = "2026-09-10", "2026-09-11", "2026-11-02"           # 1 % / 30 % grouped (final days), 1 % (recent)

    def day(d):
        r = core_recs(d, {})
        r.update(layer_recs(d, {}))
        f = {small: 0.01, big: 0.3, rec: 0.01}.get(d)
        for i in ("v", "a", "cV", "rA", "nA", "k") if f is not None else ():
            r[i] = dict(r[i], st="p", f=f)
        return r
    data, out = tmp_path / "data", tmp_path / "site"
    write_store(data, day_fn=day)
    (data / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    assert sb.run(dashboard(), str(data), str(out), {}, NOW) == ["/scr_*"]
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    days = _days(one["d0"], "2026-11-04")
    for i in ("v", "a", "cV", "rA", "nA", "k"):                        # core, both layer groups, the small group
        assert [one["st"][i][days.index(d)] for d in (small, big, rec)] == ["w", "p", "w"], i
    assert one["st"]["a"].count("p") == 1 and one["st"]["v"].count("p") == 1
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    assert f2["days"][days.index(small)]["st"] == {"t": "w", "v": "w", "w": "w", "a": "w"}
    assert f2["days"][days.index(big)]["st"] == {"t": "w", "v": "p", "w": "w", "a": "p"}
    sh = gz(out / ("scr_c_%s_202609.json.gz" % KEY))
    assert [sh["days"][9]["V"]["st"], sh["days"][10]["V"]["st"]] == ["w", "p"]   # the shards' day parts alike


def test_a_day_ga4_was_never_asked_ships_not_read_yet(tmp_path):
    # the fetch keeps a day it never sent to GA4 (its shape dead, or the volume gate) as a record with "skip" and the st
    # "s" / "o" it stands in with: it ships "-" (not read yet) everywhere, never "GA4 sampled" / "GA4 dropped rows"; a
    # status row's N/A counts its W days by the states shipped (screen rows: visits, then ads by screen; trigger rows:
    # visits, then the units read)
    gate = {"st": "s", "g": "c", "skip": "gate", "tried": [], "fv": 1}
    dead = {"st": "o", "g": "c", "skip": "dead", "tried": ["fu", "f"], "fv": 1}
    assert [sb._ch(r) for r in (gate, dead, dict(dead, st="t"), {"st": "s"})] == ["-", "-", "-", "s"]
    assert sb._ch(dict(gate, st="w", r=[])) == "w"                        # (a usable record keeps its own state)
    a_w = [gate] * 5 + [{"st": "s", "g": "c", "smp": 0.4}] * 2 + [{"st": "o", "g": "c", "cov": 0.9}, dead, "c"]
    lay = "2026-09-15"                                                     # a final day of the layer month files

    def day(d):
        r = core_recs(d, {})
        r.update(layer_recs(d, {}))
        if d in WD:
            x = a_w[WD.index(d)]
            if x == "c":                                                   # whole, but per screen only (no format)
                tot = {}
                for c, f, u, n in r["a"]["r"]:
                    tot[c] = tot.get(c, 0) + n
                x = {"st": "w", "g": "c", "r": [[c, n] for c, n in sorted(tot.items())]}
            r["a"] = dict(x)
            r["w"] = {"st": "s", "g": "u", "smp": 0.5}                      # the units read: GA4 sampled every W day
        if d == lay:
            r["nA"], r["cA"] = dict(gate, g="cf"), dict(dead, g="cf")
        return r
    data, out = tmp_path / "data", tmp_path / "site"
    write_store(data, day_fn=day)
    (data / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    assert sb.run(dashboard(), str(data), str(out), {}, NOW) == ["/scr_*"]
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    days = _days(one["d0"], "2026-11-04")
    assert "".join(one["st"]["a"][days.index(d)] for d in WD) == "-----sso-w"
    assert "".join(one["st"]["w"][days.index(d)] for d in WD) == "s" * 10
    k = days.index(lay)
    assert [one["st"][i][k - 1:k + 2] for i in ("nA", "cA")] == ["w-w", "w-w"]       # the small group, a layer group
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    assert f2["days"][days.index(WD[0])]["st"] == {"t": "w", "v": "w", "w": "s", "a": "-"}         # file 2's day states
    assert gz(out / ("scr_c_%s_202609.json.gz" % KEY))["days"][14]["A"]["st"] == "-"   # the shard's day part
    why = {it[0]: one["status"][str(i)][1] for i, it in enumerate(one["items"]) if str(i) in one["status"]}
    scr = ("Not whole — 0 whole days of inline ads in the last 10 (GA4 sampled 2 · GA4 dropped rows 1 · not read yet 6 "
           "· format not split 1)")
    assert why[MAIN] == why[EDIT] == scr and one["app"] == ["N/A", scr, 0, 0]
    assert why["Back press"] == "Not whole — 0 whole days of interstitial ads in the last 10 (GA4 sampled 10)"
    fl = gz(out / ("scr_l_%s.json.gz" % KEY))
    rep = fl["report"]["app"]
    assert "Status: N/A — %s (0 Worse, 0 Watch)" % scr in rep and "GA4 sampled —" not in rep
    # scr_l's own record of that day ships the same state as scr_all's string (never the "s" it is stored with)
    assert fl["days"][k]["nA"] == {"st": "-", "g": "cf", "skip": "gate", "tried": [], "fv": 1}
    assert fl["days"][k - 1]["nA"]["st"] == "w" and fl["days"][k]["nV"]["st"] == "w"
    # the first read a row cannot use names its day: GA4 grouped visits stop a screen row, not a trigger row
    meta = sb.load_meta(str(data), KEY)
    app = sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {})
    app.st["v"][WD[0]] = "p"
    assert [app.day_why(d, fs) for d in (WD[0], WD[9]) for fs in (False, True)] == ["p", "s", "f", "s"]
    # a core month file that cannot be read: its W days ship "x" and the N/A names them, never "not read yet"
    data, out, dash = build(tmp_path / "x")
    (data / "ga4_screens" / KEY / "core_2026-10.json.gz").write_bytes(b"not gzip")
    sb.run(dash, str(data), str(out), {}, NOW)
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    i = [it[0] for it in one["items"]].index(MAIN)
    assert one["status"][str(i)][:2] == ["N/A", "Not whole — 3 whole days of inline ads in the last 10 (store file "
                                                "unreadable 7)"]


def test_not_whole_leaves_out_the_days_with_nothing_to_read(tmp_path):
    # a W day before the app's first day (the page's coverage starts there too), or before a read's history start once
    # that read's history is done, is no day of the row: never "not read yet"; a split never read under a truth GA4 did
    # not give whole counts under the truth's state (the fetch reads a split only after its truth)
    data = tmp_path / "new" / "data"
    write_store(data, first=WD[6])                                 # a new app: its first day is W's 7th
    meta = sb.load_meta(str(data), KEY)
    app = sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {})
    assert _main_row(app)[6]["why"] == "Not whole — 4 whole days of inline ads in the last 10"
    assert [app.day_why(d, fs) for d in WD[:6] for fs in (False, True)] == [None] * 12

    def day(d):
        r = core_recs(d, {})
        if d < WD[6]:
            del r["a"]                         # ads by screen: no record before W's 7th day (its history: from W's 3rd)
        if d == WD[2]:
            r["t"] = {"st": "s", "smp": 0.4}   # W's 3rd day: the truth sampled, its splits never asked
        return r
    data = tmp_path / "hist" / "data"
    write_store(data, day_fn=day)
    meta = sb.load_meta(str(data), KEY)
    meta["reads"]["a"] = {"oldest": WD[2], "done": True}             # GA4 has nothing for it before W's 3rd day
    app = sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {})
    assert app.d0 == "2026-08-01" and [app.st["t"].get(d) for d in WD[1:4]] == ["w", "s", "w"]
    assert _main_row(app)[6]["why"] == ("Not whole — 4 whole days of inline ads in the last 10 (GA4 sampled 1 · not "
                                        "read yet 3)")
    assert [app.day_why(d) for d in WD[:6]] == [None, None, "s", "-", "-", "-"]
    meta["reads"]["a"]["done"] = False                              # its history still filling: those days are unread
    app = sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {})
    assert _main_row(app)[6]["why"] == ("Not whole — 4 whole days of inline ads in the last 10 (GA4 sampled 1 · not "
                                        "read yet 5)")


def test_a_steady_unconfirmed_copy_is_judged_on_all_formats(tmp_path):
    rng = random.Random(11)
    lab_ratio = {d: rng.uniform(0.82, 0.84) for d in _days("2026-06-01", "2026-11-05")}
    copy = {d: round(200 * rng.uniform(0.95, 1.05)) for d in _days("2026-09-01", "2026-11-04")}
    app = dup_app(tmp_path / "a", lambda d: lab_ratio[d], lambda d: copy[d])
    assert len(app.runs) == 1 and not app.runs[0]["ok"] and app.runs[0]["open"]      # pattern-only, before N
    assert app.allf() == 1 and (app._ns_fmt(WD, dup=True) or 0) > 0.4                 # the copy: ~50 % notset
    assert app.guard() is None and app.guard(screen=False) is None
    st = _main_row(app)[6]
    assert st["word"] in sb.JUDGED and not st["why"].startswith("Logging changed")
    assert sb.statuses(app)[1][0] != "N/A"
    # a copy that STARTS inside N is still the dup-driven N/A
    app = dup_app(tmp_path / "b", lambda d: lab_ratio[d], lambda d: copy[d] if d >= "2026-10-10" else 0)
    assert app.runs[0]["a"] == "2026-10-10"
    assert app.guard() == "Logging changed — duplicate ad_impression logging started 2026-10-10"


def nosplit_day(c_from, fs_to="2026-07-21"):
    """The fixture day + interstitials on MainActivity (5 a day up to fs_to, then 1) — and from c_from on, ads by screen
    whole but per screen only (grain c: GA4 sampled every screen × format split, the screen totals whole)."""
    def day(d):
        r = core_recs(d, {})
        k = 5 if d <= fs_to else 1
        r["a"]["r"].append([MAIN, "Interstitial", "zz_back_1", k])
        r["w"]["r"] = [[f, u, n + (k if u == "zz_back_1" else 0)] for f, u, n in r["w"]["r"]]
        r["t"]["a"] = [[f, n + (k if f == "Interstitial" else 0)] for f, n in r["t"]["a"]]
        if d >= c_from:
            tot = {}
            for c, f, u, n in r["a"]["r"]:
                tot[c] = tot.get(c, 0) + n
            r["a"] = {"st": "w", "g": "c", "r": [[c, n] for c, n in sorted(tot.items())]}
        return r
    return day


def test_no_format_split_from_ga4_judges_screens_on_all_formats(tmp_path):
    # the biggest apps: GA4 gives every screen × format split sampled, the screen totals whole — their days come as
    # grain c only. Over W ∪ N those are more than half the whole ads days → screen rows judged on all formats (allf 2),
    # shipped with the full-screen share on app screens measured on the newest ≤ 60 final days that had the split
    data, out = tmp_path / "data", tmp_path / "site"
    write_store(data, day_fn=nosplit_day("2026-09-20"), first="2026-06-01")
    (data / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    assert sb.run(dashboard(), str(data), str(out), {}, NOW) == ["/scr_*"]
    one, f2 = gz(out / "scr_all.json.gz")["apps"][AID], gz(out / ("scr_%s.json.gz" % KEY))
    fu = _days("2026-06-01", "2026-09-19")[-60:]                   # 22 Jul – 19 Sep: one interstitial a day
    tot = sum(counts(d, {})[1][(MAIN, "Banner", "unit_a")] + counts(d, {})[1][(EDIT, "Native advanced", "unit_n")] + 1
              for d in fu)
    assert fu[0] == "2026-07-22" and (one["allf"], one["allfs"]) == (2, round(60 / tot, 4)) == (2, 0.004)
    assert (f2["notes"]["allf"], f2["notes"]["allfs"]) == (2, one["allfs"])
    # judged on every format, c days included: status, score; the cause still needs the units (fu) — as before
    rid = "s%d" % f2["screens"].index([MAIN, "s"])
    row = f2["rows"][rid]
    assert row["st"][0] == "Normal" and row["st"][1].startswith("ads/100 ") and 90 < row["st"][2] < 110
    assert row["W"][2] == 10 and row["N"][2] == 28 and row["cause"] == "Not measurable (units not split)"
    st = one["status"][str([it[0] for it in one["items"]].index(MAIN))]
    assert st[0] == "Normal" and st[2] == row["st"][2]
    # the period table's numbers on those days: the screen's every format (tot), as on the days with the split
    i, days = [it[0] for it in one["items"]].index(MAIN), _days(one["d0"], "2026-11-04")
    for d in (WD[5], "2026-09-01"):
        assert one["A"][days.index(d)][i] == counts(d, {})[1][(MAIN, "Banner", "unit_a")] + 1, d
    # the rule's edge: more than half of W ∪ N's whole ads days (38 here) without the format — 19 is not, 20 is
    got = {}
    for c_from in ("2026-10-15", "2026-10-14"):
        d2 = tmp_path / c_from / "data"
        write_store(d2, day_fn=nosplit_day(c_from))
        meta = sb.load_meta(str(d2), KEY)
        app = sb.App(meta, sb.core_days(str(d2), KEY, meta, sb.load_recent(str(d2), KEY)), NOW, dashboard(), {})
        got[c_from] = (app.allf(), _main_row(app)[6]["why"])
    assert got["2026-10-15"] == (0, "Not whole — 0 whole days of inline ads in the last 10 (format not split 10)")
    assert got["2026-10-14"][0] == 2 and got["2026-10-14"][1].startswith("ads/100 ")
    # no split day at all: allf 2 with no measured share
    d3 = tmp_path / "all_c" / "data"
    write_store(d3, day_fn=nosplit_day("2026-01-01"))
    meta = sb.load_meta(str(d3), KEY)
    app = sb.App(meta, sb.core_days(str(d3), KEY, meta, sb.load_recent(str(d3), KEY)), NOW, dashboard(), {})
    assert (app.allf(), app.allf_share()) == (2, None)


def test_full_screen_ads_losing_their_format_still_stop_trigger_rows(tmp_path):
    def day(d):                                      # W: the interstitial keeps its unit but loses its format
        r = core_recs(d, {})
        if d >= W0:
            for part in ("a", "w"):
                fi = 1 if part == "a" else 0
                for x in r[part]["r"]:
                    if x[fi] == "Interstitial":
                        x[fi] = "(not set)"
            r["t"]["a"] = [["(not set)" if f == "Interstitial" else f, n] for f, n in r["t"]["a"]]
        return r
    data = tmp_path / "data"
    key = write_store(data, day_fn=day)
    meta = sb.load_meta(str(data), key)
    app = sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dashboard(), {})
    assert not app.runs                                                  # a unit is logged: not the copy pattern
    assert app.guard(screen=False) == "Logging changed — format not recorded 0% → 10%"
    rows, _ = sb.statuses(app)
    st = next(r[6] for r in rows if r[2] == "interstitial · Back press")
    assert (st["word"], st["why"]) == ("N/A", "Logging changed — format not recorded 0% → 10%")


# ── LMDI, cause ─────────────────────────────────────────────────────────────────────────────

def test_lmdi_terms_add_up_to_the_change_exactly():
    rng = random.Random(3)
    for case in range(40):
        units = {}
        for u in range(rng.randint(1, 6)):
            q = {}
            for s in ("W", "N"):
                imp = rng.uniform(100, 5000)
                mt = imp / rng.uniform(0.2, 0.9)
                q[s] = {"G": imp * rng.uniform(0.8, 1.2), "imp": imp, "mt": mt, "req": mt / rng.uniform(0.5, 1.0)}
                q[s]["g"] = q[s]["G"] * rng.uniform(0.05, 1.0)
            if rng.random() < 0.2:
                q["W"] = {"g": 0, "G": 0, "imp": 0, "mt": 0, "req": 0}          # stopped: whole into "units"
            units[u] = dict(q, admob=rng.random() > 0.15)
        vapp = {"W": rng.uniform(1e4, 5e4), "N": rng.uniform(4e4, 2e5)}
        vrow = {"W": vapp["W"] * rng.uniform(0.1, 0.6), "N": vapp["N"] * rng.uniform(0.1, 0.6)}
        terms, dr, rw, rn = sb.lmdi(units, vapp, vrow)
        assert math.isclose(sum(terms.values()), dr, rel_tol=1e-9, abs_tol=1e-12)
        assert math.isclose(dr, rw - rn, rel_tol=1e-12, abs_tol=1e-15)
    one = {0: {"W": {"g": 60, "G": 60, "imp": 60, "mt": 100, "req": 120},
               "N": {"g": 100, "G": 100, "imp": 100, "mt": 100, "req": 120}, "admob": True}}
    terms, dr, rw, rn = sb.lmdi(one, {"W": 1000, "N": 1000}, {"W": 1000, "N": 1000})
    assert math.isclose(terms["show"], dr) and abs(terms["fill"]) < 1e-15
    assert sb.cause_label(terms, rn) == "Lower show rate"
    assert sb.cause_label({"fill": -0.03, "show": -0.025, "req": 0.0}, 0.2) == "Mixed: Lower fill + Lower show rate"
    assert sb.cause_label({"fill": -0.03, "show": -0.01}, 0.2) == "Lower fill"
    assert sb.cause_label({"fill": -0.01}, 0.2) == "No single cause"


def _main_row(app):
    rows, _ = sb.statuses(app)
    return next(r for r in rows if r[2] == MAIN)


def test_show_drop_is_worse_with_its_cause_terms(tmp_path):
    app = app_of(tmp_path, sc={"show_w": 0.6})
    rid, row, label, k, ii, ser, st = _main_row(app)
    assert st["word"] == "Worse" and 55 <= st["score"] <= 65
    cz = sb.cause(app, row, st)
    assert cz["cause"] == "Lower show rate" and cz["terms"]["show"] < -30
    assert math.isclose(sum(cz["abs"].values()), cz["dr"], rel_tol=1e-6, abs_tol=1e-8)
    assert abs(cz["terms"]["fill"]) < 1 and abs(cz["terms"]["tie"]) < 3


def test_unit_stopped_and_changed(tmp_path):
    app = app_of(tmp_path, sc={"swap": True})
    rid, row, label, k, ii, ser, st = _main_row(app)
    assert st["word"] == "Worse"
    cz = sb.cause(app, row, st)
    assert cz["cause"] == "Ad unit changed: unit_a → unit_b"
    assert math.isclose(sum(cz["abs"].values()), cz["dr"], rel_tol=1e-6, abs_tol=1e-8)
    # the same stop without a replacement on the row
    def day(d):
        r = core_recs(d, {})
        if d >= W0:
            for part in ("a", "w"):
                r[part]["r"] = [x for x in r[part]["r"] if "unit_a" not in x]
        return r
    data = tmp_path / "c" / "data"
    key = write_store(data, day_fn=day)
    meta = sb.load_meta(str(data), key)
    dash = dashboard()
    for p in dash["placements"]:
        if p["name"] == "unit_a":
            p["daily"] = [r if r[0] < W0 else [r[0], 0, 0, 0, 0, 0] for r in p["daily"]]
    app = sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dash, {})
    rid, row, label, k, ii, ser, st = _main_row(app)
    cz = sb.cause(app, row, st)
    assert st["word"] == "Worse" and cz["cause"] == "Ad unit stopped: unit_a" and cz["stop_day"] == W0
    txt = sb.row_report(app, label, "screen", st, cz, ser, W0, versions={"1.0": "2026-08-01", "1.1": "2026-10-01",
                                                                          "1.2": "2026-10-30"})
    assert "What to check: Unit unit_a stopped requesting from %s (version 1.1): check it is still created" % W0 in txt


def test_data_quality_items(tmp_path):
    def day(d):
        r = core_recs(d, {})
        r["w"]["r"] += [["Interstitial", sb.TEST_PUB + "/1", 3], ["Banner", "unit_ghost", 5]]
        r["a"]["r"] += [[MAIN, "Interstitial", sb.TEST_PUB + "/1", 3], [NS, "Banner", "unit_ghost", 5]]
        return r
    data = tmp_path / "data"
    key = write_store(data, day_fn=day)
    meta = sb.load_meta(str(data), key)
    dash = dashboard()
    dash["placements"].append({"id": "ca-app-pub-0000000000000000/8", "name": "unit_admob_only", "app": "App A",
                               "account": "pub-0", "format": "banner",
                               "daily": [[d, 0, 500, 900, 800, 0] for d in _days("2026-08-01", "2026-11-04")]})
    app = sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dash, {})
    codes, lines = sb.dq_items(app, {"seen": 30, "n": 0})
    assert codes == ["ns", "unmatched", "test_ids", "admob_only", "no_click"]
    assert any("unit_ghost" in x for x in lines) and any("unit_admob_only" in x and "500" in x for x in lines)
    assert "no_click" not in sb.dq_items(app, {"seen": 30, "n": 4})[0] and "no_click" not in sb.dq_items(app, None)[0]


def test_cause_gates(tmp_path):
    sc = {"show_w": 0.6}
    app = app_of(tmp_path / "a", sc=sc, dash=dashboard(sc, placements=False))
    r = _main_row(app)
    assert sb.cause(app, r[1], r[6])["cause"] == "Not measurable (no AdMob data)"
    app = app_of(tmp_path / "b", sc=sc, dash=dashboard(sc, latest="2026-10-28"))
    r = _main_row(app)
    assert sb.cause(app, r[1], r[6])["cause"] == "Waiting for AdMob data"
    app = app_of(tmp_path / "c", sc=dict(sc, tie=0.5))
    r = _main_row(app)
    assert sb.cause(app, r[1], r[6])["cause"] == "Not measurable (GA4 and AdMob disagree for these units)"
    def fday(d):                                                        # ads by screen at grain f: no units
        r_ = core_recs(d, sc)
        r_["a"] = {"st": "w", "g": "f", "r": [[c, f, n] for c, f, u, n in r_["a"]["r"]]}
        return r_
    data = tmp_path / "d" / "data"
    key = write_store(data, day_fn=fday)
    meta = sb.load_meta(str(data), key)
    app = sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dashboard(sc), {})
    r = _main_row(app)
    assert r[6]["word"] == "Worse" and sb.cause(app, r[1], r[6])["cause"] == "Not measurable (units not split)"


def ghost_app(tmp_path, n_ghost, sc=None):
    """The fixture app with a second banner unit on MainActivity, "unit_ghost", that no AdMob unit matches (name or id)."""
    sc = sc or {}

    def day(d):
        r = core_recs(d, sc)
        r["a"]["r"].append([MAIN, "Banner", "unit_ghost", n_ghost])
        r["w"]["r"].append(["Banner", "unit_ghost", n_ghost])
        r["t"]["a"] = [[f, n + (n_ghost if f == "Banner" else 0)] for f, n in r["t"]["a"]]
        return r
    data = tmp_path / "data"
    key = write_store(data, day_fn=day)
    meta = sb.load_meta(str(data), key)
    return sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dashboard(sc), {})


def test_units_without_an_admob_id_are_their_own_gate(tmp_path):
    # MainActivity's only banner unit has no AdMob unit (its placement is gone): GA4's unit names do not match AdMob —
    # never "GA4 and AdMob disagree" (there is no AdMob number to disagree with)
    sc = {"show_w": 0.6}
    dash = dashboard(sc)
    dash["placements"] = [p for p in dash["placements"] if p["name"] != "unit_a"]
    app = app_of(tmp_path / "a", sc=sc, dash=dash)
    r = _main_row(app)
    cz = sb.cause(app, r[1], r[6])
    assert cz["cause"] == "Not measurable (GA4 unit names don't match AdMob)"
    assert [u[7:] for u in cz["units"]] == [[None, None]]                    # no tie without an AdMob id
    # unmatched + untied units hold over half the row's ads: named by the bigger part
    app = ghost_app(tmp_path / "b", 300, {"tie": 0.5})                       # unmatched 300/day > untied unit_a 200/day
    r = _main_row(app)
    assert sb.cause(app, r[1], r[6])["cause"] == "Not measurable (GA4 unit names don't match AdMob)"
    app = ghost_app(tmp_path / "c", 50, {"tie": 0.5})                        # unmatched 50/day < untied unit_a 200/day
    r = _main_row(app)
    assert sb.cause(app, r[1], r[6])["cause"] == "Not measurable (GA4 and AdMob disagree for these units)"
    # a small unmatched part (≈ 10 % of the row's ads), the ties fine: measured as usual, the unit in its own term
    app = ghost_app(tmp_path / "d", 20, {"show_w": 0.6})
    r = _main_row(app)
    cz = sb.cause(app, r[1], r[6])
    assert r[6]["word"] == "Worse" and cz["cause"] == "Lower show rate" and abs(cz["terms"]["unmatched"]) < 1
    assert math.isclose(sum(cz["abs"].values()), cz["dr"], rel_tol=1e-6, abs_tol=1e-8)


def test_first_bad_day():
    s = series(w_rates=[0.2, 0.2, 0.2, 0.1, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1])
    assert sb.first_bad_day(s, ND + WD, 0.2) == WD[5]
    assert sb.first_bad_day(series(), ND + WD, 0.2) is None


# ── run: files, report, pointer, order, isolation, cache, line ───────────────────────────────

def build(tmp_path, sc=None, dash=None, apps=(AID,), monkeypatch=None):
    data, out = tmp_path / "data", tmp_path / "site"
    out.mkdir(parents=True, exist_ok=True)
    for a in apps:
        write_store(data, a, sc)
    (data / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    d = dash if dash is not None else dashboard(sc)
    return data, out, d


def test_run_files_pointer_report_and_stale_removal(tmp_path):
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    (out / ("scr_c_%s_202001.json.gz" % KEY)).write_bytes(b"old")
    (out / "scr_0123456789ab.json.gz").write_bytes(b"old")
    (out / "script.js").write_bytes(b"keep")
    (out / "screens.css").write_bytes(b"keep")
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/scr_*"]
    names = sorted(f for f in os.listdir(out) if f.startswith("scr"))
    shards = ["scr_%s_%s_%s.json.gz" % (g, KEY, m) for g in "cr" for m in ("202608", "202609", "202610", "202611")]
    assert names == sorted(["script.js", "screens.css", "scr_all.json.gz", "scr_%s.json.gz" % KEY,
                            "scr_l_%s.json.gz" % KEY] + shards)
    assert all(sb.APP_RE.match(n) for n in names if n not in ("script.js", "screens.css"))
    assert not sb.APP_RE.match("script.js") and not sb.APP_RE.match("screens.css")
    p = dash["scr"]
    assert p["file"] == "scr_all.json.gz" and set(p["apps"]) == {AID}
    e = p["apps"][AID]
    raw2 = gzip.decompress((out / ("scr_%s.json.gz" % KEY)).read_bytes())
    rawl = gzip.decompress((out / ("scr_l_%s.json.gz" % KEY)).read_bytes())
    rawa = gzip.decompress((out / "scr_all.json.gz").read_bytes())
    assert (e["key"], e["from"], e["ft"]) == (KEY, "2026-08-01", "2026-11-02")
    assert e["v"] == hashlib.sha1(raw2).hexdigest()[:12] and e["vl"] == hashlib.sha1(rawl).hexdigest()[:12]
    assert p["fv"] == hashlib.sha1(rawa).hexdigest()[:12]
    f2, fl, fa = json.loads(raw2), json.loads(rawl), json.loads(rawa)
    assert (f2["v"], f2["key"], f2["td"], f2["d0"]) == (1, KEY, "2026-11-04", "2026-08-01")
    assert len(f2["days"]) == len(_days("2026-08-01", "2026-11-04")) and len(f2["adm"]["0"]) == len(f2["days"])
    one = fa["apps"][AID]
    assert len(one["vis"]) == len(f2["days"]) and all(len(s) == len(f2["days"]) for s in one["st"].values())
    assert set(one["st"]) == set(sb.READ_IDS) and one["st"]["a"].count("w") == len(f2["days"])
    assert one["items"][:2] == [[EDIT, "s", "in"], [MAIN, "s", "in"]]           # by class name, never by views
    assert ["Back press", "fs", "interstitial"] in one["items"]
    assert one["status"]["1"][0] == "Worse" and one["status"]["1"][3] == "Lower show rate"
    assert one["app"][0] == "Worse" and one["app"][2] == 1
    # the developer report: the key numbers, the acceptance check, no money
    rid = "s%d" % f2["screens"].index([MAIN, "s"])
    txt = fl["report"]["rows"][rid]
    st = f2["rows"][rid]
    assert "Score %d" % 0 not in txt and "(score %d)" % st["st"][2] in txt
    assert "Visits: W %s" % "{:,}".format(st["W"][0]) in txt and "Cause: Lower show rate" in txt
    assert "Acceptance check: After the fix ships: ads per 100 visits on %s ≥ 18.0 for 3 final days." % MAIN in txt
    assert "unit_a (%s) banner · requests/day" % IDS["unit_a"] in txt and "show 0.60 → 0.36" in txt
    assert "First bad day: %s" % W0 in txt and "Ads per 100 visits: W 12.0 · N 20.0" in txt
    assert "What to check: Ads are filled but fewer are shown." in txt and "Version: " in txt
    assert "Countries (top 3 by change): XA" in txt and txt in fl["report"]["app"]
    full = fl["report"]["app"]
    assert "$" not in full and not re.search(r"revenue|earn|ecpm|money|income|usd|₹", full, re.I)
    # layers: versions, month sums, shards
    assert fl["ver_order"] == ["1.0", "1.1"] and fl["ver"]["1.1"]["prev"] == "1.0"
    assert fl["ver"]["1.1"]["same_days"] and set(fl["shards"]["c"]) == {"202608", "202609", "202610", "202611"}
    sh = gz(out / ("scr_c_%s_202609.json.gz" % KEY))
    assert sh["m"] == "2026-09" and sh["dims"] == ["XA", "XB"] and len(sh["days"]) == 30
    assert sh["days"][0]["A"]["g"] == "cf" and sh["items"] == fl["items"]
    assert sh["v"] == 1 and gz(out / ("scr_r_%s_202608.json.gz" % KEY))["v"] == 1     # the file version, not a day part
    assert sh["days"][0]["V"]["st"] == "w" and sh["days"][0]["V"]["r"]
    assert len(fl["days"]) == len(f2["days"]) and fl["days"][-1]["k"]["r"][0][1] == "ad_click"
    # no store: no file, no pointer
    dash2 = {}
    assert sb.run(dash2, str(tmp_path / "none"), str(out), {}, NOW) == [] and "scr" not in dash2
    assert sorted(f for f in os.listdir(out) if f.startswith("scr")) == ["screens.css", "script.js"]
    assert sb.pop_line().startswith("scr: apps 0,")


def test_write_order_and_pointer_last(tmp_path, monkeypatch):
    data, out, dash = build(tmp_path)
    order, real = [], sb._write_gz

    def rec(path, gz):
        if os.path.dirname(path) == str(out):
            order.append((os.path.basename(path), "scr" in dash))
        return real(path, gz)
    monkeypatch.setattr(sb, "_write_gz", rec)
    sb.run(dash, str(data), str(out), {}, NOW)
    names = [n for n, _ in order]
    kinds = [("shard" if re.match(r"scr_[rc]_", n) else "l" if n.startswith("scr_l_") else "all"
              if n == "scr_all.json.gz" else "f2") for n in names]
    assert kinds == ["shard"] * 8 + ["l", "f2", "all"] and not any(p for _, p in order) and "scr" in dash


def test_a_failing_shard_changes_neither_file_2_nor_scr_all(tmp_path, monkeypatch, capsys):
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    sb.run(dash, str(data), str(out), {}, NOW)
    f2 = (out / ("scr_%s.json.gz" % KEY)).read_bytes()
    fa = (out / "scr_all.json.gz").read_bytes()
    real = sb.shard_body

    def boom(app, m, merged):
        if m == "2026-09":
            return 1 / 0
        return real(app, m, merged)
    monkeypatch.setattr(sb, "shard_body", boom)
    for g in "rc":                                   # gone from the site: built again this build (never skipped) — and raises
        (out / ("scr_%s_%s_202609.json.gz" % (g, KEY))).unlink()
    capsys.readouterr()
    dash2 = dashboard({"show_w": 0.6})
    assert sb.run(dash2, str(data), str(out), {}, NOW) == ["/scr_*"]
    assert (out / ("scr_%s.json.gz" % KEY)).read_bytes() == f2 and (out / "scr_all.json.gz").read_bytes() == fa
    fl = gz(out / ("scr_l_%s.json.gz" % KEY))
    assert fl["failed"] == {"r": ["202609"], "c": ["202609"]} and "202609" not in fl["shards"]["c"]
    assert not (out / ("scr_c_%s_202609.json.gz" % KEY)).exists() and (out / ("scr_c_%s_202610.json.gz" % KEY)).exists()
    assert capsys.readouterr().err.count("scr shard skipped: ZeroDivisionError") == 2
    assert dash2["scr"]["apps"][AID]["v"] == dash["scr"]["apps"][AID]["v"]


def test_a_broken_app_loses_only_its_own_files(tmp_path, monkeypatch, capsys):
    data, out, dash = build(tmp_path, apps=(AID, AID2))
    real = sb.build_app

    def boom(meta, *a, **k):
        if meta["app_id"] == AID2:
            raise KeyError("x")
        return real(meta, *a, **k)
    monkeypatch.setattr(sb, "build_app", boom)
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/scr_*"]
    assert set(dash["scr"]["apps"]) == {AID}
    assert not any(gu.file_key(AID2) in f for f in os.listdir(out))
    err = capsys.readouterr().err
    assert "scr app skipped: KeyError" in err and "x" not in err.replace("skipped", "")
    assert ", failed 1," in sb.pop_line()


def test_only_the_apps_the_catalog_selects_are_built(tmp_path):
    # the history job may have read an app the owner does not select: it is in the store, never built (its files from
    # a build when it was selected go with the stale ones); no catalog at all (or an empty one): every store app
    data, out, dash = build(tmp_path, apps=(AID, AID2))
    dash["apps_catalog"][1]["selected"] = False
    (out / ("scr_%s.json.gz" % gu.file_key(AID2))).write_bytes(b"old")
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/scr_*"]
    assert set(dash["scr"]["apps"]) == set(gz(out / "scr_all.json.gz")["apps"]) == {AID}
    assert not any(gu.file_key(AID2) in f for f in os.listdir(out))
    assert re.match(r"^scr: apps 1, .*, failed 0, broken 0, ", sb.pop_line())
    dash = dashboard()
    dash["apps_catalog"] = dash["apps_catalog"][:1]                  # not in the catalog: not selected either
    sb.run(dash, str(data), str(out), {}, NOW)
    assert set(dash["scr"]["apps"]) == {AID}
    for cat in (None, []):
        dash = dict(dashboard(), apps_catalog=cat)
        sb.run(dash, str(data), str(out), {}, NOW)
        assert set(dash["scr"]["apps"]) == {AID, AID2}, cat
    assert sb.selected({"apps_catalog": [{"app_id": AID, "selected": True}, {"app_id": AID2}]}) == {AID}
    assert sb.selected({}) is None and sb.selected({"apps_catalog": []}) is None


def test_the_history_cell_waits_for_the_skip_days_read_again(tmp_path):
    # a read's history is complete when its backfill reached the history start ("done") AND no skip day from before is
    # still being read again ("redo" non-empty: not yet)
    data, out, dash = build(tmp_path)
    p = data / "ga4_screens" / (KEY + ".json.gz")
    meta = gz(p)
    meta["reads"] = {"t": {"oldest": "2026-08-01", "done": True, "redo": []},
                     "a": {"oldest": "2026-08-01", "done": True, "redo": ["2026-09-10"]},
                     "v": {"oldest": "2026-08-01", "done": True}, "w": {"oldest": "2026-08-20", "redo": []}}
    write_json_gz_stable(str(p), meta)
    sb.run(dash, str(data), str(out), {}, NOW)
    assert gz(out / "scr_all.json.gz")["apps"][AID]["bf"] == {"t": ["2026-08-01", True], "a": ["2026-08-01", False],
                                                              "v": ["2026-08-01", True], "w": ["2026-08-20", False]}


def test_too_big_guard(tmp_path, monkeypatch):
    data, out, dash = build(tmp_path)
    monkeypatch.setattr(sb, "MAX_GZ", 10)
    assert sb.run(dash, str(data), str(out), {}, NOW) == [] and "scr" not in dash
    assert not [f for f in os.listdir(out) if f.startswith("scr_")]
    line = sb.pop_line()
    assert ", too big 2," in line and line.startswith("scr: apps 0,")


def test_month_cache_skips_unchanged_months(tmp_path, monkeypatch):
    data, out, dash = build(tmp_path)
    sb.run(dash, str(data), str(out), {}, NOW)
    assert sb.pop_line().endswith("cached 0")
    files = lambda: {f: (out / f).read_bytes() for f in sorted(os.listdir(out))}
    cold = files()
    loaded, real = [], sb._cache_get
    monkeypatch.setattr(sb, "_cache_get", lambda d, k, g, m, src: loaded.append((g, m)) or real(d, k, g, m, src))
    sb.run(dashboard(), str(data), str(out), {}, NOW)
    # 3 store months × versions + countries (served from their summaries, the recent month's rows from the cache)
    # + 3 small-group months (their cached day records)
    assert sb.pop_line().endswith("cached 9")
    assert ("cc", "2026-08") not in loaded and ("ver", "2026-08") not in loaded     # served from its summary
    assert ("cc", "2026-09") not in loaded                     # inside W ∪ N too: no Worse / Watch row needs its rows
    assert {m for g, m in loaded if g == "small"} == {"2026-08", "2026-09", "2026-10"}
    assert files() == cold                                                # the cached build = the cold build
    assert os.path.exists(data / "ga4_screens_cache" / KEY / "cc_2026-09.json.gz")
    assert os.path.exists(data / "ga4_screens_cache" / KEY / "small_2026-09.json.gz")
    p = data / "ga4_screens" / KEY / "cc_2026-09.json.gz"
    body = gz(p)
    body["days"]["2026-09-10"]["cV"]["r"][0][2] += 1
    write_json_gz_stable(str(p), body)
    sb.run(dashboard(), str(data), str(out), {}, NOW)
    assert sb.pop_line().endswith("cached 8")
    # an app with a Worse row: its report needs the window's rows, so the months inside W ∪ N are read (from the cache)
    data2, out2, dash2 = build(tmp_path / "w", {"show_w": 0.6})
    sb.run(dash2, str(data2), str(out2), {}, NOW)
    loaded.clear()
    sb.run(dashboard({"show_w": 0.6}), str(data2), str(out2), {}, NOW)
    assert ("cc", "2026-09") in loaded and ("ver", "2026-09") in loaded and ("cc", "2026-08") not in loaded


def test_the_small_cache_follows_the_screen_indexes(tmp_path):
    data, out, dash = build(tmp_path)
    sb.run(dash, str(data), str(out), {}, NOW)
    cmap = lambda: gz(data / "ga4_screens_cache" / KEY / "small_2026-08.json.gz")["map"]
    before = cmap()
    # a new screen sorting before the app's own: their indexes move — a cached small month must not keep the old ones
    p = data / "ga4_screens" / KEY / "core_2026-09.json.gz"
    body = gz(p)
    body["days"]["2026-09-10"]["v"]["r"].append(["a.a.AaaActivity", 5, 50])
    write_json_gz_stable(str(p), body)
    sb.run(dashboard(), str(data), str(out), {}, NOW)
    warm = {f: (out / f).read_bytes() for f in sorted(os.listdir(out))}
    import shutil
    shutil.rmtree(data / "ga4_screens_cache")
    sb.run(dashboard(), str(data), str(tmp_path / "cold"), {}, NOW)
    cold = {f: (tmp_path / "cold" / f).read_bytes() for f in sorted(os.listdir(tmp_path / "cold"))}
    assert warm == cold and gz(out / ("scr_%s.json.gz" % KEY))["screens"][1] == ["a.a.AaaActivity", "s"]
    assert cmap() == [i + 1 for i in before]                             # encoded again on the new indexes


def test_caches_of_the_previous_version_are_derived_again(tmp_path, monkeypatch):
    # caches written by the code before this CACHE_V (a "skip" record then shipped the "s" / "o" it is stored with, in
    # the layer states, the shards and scr_l's small records): the next build uses none of them — versions, countries
    # and the small group ship "-" (not read yet) on that day — and the caches it writes are served after
    assert sb.CACHE_V >= 4                                  # (3 wrote scr_l's stored "st": a skip day's "s" / "o")
    gate = {"st": "s", "g": "c", "skip": "gate", "tried": [], "fv": 1}
    sk, ids = "2026-09-15", ("rV", "rA", "cV", "cA", "nV", "nA", "k")

    def day(d):
        r = core_recs(d, {})
        r.update(layer_recs(d, {}))
        if d == sk:
            r.update({i: dict(gate, g=r[i]["g"]) for i in ids})
        return r
    data, out = tmp_path / "data", tmp_path / "site"
    write_store(data, day_fn=day)
    (data / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))

    def old_ch(rec):                                               # the state before: the stored st, skip or not
        st = rec.get("st") if isinstance(rec, dict) else None
        return "w" if st == "p" and sb._whole(rec) else st if st in sb.ST_CH else "-"
    with monkeypatch.context() as m:
        m.setattr(sb, "CACHE_V", sb.CACHE_V - 1)
        m.setattr(sb, "_ch", old_ch)
        sb.run(dashboard(), str(data), str(out), {}, NOW)
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    k = _days(one["d0"], "2026-11-04").index(sk)
    assert {one["st"][i][k] for i in ids} == {"s"} and sb.pop_line().endswith("cached 0")   # what those caches hold
    assert len(os.listdir(data / "ga4_screens_cache" / KEY)) > 9

    def shipped():                                                 # scr_all's strings, the shards' day parts, scr_l
        a = gz(out / "scr_all.json.gz")["apps"][AID]
        sh = [gz(out / ("scr_%s_%s_202609.json.gz" % (g, KEY)))["days"][14] for g in "rc"]
        fl = gz(out / ("scr_l_%s.json.gz" % KEY))["days"][k]
        return ({i: a["st"][i][k] for i in ids}, [[x["V"]["st"], x["A"]["st"]] for x in sh],
                {i: fl[i]["st"] for i in ("nV", "nA", "k")})
    sb.run(dashboard(), str(data), str(out), {}, NOW)
    assert sb.pop_line().endswith("cached 0")                       # none of the older caches used
    want = ({i: "-" for i in ids}, [["-", "-"], ["-", "-"]], {"nV": "-", "nA": "-", "k": "-"})
    assert shipped() == want
    files = {f: (out / f).read_bytes() for f in sorted(os.listdir(out))}
    sb.run(dashboard(), str(data), str(out), {}, NOW)
    assert not sb.pop_line().endswith("cached 0") and shipped() == want
    assert {f: (out / f).read_bytes() for f in sorted(os.listdir(out))} == files


def test_an_unchanged_store_builds_and_writes_no_shard(tmp_path, monkeypatch):
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/scr_*"]
    files = lambda d=out: {f: (d / f).read_bytes() for f in sorted(os.listdir(d))}
    cold, ptr = files(), dash["scr"]
    assert os.path.exists(data / "ga4_screens_cache" / KEY / "shards.json")
    assert os.path.exists(data / "ga4_screens_cache" / "all.json")
    built, written = [], []
    real_body, real_write = sb.shard_body, sb._write_gz
    monkeypatch.setattr(sb, "shard_body", lambda app, m, merged: built.append(m) or real_body(app, m, merged))
    monkeypatch.setattr(sb, "_write_gz", lambda p, g: written.append(os.path.basename(p)) or real_write(p, g))
    # the same store again: no shard body built, no file written, every byte the same
    dash2 = dashboard({"show_w": 0.6})
    assert sb.run(dash2, str(data), str(out), {}, NOW) == ["/scr_*"]
    assert built == [] and written == [] and files() == cold and dash2["scr"] == ptr
    # one month of countries changed: only its shard is built; written: that shard + scr_l (its month sums)
    p = data / "ga4_screens" / KEY / "cc_2026-08.json.gz"
    body = gz(p)
    body["days"]["2026-08-10"]["cV"]["r"][0][2] += 7
    write_json_gz_stable(str(p), body)
    sb.run(dashboard({"show_w": 0.6}), str(data), str(out), {}, NOW)
    assert built == ["2026-08"] and sorted(written) == ["scr_c_%s_202608.json.gz" % KEY, "scr_l_%s.json.gz" % KEY]
    after = files()
    assert {f for f in after if after[f] != cold[f]} == set(written) and set(after) == set(cold)
    # a shard missing from the site is built again although its inputs did not change (never skipped when missing)
    built.clear()
    written.clear()
    (out / ("scr_r_%s_202609.json.gz" % KEY)).unlink()
    sb.run(dashboard({"show_w": 0.6}), str(data), str(out), {}, NOW)
    assert built == ["2026-09"] and written == ["scr_r_%s_202609.json.gz" % KEY] and files() == after
    # another site folder with the same cache: everything written there, the same bytes
    out2 = tmp_path / "site2"
    sb.run(dashboard({"show_w": 0.6}), str(data), str(out2), {}, NOW)
    assert files(out2) == after


def test_shard_version_and_an_empty_month(tmp_path):
    app = app_of(tmp_path)
    body = sb.shard_body(app, "2026-09", {})
    assert body["v"] == 1 and len(body["days"]) == 30 and all(x is None for x in body["days"])
    assert body["dims"] == [] and body["items"] == app.ditems
    assert sb.shard_body(app, "2026-12", {})["days"] == []                 # a month after today: no day, no error


def test_layers_keep_no_month_bytes(tmp_path):
    data, out, dash = build(tmp_path)
    meta = sb.load_meta(str(data), KEY)
    recent = sb.load_recent(str(data), KEY)
    app = sb.App(meta, sb.core_days(str(data), KEY, meta, recent), NOW, dash, {})
    cnt = {"cached": 0}
    cc = sb.Layer(app, "cc", str(data), str(out), recent, {}, cnt).run()
    assert cc.src and all(v is None or isinstance(v, str) for v in cc.src.values())   # the sha1 only (None: a month
    assert cc.src["2026-11"] is None and isinstance(cc.src["2026-08"], str)          # of recent days), never bytes
    assert cc.summ == {} and cc.msum()                                     # countries keep only their sums
    ver = sb.Layer(app, "ver", str(data), str(out), recent, {}, cnt).run()
    assert all(v is None or isinstance(v, str) for v in ver.src.values())
    want = ver.versions()
    ver2 = sb.Layer(app, "ver", str(data), str(out), recent, {}, cnt).run()
    import shutil
    shutil.rmtree(data / "ga4_screens_cache")                              # pass 2 must re-read the month files
    for m in ver2.summ:
        ver2.summ[m].pop("same", None)
    assert ver2.versions() == want


def test_two_screens_swapping_rank_leave_old_shards_alone(tmp_path, monkeypatch):
    sc = {"edit_from": "2026-10-10"}           # EditActivity: fewer visits than MainActivity until 10 Oct, then more
    data, out, dash = build(tmp_path, sc)
    now2 = NOW - timedelta(days=20)
    a1 = sb.App(sb.load_meta(str(data), KEY), sb.core_days(str(data), KEY, sb.load_meta(str(data), KEY),
                                                           sb.load_recent(str(data), KEY)), NOW, dash, {})
    a2 = sb.App(sb.load_meta(str(data), KEY), sb.core_days(str(data), KEY, sb.load_meta(str(data), KEY),
                                                           sb.load_recent(str(data), KEY)), now2, dash, {})
    last = lambda a, c: sum(a.views[d][c][0] for d in _days((a.ft - timedelta(days=27)).isoformat(), a.ft.isoformat()))
    assert last(a1, EDIT) > last(a1, MAIN) and last(a2, EDIT) < last(a2, MAIN)   # the rank really swaps
    assert a1.ditems == a2.ditems and a1.top == [EDIT, MAIN]
    sb.run(dash, str(data), str(out), {}, NOW)
    aug = {g: (out / ("scr_%s_%s_202608.json.gz" % (g, KEY))).read_bytes() for g in "rc"}
    summ = {g: (data / "ga4_screens_cache" / KEY / ("%s_2026-08.sum.json.gz" % g)).read_bytes() for g in ("ver", "cc")}
    built, real = [], sb.shard_body
    monkeypatch.setattr(sb, "shard_body", lambda app, m, merged: built.append(m) or real(app, m, merged))
    assert sb.run(dashboard(sc), str(data), str(out), {}, now2) == ["/scr_*"]
    assert "2026-08" not in built                                          # served from its summary
    assert {g: (out / ("scr_%s_%s_202608.json.gz" % (g, KEY))).read_bytes() for g in "rc"} == aug
    assert {g: (data / "ga4_screens_cache" / KEY / ("%s_2026-08.sum.json.gz" % g)).read_bytes()
            for g in ("ver", "cc")} == summ
    assert "2026-11" in built                                              # all its days after today: an empty shard


def test_the_line_is_counts_only(tmp_path):
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    dash["placements"].append({"id": "z", "name": "z", "app": "Unmapped", "account": "pub-9", "daily": []})
    sb.run(dash, str(data), str(out), {}, NOW)
    line = sb.pop_line()
    assert re.match(r"^scr: apps 1, rows \d+, judged \d+, worse 1, watch 0, files 11, too big 0, failed 0, "
                    r"broken 0, unmapped 1, cached 0$", line)
    for bad in (AID, KEY, MAIN, "unit_a", "App A", "skipped:"):
        assert bad not in line


def test_an_unreadable_store_month_file_is_counted_flagged_and_its_days_say_so(tmp_path, monkeypatch, capsys):
    data, out, dash = build(tmp_path)
    base = data / "ga4_screens" / KEY
    (base / "core_2026-09.json.gz").write_bytes(b"not gzip")                         # not gzip
    (base / "cc_2026-08.json.gz").write_bytes(gzip.compress(b"[1, 2]"))              # JSON, not {"days": {…}}
    (base / "small_2026-10.json.gz").write_bytes(gzip.compress(b"{oops"))            # not JSON
    os.remove(base / "ver_2026-08.json.gz")                                         # in the meta's months, gone
    capsys.readouterr()
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/scr_*"] and set(dash["scr"]["apps"]) == {AID}
    line = sb.pop_line()
    assert ", failed 0, broken 4, unmapped 0," in line and "skipped:" not in line
    err = capsys.readouterr().err
    assert err.count("skipped:") == 1 and "scr store skipped: BadGzipFile\n" in err   # ONE health line, the type only
    from admob_iq import health
    monkeypatch.setattr(health, "FAULTS", {})
    for ln in err.splitlines():
        health.scan(ln)
    assert list(health.FAULTS) == ["scr store"]                                     # the red banner names the step
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    days = _days("2026-08-01", "2026-11-04")
    assert one["d0"] == days[0] and all(len(s) == len(days) for s in one["st"].values())
    st = {i: dict(zip(days, s)) for i, s in one["st"].items()}
    lost = {("t", "v", "w", "a"): _days("2026-09-01", "2026-09-30"),
            ("rV", "rA", "cV", "cA"): _days("2026-08-01", "2026-08-31"),
            ("k", "e", "uV", "uA", "s", "x", "nV", "nA"): _days("2026-10-01", "2026-10-30")}   # 31 Oct on: recent days
    for ids, ds in lost.items():
        assert {st[i][d] for i in ids for d in ds} == {"x"}, ids                     # store file unreadable
        assert {st[i][d] for i in ids for d in days if d not in ds} == {"w"}, ids    # every other day: its own state
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    assert f2["days"][days.index("2026-09-10")] == {"st": {"t": "x", "v": "x", "w": "x", "a": "x"}}
    # never cached as an empty month: the next build reads the files again, counts and flags them again
    assert not os.path.exists(data / "ga4_screens_cache" / KEY / "cc_2026-08.json.gz")
    assert not os.path.exists(data / "ga4_screens_cache" / KEY / "cc_2026-08.sum.json.gz")
    assert sb.run(dashboard(), str(data), str(out), {}, NOW) == ["/scr_*"]
    assert ", broken 4, " in sb.pop_line() and capsys.readouterr().err.count("scr store skipped: BadGzipFile") == 1
    assert gz(out / "scr_all.json.gz")["apps"][AID]["st"] == one["st"]
    # a healthy store: no line, "broken 0"
    data2, out2, dash2 = build(tmp_path / "ok")
    sb.run(dash2, str(data2), str(out2), {}, NOW)
    assert ", broken 0, " in sb.pop_line() and "scr store" not in capsys.readouterr().err


def test_an_unreadable_first_month_keeps_its_days_on_the_calendar(tmp_path):
    data, out, dash = build(tmp_path)
    base = data / "ga4_screens"
    (base / KEY / "core_2026-08.json.gz").write_bytes(gzip.compress(b"{oops"))
    meta = gz(base / (KEY + ".json.gz"))
    meta["reads"] = {i: {"oldest": "2026-08-10", "done": True} for i in ("t", "v", "w", "a")}
    write_json_gz_stable(str(base / (KEY + ".json.gz")), meta)
    sb.run(dash, str(data), str(out), {}, NOW)
    assert ", broken 1, " in sb.pop_line()
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    assert one["d0"] == "2026-08-10" and dash["scr"]["apps"][AID]["from"] == "2026-08-10"   # never a shorter history
    assert one["st"]["a"].startswith("x" * 22 + "w") and one["st"]["k"].startswith("w" * 22)  # 10–31 Aug unreadable
    assert one["vis"][:22] == [None] * 22 and one["vis"][22] is not None
    # the span a broken month may have held for a read: final days only, from its oldest filled day
    m = {"reads": {"t": {"oldest": "2026-08-10"}, "v": {"oldest": "bad"}, "w": "?"}}
    td = date(2026, 11, 4)
    assert sb.lost_span(m, "t", "2026-08", td) == ("2026-08-10", "2026-08-31")
    assert sb.lost_span(m, "v", "2026-08", td) == ("2026-08-01", "2026-08-31") == sb.lost_span(m, "w", "2026-08", td)
    assert sb.lost_span(m, "t", "2026-07", td) is None                               # before the read's history
    assert sb.lost_span(m, "a", "2026-10", td) == ("2026-10-01", "2026-10-30")      # month files: ≤ today − 5 only
    assert sb.lost_span(m, "a", "2026-11", td) is None and sb.lost_span(m, "a", "2026-13", td) is None


def test_switch_and_step(tmp_path, monkeypatch, capsys):
    assert sb.enabled({}) and not sb.enabled({"screens_tab": False})
    data, out, dash = build(tmp_path)
    sb.run(dash, str(data), str(out), {}, NOW)
    sb.off(str(out))
    assert not [f for f in os.listdir(out) if f.startswith("scr_")] and sb.pop_line() is None
    from admob_iq import build_static as bs
    monkeypatch.setattr(sb, "run", lambda *a, **k: 1 / 0)
    d = {"scr": {"v": 1}}
    assert bs._screens_step(d, str(data), str(out), {}) == [] and "scr" not in d
    assert "scr skipped: ZeroDivisionError" in capsys.readouterr().err


# ── backtest ────────────────────────────────────────────────────────────────────────────────

def test_backtest_on_a_tiny_store(tmp_path):
    data = tmp_path / "data"
    write_store(data, sc={"show_w": 0.6}, layers=False)
    buf = io.StringIO()
    res = sb.backtest(str(data), dashboard({"show_w": 0.6}), NOW, buf)
    wk = res[KEY]["weeks"]
    assert [w[0] for w in wk] == ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12",
                                  "2026-10-19", "2026-10-26", "2026-11-02"]
    assert wk[-1][1] >= 1 and all(w[1] == 0 for w in wk[:-2]) and 0 < res[KEY]["flip"] < 1
    assert buf.getvalue().startswith("%s  weeks 9  flip " % KEY)
    p = subprocess.run([sys.executable, "-m", "admob_iq.screens_build", "backtest", str(data)], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and p.stdout.startswith(KEY)
    assert subprocess.run([sys.executable, "-m", "admob_iq.screens_build"], cwd=ROOT, capture_output=True,
                          timeout=120).returncode == 2
