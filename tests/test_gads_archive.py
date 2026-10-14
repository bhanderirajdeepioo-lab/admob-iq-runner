"""Google Ads ARCHIVE (GADS_ARCHIVE; admob_iq.fetch.gads_archive + gads_campaign_day + gads_hourly + gads_store) —
offline, against a synthetic MCC (tests/gads_fake.py: only selected fields come back, filtered fields must be
selected): the daily settings snapshot (versions only on change, the month base, state_on — also before a month's
first archived day), change_event (window, overlap, dedupe, LIMIT split, account-local days, events saved without
optional fields flagged), refused fields / kinds / accounts (a slimmer answer keeps the last values: no false change),
the call budget and quota stop, later builds of a day asking nothing when nothing is due, deterministic files written
only on change, the rows per campaign × day (captured from the spend fetch with its returned cache unchanged, ties
with the spend cache, merge_spend's store-day rule, the backfill to the first spend day, the gap a pause leaves, any
403 skipped and counted, another account's failure retried then a hole), spend by hour (90 days first, 30 daily,
ties, any 403 skipped and counted), the counts-only public lines and the build wiring (off = nothing at all; a failure
costs only its part). All data is synthetic."""

import copy
import gzip
import json
import os
import re
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq.config import settings
from admob_iq.fetch import gads_archive as ga
from admob_iq.fetch import gads_campaign_day as gcd
from admob_iq.fetch import gads_hourly as ghr
from admob_iq.fetch import gads_store
from admob_iq.fetch import google_ads
from tests.gads_fake import A1, A2, A3, A4, DEV, M, MCC, S1, S2, S3, SETTINGS, TOK, Clock, FakeAds

TODAY = date(2026, 9, 24)
T0 = 1_800_000_000
H = 3600
FX = {"INR": 0.012, "USD": 1.0}
KINDS = list(ga.KIND_NAMES)
LINES = {
    "archive": re.compile(r"^gads archive: accounts \d+ \(skipped \d+\), snapshots \d+, changes \d+, events \d+, "
                          r"refused \d+, waiting \d+, calls \d+, errors \d+ \((done|partial|off)\)$"),
    "campaign": re.compile(r"^gads campaign days: campaigns \d+, days \d+, backfill days \d+ \((done|filling|waiting|off)\)"
                           r", accounts \d+ \(skipped \d+\), no account \d+, ties cost \d+/\d+, installs \d+/\d+, "
                           r"value \d+/\d+, day1 \d+/\d+, calls \d+, errors \d+$"),
    "hours": re.compile(r"^gads hours: accounts \d+ \(skipped \d+\), campaigns \d+, days \d+ "
                        r"\((fresh|done|partial|waiting|off)\), no account \d+, ties \d+/\d+, calls \d+, errors \d+$"),
}


@pytest.fixture
def data(tmp_path):
    return str(tmp_path / "data")


def gz(path):
    with gzip.open(path, "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def live(monkeypatch, fake, start, end, archive=True, cached=None):
    """The ROAS step's spend fetch against the fake → (merged spend cache, the rows kept aside)."""
    monkeypatch.setattr(google_ads, "_search", fake.search)
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: TOK)
    monkeypatch.setattr(google_ads, "_fx_to_usd", FX.get)
    fresh = google_ads.fetch_app_spend(dict(SETTINGS, gads_archive=archive), str(start), str(end), mode="live")
    return google_ads.merge_spend(cached, fresh, str(start)), google_ads.take_rows()


def step(data, spend, fake, today=TODAY, t=T0, taken=None, **kw):
    return ga.archive_step(SETTINGS, data, spend, today, now=lambda: t, clock=kw.pop("clock", Clock()),
                           search=fake.search, token=TOK, taken=taken or {}, **kw)


def arch(data, month):
    p = os.path.join(data, "ads_archive", month + ".json.gz")
    return gz(p) if os.path.exists(p) else None


def only_archive(fake):
    """No spend cache: the archive part alone (hours / campaign backfill wait)."""
    return None


# ── 1. the archive ──────────────────────────────────────────────────────────────────────────────

def test_archive_first_day_every_kind_and_events(data):
    fake = FakeAds()
    fake.add_event(A1, "2026-08-30 10:00:00.000000")                 # 25 days back: an older month's file
    fake.add_event(A1, "2026-09-23 23:30:00.000000", fields="status", old=None, new=None)
    fake.add_event(A2, "2026-09-25 01:00:00.000000", cid="21")        # the account's day is already "tomorrow"
    fake.add_event(A1, "2026-08-01 09:00:00.000000")                 # older than Google's 30 days: never asked
    lines = step(data, None, fake)
    assert LINES["archive"].match(lines[0]), lines[0]
    assert lines[0].endswith("(done)")
    assert fake.n(acct=A3) == 0                                       # CANCELED in the roster: never asked
    assert fake.n("ROSTER") == 1
    for a in (A1, A2):
        assert sorted(k for c, k, _ in fake.calls if c == a) == sorted(KINDS + ["ev"])
    sep = arch(data, "2026-09")
    r1 = sep["acct"][A1]
    assert r1["days"]["2026-09-24"]["ok"] == sorted(KINDS)
    camp = r1["ver"]["camp/11"]
    assert camp[0][0] == "2026-09-24" and camp[0][1]["target_roas.target_roas"] == 1.25
    assert camp[0][1]["campaign_budget.amount_micros"] == str(60 * M)
    assert camp[0][1]["app_campaign_setting.bidding_strategy_goal_type"] == "OPTIMIZE_RETURN_ON_ADVERTISING_SPEND"
    assert camp[0][1]["primary_status_reasons"] == ["BIDDING_STRATEGY_LEARNING"]
    assert "id" not in camp[0][1] and "name" in camp[0][1]
    assert r1["ver"]["loc/11"] == [["2026-09-24", {"pos": ["2840"], "neg": ["2356"], "lang": ["1000"]}]]
    assert r1["ver"]["ads/11"][0][1]["approval"] == {"APPROVED": 2, "DISAPPROVED": 1}
    assert r1["ver"]["asset/11"][0][1]["type"] == {"HEADLINE": 2, "MARKETING_IMAGE": 1}
    assert r1["ver"]["conv/71"][0][1]["category"] == "DOWNLOAD"
    assert r1["ver"]["bill/81"][0][1]["status"] == "APPROVED"
    assert r1["ver"]["recsub/SET_TARGET_ROAS"][0][1]["status"] == "ENABLED"
    assert r1["ver"]["cust"][0][1]["time_zone"] == "Asia/Calcutta"
    assert set(r1["ver"]) == {"cust", "camp/11", "camp/12", "loc/11", "ads/11", "asset/11", "conv/71", "bill/81",
                              "recsub/SET_TARGET_ROAS"}
    ev = r1["days"]["2026-09-23"]["ev"]
    assert len(ev) == 1 and ev[0]["f"] == ["status"] and "old" not in ev[0] and ev[0]["c"] == "11"
    aug = arch(data, "2026-08")["acct"][A1]
    assert list(aug["days"]) == ["2026-08-30"] and "ver" in aug and not aug["ver"]
    e = aug["days"]["2026-08-30"]["ev"][0]
    assert e["old"] == {"targetRoas.targetRoas": 1.0} and e["new"] == {"targetRoas.targetRoas": 1.25}
    assert e["ct"] == "GOOGLE_ADS_WEB_CLIENT" and e["op"] == "UPDATE" and e["rt"] == "CAMPAIGN"
    assert sep["acct"][A2]["days"]["2026-09-25"]["ev"][0]["c"] == "21"
    q = next(q for c, k, q in fake.calls if k == "ev" and c == A1)
    assert ">= '2026-08-27 00:00:00'" in q and "<= '2026-09-25 23:59:59'" in q and q.endswith("LIMIT 10000")
    assert "user_email" not in q                                     # who made a change is never asked
    assert ga.state_on(data, A1, "2026-09-24")["camp/11"]["target_roas.target_roas"] == 1.25


