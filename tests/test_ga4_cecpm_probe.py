"""GA4 returning-session eCPM probe (admob_iq.fetch.ga4_cecpm_probe) — offline against a small fake GA4 (SYNTHETIC: made-up
countries and money): the five reads' request bodies, the cell maths (coverage, EF = E6, P6 vs E6, the tie to the cube's
"e" cells), the go / no-go thresholds, the call cap / quota stop, and a PUBLIC log that carries counts only."""
import json
import os
import re
from datetime import date, timedelta

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_cecpm_probe as cc
from admob_iq.fetch import ga4_cube as gcu
from admob_iq.fetch import ga4_nvr as gv
from admob_iq.fetch import ga4_uninstall as gu
from tests.test_ga4_device_probe import AID, KEY, NOW, PID, RT, SECRETS, SID, TOK, unit

CTRY = ("XA", "XB", "(not set)")
USERS = 10
IMPS = 5                                                   # ad_impression events per user a day
F = date(2026, 10, 15) - timedelta(days=cc.FINAL_LAG)     # NOW (15 Oct) − the probe's edge


def ecpm(age):
    return 1.0 + 0.1 * age                                 # USD per 1000 impressions, by install age


def atom_micros(age):
    return int(round(USERS * IMPS * ecpm(age) / 1000 * 1e6))


class FakeGA:
    """One group of USERS users per (install day, country), active ages 0 .. 30, IMPS events each a day. skew: a kind's
    revenue is multiplied; meta: response metadata; fold: countries answered as "(other)" instead; refuse: kinds → 400."""

    def __init__(self, refuse=(), skew=None, meta=None, fold=()):
        self.refuse, self.skew, self.meta, self.fold = set(refuse), skew or {}, meta or {}, set(fold)
        self.bodies = []
        self.f0 = date(2025, 12, 1)

    @staticmethod
    def kind(body):
        dims = [x["name"] for x in body["dimensions"]]
        mets = [x["name"] for x in body["metrics"]]
        fl = {e["filter"]["fieldName"]: e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]}
        inl = (fl.get("firstSessionDate") or {}).get("inListFilter", {}).get("values")
        if "publisherAdImpressions" in mets:
            return "P6"
        if "countryId" not in dims:
            return "ET"
        return "EF" if inl is None else ("E14" if len(inl) == 14 else "E6")

    def __call__(self, method, url, token, body=None, params=None):
        assert method == "POST" and token == TOK and url.endswith("properties/%s:runReport" % PID)
        self.bodies.append(body)
        kind = self.kind(body)
        if kind in self.refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: DETAIL-PRIVATE")
        dims = [x["name"] for x in body["dimensions"]]
        mets = [x["name"] for x in body["metrics"]]
        fl = {e["filter"]["fieldName"]: e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]}
        inl = (fl.get("firstSessionDate") or {}).get("inListFilter", {}).get("values")
        d = date.fromisoformat(body["dateRanges"][0]["startDate"])
        agg = {}
        for i in range((date(2026, 10, 13) - self.f0).days + 1):
            x = self.f0 + timedelta(days=i)
            age = (d - x).days
            if not 0 <= age <= 30 or (inl is not None and x.strftime("%Y%m%d") not in inl):
                continue
            for c in CTRY:
                v = {"date": d.strftime("%Y%m%d"), "firstSessionDate": x.strftime("%Y%m%d"),
                     "countryId": "(other)" if c in self.fold else c}
                e = agg.setdefault(tuple(v[k] for k in dims), dict.fromkeys(mets, 0))
                rev = atom_micros(age) / 1e6 * self.skew.get(kind, 1.0)
                for m in mets:
                    e[m] += {"totalAdRevenue": rev, "eventCount": USERS * IMPS,
                             "publisherAdImpressions": USERS * IMPS}[m]
        rows = [{"dimensionValues": [{"value": v} for v in k], "metricValues": [{"value": str(e[m])} for m in mets]}
                for k, e in sorted(agg.items())]
        off, lim = body.get("offset", 0), body.get("limit", 10000)
        meta = dict({"currencyCode": "USD"}, **self.meta.get(kind, {}))
        return {"dimensionHeaders": [{"name": x} for x in dims], "metricHeaders": [{"name": x} for x in mets],
                "rows": rows[off:off + lim], "rowCount": len(rows), "metadata": meta,
                "propertyQuota": {"tokensPerDay": {"consumed": 2, "remaining": 199000}}}


