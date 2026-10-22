"""DB layer. Three interchangeable repos, same tiny interface the fetcher needs:
    init_schema(), upsert_network(row), upsert_mediation(row), append_snapshot(row)
    + fetch_network(), fetch_mediation(), fetch_snapshots(), has_data()
    + upsert_mediation_unit(row) / fetch_mediation_unit(): ad-unit totals per day from the mediation
      report WITHOUT AD_SOURCE — the source of truth for an ad unit's requests / matched requests

- `InMemoryRepo` — tests / dry-run (nothing persists).
- `FileRepo`     — history in flat JSON files, NO database. This is what makes a
                   *free, no-code* host possible: a once-a-day job (GitHub Actions
                   or a hosting control-panel cron) reads yesterday's files, appends
                   today, and saves them back. No server, no Postgres.
- `PgRepo`       — Postgres, for anyone who wants a real database.
"""

import os
import sys
import json
import gzip
import zlib
import hashlib
import itertools
import re
import datetime as _dt

from .. import stage_clock as _sc


def _switch(name, default=True):
    """A speed switch from the environment (a repo variable in refresh.yml): false/0/no/off → False, true/1/yes/on →
    True, anything else (unset, empty, a typo) → `default`. Read at call time, so a rollback needs no code push."""
    v = (os.getenv(name) or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return default


def _jsonable(row: dict) -> dict:
    """Flat-copy a row, turning date/datetime into ISO strings so it is JSON-safe.
    The dataservice already stringifies dates on read, so this is loss-free."""
    out = {}
    for k, v in row.items():
        out[k] = v.isoformat() if isinstance(v, (_dt.date, _dt.datetime)) else v
    return out


# --- Ad-unit × country baseline: COMPACT nested storage --------------------------------
# The ad_unit × country cross is high-cardinality (~24k combos × 13 months ≈ 300k monthly
# cells; and the current month alone is ~370k daily rows). As flat dict rows that is ~200MB
# per file — over GitHub's 100MB limit and committed hourly. So we store it nested with a
# shared id table and fixed-order numeric arrays (~40MB total, deltas small between commits).
# The value arrays are positional — DO NOT reorder these field lists.
ACM_FIELDS = ["days", "ad_requests", "matched_requests", "impressions", "clicks",
              "estimated_earnings_micros", "ctr_min", "ctr_max", "match_min", "match_max",
              "show_min", "show_max", "ecpm_min", "ecpm_max", "ctr_avg", "match_avg",
              "show_avg", "ecpm_avg"]
ACD_FIELDS = ["ad_requests", "matched_requests", "impressions", "clicks",
              "estimated_earnings_micros"]


def _unit_meta(r):
    return [r.get("app_id"), r.get("unit_name"), r.get("app_name"), r.get("currency_code", "USD")]


def nest_monthly(existing, rows):
    """Merge flat monthly-rollup rows into a compact {units, data} structure (in place)."""
    nested = existing or {"units": {}, "data": {}}
    units, data = nested["units"], nested["data"]
    for r in rows:
        uid, c, mo = r["ad_unit_id"], r.get("country") or "All", r["month"]
        units[uid] = _unit_meta(r)
        data.setdefault(uid, {}).setdefault(c, {})[mo] = [r.get(f, 0) for f in ACM_FIELDS]
    return nested


def nest_daily(rows):
    """Build a compact {month, dates, units, data} structure from flat daily rows.
    `data[uid][country]` is a list of [date_index, *ACD_FIELDS]. Whole-month replace."""
    dates = sorted({str(r["report_date"])[:10] for r in rows if r.get("report_date")})
    dix = {d: i for i, d in enumerate(dates)}
    units, data = {}, {}
    for r in rows:
        d = str(r.get("report_date"))[:10]
        if d not in dix:
            continue
        uid, c = r["ad_unit_id"], r.get("country") or "All"
        units[uid] = _unit_meta(r)
        data.setdefault(uid, {}).setdefault(c, []).append([dix[d]] + [r.get(f, 0) for f in ACD_FIELDS])
    month = dates[0][:7] if dates else ""
    return {"month": month, "dates": dates, "units": units, "data": data}


def iter_monthly(nested):
    """Expand the compact monthly structure back into flat dict rows (for readers/tests)."""
    units = nested.get("units", {})
    for uid, by_country in nested.get("data", {}).items():
        meta = units.get(uid) or [None, None, None, "USD"]
        for c, by_month in by_country.items():
            for mo, arr in by_month.items():
                d = dict(zip(ACM_FIELDS, arr))
                d.update(ad_unit_id=uid, app_id=meta[0], unit_name=meta[1],
                         app_name=meta[2], currency_code=meta[3], country=c, month=mo)
                yield d


def daily_series(nested, uid, country):
    """Return this (unit, country)'s current-month daily rows as flat dicts, date-ordered."""
    dates = nested.get("dates", [])
    out = []
    for arr in nested.get("data", {}).get(uid, {}).get(country, []):
        di = arr[0]
        d = dict(zip(ACD_FIELDS, arr[1:]))
        d["report_date"] = dates[di] if 0 <= di < len(dates) else None
        out.append(d)
    out.sort(key=lambda r: r["report_date"] or "")
    return out


class InMemoryRepo:
    def __init__(self):
        self.network, self.mediation, self.snapshots, self.country = [], [], [], []
        self.placement_country = []
        self.mediation_unit = []               # ad-unit totals per day (mediation, no AD_SOURCE)
        self.acm = {"units": {}, "data": {}}   # ad-unit×country monthly rollup (compact nested)
        self.acd = {"month": "", "dates": [], "units": {}, "data": {}}   # current-month daily

    def init_schema(self):
        pass

    def upsert_network(self, row):
        self.network.append(row)

    def upsert_mediation(self, row):
        self.mediation.append(row)

    def upsert_country(self, row):
        self.country.append(row)

    def upsert_mediation_unit(self, row):
        self.mediation_unit.append(row)

    def fetch_mediation_unit(self):
        return self.mediation_unit

    def upsert_placement_country(self, row):
        self.placement_country.append(row)

    def fetch_placement_country(self):
        return self.placement_country

    def merge_adunit_country_monthly(self, rows):
        self.acm = nest_monthly(self.acm, rows)

    def fetch_adunit_country_monthly(self):
        return self.acm

    def replace_adunit_country_daily(self, rows):
        self.acd = nest_daily(rows)

    def fetch_adunit_country_daily(self):
        return self.acd

    def append_snapshot(self, row):
        self.snapshots.append(row)

    def fetch_network(self):
        return self.network

    def fetch_mediation(self):
        return self.mediation

    def fetch_country(self):
        return self.country

    def fetch_snapshots(self):
        return self.snapshots

    def has_data(self):
        return bool(self.network)

    def flush(self):
        pass          # in-memory: nothing to persist


_NET_COLS = ["report_date", "account_id", "app_id", "ad_unit_id", "country", "format",
             "platform", "ad_requests", "matched_requests", "impressions", "clicks",
             "estimated_earnings_micros", "impression_rpm_micros", "match_rate",
             "show_rate", "impression_ctr", "currency_code", "is_finalized"]

_SNAP_COLS = ["report_date", "snapshot_date", "account_id", "app_id", "ad_unit_id",
              "country", "format", "estimated_earnings_micros", "impressions", "clicks"]


class PgRepo:
    """Thin psycopg wrapper. psycopg is imported lazily so importing this module
    never requires a DB to be present (keeps tests hermetic)."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._conn = None

    def _c(self):
        if self._conn is None:
            import psycopg
            self._conn = psycopg.connect(self.dsn)
        return self._conn

    def init_schema(self):
        schema = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema) as f:
            ddl = f.read()
        conn = self._c()
        conn.execute(ddl)
        conn.commit()

    def _upsert(self, table, cols, pk, row):
        vals = [row.get(c) for c in cols]
        placeholders = ", ".join(["%s"] * len(cols))
        updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in pk)
        sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders}) "
               f"ON CONFLICT ({', '.join(pk)}) DO UPDATE SET {updates}, pulled_at=now()")
        conn = self._c()
        conn.execute(sql, vals)
        conn.commit()

    def upsert_network(self, row):
        row.setdefault("is_finalized", False)
        self._upsert("network_daily", _NET_COLS,
                     ["report_date", "account_id", "app_id", "ad_unit_id",
                      "country", "format", "platform"], row)

    def upsert_mediation(self, row):
        cols = ["report_date", "account_id", "app_id", "ad_unit_id", "ad_source",
                "mediation_group", "country", "format", "platform", "ad_requests",
                "matched_requests", "impressions", "clicks", "estimated_earnings_micros",
                "observed_ecpm_micros", "match_rate", "impression_ctr",
                "currency_code", "is_finalized"]
        row.setdefault("is_finalized", False)
        row.setdefault("currency_code", "USD")
        row.setdefault("mediation_group", "")
        self._upsert("mediation_daily", cols,
                     ["report_date", "account_id", "app_id", "ad_unit_id", "ad_source",
                      "mediation_group", "country", "format", "platform"], row)

    def upsert_country(self, row):
        cols = ["report_date", "account_id", "app_id", "country", "ad_requests",
                "matched_requests", "impressions", "clicks", "estimated_earnings_micros",
                "currency_code"]
        row.setdefault("currency_code", "USD")
        self._upsert("country_daily", cols,
                     ["report_date", "account_id", "app_id", "country"], row)

    def fetch_country(self):
        return self._rows("SELECT * FROM country_daily")

    _MU_COLS = ["report_date", "account_id", "app_id", "ad_unit_id", "format", "platform",
                "ad_requests", "matched_requests", "impressions", "clicks",
                "estimated_earnings_micros", "currency_code"]

    def upsert_mediation_unit(self, row):
        row.setdefault("currency_code", "USD")
        self._upsert("mediation_unit_daily", self._MU_COLS,
                     ["report_date", "account_id", "app_id", "ad_unit_id", "format", "platform"], row)

    def fetch_mediation_unit(self):
        return self._rows("SELECT * FROM mediation_unit_daily")

    def upsert_placement_country(self, row):
        cols = ["account_id", "app_id", "ad_unit_id", "country", "ad_requests",
                "matched_requests", "impressions", "clicks", "estimated_earnings_micros",
                "currency_code"]
        row.setdefault("currency_code", "USD")
        self._upsert("placement_country", cols,
                     ["account_id", "app_id", "ad_unit_id", "country"], row)

    def fetch_placement_country(self):
        return self._rows("SELECT * FROM placement_country")

    def append_snapshot(self, row):
        vals = [row.get(c) for c in _SNAP_COLS]
        placeholders = ", ".join(["%s"] * len(_SNAP_COLS))
        sql = (f"INSERT INTO earnings_snapshots ({', '.join(_SNAP_COLS)}) "
               f"VALUES ({placeholders}) ON CONFLICT "
               "(report_date, snapshot_date, account_id, app_id, ad_unit_id, country, format) "
               "DO NOTHING")
        conn = self._c()
        conn.execute(sql, vals)
        conn.commit()

    def _rows(self, sql):
        with self._c().cursor() as cur:
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def fetch_network(self):
        return self._rows("SELECT * FROM network_daily")

    def fetch_mediation(self):
        return self._rows("SELECT * FROM mediation_daily")

    def fetch_snapshots(self):
        return self._rows("SELECT * FROM earnings_snapshots")

    def has_data(self):
        with self._c().cursor() as cur:
            cur.execute("SELECT 1 FROM network_daily LIMIT 1")
            return cur.fetchone() is not None

    def flush(self):
        pass          # Postgres commits per write


def _read_json_any(path):
    """Read <path>.gz (gzipped) if present, else the legacy plain <path> (one-time migration),
    else None. Data files are stored GZIPPED because uncompressed history outgrew GitHub's 100 MB
    per-file push limit (JSON compresses ~15x)."""
    gz = path + ".gz"
    if os.path.exists(gz):
        with gzip.open(gz, "rt", encoding="utf-8") as f:
            return json.load(f)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return None


# ── Fast history writer (⏱ speed only: the decompressed bytes are exactly what json.dump wrote) ─────────────────────
# json.dump runs Python's pure-Python encoder (it streams, so the C encoder is never used); json.dumps runs the C
# encoder and returns the SAME text (same separators, same float / int / string rules, same `default` calls). A whole
# file through json.dumps would hold its full text in memory (GBs for the snapshot history), so the text is built in
# slices: a long list in runs of _SLICE_ROWS items, a big dict in runs of _SLICE_KEYS entries, joined with the item
# separator — the concatenation is json.dumps(obj) character for character. Switches (repo variables, refresh.yml):
#   REPO_FAST_WRITE=false      write with json.dump, as before
#   REPO_SKIP_UNCHANGED=false  rewrite every history file on every flush, as before
_SLICE_ROWS = 20_000          # list items per json.dumps call (a history row is well under 1 KB of text)
_SLICE_KEYS = 1_000           # dict entries per call at the deepest sliced level (an ad unit's whole country block)
_SLICE_KW = frozenset(("ensure_ascii", "default", "separators", "allow_nan", "check_circular"))
_READ_BLOCK = 1 << 24         # 16 MB: the block size for reading back an existing file


def _key_text(k, kw):
    """The exact text json.dumps writes for one dict key plus the key separator ('"k": ' / '"k":')."""
    return json.dumps({k: 0}, **kw)[1:-2]


def _json_pieces(obj, kw, depth=2):
    """Yield str pieces whose concatenation is exactly json.dumps(obj, **kw) — the text json.dump(obj, f, **kw)
    writes — in bounded memory. Only plain lists / dicts (exact types) are sliced, `depth` levels down; anything else,
    and any keyword that changes the layout (indent, sort_keys, cls, …), goes through one json.dumps call."""
    if depth <= 0 or set(kw) - _SLICE_KW or type(obj) not in (list, dict) or not obj:
        yield json.dumps(obj, **kw)
        return
    item_sep = (kw.get("separators") or (", ", ": "))[0]
    if type(obj) is list:
        if len(obj) <= _SLICE_ROWS:
            yield json.dumps(obj, **kw)
            return
        yield "["
        for i in range(0, len(obj), _SLICE_ROWS):
            s = json.dumps(obj[i:i + _SLICE_ROWS], **kw)[1:-1]
            yield s if i == 0 else item_sep + s
        yield "]"
        return
    if depth == 1:                                  # deepest level: runs of _SLICE_KEYS entries
        if len(obj) <= _SLICE_KEYS:
            yield json.dumps(obj, **kw)
            return
        it, first = iter(obj.items()), True
        yield "{"
        while True:
            batch = dict(itertools.islice(it, _SLICE_KEYS))
            if not batch:
                break
            s = json.dumps(batch, **kw)[1:-1]
            yield s if first else item_sep + s
            first = False
        yield "}"
        return
    # an outer dict (e.g. {"units": {...}, "data": {...}}): each list / dict value is sliced one level down, the
    # other values go in runs, all in the dict's own order
    yield "{"
    first, run = True, {}
    for k, v in obj.items():
        if type(v) in (list, dict):
            if run:
                s = json.dumps(run, **kw)[1:-1]
                yield s if first else item_sep + s
                first, run = False, {}
            yield _key_text(k, kw) if first else item_sep + _key_text(k, kw)
            first = False
            yield from _json_pieces(v, kw, depth - 1)
        else:
            run[k] = v
    if run:
        s = json.dumps(run, **kw)[1:-1]
        yield s if first else item_sep + s
    yield "}"


def _text_chunks(obj, kw):
    """The UTF-8 bytes of json.dumps(obj, **kw), piece by piece (see _json_pieces)."""
    for s in _json_pieces(obj, kw):
        if s:
            yield s.encode("utf-8")


def _dump_chunks(obj, kw):
    """json.dump's own text, as UTF-8 bytes in ~1 MB pieces: json.dump(obj, f, **kw) writes exactly the pieces of
    JSONEncoder(**kw).iterencode(obj) — the pure-Python encoder, never the C one. The REPO_FAST_WRITE=false rollback
    compares and hashes with this, so it never depends on the C encoder it exists to step around."""
    kw = dict(kw)
    cls = kw.pop("cls", None) or json.JSONEncoder
    buf, size = [], 0
    for s in cls(**kw).iterencode(obj):
        buf.append(s)
        size += len(s)
        if size >= 1 << 20:
            yield "".join(buf).encode("utf-8")
            buf, size = [], 0
    if buf:
        yield "".join(buf).encode("utf-8")


class _PrefixLost(Exception):
    """The existing file could not be read back while its unchanged start was being copied."""


def _old_prefix(gz, n):
    """The first `n` decompressed bytes of the existing file `gz`, in blocks (raises _PrefixLost if it cannot)."""
    try:
        with gzip.open(gz, "rb") as old:
            while n > 0:
                b = old.read(min(n, _READ_BLOCK))
                if not b:
                    raise _PrefixLost(gz)
                n -= len(b)
                yield b
    except (OSError, EOFError, zlib.error) as e:
        raise _PrefixLost(gz) from e


def _gz_write(tmp, chunks):
    """Gzip `chunks` (bytes) into `tmp` — level 9 and the same header gzip.open(tmp, "wt") writes — and return
    (sha256 hex of the decompressed bytes, their length). A failure removes the half-written `tmp`."""
    h, n = hashlib.sha256(), 0
    try:
        with gzip.open(tmp, "wb") as g:
            for b in chunks:
                if b:
                    h.update(b)
                    n += len(b)
                    g.write(b)
    except BaseException:
        _rm(tmp)
        raise
    return h.hexdigest(), n


def _rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _same_as_file(gz, chunks):
    """Stream-compare the new text (`chunks`) with the existing file's decompressed bytes, stopping at the first
    difference. Returns (same, matched, pending): `matched` bytes of the new text are known to equal the file's start
    and `pending` is the first new piece not (fully) matched (b"" when the new text ended first). The file is read
    once, block by block alongside the new text (bounded memory). An unreadable file → (False, 0, None)."""
    matched = 0
    try:
        with gzip.open(gz, "rb") as old:
            for b in chunks:
                if old.read(len(b)) != b:
                    return False, matched, b
                matched += len(b)
            if not old.read(1):
                return True, matched, None
            return False, matched, b""
    except (OSError, EOFError, zlib.error):
        return False, 0, None


def _store_json_gz(gz, obj, dump_kw, *, compare=True, fast=True, changed=False):
    """Write obj's JSON (json.dump's exact text) to the gzip file `gz`, atomically. Returns True when `gz` was
    (re)written, False when it was left byte for byte as it was because its decompressed bytes already equal the new
    text (compare=True, and `changed` — the caller KNOWS the text differs, e.g. the row count moved — is False).

    fast=False writes with json.dump exactly as before. fast=True: the C encoder in slices; when the file differs only
    after some point, the matched start is re-read from the old file (gunzip is far cheaper than encoding) instead of
    being encoded again. Level 9 either way, so the files are the same size as before."""
    tmp = gz + ".tmp"
    have = compare and not changed and os.path.exists(gz)
    if not fast:
        if have and _same_as_file(gz, _dump_chunks(obj, dump_kw))[0]:       # (json.dump's text: no C encoder)
            return False
        try:
            with gzip.open(tmp, "wt", encoding="utf-8") as f:
                json.dump(obj, f, **dump_kw)
        except BaseException:
            _rm(tmp)
            raise
        os.replace(tmp, gz)
        return True
    chunks = _text_chunks(obj, dump_kw)
    matched, pending = 0, None
    if have:
        same, matched, pending = _same_as_file(gz, chunks)
        if same:
            return False
        if pending is None:                          # the old file was unreadable: encode everything afresh
            chunks, matched = _text_chunks(obj, dump_kw), 0

    def stream():
        if matched:
            yield from _old_prefix(gz, matched)
        if pending:
            yield pending
        yield from chunks
    try:
        _gz_write(tmp, stream())
    except _PrefixLost:                              # the old file vanished / broke meanwhile: encode it all again
        _gz_write(tmp, _text_chunks(obj, dump_kw))
    os.replace(tmp, gz)
    return True


def _write_json_gz(path, obj, *, compare=None, fast=None, changed=False, **dump_kw):
    """Atomically write obj to <path>.gz, and delete any stale plain <path> so the huge
    uncompressed file stops being committed (git picks up the deletion). Returns True when <path>.gz was
    written, False when it already held exactly this text (left untouched: git sees no change).
    compare / fast default to the REPO_SKIP_UNCHANGED / REPO_FAST_WRITE switches (both on)."""
    compare = _switch("REPO_SKIP_UNCHANGED") if compare is None else compare
    fast = _switch("REPO_FAST_WRITE") if fast is None else fast
    wrote = _store_json_gz(path + ".gz", obj, dump_kw, compare=compare, fast=fast, changed=changed)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    return wrote


def _gz_sha(path):
    """sha256 hex of a gzip file's decompressed bytes, read block by block."""
    h = hashlib.sha256()
    with gzip.open(path, "rb") as g:
        while True:
            b = g.read(_READ_BLOCK)
            if not b:
                return h.hexdigest()
            h.update(b)


