"""Google Ads spend fetch, accounts asked side by side (google_ads.fetch_app_spend, GADS_SPEND_WORKERS) and the roster
skip (needs_campaign_accounts): the same cache, rows kept aside and log lines as the one-account-after-another code —
in a synthetic MCC whose answers come back in a shuffled order. All data is synthetic."""

import hashlib
import json
import sys
import threading
import time

import pytest

from admob_iq.fetch import google_ads

MCC, DEV, TOK = "1110001111", "dev-SYNTH", "tok-SYNTH"
SETTINGS = {"google_ads_dev_token": DEV, "google_ads_login_customer_id": MCC, "google_ads_refresh_token": "rt-SYNTH",
            "google_ads_client_id": "cid-SYNTH", "google_ads_client_secret": "csec-SYNTH"}
START, END = "2026-01-01", "2026-01-12"
FX = {"USD": 1.0, "EUR": 1.1, "INR": 0.012}
NE = "HTTP 403: authorizationError=CUSTOMER_NOT_ENABLED — The customer account can't be accessed"


def _h(*parts):
    return int(hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


class MCCFake:
    """A synthetic MCC: n accounts (every 3rd not enabled, one billed in EUR, one refusing installs with HTTP 500, one
    refusing day-1 with a 403 that is not CUSTOMER_NOT_ENABLED), each answering after a seeded random pause so the
    side-by-side answers finish out of order. Thread-safe; logs every call."""

    def __init__(self, n=40, seed=7, pause=0.002):
        self.ids = ["22200%05d" % i for i in range(n)]
        self.seed, self.pause, self.calls, self.lock = seed, pause, [], threading.Lock()
        self.off = {a for i, a in enumerate(self.ids) if i % 3 == 2}
        self.ccy = {a: ("EUR" if i == 4 else "USD") for i, a in enumerate(self.ids)}
        self.inst_500, self.d1_403 = self.ids[7], self.ids[10]

    def kind(self, q):
        if "FROM customer_client" in q:
            return "roster"
        if "conversion_lag_bucket" in q:
            return "d1"
        if "biddable_app_install_conversions" in q:
            return "inst"
        if "metrics.cost_micros" in q:
            return "spend"
        if q.startswith("SELECT campaign.id FROM campaign"):
            return "camps"
        raise AssertionError(q)

    def __call__(self, customer_id, login, dev, token, query):
        assert (login, dev, token) == (MCC, DEV, TOK)
        k = self.kind(query)
        with self.lock:
            self.calls.append((customer_id, k))
        time.sleep(self.pause * (_h(self.seed, customer_id, k) % 7))
        if k == "roster":
            out = [{"customerClient": {"id": MCC, "manager": True}}]
            out += [{"customerClient": {"id": a, "currencyCode": self.ccy[a], "descriptiveName": "Synth %s" % a[-3:],
                                        "manager": False, "timeZone": "Etc/UTC"}} for a in self.ids]
            return out
        if customer_id in self.off:
            raise RuntimeError(NE)
        if k == "inst" and customer_id == self.inst_500:
            raise RuntimeError("HTTP 500: INTERNAL — synthetic")
        if k == "d1" and customer_id == self.d1_403:
            raise RuntimeError("HTTP 403: authorizationError=USER_PERMISSION_DENIED — synthetic")
        return self.rows(customer_id, k)

    def rows(self, acct, k):
        i = self.ids.index(acct)
        out = []
        for c in range(1 + i % 3):
            cid = "9%s%d" % (acct[-4:], c)
            sid = "com.synth.app%d" % ((i + c) % 9) if (i + c) % 11 else "2:%d" % (900000 + i)
            for dd in range(1, 13):
                day = "2026-01-%02d" % dd
                v = _h(acct, c, day, k)
                camp = {"id": cid, "appCampaignSetting": {"appId": sid}}
                if k == "spend":
                    if v % 5 == 0:
                        continue
                    camp.update(name="Synth campaign %s" % cid, status="ENABLED" if c else "PAUSED")
                    out.append({"campaign": camp, "metrics": {"costMicros": str(1000 + v % 900000)},
                                "segments": {"date": day}})
                elif k == "inst":
                    out.append({"campaign": camp, "segments": {"date": day},
                                "metrics": {"biddableAppInstallConversions": (v % 400) / 4,
                                            "conversionsValue": (v % 9000) / 7}})
                else:
                    for b in ("LESS_THAN_ONE_DAY", "ONE_TO_TWO_DAYS"):
                        out.append({"campaign": camp, "metrics": {"conversionsValue": (_h(v, b) % 5000) / 3},
                                    "segments": {"date": day, "conversionLagBucket": b}})
        return out


def _old_fetch_app_spend(s, start, end):
    """The pre-change fetch_app_spend's account loops, one account after another (the reference)."""
    g = google_ads
    dev, mcc = s["google_ads_dev_token"], s["google_ads_login_customer_id"]
    token = g._access_token(s["google_ads_client_id"], s["google_ads_client_secret"], s["google_ads_refresh_token"])
    accounts = g._child_accounts(mcc, dev, token) or [{"id": mcc, "currency": "USD", "name": ""}]
    rows, errs = [], []
    for a in accounts:
        try:
            for r in g._app_spend_for(a["id"], mcc, dev, token, start, end):
                r["currency"] = a["currency"]; r["account"] = a["id"]; r["account_name"] = a.get("name") or ""
                rows.append(r)
        except Exception as e:
            errs.append(str(e)[:220])
    if not rows and errs:
        return {"error": "Spend query fail (%d/%d accounts): %s" % (len(errs), len(accounts), errs[0])}, {}
    agg = g._aggregate(rows)
    inst_rows = []
    for a in accounts:
        try:
            for r in g._app_installs_for(a["id"], mcc, dev, token, start, end):
                r["currency"] = a["currency"]; r["account"] = a["id"]; inst_rows.append(r)
        except Exception as e:
            print("roas: installs/convval skipped for %s: %s" % (a.get("id"), e), file=sys.stderr)
    agg["installs"] = g._aggregate_installs(inst_rows)
    agg["convval"] = g._aggregate_convval(inst_rows, base=agg["currency_src"])
    d1_rows = []
    for a in accounts:
        try:
            for r in g._app_convval_lag_for(a["id"], mcc, dev, token, start, end):
                r["currency"] = a["currency"]; r["account"] = a["id"]; d1_rows.append(r)
        except Exception as e:
            print("roas: day-1 convval skipped for %s: %s" % (a.get("id"), e), file=sys.stderr)
    agg["convval_day1"] = g._aggregate_convval(d1_rows, base=agg["currency_src"])
    taken = {"start": str(start), "end": str(end), "accounts": [dict(a) for a in accounts], "spend": rows,
             "inst": inst_rows, "d1": d1_rows} if s.get("gads_archive") else {}
    return agg, taken


@pytest.fixture
def mcc(monkeypatch):
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: TOK)
    monkeypatch.setattr(google_ads, "_fx_to_usd", FX.get)
    monkeypatch.setattr(google_ads._aggregate, "__defaults__", (FX.get,))
    monkeypatch.setattr(google_ads._aggregate_convval, "__defaults__", (None, FX.get))

    def run(workers, fake=None, archive=True, old=False):
        fake = fake or MCCFake()
        monkeypatch.setattr(google_ads, "_search", fake)
        s = dict(SETTINGS, gads_archive=archive)
        if old:
            out, taken = _old_fetch_app_spend(s, START, END)
        else:
            monkeypatch.setenv("GADS_SPEND_WORKERS", str(workers))
            out = google_ads.fetch_app_spend(s, START, END, mode="live")
            taken = google_ads.take_rows()
        return json.dumps(out), json.dumps(taken), fake
    return run


