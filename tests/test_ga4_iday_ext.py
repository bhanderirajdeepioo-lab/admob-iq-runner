"""IDAY_EXT (admob_iq.fetch.ga4_iday_ext, wired into ga4_uninstall.fetch_iday) — offline, against a synthetic GA4 (XGA)
that answers every read of the install-day fetch from one per-day truth (tests.test_ga4_iday.IdayTruth, whole micros):
Q-B, Q-C with or without its install-day list, country parts of a split read, the paid filter, ad units by install
age and app_remove by country, with GA4's failure shapes as knobs. Every id, country, unit name and amount here is
synthetic."""

import copy
import gzip
import json
import os
import shutil
from datetime import date, datetime, timedelta, timezone

from admob_iq import value_build as vb
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_iday_ext as gx
from admob_iq.fetch import ga4_uninstall as gu
from tests.test_ga4_iday import (CFG, END, F, LOW_HOUR, MET, PID, SID, IdayTruth, Stub, World, _days, _files, _money,
                                 _split, ymd)

UNITS = (("Splash Inter", "Interstitial"), ("Home Banner", "Banner"), ("Native List", "Native"),
         ("(not set)", "(not set)"))


def unit_w(lag):
    return (6 if lag < 7 else 1, 3, 2 + lag % 3, 1 if lag % 5 == 0 else 0)


def paid_pct(x, cc):
    return 20 + (x.toordinal() * 7 + sum(map(ord, cc))) % 50


class XTruth(IdayTruth):
    """IdayTruth + the extension's views of it: a paid share per install day × country, ad units by install age,
    app_remove by day × country (its store count un / un_ev), and knobs."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.split_helps = False        # a sampled read's country parts come back unsampled
        self.part_frac = None           # … or part → its sampling fraction (None: unsampled); the whole reads 0.1
        self.rm_refuse = False
        self.late_short = {}            # day → the first n full reads have ages ≥ 91 at 90% revenue
        self.paid_over = {}             # day → the first n paid reads have 1.5× the revenue (more than all users)
        self.paid_refuse = False
        self.au_refuse = set()          # (dimension, number of metrics) GA4 refuses
        self.au_smp = 0                 # an AU read of more than this many days comes back sampled (0: never)
        self.au_loss = 0                # … loses rows into "(other)" (flagged)
        self.rm_other = {}              # day → share of app_remove events in an "(other)" row

    def rm_rows(self, d):
        ev = 20 + d.toordinal() % 13
        us = ev - ev // 6
        cs = self.weights(d)
        ws = [w for _, w in cs]
        return [(cc, u, e) for (cc, _), u, e in zip(cs, _split(us, ws), _split(ev, ws)) if u or e]

    def store(self, capped=False):
        s = super().store(capped)
        for k, v in s["daily"].items():
            rows = self.rm_rows(date.fromisoformat(k))
            v["un"], v["un_ev"] = sum(r[1] for r in rows), sum(r[2] for r in rows)
        return s

    def units(self, d, dim):
        """{(unit or format, install day): [micros, impressions, clicks]} of day d (every install age)."""
        out = {}
        for x, (act, new, ad, tot) in self.cells(d).items():
            lag = (d - x).days
            for (name, fmt), part in zip(UNITS, _split(ad, unit_w(lag))):
                if not part:
                    continue
                key = (name if dim == "adUnitName" else fmt, x)
                imp = part // 400 + 1
                v = out.setdefault(key, [0, 0, 0])
                v[0], v[1], v[2] = v[0] + part, v[1] + imp, v[2] + imp // 30
        return out


def _part_has(part, cc):
    codes, rest = part
    return cc in codes or (rest is not None and cc not in rest)


def _parse_part(e):
    """A country-part filter expression → (codes, rest)."""
    if "filter" in e:
        return list(e["filter"]["inListFilter"]["values"]), None
    if "notExpression" in e:
        return [], list(e["notExpression"]["filter"]["inListFilter"]["values"])
    a, b = e["orGroup"]["expressions"]
    return list(a["filter"]["inListFilter"]["values"]), list(b["notExpression"]["filter"]["inListFilter"]["values"])


class XGA(ga4.Ga4App):
    """Ga4App (its real report / report_all) answering every iday read from an XTruth. log = [(kind, a, b, body)]."""

    def __init__(self, truth, log=None, quota=None, pid=PID, sid=SID):
        super().__init__("tok-SECRET", pid, sid)
        self.truth, self.log, self.quota_fn = truth, [] if log is None else log, quota

    def _post(self, method, body):
        self.calls += 1
        assert method == "runReport" and body["returnPropertyQuota"] is True
        t = self.truth
        ex = body["dimensionFilter"]["andGroup"]["expressions"]
        assert ex[0]["filter"]["fieldName"] == "platform" and ex[1]["filter"]["stringFilter"]["value"] == self.stream_id
        dims, mets = [x["name"] for x in body["dimensions"]], [x["name"] for x in body["metrics"]]
        rng = body["dateRanges"][0]
        a, b = date.fromisoformat(rng["startDate"]), date.fromisoformat(rng["endDate"])
        inl = paid = part = event = None
        for e in ex[2:]:
            f = e.get("filter") or {}
            if f.get("fieldName") == "firstSessionDate":
                inl = [ga4._d(v) for v in f["inListFilter"]["values"]]
            elif f.get("fieldName") == "eventName":
                event = f["stringFilter"]["value"]
            elif f.get("fieldName") == gx.PAID_DIM:
                assert f["stringFilter"] == {"matchType": "FULL_REGEXP", "value": "[^(].*"}
                paid = True
            else:
                part = _parse_part(e)
        if tuple(dims) == ("firstSessionDate",):
            kind = "qb"
        elif tuple(dims) == ("countryId", "firstSessionDate"):
            kind = "qc" if inl is not None else "paid" if paid else "qcp" if part else "qcf"
        elif tuple(dims) == ("date",):
            kind = "qt"
        elif tuple(dims) == ("date", "countryId"):
            assert event == "app_remove"
            kind = "rm"
        else:
            assert dims[1:] == ["firstSessionDate", "date"] and dims[0] in ("adUnitName", "adFormat"), dims
            kind = "au"
        if not body.get("offset"):
            self.log.append((kind, a, b, body))
            t.reads[(kind, a)] = t.reads.get((kind, a), 0) + 1
        n = t.reads.get((kind, a), 0)
        nq = t.reads.get(("qc", a), 0) + t.reads.get(("qcf", a), 0)
        if t.fail:
            t.fail(kind, a, b)
        if "totalRevenue" in mets and t.reject_total:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: totalRevenue is not compatible")
        if kind == "paid" and t.paid_refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: firstUserGoogleAdsCampaignId")
        if kind == "au" and (dims[0], len(mets)) in t.au_refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: incompatible")
        if kind == "rm" and t.rm_refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: eventName")
        meta, rows = {"currencyCode": "USD"}, []
        if kind == "qb":
            for x, (act, new, ad, tot) in sorted(t.cells(a).items()):
                lag = (a - x).days
                if lag > t.win:
                    continue
                if lag == 0 and n <= t.qb_short.get(a, 0):
                    new = int(new * 0.9)
                rows.append(({"firstSessionDate": ymd(x)}, dict(zip(MET, [act, new, ad, tot]))))
        elif kind in ("qc", "qcf", "qcp", "paid"):
            xs = sorted(inl) if inl is not None else sorted(t.cells(a))
            loss, oth, smp = t.qc_loss.get(a), t.qc_other.get(a), t.qc_smp.get(a)
            frac = 0.1
            if smp and part and t.split_helps:
                smp = None
            elif smp and part and t.part_frac:
                frac = t.part_frac(part)
                smp = smp if frac else None
            moved = [0, 0, 0, 0]
            for cc, x, v in t.cty_rows(a, xs):
                if part and not _part_has(part, cc):
                    continue
                if paid:
                    if n <= t.paid_over.get(a, 0):
                        v = [q * 2 for q in v]                       # "paid" more than every user: inconsistent
                    else:
                        v = [_split(q, [paid_pct(x, cc), 100 - paid_pct(x, cc)])[0] for q in v]
                if loss:
                    v = [v[0], int(v[1] * (1 - loss)), int(v[2] * (1 - loss)), int(v[3] * (1 - loss))]
                if oth:
                    m = [int(q * oth) for q in v]
                    moved, v = [p + q for p, q in zip(moved, m)], [q - r for q, r in zip(v, m)]
                if smp:
                    v = [int(round(q * smp)) for q in v]
                if kind in ("qc", "qcf") and nq <= t.qc_short.get(a, 0):
                    v[2] = int(v[2] * 0.9)
                if kind in ("qcf", "qcp") and (a - x).days >= 91 and t.reads.get(("qcf", a), 0) <= t.late_short.get(a, 0):
                    v[2] = int(v[2] * 0.9)
                if any(v):
                    rows.append(({"countryId": cc, "firstSessionDate": ymd(x)}, dict(zip(MET, v))))
            if oth and inl is None:
                rows.append(({"countryId": "(other)", "firstSessionDate": "(other)"}, dict(zip(MET, moved))))
            if loss or oth:
                meta["dataLossFromOtherRow"] = True
            if smp:
                meta["samplingMetadatas"] = [{"samplesReadCount": str(int(frac * 1000)), "samplingSpaceSize": "1000"}]
        elif kind == "qt":
            for d in _days(a, b):
                if d in t.new:
                    cs = t.cells(d).values()
                    rows.append(({"date": ymd(d)}, dict(zip(MET, [sum(v[0] for v in cs), t.new[d],
                                                                  sum(v[2] for v in cs), sum(v[3] for v in cs)]))))
        elif kind == "au":
            for d in _days(a, b):
                if d not in t.new:
                    continue
                for (u, x), (ad, imp, clk) in sorted(t.units(d, dims[0]).items()):
                    rows.append(({dims[0]: u, "firstSessionDate": ymd(x), "date": ymd(d)},
                                 dict(zip(mets, [ad, imp, clk]))))
            if t.au_smp and (b - a).days + 1 > t.au_smp:
                meta["samplingMetadatas"] = [{"samplesReadCount": "100", "samplingSpaceSize": "1000"}]
            if t.au_loss and (b - a).days + 1 > t.au_loss:
                meta["dataLossFromOtherRow"] = True
        else:
            for d in _days(a, b):
                if d not in t.new:
                    continue
                o = t.rm_other.get(d)
                mo = [0, 0]
                for cc, u, e in t.rm_rows(d):
                    if o:
                        mu, me = int(u * o), int(e * o)
                        mo, u, e = [mo[0] + mu, mo[1] + me], u - mu, e - me
                    rows.append(({"date": ymd(d), "countryId": cc}, {"totalUsers": u, "eventCount": e}))
                if o:
                    rows.append(({"date": ymd(d), "countryId": "(other)"}, {"totalUsers": mo[0], "eventCount": mo[1]}))
        rows = [(dv, {m: mv.get(m, 0) for m in mets}) for dv, mv in rows]
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


def xfetch(t, ida=None, end=END, at=None, log=None, ext=True, quota=None, store=None, **kw):
    ga = XGA(t, log=log, quota=quota)
    new, stats = gu.fetch_iday(ga, store or t.store(), ida, end, at=at or end.isoformat(), ext=ext, **kw)
    return new, stats, ga


def xown(t, ida, **kw):
    """The extension's own fetch (x_only: the app's install-value history is whole): its history re-read and every
    AU / RM block — a fetch with legacy reads does only on_qc, the new days' paid read and one AU / RM block."""
    return xfetch(t, ida=ida, x_only=True, **kw)


