"""admob_iq.health — a build step that fails is SEEN (the dashboard's red banner, the public log's health line), not
only written to the private build log (1–3 Nov 2026: the eCPM "same time yesterday" step failed on every build for two
days and nobody could tell). Offline; step names are the codebase's own labels."""
import io
import json
import os
import re
import sys

import pytest

from admob_iq import health

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def clean():
    health.FAULTS.clear()
    yield
    health.FAULTS.clear()


def test_the_lines_the_codebase_prints_count_as_failed_steps():
    for line in ("ecpm intraday skipped: ZoneInfoNotFoundError", "Review Studio skipped: KeyError",
                 "ga4 nvr by country skipped: HttpError", "roas: 3 apps; ga4 audience skipped: RefreshError",
                 "mediation ad-unit history backfill skipped: TimeoutError: read timed out",
                 "roas build skipped: 'App 9' missing for acct-PRIVATE", "app icons skipped: Demo icon 404"):
        health.scan(line)
    # a message is never kept (it can carry ids): only the label and an exception TYPE
    assert health.FAULTS == {"ecpm intraday": "ZoneInfoNotFoundError", "Review Studio": "KeyError",
                             "ga4 nvr by country": "HttpError", "ga4 audience": "RefreshError",
                             "mediation ad-unit history backfill": "TimeoutError", "roas build": "error",
                             "app icons": "error"}
    for line in ("roas: D0 fixed till 2026-11-01 · 3 store-days fixed this run", "roi: apps 9, skipped 2, failed 0",
                 "ga4 audience: 4 apps, 2 skipped: quota", "roi skipped for an app: KeyError", "build complete"):
        health.scan(line)
    assert len(health.FAULTS) == 7                                      # none of these is a failed step


def test_the_stderr_reader_changes_nothing_printed_and_records_failures(monkeypatch):
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", buf)
    health.watch()
    health.watch()                                                      # once: no reader on a reader
    assert isinstance(sys.stderr, health._Tee) and sys.stderr._s is buf
    print("gads geo skipped: Http", end="", file=sys.stderr)          # a line written in parts
    print("Error\nok line", file=sys.stderr)
    sys.stderr.flush()
    assert buf.getvalue() == "gads geo skipped: HttpError\nok line\n" and health.FAULTS == {"gads geo": "HttpError"}
    assert sys.stderr.getvalue() == buf.getvalue()                    # anything else: the stream's own


def test_attach_sets_and_clears_the_step_fault_and_keeps_the_others(tmp_path, capsys):
    d = {"build_faults": [{"kind": "tz", "names": ["X/Y"], "of": 2}, {"kind": "step", "steps": [{"name": "old"}]}]}
    health.fault("roi", ValueError("x"))
    health.fault("ecpm intraday", "stale")
    health.attach(d)
    assert d["build_faults"] == [{"kind": "tz", "names": ["X/Y"], "of": 2},
                                 {"kind": "step", "steps": [{"name": "ecpm intraday", "error": "stale"},
                                                            {"name": "roi", "error": "ValueError"}]}]
    out = tmp_path / "h.json"
    health.write_public(str(out))
    health.public(str(out))
    line = capsys.readouterr().out.strip()
    assert line == ("::warning::health: 2 build step(s) failed — ecpm intraday, roi — their part of the dashboard is"
                    " not updating (red banner on the page)")
    health.FAULTS.clear()
    health.attach(d)
    assert d["build_faults"] == [{"kind": "tz", "names": ["X/Y"], "of": 2}]
    d2 = {"build_faults": [{"kind": "step", "steps": []}]}
    health.attach(d2)
    assert "build_faults" not in d2
    health.write_public(str(out))
    health.public(str(out))
    assert capsys.readouterr().out.strip() == "health: every build step ran"
    health.public(str(tmp_path / "none.json"))
    assert "no result" in capsys.readouterr().out


def test_every_step_failure_line_in_the_code_is_one_the_reader_counts():
    """The rule that keeps this permanent: a failure-isolated step logs "<step> skipped: <...>" with a plain label first
    (letters, digits, space, _ . / -) — then health counts it with no other change. A label the reader cannot parse
    would make that step's failure silent again."""
    lit = re.compile(r"""f?["']([^"']*?) skipped: """)
    bad, n = [], 0
    for base, _, files in os.walk(os.path.join(ROOT, "admob_iq")):
        for fn in files:
            if not fn.endswith(".py") or fn.endswith("_probe.py") or fn == "health.py":
                continue
            path = os.path.join(base, fn)
            for i, line in enumerate(open(path, encoding="utf-8"), 1):
                m = lit.search(line)
                if not m or line.lstrip().startswith("#"):
                    continue
                n += 1
                label = re.sub(r"\{[^}]*\}|%[sd]", "x", m.group(1))     # a placeholder in the label: one word
                if not health.NAME.fullmatch(label):
                    bad.append("%s:%d %r" % (os.path.relpath(path, ROOT), i, m.group(1)))
    assert n >= 60 and bad == []
