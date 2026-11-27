"""⚖️ ROI — the Google Ads users' pass (admob_iq.roi_build: start(cubep=True) — GA4_CUBEP and BE_PAID; owner, 16 Nov
2026: "haan sirf google ads wale users se karo · google ads and organic dono ka alag alag dekh saku esa kar do"), on
the made-up country world of tests/test_roi_build.py plus a made-up paid cube (fetch.ga4_cube_paid.MOD's own folder and
the cube's formats; every cell of it ≤ the all-users cube's): the country rows' refactor into one helper changed no
byte (digests of the outputs the build made before the pass existed); with the switch off or on, with or without a
paid cube, every all-users output byte for byte the same (the roi file, the country packs, the board files, the
pointer, roi.json.gz, data/ untouched); the paid All rows from the paid cube's cells only — never the install-day
file's every-user numbers (xs empty) — on the app's weekly k and its own Google Ads spend, every install day; the paid
country rows on the ALL-USERS k_c and Google Ads cost (also on days the paid cube read past the all-users one), each
cell ≤ the all-users one; the paid cube's OWN completeness (a day it has not folded is not final in a paid row while
the all-users one is); the paid file's own unknown-spend days and currency ("unk" / "billed": every short [X] row of
its packs expands from it alone); "busy" (its walk not through: the progress) / "none" (no paid cube of the stream) /
"fail" (a raising pass — or its Ads split past the all-users thru, or the all-users walk / 🌍 part it rides on: only
it lost, never in silence — its files gone, its health line); the scratch folder never under out_dir / data_dir (made
by start, removed by the next start / off / the exit); the counts-only ROI line; the switch, the stage name, the
workflow variable and uninstall_build's wiring (BE_TAB off: no pass; GA4_COHORTP handed on). With GA4_COHORTP
(start(cohortp=True)): the paid All rows from the Google Ads users' own D0 … D30 store (fetch.ga4_cohort_paid's
folder, ga4_cohort's format) worked by hand — never the paid cube's cells summed —, from the day its backfill began
(none it never read), with the packs, every other field of the paid file and every all-users output as without it;
the file's "all" ("cohort" | "cube") and "newest" (that read's read_today, as every user's file has ga4_cohort's:
be_build's final-cell gates on it; the paid cube's newest day — the Organic ages — in "cnew"); "busy" until that
store's backfill is done and a refresh read the recent days (its
progress), the paid cube's own busy / none first; be_build's pack gaps on the paid file it makes (pack_gaps on
"cohort", pack_gaps_p on "cube"). SYNTHETIC values only (the runner repo is public)."""
import copy
import gzip
import hashlib
import json
import os
from datetime import date, timedelta

import pytest

from admob_iq import be_build as beb
from admob_iq import roi_build as rb
from admob_iq.fetch import ga4_cohort_paid as cop
from admob_iq.fetch import ga4_cube_paid as cp
from tests.test_roi_build import (CHS, CINST, CRATE, CTODAY, T, _cc_app_step, _cc_cube, _cc_run, _cc_users, _cc_world,
                                  _expand, _pack_rows, _stub_app)
from tests.test_roi_speed import WORLDS

KEY = "aaaaaaaaaaaa"
PINST = {"AA": 10, "BB": 1, "CC": 1, "--": 1}           # the Google Ads users' installs a day (made up; ≤ CINST)
PRATE = {"AA": 25000, "BB": 1000, "CC": 5000, "--": 2000}   # … their GA4 micros a day per install day (≤ CRATE)
DAYS = [(CHS + timedelta(days=i)).isoformat() for i in range((CTODAY - CHS).days + 1)]
J30 = T.index(30)


def _tree(root):
    out = {}
    for base, _dirs, names in os.walk(str(root)):
        for n in names:
            p = os.path.join(base, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, str(root))] = f.read()
    return out


def _run(tmp_path, monkeypatch, name, cubep=True, paid=None, head=None, prep=None, cohortp=False, **kw):
    """app_step + finish on the country world (**kw: _cc_world's) + the paid cube when `paid` is a dict (_cc_cube's
    arguments over PINST / PRATE; head: fields set on its head after; prep(data): a test's own change to the stores,
    after; cohortp: GA4_COHORTP — the pass's All row from the Google Ads users' D0 … D30 store) → the roi file's JSON
    bytes, every out_dir file, the pointer, the header rules, the ROI line, PAID, the scratch files (name → JSON bytes),
    the folder, acc. Asserts the build wrote nothing under data_dir."""
    data, P, pre, spend, acc0 = _cc_world(tmp_path / name, **kw)
    if paid is not None:
        _cc_cube(data, **dict({"cube_mod": cp.MOD, "inst": PINST, "rate": PRATE}, **paid))
        if head:
            h = cp.MOD.load_head(str(data), "a~1")
            cp.MOD.write_json_gz_stable(cp.MOD.hot_path(str(data), "a~1"), dict(h, **head))
    if prep is not None:
        prep(data)
    _stub_app(monkeypatch, P, {"read_today": CTODAY.isoformat(), "stream_id": "222", "x": {}}, spend)
    out = tmp_path / name / "out"
    out.mkdir()
    before = _tree(data)
    acc = rb.start(cube=True, cmon=acc0.cmon, cubep=cubep, cohortp=cohortp)
    store, a = {"history_start": CHS.isoformat(), "stream_id": "222"}, {"app_id": "a~1", "app_name": "Alpha"}
    rb.app_step(acc, store, a, KEY, {"tz": "UTC"}, pre, {}, str(out), str(data), ids=["a~1"])
    assert not acc.fails and len(acc.apps) == 1
    dash = {}
    hdr = rb.finish(acc, dash, str(out))
    assert _tree(data) == before                                    # nothing of the pass under data_dir
    scratch = {}
    if rb.PAID_DIR:
        for n in sorted(os.listdir(rb.PAID_DIR)):
            with open(os.path.join(rb.PAID_DIR, n), "rb") as f:
                scratch[n] = gzip.decompress(f.read())
    with open(os.path.join(str(out), "roi_%s.json.gz" % KEY), "rb") as f:
        body = gzip.decompress(f.read())
    return {"body": body, "out": _tree(out), "dash": dash, "hdr": hdr, "line": rb.pop_line(),
            "paid": copy.deepcopy(rb.PAID), "scratch": scratch, "dir": rb.PAID_DIR, "acc": acc, "data": data,
            "od": out}


