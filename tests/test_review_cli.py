"""Daily App Review — the CLI (python -m admob_iq.review): runs ONLY the review builder over an already-built site,
ignores REVIEW_ENABLED, prints the same one counts-only line as the build, --force ignores the ready time, --rebuild
rewrites the --today snapshot once, and the exit code says whether the day's build failed."""

import gzip
import json
import os
import re
import subprocess
import sys
from datetime import timedelta

import pytest

from admob_iq.review import __main__ as cli
from admob_iq.review import store as rstore
from tests import review_synth as rs
from tests.test_review_build import LOG, SECRETS, at_ist, check_doc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = rs.DAY.isoformat()


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    for k in ("REVIEW_ENABLED", "REVIEW_READY_IST", "REVIEW_REBUILD_DAY"):
        monkeypatch.delenv(k, raising=False)
    site, data = str(tmp_path / "site"), str(tmp_path / "data")
    rs.make_site(site)
    return site, data


def main(site, data, *extra):
    return cli.main(["--site", site, "--data", data, *extra])


def err_lines(capsys):
    cap = capsys.readouterr()
    assert cap.out == ""
    return [x for x in cap.err.splitlines() if x]


def test_force_writes_both_trees_before_the_ready_time(dirs, capsys, monkeypatch):
    site, data = dirs
    monkeypatch.setenv("REVIEW_ENABLED", "false")                       # the CLI ignores it
    early = at_ist(rs.DAY, "06:00").strftime("%Y-%m-%dT%H:%M:%SZ")
    assert main(site, data, "--now", early) == 0                         # not ready, no --force: waits (exit 0)
    lines = err_lines(capsys)
    assert len(lines) == 1 and LOG.match(lines[0]) and "waiting (ready 09:00 IST) · open none" in lines[0]
    assert not os.path.exists(rstore.day_path(data, DS))
    assert main(site, data, "--now", early, "--force") == 0
    lines = err_lines(capsys)
    assert len(lines) == 1 and LOG.match(lines[0])
    assert lines[0].startswith(f"review: day {DS} · built (apps 7, top 4, ok 2, small 1, failed 0) · days 1 · published 1")
    doc = rstore.read_doc(rstore.day_path(data, DS), DS)
    check_doc(doc)
    assert doc["built_at"] == early
    site_copy = os.path.join(site, "review", "days", f"{DS}.json.gz")
    with open(site_copy, "rb") as a, open(rstore.day_path(data, DS), "rb") as b:
        assert a.read() == b.read()
    idx = json.load(open(os.path.join(site, "review", "index.json"), encoding="utf-8"))
    assert idx["open_day"] == DS and idx["go_live"] == DS and idx["pending_today"] is False
    for s in SECRETS:
        assert s not in lines[0]


def test_today_picks_the_day_and_two_days_make_a_history(dirs, capsys):
    site, data = dirs
    d0 = (rs.DAY - timedelta(1)).isoformat()
    assert main(site, data, "--today", d0, "--force") == 0
    assert main(site, data, "--today", DS, "--force") == 0
    lines = err_lines(capsys)
    assert len(lines) == 2 and all(LOG.match(x) for x in lines)
    assert lines[0].startswith(f"review: day {d0} · built") and lines[1].startswith(f"review: day {DS} · built")
    idx = json.load(open(os.path.join(site, "review", "index.json"), encoding="utf-8"))
    assert [x["d"] for x in idx["days"]] == [d0, DS] and idx["go_live"] == d0 and idx["open_day"] == DS
    assert json.load(gzip.open(rstore.day_path(data, d0)))["day"] == d0


def test_rebuild_rewrites_the_day_once(dirs, capsys):
    site, data = dirs
    assert main(site, data, "--today", DS, "--now", "2026-10-01T04:00:00Z") == 0
    first = open(rstore.day_path(data, DS), "rb").read()
    assert main(site, data, "--today", DS, "--now", "2026-10-01T05:00:00Z") == 0      # exists: untouched
    assert open(rstore.day_path(data, DS), "rb").read() == first
    assert main(site, data, "--today", DS, "--now", "2026-10-01T06:00:00Z", "--rebuild") == 0
    second = open(rstore.day_path(data, DS), "rb").read()
    assert second != first and json.loads(gzip.decompress(second))["built_at"] == "2026-10-01T06:00:00Z"
    assert main(site, data, "--today", DS, "--now", "2026-10-01T07:00:00Z", "--rebuild") == 0   # used up
    assert open(rstore.day_path(data, DS), "rb").read() == second
    lines = err_lines(capsys)
    assert [re.search(r"· (built|exists|rebuilt)", x).group(1) for x in lines] == ["built", "exists", "rebuilt", "exists"]
    assert all(LOG.match(x) for x in lines)
    meta = json.load(open(os.path.join(data, "review", "meta.json"), encoding="utf-8"))
    assert meta["rebuilt"] == {DS: "2026-10-01T06:00:00Z"}


def test_exit_codes(dirs, capsys, monkeypatch):
    site, data = dirs
    assert main(site, data, "--today", "2026-13-40") == 1
    assert main(site, data, "--now", "yesterday") == 1
    assert err_lines(capsys) == ["review: bad --now / --today", "review: bad --now / --today"]
    with pytest.raises(SystemExit) as e:
        cli.main(["--data", data])                                           # --site is required
    assert e.value.code == 2
    capsys.readouterr()
    monkeypatch.setattr(rstore, "build_day", lambda *a, **k: (_ for _ in ()).throw(KeyError("x")))
    assert main(site, data, "--today", DS, "--force") == 1
    lines = err_lines(capsys)
    assert len(lines) == 1 and LOG.match(lines[0]) and "failed (KeyError) · retry next run" in lines[0]
    monkeypatch.undo()
    for k in ("REVIEW_ENABLED", "REVIEW_READY_IST", "REVIEW_REBUILD_DAY"):
        monkeypatch.delenv(k, raising=False)
    os.remove(os.path.join(site, "dashboard.json.gz"))                      # unreadable site: the day fails
    assert main(site, data, "--today", DS, "--force") == 1
    assert "failed (ReviewBuildError)" in err_lines(capsys)[0]


def test_the_module_entry_point(dirs):
    site, data = dirs
    env = {k: v for k, v in os.environ.items() if not k.startswith("REVIEW_")}
    out = subprocess.run([sys.executable, "-m", "admob_iq.review", "--site", site, "--data", data, "--today", DS,
                          "--force"], cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
    assert out.returncode == 0 and out.stdout == ""
    lines = out.stderr.splitlines()
    assert len(lines) == 1 and LOG.match(lines[0]) and "· built (apps 7," in lines[0]
    assert os.path.exists(os.path.join(site, "review", "index.json"))
