"""GA4 flag probe (admob_iq.fetch.ga4_flag_probe) — offline against a small fake GA4 and a synthetic cube store
(SYNTHETIC: made-up countries, days and money): the apps and days chosen from the store's ledgers by data (the most
flagged final days, ~2 weeks apart, controls beside them), each read's request (R1 / R2 / R7 byte for byte the cube's
own reads, R5 / R6 in-lists of one), the metadata kept verbatim (samplingMetadatas, dataLossFromOtherRow, thresholding,
emptyReason) and what it flags ("(other)" rows, a hidden "(other)", a cut answer, pages), the comparisons with the day's
total, the call caps and the quota stops (the other probes' and the build's floors), resume, the private result's shape,
a PUBLIC log that carries counts only, and the workflow file."""
import copy
import gzip
import json
import os
import re
import time
from datetime import date, timedelta

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_cube as gcu
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_flag_probe as fp
from admob_iq.fetch import ga4_paid
from admob_iq.fetch import ga4_uninstall as gu
from tests.test_ga4_device_probe import AID, KEY, NOW, PID, RT, SECRETS, SID, TOK, unit

CTRY = (("XA", 3), ("XB", 2), ("XC", 1), ("(not set)", 1))      # country, weight (made up)
FOLD = "XC"                                                      # the country a folding read answers as "(other)"
USERS = 4
AGES = 40                                                        # install ages 0 … 39 on every activity day
PSHARE = 0.25                                                    # the Google Ads users' share (made up)
TODAY = NOW.date()                                               # the unit's time zone is UTC
HI = TODAY - timedelta(days=gcu.FINAL_LAG)                       # the newest final day
T_LED = 5_000_000                                                # a ledger's "t" (micros, made up)
AID2, AID3, AID4 = (AID[:-2] + s for s in ("12", "13", "14"))
PID2, PID3, PID4 = (PID[:-1] + s for s in ("1", "2", "3"))
SID2, SID3, SID4 = (SID[:-1] + s for s in ("2", "3", "4"))
KEYS = [gu.file_key(a) for a in (AID, AID2, AID3, AID4)]
PRIV = SECRETS + [AID2, AID3, AID4, PID2, PID3, PID4, SID2, SID3, SID4] + KEYS


def iso(n):
    """The final edge − n days."""
    return (HI - timedelta(days=n)).isoformat()


FL = [iso(7 * k) for k in range(20)]                             # a flagged day a week back to ~19 weeks
CLEAN = [iso(7 * k + 3) for k in range(20)]                      # an unflagged day 3 days before each
PICKS = [iso(14 * k) for k in range(10)]                         # what the ~2-week spread takes of FL
ORDER = [(PICKS[0], "fl"), (iso(3), "ctl"), (PICKS[1], "fl"), (PICKS[2], "fl"), (iso(31), "ctl"), (PICKS[3], "fl"),
         (PICKS[4], "fl"), (iso(59), "ctl")] + [(D, "fl") for D in PICKS[5:]]


def micros(age, w):
    return USERS * w * (1000 + 37 * (age % 9))


def total(share=1.0, ctry=None, ages=range(AGES)):
    return sum(int(round(micros(a, w) * share)) for a in ages for c, w in CTRY if ctry is None or c in ctry)


