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
shipped "-", not read yet — in scr_l too), Ads / user (in file 2, never scr_all: each top screen's users on the FINAL
days the users read and the ads by screen are whole — never Today / Yesterday — a recent users read replacing the month
file's, whole or not; never added across screens, per user per day; the app's daily users from its Uninstall store of
the same stream only, final days only), the counts-only line and the backtest CLI. Status v2 (owner, 6–7 Nov 2026):
impressions per user per day — a screen on its own users, a trigger and the App row on the app's daily users; days by
whole reads (a 0-user day is a whole day), "No visits", impact against the APP's total, the app-wide fold on triggers
only, the collapse rule, the 2-day confirm, the exact parts of the per-user change, the App row's AdMob check (judged on
AdMob when GA4 disagrees), ftU (one end per app), the users by screen read beside small_days, scr_all's "au", v2 files
with shards at v1, the stale users health line and the daily backtest."""
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
                tz="UTC", layers=True, day_fn=None, users=True):
    """A made-up store in the §2.7 layout: final days (≤ today − 5) in month files per group, the rest in recent; the
    layers (a day_fn's own records kept) and, with users, the app's Uninstall store of the same stream (its daily users
    to ft: uni_store)."""
    sc = sc or {}
    key = gu.file_key(aid)
    cut = (now.date() - timedelta(days=4)).isoformat()
    groups = {"core": ("t", "v", "w", "a", "m"), "small": ("k", "e", "uV", "uA", "s", "x", "nV", "nA"),
              "ver": ("rV", "rA"), "cc": ("cV", "cA")}
    files, recent = {}, {}
    if users:
        uni_store(data, aid, first=min(first, "2026-07-25"), last=(now.date() - timedelta(days=2)).isoformat(), tz=tz)
    for d in _days(first, last):
        recs = day_fn(d) if day_fn else core_recs(d, sc)
        if layers and not day_fn:
            recs.update(layer_recs(d, sc))
        elif layers:
            for k, v in layer_recs(d, sc).items():
                recs.setdefault(k, v)
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
    """The fixture's App with its users set as build_app sets them (daily users + users by screen → ftU)."""
    data = tmp_path / "data"
    key = write_store(data, aid, sc, **kw)
    meta = sb.load_meta(str(data), key)
    rec = sb.load_recent(str(data), key)
    return with_users(sb.App(meta, sb.core_days(str(data), key, meta, rec), NOW,
                             dash if dash is not None else dashboard(sc), {}), data)


def with_users(app, data_dir):
    """An App with its users set as build_app sets them: the Uninstall store's daily users + the users by screen."""
    au, auw = sb.app_users(app.meta, str(data_dir))
    sb.set_users(app, au, auw, sb.screen_users(app, str(data_dir), sb.load_recent(str(data_dir), app.key)))
    return app


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
    return with_users(sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW,
                  dup_dash(ratio_fn, latest, today_imp), {}), data)


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
    # … and the App row's ads (app_series) leave it out on such a day (dup 2: the copies are still in the truth the page
    # gets, "dk" 2 tells it the same); a day without copies counts its not recorded
    ser, fm = sb.app_series(app)
    assert app.ta[d]["notset"] == copy[d] and ser[d] == (1000, 200, app.au[d]) and fm[d] == (200, 0, 0)
    app.dup[d] = 0
    assert sb.app_series(app)[0][d][1] == 200 + copy[d] and sb.app_series(app)[1][d] == (200, 0, copy[d])
    app.dup[d] = 2
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
    app = with_users(sb.App(meta, sb.core_days(str(data), key, meta, {}), NOW, dash, {}), data)
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


def useries(rate_n=0.2, rate_w=0.2, u=1000, n_days=None, w_days=None, n_rates=None, w_rates=None, v=None):
    """A per-user series {day: (views, ads, users)}: u users a day (views = 2 × users unless v), ads = rate × users."""
    s = {}
    for i, d in enumerate(n_days if n_days is not None else ND):
        r = n_rates[i % len(n_rates)] if n_rates else rate_n
        s[d] = (v if v is not None else 2 * u, round(u * r), u)
    for i, d in enumerate(w_days if w_days is not None else WD):
        r = w_rates[i] if w_rates else rate_w
        s[d] = (v if v is not None else 2 * u, round(u * r), u)
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
    r["uV"] = {"st": "w", "g": "c", "r": [[MAIN, 300, 200], [EDIT, 150, 100], [TINY, 80, 60], [BIG, 200, 150]]}
    return r


def test_a_row_with_too_few_ads_is_not_judged(tmp_path):
    # owner, 6 Nov: screens holding a sliver of the app's ads showed scores many times 100 — ratios of near-zero rates.
    # A row is judged only while it holds ≥ 1 % of the app's ads of its kind (inline / all-format, a trigger's format)
    # in W or in N, its share taken over its own series days: else N/A "Too few ads"
    data = tmp_path / "data"
    write_store(data, day_fn=mat_day)
    meta = sb.load_meta(str(data), KEY)
    app = with_users(sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {}), data)
    rows = {r[2]: r for r in sb.statuses(app)[0]}
    st = rows[TINY][6]
    assert (st["word"], st["why"], st["score"], st["z"]) == ("N/A", "Too few ads — 0.5% of the app's inline ads", None,
                                                              None)
    assert 0.0055 < st["mat"] < 0.006 and (st["AW"], st["AN"]) == (240, 112)      # W 24 / 4,228 a day; N 4 / 4,258
    alone = sb.judge_u(rows[TINY][5], WD, ND)                                      # the same row without the gate
    assert (alone["word"], alone["score"]) == ("Better", 600)
    st = rows[EDIT][6]                                                             # 1.2 % in N, nothing in W: judged
    assert (st["base"], st["AW"], st["score"]) == ("Worse", 0, 0) and 0.0115 < st["mat"] < 0.012
    # (−1.09 % of the app's imp / user today, −0.98 % the day before — "small" then: its first day as a flag)
    assert (st["word"], st["hold"]) == ("Normal", "confirm") and st["why"].endswith(" · first day — confirms tomorrow")
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
    assert st_of[TINY] == ["N/A", "Too few ads — 0.5% of the app's inline ads", None, "", "", None, 10,    # (+ W days)
                           "N/A", "", []]                                  # not judged: N/A as the absolute word too
    assert st_of["Splash"][:2] == ["N/A", "Too few ads — 0.3% of the app's interstitial ads"]
    assert st_of[EDIT][0] == "Normal" and one["app"][2:4] == [0, 0]               # (Worse / Watch rows of the app)
    f2, fl = gz(out / ("scr_%s.json.gz" % KEY)), gz(out / ("scr_l_%s.json.gz" % KEY))
    rid = {c: "s%d" % i for i, (c, k) in enumerate(f2["screens"])}
    assert rid[TINY] not in fl["report"]["rows"] and f2["rows"][rid[EDIT]]["base"] == ["Worse", "Normal"]
    assert f2["rows"][rid[TINY]]["cause"] == "" and f2["rows"][rid[TINY]]["st"][2] is None


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
    return with_users(sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dashboard(), {}), data)


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
    # (the App row is judged on GA4's truth ÷ the app's daily users: whole, so judged — never a screen row's N/A)
    assert why[MAIN] == why[EDIT] == scr and one["app"][0] == "Normal" and one["app"][2:4] == [0, 0]
    assert why["Back press"] == "Not whole — 0 whole days of interstitial ads in the last 10 (GA4 sampled 10)"
    fl = gz(out / ("scr_l_%s.json.gz" % KEY))
    rep = fl["report"]["app"]
    assert "Status: Normal — imp/user " in rep and "GA4 sampled —" not in rep
    # scr_l's own record of that day ships the same state as scr_all's string (never the "s" it is stored with)
    assert fl["days"][k]["nA"] == {"st": "-", "g": "cf", "skip": "gate", "tried": [], "fv": 1}
    assert fl["days"][k - 1]["nA"]["st"] == "w" and fl["days"][k]["nV"]["st"] == "w"
    # the first read a row cannot use names its day: GA4 grouped visits stop a screen row, not a trigger row
    meta = sb.load_meta(str(data), KEY)
    app = with_users(sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {}), data)
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
    app = with_users(sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {}), data)
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
    app = with_users(sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {}), data)
    assert app.d0 == "2026-08-01" and [app.st["t"].get(d) for d in WD[1:4]] == ["w", "s", "w"]
    assert _main_row(app)[6]["why"] == ("Not whole — 4 whole days of inline ads in the last 10 (GA4 sampled 1 · not "
                                        "read yet 3)")
    assert [app.day_why(d) for d in WD[:6]] == [None, None, "s", "-", "-", "-"]
    meta["reads"]["a"]["done"] = False                              # its history still filling: those days are unread
    app = with_users(sb.App(meta, sb.core_days(str(data), KEY, meta, sb.load_recent(str(data), KEY)), NOW, dashboard(), {}), data)
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
    assert sb.statuses(app)[1]["word"] != "N/A"
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
    assert row["st"][0] == "Normal" and row["st"][1].startswith("imp/screen user ") and 90 < row["st"][2] < 110
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
        app = with_users(sb.App(meta, sb.core_days(str(d2), KEY, meta, sb.load_recent(str(d2), KEY)), NOW, dashboard(), {}), d2)
        got[c_from] = (app.allf(), _main_row(app)[6]["why"])
    assert got["2026-10-15"] == (0, "Not whole — 0 whole days of inline ads in the last 10 (format not split 10)")
    assert got["2026-10-14"][0] == 2 and got["2026-10-14"][1].startswith("imp/screen user ")
    # no split day at all: allf 2 with no measured share
    d3 = tmp_path / "all_c" / "data"
    write_store(d3, day_fn=nosplit_day("2026-01-01"))
    meta = sb.load_meta(str(d3), KEY)
    app = with_users(sb.App(meta, sb.core_days(str(d3), KEY, meta, sb.load_recent(str(d3), KEY)), NOW, dashboard(), {}), d3)
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
    app = with_users(sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dashboard(), {}), data)
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
    app = with_users(sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dash, {}), data)
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
    app = with_users(sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dash, {}), data)
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
    app = with_users(sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dashboard(sc), {}), data)
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
    return with_users(sb.App(meta, sb.core_days(str(data), key, meta, sb.load_recent(str(data), key)), NOW, dashboard(sc), {}), data)


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


def test_first_bad_day_per_user():
    # the daily rate PER USER below 90 % of the normal from that day on (a day without users skipped, never a break)
    s = useries(w_rates=[0.2, 0.2, 0.2, 0.1, 0.2, 0.1, 0.1, 0.1, 0.1, 0.1])
    assert sb.first_bad_day(s, ND + WD, 0.2) == WD[5]
    assert sb.first_bad_day(useries(), ND + WD, 0.2) is None
    s[WD[7]] = (0, 0, 0)
    assert sb.first_bad_day(s, ND + WD, 0.2) == WD[5]
    # users halve on a day, ads halve with them: the rate per user holds, so it is no bad day
    s = useries()
    s.update({d: (500, 100, 500) for d in WD[3:]})
    assert sb.first_bad_day(s, ND + WD, 0.2) is None
    s.update({d: (500, 100, 1000) for d in WD[3:]})                     # the same ads with the users kept: bad
    assert sb.first_bad_day(s, ND + WD, 0.2) == WD[3]


# ── run: files, report, pointer, order, isolation, cache, line ───────────────────────────────

