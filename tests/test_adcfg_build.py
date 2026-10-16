"""⚙️ Ad setting changes — the build step (admob_iq.adcfg_build) and its wiring, on SYNTHETIC apps only (tests/adcfg_synth
and the Install value fixture apps of tests/value_synth — made-up ids, names and money): every event kept privately
(data/adcfg/<key>.json) with the build day first seen, backfill finds never "new" (on the first run only what today's
data first shows is new), a "checking" event that did not hold (missing 3 new data days in a row) kept as "reverted",
one missing a day and found again the same row (never "Reverted" + live, never "new" twice), the country-mix / new
users / GA4 users drops recorded with their cause; the page block (newest first, no unit ids, the forecast's back-tests
labelled); build_static hands the reports over, uninstall_build the Play-package ids; and end to end (the real
uninstall → value → ROI → forecast steps): every existing output byte-identical with the reports or without, the only
difference being the forecast's new "acfg" block — and the forecast's numbers exactly as they were (AX held off)."""
import copy
import gzip
import json
import os
from datetime import datetime, timedelta, timezone

from admob_iq import adcfg_build as acb
from admob_iq import build_static
from admob_iq import uninstall_build as ub
from admob_iq.engine import adcfg as A
from admob_iq.engine import forecast_vd as VD
from tests import adcfg_synth as S

NOW = datetime(2026, 6, 11, 8, tzinfo=timezone.utc)      # the synthetic app's data ends 2026-06-09


def _run(x, data, now=NOW):
    run = acb.start(A.Source(x["mu"], x["cty"], x["till"]), data, now)
    return run, acb.app_step(run, x["app_id"], "aaaaaaaaaaaa", x["store"])


def _stored(data):
    with open(os.path.join(data, "adcfg", "aaaaaaaaaaaa.json"), encoding="utf-8") as f:
        return json.load(f)


def test_every_event_is_kept_privately_with_the_day_first_seen(tmp_path):
    data = str(tmp_path / "data")
    x = S.make(1)
    run, res = _run(x, data)
    st = _stored(data)
    assert st["v"] == 1 and st["first"] == "2026-06-11" and st["till"] == x["till"] and st["made"] == "2026-06-11"
    assert st["events"] == res["events"] and len(res["events"]) >= 4
    for e in st["events"]:                                # what the owner asked to keep, per event
        assert {"d", "fmt", "b", "a", "j", "conf", "kind", "rel", "st", "seen", "bf"} <= set(e)
        assert e["kind"] in ("cap", "new placement", "removed placement", "SDK") and e["conf"] in ("High", "Medium", "Low")
        # the first run: only what today's data first shows (≥ till − 6, x["till"] = 2026-06-09) is new
        assert e["seen"] == "2026-06-11" and e["bf"] == (1 if e["d"] < "2026-06-03" else 0)
    assert res["steps"] == A.fc_steps(res["events"]) and res["made"] == "2026-06-11"
    assert acb.line(run) == "ad settings: apps 1, events %d (checking %d, with update %d), new today %d, failed 0" % (
        len(res["events"]), sum(e["st"] == "checking" for e in res["events"]),
        sum(1 for e in res["events"] if e["rel"]), sum(1 for e in res["events"] if not e["bf"]))
    p = os.path.join(data, "adcfg", "aaaaaaaaaaaa.json")
    m0 = os.stat(p).st_mtime_ns
    _run(x, data, NOW + timedelta(hours=1))               # the next hourly build, the same data: nothing rewritten
    assert os.stat(p).st_mtime_ns == m0
    run2, res2 = _run(x, data, NOW + timedelta(days=1))   # tomorrow, the same data: seen days kept, made kept
    assert [e["seen"] for e in res2["events"]] == ["2026-06-11"] * len(res2["events"]) and _stored(data)["made"] == "2026-06-11"
    assert run2.new == 0


