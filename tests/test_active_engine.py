"""Active users (admob_iq.engine.active) — the "👥 Active users" tab's engine, on synthetic GA4 stores whose numbers add up
like GA4's (tests.uninstall_synth.make_active_store: an AR(1) old-user level, a weekday pattern, HLL noise, installs,
usage / return cohorts / revenue on or off, mediation, tiny apps). Every number the owner sees is a ratio of sums over
known days, unknown is null (never 0), provisional days are never judged, ad-spend swings are never blamed on old users,
the first evaluation / a new input / a moved stream never floods, and the uninstall detail it reads is never changed.
All data is made up."""

import copy
import json
import re
import time
from datetime import date, timedelta

from admob_iq.engine import active as act
from admob_iq.engine import uninstall as eng
from tests.uninstall_synth import DEFAULT_RET, END, active_udet, make_active_store, rollout

S = END - timedelta(days=act.ACT_LATE_DAYS)             # the last settled activity day of END
NOW = "2026-09-21T01:00:00Z"
KEY = "0123456789ab"
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ST = ("worse", "watch", "slow", "break", "better", "maybe_dn", "maybe_up", "normal", "price_dn", "price_up", "growth",
      "low", "noad", "wait")
WHY = (None, "mix", "installs", "steep", "young", "null_short", "gap", "few", "wait", "noad", "ads_dir")


# ── the contract (§3) ────────────────────────────────────────────────────────────────────────────

def _keys(obj, keys, where):
    assert isinstance(obj, dict), where
    assert set(obj) == set(keys), "%s: %s" % (where, sorted(set(obj) ^ set(keys)))


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


M_KEYS = ("v", "base", "all", "rel", "pp", "z", "usual", "st", "why", "est", "n", "nb", "from", "to", "bfrom", "bto", "s")
ALERT_KEYS = ("id", "source", "app_id", "app", "family", "metric", "also", "dir", "severity", "unit", "now", "before",
              "rel", "delta_pp", "z", "since", "day", "installs_from", "installs_to", "base_from", "base_to", "users",
              "opened", "last_seen", "fresh", "notify", "provisional", "estimate", "tags", "release", "linked",
              "data_till", "text", "message")


def check_m(M, where, row=False):
    keys = [k for k in M_KEYS if not (row and k in ("from", "to", "bfrom", "bto", "all", "pp"))]
    _keys(M, keys, where)
    assert M["st"] in ST and M["why"] in WHY, (where, M["st"], M["why"])
    assert isinstance(M["est"], bool) and isinstance(M["n"], int) and isinstance(M["nb"], int)
    for k in ("v", "base", "all", "rel", "pp", "z", "usual"):
        assert M.get(k) is None or _num(M[k]), (where, k)
    assert M["s"] is None or (len(M["s"]) == 4 and all(_num(x) for x in M["s"]))


def check_alert(a, closed=False):
    _keys(a, ALERT_KEYS + (("closed",) if closed else ()), "alert")
    assert a["source"] == "active" and a["family"] in ("act_drift", "act_slow", "act_spike", "act_break", "act_return")
    assert a["metric"] in ("ret_dau", "usage", "sess", "time", "ads", "d1", "d3", "d7", "d14", "d30")
    assert a["dir"] in ("up", "down") and a["severity"] in ("warning", "watch", "good")
    assert (a["severity"] == "good") == (a["dir"] == "up")          # Active: down = worse
    assert a["unit"] in ("users", "num", "sec", "pp", "per1k") and a["provisional"] is False
    assert a["id"].startswith(a["app_id"] + "|active_" + a["family"] + "_")
    assert a["message"] == a["app"] + ": " + a["text"]
    assert re.search("[%s-%s]" % (chr(0x900), chr(0x97F)), a["message"]) is None
    assert set(a["tags"]) <= {"installs", "mix", "market_wide", "update", "time"}
    assert (a["release"] is None) == ("update" not in a["tags"])
    assert isinstance(a["linked"], bool) and (a["release"] is not None or not a["linked"])   # linked: an update's
    for k in ("opened", "last_seen", "data_till"):
        assert _ISO.match(a[k])


def check_detail(d, row=None):
    _keys(d, ("v", "app_id", "app", "key", "tz", "rev_tz", "currency", "history_start", "data_till", "settled_till",
              "act_late_days", "fetched_at", "stale", "launch", "stage", "stage_why", "zoom", "releases", "edges",
              "flags", "daily", "bands", "steep", "tiles", "ctx", "latest", "split", "inst", "summary", "changes",
              "tri", "versions", "versions_more", "impact"), "detail")
    H = (date.fromisoformat(d["data_till"]) - date.fromisoformat(d["history_start"])).days + 1
    assert (date.fromisoformat(d["data_till"]) - date.fromisoformat(d["settled_till"])).days == d["act_late_days"] == 3
    _keys(d["flags"], ("tz_blend", "rev_est", "usage_split", "vuse_split", "ret_short", "ret_bad0", "ret_empty",
                       "thresholded", "gap_g", "inc_days", "rneg_days", "other_share"), "flags")
    _keys(d["edges"], ("hist", "ret_from", "ret_oldest", "ret_state", "ret_short", "usage_from", "usage_state",
                       "usage_split", "rev_from", "rev_to", "rev_gaps", "rev_state", "ga4_trunc", "edge_why", "text"),
          "edges")
    assert d["edges"]["ret_state"] in ("wait", "searching", "found", "whole", "unverified")
    assert d["edges"]["usage_state"] in ("wait", "ok", "partial") and d["edges"]["edge_why"] in ("retention", "ga4")
    dl = d["daily"]
    _keys(dl, ("start", "a1", "new", "ret", "y", "old", "oq", "old_k", "u", "s", "t", "rev", "imp", "breaks", "inc",
               "rneg", "rev_gaps", "coh"), "daily")
    for k in ("a1", "new", "ret", "y", "old", "oq", "rev", "imp"):
        assert len(dl[k]) == H, k
    for g in ("u", "s", "t"):
        assert all(len(dl[g][k]) == H for k in "nro")
    _keys(dl["coh"], ("t", "d1", "d3", "d7", "d14", "d30", "ok"), "coh")
    assert all(len(v) == H for v in dl["coh"].values())
    assert all(r is None or r > 0 for r in dl["ret"])                    # returning users: never ≤ 0
    assert all(q in (None, 1, 2) for q in dl["oq"])
    _keys(d["bands"], ("ret_dau", "sess", "time", "ads", "arpdau"), "bands")
    for b in d["bands"].values():
        _keys(b, ("med", "lo", "hi"), "band")
        assert all(len(v) == H for v in b.values())
        assert all(lo is None or (lo <= m <= hi) for lo, m, hi in zip(b["lo"], b["med"], b["hi"]))
    _keys(d["tiles"], ("ret_dau", "d1", "d7", "sess", "time", "arpdau", "ads", "ecpm"), "tiles")
    for k, M in d["tiles"].items():
        check_m(M, k)
    _keys(d["ctx"], ("a1", "new", "old", "old_est"), "ctx")
    _keys(d["latest"], ("day", "ret_dau", "a1", "prov"), "latest")
    assert d["latest"]["prov"] is True and d["latest"]["day"] == d["data_till"]
    _keys(d["summary"], ("kind", "text"), "summary")
    assert d["summary"]["kind"] in ("worse", "break", "watch", "slow", "better", "maybe", "ok", "wait")
    ch = d["changes"]
    _keys(ch, ("open", "closed", "info", "older"), "changes")
    for a in ch["open"]:
        check_alert(a)
    for a in ch["closed"]:
        check_alert(a, closed=True)
    for i in ch["info"]:
        _keys(i, ("kind", "metric", "dir", "from", "to", "rel", "text", "tags", "prov"), "info")
        assert i["kind"] in ("price", "installs", "market_wide", "early") and i["prov"] == (i["kind"] == "early")
    for o in ch["older"]:
        _keys(o, ("kind", "metric", "dir", "from", "to", "before", "now", "rel", "z", "release", "text"), "older")
        assert o["from"] <= o["to"] <= d["settled_till"]
    t = d["tri"]
    _keys(t, ("src", "cols", "cols_phone", "nmax", "stage", "label", "from", "edge", "ref", "ref_users", "ref_thin",
              "avg4", "rows"), "tri")
    assert t["src"] == "ga4_return" and all(1 <= N <= t["nmax"] <= 30 for N in t["cols"])
    assert all(len(t[k]) == 31 and t[k][0] is None for k in ("ref", "ref_users", "ref_thin"))
    for r in t["rows"]:
        _keys(r, ("week", "from", "to", "users", "days", "v", "prov", "heat", "part", "pre", "q", "nodata"), "row")
        assert all(len(r[k]) == 31 and r[k][0] is None for k in ("v", "prov", "heat"))
        for N in range(1, 31):
            assert not ((r["prov"][N] or r["part"] or r["nodata"]) and r["heat"][N])   # never coloured
    for v in d["versions"] + d["versions_more"]:
        _keys(v, ("ver", "kind", "from", "to", "share", "users", "sess", "time", "vs"), "version")
    text = json.dumps(d, ensure_ascii=False)
    assert re.search("[%s-%s]" % (chr(0x900), chr(0x97F)), text) is None           # Roman Hinglish only
    assert "NaN" not in text and "Infinity" not in text
    if row is not None:
        check_row(row)


def check_row(row):
    _keys(row, ("app_id", "app", "key", "file", "sig", "status", "data_till", "settled_till", "stale", "stage",
                "launch_day", "ready", "edges", "win", "m", "ctx", "latest", "alerts", "summary"), "row")
    _keys(row["edges"], ("hist", "ret_from", "ret_state", "usage_from", "usage_state", "rev_from", "rev_state"), "redges")
    _keys(row["win"], ("from", "to", "bfrom", "bto"), "win")
    _keys(row["m"], ("ret_dau", "d1", "d7", "sess", "time", "arpdau", "ads", "ecpm"), "m")
    for k, M in row["m"].items():
        check_m(M, k, row=k in act.WIN_METRICS)
    assert len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 2560   # ≤ 2.5 KB


# ── helpers ──────────────────────────────────────────────────────────────────────────────────────

def run(st, rv=None, E=END, astate=None, ustate=None, now=NOW, aid="a", app="App", mkt=None, cfg=None, outdated=False,
        udet_fn=None):
    """The uninstall evaluation then the Active one at data end E → (detail, row, active state, uninstall state, udet)."""
    s = dict(st, window_end=E.isoformat())
    ustate = {} if ustate is None else ustate
    astate = {} if astate is None else astate
    udet, _ = eng.evaluate_app(s, aid, app, ustate, now, revenue=rv)
    if udet_fn:
        udet = udet_fn(udet)
    d, row = act.evaluate(s, aid, app, astate, now, udet, KEY, rv, mkt, outdated=outdated, cfg=cfg)
    check_detail(d, row)
    return d, row, astate, ustate, udet


def daily(st, rv, first, last, astate=None, ustate=None, **kw):
    """The daily build from `first` to `last`: every due alert marked sent after each run → (sent, last detail, states)."""
    astate = {} if astate is None else astate
    ustate = {} if ustate is None else ustate
    sent, E, d = [], first, None
    while E <= last:
        d, row, astate, ustate, _ = run(st, rv, E, astate, ustate, now=E.isoformat() + "T12:00:00Z", **kw)
        for a in d["changes"]["open"]:
            if a["notify"]:
                sent.append((E.isoformat(), a["family"], a["metric"], a["dir"], a["severity"]))
                for ep in astate["episodes"].values():
                    if ep["id"] == a["id"]:
                        ep["notified_at"] = E.isoformat() + "T12:00:00Z"
        E += timedelta(days=1)
    return sent, d, astate, ustate


