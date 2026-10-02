// 📌 Saved dates of "compare any date" (/api/marks): auth, CSRF / body rules, strict validation, add / list / delete
// (the author or an admin), "*" marks, the audit rows, the v3 → v5 migration (review + config data kept) and the D1
// budget — and the saved CUSTOM compares (two ranges, schema v5): the same rules, listed beside the marks, the older
// page's bodies unchanged (v4 → v5 keeps every mark). Synthetic data only (made-up app ids, example.test emails). node --test
import test from "node:test";
import assert from "node:assert/strict";
import { setup, makeIndex, K, D1, ORIGIN, OWNER, TEAMMATE, TEAM2 } from "./harness.js";
import { FakeD1 } from "./fake_d1.js";
import { SCHEMA, splitSql, ensureSchema, _resetSchemaForTests } from "../src/db.js";
import { istDay, MARK_MSG, MARKS_MAX, CMPS_MAX, SCHEMA_VERSION } from "../src/db.js";

const APP = "ca-app-pub-1001~3001";
const APP2 = "ca-app-pub-1001~3002";
const addD = (d, n) => new Date(Date.parse(d + "T00:00:00Z") + n * 86400000).toISOString().slice(0, 10);
const TODAY = () => istDay(new Date().toISOString());

const list = (t, opt) => t.call("GET", "/api/marks", opt);
const add = (t, body, opt = {}) => t.call("POST", "/api/marks", { ...opt, body });
const del = (t, body, opt = {}) => t.call("POST", "/api/marks/delete", { ...opt, body });
const log = (t) => t.db.q("SELECT act, who, mark, app, date, name FROM cmp_marks_log ORDER BY id");

test("routing and methods: unknown paths → 404, wrong methods → 405 with Allow (before auth)", async () => {
  const t = await setup();
  for (const p of ["/api/marks/", "/api/marks/nope", "/api/marksx", "/api/marks/delete/", "/api/marks/constructor"]) {
    const r = await t.call("GET", p, { token: null });
    assert.equal(r.status, 404, p);
    assert.deepEqual(r.json, { error: "not_found", msg: "Nahi mila" });
  }
  for (const [m, p, allow] of [["PUT", "/api/marks", "GET, POST"], ["DELETE", "/api/marks", "GET, POST"],
    ["OPTIONS", "/api/marks", "GET, POST"], ["GET", "/api/marks/delete", "POST"], ["OPTIONS", "/api/marks/delete", "POST"]]) {
    const r = await t.call(m, p, { token: null });
    assert.equal(r.status, 405, `${m} ${p}`);
    assert.equal(r.headers.get("allow"), allow);
    assert.equal(r.headers.get("access-control-allow-origin"), null, "never CORS");
  }
});

test("auth: no / bad / expired token → 401 on every route, nothing touches D1", async () => {
  const t = await setup();
  const day = addD(TODAY(), -10);
  for (const opt of [{ token: null }, { token: "x.y.z" }, { token: t.tokens.owner.slice(0, -4) + "AAAA" }]) {
    assert.equal((await list(t, opt)).status, 401);
    assert.equal((await add(t, { app_id: APP, date: day, name: "Banner ad hataya" }, opt)).status, 401);
    assert.equal((await del(t, { id: 1 }, opt)).status, 401);
  }
  // auth runs before the CSRF / body checks
  assert.equal((await add(t, { app_id: APP, date: day, name: "x" }, { token: null, origin: "https://evil.example.test", ct: "text/plain" })).status, 401);
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM sqlite_master WHERE name = 'cmp_marks'")[0].n, 0, "nothing touched D1");
});

test("CSRF / body: foreign or missing Origin → 403, not JSON → 415, > 8 KiB → 413, not an object → 400 body", async () => {
  const t = await setup();
  const ok = { app_id: APP, date: addD(TODAY(), -10), name: "Banner ad hataya" };
  for (const origin of [null, "https://evil.example.test", "null", "http://localhost:8080"]) {
    const r = await add(t, ok, { origin });
    assert.equal(r.status, 403, String(origin));
    assert.equal(r.json.error, "forbidden");
    assert.equal((await del(t, { id: 1 }, { origin })).status, 403);
  }
  for (const ct of ["text/plain", "application/x-www-form-urlencoded", null]) assert.equal((await add(t, ok, { ct })).status, 415);
  const big = await add(t, { ...ok, pad: "x".repeat(9 * 1024) });
  assert.equal(big.status, 413);
  assert.deepEqual(big.json, { error: "payload_too_large", msg: "Request bahut badi hai" });
  for (const raw of ["{not json", "[1]", "null", "7"]) {
    const r = await t.call("POST", "/api/marks", { body: raw, raw: true });
    assert.equal(r.status, 400, raw);
    assert.equal(r.json.field, "body");
  }
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM sqlite_master WHERE name = 'cmp_marks'")[0].n, 0, "nothing touched D1");
});

