"""📡 Meta revenue / AdMob revenue — two Overview tiles (All apps and each app, on the top bar's Period: Estimated earnings of
Meta bidding / of AdMob Network + its Waterfall line) and, still on its own screen, the list: one row per app: App · AdMob req ·
Meta bid req · Meta won %. The other tiles stay as they were.

The numbers are the mediation file the page already ships (mediation_daily.json, date × app × ad source → [revenue,
impressions, matched, requests]) summed over the Period: AdMob req = the "AdMob Network" source's requests; Meta bid req =
"Meta Audience Network (bidding)"'s requests and Meta won = its matched requests, so Meta won % = won ÷ bid requests. Other
sources (the Meta waterfall line, a third network) never count in the requests or in the Meta revenue; the two are never added up; a Period with a day
the file lacks shows "—", never a part-sum.

tests/bidreq_frontend.js runs the page's own script on the SYNTHETIC file below (made-up apps, source ids and counts); every
expected number here is worked out by hand from the per-day values, not through the code under test. Node runs with
LC_ALL=en_US.UTF-8: the page formats with toLocaleString(), which follows the machine's locale."""

import html as H
import json
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
TAG = re.compile(r"<[^>]*>")

DAYS = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(10)]     # 1 … 10 Jan
TODAY = DAYS[-1]                                                                     # 10 Jan: the build's partial day
GAP = "2026-01-04"                                     # a day neither the page's dates nor the file have (a real file has one)
AXIS = [d for d in DAYS if d != GAP]
ADM, ADM_WF, META, META_WF, OTHER = "9001", "9002", "9003", "9004", "9005"
NAMES = {ADM: "AdMob Network", ADM_WF: "AdMob Network Waterfall", META: "Meta Audience Network (bidding)",
         META_WF: "Meta Audience Network", OTHER: "Pangle (bidding)"}
REV = {ADM: 20_000_000, ADM_WF: 5_000_000, META: 12_000_000, META_WF: 3_000_000, OTHER: 40_000_000}   # micros per app-day
APPS = ["Demo Gallery", "Puzzle Quest", "Alpha Tools", "Tiny Notes", "Echo Radio", "Quiet App"]   # Quiet App: no mediation rows


def _per_day(app, d):
    """{source: (matched, requests)} of one app on one day — the made-up values every expectation below is built from."""
    today = d == TODAY
    if app == "Demo Gallery":
        return {ADM: (40_000, 20_000 if today else 50_000), META: ((2_000, 16_000) if today else (8_000, 40_000)),
                ADM_WF: (5_000, 9_999), META_WF: (777, 7_777), OTHER: (100, 1_111)}       # the last three never count
    if app in ("Puzzle Quest", "Alpha Tools"):                                          # the same numbers: a tie
        return {ADM: (2_000, 1_000 if today else 3_000)}
    if app == "Tiny Notes":
        out = {}
        if d >= "2026-01-06":
            out[ADM] = (2_000, 800 if today else 2_500)
        if d >= "2026-01-08":
            out[META] = (0, 200 if today else 500)                                     # bids, never a win
        return out
    if app == "Echo Radio" and d >= "2026-01-07":                                       # Meta bidding only, no AdMob Network
        return {META: (100, 400) if today else (300, 1_200)}
    return {}


