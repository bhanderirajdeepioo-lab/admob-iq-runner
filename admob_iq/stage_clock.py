"""Build stage clock: WHERE the build's time goes. It only measures; it never changes anything the build makes.

How it is used:
  * build_static.main() starts a run (`begin`) and ends it in a finally (`finish`), so a crashed build still writes
    what it measured. On the Actions runner that file reaches the private repo only with a GOOD build's push: the push
    step does not run after a failed build (a push from a failed run could look like a fresh refresh to the watchers
    that read the private repo's commits). So the private history holds the pushed builds; each row carries the
    Actions run number (`run`), and a failed run shows as a gap in those numbers. A failed build's stage seconds still
    reach the public log (that step always runs).
  * build_static.build() marks its top-level stages in order with `step(name)`. Each one runs until the next starts,
    so together they cover the whole build.
  * Inside them, the steps that have their own budget (GA4 reads, Google Ads geo / archive, the forecast, …) are
    timed as CHILDREN: a `with stage(name):` block or a `@timed(name)` function. A parent's time = the sum of its
    children + its own. A child that repeats (once per app, once per account) is summed into ONE row with its count n.
  * Without a run (tests, probes, any other caller) every call is a no-op. Only the main thread is timed.
  * Never raises: every entry point has its own try, so a failure here never fails the build.

Output: data/build_profile.json.gz in the build's PRIVATE data dir (FILE): this build's stages plus a rolling
history of the last HISTORY_KEEP builds written to this file (one compact row each, so trends show). It is
deterministic gzip with sorted keys, and only a few KB.

The Actions log of the public runner is world-readable. `python -m admob_iq.stage_clock public <profile> [<wall
file>]` prints only "stage <name> <sec>s" lines: the total, one line per stage of PUBLIC_MIN_SEC or more, and
(with the build step's wall-clock file) the step's own wall time and what fell outside the build. Names come only
from STAGES / META, which are fixed code identifiers, and the numbers are whole seconds only. No app, account, file
name or amount is ever printed.

The total covers the python process from its start (python_start: interpreter start-up up to this module's import,
read from /proc on Linux) through the module imports (imports) and the whole build to the profile write. Outside it
(the outside_build line): the shell, printing the result and interpreter shutdown. pip runs in its own earlier step.
"""

import functools
import gzip
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

FILE = "build_profile.json.gz"
V = 1
HISTORY_KEEP = 48              # builds kept in the rolling history
HISTORY_MIN_SEC = 1.0          # a history row keeps the stages that took at least this long (small file)
PUBLIC_MIN_SEC = 20            # the public log shows a stage from this many seconds
WALL_SLACK_SEC = 5             # a profile that started before the build step (less this) is an older run's

# Every stage name the build uses, in build order. ONLY these can reach the public log (an allow-list of code
# identifiers). A name used in code but missing here is still timed into the private profile, never printed.
STAGES = (
    # the python process before build() starts
    "python_start", "imports",
    # build_static.build(): top-level stages (step) and their children
    "setup", "site_snapshot",
    "admob_fetch", "admob_network", "admob_mediation", "admob_mediation_unit", "admob_country",
    "admob_placement_country", "admob_adunit_country", "admob_rollup",
    # FileRepo's first read of each history file (db.FileRepo.LOAD_STAGES): a child of the stage that touches it first
    "repo_load_network", "repo_load_mediation", "repo_load_snapshots", "repo_load_country",
    "repo_load_placement_country", "repo_load_mediation_unit", "repo_load_adunit_country_monthly",
    "repo_load_adunit_country_daily",
    "admob_backfill_accounts", "admob_backfill_apps", "admob_backfill_mu", "repo_flush",
    # FileRepo.flush: each history file's write (db.FileRepo.WRITE_STAGES), children of repo_flush
    "repo_write_network", "repo_write_mediation", "repo_write_snapshots", "repo_write_country",
    "repo_write_placement_country", "repo_write_mediation_unit", "repo_write_adunit_country_monthly",
    "repo_write_adunit_country_daily",
    "dashboard_build", "baseline_report", "data_quality", "apps_catalog", "app_icons",
    "google_ads", "gads_spend", "gads_campaign_accounts", "gads_geo", "gads_geo_weekly", "gads_geo_day",
    "gads_archive", "gads_store_ids", "fx_series", "roas_build",
    "usd_inr",
    "ga4", "account_tzs", "ga4_revenue_prep", "ga4_uninstall_fetch", "ga4_discovery",
    "ga4_iday_load", "ga4_iday", "ga4_iday_save", "ga4_iday_only",
    "ga4_audience", "ga4_firstopen", "ga4_firstopen_cc", "ga4_cohort", "ga4_cube",
    "active_prepass", "value_prepass", "uninstall_store_load", "uninstall_eval", "active_apps", "value_apps",
    "roi_apps", "roi_cube", "roi_country", "adcfg", "forecast", "impact_any", "cohort_files",
    "impact_any_finish", "uninstall_asset", "active_finish", "value_finish", "roi_finish",
    "tabs", "uninstall_studio", "active_studio", "value_studio", "audience_tab", "firstopen_tab",
    "intraday", "dashboard_write", "baseline_write", "mediation_daily", "deductions_daily", "static_files",
    "review", "review_studio", "headers", "alerts", "deploy_guard", "teardown",
)
META = ("total", "step_wall", "outside_build")      # the public summary lines (not stages)
_ALLOWED = frozenset(STAGES) | frozenset(META)
NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")


