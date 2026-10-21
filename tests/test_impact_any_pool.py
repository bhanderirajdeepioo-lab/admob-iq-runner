"""📦 Compare any date built side by side (impact_any_build, IMPACT_ANY_WORKERS): every file, the index, the counts
line and every other output of the Uninstall step byte-identical to the in-process build — with a real process pool
(spawn), its time budget replayed in app order, a crash, a pool that breaks, inputs that cannot be pickled, the split
switched off (SPLIT=false) and split failures counted, the step raising after apps were queued (their files written as
in-process, no pool process left). Synthetic stores only (tests.uninstall_synth)."""

import copy
import gzip
import multiprocessing as mp
import os
import pickle
import re
import shutil
from concurrent.futures import Future

import pytest

from admob_iq import impact_any_build as iab
from admob_iq.engine import impact_any as ia
from tests.test_impact_any import _snap, ga4_settings, isite  # noqa: F401  (isite: the fixture)
from tests.test_impact_windows import _stores
from tests.test_uninstall_build import run
from tests.uninstall_synth import END


def _all(out, data):
    files = {}
    for tag, root in (("site", out), ("data", os.path.join(data, "ga4_uninstall"))):
        for n in sorted(os.listdir(root)):
            files[tag + "/" + n] = open(os.path.join(root, n), "rb").read()
    return files


def _twice(tmp_path, data, out, workers_b, **kw):
    """The same site built in the build's own process (A) and with workers_b (B), from two copies of its inputs."""
    d2, o2 = str(tmp_path / "data_b"), str(tmp_path / "site_b")
    shutil.copytree(data, d2)
    if os.path.exists(out):
        shutil.copytree(out, o2)
    dash_a, files_a = run(data, out, ga4_settings(impact_any_workers=0, **kw))
    line_a = iab.pop_line()
    dash_b, files_b = run(d2, o2, ga4_settings(impact_any_workers=workers_b, **kw))
    line_b = iab.pop_line()
    _twice.runs = dict(iab.RUNS)
    return (dash_a, files_a, line_a, _all(out, data)), (dash_b, files_b, line_b, _all(o2, d2))


def _same(a, b):
    assert a[2] == b[2] and a[2].startswith("impact any: apps 3,")
    assert a[0] == b[0] and a[1] == b[1]
    assert a[3].keys() == b[3].keys()
    for k in a[3]:
        assert a[3][k] == b[3][k], k


def test_side_by_side_in_a_real_pool_writes_the_same_bytes(tmp_path, isite):
    data, out = isite
    a, b = _twice(tmp_path, data, out, 2)
    _same(a, b)
    assert a[2].startswith("impact any: apps 3, built 3, kept 0,")
    assert _twice.runs == {"pool": 3, "here": 0}                       # every app really built in the pool
    assert sum(1 for k in a[3] if k.startswith("site/impact_any_")) == 4


def test_kept_and_one_changed_app_and_a_tight_budget_replayed_in_app_order(tmp_path, isite):
    from admob_iq.fetch import ga4_uninstall as gu
    from tests.test_uninstall_build import A1, A2, A6
    data, out = isite
    run(data, out, ga4_settings(impact_any_workers=0))                   # every file there: the next build keeps them
    iab.pop_line()
    p = gu.store_path(data, A1)                                          # GA4 fetched again for one app
    st = gu.load_store(p)
    st["daily"][END.isoformat()]["a1"] += 50
    gu.save_store(p, st)
    a, b = _twice(tmp_path / "k", data, out, 2)
    _same(a, b)
    assert a[2].startswith("impact any: apps 3, built 1, kept 2,")
    for aid in (A1, A2, A6):                                              # every store new, a budget spent by the first
        p = gu.store_path(data, aid)
        st = gu.load_store(p)
        st["daily"][END.isoformat()]["a1"] += 5
        gu.save_store(p, st)
    a, b = _twice(tmp_path / "b", data, out, 2, impact_any_budget_sec=1e-9)
    _same(a, b)
    assert a[2].startswith("impact any: apps 3, built 1, kept 0, stale 2, pending 0,")


def test_first_build_past_its_budget_waits_the_same_apps(tmp_path, isite):
    data, out = isite
    a, b = _twice(tmp_path, data, out, 2, impact_any_budget_sec=1e-9)
    _same(a, b)
    assert a[2].startswith("impact any: apps 3, built 1, kept 0, stale 0, pending 2,")


