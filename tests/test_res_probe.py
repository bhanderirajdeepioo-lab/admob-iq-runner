"""The runner's resource probe (admob_iq/res_probe.py): the machine's memory, swap, memory pressure, OOM kills and free
disk, the build's own memory and swap and the stage it is in, on the PUBLIC Actions log while the build runs — measure
only.

  * the line shapes: numbers, "?" / "-" and stage identifiers only — no process name, path or anything else read from
    /proc or the stage file ever reaches a line;
  * the build's memory and swap = every process under --parent (the build step's shell) except the probe itself; once
    the shell is gone and the build runs on re-parented (a runner shutdown), the build's processes by their last pids;
  * memory pressure (/proc/pressure/memory avg10) and the OOM-kill count (/proc/vmstat oom_kill): parsed, or "?";
  * the peak line: the samples' max / min, the stage at the most build RSS + swap, the sample count;
  * it samples at once and every interval, and stops on SIGTERM / SIGINT or the parent's exit, both with one last
    sample — also when the shell dies first, with or without the same SIGTERM, as in a runner kill — always exiting 0;
    no /proc (this Mac): one "res unavailable" line; it never raises;
  * what it prints as the stage is what the stage clock keeps in STAGE_NOW_FILE;
  * the build step starts it before the build, stops it after in both branches, prints the OOM-kill count and keeps
    its exit logic: run here with bash -e (GitHub's default shell), the build swapped for a stand-in.
All against a fake /proc tree and stand-ins: no real process, name or figure."""

import io
import os
import re
import shutil
import signal
import subprocess
import sys
import threading

import pytest
import yaml

from admob_iq import res_probe as rp
from admob_iq import stage_clock as sc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = 1024                                                # kB in an MB

NUM = r"(?:\d+|\?)"
STG = r"(?:[a-z][a-z0-9_]*(?:/[a-z][a-z0-9_]*)*|-|\?)"
SHAPES = (
    re.compile(r"res machine cpus=%s mem_total_mb=%s swap_total_mb=%s disk_total_mb=%s disk_free_mb=%s oom_kills=%s"
               % ((NUM,) * 6)),
    re.compile(r"res t=\d+ stage=%s used_mb=%s avail_mb=%s swap_used_mb=%s mem_some10=%s mem_full10=%s "
               r"build_rss_mb=%s build_swap_mb=%s disk_free_mb=%s oom_kills=%s" % ((STG,) + (NUM,) * 9)),
    re.compile(r"res peak used_mb=%s min_avail_mb=%s max_swap_mb=%s max_some10=%s max_full10=%s max_build_mb=%s "
               r"at_stage=%s max_build_rss_mb=%s min_disk_free_mb=%s samples=\d+" % ((NUM,) * 6 + (STG,) + (NUM,) * 2)),
    re.compile(r"res unavailable"),
    re.compile(r"res oom_kills=(?:\d+|\?)"),
)
SECRET = "com.example.secretapp"                         # a process name: never printed


def _public(lines, *never):
    """Every line one of the probe's shapes; nothing read from /proc (names, paths) in any of them."""
    for ln in lines:
        assert any(s.fullmatch(ln) for s in SHAPES), ln
        assert "/" not in re.sub(r"\b(?:at_)?stage=\S+", "", ln), ln          # a "/" only inside a stage path
        for word in (SECRET, "python", "bash", "Runner", "Fake CPU") + never:
            assert word not in ln, ln


@pytest.fixture(autouse=True)
def _fresh():
    """No stop signal left over, and the session's own signal handlers back after a test that ran main()."""
    saved = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
    del rp._STOP[:]
    sc.finish(None)
    yield
    for s, h in saved.items():
        signal.signal(s, h)
    del rp._STOP[:]
    sc.finish(None)


# ── a fake /proc ────────────────────────────────────────────────────────────────────────────────────────────────────
SHELL, ME, BUILD = 100, 101, 102
TREE = (                                                 # (pid, ppid, comm, VmRSS MB, VmSwap MB)
    (1, 0, "systemd", 12, 0),
    (SHELL, 1, "bash", 4, 8),                            # the build step's shell (--parent): not counted
    (ME, SHELL, "python3", 15, 16),                      # the probe itself: not counted
    (BUILD, SHELL, "python", 3072, 256),                 # the build
    (103, BUILD, "py (worker) 1", 512, 64),              # its workers (a name with spaces and brackets)
    (104, 103, SECRET, 256, 0),                          # … and theirs
    (105, BUILD, "defunct", None, None),                 # a zombie: no VmRSS, no VmSwap
    (200, 1, "Runner.Worker", 300, 50),                  # outside the step: not counted
    (201, 200, "node", 100, 0),
)
B_RSS, B_SWAP = 3072 + 512 + 256, 256 + 64               # the build's figures in TREE: 3840 and 320 MB


def _write(path, text):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as f:
        f.write(text)


def set_proc(root, pid, ppid, comm, rss_mb, swap_mb=0, state="S"):
    _write(root / str(pid) / "stat", "%d (%s) %s %d %d %d 0 -1 4194560 120 0 0 0 7 3 0 0 20 0 1 0 4242 9999 99\n"
           % (pid, comm, state, ppid, pid, pid))
    vm = ("VmPeak:\t99999999 kB\nVmRSS:\t%8d kB\nVmData:\t88888888 kB\nVmSwap:\t%8d kB\n"
          % (rss_mb * KB, swap_mb * KB) if rss_mb is not None else "")
    _write(root / str(pid) / "status", "Name:\t%s\nState:\t%s\nPid:\t%d\nPPid:\t%d\n%sThreads:\t1\n"
           % (comm, state, pid, ppid, vm))


