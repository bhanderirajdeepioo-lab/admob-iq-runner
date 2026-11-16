"""⚖️ Google Ads users only — the shared piece of the paid GA4 stores (admob_iq.fetch.ga4_paid), offline: the paid
filter expression (firstUserDefaultChannelGroup in-list, a fresh dict each call), ga4_paid.App AND-ing it into EVERY
runReport (no extra / the caller's extras / an event / an event list, each page of report_all; the caller's list never
changed, nothing else of the body moved; the real App's call cap kept), its quota held to Screens' stricter floors (a
property between them and every live step's stops the paid client before its call, never the live one), and
instance(): a second, independent instance of a fetch module (its globals its own — the base's never change —, its
relative imports the same shared modules, an unknown override refused, a name that is not a sibling refused,
sys.modules as it was after a failure). Also the fakes the paid fetches' tests share: a synthetic GA4 runReport
(Server: filters, grouping, GA4's flags and row limit, paging, a quota snapshot — made-up rows only, no network), a GA4
that refuses every read, and a recording client. SYNTHETIC values only (the runner repo is public)."""
import copy
import sys

import pytest

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_audience as gaud
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_nvr as gv
from admob_iq.fetch import ga4_paid as gp
from admob_iq.fetch import ga4_screens as gs
from admob_iq.fetch import ga4_uninstall as gu

SID = "9000000052"                                  # a made-up stream id
MICROS = ("totalAdRevenue",)                        # the fake rows keep these in micros (USD in the answer)
PAID_EX = {"filter": {"fieldName": "firstUserDefaultChannelGroup",
                      "inListFilter": {"values": ["Cross-network", "Paid Search"]}}}


# ── the shared fakes ────────────────────────────────────────────────────────────────────────────────────────────────
def match(ex, r):
    """A GA4 filter expression → does fake row r pass it (a field the row lacks reads "")?"""
    if "andGroup" in ex:
        return all(match(e, r) for e in ex["andGroup"]["expressions"])
    if "notExpression" in ex:
        return not match(ex["notExpression"], r)
    f = ex["filter"]
    v = str(r.get(f["fieldName"], ""))
    if "stringFilter" in f:
        assert f["stringFilter"]["matchType"] == "EXACT"
        return v == f["stringFilter"]["value"]
    return v in f["inListFilter"]["values"]


class Server:
    """GA4's runReport in ga4._call's place, over made-up rows: the request's dimensionFilter applied whole (andGroup,
    notExpression, EXACT string and in-list filters), its date range on the rows' "date", the rows grouped by the
    dimensions asked for and the metrics summed, ordered by those dimensions, paged by limit / offset with rowCount.
    flag(body) → the answer's metadata ({}: none); cap(body) → GA4's row limit for the answer (None: none) — the rows
    past it (the smallest by the last metric) rolled into one "(other)" row per activity day, dataLossFromOtherRow
    (GA4 rolls up AFTER the filters: a smaller part's answer is whole); quota: the propertyQuota snapshot every answer
    carries (None: none). Every request body it answered is kept (bodies: what GA4 itself got, whichever client)."""

    def __init__(self, rows, flag=None, cap=None, quota=None):
        self.days, self.flag, self.cap, self.quota, self.bodies = {}, flag, cap, quota, []
        for r in rows:
            self.days.setdefault(r["date"], []).append(r)

    def __call__(self, method, url, token, body=None, params=None):
        assert method == "POST" and url.endswith(":runReport") and token == "tok", url
        self.bodies.append(copy.deepcopy(body))
        dims = [d["name"] for d in body.get("dimensions") or []]
        mets = [m["name"] for m in body.get("metrics") or []]
        (rng,) = body["dateRanges"]
        a, b = (rng[k].replace("-", "") for k in ("startDate", "endDate"))
        agg = {}
        for day, rows in self.days.items():
            if a <= day <= b:
                for r in rows:
                    if match(body["dimensionFilter"], r):
                        g = agg.setdefault(tuple(str(r.get(d, "")) for d in dims), [0] * len(mets))
                        for i, m in enumerate(mets):
                            g[i] += r.get(m, 0)
        meta = dict(self.flag(body)) if self.flag else {}
        top = self.cap(body) if self.cap else None
        if top is not None and len(agg) > top:
            order = sorted(agg, key=lambda k: (-agg[k][-1], k))
            oth = {}
            for k in order[top:]:
                g = oth.setdefault(tuple(v if d == "date" else "(other)" for d, v in zip(dims, k)), [0] * len(mets))
                for i, x in enumerate(agg[k]):
                    g[i] += x
            agg = {**{k: agg[k] for k in order[:top]}, **oth}
            meta["dataLossFromOtherRow"] = True
        keys = sorted(agg)
        off, lim = int(body.get("offset") or 0), int(body.get("limit") or 10000)
        out = {"dimensionHeaders": [{"name": d} for d in dims], "metricHeaders": [{"name": m} for m in mets],
               "rows": [{"dimensionValues": [{"value": v} for v in k],
                         "metricValues": [{"value": str(x / 1e6 if m in MICROS else x)} for m, x in zip(mets, agg[k])]}
                        for k in keys[off:off + lim]],
               "rowCount": len(keys), "metadata": meta}
        if self.quota:
            out["propertyQuota"] = copy.deepcopy(self.quota)
        return out


