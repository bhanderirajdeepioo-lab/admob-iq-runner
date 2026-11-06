// 📉 CPI level actions through the Worker (/api/levels, /api/levels/act): Access + admin + CSRF rules, every
// validator, the append-only write to config/cpi_levels.json on a fake GitHub contents API (a conflicting write is
// re-read and re-appended: a concurrent action is never lost), a broken file writes nothing, undo rules, `by` from the
// verified login (never the body), the lv_log audit row, the 30 s read cache, and that the GitHub token never shows up
// in a response or in the console. Every id, repo and email here is synthetic. node --test
import test from "node:test";
import assert from "node:assert/strict";
import { setup, OWNER } from "./harness.js";
import { todayIst, LV_MSG } from "../src/levels.js";

const REPO = "example-owner/example-config";
const TOKEN = "ghp_TEST" + "only" + Math.random().toString(36).slice(2) + "y".repeat(12);
const GH_ENV = { GITHUB_TOKEN: TOKEN, CONFIG_REPO: REPO };
const FILE = "config/cpi_levels.json";
const APP = "ca-app-pub-1001~11";
let SHA_N = 0;
const newSha = () => (++SHA_N).toString(16).padStart(40, "b");

const TODAY = todayIst(new Date().toISOString());
const back = (n) => new Date(Date.parse(TODAY + "T00:00:00Z") - n * 86400000).toISOString().slice(0, 10);
const ahead = (n) => new Date(Date.parse(TODAY + "T00:00:00Z") + n * 86400000).toISOString().slice(0, 10);
const b64 = (s) => Buffer.from(s, "utf8").toString("base64");
const unb64 = (s) => new TextDecoder().decode(Uint8Array.from(atob(s), (c) => c.charCodeAt(0)));

/**
 * A fake contents API holding the file's text. plan.put: statuses to answer in order; plan.race: before the n-th PUT
 * another writer appends `race.action` (so the PUT's sha is stale → 409). Error answers echo the token.
 */
function fakeGitHub(tt, plan = {}) {
  const gh = { calls: [], text: plan.text === undefined ? null : plan.text, sha: plan.text === undefined ? null : newSha(),
    put: [...(plan.put || [])], races: [...(plan.races || [])] };
  const echo = (status) => new Response(JSON.stringify({ message: "nope", echo: TOKEN }), { status });
  tt.mock.method(globalThis, "fetch", async (input, init = {}) => {
    const url = String(typeof input === "string" ? input : input.url);
    const method = init.method || "GET";
    const headers = Object.fromEntries(new Headers(init.headers || {}));
    const body = init.body ? JSON.parse(init.body) : null;
    gh.calls.push({ url, method, headers, body });
    assert.equal(url, `https://api.github.com/repos/${REPO}/contents/${FILE}`, "only the level file is touched");
    if (method === "GET") {
      if (gh.text === null) return echo(404);
      return new Response(JSON.stringify({ sha: gh.sha, encoding: "base64", content: b64(gh.text).replace(/(.{60})/g, "$1\n"),
        echo: TOKEN }), { status: 200 });
    }
    if (method === "PUT") {
      const race = gh.races.shift();
      if (race) {                                    // someone else appended between our GET and this PUT
        const cur = gh.text === null ? { v: 1, actions: [] } : JSON.parse(gh.text);
        cur.actions.push(race);
        gh.text = JSON.stringify(cur, null, 1);
        gh.sha = newSha();
      }
      const forced = gh.put.shift();
      if (forced) return echo(forced);
      if ((gh.sha || null) !== (body.sha || null)) return echo(409);
      gh.text = unb64(body.content);
      gh.sha = newSha();
      const commit = newSha();
      return new Response(JSON.stringify({ content: { sha: gh.sha }, echo: TOKEN,
        commit: { sha: commit, html_url: `https://github.com/${REPO}/commit/${commit}` } }), { status: body.sha ? 200 : 201 });
    }
    return echo(405);
  });
  gh.puts = () => gh.calls.filter((c) => c.method === "PUT");
  gh.gets = () => gh.calls.filter((c) => c.method === "GET");
  gh.actions = () => (gh.text === null ? [] : JSON.parse(gh.text).actions);
  return gh;
}

