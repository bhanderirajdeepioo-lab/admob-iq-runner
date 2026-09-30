// Settings saves through the Worker (/api/config/status, /api/config/save): Access + admin + CSRF rules, strict
// validation of the four files, the GitHub contents-API write (sha refetch + retry on 409 / 422), the Hinglish error
// mapping, the config_log audit row, and that the GitHub token never shows up in a response or in the console.
// GitHub is a fake (global fetch mocked). Every id, repo and email here is synthetic. node --test
import test from "node:test";
import assert from "node:assert/strict";
import { setup, ORIGIN, OWNER, TEAMMATE } from "./harness.js";

const REPO = "example-owner/example-config";
const TOKEN = "ghp_TEST" + "only" + Math.random().toString(36).slice(2) + "x".repeat(12);
const GH_ENV = { GITHUB_TOKEN: TOKEN, CONFIG_REPO: REPO };
const PUB = "pub-1001";
const PUB2 = "pub-2002";
const APP = (pub, n) => `ca-app-pub-${pub.slice(4)}~${n}`;
let SHA_N = 0;
const newSha = () => (++SHA_N).toString(16).padStart(40, "a");   // 40 hex, made at runtime (no literal ids here)

const MSG = {
  admin: "Sirf admin settings badal sakta hai",
  token: "GitHub token abhi Cloudflare me nahi daala",
  auth: "GitHub token expire/galat",
  perm: "Token ko repo me likhne ki permission nahi",
  conflict: "Kisi aur ne abhi save kiya — dobara try karo",
};

const GOOD = {
  account_names: { [PUB]: "Main account", [PUB2]: "Second · ₹ wala" },
  app_names: { [APP(PUB, 11)]: "Gallery (Main)", [APP(PUB2, 22)]: "Photo Editor" },
  selected_apps: {
    accounts: {
      [PUB]: { decided: true, selected: [APP(PUB, 11), APP(PUB, 12)] },
      [PUB2]: { decided: false, selected: [] },
    },
  },
  approved_ranges: {
    placements: {
      "ca-app-pub-1001/3001": { metrics: { ecpm: { range: [1.2, 2.5], approved_at: "2026-09" } }, countries: { US: { metrics: {} } } },
      "ca-app-pub-1001/3002": { approved_at: "2026-08", range: { ctr: [1, 2] }, countries: { IN: { ctr: [1, 2] } } },   // old flat shape
    },
  },
};

/**
 * A fake GitHub contents API behind a mocked global fetch.
 * plan.get / plan.put: statuses to answer in order (then: normal behaviour). plan.throwOn: "get" | "put" → network error.
 * Every error answer echoes the token (a worst-case GitHub body), so a leak would be caught.
 */
function fakeGitHub(tt, plan = {}) {
  const gh = { calls: [], files: {}, get: [...(plan.get || [])], put: [...(plan.put || [])] };
  if (plan.existing) gh.files[plan.existing] = newSha();
  const echo = (status) => new Response(JSON.stringify({ message: "nope", echo: TOKEN, documentation_url: "x" }), { status });
  tt.mock.method(globalThis, "fetch", async (input, init = {}) => {
    const url = String(typeof input === "string" ? input : input.url);
    const headers = Object.fromEntries(new Headers(init.headers || {}));
    const method = init.method || "GET";
    const body = init.body ? JSON.parse(init.body) : null;
    gh.calls.push({ url, method, headers, body });
    const m = /^https:\/\/api\.github\.com\/repos\/([^/]+\/[^/]+)\/contents\/(.+)$/.exec(url);
    assert.ok(m, "only the GitHub contents API is called");
    const path = m[2];
    if (plan.throwOn === method.toLowerCase()) throw new TypeError(`fetch failed for ${url} with ${TOKEN}`);
    if (method === "GET") {
      const forced = gh.get.shift();
      if (forced) return echo(forced);
      if (!gh.files[path]) return echo(404);
      gh.calls[gh.calls.length - 1].sha = gh.files[path];
      return new Response(JSON.stringify({ sha: gh.files[path], path, content: "e30=", echo: TOKEN }), { status: 200 });
    }
    if (method === "PUT") {
      const forced = gh.put.shift();
      if (forced) {
        if (forced === 409 || forced === 422) gh.files[path] = newSha();   // someone else saved in between
        return echo(forced);
      }
      if ((gh.files[path] || null) !== (body.sha || null)) return echo(409);
      const commit = newSha();
      gh.files[path] = newSha();
      return new Response(JSON.stringify({
        content: { sha: gh.files[path] }, echo: TOKEN,
        commit: { sha: commit, html_url: `https://github.com/${REPO}/commit/${commit}` },
      }), { status: body.sha ? 200 : 201 });
    }
    return echo(405);
  });
  gh.puts = () => gh.calls.filter((c) => c.method === "PUT");
  gh.gets = () => gh.calls.filter((c) => c.method === "GET");
  return gh;
}