def reparent(root, pid, ppid):
    """What the kernel does to a process whose parent died: only its parent changes (pid 1 or a subreaper)."""
    stat = root / str(pid) / "stat"
    st = stat.read_text()
    cut = st.rindex(")") + 2
    rest = st[cut:].split(" ")
    rest[1] = str(ppid)
    stat.write_text(st[:cut] + " ".join(rest))
    status = root / str(pid) / "status"
    status.write_text(re.sub(r"(?m)^PPid:\t\d+$", "PPid:\t%d" % ppid, status.read_text()))


def set_mem(root, total=16384, avail=6144, swap=4096, swap_free=3072):
    _write(root / "meminfo", "MemTotal:       %d kB\nMemFree:          %d kB\nMemAvailable:   %d kB\nBuffers:  12 kB\n"
           "SwapTotal:      %d kB\nSwapFree:       %d kB\n" % (total * KB, 999 * KB, avail * KB, swap * KB,
                                                                 swap_free * KB))


def set_pressure(root, some=1.6, full=0.7):
    _write(root / "pressure" / "memory", "some avg10=%.2f avg60=0.80 avg300=0.20 total=123456\n"
           "full avg10=%.2f avg60=0.40 avg300=0.10 total=65432\n" % (some, full))


def set_ooms(root, n=0):
    _write(root / "vmstat", "nr_free_pages 255\npgfault 9999\noom_kill %d\nnr_unstable 0\n" % n)


def fake_proc(root, procs=TREE, cpus=4, **mem):
    """A fake /proc: meminfo (MB given), memory pressure (some 1.6 %, full 0.7 %), vmstat (no OOM kill yet), cpuinfo,
    and one <pid>/stat + status per (pid, ppid, comm, VmRSS MB, VmSwap MB)."""
    set_mem(root, **mem)
    set_pressure(root)
    set_ooms(root)
    _write(root / "cpuinfo", "".join("processor\t: %d\nmodel name\t: Fake CPU 9000\n\n" % i for i in range(cpus)))
    for pid, ppid, comm, rss, swap in procs:
        set_proc(root, pid, ppid, comm, rss, swap)
    os.makedirs(str(root / "self"), exist_ok=True)       # not a pid: skipped
    return root


def _disk(monkeypatch, total=73000, free=21000):
    monkeypatch.setattr(rp, "disk_mb", lambda path: (total, free))


# ── the lines ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_lines_are_numbers_and_stage_names_only(tmp_path, monkeypatch):
    proc = fake_proc(tmp_path / "proc")
    stage = tmp_path / "stage_now"
    stage.write_text("ga4/roi_apps/roi_device")
    _disk(monkeypatch)
    t = [500.0]
    p = rp.Probe(str(proc), SHELL, str(stage), str(tmp_path), me=ME, clock=lambda: t[0])
    lines = [p.machine(), p.sample()]
    t[0] += 30.4
    set_mem(proc, avail=2048, swap_free=1024)
    set_proc(proc, BUILD, SHELL, "python", 6000, 1000)
    set_pressure(proc, some=35.2, full=12.6)
    set_ooms(proc, 1)
    stage.write_text("ga4/roi_apps/roi_country")
    lines += [p.sample(), p.peak()]
    assert lines == [
        "res machine cpus=4 mem_total_mb=16384 swap_total_mb=4096 disk_total_mb=73000 disk_free_mb=21000 oom_kills=0",
        # used = MemTotal − MemAvailable; pressure = avg10, rounded; build = 3072 + 512 + 256 + 0 MB resident and
        # 256 + 64 MB swapped (the shell, the probe and the rest not counted)
        "res t=0 stage=ga4/roi_apps/roi_device used_mb=10240 avail_mb=6144 swap_used_mb=1024 mem_some10=2 "
        "mem_full10=1 build_rss_mb=3840 build_swap_mb=320 disk_free_mb=21000 oom_kills=0",
        "res t=30 stage=ga4/roi_apps/roi_country used_mb=14336 avail_mb=2048 swap_used_mb=3072 mem_some10=35 "
        "mem_full10=13 build_rss_mb=6768 build_swap_mb=1064 disk_free_mb=21000 oom_kills=1",
        "res peak used_mb=14336 min_avail_mb=2048 max_swap_mb=3072 max_some10=35 max_full10=13 max_build_mb=7832 "
        "at_stage=ga4/roi_apps/roi_country max_build_rss_mb=6768 min_disk_free_mb=21000 samples=2"]
    _public(lines, str(tmp_path))


