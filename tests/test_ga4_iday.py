"""GA4 install-value reads (admob_iq.fetch.ga4_uninstall: fetch_iday, load_iday / save_iday and refresh_all's wiring) —
offline, against a synthetic GA4 (IdayGA) that answers the three per-activity-day reads (Q-B, Q-C, Q-T) from a per-day
truth kept in whole micros, with GA4's failure shapes as knobs: a short read, "(other)" loss flagged WITHOUT an
"(other)" row, an "(other)" row, sampling, a tie outside without any flag, a rejected totalRevenue, the 427-day window,
the data edge, a shrinking window, quota. Every id, country mix and amount here is synthetic."""

import gzip
import json
import os
import shutil
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_uninstall as gu
from tests.uninstall_synth import AdminFake, Truth, UniStub

END = date(2026, 9, 23)
F = END - timedelta(days=gu.IDAY_LATE)
PID, SID = "987654321", "5550001111"
CTY = (("US", 40), ("IN", 25), ("BR", 15), ("DE", 10), ("NG", 6), ("KE", 3), ("(not set)", 1))
MET = ("activeUsers", "newUsers", "totalAdRevenue", "totalRevenue")
LOW_DAY = {"tokensPerDay": {"consumed": 195000, "remaining": 5000},
           "tokensPerHour": {"consumed": 10, "remaining": 35000},
           "tokensPerProjectPerHour": {"consumed": 10, "remaining": 13000}}
LOW_HOUR = {"tokensPerDay": {"consumed": 10, "remaining": 150000},
            "tokensPerHour": {"consumed": 10, "remaining": 35000},
            "tokensPerProjectPerHour": {"consumed": 8000, "remaining": 6000}}


_YMD = {}


def ymd(d):
    s = _YMD.get(d)
    if s is None:
        s = _YMD[d] = d.strftime("%Y%m%d")
    return s


def _days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def _split(total, weights):
    """total (int ≥ 0) over weights → ints adding up to exactly total (largest remainder, ties by position)."""
    w = sum(weights)
    if not w or not total:
        return [0] * len(weights)
    raw = [total * x / w for x in weights]
    out = [int(r) for r in raw]
    for i in sorted(range(len(raw)), key=lambda i: (out[i] - raw[i], i))[:total - sum(out)]:
        out[i] += 1
    return out


def boom(msg):
    raise RuntimeError(msg)


def ret(lag):
    return 1.0 if lag == 0 else 0.3 / lag ** 0.5


def rpu(lag):
    """Ad revenue micros per active user at install age `lag`."""
    return 2000 + 6000 // (1 + lag)


class IdayTruth:
    """One app's GA4 reality per activity day d: cells(d) = {install day X: (active, new, ad micros, total micros)} —
    every install day start..d (a1 given: the day's other actives in one old install day). Countries split every cell
    exactly (largest remainder), so Q-B = Σ countries unless a knob says otherwise."""

    def __init__(self, start, end, new=300, cty=CTY, a1=None, old_x=None, iap=0, retf=ret, noise=0.0):
        self.start, self.end, self.noise = start, end, noise
        self.days = _days(start, end)
        self.new = {d: (new(d) if callable(new) else new) for d in self.days}
        self.cty, self.a1_given, self.iap, self.retf = cty, a1, iap, retf
        self.old_x = old_x or start - timedelta(days=100)
        self.win, self.win_fn, self.edge = gu.QB_WIN, None, None
        self.qb_short, self.qc_short, self.qc_loss, self.qc_other, self.qc_smp = {}, {}, {}, {}, {}
        self.reject_total, self.fail = False, None
        self.reads, self._cells = {}, {}

    def weights(self, x):
        return self.cty(x) if callable(self.cty) else self.cty

    def cells(self, d):
        if d in self._cells:
            return self._cells[d]
        out = {}
        for x in self.days:
            if x > d:
                break
            lag = (d - x).days
            n = self.new[x]
            act = n if lag == 0 else int(n * self.retf(lag))
            if act:
                ad = act * rpu(lag)
                if self.noise:                     # cheap deterministic jitter (so the file compresses like real data)
                    j = (x.toordinal() * 7919 + lag * 104729) % 1000 / 1000 - 0.5
                    act = act if lag == 0 else max(1, int(act * (1 + self.noise * j)))
                    ad = int(ad * (1 + 2 * self.noise * ((x.toordinal() * 31 + d.toordinal() * 17) % 997 / 997 - 0.5)))
                out[x] = (act, n if lag == 0 else 0, ad, ad + ad * self.iap // 100)
        if self.a1_given is not None:
            rest = int(self.a1_given.get(d, 0)) - sum(v[0] for v in out.values())
            if rest > 0:
                out[self.old_x] = (rest, 0, rest * 1500, rest * 1500)
        if len(self.days) > 800:                   # a long truth keeps only the day asked last
            self._cells.clear()
        self._cells[d] = out
        return out

    def a1(self, d):
        return sum(v[0] for v in self.cells(d).values())

    def store(self, capped=False):
        return {"history_start": self.start.isoformat(), "window_end": self.end.isoformat(), "history_capped": capped,
                "daily": {d.isoformat(): {"new": self.new[d], "a1": self.a1(d)} for d in self.days}}

    def cty_rows(self, d, xs):
        out, cd = [], self.cells(d)
        for x in xs:
            v = cd.get(x)
            if not v:
                continue
            cs = self.weights(x)
            parts = [_split(t, [w for _, w in cs]) for t in v]
            for i, (cc, _) in enumerate(cs):
                vals = [p[i] for p in parts]
                if any(vals):
                    out.append((cc, x, vals))
        return out


def _money(m):
    return "%.6f" % (m / 1e6)


class IdayGA(ga4.Ga4App):
    """Ga4App (its real report / report_all: stream filter, paging, total order) answering the iday reads from a
    truth. `log` = [(kind, first day, last day, body)]."""

    def __init__(self, truth, log=None, quota=None, pid=PID, sid=SID):
        super().__init__("tok-SECRET", pid, sid)
        self.truth, self.log, self.quota_fn = truth, [] if log is None else log, quota

    def _post(self, method, body):
        self.calls += 1
        assert method == "runReport" and body["returnPropertyQuota"] is True
        t = self.truth
        ex = [e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]]
        assert ex[0] == {"fieldName": "platform", "stringFilter": {"matchType": "EXACT", "value": "Android"}}
        assert ex[1] == {"fieldName": "streamId", "stringFilter": {"matchType": "EXACT", "value": self.stream_id}}
        dims, mets = [x["name"] for x in body["dimensions"]], [x["name"] for x in body["metrics"]]
        rng = body["dateRanges"][0]
        a, b = date.fromisoformat(rng["startDate"]), date.fromisoformat(rng["endDate"])
        kind = {("firstSessionDate",): "qb", ("countryId", "firstSessionDate"): "qc", ("date",): "qt"}[tuple(dims)]
        if not body.get("offset"):
            self.log.append((kind, a, b, body))
            t.reads[(kind, a)] = t.reads.get((kind, a), 0) + 1
        n = t.reads.get((kind, a), 0)
        if t.fail:
            t.fail(kind, a, b)
        if "totalRevenue" in mets and t.reject_total:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: totalRevenue is not compatible")
        meta, rows = {"currencyCode": "USD"}, []
        if kind == "qb":
            assert a == b and len(ex) == 2
            win = t.win_fn(a) if t.win_fn else t.win
            if t.edge is None or a >= t.edge:
                for x, (act, new, ad, tot) in sorted(t.cells(a).items()):
                    lag = (a - x).days
                    if lag > win:
                        continue
                    if lag == 0 and n <= t.qb_short.get(a, 0):
                        new = int(new * 0.9)
                    rows.append(({"firstSessionDate": ymd(x)}, [act, new, ad, tot]))
        elif kind == "qc":
            assert a == b and len(ex) == 3 and ex[2]["fieldName"] == "firstSessionDate"
            xs = sorted(ga4._d(v) for v in ex[2]["inListFilter"]["values"])
            loss, oth, smp = t.qc_loss.get(a), t.qc_other.get(a), t.qc_smp.get(a)
            moved = [0, 0, 0, 0]
            for cc, x, v in t.cty_rows(a, xs):
                if loss:
                    v = [v[0], int(v[1] * (1 - loss)), int(v[2] * (1 - loss)), int(v[3] * (1 - loss))]
                if oth:
                    m = [int(q * oth) for q in v]
                    moved, v = [p + q for p, q in zip(moved, m)], [q - r for q, r in zip(v, m)]
                if smp:
                    v = [int(round(q * smp)) for q in v]
                if n <= t.qc_short.get(a, 0):
                    v[2] = int(v[2] * 0.9)
                if any(v):
                    rows.append(({"countryId": cc, "firstSessionDate": ymd(x)}, v))
            if oth:
                rows.append(({"countryId": "(other)", "firstSessionDate": "(other)"}, moved))
            if loss or oth:
                meta["dataLossFromOtherRow"] = True       # the filtered read: loss flagged, maybe no "(other)" row
            if smp:
                meta["samplingMetadatas"] = [{"samplesReadCount": "100", "samplingSpaceSize": "1000"}]
        else:
            for d in _days(a, b):
                if d in t.new:
                    cs = t.cells(d).values()
                    rows.append(({"date": ymd(d)}, [sum(v[0] for v in cs), t.new[d], sum(v[2] for v in cs),
                                                    sum(v[3] for v in cs)]))
        rows = [(dv, dict(zip(MET, v))) for dv, v in rows]
        order = body.get("orderBys") or []
        assert {o["dimension"]["dimensionName"] for o in order} == set(dims)
        for o in reversed(order):
            k = o["dimension"]["dimensionName"]
            rows.sort(key=lambda r: r[0][k], reverse=bool(o.get("desc")))
        off, lim = int(body.get("offset") or 0), int(body.get("limit") or 10000)
        page = rows[off:off + lim]
        q = self.quota_fn(self) if self.quota_fn else {
            "tokensPerDay": {"consumed": 10, "remaining": 150000 - self.calls},
            "tokensPerHour": {"consumed": 10, "remaining": 35000},
            "tokensPerProjectPerHour": {"consumed": 10, "remaining": 13000}}

        def val(m, v):
            return _money(v) if m in ("totalAdRevenue", "totalRevenue") else str(v)
        return {"dimensionHeaders": [{"name": x} for x in dims], "metricHeaders": [{"name": m} for m in mets],
                "rows": [{"dimensionValues": [{"value": dv[x]} for x in dims],
                          "metricValues": [{"value": val(m, mv[m])} for m in mets]} for dv, mv in page],
                "rowCount": len(rows), "propertyQuota": q, "metadata": meta}


