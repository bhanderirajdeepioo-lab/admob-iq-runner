"""The one-off GA4 Screens probe (admob_iq/fetch/ga4_screens_probe.py) on made-up apps: which apps and days it asks,
that every kind goes out one day per request with its own filter, what it keeps from each answer, that a refusal or a
quota stop never ends the run, and that its public line is counts only."""

import gzip
import json
import os
import re
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_screens as gs
from admob_iq.fetch import ga4_screens_probe as sp
from admob_iq.fetch import ga4_uninstall as gu

from tests.test_ga4_screens import _patch_routes

NOW = datetime(2026, 11, 4, 6, 0, tzinfo=timezone.utc)
FE = date(2026, 10, 30)                                 # the newest final day (today − 5, UTC)
BAD, CTRL = "ca-app-pub-0000000000000000~31", "ca-app-pub-0000000000000000~32"
APPS = [{"app_id": BAD, "package": "com.example.bad", "pid": "311"},
        {"app_id": CTRL, "package": "com.example.ctrl", "pid": "312"}]
MAIN, LIST_ = "x.y.MainActivity", "x.y.ListActivity"
QOK = {"tokensPerDay": {"consumed": 3, "remaining": 199000}, "tokensPerHour": {"consumed": 3, "remaining": 39000},
       "tokensPerProjectPerHour": {"consumed": 3, "remaining": 13900},
       "potentiallyThresholdedRequestsPerHour": {"consumed": 0, "remaining": 120},
       "serverErrorsPerProjectPerHour": {"consumed": 0, "remaining": 10}}


def _gz(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f)


def _store(data, aid, pkg, bad_days):
    """An app's Screens store: Oct 2026 final days with a whole truth; the "a" read sampled on `bad_days`."""
    root, key = os.path.join(data, gs.DIR), gu.file_key(aid)
    days = {}
    for i in range(1, 31):
        d = date(2026, 10, i).isoformat()
        a = {"st": "s", "g": "c", "smp": 0.2, "tried": ["fu", "f", "c"]} if d in bad_days else \
            {"st": "w", "g": "fu", "r": [], "tried": ["fu"]}
        days[d] = {"t": {"st": "w", "g": "t", "ev": 1000 + i, "a": [["Banner", 60], ["Interstitial", 10]],
                         "v": [100, 500]}, "a": a, "w": {"st": "w", "g": "u", "r": []}}
    _gz(gs.month_path(root, key, "core", "2026-10"), {"v": gs.STORE_V, "days": days})
    _gz(gs.meta_path(root, key), {"v": gs.STORE_V, "app_id": aid, "package": pkg, "time_zone": "UTC", "reads": {},
                                  "months": {"core": ["2026-10"]}})


ADS = [(MAIN, "Banner", "unit_b", 60), (MAIN, "Interstitial", "unit_i", 10), (LIST_, "Banner", "unit_b", 60),
       (LIST_, "Interstitial", "unit_i", 10)]
OTHER = [(MAIN, "screen_view", 100), (LIST_, "screen_view", 100)]