def test_the_peak_line_keeps_the_max_the_min_and_the_stage_at_the_most_build_memory(tmp_path, monkeypatch):
    proc = fake_proc(tmp_path / "proc")
    stage = tmp_path / "stage_now"
    free = [21000]
    monkeypatch.setattr(rp, "disk_mb", lambda path: (73000, free[0]))
    p = rp.Probe(str(proc), SHELL, str(stage), str(tmp_path), me=ME, clock=lambda: 0.0)
    assert p.peak() == ("res peak used_mb=? min_avail_mb=? max_swap_mb=? max_some10=? max_full10=? max_build_mb=? "
                        "at_stage=- max_build_rss_mb=? min_disk_free_mb=? samples=0")
    for avail, swap_free, rss, swap, some, full, disk, st in (
            (6144, 3072, 3072, 0, 1.0, 0.0, 21000, "ga4/roi_apps/roi_device"),
            (1500, 2000, 9000, 0, 20.0, 5.0, 20000, "ga4/roi_apps/roi_country"),     # the most build RSS
            (1200, 500, 8000, 3000, 60.4, 41.6, 19000, "tabs/source_tab"),          # the most build RSS + swap
            (900, 3500, 1000, 0, 2.0, 0.0, 18000, "tabs/nvr_tab")):                 # the least memory and disk free
        set_mem(proc, avail=avail, swap_free=swap_free)
        set_proc(proc, BUILD, SHELL, "python", rss, swap)
        set_pressure(proc, some, full)
        free[0] = disk
        stage.write_text(st)
        p.sample()
    os.remove(str(proc / "meminfo"))                     # unreadable now: "?" in its line, the peaks kept
    os.remove(str(proc / "pressure" / "memory"))
    os.remove(str(proc / "vmstat"))
    free[0] = None
    for pid in (BUILD, 103, 104, 105):                   # the build gone: nothing under the shell but the probe
        shutil.rmtree(str(proc / str(pid)))
    assert p.sample() == ("res t=0 stage=tabs/nvr_tab used_mb=? avail_mb=? swap_used_mb=? mem_some10=? mem_full10=? "
                          "build_rss_mb=0 build_swap_mb=0 disk_free_mb=? oom_kills=?")
    # max_build: 8768 resident + 3064 swapped at tabs/source_tab beats 9768 + 64 at roi_country (the most RSS alone)
    assert p.peak() == ("res peak used_mb=15484 min_avail_mb=900 max_swap_mb=3596 max_some10=60 max_full10=42 "
                        "max_build_mb=11832 at_stage=tabs/source_tab max_build_rss_mb=9768 min_disk_free_mb=18000 "
                        "samples=5")


def test_a_value_it_cannot_read_prints_a_question_mark(tmp_path, monkeypatch):
    proc = fake_proc(tmp_path / "proc", cpus=0)
    _write(proc / "meminfo", "garbage\nMemTotal: lots kB\nMemAvailable:\n")
    _write(proc / "vmstat", "nr_free_pages 12\noom_kill lots\n")
    _write(proc / "pressure" / "memory", "some avg10=lots avg60=0.00\nfull total=7\n")
    monkeypatch.setattr(rp, "disk_mb", lambda path: (None, None))
    monkeypatch.setattr(rp.os, "cpu_count", lambda: None)
    p = rp.Probe(str(proc), None, None, str(tmp_path), me=ME, clock=lambda: 0.0)     # no parent: no build figure
    assert p.machine() == ("res machine cpus=? mem_total_mb=? swap_total_mb=? disk_total_mb=? disk_free_mb=? "
                           "oom_kills=?")
    assert p.sample() == ("res t=0 stage=- used_mb=? avail_mb=? swap_used_mb=? mem_some10=? mem_full10=? "
                          "build_rss_mb=? build_swap_mb=? disk_free_mb=? oom_kills=?")
    assert p.peak() == ("res peak used_mb=? min_avail_mb=? max_swap_mb=? max_some10=? max_full10=? max_build_mb=? "
                        "at_stage=- max_build_rss_mb=? min_disk_free_mb=? samples=1")


@pytest.mark.parametrize("text, shown", [
    ("some avg10=1.60 avg60=0.80 avg300=0.20 total=123456\nfull avg10=0.70 avg60=0.40 avg300=0.10 total=65432\n",
     (2, 1)),
    ("some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n", (0, 0)),
    ("some avg10=99.90 avg60=1 avg300=1 total=1\nfull avg10=100.00 avg60=1 avg300=1 total=1\n", (100, 100)),
    ("full avg10=7.40 avg60=1 avg300=1 total=1\nsome avg10=12.60 avg60=1 avg300=1 total=1\n", (13, 7)),  # any order
    ("some avg10=3.00 avg60=1 avg300=1 total=1\n", (3, None)),                     # no "full" line
    ("some avg60=3.00 total=1\nfull avg10=x total=1\n", (None, None)),             # no avg10 / not a number
    ("some avg10=nan\nfull avg10=-1.00\n", (None, None)),
    ("some avg10=100.01\nfull avg10=inf\n", (None, None)),                         # outside 0-100
    ("cpu avg10=50.00\nsomething avg10=9.00\n", (None, None)),
    (None, (None, None)),                                                          # no file (no PSI)
])
def test_memory_pressure_is_avg10_in_whole_percent_or_none(tmp_path, text, shown):
    if text is not None:
        _write(tmp_path / "pressure" / "memory", text)
    assert rp.pressure(str(tmp_path)) == shown
    os.makedirs(str(tmp_path / "dir" / "pressure" / "memory"))                    # unreadable (a folder)
    assert rp.pressure(str(tmp_path / "dir")) == (None, None)


