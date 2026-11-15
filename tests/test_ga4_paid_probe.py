"""GA4 paid / organic split probe (admob_iq.fetch.ga4_paid_probe) — offline against a small fake GA4 (SYNTHETIC: made-up
countries and money): the seven reads' request bodies (the first-user-channel filter and its NOT), the day picking, the
CP + CO ties (also with "(other)" rows and a missing CO), the verdict branches, the Ads installs comparison, a PUBLIC log
that carries counts only, the workflow file and the private output's shape."""
import gzip
import json
import os
import re
from datetime import date, timedelta

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_paid_probe as pp
from tests.test_ga4_device_probe import AID, KEY, NOW, PID, RT, SECRETS, SID, TOK, unit

CTRY = ("XA", "XB", "(not set)")
USERS = 10
NEWU = 100                                                 # new users a country a day (all sources)
PSHARE = 0.4                                               # the paid share of users and revenue (synthetic)
F = date(2026, 10, 15) - timedelta(days=pp.FINAL_LAG)
HS = date(2026, 1, 1)


def atom_micros(age):
    return int(round(USERS * (1.0 + 0.1 * age) * 5 / 1000 * 1e6))


class FakeGA:
    """USERS users per (install day, country), active ages 0 .. 30. The paid channel holds PSHARE of them, everyone else
    the rest. skew: a kind's revenue multiplied; meta: response metadata; fold: countries answered as "(other)"; refuse:
    kinds → 400."""

    def __init__(self, refuse=(), skew=None, meta=None, fold=()):
        self.refuse, self.skew, self.meta, self.fold = set(refuse), skew or {}, meta or {}, set(fold)
        self.bodies = []
        self.f0 = date(2025, 12, 1)

    @staticmethod
    def kind(body):
        dims = [x["name"] for x in body["dimensions"]]
        top = body["dimensionFilter"]["andGroup"]["expressions"]
        filt = [e for e in top if "notExpression" in e or e["filter"]["fieldName"] == pp.CHANNEL]
        mode = "0" if not filt else ("O" if "notExpression" in filt[0] else "P")
        base = "N" if "newUsers" in [m["name"] for m in body["metrics"]] else ("T" if "countryId" not in dims else "C")
        return base + mode

    def __call__(self, method, url, token, body=None, params=None):
        assert method == "POST" and token == TOK and url.endswith("properties/%s:runReport" % PID)
        self.bodies.append(body)
        kind = self.kind(body)
        if kind in self.refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: DETAIL-PRIVATE")
        share = {"0": 1.0, "P": PSHARE, "O": 1 - PSHARE}[kind[1]]
        dims = [x["name"] for x in body["dimensions"]]
        mets = [x["name"] for x in body["metrics"]]
        d = date.fromisoformat(body["dateRanges"][0]["startDate"])
        agg = {}
        for i in range((date(2026, 10, 13) - self.f0).days + 1):
            x = self.f0 + timedelta(days=i)
            age = (d - x).days
            if not 0 <= age <= 30 or (kind[0] == "N" and age != 0):
                continue
            for c in CTRY:
                v = {"date": d.strftime("%Y%m%d"), "firstSessionDate": x.strftime("%Y%m%d"),
                     "countryId": "(other)" if c in self.fold else c}
                e = agg.setdefault(tuple(v[k] for k in dims), dict.fromkeys(mets, 0))
                for m in mets:
                    e[m] += {"totalAdRevenue": atom_micros(age) / 1e6 * share * self.skew.get(kind, 1.0),
                             "activeUsers": USERS * share, "newUsers": NEWU * share}[m]
        rows = [{"dimensionValues": [{"value": v} for v in k], "metricValues": [{"value": str(e[m])} for m in mets]}
                for k, e in sorted(agg.items())]
        off, lim = body.get("offset", 0), body.get("limit", 10000)
        meta = dict({"currencyCode": "USD"}, **self.meta.get(kind, {}))
        return {"dimensionHeaders": [{"name": x} for x in dims], "metricHeaders": [{"name": x} for x in mets],
                "rows": rows[off:off + lim], "rowCount": len(rows), "metadata": meta,
                "propertyQuota": {"tokensPerDay": {"consumed": 2, "remaining": 199000}}}


ADS = 40                                                   # Google Ads installs a country a day (= the paid new users)


