// Review API behaviour through the real Worker entry (fake D1 over node:sqlite, fake ASSETS). node --test
import test from "node:test";
import assert from "node:assert/strict";
import {
  setup, makeIndex, siteFiles, K, D0, D1, D2, ORIGIN, OWNER, TEAMMATE, TEAM2, LABEL, SEEN,
} from "./harness.js";

const EXPECT_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
  "x-content-type-options": "nosniff",
  "referrer-policy": "no-referrer",
  "x-robots-tag": "noindex",
};
function assertApiHeaders(r) {
  for (const [k, v] of Object.entries(EXPECT_HEADERS)) assert.equal(r.headers.get(k), v, k);
}
const actions = (t) => t.db.q("SELECT * FROM rv_actions ORDER BY id");

// ── routing, methods, headers ───────────────────────────────────────────────────────────────────

test("routing: unknown paths → 404 JSON (before auth); prototype keys are not routes", async () => {
  const t = await setup();
  for (const p of ["/api/review/nope", "/api/review/me/", "/api/review/", "/api/review/constructor",
    "/api/review/__proto__", "/api/review/toString", "/api/other", "/api", "/api/"]) {
    const r = await t.call("GET", p, { token: null });
    assert.equal(r.status, 404, p);
    assert.deepEqual(r.json, { error: "not_found", msg: "Nahi mila" });
    assertApiHeaders(r);
  }
});

test("methods: GET action / POST me / OPTIONS / HEAD → 405 (with Allow), before auth", async () => {
  const t = await setup();
  const cases = [["GET", "action", "POST"], ["GET", "decide", "POST"], ["POST", "me", "GET"], ["PUT", "day", "GET"],
    ["OPTIONS", "action", "POST"], ["OPTIONS", "me", "GET"], ["HEAD", "me", "GET"], ["DELETE", "calendar", "GET"]];
  for (const [m, p, allow] of cases) {
    const r = await t.call(m, "/api/review/" + p, { token: null });
    assert.equal(r.status, 405, `${m} ${p}`);
    assert.equal(r.headers.get("allow"), allow);
    if (m !== "HEAD") assert.deepEqual(r.json, { error: "method_not_allowed", msg: "Galat method" });
  }
});

test("non-API paths go to the static site (ASSETS) untouched; without ASSETS → 404", async () => {
  const t = await setup();
  const r = await t.call("GET", "/index.html", { token: null });
  assert.equal(r.status, 200);
  assert.match(r.text, /<title>dash<\/title>/);
  assert.equal(r.headers.get("cache-control"), null, "assets response is not rewritten");
  delete t.env.ASSETS;
  assert.equal((await t.call("GET", "/index.html", { token: null })).status, 404);
});

// ── CSRF / body rules ───────────────────────────────────────────────────────────────────────────

test("CSRF: missing / foreign / null / other-port Origin → 403 forbidden", async () => {
  const t = await setup();
  for (const origin of [null, "https://evil.example.test", "null", "http://localhost:8080", "https://localhost"]) {
    const r = await t.act({ act: "ok", app: K.a }, { origin });
    assert.equal(r.status, 403, String(origin));
    assert.deepEqual(r.json, { error: "forbidden", msg: "Ye kaam allowed nahi" });
  }
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM sqlite_master WHERE name = 'rv_state'")[0].n, 0, "nothing touched D1");
});

test("POST media type: text/plain / form / missing → 415; application/json; charset=utf-8 → ok", async () => {
  const t = await setup();
  for (const ct of ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", null, "application/jsonx"]) {
    const r = await t.act({ act: "ok", app: K.a }, { ct });
    assert.equal(r.status, 415, String(ct));
    assert.deepEqual(r.json, { error: "unsupported_media_type", msg: "Galat format" });
  }
  assert.equal((await t.act({ act: "ok", app: K.a }, { ct: "Application/JSON; charset=utf-8" })).status, 200);
});

test("body: 9 KiB → 413; not JSON / array / null / bad UTF-8 → 400 body", async () => {
  const t = await setup();
  const big = await t.act({ act: "note", app: K.a, note: "x".repeat(9 * 1024) });
  assert.equal(big.status, 413);
  assert.deepEqual(big.json, { error: "payload_too_large", msg: "Note bahut lamba hai" });
  for (const raw of ["{not json", "[1,2]", "null", "42", "\"s\"", new Uint8Array([0x7b, 0xff, 0x7d])]) {
    const r = await t.post("action", raw, { raw: true });
    assert.equal(r.status, 400, String(raw));
    assert.deepEqual(r.json, { error: "bad_request", msg: "Galat request (body)", field: "body" });
  }
});

test("auth runs before the CSRF / body checks (no token + foreign Origin → 401)", async () => {
  const t = await setup();
  const r = await t.act({ act: "ok", app: K.a }, { token: null, origin: "https://evil.example.test", ct: "text/plain" });
  assert.equal(r.status, 401);
});

// ── validation ──────────────────────────────────────────────────────────────────────────────────

