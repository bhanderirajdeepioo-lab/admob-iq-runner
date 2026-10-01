"""Synthetic BUILT site for the Daily App Review tests (admob_iq.review) and the Review tab's frontend fixture — no
network, no real data. Every id, name, package and amount below is made up.

  make_site(dir, day)   writes a small built site (dashboard.json.gz + uninstall.json.gz + the lazy per-app files +
                        the side JSON files) for 8 synthetic apps on review day `day` (default DAY):
      a1  red kamai drop (big, 🆕)             a5  green only (kamai up + a good update, madhyam)
      a2  critical ad-unit click spike (big)   a6  small app with a red uninstall-rate row (🆕)
      a3  uninstall cohort warning (big)       a7  HIDDEN (selected: false) — must never appear
      a4  all normal (big)                     a8  selected, no GA4 (active.no_ga4)
  EXPECT                the order / tiers the builder must give that site.
  make_fixture()        {"index", "day", "state", "me"} for tests/review_frontend.js (a synthetic GET day response).

    python -m tests.review_synth --write     regenerates tests/fixtures/review_sample.json
"""

import gzip
import hashlib
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

DAY = date(2026, 10, 1)                       # a Guruvar — the review day of the fixture
PUB, PUB2 = "pub-0000000000000000", "pub-1111111111111111"
FX = 88.0
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "review_sample.json")
NOW = datetime(2026, 10, 1, 4, 17, 9, tzinfo=timezone.utc)     # 09:47 IST — after the ready time


def aid(i):
    return f"ca-app-pub-0000000000000000~00000000{i:02d}"


def key(app_id):
    return hashlib.sha1(app_id.encode("utf-8")).hexdigest()[:12]


A = {i: aid(i) for i in range(1, 9)}
K = {i: key(A[i]) for i in A}
STORE = {1: "Synth Alpha Player", 2: "Synth Beta Browser", 3: "Synth Gamma Gallery", 4: "Synth Delta Diary",
         5: "Synth Echo Editor", 6: "Synth Foxtrot Flash", 7: "Synth Hidden Hotel", 8: "Synth Hotel Notes"}
ACC = {1: PUB, 2: PUB, 3: PUB, 4: PUB2, 5: PUB2, 6: PUB, 7: PUB, 8: PUB2}
ACCT_NAME = {PUB: "Synth Studio"}                 # PUB2 has no friendly name → "A/c 1111"
DNAME = {i: f"{STORE[i]} · {ACCT_NAME.get(ACC[i], 'A/c 1111')}" for i in A}
PKG = {i: f"com.example.synth{i}" for i in A}
UNIT = {i: f"ca-app-pub-0000000000000000/10000000{i:02d}" for i in A}
# USD per day: (before the last 7 days, the last 7 days)
REV = {1: (520.0, 320.0), 2: (400.0, 400.0), 3: (350.0, 350.0), 4: (450.0, 450.0), 5: (80.0, 110.0), 6: (12.0, 12.0),
       7: (999.0, 999.0), 8: (60.0, 60.0)}

# what the builder must make of this site (order.top = 🆕 first, then 7-day kamai desc; ok / small by kamai desc)
EXPECT = {
    "top": [2, 1, 3, 8], "ok": [4, 5], "small": [6],
    "tier": {1: "red", 2: "red", 3: "amber", 4: "normal", 5: "green", 6: "red", 8: "amber"},
    "nb": {1: ["kamai"], 2: ["deduct"], 3: [], 4: [], 5: [], 6: ["uninstall"], 8: []},
    "size": {1: "badi", 2: "badi", 3: "badi", 4: "badi", 5: "madhyam", 6: "chhoti", 8: "madhyam"},
    "red_feat": {1: "kamai", 2: "deduct", 6: "uninstall"},
    "amber_feat": {3: "uninstall", 8: "setup"},
    "counts": {"apps": 7, "attn": 4, "ok": 2, "small": 1, "nb": 2, "red": 2, "amber": 2, "failed": 0},
}


