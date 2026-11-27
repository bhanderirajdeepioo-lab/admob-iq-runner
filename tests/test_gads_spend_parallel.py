"""Google Ads spend fetch, accounts asked side by side (google_ads.fetch_app_spend, GADS_SPEND_WORKERS) and the roster
skip (needs_campaign_accounts): the same cache, rows kept aside and log lines as the one-account-after-another code —
in a synthetic MCC whose answers come back in a shuffled order (the read's D0 finality keys, which the one-after-another
code did not have, are compared on their own: tests/test_gads_d0_fix.py). All data is synthetic."""

import hashlib
import json
import sys
import threading
import time
from datetime import date, timedelta

import pytest

from admob_iq import health
from admob_iq.fetch import google_ads

MCC, DEV, TOK = "1110001111", "dev-SYNTH", "tok-SYNTH"
SETTINGS = {"google_ads_dev_token": DEV, "google_ads_login_customer_id": MCC, "google_ads_refresh_token": "rt-SYNTH",
            "google_ads_client_id": "cid-SYNTH", "google_ads_client_secret": "csec-SYNTH"}
START, END = "2026-01-01", "2026-01-12"
FX = {"USD": 1.0, "EUR": 1.1, "INR": 0.012}
NE = "HTTP 403: authorizationError=CUSTOMER_NOT_ENABLED — The customer account can't be accessed"
D0_KEYS = ("d1_final_till", "d1_next_fix_utc", "d1_lag_h", "d1_zones", "d1_ok",    # fetch_app_spend's D0 finality
           "d1_day", "d1_unread", "d1_ended")                                     # of the read (these two: when any)


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
            fake.d0 = {k: out.pop(k) for k in D0_KEYS if k in out}      # the rest: byte-compared with the old code
            fake.failed = out.pop("failed", None)                       # (new too: the accounts that could not answer)
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
    # one asked account refuses day-1 (a 403 that is not CUSTOMER_NOT_ENABLED): the read fixes no D0 date
    # (it answered cost, so it is not "unread": the whole read is incomplete)
    assert f.d0["d1_ok"] is False and f.d0["d1_lag_h"] == 4 and set(f.d0) == set(D0_KEYS) - {"d1_unread", "d1_ended"}
    # the not-enabled accounts (403 CUSTOMER_NOT_ENABLED on spend) are no longer asked for installs / day-1 …
    gone = {a for a, k in f0.calls if k == "spend" and a in f0.off}
    assert gone and len(gone) == len(f0.off)
    want = sorted(c for c in f0.calls if not (c[1] in ("inst", "d1") and c[0] in gone))
    assert _dump_calls(f) == want
    # … so only their two lines each go; every other line is the same, in the same order
    keep = [ln for ln in err0.splitlines() if not any(a in ln and "CUSTOMER_NOT_ENABLED" in ln for a in gone)]
    assert len(keep) == len(err0.splitlines()) - 2 * len(gone)
    lines = err.splitlines()
    banner = [ln for ln in lines if health.SKIP.search(ln)]     # new: the health banner's lines (no id in them)
    assert [ln for ln in lines if ln not in banner] == (
        ["roas: installs + day-1 not asked for %d not-enabled accounts" % len(gone)] + keep)
    assert any("HTTP 500" in ln for ln in keep) and any("USER_PERMISSION_DENIED" in ln for ln in keep)
    # the account refusing installs and the one refusing day-1 each tell the banner; the not-enabled ones never do.
    # Installs missing makes the read "failed" for that account (its stores keep the cache: merge_spend)
    assert banner == ["google ads installs skipped: RuntimeError", "google ads day-1 skipped: RuntimeError"]
    assert f.failed == [f.inst_500]


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


# ── a read an account could not answer: the health banner, never a silent $0 ───────────────────────────────────────

def test_an_account_that_cannot_answer_cost_tells_the_banner_and_marks_the_read(mcc, capsys, monkeypatch):
    class Half(MCCFake):
        def rows(self, acct, k):
            if k == "spend" and acct in self.ids[:2]:
                raise RuntimeError("HTTP 500: INTERNAL — synthetic")
            return super().rows(acct, k)
    monkeypatch.setattr(health, "FAULTS", {})
    out, _, f = mcc(4, fake=Half())
    lines = capsys.readouterr().err.splitlines()
    assert json.loads(out)["daily"]                                   # the accounts that answered still count
    assert f.failed == sorted(f.ids[:2] + [f.inst_500])
    assert [ln for ln in lines if ln.startswith("google ads spend skipped")] == ["google ads spend skipped: RuntimeError"]
    for ln in lines:
        health.scan(ln)
    assert health.FAULTS == {"google ads spend": "RuntimeError", "google ads installs": "RuntimeError",
                             "google ads day-1": "RuntimeError"}
    assert not any(a in ln for ln in lines if health.SKIP.search(ln) for a in f.ids)   # never an id in them