@pytest.mark.parametrize("text, shown", [
    ("nr_free_pages 255\npgfault 9999\noom_kill 0\nnr_unstable 0\n", 0),
    ("oom_kill 7\n", 7),
    ("oom_kill 3 \n", 3),
    ("nr_free_pages 255\n", None),                                                 # a kernel before 4.13: no field
    ("oom_kill lots\n", None),
    ("oom_kill -1\n", None),
    ("oom_killed 5\nx_oom_kill 6\n", None),                                        # only that exact field
    (None, None),                                                                  # no file
])
def test_the_oom_kill_count_is_vmstats_oom_kill_or_none(tmp_path, text, shown):
    if text is not None:
        _write(tmp_path / "vmstat", text)
    assert rp.oom_kills(str(tmp_path)) == shown


def test_the_disk_is_the_file_system_of_the_workspace(tmp_path):
    total, free = rp.disk_mb(str(tmp_path))
    assert isinstance(total, int) and isinstance(free, int) and 0 <= free <= total
    assert rp.disk_mb(str(tmp_path / "missing")) == (None, None)


# ── the build: every process under the parent but the probe ─────────────────────────────────────────────────────────
def test_the_build_is_every_process_under_the_parent_but_the_probe(tmp_path):
    proc = fake_proc(tmp_path / "proc")
    _write(proc / "300" / "stat", "garbage")             # unreadable / gone mid-walk: left out
    os.makedirs(str(proc / "301"))
    ppids = rp.processes(str(proc))
    assert ppids == {1: 0, 100: 1, 101: 100, 102: 100, 103: 102, 104: 103, 105: 102, 200: 1, 201: 200}
    assert rp.descendants(ppids, SHELL, skip={ME}) == {BUILD, 103, 104, 105}
    assert rp.descendants(ppids, SHELL) == {ME, BUILD, 103, 104, 105}
    assert rp.descendants(ppids, BUILD) == {103, 104, 105} and rp.descendants(ppids, 999) == set()
    assert rp.descendants(ppids, SHELL, skip={BUILD}) == {ME}             # a skipped pid takes its tree with it
    assert rp.descendants({5: 6, 6: 5}, 5) == {6}                         # a loop never hangs
    assert rp.mem_kb(str(proc), BUILD) == (3072 * KB, 256 * KB)           # VmRSS and VmSwap, not VmPeak / VmData
    assert rp.mem_kb(str(proc), 104) == (256 * KB, 0)
    assert rp.mem_kb(str(proc), 105) == (0, 0) and rp.mem_kb(str(proc), 999) == (0, 0)    # a zombie, gone
    _write(proc / "106" / "status", "Name:\tx\nVmRSS:\t   77 kB\nVmSwap:\tlots kB\n")
    assert rp.mem_kb(str(proc), 106) == (77, 0)                           # a bad field counts 0, the other kept
    assert rp.processes(str(tmp_path / "none")) == {}
    p = rp.Probe(str(proc), SHELL, None, str(tmp_path), me=ME, clock=lambda: 0.0)
    assert p.build_mem() == (B_RSS, B_SWAP) == (3840, 320)
    assert rp.Probe(str(proc), None, None, str(tmp_path), me=ME).build_mem() == (None, None)  # no parent: no figure


def test_once_the_shell_is_gone_its_build_is_still_found_by_its_last_pids(tmp_path):
    """A runner shutdown can kill the build step's shell first: the kernel re-parents its build (to pid 1 or a
    subreaper) and it runs on. The build's memory is then that of the last look's processes still there, by pid, and
    of everything under them, never 0 while the build lives; the probe and every other process never count."""
    proc = fake_proc(tmp_path / "proc")
    p = rp.Probe(str(proc), SHELL, None, str(tmp_path), me=ME, clock=lambda: 0.0)
    assert p.build_mem() == (B_RSS, B_SWAP)
    shutil.rmtree(str(proc / str(SHELL)))                # the shell killed: its children go to pid 1
    reparent(proc, BUILD, 1)
    reparent(proc, ME, 1)
    assert rp.descendants(rp.processes(str(proc)), SHELL) == set()
    assert p.build_mem() == (B_RSS, B_SWAP)              # the same build, not 0
    set_proc(proc, 106, 103, "py (worker) 2", 1000, 10)  # a worker it starts after that: found under its pids
    set_proc(proc, 202, 1, "orphan of another step", 4000, 40)       # another orphan under pid 1: never counted
    assert p.build_mem() == (B_RSS + 1000, B_SWAP + 10)
    shutil.rmtree(str(proc / str(BUILD)))                # the build's main process gone, its workers still there
    reparent(proc, 103, 1)
    reparent(proc, 105, 1)
    assert p.build_mem() == (B_RSS + 1000 - 3072, B_SWAP + 10 - 256)
    for pid in (103, 104, 105, 106):                     # all of it gone: 0, and it stays 0
        shutil.rmtree(str(proc / str(pid)))
    assert p.build_mem() == (0, 0) and p.build_mem() == (0, 0)


def test_with_the_shell_alive_a_finished_build_counts_0_not_its_last_figure(tmp_path):
    proc = fake_proc(tmp_path / "proc")
    p = rp.Probe(str(proc), SHELL, None, str(tmp_path), me=ME, clock=lambda: 0.0)
    assert p.build_mem() == (B_RSS, B_SWAP)
    for pid in (BUILD, 103, 104, 105):                   # the build ran to its end; the shell goes on (res_stop)
        shutil.rmtree(str(proc / str(pid)))
    assert p.build_mem() == (0, 0)
    set_proc(proc, 107, SHELL, "date", 2, 0)             # anything under the shell counts (its next command)
    assert p.build_mem() == (2, 0)