def _fake(monkeypatch, refuse=(), low_after=None):
    """ga4._call answered from made-up rows (ADS: ad_impression events by class × format × unit; OTHER: the other
    events; views 100 and exposure 9 per class), summed over whatever dimensions are asked — screen path / page screen /
    name read as the class; a split by screen class of eventCount under the event filter comes back SAMPLED (the fetch's
    "a"); `refuse` kinds → HTTP 400; after `low_after` calls the quota goes under the floors. → [(property, body)]."""
    asked = []
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    scr = (sp.SC, sp.PP, sp.PS, sp.SN)

    def call(method, url, token, body=None, params=None):
        if body is None:                                # the Admin API's property (round 4: currency, time zone)
            return {"timeZone": "UTC", "currencyCode": "USD"}
        pid = url.split("properties/")[1].split(":")[0]
        asked.append((pid, body))
        dims = [d["name"] for d in body["dimensions"]]
        met = body["metrics"][0]["name"]
        ex = ((body.get("dimensionFilter") or {}).get("andGroup") or {}).get("expressions") or []
        fl = {x["filter"]["fieldName"]: x["filter"]["stringFilter"]["value"] for x in ex if "stringFilter" in x["filter"]}
        for k in refuse:
            _, kd, km, _, _ = sp._kind(k)
            if km == met and [d for d in dims if d != "date"] == list(kd):
                raise RuntimeError("HTTP 400: made-up refusal text that must never be printed")
        day = body["dateRanges"][0]["startDate"].replace("-", "")
        if met == sp.PV:
            base = [({"c": c}, 100) for c in (MAIN, LIST_)]
        elif met in sp.REV:                             # a decimal, as GA4 gives revenue
            base = [({"c": c}, 0.25) for c in (MAIN, LIST_)]
        elif met == sp.USR:
            base = [({"c": c}, 40) for c in (MAIN, LIST_)]
        elif met == sp.EXP:
            base = [({"c": c}, 9) for c in (MAIN, LIST_)]
        else:
            base = [({"c": c, "f": f, "u": u, "e": sp.IMP}, n) for c, f, u, n in ADS]
            if fl.get("eventName") != sp.IMP and met == sp.EC:
                base += [({"c": c, "f": "", "u": "", "e": e}, n) for c, e, n in OTHER]
        out = {}
        for k, n in base:
            key = tuple(day if d == "date" else k["c"] if d in scr else k["f"] if d == sp.FMT else
                        k["u"] if d == sp.UNIT else k["e"] for d in dims)
            out[key] = out.get(key, 0) + n
        rows = [{"dimensionValues": [{"value": v} for v in key], "metricValues": [{"value": str(n)}]}
                for key, n in sorted(out.items())]
        meta = {}
        if met == sp.EC and fl.get("eventName") == sp.IMP and sp.SC in dims:
            meta["samplingMetadatas"] = [{"samplesReadCount": "200", "samplingSpaceSize": "1000"}]
        q = QOK
        if low_after is not None and len(asked) > low_after:
            q = dict(QOK, tokensPerHour={"consumed": 3, "remaining": 10})
        return {"dimensionHeaders": [{"name": d} for d in dims], "metricHeaders": [{"name": met}],
                "rows": rows, "rowCount": len(rows), "metadata": meta, "propertyQuota": q}
    monkeypatch.setattr(ga4, "_call", call)
    return asked


def _setup(monkeypatch, tmp_path):
    _patch_routes(monkeypatch, APPS)
    data = str(tmp_path / "data")
    _store(data, BAD, "com.example.bad", {"2026-10-%02d" % i for i in (3, 9, 17, 25, 28)})
    _store(data, CTRL, "com.example.ctrl", set())
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    return data, cfg


def test_it_asks_every_kind_one_day_at_a_time_and_keeps_each_answer(monkeypatch, tmp_path):
    data, cfg = _setup(monkeypatch, tmp_path)
    asked = _fake(monkeypatch)
    out = sp.run_all(cfg, data, set(), now=NOW, workers=2)
    assert "error" not in out
    kb, kc = gu.file_key(BAD), gu.file_key(CTRL)
    assert set(out["apps"]) == {kb, kc} and out["control"] == kc
    span = {}                                           # (dims, metric) → the day counts its kinds ask
    for k in sp.KINDS:
        _, kd, km, _, kn = sp._kind(k)
        span.setdefault((tuple(kd), km), set()).add(kn)
    for _, b in asked:                                  # one day per request, but for the kinds asked over N days
        r = b["dateRanges"][0]
        key = (tuple(d["name"] for d in b["dimensions"] if d["name"] != "date"), b["metrics"][0]["name"])
        n = (date.fromisoformat(r["endDate"]) - date.fromisoformat(r["startDate"])).days + 1
        assert b["returnPropertyQuota"] and n in span[key], (key, n)
    res = out["apps"][kb]
    assert res["final_end"] == FE.isoformat() and res["stopped"] is None
    assert res["alt"][0] == FE.isoformat()              # final_end − 0, then the nearest older days with a truth
    alt_kinds = {(a["k"], a["d"]) for a in res["ans"] if a["d"] in res["alt"]}
    assert alt_kinds == {(k, d) for k in sp.KINDS for d in res["alt"]}
    for d in ("2026-10-03", "2026-10-09", "2026-10-17", "2026-10-25", "2026-10-28"):
        assert d in res["sweep"]                        # every not-whole "a" day (fewer than SWEEP_MAX)
        if d not in res["alt"]:
            assert {a["k"] for a in res["ans"] if a["d"] == d} == set(sp.SWEEP_KINDS)
    c = next(a for a in res["ans"] if a["k"] == "c" and a["d"] == FE.isoformat())
    assert c["s"] and c["smp"] == 0.2 and c["space"] == 1000 and c["tok"] == 3 and c["sum"] == 140
    pub = next(a for a in res["ans"] if a["k"] == "c_pub" and a["d"] == FE.isoformat())
    assert not pub.get("s") and pub["sum"] == 140
    assert res["rows"]["c_pub|%s" % FE.isoformat()] == {MAIN: 70, LIST_: 70}
    assert res["days"]["2026-10-28"]["a"]["st"] == "s" and res["days"]["2026-10-28"]["ta"] == 70
    s = out["summary"]
    assert s["c"]["s"] == s["c"]["n"] and s["c"]["tie_n"] == 0           # sampled answers never "tie"
    assert s["c_pub"]["tie"] == s["c_pub"]["n"] > 0
    # every kind's own filter: the pin, the event, both, or none
    flt = {}
    for _, b in asked:
        ex = ((b.get("dimensionFilter") or {}).get("andGroup") or {}).get("expressions") or []
        flt.setdefault(tuple(d["name"] for d in b["dimensions"]) + (b["metrics"][0]["name"],),
                       set()).add(tuple(sorted(x["filter"]["fieldName"] for x in ex)))
    assert flt[("date", sp.SC, sp.EC)] == {("eventName", "platform", "streamId"), ("eventName",),
                                           ("eventName", "streamId")}
    assert flt[("date", sp.SC, sp.PUB)] == {("platform", "streamId"), ()}