def xsmall(days=40, **kw):
    return XTruth(END - timedelta(days=days - 1), END, **kw)


def legacy(ida):
    return {k: v for k, v in ida.items() if k not in gu.X_KEYS}


def dump(o):
    return json.dumps(o, sort_keys=True)


def late_of(t, d, hs):
    """{(week, band): Q-B ad revenue} at ages 91..427 of day d, install days ≥ hs (what c2 slots + gap must hold)."""
    out = {}
    for x, (act, new, ad, tot) in t.cells(d).items():
        lag = (d - x).days
        if x < hs or not 91 <= lag <= min(gu.QB_WIN, t.win):
            continue
        k = (gu.iday_week(x), gx.C2B_IX[lag])
        out[k] = out.get(k, 0) + ad
    return out


def want_c2(t, ida):
    """Σ Q-B at ages 91..427 over every day whose late ages were folded (slots + gap must equal it, whatever the
    status)."""
    want = {}
    for k, r in ida["d2"].items():
        if r.get("c2st") in gx.FOLDED:
            _acc(want, late_of(t, date.fromisoformat(k), t.start))
    return {k: v for k, v in want.items() if v}


def c2_sums(ida):
    out = {}
    for w, slots in ida["c2"].items():
        for s, e in slots.items():
            for i, v in enumerate(e["r2"]):
                if v:
                    out[(w, i)] = out.get((w, i), 0) + v
    return out


def _acc(dst, src):
    for k, v in src.items():
        dst[k] = dst.get(k, 0) + v
    return dst


# ── the requests ─────────────────────────────────────────────────────────────────────────────────

def test_request_shapes():
    t, log = xsmall(30), []
    xfetch(t, log=log)
    kinds = {e[0] for e in log}
    assert "qc" not in kinds and {"qb", "qcf", "paid", "qt", "au", "rm"} <= kinds
    c = [e for e in log if e[0] == "qcf"][0][3]
    assert c["dimensions"] == [{"name": "countryId"}, {"name": "firstSessionDate"}]
    assert [m["name"] for m in c["metrics"]] == list(MET) and c["metricAggregations"] == ["TOTAL"]
    assert len(c["dimensionFilter"]["andGroup"]["expressions"]) == 2          # no install-day list: every age
    p = [e for e in log if e[0] == "paid"][0][3]
    assert p["dimensions"] == c["dimensions"] and p["metrics"] == c["metrics"]
    assert p["dimensionFilter"]["andGroup"]["expressions"][2] == {"filter": {
        "fieldName": "firstUserGoogleAdsCampaignId", "stringFilter": {"matchType": "FULL_REGEXP", "value": "[^(].*"}}}
    a = [e for e in log if e[0] == "au"][0][3]
    assert [x["name"] for x in a["dimensions"]] == ["adUnitName", "firstSessionDate", "date"]
    assert [x["name"] for x in a["metrics"]] == ["totalAdRevenue", "publisherAdImpressions", "publisherAdClicks"]
    assert a["currencyCode"] == "USD" and len(a["dimensionFilter"]["andGroup"]["expressions"]) == 2
    r = [e for e in log if e[0] == "rm"][0][3]
    assert [x["name"] for x in r["dimensions"]] == ["date", "countryId"] and r["metricAggregations"] == ["TOTAL"]
    assert [x["name"] for x in r["metrics"]] == ["totalUsers", "eventCount"]
    assert r["dimensionFilter"]["andGroup"]["expressions"][2]["filter"] == {
        "fieldName": "eventName", "stringFilter": {"matchType": "EXACT", "value": "app_remove"}}
    # the split parts' filters
    named = ["US", "IN", "BR", "DE", "NG", "KE"]
    parts = gx.split_parts(named, 2)
    assert parts == [(["US", "BR", "NG"], None), (["IN", "DE", "KE"], named)]
    assert gx.cty_expr(parts[1]) == {"orGroup": {"expressions": [
        ga4._in_list("countryId", ["IN", "DE", "KE"]), {"notExpression": ga4._in_list("countryId", named)}]}}
    assert sorted(cc for p in gx.split_parts(named, 4) for cc in p[0]) == sorted(named)


def test_ext_off_reads_exactly_as_before():
    t, log = xsmall(30), []
    ida, st, _ = xfetch(t, log=log, ext=False)
    assert {e[0] for e in log} == {"qb", "qc", "qt"} and "x" not in st
    assert all(not ida[k] for k in gu.X_KEYS) and st["xcalls"] == 0


# ── the hard rule: every legacy byte as without the extension ────────────────────────────────────

def _knobs(t):
    t.qc_loss[F - timedelta(days=3)] = 0.05
    t.qc_other[F - timedelta(days=10)] = 0.04
    t.qc_smp[F - timedelta(days=20)] = 1.004
    t.qc_smp[F - timedelta(days=30)] = 1.2
    t.qc_short[F - timedelta(days=5)] = 1
    t.qb_short[F - timedelta(days=7)] = 1
    t.late_short[F - timedelta(days=12)] = 1
    t.paid_over[F - timedelta(days=14)] = 1


def _run_days(t, ext, tmp, fetches=6, **kw):
    ida = None
    for i in range(fetches):
        e = END - timedelta(days=fetches - 1 - i)
        ida, _, _ = xfetch(t, ida=ida, end=e, at=e.isoformat(), ext=ext, **kw)
    gu.save_iday(str(tmp), "ca-app-pub-0000000000000000~0000000042", ida)
    return ida


def test_legacy_files_byte_identical_with_ext(tmp_path):
    """The same GA4 truth (loss, "(other)", sampling, short reads, retries, a backfill over a call cap, new days):
    the iday files written with the extension are byte for byte the ones written without it."""
    for days, kw in ((130, {"max_calls": 60}), (480, {"max_calls": 1000, "cty_days": 150})):
        out = {}
        for ext in (False, True):
            t = XTruth(END - timedelta(days=days - 1), END, new=lambda d: 200 + d.toordinal() % 37,
                       retf=lambda lag: 1.0 if lag == 0 else 0.2 / (1 + lag) ** 0.3)
            _knobs(t)
            d = tmp_path / ("%d-%s" % (days, ext))
            ida = _run_days(t, ext, d, **kw)
            out[ext] = (ida, {f: open(os.path.join(r, f), "rb").read() for r, _, fs in os.walk(str(d)) for f in fs})
        off, on = out[False], out[True]
        assert set(on[1]) - set(off[1]) == {k for k in on[1] if ".x." in k} != set()
        for f, b in off[1].items():
            assert on[1][f] == b, f                                   # the legacy files: identical bytes
        assert dump(legacy(off[0])) == dump(legacy(on[0]))


def test_le91_is_the_inlist_read():
    t = xsmall(200)
    d = F - timedelta(days=3)
    full = XGA(t).report_all(gu._iday_body(d, d, ("countryId", "firstSessionDate")))
    old = XGA(t).report_all(gu._iday_body(d, d, ("countryId", "firstSessionDate")),
                            extra=[ga4._in_list("firstSessionDate", [ymd(d - timedelta(days=i)) for i in range(91)])])
    assert len(full) > len(old) and gu._le91(full, d) == old
    assert gu._qc_parse(gu._le91(full, d), d, t.start) == gu._qc_parse(old, d, t.start)