def _encoded(obj, kw, fast):
    """obj's JSON text (json.dump's text either way) as UTF-8 pieces: the C encoder in slices (fast), else json.dump's
    own pure-Python encoder (the REPO_FAST_WRITE=false rollback never touches the C encoder)."""
    return _text_chunks(obj, kw) if fast else _dump_chunks(obj, kw)


def _text_sha(obj, kw, fast=True):
    """sha256 hex of obj's JSON text (see _encoded; bounded memory)."""
    h = hashlib.sha256()
    for b in _encoded(obj, kw, fast):
        h.update(b)
    return h.hexdigest()


# ── Snapshot history in parts (GitHub refuses a pushed file over 100 MB) ────────────────────────────────────────────
# The append-only earnings snapshots grow every day, so the single data/snapshots.json.gz would cross GitHub's
# 100 MB per-file limit (pushes then fail and the dashboard stops updating). It is now stored as
#
#   data/snapshots/index.json                   {"v": 1, "rows": N, "part_rows": R, "parts": [{"file", "rows",
#                                                 "sha256", "bytes", "from", "to"}, …]}  — the parts IN ORDER
#   data/snapshots/part-0000-<sha12>.json.gz    rows[0:R]      (each one a JSON list written exactly like the old
#   data/snapshots/part-0001-<sha12>.json.gz    rows[R:2R] …    single file: same separators, same row text)
#
# Parts are POSITIONAL slices of the one in-memory list (part i = rows[i*R:(i+1)*R]), so reading the parts in index
# order and concatenating them gives back exactly the same rows in exactly the same order — whatever order the rows
# are in. The history is append-only, so every part but the last never changes again: it is verified (its rows
# encoded and hashed, no file read) and left untouched, and only the last part is rewritten.
# "sha256" = the hash of the part's decompressed bytes, checked on every load; "from"/"to" = its snapshot_date span
# (for a reader that wants only some days); "bytes" = its decompressed size. Joining the parts' texts, each without
# its outer [ ], with ", " and wrapping the result in [ ] gives the old single file's text byte for byte.
#
# Crash-safe: changed parts get NEW file names (the hash is in the name), index.json is replaced atomically as the
# last step, and only then are the single file and the replaced parts removed — at every moment the index on disk
# names complete files. A part file is removed only when its rows cannot be lost (the history was read from it, or
# every row's key is in the history); index.json lost → rebuilt from the part names, never an empty history. The
# first run migrates the single file (removed only after every part was written, read back and found equal);
# SNAPSHOT_PARTS=false (repo variable) goes back to the single file the same way. That switch is THE rollback for this
# layout — never a git revert of the code: a build without the parts reader sees no snapshots.json.gz.
SNAP_DIR = "snapshots"
SNAP_INDEX = "index.json"
SNAP_PART_ROWS = 1_000_000            # rows per part: far under GitHub's 50 MB warning once gzipped
_SNAP_KW = {"ensure_ascii": False, "default": str}     # the history files' json.dump keywords (FileRepo.flush)