def test_archive_next_days_only_changes_dedupe_overlap(data):
    fake = FakeAds()
    fake.add_event(A1, "2026-09-20 10:00:00.000000")
    step(data, None, fake)
    fake.camps[A1]["11"]["row"]["campaign"]["targetRoas"]["targetRoas"] = 1.4      # the owner moves the target
    fake.res[A1]["billing_setup"] = []                                              # the billing setup goes
    fake.add_event(A1, "2026-09-24 18:00:00.000000", old=1.25, new=1.4)
    fake.calls.clear()
    lines = step(data, None, fake, today=TODAY + timedelta(days=1), t=T0 + 24 * H)
    assert re.search(r"changes 2, events 1,", lines[0]), lines[0]                  # target + billing gone; 1 new event
    q = next(q for c, k, q in fake.calls if k == "ev" and c == A1)
    assert ">= '2026-09-22 00:00:00'" in q                                         # since the last day asked − 2
    r1 = arch(data, "2026-09")["acct"][A1]
    assert [v[0] for v in r1["ver"]["camp/11"]] == ["2026-09-24", "2026-09-25"]
    assert r1["ver"]["bill/81"][-1] == ["2026-09-25", None]
    assert len(r1["ver"]["loc/11"]) == 1                                           # unchanged: no new version
    assert len(r1["days"]["2026-09-20"]["ev"]) == 1                                 # asked twice, kept once
    assert ga.state_on(data, A1, "2026-09-24")["camp/11"]["target_roas.target_roas"] == 1.25
    assert ga.state_on(data, A1, "2026-09-25")["camp/11"]["target_roas.target_roas"] == 1.4
    assert "bill/81" not in ga.state_on(data, A1, "2026-09-25")
    assert [e["t"][:10] for _, e in ga.events(data, "2026-09-01", "2026-09-30")] == ["2026-09-20", "2026-09-24"]


def test_archive_month_base_repeats_carried_state(data):
    fake = FakeAds()
    step(data, None, fake, today=date(2026, 9, 30))
    fake.camps[A2]["21"]["row"]["campaignBudget"]["amountMicros"] = str(99 * M)
    step(data, None, fake, today=date(2026, 10, 1), t=T0 + 24 * H)
    octo = arch(data, "2026-10")["acct"]
    assert octo[A1]["ver"]["camp/11"] == [["2026-10-01", arch(data, "2026-09")["acct"][A1]["ver"]["camp/11"][0][1]]]
    assert octo[A2]["ver"]["camp/21"][0][1]["campaign_budget.amount_micros"] == str(99 * M)
    assert len(octo[A2]["ver"]["camp/21"]) == 1                                    # the change sits in the base day
    os.remove(os.path.join(data, "ads_archive", "2026-09.json.gz"))                 # a month file is complete alone
    assert ga.state_on(data, A1, "2026-10-01") == {k: v[0][1] for k, v in octo[A1]["ver"].items()}


def test_state_on_a_day_before_the_months_first_archived_day(data):
    fake = FakeAds()
    step(data, None, fake, today=date(2026, 9, 30))
    step(data, None, fake, today=date(2026, 10, 2), t=T0 + 48 * H)                 # no build answered on 1 Oct
    s30 = ga.state_on(data, A1, "2026-09-30")
    assert len(s30) > 5 and ga.state_on(data, A1, "2026-10-01") == s30 == ga.state_on(data, A1, "2026-10-02")
    assert ga.state_on(data, A1, "2026-09-29") == {}


def test_archive_later_builds_of_the_day_ask_nothing_when_nothing_is_due(data):
    fake = FakeAds()
    first = step(data, None, fake)[0]
    assert first.startswith("gads archive: accounts 2 (skipped 1), snapshots 2,") and fake.n("ROSTER") == 1
    for i in (1, 2, 3):
        fake.calls.clear()
        line = step(data, None, fake, t=T0 + i * H)[0]
        assert fake.calls == [], fake.calls                                          # no token, no roster request
        assert line == ("gads archive: accounts 2 (skipped 1), snapshots 0, changes 0, events 0, refused 0, "
                        "waiting 0, calls 0, errors 0 (done)"), line
    fake.calls.clear()
    step(data, None, fake, today=TODAY + timedelta(days=1), t=T0 + 24 * H)
    assert fake.n("ROSTER") == 1 and fake.n("camp") == 2                            # a new day: asked again


