"""⚖️ The first-session eCPM of Google Ads users by country (admob_iq.fetch.ga4_nvr_paid), offline against a synthetic
GA4 (tests/test_ga4_paid.Server: made-up rows of five first-user channels, two of them paid; no network): MOD is a
second instance of fetch.ga4_nvr reading ONLY the country read ("c": one call a range — the window, then the history
newest first), every request held to Google Ads users (the paid in-list last in its filter, after the ad_impression
event filter; every request GA4 itself got, whichever client sent it), each day's record {"c"} only with the paid
users' revenue and impressions, the lone read again and the backfill merge working with that one part (whole >
thresholded > sampled), its own store data/ga4_nvr_paid/ and a counts-only line ("ga4 nvr paid: apps …"); a property
under Screens' quota floors deferred; an app GA4 refuses run after run "stuck" on its third failed run; the base
ga4_nvr still makes its three reads, unfiltered, on the same GA4 (its own tests run unchanged). The build's wiring:
tests/test_uninstall_build.py. SYNTHETIC values only."""
import importlib
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_nvr as gv
from admob_iq.fetch import ga4_nvr_paid as gnp
from admob_iq.fetch import ga4_paid as gp
from admob_iq.fetch import ga4_uninstall as gu
from tests.test_ga4_paid import BETWEEN, SID, Server, held, recording, refuse, serve, unheld

NOW = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 2)
HS = TODAY - timedelta(days=100)                    # the made-up apps' GA4 history start
NV = {"new": 2, "returning": 5, "(not set)": 1}     # weights (made up)
CC = {"XA": 3, "XB": 2, "(not set)": 1}
CH = {"Cross-network": 3, "Paid Search": 1, "Organic Search": 2, "Direct": 1, "Unassigned": 1}
UNITS = (("Banner", "unit_b"), ("Interstitial", "unit_i"))
APPS = [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~2", "package": "com.example.beta"},
        {"app_id": "x~3", "package": "com.example.none"}]
C_DIMS = ["date", "newVsReturning", "countryId"]


def _days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def rows():
    """Activity day × newVsReturning × country × first-user channel × ad unit: an ad_impression row (revenue in micros,
    events) and a screen_view row (sessions, users)."""
    out = []
    for D in _days(HS, TODAY):
        for nv, wn in NV.items():
            for cc, wc in CC.items():
                for ch, wh in CH.items():
                    for fm, unit in UNITS:
                        base = {"date": D.strftime("%Y%m%d"), "newVsReturning": nv, "countryId": cc, "adFormat": fm,
                                "adUnitName": unit, "firstUserDefaultChannelGroup": ch, "platform": "Android",
                                "streamId": SID}
                        out.append(dict(base, eventName="ad_impression", totalAdRevenue=wn * wc * wh * 100,
                                        eventCount=wn * wc * wh))
                        out.append(dict(base, eventName="screen_view", sessions=wn * wh, activeUsers=wn))
    return out


def want_c(paid=True):
    """A day's "c" rows: [nvr, cc, revenue USD, ad_impression events] of Google Ads users (paid), else of everyone."""
    w = sum(v for c, v in CH.items() if c in gp.PAID or not paid) * len(UNITS)
    return sorted([{"new": "n", "returning": "r"}.get(nv, "x"), "--" if cc == "(not set)" else cc,
                   gv._r4(wn * wc * w * 100 / 1e6), wn * wc * w] for nv, wn in NV.items() for cc, wc in CC.items())


def _client(monkeypatch, base, sent, max_calls=99):
    """A recording client of class `base` on a new synthetic GA4 → (client, the Server: what GA4 itself got)."""
    srv = Server(rows())
    serve(monkeypatch, srv)
    return recording(base, sent)("tok", "111", SID, {"quota": None, "stop": None}, max_calls=max_calls), srv


CFG = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}


