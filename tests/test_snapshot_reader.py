"""Snapshot history READER (FileRepo._load_snapshots) for both layouts, with the parts written by hand here — not by the
parts writer — so this holds for any build that has the reader: the parts are read back as the same rows in the same
order, a single file next to them resolves without loss, a lost index.json is rebuilt from the part names (never an
empty history), and the single-file flush removes a parts layout only after the single file holds every row.
Synthetic rows only."""

import gzip
import hashlib
import json
import os
import random

import pytest

from admob_iq import db
from admob_iq.db import FileRepo

KW = {"ensure_ascii": False, "default": str}
PER = 4


def _rows(n, seed, start=0):
    rnd = random.Random(seed)
    return [{"report_date": "2026-%02d-%02d" % (rnd.randint(7, 10), rnd.randint(1, 28)),
             "snapshot_date": "2026-%02d-%02d" % (rnd.randint(7, 10), rnd.randint(1, 28)),
             "account_id": "pub-%d" % (i % 3), "app_id": "app~%d" % (i % 4), "ad_unit_id": "unit/%d" % i,
             "country": rnd.choice(["All", "US", "ü"]), "format": "banner",
             "estimated_earnings_micros": rnd.randint(0, 10 ** 9), "impressions": rnd.randint(0, 10 ** 6)}
            for i in range(start, start + n)]


def _sdir(d):
    return os.path.join(d, "snapshots")


def _legacy(d):
    return os.path.join(d, "snapshots.json.gz")


def _write_parts(d, rows, index=True):
    """The parts layout as the parts writer stores it: positional slices of PER rows, json.dump's text, named by hash."""
    sd = _sdir(d)
    os.makedirs(sd, exist_ok=True)
    entries = []
    for i, lo in enumerate(range(0, len(rows), PER)):
        part = rows[lo:lo + PER]
        text = json.dumps(part, **KW).encode("utf-8")
        sha = hashlib.sha256(text).hexdigest()
        name = "part-%04d-%s.json.gz" % (i, sha[:12])
        with open(os.path.join(sd, name), "wb") as f:
            f.write(gzip.compress(text))
        entries.append({"file": name, "rows": len(part), "sha256": sha, "bytes": len(text), "from": None, "to": None})
    if index:
        with open(os.path.join(sd, "index.json"), "w", encoding="utf-8") as f:
            json.dump({"v": 1, "rows": len(rows), "part_rows": PER, "parts": entries}, f)
    return [e["file"] for e in entries]


def _write_legacy(d, rows):
    os.makedirs(d, exist_ok=True)
    with gzip.open(_legacy(d), "wt", encoding="utf-8") as f:
        json.dump(rows, f, **KW)


def _load(d):
    return FileRepo(d).fetch_snapshots()


@pytest.fixture(autouse=True)
def part_rows(monkeypatch):
    monkeypatch.setattr(db, "SNAP_PART_ROWS", PER)


def test_parts_read_back_as_the_same_rows_in_the_same_order(tmp_path):
    d = str(tmp_path / "data")
    rows = _rows(11, seed=1)
    _write_parts(d, rows)
    assert _load(d) == rows


@pytest.mark.parametrize("single,parts,want", [(9, 5, "single"), (5, 9, "parts"), (7, 7, "parts")])
def test_parts_and_a_single_file_the_one_holding_the_other_wins(tmp_path, single, parts, want):
    d = str(tmp_path / "data")
    rows = _rows(9, seed=2)
    _write_parts(d, rows[:parts])
    _write_legacy(d, rows[:single])
    assert _load(d) == rows[:max(single, parts)]


def test_parts_and_an_unrelated_single_file_are_both_kept(tmp_path):
    d = str(tmp_path / "data")
    hist, newer = _rows(9, seed=3), _rows(3, seed=4, start=100)
    _write_parts(d, hist)
    _write_legacy(d, [hist[2]] + newer)
    assert _load(d) == hist + newer


def test_a_lost_index_is_rebuilt_from_the_part_names(tmp_path):
    d = str(tmp_path / "data")
    rows = _rows(10, seed=5)
    _write_parts(d, rows, index=False)
    assert _load(d) == rows


def test_part_files_that_cannot_be_put_back_in_order_stop_the_load(tmp_path):
    d = str(tmp_path / "data")
    names = _write_parts(d, _rows(10, seed=6), index=False)
    os.remove(os.path.join(_sdir(d), names[1]))
    with pytest.raises(RuntimeError, match="refusing"):
        _load(d)


def test_the_single_file_flush_retires_the_parts_only_once_it_holds_every_row(tmp_path, monkeypatch):
    """The single-file writer (SNAPSHOT_PARTS=false where the parts writer exists): the single file gets json.dump's
    text of every row, then the parts the history was read from go; a part file whose rows were never read stays."""
    monkeypatch.setenv("SNAPSHOT_PARTS", "false")
    d = str(tmp_path / "data")
    rows = _rows(10, seed=7)
    _write_parts(d, rows)
    stray = "part-0009-%s.json.gz" % ("c" * 12)
    with open(os.path.join(_sdir(d), stray), "wb") as f:
        f.write(gzip.compress(json.dumps(_rows(2, seed=8, start=500), **KW).encode("utf-8")))
    repo = FileRepo(d)
    repo.fetch_snapshots()
    added = _rows(2, seed=9, start=300)
    for r in added:
        repo.append_snapshot(dict(r))
    repo.flush()
    with gzip.open(_legacy(d), "rb") as f:
        assert f.read() == json.dumps(rows + added, **KW).encode("utf-8")
    assert sorted(os.listdir(_sdir(d))) == [stray]
    assert _load(d) == rows + added