async function cfg(o = {}) {
  const t = await setup({ env: { ...GH_ENV, ...(o.env || {}) } });
  t.status = (opt = {}) => t.call("GET", "/api/config/status", { token: t.tokens.owner, ...opt });
  t.save = (body, opt = {}) => t.call("POST", "/api/config/save", { token: t.tokens.owner, ...opt, body });
  t.log = () => {
    try {
      return t.db.q("SELECT who, file, bytes, result, commit_sha FROM config_log ORDER BY id");
    } catch {
      return [];
    }
  };
  return t;
}

const b64decode = (s) => new TextDecoder().decode(Uint8Array.from(atob(s), (c) => c.charCodeAt(0)));

// ── status ──────────────────────────────────────────────────────────────────────────────────────

test("status: {server_save, admin} for the verified user; token/repo missing or placeholder → server_save false", async () => {
  const t = await cfg();
  let r = await t.status();
  assert.equal(r.status, 200);
  assert.deepEqual(r.json, { server_save: true, admin: true });
  assert.equal(r.headers.get("cache-control"), "no-store");
  r = await t.status({ token: t.tokens.team });
  assert.deepEqual(r.json, { server_save: true, admin: false });
  for (const env of [{ GITHUB_TOKEN: "" }, { GITHUB_TOKEN: undefined }, { GITHUB_TOKEN: "  " }, { CONFIG_REPO: "" },
    { CONFIG_REPO: "owner/private-repo" }, { CONFIG_REPO: "no-slash" }, { CONFIG_REPO: "a/b/c" }]) {
    const u = await cfg({ env });
    assert.deepEqual((await u.status()).json, { server_save: false, admin: true }, JSON.stringify(env));
  }
});

test("status: Access login required (401), GET only (405), unknown config path 404; D1 not touched", async () => {
  const t = await cfg();
  assert.equal((await t.status({ token: null })).status, 401);
  assert.equal((await t.status({ token: "bad.token.here" })).status, 401);
  const post = await t.call("POST", "/api/config/status", { token: t.tokens.owner, body: {} });
  assert.equal(post.status, 405);
  assert.equal(post.headers.get("allow"), "GET");
  for (const p of ["/api/config/", "/api/config/nope", "/api/config/save/", "/api/config/__proto__", "/api/config/status/x"]) {
    assert.equal((await t.call("GET", p, { token: null })).status, 404, p);
  }
  assert.equal(t.db.statements.length, 0);
});

// ── who may save + CSRF ─────────────────────────────────────────────────────────────────────────

test("save: a non-admin gets 403 'Sirf admin settings badal sakta hai'; GitHub and D1 are never touched", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await cfg();
  const r = await t.save({ file: "account_names", content: GOOD.account_names }, { token: t.tokens.team });
  assert.equal(r.status, 403);
  assert.deepEqual(r.json, { error: "admin_only", msg: MSG.admin });
  assert.equal(gh.calls.length, 0);
  assert.equal(t.db.statements.length, 0);
});

