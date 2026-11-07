"""The loaded history, compact (FileRepo): the rows hold one shared object per distinct text value, the monthly rollup
one per distinct number, and a table's key map is kept a bucket at a time (_KeyIndex). Every reader and writer sees
exactly what a plain load and the one big {key: index} map gave: the same dicts, keys, order, values and types, the
same lookups, the same written bytes. Synthetic data only."""

import gzip
import json
import math
import os
import random
import struct

import pytest

from admob_iq import db
from admob_iq.db import FileRepo

PUB = "pub-0000000000000000"


def _put_gz(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, default=str)


def _plain(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _same(a, b):
    """Equal AND the same types all the way down (1 / 1.0 / True apart), floats bit for bit (-0.0 apart from 0.0)."""
    if a.__class__ is not b.__class__:
        return False
    if isinstance(a, dict):
        return list(a) == list(b) and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return struct.pack("<d", a) == struct.pack("<d", b)
    return a == b


def _net(i, day="2026-07-01", **kw):
    r = {"report_date": day, "app_id": "app~%d" % (i % 3), "app_name": "Synth Ä %d" % (i % 3),
         "ad_unit_id": "unit/%d" % (i % 4), "unit_name": "Unit %d" % (i % 4), "ad_source": None, "source_name": None,
         "country": ["US", "IN", "All"][i % 3], "format": "banner", "platform": "ANDROID", "ad_requests": 300 + i,
         "matched_requests": 1, "impressions": 0, "clicks": True if i % 5 == 0 else 1,
         "estimated_earnings_micros": 10 ** 12 + i, "account_id": PUB, "currency_code": "USD",
         "match_rate": [-0.0, 0.0, 1.0, 1, 0.1 + 0.2][i % 5], "is_finalized": i % 2 == 0}
    r.update(kw)
    return r


def _snap(i, sday):
    return {"report_date": "2026-07-%02d" % (1 + i % 7), "snapshot_date": sday, "account_id": PUB,
            "app_id": "app~%d" % (i % 3), "ad_unit_id": "unit/%d" % (i % 4), "country": "US", "format": "banner",
            "estimated_earnings_micros": 1000 + i, "impressions": i, "clicks": 1}


def _history(d, n=40):
    """Every flat table on disk (the snapshot history as parts, as the runner keeps it) + the monthly rollup."""
    r = FileRepo(str(d))
    r.init_schema()
    for i in range(n):
        r.upsert_network(_net(i, day="2026-07-%02d" % (1 + i % 6)))
        r.upsert_mediation(_net(i, day="2026-07-%02d" % (1 + i % 6), ad_source="src-%d" % (i % 2),
                                mediation_group="g|%d" % (i % 2)))
        r.upsert_country({"report_date": "2026-07-%02d" % (1 + i % 6), "account_id": PUB, "app_id": "app~%d" % i,
                          "app_name": "Synth %d" % i, "country": "US", "ad_requests": i, "matched_requests": i,
                          "impressions": i, "clicks": 0, "estimated_earnings_micros": -i})
        r.upsert_placement_country({"account_id": PUB, "app_id": "app~%d" % (i % 3), "ad_unit_id": "unit/%d" % i,
                                    "country": "IN", "impressions": i, "estimated_earnings_micros": 7})
        r.upsert_mediation_unit({"report_date": "2026-07-%02d" % (1 + i % 6), "account_id": PUB,
                                 "app_id": "app~%d" % (i % 3), "ad_unit_id": "unit/%d" % i, "format": "banner",
                                 "platform": "IOS", "ad_requests": i})
        for s in ("2026-07-08", "2026-07-09"):
            r.append_snapshot(_snap(i, s))
    r.merge_adunit_country_monthly([dict(_net(i), month="2026-0%d" % (5 + i % 2), days=30, ctr_min=[-0.0, 0.0][i % 2],
                                         ctr_max=1e-07, ecpm_avg=12.5, show_avg=1.0, match_avg=1)
                                    for i in range(n)])
    r.flush()


# ── the rows: a plain load's values, one object per distinct text value ─────────────────────────────────────────────
def test_the_loaded_tables_are_a_plain_load_with_each_text_value_one_shared_object(tmp_path):
    _history(tmp_path)
    r = FileRepo(str(tmp_path))
    tables = {"net": r.fetch_network(), "med": r.fetch_mediation(), "country": r.fetch_country(),
              "pc": r.fetch_placement_country(), "mu": r.fetch_mediation_unit()}
    for name, rows in tables.items():
        assert rows and _same(rows, _plain(r._path[name] + ".gz")), name
    snaps = r.fetch_snapshots()
    idx = db._snap_read_index(r._snap_dir)
    assert _same(snaps, db._snap_load_parts(r._snap_dir, idx)[0])   # (the parts read without the hook)
    # every distinct text value is ONE object, across rows and across tables …
    seen = {}
    for rows in list(tables.values()) + [snaps]:
        for row in rows:
            for v in row.values():
                if v.__class__ is str:
                    assert seen.setdefault(v, v) is v
    assert tables["net"][0]["account_id"] is snaps[0]["account_id"] is tables["pc"][0]["account_id"]
    # … and no number or flag ever stands in for another: 1 / 1.0 / True and -0.0 / 0.0 keep their own types
    rates = [x["match_rate"] for x in tables["net"]]
    assert {type(v) for v in rates} == {float, int} and any(math.copysign(1, v) < 0 for v in rates if v == 0)
    assert {type(x["clicks"]) for x in tables["net"]} == {bool, int}


def test_the_monthly_rollup_shares_its_numbers_and_keeps_every_value(tmp_path):
    _history(tmp_path)
    r = FileRepo(str(tmp_path))
    acm = r.fetch_adunit_country_monthly()
    assert _same(acm, _plain(r._ac_path["acm"] + ".gz"))
    cells = [arr for by_c in acm["data"].values() for by_m in by_c.values() for arr in by_m.values()]
    at = {f: i for i, f in enumerate(db.ACM_FIELDS)}
    assert cells[0][at["ecpm_avg"]] is cells[1][at["ecpm_avg"]]           # 12.5: one object
    zeros = [arr[at["ctr_min"]] for arr in cells]
    assert {math.copysign(1, z) for z in zeros} == {1.0, -1.0}             # -0.0 never becomes 0.0
    assert all(type(arr[at["show_avg"]]) is float and type(arr[at["match_avg"]]) is int for arr in cells)


def test_a_number_text_read_twice_is_the_value_a_plain_load_reads():
    text = json.dumps([[0.1, 0.1, -0.0, 0.0, 1e-07, 1e300, 10 ** 30, -5, 7, 7.0, True, None, "7"]] * 3)
    plain, shared = json.loads(text), json.loads(text, **db._same_numbers())
    assert _same(shared, plain) and json.dumps(shared) == json.dumps(plain)
    assert shared[0][0] is shared[0][1] is shared[2][0] and shared[0][2] is not shared[0][3]


# ── the key map: what the one {key: index} map gave ─────────────────────────────────────────────────────────────────
def _odd_rows():
    """Keys that only the joined text tells apart: '|' inside values, None, numbers, a missing column, duplicates."""
    rnd = random.Random(7)
    rows = []
    for i in range(400):
        r = {"report_date": rnd.choice(["2026-07-01", "2026-07-02", "2026-07|02", "", None, 20260703]),
             "snapshot_date": rnd.choice(["2026-07-09", "2026-07-10|x", None, "|", "a|b|c"]),
             "account_id": rnd.choice([PUB, "pub|1", None]), "app_id": rnd.choice(["app~1", "app~2|"]),
             "ad_unit_id": "unit/%d" % rnd.randint(0, 9), "country": rnd.choice(["US", "IN|US", ""]),
             "format": rnd.choice(["banner", "|"])}
        if rnd.random() < 0.1:
            del r[rnd.choice(list(r))]
        rows.append(r)
    return rows


@pytest.mark.parametrize("pk,field", [(FileRepo.SNAP_PK, 1), (FileRepo.SNAP_PK, 0), (FileRepo.NET_PK, 0),
                                      (FileRepo.SNAP_PK, 3)])
def test_the_bucketed_key_map_gives_exactly_what_the_one_map_gave(pk, field):
    rows = _odd_rows()
    one = {FileRepo._key(r, pk): i for i, r in enumerate(rows)}            # the map before this change
    assert len(one) < len(rows)                                            # (keys stored twice are in there)
    ix = db._KeyIndex(rows, pk, FileRepo._key, field)
    probes = list(one) + [FileRepo._key(r, pk) + "|" for r in rows[:50]] + ["", "|", "||||||", "2026-07-01"]
    assert bool(ix) and not ix._maps                                       # (truth without making any bucket's map)
    for k in probes + [None, 7, ("2026-07-01",)]:                          # (+ what is not a key text at all)
        assert (k in ix) == (k in one) and ix.get(k) == one.get(k) and ix.get(k, -1) == one.get(k, -1)
        if k in one:
            assert ix[k] == one[k]                                         # a key stored twice: its later row
    for i, r in enumerate(_odd_rows()[:60]):                               # writes: new keys appended as with the dict
        k = FileRepo._key(dict(r, ad_unit_id="new/%d" % i), pk)
        if k not in one:
            one[k] = ix[k] = len(rows)
            rows.append(r)
    assert dict(ix.items()) == one and len(ix) == len(one) and ix == one


def test_an_empty_index_is_falsy_and_takes_new_keys_as_a_dict_does():
    rows, one = [], {}
    ix = db._KeyIndex(rows, FileRepo.NET_PK, FileRepo._key)
    assert not ix and not one and len(ix) == 0 and ix.get("a|b") is None
    one["a|b|c"] = ix["a|b|c"] = 0
    assert ix and ix == one and "a|b|c" in ix and ix.get("a|b|c") == 0


def test_a_written_row_is_the_flat_copy_it_was_with_its_text_shared(tmp_path):
    from datetime import date, datetime
    r = FileRepo(str(tmp_path))
    fresh = lambda: "".join(["app~", "1"])                                # a new str object every call
    src = {"report_date": date(2026, 7, 1), "at": datetime(2026, 7, 1, 5, 6, 7), "app_id": fresh(), "n": 3,
           "x": None, "f": -0.0, "b": True}
    got = r._row(src)
    assert _same(got, db._jsonable(src)) and got is not src and src["report_date"] == date(2026, 7, 1)
    assert fresh() is not fresh() and r._row({"app_id": fresh()})["app_id"] is got["app_id"]
    assert r._row({"d": date(2026, 7, 1)})["d"] is got["report_date"]


def test_a_write_makes_only_its_own_buckets_map(tmp_path):
    _history(tmp_path)
    r = FileRepo(str(tmp_path))
    r.upsert_network(_net(1, day="2026-07-03"))
    r.append_snapshot(_snap(1, "2026-07-10"))
    assert list(r._pos["net"]._maps) == ["2026-07-03"] and list(r._pos["snap"]._maps) == ["2026-07-10"]
    assert sum(len(a) for a in r._pos["net"]._at.values()) == len(r.fetch_network())


# ── the whole store: the same rows and the same files as the code before this change ─────────────────────────────
def _before(monkeypatch):
    """The code before this change: plain loads and the one {key: index} map."""
    monkeypatch.setattr(db, "_shared_rows", lambda memo: lambda pairs: dict(pairs))
    monkeypatch.setattr(db, "_same_numbers", lambda: {})
    monkeypatch.setattr(FileRepo, "_index",
                        lambda self, name: {self._key(r, self._pk[name]): i for i, r in enumerate(self._rows[name])})


def _files(d):
    out = {}
    for base, _dirs, names in os.walk(str(d)):
        for n in names:
            p = os.path.join(base, n)
            with open(p, "rb") as f:
                raw = f.read()
            out[os.path.relpath(p, str(d))] = gzip.decompress(raw) if n.endswith(".gz") else raw
    return out


def _writes(r):
    """A run's writes: refreshed days, new days, a snapshot day appended twice (never overwritten), odd key values."""
    for i in range(60):
        r.upsert_network(_net(i, day="2026-07-%02d" % (4 + i % 5)))
        r.upsert_mediation(_net(i, day="2026-07-06", ad_source="src-%d" % (i % 3), mediation_group="g|%d" % (i % 2)))
        r.upsert_country({"report_date": "2026-07-06", "account_id": PUB, "app_id": "app~%d" % (i % 7),
                          "country": "US|IN" if i % 9 == 0 else "US", "ad_requests": i * 3})
        r.upsert_placement_country({"account_id": PUB, "app_id": "app~%d" % (i % 3), "ad_unit_id": "unit/%d" % i,
                                    "country": "IN", "impressions": 2 * i})
        r.upsert_mediation_unit({"report_date": "2026-07-07", "account_id": PUB, "app_id": "app~%d" % (i % 3),
                                 "ad_unit_id": "unit/%d" % (i % 9), "format": "banner", "platform": "IOS",
                                 "ad_requests": -i})
        r.append_snapshot(_snap(i, "2026-07-09"))                         # already stored: kept as it was
        r.append_snapshot(_snap(i, "2026-07-10"))
        r.append_snapshot(_snap(i, "2026-07-10"))
    r.merge_adunit_country_monthly([dict(_net(i), month="2026-07", days=9, ctr_min=0.5) for i in range(30)])


def test_a_run_on_the_compact_store_writes_what_the_code_before_wrote(tmp_path, monkeypatch):
    _history(tmp_path / "new")
    _history(tmp_path / "old")
    new = FileRepo(str(tmp_path / "new"))
    _writes(new)
    new.flush()
    _writes(new)                                                          # a write after the flush: maps built again
    new.flush()
    with monkeypatch.context() as m:
        _before(m)
        old = FileRepo(str(tmp_path / "old"))
        old._load("net")
        assert type(old._pos["net"]) is dict
        _writes(old)
        old.flush()
        _writes(old)
        old.flush()
    assert _files(tmp_path / "new") == _files(tmp_path / "old")
    for name in ("net", "med", "country", "pc", "mu", "snap"):
        assert _same(new._rows[name], old._rows[name]), name
    assert _same(new.fetch_adunit_country_monthly(), old.fetch_adunit_country_monthly())