def quiet(**kw):
    """A big, quiet established app (1% AR(1) level noise, 1% HLL)."""
    kw = dict(dict(days=400, noise=0.01, hll=0.01, seed=1), **kw)
    return make_active_store(**kw)


def settle(st, rv, E, astate, ustate, days=4, **kw):
    """The daily builds of the `days` days up to E (a drift needs DRIFT_PERSIST advanced evaluations), nothing marked
    sent → the last detail."""
    d = None
    for k in range(days, -1, -1):
        d, *_ = run(st, rv, E - timedelta(days=k), astate, ustate, **kw)
    return d


def opened(d):
    return [(a["family"], a["metric"], a["dir"], a["severity"]) for a in d["changes"]["open"]]


# ── 1. returning users, unknown days, the whole history ──────────────────────────────────────────

def test_returning_is_a1_minus_new_over_whole_history():
    st, rv = quiet(days=300)
    d, row, *_ = run(st, rv)
    dl = d["daily"]
    assert dl["start"] == st["history_start"] and len(dl["ret"]) == 300
    for i, day in enumerate(sorted(st["daily"])):
        r = st["daily"][day]
        assert dl["a1"][i] == r["a1"] and dl["new"][i] == r["new"] and dl["ret"][i] == r["a1"] - r["new"]
    assert d["tiles"]["ret_dau"]["s"][0] == sum(dl["ret"][-10:-3])        # the 7 settled days, pooled
    assert d["ctx"]["a1"] and d["ctx"]["new"] and d["ctx"]["old"]         # context: DAU, installs, 30+ days old


def test_returning_null_when_new_reaches_active():
    bad = S - timedelta(days=2)                                          # a settled day inside the tile window
    st, rv = quiet(a1={bad: 480})                                        # 480 active, 500 new that day
    d, row, *_ = run(st, rv)
    i = (bad - date.fromisoformat(d["history_start"])).days
    assert d["daily"]["ret"][i] is None and bad.isoformat() in d["daily"]["rneg"]
    assert d["flags"]["rneg_days"] == 1 and d["daily"]["a1"][i] == 480 and d["daily"]["new"][i] == 500
    t = d["tiles"]["ret_dau"]
    assert t["n"] == 6 and t["s"][1] == 6                                # "6 of 7 days": left out, counted
    assert t["s"][0] == sum(r for r in d["daily"]["ret"][-10:-3] if r is not None)
    assert all(x is None for x in (d["bands"]["ret_dau"]["med"][i],)) or d["bands"]["ret_dau"]["med"][i] > 0


def test_unknown_days_are_null_never_zero():
    st, rv = quiet(days=200)
    gone = (END - timedelta(days=50)).isoformat()
    del st["daily"][gone]                                                # GA4 never returned that day
    del st["usage"][gone]
    d, *_ = run(st, rv)
    i = (date.fromisoformat(gone) - date.fromisoformat(d["history_start"])).days
    assert d["daily"]["a1"][i] is None and d["daily"]["new"][i] is None and d["daily"]["ret"][i] is None
    assert all(d["daily"][g]["r"][i] is None for g in ("u", "s", "t"))
    zero = (END - timedelta(days=40)).isoformat()                        # no usage read that day either
    st2 = copy.deepcopy(st)
    del st2["usage"][zero]
    d2, *_ = run(st2, rv)
    j = (date.fromisoformat(zero) - date.fromisoformat(d2["history_start"])).days
    assert d2["daily"]["s"]["r"][j] is None and d2["daily"]["a1"][j] is not None


def test_revenue_gap_is_null_not_zero():
    st, rv = quiet(days=300, tz="Asia/Kolkata", rev_tz="America/Los_Angeles")
    hole = [(END - timedelta(days=k)).isoformat() for k in range(60, 70)]
    for k in hole:
        del rv["days"][k]                                                # AdMob has no rows those days
    d, row, *_ = run(st, rv)
    hs = date.fromisoformat(d["history_start"])
    idx = [(date.fromisoformat(k) - hs).days for k in hole]
    assert all(d["daily"]["rev"][i] is None and d["daily"]["imp"][i] is None for i in idx)    # never 0
    assert all(d["daily"]["rev"][i] is None for i in (idx[0] - 1, idx[-1] + 1))  # blended days touching it: unknown
    assert d["edges"]["rev_gaps"] == d["daily"]["rev_gaps"] and len(d["edges"]["rev_gaps"]) == 1
    g = d["edges"]["rev_gaps"][0]
    assert g[0] <= hole[0] and g[1] >= hole[-1]
    assert d["edges"]["rev_state"] == "partial" and any("No ad data" in t for t in d["edges"]["text"])
    assert d["flags"]["tz_blend"] and d["tiles"]["arpdau"]["est"]
    assert not [a for a in d["changes"]["open"] if a["metric"] == "ads"]
    assert not [o for o in d["changes"]["older"] if o["metric"] == "ads"]
    none, *_ = run(st, None)                                             # no AdMob at all: wait, never 0
    assert none["tiles"]["arpdau"]["st"] == "wait" and all(v is None for v in none["daily"]["rev"])
    assert none["edges"]["rev_state"] == "none"


def test_per_user_values_are_ratio_of_sums():
    st, rv = quiet(days=200)
    days = sorted(st["usage"])[-10:-3]                                   # the tile's 7 settled days
    for j, k in enumerate(days):                                         # one huge day with few sessions per user,
        u = st["usage"][k]["r"]                                          # the rest many: the mean of ratios differs
        if j == 0:
            st["usage"][k]["r"] = [u[0] * 4, u[0] * 4 * 1, u[0] * 4 * 100]
            st["daily"][k]["a1"] = st["daily"][k]["new"] + u[0] * 4 + st["usage"][k]["o"][0]
    d, *_ = run(st, rv)
    t = d["tiles"]["sess"]
    su = [st["usage"][k]["r"] for k in days]
    ratio_of_sums = sum(x[1] for x in su) / sum(x[0] for x in su)
    mean_of_ratios = sum(x[1] / x[0] for x in su) / len(su)
    assert abs(t["v"] - ratio_of_sums) < 1e-3 * ratio_of_sums and abs(ratio_of_sums - mean_of_ratios) > 0.1
    assert t["s"][:2] == [sum(x[1] for x in su), sum(x[0] for x in su)]
    tt = d["tiles"]["time"]
    assert abs(tt["v"] - sum(x[2] for x in su) / sum(x[0] for x in su)) < 1e-3 * tt["v"]


# ── 2. what changed: drift, spikes, breaks, slow ────────────────────────────────────────────────

def test_steady_app_is_all_normal_with_no_alerts():
    st, rv = quiet()
    d, row, *_ = run(st, rv)
    assert {k: t["st"] for k, t in d["tiles"].items() if k != "ecpm"} == dict.fromkeys(
        ("ret_dau", "d1", "d7", "sess", "time", "arpdau", "ads"), "normal")
    assert d["changes"]["open"] == [] and d["summary"]["kind"] == "ok"
    assert d["summary"]["text"] == "✅ Sab normal — purane users, wapsi, time aur revenue apni normal range me."
    assert row["alerts"] == {"warning": 0, "watch": 0, "good": 0}


def test_slow_drift_opens_drift():
    drop = S - timedelta(days=9)                                         # old users −10% for 10 settled days …
    back = drop + timedelta(days=14)                                     # … then back to normal
    st, rv = quiet(old=lambda d: 20000 * (0.9 if drop <= d < back else 1.0))
    st = dict(st)
    sent, d, ast, _ = daily(st, rv, END - timedelta(days=12), END)
    assert [x[1:] for x in sent] == [("act_drift", "ret_dau", "down", "warning")]        # ONE warning, sent once
    a = [x for x in d["changes"]["open"] if x["family"] == "act_drift"][0]
    assert a["since"] == drop.isoformat() and -0.12 < a["rel"] < -0.06 and not a["notify"]
    assert d["tiles"]["ret_dau"]["st"] == "worse" and d["summary"]["kind"] == "worse"
    assert d["summary"]["text"].startswith("⚠️ %s se purane users kam: roz ~" % eng.fmt_day(drop))
    # the store runs on: the level is back — closed after CLOSE_EVALS advanced evaluations without it
    ext, _ = make_ext(st, rv, 40)
    sent2, d2, ast, _ = daily(ext, rv, END + timedelta(days=1), END + timedelta(days=40), astate=ast)
    assert not [x for x in sent2 if x[1] == "act_drift" and x[3] == "down"]
    assert not [a for a in d2["changes"]["open"] if a["family"] == "act_drift" and a["dir"] == "down"]
    assert [a["family"] for a in d2["changes"]["closed"]].count("act_drift") == 1


def make_ext(st, rv, days):
    """The same app `days` data days further on (a longer synthetic history with the same knobs is simpler: rebuilt)."""
    drop = S - timedelta(days=9)
    back = drop + timedelta(days=14)
    st2, rv2 = quiet(days=400 + days, end=END + timedelta(days=days),
                     old=lambda d: 20000 * (0.9 if drop <= d < back else 1.0))
    return st2, rv2


def test_sudden_drop_opens_spike():
    day = S - timedelta(days=1)                                          # one settled day at −40% old users
    st, rv = quiet(old=lambda d: 20000 * (0.6 if d == day else 1.0))
    ast = {}
    d, *_ = run(st, rv, END - timedelta(days=2), astate=ast)            # still provisional: nothing judged
    assert opened(d) == []
    d, *_ = run(st, rv, END - timedelta(days=1), astate=ast)            # settled: a spike, sent
    d, *_ = run(st, rv, END, astate=ast)
    sp = [a for a in d["changes"]["open"] if a["family"] == "act_spike"]
    assert [(a["metric"], a["dir"], a["severity"], a["day"]) for a in sp] == [("ret_dau", "down", "watch", day.isoformat())]
    assert sp[0]["notify"] and sp[0]["text"].startswith("%s ko purane users achanak kam: " % eng.fmt_day(day))
    assert d["tiles"]["ret_dau"]["st"] == "watch"


def test_tracking_break_is_a_watch_and_never_a_drift():
    day = S - timedelta(days=1)
    st, rv = quiet(a1={day: 0})
    d, *_ = run(st, rv)
    br = [a for a in d["changes"]["open"] if a["family"] == "act_break"]
    assert [(a["severity"], a["day"]) for a in br] == [("watch", day.isoformat())]
    assert "ek bhi active user nahi" in br[0]["text"] and d["summary"]["kind"] == "break"
    i = (day - date.fromisoformat(d["history_start"])).days
    assert d["daily"]["ret"][i] is None and day.isoformat() in d["daily"]["breaks"]
    assert not [a for a in d["changes"]["open"] if a["family"] in ("act_drift", "act_spike")]
    assert d["tiles"]["ret_dau"]["st"] == "break" and d["tiles"]["ret_dau"]["n"] == 6
    low = S - timedelta(days=2)                                          # R under half its normal: tracking too
    st2, rv2 = quiet(old=lambda x: 20000 * (0.3 if x == low else 1.0))
    d2, *_ = run(st2, rv2)
    assert [(a["family"], a["day"]) for a in d2["changes"]["open"]] == [("act_break", low.isoformat())]
    assert "normal ke aadhe se bhi kam" in d2["changes"]["open"][0]["text"]


