"""📱 Devices — the fetch (admob_iq.fetch.ga4_device) and the ROI file's "dev" block (admob_iq.device_build), offline with a
fake GA4 and made-up models / countries / numbers: the three windows, the reads due (each once, newest install day first),
the truths in one call a kind, a call cap resumed next run, old install days dropped; the block's installs / paid share /
cost spread over the cell's paid installs (scaled back up on a folded day) / ROAS 7-30-90 / back next day / money back /
status, the coverage, the country lists and the small models summed apart."""
from datetime import date, datetime, timedelta, timezone

from admob_iq import device_build as dvb
from admob_iq.fetch import ga4_device as gd
from admob_iq.fetch import ga4_firstopen as gf

NOW = datetime(2026, 10, 31, 6, 0, tzinfo=timezone.utc)
F = date(2026, 10, 28)
# per install day and country: model → installs, paid installs, revenue a day per install, back next day share
MODELS = {"XM-1": (60, 50, 0.01, 0.5), "XM-2": (30, 25, 0.002, 0.3), "XM-3": (2, 2, 0.01, 0.5)}
CCS = {"XA": 1.0, "XB": 0.5}                          # country → its share of each model's installs


class FakeGA:
    def __init__(self, stop_after=None, fold=None):
        self.calls, self.asked, self.stop_after, self.fold = 0, [], stop_after, fold or {}
        self.last_metas, self.tok = [{}], 0

    def _cells(self, x, split):
        for md, (n, p, rpd, d1) in MODELS.items():
            for cc, sh in CCS.items():
                k = self.fold.get(md, 1.0) if split else 1.0      # GA4 folds only the split reads
                yield md, cc, n * sh * k, p * sh * k, rpd, d1

    def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise gf.Stop("calls")
        self.calls += 1
        self.asked.append((body, extra))
        dims = [d["name"] for d in body["dimensions"]]
        mets = [m["name"] for m in body["metrics"]]
        a = date.fromisoformat(body["dateRanges"][0]["startDate"])
        b = date.fromisoformat(body["dateRanges"][0]["endDate"])
        paid = any("firstUserGoogleAdsCampaignId" in str(e) for e in extra or [])
        xs = []
        for e in extra or []:
            f = e.get("filter") or {}
            if f.get("fieldName") == "firstSessionDate":
                if "inListFilter" in f:
                    xs = [date(int(v[:4]), int(v[4:6]), int(v[6:])) for v in f["inListFilter"]["values"]]
                else:
                    v = f["stringFilter"]["value"]
                    xs = [date(int(v[:4]), int(v[4:6]), int(v[6:]))]
        if "mobileDeviceBranding" in dims:            # the names read
            return [{"mobileDeviceModel": md, "mobileDeviceBranding": "XBrand", "mobileDeviceMarketingName": "Phone " + md[-1],
                     "newUsers": 1} for md in MODELS]
        rows = []
        for x in xs:
            for md, cc, n, p, rpd, d1 in self._cells(x, "mobileDeviceModel" in dims):
                d = a
                while d <= b:
                    age = (d - x).days
                    if age >= 0:
                        v = {"newUsers": (p if paid else n) if age == 0 else 0, "activeUsers": n * d1 if age == 1 else 0,
                             "totalAdRevenue": n * rpd}
                        row = {"mobileDeviceModel": md, "countryId": cc, "firstSessionDate": x.strftime("%Y%m%d"),
                               "date": d.strftime("%Y%m%d")}
                        row.update({m: v[m] for m in mets})
                        rows.append(row)
                    d += timedelta(days=1)
        return rows


def test_windows_and_reads_due():
    w = gd.windows(F)
    assert w[7] == (F - timedelta(days=33), F - timedelta(days=6))
    assert w[30] == (F - timedelta(days=56), F - timedelta(days=29))
    assert w[90] == (F - timedelta(days=116), F - timedelta(days=89))
    due = gd.todo({}, F)
    kinds = {}
    for k, x in due:
        kinds[k] = kinds.get(k, 0) + 1
    assert kinds == {"P": 79, "R7": 28, "D1": 28, "R30": 28, "R90": 28}   # the 7 / 30 windows share 5 days
    assert due[0][1] == F - timedelta(days=6)           # newest install day first


def test_step_reads_each_once_truths_in_one_call_and_resumes():
    ga, store = FakeGA(stop_after=40), {"v": gd.STORE_V}
    try:
        gd.step_app(ga, store, F, NOW)
        raise AssertionError("no stop")
    except gf.Stop:
        pass
    truth_calls = [b for b, e in ga.asked if [d["name"] for d in b["dimensions"]] == ["firstSessionDate", "date"]]
    assert len(truth_calls) == 5                       # one a kind for every install day due
    n_done = sum(len(v) for v in store["x"].values())
    assert 0 < n_done < 191 and store["names"]["XM-1"] == ["XBrand", "Phone 1"]
    ga2 = FakeGA()
    assert gd.step_app(ga2, store, F, NOW) == "fetched"
    assert sum(len(v) for v in store["x"].values()) == 191 and gd.todo(store, F) == []
    rec = store["x"][(F - timedelta(days=6)).isoformat()]
    assert rec["R7"]["t"] == [138, 7.14] and rec["R7"]["m"]["XM-1"]["XA"] == [60, 4.2]
    assert rec["P"]["t"] == 115.5 and rec["D1"]["t"] == 60
    ga3 = FakeGA()
    assert gd.step_app(ga3, store, F, NOW + timedelta(hours=1)) == "fresh" and ga3.calls == 0
    # a day later: old install days dropped, the newest due ones read
    store2 = dict(store)
    assert gd.step_app(FakeGA(), store2, F + timedelta(days=200), NOW) == "fetched"
    assert all(date.fromisoformat(k) >= F + timedelta(days=200 - gd.KEEP_DAYS) for k in store2["x"])