async function lv(o = {}) {
  const t = await setup({ env: { ...GH_ENV, ...(o.env || {}) } });
  t.list = (opt = {}) => t.call("GET", "/api/levels", { token: t.tokens.owner, ...opt });
  t.send = (body, opt = {}) => t.call("POST", "/api/levels/act", { token: t.tokens.owner, ...opt, body });
  t.log = () => {
    try {
      return t.db.q("SELECT who, act, app, fam, action_id, result, commit_sha FROM lv_log ORDER BY id");
    } catch {
      return [];
    }
  };
  return t;
}

const SET = { act: "set", app: APP, fam: "CPI", from: back(2), days: [back(29), back(2)], note: "naya normal" };

// ── who may read / act + CSRF ───────────────────────────────────────────────────────────────────

test("levels: Access login required (401); a non-admin gets 403 on GET and POST; GitHub and D1 never touched", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await lv();
  assert.equal((await t.list({ token: null })).status, 401);
  assert.equal((await t.send(SET, { token: null })).status, 401);
  for (const r of [await t.list({ token: t.tokens.team }), await t.send(SET, { token: t.tokens.team })]) {
    assert.equal(r.status, 403);
    assert.deepEqual(r.json, { error: "admin_only", msg: LV_MSG.admin_only });
  }
  assert.equal(gh.calls.length, 0);
  assert.equal(t.db.statements.length, 0);
});

test("levels: methods, paths, CSRF, media type and the 8 KiB body cap — all before GitHub", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await lv();
  const post = await t.call("POST", "/api/levels", { token: t.tokens.owner, body: SET });
  assert.equal(post.status, 405);
  assert.equal(post.headers.get("allow"), "GET");
  const get = await t.call("GET", "/api/levels/act", { token: t.tokens.owner });
  assert.equal(get.status, 405);
  assert.equal(get.headers.get("allow"), "POST");
  assert.equal((await t.call("OPTIONS", "/api/levels/act", { token: t.tokens.owner })).status, 405);
  for (const p of ["/api/levels/", "/api/levels/nope", "/api/levels/act/x", "/api/levels/__proto__"]) {
    assert.equal((await t.call("GET", p, { token: null })).status, 404, p);
  }
  for (const origin of [null, "https://evil.example.test", "null"]) {
    const r = await t.send(SET, { origin });
    assert.equal(r.status, 403, String(origin));
    assert.equal(r.json.error, "forbidden");
  }
  for (const ct of ["text/plain", null]) assert.equal((await t.send(SET, { ct })).status, 415, String(ct));
  assert.equal((await t.send({ ...SET, note: "n".repeat(9000) })).status, 413);
  assert.equal((await t.send("{nope", { raw: true })).status, 400);
  assert.equal(gh.calls.length, 0);
  for (const r of [post, get]) for (const [k] of r.headers) assert.equal(k.startsWith("access-control-"), false);
});

// ── validation ──────────────────────────────────────────────────────────────────────────────────