def write_site(root, key=KEY, days=None, ads=ADS):
    """A synthetic site folder: roi_<key>.json.gz and one country pack; every probe day of XA and XB has ads installs."""
    site = os.path.join(str(root), "site")
    os.makedirs(site, exist_ok=True)
    pack = "roi_%s_c00.json.gz" % key
    rows = [[d.isoformat(), 90, ads, 3.5] for d in (days or (F, F - timedelta(days=30), F - timedelta(days=100), HS))]
    with gzip.open(os.path.join(site, pack), "wt", encoding="utf-8") as f:
        json.dump({"v": 1, "c": {"XA": rows, "XB": rows, "XX": rows}}, f)
    with gzip.open(os.path.join(site, "roi_%s.json.gz" % key), "wt", encoding="utf-8") as f:
        json.dump({"cd": {"packs": [[pack, "abc"], ["../evil.json.gz", "x"]]}}, f)
    return site


def _run(monkeypatch, fake, site=None, **opts):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    return pp.run_probe([unit()], "cid", "sec", [("o", RT)], dict({"app_calls": 50, "site_dir": site}, **opts), now=NOW)


def _app(rep):
    return list(rep["apps"].values())[0]


# ── the request bodies ──────────────────────────────────────────────────────────────────────────

def test_request_bodies_of_each_read():
    d = F
    r = {k: pp.request(k, d) for k in pp.KINDS}
    paid = {"filter": {"fieldName": "firstUserDefaultChannelGroup",
                       "inListFilter": {"values": ["Cross-network", "Paid Search"]}}}
    for k, q in r.items():
        assert q["body"]["dateRanges"] == [{"startDate": d.isoformat(), "endDate": d.isoformat()}]
        assert q["body"]["currencyCode"] == "USD" and q["body"]["keepEmptyRows"] is False
    dims = lambda k: [x["name"] for x in r[k]["body"]["dimensions"]]
    mets = lambda k: [x["name"] for x in r[k]["body"]["metrics"]]
    for k in ("C0", "CP", "CO"):
        assert dims(k) == ["date", "firstSessionDate", "countryId"] and mets(k) == ["activeUsers", "totalAdRevenue"]
        # the cube's own body, with the channel filter on top
        assert r[k]["body"] == pp.gcu.body(d, d)
    for k in ("T0", "TP"):
        assert dims(k) == ["date", "firstSessionDate"] and mets(k) == ["activeUsers", "totalAdRevenue"]
    for k in ("N0", "NP"):
        assert dims(k) == ["date", "countryId"] and mets(k) == ["newUsers"]
    assert r["CP"]["extra"] == r["TP"]["extra"] == r["NP"]["extra"] == [paid]
    assert r["CO"]["extra"] == [{"notExpression": paid}]
    assert r["C0"]["extra"] == r["T0"]["extra"] == r["N0"]["extra"] == []
    # the filter JSON as the sent body carries it (stream filter first, the channel filter last)
    sent = ga4.stream_filter(SID, extra=r["CO"]["extra"])["andGroup"]["expressions"]
    assert sent[-1] == {"notExpression": {"filter": {"fieldName": "firstUserDefaultChannelGroup",
                                                     "inListFilter": {"values": ["Cross-network", "Paid Search"]}}}}
    assert json.loads(json.dumps(r["CP"]["extra"][0]))["filter"]["inListFilter"]["values"] == ["Cross-network", "Paid Search"]


def test_the_sent_bodies_carry_the_stream_filter_and_the_channel(monkeypatch):
    fake = FakeGA()
    _run(monkeypatch, fake)
    assert len(fake.bodies) == 7 * 4
    kinds = {}
    for b in fake.bodies:
        ex = b["dimensionFilter"]["andGroup"]["expressions"]
        names = {e["filter"]["fieldName"] for e in ex if "filter" in e}
        assert {"platform", "streamId"} <= names and "eventName" not in names
        kinds[fake.kind(b)] = kinds.get(fake.kind(b), 0) + 1
    assert kinds == {k: 4 for k in pp.KINDS}
    nots = [b for b in fake.bodies if any("notExpression" in e for e in b["dimensionFilter"]["andGroup"]["expressions"])]
    assert len(nots) == 4 and all(fake.kind(b) == "CO" for b in nots)