# ── (1) late ages ────────────────────────────────────────────────────────────────────────────────

def test_late_cells_plus_gap_equal_qb():
    t = XTruth(END - timedelta(days=599), END, new=lambda d: 150 + d.toordinal() % 29,
               retf=lambda lag: 1.0 if lag == 0 else 0.25)
    t.qc_loss[F - timedelta(days=4)] = 0.05
    t.qc_other[F - timedelta(days=9)] = 0.03
    ida, st, _ = xfetch(t, cty_days=60, max_calls=2000)
    d2 = ida["d2"]
    lo = F - timedelta(days=60)
    judged = sorted(k for k, r in d2.items() if r.get("c2st"))
    assert judged == [k.isoformat() for k in _days(lo, F)]                         # the country horizon, every day
    assert d2[(F - timedelta(days=4)).isoformat()]["c2st"] == "gap" and d2[(F - timedelta(days=9)).isoformat()]["c2oth"]
    assert all(r["c2st"] == "ok" and r["tie_late"] in (None, 1.0) for k, r in d2.items()
               if k not in ((F - timedelta(days=4)).isoformat(), (F - timedelta(days=9)).isoformat()))
    want = {}
    for d in _days(lo, F):
        _acc(want, late_of(t, d, t.start))
    assert c2_sums(ida) == {k: v for k, v in want.items() if v}                 # Σ slots + gap = Q-B, exactly
    gaps = [w for w, s in ida["c2"].items() if "gap" in s]
    assert gaps and all(any(s["gap"]["r2"]) for s in (ida["c2"][w] for w in gaps))
    # users at 120 / 180 / 270 / 365 by country, straight from the truth
    ix = {cc: str(i) for i, cc in enumerate(ida["cset"])}
    us = {}
    for d in _days(lo, F):
        xs = [d - timedelta(days=lag) for lag in gx.C2LAGS if d - timedelta(days=lag) >= t.start]
        for cc, x, v in t.cty_rows(d, xs):
            k = (gu.iday_week(x), ix.get(gu._slot_cc(cc), ix["ZZ"]), gx.C2L_IX[(d - x).days])
            a = v[0] - int(v[0] * 0.03) if d == F - timedelta(days=9) else v[0]
            us[k] = us.get(k, 0) + a
    got = {(w, s, i): v for w, slots in ida["c2"].items() for s, e in slots.items() if s != "gap"
           for i, v in enumerate(e["u2"]) if v}
    assert got == {k: v for k, v in us.items() if v}
    assert all(len(e["r2"]) == 3 and len(e["u2"]) == 4 for slots in ida["c2"].values()
               for s, e in slots.items() if s != "gap")


def test_late_tie_outside_retries_with_a_fresh_pair_then_folds():
    t = xsmall(300)
    d = F - timedelta(days=2)
    t.late_short[d] = 1                                              # the first full read is short past age 90
    ida, st, _ = xfetch(t, cty_days=30, max_calls=2000)
    r = ida["d2"][d.isoformat()]
    assert (r["c2st"], r["c2tries"]) == ("retry", 1) and r["tie_late"] < 0.95 and st["x"]["late_retry"] == 1
    assert ida["days"][d.isoformat()]["cst"] == "ok"                  # the legacy ages tied: folded as always
    ida, _, _ = xown(t, ida, cty_days=30, max_calls=2000)             # the rest of the history (d: asked today)
    assert ida["d2"][d.isoformat()]["c2tries"] == 1
    log = []
    ida, st, _ = xown(t, ida, log=log, at=(END + timedelta(days=1)).isoformat(), cty_days=30)
    assert [(e[0], e[1]) for e in log if e[0] in ("qb", "qcf", "paid")] == [("qb", d), ("qcf", d)]   # a fresh pair
    r = ida["d2"][d.isoformat()]
    assert (r["c2st"], r["c2tries"], r["tie_late"]) == ("ok", 2, 1.0)
    assert len([k for k, r in ida["d2"].items() if r.get("c2st") == "ok"]) == 31
    assert c2_sums(ida) == want_c2(t, ida)


# ── (2) paid vs organic ─────────────────────────────────────────────────────────────────────────

def _paid_truth(t, days, hs):
    """{(week, slot code, band): paid micros}, {(week, slot code): paid lag-0 new} over `days`."""
    r, n = {}, {}
    for d in days:
        for cc, x, v in t.cty_rows(d, sorted(t.cells(d))):
            lag = (d - x).days
            if x < hs or lag > gu.QB_WIN:
                continue
            p = [_split(q, [paid_pct(x, cc), 100 - paid_pct(x, cc)])[0] for q in v]
            k = (gu.iday_week(x), gu._slot_cc(cc))
            r[k + (gx.LB_IX[lag],)] = r.get(k + (gx.LB_IX[lag],), 0) + p[2]
            if lag == 0:
                n[k] = n.get(k, 0) + p[1]
    return r, n


def test_paid_cells_tie_back_and_organic_is_the_rest():
    t = xsmall(200)
    ida, st, _ = xfetch(t, cty_days=40, max_calls=2000)
    assert st["x"]["paid"] == 1                                        # the new day; the history: its own fetch
    ida, st2, _ = xown(t, ida, cty_days=40, max_calls=2000)
    lo = F - timedelta(days=40)
    days = _days(lo, F)
    assert all(ida["d2"][d.isoformat()]["cpst"] == "ok" for d in days) and st2["x"]["paid"] == len(days) - 1
    code = dict(enumerate(ida["cset"]))
    got_r, got_n = {}, {}
    for w, slots in ida["cp"].items():
        for s, e in slots.items():
            k = (w, code[int(s)])
            got_n[k] = got_n.get(k, 0) + e["n"]
            for i, v in enumerate(e["r"]):
                if v:
                    got_r[k + (i,)] = got_r.get(k + (i,), 0) + v
    want_r, want_n = _paid_truth(t, days, t.start)
    assert got_r == {k: v for k, v in want_r.items() if v}
    assert {k: v for k, v in got_n.items() if v} == {k: v for k, v in want_n.items() if v}
    r = ida["d2"][F.isoformat()]
    assert 0 < r["cpshare"] < 1 and r["cpx"] == 0 and 0 < r["cpn"] < 1
    # organic = all − paid: never negative in the bands both hold (lags ≤ 90: c, 91+: c2)
    for w, slots in ida["cp"].items():
        for s, e in slots.items():
            allc = (ida["c"].get(w) or {}).get(s)
            if allc and w >= gu.iday_week(lo):
                assert all(a >= p for a, p in zip(allc["r"], e["r"][:8]))


def test_paid_more_than_all_retries_then_gap():
    t = xsmall(60)
    d = F - timedelta(days=3)
    t.paid_over[d] = 9
    ida, _, _ = xfetch(t, cty_days=30, max_calls=2000)
    ida, _, _ = xown(t, ida, cty_days=30, max_calls=2000)
    assert (ida["d2"][d.isoformat()]["cpst"], ida["d2"][d.isoformat()]["cpx"]) == ("retry", 0.5)
    for i in (1, 2):
        ida, _, _ = xown(t, ida, at=(END + timedelta(days=i)).isoformat(), cty_days=30, max_calls=2000)
    r = ida["d2"][d.isoformat()]
    assert (r["cpst"], r["cptries"]) == ("gap", 3)


def test_paid_filter_refused_turns_off_for_four_weeks_and_never_touches_no_total():
    t = xsmall(30)
    t.paid_refuse = True
    log = []
    ida, st, _ = xfetch(t, log=log)
    assert len([e for e in log if e[0] == "paid"]) == 1 and ida["xs"]["paid"]["off"] == END.isoformat()
    assert ida["flags"]["no_total"] is False and st["x"]["errors"] == 0
    log = []
    ida, _, _ = xown(t, ida, log=log, at=(END + timedelta(days=3)).isoformat())
    assert not [e for e in log if e[0] == "paid"]
    t.paid_refuse = False
    log = []
    ida, _, _ = xown(t, ida, log=log, at=(END + timedelta(days=28)).isoformat())
    assert [e for e in log if e[0] == "paid"] and ida["xs"]["paid"]["off"] is None
    # the late ages are done: each day's paid read takes a fresh full read only (no Q-B: the paid tie is the full read)
    assert not [e for e in log if e[0] == "qb"]
    assert sorted(e[1] for e in log if e[0] == "qcf") == sorted(e[1] for e in log if e[0] == "paid")
    assert all(r["cpst"] == "ok" for r in ida["d2"].values())


# ── (5) the history re-read ─────────────────────────────────────────────────────────────────────

