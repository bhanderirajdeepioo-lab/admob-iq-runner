"""Runner resource probe: the machine's memory, swap, memory pressure, OOM kills and free disk, the build's own memory
and swap and the stage it is in, printed to the PUBLIC Actions log while the build runs — so a run that dies mid-build
(the runner's "shutdown signal") leaves its state at that moment behind. Measure only: it reads /proc and the disk's
statvfs, and changes nothing the build makes.

    python -m admob_iq.res_probe --parent <pid> [--interval 10] [--stage-file <file>] [--disk <dir>] [--proc /proc]

Its lines, each one line flushed at once (MB = 1024 x 1024 bytes, whole numbers):
  res machine cpus=<n> mem_total_mb=<n> swap_total_mb=<n> disk_total_mb=<n> disk_free_mb=<n> oom_kills=<n>
                                                                                                      once, at start
  res t=<s> stage=<path> used_mb=<n> avail_mb=<n> swap_used_mb=<n> mem_some10=<n> mem_full10=<n> build_rss_mb=<n>
      build_swap_mb=<n> disk_free_mb=<n> oom_kills=<n>       at once, every --interval seconds, once more at the stop
  res peak used_mb=<n> min_avail_mb=<n> max_swap_mb=<n> max_some10=<n> max_full10=<n> max_build_mb=<n>
      at_stage=<path> max_build_rss_mb=<n> min_disk_free_mb=<n> samples=<n>                             at the stop
  res unavailable                         no /proc (not Linux) or unusable arguments: its only line
t = seconds since the probe started. used = MemTotal - MemAvailable, avail = MemAvailable, swap used = SwapTotal -
SwapFree (/proc/meminfo). mem_some10 / mem_full10 = /proc/pressure/memory's avg10: the % of the last 10 s in which
some / all running tasks waited on memory (a VM short of memory with no swap stalls on page-cache refaults while
avail may still read a few hundred MB). build_rss / build_swap = the VmRSS / VmSwap sums over every process under
--parent (the build step's shell) except this probe: during the build, the build and its workers. A runner shutdown
can kill the shell first while the build runs on (the kernel re-parents it): with nothing left under the shell, they
are the sums over the processes of the last look that are still there, by pid, and everything under them.
disk_free = what an unprivileged process can still write on --disk (default: the working directory, i.e. the
workspace). oom_kills = /proc/vmstat's oom_kill: the kernel's OOM kills since boot, global or cgroup (the machine
line: the count before the build). A value it could not read prints "?".
stage = the stage clock's live path (admob_iq/stage_clock.py keeps the file STAGE_NOW_FILE names, the --stage-file
default), printed only when it is stage identifiers joined by "/" (STAGE_RE: [a-z0-9_/], at most 160 characters,
each part a letter first), "?" for anything else, "-" when there is none.
The peak line: the worst of each figure over the samples; max_build = the most build_rss + build_swap of one sample
(swapped-out pages leave VmRSS, so RSS alone can point at an earlier stage), at_stage = that sample's stage,
max_build_rss = the most build_rss; samples = the sample lines printed.

It stops on SIGTERM / SIGINT or when --parent exits, within POLL, then prints one last sample (the state at that
moment: also when the shell died first, with or without the same signal) and the peak line, and exits 0.
PUBLIC LOG: numbers and stage identifiers ONLY — never a process name, command line, path, env value or host name
(nothing else it reads is ever printed). Standard library only; never raises, always exits 0."""

import argparse
import os
import re
import signal
import sys
import time

INTERVAL = 10.0                # seconds between two sample lines
POLL = 0.1                     # seconds between two looks for a stop (a signal, the parent's exit): short, since
#                                a runner shutdown can kill the build and this probe a fraction of a second after the
#                                shell, and the last sample should still see them
STAGE_ENV = "STAGE_NOW_FILE"   # the stage clock's live file (stage_clock.NOW_ENV)
STAGE_MAX = 160                # characters of a printed stage path
# (fullmatch) [a-z0-9_/]{1,160}, and each "/" part a stage identifier (a letter first): never a bare number
STAGE_RE = re.compile(r"(?=[a-z0-9_/]{1,%d}\Z)[a-z][a-z0-9_]*(?:/[a-z][a-z0-9_]*)*" % STAGE_MAX)
MB = 1024 * 1024
_STOP = []                     # the stop signals that arrived