test("validation: d / act / app / feature / days / note / apps / flag_id → 400 with the field", async () => {
  const t = await setup();
  const cases = [
    [{ act: "ok", app: K.a, d: "2026-02-30" }, "d"],
    [{ act: "ok", app: K.a, d: "2026-10-2" }, "d"],
    [{ act: "ok", app: K.a, d: 20261002 }, "d"],
    [{ act: "OK", app: K.a }, "act"],
    [{ act: "decide", app: K.a }, "act"],
    [{ app: K.a }, "act"],
    [{ act: "ok", app: "A1A1A1A1A1A1" }, "app"],
    [{ act: "ok", app: "a1a1a1a1a1a" }, "app"],
    [{ act: "ok", app: K.e }, "app"],                   // valid key but not in the open day's snapshot
    [{ act: "ok" }, "app"],
    [{ act: "flag", app: K.a, feature: "revenue" }, "feature"],
    [{ act: "flag", app: K.a, feature: 3 }, "feature"],
    [{ act: "snooze", app: K.a, days: 7 }, "feature"],
    [{ act: "unsnooze", app: K.a, feature: null }, "feature"],
    [{ act: "snooze", app: K.a, feature: "ads", days: 5 }, "days"],
    [{ act: "snooze", app: K.a, feature: "ads", days: "7" }, "days"],
    [{ act: "note", app: K.a }, "note"],
    [{ act: "note", app: K.a, note: "   \r\n\t " }, "note"],
    [{ act: "note", app: K.a, note: 5 }, "note"],
    [{ act: "note", app: K.a, note: "x".repeat(601) }, "note"],
    [{ act: "flag", app: K.a, note: ["x"] }, "note"],
    [{ act: "bulk_ok" }, "apps"],
    [{ act: "bulk_ok", apps: [] }, "apps"],
    [{ act: "bulk_ok", apps: [K.a, K.a] }, "apps"],
    [{ act: "bulk_ok", apps: [K.a, K.e] }, "apps"],
    [{ act: "bulk_ok", apps: K.a }, "apps"],
    [{ act: "bulk_ok", apps: Array.from({ length: 61 }, (_, i) => i.toString(16).padStart(12, "0")) }, "apps"],
    [{ act: "unflag", flag_id: "1" }, "flag_id"],
    [{ act: "unflag", flag_id: 0 }, "flag_id"],
    [{ act: "unflag", flag_id: 1.5 }, "flag_id"],
  ];
  for (const [body, field] of cases) {
    const r = await t.act(body);
    assert.equal(r.status, 400, JSON.stringify(body).slice(0, 80));
    assert.equal(r.json.field, field, JSON.stringify(body).slice(0, 80));
    assert.equal(r.json.msg, `Galat request (${field})`);
  }
  assert.equal(actions(t).length, 0, "no rejected request wrote anything");
});

test("note text is NFC-normalised, \\r and control/bidi characters dropped, trimmed; 600 emoji fit", async () => {
  const t = await setup();
  const r = await t.act({ act: "note", app: K.a, note: "  Cafe\u0301\r\nline2\u0007\u202E\t!  " });
  assert.equal(r.status, 200);
  assert.equal(r.json.notes[0].text, "Café\nline2\t!");
  const emoji = await t.act({ act: "note", app: K.b, note: "📝".repeat(600) });
  assert.equal(emoji.status, 200);
  assert.equal([...emoji.json.notes[0].text].length, 600);
});

// ── the open day / index ────────────────────────────────────────────────────────────────────────

test("no index (review not live) → every action POST 409 review_not_started; GET day / calendar empty; me open_day null", async () => {
  for (const index of [null, "{not json", { v: 2 }, makeIndex(D1, { open_day: null, days: [] })]) {
    const t = await setup({ index });
    const r = await t.act({ act: "ok", app: K.a });
    assert.equal(r.status, 409, JSON.stringify(index));
    assert.deepEqual(r.json, { error: "review_not_started", msg: "Review abhi shuru nahi hua" });
    const d = await t.get(`day?d=${D1}`);
    assert.equal(d.status, 200);
    assert.deepEqual(d.json, { d: D1, open_day: null, writable: false, rev: 0, states: {}, notes: [], flags: [], snoozes: [], prev: null, log: [] });
    assert.deepEqual((await t.get(`calendar?from=${D0}&to=${D2}`)).json, { days: {} });
    const me = (await t.get("me")).json;
    assert.equal(me.open_day, null);
  }
});

test("index is cached per isolate (60 s): repeated requests fetch it once", async () => {
  const t = await setup();
  await t.get("me");
  await t.act({ act: "ok", app: K.a });
  await t.get(`day?d=${D1}`);
  assert.equal(t.assets.calls.filter((p) => p === "/review/index.json").length, 1);
});

test("day_closed: non-admin writes to an older day → 403; admin ok/note/undo/bulk_ok there are logged as admin_fix", async () => {
  const t = await setup();
  for (const act of ["ok", "kal", "note", "undo", "flag"]) {
    const r = await t.act({ d: D0, act, app: K.a, note: "n" });
    assert.equal(r.status, 403, act);
    assert.deepEqual(r.json, { error: "day_closed", msg: "Ye din band ho chuka — sirf admin sudhaar kar sakta hai" });
  }
  const own = { token: t.tokens.owner };
  const ok = await t.act({ d: D0, act: "ok", app: K.e }, own);   // K.e exists only in D0's snapshot (read from its doc)
  assert.equal(ok.status, 200);
  assert.equal(ok.json.d, D0);
  assert.equal(ok.json.state.st, "ok");
  assert.equal((await t.act({ d: D0, act: "note", app: K.b, note: "missed day fixed" }, own)).status, 200);
  const bulk = await t.act({ d: D0, act: "bulk_ok", apps: [K.a, K.b, K.c] }, own);
  assert.deepEqual(bulk.json.changed, [K.a, K.c]);
  assert.equal((await t.act({ d: D0, act: "undo", app: K.e }, own)).status, 200);
  const log = actions(t);
  assert.ok(log.length >= 5);
  for (const row of log) {
    assert.equal(row.day, D0);
    assert.equal(JSON.parse(row.extra).admin_fix, 1);
  }
  assert.equal(JSON.parse(log.find((x) => x.act === "bulk_ok").extra).bulk, 1);
  // …but not the open-day-only acts, and not days outside the snapshot list / in the future
  for (const body of [{ d: D0, act: "kal", app: K.a }, { d: D0, act: "flag", app: K.a }, { d: D0, act: "snooze", app: K.a, feature: "ads", days: 7 },
    { d: D0, act: "unsnooze", app: K.a, feature: "ads" }, { d: D0, act: "unflag", app: K.a }, { d: "2026-09-01", act: "ok", app: K.a },
    { d: D2, act: "ok", app: K.a }]) {
    const r = await t.act(body, own);
    assert.equal(r.status, 403, JSON.stringify(body));
    assert.equal(r.json.error, "day_closed");
  }
  // app validity follows THAT day's snapshot
  assert.equal((await t.act({ d: D0, act: "ok", app: K.d }, own)).json.field, "app");
  assert.equal((await t.act({ act: "ok", app: K.e }, own)).json.field, "app");
});