def test_history_reread_newest_first_never_touches_legacy(tmp_path):
    t = XTruth(END - timedelta(days=299), END, new=lambda d: 100 + d.toordinal() % 17)
    old, _, _ = xfetch(t, ext=False, max_calls=2000)                # a whole legacy history, no extension yet
    gu.save_iday(str(tmp_path / "a"), "app", old)
    log = []
    ida, st, _ = xown(t, old, log=log, max_calls=60, cty_days=100)
    gu.save_iday(str(tmp_path / "b"), "app", ida)
    for f in ("app.json.gz", "app.old.json.gz"):
        p = os.path.join("ga4_uninstall", "iday", f)
        if os.path.exists(str(tmp_path / "a" / p)):
            assert open(str(tmp_path / "a" / p), "rb").read() == open(str(tmp_path / "b" / p), "rb").read()
    assert dump(legacy(ida)) == dump(legacy(old))
    pairs = [e[1] for e in log if e[0] == "qcf"]
    assert pairs == sorted(pairs, reverse=True) and pairs[0] == F                 # newest first
    assert st["calls"] == 0 and st["xcalls"] <= 60 and st["x"]["why"] == "cap"
    assert st["why"] is None and st["qstop"] is False                           # its stop: never the legacy one
    assert [e[0] for e in log[:3]] == ["qb", "qcf", "paid"]
    left = st["x"]["left"]
    for i in range(1, 12):                                                         # (more runs the same day)
        ida, st, _ = xown(t, ida, max_calls=60, cty_days=100)
    lo = F - timedelta(days=100)
    assert st["x"]["left"] == 0 < left
    assert all(ida["d2"][d.isoformat()]["c2st"] == "ok" and ida["d2"][d.isoformat()]["cpst"] == "ok"
               for d in _days(lo, F))
    assert not [k for k in ida["d2"] if date.fromisoformat(k) < lo]                 # nothing outside the horizon
    assert c2_sums(ida) == want_c2(t, ida)
    assert dump(legacy(ida)) == dump(legacy(old))


def test_reread_obeys_hour_floor_and_plain_budget_new_days_do_not():
    t = xsmall(120)
    old, _, _ = xfetch(t, ext=False, end=END - timedelta(days=1), at=(END - timedelta(days=1)).isoformat(),
                       max_calls=2000)
    old["born"] = (END - timedelta(days=100)).isoformat()                         # (no late check)
    log = []
    ida, st, _ = xfetch(t, ida=old, log=log, quota=lambda ga: LOW_HOUR, plain=lambda: True, cty_days=60)
    assert {(e[0], e[1]) for e in log if e[0] in ("qcf", "paid")} == {("qcf", F), ("paid", F)}   # the new day only
    assert ida["d2"][F.isoformat()]["cpst"] == "ok" and len([k for k, r in ida["d2"].items() if r.get("c2st")]) == 1
    assert st["x"].get("why") is None and st["why"] is None                     # (no re-read in this fetch at all)
    # the re-read (its own fetches): the hourly floor and the plain budget stop it — never the legacy stats
    log = []
    ida2, st2, _ = xown(t, ida, log=log, quota=lambda ga: LOW_HOUR, cty_days=60)
    assert len({e[1] for e in log if e[0] in ("qb", "qcf", "paid")}) <= 1     # (its first read: no quota known yet)
    assert (st2["x"]["why"], st2["x"]["qstops"]) == ("hour", 1) and st2["why"] is None and st2["qstop"] is False
    ida3, st3, _ = xown(t, ida, plain=lambda: True, cty_days=60)
    assert st3["x"]["why"] == "budget" and st3["why"] is None and st3["xcalls"] <= 2   # (≤ its first AU / RM block)


def test_a_due_fetch_leaves_the_reread_to_the_extensions_own_fetches(monkeypatch, tmp_path):
    """Two apps due in one run (GA4 time: 4 s a call). App 1: install-value history whole, the extension never ran
    (the state right after it is switched on). App 2: its install-value history starts over. App 1's DUE fetch does no
    history re-read (only the new days' paid read and one AU / RM block): app 2's legacy backfill gets the run's time
    as with IDAY_EXT off, less only those few calls."""
    from tests.test_ga4_iday import A1, A2, APPS
    base = tmp_path / "base"
    w = XWorld(monkeypatch)
    for i in range(4):
        w.run(base, now=NOW + timedelta(hours=21 * i), cfg={"iday": True})
    st = gu.load_state(str(base))
    assert all(st["fetch"][a]["iday"]["done"] is True for a in (A1, A2))
    for p in (gu.iday_path(str(base), A2), gu.iday_path(str(base), A2, old=True)):
        if os.path.exists(p):
            os.remove(p)
    st["fetch"][A2].pop("iday")
    st["fetch"][A2].pop("last_iday", None)
    gu.save_state(str(base), st)
    later = NOW + timedelta(hours=21 * 4)
    got = {}
    for mode in ("off", "on"):
        d = tmp_path / mode
        shutil.copytree(str(base), str(d))
        w2 = XWorld(monkeypatch)
        out = gu.refresh_all(dict(CFG, iday=True, iday_ext=mode == "on"), str(d), APPS, later,
                             lambda: 4.0 * len(w2.log))
        s = gu.load_state(str(d))["fetch"]
        got[mode] = (out["counts"]["fetched"], len(gu.load_iday(str(d), A2)["days"]), s[A1]["iday"].get("x2"))
    assert got["off"][0] == got["on"][0] == 2 and got["off"][2] is None
    x2 = got["on"][2]
    assert 0 < x2["calls"] <= 3 and x2["done"] is False and x2["left"] > 0      # the re-read: its own fetches, later
    assert got["off"][1] - 2 <= got["on"][1] <= got["off"][1]                   # app 2's legacy days read this run


# ── sampling: split only while it helps ─────────────────────────────────────────────────────────

def test_sampled_read_split_that_does_not_help_is_kept_flagged_and_not_retried():
    t = xsmall(200)
    first, _, _ = xfetch(t, end=END - timedelta(days=8), at=(END - timedelta(days=8)).isoformat(), cty_days=20,
                         max_calls=2000)                                         # the slots come from unsampled days
    for i in range(0, 8):
        t.qc_smp[F - timedelta(days=i)] = 1.003
    log = []
    ida, st, _ = xfetch(t, ida=first, log=log, cty_days=20, max_calls=2000)
    parts = [e for e in log if e[0] == "qcp"]
    assert len(parts) == 2 and st["x"]["split"] == 1                              # one try: halves …
    assert ida["xs"]["split"]["no"] == END.isoformat() and ida["xs"]["split"]["lv"] == 0   # … that didn't help
    for i in range(8):
        r = ida["d2"][(F - timedelta(days=i)).isoformat()]
        assert (r["c2st"], r["c2smp"], r["c2frac"], r["cpst"], r["c2parts"]) == ("smp", True, 0.1, "smp", 1)
    log = []
    t.qc_smp[F + timedelta(days=1)] = 1.003
    ida, _, _ = xfetch(t, ida=ida, log=log, end=END + timedelta(days=1), at=(END + timedelta(days=1)).isoformat(),
                       cty_days=20)
    assert not [e for e in log if e[0] == "qcp"]                                  # not tried again for a month


def test_sampled_read_split_that_helps_is_used_for_late_and_paid():
    t = xsmall(200)
    t.split_helps = True
    first, _, _ = xfetch(t, end=END - timedelta(days=3), at=(END - timedelta(days=3)).isoformat(), cty_days=10,
                         max_calls=2000)
    for i in range(0, 3):
        t.qc_smp[F - timedelta(days=i)] = 1.2
    log = []
    ida, st, _ = xfetch(t, ida=first, log=log, cty_days=10, max_calls=2000)
    assert ida["xs"]["split"]["lv"] == 1 and ida["xs"]["split"]["no"] is None
    for i in range(3):
        d = F - timedelta(days=i)
        r = ida["d2"][d.isoformat()]
        assert (r["c2st"], r["c2parts"], r["cpst"], r["cpparts"]) == ("ok", 2, "ok", 2), r
        assert len([e for e in log if e[0] == "paid" and e[1] == d]) == 2
    assert c2_sums(ida) == want_c2(t, ida)                                      # the parts: exact (unsampled)
    # the legacy cells of those days stay what the whole read gave (sampled, flagged as before)
    assert all(ida["days"][(F - timedelta(days=i)).isoformat()]["cst"] == "gap" for i in range(3))


def test_split_goes_deeper_only_until_unsampled():
    """Halves still sampled (though reading more of the data) → quarters. Quarters unsampled: used for the late ages
    and the paid read (exact), and the next days go straight to quarters. Quarters still sampled: nothing of the split
    is used — the whole read stays, flagged, and no split is tried for a month."""
    for quarter in (None, 0.5):
        t = XTruth(END - timedelta(days=199), END + timedelta(days=1))
        t.part_frac = lambda part, q=quarter: 0.3 if len(part[0]) >= 3 else q
        first, _, _ = xfetch(t, end=END - timedelta(days=3), at=(END - timedelta(days=3)).isoformat(), cty_days=10,
                             max_calls=2000)
        for i in range(3):
            t.qc_smp[F - timedelta(days=i)] = 1.2 if quarter is None else 1.003
        log = []
        ida, st, _ = xfetch(t, ida=first, log=log, cty_days=10, max_calls=2000)
        sp, qcp = ida["xs"]["split"], [e for e in log if e[0] == "qcp"]
        days = [(F - timedelta(days=i)).isoformat() for i in range(3)]
        if quarter is None:
            assert (sp["lv"], sp["no"], sp["at"]) == (2, None, END.isoformat())
            assert len(qcp) == 2 + 4 * 3 and st["x"]["split"] == 4                 # F: halves, quarters; then quarters
            assert all((ida["d2"][k]["c2st"], ida["d2"][k]["c2parts"], ida["d2"][k]["cpst"], ida["d2"][k]["cpparts"])
                       == ("ok", 4, "ok", 4) for k in days)
            assert c2_sums(ida) == want_c2(t, ida)
            # a month on, the smallest level that works is looked for again (halves first)
            ida["xs"]["split"]["at"] = (END - timedelta(days=gx.SPLIT_RETRY_DAYS)).isoformat()
            t.qc_smp[F + timedelta(days=1)] = 1.2
            log = []
            e = END + timedelta(days=1)
            ida, _, _ = xfetch(t, ida=ida, log=log, end=e, at=e.isoformat(), cty_days=10, max_calls=2000)
            assert len([x for x in log if x[0] == "qcp"]) == 2 + 4 and ida["xs"]["split"]["at"] == e.isoformat()
        else:
            assert (sp["lv"], sp["no"]) == (0, END.isoformat()) and len(qcp) == 2 + 4 and st["x"]["split"] == 2
            assert all((ida["d2"][k]["c2st"], ida["d2"][k]["c2parts"], ida["d2"][k]["cpst"], ida["d2"][k]["c2frac"])
                       == ("smp", 1, "smp", 0.1) for k in days)