def _n(v):
    return "?" if v is None else "%d" % v


def _mb(kb):
    return None if kb is None else int(round(kb / 1024.0))


def _less(a, b):
    return max(0, a - b) if a is not None and b is not None else None


def _peak(old, new, pick):
    return old if new is None else new if old is None else pick(old, new)


def _stat_rest(proc, pid):
    """/proc/<pid>/stat's fields after "pid (comm) " (comm may hold spaces and brackets: it is never kept)."""
    with open(os.path.join(proc, str(pid), "stat"), encoding="ascii", errors="replace") as f:
        st = f.read()
    return st[st.rindex(")") + 2:].split()


def meminfo(proc):
    """/proc/meminfo → {field: kB}; {} when unreadable."""
    out = {}
    try:
        with open(os.path.join(proc, "meminfo"), encoding="ascii", errors="replace") as f:
            for line in f:
                key, _, rest = line.partition(":")
                v = rest.split()
                if v and v[0].isdigit():
                    out[key.strip()] = int(v[0])
    except OSError:
        pass
    return out


def oom_kills(proc):
    """/proc/vmstat's oom_kill: the kernel's OOM kills since boot, by a global or a cgroup OOM (Linux 4.13+, readable
    without root); None when unreadable."""
    try:
        with open(os.path.join(proc, "vmstat"), encoding="ascii", errors="replace") as f:
            for line in f:
                key, _, v = line.partition(" ")
                if key == "oom_kill":
                    v = v.strip()
                    return int(v) if v.isdigit() else None
    except OSError:
        pass
    return None


def pressure(proc):
    """/proc/pressure/memory's avg10 of its "some" and "full" lines → (some, full) in whole % (0-100); None for one
    it cannot read (no file, a kernel booted with psi=0 refuses the read, or no number in 0-100)."""
    got = {}
    try:
        with open(os.path.join(proc, "pressure", "memory"), encoding="ascii", errors="replace") as f:
            for line in f:
                kind, _, rest = line.partition(" ")
                if kind not in ("some", "full") or kind in got:
                    continue
                for field in rest.split():
                    name, _, v = field.partition("=")
                    if name == "avg10":
                        try:
                            x = float(v)
                        except ValueError:
                            x = -1.0
                        got[kind] = int(round(x)) if 0.0 <= x <= 100.0 else None     # (also NaN: None)
                        break
    except OSError:
        pass
    return got.get("some"), got.get("full")


def cpus(proc):
    """The online CPUs: /proc/cpuinfo's processor entries, else os.cpu_count() (None when unknown)."""
    try:
        with open(os.path.join(proc, "cpuinfo"), encoding="ascii", errors="replace") as f:
            n = sum(1 for line in f if line.split(":")[0].strip() == "processor")
        if n:
            return n
    except OSError:
        pass
    return os.cpu_count()


def processes(proc):
    """{pid: parent pid} of every process in /proc (one that is gone or unreadable mid-walk is left out)."""
    out = {}
    try:
        names = os.listdir(proc)
    except OSError:
        return out
    for name in names:
        if name.isascii() and name.isdigit():
            try:
                out[int(name)] = int(_stat_rest(proc, name)[1])
            except (OSError, ValueError, IndexError):
                continue
    return out


def descendants(ppids, root, skip=()):
    """Every pid under root (root itself not), less the pids in skip and everything under them."""
    kids = {}
    for pid, pp in ppids.items():
        kids.setdefault(pp, []).append(pid)
    out, todo = set(), list(kids.get(root, ()))
    while todo:
        pid = todo.pop()
        if pid in out or pid in skip or pid == root:
            continue
        out.add(pid)
        todo.extend(kids.get(pid, ()))
    return out