def test_archive_once_a_day_failed_kind_retried_then_weekly(data):
    fake = FakeAds()
    fake.fail = lambda acct, k, q: "HTTP 403: authorizationError=USER_PERMISSION_DENIED — SECRET" if k == "bill" else None
    step(data, None, fake)
    st = gads_store.read_gz(os.path.join(data, "ads_archive", "state.json.gz"))
    assert st["streak"][A1]["bill"] == [1, "2026-09-24", "authorizationError=USER_PERMISSION_DENIED"]
    assert arch(data, "2026-09")["acct"][A1]["days"]["2026-09-24"]["err"] == {
        "bill": "authorizationError=USER_PERMISSION_DENIED"}
    for i in (1, 2):                                                                # the same day: only bill again
        fake.calls.clear()
        lines = step(data, None, fake, t=T0 + i * H)
        assert sorted(k for _, k, _ in fake.calls) == ["ROSTER", "bill", "bill"], fake.calls
    fake.calls.clear()
    lines = step(data, None, fake, t=T0 + 3 * H)                                    # TRIES reached today: nothing
    assert fake.calls == [] and lines[0].endswith("calls 0, errors 0 (partial)")    # due, not even the roster
    for k in (1, 2):                                                                # refused 3 days in a row …
        step(data, None, fake, today=TODAY + timedelta(days=k), t=T0 + k * 24 * H)
    fake.calls.clear()
    lines = step(data, None, fake, today=TODAY + timedelta(days=3), t=T0 + 72 * H)
    assert fake.n("bill") == 0 and "waiting 2" in lines[0] and lines[0].endswith("(done)")   # … then weekly
    fake.calls.clear()
    step(data, None, fake, today=TODAY + timedelta(days=9), t=T0 + 9 * 24 * H)
    assert fake.n("bill") == 2


def test_archive_refused_field_dropped_remembered_and_retried_monthly(data):
    fake = FakeAds()
    fake.unknown = {"campaign.start_date", "campaign.end_date"}
    step(data, None, fake)
    assert 4 <= fake.n("camp") <= 6                   # full, without start_date, without end_date (an account asking
                                                      # after another one learnt it skips those) …
    camp = arch(data, "2026-09")["acct"][A1]["ver"]["camp/11"][0][1]
    assert "start_date" not in camp and "target_roas.target_roas" in camp
    day = arch(data, "2026-09")["acct"][A1]["days"]["2026-09-24"]
    assert set(day["drop"]["camp"]) >= {"campaign.start_date", "campaign.end_date"}
    st = gads_store.read_gz(os.path.join(data, "ads_archive", "state.json.gz"))
    assert st["drop"]["camp"] == {"f": ["campaign.end_date", "campaign.start_date"], "at": "2026-09-24"}
    fake.calls.clear()
    step(data, None, fake, today=TODAY + timedelta(days=1), t=T0 + 24 * H)
    assert fake.n("camp") == 2                        # … then remembered: one request each
    fake.unknown = set()
    fake.calls.clear()
    step(data, None, fake, today=TODAY + timedelta(days=31), t=T0 + 31 * 24 * H)
    q = [q for _, k, q in fake.calls if k == "camp"]
    assert len(q) == 2 and all("campaign.start_date," in x for x in q)             # asked for again after 30 days


def test_archive_core_only_when_the_refusal_names_no_field_and_other_400_raise(data):
    fake = FakeAds()
    fake.fail = lambda acct, k, q: ("HTTP 400: queryError=PROHIBITED_FIELD_COMBINATION_IN_SELECT_CLAUSE — SECRET"
                                    if k == "asset" and "performance_label" in q else None)
    step(data, None, fake)
    asset = arch(data, "2026-09")["acct"][A1]["ver"]["asset/11"][0][1]
    assert asset == {"n": 3}                                                        # core only: counted, no split
    fake2 = FakeAds()
    fake2.fail = lambda acct, k, q: "HTTP 400: requestError=INVALID_INPUT — SECRET" if k == "conv" else None
    step(data + "2", None, fake2)
    assert fake2.n("conv") == 2                                                     # not a field error: once each
    assert arch(data + "2", "2026-09")["acct"][A1]["days"]["2026-09-24"]["err"] == {"conv": "requestError=INVALID_INPUT"}


def test_archive_many_refused_fields_core_only_then_learnt_build_by_build(data):
    fake = FakeAds()
    del fake.accounts[A2]                                                          # one account: a fixed order
    bad = ["campaign.name", "campaign.serving_status", "campaign.start_date", "campaign.end_date_time"]
    fake.unknown = set(bad)
    step(data, None, fake)
    assert fake.n("camp") == 4                                                     # 3 named one by one, then core
    day = arch(data, "2026-09")["acct"][A1]["days"]["2026-09-24"]
    assert "camp" in day["ok"] and "err" not in day                                # the kind still answered …
    assert set(arch(data, "2026-09")["acct"][A1]["ver"]["camp/11"][0][1]) == {"status", "app_campaign_setting.app_id"}
    st = gads_store.read_gz(os.path.join(data, "ads_archive", "state.json.gz"))
    assert st["drop"]["camp"]["f"] == sorted(bad[:3])                              # … only the named ones remembered
    step(data, None, fake, today=TODAY + timedelta(days=1), t=T0 + 24 * H)
    camp = ga.state_on(data, A1, "2026-09-25")["camp/11"]
    assert camp["target_roas.target_roas"] == 1.25 and "name" not in camp           # the next build: the rest again
    st = gads_store.read_gz(os.path.join(data, "ads_archive", "state.json.gz"))
    assert st["drop"]["camp"] == {"f": sorted(bad), "at": "2026-09-25"}             # the 4th learnt, the 3 kept
    fake.calls.clear()
    step(data, None, fake, today=TODAY + timedelta(days=2), t=T0 + 48 * H)
    assert fake.n("camp") == 1                                                     # one request from now on


