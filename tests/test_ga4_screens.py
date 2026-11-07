"""🖼️ Screens — the GA4 fetch (admob_iq.fetch.ga4_screens), offline with a fake GA4 and made-up apps, screen classes,
ad units and numbers: every read's dimensions / metrics / event filter per shape, the whole check (whole, partial,
silent loss, sampled, cut, thresholded), the grain (chunk ladder, coarser shapes per day with the shapes tried saved
before a stop, the volume gate, dead shapes and their retry — final days only — and a final day they leave unasked,
asked anyway), the skips without calls, the event list, the recent window and its truth, the gap fill, the two passes,
quota floors and 429s, the store (recent file, month files by group, the move, damaged files left alone, old skip
records read again), the loaders, the history job (token renewal, its heartbeat, its staged files and their merge), and
counts-only lines."""
import gzip
import hashlib
import json
import os
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import stage_clock
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_activity_probe as probe
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_screens as gs
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 11, 4, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 4)
FE = date(2026, 10, 30)                                 # the newest final day (today − 5)
AID = "ca-app-pub-0000000000000000~21"
AID2 = "ca-app-pub-0000000000000000~22"
KEY = gu.file_key(AID)
MAIN, LIST_, ADACT = "x.y.MainActivity", "x.y.ListActivity", "z.ads.AdActivity"
# per day, made up: views (class, nvr, version, country, views, eng s, sessions, users) …
VIEW = [(MAIN, "new", "1.0", "XA", 30, 150, 10, 8), (MAIN, "returning", "1.1", "XB", 70, 350, 20, 15),
        (LIST_, "returning", "1.1", "XA", 50, 200, 12, 9), (ADACT, "returning", "1.1", "XA", 10, 30, 5, 4)]
# … ad impressions (class, format, unit, nvr, version, country, source, events, users) …
ADS = [(MAIN, "Banner", "unit_a", "new", "1.0", "XA", "src_a", 15, 5),
       (MAIN, "Banner", "unit_a", "returning", "1.1", "XB", "src_a", 25, 9),
       (LIST_, "Banner", "unit_a", "returning", "1.1", "XA", "src_b", 20, 7),
       (ADACT, "Interstitial", "unit_b", "returning", "1.1", "XA", "src_a", 10, 6)]
# … other events (class, event, n) and exposure (class, ms)
EVS = [(MAIN, "ad_click", 3), (ADACT, "ad_reward", 2), (MAIN, "inter_shown", 5), (LIST_, "banner_load_fail", 4),
       (MAIN, "screen_view", 100), (MAIN, "my_event", 50)]
EXPO = [(MAIN, 9000), (LIST_, 4000)]
# … revenue per day (class, total, ad revenue: GA4's decimals)
REVS = [(MAIN, 0.75, 0.75), (LIST_, 0.25, 0.25), (ADACT, 1.5, 1.25)]
VCOL = {gs.SC: 0, gs.PP: 0, gs.NVR: 1, gs.VER: 2, gs.CTY: 3}
VMET = {"screenPageViews": 4, "userEngagementDuration": 5, "sessions": 6, "activeUsers": 7}
ACOL = {gs.SC: 0, gs.PP: 0, gs.FMT: 1, gs.UNIT: 2, gs.NVR: 3, gs.VER: 4, gs.CTY: 5, gs.SRC: 6}
AMET = {"eventCount": 7, "activeUsers": 8}
Q = namedtuple("Q", "dims mets event events a b")


def _scr(q):
    """The screen dimension a call asks: the page path (ads, clicks, own events, exposure) or the class (views,
    users, the layers), else None."""
    return gs.PP if gs.PP in q.dims else gs.SC if gs.SC in q.dims else None


class Model:
    """The made-up GA4 behind both fakes: rows for any ask, `hook(q, rows) → (rows, metadata)` to bend an answer."""

    def __init__(self, hook=None, events_per_day=1000, no_ads=()):
        self.hook, self.events_per_day, self.no_ads = hook, events_per_day, set(no_ads)

    def table(self, day, mets, event, events):
        if event == gs.IMP:
            return ([] if day.isoformat() in self.no_ads else ADS), ACOL, AMET
        if events:
            return [r for r in EVS if r[1] in events], {gs.SC: 0, gs.PP: 0, gs.EVN: 1}, {"eventCount": 2}
        if "adUnitExposure" in mets:
            return EXPO, {gs.SC: 0, gs.PP: 0}, {"adUnitExposure": 1}
        if "totalRevenue" in mets:
            return REVS, {gs.SC: 0, gs.PP: 0}, {"totalRevenue": 1, "totalAdRevenue": 2}
        if list(mets) == ["eventCount"]:
            ads = 0 if day.isoformat() in self.no_ads else sum(r[7] for r in ADS)
            rest = self.events_per_day - ads - sum(r[2] for r in EVS)
            return EVS + [(MAIN, "ad_impression", ads), (MAIN, "session_start", rest)], {gs.SC: 0, gs.PP: 0,
                                                                                         gs.EVN: 1}, \
                {"eventCount": 2}
        return VIEW, VCOL, VMET

    def rows(self, q):
        out = {}
        d = q.a
        while d <= q.b:
            tab, cols, mcol = self.table(d, q.mets, q.event, q.events)
            for r in tab:
                k = tuple(([d.strftime("%Y%m%d")] if "date" in q.dims else [])
                          + [r[cols[x]] for x in q.dims if x != "date"])
                v = out.setdefault(k, [0] * len(q.mets))
                for i, m in enumerate(q.mets):
                    v[i] += r[mcol[m]]
            d += timedelta(days=1)
        rows = [dict(zip(q.dims, k), **dict(zip(q.mets, v))) for k, v in sorted(out.items())]
        meta = {}
        if self.hook:
            rows, meta = self.hook(q, rows)
        return rows, meta


def _q(body, event, events):
    dims = [x["name"] for x in body["dimensions"]]
    mets = [x["name"] for x in body["metrics"]]
    r = body["dateRanges"][0]
    return Q(tuple(dims), tuple(mets), event, tuple(events) if events else None,
             date.fromisoformat(r["startDate"]), date.fromisoformat(r["endDate"]))


class FakeGA:
    """report_all as ga4.Ga4App's (+ last_metas / last_pages / last_row_count); stop_after → gf.Stop("calls");
    tick: seconds the shared clock moves per call."""

    def __init__(self, model=None, stop_after=None, clock=None, tick=0.0):
        self.model, self.stop_after = model or Model(), stop_after
        self.calls, self.tok, self.asked = 0, 0, []
        self.last_metas, self.last_pages, self.last_row_count = [{}], 1, 0
        self.clock, self.tick, self.over = clock if clock is not None else [0.0], tick, None

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        self.tok += 1
        self.clock[0] += self.tick
        q = _q(body, event, events)
        self.asked.append(q)
        rows, meta = self.model.rows(q)
        self.last_metas, self.last_pages = [meta], 1
        self.last_row_count = meta.pop("_rc", len(rows)) if isinstance(meta, dict) else len(rows)
        return rows


def _it(hs=date(2026, 10, 1), aid=AID, pid="111"):
    return {"a": {"app_id": aid, "package": "com.example." + aid[-2:]}, "r": {"property_id": pid, "stream_id": "222"},
            "tz": "UTC", "hs": hs, "st": {}, "tok": "tok"}


def _job(tmp_path, ga=None, hs=date(2026, 10, 1), clock=None):
    ga = ga or FakeGA()
    return gs.Job(str(tmp_path / "data" / gs.DIR), _it(hs), NOW, ga, clock or (lambda: ga.clock[0]))


def _rid(q):
    """Which read (and shape) a call was."""
    dims = [x for x in q.dims if x != "date"]
    if q.mets == gs.VM and not dims:
        return "TV"
    if q.event == gs.IMP and dims == [gs.FMT] and "date" in q.dims:
        return "TA"
    if q.mets == gs.EC and not dims and not q.event and not q.events:
        return "TE0"
    if dims == [gs.EVN] and "date" not in q.dims:
        return "events"
    for rid, R in gs.READS.items():
        if rid == "t":
            continue
        if R.get("own") and list(R["own"][0]) == dims and R["own"][1] == q.mets and \
                (q.events == R.get("evs") or (rid == "x" and q.events and q.events != gs.CLICKS)):
            return rid + ":own"
        for s, sd in R["shapes"]:
            if list(sd) == dims and tuple(R["mets"]) == q.mets and q.event == R.get("ev") and \
                    (R.get("evs") is None or q.events == R.get("evs") or (rid == "x" and q.events != gs.CLICKS)):
                return rid + ":" + s
    return "?"


def _t_days(job, days):
    gs.fill(job, "t", [d.isoformat() if isinstance(d, date) else d for d in days], True)


def _final(tmp_path, grp, month):
    with gzip.open(gs.month_path(str(tmp_path / "data" / gs.DIR), KEY, grp, month), "rt", encoding="utf-8") as f:
        return json.load(f)["days"]


# ── the reads ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_every_read_asks_its_dimensions_metrics_and_event_filter(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    job.meta["events"] = {"at": gu._now_iso(NOW), "names": ["inter_shown"]}
    _t_days(job, [FE])
    assert [(q.dims, q.mets, q.event, q.events) for q in ga.asked] == [
        (("date",), ("screenPageViews", "userEngagementDuration"), None, None),
        (("date", "adFormat"), ("eventCount",), "ad_impression", None),
        (("date",), ("eventCount",), None, None)]
    want = {
        ("v", "c"): ([("date", "unifiedScreenClass")], ("screenPageViews", "userEngagementDuration"), None, None),
        ("w", "u"): ([("date", "adFormat", "adUnitName")], ("eventCount",), "ad_impression", None),
        ("a", "fu"): ([("date", "unifiedPagePathScreen", "adFormat", "adUnitName")], ("eventCount",), "ad_impression",
                      None),
        ("a", "f"): ([("date", "unifiedPagePathScreen", "adFormat")], ("eventCount",), "ad_impression", None),
        ("a", "c"): ([("date", "unifiedPagePathScreen")], ("eventCount",), "ad_impression", None),
        ("nV", "c"): ([("date", "newVsReturning", "unifiedScreenClass")], ("screenPageViews",), None, None),
        ("rV", "a"): ([("date", "appVersion")], ("screenPageViews",), None, None),
        ("cA", "cf"): ([("date", "countryId", "unifiedScreenClass", "adFormat")], ("eventCount",), "ad_impression",
                       None),
        ("nA", "f"): ([("date", "newVsReturning", "adFormat")], ("eventCount",), "ad_impression", None),
        ("rA", "a"): ([("date", "appVersion")], ("eventCount",), "ad_impression", None),
        ("k", "c"): ([("date", "eventName"), ("date", "unifiedPagePathScreen", "eventName")], ("eventCount",), None,
                     ("ad_click", "ad_reward")),
        ("e", "c"): ([("date",), ("date", "unifiedPagePathScreen")], ("adUnitExposure",), None, None),
        ("uV", "c"): ([("date", "unifiedScreenClass")], ("sessions", "activeUsers"), None, None),
        ("uA", "c"): ([("date", "unifiedScreenClass")], ("activeUsers",), "ad_impression", None),
        ("uA", "a"): ([("date",)], ("activeUsers",), "ad_impression", None),
        ("s", "fs"): ([("date", "adFormat", "adSourceName")], ("eventCount",), "ad_impression", None),
        ("x", "c"): ([("date", "eventName"), ("date", "unifiedPagePathScreen", "eventName")], ("eventCount",), None,
                     ("inter_shown",)),
    }
    for (rid, s), (dims, mets, ev, evs) in want.items():
        n = len(ga.asked)
        recs, clean, _ = gs.read_chunk(job, rid, s, FE, FE)
        asked = ga.asked[n:]
        assert [q.dims for q in asked] == dims, (rid, s)
        assert all(q.mets == mets and q.event == ev and q.events == evs for q in asked[-1:]), (rid, s)
        assert clean and recs[FE.isoformat()]["st"] == "w" and recs[FE.isoformat()]["g"] == s, (rid, s)
    # the rows as stored (positional, sorted, ints)
    d = FE.isoformat()
    assert gs.read_chunk(job, "v", "c", FE, FE)[0][d]["r"] == [[LIST_, 50, 200], [MAIN, 100, 500], [ADACT, 10, 30]]
    assert gs.read_chunk(job, "a", "fu", FE, FE)[0][d]["r"] == [[LIST_, "Banner", "unit_a", 20],
                                                                [MAIN, "Banner", "unit_a", 40],
                                                                [ADACT, "Interstitial", "unit_b", 10]]
    k = gs.read_chunk(job, "k", "c", FE, FE)[0][d]
    assert k["t"] == [["ad_click", 3], ["ad_reward", 2]] and k["r"] == [[MAIN, "ad_click", 3], [ADACT, "ad_reward", 2]]
    assert gs.read_chunk(job, "e", "c", FE, FE)[0][d]["t"] == 13000
    assert gs.read_chunk(job, "x", "c", FE, FE)[0][d]["ev"] == ["inter_shown"]
    assert gs.read_chunk(job, "uA", "a", FE, FE)[0][d]["r"] == [[27]]
    t = job.truth(d)
    assert t == {"st": "w", "g": "t", "fv": 1, "v": [160, 730], "a": [["Banner", 60], ["Interstitial", 10]], "ev": 1000,
                 "tried": ["t"]}
    assert gs.AD_EVENT_RE.pattern == probe.AD_EVENT_RE.pattern and gs.STD_AD_EVENTS == probe.STD_AD_EVENTS


def _hook_rows(fn):
    def hook(q, rows):
        return fn(q, rows)
    return hook