def write_cube(tmp_path, days=None, scale=1.0):
    """A synthetic cube store in tmp_path: each day's "e" cells for the six install days, revenue scaled."""
    for d in days or (F, F - timedelta(days=30), F - timedelta(days=100), date(2026, 1, 14)):
        mo = {"v": gcu.V, "stream_id": SID, "days": {d.isoformat(): {"st": "ok"}}, "b": {}, "c": {}, "e": {}, "t": {},
              "loss": {}}
        for x in cc.installs(d, cc.AGES):
            age = (d - date.fromisoformat(x)).days
            for c in ("XA", "XB", "--"):
                mo["e"].setdefault(c, {})[x] = [0] * (age + 1) + [int(atom_micros(age) * scale)]
        path = gcu.month_path(str(tmp_path), AID, d.isoformat()[:7])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        old = gu.load_store(path)
        if old:
            for c, xs in mo["e"].items():
                old["e"].setdefault(c, {}).update(xs)
            old["days"].update(mo["days"])
            mo = old
        gu.save_store(path, mo)
    return str(tmp_path)


FS_SHARE = 0.5                                             # the first session's share of the install day (synthetic)


def write_nvr(data_dir, drop=(), stream=SID, share=FS_SHARE):
    """A synthetic ga4_nvr store beside the cube: per install day of the probe's days, every named country's first
    session ("n") = `share` of the install day's own revenue and impressions, plus a returning row (never a base).
    drop: (cc, X) pairs left without a first-session row."""
    days = {}
    for d in (F, F - timedelta(days=30), F - timedelta(days=100), date(2026, 1, 14)):
        for x in cc.installs(d, cc.AGES):
            rows = []
            for c in ("XA", "XB"):
                if (c, x) not in drop:
                    rows.append(["n", c, round(atom_micros(0) * share / 1e6, 4), int(USERS * IMPS * share)])
                rows.append(["r", c, 9.0, 9])
            rows.append(["n", "--", 9.0, 9])                          # not set: never a base
            days[x] = {"u": [], "c": rows, "s": []}
    path = os.path.join(data_dir, gv.DIR, KEY + ".json.gz")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gu.save_store(path, {"v": gv.STORE_V, "stream_id": stream, "days": days})
    return data_dir


def _run(monkeypatch, fake, data_dir=None, **opts):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    return cc.run_probe([unit()], "cid", "sec", [("o", RT)], dict({"app_calls": 50, "data_dir": data_dir}, **opts),
                        now=NOW)


# ── the request bodies ──────────────────────────────────────────────────────────────────────────

def test_request_bodies_of_each_read():
    d = F
    six = [x.replace("-", "") for x in cc.installs(d, cc.AGES)]
    r = {k: cc.request(k, d) for k in cc.KINDS}
    for k, q in r.items():
        assert q["body"]["dateRanges"] == [{"startDate": d.isoformat(), "endDate": d.isoformat()}]
        assert q["body"]["currencyCode"] == "USD" and q["body"]["keepEmptyRows"] is False
    dims = lambda k: [x["name"] for x in r[k]["body"]["dimensions"]]
    mets = lambda k: [x["name"] for x in r[k]["body"]["metrics"]]
    for k in ("E6", "E14", "EF", "P6"):
        assert dims(k) == ["date", "firstSessionDate", "countryId"]
    assert dims("ET") == ["date", "firstSessionDate"]
    for k in ("E6", "E14", "EF", "ET"):
        assert mets(k) == ["totalAdRevenue", "eventCount"] and r[k]["event"] == "ad_impression"
    assert mets("P6") == ["publisherAdImpressions", "totalAdRevenue"] and r["P6"]["event"] is None
    assert r["E6"]["extra"] == [ga4._in_list("firstSessionDate", sorted(six))] and len(six) == 6
    assert r["ET"]["extra"] == r["P6"]["extra"] == r["E6"]["extra"] and r["EF"]["extra"] == []
    vals = r["E14"]["extra"][0]["filter"]["inListFilter"]["values"]
    assert len(vals) == 14 and vals[0] == (d - timedelta(days=13)).strftime("%Y%m%d") and vals[-1] == d.strftime("%Y%m%d")