def test_three_month_decline_opens_slow_watch():
    start = S - timedelta(days=110)                                      # −0.2% a day for 110 days (≈ −20%)
    st, rv = quiet(days=700, noise=0.004, hll=0.004,
                   old=lambda d: 20000 * (0.998 ** max(0, (d - start).days)))
    sent, d, ast, _ = daily(st, rv, END - timedelta(days=5), END)
    sl = [a for a in d["changes"]["open"] if a["family"] == "act_slow"]
    assert [(a["dir"], a["severity"]) for a in sl] == [("down", "watch")]
    assert sl[0]["text"].startswith("Purane users 3 mahine se dheere-dheere ghat rahe: roz ~")
    assert d["tiles"]["ret_dau"]["st"] in ("slow", "watch", "worse")


def test_slow_needs_14_months_of_history():
    start = S - timedelta(days=110)
    st, rv = quiet(days=300, noise=0.004, hll=0.004, old=lambda d: 20000 * (0.998 ** max(0, (d - start).days)))
    P = act.prepare(st, active_udet(st), rv, END)
    assert act._slow_q(P, P["iS"]) is not None                          # the change is measurable …
    assert act._slow_at(P, P["iS"]) is None                             # … but its null has < SLOW_NULL_MIN weeks
    q = [act._slow_q(P, P["iS"] - 7 * w) for w in range(1, act.SLOW_NULL_WEEKS + 1)]
    assert sum(1 for x in q if x is not None) < act.SLOW_NULL_MIN


# ── 3. provisional days ─────────────────────────────────────────────────────────────────────────

def test_provisional_days_never_judged():
    st, rv = quiet()
    crash = lambda d: 20000 * (0.8 if d > S else 1.0)                   # −20% only on the 3 provisional days
    st2, rv2 = quiet(old=crash)
    ast1, ast2 = {}, {}
    d1, *_ = run(st, rv, END - timedelta(days=1), astate=ast1)
    d2, *_ = run(st2, rv2, END - timedelta(days=1), astate=ast2)
    d1, *_ = run(st, rv, END, astate=ast1)
    d2, *_ = run(st2, rv2, END, astate=ast2)
    assert d2["changes"]["open"] == [] and ast1 == ast2                  # no alert, no state change
    assert d1["tiles"] == d2["tiles"] and d2["latest"]["ret_dau"] < d1["latest"]["ret_dau"]
    assert [i for i in d2["changes"]["info"] if i["kind"] == "early"] == []   # −20%: not a crash


def test_provisional_crash_is_early_look_info_only():
    st, rv = quiet(old=lambda d: 20000 * (0.3 if d == END - timedelta(days=1) else 1.0))
    ast = {}
    d, row, *_ = run(st, rv, astate=ast)
    early = [i for i in d["changes"]["info"] if i["kind"] == "early"]
    assert [(i["from"], i["prov"]) for i in early] == [((END - timedelta(days=1)).isoformat(), True)]
    assert early[0]["text"].startswith("⏳ %s (abhi aa raha): active users normal ke aadhe se bhi kam" %
                                       eng.fmt_day(END - timedelta(days=1)))
    assert d["changes"]["open"] == [] and row["alerts"] == {"warning": 0, "watch": 0, "good": 0}
    assert d["tiles"]["ret_dau"]["st"] == "normal" and not ast["episodes"]


# ── 4. the install mix (ad spend) ───────────────────────────────────────────────────────────────

def test_installs_doubling_is_not_a_returning_alert():
    surge = S - timedelta(days=25)
    newf = lambda c: 4000 if c >= surge else 2000                        # noqa: E731 — installs ×2, old users flat
    st, rv = quiet(new=newf)
    sent, d, *_ = daily(st, rv, END - timedelta(days=4), END)
    assert not [a for a in d["changes"]["open"] if a["metric"] == "ret_dau"]            # cohort mode: never an alert
    assert d["tiles"]["ret_dau"]["st"] in ("normal", "maybe_up") and d["split"] is not None
    if d["tiles"]["ret_dau"]["st"] == "maybe_up":
        assert d["tiles"]["ret_dau"]["why"] == "installs"
    assert d["split"]["recent_rel"] > 0.2 and abs(d["split"]["old_rel"]) < 0.03       # the old users: flat
    assert not [o for o in d["changes"]["older"] if o["metric"] == "ret_dau" and "purane users zyada" in o["text"]]
    raw, rvr = quiet(new=newf, ret=False)                                # no return data: raw / elasticity mode
    sent, d2, *_ = daily(raw, rvr, END - timedelta(days=4), END)
    for a in d2["changes"]["open"]:
        assert a["metric"] != "ret_dau" or (a["severity"] == "watch" and "installs" in a["tags"])
    assert d2["tiles"]["ret_dau"]["st"] in ("normal", "maybe_up", "maybe_dn", "watch")
    assert d2["inst"] is not None and d2["inst"]["rel"] > 0.1 and d2["inst"]["mode"] in ("elastic", "raw")


def test_installs_cut_with_flat_old_users_is_info_only():
    cut = S - timedelta(days=30)
    st, rv = quiet(new=lambda c: 1000 if c >= cut else 2000)
    sent, d, *_ = daily(st, rv, END - timedelta(days=4), END)
    assert not [a for a in d["changes"]["open"] if a["metric"] == "ret_dau"] and sent == []
    info = [i for i in d["changes"]["info"] if i["kind"] == "installs"]
    assert info and info[0]["dir"] == "down" and "naye installs kam aane se (ad spend?)" in info[0]["text"]
    assert "30+ din purane users normal" in info[0]["text"]


# ── 5. revenue ──────────────────────────────────────────────────────────────────────────────────

def test_ecpm_only_move_is_price_info_not_alert():
    cut = S - timedelta(days=6)
    st, rv = quiet(ecpm=lambda d: 2.0 * (0.85 if d >= cut else 1.0))     # eCPM −15%, ads per user the same
    d, *_ = run(st, rv)
    assert d["tiles"]["arpdau"]["st"] == "price_dn" and d["tiles"]["ads"]["st"] == "normal"
    assert d["changes"]["open"] == []
    price = [i for i in d["changes"]["info"] if i["kind"] == "price"]
    assert len(price) == 1 and price[0]["dir"] == "down" and price[0]["tags"] == []
    assert price[0]["text"].startswith("Ad ka rate (eCPM) −15% (") and "app ke use ka nahi" in price[0]["text"]
    revs = []                                                            # 8 of 10 apps' eCPM fell that week: market-wide
    for k in range(10):
        s_, r_ = quiet(days=120, seed=k + 3, ecpm=lambda d, k=k: 2.0 * (0.85 if d >= cut and k < 8 else 1.0))
        revs.append(r_["days"])
    mkt = act.market(revs, END.isoformat())
    assert mkt["latest"] and mkt["latest"]["dir"] == "down" and (mkt["latest"]["apps"], mkt["latest"]["of"]) == (10, 8)
    d2, *_ = run(st, rv, mkt=mkt)
    p2 = [i for i in d2["changes"]["info"] if i["kind"] == "price"][0]
    assert p2["tags"] == ["market_wide"] and p2["text"].endswith(" · 10 me se 8 apps me aisa")
    assert act.market(revs[:5], END.isoformat()) == {"weeks": [], "latest": None}      # too few apps


def test_ads_per_user_drop_alerts():
    cut = S - timedelta(days=12)
    st, rv = quiet(ipu=lambda d, v: 4.0 * (0.92 if d >= cut else 1.0))   # ads per user −8%, settled, persistent
    sent, d, *_ = daily(st, rv, END - timedelta(days=4), END)
    ads = [a for a in d["changes"]["open"] if a["metric"] == "ads"]
    assert [(a["family"], a["dir"]) for a in ads] == [("act_drift", "down")] and ads[0]["unit"] == "per1k"
    assert ads[0]["text"].endswith("— ad load/fill check karo") and "1,000 users pe" in ads[0]["text"]
    assert d["tiles"]["ads"]["st"] in ("worse", "watch") and d["tiles"]["arpdau"]["st"] == d["tiles"]["ads"]["st"]
    # the same with time per user −8%: the users stay less, ads follow — said so
    st2, rv2 = quiet(ipu=lambda d, v: 4.0 * (0.92 if d >= cut else 1.0),
                     tpu=lambda d, v, new: (150.0 if new else 280.0 * (0.92 if d >= cut else 1.0)))
    sent, d2, *_ = daily(st2, rv2, END - timedelta(days=4), END)
    a2 = [a for a in d2["changes"]["open"] if a["metric"] == "ads"][0]
    assert "time" in a2["tags"] and "log kam time de rahe (time/user −" in a2["text"]


def test_other_network_shift_caps_ads_alert():
    cut = S - timedelta(days=12)
    st, rv = quiet(ipu=lambda d, v: 4.0 * (0.92 if d >= cut else 1.0),
                   other=lambda d: 0.02 if d < cut else 0.15)            # mediation took ~10 points more
    sent, d, *_ = daily(st, rv, END - timedelta(days=4), END)
    a = [x for x in d["changes"]["open"] if x["metric"] == "ads"][0]
    assert a["severity"] == "watch" and "mix" in a["tags"]
    assert "dusre ad networks (mediation) ka hissa badla" in a["text"]
    assert d["flags"]["other_share"] > 0.1
    assert any("Sirf AdMob Network — dusre ad networks (mediation) se ~" in t for t in d["edges"]["text"])


# ── 6. young / steep apps, launch ────────────────────────────────────────────────────────────────

def test_steep_young_app_is_growth_not_alert():
    st, rv = quiet(days=80, old=lambda d: 1000 * 1.4 ** ((d - (END - timedelta(days=79))).days / 7), new=30)
    d, row, *_ = run(st, rv)
    assert d["changes"]["open"] == []
    assert d["tiles"]["ret_dau"]["st"] == "growth" and d["tiles"]["ret_dau"]["why"] == "steep" and d["steep"]["ret_dau"]
    assert "normal range abhi nahi banti" in d["summary"]["text"] and "purane users," not in d["summary"]["text"]
    last = d["daily"]["ret"][-1]
    for m in ("ret_dau",):
        for k in ("med", "hi"):
            assert all(v is None or v <= 1.5 * last for v in d["bands"][m][k])   # never an absurd "expected"
    i = (date.fromisoformat(d["steep"]["ret_dau"][-1][1]) - date.fromisoformat(d["history_start"])).days
    assert d["bands"]["ret_dau"]["med"][i] is None                       # a steep day: no band


def test_pre_launch_test_installs_are_left_out():
    st, rv = quiet(days=200, pre_days=300)
    d, row, astate, ustate, udet = run(st, rv)
    whole = eng.cohort_data(eng.fill_days(dict(st, window_end=END.isoformat())), END)
    L = eng.launch_day(whole["n"])
    assert udet["launch"]["hidden"] and d["launch"]["hidden"] and d["launch"]["day"] == udet["launch"]["day"]
    P = act.prepare(dict(st, window_end=END.isoformat()), udet, rv, END)
    assert P["i0"] == L                                                  # the same launch as Uninstall
    i0 = L
    assert all(v is None for v in d["bands"]["ret_dau"]["med"][:i0])     # no band before the launch
    assert any(r["pre"] for r in d["tri"]["rows"]) and not any(r["pre"] for r in d["tri"]["rows"][:20])
    P["nmax"] = act._nmax(P)
    assert d["tri"]["ref_users"][1] == act._cw(P, 1, i0, P["iS"] - 1)[1]   # ref: post-launch install days only
    assert d["tiles"]["ret_dau"]["st"] == "normal"