def test_whole_partial_silent_loss_sampled_cut_and_thresholded(tmp_path):
    d = FE.isoformat()

    def run(fn, rid="a", s="fu", a=FE, b=FE):
        job = _job(tmp_path / str(len(os.listdir(tmp_path)) if os.path.exists(tmp_path) else "0"), FakeGA())
        _t_days(job, gs._days(a, b))
        job.ga.model.hook = fn
        return gs.read_chunk(job, rid, s, a, b)

    fold = lambda q, rows: (rows + [dict(rows[0], **{_scr(q): "(other)", "eventCount": 10})] if q.event and
                            _scr(q) else rows, {})
    # a fold row inside the tie: the main screen loses 1 to "(other)": partial at 1/70 > 0.5 %, the rows and share kept
    def moved(q, rows):
        if q.event != gs.IMP or not _scr(q):
            return rows, {}
        rows = [dict(r) for r in rows]
        rows[-1]["eventCount"] -= 5
        return rows + [dict(rows[-1], **{_scr(q): "(other)", "eventCount": 5})], {}
    recs, clean, _ = run(moved)
    assert clean and recs[d]["st"] == "p" and recs[d]["f"] == round(5 / 70, 4) and len(recs[d]["r"]) == 4
    # silent loss: a screen's row missing, no fold row → "o", coverage kept, no rows
    drop = lambda q, rows: ([r for r in rows if r.get(_scr(q)) != LIST_] if q.event else rows,
                            {"dataLossFromOtherRow": True})
    recs, clean, _ = run(drop)
    assert clean and recs[d] == {"g": "fu", "fv": 1, "st": "o", "cov": round(50 / 70, 4), "loss": 1, "pp": 1}
    # reads without a truth (uV, uA): GA4's loss flag alone makes the day not whole (no rows), and uA's cascade then
    # tries its coarser shape "a"
    for rid in ("uV", "uA"):
        recs, _, _ = run(drop if rid == "uA" else lambda q, rows: (
            [r for r in rows if r.get(_scr(q)) != LIST_], {"dataLossFromOtherRow": True}), rid, "c")
        assert recs[d] == {"g": "c", "fv": 1, "st": "o", "cov": None, "loss": 1}, rid
    job = _job(tmp_path / "ua", FakeGA())
    _t_days(job, [FE])
    job.ga.model.hook = lambda q, rows: (rows, {"dataLossFromOtherRow": True} if _scr(q) else {})
    n = len(job.ga.asked)
    gs.fill(job, "uA", [d], True)
    assert [_rid(q) for q in job.ga.asked[n:]] == ["uA:c", "uA:a"]
    rec = _final(tmp_path / "ua", "small", "2026-10")[d]["uA"]
    assert rec["st"] == "w" and rec["g"] == "a" and rec["tried"] == ["c", "a"] and rec["r"] == [[27]]
    # a k / x / e own truth that lost rows ties nothing: the read is not whole, no split asked
    job = _job(tmp_path / "own", FakeGA())
    _t_days(job, [FE])
    job.ga.model.hook = lambda q, rows: (rows, {"dataLossFromOtherRow": True} if q.events == gs.CLICKS else {})
    n = len(job.ga.asked)
    recs, clean, _ = gs.read_chunk(job, "k", "c", FE, FE)
    assert not clean and recs[d] == {"st": "o", "cov": None, "loss": 1, "g": "c", "fv": 1, "pp": 1}
    assert [_rid(q) for q in job.ga.asked[n:]] == ["k:own"]
    # 10 events over a truth of 70: never "whole" either (1 over would be inside the 2 % / 1 tie)
    recs, _, _ = run(fold)
    assert recs[d]["st"] == "o"
    # sampled: GA4's sample share, no rows, no coverage
    smp = lambda q, rows: (rows, {"samplingMetadatas": [{"samplesReadCount": "25", "samplingSpaceSize": "100"}]}
                           if q.event else {})
    recs, clean, info = run(smp)
    assert not clean and info["s"] and recs[d] == {"g": "fu", "fv": 1, "st": "s", "smp": 0.25, "pp": 1}
    # cut: fewer rows than GA4's row count
    cut = lambda q, rows: (rows[:-1], {"_rc": len(rows)}) if q.event else (rows, {})
    recs, clean, _ = run(cut)
    assert not clean and recs[d]["st"] == "o" and recs[d]["trunc"] == 1 and "r" not in recs[d]
    # thresholded: users → "t" (no rows); additive → "p" with the note, rows kept
    thr = lambda q, rows: (rows, {"subjectToThresholding": True})
    recs, _, _ = run(thr, "uV", "c")
    assert recs[d] == {"g": "c", "fv": 1, "st": "t"}
    recs, _, _ = run(thr, "v", "c")
    assert recs[d]["st"] == "p" and recs[d]["thr"] == 1 and len(recs[d]["r"]) == 3
    # an undated row: in a multi-day read the read is not whole; in a one-day read it is that day's fold row
    und = lambda q, rows: (rows + [{"date": "(other)", gs.SC: "(other)", "screenPageViews": 0,
                                    "userEngagementDuration": 0}] if gs.SC in q.dims else rows, {})
    recs, clean, _ = run(und, "v", "c", FE - timedelta(days=1), FE)
    assert not clean and all(r["st"] == "o" for r in recs.values())
    recs, clean, _ = run(und, "v", "c")
    assert clean and recs[d]["st"] == "w" and [gs.FOLD and r for r in recs[d]["r"] if r[0] == "(other)"]


def test_tie_with_a_folded_format_key():
    # the fold's own format is "(other)": its events cover the formats' shortfall
    want = {"Banner": 60, "Interstitial": 10}
    rows = [["a", "Banner", 50], ["b", "Interstitial", 10], ["(other)", "(other)", 10]]
    assert gs._tie(rows, 1, 2, want)
    assert not gs._tie([["a", "Banner", 50], ["b", "Interstitial", 10]], 1, 2, want)          # 10 lost
    assert not gs._tie([["a", "Banner", 80], ["(other)", "(other)", -10]], 1, 2, want)         # a format over its truth
    assert gs._tie([["a", "Banner", 59]], None, 2, {"": 60})                                   # within 2 % / 1


# ── the grain ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_chunk_ladder_halves_on_a_bad_multi_day_read_and_doubles_after_two_whole_ones(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    days = gs._days(FE - timedelta(days=13), FE)
    _t_days(job, days)
    # GA4 loses a screen's ads in any read of more than 3 days at the finest shape
    ga.model.hook = lambda q, rows: (([r for r in rows if r.get(_scr(q)) != LIST_]
                                      if q.event and gs.UNIT in q.dims and _scr(q) and (q.b - q.a).days >= 3
                                      else rows), {})
    n = len(ga.asked)
    gs.fill(job, "a", list(reversed(days)), True)
    sizes = [(q.b - q.a).days + 1 for q in ga.asked[n:]]
    assert sizes == [14, 7, 3, 3, 7, 3, 3, 2]
    rd = job.rd("a")
    assert rd["d"]["fu"] == 7 and rd["streak"]["fu"] == 0
    stored = _final(tmp_path, "core", "2026-10")
    assert all(stored[d]["a"]["st"] == "w" and stored[d]["a"]["g"] == "fu" for d in days)
    # a recent window never changes the grain
    assert rd["gate"]["fu"] == {"ok": 3000}                 # whole reads only: never the 14 / 7 days that lost rows
    rd["d"]["fu"] = 14
    job.recent = {}
    w = gs._days(job.recent_start, TODAY)
    gs.fill(job, "t", w, False)
    gs.fill(job, "a", w, False)
    assert rd["d"]["fu"] == 14 and rd["dead"] == {} and rd["gate"] == {"fu": {"ok": 3000}}
    assert all(job.recent[d]["a"]["st"] == "w" for d in w)


def test_coarser_shapes_per_day_and_the_shapes_tried_saved_before_a_stop(tmp_path):
    d = FE.isoformat()
    sampled = {"samplingMetadatas": [{"samplesReadCount": "1", "samplingSpaceSize": "4"}]}
    # fu and f sampled, c whole
    hook = lambda q, rows: (rows, sampled if q.event and _scr(q) and len(q.dims) > 2 else {})
    ga = FakeGA(Model())
    job = _job(tmp_path, ga)
    _t_days(job, [FE])
    ga.model.hook, ga.stop_after = hook, ga.calls + 1          # the fu read goes out, then the run stops
    with pytest.raises(gf.Stop):
        gs.fill(job, "a", [d], True)
    assert job.rd("a")["pend"][d]["tried"] == ["fu"] and job.rd("a")["pend"][d]["st"] == "s"
    on_disk = gs._read_gz(gs.meta_path(job.root, KEY))
    assert on_disk["reads"]["a"]["pend"][d]["tried"] == ["fu"]                  # saved at once
    # the next run: a new job from the files, fu never sent again
    ga2 = FakeGA(Model(hook))
    job2 = gs.Job(job.root, _it(), NOW, ga2, lambda: 0.0)
    assert job2.needs("a", d)
    gs.fill(job2, "a", [d], True)
    assert [_rid(q) for q in ga2.asked] == ["a:f", "a:c"]
    rec = _final(tmp_path, "core", "2026-10")[d]["a"]
    assert rec["g"] == "c" and rec["tried"] == ["fu", "f", "c"] and rec["st"] == "w" and rec["r"] == [
        [LIST_, 20], [MAIN, 40], [ADACT, 10]]
    assert d not in job2.rd("a")["pend"] and not job2.needs("a", d)