def fetch(t, ida=None, end=END, at=None, log=None, quota=None, store=None, **kw):
    ga = IdayGA(t, log=log, quota=quota)
    new, stats = gu.fetch_iday(ga, store or t.store(), ida, end, at=at or end.isoformat(), **kw)
    return new, stats, ga


def expect_x(t, days, hs=None):
    """x as the folds of `days` (each once) must hold it, straight from the truth."""
    hs = hs or t.start
    x = {}
    for d in days:
        for X, (act, new, ad, tot) in t.cells(d).items():
            lag = (d - X).days
            if X < hs or lag > 365 or lag > t.win:
                continue
            e = x.setdefault(X.isoformat(), {"n": 0, "u": [0] * 13, "r": [0] * 10})
            if lag == 0:
                e["n"] += new
            if lag in gu.ULAGS:
                e["u"][gu.ULAGS.index(lag)] += act
            e["r"][gu.iday_band(lag)] += ad
            if tot - ad:
                e.setdefault("p", [0] * 10)[gu.iday_band(lag)] += tot - ad
    return x


def folded(ida):
    return sorted(k for k, r in ida["days"].items() if r["st"] in gu.QB_FOLDED)


def small(days=40, **kw):
    return IdayTruth(END - timedelta(days=days - 1), END, **kw)


# ── requests ─────────────────────────────────────────────────────────────────────────────────────

def test_request_bodies_are_the_specs():
    t, log = small(20), []
    fetch(t, log=log)
    qb = [e for e in log if e[0] == "qb"]
    qc = [e for e in log if e[0] == "qc"]
    qt = [e for e in log if e[0] == "qt"]
    b = qb[0][3]
    assert b["dimensions"] == [{"name": "firstSessionDate"}] and [m["name"] for m in b["metrics"]] == list(MET)
    assert (b["currencyCode"], b["metricAggregations"], b["keepEmptyRows"]) == ("USD", ["TOTAL"], False)
    assert b["dateRanges"] == [{"startDate": F.isoformat(), "endDate": F.isoformat()}] and b["limit"] == 100000
    c = qc[0][3]
    assert c["dimensions"] == [{"name": "countryId"}, {"name": "firstSessionDate"}]
    inl = c["dimensionFilter"]["andGroup"]["expressions"][2]["filter"]
    assert inl["fieldName"] == "firstSessionDate"
    assert inl["inListFilter"]["values"] == [ymd(F - timedelta(days=i)) for i in range(91)]
    assert all(len(e[3]["dimensionFilter"]["andGroup"]["expressions"]) == 3 for e in qc)
    q = qt[0][3]
    assert q["dimensions"] == [{"name": "date"}] and "metricAggregations" not in q and q["currencyCode"] == "USD"
    assert len(qt) == 1 and (qt[0][1], qt[0][2]) == (t.start, F)     # one block: every day read this fetch
    assert [e[1] for e in qb] == sorted((e[1] for e in qb), reverse=True)          # newest first
    assert all(e[0] == "qc" and e[1] == p[1] for p, e in zip(log, log[1:]) if p[0] == "qb" and e[0] == "qc")


# ── when a day is read, and each is folded once ─────────────────────────────────────────────────

