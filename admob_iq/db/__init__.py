"""DB layer. Three interchangeable repos, same tiny interface the fetcher needs:
    init_schema(), upsert_network(row), upsert_mediation(row), append_snapshot(row)
    + fetch_network(), fetch_mediation(), fetch_snapshots(), has_data()

- `InMemoryRepo` — tests / dry-run (nothing persists).
- `FileRepo`     — history in flat JSON files, NO database. This is what makes a
                   *free, no-code* host possible: a once-a-day job (GitHub Actions
                   or a hosting control-panel cron) reads yesterday's files, appends
                   today, and saves them back. No server, no Postgres.
- `PgRepo`       — Postgres, for anyone who wants a real database.
"""

import os
import json
import gzip
import datetime as _dt


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


def _write_json_gz(path, obj, **dump_kw):
    """Atomically write obj to <path>.gz, and delete any stale plain <path> so the huge
    uncompressed file stops being committed (git picks up the deletion)."""
    gz = path + ".gz"
    tmp = gz + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(obj, f, **dump_kw)
    os.replace(tmp, gz)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


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

    def __init__(self, data_dir: str = "data"):
        self.dir = data_dir
        self._path = {"net": os.path.join(data_dir, "network.json"),
                      "med": os.path.join(data_dir, "mediation.json"),
                      "snap": os.path.join(data_dir, "snapshots.json"),
                      "country": os.path.join(data_dir, "country.json"),
                      "pc": os.path.join(data_dir, "placement_country.json")}
        self._pk = {"net": self.NET_PK, "med": self.MED_PK, "snap": self.SNAP_PK,
                    "country": self.COUNTRY_PK, "pc": self.PC_PK}
        self._rows = {}   # name -> list (lazy-loaded)
        self._pos = {}    # name -> {key: index}
        # ad-unit×country baseline: compact NESTED structures, own files (not the flat model)
        self._ac_path = {"acm": os.path.join(data_dir, "adunit_country_monthly.json"),
                         "acd": os.path.join(data_dir, "adunit_country_daily.json")}
        self._ac = {}     # name -> nested dict (lazy-loaded)

    def init_schema(self):
        os.makedirs(self.dir, exist_ok=True)   # files are written on flush()

    @staticmethod
    def _key(row, pk):
        return "|".join(str(row.get(c, "")) for c in pk)

    def _load(self, name):
        if name not in self._rows:
            data = _read_json_any(self._path[name])
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

    def fetch_placement_country(self):
        return self._load("pc")

    def _load_ac(self, name, default):
        if name not in self._ac:
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

    def flush(self):
        """Persist everything touched this session to disk (atomic, GZIPPED per file)."""
        os.makedirs(self.dir, exist_ok=True)
        for name, rows in self._rows.items():
            _write_json_gz(self._path[name], rows, ensure_ascii=False, default=str)
        for name, nested in self._ac.items():          # compact ad-unit×country structures
            _write_json_gz(self._ac_path[name], nested, ensure_ascii=False, default=str,
                           separators=(",", ":"))

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