# ── 7. new users coming back ─────────────────────────────────────────────────────────────────────

def test_d1_drop_opens_return_alert_and_provisional_cells_never_colour():
    lo = S - timedelta(days=7)                                           # the newest settled install week at D1
    st, rv = quiet(new=2000, rho=lambda c, k: DEFAULT_RET(k) - (0.04 if k == 1 and lo <= c <= S - timedelta(days=1)
                                                                  else 0.0))
    d, *_ = run(st, rv, astate={"eval": {}, "episodes": {}, "closed": []})
    ra = [a for a in d["changes"]["open"] if a["family"] == "act_return"]
    assert [(a["metric"], a["dir"]) for a in ra] == [("d1", "down")] and ra[0]["unit"] == "pp"
    assert -4.5 < ra[0]["delta_pp"] < -3.5 and ra[0]["installs_to"] == (S - timedelta(days=1)).isoformat()
    assert ra[0]["text"].startswith("Agle din wapas aane wale kam: 100 me 26, pehle 30 (")
    assert d["tiles"]["d1"]["st"] in ("worse", "watch")
    # the same drop only on install days whose day 1 is still provisional: no alert, never coloured
    E2 = END - timedelta(days=5)                                          # a Monday: last week's D1 cells just in
    S2 = E2 - timedelta(days=act.ACT_LATE_DAYS)
    st2, rv2 = quiet(new=2000, rho=lambda c, k: DEFAULT_RET(k) - (0.15 if k == 1 and c >= S2 else 0.0))
    d2, *_ = run(st2, rv2, E2)
    assert not [a for a in d2["changes"]["open"] if a["family"] == "act_return"]
    wk = d2["tri"]["rows"][1]                                            # the week S2 falls in: its D1 is provisional
    assert wk["from"] <= S2.isoformat() <= wk["to"] and wk["prov"][1] and wk["v"][1] < d2["tri"]["ref"][1] - 0.01
    assert wk["heat"][1] == 0 and d2["tiles"]["d1"]["st"] == "normal"


def test_return_columns_follow_stage_and_nmax():
    st, rv = quiet(days=200)
    for stage, zoom, want in (("stable", None, [1, 3, 7, 14, 30]), ("badh_raha", None, [1, 2, 3, 4, 5, 6, 7, 10, 14, 21, 30]),
                              ("stable", {"until": "x"}, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 30])):
        d, *_ = run(st, rv, udet_fn=lambda u, s=stage, z=zoom: dict(u, stage=s, zoom=z))
        assert d["tri"]["cols"] == want and d["tri"]["nmax"] == 30 and d["tri"]["cols_phone"] == [1, 3, 7, 14, 30]
    young, rvy = quiet(days=200, ret_edge="searching", ret_days=20)      # 20 install days of return data only
    d, *_ = run(young, rvy, udet_fn=lambda u: dict(u, stage="stable", zoom=None))
    assert d["tri"]["nmax"] < 30 and all(N <= d["tri"]["nmax"] for N in d["tri"]["cols"] + d["tri"]["cols_phone"])
    assert d["tiles"]["d7"]["st"] in ("low", "normal")


def test_return_grid_ref_avg4_pre_prov():
    st, rv = quiet(days=200)
    d, *_ = run(st, rv)
    t = d["tri"]
    assert t["label"] == "All-time normal" and t["edge"] == d["history_start"]
    assert abs(t["ref"][1] - 0.3) < 0.002 and abs(t["ref"][7] - DEFAULT_RET(7)) < 0.002
    assert not any(t["ref_thin"][1:])
    a4 = t["avg4"]
    assert date.fromisoformat(a4["to"]).weekday() == 6 and a4["to"] <= d["settled_till"]
    assert (date.fromisoformat(a4["to"]) - date.fromisoformat(a4["from"])).days == 27
    assert a4["v"][1] is not None and a4["prov"][1] is False
    rows = t["rows"]
    assert rows[0]["to"] == d["data_till"] and rows[0]["v"][30] is None  # the newest week has not reached D30
    assert all(r["prov"][N] for r in rows[:1] for N in range(1, 31) if r["v"][N] is not None)
    assert all(not any(r["heat"][1:]) for r in rows)                     # steady: nothing coloured
    assert [r["week"] for r in rows] == sorted((r["week"] for r in rows), reverse=True)
    coh = d["daily"]["coh"]
    assert coh["t"][-40] == st["ret"][sorted(st["ret"])[-40]]["t"] and coh["ok"][-40] == 1
    assert coh["d1"][-40] == st["ret"][sorted(st["ret"])[-40]]["a"][1] and coh["d30"][-1] is None
    pre, rvp = quiet(days=200, pre_days=150)                             # test installs before the launch:
    d2, *_ = run(pre, rvp)                                               # their weeks kept, flagged, out of ref
    launch = d2["launch"]["day"]
    rows2 = d2["tri"]["rows"]
    assert [r["pre"] for r in rows2] == [r["to"] < launch for r in rows2] and any(r["pre"] for r in rows2)
    assert abs(d2["tri"]["ref"][1] - 0.3) < 0.002                        # the testers' D1 (1 of 1–2) left out


def test_every_return_rate_is_over_the_install_days_ga4_new_users_never_the_cohort_total():
    """Firebase's D1 / D7 base is "New users": every rate = Σ day-N returners ÷ Σ the install days' GA4 new users (daily
    "new"). The cohort's own total t (here 8% above new — still a usable cohort) never divides: tiles, act_return and
    the grid (all-time normal, 4-week average, weeks) read exactly as when t = new. (Every cohort here is usable, so no
    returner is imputed: ρ̂ is proved by the next test.)"""
    lo = S - timedelta(days=7)
    kw = dict(new=2000,
              rho=lambda c, k: DEFAULT_RET(k) - (0.04 if k == 1 and lo <= c <= S - timedelta(days=1) else 0.0))
    st, rv = quiet(**kw)
    base, *_ = run(copy.deepcopy(st), rv, astate={"eval": {}, "episodes": {}, "closed": []})
    for e in st["ret"].values():
        e["t"] = int(round(e["t"] * 1.08))
    d, *_ = run(st, rv, astate={"eval": {}, "episodes": {}, "closed": []})
    for k in ("d1", "d7"):
        for f in ("v", "base", "all", "pp", "z", "s", "n", "nb", "st"):
            assert d["tiles"][k][f] == base["tiles"][k][f], (k, f)
    t1 = d["tiles"]["d1"]
    assert t1["s"][1] == 2000 * t1["n"] and t1["s"][3] == 2000 * t1["nb"]     # Σ new users, not Σ t
    assert abs(t1["base"] - 0.3) < 0.002 and abs(t1["v"] - 0.26) < 0.002
    ra = [a for a in d["changes"]["open"] if a["family"] == "act_return"]
    assert [(a["metric"], a["dir"]) for a in ra] == [("d1", "down")] and ra[0]["users"] == 2000 * t1["n"]
    assert ra[0]["text"].startswith("Agle din wapas aane wale kam: 100 me 26, pehle 30 (")
    g, gb = d["tri"], base["tri"]
    assert g["ref"] == gb["ref"] and g["ref_users"] == gb["ref_users"] and g["avg4"] == gb["avg4"]
    assert [(r["v"], r["users"], r["heat"]) for r in g["rows"]] == [(r["v"], r["users"], r["heat"]) for r in gb["rows"]]
    assert g["rows"][2]["users"] == 7 * 2000                              # a full settled week: Σ new users
    assert d["daily"]["old"] == base["daily"]["old"] and d["daily"]["y"] == base["daily"]["y"]
    last = sorted(st["ret"])[-40]
    assert d["daily"]["coh"]["t"][-40] == st["ret"][last]["t"] != 2000        # t itself is kept as stored
    # an install day whose GA4 new users are unknown has no rate (never 0): left out of both sums
    gone = (lo + timedelta(days=2)).isoformat()
    st2 = copy.deepcopy(st)
    del st2["daily"][gone]
    d2, _, _, _, udet = run(st2, rv)
    P = act.prepare(dict(st2, window_end=END.isoformat()), udet, rv, END.isoformat())
    i = (date.fromisoformat(gone) - P["hs"]).days
    assert P["usable"][i] and not P["rd"][i] and act._cw(P, 1, i, i) == (0, 0, 0) and d2["daily"]["new"][i] is None
    t2 = d2["tiles"]["d1"]
    assert t2["n"] == t1["n"] - 1 and t2["s"][1] == t1["s"][1] - 2000 and t2["s"][0] < t1["s"][0]


def test_imputed_returners_are_the_install_days_new_users_times_rho_per_new_user_never_the_cohort_scale():
    """A recent cohort GA4 could not complete is imputed: its install day's GA4 new users × ρ̂_k, ρ̂ = Σ day-k returners
    ÷ Σ GA4 new users (every rate's base). Neither the cohorts' own total t nor the app's cohort scale ret_k (both 8%
    above new here) enters: the recent returners, old users, their quality and the returning-users split (old vs
    recent) read exactly as when t = new."""
    bad = lambda c: S - timedelta(days=20) <= c <= S - timedelta(days=12)        # 9 cohorts GA4 could not complete
    st, rv = quiet(new=2000, ret_ok=lambda c: not bad(c))
    base, _, _, _, udet = run(copy.deepcopy(st), rv)
    for e in st["ret"].values():
        e["t"] = int(round(e["t"] * 1.08))
    st["flags"]["impact"]["ret_k"] = 1.08
    d, _, _, _, udet2 = run(st, rv)
    P = act.prepare(dict(st, window_end=END.isoformat()), udet2, rv, END.isoformat())
    iS = P["iS"]
    imp = [i for i in range(iS - 6, iS + 1) if P["yi"][i]]
    assert len(imp) == 7 and min(P["yi"][i] for i in imp) > 1000                   # the tile week IS imputed
    rho, K = act._rho_at(P, iS)
    assert K == 30 and rho[1] == 0.3 and rho[7] == int(2000 * DEFAULT_RET(7)) / 2000     # per new user, not per t
    ri, Ki = act._rho_at(P, iS)[0], P["Kd"][iS]
    want = sum(P["A"][iS - k][k] if P["usable"][iS - k] else 2000 * ri[k] for k in range(1, Ki + 1))
    assert Ki == 30 and abs(P["Y"][iS] - want) < 1e-6                             # new × ρ̂: no ret_k
    for k in ("y", "old", "oq", "old_k"):
        assert d["daily"][k] == base["daily"][k], k
    assert d["split"] is not None and d["split"] == base["split"]
    assert d["tiles"]["ret_dau"] == base["tiles"]["ret_dau"] and d["ctx"] == base["ctx"]