def test_day_read_once_when_final():
    t, log = small(40), []
    ida, st, _ = fetch(t, log=log)
    assert max(e[2] for e in log) == F and max(ida["days"]) == F.isoformat()      # nothing after E − 3
    assert folded(ida) == [d.isoformat() for d in _days(t.start, F)] and ida["done"] and ida["from"] == t.start.isoformat()
    assert ida["x"] == expect_x(t, _days(t.start, F))                            # each day folded exactly once
    x0, c0 = json.dumps(ida["x"], sort_keys=True), json.dumps(ida["c"], sort_keys=True)
    ida2, st2, _ = fetch(t, ida=ida)                                             # the same day again: no call at all
    assert st2["calls"] == 0 and json.dumps(ida2["x"], sort_keys=True) == x0 and json.dumps(ida2["c"], sort_keys=True) == c0
    t2 = IdayTruth(t.start, END + timedelta(days=1))                              # the next day (the truth moved on)
    ida3, st3, _ = fetch(t2, ida=ida2, end=END + timedelta(days=1))
    assert st3["days"] == 1 and st3["cdays"] == 1 and st3["folded"] == 1
    assert ida3["x"] == expect_x(t2, _days(t.start, F + timedelta(days=1)))
    assert ida is not ida2 and json.dumps(ida["x"], sort_keys=True) == x0           # the input is never changed


def test_qb_every_day_qc_only_inside_country_horizon():
    t, log = small(60), []
    ida, _, _ = fetch(t, log=log, cty_days=20)
    lo = F - timedelta(days=20)
    assert {e[1] for e in log if e[0] == "qb"} == set(_days(t.start, F))
    assert {e[1] for e in log if e[0] == "qc"} == set(_days(lo, F))
    assert all(r["cst"] == "none" for k, r in ida["days"].items() if date.fromisoformat(k) < lo)
    assert all(r["cst"] == "ok" for k, r in ida["days"].items() if date.fromisoformat(k) >= lo)
    assert ida["cfrom"] == lo.isoformat()


def test_qb_window_no_cov_beyond_427_and_rb_old_from_totals():
    t = IdayTruth(END - timedelta(days=599), END, new=50, retf=lambda lag: 1.0 if lag == 0 else 0.2)
    ida, st, _ = fetch(t, cty_days=5, max_calls=1000)
    days = ida["days"]
    assert st["folded"] == 597 and all(r["st"] == "ok" for r in days.values())
    for k, r in days.items():
        d = date.fromisoformat(k)
        if (d - t.start).days > gu.QB_WIN:
            assert r["cov"] is None                              # older users are legitimately missing from Q-B
        else:
            assert r["cov"] == 1.0
        old = sum(v[2] for x, v in t.cells(d).items() if (d - x).days > gu.QB_WIN)
        assert r["rb_old"] == old and r["rev"] - r["rev4"] == old and r.get("ab_old") is None
        assert r["win"] == min(gu.QB_WIN, (d - t.start).days) and sum(r["ab"]) == r["a4"]
    assert ida["x"] == expect_x(t, _days(t.start, F))


def test_a_capped_history_never_judges_cov():
    t = small(30)
    ida, _, _ = fetch(t, store=t.store(capped=True))
    assert all(r["cov"] is None and r["st"] == "ok" for r in ida["days"].values())


def test_qb_short_retries_then_q_after_3():
    t = small(30)
    d = F - timedelta(days=4)
    t.qb_short[d] = 9                                            # short on every read
    ida, st, _ = fetch(t)
    r = ida["days"][d.isoformat()]
    assert (r["st"], r["tries"], r["ncov"]) == ("retry", 1, 0.9) and st["retry"] == 1
    assert ida["x"][d.isoformat()]["n"] == 0 and r.get("cst") is None           # not folded, no country read
    x0 = ida["x"]
    ida, st, _ = fetch(t, ida=ida)                               # the same day: each retry at most once a day
    assert st["calls"] == 0
    ida, _, _ = fetch(t, ida=ida, at=(END + timedelta(days=1)).isoformat())
    assert ida["days"][d.isoformat()]["st"] == "retry" and ida["days"][d.isoformat()]["tries"] == 2
    ida, st, _ = fetch(t, ida=ida, at=(END + timedelta(days=2)).isoformat())
    r = ida["days"][d.isoformat()]
    assert (r["st"], r["tries"]) == ("q", 3) and st["flagged"] == 1          # kept (≈), folded once …
    assert r["cst"] == "retry" and r["tie_new"] > 1.1           # … and its countries don't tie to a short Q-B
    assert ida["x"] != x0 and ida["x"][d.isoformat()]["n"] == int(t.new[d] * 0.9)
    t2 = small(30)
    t2.qb_short[d] = 1                                           # short once: the retry folds it whole
    ida, _, _ = fetch(t2)
    ida, _, _ = fetch(t2, ida=ida, at=(END + timedelta(days=1)).isoformat())
    assert ida["days"][d.isoformat()]["st"] == "ok" and ida["x"] == expect_x(t2, _days(t2.start, F))


# ── countries: the tie to Q-B, loss, sampling, "(other)" ──────────────────────────────────────────

def _slot_sum(ida, key, idx=None):
    """Σ over weeks and slots (all, or those in idx) of c[W][slot][key] (n) or the r bands (key="r")."""
    out = 0 if key == "n" else [0] * 8
    for w, slots in ida["c"].items():
        for s, e in slots.items():
            if s == "gap" or (idx is not None and s not in idx):
                continue
            if key == "n":
                out += e["n"]
            else:
                out = [a + b for a, b in zip(out, e["r"])]
    return out


def _check_tie(ida, hs):
    """Σ slots + gap = Σ x, per install week and revenue band (≤ 90 days) and in lag-0 installs."""
    weeks = {}
    for k, e in ida["x"].items():
        w = weeks.setdefault(gu.iday_week(k), {"n": 0, "r": [0] * 8})
        w["n"] += e["n"]
        w["r"] = [a + b for a, b in zip(w["r"], e["r"][:8])]
    got = {}
    for w, slots in ida["c"].items():
        g = got.setdefault(w, {"n": 0, "r": [0] * 8})
        for s, e in slots.items():
            g["n"] += e["n"]
            g["r"] = [a + b for a, b in zip(g["r"], e["r"])]
    for w in set(weeks) | set(got):
        assert weeks.get(w, {"n": 0, "r": [0] * 8}) == got.get(w, {"n": 0, "r": [0] * 8}), w


def test_country_sum_plus_gap_equals_qb():
    t = small(70)
    t.qc_loss[F - timedelta(days=3)] = 0.05
    t.qc_other[F - timedelta(days=10)] = 0.04
    t.qc_smp[F - timedelta(days=20)] = 1.004
    t.qc_smp[F - timedelta(days=30)] = 1.2                       # sampled, tie outside: gap
    ida, st, _ = fetch(t, max_calls=200)
    cst = {k: r["cst"] for k, r in ida["days"].items()}
    assert cst[(F - timedelta(days=3)).isoformat()] == "gap" and cst[(F - timedelta(days=10)).isoformat()] == "gap"
    assert cst[(F - timedelta(days=20)).isoformat()] == "smp" and cst[(F - timedelta(days=30)).isoformat()] == "gap"
    assert all(v in gu.QC_FOLDED for v in cst.values()) and (st["csmp"], st["cgap"]) == (1, 3)
    _check_tie(ida, t.start)
    assert ida["flags"]["smp"] is True and all("qbc" not in r for r in ida["days"].values())