def build(tmp_path, sc=None, dash=None, apps=(AID,), monkeypatch=None, **kw):
    data, out = tmp_path / "data", tmp_path / "site"
    out.mkdir(parents=True, exist_ok=True)
    for a in apps:
        write_store(data, a, sc, **kw)
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
    assert (f2["v"], f2["key"], f2["td"], f2["d0"]) == (4, KEY, "2026-11-04", "2026-08-01")
    assert len(f2["days"]) == len(_days("2026-08-01", "2026-11-04")) and len(f2["adm"]["0"]) == len(f2["days"])
    one = fa["apps"][AID]
    # scr_all: All apps' day arrays + the app's daily users "au" (≤ ftU: the App total and All apps from this file
    # alone), ftU, the copy-day states "dk", the Low screens / triggers "lo" / "lt"; the screens' own users ("U" / "Us")
    # stay file 2's
    assert set(one) == {"key", "ft", "td", "d0", "items", "vis", "V", "A", "ta", "st", "bf", "status", "app", "dq", "au",
                        "ftu", "dk", "nvr", "lo", "lt", "rv", "pt", "sg"} and one["ftu"] == "2026-11-02" \
        and len(one["au"]) == len(one["vis"]) == len(one["rv"])
    assert set(f2) == {"v", "key", "app_id", "ft", "td", "d0", "screens", "units", "trig", "days", "adm", "rows", "notes",
                       "Us", "U", "au", "ufmt", "pw", "pu", "sig", "fs4", "fsd", "adt"} and len(f2["U"]) == len(f2["days"]) \
        and f2["au"] == one["au"] and len(f2["adt"]) == len(f2["days"])
    assert one["dk"] == "0" * len(one["vis"]) and f2["notes"]["ftu"] == "2026-11-02"
    assert len(one["vis"]) == len(f2["days"]) and all(len(s) == len(f2["days"]) for s in one["st"].values())
    assert set(one["st"]) == set(sb.READ_IDS) and one["st"]["a"].count("w") == len(f2["days"])
    assert one["items"][:2] == [[EDIT, "s", "in"], [MAIN, "s", "in"]]           # by class name, never by views
    assert ["Back press", "fs", "interstitial"] in one["items"]
    # status per item: [word, why, score, cause, its Needs attention group, impact (of the app's imp / user), W days
    # (Needs attention's "n/10 days", from scr_all alone)]
    s1 = one["status"]["1"]
    assert s1[:2] == ["Worse", "imp/screen user 1.00 → 0.600 (−40%) · z −18.0"] and s1[2] == 60
    assert s1[3:5] == ["Lower show rate", "Lower show rate"] and -0.27 < s1[5] < -0.26 and s1[6] == 10
    f0 = min(i for i, it in enumerate(one["items"]) if it[1] == "fs")          # the triggers: file 2's rows "t<group>"
    assert all(len(s) == 10 for s in one["status"].values()) and any(int(i) >= f0 for i in one["status"])
    assert all(s[6] == f2["rows"]["t%d" % (int(i) - f0)]["W"][2] for i, s in one["status"].items() if int(i) >= f0)
    # the App row: [word, why, worse n, watch n, score, cause, parts, daily users move, AdMob check]
    a = one["app"]
    assert a[0] == "Worse" and a[1].startswith("imp/user 0.337 → 0.248 (−26%) · z −") and a[2:4] == [1, 0]
    assert a[1].endswith(" · AdMob agrees (inline −31%)") and a[4] == 74 and set(a[6]) == {"avu", "adv"}
    assert abs(a[7]) < 0.01 and a[8]["st"] == "agree" and a[8]["f"] == "inline"
    r2 = f2["rows"]["s%d" % f2["screens"].index([MAIN, "s"])]
    assert r2["U"] == [2000, 5600] and r2["reach"] and r2["base"] == ["Worse", "Worse"] and r2["group"] == "Lower show rate"
    assert r2["W"][2] == s1[6]                                                        # the same W days in both files
    assert set(r2["parts"]) == {"vpu", "tpv", "apm"} and math.isclose(sum(r2["parts"].values()), 100 * 0.6 / 1.0 - 100,
                                                                         abs_tol=0.6)
    # the developer report: the key numbers, the acceptance check, no money
    rid = "s%d" % f2["screens"].index([MAIN, "s"])
    txt = fl["report"]["rows"][rid]
    st = f2["rows"][rid]
    assert "Score %d" % 0 not in txt and "(score %d)" % st["st"][2] in txt
    assert ("Impressions per screen user per day (this screen's ads ÷ this screen's own daily users): W 0.600 · N 1.00"
            in txt) and "Screen users: W 200/day · N 200/day · reach W 22% · N 22%" in txt
    assert "Why it moved (% of normal, adds up to −40." in txt and "ads per minute −40." in txt
    assert "Cause: Lower show rate" in txt
    assert ("Acceptance check: after the fix ships, for 3 final days: impressions per screen user per day on %s ≥ 0.902 "
            "(0.9 × normal) and ads per minute ≥ 1.08 (0.9 × 1.20)" % MAIN) in txt
    assert "unit_a (%s) banner · requests/day" % IDS["unit_a"] in txt and "show 0.60 → 0.36" in txt
    assert "First bad day: %s" % W0 in txt and "Ads per 100 visits: W 12.0 · N 20.0" in txt
    assert "What to check: Ads are filled but fewer are shown." in txt and "Version: " in txt
    assert "Countries (top 3 by change, per 100 visits): XA" in txt and txt in fl["report"]["app"]
    assert "(per 100 visits — GA4 gives no users by version or country here)" in txt
    head = fl["report"]["app"].split("\n\n")[0]
    assert "GA4 data till 2026-11-02 · users till 2026-11-02" in head and "Daily users (GA4 active users" in head
    assert "New vs returning (ads per 100 views): new-user mix" in head and "not the cause" not in head
    assert "Causes: Lower show rate — 1 row (≈ −26% of the app's impressions per user)" in head
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


# ── Ads / user (owner, 6 Nov 2026: "1 user ko kitna impression mila") ───────────────────────────────────────────

RARE = "x.y.RareActivity"                                          # a screen in "All other screens" (5 visits a day)


def users_day(d):
    """The fixture day + a rarely visited screen, and the users by screen (uV): Edit 100 · Main 200 · Rare 3 · not
    recorded 8 · the ad SDK's Activity 40 a day; W's days each carry one case of the whole-days rule."""
    r = core_recs(d, {})
    r.update(layer_recs(d, {}))
    r["v"]["r"].append([RARE, 5, 50])
    r["a"]["r"].append([RARE, "Banner", "unit_a", 3])
    rows = [[ADACT, 60, 40], [NS, 10, 8], [EDIT, 150, 100], [MAIN, 300, 200], [RARE, 4, 3]]
    uv = {"st": "w", "g": "c", "r": rows}
    main = lambda n: [x if x[0] != MAIN else [MAIN, 300, n] for x in rows]
    case = {WD[0]: {"st": "s", "g": "c", "smp": 0.3},                            # GA4 sampled the users read
            WD[1]: {"st": "p", "g": "c", "f": 0.3, "r": main(50)},              # 30 % grouped: not whole
            WD[2]: {"st": "p", "g": "c", "f": 0.01, "r": main(190)},            # 1 % grouped: whole
            WD[3]: {"st": "t", "g": "c", "thr": 1},                             # thresholded
            WD[5]: {"st": "w", "g": "c", "r": [x for x in rows if x[0] != MAIN]},   # whole, no Main row: 0 users
            WD[7]: {"st": "o", "g": "c", "cov": None, "loss": 1},               # a recent day, rows dropped
            WD[8]: {"st": "w", "g": "c", "r": main(210)}}                       # a recent day, whole
    r["uV"] = case.get(d, uv)
    if d == WD[4]:
        r["a"] = dict(r["a"], st="p", f=0.3)            # the ads by screen 30 % grouped: its ads ship, the day is not whole
    if d == VNW:
        r["v"] = dict(r["v"], st="p", f=0.3)            # the screen views 30 % grouped (users read, ads by screen whole)
    return r


VNW = "2026-10-15"                                                   # a final day in N whose views read is not whole