test("older-day doc served as plain JSON (not gzip) is read too; an unreadable older doc → 500", async () => {
  const t = await setup({ gzip: false });
  assert.equal((await t.act({ d: D0, act: "ok", app: K.e }, { token: t.tokens.owner })).status, 200);
  const u = await setup();
  delete u.assets.files[`/review/days/${D0}.json.gz`];
  const r = await u.act({ d: D0, act: "ok", app: K.e }, { token: u.tokens.owner });
  assert.equal(r.status, 500);
  assert.equal(r.json.error, "server_error");
});

// ── acts ────────────────────────────────────────────────────────────────────────────────────────

test("ok / kal: upsert, last write wins, who/at from the verified email, rev increases", async () => {
  const t = await setup();
  const a = await t.act({ act: "ok", app: K.a });
  assert.equal(a.status, 200);
  assertApiHeaders(a);
  assert.equal(a.json.ok, true);
  assert.equal(a.json.app, K.a);
  assert.equal(a.json.d, D1);
  assert.deepEqual(Object.keys(a.json.state).sort(), ["at", "snz", "st", "who"]);
  assert.deepEqual([a.json.state.st, a.json.state.who], ["ok", TEAMMATE]);
  const b = await t.act({ act: "kal", app: K.a }, { token: t.tokens.team2 });
  assert.deepEqual([b.json.state.st, b.json.state.who], ["kal", TEAM2]);
  assert.ok(b.json.rev > a.json.rev);
  const c = await t.act({ act: "ok", app: K.a }, { token: t.tokens.owner });
  assert.deepEqual([c.json.state.st, c.json.state.who], ["ok", OWNER]);
  assert.deepEqual(actions(t).map((x) => [x.act, x.who, x.app, x.day]),
    [["ok", TEAMMATE, K.a, D1], ["kal", TEAM2, K.a, D1], ["ok", OWNER, K.a, D1]]);
});

test("note: stored with app_label; no state → state ok; an existing kal/flag state is kept", async () => {
  const t = await setup();
  const n = await t.act({ act: "note", app: K.a, note: "developer ko bata diya" });
  assert.equal(n.status, 200);
  assert.equal(n.json.state.st, "ok");
  assert.deepEqual(n.json.notes.map((x) => [x.text, x.who, x.app]), [["developer ko bata diya", TEAMMATE, K.a]]);
  assert.equal(t.db.q("SELECT app_label FROM rv_notes")[0].app_label, LABEL(K.a));
  const logRow = actions(t)[0];
  assert.deepEqual([logRow.act, logRow.note, logRow.ref], ["note", "developer ko bata diya", n.json.notes[0].id]);
  await t.act({ act: "kal", app: K.b });
  assert.equal((await t.act({ act: "note", app: K.b, note: "kal dekhenge" })).json.state.st, "kal");
  await t.act({ act: "flag", app: K.c });
  assert.equal((await t.act({ act: "note", app: K.c, note: "admin dekho" })).json.state.st, "flag");
});

test("flag: per feature and whole app; one open flag per app+feature (409 already_flagged + flag_id)", async () => {
  const t = await setup();
  const f1 = await t.act({ act: "flag", app: K.a, feature: "kamai", note: "eCPM 40% gira" });
  assert.equal(f1.status, 200);
  assert.equal(f1.json.state, null, "a feature flag does not change the card state");
  const flag = f1.json.flags[0];
  assert.equal(flag.feature, "kamai");
  assert.equal(flag.status, "open");
  assert.equal(flag.day, D1);
  assert.equal(flag.raised_by, TEAMMATE);
  assert.equal(flag.app_label, LABEL(K.a));
  assert.equal(flag.note, "eCPM 40% gira");
  assert.deepEqual(Object.keys(flag).sort(), ["app", "app_label", "day", "dec_at", "dec_by", "dec_day", "dec_note", "decision",
    "done_at", "done_by", "done_day", "done_note", "feature", "id", "note", "raised_at", "raised_by", "status", "wd_at", "wd_by"]);
  const again = await t.act({ act: "flag", app: K.a, feature: "kamai" }, { token: t.tokens.team2 });
  assert.equal(again.status, 409);
  assert.deepEqual(again.json, { error: "conflict", msg: "Ye pehle se 🚩 Re-review me hai", why: "already_flagged", flag_id: flag.id });
  assert.equal((await t.act({ act: "flag", app: K.a, feature: "uninstall" })).status, 200, "other feature is its own item");
  const whole = await t.act({ act: "flag", app: K.a });
  assert.equal(whole.status, 200);
  assert.equal(whole.json.state.st, "flag");
  assert.equal(whole.json.flags.length, 3);
  assert.equal(whole.json.flags.find((f) => f.feature === null).note, "");
  assert.equal((await t.act({ act: "flag", app: K.a, feature: null })).json.why, "already_flagged");
  const log = actions(t);
  assert.deepEqual(log.map((x) => [x.act, x.feature, x.ref]), [["flag", "kamai", 1], ["flag", "uninstall", 2], ["flag", null, 3]]);
});

test("ok / kal on a card in 🚩 Re-review → 409 flagged (state and log unchanged)", async () => {
  const t = await setup();
  await t.act({ act: "flag", app: K.a });
  const before = actions(t).length;
  for (const act of ["ok", "kal"]) {
    const r = await t.act({ act, app: K.a });
    assert.equal(r.status, 409);
    assert.equal(r.json.why, "flagged");
    assert.equal(r.json.msg, "Ye card 🚩 Re-review me hai — admin ke faisle tak aise hi rahega");
  }
  assert.equal(actions(t).length, before);
  assert.equal((await t.day()).states[K.a].st, "flag");
});

