"""⚖️ Breakeven's returning-session eCPM — the fetch (admob_iq.fetch.ga4_cecpm), offline with a fake GA4 and SYNTHETIC
countries and money: the one read shape, a record per activity day, GA4's flags → the day's state, the walk (forward,
hot, retries, redo, the backfill newest first), a Stop that keeps every day read, a store of another version / stream
read again, the build's read (load_cells) and a log line of counts only."""
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4_cecpm as ce
from admob_iq.fetch import ga4_cube as gcu
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 15)
EDGE = TODAY - timedelta(days=ce.FINAL_LAG)                 # 10 Oct
HS = date(2026, 9, 20)
AID = "ca-app-pub-0000000000000000~41"
KEY = gu.file_key(AID)
SID = "9000000041"
CTRY = ("XA", "XB", "(not set)")
USERS, IMPS = 10, 5                                        # users of an install day per country; ad events a user a day


def ecpm(cc, age):
    return {"XA": 2.0, "XB": 1.0, "(not set)": 0.5, "(other)": 0.25}[cc] * (1.0 - 0.05 * age)


def micros(cc, age):
    return int(round(USERS * IMPS * ecpm(cc, age) / 1000 * 1e6))


class FakeGA:
    """Answers the one read shape of activity day D: one group of USERS users per (install day, country) since HS,
    active every day, IMPS ad events each. meta: {D: GA4 metadata}; fold: countries answered as "(other)"; extra: junk
    rows added; stop_after: a Stop after that many calls."""

    def __init__(self, meta=None, fold=(), extra=False, stop_after=None, hs=HS, scale=None, sample_cc=False,
                 smp_pool=False):
        self.meta, self.fold, self.extra, self.stop_after, self.hs = meta or {}, set(fold), extra, stop_after, hs
        self.sample_cc, self.smp_pool = sample_cc, smp_pool       # GA4 samples the country read (and the pooled one)
        self.shapes = []
        self.scale = scale or {}                            # {D: × users that day} (GA4 still filling a day)
        self.calls, self.asked, self.tok = 0, [], 0
        self.last_metas = [{}]
        self.last_row_count = 0

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        dims = [x["name"] for x in body["dimensions"]]
        assert dims in (["date", "firstSessionDate", "countryId"], ["date", "firstSessionDate"])
        pooled = "countryId" not in dims
        self.shapes.append("pool" if pooled else "cc")
        assert [x["name"] for x in body["metrics"]] == ["totalAdRevenue", "eventCount"]
        assert event == "ad_impression" and body["currencyCode"] == "USD" and body["keepEmptyRows"] is False
        assert page_rows == gu.UNI_PAGE_ROWS and len(extra) == 1
        D = date.fromisoformat(body["dateRanges"][0]["startDate"])
        assert body["dateRanges"][0]["endDate"] == D.isoformat()
        xs = extra[0]["filter"]["inListFilter"]["values"]
        assert xs == sorted((D - timedelta(days=a)).strftime("%Y%m%d") for a in ce.AGES)
        self.asked.append(D)
        rows = []
        for x in xs:
            X = date(int(x[:4]), int(x[4:6]), int(x[6:]))
            if X < self.hs:
                continue
            age = (D - X).days
            k = self.scale.get(D, 1.0)
            if pooled:
                rows.append({"date": D.strftime("%Y%m%d"), "firstSessionDate": x,
                             "totalAdRevenue": sum(micros(c, age) for c in CTRY) / 1e6 * k,
                             "eventCount": round(USERS * IMPS * k) * len(CTRY)})
                continue
            for c in CTRY:
                cc = "(other)" if c in self.fold else c
                rows.append({"date": D.strftime("%Y%m%d"), "firstSessionDate": x, "countryId": cc,
                             "totalAdRevenue": micros(c, age) / 1e6 * k, "eventCount": round(USERS * IMPS * k)})
        if self.extra:
            rows.append({"date": D.strftime("%Y%m%d"), "firstSessionDate": "(other)", "countryId": "XA",
                         "totalAdRevenue": 0.5, "eventCount": 7})
        m = dict(self.meta.get(D, {}))
        if not pooled and (self.sample_cc is True or (isinstance(self.sample_cc, date) and D >= self.sample_cc)):
            m["samplingMetadatas"] = [{"samplesReadCount": "1", "samplingSpaceSize": "5"}]   # (True: every day; a
            #                                                                             date: the days from it)
        if pooled and not self.smp_pool:
            m.pop("samplingMetadatas", None)              # (the no-country read: whole, as the probe measured)
        self.last_metas = [m]
        self.last_row_count = len(rows) + (5 if m.get("cut") else 0)
        return rows

    def truncated(self, rows):
        return bool(self.last_row_count and self.last_row_count > len(rows))


def run(ga, data, today=TODAY, hs=HS, now=NOW):
    st = ce.Store(data, AID, SID)
    try:
        res = ce.step_app(ga, st, today, hs, now)
    except gf.Stop:
        res = "deferred"
    st.save()
    st.head.update(app_id=AID, stream_id=SID)
    st.save_head()
    return res, st


def month(data, k):
    return gu.load_store(ce.month_path(data, AID, k))