def test_the_parent_is_gone_once_it_exits_or_is_a_zombie(tmp_path):
    proc = fake_proc(tmp_path / "proc")
    assert rp.alive(str(proc), SHELL) and not rp.alive(str(proc), 999)
    set_proc(proc, 106, BUILD, "zz", None, state="Z")
    assert not rp.alive(str(proc), 106)
    _write(proc / "107" / "stat", "unparsable")
    assert rp.alive(str(proc), 107)                      # an odd read never stops the probe by mistake


# ── the stage ───────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("content, shown", [
    (b"ga4/roi_apps/roi_device", "ga4/roi_apps/roi_device"),
    (b"setup", "setup"),
    (b"a" * 160, "a" * 160),
    (b"", "-"),                                          # the stage clock between stages
    (b"a" * 161, "?"),                                   # too long
    (b"ga4/roi apps", "?"),
    (b"ga4/roi_apps\n", "?"),
    (b"GA4", "?"),
    (b"com.example.secretapp", "?"),
    (b"ca-app-pub-0000000000000000~0000000000", "?"),
    (b"1234", "?"),                                      # a bare number never prints
    (b"ga4/123", "?"),
    (b"/ga4", "?"),
    (b"ga4/", "?"),
    (b"ga4//roi_apps", "?"),
    (b"../../etc", "?"),
    (b"ga4/\xc3\xa9", "?"),
    (b"\xff\xfe", "?"),
])
def test_the_stage_prints_only_when_it_is_stage_identifiers(tmp_path, content, shown):
    f = tmp_path / "stage_now"
    f.write_bytes(content)
    assert rp.stage_text(str(f)) == shown


def test_no_stage_file_is_a_dash_and_an_unreadable_one_a_question_mark(tmp_path, monkeypatch):
    assert rp.stage_text(None) == "-" and rp.stage_text("") == "-"
    assert rp.stage_text(str(tmp_path / "missing")) == "-"
    assert rp.stage_text(str(tmp_path)) == "?"           # a folder where the file should be
    monkeypatch.setenv(rp.STAGE_ENV, "/somewhere/stage_now")
    assert rp._args([]).stage_file == "/somewhere/stage_now"           # the default: the stage clock's env
    monkeypatch.delenv(rp.STAGE_ENV)
    assert rp._args([]).stage_file is None


def test_it_prints_the_stage_the_stage_clock_keeps(tmp_path, monkeypatch):
    """What the stage clock writes (STAGE_NOW_FILE) is what the probe prints, at every depth, and "-" between runs."""
    now = tmp_path / "stage_now"
    monkeypatch.setenv(sc.NOW_ENV, str(now))
    proc = fake_proc(tmp_path / "proc")
    _disk(monkeypatch)
    p = rp.Probe(str(proc), SHELL, str(now), str(tmp_path), me=ME, clock=lambda: 0.0)

    def stage():
        return p.sample().split()[2]

    assert stage() == "stage=-"                          # before the run: no file
    sc.begin()
    try:
        assert stage() == "stage=-"                      # the run, no stage open yet
        sc.step("ga4")
        with sc.stage("roi_apps"):
            with sc.stage("roi_device"):
                assert stage() == "stage=ga4/roi_apps/roi_device"
            assert stage() == "stage=ga4/roi_apps"
        sc.step("tabs")
        assert stage() == "stage=tabs"
    finally:
        sc.finish(None)
    assert stage() == "stage=-"
    assert rp.STAGE_ENV == sc.NOW_ENV
    longest = "/".join(sorted(sc.STAGES, key=len)[-4:])  # deeper and longer than any path the build has
    assert len(longest) <= rp.STAGE_MAX and rp.STAGE_RE.fullmatch(longest)
    assert all(rp.STAGE_RE.fullmatch(n) for n in sc.STAGES)


# ── when it samples and how it stops ────────────────────────────────────────────────────────────────────────────────
def test_it_samples_at_once_and_every_interval_until_the_parent_exits(tmp_path, monkeypatch):
    proc = fake_proc(tmp_path / "proc")
    _disk(monkeypatch)
    t, naps = [1000.0], []

    def sleep(s):
        naps.append(s)
        t[0] += s
        if t[0] >= 1075:                                 # the shell exits between the 3rd and the 4th sample
            shutil.rmtree(str(proc / str(SHELL)), ignore_errors=True)

    out = []
    p = rp.Probe(str(proc), SHELL, None, str(tmp_path), me=ME, clock=lambda: t[0])
    assert p.watch(out.append, interval=30, sleep=sleep) == "parent"
    assert [ln.split()[1] for ln in out] == ["t=0", "t=30", "t=60"]
    assert naps and max(naps) <= rp.POLL and min(naps) > 0             # it looks for a stop every POLL seconds