class FakeGA:
    """Every activity day: USERS × weight users per (install day, country), install ages 0 … AGES − 1. Filters are
    honoured (countryId / firstSessionDate in-lists, the paid channel: PSHARE of everyone). fold: kinds whose FOLD rows
    come back as "(other)" (+ dataLossFromOtherRow); hide: kinds whose FOLD rows are dropped with the flag kept (an
    in-list's way); meta: kind → metadata added; cut: kinds whose rowCount says more than the rows sent; refuse: kinds
    → HTTP 400; quota: the propertyQuota every answer reports."""

    def __init__(self, refuse=(), meta=None, fold=(), hide=(), cut=(), quota=None):
        self.refuse, self.meta, self.fold, self.hide, self.cut = set(refuse), meta or {}, set(fold), set(hide), set(cut)
        self.quota = quota or {"tokensPerDay": {"consumed": 3, "remaining": 199000},
                               "tokensPerHour": {"consumed": 3, "remaining": 39000}}
        self.bodies = []

    @staticmethod
    def kind(body):
        dims = tuple(x["name"] for x in body["dimensions"])
        if dims != gcu.DIMS:
            return {("date",): "R2", ("date", "countryId"): "R3", ("date", "firstSessionDate"): "R4"}[dims]
        names = [e["filter"]["fieldName"] for e in body["dimensionFilter"]["andGroup"]["expressions"] if "filter" in e]
        rest = [n for n in names if n not in ("platform", "streamId")]
        by = {"countryId": "R5", "firstSessionDate": "R6", ga4_paid.CHANNEL: "R7"}
        return by.get(rest[0] if rest else None, "R1")

    def __call__(self, method, url, token, body=None, params=None):
        assert method == "POST" and token == TOK and url.endswith(":runReport")
        self.bodies.append(copy.deepcopy(body))
        kind = self.kind(body)
        if kind in self.refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: DETAIL-PRIVATE")
        dims = [x["name"] for x in body["dimensions"]]
        mets = [x["name"] for x in body["metrics"]]
        d = date.fromisoformat(body["dateRanges"][0]["startDate"])
        ex = body["dimensionFilter"]["andGroup"]["expressions"]
        lists = {e["filter"]["fieldName"]: e["filter"]["inListFilter"]["values"] for e in ex
                 if "inListFilter" in (e.get("filter") or {})}
        share = PSHARE if ga4_paid.CHANNEL in lists else 1.0
        agg = {}
        for age in range(AGES):
            x = d - timedelta(days=age)
            for c, w in CTRY:
                if c not in lists.get("countryId", [c]) or x.strftime("%Y%m%d") not in lists.get(
                        "firstSessionDate", [x.strftime("%Y%m%d")]):
                    continue
                v = {"date": d.strftime("%Y%m%d"), "firstSessionDate": x.strftime("%Y%m%d"), "countryId": c}
                if c == FOLD and kind in self.hide:
                    continue
                if c == FOLD and kind in self.fold:
                    v.update(firstSessionDate="(other)", countryId="(other)")
                e = agg.setdefault(tuple(v[k] for k in dims), [0, 0])
                e[0] += int(round(USERS * w * share))
                e[1] += int(round(micros(age, w) * share))
        rows = [{"dimensionValues": [{"value": v} for v in k],
                 "metricValues": [{"value": str(e[0]) if m == "activeUsers" else "%.6f" % (e[1] / 1e6)} for m in mets]}
                for k, e in sorted(agg.items())]
        meta = {"currencyCode": "USD", "timeZone": "Etc/UTC"}
        if kind in self.fold or kind in self.hide:
            meta["dataLossFromOtherRow"] = True
        meta.update(self.meta.get(kind, {}))
        off, lim = body.get("offset", 0), body.get("limit", 10000)
        return {"dimensionHeaders": [{"name": x} for x in dims], "metricHeaders": [{"name": x} for x in mets],
                "rows": rows[off:off + lim], "rowCount": len(rows) + (3 if kind in self.cut else 0), "metadata": meta,
                "propertyQuota": copy.deepcopy(self.quota)}


def led(fl, t=T_LED):
    return {"st": "ok", "rows": 9, "loss": 0, "t": t, "fl": fl, "via": "day", "at": "2026-10-14T00:00:00Z", "sv": 2,
            "ol": 0, "n": 1, "cap": 0}


def ledgers(fl=FL, clean=CLEAN, t=T_LED):
    out = {D: led(0, t) for D in clean}
    out.update({D: led(1, t) for D in fl})
    return out


def planned(u=None, fl=FL, clean=CLEAN):
    u = u or unit()
    return dict(u, plan=fp.plan_days(ledgers(fl, clean), TODAY))


def unit_of(aid, pid, sid):
    return dict(unit(), key=gu.file_key(aid), app_id=aid, app_ids=[aid], property_id=pid, stream_id=sid)


def _patch(monkeypatch, fake):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)


def _run(monkeypatch, fake, units=None, last=None, **opts):
    _patch(monkeypatch, fake)
    return fp.run_probe(units or [planned()], "cid", "sec", [("o", RT)], opts, now=NOW, last=last)


def _app(rep, key=KEY):
    return rep["apps"][key]


# ── the apps and days chosen from the store ─────────────────────────────────────────────────────────────────────────

def test_the_days_are_spread_and_the_controls_sit_beside_them():
    p = fp.plan_days(ledgers(), TODAY)
    assert p["hi"] == HI.isoformat() and p["lo"] == (TODAY - timedelta(days=fp.WINDOW)).isoformat()
    assert p["order"] == ORDER and p["r7"] == [D for D, _ in ORDER[:3]]
    assert p["pick"] == {"final": 40, "fl": 20, "clean": 20, "fl_t": 20 * T_LED}
    assert set(p["led"]) == {D for D, _ in ORDER} and p["led"][PICKS[0]]["fl"] == 1
    # flagged days that bunch: the ~2-week pass takes one, the rest are filled farthest-first (a tie: the newer)
    bunch = [iso(n) for n in range(12)]
    assert fp.spread(bunch, 4) == [iso(0), iso(11), iso(5), iso(8)]
    assert fp.spread(bunch, 40) == fp.spread(bunch, 12) and len(fp.spread(bunch, 40)) == 12
    assert fp.spread([], 5) == []
    # controls: the nearest unflagged day to picks 1, 3, 5 (each once, a tie: the newer); no anchor → spread
    assert fp.controls([iso(1), iso(5), iso(9)], [iso(3), iso(6)]) == [(0, iso(1)), (None, iso(5)), (None, iso(9))]
    assert fp.controls([iso(2), iso(4)], [iso(3)], n=1) == [(0, iso(2))]
    q = fp.plan_days(ledgers(fl=[iso(0)], clean=[iso(2), iso(20), iso(40)]), TODAY)
    assert q["order"] == [(iso(0), "fl"), (iso(2), "ctl"), (iso(20), "ctl"), (iso(40), "ctl")]
    # only FINAL days of the window count: newer than the edge or older than the window are never picked
    edge = {(HI + timedelta(days=1)).isoformat(): led(1), (TODAY - timedelta(days=fp.WINDOW + 1)).isoformat(): led(1),
            "not-a-day": led(1), iso(0): led(0, 0)}
    r = fp.plan_days(edge, TODAY)
    assert r["pick"] == {"final": 1, "fl": 0, "clean": 0, "fl_t": 0} and r["order"] == []