def _med():
    by_app = {}
    for app in APPS:
        srcs = {}
        for i, d in enumerate(AXIS):
            for k, (m, q) in _per_day(app, d).items():
                srcs.setdefault(k, []).append([i, REV[k], m // 2, m, q])
        if srcs:
            by_app[app] = srcs
    return {"dates": AXIS, "names": NAMES, "by_app": by_app, "currency": "USD"}


def _dash(roas=None):
    rows = [[d, 5_000_000, 2_000, 3_000, 2_500, 10] for d in AXIS]
    d = {"currency": "USD", "usd_inr": 90.0, "today_date": TODAY, "latest_complete": DAYS[-2],
         "generated_at": "2026-01-10T06:00:00Z", "apps_catalog": [], "app_icons": {}, "app_store_ids": {},
         "accounts": [], "known_accounts": ["pub-0000000000000001"],
         "apps": [{"name": n, "account": "pub-0000000000000001", "placements": 1, "revenue": 1.0, "avg_health": 70,
                   "platform": "Android", "ecpm": 1.0, "change_pct": 0, "at_risk": 0, "declining": 0,
                   "health_dist": [1, 0, 0]} for n in APPS],
         "alerts": {"counts": {"critical": 0, "warning": 0, "improving": 0}, "items": []},
         "movers": {"increasing": [], "decreasing": []}, "kpis": {"apps": len(APPS), "accounts": 1, "revenue": 0, "ecpm": 0},
         "placements": [{"id": "ca-app-pub-0000000000000001/%d" % (1000 + i), "name": "unit_%d" % i, "app": n, "daily": rows}
                        for i, n in enumerate(APPS)]}
    if roas is not None:
        d["roas"] = roas
    return d


W7 = AXIS[1:8]                                         # the page's "Last 7 days": its last 7 complete dates (2, 3, 5 … 9 Jan)
WINDOWS = {"y": ["2026-01-09"], "today": [TODAY], "w7": W7, "all": AXIS[:8]}
# by hand. Per day: Demo 50,000 AdMob / 40,000 Meta / 8,000 won (today 20,000 / 16,000 / 2,000); Puzzle and Alpha 3,000
# AdMob (today 1,000); Tiny 2,500 AdMob from 6 Jan and 500 Meta from 8 Jan, never won (today 800 / 200); Echo 1,200 Meta /
# 300 won from 7 Jan, no AdMob (today 400 / 100).
EXP = {
    "y": {"Demo Gallery": [50_000, 40_000, 8_000], "Puzzle Quest": [3_000, 0, 0], "Alpha Tools": [3_000, 0, 0],
          "Tiny Notes": [2_500, 500, 0], "Echo Radio": [0, 1_200, 300]},
    "today": {"Demo Gallery": [20_000, 16_000, 2_000], "Puzzle Quest": [1_000, 0, 0], "Alpha Tools": [1_000, 0, 0],
              "Tiny Notes": [800, 200, 0], "Echo Radio": [0, 400, 100]},
    "w7": {"Demo Gallery": [350_000, 280_000, 56_000], "Puzzle Quest": [21_000, 0, 0], "Alpha Tools": [21_000, 0, 0],
           "Tiny Notes": [10_000, 1_000, 0], "Echo Radio": [0, 3_600, 900]},
    "all": {"Demo Gallery": [400_000, 320_000, 64_000], "Puzzle Quest": [24_000, 0, 0], "Alpha Tools": [24_000, 0, 0],
            "Tiny Notes": [10_000, 1_000, 0], "Echo Radio": [0, 3_600, 900]},
}
TOT = {"y": [58_500, 41_700, 8_300], "today": [22_800, 16_600, 2_100], "w7": [402_000, 284_600, 56_900],
       "all": [458_000, 324_600, 64_900]}


def _bqu():
    """📡 Demo Gallery's ad units file (build_mediation_units' shape): every day of DAYS but GAP, made-up units / counts.
    Per day: Banner Home AdMob 10,000 (5,000 impr) · Meta 9,900 · Waterfall 3,000; Inter Exit AdMob 5,000 · Meta 3,000 ·
    Pangle 2,000 with no impression; Rewarded AdMob 4,000 only; Native Small AdMob 100 only; Splash Open AdMob 2,000 +
    its Waterfall 1,500 (AdMob's own lines only); Inter Boost AdMob 5,000 with no impression · Liftoff 6,500 (130%);
    WF Only the Waterfall line alone, 1,900; Round Edge AdMob 10,000 · Meta 7,960 (79.6%); Old Unit only on 1 Jan."""
    ds = [d for d in DAYS if d != GAP]
    every = lambda req, imp: [[i, req, imp] for i in range(len(ds))]
    return {"v": 1, "dates": ds,
            "names": {"ADM": "AdMob Network", "META": "Meta Audience Network (bidding)", "WF": "AdMob Network Waterfall",
                      "PNG": "Pangle ROW SDK (bidding)", "LIFT": "Liftoff Monetize (bidding)"},
            "units": {"u1": {"n": "Banner Home", "f": "BANNER", "s": {"ADM": every(10000, 5000), "META": every(9900, 100),
                                                                      "WF": every(3000, 500)}},
                      "u2": {"n": "Inter Exit", "f": "INTERSTITIAL", "s": {"ADM": every(5000, 2000), "META": every(3000, 900),
                                                                          "PNG": every(2000, 0)}},
                      "u3": {"n": "Rewarded", "f": "REWARDED", "s": {"ADM": every(4000, 3000)}},
                      "u4": {"n": "Native Small", "f": "NATIVE", "s": {"ADM": every(100, 80)}},
                      "u5": {"n": "Old Unit", "f": "BANNER", "s": {"ADM": [[0, 700, 600]]}},
                      "u6": {"n": "Splash Open", "f": "APP_OPEN", "s": {"ADM": every(2000, 1500), "WF": every(1500, 900)}},
                      "u7": {"n": "Inter Boost", "f": "INTERSTITIAL", "s": {"ADM": every(5000, 0), "LIFT": every(6500, 3000)}},
                      "u8": {"n": "WF Only", "f": "BANNER", "s": {"WF": every(1900, 600)}},
                      "u9": {"n": "Round Edge", "f": "BANNER", "s": {"ADM": every(10000, 4000), "META": every(7960, 500)}}}}


@pytest.fixture(scope="module")
def page_html():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def rep(tmp_path_factory, page_html):
    if NODE is None:
        pytest.skip("node is not installed")
    tmp = tmp_path_factory.mktemp("bidreq")
    fx = {"dash": _dash(), "dashAds": _dash({"configured": True, "by_app": {}, "unmatched_spend_usd": 0}), "med": _med(),
          "windows": WINDOWS, "gapIn": ["2026-01-03", GAP, "2026-01-05"], "other": OTHER,
          "apps": ["Demo Gallery", "Puzzle Quest", "Tiny Notes", "Echo Radio", "Quiet App"], "bqu": _bqu()}
    (tmp / "fx.json").write_text(json.dumps(fx))
    script = max(re.findall(r"<script>(.*?)</script>", page_html, re.S), key=len)
    (tmp / "app.js").write_text(script, encoding="utf-8")
    subprocess.run([NODE, "--check", str(tmp / "app.js")], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "bidreq_frontend.js"), str(tmp / "app.js"), str(tmp / "fx.json")],
                         check=True, capture_output=True, text=True, timeout=300,
                         env={**os.environ, "LC_ALL": "en_US.UTF-8"})   # toLocaleString() follows the locale (en_IN: 3,21,000)
    r = json.loads(out.stdout)
    assert r["errors"] == []
    return r["rep"]