def test_archive_a_slimmer_answer_keeps_the_last_values_and_is_no_change(data):
    fake = FakeAds()
    step(data, None, fake)
    day0 = ga.state_on(data, A1, "2026-09-24")
    assert day0["camp/11"]["serving_status"] == "SERVING"
    fake.unknown = {"campaign.start_date", "campaign.end_date", "campaign.serving_status"}   # 3 refusals: core only
    lines = step(data, None, fake, today=TODAY + timedelta(days=1), t=T0 + 24 * H)
    assert "changes 0" in lines[0], lines[0]                                        # no fake version …
    assert ga.state_on(data, A1, "2026-09-25") == day0                              # … the last answered values
    assert len(arch(data, "2026-09")["acct"][A1]["ver"]["camp/11"]) == 1
    day = arch(data, "2026-09")["acct"][A1]["days"]["2026-09-25"]
    assert set(day["drop"]["camp"]) >= set(fake.unknown)                            # what was not asked is listed
    fake.camps[A1]["11"]["row"]["campaign"]["targetRoas"]["targetRoas"] = 1.5      # a real change, fewer fields
    lines = step(data, None, fake, today=TODAY + timedelta(days=2), t=T0 + 48 * H)
    c = ga.state_on(data, A1, "2026-09-26")["camp/11"]
    assert "changes 1" in lines[0] and c["target_roas.target_roas"] == 1.5, lines[0]
    assert c["serving_status"] == "SERVING" and c["start_date"] == "2025-01-01" and "end_date" not in c


def test_archive_no_campaign_skips_campaign_kinds(data):
    fake = FakeAds()
    fake.camps[A2] = {}
    step(data, None, fake)
    assert sorted(k for c, k, _ in fake.calls if c == A2) == sorted(["cust", "camp", "conv", "bill", "abud", "recsub",
                                                                      "ev"])
    day = arch(data, "2026-09")["acct"][A2]["days"]["2026-09-24"]
    assert day["ok"] == sorted(KINDS) and "drop" not in day


def test_archive_change_event_limit_split_and_full_day_marked(data, monkeypatch):
    monkeypatch.setattr(ga, "EV_LIMIT", 4)
    fake = FakeAds()
    for i in range(9):
        fake.add_event(A1, "2026-09-%02d 1%d:00:00.000000" % (5 + i % 3, i), fields="name" if i % 2 else "status")
    for i in range(5):
        fake.add_event(A1, "2026-09-20 0%d:00:00.000000" % i)
    step(data, None, fake)
    evs = [e for a, e in ga.events(data) if a == A1]
    assert len(evs) == 9 + 4                                                         # one full day keeps its 4
    assert arch(data, "2026-09")["acct"][A1]["days"]["2026-09-20"]["trunc"] is True
    assert fake.n("ev", A1) > 1


def test_archive_events_saved_without_old_values_are_flagged(data):
    fake = FakeAds()
    fake.add_event(A1, "2026-09-20 10:00:00.000000")
    fake.unknown = {"change_event.old_resource"}
    step(data, None, fake)
    d20 = arch(data, "2026-09")["acct"][A1]["days"]["2026-09-20"]
    assert "old" not in d20["ev"][0] and d20["ev"][0]["new"] and d20["drop"] == {"ev": ["change_event.old_resource"]}
    fake2 = FakeAds()
    fake2.add_event(A1, "2026-09-24 10:00:00.000000")
    step(data + "2", None, fake2)
    fake2.unknown = {"change_event.old_resource"}
    step(data + "2", None, fake2, today=TODAY + timedelta(days=1), t=T0 + 24 * H)  # asked again (the overlap) …
    d24 = arch(data + "2", "2026-09")["acct"][A1]["days"]["2026-09-24"]
    assert d24["ev"][0]["old"] and "drop" not in d24                               # … the full event is kept


def test_archive_account_not_enabled_once_then_skipped(data):
    fake = FakeAds()
    fake.accounts[A3]["status"] = None                                               # the roster does not say
    fake.gone = {A3}
    lines = step(data, None, fake)
    assert fake.n(acct=A3) == 1 and "skipped 1" in lines[0]
    fake.calls.clear()
    step(data, None, fake, today=TODAY + timedelta(days=1), t=T0 + 24 * H)
    assert fake.n(acct=A3) == 0
    fake.calls.clear()
    step(data, None, fake, today=TODAY + timedelta(days=8), t=T0 + 8 * 24 * H)
    assert fake.n(acct=A3) == 1


def test_archive_budget_and_quota_stop_then_continue(data):
    fake = FakeAds()
    lines = step(data, None, fake, max_calls=8)
    assert fake.n() == 8 and lines[0].endswith("(partial)")
    step(data, None, fake, t=T0 + H)
    st = gads_store.read_gz(os.path.join(data, "ads_archive", "state.json.gz"))
    assert all(set(KINDS) <= set(st["acct"][a]["ok"]) and st["acct"][a]["ev"] == "2026-09-24" for a in (A1, A2))
    fake2 = FakeAds()
    fake2.fail = lambda acct, k, q: "HTTP 429: quotaError=RESOURCE_EXHAUSTED — SECRET" if k == "loc" else None
    lines = step(data + "q", None, fake2)
    n = fake2.n()
    assert lines[0].endswith("(partial)") and n <= 1 + 2 * 3 + 2                      # no request after the quota error
    assert all(k != "ev" for _, k, _ in fake2.calls)


def test_archive_files_deterministic_and_written_only_on_change(tmp_path):
    out = []
    for name in ("a", "b"):
        fake = FakeAds()
        fake.add_event(A1, "2026-09-20 10:00:00.000000")
        d = str(tmp_path / name)
        step(d, None, fake)
        out.append({f: open(os.path.join(d, "ads_archive", f), "rb").read()
                    for f in sorted(os.listdir(os.path.join(d, "ads_archive")))})
    assert out[0] == out[1] and set(out[0]) == {"2026-09.json.gz", "state.json.gz"}
    d = str(tmp_path / "a")
    p = os.path.join(d, "ads_archive", "2026-09.json.gz")
    os.utime(p, (1, 1))
    step(d, None, FakeAds(), t=T0 + H)                                               # nothing due: nothing written
    assert os.path.getmtime(p) == 1


