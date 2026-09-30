// D1 schema: idempotent creation, versioning, constraints, partial unique indexes, schema.sql == db.js. node --test
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { FakeD1 } from "./fake_d1.js";
import {
  SCHEMA, SCHEMA_VERSION, MIGRATIONS, CONFIG_LOG_DDL, ensureSchema, splitSql, addDays, _resetSchemaForTests,
} from "../src/db.js";

const TABLES = ["rv_actions", "rv_flags", "rv_meta", "rv_notes", "rv_snoozes", "rv_state"];
const hasConfigLog = (db) => db.q("SELECT COUNT(*) AS n FROM sqlite_master WHERE type = 'table' AND name = 'config_log'")[0].n === 1;
const INDEXES = ["rv_actions_day", "rv_flags_day", "rv_flags_one_open", "rv_flags_status", "rv_notes_day", "rv_snoozes_one_live"];

const objects = (db, type) => db.q("SELECT name FROM sqlite_master WHERE type = ? AND name LIKE 'rv_%' ORDER BY name", type).map((r) => r.name);
const throwsConstraint = (fn) => assert.throws(fn, /constraint/i);

test("schema.sql equals the DDL in db.js (SCHEMA)", () => {
  const file = readFileSync(fileURLToPath(new URL("../schema.sql", import.meta.url)), "utf8");
  assert.equal(file.trim(), SCHEMA.trim());
});

test("splitSql: 14 statements; a ';' inside a trailing comment does not split", () => {
  const parts = splitSql(SCHEMA);
  assert.equal(parts.length, 14);
  assert.ok(parts.some((p) => p.includes("append-only; never UPDATE/DELETE")));
  for (const p of parts) assert.match(p, /^(CREATE|INSERT)/);
});

test("ensureSchema creates every table + index, schema_version = 3, and is idempotent", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  assert.equal(await ensureSchema(db), 3);
  assert.equal(SCHEMA_VERSION, 3);
  assert.deepEqual(objects(db, "table"), TABLES);
  assert.ok(hasConfigLog(db));
  assert.deepEqual(objects(db, "index"), INDEXES);
  const batches = db.batches;
  await ensureSchema(db);
  assert.equal(db.batches, batches, "second call in the same isolate does nothing");
  _resetSchemaForTests();                          // a new isolate on the same database
  db.sqlite.exec("INSERT INTO rv_state (day, app, st, who, at) VALUES ('2026-10-01','a1a1a1a1a1a1','ok','x@example.test','t')");
  assert.equal(await ensureSchema(db), 3);
  assert.deepEqual(objects(db, "table"), TABLES);
  assert.deepEqual(db.q("SELECT k, v FROM rv_meta"), [{ k: "schema_version", v: "3" }]);
  assert.equal(db.q("SELECT COUNT(*) AS n FROM rv_state")[0].n, 1, "existing data kept");
});

test("ensureSchema: a failure is not cached (next call retries); separate databases each get the schema", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  db.failNext = new Error("temporary");
  await assert.rejects(ensureSchema(db), /temporary/);
  assert.equal(await ensureSchema(db), 3);
  const other = new FakeD1();
  assert.equal(await ensureSchema(other), 3);
  assert.deepEqual(objects(other, "table"), TABLES);
});

test("MIGRATIONS run in order in one batch each and bump schema_version", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  MIGRATIONS[4] = ["ALTER TABLE rv_notes ADD COLUMN edited_at TEXT"];
  MIGRATIONS[5] = ["CREATE INDEX IF NOT EXISTS rv_notes_who ON rv_notes(who)"];
  try {
    assert.equal(await ensureSchema(db), 5);
    assert.deepEqual(db.q("SELECT v FROM rv_meta WHERE k = 'schema_version'"), [{ v: "5" }]);
    assert.ok(db.q("PRAGMA table_info(rv_notes)").some((c) => c.name === "edited_at"));
    _resetSchemaForTests();
    assert.equal(await ensureSchema(db), 5, "already migrated → nothing re-run");
  } finally {
    delete MIGRATIONS[4];
    delete MIGRATIONS[5];
    _resetSchemaForTests();
  }
});