const BAD = [
  // [body, field]
  [{ ...SET, act: "delete" }, "act"],
  [{ ...SET, act: undefined }, "act"],
  [{ ...SET, by: "someone@example.test" }, "by"],
  [{ ...SET, id: "a-000000000001" }, "id"],
  [{ ...SET, at: "2026-01-01T00:00:00Z" }, "at"],
  [{ ...SET, app: "com.example.app" }, "app"],
  [{ ...SET, app: "ca-app-pub-1001/22" }, "app"],
  [{ ...SET, fam: "cpi" }, "fam"],
  [{ ...SET, fam: "__proto__" }, "fam"],
  [{ ...SET, from: "2026-02-30" }, "from"],
  [{ ...SET, from: ahead(1), days: [back(20), back(1)] }, "from"],
  [{ ...SET, from: back(1600), days: [back(1650), back(1620)] }, "from"],
  [{ ...SET, days: [back(5), back(2)] }, "days"],                       // 4 days
  [{ ...SET, days: [back(200), back(2)] }, "days"],                     // 199 days
  [{ ...SET, days: [back(2), back(29)] }, "days"],                      // reversed
  [{ ...SET, days: [back(29), back(1)] }, "days"],                      // after from
  [{ ...SET, days: [back(29)] }, "days"],
  [{ ...SET, days: undefined }, "days"],                                 // neither days nor value
  [{ ...SET, value: 31.9 }, "days"],                                     // both
  [{ act: "set", app: APP, fam: "CPI", from: back(2), value: 0 }, "value"],
  [{ act: "set", app: APP, fam: "CPI", from: back(2), value: -3 }, "value"],
  [{ act: "set", app: APP, fam: "CPI", from: back(2), value: 1e9 }, "value"],
  [{ act: "set", app: APP, fam: "CPI", from: back(2), value: "31.9" }, "value"],
  [{ ...SET, note: "bell\u0007" }, "note"],
  [{ ...SET, note: "rtl‮trick" }, "note"],
  [{ ...SET, note: "n".repeat(201) }, "note"],
  [{ ...SET, note: 5 }, "note"],
  [{ act: "rollback", app: APP, fam: "CPI", from: back(2), level: "L-xyz" }, "level"],
  [{ act: "rollback", app: APP, fam: "CPI", from: back(2) }, "level"],
  [{ act: "rollback", app: APP, fam: "CPI", from: back(2), level: "L-0123456789", days: [back(9), back(2)] }, "days"],
  [{ act: "reject", app: APP, fam: "CPI", level: "L-0123456789", from: back(2) }, "from"],
  [{ act: "accept", app: APP, fam: "ROAS_G", from: back(2), proposal: { days: [back(29), back(2)] } }, "proposal"],
  [{ act: "accept", app: APP, fam: "ROAS_G", from: back(2), proposal: { day: back(5), days: [back(29), back(2)], v: 1 } }, "proposal"],
  [{ act: "accept", app: APP, fam: "ROAS_G", from: back(2), proposal: { day: back(5), days: [back(3), back(2)] } }, "proposal"],
  [{ act: "auto", app: APP, fam: "CPI" }, "from"],
  [{ act: "undo", ref: "a-123" }, "ref"],
  [{ act: "undo", ref: "a-000000000001", app: APP }, "app"],
];

test("validation: every broken action → 400 with its field and a Hinglish reason; GitHub never called", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await lv();
  for (const [body, field] of BAD) {
    const r = await t.send(body);
    assert.equal(r.status, 400, `${JSON.stringify(body).slice(0, 90)}: ${r.text}`);
    assert.equal(r.json.error, "bad_request");
    assert.equal(r.json.field, field, JSON.stringify(body).slice(0, 90));
    assert.ok(r.json.msg && !r.json.msg.includes(TOKEN));
  }
  assert.equal(gh.calls.length, 0);
});

// ── the write ───────────────────────────────────────────────────────────────────────────────────

