"""📱 Devices All time — the history job (admob_iq.fetch.ga4_device: backfill_all, fill, refresh, merge_staged,
prune_merged, bf_line) and its workflow, offline: the real App / paging / quota gate run against a fake GA4 answered
from a made-up model (two phone models, two countries, install days with and without installs, paid installs only
after a made-up spend start). Checked: phase A (the last year) before B, newest month first, never an install day the
hourly fetch reads; the truths one call a kind a month; S month-batched, P / D1 one day a call and none for a day whose
truth is 0; resume from either store (a day is never read twice); a property at its floor or answering 429 waits while
another goes on; the merge's rules (the hourly fetch's days never copied, a whole record never replaced by a folded
one, idempotent, a broken file counted); phase R; the counts-only lines. No real data."""
import gzip
import json
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_device as gd
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 11, 6, 6, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 6)
F = ga4.window_end_in("UTC", NOW) - timedelta(days=gd.LATE)
TOP = TODAY - timedelta(days=gd.RANGE_DAYS)             # the newest install day the job reads
HS = date(2025, 6, 10)                                  # the made-up app's first install day
SPEND = date(2026, 3, 1)                                # paid installs from here on
AID = "ca-app-pub-0000000000000000~31"
AID2 = "ca-app-pub-0000000000000000~32"
KEY, KEY2 = gu.file_key(AID), gu.file_key(AID2)
MODELS = {"XM-1": 0.6, "XM-2": 0.4}
CCS = {"XA": 0.75, "XB": 0.25}
RPD = 0.01                                              # revenue a user a day of activity


def n_of(x, hs=HS):
    """Installs of install day x: 0 on every 9th day (and before hs), else 20 or 40."""
    if x < hs or x.day % 9 == 0:
        return 0
    return 40 if x.toordinal() % 2 else 20


def _ymd(s):
    return date(int(s[:4]), int(s[4:6]), int(s[6:]))


class Q:
    def __init__(self, body):
        self.dims = tuple(d["name"] for d in body.get("dimensions") or [])
        self.mets = tuple(m["name"] for m in body.get("metrics") or [])
        r = body["dateRanges"][0]
        self.a, self.b = date.fromisoformat(r["startDate"]), date.fromisoformat(r["endDate"])
        self.xs, self.paid = [], False
        for e in (body.get("dimensionFilter") or {}).get("andGroup", {}).get("expressions", []):
            f = e.get("filter") or {}
            if f.get("fieldName") == "firstSessionDate":
                if "inListFilter" in f:
                    self.xs = [_ymd(v) for v in f["inListFilter"]["values"]]
                else:
                    self.xs = [_ymd(f["stringFilter"]["value"])]
            if f.get("fieldName") == gd.CAMP:
                self.paid = True
        self.limit, self.offset = body.get("limit") or 10 ** 9, body.get("offset") or 0


def rows_for(q, hs=HS):
    """The made-up GA4 answer for one request."""
    if "mobileDeviceBranding" in q.dims:
        return [{"mobileDeviceModel": m, "mobileDeviceBranding": "XBrand", "mobileDeviceMarketingName": "Phone " + m[-1],
                 "newUsers": 5} for m in MODELS]
    out = []
    for x in q.xs:
        n = n_of(x, hs)
        if not n:
            continue
        p = n // 2 if x >= SPEND else 0
        split = gd.MODEL in q.dims
        cells = [(m, c, ms * cs) for m, ms in MODELS.items() for c, cs in CCS.items()] if split else [(None, None, 1.0)]
        for m, c, sh in cells:
            base = (p if q.paid else n) * sh
            if "date" in q.dims:                        # the truths: firstSessionDate × date
                d = max(q.a, x)
                while d <= q.b:
                    v = {"newUsers": base if d == x else 0, "activeUsers": n * sh * 0.25 if d == x + timedelta(days=1)
                         else 0, "totalAdRevenue": base * RPD}
                    if any(v[k] for k in q.mets):
                        row = {"firstSessionDate": x.strftime("%Y%m%d"), "date": d.strftime("%Y%m%d")}
                        row.update({k: v[k] for k in q.mets})
                        out.append(row)
                    d += timedelta(days=1)
                continue
            lo, hi = max(q.a, x), q.b
            if hi < lo:
                continue
            v = {"newUsers": base if lo <= x <= hi else 0,
                 "activeUsers": n * sh * 0.25 if lo <= x + timedelta(days=1) <= hi else 0,
                 "totalAdRevenue": base * RPD * ((hi - lo).days + 1)}
            if not any(v[k] for k in q.mets):
                continue
            row = {}
            if "firstSessionDate" in q.dims:
                row["firstSessionDate"] = x.strftime("%Y%m%d")
            if split:
                row.update(mobileDeviceModel=m, countryId=c)
            row.update({k: v[k] for k in q.mets})
            out.append(row)
    return out