// The first released DDL (schema_version 1): rv_flags without dec_day / done_day.
const V1_FLAGS = `CREATE TABLE IF NOT EXISTS rv_flags (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, app TEXT NOT NULL, app_label TEXT NOT NULL DEFAULT '',
  feature TEXT, note TEXT NOT NULL DEFAULT '', raised_by TEXT NOT NULL, raised_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','kaam','closed','withdrawn')),
  decision TEXT CHECK (decision IN ('theek','kaam','band')), dec_note TEXT, dec_by TEXT, dec_at TEXT,
  done_note TEXT, done_by TEXT, done_at TEXT, wd_by TEXT, wd_at TEXT)`;

test("a schema_version 1 database is migrated to 3 (rv_flags gets dec_day / done_day, config_log; data kept); a new one starts at 3", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  db.sqlite.exec("CREATE TABLE rv_meta (k TEXT PRIMARY KEY, v TEXT NOT NULL); INSERT INTO rv_meta VALUES ('schema_version', '1');");
  db.sqlite.exec(V1_FLAGS);
  db.sqlite.exec("INSERT INTO rv_flags (day, app, raised_by, raised_at) VALUES ('2026-10-01', 'a1a1a1a1a1a1', 'x@example.test', 't')");
  assert.equal(await ensureSchema(db), 3);
  const cols = db.q("PRAGMA table_info(rv_flags)").map((c) => c.name);
  assert.ok(cols.includes("dec_day") && cols.includes("done_day"));
  assert.ok(hasConfigLog(db));
  assert.deepEqual(db.q("SELECT v FROM rv_meta WHERE k = 'schema_version'"), [{ v: "3" }]);
  assert.equal(db.q("SELECT COUNT(*) AS n FROM rv_flags")[0].n, 1, "existing flag kept");
  _resetSchemaForTests();
  assert.equal(await ensureSchema(db), 3, "migrated once; a new isolate does not re-run it");
  _resetSchemaForTests();
  const fresh = new FakeD1();
  assert.equal(await ensureSchema(fresh), 3);
  assert.ok(fresh.q("PRAGMA table_info(rv_flags)").some((c) => c.name === "dec_day"));
  assert.ok(hasConfigLog(fresh));
  _resetSchemaForTests();
});

test("a schema_version 2 database (the live Review DB) is migrated to 3: config_log added, review data untouched", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  const v2 = splitSql(SCHEMA).filter((s) => !s.includes("config_log") && !s.startsWith("INSERT"));
  for (const s of v2) db.sqlite.exec(s);
  db.sqlite.exec("INSERT INTO rv_meta VALUES ('schema_version', '2')");
  db.sqlite.exec("INSERT INTO rv_state (day, app, st, who, at) VALUES ('2026-10-01','a1a1a1a1a1a1','ok','x@example.test','t')");
  assert.equal(hasConfigLog(db), false);
  const batches = db.batches;
  assert.equal(await ensureSchema(db), 3);
  assert.equal(db.batches, batches + 2, "the schema batch + one migration batch");
  assert.ok(hasConfigLog(db));
  assert.deepEqual(db.q("SELECT v FROM rv_meta WHERE k = 'schema_version'"), [{ v: "3" }]);
  assert.equal(db.q("SELECT COUNT(*) AS n FROM rv_state")[0].n, 1, "existing review state kept");
  const cols = db.q("PRAGMA table_info(config_log)").map((c) => c.name);
  assert.deepEqual(cols, ["id", "who", "at", "file", "bytes", "result", "commit_sha"]);
  _resetSchemaForTests();
});

test("MIGRATIONS[3] creates the same config_log table as SCHEMA", () => {
  const norm = (s) => s.replace(/--[^\n]*/g, "").replace(/\s+/g, " ").trim();
  const inSchema = splitSql(SCHEMA).find((s) => s.includes("config_log"));
  assert.deepEqual(MIGRATIONS[3], [CONFIG_LOG_DDL]);
  assert.equal(norm(inSchema), norm(CONFIG_LOG_DDL));
});

