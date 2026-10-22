"""History writer speed-up (db._write_json_gz / FileRepo.flush): the C encoder in slices gives json.dump's text
character for character, and a file whose decompressed bytes would not change is left untouched. Synthetic data only."""

import datetime
import gzip
import json
import os
import random

import pytest

from admob_iq import db
from admob_iq.db import FileRepo, _json_pieces, _write_json_gz
from admob_iq.fetch import fetcher

LIST_KW = {"ensure_ascii": False, "default": str}                          # FileRepo's flat history files
NEST_KW = {"ensure_ascii": False, "default": str, "separators": (",", ":")}  # its compact ad-unit × country files

TRICKY = [0.1, 1e-7, 1e16, 1e22, -0.0, 0.0, 5e-324, 1.7976931348623157e308, 2.5, 1 / 3, 123456789.123456789,
          float("nan"), float("inf"), float("-inf"), 2 ** 70, -(2 ** 63), 10 ** 30 + 1, 0, -1, True, False, None,
          "", "plain", "हिंदी ऐप", "emoji 🎯🚀", "é combining", "line\nbreak\ttab", "quote \" back \\ slash",
          "   separators", "ctrl \x00\x01\x1f", "퟿￿", "日本語", "<script>&amp;</script>",
          datetime.date(2026, 2, 28), datetime.datetime(2028, 2, 29, 23, 59, 59)]


def _text(obj, kw):
    return json.dumps(obj, **kw)


def _old_bytes(obj, kw, tmp):
    """What the writer before this change put in the file (json.dump through gzip text mode), decompressed."""
    p = str(tmp / "old.json.gz")
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(obj, f, **kw)
    with gzip.open(p, "rb") as f:
        return f.read()


def _rand_value(rnd, depth):
    k = rnd.random()
    if depth <= 0 or k < 0.55:
        return rnd.choice(TRICKY)
    if k < 0.8:
        return [_rand_value(rnd, depth - 1) for _ in range(rnd.randint(0, 6))]
    keys = [rnd.choice(["a", "b", "ü", "🎯", "", "id", "x y"]) + str(rnd.randint(0, 50)) for _ in range(rnd.randint(0, 6))]
    keys += [rnd.choice([1, 2.5, True, None, -7])] if rnd.random() < 0.3 else []
    return {kk: _rand_value(rnd, depth - 1) for kk in keys}


@pytest.fixture
def small_slices(monkeypatch):
    monkeypatch.setattr(db, "_SLICE_ROWS", 3)
    monkeypatch.setattr(db, "_SLICE_KEYS", 2)


@pytest.mark.parametrize("kw", [LIST_KW, NEST_KW, {"ensure_ascii": True, "default": str}])
def test_pieces_join_to_json_dumps_for_tricky_values(kw, small_slices):
    rows = [{"report_date": "2026-10-%02d" % (i % 28 + 1), "v": v, "n": i, "nested": {"l": [v, [v]], "d": {"k": v}}}
            for i, v in enumerate(TRICKY)]
    nested = {"month": "2026-10", "dates": ["2026-10-01", "2026-10-02"], "flag": True, "none": None,
              "units": {"u%d" % i: [None, "unit %d ü" % i, v, "USD"] for i, v in enumerate(TRICKY)},
              "data": {"u%d" % i: {"US": [[0, i, v]], "IN": {"2026-09": [i, v]}} for i, v in enumerate(TRICKY)},
              7: "int key", 2.5: "float key", None: "none key", False: "bool key", "empty": [], "emptyd": {}}
    for obj in (rows, nested, [], {}, [[]], [{}], TRICKY, list(range(10)), {"a": list(range(10))}):
        assert "".join(_json_pieces(obj, kw)) == _text(obj, kw)


def test_pieces_join_to_json_dumps_random_structures(small_slices):
    rnd = random.Random(20261022)
    for _ in range(400):
        obj = _rand_value(rnd, 4)
        if rnd.random() < 0.5:
            obj = [obj, _rand_value(rnd, 3), _rand_value(rnd, 2)] * rnd.randint(1, 4)
        for kw in (LIST_KW, NEST_KW):
            assert "".join(_json_pieces(obj, kw)) == _text(obj, kw)


def test_pieces_match_on_default_sized_slices():
    rows = [{"i": i, "s": "ü%d" % i, "f": i / 7} for i in range(db._SLICE_ROWS * 2 + 5)]
    big = {"units": {"u%d" % i: [i, "n"] for i in range(db._SLICE_KEYS * 3 + 1)},
           "data": {"u%d" % i: {"US": [[0, i]]} for i in range(db._SLICE_KEYS * 2 + 7)}}
    assert "".join(_json_pieces(rows, LIST_KW)) == _text(rows, LIST_KW)
    assert "".join(_json_pieces(big, NEST_KW)) == _text(big, NEST_KW)


