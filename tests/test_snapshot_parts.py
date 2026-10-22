"""Snapshot history stored in parts (data/snapshots/): the same rows in the same order after any write / read, a
lossless migration from (and back to) the single snapshots.json.gz, and no loss when either switch stops half way.
Synthetic rows only."""

import gzip
import json
import os
import random

import pytest

from admob_iq import db
from admob_iq.db import FileRepo

KW = {"ensure_ascii": False, "default": str}


def _rows(n, seed=1, start=0):
    rnd = random.Random(seed)
    out = []
    for i in range(start, start + n):
        out.append({"report_date": "2026-%02d-%02d" % (rnd.randint(7, 10), rnd.randint(1, 28)),
                    "snapshot_date": "2026-%02d-%02d" % (rnd.randint(7, 10), rnd.randint(1, 28)),   # not in order
                    "account_id": "pub-%d" % (i % 3), "app_id": "app~%d" % (i % 5), "ad_unit_id": "unit/%d" % i,
                    "country": rnd.choice(["All", "US", "IN"]), "format": rnd.choice(["banner", "app_open"]),
                    "estimated_earnings_micros": rnd.randint(0, 10 ** 9), "impressions": rnd.randint(0, 10 ** 6),
                    "clicks": rnd.randint(0, 999)})
    return out


def _old_text(rows):
    """The single file's text exactly as the writer before this change wrote it (json.dump)."""
    return json.dumps(rows, **KW).encode("utf-8")


