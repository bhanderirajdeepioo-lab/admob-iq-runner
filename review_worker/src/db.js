// D1 storage for the Daily App Review: schema (created on first request, no manual migration),
// every query, and every state rule of the API. Input is already validated by index.js.
//
// Rules that must hold:
// - rv_actions is APPEND-ONLY (never UPDATE/DELETE). Every successful write appends ≥ 1 row to it
//   in the SAME db.batch (a batch is one transaction in D1).
// - Conflict checks that matter under concurrency are done INSIDE the batch (guarded INSERT … SELECT
//   … WHERE / conditional UPDATE / the partial unique indexes), so two people clicking at once can
//   never break a rule. Plain state changes are last-write-wins; the log keeps both.
// - Only `?` placeholders; null is bound, never undefined.

import { ApiError } from "./auth.js";

export const FEATS = ["kamai", "uninstall", "active", "value", "update", "ads", "deduct", "mediation", "health", "setup"];

export const SCHEMA_VERSION = 5;

// The exact DDL of the spec (§B.5). review_worker/schema.sql must stay equal to this (a test checks).
export const SCHEMA = `CREATE TABLE IF NOT EXISTS rv_meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rv_state (
  day TEXT NOT NULL, app TEXT NOT NULL,
  st  TEXT NOT NULL CHECK (st IN ('ok','kal','flag')),
  snz TEXT NOT NULL DEFAULT '[]',               -- JSON array of feature ids snoozed at the moment of this state
  who TEXT NOT NULL, at TEXT NOT NULL,
  PRIMARY KEY (day, app));
CREATE TABLE IF NOT EXISTS rv_actions (           -- append-only; never UPDATE/DELETE
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, who TEXT NOT NULL,
  act TEXT NOT NULL, day TEXT NOT NULL, app TEXT, feature TEXT, note TEXT, ref INTEGER, extra TEXT);
CREATE INDEX IF NOT EXISTS rv_actions_day ON rv_actions(day, id);
CREATE TABLE IF NOT EXISTS rv_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, app TEXT NOT NULL, app_label TEXT NOT NULL DEFAULT '',
  text TEXT NOT NULL, who TEXT NOT NULL, at TEXT NOT NULL, deleted_by TEXT, deleted_at TEXT);
CREATE INDEX IF NOT EXISTS rv_notes_day ON rv_notes(day, app);
CREATE TABLE IF NOT EXISTS rv_flags (
  id INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, app TEXT NOT NULL, app_label TEXT NOT NULL DEFAULT '',
  feature TEXT,                                 -- NULL = poori app
  note TEXT NOT NULL DEFAULT '', raised_by TEXT NOT NULL, raised_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','kaam','closed','withdrawn')),
  decision TEXT CHECK (decision IN ('theek','kaam','band')), dec_note TEXT, dec_by TEXT, dec_at TEXT,
  done_note TEXT, done_by TEXT, done_at TEXT, wd_by TEXT, wd_at TEXT,
  dec_day TEXT, done_day TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS rv_flags_one_open ON rv_flags(app, ifnull(feature,'*')) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS rv_flags_status ON rv_flags(status, day);
CREATE INDEX IF NOT EXISTS rv_flags_day ON rv_flags(day);
CREATE TABLE IF NOT EXISTS rv_snoozes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, app_label TEXT NOT NULL DEFAULT '', feature TEXT NOT NULL,
  day TEXT NOT NULL, until TEXT NOT NULL, days INTEGER NOT NULL CHECK (days IN (7,14)), note TEXT NOT NULL DEFAULT '',
  who TEXT NOT NULL, at TEXT NOT NULL, cleared_by TEXT, cleared_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS rv_snoozes_one_live ON rv_snoozes(app, feature) WHERE cleared_at IS NULL;
CREATE TABLE IF NOT EXISTS config_log (            -- append-only: every Settings save through /api/config/save
  id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT NOT NULL, at TEXT NOT NULL, file TEXT NOT NULL,
  bytes INTEGER NOT NULL, result TEXT NOT NULL, commit_sha TEXT);
CREATE TABLE IF NOT EXISTS cmp_marks (            -- 📌 saved dates of "compare any date" (app = an AdMob app id or '*')
  id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, date TEXT NOT NULL, name TEXT NOT NULL,
  who TEXT NOT NULL, at TEXT NOT NULL, deleted_by TEXT, deleted_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS cmp_marks_one_live ON cmp_marks(app, date, name) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS cmp_marks_log (        -- append-only: every add / delete of a saved date
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, who TEXT NOT NULL,
  act TEXT NOT NULL CHECK (act IN ('add','delete')), mark INTEGER NOT NULL,
  app TEXT NOT NULL, date TEXT NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cmp_ranges (           -- 📅 saved custom compares: two date ranges, Pehle (b_*) vs Baad (a_*)
  id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, b_from TEXT NOT NULL, b_to TEXT NOT NULL,
  a_from TEXT NOT NULL, a_to TEXT NOT NULL, name TEXT NOT NULL,
  who TEXT NOT NULL, at TEXT NOT NULL, deleted_by TEXT, deleted_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS cmp_ranges_one_live ON cmp_ranges(app, b_from, b_to, a_from, a_to, name) WHERE deleted_at IS NULL;
CREATE TABLE IF NOT EXISTS cmp_ranges_log (       -- append-only: every add / delete of a saved compare
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, who TEXT NOT NULL,
  act TEXT NOT NULL CHECK (act IN ('add','delete')), cmp INTEGER NOT NULL, app TEXT NOT NULL,
  b_from TEXT NOT NULL, b_to TEXT NOT NULL, a_from TEXT NOT NULL, a_to TEXT NOT NULL, name TEXT NOT NULL);
INSERT OR IGNORE INTO rv_meta (k, v) VALUES ('schema_version', '5');`;