def test_qc_loss_flag_without_other_row_is_gap():
    t = small(30)
    d = F - timedelta(days=2)
    t.qc_loss[d] = 0.05
    ida, _, _ = fetch(t)
    r = ida["days"][d.isoformat()]
    assert (r["cst"], r["closs"], r["coth"]) == ("gap", True, False) and r["tie_rev"] < 0.96
    lost_n = t.new[d] - sum(int(v[1] * 0.95) for cc, x, v in t.cty_rows(d, [d]))
    assert lost_n > 0
    assert ida["c"][gu.iday_week(d)]["gap"]["n"] == lost_n        # the exact shortfall, visible, never spread
    clean = small(30)
    ida2, _, _ = fetch(clean)
    assert "gap" not in ida2["c"].get(gu.iday_week(d), {}) and ida2["days"][d.isoformat()]["tie_rev"] == 1.0
    _check_tie(ida, t.start)


def test_qc_never_rereads_in_chunks():
    t, log = small(30), []
    d = F - timedelta(days=2)
    t.qc_loss[d] = 0.05
    ida, _, _ = fetch(t, log=log)
    for i in range(1, 4):
        ida, _, _ = fetch(t, ida=ida, log=log, at=(END + timedelta(days=i)).isoformat())
    asks = [e for e in log if e[0] == "qc" and e[1] == d]
    assert len(asks) == 1
    assert all(len(e[3]["dimensionFilter"]["andGroup"]["expressions"][2]["filter"]["inListFilter"]["values"]) == 91
               for e in log if e[0] == "qc")


def test_qc_tie_outside_without_flag_retries_then_gap():
    t = small(30)
    d = F - timedelta(days=2)
    t.qc_short[d] = 9
    ida, st, _ = fetch(t)
    r = ida["days"][d.isoformat()]
    assert (r["cst"], r["ctries"], r["closs"]) == ("retry", 1, False) and st["retry"] == 1
    assert "qbc" in r and all("gap" not in c for c in ida["c"].values())       # not folded yet
    for i in (1, 2):
        ida, _, _ = fetch(t, ida=ida, at=(END + timedelta(days=i)).isoformat())
    r = ida["days"][d.isoformat()]
    assert (r["cst"], r["ctries"]) == ("gap", 3) and "qbc" not in r
    assert ida["c"][gu.iday_week(d)]["gap"]["r"] != [0] * 8
    _check_tie(ida, t.start)


def test_qc_retry_rereads_qb_for_tie_not_refold():
    t, log = small(30), []
    d = F - timedelta(days=2)
    t.qc_short[d] = 1
    ida, _, _ = fetch(t, log=log)
    x0 = json.dumps(ida["x"], sort_keys=True)
    n = len(log)
    ida, st, _ = fetch(t, ida=ida, log=log, at=(END + timedelta(days=1)).isoformat())
    assert [(e[0], e[1]) for e in log[n:]] == [("qb", d), ("qc", d)]            # a fresh Q-B for the tie, then Q-C
    assert json.dumps(ida["x"], sort_keys=True) == x0 and st["folded"] == 0     # … never folded again
    assert ida["days"][d.isoformat()]["cst"] == "ok" and ida["days"][d.isoformat()]["ctries"] == 2
    _check_tie(ida, t.start)


def test_qc_sampled_folds_as_smp_and_sets_flag():
    t = small(30)
    d = F - timedelta(days=1)
    t.qc_smp[d] = 1.01
    ida, _, _ = fetch(t)
    r = ida["days"][d.isoformat()]
    assert (r["cst"], r["csmp"], r["smp_frac"]) == ("smp", True, 0.1) and ida["flags"]["smp"] is True
    ix = {cc: str(i) for i, cc in enumerate(ida["cset"])}
    us = [v for cc, x, v in t.cty_rows(d, [d]) if cc == "US"][0]
    ref = small(30)
    ida0, _, _ = fetch(ref)
    got = ida["c"][gu.iday_week(d)][ix["US"]]["n"] - ida0["c"][gu.iday_week(d)][ix["US"]]["n"]
    assert got == int(round(us[1] * 1.01)) - us[1]               # folded as GA4 gave it: no rescaling


def test_other_rows_never_folded():
    t = small(30)
    d = F - timedelta(days=5)
    t.qc_other[d] = 0.1
    ida, _, _ = fetch(t)
    r = ida["days"][d.isoformat()]
    assert (r["cst"], r["coth"]) == ("gap", True)
    assert "(other)" not in ida["cset"] and all(len(cc) == 2 for cc in ida["cset"])
    assert ida["c"][gu.iday_week(d)]["gap"]["n"] > 0
    _check_tie(ida, t.start)


def test_day_totals_one_call_per_block_and_null_on_fail():
    t, log = small(30), []

    def fail(kind, a, b):
        if kind == "qt":
            raise RuntimeError("HTTP 503: UNAVAILABLE")
    t.fail = fail
    ida, _, _ = fetch(t, log=log)
    assert len([e for e in log if e[0] == "qt"]) == 1
    assert all(r.get("rev") is None and not r.get("tt") and r.get("rb_old") is None for r in ida["days"].values())
    t.fail, log2 = None, []
    ida, _, _ = fetch(t, ida=ida, log=log2, at=(END + timedelta(days=1)).isoformat())
    assert [(e[0], e[1], e[2]) for e in log2] == [("qt", t.start, F)]         # asked again, one block
    assert all(r["rev"] == sum(v[2] for v in t.cells(date.fromisoformat(k)).values()) and r["rb_old"] == 0
               for k, r in ida["days"].items())
    # two blocks: the new days and the backfill
    t3, log3 = small(200), []
    ida, _, _ = fetch(t3, log=log3, max_calls=40)
    t3b = IdayTruth(t3.start, END + timedelta(days=1))
    log4 = []
    ida, _, _ = fetch(t3b, ida=ida, end=END + timedelta(days=1), log=log4, max_calls=40)
    blocks = [(e[1], e[2]) for e in log4 if e[0] == "qt"]
    assert len(blocks) == 2 and blocks[0] == (F + timedelta(days=1), F + timedelta(days=1))


# ── the backfill ─────────────────────────────────────────────────────────────────────────────────