def test_the_interval_never_drifts(tmp_path, monkeypatch):
    proc = fake_proc(tmp_path / "proc")
    _disk(monkeypatch)
    t = [0.0]

    def slow_sample():                                   # a sample that takes 7 s (a busy machine)
        t[0] += 7
        return real()

    def sleep(s):
        t[0] += s
        if t[0] >= 100:
            rp._STOP.append(signal.SIGTERM)

    out = []
    p = rp.Probe(str(proc), SHELL, None, str(tmp_path), me=ME, clock=lambda: t[0])
    real, p.sample = p.sample, slow_sample
    assert p.watch(out.append, interval=30, sleep=sleep) == "signal"
    assert [ln.split()[1] for ln in out] == ["t=7", "t=37", "t=67", "t=97"]     # on the 30 s grid, not 37 s apart


def _main(tmp_path, monkeypatch, stop_at=None, shell_dies_at=None, sigterm_too=False, change_at=None):
    """main() on the fake /proc with a fake clock and a 30 s interval: a stop signal at stop_at seconds, or at
    shell_dies_at the build step's shell dies first, as in a runner kill (the kernel re-parents the build to pid 1 and
    it runs on; sigterm_too: the probe gets the same SIGTERM at that moment); change_at = (seconds, fn(proc, stage)):
    one change of the machine before that."""
    proc = fake_proc(tmp_path / "proc", procs=[x for x in TREE if x[0] != ME])
    stage = tmp_path / "stage_now"
    stage.write_text("ga4/roi_apps")
    _disk(monkeypatch)
    t, done = [0.0], set()

    def sleep(s):
        t[0] += s
        if change_at is not None and t[0] >= change_at[0] and "change" not in done:
            done.add("change")
            change_at[1](proc, stage)
        if stop_at is not None and t[0] >= stop_at and not rp._STOP:
            rp._STOP.append(signal.SIGTERM)
        if shell_dies_at is not None and t[0] >= shell_dies_at and "shell" not in done:
            done.add("shell")
            shutil.rmtree(str(proc / str(SHELL)))
            reparent(proc, BUILD, 1)
            if sigterm_too:
                rp._STOP.append(signal.SIGTERM)

    buf = io.StringIO()
    assert rp.main(["--proc", str(proc), "--parent", str(SHELL), "--stage-file", str(stage), "--disk", str(tmp_path),
                    "--interval", "30"], out=buf, sleep=sleep, clock=lambda: t[0]) == 0
    return buf.getvalue().splitlines()


def test_a_stop_signal_takes_one_last_sample_then_prints_the_peak(tmp_path, monkeypatch):
    lines = _main(tmp_path, monkeypatch, stop_at=65)
    assert lines[0] == ("res machine cpus=4 mem_total_mb=16384 swap_total_mb=4096 disk_total_mb=73000 "
                        "disk_free_mb=21000 oom_kills=0")
    assert [ln.split()[1] for ln in lines[1:-1]] == ["t=0", "t=30", "t=60", "t=65"]   # the last: the state at the stop
    assert lines[-1] == ("res peak used_mb=10240 min_avail_mb=6144 max_swap_mb=1024 max_some10=2 max_full10=1 "
                         "max_build_mb=4160 at_stage=ga4/roi_apps max_build_rss_mb=3840 min_disk_free_mb=21000 "
                         "samples=4")
    _public(lines, str(tmp_path))


@pytest.mark.parametrize("sigterm_too", [False, True])
def test_when_the_shell_dies_first_it_still_takes_the_last_sample_of_the_build(tmp_path, monkeypatch, sigterm_too):
    """The shell gone (with or without the same SIGTERM to the probe): one last sample at that moment, the build in it
    (re-parented, found by its pids), then the peak line."""
    lines = _main(tmp_path, monkeypatch, shell_dies_at=45, sigterm_too=sigterm_too)
    assert [ln.split()[1] for ln in lines[1:-1]] == ["t=0", "t=30", "t=45"]
    assert all(" build_rss_mb=3840 build_swap_mb=320 " in ln for ln in lines[1:-1])
    assert lines[-1] == ("res peak used_mb=10240 min_avail_mb=6144 max_swap_mb=1024 max_some10=2 max_full10=1 "
                         "max_build_mb=4160 at_stage=ga4/roi_apps max_build_rss_mb=3840 min_disk_free_mb=21000 "
                         "samples=3")
    _public(lines, str(tmp_path))