// Schema changes: MIGRATIONS[n] = [sql, …] upgrades version n-1 → n (run in order, one batch each). A NEW database
// gets the current SCHEMA (and schema_version = SCHEMA_VERSION) directly; only an older database runs these.
// 2: the review day of a flag decision (dec_day) and of "kaam ho gaya" (done_day) — before 09:00 IST the open day is
//    still yesterday, so the IST date of dec_at / done_at is not the day the decision belongs to.
// 3: config_log, the audit of Settings saves (POST /api/config/save: who, at, file, bytes, result, commit sha).
// 4: cmp_marks (+ its one-live index) and cmp_marks_log — the 📌 saved dates of "compare any date" (/api/marks):
//    who saved / deleted one and when; deleting only marks the row (deleted_by / deleted_at), the log keeps both.
// 5: cmp_ranges (+ its one-live index) and cmp_ranges_log — the saved CUSTOM compares (two date ranges, Pehle vs Baad)
//    of "compare any date", the same rules as cmp_marks. New tables only (IF NOT EXISTS): a v4 database keeps every
//    mark, and an older client that never sends a range keeps working exactly as before.
export const CONFIG_LOG_DDL = `CREATE TABLE IF NOT EXISTS config_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT NOT NULL, at TEXT NOT NULL, file TEXT NOT NULL,
  bytes INTEGER NOT NULL, result TEXT NOT NULL, commit_sha TEXT)`;
export const MARKS_DDL = [`CREATE TABLE IF NOT EXISTS cmp_marks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, date TEXT NOT NULL, name TEXT NOT NULL,
  who TEXT NOT NULL, at TEXT NOT NULL, deleted_by TEXT, deleted_at TEXT)`,
"CREATE UNIQUE INDEX IF NOT EXISTS cmp_marks_one_live ON cmp_marks(app, date, name) WHERE deleted_at IS NULL",
`CREATE TABLE IF NOT EXISTS cmp_marks_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, who TEXT NOT NULL,
  act TEXT NOT NULL CHECK (act IN ('add','delete')), mark INTEGER NOT NULL,
  app TEXT NOT NULL, date TEXT NOT NULL, name TEXT NOT NULL)`];
export const RANGES_DDL = [`CREATE TABLE IF NOT EXISTS cmp_ranges (
  id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, b_from TEXT NOT NULL, b_to TEXT NOT NULL,
  a_from TEXT NOT NULL, a_to TEXT NOT NULL, name TEXT NOT NULL,
  who TEXT NOT NULL, at TEXT NOT NULL, deleted_by TEXT, deleted_at TEXT)`,
"CREATE UNIQUE INDEX IF NOT EXISTS cmp_ranges_one_live ON cmp_ranges(app, b_from, b_to, a_from, a_to, name) WHERE deleted_at IS NULL",
`CREATE TABLE IF NOT EXISTS cmp_ranges_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, who TEXT NOT NULL,
  act TEXT NOT NULL CHECK (act IN ('add','delete')), cmp INTEGER NOT NULL, app TEXT NOT NULL,
  b_from TEXT NOT NULL, b_to TEXT NOT NULL, a_from TEXT NOT NULL, a_to TEXT NOT NULL, name TEXT NOT NULL)`];
export const MIGRATIONS = {
  2: ["ALTER TABLE rv_flags ADD COLUMN dec_day TEXT", "ALTER TABLE rv_flags ADD COLUMN done_day TEXT"],
  3: [CONFIG_LOG_DDL],
  4: MARKS_DDL,
  5: RANGES_DDL,
};

/** One statement per entry (a ';' inside a trailing comment is not a statement end). */
export function splitSql(sql) {
  return sql.split(/;[ \t]*(?:\n|$)/).map((s) => s.trim()).filter(Boolean);
}

const SCHEMA_STATEMENTS = splitSql(SCHEMA);
let schemaReady = new WeakMap();   // per isolate, per D1 binding object; a failure is forgotten (retried)

export function _resetSchemaForTests() {
  schemaReady = new WeakMap();
}

/** Create the tables once per isolate (idempotent), then run any pending MIGRATIONS. */
export function ensureSchema(db) {
  let p = schemaReady.get(db);
  if (!p) {
    p = (async () => {
      await db.batch(SCHEMA_STATEMENTS.map((s) => db.prepare(s)));
      let v = Number(await db.prepare("SELECT v FROM rv_meta WHERE k = 'schema_version'").first("v")) || 0;
      while (Array.isArray(MIGRATIONS[v + 1])) {
        const n = v + 1;
        await db.batch([
          ...MIGRATIONS[n].map((s) => db.prepare(s)),
          db.prepare("UPDATE rv_meta SET v = ? WHERE k = 'schema_version'").bind(String(n)),
        ]);
        v = n;
      }
      return v;
    })();
    p.catch(() => schemaReady.delete(db));
    schemaReady.set(db, p);
  }
  return p;
}

// ── small helpers ────────────────────────────────────────────────────────────────────────────────

/** YYYY-MM-DD + n days (calendar arithmetic, UTC). */
export function addDays(d, n) {
  const t = Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)) + n * 86400000;
  return new Date(t).toISOString().slice(0, 10);
}