def test_the_days_asked():
    assert pp.pick_days(F, HS) == [F, F - timedelta(days=30), F - timedelta(days=100), HS]      # F − 300 is before HS
    assert pp.pick_days(F, date(2024, 1, 1)) == [F - timedelta(days=n) for n in (0, 30, 100, 300)]
    assert pp.pick_days(F, F - timedelta(days=20)) == [F, F - timedelta(days=20)]               # nearest valid day, once
    assert pp.pick_days(F) == [F - timedelta(days=n) for n in (0, 30, 100, 300)]
    assert pp.pick_days(F, F + timedelta(days=1)) == []                                          # (a history after F: none)


# ── a whole run ─────────────────────────────────────────────────────────────────────────────────

def test_a_consistent_app_is_go_and_everything_ties(monkeypatch, tmp_path, capsys):
    rep = _run(monkeypatch, FakeGA(), write_site(tmp_path))
    a = _app(rep)
    assert a["complete"] and len(a["days"]) == 4
    assert a["verdict"] == {"checks": {"whole": True, "tie": True}, "verdict": "go"}
    day = a["days"][F.isoformat()]
    assert all(r["ok"] and r["rows"] > 0 and r["tok"] == 2 and not r["cut"] for r in day["reads"].values())
    c = day["cmp"]
    assert c["tie"]["rev"] == 1.0 and c["tie"]["users"] == 1.0 and c["tie"]["rev_ratio"] == 1.0
    assert c["tie"]["users_ratio"] == 1.0 and c["tie"]["only_c0"] == 0 and c["tie"]["only_merged"] == 0
    assert c["share"] == {"rev": PSHARE, "users": PSHARE}
    assert c["cov_p_min"] == 1.0 and c["cov_0_min"] == 1.0 and len(c["cov_p"]) == 31
    ads = c["ads"]
    assert ads["data"] and ads["ads"] == 2 * ADS and ads["np"] == 2 * NEWU * PSHARE and ads["np_ratio"] == 1.0
    assert ads["np_median"] == 1.0 and ads["n0_ratio"] == 2.5 and ads["n0_median"] == 2.5 and ads["judged"] == 2
    assert rep["counts"] == dict(apps=1, reads=28, accepted=28, refused=0, failed=0, go=1, nogo=0, unknown=0, calls=28,
                                 seconds=rep["counts"]["seconds"])
    line = pp.public_line(rep["counts"])
    out = capsys.readouterr().out + line
    for s in SECRETS + list(CTRY) + [F.isoformat()]:
        assert s not in out
    assert re.fullmatch(r"paid probe: apps \d+, reads \d+, accepted \d+, refused \d+, failed \d+, go \d+, nogo \d+, "
                        r"unknown \d+, calls \d+, \d+s", line)


def test_no_site_files_leave_the_ads_comparison_empty_and_the_verdict_alone(monkeypatch, tmp_path):
    a = _app(_run(monkeypatch, FakeGA(), None))
    assert a["verdict"]["verdict"] == "go" and a["days"][F.isoformat()]["cmp"]["ads"] == {"data": False}


def test_halves_that_do_not_add_up_are_nogo(monkeypatch):
    a = _app(_run(monkeypatch, FakeGA(skew={"CO": 0.9})))
    t = a["days"][F.isoformat()]["cmp"]["tie"]
    assert t["rev"] < pp.TIE_MIN and t["users"] == 1.0                          # (users are reported, never judged)
    assert a["verdict"]["checks"] == {"whole": True, "tie": False} and a["verdict"]["verdict"] == "nogo"
    u = _app(_run(monkeypatch, FakeGA()))
    assert u["verdict"]["verdict"] == "go"


def test_other_rows_make_the_app_not_whole(monkeypatch):
    a = _app(_run(monkeypatch, FakeGA(fold=("XB",))))
    day = a["days"][F.isoformat()]
    assert day["reads"]["CP"]["other_rows"] > 0 and day["reads"]["CO"]["other_rows"] > 0
    assert a["verdict"]["checks"]["whole"] is False and a["verdict"]["verdict"] == "nogo"