def _n(n):
    """bqN by hand: 9,518 · 52.1k · 13.5M · 1.2B."""
    a = abs(n)
    return ("%.1fB" % (n / 1e9) if a >= 999_950_000 else "%.1fM" % (n / 1e6) if a >= 999_950 else
            "%.1fk" % (n / 1e3) if a >= 10_000 else format(n, ","))


def _pct(won, req):
    return "%.1f%%" % (won / req * 100) if req else "—"


# ── the sums ───────────────────────────────────────────────────────────────────────────────────
def test_the_period_sums_count_only_admob_network_and_meta_bidding(rep):
    for k, exp in EXP.items():
        got = rep["win"][k]
        assert got["ok"] is True, k
        assert got["apps"] == exp, k                       # waterfall lines, a third network, an app without rows: never in it
        assert got["t"] == TOT[k], k


def test_states_never_show_a_part_sum(rep):
    s = rep["states"]
    assert s["notYet"] == {"ok": False, "why": "load"} and s["loading"] == {"ok": False, "why": "load"}
    assert s["failed"] == {"ok": False, "why": "err"}
    assert s["empty"] == {"ok": False, "why": "none"} and s["noWin"] == {"ok": False, "why": "none"}
    assert s["before"] == {"ok": False, "why": "none"}     # a Period starting before the file: "—", not the part inside it
    assert s["after"] == {"ok": False, "why": "none"}
    assert s["gapIn"] == {"ok": False, "why": "none"}      # a Period day inside the file's range that it lacks: the same
    assert s["afterStale"] == {"ok": False, "why": "load"}         # the file of an older build: the new one is on its way
    assert s["afterStaleFailed"] == {"ok": False, "why": "err"}
    assert s["staleCovered"] == {"ok": True, "apps": EXP["y"], "t": TOT["y"]}   # an older file with every day: its numbers
    # …but never its last day (that build's partial day) as a whole one: on its way, or "couldn't load"
    assert s["staleLastDay"] == {"ok": False, "why": "load"} and s["staleLastDayFailed"] == {"ok": False, "why": "err"}
    assert s["staleWeek"] == {"ok": True, "apps": EXP["w7"], "t": TOT["w7"]}
    assert s["noSource"] == {"ok": False, "why": "src"}
    assert s["noMeta"] == {"ok": True, "apps": {"Demo Gallery": [50_000, 0, 0], "Puzzle Quest": [3_000, 0, 0],
                                                "Alpha Tools": [3_000, 0, 0], "Tiny Notes": [2_500, 0, 0]},
                           "t": [58_500, 0, 0]}            # no Meta source at all: AdMob still counts, Echo has nothing left
    assert s["namesCase"] == {"ok": True, "apps": EXP["y"], "t": TOT["y"]}      # AdMob's names, any case / spacing