def test_a_checking_event_that_does_not_hold_is_reverted(tmp_path):
    chk = {"d": "2026-05-30", "fmt": "banner", "j": 0.5, "st": "checking", "seen": "2026-06-08", "bf": 0}
    old = {"till": "2026-06-09", "events": [chk, {"d": "2026-03-01", "fmt": "native", "j": -0.4, "st": "confirmed",
                                                  "seen": "2026-06-01", "bf": 1}]}
    now = [{"d": "2026-03-02", "fmt": "native", "j": -0.41, "st": "confirmed"},            # the same one, a day moved
           {"d": "2026-06-01", "fmt": "app_open", "j": 0.6, "st": "checking"}]              # a new one
    evs, gone = acb.merge(old, now, "2026-06-11", "2026-06-10")
    assert [(e["d"], e["seen"], e["bf"], e.get("miss")) for e in evs] == [
        ("2026-03-02", "2026-06-01", 1, None), ("2026-05-30", "2026-06-08", 0, 1),
        ("2026-06-01", "2026-06-11", 0, None)]
    assert gone == []                                     # missing ONE new data day: still checking
    st = {"till": "2026-06-10", "events": evs, "gone": gone}
    evs, gone = acb.merge(st, now, "2026-06-11", "2026-06-10")          # the next hourly build, the same data
    assert [e.get("miss") for e in evs if e["fmt"] == "banner"] == [1] and gone == []
    for k, till in enumerate(("2026-06-11", "2026-06-12")):              # missing on 3 new data days in a row
        evs, gone = acb.merge({"till": st["till"], "events": evs, "gone": gone}, now, "2026-06-1%d" % (2 + k), till)
        st["till"] = till
    assert not [e for e in evs if e["fmt"] == "banner"]
    assert [(g["d"], g["st"], g["gone"], g["seen"]) for g in gone] == [
        ("2026-05-30", "reverted", "2026-06-13", "2026-06-08")]
    evs2, gone2 = acb.merge({"till": "2026-06-12", "events": evs, "gone": gone}, now, "2026-06-14", "2026-06-13")
    assert gone2 == gone                                  # kept once, never doubled
    # … and found again later: the same row back (no "Reverted" + live pair), its first-seen day kept, never "new" twice
    back = now + [{"d": "2026-05-31", "fmt": "banner", "j": 0.45, "st": "checking"}]
    evs3, gone3 = acb.merge({"till": "2026-06-13", "events": evs2, "gone": gone2}, back, "2026-06-15", "2026-06-14")
    assert gone3 == [] and [(e["d"], e["seen"]) for e in evs3 if e["fmt"] == "banner"] == [("2026-05-31", "2026-06-08")]


def test_found_missing_a_day_found_again_is_one_row(tmp_path):
    """The flicker (review): found → missing on one new data day → found: ONE row all along, never Reverted, its first
    seen day unchanged — and "new today" only on the day it was first found."""
    e = {"d": "2026-06-01", "fmt": "interstitial", "j": 0.5, "st": "checking"}
    o = {}
    days = (("2026-06-08", [e]), ("2026-06-09", []), ("2026-06-10", [dict(e, j=0.48)]), ("2026-06-11", [e]))
    for k, (till, found) in enumerate(days):
        evs, gone = acb.merge(o, [dict(x) for x in found], "2026-06-%02d" % (9 + k), till)
        assert len([x for x in evs if x["fmt"] == "interstitial"]) == 1 and gone == [], (till, evs, gone)
        assert evs[0]["seen"] == "2026-06-09" and evs[0]["st"] == "checking"
        o = {"till": till, "events": evs, "gone": gone}