test("validation: app_id format or '*', a real date of the last 400 days (IST), a 1–80 char name with no control / bidi character", async () => {
  const t = await setup();
  const today = TODAY(), day = addD(today, -10), name = "Banner ad hataya";
  const cases = [
    [{ date: day, name }, "app_id"], [{ app_id: "", date: day, name }, "app_id"], [{ app_id: "**", date: day, name }, "app_id"],
    [{ app_id: "com.demo.app", date: day, name }, "app_id"], [{ app_id: "ca-app-pub-1~", date: day, name }, "app_id"],
    [{ app_id: APP + " ", date: day, name }, "app_id"], [{ app_id: 5, date: day, name }, "app_id"],
    [{ app_id: APP, name }, "date"], [{ app_id: APP, date: "2026-02-30", name }, "date"], [{ app_id: APP, date: "26-09-15", name }, "date"],
    [{ app_id: APP, date: addD(today, 1), name }, "date"], [{ app_id: APP, date: addD(today, -401), name }, "date"],
    [{ app_id: APP, date: day + "T00:00", name }, "date"],
    [{ app_id: APP, date: day }, "name"], [{ app_id: APP, date: day, name: "" }, "name"], [{ app_id: APP, date: day, name: "   " }, "name"],
    [{ app_id: APP, date: day, name: "x".repeat(81) }, "name"], [{ app_id: APP, date: day, name: "a\nb" }, "name"],
    [{ app_id: APP, date: day, name: "a\u0007b" }, "name"], [{ app_id: APP, date: day, name: "a\u202Eb" }, "name"],
    [{ app_id: APP, date: day, name: "a\u2066b" }, "name"], [{ app_id: APP, date: day, name: "a\u200Fb" }, "name"],
    [{ app_id: APP, date: day, name: 42 }, "name"],
  ];
  for (const [body, field] of cases) {
    const r = await add(t, body);
    assert.equal(r.status, 400, JSON.stringify(body).slice(0, 90));
    assert.equal(r.json.field, field, JSON.stringify(body).slice(0, 90));
    assert.equal(r.json.msg, MARK_MSG[field]);
  }
  for (const body of [{}, { id: 0 }, { id: -1 }, { id: 1.5 }, { id: "1" }, { id: null }]) {
    const r = await del(t, body);
    assert.equal(r.status, 400, JSON.stringify(body));
    assert.equal(r.json.field, "id");
  }
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM cmp_marks")[0].n, 0);
  // the edges that ARE allowed: today, 400 days back, 80 characters (emoji = one each), NFC + trimmed
  const okBodies = [{ app_id: APP, date: today, name: "aaj" }, { app_id: APP, date: addD(today, -400), name: "400 din" },
    { app_id: "*", date: day, name: "📌".repeat(80) }, { app_id: APP2, date: day, name: "  Cafe\u0301 notification shuru  " }];
  for (const b of okBodies) assert.equal((await add(t, b)).status, 200, JSON.stringify(b).slice(0, 60));
  assert.deepEqual(t.db.q("SELECT name FROM cmp_marks WHERE app = ?", APP2), [{ name: "Caf\u00e9 notification shuru" }]);
});