def test_ads_per_user_counts_each_top_screens_users_on_whole_final_days_only(tmp_path):
    data, out = tmp_path / "data", tmp_path / "site"
    write_store(data, day_fn=users_day)
    (data / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    assert sb.run(dashboard(), str(data), str(out), {}, NOW) == ["/scr_*"]
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    days = _days(one["d0"], "2026-11-04")
    items = [it[0] for it in one["items"]]
    # file 2 carries them (only the app page reads them, never All apps): the top screens as its screen indexes ("Us"),
    # per day their users ("U")
    assert items[:3] == [EDIT, MAIN, "Other screens"] and len(f2["U"]) == len(days)
    assert f2["Us"] == [f2["screens"].index([EDIT, "s"]), f2["screens"].index([MAIN, "s"])]
    assert not {"U", "Us"} & set(one) and "au" in one                  # (the screens' users: file 2 only)
    U = {d: f2["U"][days.index(d)] for d in WD}
    # one users number per TOP screen (Edit, Main) a day: Rare (All other screens), not recorded and the ad SDK's
    # Activity never ship — no row gets users added across screens
    assert U[WD[6]] == [100, 200] and U[WD[9]] == [100, 200] and {len(u) for u in f2["U"] if u} == {2}
    # Today / Yesterday never — though their users read and their ads by screen are whole: not final, and the users (a
    # layer read) and the ads (core) of those days are snapshots hours apart
    assert days[-2:] == ["2026-11-03", "2026-11-04"] and f2["U"][-2:] == [None, None]
    fl = gz(out / ("scr_l_%s.json.gz" % KEY))
    assert [fl["days"][-k]["uV"]["st"] for k in (1, 2)] == ["w", "w"] and one["st"]["a"][-2:] == "ww"
    # whole days only: sampled / 30 % grouped / thresholded / rows dropped → none; 1 % grouped is whole; a whole day
    # without the screen's row has 0; ads by screen not whole that day (its ads still in "A") → none
    assert [U[d] for d in WD] == [None, None, [100, 190], None, None, [100, 0], [100, 200], None, [100, 210], [100, 200]]
    assert one["A"][days.index(WD[4])][1] is not None
    # the screen views not whole that day (its users read and its ads by screen whole): none either — the build's own
    # per-user days need all three
    k = days.index(VNW)
    assert (one["st"]["v"][k], one["st"]["a"][k], fl["days"][k]["uV"]["st"]) == ("p", "w", "w")
    assert f2["U"][k] is None and f2["U"][k - 1] == [100, 200]
    # the per user per day math over W: Σ the day's ads ÷ Σ the day's users of that screen, on the days with users
    ads = lambda d: counts(d, {})[1][(MAIN, "Banner", "unit_a")]
    use = [d for d in WD if U[d] is not None]
    got = sum(one["A"][days.index(d)][1] for d in use) / sum(U[d][1] for d in use)
    assert got != pytest.approx(sum(one["A"][days.index(d)][1] / U[d][1] for d in use if U[d][1]) / 4)   # (Σ ÷ Σ: no mean)
    assert use == [WD[2], WD[5], WD[6], WD[8], WD[9]]
    assert got == pytest.approx(sum(ads(d) for d in use) / 800.0) and 1.15 < got < 1.35   # (190 + 0 + 200 + 210 + 200)
    assert got != pytest.approx(sum(one["A"][days.index(d)][1] for d in WD) / 800.0)      # (not every W day's ads)
    # scr_l keeps the users read as it was (its own day states)
    fl = gz(out / ("scr_l_%s.json.gz" % KEY))
    assert [fl["days"][days.index(d)]["uV"]["st"] for d in WD[:4]] == ["s", "p", "w", "t"]
    # the small cache carries the users of its whole days by screen index: a cache from before them (no "sv") is
    # encoded again, never served
    cpath = data / "ga4_screens_cache" / KEY / "small_2026-10.json.gz"
    c = gz(cpath)
    si = c["map"][c["cls"].index(MAIN)]
    assert c["sv"] == sb.SMALL_V and dict(map(tuple, c["u"][WD[2]]))[si] == 190
    assert sorted(c["u"]) == [d for d in _days("2026-10-01", "2026-10-30") if d not in (WD[0], WD[1], WD[3])]
    raw = {f: (out / f).read_bytes() for f in ("scr_all.json.gz", "scr_%s.json.gz" % KEY)}
    write_json_gz_stable(str(cpath), {k: v for k, v in c.items() if k not in ("sv", "u")})
    sb.run(dashboard(), str(data), str(out), {}, NOW)
    assert {f: (out / f).read_bytes() for f in raw} == raw and gz(cpath)["sv"] == sb.SMALL_V
    # an app with no whole users day ships neither "U" nor "Us"
    data2, out2 = tmp_path / "d2", tmp_path / "s2"
    write_store(data2, day_fn=lambda d: dict(users_day(d), uV={"st": "s", "g": "c", "smp": 0.2}))
    (data2 / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    sb.run(dashboard(), str(data2), str(out2), {}, NOW)
    assert not {"U", "Us"} & set(gz(out2 / ("scr_%s.json.gz" % KEY)))


def test_a_recent_users_read_replaces_the_month_files_whole_or_not(tmp_path):
    # the fetch re-reads recent days: a final day in a month file AND in recent takes recent's users read, whole or not —
    # whole in the month file but not in recent: no users that day; the reverse: recent's users
    d1, d2 = "2026-10-20", "2026-10-21"                                            # final days of small_2026-10
    data, out = tmp_path / "data", tmp_path / "site"
    write_store(data, day_fn=lambda d: dict(users_day(d), uV={"st": "s", "g": "c", "smp": 0.4}) if d == d2 else users_day(d))
    (data / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    small = gz(data / "ga4_screens" / KEY / "small_2026-10.json.gz")["days"]
    assert small[d1]["uV"]["st"] == "w" and small[d2]["uV"]["st"] == "s"
    rp = data / "ga4_screens" / KEY / "recent.json.gz"
    rec = gz(rp)
    assert d1 not in rec["days"] and d2 not in rec["days"]
    rec["days"][d1] = {"uV": {"st": "o", "g": "c", "cov": 0.8, "loss": 1}}       # recent: GA4 dropped rows
    rec["days"][d2] = {"uV": {"st": "w", "g": "c", "r": [[ADACT, 60, 40], [NS, 10, 8], [EDIT, 150, 120], [MAIN, 300, 222]]}}
    write_json_gz_stable(str(rp), rec)
    sb.run(dashboard(), str(data), str(out), {}, NOW)
    f2, fl = gz(out / ("scr_%s.json.gz" % KEY)), gz(out / ("scr_l_%s.json.gz" % KEY))
    days = _days(f2["d0"], "2026-11-04")
    assert [f2["U"][days.index(d)] for d in ("2026-10-19", d1, d2)] == [[100, 200], None, [120, 222]]
    assert [fl["days"][days.index(d)]["uV"]["st"] for d in (d1, d2)] == ["o", "w"]       # scr_l: recent's, as shipped


def uni_store(data, aid=AID, last="2026-11-02", first="2026-07-25", tz="UTC", **kw):
    """A made-up Uninstall store (data/ga4_uninstall/<key>.json.gz) of the fixture's stream: daily a1 = 900 + a wiggle
    from `first` up to `last` (its window end), none on 2026-09-15 (a1 0)."""
    daily = {d: {"new": 10, "a1": 0 if d == "2026-09-15" else 900 + 10 * _j(d), "a28": 5000, "un": 3, "un_ev": 3,
                 "upd": 0} for d in _days(first, last)}
    body = {"v": 3, "app_id": aid, "package": "x.y.app", "property_id": "0", "stream_id": "0", "time_zone": tz,
            "daily": daily, "flags": {"truncated": [], "thresholded": False, "incomplete_days": {}}}
    body.update(kw)
    p = os.path.join(str(data), "ga4_uninstall", gu.file_key(aid) + ".json.gz")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    write_json_gz_stable(p, body)
    return daily


def test_the_apps_daily_users_come_from_its_uninstall_store_of_the_same_stream(tmp_path):
    data, out, dash = build(tmp_path)
    daily = uni_store(data, last="2026-11-04")                         # (its Yesterday and Today: never shipped)
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/scr_*"]
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    days = _days(f2["d0"], "2026-11-04")
    want = [daily[d]["a1"] if d in daily and daily[d]["a1"] and d <= "2026-11-02" else None for d in days]
    assert f2["au"] == want and "auw" not in f2 and one["au"] == want and "auw" not in one   # file 2 and scr_all
    assert f2["au"][days.index("2026-09-15")] is None                                   # no users: never 0
    assert f2["au"][-2:] == [None, None] and daily["2026-11-03"]["a1"] > 0 and daily["2026-11-04"]["a1"] > 0   # not final
    # the app's ads per active user per day over W: Σ GA4's labelled ad_impression (inline + full-screen) ÷ Σ its users
    ks = [days.index(d) for d in WD]
    got = sum(one["ta"][k][0] + one["ta"][k][1] for k in ks) / sum(f2["au"][k] for k in ks)
    lab = lambda d: sum(n for (c, f, u), n in counts(d, {})[1].items() if sb.fgroup(sb.fmt(f)) in (0, 1))
    assert got == pytest.approx(sum(lab(d) for d in WD) / sum(daily[d]["a1"] for d in WD))
    meta = sb.load_meta(str(data), KEY)
    au, why = sb.app_users(meta, str(data))
    assert why is None and au == {d: e["a1"] for d, e in daily.items() if e["a1"]}
    # thresholding only withholds rows (a withheld day reads 0: left out), never changes a day's number: kept
    uni_store(data, flags={"truncated": ["cells"], "thresholded": True})
    assert sb.app_users(meta, str(data))[1] is None
    # another stream's users, or its days on another calendar, or another app's file: never used
    for kw in ({"stream_id": "9"}, {"property_id": "9"}, {"time_zone": "Asia/Calcutta"}, {"app_id": AID2}):
        uni_store(data, **kw)
        assert sb.app_users(meta, str(data)) == ({}, "stream"), kw
    uni_store(data, flags={"truncated": ["daily"]})                     # GA4 cut the daily report
    assert sb.app_users(meta, str(data)) == ({}, "cut")
    uni_store(data, daily={d: {"a1": 0} for d in WD})                   # no day with users
    assert sb.app_users(meta, str(data)) == ({}, "none")
    p = data / "ga4_uninstall" / (KEY + ".json.gz")
    p.write_bytes(b"not gzip")
    assert sb.app_users(meta, str(data)) == ({}, "none")
    p.unlink()
    assert sb.app_users(meta, str(data)) == ({}, "none")
    # the tile's why ships instead of the series
    uni_store(data, stream_id="9")
    sb.run(dashboard(), str(data), str(out), {}, NOW)
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    assert "au" not in f2 and f2["auw"] == "stream"


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
    app = with_users(sb.App(meta, sb.core_days(str(data), KEY, meta, recent), NOW, dash, {}), data)
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
    assert re.match(r"^scr: apps 1, users 1, rows \d+, judged \d+, worse 1, watch 0, files 11, too big 0, failed 0, "
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
    assert f2["days"][days.index("2026-09-10")] == {"st": {"t": "x", "v": "x", "w": "x", "a": "x"}}   # (m: never fetched)
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


# ── status v2: impressions per user per day (owner, 6–7 Nov 2026) ───────────────────────────────────────────────

def test_status_v2_rules_in_order():
    # the order: Not whole (the missing W days by part, "u" users not in yet) · the guard · No ads / Ads started · Too
    # few ads · No visits · Too early · the shipped thresholds on the PER-USER score (+ collapse) · the holds
    j = lambda s, **k: sb.judge_u(s, WD, ND, **k)
    st = j(useries(w_days=WD[:4]), miss=lambda d: "u")
    assert (st["word"], st["why"]) == ("N/A", "Not whole — 4 whole days of inline ads in the last 10 (users not in yet 6)")
    assert j(useries(), guard="Logging changed — format not recorded 40%")["why"].startswith("Logging changed")
    assert j(useries(rate_n=0, rate_w=0))["why"] == "No inline ads"
    assert j(useries(rate_n=0, rate_w=0), kind="t", what="interstitial")["why"] == "No full-screen ads"
    assert j(useries(rate_n=0, rate_w=0.1))["why"].startswith("Ads started")
    st = j(useries(n_days=ND[:13]))
    assert (st["word"], st["why"]) == ("Too early", "normal has 13 whole days (needs 14)")
    st = j(useries(w_days=WD[:6]))
    assert (st["word"], st["why"]) == ("Too early", "last 10 days have 6 whole days (needs 7)")
    assert j(useries(u=100, v=10))["why"] == "280 views in the normal (needs 300)"
    assert j(useries(u=10, rate_n=0.1, rate_w=0.1))["why"] == "10 ads expected (needs 30)"
    st = j(useries(rate_w=0.12))
    assert (st["word"], st["score"], st["h"]) == ("Worse", 60, [60, 60]) and st["z"] <= -3
    assert st["why"] == "imp/screen user 0.200 → 0.120 (−40%) · z −17.9"
    assert j(useries(rate_w=0.17))["word"] == "Watch" and j(useries(rate_w=0.26))["word"] == "Better"
    assert j(useries(rate_w=0.195))["word"] == "Normal"
    # collapse: more than half gone, both halves too, z ≤ −2 → Worse though z misses −3 (a stop is never held by z)
    st = j(useries(n_rates=[0.1, 0.5], rate_w=0.12, u=200))
    assert (st["word"], st["score"], st["h"]) == ("Worse", 40, [40, 40]) and -3 < st["z"] <= -2
    assert sb._base_word(53, -2.5, [53, 53]) == "Normal" and sb._base_word(50, -2.0, [60, 60]) == "Worse"
    assert sb._base_word(50, -1.9, [50, 50]) == "Normal" and sb._base_word(50, -2.5, [50, 61]) == "Normal"


def test_zero_user_days_are_whole_days():
    # critic B2: a whole day with 0 users of the screen is (0, 0, 0) — a day for the count, nothing for any sum — so a
    # screen without ads reads "No ads", never "Not whole · users not in yet"; ads in N but no users in W → "No visits"
    z = {d: (0, 0, 0) for d in WD + ND}
    st = sb.judge_u(z, WD, ND)
    assert (st["word"], st["why"], st["dW"], st["dN"]) == ("N/A", "No inline ads", 10, 28)
    s = useries()
    s.update({d: (0, 0, 0) for d in WD})
    st = sb.judge_u(s, WD, ND)
    assert (st["word"], st["why"], st["dW"], st["UW"]) == ("N/A", "No visits in the last 10 days", 10, 0)
    s = useries()
    s.update({d: (0, 0, 0) for d in WD[:4]})                           # 4 days nobody came: the rate of the other 6
    st = sb.judge_u(s, WD, ND)
    assert (st["word"], st["dW"], st["score"], st["UW"]) == ("Normal", 10, 100, 6000)
    # in the build: a whole users read without the screen's row → (0, 0, 0); a day with no whole users read → absent
    app = sb.App.__new__(sb.App)
    app.days = WD[:3]
    app.views = {d: {MAIN: [100, 1000]} for d in app.days}
    fu = sb.a_day({"st": "w", "g": "fu", "r": [[MAIN, "Banner", "u1", 10]]})
    app.ads = {d: fu for d in app.days}
    app.whole = {"v": set(app.days), "a": set(app.days), "w": set(app.days)}
    app.su = {WD[0]: {MAIN: 40}, WD[1]: {EDIT: 5}}
    ser, base = sb.screen_series_u(app, MAIN, False)
    assert ser == {WD[0]: (100, 10, 40), WD[1]: (0, 0, 0)} and set(base) == set(WD[:3])


def test_screen_denominator_is_the_screens_own_users():
    # the screen's ads ÷ the screen's OWN users: half the visitors and half the ads is the same rate (Normal, 100);
    # half the ads with the same visitors is a real drop
    s = useries(u=1000, rate_n=0.2, rate_w=0.2)
    s.update({d: (1000, 100, 500) for d in WD})
    st = sb.judge_u(s, WD, ND)
    assert (st["word"], st["score"], st["UW"], st["AW"]) == ("Normal", 100, 5000, 1000)
    s.update({d: (2000, 100, 1000) for d in WD})
    assert sb.judge_u(s, WD, ND)["word"] == "Worse"


def test_impact_is_against_the_app_total():
    # critic B2: a flag stands only at ≥ 1 % of the APP's total imp / user: impact = (AW − rn·UW) ÷ (app_rn · the app's
    # daily users over the row's W days) — the ads the row lost against its own normal rate, in the app's units
    s = useries(u=1000, rate_n=0.2, rate_w=0.12)                       # −0.08 × 1,000 users × 10 days = −800 ads
    au = {d: 5000 for d in WD + ND}
    st = sb.judge_u(s, WD, ND, app_rn=2.0, au=au)                      # the app: 2 ads per user × 50,000 user-days
    assert st["imp"] == round(-800 / 100000, 5) == -0.008
    assert (st["word"], st["base"], st["hold"]) == ("Normal", "Worse", "small")
    assert st["why"].endswith(" · small — −0.8% of the app's imp / user")
    st = sb.judge_u(s, WD, ND, app_rn=1.0, au=au)                      # the same loss is 1.6 % of a smaller app total
    assert (st["word"], st["imp"]) == ("Worse", -0.016)
    up = useries(u=1000, rate_n=0.2, rate_w=0.26)
    assert sb.judge_u(up, WD, ND, app_rn=2.0, au=au)["hold"] == "small"    # Better too: + under 1 %
    assert sb.judge_u(up, WD, ND, app_rn=0.5, au=au)["word"] == "Better"
    # without the app's normal (no daily users) the hold cannot be weighed: the word stands
    assert sb.judge_u(s, WD, ND, app_rn=None, au=au)["word"] == "Worse"


def test_the_app_wide_fold_is_for_triggers_only():
    # critic B1: a trigger's ads ÷ the app's daily users = app views per user × ads per app view; when users open fewer
    # screens app-wide, its flag goes to the App row ("app-wide"). A screen's own users carry no app-views factor: no fold
    au = {d: 1000 for d in WD + ND}
    vapp = {d: (7000 if d in WD else 10000) for d in WD + ND}          # app views per user −30 %
    s = {d: (vapp[d], vapp[d] // 50, 1000) for d in WD + ND}          # ads per app view flat (0.02)
    st = sb.judge_u(s, WD, ND, kind="t", what="interstitial", app_rn=0.5, au=au, vapp=vapp)
    assert (st["base"], st["word"], st["hold"], st["own"]) == ("Worse", "Normal", "fold", 100)
    assert st["why"].endswith(" · app-wide — users open fewer screens (see App total)")
    s2 = {d: (vapp[d], vapp[d] // 70 if d in WD else vapp[d] // 50, 1000) for d in WD + ND}   # ads per view −29 % too
    st = sb.judge_u(s2, WD, ND, kind="t", what="interstitial", app_rn=0.5, au=au, vapp=vapp)
    assert st["word"] == "Worse" and st["own"] < sb.OWN_FOLD
    scr = {d: (2000, 140 if d in WD else 200, 1000) for d in WD + ND}
    st = sb.judge_u(scr, WD, ND, kind="s", app_rn=0.5, au=au, vapp=vapp)
    assert st["word"] == "Worse" and st["own"] is None and st["hold"] is None


def test_confirm_needs_two_final_days_in_a_row():
    w = {"word": "Worse", "why": "x", "base": "Worse"}
    assert sb._confirm(w, ["Watch"])["word"] == "Worse"                # Worse / Watch are one family
    st = sb._confirm(w, ["Normal"])
    assert (st["word"], st["why"], st["hold"]) == ("Normal", "x · first day — confirms tomorrow", "confirm")
    assert sb._confirm(w, [None])["word"] == "Normal"                  # (no day before: not confirmed)
    assert sb._confirm(dict(w, word="Better"), ["Worse"])["word"] == "Normal"
    assert sb._confirm(dict(w, word="N/A"), ["Normal"])["word"] == "N/A" and sb.CONFIRM_DAYS == 2


def test_parts_add_up_to_the_change_exactly():
    # screen: imp / screen user = views per user × time per view × ads per minute ÷ 60, exact LMDI parts in % of normal
    s = {d: (3000 if d in WD else 4000, 120 if d in WD else 200, 1000) for d in WD + ND}
    eng = {d: (330 if d in WD else 400) * (3000 if d in WD else 4000) for d in WD + ND}   # seconds: 330 / 400 a view
    st = sb.judge_u(s, WD, ND, eng=eng)
    p = st["parts"]
    assert set(p) == {"vpu", "tpv", "apm"} and math.isclose(sum(p.values()), 100 * (st["rw"] / st["rn"] - 1), abs_tol=0.2)
    assert p["vpu"] < 0 and p["tpv"] < 0 and st["G"] == [9900000, 44800000]
    assert sb.cause_u(st, {"cause": "Lower show rate"}) == "Users open it fewer times"   # views / user −25 % leads
    # without engagement time: views per user × ads per view
    st = sb.judge_u(s, WD, ND)
    assert set(st["parts"]) == {"vpu", "adv"} and math.isclose(sum(st["parts"].values()), -40.0, abs_tol=0.2)
    # trigger / App: app views per user × ads per app view
    vapp = {d: 8000 if d in WD else 10000 for d in WD + ND}
    t = {d: (vapp[d], 150 if d in WD else 200, 1000) for d in WD + ND}
    st = sb.judge_u(t, WD, ND, kind="t", what="interstitial", au={d: 1000 for d in t}, vapp=vapp)
    assert set(st["parts"]) == {"avu", "adv"} and math.isclose(sum(st["parts"].values()), -25.0, abs_tol=0.2)
    # the ad-logic part → the AdMob cause; no ads in W → "Ads stopped" (or the stopped unit's own words)
    st = sb.judge_u({d: (4000, 120 if d in WD else 200, 1000) for d in WD + ND}, WD, ND, eng={d: 1600000 for d in eng})
    assert max(st["parts"], key=lambda k: -st["parts"][k]) == "apm"
    assert sb.cause_u(st, {"cause": "Mixed: Fewer ad requests + Lower show rate"}).startswith("Mixed: Fewer ad requests")
    assert sb.cause_group("Mixed: Fewer ad requests + Lower show rate") == "Fewer ad requests"
    assert sb.cause_group("Ad unit stopped: unit_a") == "Ad unit stopped"
    st = sb.judge_u({d: (4000, 0 if d in WD else 200, 1000) for d in WD + ND}, WD, ND)
    assert sb.cause_u(st, {}) == "Ads stopped" and sb.cause_u(st, {"cause": "Ad unit stopped: u"}) == "Ad unit stopped: u"


class _Adm:
    def __bool__(self):
        return True


def _app_ns(**kw):
    """A stand-in App for app_judge: no copy runs, the truth / visits / daily users of the days given."""
    import types
    days = WD + ND
    a = types.SimpleNamespace(runs=[], ta={d: {} for d in days}, vis={d: 20000 for d in days},
                              st={"t": {}}, au={d: 1000 for d in days}, adm=_Adm())
    a.__dict__.update(kw)
    return a


def _aser(gi, gf, gns):
    """The App series from GA4 per user per day per format (W, N): inline, full-screen, not recorded."""
    ser, fm = {}, {}
    for d in WD + ND:
        k = 0 if d in WD else 1
        il, fl, ns = round(1000 * gi[k]), round(1000 * gf[k]), round(1000 * gns[k])
        ser[d], fm[d] = (20000, il + fl + ns, 1000), (il, fl, ns)
    return ser, fm


def test_app_row_admob_word():
    # critic B3: "not recorded" became inline after an update — GA4's total per daily user rose, while AdMob's fell: the
    # App row is judged on AdMob ("Worse (AdMob)"), never a quiet N/A
    ser, fm = _aser((5.0, 1.0), (0.4, 0.4), (0.0, 2.6))                # GA4 4.00 → 5.40 per daily user
    adm = {d: ((1.8 if d in WD else 3.6) * 1000, (0.3 if d in WD else 0.4) * 1000) for d in WD + ND}   # AdMob 4.0 → 2.1
    st = sb.app_judge(_app_ns(), WD, ND, ser, fm, adm)
    assert st["word"] == "Worse" and st["adm"]["st"] == "admob" and st["adm"]["f"] == "inline"
    assert st["why"].startswith("AdMob imp/user 4.00 → 2.10 (−48%) · z ") and st["ga4"]["base"] == "Better"
    assert st["why"].endswith(" · GA4 +35% ≠ AdMob −48% — GA4 logging changed")
    al = sb.app_list(st, [])
    assert al[0] == "Worse" and al[5] == "GA4 logging changed" and al[8]["st"] == "admob"
    # both up → Better stands, "AdMob agrees"
    ser, fm = _aser((8.0, 6.0), (0.3, 0.3), (0.0, 0.0))
    adm = {d: ((6.5 if d in WD else 5.0) * 1000, 300.0) for d in WD + ND}
    st = sb.app_judge(_app_ns(), WD, ND, ser, fm, adm)
    assert (st["word"], st["adm"]["st"]) == ("Better", "agree") and st["why"].endswith(" · AdMob agrees (inline +30%)")
    # GA4 ≠ AdMob, and AdMob too thin to judge (Too early: 10 ads expected) → N/A "Not measurable (GA4 ≠ AdMob)"
    ser, fm = _aser((5.0, 1.0), (0.4, 0.4), (0.0, 2.6))
    adm = {d: (0.5 if d in WD else 1.0, 0.0) for d in WD + ND}
    st = sb.app_judge(_app_ns(), WD, ND, ser, fm, adm)
    assert (st["word"], st["adm"]["st"]) == ("N/A", "na") and st["why"].startswith("Not measurable (GA4 ≠ AdMob) — GA4 +")
    # fewer than 7 / 14 AdMob-complete days: the word stands, "AdMob not checked"
    ser, fm = _aser((0.6, 1.0), (0.3, 0.3), (0.0, 0.0))
    st = sb.app_judge(_app_ns(), WD, ND, ser, fm, {d: (1000.0, 300.0) for d in WD[:6] + ND})
    assert st["word"] == "Worse" and st["adm"]["st"] == "unchecked" and st["why"].endswith(" · AdMob not checked")


def test_app_row_dau_move_and_guard():
    # the App row's why names a daily-users move over 25 %; its guard is a duplicate run only (critic S4)
    ser = {d: (20000, 3000 if d in WD else 1000, 5000 if d in WD else 1000) for d in WD + ND}   # ×5 users, ×0.6 rate
    fm = {d: (ser[d][1], 0, 0) for d in ser}
    au = {d: ser[d][2] for d in ser}
    st = sb.app_judge(_app_ns(au=au), WD, ND, ser, fm, {})
    assert st["word"] == "Worse" and st["dau"] == 4.0 and "imp/user 1.00 → 0.600 (−40%) · z " in st["why"]
    assert " · daily users ×5.0" in st["why"] and st["adm"]["st"] == "unchecked"
    run = {"a": ND[5], "b": WD[2], "open": False, "days": [], "ok": False}
    assert sb.app_judge(_app_ns(au=au, runs=[run]), WD, ND, ser, fm, {})["why"].startswith(
        "Logging changed — duplicate ad_impression logging started")
    early = dict(run, a="2026-08-01", b="2026-08-05")                  # a run outside W ∪ N: no guard
    assert sb.app_judge(_app_ns(au=au, runs=[early]), WD, ND, ser, fm, {})["word"] == "Worse"


def test_nvr_split_is_exact():
    # the App row's users mix, measured: ads per 100 app views split exactly into the new-user share of views (mix) and
    # each group's own ads per view (within) — their sum is the change; views per user is its own (not split) number
    def frag(nv, na):
        return json.dumps({"nV": {"st": "w", "g": "a", "r": [["new", nv[0]], ["returning", nv[1]]]},
                           "nA": {"st": "w", "g": "a", "r": [["new", na[0]], ["returning", na[1]]]}}).encode()
    fr = {d: frag((300, 700), (30, 140)) if d in WD else frag((100, 900), (10, 180)) for d in WD + ND}
    fr[WD[0]] = json.dumps({"nV": {"st": "s"}, "nA": {"st": "w", "r": []}}).encode()     # not whole: left out
    app = sb.App.__new__(sb.App)
    app.vis, app.au, app.ta = {}, {}, {}
    out = sb.nvr_split(app, fr, WD, ND, {})
    assert out["d"] == [9, 28] and out["g"] == {"new": [10.0, 10.0], "returning": [20.0, 20.0]}
    assert math.isclose(out["mix"] + out["within"], out["ch"], abs_tol=0.11) and out["within"] == 0.0
    assert out["ch"] == -10.5 and out["vpu"] is None
    assert sb.nvr_split(app, {}, WD, ND, {}) is None


def test_nvr_views_per_user_on_the_ga4_judges_days_when_judged_on_admob():
    # an App row judged on AdMob carries the AdMob judge's sums (AdMob-complete days only); views per user in the users
    # mix divides the app's views on EVERY W / N day with daily users, so it takes the GA4 judge's users ("ga4") of those
    # same days. AdMob one day behind (none for the last W day): views per user 18 → 20 a day is still −10 %, never the
    # 0 % of ten days' views over nine days' users
    ser, fm = _aser((5.0, 1.0), (0.4, 0.4), (0.0, 2.6))                # GA4 4.00 → 5.40 per daily user
    adm = {d: ((1.8 if d in WD else 3.6) * 1000, (0.3 if d in WD else 0.4) * 1000) for d in WD[:-1] + ND}
    app = _app_ns(vis={d: 18000 if d in WD else 20000 for d in WD + ND})
    st = sb.app_judge(app, WD, ND, ser, fm, adm)
    assert (st["word"], st["adm"]["st"], st["dW"], st["UW"]) == ("Worse", "admob", 9, 9000)
    assert (st["ga4"]["dW"], st["ga4"]["UW"]) == (10, 10000)

    def frag(nv, na):
        return json.dumps({"nV": {"st": "w", "g": "a", "r": [["new", nv[0]], ["returning", nv[1]]]},
                           "nA": {"st": "w", "g": "a", "r": [["new", na[0]], ["returning", na[1]]]}}).encode()
    fr = {d: frag((300, 700), (30, 140)) if d in WD else frag((100, 900), (10, 180)) for d in WD + ND}
    nvr = sb.nvr_split(app, fr, WD, ND, st)
    assert nvr["vpu"] == -10.0
    # the developer report: its users mix labelled — the ads per 100 views come from the GA4 logging that changed
    import types
    al = sb.app_list(st, [])
    head = sb.report_head(types.SimpleNamespace(ft=date(2026, 11, 2), ftu=date(2026, 11, 2)), KEY, al, st, nvr, [])
    line = [x for x in head if "New vs returning" in x]
    assert len(line) == 1 and line[0].startswith("  New vs returning (ads per 100 views; GA4, logging changed): "
                                                 "new-user mix ")
    assert line[0].endswith(" · views per user −10.0% (not split: GA4 gives no new / returning users here)")
    assert head[1].startswith("Status: Worse (AdMob) — AdMob imp/user 4.00 → 2.10 (−48%)")
    # a row judged on GA4 keeps the plain line
    al[8] = dict(al[8], st="agree")
    assert [x for x in sb.report_head(types.SimpleNamespace(ft=date(2026, 11, 2), ftu=date(2026, 11, 2)), KEY, al, st,
                                      nvr, []) if "New vs returning" in x][0].startswith(
        "  New vs returning (ads per 100 views): new-user mix ")


def test_ftu_one_end_per_app(tmp_path):
    # ftU = the last final day with BOTH the app's daily users and a whole screen users read: every window ends there
    data, out, dash = build(tmp_path)
    uni_store(data, last="2026-11-01")                                # the daily users one day short (a morning build)
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/scr_*"]
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    days = _days(one["d0"], "2026-11-04")
    assert (one["ft"], one["ftu"], f2["notes"]["ftu"]) == ("2026-11-02", "2026-11-01", "2026-11-01")
    assert f2["notes"]["w"] == ["2026-10-23", "2026-11-01"] and f2["notes"]["n"][1] == "2026-10-22"
    k = days.index("2026-11-01")
    assert one["au"][k] and one["au"][k + 1:] == [None] * 3 and f2["U"][k] and f2["U"][k + 1:] == [None] * 3
    fl = gz(out / ("scr_l_%s.json.gz" % KEY))
    assert "GA4 data till 2026-11-02 · users till 2026-11-01" in fl["report"]["app"]
    app = app_of(tmp_path / "b")
    assert app.ftu == date(2026, 11, 2) and app.windows()[0][-1] == "2026-11-02" and not sb.stale_users(app)
    su = dict(app.su)
    sb.set_users(app, {d: 900 for d in _days("2026-08-01", "2026-10-30")}, None, su)
    assert app.ftu == date(2026, 10, 30) and sb.stale_users(app)       # 3 days late: the health line
    sb.set_users(app, {}, "stream", su)
    assert app.ftu == date(2026, 11, 2) and app.auw == "stream" and sb.stale_users(app)
    # daily users up to ft but never a whole screen users day: ftU = ft (no lag shows), still the health line
    sb.set_users(app, {d: 900 for d in _days("2026-08-01", "2026-11-02")}, None, {})
    assert app.ftu == date(2026, 11, 2) and app.au and not app.su and sb.stale_users(app)
    app.final = app.final[-2:]                                          # a brand-new app (under 3 final days): not yet
    assert not sb.stale_users(app)


def test_screen_users_match_small_days_users(tmp_path):
    # screen_users reads the users by screen beside small_days, never through it: the same users (by class), from the
    # month cache or the store file, and no class registered (the screen indexes, and the shards, stay as they were)
    data, out, dash = build(tmp_path, day_fn=users_day)
    meta = sb.load_meta(str(data), KEY)
    rec = sb.load_recent(str(data), KEY)
    for cached in (False, True):
        app = sb.App(meta, sb.core_days(str(data), KEY, meta, rec), NOW, dash, {})
        n0 = list(app.screens)
        su = sb.screen_users(app, str(data), rec)
        assert app.screens == n0                                       # nothing registered
        if not cached:
            assert not os.path.exists(data / "ga4_screens_cache" / KEY / "small_2026-10.json.gz")
        users = sb.small_days(app, str(data), rec)[3]
        want = {d: {app.screens[si]: n for si, n in u.items()} for d, u in users.items() if d <= "2026-11-02"}
        assert su == want and su[WD[2]][MAIN] == 190 and MAIN not in su[WD[5]] and WD[0] not in su
        sb.run(dash, str(data), str(out), {}, NOW)                     # (writes the month caches)


def test_aggregates_never_get_users_and_today_yesterday_never_judged(tmp_path):
    data, out, dash = build(tmp_path)
    sb.run(dash, str(data), str(out), {}, NOW)
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    tops = [i for i, it in enumerate(one["items"]) if it[1] == "s"]
    assert [f2["screens"][si][0] for si in f2["Us"]] == [one["items"][i][0] for i in tops] == [EDIT, MAIN]
    assert {len(u) for u in f2["U"] if u} == {2}                      # one users number per TOP screen, never an aggregate
    assert all(one["items"][int(i)][1] in ("s", "fs") for i in one["status"])     # aggregate rows: never a word
    # Today / Yesterday: no daily users, no screen users, no window reaches them
    assert one["au"][-2:] == [None, None] and f2["U"][-2:] == [None, None] and f2["au"][-2:] == [None, None]
    assert f2["notes"]["w"][1] <= one["ftu"] <= one["ft"] < one["td"]


def test_line_users_and_stale_users_warning(tmp_path, monkeypatch, capsys):
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    os.remove(data / "ga4_uninstall" / (KEY + ".json.gz"))            # no daily users at all
    capsys.readouterr()
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/scr_*"]
    assert sb.pop_line().startswith("scr: apps 1, users 0, rows ")
    err = capsys.readouterr().err
    assert err.count("skipped:") == 1 and "scr users skipped: StaleUsersWarning\n" in err
    from admob_iq import health
    monkeypatch.setattr(health, "FAULTS", {})
    for ln in err.splitlines():
        health.scan(ln)
    assert health.FAULTS == {"scr users": "StaleUsersWarning"}
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    assert one["auw"] == "none" and "au" not in one
    assert one["app"][0] == "N/A" and one["app"][1].endswith("(users not in yet 10)")
    trig = [one["status"][str(i)] for i, it in enumerate(one["items"]) if it[1] == "fs"]
    assert trig and all(s[0] == "N/A" and s[1].endswith("(users not in yet 10)") for s in trig)
    # screens keep their own users: still judged
    assert one["status"][str([it[0] for it in one["items"]].index(MAIN))][0] == "Worse"
    # healthy again: no line
    uni_store(data, last="2026-11-02")
    sb.run(dash, str(data), str(out), {}, NOW)
    assert sb.pop_line().startswith("scr: apps 1, users 1, ") and "skipped" not in capsys.readouterr().err
    # daily users in, but the users by screen read never whole (always sampled): every screen row is N/A, so the line
    data2, out2 = tmp_path / "d2", tmp_path / "s2"
    out2.mkdir()
    write_store(data2, day_fn=lambda d: dict(users_day(d), uV={"st": "s", "g": "c", "smp": 0.2}))
    (data2 / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    capsys.readouterr()
    assert sb.run(dash, str(data2), str(out2), {}, NOW) == ["/scr_*"]
    assert sb.pop_line().startswith("scr: apps 1, users 0, ")
    err = capsys.readouterr().err
    assert err.count("skipped:") == 1 and "scr users skipped: StaleUsersWarning\n" in err
    assert "au" in gz(out2 / "scr_all.json.gz")["apps"][AID]          # the daily users themselves are in


def test_v4_files_and_shards_v1(tmp_path):
    data, out, dash = build(tmp_path)
    sb.run(dash, str(data), str(out), {}, NOW)
    assert sb.V == 4 and dash["scr"]["v"] == 4
    assert gz(out / "scr_all.json.gz")["v"] == 4 and gz(out / ("scr_%s.json.gz" % KEY))["v"] == 4
    assert gz(out / ("scr_l_%s.json.gz" % KEY))["v"] == 4
    assert gz(out / ("scr_c_%s_202609.json.gz" % KEY))["v"] == 1 == sb.V_SHARD == sb.SHARD_V    # shards untouched


def test_a_file_version_bump_derives_no_shard(tmp_path, monkeypatch):
    # V is file 2's / scr_l's / scr_all's version only: a bump writes those again, never derives or writes a shard (the
    # shard keys hold KEY_V) — the next build as quick as an unchanged one, every shard's bytes the same
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    sb.run(dash, str(data), str(out), {}, NOW)
    shards = lambda: {f: (out / f).read_bytes() for f in sorted(os.listdir(out)) if re.match(r"scr_[rc]_", f)}
    before = shards()
    assert len(before) > 2
    built, written = [], []
    real_body, real_write = sb.shard_body, sb._write_gz
    monkeypatch.setattr(sb, "shard_body", lambda app, m, merged: built.append(m) or real_body(app, m, merged))
    monkeypatch.setattr(sb, "_write_gz", lambda p, g: written.append(os.path.basename(p)) or real_write(p, g))
    monkeypatch.setattr(sb, "V", sb.V + 1)
    dash2 = dashboard({"show_w": 0.6})
    assert sb.run(dash2, str(data), str(out), {}, NOW) == ["/scr_*"]
    assert built == [] and shards() == before and not [f for f in written if re.match(r"scr_[rc]_", f)]
    assert dash2["scr"]["v"] == sb.V == gz(out / "scr_all.json.gz")["v"] == gz(out / ("scr_%s.json.gz" % KEY))["v"]
    assert gz(out / ("scr_l_%s.json.gz" % KEY))["v"] == sb.V and sorted(written) == sorted(
        ["scr_all.json.gz", "scr_%s.json.gz" % KEY, "scr_l_%s.json.gz" % KEY])


# ── backtest ────────────────────────────────────────────────────────────────────────────────

def test_backtest_v2_tiny_store(tmp_path):
    # every final day with W + N inside the history replayed as "today": the words after the holds and the confirm,
    # per app — counts and 12-hex keys only
    data = tmp_path / "data"
    write_store(data, sc={"show_w": 0.6})
    buf = io.StringIO()
    res = sb.backtest(str(data), dashboard({"show_w": 0.6}), NOW, buf)
    r = res[KEY]
    assert r["days"] == len(_days("2026-09-07", "2026-11-02")) and r["ftu"] == "2026-11-02" and r["users"]
    # the drop starts on W0 (24 Oct): MainActivity turns Worse once both halves of W show it, from its 2nd such day
    # (the confirm) to ft — one episode, the only flagged row
    assert 1 <= r["worse"] < 9 and r["watch"] == 0 and r["confirm"] >= 1 and r["episodes"] == 1
    assert r["median"] == r["worse"] and r["row_months"] == [2, r["row_months"][1]] and r["app"][0] >= 1
    line = buf.getvalue()
    assert line.startswith("%s  days %d  judged " % (KEY, r["days"])) and "MainActivity" not in line
    p = subprocess.run([sys.executable, "-m", "admob_iq.screens_build", "backtest", str(data)], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and p.stdout.startswith(KEY)
    assert subprocess.run([sys.executable, "-m", "admob_iq.screens_build"], cwd=ROOT, capture_output=True,
                          timeout=120).returncode == 2
    # --users: the daily users from a built site's file 2 (the store without its Uninstall store)
    out = tmp_path / "site"
    (data / "app_store_ids.json").write_text(json.dumps({"by_id": {}}))
    sb.run(dashboard({"show_w": 0.6}), str(data), str(out), {}, NOW)
    os.remove(data / "ga4_uninstall" / (KEY + ".json.gz"))
    assert sb.backtest(str(data), dashboard({"show_w": 0.6}), NOW, io.StringIO(), users=str(out))[KEY]["users"]
    assert not sb.backtest(str(data), dashboard({"show_w": 0.6}), NOW, io.StringIO())[KEY]["users"]


# ── absolute numbers: Ads / view, Fill, Show rate, the format benchmark (owner, 7 Nov 2026) ──────────────

def test_absolute_numbers_share_a_unit_by_sigma_and_keep_its_rates(tmp_path):
    # MAIN and the not-recorded class share unit_a (200 + 4 a day): MAIN's AdMob side is σ = Σg ÷ ΣG of the unit's
    # requests / matched / impressions — the rates stay the unit's (fill 0.9, show 0.6 in the fixture)
    app = app_of(tmp_path)
    w = app.windows()[0]
    side = sb.ab_side(app, w, app.allf())
    assert side["sig"] == ["W", 10, w[0], w[-1]] and side["K"] == w
    ua = app.uix[("unit_a", "banner")]
    g = sum(app.ads[d]["cu"][(MAIN, "unit_a", "banner")] for d in w)
    G = sum(app.w[d][("unit_a", "banner")] for d in w)
    assert side["g"][MAIN] == {ua: g} and side["G"][ua] == G and g < G
    ab = sb.ab_row(app, side, MAIN, w, 0)
    X = side["X"][ua]
    assert ab["p"]["banner"] == [1.0, g / G * X[0], g / G * X[1], g / G * X[2]]
    assert abs(ab["fill"] - 0.9) < 1e-3 and abs(ab["show"] - 0.6) < 1e-3 and ab["unm"] == 0 and ab["why"] == ""
    va = [(app.views[d][MAIN][0], app.ads[d]["cls"][MAIN][0]) for d in w]
    assert ab["av"] == 100 * sum(a for _, a in va) / sum(v for v, _ in va) and ab["ads"] == sum(a for _, a in va)
    assert side["ufmt"][ua] == "banner" and all(f is None for u, f in zip(app.units, side["ufmt"]) if not u[2])
    # one vote per unit (its AdMob ids): the W sums over the complete days
    bu = {r[0]: r for r in side["bu"]}
    assert bu[(IDS["unit_a"],)][1:] == ["banner"] + X and bu[(IDS["unit_n"],)][1] == "native"
    # file 2's shape: 4 places for shares / rates, 1 for sums
    sh = sb.ab_ship(ab, side["sig"])
    assert sh["p"]["banner"][0] == 1 and sh["fill"] == round(ab["fill"], 4) and sh["p"]["banner"][1] == round(
        g / G * X[0], 1) and set(sh) == {"av", "fill", "show", "p", "sig", "unm", "why"}


def test_absolute_sigma_falls_back_to_the_newest_split_days_and_unmatched_units_stay_out(tmp_path):
    # W's ads by screen come without the unit (grain c) on 8 of 10 days: σ from the newest 28 split days ≤ W's end;
    # EDIT also shows a unit AdMob does not know (no id): its ads are the unmatched share, never in a rate
    def day_fn(d):
        r = core_recs(d, {})
        r["a"]["r"].append([EDIT, "Native advanced", "zz_house", 50])
        r["w"]["r"].append(["Native advanced", "zz_house", 50])
        if W0 <= d <= "2026-10-31":
            tot = {}
            for c, f, u, n in r["a"]["r"]:
                tot[c] = tot.get(c, 0) + n
            r["a"] = {"st": "w", "g": "c", "r": [[c, n] for c, n in tot.items()]}
        return r
    app = app_of(tmp_path, day_fn=day_fn)
    w = app.windows()[0]
    side = sb.ab_side(app, w, app.allf())
    fu = [d for d in app.days if d <= w[-1] and app.ads[d]["g"] == "fu"]
    assert side["sig"] == ["new", 28, fu[-28], fu[-1]] and fu[-1] == w[-1] and len([d for d in fu if d in w]) == 2
    ab = sb.ab_row(app, side, EDIT, w, app.allf())
    assert set(ab["p"]) == {"native"} and abs(ab["unm"] - 0.5) < 0.05 and abs(ab["p"]["native"][0] - 0.5) < 0.05
    assert abs(ab["fill"] - 0.9) < 0.01 and abs(ab["show"] - 0.6) < 0.01               # (the fixture's rounded AdMob)
    j = sb.ab_judge("Normal", ab, {"fmt": {"native": {"fill": None, "show": [0.7, 0.8, 0.9, 0.95, 20]}}},
                    side["sig"])                                   # (~930 requests in W: under the fill floor)
    assert j[0] == "Low" and j[1].startswith("Show rate 60 % (native median 90 %): ads filled but not shown · ")
    assert j[1].endswith(" · unit mix from %d %s – %d %s" % (
        sb._d(fu[-28]).day, sb.MONTHS[sb._d(fu[-28]).month - 1], sb._d(fu[-1]).day, sb.MONTHS[sb._d(fu[-1]).month - 1]))
    # no AdMob: "—" with the reason, never a 0
    app2 = app_of(tmp_path / "b", dash=dashboard(placements=False))
    s2 = sb.ab_side(app2, w, 0)
    ab2 = sb.ab_row(app2, s2, MAIN, w, 0)
    assert (ab2["fill"], ab2["show"], ab2["why"], ab2["nm"], s2["bu"]) == (None, None, "AdMob data nahi", True, [])
    assert sb.ab_judge("Normal", ab2, {"fmt": {}}, s2["sig"]) == ["Not measurable", "AdMob data nahi", []]


def test_absolute_a_screen_without_ads_in_w_has_no_fill_or_show(tmp_path):
    # EditActivity shows no ads in W (its views go on) and W's ads by screen come without the unit on 8 of 10 days: σ falls
    # back to the newest 28 split days, most of them before W, when EDIT still had its native unit — they never lend it its
    # unit's rates: no Fill / Show rate, no parts, "—" with the reason; the judge's word stays "No ads"
    def day_fn(d):
        r = core_recs(d, {})
        if d >= W0:
            ar = [x for x in r["a"]["r"] if x[0] != EDIT]
            w, t = {}, {}
            for c, f, u, n in ar:
                w[(f, u)] = w.get((f, u), 0) + n
                t[f] = t.get(f, 0) + n
            r["a"]["r"], r["w"]["r"], r["t"]["a"] = ar, [[f, u, n] for (f, u), n in w.items()], [[f, n] for f, n in t.items()]
            if d <= "2026-10-31":
                tot = {}
                for c, f, u, n in ar:
                    tot[c] = tot.get(c, 0) + n
                r["a"] = {"st": "w", "g": "c", "r": [[c, n] for c, n in tot.items()]}
        return r
    app = app_of(tmp_path, day_fn=day_fn)
    w = app.windows()[0]
    side = sb.ab_side(app, w, app.allf())
    assert side["sig"][0] == "new" and side["g"].get(EDIT)              # the older split days carry EDIT's native ads
    ab = sb.ab_row(app, side, EDIT, w, app.allf())
    assert (ab["ads"], ab["av"], ab["fill"], ab["show"], ab["p"], ab["unm"]) == (0, 0, None, None, {}, None)
    assert ab["why"] == "is period me is screen pe koi ad nahi" and ab["views"] > 0
    sh = sb.ab_ship(ab, side["sig"])
    assert (sh["fill"], sh["show"], sh["p"], sh["why"]) == (None, None, {}, "is period me is screen pe koi ad nahi")
    assert sb.ab_judge("Normal", ab, {"fmt": {}}, side["sig"])[0] == "No ads"
    m = sb.ab_row(app, side, MAIN, w, app.allf())                      # a screen with its ads: rated as before
    assert m["ads"] > 0 and abs(m["fill"] - 0.9) < 0.01 and abs(m["show"] - 0.6) < 0.01 and m["why"] == ""


def test_absolute_benchmark_quantiles_one_vote_per_unit_and_none_under_20():
    # banner: 25 units (req ≥ 1000) fill 0.50 … 0.98, one small unit left out of the sample, a unit seen by two apps
    # votes once; native: 19 → no benchmark
    bu = [["b%d" % i, "banner", 2000, 2000 * (0.5 + 0.02 * i), 1000 * (0.5 + 0.02 * i)] for i in range(25)]
    bu += [["small", "banner", 999, 10, 5]] + [["n%d" % i, "native", 5000, 4000, 3000] for i in range(19)]
    rows = {str(i): ("Normal", {"p": {"banner": [0.9, 1, 1, 1], "native": [0.1, 1, 1, 1]}, "av": float(i),
                                "ads": 300}) for i in range(20)}
    rows["x"] = ("N/A", {"p": {"banner": [1, 1, 1, 1]}, "av": 99.0, "ads": 10 ** 6})   # its level votes too
    rows["y"] = ("Normal", {"p": {"banner": [1, 1, 1, 1]}, "av": 50.0, "ads": 299})    # under AB_ADS: no vote
    B = sb.ab_bench({"a": (bu, rows, None), "b": (bu[:3], {}, None), "c": ([], {}, None)})
    fl = sorted(0.5 + 0.02 * i for i in range(25))
    f = B["fmt"]["banner"]["fill"]
    assert f[-1] == 25 and abs(f[1] - fl[6]) < 1e-12 and abs(f[2] - fl[12]) < 1e-12 and abs(f[0] - (fl[2] + 0.4 *
                                                                                                  (fl[3] - fl[2]))) < 1e-12
    assert B["fmt"]["banner"]["nall"] == 26 and B["fmt"]["banner"]["show"][-1] == 25           # matched 10 < 300: out
    assert B["fmt"]["native"] == {"fill": None, "show": None, "av": None, "nall": 19} and B["apps"] == 2
    assert B["fmt"]["banner"]["av"] == pytest.approx([2.0, 5.0, 10.0, 21]) and B["min"] == {"req": 1000, "mt": 300, "ads": 300, "n": 20}
    sh = sb.ab_bench_ship(B)
    assert sh["fmt"]["banner"]["fill"][1] == round(fl[6], 4) and sh["check"]["show"] == sb.CHECK["Lower show rate"]


def test_absolute_status_words_and_cause():
    B = {"fmt": {"native": {"fill": [0.5, 0.72, 0.88, 0.98, 130], "show": [0.14, 0.28, 0.64, 0.79, 153],
                            "av": [3.3, 9.7, 26.6, 45]},
                 "banner": {"fill": [0.55, 0.7, 0.85, 0.94, 167], "show": [0.43, 0.7, 0.8, 0.86, 203], "av": None}}}

    def ab(p, av=20.0, ads=5000, nm=False):
        return {"p": p, "av": av, "ads": ads, "nm": nm, "why": "x" if nm else ""}
    low = ab({"native": [0.997, 10000, 7100, 1640], "banner": [0.003, 10, 9, 8]})
    w, cz, weak = sb.ab_judge("Normal", low, B, ["W", 10, "2026-10-24", "2026-11-02"])
    assert w == "Low" and cz == "Show rate 23 % (native median 64 %): ads filled but not shown; Fill 71 % (native " \
                                "median 88 %): requests not filled"                  # weakest (÷ median) first
    assert weak == [["show", "native", 0.231, 0.64, 0.28], ["fill", "native", 0.71, 0.88, 0.72]]
    assert sb.ab_judge("Normal", ab({"native": [1.0, 10000, 7200, 6000]}), B, None)[0] == "OK"      # = p25: not under
    assert sb.ab_judge("Normal", ab({"banner": [1.0, 10000, 9000, 8000]}), B, None) == ["OK", "", []]
    assert sb.ab_judge("Worse", ab({"banner": [0.15, 100000, 1000, 10], "native": [0.85, 900, 200, 100]}), B,
                       None)[0] == "Too few ads"                  # the weak banner part is under 20 %: not judged
    few = sb.ab_judge("Better", ab({"native": [0.9, 10000, 8000, 6000]}, av=2.4), B, None)
    assert few == ["Few ads", "Ads / view 2 % (native median 27 %): few ads per view", [["av", "native", 2.4, 26.6, 9.7]]]
    assert sb.ab_judge("Normal", ab({"banner": [0.9, 10000, 8000, 6000]}, av=0.1), B, None)[0] == "OK"   # no av bench
    assert sb.ab_judge("Normal", ab({"native": [0.9, 10000, 8000, 6000]}, av=2.4, ads=299), B, None)[0] == "OK"
    assert sb.ab_judge("N/A", low, B, None) == ["N/A", "", []] and sb.ab_judge("Too early", low, B, None)[0] == "Too early"
    assert sb.ab_judge("Normal", ab({}, ads=0), B, None)[0] == "No ads"
    assert sb.ab_judge("Normal", ab({}, nm=True), B, None) == ["Not measurable", "x", []]
    # a req floor: 999 requests at fill 10 % are not judged on fill
    assert sb.ab_judge("Normal", ab({"banner": [1.0, 999, 400, 380]}), B, None)[0] == "OK"


def test_absolute_files_v3_and_a_benchmark_failure_ships_blank_words(tmp_path, monkeypatch, capsys):
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    assert sb.run(dash, str(data), str(out), {}, NOW) == ["/scr_*"]
    fa, f2, fl = gz(out / "scr_all.json.gz"), gz(out / ("scr_%s.json.gz" % KEY)), gz(out / ("scr_l_%s.json.gz" % KEY))
    one = fa["apps"][AID]
    assert set(fa["bench"]) == {"fmt", "min", "apps", "check"} and fa["bench"]["apps"] == 1
    assert fa["bench"]["fmt"]["banner"] == {"fill": None, "show": None, "av": None, "nall": 1}       # 1 unit < 20
    st = {it[0]: one["status"][str(i)] for i, it in enumerate(one["items"]) if str(i) in one["status"]}
    assert all(len(s) == 10 for s in st.values()) and st[MAIN][7] == "OK" and one["lo"] == 0
    assert all(s[7] for i, s in one["status"].items() if one["items"][int(i)][1] == "fs") and one["lt"] == 0  # triggers
    assert len(f2["ufmt"]) == len(f2["units"]) and "banner" in f2["ufmt"]
    rid = {c: "s%d" % i for i, (c, k) in enumerate(f2["screens"])}
    ab = f2["rows"][rid[MAIN]]["ab"]
    assert set(ab) == {"av", "fill", "show", "p", "sig", "unm", "why"} and ab["sig"][0] == "W" and ab["p"]["banner"][0] == 1
    assert "ab" in f2["rows"]["t0"] and "ab" not in f2["rows"].get(rid[ADACT], {})
    rep = fl["report"]["rows"][rid[MAIN]]
    assert "\nAbsolute (last 10 days): Ads / view " in rep and "banner 100 % of the unit ads (fill 90 %, show" in rep
    # a failing benchmark: the words ship "", one health line, the rest of the files unchanged
    monkeypatch.setattr(sb, "ab_bench", lambda apps: 1 / 0)
    out2 = tmp_path / "site2"
    sb.run(dashboard({"show_w": 0.6}), str(data), str(out2), {}, NOW)
    assert "scr bench skipped: ZeroDivisionError" in capsys.readouterr().err
    fb = gz(out2 / "scr_all.json.gz")
    assert fb["bench"] is None and fb["apps"][AID]["lo"] is None and fb["apps"][AID]["status"]["0"][7:] == ["", "", []]
    assert gz(out2 / ("scr_%s.json.gz" % KEY)) == f2


# ── absolute numbers of the full-screen triggers (owner, 7 Nov 2026: the same rule as the screens) ──────────────

def _trig(app, label, f):
    return next(gi for gi, (f_, lab, _) in enumerate(app.trig) if lab == label and f_ == f)


def test_absolute_trigger_numbers_split_a_shared_unit_by_sigma_and_keep_unmatched_units_out(tmp_path):
    # Back press (interstitial): zz_back_1 + house_exit (no AdMob id: the unmatched share, never in a rate); the same
    # AdMob unit is also logged as "ZZ_back_1" with the rewarded format (a second GA4 unit, its own trigger): σ splits the
    # unit's AdMob between the two triggers by their GA4 ads, the rates stay the unit's (fill 0.9, show 0.6)
    def day_fn(d):
        r = core_recs(d, {})
        r["w"]["r"] += [["Rewarded", "ZZ_back_1", 10], ["Interstitial", "house_exit", 15]]
        return r
    app = app_of(tmp_path, day_fn=day_fn)
    w = app.windows()[0]
    side, ts = sb.ab_side(app, w, app.allf()), sb.ab_tside(app, w)
    assert ts["sig"] == ["W", 10, w[0], w[-1]] and ts["S"] == w
    bi, br = _trig(app, "Back press", "interstitial"), _trig(app, "Back press", "rewarded")
    ua, ub = app.uix[("zz_back_1", "interstitial")], app.uix[("ZZ_back_1", "rewarded")]
    assert app.units[ua][2] == app.units[ub][2] and side["ufmt"][ub] == "interstitial"     # AdMob's format, one unit
    ga = sum(app.w[d][("zz_back_1", "interstitial")] for d in w)
    gb, gh = 10 * len(w), 15 * len(w)
    assert ts["G"][tuple(app.units[ua][2])] == ga + gb
    X = side["X"][ua]
    t = sb.ab_trig(app, side, ts, bi, w)
    s = ga / (ga + gb)
    assert t["p"]["interstitial"] == pytest.approx([ga / (ga + gh), s * X[0], s * X[1], s * X[2]])
    assert t["unm"] == pytest.approx(gh / (ga + gh)) and t["ads"] == ga + gh and t["why"] == "" and not t["nm"]
    assert t["fill"] == pytest.approx(X[1] / X[0]) and t["show"] == pytest.approx(X[2] / X[1])     # the unit's own
    assert abs(t["fill"] - 0.9) < 0.01 and abs(t["show"] - 0.6) < 0.01 and t["sh"] == [["zz_back_1", round(s, 4)]]
    r = sb.ab_trig(app, side, ts, br, w)
    assert r["p"]["interstitial"] == pytest.approx([1.0, (1 - s) * X[0], (1 - s) * X[1], (1 - s) * X[2]])
    assert r["show"] == pytest.approx(X[2] / X[1]) and r["sh"] == [["ZZ_back_1", round(1 - s, 4)]]
    # an unshared unit: σ = 1, its own AdMob whole (App resume)
    ar = sb.ab_trig(app, side, ts, _trig(app, "App resume", "appopen"), w)
    assert ar["p"]["appopen"][1:] == side["X"][app.uix[("aoa_resume", "appopen")]] and ar["sh"] == [] and ar["unm"] == 0
    # file 2's shape = the screens' (no Ads / view on a trigger)
    sh = sb.ab_ship(t, ts["sig"])
    assert set(sh) == {"av", "fill", "show", "p", "sig", "unm", "why"} and sh["av"] is None and sh["sig"][0] == "W"


def test_absolute_trigger_sigma_falls_back_and_a_trigger_without_ads_has_no_fill_or_show(tmp_path):
    # the units read is sampled on 8 of W's 10 days: σ from the newest 28 whole units-read days ≤ W's end; App resume
    # shows no ads in W at all: no Fill / Show rate, "—" with the reason, the word "No ads"; no AdMob: "AdMob data nahi"
    def day_fn(d):
        r = core_recs(d, {})
        if d >= W0:
            r["w"]["r"] = [x for x in r["w"]["r"] if x[1] != "aoa_resume"]
        if W0 <= d <= "2026-10-31":
            r["w"] = {"st": "s", "g": "u", "smp": 0.5}
        return r
    app = app_of(tmp_path, day_fn=day_fn)
    w = app.windows()[0]
    side, ts = sb.ab_side(app, w, app.allf()), sb.ab_tside(app, w)
    ok = [d for d in app.days if d <= w[-1] and d in app.whole["w"]]
    assert ts["sig"] == ["new", 28, ok[-28], ok[-1]] and len([d for d in ok if d >= w[0]]) == 2
    t = sb.ab_trig(app, side, ts, _trig(app, "Back press", "interstitial"), w)
    assert abs(t["fill"] - 0.9) < 0.01 and abs(t["show"] - 0.6) < 0.01 and t["why"] == ""
    z = sb.ab_trig(app, side, ts, _trig(app, "App resume", "appopen"), w)
    assert (z["ads"], z["fill"], z["show"], z["p"], z["why"]) == (0, None, None, {}, "is period me is trigger ke koi ad nahi")
    assert sb.ab_judge("Normal", z, {"fmt": {}}, ts["sig"], trig=True)[:2] == ["No ads", "10 din me is trigger ke koi ad nahi"]
    app2 = app_of(tmp_path / "b", dash=dashboard(placements=False))
    s2, t2 = sb.ab_side(app2, w, 0), sb.ab_tside(app2, w)
    n2 = sb.ab_trig(app2, s2, t2, _trig(app2, "Back press", "interstitial"), w)
    assert (n2["fill"], n2["show"], n2["why"], n2["nm"]) == (None, None, "AdMob data nahi", True)


def test_absolute_trigger_words_low_ok_no_benchmark_and_too_few_ads():
    B = {"fmt": {"interstitial": {"fill": [0.4, 0.8, 0.9, 0.95, 30], "show": [0.2, 0.3, 0.5, 0.7, 30], "av": None},
                 "appopen": {"fill": [0.4, 0.8, 0.9, 0.95, 25], "show": [0.1, 0.2, 0.3, 0.5, 25], "av": None},
                 "rewarded": {"fill": None, "show": None, "av": None}}}

    def ab(p, ads=5000, nm=False):
        return {"p": p, "av": None, "ads": ads, "nm": nm, "why": "x" if nm else ""}
    j = sb.ab_judge("Normal", ab({"interstitial": [0.9, 10000, 9500, 2000], "rewarded": [0.1, 500, 400, 300]}), B, None,
                    trig=True)
    assert j == ["Low", "Show rate 21 % (interstitial median 50 %): ads filled but not shown",
                 [["show", "interstitial", 0.2105, 0.5, 0.3]]]
    assert sb.ab_judge("Watch", ab({"appopen": [1.0, 4000, 3800, 1500]}), B, None, trig=True) == ["OK", "", []]
    # a format with no benchmark (n < 20): the number shown, never judged
    assert sb.ab_judge("Normal", ab({"rewarded": [1.0, 5000, 4000, 3000]}), B, None, trig=True) == [
        "No benchmark", "rewarded: no benchmark (n < 20)", []]
    # … beside a judged part: that part's word
    assert sb.ab_judge("Normal", ab({"rewarded": [0.7, 5000, 4000, 3000], "appopen": [0.3, 4000, 3800, 1500]}), B, None,
                       trig=True)[0] == "OK"
    # under the floors (999 requests, 299 matched): Too few ads; the screens' words for the same parts stay theirs
    few = ab({"interstitial": [1.0, 999, 299, 10]})
    assert sb.ab_judge("Normal", few, B, None, trig=True)[0] == "Too few ads"
    assert sb.ab_judge("Normal", ab({"rewarded": [1.0, 5000, 4000, 3000]}), B, None) == ["OK", "", []]
    assert sb.ab_judge("N/A", few, B, None, trig=True) == ["N/A", "", []]
    assert sb.ab_judge("Normal", ab({}, nm=True), B, None, trig=True) == ["Not measurable", "x", []]


def test_absolute_trigger_words_ship_in_scr_all_with_their_low_count(tmp_path, monkeypatch, capsys):
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    sb.run(dash, str(data), str(out), {}, NOW)
    fa, f2 = gz(out / "scr_all.json.gz"), gz(out / ("scr_%s.json.gz" % KEY))
    one = fa["apps"][AID]
    tr = {it[0]: one["status"][str(i)] for i, it in enumerate(one["items"]) if it[1] == "fs"}
    assert sorted(tr) == ["App resume", "Back press"] and all(len(s) == 10 for s in tr.values())
    # 1 unit per format < 20: no benchmark — the words never "" and never Low; "lt" beside "lo"
    assert {s[7] for s in tr.values()} <= {"No benchmark", "N/A", "Too few ads", "Too early"} and one["lt"] == 0
    assert set(f2["rows"]["t0"]["ab"]) == {"av", "fill", "show", "p", "sig", "unm", "why"}
    assert abs(f2["rows"]["t0"]["ab"]["fill"] - 0.9) < 0.01
    # a benchmark failure: "lt" null like "lo" (the key stays: the page says "—", benchmark nahi bana)
    monkeypatch.setattr(sb, "ab_bench", lambda apps: 1 / 0)
    out2 = tmp_path / "site2"
    sb.run(dashboard({"show_w": 0.6}), str(data), str(out2), {}, NOW)
    assert "scr bench skipped: ZeroDivisionError" in capsys.readouterr().err
    fb = gz(out2 / "scr_all.json.gz")["apps"][AID]
    assert "lt" in fb and fb["lt"] is None and all(s[7:] == ["", "", []] for s in fb["status"].values())



# ── v 4: Firebase's numbers and the three signals (owner, 8 Nov 2026) ─────────────────────────────────────────────────
def _ix(d, d0="2026-08-01"):
    return (date.fromisoformat(d) - date.fromisoformat(d0)).days


def test_v4_periods_are_the_fetchs_and_the_pages():
    from admob_iq.fetch import ga4_screens as gs
    for td in (date(2026, 11, 4), date(2026, 3, 1), date(2026, 1, 31), date(2024, 2, 29), date(2026, 12, 31)):
        for d0 in (td, td - timedelta(days=1), td - timedelta(days=45), td - timedelta(days=400), td.replace(day=1)):
            assert sb.pwin(td, d0) == [(k, lo.isoformat(), hi.isoformat(), kd) for k, lo, hi, kd in gs.pu_wanted(td, d0)]
    w = {k: (lo, hi, kd) for k, lo, hi, kd in sb.pwin("2026-11-04", "2026-08-01")}
    assert w["2026-10-27_2026-11-02"] == ("2026-10-27", "2026-11-02", "roll")           # 7 days ending td − 2
    assert w["2026-10-01_2026-10-31"][2] == "month" and w["2026-11-01_2026-11-04"][2] == "day"
    assert sb._prev("2026-10-01", "2026-10-31", "month") == ("2026-09-01", "2026-09-30")
    assert sb._prev("2026-11-01", "2026-11-04", "day") == ("2026-10-01", "2026-10-31")   # this month: the month before
    assert sb._prev("2026-10-27", "2026-11-02", "roll") == ("2026-10-20", "2026-10-26")


def test_v4_revenue_full_screen_rows_users_of_a_period(tmp_path):
    def day_fn(d):
        r = core_recs(d, {})
        r["m"] = {"st": "w", "g": "c", "t": [2600000, 2550000],
                  "r": [[MAIN, 500000, 500000], [EDIT, 100000, 50000], [ADACT, 2000000, 2000000]]}
        return r
    data, out, dash = build(tmp_path, day_fn=day_fn)
    for p in dash["placements"]:
        for row in p["daily"]:
            row[1] = row[2] * 1000 + 7                  # AdMob revenue micros, its own per unit and day
    users = {"2026-10-01_2026-10-31": {"lo": "2026-10-01", "hi": "2026-10-31", "st": "w", "tot": 1000, "fin": 1,
                                       "r": [[MAIN, 900], [EDIT, 300], ["x.y.Gone", 5]]},
             "2026-10-02_2026-10-30": {"lo": "2026-10-02", "hi": "2026-10-30", "st": "w", "tot": 9, "r": []},
             "2026-10-27_2026-11-02": {"lo": "2026-10-27", "hi": "2026-11-02", "st": "s", "smp": 0.5},
             "2026-09-01_2026-09-30": {"lo": "2026-09-02", "hi": "2026-09-30", "st": "w", "tot": 5, "r": []}}
    write_json_gz_stable(str(data / "ga4_screens" / KEY / "users.json.gz"), {"v": 1, "w": users})
    sb.run(dash, str(data), str(out), {}, NOW)
    f2, one = gz(out / ("scr_%s.json.gz" % KEY)), gz(out / "scr_all.json.gz")["apps"][AID]
    assert f2["pw"] == [list(x) for x in sb.pwin("2026-11-04", "2026-08-01")]
    six = {c: i for i, (c, _) in enumerate(f2["screens"])}
    e = f2["days"][_ix("2026-10-15")]
    assert e["m"] == sorted([[six[MAIN], 500000, 500000], [six[EDIT], 100000, 50000], [six[ADACT], 2000000, 2000000]])
    assert e["st"]["m"] == "w" and set(one["st"]) == set(sb.READ_IDS) and "m" in one["st"]
    # the users of a period: only a period the page offers with the same days; a class the build does not know left
    # out; a sampled period ships its state only
    assert f2["pu"] == {"2026-10-01_2026-10-31": {"st": "w", "u": sorted([[six[MAIN], 900], [six[EDIT], 300]]),
                                                  "tot": 1000},
                        "2026-10-27_2026-11-02": {"st": "s"}}
    assert one["pt"] == {"2026-10-01_2026-10-31": 1000}
    # the full-screen rows from AdMob: by trigger label, summed on AdMob's own days (never blended), none after
    # latest_complete
    labels = [(f, lab) for f, lab, _ in f2["fs4"]]
    assert labels == [("appopen", "App resume"), ("interstitial", "Back press")]
    assert f2["fs4"][1][2] == ["zz_back_1"] and len(f2["fsd"]) == 2 and len(f2["fsd"][1]) == len(f2["days"])
    row = next(r for r in next(p for p in dash["placements"] if p["name"] == "zz_back_1")["daily"] if r[0] == "2026-10-15")
    assert f2["fsd"][1][_ix("2026-10-15")] == [row[3], row[4], row[2], row[1]]
    assert f2["fsd"][1][_ix("2026-11-04")] is None and f2["fsd"][1][_ix("2026-11-03")] is not None
    day = [next(r for r in p["daily"] if r[0] == "2026-10-15") for p in dash["placements"]]
    assert f2["adt"][_ix("2026-10-15")] == [sum(r[3] for r in day), sum(r[4] for r in day), sum(r[2] for r in day),
                                            sum(r[1] for r in day)]
    # scr_all: per day [GA4's revenue on every screen, AdMob's app total]
    assert one["rv"][_ix("2026-10-15")] == [2600000, sum(r[1] for r in day)]
    assert one["rv"][_ix("2026-11-04")] == [2600000, None]
    assert set(one["sg"]) == {k for k, *_ in sb.pwin("2026-11-04", "2026-08-01")}


def test_v4_the_three_signals(tmp_path):
    # ⚠️ + 🔻: the main screen's banner unit shows 36 % of its fills from W0 (24 Oct) and its ads per user fall 40 %
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    sb.run(dash, str(data), str(out), {}, NOW)
    f2, one = gz(out / ("scr_%s.json.gz" % KEY)), gz(out / "scr_all.json.gz")["apps"][AID]
    six = {c: i for i, (c, _) in enumerate(f2["screens"])}
    w7 = f2["sig"]["2026-10-27_2026-11-02"]["s%d" % six[MAIN]]
    codes = {x[0]: x for x in w7}
    assert set(codes) == {"w", "d"}
    w = codes["w"]
    assert w[1] == "unit_a" and 0.35 < w[2] < 0.37 and w[3] >= sb.SIG_WASTE and w[4] > w[5] > 0
    d = codes["d"]
    assert d[3:] == ["2026-10-20", "2026-10-26"] and d[2] <= (1 - sb.SIG_DROP) * d[1]
    assert one["sg"]["2026-10-27_2026-11-02"] == [0, 1, 1]
    # a whole month before W0: neither (the show rate 60 %, no drop)
    assert "2026-09-01_2026-09-30" not in f2["sig"] and one["sg"]["2026-09-01_2026-09-30"] == [0, 0, 0]
    # October: 8 days of the change in 31 — its month shows more than half its fills (no ⚠️) and −10 % only (no 🔻)
    assert "s%d" % six[MAIN] not in f2["sig"].get("2026-10-01_2026-10-31", {})
    # All time: no 🔻 (nothing before it)
    assert all(x[0] != "d" for xs in f2["sig"].get("2026-08-01_2026-11-04", {}).values() for x in xs)


def test_v4_ad_space_signal(tmp_path):
    # 💡: the edit screen keeps a third of the screen time but shows no ads at all
    def day_fn(d):
        r = core_recs(d, {})
        r["a"]["r"] = [x for x in r["a"]["r"] if x[0] != EDIT]
        r["w"]["r"] = [x for x in r["w"]["r"] if x[1] != "unit_n"]
        r["t"]["a"] = [[f, n] for f, n in r["t"]["a"] if f != "Native advanced"]
        return r
    data, out, dash = build(tmp_path, day_fn=day_fn)
    sb.run(dash, str(data), str(out), {}, NOW)
    f2, one = gz(out / ("scr_%s.json.gz" % KEY)), gz(out / "scr_all.json.gz")["apps"][AID]
    six = {c: i for i, (c, _) in enumerate(f2["screens"])}
    b = f2["sig"]["2026-10-01_2026-10-31"]["s%d" % six[EDIT]]
    assert len(b) == 1 and b[0][0] == "b" and abs(b[0][1] - 1 / 3) < 0.01 and b[0][2] == 0
    assert one["sg"]["2026-10-01_2026-10-31"][0] == 1
    assert "s%d" % six[MAIN] not in f2["sig"]["2026-10-01_2026-10-31"]


def test_v4_a_row_whose_ads_stop_is_flagged_dropped(tmp_path):
    # the main screen's ads stop from W0: its share of the app's ads NOW is 0, before it was most of them — 🔻 holds on
    # the larger of the two (a materiality on the period alone would never flag the row that matters most)
    def day_fn(d):
        r = core_recs(d, {})
        if d >= W0:
            r["a"]["r"] = [x for x in r["a"]["r"] if x[0] != MAIN]
            r["t"]["a"] = [[f, n - (200 + _j(d) if f == "Banner" else 0)] for f, n in r["t"]["a"]]
        return r
    data, out, dash = build(tmp_path, day_fn=day_fn)
    sb.run(dash, str(data), str(out), {}, NOW)
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    six = {c: i for i, (c, _) in enumerate(f2["screens"])}
    codes = [x[0] for x in f2["sig"]["2026-10-27_2026-11-02"]["s%d" % six[MAIN]]]
    assert "d" in codes
    d = next(x for x in f2["sig"]["2026-10-27_2026-11-02"]["s%d" % six[MAIN]] if x[0] == "d")
    assert d[2] == 0 and d[1] > 0 and d[3:] == ["2026-10-20", "2026-10-26"]


def test_v4_one_admob_unit_two_ga4_names_counts_once(tmp_path):
    # one AdMob unit logged by GA4 under two names (two cases) on the main screen: ⚠️ weighs it ONCE — fills 100 a day,
    # shown 40, the app's fills 400: 60 not shown = 15 % of the app's fills, under the 20 % bar (counted twice: 30 %)
    def day_fn(d):
        r = core_recs(d, {})
        r["a"]["r"] = [[MAIN, "Banner", "unit_a", 50], [MAIN, "Banner", "Unit_A", 50], [EDIT, "Native advanced", "unit_n", 50]]
        r["w"]["r"] = [["Banner", "unit_a", 50], ["Banner", "Unit_A", 50], ["Native advanced", "unit_n", 50]]
        r["t"]["a"] = [["Banner", 100], ["Native advanced", 50]]
        return r
    data, out, dash = build(tmp_path, day_fn=day_fn)
    for p in dash["placements"]:
        for row in p["daily"]:
            if p["name"] == "unit_a":
                row[2:5] = [40, 110, 100]                   # imp, req, matched
            elif p["name"] == "unit_n":
                row[2:5] = [290, 310, 300]
            else:
                row[2:5] = [0, 0, 0]
    sb.run(dash, str(data), str(out), {}, NOW)
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    six = {c: i for i, (c, _) in enumerate(f2["screens"])}
    assert all(x[0] != "w" for xs in f2["sig"].values() for x in xs.get("s%d" % six[MAIN], []))
    # (the same unit at 30 % of the app's fills — a smaller app: it is flagged, once)
    for p in dash["placements"]:
        if p["name"] == "unit_n":
            for row in p["daily"]:
                row[2:5] = [90, 110, 100]
    sb.run(dash, str(data), str(out), {}, NOW)
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    w = [x for x in f2["sig"]["2026-10-01_2026-10-31"]["s%d" % six[MAIN]] if x[0] == "w"]
    assert len(w) == 1 and w[0][1] in ("unit_a", "Unit_A") and w[0][4] == 3100 and w[0][5] == 1240   # 31 days, once


def test_v4_unjudged_counts_old_unit_mix_and_a_failure_kept_to_its_app(tmp_path, monkeypatch, capsys):
    data, out, dash = build(tmp_path, {"show_w": 0.6})
    sb.run(dash, str(data), str(out), {}, NOW)
    one = gz(out / "scr_all.json.gz")["apps"][AID]
    assert one["sg"]["2026-08-01_2026-11-04"][2] is None                      # All time: 🔻 is never judged — "—"
    assert one["sg"]["2026-11-04_2026-11-04"] == [None, None, None]           # Today: no final day, AdMob's not complete
    assert one["sg"]["2026-10-27_2026-11-02"] == [0, 1, 1]
    # a screen's unit mix from days before the period (none of its own): ⚠️ names those days
    def day_fn(d):
        r = core_recs(d, {"show_w": 0.6})
        if d >= "2026-09-15":                                                 # GA4 stops splitting screens by unit
            r["a"] = {"st": "w", "g": "c", "r": [[c, n] for c, n in
                                                 ((c, sum(x[3] for x in r["a"]["r"] if x[0] == c)) for c in (MAIN, EDIT, ADACT, NS))]}
        return r
    data2, out2, dash2 = build(tmp_path / "b", {"show_w": 0.6}, day_fn=day_fn)
    sb.run(dash2, str(data2), str(out2), {}, NOW)
    f2 = gz(out2 / ("scr_%s.json.gz" % KEY))
    six = {c: i for i, (c, _) in enumerate(f2["screens"])}
    w = next(x for x in f2["sig"]["2026-10-27_2026-11-02"]["s%d" % six[MAIN]] if x[0] == "w")
    assert f2["notes"]["allf"] == 2 and w[6:] == ["2026-08-18", "2026-09-14"]   # the newest SIG_N split days up to its end
    # v 4 failing on an app: its files still written, ONE health line with the type
    monkeypatch.setattr(sb, "signals4", lambda *a, **k: (_ for _ in ()).throw(ValueError("made-up")))
    capsys.readouterr()
    sb.run(dash, str(data), str(out), {}, NOW)
    err = capsys.readouterr().err
    assert "scr v4 skipped: ValueError\n" in err and "made-up" not in err
    f2 = gz(out / ("scr_%s.json.gz" % KEY))
    assert f2["v"] == sb.V and f2["sig"] == {} and f2["pw"] == [] and len(f2["days"]) == len(_days("2026-08-01", "2026-11-04"))