def test_the_sent_bodies_carry_the_stream_filter_and_the_event(monkeypatch):
    fake = FakeGA()
    _run(monkeypatch, fake)
    assert len(fake.bodies) == 5 * 4
    for b in fake.bodies:
        names = {e["filter"]["fieldName"] for e in b["dimensionFilter"]["andGroup"]["expressions"]}
        assert {"platform", "streamId"} <= names
        assert ("eventName" in names) == ("publisherAdImpressions" not in [m["name"] for m in b["metrics"]])


def test_the_days_asked():
    hs = date(2026, 1, 1)
    assert cc.pick_days(F, hs) == [F, F - timedelta(days=30), F - timedelta(days=100), date(2026, 1, 14)]
    assert cc.pick_days(F, date(2024, 1, 1))[-1] == F - timedelta(days=480)
    assert cc.pick_days(F, F - timedelta(days=20)) == [F, F - timedelta(days=7)]      # the oldest day with 13 behind it
    assert cc.pick_days(F, F - timedelta(days=60))[0:2] == [F, F - timedelta(days=30)]


# ── a whole run ─────────────────────────────────────────────────────────────────────────────────

def test_a_consistent_app_is_go_and_every_comparison_ties(monkeypatch, tmp_path, capsys):
    rep = _run(monkeypatch, FakeGA(), write_cube(tmp_path))
    a = list(rep["apps"].values())[0]
    assert a["complete"] and len(a["days"]) == 4
    assert a["verdict"]["verdict"] == "go" and all(v is True for v in a["verdict"]["checks"].values())
    day = a["days"][F.isoformat()]
    assert all(r["ok"] and r["rows"] > 0 and r["tok"] == 2 for r in day["reads"].values())
    c = day["cmp"]
    assert c["ef"]["rev"] == 1.0 and c["ef"]["cnt"] == 1.0 and c["ef"]["equal"] == c["ef"]["a"] == 6 * 3
    assert c["e14"]["rev"] == 1.0 and c["p6"]["cnt"] == 1.0 and c["p6"]["near"] == c["p6"]["a"]
    assert c["cov_min"] == 1.0 and set(c["cov"]) == set(cc.installs(F, cc.AGES))
    assert c["cube"]["day"] and c["cube"]["rev"] == 1.0 and c["cube"]["only_cube"] == 0
    rep_counts = rep["counts"]
    assert rep_counts == dict(apps=1, reads=20, accepted=20, refused=0, failed=0, go=1, nogo=0, unknown=0,
                              calls=20, seconds=rep_counts["seconds"])
    line = cc.public_line(rep_counts)
    out = capsys.readouterr().out + line
    for s in SECRETS + list(CTRY) + [F.isoformat()]:
        assert s not in out
    assert re.fullmatch(r"cecpm probe: apps \d+, reads \d+, accepted \d+, refused \d+, failed \d+, go \d+, nogo \d+, "
                        r"unknown \d+, calls \d+, \d+s", line)
    assert all(re.fullmatch(r"cecpm progress: (calls \d+, \d+s|apps \d+/\d+, calls \d+, \d+s)", ln)
               for ln in out.splitlines() if ln.startswith("cecpm progress"))


