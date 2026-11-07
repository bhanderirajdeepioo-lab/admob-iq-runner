"""📱 Devices inside the ROI step (roi_build.app_step → _dev → device_build.build_app), offline on the ROI tests' made-up
country world (tests/test_roi_build.py: install days from 1 Aug, Google Ads split by country from 1 Sep): the ROI file
carries only the stub, the Devices files sit beside it with the app's key, their cost comes from the 🌍 Countries cost
(by country × install day), a month with no AdMob behind its scale is counted, finish() keeps the app's Devices files
and removes another app's, the counts-only line, and a failure costs only the block. Memory: the store is read once
(build_app works on app_step's own copy, every file as when it read the store again) and build_app frees its cell
caches before it writes. No real data."""
import gzip
import json
import os
import sys
from datetime import timedelta

import pytest

from admob_iq import device_build as dvb
from admob_iq import roi_build as rb
from admob_iq.fetch import ga4_device as gd
from admob_iq.fetch import ga4_uninstall as gu
from tests import test_roi_build as trb

AID = "a~1"
CCS = {"AA": 0.6, "BB": 0.3, "DD": 0.1}
MODELS = {"XM-1": 0.7, "XM-2": 0.3}


def _day(x, f, at="2026-10-13T00:00:00Z"):
    s, p, d = {}, {}, {}
    for md, ms in MODELS.items():
        for cc, cs in CCS.items():
            n = 100 * ms * cs
            s.setdefault(md, {})[cc] = [n, round(n * 0.01 * ((f - x).days + 1), 4)]
            p.setdefault(md, {})[cc] = n / 2
            d.setdefault(md, {})[cc] = n / 4
    return {"S": {"m": s, "t": [100, round(sum(v[1] for c in s.values() for v in c.values()), 4)], "to": f.isoformat(),
                  "at": at}, "P": {"m": p, "t": 50, "at": at}, "D1": {"m": d, "t": 25, "at": at}}


def _store(data):
    today = trb.CTODAY
    f = today - timedelta(days=5)
    st = gd.Store(os.path.join(str(data), gd.DIR), gu.file_key(AID))
    x, xs = trb.CHS, {}
    while x <= today:
        xs[x.isoformat()] = _day(x, f)
        x += timedelta(days=1)
    st.save_view({"app_id": AID, "stream_id": "222", "F": f.isoformat(), "today": today.isoformat(), "x": xs,
                  "names": {"XM-1": ["XBrand", "Phone One"]}})