test("add / list: any logged-in user adds; who + when stored; the same app + date + name is one mark (dup); '*' marks listed", async () => {
  const t = await setup();
  const d1 = addD(TODAY(), -20), d2 = addD(TODAY(), -5);
  const empty = await list(t);
  assert.equal(empty.status, 200);
  assert.deepEqual(empty.json, { marks: [], compares: [], me: TEAMMATE, admin: false });
  const a = await add(t, { app_id: APP, date: d1, name: "Banner ad hataya" });
  assert.equal(a.status, 200);
  assert.equal(a.json.ok, true);
  assert.equal(a.json.dup, false);
  assert.deepEqual({ ...a.json.mark, at: "t" }, { id: 1, app_id: APP, date: d1, name: "Banner ad hataya", who: TEAMMATE, at: "t" });
  assert.match(a.json.mark.at, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  const star = await add(t, { app_id: "*", date: d2, name: "Notification shuru" }, { token: t.tokens.owner });
  assert.equal(star.status, 200);
  assert.equal(star.json.mark.who, OWNER);
  assert.deepEqual(star.json.marks.map((m) => [m.app_id, m.date]), [["*", d2], [APP, d1]], "newest date first");
  const dup = await add(t, { app_id: APP, date: d1, name: " Banner ad hataya " }, { token: t.tokens.team2 });
  assert.equal(dup.status, 200);
  assert.equal(dup.json.dup, true);
  assert.equal(dup.json.mark.id, 1);
  assert.equal(dup.json.mark.who, TEAMMATE, "the first author stays");
  const other = await add(t, { app_id: APP, date: d1, name: "Banner ad wapas" });
  assert.equal(other.json.dup, false);
  const L = await list(t, { token: t.tokens.owner });
  assert.equal(L.json.admin, true);
  assert.equal(L.json.me, OWNER);
  assert.equal(L.json.marks.length, 3);
  assert.deepEqual(log(t).map((r) => [r.act, r.who, r.mark]), [["add", TEAMMATE, 1], ["add", OWNER, 2], ["add", TEAMMATE, 3]],
    "one audit row per real add (none for the dup)");
  for (const r of [a, star, L]) assert.equal(r.headers.get("cache-control"), "no-store");
});

test("delete: the author OK, another user 403, an admin OK; deleted twice → 404; the row is only marked, the log keeps both", async () => {
  const t = await setup();
  const d = addD(TODAY(), -30);
  const m1 = (await add(t, { app_id: APP, date: d, name: "Ad placement badla" })).json.mark;
  const m2 = (await add(t, { app_id: "*", date: d, name: "Sab apps pe naya SDK" })).json.mark;
  const m3 = (await add(t, { app_id: APP2, date: d, name: "Teen" }, { token: t.tokens.team2 })).json.mark;
  // another (non-admin) user may not
  const no = await del(t, { id: m1.id }, { token: t.tokens.team2 });
  assert.equal(no.status, 403);
  assert.deepEqual(no.json, { error: "forbidden", msg: MARK_MSG.not_author });
  assert.equal((await list(t)).json.marks.length, 3);
  // the author may
  const own = await del(t, { id: m1.id });
  assert.equal(own.status, 200);
  assert.deepEqual([own.json.ok, own.json.id], [true, m1.id]);
  assert.deepEqual(own.json.marks.map((m) => m.id).sort(), [m2.id, m3.id].sort());
  // an admin may delete anyone's
  const adm = await del(t, { id: m3.id }, { token: t.tokens.owner });
  assert.equal(adm.status, 200);
  // gone / never there → 404
  for (const id of [m1.id, 999]) {
    const r = await del(t, { id }, { token: t.tokens.owner });
    assert.equal(r.status, 404);
    assert.equal(r.json.msg, MARK_MSG.not_found);
  }
  assert.deepEqual((await list(t)).json.marks.map((m) => m.id), [m2.id]);
  assert.deepEqual(t.db.q("SELECT id, deleted_by FROM cmp_marks ORDER BY id").map((r) => [r.id, r.deleted_by]),
    [[m1.id, TEAMMATE], [m2.id, null], [m3.id, OWNER]], "rows kept, marked deleted");
  assert.deepEqual(log(t).map((r) => [r.act, r.who, r.mark]),
    [["add", TEAMMATE, m1.id], ["add", TEAMMATE, m2.id], ["add", TEAM2, m3.id], ["delete", TEAMMATE, m1.id], ["delete", OWNER, m3.id]]);
  // a deleted name can be saved again (one LIVE mark per app + date + name)
  const again = await add(t, { app_id: APP, date: d, name: "Ad placement badla" }, { token: t.tokens.team2 });
  assert.equal(again.json.dup, false);
  assert.notEqual(again.json.mark.id, m1.id);
});

test("two people deleting the same mark at once: one 200, one 404, ONE audit row", async () => {
  const t = await setup();
  const m = (await add(t, { app_id: APP, date: addD(TODAY(), -3), name: "Ek" }, { token: t.tokens.owner })).json.mark;
  const [x, y] = await Promise.all([del(t, { id: m.id }, { token: t.tokens.owner }), del(t, { id: m.id }, { token: t.tokens.owner })]);
  assert.deepEqual([x.status, y.status].sort(), [200, 404]);
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM cmp_marks_log WHERE act = 'delete'")[0].n, 1);
});

test("two people saving the same date + name at once: one mark, both answered OK with it", async () => {
  const t = await setup();
  const body = { app_id: "*", date: addD(TODAY(), -8), name: "Same" };
  const [x, y] = await Promise.all([add(t, body), add(t, body, { token: t.tokens.team2 })]);
  assert.deepEqual([x.status, y.status], [200, 200]);
  assert.equal(x.json.mark.id, y.json.mark.id);
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM cmp_marks")[0].n, 1);
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM cmp_marks_log")[0].n, 1);
});

test("at most MARKS_MAX live marks: one more → 409 with the Hinglish reason, nothing written", async () => {
  const t = await setup();
  await list(t);                                   // the schema is there
  const day = addD(TODAY(), -2);
  const ins = t.db.sqlite.prepare("INSERT INTO cmp_marks (app, date, name, who, at) VALUES ('*', ?, ?, 'x@example.test', 't')");
  for (let i = 0; i < MARKS_MAX; i++) ins.run(day, "m" + i);
  const r = await add(t, { app_id: APP, date: day, name: "one more" });
  assert.equal(r.status, 409);
  assert.deepEqual(r.json, { error: "conflict", msg: MARK_MSG.too_many, why: "too_many" });
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM cmp_marks_log")[0].n, 0);
});

test("a schema_version 3 database is migrated to 5: the marks and compares work, review and config data untouched", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  const v3 = splitSql(SCHEMA).filter((s) => !s.includes("cmp_marks") && !s.includes("cmp_ranges") && !s.startsWith("INSERT"));
  for (const s of v3) db.sqlite.exec(s);
  db.sqlite.exec("INSERT INTO rv_meta VALUES ('schema_version', '3')");
  db.sqlite.exec("INSERT INTO rv_state (day, app, st, who, at) VALUES ('2026-10-01','a1a1a1a1a1a1','ok','x@example.test','t')");
  db.sqlite.exec("INSERT INTO rv_notes (day, app, text, who, at) VALUES ('2026-10-01','a1a1a1a1a1a1','note','x@example.test','t')");
  db.sqlite.exec("INSERT INTO rv_actions (at, who, act, day, app) VALUES ('t','x@example.test','ok','2026-10-01','a1a1a1a1a1a1')");
  db.sqlite.exec("INSERT INTO config_log (who, at, file, bytes, result) VALUES ('x@example.test','t','app_names',12,'ok')");
  const before = ["rv_state", "rv_notes", "rv_actions", "config_log"].map((n) => db.q(`SELECT * FROM ${n}`));
  assert.equal(db.q("SELECT COUNT(*) AS n FROM sqlite_master WHERE name LIKE 'cmp_marks%'")[0].n, 0);
  const batches = db.batches;
  assert.equal(await ensureSchema(db), 5);
  assert.equal(db.batches, batches + 3, "the schema batch + one batch per migration (4, 5)");
  assert.deepEqual(db.q("SELECT v FROM rv_meta WHERE k = 'schema_version'"), [{ v: "5" }]);
  assert.equal(db.q("SELECT COUNT(*) AS n FROM sqlite_master WHERE name IN ('cmp_marks','cmp_marks_one_live','cmp_marks_log')")[0].n, 3);
  assert.equal(db.q("SELECT COUNT(*) AS n FROM sqlite_master WHERE name IN ('cmp_ranges','cmp_ranges_one_live','cmp_ranges_log')")[0].n, 3);
  assert.deepEqual(["rv_state", "rv_notes", "rv_actions", "config_log"].map((n) => db.q(`SELECT * FROM ${n}`)), before, "data kept");
  _resetSchemaForTests();
  // the same database behind the Worker: the review API and the marks both work
  const t = await setup();
  t.env.REVIEW_DB = db;
  const r = await add(t, { app_id: APP, date: addD(TODAY(), -1), name: "Migrated" });
  assert.equal(r.status, 200);
  assert.equal((await t.day(D1)).states[K.a], undefined, "the open day's states read fine");
  assert.equal(db.q("SELECT COUNT(*) AS n FROM rv_state")[0].n, 1);
  assert.equal(db.q("SELECT COUNT(*) AS n FROM config_log")[0].n, 1);
});