def test_a_cube_that_disagrees_is_nogo_and_no_cube_is_unknown(monkeypatch, tmp_path):
    a = list(_run(monkeypatch, FakeGA(), write_cube(tmp_path, scale=0.9))["apps"].values())[0]
    assert a["verdict"]["checks"]["cube_tie"] is False and a["verdict"]["verdict"] == "nogo"
    b = list(_run(monkeypatch, FakeGA(), None)["apps"].values())[0]               # no private clone at all
    assert b["verdict"]["checks"]["cube_tie"] is None and b["verdict"]["verdict"] == "unknown"
    assert all(d["cmp"]["cube"] == {"day": False} for d in b["days"].values())


def test_ef_that_differs_and_et_that_does_not_cover_are_nogo(monkeypatch, tmp_path):
    cube = write_cube(tmp_path)
    a = list(_run(monkeypatch, FakeGA(skew={"EF": 1.5}), cube)["apps"].values())[0]
    assert a["verdict"]["checks"]["ef_equal"] is False and a["verdict"]["verdict"] == "nogo"
    b = list(_run(monkeypatch, FakeGA(skew={"ET": 1.5}), cube)["apps"].values())[0]
    assert b["verdict"]["checks"]["coverage"] is False and b["days"][F.isoformat()]["cmp"]["cov_min"] < cc.COVERAGE_MIN


def test_a_refused_e6_is_nogo_and_a_refused_diagnostic_read_is_not_a_failure(monkeypatch, tmp_path):
    cube = write_cube(tmp_path)
    rep = _run(monkeypatch, FakeGA(refuse=("E6",)), cube)
    a = list(rep["apps"].values())[0]
    assert a["verdict"]["checks"]["e6_whole"] is False and a["verdict"]["verdict"] == "nogo"
    assert a["days"][F.isoformat()]["reads"]["E6"]["err"] == {"http": 400, "status": "INVALID_ARGUMENT"}
    assert "DETAIL" not in str(rep) and rep["counts"]["refused"] == 4 and rep["counts"]["nogo"] == 1
    b = list(_run(monkeypatch, FakeGA(refuse=("E14", "P6")), cube)["apps"].values())[0]
    assert b["verdict"]["verdict"] == "go"                                       # E14 / P6 are informational


def test_flags_sampling_and_other_rows(monkeypatch, tmp_path):
    cube = write_cube(tmp_path)
    s = list(_run(monkeypatch, FakeGA(meta={"E6": {"samplingMetadatas": [{"samplesReadCount": "1",
                                                                        "samplingSpaceSize": "4"}]}}), cube)["apps"]
             .values())[0]
    assert s["verdict"]["checks"]["unsampled"] is False and s["verdict"]["verdict"] == "nogo"
    assert s["days"][F.isoformat()]["reads"]["E6"]["sampled"] and s["days"][F.isoformat()]["reads"]["E6"]["smp_frac"] == 0.25
    o = list(_run(monkeypatch, FakeGA(fold=("XB",), meta={"E6": {"dataLossFromOtherRow": True}}), cube)["apps"].values())[0]
    day = o["days"][F.isoformat()]
    assert day["reads"]["E6"]["loss"] and day["reads"]["E6"]["other_rows"] > 0 and day["cmp"]["unflagged"] is False
    assert o["verdict"]["checks"]["coverage"] is None                           # flagged days are not judged on coverage


# ── the call cap / quota stop ───────────────────────────────────────────────────────────────────

def test_the_call_cap_stops_cleanly_and_keeps_what_was_read(monkeypatch, tmp_path, capsys):
    fake = FakeGA()
    rep = _run(monkeypatch, fake, write_cube(tmp_path), max_calls=7)
    a = list(rep["apps"].values())[0]
    assert len(fake.bodies) == 7 and a["stopped"] == "calls" and not a["complete"]
    assert len(a["days"][F.isoformat()]["reads"]) == 5 and len(a["days"][(F - timedelta(days=30)).isoformat()]["reads"]) == 2
    assert a["verdict"]["verdict"] == "unknown" and rep["counts"]["reads"] == 7 and rep["counts"]["accepted"] == 7
    assert cc.MAX_CALLS == 650 and rep["rules"]["max_calls"] == 7
    assert "stopped" not in capsys.readouterr().out