TODAY = F + timedelta(days=3)                       # the property's today (F = its newest final day)


def _full_store(fold=None):
    store = {"v": gd.STORE_V}
    for _ in range(12):                                 # the call cap: as many runs as it takes
        try:
            if gd.step_app(FakeGA(fold=fold), store, F, NOW, TODAY) == "fresh":
                break
        except gf.Stop:
            continue
    return store


def _cost(store, per_paid=0.4):
    """$per_paid a paid install on every install day × country of the store."""
    return {cc: {date.fromisoformat(k): (50 + 25 + 2) * sh * per_paid for k in store["x"]} for cc, sh in CCS.items()}


def test_period_reads_today_first_so_far_and_re_read_by_age():
    store = {"v": gd.STORE_V}
    due = gd.todo(store, F, TODAY, NOW)
    assert due[:5] == [("S", TODAY), ("P", TODAY), ("S", TODAY - timedelta(days=1)), ("P", TODAY - timedelta(days=1)),
                       ("D1", TODAY - timedelta(days=1))]            # today / yesterday first
    store = _full_store()
    assert store["today"] == TODAY.isoformat() and gd.todo(store, F, TODAY, NOW) == []
    s = store["x"][(TODAY - timedelta(days=10)).isoformat()]["S"]
    assert s["to"] == TODAY.isoformat() and s["t"] == [138, round(1.02 * 11, 4)]      # installs, revenue to today
    assert store["x"][(TODAY - timedelta(days=10)).isoformat()]["P"]["fin"] is True    # a final day's paid installs
    assert not store["x"][TODAY.isoformat()]["P"].get("fin")                           # today's: read again
    # an hour later nothing; three hours later the newest days again; a day later every S up to 31 days old
    assert gd.todo(store, F, TODAY, NOW + timedelta(hours=1)) == []
    again = gd.todo(store, F, TODAY, NOW + timedelta(hours=3))
    assert {k for k, _ in again} == {"S", "P", "D1"} and all((TODAY - x).days <= 2 for _, x in again)
    day = gd.todo(store, F, TODAY, NOW + timedelta(hours=21))
    assert sum(1 for k, x in day if k == "S") == 32 and max((TODAY - x).days for k, x in day if k == "S") == 31


def test_dev_block_periods_rows_kpis_verdicts():
    store = _full_store()
    curve = {"90_180": 1.5, "90_365": 2.0, "30_180": 3.0, "30_365": 4.0}
    blk = dvb.dev_block(store, _cost(store), set(), lambda X: 1.0, curve)
    # the owner's standard picker (3 Nov 2026), in his order — no Custom here (sums per button)
    assert blk["v"] == 2 and [p for p, _ in blk["periods"]] == ["today", "yday", "7", "tm", "lm", "30", "60", "90", "all"]
    xd = sorted(store["x"])
    assert blk["P"]["all"]["from"] == xd[0] and blk["P"]["all"]["to"] == TODAY.isoformat()      # All time: the store's first day
    assert blk["P"]["60"]["from"] == (TODAY - timedelta(days=60)).isoformat() and blk["P"]["60"]["days"] <= 60
    # the month mover (4 Nov 2026): every calendar month of the store as its own period — the current one up to today
    mons = sorted(k for k in blk["P"] if k.startswith("mon:"))
    first_m = date.fromisoformat(xd[0]).replace(day=1)
    assert mons[0] == "mon:%04d-%02d" % (first_m.year, first_m.month) and mons[-1] == "mon:%04d-%02d" % (TODAY.year, TODAY.month)
    cur = blk["P"][mons[-1]]
    assert cur["from"] == TODAY.replace(day=1).isoformat() and cur["to"] == TODAY.isoformat()
    assert all(blk["P"][k]["from"].endswith("-01") for k in mons) and len(mons) <= dvb.MONTHS_MAX
    assert [p for p, _ in blk["periods"]] == ["today", "yday", "7", "tm", "lm", "30", "60", "90", "all"]   # months: the mover only
    p30 = blk["P"]["30"]
    assert p30["days"] == 30 and p30["from"] == (TODAY - timedelta(days=30)).isoformat()
    t = p30["tot"]
    assert t["n"] == 138 * 30 and t["p"] == round(115.5 * 30) and abs(t["cost"] - 115.5 * 30 * 0.4) < 0.1
    rows = {r[0]: r for r in p30["rows"]}
    one = rows["XM-1"]                                  # [model, installs, paid, cost, revenue so far, back next day]
    assert one[1] == 2700 and one[2] == 2250 and abs(one[3] - 900) < 0.05 and one[5] == 0.5
    assert abs(one[4] - 0.9 * sum(j + 1 for j in range(1, 31))) < 0.1                # so far: older days longer
    assert blk["P"]["today"]["tot"]["n"] == 138 and blk["P"]["today"]["tot"]["d1"] is None
    assert blk["V"]["XM-1"][0] == "Profit" and blk["V"]["XM-2"][0] == "Slow" and blk["V"]["XM-3"][0] == "Too little data"
    assert blk["vcount"] == {"Loss": 0, "Slow": 1, "Profit": 1, "No ads": 0, "Too little data": 1}
    assert [c for c, _ in blk["cc"]] == ["XA", "XB"] and blk["P"]["30"]["by"]["XB"]["tot"]["n"] == 46 * 30
    assert blk["Vc"]["XA"]["XM-1"][0] == "Profit" and blk["names"]["XM-1"] == ["XBrand", "Phone 1"]
    assert blk["cov"]["S"] == 1.0 and blk["cov"]["P"] == 1.0