test("the marks endpoints stay inside the D1 Free budget (cold isolate) and never send CORS headers", async () => {
  const t = await setup({ index: makeIndex(D1) });
  const day = addD(TODAY(), -12);
  const cost = async (fn) => { t.resetCaches(); const n0 = t.db.statements.length; const r = await fn(); return [t.db.statements.length - n0, r]; };
  for (const [name, fn] of [["list", () => list(t)], ["add", () => add(t, { app_id: APP, date: day, name: "a" })],
    ["dup", () => add(t, { app_id: APP, date: day, name: "a" })], ["delete", () => del(t, { id: 1 })],
    ["compare", () => add(t, { app_id: APP, name: "c", before_from: addD(day, -14), before_to: addD(day, -8), after_from: addD(day, -7), after_to: day })],
    ["compare delete", () => del(t, { id: 1, kind: "compare" })]]) {
    const [n, r] = await cost(fn);
    assert.equal(r.status, 200, `${name}: ${r.text}`);
    assert.ok(n <= 50, `${name} used ${n} D1 statements`);
    assert.equal(r.headers.get("access-control-allow-origin"), null);
  }
  assert.equal(ORIGIN, "http://localhost");
});

// ── 📅 saved custom compares (two ranges; schema v5) ─────────────────────────────────────────────────────────────────
const cmp = (bf, bt, af, at, name, app = APP) => ({ app_id: app, name, before_from: bf, before_to: bt, after_from: af, after_to: at });
const clog = (t) => t.db.q("SELECT act, who, cmp, app, b_from, b_to, a_from, a_to, name FROM cmp_ranges_log ORDER BY id");