def _http(monkeypatch, quota=None, fail=None, hs=HS):
    """ga4._call answered by rows_for (the real App, report_all, paging and gate run); quota(pid, n) → propertyQuota,
    fail(pid, n) → an exception to raise. → [(property id, Q)] asked."""
    asked = []
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)

    def call(method, url, token, body=None, params=None):
        pid = url.split("properties/")[1].split(":")[0]
        n = sum(1 for p, _ in asked if p == pid)
        if fail:
            e = fail(pid, n)
            if e:
                raise e
        q = Q(body)
        asked.append((pid, q))
        rows = rows_for(q, hs)
        page = rows[q.offset:q.offset + q.limit]
        return {"dimensionHeaders": [{"name": d} for d in q.dims], "metricHeaders": [{"name": m} for m in q.mets],
                "rows": [{"dimensionValues": [{"value": r.get(d, "")} for d in q.dims],
                          "metricValues": [{"value": str(r[m])} for m in q.mets]} for r in page],
                "rowCount": len(rows), "metadata": {},
                "propertyQuota": (quota(pid, n) if quota else None) or {"tokensPerDay": {"consumed": 2,
                                                                                         "remaining": 190000}}}
    monkeypatch.setattr(ga4, "_call", call)
    return asked


def _routes(monkeypatch, apps, hs=HS):
    routes = {a["package"]: {"property_id": a["pid"], "stream_id": "2" + a["pid"], "owner": "o"} for a in apps}
    monkeypatch.setattr(gd.gu, "load_state", lambda d: {"routes": {"by_package": routes},
                                                        "tz": {a["pid"]: "UTC" for a in apps},
                                                        "fetch": {a["app_id"]: {"package": a["package"]} for a in apps}})
    monkeypatch.setattr(gd.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": hs.isoformat()})
    monkeypatch.setattr(ga4, "access_token", lambda c, s, r: "tok")


CFG = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
APPS = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"}]


def _staged_days(staged, key=KEY):
    st = gd.Store(staged, key)
    out = {}
    for m in st.months():
        out.update(st.month(m))
    return out


def _kind(q):
    if "mobileDeviceBranding" in q.dims:
        return "names"
    if "date" in q.dims:
        return "T" + ("P" if q.paid else "D1" if "activeUsers" in q.mets else "S")
    if "firstSessionDate" in q.dims:
        return "Sb"
    return "P" if q.paid else "D1" if "activeUsers" in q.mets else "S1"


def test_the_history_fills_every_old_install_day_newest_first_a_before_b(monkeypatch, tmp_path):
    _routes(monkeypatch, APPS)
    asked = _http(monkeypatch)
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    pushes, lines = [], []
    out = gd.backfill_all(CFG, data, staged, [dict(a) for a in APPS], NOW, clock=lambda: 0.0, workers=2,
                          push=lambda: pushes.append(1) or True, say=lines.append, tick=0.01)
    assert out["apps"] == {AID: "done"} and out["pushed"] and pushes and "error" not in out
    days = _staged_days(staged)
    want = {(HS + timedelta(days=i)).isoformat() for i in range((TOP - HS).days + 1)}
    assert set(days) == want                            # every install day hs … today − RANGE_DAYS, none newer
    assert all(set(v) == {"S", "P", "D1"} for v in days.values())
    # S month-batched: one S call a month (≤ S_BATCH_N installs), one truth call a kind a month (the month the last
    # year starts in is read in two parts: its phase A days, later its phase B ones)
    kinds = [_kind(q) for _, q in asked]
    a0 = TODAY - timedelta(days=gd.A_DAYS)
    parts = len(gd._months_desc(a0, TOP)) + len(gd._months_desc(HS, a0 - timedelta(days=1)))
    assert parts == len({d[:7] for d in want}) + 1
    assert kinds.count("Sb") == parts and kinds.count("TS") == parts
    assert kinds.count("TP") == kinds.count("TD1") == parts and kinds.count("S1") == 0
    # P / D1 one day a call — and none for a day whose truth is 0 (no installs / no paid installs)
    p_days = [q.xs[0] for _, q in asked if _kind(q) == "P"]
    assert sorted(p_days) == sorted(x for x in (date.fromisoformat(d) for d in want) if n_of(x) and x >= SPEND)
    d1_days = [q.xs[0] for _, q in asked if _kind(q) == "D1"]
    assert sorted(d1_days) == sorted(x for x in (date.fromisoformat(d) for d in want) if n_of(x))
    # newest first, phase A (the last year) before phase B
    sb = [min(q.xs) for _, q in asked if _kind(q) == "Sb"]
    assert sb == sorted(sb, reverse=True) and sb[0].strftime("%Y-%m") == TOP.strftime("%Y-%m")
    assert max(x for x in sb if x < TODAY - timedelta(days=gd.A_DAYS)) < min(
        x for x in sb if x >= TODAY - timedelta(days=gd.A_DAYS))
    # the records: truth beside the split, revenue so far to F, the call's tokens, the batch's size
    x = TOP - timedelta(days=3) if n_of(TOP - timedelta(days=3)) else TOP - timedelta(days=4)
    s = days[x.isoformat()]["S"]
    n = n_of(x)
    assert s["t"][0] == n and s["m"]["XM-1"]["XA"][0] == n * 0.45 and s["to"] == F.isoformat() and s["b"] > 1
    assert abs(s["t"][1] - n * RPD * ((F - x).days + 1)) < 1e-6 and "tok" in s
    zero = next(d for d in sorted(want) if not n_of(date.fromisoformat(d)))
    assert days[zero]["S"]["m"] == {} and days[zero]["S"]["t"] == [0, 0] and days[zero]["P"]["t"] == 0
    meta = gd._read_gz(gd.meta_path(staged, KEY))
    assert meta["bf"]["A"]["done"] and meta["bf"]["B"]["done"] and meta["bf"]["R"]["at"]
    assert meta["names"]["XM-1"] == ["XBrand", "Phone 1"] and meta["names_all_at"]
    line = gd.bf_line(out)
    assert line.startswith("devices backfill: apps 1, with GA4 1, done 1, deferred 0, failed 0, waiting 0, days read %d"
                           % len(want))
    assert "example" not in line and KEY not in line and AID not in line and "XM-" not in line
    # a second run: nothing left to read (resume = the stores)
    asked.clear()
    out2 = gd.backfill_all(CFG, data, staged, [dict(a) for a in APPS], NOW, clock=lambda: 0.0, workers=1, tick=0.01)
    assert out2["apps"] == {AID: "done"} and [k for k in (_kind(q) for _, q in asked) if k != "names"] == []


def test_a_stop_resumes_where_it_was_and_no_day_is_read_twice(monkeypatch, tmp_path):
    _routes(monkeypatch, APPS)
    asked = _http(monkeypatch)
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    t = [0.0]

    def clock():                                        # every call 1 s: the job's 40 s clock runs out mid-way
        t[0] += 0.5
        return t[0]
    out = gd.backfill_all(CFG, data, staged, [dict(a) for a in APPS], NOW, clock=clock, budget=40, workers=1,
                          tick=0.01)
    assert out["apps"] == {AID: "deferred"} and 0 < len(_staged_days(staged))
    first = list(asked)
    out2 = gd.backfill_all(CFG, data, staged, [dict(a) for a in APPS], NOW, clock=lambda: 0.0, workers=1, tick=0.01)
    assert out2["apps"] == {AID: "done"}
    one_day = [(_kind(q), q.xs[0]) for _, q in first + asked[len(first):] if _kind(q) in ("P", "D1")]
    assert len(one_day) == len(set(one_day))            # never the same day's read twice
    days = _staged_days(staged)
    assert len(days) == (TOP - HS).days + 1 and all(set(v) == {"S", "P", "D1"} for v in days.values())


def test_the_build_store_counts_as_done(monkeypatch, tmp_path):
    # days the build already holds (its month files or the recent copy of the v1 file) are never read again
    _routes(monkeypatch, APPS)
    asked = _http(monkeypatch)
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    root = os.path.join(data, gd.DIR)
    st = gd.Store(root, KEY)
    have = {}
    for i in range(40):
        x = TOP - timedelta(days=i)
        have[x.isoformat()] = {"S": {"m": {}, "t": [0, 0], "to": F.isoformat(), "at": "2026-11-01T00:00:00Z"},
                               "P": {"m": {}, "t": 0, "at": "2026-11-01T00:00:00Z"},
                               "D1": {"m": {}, "t": 0, "at": "2026-11-01T00:00:00Z"}}
    st.meta = {"v": gd.STORE_V, "F": F.isoformat(), "today": TODAY.isoformat()}
    st.file_days(have)
    st.write_recent({})
    st.save_meta()
    gd.backfill_all(CFG, data, staged, [dict(a) for a in APPS], NOW, clock=lambda: 0.0, workers=1, tick=0.01)
    read = {x.isoformat() for _, q in asked if _kind(q) in ("P", "D1") for x in q.xs}
    assert read and not (read & set(have))
    assert not (set(_staged_days(staged)) & set(have))


def test_a_property_at_its_floor_or_a_429_waits_the_other_goes_on(monkeypatch, tmp_path):
    apps = [{"app_id": AID, "package": "com.example.alpha", "pid": "111"},
            {"app_id": AID2, "package": "com.example.beta", "pid": "112"}]
    _routes(monkeypatch, apps)
    low = {"tokensPerHour": {"consumed": 30000, "remaining": 10000}}           # 25 % left: under the job's 65 %
    asked = _http(monkeypatch, quota=lambda pid, n: low if pid == "111" else None,
                  fail=lambda pid, n: None)
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    out = gd.backfill_all(CFG, data, staged, [dict(a) for a in apps], NOW, clock=lambda: 0.0, budget=600, workers=1,
                          wall=lambda: datetime(2026, 11, 6, 6, 30, tzinfo=timezone.utc), tick=0.01)
    assert out["apps"] == {AID: "deferred", AID2: "done"} and out["counts"]["quota_stops"] == 1
    assert len([1 for p, _ in asked if p == "111"]) == 1    # one call, then the property waits for the next hour
    meta = gd._read_gz(gd.meta_path(staged, KEY))
    assert meta["bf"]["state"] == "paused" and meta["bf"]["why"] == "hour_low"
    # a 429: deferred, never failed
    asked2 = _http(monkeypatch, fail=lambda pid, n: RuntimeError("HTTP 429: RESOURCE_EXHAUSTED") if pid == "111"
                   else None)
    out = gd.backfill_all(CFG, str(tmp_path / "d2"), str(tmp_path / "s2"), [dict(a) for a in apps], NOW,
                          clock=lambda: 0.0, budget=600, workers=1,
                          wall=lambda: datetime(2026, 11, 6, 6, 30, tzinfo=timezone.utc), tick=0.01)
    assert out["apps"][AID] == "deferred" and out["counts"]["failed"] == 0 and not [1 for p, _ in asked2 if p == "111"]


def test_a_big_month_is_read_in_several_batches(monkeypatch, tmp_path):
    _routes(monkeypatch, APPS)
    asked = _http(monkeypatch)
    monkeypatch.setattr(gd, "S_BATCH_N", 100)           # ≤ 100 installs a call: 2 – 5 install days
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    gd.backfill_all(CFG, data, staged, [dict(a) for a in APPS], NOW, clock=lambda: 0.0, workers=1, tick=0.01)
    sb = [q for _, q in asked if _kind(q) == "Sb"]
    assert all(sum(n_of(x) for x in q.xs) <= 100 for q in sb)
    assert sum(len(q.xs) for q in sb) == sum(1 for i in range((TOP - HS).days + 1) if n_of(HS + timedelta(days=i)))
    days = _staged_days(staged)
    assert all(v["S"]["t"][0] == sum(sum(c[0] for c in cm.values()) for cm in v["S"]["m"].values())
               for v in days.values())


def test_phase_r_reads_old_revenue_so_far_again_when_it_is_stale(monkeypatch, tmp_path):
    _routes(monkeypatch, APPS)
    asked = _http(monkeypatch)
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    gd.backfill_all(CFG, data, staged, [dict(a) for a in APPS], NOW, clock=lambda: 0.0, workers=1, tick=0.01)
    later = NOW + timedelta(days=30)                    # 30 days on: the last year's months are due (R_NEAR = 28)
    asked.clear()
    out = gd.backfill_all(CFG, data, staged, [dict(a) for a in APPS], later, clock=lambda: 0.0, workers=1, tick=0.01)
    assert out["counts"]["refreshed"] > 0
    f2 = ga4.window_end_in("UTC", later) - timedelta(days=gd.LATE)
    days = _staged_days(staged)
    near = [d for d in days if (later.date() - date.fromisoformat(d)).days <= gd.A_DAYS
            and date.fromisoformat(d) <= TOP]
    assert all(days[d]["S"]["to"] == f2.isoformat() for d in near)
    far = [d for d in days if (later.date() - date.fromisoformat(d)).days > gd.A_DAYS + 31]
    assert far and all(days[d]["S"]["to"] == F.isoformat() for d in far)     # older: every R_FAR days only
    asked.clear()
    gd.backfill_all(CFG, data, staged, [dict(a) for a in APPS], later, clock=lambda: 0.0, workers=1, tick=0.01)
    assert not [q for _, q in asked if _kind(q) == "Sb"]                      # the job's own newer read counts


# ── the merge into the build's store ────────────────────────────────────────────────────────────────────────────────
def _rec(n, at, folded=False, to=None):
    m = {"XM-1": {"XA": [n * (0.5 if folded else 1), n * RPD]}}
    r = {"m": m, "t": [n, n * RPD], "at": at, "f": None}
    if to:
        r["to"] = to
    return r


def _write_staged(staged, key, days, meta=None):
    st = gd.Store(staged, key)
    st.meta = dict({"v": gd.STORE_V, "app_id": AID, "F": F.isoformat(), "today": TODAY.isoformat(),
                    "names": {"XM-OLD": ["XBrand", "Old Phone"], "XM-1": ["XBrand", "Stale"]},
                    "bf": {"A": {"done": True}}}, **(meta or {}))
    st.file_days(days)
    st.save_meta()


def test_merge_staged_rules(tmp_path):
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    root = os.path.join(data, gd.DIR)
    b = gd.Store(root, KEY)
    b.meta = {"v": gd.STORE_V, "app_id": AID, "F": F.isoformat(), "today": TODAY.isoformat(),
              "names": {"XM-1": ["XBrand", "Phone 1"]}}
    old_whole = (TODAY - timedelta(days=200)).isoformat()
    recent_day = (gd.cut_of(F) + timedelta(days=2)).isoformat()                # in the build's recent file, ≤ TOP
    own = (TODAY - timedelta(days=5)).isoformat()                              # the hourly fetch's own
    b.file_days({old_whole: {"S": _rec(10, "2026-10-01T00:00:00Z")}})
    b.write_recent({recent_day: {"R90": {"m": {}, "t": [0, 0]}}, own: {"S": _rec(7, "2026-11-06T05:00:00Z")}})
    b.save_meta()
    fresh = (TODAY - timedelta(days=300)).isoformat()
    _write_staged(staged, KEY, {
        old_whole: {"S": _rec(10, "2026-11-02T00:00:00Z", folded=True)},       # newer but folded: never over a whole
        fresh: {"S": _rec(4, "2026-11-02T00:00:00Z"), "P": {"m": {}, "t": 0, "at": "2026-11-02T00:00:00Z"},
                "R7": {"m": {}, "t": [0, 0]}},
        recent_day: {"S": _rec(5, "2026-11-02T00:00:00Z")},
        own: {"S": _rec(99, "2026-11-06T06:00:00Z")}})                         # the hourly fetch's day: never copied
    with open(gd.month_path(staged, KEY, "2025-01"), "wb") as fh:
        fh.write(b"not gzip")
    state = {"fetch": {}}
    m1 = gd.merge_staged(data, staged, state)
    assert m1 == {"merged": 3, "files": 5, "bad": 1, "stalled": 0}
    b2 = gd.Store(root, KEY)
    assert b2.month(old_whole[:7])[old_whole]["S"]["at"] == "2026-10-01T00:00:00Z"     # the whole one stays
    assert set(b2.month(fresh[:7])[fresh]) == {"S", "P"}                       # only S / P / D1 are taken
    rec = b2.recent()
    assert rec[recent_day]["S"]["t"] == [5, 5 * RPD] and "R90" in rec[recent_day]   # a recent day: its recent file
    assert rec[own]["S"]["t"] == [7, 7 * RPD]
    assert b2.meta["names"] == {"XM-1": ["XBrand", "Phone 1"], "XM-OLD": ["XBrand", "Old Phone"]}   # the build's win
    assert b2.meta["bf"] == {"A": {"done": True}} and b2.meta["months"][fresh[:7]]
    # idempotent: unchanged staged files are not read again; without the memory nothing changes either
    assert gd.merge_staged(data, staged, state) == {"merged": 0, "files": 1, "bad": 1, "stalled": 0}
    assert gd.merge_staged(data, staged, {"fetch": {}})["merged"] == 0
    # the job's next run removes the staged files the build merged (never the broken one)
    gd.save_state(data, state)
    assert gd.prune_merged(staged, data) == 4
    assert gd.months_on_disk(staged, KEY) == ["2025-01"]


def test_merge_takes_one_staged_file_at_a_time(monkeypatch, tmp_path):
    # a backlog of staged months: each is read, merged and written before the next one is read (never all held at once)
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    b = gd.Store(os.path.join(data, gd.DIR), KEY)
    b.meta = {"v": gd.STORE_V, "app_id": AID, "F": F.isoformat(), "today": TODAY.isoformat()}
    b.save_meta()
    days = {(TODAY - timedelta(days=d)).isoformat(): {"S": _rec(4, "2026-11-02T00:00:00Z")} for d in (200, 240, 280)}
    _write_staged(staged, KEY, days)
    log, real_read, real_write = [], gd._read_gz, gd.Store.write_month
    monkeypatch.setattr(gd, "_read_gz", lambda p: (log.append(("read", p)), real_read(p))[1])
    monkeypatch.setattr(gd.Store, "write_month", lambda self, m, xs: (log.append(("write", m)), real_write(self, m, xs))[1])
    assert gd.merge_staged(data, staged, {})["merged"] == 3
    order = [e for e in log if e[0] == "write" or (e[1].startswith(staged) and not e[1].endswith("meta.json.gz"))]
    months = sorted({x[:7] for x in days})
    assert order == [e for m in months for e in (("read", gd.month_path(staged, KEY, m)), ("write", m))]


def test_a_stopped_history_job_is_said(tmp_path):
    old, new_ = "2026-11-05T10:00:00Z", "2026-11-06T01:00:00Z"   # NOW: 6 Nov 06:00 UTC → 20 h / 5 h before
    assert gd.bf_stalled({"A": {"done": False}, "at": old}, NOW)
    assert not gd.bf_stalled({"A": {"done": False}, "at": new_}, NOW)
    assert not gd.bf_stalled({"A": {"done": True}, "B": {"done": True}, "at": old}, NOW)     # nothing left to do
    assert not gd.bf_stalled({"A": {"done": False}}, NOW) and not gd.bf_stalled(None, NOW)  # not run yet
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    b = gd.Store(os.path.join(data, gd.DIR), KEY)
    b.meta = {"v": gd.STORE_V, "app_id": AID, "F": F.isoformat(), "today": TODAY.isoformat()}
    b.save_meta()
    _write_staged(staged, KEY, {(TODAY - timedelta(days=300)).isoformat(): {"S": _rec(4, "2026-11-02T00:00:00Z")}},
                  meta={"bf": {"A": {"done": False}, "at": old}})
    assert gd.merge_staged(data, staged, {}, NOW)["stalled"] == 1
    from admob_iq import health
    health.FAULTS.clear()
    for ln in gd.log_line({"counts": {"merged": 1, "staged_bad": 0, "stalled": 1}}).splitlines():
        health.scan(ln)
    assert health.FAULTS == {"ga4 device history": "StalledError"}
    health.FAULTS.clear()
    assert "skipped" not in gd.log_line({"counts": {"merged": 1, "staged_bad": 0, "stalled": 0}})


def test_merge_waits_for_the_build_to_split_its_v1_file(tmp_path):
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    p = gd.store_path(data, AID)
    os.makedirs(os.path.dirname(p))
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump({"v": gd.V1, "F": F.isoformat(), "x": {}}, fh)
    _write_staged(staged, KEY, {(TODAY - timedelta(days=300)).isoformat(): {"S": _rec(4, "2026-11-02T00:00:00Z")}})
    state = {}
    assert gd.merge_staged(data, staged, state)["merged"] == 0 and not state["staged"]
    assert not os.path.exists(gd.meta_path(os.path.join(data, gd.DIR), KEY))


def test_refresh_all_merges_first_and_says_so_in_counts(monkeypatch, tmp_path):
    data, staged = str(tmp_path / "data"), str(tmp_path / gd.BF_DIR)
    _write_staged(staged, KEY, {(TODAY - timedelta(days=300)).isoformat(): {"S": _rec(4, "2026-11-02T00:00:00Z")}})
    monkeypatch.setattr(gd.gu, "load_state", lambda d: {"routes": {"by_package": {}}, "tz": {}, "fetch": {}})
    out = gd.refresh_all(CFG, data, [], NOW, clock=lambda: 0.0, staged_dir=staged)
    assert out["counts"]["merged"] == 1 and "error" not in out
    assert gd.log_line(out).endswith(", merged 1, staged bad 0")
    assert json.load(open(os.path.join(data, gd.DIR, "state.json")))["staged"]
    assert "merged" not in gd.log_line({"counts": {"selected": 1}})      # without the history: the line as before
    # a failure is seen: the health banner's "<step> skipped: <ErrorType>" line (admob_iq.health)
    from admob_iq import health
    health.FAULTS.clear()
    for ln in gd.log_line({"counts": {"merged": 0, "staged_bad": 2}, "error": "KeyError"}).splitlines():
        health.scan(ln)
    assert health.FAULTS == {"ga4 device": "KeyError", "ga4 device history": "StagedFileError"}
    health.FAULTS.clear()


# ── the workflow and the wiring ─────────────────────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_workflow_and_the_switch():
    wf = open(os.path.join(ROOT, ".github", "workflows", "devices-backfill.yml"), encoding="utf-8").read()
    assert "workflow_dispatch" in wf and 'cron: "17 */6 * * *"' in wf and "contents: read" in wf
    assert "group: devices-backfill" in wf and "cancel-in-progress: false" in wf and "timeout-minutes: 350" in wf
    assert "runs-on: ubuntu-24.04" in wf and "python -m admob_iq.fetch.ga4_device --backfill 2>" in wf
    assert "x-access-token:$DATA_REPO_TOKEN@" not in wf and "http.extraheader" in wf
    assert "vars.GA4_DEVICE_HISTORY != 'false'" in wf
    assert "inputs.apps" not in wf and "github.event.inputs" not in wf      # inputs: from the event file only
    ref = open(os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8").read()
    assert "GA4_DEVICE_HISTORY:   ${{ vars.GA4_DEVICE_HISTORY || 'true' }}" in ref
    assert "DEVICE_STAGED_DIR:    _private/ga4_device_bf" in ref
    from admob_iq import config
    cfg = config.settings()
    assert cfg["ga4_device_history"] is False and cfg["device_staged_dir"] == ""
    src = open(os.path.join(ROOT, "admob_iq", "uninstall_build.py"), encoding="utf-8").read()
    assert 'staged_dir=(s.get("device_staged_dir") or None) if s.get("ga4_device_history") else None' in src


def test_git_push_label_is_fixed_words():
    calls = []

    class R:
        returncode = 0

    def run(cmd, **kw):
        calls.append(cmd)
        r = R()
        r.returncode = 1 if "diff" in cmd else 0
        return r
    from admob_iq.fetch import ga4_screens as gs
    assert gs.git_push("/repo", gd.BF_DIR, "secret-token", run=run, pause=lambda s: None, label="devices backfill")
    msg = [c for c in calls if "commit" in c][0]
    assert msg[msg.index("-m") + 1].startswith("devices backfill ")
    assert all("secret-token" not in " ".join(c) for c in calls)
