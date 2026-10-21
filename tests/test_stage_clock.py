"""The build stage clock (admob_iq/stage_clock.py): where the build's time goes — measure only.

  * nesting and totals: top-level stages (step) cover the run, children (stage / timed) sum into their parent, a
    repeated child is one row with its count;
  * a crashed build still writes its profile (main's finally), the stage it died in marked ok: false (on the runner
    only a good build's push carries the file: each history row's Actions run number shows a failed run as a gap);
  * the rolling history keeps the last 48 builds;
  * local disk / JSON time is its own child row: FileRepo's first read of each file, the install-day file read and
    write next to its GA4 reads (ga4_iday);
  * the PUBLIC lines: "stage <name> <sec>s" only, allow-listed names, no digit but the seconds;
  * the helper never fails the build, and the build's outputs are byte-identical with it on;
  * every stage name the code uses is on the allow-list; the workflow prints the lines and keeps the build's redaction.
All synthetic: no network, no real names or figures."""

import gzip
import json
import os
import re
from datetime import date

import pytest
import yaml

from admob_iq import build_static
from admob_iq import stage_clock as sc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def tick(self, s):
        self.t += s


@pytest.fixture(autouse=True)
def _no_run_left(monkeypatch):
    monkeypatch.delenv("GITHUB_RUN_NUMBER", raising=False)     # (off the runner unless a test sets it)
    sc.finish(None)
    yield
    sc.finish(None)


def _by(prof):
    return {(e.get("parent"), e["name"]): e for e in prof["stages"]}


# ── nesting and totals ──────────────────────────────────────────────────────────────────────────────────────────────
def test_nesting_and_totals(tmp_path):
    c = Clock()
    sc.begin(clock=c)

    @sc.timed("ga4_cube")
    def cube(x):
        c.tick(5)
        return x * 2

    sc.step("setup")
    c.tick(2)
    with sc.stage("site_snapshot"):
        c.tick(3)
    sc.step("admob_fetch")
    c.tick(1)
    for _ in range(3):                                   # once per account: one row, n = 3
        with sc.stage("admob_network"):
            c.tick(4)
    with sc.stage("admob_mediation"):
        with sc.stage("admob_rollup"):                   # a grandchild
            c.tick(1)
        c.tick(1)
    sc.step("ga4")
    assert cube(21) == 42                                # the decorator returns what the function does
    with sc.stage("ga4_cohort"):
        sc.step("tabs")                                  # a top-level mark inside a timed block is ignored
        c.tick(2)
    c.tick(0.5)
    prof = sc.finish(str(tmp_path))

    by = _by(prof)
    assert [e["name"] for e in prof["stages"]] == ["setup", "site_snapshot", "admob_fetch", "admob_network",
                                                   "admob_mediation", "admob_rollup", "ga4", "ga4_cube", "ga4_cohort"]
    assert by[(None, "setup")]["sec"] == 5.0 and by[("setup", "site_snapshot")]["sec"] == 3.0
    net = by[("admob_fetch", "admob_network")]
    assert net["sec"] == 12.0 and net["n"] == 3 and "n" not in by[(None, "admob_fetch")]
    assert by[("admob_fetch", "admob_mediation")]["sec"] == 2.0 and by[("admob_mediation", "admob_rollup")]["sec"] == 1.0
    assert by[(None, "admob_fetch")]["sec"] == 15.0      # its own 1 + 12 + 2
    assert by[(None, "ga4")]["sec"] == 7.5 and by[("ga4", "ga4_cube")]["sec"] == 5.0
    assert by[("ga4", "ga4_cohort")]["sec"] == 2.0
    assert (None, "tabs") not in by
    for (parent, name), e in by.items():                 # a parent's time = Σ children + its own (never less)
        kids = sum(k["sec"] for (p, _n), k in by.items() if p == name)
        assert e["sec"] + 1e-9 >= kids
        assert e["ok"] is True
    assert prof["total_sec"] == 27.5 and prof["unmeasured_sec"] == 0.0
    assert prof["v"] == 1 and prof["ok"] is True and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", prof["at"])
    on_disk = sc.read(os.path.join(str(tmp_path), sc.FILE))
    assert on_disk == prof and on_disk["history"][-1] == sc.history_row(prof)
    assert on_disk["history"][-1]["s"] == {"setup": 5.0, "site_snapshot": 3.0, "admob_fetch": 15.0,
                                           "admob_network": 12.0, "admob_mediation": 2.0, "admob_rollup": 1.0,
                                           "ga4": 7.5, "ga4_cube": 5.0, "ga4_cohort": 2.0}