def test_a_partial_split_over_two_percent_gets_the_coarser_shape_beside_it(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    d = FE.isoformat()
    _t_days(job, [FE])

    def hook(q, rows):
        if q.event == gs.IMP and gs.SC in q.dims and gs.CTY in q.dims:
            rows = [dict(r) for r in rows]
            rows[0][gs.SC] = "(other)"                      # 15 of 70 folded into "(other)"
        return rows, {}
    ga.model.hook = hook
    gs.fill(job, "cA", [d], True)
    rec = _final(tmp_path, "cc", "2026-10")[d]["cA"]
    assert rec["st"] == "p" and rec["g"] == "cf" and rec["f"] > gs.FOLD_CO
    assert rec["co"]["g"] == "f" and rec["co"]["st"] == "w" and rec["co"]["r"] == [
        ["XA", "Banner", 35], ["XA", "Interstitial", 10], ["XB", "Banner", 25]]


def test_the_coarser_shape_goes_through_the_ladder_and_a_day_not_whole_is_retried_next_run(tmp_path):
    days = gs._days(FE - timedelta(days=2), FE)
    flag = {"bad": True}

    def hook(q, rows):
        if q.event != gs.IMP or gs.CTY not in q.dims:
            return rows, {}
        if gs.SC in q.dims:                                 # cf: 15 of 70 folded every day ("p", over 2 %)
            rows = [dict(r, **({gs.SC: "(other)"} if r[gs.SC] == MAIN and r[gs.CTY] == "XA" else {})) for r in rows]
            return rows, {}
        if (q.b - q.a).days >= 1 or (q.a == FE and flag["bad"]):     # f: sampled over 2+ days, and FE alone
            return rows, {"samplingMetadatas": [{"samplesReadCount": "1", "samplingSpaceSize": "3"}]}
        return rows, {}
    ga = FakeGA(Model(hook))
    job = _job(tmp_path, ga)
    _t_days(job, days)
    n = len(ga.asked)
    gs.fill(job, "cA", list(reversed(days)), True)
    got = [(_rid(q), (q.b - q.a).days + 1) for q in ga.asked[n:]]
    assert got == [("cA:cf", 3), ("cA:f", 3), ("cA:f", 1), ("cA:f", 1), ("cA:f", 1)]    # halved, as any read
    cc = _final(tmp_path, "cc", "2026-10")
    for d in days[:2]:
        assert cc[d]["cA"]["st"] == "p" and cc[d]["cA"]["co"]["st"] == "w" and cc[d]["cA"]["co"]["g"] == "f"
    rec = cc[FE.isoformat()]["cA"]
    assert rec["st"] == "p" and rec["co"] == {"st": "s", "g": "f", "smp": round(1 / 3, 4)}
    rd = job.rd("cA")
    assert rd["cop"] == {FE.isoformat(): ["f", 1]} and rd["d"]["f"] == 3     # (1, then two whole: up to 3)
    assert rd["gate"]["f"] == {"bad": 1000, "ok": 1000}     # the shape's own gate learned from these final reads
    n = len(ga.asked)
    gs.fill(job, "cA", [], True)                            # the same run: never sent twice
    assert ga.asked[n:] == []
    on_disk = gs._read_gz(gs.meta_path(job.root, KEY))["reads"]["cA"]["cop"]
    assert on_disk == {FE.isoformat(): ["f", 1]}
    # the next run retries it (whole now): co whole, nothing owed
    flag["bad"] = False
    ga2 = FakeGA(Model(hook))
    job2 = gs.Job(job.root, _it(), NOW, ga2, lambda: 0.0)
    gs.fill(job2, "cA", [], True)
    assert [_rid(q) for q in ga2.asked] == ["cA:f"]
    assert _final(tmp_path, "cc", "2026-10")[FE.isoformat()]["cA"]["co"]["st"] == "w" and job2.rd("cA")["cop"] == {}
    # never more than DEAD_AFTER tries (one a run)
    flag["bad"] = True
    gs.Store(job.root, KEY, {}).put({FE.isoformat(): {"cA": dict(rec, co={"st": "s", "g": "f"})}})
    for i in range(gs.DEAD_AFTER + 2):
        jb = gs.Job(job.root, _it(), NOW, FakeGA(Model(hook)), lambda: 0.0)
        if i == 0:
            jb.rd("cA")["cop"] = {FE.isoformat(): ["f", 1]}
        gs.fill(jb, "cA", [], True)
        jb.store.save_meta()
        if i < gs.DEAD_AFTER - 1:
            assert jb.ga.calls == 1 and jb.rd("cA")["cop"].get(FE.isoformat()) in (["f", 2], None), i
        else:
            assert jb.ga.calls == 0 and jb.rd("cA")["cop"] == {}, i


def test_a_stop_before_the_coarser_read_keeps_it_owed(tmp_path):
    def hook(q, rows):
        if q.event == gs.IMP and gs.CTY in q.dims and gs.SC in q.dims:
            rows = [dict(r, **({gs.SC: "(other)"} if r[gs.SC] == MAIN and r[gs.CTY] == "XA" else {})) for r in rows]
        return rows, {}
    ga = FakeGA(Model(hook))
    job = _job(tmp_path, ga)
    days = gs._days(FE - timedelta(days=2), FE)
    _t_days(job, days)
    ga.stop_after = ga.calls + 1                            # the cf read goes out, then the run stops
    with pytest.raises(gf.Stop):
        gs.fill(job, "cA", list(reversed(days)), True)
    assert gs._read_gz(gs.meta_path(job.root, KEY))["reads"]["cA"]["cop"] == {d: ["f", 0] for d in days}
    ga2 = FakeGA(Model(hook))
    job2 = gs.Job(job.root, _it(), NOW, ga2, lambda: 0.0)
    job2.rd("cA")["gate"]["f"] = {"bad": 2500, "ok": 1000}  # 3 days (3,000 events) would be sampled: 1 day a call
    gs.fill(job2, "cA", [], True)
    assert [(_rid(q), (q.b - q.a).days + 1) for q in ga2.asked] == [("cA:f", 1)] * 3
    cc = _final(tmp_path, "cc", "2026-10")
    assert all(cc[d]["cA"]["co"]["st"] == "w" for d in days) and job2.rd("cA")["cop"] == {}


def test_the_volume_gate_skips_a_shape_on_a_big_day_and_learns_from_final_reads(tmp_path):
    ga = FakeGA(Model(events_per_day=1000))
    job = _job(tmp_path, ga)
    days = gs._days(FE - timedelta(days=2), FE)
    _t_days(job, days)
    rd = job.rd("a")
    rd["gate"]["fu"] = {"bad": 900}                         # GA4 sampled fu at 900 events before
    n = len(ga.asked)
    gs.fill(job, "a", list(reversed(days)), True)
    assert [_rid(q) for q in ga.asked[n:]] == ["a:f"] and job.c["gated"] == 3
    rec = _final(tmp_path, "core", "2026-10")[FE.isoformat()]["a"]
    assert rec["g"] == "f" and rec["tried"] == ["f"]
    assert rd["gate"]["f"] == {"ok": 3000}                  # a whole 3-day read at f: 3,000 events seen whole
    # a sampled final read records its volume as "bad"; a range at that volume is then read in fewer days
    job2 = _job(tmp_path / "b", FakeGA(Model(events_per_day=1000)))
    _t_days(job2, days)
    job2.ga.model.hook = lambda q, rows: (rows, {"samplingMetadatas": [{"samplesReadCount": "1", "samplingSpaceSize": "9"}]}
                                          if q.event and gs.UNIT in q.dims and (q.b - q.a).days >= 2 else {})
    n = len(job2.ga.asked)
    gs.fill(job2, "w", list(reversed(days)), True)
    assert job2.rd("w")["gate"]["u"] == {"bad": 3000, "ok": 1000}
    assert [(q.b - q.a).days + 1 for q in job2.ga.asked[n:]] == [3, 1, 1, 1]
    assert gs._gated({"bad": 3000, "ok": 1000}, 3000) and not gs._gated({"bad": 3000, "ok": 1000}, 2000)
    assert not gs._gated({"bad": 3000, "ok": 5000}, 4000) and not gs._gated({}, 10 ** 9)


def test_a_dead_shape_is_skipped_until_14_more_days_were_read_then_tried_once(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga, hs=date(2026, 9, 1))
    days = list(reversed(gs._days(FE - timedelta(days=25), FE)))
    _t_days(job, days)
    ga.model.hook = lambda q, rows: (rows, {"samplingMetadatas": [{"samplesReadCount": "1", "samplingSpaceSize": "5"}]}
                                     if q.event and gs.UNIT in q.dims and _scr(q) else {})
    rd = job.rd("a")
    rd["d"]["fu"] = 1
    n = len(ga.asked)
    gs.fill(job, "a", days[:3], True)                       # 3 final days with fu failing → dead
    assert [_rid(q) for q in ga.asked[n:]] == ["a:fu", "a:fu", "a:fu", "a:f"]
    assert rd["dead"]["fu"]["n"] == 3 and rd["dead"]["fu"]["until"] == 0 + gs.DEAD_RETRY and rd["read"] == 3
    n = len(ga.asked)
    gs.fill(job, "a", days[3:16], True)                     # skipped: no fu call
    assert {_rid(q) for q in ga.asked[n:]} == {"a:f"} and job.c["dead"] == 13
    assert rd["read"] == 16 >= rd["dead"]["fu"]["until"]
    n = len(ga.asked)
    gs.fill(job, "a", days[16:20], True)                    # the retry: once, on one final day — still bad
    assert [_rid(q) for q in ga.asked[n:]].count("a:fu") == 1
    assert rd["dead"]["fu"]["until"] == 16 + gs.DEAD_RETRY and rd["read"] == 20
    # whole again at the next retry → alive
    rd["read"] = rd["dead"]["fu"]["until"]
    ga.model.hook = None
    gs.fill(job, "a", days[20:22], True)
    assert "fu" not in rd["dead"]
    assert _final(tmp_path, "core", "2026-10")[days[20]]["a"]["g"] == "fu"        # the retry day


SAMPLED = {"samplingMetadatas": [{"samplesReadCount": "1", "samplingSpaceSize": "4"}]}


def _a_shape(q):
    """Which shape of the "a" read a call was (None: another read)."""
    return {3: "fu", 2: "f", 1: "c"}[len(q.dims) - 1] if q.event == gs.IMP and gs.PP in q.dims else None


def test_a_final_day_every_shape_is_dead_for_is_still_asked_its_coarsest_shape(tmp_path):
    # no "skip" record stored as final (never read again): the finer shapes are skipped (dead), the coarsest is asked
    # — and its answer (sampled) is the day's record; the dead rule counts the finer skips, the gate learns from the call
    ga = FakeGA(Model(lambda q, rows: (rows, SAMPLED if _a_shape(q) else {})))
    job = _job(tmp_path, ga)
    d = FE.isoformat()
    _t_days(job, [FE])
    rd = job.rd("a")
    for s in ("fu", "f", "c"):
        rd["dead"][s] = {"n": 3, "st": "s", "until": gs.DEAD_RETRY}     # its one retry not due (nothing read yet)
    n = len(ga.asked)
    gs.fill(job, "a", [d], True)
    assert [(_rid(q), q.a, q.b) for q in ga.asked[n:]] == [("a:c", FE, FE)] and job.c["dead"] == 2
    assert _final(tmp_path, "core", "2026-10")[d]["a"] == {"g": "c", "fv": 1, "st": "s", "smp": 0.25, "tried": ["c"],
                                                          "pp": 1}
    assert rd["gate"]["c"] == {"bad": 1000} and rd["dead"]["c"]["n"] == 4 and rd["read"] == 1 and rd["pend"] == {}
    assert not job.needs("a", d)


def test_a_dead_coarsest_shape_is_read_at_its_grain_never_a_day_at_a_time(tmp_path):
    # every shape dead, GA4 whole at c: the 3 final days go out in ONE read of the coarsest (its grain), never 3
    # one-day reads; the whole answer revives it; the finer shapes stay dead (their own retry brings them back)
    ga = FakeGA()
    job = _job(tmp_path, ga)
    days = gs._days(FE - timedelta(days=2), FE)
    _t_days(job, days)
    rd = job.rd("a")
    for s in ("fu", "f", "c"):
        rd["dead"][s] = {"n": 3, "st": "s", "until": gs.DEAD_RETRY}
    n = len(ga.asked)
    gs.fill(job, "a", list(reversed(days)), True)
    assert [(_rid(q), q.a, q.b) for q in ga.asked[n:]] == [("a:c", FE - timedelta(days=2), FE)]
    core = _final(tmp_path, "core", "2026-10")
    assert all(core[d]["a"]["g"] == "c" and core[d]["a"]["st"] == "w" and core[d]["a"]["tried"] == ["c"] for d in days)
    assert set(rd["dead"]) == {"fu", "f"} and job.c["dead"] == 6 and rd["pend"] == {}


def test_a_dead_shapes_one_day_retry_never_changes_its_grain(tmp_path):
    # fu dead with its retry due: one day of it goes out (whole: alive again) — its grain stays what it was
    ga = FakeGA()
    job = _job(tmp_path, ga)
    days = gs._days(FE - timedelta(days=2), FE)
    _t_days(job, days)
    rd = job.rd("a")
    rd["d"]["fu"], rd["streak"]["fu"] = 14, 1
    rd["dead"]["fu"] = {"n": 3, "st": "s", "until": 0}
    n = len(ga.asked)
    gs.fill(job, "a", list(reversed(days)), True)
    asked = [(_rid(q), q.a, q.b) for q in ga.asked[n:]]
    assert asked[0] == ("a:fu", FE, FE) and "fu" not in rd["dead"]
    assert rd["d"]["fu"] == 14 and rd["streak"]["fu"] == 1


def test_a_gated_final_day_is_still_asked_its_coarsest_and_the_gate_learns_from_it(tmp_path):
    # GA4 sampled every shape at 500 events before and both days have 1,000: the finer shapes skipped (gated), the
    # coarsest asked anyway — the ladder a day at a time (the volume) — whole, kept; the gate now knows c whole at 1,000
    ga = FakeGA()
    job = _job(tmp_path, ga)
    days = gs._days(FE - timedelta(days=1), FE)
    _t_days(job, days)
    rd = job.rd("a")
    for s in ("fu", "f", "c"):
        rd["gate"][s] = {"bad": 500}
    n = len(ga.asked)
    gs.fill(job, "a", list(reversed(days)), True)
    d0 = FE - timedelta(days=1)
    assert [(_rid(q), q.a, q.b) for q in ga.asked[n:]] == [("a:c", FE, FE), ("a:c", d0, d0)]
    core = _final(tmp_path, "core", "2026-10")
    assert all(core[d]["a"]["g"] == "c" and core[d]["a"]["tried"] == ["c"] and "skip" not in core[d]["a"]
               for d in days)
    assert job.c["gated"] == 4 and rd["gate"] == {"fu": {"bad": 500}, "f": {"bad": 500}, "c": {"bad": 500, "ok": 1000}}
    # w's one shape gated, GA4 sampled: one call, one day; the answer is the day's record
    ga.model.hook = lambda q, rows: (rows, SAMPLED if q.event == gs.IMP and gs.UNIT in q.dims else {})
    job.rd("w")["gate"]["u"] = {"bad": 500}
    n = len(ga.asked)
    gs.fill(job, "w", [FE.isoformat()], True)
    assert [(_rid(q), q.a, q.b) for q in ga.asked[n:]] == [("w:u", FE, FE)]
    assert _final(tmp_path, "core", "2026-10")[FE.isoformat()]["w"] == {"g": "u", "fv": 1, "st": "s", "smp": 0.25,
                                                                        "tried": ["u"]}


def test_a_stop_while_reading_the_coarsest_leaves_the_days_left_with_no_record(tmp_path):
    hook = lambda q, rows: (rows, SAMPLED if q.event == gs.IMP and gs.UNIT in q.dims else {})
    ga = FakeGA(Model(hook))
    job = _job(tmp_path, ga)
    days = gs._days(FE - timedelta(days=2), FE)
    _t_days(job, days)
    job.rd("w")["dead"]["u"] = {"n": 3, "st": "s", "until": gs.DEAD_RETRY}
    ga.stop_after = ga.calls + 1                            # the 3-day read goes out (sampled), then the run stops
    with pytest.raises(gf.Stop):
        gs.fill(job, "w", list(reversed(days)), True)
    core = _final(tmp_path, "core", "2026-10")
    assert all("w" not in core[d] for d in days)            # nothing stored as final, never a skip record
    assert job.rd("w")["pend"] == {}
    # the next run asks the days again (the stop came before the smaller grain was saved: the 3-day read once more,
    # then a day at a time) and stores GA4's answers
    ga2 = FakeGA(Model(hook))
    job2 = gs.Job(job.root, _it(), NOW, ga2, lambda: 0.0)
    gs.fill(job2, "w", [d for d in reversed(days) if job2.needs("w", d)], True)
    assert [(_rid(q), q.a, q.b) for q in ga2.asked] == [("w:u", FE - timedelta(days=2), FE)] + [
        ("w:u",) + (FE - timedelta(days=i),) * 2 for i in range(3)]
    core = _final(tmp_path, "core", "2026-10")
    assert all(core[d]["w"]["st"] == "s" and core[d]["w"]["tried"] == ["u"] and "skip" not in core[d]["w"]
               for d in days)


def test_a_coarser_shape_dead_or_gated_is_not_read_beside_a_grouped_day(tmp_path):
    # cA's cf folds 15 of 70 every day ("p", over 2 %) and f is gated at 1,000 events: its "co" is not asked (the day
    # keeps its own whole-enough record; "co" is only beside it) — the calls are what they were before 6 Nov
    def hook(q, rows):
        if q.event == gs.IMP and gs.SC in q.dims and gs.CTY in q.dims:
            rows = [dict(r, **({gs.SC: "(other)"} if r[gs.SC] == MAIN and r[gs.CTY] == "XA" else {})) for r in rows]
        return rows, {}
    ga = FakeGA(Model(hook))
    job = _job(tmp_path, ga)
    days = gs._days(FE - timedelta(days=1), FE)
    _t_days(job, days)
    rd = job.rd("cA")
    rd["gate"]["f"] = {"bad": 500}
    n = len(ga.asked)
    gs.fill(job, "cA", list(reversed(days)), True)
    assert [(_rid(q), (q.b - q.a).days + 1) for q in ga.asked[n:]] == [("cA:cf", 2)]
    cc = _final(tmp_path, "cc", "2026-10")
    assert all(cc[d]["cA"]["st"] == "p" and "co" not in cc[d]["cA"] for d in days) and rd["cop"] == {}


def test_days_without_ads_or_events_cost_the_ad_reads_nothing(tmp_path):
    quiet = {(FE - timedelta(days=i)).isoformat() for i in range(3)}
    ga = FakeGA(Model(no_ads=quiet))
    job = _job(tmp_path, ga)
    days = sorted(quiet, reverse=True)
    _t_days(job, days)
    n = len(ga.asked)
    for rid in ("w", "a", "nA", "rA", "cA", "uA", "s"):
        gs.fill(job, rid, days, True)
    assert ga.asked[n:] == []
    core = _final(tmp_path, "core", "2026-10")
    assert all(core[d]["a"] == {"st": "w", "g": "fu", "fv": 1, "r": []} for d in days)
    gs.fill(job, "x", days, True)                           # no event list: no call either
    assert ga.asked[n:] == [] and _final(tmp_path, "small", "2026-10")[days[0]]["x"] == {
        "st": "w", "ev": [], "t": [], "r": [], "fv": 1}
    # k: its own truth asked, the split only for days with clicks
    ga.model.hook = lambda q, rows: (([r for r in rows if r["date"] != days[0].replace("-", "")]
                                      if q.events == gs.CLICKS else rows), {})
    gs.fill(job, "k", days, True)
    assert [(_rid(q), q.a, q.b) for q in ga.asked[n:]] == [("k:own", FE - timedelta(days=2), FE),
                                                            ("k:c", FE - timedelta(days=2), FE - timedelta(days=1))]
    assert _final(tmp_path, "small", "2026-10")[days[0]]["k"]["r"] == []


def test_a_gained_event_name_reads_xs_history_again(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    job.meta["events"] = {"at": "2026-11-01T00:00:00Z", "names": ["inter_shown"]}
    rd = job.rd("x")
    rd.update(oldest="2026-10-01", top="2026-10-30", done=True)
    gs.discover(job)
    q = ga.asked[-1]
    assert q.dims == ("eventName",) and q.event is None and (q.a, q.b) == (FE - timedelta(days=27), FE)
    assert job.meta["events"] == {"at": gu._now_iso(NOW), "names": ["banner_load_fail", "inter_shown"],
                                  "seen": ["banner_load_fail", "inter_shown"]}
    assert "oldest" not in rd and "done" not in rd
    gs.discover(job)                                        # within a day: not asked again
    assert len(ga.asked) == 1
    # a stored x day with the old list needs a read; one with every name does not
    job.store.put({"2026-10-10": {"x": {"st": "w", "ev": ["inter_shown"], "fv": 1, "r": []}},
                   "2026-10-11": {"x": {"st": "w", "ev": ["banner_load_fail", "inter_shown"], "fv": 1, "r": []}}})
    assert job.needs("x", "2026-10-10") and not job.needs("x", "2026-10-11")


def test_a_name_that_drops_out_of_the_top_and_comes_back_is_not_new(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    # seen once before (both names); today's list has only one of them back: nothing new, x's history stays
    job.meta["events"] = {"at": "2026-11-01T00:00:00Z", "names": ["inter_shown"],
                          "seen": ["banner_load_fail", "inter_shown"]}
    rd = job.rd("x")
    rd.update(oldest="2026-10-01", top="2026-10-30", done=True)
    gs.discover(job)
    assert job.meta["events"]["names"] == ["banner_load_fail", "inter_shown"]
    assert job.meta["events"]["seen"] == ["banner_load_fail", "inter_shown"]
    assert rd["done"] and rd["oldest"] == "2026-10-01"


# ── pass 1: the gap fill, the recent window and its truth ───────────────────────────────────────────────────────────
def test_recent_splits_are_read_right_after_their_own_truth(tmp_path):
    ga = FakeGA(tick=200.0)                                 # each call 200 s: older than TRUTH_FRESH_SEC by the next
    job = _job(tmp_path, ga, clock=lambda: ga.clock[0])
    gs.step_recent(job)
    recent = [(i, _rid(q)) for i, q in enumerate(ga.asked) if q.b == TODAY]
    assert recent[0][1] == "TV" and {r for _, r in recent} >= {"v:c", "a:fu", "cA:cf", "x:own", "uA:c"}
    for i, rid in recent:
        if rid in ("TV", "TA", "TE0"):
            continue
        j = max(k for k, r in recent if r == "TE0" and k < i)
        assert i - j <= (2 if rid.endswith(":c") and rid[0] in "kexm" else 1), (i, rid)
    for rid in gs.ORDER:
        assert job.rd(rid)["recent_at"] == gu._now_iso(NOW) and job.rd(rid)["upto"] == FE.isoformat()
    rf = gs.load_recent(str(tmp_path / "data"), KEY)
    assert sorted(rf) == gs._days(job.recent_start, TODAY) and rf[TODAY.isoformat()]["v"]["st"] == "w"


def test_only_due_reads_fill_their_own_gap_then_their_recent_window(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    fresh, old = gu._now_iso(NOW - timedelta(hours=1)), gu._now_iso(NOW - timedelta(hours=4))
    for rid in gs.ORDER:
        job.rd(rid).update(recent_at=fresh, upto=FE.isoformat(), oldest="2026-10-01", done=True)
    job.rd("t")["upto"] = job.rd("v")["upto"] = (FE - timedelta(days=3)).isoformat()
    job.rd("v")["recent_at"] = old
    job.meta["events"] = {"at": gu._now_iso(NOW), "names": []}
    gs.step_recent(job)
    got = [(_rid(q), q.a, q.b) for q in ga.asked]
    gap, rec = (FE - timedelta(days=2), FE), (job.recent_start, TODAY)
    assert got == [("TV",) + gap, ("TA",) + gap, ("TE0",) + gap, ("TV",) + rec, ("TA",) + rec, ("TE0",) + rec,
                   ("v:c",) + gap, ("v:c",) + rec]
    assert job.rd("v")["upto"] == FE.isoformat() and job.rd("v")["recent_at"] == gu._now_iso(NOW)
    assert job.rd("a")["recent_at"] == fresh                # not due: untouched
    ga.asked.clear()
    gs.step_recent(job)                                     # nothing due now
    assert ga.asked == []


def test_a_recent_day_turning_final_moves_to_its_month_file(tmp_path):
    w = {"st": "w", "g": "c", "fv": 1, "r": [["a", 1, 1]]}
    o = {"st": "o", "g": "c", "fv": 1, "cov": 0.5}
    assert gs.merge_rec(None, w) is w and gs.merge_rec(o, w) is w and gs.merge_rec(w, o) is w
    assert gs.merge_rec(w, dict(w, rc=1)) is w              # a final read never gives way to one made while recent
    rc = dict(w, rc=1)
    assert gs.merge_rec(rc, o) is rc and gs.merge_rec(dict(o, rc=1), o) is o
    job = _job(tmp_path, FakeGA())
    d1, d2 = FE.isoformat(), (FE - timedelta(days=1)).isoformat()
    job.store.put({d1: {"v": o}, d2: {"v": w}})
    job.recent = {d1: {"v": w}, d2: {"v": o}, TODAY.isoformat(): {"v": w}}
    job.move_recent()
    core = _final(tmp_path, "core", "2026-10")
    assert core[d1]["v"] == dict(w, rc=1) and core[d2]["v"] == w
    assert sorted(job.recent) == [TODAY.isoformat()] and job.needs("v", d1) and not job.needs("v", d2)


def test_month_files_by_group_and_the_loaders(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    job.meta["events"] = {"at": gu._now_iso(NOW), "names": ["inter_shown"]}
    days = list(reversed(gs._days(date(2026, 9, 29), date(2026, 10, 2))))
    _t_days(job, days)
    for rid in gs.ORDER[1:]:
        gs.fill(job, rid, days, True)
    root = str(tmp_path / "data" / gs.DIR)
    assert sorted(os.listdir(os.path.join(root, KEY))) == sorted(
        "%s_%s.json.gz" % (g, m) for g in gs.GRPS for m in ("2026-09", "2026-10"))
    assert job.meta["months"] == {g: ["2026-09", "2026-10"] for g in gs.GRPS}
    job.store.save_meta()
    data = str(tmp_path / "data")
    assert gs.store_keys(data) == [KEY] and gs.load_meta(data, KEY)["app_id"] == AID
    got = list(gs.iter_months(data, KEY, "cc"))
    assert [m for m, _, _ in got] == ["2026-09", "2026-10"]
    with open(gs.month_path(root, KEY, "cc", "2026-09"), "rb") as f:
        assert got[0][1] == hashlib.sha1(f.read()).hexdigest()
    assert sorted(got[0][2]) == ["2026-09-29", "2026-09-30"] and set(got[0][2]["2026-09-29"]) == {"cV", "cA"}
    assert set(_final(tmp_path, "small", "2026-10")["2026-10-01"]) == {"k", "e", "uV", "uA", "s", "x", "nV", "nA"}
    assert set(_final(tmp_path, "ver", "2026-10")["2026-10-01"]) == {"rV", "rA"}
    assert set(_final(tmp_path, "core", "2026-10")["2026-10-01"]) == {"t", "v", "w", "a", "m"}
    assert gs.load_recent(data, KEY) == {} and gs.store_keys(str(tmp_path / "none")) == []


# ── pass 2 and the run ──────────────────────────────────────────────────────────────────────────────────────────────
def test_backfill_walks_newest_first_by_chunk_across_every_read(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga, hs=FE - timedelta(days=40))
    job.meta["events"] = {"at": gu._now_iso(NOW), "names": ["inter_shown"]}
    gs.backfill(job, FE - timedelta(days=gs.TARGET_DAYS - 1))
    first = [(_rid(q), q.b) for q in ga.asked[:6]]
    assert first == [("TV", FE), ("TA", FE), ("TE0", FE), ("v:c", FE), ("w:u", FE), ("a:fu", FE)]
    seg1 = [q for q in ga.asked if q.a >= FE - timedelta(days=30)]
    order = []
    for q in seg1:
        r = _rid(q).split(":")[0]
        if r in ("TV", "TA", "TE0"):
            r = "t"
        if not order or order[-1] != r:
            order.append(r)
    assert order == list(gs.ORDER)                          # t, then each read, before any older day
    assert all(job.rd(r)["done"] for r in gs.ORDER) and min(q.a for q in ga.asked) == FE - timedelta(days=40)
    n = len(ga.asked)
    gs.backfill(job, FE - timedelta(days=100))              # complete: nothing more
    assert len(ga.asked) == n


def _rewrite(path, fn):
    """A store file → fn(its dict) → written back (a store as written before this change)."""
    j = gs._read_gz(path)
    fn(j)
    gs.write_json_gz_stable(path, j)


def test_an_old_skip_record_in_the_builds_store_is_read_again_by_the_hourly_backfill(monkeypatch, tmp_path):
    # a final day stored as a skip before this change (nothing asked) is no answer: the build looks once for every
    # skip record and pass 2 asks GA4 for those days, wherever its cursor and "done" stand
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)                        # history start 2026-10-21
    asked = _http(monkeypatch, Model())
    data = str(tmp_path / "data")
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.refresh_all(cfg, data, [dict(a) for a in apps], NOW, clock=lambda: 0.0, budget=1000)
    assert out["apps"] == {AID: "fetched"}
    d, root = "2026-10-24", os.path.join(data, gs.DIR)
    p = gs.month_path(root, KEY, "core", "2026-10")
    _rewrite(p, lambda j: j["days"][d].update(w={"st": "s", "g": "u", "skip": "dead", "tried": [], "fv": 1}))
    _rewrite(gs.meta_path(root, KEY), lambda m: [rd.pop("redo", None) for rd in m["reads"].values()])
    assert all(r["done"] for r in gs.load_meta(data, KEY)["reads"].values())
    n = len(asked)
    out = gs.refresh_all(cfg, data, [dict(a) for a in apps], NOW + timedelta(hours=1), clock=lambda: 0.0)
    assert out["apps"] == {AID: "fetched"}
    assert [(_rid(q), q.a.isoformat(), q.b.isoformat()) for _, q in asked[n:] if "date" in q.dims] == [("w:u", d, d)]
    rec = gs._read_gz(p)["days"][d]["w"]
    assert rec["st"] == "w" and rec["tried"] == ["u"] and "skip" not in rec
    assert all(rd["redo"] == [] for rd in gs.load_meta(data, KEY)["reads"].values())


def _patch_routes(monkeypatch, apps):
    routes = {a["package"]: {"property_id": a["pid"], "stream_id": "2" + a["pid"], "owner": "o"} for a in apps}
    monkeypatch.setattr(gs.gu, "load_state", lambda d: {"routes": {"by_package": routes},
                                                        "tz": {a["pid"]: "UTC" for a in apps},
                                                        "fetch": {a["app_id"]: {"package": a["package"]}
                                                                  for a in apps}})
    monkeypatch.setattr(gs.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": "2026-10-21"})
    monkeypatch.setattr(gs.ga4, "access_token", lambda c, s, r: "tok")


def _http(monkeypatch, model, quota=None, fail=None, auth=None):
    """ga4._call answered from the model (the real App, report_all and paging run); quota(pid, n) → propertyQuota;
    fail(pid, n) → an exception to raise; auth(token) → an exception to raise for that bearer token. → the list of
    (property, Q) asked."""
    asked = []
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)

    def call(method, url, token, body=None, params=None):
        pid = url.split("properties/")[1].split(":")[0]
        n = sum(1 for p, _ in asked if p == pid)
        if auth:
            e = auth(token)
            if e:
                raise e
        if fail:
            e = fail(pid, n)
            if e:
                raise e
        flt = body.get("dimensionFilter", {}).get("andGroup", {}).get("expressions", [])
        ev = evs = None
        for x in flt:
            f = x["filter"]
            if f["fieldName"] == "eventName":
                if "stringFilter" in f:
                    ev = f["stringFilter"]["value"]
                else:
                    evs = f["inListFilter"]["values"]
        q = _q(body, ev, evs)
        asked.append((pid, q))
        rows, meta = model.rows(q)
        return {"dimensionHeaders": [{"name": d} for d in q.dims], "metricHeaders": [{"name": m} for m in q.mets],
                "rows": [{"dimensionValues": [{"value": r.get(d, "")} for d in q.dims],
                          "metricValues": [{"value": str(r[m])} for m in q.mets]} for r in rows],
                "rowCount": len(rows), "metadata": meta,
                "propertyQuota": (quota(pid, n) if quota else None) or {"tokensPerDay": {"consumed": 1,
                                                                                         "remaining": 190000}}}
    monkeypatch.setattr(ga4, "_call", call)
    return asked


def test_refresh_all_two_passes_store_and_counts_only_line(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"},
            {"app_id": AID2, "package": "com.example.beta", "pid": "112"}]
    _patch_routes(monkeypatch, apps)
    asked = _http(monkeypatch, Model())
    data = str(tmp_path / "data")
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.refresh_all(cfg, data, [dict(a) for a in apps] + [{"app_id": "x~3", "package": None}], NOW,
                         clock=lambda: 0.0, budget=1000, workers=1)
    assert out["apps"] == {AID: "fetched", AID2: "fetched"} and "error" not in out
    day = [(i, q) for i, (_, q) in enumerate(asked) if "date" in q.dims or q.dims == ("eventName",)]   # (not a
    recent = [i for i, q in day if q.b == TODAY or q.dims == ("eventName",)]                           # period's
    back = [i for i, q in day if q.b <= FE and q.dims != ("eventName",)]                               # users)
    assert recent and back and max(recent) < min(back)      # every app's recent window before any backfill
    meta = gs.load_meta(data, KEY)
    assert meta["package"] == "com.example.alpha" and all(meta["reads"][r]["done"] for r in gs.ORDER)
    assert min(meta["months"]["core"]) == "2026-10" and _final(tmp_path, "core", "2026-10")["2026-10-21"]["t"]["ev"]
    st = json.load(open(os.path.join(data, gs.DIR, "state.json")))
    assert st["fetch"][AID]["key"] == KEY and st["fetch"][AID]["last_ok"] == gu._now_iso(NOW)
    c = out["counts"]
    assert c["calls"] == len(asked) and c["whole"] > 0 and c["quota_stops"] == 0
    line = gs.log_line(out)
    assert line.startswith("ga4 screens: apps 2, with GA4 2, fetched 2, fresh 0, failed 0, deferred 0, waiting 0, ")
    assert "skipped:" not in line and "example" not in line and "Activity" not in line and "unit_" not in line
    assert KEY not in line and "~" not in line
    # an hour later: the backfill moved the store's first day back (d0), so only the periods that changed with it are
    # read (no day read: the history is complete) …
    root = os.path.join(data, gs.DIR)
    had = set(gs.load_users(root, KEY)["w"])
    n = len(asked)
    out2 = gs.refresh_all(cfg, data, [dict(a) for a in apps], NOW + timedelta(hours=1), clock=lambda: 0.0)
    again = asked[n:]
    assert again and all("date" not in q.dims for _, q in again)
    w2 = gs.load_users(root, KEY)["w"]
    new = {k for k in w2 if k not in had}
    assert new and {"%s_%s" % (q.a, q.b) for p, q in again if p == "111"} == new
    assert min(gu._d(k[:10]) for k in w2) == gu._d(gs.store_d0(root, KEY))
    # … and an hour after that nothing is due: fresh, no call
    n = len(asked)
    out3 = gs.refresh_all(cfg, data, [dict(a) for a in apps], NOW + timedelta(hours=2), clock=lambda: 0.0)
    assert out3["apps"] == {AID: "fresh", AID2: "fresh"} and len(asked) == n
    # an internal error: counted, and the health line printed with the type only
    err = gs.log_line({"counts": {}, "error": "KeyError"})
    assert err.splitlines()[0].endswith(", error KeyError") and err.splitlines()[1] == "ga4 screens skipped: KeyError"


def test_quota_floors_and_a_429_stop_the_property_deferred_not_failed(monkeypatch, tmp_path):
    q = lambda hour, day, thr=500, err=10: {"tokensPerHour": {"consumed": 40000 - hour, "remaining": hour},
                                            "tokensPerProjectPerHour": {"consumed": 0, "remaining": 14000},
                                            "tokensPerDay": {"consumed": 200000 - day, "remaining": day},
                                            "potentiallyThresholdedRequestsPerHour": {"remaining": thr},
                                            "serverErrorsPerProjectPerHour": {"remaining": err}}
    assert gs.quota_gate(q(30000, 150000)) is None
    assert gs.quota_gate(q(23000, 150000)) == "hour_low"            # < 60 % of 40,000
    assert gs.quota_gate(q(30000, 70000)) == "day_low"              # < 40 % of 200,000
    assert gs.quota_gate(q(30000, 150000, thr=59)) == "count_low"
    assert gs.quota_gate(q(30000, 150000, err=4)) == "count_low"
    # the history job: 65 % of an hourly bucket, above the other GA4 steps' 50 % (gaud.HOUR_FLOOR)
    assert gs.bf_gate(q(26000, 150000)) is None and gs.bf_gate(q(25999, 150000)) == "hour_low"
    assert gs.BF_FLOORS["tokensPerHour"] > gs.gaud.HOUR_FLOOR and gs.BF_FLOORS["tokensPerProjectPerHour"] > \
        gs.gaud.HOUR_FLOOR and gs.BF_FLOORS["tokensPerDay"] == 0.4
    # the build's step: the first app's property gets low after 2 calls; the other app gets a 429 at once
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"},
            {"app_id": AID2, "package": "com.example.beta", "pid": "112"}]
    _patch_routes(monkeypatch, apps)
    asked = _http(monkeypatch, Model(), quota=lambda pid, n: q(20000 if n >= 1 else 39000, 190000),
                  fail=lambda pid, n: RuntimeError("HTTP 429: RESOURCE_EXHAUSTED") if pid == "112" else None)
    data = str(tmp_path / "data")
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.refresh_all(cfg, data, [dict(a) for a in apps], NOW, clock=lambda: 0.0)
    assert out["apps"] == {AID: "deferred", AID2: "deferred"} and out["counts"]["quota_stops"] == 2
    assert out["stops"] == {"hour_low": 1, "quota_429": 1}
    assert len([1 for p, _ in asked if p == "111"]) == 2 and not [1 for p, _ in asked if p == "112"]
    st = json.load(open(os.path.join(data, gs.DIR, "state.json")))
    assert st["fetch"][AID]["deferred"] and not st["fetch"][AID2].get("fail")
    assert gs.load_meta(data, KEY)["reads"]["t"]["oldest"]                  # what was set up is kept


def test_the_run_budget_and_the_app_call_cap_defer(tmp_path):
    ga = FakeGA(stop_after=4)
    job = _job(tmp_path, ga)
    with pytest.raises(gf.Stop):
        gs.step_recent(job)
    assert ga.calls == 4


# ── the history job ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_backfill_all_reads_only_final_days_into_its_own_folder_and_pushes(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)
    asked = _http(monkeypatch, Model())
    data, staged = str(tmp_path / "data"), str(tmp_path / gs.BF_DIR)
    pushes, lines = [], []
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.backfill_all(cfg, data, staged, [dict(a) for a in apps], NOW, clock=lambda: 0.0, workers=2,
                          push=lambda: pushes.append(1) or True, say=lines.append, tick=0.01)
    assert out["apps"] == {AID: "done"} and out["pushed"] and pushes
    assert all(q.b <= FE for _, q in asked) and not os.path.exists(os.path.join(data, gs.DIR))
    meta = gs._read_gz(gs.meta_path(staged, KEY))
    assert meta["reads"]["a"]["top"] == FE.isoformat() and meta["reads"]["a"]["done"]
    assert "recent.json.gz" not in os.listdir(os.path.join(staged, KEY))
    line = gs.bf_line(out)
    assert line.startswith("ga4 screens backfill: apps 1, with GA4 1, done 1, deferred 0, failed 0") and \
        "example" not in line and KEY not in line
    # its records merge into the build's store; a second merge changes nothing; a broken file is skipped and counted
    with open(os.path.join(staged, KEY, "cc_2026-09.json.gz"), "wb") as f:
        f.write(b"not gzip")
    state = {"fetch": {}, "staged": {}}
    m1 = gs.merge_staged(data, staged, state)
    assert m1["merged"] > 0 and m1["bad"] == 1
    core = _final(tmp_path, "core", "2026-10")
    assert core["2026-10-21"]["a"]["st"] == "w"
    m2 = gs.merge_staged(data, staged, state)
    assert m2["merged"] == 0 and m2["bad"] == 1
    m3 = gs.merge_staged(data, staged, {"fetch": {}, "staged": {}})          # without the sha memory: still nothing
    assert m3["merged"] == 0


def test_backfill_all_moves_on_from_a_property_at_its_floor(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"},
            {"app_id": AID2, "package": "com.example.beta", "pid": "112"}]
    _patch_routes(monkeypatch, apps)
    low = {"tokensPerHour": {"consumed": 30000, "remaining": 10000}}
    asked = _http(monkeypatch, Model(), quota=lambda pid, n: low if pid == "111" else None)
    data, staged = str(tmp_path / "data"), str(tmp_path / gs.BF_DIR)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    t = [0.0]
    out = gs.backfill_all(cfg, data, staged, [dict(a) for a in apps], NOW, clock=lambda: t[0], budget=600,
                          workers=1, wall=lambda: datetime(2026, 11, 4, 6, 30, tzinfo=timezone.utc), tick=0.01)
    assert out["apps"] == {AID: "deferred", AID2: "done"} and out["counts"]["quota_stops"] == 1
    assert len([1 for p, _ in asked if p == "111"]) == 1    # one call, then the property waits for the next hour
    assert gs._next_hour(datetime(2026, 11, 4, 6, 30, tzinfo=timezone.utc)).hour == 7


def _tokens(monkeypatch):
    """ga4.access_token → "tok1", "tok2", … (one more each fetch). → the list of tokens handed out."""
    got = []
    monkeypatch.setattr(gs.ga4, "access_token", lambda c, s, r: got.append("tok%d" % (len(got) + 1)) or got[-1])
    return got


def test_the_history_job_renews_its_access_token_before_it_expires(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)
    got = _tokens(monkeypatch)
    t, refused = [0.0], []
    sent = {}

    def auth(token):                                        # Google's token lasts about an hour from its fetch
        sent.setdefault(token, t[0])
        t[0] += 300.0                                       # every call: 300 s on the job's clock
        if t[0] - sent[token] > 3600:
            refused.append(token)
            return RuntimeError("HTTP 401: UNAUTHENTICATED")
    asked = _http(monkeypatch, Model(), auth=auth)
    data, staged = str(tmp_path / "data"), str(tmp_path / gs.BF_DIR)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.backfill_all(cfg, data, staged, [dict(a) for a in apps], NOW, clock=lambda: t[0], workers=1, tick=0.01)
    assert t[0] > 2 * 3600 and len(asked) > 24              # the run outlived two tokens …
    assert out["apps"] == {AID: "done"} and "error" not in out and out["counts"]["failed"] == 0
    assert len(got) >= 3 and refused == []                  # … each renewed before it ran out


def test_a_401_gets_a_new_token_and_the_call_once_more(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)
    got = _tokens(monkeypatch)
    n, refused = [0], []

    def auth(token):                                        # tok1 revoked after its 3rd call, whatever the clock
        n[0] += 1
        if token == "tok1" and n[0] > 3:
            refused.append(token)
            return RuntimeError("HTTP 401: UNAUTHENTICATED")
    _http(monkeypatch, Model(), auth=auth)
    data, staged = str(tmp_path / "data"), str(tmp_path / gs.BF_DIR)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.backfill_all(cfg, data, staged, [dict(a) for a in apps], NOW, clock=lambda: 0.0, workers=2, tick=0.01)
    assert refused == ["tok1"] and got == ["tok1", "tok2"]
    assert out["apps"] == {AID: "done"} and out["counts"]["failed"] == 0
    # the build's step too; a token GA4 refuses again is a failed app (auth), never a loop
    monkeypatch.setattr(gs.ga4, "access_token", lambda c, s, r: "dead")
    _http(monkeypatch, Model(), auth=lambda token: RuntimeError("HTTP 401: UNAUTHENTICATED"))
    out = gs.refresh_all(cfg, str(tmp_path / "d2"), [dict(a) for a in apps], NOW, clock=lambda: 0.0)
    assert out["apps"] == {AID: "failed"}
    st = json.load(open(os.path.join(str(tmp_path / "d2"), gs.DIR, "state.json")))
    assert st["fetch"][AID]["fail"] == "auth"


def _bf_clockwork():
    """A fake wall clock the history job's rests advance (sleep moves it), so a 3-minute rest costs no real time."""
    w = [0.0]
    base = datetime(2026, 11, 4, 6, 5, tzinfo=timezone.utc)
    return (lambda: base + timedelta(seconds=w[0])), (lambda s: w.__setitem__(0, w[0] + s))


def test_the_history_job_tries_an_app_again_after_a_passing_error(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)
    n = [0]

    def flaky(token):                                       # the first two calls: a 5xx that ga4._call gave up on
        n[0] += 1
        if n[0] <= 2:
            return RuntimeError("HTTP 503: unavailable")
    _http(monkeypatch, Model(), auth=flaky)
    data, staged = str(tmp_path / "data"), str(tmp_path / gs.BF_DIR)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    wall, sleep = _bf_clockwork()
    out = gs.backfill_all(cfg, data, staged, [dict(a) for a in apps], NOW, clock=lambda: 0.0, workers=1,
                          wall=wall, sleep=sleep, tick=0.01)
    assert out["apps"] == {AID: "done"} and out["counts"]["failed"] == 0 and "error" not in out
    assert (wall() - datetime(2026, 11, 4, 6, 5, tzinfo=timezone.utc)).total_seconds() >= 2 * gs.BF_RETRY_SEC


def test_the_history_job_gives_an_app_up_only_after_several_errors(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)
    n = [0]

    def down(token):
        n[0] += 1
        return RuntimeError("HTTP 503: unavailable")
    _http(monkeypatch, Model(), auth=down)
    data, staged = str(tmp_path / "data"), str(tmp_path / gs.BF_DIR)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    wall, sleep = _bf_clockwork()
    out = gs.backfill_all(cfg, data, staged, [dict(a) for a in apps], NOW, clock=lambda: 0.0, workers=1,
                          wall=wall, sleep=sleep, tick=0.01)
    assert out["apps"] == {AID: "failed"} and out["counts"]["failed"] == 1 and n[0] == gs.BF_FAIL_MAX


def test_a_heartbeat_that_raises_never_stops_the_pushes(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"},
            {"app_id": AID2, "package": "com.example.beta", "pid": "112"}]
    _patch_routes(monkeypatch, apps)
    _http(monkeypatch, Model())
    monkeypatch.setattr(gs, "HEARTBEAT_SEC", 0)
    pushes = []

    def say(line):
        raise RuntimeError("dictionary changed size during iteration")
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.backfill_all(cfg, str(tmp_path / "data"), str(tmp_path / gs.BF_DIR), [dict(a) for a in apps], NOW,
                          clock=lambda: 0.0, workers=2, push=lambda: pushes.append(1) or True, push_sec=0, say=say,
                          tick=0.001)
    assert "error" not in out and out["apps"] == {AID: "done", AID2: "done"} and len(pushes) >= 2


def test_a_damaged_store_file_is_never_written_over(monkeypatch, tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    days = gs._days(date(2026, 10, 1), date(2026, 10, 7))
    _t_days(job, days)
    job.store.save_meta()
    root = str(tmp_path / "data" / gs.DIR)
    p = gs.month_path(root, KEY, "core", "2026-10")
    raw = open(p, "rb").read()
    with open(p, "wb") as f:
        f.write(raw[:len(raw) // 2])                        # cut in half
    cut = open(p, "rb").read()
    with pytest.raises(gs.StoreError):
        gs.Store(root, KEY, {}).put({"2026-10-09": {"t": {"st": "w", "g": "t", "fv": 1}}})
    assert open(p, "rb").read() == cut                      # left as it is
    with pytest.raises(gs.StoreError):
        gs.Store(root, KEY, {}).status("2026-10-02", "v")
    assert gs.Store(root, KEY, {}, strict=False).status("2026-10-02", "v") is None     # read only: just not there
    # an unreadable meta is never replaced by a new one (its months and the reads' progress would be lost)
    mp = gs.meta_path(root, KEY)
    with open(mp, "wb") as f:
        f.write(b"\x1f\x8bbroken")
    with pytest.raises(gs.StoreError):
        gs.Job(root, _it(), NOW, FakeGA(), lambda: 0.0)
    assert open(mp, "rb").read() == b"\x1f\x8bbroken"
    # merge_staged: that app is skipped and counted; nothing of it written
    staged = str(tmp_path / "bf")
    bst = gs.Store(staged, KEY, {"v": 1, "app_id": AID, "reads": {}, "months": {}})
    bst.put({"2026-10-20": {"v": {"st": "w", "g": "c", "fv": 1, "r": []}}})
    bst.save_meta()
    assert gs.merge_staged(str(tmp_path / "data"), staged, {"fetch": {}})["bad"] == 1
    assert open(mp, "rb").read() == b"\x1f\x8bbroken" and open(p, "rb").read() == cut
    # a NEW meta beside month files already there finds them
    os.remove(mp)
    job2 = gs.Job(root, _it(), NOW, FakeGA(), lambda: 0.0)
    assert job2.meta["months"] == {"core": ["2026-10"]}
    os.remove(p)
    assert gs.Job(root, _it(), NOW, FakeGA(), lambda: 0.0).meta["months"] == {}
    # the build's step: the app ends "failed" for the run, the file untouched
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)
    _http(monkeypatch, Model())
    with open(p, "wb") as f:
        f.write(cut)
    with open(mp, "wb") as f:
        f.write(b"\x1f\x8bbroken")
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.refresh_all(cfg, str(tmp_path / "data"), [dict(a) for a in apps], NOW, clock=lambda: 0.0)
    assert out["apps"] == {AID: "failed"} and "error" not in out
    assert open(mp, "rb").read() == b"\x1f\x8bbroken" and open(p, "rb").read() == cut


def test_merge_staged_rules_and_progress(tmp_path):
    data, staged = str(tmp_path / "data"), str(tmp_path / "bf")
    root = os.path.join(data, gs.DIR)
    w = {"st": "w", "g": "c", "fv": 1, "r": [[MAIN, 1, 2]]}
    o = {"st": "o", "g": "c", "fv": 1, "cov": 0.4}
    store = gs.Store(root, KEY, {"v": 1, "app_id": AID, "reads": {"v": {"oldest": "2026-10-10", "upto": "2026-10-30"}},
                                 "months": {}})
    store.put({"2026-10-01": {"v": o}, "2026-10-02": {"v": dict(w, r=[[MAIN, 9, 9]])}})
    store.save_meta()
    sm = {"v": 1, "app_id": AID, "reads": {"v": {"oldest": "2026-09-01", "top": "2026-10-09", "done": True,
                                                 "d": {"c": 7}, "gate": {"c": {"bad": 5}}},
                                           "a": {"oldest": "2026-09-01", "top": "2026-09-20"}},
          "months": {"core": ["2026-10"]}}
    bst = gs.Store(staged, KEY, sm)
    smp = {"st": "s", "g": "c", "fv": 1, "smp": 0.3}
    bst.put({"2026-10-01": {"v": w}, "2026-10-02": {"v": w}, "2026-10-03": {"v": o, "a": w},
             "2026-10-04": {"v": dict(w, rc=1), "a": smp}})
    bst.save_meta()
    store.put({"2026-10-04": {"a": dict(o, cov=0.9)}})
    out = gs.merge_staged(data, staged, {"fetch": {}})
    assert out == {"merged": 2, "not_whole": 1, "bad": 0}
    days = gs._read_gz(gs.month_path(root, KEY, "core", "2026-10"))["days"]
    assert days["2026-10-01"]["v"] == w                     # not whole here, whole staged: copied
    assert days["2026-10-02"]["v"]["r"] == [[MAIN, 9, 9]]   # whole here: kept
    assert days["2026-10-03"]["a"] == w
    # a staged FINAL record that is not whole, where the store has none: copied (the day's outcome — the build's
    # cursor moves past it); over a stored one that is not whole: never; a record read while recent: never
    assert days["2026-10-03"]["v"] == o and days["2026-10-04"]["a"] == dict(o, cov=0.9)
    assert "v" not in days["2026-10-04"]
    # … and a later whole staged record still replaces it
    bst.put({"2026-10-03": {"v": dict(w, r=[[MAIN, 3, 3]])}})
    assert gs.merge_staged(data, staged, {"fetch": {}}) == {"merged": 1, "not_whole": 0, "bad": 0}
    assert gs._read_gz(gs.month_path(root, KEY, "core", "2026-10"))["days"]["2026-10-03"]["v"]["r"] == [[MAIN, 3, 3]]
    meta = gs.load_meta(data, KEY)
    assert meta["reads"]["v"]["oldest"] == "2026-09-01" and meta["reads"]["v"]["done"]       # the fills touch
    assert meta["reads"]["v"]["d"] == {"c": 7} and meta["reads"]["v"]["gate"] == {"c": {"bad": 5}}
    assert "oldest" not in meta["reads"]["a"]               # the build has no fill for a yet: nothing to join
    assert gs.merge_staged(data, staged, {"fetch": {}}) == {"merged": 0, "not_whole": 0, "bad": 0}
    assert gs.merge_staged(data, str(tmp_path / "missing")) == {"merged": 0, "not_whole": 0, "bad": 0}
    with open(os.path.join(staged, "0123456789ab.json.gz"), "wb") as f:
        f.write(b"\x1f\x8bbroken")
    assert gs.merge_staged(data, staged, {"fetch": {}})["bad"] == 1


def test_merge_staged_an_asked_record_replaces_a_skip_record_never_the_reverse(tmp_path):
    # a skip record (from before: nothing asked, stored as final) is no answer: GA4's, whole or not, replaces it; it
    # never replaces GA4's, is never copied, and a whole record still never gives way to one that is not
    data, staged = str(tmp_path / "data"), str(tmp_path / "bf")
    root = os.path.join(data, gs.DIR)
    w = {"st": "w", "g": "c", "fv": 1, "r": [[MAIN, 1, 2]], "tried": ["c"]}
    o = {"st": "o", "g": "c", "fv": 1, "cov": 0.4, "tried": ["c"]}
    sk = {"st": "s", "g": "c", "skip": "gate", "tried": [], "fv": 1}
    assert gs.merge_rec(sk, o) is o and gs.merge_rec(o, sk) is o and gs.merge_rec(w, sk) is w
    assert gs.merge_rec(sk, w) is w and gs.merge_rec(dict(sk, rc=1), o) is o
    assert not gs._complete(gs._status(sk), "v", []) and gs._complete(gs._status(o), "v", [])
    store = gs.Store(root, KEY, {"v": 1, "app_id": AID, "reads": {}, "months": {}})
    store.put({"2026-10-01": {"v": sk}, "2026-10-02": {"v": o}, "2026-10-03": {"v": w}, "2026-10-04": {"v": sk}})
    store.save_meta()
    bst = gs.Store(staged, KEY, {"v": 1, "app_id": AID, "reads": {}, "months": {}})
    bst.put({"2026-10-01": {"v": dict(o, cov=0.7)},       # GA4's answer, not whole, over a skip record: copied
             "2026-10-02": {"v": sk},                     # a skip record over GA4's answer: never
             "2026-10-03": {"v": o},                      # not whole over whole: never
             "2026-10-04": {"v": w},                      # whole over a skip record: copied
             "2026-10-05": {"v": sk}})                    # a skip record where the build has none: never either
    bst.save_meta()
    assert gs.merge_staged(data, staged, {"fetch": {}}) == {"merged": 1, "not_whole": 1, "bad": 0}
    days = gs._read_gz(gs.month_path(root, KEY, "core", "2026-10"))["days"]
    assert days["2026-10-01"]["v"] == dict(o, cov=0.7) and days["2026-10-02"]["v"] == o
    assert days["2026-10-03"]["v"] == w and days["2026-10-04"]["v"] == w and "2026-10-05" not in days


def test_git_push_sends_the_token_in_a_header_and_adds_only_its_folder():
    calls = []

    class R:
        def __init__(self, rc):
            self.returncode = rc

    def run(cmd, **kw):
        calls.append(cmd)
        if "push" in cmd:
            return R(0 if sum(1 for c in calls if "push" in c) > 1 else 1)        # the first push loses a race
        if "diff" in cmd:
            return R(1)
        return R(0)
    assert gs.git_push("/repo", gs.BF_DIR, "secret-token", run=run, pause=lambda s: None)
    flat = [" ".join(c) for c in calls]
    assert all("secret-token" not in f for f in flat)       # only base64 inside the header, never a URL
    assert all("https://" not in f for f in flat)
    adds = [c for c in calls if "add" in c]
    assert adds and all(c[-1] == gs.BF_DIR for c in adds)
    assert sum(1 for c in calls if "fetch" in c) == 2 and sum(1 for c in calls if "reset" in c) == 2


def test_bf_apps_one_per_package_and_the_apps_input(monkeypatch, tmp_path):
    monkeypatch.setattr(gs.gu, "load_state", lambda d: {"routes": {"by_package": {}}, "tz": {}, "fetch": {
        AID: {"package": "com.example.alpha"}, AID2: {"package": "com.example.alpha"},
        "ca-app-pub-0000000000000000~23": {"package": "com.example.gamma"}}})
    got = gs.bf_apps(str(tmp_path))
    assert [a["app_id"] for a in got] == [AID, "ca-app-pub-0000000000000000~23"]
    assert gs.bf_apps(str(tmp_path), {KEY}) == [{"app_id": AID, "package": "com.example.alpha"}]


def test_stage_names_and_the_wiring():
    assert "ga4_screens" in stage_clock.STAGES
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "admob_iq", "uninstall_build.py"), encoding="utf-8").read()
    i = src.index('_sc.stage("ga4_screens")')
    assert i > src.index('_sc.stage("ga4_cube")') and 'print("ga4 screens skipped: %s" % type(e).__name__' in src
    from admob_iq import config
    cfg = config.settings()
    assert cfg["ga4_screens"] is False and cfg["ga4_screens_budget_sec"] == 0 and cfg["screens_tab"] is True
    wf = open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8").read()
    assert "GA4_SCREENS:          ${{ vars.GA4_SCREENS || 'true' }}" in wf
    assert "SCREENS_STAGED_DIR:   _private/ga4_screens_bf" in wf and "GA4_SCREENS_BUDGET_SEC:" in wf
    bf = open(os.path.join(root, ".github", "workflows", "screens-backfill.yml"), encoding="utf-8").read()
    assert "workflow_dispatch" in bf and "contents: read" in bf and "--backfill" in bf and "timeout-minutes: 350" in bf
    assert "x-access-token:$DATA_REPO_TOKEN@" not in bf
    assert 'cron: "47 */6 * * *"' in bf and "group: screens-backfill" in bf and "cancel-in-progress: false" in bf


def test_merge_staged_never_undoes_a_reset_of_xs_history(tmp_path):
    # the job's x fill was made with the old event list; the build gained a name and reset x: the job's progress is
    # not adopted until the job has read every name the build reads
    data, staged = str(tmp_path / "data"), str(tmp_path / "bf")
    root = os.path.join(data, gs.DIR)
    sm = {"v": 1, "app_id": AID, "events": {"at": "2026-11-01T00:00:00Z", "names": ["inter_shown"]},
          "reads": {"x": {"oldest": "2026-09-01", "top": "2026-10-30", "done": True},
                    "v": {"oldest": "2026-09-01", "top": "2026-10-30", "done": True}}, "months": {}}
    gs.Store(staged, KEY, sm).save_meta()
    ga = FakeGA()
    job = gs.Job(root, _it(hs=date(2026, 9, 1)), NOW, ga, lambda: 0.0)
    job.meta["events"] = {"at": "2026-11-01T00:00:00Z", "names": ["inter_shown"]}
    for rid in ("x", "v"):
        job.init_read(rid)
    gs.discover(job)                                        # gains "banner_load_fail" → x reset
    job.init_read("x")
    job.store.save_meta()
    assert job.meta["events"]["names"] == ["banner_load_fail", "inter_shown"]
    gs.merge_staged(data, staged, {"fetch": {}})
    reads = gs.load_meta(data, KEY)["reads"]
    assert reads["x"]["oldest"] == "2026-10-31" and not reads["x"].get("done")
    assert reads["v"]["oldest"] == "2026-09-01" and reads["v"]["done"]      # other reads still join
    gs.merge_staged(data, staged, {"fetch": {}})            # (every build: still not undone)
    assert gs.load_meta(data, KEY)["reads"]["x"]["oldest"] == "2026-10-31"
    # once the job read the new list too, its (new) x fill joins
    sm["events"]["names"] = ["banner_load_fail", "inter_shown"]
    gs.Store(staged, KEY, sm).save_meta()
    gs.merge_staged(data, staged, {"fetch": {}})
    assert gs.load_meta(data, KEY)["reads"]["x"]["oldest"] == "2026-09-01"


def test_a_long_merge_never_eats_the_builds_ga4_time(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)
    _http(monkeypatch, Model())
    t = [0.0]

    def slow_merge(data_dir, staged_dir, state=None):        # a first merge longer than the whole budget
        t[0] += 10 * gs.BUDGET_SEC
        return {"merged": 0, "not_whole": 0, "bad": 0}
    monkeypatch.setattr(gs, "merge_staged", slow_merge)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.refresh_all(cfg, str(tmp_path / "data"), [dict(a) for a in apps], NOW, clock=lambda: t[0],
                         staged_dir=str(tmp_path / "bf"))
    assert out["apps"] == {AID: "fetched"} and out["counts"]["deferred"] == 0


def test_the_history_job_leaves_its_last_word_on_each_app(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"},
            {"app_id": AID2, "package": "com.example.beta", "pid": "112"}]
    _patch_routes(monkeypatch, apps)
    low = {"tokensPerHour": {"consumed": 30000, "remaining": 10000}}
    _http(monkeypatch, Model(), quota=lambda pid, n: low if pid == "111" else None)
    data, staged = str(tmp_path / "data"), str(tmp_path / gs.BF_DIR)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    gs.backfill_all(cfg, data, staged, [dict(a) for a in apps], NOW, clock=lambda: 0.0, budget=600, workers=1,
                    wall=lambda: datetime(2026, 11, 4, 6, 30, tzinfo=timezone.utc), tick=0.01)
    paused = gs._read_gz(gs.meta_path(staged, KEY))["bf"]
    assert paused["state"] == "paused" and paused["why"] and paused["n"]["paused"] >= 1
    assert paused["q"]["tokensPerHour"] == 0.25 and paused["type"] is None
    done = gs._read_gz(gs.meta_path(staged, gu.file_key(AID2)))["bf"]
    assert done["state"] == "done B" and done["n"] == {"done A": 1, "done B": 1}


def test_an_old_skip_record_is_read_again_by_the_history_job(monkeypatch, tmp_path):
    # folders written before this change: a final day stored as a skip (nothing asked) is no answer — the history job
    # looks once for every skip record (its folder's and the build's), asks GA4 for those days only and ends done;
    # the merge then puts GA4's answer over the build's skip record
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)                        # history start 2026-10-21
    asked = _http(monkeypatch, Model())
    data, staged = str(tmp_path / "data"), str(tmp_path / gs.BF_DIR)
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}

    def run():
        return gs.backfill_all(cfg, data, staged, [dict(a) for a in apps], NOW, clock=lambda: 0.0, workers=1,
                               tick=0.01)
    assert run()["apps"] == {AID: "done"}
    d1, d2 = "2026-10-25", "2026-10-23"
    skip = {"st": "s", "g": "c", "skip": "gate", "tried": [], "fv": 1}
    core, small = gs.month_path(staged, KEY, "core", "2026-10"), gs.month_path(staged, KEY, "small", "2026-10")
    _rewrite(core, lambda j: j["days"][d1].update(a=skip))              # the job's own: "a" stored unasked
    _rewrite(small, lambda j: j["days"][d2].pop("s"))                   # the build's: "s" skipped there, not read here
    bst = gs.Store(os.path.join(data, gs.DIR), KEY, {"v": 1, "app_id": AID, "reads": {}, "months": {}})
    bst.put({d2: {"s": dict(skip, g="fs", st="o", skip="dead")}})
    bst.save_meta()
    _rewrite(gs.meta_path(staged, KEY), lambda m: [rd.pop("redo", None) for rd in m["reads"].values()])
    assert all(r["done"] for r in gs._read_gz(gs.meta_path(staged, KEY))["reads"].values())
    n = len(asked)
    out = run()
    assert out["apps"] == {AID: "done"} and "error" not in out
    assert [(_rid(q), q.a.isoformat(), q.b.isoformat()) for _, q in asked[n:] if "date" in q.dims] == [
        ("a:fu", d1, d1), ("s:fs", d2, d2)]                 # (the users of a period moved with d0: their own test)
    rec = gs._read_gz(core)["days"][d1]["a"]
    assert rec["st"] == "w" and rec["g"] == "fu" and rec["tried"] == ["fu"] and "skip" not in rec
    assert gs._read_gz(small)["days"][d2]["s"]["st"] == "w"
    assert all(rd["redo"] == [] for rd in gs._read_gz(gs.meta_path(staged, KEY))["reads"].values())
    gs.merge_staged(data, staged, {"fetch": {}, "staged": {}})
    got = _final(tmp_path, "small", "2026-10")[d2]["s"]
    assert got["st"] == "w" and "skip" not in got


# ── the page path (6 Nov 2026) ──────────────────────────────────────────────────────────────────────────────────────
def _by_class(rec):
    """A record as the class reads stored it before 6 Nov: no "pp" mark."""
    return {k: v for k, v in rec.items() if k != "pp"}


def test_a_class_record_not_whole_is_asked_again_by_page_path_and_a_whole_one_stays(monkeypatch, tmp_path):
    # the build's store as the class reads left it: one ads day sampled, one whole; the next run asks only the sampled
    # day again — by page path — and keeps the whole one; the views read (still by class) is never asked again
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)                        # history start 2026-10-21
    asked = _http(monkeypatch, Model())
    data = str(tmp_path / "data")
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    assert gs.refresh_all(cfg, data, [dict(a) for a in apps], NOW, clock=lambda: 0.0, budget=1000)["apps"] == {
        AID: "fetched"}
    root = os.path.join(data, gs.DIR)
    p = gs.month_path(root, KEY, "core", "2026-10")
    bad, good = "2026-10-24", "2026-10-25"

    def back(j):
        j["days"][bad]["a"] = {"st": "s", "g": "c", "smp": 0.2, "tried": ["fu", "f", "c"], "fv": 1}
        j["days"][good]["a"] = _by_class(j["days"][good]["a"])
    _rewrite(p, back)

    def old_meta(m):                                        # learned by class: a dead fu, a gate; no page path mark
        for rid, rd in m["reads"].items():
            rd.pop("redo", None)
            if rid in gs.PP_READS:
                rd.pop("dim", None)
                rd["dead"], rd["gate"] = {"fu": {"n": 3, "st": "s", "until": 999}}, {"f": {"bad": 1}}
    _rewrite(gs.meta_path(root, KEY), old_meta)
    n = len(asked)
    gs.refresh_all(cfg, data, [dict(a) for a in apps], NOW + timedelta(hours=1), clock=lambda: 0.0)
    redo = [(_rid(q), q.a.isoformat(), q.b.isoformat()) for _, q in asked[n:] if q.a.isoformat() <= "2026-10-30"
            and "date" in q.dims]                       # (a period's users moved with d0: their own test)
    assert redo == [("a:fu", bad, bad)]                     # the learned state started again: fu alive, whole
    days = gs._read_gz(p)["days"]
    assert days[bad]["a"]["st"] == "w" and days[bad]["a"]["g"] == "fu" and days[bad]["a"]["pp"] == 1
    assert days[good]["a"] == _by_class(days[good]["a"]) and "pp" not in days[good]["a"]      # (kept as it was)
    m = gs.load_meta(data, KEY)
    for rid in gs.PP_READS:
        assert m["reads"][rid]["dim"] == gs.PP and "fu" not in m["reads"][rid]["dead"], rid
    assert "dim" not in m["reads"]["v"]