@pytest.mark.parametrize("sigterm_too", [False, True])
def test_a_runner_kill_leaves_the_state_at_the_kill_not_the_last_interval_sample(tmp_path, monkeypatch, sigterm_too):
    """Memory runs out and the build moves to its next stage after the t=30 sample; the shell dies at t=58 while the
    build lives on. The log must end on that state, not on the 28 s old sample (which reads as plenty of headroom)."""
    def low(proc, stage):
        set_mem(proc, avail=400, swap_free=0)
        set_proc(proc, BUILD, SHELL, "python", 15000, 900)
        set_pressure(proc, 48.3, 31.7)
        stage.write_text("ga4/roi_apps/roi_country")

    lines = _main(tmp_path, monkeypatch, shell_dies_at=58, sigterm_too=sigterm_too, change_at=(50, low))
    assert [ln.split()[1] for ln in lines[1:-1]] == ["t=0", "t=30", "t=58"]
    assert lines[2] == ("res t=30 stage=ga4/roi_apps used_mb=10240 avail_mb=6144 swap_used_mb=1024 mem_some10=2 "
                        "mem_full10=1 build_rss_mb=3840 build_swap_mb=320 disk_free_mb=21000 oom_kills=0")
    assert lines[-2:] == [
        "res t=58 stage=ga4/roi_apps/roi_country used_mb=15984 avail_mb=400 swap_used_mb=4096 mem_some10=48 "
        "mem_full10=32 build_rss_mb=15768 build_swap_mb=964 disk_free_mb=21000 oom_kills=0",
        "res peak used_mb=15984 min_avail_mb=400 max_swap_mb=4096 max_some10=48 max_full10=32 max_build_mb=16732 "
        "at_stage=ga4/roi_apps/roi_country max_build_rss_mb=15768 min_disk_free_mb=21000 samples=3"]
    _public(lines, str(tmp_path))


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_a_real_signal_stops_it_with_a_last_sample_the_peak_and_exit_0(tmp_path, sig):
    proc = fake_proc(tmp_path / "proc", procs=[x for x in TREE if x[0] != ME])
    env = dict(os.environ, PYTHONPATH=ROOT)
    env.pop(rp.STAGE_ENV, None)
    p = subprocess.Popen([sys.executable, "-m", "admob_iq.res_probe", "--proc", str(proc), "--parent", str(SHELL),
                          "--interval", "0.2", "--disk", str(tmp_path)], cwd=str(tmp_path), env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    guard = threading.Timer(60, p.kill)                  # (a hang fails the test, never the session)
    guard.start()
    try:
        head = [p.stdout.readline().rstrip("\n") for _ in range(3)]      # the machine line + two samples
        p.send_signal(sig)
        rest, err = p.communicate(timeout=60)
    finally:
        guard.cancel()
    lines = head + rest.splitlines()
    assert p.returncode == 0 and err == ""
    assert lines[0].startswith("res machine ") and lines[1].startswith("res t=0 stage=- ")
    samples = [ln for ln in lines if ln.startswith("res t=")]
    assert len(samples) >= 3 and lines[-2] == samples[-1]                # the last sample, then the peak
    assert re.fullmatch(r"res peak used_mb=10240 min_avail_mb=6144 max_swap_mb=1024 max_some10=2 max_full10=1 "
                        r"max_build_mb=4160 at_stage=- max_build_rss_mb=3840 min_disk_free_mb=\d+ samples=%d"
                        % len(samples), lines[-1]), lines[-1]            # (this disk's real free space)
    _public(lines, str(tmp_path))


# ── it never fails ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_without_proc_it_says_unavailable_once_and_exits_0(tmp_path):
    buf = io.StringIO()
    assert rp.main(["--proc", str(tmp_path / "none"), "--parent", "1"], out=buf) == 0
    assert buf.getvalue() == "res unavailable\n"
    if not os.path.isfile("/proc/meminfo"):              # this Mac: the module as the workflow runs it
        r = subprocess.run([sys.executable, "-m", "admob_iq.res_probe", "--parent", str(os.getpid())], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
        assert (r.returncode, r.stdout, r.stderr) == (0, "res unavailable\n", "")


@pytest.mark.parametrize("argv", [["--interval", "x"], ["--parent", "y"], ["--parent", "0"], ["--nope"], ["extra"]])
def test_unusable_arguments_say_unavailable_and_exit_0(tmp_path, argv, capsys):
    buf = io.StringIO()
    assert rp.main(argv + ["--proc", str(fake_proc(tmp_path / "proc"))], out=buf) == 0
    assert buf.getvalue() == "res unavailable\n"


def test_a_bad_interval_falls_back_to_10_s_and_it_looks_for_a_stop_10_times_a_second():
    for v in ("-1", "0", "nan"):
        assert rp._args(["--interval", v]).interval == rp.INTERVAL == 10.0
    assert rp._args(["--interval", "0.5"]).interval == 0.5 and rp._args([]).interval == 10.0
    assert rp.POLL == 0.1


class _Closed(io.StringIO):
    def write(self, s):
        raise BrokenPipeError(32, "Broken pipe")


def test_a_closed_log_never_raises(tmp_path, monkeypatch):
    _disk(monkeypatch)
    proc = fake_proc(tmp_path / "proc")
    assert rp.main(["--proc", str(proc), "--parent", str(SHELL)], out=_Closed()) == 0
    assert rp.main(["--proc", str(tmp_path / "none")], out=_Closed()) == 0


def test_an_unforeseen_error_never_raises(tmp_path, monkeypatch):
    proc = fake_proc(tmp_path / "proc")

    def boom(*_a, **_k):
        raise RuntimeError("synthetic")

    monkeypatch.setattr(rp.Probe, "watch", boom)
    buf = io.StringIO()
    assert rp.main(["--proc", str(proc), "--parent", str(SHELL)], out=buf) == 0
    assert buf.getvalue().startswith("res machine ")


@pytest.mark.skipif(not os.path.isfile("/proc/meminfo"), reason="Linux only: the real /proc")
def test_on_linux_the_real_proc_gives_numbers(tmp_path):
    p = rp.Probe("/proc", os.getppid(), None, str(tmp_path))
    lines = [p.machine(), p.sample(), p.peak()]
    _public(lines)
    assert "?" not in lines[0] and "used_mb=?" not in lines[1] and "build_rss_mb=?" not in lines[1]


# ── the build step ──────────────────────────────────────────────────────────────────────────────────────────────────
def _build_step():
    with open(os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        steps = yaml.safe_load(f)["jobs"]["refresh"]["steps"]
    return next(s for s in steps if s.get("name") == "Build dashboard + send alerts")


def test_the_build_step_starts_the_probe_before_the_build_and_stops_it_after_in_both_branches():
    step = _build_step()
    run, env = step["run"], step["env"]
    assert env[sc.NOW_ENV] == "/tmp/stage_now" and "secrets." not in env[sc.NOW_ENV]
    start = run.index("python -m admob_iq.res_probe --parent $$ 2>/dev/null &\n")      # background, stderr dropped
    build = run.index("if python -m admob_iq.build_static > /tmp/build.log 2>&1; then")
    assert start < run.index("res_pid=$!") < run.index("date +%s.%N > /tmp/build_wall") < build
    then, other = run.index("echo \"build complete\""), run.index("echo \"::error::build failed")
    assert then < other < run.index("\n  exit 1\nfi\n")                  # the failed build still fails the step
    walls = [m.start() for m in re.finditer(r"date \+%s\.%N >> /tmp/build_wall\n", run)]
    stops = [m.start() for m in re.finditer(r"^ *res_stop$", run, re.M)]
    assert len(walls) == len(stops) == 2                 # both branches, after the build's wall clock
    assert walls[0] < stops[0] < then < walls[1] < stops[1] < other
    body = run[run.index("res_stop() {"):run.index("\n}\n", run.index("res_stop() {"))]
    assert 'kill -TERM "$res_pid" 2>/dev/null || true' in body and 'wait "$res_pid" 2>/dev/null || true' in body
    assert "sudo -n dmesg 2>/dev/null" in body and "grep -ci 'killed process' || true" in body    # a count only
    assert run.count("-m admob_iq.res_probe") == 1 and not re.search(r"\btee\b", run) and "cat /tmp" not in run


def _stub(path, text):
    _write(path, "#!/bin/sh\n" + text)
    os.chmod(str(path), 0o755)


def _run_step(tmp_path, build_exit, sudo_ok=True, probe=True, shell=("bash", "-e")):
    """The build step's own script, run as GitHub runs it (bash -e, or the explicit bash -eo pipefail), with a
    stand-in build that runs 1 s (the probe is up by then, as in any real build), prints a line with digits and exits
    build_exit; `python` = this interpreter, `sudo` a stub whose dmesg has two OOM kills, /tmp/ swapped for tmp_path."""
    step = _build_step()
    work = tmp_path / "work"
    os.makedirs(str(work))
    script = step["run"].replace("/tmp/", str(work) + "/")
    script = script.replace("python -m admob_iq.build_static", "python -c 'import sys, time; time.sleep(1); "
                            "print(\"app 4242 earned 12.34\"); sys.exit(%d)'" % build_exit)
    if not probe:
        script = script.replace("python -m admob_iq.res_probe", "no_such_probe_command")
    _write(work / "step.sh", script)
    bin_dir = tmp_path / "bin"
    _stub(bin_dir / "python", 'exec "%s" "$@"\n' % sys.executable)
    _stub(bin_dir / "sudo", '[ "$1" = "-n" ] && [ "$2" = "dmesg" ] || exit 1\n%s' % (
        "printf '[  1.0] Linux version x\\n[ 99.0] Out of memory: Killed process 4242 (%s) total-vm:1kB\\n"
        "[ 99.1] oom_reaper: reaped process 4242\\n[120.0] Memory cgroup out of memory: killed process 4343 (node)\\n'"
        "\n" % SECRET if sudo_ok else "exit 1\n"))
    env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ.get("PATH", ""), PYTHONPATH=ROOT)
    env[sc.NOW_ENV] = str(work / "stage_now")
    r = subprocess.run(list(shell) + [str(work / "step.sh")], cwd=str(work), env=env, capture_output=True, text=True,
                       timeout=120)
    return r.returncode, r.stdout.splitlines(), r.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("shell", [("bash", "-e"), ("bash", "--noprofile", "--norc", "-eo", "pipefail")])
def test_the_step_still_passes_a_good_build_and_fails_a_bad_one_with_the_probe_around_it(tmp_path, shell):
    code, out, err = _run_step(tmp_path / "ok", 0, shell=shell)
    assert code == 0 and err == ""
    res = [ln for ln in out if ln.startswith("res ")]
    assert out[-2:] == ["res oom_kills=2", "build complete"] and out.index("res oom_kills=2") == len(res) - 1
    assert res[0] == "res unavailable" if not os.path.isfile("/proc/meminfo") else res[-2].startswith("res peak ")
    _public(res)

    code, out, err = _run_step(tmp_path / "bad", 3, sudo_ok=False, shell=shell)
    assert code == 1 and err == ""
    i = out.index("::error::build failed — tail below, digits masked for privacy")
    assert out[i - 1] == "res oom_kills=?" and out[i + 1:] == ["app #### earned #.##"]   # the tail, masked as before
    _public([ln for ln in out if ln.startswith("res ")])


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_a_probe_that_cannot_start_never_fails_the_step(tmp_path):
    code, out, err = _run_step(tmp_path / "ok", 0, probe=False)
    assert (code, out[-2:], err) == (0, ["res oom_kills=2", "build complete"], "")
    code, out, err = _run_step(tmp_path / "bad", 5, probe=False)
    assert code == 1 and "::error::build failed — tail below, digits masked for privacy" in out and err == ""