test("compares: add / list / dup beside the marks; the answer carries both lists; who + when stored", async () => {
  const t = await setup();
  const T = TODAY(), b0 = addD(T, -60), b1 = addD(T, -54), a0 = addD(T, -30), a1 = addD(T, -24);
  const m = await add(t, { app_id: APP, date: addD(T, -3), name: "Ek date" });
  assert.deepEqual(m.json.compares, []);
  const c = await add(t, cmp(b0, b1, a0, a1, "Diwali vs pehle"));
  assert.equal(c.status, 200);
  assert.equal(c.json.ok, true);
  assert.equal(c.json.dup, false);
  assert.deepEqual({ ...c.json.compare, at: "t" }, { id: 1, app_id: APP, before_from: b0, before_to: b1, after_from: a0, after_to: a1,
    name: "Diwali vs pehle", who: TEAMMATE, at: "t" });
  assert.equal(c.json.mark, undefined, "a compare is never a date mark");
  assert.deepEqual(c.json.marks.map((x) => x.name), ["Ek date"], "the marks are untouched");
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM cmp_marks")[0].n, 1);
  const star = await add(t, cmp(addD(T, -400), addD(T, -394), addD(T, -10), addD(T, -4), "Saal bhar baad", "*"), { token: t.tokens.owner });
  assert.equal(star.status, 200);
  assert.deepEqual(star.json.compares.map((x) => [x.app_id, x.after_from]), [["*", addD(T, -10)], [APP, a0]], "newest Baad first");
  const dup = await add(t, cmp(b0, b1, a0, a1, "  Diwali vs pehle "), { token: t.tokens.team2 });
  assert.deepEqual([dup.json.dup, dup.json.compare.id, dup.json.compare.who], [true, 1, TEAMMATE]);
  const other = await add(t, cmp(b0, b1, a0, addD(a1, 1), "Diwali vs pehle"));
  assert.equal(other.json.dup, false, "other ranges = another compare");
  const L = await list(t);
  assert.deepEqual(Object.keys(L.json).sort(), ["admin", "compares", "marks", "me"]);
  assert.equal(L.json.compares.length, 3);
  assert.equal(L.json.marks.length, 1);
  assert.deepEqual(clog(t).map((r) => [r.act, r.who, r.cmp, r.name]),
    [["add", TEAMMATE, 1, "Diwali vs pehle"], ["add", OWNER, 2, "Saal bhar baad"], ["add", TEAMMATE, 3, "Diwali vs pehle"]]);
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM cmp_marks_log")[0].n, 1, "the marks' log only has the mark");
});