class _Pool:
    """A stand-in pool: runs each job here (so the test can patch the engine) or answers like a broken pool."""

    def __init__(self, broken=False):
        self.broken, self.n = broken, 0

    def submit(self, fn, *a):
        self.n += 1
        f = Future()
        if self.broken and self.n >= 2:
            f.set_exception(RuntimeError("pool broke"))
        else:
            f.set_result(fn(*a))
        return f

    def shutdown(self, **k):
        pass


@pytest.mark.parametrize("broken", [False, True])
def test_a_crash_costs_only_that_apps_file_and_a_broken_pool_builds_the_rest_here(tmp_path, isite, monkeypatch,
                                                                                    broken):
    data, out = isite
    real, calls = ia.build_app, []

    def boom(store, rev, app_id, *a, **k):
        calls.append(app_id)
        if len(calls) % 3 == 2:                                          # the second app of each build
            raise RuntimeError("boom")
        return real(store, rev, app_id, *a, **k)
    monkeypatch.setattr(ia, "build_app", boom)
    pools, made = [], {}
    monkeypatch.setattr(iab, "_pool", lambda acc: pools.append(1) or made.setdefault(id(acc), _Pool(broken)))
    a, b = _twice(tmp_path, data, out, 2)
    _same(a, b)
    assert a[2].startswith("impact any: apps 3, built 2, kept 0, stale 0, pending 0, failed 1,")
    assert len(calls) == 6 and pools and _twice.runs == ({"pool": 1, "here": 2} if broken else {"pool": 3, "here": 0})


def test_inputs_that_cannot_be_pickled_are_built_here_in_order(tmp_path, isite, monkeypatch):
    data, out = isite
    n = []

    class Pk:
        HIGHEST_PROTOCOL, loads = pickle.HIGHEST_PROTOCOL, staticmethod(pickle.loads)

        @staticmethod
        def dumps(obj, *a, **k):
            n.append(1)
            if len(n) == 2:
                raise pickle.PicklingError("x")
            return pickle.dumps(obj, *a, **k)
    monkeypatch.setattr(iab, "pickle", Pk)
    monkeypatch.setattr(iab, "_pool", lambda acc: _Pool())
    a, b = _twice(tmp_path, data, out, 2)
    _same(a, b)
    assert len(n) == 3


def test_the_job_serializes_as_the_writer_and_never_changes_its_inputs(tmp_path):
    for i, (st, rv) in enumerate(_stores()):
        if i > 3:
            break
        st = dict(st, window_end=END.isoformat())
        s0, r0 = copy.deepcopy(st), copy.deepcopy(rv)
        body, failed = ia.build_app(st, rv, "a", "0" * 12, "sig", 7)
        assert st == s0 and rv == r0                                     # build_app reads its inputs only
        res = iab._job(iab._payload(st, rv, "a", "0" * 12, "sig", 7, "impact_any_%s.json.gz" % ("0" * 12)))
        p = str(tmp_path / ("w%d.json.gz" % i))
        iab.write_json_gz_stable(p, body)
        with gzip.open(p, "rb") as f:
            assert f.read() == res["raw"] == iab._raw(body)
        assert res["failed"] == failed and res["entry"] == ia.index_entry(body, "impact_any_%s.json.gz" % ("0" * 12))
        assert res["sec"] >= 0 and res["fails"] == 0
    bad = iab._job(b"not a pickle")
    assert set(bad) == {"err", "sec", "fails"} and bad["fails"] == 0


def test_workers_setting():
    assert iab.start("/nonexistent", {"impact_any_workers": "x"})["workers"] == 0
    assert iab.start("/nonexistent", {"impact_any_workers": -3})["workers"] == 0
    assert iab.start("/nonexistent", {"impact_any_workers": 2})["workers"] == 2
    assert iab.start("/nonexistent", {})["workers"] == iab.WORKERS


def test_split_off_reaches_the_pool_processes(tmp_path, isite):
    """SPLIT=false (attrib.ON, set by the build at run time): a spawned pool process imports the engine fresh (ON:
    True) — the job carries the switch, so its files are the in-process ones (no split in them)."""
    data, out = isite
    d1, o1 = str(tmp_path / "data_on"), str(tmp_path / "site_on")
    shutil.copytree(data, d1)
    run(d1, o1, ga4_settings(impact_any_workers=0))                     # (on: the split is in these files)
    iab.pop_line()
    a, b = _twice(tmp_path, data, out, 2, split=False)
    _same(a, b)
    assert _twice.runs == {"pool": 3, "here": 0}
    for split, root in ((True, o1), (False, out + "_b")):
        files = [n for n in os.listdir(root) if iab.FILE_RE.match(n)]
        assert len(files) == 3
        assert all((b'"sp"' in gzip.decompress(open(os.path.join(root, n), "rb").read())) == split for n in files)