def test_the_cache_never_answers_for_another_file_or_period(rep):
    c = rep["cache"]
    assert c["first"] == TOT["y"] and c["again"] == TOT["y"]
    assert c["other"] == [58_500, 40_000, 8_000]           # 6 Jan: no Tiny / Echo Meta yet
    assert c["newFile"] == [117_000, 83_400, 16_600]       # a new file (requests and wins doubled), the same Period


def test_counts_and_rates_read_short(rep):
    assert rep["fmt"] == ["0", "7", "9,999", "9,999", "10.0k", "52.1k", "999.9k", "1.0M", "1.2M", "999.9M", "1.0B", "9.3B",
                          "—", "0.0%", "33.3%", "100.0%"]


# ── the tiles ──────────────────────────────────────────────────────────────────────────────────
def _tile(h):
    m = re.match(r'<div class="card kpi mk-kpi" data-mk="(meta|admob)" title="([^"]*)">'
                 r'<div class="l">([^<]*)</div><div class="v[^"]*">([^<]*)</div><div class="d muted">([^<]*)</div></div>$', h, re.S)
    assert m, h
    kind, title, label, v, d = m.groups()
    return {"kind": kind, "title": H.unescape(title), "label": label, "v": v, "d": d}


# by hand, USD per app-day: AdMob (ADM 20 + ADM_WF 5) Demo 25, Puzzle 20, Alpha 20, Tiny 20 (from 6 Jan); Meta (META 12 only)
# Demo 12, Tiny 12 (from 8 Jan), Echo 12 (from 7 Jan). META_WF (3) and OTHER (40) never count.
REVT = {"y": (85, 36), "today": (85, 36), "w7": (535, 144), "all": (600, 156)}
TIP_MIDDLE = " ki Estimated earnings — AdMob report ka “Estimated earnings” column, upar wale Period me. Revenue tile me ye shamil hai (Revenue = saare networks)."