def mem_kb(proc, pid):
    """One process's (VmRSS, VmSwap) in kB; 0 for each it lacks (gone, a zombie, a kernel thread or unreadable)."""
    got = {"VmRSS": 0, "VmSwap": 0}
    try:
        with open(os.path.join(proc, str(pid), "status"), encoding="ascii", errors="replace") as f:
            for line in f:
                key, _, rest = line.partition(":")
                if key in got:
                    v = rest.split()
                    got[key] = int(v[0]) if v and v[0].isdigit() else 0
    except OSError:
        pass
    return got["VmRSS"], got["VmSwap"]


def alive(proc, pid):
    """False once the process is gone (or a zombie); an odd read error counts as alive (never a stop by mistake)."""
    try:
        return _stat_rest(proc, pid)[0] not in ("Z", "X", "x")
    except (FileNotFoundError, ProcessLookupError):
        return False
    except (OSError, ValueError, IndexError):
        return True


def disk_mb(path):
    """(total, free for an unprivileged writer) in MB of the file system that holds path; (None, None) unreadable."""
    try:
        st = os.statvfs(path)
        return st.f_blocks * st.f_frsize // MB, st.f_bavail * st.f_frsize // MB
    except (OSError, AttributeError, ValueError):
        return None, None


def stage_text(path):
    """The stage clock's live path when it is stage identifiers only; "-" when there is none (no file, empty); "?"
    for anything else (nothing else from the file is ever printed)."""
    if not path:
        return "-"
    try:
        with open(path, "rb") as f:
            raw = f.read(STAGE_MAX + 1)
    except FileNotFoundError:
        return "-"
    except OSError:
        return "?"
    if not raw:
        return "-"
    text = raw.decode("ascii", "replace")
    return text if STAGE_RE.fullmatch(text) else "?"


