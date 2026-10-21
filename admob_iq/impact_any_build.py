"""📦 "Compare any date" — the build step, called from uninstall_build.run_uninstall (one store in memory at a time).

  * start: reads the previous index (impact_any_index.json.gz) — each app's input signature ("sig": the store file,
    the AdMob revenue a GA4 day can touch, late days, the engine code: engine.impact_any.input_sig).
  * app_step: right after an app's uninstall evaluation. Its sig unchanged and its file there → kept untouched (most
    hourly builds compute nothing: a store changes when GA4 is fetched, ~once a day). Else every candidate date of the
    app is evaluated as a pseudo-release (engine.impact_any.build_app) → impact_any_<key>.json.gz (deterministic,
    rewritten only on change) — while this build's computing stays within BUDGET_SEC; past it, the app keeps its
    older file (index "fresh": false) or waits (no file yet: "pending"), and the next build goes on.
  * finish: the index (per app: its file, first / last date, data / settled till, fresh), stale files removed. Its ONE
    counts-only log line and its _headers rule ("/impact_any_*": no-store) come from build_static.build
    (_impact_any_tail, right after the Uninstall step): the Uninstall step's own outputs — its returned file list, its
    log lines — stay exactly as without the feature.
  * off(out_dir): the switch (repo variable IMPACT_ANY=false): every file of it removed, nothing printed — the site as
    without the feature.
  * side by side (IMPACT_ANY_WORKERS, default WORKERS; 0 = in the build's own process, as before): an app to rebuild is
    handed — a pickled copy of its store and revenue as app_step got them — to a small process pool and built there
    while the build goes on with the next apps; its file is written, and the budget rule above applied, in APP ORDER
    (an app is built only if the earlier apps' computing seconds are under BUDGET_SEC), as the jobs finish and at the
    latest in finish(). The file bytes are the same (the same engine on the same inputs, serialized as
    write_json_gz_stable does); a job the pool can not run is built here from its copy.

Failure-isolated: an app that raises costs only its own file (left out of the index, its file removed), never the
Uninstall step. No alert or notification ever comes from here. PRIVACY: the log line has counts only.
"""

import gzip
import hashlib
import json
import os
import pickle
import re
import sys
import time

from .db import write_gz_stable, write_json_gz_stable
from .engine import impact_any as ia

PREFIX = "impact_any_"
INDEX = "impact_any_index.json.gz"
FILE_RE = re.compile(r"^impact_any_[0-9a-f]{12}\.json\.gz$")
INDEX_V = 1
BUDGET_SEC = 150              # this step's computing per build at most (+ the app under way): the hourly build
                              # stays within ~3 minutes more even when every app is rebuilt (a code change, a first run)
LINE = None                   # this build's counts line (build_static.build prints it: pop_line)
WORKERS = 2                   # apps rebuilt side by side in their own processes (IMPACT_ANY_WORKERS; 0 = inline)
RUNS = {"pool": 0, "here": 0}  # this build's side-by-side jobs: built in the pool / here from their copy (tests read it)


def enabled(s):
    return bool((s or {}).get("impact_any", True))


def _old_index(out_dir):
    try:
        with open(os.path.join(out_dir, INDEX), "rb") as f:
            idx = json.loads(gzip.decompress(f.read()))
        if idx.get("v") == INDEX_V and idx.get("file_v") == ia.V:
            return {a["app_id"]: a for a in idx.get("apps") or [] if isinstance(a, dict) and a.get("app_id")}
    except Exception:
        pass
    return {}


def start(out_dir, s=None, clock=None):
    """The step's accumulator for one build (the previous index read: what each app's file was built from)."""
    global LINE
    LINE = None
    RUNS.update(pool=0, here=0)
    try:
        workers = max(0, int((s or {}).get("impact_any_workers", WORKERS) or 0))
    except (TypeError, ValueError):
        workers = 0
    return {"code": ia.code_sig(), "old": _old_index(out_dir), "index": [], "files": [], "built": 0, "kept": 0,
            "stale": 0, "pending": 0, "failed": 0, "failed_windows": 0, "dates": 0, "spent": 0.0,
            "budget": float((s or {}).get("impact_any_budget_sec", BUDGET_SEC)), "clock": clock or time.monotonic,
            "workers": workers, "pool": None, "jobs": []}