def test_split_part_refused_or_failing_turns_the_split_off():
    """GA4 refuses the country-part filter (HTTP 400: that shape was never probed) or the part read fails: the split
    is off for SPLIT_RETRY_DAYS and every sampled day is judged on its whole read at once (smp) — never left `err`
    and asked again every day. A quota answer on a part says nothing of the split: the day waits, no try counted."""
    days = [F - timedelta(days=i) for i in range(20)]
    for err in ("HTTP 400: INVALID_ARGUMENT: part filter", "HTTP 500: INTERNAL", "HTTP 429: RESOURCE_EXHAUSTED"):
        t = xsmall(60)
        base, _, _ = xfetch(t, ext=False, cty_days=20, max_calls=2000)          # the legacy history: slots known
        for d in days:
            t.qc_smp[d] = 1.0                                                   # sampled, the tie inside

        def fail(kind, a, b, err=err):
            if kind == "qcp":
                raise RuntimeError(err)
        t.fail = fail
        log = []
        ida, st, _ = xown(t, base, log=log, cty_days=20, max_calls=2000)
        assert len([e for e in log if e[0] == "qcp"]) == 1 and st["x"]["split"] == 0
        r = ida["d2"][F.isoformat()]
        if "429" in err:
            assert (r["c2st"], r["c2tries"], ida["xs"]["split"]["no"]) == ("err", 0, None) and st["x"]["qstops"] == 1
            continue
        assert ida["xs"]["split"] == {"lv": 0, "no": END.isoformat(), "at": END.isoformat()}
        assert all((ida["d2"][d.isoformat()]["c2st"], ida["d2"][d.isoformat()]["cpst"],
                    ida["d2"][d.isoformat()]["c2parts"]) == ("smp", "smp", 1) for d in days)
        assert c2_sums(ida) == want_c2(t, ida)
        log = []
        ida, st, _ = xown(t, ida, log=log, at=(END + timedelta(days=1)).isoformat(), cty_days=20, max_calls=2000)
        assert not [e for e in log if e[0] in ("qb", "qcf", "qcp", "paid")]     # nothing left to ask again


def test_a_failing_day_is_asked_at_most_iday_tries_times_then_every_four_weeks():
    t = xsmall(60)
    base, _, _ = xfetch(t, ext=False, cty_days=20, max_calls=2000)
    bad = F - timedelta(days=5)

    def fail(kind, a, b):
        if kind == "qcf" and a == bad:
            raise RuntimeError("HTTP 500: INTERNAL")
    t.fail = fail
    ida, asked = base, []
    for i in range(gu.IDAY_TRIES + 2):
        e = END + timedelta(days=i)
        log = []
        ida, st, _ = xown(t, ida, log=log, at=e.isoformat(), cty_days=20, max_calls=2000)
        asked.append(len([x for x in log if x[0] == "qcf" and x[1] == bad]))
    r = ida["d2"][bad.isoformat()]
    assert asked == [1] * gu.IDAY_TRIES + [0, 0]
    assert (r["c2st"], r["c2tries"], r["cpst"], r["cptries"]) == ("err", 3, "err", 3) and st["x"]["left"] == 0
    assert all(ida["d2"][d.isoformat()]["c2st"] == "ok" for d in _days(F - timedelta(days=20), F) if d != bad)
    t.fail = None
    e = date.fromisoformat(r["c2at"]) + timedelta(days=gx.ERR_RETRY_DAYS)
    ida, _, _ = xown(t, ida, at=e.isoformat(), cty_days=20, max_calls=2000)
    r = ida["d2"][bad.isoformat()]
    assert (r["c2st"], r["c2tries"], r["cpst"]) == ("ok", 4, "ok")
    assert c2_sums(ida) == want_c2(t, ida)


# ── (4) ad units by install age ─────────────────────────────────────────────────────────────────

def _au_truth(t, days, dim, hs):
    out = {}
    for d in days:
        for (u, x), (ad, imp, clk) in t.units(d, dim).items():
            lag = (d - x).days
            if x < hs or lag > gu.QB_WIN:
                continue
            k = (gu.iday_week(x), "--" if u == "(not set)" else u, gx.LB_IX[lag])
            v = out.setdefault(k, [0, 0, 0])
            v[0], v[1], v[2] = v[0] + ad, v[1] + imp, v[2] + clk
    return out


def _au_got(ida):
    units = ida["xs"]["au"]["units"]
    out = {}
    for w, slots in ida["au"].items():
        for s, e in slots.items():
            for i in range(len(gx.LBANDS)):
                if e["r"][i] or e["i"][i] or e["k"][i]:
                    out[(w, units[int(s)], i)] = [e["r"][i], e["i"][i], e["k"][i]]
    return out


def test_ad_units_by_install_age_in_weekly_blocks():
    t = xsmall(120)
    log = []
    ida, st, _ = xfetch(t, log=log, cty_days=30, max_calls=2000)
    assert len([e for e in log if e[0] == "au"]) == 1                              # a fetch with legacy reads: one
    ida, st, _ = xown(t, ida, log=log, cty_days=30, max_calls=2000)                # its own fetch: the rest
    blocks = [(e[1], e[2]) for e in log if e[0] == "au"]
    assert all((b - a).days == 6 for a, b in blocks[:-1]) and blocks == sorted(blocks, reverse=True)
    done = sorted(k for k, r in ida["d2"].items() if r.get("aust") == "ok")
    assert done and all(ida["d2"][k]["tie_au"] in (None, 1.0) for k in done)
    days = [date.fromisoformat(k) for k in done]
    assert _au_got(ida) == {k: v for k, v in _au_truth(t, days, "adUnitName", t.start).items() if any(v)}
    assert set(ida["xs"]["au"]["units"]) == {"Splash Inter", "Home Banner", "Native List", "--"}
    # the newest block waits until it is whole, then goes in ONE call
    pending = [d for d in _days(F - timedelta(days=30), F) if d.isoformat() not in done]
    assert pending and len(pending) < gx.AU_DAYS
    n = 0
    for i in range(1, 9):
        e = END + timedelta(days=i)
        t2 = XTruth(t.start, e)
        log = []
        ida, _, _ = xfetch(t2, ida=ida, end=e, at=e.isoformat(), log=log, cty_days=30, max_calls=2000)
        n += len([x for x in log if x[0] == "au"])
    assert n == 1


def test_ad_unit_shape_fallback_and_sampled_blocks_go_daily():
    t = xsmall(60)
    t.au_refuse = {("adUnitName", 3), ("adUnitName", 2)}
    log = []
    ida, _, _ = xfetch(t, log=log, cty_days=20, max_calls=2000)
    ida, _, _ = xown(t, ida, log=log, cty_days=20, max_calls=2000)
    asked = [(e[3]["dimensions"][0]["name"], len(e[3]["metrics"])) for e in log if e[0] == "au"]
    assert asked[:3] == [("adUnitName", 3), ("adUnitName", 2), ("adFormat", 3)]
    assert ida["xs"]["au"]["dim"] == "adFormat" and set(asked[3:]) == {("adFormat", 3)}
    assert set(ida["xs"]["au"]["units"]) <= {"Interstitial", "Banner", "Native", "--"}
    assert {(r["audim"], r["aumets"]) for r in ida["d2"].values() if r.get("aust")} == {("adFormat", 3)}
    t3 = xsmall(60)
    t3.au_refuse = {(d, n) for d in ("adUnitName", "adFormat") for n in (2, 3)}
    ida3, st3, _ = xfetch(t3, cty_days=20, max_calls=2000)
    assert ida3["xs"]["au"]["off"] == END.isoformat() and st3["x"]["errors"] == 0 and not ida3["au"]
    # a block sampled over several days: shorter blocks (7 → 3 → 1), nothing of it folded
    t4 = xsmall(60)
    t4.au_smp = 1
    ida4, _, _ = xfetch(t4, cty_days=20, max_calls=2000)
    assert ida4["xs"]["au"]["blk"] == 3 and not [r for r in ida4["d2"].values() if r.get("aust")]
    ida4, _, _ = xfetch(t4, ida=ida4, at=(END + timedelta(days=1)).isoformat(), cty_days=20, max_calls=500)
    assert ida4["xs"]["au"]["blk"] == 1 and not [r for r in ida4["d2"].values() if r.get("aust")]
    ida4, _, _ = xfetch(t4, ida=ida4, at=(END + timedelta(days=2)).isoformat(), cty_days=20, max_calls=500)
    assert {r.get("aublk") for r in ida4["d2"].values() if r.get("aust")} == {1}
    assert {r.get("aust") for r in ida4["d2"].values() if r.get("aust")} == {"ok"}
    # sampled only past 3 days (or lossy past 3 days): 3-day blocks from then on, folded whole
    for knob in ("au_smp", "au_loss"):
        t5 = xsmall(60)
        setattr(t5, knob, 3)
        log = []
        ida5, _, _ = xfetch(t5, cty_days=20, max_calls=2000)
        ida5, _, _ = xfetch(t5, ida=ida5, log=log, at=(END + timedelta(days=1)).isoformat(), cty_days=20,
                            max_calls=500)
        assert ida5["xs"]["au"]["blk"] == 3
        assert {(e[2] - e[1]).days for e in log if e[0] == "au"} <= {0, 1, 2}
        done = [k for k, r in ida5["d2"].items() if r.get("aust")]
        assert done and {ida5["d2"][k]["aust"] for k in done} == {"ok"}
        assert _au_got(ida5) == {k: v for k, v in _au_truth(t5, [date.fromisoformat(k) for k in done], "adUnitName",
                                                             t5.start).items() if any(v)}