def test_a_quota_stop_ends_the_property_and_keeps_the_reads(monkeypatch):
    class Low(FakeGA):
        def __call__(self, *a, **k):
            j = super().__call__(*a, **k)
            if len(self.bodies) >= 3:
                j["propertyQuota"] = {"tokensPerDay": {"consumed": 190000, "remaining": 10000}}
            return j
    fake = Low()
    a = list(_run(monkeypatch, fake)["apps"].values())[0]
    assert len(fake.bodies) == 3 and a["stopped"] == "quota_low" and a["verdict"]["verdict"] == "unknown"
    assert sum(len(d["reads"]) for d in a["days"].values()) == 3


def test_the_per_app_cap_stops_only_that_app(monkeypatch):
    fake = FakeGA()
    a = list(_run(monkeypatch, fake, app_calls=4)["apps"].values())[0]
    assert len(fake.bodies) == 4 and a["stopped"] == "app_cap" and not a["complete"]


# ── the cell maths ──────────────────────────────────────────────────────────────────────────────

def test_cells_of_routes_rows_and_counts_the_ones_in_no_cell():
    d = date(2026, 10, 12)
    rows = [{"date": "20261012", "firstSessionDate": "20261012", "countryId": "XA", "totalAdRevenue": 0.5, "eventCount": 10},
            {"date": "20261012", "firstSessionDate": "20261011", "countryId": "(not set)", "totalAdRevenue": 0.25,
             "eventCount": 4},
            {"date": "20261012", "firstSessionDate": "20261011", "countryId": "", "totalAdRevenue": 0.25, "eventCount": 6},
            {"date": "20261012", "firstSessionDate": "(other)", "countryId": "XA", "totalAdRevenue": 9, "eventCount": 9},
            {"date": "20261012", "firstSessionDate": "20261011", "countryId": "(other)", "totalAdRevenue": 9, "eventCount": 9},
            {"date": "20261012", "firstSessionDate": "20261013", "countryId": "XA", "totalAdRevenue": 9, "eventCount": 9},
            {"date": "20261011", "firstSessionDate": "20261011", "countryId": "XA", "totalAdRevenue": 9, "eventCount": 9}]
    cells, rest = cc.cells_of(rows, d, ("totalAdRevenue", "eventCount"))
    assert cells == {("XA", "2026-10-12", 0): [500000, 10], ("--", "2026-10-11", 1): [500000, 10]} and rest == 4


def test_overlap_and_cmp_cells():
    a = {("XA", "x", 0): [100, 10], ("XB", "x", 0): [100, 10]}
    b = {("XA", "x", 0): [100, 10], ("XB", "x", 0): [50, 10], ("XC", "x", 0): [50, 5]}
    assert cc.overlap(a, a, 0) == 1.0 and cc.overlap(a, b, 0) == round(150 / 250, 6) and cc.overlap({}, {}, 0) is None
    c = cc.cmp_cells(a, b)
    assert (c["a"], c["b"], c["both"], c["only_a"], c["only_b"], c["equal"]) == (2, 3, 2, 0, 1, 1)
    assert c["rev"] == 0.6 and c["cnt"] == round(20 / 25, 6) and c["rev_ratio"] == 1.0 and c["cnt_ratio"] == 1.25


def test_p6_against_e6_per_cell():
    e6 = {("XA", "x", 0): [100, 100], ("XB", "x", 0): [100, 100], ("XC", "x", 0): [100, 100]}
    p6 = {("XA", "x", 0): [100, 101], ("XB", "x", 0): [100, 80], ("XC", "x", 0): [100, 100]}
    c = cc.cmp_cells(e6, p6)
    assert c["near"] == 2 and c["equal"] == 1 and c["cnt_ratio"] == round(281 / 300, 4)


def test_coverage_is_sigma_countries_over_the_no_country_read():
    e6 = {("XA", "x1", 0): [60, 6], ("XB", "x1", 0): [39, 3], ("XA", "x2", 1): [50, 5]}
    et = {"x1": [100, 10], "x2": [50, 5], "x3": [0, 0]}
    out, mn = cc.coverage(e6, et)
    assert out == {"x1": [0.99, 0.9], "x2": [1.0, 1.0]} and mn == 0.9                 # x3: nothing to judge
    assert cc.coverage({}, {}) == ({}, None)