# ── the read and its record ─────────────────────────────────────────────────────────────────────────────────────────
def test_a_day_record_holds_every_age_of_every_country():
    ga = FakeGA(extra=True)
    rec = ce.read_day(ga, EDGE, "2026-10-15T06:00:00Z")
    assert rec["st"] == "oth" and rec["f"] == gcu.F_OTHER and rec["n"] == 6 * 3 + 1   # an "(other)" install day
    assert (rec["xn"], rec["xr"], rec["xi"]) == (1, 500000, 7)          # … is in no cell: measured
    assert ce.read_day(FakeGA(), EDGE, "t")["st"] == "ok"
    assert set(rec["c"]) == {"XA", "XB", "--"}                          # "(not set)" → "--"
    for k, a in enumerate(ce.AGES):
        assert rec["c"]["XA"][2 * k: 2 * k + 2] == [micros("XA", a), USERS * IMPS]
    ga2 = FakeGA(fold=("XB",))
    rec2 = ce.read_day(ga2, EDGE, "t")
    assert rec2["st"] == "oth" and rec2["f"] & gcu.F_OTHER and set(rec2["c"]) == {"XA", "~", "--"}
    assert rec2["c"]["~"][0] == micros("XB", 0)                         # GA4's "(other)" country of a real install day


def test_flags_become_the_days_state_and_bad_days_keep_no_cells():
    for meta, st in (({"cut": True}, "cut"), ({"subjectToThresholding": True}, "thr"),
                     ({"dataLossFromOtherRow": True}, "oth")):
        rec = ce.read_day(FakeGA(meta={EDGE: meta}), EDGE, "t")
        assert rec["st"] == st and (("c" in rec) == (st not in ce.BAD))
    ga = FakeGA(meta={EDGE: {"samplingMetadatas": [{}]}})              # GA4 samples the country split: pooled
    rec = ce.read_day(ga, EDGE, "t")
    assert rec["st"] == ce.POOL and set(rec["c"]) == {"*"} and rec["f6"] & gcu.F_SMP and ga.shapes == ["cc", "pool"]
    assert rec["c"]["*"][:2] == [sum(micros(c, 0) for c in CTRY), USERS * IMPS * len(CTRY)]
    rec = ce.read_day(FakeGA(meta={EDGE: {"samplingMetadatas": [{}]}}, smp_pool=True), EDGE, "t")
    assert rec["st"] == "smp" and "c" not in rec                        # both sampled: nothing kept, retried


def test_parse_routes_rows_into_cells_and_trims():
    D = date(2026, 10, 12)
    rows = [{"date": "20261012", "firstSessionDate": "20261012", "countryId": "XA", "totalAdRevenue": 0.25,
             "eventCount": 10},
            {"date": "20261012", "firstSessionDate": "20261011", "countryId": "", "totalAdRevenue": 0.5, "eventCount": 4},
            {"date": "20261012", "firstSessionDate": "20261008", "countryId": "XA", "totalAdRevenue": 9, "eventCount": 9},
            {"date": "20261011", "firstSessionDate": "20261011", "countryId": "XA", "totalAdRevenue": 9, "eventCount": 9},
            {"date": "20261012", "firstSessionDate": "20261013", "countryId": "XA", "totalAdRevenue": 9, "eventCount": 9}]
    rec = ce.parse(rows, D, 0, "t")
    assert rec["c"] == {"XA": [250000, 10], "--": [0, 0, 500000, 4]}     # age 4 is not asked: in no cell
    assert rec["xn"] == 3 and rec["xi"] == 27


# ── the walk ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_first_run_folds_the_edge_reads_hot_days_and_backfills_newest_first(tmp_path):
    data = str(tmp_path)
    ga = FakeGA()
    res, st = run(ga, data)
    assert res == "fetched"
    hot = [TODAY - timedelta(days=i) for i in range(ce.FINAL_LAG - 1, -1, -1)]
    back = [EDGE - timedelta(days=i) for i in range(1, (EDGE - HS).days + 1)]
    assert ga.asked == [EDGE] + hot + back                               # forward (the edge only), hot, backfill
    h = gu.load_store(ce.head_path(data, AID))
    assert h["upto"] == EDGE.isoformat() and h["oldest"] == HS.isoformat() and h["done"] is True
    assert sorted(h["hot"]) == [d.isoformat() for d in hot] and h["v"] == ce.V and h["ages"] == list(ce.AGES)
    assert len(month(data, "2026-10")["days"]) == 10 and len(month(data, "2026-09")["days"]) == 11
    assert sorted(os.listdir(ce.app_dir(data, AID))) == ["2026-09.json.gz", "2026-10.json.gz", ce.HEAD]
    # the next run, same day, 2 hours on: nothing due
    ga2 = FakeGA()
    assert run(ga2, data, now=NOW + timedelta(hours=2))[0] == "fresh" and ga2.asked == []
    # 7 hours on: the hot days again (replaced, never folded)
    ga3 = FakeGA()
    assert run(ga3, data, now=NOW + timedelta(hours=7))[0] == "fetched" and ga3.asked == hot