def _snap_index_path(snap_dir):
    return os.path.join(snap_dir, SNAP_INDEX)


def _snap_read_index(snap_dir):
    """The parts index, or None when there is none (single-file layout)."""
    p = _snap_index_path(snap_dir)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        idx = json.load(f)
    if not isinstance(idx, dict) or not isinstance(idx.get("parts"), list):
        raise ValueError("snapshot index is not a parts index: %s" % p)
    return idx


_PART_NAME = re.compile(r"part-(\d{4,})-([0-9a-f]{12})\.json\.gz")


def _snap_part_files(snap_dir):
    """The part files on disk (not the half-written .part-*.tmp ones), by name."""
    if not os.path.isdir(snap_dir):
        return []
    return sorted(f for f in os.listdir(snap_dir) if f.startswith("part-"))


def _snap_rebuild_index(names):
    """index.json is missing but part files are on disk (a copy or merge that lost it): the index rebuilt from the
    part names — only when they form ONE unbroken list (part-0000 … part-k, one file per number). Raises ValueError
    otherwise: the history is never guessed at. _snap_load_parts(rebuilt=True) then checks each part against the hash
    in its name and the positional row counts."""
    by_no = {}
    for f in names:
        m = _PART_NAME.fullmatch(f)
        if m is None:
            raise ValueError("a part file name that is not part-NNNN-<hash>.json.gz")
        by_no.setdefault(int(m.group(1)), []).append(f)
    if sorted(by_no) != list(range(len(by_no))):
        raise ValueError("the part numbers are not 0..%d without a gap" % (len(by_no) - 1))
    if any(len(v) > 1 for v in by_no.values()):
        raise ValueError("%d part number(s) with more than one file" % sum(len(v) > 1 for v in by_no.values()))
    return {"v": 1, "parts": [{"file": by_no[i][0]} for i in range(len(by_no))]}


