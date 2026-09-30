// Access JWT verification (auth.js through the real Worker entry). node --test
import test from "node:test";
import assert from "node:assert/strict";
import { setup, OWNER, TEAMMATE, TEAM, AUD, testKey } from "./harness.js";
import { makeKey, jwksOf, signJwt, signHs256, unsignedJwt, claims, b64url } from "./jwt.js";
import { isAdmin, accessConfig, readToken } from "../src/auth.js";

const REMOTE = "https://admob.example.test";          // not localhost → ACCESS_JWKS_JSON must be ignored
const CERTS = `https://${TEAM}/cdn-cgi/access/certs`;
const now = () => Math.floor(Date.now() / 1000);

const me = (t, token, opt = {}) => t.get("me", { token, ...opt });

/** Mock global fetch as the Access certs endpoint. `impl(url)` returns a Response or throws. */
function mockCerts(t, impl) {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    calls.push(String(url));
    return impl(String(url));
  });
  return calls;
}
const jwksResponse = (...keys) => new Response(JSON.stringify(jwksOf(...keys)), { status: 200, headers: { "content-type": "application/json" } });

test("valid token → me 200; admin true for ADMIN_EMAILS, false otherwise; email lower-cased", async () => {
  const t = await setup();
  const o = await me(t, t.tokens.owner);
  assert.equal(o.status, 200);
  assert.equal(o.json.email, OWNER);
  assert.equal(o.json.admin, true);
  const r = await me(t, t.tokens.team);
  assert.equal(r.status, 200);
  assert.deepEqual([r.json.email, r.json.admin], [TEAMMATE, false]);
  assert.equal(r.json.open_day, "2026-10-02");
  assert.match(r.json.server_time, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  const upper = await signJwt(t.key, claims("Owner@Example.TEST"));
  const u = await me(t, upper);
  assert.equal(u.status, 200);
  assert.deepEqual([u.json.email, u.json.admin], [OWNER, true]);
});

test("missing token → 401 with the fixed Hinglish message", async () => {
  const t = await setup();
  const r = await me(t, null);
  assert.equal(r.status, 401);
  assert.deepEqual(r.json, { error: "unauthorized", msg: "Login zaroori — page reload karo" });
});

test("cookie CF_Authorization works like the header; the header wins when both are sent", async () => {
  const t = await setup();
  const c = await me(t, null, { headers: { Cookie: `theme=dark; CF_Authorization=${t.tokens.team}; x=1` } });
  assert.equal(c.status, 200);
  assert.equal(c.json.email, TEAMMATE);
  const both = await me(t, "garbage.token.value", { headers: { Cookie: `CF_Authorization=${t.tokens.team}` } });
  assert.equal(both.status, 401);
  const emptyCookie = await me(t, null, { headers: { Cookie: "CF_Authorization=; other=1" } });
  assert.equal(emptyCookie.status, 401);
});

test("alg none / HS256 (alg confusion) / RS512 / PS256 / missing kid → 401", async () => {
  const t = await setup();
  const c = claims(TEAMMATE);
  const tokens = [
    unsignedJwt(c, { kid: t.key.kid }),
    unsignedJwt(c, { kid: t.key.kid }, "e30"),
    await signHs256(t.key.jwk.n, c, { kid: t.key.kid }),
    await signJwt(t.key, c, { alg: "RS512" }),
    await signJwt(t.key, c, { alg: "PS256" }),
    await signJwt(t.key, c, { kid: undefined }),
    await signJwt(t.key, c, { kid: "" }),
    await signJwt(t.key, c, { crit: ["exp"] }),
  ];
  for (const tok of tokens) assert.equal((await me(t, tok)).status, 401, tok.slice(0, 40));
});

test("bad signature: other key with the same kid, tampered payload, truncated signature → 401", async () => {
  const t = await setup();
  const other = await makeKey(t.key.kid);
  assert.equal((await me(t, await signJwt(other, claims(OWNER)))).status, 401);
  const good = t.tokens.team;
  const [h, , s] = good.split(".");
  const forged = `${h}.${b64url(JSON.stringify(claims(OWNER)))}.${s}`;
  assert.equal((await me(t, forged)).status, 401);
  assert.equal((await me(t, good.slice(0, -10))).status, 401);
  assert.equal((await me(t, good)).status, 200);
});

test("unknown kid (localhost test JWKS) → 401", async () => {
  const t = await setup();
  const stranger = await makeKey("kid-unknown");
  assert.equal((await me(t, await signJwt(stranger, claims(OWNER)))).status, 401);
});

test("wrong iss → 401 (other team, http://, trailing slash, missing)", async () => {
  const t = await setup();
  for (const iss of ["https://evil.example.test", `http://${TEAM}`, `https://${TEAM}/`, undefined]) {
    assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { iss })))).status, 401, String(iss));
  }
});