def write_month(data_dir, aid, k, days, stream=SID):
    p = gcu.month_path(data_dir, aid, k)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(dict(gcu._empty_month(stream), days=days), f)


def write_store(data_dir, aid, fl, clean, stream=SID, t=T_LED):
    by = {}
    for D, v in ledgers(fl, clean, t).items():
        by.setdefault(D[:7], {})[D] = v
    for k, days in by.items():
        write_month(data_dir, aid, k, days, stream)


LO = TODAY - timedelta(days=fp.WINDOW)                           # the window's first day
OTHER = [(LO + timedelta(days=n)).isoformat() for n in range(10)]  # days of another stream's month, in the window


def write_clone(root):
    """A synthetic private clone: the Uninstall state's routes + cube stores — A: 20 flagged final days (its first
    month in the window replaced by another stream's, full of flags), B: 12, C: 5 in the window (+ 10 out of it; its
    newest month unreadable), D: no store."""
    data = os.path.join(str(root), "data")
    ids = ((AID, PID, SID), (AID2, PID2, SID2), (AID3, PID3, SID3), (AID4, PID4, SID4))
    state = {"routes": {"by_package": {}}, "fetch": {}, "tz": {}}
    for i, (aid, pid, sid) in enumerate(ids):
        pkg = "pkg.synth.%d" % i
        state["routes"]["by_package"][pkg] = {"property_id": pid, "stream_id": sid, "owner": "o"}
        state["fetch"][aid] = {"package": pkg, "meta": {"history_start": "2026-01-01"}}
        state["tz"][pid] = "UTC"
    p = os.path.join(data, "ga4_uninstall", "state.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f)
    write_store(data, AID, FL, CLEAN)
    assert len({D[:7] for D in OTHER}) == 1 and OTHER[0][:7] == CLEAN[-1][:7]
    write_month(data, AID, OTHER[0][:7], {D: led(1) for D in OTHER}, stream="another")   # (its one clean day goes)
    write_store(data, AID2, FL[:12], CLEAN, stream=SID2)
    late = [(HI + timedelta(days=n)).isoformat() for n in (1, 2)]
    old = [(TODAY - timedelta(days=fp.WINDOW + n)).isoformat() for n in range(1, 9)]
    write_store(data, AID3, FL[:5] + late + old, CLEAN[:5], stream=SID3)
    bad = gcu.month_path(data, AID3, HI.strftime("%Y-%m"))
    with open(bad, "wb") as f:                       # an unreadable month: passed over, never a crash
        f.write(b"not a gzip")
    return data


def test_choose_takes_the_two_apps_with_the_most_flagged_final_days(tmp_path):
    data = write_clone(tmp_path)
    units = fp.cp.units_from_state(fp.sp.load_state(str(tmp_path)))
    assert len(units) == 4
    chosen, stores = fp.choose(units, data, NOW)
    assert stores == 3 and [u["key"] for u in chosen] == KEYS[:2]
    a, b = chosen
    assert a["plan"]["pick"]["fl"] == 20 and a["plan"]["order"] == ORDER          # the other stream's month ignored
    assert a["plan"]["pick"]["clean"] == 19 and a["plan"]["led"][ORDER[0][0]] == led(1)
    assert b["plan"]["pick"]["fl"] == 12 and b["property_id"] == PID2
    assert set(fp.ledgers(data, AID, "another", LO, HI)) == set(OTHER)
    assert not set(fp.ledgers(data, AID, SID, LO, HI)) & set(OTHER)
    # a tie on flagged days: more revenue on them first, then the key
    write_store(data, AID3, FL[:12], [], stream=SID3, t=2 * T_LED)
    chosen, _ = fp.choose(units, data, NOW)
    assert [u["key"] for u in chosen] == [KEYS[0], KEYS[2]]
    assert [u["key"] for u in fp.choose(units, data, NOW, n=1)[0]] == [KEYS[0]]


# ── the request bodies ──────────────────────────────────────────────────────────────────────────────────────────────

def test_r1_r2_r7_are_the_cubes_own_reads_byte_for_byte(monkeypatch):
    fake = FakeGA()
    _patch(monkeypatch, fake)
    d = date(2026, 10, 1)
    gcu.split_read(gf.App(TOK, PID, SID, {"quota": None, "stop": None}, max_calls=9), d, total=None)
    gcu.day_total(gf.App(TOK, PID, SID, {"quota": None, "stop": None}, max_calls=9), d)
    gcu.split_read(ga4_paid.App(TOK, PID, SID, {"quota": None, "stop": None}, max_calls=9), d, total=None)
    cube = list(fake.bodies)
    assert [fake.kind(b) for b in cube] == ["R1", "R2", "R7"]
    fake.bodies.clear()
    ga = fp.App(TOK, PID, SID, fp.Run(60, time.monotonic, 70), pr.new_prop(), cap=70)
    day = {"plan": list(fp.KINDS), "reads": {}, "na": {}}
    fp.day_reads(ga, d, day, {})
    sent = {fake.kind(b): b for b in fake.bodies}
    assert list(sent) == list(fp.KINDS) and len(fake.bodies) == 7
    assert [sent["R1"], sent["R2"], sent["R7"]] == cube
    dims = lambda k: [x["name"] for x in sent[k]["dimensions"]]
    assert dims("R1") == dims("R5") == dims("R6") == dims("R7") == ["date", "firstSessionDate", "countryId"]
    assert dims("R2") == ["date"] and dims("R3") == ["date", "countryId"] and dims("R4") == ["date", "firstSessionDate"]
    for b in sent.values():
        assert b["dateRanges"] == [{"startDate": "2026-10-01", "endDate": "2026-10-01"}]
        assert [m["name"] for m in b["metrics"]] == ["activeUsers", "totalAdRevenue"]
        assert b["currencyCode"] == "USD" and b["keepEmptyRows"] is False and b["limit"] == gu.UNI_PAGE_ROWS
        assert b["returnPropertyQuota"] is True
        ex = b["dimensionFilter"]["andGroup"]["expressions"]
        assert ex[:2] == [ga4._exact("platform", "Android"), ga4._exact("streamId", SID)]
    extra = lambda k: sent[k]["dimensionFilter"]["andGroup"]["expressions"][2:]
    assert all(extra(k) == [] for k in ("R1", "R2", "R3", "R4"))
    assert extra("R5") == [{"filter": {"fieldName": "countryId", "inListFilter": {"values": ["XA"]}}}]   # R3's top
    ymd = d.strftime("%Y%m%d")
    assert extra("R6") == [{"filter": {"fieldName": "firstSessionDate", "inListFilter": {"values": [ymd]}}}]
    assert extra("R7") == [{"filter": {"fieldName": "firstUserDefaultChannelGroup",
                                       "inListFilter": {"values": ["Cross-network", "Paid Search"]}}}]
    assert fp.request("R5", d, "XA")["extra"] == [gcu.cc_in(["XA"])] and fp.request("R1", d)["body"] == gcu.body(d, d)


# ── a whole run ─────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_consistent_run_ties_every_read_and_keeps_the_metadata(monkeypatch, capsys):
    rep = _run(monkeypatch, FakeGA(), max_calls=70)
    a = _app(rep)
    assert a["complete"] is False and a["stopped"] == "app_cap"                    # 13 days need more than 70 calls
    assert rep["rules"]["app_calls"] == 70 and rep["counts"]["calls"] == 70
    F1, C1 = ORDER[0][0], ORDER[1][0]
    day = a["days"][F1]
    assert day["type"] == "fl" and day["plan"] == list(fp.KINDS) and day["done"] and day["top"] == "XA"
    assert day["led"] == led(1) and day["na"] == {}
    T = total()
    r1 = day["reads"]["R1"]
    assert r1["ok"] and r1["whole"] and not (r1["loss"] or r1["sampled"] or r1["thresh"] or r1["cut"] or r1["hidden"])
    assert r1["rows"] == r1["row_count"] == AGES * len(CTRY) and r1["pages"] == 1 and r1["calls"] == 1
    assert r1["pg"] == [{"rc": AGES * len(CTRY), "n": AGES * len(CTRY),
                         "meta": {"currencyCode": "USD", "timeZone": "Etc/UTC"}}]
    assert r1["keys"] == ["currencyCode", "timeZone"] and r1["smp"] == [] and r1["empty"] == [] and r1["usd"] is True
    assert r1["sum"] == {"activeUsers": AGES * USERS * 7, "totalAdRevenue": T} and r1["other"]["rows"] == 0
    assert r1["cc_n"] == 3 and r1["x_n"] == AGES and r1["unset_rows"] == AGES and r1["odd"] == {"rows": 0, "rev": 0}
    assert r1["tok"] == 3 and r1["sec"] >= 0
    assert day["reads"]["R2"]["t_ok"] is True and day["reads"]["R2"]["rows"] == 1
    c = day["cmp"]
    assert c["t"] == T and c["t_ok"] and c["led"] == {"t": T_LED, "r": round(T_LED / T, 6), "d": T_LED - T}
    for k in ("R1", "R3", "R4"):
        assert c[k] == {"r": 1.0, "d": 0, "tie": True}
    assert c["R5"]["want"] == total(ctry=("XA",)) and c["R5"]["rw"] == 1.0 and c["R5"]["tie"]
    assert c["R6"]["want"] == total(ages=(0,)) and c["R6"]["rw"] == 1.0 and c["R6"]["tie"]
    assert c["R7"] == {"r": PSHARE, "d": total(PSHARE) - T}
    assert "R7" in a["days"][C1]["reads"] and a["days"][C1]["type"] == "ctl"
    assert all("R7" not in a["days"][D]["reads"] for D, _ in ORDER[3:] if D in a["days"])
    assert a["sum"]["fl"]["R1"]["whole"] == a["sum"]["fl"]["R1"]["n"] and a["sum"]["ctl"]["R1"]["tie"] >= 1
    assert a["tokens"] == 3 * 70 and set(a) >= {"key", "today", "window", "pick", "order", "r7", "days", "calls", "sec"}
    lines = fp.public_lines(rep["counts"])
    out = capsys.readouterr().out + "\n".join(lines)
    for s in PRIV + [D for D, _ in ORDER] + [str(T), str(T_LED), "XA"]:
        assert s not in out
    assert re.fullmatch(r"flag probe: apps 1, days \d+, carried 0, reads \d+, calls 70, \d+s, stopped app_cap 1",
                        lines[0])
    per = r" ".join(r"%s \d+" % f for f in fp.TALLY)
    assert all(re.fullmatch(r"flag probe: R\d fl %s \| ctl %s" % (per, per), ln) for ln in lines[1:]), lines
    assert len(lines) == 1 + len(fp.KINDS)


def test_metadata_is_kept_verbatim_and_named(monkeypatch):
    m = {"samplingMetadatas": [{"samplesReadCount": "250", "samplingSpaceSize": "1000"}], "subjectToThresholding": True,
         "emptyReason": "SYNTH_REASON", "schemaRestrictionResponse": {"activeMetricRestrictions": []}}
    a = _app(_run(monkeypatch, FakeGA(meta={"R1": m}, fold=("R1",)), max_calls=7))
    day = a["days"][ORDER[0][0]]
    r1 = day["reads"]["R1"]
    assert r1["pg"][0]["meta"] == dict(m, currencyCode="USD", timeZone="Etc/UTC", dataLossFromOtherRow=True)
    assert r1["keys"] == sorted(r1["pg"][0]["meta"]) and r1["smp"] == [[250, 1000]] and r1["smp_frac"] == 0.25
    assert r1["sampled"] and r1["thresh"] and r1["loss"] and r1["empty"] == ["SYNTH_REASON"]
    xc = total(ctry=(FOLD,))
    assert r1["other"] == {"rows": 1, "rev": xc, "users": AGES * USERS} and not r1["hidden"] and not r1["whole"]
    assert day["cmp"]["R1"]["tie"] is True                  # the "(other)" row still holds its revenue
    assert all(day["reads"][k]["whole"] for k in ("R2", "R3", "R4", "R5", "R6", "R7"))
    assert a["sum"]["fl"]["R1"] == dict.fromkeys(fp.TALLY, 0) | {"n": 1, "ok": 1, "loss": 1, "sampled": 1, "thresh": 1,
                                                                 "other": 1, "empty": 1, "tie": 1}


def test_a_hidden_other_a_cut_answer_and_pages(monkeypatch):
    a = _app(_run(monkeypatch, FakeGA(hide=("R1",), cut=("R4",)), max_calls=7))
    day = a["days"][ORDER[0][0]]
    r1, r4 = day["reads"]["R1"], day["reads"]["R4"]
    assert r1["loss"] and r1["hidden"] and r1["other"]["rows"] == 0 and not r1["whole"]
    assert day["cmp"]["R1"]["tie"] is False and day["cmp"]["R1"]["d"] == -total(ctry=(FOLD,))
    assert r4["cut"] and not r4["whole"] and r4["row_count"] == r4["rows"] + 3 and "tie" in day["cmp"]["R4"]
    monkeypatch.setattr(fp, "PAGE_ROWS", 50)
    fake = FakeGA()
    a = _app(_run(monkeypatch, fake, max_calls=10))
    r1 = a["days"][ORDER[0][0]]["reads"]["R1"]
    n = AGES * len(CTRY)
    assert r1["pages"] == r1["calls"] == 4 and [p["n"] for p in r1["pg"]] == [50, 50, 50, n - 150]
    assert all(p["rc"] == n for p in r1["pg"]) and r1["rows"] == n and not r1["cut"] and r1["whole"]
    assert a["days"][ORDER[0][0]]["cmp"]["R1"]["tie"] and len(fake.bodies) == 10
    assert [b["offset"] for b in fake.bodies[:4]] == [0, 50, 100, 150]


def test_a_refused_country_read_leaves_r5_unasked_and_the_detail_off(monkeypatch):
    rep = _run(monkeypatch, FakeGA(refuse=("R3",)), max_calls=6)
    day = _app(rep)["days"][ORDER[0][0]]
    assert day["reads"]["R3"] == dict(day["reads"]["R3"], ok=False, err={"http": 400, "status": "INVALID_ARGUMENT"})
    assert day["na"] == {"R5": "no_top"} and "R5" not in day["reads"] and "R5" not in day["cmp"]
    assert day["done"] and "DETAIL" not in json.dumps(rep) and set(day["reads"]) == {"R1", "R2", "R3", "R4", "R6", "R7"}
    assert rep["counts"]["kinds"]["R3"]["fl"]["refused"] == 1


def test_a_bug_mid_day_keeps_the_reads_made(monkeypatch):
    real = fp.request

    def broken(kind, d, top=None):
        if kind == "R4":
            raise KeyError("PRIVATE-detail")
        return real(kind, d, top)
    monkeypatch.setattr(fp, "request", broken)
    rep = _run(monkeypatch, FakeGA(), max_calls=70)
    a = _app(rep)
    day = a["days"][ORDER[0][0]]
    assert a["crash"] == "KeyError" and not a["complete"] and "PRIVATE-detail" not in json.dumps(rep)
    assert list(day["reads"]) == ["R1", "R2", "R3"] and not day["done"] and day["cmp"]["R3"]["tie"]
    assert rep["counts"]["reads"] == 3


# ── the call caps and the quota ─────────────────────────────────────────────────────────────────────────────────────

def test_the_call_caps_stop_cleanly_with_what_was_read(monkeypatch):
    fake = FakeGA()
    a = _app(_run(monkeypatch, fake, max_calls=9))
    assert a["stopped"] == "app_cap" and len(fake.bodies) == 9 and not a["complete"]
    F1, C1 = ORDER[0][0], ORDER[1][0]
    assert a["days"][F1]["done"] and list(a["days"][C1]["reads"]) == ["R1", "R2"] and not a["days"][C1]["done"]
    assert a["days"][C1]["cmp"]["R1"]["tie"] and set(a["days"]) == {F1, C1}
    fake = FakeGA()                                           # the run's cap, the app's set higher
    a = _app(_run(monkeypatch, fake, max_calls=9, app_calls=50))
    assert a["stopped"] == "calls" and len(fake.bodies) == 9
    fake = FakeGA()                                           # never more than 70 calls, whatever is asked
    rep = _run(monkeypatch, fake, max_calls=500, app_calls=500)
    assert rep["rules"]["max_calls"] == 70 and len(fake.bodies) == 70 and _app(rep)["stopped"] == "calls"
    fake = FakeGA()                                           # two apps share the calls
    u2 = planned(unit_of(AID2, PID2, SID2))
    rep = _run(monkeypatch, fake, units=[planned(), u2], max_calls=12)
    assert rep["rules"]["app_calls"] == 6 and len(fake.bodies) == 12
    assert {k: v["stopped"] for k, v in rep["apps"].items()} == {KEY: "app_cap", u2["key"]: "app_cap"}


def test_the_quota_floors_stop_the_property(monkeypatch):
    low = FakeGA(quota={"tokensPerDay": {"consumed": 3, "remaining": 1}})
    u2 = planned(unit_of(AID2, PID, SID2))                    # the same property: it stops for both apps
    rep = _run(monkeypatch, low, units=[planned(), u2], max_calls=70)
    assert len(low.bodies) == 1 and {v["stopped"] for v in rep["apps"].values()} == {"quota_low"}
    assert _app(rep)["days"][ORDER[0][0]]["reads"]["R1"]["ok"] and rep["apps"][u2["key"]]["days"] == {}
    # the build's own floors (ga4_audience.quota_stop) stop it too, even where the other probes' gate would not
    monkeypatch.setattr(pr, "QUOTA_FRAC", 0.0)
    hour = FakeGA(quota={"tokensPerHour": {"consumed": 30000, "remaining": 10000}})
    a = _app(_run(monkeypatch, hour, max_calls=70))
    assert a["stopped"] == "hour_low" and len(hour.bodies) == 1
    for q in ({"potentiallyThresholdedRequestsPerHour": {"consumed": 115, "remaining": 5}},
              {"serverErrorsPerProjectPerHour": {"consumed": 6, "remaining": 4}}):
        f = FakeGA(quota=q)
        assert _app(_run(monkeypatch, f, max_calls=70))["stopped"] in ("quota_low", "count_low") and len(f.bodies) == 1


# ── resume ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_resume_carries_the_days_read_whole_and_reads_on(monkeypatch, tmp_path):
    first = _run(monkeypatch, FakeGA(), max_calls=9)
    F1, C1, F2 = (D for D, _ in ORDER[:3])
    last = {KEY: _app(first)}
    fake = FakeGA()
    rep = _run(monkeypatch, fake, last=last, max_calls=9, resume=True)
    a = _app(rep)
    assert a["days"][F1] == dict(_app(first)["days"][F1], carried=True)
    assert len(fake.bodies) == 9 and all(b["dateRanges"][0]["startDate"] != F1 for b in fake.bodies)
    assert a["days"][C1]["done"] and not a["days"][C1].get("carried") and list(a["days"][F2]["reads"]) == ["R1", "R2"]
    assert rep["counts"]["carried"] == 1 and rep["rules"]["resume"] is True
    fake = FakeGA()                                            # resume off: read again from the first day
    _run(monkeypatch, fake, last=last, max_calls=9)
    assert fake.bodies[0]["dateRanges"][0]["startDate"] == F1
    # a day of another kind, or one not read whole, is read again
    other = {KEY: dict(last[KEY], days={F1: dict(last[KEY]["days"][F1], type="ctl")})}
    fake = FakeGA()
    _run(monkeypatch, fake, last=other, max_calls=7, resume=True)
    assert fake.bodies[0]["dateRanges"][0]["startDate"] == F1
    # the last report on disk: kept only under the same rules
    os.makedirs(tmp_path / "ga4")
    with open(tmp_path / fp.OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(first, f)
    assert fp.load_last(str(tmp_path), fp.rules(5)) == {KEY: _app(first)}
    assert fp.load_last(str(tmp_path), dict(fp.rules(70), window=99)) == {}
    assert fp.load_last(str(tmp_path / "none"), fp.rules(70)) == {}


# ── main: the clone, the inputs, the private result ─────────────────────────────────────────────────────────────────

def _main(monkeypatch, tmp_path, fake, inputs=None):
    write_clone(tmp_path / "_private")
    _patch(monkeypatch, fake)
    wrote = {}
    monkeypatch.setattr(fp.pr, "write_private", lambda path, raw, msg: wrote.update(path=path, raw=raw) or True)
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKENS": json.dumps({"o": RT}),
           "FLAG_DATA_DIR": str(tmp_path / "_private")}
    if inputs is not None:
        ev = tmp_path / "event.json"
        ev.write_text(json.dumps({"inputs": inputs}))
        env["GITHUB_EVENT_PATH"] = str(ev)
    fp.main(env=env, now=NOW)
    return json.loads(wrote["raw"]), wrote["path"]


def test_main_writes_the_private_result_in_its_shape(monkeypatch, tmp_path, capsys):
    fake = FakeGA()
    rep, path = _main(monkeypatch, tmp_path, fake)
    assert path == "ga4/flag_probe.json" == fp.OUT_PATH and len(fake.bodies) == 70
    assert set(rep) == {"v", "probe", "at", "rules", "counts", "apps"} and rep["v"] == 1 and rep["probe"] == "ga4_flag"
    assert rep["rules"] == {"v": 1, "window": 150, "final_lag": gcu.FINAL_LAG, "n_apps": 2, "n_fl": 10, "gap": 14,
                            "n_ctl": 3, "ctl_at": [0, 2, 4], "r7_days": 3, "kinds": list(fp.KINDS), "max_calls": 70,
                            "page_rows": gu.UNI_PAGE_ROWS, "quota_frac": pr.QUOTA_FRAC, "app_calls": 35,
                            "resume": False}
    assert set(rep["apps"]) == set(KEYS[:2])
    a = rep["apps"][KEY]
    assert set(a) == {"key", "today", "window", "pick", "order", "r7", "days", "stopped", "complete", "sum", "calls",
                      "tokens", "sec"}
    assert a["key"] == KEY and a["today"] == TODAY.isoformat() and a["window"] == [a["window"][0], HI.isoformat()]
    assert a["order"] == [D for D, _ in ORDER] and a["stopped"] == "app_cap" and len(a["days"]) == 6
    day = a["days"][ORDER[0][0]]
    assert set(day) == {"type", "led", "plan", "reads", "na", "at", "cmp", "done", "top"}
    assert set(day["reads"]) == set(fp.KINDS) and day["at"] == "2026-10-15T06:00:00Z"
    r = day["reads"]["R1"]
    assert set(r) == {"ok", "rows", "row_count", "pages", "cut", "pg", "smp", "empty", "keys", "sum", "other",
                      "unset_rows", "odd", "hidden", "whole", "cc_n", "x_n", "thresh", "loss", "sampled", "smp_frac",
                      "usd", "tok", "tok_delta", "sec", "calls"}
    assert set(day["reads"]["R2"]) - set(r) == {"t_ok"} and "cc_n" in day["reads"]["R3"] and "x_n" in day["reads"]["R4"]
    assert set(day["cmp"]) == {"t", "t_ok", "led", "R1", "R3", "R4", "R5", "R6", "R7"}
    out = capsys.readouterr().out
    assert "flag probe: 2 app(s) chosen of 3 with a cube store, 26 day(s) planned" in out and "report written" in out
    for s in PRIV + [D for D, _ in ORDER] + ["pkg.synth", "XA", str(total())]:
        assert s not in out
    for ln in out.strip().splitlines():
        assert re.fullmatch(r"flag (probe|progress): [a-zA-Z0-9 ,()/_|<>.]+", ln), ln


def test_main_inputs_lower_the_cap_and_resume(monkeypatch, tmp_path):
    fake = FakeGA()
    rep, _ = _main(monkeypatch, tmp_path, fake, inputs={"max_calls": "12", "resume": "true"})
    assert len(fake.bodies) == 12 and rep["rules"]["max_calls"] == 12 and rep["rules"]["resume"] is True
    fake = FakeGA()
    rep, _ = _main(monkeypatch, tmp_path / "b", fake, inputs={"max_calls": "900"})
    assert len(fake.bodies) == 70 and rep["rules"]["max_calls"] == 70


def test_main_without_the_private_clone_or_flags_makes_no_ga4_call(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(ga4, "_call", lambda *a, **k: calls.append(1))
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GA4_REFRESH_TOKEN": RT,
           "FLAG_DATA_DIR": str(tmp_path / "none")}
    for root, why in ((tmp_path / "none", "no private clone"), (tmp_path / "clean", "no cube store with a flagged")):
        if root.name == "clean":
            data = write_clone(root)
            for aid, sid in ((AID, SID), (AID2, SID2), (AID3, SID3)):
                for k in os.listdir(gcu.app_dir(data, aid)):
                    os.remove(os.path.join(gcu.app_dir(data, aid), k))
                write_store(data, aid, [], CLEAN, stream=sid)
            env["FLAG_DATA_DIR"] = str(root)
        try:
            fp.main(env=env, now=NOW)
            assert False, "should exit"
        except SystemExit as e:
            assert why in str(e)
    assert calls == []


def test_counts_and_the_public_lines_name_nothing():
    run = type("R", (), {"calls": 9, "elapsed": lambda self: 3})()
    ok = {"ok": True, "whole": True}
    apps = {"k1": {"stopped": "app_cap", "days": {
        "d1": {"type": "fl", "reads": {"R1": {"ok": True, "loss": True, "hidden": True}, "R2": ok,
                                       "R3": {"ok": False, "err": {"http": 400}}},
               "cmp": {"R1": {"tie": False}}},
        "d2": {"type": "ctl", "carried": True, "reads": {"R1": ok}, "cmp": {"R1": {"tie": True}}}}},
        "k2": {"crash": "ValueError"}}
    c = fp.counts(apps, run)
    assert (c["apps"], c["days"], c["carried"], c["reads"], c["calls"], c["seconds"]) == (2, 2, 1, 4, 9, 3)
    assert c["stopped"] == {"app_cap": 1} and c["kinds"]["R3"]["fl"]["refused"] == 1
    assert c["kinds"]["R1"]["fl"] == dict.fromkeys(fp.TALLY, 0) | {"n": 1, "ok": 1, "loss": 1, "hidden": 1}
    assert c["kinds"]["R1"]["ctl"] == dict.fromkeys(fp.TALLY, 0) | {"n": 1, "ok": 1, "whole": 1, "tie": 1}
    lines = fp.public_lines(c)
    assert lines[0] == "flag probe: apps 2, days 2, carried 1, reads 4, calls 9, 3s, stopped app_cap 1"
    assert lines[1].startswith("flag probe: R1 fl n 1 ok 1 refused 0 failed 0 whole 0 loss 1 ") and len(lines) == 4
    assert fp.public_lines({})[0] == "flag probe: apps 0, days 0, carried 0, reads 0, calls 0, 0s, stopped none"


# ── the workflow file ───────────────────────────────────────────────────────────────────────────────────────────────

def test_the_workflow_file_parses_runs_on_dispatch_only_and_keeps_the_inputs_off_the_log():
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wfs = os.path.join(root, ".github", "workflows")
    with open(os.path.join(wfs, "ga4-flag-probe.yml"), encoding="utf-8") as fh:
        raw = fh.read()
    wf = yaml.safe_load(raw)                                              # (a ": " in a step's name broke one once)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and "schedule" not in raw and "cron" not in raw
    assert set(on["workflow_dispatch"]["inputs"]) == {"max_calls", "resume"}
    assert wf["permissions"] == {"contents": "read"} and "github.event.inputs" not in raw and "inputs." not in raw
    assert wf["concurrency"] == {"group": "ga4-flag-probe", "cancel-in-progress": False}
    job = wf["jobs"]["probe"]
    assert job["timeout-minutes"] == 45 and job["runs-on"] == "ubuntu-latest"
    steps = job["steps"]
    assert all(": " not in st.get("name", "") for st in steps)
    assert steps[0]["with"]["persist-credentials"] is False and steps[1]["with"]["python-version"] == "3.11"
    (clone,) = [st for st in steps if "clone" in (st.get("run") or "")]
    assert "> /dev/null 2>&1" in clone["run"] and "::add-mask::" in clone["run"] and "timeout 480 git " in clone["run"]
    (runs,) = [st for st in steps if "ga4_flag_probe" in (st.get("run") or "")]
    assert runs["run"].startswith("python -m admob_iq.fetch.ga4_flag_probe 2>/tmp/")
    assert runs["env"]["FLAG_DATA_DIR"] == "_private"
    for st in steps:                                                      # the inputs reach neither env nor script
        e = json.dumps(st.get("env") or {})
        assert "max_calls" not in e and "resume" not in e and "inputs" not in (st.get("run") or "")
    # the env / secrets blocks are the paid probe's (the template), word for word
    with open(os.path.join(wfs, "ga4-paid-probe.yml"), encoding="utf-8") as fh:
        tpl = yaml.safe_load(fh)["jobs"]["probe"]["steps"]
    (tclone,) = [st for st in tpl if "clone" in (st.get("run") or "")]
    (trun,) = [st for st in tpl if "ga4_paid_probe" in (st.get("run") or "")]
    assert clone["env"] == tclone["env"]
    assert {k: v for k, v in runs["env"].items() if k != "FLAG_DATA_DIR"} == \
        {k: v for k, v in trun["env"].items() if k != "PAID_DATA_DIR"}
    need = {"DATA_REPO", "DATA_REPO_TOKEN", "GA4_REFRESH_TOKENS", "GA4_CLIENT_ID", "GA4_CLIENT_SECRET"}
    assert need <= set(runs["env"])
