// Cloudflare D1 limits the Worker must stay inside (node --test).
// - Workers Free allows 50 D1 queries per request, and every statement inside a batch() counts.
// - At most 100 bound parameters per statement.
// Every endpoint is measured on a COLD isolate (schema check included), which is the worst case.
import test from "node:test";
import assert from "node:assert/strict";
import { setup, makeIndex, K, D0, D1 } from "./harness.js";

const D1_FREE_QUERIES = 50;
const MAX_PARAMS = 100;

// 60 synthetic keys (the API's bulk_ok maximum), all in the open day's snapshot
const KEYS = Array.from({ length: 60 }, (_, i) => (0xa00000000000 + i).toString(16));
const bigIndex = () => makeIndex(D1, { open_apps: Object.fromEntries(KEYS.map((k, i) => [k, `Demo App ${i} · Acme Games`])) });

/** Statements executed by one request on a cold isolate. */
async function cost(t, fn) {
  t.resetCaches();
  const before = t.db.statements.length;
  const r = await fn();
  return { n: t.db.statements.length - before, r };
}

test("every endpoint stays under the D1 Free budget of 50 queries per request (cold isolate)", async () => {
  const t = await setup({ index: bigIndex() });
  const [A, B, C] = KEYS;
  const own = { token: t.tokens.owner };
  const seen = {};
  const run = async (name, fn, status = 200) => {
    const { n, r } = await cost(t, fn);
    assert.equal(r.status, status, `${name}: ${r.text}`);
    assert.ok(n <= D1_FREE_QUERIES, `${name} used ${n} D1 statements`);
    seen[name] = n;
  };
  await run("me", () => t.get("me"));
  await run("ok", () => t.act({ act: "ok", app: A }));
  await run("kal", () => t.act({ act: "kal", app: A }));
  const nt = await t.act({ act: "note", app: A, note: "n" });
  await run("note", () => t.act({ act: "note", app: A, note: "n" }));
  await run("note_edit", () => t.act({ act: "note_edit", app: A, note_id: nt.json.notes[0].id, note: "m" }, own));
  const on = await t.act({ d: D0, act: "note", app: K.a, note: "o" }, own);   // (K.a: in the older day's snapshot)
  await run("note_edit (older day, admin)", () => t.act({ d: D0, act: "note_edit", app: K.a, note_id: on.json.notes[0].id, note: "p" }, own));
  await run("flag feature", () => t.act({ act: "flag", app: A, feature: "kamai" }));
  await run("flag conflict", () => t.act({ act: "flag", app: A, feature: "kamai" }), 409);
  await run("flag app", () => t.act({ act: "flag", app: B }));
  await run("ok on flagged", () => t.act({ act: "ok", app: B }), 409);
  await run("unflag", () => t.act({ act: "unflag", app: B, feature: null }));
  await run("snooze", () => t.act({ act: "snooze", app: C, feature: "ads", days: 7 }));
  await run("unsnooze", () => t.act({ act: "unsnooze", app: C, feature: "ads" }));
  await run("undo", () => t.act({ act: "undo", app: A }));
  await run("bulk_ok 60", () => t.act({ act: "bulk_ok", apps: KEYS }));
  const f = (await t.act({ act: "flag", app: C, feature: "ads" })).json.flags[0];
  await run("decide kaam", () => t.decide({ flag_id: f.id, decision: "kaam", note: "k" }));
  await run("decide done", () => t.decide({ flag_id: f.id, decision: "done" }));
  await run("day", () => t.get(`day?d=${D1}`));
  await run("day (older)", () => t.get("day?d=2026-10-01", own));
  await run("calendar", () => t.get("calendar?from=2025-09-01&to=2026-10-05"));
  assert.ok(Object.keys(seen).length >= 20);
});

test("bulk_ok uses the same number of D1 statements for 2 apps and for 60 apps", async () => {
  const t = await setup({ index: bigIndex() });
  const two = await cost(t, () => t.act({ act: "bulk_ok", apps: KEYS.slice(0, 2) }));
  const sixty = await cost(t, () => t.act({ act: "bulk_ok", apps: KEYS }));
  assert.equal(two.r.status, 200);
  assert.equal(sixty.r.status, 200);
  assert.equal(two.r.json.changed.length, 2);
  assert.equal(sixty.r.json.changed.length, 58, "the 2 already reviewed are left alone");
  assert.equal(sixty.n, two.n);
  assert.equal(Object.keys(sixty.r.json.states).length, 60);
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM rv_actions WHERE act = 'bulk_ok'")[0].n, 60);
});

test("no statement binds more than 100 parameters (D1 limit)", async (tt) => {
  const t = await setup({ index: bigIndex() });
  const counts = [];
  const orig = t.db.prepare.bind(t.db);
  tt.mock.method(t.db, "prepare", (sql) => {
    const st = orig(sql);
    const bind = st.bind.bind(st);
    st.bind = (...v) => {
      counts.push(v.length);
      return bind(...v);
    };
    return st;
  });
  await t.act({ act: "bulk_ok", apps: KEYS });
  await t.act({ act: "note", app: KEYS[0], note: "n" });
  await t.get(`day?d=${D1}`);
  await t.get("calendar?from=2026-01-01&to=2026-10-05");
  assert.ok(counts.length > 10);
  assert.ok(Math.max(...counts) <= MAX_PARAMS, `max params ${Math.max(...counts)}`);
});