test("aud: wrong string / wrong array / missing → 401; right string or array containing it → 200", async () => {
  const t = await setup();
  for (const aud of ["other-aud", ["other-aud", "x"], [], undefined, 42]) {
    assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { aud })))).status, 401, JSON.stringify(aud));
  }
  for (const aud of [AUD, ["x", AUD]]) {
    assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { aud })))).status, 200, JSON.stringify(aud));
  }
});

test("exp: past by > 60 s → 401; within the 60 s skew → 200; missing / non-number → 401", async () => {
  const t = await setup();
  assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { exp: now() - 120 })))).status, 401);
  assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { exp: now() - 30 })))).status, 200);
  assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { exp: undefined })))).status, 401);
  assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { exp: String(now() + 999) })))).status, 401);
});

test("nbf / iat in the future (beyond skew) → 401; within skew → 200", async () => {
  const t = await setup();
  assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { nbf: now() + 300 })))).status, 401);
  assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { nbf: now() + 30 })))).status, 200);
  assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { iat: now() + 300 })))).status, 401);
  assert.equal((await me(t, await signJwt(t.key, claims(TEAMMATE, { nbf: "0" })))).status, 401);
});

test("no email (service token) / malformed email → 401", async () => {
  const t = await setup();
  for (const email of [undefined, "", "no-at-sign", "a@b@c", "sp ace@example.test", 7]) {
    assert.equal((await me(t, await signJwt(t.key, claims(email)))).status, 401, String(email));
  }
});

test("malformed tokens → 401 (bad base64, wrong part count, non-JSON, array payload, too long)", async () => {
  const t = await setup();
  const h = b64url(JSON.stringify({ alg: "RS256", kid: t.key.kid }));
  const p = b64url(JSON.stringify(claims(TEAMMATE)));
  const bad = [
    "abc", "a.b", "a.b.c.d", `${h}.${p}.`, `${h}..sig`, `.${p}.sig`,
    `${h}.${p}.sig!!`, `${h}.p@yload.sig`, `${h}.${p}x.sig`,                 // bad chars / bad length
    `${b64url("not json")}.${p}.sig`, `${h}.${b64url("[1,2]")}.sig`, `${h}.${b64url("null")}.sig`,
    `${b64url("\xff\xfe")}.${p}.sig`,
    `${h}.${p}.${"A".repeat(20000)}`,
  ];
  for (const tok of bad) assert.equal((await me(t, tok)).status, 401, tok.slice(0, 50));
});

test("JWKS fetch failure → 503 auth_unavailable (network error, HTTP 500, bad JSON, no RSA keys)", async (tt) => {
  const t = await setup();
  const token = t.tokens.team;
  const cases = [
    () => { throw new TypeError("network down"); },
    () => new Response("oops", { status: 500 }),
    () => new Response("not json", { status: 200 }),
    () => new Response(JSON.stringify({ keys: [{ kty: "EC", kid: "x" }] }), { status: 200 }),
  ];
  for (const impl of cases) {
    t.resetCaches();
    const calls = mockCerts(tt, impl);
    const r = await me(t, token, { base: REMOTE });
    assert.equal(r.status, 503);
    assert.equal(r.json.error, "auth_unavailable");
    assert.equal(r.json.msg, "Server me dikkat — thodi der baad try karo");
    assert.deepEqual(calls, [CERTS]);
    tt.mock.restoreAll();
  }
});

test("ACCESS_JWKS_JSON is ignored on a non-localhost host (JWKS fetched from the team domain)", async (tt) => {
  const t = await setup();
  const calls = mockCerts(tt, () => new Response("{}", { status: 200 }));   // team JWKS has no keys
  const r = await me(t, t.tokens.team, { base: REMOTE });
  assert.equal(r.status, 503);
  assert.deepEqual(calls, [CERTS]);
  tt.mock.restoreAll();

  t.resetCaches();
  const key = await testKey();
  const calls2 = mockCerts(tt, () => jwksResponse(key));
  const ok = await me(t, t.tokens.team, { base: REMOTE });
  assert.equal(ok.status, 200);
  assert.deepEqual(calls2, [CERTS]);
});

test("ACCESS_JWKS_JSON is honoured on localhost, 127.0.0.1 and [::1] (no network fetch)", async (tt) => {
  const t = await setup();
  const calls = mockCerts(tt, () => { throw new Error("must not fetch"); });
  for (const base of ["http://localhost:8787", "http://127.0.0.1:8787", "http://[::1]:8787"]) {
    assert.equal((await me(t, t.tokens.team, { base })).status, 200, base);
  }
  assert.equal(calls.length, 0);
});