test("compares: strict validation — real days of the last ~4 years, Pehle wholly before Baad, ≤ 400 days each, the name rule", async () => {
  const t = await setup();
  const T = TODAY(), name = "Tulna";
  const B = [addD(T, -40), addD(T, -34)], A = [addD(T, -20), addD(T, -14)];
  const cases = [
    cmp(B[0], B[1], A[0], "2026-02-30", name), cmp(B[0], B[1], A[0], addD(T, 1), name), cmp(addD(T, -1501), B[1], A[0], A[1], name),
    cmp(B[1], B[0], A[0], A[1], name), cmp(B[0], B[1], A[1], A[0], name), cmp(B[0], A[0], A[0], A[1], name),
    cmp(A[0], A[1], B[0], B[1], name), cmp(addD(T, -900), addD(T, -500), A[0], A[1], name),
    cmp(B[0], B[1], addD(T, -420), T, name), { app_id: APP, name, before_from: B[0], before_to: B[1], after_from: A[0] },
    { app_id: APP, name, before_from: B[0], before_to: B[1], after_from: A[0], after_to: 5 },
    cmp(B[0] + "T00:00", B[1], A[0], A[1], name),
  ];
  for (const body of cases) {
    const r = await add(t, body);
    assert.equal(r.status, 400, JSON.stringify(body));
    assert.equal(r.json.field, "ranges", JSON.stringify(body));
    assert.equal(r.json.msg, MARK_MSG.ranges);
  }
  for (const [body, field] of [[cmp(B[0], B[1], A[0], A[1], ""), "name"], [cmp(B[0], B[1], A[0], A[1], "a\u202Eb"), "name"],
    [cmp(B[0], B[1], A[0], A[1], name, "com.demo"), "app_id"], [{ ...cmp(B[0], B[1], A[0], A[1], name), app_id: undefined }, "app_id"]]) {
    const r = await add(t, body);
    assert.equal(r.status, 400);
    assert.equal(r.json.field, field);
  }
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM cmp_ranges")[0].n, 0);
  // the edges that ARE allowed: one-day ranges, Baad ending today, 400 days in a range, ~4 years back
  for (const b of [cmp(addD(T, -2), addD(T, -2), addD(T, -1), addD(T, -1), "ek din"), cmp(addD(T, -900), addD(T, -501), addD(T, -6), T, "400 din"),
    cmp(addD(T, -1500), addD(T, -1494), addD(T, -7), addD(T, -1), "4 saal")]) assert.equal((await add(t, b)).status, 200, JSON.stringify(b));
});

test("compares: delete with kind 'compare' — the author OK, another user 403, an admin OK, twice → 404; {id} alone is still a date mark", async () => {
  const t = await setup();
  const T = TODAY();
  const mk = (await add(t, { app_id: APP, date: addD(T, -5), name: "Date wali" })).json.mark;          // id 1 in cmp_marks
  const c1 = (await add(t, cmp(addD(T, -40), addD(T, -34), addD(T, -20), addD(T, -14), "Ek"))).json.compare;   // id 1 in cmp_ranges
  const c2 = (await add(t, cmp(addD(T, -40), addD(T, -34), addD(T, -20), addD(T, -14), "Do"), { token: t.tokens.team2 })).json.compare;
  assert.equal(mk.id, c1.id, "two id spaces");
  const no = await del(t, { id: c2.id, kind: "compare" });
  assert.equal(no.status, 403);
  assert.equal(no.json.msg, MARK_MSG.not_author);
  // an older page's body {id}: the DATE mark with that id, never the compare
  const old = await del(t, { id: mk.id });
  assert.equal(old.status, 200);
  assert.deepEqual([old.json.kind, old.json.marks.length, old.json.compares.length], ["date", 0, 2]);
  const own = await del(t, { id: c1.id, kind: "compare" });
  assert.equal(own.status, 200);
  assert.deepEqual([own.json.ok, own.json.id, own.json.kind], [true, c1.id, "compare"]);
  assert.deepEqual(own.json.compares.map((x) => x.id), [c2.id]);
  assert.equal((await del(t, { id: c2.id, kind: "compare" }, { token: t.tokens.owner })).status, 200, "an admin may");
  for (const id of [c1.id, 99]) assert.equal((await del(t, { id, kind: "compare" }, { token: t.tokens.owner })).status, 404);
  for (const kind of ["mark", "", 1, "Compare"]) {
    const r = await del(t, { id: c2.id, kind });
    assert.equal(r.status, 400, String(kind));
    assert.equal(r.json.field, "kind");
  }
  assert.deepEqual(t.db.q("SELECT id, deleted_by FROM cmp_ranges ORDER BY id").map((r) => [r.id, r.deleted_by]), [[c1.id, TEAMMATE], [c2.id, OWNER]]);
  assert.deepEqual(clog(t).map((r) => [r.act, r.cmp]), [["add", c1.id], ["add", c2.id], ["delete", c1.id], ["delete", c2.id]]);
});