test("act: each action is appended (the first creates the file); by = the verified login, id + server time added", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await lv();
  const bodies = [
    SET,
    { act: "set", app: APP, fam: "ECPM", from: back(2), value: 2.5 },
    { act: "rollback", app: APP, fam: "CPI", from: back(2), level: "L-0123456789" },
    { act: "reject", app: APP, fam: "CPI", level: "L-abcdef0123" },
    { act: "accept", app: APP, fam: "ROAS_G", from: back(2), proposal: { day: back(10), days: [back(29), back(2)] } },
    { act: "auto", app: APP, fam: "GAP", from: back(2), note: "  wapas auto  " },
  ];
  const ids = [];
  for (const b of bodies) {
    const before = Date.now();
    const r = await t.send(b);
    assert.equal(r.status, 200, r.text);
    const a = r.json.action;
    assert.match(a.id, /^a-[0-9a-f]{12}$/);
    assert.equal(a.by, OWNER);
    assert.ok(Date.parse(a.at) >= before - 1000 && Date.parse(a.at) <= Date.now() + 1000);
    assert.equal(r.json.ok, true);
    assert.match(r.json.commit_url, /^https:\/\/github\.com\/.+\/commit\/[0-9a-f]{40}$/);
    ids.push(a.id);
  }
  assert.equal(new Set(ids).size, ids.length);
  const acts = gh.actions();
  assert.deepEqual(acts.map((a) => a.id), ids);
  assert.deepEqual(acts.map((a) => a.act), ["set", "set", "rollback", "reject", "accept", "auto"]);
  assert.equal(acts[5].note, "wapas auto");                              // NFC + trimmed
  assert.deepEqual(acts[0].days, SET.days);
  assert.equal(acts[1].value, 2.5);
  assert.equal(gh.puts()[0].body.sha, undefined, "the first PUT creates the file");
  assert.ok(gh.puts().slice(1).every((c) => /^[0-9a-f]{40}$/.test(c.body.sha)));
  assert.match(gh.puts()[0].body.message, /^cpi_levels — set by owner@example\.test via dashboard$/);
  assert.equal(JSON.parse(gh.text).v, 1);
  const log = t.log();
  assert.equal(log.length, 6);
  assert.deepEqual(log[0], { who: OWNER, act: "set", app: APP, fam: "CPI", action_id: ids[0], result: "ok",
    commit_sha: log[0].commit_sha });
  assert.match(log[0].commit_sha, /^[0-9a-f]{40}$/);
});

test("act: a write that conflicts re-reads and appends to the NEW content — the other writer's action survives", async (tt) => {
  const other = { id: "a-0000000000aa", at: "2026-01-01T00:00:00Z", by: "other@example.test", act: "auto", app: APP,
    fam: "CPI", from: back(3) };
  const gh = fakeGitHub(tt, { text: JSON.stringify({ v: 1, actions: [] }), races: [other] });
  const t = await lv();
  const r = await t.send(SET);
  assert.equal(r.status, 200, r.text);
  assert.deepEqual(gh.actions().map((a) => a.id), [other.id, r.json.action.id]);
  assert.deepEqual(r.json.actions.map((a) => a.id), [other.id, r.json.action.id]);
  assert.equal(gh.puts().length, 2);
  assert.equal(gh.gets().length, 2);
});

test("act: 4 conflicts in a row → 409 github_conflict, nothing half-written, audited", async (tt) => {
  const gh = fakeGitHub(tt, { put: [409, 422, 409, 409] });
  const t = await lv();
  const r = await t.send(SET);
  assert.equal(r.status, 409);
  assert.equal(r.json.error, "github_conflict");
  assert.equal(r.json.msg, "Kisi aur ne abhi save kiya — dobara try karo");
  assert.equal(gh.text, null);
  assert.equal(gh.puts().length, 4);
  assert.deepEqual(t.log().map((x) => x.result), ["github_conflict"]);
});

test("act: a broken file → 409 levels_broken and nothing is written", async (tt) => {
  for (const text of ["{nope", JSON.stringify({ v: 2, actions: [] }), JSON.stringify({ v: 1, actions: [1] }), JSON.stringify([])]) {
    const gh = fakeGitHub(tt, { text });
    const t = await lv();
    const r = await t.send(SET);
    assert.equal(r.status, 409, text);
    assert.deepEqual(r.json, { error: "levels_broken", msg: LV_MSG.levels_broken });
    assert.equal(gh.puts().length, 0);
    assert.equal(gh.text, text);
    tt.mock.restoreAll();
  }
});

test("act: undo needs a known, not-undone action that is not an undo itself (409 otherwise)", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await lv();
  const first = (await t.send(SET)).json.action;
  let r = await t.send({ act: "undo", ref: "a-0000000000ff" });
  assert.equal(r.status, 409);
  assert.deepEqual(r.json, { error: "conflict", why: "unknown_ref", msg: LV_MSG.unknown_ref });
  r = await t.send({ act: "undo", ref: first.id });
  assert.equal(r.status, 200, r.text);
  const undo = r.json.action;
  assert.deepEqual([undo.act, undo.ref], ["undo", first.id]);
  r = await t.send({ act: "undo", ref: first.id });
  assert.equal(r.json.why, "already_undone");
  r = await t.send({ act: "undo", ref: undo.id });
  assert.equal(r.json.why, "unknown_ref");
  assert.deepEqual(gh.actions().map((a) => a.act), ["set", "undo"]);
  const log = t.log();
  assert.deepEqual(log.map((x) => [x.act, x.result, x.app, x.fam]), [["set", "ok", APP, "CPI"],
    ["undo", "unknown_ref", null, null], ["undo", "ok", APP, "CPI"], ["undo", "already_undone", APP, "CPI"],
    ["undo", "unknown_ref", null, null]]);
});