def test_cube_cells_reads_the_months_e_cells(tmp_path):
    d = F
    data = write_cube(tmp_path, days=[d])
    xs = cc.installs(d, cc.AGES)
    got, led = cc.cube_cells(data, unit(), d, xs)
    assert led == {"st": "ok"} and cc.cube_clean(led) and not cc.cube_clean({"st": "ok", "fl": 1})
    assert not cc.cube_clean({"ol": 5}) and not cc.cube_clean({"via": "split", "loss": 3}) and cc.cube_clean({"ol": 0})
    assert len(got) == 3 * 6 and got[("XA", d.isoformat(), 0)] == [atom_micros(0), 0]
    assert got[("XB", (d - timedelta(days=13)).isoformat(), 13)] == [atom_micros(13), 0]
    assert cc.cube_cells(data, unit(), d - timedelta(days=1), xs) is None            # not folded
    assert cc.cube_cells(None, unit(), d, xs) is None and cc.cube_cells(str(tmp_path / "x"), unit(), d, xs) is None


# ── the day-1 base (the first session; informational) ───────────────────────────────────────────

def test_the_day_one_base_is_measured_and_never_judged(monkeypatch, tmp_path):
    data = write_nvr(write_cube(tmp_path))
    a = list(_run(monkeypatch, FakeGA(), data)["apps"].values())[0]
    assert a["verdict"]["verdict"] == "go" and "fs" not in a["verdict"]["checks"]
    day = a["days"][F.isoformat()]["cmp"]["fs"]
    assert day["held"] == 6 and day["ret_cells"] == 2 * 5 == day["ret_cells_base"]       # XA, XB at ages 1 .. 13
    assert a["fs"] == {"days": 4, "held": 24, "base": 1.0, "base_cells": 1.0, "rev0": FS_SHARE, "imp0": FS_SHARE,
                       "ecpm0": 1.0}


def test_a_missing_base_lowers_the_share_and_no_store_is_said(monkeypatch, tmp_path):
    x = (F - timedelta(days=13)).isoformat()
    data = write_nvr(write_cube(tmp_path), drop={("XA", x)})
    a = list(_run(monkeypatch, FakeGA(), data)["apps"].values())[0]
    day = a["days"][F.isoformat()]["cmp"]["fs"]
    assert day["ret_cells_base"] == day["ret_cells"] - 1
    assert day["ret_base"] == day["ret"] - atom_micros(13)
    assert a["verdict"]["verdict"] == "go"                                              # informational only
    b = list(_run(monkeypatch, FakeGA(), write_cube(tmp_path / "other"))["apps"].values())[0]
    assert all(d["cmp"]["fs"] == {"store": False} for d in b["days"].values()) and b["fs"] is None
    c = list(_run(monkeypatch, FakeGA(), write_nvr(write_cube(tmp_path / "s2"), stream="9000000002"))["apps"]
             .values())[0]
    assert c["fs"] is None                                                              # another stream's store


def test_a_broken_store_costs_only_the_base_check(monkeypatch, tmp_path):
    data = write_cube(tmp_path)
    path = os.path.join(data, gv.DIR, KEY + ".json.gz")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gu.save_store(path, {"v": gv.STORE_V, "stream_id": SID, "days": {F.isoformat(): {"c": [["n", "XA", "x", 1]]}}})
    a = list(_run(monkeypatch, FakeGA(), data)["apps"].values())[0]
    day = a["days"][F.isoformat()]["cmp"]
    assert day["fs"].get("err") and day["cube"]["rev"] == 1.0 and a["verdict"]["verdict"] == "go"


# ── the verdict ─────────────────────────────────────────────────────────────────────────────────