def test_the_first_run_counts_only_what_todays_data_first_shows():
    evs, _ = acb.merge({}, [{"d": d, "fmt": "banner", "j": 0.4, "st": "checking"} for d in
                            ("2026-05-20", "2026-06-02", "2026-06-03", "2026-06-04")], "2026-06-11", "2026-06-09")
    assert [(e["d"], e["bf"]) for e in evs] == [("2026-05-20", 1), ("2026-06-02", 1), ("2026-06-03", 0),
                                                ("2026-06-04", 0)]
    # the next run (a stored file): a new find is new unless older than BF_DAYS
    evs2, _ = acb.merge({"till": "2026-06-09", "events": evs}, [dict(x) for x in evs] + [
        {"d": "2026-05-25", "fmt": "native", "j": 0.4, "st": "checking"}], "2026-06-12", "2026-06-10")
    assert [(e["d"], e["fmt"], e["bf"]) for e in evs2 if e["fmt"] == "native"] == [("2026-05-25", "native", 0)]


def test_the_country_mix_drops_are_recorded(tmp_path):
    data = str(tmp_path / "data")
    for seed in range(1, 30):
        x = S.make(seed)
        if any(d["kind"] == "mix" for d in x["decoys"]):
            break
    _run(x, data)
    st = _stored(data)
    D = next(d["d"] for d in x["decoys"] if d["kind"] == "mix")
    assert st["dropped"] and all({"d", "fmt", "m", "j", "why", "mix"} <= set(e) for e in st["dropped"])
    assert any(abs((A._d(e["d"]) - A._d(D)).days) <= 7 and e["why"] == "country mix" for e in st["dropped"])
    assert not any(abs((A._d(e["d"]) - A._d(D)).days) <= 3 and e["st"] == "confirmed" and e["fmt"] == "banner"
                   and not any(abs((A._d(t["d"]) - A._d(e["d"])).days) <= 5 for t in x["truth"]) for e in st["events"])


def test_the_new_users_and_ga4_users_drops_are_recorded(tmp_path):
    """The build hands GA4's new users over (its store's daily "new"): an install surge under an onboarding ad and a
    break in GA4's users count are no event, each recorded in dropped with its cause."""
    for k, (sched, onb, why) in enumerate(((("surge", 200), 4, "new users"), (("users", 200), 0, "GA4 users"))):
        data = str(tmp_path / ("d%d" % k))
        x = S.make(3, n=420, sched=[("cap", 100), sched], onb=onb)
        _, res = _run(x, data)
        D = A._d(x["decoys"][0]["d"])
        assert not [e for e in res["events"] if abs((A._d(e["d"]) - D).days) <= 4]
        assert [e for e in _stored(data)["dropped"] if abs((A._d(e["d"]) - D).days) <= 4 and e["why"] == why]


def test_the_page_block(tmp_path):
    data = str(tmp_path / "data")
    x = S.make(1)
    _, res = _run(x, data)
    steps = res["steps"]
    assert steps
    s0 = A._d(steps[0]["at"])
    T1, T2 = (s0 - timedelta(days=20)).isoformat(), (s0 - timedelta(days=60)).isoformat()
    fc = {"bt": [[T1, 0.1, 0.2, 0.3, []], [T2, -0.1, 0.0, 0.1, []]],
          "hz": {"btx": {"58": [[T1, 0.1, 0, 0], [T2, 0.2, 0, 0]]}}}
    blk = acb.page(res, fc, 0)
    assert blk["v"] == 1 and blk["ax"] == 0 and blk["mat"] == A.MATERIAL and blk["made"] == "2026-06-11"
    assert [e["d"] for e in blk["ev"]] == sorted((e["d"] for e in blk["ev"]), reverse=True)        # newest first
    assert all("uid" not in e and "score" not in e for e in blk["ev"])                              # no unit ids
    assert T1 in blk["bt"]["30"] and T2 not in blk["bt"]["30"] and T2 in blk["bt"]["90"]
    assert blk["bt"]["58"] == [T1] and blk["steps"] == steps
    assert set(blk["wk"]["f"]) <= set(A.FMTS) and blk["wk"]["d0"] == "2025-01-06"
    assert blk["n"]["all"] == len(res["events"]) and blk["n"]["conf"] + blk["n"]["chk"] == blk["n"]["all"]
    assert acb.page(None, fc) is None