def test_split_failures_in_the_pool_are_counted_as_in_process(tmp_path, isite, monkeypatch, capsys):
    """A split builder that raises (attrib.safe: counted in attrib.FAILS, "split failed: N"): the pool processes' count
    comes back with each job — the same N either way, and more than the Uninstall evaluation's own."""
    from admob_iq.engine import attrib
    from tests.uninstall_synth import split_fails
    data, out = isite
    monkeypatch.setattr(attrib, "rate", split_fails)                     # here (A, and B's own evaluation) …
    monkeypatch.setattr(iab, "SWITCHES", iab.SWITCHES + ((attrib, "rate"),))   # … and in each pool process (B)
    d0, o0 = str(tmp_path / "data_0"), str(tmp_path / "site_0")
    shutil.copytree(data, d0)
    run(d0, o0, ga4_settings(impact_any=False))
    base = int(re.findall(r"^split failed: (\d+)$", capsys.readouterr().err, re.M)[-1])
    a, b = _twice(tmp_path, data, out, 2)
    _same(a, b)
    assert _twice.runs == {"pool": 3, "here": 0}
    n = [int(x) for x in re.findall(r"^split failed: (\d+)$", capsys.readouterr().err, re.M)]
    assert len(n) == 2 and n[0] == n[1] > base > 0
    assert attrib.rate is split_fails and attrib.ON is True              # (a job built here restores this process's)


def test_a_step_that_raises_after_apps_were_queued_writes_their_files_and_leaves_no_pool(tmp_path, isite,
                                                                                         monkeypatch):
    """The Uninstall loop raises on the 2nd app (after apps 1 and 2 were handed to the pool): the files the in-process
    build had written by then are written (in app order) before the error goes on, and no pool process is left running
    on the build's CPUs or for the interpreter's exit to wait on."""
    from admob_iq.engine import uninstall as eng
    data, out = isite
    real, seen = eng.cohort_file, {}
    for w in (0, 2):
        d, o, n = str(tmp_path / ("data%d" % w)), str(tmp_path / ("site%d" % w)), []
        shutil.copytree(data, d)

        def cf(store, n=n):
            n.append(1)
            if len(n) == 2:
                raise RuntimeError("synthetic")
            return real(store)
        monkeypatch.setattr(eng, "cohort_file", cf)
        iab.RUNS.update(pool=0, here=0)
        with pytest.raises(RuntimeError):
            run(d, o, ga4_settings(impact_any_workers=w))
        seen[w] = _all(o, d)
        assert not mp.active_children()
        assert iab.RUNS == ({"pool": 2, "here": 0} if w else {"pool": 0, "here": 0})
    assert seen[0].keys() == seen[2].keys() and seen[0] == seen[2]
    assert sum(1 for k in seen[2] if k.startswith("site/impact_any_")) == 2


class _Rec:
    """A stand-in pool that records its shutdown (futures never done: drain must not wait on them when interrupted)."""

    def __init__(self):
        self.down = None

    def submit(self, fn, *a):
        return Future()

    def shutdown(self, **k):
        self.down = k


def test_drain_interrupted_drops_the_queued_jobs_and_shuts_the_pool_down(tmp_path):
    from tests.test_impact_windows import _stores
    acc = iab.start(str(tmp_path), {"impact_any_workers": 2})
    pool = acc["pool"] = _Rec()
    st, rv = next(iter(_stores()))
    st = dict(st, window_end=END.isoformat())
    p = str(tmp_path / "s.json.gz")
    iab.write_json_gz_stable(p, st)
    iab.app_step(acc, str(tmp_path), st, {"app_id": "a"}, "0" * 12, p, rv, 7)
    assert len(acc["jobs"]) == 1
    iab.drain(acc, wait=False)                                           # (a KeyboardInterrupt: nothing waited on)
    assert pool.down == {"wait": False, "cancel_futures": True} and acc["pool"] is False
    assert not [f for f in os.listdir(str(tmp_path)) if f.startswith("impact_any_")]
    acc = iab.start(str(tmp_path), {"impact_any_workers": 2})
    pool = acc["pool"] = _Pool()
    iab.app_step(acc, str(tmp_path), st, {"app_id": "a"}, "0" * 12, p, rv, 7)
    iab.drain(acc)                                                       # (an error: settled as finish() would)
    assert os.listdir(str(tmp_path)).count("impact_any_%s.json.gz" % ("0" * 12)) == 1 and acc["built"] == 1