def test_time_before_the_first_step_is_reported_as_unmeasured(tmp_path):
    c = Clock()
    sc.begin(clock=c)
    c.tick(3)
    sc.step("setup")
    c.tick(2)
    prof = sc.finish(None)
    assert prof["total_sec"] == 5.0 and prof["unmeasured_sec"] == 3.0
    assert not os.listdir(str(tmp_path))                 # data_dir None: nothing written


def test_an_exception_passes_through_and_marks_the_stage(tmp_path):
    c = Clock()
    sc.begin(clock=c)
    sc.step("ga4")
    with pytest.raises(ValueError):
        with sc.stage("ga4_cube"):
            c.tick(1)
            raise ValueError("x")
    with sc.stage("ga4_cohort"):
        c.tick(1)
    prof = sc.finish(str(tmp_path), ok=True)
    by = _by(prof)
    assert by[("ga4", "ga4_cube")]["ok"] is False and by[("ga4", "ga4_cube")]["sec"] == 1.0
    assert by[("ga4", "ga4_cohort")]["ok"] is True and by[(None, "ga4")]["ok"] is True


def test_without_a_run_every_call_is_a_no_op():
    calls = []

    @sc.timed("forecast")
    def f(a, b=2):
        calls.append((a, b))
        return a + b

    assert not sc.active()
    sc.step("setup")
    with sc.stage("forecast"):
        pass
    assert f(1, b=3) == 4 and calls == [(1, 3)] and f.__name__ == "f"
    assert sc.finish("never-written") is None and not os.path.exists("never-written")


# ── a crash still writes ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_crashed_build_still_writes_what_it_measured(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}

    def boom(data_dir="data", **_k):
        seen["data_dir"] = data_dir
        sc.step("setup")
        sc.step("admob_fetch")
        with sc.stage("admob_network"):
            pass
        raise RuntimeError("synthetic")

    monkeypatch.setattr(build_static, "build", boom)
    with pytest.raises(RuntimeError):
        build_static.main()
    assert seen["data_dir"] == "data"
    prof = sc.read(os.path.join(str(tmp_path), "data", sc.FILE))
    assert prof["ok"] is False and not sc.active()
    by = _by(prof)
    assert by[(None, "admob_fetch")]["ok"] is False      # the stage it died in
    assert by[(None, "setup")]["ok"] is True and by[("admob_fetch", "admob_network")]["ok"] is True
    assert prof["stages"][0]["name"] in ("python_start", "imports")   # the run starts at the module's import
    assert (None, "imports") in by
    assert prof["history"][-1]["ok"] is False and len(prof["history"]) == 1