def test_loss_no_ads_and_too_little_data():
    store = _full_store()
    blk = dvb.dev_block(store, {}, set(), lambda X: 1.0, {"90_365": 1.1})
    assert {m: v[0] for m, v in blk["V"].items()} == {"XM-1": "No ads", "XM-2": "No ads", "XM-3": "Too little data"}
    blk = dvb.dev_block(store, _cost(store, 5.0), set(), lambda X: 1.0, {"90_365": 1.1, "30_365": 1.5})
    assert {m: v[0] for m, v in blk["V"].items() if m != "XM-3"} == {"XM-1": "Loss", "XM-2": "Loss"}
    assert dvb.status(None, {"n": 10, "cost": 1, "rev": 1}, None, 1.0, {}) == ("Too little data", None)


def test_a_folded_day_keeps_the_cost_per_install():
    store = _full_store(fold={"XM-2": 0.0})            # GA4 folds XM-2 away: coverage < 1
    blk = dvb.dev_block(store, _cost(store), set(), lambda X: 1.0, {})
    assert blk["cov"]["P"] < 0.7 and blk["cov"]["n"] < 0.7 and blk["cov"]["S"] < 0.95
    one = {r[0]: r for r in blk["P"]["30"]["rows"]}["XM-1"]
    assert abs(one[3] / one[2] - 0.4) < 1e-4            # its cost per paid install: not raised by the folded installs


def test_curve_of():
    T = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365]
    rows = [{"t": [0, 0, 0, 0, 0, 3, 0, 10, 15, 20]}, {"t": [0, 0, 0, 0, 0, 3, 0, 10, None, None]}]
    c = dvb.curve_of(rows, T)
    assert c["90_365"] == 2.0 and c["90_180"] == 1.5 and abs(c["30_365"] - 20 / 3) < 1e-9


def test_log_line_counts_only():
    assert gd.log_line({"counts": {"selected": 2, "with_ga4": 2, "fetched": 1, "calls": 9}}) == \
        "ga4 device: apps 2, with GA4 2, fetched 1, fresh 0, failed 0, deferred 0, waiting 0, calls 9, tokens 0"


def test_days_without_cost_do_not_lower_the_cpi():
    store = _full_store()
    unk = {TODAY, TODAY - timedelta(days=1)}           # Google Ads has not split these days by country yet
    blk = dvb.dev_block(store, _cost(store), unk, lambda X: 1.0, {})
    p7 = blk["P"]["7"]
    assert p7["nocost"] == 1 and p7["known"] is False
    t = p7["tot"]
    assert t["p"] == round(115.5 * 7) and t["pk"] == round(115.5 * 6)                  # yesterday's paid installs not in pk
    assert abs(t["cost"] / t["pk"] - 0.4) < 1e-4                                       # the CPI of the days with a cost
    one = {r[0]: r for r in p7["rows"]}["XM-1"]
    assert one[6] == 75 * 6 and abs(one[3] / one[6] - 0.4) < 1e-4
    td = blk["P"]["today"]
    assert td["nocost"] == 1 and td["tot"]["cost"] == 0 and td["tot"]["pk"] == 0


# ── store v2 (6 Nov 2026: All time): one folder an app, sharded by install month; nothing dropped ────────────────────
import gzip as _gzip
import json as _json
import os as _os

import pytest as _pytest

from admob_iq.fetch import ga4_uninstall as _gu

AIDV = "ca-app-pub-0000000000000000~41"
KEYV = _gu.file_key(AIDV)


def _days_of(view):
    return {k for k in view.get("x") or {}} | {k for k in view.get("aged") or {}}


def _all_days(data, key=KEYV):
    root = _os.path.join(data, gd.DIR)
    st = gd.Store(root, key)
    out = dict(st.recent())
    for m in st.months():
        for k, v in st.month(m).items():
            assert k not in out                         # every install day in ONE place
            out[k] = v
    return out