def _snap_part_text(snap_dir, entry):
    """A part's decompressed bytes (raises with a clear message when a listed part is missing)."""
    p = os.path.join(snap_dir, entry["file"])
    if not os.path.exists(p):
        raise FileNotFoundError("snapshot part listed in %s is missing: %s — refusing to go on with a partial "
                                "snapshot history" % (_snap_index_path(snap_dir), entry["file"]))
    with open(p, "rb") as f:
        return gzip.decompress(f.read())


def _snap_load_parts(snap_dir, idx, rebuilt=False):
    """(rows, entries): every part in index order, concatenated — the history exactly as it was written. Each entry
    carries what is REALLY on disk (rows, sha256 of the decompressed bytes); a part that differs from its index entry
    is still loaded as it is (it is then simply rewritten at the next flush). rebuilt (an index rebuilt from the part
    names): every part must match the hash in its name and every part but the last hold SNAP_PART_ROWS rows (the
    positional layout the writer makes), else ValueError."""
    rows, entries, odd = [], [], 0
    parts = idx["parts"]
    for i, e in enumerate(parts):
        raw = _snap_part_text(snap_dir, e)
        sha, size = hashlib.sha256(raw).hexdigest(), len(raw)
        part = json.loads(raw.decode("utf-8"))
        del raw
        if not isinstance(part, list):
            raise ValueError("snapshot part is not a JSON list: %s" % e["file"])
        if rebuilt:
            if _PART_NAME.fullmatch(e["file"]).group(2) != sha[:12]:
                raise ValueError("snapshot part %d does not match the hash in its name" % i)
            if i < len(parts) - 1 and len(part) != SNAP_PART_ROWS:
                raise ValueError("snapshot part %d is not a full part" % i)
        else:
            odd += sha != e.get("sha256") or len(part) != e.get("rows")
        lo_d, hi_d = _snap_span(part)
        entries.append(dict(e, sha256=sha, rows=len(part), bytes=size, **{"from": lo_d, "to": hi_d}))
        rows.extend(part)
    if odd:
        print(f"snapshot parts: {odd} part(s) differ from the index (kept as on disk, rewritten at the next flush)",
              file=sys.stderr)
    return rows, entries


