"""Google Ads geo probe (admob_iq.fetch.gads_geo_probe) and the roster's time_zone (google_ads._child_accounts) —
offline, against a fake Google Ads API (google_ads._search mocked): every request shape (the spend / installs paths,
Q-G1 presence and area of interest, user_location_view, Q-G2, Q-G3, the conversion actions), the G1–G8 maths on a
synthetic MCC whose truth is known, refused requests kept as their code only, the quota / time-budget stops, a report
that is written even when the bookkeeping has a bug, and a PUBLIC log that stays counts-only. All data is synthetic."""

import json
import os
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq.fetch import gads_geo_probe as gp
from admob_iq.fetch import google_ads

NOW = datetime(2026, 9, 27, 6, 0, tzinfo=timezone.utc)
START, END, SETTLED_END = date(2026, 8, 30), date(2026, 9, 26), date(2026, 9, 24)
MCC = "1112223333"
A1, A2, A3, MGR = "1234567890", "2345678901", "3456789012", "9999999999"
BIG, MID, SMALL = "com.secret.big", "com.secret.mid", "com.secret.small"
DEV, RT, TOK, CID, CSEC = "dev-SECRET", "rt-SECRET", "tok-SECRET", "cid-SECRET", "csec-SECRET"
SECRETS = [MCC, A1, A2, A3, MGR, BIG, MID, SMALL, DEV, RT, TOK, CID, CSEC, "secret", "SECRET", "Asia/Calcutta",
           "America/", "2026-", "US", "0.9"]
CTY = (("2840", 50), ("2356", 30), ("2076", 20))               # US / IN / BR % of every store's geo split
ISO = {"2840": "US", "2356": "IN", "2076": "BR", "2826": "GB", "2276": "DE"}
REFUSE = "HTTP 400: queryError=PROHIBITED_SEGMENT_WITH_METRIC_IN_SELECT_OR_WHERE_CLAUSE — SECRETDETAIL %s" % A2
SETTINGS = {"google_ads_dev_token": DEV, "google_ads_login_customer_id": MCC, "google_ads_refresh_token": RT,
            "client_id": CID, "client_secret": CSEC}


def days():
    return [(START + timedelta(days=i)).isoformat() for i in range((END - START).days + 1)]