def test_an_account_with_no_cost_in_the_window_has_nothing_to_miss(mcc, capsys):
    """It answered cost with no row (no click): its installs / day-1 query failing misses nothing — no banner, the
    read is not marked (the D0 rule's own "idle")."""
    class Idle(MCCFake):
        def __init__(self):
            super().__init__()
            self.idle = self.ids[0]
            self.inst_500 = self.d1_403 = None                       # only the idle account fails here

        def rows(self, acct, k):
            if acct == self.idle:
                if k == "spend":
                    return []
                raise RuntimeError("HTTP 500: INTERNAL — synthetic")
            return super().rows(acct, k)
    out, _, f = mcc(4, fake=Idle())
    lines = capsys.readouterr().err.splitlines()
    assert json.loads(out)["daily"] and f.failed is None
    assert not [ln for ln in lines if health.SKIP.search(ln)]
    assert sum(f.idle in ln for ln in lines) == 2                    # the private log still has both lines


@pytest.mark.parametrize("step, error", [("_access_token", "OAuth fail"), ("_child_accounts", "MCC accounts nahi mile")])
def test_a_google_ads_sign_in_or_account_list_that_fails_tells_the_banner(monkeypatch, capsys, step, error):
    def refused(*a):
        raise RuntimeError("HTTP 400: invalid_grant — synthetic")
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: TOK)
    monkeypatch.setattr(google_ads, step, refused)
    out = google_ads.fetch_app_spend(dict(SETTINGS), START, END, mode="live")
    assert out["error"].startswith(error)
    assert "google ads spend skipped: RuntimeError" in capsys.readouterr().err.splitlines()


def _held_inputs():
    cached = {"v": google_ads.SPEND_CACHE_V, "currency_src": "USD", "fx": {},
              "daily": {"com.synth.both": {"2026-01-10": 100, "2026-01-11": 100}, "com.synth.b": {"2026-01-10": 7}},
              "installs": {"com.synth.both": {"2026-01-10": 10}}, "convval": {"com.synth.both": {"2026-01-10": 5.0}},
              "campaigns": {"com.synth.both": [{"id": "1", "account": "2220000001"}, {"id": "2", "account": "2220000002"}],
                            "com.synth.b": [{"id": "3", "account": "2220000002"}]}}
    fresh = {"currency_src": "USD", "fx": {}, "d1_ok": True,     # account …1 could not answer: only …2's part is here
             "daily": {"com.synth.both": {"2026-01-10": 60, "2026-01-11": 60, "2026-01-12": 60},
                       "com.synth.b": {"2026-01-10": 9}},
             "installs": {"com.synth.both": {"2026-01-10": 6}}, "convval": {"com.synth.both": {"2026-01-10": 3.0}},
             "campaigns": {"com.synth.both": [{"id": "2", "account": "2220000002"}],
                           "com.synth.b": [{"id": "3", "account": "2220000002"}]},
             "failed": ["2220000001"]}
    return cached, fresh


def test_a_store_of_an_account_that_could_not_answer_keeps_its_cached_days_and_its_own_last_day():
    cached, fresh = _held_inputs()
    out = google_ads.merge_spend(cached, fresh, "2026-01-01", ok_till="2026-01-11")
    # …1's part of the days the cache has is not lost; a day the cache lacks takes what this read has (…2's part)
    assert out["daily"]["com.synth.both"] == {"2026-01-10": 100, "2026-01-11": 100, "2026-01-12": 60}
    assert out["installs"]["com.synth.both"] == {"2026-01-10": 10} and out["convval"]["com.synth.both"] == {
        "2026-01-10": 5.0}
    assert out["daily"]["com.synth.b"] == {"2026-01-10": 9}          # a store of answering accounts only: updated
    assert [c["account"] for c in out["campaigns"]["com.synth.both"]] == ["2220000001", "2220000002"]   # stays held
    assert out["held_till"] == {"com.synth.both": "2026-01-11"}      # its own last whole day: the last read through
    # held again later: the first day stays (the cache's whole days stop there), whatever the newer reads' day
    cached2, fresh2 = _held_inputs()
    out2 = google_ads.merge_spend(dict(cached2, held_till=out["held_till"]), fresh2, "2026-01-01", ok_till="2026-01-20")
    assert out2["held_till"] == {"com.synth.both": "2026-01-11"}
    # every account answered: laid over as before, no store held
    cached3, fresh3 = _held_inputs()
    fresh3.pop("failed")
    out3 = google_ads.merge_spend(dict(cached3, held_till=out["held_till"]), fresh3, "2026-01-01", ok_till="2026-01-20")
    assert out3["daily"]["com.synth.both"] == {"2026-01-10": 60, "2026-01-11": 60, "2026-01-12": 60}
    assert [c["account"] for c in out3["campaigns"]["com.synth.both"]] == ["2220000002"] and "held_till" not in out3
    # a failed read keeps the cache whole, its held days with it
    assert google_ads.merge_spend(dict(cached3, held_till={"com.synth.both": "2026-01-11"}), {"error": "x"},
                                  "2026-01-01")["held_till"] == {"com.synth.both": "2026-01-11"}