def test_a_grid_week_without_a_rate_day_has_unknown_installs_never_0():
    """The grid's "N installs" is the rate's base (Σ GA4 new users of the week's rate days): a week whose install days'
    new users are all unknown has no rate and unknown installs (null — "— installs", never 0), marked part data; a week
    with one such day is part data, its installs the other 6 days'."""
    st, rv = quiet(new=2000)
    d0, *_ = run(copy.deepcopy(st), rv)
    w_all, w_one = d0["tri"]["rows"][3], d0["tri"]["rows"][5]
    assert w_all["users"] == w_one["users"] == 7 * 2000 and not w_all["part"] and not w_one["part"]
    wa = date.fromisoformat(w_all["from"])
    for j in range(7):
        del st["daily"][(wa + timedelta(days=j)).isoformat()]["new"]
    del st["daily"][(date.fromisoformat(w_one["from"]) + timedelta(days=3)).isoformat()]["new"]
    d, *_ = run(st, rv)
    r = next(x for x in d["tri"]["rows"] if x["from"] == w_all["from"])
    assert r["users"] is None and r["part"] and not r["nodata"]
    assert all(v is None for v in r["v"]) and not any(r["heat"])
    r1 = next(x for x in d["tri"]["rows"] if x["from"] == w_one["from"])
    assert r1["users"] == 6 * 2000 and r1["part"] and r1["v"][1] is not None and not any(r1["heat"])
    assert all(x["users"] == y["users"] for x, y in zip(d["tri"]["rows"], d0["tri"]["rows"])
               if x["from"] not in (w_all["from"], w_one["from"]))


# ── 8. the version table ────────────────────────────────────────────────────────────────────────

def test_version_table_keeps_rest_and_unknown():
    R1, R2 = END - timedelta(days=80), END - timedelta(days=30)
    st, rv = quiet(days=200, versions=rollout("1.0", [(R1, "1.1", 0.3), (R2, "1.2", 0.3)]))
    for k, vu in st["vuse"].items():                                     # GA4's tail and "(not set)": kept, shown
        vu["_rest"] = [1, 2, 150, 40, 90, 11000]
        vu["_x"] = [0, 0, 0, 25, 50, 7000]
    d, *_ = run(st, rv)
    vers = [v["ver"] for v in d["versions"]]
    assert vers[:3] == ["1.2", "1.1", "1.0"] and vers[-2:] == ["_x", "_rest"] or vers[-2:] == ["_rest", "_x"]
    kinds = {v["ver"]: v["kind"] for v in d["versions"]}
    assert kinds["_rest"] == "rest" and kinds["_x"] == "x" and kinds["1.2"] is None
    v12 = [v for v in d["versions"] if v["ver"] == "1.2"][0]
    assert v12["from"] == R2.isoformat() and v12["vs"]["st"] == "maybe" and v12["vs"]["why"] == "few"
    assert v12["share"] > 0.8 and v12["sess"] and v12["time"]
    nosplit, rvn = quiet(days=200, split=False, versions=rollout("1.0", [(R1, "1.1", 0.3)]))
    d2, *_ = run(nosplit, rvn)
    assert d2["flags"]["vuse_split"] is False
    assert "Version ke hisaab se sessions/time sab users ke (GA4 split nahi deta)." in d2["edges"]["text"]
    many, rvm = quiet(days=200, versions=rollout("1.0", [(END - timedelta(days=150 - 10 * k), "1.%d" % (k + 1), 0.9)
                                                        for k in range(12)]))
    d3, *_ = run(many, rvm)
    assert len([v for v in d3["versions"] if not v["kind"]]) == 10 and len(d3["versions_more"]) == 3   # never dropped


# ── 9. edges ─────────────────────────────────────────────────────────────────────────────────────

def test_edge_text_reads_ret_from_from_store():
    texts = []
    for edge in (END - timedelta(days=70), END - timedelta(days=90)):
        st, rv = quiet(days=300, ret_edge=edge)
        d, *_ = run(st, rv, cfg={"retention_changed": None})
        assert d["edges"]["ret_state"] == "found" and d["edges"]["ret_from"] == edge.isoformat()
        assert d["tri"]["edge"] == edge.isoformat()
        texts.append(d["edges"]["text"][0])
        assert eng.fmt_day(edge, END) in texts[-1]
    assert texts[0] != texts[1]
    st, rv = quiet(days=300)                                             # whole
    d, *_ = run(st, rv)
    assert d["edges"]["ret_state"] == "whole" and d["edges"]["text"][0].startswith("🔁 Wapsi ka data poori history (")
    st, rv = quiet(days=300, ret_edge="searching")
    d, *_ = run(st, rv)
    assert d["edges"]["ret_state"] == "searching" and "abhi %s tak mila" % eng.fmt_day(d["edges"]["ret_oldest"], END) \
        in d["edges"]["text"][0]
    st, rv = quiet(days=300, ret=False, usage=False)
    d, *_ = run(st, rv)
    assert d["edges"]["ret_state"] == "wait" and d["edges"]["usage_state"] == "wait"
    assert d["edges"]["text"][0] == "🔁 Wapsi (D1/D7) ka data agle GA4 fetch ke saath aayega."
    assert "⏳ Sessions aur time agle GA4 fetch ke baad aayenge (poori history ek saath)." in d["edges"]["text"]
    assert d["tiles"]["d1"]["st"] == d["tiles"]["sess"]["st"] == "wait"
    assert d["summary"]["text"].endswith(" · Wapsi (D1/D7) ka data abhi aa raha. · Sessions/time agle fetch me.")
    assert "purane users" in d["summary"]["text"] and "wapsi, time" not in d["summary"]["text"]
    tiny, rvt = quiet(days=300, new=10, old=300, zero_t=True)
    d, *_ = run(tiny, rvt)
    assert d["edges"]["ret_state"] == "unverified" and d["flags"]["ret_empty"] > 0
    assert d["edges"]["text"][0].startswith("🔁 Installs kam hain, isliye GA4 ki purani seema check nahi ho sakti")


def test_edge_reason_only_when_edge_fits_retention():
    changed = END + timedelta(days=7)
    inside, outside = changed - timedelta(days=60), changed - timedelta(days=150)
    for edge, cfg, want in ((inside, {"retention_changed": changed.isoformat()}, "retention"),
                            (outside, {"retention_changed": changed.isoformat()}, "ga4"),
                            (inside, {"retention_changed": ""}, "ga4"), (inside, {"retention_changed": "none"}, "ga4")):
        st, rv = quiet(days=300, ret_edge=edge)
        d, *_ = run(st, rv, cfg=cfg)
        assert d["edges"]["edge_why"] == want
        t = d["edges"]["text"][0]
        assert ("sirf 2 mahine rakhta tha" in t) == (want == "retention")
        assert ("GA4 ne is se pehle ke install dino ka user data poora nahi diya" in t) == (want == "ga4")


# ── 10. seeding, bursts, stream moves ─────────────────────────────────────────────────────────────

def _drop_store(**kw):
    drop = S - timedelta(days=9)
    return quiet(old=lambda d: 20000 * (0.85 if d >= drop else 1.0), **kw)


def test_first_evaluation_is_seeded():
    st, rv = _drop_store()
    d, row, ast, *_ = run(st, rv)
    assert d["changes"]["open"] and not any(a["notify"] for a in d["changes"]["open"])
    assert all(e["seeded"] and e["notified_at"] == NOW for e in ast["episodes"].values())


def test_new_input_is_seeded_and_burned_in():
    cut = S - timedelta(days=12)                                         # time per user −15% from `cut`
    st, rv = quiet(tpu=lambda d, v, new: 150.0 if new else 280.0 * (0.85 if d >= cut else 1.0))
    for since, seeded in ((10, True), (40, False)):                      # usage first seen 10 / 40 days ago
        ast, ust = {}, {}
        run(dict(st, usage={}, vuse={}), rv, END - timedelta(days=60), ast, ust)   # first evaluation: no usage yet
        run(st, rv, END - timedelta(days=since), ast, ust)                         # usage arrives
        assert ast["eval"]["a"]["inputs"]["usage"] == (END - timedelta(days=since)).isoformat()
        d = settle(st, rv, END, ast, ust)
        use = [a for a in d["changes"]["open"] if a["metric"] in ("time", "usage")]
        assert use and all(a["notify"] is not seeded for a in use), (since, use)
    # return data found only 5 days ago: its alerts are seeded (all and the noise still settle)
    lo = S - timedelta(days=7)
    st2, rv2 = quiet(new=2000, rho=lambda c, k: DEFAULT_RET(k) - (0.04 if k == 1 and lo <= c <= S - timedelta(days=1)
                                                                   else 0.0))
    ast, ust = {}, {}
    run(dict(st2, ret={}, ret_from=None), rv2, END - timedelta(days=60), ast, ust)
    run(dict(st2, ret_from=None), rv2, END - timedelta(days=30), ast, ust)        # searching: no edge yet
    run(st2, rv2, END - timedelta(days=5), ast, ust)                                # the edge is found
    assert ast["eval"]["a"]["inputs"]["ret_edge"] == (END - timedelta(days=5)).isoformat()
    d, *_ = run(st2, rv2, END, ast, ust)
    ra = [a for a in d["changes"]["open"] if a["family"] == "act_return"]
    assert ra and not ra[0]["notify"]
    # an outdated store: seeded too
    st3, rv3 = _drop_store()
    ast, ust = {}, {}
    run(st3, rv3, END - timedelta(days=30), ast, ust)
    d = settle(st3, rv3, END, ast, ust, outdated=True)
    assert d["changes"]["open"] and not any(a["notify"] for a in d["changes"]["open"])


def test_moved_stream_reseeds():
    st, rv = _drop_store()
    ast, ust = {}, {}
    run(st, rv, END - timedelta(days=30), ast, ust)
    d = settle(st, rv, END, ast, ust)
    assert any(a["notify"] for a in d["changes"]["open"])                # a real one, due
    old_ids = {e["id"] for e in ast["episodes"].values()}
    moved = dict(st, stream_id="s2")                                     # the fetch re-pulled another stream
    d2, *_ = run(moved, rv, END, ast, ust)
    assert d2["changes"]["open"] and not any(a["notify"] for a in d2["changes"]["open"])
    assert ast["eval"]["a"]["src"] == ["p", "s2"] and not d2["changes"]["closed"]
    assert all(e["seeded"] for e in ast["episodes"].values())
    assert {e["id"] for e in ast["episodes"].values()} != old_ids or all(e["seeded"] for e in ast["episodes"].values())


def test_uninstall_pass_never_touches_active_episodes():
    st, rv = _drop_store()
    ast, ust = {}, {}
    for k in range(10, -1, -1):
        run(st, rv, END - timedelta(days=k), ast, ust)
    assert ast["episodes"] and "active" not in ust
    assert not set(ast["episodes"]) & set(ust.get("episodes") or {})
    assert not {e["id"] for e in ast["episodes"].values()} & {e["id"] for e in (ust.get("episodes") or {}).values()}
    assert all(e["family"].startswith("act_") for e in ast["episodes"].values())
    assert not any(e["family"].startswith("act_") for e in (ust.get("episodes") or {}).values())


def test_hourly_re_runs_change_nothing():
    st, rv = _drop_store()
    ast, ust = {}, {}
    run(st, rv, END - timedelta(days=1), ast, ust)
    d1, row1, *_ = run(st, rv, END, ast, ust, now="2026-09-21T01:00:00Z")
    snap = json.dumps(ast, sort_keys=True)
    d2, row2, *_ = run(st, rv, END, ast, ust, now="2026-09-21T02:00:00Z")
    assert json.dumps(ast, sort_keys=True) == snap                       # the elasticity too: computed at a data
    assert ast["eval"]["a"]["beta"]["at"] == (END - timedelta(days=1)).isoformat()   # day, re-done weekly
    assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True) and row1 == row2