def test_backfill_newest_first_stops_on_cap_budget_quota_edge():
    t, log = small(200), []
    ida, st, _ = fetch(t, log=log, max_calls=41)
    qb = [e[1] for e in log if e[0] == "qb"]
    assert qb == sorted(qb, reverse=True) and qb[0] == F                          # newest → oldest
    assert st["calls"] <= 41 and st["why"] == "cap" and not ida["done"]
    assert [e[0] for e in log].count("qt") == 1                                   # the Q-T block still got its call
    assert ida["from"] == qb[-1].isoformat() and ida["to"] == F.isoformat()
    log2 = []
    fetch(t, ida=ida, log=log2, max_calls=41, at=(END + timedelta(days=1)).isoformat())
    nxt = [e[1] for e in log2 if e[0] == "qb"]
    assert nxt[0] == qb[-1] - timedelta(days=1)                                   # the cursor resumes
    # the plain budget (the backfill only) and the 2× budget (everything)
    calls = {"n": 0}

    def plain():
        return calls["n"] >= 1
    log3 = []
    ga = IdayGA(t, log=log3)
    real = ga._post

    def post(method, body):
        calls["n"] += 1
        return real(method, body)
    ga._post = post
    ida3, st3 = gu.fetch_iday(ga, t.store(), None, END, at=END.isoformat(), plain=plain)
    assert [e[0] for e in log3] == ["qb", "qc", "qt"] and st3["why"] == "budget"   # the new day, never starved
    ida4, st4, _ = fetch(t, stop=lambda: True)
    assert st4["calls"] == 0 and ida4["days"] == {}
    # low quota: nothing at all
    ga5 = IdayGA(t, quota=lambda ga: LOW_DAY)
    ga5.quota = LOW_DAY                                          # (the uninstall reads before it saw the quota)
    ida5, st5 = gu.fetch_iday(ga5, t.store(), None, END, at=END.isoformat())
    assert st5["calls"] == 0 and st5["qstop"] and st5["why"] == "quota" and ida5["days"] == {}
    # the data edge: 7 days in a row with no install-day row while the day had installs
    te = small(60)
    te.edge = F - timedelta(days=20)
    ida6, st6, _ = fetch(te)
    assert ida6["edge"] == (te.edge - timedelta(days=1)).isoformat() and ida6["done"]
    edge_days = sorted(k for k, r in ida6["days"].items() if r["st"] == "edge")
    assert edge_days == [(te.edge - timedelta(days=i)).isoformat() for i in range(7, 0, -1)]
    assert ida6["from"] == edge_days[0] and all(ida6["x"].get(k, {"n": 0})["n"] == 0 for k in edge_days)
    log7 = []
    fetch(te, ida=ida6, log=log7, at=(END + timedelta(days=1)).isoformat())
    assert not [e for e in log7 if e[0] == "qb"]                                  # done: nothing more asked


def test_a_failed_call_is_err_asked_again_next_day_and_two_in_a_row_stop():
    t = small(30)
    d = F - timedelta(days=3)
    t.fail = lambda kind, a, b: boom("HTTP 500: x") if (kind, a) == ("qb", d) else None
    ida, st, _ = fetch(t)
    assert ida["days"][d.isoformat()]["st"] == "err" and ida["from"] == d.isoformat()   # the backfill stops there
    t.fail = None
    ida, _, _ = fetch(t, ida=ida, at=(END + timedelta(days=1)).isoformat())
    assert ida["days"][d.isoformat()]["st"] == "ok" and ida["done"]
    assert ida["x"] == expect_x(t, _days(t.start, F))
    t2 = small(30)
    t2.fail = lambda kind, a, b: boom("HTTP 500: x")
    _, st2, _ = fetch(t2)
    assert st2["calls"] == 2 and st2["why"] == "errors"
    t3 = small(30)
    t3.fail = lambda kind, a, b: boom("HTTP 429: RESOURCE_EXHAUSTED")
    ida3, st3, _ = fetch(t3)
    assert st3["calls"] == 1 and st3["qstop"] and ida3["days"][F.isoformat()]["st"] == "err"


def test_steady_state_costs_three_calls_a_day_and_two_more_for_the_late_check():
    t = IdayTruth(END - timedelta(days=59), END + timedelta(days=12))
    ida, _, _ = fetch(t, end=END - timedelta(days=12))
    ida["born"] = (END - timedelta(days=100)).isoformat()          # past its first 28 days: no late check
    for i in range(-11, 1):
        log = []
        e = END + timedelta(days=i)
        ida, st, _ = fetch(t, ida=ida, end=e, log=log)
        assert [x[0] for x in log] == ["qb", "qc", "qt"] and st["calls"] == 3 and st["tok"] >= 0
    ida["born"] = END.isoformat()                                  # a young file: day F − 7, read fresh, again
    log = []
    ida, st, _ = fetch(t, ida=ida, end=END + timedelta(days=1), log=log)
    assert [x[0] for x in log] == ["qb", "qc", "qb", "qc", "qt"] and st["calls"] == 5
    assert ida["x"] == expect_x(t, _days(t.start, F + timedelta(days=1)))


def test_hour_floor_stops_backfill_not_new_days():
    t = small(40)
    ida, st, _ = fetch(t, quota=lambda ga: LOW_HOUR)
    assert sorted(ida["days"]) == [F.isoformat()] and st["why"] == "hour" and st["qstop"]
    assert ida["days"][F.isoformat()]["cst"] == "ok" and ida["days"][F.isoformat()]["tt"]


def test_late_check_measures_only_in_the_first_28_days():
    t = small(40)
    ida, _, _ = fetch(t, end=END - timedelta(days=7))              # day D = F − 7 read fresh at age 5 …
    d = F - timedelta(days=gu.IDAY_CHECK_AGE)
    for i in range(1, 8):
        ida, _, _ = fetch(t, ida=ida, end=END - timedelta(days=7 - i), at=(END - timedelta(days=7 - i)).isoformat())
    r = ida["days"][d.isoformat()]
    assert r["chk"] is not None and r["chk"]["n"] == t.new[d] and r["chk"]["tie_rev"] == 1.0
    assert r["chk"]["closs"] is False and r["tries"] == 1                        # … measured, never folded again
    assert ida["x"] == expect_x(t, _days(t.start, F))
    old = dict(ida, born=(END - timedelta(days=40)).isoformat())
    for k in old["days"]:
        old["days"][k] = dict(old["days"][k], chk=None)
    log = []
    fetch(t, ida=old, log=log, at=(END + timedelta(days=1)).isoformat())
    assert log == []                                             # past the first 28 days: no late check


def test_src_change_or_v_bump_starts_over():
    t = small(30)
    ida, _, _ = fetch(t)
    ga = IdayGA(t, sid="5550009999")
    new, _ = gu.fetch_iday(ga, t.store(), ida, END, at=END.isoformat())
    assert new["src"] == [PID, "5550009999"] and new["born"] == END.isoformat()
    assert all(r["tries"] == 1 for r in new["days"].values())    # read again from scratch
    bumped = dict(ida, v=gu.IDAY_V - 1)
    new2, st2, _ = fetch(t, ida=bumped, at=(END + timedelta(days=1)).isoformat())
    assert new2["v"] == gu.IDAY_V and st2["folded"] == len(_days(t.start, F))
    assert new2["x"] == expect_x(t, _days(t.start, F))


def test_cset_append_marks_part_cells(monkeypatch):
    monkeypatch.setattr(gu, "CSET_N", 2)
    surge = END - timedelta(days=20)

    def cty(x):
        return (("US", 70), ("IN", 29), ("JP", 1), ("FR", 30 if x >= surge else 0))
    t = IdayTruth(END - timedelta(days=59), END, cty=cty)
    e0 = surge + timedelta(days=gu.IDAY_LATE - 1)                 # F = surge − 1: no FR install yet
    ida, _, _ = fetch(t, end=e0)
    assert ida["cset"] == ["US", "IN", "--", "ZZ"]                # JP (1%) stays in "Other countries"
    added = None
    for i in range(1, 20):
        e = e0 + timedelta(days=i)
        before = sorted(k for k, r in ida["days"].items() if r["cst"] in gu.QC_FOLDED)
        ida, _, _ = fetch(t, ida=ida, end=e, at=e.isoformat())
        if "FR" in ida["cset"] and added is None:
            added = (e, before)
    assert added is not None and ida["cset"][:4] == ["US", "IN", "--", "ZZ"] and ida["cset"][4] == "FR"
    assert "JP" not in ida["cset"]
    assert ida["cset_since"]["FR"] == gu._date_ranges(added[1])    # the days folded before it got its slot
    fr_days = [k for k, r in ida["days"].items() if r["cst"] in gu.QC_FOLDED and k not in added[1]]
    want = sum(v[1] for k in fr_days for cc, x, v in t.cty_rows(date.fromisoformat(k), [date.fromisoformat(k)])
               if cc == "FR")
    assert _slot_sum(ida, "n", {"4"}) == want > 0
    _check_tie(ida, t.start)