def test_store_v2_splits_recent_and_month_files_and_reads_back(tmp_path):
    store = _full_store()
    big = dict(store)
    xs = dict(store["x"])
    for i in range(140, 200):                          # older install days (the history job's, merged): kept for good
        x = F - timedelta(days=i)
        xs[x.isoformat()] = {"S": {"m": {"XM-1": {"XA": [3, 0.5]}}, "t": [3, 0.5], "at": "2026-10-01T00:00:00Z"}}
    big["x"] = xs
    data = str(tmp_path / "data")
    st = gd.Store(_os.path.join(data, gd.DIR), KEYV)
    st.save_view(big)
    cut = gd.cut_of(F).isoformat()
    rec = gd.Store(_os.path.join(data, gd.DIR), KEYV).recent()
    assert rec and min(rec) >= cut                      # the recent file: the hourly fetch's days only
    months = gd.Store(_os.path.join(data, gd.DIR), KEYV).months()
    assert months and all(m < cut[:7] or m == cut[:7] for m in months)
    meta = gd._read_gz(gd.meta_path(_os.path.join(data, gd.DIR), KEYV))
    assert set(meta["months"]) == set(months) and all(len(v) == 12 for v in meta["months"].values())
    assert "x" not in meta and meta["F"] == F.isoformat() and meta["names"]["XM-1"] == ["XBrand", "Phone 1"]
    assert set(_all_days(data)) == set(xs)              # nothing lost, nothing twice
    # a reader gets ONE dict: the meta + the recent days as "x"
    view = gd.load_store(gd.store_path(data, AIDV))
    assert view["x"] == rec and view["names"] == store["names"] and view["F"] == F.isoformat()


def test_aged_days_move_to_their_month_file_never_dropped(tmp_path):
    store = _full_store()
    n0 = {k for k in store["x"]}
    data = str(tmp_path / "data")
    st = gd.Store(_os.path.join(data, gd.DIR), KEYV)
    st.save_view(dict(store))
    later = F + timedelta(days=60)                     # 60 days on: the oldest install days age out of "x"
    view = gd.Store(_os.path.join(data, gd.DIR), KEYV).view()
    try:
        gd.step_app(FakeGA(stop_after=0), view, later, NOW + timedelta(days=60), later + timedelta(days=3))
    except gf.Stop:
        pass
    assert view.get("aged") and all(k < gd.cut_of(later).isoformat() for k in view["aged"])
    gd.Store(_os.path.join(data, gd.DIR), KEYV).save_view(view)
    assert n0 <= set(_all_days(data))                  # every day read before is still there


def test_v1_store_is_split_on_first_run_and_deleted_on_the_next(monkeypatch, tmp_path):
    data = str(tmp_path / "data")
    v1 = _full_store()
    v1.update(v=gd.V1, app_id=AIDV, package="com.example.alpha", property_id="111", stream_id="2111", time_zone="UTC")
    p = gd.store_path(data, AIDV)
    _os.makedirs(_os.path.dirname(p))
    with _gzip.open(p, "wt", encoding="utf-8") as fh:
        _json.dump(v1, fh)
    monkeypatch.setattr(gd.gf, "App", lambda *a, **k: FakeGA(stop_after=0))      # no GA4 call this run
    import threading
    args = ({"app_id": AIDV, "package": "com.example.alpha"}, {}, {"property_id": "111", "stream_id": "2111"},
            {"quota": None, "stop": None}, "tok", {"tz": {"111": "UTC"}}, data, NOW, "2026-10-31T06:00:00Z",
            None, dict.fromkeys(gd.COUNTS, 0), threading.Lock())
    assert gd._one_app(*args) == "deferred"
    assert _os.path.exists(p)                           # left one run: a bad v2 write can still fall back
    assert set(_all_days(data)) == set(v1["x"])
    meta = gd._read_gz(gd.meta_path(_os.path.join(data, gd.DIR), KEYV))
    assert meta["app_id"] == AIDV and meta["names"] == v1["names"] and meta["v"] == gd.STORE_V
    st = {}
    assert gd._one_app(*(args[:1] + (st,) + args[2:])) == "deferred"
    assert not _os.path.exists(p) and set(_all_days(data)) == set(v1["x"])      # v2 read fine: the v1 copy is gone
    assert gd.load_store(p)["names"] == v1["names"]


def test_an_unreadable_v2_file_is_never_written_over(tmp_path):
    data = str(tmp_path / "data")
    root = _os.path.join(data, gd.DIR)
    st = gd.Store(root, KEYV)
    view = _full_store()
    st.save_view(dict(view))
    old = F - timedelta(days=gd.KEEP_DAYS + 40)
    with open(gd.month_path(root, KEYV, old.isoformat()[:7]), "wb") as fh:
        fh.write(b"not gzip")
    before = open(gd.recent_path(root, KEYV), "rb").read()
    v = gd.Store(root, KEYV).view()
    v["aged"] = {old.isoformat(): {"S": {"m": {}, "t": [0, 0], "at": "2026-10-31T06:00:00Z"}}}
    with _pytest.raises(gd.StoreError):
        gd.Store(root, KEYV).save_view(v)
    assert open(gd.month_path(root, KEYV, old.isoformat()[:7]), "rb").read() == b"not gzip"
    assert open(gd.recent_path(root, KEYV), "rb").read() == before
    assert gd.load_store(gd.store_path(data, AIDV))["x"]          # a reader still gets what is readable