def refuse(method, url, token, body=None, params=None):
    """GA4 refusing every read (ga4._call's own error for a 4xx answer) — a made-up message."""
    raise RuntimeError("HTTP 400: INVALID_ARGUMENT (synthetic)")


def snap(k, left, size=None):
    """A synthetic quota snapshot: bucket k with `left` of its size (the standard property's, gu.QUOTA_CAP) left."""
    size = gu.QUOTA_CAP[k] if size is None else size
    return {k: {"consumed": int(size - left), "remaining": int(left)}}


# between Screens' floors (ga4_screens.quota_gate: 60 % hourly, 40 % of the day, 60 thresholded requests left) and every
# live step's (gaud.quota_stop: 50 % hourly, 10 % of any bucket, 5 thresholded requests)
DAY, HOUR, PHOUR = (gu.QUOTA_CAP[k] for k in ("tokensPerDay", "tokensPerHour", "tokensPerProjectPerHour"))
BETWEEN = [snap("tokensPerDay", 0.39 * DAY), snap("tokensPerDay", 0.35 * DAY), snap("tokensPerDay", 0.12 * DAY),
           snap("tokensPerHour", 0.55 * HOUR), snap("tokensPerProjectPerHour", 0.55 * PHOUR),
           snap("potentiallyThresholdedRequestsPerHour", 30, 120)]
ABOVE = {**snap("tokensPerDay", 0.45 * DAY), **snap("tokensPerHour", 0.65 * HOUR),
         **snap("tokensPerProjectPerHour", 0.65 * PHOUR), **snap("potentiallyThresholdedRequestsPerHour", 80, 120)}


def recording(base, sent):
    """The client class `base` (ga4_paid.App, or ga4_firstopen.App: the unfiltered fetch) whose _post keeps every
    request body it sent (sent) — its own gate, call cap and paging as they are; GA4 itself is ga4._call (a Server)."""
    class Rec(base):
        def _post(self, method, body, measure=False):
            j = super()._post(method, body, measure)
            sent.append(body)
            return j
    return Rec


def serve(monkeypatch, server):
    """GA4 → the Server (no network, no pause between calls, a made-up access token)."""
    monkeypatch.setattr(ga4, "_call", server)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda c, s, r: "tok")


def held(body):
    """A request held to Google Ads users: its filter is the stream's two expressions first, then the read's own, then
    the paid in-list — once, last."""
    ex = body["dimensionFilter"]["andGroup"]["expressions"]
    return (ex[:2] == [ga4._exact("platform", "Android"), ga4._exact("streamId", SID)] and ex[-1] == PAID_EX
            and ex.count(PAID_EX) == 1)


def unheld(body):
    """A request of the unfiltered fetch: no channel filter anywhere in it."""
    return "firstUserDefaultChannelGroup" not in repr(body)


# ── the filter ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_paid_expression_is_the_first_user_channel_in_list_fresh_each_call():
    assert gp.CHANNEL == "firstUserDefaultChannelGroup" and gp.PAID == ("Cross-network", "Paid Search")
    a, b = gp.expr(), gp.expr()
    assert a == b == PAID_EX and a is not b and a["filter"] is not b["filter"]
    a["filter"]["inListFilter"]["values"].append("Organic Search")     # a request that changes its copy …
    assert gp.expr() == PAID_EX                                         # … never changes the next one


class Capture(gp.App):
    """ga4_paid.App with _post mocked: each body kept, a two-page answer (rowCount 3, `limit` rows a page)."""

    def _post(self, method, body, measure=False):
        self.bodies.append(body)
        n = min(int(body.get("limit") or 3), 3 - int(body.get("offset") or 0))
        return {"dimensionHeaders": [{"name": "date"}], "metricHeaders": [{"name": "activeUsers"}], "rowCount": 3,
                "rows": [{"dimensionValues": [{"value": "20260901"}], "metricValues": [{"value": "1"}]}] * n}