def test_flags_sampling_thresholding_and_loss_make_it_not_whole(monkeypatch):
    for kind, m, flag in (("CP", {"samplingMetadatas": [{"samplesReadCount": "1", "samplingSpaceSize": "4"}]}, "sampled"),
                          ("CO", {"subjectToThresholding": True}, "thresh"),
                          ("CP", {"dataLossFromOtherRow": True}, "loss")):
        a = _app(_run(monkeypatch, FakeGA(meta={kind: m})))
        assert a["days"][F.isoformat()]["reads"][kind][flag] is True
        assert a["verdict"]["checks"]["whole"] is False and a["verdict"]["verdict"] == "nogo"
    # a flag on a diagnostic read is not the verdict's business
    b = _app(_run(monkeypatch, FakeGA(meta={"NP": {"dataLossFromOtherRow": True}})))
    assert b["verdict"]["verdict"] == "go"


def test_a_refused_co_is_nogo_and_a_refused_diagnostic_read_is_not(monkeypatch):
    rep = _run(monkeypatch, FakeGA(refuse=("CO",)))
    a = _app(rep)
    assert a["verdict"]["checks"]["whole"] is False and a["verdict"]["verdict"] == "nogo"
    assert a["days"][F.isoformat()]["reads"]["CO"]["err"] == {"http": 400, "status": "INVALID_ARGUMENT"}
    assert "DETAIL" not in str(rep) and rep["counts"]["refused"] == 4 and rep["counts"]["nogo"] == 1
    assert "tie" not in a["days"][F.isoformat()]["cmp"]                            # (no CO: no tie to make)
    b = _app(_run(monkeypatch, FakeGA(refuse=("TP", "T0", "NP", "N0"))))
    assert b["verdict"]["verdict"] == "go"


def test_a_co_that_was_never_read_is_unknown(monkeypatch):
    fake = FakeGA()
    rep = _run(monkeypatch, fake, max_calls=2)
    a = _app(rep)
    d = a["days"][F.isoformat()]
    assert list(d["reads"]) == ["C0", "CP"] and "tie" not in d["cmp"] and d["cmp"]["share"]["rev"] == PSHARE
    assert a["stopped"] == "calls" and not a["complete"] and len(fake.bodies) == 2
    assert a["verdict"] == {"checks": {"whole": None, "tie": None}, "verdict": "unknown"}


def test_a_quota_stop_keeps_the_reads(monkeypatch):
    class Low(FakeGA):
        def __call__(self, *a, **k):
            j = super().__call__(*a, **k)
            j["propertyQuota"] = {"tokensPerDay": {"consumed": 2, "remaining": 1}}
            return j
    a = _app(_run(monkeypatch, Low()))
    assert a.get("stopped") and not a["complete"] and a["verdict"]["verdict"] == "unknown"
    assert a["days"][F.isoformat()]["reads"]["C0"]["ok"]


def test_the_per_app_cap_stops_only_that_app(monkeypatch):
    a = _app(_run(monkeypatch, FakeGA(), app_calls=9))
    assert a["stopped"] == "app_cap" and len(a["days"]) == 2


# ── cells, ties, the Ads comparison ─────────────────────────────────────────────────────────────

def test_cells_of_routes_rows_and_counts_the_ones_in_no_cell():
    d = date(2026, 10, 10)
    r = lambda day, x, c, rev, u: {"date": day, "firstSessionDate": x, "countryId": c, "totalAdRevenue": rev,
                                   "activeUsers": u}
    rows = [r("20261010", "20261010", "XA", "1.5", "3"), r("20261010", "20261010", "XA", "0.5", "1"),
            r("20261010", "20261009", "(not set)", "2", "2"), r("20261010", "20261010", "(other)", "9", "9"),
            r("20261010", "(other)", "XA", "9", "9"), r("20261010", "20261011", "XA", "9", "9"),
            r("20261009", "20261009", "XA", "9", "9")]
    cells, rest = pp.cells_of(rows, d)
    assert cells == {("XA", "2026-10-10"): [2_000_000, 4], ("--", "2026-10-09"): [2_000_000, 2]} and rest == 4
    assert pp.by_country([{"date": "20261010", "countryId": "XA", "newUsers": "7"},
                          {"date": "20261010", "countryId": "(other)", "newUsers": "5"},
                          {"date": "20261009", "countryId": "XA", "newUsers": "5"}], d) == {"XA": 7}