class FakeAds:
    """A synthetic MCC. Accounts A1 (INR, Asia/Calcutta: BIG + SMALL), A2 (INR, America/Los_Angeles: MID), A3 (INR, no
    spend) and a nested manager. Cost a day: BIG 600, MID 300, SMALL 100 (units of 10^6 micros); SMALL also has a
    non-MULTI_CHANNEL campaign holding 20% of its cost. Per country (CTY %) presence = presence[store] % of the
    MULTI_CHANNEL cost, area of interest = 95 %, user location = 100 %; installs a day BIG 100, MID 40, SMALL 5;
    DOWNLOAD conversions = 0.9 × installs. Integer micros throughout, so every expected ratio is exact.
    `refuse[kind]` = customer ids (or "*") that get an HTTP 400; `raise_for[kind]` = (ids, text)."""

    def __init__(self, presence=None, extra_country=None, ccy=None, tz_refused=False):
        self.presence = {BIG: 100, MID: 100, SMALL: 100, **(presence or {})}
        self.extra_country, self.tz_refused = extra_country, tz_refused
        self.ccy = {A1: "INR", A2: "INR", A3: "INR", **(ccy or {})}
        self.stores = {A1: {BIG: 600, SMALL: 100}, A2: {MID: 300}, A3: {}}
        self.inst = {BIG: 100, MID: 40, SMALL: 5}
        self.camps = {BIG: [("11", "MULTI_CHANNEL", 100)], MID: [("21", "MULTI_CHANNEL", 100)],
                      SMALL: [("12", "MULTI_CHANNEL", 80), ("13", "DISPLAY", 20)]}
        self.refuse, self.raise_for, self.queries, self.on_call = {}, {}, [], None

    def kind(self, q):
        if "FROM customer_client" in q:
            return "ROSTER"
        if "FROM geo_target_constant" in q:
            return "G5"
        if "FROM conversion_action" in q:
            return "CA" if "counting_type" in q else "CA_MIN"
        if "FROM user_location_view" in q:
            return "ULV"
        if "FROM geographic_view" in q:
            return "G2" if "conversion_action_category" in q else "G1I" if "AREA_OF_INTEREST" in q else "G1P"
        if "campaign.advertising_channel_sub_type" in q:
            return "CHAN"
        if "biddable_app_install_conversions" in q:
            return "INST"
        return "SPEND"

    def cty(self):
        return CTY + ((self.extra_country, 1),) if self.extra_country else CTY

    def search(self, customer_id, login, dev, token, query):
        assert (login, dev, token) == (MCC, DEV, TOK)
        k = self.kind(query)
        self.queries.append((customer_id, k, query))
        if self.on_call:
            self.on_call(k)
        ids, text = self.raise_for.get(k, ((), ""))
        if customer_id in ids or "*" in ids:
            raise RuntimeError(text)
        if customer_id in self.refuse.get(k, ()) or "*" in self.refuse.get(k, ()):
            raise RuntimeError(REFUSE)
        if k == "ROSTER":
            if self.tz_refused and "time_zone" in query:
                raise RuntimeError("HTTP 400: queryError=UNRECOGNIZED_FIELD — SECRETDETAIL")
            rows = [{"customerClient": {"id": a, "currencyCode": self.ccy[a], "descriptiveName": "SECRET " + a,
                                        "manager": False, "timeZone": tz}}
                    for a, tz in ((A1, "Asia/Calcutta"), (A2, "America/Los_Angeles"), (A3, "Asia/Calcutta"))]
            return rows + [{"customerClient": {"id": MGR, "manager": True, "timeZone": "Asia/Calcutta"}}]
        if k == "G5":
            return [{"geoTargetConstant": {"id": i, "countryCode": c}} for i, c in ISO.items()]
        if k in ("CA", "CA_MIN"):
            return [{"conversionAction": {"id": "1", "category": "DOWNLOAD", "type": "GOOGLE_PLAY_DOWNLOAD",
                                          "status": "ENABLED", "clickThroughLookbackWindowDays": "30",
                                          "includeInConversionsMetric": True, "countingType": "ONE_PER_CLICK",
                                          "primaryForGoal": True}},
                    {"conversionAction": {"id": "2", "category": "PURCHASE", "type": "FIREBASE_ANDROID_CUSTOM",
                                          "status": "ENABLED", "clickThroughLookbackWindowDays": "90",
                                          "includeInConversionsMetric": False, "countingType": "MANY_PER_CLICK",
                                          "primaryForGoal": False}},
                    {"conversionAction": {"id": "3", "category": "DOWNLOAD", "status": "REMOVED"}}]
        if k == "CHAN":
            return [{"campaign": {"id": cid, "advertisingChannelType": ch, "advertisingChannelSubType": "X"}}
                    for s in self.stores[customer_id] for cid, ch, _ in self.camps[s]]
        m = re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", query)
        ds = [d for d in days() if m.group(1) <= d <= m.group(2)]
        out = []
        for s, per_day in self.stores[customer_id].items():
            camp = lambda cid: {"id": cid, "name": "SECRET", "status": "ENABLED", "appCampaignSetting": {"appId": s}}
            for d in ds:
                seg = {"date": d}
                if k == "SPEND":
                    out += [{"campaign": camp(cid), "metrics": {"costMicros": str(per_day * 10 ** 6 * sh // 100)},
                             "segments": seg} for cid, _, sh in self.camps[s]]
                elif k == "INST":
                    out.append({"campaign": camp("x"), "segments": seg,
                                "metrics": {"biddableAppInstallConversions": self.inst[s], "conversionsValue": 1.5}})
                else:
                    for cid, ch, sh in self.camps[s]:
                        if ch != "MULTI_CHANNEL":
                            continue
                        for cc, share in self.cty():
                            cost = per_day * 10 ** 6 * sh * share // 10000
                            if k == "G1P":
                                out.append({"campaign": camp(cid), "segments": seg,
                                            "geographicView": {"countryCriterionId": cc,
                                                               "locationType": "LOCATION_OF_PRESENCE"},
                                            "metrics": {"costMicros": str(cost * self.presence[s] // 100),
                                                        "impressions": "10", "clicks": "1"}})
                            elif k == "G1I":
                                out.append({"campaign": camp(cid), "segments": seg,
                                            "geographicView": {"countryCriterionId": cc,
                                                               "locationType": "AREA_OF_INTEREST"},
                                            "metrics": {"costMicros": str(cost * 95 // 100)}})
                            elif k == "ULV":
                                out.append({"campaign": camp(cid), "segments": seg,
                                            "userLocationView": {"countryCriterionId": cc, "targetingLocation": True},
                                            "metrics": {"costMicros": str(cost)}})
                            elif k == "G2":
                                out.append({"campaign": camp(cid),
                                            "segments": {**seg, "conversionActionCategory": "DOWNLOAD"},
                                            "geographicView": {"countryCriterionId": cc,
                                                               "locationType": "LOCATION_OF_PRESENCE"},
                                            "metrics": {"conversions": self.inst[s] * sh * share * 9 / 100000}})
        return out


@pytest.fixture
def fake(monkeypatch):
    def make(**kw):
        f = FakeAds(**kw)
        monkeypatch.setattr(google_ads, "_search", f.search)
        return f
    monkeypatch.setattr(gp, "_sleep", lambda s: None)
    return make


def _run(workers=1, **kw):
    kw.setdefault("packages", {BIG, MID, "com.secret.other"})
    return gp.run_probe(SETTINGS, TOK, now=NOW, workers=workers, tick=0, **kw)


# ── the roster's time zone (google_ads.py) ──────────────────────────────────────────────────────

def test_the_roster_asks_the_time_zone_and_keeps_it_per_account(fake):
    f = fake()
    accts = google_ads._child_accounts(MCC, DEV, TOK)
    (q,) = [q for _, k, q in f.queries if k == "ROSTER"]
    assert "customer_client.time_zone" in q and q.endswith("FROM customer_client")
    assert [a["id"] for a in accts] == [A1, A2, A3]                                    # the manager is skipped
    assert {a["id"]: a["tz"] for a in accts} == {A1: "Asia/Calcutta", A2: "America/Los_Angeles", A3: "Asia/Calcutta"}
    assert set(accts[0]) == {"id", "currency", "name", "tz"}


def test_a_refused_time_zone_asks_the_old_roster_and_spend_is_unchanged(fake, monkeypatch):
    f = fake(tz_refused=True)
    accts = google_ads._child_accounts(MCC, DEV, TOK)
    qs = [q for _, k, q in f.queries if k == "ROSTER"]
    assert len(qs) == 2 and "time_zone" in qs[0] and "time_zone" not in qs[1]
    assert [a["id"] for a in accts] == [A1, A2, A3] and all("tz" not in a for a in accts)
    s = {"google_ads_dev_token": DEV, "google_ads_login_customer_id": MCC, "google_ads_refresh_token": RT,
         "google_ads_client_id": CID, "google_ads_client_secret": CSEC}
    monkeypatch.setattr(google_ads, "_access_token", lambda cid, csec, rt: TOK)
    refused = google_ads.fetch_app_spend(s, START.isoformat(), END.isoformat(), mode="live")
    f.tz_refused = False
    with_tz = google_ads.fetch_app_spend(s, START.isoformat(), END.isoformat(), mode="live")
    # the spend / installs / convval the build caches are the same with or without the new field — no "tz" leaks in
    assert json.dumps(refused, sort_keys=True) == json.dumps(with_tz, sort_keys=True)
    assert "tz" not in json.dumps(with_tz) and set(with_tz["daily"]) == {BIG, MID, SMALL}


# ── the probe: requests ─────────────────────────────────────────────────────────────────────────

def test_every_request_is_the_specs_shape_over_the_last_28_days(fake):
    f = fake()
    rep = _run()
    assert rep["window"] == {"start": START.isoformat(), "end": END.isoformat(),
                             "settled_end": SETTLED_END.isoformat(), "days": 28}
    by = {}
    for cid, k, q in f.queries:
        by.setdefault(cid, []).append(k)
    assert by[MCC] == ["ROSTER", "G5"]                                   # once: the roster, then the country map
    assert by[A1] == by[A2] == ["SPEND", "CHAN", "INST", "G1P", "G1I", "ULV", "G2", "CA"]
    assert by[A3] == ["SPEND", "CA"]                                     # no spend: nothing to split by country
    assert MGR not in by
    qs = {k: q for cid, k, q in f.queries if cid == A1}
    rng = "segments.date BETWEEN '%s' AND '%s'" % (START, END)
    assert qs["G1P"] == ("SELECT campaign.id, campaign.app_campaign_setting.app_id, "
                         "geographic_view.country_criterion_id, geographic_view.location_type, "
                         "segments.date, metrics.cost_micros, metrics.impressions, metrics.clicks "
                         "FROM geographic_view WHERE %s "
                         "AND campaign.advertising_channel_type = 'MULTI_CHANNEL' "
                         "AND geographic_view.location_type = 'LOCATION_OF_PRESENCE' "
                         "AND metrics.cost_micros > 0" % rng)
    assert qs["G1I"] == qs["G1P"].replace("LOCATION_OF_PRESENCE", "AREA_OF_INTEREST")
    assert qs["G2"] == ("SELECT campaign.app_campaign_setting.app_id, geographic_view.country_criterion_id, "
                        "geographic_view.location_type, segments.date, segments.conversion_action_category, "
                        "metrics.conversions FROM geographic_view WHERE %s "
                        "AND campaign.advertising_channel_type = 'MULTI_CHANNEL' "
                        "AND geographic_view.location_type = 'LOCATION_OF_PRESENCE' "
                        "AND segments.conversion_action_category = 'DOWNLOAD'" % rng)
    assert rng in qs["SPEND"] and rng in qs["INST"] and rng in qs["ULV"]
    assert "FROM user_location_view" in qs["ULV"] and "user_location_view.country_criterion_id" in qs["ULV"]
    (g5,) = [q for cid, k, q in f.queries if k == "G5"]
    assert g5 == ("SELECT geo_target_constant.id, geo_target_constant.country_code "
                  "FROM geo_target_constant WHERE geo_target_constant.target_type = 'Country'")
    for k in ("category", "click_through_lookback_window_days", "include_in_conversions_metric"):
        assert "conversion_action." + k in qs["CA"]
    assert rep["counts"]["calls"] == 2 + 8 + 8 + 2 and rep["counts"]["errors"] == 0


# ── the probe: G1–G8 on a known truth ───────────────────────────────────────────────────────────

def test_complete_presence_passes_g1_and_every_measure_matches_the_truth(fake):
    fake()
    rep = _run()
    sm, v = rep["summary"], rep["verdict"]
    g1 = sm["g1"]
    assert (g1["accepted"], g1["of"], g1["refused"]) == (2, 2, {})
    assert g1["top"] == [BIG, MID] and g1["top_share"] == 0.9              # BIG 60% alone is < 80%
    assert g1["total_cost"] == 1000 * 10 ** 6 * 26 and g1["base_ccy"] == "INR"
    assert g1["cov_top"]["n"] == 2 * 26 and g1["cov_top"]["p10"] == 1.0 and g1["cov_top"]["unknown"] == 0
    assert g1["cov_fresh_top"]["n"] == 2 * 2                              # the 2 newest days, apart
    assert g1["cov_all"]["min"] == 0.8                                    # SMALL: 20% of it is not MULTI_CHANNEL
    assert g1["cov_top_vs_multi"]["p50"] == 1.0 and g1["non_multi_share"] == 0.02
    assert g1["per_store"][SMALL]["weighted"] == 0.8 and g1["per_store"][SMALL]["ga4"] is False
    assert g1["per_store"][BIG]["ga4"] is True and g1["per_store"][BIG]["share"] == 0.6
    assert g1["no_country_share"] == 0 and g1["orphan_days"] == 0 and g1["pass"] is True
    g2 = sm["g2"]
    assert g2["interest_top"]["p50"] == 0.95 and g2["both_top"]["weighted"] == 1.95 and g2["use"] == "presence"
    assert sm["g3"]["cov_top"]["p10"] == 1.0 and sm["g3"]["fallback_ok"] is True
    g4 = sm["g4"]
    assert g4["top"]["p50"] == 0.9 and g4["top"]["n"] == 2 * 26             # SMALL (5 installs a day) is not compared
    assert g4["all"]["n"] == 2 * 26 and g4["days_inst_no_dl"] == 0
    g5 = sm["g5"]
    assert (g5["accepted"], g5["via"], g5["countries"], g5["with_cost"], g5["unmapped_with_cost"]) == \
        (True, "mcc", 5, 3, 0) and g5["pass"] is True
    g6 = sm["g6"]
    assert g6["roster_tz"] is True and g6["by_zone"] == {"Asia/Calcutta": 2, "America/Los_Angeles": 1}
    assert g6["spend_share_by_zone"] == {"Asia/Calcutta": 0.7, "America/Los_Angeles": 0.3}
    g7 = sm["g7"]
    assert (g7["accepted"], g7["of"], g7["fallback"], g7["actions"], g7["download_included"]) == (3, 3, 0, 6, 3)
    assert g7["by_category"] == {"DOWNLOAD": 3, "PURCHASE": 3} and g7["by_status"] == {"ENABLED": 6, "REMOVED": 3}
    assert g7["by_lookback"] == {"30": 3, "90": 3} and g7["by_include"] == {"True": 3, "False": 3}
    g8 = sm["g8"]
    assert g8["rows_28"] == {"G1P": 3 * 3 * 28, "G2": 3 * 3 * 28} and g8["rows_400_est"]["G1P"] == 3600
    assert g8["cache"]["stores"] == 3 and g8["cache"]["cells_28"] == 3 * 3 * 28
    assert g8["cache"]["cells_400_est"] == 3600 and g8["cache"]["gz_bytes_28"] > 0
    assert g8["cache_ga4"]["stores"] == 2                                 # only the GA4 apps' packages are kept
    assert g8["calls_by_kind"]["G1P"] == 2 and g8["calls"] == rep["counts"]["calls"]
    assert g8["per_account"][A1]["rows_28"] == 2 * 2 * 3 * 28 and g8["per_account"][A3]["rows_28"] == 0
    assert g8["per_account_max"]["rows_28"] == 2 * 2 * 3 * 28
    assert v == {"g1_pass": True, "g5_pass": True, "use": "presence", "gads_geo_may_go_on": True,
                 "note": "GADS_GEO also needs the owner's yes (spec §8 Q5)"}
    x = rep["stores"][BIG][START.isoformat()]
    assert x == {"c": 600 * 10 ** 6, "cm": 600 * 10 ** 6, "p": 600 * 10 ** 6, "i": 570 * 10 ** 6,
                 "u": 600 * 10 ** 6, "inst": 100, "dl": 90.0}
    assert rep["iso"]["2840"] == "US" and rep["ccid_cost"]["2840"] == (300 + 150 + 40) * 10 ** 6 * 28


def test_a_short_presence_fails_g1_and_the_fallback_is_named(fake):
    fake(presence={BIG: 90})
    rep = _run()
    g1 = rep["summary"]["g1"]
    assert g1["cov_top"]["p10"] == 0.9 and g1["cov_top"]["p50"] == 0.95 and g1["pass"] is False
    assert rep["summary"]["g3"]["fallback_ok"] is True
    assert rep["verdict"]["use"] == "user_location" and rep["verdict"]["gads_geo_may_go_on"] is False


def test_an_unmapped_country_with_cost_fails_g5(fake):
    fake(extra_country="2999")
    rep = _run()
    g5 = rep["summary"]["g5"]
    assert g5["with_cost"] == 4 and g5["unmapped_with_cost"] == 1 and g5["unmapped_cost_share"] > 0
    assert g5["pass"] is False and rep["verdict"]["gads_geo_may_go_on"] is False
    assert rep["summary"]["g8"]["cache"]["cells_28"] == 3 * 4 * 28


def test_another_currency_is_converted_and_ratios_do_not_move(fake):
    fake(ccy={A2: "USD"})
    rep = _run(fx_fn=lambda c: {"INR": 0.012, "USD": 1.0}[c])
    assert rep["base_ccy"] == "INR" and rep["rates"] == {"INR": 1.0, "USD": pytest.approx(1 / 0.012)}
    g1 = rep["summary"]["g1"]
    assert g1["top"] == [MID]                                             # $300 a day outweighs ₹700
    assert g1["cov_top"]["p10"] == 1.0 and g1["pass"] is True


# ── the probe: refusals, stops, bugs ────────────────────────────────────────────────────────────

def test_a_refused_request_is_kept_as_its_code_and_the_rest_goes_on(fake):
    f = fake()
    f.refuse = {"G1I": {A2}, "CA": {A1}, "G5": {MCC}}
    rep = _run()
    g2 = rep["summary"]["g2"]
    assert (g2["accepted_interest"], g2["of"]) == (1, 2)
    assert g2["refused"] == {"queryError=PROHIBITED_SEGMENT_WITH_METRIC_IN_SELECT_OR_WHERE_CLAUSE": 1}
    assert g2["interest_top"]["unknown"] == 26                            # MID's interest: unknown, never 0
    assert rep["stores"][MID][START.isoformat()]["i"] is None
    err = rep["accounts"][A2]["calls"]["G1I"]["err"]
    assert err["http"] == 400 and A2 not in err["msg"] and "#" in err["msg"]
    assert rep["summary"]["g1"]["pass"] is True                           # presence is untouched
    g7 = rep["summary"]["g7"]
    assert (g7["accepted"], g7["fallback"]) == (3, 1)                     # A1: the spec's fields only
    assert rep["summary"]["g5"]["via"] == "account" and rep["summary"]["g5"]["pass"] is True
    assert rep["counts"]["errors"] == 3


def test_a_quota_error_stops_every_further_call(fake):
    f = fake()
    f.raise_for = {"G1P": ({A1}, "HTTP 429: quotaError=RESOURCE_EXHAUSTED — slow down")}
    rep = _run()
    kinds = [k for _, k, _ in f.queries]
    assert kinds == ["ROSTER", "G5", "SPEND", "CHAN", "INST", "G1P"]      # nothing after the quota error
    assert rep["stopped"] == "quota" and rep["counts"]["stopped"] == 1
    assert rep["accounts"][A2]["stopped"] == "quota" and rep["accounts"][A2]["calls"]["SPEND"]["n"] == 0
    assert rep["summary"]["g1"]["pass"] is False and rep["summary"]["g1"]["cov_top"]["unknown"] > 0
    json.loads(gp._dump(rep))


def test_the_time_budget_stops_new_calls_and_the_report_is_still_whole(fake):
    f = fake()
    now = [0.0]
    f.on_call = lambda k: now.__setitem__(0, now[0] + 100)
    rep = gp.run_probe(SETTINGS, TOK, now=NOW, workers=1, tick=0, budget=250, clock=lambda: now[0])
    assert [k for _, k, _ in f.queries] == ["ROSTER", "G5", "SPEND"]
    assert rep["stopped"] == "budget" and rep["accounts"][A1]["stopped"] == "budget"
    assert rep["counts"]["stopped"] == 1 and rep["summary"]["g5"]["pass"] is True
    assert gp.public_line(rep["counts"]).startswith("gads geo probe: accounts 1/3 (with spend 1), calls 3, errors 0, ")


def test_the_report_is_still_written_when_the_bookkeeping_has_a_bug(fake, monkeypatch):
    fake()
    monkeypatch.setattr(gp, "summary", lambda rep: 1 / 0)
    rep = _run()
    assert rep["summary"] == {"err": {"type": "ZeroDivisionError"}} and rep["verdict"] is None
    assert rep["stores"][BIG][START.isoformat()]["p"] == 600 * 10 ** 6    # the spent calls' results are all there
    monkeypatch.setattr(gp, "fold_account", lambda res: [][1])
    rep = _run()
    assert rep["accounts"][A1]["err"] == {"type": "IndexError"} and rep["stores"] == {}
    assert rep["accounts"][A1]["calls"]["G1P"]["rows"] == 2 * 3 * 28
    json.loads(gp._dump(rep))


def test_a_counts_only_heartbeat_at_least_every_minute(capsys):
    t = iter(range(0, 10000, 25))
    run = gp.Run(clock=lambda: float(next(t)))
    for _ in range(4):
        run.start_call()
    assert capsys.readouterr().out.splitlines() == ["gads geo progress: calls 2, 100s",
                                                    "gads geo progress: calls 4, 200s"]


# ── main + the public log ───────────────────────────────────────────────────────────────────────

ENV = {"GOOGLE_ADS_DEVELOPER_TOKEN": DEV, "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "111-222-3333",
       "GOOGLE_ADS_REFRESH_TOKEN": RT, "GOOGLE_CLIENT_ID": CID, "GOOGLE_CLIENT_SECRET": CSEC,
       "DATA_REPO": "owner/secret-repo", "DATA_REPO_TOKEN": "gh-SECRET"}


def test_main_writes_the_private_file_and_prints_counts_only(fake, monkeypatch, capsys):
    fake()
    put, seen = {}, {}
    monkeypatch.setattr(google_ads, "_access_token", lambda cid, csec, rt: seen.update(c=(cid, csec, rt)) or TOK)
    monkeypatch.setattr(gp, "_private_json", lambda path: {"fetch": {"a1": {"package": BIG}, "a2": {"package": MID},
                                                                     "a3": {}}} if path == gp.STATE_PATH else None)
    monkeypatch.setattr(gp, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    gp.main(dict(ENV), now=NOW)
    assert seen["c"] == (CID, CSEC, RT)                  # no GOOGLE_ADS_CLIENT_*: the AdMob client, as the Ads fetch
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert all(line.startswith("gads geo ") for line in lines)
    assert lines[:3] == ["gads geo probe: start", "gads geo probe: GA4 apps known 2",
                         "gads geo probe: 3 account(s) to probe"]
    res = [line for line in lines if line.startswith("gads geo probe: accounts ")]
    assert len(res) == 1 and lines[-1] == "gads geo probe: report written"
    assert re.fullmatch(r"gads geo probe: accounts 3/3 \(with spend 2\), calls 20, errors 0, geo cost accepted 2/2, "
                        r"area-of-interest accepted 2/2, user location accepted 2/2, geo installs accepted 2/2, "
                        r"conversion actions accepted 3/3, country map accepted 1, stores with spend 3, "
                        r"time zones 2, stopped 0, \d+s", res[0]), res[0]
    for s in SECRETS:
        assert s not in out
    rep = json.loads(put[gp.OUT_PATH])
    assert rep["verdict"]["gads_geo_may_go_on"] is True and rep["ga4_packages"] == [BIG, MID]
    assert set(rep["stores"]) == {BIG, MID, SMALL} and rep["summary"]["g8"]["cache_ga4"]["stores"] == 2


def test_main_without_the_ga4_state_still_probes(fake, monkeypatch, capsys):
    fake()
    put = {}
    monkeypatch.setattr(google_ads, "_access_token", lambda cid, csec, rt: TOK)

    def no_state(path):
        raise SystemExit("could not read")
    monkeypatch.setattr(gp, "_private_json", no_state)
    monkeypatch.setattr(gp, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    gp.main(dict(ENV, PROBE_MAX_ACCOUNTS="1"), now=NOW)
    rep = json.loads(put[gp.OUT_PATH])
    assert rep["ga4_packages"] is None and rep["summary"]["g8"]["cache_ga4"] is None
    assert set(rep["accounts"]) == {A1} and rep["summary"]["g1"]["per_store"][BIG]["ga4"] is None
    assert "gads geo probe: GA4 apps known 0" in capsys.readouterr().out


def test_main_without_secrets_or_sign_in_exits_before_any_call(fake, monkeypatch, capsys):
    f = fake()
    monkeypatch.setattr(gp, "write_private", lambda *a: pytest.fail("nothing to write"))
    with pytest.raises(SystemExit):
        gp.main({k: v for k, v in ENV.items() if k != "GOOGLE_ADS_DEVELOPER_TOKEN"}, now=NOW)

    def boom(cid, csec, rt):
        raise RuntimeError("unauthorized_client SECRETDETAIL " + RT)
    monkeypatch.setattr(google_ads, "_access_token", boom)
    with pytest.raises(SystemExit):
        gp.main(dict(ENV), now=NOW)
    assert not f.queries
    out = capsys.readouterr().out
    assert out.splitlines() == ["gads geo probe: start", "gads geo probe: Google Ads sign-in failed"]


def test_a_failed_roster_is_still_written(fake, monkeypatch):
    f = fake()
    f.refuse = {"ROSTER": {MCC}}
    rep = _run()
    assert rep["once"]["ROSTER"]["ok"] is False and rep["once"]["ROSTER"]["err"]["http"] == 400
    assert rep["accounts"] == {} and rep["counts"]["accounts"] == 0 and rep["verdict"]["g1_pass"] is False
    json.loads(gp._dump(rep))


def test_the_workflow_uses_the_builds_ads_secrets_and_keeps_them_off_the_public_log():
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "gads-geo-probe.yml"), encoding="utf-8") as fh:
        wf = yaml.safe_load(fh)
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as fh:
        ref = yaml.safe_load(fh)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and set(on["workflow_dispatch"]["inputs"]) == {"max_accounts"}
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["probe"]
    steps = job["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    assert not any("clone" in (st.get("run") or "") for st in steps)      # nothing private is cloned
    (st,) = [s for s in steps if s.get("name") == "Run"]
    assert st["run"].startswith("python -m admob_iq.fetch.gads_geo_probe 2>/tmp/")
    assert "details kept off the public log" in st["run"] and "${{" not in st["run"]
    assert st["env"]["PROBE_MAX_ACCOUNTS"] == "${{ github.event.inputs.max_accounts }}"   # env, never inlined in run
    (build,) = [s for s in ref["jobs"]["refresh"]["steps"] if s.get("name") == "Build dashboard + send alerts"]
    ads = {k: v for k, v in build["env"].items() if k.startswith("GOOGLE_")}
    assert set(ads) == {"GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_LOGIN_CUSTOMER_ID", "GOOGLE_ADS_REFRESH_TOKEN",
                        "GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"}
    for k, v in ads.items():
        assert st["env"][k] == v                                          # the very same secrets as the build's fetch
    assert set(st["env"]) == set(ads) | {"DATA_REPO", "DATA_REPO_TOKEN", "PROBE_MAX_ACCOUNTS", "PYTHONUNBUFFERED"}
    # setup (≤ 3) + the call budget + in-flight calls (≤ 1) + the private write (≤ 4) ≤ the timeout
    assert 3 + gp.BUDGET_SEC / 60 + 1 + 4 <= job["timeout-minutes"]