def _routes(monkeypatch):
    """Two made-up properties (one app each; com.example.none has no GA4), their history from HS."""
    route = {"property_id": "111", "stream_id": SID, "owner": "o"}
    monkeypatch.setattr(gv.gu, "load_state", lambda d: {"routes": {"by_package": {
        "com.example.alpha": route, "com.example.beta": dict(route, property_id="112")}},
        "tz": {"111": "Asia/Kolkata", "112": "UTC"}, "fetch": {}})
    monkeypatch.setattr(gv.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": HS.isoformat()})


def _ranges(sent):
    return [(b["dateRanges"][0]["startDate"], b["dateRanges"][0]["endDate"]) for b in sent]


# ── the instance ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_instance_its_knob_and_the_base_untouched(monkeypatch):
    monkeypatch.delenv("GA4_NVRP_MAX_CALLS", raising=False)
    m = importlib.reload(gnp).MOD
    assert m is not gv and m.__name__ == "admob_iq.fetch._ga4_nvr_paid_impl" and m.step_app is not gv.step_app
    assert (m.DIR, m.NAME, m.APP, m.PARTS, m.MAX_CALLS) == ("ga4_nvr_paid", "ga4 nvr paid", gp.App, ("c",),
                                                            gv.MAX_CALLS)
    assert gnp.BUDGET_SEC == 60 and m.READS == gv.READS and m.STORE_V == gv.STORE_V
    assert (gv.DIR, gv.NAME, gv.APP, gv.PARTS) == ("ga4_nvr", "ga4 nvr", None, ("u", "c", "s"))   # the base: its own
    try:
        monkeypatch.setenv("GA4_NVRP_MAX_CALLS", "4")
        assert importlib.reload(gnp).MOD.MAX_CALLS == 4 and gv.MAX_CALLS != 4
        monkeypatch.setenv("GA4_NVRP_MAX_CALLS", "")                    # empty: the default
        assert importlib.reload(gnp).MOD.MAX_CALLS == gv.MAX_CALLS
    finally:
        monkeypatch.delenv("GA4_NVRP_MAX_CALLS", raising=False)
        importlib.reload(gnp)
    assert gnp.log_line({"counts": {"selected": 3, "with_ga4": 2, "fetched": 1, "calls": 4}}) == (
        "ga4 nvr paid: apps 3, with GA4 2, fetched 1, fresh 0, failed 0, deferred 0, waiting 0, calls 4, tokens 0")
    assert gnp.log_line({"counts": {}, "error": "KeyError"}).endswith(", tokens 0, error KeyError")


# ── the reads ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_only_the_country_read_one_call_a_range_every_read_held_to_google_ads_users(monkeypatch):
    sent = []
    (ga, srv), store = _client(monkeypatch, gp.App, sent), {"v": gnp.MOD.STORE_V}
    assert gnp.MOD.step_app(ga, store, TODAY, HS, NOW) == "fetched"
    recent = TODAY - timedelta(days=gv.RECENT_DAYS - 1)
    edge = recent - timedelta(days=1)
    assert _ranges(sent) == [(recent.isoformat(), TODAY.isoformat()),                      # the window, then the
                             ((edge - timedelta(days=gv.CHUNK_DAYS - 1)).isoformat(), edge.isoformat()),   # history
                             (HS.isoformat(), (edge - timedelta(days=gv.CHUNK_DAYS)).isoformat())]       # newest first
    assert ga.calls == len(sent) == 3 and all(held(b) for b in sent)
    assert srv.bodies == sent                                           # every request GA4 itself got
    for b in sent:
        assert [d["name"] for d in b["dimensions"]] == C_DIMS and [m["name"] for m in b["metrics"]] == list(gv.EV)
        ex = b["dimensionFilter"]["andGroup"]["expressions"]
        assert ex[2] == ga4._exact("eventName", "ad_impression") and len(ex) == 4     # the event filter, then paid
    days = store["days"]
    assert sorted(days) == [D.isoformat() for D in _days(HS, TODAY)] and all(set(v) == {"c"} for v in days.values())
    assert all(v["c"] == want_c() for v in days.values())               # the paid users' revenue and events only
    assert want_c() != want_c(paid=False)
    assert store["mark"] == {} and all(store["mp"][d] == {} for d in days) and store["rr"] == {}
    assert store["backfill"] == {"oldest": HS.isoformat(), "done": True}
    ga2, srv = _client(monkeypatch, gp.App, sent)
    n = len(sent)
    assert gnp.MOD.step_app(ga2, store, TODAY, HS, NOW + timedelta(minutes=30)) == "fresh" and ga2.calls == 0
    assert gnp.MOD.step_app(ga2, store, TODAY, HS, NOW + timedelta(hours=1)) == "fetched" and ga2.calls == 1
    assert len(sent) == n + 1 and held(sent[-1])                        # the window again: one read, where ga4_nvr
    assert srv.bodies == sent[n:]                                       # makes three


def test_the_base_still_makes_its_three_reads_unfiltered_on_the_same_ga4(monkeypatch):
    sent = []
    (ga, srv), store = _client(monkeypatch, gf.App, sent), {"v": gv.STORE_V}
    assert gv.step_app(ga, store, TODAY, HS, NOW) == "fetched"
    assert ga.calls == len(sent) == 3 * 3 and all(unheld(b) for b in sent) and srv.bodies == sent
    assert [[d["name"] for d in b["dimensions"]] for b in sent[:3]] == [
        ["date", "newVsReturning", "adFormat", "adUnitName"], C_DIMS, ["date", "newVsReturning"]]
    assert all(set(v) == {"u", "c", "s"} and v["c"] == want_c(paid=False) for v in store["days"].values())


def test_refresh_all_its_own_store_and_a_counts_only_line(monkeypatch, tmp_path):
    data = str(tmp_path)
    _routes(monkeypatch)
    srv = Server(rows())
    serve(monkeypatch, srv)
    sent = []
    monkeypatch.setattr(gnp.MOD, "APP", recording(gp.App, sent))
    out = gnp.refresh_all(CFG, data, APPS, NOW)                         # (no clock given: the monotonic one)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and "error" not in out
    assert out["counts"]["calls"] == len(sent) == 2 * 3 and all(held(b) for b in sent)
    assert srv.bodies == sent and out["counts"]["stuck"] == 0          # every request GA4 itself got
    assert sorted(os.listdir(data)) == ["ga4_nvr_paid"]                 # its own store only (never ga4_nvr's)
    root = os.path.join(data, "ga4_nvr_paid")
    assert sorted(os.listdir(root)) == sorted([gu.file_key("x~1") + ".json.gz", gu.file_key("x~2") + ".json.gz",
                                               "state.json"])
    st = gnp.MOD.load_store(gnp.MOD.store_path(data, "x~1"))           # (ga4_nvr's own readers, on the paid store)
    assert st["v"] == gv.STORE_V and st["time_zone"] == "Asia/Kolkata" and st["stream_id"] == SID
    assert all(set(v) == {"c"} for v in st["days"].values()) and st["backfill"]["done"]
    assert json.load(open(os.path.join(root, "state.json"), encoding="utf-8"))["fetch"]["x~1"]["last_ok"]
    line = gnp.log_line(out)
    assert line == ("ga4 nvr paid: apps 3, with GA4 2, fetched 2, fresh 0, failed 0, deferred 0, waiting 0, calls 6, "
                    "tokens 0")


# ── the quota: Screens' floors; a stuck app ────────────────────────────────────────────────────────────────────────
def test_a_property_under_screens_floors_is_deferred_after_its_first_call(monkeypatch, tmp_path):
    """Every answer's snapshot under Screens' floor of the day but above every live step's: each property's first call
    (no snapshot yet), then its app deferred — never a read past Screens' floors."""
    _routes(monkeypatch)
    srv = Server(rows(), quota=BETWEEN[1])
    serve(monkeypatch, srv)
    out = gnp.refresh_all(CFG, str(tmp_path), APPS, NOW)
    assert out["apps"] == {"x~1": "deferred", "x~2": "deferred"} and out["counts"]["calls"] == len(srv.bodies) == 2
    assert all(held(b) for b in srv.bodies) and out["counts"]["stuck"] == 0


def test_an_app_ga4_refuses_run_after_run_is_stuck_on_its_third_failed_run(monkeypatch, tmp_path):
    """ga4_nvr retries a failed app every RETRY_HOURS and never counts it; the paid wrapper keeps ga4_cecpm's streak
    ("fails" in the paid state): runs 1 and 2 fail (stuck 0), run 3 → both apps stuck; a run inside RETRY_HOURS holds
    them back (failed, not tried: still stuck); GA4 answering again → fetched, the streak over."""
    data = str(tmp_path)
    _routes(monkeypatch)
    serve(monkeypatch, Server(rows()))
    monkeypatch.setattr(ga4, "_call", refuse)
    path = os.path.join(data, "ga4_nvr_paid", "state.json")
    for h, stuck, fails in ((0, 0, 1), (4, 0, 2), (8, 2, 3), (9, 2, 3)):
        out = gnp.refresh_all(CFG, data, APPS, NOW + timedelta(hours=h))
        assert out["apps"] == {"x~1": "failed", "x~2": "failed"} and "error" not in out, h
        assert out["counts"]["stuck"] == stuck and out["counts"]["calls"] == (0 if h == 9 else 2), h
        st = json.load(open(path, encoding="utf-8"))["fetch"]
        assert [st[a]["fails"] for a in ("x~1", "x~2")] == [fails] * 2, h
    assert gnp.log_line(out) == ("ga4 nvr paid: apps 3, with GA4 2, fetched 0, fresh 0, failed 2, deferred 0, "
                                 "waiting 0, calls 0, tokens 0")         # (counts only: the build prints the banner)
    serve(monkeypatch, Server(rows()))
    out = gnp.refresh_all(CFG, data, APPS, NOW + timedelta(hours=12))
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and out["counts"]["stuck"] == 0
    st = json.load(open(path, encoding="utf-8"))["fetch"]
    assert not any("fails" in st[a] or st[a].get("fail") for a in ("x~1", "x~2"))


def test_the_stuck_rule_leaves_a_run_that_ended_in_an_error_and_never_raises(monkeypatch, tmp_path):
    """streak(): a run whose own status holds an "error" is left as it is (its line is the banner); a state it cannot
    read or write → "error" (never raised)."""
    out = {"counts": {}, "apps": {"x~1": "failed"}, "error": "KeyError"}
    assert gp.streak(gnp.MOD, str(tmp_path), out, NOW) is out and out["counts"] == {} and not os.listdir(tmp_path)
    monkeypatch.setattr(gnp.MOD, "save_state", lambda d, s: 1 / 0)
    out = gp.streak(gnp.MOD, str(tmp_path), {"counts": {}, "apps": {}}, NOW)
    assert out == {"counts": {}, "apps": {}, "error": "ZeroDivisionError"}


# ── the merge, with one part ────────────────────────────────────────────────────────────────────────────────────────
def test_a_day_read_alone_keeps_its_country_read_unless_the_chunks_is_better(monkeypatch):
    """ga4_nvr's rule with "c" the only part: a final day read alone ("rr") keeps its country read unless the first
    backfill chunk's is better (whole > thresholded > sampled) — and nothing but "c" is ever asked or kept."""
    from tests import test_ga4_nvr as tn
    m = gnp.MOD
    hs, lone = TODAY - timedelta(days=20), (TODAY - timedelta(days=6)).isoformat()
    monkeypatch.setattr(m, "_mark", lambda ga: getattr(ga, "flag", None))

    def case(own, chunk):
        store = {"v": m.STORE_V}
        with pytest.raises(gf.Stop):
            m.step_app(tn.FakeGA(stop_after=1), store, TODAY, hs, NOW)      # the window (one read), then a stop
        store["days"][lone] = {"c": [["n", "XA", 9.0, 50]]}
        store["mp"][lone] = own
        m._remark(store["mark"], lone, own)
        store["rr"] = {lone: 1}

        class G(tn.FakeGA):
            def report_all(self, body, **kw):
                got = super().report_all(body, **kw)
                a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
                self.flag = chunk if (b - a).days > gv.RECENT_DAYS else None
                return got
        ga = G()
        m.step_app(ga, store, TODAY + timedelta(days=1), hs, NOW + timedelta(days=1))
        assert ga.calls == 2 and all([x["name"] for x in q["dimensions"]] == C_DIMS for q in ga.asked)
        assert all(set(v) == {"c"} for v in store["days"].values()) and store["rr"] == {lone: 1}
        return store
    st = case({"c": "s"}, "s")                                         # sampled vs sampled: the lone read stays
    assert st["days"][lone]["c"] == [["n", "XA", 9.0, 50]] and st["mp"][lone] == {"c": "s"} and st["mark"][lone] == "s"
    st = case({"c": "s"}, "t")                                         # thresholded beats sampled
    assert st["days"][lone]["c"][0] == ["n", "--", 0.8, 40] and st["mp"][lone] == {"c": "t"} and st["mark"][lone] == "t"
    st = case({"c": "t"}, None)                                        # whole beats thresholded
    assert st["days"][lone]["c"][0] == ["n", "--", 0.8, 40] and st["mp"][lone] == {} and lone not in st["mark"]
    assert gv._mark is not m._mark                                      # (the base's own, untouched)