def _snap_parts_text(snap_dir, idx):
    """The parts' rows as ONE JSON list text (bytes, piece by piece): what the single file would hold."""
    yield b"["
    first = True
    for e in idx["parts"]:
        inner = memoryview(_snap_part_text(snap_dir, e))[1:-1]
        if len(inner):
            if not first:
                yield b", "
            yield inner
            first = False
    yield b"]"


def _legacy_text(legacy):
    """The single file's decompressed bytes, block by block (<legacy>.gz, else the plain <legacy>)."""
    gz = legacy + ".gz"
    f = gzip.open(gz, "rb") if os.path.exists(gz) else open(legacy, "rb")
    with f:
        while True:
            b = f.read(_READ_BLOCK)
            if not b:
                return
            yield b


class _Bytes:
    """read(n) over a generator of bytes-like blocks (a block is sliced, never copied whole)."""

    def __init__(self, gen):
        self.gen, self.buf, self.pos = gen, b"", 0

    def read(self, n):
        out = []
        while n > 0:
            if self.pos >= len(self.buf):
                b = next(self.gen, None)
                if b is None:
                    break
                self.buf, self.pos = b, 0
                continue
            take = self.buf[self.pos:self.pos + n]
            self.pos += len(take)
            n -= len(take)
            out.append(take)
        return b"".join(out)


def _snap_relation(snap_dir, idx, legacy):
    """How the parts and the single file relate when BOTH are on disk (bounded memory, compared as text):
      "same"   — the same rows;
      "legacy" — the parts' rows are the first rows of the single file (it was written later: a switch back to the
                 single file that stopped before removing the parts);
      "parts"  — the single file's rows are the first rows of the parts (a migration that stopped before removing
                 the single file);
      "other"  — neither (e.g. a build without parts support started a new single file next to them)."""
    a, b = _Bytes(_legacy_text(legacy)), _Bytes(_snap_parts_text(snap_dir, idx))
    off = 0
    while True:
        x, y = a.read(1 << 20), b.read(1 << 20)
        if x == y:
            if not x:
                return "same"
            off += len(x)
            continue
        n = min(len(x), len(y))
        i = next((k for k in range(n) if x[k] != y[k]), n)
        at = off + i
        xa, yb = x[i:] + a.read(3), y[i:] + b.read(3)
        if yb == b"]" and (xa[:2] == b", " or at == 1):
            return "legacy"
        if xa == b"]" and (yb[:2] == b", " or at == 1):
            return "parts"
        return "other"


def _snap_rows_known(path, has_key):
    """True when every row of the part file `path` is a row whose key the history being written already holds."""
    try:
        with open(path, "rb") as f:
            part = json.loads(gzip.decompress(f.read()).decode("utf-8"))
        return isinstance(part, list) and all(isinstance(r, dict) and has_key(r) for r in part)
    except Exception:
        return False