class CaptureBase(gf.App):
    _post = Capture._post


def _app(cls):
    ga = cls("tok", "111", SID, {"quota": None, "stop": None}, max_calls=50)
    ga.bodies = []
    return ga


def test_every_runreport_carries_the_paid_filter_after_the_callers_own():
    body = {"dateRanges": [{"startDate": "2026-09-01", "endDate": "2026-09-01"}], "dimensions": [{"name": "date"}],
            "metrics": [{"name": "activeUsers"}]}
    cc = ga4._in_list("countryId", ["XA", "XB"])
    xs = [cc, {"notExpression": ga4._in_list("firstSessionDate", ["20260901"])}]
    for kw in ({}, {"extra": None}, {"extra": [cc]}, {"extra": tuple(xs)}, {"event": "ad_impression"},
               {"events": ("first_open", "app_remove")}, {"event": "ad_impression", "extra": [cc]}):
        paid, base = _app(Capture), _app(CaptureBase)
        before = copy.deepcopy(kw)
        rows = paid.report(dict(body), **kw)
        base.report(dict(body), **kw)
        assert kw == before and len(rows) == 3, kw                        # the caller's own list never changed
        (p,), (q,) = paid.bodies, base.bodies
        ex = p["dimensionFilter"]["andGroup"]["expressions"]
        assert ex == q["dimensionFilter"]["andGroup"]["expressions"] + [PAID_EX], kw     # the read's own filters
        assert ex[:2] == [ga4._exact("platform", "Android"), ga4._exact("streamId", SID)]  # (the stream's first) —
        assert {k: v for k, v in p.items() if k != "dimensionFilter"} == \
            {k: v for k, v in q.items() if k != "dimensionFilter"}                       # nothing else moved
        assert p["returnPropertyQuota"] is True
    ga = _app(Capture)                                                    # report_all: every page carries it
    rows = ga.report_all(dict(body), extra=[cc], page_rows=2)
    assert len(rows) == 3 and [b["offset"] for b in ga.bodies] == [0, 2] and ga.last_pages == 2
    assert all(b["dimensionFilter"]["andGroup"]["expressions"][-2:] == [cc, PAID_EX] for b in ga.bodies)
    assert isinstance(ga, gf.App) and gp.App._post is gf.App._post      # _post (its gate, Stop, quota): the App's


def test_the_real_app_with_the_served_ga4_keeps_its_call_cap(monkeypatch):
    rows = [{"date": "20260901", "platform": "Android", "streamId": SID, "countryId": "XA",
             "firstUserDefaultChannelGroup": ch, "activeUsers": n}
            for ch, n in (("Cross-network", 3), ("Paid Search", 1), ("Organic Search", 5))]
    serve(monkeypatch, Server(rows))
    sent = []
    ga = recording(gp.App, sent)("tok", "111", SID, {"quota": None, "stop": None}, max_calls=1)
    got = ga.report({"dateRanges": [{"startDate": "2026-09-01", "endDate": "2026-09-01"}],
                     "dimensions": [{"name": "countryId"}], "metrics": [{"name": "activeUsers"}]})
    assert got == [{"countryId": "XA", "activeUsers": 4}] and held(sent[0])    # the organic rows never counted
    with pytest.raises(gf.Stop):
        ga.report({"dateRanges": [{"startDate": "2026-09-01", "endDate": "2026-09-01"}],
                   "dimensions": [{"name": "countryId"}], "metrics": [{"name": "activeUsers"}]})
    assert ga.calls == 1 and len(sent) == 1