test("save: CSRF + media type + size rules still hold (403 / 415 / 413), all before GitHub", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await cfg();
  const body = { file: "account_names", content: GOOD.account_names };
  for (const origin of [null, "https://evil.example.test", "null", "http://localhost:8080"]) {
    const r = await t.save(body, { origin });
    assert.equal(r.status, 403, String(origin));
    assert.equal(r.json.error, "forbidden");
  }
  for (const ct of ["text/plain", "application/x-www-form-urlencoded", null]) {
    assert.equal((await t.save(body, { ct })).status, 415, String(ct));
  }
  assert.equal((await t.save(body, { token: null })).status, 401);
  const get = await t.call("GET", "/api/config/save", { token: t.tokens.owner });
  assert.equal(get.status, 405);
  assert.equal(get.headers.get("allow"), "POST");
  const huge = { file: "app_names", content: { [APP(PUB, 1)]: "x".repeat(270 * 1024) } };
  const big = await t.save(huge);
  assert.equal(big.status, 413);
  assert.deepEqual(big.json, { error: "payload_too_large", msg: "File bahut badi hai (256 KB tak)" });
  assert.equal((await t.save("{not json", { raw: true })).status, 400);
  assert.equal((await t.save([1, 2])).status, 400);
  assert.equal(gh.calls.length, 0);
  for (const r of [big]) for (const [k] of r.headers) assert.equal(k.startsWith("access-control-"), false);
});

test("save: the written file (indent 1) is capped at 256 KiB; a body above the review API's 8 KiB is fine", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await cfg();
  const names = {};
  for (let i = 0; i < 200; i++) names[APP(PUB, 1000 + i)] = "App naam number " + i;
  const r = await t.save({ file: "app_names", content: names });
  assert.equal(r.status, 200, r.text);
  assert.ok(JSON.stringify(names).length > 8192);
  // a body that fits the request cap, but whose file as written (indent 1) is over 256 KiB
  const many = {};
  for (let i = 0; i < 2640; i++) many[APP(PUB, 10000 + i)] = "n".repeat(70);
  const compact = JSON.stringify({ file: "app_names", content: many }).length;
  const written = new TextEncoder().encode(JSON.stringify(many, null, 1)).length;
  assert.ok(compact < 256 * 1024 + 8192 && written > 256 * 1024, `${compact} / ${written}`);
  const over = await t.save({ file: "app_names", content: many });
  assert.equal(over.status, 413);
  assert.equal(over.json.msg, "File bahut badi hai (256 KB tak)");
  assert.equal(gh.puts().length, 1);
});

// ── validation ──────────────────────────────────────────────────────────────────────────────────

test("validation: each of the four files in its real shape is accepted", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await cfg();
  for (const [file, content] of Object.entries(GOOD)) {
    const r = await t.save({ file, content });
    assert.equal(r.status, 200, `${file}: ${r.text}`);
    assert.equal(r.json.ok, true);
    assert.equal(r.json.file, file);
  }
  assert.deepEqual(gh.puts().map((c) => c.url.split("/contents/")[1]),
    ["config/account_names.json", "config/app_names.json", "config/selected_apps.json", "config/approved_ranges.json"]);
  assert.equal((await t.save({ file: "account_names", content: {} })).status, 200, "an empty map is valid");
});