def test_the_learned_state_starts_again_once_for_the_page_path_reads_only(tmp_path):
    job = _job(tmp_path)
    for rid in ("a", "v"):
        rd = job.meta["reads"].setdefault(rid, {})
        rd.update(d={"fu": 3}, dead={"f": {"n": 3, "until": 9}}, gate={"c": {"bad": 5}}, redo=["2026-10-01"])
    rd = job.rd("a")
    assert rd["dim"] == gs.PP and rd["dead"] == rd["gate"] == {} and "redo" not in rd
    assert rd["d"] == {"fu": 3}                             # (the grain stays: the ladder halves and doubles from it)
    rd["dead"]["fu"] = {"n": 1}                             # learned by page path from here on: kept
    assert job.rd("a")["dead"] == {"fu": {"n": 1}}
    v = job.rd("v")
    assert "dim" not in v and v["d"] == {"fu": 3} and v["redo"] == ["2026-10-01"]
    assert gs.PP_READS == {"a", "k", "e", "x"}


def test_the_staged_merge_takes_a_page_path_answer_over_a_class_one_not_whole(tmp_path):
    data, staged = str(tmp_path / "data"), str(tmp_path / "private" / gs.BF_DIR)
    root = os.path.join(data, gs.DIR)
    meta = {"v": gs.STORE_V, "app_id": AID, "package": "com.example.alpha", "reads": {}, "events": {}, "months": {}}
    st_ = gs.Store(root, KEY, meta)
    d1, d2 = "2026-10-24", "2026-10-25"
    st_.put({d1: {"a": {"st": "s", "g": "c", "smp": 0.2, "tried": ["c"], "fv": 1}},
             d2: {"a": {"st": "w", "g": "fu", "r": [[MAIN, "Banner", "unit_a", 60]], "tried": ["fu"], "fv": 1}}})
    st_.save_meta()
    sm = dict(meta, reads={"a": {"dim": gs.PP, "dead": {"fu": {"n": 3, "until": 9}}}})
    ss = gs.Store(staged, KEY, sm)
    ss.put({d1: {"a": {"st": "w", "g": "c", "r": [[MAIN, 70]], "tried": ["c"], "fv": 1, "pp": 1}},
            d2: {"a": {"st": "s", "g": "c", "smp": 0.2, "tried": ["c"], "fv": 1, "pp": 1}}})
    ss.save_meta()
    state = gs.load_state(data)
    state["staged"] = {"x": "y"}                            # (merged under the old rules: looked at once more)
    out = gs.merge_staged(data, staged, state)
    assert out["merged"] == 1 and state["merge_v"] == gs.MERGE_V and "x" not in state["staged"]
    days = gs._read_gz(gs.month_path(root, KEY, "core", "2026-10"))["days"]
    assert days[d1]["a"]["pp"] == 1 and days[d1]["a"]["st"] == "w"     # the page path answer over the class one
    assert days[d2]["a"]["st"] == "w" and "pp" not in days[d2]["a"]     # a whole class answer stays
    assert gs.load_meta(data, KEY)["reads"]["a"].get("dead") in (None, {})   # learned by page path, the build's
                                                                            # not yet: never copied across