def _dump_calls(fake):
    return sorted(fake.calls)


@pytest.mark.parametrize("workers", [1, 2, 4, 8])
def test_same_cache_rows_and_lines_as_one_after_another(mcc, capsys, workers):
    out0, taken0, f0 = mcc(1, old=True)
    err0 = capsys.readouterr().err
    out, taken, f = mcc(workers)
    err = capsys.readouterr().err
    assert out == out0 and taken == taken0                    # the very same bytes (order included)
    js = json.loads(out)
    assert js["daily"] and js["installs"] and js["convval"] and js["convval_day1"] and "EUR" in js["fx"]
    # the not-enabled accounts (403 CUSTOMER_NOT_ENABLED on spend) are no longer asked for installs / day-1 …
    gone = {a for a, k in f0.calls if k == "spend" and a in f0.off}
    assert gone and len(gone) == len(f0.off)
    want = sorted(c for c in f0.calls if not (c[1] in ("inst", "d1") and c[0] in gone))
    assert _dump_calls(f) == want
    # … so only their two lines each go; every other line is the same, in the same order
    keep = [ln for ln in err0.splitlines() if not any(a in ln and "CUSTOMER_NOT_ENABLED" in ln for a in gone)]
    assert len(keep) == len(err0.splitlines()) - 2 * len(gone)
    assert err.splitlines() == ["roas: installs + day-1 not asked for %d not-enabled accounts" % len(gone)] + keep
    assert any("HTTP 500" in ln for ln in keep) and any("USER_PERMISSION_DENIED" in ln for ln in keep)