def test_a_good_main_writes_and_prints_as_before(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(build_static, "build", lambda data_dir="data", **_k: {"mode": "mock"})
    build_static.main()
    assert capsys.readouterr().out == "build complete: {'mode': 'mock'}\n"
    prof = sc.read(os.path.join(str(tmp_path), "data", sc.FILE))
    assert prof["ok"] is True and prof["total_sec"] >= prof["stages"][-1]["sec"]


# ── history ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_history_keeps_the_last_48_builds(tmp_path):
    d = str(tmp_path)
    for i in range(1, 51):
        c = Clock()
        sc.begin(clock=c)
        sc.step("admob_fetch")
        c.tick(i)
        sc.step("deploy_guard")
        c.tick(0.4)                                      # under HISTORY_MIN_SEC: not in the compact row
        sc.finish(d)
    prof = sc.read(os.path.join(d, sc.FILE))
    h = prof["history"]
    assert len(h) == sc.HISTORY_KEEP == 48
    assert [r["s"]["admob_fetch"] for r in h] == [float(i) for i in range(3, 51)]
    assert all(set(r) == {"at", "ok", "total", "s"} and set(r["s"]) == {"admob_fetch"} for r in h)
    assert h[-1]["total"] == prof["total_sec"] == 50.4
    raw = open(os.path.join(d, sc.FILE), "rb").read()
    assert raw[4:8] == b"\x00\x00\x00\x00" and len(raw) < 4096      # deterministic gzip (no mtime), small


def test_each_row_carries_the_actions_run_number_so_a_failed_run_shows_as_a_gap(tmp_path, monkeypatch):
    d = str(tmp_path)
    for run in ("101", "103"):                           # run 102 failed: its file never reached the private repo
        monkeypatch.setenv("GITHUB_RUN_NUMBER", run)
        sc.begin(clock=Clock())
        sc.step("setup")
        sc.finish(d)
    prof = sc.read(os.path.join(d, sc.FILE))
    assert prof["run"] == 103 and [h["run"] for h in prof["history"]] == [101, 103]
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "\u00b2")            # not a plain number: no "run", still timed
    sc.begin(clock=Clock())
    sc.step("setup")
    prof = sc.finish(d)
    assert "run" not in prof and "run" not in prof["history"][-1] and len(prof["history"]) == 3


def test_a_damaged_profile_starts_a_fresh_history(tmp_path):
    d = str(tmp_path)
    with open(os.path.join(d, sc.FILE), "wb") as f:
        f.write(b"not gzip")
    sc.begin(clock=Clock())
    sc.step("setup")
    sc.finish(d)
    assert len(sc.read(os.path.join(d, sc.FILE))["history"]) == 1


# ── the helper never fails the build ────────────────────────────────────────────────────────────────────────────────
def test_the_helper_never_fails_the_build(tmp_path, monkeypatch):
    def bad(*_a, **_k):
        raise OSError("synthetic")

    sc.begin(clock=bad)                                  # a clock that fails: no run, nothing raised
    assert not sc.active()

    sc.begin(clock=Clock())
    monkeypatch.setattr(sc._Run, "open", bad)
    monkeypatch.setattr(sc._Run, "close", bad)

    @sc.timed("forecast")
    def f():
        return "same"

    sc.step("setup")
    with sc.stage("site_snapshot"):
        x = 7
    assert f() == "same" and x == 7
    monkeypatch.undo()

    sc.begin(clock=Clock())
    sc.step("setup")
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where the data dir should be")
    prof = sc.finish(str(blocker / "data"))              # the write fails: still no exception, the profile returned
    assert prof is not None and prof["stages"][0]["name"] == "setup"

    sc.begin(clock=Clock())
    monkeypatch.setattr(sc._Run, "profile", bad)
    assert sc.finish(str(tmp_path)) is None and not sc.active()


def test_another_thread_is_never_timed():
    import threading
    c = Clock()
    sc.begin(clock=c)
    sc.step("ga4")

    def work():
        with sc.stage("ga4_cube"):
            c.tick(1)
        sc.step("tabs")

    t = threading.Thread(target=work)
    t.start()
    t.join()
    prof = sc.finish(None)
    assert [e["name"] for e in prof["stages"]] == ["ga4"]


# ── local disk / JSON time: its own rows ───────────────────────────────────────────────────────────────────────────
_NET = {"account_id": "acct-x", "app_id": "app-x", "ad_unit_id": "unit-x", "country": "ZZ", "format": "f",
        "platform": "p", "estimated_earnings_micros": 1}


def _repo_ops(repo, day):
    row = dict(_NET, report_date=day)
    repo.upsert_network(dict(row))
    repo.append_snapshot(dict(row, snapshot_date=day))
    repo.upsert_mediation(dict(row, ad_source="src-x"))