def test_all_apps_tiles_by_period(rep):
    for r, w in (("today", "today"), ("yesterday", "y"), ("7d", "w7"), ("all", "all")):
        x = rep["tiles"]["all|" + r]
        assert x["win"] == WINDOWS[w], r
        meta, adm = (_tile(h) for h in x["t"])
        assert meta["label"] == "Meta revenue" and adm["label"] == "AdMob revenue"
        assert meta["v"] == "$%d" % REVT[w][1] and adm["v"] == "$%d" % REVT[w][0], r
        assert meta["d"] == "Meta (bidding) · " + x["label"] and adm["d"] == "AdMob + Waterfall · " + x["label"], r
        assert meta["title"] == "Meta Audience Network (bidding)" + TIP_MIDDLE + "\n$%d.00" % REVT[w][1], r
        assert adm["title"] == "AdMob Network + AdMob Network Waterfall" + TIP_MIDDLE + "\n$%d.00" % REVT[w][0], r
    assert rep["tiles"]["all|7d"]["label"].endswith("7d")


def test_an_apps_tiles_are_its_own_numbers_and_no_button(rep):
    want = {"Demo Gallery": ("$84", "$175"), "Puzzle Quest": ("—", "$140"), "Tiny Notes": ("$24", "$80"),
            "Echo Radio": ("$36", "—"), "Quiet App": ("—", "—")}
    for app, (mv, av) in want.items():
        x = rep["tiles"]["app|" + app]
        meta, adm = (_tile(h) for h in x["t"])
        assert (meta["v"], adm["v"]) == (mv, av), app
        assert meta["d"] == ("Meta (bidding)" if mv != "—" else "no Meta") + " · " + x["label"], app
        assert adm["d"] == ("AdMob + Waterfall" if av != "—" else "no AdMob") + " · " + x["label"], app
        for h in x["t"]:
            assert "onclick" not in h and "<button" not in h and "mk-hint" not in h and "mk-tap" not in h
        assert "\n$" not in (meta["title"] if mv == "—" else "") + (adm["title"] if av == "—" else "")   # no amount without rows
    assert "\n$84.00" in _tile(rep["tiles"]["app|Demo Gallery"]["t"][0])["title"]


def test_in_inr_the_tiles_convert_at_the_dashboards_rate(rep):
    meta, adm = (_tile(h) for h in rep["inr"]["t"])
    assert rep["inr"]["sym"] == "₹"
    assert adm["v"] == "₹48,150" and meta["v"] == "₹12,960"          # 535 × 90 and 144 × 90
    assert "\n$535.00" in adm["title"] and "\n$144.00" in meta["title"]   # the title keeps the exact USD


def test_tiles_while_loading_failed_or_empty(rep):
    for k, v, why in (("loading", "…", None), ("failed", "—", "couldn't load"), ("empty", "—", "no mediation data")):
        x = rep["tiles"][k]
        meta, adm = (_tile(h) for h in x["t"])
        assert meta["v"] == v and adm["v"] == v, k
        if why is None:      # loading: the same caption as with the numbers — the tile never changes size when they land
            assert meta["d"] == "Meta (bidding) · " + x["label"] and adm["d"] == "AdMob + Waterfall · " + x["label"]
        else:
            assert meta["d"] == why + " · " + x["label"] and adm["d"] == why + " · " + x["label"], k
        assert "\n$" not in meta["title"] + adm["title"]
    x = rep["tiles"]["noSource"]                                    # a file with no "AdMob Network" source
    assert [_tile(h)["v"] for h in x["t"]] == ["—", "—"] and _tile(x["t"][0])["d"] == "no AdMob Network source · " + x["label"]


def test_the_tiles_on_the_page_take_their_numbers_in_place(rep):
    p = rep["repaint"]
    assert p["meta"] == p["want"][0] and p["admob"] == p["want"][1]
    assert _tile(p["meta"])["v"] == "$36" and _tile(p["admob"])["v"] == "$85"


def test_overview_row_swaps_the_two_bid_tiles_for_revenue_in_the_same_place(rep):
    o = rep["overview"]
    assert o["dash"] == {"cls": "c6", "labels": ["Revenue", "Avg eCPM", "Match rate", "Meta revenue", "AdMob revenue",
                                                 "Apps · Accounts"], "mk": 2}
    assert o["dashAds"] == {"cls": "c11", "labels": ["Revenue", "Ad spend", "Profit / Loss", "Google Ads installs",
                                                     "New revenue", "Old revenue", "Avg eCPM", "Match rate", "Meta revenue",
                                                     "AdMob revenue", "Apps · Accounts"], "mk": 2}