test("unflag today's flag (by id or by app+feature); whole-app unflag clears the flag state; older flags → 403 not_raised_today", async () => {
  const t = await setup({ index: makeIndex(D0) });
  const old = await t.act({ d: D0, act: "flag", app: K.a, feature: "ads" });
  assert.equal(old.status, 200);
  t.setIndex(makeIndex(D1));
  const f = (await t.act({ act: "flag", app: K.a, feature: "kamai" })).json.flags.find((x) => x.feature === "kamai");
  await t.act({ act: "ok", app: K.b });
  await t.act({ act: "flag", app: K.b });

  const u1 = await t.act({ act: "unflag", flag_id: f.id });
  assert.equal(u1.status, 200);
  assert.equal(u1.json.app, K.a);
  const w = u1.json.flags.find((x) => x.id === f.id);
  assert.deepEqual([w.status, w.wd_by], ["withdrawn", TEAMMATE]);
  assert.equal((await t.act({ act: "unflag", flag_id: f.id })).json.why, "not_open");
  assert.equal((await t.act({ act: "unflag", app: K.a, feature: "kamai" })).status, 404);

  const u2 = await t.act({ act: "unflag", app: K.b, feature: null });
  assert.equal(u2.status, 200);
  assert.equal(u2.json.state, null, "whole-app unflag removes the 🚩 state (card back to ⏳ Baaki)");

  const oldFlag = (await t.day()).flags.find((x) => x.day === D0);
  const u3 = await t.act({ act: "unflag", flag_id: oldFlag.id });
  assert.equal(u3.status, 403);
  assert.deepEqual(u3.json, { error: "forbidden", msg: "Ye kaam allowed nahi", why: "not_raised_today" });
  assert.equal((await t.act({ act: "unflag", app: K.a, feature: "ads" })).json.why, "not_raised_today");
  assert.equal((await t.act({ act: "unflag", flag_id: 999 })).status, 404);
  assert.equal((await t.act({ act: "unflag", flag_id: oldFlag.id, app: K.b })).json.field, "flag_id");
  const bWhole = u2.json.flags.find((x) => x.feature === null);
  assert.equal(bWhole.status, "withdrawn");
  assert.deepEqual(actions(t).filter((x) => x.act === "unflag").map((x) => x.ref), [f.id, bWhole.id]);
});

test("undo: removes the state, soft-deletes that day's notes, withdraws that day's open flags; decided flags + snoozes stay", async () => {
  const t = await setup();
  await t.act({ act: "note", app: K.a, note: "pehla note" });
  const fk = (await t.act({ act: "flag", app: K.a, feature: "kamai" })).json.flags[0];
  const fu = (await t.act({ act: "flag", app: K.a, feature: "uninstall" })).json.flags.find((x) => x.feature === "uninstall");
  await t.decide({ flag_id: fu.id, decision: "kaam", note: "dev ko bolo" });
  await t.act({ act: "flag", app: K.a });
  await t.act({ act: "snooze", app: K.a, feature: "ads", days: 7 });
  await t.act({ act: "note", app: K.b, note: "doosra app" });

  const u = await t.act({ act: "undo", app: K.a }, { token: t.tokens.team2 });
  assert.equal(u.status, 200);
  assert.equal(u.json.state, null);
  assert.deepEqual(u.json.notes, []);
  const byId = Object.fromEntries(u.json.flags.map((x) => [x.id, x]));
  assert.equal(byId[fk.id].status, "withdrawn");
  assert.equal(byId[fk.id].wd_by, TEAM2);
  assert.equal(byId[fu.id].status, "kaam", "decided flag stays");
  assert.equal(u.json.flags.find((x) => x.feature === null).status, "withdrawn");
  assert.equal(u.json.snoozes.length, 1, "snooze stays");
  const notes = t.db.q("SELECT app, deleted_by FROM rv_notes ORDER BY id");
  assert.deepEqual(notes, [{ app: K.a, deleted_by: TEAM2 }, { app: K.b, deleted_by: null }]);
  assert.equal((await t.day()).notes.length, 1);
  // after undo the card can be flagged again (no stuck unique index)
  assert.equal((await t.act({ act: "flag", app: K.a, feature: "kamai" })).status, 200);
});

test("snooze: until = open day + 7/14, replaces the live one; unsnooze clears; state.snz records snoozes at that moment", async () => {
  const t = await setup();
  const s1 = await t.act({ act: "snooze", app: K.a, feature: "ads", days: 7, note: "agle update me fix" });
  assert.equal(s1.status, 200);
  assert.deepEqual(s1.json.snoozes.map((x) => [x.feature, x.day, x.until, x.days, x.note, x.who, x.app_label]),
    [["ads", D1, "2026-10-09", 7, "agle update me fix", TEAMMATE, LABEL(K.a)]]);
  const s2 = await t.act({ act: "snooze", app: K.a, feature: "ads", days: 14 });
  assert.deepEqual(s2.json.snoozes.map((x) => [x.until, x.days]), [["2026-10-16", 14]]);
  await t.act({ act: "snooze", app: K.a, feature: "kamai", days: 7 });
  const ok = await t.act({ act: "ok", app: K.a });
  assert.deepEqual(ok.json.state.snz, ["kamai", "ads"], "FEATS order");
  const un = await t.act({ act: "unsnooze", app: K.a, feature: "ads" });
  assert.equal(un.status, 200);
  assert.deepEqual(un.json.snoozes.map((x) => x.feature), ["kamai"]);
  assert.equal((await t.act({ act: "unsnooze", app: K.a, feature: "ads" })).status, 404);
  assert.equal((await t.act({ act: "unsnooze", app: K.b, feature: "ads" })).json.error, "not_found");
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM rv_snoozes WHERE cleared_at IS NULL")[0].n, 1);
  assert.deepEqual(actions(t).map((x) => x.act), ["snooze", "snooze", "snooze", "ok", "unsnooze"]);
  assert.deepEqual(JSON.parse(actions(t)[1].extra), { days: 14, until: "2026-10-16" });
});