def _day(ef=(1.0, 1.0), cov=1.0, unflagged=True, cube=(100, 100), e6=None, clean=True, reads=("EF", "ET"), **flags):
    rec = dict({"ok": True, "cut": False, "loss": False, "sampled": False, "other_rows": 0}, **flags)
    rd = dict({k: {"ok": True} for k in reads}, E6=e6 or rec)
    return {"reads": rd, "cmp": {"ef": {"rev": ef[0], "cnt": ef[1]}, "cov_min": cov, "unflagged": unflagged,
                                 "cube": {"day": True, "lo": cube[0], "hi": cube[1], "clean": clean}}}


def test_verdict_thresholds():
    v = lambda *days, complete=True: cc.verdict({str(i): d for i, d in enumerate(days)}, complete)
    assert v(_day())["verdict"] == "go"
    assert v(_day(cov=0.98))["verdict"] == "go" and v(_day(cov=0.9799))["checks"]["coverage"] is False
    assert v(_day(cube=(99, 100)))["verdict"] == "go" and v(_day(cube=(98.9, 100)))["checks"]["cube_tie"] is False
    assert v(_day(ef=(0.999, 1.0)))["verdict"] == "go" and v(_day(ef=(0.9989, 1.0)))["checks"]["ef_equal"] is False
    assert v(_day(ef=(1.0, 0.9)))["verdict"] == "nogo"
    assert v(_day(sampled=True))["checks"]["unsampled"] is False
    assert v(_day(cut=True))["checks"]["e6_whole"] is False
    assert v(_day(cov=0.5, unflagged=False))["checks"]["coverage"] is None             # flagged: not judged
    assert v(_day(cov=0.5, unflagged=False))["verdict"] == "unknown"
    assert v(_day(), complete=False)["verdict"] == "unknown"
    assert v(_day(cube=(98, 100)), _day(cube=(100, 100)))["checks"]["cube_tie"] is True    # pooled over the days: 198/200
    assert v(_day(), _day(sampled=True))["verdict"] == "nogo"
    assert cc.verdict({}, True)["verdict"] == "unknown"
    # a refused E6 is False, one that failed some other way is not judged
    assert v(_day(e6={"ok": False, "err": {"http": 400}}))["checks"]["e6_whole"] is False
    assert v(_day(e6={"ok": False, "err": {"http": 503}}))["checks"]["e6_whole"] is None
    # nothing to compare (no ad rows on either side) is no evidence either way — never a "nogo"
    assert v(_day(ef=(None, None)), _day())["verdict"] == "go"
    assert v(_day(ef=(None, None)))["checks"]["ef_equal"] is None
    assert v(_day(ef=(None, 1.0)))["checks"]["ef_equal"] is True and v(_day(ef=(None, 0.9)))["checks"]["ef_equal"] is False
    assert v(_day(ef=(0.0, 1.0)))["checks"]["ef_equal"] is False
    # a diagnostic read refused: that day is not required; a comparison that was not made: not judged (never "go")
    assert v(_day(reads=("ET",)), _day())["checks"]["ef_equal"] is True
    broken = _day()
    broken["cmp"].pop("ef")
    assert v(broken, _day())["checks"]["ef_equal"] is None and v(broken, _day())["verdict"] == "unknown"
    nocov = _day()
    nocov["cmp"].pop("unflagged")
    assert v(nocov, _day())["checks"]["coverage"] is None
    # only days the cube itself read whole are tied
    assert v(_day(cube=(50, 100), clean=False), _day())["checks"]["cube_tie"] is True
    assert v(_day(cube=(50, 100), clean=False))["checks"]["cube_tie"] is None


def test_counts_name_nothing():
    run = type("R", (), {"calls": 9, "elapsed": lambda self: 3})()
    apps = {"k1": {"days": {"d": {"reads": {"E6": {"ok": True}, "EF": {"ok": False, "err": {"http": 400}},
                                            "P6": {"ok": False, "err": {"http": 503}}}}}, "verdict": {"verdict": "go"}},
            "k2": {"verdict": {"verdict": "nogo"}}, "k3": {"crash": "ValueError"}}
    c = cc.counts(apps, run)
    assert c == dict(apps=3, reads=3, accepted=1, refused=1, failed=1, go=1, nogo=1, unknown=1, calls=9, seconds=3)
    assert cc.public_line(c) == "cecpm probe: apps 3, reads 3, accepted 1, refused 1, failed 1, go 1, nogo 1, unknown 1, calls 9, 3s"