def test_keep_new_whole_never_gives_way_to_a_folded_record():
    whole = {"m": {"XM-1": {"XA": [10, 1.0]}}, "t": [10, 1.0], "at": "2026-10-01T00:00:00Z"}
    folded = {"m": {"XM-1": {"XA": [5, 0.5]}}, "t": [10, 1.0], "at": "2026-10-02T00:00:00Z"}
    newer = dict(whole, at="2026-10-03T00:00:00Z")
    assert gd.keep_new(None, whole) and not gd.keep_new(whole, None)
    assert not gd.keep_new(whole, folded)               # read later, but folded: the whole one stays
    assert gd.keep_new(folded, newer) and gd.keep_new(whole, newer)
    assert not gd.keep_new(newer, whole)                # an older read never replaces a newer one
    assert gd._whole({"m": {}, "t": 0}) and gd._whole({"m": {}, "t": [0, 0]}) and not gd._whole({"m": {}})


def test_names_all_reads_the_whole_life_a_year_a_call_and_names_accumulate():
    class G(FakeGA):
        def report_all(self, body, event=None, events=None, extra=None, page_rows=None):
            self.calls += 1
            a = body["dateRanges"][0]["startDate"]
            self.asked.append((a, body["dateRanges"][0]["endDate"]))
            nm = "Old" if a < "2025-01-01" else "New"
            return [{"mobileDeviceModel": "XM-1", "mobileDeviceBranding": "XBrand", "mobileDeviceMarketingName": nm,
                     "newUsers": 5},
                    {"mobileDeviceModel": "XM-OLD", "mobileDeviceBranding": "XBrand", "mobileDeviceMarketingName": "Gone",
                     "newUsers": 1},
                    {"mobileDeviceModel": "(other)", "newUsers": 9}]
    ga = G()
    got = gd.names_all(ga, date(2023, 8, 20), date(2026, 10, 28))
    assert ga.calls == 4 and ga.asked[0][0] == "2023-08-20" and ga.asked[-1][1] == "2026-10-28"
    assert got == {"XM-1": ["XBrand", "New"], "XM-OLD": ["XBrand", "Gone"]}       # the newest range's name wins
    store = {"v": gd.STORE_V, "names": {"XM-OLD": ["XBrand", "Gone"]}}
    try:
        gd.step_app(FakeGA(stop_after=1), store, F, NOW)
    except gf.Stop:
        pass
    assert store["names"]["XM-OLD"] == ["XBrand", "Gone"] and store["names"]["XM-1"] == ["XBrand", "Phone 1"]


# ── v3: every window from per-install-day cells (6 Nov 2026: All time + the standard picker + Custom) ───────────────
FIRST = date(2026, 1, 20)                               # the made-up app's first install day (months of history)


def _old_day(x, at="2026-10-20T00:00:00Z", to=None, folded=1.0):
    """S / P / D1 of an install day older than the hourly fetch's, as the history job stores them."""
    s, p, d, tn, trev, tp, td = {}, {}, {}, 0, 0.0, 0, 0
    days = ((to or F) - x).days + 1
    for md, (n, pd, rpd, d1) in MODELS.items():
        for cc, sh in CCS.items():
            nn = n * sh
            s.setdefault(md, {})[cc] = [nn * folded, round(nn * rpd * days * folded, 4)]
            p.setdefault(md, {})[cc] = pd * sh * folded
            d.setdefault(md, {})[cc] = nn * d1 * folded
            tn += nn
            trev += nn * rpd * days
            tp += pd * sh
            td += nn * d1
    return {"S": {"m": s, "t": [tn, round(trev, 4)], "to": (to or F).isoformat(), "at": at, "f": None},
            "P": {"m": p, "t": tp, "at": at, "fin": True},
            "D1": {"m": d, "t": td, "at": at, "fin": True}}


def _v3_store(tmp_path, old_from=FIRST, skip=()):
    """A v2 store on disk: the hourly fetch's recent days (_full_store) + month files from old_from on."""
    data = str(tmp_path / "data")
    store = _full_store()
    store.update(app_id=AIDV, stream_id="2111")
    root = _os.path.join(data, gd.DIR)
    st = gd.Store(root, KEYV)
    old = {}
    x = old_from
    cut = gd.cut_of(F)
    while x < cut:
        if x.isoformat() not in skip:
            old[x.isoformat()] = _old_day(x)
        x += timedelta(days=1)
    v = dict(store)
    v["x"] = {k: dict(r) for k, r in store["x"].items()}
    while x <= TODAY - timedelta(days=gd.RANGE_DAYS):  # the recent file's days older than the period view: the job's
        k = x.isoformat()
        if k not in skip:
            for kind, rec in _old_day(x).items():
                v["x"].setdefault(k, {}).setdefault(kind, rec)
        x += timedelta(days=1)
    v["aged"] = old
    st.save_view(v)
    return data


def _cost_all(lo, hi, per_paid=0.4):
    out = {}
    x = lo
    while x <= hi:
        for cc, sh in CCS.items():
            out.setdefault(cc, {})[x] = (50 + 25 + 2) * sh * per_paid
        x += timedelta(days=1)
    return out