def test_no_total_fallback_once():
    t, log = small(30), []
    t.reject_total = True
    ida, st, _ = fetch(t, log=log)
    asked_total = [e for e in log if "totalRevenue" in [m["name"] for m in e[3]["metrics"]]]
    assert len(asked_total) == 1 and ida["flags"]["no_total"] is True           # rejected ONCE, then never asked
    assert all(r["tot"] is None and r["rev"] is not None for r in ida["days"].values())
    assert all("p" not in e for e in ida["x"].values()) and st["folded"] == len(_days(t.start, F))
    log2 = []
    fetch(t, ida=ida, log=log2, at=(END + timedelta(days=1)).isoformat(), end=END + timedelta(days=1))
    assert all("totalRevenue" not in [m["name"] for m in e[3]["metrics"]] for e in log2)


def test_iap_is_folded_apart_and_flagged():
    t = small(30, iap=3)
    ida, _, _ = fetch(t)
    assert ida["flags"]["iap"] is True and ida["x"] == expect_x(t, _days(t.start, F))
    assert all(e.get("p") for e in ida["x"].values())
    t0 = small(30)
    ida0, _, _ = fetch(t0)
    assert ida0["flags"]["iap"] is False and all("p" not in e for e in ida0["x"].values())


def test_qb_win_drop_sets_flag_and_nulls_long_cells():
    t = IdayTruth(END - timedelta(days=499), END, new=20, retf=lambda lag: 1.0 if lag == 0 else 0.3)
    t.win_fn = lambda d: 200 if d >= F - timedelta(days=1) else gu.QB_WIN
    ida, _, _ = fetch(t, end=END - timedelta(days=2), cty_days=5, max_calls=1000)
    assert ida["flags"]["qb_win"] is False and ida["wlast"] >= 420
    ida, _, _ = fetch(t, ida=ida, cty_days=5, at=(END + timedelta(days=1)).isoformat())
    assert ida["flags"]["qb_win"] is True
    r = ida["days"][F.isoformat()]
    assert r["win"] == 200 and r["st"] == "ok"      # the ledger says how far each day reaches: the engine nulls past it


# ── the file ─────────────────────────────────────────────────────────────────────────────────────

def _gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def test_hot_old_split_monthly_roll_and_stable_write(tmp_path):
    t = IdayTruth(END - timedelta(days=699), END, new=10, retf=lambda lag: 1.0 if lag == 0 else 0.1)
    ida, _, _ = fetch(t, cty_days=150, max_calls=2000)
    aid = "ca-app-pub-0000000000000000~0000000042"
    assert gu.save_iday(str(tmp_path), aid, ida) is True
    hot_p, old_p = gu.iday_path(str(tmp_path), aid), gu.iday_path(str(tmp_path), aid, old=True)
    assert hot_p.endswith(os.path.join("ga4_uninstall", "iday", gu.file_key(aid) + ".json.gz"))
    hot, old = _gz(hot_p), _gz(old_p)
    xcut = (F - timedelta(days=400)).replace(day=1).isoformat()
    assert hot["cut"]["x"] == xcut and min(hot["days"]) == xcut and max(old["days"]) < xcut
    assert min(hot["x"]) >= xcut and max(old["x"]) < xcut and old["src"] == hot["src"]
    ccut = (F - timedelta(days=100)).replace(day=1)
    assert all(date.fromisoformat(w) + timedelta(days=6) < ccut for w in old["c"])
    assert all(date.fromisoformat(w) + timedelta(days=6) >= ccut for w in hot["c"])
    back = gu.load_iday(str(tmp_path), aid)
    assert json.dumps(back, sort_keys=True) == json.dumps(ida, sort_keys=True)          # hot + old = the whole
    assert gu.save_iday(str(tmp_path), aid, back) is False                              # unchanged: nothing written
    b0 = open(old_p, "rb").read()
    t2 = IdayTruth(t.start, END + timedelta(days=1), new=10, retf=lambda lag: 1.0 if lag == 0 else 0.1)
    nxt, _, _ = fetch(t2, ida=back, end=END + timedelta(days=1), cty_days=150)
    gu.save_iday(str(tmp_path), aid, nxt)
    same_month = (F + timedelta(days=1) - timedelta(days=400)).month == (F - timedelta(days=400)).month
    assert (open(old_p, "rb").read() == b0) == same_month          # .old moves a whole month at a time
    # a damaged .old part (or another stream's): the file starts over, never half a history
    with open(old_p, "wb") as f:
        f.write(b"\x1f\x8bnot gzip")
    assert gu.load_iday(str(tmp_path), aid) is None