def test_overlap_tie_cells_share_and_coverage():
    c0 = {("XA", "x1"): [100, 10], ("XB", "x1"): [50, 5]}
    p = {("XA", "x1"): [40, 4]}
    o = {("XA", "x1"): [60, 6], ("XB", "x1"): [50, 5]}
    t = pp.tie_cells(c0, p, o)
    assert t["rev"] == 1.0 and t["users"] == 1.0 and t["rev_ratio"] == 1.0 and t["cells"] == t["merged"] == 2
    t2 = pp.tie_cells(c0, p, {("XA", "x1"): [60, 6]})                      # XB lost in the other half
    assert t2["only_c0"] == 1 and t2["rev"] == round(100 / 150, 6) and t2["users"] == round(10 / 15, 6)
    t3 = pp.tie_cells(c0, p, {("XA", "x1"): [60, 6], ("XB", "x1"): [50, 5], ("XC", "x1"): [50, 5]})   # more than C0
    assert t3["only_merged"] == 1 and t3["rev_ratio"] > 1 and t3["rev"] == round(150 / 200, 6)
    assert pp.tie_cells({}, {}, {})["rev"] is None
    assert pp.share(p, c0) == {"rev": round(40 / 150, 4), "users": round(4 / 15, 4)}
    cov, mn = pp.coverage(p, {"x1": [80, 8], "x2": [0, 0]})
    assert cov == {"x1": 0.5} and mn == 0.5 and pp.coverage({}, {})[1] is None


def test_ads_installs_and_comparison(tmp_path):
    site = write_site(tmp_path, days=(F,))
    got = pp.ads_installs(site, KEY, [F.isoformat(), "2020-01-01"])
    assert got == {F.isoformat(): {"XA": ADS, "XB": ADS, "XX": ADS}, "2020-01-01": {}}      # (the bad pack name is skipped)
    assert pp.ads_installs(site, "000000000000", [F.isoformat()]) is None and pp.ads_installs(None, KEY, []) is None
    c = pp.ads_cmp({"XA": 40, "XB": 10, "XX": 99}, {"XA": 100, "XB": 20}, {"XA": 40, "XB": 30, "XC": 5, "XX": 8})
    assert c["ads"] == 75 and c["countries"] == 3 and c["judged"] == 2           # XC has < 20 installs
    assert c["np"] == 50 and c["np_ratio"] == round(50 / 75, 4) and c["np_median"] == round((1.0 + 10 / 30) / 2, 4)
    assert c["n0"] == 120 and c["n0_ratio"] == round(120 / 75, 4) and c["n0_median"] == round((2.5 + 20 / 30) / 2, 4)
    assert "np" not in pp.ads_cmp(None, None, {"XA": 5})


# ── the verdict ─────────────────────────────────────────────────────────────────────────────────

def _read(**kw):
    return dict({"ok": True, "cut": False, "other_rows": 0}, **kw)


def _day(rev=1.0, **over):
    reads = {k: _read() for k in ("C0", "CP", "CO")}
    reads.update(over)
    return {"reads": reads, "cmp": {"tie": {"rev": rev}}}


def test_verdict_branches():
    v = pp.verdict
    assert v({"a": _day(), "b": _day(0.995)}, True) == {"checks": {"whole": True, "tie": True}, "verdict": "go"}
    assert v({"a": _day()}, False)["verdict"] == "unknown"                       # not every day asked was read
    assert v({"a": _day(0.98)}, True) == {"checks": {"whole": True, "tie": False}, "verdict": "nogo"}
    assert v({"a": _day(), "b": _day(0.5)}, True)["checks"]["tie"] is False
    for bad in ({"cut": True}, {"thresh": True}, {"loss": True}, {"sampled": True}, {"other_rows": 2}):
        assert v({"a": _day(CP=_read(**bad))}, True)["checks"]["whole"] is False
        assert v({"a": _day(CO=_read(**bad))}, True)["verdict"] == "nogo"
    refused = {"ok": False, "err": {"http": 400}}
    assert v({"a": _day(CO=refused)}, True)["checks"]["whole"] is False
    for err in ({"http": 429}, {"http": 503}, {"type": "Timeout"}):               # not the answer: asked again next run
        w = v({"a": _day(CO={"ok": False, "err": err})}, True)
        assert w["checks"]["whole"] is None and w["verdict"] == "unknown"
    nocmp = _day()
    nocmp["cmp"] = {}
    assert v({"a": nocmp}, True)["checks"]["tie"] is None
    noco = _day()
    del noco["reads"]["CO"]
    noco["cmp"] = {}
    assert v({"a": noco}, True) == {"checks": {"whole": None, "tie": None}, "verdict": "unknown"}
    assert v({"a": _day(C0={"ok": False, "err": {"http": 400}})}, True)["checks"]["tie"] is None
    zero = _day(None)
    assert v({"a": zero}, True)["checks"]["tie"] is None                           # nothing on either side: not judged
    assert v({}, True) == {"checks": {"whole": None, "tie": None}, "verdict": "unknown"}
    # a day whose C0 failed is not skipped: the tie was not measured on every day asked
    for err in ({"http": 503}, {"type": "ReadTimeout"}):
        two = {"a": _day(), "b": _day(C0={"ok": False, "err": err})}
        w = v(two, True)
        assert w["checks"]["tie"] is None and w["verdict"] == "unknown"
    # "(other)" on C0 alone: the all-row sums are tied, not the cells
    def sums(a, b, c):
        return {"C0": _read(other_rows=1, s={"totalAdRevenue": {"sum": a}}),
                "CP": _read(s={"totalAdRevenue": {"sum": b}}), "CO": _read(s={"totalAdRevenue": {"sum": c}})}
    lossy = _day(0.667, **sums(100, 40, 60))
    assert v({"a": lossy}, True) == {"checks": {"whole": True, "tie": True}, "verdict": "go"}
    assert v({"a": _day(1.0, **sums(100, 40, 50))}, True)["verdict"] == "nogo"
    assert v({"a": _day(1.0, C0=_read(other_rows=1))}, True)["checks"]["tie"] is None
    # a false beats an unknown day
    assert v({"a": _day(0.5), "b": nocmp}, True)["checks"]["tie"] is False