def test_errors_are_the_ones_json_dump_raises(small_slices):
    with pytest.raises(TypeError):                         # an unsupported key, in a slice like in the whole
        "".join(_json_pieces([{"a": 1}] * 4 + [{(1, 2): 3}], LIST_KW))
    with pytest.raises(ValueError):
        "".join(_json_pieces([1.0, float("nan")] * 4, {"allow_nan": False}))
    loop = [1, 2, 3, 4]
    loop.append(loop)
    with pytest.raises(ValueError):                        # a circular reference across slices
        "".join(_json_pieces(loop, LIST_KW))


@pytest.mark.parametrize("fast", [True, False])
@pytest.mark.parametrize("kw", [LIST_KW, NEST_KW])
def test_written_file_is_byte_identical_to_the_old_writer(tmp_path, small_slices, fast, kw):
    rnd = random.Random(7)
    obj = [{"k": i, "v": rnd.choice(TRICKY), "w": _rand_value(rnd, 2)} for i in range(40)]
    if kw is NEST_KW:
        obj = {"units": {"u%d" % i: r for i, r in enumerate(obj)}, "data": {"x": obj}}
    want = _old_bytes(obj, kw, tmp_path)
    path = str(tmp_path / "f.json")
    assert _write_json_gz(path, obj, compare=True, fast=fast, **kw) is True
    with gzip.open(path + ".gz", "rb") as f:
        assert f.read() == want


@pytest.mark.parametrize("kw", [LIST_KW, NEST_KW, {"ensure_ascii": True, "default": str}, {}])
def test_dump_chunks_are_json_dumps_own_text(kw):
    """The rollback path's text (db._dump_chunks) is what json.dump writes, piece for piece joined."""
    import io
    rnd = random.Random(11)
    objs = [TRICKY, [{"v": v, "n": [v, {"k": v}]} for v in TRICKY], [], {}, "x" * (3 << 20)]
    objs += [_rand_value(rnd, 4) for _ in range(200)]
    for obj in objs:
        if not kw and any(isinstance(v, datetime.date) for v in (obj if isinstance(obj, list) else [])):
            continue                                       # (no default=: json.dump raises for a date, so would this)
        f = io.StringIO()
        try:
            json.dump(obj, f, **kw)
        except TypeError:
            with pytest.raises(TypeError):
                b"".join(db._dump_chunks(obj, kw))
            continue
        assert b"".join(db._dump_chunks(obj, kw)) == f.getvalue().encode("utf-8")


def test_the_json_dump_rollback_compares_with_json_dumps_text(tmp_path, monkeypatch):
    """REPO_FAST_WRITE=false with REPO_SKIP_UNCHANGED on: whether a file is unchanged is decided on json.dump's text,
    so a file the C encoder wrote with a different text (the case the rollback exists for) is rewritten as json.dump
    writes it, never kept."""
    real = db._text_chunks

    def skewed(obj, kw):
        for b in real(obj, kw):
            yield b.replace(b", ", b",  ")
    path = str(tmp_path / "f.json")
    rows = [{"i": i, "s": "ü%d" % i} for i in range(9)]
    monkeypatch.setattr(db, "_text_chunks", skewed)
    assert _write_json_gz(path, rows, compare=True, fast=True, **LIST_KW) is True
    with gzip.open(path + ".gz", "rb") as f:
        assert f.read() != _old_bytes(rows, LIST_KW, tmp_path)           # (the skewed text)
    assert _write_json_gz(path, rows, compare=True, fast=False, **LIST_KW) is True
    with gzip.open(path + ".gz", "rb") as f:
        assert f.read() == _old_bytes(rows, LIST_KW, tmp_path)
    assert _write_json_gz(path, rows, compare=True, fast=False, **LIST_KW) is False    # now unchanged


def _stat(p):
    st = os.stat(p)
    with open(p, "rb") as f:
        return st.st_ino, st.st_mtime_ns, f.read()


def test_unchanged_file_is_left_untouched_and_a_change_is_written(tmp_path, small_slices):
    path = str(tmp_path / "net.json")
    rows = [{"report_date": "2026-10-%02d" % (i % 28 + 1), "app": "ऐप %d" % i, "x": i * 1.5} for i in range(50)]
    assert _write_json_gz(path, rows, **LIST_KW) is True
    before = _stat(path + ".gz")
    assert _write_json_gz(path, json.loads(json.dumps(rows)), **LIST_KW) is False      # same text: no write
    assert _stat(path + ".gz") == before                                                 # same inode, mtime, bytes
    for change in ("last value", "first value", "drop last", "add row", "middle"):
        new = json.loads(json.dumps(rows))
        if change == "last value":
            new[-1]["x"] = -1
        elif change == "first value":
            new[0]["x"] = 0.25
        elif change == "drop last":
            new = new[:-1]                                  # the new text is shorter than the file
        elif change == "add row":
            new.append({"report_date": "2026-10-30", "app": "new", "x": None})
        else:
            new[25]["app"] = "बदला"
        assert _write_json_gz(path, new, **LIST_KW) is True, change
        with gzip.open(path + ".gz", "rb") as f:
            assert f.read() == _old_bytes(new, LIST_KW, tmp_path), change
        rows = new


