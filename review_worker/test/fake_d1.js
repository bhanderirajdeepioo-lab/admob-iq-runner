// A Cloudflare D1 binding shim over node:sqlite (in-memory), for tests only.
// Same surface the Worker uses: prepare().bind().first()/all()/run()/raw(), batch() (one transaction,
// rolled back on error), exec(). Like D1, binding `undefined` (or an object) throws.

import { DatabaseSync } from "node:sqlite";

function checkBind(v, i) {
  if (v === undefined) throw new TypeError(`D1_TYPE_ERROR: Type 'undefined' not supported for value 'undefined' (param ${i + 1})`);
  if (v !== null && typeof v === "object" && !(v instanceof Uint8Array) && !(v instanceof ArrayBuffer)) {
    throw new TypeError(`D1_TYPE_ERROR: Type 'object' not supported (param ${i + 1})`);
  }
  if (typeof v === "boolean") return v ? 1 : 0;
  if (v instanceof ArrayBuffer) return new Uint8Array(v);
  return v;
}

const plain = (row) => (row ? { ...row } : row);

function d1Error(e) {
  const err = new Error(`D1_ERROR: ${e && e.message ? e.message : String(e)}`);
  err.cause = e;
  return err;
}

class FakeStatement {
  constructor(d1, sql, params) {
    this._d1 = d1;
    this._sql = sql;
    this._params = params;
  }

  bind(...values) {
    return new FakeStatement(this._d1, this._sql, values.map(checkBind));
  }

  _prepared() {
    this._d1.statements.push(this._sql);
    try {
      return this._d1.sqlite.prepare(this._sql);
    } catch (e) {
      throw d1Error(e);
    }
  }

  /** Runs now (sync); used by batch() and the async methods. Returns a D1Result. */
  _exec() {
    const st = this._prepared();
    try {
      if (st.columns().length > 0) {
        const results = st.all(...this._params).map(plain);
        return { results, success: true, meta: { changes: 0, last_row_id: 0, rows_read: results.length } };
      }
      const r = st.run(...this._params);
      return {
        results: [], success: true,
        meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid), rows_written: Number(r.changes) },
      };
    } catch (e) {
      throw d1Error(e);
    }
  }

  async first(col) {
    await this._d1._tick();
    const st = this._prepared();
    let row;
    try {
      row = st.get(...this._params);
    } catch (e) {
      throw d1Error(e);
    }
    if (!row) return null;
    if (col === undefined) return plain(row);
    if (!(col in row)) throw new Error(`D1_COLUMN_NOTFOUND: ${col}`);
    return row[col];
  }

  async all() {
    await this._d1._tick();
    return this._exec();
  }

  async run() {
    await this._d1._tick();
    return this._exec();
  }

  async raw(opts = {}) {
    await this._d1._tick();
    const st = this._prepared();
    const rows = st.all(...this._params);
    const cols = st.columns().map((c) => c.name);
    const out = rows.map((r) => cols.map((c) => r[c]));
    return opts.columnNames ? [cols, ...out] : out;
  }
}

export class FakeD1 {
  constructor() {
    this.sqlite = new DatabaseSync(":memory:");
    this.statements = [];     // every SQL text prepared (for assertions)
    this.batches = 0;
    this.failNext = null;     // set to an Error to make the next batch()/first() fail (tests)
  }

  prepare(sql) {
    if (typeof sql !== "string") throw new TypeError("D1_TYPE_ERROR: sql must be a string");
    return new FakeStatement(this, sql, []);
  }

  async _tick() {
    await Promise.resolve();   // yield like a network call so concurrent requests interleave
    if (this.failNext) {
      const e = this.failNext;
      this.failNext = null;
      throw e;
    }
  }

  async batch(stmts) {
    if (!Array.isArray(stmts)) throw new TypeError("D1_TYPE_ERROR: batch() needs an array");
    await this._tick();
    this.batches += 1;
    const db = this.sqlite;
    db.exec("BEGIN");
    try {
      const out = stmts.map((s) => s._exec());
      db.exec("COMMIT");
      return out;
    } catch (e) {
      try {
        db.exec("ROLLBACK");
      } catch {
        /* already rolled back */
      }
      throw e;
    }
  }

  async exec(sql) {
    await this._tick();
    this.sqlite.exec(sql);
    return { count: sql.split(";").filter((s) => s.trim()).length, duration: 0 };
  }

  /** Test helper: synchronous SELECT → plain rows. */
  q(sql, ...params) {
    return this.sqlite.prepare(sql).all(...params).map(plain);
  }
}