def _file_sig(path):
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()


def app_step(acc, out_dir, store, a, key, path, rev, late):
    """One app (its store as evaluate_app got it, the same revenue) → its lazy file + index line in acc. Never
    raises."""
    name = PREFIX + key + ".json.gz"
    fp = os.path.join(out_dir, name)
    try:
        E = ia._d(store["window_end"])
        sig = ia.input_sig(_file_sig(path), rev, E, late, acc["code"], store.get("time_zone"))
        old = acc["old"].get(a["app_id"])
        have = old is not None and old.get("file") == name and os.path.exists(fp)
        if have and old.get("sig") == sig:
            line = dict(old, fresh=True)
            acc["kept"] += 1
        else:
            payload = None
            if acc.get("workers"):
                _settle(acc, wait=False)                # the earlier apps' jobs that are done, in order
                try:
                    payload = pickle.dumps((store, rev, a["app_id"], key, sig, late, name),
                                           protocol=pickle.HIGHEST_PROTOCOL)
                except Exception:                       # (not picklable: built here, after the earlier apps)
                    _settle(acc, wait=True)
            if acc["spent"] >= acc["budget"]:          # this build's computing is spent: the next build goes on
                line = _past_budget(acc, a, key, have, old)   # (spent only grows: past it now, past it in order)
            elif payload is not None:                   # built side by side: written in order (_settle)
                _queue(acc, payload, name, fp, a, key, have, old)
                return
            else:
                t0 = acc["clock"]()
                try:
                    body, failed = ia.build_app(store, rev, a["app_id"], key, sig, late)
                    write_json_gz_stable(fp, body)
                finally:
                    acc["spent"] += acc["clock"]() - t0
                line = ia.index_entry(body, name)
                acc["built"] += 1
                acc["failed_windows"] += failed
        _add(acc, line, name)
    except Exception:
        acc["failed"] += 1


def _past_budget(acc, a, key, have, old):
    if have:
        acc["stale"] += 1
        return dict(old, fresh=False)
    acc["pending"] += 1
    return {"app_id": a["app_id"], "key": key, "file": None, "pending": True}


def _add(acc, line, name, at=None):
    """The app's index line (at: its place, held since app_step) and its file."""
    if line.get("file"):
        acc["files"].append(name)
        acc["dates"] += int(line.get("dates") or 0)
    if at is None:
        acc["index"].append(line)
    else:
        acc["index"][at] = line


# ── side by side: an app's build in a process of its own, its file written and counted in app order ────────────────

class _Job:
    __slots__ = ("payload", "name", "fp", "a", "key", "have", "old", "fut")

    def __init__(self, payload, name, fp, a, key, have, old):
        self.payload, self.name, self.fp, self.a, self.key, self.have, self.old = payload, name, fp, a, key, have, old
        self.fut = None


def _raw(body):
    """The file's bytes before gzip — write_json_gz_stable's own serialization."""
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _job(payload):
    """One app's build from its pickled inputs (in a pool process, or here when the pool can not run it) → {"raw",
    "failed", "entry", "sec"} or {"err", "sec"}; never raises."""
    t0 = time.monotonic()
    try:
        store, rev, app_id, key, sig, late, name = pickle.loads(payload)
        body, failed = ia.build_app(store, rev, app_id, key, sig, late)
        return {"raw": _raw(body), "failed": failed, "entry": ia.index_entry(body, name), "sec": time.monotonic() - t0}
    except Exception as e:
        return {"err": type(e).__name__, "sec": time.monotonic() - t0}