def test_forward_reads_every_day_an_outage_left_and_drops_final_hot_copies(tmp_path):
    data = str(tmp_path)
    run(FakeGA(), data)
    later = TODAY + timedelta(days=4)
    ga = FakeGA()
    run(ga, data, today=later, now=NOW + timedelta(days=4))
    new_final = [EDGE + timedelta(days=i) for i in range(1, 5)]
    assert ga.asked[:4] == new_final                                     # oldest first: never a hole
    h = gu.load_store(ce.head_path(data, AID))
    assert h["upto"] == (later - timedelta(days=ce.FINAL_LAG)).isoformat()
    assert all(k > h["upto"] for k in h["hot"])                          # a copy read while filling never stands in
    assert all(d.isoformat() in month(data, "2026-10")["days"] for d in new_final)


def test_a_day_ga4_empties_after_filling_it_is_held_never_folded_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "TOT_MIN", 100)                              # (the fake app's 900 events a day: judged)
    data = str(tmp_path)
    run(FakeGA(), data)                                                  # the next final day D is hot: read whole
    D = EDGE + timedelta(days=1)
    assert gu.load_store(ce.head_path(data, AID))["pk"][D.isoformat()] == 900
    res, st = run(FakeGA(scale={D: 0.01}), data, today=TODAY + timedelta(days=1), now=NOW + timedelta(days=1))
    h = gu.load_store(ce.head_path(data, AID))
    assert h["upto"] == EDGE.isoformat() and D.isoformat() in h["low"] and st.held >= 1
    assert ce._day_events(h["hot"][D.isoformat()]) == 900                # its fuller copy stays
    assert D.isoformat() not in month(data, "2026-10")["days"]
    ga = FakeGA()                                                        # an hour later, whole: folded
    run(ga, data, today=TODAY + timedelta(days=1), now=NOW + timedelta(days=1, hours=1))
    h = gu.load_store(ce.head_path(data, AID))
    assert ga.asked[0] == D and h["upto"] == D.isoformat()
    assert all(D.isoformat() not in h.get(f, {}) for f in ("low", "hot", "pk"))
    assert month(data, "2026-10")["days"][D.isoformat()]["st"] == "ok"
    # GA4 keeps it so LOW_WAIT days past the edge: folded as it is, "low" — the walk goes on
    data2 = str(tmp_path / "b")
    run(FakeGA(), data2)
    for i in range(1, ce.LOW_WAIT + 2):
        run(FakeGA(scale={D: 0.01}), data2, today=TODAY + timedelta(days=i), now=NOW + timedelta(days=i))
    h = gu.load_store(ce.head_path(data2, AID))
    assert month(data2, "2026-10")["days"][D.isoformat()]["st"] == ce.LOW and h["upto"] > D.isoformat()
    # never: a day with no earlier read, a small day, a sampled answer
    assert not ce._collapsed({}, D, {"st": "ok", "c": {}, "xi": 1})
    assert not ce._collapsed({"pk": {D.isoformat(): 99}}, D, {"st": "ok", "c": {}, "xi": 1})
    assert not ce._collapsed({"pk": {D.isoformat(): 5000}}, D, {"st": "smp"})
    assert ce._collapsed({"pk": {D.isoformat(): 5000}}, D, {"st": "ok", "c": {"XA": [0, 10]}, "xi": 0})


def test_a_real_lasting_drop_in_traffic_folds_as_it_is(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "TOT_MIN", 100)
    data = str(tmp_path)
    run(FakeGA(), data)

    class Drop(dict):                                    # every read of every day from D0 on: 30 % (a campaign cut)
        def get(self, k, d=None):
            return 0.3 if k >= D0 else 1.0

        def __bool__(self):
            return True
    D0 = TODAY + timedelta(days=1)                       # (from a day not read yet: GA4's numbers of a day only grow)
    for i in range(1, 21):
        run(FakeGA(scale=Drop()), data, today=TODAY + timedelta(days=i), now=NOW + timedelta(days=i))
    h = gu.load_store(ce.head_path(data, AID))
    days = {**month(data, "2026-10")["days"], **(month(data, "2026-11") or {"days": {}})["days"]}
    later = [k for k in days if k >= D0.isoformat()]
    assert len(later) == 20 - ce.FINAL_LAG and all(days[k]["st"] == "ok" for k in later)
    assert h["upto"] == (TODAY + timedelta(days=20 - ce.FINAL_LAG)).isoformat() and not h.get("low")


def test_a_hot_refresh_never_replaces_a_fuller_copy_with_an_emptied_one(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "TOT_MIN", 100)
    data = str(tmp_path)
    run(FakeGA(), data)
    D = TODAY - timedelta(days=2)
    res, st = run(FakeGA(scale={D: 0.005}), data, now=NOW + timedelta(hours=7))
    h = gu.load_store(ce.head_path(data, AID))
    assert ce._day_events(h["hot"][D.isoformat()]) == 900 and st.held == 1
    run(FakeGA(scale={D: 1.5}), data, now=NOW + timedelta(hours=14))     # GA4 adds more: the bigger copy wins
    assert ce._day_events(gu.load_store(ce.head_path(data, AID))["hot"][D.isoformat()]) == 1350


def test_a_stop_keeps_every_day_read_and_the_walk_goes_on(tmp_path):
    data = str(tmp_path)
    res, st = run(FakeGA(stop_after=2 + ce.FINAL_LAG + 1), data)        # the edge, the hot days, 2 of the backfill
    assert res == "deferred"
    h = gu.load_store(ce.head_path(data, AID))
    assert h["upto"] == EDGE.isoformat() and h["oldest"] == (EDGE - timedelta(days=2)).isoformat()
    assert not h.get("done") and len(month(data, "2026-10")["days"]) == 3
    ga = FakeGA()
    run(ga, data, now=NOW + timedelta(minutes=30))
    assert ga.asked[0] == EDGE - timedelta(days=3) and ga.asked[-1] == HS        # on from where it stopped
    assert gu.load_store(ce.head_path(data, AID))["done"] is True