def test_a_damaged_or_odd_existing_file_is_rewritten(tmp_path, small_slices):
    path = str(tmp_path / "f.json")
    rows = [{"i": i} for i in range(20)]
    want = _old_bytes(rows, LIST_KW, tmp_path)
    for junk in (b"not gzip at all", gzip.compress(b'[{"i": 0}, {"i": 1}')[:-6], b"", gzip.compress(want + b" ")):
        with open(path + ".gz", "wb") as f:
            f.write(junk)
        assert _write_json_gz(path, rows, **LIST_KW) is True
        with gzip.open(path + ".gz", "rb") as f:
            assert f.read() == want
    with open(path, "w") as f:                              # a stale plain file goes even when nothing is written
        f.write("[]")
    assert _write_json_gz(path, rows, **LIST_KW) is False and not os.path.exists(path)


def test_the_old_file_vanishing_mid_copy_falls_back_to_a_full_encode(tmp_path, small_slices, monkeypatch):
    path = str(tmp_path / "f.json")
    rows = [{"i": i, "s": "x" * 10} for i in range(30)]
    _write_json_gz(path, rows, **LIST_KW)
    rows[-1]["i"] = -5

    def lost(gz, n):
        raise db._PrefixLost(gz)
        yield b""                                           # (a generator, like the real one)
    monkeypatch.setattr(db, "_old_prefix", lost)
    assert _write_json_gz(path, rows, **LIST_KW) is True
    with gzip.open(path + ".gz", "rb") as f:
        assert f.read() == _old_bytes(rows, LIST_KW, tmp_path)
    assert not os.path.exists(path + ".gz.tmp")


def test_switches_off_write_every_file_with_json_dump(tmp_path, monkeypatch):
    path = str(tmp_path / "f.json")
    rows = [{"i": i} for i in range(5)]
    monkeypatch.setenv("REPO_SKIP_UNCHANGED", "false")
    monkeypatch.setenv("REPO_FAST_WRITE", "false")
    calls = []
    real = json.dump
    monkeypatch.setattr(db.json, "dump", lambda *a, **k: (calls.append(1), real(*a, **k)))
    assert _write_json_gz(path, rows, **LIST_KW) is True
    assert _write_json_gz(path, rows, **LIST_KW) is True                # rewritten although unchanged
    assert len(calls) == 2


def _tree(d):
    """{relative path: decompressed bytes (gz) or bytes} of every file under d."""
    out = {}
    for base, _dirs, names in os.walk(d):
        for n in names:
            p = os.path.join(base, n)
            with open(p, "rb") as f:
                b = f.read()
            out[os.path.relpath(p, d)] = gzip.decompress(b) if n.endswith(".gz") else b
    return out


def _filled_repo(d):
    repo = FileRepo(d)
    repo.init_schema()
    for day in (datetime.date(2026, 10, 20), datetime.date(2026, 10, 21)):
        fetcher.run_once([{"account_id": "pub-a"}, {"account_id": "pub-b"}], repo, today=day, mode="mock",
                         rolling_days=40, adunit_country_days=45)
    return repo


@pytest.mark.parametrize("snap_parts", ["true", "false"])
def test_filerepo_flush_same_files_both_ways_and_second_flush_writes_nothing(tmp_path, monkeypatch, snap_parts):
    monkeypatch.setenv("SNAPSHOT_PARTS", snap_parts)
    old, new = str(tmp_path / "old"), str(tmp_path / "new")
    monkeypatch.setenv("REPO_FAST_WRITE", "false")
    monkeypatch.setenv("REPO_SKIP_UNCHANGED", "false")
    _filled_repo(old).flush()
    monkeypatch.delenv("REPO_FAST_WRITE")
    monkeypatch.delenv("REPO_SKIP_UNCHANGED")
    repo = _filled_repo(new)
    repo.flush()
    assert _tree(old) == _tree(new)                                     # the same decompressed bytes, every file
    stats = {p: _stat(os.path.join(new, p)) for p in _tree(new)}
    repo.flush()                                                        # nothing changed since: nothing written
    again = FileRepo(new)
    for f in (again.fetch_network, again.fetch_mediation, again.fetch_country, again.fetch_snapshots,
              again.fetch_placement_country, again.fetch_mediation_unit, again.fetch_adunit_country_monthly,
              again.fetch_adunit_country_daily):
        f()
    again.flush()                                                       # a fresh load + flush: nothing written
    assert {p: _stat(os.path.join(new, p)) for p in _tree(new)} == stats


def test_every_speed_switch_is_a_repo_variable_of_the_build_step():
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    step = [s for s in wf["jobs"]["refresh"]["steps"] if s.get("name", "").startswith("Build dashboard")][0]
    for name in ("REPO_FAST_WRITE", "REPO_SKIP_UNCHANGED", "SNAPSHOT_PARTS"):
        assert step["env"][name] == "${{ vars.%s }}" % name             # empty → the code's default
    for v, want in (("", True), ("false", False), ("0", False), ("off", False), ("true", True), ("typo", True)):
        os.environ["REPO_X_TEST"] = v
        try:
            assert db._switch("REPO_X_TEST") is want
        finally:
            del os.environ["REPO_X_TEST"]