def test_the_uninstall_detail_is_never_changed():
    st, rv = _drop_store(versions=rollout("1.0", [(END - timedelta(days=20), "1.1", 0.3)]))
    s = dict(st, window_end=END.isoformat())
    udet, _ = eng.evaluate_app(s, "a", "App", {}, NOW, revenue=rv)
    before = copy.deepcopy(udet)
    d, row = act.evaluate(s, "a", "App", {}, NOW, udet, KEY, rv, None)
    assert udet == before
    d["impact"]["updates"].append("x")                                  # a deep copy: never the same object
    d["releases"].append("x")
    assert udet == before


# ── 11. the update link ─────────────────────────────────────────────────────────────────────────

def _impact_alert(level, rows, R):
    return {"family": "impact", "level": level, "dir": "down" if level == "win" else "up",
            "severity": {"halt": "warning", "hold": "watch", "win": "good"}[level],
            "release": {"key": "ver:9.9@%s" % R.isoformat(), "label": "v9.9", "date": R.isoformat()},
            "rows": rows}


def test_an_open_update_impact_alert_covers_the_same_change():
    drop = S - timedelta(days=9)
    R = drop - timedelta(days=1)
    st, rv = quiet(old=lambda d: 20000 * (0.85 if d >= drop else 1.0))
    halt = _impact_alert("hold", {"worse": ["returning_dau"], "better": []}, R)
    ast, ust = {}, {}
    run(st, rv, END - timedelta(days=30), ast, ust)
    d = settle(st, rv, END, ast, ust, udet_fn=lambda u: dict(u, alerts=list(u["alerts"]) + [halt]))
    a = [x for x in d["changes"]["open"] if x["family"] == "act_drift" and x["metric"] == "ret_dau"][0]
    assert not a["notify"] and a["release"]["label"] == "v9.9" and a["severity"] == "watch"   # capped at HOLD's
    assert "update" in a["tags"] and a["text"].endswith(" · v9.9 ke baad") and a["linked"]   # one story, counted once
    # a WIN (dir "down" in uninstall's terms) lists better rows: it never covers a DOWN episode
    win = _impact_alert("win", {"worse": [], "better": ["returning_dau"]}, R)
    ast, ust = {}, {}
    run(st, rv, END - timedelta(days=30), ast, ust)
    d = settle(st, rv, END, ast, ust, udet_fn=lambda u: dict(u, alerts=list(u["alerts"]) + [win]))
    a = [x for x in d["changes"]["open"] if x["family"] == "act_drift" and x["metric"] == "ret_dau"][0]
    assert a["notify"] and a["severity"] == "warning" and a["release"] is None and not a["linked"]
    # … and it does cover an UP one
    up, rvu = quiet(old=lambda d: 20000 * (1.15 if d >= drop else 1.0))
    ast, ust = {}, {}
    run(up, rvu, END - timedelta(days=30), ast, ust)
    d = settle(up, rvu, END, ast, ust, udet_fn=lambda u: dict(u, alerts=list(u["alerts"]) + [win]))
    a = [x for x in d["changes"]["open"] if x["family"] == "act_drift" and x["metric"] == "ret_dau"][0]
    assert a["dir"] == "up" and not a["notify"] and a["release"]["label"] == "v9.9"


# ── 12. history, O (old users), calibration ─────────────────────────────────────────────────────

def test_older_changes_list_a_3_month_old_drop():
    a, b = S - timedelta(days=100), S - timedelta(days=85)               # −15% for 2 weeks, 3 months ago
    st, rv = quiet(old=lambda d: 20000 * (0.85 if a <= d <= b else 1.0))
    d, *_ = run(st, rv)
    old = [o for o in d["changes"]["older"] if o["kind"] == "act_drift" and o["metric"] == "ret_dau"
           and o["dir"] == "down"]
    assert len(old) == 1 and abs((date.fromisoformat(old[0]["from"]) - a).days) <= 3
    assert date.fromisoformat(old[0]["to"]) >= b - timedelta(days=3) and old[0]["rel"] < -0.08
    assert old[0]["text"].startswith("%s se purane users kam" % eng.fmt_day(old[0]["from"], END))
    assert d["changes"]["open"] == []


def test_model_mode_old_users_stop_90_days_before_the_first_return_window():
    edge = END - timedelta(days=100)
    st, rv = quiet(days=400, ret_edge=edge)
    d, *_ = run(st, rv)
    hs = date.fromisoformat(d["history_start"])
    first = next(i for i, q in enumerate(d["daily"]["oq"]) if q is not None)
    first_rho = (edge - hs).days + 29                                    # ρ̂'s first day: 28 + 1 cohorts after the edge
    assert abs(first - (first_rho - 29 - act.MODEL_BACK_DAYS)) <= 16
    assert all(v is None for v in d["daily"]["old"][:first])
    assert d["daily"]["oq"][first] == 1 and d["daily"]["oq"][-40] == 2   # ≈ model mode, then measured


def test_calibration_steady_noise_stays_quiet():
    t = time.time()
    per_year = []
    for seed in range(20):
        st, rv = make_active_store(1095, seed=seed, usage=False, ret=False, revenue=False, noise=0.02, noise_ar=0.9)
        sent = act.replay(st, "a", active_udet(st), rv, 730, metrics=("ret_dau",))
        down = [x for x in sent if x[3] == "down"]
        per_year.append((len(down) / 2.0, sum(1 for x in down if x[4] == "warning") / 2.0))
    per_year.sort()
    assert per_year[10][0] <= 1.5 and sorted(w for _, w in per_year)[10] <= 0.5, per_year
    assert time.time() - t < 60


def test_the_same_install_week_never_re_alerts_at_a_later_day():
    X = S - timedelta(days=16)                                           # one install week comes back less on every day
    st, rv = quiet(new=2000, rho=lambda c, k: DEFAULT_RET(k) * (0.8 if X <= c <= X + timedelta(days=6) else 1.0))
    first = X + timedelta(days=6 + 1 + act.ACT_LATE_DAYS)                # its D1 settled: the first alert
    ast, ust = {}, {}
    run(st, rv, END - timedelta(days=60), ast, ust)                      # the return data's burn-in is long over
    sent, d, ast, _ = daily(st, rv, first - timedelta(days=8), END, ast, ust)   # from before its first install day
    ret = [x for x in sent if x[1] == "act_return"]
    assert [x[2:4] for x in ret] == [("d1", "down")], ret                 # D3 / D7 of the same week later: old news
    cl = ast["eval"]["a"]["claimed"]["down"]                             # the install days it told about: claimed
    assert cl[0][0] <= X.isoformat() and cl[-1][1] >= (X + timedelta(days=6)).isoformat()


# ── 13. review fixes: outages, install swings, reversals, re-tellings, real $0 ad days, young apps ───────────────

LIVE = dict(noise=0.03, noise_ar=0.9, hll=0.008)       # live-like noise (the spread measured on established live apps)


def adaily(st, rv, first, last, astate=None):
    """Daily Active evaluations (the uninstall detail stubbed) from `first` to `last`, every due alert marked sent →
    (sent [(E, family, metric, dir, severity, tags)], [(E, detail)])."""
    astate = {} if astate is None else astate
    sent, out, E = [], [], first
    while E <= last:
        s = dict(st, window_end=E.isoformat())
        d, row = act.evaluate(s, "a", "App", astate, E.isoformat() + "T12:00:00Z", active_udet(s), KEY, rv, None)
        check_detail(d, row)
        for a in d["changes"]["open"]:
            if a["notify"]:
                sent.append((E.isoformat(), a["family"], a["metric"], a["dir"], a["severity"], tuple(a["tags"])))
                for ep in astate["episodes"].values():
                    if ep["id"] == a["id"]:
                        ep["notified_at"] = E.isoformat()
        out.append((E, d))
        E += timedelta(days=1)
    return sent, out


def test_a_tracking_outage_that_runs_on_is_one_break_story():
    X = S - timedelta(days=20)                                           # 10 settled days of broken tracking
    days = [X + timedelta(days=k) for k in range(10)]
    for name, kw in (("a1 = 0", dict(a1={d: 0 for d in days})),
                     ("returning at 30%", dict(old=lambda d: 20000 * (0.3 if X <= d <= days[-1] else 1.0)))):
        st, _ = quiet(ret=False, usage=False, revenue=False, **kw)
        sent, out = adaily(st, None, X + timedelta(days=2), X + timedelta(days=22))    # (the first build: seeded)
        assert [x[1:5] for x in sent] == [("act_break", "ret_dau", "down", "watch")], (name, sent)
        for E, d in out:
            fams = {a["family"] for a in d["changes"]["open"]}
            assert fams <= {"act_break"}, (name, E, fams)                  # never a drift / slow / spike (recovery too)
            if X <= E - timedelta(days=act.ACT_LATE_DAYS) <= days[-1]:    # every outage day: one story, the tile says it
                assert d["tiles"]["ret_dau"]["st"] == "break" and d["summary"]["kind"] == "break", (name, E)
                assert len(d["changes"]["open"]) == 1 and d["changes"]["open"][0]["day"] == X.isoformat()
        E, d = next((E, d) for E, d in out if E - timedelta(days=act.ACT_LATE_DAYS) == days[-1])
        br = d["changes"]["open"][0]
        assert eng.fmt_span(X, days[-1], E) in br["text"] and br["text"].endswith("— abhi bhi chal raha"), br["text"]
        assert d["summary"]["text"].startswith("🟡 Tracking check karo — %s me" % eng.fmt_span(X, days[-1], E))
        assert {x.isoformat() for x in days} <= set(d["daily"]["breaks"])


def test_consecutive_break_days_are_one_alert():
    st, _ = quiet(ret=False, usage=False, revenue=False, a1={S - timedelta(days=1): 0, S: 0})
    d, *_ = run(st, None)
    br = [a for a in d["changes"]["open"] if a["family"] == "act_break"]
    assert len(br) == 1 and br[0]["day"] == (S - timedelta(days=1)).isoformat()
    assert eng.fmt_span(S - timedelta(days=1), S, END) in br[0]["text"]


def test_raw_mode_install_swings_are_never_blamed_on_old_users():
    X = END - timedelta(days=130)                                        # new share ~14% (the live p75), old flat
    cases = {"cut −40%": lambda c: 1800 if c >= X else 3000,
             "×1.6 for 35 days": lambda c: 4800 if X <= c < X + timedelta(days=35) else 3000,
             "×2 for 35 days": lambda c: 6000 if X <= c < X + timedelta(days=35) else 3000}
    for name, newf in cases.items():
        for seed in range(3):
            st, _ = make_active_store(520, seed=seed, old=10000, new=newf, usage=False, revenue=False, ret=False, **LIVE)
            sent = act.replay(st, "a", active_udet(st), None, 250, metrics=("ret_dau",))
            after = [x for x in sent if x[0] >= X.isoformat()]
            assert all("installs" in x[5] for x in after), (name, seed, after)   # capped, and the installs said
            assert not [x for x in after if x[4] in ("good", "warning")], (name, seed, after)