def test_a_refusal_or_a_quota_stop_never_ends_the_run(monkeypatch, tmp_path):
    data, cfg = _setup(monkeypatch, tmp_path)
    _fake(monkeypatch, refuse=("sn",), low_after=20)
    out = sp.run_all(cfg, data, {gu.file_key(BAD)}, now=NOW, workers=1)
    res = out["apps"][gu.file_key(BAD)]
    assert res["stopped"] == "hour_low" and 0 < len(res["ans"]) <= 21
    sn = [a for a in res["ans"] if a["k"] == "sn"]
    assert sn and all(a["http"] == "4xx" and "sum" not in a for a in sn)
    assert out["counts"]["4xx"] == len(sn) and out["counts"]["stopped"] == 1


def test_the_public_line_is_counts_only(monkeypatch, tmp_path, capsys):
    data, cfg = _setup(monkeypatch, tmp_path)
    _fake(monkeypatch, refuse=("sn",))
    got = {}
    monkeypatch.setattr(sp.dp, "write_private", lambda path, text, msg: got.update(path=path, text=text, msg=msg)
                        or True)
    env = {"GA4_CLIENT_ID": "c", "GA4_CLIENT_SECRET": "s", "GA4_REFRESH_TOKENS": json.dumps({"o": "rt"}),
           "SCREENS_PROBE_DATA_DIR": str(tmp_path)}
    sp.main(env=env, now=NOW)
    printed = capsys.readouterr().out.strip().splitlines()
    assert len(printed) == 1 and re.fullmatch(r"screens probe: apps 2, calls \d+, tokens \d+, sampled \d+, loss \d+, "
                                              r"refused \d+, stopped 0, written", printed[0]), printed
    assert got["path"] == sp.OUT and re.fullmatch(r"screens probe \d{4}-\d\d-\d\d \d\d:\d\d UTC", got["msg"])
    j = json.loads(got["text"])
    assert set(j["apps"]) == {gu.file_key(BAD), gu.file_key(CTRL)}
    assert "made-up refusal" not in got["text"]        # a refusal keeps its class only


def test_plan_spreads_the_sweep_and_keeps_only_days_with_a_whole_truth():
    days = {}
    for i in range(120):
        d = (FE - timedelta(days=i)).isoformat()
        days[d] = {"t": {"st": "w", "ev": i}, "a": {"st": "s" if i % 2 else "w"}}
    days[(FE - timedelta(days=30)).isoformat()]["t"] = {"st": "s"}       # no whole truth: never asked
    alt, sweep = sp.plan(days, FE)
    assert alt == [FE.isoformat(), (FE - timedelta(days=31)).isoformat(), (FE - timedelta(days=95)).isoformat()]
    assert (FE - timedelta(days=30)).isoformat() not in sweep
    bad = [d for d in sweep if days[d]["a"]["st"] == "s"]
    assert len(bad) <= sp.SWEEP_MAX + sp.NEWEST and sweep == sorted(sweep, reverse=True)
    assert FE.isoformat() in sweep and (FE - timedelta(days=119)).isoformat() in sweep


