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
    assert blk["v"] == 2 and [p for p, _ in blk["periods"]] == ["today", "yday", "7", "30", "tm", "lm", "90"]
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