test("compares: at most CMPS_MAX live ones → 409; two people saving the same compare at once → one row", async () => {
  const t = await setup();
  const T = TODAY(), body = cmp(addD(T, -40), addD(T, -34), addD(T, -20), addD(T, -14), "Same", "*");
  const [x, y] = await Promise.all([add(t, body), add(t, body, { token: t.tokens.team2 })]);
  assert.deepEqual([x.status, y.status, x.json.compare.id], [200, 200, y.json.compare.id]);
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM cmp_ranges")[0].n, 1);
  const ins = t.db.sqlite.prepare("INSERT INTO cmp_ranges (app, b_from, b_to, a_from, a_to, name, who, at) VALUES ('*', ?, ?, ?, ?, ?, 'x@example.test', 't')");
  for (let i = 1; i < CMPS_MAX; i++) ins.run(body.before_from, body.before_to, body.after_from, body.after_to, "c" + i);
  const r = await add(t, { ...body, name: "one more" });
  assert.equal(r.status, 409);
  assert.deepEqual(r.json, { error: "conflict", msg: MARK_MSG.too_many_cmp, why: "too_many" });
});

test("a schema_version 4 database (the live one) → 5: every saved date kept and still listed / deletable, compares added", async () => {
  _resetSchemaForTests();
  const db = new FakeD1();
  const v4 = splitSql(SCHEMA).filter((s) => !s.includes("cmp_ranges") && !s.startsWith("INSERT"));
  for (const s of v4) db.sqlite.exec(s);
  db.sqlite.exec("INSERT INTO rv_meta VALUES ('schema_version', '4')");
  const d = addD(TODAY(), -9);
  db.sqlite.exec(`INSERT INTO cmp_marks (app, date, name, who, at) VALUES ('${APP}', '${d}', 'Purani', '${TEAMMATE}', 't')`);
  db.sqlite.exec(`INSERT INTO cmp_marks_log (at, who, act, mark, app, date, name) VALUES ('t', '${TEAMMATE}', 'add', 1, '${APP}', '${d}', 'Purani')`);
  const batches = db.batches;
  assert.equal(await ensureSchema(db), SCHEMA_VERSION);
  assert.equal(SCHEMA_VERSION, 5);
  assert.equal(db.batches, batches + 2, "the schema batch + migration 5");
  assert.deepEqual(db.q("SELECT v FROM rv_meta WHERE k = 'schema_version'"), [{ v: "5" }]);
  _resetSchemaForTests();
  const t = await setup();
  t.env.REVIEW_DB = db;
  const L = await list(t);
  assert.deepEqual(L.json.marks.map((m) => [m.id, m.name]), [[1, "Purani"]]);
  assert.deepEqual(L.json.compares, []);
  const c = await add(t, cmp(addD(TODAY(), -40), addD(TODAY(), -34), addD(TODAY(), -20), addD(TODAY(), -14), "Nayi"));
  assert.equal(c.status, 200);
  assert.equal((await del(t, { id: 1 })).json.marks.length, 0, "the old mark deletes as before");
  assert.equal(db.q("SELECT COUNT(*) AS n FROM cmp_ranges")[0].n, 1);
  _resetSchemaForTests();
});