test("JWKS cached 10 min; unknown kid → one forced refetch at most every 30 s; rotation picks up new keys", async (tt) => {
  const t = await setup();
  const key = await testKey();
  const rotated = await makeKey("kid-rotated");
  let serve = [key];
  const calls = mockCerts(tt, () => jwksResponse(...serve));
  let clock = Date.now();
  tt.mock.method(Date, "now", () => clock);

  assert.equal((await me(t, t.tokens.team, { base: REMOTE })).status, 200);
  assert.equal((await me(t, t.tokens.owner, { base: REMOTE })).status, 200);
  assert.equal(calls.length, 1, "second request uses the cache");

  const stranger = await signJwt(await makeKey("kid-nobody"), claims(OWNER));
  assert.equal((await me(t, stranger, { base: REMOTE })).status, 401);
  assert.equal(calls.length, 1, "cache younger than 30 s → no forced refetch");

  clock += 31_000;
  assert.equal((await me(t, stranger, { base: REMOTE })).status, 401);
  assert.equal(calls.length, 2, "one forced refetch");
  assert.equal((await me(t, stranger, { base: REMOTE })).status, 401);
  assert.equal(calls.length, 2, "not again within 30 s");

  serve = [key, rotated];
  clock += 31_000;
  const rotTok = await signJwt(rotated, claims(TEAMMATE));
  assert.equal((await me(t, rotTok, { base: REMOTE })).status, 200, "new kid found after refetch");
  assert.equal(calls.length, 3);

  clock += 10 * 60 * 1000 + 1;
  assert.equal((await me(t, t.tokens.team, { base: REMOTE })).status, 200);
  assert.equal(calls.length, 4, "TTL expired → refetch");
});

test("missing / placeholder config → 500 misconfigured (no data served)", async () => {
  for (const env of [
    { ACCESS_AUD: "" }, { ACCESS_TEAM_DOMAIN: "" }, { ACCESS_AUD: undefined }, { ACCESS_TEAM_DOMAIN: "ACCESS_TEAM_DOMAIN" },
    { ACCESS_AUD: "ACCESS_AUD" }, { ACCESS_TEAM_DOMAIN: "not a domain/x" },
  ]) {
    const t = await setup({ env });
    const r = await me(t, t.tokens.owner);
    assert.equal(r.status, 500, JSON.stringify(env));
    assert.equal(r.json.error, "misconfigured");
    assert.equal(r.json.email, undefined);
  }
  const bad = await setup({ env: { ACCESS_JWKS_JSON: "{not json" } });
  assert.equal((await me(bad, bad.tokens.owner)).status, 500);
});

test("ACCESS_TEAM_DOMAIN given as https://…/ is normalised (iss still must match exactly)", async () => {
  const t = await setup({ env: { ACCESS_TEAM_DOMAIN: `https://${TEAM}/` } });
  assert.equal((await me(t, t.tokens.team)).status, 200);
  assert.deepEqual(accessConfig({ ACCESS_TEAM_DOMAIN: `HTTPS://${TEAM.toUpperCase()}`, ACCESS_AUD: "x" }), { domain: TEAM, aud: "x" });
});

test("isAdmin: comma/space list, case-insensitive, junk ignored", () => {
  const env = { ADMIN_EMAILS: " Owner@Example.test,  second@example.test  third@example.test,,notanemail " };
  assert.equal(isAdmin(OWNER, env), true);
  assert.equal(isAdmin("second@example.test", env), true);
  assert.equal(isAdmin("third@example.test", env), true);
  assert.equal(isAdmin("notanemail", env), false);
  assert.equal(isAdmin(TEAMMATE, env), false);
  assert.equal(isAdmin(OWNER, {}), false);
  assert.equal(isAdmin("", env), false);
});

test("readToken: header first, then the CF_Authorization cookie", () => {
  const req = (h) => new Request("http://localhost/api/review/me", { headers: h });
  assert.equal(readToken(req({ "Cf-Access-Jwt-Assertion": " a.b.c " })), "a.b.c");
  assert.equal(readToken(req({ Cookie: "CF_Authorization=x.y.z" })), "x.y.z");
  assert.equal(readToken(req({ Cookie: "CF_Authorization_other=1" })), null);
  assert.equal(readToken(req({})), null);
});

test("devkeys.mjs (local e2e helper) prints a JWKS + owner/team/expired tokens that this Worker accepts / rejects", async () => {
  const { execFileSync } = await import("node:child_process");
  const { fileURLToPath } = await import("node:url");
  const env = { ...process.env };
  delete env.NODE_TEST_CONTEXT;
  const out = JSON.parse(execFileSync(process.execPath, [fileURLToPath(new URL("./devkeys.mjs", import.meta.url))], { env, encoding: "utf8" }));
  assert.deepEqual(Object.keys(out.tokens).sort(), ["expired", "owner", "team"]);
  assert.equal(out.jwks_line, JSON.stringify(out.jwks));
  const t = await setup({ env: { ACCESS_JWKS_JSON: out.jwks_line } });
  const o = await me(t, out.tokens.owner, { base: "http://localhost:8787" });
  assert.deepEqual([o.status, o.json.email, o.json.admin], [200, OWNER, true]);
  const m = await me(t, out.tokens.team, { base: "http://localhost:8787" });
  assert.deepEqual([m.status, m.json.email, m.json.admin], [200, TEAMMATE, false]);
  assert.equal((await me(t, out.tokens.expired, { base: "http://localhost:8787" })).status, 401);
  assert.equal((await me(t, t.tokens.owner, { base: "http://localhost:8787" })).status, 401, "a different key pair is not accepted");
});