def _write_legacy(d, rows):
    os.makedirs(d, exist_ok=True)
    with gzip.open(os.path.join(d, "snapshots.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(rows, f, **KW)


def _legacy(d):
    return os.path.join(d, "snapshots.json.gz")


def _sdir(d):
    return os.path.join(d, "snapshots")


def _index(d):
    with open(os.path.join(_sdir(d), "index.json"), encoding="utf-8") as f:
        return json.load(f)


def _parts_text(d):
    """The parts joined back into the single file's text: inner texts with ', ' inside [ ]."""
    inner = []
    for e in _index(d)["parts"]:
        with gzip.open(os.path.join(_sdir(d), e["file"]), "rb") as f:
            t = f.read()
        assert t[:1] == b"[" and t[-1:] == b"]"
        if t[1:-1]:
            inner.append(t[1:-1])
    return b"[" + b", ".join(inner) + b"]"


def _files(d):
    return sorted(os.listdir(_sdir(d))) if os.path.isdir(_sdir(d)) else []


def _load(d):
    return FileRepo(d).fetch_snapshots()


def _append(repo, rows):
    for r in rows:
        repo.append_snapshot(dict(r))


@pytest.fixture(autouse=True)
def small_parts(monkeypatch):
    monkeypatch.setattr(db, "SNAP_PART_ROWS", 7)
    monkeypatch.delenv("SNAPSHOT_PARTS", raising=False)


def test_round_trip_same_rows_same_order(tmp_path):
    d = str(tmp_path / "data")
    rows = _rows(25)
    repo = FileRepo(d)
    _append(repo, rows)
    repo.flush()
    idx = _index(d)
    assert [e["rows"] for e in idx["parts"]] == [7, 7, 7, 4] and idx["rows"] == 25
    assert _files(d) == sorted([e["file"] for e in idx["parts"]] + ["index.json"])
    assert not os.path.exists(_legacy(d))
    back = _load(d)
    assert back == rows and json.dumps(back, **KW) == json.dumps(rows, **KW)          # same rows, same order
    assert _parts_text(d) == _old_text(rows)                     # joined parts = the old single file, byte for byte
    for e in idx["parts"]:
        with gzip.open(os.path.join(_sdir(d), e["file"]), "rb") as f:
            raw = f.read()
        assert e["bytes"] == len(raw) and e["file"].startswith("part-") and e["sha256"][:12] in e["file"]
        part = json.loads(raw)
        assert (e["from"], e["to"]) == (min(r["snapshot_date"] for r in part), max(r["snapshot_date"] for r in part))


def test_migration_from_the_single_file_is_lossless(tmp_path):
    d = str(tmp_path / "data")
    old = _rows(30, seed=2)
    _write_legacy(d, old)
    repo = FileRepo(d)
    assert repo.fetch_snapshots() == old                         # read from the single file
    new = _rows(5, seed=3, start=1000)
    _append(repo, new + old[:3])                                 # existing keys stay deduped (append-only)
    repo.flush()
    assert not os.path.exists(_legacy(d))                        # removed only after the parts were read back
    assert _parts_text(d) == _old_text(old + new)
    assert _load(d) == old + new


def test_sealed_parts_are_left_untouched_and_only_the_last_part_changes(tmp_path):
    d = str(tmp_path / "data")
    rows = _rows(16)
    repo = FileRepo(d)
    _append(repo, rows)
    repo.flush()
    first = _index(d)["parts"]
    sealed = {e["file"]: os.stat(os.path.join(_sdir(d), e["file"])) for e in first[:2]}
    repo = FileRepo(d)
    repo.fetch_snapshots()
    _append(repo, _rows(9, seed=5, start=500))                   # 16 → 25 rows: part 2 grows, part 3 is new
    repo.flush()
    now = _index(d)["parts"]
    assert [e["file"] for e in now[:2]] == [e["file"] for e in first[:2]]
    for f, st in sealed.items():
        st2 = os.stat(os.path.join(_sdir(d), f))
        assert (st2.st_ino, st2.st_mtime_ns) == (st.st_ino, st.st_mtime_ns)
    assert now[2]["file"] != first[2]["file"] and len(now) == 4
    assert _files(d) == sorted([e["file"] for e in now] + ["index.json"])          # the old last part is gone
    assert _load(d) == rows + _rows(9, seed=5, start=500)


def test_crash_before_the_index_loses_nothing(tmp_path, monkeypatch):
    """A migration that stopped after writing its parts but before index.json: the parts hold the single file's rows
    and that run's new ones, so they are read (index rebuilt from their names) — nothing on disk is dropped — and the
    next flush finishes the migration."""
    d = str(tmp_path / "data")
    old = _rows(20, seed=4)
    _write_legacy(d, old)
    repo = FileRepo(d)
    repo.fetch_snapshots()
    added = _rows(3, seed=6, start=900)
    _append(repo, added)
    real = db._gz_sha
    monkeypatch.setattr(db, "_gz_sha", lambda p: (_ for _ in ()).throw(RuntimeError("power cut")))
    with pytest.raises(RuntimeError):
        repo.flush()                                             # parts written, read-back never finished
    monkeypatch.setattr(db, "_gz_sha", real)
    assert os.path.exists(_legacy(d)) and not os.path.exists(os.path.join(_sdir(d), "index.json"))
    assert _load(d) == old + added                               # the single file's rows first, none lost
    again = FileRepo(d)
    again.fetch_snapshots()
    again.flush()                                                # the migration finishes
    assert not os.path.exists(_legacy(d)) and _load(d) == old + added
    assert _files(d) == sorted([e["file"] for e in _index(d)["parts"]] + ["index.json"])   # leftovers removed


def test_crash_while_the_first_parts_were_written_keeps_the_single_file(tmp_path, monkeypatch):
    """A migration that stopped after its first part: that part's rows are the single file's first rows, so the single
    file is the history; the next flush migrates again and removes the leftover."""
    d = str(tmp_path / "data")
    old = _rows(20, seed=16)
    _write_legacy(d, old)
    repo = FileRepo(d)
    repo.fetch_snapshots()
    real = db._gz_write
    n = []

    def write(tmp, chunks):
        if n:
            raise KeyboardInterrupt("power cut")
        n.append(1)
        return real(tmp, chunks)
    monkeypatch.setattr(db, "_gz_write", write)
    with pytest.raises(KeyboardInterrupt):
        repo.flush()
    monkeypatch.setattr(db, "_gz_write", real)
    assert len(db._snap_part_files(_sdir(d))) == 1
    assert _load(d) == old
    again = FileRepo(d)
    again.fetch_snapshots()
    again.flush()
    assert not os.path.exists(_legacy(d)) and _load(d) == old
    assert _files(d) == sorted([e["file"] for e in _index(d)["parts"]] + ["index.json"])


def test_crash_after_the_index_before_the_single_file_went(tmp_path, monkeypatch):
    d = str(tmp_path / "data")
    old = _rows(20, seed=7)
    _write_legacy(d, old)
    repo = FileRepo(d)
    repo.fetch_snapshots()
    added = _rows(4, seed=8, start=700)
    _append(repo, added)
    real = db._rm

    def rm(p):
        if p.endswith("snapshots.json.gz"):
            raise KeyboardInterrupt("power cut")
        real(p)
    monkeypatch.setattr(db, "_rm", rm)
    with pytest.raises(KeyboardInterrupt):
        repo.flush()
    monkeypatch.setattr(db, "_rm", real)
    assert os.path.exists(_legacy(d)) and os.path.exists(os.path.join(_sdir(d), "index.json"))
    assert db._snap_relation(_sdir(d), _index(d), os.path.join(d, "snapshots.json")) == "parts"
    assert _load(d) == old + added                               # the parts hold the single file's rows and more
    again = FileRepo(d)
    again.fetch_snapshots()
    again.flush()
    assert not os.path.exists(_legacy(d)) and _load(d) == old + added


def test_switch_back_to_the_single_file_and_a_crash_half_way(tmp_path, monkeypatch):
    d = str(tmp_path / "data")
    rows = _rows(18, seed=9)
    repo = FileRepo(d)
    _append(repo, rows)
    repo.flush()
    monkeypatch.setenv("SNAPSHOT_PARTS", "false")
    repo = FileRepo(d)
    assert repo.fetch_snapshots() == rows                        # still read from the parts
    added = _rows(2, seed=10, start=800)
    _append(repo, added)
    real = db._snap_remove_parts
    monkeypatch.setattr(db, "_snap_remove_parts", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt("cut")))
    with pytest.raises(KeyboardInterrupt):
        repo.flush()                                             # single file written, parts not yet removed
    monkeypatch.setattr(db, "_snap_remove_parts", real)
    assert db._snap_relation(_sdir(d), _index(d), os.path.join(d, "snapshots.json")) == "legacy"
    assert _load(d) == rows + added                              # the single file holds everything: it wins
    again = FileRepo(d)
    again.fetch_snapshots()
    again.flush()
    assert not os.path.isdir(_sdir(d))
    with gzip.open(_legacy(d), "rb") as f:
        assert f.read() == _old_text(rows + added)               # exactly the old single file
    monkeypatch.setenv("SNAPSHOT_PARTS", "true")                 # and forward again
    again = FileRepo(d)
    again.fetch_snapshots()
    again.flush()
    assert not os.path.exists(_legacy(d)) and _load(d) == rows + added


def test_a_single_file_started_next_to_the_parts_is_merged_not_lost(tmp_path):
    """A build without parts support (an older checkout) finds no snapshots.json.gz, starts a new one next to the parts:
    the next build keeps every part row and adds the new file's rows the parts lack, in the new file's order."""
    d = str(tmp_path / "data")
    hist = _rows(15, seed=11)
    repo = FileRepo(d)
    _append(repo, hist)
    repo.flush()
    newer = _rows(4, seed=12, start=600)
    _write_legacy(d, [hist[3]] + newer)                          # one row the parts already have
    assert db._snap_relation(_sdir(d), _index(d), os.path.join(d, "snapshots.json")) == "other"
    repo = FileRepo(d)
    assert repo.fetch_snapshots() == hist + newer
    repo.flush()
    assert not os.path.exists(_legacy(d)) and _load(d) == hist + newer


@pytest.mark.parametrize("legacy_rows,part_rows,want", [
    (0, 0, "same"), (5, 5, "same"), (0, 3, "parts"), (3, 0, "legacy"), (2, 9, "parts"), (9, 2, "legacy"),
    (7, 7, "same"), (7, 14, "parts"), (14, 7, "legacy")])
def test_relation_of_parts_and_single_file(tmp_path, legacy_rows, part_rows, want):
    d = str(tmp_path / "data")
    rows = _rows(max(legacy_rows, part_rows), seed=13)
    repo = FileRepo(d)
    repo.fetch_snapshots()                                       # (touched, so even 0 rows are written as parts)
    _append(repo, rows[:part_rows])
    repo.flush()
    _write_legacy(d, rows[:legacy_rows])
    assert db._snap_relation(_sdir(d), _index(d), os.path.join(d, "snapshots.json")) == want
    assert _load(d) == rows[:max(legacy_rows, part_rows)]


def test_relation_spots_a_changed_row(tmp_path):
    d = str(tmp_path / "data")
    rows = _rows(10, seed=14)
    repo = FileRepo(d)
    _append(repo, rows)
    repo.flush()
    other = json.loads(json.dumps(rows))
    other[4]["clicks"] += 1
    _write_legacy(d, other)
    assert db._snap_relation(_sdir(d), _index(d), os.path.join(d, "snapshots.json")) == "other"


def test_a_missing_part_stops_the_build_instead_of_losing_history(tmp_path):
    d = str(tmp_path / "data")
    repo = FileRepo(d)
    _append(repo, _rows(20))
    repo.flush()
    os.remove(os.path.join(_sdir(d), _index(d)["parts"][1]["file"]))
    with pytest.raises(FileNotFoundError):
        _load(d)


def test_a_part_that_differs_from_its_index_is_read_as_it_is_and_rewritten(tmp_path):
    d = str(tmp_path / "data")
    rows = _rows(14, seed=15)
    repo = FileRepo(d)
    _append(repo, rows)
    repo.flush()
    e = _index(d)["parts"][0]
    p = os.path.join(_sdir(d), e["file"])
    edited = json.loads(gzip.open(p, "rb").read())
    edited[0]["clicks"] = 123456
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(json.dumps(edited, indent=0))                    # not the writer's own layout either
    repo = FileRepo(d)
    assert repo.fetch_snapshots() == edited + rows[7:]
    repo.flush()
    assert _parts_text(d) == _old_text(edited + rows[7:]) and _index(d)["parts"][0]["file"] != e["file"]


def test_empty_history(tmp_path):
    d = str(tmp_path / "data")
    repo = FileRepo(d)
    repo.fetch_snapshots()
    repo.flush()
    assert _index(d)["parts"] == [] and _load(d) == []


def test_default_part_size_stays_far_under_githubs_limits():
    import re
    with open(db.__file__, encoding="utf-8") as f:
        src = f.read()
    # a part of 1M short rows gzips far under GitHub's 50 MB warning (100 MB refused)
    assert re.search(r"^SNAP_PART_ROWS = 1_000_000 ", src, re.M) and db.SNAP_DIR == "snapshots"


def _parts_on_disk(d):
    return [f for f in _files(d) if f.startswith("part-")]


def test_a_lost_index_is_rebuilt_from_the_part_names_and_nothing_is_deleted(tmp_path):
    """index.json lost (a copy or merge that dropped it), the parts still there: the history is read back whole from
    the part names, and the next flush keeps every row."""
    d = str(tmp_path / "data")
    rows = _rows(19, seed=17)
    repo = FileRepo(d)
    _append(repo, rows)
    repo.flush()
    os.remove(os.path.join(_sdir(d), "index.json"))
    repo = FileRepo(d)
    assert repo.fetch_snapshots() == rows
    added = _rows(1, seed=18, start=950)
    _append(repo, added)
    repo.flush()
    assert _load(d) == rows + added and _parts_text(d) == _old_text(rows + added)
    assert _files(d) == sorted([e["file"] for e in _index(d)["parts"]] + ["index.json"])


@pytest.mark.parametrize("damage", ["gap", "two with one number", "edited part", "short middle part", "odd name"])
def test_part_files_that_cannot_be_put_back_in_order_stop_the_load(tmp_path, damage):
    """Without index.json and without a single file, part files that do not form one unbroken, checked list stop the
    load (the build fails loudly) instead of an empty or partial history being written over them."""
    d = str(tmp_path / "data")
    repo = FileRepo(d)
    _append(repo, _rows(25, seed=19))
    repo.flush()
    parts = _index(d)["parts"]
    os.remove(os.path.join(_sdir(d), "index.json"))
    sd = _sdir(d)
    if damage == "gap":
        os.remove(os.path.join(sd, parts[1]["file"]))
    elif damage == "two with one number":
        with open(os.path.join(sd, "part-0002-%s.json.gz" % ("0" * 12)), "wb") as f:
            f.write(gzip.compress(b"[]"))
    elif damage == "edited part":
        p = os.path.join(sd, parts[0]["file"])
        with open(p, "wb") as f:
            f.write(gzip.compress(gzip.open(p).read().replace(b"pub-", b"pub_")))
    elif damage == "short middle part":
        p = os.path.join(sd, parts[1]["file"])
        txt = b"[" + b", ".join(json.dumps(r, **KW).encode() for r in json.loads(gzip.open(p).read())[:3]) + b"]"
        os.remove(p)
        with open(os.path.join(sd, "part-0001-%s.json.gz" % db.hashlib.sha256(txt).hexdigest()[:12]), "wb") as f:
            f.write(gzip.compress(txt))
    else:
        with open(os.path.join(sd, "part-x.json.gz"), "wb") as f:
            f.write(gzip.compress(b"[]"))
    before = sorted(os.listdir(sd))
    with pytest.raises(RuntimeError, match="refusing"):
        _load(d)
    assert sorted(os.listdir(sd)) == before


def test_part_files_without_an_index_next_to_the_single_file_are_never_deleted(tmp_path):
    """Part files that do not check out, next to the single file: the single file is read, and the part files stay
    where they are through any number of flushes (their rows were never read)."""
    d = str(tmp_path / "data")
    repo = FileRepo(d)
    _append(repo, _rows(16, seed=20))
    repo.flush()
    parts = _index(d)["parts"]
    os.remove(os.path.join(_sdir(d), "index.json"))
    os.remove(os.path.join(_sdir(d), parts[0]["file"]))                 # a gap: cannot be put back in order
    orphans = _parts_on_disk(d)
    single = _rows(5, seed=21, start=300)
    _write_legacy(d, single)
    for _ in range(2):
        repo = FileRepo(d)
        assert repo.fetch_snapshots() == single
        repo.flush()
    assert set(orphans) <= set(_parts_on_disk(d)) and _load(d) == single


def test_an_unlisted_part_is_deleted_only_when_its_rows_are_in_the_history(tmp_path):
    """A part file the index does not name: the replaced last part a crashed flush left behind (all its rows are in
    the history) goes; a part whose rows the history lacks (e.g. of a newer index a bad merge lost) stays."""
    d = str(tmp_path / "data")
    rows = _rows(10, seed=22)
    repo = FileRepo(d)
    _append(repo, rows)
    repo.flush()
    old_last = _index(d)["parts"][-1]["file"]
    with open(os.path.join(_sdir(d), old_last), "rb") as f:
        old_last_bytes = f.read()
    repo = FileRepo(d)
    repo.fetch_snapshots()
    _append(repo, _rows(2, seed=23, start=400))
    repo.flush()                                                         # the last part replaced, the old one gone
    assert old_last not in _files(d)
    with open(os.path.join(_sdir(d), old_last), "wb") as f:              # as if the flush had stopped before removing it
        f.write(old_last_bytes)
    foreign = "part-0009-%s.json.gz" % ("a" * 12)
    with open(os.path.join(_sdir(d), foreign), "wb") as f:
        f.write(gzip.compress(json.dumps(_rows(2, seed=24, start=700), **KW).encode()))
    repo = FileRepo(d)
    repo.fetch_snapshots()
    _append(repo, _rows(1, seed=25, start=500))
    repo.flush()
    assert old_last not in _files(d) and foreign in _files(d)
    monkey = FileRepo(d)
    assert monkey.fetch_snapshots() == rows + _rows(2, seed=23, start=400) + _rows(1, seed=25, start=500)


def test_switch_back_keeps_a_part_file_whose_rows_were_never_read(tmp_path, monkeypatch):
    d = str(tmp_path / "data")
    rows = _rows(9, seed=26)
    repo = FileRepo(d)
    _append(repo, rows)
    repo.flush()
    foreign = "part-0007-%s.json.gz" % ("b" * 12)
    with open(os.path.join(_sdir(d), foreign), "wb") as f:
        f.write(gzip.compress(json.dumps(_rows(2, seed=27, start=800), **KW).encode()))
    monkeypatch.setenv("SNAPSHOT_PARTS", "false")
    repo = FileRepo(d)
    repo.fetch_snapshots()
    repo.flush()
    assert _files(d) == [foreign] and not os.path.exists(os.path.join(_sdir(d), "index.json"))
    assert _load(d) == rows                                              # (the single file; the stray part kept)


def _skewed_c_encoder(monkeypatch):
    """A C-encoder path whose text is NOT json.dump's (the case REPO_FAST_WRITE=false exists for)."""
    real = db._text_chunks

    def skewed(obj, kw):
        for b in real(obj, kw):
            yield b.replace(b", ", b",  ")
    monkeypatch.setattr(db, "_text_chunks", skewed)


@pytest.mark.parametrize("start", ["single", "parts"])
def test_the_json_dump_rollback_never_depends_on_the_c_encoder(tmp_path, monkeypatch, start):
    """REPO_FAST_WRITE=false: the parts are written, hashed, read back and kept with json.dump's own encoder, and the
    switch back to the single file checks it the same way — a C encoder that writes a different text cannot fail or
    change the build."""
    d = str(tmp_path / "data")
    rows = _rows(16, seed=28)
    if start == "single":
        _write_legacy(d, rows)
    else:
        repo = FileRepo(d)
        _append(repo, rows)
        repo.flush()
    _skewed_c_encoder(monkeypatch)
    monkeypatch.setenv("REPO_FAST_WRITE", "false")
    repo = FileRepo(d)
    repo.fetch_snapshots()
    added = _rows(3, seed=29, start=600)
    _append(repo, added)
    repo.flush()
    assert _parts_text(d) == _old_text(rows + added) and _load(d) == rows + added
    files = _files(d)
    repo = FileRepo(d)
    repo.fetch_snapshots()
    repo.flush()                                                         # unchanged: kept by json.dump's hash
    assert _files(d) == files
    monkeypatch.setenv("SNAPSHOT_PARTS", "false")
    repo = FileRepo(d)
    repo.fetch_snapshots()
    repo.flush()
    with gzip.open(_legacy(d), "rb") as f:
        assert f.read() == _old_text(rows + added)
    assert not os.path.isdir(_sdir(d))