def _run(tmp_path, monkeypatch, name, with_store=True):
    data, P, pre, spend, acc0 = trb._cc_world(tmp_path / name)
    if with_store:
        _store(data)
    co = {"read_today": trb.CTODAY.isoformat(), "stream_id": "222", "x": {}}
    trb._stub_app(monkeypatch, P, co, spend)
    out = tmp_path / name / "out"
    out.mkdir()
    acc = rb.start(cube=True, cmon=acc0.cmon)
    store, a = {"history_start": trb.CHS.isoformat(), "stream_id": "222"}, {"app_id": AID, "app_name": "Alpha"}
    rb.app_step(acc, store, a, "aaaaaaaaaaaa", {"tz": "UTC"}, pre, {}, str(out), str(data), ids=[AID])
    assert not acc.fails and len(acc.apps) == 1
    with gzip.open(os.path.join(str(out), "roi_aaaaaaaaaaaa.json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f), acc, out


def _load(out, name):
    with gzip.open(os.path.join(str(out), name), "rt", encoding="utf-8") as f:
        return json.load(f)


def test_the_roi_file_carries_a_stub_and_the_files_sit_beside_it(tmp_path, monkeypatch):
    body, acc, out = _run(tmp_path, monkeypatch, "on")
    dev = body["dev"]
    assert dev["v"] == 3 and dev["file"] == "roi_aaaaaaaaaaaa_dv.json.gz" and set(dev) == {"v", "file", "sha", "vcount",
                                                                                         "today", "first"}
    assert dev["first"] == trb.CHS.isoformat() and acc.apps[0]["dv"] == dev["vcount"]
    D = _load(out, dev["file"])
    assert D["P"]["all"]["from"] == trb.CHS.isoformat()
    assert D["P"]["all"]["tot"]["n"] == 100 * ((trb.CTODAY - trb.CHS).days + 1)
    # the cost: the 🌍 Countries cost of each country × install day (from 1 Sep: AA and BB split, XX never a country)
    t = D["P"]["all"]["by"]["AA"]["tot"]
    assert t["cost"] > 0 and t["pk"] > 0 and D["P"]["all"]["by"]["AA"]["rows"][0][0] == "XM-1"
    aug = [m for m in D["months"] if m[0] == "2026-08"][0]
    assert aug[1][D["U"].index("nc")] == 31             # August: Google Ads has not split it by country
    names = sorted(n for n in os.listdir(str(out)) if n.startswith("roi_aaaaaaaaaaaa_dv"))
    assert names == ["roi_aaaaaaaaaaaa_dv.json.gz"] + sorted(
        "roi_aaaaaaaaaaaa_dv%s_%s.json.gz" % (k, m) for m in ("2026-08", "2026-09", "2026-10") for k in "dm")
    assert set(names) <= acc.dvf
    # finish keeps the app's Devices files, removes another app's / an older build's stray one
    for f in ("roi_bbbbbbbbbbbb_dv.json.gz", "roi_bbbbbbbbbbbb_dvm_2026-01.json.gz", "roi_aaaaaaaaaaaa_dvd_2025-01.json.gz"):
        open(os.path.join(str(out), f), "w").close()
    assert rb.finish(acc, {}, str(out)) == ["/roi*"]
    left = sorted(n for n in os.listdir(str(out)) if "_dv" in n)
    assert left == names
    line = rb.pop_line()
    assert "; devices: apps 1, rows " in line and ", months 3, cached 0, built " in line and ", failed 0" in line
    assert "Alpha" not in line and "XM-" not in line and "AA" not in line


def test_a_device_failure_costs_only_its_block(tmp_path, monkeypatch, capsys):
    plain, acc0, _ = _run(tmp_path, monkeypatch, "none", with_store=False)
    assert "dev" not in plain and acc0.dvn["apps"] == 0
    monkeypatch.setattr(dvb, "build_app", lambda *a, **k: 1 / 0)
    capsys.readouterr()
    bad, acc, out = _run(tmp_path, monkeypatch, "bad")
    assert "dev" not in bad and acc.dvn["failed"] == 1 and not [n for n in os.listdir(str(out)) if "_dv" in n]
    assert "devices skipped: ZeroDivisionError" in capsys.readouterr().err     # the health banner sees it
    plain.pop("newest", None)
    bad.pop("newest", None)
    assert bad == plain                                 # every other byte as without a device store


def test_over_the_size_limit_the_last_stub_stays(tmp_path, monkeypatch):
    body, acc, out = _run(tmp_path, monkeypatch, "big")
    last = body["dev"]
    data = tmp_path / "big" / "data"
    st = gd.Store(os.path.join(str(data), gd.DIR), gu.file_key(AID))
    v = st.view()                                       # the hourly fetch read today's revenue again …
    v["x"][trb.CTODAY.isoformat()]["S"]["m"]["XM-1"]["AA"][1] += 5
    v["x"][trb.CTODAY.isoformat()]["S"]["at"] = "2026-10-13T05:00:00Z"
    st.save_view(v)
    monkeypatch.setattr(dvb, "MAX_GZ", 50)              # … and this build's files would be over the limit
    co = {"read_today": trb.CTODAY.isoformat(), "stream_id": "222", "x": {}}
    P = trb._P(trb.CHS, trb.CTODAY - timedelta(days=6))
    P["sc"]["kf"] = lambda d_: (1.2, "ok", False, 1.2)
    _, _, pre, spend, acc0 = trb._cc_world(tmp_path / "w2")
    trb._stub_app(monkeypatch, P, co, spend)
    acc2 = rb.start(cube=True, cmon=acc0.cmon)
    store, a = {"history_start": trb.CHS.isoformat(), "stream_id": "222"}, {"app_id": AID, "app_name": "Alpha"}
    rb.app_step(acc2, store, a, "aaaaaaaaaaaa", {"tz": "UTC"}, pre, {}, str(out), str(data), ids=[AID])
    with gzip.open(os.path.join(str(out), "roi_aaaaaaaaaaaa.json.gz"), "rt", encoding="utf-8") as f:
        again = json.load(f)
    assert again["dev"] == last and acc2.dvn["toobig"] == 2    # October (its two files, checked together) + the buttons'
    assert {n for n in os.listdir(str(out)) if n.startswith("roi_aaaaaaaaaaaa_dv")} <= acc2.dvf


def test_a_failure_after_a_good_build_keeps_the_last_stub_and_its_files(tmp_path, monkeypatch, capsys):
    body, acc, out = _run(tmp_path, monkeypatch, "keep")
    last = body["dev"]
    names = {n for n in os.listdir(str(out)) if n.startswith("roi_aaaaaaaaaaaa_dv")}
    data = tmp_path / "keep" / "data"
    monkeypatch.setattr(dvb, "build_app", lambda *a, **k: 1 / 0)
    _, _, pre, spend, acc0 = trb._cc_world(tmp_path / "w3")
    co = {"read_today": trb.CTODAY.isoformat(), "stream_id": "222", "x": {}}
    trb._stub_app(monkeypatch, trb._P(trb.CHS, trb.CTODAY - timedelta(days=6)), co, spend)
    acc2 = rb.start(cube=True, cmon=acc0.cmon)
    store, a = {"history_start": trb.CHS.isoformat(), "stream_id": "222"}, {"app_id": AID, "app_name": "Alpha"}
    capsys.readouterr()
    rb.app_step(acc2, store, a, "aaaaaaaaaaaa", {"tz": "UTC"}, pre, {}, str(out), str(data), ids=[AID])
    assert "devices skipped: ZeroDivisionError" in capsys.readouterr().err
    with gzip.open(os.path.join(str(out), "roi_aaaaaaaaaaaa.json.gz"), "rt", encoding="utf-8") as f:
        assert json.load(f)["dev"] == last and acc2.dvn["failed"] == 1
    rb.finish(acc2, {}, str(out))                       # never cleaned away (nor built again next time)
    assert {n for n in os.listdir(str(out)) if n.startswith("roi_aaaaaaaaaaaa_dv")} == names


def test_too_big_is_said_even_when_no_devices_block_was_built(tmp_path, monkeypatch, capsys):
    _, acc, out = _run(tmp_path, monkeypatch, "tb")
    acc.dvn.update(apps=0, failed=0, toobig=1)
    capsys.readouterr()
    rb.finish(acc, {}, str(out))
    assert "devices skipped: TooBigError" in capsys.readouterr().err and "devices:" not in rb.LINE


# ── 🧠 memory: build_app works on app_step's own copy of the store (never read twice) and frees its cells early ──────
def _bytes(d):
    """Every file of a folder → its decompressed bytes."""
    return {n: gzip.decompress(open(os.path.join(str(d), n), "rb").read()) for n in sorted(os.listdir(str(d)))}


def test_the_devices_block_reads_the_store_once_and_writes_the_same_files(tmp_path, monkeypatch):
    real_build, real_view, real_load = dvb.build_app, gd.Store.view, gd.load_store
    seen, views = {}, []

    def view(self):
        views.append(self.key)
        return real_view(self)

    def load_store(path):
        seen["dst"] = real_load(path)
        return seen["dst"]

    def build_app(*a, **k):
        seen["view"] = k.get("view")
        return real_build(*a, **k)
    monkeypatch.setattr(gd.Store, "view", view)
    monkeypatch.setattr(gd, "load_store", load_store)
    monkeypatch.setattr(dvb, "build_app", build_app)
    once, _, out1 = _run(tmp_path, monkeypatch, "once")
    assert seen["view"] is seen["dst"] and views == [gu.file_key(AID)]     # one read of the store: app_step's own
    # as before this change: build_app read the same store again itself
    monkeypatch.setattr(dvb, "build_app", lambda *a, **k: real_build(*a, **{x: v for x, v in k.items() if x != "view"}))
    views.clear()
    twice, _, out2 = _run(tmp_path, monkeypatch, "twice")
    assert views == [gu.file_key(AID)] * 2
    assert once == twice and "dev" in once and _bytes(out1) == _bytes(out2)
    sd = os.path.join(gd.DIR, gu.file_key(AID))
    assert _bytes(tmp_path / "once" / "data" / sd) == _bytes(tmp_path / "twice" / "data" / sd)


def _long_store(data, v1=False):
    """A store whose older install days sit in their month files (more than KEEP_DAYS back), or (v1) the one-file
    store of before 6 Nov 2026 → the first install day."""
    today = trb.CTODAY
    f = today - timedelta(days=5)
    first = today - timedelta(days=gd.KEEP_DAYS + 60)
    xs, x = {}, first
    while x <= today:
        xs[x.isoformat()] = _day(x, f)
        x += timedelta(days=1)
    view = {"app_id": AID, "stream_id": "222", "F": f.isoformat(), "today": today.isoformat(), "x": xs,
            "names": {"XM-1": ["XBrand", "Phone One"]}}
    if v1:
        from admob_iq.db import write_json_gz_stable
        os.makedirs(os.path.join(str(data), gd.DIR), exist_ok=True)
        write_json_gz_stable(gd.store_path(str(data), AID), dict(view, v=gd.V1))
    else:
        gd.Store(os.path.join(str(data), gd.DIR), gu.file_key(AID)).save_view(view)
    return first


def _build(data, out, first, **kw):
    cost = {}
    X = first
    while X <= trb.CTODAY:
        cost.setdefault("AA", {})[X] = 2.0
        cost.setdefault("BB", {})[X] = 0.5 if X.day % 3 else 0.0
        X += timedelta(days=1)
    return dvb.build_app(str(data), gu.file_key(AID), cost, {first}, lambda X: 1.2, lambda X: X.month == 9, {}, first,
                         str(out), {}, **kw)


@pytest.mark.parametrize("v1", [False, True])
def test_build_app_on_the_callers_copy_of_the_store_writes_the_same_files(tmp_path, v1):
    runs = {}
    for how in ("own", "given"):
        data, out = tmp_path / how / "data", tmp_path / how / "out"
        out.mkdir(parents=True)
        first = _long_store(data, v1)
        got = []
        for _ in range(2):                              # a full build, then a warm one (its cold months cached)
            kw = {"view": gd.load_store(gd.store_path(str(data), AID))} if how == "given" else {}
            got.append(_build(data, out, first, **kw))
        runs[how] = (got, _bytes(out), _bytes(data / gd.DIR / gu.file_key(AID)))
    assert runs["own"] == runs["given"]
    assert len(runs["own"][1]) > 7                      # the stub + both files of every month (not vacuous)
    st = gd.Store(os.path.join(str(tmp_path / "own" / "data"), gd.DIR), gu.file_key(AID))
    assert (st.meta is None) == v1 and (v1 or len(st.months()) >= 2)    # (v2: months read from their files)


def test_build_app_frees_its_cell_caches_before_writing(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    out.mkdir()
    first = _long_store(data)
    names = ("dcache", "mcells", "allc", "sums", "run_c", "recent")
    at = {}

    def prof(frame, event, arg):                        # build_app's names at its first site write (the stub's)
        if event == "call" and frame.f_code is dvb.put_file.__code__ and not at:
            up = frame.f_back
            if up is not None and up.f_code is dvb.build_app.__code__:
                at.update({k: up.f_locals.get(k, "missing") for k in names + ("W",)})
    sys.setprofile(prof)
    try:
        got = _build(data, out, first)
    finally:
        sys.setprofile(None)
    assert got and at and all(at[k] is None for k in names) and at["W"]     # the verdict windows stay
