"""GA4 activity probe (admob_iq.fetch.ga4_activity_probe + .github/workflows/ga4-activity-probe.yml) — offline against a
small fake GA4 (SYNTHETIC: made-up screen classes, screen names, ad units, ad sources, countries and money): each read's
request shape, the ties to each truth and key by key, the Activity table and where each ad format lands, the screen
dimension falling back to the page path, fold rows and silent folds, sampling, truncation by age, loss by range, late data
on the newest days, the conditional reads and their skips, the verdict, the offline AdMob check, the size guard and the
PUBLIC log (a counts-only heartbeat + ONE counts-only line)."""
import copy
import itertools
import json
import os
import re
from datetime import date, timedelta

import pytest
import yaml

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_activity_probe as ac
from tests.test_ga4_device_probe import AID, KEY, NOW, PID, RT, SECRETS, SID, TOK, unit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TODAY, F, W0, W7 = date(2026, 10, 15), date(2026, 10, 10), date(2026, 9, 13), date(2026, 10, 4)   # NOW in UTC
H0 = date(2026, 1, 1)                                            # unit()'s history start: the fake's first day
EDGE = date(2026, 6, 1)                                          # the age mode's raw-data edge
W = 28
# (class, screen name, views a day, engagement s a view, previous class)
CLASSES = (("XSplashActivity", "(not set)", 100, 3, "(not set)"), ("XHomeActivity", "home", 300, 20, "XSplashActivity"),
           ("XListActivity", "list", 120, 10, "XHomeActivity"), ("AdActivity", "(not set)", 60, 15, "XHomeActivity"),
           ("FullScreenWebViewDisplay", "(not set)", 10, 5, "XListActivity"))
VIEWS = sum(v for _, _, v, _, _ in CLASSES)                      # 590 a day
# (class, ad format, ad unit, impressions a day, USD an impression, ad source)
PLACES = (("XHomeActivity", "Banner", "unit-banner-PRIVATE", 600, 0.0004, "XNet One"),
          ("XListActivity", "Native advanced", "unit-native-PRIVATE", 60, 0.001, "XNet One"),
          ("AdActivity", "Interstitial", "unit-inter-PRIVATE", 40, 0.006, "XNet One"),
          ("AdActivity", "App open", "unit-open-PRIVATE", 20, 0.004, "XNet Two"),
          ("FullScreenWebViewDisplay", "Rewarded", "unit-reward-PRIVATE", 10, 0.01, "XNet Two"))
IMPS = sum(p[3] for p in PLACES)                                 # 730 a day
# other events a day: (event, class, ad format, count) — the last is the app's own ad event, logged on the host screen
OTHER = (("ad_click", "XHomeActivity", "Banner", 6), ("ad_click", "AdActivity", "Interstitial", 1),
         ("ad_reward", "FullScreenWebViewDisplay", "Rewarded", 8), ("x_inter_ad_show", "XHomeActivity", "(not set)", 40))
NAMES = [c for c, *_ in CLASSES] + [p[2] for p in PLACES] + ["XNet One", "XNet Two", "x_inter_ad_show", "Banner",
                                                             "Native advanced", "Interstitial", "XA", "XB", "home"]
DIM = {"unifiedScreenClass": "cls", "unifiedPagePathScreen": "cls", "unifiedScreenName": "name", "adFormat": "fmt",
       "adUnitName": "unit", "adSourceName": "src", "eventName": "ev", "newVsReturning": "nvr", "appVersion": "ver",
       "countryId": "cc", "customEvent:firebase_previous_class": "prev"}
SCREEN = ("unifiedScreenClass", "unifiedPagePathScreen")
BLANK = {"cls": "(not set)", "name": "(not set)", "fmt": "(not set)", "unit": "(not set)", "src": "(not set)",
         "prev": "(not set)", "n": 0, "users": 0, "eng": 0, "rev": 0.0}
PREV_API = "customEvent:firebase_previous_class"