def _bt(data, out, cost=None, unk=(), kq=None, info=None, first=FIRST, k=1.0):
    return dvb.build_app(data, KEYV, _cost_all(FIRST, TODAY) if cost is None else cost, set(unk), lambda X: k,
                         kq or (lambda X: False), {"90_180": 1.5, "90_365": 2.0, "30_180": 3.0, "30_365": 4.0},
                         first, out, info)


def _load(out, name):
    with _gzip.open(_os.path.join(out, name), "rt", encoding="utf-8") as fh:
        return _json.load(fh)


def test_v3_buttons_equal_the_v2_block_on_the_same_store(tmp_path):
    data = _v3_store(tmp_path)
    out = str(tmp_path / "site")
    stub, files = _bt(data, out)
    assert stub["v"] == 3 and stub["file"] == "roi_%s_dv.json.gz" % KEYV and len(stub["sha"]) == 12
    D = _load(out, stub["file"])
    assert [k for k, _ in D["periods"]] == ["today", "yday", "7", "tm", "lm", "30", "60", "90", "all", "cus"]
    assert D["periods"][2][1] == "Last 7 days" and D["periods"][8][1] == "All time" and D["periods"][9][1] == "Custom"
    view = gd.load_store(gd.store_path(data, AIDV))
    v2 = dvb.dev_block(view, _cost_all(FIRST, TODAY), set(), lambda X: 1.0,
                       {"90_180": 1.5, "90_365": 2.0, "30_180": 3.0, "30_365": 4.0})
    for pid in ("today", "yday", "7", "tm", "lm", "30", "60", "90"):
        a, b = v2["P"][pid], D["P"][pid]
        assert (a["from"], a["to"]) == (b["from"], b["to"])
        rows2 = {r[0]: r for r in a["rows"]}
        for r in b["rows"]:                             # [model, n, p, cost, rev, d1, dn, pk] vs v2's d1 share
            o = rows2[r[0]]
            # (v2 rounded the counts; v3 keeps GA4's — whole numbers on real data, halves on this made-up one)
            assert (o[1], o[2], o[6]) == (round(r[1]), round(r[2]), round(r[7]))
            assert abs(o[3] - r[3]) < 0.01 and abs(o[4] - r[4]) < 0.01
            assert o[5] == (round(r[5] / r[6], 4) if r[6] else None)
        assert a["tot"]["n"] == round(b["tot"]["n"]) and abs(a["tot"]["cost"] - b["tot"]["cost"]) < 0.01
        assert b["u"][0] == (gd_d(b["to"]) - gd_d(b["from"])).days + 1
    assert D["V"] == v2["V"] and D["vcount"] == v2["vcount"] and D["cov"]["R7"] == v2["cov"]["R7"]
    # All time: from the app's first install day, every month (old months from their files)
    al = D["P"]["all"]
    assert al["from"] == FIRST.isoformat() and al["to"] == TODAY.isoformat()
    days_all = (TODAY - FIRST).days + 1
    assert al["u"][0] == days_all and al["u"][1] == days_all and al["tot"]["n"] == 138 * days_all
    assert [m[0] for m in D["months"]] == dvb.month_list(FIRST, TODAY)
    assert D["names"]["XM-1"] == ["XBrand", "Phone 1"] and [c for c, _ in D["cc"]] == ["XA", "XB"]


def gd_d(s):
    return date.fromisoformat(s)


def test_v3_month_files_sum_the_days_and_all_time_sums_the_months(tmp_path):
    data = _v3_store(tmp_path)
    out = str(tmp_path / "site")
    stub, files = _bt(data, out)
    D = _load(out, stub["file"])
    tot = {}
    for m, u, sm, sd in D["months"]:
        assert sm and sd and dvb.dv_name(KEYV, "dvm", m) in files and dvb.dv_name(KEYV, "dvd", m) in files
        M_ = _load(out, dvb.dv_name(KEYV, "dvm", m))
        Dd = _load(out, dvb.dv_name(KEYV, "dvd", m))
        mc = dvb.dec(M_, M_["c"])
        sums = {}
        uu = dvb.unit0(0)
        for X, e in Dd["X"].items():
            dvb.cells_add(sums, dvb.dec(Dd, e["c"]))
            uu = dvb.unit_add(uu, e["u"])
        dvb.cells_round(sums)
        assert sums == mc                               # a month = the sum of its install days, cell for cell
        assert uu[1:5] == M_["u"][1:5] and M_["u"] == u
        dvb.cells_add(tot, mc)
    dvb.cells_round(tot)
    rows, rest, t = dvb.plist(tot)
    assert [r[:3] for r in rows] == [r[:3] for r in D["P"]["all"]["rows"]] and t == D["P"]["all"]["tot"]
    xa = dvb.plist(tot, "XA", dvb.MIN_ROW, dvb.MAX_ROWS_CC)
    assert xa[2] == D["P"]["all"]["by"]["XA"]["tot"]