def test_a_short_sampled_ad_unit_block_halves_the_block_size_not_its_length():
    """The first AU block read is a short run (a day whose Q-B is still `retry` breaks it) and comes back sampled:
    the block size goes 7 → 3 (then 3 → 1), never straight to the short run's half."""
    t = xsmall(60)
    q = F - timedelta(days=6)
    t.qb_short[q] = 10                                  # Q-B of q short: `retry` this fetch → not eligible
    t.au_smp = 1                                        # every AU read of more than a day comes back sampled
    log = []
    ida, _, _ = xfetch(t, log=log, cty_days=22, max_calls=2000)
    assert ida["days"][q.isoformat()]["st"] == "retry"
    assert [(e[1], e[2]) for e in log if e[0] == "au"] == [(F - timedelta(days=8), F - timedelta(days=7))]
    assert ida["xs"]["au"]["blk"] == 3
    ida, _, _ = xown(t, ida, at=(END + timedelta(days=1)).isoformat(), cty_days=22, max_calls=2000)
    assert ida["xs"]["au"]["blk"] == 1


def test_ad_unit_dimension_change_starts_the_cells_over():
    """Clicks refused later (the same dimension): the units stay, the days read without clicks say so (aumets 2, k
    stays 0). Every unit-name shape refused later: GA4 gives formats only — the unit-name cells, units and their days'
    ledger start over in adFormat; names and formats never share a slot list."""
    t = xsmall(60)
    ida, _, _ = xfetch(t, cty_days=20, max_calls=2000)
    ida, _, _ = xown(t, ida, cty_days=20, max_calls=2000)
    xa = ida["xs"]["au"]
    assert (xa["dim"], xa["udim"]) == ("adUnitName", "adUnitName") and "Splash Inter" in xa["units"]
    done0 = {k for k, r in ida["d2"].items() if r.get("aust") in gx.FOLDED}
    assert done0 and {(ida["d2"][k]["audim"], ida["d2"][k]["aumets"]) for k in done0} == {("adUnitName", 3)}
    units0 = list(xa["units"])
    e1 = END + timedelta(days=7)
    t1 = XTruth(t.start, e1)
    t1.au_refuse = {("adUnitName", 3)}
    ida, _, _ = xfetch(t1, ida=ida, end=e1, at=e1.isoformat(), cty_days=20, max_calls=2000)    # refused: err
    ida, _, _ = xown(t1, ida, end=e1, at=(e1 + timedelta(days=1)).isoformat(), cty_days=20, max_calls=2000)
    xa = ida["xs"]["au"]
    assert (xa["dim"], xa["mets"], xa["udim"], xa["units"]) == ("adUnitName", list(gx.AU_METS3[:2]), "adUnitName",
                                                                units0)
    new = {k for k, r in ida["d2"].items() if r.get("aust") in gx.FOLDED} - done0
    assert new and {ida["d2"][k]["aumets"] for k in new} == {2} and {ida["d2"][k]["aumets"] for k in done0} == {3}
    e2 = e1 + timedelta(days=7)
    t2 = XTruth(t.start, e2)
    t2.au_refuse = {("adUnitName", 3), ("adUnitName", 2)}
    ida, _, _ = xfetch(t2, ida=ida, end=e2, at=e2.isoformat(), cty_days=20, max_calls=2000)
    for _ in range(2):                                  # (the days the restart reopened: the next own fetch)
        ida, st, _ = xown(t2, ida, end=e2, at=(e2 + timedelta(days=1)).isoformat(), cty_days=20, max_calls=2000)
    xa = ida["xs"]["au"]
    assert (xa["dim"], xa["udim"]) == ("adFormat", "adFormat")
    assert set(xa["units"]) <= {"Interstitial", "Banner", "Native", "--"}
    done = sorted(k for k, r in ida["d2"].items() if r.get("aust") in gx.FOLDED)
    assert done and {(ida["d2"][k]["audim"], ida["d2"][k]["aumets"]) for k in done} == {("adFormat", 3)}
    assert not [k for k, r in ida["d2"].items() if r.get("aust") and k not in done]
    assert _au_got(ida) == {k: v for k, v in _au_truth(t2, [date.fromisoformat(k) for k in done], "adFormat",
                                                        t2.start).items() if any(v)}
    assert st["x"]["left"] == 0


# ── (3) app_remove by country ───────────────────────────────────────────────────────────────────

def test_app_remove_by_country_ledger():
    t = xsmall(90)
    t.rm_other[F - timedelta(days=20)] = 0.5
    log = []
    ida, st, _ = xfetch(t, log=log, cty_days=40, max_calls=2000)
    rm = ida["rm"]
    assert (min(rm), max(rm)) == ((F - timedelta(days=40)).isoformat(), (F - timedelta(days=11)).isoformat())
    assert len([e for e in log if e[0] == "rm"]) == 1             # 30 days; the newest 4 (to F − 7) wait for a week
    ix = {cc: str(i) for i, cc in enumerate(ida["cset"])}
    for k, r in rm.items():
        d = date.fromisoformat(k)
        want = {}
        for cc, u, e in t.rm_rows(d):
            s = ix.get(gu._slot_cc(cc), ix["ZZ"])
            if d == F - timedelta(days=20):
                u, e = u - int(u * 0.5), e - int(e * 0.5)
            p = want.get(s) or [0, 0]
            want[s] = [p[0] + u, p[1] + e]
        assert r["s"] == want
        if d == F - timedelta(days=20):
            assert r["st"] == "gap" and r["o"][1] > 0 and r["tie"] == 1.0
        else:
            assert (r["st"], r["tie"], r["o"]) == ("ok", 1.0, [0, 0])
    # steady state: one block a week
    n = 0
    for i in range(1, 15):
        e = END + timedelta(days=i)
        lg = []
        ida, _, _ = xfetch(XTruth(t.start, e), ida=ida, end=e, at=e.isoformat(), log=lg, cty_days=40, max_calls=2000)
        n += len([x for x in lg if x[0] == "rm"])
    assert n == 2 and max(ida["rm"]) == (F + timedelta(days=3)).isoformat()


def test_app_remove_refused_turns_off_for_four_weeks():
    t = xsmall(90)
    t.rm_refuse = True
    log = []
    ida, st, _ = xfetch(t, log=log, cty_days=40, max_calls=2000)
    ida, st, _ = xown(t, ida, log=log, cty_days=40, max_calls=2000)
    assert len([e for e in log if e[0] == "rm"]) == 1 and ida["xs"]["rm"]["off"] == END.isoformat()
    assert ida["rm"] == {} and st["x"]["errors"] == 0 and st["x"]["left"] == 0     # nothing left that a fetch would do
    log = []
    ida, _, _ = xown(t, ida, log=log, at=(END + timedelta(days=3)).isoformat(), cty_days=40, max_calls=2000)
    assert not [e for e in log if e[0] == "rm"]
    t.rm_refuse = False
    ida, st, _ = xown(t, ida, log=log, at=(END + timedelta(days=28)).isoformat(), cty_days=40, max_calls=2000)
    assert [e for e in log if e[0] == "rm"] and ida["xs"]["rm"]["off"] is None and ida["rm"] and st["x"]["rm_days"]


def test_a_slot_added_later_records_the_extension_days_before_it(monkeypatch):
    """A country that grows into its own slot: the late-age, paid and app_remove days that went in before (into "ZZ")
    are recorded per kind (xs.since), like the legacy cset_since; from then on its cells go to its slot."""
    monkeypatch.setattr(gu, "CSET_N", 2)
    surge = END - timedelta(days=20)

    def cty(x):
        return (("US", 70), ("IN", 29), ("JP", 1), ("FR", 30 if x >= surge else 0))
    t = XTruth(END - timedelta(days=99), END, cty=cty)
    e0 = surge + timedelta(days=gu.IDAY_LATE - 1)
    ida, _, _ = xfetch(t, end=e0, at=e0.isoformat(), cty_days=60, max_calls=2000)
    assert ida["cset"] == ["US", "IN", "--", "ZZ"] and "since" not in ida["xs"]
    added = None
    for i in range(1, 20):
        e = e0 + timedelta(days=i)
        before = {"c2": sorted(k for k, r in ida["d2"].items() if r.get("c2st") in gx.FOLDED),
                  "cp": sorted(k for k, r in ida["d2"].items() if r.get("cpst") in gx.FOLDED),
                  "rm": sorted(ida["rm"])}
        ida, _, _ = xfetch(t, ida=ida, end=e, at=e.isoformat(), cty_days=60, max_calls=2000)
        if "FR" in ida["cset"] and added is None:
            added = before
    assert added is not None and ida["cset"][4] == "FR"
    assert ida["xs"]["since"] == {"FR": {k: gu._date_ranges(v) for k, v in added.items()}}
    s = str(ida["cset"].index("FR"))
    assert any(s in slots for slots in ida["cp"].values()) and any(r["s"].get(s) for r in ida["rm"].values())