def test_sampled_days_are_read_again_at_most_retry_times(tmp_path):
    data = str(tmp_path)
    bad = EDGE - timedelta(days=5)
    smp = {bad: {"samplingMetadatas": [{}]}}
    run(FakeGA(meta=smp, smp_pool=True), data)
    h = gu.load_store(ce.head_path(data, AID))
    assert h["retry"] == {bad.isoformat(): [0, "2026-10-15T06:00:00Z"]}
    assert month(data, "2026-10")["days"][bad.isoformat()]["st"] == "smp"
    ga = FakeGA(meta=smp, smp_pool=True)
    run(ga, data, now=NOW + timedelta(hours=12))
    assert bad not in ga.asked                                           # not before RETRY_GAP_HOURS
    for i, n in ((1, 1), (2, 2)):
        ga = FakeGA(meta=smp, smp_pool=True)
        run(ga, data, now=NOW + timedelta(days=i, hours=1), today=TODAY)
        assert ga.asked.count(bad) == 2                                  # (the country read, then the pooled one)
        rec = month(data, "2026-10")["days"][bad.isoformat()]
        assert rec["st"] == "smp" and rec["rt"] == n
    assert gu.load_store(ce.head_path(data, AID))["retry"] == {}         # after the last one: as it is, for good
    ga = FakeGA()
    run(ga, data, now=NOW + timedelta(days=5), today=TODAY)
    assert bad not in ga.asked
    # an answer that comes whole on a retry replaces the day
    data2 = str(tmp_path / "b")
    run(FakeGA(meta=smp, smp_pool=True), data2)
    run(FakeGA(), data2, now=NOW + timedelta(days=1, hours=1))
    rec = month(data2, "2026-10")["days"][bad.isoformat()]
    assert rec["st"] == "ok" and rec["rt"] == 1 and "c" in rec
    assert gu.load_store(ce.head_path(data2, AID))["retry"] == {}


def test_a_month_file_that_cannot_be_read_has_its_days_read_again(tmp_path):
    data = str(tmp_path)
    run(FakeGA(), data)
    p = ce.month_path(data, AID, "2026-09")
    with open(p, "wb") as f:
        f.write(b"not a gzip")
    st = ce.Store(data, AID, SID)
    st.month("2026-09")                                                  # a walk that touches September: its days
    assert st.bad == {"2026-09"} and st.head["redo"][0] == HS.isoformat() and len(st.head["redo"]) == 11   # again
    st.month("2026-09")
    assert st.reread == 11                                               # counted once
    data3 = str(tmp_path / "c")
    run(FakeGA(), data3)
    with open(ce.month_path(data3, AID, "2026-09"), "wb") as f:
        f.write(b"junk")
    h = gu.load_store(ce.head_path(data3, AID))
    h["done"] = False
    h["oldest"] = "2026-09-25"                                           # the backfill not done: it walks September
    gu.save_store(ce.head_path(data3, AID), h)
    ga3 = FakeGA()
    run(ga3, data3, now=NOW + timedelta(hours=1))
    mo = month(data3, "2026-09")
    assert len(mo["days"]) == 11                                         # 25 … 30 Sep read again (redo) + 20 … 24
    assert set(ga3.asked) == {date(2026, 9, d) for d in range(20, 31)}
    assert gu.load_store(ce.head_path(data3, AID))["redo"] == []


def test_another_version_or_stream_starts_over(tmp_path):
    data = str(tmp_path)
    run(FakeGA(), data)
    h = gu.load_store(ce.head_path(data, AID))
    h["ages"] = [0, 1]
    gu.save_store(ce.head_path(data, AID), h)
    st = ce.Store(data, AID, SID)
    assert st.fresh and "upto" not in st.head
    st2 = ce.Store(data, AID, "9000000042")
    assert st2.fresh
    assert ce.load_cells(data, KEY) is None                              # the build never reads a head of other ages


def test_a_history_start_that_moves_back_goes_on(tmp_path):
    data = str(tmp_path)
    run(FakeGA(), data)
    ga = FakeGA(hs=HS - timedelta(days=5))
    run(ga, data, hs=HS - timedelta(days=5), now=NOW + timedelta(hours=1))
    assert ga.asked == [HS - timedelta(days=i) for i in range(1, 6)]
    h = gu.load_store(ce.head_path(data, AID))
    assert h["oldest"] == (HS - timedelta(days=5)).isoformat() and h["done"] is True


def test_an_app_younger_than_the_final_edge_reads_only_its_hot_days(tmp_path):
    data = str(tmp_path)
    hs = TODAY - timedelta(days=1)
    ga = FakeGA(hs=hs)
    res, st = run(ga, data, hs=hs)
    assert ga.asked == [hs, TODAY] and "upto" not in st.head and not st.head.get("done")