# ── the list ───────────────────────────────────────────────────────────────────────────────────
def _rows(h):
    body = re.search(r"<tbody>(.*?)</tbody>", h, re.S).group(1)
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        tds = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        nm = re.search(r"<span>([^<]*)</span></span>$", tds[0][1])
        name = nm.group(1) if nm else TAG.sub("", tds[0][1]).strip()
        out.append([name] + [(TAG.sub("", t).strip(), H.unescape((re.search(r'title="([^"]*)"', a) or [None, ""])[1]))
                             for a, t in tds[1:]])
    return out


def _cells(a, m, wn):
    return [(_n(a), format(a, ",")) if a else ("—", ""), (_n(m), format(m, ",")) if m else ("—", ""),
            (_pct(wn, m), "%s won of %s" % (format(wn, ","), format(m, ","))) if m else ("—", "")]


def test_list_rows_most_admob_requests_first_all_apps_last(rep):
    for r, w in (("yesterday", "y"), ("7d", "w7"), ("all", "all")):
        rows = _rows(rep["list"][r])
        exp = sorted(EXP[w].items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))   # a tie: more Meta, then the name
        assert [x[0] for x in rows] == [a for a, _ in exp] + ["All apps"], r
        for (app, v), row in zip(exp + [("All apps", TOT[w])], rows):
            assert row[1:] == _cells(*v), (r, app)
    rows = _rows(rep["list"]["7d"])
    assert [x[0] for x in rows] == ["Demo Gallery", "Alpha Tools", "Puzzle Quest", "Tiny Notes", "Echo Radio", "All apps"]
    assert rows[4][1:] == [("—", ""), ("3,600", "3,600"), ("25.0%", "900 won of 3,600")]       # Meta only: AdMob "—"
    assert rows[5][1:] == [("402.0k", "402,000"), ("284.6k", "284,600"), ("20.0%", "56,900 won of 284,600")]
    h = rep["list"]["7d"]
    assert "<th>App</th>" in h and ">AdMob req</th>" in h and ">Meta bid req</th>" in h and "Meta won %<span class=\"bq-s\">won ÷ bid req</span></th>" in h
    assert 'onclick="bqClose()">← Overview</span>' in h and '<div class="card pad0 bq-full">' in h
    assert '<tr class="dw-tot"><td class="nm">All apps</td>' in h


def test_list_follows_an_app_picked_in_the_header(rep):
    h = rep["list"]["app|Tiny Notes"]
    assert [x[0] for x in _rows(h)] == ["Tiny Notes"] and "dw-tot" not in h       # that app's row only, no All apps row
    assert _rows(h)[0][1:] == _cells(10_000, 1_000, 0)
    assert re.search(r"</b> · <[^>]*>.*Tiny Notes\. Period upar se badlo\.", h)   # the header names the app
    q = rep["list"]["app|Quiet App"]
    assert "Is period me is app ki koi bid request nahi." in q and "dw-tot" not in q


def test_list_states(rep):
    L = rep["list"]
    assert "⏳ Mediation data load ho raha hai…" in L["loading"] and "<table" not in L["loading"]
    assert "Mediation data load nahi hua — page refresh karo." in L["failed"]
    assert "Is period ka mediation data nahi — Period badal ke dekho." in L["empty"]
    assert "Mediation data me “AdMob Network” source nahi mila." in L["noSource"]
    assert "Is period me koi bid request nahi." in L["noRows"] and "dw-tot" not in L["noRows"]   # data, but no bid request
    for k in ("loading", "failed", "empty", "noSource", "noRows"):
        assert 'onclick="bqClose()">← Overview</span>' in L[k], k