def iso(d):
    return d.isoformat()


def _days(end, n):
    return [end - timedelta(days=i) for i in range(n - 1, -1, -1)]


def _gz(path, obj):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def _js(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def dashboard(day=DAY):
    """The dashboard.json fields the review builder reads (§A.2), for review day `day`."""
    y = day - timedelta(1)                        # latest_complete (AdMob's last full day)
    ga4 = day - timedelta(3)                      # GA4 lags 3 days
    settled = day - timedelta(6)
    w7_start = y - timedelta(6)
    placements = []
    for i in A:
        before, now = REV[i]
        daily = []
        for d in _days(y, 60):
            usd = now if d >= w7_start else before
            impr, clicks = 100_000, 1_000
            if i == 2 and d >= y - timedelta(3):
                clicks = 4_000                    # the click spike: 1% → 4% click rate for the last 4 days
            daily.append([iso(d), int(round(usd * 1e6)), impr, 120_000, 110_000, clicks])
        placements.append({"id": UNIT[i], "app": DNAME[i], "country": "All",
                           "place": "home_banner" if i == 2 else "main_banner", "daily": daily})
    catalog = [{"account_id": ACC[i], "app_id": A[i], "app_name": DNAME[i], "rev": REV[i][1] * 30,
                "selected": i != 7, "account_decided": True} for i in A]
    alerts = {"counts": {"critical": 2}, "items": [
        {"app": DNAME[2], "id": UNIT[2], "place": "home_banner", "severity": "critical", "kind": "spike",
         "metrics": [{"metric": "ctr", "current": 0.04, "message": "CTR 4.00% vs 1.00%"}]},
        {"app": DNAME[7], "id": UNIT[7], "place": "main_banner", "severity": "critical", "kind": "spike",
         "metrics": [{"metric": "ctr", "current": 0.05, "message": "CTR 5.00% vs 1.00%"}]}]}
    uni_apps = [{"app_id": A[i], "ready": True, "head4": {"D0": {"p": 0.2, "from": iso(ga4 - timedelta(13)),
                                                               "to": iso(ga4 - timedelta(7))}},
                 "rate7": 2.0, "updates": ([{"date": iso(day - timedelta(21)), "label": "v1.0.7 → v1.0.8"}]
                                           if i == 5 else [])}
                for i in (1, 2, 3, 4, 5, 6, 7)]
    uni_alerts = [
        {"app_id": A[3], "family": "cohort", "severity": "warning", "n": 0, "dir": "up",
         "installs_from": iso(day - timedelta(16)), "installs_to": iso(day - timedelta(10)), "before": 0.2,
         "now": 0.3, "vs": ["always"], "opened": iso(day - timedelta(8)), "users": 700, "provisional": False,
         "message": "synthetic"},
        {"app_id": A[6], "family": "rate_drift", "severity": "warning", "dir": "up", "before": 2.0, "now": 3.0,
         "since": iso(day - timedelta(7)), "base_from": iso(day - timedelta(60)), "base_to": iso(day - timedelta(33)),
         "data_till": iso(ga4), "provisional": False, "opened": iso(day - timedelta(5)), "message": "synthetic"},
        {"app_id": A[7], "family": "cohort", "severity": "warning", "n": 0, "dir": "up",
         "installs_from": iso(day - timedelta(16)), "installs_to": iso(day - timedelta(10)), "before": 0.2,
         "now": 0.5, "vs": ["prev"], "opened": iso(day - timedelta(8)), "users": 900, "provisional": False}]
    win = {"from": iso(ga4 - timedelta(6)), "to": iso(ga4), "bfrom": iso(ga4 - timedelta(13)),
           "bto": iso(ga4 - timedelta(7))}
    act_apps = [{"app_id": A[i], "key": K[i], "file": f"active_{K[i]}.json.gz" if i == 4 else None,
                 "m": {"ret_dau": {"v": 12000 + 1000 * i, "rel": 0.01, "st": "normal"}, "d1": {"v": 0.35}},
                 "win": win, "data_till": iso(ga4)} for i in (1, 2, 3, 4, 5, 6, 7)]
    val_apps = [{"app_id": A[4], "key": K[4], "file": f"value_{K[4]}.json.gz",
                 "pay": {"st": "ok", "p": 45, "from": iso(day - timedelta(90)), "to": iso(day - timedelta(84))},
                 "cpi": {"spend4_src": 50.0 * 28 * FX}},
                {"app_id": A[5], "key": K[5], "pay": {"st": "nospend", "note": "Google Ads spend nahi — synthetic"}}]
    spend = {iso(d): 50_000_000 for d in _days(y, 20)}
    installs = {iso(d): 100 for d in _days(y, 20)}
    return {
        "today_date": iso(day), "latest_complete": iso(y), "usd_inr": FX,
        "generated_at": f"{iso(day)}T04:13:55+00:00",
        "apps_catalog": catalog, "placements": placements, "alerts": alerts,
        "range_alerts": [{"id": UNIT[7], "app": DNAME[7], "place": "main_banner", "metric": "show", "range": [0.8, 0.95],
                          "now": 0.5, "severity": "warning"}],
        "uninstall": {"apps": uni_apps, "alerts": uni_alerts, "data_till_max": iso(ga4)},
        "active": {"apps": act_apps, "alerts": [], "no_ga4": [{"app_id": A[8], "app": DNAME[8]}],
                   "settled_till_max": iso(settled)},
        "value": {"apps": val_apps},
        "roas": {"by_app": {DNAME[4]: {"daily": spend, "installs_daily": installs,
                                       "campaigns": [{"status": "ENABLED"}, {"status": "PAUSED"}]}}},
        "account_health": {"per_app": [{"app": DNAME[i], "ivt": "clean", "serving": "ok", "app_ads_txt": "ok",
                                        "consent": "ok", "tcf": "ok"} for i in A]},
        "accounts": [{"account_id": PUB, "token": "Valid"}, {"account_id": PUB2, "token": "Valid"}],
        "app_store_ids": {A[8]: PKG[8]},
    }


def uninstall_asset(day=DAY):
    """uninstall.json.gz: per app key / package / late days / daily rate series / judged updates."""
    ga4 = day - timedelta(3)
    start = ga4 - timedelta(89)
    apps = []
    for i in (1, 2, 3, 4, 5, 6, 7):
        a = {"app_id": A[i], "key": K[i], "package": PKG[i], "late_days": 7, "alerts_closed": [],
             "impact": {"updates": []}}
        if i == 5:
            a["impact"]["updates"] = [{"date": iso(day - timedelta(21)), "label": "v1.0.7 → v1.0.8",
                                       "verdict": {"level": "win", "why": "back next day badha — synthetic"}}]
        if i == 6:
            since = day - timedelta(7)
            days = _days(ga4, 90)
            a["daily"] = {"start": iso(start), "rate": [3.0 if d >= since else 2.0 for d in days],
                          "un": [30 if d >= since else 20 for d in days], "a28": [10_000 for _ in days]}
        apps.append(a)
    return {"v": 1, "apps": apps}


def cohort_file(day=DAY):
    """uninstall_c_<a3>.json.gz: day-0 uninstall share 20 → 30 in 100 from the install week 23 days back."""
    ga4 = day - timedelta(3)
    start = ga4 - timedelta(89)
    turn = day - timedelta(23)
    days = _days(ga4, 90)
    return {"start": iso(start), "end": iso(ga4), "new": [100 for _ in days],
            "lags": [[[0, 30 if d >= turn else 20], [2, 5]] for d in days]}


def make_site(site_dir, day=DAY):
    """Write the synthetic built site into `site_dir` (created) → the dashboard dict."""
    os.makedirs(site_dir, exist_ok=True)
    dash = dashboard(day)
    _gz(os.path.join(site_dir, "dashboard.json.gz"), dash)
    _gz(os.path.join(site_dir, "uninstall.json.gz"), uninstall_asset(day))
    _gz(os.path.join(site_dir, f"uninstall_c_{K[3]}.json.gz"), cohort_file(day))
    _gz(os.path.join(site_dir, f"active_{K[4]}.json.gz"), {"changes": {"info": []}, "act_late_days": 3})
    _gz(os.path.join(site_dir, f"value_{K[4]}.json.gz"), {"changes": {"info": []}, "weeks": [], "scale": {}})
    _js(os.path.join(site_dir, "account_names.json"), ACCT_NAME)
    _js(os.path.join(site_dir, "app_names.json"), {A[5]: "Synth Echo Editor – Pro"})
    _js(os.path.join(site_dir, "approved_ranges.json"), {"placements": {}})
    _js(os.path.join(site_dir, "baseline.json"), {"units": [], "data_range": {"last": "2026-08"}})
    y = day - timedelta(1)
    dd = [iso(d) for d in _days(y, 14)]
    _js(os.path.join(site_dir, "deductions_daily.json"), {
        "dates": dd, "units": {UNIT[4]: {"app_id": A[4], "unit_name": "main_banner"}},
        "data": {UNIT[4]: [[10, 452_000_000, 450_000_000]]}})
    md = [iso(d) for d in _days(y, 21)]
    _js(os.path.join(site_dir, "mediation_daily.json"), {
        "dates": md, "names": {"s1": "Synth Network One", "s2": "Synth Network Two"},
        "by_app": {DNAME[4]: {"s1": [[j, 300_000_000, 0, 60_000, 70_000] for j in range(len(md))],
                              "s2": [[j, 150_000_000, 0, 40_000, 50_000] for j in range(len(md))]}}})
    return dash


# ── the frontend fixture ────────────────────────────────────────────────────────────────────────
TEAM, OWNER = "team@example.test", "owner@example.test"


def _flag(fid, day, app, feature, status, note, raised_by=TEAM, raised_at=None, decision=None, dec_note=None,
          dec_by=None, dec_at=None, dec_day=None):
    return {"id": fid, "day": day, "app": K[app], "app_label": DNAME[app], "feature": feature, "note": note,
            "raised_by": raised_by, "raised_at": raised_at or f"{day}T05:00:00.000Z", "status": status,
            "decision": decision, "dec_note": dec_note, "dec_by": dec_by, "dec_at": dec_at, "done_note": None,
            "done_by": None, "done_at": None, "wd_by": None, "wd_at": None, "dec_day": dec_day, "done_day": None}


def daystate(day=DAY):
    """A synthetic GET /api/review/day response for `day` (§B.7) that exercises every layout rule (§C.5):
      a5 (ok group)    an OPEN flag on Kamai from an earlier day   → lifted to the top
      a4 (ok group)    yesterday's "kal dobara dekho"              → lifted to the top
      a1 (top, 🆕)      newBad                                      → first in the top
      a2 (top, 🆕)      its only red feature (deduct) snoozed       → drops to "Sab theek"
      a6 (small)       a whole-app 🛠 kaam flag                     → NOT lifted (chip only)
      a3 (top)         a feature flag raised today (open)
    plus a note with HTML-looking text (the page must escape it)."""
    d, d1, d2 = iso(day), iso(day - timedelta(1)), iso(day - timedelta(2))
    at = f"{d}T05:10:00.000Z"
    flags = [_flag(1, d1, 5, "kamai", "open", "Kamai upar gayi par ad rate gira — synthetic"),
             _flag(2, d2, 6, None, "kaam", "Poori app dekho — synthetic", decision="kaam",
                   dec_note="Developer ko bolo — synthetic", dec_by=OWNER, dec_at=f"{d2}T09:00:00.000Z", dec_day=d2),
             _flag(3, d, 3, "uninstall", "open", "", raised_at=at)]
    snoozes = [{"id": 1, "app": K[2], "app_label": DNAME[2], "feature": "deduct", "day": d,
                "until": iso(day + timedelta(7)), "days": 7, "note": "Pata hai — synthetic", "who": TEAM, "at": at}]
    states = {K[4]: {"st": "ok", "who": TEAM, "at": at, "snz": []},
              K[2]: {"st": "ok", "who": TEAM, "at": at, "snz": ["deduct"]},
              K[3]: {"st": "kal", "who": OWNER, "at": at, "snz": []}}
    notes = [{"id": 1, "app": K[4], "text": "Synthetic note <img src=x onerror=alert(1)> & more", "who": TEAM,
              "at": at}]
    log = [{"id": 6, "at": at, "who": OWNER, "act": "kal", "app": K[3], "feature": None, "note": None, "ref": None,
            "extra": None},
           {"id": 5, "at": at, "who": TEAM, "act": "flag", "app": K[3], "feature": "uninstall", "note": "", "ref": 3,
            "extra": None},
           {"id": 4, "at": at, "who": TEAM, "act": "snooze", "app": K[2], "feature": "deduct",
            "note": "Pata hai — synthetic", "ref": 1, "extra": "{\"days\":7}"},
           {"id": 3, "at": at, "who": TEAM, "act": "ok", "app": K[2], "feature": None, "note": None, "ref": None,
            "extra": None},
           {"id": 2, "at": at, "who": TEAM, "act": "note", "app": K[4], "feature": None,
            "note": "Synthetic note <img src=x onerror=alert(1)> & more", "ref": 1, "extra": None},
           {"id": 1, "at": at, "who": TEAM, "act": "ok", "app": K[4], "feature": None, "note": None, "ref": None,
            "extra": None}]
    return {"d": d, "open_day": d, "writable": True, "rev": 6, "states": states, "notes": notes, "flags": flags,
            "snoozes": snoozes, "prev": {"d": d1, "kal": [K[4]]}, "log": log}


def make_fixture(tmp=None):
    """{"index", "day", "state", "me"}: three snapshot days (DAY-2 … DAY) over the synthetic site, the open day's
    document, a synthetic DAYSTATE and /me — written by the REAL builder code."""
    from admob_iq.review.store import read_doc, review_run
    own = tmp is None
    tmp = tmp or tempfile.mkdtemp(prefix="review_synth_")
    site, data = os.path.join(tmp, "site"), os.path.join(tmp, "data")
    make_site(site, DAY)
    import contextlib
    import io
    env = {"REVIEW_READY_IST": "09:00"}
    with contextlib.redirect_stderr(io.StringIO()):
        for back in (2, 1, 0):
            d = DAY - timedelta(back)
            res = review_run(None, data, site, NOW - timedelta(days=back), today=d, env=env)
            if not res["ok"]:
                raise RuntimeError("synthetic review build failed")
    with open(os.path.join(site, "review", "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    doc = read_doc(os.path.join(data, "review", "days", f"{iso(DAY)}.json.gz"), iso(DAY))
    out = {"_about": ("Synthetic Daily App Review fixture (tests/review_synth.py --write): index.json + the open "
                      "day's card document written by admob_iq.review over a made-up site, a synthetic GET day "
                      "response and /me. No real data."),
           "index": index, "day": doc, "state": daystate(DAY),
           "me": {"email": OWNER, "admin": True, "open_day": iso(DAY), "go_live": index["go_live"],
                  "server_time": "2026-10-01T05:30:00.000Z"}}
    if own:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def fixture_text(fx):
    return json.dumps(fx, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    if "--write" not in sys.argv:
        print("usage: python -m tests.review_synth --write", file=sys.stderr)
        sys.exit(2)
    os.makedirs(os.path.dirname(FIXTURE), exist_ok=True)
    with open(FIXTURE, "w", encoding="utf-8") as f:
        f.write(fixture_text(make_fixture()))
    print(f"wrote {os.path.relpath(FIXTURE)}")