def test_the_run_options_pick_kinds_days_and_the_private_path(monkeypatch, tmp_path):
    data, cfg = _setup(monkeypatch, tmp_path)
    asked = _fake(monkeypatch)
    opts, path = sp.options({"only": "ppf,pp31,ppk,nope", "sweep": "0", "back": "0,20", "tag": "r2"})
    assert opts == {"only": {"ppf", "pp31", "ppk"}, "sweep": False, "back": (0, 20), "days": None}
    assert path == "ga4/screens_probe_r2.json"
    assert sp.options({"tag": "../x"})[1] == sp.OUT and sp.options({})[0] == {"only": None, "sweep": True,
                                                                              "back": None, "days": None}
    out = sp.run_all(cfg, data, {gu.file_key(BAD)}, now=NOW, workers=1, opts=opts)
    res = out["apps"][gu.file_key(BAD)]
    assert res["sweep"] == [] and len(res["alt"]) == 2
    assert {a["k"] for a in res["ans"]} == {"ppf", "pp31", "ppk"} and len(res["ans"]) == 6
    for _, b in asked:
        r = b["dateRanges"][0]
        dims = [d["name"] for d in b["dimensions"]]
        if dims == ["date", sp.PP] and b["metrics"][0]["name"] == sp.EC:          # pp31: 31 days ending on the day
            assert (date.fromisoformat(r["endDate"]) - date.fromisoformat(r["startDate"])).days == 30
        else:
            assert r["startDate"] == r["endDate"]
        if sp.EVN in dims:                                                        # ppk: the click events, in a list
            ex = b["dimensionFilter"]["andGroup"]["expressions"]
            assert {"inListFilter": {"values": list(gs.CLICKS)}, "fieldName": "eventName"} in [x["filter"] for x in ex]
    assert out["opts"] == {"only": ["pp31", "ppf", "ppk"], "sweep": False, "back": (0, 20), "days": None}


def test_a_format_filter_rides_the_pin_and_the_event():
    b = sp.request("ppI", FE, "777")
    ex = [x["filter"] for x in b["dimensionFilter"]["andGroup"]["expressions"]]
    assert {"fieldName": "platform", "stringFilter": {"matchType": "EXACT", "value": "Android"}} in ex
    assert {"fieldName": "eventName", "stringFilter": {"matchType": "EXACT", "value": sp.IMP}} in ex
    assert {"fieldName": sp.FMT, "inListFilter": {"values": list(sp.INLINE)}} in ex
    assert [d["name"] for d in b["dimensions"]] == ["date", sp.PP]
    b = sp.request("ppU31", FE, "777")
    assert b["dateRanges"] == [{"startDate": (FE - timedelta(days=30)).isoformat(), "endDate": FE.isoformat()}]


def test_round_4_revenue_in_micros_period_users_pinned_days_and_the_currency(monkeypatch, tmp_path):
    """Round 4 (8 Nov 2026): revenue by screen kept in micros and tied to its date total, a period's users by screen with
    no date dimension over the kind's own days, the ALT days pinned to ISO dates, the property's currency kept."""
    data, cfg = _setup(monkeypatch, tmp_path)
    asked = _fake(monkeypatch)
    opts, _ = sp.options({"only": "t_rv31,rv_c31,rv_pp31,us_c31,us_t31,us_c1000", "sweep": "0",
                          "days": "2026-10-31,bad,2026-02-30,2026-09-30,2026-10-31"})
    assert opts["days"] == ("2026-10-31", "2026-09-30")          # bad and impossible dates dropped, once each
    out = sp.run_all(cfg, data, {gu.file_key(BAD)}, now=NOW, workers=1, opts=opts)
    res = out["apps"][gu.file_key(BAD)]
    assert res["alt"] == ["2026-10-31", "2026-09-30"] and res["sweep"] == []
    assert res["prop"] == {"time_zone": "UTC", "currency": "USD"}
    rv = next(a for a in res["ans"] if a["k"] == "rv_c31" and a["d"] == "2026-10-31")
    assert rv["sum"] == 500000                                    # 2 screens × 0.25 → micros
    assert res["rows"]["rv_c31|2026-10-31"] == {MAIN: 250000, LIST_: 250000}
    assert res["rows"]["us_c31|2026-10-31"] == {MAIN: 40, LIST_: 40}
    assert out["summary"]["rv_c31"]["tie"] == out["summary"]["rv_c31"]["tie_n"] == 2
    assert out["summary"]["rv_pp31"]["tie"] == 2
    seen = set()
    for _, b in asked:
        dims = [d["name"] for d in b["dimensions"]]
        r = b["dateRanges"][0]
        n = (date.fromisoformat(r["endDate"]) - date.fromisoformat(r["startDate"])).days + 1
        if b["metrics"][0]["name"] == sp.USR:
            assert "date" not in dims and n in (31, 1000)         # a period: unique users, never per day
            seen.add((tuple(dims), n, r["endDate"]))
    assert ((sp.SC,), 31, "2026-10-31") in seen and ((), 31, "2026-09-30") in seen and ((sp.SC,), 1000, "2026-10-31") in seen