def test_event_of_caps_values_and_fields():
    big = {"data": "x" * 5000}
    row = {"changeEvent": {"changeDateTime": "2026-09-01 00:00:00", "changeResourceType": "ASSET",
                           "changeResourceName": "customers/1/assets/7", "clientType": "GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION",
                           "resourceChangeOperation": "CREATE", "changedFields": "imageAsset,name",
                           "newResource": {"asset": {"imageAsset": big, "name": "n"}}}}
    ev = ga.event_of(row)
    assert ev["new"]["name"] == "n" and set(ev["new"]["imageAsset"]) == {"_len", "_sha1"}
    assert ev["ct"] == "GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION" and "old" not in ev and "c" not in ev
    many = dict(row["changeEvent"], changedFields=",".join("f%d" % i for i in range(50)))
    ev = ga.event_of({"changeEvent": many})
    assert len(ev["f"]) == ga.CAP_FIELDS and ev["_more"] == 10


# ── 2. rows per campaign × day ───────────────────────────────────────────────────────────────────

def test_fetch_app_spend_returns_the_same_cache_with_or_without_the_archive(monkeypatch):
    fake = FakeAds()
    on, taken = live(monkeypatch, fake, "2026-06-26", "2026-09-24", archive=True)
    off, none = live(monkeypatch, fake, "2026-06-26", "2026-09-24", archive=False)
    assert json.dumps(on, sort_keys=True) == json.dumps(off, sort_keys=True)
    assert none == {} and google_ads.take_rows() == {}
    assert taken["start"] == "2026-06-26" and {r["campaign_id"] for r in taken["inst"]} == {"11", "12", "21"}
    assert all(r["account"] in (A1, A2) for k in ("spend", "inst", "d1") for r in taken[k])
    q = [q for _, k, q in fake.calls if k in ("INST", "D1")]
    assert q and all(x.startswith("SELECT campaign.id, campaign.app_campaign_setting.app_id, ") for x in q)


def test_campaign_capture_ties_the_spend_cache_exactly(data, monkeypatch):
    fake = FakeAds()
    spend, taken = live(monkeypatch, fake, "2026-06-26", "2026-09-24")
    lines = step(data, spend, fake, taken=taken, max_calls=0)
    cl = next(x for x in lines if x.startswith("gads campaign days:"))
    assert LINES["campaign"].match(cl), cl
    m = re.search(r"ties cost (\d+)/(\d+), installs (\d+)/(\d+), value (\d+)/(\d+), day1 (\d+)/(\d+)", cl)
    nums = list(map(int, m.groups()))
    assert nums[1] > 100 and all(nums[i] == nums[i + 1] for i in range(0, 8, 2)), cl
    got = gcd.load(data)
    for sid in (S1, S2):
        for dd, v in spend["daily"][sid].items():
            assert sum(got["cost"][c].get(dd, 0) for c, x in got["camp"].items() if x["s"] == sid) == v
    assert got["camp"]["12"] == {"s": S1, "a": A1} and got["ccy"] == {A1: "INR", A2: "INR"}
    assert sorted(os.listdir(os.path.join(data, "ads_campaign_day"))) == [
        "2026-06.json.gz", "2026-07.json.gz", "2026-08.json.gz", "2026-09.json.gz", "state.json.gz"]


def test_campaign_overlay_is_merge_spends_store_day_rule(data, monkeypatch):
    fake = FakeAds()
    spend, taken = live(monkeypatch, fake, "2026-08-01", "2026-09-24")
    step(data, spend, fake, taken=taken, max_calls=0)
    c12 = fake.camps[A1].pop("12")                                # its days of the new window are gone at Google
    spend2, taken2 = live(monkeypatch, fake, "2026-09-01", "2026-09-25", cached=spend)
    fake.camps[A1]["12"] = c12
    step(data, spend2, fake, taken=taken2, max_calls=0)
    got = gcd.load(data)
    fresh_days = {r["date"] for r in taken2["spend"] if r["store_id"] == S1}
    kept = [dd for dd in got["cost"]["12"] if dd >= "2026-09-01"]
    assert kept and not set(kept) & fresh_days                     # a store-day in the fresh rows is replaced whole;
    for dd in kept:                                                # one that is not keeps its cells — as the cache
        assert spend2["daily"][S1][dd] == spend["daily"][S1][dd] == got["cost"]["12"][dd] + got["cost"]["11"].get(dd, 0)
    assert [dd for dd in got["cost"]["12"] if dd < "2026-09-01"]                        # older days kept
    t = gcd.ties(gcd.months(data), spend2, "2026-08-01", "2026-09-25")
    assert all(ok == n for ok, n in t.values())