# ── refresh_all and the log line ───────────────────────────────────────────────────────────────────────────────────
def _refresh(monkeypatch, tmp_path, apps=None, budget=None, stop_after=None, tick=0.0, workers=ce.WORKERS, now=NOW):
    data, clk = str(tmp_path), [0.0]
    route = {"property_id": "111", "stream_id": SID, "owner": "o"}
    monkeypatch.setattr(ce.gu, "load_state", lambda d: {"routes": {"by_package": {"com.example.alpha": route,
                                                                                  "com.example.beta": dict(route, property_id="112")}},
                                                        "tz": {"111": "Asia/Kolkata", "112": "UTC"}, "fetch": {}})
    monkeypatch.setattr(ce.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": HS.isoformat()})
    monkeypatch.setattr(ce.ga4, "access_token", lambda c, s, r: "tok")
    made = {}

    class A(FakeGA):
        def __init__(self, token, pid, sid, prop, over=None, max_calls=ce.MAX_CALLS):
            super().__init__(stop_after=stop_after)
            self.over, self.pid = over, pid

        def report_all(self, *a, **k):
            if self.over and self.over():
                raise gf.Stop("budget")
            clk[0] += tick
            made[self.pid] = made.get(self.pid, 0) + 1
            return super().report_all(*a, **k)
    monkeypatch.setattr(ce.gf, "App", A)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    apps = apps or [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~2", "package": "com.example.beta"},
                    {"app_id": "x~3", "package": "com.example.none"}, {"app_id": "x~4", "package": ""}]
    return data, made, ce.refresh_all(cfg, data, apps, now, clock=lambda: clk[0], budget=budget, workers=workers)


def test_refresh_all_reads_every_app_and_logs_counts_only(monkeypatch, tmp_path):
    data, made, out = _refresh(monkeypatch, tmp_path)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and "error" not in out
    c = out["counts"]
    assert (c["selected"], c["with_ga4"], c["fetched"], c["left"]) == (3, 2, 2, 0)
    assert c["days"] == 2 * ((EDGE - HS).days + 1) and c["hot"] == 2 * ce.FINAL_LAG
    st = ce.load_state(data)["fetch"]
    assert st["x~1"]["last_ok"] and st["x~1"]["key"] == gu.file_key("x~1") and "deferred" not in st["x~1"]
    h = gu.load_store(ce.head_path(data, "x~1"))
    assert h["time_zone"] == "Asia/Kolkata" and h["property_id"] == "111" and h["package"] == "com.example.alpha"
    line = ce.log_line(out)
    assert line.startswith("ga4 cohort ecpm: apps 3, with GA4 2, fetched 2, fresh 0, failed 0, deferred 0, waiting 0, "
                           "days folded 42, hot days 10, flagged 0, sampled 0, pooled 0, held back 0, "
                           "folded low 0, rows in no cell 0, read again 0, days left 0, stuck 0, calls ")
    for s in ("example", "x~", "111", SID, "XA", "2026"):
        assert s not in line


def test_the_budget_defers_and_the_cut_app_goes_first_next_run(monkeypatch, tmp_path):
    apps = [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~5", "package": "com.example.alpha"}]
    data, made, out = _refresh(monkeypatch, tmp_path, apps=apps, budget=10, tick=1.0)
    assert out["apps"]["x~1"] == "deferred" and out["apps"]["x~5"] == "deferred"
    assert out["counts"]["left"] > 0
    st = ce.load_state(data)["fetch"]
    assert st["x~1"]["deferred"] is True


def test_no_budget_given_means_the_fill_budget_while_history_is_read(tmp_path):
    data = str(tmp_path)
    assert ce.pick_budget(None, [ce.Store(data, AID, SID)]) == ce.FILL_SEC       # a new store
    run(FakeGA(), data)
    done = ce.Store(data, AID, SID)
    assert done.head["done"] and ce.pick_budget(None, [done]) == ce.BUDGET_SEC < ce.FILL_SEC
    assert ce.pick_budget(0, [done]) == ce.BUDGET_SEC and ce.pick_budget(25, [done]) == 25
    done.head["redo"] = ["2026-10-01"]
    assert ce.pick_budget(None, [done]) == ce.FILL_SEC
    assert ce.pick_budget(None, []) == ce.BUDGET_SEC


def test_a_bug_never_costs_the_build(monkeypatch, tmp_path):
    monkeypatch.setattr(ce.gu, "load_state", lambda d: 1 / 0)
    out = ce.refresh_all({}, str(tmp_path), [])
    assert out["error"] == "ZeroDivisionError" and ce.log_line(out).endswith(", error ZeroDivisionError")


# ── the build's read ───────────────────────────────────────────────────────────────────────────────────────────────
def test_load_cells_gives_every_install_days_ages_and_the_hot_copies(tmp_path):
    data = str(tmp_path)
    run(FakeGA(meta={EDGE - timedelta(days=4): {"samplingMetadatas": [{}]}}), data)
    got = ce.load_cells(data, KEY)
    assert got["done"] and got["hs"] == HS.isoformat() and got["upto"] == EDGE.isoformat()
    X = EDGE - timedelta(days=10)                                        # X + 6 = the sampled day, X + 13 a hot one
    cell = got["cells"][("XA", X.isoformat())]
    for k, a in enumerate(ce.AGES):
        D = X + timedelta(days=a)
        if D == EDGE - timedelta(days=4):
            assert cell[2 * k: 2 * k + 2] == [0, 0] and got["days"][D.isoformat()] == (ce.POOL, False)
        else:
            assert cell[2 * k: 2 * k + 2] == [micros("XA", a), USERS * IMPS]
    assert got["days"][TODAY.isoformat()] == ("ok", True)                # a hot copy: marked
    assert got["days"][(EDGE - timedelta(days=4)).isoformat()] == (ce.POOL, False)
    assert got["cells"][("*", X.isoformat())] == [0] * 8 + [sum(micros(c, 6) for c in CTRY), USERS * IMPS * len(CTRY),
                                                       0, 0]
    # (the pooled day's "*" cell, at its one age: X + 6)
    assert got["days"][EDGE.isoformat()] == ("ok", False)                # a folded day: never marked hot
    Y = TODAY - timedelta(days=1)
    assert got["cells"][("XB", Y.isoformat())][2:4] == [micros("XB", 1), USERS * IMPS]
    only = ce.load_cells(data, KEY, want={X.isoformat()})
    assert set(x for _, x in only["cells"]) == {X.isoformat()}
    assert ce.load_cells(str(tmp_path / "none"), KEY) is None


# ── review round 1: the count of days left, the two rounds, damaged months, a lost head, stuck apps ────────────────
def test_days_left_counts_an_app_not_started_and_the_forward_gap(tmp_path):
    data = str(tmp_path)
    st = ce.Store(data, AID, SID)
    assert st.left(HS, EDGE) == (EDGE - HS).days + 1                     # nothing read yet: every final day
    run(FakeGA(stop_after=1 + ce.FINAL_LAG + 3), data)                   # the edge, the hot days, 3 of the backfill
    st = ce.Store(data, AID, SID)
    assert st.left(HS, EDGE) == (EDGE - HS).days - 3
    assert st.left(HS, EDGE + timedelta(days=2)) == (EDGE - HS).days - 3 + 2      # + the final days after upto


def test_a_history_fill_never_holds_back_another_apps_newest_days(monkeypatch, tmp_path):
    apps = [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~2", "package": "com.example.beta"}]
    data, made, out = _refresh(monkeypatch, tmp_path, apps=apps, budget=1 + ce.FINAL_LAG + 1 + ce.FINAL_LAG + 3,
                               tick=1.0, workers=1)
    for aid in ("x~1", "x~2"):                                           # both got their newest days first …
        h = gu.load_store(ce.head_path(data, aid))
        assert h["upto"] == EDGE.isoformat() and len(h["hot"]) == ce.FINAL_LAG
    assert out["apps"] == {"x~1": "deferred", "x~2": "deferred"}         # … then the history with the time left


def test_properties_take_turns_by_their_longest_waiting_app(monkeypatch, tmp_path):
    apps = [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~2", "package": "com.example.beta"}]
    order, real = [], ce.step_app

    def spy(ga, st, today, hs, now, part=None):
        if part == "fill":
            order.append(st.app_id)
        return real(ga, st, today, hs, now, part)
    monkeypatch.setattr(ce, "step_app", spy)
    _refresh(monkeypatch, tmp_path, apps=apps, budget=2 * (1 + ce.FINAL_LAG) + 3, tick=1.0, workers=1)
    assert order[0] == "x~1"                                             # (ids in order the first time)
    order.clear()
    _refresh(monkeypatch, tmp_path, apps=apps, budget=2 * (1 + ce.FINAL_LAG) + 3, tick=1.0, workers=1,
             now=NOW + timedelta(minutes=30))
    assert order[0] == "x~2"                                             # x~2 never had its fill: first now


def test_a_damaged_month_the_walk_no_longer_touches_is_found_and_read_again(tmp_path):
    data = str(tmp_path)
    run(FakeGA(), data)                                                  # done: only October is touched from now on
    with open(ce.month_path(data, AID, "2026-09"), "wb") as f:
        f.write(b"junk")
    st = ce.Store(data, AID, SID)
    st.check_months(TODAY + timedelta(days=1))
    assert st.bad == {"2026-09"} and len(st.head["redo"]) == 11
    assert len(gu.load_store(ce.head_path(data, AID))["redo"]) == 11     # durable before anything is written over it
    ga = FakeGA()
    run(ga, data, today=TODAY + timedelta(days=1), now=NOW + timedelta(days=1))
    assert set(ga.asked) >= {HS + timedelta(days=i) for i in range(11)}
    assert len(month(data, "2026-09")["days"]) == 11 and gu.load_store(ce.head_path(data, AID))["redo"] == []
    ga2 = FakeGA()
    run(ga2, data, today=TODAY + timedelta(days=1), now=NOW + timedelta(days=1, hours=1))
    assert ga2.asked == []                                               # (checked once a property day)


def test_cells_are_whole_pairs_and_an_odd_cell_never_crashes_the_read(tmp_path):
    D = date(2026, 10, 12)
    rows = [{"date": "20261012", "firstSessionDate": "20261012", "countryId": "XA", "totalAdRevenue": 0.25,
             "eventCount": 10},
            {"date": "20261012", "firstSessionDate": "20261011", "countryId": "XA", "totalAdRevenue": 0.01,
             "eventCount": 0}]
    rec = ce.parse(rows, D, 0, "t")
    assert len(rec["c"]["XA"]) % 2 == 0 and rec["c"]["XA"] == [250000, 10, 10000, 0]
    data = str(tmp_path)
    run(FakeGA(), data)
    mo = month(data, "2026-10")
    mo["days"][EDGE.isoformat()]["c"]["XA"] = [5, 5, 7]                  # an odd cell (an older writer)
    gu.save_store(ce.month_path(data, AID, "2026-10"), mo)
    got = ce.load_cells(data, KEY)
    assert got["cells"][("XA", (EDGE - timedelta(days=1)).isoformat())][2:4] == [7, 0]


def test_a_lost_head_never_reads_the_history_twice(tmp_path):
    data = str(tmp_path)
    run(FakeGA(), data)
    os.remove(ce.head_path(data, AID))
    ga = FakeGA()
    run(ga, data, now=NOW + timedelta(hours=1))
    assert ga.asked == [EDGE] + [TODAY - timedelta(days=i) for i in range(ce.FINAL_LAG - 1, -1, -1)]
    h = gu.load_store(ce.head_path(data, AID))
    assert h["done"] and h["oldest"] == HS.isoformat() and len(month(data, "2026-09")["days"]) == 11


def test_redo_days_are_read_before_the_backfill(tmp_path):
    data = str(tmp_path)
    run(FakeGA(), data)
    with open(ce.month_path(data, AID, "2026-10"), "wb") as f:
        f.write(b"junk")                                                 # October cannot be read
    hs, today = HS - timedelta(days=30), TODAY + timedelta(days=1)       # the history start moved back: a backfill
    ga = FakeGA(hs=hs, stop_after=1 + ce.FINAL_LAG + 10)
    res, st = run(ga, data, today=today, hs=hs, now=NOW + timedelta(days=1))
    assert res == "deferred"
    assert ga.asked[1 + ce.FINAL_LAG:] == [EDGE - timedelta(days=i) for i in range(10)]   # 10 … 1 Oct, first


def test_an_app_failing_run_after_run_is_stuck(monkeypatch, tmp_path):
    apps = [{"app_id": "x~1", "package": "com.example.alpha"}]
    boom = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 400: x"))
    monkeypatch.setattr(ce, "step_app", boom)
    for i in range(ce.FAIL_LINE):
        data, made, out = _refresh(monkeypatch, tmp_path, apps=apps, now=NOW + timedelta(hours=4 * i))
        assert out["apps"] == {"x~1": "failed"}
    assert out["counts"]["stuck"] == 1 and ", stuck 1, " in ce.log_line(out)
    data, made, out = _refresh(monkeypatch, tmp_path, apps=apps, now=NOW + timedelta(hours=4 * ce.FAIL_LINE - 2))
    assert out["counts"]["stuck"] == 1                                   # (the RETRY_HOURS gate: still stuck)


def test_today_is_the_propertys_date_not_utcs(monkeypatch, tmp_path):
    late = datetime(2026, 10, 15, 20, 0, tzinfo=timezone.utc)            # 01:30 on 16 Oct in Asia/Kolkata
    data, made, out = _refresh(monkeypatch, tmp_path, now=late)
    ist, utc = (gu.load_store(ce.head_path(data, a)) for a in ("x~1", "x~2"))
    assert ist["hot_today"] == "2026-10-16" and ist["upto"] == (date(2026, 10, 16) - timedelta(days=ce.FINAL_LAG)).isoformat()
    assert utc["hot_today"] == "2026-10-15" and utc["upto"] == EDGE.isoformat()


def test_the_cut_app_goes_first_next_run(monkeypatch, tmp_path):
    apps = [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~5", "package": "com.example.alpha"}]
    order, real = [], ce.step_app

    def spy(ga, st, today, hs, now, part=None):
        if part == "fill":
            order.append(st.app_id)
        return real(ga, st, today, hs, now, part)
    monkeypatch.setattr(ce, "step_app", spy)
    data, _, out = _refresh(monkeypatch, tmp_path, apps=apps, budget=2 * (1 + ce.FINAL_LAG) + 25, tick=1.0)
    assert out["apps"] == {"x~1": "fetched", "x~5": "deferred"} and order == ["x~1", "x~5"]
    st = ce.load_state(data)["fetch"]
    assert "deferred" not in st["x~1"] and st["x~5"]["deferred"] is True
    order.clear()
    data, _, out = _refresh(monkeypatch, tmp_path, apps=apps, budget=10 ** 6, now=NOW + timedelta(minutes=30))
    assert order == ["x~5"] and out["apps"] == {"x~5": "fetched", "x~1": "fresh"}   # (x~1: nothing left to fill)
    assert "deferred" not in ce.load_state(data)["fetch"]["x~5"]


def test_the_real_app_keeps_the_call_cap_and_the_propertys_quota_floor(monkeypatch, tmp_path):
    data = str(tmp_path)
    route = {"property_id": "111", "stream_id": SID, "owner": "o"}
    monkeypatch.setattr(ce.gu, "load_state", lambda d: {"routes": {"by_package": {
        "com.example.alpha": route, "com.example.beta": dict(route, property_id="112")}},
        "tz": {"111": "UTC", "112": "UTC"}, "fetch": {}})
    monkeypatch.setattr(ce.gaud, "_uni_meta",
                        lambda ust, d, aid, r: {"history_start": (HS - timedelta(days=200)).isoformat()})
    monkeypatch.setattr(ce.ga4, "access_token", lambda c, s, r: "tok")
    monkeypatch.setattr(ce.ga4, "_sleep", lambda s: None)
    n = {}

    def call(method, url, token, body=None, params=None):
        pid = url.split("/properties/")[1].split(":")[0]
        n[pid] = n.get(pid, 0) + 1
        low = pid == "111" and n[pid] >= 4                    # property 111 under its floor from its 4th answer on
        b = {"consumed": 39000, "remaining": 1000} if low else {"consumed": 10, "remaining": 39990}
        return {"rows": [], "rowCount": 0, "metadata": {}, "propertyQuota": {"tokensPerHour": b}}
    monkeypatch.setattr(ce.ga4, "_call", call)
    apps = [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~5", "package": "com.example.alpha"},
            {"app_id": "x~2", "package": "com.example.beta"}]
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = ce.refresh_all(cfg, data, apps, NOW, clock=lambda: 0.0, budget=10 ** 6)
    assert "error" not in out
    assert out["apps"] == {"x~1": "deferred", "x~5": "deferred", "x~2": "deferred"}
    assert n == {"111": 4, "112": ce.MAX_CALLS}       # the floor stops property 111 (x~5 never asks); the cap stops x~2
    st = ce.load_state(data)["fetch"]
    assert "turn" in st["x~1"] and "turn" not in st["x~5"]      # x~5 never had its turn: it goes first next run


def test_an_app_whose_country_split_ga4_samples_reads_the_pooled_day_only(tmp_path):
    data = str(tmp_path)
    ga = FakeGA(sample_cc=True)
    run(ga, data)
    h = gu.load_store(ce.head_path(data, AID))
    n_back = (EDGE - HS).days                                            # the history: POOL_RUN tries, then a try
    want = 1 + ce.POOL_RUN + (n_back - ce.POOL_RUN) // ce.POOL_CHECK     # every POOL_CHECK-th day (+ the forward one)
    assert h["pool"] is True and h["bpool"] is True and ga.shapes[:2] == ["cc", "pool"]
    assert ga.shapes.count("cc") == want < n_back
    days = month(data, "2026-10")["days"]
    assert all(r["st"] == ce.POOL and set(r["c"]) == {"*"} for r in days.values())
    got = ce.load_cells(data, KEY)
    X = EDGE - timedelta(days=13)
    assert got["cells"][("*", X.isoformat())][10:12] == [sum(micros(c, 13) for c in CTRY), USERS * IMPS * len(CTRY)]
    assert ("XA", X.isoformat()) not in got["cells"]                     # (no country cells: never the sampled split)
    ga2 = FakeGA()                                                       # the next day: the country read whole again
    run(ga2, data, today=TODAY + timedelta(days=1), now=NOW + timedelta(days=1))
    h = gu.load_store(ce.head_path(data, AID))
    assert h["pool"] is False and ga2.shapes[0] == "cc" and "pool" not in ga2.shapes
    assert month(data, "2026-10")["days"][(EDGE + timedelta(days=1)).isoformat()]["st"] == "ok"


def test_the_history_asks_the_country_read_again_and_keeps_it_where_ga4_answers_whole(tmp_path):
    data = str(tmp_path)
    busy = EDGE - timedelta(days=6)                                      # GA4 samples the country split from here on
    ga = FakeGA(sample_cc=busy)
    run(ga, data)
    days = {**month(data, "2026-09")["days"], **month(data, "2026-10")["days"]}
    assert all(days[d.isoformat()]["st"] == ce.POOL for d in (EDGE, busy))
    old = [k for k in days if k < (busy - timedelta(days=ce.POOL_CHECK)).isoformat()]
    assert old and all(days[k]["st"] == "ok" and "XA" in days[k]["c"] for k in old)   # whole again: by country
    h = gu.load_store(ce.head_path(data, AID))
    assert h["bpool"] is False and h["bstreak"] == 0


def test_round_two_defers_only_an_app_with_history_left_and_a_good_first_round_ends_a_streak(monkeypatch, tmp_path):
    apps = [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~5", "package": "com.example.alpha"}]
    data, _, out = _refresh(monkeypatch, tmp_path, apps=apps, budget=10 ** 6)          # both histories read
    st = ce.load_state(data)
    st["fetch"]["x~1"]["fails"] = 2                                       # (two failed runs before)
    ce.save_state(data, st)
    data, _, out = _refresh(monkeypatch, tmp_path, apps=apps, budget=2 * ce.FINAL_LAG, tick=1.0,
                            now=NOW + timedelta(hours=7))                 # the hot reads only: just enough time
    assert out["apps"] == {"x~1": "fetched", "x~5": "fetched"} and out["counts"]["deferred"] == 0
    st = ce.load_state(data)["fetch"]
    assert all("deferred" not in st[a] for a in ("x~1", "x~5")) and "fails" not in st["x~1"]


def test_a_month_file_gone_inside_the_folded_days_is_read_again(tmp_path):
    data = str(tmp_path)
    run(FakeGA(), data)
    os.remove(ce.month_path(data, AID, "2026-09"))
    ga = FakeGA()
    run(ga, data, today=TODAY + timedelta(days=1), now=NOW + timedelta(days=1))
    assert {HS + timedelta(days=i) for i in range(11)} <= set(ga.asked)
    assert len(month(data, "2026-09")["days"]) == 11