function parseArr(s) {
  try {
    const v = JSON.parse(s);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function parseObj(s) {
  if (s == null) return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

const rows = (res) => (res && Array.isArray(res.results) ? res.results : []);
const changes = (res) => Number((res && res.meta && res.meta.changes) || 0);

const FLAG_COLS = "id, day, app, app_label, feature, note, raised_by, raised_at, status, decision, dec_note, " +
  "dec_by, dec_at, done_note, done_by, done_at, wd_by, wd_at, dec_day, done_day";
const SNZ_COLS = "s.id, s.app, s.app_label, s.feature, s.day, s.until, s.days, s.note, s.who, s.at";

// A flag is "live on d": raised on d, or raised before d and still open / kaam on d, or closed on or after d. Carry-over
// of open 🚩 to later days comes from this rule. Days are REVIEW days: a decision belongs to the open day it was made
// on (dec_day / done_day; before 09:00 IST that is still yesterday), the IST date of its timestamp is only the
// fallback for a row without one. A withdrawal only ever happens on the flag's own day (unflag / undo), so a
// withdrawn flag is never carried. On the open day (and later) the admin view also lists what was CLOSED in the last
// 14 days ("Band"), so those stay in the list instead of vanishing the morning after the decision.
export const CLOSED_DAYS = 14;
const FLAG_LIVE = "(day = ? OR (day < ? AND (status IN ('open','kaam') OR (status = 'closed' AND " +
  "COALESCE(done_day, dec_day, date(COALESCE(done_at, dec_at), '+330 minutes')) >= ?))))";
const flagLiveArgs = (d, openDay) => [d, d, openDay && d >= openDay ? addDays(d, -CLOSED_DAYS) : d];

// A snooze is "active on review day d": made on a review day ≤ d (`day`), runs until ≥ d, and not cleared on a
// review day ≤ d. Snoozes are made and cleared only on the open day, so:
// - d ≥ open day (the page's 60 s polling, every write): "cleared" simply means cleared_at IS NOT NULL. Cheap.
// - an older d (History, admin corrections): the review day of a clear is the `day` of the snooze/unsnooze action
//   logged with the same timestamp (exact, also before 09:00 IST while yesterday is still open). The lookup is
//   bounded to the snooze's own ≤ 14-day window, so it runs on the rv_actions(day, id) index instead of scanning
//   the whole (ever-growing) log. The IST date of cleared_at is only a fallback.
const SNZ_OPEN = "s.day <= ? AND s.until >= ? AND s.cleared_at IS NULL";
const SNZ_PAST = "s.day <= ? AND s.until >= ? AND (s.cleared_at IS NULL OR (NOT EXISTS (SELECT 1 FROM rv_actions a " +
  "WHERE a.day >= s.day AND a.day <= ? AND a.at = s.cleared_at AND a.app = s.app AND a.feature = s.feature " +
  "AND a.act IN ('snooze','unsnooze')) AND date(s.cleared_at, '+330 minutes') > ?))";

/** The snooze rule for review day d: {sql, args}. `openDay` null → the exact (older-day) rule. */
export function snzRule(d, openDay) {
  return openDay && d >= openDay ? { sql: SNZ_OPEN, args: [d, d] } : { sql: SNZ_PAST, args: [d, d, d, d] };
}

function flagObj(r) {
  return {
    id: r.id, day: r.day, app: r.app, app_label: r.app_label, feature: r.feature ?? null, note: r.note,
    raised_by: r.raised_by, raised_at: r.raised_at, status: r.status, decision: r.decision ?? null,
    dec_note: r.dec_note ?? null, dec_by: r.dec_by ?? null, dec_at: r.dec_at ?? null,
    done_note: r.done_note ?? null, done_by: r.done_by ?? null, done_at: r.done_at ?? null,
    wd_by: r.wd_by ?? null, wd_at: r.wd_at ?? null, dec_day: r.dec_day ?? null, done_day: r.done_day ?? null,
  };
}

function snzObj(r) {
  return {
    id: r.id, app: r.app, app_label: r.app_label, feature: r.feature, day: r.day, until: r.until,
    days: r.days, note: r.note, who: r.who, at: r.at,
  };
}

const stateObj = (r) => ({ st: r.st, who: r.who, at: r.at, snz: parseArr(r.snz) });
const noteObj = (r) => ({ id: r.id, app: r.app, text: r.text, who: r.who, at: r.at });
const logObj = (r) => ({
  id: r.id, at: r.at, who: r.who, act: r.act, app: r.app ?? null, feature: r.feature ?? null,
  note: r.note ?? null, ref: r.ref ?? null, extra: parseObj(r.extra),
});

const byFeat = (a, b) => FEATS.indexOf(a) - FEATS.indexOf(b);

/**
 * INSERT INTO rv_actions … SELECT … [WHERE guard] — the audit row. `refSql` (a scalar subquery) replaces the
 * literal ref when the id is created in the same batch; `guard` makes the row (and so the write) conditional.
 */
function logStmt(db, a, opt = {}) {
  const refPart = opt.refSql ? opt.refSql : "?";
  const sql = "INSERT INTO rv_actions (at, who, act, day, app, feature, note, ref, extra) " +
    `SELECT ?, ?, ?, ?, ?, ?, ?, ${refPart}, ?` + (opt.guard ? ` WHERE ${opt.guard}` : "");
  const args = [
    a.at, a.who, a.act, a.day, a.app ?? null, a.feature ?? null, a.note ? a.note : null,
    ...(opt.refSql ? opt.refArgs || [] : [a.ref ?? null]),
    a.extra ? JSON.stringify(a.extra) : null,
    ...(opt.guard ? opt.guardArgs || [] : []),
  ];
  return db.prepare(sql).bind(...args);
}

// ── reads ────────────────────────────────────────────────────────────────────────────────────────

const REV_SQL = "SELECT IFNULL(MAX(id), 0) AS rev FROM rv_actions";

export async function getRev(db) {
  return Number(await db.prepare(REV_SQL).first("rev")) || 0;
}

/** Features of `app` with a snooze active on review day d, in FEATS order. */
export async function activeSnoozedFeatures(db, d, app, openDay) {
  const s = snzRule(d, openDay);
  const res = await db.prepare(`SELECT s.feature AS feature FROM rv_snoozes s WHERE s.app = ? AND ${s.sql}`)
    .bind(app, ...s.args).all();
  return [...new Set(rows(res).map((r) => r.feature))].sort(byFeat);
}

/** DAYSTATE for day d (without the index-derived fields). `openDay` = the index's open day. */
export async function getDayState(db, d, openDay) {
  const s = snzRule(d, openDay);
  const res = await db.batch([
    db.prepare(REV_SQL),
    db.prepare("SELECT app, st, snz, who, at FROM rv_state WHERE day = ? ORDER BY app").bind(d),
    db.prepare("SELECT id, app, text, who, at FROM rv_notes WHERE day = ? AND deleted_at IS NULL ORDER BY id").bind(d),
    db.prepare(`SELECT ${FLAG_COLS} FROM rv_flags WHERE ${FLAG_LIVE} ORDER BY id`).bind(...flagLiveArgs(d, openDay)),
    db.prepare(`SELECT ${SNZ_COLS} FROM rv_snoozes s WHERE ${s.sql} ORDER BY s.id`).bind(...s.args),
    db.prepare("SELECT MAX(day) AS d FROM rv_state WHERE day < ?").bind(d),
    db.prepare("SELECT app FROM rv_state WHERE st = 'kal' AND day = (SELECT MAX(day) FROM rv_state WHERE day < ?) " +
      "ORDER BY app").bind(d),
    db.prepare("SELECT id, at, who, act, app, feature, note, ref, extra FROM rv_actions WHERE day = ? " +
      "ORDER BY id DESC LIMIT 500").bind(d),
  ]);
  const states = {};
  for (const r of rows(res[1])) states[r.app] = stateObj(r);
  const prevDay = rows(res[5])[0] ? rows(res[5])[0].d : null;
  return {
    rev: Number(rows(res[0])[0] ? rows(res[0])[0].rev : 0) || 0,
    states,
    notes: rows(res[2]).map(noteObj),
    flags: rows(res[3]).map(flagObj),
    snoozes: rows(res[4]).map(snzObj),
    prev: prevDay ? { d: prevDay, kal: rows(res[6]).map((r) => r.app) } : null,
    log: rows(res[7]).map(logObj),
  };
}

/** One app on day d, for the action response: {rev, state, notes, flags, snoozes}. */
export async function getAppView(db, d, app, openDay) {
  const s = snzRule(d, openDay);
  const res = await db.batch([
    db.prepare(REV_SQL),
    db.prepare("SELECT app, st, snz, who, at FROM rv_state WHERE day = ? AND app = ?").bind(d, app),
    db.prepare("SELECT id, app, text, who, at FROM rv_notes WHERE day = ? AND app = ? AND deleted_at IS NULL " +
      "ORDER BY id").bind(d, app),
    db.prepare(`SELECT ${FLAG_COLS} FROM rv_flags WHERE app = ? AND ${FLAG_LIVE} ORDER BY id`)
      .bind(app, ...flagLiveArgs(d, openDay)),
    db.prepare(`SELECT ${SNZ_COLS} FROM rv_snoozes s WHERE s.app = ? AND ${s.sql} ORDER BY s.id`)
      .bind(app, ...s.args),
  ]);
  const st = rows(res[1])[0];
  return {
    rev: Number(rows(res[0])[0] ? rows(res[0])[0].rev : 0) || 0,
    state: st ? stateObj(st) : null,
    notes: rows(res[2]).map(noteObj),
    flags: rows(res[3]).map(flagObj),
    snoozes: rows(res[4]).map(snzObj),
  };
}

export async function getStates(db, d, apps) {
  const out = {};
  if (!apps.length) return out;
  const res = await db.prepare(
    `SELECT app, st, snz, who, at FROM rv_state WHERE day = ? AND app IN (${apps.map(() => "?").join(",")})`)
    .bind(d, ...apps).all();
  for (const r of rows(res)) out[r.app] = stateObj(r);
  return out;
}

export async function getFlag(db, id) {
  const r = await db.prepare(`SELECT ${FLAG_COLS} FROM rv_flags WHERE id = ?`).bind(id).first();
  return r ? flagObj(r) : null;
}

async function openFlagFor(db, app, feature) {
  const r = await db.prepare(`SELECT ${FLAG_COLS} FROM rv_flags WHERE app = ? AND ifnull(feature,'*') = ? ` +
    "AND status = 'open'").bind(app, feature ?? "*").first();
  return r ? flagObj(r) : null;
}

/** {"YYYY-MM-DD": {rev, kal, flag, notes, people}} for from…to; only days that have rows. */
export async function getCalendar(db, from, to) {
  const res = await db.batch([
    db.prepare("SELECT day, COUNT(*) AS rev, SUM(CASE WHEN st = 'kal' THEN 1 ELSE 0 END) AS kal FROM rv_state " +
      "WHERE day BETWEEN ? AND ? GROUP BY day").bind(from, to),
    db.prepare("SELECT day, COUNT(*) AS n FROM rv_flags WHERE day BETWEEN ? AND ? AND status <> 'withdrawn' " +
      "GROUP BY day").bind(from, to),
    db.prepare("SELECT day, COUNT(*) AS n FROM rv_notes WHERE day BETWEEN ? AND ? AND deleted_at IS NULL " +
      "GROUP BY day").bind(from, to),
    db.prepare("SELECT day, COUNT(DISTINCT who) AS n FROM rv_actions WHERE day BETWEEN ? AND ? GROUP BY day")
      .bind(from, to),
  ]);
  const days = {};
  const at = (d) => (days[d] ||= { rev: 0, kal: 0, flag: 0, notes: 0, people: 0 });
  for (const r of rows(res[0])) Object.assign(at(r.day), { rev: Number(r.rev) || 0, kal: Number(r.kal) || 0 });
  for (const r of rows(res[1])) at(r.day).flag = Number(r.n) || 0;
  for (const r of rows(res[2])) at(r.day).notes = Number(r.n) || 0;
  for (const r of rows(res[3])) at(r.day).people = Number(r.n) || 0;
  const out = {};
  for (const d of Object.keys(days).sort()) out[d] = days[d];
  return out;
}

// ── writes (one db.batch each; every one appends its rv_actions row inside that batch) ────────────

// ok / kal are refused only while a WHOLE-APP 🚩 raised on that day is still open (undecided). Once the admin has
// decided it (theek / kaam / band) the card can be marked again; the "flag" state row itself stays as History's record.
const NO_OPEN_APP_FLAG = "NOT EXISTS (SELECT 1 FROM rv_flags WHERE day = ? AND app = ? AND feature IS NULL AND status = 'open')";

/**
 * Apply one review action. `a` = {act, d, openDay, app, feature, note, days, apps, flagId, who, at,
 * label, labels (Map key→label), extra}. Returns {app} (single) or {changed} (bulk_ok).
 * @throws {ApiError} 409 conflict (why …) · 403 forbidden (why not_raised_today) · 404 not_found
 */
export async function applyAction(db, a) {
  const base = { at: a.at, who: a.who, day: a.d };
  switch (a.act) {
    case "ok":
    case "kal": {
      const snz = await activeSnoozedFeatures(db, a.d, a.app, a.openDay);
      const res = await db.batch([
        logStmt(db, { ...base, act: a.act, app: a.app, extra: a.extra },
          { guard: NO_OPEN_APP_FLAG, guardArgs: [a.d, a.app] }),
        db.prepare("INSERT INTO rv_state (day, app, st, snz, who, at) SELECT ?, ?, ?, ?, ?, ? " +
          `WHERE ${NO_OPEN_APP_FLAG} ` +
          "ON CONFLICT(day, app) DO UPDATE SET st = excluded.st, snz = excluded.snz, who = excluded.who, " +
          "at = excluded.at")
          .bind(a.d, a.app, a.act, JSON.stringify(snz), a.who, a.at, a.d, a.app),
      ]);
      if (!changes(res[0])) throw new ApiError(409, "conflict", { why: "flagged" });
      return { app: a.app };
    }
    case "note": {
      const snz = await activeSnoozedFeatures(db, a.d, a.app, a.openDay);
      await db.batch([
        db.prepare("INSERT INTO rv_notes (day, app, app_label, text, who, at) VALUES (?, ?, ?, ?, ?, ?)")
          .bind(a.d, a.app, a.label || "", a.note, a.who, a.at),
        logStmt(db, { ...base, act: "note", app: a.app, note: a.note, extra: a.extra }, {
          refSql: "(SELECT MAX(id) FROM rv_notes WHERE day = ? AND app = ? AND who = ? AND at = ?)",
          refArgs: [a.d, a.app, a.who, a.at],
        }),
        // a note also counts as reviewed ("📝 Reviewed + note") when the card has no state yet
        db.prepare("INSERT INTO rv_state (day, app, st, snz, who, at) VALUES (?, ?, 'ok', ?, ?, ?) " +
          "ON CONFLICT(day, app) DO NOTHING").bind(a.d, a.app, JSON.stringify(snz), a.who, a.at),
      ]);
      return { app: a.app };
    }
    case "flag": {
      const fk = a.feature ?? "*";
      const stmts = [
        db.prepare("INSERT INTO rv_flags (day, app, app_label, feature, note, raised_by, raised_at) " +
          "VALUES (?, ?, ?, ?, ?, ?, ?)").bind(a.d, a.app, a.label || "", a.feature ?? null, a.note || "", a.who, a.at),
        logStmt(db, { ...base, act: "flag", app: a.app, feature: a.feature ?? null, note: a.note }, {
          refSql: "(SELECT id FROM rv_flags WHERE app = ? AND ifnull(feature,'*') = ? AND status = 'open')",
          refArgs: [a.app, fk],
        }),
      ];
      if (a.feature == null) {   // whole app → the card's state is "🚩 Re-review (Important)"
        const snz = await activeSnoozedFeatures(db, a.d, a.app, a.openDay);
        stmts.push(db.prepare("INSERT INTO rv_state (day, app, st, snz, who, at) VALUES (?, ?, 'flag', ?, ?, ?) " +
          "ON CONFLICT(day, app) DO UPDATE SET st = 'flag', snz = excluded.snz, who = excluded.who, at = excluded.at")
          .bind(a.d, a.app, JSON.stringify(snz), a.who, a.at));
      }
      try {
        await db.batch(stmts);
      } catch (e) {
        const open = await openFlagFor(db, a.app, a.feature);   // the partial unique index said no
        if (open) throw new ApiError(409, "conflict", { why: "already_flagged", flag_id: open.id });
        throw e;
      }
      return { app: a.app };
    }
    case "unflag": {
      const flag = a.flagId ? await getFlag(db, a.flagId) : await openFlagFor(db, a.app, a.feature);
      if (!flag) throw new ApiError(404, "not_found");
      if (a.flagId && a.app && flag.app !== a.app) throw new ApiError(400, "bad_request", { field: "flag_id" });
      if (flag.day !== a.openDay) throw new ApiError(403, "forbidden", { why: "not_raised_today" });
      if (flag.status !== "open" || flag.decision !== null) throw new ApiError(409, "conflict", { why: "not_open" });
      const cond = "id = ? AND status = 'open' AND decision IS NULL AND day = ?";
      const stmts = [
        logStmt(db, { ...base, act: "unflag", app: flag.app, feature: flag.feature, ref: flag.id }, {
          guard: `EXISTS (SELECT 1 FROM rv_flags WHERE ${cond})`, guardArgs: [flag.id, a.openDay],
        }),
        db.prepare(`UPDATE rv_flags SET status = 'withdrawn', wd_by = ?, wd_at = ? WHERE ${cond}`)
          .bind(a.who, a.at, flag.id, a.openDay),
      ];
      if (flag.feature === null) {
        stmts.push(db.prepare("DELETE FROM rv_state WHERE day = ? AND app = ? AND st = 'flag' AND EXISTS " +
          "(SELECT 1 FROM rv_flags WHERE id = ? AND status = 'withdrawn' AND wd_at = ?)")
          .bind(a.d, flag.app, flag.id, a.at));
      }
      const res = await db.batch(stmts);
      if (!changes(res[0])) throw new ApiError(409, "conflict", { why: "not_open" });
      return { app: flag.app };
    }
    case "undo": {
      await db.batch([
        logStmt(db, { ...base, act: "undo", app: a.app, extra: a.extra }),
        db.prepare("DELETE FROM rv_state WHERE day = ? AND app = ?").bind(a.d, a.app),
        db.prepare("UPDATE rv_notes SET deleted_by = ?, deleted_at = ? WHERE day = ? AND app = ? AND deleted_at IS NULL")
          .bind(a.who, a.at, a.d, a.app),
        db.prepare("UPDATE rv_flags SET status = 'withdrawn', wd_by = ?, wd_at = ? WHERE day = ? AND app = ? " +
          "AND status = 'open' AND decision IS NULL").bind(a.who, a.at, a.d, a.app),
      ]);
      return { app: a.app };
    }
    case "snooze": {
      const until = addDays(a.openDay, a.days);
      await db.batch([
        db.prepare("UPDATE rv_snoozes SET cleared_by = ?, cleared_at = ? WHERE app = ? AND feature = ? " +
          "AND cleared_at IS NULL").bind(a.who, a.at, a.app, a.feature),
        db.prepare("INSERT INTO rv_snoozes (app, app_label, feature, day, until, days, note, who, at) " +
          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
          .bind(a.app, a.label || "", a.feature, a.openDay, until, a.days, a.note || "", a.who, a.at),
        logStmt(db, { ...base, act: "snooze", app: a.app, feature: a.feature, note: a.note,
          extra: { days: a.days, until } }, {
          refSql: "(SELECT id FROM rv_snoozes WHERE app = ? AND feature = ? AND cleared_at IS NULL)",
          refArgs: [a.app, a.feature],
        }),
      ]);
      return { app: a.app };
    }
    case "unsnooze": {
      const live = await db.prepare("SELECT id FROM rv_snoozes WHERE app = ? AND feature = ? AND cleared_at IS NULL " +
        "AND until >= ?").bind(a.app, a.feature, a.openDay).first();
      if (!live) throw new ApiError(404, "not_found");
      const res = await db.batch([
        logStmt(db, { ...base, act: "unsnooze", app: a.app, feature: a.feature, ref: live.id }, {
          guard: "EXISTS (SELECT 1 FROM rv_snoozes WHERE id = ? AND cleared_at IS NULL)", guardArgs: [live.id],
        }),
        db.prepare("UPDATE rv_snoozes SET cleared_by = ?, cleared_at = ? WHERE id = ? AND cleared_at IS NULL")
          .bind(a.who, a.at, live.id),
      ]);
      if (!changes(res[0])) throw new ApiError(404, "not_found");
      return { app: a.app };
    }
    case "bulk_ok": {
      // A FIXED number of statements for any group size (D1 Free allows 50 queries per request and counts each
      // statement of a batch): the keys go in as one JSON array and json_each() expands them inside SQLite.
      const s = snzRule(a.d, a.openDay);
      const snzRes = await db.prepare(`SELECT s.app AS app, s.feature AS feature FROM rv_snoozes s WHERE ${s.sql}`)
        .bind(...s.args).all();
      const want = new Set(a.apps);
      const snzBy = {};
      for (const r of rows(snzRes)) if (want.has(r.app)) (snzBy[r.app] ||= new Set()).add(r.feature);
      const snzMap = JSON.stringify(Object.fromEntries(
        Object.entries(snzBy).map(([k, v]) => [k, [...v].sort(byFeat)])));
      const keys = JSON.stringify(a.apps);
      const extra = JSON.stringify({ bulk: 1, ...(a.extra || {}) });
      const NO_STATE = "NOT EXISTS (SELECT 1 FROM rv_state st WHERE st.day = ? AND st.app = j.value)";
      const res = await db.batch([
        // one transaction: this SELECT sees exactly the apps the two INSERTs below change
        db.prepare(`SELECT j.value AS app FROM json_each(?) AS j WHERE ${NO_STATE} ORDER BY j.key`).bind(keys, a.d),
        db.prepare("INSERT INTO rv_actions (at, who, act, day, app, feature, note, ref, extra) " +
          `SELECT ?, ?, 'bulk_ok', ?, j.value, NULL, NULL, NULL, ? FROM json_each(?) AS j WHERE ${NO_STATE} ` +
          "ORDER BY j.key").bind(a.at, a.who, a.d, extra, keys, a.d),
        db.prepare("INSERT INTO rv_state (day, app, st, snz, who, at) " +
          "SELECT ?, j.value, 'ok', COALESCE(json_extract(?, '$.\"' || j.value || '\"'), '[]'), ?, ? " +
          "FROM json_each(?) AS j WHERE 1 ON CONFLICT(day, app) DO NOTHING")
          .bind(a.d, snzMap, a.who, a.at, keys),
      ]);
      const got = new Set(rows(res[0]).map((r) => r.app));
      return { changed: a.apps.filter((k) => got.has(k)) };
    }
    default:
      throw new ApiError(400, "bad_request", { field: "act" });
  }
}

/**
 * Admin decision on one 🚩 flag. `x` = {flagId, decision, note, who, at, logDay|null}. Returns the updated FLAG.
 * theek/band: open → closed · kaam: open → kaam · done: kaam → closed.
 */
export async function decideFlag(db, x) {
  const flag = await getFlag(db, x.flagId);
  if (!flag) throw new ApiError(404, "not_found");
  const why = (f) => (x.decision === "done"
    ? (f.status === "kaam" ? null : "not_kaam")
    : (f.status === "open" ? null : f.status === "withdrawn" ? "not_open" : "already_decided"));
  const w0 = why(flag);
  if (w0) throw new ApiError(409, "conflict", { why: w0 });
  const note = x.note ? x.note : null;
  const logDay = x.logDay || flag.day;
  let cond;
  let upd;
  if (x.decision === "done") {
    cond = "id = ? AND status = 'kaam'";
    upd = db.prepare("UPDATE rv_flags SET status = 'closed', done_note = ?, done_by = ?, done_at = ?, done_day = ? " +
      `WHERE ${cond}`).bind(note, x.who, x.at, logDay, flag.id);
  } else {
    cond = "id = ? AND status = 'open'";
    upd = db.prepare("UPDATE rv_flags SET status = ?, decision = ?, dec_note = ?, dec_by = ?, dec_at = ?, dec_day = ? " +
      `WHERE ${cond}`).bind(x.decision === "kaam" ? "kaam" : "closed", x.decision, note, x.who, x.at, logDay, flag.id);
  }
  const res = await db.batch([
    logStmt(db, { at: x.at, who: x.who, act: "decide", day: logDay, app: flag.app, feature: flag.feature,
      note, ref: flag.id, extra: { decision: x.decision } }, {
      guard: `EXISTS (SELECT 1 FROM rv_flags WHERE ${cond})`, guardArgs: [flag.id],
    }),
    upd,
  ]);
  const now = await getFlag(db, flag.id);
  if (!changes(res[0])) throw new ApiError(409, "conflict", { why: why(now) || "already_decided" });
  return now;
}

// ── 📌 saved dates of "compare any date" (GET /api/marks, POST /api/marks, POST /api/marks/delete) ──────────────────
// The Uninstall tab's Update impact card: a date the team names ("Banner ad hataya") for one app or every app ("*").
// index.js has already verified the Access login (JWT), the same-origin JSON POST rules and the body size; here the mark
// is validated strictly and kept in cmp_marks (audit rows in cmp_marks_log). Any logged-in user may add a mark; only its
// author or an admin may delete it (the row is only marked deleted, the log keeps both).

export const MARK_APP_RE = /^ca-app-pub-\d{1,24}~\d{1,24}$/;   // an AdMob app id (config.js APP_RE) — or "*": every app
export const MARK_NAME_MAX = 80;                // code points
export const MARK_DAYS = 400;                   // a mark's date: a real day of the last 400 days (IST)
export const MARKS_MAX = 2000;                  // live marks in all: a runaway client cannot fill D1
// control characters (C0, DEL, C1) and the bidi controls (LRM / RLM / ALM, embeddings, overrides, isolates)
const BAD_CHARS = /[\u0000-\u001F\u007F-\u009F\u061C\u200E\u200F\u202A-\u202E\u2066-\u2069]/;
const MARK_DAY_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Hinglish reasons the page shows (the field stays in `field`). */
export const MARK_MSG = {
  app_id: "App galat hai",
  date: "Date galat hai — pichhle 400 din ki koi asli date chuno",
  name: "Naam 1–80 akshar ka ho (koi control / ulta-likhne wala character nahi)",
  id: "Saved date galat hai",
  not_author: "Ye date sirf jisne save ki wo (ya admin) hata sakta hai",
  not_found: "Ye saved date ab nahi hai (shayad kisi ne hata di)",
  too_many: "Bahut saari saved dates — pehle kuch purani hatao",
  ranges: "Dono range galat hain — Pehle (from ≤ to) poori Baad se pehle ho, har range 400 din tak, pichhle ~4 saal me",
  kind: "Kya hatana hai, samajh nahi aaya",
  too_many_cmp: "Bahut saari saved tulna — pehle kuch purani hatao",
};

const bad = (field) => new ApiError(400, "bad_request", { field, msg: MARK_MSG[field] });

function isMarkDay(s) {
  if (typeof s !== "string" || !MARK_DAY_RE.test(s)) return false;
  const t = Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10));
  return new Date(t).toISOString().slice(0, 10) === s;
}

/** The IST calendar day of an ISO instant (the dashboard's day). */
export function istDay(nowIso) {
  return new Date(Date.parse(nowIso) + 330 * 60000).toISOString().slice(0, 10);
}

/** The name as stored: NFC, trimmed; 1–80 code points with no control / bidi character (rejected, never stripped). */
export function normName(v) {
  if (typeof v !== "string" || v.length > MARK_NAME_MAX * 8) throw bad("name");
  const s = v.normalize("NFC").trim();
  const n = [...s].length;
  if (n < 1 || n > MARK_NAME_MAX || BAD_CHARS.test(s)) throw bad("name");
  return s;
}

/** POST /api/marks body → {app, date, name}. Unknown keys are ignored. */
export function validateMark(b, nowIso) {
  const app = b.app_id;
  if (typeof app !== "string" || !(app === "*" || MARK_APP_RE.test(app))) throw bad("app_id");
  const date = b.date;
  const today = istDay(nowIso);
  if (!isMarkDay(date) || date > today || date < addDays(today, -MARK_DAYS)) throw bad("date");
  return { app, date, name: normName(b.name) };
}

/** POST /api/marks/delete body → the id (a date mark; kind "compare" → a saved compare, validateDeleteAny). */
export function validateDelete(b) {
  const id = b.id;
  if (typeof id !== "number" || !Number.isSafeInteger(id) || id <= 0) throw bad("id");
  return id;
}

/** POST /api/marks/delete body → {id, kind: "date" | "compare"}; no kind = a date mark (the body every older page sends). */
export function validateDeleteAny(b) {
  const id = validateDelete(b);
  const k = b.kind;
  if (k === undefined || k === null || k === "date") return { id, kind: "date" };
  if (k === "compare") return { id, kind: "compare" };
  throw bad("kind");
}

// ── 📅 saved CUSTOM compares (two ranges: Pehle b_from…b_to vs Baad a_from…a_to), the same rules as the marks ──────────
// POST /api/marks with any of before_from / before_to / after_from / after_to is a compare; one without them is a date
// mark (exactly as before). Listed by GET /api/marks as `compares` beside `marks`; deleted with {id, kind: "compare"}.
export const CMP_DAYS = 1500;                   // a range day: a real day of the last ~4 years (IST) — "saal bhar ka farak"
export const CMP_SPAN_MAX = 400;                // one range: at most 400 days
export const CMPS_MAX = 2000;                   // live saved compares in all
export const CMP_KEYS = ["before_from", "before_to", "after_from", "after_to"];

/** A POST /api/marks body that is a compare (any range key present). */
export function isCompareBody(b) {
  return CMP_KEYS.some((k) => Object.prototype.hasOwnProperty.call(b, k));
}

/** POST /api/marks compare body → {app, bf, bt, af, at, name}: four real days of the last CMP_DAYS (IST), Pehle from ≤ to,
 *  Baad from ≤ to, Pehle wholly before Baad, each range ≤ CMP_SPAN_MAX days. Unknown keys are ignored. */
export function validateCompare(b, nowIso) {
  const app = b.app_id;
  if (typeof app !== "string" || !(app === "*" || MARK_APP_RE.test(app))) throw bad("app_id");
  const today = istDay(nowIso), lo = addDays(today, -CMP_DAYS);
  const [bf, bt, af, at] = CMP_KEYS.map((k) => b[k]);
  const days = (x, y) => Math.round((Date.parse(y + "T00:00:00Z") - Date.parse(x + "T00:00:00Z")) / 86400000);
  if (![bf, bt, af, at].every((d) => isMarkDay(d) && d <= today && d >= lo)) throw bad("ranges");
  if (!(bf <= bt && bt < af && af <= at)) throw bad("ranges");
  if (days(bf, bt) >= CMP_SPAN_MAX || days(af, at) >= CMP_SPAN_MAX) throw bad("ranges");
  return { app, bf, bt, af, at, name: normName(b.name) };
}

const CMP_COLS = "id, app AS app_id, b_from AS before_from, b_to AS before_to, a_from AS after_from, a_to AS after_to, name, who, at";

/** Every live saved compare, newest Baad first. */
export async function listCompares(db) {
  const res = await db.prepare(`SELECT ${CMP_COLS} FROM cmp_ranges WHERE deleted_at IS NULL ORDER BY a_from DESC, id DESC`).all();
  return rows(res);
}

async function liveCompare(db, c) {
  return db.prepare(`SELECT ${CMP_COLS} FROM cmp_ranges WHERE app = ? AND b_from = ? AND b_to = ? AND a_from = ? AND a_to = ? ` +
    "AND name = ? AND deleted_at IS NULL").bind(c.app, c.bf, c.bt, c.af, c.at, c.name).first();
}

/** Add one compare (c = validateCompare's) as `who` at `at` → {compare, dup}: addMark's rules (the same app + ranges +
 *  name already saved → that one, dup; one batch: the row and its audit row in cmp_ranges_log, or neither). */
export async function addCompare(db, c, who, at) {
  const have = await liveCompare(db, c);
  if (have) return { compare: have, dup: true };
  const n = Number(await db.prepare("SELECT COUNT(*) AS n FROM cmp_ranges WHERE deleted_at IS NULL").first("n")) || 0;
  if (n >= CMPS_MAX) throw new ApiError(409, "conflict", { why: "too_many", msg: MARK_MSG.too_many_cmp });
  try {
    await db.batch([
      db.prepare("INSERT INTO cmp_ranges (app, b_from, b_to, a_from, a_to, name, who, at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
        .bind(c.app, c.bf, c.bt, c.af, c.at, c.name, who, at),
      db.prepare("INSERT INTO cmp_ranges_log (at, who, act, cmp, app, b_from, b_to, a_from, a_to, name) " +
        "SELECT ?, ?, 'add', id, app, b_from, b_to, a_from, a_to, name FROM cmp_ranges WHERE id = last_insert_rowid()").bind(at, who),
    ]);
  } catch (e) {
    const won = await liveCompare(db, c);
    if (won) return { compare: won, dup: true };
    throw e;
  }
  return { compare: await liveCompare(db, c), dup: false };
}

/** Delete compare `id` as `who` (its author, or an admin) at `at`: deleteMark's rules (only marked deleted + its audit
 *  row, one batch; deleted meanwhile / never there → 404; someone else's → 403). */
export async function deleteCompare(db, id, who, admin, at) {
  const c = await db.prepare(`SELECT ${CMP_COLS} FROM cmp_ranges WHERE id = ? AND deleted_at IS NULL`).bind(id).first();
  if (!c) throw new ApiError(404, "not_found", { msg: MARK_MSG.not_found });
  if (c.who !== who && !admin) throw new ApiError(403, "forbidden", { msg: MARK_MSG.not_author });
  const res = await db.batch([
    db.prepare("UPDATE cmp_ranges SET deleted_by = ?, deleted_at = ? WHERE id = ? AND deleted_at IS NULL").bind(who, at, id),
    db.prepare("INSERT INTO cmp_ranges_log (at, who, act, cmp, app, b_from, b_to, a_from, a_to, name) " +
      "SELECT ?, ?, 'delete', id, app, b_from, b_to, a_from, a_to, name FROM cmp_ranges WHERE id = ? AND changes() = 1").bind(at, who, id),
  ]);
  if (!changes(res[0])) throw new ApiError(404, "not_found", { msg: MARK_MSG.not_found });
  return c;
}

const MARK_COLS = "id, app AS app_id, date, name, who, at";

/** Every live mark, newest date first. */
export async function listMarks(db) {
  const res = await db.prepare(`SELECT ${MARK_COLS} FROM cmp_marks WHERE deleted_at IS NULL ORDER BY date DESC, id DESC`).all();
  return rows(res);
}

async function liveOne(db, app, date, name) {
  return db.prepare(`SELECT ${MARK_COLS} FROM cmp_marks WHERE app = ? AND date = ? AND name = ? AND deleted_at IS NULL`)
    .bind(app, date, name).first();
}

/**
 * Add one mark (m = validateMark's) as `who` at `at` → {mark, dup}. The same app + date + name already saved (by anyone)
 * → that one, dup: true (nothing written). One batch: the row and its audit row (cmp_marks_log), or neither.
 */
export async function addMark(db, m, who, at) {
  const have = await liveOne(db, m.app, m.date, m.name);
  if (have) return { mark: have, dup: true };
  const n = Number(await db.prepare("SELECT COUNT(*) AS n FROM cmp_marks WHERE deleted_at IS NULL").first("n")) || 0;
  if (n >= MARKS_MAX) throw new ApiError(409, "conflict", { why: "too_many", msg: MARK_MSG.too_many });
  try {
    await db.batch([
      db.prepare("INSERT INTO cmp_marks (app, date, name, who, at) VALUES (?, ?, ?, ?, ?)").bind(m.app, m.date, m.name, who, at),
      db.prepare("INSERT INTO cmp_marks_log (at, who, act, mark, app, date, name) " +
        "SELECT ?, ?, 'add', id, app, date, name FROM cmp_marks WHERE id = last_insert_rowid()").bind(at, who),
    ]);
  } catch (e) {
    // two people saving the same name on the same day at once: the one-live index refuses the second (its batch rolled
    // back) — it gets the first one's mark
    const won = await liveOne(db, m.app, m.date, m.name);
    if (won) return { mark: won, dup: true };
    throw e;
  }
  return { mark: await liveOne(db, m.app, m.date, m.name), dup: false };
}

/**
 * Delete mark `id` as `who` (its author, or an admin) at `at` → the deleted mark. Marks the row deleted and appends the
 * audit row in one batch; a mark deleted meanwhile → 404.
 */
export async function deleteMark(db, id, who, admin, at) {
  const mk = await db.prepare(`SELECT ${MARK_COLS} FROM cmp_marks WHERE id = ? AND deleted_at IS NULL`).bind(id).first();
  if (!mk) throw new ApiError(404, "not_found", { msg: MARK_MSG.not_found });
  if (mk.who !== who && !admin) throw new ApiError(403, "forbidden", { msg: MARK_MSG.not_author });
  const res = await db.batch([
    db.prepare("UPDATE cmp_marks SET deleted_by = ?, deleted_at = ? WHERE id = ? AND deleted_at IS NULL").bind(who, at, id),
    db.prepare("INSERT INTO cmp_marks_log (at, who, act, mark, app, date, name) " +
      "SELECT ?, ?, 'delete', id, app, date, name FROM cmp_marks WHERE id = ? AND changes() = 1").bind(at, who, id),
  ]);
  if (!changes(res[0])) throw new ApiError(404, "not_found", { msg: MARK_MSG.not_found });
  return mk;
}