def test_a_history_files_first_read_is_its_own_row_under_the_stage_that_touched_it(tmp_path, monkeypatch):
    """FileRepo reads a file when it is first used (gunzip + parse + key map). That is booked as repo_load_<file>
    under the stage that touched it (not as the AdMob report's own time), once per file, and changes nothing."""
    from admob_iq import db
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):                                     # the same history on disk in both
        r0 = db.FileRepo(str(d))
        for day in ("2026-01-01", "2026-01-02"):
            _repo_ops(r0, day)
        r0.flush()

    def run(d):
        r = db.FileRepo(str(d))
        sc.step("admob_fetch")
        with sc.stage("admob_network"):
            for day in ("2026-01-02", "2026-01-03", "2026-01-04"):
                r.upsert_network(dict(_NET, report_date=day))
                r.append_snapshot(dict(_NET, report_date=day, snapshot_date="2026-01-05"))
        with sc.stage("admob_rollup"):
            r.fetch_adunit_country_monthly()
        sc.step("dashboard_build")
        n = len(r.fetch_network())                       # loaded already: no second read
        r.fetch_country()                                # first touched here
        r.flush()
        return n

    assert run(a) == 4                                   # (the clock off: no run)
    c = Clock()
    orig = db._read_json_any

    def slow_read(path):                                 # a read that takes 2 s on the fake clock
        c.tick(2)
        return orig(path)

    monkeypatch.setattr(db, "_read_json_any", slow_read)
    sc.begin(clock=c)
    assert run(b) == 4
    prof = sc.finish(None)
    monkeypatch.undo()

    by = _by(prof)
    for parent, name in (("admob_network", "repo_load_network"), ("admob_network", "repo_load_snapshots"),
                         ("admob_rollup", "repo_load_adunit_country_monthly"),
                         ("dashboard_build", "repo_load_country")):
        e = by[(parent, name)]
        assert e["sec"] == 2.0 and "n" not in e and e["ok"], name           # once per file, never per row
    assert by[("admob_fetch", "admob_network")]["sec"] == 4.0                # = its two first reads, nothing more
    assert by[(None, "dashboard_build")]["sec"] == 2.0
    assert not [k for k in by if k[1] == "repo_load_mediation"]             # never touched: never read
    assert _tree(str(a)) == _tree(str(b))                                   # the same files


def test_the_install_day_reads_are_their_own_rows_and_change_nothing(tmp_path, monkeypatch):
    """The install-day (install value) reads inside each due app's GA4 fetch: ga4_iday (with its file read
    ga4_iday_load and write ga4_iday_save) under ga4_uninstall_fetch, one row each summed over the apps; every file
    the fetch writes byte-identical with the clock on."""
    from tests.test_ga4_iday import World, _files
    off, on = tmp_path / "off", tmp_path / "on"
    World(monkeypatch).run(off, cfg={"iday": True})
    w = World(monkeypatch)
    sc.begin()
    sc.step("ga4")
    with sc.stage("ga4_uninstall_fetch"):
        out = w.run(on, cfg={"iday": True})
    prof = sc.finish(None)
    fa, fb = _files(off), _files(on)
    assert len(fa) > 3 and fa == fb
    assert out["iday"]["apps"] == 2
    by = _by(prof)
    for name in ("ga4_iday_load", "ga4_iday", "ga4_iday_save"):
        e = by[("ga4_uninstall_fetch", name)]
        assert e["ok"] and e.get("n") == 2, name
    kids = sum(e["sec"] for (p, _n), e in by.items() if p == "ga4_uninstall_fetch")
    assert by[("ga4", "ga4_uninstall_fetch")]["sec"] + 1e-9 >= kids
    _check_public(sc.public_lines(prof, min_sec=0))


# ── the public lines ────────────────────────────────────────────────────────────────────────────────────────────────
LINE = re.compile(r"stage ([a-z][a-z0-9_]*) (\d+)s")


def _check_public(lines):
    allowed = set(sc.STAGES) | set(sc.META)
    for ln in lines:
        m = LINE.fullmatch(ln)
        assert m, ln
        name, sec = m.groups()
        assert name in allowed, ln
        rest = ln.replace("stage %s " % name, "", 1)
        assert re.findall(r"\d+", rest) == [sec], ln       # no digit but the seconds
        assert not re.search(r"ca-app|pub-|com\.|\$|₹|@|/|\.json", ln)