def test_v3_cache_hit_and_a_miss_on_a_cost_change(tmp_path):
    data = _v3_store(tmp_path)
    out = str(tmp_path / "site")
    i1 = {}
    s1, _ = _bt(data, out, info=i1)
    D1 = _load(out, s1["file"])
    i2 = {}
    s2, _ = _bt(data, out, info=i2)
    hot0 = (TODAY - timedelta(days=gd.RANGE_DAYS)).replace(day=1)
    cold = [m for m in dvb.month_list(FIRST, TODAY) if m < hot0.isoformat()[:7]]
    assert i1.get("cached", 0) == 0 and i2["cached"] == len(cold) and s1["sha"] == s2["sha"]
    # Google Ads fills a hole of an old month: only that month is built again, All time follows
    cost = _cost_all(FIRST, TODAY)
    x = date(2026, 3, 10)
    for cc in cost:
        cost[cc][x] = cost[cc][x] * 3
    i3 = {}
    s3, _ = _bt(data, out, cost=cost, info=i3)
    D3 = _load(out, s3["file"])
    assert i3["cached"] == len(cold) - 1 and s3["sha"] != s1["sha"]
    assert abs(D3["P"]["all"]["tot"]["cost"] - D1["P"]["all"]["tot"]["cost"] - 2 * 77 * 1.5 * 0.4) < 0.01
    mar = [m for m in D3["months"] if m[0] == "2026-03"][0]
    assert mar[2] != [m for m in D1["months"] if m[0] == "2026-03"][0][2]        # its month file was built again
    fresh = str(tmp_path / "fresh")                     # the cached sums = a build from scratch
    s4, _ = _bt(data, fresh, cost=cost)
    D4 = _load(fresh, s4["file"])
    assert D3["P"]["all"]["tot"] == D4["P"]["all"]["tot"] and D3["P"]["all"]["rows"] == D4["P"]["all"]["rows"]
    assert D3["P"]["all"]["by"] == D4["P"]["all"]["by"] and s3["sha"] == s4["sha"]


def test_v3_days_still_filling_no_admob_match_and_old_revenue_dates(tmp_path):
    skip = {(date(2026, 2, 1) + timedelta(days=i)).isoformat() for i in range(10)}     # 10 old days not filled yet
    data = _v3_store(tmp_path, skip=skip)
    out = str(tmp_path / "site")
    stub, _ = _bt(data, out, kq=lambda X: X < date(2026, 3, 1))                     # Jan, Feb: no AdMob match
    D = _load(out, stub["file"])
    U = D["U"]
    al = D["P"]["all"]["u"]
    days_all = (TODAY - FIRST).days + 1
    assert al[U.index("y")] == days_all and al[U.index("d")] == days_all - 10
    feb = [m for m in D["months"] if m[0] == "2026-02"][0]
    assert feb[1][U.index("y")] == 28 and feb[1][U.index("d")] == 18 and feb[1][U.index("kq")] == 18
    assert al[U.index("kq")] == (date(2026, 3, 1) - FIRST).days - 10
    assert al[U.index("to")] == F.isoformat()                                         # the oldest revenue date
    assert D["P"]["30"]["u"][U.index("kq")] == 0 and D["P"]["30"]["u"][U.index("d")] == 30
    jan = [m for m in D["months"] if m[0] == "2026-01"][0]
    assert jan[1][U.index("y")] == 12                                                 # 20 … 31 Jan (from the first day)
    # a month with nothing read: listed, no files
    data2 = _v3_store(tmp_path / "b", old_from=date(2026, 4, 1))
    out2 = str(tmp_path / "site2")
    D2 = _load(out2, _bt(data2, out2)[0]["file"])
    m2 = {m[0]: m for m in D2["months"]}
    assert m2["2026-02"][2] is None and m2["2026-02"][3] is None and m2["2026-02"][1][U.index("d")] == 0
    assert D2["P"]["all"]["u"][U.index("d")] < D2["P"]["all"]["u"][U.index("y")]


def test_v3_a_file_over_the_limit_is_not_written_and_the_last_copy_stays(monkeypatch, tmp_path):
    data = _v3_store(tmp_path)
    out = str(tmp_path / "site")
    stub, files = _bt(data, out)
    m = "2026-03"
    before = open(_os.path.join(out, dvb.dv_name(KEYV, "dvd", m)), "rb").read()
    cost = _cost_all(FIRST, TODAY)
    for cc in cost:
        cost[cc][date(2026, 3, 5)] *= 2                 # March changes …
    monkeypatch.setattr(dvb, "MAX_GZ", 300)             # … but its day file would be over the limit
    info = {}
    try:
        _bt(data, out, cost=cost, info=info)
    except dvb.TooBigError:
        pass                                            # (the buttons' file is over it too: the caller keeps its stub)
    assert info.get("toobig", 0) >= 1
    assert open(_os.path.join(out, dvb.dv_name(KEYV, "dvd", m)), "rb").read() == before