def _snap_drop_stale(snap_dir, keep, known, has_key=None):
    """Remove the part files the new layout does not use — but only those whose rows cannot be lost: half-written
    .part-*.tmp files, files in `known` (the history was read from them, or from the single file that holds their
    rows), and files whose every row's key the history holds (`has_key`; e.g. a part a crashed flush left behind).
    Any other part file (say, the parts of an index a bad copy lost) stays where it is, with a counts-only warning.
    Returns how many stayed."""
    left = 0
    if not os.path.isdir(snap_dir):
        return 0
    for f in sorted(os.listdir(snap_dir)):
        if f in keep:
            continue
        p = os.path.join(snap_dir, f)
        if f.startswith(".part-") or f == SNAP_INDEX + ".tmp":
            _rm(p)
        elif f.startswith("part-"):
            if f in known or (has_key is not None and _snap_rows_known(p, has_key)):
                _rm(p)
            else:
                left += 1
    if left:
        print(f"snapshot parts: {left} part file(s) not read into the history left in place (not deleted)",
              file=sys.stderr)
    return left


def _snap_remove_parts(snap_dir, known=(), has_key=None):
    """Drop the parts layout: index first (from then on the single file is what every reader loads), then the parts
    the history was read from (see _snap_drop_stale: a part file whose rows were never read is not deleted)."""
    _rm(_snap_index_path(snap_dir))
    if os.path.isdir(snap_dir):
        _snap_drop_stale(snap_dir, set(), set(known), has_key)
        try:
            os.rmdir(snap_dir)
        except OSError:
            pass


def _snap_span(rows):
    """(min, max) snapshot_date of a part, or (None, None) when they are not all strings."""
    try:
        ds = [r["snapshot_date"] for r in rows]
        if ds and all(type(d) is str for d in ds):
            return min(ds), max(ds)
    except Exception:
        pass
    return None, None


def _snap_write_parts(snap_dir, legacy, rows, prev, *, fast=True, compare=True, known=(), has_key=None):
    """Store `rows` as parts (see SNAP_DIR) and return (written, kept, entries). `prev` = the entries of the parts the rows were
    loaded from (None: nothing to reuse). A part whose slice still encodes to the same text is kept untouched; a
    changed or new part is written under a new name, read back and checked; then the index is replaced; then the
    single file and the part files the index no longer names are removed — only those whose rows cannot be lost
    (`known`: the files the history was read from; see _snap_drop_stale). fast=False: json.dump's own encoder
    for the text, its hash and the unchanged-part check (no C encoder anywhere)."""
    os.makedirs(snap_dir, exist_ok=True)
    n = SNAP_PART_ROWS
    entries, fresh = [], []
    for i, lo in enumerate(range(0, len(rows), n)):
        part = rows[lo:lo + n]
        old = prev[i] if (compare and prev and i < len(prev)) else None
        if (old is not None and old.get("rows") == len(part)
                and os.path.exists(os.path.join(snap_dir, old["file"]))
                and _text_sha(part, _SNAP_KW, fast) == old.get("sha256")):
            entries.append(old)                     # same text as the file on disk (verified at load): untouched
            continue
        tmp = os.path.join(snap_dir, ".part-%04d.tmp" % i)
        sha, size = _gz_write(tmp, _encoded(part, _SNAP_KW, fast))      # the hash of exactly the bytes written
        name = "part-%04d-%s.json.gz" % (i, sha[:12])
        os.replace(tmp, os.path.join(snap_dir, name))
        lo_d, hi_d = _snap_span(part)
        ent = {"file": name, "rows": len(part), "sha256": sha, "bytes": size, "from": lo_d, "to": hi_d}
        entries.append(ent)
        fresh.append(ent)
    for ent in fresh:                               # read back every new part before anything points at it
        if _gz_sha(os.path.join(snap_dir, ent["file"])) != ent["sha256"]:
            raise RuntimeError("snapshot part read back different from what was written: %s" % ent["file"])
    idx = {"v": 1, "rows": len(rows), "part_rows": n, "parts": entries}
    text = json.dumps(idx, indent=1, sort_keys=True) + "\n"
    ip = _snap_index_path(snap_dir)
    try:
        with open(ip, encoding="utf-8") as f:
            same = f.read() == text
    except OSError:
        same = False
    if not same:
        with open(ip + ".tmp", "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(ip + ".tmp", ip)                 # ← the switch: from here on readers load these parts
    for p in (legacy + ".gz", legacy):              # every row is now in parts that were read back equal
        _rm(p)
    _snap_drop_stale(snap_dir, {e["file"] for e in entries} | {SNAP_INDEX},
                     set(known) | {e["file"] for e in (prev or ())}, has_key)
    return len(fresh), len(entries) - len(fresh), entries


def write_json_gz_stable(path, obj):
    """Write obj to `path` (the full .gz name) as DETERMINISTIC gzip — sorted keys, compact JSON, no
    timestamp or file name in the gzip header — and only when the content changed. Returns True when
    the file was (re)written. The hourly build then leaves an unchanged file's bytes alone, so the
    private repo's git history doesn't grow by a fresh copy of every file on every run."""
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return write_gz_stable(path, raw)


def write_gz_stable(path, raw):
    """write_json_gz_stable's writer for bytes already serialized the same way (a big file built from its parts):
    deterministic gzip, written only when the content changed. Returns True when the file was (re)written."""
    import io
    try:
        with open(path, "rb") as f:
            if gzip.decompress(f.read()) == raw:      # inflating is far cheaper than compressing again
                return False
    except (OSError, EOFError, ValueError, zlib.error):
        pass                                          # missing or damaged (a bad deflate stream is zlib.error) → write a fresh one
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0) as g:
        g.write(raw)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(buf.getvalue())
    os.replace(tmp, path)
    return True