test("snooze made / cleared while an older day is still open is dated by the REVIEW day, not the clock", async () => {
  // open_day D1 while the clock is already later (e.g. before 09:00 IST the next day): the snooze belongs to D1.
  const t = await setup();
  await t.act({ act: "snooze", app: K.a, feature: "ads", days: 7 });
  t.db.sqlite.exec("UPDATE rv_snoozes SET at = '2026-10-02T20:00:00.000Z'");   // = 03 Oct 01:30 IST
  assert.equal((await t.day(D1)).snoozes.length, 1, "active on its review day D1");
  await t.act({ act: "unsnooze", app: K.a, feature: "ads" });
  t.db.sqlite.exec("UPDATE rv_snoozes SET cleared_at = '2026-10-02T20:05:00.000Z'; UPDATE rv_actions SET at = '2026-10-02T20:05:00.000Z' WHERE act = 'unsnooze'");
  assert.equal((await t.day(D1)).snoozes.length, 0, "cleared on review day D1 → not active on D1");
  assert.equal((await t.day(D0)).snoozes.length, 0, "never active before it was made");
});

test("older days: a snooze counts as cleared from the REVIEW day of its clear (not the IST clock date)", async () => {
  // Pin every timestamp to realistic IST moments (the test machine's clock is not a review day).
  const t = await setup({ index: makeIndex(D0) });
  const own = { token: t.tokens.owner };
  await t.act({ d: D0, act: "snooze", app: K.a, feature: "ads", days: 7 });
  await t.act({ d: D0, act: "snooze", app: K.b, feature: "ads", days: 7 });
  await t.act({ d: D0, act: "snooze", app: K.c, feature: "kamai", days: 14 });
  t.db.sqlite.exec("UPDATE rv_snoozes SET at = '2026-10-01T06:00:00.000Z'; UPDATE rv_actions SET at = '2026-10-01T06:00:00.000Z'");
  // K.a: cleared at 01:30 IST on 02 Oct while 01 Oct (D0) was still the open day → cleared ON review day D0
  await t.act({ d: D0, act: "unsnooze", app: K.a, feature: "ads" });
  t.db.sqlite.exec("UPDATE rv_snoozes SET cleared_at = '2026-10-01T20:00:00.000Z' WHERE app = '" + K.a + "';" +
    "UPDATE rv_actions SET at = '2026-10-01T20:00:00.000Z' WHERE act = 'unsnooze'");
  t.setIndex(makeIndex(D1));
  // K.b: cleared on review day D1 (11:30 IST) → still active on D0, not on D1
  await t.act({ act: "unsnooze", app: K.b, feature: "ads" });
  t.db.sqlite.exec("UPDATE rv_snoozes SET cleared_at = '2026-10-02T06:00:00.000Z' WHERE app = '" + K.b + "';" +
    "UPDATE rv_actions SET at = '2026-10-02T06:00:00.000Z' WHERE act = 'unsnooze' AND app = '" + K.b + "'");

  const snzOf = (s) => s.snoozes.map((x) => [x.app, x.feature]).sort();
  assert.deepEqual(snzOf(await t.day(D0)), [[K.b, "ads"], [K.c, "kamai"]].sort());
  assert.deepEqual(snzOf(await t.day(D1)), [[K.c, "kamai"]]);
  // an admin correction on D0 records the snoozes active ON D0
  const fix = await t.act({ d: D0, act: "ok", app: K.b }, own);
  assert.deepEqual(fix.json.state.snz, ["ads"]);
  assert.deepEqual(fix.json.snoozes.map((x) => x.feature), ["ads"]);
  assert.deepEqual((await t.act({ d: D0, act: "ok", app: K.a }, own)).json.state.snz, []);
  // fallback when no clearing action row exists: the IST date of cleared_at decides
  t.db.sqlite.exec("INSERT INTO rv_snoozes (app, feature, day, until, days, who, at, cleared_by, cleared_at) VALUES " +
    `('${K.e}', 'setup', '${D0}', '2026-10-08', 7, 'x@example.test', '2026-10-01T06:00:00.000Z', 'x@example.test', '2026-10-02T06:00:00.000Z')`);
  assert.ok(snzOf(await t.day(D0)).some(([a]) => a === K.e), "cleared on IST 02 Oct → active on 01 Oct");
  assert.equal(snzOf(await t.day(D1)).some(([a]) => a === K.e), false);
});

test("bulk_ok records, per app, the snoozes active at that moment (FEATS order)", async () => {
  const t = await setup();
  await t.act({ act: "snooze", app: K.c, feature: "ads", days: 7 });
  await t.act({ act: "snooze", app: K.c, feature: "kamai", days: 14 });
  await t.act({ act: "snooze", app: K.a, feature: "setup", days: 7 });
  await t.act({ act: "unsnooze", app: K.a, feature: "setup" });
  const r = await t.act({ act: "bulk_ok", apps: [K.d, K.c, K.a] });
  assert.equal(r.status, 200);
  assert.deepEqual(r.json.changed, [K.d, K.c, K.a], "request order");
  assert.deepEqual(r.json.states[K.c].snz, ["kamai", "ads"]);
  assert.deepEqual(r.json.states[K.d].snz, []);
  assert.deepEqual(r.json.states[K.a].snz, []);
  assert.deepEqual(actions(t).filter((x) => x.act === "bulk_ok").map((x) => x.app), [K.d, K.c, K.a], "log in request order");
});

test("bulk_ok: only apps without a state become ok (one log row each, extra bulk); reviewed / kal / flag apps untouched", async () => {
  const t = await setup();
  await t.act({ act: "kal", app: K.a });
  await t.act({ act: "flag", app: K.b });
  const r = await t.act({ act: "bulk_ok", apps: [K.a, K.b, K.c, K.d] }, { token: t.tokens.team2 });
  assert.equal(r.status, 200);
  assert.deepEqual(r.json.changed, [K.c, K.d]);
  assert.deepEqual(Object.fromEntries(Object.entries(r.json.states).map(([k, v]) => [k, [v.st, v.who]])), {
    [K.a]: ["kal", TEAMMATE], [K.b]: ["flag", TEAMMATE], [K.c]: ["ok", TEAM2], [K.d]: ["ok", TEAM2],
  });
  const bulkRows = actions(t).filter((x) => x.act === "bulk_ok");
  assert.deepEqual(bulkRows.map((x) => [x.app, JSON.parse(x.extra).bulk]), [[K.c, 1], [K.d, 1]]);
  const again = await t.act({ act: "bulk_ok", apps: [K.c, K.d] });
  assert.deepEqual(again.json.changed, []);
  assert.equal(actions(t).filter((x) => x.act === "bulk_ok").length, 2, "nothing changed → nothing logged");
  assert.equal(again.json.rev, r.json.rev);
});

