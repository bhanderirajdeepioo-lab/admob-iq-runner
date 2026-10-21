"""🆕 First open tab — the build step (admob_iq.firstopen_build), on made-up stores: every day of every store in one lazy
file (nothing trimmed), the status rule (last 7 final days vs the 28 before: Worse / Watch / Better / Normal, Too early,
N/A), the pointer the hub reads, one splat header rule, the switch, failure isolation and a counts-only line; BY COUNTRY
(synthetic country stores, 40 made-up countries): the lazy file's shape (every real day, every country), the app's own
status rule per country, the share, the GA4-unnamed users (measured, never clamped), the "cc" pointer only when the file
was written, stale files removed, and the app's own data byte for byte the same with a broken / too big / missing store;
the status window on the CALENDAR (the unbroken run of days ending at final till): a hole (the backfill reads oldest /
newest in turn), a lag (a fetch behind / switched off) or a "none" day inside the 35 days = Too early with the why, never a
window across a hole or weeks old; "last_day" / "missing" in the file, "last" in the pointer."""
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq import firstopen_build as fb
from admob_iq.db import write_json_gz_stable
from admob_iq.fetch import ga4_firstopen as gf

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)


def _store(data, aid, days, home7, home28, splash=1000, langs=True):
    """`days` days to 13 Oct; Home = home7 × Splash on the last 7 final days (≤ 11 Oct), home28 before."""
    d0 = date(2026, 10, 13) - timedelta(days=days - 1)
    recs = {}
    for i in range(days):
        d = d0 + timedelta(days=i)
        last7 = date(2026, 10, 5) <= d <= date(2026, 10, 11)
        h = round(splash * (home7 if last7 or d > date(2026, 10, 11) else home28))
        recs[d.isoformat()] = dict(first_open=splash + 20, splash=splash, home=h, splash_any=splash, home_any=h,
                                   **({"language": splash // 2} if langs else {}))
    s = {"v": gf.STORE_V, "app_id": aid, "package": "com.example." + aid[-1], "time_zone": "Asia/Kolkata",
         "steps": {"splash": "SplashActivity", "home": "MainActivity", **({"language": "LanguageActivity"} if langs else {})},
         "days": recs}
    write_json_gz_stable(gf.store_path(data, aid), s)


def test_file_status_pointer_and_header(tmp_path):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(os.path.join(data, gf.DIR)); os.makedirs(out)
    _store(data, "a~1", 60, 0.50, 0.60)          # −10 pts → Worse
    _store(data, "a~2", 60, 0.57, 0.60)          # −3 → Watch
    _store(data, "a~3", 60, 0.70, 0.60)          # +10 → Better
    _store(data, "a~4", 60, 0.61, 0.60)          # +1 → Normal
    _store(data, "a~5", 20, 0.61, 0.60)          # 20 days → Too early
    _store(data, "a~6", 60, 0.61, 0.60, splash=10)   # 70 Splash in 7 days → N/A
    dash = {"uninstall": {"apps": [{"app_id": "a~1", "app": "Alpha App"}]}}
    paths = fb.run(dash, data, out, {}, now=NOW)
    assert paths == ["/firstopen*"]
    with gzip.open(os.path.join(out, fb.FILE), "rt", encoding="utf-8") as f:
        body = json.load(f)
    st = {x["key"]: x["status"] for x in body["summary"]}
    from admob_iq.fetch import ga4_uninstall as gu
    assert [st[gu.file_key("a~%d" % i)] for i in range(1, 7)] == ["Worse", "Watch", "Better", "Normal", "Too early", "N/A"]
    a1 = next(x for x in body["summary"] if x["app"] == "Alpha App")
    assert abs(a1["s2h"] - 0.5) < 1e-6 and abs(a1["usual"] - 0.6) < 1e-6 and abs(a1["change"] + 0.1) < 1e-6
    assert a1["steps"]["language"] == [0.5, 0.5] and a1["final_days"] == 58 and abs(a1["fo_day"] - 1020) < 1e-6
    app1 = next(x for x in body["apps"] if x["app"] == "Alpha App")
    assert len(app1["days"]) == 60 and app1["days"][0][0] == "2026-08-15" and app1["final_till"] == "2026-10-11"   # nothing trimmed
    assert app1["days"][0][1:4] == [1020, 1000, 600] and app1["days"][0][-1] is None and a1["sample"] is None
    assert dash["firstopen"]["file"] == fb.FILE and dash["firstopen"]["apps"]["Alpha App"]["status"] == "Worse"
    assert dash["firstopen"]["apps"]["Alpha App"]["id"] == "a~1"
    line = fb.pop_line()
    assert line.startswith("first open: apps 6, days ") and "worse 1, watch 1, better 1, normal 1, too early 1, n/a 1" in line
    assert "Alpha" not in line and "example" not in line


def test_no_store_and_switch_off_leave_no_file(tmp_path):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(out)
    open(os.path.join(out, fb.FILE), "w").close()
    dash = {"firstopen": {"file": "old"}}
    assert fb.run(dash, data, out, {}, now=NOW) == [] and "firstopen" not in dash and not os.path.exists(os.path.join(out, fb.FILE))
    open(os.path.join(out, fb.FILE), "w").close()
    fb.off(out)
    assert not os.path.exists(os.path.join(out, fb.FILE)) and fb.enabled({}) and not fb.enabled({"firstopen_tab": False})


# ── by country (firstopen_cc_<key>.json.gz) ──────────────────────────────────────────────────────────────────────────
from admob_iq.fetch import ga4_firstopen_cc as fc   # noqa: E402
from admob_iq.fetch import ga4_uninstall as gu      # noqa: E402

UNNAMED = (7, 6, 5)
NEG_DAY = "2026-08-20"                               # GA4 named a little more than its own total (sampling): kept as is


def _cc_rows(i, d):
    """Synthetic country C<i> on day d → [first_open, splash, home] (C00 … C03 big enough to judge, the rest N/A)."""
    last7 = date(2026, 10, 5) <= d
    if i < 4:
        fo, sp = (1100, 900, 700, 500)[i], (1000, 800, 600, 400)[i]
        return [fo, sp, round(sp * ((0.50, 0.57, 0.70, 0.61)[i] if last7 else 0.60))]
    if i in (37, 38):
        return [0, 0, 0] if (i == 38 and d < date(2026, 9, 1)) else [20, 10, 5]
    if i == 39:
        return [20, 10, 5] if last7 else [30, 20, 10]
    fo = 40 - i // 2
    return [fo, fo - 12, (fo - 12) // 2]


def _cc_store(data, aid, days=60, n=40, smp_day=None, broken=False):
    d0 = date(2026, 10, 13) - timedelta(days=days - 1)
    recs = {(d0 - timedelta(days=1)).isoformat(): {"none": True, "at": "x"}}
    for k in range(days):
        d = d0 + timedelta(days=k)
        c = {"C%02d" % i: _cc_rows(i, d) for i in range(n)}
        c = {cc: v for cc, v in c.items() if any(v)}   # the fetch leaves out a country nobody of reached
        t = [sum(v[j] for v in c.values()) + UNNAMED[j] for j in range(3)]
        if d.isoformat() == NEG_DAY:
            t[0] = sum(v[0] for v in c.values()) - 3
        recs[d.isoformat()] = {"c": c, "t": t, "smp": 0.5 if d.isoformat() == smp_day else None, "fin": True,
                               "sg": "s", "at": "x"}
    if broken:
        recs[(d0 + timedelta(days=3)).isoformat()]["c"]["C00"] = "x"
    s = {"v": fc.STORE_V, "app_id": aid, "package": "com.example.x", "time_zone": "Asia/Kolkata", "days": recs}
    write_json_gz_stable(fc.store_path(data, aid), s)
    return recs


def _read(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _dirs(tmp_path):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(os.path.join(data, gf.DIR)); os.makedirs(out)
    return data, out


def test_country_file_every_country_status_share_unnamed_and_pointer(tmp_path):
    data, out = _dirs(tmp_path)
    _store(data, "a~1", 60, 0.50, 0.60)
    _store(data, "a~2", 60, 0.57, 0.60)
    _store(data, "a~3", 60, 0.61, 0.60)
    recs = _cc_store(data, "a~1", smp_day="2026-10-06")
    _cc_store(data, "a~2", days=20)                   # 20 days → every country Too early
    dash = {}
    assert fb.run(dash, data, out, {}, now=NOW) == ["/firstopen*"]   # no new header rule
    k1, k2, k3 = (gu.file_key("a~%d" % i) for i in (1, 2, 3))
    assert sorted(f for f in os.listdir(out) if f.startswith("firstopen")) == sorted(
        [fb.FILE, "firstopen_cc_%s.json.gz" % k1, "firstopen_cc_%s.json.gz" % k2])
    body = _read(os.path.join(out, "firstopen_cc_%s.json.gz" % k1))
    assert body["v"] == 1 and body["key"] == k1 and body["app_id"] == "a~1"
    assert body["final_till"] == "2026-10-11" and body["first_day"] == "2026-08-15"
    days = body["days"]
    assert len(days) == 60 and [d[0] for d in days] == sorted(d[0] for d in days)     # every real day, the none day out
    assert all(len(d) == 6 for d in days) and len(days[-1][5]) == 40 and "C38" not in days[0][5]   # as stored
    neg = next(d for d in days if d[0] == NEG_DAY)
    assert neg[1] == sum(v[0] for v in neg[5].values()) - 3                           # measured, never clamped
    assert next(d for d in days if d[0] == "2026-10-06")[4] == 0.5
    S = body["summary"]
    assert len(S) == 40 and {x["cc"] for x in S} == {"C%02d" % i for i in range(40)}   # every country kept
    assert [x["cc"] for x in S[:4]] == ["C00", "C01", "C02", "C03"]
    assert [x["cc"] for x in S[-4:]] == ["C36", "C39", "C37", "C38"]   # 7-day first opens, then all-time, then the code
    st = {x["cc"]: x["status"] for x in S}
    assert [st["C%02d" % i] for i in range(4)] == ["Worse", "Watch", "Better", "Normal"]
    assert {st["C%02d" % i] for i in range(4, 40)} == {"N/A"}
    c0 = S[0]
    assert set(c0) == {"cc", "status", "why", "s2h", "usual", "change", "opened", "opened_usual", "fo_day", "fo_day_usual",
                       "final_days", "sample", "share"}
    assert abs(c0["s2h"] - 0.5) < 1e-6 and abs(c0["usual"] - 0.6) < 1e-6 and abs(c0["fo_day"] - 1100) < 1e-6
    assert c0["final_days"] == 58 and c0["sample"] == 0.5 and abs(c0["opened"] - 1000 / 1100) < 1e-6
    w7 = [d for d in days if "2026-10-05" <= d[0] <= "2026-10-11"]
    t7 = sum(d[1] for d in w7)
    assert abs(c0["share"] - 7 * 1100 / t7) < 1e-6
    assert abs(sum(x["share"] for x in S) + body["unnamed"]["summary"]["share"] - 1) < 1e-5   # the board adds up
    u = body["unnamed"]["summary"]
    assert u == {"fo_day": 7.0, "opened": round(6 / 7, 6), "s2h": round(5 / 6, 6), "share": round(49 / t7, 6)}
    b2 = _read(os.path.join(out, "firstopen_cc_%s.json.gz" % k2))
    assert {x["status"] for x in b2["summary"]} == {"Too early"} and len(b2["days"]) == 20
    assert {x["why"] for x in b2["summary"]} == {"history 18 final days"} and b2["missing"] == 0   # young, not a hole
    # the pointer on the app's entry (only where the file was written)
    main = _read(os.path.join(out, fb.FILE))
    apps = {a["key"]: a for a in main["apps"]}
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    import hashlib
    assert apps[k1]["cc"] == {"file": "firstopen_cc_%s.json.gz" % k1, "v": hashlib.sha1(raw).hexdigest()[:12],
                              "from": "2026-08-15", "last": "2026-10-13", "n": 40, "days": 60}
    assert body["last_day"] == "2026-10-13" and body["missing"] == 0                  # the status window is whole
    assert apps[k2]["cc"]["n"] == 40 and apps[k2]["cc"]["days"] == 20 and "cc" not in apps[k3]
    assert set(dash["firstopen"]) == {"file", "v", "apps"}                         # the dashboard pointer as before
    line = fb.pop_line()
    assert ", by country: apps 2, countries 40, kb " in line and "failed" not in line
    assert "C00" not in line and "example" not in line


def test_country_part_never_changes_the_app_data(tmp_path, monkeypatch):
    """A broken country store, a store with no real day, a file over the guard: the app's own First open data and file are
    byte for byte what they are with no country store at all."""
    base, out0 = _dirs(tmp_path / "base")
    for i in (1, 2, 3):
        _store(base, "a~%d" % i, 60, 0.50 + i / 100, 0.60)
    fb.run({}, base, out0, {}, now=NOW)
    ref = open(os.path.join(out0, fb.FILE), "rb").read()
    refm = _read(os.path.join(out0, fb.FILE))
    assert "firstopen_cc_" not in json.dumps(refm) and not any(f.startswith("firstopen_cc_") for f in os.listdir(out0))
    line0 = fb.pop_line()
    assert line0.endswith(", by country: apps 0, countries 0, kb 0")
    # an empty country folder and a store with only "none" days change nothing
    os.makedirs(os.path.join(base, fc.DIR))
    write_json_gz_stable(fc.store_path(base, "a~3"), {"v": fc.STORE_V, "app_id": "a~3", "days": {"2026-10-01": {"none": True}}})
    fb.run({}, base, out0, {}, now=NOW)
    assert open(os.path.join(out0, fb.FILE), "rb").read() == ref
    # a.1 good, a.2 broken (+ its old file in the site), a stale file of an app gone
    k1, k2 = gu.file_key("a~1"), gu.file_key("a~2")
    _cc_store(base, "a~1")
    _cc_store(base, "a~2", broken=True)
    for k in (k2, "0123456789ab"):
        open(os.path.join(out0, "firstopen_cc_%s.json.gz" % k), "w").close()
    dash = {}
    assert fb.run(dash, base, out0, {}, now=NOW) == ["/firstopen*"]
    got = _read(os.path.join(out0, fb.FILE))
    assert sorted(f for f in os.listdir(out0) if f.startswith("firstopen_cc_")) == ["firstopen_cc_%s.json.gz" % k1]
    a1 = next(a for a in got["apps"] if a["key"] == k1)
    assert a1.pop("cc")["file"] == "firstopen_cc_%s.json.gz" % k1
    assert got == refm                                                   # everything else exactly as without it
    assert "failed 1, too big 0" in fb.pop_line()
    # a country file over its guard: not written, no pointer, the app file as without it
    monkeypatch.setattr(fb, "CC_MAX_GZ", 10)
    fb.run({}, base, out0, {}, now=NOW)
    monkeypatch.undo()
    assert open(os.path.join(out0, fb.FILE), "rb").read() == ref
    assert not any(f.startswith("firstopen_cc_") for f in os.listdir(out0))
    assert "failed 1, too big 1" in fb.pop_line()
    # the country module itself failing costs only the country files
    monkeypatch.setattr(fb, "build_cc", lambda *a, **k: 1 / 0)
    fb.run({}, base, out0, {}, now=NOW)
    monkeypatch.undo()
    assert open(os.path.join(out0, fb.FILE), "rb").read() == ref
    # switched off / no store: every country file goes with the main file
    fb.run({}, base, out0, {}, now=NOW)
    assert any(f.startswith("firstopen_cc_") for f in os.listdir(out0))
    fb.off(out0)
    assert not [f for f in os.listdir(out0) if f.startswith("firstopen")]
    open(os.path.join(out0, "firstopen_cc_%s.json.gz" % k1), "w").close()
    assert fb.run({}, str(tmp_path / "nothing"), out0, {}, now=NOW) == []
    assert not [f for f in os.listdir(out0) if f.startswith("firstopen")]


def test_country_rows_feed_the_app_rule_unchanged():
    """summarize() is the one rule: a country's entry is what summarize() says on its rows in the app's layout."""
    recs = {}
    for k in range(40):
        d = (date(2026, 9, 1) + timedelta(days=k)).isoformat()
        recs[d] = {"c": {"AA": [50, 40, 20 if k < 33 else 10], "BB": [5, 4, 2]}, "t": [60, 48, 24], "smp": None}
    body = fb.build_cc({"days": recs}, "k", "a", "2026-10-08")
    rows = [[d, 50, 40, 20 if i < 33 else 10] + [None] * 5 + [None] for i, d in enumerate(sorted(recs))]
    want = fb.summarize("AA", "AA", rows, "2026-10-08")
    got = body["summary"][0]
    assert got["cc"] == "AA" and all(got[k] == want[k] for k in fb.CC_KEEP)
    assert body["summary"][1]["cc"] == "BB"
    assert fb.build_cc({"days": {"2026-09-01": {"none": True}}}, "k", "a", "2026-10-08") is None


def _gap_store(skip, k_none=()):
    """AA (judged) and BB (small): S2H 50 % the last 24 days, 60 % before; 63 days back from final till 18 Oct 2026, the
    days `skip(k)` (k days before final till) not read, the days in k_none read as {"none": true}; 2 not-final days."""
    ft, recs = date(2026, 10, 18), {}
    for k in range(-2, 63):
        d = (ft - timedelta(days=k)).isoformat()
        if skip(k):
            continue
        if k in k_none:
            recs[d] = {"none": True}
            continue
        s2h = 0.5 if k < 24 else 0.6
        c = {"AA": [1200, 1000, round(1000 * s2h)], "BB": [12, 10, 5]}
        recs[d] = {"c": c, "t": [1212 + 8, 1010 + 6, c["AA"][2] + 5 + 4], "smp": None}
    return {"days": recs}


def test_country_status_window_is_the_calendar_run_ending_at_final_till():
    """The country store has holes (its backfill reads oldest / newest in turn) or lags (a deferred / switched-off fetch):
    the status, the 7-day values, the share and the unnamed users come only from the unbroken calendar run that ends at
    final till — a hole or a lag inside the 35 days = Too early (why says which), never a window across a hole or weeks
    old; every real day stays in "days"."""
    ft = "2026-10-18"
    whole = fb.build_cc(_gap_store(lambda k: False), "k", "a", ft)
    aa = whole["summary"][0]
    assert aa["cc"] == "AA" and aa["status"] == "Watch" and abs(aa["change"] - (0.5 - (17 * 0.5 + 11 * 0.6) / 28)) < 1e-6
    assert whole["missing"] == 0 and whole["last_day"] == "2026-10-20" and len(whole["days"]) == 65
    # backfill half done: days 23 … 42 before final till not read yet → Too early, no Worse from a window across the hole
    half = fb.build_cc(_gap_store(lambda k: 23 <= k <= 42), "k", "a", ft)
    assert {x["status"] for x in half["summary"]} == {"Too early"}
    assert {x["why"] for x in half["summary"]} == {"country data incomplete: 12 din missing"} and half["missing"] == 12
    assert len(half["days"]) == 45 and half["first_day"] == "2026-08-17"                # every real day kept
    a2 = half["summary"][0]
    assert a2["final_days"] == 23 and abs(a2["s2h"] - 0.5) < 1e-6 and abs(a2["fo_day"] - 1200) < 1e-6
    assert abs(a2["usual"] - 0.5) < 1e-6 and a2["change"] == 0                         # only days of the unbroken run
    assert abs(a2["share"] - 1200 / 1220) < 1e-6 and half["unnamed"]["summary"]["fo_day"] == 8.0
    # the fetch stopped: the newest day 12 days before final till → Too early "country data <day> tak", nothing judged,
    # no 7-day value from old days (not "0 / day")
    old = fb.build_cc(_gap_store(lambda k: k < 12), "k", "a", ft)
    assert {x["status"] for x in old["summary"]} == {"Too early"}
    assert {x["why"] for x in old["summary"]} == {"country data 2026-10-06 tak"} and old["missing"] == 12
    assert old["last_day"] == "2026-10-06" and len(old["days"]) == 51
    for x in old["summary"]:
        assert x["s2h"] is None and x["usual"] is None and x["change"] is None and x["fo_day"] is None
        assert x["share"] is None and x["final_days"] == 0
    assert [x["cc"] for x in old["summary"]] == ["AA", "BB"]                            # all-time first opens order
    assert old["unnamed"]["summary"] == {"fo_day": None, "opened": None, "s2h": None, "share": None}
    # final till itself not read (a later not-final day is): a lag too
    lag = fb.build_cc(_gap_store(lambda k: k == 0), "k", "a", ft)
    assert {x["why"] for x in lag["summary"]} == {"country data 2026-10-17 tak"} and lag["missing"] == 1
    # a {"none": true} day inside the window is a hole; one older than the 35 days changes nothing
    nn = fb.build_cc(_gap_store(lambda k: False, k_none=(3,)), "k", "a", ft)
    assert {x["status"] for x in nn["summary"]} == {"Too early"} and nn["missing"] == 1
    assert nn["summary"][0]["why"] == "country data incomplete: 1 din missing"
    far = fb.build_cc(_gap_store(lambda k: 40 <= k <= 45), "k", "a", ft)
    assert far["missing"] == 0 and far["summary"][0]["status"] == "Watch" and far["summary"][0]["final_days"] == 40
    assert far["summary"][0] == dict(aa, final_days=40)
    # the rule is still summarize(): the run's rows give exactly its answer
    rows = [[d[0], *d[5]["AA"], None, None, None, None, None, None] for d in half["days"] if "2026-09-26" <= d[0] <= ft]
    want = fb.summarize("AA", "AA", rows, ft)
    assert all(a2[k] == want[k] for k in fb.CC_KEEP if k != "why") and want["why"] == "history 23 final days"


def test_country_file_lists_the_days_ga4_no_longer_has():
    """A day the country fetch found gone from GA4 ({"none": true, "why": "ga4"}) is listed in "gone" — the page says
    "GA4 me ab nahi" there instead of "abhi padhe ja rahe hain"; a plain none day (no first opens) is not listed."""
    rec = {"c": {"AA": [5, 4, 2]}, "t": [6, 5, 2], "smp": None, "fin": True, "sg": "x", "at": "t"}
    store = {"days": {"2026-08-10": dict(rec), "2026-08-01": {"none": True, "why": "ga4", "at": "t"},
                      "2026-08-02": {"none": True, "why": "ga4", "at": "t"}, "2026-08-05": {"none": True, "at": "t"}}}
    body = fb.build_cc(store, "k", "a~1", "2026-08-10")
    assert body["gone"] == ["2026-08-01", "2026-08-02"] and body["first_day"] == "2026-08-10"