const BAD = [
  // [file, content, reason fragment]
  ["account_names", [], "object hona chahiye"],
  ["account_names", null, "object hona chahiye"],
  ["account_names", { "pub-abc": "x" }, "Account id galat"],
  ["account_names", { "ca-app-pub-1001~1": "x" }, "Account id galat"],
  ["account_names", { [PUB]: "" }, "1–60"],
  ["account_names", { [PUB]: "   " }, "1–60"],
  ["account_names", { [PUB]: "y".repeat(61) }, "1–60"],
  ["account_names", { [PUB]: 5 }, "1–60"],
  ["account_names", { [PUB]: "bad\u0007bell" }, "1–60"],
  ["account_names", { [PUB]: "rtl\u202Etrick" }, "1–60"],
  ["app_names", { [PUB]: "x" }, "App id galat"],
  ["app_names", { "ca-app-pub-1001/2002": "x" }, "App id galat"],
  ["app_names", { [APP(PUB, 1)]: "z".repeat(81) }, "1–80"],
  ["app_names", { [APP(PUB, 1)]: null }, "1–80"],
  ["selected_apps", { [PUB]: { decided: true, selected: [] } }, "sirf \"accounts\""],
  ["selected_apps", { accounts: {}, extra: 1 }, "sirf \"accounts\""],
  ["selected_apps", { accounts: [] }, "sirf \"accounts\""],
  ["selected_apps", { accounts: { "pub-x": { decided: true, selected: [] } } }, "Account id galat"],
  ["selected_apps", { accounts: { [PUB]: { decided: "yes", selected: [] } } }, "decided (true/false)"],
  ["selected_apps", { accounts: { [PUB]: { decided: true } } }, "decided (true/false)"],
  ["selected_apps", { accounts: { [PUB]: { decided: true, selected: {} } } }, "decided (true/false)"],
  ["selected_apps", { accounts: { [PUB]: { decided: true, selected: [], note: "x" } } }, "decided (true/false)"],
  ["selected_apps", { accounts: { [PUB]: { decided: true, selected: ["com.example.app"] } } }, "app id galat"],
  ["selected_apps", { accounts: { [PUB]: { decided: true, selected: [7] } } }, "app id galat"],
  ["selected_apps", { accounts: { [PUB]: { decided: true, selected: [APP(PUB2, 5)] } } }, "publisher id alag"],
  ["selected_apps", { accounts: { [PUB]: { decided: true, selected: [APP("pub-10011", 5)] } } }, "publisher id alag"],
  ["approved_ranges", { placements: [] }, "sirf \"placements\""],
  ["approved_ranges", {}, "sirf \"placements\""],
  ["approved_ranges", { placements: {}, x: 1 }, "sirf \"placements\""],
  ["approved_ranges", { placements: { u1: [1, 2] } }, "object hona chahiye"],
  ["approved_ranges", { placements: { u1: { metrics: [] } } }, "\"metrics\" object"],
  ["approved_ranges", { placements: { u1: { countries: { US: [1, 2] } } } }, "country"],
  ["approved_ranges", { placements: { ["u".repeat(201)]: {} } }, "Placement id galat"],
];

test("validation: every broken shape → 400 with a Hinglish reason (incl. a selected app of another publisher)", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await cfg();
  for (const [file, content, why] of BAD) {
    const r = await t.save({ file, content });
    assert.equal(r.status, 400, `${file} ${JSON.stringify(content).slice(0, 60)}: ${r.text}`);
    assert.equal(r.json.error, "bad_request");
    assert.equal(r.json.field, "content");
    assert.ok(r.json.msg.includes(why), `${file}: "${r.json.msg}" should mention "${why}"`);
    assert.equal(/[\u0900-\u097F]/.test(r.json.msg), false, "Roman script only");
  }
  for (const body of [{ file: "accounts", content: {} }, { file: "../secrets", content: {} }, { file: "__proto__", content: {} },
    { content: {} }, { file: ["app_names"], content: {} }]) {
    const r = await t.save(body);
    assert.equal(r.status, 400, JSON.stringify(body));
    assert.equal(r.json.field, "file");
  }
  const extra = await t.save({ file: "app_names", content: {}, message: "custom" });
  assert.equal(extra.status, 400);
  assert.equal(extra.json.field, "body");
  assert.equal(gh.calls.length, 0, "nothing invalid reaches GitHub");
  assert.deepEqual(t.log(), [], "validation failures are not saves");
});