def test_counts_name_nothing():
    run = type("R", (), {"calls": 9, "elapsed": lambda self: 3})()
    apps = {"k1": {"days": {"d": {"reads": {"CP": {"ok": True}, "CO": {"ok": False, "err": {"http": 400}},
                                            "NP": {"ok": False, "err": {"http": 503}}}}}, "verdict": {"verdict": "go"}},
            "k2": {"verdict": {"verdict": "nogo"}}, "k3": {"crash": "ValueError"}}
    c = pp.counts(apps, run)
    assert c == dict(apps=3, reads=3, accepted=1, refused=1, failed=1, go=1, nogo=1, unknown=1, calls=9, seconds=3)
    assert pp.public_line(c) == "paid probe: apps 3, reads 3, accepted 1, refused 1, failed 1, go 1, nogo 1, unknown 1, calls 9, 3s"


# ── main: the clone's layout, the inputs, the private output ────────────────────────────────────────────────────────

def _main_env(monkeypatch, tmp_path, fake, inputs=None, last=None):
    root = tmp_path / "_private"
    os.makedirs(root / "data")
    write_site(root)
    if last is not None:
        os.makedirs(root / "ga4", exist_ok=True)
        with open(root / pp.OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(last, f)
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    seen = {}
    monkeypatch.setattr(pp.sp, "load_state", lambda r: seen.setdefault("root", r) and {"x": 1})
    monkeypatch.setattr(pp.cp, "units_from_state", lambda st: [unit()])
    wrote = {}
    monkeypatch.setattr(pp.pr, "write_private", lambda path, raw, msg: wrote.update(path=path, raw=raw) or True)
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKENS": json.dumps({"o": RT}),
           "PAID_DATA_DIR": str(root)}
    if inputs is not None:
        ev = tmp_path / "event.json"
        ev.write_text(json.dumps({"inputs": inputs}))
        env["GITHUB_EVENT_PATH"] = str(ev)
    pp.main(env=env, now=NOW)
    return seen, json.loads(wrote["raw"]), wrote["path"], str(root)