def test_the_history_job_reads_only_the_apps_the_dashboard_has_selected(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"},
            {"app_id": AID2, "package": "com.example.beta", "pid": "112"}]
    _patch_routes(monkeypatch, apps)
    data = str(tmp_path / "data")
    assert {a["app_id"] for a in gs.bf_apps(data)} == {AID, AID2}          # no published dashboard: every app
    site = tmp_path / "site"
    site.mkdir()
    with gzip.open(site / "dashboard.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"apps_catalog": [{"app_id": AID, "selected": True}, {"app_id": AID2, "selected": False}]}, f)
    assert [a["app_id"] for a in gs.bf_apps(data)] == [AID]


def test_a_finer_shape_that_dies_on_the_way_stops_walking_and_the_rest_go_coarser(tmp_path):
    # 10 final days, fu and f sampled at every size, c whole: fu is asked until it dies (its 3rd one-day failure),
    # never for the other days; f the same; c reads every day left, at its grain
    ga = FakeGA(Model(lambda q, rows: (rows, SAMPLED if _a_shape(q) in ("fu", "f") else {})))
    job = _job(tmp_path, ga)
    days = gs._days(FE - timedelta(days=9), FE)
    _t_days(job, days)
    n = len(ga.asked)
    gs.fill(job, "a", list(reversed(days)), True)
    one = lambda s: sum(1 for q in ga.asked[n:] if _a_shape(q) == s and q.a == q.b)
    assert one("fu") == 3 and one("f") == 3
    core = _final(tmp_path, "core", "2026-10")
    assert all(core[d]["a"]["st"] == "w" for d in days) and {core[d]["a"]["g"] for d in days} == {"c"}
    rd = job.rd("a")
    assert "until" in rd["dead"]["fu"] and "until" in rd["dead"]["f"] and "c" not in rd["dead"]


def test_the_history_job_never_asks_a_day_the_builds_store_answered(monkeypatch, tmp_path):
    # the build's store holds GA4's own final answer (sampled, by page path) for a day: the history job's needs() is
    # False for it, whole or not — the same day is never asked twice
    root = str(tmp_path / "data" / gs.DIR)
    meta = {"v": gs.STORE_V, "app_id": AID, "package": "com.example.21", "reads": {}, "events": {}, "months": {}}
    b = gs.Store(root, KEY, meta)
    d = FE.isoformat()
    b.put({d: {"a": {"st": "s", "g": "c", "smp": 0.2, "tried": ["c"], "fv": 1, "pp": 1},
               "w": {"st": "s", "g": "u", "smp": 0.2, "tried": ["u"], "fv": 1}}})
    b.save_meta()
    job = gs.Job(str(tmp_path / "staged"), _it(), NOW, FakeGA(), lambda: 0.0,
                 also=gs.Store(root, KEY, gs._read_gz(gs.meta_path(root, KEY)), strict=False), bf=True)
    assert not job.needs("a", d) and not job.needs("w", d)
    b.put({d: {"a": {"st": "s", "g": "c", "smp": 0.2, "tried": ["c"], "fv": 1}}})         # by class: asked again
    job = gs.Job(str(tmp_path / "staged"), _it(), NOW, FakeGA(), lambda: 0.0,
                 also=gs.Store(root, KEY, gs._read_gz(gs.meta_path(root, KEY)), strict=False), bf=True)
    assert job.needs("a", d) and not job.needs("w", d)


# ── revenue by screen (m) and the users of a period (owner, 8 Nov 2026: "Firebase jaise numbers … Revenue") ────────
def test_revenue_by_class_in_micros_tied_to_its_own_total(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    _t_days(job, [FE])
    d = FE.isoformat()
    n = len(ga.asked)
    recs, clean, _ = gs.read_chunk(job, "m", "c", FE, FE)
    assert [_rid(q) for q in ga.asked[n:]] == ["m:own", "m:c"]
    assert [q.mets for q in ga.asked[n:]] == [gs.REVM, gs.REVM] and all(q.event is None for q in ga.asked[n:])
    rec = recs[d]
    assert clean and rec["st"] == "w" and rec["t"] == [2500000, 2250000]          # 0.75 + 0.25 + 1.5 · 1.25 ad
    assert rec["r"] == [[LIST_, 250000, 250000], [MAIN, 750000, 750000], [ADACT, 1500000, 1250000]]
    assert gs._mic("1234.567891") == 1234567891 and gs._mic(None) == 0 and gs._mic("x") == 0
    # a day with no revenue at all costs the split nothing: whole and empty, its zero truth kept
    ga.model.hook = lambda q, rows: ([] if "totalRevenue" in q.mets else rows, {})
    n = len(ga.asked)
    recs, clean, _ = gs.read_chunk(job, "m", "c", FE, FE)
    assert clean and recs[d] == {"st": "w", "g": "c", "fv": 1, "r": [], "t": [0, 0]}
    assert [_rid(q) for q in ga.asked[n:]] == ["m:own"]
    # the ad revenue of a screen lost: the second metric does not tie → not whole, no rows
    def lose(q, rows):
        if "totalRevenue" not in q.mets or gs.SC not in q.dims:
            return rows, {}
        return [dict(r, totalAdRevenue=0) if r.get(gs.SC) == ADACT else r for r in rows], {}
    ga.model.hook = lose
    recs, _, _ = gs.read_chunk(job, "m", "c", FE, FE)
    assert recs[d]["st"] == "o" and "r" not in recs[d]
    assert gs.GRP["m"] == "core" and "m" in gs.CORE and gs.ORDER.index("m") == gs.ORDER.index("a") + 1


def test_the_periods_the_page_offers():
    today, d0 = date(2026, 11, 4), date(2026, 8, 20)
    got = gs.pu_wanted(today, d0)
    keys = [k for k, *_ in got]
    assert len(keys) == len(set(keys))
    kinds = {k: kd for k, _, _, kd in got}
    ft = "2026-11-02"                                       # td − 2, the page's last final day
    assert kinds["2026-11-04_2026-11-04"] == "day" and kinds["2026-11-03_2026-11-03"] == "day"
    assert kinds["2026-10-27_%s" % ft] == "roll" and kinds["2026-10-04_%s" % ft] == "roll"
    assert kinds["2026-09-04_%s" % ft] == "roll" and kinds["2026-08-20_%s" % ft] == "roll"     # 90 days: from d0
    assert kinds["2026-11-01_2026-11-04"] == "day"         # this month (… today)
    assert kinds["2026-08-20_2026-11-04"] == "all"
    months = [k for k, _, _, kd in got if kd == "month"]
    assert months == ["2026-10-01_2026-10-31", "2026-09-01_2026-09-30", "2026-08-20_2026-08-31"]   # newest first
    assert all(gu._d(k[:10]) >= d0 for k in keys)
    # a store younger than 60 days: the clamped windows come once (60 = 90 = from d0)
    young = gs.pu_wanted(today, date(2026, 10, 10))
    assert [k for k, *_ in young].count("2026-10-10_%s" % ft) == 1
    assert [k for k, _, _, kd in young if kd == "month"] == ["2026-10-10_2026-10-31"]


def _pu_hook(extra=None):
    def hook(q, rows):
        if "date" in q.dims or "activeUsers" not in q.mets or q.event:
            return rows, {}
        return (extra or (lambda q, rows: (rows, {})))(q, rows)
    return hook


def test_a_periods_users_record(tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga)
    lo, hi = date(2026, 10, 1), date(2026, 10, 31)
    rec = gs.read_users(job, lo, hi)
    q1, q2 = ga.asked[-2:]
    assert q1.dims == (gs.SC,) and q2.dims == () and q1.mets == q2.mets == ("activeUsers",) and not q1.event
    assert (q1.a, q1.b) == (lo, hi) and job.did
    # the fake's users per class are a sum over 31 days (GA4's are unique: the record keeps what GA4 says)
    assert rec["st"] == "w" and rec["lo"] == "2026-10-01" and rec["hi"] == "2026-10-31" and "fin" not in rec
    assert rec["r"] == [[LIST_, 9 * 31], [MAIN, 23 * 31], [ADACT, 4 * 31]] and rec["tot"] == 36 * 31
    fin = gs.read_users(job, lo, FE)
    assert fin["fin"] == 1
    # GA4's fold: the named rows kept, the fold's users beside them, "p"
    ga.model.hook = _pu_hook(lambda q, rows: ((rows + [{gs.SC: "(other)", "activeUsers": 5}]) if q.dims else rows,
                                              {"dataLossFromOtherRow": True} if q.dims else {}))
    rec = gs.read_users(job, lo, hi)
    assert rec["st"] == "p" and rec["fold"] == 5 and rec["loss"] == 1 and len(rec["r"]) == 3
    # sampled / cut: no rows
    ga.model.hook = _pu_hook(lambda q, rows: (rows, {"samplingMetadatas": [{"samplesReadCount": "1",
                                                                           "samplingSpaceSize": "4"}]}))
    assert gs.read_users(job, lo, hi) == {"lo": "2026-10-01", "hi": "2026-10-31", "at": gu._now_iso(NOW), "st": "s",
                                          "smp": 0.25}
    ga.model.hook = _pu_hook(lambda q, rows: (rows[:-1], {"_rc": len(rows)}) if q.dims else (rows, {}))
    rec = gs.read_users(job, lo, hi)
    assert rec["st"] == "o" and rec["trunc"] == 1 and "r" not in rec
    ga.model.hook = _pu_hook(lambda q, rows: (rows, {"subjectToThresholding": True}))
    assert gs.read_users(job, lo, hi)["thr"] == 1


def test_when_a_period_is_read_again():
    fe, now = date(2026, 10, 30), NOW
    at = lambda h: gu._now_iso(now - timedelta(hours=h))
    rec = lambda st, h, **k: dict({"st": st, "at": at(h)}, **k)
    assert gs._pu_due(None, "day", date(2026, 11, 4), fe, now)
    assert not gs._pu_due(rec("w", 2), "day", date(2026, 11, 4), fe, now)
    assert gs._pu_due(rec("w", 3), "day", date(2026, 11, 4), fe, now)
    assert not gs._pu_due(rec("w", 5), "roll", date(2026, 11, 2), fe, now)
    assert gs._pu_due(rec("w", 6), "roll", date(2026, 11, 2), fe, now)
    assert not gs._pu_due(rec("w", 23), "all", date(2026, 11, 4), fe, now)
    assert gs._pu_due(rec("w", 24), "all", date(2026, 11, 4), fe, now)
    # final: a whole record read once it was final is never read again; one read before it was, or not whole, a day on
    assert not gs._pu_due(rec("w", 500, fin=1), "month", date(2026, 9, 30), fe, now)
    assert not gs._pu_due(rec("p", 500, fin=1), "month", date(2026, 9, 30), fe, now)
    assert not gs._pu_due(rec("w", 20), "month", date(2026, 9, 30), fe, now)
    assert gs._pu_due(rec("w", 24), "month", date(2026, 9, 30), fe, now)
    assert gs._pu_due(rec("s", 24, fin=1), "month", date(2026, 9, 30), fe, now)
    assert not gs._pu_due(rec("s", 23, fin=1), "month", date(2026, 9, 30), fe, now)
    assert gs._pu_due({"st": "?"}, "month", date(2026, 9, 30), fe, now)


def test_step_users_reads_the_due_periods_drops_old_ones_and_keeps_the_currency(monkeypatch, tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga, hs=date(2026, 8, 20))
    job.ga.max_calls = 60
    job.rd("t")["done"] = True                              # (the history complete: d0 stands still — the wait: its own test)
    root = str(tmp_path / "data" / gs.DIR)
    assert gs.store_d0(root, KEY) is None
    gs.step_users(job)                                      # an empty store: nothing to ask
    assert not ga.asked and not os.path.exists(gs.users_path(root, KEY))
    _t_days(job, gs._days(date(2026, 8, 20), FE))
    assert gs.store_d0(root, KEY) == "2026-08-20"
    props = []
    monkeypatch.setattr(ga4, "property_meta", lambda tok, pid: props.append(pid) or {"currency": "USD",
                                                                                      "time_zone": "Etc/GMT"})
    ga.token, ga.property_id = "tok", "111"
    stale = gu._now_iso(NOW - timedelta(days=9))
    os.makedirs(os.path.dirname(gs.users_path(root, KEY)), exist_ok=True)
    gs.write_json_gz_stable(gs.users_path(root, KEY), {"v": 1, "w": {"2026-10-20_2026-10-26": {"st": "w", "at": stale,
                                                                                               "r": [], "tot": 0}}})
    n = len(ga.asked)
    gs.step_users(job, months=1, calls=60)
    asked = ga.asked[n:]
    uf = gs.load_users(root, KEY)
    want = gs.pu_wanted(TODAY, date(2026, 8, 20))
    first = [k for k, _, _, kd in want if kd != "month"] + [[k for k, _, _, kd in want if kd == "month"][0]]
    assert sorted(uf["w"]) == sorted(first)                 # yesterday's week dropped, one month (newest) only
    assert len(asked) == 2 * len(first) and all("date" not in q.dims for q in asked)
    assert uf["prop"] == {"currency": "USD", "time_zone": "Etc/GMT", "at": gu._now_iso(NOW)} and props == ["111"]
    assert job.ga.max_calls == 60 + len(asked)              # the day reads after it keep their 60
    # the next run: the next month (newest first), the currency kept (a day not passed), the calls cap holds
    n = len(ga.asked)
    gs.step_users(job, months=4, calls=2)
    assert len(ga.asked) - n == 2 and props == ["111"]
    assert len(gs.load_users(root, KEY)["w"]) == len(first) + 1
    # a stop part way keeps every period read before it: today due again (its record aged), then the last month,
    # which the stop cuts after its first call
    uf = gs.load_users(root, KEY)
    tk = "%s_%s" % (TODAY, TODAY)
    uf["w"][tk]["at"] = stale
    gs.write_json_gz_stable(gs.users_path(root, KEY), uf)
    ga.stop_after = len(ga.asked) + 3
    with pytest.raises(gf.Stop):
        gs.step_users(job, months=4, calls=60)
    uf = gs.load_users(root, KEY)
    assert uf["w"][tk]["at"] == gu._now_iso(NOW) and "2026-08-20_2026-08-31" not in uf["w"]
    assert len(uf["w"]) == len(first) + 1
    ga.stop_after = None
    # a refused property read keeps the currency it had
    monkeypatch.setattr(ga4, "property_meta", lambda tok, pid: (_ for _ in ()).throw(RuntimeError("HTTP 403: no")))
    uf = gs.load_users(root, KEY)
    uf["prop"]["at"] = stale
    gs.step_property(job, uf)
    assert uf["prop"]["currency"] == "USD" and uf["prop"]["at"] == gu._now_iso(NOW) and uf["prop"]["err"] == 1   # (waits)


def test_a_bug_in_the_users_step_never_costs_the_day_reads_and_is_never_silent(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]
    _patch_routes(monkeypatch, apps)
    asked = _http(monkeypatch, Model())
    monkeypatch.setattr(gs, "step_users", lambda job: (_ for _ in ()).throw(KeyError("made-up")))
    data = str(tmp_path / "data")
    cfg = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
    out = gs.refresh_all(cfg, data, [dict(a) for a in apps], NOW, clock=lambda: 0.0, budget=1000)
    assert out["apps"] == {AID: "fetched"} and "error" not in out and asked
    assert all(r["done"] for r in gs.load_meta(data, KEY)["reads"].values())
    assert out["counts"]["periods_failed"] == 1 and out["counts"]["periods"] == 0
    line = gs.log_line(out)
    assert line.splitlines()[0].endswith(", periods 0, periods failed 1")
    assert line.splitlines()[1] == "ga4 screens periods skipped: KeyError" and "made-up" not in line
    from admob_iq import health
    got = []
    monkeypatch.setattr(health, "fault", lambda name, typ: got.append((name, typ)))
    health.scan(line.splitlines()[1])
    assert got == [("ga4 screens periods", "KeyError")]



def test_the_reviews_fixes_refunds_tiny_revenue_thresholding_d0_and_the_property(monkeypatch, tmp_path):
    # a refund day: own truth [-7.99, 2.00] is a day to split (its ad revenue by screen kept), never an empty record
    ga = FakeGA()
    job = _job(tmp_path, ga)
    _t_days(job, [FE])
    d = FE.isoformat()

    def refund(q, rows):
        if "totalRevenue" not in q.mets:
            return rows, {}
        if gs.SC not in q.dims:
            return [dict(r, totalRevenue=-7.99, totalAdRevenue=2.0) for r in rows], {}
        return ([{gs.SC: MAIN, "date": r.get("date"), "totalRevenue": -7.99, "totalAdRevenue": 2.0} for r in rows[:1]],
                {})
    ga.model.hook = refund
    recs, clean, _ = gs.read_chunk(job, "m", "c", FE, FE)
    assert recs[d]["st"] == "w" and recs[d]["t"] == [-7990000, 2000000] and recs[d]["r"] == [[MAIN, -7990000, 2000000]]
    # tiny revenue: GA4's per-row rounding inside the micros floor ties
    assert gs._tie([["a", 4], ["b", 4], ["c", 4]], None, 1, {"": 14}, gs.MIC_ABS)
    assert not gs._tie([["a", 4], ["b", 4], ["c", 4]], None, 1, {"": 14})
    # thresholded: kept, but never final (asked again a day on)
    ga.model.hook = _pu_hook(lambda q, rows: (rows, {"subjectToThresholding": True}))
    rec = gs.read_users(job, date(2026, 10, 1), FE)
    assert rec["thr"] == 1 and "fin" not in rec
    # an unreadable users file starts again (it is GA4's to read again), never an error every run
    root = str(tmp_path / "data" / gs.DIR)
    os.makedirs(os.path.dirname(gs.users_path(root, KEY)), exist_ok=True)
    with open(gs.users_path(root, KEY), "wb") as f:
        f.write(b"{oops")
    assert gs.load_users(root, KEY) == {"v": gs.PU_V, "w": {}}


def test_periods_from_d0_wait_for_the_truths_history_and_the_property_read_waits_too(monkeypatch, tmp_path):
    ga = FakeGA()
    job = _job(tmp_path, ga, hs=date(2026, 8, 20))
    job.ga.max_calls = 60
    root = str(tmp_path / "data" / gs.DIR)
    _t_days(job, gs._days(date(2026, 10, 10), FE))           # the history still filling: d0 = 10 Oct for now
    calls = []
    monkeypatch.setattr(ga4, "property_meta", lambda tok, pid: calls.append(pid) or (_ for _ in ()).throw(
        RuntimeError("HTTP 500")))
    ga.token, ga.property_id = "tok", "111"
    gs.step_users(job, months=4, calls=60)
    uf = gs.load_users(root, KEY)
    assert uf["w"] and all(not k.startswith("2026-10-10_") for k in uf["w"])   # nothing keyed on the moving d0
    assert calls == ["111"] and uf["prop"]["err"] == 1 and "currency" not in uf["prop"]
    gs.step_users(job, months=4, calls=60)                   # the failed property read waits a day
    assert calls == ["111"]
    job.rd("t")["done"] = True                               # the history complete: d0 stands still
    gs.step_users(job, months=4, calls=60)
    uf = gs.load_users(root, KEY)
    assert "2026-10-10_%s" % TODAY in uf["w"] and "2026-10-10_2026-10-31" in uf["w"]
    # a stopped property: no property read at all (its reads stop at the App's gate — not this fake's)
    uf["prop"] = {}
    gs.write_json_gz_stable(gs.users_path(root, KEY), uf)
    job.ga.prop = {"stop": "hour_low"}
    gs.step_users(job, months=4, calls=60)
    assert calls == ["111"]