def _pool(acc):
    if acc["pool"] is None:
        try:
            import multiprocessing as mp
            from concurrent.futures import ProcessPoolExecutor
            acc["pool"] = ProcessPoolExecutor(max_workers=acc["workers"], mp_context=mp.get_context("spawn"))
        except Exception:
            acc["pool"] = False
    return acc["pool"] or None


def _queue(acc, payload, name, fp, a, key, have, old):
    job = _Job(payload, name, fp, a, key, have, old)
    pool = _pool(acc)
    if pool is not None:
        try:
            job.fut = pool.submit(_job, payload)
        except Exception:                               # the pool can not take it: built here from the copy (_settle)
            acc["pool"] = False
    acc["jobs"].append(job)
    acc["index"].append(job)                            # its place in the index (app order), the line once settled


def _settle(acc, wait):
    """The queued apps in app order: each decided by today's budget rule on the seconds of the apps before it, its file
    written; wait False: only while the next one's job is done."""
    while acc["jobs"]:
        job = acc["jobs"][0]
        if not wait and job.fut is not None and not job.fut.done():
            return
        acc["jobs"].pop(0)
        at = next(i for i, x in enumerate(acc["index"]) if x is job)
        if acc["spent"] >= acc["budget"]:
            if job.fut is not None:
                job.fut.cancel()
            _add(acc, _past_budget(acc, job.a, job.key, job.have, job.old), job.name, at)
            continue
        res = None
        if job.fut is not None:
            try:
                res = job.fut.result()
            except Exception:                           # the pool broke: this one and the rest built here
                acc["pool"] = False
        if res is None:
            res = _job(job.payload)
            RUNS["here"] += 1
        else:
            RUNS["pool"] += 1
        acc["spent"] += res["sec"]
        line = None
        if "err" not in res:
            t0 = acc["clock"]()
            try:
                write_gz_stable(job.fp, res["raw"])
                line = res["entry"]
            except Exception:
                line = None
            finally:
                acc["spent"] += acc["clock"]() - t0
        if line is None:
            del acc["index"][at]
            acc["failed"] += 1
            continue
        acc["built"] += 1
        acc["failed_windows"] += res["failed"]
        _add(acc, line, job.name, at)


def _close(acc):
    pool, acc["pool"] = acc.get("pool"), False
    if pool:
        try:
            pool.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass


def finish(acc, out_dir):
    """The index, stale files removed, the log line (LINE) → the site file names of the feature. Never raises."""
    global LINE
    try:
        try:
            _settle(acc, wait=True)                     # the apps built side by side, in order
        finally:
            _close(acc)
        keep = set(acc["files"])
        for f in os.listdir(out_dir):
            if FILE_RE.match(f) and f not in keep:
                try:
                    os.remove(os.path.join(out_dir, f))
                except OSError:
                    pass
        idx = {"v": INDEX_V, "file_v": ia.V, "history_days": ia.HISTORY_DAYS, "windows": list(ia.WINDOWS),
               "apps": sorted(acc["index"], key=lambda x: x["app_id"])}
        write_json_gz_stable(os.path.join(out_dir, INDEX), idx)
        LINE = ("impact any: apps %d, built %d, kept %d, stale %d, pending %d, failed %d, dates %d, failed windows %d"
                % (len(acc["index"]) + acc["failed"], acc["built"], acc["kept"], acc["stale"], acc["pending"],
                   acc["failed"], acc["dates"], acc["failed_windows"]))
        return [INDEX] + sorted(keep)
    except Exception as e:
        try:
            os.remove(os.path.join(out_dir, INDEX))
        except OSError:
            pass
        print("impact any skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    """The switch off: every file of the feature removed (a rollback leaves the site as without it), no log line."""
    global LINE
    LINE = None
    try:
        for f in os.listdir(out_dir):
            if FILE_RE.match(f) or f == INDEX:
                os.remove(os.path.join(out_dir, f))
    except OSError:
        pass


def pop_line():
    """This build's counts line (None when the step did not run) — once."""
    global LINE
    line, LINE = LINE, None
    return line