def test_public_lines_are_allow_listed_names_and_whole_seconds():
    prof = {"total_sec": 1500.4, "stages": [
        {"name": "python_start", "sec": 0.2, "ok": True},
        {"name": "admob_fetch", "sec": 312.6, "ok": True},
        {"name": "admob_network", "sec": 19.9, "parent": "admob_fetch", "ok": True, "n": 4},
        {"name": "ga4_cube", "sec": 20.0, "parent": "ga4", "ok": True},
        {"name": "forecast", "sec": 151.2, "parent": "roi_apps", "ok": True, "n": 37},
        {"name": "com.example.someapp", "sec": 99.0, "ok": True},            # never an app / package
        {"name": "ca-app-pub-0000000000000000~0000000000", "sec": 50.0, "ok": True},
        {"name": "revenue_123_45", "sec": 60.0, "ok": True},                # not on the list
        {"name": "ga4", "sec": True, "ok": True},                           # not a number
        {"name": "deploy_guard", "sec": float("nan"), "ok": True},
    ]}
    lines = sc.public_lines(prof, wall=1504.6)
    assert lines == ["stage total 1500s", "stage admob_fetch 313s", "stage ga4_cube 20s", "stage forecast 151s",
                     "stage step_wall 1505s", "stage outside_build 4s"]
    _check_public(lines)
    assert sc.public_lines({"total_sec": 5.0, "stages": []}) == ["stage total 5s"]
    assert sc.public_lines({"stages": [{"name": "setup", "sec": 30}]}, wall=2.0) == ["stage setup 30s",
                                                                                     "stage step_wall 2s"]


def test_every_allow_listed_name_is_a_code_identifier():
    for name in set(sc.STAGES) | set(sc.META):
        assert sc.NAME_RE.match(name), name
    assert len(set(sc.STAGES)) == len(sc.STAGES)


def _wall(path, start, end=None):
    with open(path, "w", encoding="utf-8") as f:
        f.write("%.6f\n" % start + ("%.6f\n" % end if end is not None else ""))