class FileRepo:
    """History as flat JSON files (GZIPPED on disk) — no database. Same interface as the others.

    Rows are held in memory with a key→index map (O(1) upsert), and written to
    disk once via `flush()` — NOT on every row. That keeps a run fast and cheap
    even with tens of thousands of rows (the earlier write-per-row version was
    O(n²) and choked on real volume). Callers persist by calling `flush()` when
    done (build_static does; tests do). Dates are stored as ISO strings, which the
    dataservice reads via `str(...)`, so reads are drop-in identical to the others.
    """

    NET_PK = ["report_date", "account_id", "app_id", "ad_unit_id", "country",
              "format", "platform"]
    MED_PK = ["report_date", "account_id", "app_id", "ad_unit_id", "ad_source",
              "mediation_group", "country", "format", "platform"]
    SNAP_PK = ["report_date", "snapshot_date", "account_id", "app_id", "ad_unit_id",
               "country", "format"]
    COUNTRY_PK = ["report_date", "account_id", "app_id", "country"]
    PC_PK = ["account_id", "app_id", "ad_unit_id", "country"]
    MU_PK = ["report_date", "account_id", "app_id", "ad_unit_id", "format", "platform"]
    # ⏱ measure only (stage_clock): each history file's FIRST read (gunzip + JSON parse + key map) is its own child
    # stage of whichever stage touches the file first (e.g. admob_network), so local disk / JSON time is never booked
    # as the report call's time. Later reads of the loaded rows are not timed.
    LOAD_STAGES = {"net": "repo_load_network", "med": "repo_load_mediation", "snap": "repo_load_snapshots",
                   "country": "repo_load_country", "pc": "repo_load_placement_country",
                   "mu": "repo_load_mediation_unit", "acm": "repo_load_adunit_country_monthly",
                   "acd": "repo_load_adunit_country_daily"}
    # ⏱ measure only: each history file's write in flush() (a child of repo_flush; an unchanged file costs only the
    # encode + compare, a snapshot part that did not change costs only its encode + hash)
    WRITE_STAGES = {"net": "repo_write_network", "med": "repo_write_mediation", "snap": "repo_write_snapshots",
                    "country": "repo_write_country", "pc": "repo_write_placement_country",
                    "mu": "repo_write_mediation_unit", "acm": "repo_write_adunit_country_monthly",
                    "acd": "repo_write_adunit_country_daily"}

    def __init__(self, data_dir: str = "data"):
        self.dir = data_dir
        self._path = {"net": os.path.join(data_dir, "network.json"),
                      "med": os.path.join(data_dir, "mediation.json"),
                      "snap": os.path.join(data_dir, "snapshots.json"),
                      "country": os.path.join(data_dir, "country.json"),
                      "pc": os.path.join(data_dir, "placement_country.json"),
                      # ad-unit totals per day from the mediation report WITHOUT AD_SOURCE (the ad
                      # unit's own requests / matched requests) — full daily history, never rolled up
                      "mu": os.path.join(data_dir, "mediation_unit.json")}
        self._pk = {"net": self.NET_PK, "med": self.MED_PK, "snap": self.SNAP_PK,
                    "country": self.COUNTRY_PK, "pc": self.PC_PK, "mu": self.MU_PK}
        self._rows = {}   # name -> list (lazy-loaded)
        self._pos = {}    # name -> {key: index}
        # ad-unit×country baseline: compact NESTED structures, own files (not the flat model)
        self._ac_path = {"acm": os.path.join(data_dir, "adunit_country_monthly.json"),
                         "acd": os.path.join(data_dir, "adunit_country_daily.json")}
        self._ac = {}     # name -> nested dict (lazy-loaded)
        # snapshot history in parts (see SNAP_DIR): the entries of the parts the rows were read from (None: not from
        # parts) — a part whose rows still encode to its hash is left untouched by flush()
        self._snap_dir = os.path.join(data_dir, SNAP_DIR)
        self._snap_parts = None
        self._snap_known = set()  # the part files whose rows are in the loaded history (flush may remove them)
        self._disk_rows = {}  # name -> rows in its file as last read / written (a different count = the text changed)

    def init_schema(self):
        os.makedirs(self.dir, exist_ok=True)   # files are written on flush()

    @staticmethod
    def _key(row, pk):
        return "|".join(str(row.get(c, "")) for c in pk)

    def _load(self, name):
        if name not in self._rows:
            with _sc.stage(self.LOAD_STAGES.get(name, "repo_load")):
                if name == "snap":
                    data = self._load_snapshots()
                else:
                    data = _read_json_any(self._path[name])
                    self._disk_rows[name] = len(data) if isinstance(data, list) else None
                self._rows[name] = data if data is not None else []
                self._pos[name] = {self._key(r, self._pk[name]): i
                                   for i, r in enumerate(self._rows[name])}
        return self._rows[name]

    def _upsert(self, name, row):
        row = _jsonable(row)
        rows = self._load(name); pos = self._pos[name]
        k = self._key(row, self._pk[name])
        if k in pos:
            rows[pos[k]] = row          # refresh existing (e.g. today's estimate)
        else:
            pos[k] = len(rows); rows.append(row)

    def upsert_network(self, row):
        row.setdefault("is_finalized", False)
        self._upsert("net", row)

    def upsert_mediation(self, row):
        row.setdefault("is_finalized", False)
        row.setdefault("currency_code", "USD")
        row.setdefault("mediation_group", "")
        self._upsert("med", row)

    def upsert_country(self, row):
        row.setdefault("currency_code", "USD")
        self._upsert("country", row)

    def upsert_placement_country(self, row):
        row.setdefault("currency_code", "USD")
        self._upsert("pc", row)

    def upsert_mediation_unit(self, row):
        row.setdefault("currency_code", "USD")
        self._upsert("mu", row)

    def fetch_mediation_unit(self):
        return self._load("mu")

    def fetch_placement_country(self):
        return self._load("pc")

    def _load_ac(self, name, default):
        if name not in self._ac:
            with _sc.stage(self.LOAD_STAGES.get(name, "repo_load")):
                data = _read_json_any(self._ac_path[name])
                self._ac[name] = data if data is not None else default
        return self._ac[name]

    def merge_adunit_country_monthly(self, rows):
        cur = self._load_ac("acm", {"units": {}, "data": {}})
        self._ac["acm"] = nest_monthly(cur, [_jsonable(r) for r in rows])

    def fetch_adunit_country_monthly(self):
        return self._load_ac("acm", {"units": {}, "data": {}})

    def replace_adunit_country_daily(self, rows):
        """The daily table holds ONLY the current month — replace it wholesale each run
        (completed months live in the monthly rollup, so old daily rows are dropped)."""
        self._ac["acd"] = nest_daily([_jsonable(r) for r in rows])

    def fetch_adunit_country_daily(self):
        return self._load_ac("acd", {"month": "", "dates": [], "units": {}, "data": {}})

    def append_snapshot(self, row):
        row = _jsonable(row)
        rows = self._load("snap"); pos = self._pos["snap"]
        k = self._key(row, self.SNAP_PK)
        if k not in pos:                # append-only; never overwrite a snapshot
            pos[k] = len(rows); rows.append(row)

    def _load_snapshots(self):
        """The snapshot history as ONE list in its stored order, from whichever layout is on disk: the parts (index
        present), else the single file (the first run after the switch to parts migrates it at flush). Both on disk
        means a switch between layouts stopped half way (or a build without parts support wrote a single file next
        to them): the one holding the other's rows as its first rows wins; if neither does, the parts' rows come first
        and then the single file's rows the parts lack. Nothing on disk is ever dropped.
        Part files WITHOUT index.json (a copy or merge that lost it, or a write that stopped before it): the index is
        rebuilt from the part names (_snap_rebuild_index, checked part by part), then the same rules apply. If it
        cannot be, the single file is the history and the part files are left in place (never deleted); with no
        single file either, the load stops rather than start an empty history."""
        legacy = self._path["snap"]
        idx = _snap_read_index(self._snap_dir)
        self._snap_parts = None
        self._snap_known = set()
        self._disk_rows["snap"] = None
        has_legacy = os.path.exists(legacy + ".gz") or os.path.exists(legacy)
        rebuilt = False
        if idx is None:
            orphans = _snap_part_files(self._snap_dir)
            if orphans:
                try:
                    idx, rebuilt = _snap_rebuild_index(orphans), True
                except ValueError as err:
                    self._snap_orphans_unusable(len(orphans), err, has_legacy)
            if idx is None:
                data = _read_json_any(legacy)
                self._disk_rows["snap"] = len(data) if isinstance(data, list) else None
                return data
            print(f"snapshot history: index.json missing — rebuilt from {len(orphans)} part file name(s)",
                  file=sys.stderr)
        rel = _snap_relation(self._snap_dir, idx, legacy) if has_legacy else "parts"
        if rel == "legacy":
            print("snapshot history: the single file holds every part row (a switch back to it did not finish) "
                  "— read from the single file", file=sys.stderr)
            self._snap_known = {e["file"] for e in idx["parts"]}
            return _read_json_any(legacy)
        try:
            rows, parts = _snap_load_parts(self._snap_dir, idx, rebuilt=rebuilt)
        except ValueError as err:
            if not rebuilt:
                raise
            self._snap_orphans_unusable(len(idx["parts"]), err, has_legacy)
            data = _read_json_any(legacy)
            self._disk_rows["snap"] = len(data) if isinstance(data, list) else None
            return data
        self._snap_parts, self._snap_known = parts, {e["file"] for e in idx["parts"]}
        if rel == "other":
            seen = {self._key(r, self.SNAP_PK) for r in rows}
            extra = [r for r in (_read_json_any(legacy) or []) if self._key(r, self.SNAP_PK) not in seen]
            print(f"snapshot history: a separate single file next to the parts — {len(extra)} row(s) of it the "
                  f"parts lack added after the parts' rows", file=sys.stderr)
            rows.extend(extra)
        return rows

    @staticmethod
    def _snap_orphans_unusable(n, err, has_legacy):
        """Part files without an index that cannot be read back as one history: stop (no single file to fall back on),
        else say so — the single file is read and the part files stay where they are (never deleted)."""
        if not has_legacy:
            raise RuntimeError("snapshot index.json is missing and the %d part file(s) on disk cannot be read back as "
                               "one history (%s) — refusing to go on with a partial snapshot history" % (n, err))
        print(f"snapshot history: {n} part file(s) without an index do not form one history ({err}) — read from the "
              f"single file, the part files left in place", file=sys.stderr)

    def _snap_has_key(self, row):
        return self._key(row, self.SNAP_PK) in self._pos.get("snap", ())

    def _flush_snapshots(self, rows, compare, fast):
        """Write the snapshot history: as parts (SNAPSHOT_PARTS, default on), else as the single file. Either way
        the other layout is removed only after the new one was written and read back equal. Returns True when a
        file was written."""
        legacy = self._path["snap"]
        if _switch("SNAPSHOT_PARTS"):
            wrote, _kept, self._snap_parts = _snap_write_parts(self._snap_dir, legacy, rows, self._snap_parts,
                                                               fast=fast, compare=compare, known=self._snap_known,
                                                               has_key=self._snap_has_key)
            self._snap_known = {e["file"] for e in self._snap_parts}
            self._disk_rows["snap"] = None
            return wrote > 0
        disk = self._disk_rows.get("snap")
        wrote = _write_json_gz(legacy, rows, compare=compare, fast=fast,
                               changed=disk is not None and disk != len(rows), **_SNAP_KW)
        self._disk_rows["snap"] = len(rows)
        if os.path.exists(_snap_index_path(self._snap_dir)) or os.path.isdir(self._snap_dir):
            if _gz_sha(legacy + ".gz") != _text_sha(rows, _SNAP_KW, fast):   # the single file must hold every row
                raise RuntimeError("snapshot single file read back different from the rows; the parts are kept")
            _snap_remove_parts(self._snap_dir, self._snap_known, self._snap_has_key)
        self._snap_parts = None
        self._snap_known = set()
        return wrote

    def flush(self):
        """Persist everything touched this session to disk (atomic, GZIPPED per file). A file whose decompressed
        bytes would not change is left untouched (REPO_SKIP_UNCHANGED); the text is json.dump's either way."""
        os.makedirs(self.dir, exist_ok=True)
        compare, fast = _switch("REPO_SKIP_UNCHANGED"), _switch("REPO_FAST_WRITE")
        wrote = kept = 0
        for name, rows in self._rows.items():
            with _sc.stage(self.WRITE_STAGES[name]):
                if name == "snap":
                    w = self._flush_snapshots(rows, compare, fast)
                else:
                    disk = self._disk_rows.get(name)
                    w = _write_json_gz(self._path[name], rows, compare=compare, fast=fast,
                                       changed=disk is not None and disk != len(rows),
                                       ensure_ascii=False, default=str)
                    self._disk_rows[name] = len(rows)
            wrote, kept = wrote + bool(w), kept + (not w)
        for name, nested in self._ac.items():          # compact ad-unit×country structures
            with _sc.stage(self.WRITE_STAGES[name]):
                w = _write_json_gz(self._ac_path[name], nested, compare=compare, fast=fast,
                                   ensure_ascii=False, default=str, separators=(",", ":"))
            wrote, kept = wrote + bool(w), kept + (not w)
        print(f"repo flush: {wrote} file(s) written, {kept} unchanged", file=sys.stderr)

    def fetch_network(self):
        return self._load("net")

    def fetch_mediation(self):
        return self._load("med")

    def fetch_country(self):
        return self._load("country")

    def fetch_snapshots(self):
        return self._load("snap")

    def has_data(self):
        return bool(self._load("net"))