def test_a_broken_app_costs_only_itself(tmp_path):
    data = str(tmp_path / "data")
    x = S.make(1)
    run = acb.start(A.Source(x["mu"], x["cty"], x["till"]), data, NOW)
    assert acb.app_step(run, x["app_id"], "bbbbbbbbbbbb", {"daily": "broken"}) is None and run.fails == 1
    assert acb.app_step(run, "ca-app-pub-x~nothing", "cccccccccccc", x["store"]) is None and run.fails == 1
    assert acb.app_step(run, x["app_id"], "aaaaaaaaaaaa", x["store"]) and run.apps == 1


def test_many_apps_on_the_same_days(tmp_path):
    data = str(tmp_path / "data")
    x = S.make(1)
    run = acb.start(A.Source(x["mu"], x["cty"], x["till"]), data, NOW)
    for k in ("aaaaaaaaaaa1", "aaaaaaaaaaa2", "aaaaaaaaaaa3", "aaaaaaaaaaa4"):     # the same app under 4 keys
        res = acb.app_step(run, x["app_id"], k, x["store"])
    assert all(e["wide"] == 3 for e in res["events"])
    run2 = acb.start(A.Source(x["mu"], x["cty"], x["till"]), data, NOW)           # the next build reads them back
    assert set(run2.others) == {"aaaaaaaaaaa1", "aaaaaaaaaaa2", "aaaaaaaaaaa3", "aaaaaaaaaaa4"}


def test_build_static_hands_the_reports_over(monkeypatch):
    got = {}

    class Repo:
        mu = [{"app_id": "a~1", "report_date": "2026-01-01"}]
        cty = [{"app_id": "a~1", "report_date": "2026-01-01", "country": "AA"}]

        def fetch_network(self):
            return [{"app_id": "a~1", "report_date": "2026-01-01", "estimated_earnings_micros": 1, "impressions": 1}]

        def fetch_mediation(self):
            return []

        def fetch_country(self):
            return self.cty

        def fetch_mediation_unit(self):
            return self.mu
    monkeypatch.setattr(build_static, "_uninstall_step", lambda d, dd, o, s, revenue=None: got.update(rev=revenue) or [])
    build_static._uninstall_with_revenue({}, Repo(), "data", "site", {"report_currency": "USD", "ga4_active": False},
                                         "UTC", datetime(2026, 1, 3).date())
    src = got["rev"]["adsrc"]
    assert isinstance(src, A.Source) and src.mu is Repo.mu and src.cty is Repo.cty and src.till == "2026-01-02"


def test_the_play_package_ids():
    apps = [{"app_id": "a~1", "package": "p.one"}, {"app_id": "a~2", "same_pkg": "p.one"},
            {"app_id": "a~3", "same_pkg": "p.two"}]
    assert ub.pkg_ids(apps[0], apps) == ["a~1", "a~2"]
    assert ub.pkg_ids({"app_id": "a~9"}, apps, "p.two") == ["a~9", "a~3"]
    assert ub.pkg_ids({"app_id": "a~9"}, apps) == ["a~9"]


# ── end to end: the real uninstall → value → ROI → forecast steps, with the reports or without ─────────────────────
def _e2e(tmp_path, monkeypatch, name, with_reports):
    from tests import test_value_build as tv
    from admob_iq.fetch import ga4_uninstall as gu
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(tv.STATUS))
    data, out = str(tmp_path / name / "data"), str(tmp_path / name / "site")
    end = tv.NOW.date() - timedelta(days=2)
    rev, made = tv.vs.seed_build(data, end=end)
    if with_reports:
        mu, cty = [], []
        for k, (aid, _, _, _) in enumerate(tv.APPS):
            hs = made[aid]["hs"]
            x = S.make(50 + k, n=(end - hs).days + 1, start=hs.isoformat(), dau0=25000)
            for r in x["mu"]:
                mu.append(dict(r, app_id=aid))
            for r in x["cty"]:
                cty.append(dict(r, app_id=aid))
        rev["adsrc"] = A.Source(mu, cty, end.isoformat())
    dash = tv.dashboard()
    ub.run_uninstall(dash, data, out, tv.ga4_settings(), now=tv.NOW, revenue=rev)
    return data, out, dash