def proc_age(stat_text, uptime_text, hz):
    """Seconds since a process started, from the text of /proc/<pid>/stat (field 22: start time in clock ticks after
    boot) and /proc/uptime. None when unreadable."""
    try:
        rest = stat_text[stat_text.rindex(")") + 2:].split()       # the fields after "pid (comm) ": field 3 onwards
        start = int(rest[19]) / float(hz)                           # field 22
        return max(0.0, float(uptime_text.split()[0]) - start)
    except Exception:
        return None


def _python_age():
    """Seconds from this python process's start to now (Linux /proc; None elsewhere)."""
    try:
        with open("/proc/self/stat", encoding="utf-8") as f:
            st = f.read()
        with open("/proc/uptime", encoding="utf-8") as f:
            up = f.read()
        return proc_age(st, up, os.sysconf("SC_CLK_TCK"))
    except Exception:
        return None


_T_IMPORT = time.perf_counter()        # build_static imports this module first: the imports are timed from here
_PY_AGE = _python_age()                # interpreter start-up before that (Linux only)


class _Frame:
    __slots__ = ("key", "t", "lap")

    def __init__(self, key, t, lap):
        self.key, self.t, self.lap = key, t, lap


def _run_no():
    """The Actions run number (GITHUB_RUN_NUMBER), or None off the runner. Consecutive history rows then show a run
    whose build never reached the private repo (a failed one) as a gap."""
    v = os.environ.get("GITHUB_RUN_NUMBER", "")
    return int(v) if v.isascii() and v.isdigit() else None