def test_the_cli_prints_this_runs_lines_and_flags_a_profile_from_an_older_run(tmp_path, capsys):
    from datetime import datetime, timezone
    d = str(tmp_path)
    sc.begin(clock=Clock())
    sc.step("ga4")
    sc.finish(d)
    prof = sc.read(os.path.join(d, sc.FILE))
    at = datetime.strptime(prof["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    wall = os.path.join(d, "build_wall")

    _wall(wall, at - 1.5, at + 30.25)                    # this run (its "at" is after the step began)
    assert sc.main(["public", os.path.join(d, sc.FILE), wall]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["stage total 0s", "stage step_wall 32s", "stage outside_build 32s"]
    _check_public(out)

    _wall(wall, at + 3600)                               # an older run's file (the build died before writing)
    sc.main(["public", os.path.join(d, sc.FILE), wall])
    assert capsys.readouterr().out == "::warning::build profile not written this run\n"

    sc.main(["public", os.path.join(d, sc.FILE), os.path.join(d, "no_wall")])     # the build step never ran
    assert capsys.readouterr().out == "::warning::build profile not written this run\n"
    sc.main(["public", os.path.join(d, "missing.json.gz")])
    assert capsys.readouterr().out == "::warning::build profile not written this run\n"
    sc.main(["public", os.path.join(d, sc.FILE)])                                 # no wall file given: as it is
    assert capsys.readouterr().out == "stage total 0s\n"
    assert sc.main([]) == 0 and sc.main(["other", "x"]) == 0 and capsys.readouterr().out == ""


def test_read_wall():
    assert sc.read_wall("/nonexistent/wall") == (None, None)


def test_proc_age_reads_the_process_start_from_proc():
    fields = ["S"] + ["0"] * 18 + ["5000"] + ["0"] * 10              # field 3 … : field 22 = 5000 ticks
    stat = "4242 (py (x) y) " + " ".join(fields)
    assert sc.proc_age(stat, "100.50 200.00", 100) == pytest.approx(50.5)
    assert sc.proc_age("garbage", "1", 100) is None


# ── wiring ──────────────────────────────────────────────────────────────────────────────────────────────────────────
USE = re.compile(r"_sc\.(?:step|stage|timed)\(\"([^\"]+)\"\)")


def test_every_stage_name_the_code_uses_is_on_the_allow_list():
    from admob_iq.db import FileRepo
    used = set(FileRepo.LOAD_STAGES.values())            # (FileRepo's first reads: named per file, below)
    for base, _dirs, names in os.walk(os.path.join(ROOT, "admob_iq")):
        for n in names:
            if n.endswith(".py"):
                with open(os.path.join(base, n), encoding="utf-8") as f:
                    used |= set(USE.findall(f.read()))
    assert used <= set(sc.STAGES), used - set(sc.STAGES)
    repo = FileRepo("unused")
    assert set(FileRepo.LOAD_STAGES) == set(repo._path) | set(repo._ac_path)    # every history file has its name
    assert set(sc.STAGES) - used == {"python_start", "imports"}     # (begin adds those two) — no stale names


def test_build_static_imports_the_clock_first_and_main_writes_in_a_finally():
    src = open(build_static.__file__, encoding="utf-8").read()
    assert src.index("from . import stage_clock as _sc") < src.index("from .config import")
    body = src[src.index("def build("):src.index("def main(")]
    assert body.index('_sc.step("setup")') < body.index("_guard_snapshot(out_dir)")
    assert body.index('_sc.step("deploy_guard")') < body.index("_deploy_guard_step(out_dir, guard_prev)") \
        < body.index('_sc.step("teardown")') < body.index("return {")
    main = src[src.index("def main("):]
    assert "_sc.begin(imports=True)" in main and "finally:\n        _sc.finish(data_dir, ok=ok)" in main


def _steps():
    with open(os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["jobs"]["refresh"]["steps"]


def test_the_workflow_prints_the_stage_lines_after_the_build_and_keeps_its_redaction():
    steps = _steps()
    b = next(i for i, s in enumerate(steps) if s.get("name") == "Build dashboard + send alerts")
    build = steps[b]["run"]
    assert "python -m admob_iq.build_static > /tmp/build.log 2>&1" in build          # output still never logged
    assert "tail -n 30 /tmp/build.log | sed -E 's/[0-9]+\\.[0-9]+/#.##/g; s/[0-9]{4,}/####/g'" in build
    assert build.index("date +%s.%N > /tmp/build_wall") < build.index("python -m admob_iq.build_static")
    assert build.count("date +%s.%N >> /tmp/build_wall") == 2                        # success and failure
    t = steps[b + 1]
    assert t["name"].startswith("Build time per stage")
    assert t["if"] == "always()" and t["continue-on-error"] is True
    assert t["run"].strip() == ("python -m admob_iq.stage_clock public data/build_profile.json.gz /tmp/build_wall "
                                "2>/dev/null || true")
    assert "env" not in t and "secrets." not in json.dumps(t)
    # a failed build's profile is never pushed on its own: no step that runs after a failure pushes anything
    for s in steps:
        cond = str(s.get("if") or "")
        if "always()" in cond or "failure()" in cond:
            assert "git push" not in str(s.get("run") or ""), s.get("name")
    assert "failed run could look like a fresh refresh" in open(
        os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8").read()


# ── outputs unchanged ───────────────────────────────────────────────────────────────────────────────────────────────
def _tree(root, skip=()):
    out = {}
    for base, _dirs, names in os.walk(root):
        for n in names:
            p = os.path.join(base, n)
            rel = os.path.relpath(p, root)
            if rel in skip:
                continue
            raw = open(p, "rb").read()
            if n.endswith(".gz"):
                raw = gzip.decompress(raw)                # (FileRepo's own gzip headers carry the write time)
            if n.startswith("dashboard.json"):
                d = json.loads(raw)
                d.pop("generated_at", None)               # the build's own clock
                raw = json.dumps(d, sort_keys=True).encode()
            out[rel] = raw
    return out


def test_a_build_makes_the_same_outputs_with_the_clock_on(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build_static.build(out_dir=str(a / "site"), data_dir=str(a / "data"), today=date(2026, 7, 23), mode="mock")
    sc.begin()
    build_static.build(out_dir=str(b / "site"), data_dir=str(b / "data"), today=date(2026, 7, 23), mode="mock")
    prof = sc.finish(str(b / "data"))
    assert _tree(str(a / "site")) == _tree(str(b / "site"))
    assert _tree(str(a / "data")) == _tree(str(b / "data"), skip=(sc.FILE,))
    assert sorted(os.listdir(str(b / "data"))) == sorted(os.listdir(str(a / "data")) + [sc.FILE])

    by = _by(prof)
    top = [e["name"] for e in prof["stages"] if "parent" not in e]
    assert top[:3] == ["setup", "admob_fetch", "repo_flush"] and top[-3:] == ["alerts", "deploy_guard", "teardown"]
    assert ("setup", "site_snapshot") in by and ("admob_fetch", "admob_network") in by
    assert by[("admob_network", "repo_load_network")].get("n", 1) == 1      # each file's first read: its own row, once
    assert ("admob_network", "repo_load_snapshots") in by and ("admob_mediation", "repo_load_mediation") in by
    assert ("tabs", "uninstall_studio") in by and ("tabs", "firstopen_tab") in by
    assert all(e["ok"] for e in prof["stages"]) and prof["ok"] is True
    assert prof["unmeasured_sec"] <= 0.1 + 0.01 * prof["total_sec"]
    _check_public(sc.public_lines(prof, min_sec=0))


def _bytes(root):
    out = {}
    for base, _dirs, names in os.walk(root):
        for n in names:
            p = os.path.join(base, n)
            raw = open(p, "rb").read()
            rel = os.path.relpath(p, root)
            if n == "dashboard.json.gz":                 # (the synthetic builder's own gzip.open: its header has a time)
                raw = gzip.decompress(raw)
            if rel.startswith(os.path.join("data", "forecast") + os.sep) and n.endswith(".json"):
                d = json.loads(raw)                      # a forecast tune's measured seconds: the wall clock, never
                d.pop("tune_sec", None)                  # the data (as tests/test_adcfg_build.py) — it jitters run to
                raw = json.dumps(d, sort_keys=True).encode()    # run with or without the stage clock
            out[rel] = raw
    return out


def test_the_ga4_steps_make_the_same_files_with_the_clock_on(tmp_path):
    """The real Uninstall / Active / Install value / ROI + forecast step on the synthetic site (tests/value_studio_synth):
    every site and data file byte-identical with the clock on, and its stages nested under the top-level one."""
    from tests import value_studio_synth as vss
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    vss.make_site(str(a))
    sc.begin()
    sc.step("ga4")
    vss.make_site(str(b))
    prof = sc.finish(None)
    ta, tb = _bytes(str(a)), _bytes(str(b))
    assert len(ta) > 20 and ta == tb

    by = _by(prof)
    for name in ("ga4_uninstall_fetch", "active_prepass", "value_prepass", "uninstall_store_load", "uninstall_eval",
                 "active_apps", "value_apps", "roi_apps", "cohort_files", "uninstall_asset", "active_finish",
                 "value_finish", "roi_finish"):
        assert ("ga4", name) in by and by[("ga4", name)]["ok"], name
    assert ("roi_apps", "forecast") in by
    n_apps = by[("ga4", "uninstall_eval")].get("n", 1)
    assert n_apps >= 2 and by[("ga4", "value_apps")].get("n", 1) == n_apps     # one row, summed over the apps
    kids = sum(e["sec"] for (p, _n), e in by.items() if p == "ga4")
    assert by[(None, "ga4")]["sec"] + 1e-9 >= kids
    _check_public(sc.public_lines(prof, min_sec=0))