def test_a_held_store_stops_its_app_at_its_own_last_day_on_both_screens():
    """Install value / ROI (value_build.app_spend) and CPI vs eCPM (cpi_build._spend): a held store's days after its
    held_till are "not in yet" (None / the app's till), every other store goes on to the read's day."""
    from datetime import date
    from admob_iq import cpi_build, value_build
    sp = {"ccy": "INR", "first": "2026-01-01", "till": "2026-01-20",
          "daily": {"com.synth.both": {"2026-01-12": 60}, "com.synth.b": {"2026-01-12": 9}},
          "installs": {}, "held": {"com.synth.both": "2026-01-11"}}
    pre = {"spend": sp, "owner": {"com.synth.both": "Synth Both", "com.synth.b": "Synth B"}, "siblings": {}}
    assert value_build.app_spend(pre, {"app_name": "Synth Both"}, {})["till"] == "2026-01-11"
    assert value_build.app_spend(pre, {"app_name": "Synth B"}, {})["till"] == "2026-01-20"
    D = cpi_build._Days(date(2026, 1, 1), date(2026, 1, 20))
    cache = {"daily": {k: {d: v * 1e6 for d, v in x.items()} for k, x in sp["daily"].items()},
             "held_till": {"com.synth.both": "2026-01-11"}}
    R = [0.012] * D.n
    held = cpi_build._spend(D, cache, "com.synth.both", "2026-01-20", R, None)["sp_inr"]
    other = cpi_build._spend(D, cache, "com.synth.b", "2026-01-20", R, None)["sp_inr"]
    assert held[D.ix["2026-01-11"]] == 0 and held[D.ix["2026-01-12"]] is None      # after its own day: not in yet
    assert other[D.ix["2026-01-12"]] == 9


def test_a_hold_longer_than_the_window_is_read_again_whole_once_its_account_answers():
    """refetch_from: while a store is held the read reaches back to its last whole day, so the read after its account
    answers again restates every day the hold left partial (a shared store: the other account's part only; a store of
    the failed account alone: nothing) — however long the hold, whatever the window (here 3 days)."""
    A, B, S, SOLO, W = "2220000001", "2220000002", "com.synth.shared", "com.synth.solo", 3

    def d(i):
        return (date(2026, 1, 1) + timedelta(days=i)).isoformat()

    def read(lo, today, failed):
        days = [d(i) for i in range(lo, today + 1)]
        daily = {S: {x: 10 if failed else 20 for x in days}}
        camps = {S: [{"id": "2", "account": B}] + ([] if failed else [{"id": "1", "account": A}])}
        if not failed:
            daily[SOLO], camps[SOLO] = {x: 5 for x in days}, [{"id": "3", "account": A}]
        return {"currency_src": "USD", "fx": {}, "d1_ok": True, "daily": daily, "installs": {}, "convval": {},
                "campaigns": camps, **({"failed": [A]} if failed else {})}
    cache, ok = google_ads.merge_spend(None, read(-W, 0, False), d(-W)), d(-1)
    for today in range(1, 10):                          # A fails on reads 1 … 7 (longer than the window), then answers
        lo = google_ads.refetch_from(cache, d(today - W))
        cache = google_ads.merge_spend(cache, read((date.fromisoformat(lo) - date(2026, 1, 1)).days, today, today < 8),
                                       lo, ok_till=ok)
        ok = d(today - 1)
        if today < 8:
            assert cache["held_till"] == {S: d(-1), SOLO: d(-1)} and lo == min(d(-1), d(today - W))
    assert "held_till" not in cache
    assert set(cache["daily"][S].values()) == {20} and set(cache["daily"][SOLO].values()) == {5}
    assert sorted(cache["daily"][S]) == sorted(cache["daily"][SOLO]) == [d(i) for i in range(-W, 10)]
    assert google_ads.refetch_from(None, "2026-03-01") == "2026-03-01"
    assert google_ads.refetch_from({"held_till": {"x": "2026-02-01", "y": None, "z": 7}}, "2026-03-01") == "2026-02-01"


def test_the_build_hands_the_last_read_day_to_merge_spend():
    """build_static: every merge_spend call gets the recorded last day a read went through (ok_till) — a store held
    from this read on keeps it as its own last day; without it the store's new days would read as $0."""
    import ast
    import inspect
    from admob_iq import build_static
    tree = ast.parse(inspect.getsource(build_static))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "merge_spend"]
    assert calls and all(any(k.arg == "ok_till" for k in c.keywords) for c in calls)
    # … and its read starts at refetch_from's day (a held store's last whole day when older than the window)
    assert any(isinstance(n, ast.Assign) and getattr(n.value, "func", None) is not None
               and getattr(n.value.func, "id", None) == "refetch_from"
               and [getattr(t, "id", None) for t in n.targets] == ["refetch_start"] for n in ast.walk(tree))


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