// ── decide (admin) ──────────────────────────────────────────────────────────────────────────────

test("decide: non-admin → 403 admin_only (even with a valid body)", async () => {
  const t = await setup();
  const f = (await t.act({ act: "flag", app: K.a })).json.flags[0];
  const r = await t.decide({ flag_id: f.id, decision: "theek" }, { token: t.tokens.team });
  assert.equal(r.status, 403);
  assert.deepEqual(r.json, { error: "admin_only", msg: "Sirf admin faisla kar sakta hai" });
  assert.equal((await t.decide({}, { token: t.tokens.team })).status, 403);
});

test("decide: theek / band close, kaam → kaam (note required), done closes a kaam flag; wrong transitions → 409", async () => {
  const t = await setup();
  const mk = async (feature) => (await t.act({ act: "flag", app: K.a, feature })).json.flags.find((x) => x.feature === feature).id;
  const [fTheek, fBand, fKaam] = [await mk("kamai"), await mk("ads"), await mk("uninstall")];

  for (const [body, field] of [[{ flag_id: fKaam, decision: "kaam" }, "note"], [{ flag_id: fKaam, decision: "kaam", note: "  " }, "note"],
    [{ flag_id: fBand, decision: "band" }, "note"], [{ flag_id: fBand, decision: "close" }, "decision"], [{ flag_id: "1", decision: "theek" }, "flag_id"],
    [{ flag_id: fBand, decision: "band", note: "x".repeat(601) }, "note"]]) {
    const r = await t.decide(body);
    assert.equal(r.status, 400, JSON.stringify(body));
    assert.equal(r.json.field, field);
  }
  assert.equal((await t.decide({ flag_id: 999, decision: "theek" })).status, 404);

  const th = await t.decide({ flag_id: fTheek, decision: "theek" });
  assert.equal(th.status, 200);
  assert.deepEqual([th.json.flag.status, th.json.flag.decision, th.json.flag.dec_by, th.json.flag.dec_note], ["closed", "theek", OWNER, null]);
  const bd = await t.decide({ flag_id: fBand, decision: "band", note: "ad unit band karo" });
  assert.deepEqual([bd.json.flag.status, bd.json.flag.decision, bd.json.flag.dec_note], ["closed", "band", "ad unit band karo"]);
  const km = await t.decide({ flag_id: fKaam, decision: "kaam", note: "developer ko do" });
  assert.deepEqual([km.json.flag.status, km.json.flag.decision], ["kaam", "kaam"]);
  assert.ok(km.json.rev > bd.json.rev);

  assert.equal((await t.decide({ flag_id: fKaam, decision: "theek" })).json.why, "already_decided");
  assert.equal((await t.decide({ flag_id: fTheek, decision: "done" })).json.why, "not_kaam");
  assert.equal((await t.decide({ flag_id: fTheek, decision: "band", note: "x" })).json.why, "already_decided");
  const dn = await t.decide({ flag_id: fKaam, decision: "done", note: "fix live" });
  assert.deepEqual([dn.json.flag.status, dn.json.flag.decision, dn.json.flag.done_note, dn.json.flag.done_by], ["closed", "kaam", "fix live", OWNER]);
  assert.equal((await t.decide({ flag_id: fKaam, decision: "done" })).json.why, "not_kaam");

  const wd = await mk("health");
  await t.act({ act: "unflag", flag_id: wd });
  const r = await t.decide({ flag_id: wd, decision: "theek" });
  assert.equal(r.status, 409);
  assert.deepEqual(r.json, { error: "conflict", msg: "Ye 🚩 ab khula nahi hai", why: "not_open" });

  const dec = actions(t).filter((x) => x.act === "decide");
  assert.deepEqual(dec.map((x) => [x.ref, JSON.parse(x.extra).decision, x.day, x.who]),
    [[fTheek, "theek", D1, OWNER], [fBand, "band", D1, OWNER], [fKaam, "kaam", D1, OWNER], [fKaam, "done", D1, OWNER]]);
  // re-flag the same feature after a decision → a NEW flag
  const again = await t.act({ act: "flag", app: K.a, feature: "kamai" });
  assert.equal(again.status, 200);
  assert.equal(again.json.flags.filter((x) => x.feature === "kamai").length, 2);
});

test("decide works without a review index (log day = the flag's own day)", async () => {
  const t = await setup();
  const f = (await t.act({ act: "flag", app: K.a, feature: "kamai" })).json.flags[0];
  t.setIndex(null);
  const r = await t.decide({ flag_id: f.id, decision: "theek" });
  assert.equal(r.status, 200);
  assert.equal(actions(t).at(-1).day, D1);
});

// ── GET day / calendar ──────────────────────────────────────────────────────────────────────────