class Probe:
    """One build's samples and their peaks."""

    def __init__(self, proc="/proc", parent=None, stage_file=None, disk=".", me=None, clock=time.monotonic):
        self.proc, self.parent, self.stage_file, self.disk = proc, parent, stage_file, disk
        self.me = os.getpid() if me is None else me              # never counted as the build
        self.clock, self.t0 = clock, clock()
        self.last = set()                                        # the build's pids at the last look that found any
        self.n, self.used, self.avail, self.swap, self.some, self.full = 0, None, None, None, None, None
        self.rss, self.top, self.top_stage, self.disk_free = None, None, "-", None

    def machine(self):
        m = meminfo(self.proc)
        total, free = disk_mb(self.disk)
        return "res machine cpus=%s mem_total_mb=%s swap_total_mb=%s disk_total_mb=%s disk_free_mb=%s oom_kills=%s" % (
            _n(cpus(self.proc)), _n(_mb(m.get("MemTotal"))), _n(_mb(m.get("SwapTotal"))), _n(total), _n(free),
            _n(oom_kills(self.proc)))

    def build_mem(self):
        """(RSS, swap) MB of every process under the parent except this probe; with nothing under it (the shell gone,
        its build re-parented and running on), of the last look's processes still there and everything under them.
        (None, None) without a parent."""
        if self.parent is None:
            return None, None
        ppids = processes(self.proc)
        pids = descendants(ppids, self.parent, skip={self.me})
        if not pids:
            pids = {p for p in self.last if p in ppids}
            for p in list(pids):
                pids |= descendants(ppids, p, skip={self.me})
        self.last = pids or self.last
        rss = swap = 0
        for p in pids:
            r, s = mem_kb(self.proc, p)
            rss, swap = rss + r, swap + s
        return _mb(rss), _mb(swap)

    def sample(self):
        """Measure once → its line; the peaks take it in."""
        t = self.clock() - self.t0
        m = meminfo(self.proc)
        used, avail = _mb(_less(m.get("MemTotal"), m.get("MemAvailable"))), _mb(m.get("MemAvailable"))
        swap = _mb(_less(m.get("SwapTotal"), m.get("SwapFree")))
        some, full = pressure(self.proc)
        rss, bswap = self.build_mem()
        free, stage, ooms = disk_mb(self.disk)[1], stage_text(self.stage_file), oom_kills(self.proc)
        self.n += 1
        self.used, self.avail, self.swap = _peak(self.used, used, max), _peak(self.avail, avail, min), \
            _peak(self.swap, swap, max)
        self.some, self.full, self.disk_free = _peak(self.some, some, max), _peak(self.full, full, max), \
            _peak(self.disk_free, free, min)
        self.rss = _peak(self.rss, rss, max)
        if rss is not None and (self.top is None or rss + bswap > self.top):
            self.top, self.top_stage = rss + bswap, stage
        return ("res t=%d stage=%s used_mb=%s avail_mb=%s swap_used_mb=%s mem_some10=%s mem_full10=%s build_rss_mb=%s "
                "build_swap_mb=%s disk_free_mb=%s oom_kills=%s" % (
                    int(round(max(0.0, t))), stage, _n(used), _n(avail), _n(swap), _n(some), _n(full), _n(rss),
                    _n(bswap), _n(free), _n(ooms)))

    def peak(self):
        return ("res peak used_mb=%s min_avail_mb=%s max_swap_mb=%s max_some10=%s max_full10=%s max_build_mb=%s "
                "at_stage=%s max_build_rss_mb=%s min_disk_free_mb=%s samples=%d" % (
                    _n(self.used), _n(self.avail), _n(self.swap), _n(self.some), _n(self.full), _n(self.top),
                    self.top_stage, _n(self.rss), _n(self.disk_free), self.n))

    def parent_alive(self):
        return self.parent is None or alive(self.proc, self.parent)

    def watch(self, emit, interval=INTERVAL, sleep=time.sleep, poll=POLL):
        """Sample at once, then every `interval` seconds (on the probe's own clock, no drift), until a stop signal
        (→ "signal") or the parent's exit (→ "parent")."""
        while True:
            emit(self.sample())
            due = self.t0 + (int((self.clock() - self.t0) // interval) + 1) * interval
            while True:
                if _STOP:
                    return "signal"
                if not self.parent_alive():
                    return "parent"
                left = due - self.clock()
                if left <= 0:
                    break
                sleep(min(poll, left))


def _on_signal(signum, _frame):
    _STOP.append(signum)       # (the loop sees it within POLL: no exception in the middle of a write)


def _emit(out, line):
    out.write(line + "\n")
    out.flush()


def _args(argv):
    """The arguments → a namespace, or None when unusable (argparse's own message goes to stderr)."""
    ap = argparse.ArgumentParser(prog="python -m admob_iq.res_probe", add_help=False)
    ap.add_argument("--parent", type=int)
    ap.add_argument("--interval", type=float, default=INTERVAL)
    ap.add_argument("--stage-file", default=os.environ.get(STAGE_ENV) or None)
    ap.add_argument("--disk", default=".")
    ap.add_argument("--proc", default="/proc")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return None
    if a.parent is not None and a.parent <= 0:
        return None
    if not a.interval > 0:                      # (also NaN)
        a.interval = INTERVAL
    return a


def main(argv=None, out=None, sleep=time.sleep, clock=time.monotonic):
    """The probe (the module docstring). Always → 0; never raises."""
    out = out or sys.stdout
    try:
        for s in (signal.SIGTERM, signal.SIGINT):
            signal.signal(s, _on_signal)
    except Exception:
        pass
    try:
        a = _args(sys.argv[1:] if argv is None else list(argv))
        if a is None or not os.path.isfile(os.path.join(a.proc, "meminfo")):
            _emit(out, "res unavailable")
            return 0
        p = Probe(a.proc, a.parent, a.stage_file, a.disk, clock=clock)
        _emit(out, p.machine())
        p.watch(lambda line: _emit(out, line), a.interval, sleep)
        _emit(out, p.sample())                   # the state at the stop, also when the shell died first (a runner kill)
        _emit(out, p.peak())
    except BaseException:
        try:                                     # (the log's pipe is gone: the exit stays 0 and silent)
            fd = out.fileno()
            null = os.open(os.devnull, os.O_WRONLY)
            os.dup2(null, fd)
            os.close(null)
        except BaseException:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