def test_cohort_mode_install_ramp_is_not_a_slow_old_user_trend():
    X = END - timedelta(days=130)
    ramp = lambda c: int(3000 * (1 - 0.5 * min(1, max(0, (c - X).days) / 90)))   # noqa: E731 — ad spend halved
    for seed in range(2):
        st, _ = make_active_store(700, seed=seed, old=10000, new=ramp, usage=False, revenue=False, **LIVE)
        P = act.prepare(dict(st, window_end=END.isoformat()), active_udet(st), None, END)
        assert act._slow_at(P, P["iS"]) is not None and act._slow_at(P, P["iS"])["rel"] < -0.1   # R fell 3 months
        info = {}
        sent = act.replay(st, "a", active_udet(st), None, 250, metrics=("ret_dau",), state_out=info)
        assert [x for x in sent if x[0] >= X.isoformat()] == [], (seed, sent)     # … the installs', never old users'


def test_a_growth_that_turns_into_a_fall_is_told_as_a_fall():
    hs = END - timedelta(days=199)
    turn = hs + timedelta(days=112)                                      # ×1.28 a week (not "steep"), then ×0.8

    def old(d):
        t = (d - hs).days
        return 300 * 1.28 ** (min(t, 112) / 7) * 0.8 ** (max(0, t - 112) / 7)
    st, _ = make_active_store(200, seed=0, old=old, new=40, usage=False, revenue=False, ret=False, **LIVE)
    sent, out = adaily(st, None, turn - timedelta(days=4), turn + timedelta(days=48))
    assert [x for x in sent if x[3] == "down" and x[0] <= (turn + timedelta(days=13)).isoformat()], sent  # ≤ 10 days
    for E, d in out:
        k = (E - timedelta(days=act.ACT_LATE_DAYS) - turn).days
        t = d["tiles"]["ret_dau"]
        assert not (t["st"] == "better" and t["rel"] is not None and t["rel"] <= -act.MIN_REL["ret_dau"]), (k, t)
        if k >= 28:                                                      # the fall: told, and it stays told
            assert [a for a in d["changes"]["open"] if a["family"] == "act_drift" and a["dir"] == "down"], k
            assert d["summary"]["kind"] in ("worse", "watch") and t["st"] in ("worse", "watch"), k


def test_a_steady_decline_stays_told_while_it_runs():
    hs = END - timedelta(days=329)
    X = hs + timedelta(days=150)                                         # −5% a week from X; < 14 months: no act_slow
    for seed in (0, 1):
        st, _ = make_active_store(330, seed=seed, old=lambda d: 20000 * 0.95 ** (max(0, (d - X).days) / 7),
                                  usage=False, revenue=False, ret=False, **LIVE)
        fin = {}
        sent = act.replay(st, "a", active_udet(st), None, 180, metrics=("ret_dau",), state_out=fin)
        down = [x for x in sent if x[3] == "down"]
        assert [x[1] for x in down] == ["act_drift"], (seed, down)          # told once …
        assert [e for e in fin["episodes"].values() if e["family"] == "act_drift" and e["dir"] == "down"]  # … still open


def test_one_step_is_one_story_never_re_told_as_a_slow_trend():
    X = END - timedelta(days=120)
    for seed in range(15):                                               # −15% for good, live-like noise
        st, _ = make_active_store(500, seed=seed, old=lambda d: 20000 * (0.85 if d >= X else 1.0), usage=False,
                                  revenue=False, ret=False, **LIVE)
        sent = act.replay(st, "a", active_udet(st), None, 200, metrics=("ret_dau",))
        down = [x for x in sent if x[3] == "down" and x[0] >= X.isoformat()]
        assert 1 <= len(down) <= 2, (seed, down)                         # a spike then its drift: one story
        assert [x[1] for x in down] in (["act_drift"], ["act_spike", "act_drift"], ["act_slow"]), (seed, down)


def test_a_day_admob_reports_0_ads_is_a_real_0():
    bad = {S - timedelta(days=k) for k in range(3)}                      # AdMob's rows say 0 ads while users are there
    st, rv = quiet(ipu=lambda d, v: 4.0 * (0.0 if d in bad else 1.0))
    ast = {"eval": {"a": {"end": (END - timedelta(days=90)).isoformat(), "src": ["p", "s"], "streak": {}, "since": {},
                          "claimed": {}, "beta": {}, "inputs": dict.fromkeys(("usage", "ret", "ret_edge", "rev"),
                                                                            (END - timedelta(days=400)).isoformat())}},
           "episodes": {}, "closed": []}
    d, *_ = run(st, rv, astate=ast)
    ads = [a for a in d["changes"]["open"] if a["metric"] == "ads"]
    assert [(a["family"], a["severity"], a["notify"]) for a in ads] == [("act_spike", "warning", True)]
    t = d["tiles"]["ads"]
    assert t["n"] == 7 and t["rel"] < -0.3 and t["st"] == "worse" and d["tiles"]["arpdau"]["n"] == 7
    i = (S - timedelta(days=1) - date.fromisoformat(d["history_start"])).days
    assert d["daily"]["imp"][i] == 0 and d["daily"]["rev"][i] == 0     # 0, never "No ad data"


def test_an_account_reported_day_without_the_apps_row_is_0_not_unknown():
    st, rv = quiet(days=200)
    hole = [(END - timedelta(days=k)).isoformat() for k in range(20, 25)]
    for k in hole:
        del rv["days"][k]
    d0, *_ = run(st, rv)                                                 # nothing says the account reported: unknown
    hs = date.fromisoformat(d0["history_start"])
    idx = [(date.fromisoformat(k) - hs).days for k in hole]
    assert all(d0["daily"]["rev"][i] is None for i in idx) and d0["edges"]["rev_gaps"]
    d1, *_ = run(st, dict(rv, cover_days=sorted(set(rv["days"]) | set(hole))))    # the account reported those days
    assert all(d1["daily"]["rev"][i] == 0 and d1["daily"]["imp"][i] == 0 for i in idx[1:-1])
    assert d1["edges"]["rev_gaps"] == [] and d1["edges"]["rev_state"] == "ok"
    one = dict(rv, days=dict(rv["days"]))                                # a one-day hole between two rows: a 0
    gone = (END - timedelta(days=40)).isoformat()
    del one["days"][gone]
    d2, *_ = run(st, one)
    j = (date.fromisoformat(gone) - hs).days
    assert d2["daily"]["rev"][j] is not None


def test_a_young_apps_tiles_count_their_days():
    st, rv = quiet(days=30)
    d, *_ = run(st, rv)
    t, ar = d["tiles"]["ret_dau"], d["tiles"]["arpdau"]
    assert (t["st"], t["why"], t["n"]) == ("low", "young", 7) and t["v"] is not None and t["s"][1] == 7
    assert (ar["st"], ar["why"], ar["n"]) == ("low", "young", 7) and ar["v"] is not None
    cut = (S - timedelta(days=10)).isoformat()                           # no AdMob rows in its last 7 settled days
    d2, *_ = run(st, dict(rv, days={k: v for k, v in rv["days"].items() if k < cut}))
    assert d2["tiles"]["arpdau"]["st"] == "noad" and d2["tiles"]["ads"]["st"] == "noad"


def test_the_old_users_split_needs_the_same_return_days_on_both_sides():
    st, rv = quiet(days=300, ret_edge=END - timedelta(days=75))         # the return data's edge still young: the
    d, *_ = run(st, rv)                                                  # returners' days K grow across B
    assert d["split"] is None and d["inst"] is not None
    st2, rv2 = quiet(days=300)                                           # the whole history: K = 30 on every day
    d2, *_ = run(st2, rv2)
    assert d2["split"] is not None and abs(d2["split"]["recent_rel"]) < 0.05 and abs(d2["split"]["old_rel"]) < 0.05


def test_an_open_alert_decides_a_tile_that_would_say_not_enough_data():
    drop = S - timedelta(days=9)                                         # a small app (under 200 returning users a day)
    st, _ = quiet(old=lambda d: 150 * (0.7 if d >= drop else 1.0), new=20, ret=False, usage=False, revenue=False)
    ast, ust = {}, {}
    run(st, None, END - timedelta(days=30), ast, ust)
    d = settle(st, None, END, ast, ust)
    al = [a for a in d["changes"]["open"] if a["metric"] == "ret_dau" and a["dir"] == "down"]
    assert al and d["tiles"]["ret_dau"]["st"] in ("worse", "watch") and d["tiles"]["ret_dau"]["why"] is None
    assert d["summary"]["kind"] in ("worse", "watch")


def test_calibration_live_like_noise_stays_quiet():
    """The same placebo with the live apps' measured noise (σ of a week's change ~2.7%, strongly autocorrelated)."""
    per = []
    for seed in range(12):
        st, rv = make_active_store(1095, seed=seed, usage=False, ret=False, revenue=False, **LIVE)
        sent = act.replay(st, "a", active_udet(st), rv, 730, metrics=("ret_dau",))
        down = [x for x in sent if x[3] == "down"]
        per.append((len(down) / 2.0, sum(1 for x in down if x[4] == "warning") / 2.0))
    down = sorted(p[0] for p in per)
    assert down[6] <= 1.5 and sorted(p[1] for p in per)[6] <= 0.5 and sum(down) / len(down) <= 1.0, per


def test_an_open_storys_null_only_ever_keeps_it_open():
    X = S - timedelta(days=40)                                           # a −15% step 40 days ago, live-like noise
    st, _ = make_active_store(400, seed=3, old=lambda d: 20000 * (0.85 if d >= X else 1.0), usage=False, revenue=False,
                              ret=False, **LIVE)
    P = act.prepare(dict(st, window_end=END.isoformat()), active_udet(st), None, END)
    i = (X - P["hs"]).days
    held_any = 0
    for e in range(i + 7, P["iS"] + 1):
        free = act._drift_at(P, "ret_dau", e)["down"]
        for cap in (i - 1, i - 60):                                      # the story's own "before" null, or older
            held = act._drift_at(P, "ret_dau", e, {"down": cap})["down"]
            assert free is None or (held is not None and abs(held["z"]) >= abs(free["z"]) - 1e-9), (e, cap)
            held_any += held is not None
    assert held_any


# ── the All-apps "📅 Daily" series (portfolio_part / portfolio): every app's own arrays, summed per day ──────────

D0 = date(2026, 6, 1)


def _pd(aid, a1, new=None, *, start=D0, till=None, launch=None, d1=None, d7=None, u=None, s=None, t=None, rev=None,
        breaks=(), est=False, currency="USD"):
    """A minimal detail (only what portfolio_part reads), its arrays from `start`."""
    H = len(a1)
    nul = [None] * H
    new = new if new is not None else [10] * H
    till = till or start + timedelta(days=H - 1)
    return {"app_id": aid, "app": "App " + aid, "key": (aid * 12)[:12], "history_start": start.isoformat(),
            "data_till": till.isoformat(), "settled_till": (till - timedelta(days=3)).isoformat(), "stale": False,
            "currency": currency, "launch": launch or {"day": start.isoformat(), "hidden": False, "sure": False},
            "flags": {"tz_blend": est, "rev_est": False},
            "daily": {"start": start.isoformat(), "a1": a1, "new": new,
                      "ret": [a - n if a and n is not None and a > n else None for a, n in zip(a1, new)],
                      "u": {"r": u or nul}, "s": {"r": s or nul}, "t": {"r": t or nul}, "rev": rev or nul,
                      "breaks": [x.isoformat() for x in breaks], "coh": {"d1": d1 or nul, "d7": d7 or nul}}}