test("act: the file after the append is capped at 256 KiB (413, nothing written)", async (tt) => {
  const many = [];
  for (let i = 0; i < 1300; i++) {
    many.push({ id: "a-" + i.toString(16).padStart(12, "0"), at: "2026-01-01T00:00:00Z", by: "x@example.test", act: "set",
      app: APP, fam: "CPI", from: back(2), value: 1, note: "n".repeat(150) });
  }
  const gh = fakeGitHub(tt, { text: JSON.stringify({ v: 1, actions: many }, null, 1) });
  const t = await lv();
  const r = await t.send(SET);
  assert.equal(r.status, 413);
  assert.deepEqual(r.json, { error: "payload_too_large", msg: LV_MSG.too_large });
  assert.equal(gh.puts().length, 0);
});

test("token / repo missing → 503 with the Settings reason; GitHub auth errors map like Settings; token never leaks", async (tt) => {
  const logs = [];
  tt.mock.method(console, "error", (...a) => logs.push(a.join(" ")));
  tt.mock.method(console, "log", (...a) => logs.push(a.join(" ")));
  let gh = fakeGitHub(tt);
  let t = await lv({ env: { GITHUB_TOKEN: "" } });
  let r = await t.send(SET);
  assert.equal(r.status, 503);
  assert.equal(r.json.error, "token_missing");
  assert.equal(gh.calls.length, 0);
  t = await lv({ env: { CONFIG_REPO: "owner/private-repo" } });
  assert.equal((await t.send(SET)).json.error, "repo_missing");
  const g = await t.list();
  assert.deepEqual(g.json, { actions: [], me: OWNER, admin: true, server_save: false });
  tt.mock.restoreAll();
  tt.mock.method(console, "error", (...a) => logs.push(a.join(" ")));
  gh = fakeGitHub(tt, { put: [401] });
  t = await lv();
  r = await t.send(SET);
  assert.equal(r.status, 502);
  assert.deepEqual([r.json.error, r.json.gh_status], ["github_auth", 401]);
  for (const x of [r.text, ...logs]) assert.equal(x.includes(TOKEN), false);
  const auth = gh.calls[0].headers.authorization;
  assert.equal(auth, "Bearer " + TOKEN, "the token goes only in the Authorization header");
});

// ── read ────────────────────────────────────────────────────────────────────────────────────────

test("list: the admin reads every action (no file = none), cached 30 s per isolate, refreshed by its own write", async (tt) => {
  const saved = { id: "a-0000000000bb", at: "2026-01-01T00:00:00Z", by: OWNER, act: "auto", app: APP, fam: "CPI", from: back(3) };
  const gh = fakeGitHub(tt, { text: JSON.stringify({ v: 1, actions: [saved] }) });
  const t = await lv();
  let r = await t.list();
  assert.equal(r.status, 200);
  assert.deepEqual(r.json, { actions: [saved], me: OWNER, admin: true, server_save: true });
  assert.equal(r.headers.get("cache-control"), "no-store");
  await t.list();
  assert.equal(gh.gets().length, 1, "second read from the isolate cache");
  const a = (await t.send(SET)).json.action;
  const n = gh.gets().length;
  r = await t.list();
  assert.equal(gh.gets().length, n, "the write refreshed the cache");
  assert.deepEqual(r.json.actions.map((x) => x.id), [saved.id, a.id]);
  t.resetCaches();
  gh.text = null;
  assert.deepEqual((await t.list()).json.actions, []);
});