# ── the loader and the screen ──────────────────────────────────────────────────────────────────
def test_one_fetch_for_every_caller_and_a_new_build_fetches_again(rep):
    o = rep["loader"]
    assert o["inFlight"] == {"calls": 1, "waiting": 2, "loading": True}
    assert o["landed"] == {"calls": 1, "n": {"a": 1, "b": 1}, "medb": "2026-01-10T06:00:00Z", "build": "2026-01-10T06:00:00Z",
                           "err": False, "waiting": 0}
    assert o["cached"] == {"calls": 1, "n": {"a": 2, "b": 1}}
    assert o["newBuildCalls"] == 2 and o["newBuild"] == {"calls": 2, "n": {"a": 2, "b": 2}, "medb": "2026-01-10T07:00:00Z"}
    # a failure: the caller still hears back (a tile never stays on "…"), the last good file stays, the next ask tries again
    assert o["failed"] == {"calls": 3, "n": {"a": 3, "b": 2}, "err": True, "kept": len(AXIS), "medb": "2026-01-10T07:00:00Z",
                           "loading": False}
    assert o["retry"] == {"calls": 4, "n": {"a": 3, "b": 3}, "err": False, "medb": "2026-01-10T08:00:00Z"}
    # a newer build while the file was on its way: fetched once more, the caller answered once, with the newer build's
    assert o["race"] == {"fetches": 2, "n": {"a": 4, "b": 3}, "medb": "2026-01-10T10:00:00Z", "loading": False, "waiting": 0}
    assert o["missing"] == {"calls": 7, "dates": 0, "err": False}      # no file: an empty one, as the Mediation tab had it


def test_the_overview_fetches_the_file_only_when_it_is_on_screen(rep):
    f = rep["ovFetch"]
    assert f["onOverview"] == {"calls": 1, "med": True}
    assert f["passThrough"] == {"calls": 0, "med": False}  # render() passes through show('overview') before the real screen
    assert f["showList"] == {"rows": 5, "total": True, "calls": 0}      # show('bidreq'): the list, from the file in hand


def test_the_screen_is_wired_like_the_other_drill_pages(rep):
    assert rep["wiring"] == {"title": ["Bid requests", "AdMob · Meta (bidding) · har app"], "drill": "overview", "render": True}
    s = rep["screen"]
    assert s["open"] == {"shown": "bidreq", "steps": "bidreq"}         # a tile's tap: the list, and phone Back's step
    assert s["undo"] == "overview"
    assert s["close"] == {"shown": "overview", "steps": ""}            # "← Overview": the step goes with it
    assert s["left"] == ""                                              # left by the menu: the step goes too
    assert s["hubSteps"] == "bidreq"  # ✨ hub too (the hub rewrites the URL of the step Back lands on)
    assert s["paintFirst"] is True and s["paintAfter"] is True          # "load ho raha hai", then the rows once the file is in


# ── the layout ─────────────────────────────────────────────────────────────────────────────────
def test_eleven_tiles_wrap_into_balanced_rows(page_html):
    css = page_html[page_html.index("<style>"):page_html.index("</style>")]
    base = ".c11{grid-template-columns:repeat(6,minmax(0,1fr))}"
    mid = "@media(max-width:1387px){.c11{grid-template-columns:repeat(4,minmax(0,1fr))}}"
    low = "@media(max-width:1000px){.c11{grid-template-columns:repeat(3,minmax(0,1fr))}}"
    assert css.index(base) < css.index(mid) < css.index(low)            # 6+5 → 4+4+3 → 3+3+3+2
    phone = css[css.index("@media(max-width:760px){"):]
    assert ".ov-kpi.row.c11{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}" in phone
    assert ".ov-kpi.row.c11>.kpi:nth-child(11){grid-column:1/-1}" in phone   # 2-up, the 11th on its own row
    assert ".mk-kpi .v{min-height:calc(var(--vmax,24px)*1.5)}" in css       # "…" → the number: the same height
    assert ".card.pad0.bq-full table{min-width:0}" in phone                  # the list fits a phone