// ── the GitHub write ────────────────────────────────────────────────────────────────────────────

test("write: GET sha → PUT (indent-1 JSON, commit message with the email, User-Agent, bearer token) → {ok, sha, commit_url}", async (tt) => {
  const gh = fakeGitHub(tt, { existing: "config/selected_apps.json" });
  const t = await cfg();
  const shaBefore = gh.files["config/selected_apps.json"];
  const r = await t.save({ file: "selected_apps", content: GOOD.selected_apps });
  assert.equal(r.status, 200, r.text);
  assert.deepEqual(gh.calls.map((c) => c.method), ["GET", "PUT"]);
  for (const c of gh.calls) {
    assert.equal(c.url, `https://api.github.com/repos/${REPO}/contents/config/selected_apps.json`);
    assert.equal(c.headers["user-agent"], "admob-iq-dashboard");
    assert.equal(c.headers.authorization, "Bearer " + TOKEN);
    assert.equal(c.headers.accept, "application/vnd.github+json");
  }
  const put = gh.puts()[0].body;
  assert.deepEqual(Object.keys(put).sort(), ["content", "message", "sha"]);
  assert.equal(put.sha, shaBefore);
  assert.equal(put.message, `selected_apps — saved by ${OWNER} via dashboard`);
  assert.equal(b64decode(put.content), JSON.stringify(GOOD.selected_apps, null, 1));
  assert.match(r.json.sha, /^[0-9a-f]{40}$/);
  assert.equal(r.json.commit_url, `https://github.com/${REPO}/commit/${r.json.sha}`);
  assert.deepEqual(Object.keys(r.json).sort(), ["commit_url", "file", "ok", "sha"]);
});

test("write: a file that does not exist yet (GET 404) is created without a sha; UTF-8 content survives", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await cfg();
  const r = await t.save({ file: "account_names", content: GOOD.account_names });
  assert.equal(r.status, 200, r.text);
  const put = gh.puts()[0].body;
  assert.equal("sha" in put, false);
  assert.equal(b64decode(put.content), JSON.stringify(GOOD.account_names, null, 1));
  assert.ok(b64decode(put.content).includes("₹ wala"));
});

test("write: 409 → sha refetched and PUT retried; 422 likewise; up to 3 retries, then 409 'Kisi aur ne abhi save kiya'", async (tt) => {
  const body = { file: "app_names", content: GOOD.app_names };
  {
    const gh = fakeGitHub(tt, { existing: "config/app_names.json", put: [409] });
    const t = await cfg();
    const r = await t.save(body);
    assert.equal(r.status, 200, r.text);
    assert.deepEqual(gh.calls.map((c) => c.method), ["GET", "PUT", "GET", "PUT"]);
    const [a, b] = gh.puts().map((c) => c.body.sha);
    assert.equal(a, gh.gets()[0].sha);
    assert.notEqual(a, b, "the retry uses the fresh sha");
    assert.equal(b, gh.gets()[1].sha, "…the one the second GET returned");
    tt.mock.restoreAll();
  }
  {
    const gh = fakeGitHub(tt, { existing: "config/app_names.json", put: [422, 422, 422] });
    const t = await cfg();
    const r = await t.save(body);
    assert.equal(r.status, 200, r.text);
    assert.equal(gh.puts().length, 4, "1 PUT + 3 retries");
    tt.mock.restoreAll();
  }
  {
    const gh = fakeGitHub(tt, { existing: "config/app_names.json", put: [409, 422, 409, 409] });
    const t = await cfg();
    const r = await t.save(body);
    assert.equal(r.status, 409);
    assert.deepEqual(r.json, { error: "github_conflict", msg: MSG.conflict, gh_status: 409 });
    assert.equal(gh.puts().length, 4);
    assert.equal(gh.gets().length, 4);
    assert.deepEqual(t.log().map((x) => x.result), ["github_conflict"]);
  }
});