class FakeGA:
    """Event groups every day of 2026 to TODAY: per class its screen_view and user_engagement events, per placement its
    ad_impression events, the OTHER events; newVsReturning and the country alternate by day, the app version changes on
    1 Oct. Modes: refuse(dims, metrics) → HTTP 400 (and INCOMPATIBLE in checkCompatibility); fold {"mode": "drop" |
    "label", "units"}: a read with a screen AND the ad unit loses those units' rows ("drop": gone, dataLossFromOtherRow
    set, no fold row) or answers them as ONE row with fold_label in every dimension; fold_today: the same for every row of
    TODAY in reads with a screen; sample=N: a read pairing a screen with an ad dimension over > N days is sampled (rows
    scaled ±0.4 %, so its ties still hold); age=EDGE: a read with the screen class and the ad unit (age_fmt: or the ad
    format) starting before EDGE loses the banner unit's days before it, with a PROPERTY truncation; range_days=N: a read
    with the screen class and the ad unit over > N days loses the native unit on every day; drift: days after F grow 5 %
    with every report; cty_drop: reads with countryId and date lose one class in one country; pub: publisher
    impressions = events × pub; views_range=N: a views read by date and screen class over > N days loses the splash
    screen's views on every day; fail(dims, metrics, days) → an error text to raise (e.g. a 429)."""

    def __init__(self, refuse=None, refuse_mets=(), custom=(), fold=None, fold_label="(other)", fold_today=False,
                 sample=None, age=None, age_fmt=False, range_days=None, drift=False, no_views=False, no_custom=False,
                 cty_drop=False, pub=1.0, views_range=None, fail=None):
        self.refuse, self.refuse_mets, self.custom = refuse or (lambda dims, mets: False), set(refuse_mets), custom
        self.fold, self.fold_label, self.fold_today, self.sample = fold, fold_label, fold_today, sample
        self.age, self.age_fmt, self.range_days, self.drift, self.cty_drop, self.pub = (age, age_fmt, range_days, drift,
                                                                                         cty_drop, pub)
        self.views_range, self.fail = views_range, fail or (lambda dims, mets, days: None)
        self.calls, self.bodies, self.other, self.n = [], [], [], 0
        self.by_day, d = {}, H0
        while d <= TODAY:
            day = {"nvr": "new" if d.day % 2 else "returning", "ver": "9.1" if d < date(2026, 10, 1) else "9.2",
                   "cc": "XA" if d.day % 2 else "XB", "date": d}
            atoms = []
            for c, nm, v, s, prev in CLASSES:
                if not no_views:
                    atoms.append(dict(BLANK, **day, ev="screen_view", cls=c, name=nm, n=v, users=v // 2, prev=prev))
                atoms.append(dict(BLANK, **day, ev="user_engagement", cls=c, name=nm, n=v, eng=v * s))
            for c, f, un, n, usd, src in PLACES:
                atoms.append(dict(BLANK, **day, ev="ad_impression", cls=c, fmt=f, unit=un, src=src, n=n, users=n // 4,
                                  rev=n * usd))
            for ev, c, f, n in OTHER:
                if not (no_custom and not ev.startswith("ad_")):
                    atoms.append(dict(BLANK, **day, ev=ev, cls=c, fmt=f, n=n))
            self.by_day[d] = atoms
            d += timedelta(days=1)

    def met(self, a, m):
        ev, n = a["ev"], a["n"]
        return {"eventCount": n, "screenPageViews": n if ev == "screen_view" else 0, "activeUsers": a["users"],
                "sessions": a["users"] if ev == "screen_view" else 0, "userEngagementDuration": a["eng"],
                "totalAdRevenue": a["rev"], "publisherAdImpressions": n * self.pub if ev == "ad_impression" else 0,
                "publisherAdClicks": n if ev == "ad_click" else 0,
                "adUnitExposure": 30000 * n if ev == "ad_impression" and a["fmt"] == "Banner" else 0}[m]

    @staticmethod
    def val(a, k):
        if k == "date":
            return a["date"].strftime("%Y%m%d")
        if k == "yearMonth":
            return a["date"].strftime("%Y%m")
        return a[DIM[k]]

    @staticmethod
    def pred(expr):
        f = expr.get("filter")
        if f:
            name = f["fieldName"]
            if name in ("platform", "streamId"):
                assert f["stringFilter"]["value"] == {"platform": "Android", "streamId": SID}[name]
                return lambda a: True
            key = DIM[name]
            if "inListFilter" in f:
                vals = set(f["inListFilter"]["values"])
                return lambda a: a[key] in vals
            v = f["stringFilter"]["value"]
            return lambda a: a[key] == v
        subs = [FakeGA.pred(e) for e in expr["andGroup"]["expressions"]]
        return lambda a: all(p(a) for p in subs)

    def __call__(self, method, url, token, body=None, params=None):
        assert token == TOK
        if method == "GET":
            if url == "%s/properties/%s/dataRetentionSettings" % (ga4.ADMIN, PID):
                self.other.append("RET")
                return {"eventDataRetention": "FOURTEEN_MONTHS", "userDataRetention": "FOURTEEN_MONTHS"}
            assert url == "%s/properties/%s/metadata" % (ga4.DATA, PID)
            self.other.append("META")
            return {"dimensions": [{"apiName": x} for x in ("date", "eventName") + ac.META_DIMS]
                    + [{"apiName": "customEvent:" + p, "customDefinition": True} for p in self.custom],
                    "metrics": [{"apiName": x} for x in ac.META_METS if x not in self.refuse_mets]}
        ex = body["dimensionFilter"]["andGroup"]["expressions"]
        assert [e["filter"]["fieldName"] for e in ex[:2]] == ["platform", "streamId"]     # pinned to the stream
        if url.endswith("properties/%s:checkCompatibility" % PID):
            self.other.append("CC")
            base = [x["name"] for x in body["dimensions"]]
            return {"dimensionCompatibilities": [
                        {"dimensionMetadata": {"apiName": x},
                         "compatibility": "INCOMPATIBLE" if self.refuse(base + [x], ["eventCount"]) else "COMPATIBLE"}
                        for x in ("date",) + ac.META_DIMS],
                    "metricCompatibilities": [
                        {"metricMetadata": {"apiName": x},
                         "compatibility": "INCOMPATIBLE" if x in self.refuse_mets else "COMPATIBLE"}
                        for x in ac.META_METS]}
        assert url.endswith("properties/%s:runReport" % PID) and body.get("returnPropertyQuota") is True
        dims, mets = [x["name"] for x in body.get("dimensions") or []], [x["name"] for x in body["metrics"]]
        self.calls.append(tuple(dims))
        if body.get("offset", 0) == 0:
            self.bodies.append(body)
        if self.refuse(dims, mets) or set(mets) & self.refuse_mets:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: DETAIL-PRIVATE")
        s = date.fromisoformat(body["dateRanges"][0]["startDate"])
        t = date.fromisoformat(body["dateRanges"][0]["endDate"])
        if self.fail(dims, mets, (t - s).days + 1):
            raise RuntimeError(self.fail(dims, mets, (t - s).days + 1))
        keep = self.pred(body["dimensionFilter"])
        scr, sc = any(d in dims for d in SCREEN), "unifiedScreenClass" in dims
        unit_, fmt_ = "adUnitName" in dims, "adFormat" in dims
        ndays = (t - s).days + 1
        sampled = bool(self.sample and scr and (fmt_ or unit_) and ndays > self.sample)
        aged = bool(self.age and sc and (unit_ or (self.age_fmt and fmt_)) and s < self.age)
        grow = 1.05 ** self.n if self.drift else 1.0
        self.n += 1
        meta, agg, d = {"currencyCode": "USD"}, {}, s
        while d <= t:
            for a in self.by_day.get(d, ()):
                if not keep(a):
                    continue
                if aged and d < self.age and a["fmt"] == "Banner":
                    continue
                if self.range_days and sc and unit_ and ndays > self.range_days and a["unit"] == "unit-native-PRIVATE":
                    continue
                if self.views_range and sc and "date" in dims and not (unit_ or fmt_) and ndays > self.views_range \
                        and a["cls"] == "XSplashActivity":
                    continue
                if self.cty_drop and "countryId" in dims and "date" in dims and a["cc"] == "XB" \
                        and a["cls"] == "XListActivity":
                    continue
                fold = False
                if self.fold and scr and unit_ and a["unit"] in self.fold["units"]:
                    if self.fold["mode"] == "drop":
                        meta["dataLossFromOtherRow"] = True
                        continue
                    fold = True
                if self.fold_today and scr and d == TODAY:
                    fold = True
                key = (self.fold_label,) * len(dims) if fold else tuple(self.val(a, k) for k in dims)
                e = agg.setdefault(key, [0.0] * len(mets))
                g = grow if d > F else 1.0
                for i, m in enumerate(mets):
                    e[i] += self.met(a, m) * g
            d += timedelta(days=1)
        rows = []
        for i, (k, e) in enumerate(sorted(agg.items())):
            if not any(e):
                continue                                             # keepEmptyRows false
            if sampled:
                e = [round(v * (1.004 if i % 2 else 0.996), 6) for v in e]
            rows.append({"dimensionValues": [{"value": v} for v in k], "metricValues": [{"value": str(v)} for v in e]})
        if sampled:
            meta["samplingMetadatas"] = [{"samplesReadCount": "4000000", "samplingSpaceSize": "12000000"}]
        if aged:
            meta["dataTruncationReasons"] = [{"dataTruncationType": "DATA_TRUNCATION_TYPE_PROPERTY",
                                              "dataTruncationDate": self.age.isoformat(),
                                              "dataTruncationDateRanges": [{"startDate": s.isoformat(),
                                                                            "endDate": (self.age - timedelta(days=1))
                                                                            .isoformat()}]}]
        off, lim = body.get("offset", 0), body.get("limit", 10000)
        return {"dimensionHeaders": [{"name": x} for x in dims], "metricHeaders": [{"name": x} for x in mets],
                "rows": rows[off:off + lim], "rowCount": len(rows), "metadata": meta,
                "propertyQuota": {"tokensPerDay": {"consumed": 1, "remaining": 199000}}}


def _patch(monkeypatch, fake):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)


def _run(monkeypatch, fake, u=None, **opts):
    _patch(monkeypatch, fake)
    u = u or unit()
    rep = ac.run_probe([u], "cid", "sec", [("o", RT)], opts, now=NOW, tick=0)
    return rep, rep["apps"][u["key"]]


def _skips(a):
    return {k: r["skip"] for k, r in a["reads"].items() if "skip" in r}


def _ctx(p, got, ok=()):
    c = ac.Ctx(None, None, unit(), p, {"reads": {k: {"ok": True, "state": "whole"} for k in ok}})
    c.got.update(got)
    return c


def _no_leak(text):
    for s in SECRETS + NAMES:
        assert s not in text, s


# ── the windows, the request shapes ──────────────────────────────────────────────────────────

def test_windows_are_final_days_in_the_property_zone():
    p = ac.plan_of(unit(), NOW)
    assert (p["today"], p["F"], p["a"], p["a7"], p["r0"], p["h0"], p["days"]) == (TODAY, F, W0, W7, F + timedelta(1), H0, W)
    late = ac.plan_of(dict(unit(), tz="Pacific/Pago_Pago"), NOW)            # UTC−11: still 14 Oct there
    assert late["today"] == date(2026, 10, 14) and late["F"] == date(2026, 10, 9)
    assert ac.plan_of(dict(unit(), history_start=None), NOW)["h0"] == F - timedelta(days=729)
    young = ac.plan_of(dict(unit(), history_start="2026-10-01"), NOW)
    assert young["a"] == young["h0"] == date(2026, 10, 1) and young["a7"] == W7 and young["days"] == 10
    assert ac.plan_of(dict(unit(), history_start="2026-10-12"), NOW) is None
    rep = ac.run_probe([dict(unit(), history_start="2026-10-12")], "c", "s", [("o", RT)], {}, now=NOW, tick=0)
    assert rep["apps"][KEY]["complete"] and rep["apps"][KEY]["empty"] and rep["counts"]["calls"] == 0


def test_each_read_asks_its_own_shape(monkeypatch):
    fake = FakeGA(custom=("firebase_previous_class",))
    rep, a = _run(monkeypatch, fake)
    spans = {"W": (W0, F), "W7": (W7, F), "R": (F + timedelta(1), TODAY), "H": (H0, F)}
    bodies = iter(fake.bodies)
    for r in ac.READS:
        rec = a["reads"][r.id]
        if r.id in ("META", "CC") or "skip" in rec:
            continue
        body = next(bodies)
        dims = [x["name"] for x in body["dimensions"]]
        assert dims == [ac.SC if d == ac.SCA else PREV_API if d == ac.PREV else d for d in r.dims], r.id
        assert [x["name"] for x in body["metrics"]] == list(r.mets), r.id
        assert body["currencyCode"] == "USD" and body["keepEmptyRows"] is False and "metricFilter" not in body
        assert [o["dimension"]["dimensionName"] for o in body.get("orderBys", [])] == dims   # report_all's total order
        assert (body["dateRanges"][0]["startDate"], body["dateRanges"][0]["endDate"]) == tuple(
            x.isoformat() for x in spans[r.span]), r.id
        ev = body["dimensionFilter"]["andGroup"]["expressions"][2:]
        if r.filt is None:
            assert ev == [], r.id
        elif r.filt == "XC":
            assert ev == [ga4._in_list("eventName", ["x_inter_ad_show"])]
        elif isinstance(r.filt, tuple):
            assert ev == [ga4._in_list("eventName", r.filt)], r.id
        else:
            assert ev == [ga4._exact("eventName", r.filt)], r.id
    assert next(bodies, None) is None
    assert fake.other == ["META", "RET"]                                        # RET once, after META
    assert rep["counts"]["calls"] == 1 + len(fake.calls) == sum(v["calls"] for v in a["calls"].values())


# ── every read whole: the table, the shape, the history, the verdict ─────────────────────────

def test_every_read_whole_and_the_activity_table(monkeypatch):
    rep, a = _run(monkeypatch, FakeGA(custom=("firebase_previous_class", "x_placement")))
    reads = a["reads"]
    assert a["complete"] and a["sca"] == "SC" and a["retention"]["eventDataRetention"] == "FOURTEEN_MONTHS"
    assert a["win"]["W"] == ["2026-09-13", "2026-10-10"] and a["win"]["R"] == ["2026-10-11", "2026-10-15"]
    assert a["win"]["d*"] == "2026-10-10" and a["win"]["Bv"] is None and a["win"]["Ba"] is None
    ran = {k for k, r in reads.items() if "skip" not in r}
    assert ran == {r.id for r in ac.READS if r.when is None} | {"XC", "PV"}
    assert set(_skips(a).values()) == {"whole"} and set(_skips(a)) == {r.id for r in ac.READS if r.when} - {"XC", "PV"}
    for k in ran - {"META"}:
        r = reads[k]
        assert r["ok"] and r["state"] == "whole" and not r["off"] and not r["fold_rows"], (k, r)
        assert all(abs(v - 1) < 1e-9 for v in (r.get("tie") or {}).values()), (k, r.get("tie"))
        for slot in ac.KEY_SLOTS:
            assert all(t["w2"] == 1.0 and t["off2"] == 0 for t in (r.get(slot) or {}).values()), (k, slot)
    assert reads["A"]["data"] and "data" not in reads["AUD"] and isinstance(a["reads"]["VDH"]["day"], dict)
    assert all(e[4] is True and e[5] is True for e in reads["AUDH"]["day"].values())
    m = reads["META"]
    assert m["custom_screen"] == {"firebase_previous_class": PREV_API} and m["mets"]["adUnitExposure"]
    assert m["custom"] == 2 and m["placement"] == ["customEvent:x_placement"]
    f = a["facts"]
    rows = {r[0]: r for r in f["table"]}
    home, lst, ad, web = rows["XHomeActivity"], rows["XListActivity"], rows["AdActivity"], rows["FullScreenWebViewDisplay"]
    assert home[1:3] == ["no", 300 * W] and home[6] == 600 * W and home[8] == {"banner": 600 * W}
    assert home[9] == 6 * W and home[13] == 2.0 and home[4] == 150 * W and home[12] == 30000 * 600 * W / 1000
    assert home[11] == {"banner": 150 * W} and lst[13] == 0.5 and lst[8] == {"native": 60 * W}
    assert ad[1] == "ad" and ad[13] == 1.0 and ad[8] == {"appopen": 20 * W, "interstitial": 40 * W} and ad[9] == W
    assert web[1] == "ad" and web[10] == 8 * W and rows["XSplashActivity"][13] == 0.0
    assert [r[0] for r in f["table"]][0] == "XHomeActivity"                              # most views first
    fm = f["fmt"]
    assert {k: (v["on_ad"], v["on_host"], v["lost"]) for k, v in fm.items()} == {
        "appopen": (1.0, 0.0, 0.0), "banner": (0.0, 1.0, 0.0), "interstitial": (1.0, 0.0, 0.0),
        "native": (0.0, 1.0, 0.0), "rewarded": (1.0, 0.0, 0.0)}
    assert fm["banner"]["share"] == round(600 / IMPS, 4) and fm["native"]["raw"] == ["Native advanced"]
    assert fm["banner"]["top_host"] == ["XHomeActivity", 1.0] and f["ad_like"] == []
    assert f["adcheck"] == {"ad_views": 70 * W, "ad_views_per_fs_imp": 1.0, "ret_max": round(70 / 520, 4),
                            "ad_eng_per_view": round(950 / 70, 2)}
    assert f["screens"] == {"classes": 5, "top1": round(300 / VIEWS, 4), "c90": 4, "sca": "SC", "sca_units": True,
                            "ad_screens": ["AdActivity", "FullScreenWebViewDisplay"]}
    assert f["names"] == {"share": round(420 / VIEWS, 4), "n": 2, "max_per_class": 1, "classes_split": 0, "mixed": [],
                          "mixed_n": 0}
    assert f["obf"] == 0.0 and f["meta_extra"] == ["customEvent:x_placement"]
    assert {u[0]: (u[4], u[5], u[6]) for u in f["units"]["units"]}["unit-inter-PRIVATE"] == ("AdActivity", 1.0, 1.0)
    assert f["units"]["unit_map"]["banner"] == {"units": 1, "one99": 1.0, "one95": 1.0}
    assert f["ev"]["ev_vs_imps"] == 1.0 and f["ev"]["rev_on_imp"] == 1.0 and f["ev"]["views_tie"] == 1.0
    assert f["ev"]["custom_ad_events"] == {"x_inter_ad_show": 40 * W}
    assert f["xc"]["x_inter_ad_show"] == {"n": 40 * W, "fmt": "interstitial", "per_imp": 1.0, "on_ad": 0.0, "host": 1.0,
                                          "hosts": [["XHomeActivity", 1.0]]}
    assert f["clicks"] == {"n": 7 * W, "on_ad": round(1 / 7, 4), "fmt_named": 1.0, "tie": 1.0}
    assert f["rewards"] == {"n": 8 * W, "per_imp": 0.8} and f["eng"]["tie"] == 1.0 and f["eng"]["unset"] == 0.0
    ly = f["layers"]
    assert ly["sessions"] == {"accepted": True, "sum_ratio": 1.0} and ly["exposure"]["tie"] == 1.0
    assert ly["reach"]["banner"] == [["XHomeActivity", 150 * W, 4.0]]
    assert ly["nvr"]["daily_whole"] and 0 < ly["nvr"]["views_new"] < 1
    assert ly["ver"]["versions"] == 2 and ly["ver"]["newest"] == "9.2" and ly["ver"]["classes_new"] == []
    assert ly["country"]["countries"] == 2 and ly["country"]["whole"] and ly["country"]["rows_day"]["cvd"] == 5.0
    assert ly["sources"]["appopen"] == {"XNet Two": 1.0} and ly["pv"]["AdActivity"] == [["XHomeActivity", 1.0]]
    assert f["daily"]["vd_rows_day"] == 5.0 and f["daily"]["aud_rows_day"] == 5.0 and f["daily"]["aud_days_lossy"] == 0
    assert all(x["state"] == "whole" and x["views"] == VIEWS for x in f["recent"].values()) and len(f["recent"]) == 5
    h = f["hist"]
    assert h["first_day"] == {"screen_view": "2026-01-01", "ad_impression": "2026-01-01"} and h["gaps"] == 0
    assert h["views_from"] == h["ads_from"] == "2026-01-01" and h["cause"] == {"views": "whole", "ads": "whole"}
    assert h["hd0_w"] == {"screen_view": 1.0, "ad_impression": 1.0} and h["w_range"] == {"views": 1.0, "ads": 1.0}
    assert h["old_split"] is None and h["edge"] is None and h["per_month"][-1][0] == "202610"
    assert h["per_month"][0] == ["202601", VIEWS * 31, IMPS * 31, 1.0, 1.0, 1.0, 1.0]
    assert h["top_month"]["202610"][0] == ["XHomeActivity", 300 * 10]
    v = a["verdict"]
    assert v["word"] == "build" and v["imps_whole"] and v["views_whole"] and v["daily"] == "whole"
    assert v["fs"] == {"appopen": "sdk", "interstitial": "sdk", "rewarded": "sdk"} and v["names"] == "yes"
    assert v["recent"]["today"] == "whole" and v["newest_whole"] == "2026-10-15" and v["units1"] == {
        "banner": 1.0, "native": 1.0}
    assert v["eng_ok"] and v["eng_attr"] == "ad-screen-time" and v["ret_note"] and v["clicks"] == "yes"
    assert v["trust"] == {"imps": "absent", "rev": "absent"} and v["retention"] == "FOURTEEN_MONTHS"
    assert all(v["layers"][k] for k in ("sessions", "reach", "exposure", "nvr", "version", "source", "prev_class",
                                        "app_events")) and v["layers"]["country"] == "daily"
    s = rep["summary"]
    assert s["words"] == {"build": 1} and s["fs"]["interstitial"] == {"sdk": 1} and s["rows"][0][:2] == [KEY, "build"]
    c = rep["counts"]
    assert (c["reads"], c["ok"], c["refused"], c["off"], c["other"], c["sampled"], c["trunc"]) == (39, 39, 0, 0, 0, 0, 0)
    assert c["calls"] == 39                                                    # META + 38 reports; RET not counted
    assert c["skipped"] == 13 and c["kinds"]["AUD"] == {"n": 1, "ok": 1, "refused": 0, "off": 0, "other": 0,
                                                       "sampled": 0, "trunc": 0, "skipped": 0}


# ── T and T2, folds, formats ────────────────────────────────────────────────────────────────

def test_the_event_truth_and_the_publisher_truth_are_separate_reads(monkeypatch):
    _, a = _run(monkeypatch, FakeGA(refuse=lambda dims, mets: "publisherAdImpressions" in mets))
    r = a["reads"]
    assert r["T2"]["err"] == {"http": 400, "status": "INVALID_ARGUMENT"} and r["T"]["ok"]
    assert all(abs(v - 1) < 1e-9 for k in ("A", "F", "AF", "U", "AU") for v in r[k]["tie"].values())
    assert a["facts"]["ev"]["ev_vs_imps"] is None and a["verdict"]["word"] == "build"
    _, b = _run(monkeypatch, FakeGA(pub=0.5))
    assert b["facts"]["ev"]["ev_vs_imps"] == 2.0 and b["facts"]["ev"]["rev_on_imp"] == 1.0
    assert b["verdict"]["trust_note"] == ["ev_vs_imps"]


def test_a_silent_fold_is_caught_by_the_ties_and_a_fold_row_by_its_label(monkeypatch):
    rep, a = _run(monkeypatch, FakeGA(fold={"mode": "drop", "units": {"unit-native-PRIVATE"}}))
    au = a["reads"]["AU"]
    assert au["loss"] and au["fold_rows"] == 0 and au["tie"]["eventCount"] == round((IMPS - 60) / IMPS, 4)
    assert au["keys"]["eventCount"]["off2"] == 1 and au["keys"]["eventCount"]["w2"] == round((IMPS - 60) / IMPS, 4)
    assert au["state"] == "lossy" and au["off"]
    k = rep["counts"]["kinds"]
    assert k["AU"]["off"] == 1 and k["AU"]["other"] == 0 and rep["counts"]["other"] == 0
    assert k["A"]["off"] == 0 and k["AF"]["off"] == 0
    rep, b = _run(monkeypatch, FakeGA(fold={"mode": "label", "units": {"unit-native-PRIVATE"}}, fold_label="other"))
    au = b["reads"]["AU"]
    assert au["fold_rows"] == 1 and au["s"]["eventCount"]["fold"] == round(60 / IMPS, 4)
    assert abs(au["tie"]["eventCount"] - 1) < 1e-9 and au["state"] == "lossy"          # Σ holds, the unit does not
    assert au["keys"]["eventCount"]["off2"] == 1 and au["keys"]["eventCount"]["w2"] == round((IMPS - 60) / IMPS, 4)
    assert rep["counts"]["kinds"]["AU"]["other"] == 1 and rep["counts"]["kinds"]["A"]["other"] == 0
    assert "fold" in b["admob"] or b["admob"] == {"state": "absent"}


def test_format_shares_are_over_the_format_truth_and_every_full_screen_code():
    fm = {"AdActivity": {"interstitial": 800.0}, "(other)": {"interstitial": 50.0}, "XGameActivity": {"interstitial": 50.0,
                                                                                                     "rewarded": 400.0},
          "(not set)": {"rewarded": 500.0}, "XBreakActivity": {"rewarded": 100.0}}
    ftot = {"interstitial": 1000.0, "rewarded": 1000.0, "banner": 8000.0}
    out = ac.fmt_facts(fm, ftot, {"interstitial": {"Interstitial"}}, {"XBreakActivity"})
    it = out["interstitial"]
    assert (it["share"], it["on_ad"], it["on_host"], it["on_unset"], it["lost"]) == (0.1, 0.8, 0.05, 0.0, 0.15)
    assert it["top_host"] == ["XGameActivity", 0.05] and it["raw"] == ["Interstitial"]
    rw = out["rewarded"]
    assert (rw["on_unset"], rw["on_like"], rw["on_host"], rw["lost"]) == (0.5, 0.1, 0.4, 0.0)
    assert out["banner"]["lost"] == 1.0                                       # F has it, the split shows nothing
    base = {"share": 0.1, "lost": 0.0, "on_ad": 0.0, "on_like": 0.0, "on_unset": 0.0}
    assert ac.fs_code(dict(base, share=0.004, lost=0.5)) == "small"
    assert ac.fs_code(dict(base, lost=0.03, on_ad=0.97)) == "lost"
    assert ac.fs_code(dict(base, on_ad=0.95)) == "sdk"
    assert ac.fs_code(dict(base, on_ad=0.02, on_like=0.01, on_unset=0.02)) == "host"
    assert ac.fs_code(dict(base, on_unset=0.5)) == "unset"
    assert ac.fs_code(dict(base, on_ad=0.4, on_like=0.05)) == "check"
    assert ac.fs_code(dict(base, on_ad=0.5)) == "mixed"
    assert [ac._fmt(x) for x in ("Native advanced", "NATIVE", "native_banner", "Rewarded interstitial",
                                 "REWARDED_INTERSTITIAL", "App open", "APP_OPEN", "(other)", "other", "(not set)", None,
                                 "Sticky XL")] == ["native", "native", "native", "rewardedinterstitial",
                                                    "rewardedinterstitial", "appopen", "appopen", "fold", "fold",
                                                    "notset", "notset", "stickyxl"]


def test_ad_screens_obfuscation_and_ad_events_are_named_generically():
    for c in ("AdActivity", "com.google.android.gms.ads.AdActivity", "AudienceNetworkActivity", "AdUnitActivity",
              "AppLovinFullscreenActivity", "TTFullScreenVideoActivity", "MBRewardVideoActivity",
              "FullScreenWebViewDisplay", "com.x.y.FullScreenWebViewDisplay", "XyzInterstitialActivity"):
        assert ac.is_ad_screen(c), c
    for c in ("DownloadActivity", "ReadActivity", "ThreadActivity", "AddActivity", "RemoveAdsActivity",
              "FullScreenImageActivity", "MainActivity", "InterstitialHelpActivity", "(not set)", "", None):
        assert not ac.is_ad_screen(c), c
    assert [ac.is_obf(c) for c in ("a.b.c", "ab", "com.x.Q", "XHomeActivity", "AdActivity", "(not set)")] == \
        [True, True, True, False, False, False]
    rows = [{"eventName": n, "eventCount": c} for n, c in (("x_inter_ad_show", 9), ("ad_impression", 99), ("ShowRewardAd", 5),
                                                          ("add_to_cart", 50), ("download_done", 40), ("ads_loaded", 7))]
    assert ac.custom_ad_events(rows) == [("x_inter_ad_show", 9), ("ads_loaded", 7), ("ShowRewardAd", 5)]
    assert [ac.fmt_guess(n) for n in ("x_inter_ad_show", "ShowRewardAd", "aoa_show", "ads_loaded")] == \
        ["interstitial", "rewarded", "appopen", None]


# ── the screen dimension of the ad reads ─────────────────────────────────────────────────────

def test_a_refused_class_x_format_moves_the_ad_reads_to_the_page_path(monkeypatch):
    fake = FakeGA(refuse=lambda dims, mets: "unifiedScreenClass" in dims and "adFormat" in dims)
    _, a = _run(monkeypatch, fake)
    r = a["reads"]
    assert r["AF"]["err"]["http"] == 400 and r["AFP"]["ok"] and r["AFP"]["state"] == "whole" and a["sca"] == "PS"
    assert r["AU"]["dims"] == [ac.PS, "adFormat", "adUnitName"] and r["AU"]["state"] == "whole"
    assert _skips(a)["AUP"] == "same" and fake.other.count("CC") == 1 and r["CC"]["ok"]
    assert r["CC"]["fields"]["adFormat"] == "INCOMPATIBLE" and r["CC"]["fields"][ac.PS] == "COMPATIBLE"
    first = fake.calls.index(("unifiedScreenClass", "adFormat"))
    assert not [d for d in fake.calls[first + 1:] if "unifiedScreenClass" in d and ({"adFormat", "adUnitName"} & set(d))]
    assert a["facts"]["fmt"]["interstitial"]["on_ad"] == 1.0 and a["verdict"]["word"] == "build"
    assert a["verdict"]["imps_whole"] and a["facts"]["screens"]["sca"] == "PS"
    fake = FakeGA(refuse=lambda dims, mets: "adFormat" in dims and any(d in dims for d in SCREEN))
    rep, b = _run(monkeypatch, fake)
    assert b["sca"] == "none" and fake.other.count("CC") == 1 and b["reads"]["AFP"]["err"]["http"] == 400
    pair = {r_.id for r_ in ac.READS if ac.SCA in r_.dims} - {"AF"} | {"AUP", "OAP0", "OAP"}
    assert {k for k, why in _skips(b).items() if why == "no_shape"} == pair
    assert not [d for d in fake.calls if any(x in d for x in SCREEN) and "adFormat" in d][2:]   # AF + AFP only
    assert b["complete"] and b["verdict"]["word"] == "check" and rep["counts"]["skipped"] == len(_skips(b))


# ── sampling, the daily store, AUD1 / AUDS / AUP ─────────────────────────────────────────────

def test_a_sampled_read_is_never_whole_and_the_one_day_read_decides(monkeypatch):
    rep, a = _run(monkeypatch, FakeGA(sample=7))
    r = a["reads"]
    aud = r["AUD"]
    assert aud["sampled"] and aud["smp"] == {"read": 4000000, "space": 12000000} and aud["state"] == "sampled"
    assert all(abs(v - 1) <= 0.02 for v in aud["tie"].values()) and aud["keys"]["eventCount"]["w2"] == 1.0
    assert r["AUD1"]["state"] == "whole" and list(r["AUD1"]["day"]) == ["20261010"] and a["win"]["d*"] == "2026-10-10"
    assert _skips(a)["AUDS"] == "whole" and r["AU"]["state"] == "sampled" and r["AUP"]["state"] == "sampled"
    assert r["A"]["state"] == "whole" and r["AF"]["state"] == "sampled" and r["CAD"]["state"] == "whole"
    assert a["facts"]["daily"]["smp_space"] == 12000000 and a["facts"]["daily"]["sampled"]
    v = a["verdict"]
    assert v["daily"] == "day1" and not v["imps_whole"] and v["word"] == "build-split"
    assert a["win"]["Ba"] == ["2026-01-01", "2026-01-07"] and r["OA"]["state"] == "whole"
    assert a["facts"]["hist"]["cause"]["ads"] == "range" and _skips(a)["OAS"] == "whole"
    c = rep["counts"]
    assert c["sampled"] == sum(1 for x in r.values() if x.get("sampled")) and c["reads"] + c["skipped"] == len(r)
    _, b = _run(monkeypatch, FakeGA(fold={"mode": "drop", "units": {"unit-native-PRIVATE"}}))
    rb = b["reads"]
    assert rb["AUD"]["state"] == "lossy" and b["win"]["d*"] == "2026-10-10" and rb["AUD1"]["state"] == "lossy"
    assert rb["AUDS"]["state"] == "whole" and rb["AUP"]["state"] == "lossy" and b["verdict"]["daily"] == "no-units"
    assert b["verdict"]["word"] == "build-split" and b["facts"]["daily"]["aud_days_lossy"] == W


# ── the history ─────────────────────────────────────────────────────────────────────────────

def test_old_days_lost_by_age_are_found_with_the_truncation_edge(monkeypatch):
    monkeypatch.setattr(ac, "PAGE_ROWS", 500)                       # the long reads page
    _, a = _run(monkeypatch, FakeGA(age=EDGE))
    r, h = a["reads"], a["facts"]["hist"]
    assert r["VDH"]["pages"] == 3 and r["VDH"]["state"] == "whole" and r["AUDH"]["pages"] == 3
    assert r["AUDH"]["state"] == "lossy" and r["AUDH"]["trunc"] == [["DATA_TRUNCATION_TYPE_PROPERTY", "2026-06-01",
                                                                     [["2026-01-01", "2026-05-31"]]]]
    assert a["win"]["Ba"] == ["2026-05-25", "2026-05-31"] and r["OA"]["state"] == "lossy" and r["OA"]["trunc"]
    assert r["OAS"]["state"] == "whole" and r["OAP0"]["ok"] and r["OAP"]["state"] == "whole"
    assert h["ads_from"] == "2026-06-01" and h["views_from"] == "2026-01-01" and h["edge"] == "2026-06-01"
    assert h["cause"] == {"views": "whole", "ads": "age"} and h["old_split"] == "format"
    assert h["off_days"]["ads"][0] == ["20260531", round((IMPS - 600) / IMPS, 4)] and h["off_days"]["views"] == []
    assert r["OAP0"]["vs"]["publisherAdImpressions"]["w2"] == 1.0 and a["verdict"]["word"] == "build-from"
    _, b = _run(monkeypatch, FakeGA(age=EDGE, age_fmt=True))
    assert b["reads"]["OAS"]["state"] == "lossy" and b["facts"]["hist"]["old_split"] == "publisher"


def test_a_long_range_loss_is_whole_in_short_reads(monkeypatch):
    _, a = _run(monkeypatch, FakeGA(range_days=60, views_range=60))
    r, h = a["reads"], a["facts"]["hist"]
    assert r["VDH"]["state"] == "lossy" and a["win"]["Bv"] == ["2026-09-06", "2026-09-12"]
    assert r["OV"]["state"] == "whole" and h["cause"]["views"] == "range" and h["views_from"] is None
    assert h["w_range"]["views"] == round((VIEWS - 100) / VIEWS, 4) and r["VD"]["state"] == "whole"
    assert r["AUDH"]["state"] == "lossy" and not r["AUDH"].get("trunc") and h["ads_from"] is None
    assert a["win"]["Ba"] == ["2026-09-06", "2026-09-12"] and r["OA"]["state"] == "whole"
    assert h["cause"]["ads"] == "range" and h["old_split"] is None and _skips(a)["OAS"] == "whole"
    assert h["w_range"]["ads"] == round((IMPS - 60) / IMPS, 4)
    assert r["HD0"]["keys_sv"]["eventCount"]["w2"] == 1.0 and r["HD0"]["state"] == "whole"
    assert a["verdict"]["word"] == "build-from"


# ── Today / Yesterday ───────────────────────────────────────────────────────────────────────

def test_the_newest_days_are_bracketed_by_the_truth_before_and_after(monkeypatch):
    _, a = _run(monkeypatch, FakeGA(drift=True))
    rv, rau = a["reads"]["RV"], a["reads"]["RAU"]
    assert rv["state"] == "whole" and rau["state"] == "whole" and rv["bracket"]["screenPageViews"]["off"] == 0
    tie = sum(e[0] for e in rv["day"].values()) / ac.dp._tot(
        [{"v": e[1]} for e in rv["day"].values()], "v")                # Σ RV ÷ the after-truth: under 1, inside
    assert tie < 0.98 and all(x > 1.05 for x in rv["drift"].values())
    rec = a["facts"]["recent"]
    assert [x["state"] for x in rec.values()] == ["whole"] * 5 and a["verdict"]["newest_whole"] == "2026-10-15"
    _, b = _run(monkeypatch, FakeGA(fold_today=True))
    rec = b["facts"]["recent"]
    assert rec["2026-10-15"]["state"] == "folds" and rec["2026-10-15"]["views_in"] is False
    assert [rec[d]["state"] for d in ("2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14")] == ["whole"] * 4
    v = b["verdict"]
    assert v["recent"]["today"] == "folds" and v["recent"]["yesterday"] == "whole" and v["newest_whole"] == "2026-10-14"
    assert b["reads"]["RV"]["state"] == "lossy" and b["reads"]["RV"]["fold_rows"] == 1


# ── the conditional reads ───────────────────────────────────────────────────────────────────

def test_conditional_reads_run_only_when_needed(monkeypatch):
    _, a = _run(monkeypatch, FakeGA(no_custom=True))
    assert _skips(a)["XC"] == "no_events" and _skips(a)["PV"] == "not_registered" and a["facts"]["xc"] is None
    assert not a["verdict"]["layers"]["app_events"] and not a["verdict"]["layers"]["prev_class"]
    fake = FakeGA(refuse=lambda dims, mets: "adUnitExposure" in mets and "unifiedScreenClass" in dims)
    _, b = _run(monkeypatch, fake)
    assert b["reads"]["XE"]["err"]["http"] == 400 and b["reads"]["XEP"]["state"] == "whole"
    assert b["verdict"]["layers"]["exposure"] and b["facts"]["layers"]["exposure"]["read"] == "XEP"
    _, c = _run(monkeypatch, FakeGA(cty_drop=True))
    r = c["reads"]
    assert r["CVD"]["state"] == "lossy" and r["CV"]["state"] == "whole" and r["CAD"]["state"] == "lossy"
    assert r["CA"]["state"] == "whole" and c["verdict"]["layers"]["country"] == "window"
    assert r["CVD"]["keys"]["screenPageViews"]["w2"] == round(1 - 4 * 120 / (7 * VIEWS), 4)


def test_refused_reads_are_kept_and_every_other_read_goes_on(monkeypatch):
    rep, a = _run(monkeypatch, FakeGA(refuse_mets=("adUnitExposure",), refuse=lambda dims, mets: "appVersion" in dims))
    r = a["reads"]
    for k in ("XE0", "XE", "XEP", "AVD", "AAD"):
        assert r[k]["ok"] is False and r[k]["err"] == {"http": 400, "status": "INVALID_ARGUMENT"}, k
    assert r["META"]["mets"]["adUnitExposure"] is False and a["complete"]
    assert all(x["ok"] for k, x in r.items() if "skip" not in x and k not in ("XE0", "XE", "XEP", "AVD", "AAD"))
    assert rep["counts"]["kinds"]["XE"] == {"n": 1, "ok": 0, "refused": 1, "off": 0, "other": 0, "sampled": 0,
                                           "trunc": 0, "skipped": 0}
    assert rep["counts"]["refused"] == 5 and not a["verdict"]["layers"]["exposure"]
    assert not a["verdict"]["layers"]["version"] and a["verdict"]["word"] == "build"


def test_a_429_stops_the_property_and_a_bug_costs_one_read_only(monkeypatch):
    fake = FakeGA(fail=lambda dims, mets, days: "HTTP 429: RESOURCE_EXHAUSTED: DETAIL-PRIVATE"
                  if dims == ["date", "unifiedScreenClass"] and days > W else None)          # VDH: the history
    rep, a = _run(monkeypatch, fake)
    assert a["stopped"] == "quota_429" and not a["complete"] and a["reads"]["VDH"]["err"]["http"] == 429
    assert a["reads"]["HD0"]["state"] == "whole" and "AUDH" not in a["reads"] and a["facts"]["hist"]["first_day"]
    assert rep["counts"]["complete"] == 0 and rep["counts"]["refused"] == 0
    assert ac.public_line(rep["counts"], True).startswith("activity probe: apps 1, complete 0,")

    def boom(c):
        raise ZeroDivisionError("PRIVATE")
    monkeypatch.setattr(ac, "pick_dstar", boom)
    _, b = _run(monkeypatch, FakeGA())
    assert b["complete"] and b["reads"]["AUD"]["bug"] == "ZeroDivisionError" and b["reads"]["AUD"]["state"] == "whole"
    assert b["reads"]["AUDH"]["state"] == "whole" and b["verdict"]["word"] == "build"


# ── the verdict ─────────────────────────────────────────────────────────────────────────────

def test_verdict_words_mixed_names_and_obfuscated_classes(monkeypatch):
    base = {"imps_whole": True, "views_whole": True, "daily": "whole", "cause": {"ads": "whole"},
            "ads_from": "2026-01-01", "first_ad": "2026-01-01"}
    assert ac.verdict_word(dict(base, no_screens=True, one_screen=True)) == "no-screens"
    assert ac.verdict_word(dict(base, one_screen=True, screens="one-screen")) == "one-screen"
    assert ac.verdict_word(dict(base, one_screen=True, screens="use-names")) == "use-names"
    assert ac.verdict_word(base) == "build"
    assert ac.verdict_word(dict(base, ads_from="2026-06-01", cause={"ads": "age"})) == "build-from"
    assert ac.verdict_word(dict(base, ads_from=None, cause={"ads": "range"})) == "build-from"
    assert ac.verdict_word(dict(base, imps_whole=False, daily="day1")) == "build-split"
    assert ac.verdict_word(dict(base, daily="no-units")) == "build-split"
    assert ac.verdict_word(dict(base, imps_whole=False)) == "check"
    assert ac.verdict_word(dict(base, cause={"ads": "unknown"})) == "check"
    assert ac.verdict_word(dict(base, daily="page_path")) == "check"
    vn = [{ac.SC: "XHomeActivity", ac.SN: "home", "screenPageViews": 50},
          {ac.SC: "XHomeActivity", ac.SN: "(not set)", "screenPageViews": 50},
          {ac.SC: "XListActivity", ac.SN: "list", "screenPageViews": 100},
          {ac.SC: "XListActivity", ac.SN: "list_b", "screenPageViews": 10}]
    assert ac.names_facts(vn) == {"share": round(160 / 210, 4), "n": 3, "max_per_class": 2, "classes_split": 1,
                                  "mixed": ["XHomeActivity"], "mixed_n": 1}
    p = ac.plan_of(unit(), NOW)
    c = _ctx(p, {"V": [{ac.SC: "a.b", "screenPageViews": 100}, {ac.SC: "XHomeActivity", "screenPageViews": 300}]})
    assert ac.f_obf(c, ac.base(c)) == 0.25
    _, a = _run(monkeypatch, FakeGA(no_views=True))
    assert a["verdict"]["no_screens"] and a["verdict"]["word"] == "no-screens"


# ── AdMob (offline) ─────────────────────────────────────────────────────────────────────────

def _clone(tmp_path, rows):
    os.makedirs(tmp_path / "data", exist_ok=True)
    os.makedirs(tmp_path / "site", exist_ok=True)
    (tmp_path / "data" / "mediation_unit.json").write_text(json.dumps(rows), encoding="utf-8")
    (tmp_path / "site" / "dashboard.json").write_text(json.dumps({"report_tz": "UTC"}), encoding="utf-8")
    return str(tmp_path)


def _mu(d, uid, name, fmt, imps, clicks=0, micros=0, req=0, matched=0, cur="USD", app=AID):
    return {"report_date": d, "app_id": app, "ad_unit_id": uid, "unit_name": name, "format": fmt, "impressions": imps,
            "clicks": clicks, "estimated_earnings_micros": micros, "ad_requests": req, "matched_requests": matched,
            "currency_code": cur}


ADMOB_ROWS = [_mu(d, "ca-unit-1", "unit-banner-PRIVATE", "BANNER", 100, 2, 40000, 200, 150)
              for d in ("2026-09-12", "2026-09-13", "2026-09-14")] + [
    _mu("2026-09-13", "ca-unit-2", "unit-native-PRIVATE", "NATIVE", 50, micros=50000),
    _mu("2026-09-14", "ca-unit-3", "unit-native-PRIVATE", "NATIVE", 10, micros=10000),        # the same name again
    _mu("2026-09-13", "ca-unit-4", "unit-gone-PRIVATE", "INTERSTITIAL", 5, micros=30000),     # GA4 never shows it
    _mu("2026-09-13", "ca-unit-5", "", "REWARDED", 7, micros=70000),                          # matched by its id
    _mu("2026-08-15", "ca-unit-1", "unit-banner-PRIVATE", "BANNER", 300, micros=120000),     # H only
    _mu("2026-09-13", "x", "y", "BANNER", 999, 9, app="ca-app-pub-0000000000000000~99")]      # another app


def _admob_ctx():
    p = {"a": date(2026, 9, 13), "F": date(2026, 9, 14), "days": 2, "h0": date(2026, 8, 1)}
    got = {"F": [{"adFormat": "Banner", "eventCount": 180, "totalAdRevenue": 0.072},
                 {"adFormat": "Native advanced", "eventCount": 60, "totalAdRevenue": 0.06},
                 {"adFormat": "Rewarded", "eventCount": 7, "totalAdRevenue": 0.07}],
           "U": [{"adFormat": "Banner", "adUnitName": "unit-banner-PRIVATE", "eventCount": 180, "totalAdRevenue": 0.072},
                 {"adFormat": "Native advanced", "adUnitName": "unit-native-PRIVATE", "eventCount": 60,
                  "totalAdRevenue": 0.06},
                 {"adFormat": "Rewarded", "adUnitName": "ca-unit-5", "eventCount": 7, "totalAdRevenue": 0.07}],
           "EV": [{"eventName": "ad_click", "eventCount": 4}, {"eventName": "ad_impression", "eventCount": 247}],
           "FD": [{"date": "20260913", "adFormat": "Banner", "eventCount": 90}, {"date": "20260914", "adFormat":
                                                                                  "Banner", "eventCount": 99},
                  {"date": "20260913", "adFormat": "Native advanced", "eventCount": 50}],
           "HD0": [{"date": "20260815", "eventName": "ad_impression", "eventCount": 300, "totalAdRevenue": 0.12},
                   {"date": "20260913", "eventName": "ad_impression", "eventCount": 140, "totalAdRevenue": 0.1},
                   {"date": "20260914", "eventName": "ad_impression", "eventCount": 99, "totalAdRevenue": 0.04},
                   {"date": "20260914", "eventName": "screen_view", "eventCount": 1000, "totalAdRevenue": 0}]}
    return _ctx(p, got, ok=("EV", "HD0"))


def test_admob_is_read_offline_and_compared_on_the_same_days(tmp_path):
    u = unit()
    adm = ac.load_admob(_clone(tmp_path, ADMOB_ROWS), [u], now=NOW)
    assert adm["state"] == "ok" and adm["tz"] == "UTC" and set(adm["apps"]) == {KEY}
    me = adm["apps"][KEY]
    assert me["cur"] == ["USD"] and me["raw"]["native"] == ["NATIVE"] and me["ids"] == 1
    t = ac.admob_tie(adm, u, _admob_ctx())
    assert t["fmt"] == {"banner": [180, 200, 0.9], "native": [60, 60, 1.0], "interstitial": [0, 5, 0.0],
                        "rewarded": [7, 7, 1.0]}
    assert t["all"] == round(247 / 272, 4) and t["admob_days"] == 2 and t["days"] == 2 and t["tz_ga4"] == "UTC"
    assert t["rev"]["banner"] == [0.072, 0.08, 0.9] and t["all_rev"] == round(0.202 / 0.24, 4)
    assert t["clicks"] == [4, 4, 1.0]
    units = {x[0]: x for x in t["units"]}
    assert units["unit-banner-PRIVATE"] == ["unit-banner-PRIVATE", "banner", 180, 200, 0.9, 0.072, 0.08, 0.9, 400, 300,
                                            "name", False]
    assert units["unit-native-PRIVATE"][3:5] == [60, 1.0] and units["unit-native-PRIVATE"][10:] == ["name", True]
    assert units["ca-unit-5"][10] == "id" and units["unit-gone-PRIVATE"][2:5] == [0, 5, 0.0]
    assert units["unit-gone-PRIVATE"][10] == "admob_only"
    lo, hi = 140 / 162, 99 / 110                                   # GA4 ÷ AdMob on 13 and 14 Sep
    assert t["day"] == {"n": 2, "p10": round(lo + 0.1 * (hi - lo), 4), "p50": round((lo + hi) / 2, 4),
                        "p90": round(lo + 0.9 * (hi - lo), 4)}
    assert t["month"][0] == ["202608", 300, 300, 1.0, 0.12, 0.12, 1.0, 1] and t["ga4_from"] == "202608"
    assert ac.verdict.__name__ and ac.trust(t["all"]) == "match" and ac.trust(1.3) == "high" and ac.trust(2.0) == \
        "double" and ac.trust(0.8) == "short" and ac.trust(0.5) == "low" and ac.trust(None) == "absent"
    eur = ac.load_admob(_clone(tmp_path / "eur", ADMOB_ROWS + [_mu("2026-09-13", "ca-unit-1", "unit-banner-PRIVATE",
                                                                   "BANNER", 1, cur="EUR")]), [u], now=NOW)
    te = ac.admob_tie(eur, u, _admob_ctx())
    assert "rev" not in te and "all_rev" not in te and te["cur"] == ["EUR", "USD"]
    assert te["units"][0][6] is None and te["month"][0][5] is None
    assert ac.admob_tie({"state": "absent"}, u, _admob_ctx()) == {"state": "absent"}
    assert ac.load_admob(str(tmp_path / "nope"), [u]) == {"state": "absent"}


# ── the run, the public log, the size guard, the workflow ───────────────────────────────────

def test_main_writes_privately_and_prints_one_counts_only_line(monkeypatch, capsys, tmp_path):
    _patch(monkeypatch, FakeGA(custom=("firebase_previous_class",)))
    monkeypatch.setattr(ac.sp, "load_state", lambda root: {})
    monkeypatch.setattr(ac.cp, "units_from_state", lambda st: [unit()])
    monkeypatch.setattr(ac.ga4_probe, "owner_tokens", lambda env: ([("o", RT)], 0))
    put = {}
    monkeypatch.setattr(ac.pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    tick = itertools.count(0, 9)
    env = {"GA4_CLIENT_ID": "c", "GA4_CLIENT_SECRET": "s", "ACTIVITY_DATA_DIR": str(tmp_path)}
    ac.main(env, now=NOW, clock=lambda: float(next(tick)))
    rep = json.loads(put[ac.OUT_PATH])
    assert set(put) == {"ga4/activity_probe.json"} and set(rep["apps"]) == {KEY} and rep["v"] == 2
    assert rep["counts"]["complete"] == 1 and rep["rules"]["admob"] == "absent" and "trimmed" not in rep
    out = capsys.readouterr().out.splitlines()
    res = [ln for ln in out if ln.startswith("activity probe:")]
    beats = [ln for ln in out if ln.startswith("activity progress:")]
    assert len(res) == 1 and beats and len(res) + len(beats) == len(out)
    assert re.fullmatch(r"activity probe: apps 1, complete 1, zone missing 0, reads 39, ok 39, refused 0, off 0, other 0, "
                        r"sampled 0, truncated 0, skipped 13, calls 39, \d+s, saved yes", res[0]), res[0]
    assert all(re.fullmatch(r"activity progress: apps [01]/1, calls \d+, \d+s", b) for b in beats), beats
    _no_leak("\n".join(out))
    monkeypatch.setattr(ac.pr, "write_private", lambda path, text, msg: False)
    with pytest.raises(SystemExit) as e:
        ac.main(env, now=NOW, clock=lambda: float(next(tick)))
    assert e.value.code == 1
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("activity probe: apps 1,") and last.endswith(", saved no")


def test_the_size_guard_drops_the_biggest_data_first_then_the_long_day_maps():
    day = {"2026%04d" % i: [1, 1, 0.0, 0.0, True, None] for i in range(101, 400)}
    rep = {"apps": {"k": {"reads": {"A": {"data": [["x" * 40, 1.0]] * 300}, "V": {"data": [["y" * 40, 1.0]] * 50},
                                    "VDH": {"day": dict(day)}, "AUDH": {"day": dict(day)}, "VD": {"day": dict(day)}},
                          "facts": {"hist": {"per_month": [["202601", 1, 1, 1.0, 1.0, 1.0, 1.0]]}}}}}
    full = len(ac.pr._dump(rep))
    one = json.loads(ac.dump_guarded(copy.deepcopy(rep), limit=full - 100))
    r = one["apps"]["k"]["reads"]
    assert one["trimmed"] == 1 and "data" not in r["A"] and "data" in r["V"] and "day" in r["VDH"]
    every = json.loads(ac.dump_guarded(copy.deepcopy(rep), limit=100))
    r = every["apps"]["k"]["reads"]
    assert every["trimmed"] == 4 and "data" not in r["V"] and "day" not in r["VDH"] and "day" not in r["AUDH"]
    assert "day" in r["VD"] and every["apps"]["k"]["facts"]["hist"]["per_month"]
    assert "trimmed" not in json.loads(ac.dump_guarded(copy.deepcopy(rep)))


def test_a_counts_only_heartbeat_at_least_every_minute(capsys):
    t = iter(range(0, 1000, 25))
    run = ac.Run(clock=lambda: float(next(t)), total=3)
    for _ in range(6):
        run.tick()
    assert capsys.readouterr().out.splitlines() == ["activity progress: apps 0/3, calls 3, 75s",
                                                    "activity progress: apps 0/3, calls 6, 150s"]


def test_the_workflow_keeps_inputs_and_secrets_off_the_public_log():
    with open(os.path.join(ROOT, ".github", "workflows", "ga4-activity-probe.yml"), encoding="utf-8") as fh:
        raw = fh.read()
    wf = yaml.safe_load(raw)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and set(on["workflow_dispatch"]["inputs"]) == {"apps"}
    assert wf["permissions"] == {"contents": "read"} and "github.event.inputs" not in raw and "inputs." not in raw
    job = wf["jobs"]["probe"]
    assert job["runs-on"] == "ubuntu-24.04" and wf["concurrency"]["group"] == "ga4-activity-probe"
    steps = job["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    (clone,) = [st for st in steps if "clone" in (st.get("run") or "")]
    assert "> /dev/null 2>&1" in clone["run"] and "::add-mask::" in clone["run"] and "timeout 480 git " in clone["run"]
    assert "@github.com" not in clone["run"] and not any(k.startswith("GA4_") for k in clone.get("env") or {})
    assert 3 + 8 + 1 + ac.BUDGET_SEC / 60 + 4 <= job["timeout-minutes"]
    (st,) = [s for s in steps if s.get("name") == "Run"]
    assert st["run"].startswith("python -m admob_iq.fetch.ga4_activity_probe 2>/tmp/")
    assert "details kept off the public log" in st["run"] and st["env"]["ACTIVITY_DATA_DIR"] == "_private"
    assert not any(k.startswith("GA4_") for s in steps if s is not st for k in (s.get("env") or {}))