def test_v3_over_the_limit_the_month_stays_whole_and_without_a_copy_it_is_a_gap(monkeypatch, tmp_path):
    data = _v3_store(tmp_path)
    out = str(tmp_path / "site")
    D1 = _load(out, _bt(data, out)[0]["file"])
    m = "2026-03"
    e1 = [e for e in D1["months"] if e[0] == m][0]
    before = {k: open(_os.path.join(out, dvb.dv_name(KEYV, k, m)), "rb").read() for k in ("dvm", "dvd")}
    cost = _cost_all(FIRST, TODAY)
    for cc in cost:
        cost[cc][date(2026, 3, 5)] *= 2                 # March changes (its unit too) …
    real = dvb._gz_new
    monkeypatch.setattr(dvb, "MAX_GZ", 10 ** 6)

    def big(path, raw):                                 # … but its day file would be over the limit
        z, n = real(path, raw)
        return (b"x" * (dvb.MAX_GZ + 1), None) if "_dvd_" + m in path and z is not None else (z, n)
    monkeypatch.setattr(dvb, "_gz_new", big)
    info = {}
    D2 = _load(out, _bt(data, out, cost=cost, info=info)[0]["file"])
    e2 = [e for e in D2["months"] if e[0] == m][0]
    assert info["toobig"] == 1 and e2 == e1             # the last good copy WHOLE: its unit with its files' sha1
    assert {k: open(_os.path.join(out, dvb.dv_name(KEYV, k, m)), "rb").read() for k in ("dvm", "dvd")} == before
    assert _load(out, dvb.dv_name(KEYV, "dvm", m))["u"] == e2[1]          # (the page's consistency check holds)
    assert _load(data, _os.path.join(gd.DIR, KEYV, "agg.json.gz"))["months"][m]["k"] is None    # tried again
    # no copy to keep (a new site folder): the month is marked, never shown as 0 installs in silence
    out2 = str(tmp_path / "site2")
    D3 = _load(out2, _bt(data, out2, cost=cost)[0]["file"])
    e3 = [e for e in D3["months"] if e[0] == m][0]
    assert e3[2] is None and e3[3] is None and e3[4] == 1
    assert all(len(e) == 4 for e in D3["months"] if e[0] != m)


def test_v3_an_unreadable_store_month_is_never_built_as_an_empty_one(tmp_path, capsys):
    data = _v3_store(tmp_path)
    out = str(tmp_path / "site")
    D1 = _load(out, _bt(data, out)[0]["file"])
    m = "2026-03"
    with open(gd.month_path(_os.path.join(data, gd.DIR), KEYV, m), "wb") as fh:
        fh.write(b"not gzip")                           # (its size changes: the month's key too)
    capsys.readouterr()
    info = {}
    D2 = _load(out, _bt(data, out, info=info)[0]["file"])
    assert capsys.readouterr().err.count("devices skipped: StoreError") == 1 and info["bad"] == 1
    assert [e for e in D2["months"] if e[0] == m] == [e for e in D1["months"] if e[0] == m]     # the last good files
    assert D2["P"]["all"]["tot"] == D1["P"]["all"]["tot"]                                       # All time not lowered
    assert _load(data, _os.path.join(gd.DIR, KEYV, "agg.json.gz"))["months"][m]["k"] is None    # never cached
    out2 = str(tmp_path / "site2")                      # no copy: marked for the page
    D3 = _load(out2, _bt(data, out2)[0]["file"])
    assert [e for e in D3["months"] if e[0] == m][0][4] == 1


def test_v3_a_cache_write_that_fails_is_said(monkeypatch, tmp_path, capsys):
    data = _v3_store(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    monkeypatch.setattr(dvb, "agg_path", lambda d, k: str(blocker / "agg.json.gz"))
    capsys.readouterr()
    assert _bt(data, str(tmp_path / "site"))[0]["v"] == 3      # the files are written, the page is whole
    assert "devices cache skipped: " in capsys.readouterr().err


def test_v3_a_stopped_history_job_is_marked_for_the_page(tmp_path):
    data = _v3_store(tmp_path)
    st = gd.Store(_os.path.join(data, gd.DIR), KEYV)
    st.meta["bf"] = {"A": {"done": False}, "at": "2020-01-01T00:00:00Z"}    # its last word: long ago
    st.save_meta()
    out = str(tmp_path / "site")
    h = _load(out, _bt(data, out)[0]["file"])["hist"]
    assert h["on"] is True and h["stale"] is True


def test_v3_store_without_history_and_a_v1_store(tmp_path):
    # only the hourly fetch's days (no month files): All time starts at the store's first day with S
    data = str(tmp_path / "data")
    store = _full_store()
    gd.Store(_os.path.join(data, gd.DIR), KEYV).save_view(dict(store))
    out = str(tmp_path / "site")
    stub, _ = _bt(data, out, first=None)
    D = _load(out, stub["file"])
    s_days = sorted(k for k, v in store["x"].items() if v.get("S"))
    assert D["first"] == s_days[0] and D["P"]["all"]["u"][1] == len(s_days)
    # a v1 file (not split yet): the same block
    d1 = str(tmp_path / "v1")
    p = gd.store_path(d1, AIDV)
    _os.makedirs(_os.path.dirname(p))
    v1 = dict(store, v=gd.V1)
    with _gzip.open(p, "wt", encoding="utf-8") as fh:
        _json.dump(v1, fh)
    o1 = str(tmp_path / "s1")
    s1, _ = _bt(d1, o1, first=None)
    assert _load(o1, s1["file"])["P"] == D["P"]
    assert dvb.build_app(str(tmp_path / "none"), KEYV, {}, set(), lambda X: 1.0, lambda X: False, {}, None,
                         str(tmp_path / "s0")) is None