def _paid(r):
    """The paid file and its packs' rows {cc: rows} (each pack checked: its sha1-12, number, key, build)."""
    body = json.loads(r["scratch"]["roi_%s_p.json.gz" % KEY])
    rows = {}
    for i, (name, sha) in enumerate(body["packs"]):
        raw = r["scratch"][name]
        pk = json.loads(raw)
        assert name == "roi_%s_p%02d.json.gz" % (KEY, i) and hashlib.sha1(raw).hexdigest()[:12] == sha
        assert (pk["v"], pk["key"], pk["ix"], pk["b"]) == (1, KEY, i, body["b"])
        assert set(pk) == {"v", "b", "key", "ix", "c"}                  # the country packs' format
        assert raw == json.dumps(pk, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
        for cc, rs in pk["c"].items():
            assert cc not in rows                                    # every country in exactly one pack
            rows[cc] = rs
    assert set(r["scratch"]) == {"roi_%s_p.json.gz" % KEY} | {n for n, _ in body["packs"]}
    return body, rows


def _pexpand(body, rows, cc):
    """A paid pack's rows, each short [X] expanded from the PAID FILE alone (the format contract: _zrow on its "thru",
    "fthru", "unk" and "billed" — never the all-users file's)."""
    return _expand(rows, {"thru": body["thru"], "fthru": body["fthru"],
                          "geo": {"unk": body["unk"], "billed": body["billed"]}}, cc)


# ── the refactor: every all-users country output as the build made it before the pass existed ─────────────────────
# sha256 of each world's outputs (_cty's "cd" JSON + every file it wrote, decompressed; app_step: the roi file + its
# files) — worked out once with the build BEFORE the paid pass existed (its country rows inline in _cty), on the made-up
# worlds of tests/test_roi_speed.py (two pack sizes), with the country users' files, and through app_step
BEFORE = {
    "app_step": "4a07a370a6c7c4fb6ff0e3befdf6a9aa0bc85c5b24f4602677bf1323c9a62f5c",
    "gaps/1500000": "a3dec213becc57af47343f6b2bbcc902f50ab33d908aade45535677bb223f322",
    "gaps/20000": "a825c43ff996fd6592327028b924a6cfd4f4eb43118b0ebce89c230c37d174eb",
    "hole/1500000": "68cb648d903121268e9ecc76ee160e76e2bc9406545167190b857ddd2cd6f723",
    "hole/20000": "cde955faa649400ef15a7af06d43b90d9c4f06e5118143eab20920afc9fabfc8",
    "loss/1500000": "cd2c436868ee8dceed24cc40efd63bc259dcd42e91530615ca20e7fd630c8435",
    "loss/20000": "88747e334ae6aaefc6877d9bdff3ccf661b3c3dc12c00b55bfc6035d0fa9a442",
    "months/1500000": "265e6e3aadd76d0d27cc9dcfc70b070b72e490da708d03e45835d631531c6dc5",
    "months/20000": "aceec22c1d819c7eedab7abe7ebc0e16f118b39e8c2746dd4291c3475f5b459a",
    "plain/1500000": "c659527d51431045f7825abe543f2c754a96e2f4a8f3c6d2db5b112c59791457",
    "plain/20000": "164759a343af3d9a01d663980ba6679f12d6e0e1cda4d152aef975d354afa02c",
    "users": "d7625abcd311c4742c90846ec51bfaefb3308a4fd6ca8c743e2d5b37b33422a6",
    "zero_rows/1500000": "e5c7d686e69c855f4b2222aa184ecc2f01cc3a5af8ac1e7a37787e86822d065f",
    "zero_rows/20000": "ba18b35b945003e97cc0aa47be74afb995af0991e76c6e34c31e37a64589b393",
}


def _nomix(raw):
    """A roi file without its 📊 "mix" (revenue by install month, added after these digests were taken; nothing of the
    pass reads or writes it) — every other byte as written."""
    body = json.loads(raw)
    if body.pop("mix", None) is None:
        return raw
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _digest(top, od):
    files = {}
    for n in sorted(os.listdir(str(od))):
        with open(os.path.join(str(od), n), "rb") as f:
            raw = gzip.decompress(f.read())
            files[n] = hashlib.sha256(_nomix(raw) if rb.FILE_RE.match(n) else raw).hexdigest()
    return hashlib.sha256(json.dumps({"top": top, "files": files}, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("world", sorted(BEFORE))
def test_country_outputs_byte_identical_to_the_build_before_the_pass(tmp_path, monkeypatch, world):
    if world == "app_step":
        full, _, out = _cc_app_step(tmp_path, monkeypatch, "on")
        assert "mix" in json.loads(full)
        assert _digest(hashlib.sha256(_nomix(full)).hexdigest(), out) == BEFORE[world]
        return
    if world == "users":
        kw = dict(inst=dict(CINST, EE=3), rate=dict(CRATE, EE=50000), only={"EE": {date(2026, 9, 5), date(2026, 9, 6)}})
        data, P, pre, spend, acc = _cc_world(tmp_path, **kw)
        _cc_users(data, skip={date(2026, 9, 10)}, ou={date(2026, 9, 20): 7}, fl={date(2026, 9, 25)},
                  hot_at={CTODAY: "2026-10-12T00:00:00Z"}, extra={("FF", date(2026, 9, 1), 5): 3})
        acc = rb.start(cube=True, cmon=acc.cmon)
        out = "o1"
    else:
        w, pm = world.split("/")
        monkeypatch.setattr(rb, "PACK_MAX", int(pm))
        data, P, pre, spend, acc = _cc_world(tmp_path / "w", **WORLDS[w])
        out = "o"
    cd, od, _ = _cc_run(tmp_path, data, P, pre, spend, acc, out=out)
    assert _digest(hashlib.sha256(json.dumps(cd, sort_keys=True).encode()).hexdigest(), od) == BEFORE[world]


# ── the switch: every all-users output byte for byte ────────────────────────────────────────────────────────────────
def test_switch_off_or_on_every_all_users_output_byte_for_byte(tmp_path, monkeypatch):
    off = _run(tmp_path, monkeypatch, "off", cubep=False, paid={})         # a paid cube on disk, the switch off
    on = _run(tmp_path, monkeypatch, "on", paid={})
    bare = _run(tmp_path, monkeypatch, "bare")                             # the switch on, no paid cube on disk
    assert off["paid"] == {} and off["dir"] is None and off["scratch"] == {} and not off["acc"].cubep
    assert on["paid"] == {KEY: {"st": "ok", "file": "roi_%s_p.json.gz" % KEY}} and bare["paid"] == {KEY: {"st": "none"}}
    for r in (on, bare):
        assert r["body"] == off["body"] and r["out"] == off["out"]          # the roi file, packs, board files, roi.json
        assert r["dash"] == off["dash"] and r["hdr"] == off["hdr"] == ["/roi*"]
    assert ", paid" not in off["line"] and "ads split unread 0" in off["line"]
    tail = "ads split unread 0"
    assert on["line"] == off["line"].replace(tail, tail + ", paid ok 1 busy 0 none 0 fail 0")
    assert bare["line"] == off["line"].replace(tail, tail + ", paid ok 0 busy 0 none 1 fail 0")
    assert "Alpha" not in on["line"] and KEY not in on["line"]             # counts only
    assert sorted(on["scratch"]) == ["roi_%s_p.json.gz" % KEY, "roi_%s_p00.json.gz" % KEY] and bare["scratch"] == {}
    assert not any("_p" in n for n in on["out"])                           # never the site's


# ── the paid rows ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_paid_rows_come_from_the_paid_cube_only(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, "on", paid={})
    body, prow = _paid(r)
    allf = json.loads(r["body"])
    cd = allf["cd"]
    assert set(body) == {"v", "key", "b", "rows", "packs", "thru", "fthru", "newest", "loss", "unk", "billed", "all"}
    assert (body["v"], body["key"], body["thru"], body["fthru"], body["newest"]) == (1, KEY, "2026-10-13", "2026-10-10",
                                                                                    "2026-10-13")
    assert body["all"] == "cube"                                    # (GA4_COHORTP off: the paid cube's cells summed)
    assert body["loss"] == {"days": 0, "share": 0.0}
    # its own unknown-spend days: here the all-users file's (both cubes read through the same day)
    assert body["unk"] == cd["geo"]["unk"] == [["2026-08-01", "2026-08-31"], ["2026-09-15", "2026-09-15"],
                                               ["2026-10-13", "2026-10-13"]] and body["billed"] is True
    # the All row: every install day (a day with no Google Ads user would be a real 0), the paid cube's cells summed
    # over every country × the app's weekly k (1.2) — never the install-day file's (xs: 100 installs a day, D30 = $62)
    assert [x[0] for x in body["rows"]] == DAYS and {len(x) for x in body["rows"]} <= {14, 16}
    a_all = {x[0]: x for x in allf["rows"]}
    cum, d = 0.0, []
    for _ in range(31):
        cum += sum(PRATE.values()) / 1e6 * 1.2
        d.append(round(cum, 4))
    x = {x[0]: x for x in body["rows"]}["2026-08-05"]
    assert x[1] == sum(PINST.values()) and a_all["2026-08-05"][1] == 100            # n: the paid cells' installs
    assert x[4] == d and x[5] == 31 and x[6] is None                                # day by day, final; no users read
    assert x[7][J30] == d[30] and a_all["2026-08-05"][7][J30] == 62.0              # D30 from the cells, not xs
    b1 = 30 * sum(PRATE.values()) / 1e6 * 1.2                                       # D60: bucket 1, folded (Oct 4)
    assert x[14] == [pytest.approx(d[30] + b1, abs=1e-4)] and x[15] == 1 and x[7][T.index(60)] == x[14][0]
    assert (x[8], x[9]) == (x[14][0], "2026-10-04")                                 # so far: the furthest of its own
    assert x[2:4] == a_all["2026-08-05"][2:4] and x[13] == a_all["2026-08-05"][13]  # the app's own spend / Ads installs
    assert x[10] is None and x[11] == "N/A" and x[12] == 0                         # under 30 installs: N/A
    young = {x[0]: x for x in body["rows"]}["2026-10-12"]                           # read through Oct 13, none final
    assert young[4] == d[:2] and young[5] == 0 and young[7] == [None] * len(T)
    # the countries: the 🌍 rows' own code on the ALL-USERS k_c and Google Ads cost; every cell ≤ the all-users one
    arow = _pack_rows(r["od"], cd)
    assert set(prow) == set(arow) == {"AA", "BB", "CC", "--", "DD", "XX"}
    for cc in ("AA", "BB", "CC", "--"):
        P_ = {x[0]: x for x in _pexpand(body, prow[cc], cc)}
        A_ = {x[0]: x for x in _expand(arow[cc], cd, cc)}
        assert sorted(P_) == sorted(A_) == DAYS
        for X, p in P_.items():
            a = A_[X]
            assert p[1] == PINST[cc] <= a[1] == CINST[cc], (cc, X)                 # installs: the paid cube's
            assert p[2:4] == a[2:4] and p[13] == a[13] and p[5] == a[5], (cc, X)   # the same cost; finality here
            assert p[12] == a[12], (cc, X)                                         # … the same k_c ≈ bits
            share = PRATE[cc] / CRATE[cc]                                           # the same k_c: the paid share
            for vp, va in zip(p[4] or [], a[4] or []):                             # of every cell
                assert vp <= va + 1e-9 and vp == pytest.approx(va * share, abs=1e-4), (cc, X)
            assert len(p) == len(a) and (len(p) < 16 or (p[15] == a[15] and all(
                vp == pytest.approx(va * share, abs=2e-4) for vp, va in zip(p[14], a[14]))))
    assert prow["DD"] == arow["DD"] and prow["XX"] == arow["XX"]                    # Ads only: the same rows


def test_paid_completeness_is_the_paid_cubes_own(tmp_path, monkeypatch):
    # the paid cube has not folded Sep 29 … Oct 13 yet (read, not final) while the all-users cube folded through Oct 10
    r = _run(tmp_path, monkeypatch, "late", paid={"hot_from": date(2026, 9, 29)})
    body, prow = _paid(r)
    cd = json.loads(r["body"])["cd"]
    assert (cd["fthru"], body["fthru"], body["thru"]) == ("2026-10-10", "2026-09-28", cd["thru"])
    pa = {x[0]: x for x in body["rows"]}
    assert pa["2026-09-20"][5] == 9 and pa["2026-09-20"][7][T.index(14)] is None    # Sep 20 … 28 final only
    assert pa["2026-08-05"][15] == 0 and pa["2026-08-05"][7][T.index(60)] is None   # its D60 (Oct 4) not folded
    AA = {x[0]: x for x in prow["AA"]}["2026-09-20"]
    AA_all = {x[0]: x for x in _pack_rows(r["od"], cd)["AA"]}["2026-09-20"]
    assert (AA[5], AA_all[5]) == (9, 21) and AA[7][T.index(14)] is None and AA_all[7][T.index(14)] is not None
    # the paid cube read further than the all-users one (it misses Oct 1): the paid rows go on to Oct 13, with the
    # same Google Ads split on the days the spend cache knows (to Oct 12); later: unknown (null), never 0
    r2 = _run(tmp_path, monkeypatch, "ahead", paid={}, holes={date(2026, 10, 1)})
    b2, p2 = _paid(r2)
    cd2 = json.loads(r2["body"])["cd"]
    assert cd2["thru"] == "2026-09-30" and b2["thru"] == "2026-10-13" and b2["rows"][-1][0] == "2026-10-13"
    AA2 = {x[0]: x for x in p2["AA"]}
    assert AA2["2026-10-05"][3] == 6.0 and AA2["2026-10-05"][2] == 3.0 and AA2["2026-10-13"][3] is None
    XX2 = {x[0]: x for x in p2["XX"]}
    assert XX2["2026-10-05"][3] == 1.0 and XX2["2026-10-13"] == ["2026-10-13"]


def test_paid_file_carries_its_own_unknown_spend_days(tmp_path, monkeypatch):
    """The paid file's "unk" / "billed" (the format contract be_build reads): the pass's OWN install days whose Google
    Ads cost by country is unknown — the all-users file's, a day past the all-users thru with spend but no split (Oct
    5, after the all-users cube's hole on Oct 1), the days past the spend cache (Oct 13) — so every short [X] row of
    every paid pack expands, from the paid file alone, to exactly the row the build made (by the contract's rule and by
    be_build's own reader of it, _xrow — the two sides of one format): Oct 5's spend null, never
    the known 0 that the all-users file's "geo" "unk" (it ends at the all-users thru) would give. Only the file's own
    days: a paid cube that read LESS far than the all-users one names no day past its own thru."""
    made, inside = {}, []
    real_pass, real_out = rb._paid_pass, rb._cc_out

    def pass_(*a, **k):
        inside.append(1)
        try:
            return real_pass(*a, **k)
        finally:
            inside.pop()

    def out_(full, px, cc):                                         # the paid country rows as the build made them
        if inside:
            made[cc] = [rb._row_out(x) for x in full]
        return real_out(full, px, cc)
    monkeypatch.setattr(rb, "_paid_pass", pass_)
    monkeypatch.setattr(rb, "_cc_out", out_)

    def go(name, n=5, **kw):
        made.clear()
        r = _run(tmp_path, monkeypatch, name, **kw)
        body, prow = _paid(r)
        cd = json.loads(r["body"])["cd"]
        assert sorted(made) == sorted(cc for cc in prow if cc != "XX") and len(made) == n
        oi = beb._OIn.of(cd, body)                                  # (be_build's reading of the same two files)
        for cc, rows in made.items():
            assert _pexpand(body, prow[cc], cc) == rows, (name, cc)  # every [X]: the build's own row, from the file
            assert [beb._xrow(oi, "p", date.fromisoformat(x[0]).toordinal(), cc) if len(x) == 1 else y
                    for x, y in zip(prow[cc], rows)] == rows, (name, cc)   # … and as be_build expands it (its reader)
        return body, prow, cd
    body, prow, cd = go("u2", paid={}, holes={date(2026, 10, 1)}, geo_holes=(date(2026, 9, 15), date(2026, 10, 5)))
    assert (cd["thru"], body["thru"], body["fthru"]) == ("2026-09-30", "2026-10-13", "2026-10-10")
    assert cd["geo"]["unk"] == [["2026-08-01", "2026-08-31"], ["2026-09-15", "2026-09-15"]]
    assert body["unk"] == [["2026-08-01", "2026-08-31"], ["2026-09-15", "2026-09-15"], ["2026-10-05", "2026-10-05"],
                           ["2026-10-13", "2026-10-13"]] and body["billed"] is True
    b2, _, cd2 = go("behind", paid={"holes": {date(2026, 10, 10)}})   # the paid cube's hole on Oct 10
    assert (cd2["thru"], b2["thru"]) == ("2026-10-13", "2026-10-09") and cd2["geo"]["unk"][-1] == ["2026-10-13"] * 2
    assert b2["unk"] == [["2026-08-01", "2026-08-31"], ["2026-09-15", "2026-09-15"]] and b2["billed"] is True
    DD = {x[0]: x for x in prow["DD"]}                              # Ads only: no Google Ads user of its own
    assert DD["2026-10-04"][3] == 1.0 and DD["2026-10-05"] == ["2026-10-05"]
    got = {x[0]: x for x in _pexpand(body, prow["DD"], "DD")}["2026-10-05"]
    old = {x[0]: x for x in _expand(prow["DD"], dict(cd, thru=body["thru"], fthru=body["fthru"]), "DD")}["2026-10-05"]
    assert (got[3], got[13]) == (None, None) and (old[3], old[13]) == (0.0, 0.0)   # (by the all-users "unk": wrong)
    XX = {x[0]: x for x in prow["XX"]}                              # "Not split": the same rule
    assert XX["2026-10-04"][3] == 1.0 and XX["2026-10-05"] == ["2026-10-05"]
    assert {x[0]: x for x in _pexpand(body, prow["XX"], "XX")}["2026-10-05"][3] is None
    # a country only the Google Ads users' read names, on one install day (Sep 1): every other day of it [X] — no Ads
    # cost of its own, so spend 0 on a known day and null on an unknown one (Aug, Sep 15, Oct 13), go() checking both
    # readers on each
    b3, p3, _ = go("only", n=6, paid={"inst": dict(PINST, EE=1), "rate": dict(PRATE, EE=3000),
                                      "only": {"EE": {date(2026, 9, 1)}}})
    assert [x[0] for x in p3["EE"] if len(x) > 1] == ["2026-09-01"] and len(p3["EE"]) == len(DAYS)
    EE = {x[0]: x for x in _pexpand(b3, p3["EE"], "EE")}
    assert [EE[d][3] for d in ("2026-08-01", "2026-09-02", "2026-09-15", "2026-09-16", "2026-10-13")] == \
        [None, 0.0, None, 0.0, None]


def test_loss_and_flags_of_the_paid_cube_mark_its_rows(tmp_path, monkeypatch):
    # the paid cube measured "(other)" on Sep 20 and GA4 flagged Sep 25: ≈ bits 2 / 4 on the rows using those days
    # (the all-users rows: none — its cube had neither), its file's loss note
    r = _run(tmp_path, monkeypatch, "loss", paid={"loss": {date(2026, 9, 20): 3000}, "flags": {date(2026, 9, 25)}})
    body, prow = _paid(r)
    assert body["loss"] == {"days": 1, "share": pytest.approx(3000 / (51 * sum(PRATE.values()) + 3000), abs=1e-6)}
    pa = {x[0]: x for x in body["rows"]}
    assert pa["2026-09-01"][12] == 6 and pa["2026-09-22"][12] == 4 and pa["2026-09-26"][12] == 0
    AA = {x[0]: x for x in prow["AA"]}
    assert AA["2026-09-01"][12] & 6 == 6 and not AA["2026-09-26"][12] & 6
    assert not any(x[12] & 6 for x in json.loads(r["body"])["rows"] if len(x) > 12)


def test_paid_pass_time_never_counts_in_the_forecast_budget(tmp_path, monkeypatch):
    # the forecast's clock runs from the first app; the paid pass (inside the country part's window) moves the clock's
    # start by exactly what it took — the forecast's budget, re-tunes and numbers as without the pass
    from types import SimpleNamespace
    now = [100.0]
    fc = SimpleNamespace(clock=lambda: now[0], t0=50.0)
    real = rb._paid_pass

    def slow(*a, **k):
        now[0] += 7.0
        return real(*a, **k)
    monkeypatch.setattr(rb, "_paid_pass", slow)
    data, P, pre, spend, acc0 = _cc_world(tmp_path / "w")
    _cc_cube(data, cube_mod=cp.MOD, inst=PINST, rate=PRATE)
    _stub_app(monkeypatch, P, {"read_today": CTODAY.isoformat(), "stream_id": "222", "x": {}}, spend)
    out = tmp_path / "w" / "out"
    out.mkdir()
    acc = rb.start(cube=True, cmon=acc0.cmon, cubep=True)
    acc.fc = fc                                                     # (the forecast step itself then fails: caught)
    store, a = {"history_start": CHS.isoformat(), "stream_id": "222"}, {"app_id": "a~1", "app_name": "Alpha"}
    rb.app_step(acc, store, a, KEY, {"tz": "UTC"}, pre, {}, str(out), str(data), ids=["a~1"])
    assert not acc.fails and acc.pdn["ok"] == 1 and fc.t0 == pytest.approx(57.0)
    rb.start()


# ── GA4_COHORTP: the paid All row from the Google Ads users' own D0 … D30 read ─────────────────────────────────────
COR, COU = 50000, 40                    # their D0 … D30 store (made up): micros at age 0 (+ 100 an age), users on day 0
#                                         (2 on each later day) — never what the paid cube's cells sum to (PRATE, PINST)
LO, LF, NOBODY = date(2026, 9, 20), date(2026, 8, 10), date(2026, 9, 3)


def _co_store(data, done=True, rt=CTODAY, stream="222", skip=(), lo=(), lf=(), refreshed=True, frm=CHS):
    """fetch.ga4_cohort_paid's store of app a~1 (its own folder, ga4_cohort's format): every install day CHS … rt but
    `skip` (the read named no Google Ads user of it) earns COR + 100 × age micros at each age lived, COU users on day 0
    and 2 later; lo / lf: activity days whose read kept "(other)" / GA4 flagged; done: its backfill through;
    refreshed: a refresh read the recent days (its read_today); frm: the day its backfill began at (the activity days
    before it never read: no cell)."""
    x, X = {}, CHS
    while X <= rt:
        live = [frm <= X + timedelta(days=L) <= rt for L in range(31)]
        if X not in skip and any(live):
            x[X.isoformat()] = {"r": [COR + 100 * L if live[L] else 0 for L in range(31)],
                                "u": [(COU if L == 0 else 2) if live[L] else 0 for L in range(31)]}
        X += timedelta(days=1)
    body = {"v": 1, "app_id": "a~1", "package": "p.q", "property_id": "111", "stream_id": stream, "time_zone": "UTC",
            "hs": CHS.isoformat(), "backfill": dict({"from": frm.isoformat(), "next": "2026-09-09"},
                                                    **({"done": True} if done else {})), "x": x}
    if refreshed:
        body["read_today"] = rt.isoformat()
    if lo:
        body["lo"] = {D.isoformat(): 1234 for D in lo}
    if lf:
        body["lf"] = {D.isoformat(): 1 for D in lf}
    cop.MOD.save_store(str(data), "a~1", body, CTODAY)


def _d_of(rt=CTODAY, X=date(2026, 8, 5)):
    """The All row's d of install day X by hand: the store's cells × the app's weekly k (1.2), cumulative."""
    cum, d = 0.0, []
    for L in range(min(30, (rt - X).days) + 1):
        cum += (COR + 100 * L) / 1e6 * 1.2
        d.append(round(cum, 4))
    return d


def test_paid_all_row_comes_from_their_own_d0_d30_read_never_the_cube_sum(tmp_path, monkeypatch):
    """GA4_COHORTP on and their D0 … D30 store done: the paid All rows are made from it exactly as every user's are
    from ga4_cohort — its cells × the app's weekly k, its users (n = day 0's), its own finality (read_today − 3), every
    install day hs … read_today (one it named no Google Ads user of: a real 0), q bit 1 from its own "lo" / "lf", the
    paid cube's 30-day columns on top of its D30 (t at day 60 from them once final) — never the paid cube's country
    cells summed; the packs, every other field of the paid file and every all-users output byte for byte as with the
    switch off; the switch off with the store on disk: never read (the file of a build without the store)."""
    prep = lambda d_: _co_store(d_, skip={NOBODY}, lo={LO}, lf={LF})    # noqa: E731
    co = _run(tmp_path, monkeypatch, "co", paid={}, cohortp=True, prep=prep)
    cube = _run(tmp_path, monkeypatch, "cube", paid={}, prep=prep)      # the switch off, the store on disk
    plain = _run(tmp_path, monkeypatch, "plain", paid={})               # … and no store at all
    pf = "roi_%s_p.json.gz" % KEY
    assert co["paid"] == cube["paid"] == {KEY: {"st": "ok", "file": pf}} and co["acc"].pdn["ok"] == 1
    assert cube["scratch"] == plain["scratch"]                          # (the switch off: the store never read)
    bc, pc = _paid(co)
    bk, pk = _paid(cube)
    assert (bc["all"], bk["all"]) == ("cohort", "cube") and pc == pk
    assert {n: v for n, v in co["scratch"].items() if n != pf} == {n: v for n, v in cube["scratch"].items() if n != pf}
    assert {k: v for k, v in bc.items() if k not in ("rows", "all", "cnew")} == \
        {k: v for k, v in bk.items() if k not in ("rows", "all")}       # (packs, edges, newest, loss, unk, billed)
    assert bc["cnew"] == bk["newest"] and "cnew" not in bk              # (the paid cube's newest day: both reads' here)
    for r in (co, cube):                                                # every all-users output as without the pass
        assert r["body"] == plain["body"] and r["out"] == plain["out"] and r["dash"] == plain["dash"]
    tail = "ads split unread 0"
    assert co["line"] == plain["line"] and co["line"].endswith(tail + ", paid ok 1 busy 0 none 0 fail 0")
    rows, krow = {x[0]: x for x in bc["rows"]}, {x[0]: x for x in bk["rows"]}
    assert [x[0] for x in bc["rows"]] == DAYS                           # every install day hs … read_today
    d = _d_of()
    x, k = rows["2026-08-05"], krow["2026-08-05"]
    assert (x[1], x[4], x[5], x[6]) == (COU, d, 31, [COU] + [2] * 30)   # n, d (final), u: the store's own
    assert (k[1], k[6]) == (sum(PINST.values()), None) and k[4] != d    # (the cube's sum: other numbers)
    assert x[7][J30] == d[30] and x[7][:J30 + 1] == [d[a] for a in T[:J30 + 1]]
    b1 = 30 * sum(PRATE.values()) / 1e6 * 1.2                           # D60: the paid cube's bucket 1 on ITS D30
    assert x[14] == [pytest.approx(d[30] + b1, abs=1e-4)] and x[15] == 1 and x[7][T.index(60)] == x[14][0]
    assert (x[8], x[9]) == (x[14][0], "2026-10-04")                     # so far: the furthest of its own
    assert x[2:4] == k[2:4] and x[13] == k[13] and x[3] == 10.0         # the app's own spend
    assert x[10] is None and x[11] in ("Worse", "Watch", "Normal", "Better", "Too early")   # judged (≥ 30 installs)
    assert x[12] == 1 and rows["2026-09-01"][12] == 1                   # its "lf" (Aug 10) / "lo" (Sep 20) in its d
    assert rows["2026-08-15"][12] == 0 and rows["2026-09-25"][12] == 0
    z = rows[NOBODY.isoformat()]                                        # a day it named no Google Ads user of: a
    assert (z[1], z[4], z[5], z[6]) == (0, [0.0] * 31, 31, [0] * 31)    # real 0, never left out
    y = rows["2026-10-12"]                                              # read through Oct 13, none final (Oct 10)
    assert (y[4], y[5], y[7]) == (d[:2], 0, [None] * len(T))
    assert rows["2026-09-20"][5] == 21                                  # final through read_today − 3 (Oct 10)


def test_paid_all_rows_start_at_the_day_their_d0_d30_backfill_began(tmp_path, monkeypatch):
    """Their D0 … D30 read's backfill began after the history start (ga4_cohort's backfill runs once, from the start
    it saw — the history start moved back since: the days before it never read): the paid All rows start at that day
    ("from"), every activity day of each read — an earlier install day has no row, never a $0 / ROAS-0 day nobody
    read nor one whose unread early ages count as 0 revenue."""
    frm = date(2026, 9, 10)
    r = _run(tmp_path, monkeypatch, "from", paid={}, cohortp=True, prep=lambda d_: _co_store(d_, frm=frm))
    assert r["paid"] == {KEY: {"st": "ok", "file": "roi_%s_p.json.gz" % KEY}}
    body, _ = _paid(r)
    assert body["all"] == "cohort" and [x[0] for x in body["rows"]] == [d for d in DAYS if d >= frm.isoformat()]
    x = body["rows"][0]
    assert (x[1], x[4], x[5], x[6]) == (COU, _d_of(X=frm), 31, [COU] + [2] * 30)   # its own cells from day 0, final


def test_paid_file_newest_day_is_never_before_its_last_all_row(tmp_path, monkeypatch):
    """The paid file's "newest", its All rows from their D0 … D30 read: THAT read's read_today — as every user's file
    has ga4_cohort's (its rows final through it − FINAL_LAG, none past it) —, the D0 … D30 read ahead of the paid cube
    or behind it; the paid cube's newest day (its packs': the Organic pass's ages) in "cnew"; the edges ("thru" /
    "fthru": the packs') never move. be_build on the file: no D0 … D30 cell of an All row past its final edge (df)
    passes asof's gate (X + a + LAG ≤ newest), the anchor's / _holes' limit (newest − CLAG) is never after the rows'
    newest final cell (CLAG ≥ the final lag; folded at D+3 a day before it: often still empty), and the Organic ages
    count from the older of the two cubes' newest days — never from the D0 … D30 read's."""
    fn, pf = "roi_%s.json.gz" % KEY, "roi_%s_p.json.gz" % KEY

    def be_side(r, body, rt):                                           # (before the next run's start: its folder)
        newest, app = beb.load(str(r["od"]), str(r["data"]), KEY, fn, True, (r["dir"], pf))[:2]
        nw = rt.toordinal()
        assert newest == rt.isoformat()
        fe = max(x.X + len(x.dd) - 1 for x in app if x.dd)                 # the rows' newest final cell (read_today
        assert fe == nw - rb.gco.FINAL_LAG and nw - beb.CLAG <= fe          # − FINAL_LAG): the anchor's / _holes'
        #                                                                     limit never after it
        n = 0
        for x in app:
            for j, a in enumerate(beb.GRID):
                if a <= 30 and a in beb.ASOF and x.X + a + beb.LAG <= nw and x.cum[j] is not None:
                    assert x.fin[j] is not None, (x.day, a)                 # asof's gate: a final cell, never one
                    n += 1                                                  # past df
        assert n > 300
        oi = beb._OIn.of(json.loads(r["body"])["cd"], body)                # every user's cube: through Oct 13
        assert oi.nw == min(date.fromisoformat(body["cnew"]), CTODAY).toordinal()
    rt = CTODAY + timedelta(days=1)
    ahead = _run(tmp_path, monkeypatch, "ahead", paid={"holes": (CTODAY,)}, cohortp=True,     # (the paid cube read
                 prep=lambda d_: _co_store(d_, rt=rt))                                          # through Oct 12)
    ba, _ = _paid(ahead)
    assert (ba["newest"], ba["cnew"], ba["rows"][-1][0], ba["thru"], ba["fthru"]) == \
        ("2026-10-14", "2026-10-12", "2026-10-14", "2026-10-12", "2026-10-10")
    assert {x[0]: x for x in ba["rows"]}["2026-08-05"][4] == _d_of(rt)
    be_side(ahead, ba, rt)
    rt = CTODAY - timedelta(days=1)
    behind = _run(tmp_path, monkeypatch, "behind", paid={}, cohortp=True, prep=lambda d_: _co_store(d_, rt=rt))
    bb, _ = _paid(behind)
    assert (bb["newest"], bb["cnew"], bb["rows"][-1][0], bb["thru"], bb["fthru"]) == \
        ("2026-10-12", "2026-10-13", "2026-10-12", "2026-10-13", "2026-10-10")
    assert {x[0]: x for x in bb["rows"]}["2026-10-07"][5] == 3          # (final through Oct 9 there)
    be_side(behind, bb, rt)


def test_paid_pass_busy_until_their_d0_d30_backfill_is_done(tmp_path, monkeypatch, capsys):
    """GA4_COHORTP on: no store of the stream yet (none, or another stream's) → "busy" with no progress; its backfill
    not through, or through with no refresh yet → "busy" with its "from" / "next"; nothing written, every all-users
    output as with the switch off, counted busy, no health line. The paid cube's own walk not through: ITS progress
    first; no paid cube of the stream: "none" — whatever the D0 … D30 read."""
    off = _run(tmp_path, monkeypatch, "off", cubep=False)
    prog = {"st": "busy", "from": "2026-08-01", "next": "2026-09-09"}
    capsys.readouterr()
    for name, prep, want in (("nostore", None, {"st": "busy"}),
                             ("stream", lambda d_: _co_store(d_, stream="999"), {"st": "busy"}),
                             ("backfill", lambda d_: _co_store(d_, done=False), prog),
                             ("norefresh", lambda d_: _co_store(d_, refreshed=False), prog)):
        r = _run(tmp_path, monkeypatch, name, paid={}, cohortp=True, prep=prep)
        assert r["paid"] == {KEY: want} and r["scratch"] == {}, name
        assert r["line"].endswith(", paid ok 0 busy 1 none 0 fail 0") and r["acc"].pdn["busy"] == 1, name
        assert r["body"] == off["body"] and r["out"] == off["out"] and r["dash"] == off["dash"], name
    assert "roi paid" not in capsys.readouterr().err
    walk = _run(tmp_path, monkeypatch, "walk", paid={"done": False}, cohortp=True,
                head={"from": "2026-08-01", "walk_at": "2026-10-13T05:00:00Z"},
                prep=lambda d_: _co_store(d_, done=False))
    assert walk["paid"] == {KEY: {"st": "busy", "from": "2026-08-01", "next": "2026-10-11", "at": "2026-10-13"}}
    none = _run(tmp_path, monkeypatch, "none", paid={"stream": "999"}, cohortp=True, prep=_co_store)
    assert none["paid"] == {KEY: {"st": "none"}} and none["scratch"] == {}


def test_be_build_holds_their_own_all_rows_against_their_packs(tmp_path, monkeypatch):
    """be_build on roi_build's own paid file: "all" "cohort" → every user's pack-gap rule on it (pack_gaps: its All rows
    — an independent read — against its packs, on its own newest / fthru), never pack_gaps_p; "cube" → pack_gaps_p,
    every user's All rows the reference (as before GA4_COHORTP)."""
    seen = []
    real_g, real_p = beb.pack_gaps, beb.pack_gaps_p
    monkeypatch.setattr(beb, "pack_gaps", lambda *a: seen.append(("all", a)) or real_g(*a))
    monkeypatch.setattr(beb, "pack_gaps_p", lambda *a: seen.append(("ref", a)) or real_p(*a))
    for name, co in (("co", True), ("cube", False)):
        r = _run(tmp_path, monkeypatch, name, paid={}, cohortp=co, prep=_co_store)
        body, _ = _paid(r)
        fn, pf = "roi_%s.json.gz" % KEY, "roi_%s_p.json.gz" % KEY
        seen.clear()
        got = beb.load(str(r["od"]), str(r["data"]), KEY, fn, True, (r["dir"], pf))
        (kind, args), = seen
        S_own, S_every = {}, {}
        for x in body["rows"]:
            beb._fday(S_own, x)
        for x in json.loads(r["body"])["rows"]:
            beb._fday(S_every, x)
        assert sum(S_own.values()) > 0 and got[0] == body["newest"] and got[4] == set()
        if co:
            assert kind == "all" and args[0] == S_own and args[2:4] == (date(2026, 10, 13).toordinal(),
                                                                       date(2026, 10, 10).toordinal())
        else:
            assert kind == "ref" and args[0] == S_every != S_own


# ── busy / none / fail: only the paid pass ──────────────────────────────────────────────────────────────────────────
def test_busy_none_and_fail_cost_only_the_paid_pass(tmp_path, monkeypatch, capsys):
    from admob_iq import health
    off = _run(tmp_path, monkeypatch, "off", cubep=False)
    busy = _run(tmp_path, monkeypatch, "busy", paid={"done": False},
                head={"from": "2026-08-01", "walk_at": "2026-10-13T05:00:00Z"})
    assert busy["paid"] == {KEY: {"st": "busy", "from": "2026-08-01", "next": "2026-10-11", "at": "2026-10-13"}}
    assert busy["scratch"] == {} and busy["line"].endswith(", paid ok 0 busy 1 none 0 fail 0")
    other = _run(tmp_path, monkeypatch, "other", paid={"stream": "999"})            # another stream's paid cube
    assert other["paid"] == {KEY: {"st": "none"}} and other["scratch"] == {}
    capsys.readouterr()

    def boom(*a, **k):
        raise ValueError("bad month")
    with monkeypatch.context() as m:                                                # a raise inside the paid read
        m.setattr(cp.MOD, "months", boom)
        early = _run(tmp_path, monkeypatch, "early", paid={})
    err = capsys.readouterr().err
    real = rb._gz_fast

    def late_boom(path, raw):                                                       # … or after its packs were written
        if path.endswith("_p.json.gz"):
            raise OSError("disk")
        real(path, raw)
    monkeypatch.setattr(rb, "_gz_fast", late_boom)
    late = _run(tmp_path, monkeypatch, "late", paid={})
    err2 = capsys.readouterr().err
    for r in (early, late):
        assert r["paid"] == {KEY: {"st": "fail"}} and r["scratch"] == {} and r["dir"]   # its files removed
        assert r["line"].endswith(", paid ok 0 busy 0 none 0 fail 1") and r["acc"].pdn["fail"] == 1
    assert "roi paid skipped: ValueError" in err and "roi paid skipped: OSError" in err2
    for r in (busy, other, early, late):                                             # every all-users byte as without
        assert r["body"] == off["body"] and r["out"] == off["out"] and r["dash"] == off["dash"]
    health.FAULTS.clear()
    try:
        health.scan("roi paid skipped: ValueError")
        assert health.FAULTS == {"roi paid": "ValueError"}                          # the health banner names it
    finally:
        health.FAULTS.clear()


def test_a_raising_ads_split_past_the_all_users_thru_costs_only_the_paid_pass(tmp_path, monkeypatch, capsys):
    """The Google Ads split of the days past the all-users thru is the paid pass's alone (_geo_more): its raise — Oct
    5's downloads no number, after the all-users cube's hole on Oct 1 — never costs the 🌍 table (its "cd", packs and
    board files byte for byte as with the switch off, nothing counted failed there); the paid pass "fail" with the
    real type on its health line, raised where the pass first needs that split (a paid walk not through yet: "busy")."""
    from admob_iq.fetch import gads_geo_day as gdd
    real = gdd.load

    def bad(d_, keep=None):
        g = real(d_, keep=keep)
        g["days"]["s1"]["2026-10-05"]["AA"] = [6_000_000, "n/a"]
        return g
    monkeypatch.setattr(gdd, "load", bad)
    capsys.readouterr()
    off = _run(tmp_path, monkeypatch, "off", cubep=False, paid={}, holes={date(2026, 10, 1)})
    e_off = capsys.readouterr().err
    on = _run(tmp_path, monkeypatch, "on", paid={}, holes={date(2026, 10, 1)})
    e_on = capsys.readouterr().err
    assert json.loads(off["body"])["cd"]["thru"] == "2026-09-30" and on["acc"].cdn == off["acc"].cdn
    assert on["body"] == off["body"] and on["out"] == off["out"] and on["dash"] == off["dash"]
    assert on["paid"] == {KEY: {"st": "fail"}} and on["scratch"] == {}
    line = "roi paid skipped: ValueError\n"
    assert "roi paid" not in e_off and line in e_on and e_on.replace(line, "", 1) == e_off
    tail = "ads split unread 0"
    assert on["line"] == off["line"].replace(tail, tail + ", paid ok 0 busy 0 none 0 fail 1")
    busy = _run(tmp_path, monkeypatch, "busy", paid={"done": False}, holes={date(2026, 10, 1)})
    assert busy["paid"][KEY]["st"] == "busy" and busy["body"] == off["body"] and busy["out"] == off["out"]
    assert "roi paid" not in capsys.readouterr().err


def test_a_raising_all_users_side_fails_the_paid_pass_never_silently(tmp_path, monkeypatch, capsys):
    """The switch on and the paid pass could not run because the all-users side raised — the cube's walk (_late) or
    its 🌍 part (_cty: a hot day's country cell that is no number) —: PAID "fail", counted, its health line with that
    raise's type (be_build would otherwise read "off": every user's numbers under the note that the Google Ads ones
    are on their way); the switch off: no word of it. Its own non-runs — the all-users walk not through, no country
    in the cube — stay no entry, nothing counted, nothing printed."""
    from admob_iq.fetch import ga4_cube as cu

    def bad_cell(data):                         # Oct 13's AA installs no number: the 🌍 read fails, the walk does not
        h = cu.load_head(str(data), "a~1")
        h["d"][CTODAY.isoformat()]["e"]["AA"][CTODAY.isoformat()][0] = "n/a"
        cu.write_json_gz_stable(cu.hot_path(str(data), "a~1"), h)

    def strip(data):                            # the cube without its country parts: no country named
        for M, mo in cu.months(str(data), "a~1", "222"):
            cu.write_json_gz_stable(cu.month_path(str(data), "a~1", M), dict(mo, c={}, e={}))
        h = cu.load_head(str(data), "a~1")
        for rec in h["d"].values():
            rec["c"], rec["e"] = {}, {}
        cu.write_json_gz_stable(cu.hot_path(str(data), "a~1"), h)
    real = rb._late

    def walk_boom(*a, **k):                     # the all-users walk raises (the paid one would not)
        if k.get("cu", rb.gcu) is rb.gcu:
            raise OSError("disk")
        return real(*a, **k)
    tail = "ads split unread 0"
    capsys.readouterr()
    for name, prep, why in (("cty", bad_cell, "RuntimeError"), ("walk", None, "OSError")):
        with monkeypatch.context() as m:
            if prep is None:
                m.setattr(rb, "_late", walk_boom)
            off = _run(tmp_path, monkeypatch, name + "_off", cubep=False, paid={}, prep=prep)
            e_off = capsys.readouterr().err
            on = _run(tmp_path, monkeypatch, name + "_on", paid={}, prep=prep)
            e_on = capsys.readouterr().err
        assert "cd" not in json.loads(on["body"]) and ("late" in json.loads(on["body"])) == (name == "cty")
        assert on["body"] == off["body"] and on["out"] == off["out"] and on["dash"] == off["dash"]
        assert off["paid"] == {} and on["paid"] == {KEY: {"st": "fail"}} and on["scratch"] == {}
        assert on["acc"].cdn["failed"] == off["acc"].cdn["failed"] == (name == "cty")
        line = "roi paid skipped: %s\n" % why
        assert "roi paid" not in e_off and line in e_on and e_on.replace(line, "", 1) == e_off, name
        assert ", paid" not in off["line"] and on["line"] == off["line"].replace(
            tail, tail + ", paid ok 0 busy 0 none 0 fail 1"), name
    for name, kw in (("busy", {"done": False}), ("nocc", {"prep": strip})):
        r = _run(tmp_path, monkeypatch, name, paid={}, **kw)
        assert "cd" not in json.loads(r["body"]) and r["paid"] == {} and r["scratch"] == {}, name
        assert r["acc"].pdn == {"ok": 0, "busy": 0, "none": 0, "fail": 0} and r["acc"].cdn["failed"] == 0, name
        assert r["line"].endswith(", paid ok 0 busy 0 none 0 fail 0") and "roi paid" not in capsys.readouterr().err


# ── the scratch folder ──────────────────────────────────────────────────────────────────────────────────────────────
def test_scratch_folder_never_under_the_site_or_data(tmp_path, monkeypatch):
    r = _run(tmp_path, monkeypatch, "on", paid={})
    d = r["dir"]
    assert d and os.path.isdir(d) and os.path.basename(d).startswith("roi_paid_")
    real = os.path.realpath(d)
    for root in (r["data"], r["od"]):
        base = os.path.realpath(str(root))
        assert os.path.commonpath([real, base]) != base                              # never inside out_dir / data_dir
    rb.start()                                                                       # the next build: the old one gone
    assert not os.path.exists(d) and rb.PAID == {} and rb.PAID_DIR is None
    rb.start(cubep=True)
    d2 = rb.PAID_DIR
    assert os.path.isdir(d2) and d2 != d
    rb.off(str(tmp_path / "gone"))                                                   # the ROI section off
    assert not os.path.exists(d2) and rb.PAID_DIR is None and rb.PAID == {}
    rb.start(cubep=True)
    d3 = rb.PAID_DIR
    rb._paid_drop()                                                                  # the process's exit (atexit)
    assert not os.path.exists(d3) and rb.PAID_DIR is None and rb._PAID_EXIT
    # a folder that cannot be made: every app's pass "fail" (counted), never the ROI section
    off = _run(tmp_path, monkeypatch, "off", cubep=False)

    def no_dir(**k):
        raise OSError("no temp")
    monkeypatch.setattr(rb.tempfile, "mkdtemp", no_dir)
    bad = _run(tmp_path, monkeypatch, "nodir", paid={})
    assert bad["dir"] is None and bad["paid"] == {KEY: {"st": "fail"}} and bad["body"] == off["body"]
    assert bad["out"] == off["out"] and bad["line"].endswith(", paid ok 0 busy 0 none 0 fail 1")


def test_stale_scratch_folders_of_killed_runs_go_and_nothing_else(tmp_path, monkeypatch):
    """A run killed before its exit (no atexit) leaves its folder: a later start(cubep) removes it once untouched for
    PAID_STALE_H hours — only "roi_paid_*" folders holding nothing but this pass's files; a running build's (fresh) and
    anything else stay."""
    import tempfile
    import time
    root = tmp_path / "tmp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    old = time.time() - (rb.PAID_STALE_H + 1) * 3600
    pf = "roi_%s_p.json.gz" % KEY
    made = {"roi_paid_k1lled00": [pf, "roi_%s_p00.json.gz" % KEY], "roi_paid_empty000": [], "roi_paid_fresh000": [pf],
            "roi_paid_foreign0": [pf, "notes.txt"], "other_folder": [pf]}
    for n, files in made.items():
        (root / n).mkdir()
        for f in files:
            (root / n / f).write_bytes(b"x")
        if n != "roi_paid_fresh000":
            os.utime(str(root / n), (old, old))
    rb.start(cubep=True)
    left = sorted(os.listdir(str(root)))
    assert os.path.basename(rb.PAID_DIR) in left and os.path.dirname(rb.PAID_DIR) == str(root)
    assert sorted(n for n in left if n != os.path.basename(rb.PAID_DIR)) == ["other_folder", "roi_paid_foreign0",
                                                                             "roi_paid_fresh000"]
    rb.start()
    assert sorted(os.listdir(str(root))) == ["other_folder", "roi_paid_foreign0", "roi_paid_fresh000"]


# ── the switch, the stage, the workflow, the wiring ─────────────────────────────────────────────────────────────────
def test_switch_stage_workflow_and_the_uninstall_wiring(tmp_path, monkeypatch):
    import yaml
    from admob_iq import stage_clock as sc
    from admob_iq.config import settings
    from admob_iq.fetch import ga4_uninstall as gu
    from tests import test_value_build as tvb
    monkeypatch.delenv("BE_PAID", raising=False)
    assert settings()["be_paid"] is False
    monkeypatch.setenv("BE_PAID", "TRUE")
    assert settings()["be_paid"] is True
    monkeypatch.delenv("BE_PAID")
    monkeypatch.delenv("BE_TAB", raising=False)                                       # the tab's switch: the key the
    assert settings()["be_tab"] is True                                                # gate below reads
    monkeypatch.setenv("BE_TAB", "false")
    assert settings()["be_tab"] is False
    monkeypatch.delenv("BE_TAB")
    assert sc.STAGES[sc.STAGES.index("roi_country") + 1] == "roi_paid"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    env = [st for st in wf["jobs"]["refresh"]["steps"] if st.get("name") == "Build dashboard + send alerts"][0]["env"]
    assert env["BE_PAID"] == "${{ vars.BE_PAID || 'false' }}"
    # uninstall_build starts the ROI with the pass only when BOTH switches are on (the paid cube's reads and its use)
    # and the tab is: be_build, the pass's only reader, runs only with BE_TAB on (off: no pass at all, nothing wasted)
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(tvb.STATUS))
    monkeypatch.setattr(cp, "refresh_all", lambda *a, **k: {"counts": {}})         # (no GA4: no network in tests)
    monkeypatch.setattr(cop, "refresh_all", lambda *a, **k: {"counts": {}})
    got, real = [], rb.start

    def start(**k):
        got.append((k.get("cubep"), k.get("cohortp")))
        return real(**k)
    monkeypatch.setattr(rb, "start", start)
    for i, kw in enumerate(({"ga4_cubep": True, "be_paid": False}, {"ga4_cubep": True, "be_paid": True},
                            {"ga4_cubep": True, "be_paid": True, "be_tab": False},
                            {"ga4_cubep": True, "be_paid": True, "ga4_cohortp": True})):
        tvb.vbuild(str(tmp_path / str(i) / "data"), str(tmp_path / str(i) / "site"), s=tvb.ga4_settings(**kw))
    assert got == [(False, False), (True, False), (False, False), (True, True)]     # (GA4_COHORTP: the pass's All
    rb.start()                                                                       # row from its store) — its
    #                                                                                  scratch folder let go
