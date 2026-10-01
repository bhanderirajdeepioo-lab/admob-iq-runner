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

Failure-isolated: an app that raises costs only its own file (left out of the index, its file removed), never the
Uninstall step. No alert or notification ever comes from here. PRIVACY: the log line has counts only.
"""

import gzip
import hashlib
import json
import os
import re
import sys
import time

from .db import write_json_gz_stable
from .engine import impact_any as ia

PREFIX = "impact_any_"
INDEX = "impact_any_index.json.gz"
FILE_RE = re.compile(r"^impact_any_[0-9a-f]{12}\.json\.gz$")
INDEX_V = 1
BUDGET_SEC = 150              # this step's computing per build at most (+ the app under way): the hourly build
                              # stays within ~3 minutes more even when every app is rebuilt (a code change, a first run)
LINE = None                   # this build's counts line (build_static.build prints it: pop_line)


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
    return {"code": ia.code_sig(), "old": _old_index(out_dir), "index": [], "files": [], "built": 0, "kept": 0,
            "stale": 0, "pending": 0, "failed": 0, "failed_windows": 0, "dates": 0, "spent": 0.0,
            "budget": float((s or {}).get("impact_any_budget_sec", BUDGET_SEC)), "clock": clock or time.monotonic}


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
        elif acc["spent"] >= acc["budget"]:            # this build's computing is spent: the next build goes on
            if have:
                line = dict(old, fresh=False)
                acc["stale"] += 1
            else:
                line = {"app_id": a["app_id"], "key": key, "file": None, "pending": True}
                acc["pending"] += 1
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
        if line.get("file"):
            acc["files"].append(name)
            acc["dates"] += int(line.get("dates") or 0)
        acc["index"].append(line)
    except Exception:
        acc["failed"] += 1


def finish(acc, out_dir):
    """The index, stale files removed, the log line (LINE) → the site file names of the feature. Never raises."""
    global LINE
    try:
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