def test_campaign_backfill_to_the_first_spend_day(data, monkeypatch):
    fake = FakeAds(lo="2025-03-10")
    spend, _ = live(monkeypatch, fake, "2025-01-01", "2026-09-24", archive=False)    # the cache's settled history
    spend, taken = live(monkeypatch, fake, "2026-06-26", "2026-09-24", cached=spend)
    fake.calls.clear()
    lines = step(data, spend, fake, taken=taken)
    cl = next(x for x in lines if x.startswith("gads campaign days:"))
    assert "backfill days 360 (filling)" in cl, cl
    rng = sorted({re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", q).groups() for _, k, q in fake.calls if k == "SPEND"})
    assert rng == [("2025-07-01", "2025-12-27"), ("2025-12-28", "2026-06-25")]               # 180 days, newest first
    assert fake.n(acct=A3) == 0 and "skipped 0" in cl                                 # A3's stores never had spend
    step(data, spend, fake, taken={}, t=T0 + H)
    st = gads_store.read_gz(os.path.join(data, "ads_campaign_day", "state.json.gz"))
    assert st["done"] and st["bfrom"] == "2025-03-10" and st["holes"] == []
    got = gcd.load(data)
    assert min(dd for c in got["cost"].values() for dd in c) == "2025-03-10"
    t = gcd.ties(gcd.months(data), spend, "2025-03-10", "2026-09-24")
    assert t["cost"][0] == t["cost"][1] > 500
    fake.calls.clear()
    lines = step(data, spend, fake, taken={}, t=T0 + 2 * H)
    assert fake.n("SPEND") == 0 and "(done)" in next(x for x in lines if x.startswith("gads campaign days:"))


def test_campaign_backfill_holes_when_installs_fail_and_stop_on_cost_failure(data, monkeypatch):
    fake = FakeAds(lo="2026-01-01")
    spend, _ = live(monkeypatch, fake, "2026-01-01", "2026-09-24", archive=False)
    spend, taken = live(monkeypatch, fake, "2026-06-26", "2026-09-24", cached=spend)
    fake.fail = lambda acct, k, q: "HTTP 500: SECRET" if k == "INST" and acct == A2 and "2026-06-25" in q else None
    step(data, spend, fake, taken=taken)
    st = gads_store.read_gz(os.path.join(data, "ads_campaign_day", "state.json.gz"))
    assert st["holes"] == [["cv", A2, "2026-01-01", "2026-06-25"], ["inst", A2, "2026-01-01", "2026-06-25"]]
    assert st["done"]                                                                  # the chunk still went in
    fake2 = FakeAds(lo="2026-01-01")
    spend, _ = live(monkeypatch, fake2, "2026-01-01", "2026-09-24", archive=False)
    spend, taken = live(monkeypatch, fake2, "2026-06-26", "2026-09-24", cached=spend)
    fake2.fail = lambda acct, k, q: "HTTP 500: SECRET" if k == "SPEND" and acct == A1 and "2026-06-25" in q else None
    lines = step(data + "2", spend, fake2, taken=taken)
    st = gads_store.read_gz(os.path.join(data + "2", "ads_campaign_day", "state.json.gz"))
    assert st["bfrom"] == "2026-06-26" and st["bfails"] == 1                          # nothing written, asked again
    assert "backfill days 0 (filling)" in next(x for x in lines if x.startswith("gads campaign days:"))


def test_campaign_backfill_asks_every_live_account_and_marks_owners_that_cannot_answer(data, monkeypatch):
    fake = FakeAds(lo="2026-01-01")
    fake.accounts[A4] = {"ccy": "INR", "tz": "Asia/Calcutta", "status": "ENABLED"}
    fake.camps[A4] = {"41": dict(fake.camp("41", S1, 7), hi="2026-05-31")}       # an older owner of the store
    fake.res[A4] = fake.extras("41")
    spend, _ = live(monkeypatch, fake, "2026-01-01", "2026-09-24", archive=False)
    spend, taken = live(monkeypatch, fake, "2026-06-26", "2026-09-24", cached=spend)
    assert {c["account"] for c in spend["campaigns"][S1]} == {A1}                 # the cache's map lost that owner
    spend["daily"][S3] = {"2026-03-0%d" % i: 5 * M for i in (1, 2, 3)}            # a store of a CANCELED account
    spend["campaigns"][S3] = [{"id": "31", "name": "x", "status": "PAUSED", "cost_micros": 15 * M, "account": A3,
                               "account_name": ""}]
    fake.calls.clear()
    lines = step(data, spend, fake, taken=taken)
    cl = next(x for x in lines if x.startswith("gads campaign days:"))
    assert "accounts 4 (skipped 1)" in cl and fake.n(acct=A3) == 0, cl
    st = gads_store.read_gz(os.path.join(data, "ads_campaign_day", "state.json.gz"))
    assert st["done"] and st["holes"] == [["all", A3, "2026-01-01", "2026-06-25"]]
    got = gcd.load(data)
    assert got["camp"]["41"] == {"s": S1, "a": A4} and max(got["cost"]["41"]) <= "2026-05-31"
    for dd, v in spend["daily"][S1].items():                                       # the store's days complete
        assert sum(got["cost"][c].get(dd, 0) for c, x in got["camp"].items() if x["s"] == S1) == v, dd


def test_campaign_backfill_any_403_is_skipped_and_counted_never_blocks(data, monkeypatch):
    fake = FakeAds(lo="2026-01-01")
    fake.accounts[A4] = {"ccy": "INR", "tz": "Asia/Calcutta", "status": "ENABLED"}  # no app campaign at all
    fake.camps[A4], fake.res[A4] = {}, {}
    spend, _ = live(monkeypatch, fake, "2026-01-01", "2026-09-24", archive=False)
    spend, taken = live(monkeypatch, fake, "2026-06-26", "2026-09-24", cached=spend)
    denied = "HTTP 403: authorizationError=USER_PERMISSION_DENIED — SECRET"
    fake.fail = lambda acct, k, q: denied if k in ("SPEND", "INST", "D1") and (
        acct == A4 or (acct == A2 and "2026-06-25" in q)) else None                 # an owner too, in the backfill
    fake.calls.clear()
    lines = step(data, spend, fake, taken=taken)
    cl = next(x for x in lines if x.startswith("gads campaign days:"))
    assert "backfill days 176 (done)" in cl and "(skipped 2)" in cl and cl.endswith("errors 2"), cl
    assert fake.n("SPEND", A4) == 1 and fake.n("INST", A4) == 0
    st = gads_store.read_gz(os.path.join(data, "ads_campaign_day", "state.json.gz"))
    assert st["done"] and st["bfails"] == 0 and st["skip"] == {A2: "2026-10-01", A4: "2026-10-01"}
    assert st["holes"] == [["all", A2, "2026-01-01", "2026-06-25"]]                  # the owner's days stay out
    got = gcd.load(data)
    assert min(dd for c, x in got["camp"].items() if x["s"] == S1 for dd in got["cost"][c]) == "2026-01-01"
    assert min(dd for c, x in got["camp"].items() if x["s"] == S2 for dd in got["cost"][c]) == "2026-06-26"


def test_campaign_backfill_another_accounts_failure_retried_then_a_hole(data, monkeypatch):
    fake = FakeAds(lo="2026-01-01")
    fake.accounts[A4] = {"ccy": "INR", "tz": "Asia/Calcutta", "status": "ENABLED"}
    fake.camps[A4], fake.res[A4] = {}, {}
    spend, _ = live(monkeypatch, fake, "2026-01-01", "2026-09-24", archive=False)
    spend, taken = live(monkeypatch, fake, "2026-06-26", "2026-09-24", cached=spend)
    fake.fail = lambda acct, k, q: "HTTP 500: SECRET" if acct == A4 and k == "SPEND" else None
    for i in range(3):                                                                # a passing error? asked again
        lines = step(data, spend, fake, taken=taken if i == 0 else {}, t=T0 + i * H)
        cl = next(x for x in lines if x.startswith("gads campaign days:"))
        assert "backfill days 0 (filling)" in cl and cl.endswith("errors 1"), cl
    fake.calls.clear()
    step(data, spend, fake, taken={}, t=T0 + 3 * H)
    assert fake.n("SPEND") == 0                                                       # 3 failed chunks: waits a day
    step(data, spend, fake, taken={}, today=TODAY + timedelta(days=1), t=T0 + 24 * H)
    st = gads_store.read_gz(os.path.join(data, "ads_campaign_day", "state.json.gz"))
    assert st["done"] and st["bfails"] == 0 and st["holes"] == [["all", A4, "2026-01-01", "2026-06-25"]]
    got = gcd.load(data)
    for sid in (S1, S2):
        for dd, v in spend["daily"][sid].items():
            assert sum(got["cost"][c].get(dd, 0) for c, x in got["camp"].items() if x["s"] == sid) == v, dd


def test_campaign_backfill_fills_the_gap_a_pause_left(data, monkeypatch):
    fake = FakeAds(lo="2025-06-01")
    t0, t1 = date(2026, 6, 24), date(2026, 10, 24)
    spend, _ = live(monkeypatch, fake, "2025-06-01", t0, archive=False)
    spend, taken = live(monkeypatch, fake, "2026-03-26", t0, cached=spend)
    step(data, spend, fake, today=t0, taken=taken)
    st = gads_store.read_gz(os.path.join(data, "ads_campaign_day", "state.json.gz"))
    assert st["done"] and st["cov"] == [["2025-06-01", "2026-06-24"]]
    spend, _ = live(monkeypatch, fake, "2026-06-01", t1, archive=False, cached=spend)  # GADS_ARCHIVE off 4 months …
    spend, taken = live(monkeypatch, fake, "2026-07-26", t1, cached=spend)            # … then on again
    lines = step(data, spend, fake, today=t1, t=T0 + 200 * H, taken=taken)
    cl = next(x for x in lines if x.startswith("gads campaign days:"))
    assert "backfill days 31 (done)" in cl, cl                                        # the gap, and only the gap
    st = gads_store.read_gz(os.path.join(data, "ads_campaign_day", "state.json.gz"))
    assert st["done"] and st["cov"] == [["2025-06-01", "2026-10-24"]] and st["bfrom"] == "2025-06-01"
    got = gcd.load(data)
    for sid in (S1, S2):
        for dd, v in spend["daily"][sid].items():
            assert sum(got["cost"][c].get(dd, 0) for c, x in got["camp"].items() if x["s"] == sid) == v, dd


def test_covered_ranges_and_the_next_backfill_chunk():
    cov = gads_store.cov_add([], "2026-03-01", "2026-03-31")
    cov = gads_store.cov_add(cov, "2026-04-01", "2026-04-10")                        # adjacent: joined
    assert cov == [["2026-03-01", "2026-04-10"]]
    assert gads_store.cov_next(cov, "2026-01-01", 30) == (date(2026, 1, 30), date(2026, 2, 28))
    assert gads_store.cov_next(cov, "2026-03-01", 30) is None and gads_store.cov_next([], "2026-01-01", 30) is None
    cov = gads_store.cov_add(cov, "2026-06-01", "2026-06-30")                        # above a gap: the gap first
    assert gads_store.cov_next(cov, "2026-01-01", 30) == (date(2026, 5, 2), date(2026, 5, 31))
    assert gads_store.cov_next(cov, "2026-01-01", 90) == (date(2026, 4, 11), date(2026, 5, 31))
    assert gads_store.cov_of({"bfrom": "2026-03-01", "first": "2026-03-01", "till": "2026-04-10"}) == \
        [["2026-03-01", "2026-04-10"]]


# ── 4. spend by hour ─────────────────────────────────────────────────────────────────────────────

def test_hours_first_90_days_then_30_daily_and_ties(data, monkeypatch):
    fake = FakeAds()
    spend, _ = live(monkeypatch, fake, "2026-06-01", "2026-09-24", archive=False)
    fake.calls.clear()
    lines = step(data, spend, fake)
    hl = next(x for x in lines if x.startswith("gads hours:"))
    assert LINES["hours"].match(hl) and "days 90 (done)" in hl, hl
    assert [re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", q).groups() for _, k, q in fake.calls if k == "HOURLY"] \
        == [("2026-06-26", "2026-09-23")] * 2
    m = re.search(r"ties (\d+)/(\d+)", hl)
    assert int(m.group(1)) == int(m.group(2)) > 150
    h = ghr.load(data)
    assert h["tz"] == {A1: "Asia/Calcutta", A2: "Asia/Calcutta"} and h["camp"]["11"] == S1
    for dd, hs in h["h"][A1]["11"].items():                                          # Σ hours = the day's cost
        assert sum(hs) == sum(int(r["metrics"]["costMicros"]) for r in fake.metric_rows(A1, "SPEND", dd, dd)
                              if r["campaign"]["id"] == "11")
    fake.calls.clear()
    lines = step(data, spend, fake, t=T0 + 19 * H)
    assert fake.n("HOURLY") == 0 and "(fresh)" in next(x for x in lines if x.startswith("gads hours:"))
    day = next(dd for dd in sorted(h["h"][A1]["11"]) if dd >= "2026-09-10" and h["h"][A1]["11"][dd][5])
    fake.stop_hours = {("11", day, 5)}                                                # Google restates one hour
    lines = step(data, spend, fake, today=TODAY + timedelta(days=1), t=T0 + 24 * H)
    assert [re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", q).groups() for _, k, q in fake.calls if k == "HOURLY"] \
        == [("2026-08-26", "2026-09-24")] * 2
    assert ghr.load(data)["h"][A1]["11"][day][5] == 0
    assert "2026-06-26" in ghr.load(data)["h"][A1]["11"]                              # older days kept


def test_hours_failure_retried_then_backs_off(data, monkeypatch):
    fake = FakeAds()
    spend, _ = live(monkeypatch, fake, "2026-06-01", "2026-09-24", archive=False)
    fake.fail = lambda acct, k, q: "HTTP 500: SECRET" if k == "HOURLY" and acct == A2 else None
    for i in range(3):
        lines = step(data, spend, fake, t=T0 + i * H)
        assert "(partial)" in next(x for x in lines if x.startswith("gads hours:"))
    fake.calls.clear()
    step(data, spend, fake, t=T0 + 4 * H)
    assert fake.n("HOURLY") == 0                                                       # waits ~20 h after 3 failures
    assert len(ghr.load(data)["h"][A1]["11"]) > 70 and A2 not in ghr.load(data)["h"]


def test_hours_any_403_skipped_and_counted(data, monkeypatch):
    fake = FakeAds()
    spend, _ = live(monkeypatch, fake, "2026-06-01", "2026-09-24", archive=False)
    fake.fail = lambda acct, k, q: ("HTTP 403: authorizationError=USER_PERMISSION_DENIED — SECRET"
                                    if k == "HOURLY" and acct == A2 else None)
    lines = step(data, spend, fake)
    hl = next(x for x in lines if x.startswith("gads hours:"))
    assert "(skipped 1)" in hl and "(done)" in hl and hl.endswith("errors 1"), hl
    fake.calls.clear()
    step(data, spend, fake, today=TODAY + timedelta(days=1), t=T0 + 24 * H)
    assert fake.n("HOURLY", A2) == 0 and fake.n("HOURLY", A1) == 1


# ── public lines and the build wiring ────────────────────────────────────────────────────────────

def test_public_lines_counts_only(data, monkeypatch):
    fake = FakeAds()
    fake.add_event(A1, "2026-09-20 10:00:00.000000")
    spend, taken = live(monkeypatch, fake, "2026-06-26", "2026-09-24")
    fake.fail = lambda acct, k, q: "HTTP 403: authorizationError=USER_PERMISSION_DENIED %s %s SECRET" % (acct, S1) \
        if k == "abud" else None
    lines = step(data, spend, fake, taken=taken)
    lines += ga.archive_step(dict(SETTINGS, google_ads_dev_token=None), data, spend, TODAY, taken={})
    assert len(lines) == 6
    secrets = [MCC, A1, A2, A3, S1, S2, S3, DEV, TOK, "SECRET", "secret", "synth", "com.", "2026", "2025", "INR", "USD",
               "Asia", "0.", "camp "]
    for ln in lines:
        assert any(p.match(ln) for p in LINES.values()), ln
        for s_ in secrets:
            assert s_ not in ln.replace("campaigns", "").replace("campaign days", ""), (s_, ln)


def test_off_no_call_no_file_no_line(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GADS_ARCHIVE", raising=False)
    assert settings()["gads_archive"] is False
    monkeypatch.setattr(google_ads, "_search", lambda *a: (_ for _ in ()).throw(AssertionError("no request")))
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: (_ for _ in ()).throw(AssertionError("no token")))
    data = str(tmp_path / "data")
    os.makedirs(data)
    spend = {"v": 2, "currency_src": "INR", "daily": {S1: {"2026-09-01": M}}, "campaigns": {}, "fx": {}}
    keep = copy.deepcopy(spend)
    build_static._gads_archive_step(dict(SETTINGS, gads_archive=False), data, spend, TODAY)
    build_static._gads_archive_step({}, data, spend, TODAY)
    assert capsys.readouterr().err == "" and os.listdir(data) == [] and spend == keep
    build_static._gads_archive_step(dict(gads_archive=True), data, spend, TODAY)       # on, but no Google Ads secrets
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 3 and all("(off)" in x and "calls 0, errors 0" in x for x in err)
    assert os.listdir(data) == [] and spend == keep


def test_parts_fail_alone(tmp_path, monkeypatch, capsys):
    fake = FakeAds()
    data = str(tmp_path / "data")
    spend, taken = live(monkeypatch, fake, "2026-06-26", "2026-09-24")
    keep = json.dumps(spend, sort_keys=True)
    monkeypatch.setattr(ga, "archive_part", lambda *a: 1 / 0)
    monkeypatch.setattr(ghr, "hourly_part", lambda *a, **k: {}["x"])
    lines = ga.archive_step(SETTINGS, data, spend, TODAY, search=fake.search, token=TOK, taken=taken)
    assert lines[0] == "gads archive skipped: ZeroDivisionError" and "gads hours skipped: KeyError" in lines
    assert LINES["campaign"].match(lines[-1]) and json.dumps(spend, sort_keys=True) == keep
    monkeypatch.setattr(ga, "archive_step", lambda *a, **k: [][1])
    capsys.readouterr()
    build_static._gads_archive_step(dict(SETTINGS), data, spend, TODAY)
    assert capsys.readouterr().err == "gads archive skipped: IndexError\n"
    assert json.dumps(spend, sort_keys=True) == keep


def test_build_wiring_order_and_refresh_yml():
    src = open(build_static.__file__, encoding="utf-8").read()
    i_write = src.index("json.dump(spend, _cf)")
    i_geo = src.index("            _gads_geo_step(s, data_dir, spend, today)")
    i_arch = src.index("            _gads_archive_step(s, data_dir, spend, today)")
    i_roas = src.index("dashboard[\"roas\"] = build_roas(")
    assert i_write < i_geo < i_arch < i_roas
    body = src[src.index("def _gads_archive_step"):src.index("def data_quality")]
    assert 'if not s.get("gads_archive"):' in body and "except Exception as _ae:" in body
    y = open(os.path.join(os.path.dirname(build_static.__file__), "..", ".github", "workflows", "refresh.yml"),
             encoding="utf-8").read()
    assert "GADS_ARCHIVE:         ${{ vars.GADS_ARCHIVE || 'true' }}" in y