# ── cost ─────────────────────────────────────────────────────────────────────────────────────────

def test_steady_state_cost_after_the_reread():
    t = XTruth(END - timedelta(days=99), END + timedelta(days=28))
    ida, _, _ = xfetch(t, end=END - timedelta(days=28), cty_days=60, max_calls=3000)
    ida, st, _ = xown(t, ida, end=END - timedelta(days=28), cty_days=60, max_calls=3000)    # the re-read
    assert st["x"]["left"] == 0
    ida["born"] = (END - timedelta(days=200)).isoformat()
    calls = xcalls = 0
    for i in range(-27, 29):
        e = END + timedelta(days=i)
        ida, st, _ = xfetch(t, ida=ida, end=e, at=e.isoformat(), cty_days=60)
        calls += st["calls"]
        xcalls += st["xcalls"]
        assert st["x"]["left"] == 0                                                  # no own fetch needed
    assert calls == 3 * 56                                                           # Q-B, Q-C, Q-T: as before
    assert xcalls <= 56 * (1 + 2 / 7) + 2                                            # + paid, a unit and an RM block a week


# ── the files ────────────────────────────────────────────────────────────────────────────────────

def _gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def test_ext_files_apart_load_and_old_files_still_load(tmp_path):
    t = xsmall(200)
    ida, _, _ = xfetch(t, cty_days=60, max_calls=2000)
    ida["xs"]["lo"] = (F + timedelta(days=500)).isoformat()      # (a horizon far ahead: everything is "old" now)
    aid = "ca-app-pub-0000000000000000~0000000042"
    d = str(tmp_path)
    assert gu.save_iday(d, aid, ida) is True
    hot = _gz(gu.iday_path(d, aid))
    assert not set(gu.X_KEYS) & set(hot)                                             # never in the iday files
    xh, xo = _gz(gx.x_path(d, aid)), _gz(gx.x_path(d, aid, old=True))
    assert xh["xv"] == gx.X_V and xh["src"] == ida["src"] and xo["c2"] and xo["d2"] and xo["rm"] and not xh["d2"]
    back = gu.load_iday(d, aid)
    assert dump(back) == dump(ida) and dump(vb.load_iday(d, aid)) == dump(ida)
    assert gu.save_iday(d, aid, back) is False                                       # unchanged: nothing written
    # without the extension's files (every file written before it): the same legacy data, its keys empty
    for old in (False, True):
        os.remove(gx.x_path(d, aid, old=old))
    back2 = gu.load_iday(d, aid)
    assert dump(legacy(back2)) == dump(legacy(ida)) and all(back2[k] == {} for k in gu.X_KEYS)
    assert vb.load_iday(d, aid)["c2"] == {}
    # a damaged extension part: the extension starts over, the legacy data never does
    gu.save_iday(d, aid, ida)
    with open(gx.x_path(d, aid, old=True), "wb") as f:
        f.write(b"\x1f\x8bnot gzip")
    back3 = gu.load_iday(d, aid)
    assert back3 is not None and dump(legacy(back3)) == dump(legacy(ida)) and back3["c2"] == {}
    # an extension file of another stream is never merged
    gx.save_ext(d, aid, dict(ida, src=["1", "2"]))
    assert gu.load_iday(d, aid)["d2"] == {}
    # a history that started over (no extension data): its old files go
    assert gu.save_iday(d, aid, dict(ida, **{k: {} for k in gu.X_KEYS})) is True
    assert not os.path.exists(gx.x_path(d, aid)) and not os.path.exists(gx.x_path(d, aid, old=True))


def test_x_split_keeps_only_frozen_parts_old():
    lo = date(2026, 6, 17)
    cut = date(2026, 6, 1)
    weeks = [gu.iday_week(cut - timedelta(days=n)) for n in (400, 430, 433, 434, 440, 500)]
    ida = {"src": ["1", "2"], "v": 1, "xs": {"lo": lo.isoformat()},
           "c2": {w: {"0": {"r2": [1, 0, 0], "u2": [0] * 4}} for w in weeks},
           "cp": {}, "au": {}, "rm": {k: {"st": "ok"} for k in ("2026-05-31", "2026-06-01")},
           "d2": {k: {"c2st": "ok"} for k in ("2026-05-31", "2026-06-01")}}
    hot, old = gx.x_split(ida)
    assert sorted(old["d2"]) == sorted(old["rm"]) == ["2026-05-31"] and sorted(hot["d2"]) == ["2026-06-01"]
    for w in weeks:                               # an install week any day ≥ cut can still reach stays hot
        reach = date.fromisoformat(w) + timedelta(days=6) >= cut - timedelta(days=gu.QB_WIN)
        assert (w in hot["c2"]) == reach and (w in old["c2"]) != reach


def test_file_sizes_for_a_long_app(tmp_path):
    """A long, wide app at its largest: 120 install weeks × 35 slots (c2, cp), 60 ad units, 400 ledger days, 35
    slots of app_remove — jittered like real data: the extension's files stay well under the iday caps."""
    import random
    rnd = random.Random(7)

    def li(n, top):
        return [rnd.randint(0, top) for _ in range(n)]
    weeks = [gu.iday_week(END - timedelta(days=7 * i)) for i in range(120)]
    days = [(END - timedelta(days=i)).isoformat() for i in range(400)]
    ida = {"src": ["1", "2"], "v": 1, "to": days[0], "xs": {"lo": days[-1], "au": {"units": ["u%d" % i for i in range(60)]}},
           "c2": {w: dict({str(s): {"r2": li(3, 10 ** 7), "u2": li(4, 5000)} for s in range(35)},
                          gap={"r2": li(3, 10 ** 5)}) for w in weeks[:70]},
           "cp": {w: {str(s): {"n": rnd.randint(0, 9000), "r": li(11, 10 ** 7), "u": li(11, 9000)} for s in range(35)}
                  for w in weeks},
           "au": {w: {str(u): {"r": li(11, 10 ** 7), "i": li(11, 10 ** 5), "k": li(11, 3000)} for u in range(60)}
                  for w in weeks},
           "d2": {k: {"c2st": "ok", "c2tries": 1, "c2at": k, "tie_late": 1.0, "c2loss": False, "c2oth": False,
                      "c2smp": False, "c2frac": None, "c2rows": rnd.randint(1000, 35000), "c2tok": 1, "c2parts": 1,
                      "cpst": "ok", "cptries": 1, "cpat": k, "cpshare": 0.4, "cpn": 0.5, "cpx": 0.0, "cploss": False,
                      "cpoth": False, "cpsmp": False, "cpfrac": None, "cprows": 9000, "cptok": 1, "cpparts": 1,
                      "aust": "ok", "autries": 1, "auat": k, "tie_au": 1.0, "auloss": False, "auoth": False,
                      "ausmp": False, "aufrac": None, "aublk": 7, "audim": "adUnitName", "aumets": 3} for k in days},
           "rm": {k: {"s": {str(s): [rnd.randint(0, 900), rnd.randint(0, 1100)] for s in range(35)}, "o": [0, 0],
                      "st": "ok", "at": k, "ev": 9000, "tie": 1.0, "tu": 0.99} for k in days}}
    gx.save_ext(str(tmp_path), "app", ida)
    size = sum(os.path.getsize(gx.x_path(str(tmp_path), "app", old=o)) for o in (False, True)
               if os.path.exists(gx.x_path(str(tmp_path), "app", old=o)))
    assert size < 2500 * 1024, size


def test_a_bug_in_the_extension_never_costs_the_legacy_fetch(monkeypatch):
    t = xsmall(40)
    base, _, _ = xfetch(t, ext=False)

    def boom(*a, **k):
        raise ZeroDivisionError("a bug")
    monkeypatch.setattr(gx, "qcx_parse", boom)
    ida, st, _ = xfetch(t)
    assert st["x"]["errors"] == 1 and all(ida[k] == {} for k in gu.X_KEYS if k != "xs")
    assert dump(legacy(ida)) == dump(legacy(base))


def test_ext_init_failure_never_costs_the_legacy_fetch(monkeypatch):
    t = xsmall(40)
    base, _, _ = xfetch(t, ext=False)

    def boom(run):
        raise ZeroDivisionError("a bug")
    monkeypatch.setattr(gx, "Ext", boom)
    ida, st, _ = xfetch(t)
    assert st["x"] == {"errors": 1, "left": 0} and dump(ida) == dump(base)


def test_legacy_totals_come_before_the_extension():
    """A fetch whose time budget runs out right after the legacy reads: Q-T still goes (the legacy data as without
    the extension), the extension gets nothing."""
    t = xsmall(60)
    old, _, _ = xfetch(t, ext=False, end=END - timedelta(days=1), at=(END - timedelta(days=1)).isoformat(),
                       max_calls=2000)
    old["born"] = (END - timedelta(days=100)).isoformat()                         # (no late check)
    got = {}
    for ext in (False, True):
        log = []
        ga = XGA(t, log=log)
        ida, st = gu.fetch_iday(ga, t.store(), old, END, stop=lambda: ga.calls >= 3, at=END.isoformat(), ext=ext)
        got[ext] = (dump(legacy(ida)), [e[0] for e in log], st)
    assert got[True][0] == got[False][0] and got[False][1] == ["qb", "qc", "qt"]
    assert got[True][1] == ["qb", "qcf", "qt"] and got[True][2]["x"]["why"] == "budget"
    assert got[True][2]["why"] is None and got[True][2]["qstop"] is False