test("GET day: prev.kal, carried open / kaam flags, decided-later flags, log newest first, rev, writable", async () => {
  const t = await setup({ index: makeIndex(D0) });
  await t.act({ d: D0, act: "kal", app: K.a });
  await t.act({ d: D0, act: "ok", app: K.b });
  const fOpen = (await t.act({ d: D0, act: "flag", app: K.a, feature: "kamai", note: "dekho" })).json.flags[0];
  const fKaam = (await t.act({ d: D0, act: "flag", app: K.b, feature: "ads" })).json.flags[0];
  const fTheek = (await t.act({ d: D0, act: "flag", app: K.c })).json.flags[0];
  await t.decide({ d: D0, flag_id: fKaam.id, decision: "kaam", note: "campaign dekho" });
  const fWd = (await t.act({ d: D0, act: "flag", app: K.c, feature: "health" })).json.flags.find((x) => x.feature === "health");
  await t.act({ d: D0, act: "unflag", flag_id: fWd.id });

  t.setIndex(makeIndex(D1));
  // pin the decision / withdrawal timestamps to known review days (the test clock is not a review day)
  t.db.sqlite.exec("UPDATE rv_flags SET status = 'closed', decision = 'theek', dec_by = 'owner@example.test', dec_at = '2026-10-02T05:00:00.000Z' WHERE id = " + fTheek.id);
  t.db.sqlite.exec("UPDATE rv_flags SET wd_at = '2026-10-01T05:00:00.000Z' WHERE id = " + fWd.id);

  const day1 = await t.get(`day?d=${D1}`);
  assert.equal(day1.status, 200);
  assertApiHeaders(day1);
  const s = day1.json;
  assert.deepEqual(Object.keys(s).sort(), ["d", "flags", "log", "notes", "open_day", "prev", "rev", "snoozes", "states", "writable"]);
  assert.equal(s.open_day, D1);
  assert.equal(s.writable, true);
  assert.deepEqual(s.prev, { d: D0, kal: [K.a] });
  assert.deepEqual(s.flags.map((x) => [x.id, x.status]).sort(), [[fOpen.id, "open"], [fKaam.id, "kaam"], [fTheek.id, "closed"]].sort(),
    "open + kaam carry over; closed on D1 is still listed on D1; withdrawn on D0 is not");
  assert.deepEqual(s.states, {});
  assert.deepEqual(s.log, [], "D1 has no actions yet (decide on D0's open day was logged on D0)");

  const d0 = (await t.get(`day?d=${D0}`)).json;
  assert.equal(d0.writable, false, "team cannot write D0");
  assert.equal((await t.get(`day?d=${D0}`, { token: t.tokens.owner })).json.writable, true, "admin may correct D0");
  assert.equal((await t.get(`day?d=2026-09-01`, { token: t.tokens.owner })).json.writable, false, "not a snapshot day");
  assert.ok(d0.log.length >= 7);
  const ids = d0.log.map((x) => x.id);
  assert.deepEqual(ids, [...ids].sort((a, b) => b - a), "newest first");
  assert.deepEqual(Object.keys(d0.log[0]).sort(), ["act", "app", "at", "extra", "feature", "id", "note", "ref", "who"]);
  assert.equal(d0.rev, s.rev);
  assert.equal(d0.states[K.a].st, "kal");
  assert.equal(d0.states[K.a].who, TEAMMATE);
  assert.match(d0.states[K.a].at, /Z$/);

  const r0 = s.rev;
  await t.act({ act: "ok", app: K.c });
  const s2 = (await t.get(`day?d=${D1}`)).json;
  assert.ok(s2.rev > r0);
  assert.deepEqual(s2.log.map((x) => [x.act, x.app, x.who]), [["ok", K.c, TEAMMATE]]);

  // a later OPEN day: open + kaam still carried, and the theek-closed flag stays listed (admin view "Band", last 14 days)
  t.setIndex(makeIndex(D2));
  const s3 = (await t.get(`day?d=${D2}`)).json;
  assert.deepEqual(s3.flags.map((x) => x.id).sort(), [fOpen.id, fKaam.id, fTheek.id].sort());
  // …but History of an older day d only lists what was closed on or after d (the flag closed on D1 is not on D0 + …)
  const past = (await t.get(`day?d=${D1}`, { token: t.tokens.owner })).json;
  assert.ok(past.flags.some((x) => x.id === fTheek.id), "closed on D1 → still listed on D1");
  assert.deepEqual(s3.prev, { d: D1, kal: [] });
  assert.equal((await t.get("day?d=2026-13-01")).json.field, "d");
  assert.equal((await t.get("day")).json.field, "d");
});

test("calendar: per-day counts (rev, kal, flag w/o withdrawn, notes w/o deleted, people); range validation", async () => {
  const t = await setup({ index: makeIndex(D0) });
  await t.act({ d: D0, act: "kal", app: K.a });
  await t.act({ d: D0, act: "ok", app: K.b }, { token: t.tokens.team2 });
  await t.act({ d: D0, act: "flag", app: K.c, feature: "ads" });
  const wd = (await t.act({ d: D0, act: "flag", app: K.c, feature: "kamai" })).json.flags.find((x) => x.feature === "kamai");
  await t.act({ d: D0, act: "unflag", flag_id: wd.id });
  await t.act({ d: D0, act: "note", app: K.e, note: "a" });
  await t.act({ d: D0, act: "note", app: K.b, note: "b" });
  t.setIndex(makeIndex(D1));
  await t.act({ act: "ok", app: K.a }, { token: t.tokens.owner });
  await t.act({ act: "undo", app: K.a }, { token: t.tokens.owner });

  const r = await t.get(`calendar?from=${D0}&to=${D2}`);
  assert.equal(r.status, 200);
  assert.deepEqual(r.json, { days: {
    [D0]: { rev: 3, kal: 1, flag: 1, notes: 2, people: 2 },
    [D1]: { rev: 0, kal: 0, flag: 0, notes: 0, people: 1 },
  } });
  assert.deepEqual((await t.get(`calendar?from=${D1}&to=${D1}`)).json.days[D0], undefined);
  for (const [q, field] of [[`from=${D1}&to=${D0}`, "to"], ["from=2025-01-01&to=2026-02-06", "to"], ["from=x&to=2026-01-01", "from"],
    [`from=${D0}`, "to"], ["to=2026-01-01", "from"]]) {
    const e = await t.get(`calendar?${q}`);
    assert.equal(e.status, 400, q);
    assert.equal(e.json.field, field, q);
  }
  assert.equal((await t.get("calendar?from=2025-01-01&to=2026-02-05")).status, 200, "400 days is allowed");
});

// ── robustness ──────────────────────────────────────────────────────────────────────────────────