def _pf(*dets, missing=()):
    return act.portfolio([act.portfolio_part(d) for d in dets], missing)


def test_portfolio_sums_each_day_over_the_apps_with_data_never_0():
    a = _pd("a", [100, 101, 102, 103, None, 0, 106, None, 108, 109])
    b = _pd("b", [50, 50, 50, 50, 50, 50, 50, None, 50, 50], new=[10, 10, 60, 10, 10, 10, 10, 10, 10, 10])
    body = _pf(a, b)
    T = body["total"]
    assert body["from"] == D0.isoformat() and body["to"] == (D0 + timedelta(days=9)).isoformat()
    assert T["a1"] == [150, 151, 152, 153, 50, 50, 156, None, 158, 159]              # a day with no app: null, never 0
    assert T["k"] == [2, 2, 2, 2, 1, 1, 2, 0, 2, 2] and T["n"] == [2] * 10          # "1 of 2 apps"
    assert T["new"][4] == 10 and T["kn"][4] == 1 and T["new"][7] is None            # a1 unknown / 0: its new left out
    assert T["ret"][2] == 92 and T["kr"][2] == 1                                    # b: 50 active ≤ 60 new → no returning
    assert T["ret"][0] == 90 + 40 and T["kr"][0] == 2
    pa = next(p for p in body["apps"] if p["app_id"] == "a")
    assert pa["a1"][5] is None and pa["new"][5] is None and pa["ret"][5] is None    # a1 = 0 is no data, never 0
    assert set(T) == set(act.PORT_TOTAL) and all(len(v) == 10 for v in T.values())
    assert body["marks"] == [] and body["missing"] == []


def test_portfolio_marks_launch_and_stop_and_counts_the_apps_in_the_set():
    L = D0 + timedelta(days=10)
    a = _pd("a", [1000] * 30)
    b = _pd("b", [3] * 10 + [800] * 20, launch={"day": L.isoformat(), "hidden": True, "sure": True})  # test installs
    c = _pd("c", [500] * 22 + [0] * 8)                                              # stopped: 8 days without users
    d = _pd("d", [400] * 27 + [None] * 3)                                           # a 3-day gap only: missing
    e = _pd("e", [300] * 28, till=D0 + timedelta(days=27))                          # its data 2 days behind
    body = _pf(a, b, c, d, e)
    by = {p["app_id"]: p for p in body["apps"]}
    assert by["b"]["start"] == L.isoformat() and by["b"]["start_why"] == "launch" and len(by["b"]["a1"]) == 20
    assert by["a"]["start_why"] == "data" and not by["a"]["stopped"]
    assert by["c"]["stopped"] and by["c"]["to"] == (D0 + timedelta(days=21)).isoformat() and len(by["c"]["a1"]) == 22
    assert not by["d"]["stopped"] and by["d"]["to"] == (D0 + timedelta(days=29)).isoformat()
    assert not by["e"]["stopped"] and by["e"]["data_till"] < body["to"]
    assert body["marks"] == [{"day": L.isoformat(), "start": ["b"], "stop": []},
                             {"day": (D0 + timedelta(days=22)).isoformat(), "start": [], "stop": ["c"]}]
    T = body["total"]
    assert T["n"][:10] == [4] * 10 and T["n"][10:22] == [5] * 12 and T["n"][22:] == [4] * 8
    assert T["k"][9] == 4 and T["a1"][9] == 1000 + 500 + 400 + 300                  # b's test installs never count
    assert T["k"][28:] == [2, 2] and T["n"][28:] == [4, 4]                         # d and e: in the set, no data yet
    assert T["a1"][29] == 1000 + 800


def test_portfolio_d1_d7_pool_the_returners_over_the_install_days_new_users():
    H = 20
    a = _pd("a", [1000] * H, new=[100] * H, d1=[30] * (H - 1) + [None], d7=[10] * (H - 7) + [None] * 7)
    b = _pd("b", [2000] * H, new=[300] * 2 + [0] + [300] * (H - 3), d1=[60, None, 0] + [60] * (H - 4) + [None],
            d7=[20] * (H - 7) + [None] * 7)
    T = _pf(a, b)["total"]
    assert (T["d1"][0], T["d1n"][0], T["d1k"][0]) == (90, 400, 2)                  # 90 ÷ 400 = 22.5%, not (30% + 20%)/2
    assert (T["d1"][1], T["d1n"][1], T["d1k"][1]) == (30, 100, 1)                  # b's cohort unusable that day
    assert (T["d1"][2], T["d1n"][2], T["d1k"][2]) == (30, 100, 1)                  # b had 0 new users: no rate
    assert T["d1"][-1] is None and T["d1n"][-1] is None and T["d1k"][-1] == 0       # day 1 not reached yet: null
    E = H - 1
    assert [i for i in range(H) if T["d1p"][i]] == [E - 3, E - 2, E - 1]            # c + 1 after settled_till
    assert [i for i in range(H) if T["d7p"][i]] == [E - 9, E - 8, E - 7]            # c + 7 after settled_till, reached
    assert T["d7"][E - 7] == 30 and T["d7n"][E - 7] == 400 and T["d7"][E - 6] is None


def test_portfolio_week_on_week_compares_the_same_apps_only():
    a = _pd("a", [1000 + 10 * i for i in range(21)])
    b = _pd("b", [None] * 10 + [500] * 11)                                          # appears on day 10
    c = _pd("c", [200] * 21)
    c["daily"]["a1"][6] = None                                                      # no data a week before day 13
    T = _pf(a, b, c)["total"]
    assert T["wow"][14] == float("%.4g" % ((1140 + 200) / (1070 + 200) - 1)) and T["wk"][14] == 2   # b not compared
    assert T["wow"][13] == float("%.4g" % (1130 / 1060 - 1)) and T["wk"][13] == 1   # c: no data on day 6
    assert T["wk"][17] == 3 and T["wow"][17] == float("%.4g" % ((1170 + 500 + 200) / (1100 + 500 + 200) - 1))
    assert T["wow"][:7] == [None] * 7 and T["wk"][:7] == [0] * 7


def test_portfolio_per_user_values_and_revenue_are_ratios_of_sums():
    a = _pd("a", [1000] * 4, u=[100, 100, 0, 100], s=[300, 300, 0, None], t=[6000] * 4, rev=[10.0, None, 10.0, 10.0],
            est=True)
    b = _pd("b", [5000] * 4, u=[900, None, 900, 900], s=[900, None, 900, 900], t=[9000, None, 9000, 9000],
            rev=[None, None, 5.12345, 2.5])
    c = _pd("c", [700] * 4, rev=[99.0] * 4, currency="INR")
    body = _pf(a, b, c)
    T = body["total"]
    assert (T["s"][0], T["u"][0], T["t"][0], T["ku"][0]) == (1200, 1000, 15000, 2)  # 1.2 sessions, not (3 + 1)/2
    assert (T["u"][1], T["ku"][1]) == (100, 1)                                      # b's incomplete usage day: out
    assert (T["u"][2], T["ku"][2]) == (900, 1)                                      # a: no returning users that day
    assert (T["rev"][0], T["ra1"][0], T["kv"][0], T["est"][0]) == (10.0, 1000, 1, 1)  # b's no-ad-data day: not its DAU
    assert T["rev"][1] is None and T["ra1"][1] is None and T["kv"][1] == 0          # no ad data anywhere: null, never 0
    assert (T["rev"][2], T["ra1"][2], T["est"][2]) == (15.1235, 6000, 1)
    assert (T["rev"][3], T["ra1"][3]) == (12.5, 6000)
    assert body["currency"] == "USD"                                                # c's INR: its own, never summed in
    pc = next(p for p in body["apps"] if p["app_id"] == "c")
    assert pc["currency"] == "INR" and pc["rev"] == [99.0] * 4 and T["a1"][0] == 6700


def test_portfolio_provisional_days_follow_each_apps_settled_till():
    a = _pd("a", [1000] * 21)                                                       # data till day 20, settled day 17
    b = _pd("b", [500] * 16, till=D0 + timedelta(days=15))                          # 5 days behind: settled day 12
    body = _pf(a, b)
    T = body["total"]
    assert [i for i in range(21) if T["prov"][i]] == [13, 14, 15, 18, 19, 20]
    assert body["settled_till"] == (D0 + timedelta(days=17)).isoformat()
    assert T["k"][16:] == [1] * 5 and T["n"][16:] == [2] * 5


def test_portfolio_is_order_free_and_empty_is_null():
    a, b = _pd("a", [100] * 9), _pd("b", [None, None, 7, 8, 9, 10, 11, 12, 13])
    miss = [{"app_id": "z", "app": "Zed", "why": "error"}, {"app_id": "y", "app": "Ann", "why": "no_data"}]
    assert _pf(a, b, missing=miss) == _pf(b, a, missing=miss[::-1])
    assert [m["app"] for m in _pf(a, missing=miss)["missing"]] == ["Ann", "Zed"]
    assert act.portfolio_part(_pd("n", [None, 0, None])) is None                    # never a day with users
    for body in (act.portfolio([]), act.portfolio([None], miss)):
        assert body["total"] is None and body["apps"] == [] and body["from"] is None and body["settled_till"] is None
    pb = _pf(b)["apps"][0]
    assert pb["start"] == (D0 + timedelta(days=2)).isoformat() and len(pb["a1"]) == 7   # its first day with users


def test_portfolio_part_reads_the_apps_own_detail():
    X = S - timedelta(days=9)
    st, rv = quiet(days=200, pre_days=40, a1={X: 0}, tz="Asia/Kolkata", rev_tz="America/Los_Angeles")
    d, row, *_ = run(st, rv)
    p = act.portfolio_part(d)
    dl, hs = d["daily"], date.fromisoformat(d["history_start"])
    assert d["launch"]["hidden"] and p["start"] == d["launch"]["day"] and p["start_why"] == "launch"
    i0 = (date.fromisoformat(p["start"]) - hs).days
    assert p["to"] == d["data_till"] and len(p["a1"]) == len(dl["a1"]) - i0 and not p["stopped"]
    for j, i in enumerate(range(i0, len(dl["a1"]))):
        ok = bool(dl["a1"][i])
        assert p["a1"][j] == (dl["a1"][i] if ok else None) and p["ret"][j] == (dl["ret"][i] if ok else None)
        assert p["d1"][j] == (dl["coh"]["d1"][i] if ok and dl["new"][i] else None)
        assert p["u"][j] == (dl["u"]["r"][i] or None if ok else None) and p["rev"][j] == (dl["rev"][i] if ok else None)
    x = (X - date.fromisoformat(p["start"])).days
    assert p["a1"][x] is None and p["brk"] == [X.isoformat()] and p["rev_est"] and p["settled_till"] == d["settled_till"]
    body = act.portfolio([p])
    T = body["total"]
    assert T["a1"] == p["a1"] and T["d1"] == p["d1"] and T["k"][x] == 0 and T["n"] == [1] * len(p["a1"])
    assert T["brk"][x] == 1 and body["marks"] == [] and body["currency"] == d["currency"]
    assert T["s"][-10] == dl["s"]["r"][-10] and T["rev"][-10] == dl["rev"][-10]
    txt = json.dumps(body, ensure_ascii=False, allow_nan=False)                      # no NaN / Infinity ever
    assert re.search("[%s-%s]" % (chr(0x900), chr(0x97F)), txt) is None