# ── main: the clone's layout, the call cap input, apps carried over ─────────────────────────────────────────────────

def _main_env(monkeypatch, tmp_path, fake, inputs=None, last=None):
    root = tmp_path / "_private"
    data = root / "data"
    write_nvr(write_cube(data))
    if last is not None:
        os.makedirs(root / "ga4", exist_ok=True)
        with open(root / cc.OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(last, f)
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    seen = {}
    monkeypatch.setattr(cc.sp, "load_state", lambda r: seen.setdefault("root", r) and {"x": 1})
    monkeypatch.setattr(cc.cp, "units_from_state", lambda st: [unit()])
    wrote = {}
    monkeypatch.setattr(cc.pr, "write_private", lambda path, raw, msg: wrote.update(path=path, raw=raw) or True)
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKENS": json.dumps({"o": RT}),
           "CECPM_DATA_DIR": str(root)}
    if inputs is not None:
        ev = tmp_path / "event.json"
        ev.write_text(json.dumps({"inputs": inputs}))
        env["GITHUB_EVENT_PATH"] = str(ev)
    cc.main(env=env, now=NOW)
    return seen, json.loads(wrote["raw"]), str(root)


def test_main_reads_the_routes_from_the_clone_and_ties_to_its_data_folder(monkeypatch, tmp_path, capsys):
    seen, rep, root = _main_env(monkeypatch, tmp_path, FakeGA())
    a = rep["apps"][KEY]
    assert seen["root"] == root                                          # (sp adds data/ for the routes itself)
    assert a["verdict"]["verdict"] == "go" and a["verdict"]["checks"]["cube_tie"] is True
    assert a["fs"]["base"] == 1.0 and a["days"][F.isoformat()]["cmp"]["cube"]["clean"] is True
    out = capsys.readouterr().out
    for sec in SECRETS + [F.isoformat()]:
        assert sec not in out


def test_main_without_the_private_clone_makes_no_ga4_call(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ga4, "_call", lambda *a, **k: calls.append(1))
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKEN": RT,
           "CECPM_DATA_DIR": str(tmp_path / "none")}
    try:
        cc.main(env=env, now=NOW)
        assert False, "should exit"
    except SystemExit as e:
        assert "no private clone" in str(e)
    assert calls == []


def test_the_call_cap_input_and_apps_carried_over(monkeypatch, tmp_path):
    fake = FakeGA()
    old = {"v": 1, "rules": cc.rules(cc.MAX_CALLS), "apps": {"k-other": {"key": "k-other", "complete": True}}}
    seen, rep, root = _main_env(monkeypatch, tmp_path, fake, inputs={"max_calls": "7"}, last=old)
    assert len(fake.bodies) == 7 and rep["rules"]["max_calls"] == 7
    assert rep["apps"]["k-other"] == {"key": "k-other", "complete": True}            # carried over as it was
    other = dict(old, rules=dict(old["rules"], offsets=[0, 1]))
    seen, rep2, _ = _main_env(monkeypatch, tmp_path / "b", FakeGA(), last=other)
    assert "k-other" not in rep2["apps"]                                 # made under other rules: never mixed in


def test_a_stop_mid_day_still_compares_the_reads_made(monkeypatch, tmp_path):
    rep = _run(monkeypatch, FakeGA(), write_cube(tmp_path), max_calls=6)
    a = list(rep["apps"].values())[0]
    d2 = a["days"][(F - timedelta(days=30)).isoformat()]
    assert list(d2["reads"]) == ["E6"] and d2["cmp"]["cube"]["day"] and d2["cmp"]["cube"]["rev"] == 1.0
    assert a["verdict"]["verdict"] == "unknown" and a["stopped"] == "calls"