def test_answers_really_finish_out_of_order_and_side_by_side(mcc):
    """The fake's pauses shuffle the finishing order: what is compared above is not one-after-another by chance."""
    done, lock, live, peak = [], threading.Lock(), [0], [0]

    class Probe(MCCFake):
        def __call__(self, *a):
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            try:
                return super().__call__(*a)
            finally:
                with lock:
                    live[0] -= 1
                    done.append((a[0], self.kind(a[4])))
    p = Probe(seed=3)
    out4, _, _ = mcc(4, fake=p)
    spend_done = [a for a, k in done if k == "spend"]
    assert peak[0] > 1 and sorted(spend_done) == p.ids and spend_done != p.ids
    out1, _, _ = mcc(1, fake=MCCFake(seed=3), old=True)
    assert out4 == out1


def test_no_archive_takes_nothing_and_all_failing_spend_is_the_same_error(mcc):
    out0, taken0, _ = mcc(1, archive=False, old=True)
    out, taken, _ = mcc(4, archive=False)
    assert out == out0 and taken == taken0 == "{}"

    class Down(MCCFake):
        def rows(self, acct, k):
            raise RuntimeError("HTTP 503: UNAVAILABLE — synthetic")
    out0, _, _ = mcc(1, fake=Down(), old=True)
    out, _, _ = mcc(4, fake=Down())
    assert out == out0 and "Spend query fail" in json.loads(out)["error"]


def test_bad_worker_setting_falls_back(monkeypatch):
    monkeypatch.setenv("GADS_SPEND_WORKERS", "x")
    assert google_ads._spend_workers() == google_ads.SPEND_WORKERS
    monkeypatch.setenv("GADS_SPEND_WORKERS", "0")
    assert google_ads._spend_workers() == 1
    monkeypatch.delenv("GADS_SPEND_WORKERS")
    assert google_ads._spend_workers() == 4


# ── the roster stage: asked only when a cached campaign has no account ─────────────────────────────────────────────

def _cache(untagged=0):
    camps = {"com.synth.a": [{"id": "91", "name": "A", "status": "ENABLED", "cost_micros": 5, "account": "2220000001",
                              "account_name": "Synth 1"},
                             {"id": "92", "name": "B", "status": "PAUSED", "cost_micros": 0, "account": "2220000002",
                              "account_name": ""}],
             "com.synth.b": [{"id": "93", "name": "C", "status": "REMOVED", "cost_micros": 7,
                              "account": None if untagged else "2220000003", "account_name": None}]}
    return {"v": google_ads.SPEND_CACHE_V, "daily": {"com.synth.a": {"2026-01-01": 5}}, "campaigns": camps,
            "currency_src": "USD", "fx": {}}


def test_roster_needed_only_for_an_untagged_campaign():
    full = {"91": {"account": "X", "account_name": "Y"}, "92": {"account": "X", "account_name": "Y"},
            "93": {"account": "2220000009", "account_name": "Synth 9"}}
    c = _cache()
    assert not google_ads.needs_campaign_accounts(c)
    before = json.dumps(c)
    google_ads.apply_campaign_accounts(c, full)               # what the skipped roster could have done: nothing
    assert json.dumps(c) == before
    assert json.dumps(google_ads.apply_campaign_accounts(_cache(), {})) == before
    u = _cache(untagged=1)
    assert google_ads.needs_campaign_accounts(u)
    google_ads.apply_campaign_accounts(u, full)
    assert u["campaigns"]["com.synth.b"][0]["account"] == "2220000009"
    for x in (None, {}, {"error": "x"}, {"campaigns": {}}, {"campaigns": {"s": []}}):
        assert not google_ads.needs_campaign_accounts(x)


def test_build_skips_the_roster_queries_when_every_campaign_is_tagged(monkeypatch):
    """build_static's gads_campaign_accounts stage: fetch_campaign_accounts only when needs_campaign_accounts."""
    import inspect
    from admob_iq import build_static
    src = inspect.getsource(build_static.build)
    assert 'fetch_campaign_accounts(s, mode="live") if needs_campaign_accounts(spend) else {}' in src