def _files(root):
    got = {}
    for dp, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(dp, f)
            got[os.path.relpath(p, root)] = open(p, "rb").read()
    return got


def test_end_to_end_every_existing_output_byte_identical(tmp_path, monkeypatch, capsys):
    d0, o0, dash0 = _e2e(tmp_path, monkeypatch, "without", False)
    d1, o1, dash1 = _e2e(tmp_path, monkeypatch, "with", True)
    s0, s1 = _files(o0), _files(o1)
    assert set(s0) == set(s1)
    diff = sorted(k for k in s0 if s0[k] != s1[k])
    assert diff and all(k.startswith("roi_") and k != "roi.json.gz" for k in diff)          # the per-app ROI files only
    blocks = 0
    for k in diff:
        a = json.loads(gzip.decompress(s0[k]))
        b = json.loads(gzip.decompress(s1[k]))
        blk = b["fc"].pop("acfg")
        assert a == b                                     # every other number of the file exactly as it was
        assert blk["v"] == 1 and blk["ax"] == VD.AX == 0 and isinstance(blk["ev"], list)
        blocks += 1
    assert blocks >= 2
    f0, f1 = _files(d0), _files(d1)
    new = sorted(k for k in f1 if k not in f0)
    assert new and all(k.startswith("adcfg" + os.sep) for k in new)                        # its own private files
    def nosec(k, v):                                      # (a tune's measured seconds: the clock, never the data)
        if k.startswith("forecast" + os.sep) and k.endswith(".json"):
            return json.dumps({x: y for x, y in json.loads(v).items() if x != "tune_sec"}, sort_keys=True)
        return v
    assert {k: nosec(k, v) for k, v in f1.items() if k in f0} == {k: nosec(k, v) for k, v in f0.items()}   # forecast too
    assert json.dumps(dash0, sort_keys=True, default=str) == json.dumps(dash1, sort_keys=True, default=str)


def test_the_forecast_gets_the_steps_but_its_numbers_stay(tmp_path, monkeypatch):
    """The forecast's run with the ad setting changes (acfg) = without them, every byte (AX 0, held off: the back-test
    did not show a win); with AX 1 a test whose 30-day window holds one is a sudden-change test (kind "ads")."""
    from admob_iq import forecast_build as fb
    from tests.test_forecast_build import _rows_life, Clock
    from tests.test_forecast_engine import make, LAST
    app = make()
    rows, life, ida = _rows_life(app, ga4=True)
    now = datetime(2026, 1, 2, 6, tzinfo=timezone.utc)
    steps = [{"at": (LAST - timedelta(days=d)).isoformat(), "x": 0.3, "fmt": "app_open"} for d in (100, 200, 260)]
    out = []
    for i, (st, ax) in enumerate(((None, 0), (steps, 0), (steps, 1))):
        monkeypatch.setattr(VD, "AX", ax)
        data = str(tmp_path / ("f%d" % i))
        os.makedirs(data)
        run = fb.start(data, now, Clock())
        out.append((fb.app_step(run, "a~1", "k1", rows, {"S": LAST}, ida, life, LAST.isoformat(), [], acfg=st),
                    _files(data)))
    assert out[0][0] == out[1][0] and out[0][1] == out[1][1]          # AX 0: the page and the stored file identical
    kinds = {k for r in out[2][0]["bt"] for k in r[4]}
    ev = [e for e in out[2][0]["events"] if e["kind"] == "ads"]
    assert kinds and ev and all(abs(e["x"] - 1.3) < 1e-9 for e in ev)   # AX 1: the back-tests carry them
    assert not [e for e in out[0][0]["events"] if e["kind"] == "ads"]