def test_file_caps_for_the_longest_app(tmp_path):
    """The longest app (1,130 days), 30 countries, jittered so it compresses like real data: under the caps (hot
    300 KB gz, old 500 KB gz). The shape probe's estimate: hot ≤ 165 KB, old ≤ 399 KB."""
    cty = tuple(("%s%s" % (chr(65 + i // 26), chr(65 + i % 26)), 60 - i) for i in range(30))
    t = IdayTruth(END - timedelta(days=1129), END, new=lambda d: 3000 + (d.toordinal() * 37) % 900, cty=cty, noise=0.5)
    ida, st, _ = fetch(t, max_calls=5000)
    assert ida["done"] and st["folded"] == 1127 and st["cdays"] == 401 and len(ida["cset"]) == 32 <= gu.CSET_MAX   # (the 5 past the top 25 hold ≥ 2%: appended)
    gu.save_iday(str(tmp_path), "app", ida)
    hot = os.path.getsize(gu.iday_path(str(tmp_path), "app"))
    old = os.path.getsize(gu.iday_path(str(tmp_path), "app", old=True))
    assert hot < 300 * 1024 and old < 500 * 1024, (hot, old)


# ── the build's wiring: refresh_all, plan, the store, the log ─────────────────────────────────────

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
A1, A2 = "ca-app-pub-1111111111111111~1", "ca-app-pub-1111111111111111~2"
PKG1, PKG2, S2 = "com.secret.one", "com.secret.two", "5550002222"
APPS = [{"app_id": A1, "app_name": "One", "package": PKG1}, {"app_id": A2, "app_name": "Two", "package": PKG2}]
CFG = {"client_id": "cid", "client_secret": "sec", "refresh_tokens": json.dumps({"owner@secret-ws.test": "rt-SECRET"}),
       "refresh_token": "", "min_hours": 20.0, "retry_hours": 3.0, "refetch_days": 10, "rebuild_days": 28,
       "max_history_days": 1300, "run_budget_sec": 900, "streams_ttl_hours": 168.0}


class Stub(UniStub):
    """The uninstall stub + the iday reads, answered from an IdayTruth built on the same days (new users and daily
    actives), so the self-checks hold."""

    def __init__(self, truth, iday, *a, **kw):
        super().__init__(truth, *a, **kw)
        self.iday = IdayGA(iday, sid=self.stream_id)

    def _post(self, method, body):
        dims = tuple(d["name"] for d in body.get("dimensions") or [])
        mets = [m["name"] for m in body.get("metrics") or []]
        if dims in (("firstSessionDate",), ("countryId", "firstSessionDate")) or (
                dims == ("date",) and "totalAdRevenue" in mets):
            self.calls += 1
            self.log.append((self.property_id, self.stream_id, body))
            return self.iday._post(method, body)
        return super()._post(method, body)


class World:
    def __init__(self, monkeypatch, fail=None):
        self.truths, self.idays = {}, {}
        for sid, days, new in ((SID, 80, 400), (S2, 50, 200)):
            tr = Truth(END - timedelta(days=days - 1), END + timedelta(days=10), new, old_per_day=10)
            self.truths[sid] = tr
            self.idays[sid] = IdayTruth(tr.start, tr.end, new=lambda d, tr=tr: tr.new[d], a1=tr.a1,
                                        retf=lambda lag: 1.0 if lag == 0 else 0.05 / lag ** 0.5)
        self.admin = AdminFake({"tok-SECRET": [PID]}, {PID: [(SID, PKG1), (S2, PKG2)]})
        self.log, self.fail = [], fail
        monkeypatch.setattr(ga4.requests, "get", self.admin.get)
        monkeypatch.setattr(ga4.requests, "post", self.admin.post)
        monkeypatch.setattr(ga4, "_sleep", lambda s: None)
        monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: "tok-SECRET")
        monkeypatch.setattr(ga4, "Ga4App", self._app)

    def _app(self, tok, pid, sid):
        s = Stub(self.truths[sid], self.idays[sid], tok, pid, sid, log=self.log)
        if self.fail:
            self.idays[sid].fail = self.fail
        return s

    def run(self, data_dir, now=NOW, cfg=None):
        return gu.refresh_all(dict(CFG, **(cfg or {})), str(data_dir), APPS, now, lambda: 0.0)


def _files(d):
    out = {}
    for root, _, names in os.walk(str(d)):
        for n in names:
            p = os.path.join(root, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, str(d))] = f.read()
    return out


def test_store_unchanged_by_iday(monkeypatch, tmp_path):
    off, on = tmp_path / "off", tmp_path / "on"
    World(monkeypatch).run(off)
    w = World(monkeypatch)
    out = w.run(on, cfg={"iday": True})
    a, b = _files(off), _files(on)
    stores = [k for k in a if k.startswith("ga4_uninstall" + os.sep) and k.endswith(".json.gz")
              and os.sep + "iday" + os.sep not in k]
    assert len(stores) == 2 and all(a[k] == b[k] for k in stores)           # the main store: byte-identical
    assert not [k for k in a if "iday" in k]                                 # off: nothing of it written …
    assert "iday" not in json.loads(a[os.path.join("ga4_uninstall", "state.json")])["fetch"][A1]
    st = gu.load_state(str(on))
    assert set(st["fetch"][A1]["tokens"]) == {"usage", "vuse", "ret", "iday"}
    assert st["fetch"][A1]["iday"]["v"] == gu.IDAY_V and st["fetch"][A1]["iday"]["calls"] > 0
    for aid in (A1, A2):
        ida = gu.load_iday(str(on), aid)
        assert ida["src"] == [PID, SID if aid == A1 else S2] and ida["tz"] == "Asia/Kolkata"
        assert ida["days"] and all(r["st"] == "ok" for r in ida["days"].values())
        assert all(r["cst"] == "ok" for r in ida["days"].values())
    c = out["iday"]
    assert c["apps"] == 2 and c["folded"] == c["days"] and c["whole"] + c["filling"] == 2
    line = gu.iday_log_line(out)
    assert line.startswith("ga4 iday: apps 2, days read ") and gu.iday_log_line({}) is None


def test_iday_never_fails_app_fetch(monkeypatch, tmp_path):
    off, on = tmp_path / "off", tmp_path / "on"
    World(monkeypatch).run(off)
    w = World(monkeypatch)

    def boom(ida, q):
        raise ZeroDivisionError("a bug in the fold")
    monkeypatch.setattr(gu, "_iday_fold_qb", boom)
    out = w.run(on, cfg={"iday": True})
    assert out["counts"]["fetched"] == 2 and not out.get("error")
    a, b = _files(off), _files(on)
    assert [k for k in b if "iday" in k] == []                              # no file from a failed iday step
    assert all(a[k] == b[k] for k in a if k.endswith(".json.gz"))
    assert "iday" not in gu.load_state(str(on))["fetch"][A1]
    # a failure later (an iday GA4 read) costs only the reads: the fetch and the file go on
    on2 = tmp_path / "on2"
    monkeypatch.undo()
    w2 = World(monkeypatch, fail=lambda kind, a, b: boom("HTTP 500: x"))
    out2 = w2.run(on2, cfg={"iday": True})
    assert out2["counts"]["fetched"] == 2
    ida = gu.load_iday(str(on2), A1)
    assert ida is not None and len(ida["days"]) == 2 and {r["st"] for r in ida["days"].values()} == {"err"}


def test_backfill_due_uses_iday_done():
    """A store whose install-value history is still coming in gets its OWN fetch kind ("iday": the store only read,
    last_ok never moved) — never an "incr" that would push the next real GA4 day back by min_hours."""
    cfg = dict(CFG, iday=True)
    ok = {"property_id": PID, "stream_id": SID, "last_ok": "2026-09-24T12:00:00Z", "last_try": "2026-09-24T12:00:00Z"}
    store = {"v": gu.STORE_V, "history_start": "2026-01-01", "window_end": "2026-09-23", "next_rebuild": "2026-10-10",
             "covered": [["2026-01-01", "2026-09-23"]], "property_id": PID, "stream_id": SID}
    meta = gu.store_meta(dict(store, impact_v=gu.IMPACT_V, ret_from="2026-01-01"))
    filling = dict(ok, iday={"v": 1, "from": "2026-05-01", "to": "2026-09-20", "cfrom": "2026-05-01", "done": False})
    whole = dict(ok, iday=dict(filling["iday"], done=True))
    assert not gu.backfill_due(meta, filling) and not gu.backfill_due(meta)
    assert gu.plan(filling, meta, END, NOW, cfg) == "iday"
    assert gu.plan(whole, meta, END, NOW, cfg) is None
    assert gu.plan(filling, meta, END, NOW, CFG) is None                      # GA4_IDAY off: never
    fresh = dict(filling, last_ok="2026-09-25T09:00:00Z")                     # within min_hours: still its own kind
    assert gu.plan(fresh, meta, END, NOW, cfg) == "iday"
    just = dict(fresh, last_iday="2026-09-25T11:00:00Z")                      # … at most every IDAY_EVERY_HOURS
    assert gu.plan(just, meta, END, NOW, cfg) is None
    assert gu.plan(just, meta, END, NOW + timedelta(hours=gu.IDAY_EVERY_HOURS), cfg) == "iday"
    # a new settled GA4 day wins over it: the app's real fetch, as without GA4_IDAY
    assert gu.plan(filling, meta, END + timedelta(days=1), NOW, cfg) == gu.plan(ok, meta, END + timedelta(days=1), NOW, CFG)
    # GA4_IDAY just switched on: an app with no install-value history yet starts it at once (its own kind — the app's
    # next real fetch keeps its min_hours clock), not only after that real fetch
    never = dict(ok, last_ok="2026-09-25T09:00:00Z")                          # fetched 3h ago, no "iday" yet
    assert "iday" not in never and gu.plan(never, meta, END, NOW, cfg) == "iday"
    assert gu.plan(never, meta, END, NOW, CFG) is None                        # GA4_IDAY off: never
    assert gu.plan(dict(never, last_iday="2026-09-25T11:00:00Z"), meta, END, NOW, cfg) is None   # every 2 h at most


def test_iday_only_fetch_never_holds_back_the_new_day(monkeypatch, tmp_path):
    """An app with iday.done False read in the morning (the install-value backfill alone) still gets the new GA4 day
    the same day after noon — the iday-only fetch leaves last_ok (the min_hours clock) and the store alone."""
    w = World(monkeypatch)
    cfg = {"iday": True, "iday_max_calls": 12}
    t1 = datetime(2026, 9, 24, 7, 0, tzinfo=timezone.utc)                   # 12:30 IST: the day settles, both fetched
    w.run(tmp_path, now=t1, cfg=cfg)
    st = gu.load_state(str(tmp_path))["fetch"][A1]
    assert st["iday"]["done"] is False
    last_ok, we = st["last_ok"], gu.load_store(gu.store_path(str(tmp_path), A1))["window_end"]
    morning = t1 + timedelta(hours=18)                                       # next morning 06:30 IST: backfill only
    before = _files(tmp_path)
    from0 = gu.load_iday(str(tmp_path), A1)["from"]
    out = w.run(tmp_path, now=morning, cfg=cfg)
    st = gu.load_state(str(tmp_path))["fetch"][A1]
    assert out["counts"]["fetched"] == 0 and out["counts"]["deferred"] == 0 and out["apps"][A1] == "fresh"
    assert st["last_ok"] == last_ok and st["last_iday"] == gu._now_iso(morning)
    store_keys = [k for k in before if k.endswith(".json.gz") and os.sep + "iday" + os.sep not in k]
    after = _files(tmp_path)
    assert store_keys and all(before[k] == after[k] for k in store_keys)       # the store: never touched
    assert gu.load_iday(str(tmp_path), A1)["from"] < from0                   # … and the backfill went on
    noon = t1 + timedelta(days=1, hours=0, minutes=30)                       # the next day settles: fetched at once
    out = w.run(tmp_path, now=noon, cfg=cfg)
    assert out["apps"][A1] == "fetched"
    assert gu.load_store(gu.store_path(str(tmp_path), A1))["window_end"] > we


class _Clock:
    def __init__(self):
        self.t, self.on = 0.0, False

    def __call__(self):
        return self.t


def test_iday_backfill_never_defers_another_apps_new_day(monkeypatch, tmp_path):
    """24 apps, each its own property, a clock that moves 1 s per GA4 call and a 300 s budget: a run where every app
    has a new GA4 day fetches every app with GA4_IDAY on exactly as with it off (no app deferred), the install-value
    backfill taking only the time left."""
    n, clk = 24, _Clock()
    pids = ["9%08d" % i for i in range(n)]
    sids = ["7%09d" % i for i in range(n)]
    apps, truths, idays = [], {}, {}
    for i in range(n):
        tr = Truth(END - timedelta(days=299), END + timedelta(days=10), 300, old_per_day=10)
        truths[sids[i]] = tr
        idays[sids[i]] = IdayTruth(tr.start, tr.end, new=lambda d, tr=tr: tr.new[d], a1=tr.a1,
                                   retf=lambda lag: 1.0 if lag == 0 else 0.05 / lag ** 0.5)
        apps.append({"app_id": "ca-app-pub-1~%d" % i, "app_name": "A%02d" % i, "package": "com.x.a%d" % i})

    class Tick(Stub):
        def _post(self, method, body):
            if clk.on:
                clk.t += 1.0
            return super()._post(method, body)
    admin = AdminFake({"tok-SECRET": pids}, {pids[i]: [(sids[i], apps[i]["package"])] for i in range(n)})
    monkeypatch.setattr(ga4.requests, "get", admin.get)
    monkeypatch.setattr(ga4.requests, "post", admin.post)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: "tok-SECRET")
    monkeypatch.setattr(ga4, "Ga4App", lambda tok, pid, sid: Tick(truths[sid], idays[sid], tok, pid, sid, log=[]))
    cfg = dict(CFG, run_budget_sec=300)
    base = tmp_path / "base"
    first = gu.refresh_all(cfg, str(base), apps, NOW, clk)                   # frozen clock: every store built
    assert first["counts"]["fetched"] == n
    got = {}
    for mode in ("off", "on"):
        d = tmp_path / mode
        shutil.copytree(str(base), str(d))
        c = dict(cfg, iday=(mode == "on"))                                  # (on: every app's backfill starts here)
        clk.t, clk.on = 0.0, True
        out = gu.refresh_all(c, str(d), apps, NOW + timedelta(hours=21), clk)
        clk.on = False
        got[mode] = (out["counts"]["fetched"], out["counts"]["deferred"], clk.t)
        assert out["counts"]["deferred"] == 0, (mode, out["counts"])
    assert got["on"][0] == got["off"][0] == n
    assert got["on"][2] <= cfg["run_budget_sec"] + 60                     # the backfill stopped on time


def test_backfill_carries_on_across_runs_until_whole(monkeypatch, tmp_path):
    w = World(monkeypatch)
    out = w.run(tmp_path, cfg={"iday": True, "iday_max_calls": 30})
    st = gu.load_state(str(tmp_path))["fetch"][A1]["iday"]
    assert st["done"] is False and out["iday"]["filling"] >= 1
    for i in range(1, 8):
        out = w.run(tmp_path, now=NOW + timedelta(hours=21 * i), cfg={"iday": True, "iday_max_calls": 30})
    st = gu.load_state(str(tmp_path))["fetch"][A1]["iday"]
    ida = gu.load_iday(str(tmp_path), A1)
    assert st["done"] is True and ida["from"] == w.truths[SID].start.isoformat() and out["iday"]["whole"] == 2
    assert all(r["st"] == "ok" for r in ida["days"].values())


def test_public_line_counts_only(monkeypatch, tmp_path):
    w = World(monkeypatch)
    out = w.run(tmp_path, cfg={"iday": True})
    line = gu.iday_log_line(out)
    assert line and gu.iday_log_line({"counts": {}}) is None
    for secret in (PID, SID, S2, PKG1, A1, "US", "IN", "tok-SECRET", "secret", "$", "."):
        assert secret not in line
    nums = [int(x.strip(",()")) for x in line.split() if x.strip(",()").isdigit()]
    assert len(nums) == 12 and all(n >= 0 for n in nums)
