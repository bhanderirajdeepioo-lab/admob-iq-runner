"""Google Ads install probe (admob_iq.fetch.gads_inst_probe) — offline, against a fake Google Ads API (google_ads._search
mocked; SYNTHETIC accounts, stores and numbers): the Play installs and the Firebase first opens of every app campaign by
day and by country, each conversion action by its type (a secondary one too: all_conversions), the build's biddable
installs beside them, a refused request kept as refused while the rest goes on, and a PUBLIC line of counts only."""
import re

import pytest

from admob_iq.fetch import gads_geo_probe as gp
from admob_iq.fetch import gads_inst_probe as ip
from admob_iq.fetch import google_ads
from tests.test_gads_geo_probe import (A1, A2, A3, BIG, CTY, DEV, ISO, MCC, MGR, MID, NOW, SECRETS, SETTINGS, SMALL, TOK,
                                       days)

PLAY_A, FO_A = "ANDROID_INSTALLS_ALL_OTHER_APPS", "FIREBASE_ANDROID_FIRST_OPEN"
REFUSE = "HTTP 400: queryError=PROHIBITED_SEGMENT_WITH_METRIC_IN_SELECT_OR_WHERE_CLAUSE — SECRETDETAIL"


class FakeAds:
    """A1 bids on first_open for BIG and SMALL (Play installs only as its secondary "all other apps" action), A2 on
    Google Play installs for MID (first_open secondary), A3 has no app campaign. A day: Play installs BIG 100, SMALL 10,
    MID 50; first opens BIG 90, SMALL 8, MID 45; by country the CTY shares. refuse[kind] = customer ids (or "*")."""

    def __init__(self, refuse=None):
        self.refuse, self.queries = refuse or {}, []
        self.stores = {A1: (BIG, SMALL), A2: (MID,), A3: ()}
        self.play, self.fo = {BIG: 100, SMALL: 10, MID: 50}, {BIG: 90, SMALL: 8, MID: 45}
        self.acts = {A1: {"7": (FO_A, BIG, False), "8": (PLAY_A, None, False), "9": (FO_A, SMALL, False),
                          "10": ("UNKNOWN", None, True)},
                     A2: {"1": ("GOOGLE_PLAY_DOWNLOAD", MID, True), "2": (FO_A, MID, False)}, A3: {}}

    @staticmethod
    def kind(q):
        if "FROM customer_client" in q:
            return "ROSTER"
        if "FROM geo_target_constant" in q:
            return "G5"
        if "FROM conversion_action" in q:
            return "CA" if "app_id" in q else "CA_MIN"
        if "FROM geographic_view" in q:
            return "GEO"
        if "segments.conversion_action" in q:
            return "CONV"
        if "biddable_app_install_conversions" in q:
            return "INST"
        raise AssertionError(q)

    def search(self, customer_id, login, dev, token, query):
        assert (login, dev, token) == (MCC, DEV, TOK)
        k = self.kind(query)
        self.queries.append((customer_id, k))
        r = self.refuse.get(k, ())
        if customer_id in r or "*" in r:
            raise RuntimeError(REFUSE)
        if k == "ROSTER":
            return [{"customerClient": {"id": a, "currencyCode": "INR", "descriptiveName": "SECRET", "manager": False,
                                        "timeZone": "Asia/Calcutta"}} for a in (A1, A2, A3)] \
                + [{"customerClient": {"id": MGR, "manager": True}}]
        if k == "G5":
            return [{"geoTargetConstant": {"id": i, "countryCode": c}} for i, c in ISO.items()]
        if k in ("CA", "CA_MIN"):
            return [{"conversionAction": dict({"id": i, "type": t, "category": "DOWNLOAD"},
                                              **({"appId": app, "status": "ENABLED", "includeInConversionsMetric": inc,
                                                  "primaryForGoal": inc} if k == "CA" else {}))}
                    for i, (t, app, inc) in self.acts[customer_id].items()]
        m = re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", query)
        ds = [d for d in days() if m.group(1) <= d <= m.group(2)]
        out, acts, goal_fo = [], self.acts[customer_id], customer_id == A1
        for s in self.stores[customer_id]:
            camp = {"id": "5", "appCampaignSetting": {"appId": s}}
            ip_ = next(i for i, v in acts.items() if v[0] in ip.PLAY and v[1] in (s, None))
            if_ = next(i for i, v in acts.items() if v[0] == FO_A and v[1] == s)
            for d in ds:
                ca = lambda i: "customers/%s/conversionActions/%s" % (customer_id, i)
                if k == "INST":
                    out.append({"campaign": camp, "segments": {"date": d},
                                "metrics": {"biddableAppInstallConversions": self.fo[s] if goal_fo else self.play[s]}})
                elif k == "CONV":
                    for i, v in ((ip_, self.play[s]), (if_, self.fo[s])):
                        out.append({"campaign": camp, "segments": {"date": d, "conversionAction": ca(i)},
                                    "metrics": {"allConversions": v, "conversions": v if (i == if_) == goal_fo else 0}})
                elif k == "GEO":
                    for cc, share in CTY:
                        for i, v in ((ip_, self.play[s]), (if_, self.fo[s])):
                            out.append({"campaign": camp, "segments": {"date": d, "conversionAction": ca(i)},
                                        "geographicView": {"countryCriterionId": cc, "locationType": "LOCATION_OF_PRESENCE"},
                                        "metrics": {"allConversions": v * share / 100}})
        return out