# ── the quota: Screens' floors ──────────────────────────────────────────────────────────────────────────────────────
def test_the_paid_client_stops_at_screens_floors_where_every_live_step_goes_on(monkeypatch):
    """The paid steps run after Screens: a property whose last snapshot sits under Screens' floors but above every live
    step's stops the paid client BEFORE its call — prop["stop"] set: every later call on the property stops too, its
    report_all as well, even once a snapshot is back up — while ga4_firstopen.App (every live step's client) makes its
    call; above Screens' floors both go on (the paid read held to Google Ads users)."""
    rows = [{"date": "20260901", "platform": "Android", "streamId": SID, "countryId": "XA",
             "firstUserDefaultChannelGroup": ch, "activeUsers": n}
            for ch, n in (("Cross-network", 3), ("Paid Search", 1), ("Organic Search", 5))]
    body = {"dateRanges": [{"startDate": "2026-09-01", "endDate": "2026-09-01"}],
            "dimensions": [{"name": "countryId"}], "metrics": [{"name": "activeUsers"}]}
    srv = Server(rows)
    serve(monkeypatch, srv)
    for q in BETWEEN:
        why = gs.quota_gate(q)
        assert gaud.quota_stop(q) is None and why in ("day_low", "hour_low", "count_low"), q    # (between the two)
        live, paid = [], []
        assert recording(gf.App, live)("tok", "111", SID, {"quota": copy.deepcopy(q), "stop": None}).report(dict(body))
        prop = {"quota": copy.deepcopy(q), "stop": None}
        ga = recording(gp.App, paid)("tok", "111", SID, prop)
        with pytest.raises(gf.Stop, match=why):
            ga.report(dict(body))
        assert prop["stop"] == why and ga.calls == 0 and paid == [] and len(live) == 1, q
        prop["quota"] = copy.deepcopy(ABOVE)                            # stopped for the run: never a call again
        with pytest.raises(gf.Stop, match=why):
            ga.report_all(dict(body))
        assert ga.calls == 0 and paid == []
    assert len(srv.bodies) == len(BETWEEN) and all(unheld(b) for b in srv.bodies)    # GA4 got the live calls only
    assert gaud.quota_stop(ABOVE) is None and gs.quota_gate(ABOVE) is None
    live, paid = [], []
    recording(gf.App, live)("tok", "111", SID, {"quota": copy.deepcopy(ABOVE), "stop": None}).report(dict(body))
    prop = {"quota": copy.deepcopy(ABOVE), "stop": None}
    got = recording(gp.App, paid)("tok", "111", SID, prop).report(dict(body))
    assert got == [{"countryId": "XA", "activeUsers": 4}] and prop["stop"] is None and len(live) == len(paid) == 1
    assert held(paid[0]) and unheld(live[0])


# ── instance() ──────────────────────────────────────────────────────────────────────────────────────────────────────
TWIN = "admob_iq.fetch._test_ga4_paid_twin"


def test_an_instance_is_independent_of_its_base_and_shares_the_modules_under_it():
    base = {k: getattr(gv, k) for k in ("DIR", "APP", "NAME", "PARTS", "MAX_CALLS", "BUDGET_SEC")}
    try:
        twin = gp.instance(gv, TWIN, DIR="twin_dir", NAME="twin", PARTS=("c",), APP=gp.App)
        assert sys.modules[TWIN] is twin and twin is not gv and twin.__name__ == TWIN
        assert (twin.DIR, twin.NAME, twin.PARTS, twin.APP) == ("twin_dir", "twin", ("c",), gp.App)
        assert {k: getattr(gv, k) for k in base} == base and gv.APP is None and gv.DIR == "ga4_nvr"
        assert twin.__package__ == "admob_iq.fetch"                     # its relative imports: the same modules
        assert twin.gf is gf and twin.ga4 is ga4 and twin.gu is gv.gu and twin.gaud is gv.gaud
        assert twin.read is not gv.read and twin.read.__globals__ is vars(twin)    # its own functions, its own globals
        twin.MAX_CALLS = 1                                              # a global set on it …
        assert gv.MAX_CALLS == base["MAX_CALLS"]                        # … never on the base
        assert twin.log_line({"counts": {"selected": 2}}).startswith("twin: apps 2, ")
        assert gv.log_line({"counts": {"selected": 2}}).startswith("ga4 nvr: apps 2, ")
        again = gp.instance(gv, TWIN)                                   # made again: a new one, the old one untouched
        assert sys.modules[TWIN] is again and again is not twin and again.DIR == "ga4_nvr" and twin.DIR == "twin_dir"
    finally:
        sys.modules.pop(TWIN, None)


def test_an_unknown_override_or_a_name_that_is_not_a_sibling_is_refused_and_nothing_is_left():
    try:
        with pytest.raises(AttributeError, match="MAX_CALS"):
            gp.instance(gv, TWIN, DIR="x", MAX_CALS=3)                   # a typo never adds a dead knob
        assert TWIN not in sys.modules
        first = gp.instance(gv, TWIN, DIR="x")
        with pytest.raises(AttributeError):
            gp.instance(gv, TWIN, DIR="y", NAMES="z")
        assert sys.modules[TWIN] is first and first.DIR == "x"         # an earlier instance stays as it was
        for name in ("admob_iq.fetch.ga4_nvr", "admob_iq._ga4_twin", "_ga4_twin"):
            with pytest.raises(ValueError):
                gp.instance(gv, name)
        assert sys.modules["admob_iq.fetch.ga4_nvr"] is gv and "admob_iq._ga4_twin" not in sys.modules
    finally:
        sys.modules.pop(TWIN, None)