test("rv_flags_one_open: one OPEN flag per app + feature (NULL = poori app is its own slot); closed ones do not count", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  await ensureSchema(db);
  const ins = (app, feature, status = "open") => db.sqlite.prepare(
    "INSERT INTO rv_flags (day, app, feature, raised_by, raised_at, status) VALUES ('2026-10-01', ?, ?, 'x@example.test', 't', ?)")
    .run(app, feature, status);
  ins("a1a1a1a1a1a1", null);
  throwsConstraint(() => ins("a1a1a1a1a1a1", null));
  ins("a1a1a1a1a1a1", "kamai");
  throwsConstraint(() => ins("a1a1a1a1a1a1", "kamai"));
  ins("b2b2b2b2b2b2", "kamai");                    // other app
  ins("a1a1a1a1a1a1", "kamai", "closed");          // history rows are unlimited
  ins("a1a1a1a1a1a1", "kamai", "kaam");
  ins("a1a1a1a1a1a1", "kamai", "withdrawn");
  db.sqlite.exec("UPDATE rv_flags SET status = 'closed' WHERE app = 'a1a1a1a1a1a1' AND feature = 'kamai' AND status = 'open'");
  ins("a1a1a1a1a1a1", "kamai");                    // re-flag after a decision
  throwsConstraint(() => ins("a1a1a1a1a1a1", "kamai", "maybe"));
  throwsConstraint(() => db.sqlite.exec("UPDATE rv_flags SET decision = 'later' WHERE id = 1"));
});

test("rv_snoozes_one_live: one uncleared snooze per app + feature; days must be 7 or 14", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  await ensureSchema(db);
  const ins = (feature, days = 7, cleared = null) => db.sqlite.prepare(
    "INSERT INTO rv_snoozes (app, feature, day, until, days, who, at, cleared_at) VALUES ('a1a1a1a1a1a1', ?, '2026-10-01', '2026-10-08', ?, 'x@example.test', 't', ?)")
    .run(feature, days, cleared);
  ins("ads");
  throwsConstraint(() => ins("ads"));
  ins("ads", 14, "2026-10-02T00:00:00.000Z");      // cleared rows do not count
  ins("kamai", 14);
  throwsConstraint(() => ins("setup", 10));
});

test("rv_state: st must be ok / kal / flag; (day, app) is the primary key", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  await ensureSchema(db);
  const ins = (st) => db.sqlite.prepare("INSERT INTO rv_state (day, app, st, who, at) VALUES ('2026-10-01', 'a1a1a1a1a1a1', ?, 'x', 't')").run(st);
  throwsConstraint(() => ins("done"));
  ins("ok");
  throwsConstraint(() => ins("kal"));
  assert.equal(db.q("SELECT snz FROM rv_state")[0].snz, "[]");
});

test("the fake D1 behaves like D1 where the Worker relies on it", async () => {
  const db = new FakeD1();
  await db.exec("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT UNIQUE)");
  assert.throws(() => db.prepare("SELECT 1").bind(undefined), /D1_TYPE_ERROR/);
  assert.throws(() => db.prepare("SELECT 1").bind({}), /D1_TYPE_ERROR/);
  const r = await db.prepare("INSERT INTO t (v) VALUES (?)").bind("a").run();
  assert.equal(r.success, true);
  assert.deepEqual([r.meta.changes, r.meta.last_row_id], [1, 1]);
  assert.equal(await db.prepare("SELECT v FROM t WHERE id = ?").bind(1).first("v"), "a");
  assert.equal(await db.prepare("SELECT v FROM t WHERE id = ?").bind(9).first(), null);
  await assert.rejects(db.prepare("SELECT v FROM t").first("nope"), /D1_COLUMN_NOTFOUND/);
  assert.deepEqual((await db.prepare("SELECT id, v FROM t").all()).results, [{ id: 1, v: "a" }]);
  assert.deepEqual(await db.prepare("SELECT id, v FROM t").raw({ columnNames: true }), [["id", "v"], [1, "a"]]);
  await assert.rejects(db.batch([
    db.prepare("INSERT INTO t (v) VALUES ('b')"),
    db.prepare("INSERT INTO t (v) VALUES ('a')"),       // UNIQUE violation → whole batch rolled back
  ]), /UNIQUE constraint failed/);
  assert.equal(db.q("SELECT COUNT(*) AS n FROM t")[0].n, 1);
  const res = await db.batch([db.prepare("INSERT INTO t (v) VALUES ('c')"), db.prepare("SELECT COUNT(*) AS n FROM t")]);
  assert.equal(res[0].meta.changes, 1);
  assert.deepEqual(res[1].results, [{ n: 2 }]);
  assert.equal((await db.prepare("SELECT ? AS b").bind(true).first("b")), 1);
});

test("addDays: calendar arithmetic across month / year ends", () => {
  assert.equal(addDays("2026-10-02", 7), "2026-10-09");
  assert.equal(addDays("2026-12-28", 14), "2027-01-11");
  assert.equal(addDays("2028-02-22", 7), "2028-02-29");
});