def test_an_apps_ad_units_each_network_and_the_three_marks(rep):
    """Yesterday (9 Jan) by hand: AdMob 36,100 requests in all; columns by each network's requests (Meta 20,860, Liftoff
    6,500, Waterfall 6,400, Pangle 2,000); rows by AdMob's (a tie by name). Amber: Meta 60% on Inter Exit, Liftoff 130%
    on Inter Boost (either way); not Meta 7,960 of 10,000 on Round Edge — 79.6% reads 80%, the mark follows the % as
    printed. Red "0 impr": AdMob's own 5,000 on Inter Boost, Pangle 2,000 on Inter Exit. The Waterfall shows requests,
    never a %. "Mediation nahi" (AdMob's own lines only): Rewarded (11% of the app's AdMob requests), Splash Open (5.5%)
    and WF Only (the Waterfall line alone, no AdMob bidding: its 1,900 = 5.3%) red, Native Small (0.3%) light."""
    u = rep["units"]
    assert u["heads"] == ["AdMob|req", "Meta|req · % of AdMob", "Liftoff Monetize|req · % of AdMob", "AdMob Waterfall|req",
                          "Pangle ROW SDK|req · % of AdMob"]
    assert u["rows"] == [["Banner Home banner", "10.0k", "9,900 99%", "—", "3,000", "—"],
                         ["Round Edge banner", "10.0k", "7,960 80%", "—", "—", "—"],
                         ["Inter Boost interstitial", "5,000 0 impr", "—", "6,500 130%", "—", "—"],
                         ["Inter Exit interstitial", "5,000", "3,000 60%", "—", "—", "2,000 40% 0 impr"],
                         ["Rewarded rewarded Mediation nahi", "4,000", "—", "—", "—", "—"],
                         ["Splash Open app open Mediation nahi", "2,000", "—", "—", "1,500", "—"],
                         ["Native Small native Mediation nahi", "100", "—", "—", "—", "—"],
                         ["WF Only banner Mediation nahi", "—", "—", "—", "1,900", "—"]]
    assert u["cls"] == ["bqu-dead", "bqu-gap", "bqu-gap", "bqu-dead"] and u["chips"] == [True, True, False, True]
    assert u["sum"] == "⚠️ Mediation nahi: 4 (3 bade) | Request farak: 2 | 0 impression: 2 |" and u["note"]


def test_the_ad_units_card_states_and_the_tap_into_an_app(rep):
    u = rep["units"]
    assert u["loading"] and u["failed"] and u["noPointer"] and u["gapPeriod"] and u["nothing"]
    assert u["allTap"] and u["appNoTap"]           # All apps: a row opens its app; an app's own row is no button


def test_the_ad_units_file_a_newer_build_wins_and_a_failure_says_so(rep):
    """Two builds' requests in flight: the older one's answer lands last and is dropped (the newer one's stays); a failed
    fetch is "err" (the card says it could not load). Each request asks for its own build (?b=)."""
    b = rep["bquLoad"]
    assert b["urls"] == ["bqu_x.json.gz?b=B1", "bqu_x.json.gz?b=B2"]
    assert b["kept"] == {"b": "B2", "st": "ok", "tag": "new"} and b["cb"] == 2
    assert b["failed"] == {"b": "B3", "st": "err"}


def test_the_hub_keeps_the_bid_requests_screen_when_the_app_changes(rep):
    """A row tap / the header's pick on the list keeps the list (the app's ad units). A hub step that set its own tab
    (another tab, the ← out to All apps' Overview, Back / Forward) lands on that tab's page, not on the list."""
    h = rep["hubApp"]
    assert h["onBid"] == ["bidreq"] and h["elsewhere"] and h["elsewhere"] != ["bidreq"]
    assert h["goRev"]["want"] and h["goRev"]["shown"] == [h["goRev"]["want"]] and h["goRev"]["tab"] == "revenue"
    assert h["goOv"]["want"] and h["goOv"]["shown"] == [h["goOv"]["want"]] and h["goOv"]["want"] != "bidreq"


def test_a_networks_bidding_and_waterfall_lines_never_share_a_name(rep):
    assert rep["bquNames"] == ["Meta", "Meta (waterfall)", "AdMob Waterfall", "AdMob Network", "AppLovin", "AppLovin (waterfall)"]