def test_x_only_fetch_reads_no_legacy_day_and_changes_no_legacy_key():
    """x_only (the app's history is whole; the fetch exists only for the extension): no legacy step — not even a new
    day that is due — and every legacy key byte for byte as it came in."""
    t = xsmall(120)
    old, _, _ = xfetch(t, ext=False, end=END - timedelta(days=2), at=(END - timedelta(days=2)).isoformat(),
                       max_calls=2000)
    assert old["done"] is True
    log = []
    ida, st, _ = xfetch(t, ida=old, log=log, x_only=True, cty_days=30, max_calls=2000)
    assert dump(legacy(ida)) == dump(legacy(old)) and st["calls"] == 0 and st["xcalls"] > 0
    assert "qt" not in {e[0] for e in log}
    read = {e[1] for e in log if e[0] in ("qb", "qcf", "paid")}
    assert read and max(read) == F - timedelta(days=2)                         # F − 1, F: the legacy's, untouched
    assert all(ida["d2"][d.isoformat()]["c2st"] == "ok" for d in _days(F - timedelta(days=30), F - timedelta(days=2)))
    # a file of another stream (or none): nothing to save, its real fetch starts it over
    assert gu.fetch_iday(XGA(t), t.store(), None, END, ext=True, x_only=True)[0] is None
    assert gu.fetch_iday(XGA(t), t.store(), dict(old, src=["1", "2"]), END, ext=True, x_only=True)[0] is None


# ── the build's wiring ──────────────────────────────────────────────────────────────────────────

class XStub(Stub):
    def __init__(self, truth, iday, *a, **kw):
        super().__init__(truth, iday, *a, **kw)
        self.iday = XGA(iday, sid=self.stream_id)

    def _post(self, method, body):
        dims = tuple(d["name"] for d in body.get("dimensions") or [])
        ev = [e.get("filter", {}).get("stringFilter", {}).get("value")
              for e in body["dimensionFilter"]["andGroup"]["expressions"][2:]] if body.get("dimensionFilter") else []
        if (dims[1:] == ("firstSessionDate", "date") or (dims == ("date", "countryId") and "app_remove" in ev)):
            self.calls += 1
            self.log.append((self.property_id, self.stream_id, body))
            return self.iday._post(method, body)
        return super()._post(method, body)


class XWorld(World):
    def __init__(self, monkeypatch):
        super().__init__(monkeypatch)
        for sid, tr in self.truths.items():
            it = self.idays[sid]
            self.idays[sid] = x = XTruth(tr.start, tr.end, new=lambda d, tr=tr: tr.new[d], a1=tr.a1,
                                         retf=lambda lag: 1.0 if lag == 0 else 0.05 / lag ** 0.5)
            x.win = it.win

    def _app(self, tok, pid, sid):
        return XStub(self.truths[sid], self.idays[sid], tok, pid, sid, log=self.log)


NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
CFG_ON = dict(CFG, iday=True)


def test_refresh_all_counts_line_and_plan(monkeypatch, tmp_path):
    w = XWorld(monkeypatch)
    out = w.run(tmp_path, cfg={"iday": True, "iday_ext": True})
    line = gx.iday_x_log_line(out)
    assert line.startswith("ga4 iday ext: apps 2, late-age days ") and gx.iday_x_log_line({}) is None
    for secret in (PID, SID, "com.secret", "US", "IN", "Splash", "Banner", "tok-SECRET", "secret", "$", "."):
        assert secret not in line
    nums = [int(x.strip(",()")) for x in line.split() if x.strip(",()").isdigit()]
    assert len(nums) == len(gx.X_COUNTS) and all(n >= 0 for n in nums)
    st = gu.load_state(str(tmp_path))["fetch"]
    a1 = sorted(st)[0]
    assert set(st[a1]["iday"]["x2"]) == {"done", "left", "calls", "tok", "why"}
    assert set(st[a1]["tokens"]) == {"usage", "vuse", "ret", "iday", "iday_x"}       # its tokens apart from the legacy
    assert os.path.exists(gx.x_path(str(tmp_path), a1))
    # plan: an app whose extension still has days to do keeps its install-value-only fetches
    meta = {"v": gu.STORE_V, "history_start": "2026-01-01", "window_end": "2026-09-23", "next_rebuild": "2026-10-10",
            "covered": [["2026-01-01", "2026-09-23"]], "property_id": PID, "stream_id": SID}
    meta = gu.store_meta(dict(meta, impact_v=gu.IMPACT_V, ret_from="2026-01-01"))
    whole = {"property_id": PID, "stream_id": SID, "last_ok": "2026-09-25T09:00:00Z",
             "iday": {"v": 1, "done": True, "x2": {"done": False, "left": 9}}}
    cfg = dict(CFG, iday=True, iday_ext=True)
    assert gu.plan(whole, meta, END, NOW, cfg) == "iday"
    assert gu.plan(whole, meta, END, NOW, dict(cfg, iday_ext=False)) is None
    whole["iday"]["x2"]["done"] = True
    assert gu.plan(whole, meta, END, NOW, cfg) is None
    # its own clock: an extension-only fetch at most every IDAY_EVERY_HOURS (last_iday_x), never on last_iday
    whole["iday"]["x2"]["done"] = False
    assert gu.plan(dict(whole, last_iday="2026-09-25T11:30:00Z"), meta, END, NOW, cfg) == "iday"
    assert gu.plan(dict(whole, last_iday_x="2026-09-25T11:30:00Z"), meta, END, NOW, cfg) is None
    filling = dict(whole, iday={"v": 1, "done": False}, last_iday_x="2026-09-25T11:30:00Z")
    assert gu.plan(filling, meta, END, NOW, cfg) == "iday"
    assert gu.plan(dict(filling, last_iday="2026-09-25T11:30:00Z"), meta, END, NOW, cfg) is None
    whole["iday"]["x2"]["done"] = True
    never = dict(whole, iday={"v": 1, "done": True})                                 # IDAY_EXT never ran: at once
    assert gu.plan(never, meta, END, NOW, cfg) == "iday" and gu.plan(never, meta, END, NOW, CFG_ON) is None
    assert gu.x_only_fetch(never) and not gu.x_only_fetch({"iday": {"done": False}}) and not gu.x_only_fetch({})
    # off: no line, no file, the state as before
    w2 = XWorld(monkeypatch)
    out2 = w2.run(tmp_path / "off", cfg={"iday": True})
    assert "iday_x" not in out2 and gx.iday_x_log_line(out2) is None
    assert "x2" not in gu.load_state(str(tmp_path / "off"))["fetch"][a1]["iday"]
    assert set(gu.load_state(str(tmp_path / "off"))["fetch"][a1]["tokens"]) == {"usage", "vuse", "ret", "iday"}


def test_x_only_fetches_through_refresh_all_leave_the_legacy_as_without_it(monkeypatch, tmp_path):
    """Both apps' histories whole: with IDAY_EXT on, plan() gives them install-value-only fetches that are the
    extension's alone — the legacy files, the legacy counts line and the legacy state stay exactly what they are with
    it off (where no such fetch happens at all), until the extension's days are done."""
    base = tmp_path / "base"
    w = XWorld(monkeypatch)
    for i in range(4):
        w.run(base, now=NOW + timedelta(hours=21 * i), cfg={"iday": True})
    st0 = gu.load_state(str(base))["fetch"]
    assert all(st0[a]["iday"]["done"] is True and "x2" not in st0[a]["iday"] for a in st0)
    later = NOW + timedelta(hours=21 * 3 + 3)                                  # inside min_hours: no real fetch
    out = {}
    for mode in ("off", "on"):
        d = tmp_path / mode
        shutil.copytree(str(base), str(d))
        cfg = {"iday": True, "iday_ext": mode == "on"}
        out[mode] = [w.run(d, now=later + timedelta(hours=2 * i), cfg=cfg) for i in range(6)]
    a, b = _files(tmp_path / "off"), _files(tmp_path / "on")
    legacy_files = [k for k in a if k.endswith(".json.gz")]
    assert legacy_files and all(a[k] == b[k] for k in legacy_files)              # every legacy file: same bytes
    assert [k for k in b if ".x." in k] and not [k for k in a if ".x." in k]
    for o_off, o_on in zip(out["off"], out["on"]):
        assert o_off["counts"]["fetched"] == o_on["counts"]["fetched"] == 0
        assert gu.iday_log_line(o_off) == gu.iday_log_line(o_on)                # the legacy line: identical
    assert out["on"][0]["iday_x"]["apps"] == 2 and out["on"][0]["iday_x"]["late"] > 0
    s_off, s_on = gu.load_state(str(tmp_path / "off"))["fetch"], gu.load_state(str(tmp_path / "on"))["fetch"]
    for aid in s_off:
        on = copy.deepcopy(s_on[aid])
        x2 = on["iday"].pop("x2")
        assert on.pop("last_iday_x") and x2["done"] is True and x2["left"] == 0
        assert on == s_off[aid]                                             # every legacy key (last_iday too)
    assert sum(1 for o in out["on"] if (o.get("iday_x") or {}).get("apps")) < 6   # done: no more of its fetches
