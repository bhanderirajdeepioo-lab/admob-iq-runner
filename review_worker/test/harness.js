// Shared test setup: fake D1 + fake ASSETS (index.json and day docs) + signed tokens + request helpers.
// All data is synthetic (fake keys, "Demo …" names, example.test emails).

import { gzipSync } from "node:zlib";
import worker, { _resetForTests } from "../src/index.js";
import { FakeD1 } from "./fake_d1.js";
import { makeKey, jwksOf, signJwt, claims, OWNER, TEAMMATE, TEAM, AUD } from "./jwt.js";

export { OWNER, TEAMMATE, TEAM, AUD };
export const TEAM2 = "team2@example.test";

export const K = {
  a: "a1a1a1a1a1a1", b: "b2b2b2b2b2b2", c: "c3c3c3c3c3c3", d: "d4d4d4d4d4d4", e: "e5e5e5e5e5e5",
};
export const D0 = "2026-10-01";   // an older snapshot day
export const D1 = "2026-10-02";   // the open day (default index)
export const D2 = "2026-10-03";
export const ORIGIN = "http://localhost";

export const LABEL = (k) => `Demo ${k.slice(0, 2).toUpperCase()} Photo · Acme Games`;

/** Synthetic day doc: only the fields the Worker reads (day, apps[].key/name/acct). */
export function makeDoc(day, keys) {
  return { v: 1, day, apps: keys.map((k) => ({ key: k, name: `Demo ${k.slice(0, 2).toUpperCase()} Photo`, acct: "Acme Games" })) };
}

export const DAY_APPS = {
  [D0]: [K.a, K.b, K.c, K.e],
  [D1]: [K.a, K.b, K.c, K.d],
  [D2]: [K.a, K.b, K.c, K.d],
};

export function makeIndex(openDay = D1, over = {}) {
  const days = Object.keys(DAY_APPS).filter((d) => d <= openDay).sort();
  return {
    v: 1, go_live: days[0] || null, today_ist: openDay, open_day: openDay, pending_today: false, retry: false,
    ready_ist: "09:00", next_snapshot: null,
    days: days.map((d) => ({ d, apps: DAY_APPS[d].length, top: 1, small: 1, file: `review/days/${d}.json.gz` })),
    open_apps: Object.fromEntries(DAY_APPS[openDay].map((k) => [k, LABEL(k)])),
    ...over,
  };
}

/** The static files the fake ASSETS binding serves. `gzip:false` serves day docs as plain JSON bytes. */
export function siteFiles({ index = makeIndex(), gzip = true } = {}) {
  const files = { "/index.html": "<!doctype html><title>dash</title>" };
  if (index !== null) files["/review/index.json"] = typeof index === "string" ? index : JSON.stringify(index);
  for (const d of Object.keys(DAY_APPS)) {
    const raw = JSON.stringify(makeDoc(d, DAY_APPS[d]));
    files[`/review/days/${d}.json.gz`] = gzip ? gzipSync(raw) : raw;
  }
  return files;
}

export function makeAssets(files) {
  const calls = [];
  return {
    calls,
    files,
    async fetch(input) {
      const u = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url);
      calls.push(u.pathname);
      const body = files[u.pathname];
      if (body === undefined) return new Response("Not found", { status: 404 });
      return new Response(body, { status: 200 });
    },
  };
}

let KEY = null;
export async function testKey() {
  if (!KEY) KEY = await makeKey("kid-test-a");
  return KEY;
}

/** Every response the helpers saw (to assert "no Access-Control-* header anywhere"). */
export const SEEN = [];

/**
 * A fresh isolate (caches reset), a fresh D1 and helpers.
 * @param {{index?: object|null|string, gzip?: boolean, env?: object, files?: object}} o
 */
export async function setup(o = {}) {
  _resetForTests();
  const key = await testKey();
  const db = new FakeD1();
  const assets = makeAssets(o.files || siteFiles({ index: o.index === undefined ? makeIndex() : o.index, gzip: o.gzip !== false }));
  const env = {
    REVIEW_DB: db, ASSETS: assets, ACCESS_TEAM_DOMAIN: TEAM, ACCESS_AUD: AUD, ADMIN_EMAILS: OWNER,
    ACCESS_JWKS_JSON: JSON.stringify(jwksOf(key)), ...(o.env || {}),
  };
  const tokens = {
    owner: await signJwt(key, claims(OWNER)),
    team: await signJwt(key, claims(TEAMMATE)),
    team2: await signJwt(key, claims(TEAM2)),
  };

  async function call(method, path, opt = {}) {
    const h = new Headers(opt.headers || {});
    const token = "token" in opt ? opt.token : tokens.team;
    if (token) h.set("Cf-Access-Jwt-Assertion", token);
    let body;
    if (opt.body !== undefined) {
      body = opt.raw ? opt.body : JSON.stringify(opt.body);
      const ct = "ct" in opt ? opt.ct : "application/json";
      if (ct) h.set("Content-Type", ct);
      const origin = "origin" in opt ? opt.origin : ORIGIN;
      if (origin) h.set("Origin", origin);
    }
    const res = await worker.fetch(new Request((opt.base || ORIGIN) + path, { method, headers: h, body }), env, {});
    const text = await res.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {
      json = null;
    }
    const out = { status: res.status, headers: res.headers, json, text };
    SEEN.push(out);
    return out;
  }

  const get = (path, opt) => call("GET", "/api/review/" + path, opt);
  const post = (path, body, opt = {}) => call("POST", "/api/review/" + path, { ...opt, body });
  const act = (body, opt) => post("action", { d: D1, ...body }, opt);
  const decide = (body, opt = {}) => post("decide", body, { token: tokens.owner, ...opt });
  const day = async (d = D1, opt) => (await get(`day?d=${d}`, opt)).json;

  /** Swap the served index (e.g. the next day opens) and drop the isolate caches, keeping D1 data. */
  function setIndex(index) {
    if (index === null) delete assets.files["/review/index.json"];
    else assets.files["/review/index.json"] = typeof index === "string" ? index : JSON.stringify(index);
    _resetForTests();
  }

  /** A new isolate: JWKS / schema / index / doc caches dropped (D1 data kept). */
  const resetCaches = () => _resetForTests();

  return { db, env, assets, key, tokens, call, get, post, act, decide, day, setIndex, resetCaches };
}