class _Run:
    def __init__(self, clock, t0, pre):
        self.clock, self.t0, self.pre = clock, t0, pre
        self.run_no = _run_no()
        back = max(0.0, clock() - t0) + pre
        self.at = (datetime.now(timezone.utc) - timedelta(seconds=back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.rows, self.order, self.stack = {}, [], []

    def row(self, name, parent):
        key = (parent, name)
        if key not in self.rows:
            self.rows[key] = {"name": name, "parent": parent, "sec": 0.0, "ok": True, "n": 0}
            self.order.append(key)
        return key

    def add(self, name, parent, sec, ok):
        r = self.rows[self.row(name, parent)]
        r["sec"] += max(0.0, float(sec))
        r["n"] += 1
        r["ok"] = r["ok"] and bool(ok)

    def open(self, name, lap):
        parent = self.stack[-1].key[1] if self.stack else None
        f = _Frame(self.row(name, parent), self.clock(), lap)
        self.stack.append(f)
        return f

    def close(self, f, ok):
        if not any(x is f for x in self.stack):            # closed already
            return
        while self.stack:                                   # anything left open above it ends with it
            top = self.stack.pop()
            self.add(top.key[1], top.key[0], self.clock() - top.t, ok)
            if top is f:
                return

    def profile(self, ok):
        total = self.pre + max(0.0, self.clock() - self.t0)
        stages = []
        for key in self.order:
            r = self.rows[key]
            if not r["n"]:
                continue
            e = {"name": r["name"], "sec": round(r["sec"], 1), "ok": r["ok"]}
            if r["parent"] is not None:
                e["parent"] = r["parent"]
            if r["n"] > 1:
                e["n"] = r["n"]
            stages.append(e)
        top = sum(r["sec"] for (p, _n), r in self.rows.items() if p is None)
        prof = {"v": V, "at": self.at, "ok": bool(ok), "total_sec": round(total, 1),
                "unmeasured_sec": round(max(0.0, total - top), 1), "stages": stages}
        if self.run_no is not None:
            prof["run"] = self.run_no
        return prof


_RUN = None


def _main_thread():
    return threading.current_thread() is threading.main_thread()


def active():
    """True while a run is being timed."""
    return _RUN is not None


def begin(clock=None, imports=False):
    """Start timing a build. imports=True (build_static.main): the run starts at this module's import, with the
    python start-up before it (python_start, Linux) and the imports (imports) as its first two stages."""
    global _RUN
    try:
        clk = clock or time.perf_counter
        if imports and clock is None:
            run = _Run(clk, _T_IMPORT, _PY_AGE or 0.0)
            if _PY_AGE is not None:
                run.add("python_start", None, _PY_AGE, True)
            run.add("imports", None, clk() - _T_IMPORT, True)
        else:
            run = _Run(clk, clk(), 0.0)
        _RUN = run
    except Exception:
        _RUN = None


def step(name):
    """The next top-level stage starts here (the open one ends). Ignored inside a timed block."""
    run = _RUN
    if run is None:
        return
    try:
        if not _main_thread() or any(not f.lap for f in run.stack):
            return
        while run.stack:
            run.close(run.stack[-1], True)
        run.open(name, True)
    except Exception:
        pass


class stage:
    """`with stage(name):` times the block as a child of the stage open around it. Never raises; an exception from
    the block passes through unchanged (the stage is then marked ok: false)."""
    __slots__ = ("name", "run", "f")

    def __init__(self, name):
        self.name, self.run, self.f = name, None, None

    def __enter__(self):
        try:
            run = _RUN
            if run is not None and _main_thread():
                self.f = run.open(self.name, False)
                self.run = run
        except Exception:
            self.run = self.f = None
        return self

    def __exit__(self, et, ev, tb):
        try:
            if self.f is not None and self.run is _RUN:
                self.run.close(self.f, et is None)
        except Exception:
            pass
        return False


def timed(name):
    """Decorator: every call of the function is timed as `stage(name)`."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **k):
            with stage(name):
                return fn(*a, **k)
        return wrapper
    return deco


def finish(data_dir, ok=True):
    """End the run: the stage still open ends (ok: false when the build crashed in it), and data_dir/FILE is written
    with this build + the rolling history (data_dir None: nothing written). → the profile, or None. Never raises."""
    global _RUN
    run, _RUN = _RUN, None
    if run is None:
        return None
    try:
        while run.stack:
            run.close(run.stack[-1], ok)
        prof = run.profile(ok)
    except Exception:
        return None
    if data_dir is not None:
        try:
            write(data_dir, prof)
        except Exception:
            pass
    return prof


def history_row(prof):
    """One compact history row: when, ok, total, the Actions run number (on the runner) and every stage of
    HISTORY_MIN_SEC or more ({name: sec})."""
    s = {}
    for e in prof.get("stages") or []:
        if e.get("sec", 0) >= HISTORY_MIN_SEC:
            s[e["name"]] = round(s.get(e["name"], 0.0) + e["sec"], 1)
    row = {"at": prof.get("at"), "ok": prof.get("ok"), "total": prof.get("total_sec"), "s": s}
    if isinstance(prof.get("run"), int):
        row["run"] = prof["run"]
    return row


def read(path):
    """A profile file → its dict, or None."""
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def write(data_dir, prof):
    """prof + the history (the previous file's, this build appended, the newest HISTORY_KEEP kept) → data_dir/FILE
    (deterministic gzip, sorted keys). prof itself gets the "history" key."""
    path = os.path.join(data_dir, FILE)
    old = read(path) or {}
    hist = [h for h in (old.get("history") or []) if isinstance(h, dict)]
    prof["history"] = (hist + [history_row(prof)])[-HISTORY_KEEP:]
    os.makedirs(data_dir, exist_ok=True)
    from .db import write_json_gz_stable
    write_json_gz_stable(path, prof)


# ── the public log ──────────────────────────────────────────────────────────────────────────────────────────────────
def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v >= 0


def _line(name, sec):
    return "stage %s %ds" % (name, int(round(sec)))


def public_lines(prof, wall=None, min_sec=PUBLIC_MIN_SEC):
    """The PUBLIC lines: "stage total <sec>s", one "stage <name> <sec>s" per stage of min_sec or more (allow-listed
    names only, in build order), and with `wall` (the build step's own seconds) "stage step_wall <sec>s" +
    "stage outside_build <sec>s" (wall − total: the shell, printing the result, interpreter shutdown)."""
    total = prof.get("total_sec")
    out = [_line("total", total)] if _num(total) else []
    for e in prof.get("stages") or []:
        name, sec = e.get("name"), e.get("sec")
        if isinstance(name, str) and name in _ALLOWED and NAME_RE.match(name) and _num(sec) and sec >= min_sec:
            out.append(_line(name, sec))
    if _num(wall):
        out.append(_line("step_wall", wall))
        if _num(total):
            out.append(_line("outside_build", max(0.0, wall - total)))
    return out


def _epoch(at):
    try:
        return datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def read_wall(path):
    """The build step's wall-clock file (`date +%s.%N` before and after the build, one per line) → (start, seconds
    or None)."""
    try:
        with open(path, encoding="utf-8") as f:
            v = [float(x) for x in f.read().split()]
    except Exception:
        return None, None
    if not v:
        return None, None
    return v[0], (v[1] - v[0] if len(v) > 1 and v[1] >= v[0] else None)


def main(argv=None):
    """`public <profile> [<wall file>]` → the public lines on stdout. Always exits 0."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] != "public":
        return 0
    try:
        prof = read(argv[1])
        checked = len(argv) > 2                      # with the wall file: the profile must be this build step's
        start, wall = read_wall(argv[2]) if checked else (None, None)
        at = _epoch((prof or {}).get("at"))
        if not prof or (checked and (start is None or at is None or at < start - WALL_SLACK_SEC)):
            print("::warning::build profile not written this run")
            return 0
        for ln in public_lines(prof, wall):
            print(ln)
    except Exception:
        print("::warning::build profile unreadable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