test("errors: token missing → 503 (no GitHub call); CONFIG_REPO missing → 503; both audited", async (tt) => {
  const gh = fakeGitHub(tt);
  let t = await cfg({ env: { GITHUB_TOKEN: undefined } });
  let r = await t.save({ file: "account_names", content: GOOD.account_names });
  assert.equal(r.status, 503);
  assert.deepEqual(r.json, { error: "token_missing", msg: MSG.token });
  assert.deepEqual(t.log().map((x) => x.result), ["token_missing"]);
  t = await cfg({ env: { CONFIG_REPO: "" } });
  r = await t.save({ file: "account_names", content: GOOD.account_names });
  assert.equal(r.status, 503);
  assert.equal(r.json.error, "repo_missing");
  assert.match(r.json.msg, /CONFIG_REPO/);
  assert.equal(gh.calls.length, 0);
});

test("errors: GitHub 401 → 'GitHub token expire/galat'; 403 / 404 → 'permission nahi'; 5xx / network → unavailable", async (tt) => {
  const cases = [
    [{ get: [401] }, 502, "github_auth", MSG.auth, 401],
    [{ existing: "config/app_names.json", put: [401] }, 502, "github_auth", MSG.auth, 401],
    [{ get: [403] }, 502, "github_forbidden", MSG.perm, 403],
    [{ existing: "config/app_names.json", put: [403] }, 502, "github_forbidden", MSG.perm, 403],
    [{ put: [404] }, 502, "github_forbidden", MSG.perm, 404],     // GET 404 (no access looks like "new") → PUT 404
    [{ get: [500] }, 502, "github_unavailable", null, 500],
    [{ existing: "config/app_names.json", put: [502] }, 502, "github_unavailable", null, 502],
    [{ throwOn: "get" }, 502, "github_unavailable", null, 0],
    [{ existing: "config/app_names.json", throwOn: "put" }, 502, "github_unavailable", null, 0],
  ];
  for (const [plan, status, error, msg, ghStatus] of cases) {
    const gh = fakeGitHub(tt, plan);
    const t = await cfg();
    const r = await t.save({ file: "app_names", content: GOOD.app_names });
    assert.equal(r.status, status, JSON.stringify(plan));
    assert.equal(r.json.error, error, JSON.stringify(plan));
    if (msg) assert.equal(r.json.msg, msg);
    else assert.equal(r.json.msg, "GitHub se jud nahi paaye — thodi der baad try karo");
    assert.equal(r.json.gh_status, ghStatus);
    assert.deepEqual(Object.keys(r.json).sort(), ["error", "gh_status", "msg"], "nothing from GitHub's body");
    assert.deepEqual(t.log().map((x) => x.result), [error]);
    assert.ok(gh.calls.length >= 1);
    tt.mock.restoreAll();
  }
});

// ── audit ───────────────────────────────────────────────────────────────────────────────────────

test("audit: each save appends a config_log row (who, at, file, bytes, result, commit sha)", async (tt) => {
  fakeGitHub(tt);
  const t = await cfg();
  const r1 = await t.save({ file: "account_names", content: GOOD.account_names });
  const r2 = await t.save({ file: "approved_ranges", content: GOOD.approved_ranges });
  assert.equal(r1.status, 200);
  assert.equal(r2.status, 200);
  const rows = t.db.q("SELECT who, at, file, bytes, result, commit_sha FROM config_log ORDER BY id");
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((x) => [x.who, x.file, x.result, x.commit_sha]), [
    [OWNER, "account_names", "ok", r1.json.sha], [OWNER, "approved_ranges", "ok", r2.json.sha]]);
  assert.equal(rows[0].bytes, new TextEncoder().encode(JSON.stringify(GOOD.account_names, null, 1)).length);
  for (const x of rows) assert.match(x.at, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  assert.equal(t.db.q("SELECT COUNT(*) AS n FROM rv_actions")[0].n, 0, "the review log is not touched");
});