test("concurrent clicks: last write wins, the log keeps every action; double flag → one 200 + one 409", async () => {
  const t = await setup();
  const [a, b] = await Promise.all([
    t.act({ act: "ok", app: K.a }, { token: t.tokens.team }),
    t.act({ act: "kal", app: K.a }, { token: t.tokens.team2 }),
  ]);
  assert.deepEqual([a.status, b.status], [200, 200]);
  const log = actions(t);
  assert.deepEqual(log.map((x) => x.act).sort(), ["kal", "ok"]);
  const last = log.at(-1);
  const st = (await t.day()).states[K.a];
  assert.deepEqual([st.st, st.who], [last.act, last.who], "final state = the last logged write");

  const flags = await Promise.all([1, 2, 3].map(() => t.act({ act: "flag", app: K.b, feature: "kamai" })));
  assert.deepEqual(flags.map((x) => x.status).sort(), [200, 409, 409]);
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM rv_flags WHERE app = ?", K.b)[0].n, 1);

  const [f, o] = await Promise.all([t.act({ act: "flag", app: K.c }), t.act({ act: "ok", app: K.c })]);
  assert.equal(f.status, 200);
  assert.ok([200, 409].includes(o.status));
  assert.equal((await t.day()).states[K.c].st, "flag", "a whole-app flag is never overwritten by ok");

  const bulk = await Promise.all([t.act({ act: "bulk_ok", apps: [K.d] }), t.act({ act: "bulk_ok", apps: [K.d] }, { token: t.tokens.team2 })]);
  assert.deepEqual(bulk.map((x) => x.json.changed.length).sort(), [0, 1]);
  assert.equal(actions(t).filter((x) => x.act === "bulk_ok").length, 1);
});

test("rv_actions is append-only: no UPDATE / DELETE statement ever targets it", async () => {
  const t = await setup();
  await t.act({ act: "note", app: K.a, note: "n" });
  await t.act({ act: "flag", app: K.a });
  await t.act({ act: "undo", app: K.a });
  const f = (await t.act({ act: "flag", app: K.b, feature: "ads" })).json.flags[0];
  await t.act({ act: "unflag", flag_id: f.id });
  await t.act({ act: "snooze", app: K.b, feature: "ads", days: 7 });
  await t.act({ act: "unsnooze", app: K.b, feature: "ads" });
  await t.act({ act: "bulk_ok", apps: [K.c] });
  const f2 = (await t.act({ act: "flag", app: K.d })).json.flags[0];
  await t.decide({ flag_id: f2.id, decision: "kaam", note: "k" });
  await t.decide({ flag_id: f2.id, decision: "done" });
  const bad = t.db.statements.filter((s) => /\b(UPDATE\s+rv_actions|DELETE\s+FROM\s+rv_actions|REPLACE\s+INTO\s+rv_actions)\b/i.test(s));
  assert.deepEqual(bad, []);
  assert.equal(actions(t).length, 11);
});

test("DB trouble: schema failure → 503 db_unavailable then retried; query failure → 500; missing binding → 500", async () => {
  const t = await setup();
  t.db.failNext = new Error("disk full");
  const r = await t.get("me");
  assert.equal(r.status, 503);
  assert.deepEqual(r.json, { error: "db_unavailable", msg: "Server me dikkat — thodi der baad try karo" });
  assert.equal((await t.get("me")).status, 200, "schema retried on the next request");
  t.db.failNext = new Error("boom");
  const e = await t.act({ act: "ok", app: K.a });
  assert.equal(e.status, 500);
  assert.equal(e.json.error, "server_error");
  delete t.env.REVIEW_DB;
  assert.equal((await t.get("me")).json.error, "misconfigured");
});

test("privacy: console output never contains emails, notes, app keys/labels or messages from errors", async (tt) => {
  const lines = [];
  for (const m of ["log", "info", "warn", "error", "debug"]) {
    tt.mock.method(console, m, (...args) => lines.push(args.map(String).join(" ")));
  }
  const t = await setup();
  const secretNote = "SECRET-NOTE revenue $123.45";
  await t.act({ act: "note", app: K.a, note: secretNote });
  await t.act({ act: "flag", app: K.a, feature: "kamai", note: secretNote });
  await t.act({ act: "ok", app: K.a });
  t.db.failNext = new Error(`leak ${TEAMMATE} ${secretNote} ${K.a}`);
  assert.equal((await t.act({ act: "note", app: K.b, note: secretNote })).status, 500);
  t.resetCaches();
  t.db.failNext = new Error(`leak ${OWNER}`);
  assert.equal((await t.get("me", { token: t.tokens.owner })).status, 503);
  await t.act({ act: "ok", app: K.a }, { origin: "https://evil.example.test" });
  await t.get("me", { token: "bad.token.here" });
  tt.mock.restoreAll();
  assert.ok(lines.length >= 2, "errors were logged (type only)");
  const joined = lines.join("\n");
  for (const s of [TEAMMATE, OWNER, "example.test", "SECRET", "123.45", K.a, K.b, "Demo", "leak", "@"]) {
    assert.equal(joined.includes(s), false, `console leaked ${s}`);
  }
});

test("no Access-Control-* header on any response seen in this file; every API response has the security headers", () => {
  assert.ok(SEEN.length > 100);
  for (const r of SEEN) {
    for (const [k] of r.headers) assert.equal(k.toLowerCase().startsWith("access-control-"), false, k);
    if (r.json && (r.json.error || r.json.ok || r.json.email || r.json.days || r.json.d)) {
      assert.equal(r.headers.get("x-content-type-options"), "nosniff");
      assert.equal(r.headers.get("cache-control"), "no-store");
    }
  }
});

test("error bodies use the fixed messages; ORIGIN helper sanity", async () => {
  const t = await setup();
  assert.equal(ORIGIN, "http://localhost");
  const r = await t.get("me", { token: null });
  assert.deepEqual(Object.keys(r.json).sort(), ["error", "msg"]);
  assert.deepEqual(siteFiles({ index: null })["/review/index.json"], undefined);
});
