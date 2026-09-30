"""The Review API Worker's own node:test suite (review_worker/test/*.test.js: Access JWT auth, CSRF, every action and
admin decision, the D1 schema over a node:sqlite fake), run from the Python suite so one command covers both. Skipped
where node (≥ 22.5, for node:sqlite) or the review_worker folder is missing."""

import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WDIR = os.path.join(ROOT, "review_worker")
NODE = shutil.which("node")


def _node_ok():
    if NODE is None or not os.path.isdir(os.path.join(WDIR, "test")):
        return False
    try:
        v = subprocess.run([NODE, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    m = re.match(r"^v(\d+)\.(\d+)", v)
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (22, 5)


pytestmark = pytest.mark.skipif(not _node_ok(), reason="node >= 22.5 or review_worker/ not available")


def test_worker_node_suite_passes():
    tests = sorted(n for n in os.listdir(os.path.join(WDIR, "test")) if n.endswith(".test.js"))
    assert tests, "no review_worker/test/*.test.js"
    out = subprocess.run([NODE, "--test", *[os.path.join("test", n) for n in tests]], cwd=WDIR, capture_output=True,
                         text=True, timeout=600)
    assert out.returncode == 0, (out.stdout[-4000:], out.stderr[-2000:])
    assert re.search(r"^ℹ fail 0$", out.stdout, re.M), out.stdout[-2000:]


def test_worker_sources_parse():
    src = os.path.join(WDIR, "src")
    if not os.path.isdir(src):
        pytest.skip("review_worker/src not available")
    for n in sorted(os.listdir(src)):
        if n.endswith(".js"):
            out = subprocess.run([NODE, "--check", os.path.join(src, n)], capture_output=True, text=True, timeout=60)
            assert out.returncode == 0, (n, out.stderr[-1000:])