@pytest.fixture
def fake(monkeypatch):
    def make(**kw):
        f = FakeAds(**kw)
        monkeypatch.setattr(google_ads, "_search", f.search)
        return f
    monkeypatch.setattr(gp, "_sleep", lambda s: None)
    return make


def _run():
    return ip.run_probe(SETTINGS, TOK, now=NOW, workers=1, tick=0)


def test_play_installs_and_first_opens_by_day_and_country(fake, capsys):
    f = fake()
    rep = _run()
    sm = rep["summary"]["stores"]
    assert set(sm) == {BIG, SMALL, MID} and len(days()) == 28
    big = sm[BIG]
    assert big["play"] == 2800 and big["first_open"] == 2520 and big["ratio"] == 0.9 and big["inst"] == 2520
    assert big["t"] == {PLAY_A: [2800, 0], FO_A: [2520, 2520]} and big["geo"] == {PLAY_A: 2800, FO_A: 2520}
    assert sm[MID]["play"] == 1400 and sm[MID]["t"]["GOOGLE_PLAY_DOWNLOAD"] == [1400, 1400] and sm[MID]["inst"] == 1400
    assert sm[SMALL]["ratio"] == 0.8
    assert rep["stores"][BIG]["cc"] == {"US": {PLAY_A: 1400, FO_A: 1260}, "IN": {PLAY_A: 840, FO_A: 756},
                                        "BR": {PLAY_A: 560, FO_A: 504}}
    d0 = rep["stores"][MID]["days"][days()[0]]
    assert d0 == {"inst": 50, "t": {"GOOGLE_PLAY_DOWNLOAD": [50, 50], FO_A: [45, 0]}}
    assert rep["summary"]["with_play"] == 3 and rep["summary"]["both"] == 3
    assert rep["accounts"][A1]["ca"] == {FO_A: [2, 0], PLAY_A: [1, 0], "UNKNOWN": [1, 1]}
    assert rep["accounts"][A3]["no_installs"] and not {k for a, k in f.queries if a == A3} & {"CONV", "GEO"}
    assert all("_fold" not in a for a in rep["accounts"].values())
    c = rep["counts"]
    assert (c["accounts"], c["of"], c["conv_ok"], c["conv_of"], c["geo_ok"], c["geo_of"]) == (3, 3, 2, 2, 2, 2)
    line = ip.public_line(c)
    out = capsys.readouterr().out + line
    for s in SECRETS + ["2800", "0.9", "INR"]:
        assert s not in out, s
    assert re.fullmatch(r"gads inst probe: accounts 3/3, calls \d+, errors 0, installs accepted 3/3, conversion actions "
                        r"accepted 3/3, per-action conversions accepted 2/2, per-country accepted 2/2, stores 3, with a "
                        r"Play count 3, with first opens 3, both 3, stopped 0, \d+s", line), line


def test_a_refused_request_is_kept_and_the_rest_goes_on(fake):
    fake(refuse={"GEO": {A2}, "CA": {A1}})
    rep = _run()
    a2 = rep["accounts"][A2]["calls"]["GEO"]
    assert a2["err"]["http"] == 400 and "queryError=PROHIBITED" in a2["err"]["code"]
    assert rep["stores"][MID]["cc"] == {} and rep["summary"]["stores"][MID]["play"] == 1400
    # A1's CA refused → asked once more without the app id (CA_MIN): the types still known
    assert rep["accounts"][A1]["calls"]["CA_MIN"]["n"] == 1 and rep["summary"]["stores"][BIG]["play"] == 2800
    c = rep["counts"]
    assert (c["geo_ok"], c["geo_of"], c["ca_ok"], c["ca_of"], c["errors"]) == (1, 2, 3, 3, 2)
