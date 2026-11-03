"""Feature health — a build step that fails must be SEEN on the dashboard, not only in the private build log.

Every optional step of the build is failure-isolated: on an error the dashboard is built without that part and the log
gets one "<step> skipped: <ErrorType>" line (a few older ones print the message instead of the type). That log is private and nobody reads it, so a step that fails on EVERY build
looks like a working dashboard with one part quietly frozen (1–3 Nov 2026: the eCPM "same time yesterday" step raised
on every build for two days after the runner image changed). watch() puts a reader on the build's stderr that records
every "<step> skipped: <ErrorType>" line as it is printed — every step of the codebase logs its failure that way, so
each one (and every future one written the same way) counts without touching it; fault() records one directly.
attach() puts this build's failures in dashboard["build_faults"] — the page's red banner names the parts that are not
updating — and write_public() the step names for the public log (fixed code labels, never data: no app, id or amount).
Never raises, and never changes what is printed."""
import json
import re
import sys

FAULTS = {}          # this build's failed steps: {step name: error TYPE, or "error" when the line has no type}
# "<step> skipped: <ErrorType or message>" at a line's start or after a "; " / " | " / " · " separator (a combined
# counts line). Only the step's label and an exception TYPE are kept — a message (it can carry ids) never is. Counts
# lines say "skipped 3" (no colon): never a failure.
SKIP = re.compile(r"(?:^|; |\| |· )([A-Za-z][A-Za-z0-9 _./-]{0,60}?) skipped: (\S*)")
NAME = re.compile(r"[A-Za-z][A-Za-z0-9 _./-]{0,60}")
TYPE = re.compile(r"[A-Z][A-Za-z0-9_]*(?:Error|Exception|Exit|Interrupt|Warning|Timeout)")


def scan(line):
    """Record every step failure a printed line reports."""
    for m in SKIP.finditer(line or ""):
        tok = m.group(2).rstrip(":,;.")
        fault(m.group(1).strip(), tok if TYPE.fullmatch(tok) else "error")


class _Tee:
    """sys.stderr as it was, plus a line reader for scan(): writes go through unchanged; anything else is the stream's."""

    def __init__(self, stream):
        self._s, self._buf = stream, ""

    def write(self, text):
        n = self._s.write(text)
        try:
            self._buf += text
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                scan(line)
            self._buf = self._buf[-4000:]
        except Exception:
            pass
        return n

    def flush(self):
        return self._s.flush()

    def __getattr__(self, name):
        return getattr(self._s, name)


def watch():
    """Read the build's stderr for step failures from now on (once)."""
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr)


def fault(name, exc):
    """Record a failed step (exc: the exception, or a short reason)."""
    try:
        FAULTS[str(name)] = type(exc).__name__ if isinstance(exc, BaseException) else str(exc)
    except Exception:
        pass


def attach(dashboard):
    """dashboard["build_faults"]: its "step" entry set to this build's failed steps (other kinds kept), removed when none."""
    try:
        keep = [f for f in dashboard.get("build_faults") or () if isinstance(f, dict) and f.get("kind") != "step"]
        if FAULTS:
            keep.append({"kind": "step", "steps": [{"name": n, "error": e} for n, e in sorted(FAULTS.items())]})
        if keep:
            dashboard["build_faults"] = keep
        else:
            dashboard.pop("build_faults", None)
    except Exception as e:
        print("health attach skipped: %s" % type(e).__name__, file=sys.stderr)


def write_public(path):
    """The failed steps of the whole build (the ones after the dashboard was written too) for the public log's line."""
    try:
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"steps": sorted(FAULTS)}, f)
    except Exception:
        pass


def public(path):
    """The public log's line: the failed steps' names (code labels) and their count — never data."""
    try:
        with open(path, encoding="utf-8") as f:
            steps = [str(s) for s in (json.load(f) or {}).get("steps") or []]
    except Exception:
        print("health: no result (the build did not reach it)")
        return
    if steps:
        print("::warning::health: %d build step(s) failed — %s — their part of the dashboard is not updating (red "
              "banner on the page)" % (len(steps), ", ".join(steps)))
    else:
        print("health: every build step ran")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "public":
        public(sys.argv[2])