test("audit: D1 down before the write → 503 db_unavailable and no commit; audit insert failing after a commit → still 200", async (tt) => {
  const gh = fakeGitHub(tt);
  const t = await cfg();
  t.db.failNext = new Error("d1 down");
  const r = await t.save({ file: "account_names", content: GOOD.account_names });
  assert.equal(r.status, 503);
  assert.equal(r.json.error, "db_unavailable");
  assert.equal(gh.calls.length, 0);
  const u = await cfg();
  const orig = u.db.prepare.bind(u.db);
  tt.mock.method(u.db, "prepare", (sql) => {
    if (/INSERT INTO config_log/.test(sql)) throw new Error("insert failed");
    return orig(sql);
  });
  tt.mock.method(console, "error", () => {});
  const ok = await u.save({ file: "account_names", content: GOOD.account_names });
  assert.equal(ok.status, 200, "the commit happened; the page must not show a failure");
});

// ── secrets ─────────────────────────────────────────────────────────────────────────────────────

test("secrets: the GitHub token never appears in any response body/header or in console output", async (tt) => {
  const lines = [];
  for (const m of ["log", "info", "warn", "error", "debug"]) {
    tt.mock.method(console, m, (...args) => lines.push(args.map((a) => (a && a.stack) || String(a)).join(" ")));
  }
  const seen = [];
  const plans = [{}, { existing: "config/app_names.json" }, { get: [401] }, { put: [403] }, { put: [409, 409, 409, 409] },
    { get: [500] }, { throwOn: "get" }, { throwOn: "put" }];
  for (const plan of plans) {
    const gh = fakeGitHub(tt, plan);
    const t = await cfg();
    seen.push(await t.status(), await t.status({ token: t.tokens.team }));
    seen.push(await t.save({ file: "app_names", content: GOOD.app_names }));
    seen.push(await t.save({ file: "app_names", content: { bad: TOKEN } }));
    seen.push(await t.save({ file: "app_names", content: GOOD.app_names }, { token: t.tokens.team }));
    t.db.failNext = new Error("db " + TOKEN);
    seen.push(await t.save({ file: "app_names", content: GOOD.app_names }));
    assert.ok(gh.calls.some((c) => c.headers.authorization === "Bearer " + TOKEN), "the token was really used");
    gh.calls.length = 0;
    // restore only fetch; keep the console spies
    globalThis.fetch.mock.restore();
  }
  assert.ok(seen.length >= 40);
  for (const r of seen) {
    assert.equal(r.text.includes(TOKEN), false, `response leaked the token: ${r.status}`);
    assert.equal(r.text.includes("ghp_"), false);
    for (const [, v] of r.headers) assert.equal(v.includes(TOKEN), false);
  }
  const joined = lines.join("\n");
  assert.ok(lines.length >= 1, "failures were logged (type only)");
  for (const s of [TOKEN, "ghp_", OWNER, TEAMMATE, "@", REPO]) assert.equal(joined.includes(s), false, `console leaked ${s}`);
});

test("the review API is unchanged next to the config API (same origin rules, same messages)", async () => {
  const t = await cfg();
  const me = await t.get("me", { token: t.tokens.owner });
  assert.equal(me.status, 200);
  assert.equal(me.json.admin, true);
  const big = await t.act({ act: "note", app: "a1a1a1a1a1a1", note: "x".repeat(9 * 1024) });
  assert.deepEqual([big.status, big.json.msg], [413, "Note bahut lamba hai"]);
  const bad = await t.act({ act: "nope" });
  assert.deepEqual(bad.json, { error: "bad_request", msg: "Galat request (act)", field: "act" });
  assert.equal((await t.call("GET", "/api/other", { token: null })).status, 404);
  assert.equal(ORIGIN, "http://localhost");
});