def test_main_writes_the_private_report_in_its_shape(monkeypatch, tmp_path, capsys):
    seen, rep, path, root = _main_env(monkeypatch, tmp_path, FakeGA())
    assert seen["root"] == root and path == "ga4/paid_probe.json" == pp.OUT_PATH
    assert set(rep) == {"v", "probe", "at", "rules", "counts", "apps"} and rep["v"] == 1 and rep["probe"] == "ga4_paid"
    assert rep["rules"] == {"offsets": [0, 30, 100, 300], "paid": ["Cross-network", "Paid Search"],
                            "channel": "firstUserDefaultChannelGroup", "tie_min": 0.99, "ads_min": 20,
                            "max_calls": pp.MAX_CALLS}
    a = rep["apps"][KEY]
    assert set(a) >= {"key", "F", "days", "asked", "complete", "verdict", "calls", "tokens", "sec"}
    assert a["verdict"]["verdict"] == "go" and set(a["days"]) == set(a["asked"])
    day = a["days"][F.isoformat()]
    assert set(day["reads"]) == set(pp.KINDS) and set(day["cmp"]) == {"tie", "share", "cov_p", "cov_p_min", "cov_0",
                                                                          "cov_0_min", "ads"}
    assert set(day["reads"]["CP"]) >= {"ok", "rows", "row_count", "cut", "other_rows", "unset_rows", "s", "thresh", "loss",
                                       "sampled", "tok", "sec", "calls", "cells", "in_no_cell"}
    assert set(day["reads"]["CP"]["s"]) == {"activeUsers", "totalAdRevenue"}
    assert set(day["reads"]["NP"]["s"]) == {"newUsers"}
    out = capsys.readouterr().out
    assert "paid probe: 1 app(s) to probe, 0 carried over" in out and "report written" in out
    for s in SECRETS + [F.isoformat()]:
        assert s not in out


def test_main_without_the_private_clone_makes_no_ga4_call(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ga4, "_call", lambda *a, **k: calls.append(1))
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKEN": RT,
           "PAID_DATA_DIR": str(tmp_path / "none")}
    try:
        pp.main(env=env, now=NOW)
        assert False, "should exit"
    except SystemExit as e:
        assert "no private clone" in str(e)
    assert calls == []


def test_the_call_cap_input_and_apps_carried_over(monkeypatch, tmp_path):
    fake = FakeGA()
    old = {"v": 1, "rules": pp.rules(pp.MAX_CALLS), "apps": {"k-other": {"key": "k-other", "complete": True}}}
    seen, rep, path, root = _main_env(monkeypatch, tmp_path, fake, inputs={"max_calls": "7"}, last=old)
    assert len(fake.bodies) == 7 and rep["rules"]["max_calls"] == 7
    assert rep["apps"]["k-other"] == {"key": "k-other", "complete": True}            # carried over as it was
    other = dict(old, rules=dict(old["rules"], offsets=[0, 1]))
    seen, rep2, _, _ = _main_env(monkeypatch, tmp_path / "b", FakeGA(), last=other)
    assert "k-other" not in rep2["apps"]                                 # made under other rules: never mixed in


# ── the workflow file ───────────────────────────────────────────────────────────────────────────

def test_the_workflow_file_parses_and_keeps_the_inputs_off_the_log():
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "ga4-paid-probe.yml"), encoding="utf-8") as fh:
        raw = fh.read()
    wf = yaml.safe_load(raw)                                              # (a ": " in a step's name broke it once)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and set(on["workflow_dispatch"]["inputs"]) == {"apps", "max_calls"}
    assert wf["permissions"] == {"contents": "read"} and "github.event.inputs" not in raw and "inputs." not in raw
    steps = wf["jobs"]["probe"]["steps"]
    assert all(": " not in st.get("name", "") for st in steps)
    assert steps[0]["with"]["persist-credentials"] is False
    (clone,) = [st for st in steps if "clone" in (st.get("run") or "")]
    assert "> /dev/null 2>&1" in clone["run"] and "::add-mask::" in clone["run"] and "timeout 480 git " in clone["run"]
    (runs,) = [st for st in steps if "ga4_paid_probe" in (st.get("run") or "")]
    assert "2>/tmp/" in runs["run"] and runs["env"]["PAID_DATA_DIR"] == "_private"
    for st in steps:                                                      # the inputs reach neither env nor script
        assert "max_calls" not in json.dumps(st.get("env") or {}) and "apps" not in (st.get("run") or "").split()
    assert {"DATA_REPO", "DATA_REPO_TOKEN"} <= set(runs["env"])           # (the private write)


def test_ads_installs_without_country_packs_is_none(tmp_path):
    import gzip as gz
    import json as js
    with gz.open(str(tmp_path / "roi_k1.json.gz"), "wt", encoding="utf-8") as f:
        js.dump({"days": []}, f)
    assert pp.ads_installs(str(tmp_path), "k1", ["2026-01-01"]) is None
    with gz.open(str(tmp_path / "roi_k2.json.gz"), "wt", encoding="utf-8") as f:
        js.dump({"cd": {"packs": []}}, f)
    assert pp.ads_installs(str(tmp_path), "k2", ["2026-01-01"]) is None
