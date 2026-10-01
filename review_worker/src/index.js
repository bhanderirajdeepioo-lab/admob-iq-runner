// Daily App Review API — Cloudflare Worker entry.
//
//   /api/review/*   → this API (Access JWT verified here, then D1 binding REVIEW_DB)
//   /api/config/*   → Settings saves (Access JWT, admins only; commits config/<file>.json with the GITHUB_TOKEN
//                     secret — see config.js), audited in D1 (config_log)
//   /api/marks      → 📌 saved dates of "compare any date" (Access JWT; GET all, POST add; /api/marks/delete: the
//                     author or an admin) in D1 (cmp_marks, audited in cmp_marks_log — see db.js)
//   other /api/*    → 404 JSON
//   everything else → the static dashboard (env.ASSETS), exactly as without this Worker
//
// Security model (see README): the host is behind Cloudflare Access at the edge AND every API request is
// re-verified here (RS256 JWT, iss, aud, exp). POSTs need JSON + a same-origin Origin header (CSRF). No CORS
// headers are ever sent. Nothing logs emails, notes, app names or money: errors log their TYPE only.

import { ApiError, verifyAccess, isAdmin, _resetAuthForTests } from "./auth.js";
import {
  FEATS, ensureSchema, getRev, getDayState, getAppView, getStates, getCalendar, applyAction, decideFlag,
  _resetSchemaForTests, validateMark, validateDelete, listMarks, addMark, deleteMark,
} from "./db.js";
import { CFG_MSG, CONFIG_MAX_BYTES, serverSaveReady, githubConfig, validateSave, commitConfig, auditSave } from "./config.js";

export { ApiError };

const PREFIX = "/api/review/";
const ROUTES = { me: "GET", day: "GET", calendar: "GET", action: "POST", decide: "POST" };
const CONFIG_PREFIX = "/api/config/";
const CONFIG_ROUTES = { status: "GET", save: "POST" };
const MARKS_PATH = "/api/marks";
const MARKS_ROUTES = { "": ["GET", "POST"], "/delete": ["POST"] };   // /api/marks · /api/marks/delete
const MAX_BODY = 8192;
const CONFIG_MAX_BODY = CONFIG_MAX_BYTES + 8192;   // {file, content}: the file (≤ 256 KiB as written) + the envelope
const NOTE_MAX = 600;
const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;
const KEY_RE = /^[0-9a-f]{12}$/;
const ACTS = new Set(["ok", "note", "kal", "flag", "unflag", "undo", "snooze", "unsnooze", "bulk_ok"]);
const FIX_ACTS = new Set(["ok", "note", "undo", "bulk_ok"]);   // admin corrections allowed on older days
const DECISIONS = new Set(["theek", "kaam", "band", "done"]);
const INDEX_TTL_MS = 60 * 1000;
const INDEX_MISS_TTL_MS = 15 * 1000;
const DOC_LRU = 5;

const HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Robots-Tag": "noindex",
  // never framed (clickjacking): the page's static _headers say the same for the dashboard itself
  "X-Frame-Options": "DENY",
  "Content-Security-Policy": "frame-ancestors 'none'",
};

const SERVER_MSG = "Server me dikkat — thodi der baad try karo";
const MSG = {
  bad_request: "Galat request",
  unauthorized: "Login zaroori — page reload karo",
  forbidden: "Ye kaam allowed nahi",
  admin_only: "Sirf admin faisla kar sakta hai",
  day_closed: "Ye din band ho chuka — sirf admin sudhaar kar sakta hai",
  not_found: "Nahi mila",
  method_not_allowed: "Galat method",
  review_not_started: "Review abhi shuru nahi hua",
  payload_too_large: "Note bahut lamba hai",
  unsupported_media_type: "Galat format",
  server_error: SERVER_MSG,
  misconfigured: SERVER_MSG,
  auth_unavailable: SERVER_MSG,
  db_unavailable: SERVER_MSG,
};
const CONFLICT_MSG = {
  flagged: "Ye card 🚩 Re-review me hai — admin ke faisle tak aise hi rahega",
  already_flagged: "Ye pehle se 🚩 Re-review me hai",
  not_open: "Ye 🚩 ab khula nahi hai",
  not_kaam: "Ye 🚩 abhi kaam me nahi hai",
  already_decided: "Is 🚩 pe faisla ho chuka hai",
  day_moved: "Naye din ke cards aa gaye — upar “Kholo” dabao",
};

// ── per-isolate caches (test-only reset below) ──────────────────────────────────────────────────
let indexCache = null;        // {at, val}
let docCache = new Map();     // day → Map key→label (LRU, DOC_LRU entries)

/** TEST ONLY: clear the JWKS, schema, index and day-doc caches of this isolate. */
export function _resetForTests() {
  _resetAuthForTests();
  _resetSchemaForTests();
  indexCache = null;
  docCache = new Map();
}

// ── responses ───────────────────────────────────────────────────────────────────────────────────

function json(status, body, extraHeaders) {
  return new Response(JSON.stringify(body), { status, headers: { ...HEADERS, ...(extraHeaders || {}) } });
}

function errorResponse(e) {
  const x = e.extra || {};
  let msg = MSG[e.error] || SERVER_MSG;
  if (e.error === "bad_request") msg = `Galat request (${x.field || "body"})`;
  if (e.error === "conflict") msg = CONFLICT_MSG[x.why] || "Ye abhi nahi ho sakta";
  if (x.msg) msg = x.msg;                             // config saves carry their own Hinglish reason
  const body = { error: e.error, msg };
  if (x.why) body.why = x.why;
  if (x.field) body.field = x.field;
  if (x.gh_status !== undefined) body.gh_status = x.gh_status;   // the GitHub HTTP status only, never its body
  if (x.flag_id) body.flag_id = x.flag_id;
  if (x.open_day) body.open_day = x.open_day;
  return json(e.status, body, x.allow ? { Allow: x.allow } : null);
}

const bad = (field) => new ApiError(400, "bad_request", { field });

function errType(e) {
  return (e && e.constructor && e.constructor.name) || typeof e;
}

// ── validation helpers ──────────────────────────────────────────────────────────────────────────

export function isDay(s) {
  if (typeof s !== "string" || !DAY_RE.test(s)) return false;
  const t = Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10));
  return new Date(t).toISOString().slice(0, 10) === s;
}

function dayDiff(a, b) {
  return Math.round((Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / 86400000);
}

/** NFC, no \r, no control chars (except \n \t), no bidi overrides, trimmed; ≤ 600 code points. */
export function normNote(v, field = "note") {
  if (v === undefined || v === null) return "";
  if (typeof v !== "string") throw bad(field);
  if (v.length > NOTE_MAX * 8) throw bad(field);
  const s = v.normalize("NFC")
    .replace(/\r/g, "")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F\u202A-\u202E\u2066-\u2069]/g, "")
    .trim();
  if ([...s].length > NOTE_MAX) throw bad(field);
  return s;
}

function posInt(v) {
  return typeof v === "number" && Number.isSafeInteger(v) && v > 0;
}

async function readCapped(request, max) {
  if (!request.body) return new Uint8Array(0);
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > max) {
      try {
        await reader.cancel();
      } catch {
        /* ignore */
      }
      return null;
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.byteLength;
  }
  return out;
}

/** POST guard: JSON media type → same-origin Origin → ≤ `max` bytes (8 KiB) → a JSON object. */
async function readJsonBody(request, url, max = MAX_BODY, tooLarge = null) {
  const ct = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  if (ct !== "application/json") throw new ApiError(415, "unsupported_media_type");
  const origin = request.headers.get("Origin");
  if (!origin || origin !== url.origin) throw new ApiError(403, "forbidden");
  const len = Number(request.headers.get("Content-Length"));
  if (Number.isFinite(len) && len > max) throw new ApiError(413, "payload_too_large", tooLarge);
  const buf = await readCapped(request, max);
  if (buf === null) throw new ApiError(413, "payload_too_large", tooLarge);
  let obj;
  try {
    obj = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(buf));
  } catch {
    throw bad("body");
  }
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) throw bad("body");
  return obj;
}

// ── the open day, from the static site (same file the page reads) ─────────────────────────────────

function cleanIndex(j) {
  if (!j || typeof j !== "object" || j.v !== 1) return null;
  const days = new Set();
  if (Array.isArray(j.days)) for (const x of j.days) if (x && isDay(x.d)) days.add(x.d);
  const openApps = new Map();
  if (j.open_apps && typeof j.open_apps === "object" && !Array.isArray(j.open_apps)) {
    for (const [k, v] of Object.entries(j.open_apps)) {
      if (KEY_RE.test(k)) openApps.set(k, typeof v === "string" ? v.slice(0, 300) : "");
    }
  }
  return {
    open_day: isDay(j.open_day) ? j.open_day : null,
    go_live: isDay(j.go_live) ? j.go_live : null,
    days,
    openApps,
  };
}

/** site/review/index.json through the ASSETS binding; per-isolate cache 60 s. Missing / invalid → null. */
export async function getIndex(env, request) {
  const now = Date.now();
  if (indexCache && now - indexCache.at < (indexCache.val ? INDEX_TTL_MS : INDEX_MISS_TTL_MS)) return indexCache.val;
  let val = null;
  try {
    if (env.ASSETS && typeof env.ASSETS.fetch === "function") {
      const res = await env.ASSETS.fetch(new URL("/review/index.json", request.url).toString());
      if (res && res.status === 200) val = cleanIndex(JSON.parse(await res.text()));
    }
  } catch {
    val = null;
  }
  indexCache = { at: now, val };
  return val;
}

async function readMaybeGzipJson(res) {
  const buf = new Uint8Array(await res.arrayBuffer());
  let text;
  if (buf.length > 2 && buf[0] === 0x1f && buf[1] === 0x8b) {
    const stream = new Response(buf).body.pipeThrough(new DecompressionStream("gzip"));
    text = await new Response(stream).text();
  } else {
    text = new TextDecoder().decode(buf);
  }
  return JSON.parse(text);
}

/** Map key → app label ("name · acct") for snapshot day d, or null if that day's cards cannot be read. */
async function dayApps(env, request, idx, d) {
  if (d === idx.open_day && idx.openApps.size) return idx.openApps;
  if (!idx.days.has(d)) return null;
  if (docCache.has(d)) {
    const hit = docCache.get(d);
    docCache.delete(d);
    docCache.set(d, hit);
    return hit;
  }
  let map = null;
  try {
    const res = await env.ASSETS.fetch(new URL(`/review/days/${d}.json.gz`, request.url).toString());
    if (res && res.status === 200) {
      const doc = await readMaybeGzipJson(res);
      if (doc && doc.day === d && Array.isArray(doc.apps)) {
        map = new Map();
        for (const a of doc.apps) {
          if (!a || !KEY_RE.test(String(a.key))) continue;
          const name = typeof a.name === "string" ? a.name : "";
          const acct = typeof a.acct === "string" ? a.acct : "";
          map.set(a.key, (acct ? `${name} · ${acct}` : name).slice(0, 300));
        }
      }
    }
  } catch {
    map = null;
  }
  if (map) {
    docCache.set(d, map);
    while (docCache.size > DOC_LRU) docCache.delete(docCache.keys().next().value);
  }
  return map;
}

function emptyDay(d, openDay) {
  return { d, open_day: openDay, writable: false, rev: 0, states: {}, notes: [], flags: [], snoozes: [], prev: null, log: [] };
}

// ── handlers ────────────────────────────────────────────────────────────────────────────────────

async function hMe(c) {
  const idx = await getIndex(c.env, c.request);
  return json(200, {
    email: c.email, admin: c.admin, open_day: idx ? idx.open_day : null, go_live: idx ? idx.go_live : null,
    server_time: c.now,
  });
}

async function hDay(c) {
  const d = c.url.searchParams.get("d");
  if (!isDay(d)) throw bad("d");
  const idx = await getIndex(c.env, c.request);
  if (!idx || !idx.open_day) return json(200, emptyDay(d, null));
  const s = await getDayState(c.db, d, idx.open_day);
  const writable = d === idx.open_day || (c.admin && d < idx.open_day && idx.days.has(d));
  return json(200, { d, open_day: idx.open_day, writable, ...s });
}

async function hCalendar(c) {
  const from = c.url.searchParams.get("from");
  const to = c.url.searchParams.get("to");
  if (!isDay(from)) throw bad("from");
  if (!isDay(to) || to < from || dayDiff(from, to) > 400) throw bad("to");
  const idx = await getIndex(c.env, c.request);
  if (!idx || !idx.open_day) return json(200, { days: {} });
  return json(200, { days: await getCalendar(c.db, from, to) });
}

async function hAction(c) {
  const b = c.body;
  const act = b.act;
  if (typeof act !== "string" || !ACTS.has(act)) throw bad("act");
  const d = b.d;
  if (!isDay(d)) throw bad("d");
  const idx = await getIndex(c.env, c.request);
  if (!idx || !idx.open_day) throw new ApiError(409, "review_not_started");

  // `live: true` = sent from the page's "Aaj ka review" (the day it loaded). If a newer snapshot has opened since, the
  // click belongs to a day that is now closed: refuse it (409 day_moved + the new open day) instead of silently
  // turning an admin's click into an "admin sudhaar" on yesterday. History's admin corrections never send `live`.
  if (b.live !== undefined && b.live !== null && typeof b.live !== "boolean") throw bad("live");
  if (b.live === true && d < idx.open_day) throw new ApiError(409, "conflict", { why: "day_moved", open_day: idx.open_day });

  const feature = b.feature === undefined ? null : b.feature;
  if (feature !== null && (typeof feature !== "string" || !FEATS.includes(feature))) throw bad("feature");
  if ((act === "snooze" || act === "unsnooze") && feature === null) throw bad("feature");
  const note = normNote(b.note);
  if (act === "note" && !note) throw bad("note");
  if (act === "snooze" && b.days !== 7 && b.days !== 14) throw bad("days");

  // which day may be written: the open day; admins may correct an older snapshot day (ok/note/undo/bulk_ok)
  const openDay = idx.open_day;
  let adminFix = false;
  if (d !== openDay) {
    if (c.admin && FIX_ACTS.has(act) && d < openDay && idx.days.has(d)) adminFix = true;
    else throw new ApiError(403, "day_closed");
  }
  const labels = await dayApps(c.env, c.request, idx, d);
  if (!labels) throw new ApiError(500, "server_error");

  const a = {
    act, d, openDay, feature, note, days: b.days, who: c.email, at: c.now,
    extra: adminFix ? { admin_fix: 1 } : null, app: null, apps: null, flagId: null, label: "",
  };
  if (act === "bulk_ok") {
    const apps = b.apps;
    if (!Array.isArray(apps) || apps.length < 1 || apps.length > 60) throw bad("apps");
    if (new Set(apps).size !== apps.length) throw bad("apps");
    for (const k of apps) if (typeof k !== "string" || !KEY_RE.test(k) || !labels.has(k)) throw bad("apps");
    a.apps = apps;
  } else if (act === "unflag" && b.flag_id !== undefined && b.flag_id !== null) {
    if (!posInt(b.flag_id)) throw bad("flag_id");
    a.flagId = b.flag_id;
    if (b.app !== undefined && b.app !== null) {
      if (typeof b.app !== "string" || !KEY_RE.test(b.app)) throw bad("app");
      a.app = b.app;
    }
  } else {
    if (typeof b.app !== "string" || !KEY_RE.test(b.app) || !labels.has(b.app)) throw bad("app");
    a.app = b.app;
    a.label = labels.get(b.app) || "";
  }

  const r = await applyAction(c.db, a);
  if (act === "bulk_ok") {
    const states = await getStates(c.db, d, a.apps);
    return json(200, { ok: true, rev: await getRev(c.db), d, changed: r.changed, states });
  }
  const v = await getAppView(c.db, d, r.app, openDay);
  return json(200, { ok: true, rev: v.rev, d, app: r.app, state: v.state, notes: v.notes, flags: v.flags, snoozes: v.snoozes });
}

async function hDecide(c) {
  if (!c.admin) throw new ApiError(403, "admin_only");
  const b = c.body;
  if (!posInt(b.flag_id)) throw bad("flag_id");
  if (typeof b.decision !== "string" || !DECISIONS.has(b.decision)) throw bad("decision");
  const note = normNote(b.note);
  if ((b.decision === "kaam" || b.decision === "band") && !note) throw bad("note");
  // decisions do not need a snapshot: flags live in D1 (log day = open day, else the flag's own day)
  const idx = await getIndex(c.env, c.request);
  const flag = await decideFlag(c.db, {
    flagId: b.flag_id, decision: b.decision, note, who: c.email, at: c.now,
    logDay: idx && idx.open_day ? idx.open_day : null,
  });
  return json(200, { ok: true, rev: await getRev(c.db), flag });
}

const HANDLERS = { me: hMe, day: hDay, calendar: hCalendar, action: hAction, decide: hDecide };

async function api(request, env, url) {
  const name = url.pathname.slice(PREFIX.length);
  if (!Object.prototype.hasOwnProperty.call(ROUTES, name)) throw new ApiError(404, "not_found");
  const method = ROUTES[name];
  if (request.method !== method) throw new ApiError(405, "method_not_allowed", { allow: method });

  const { email } = await verifyAccess(request, env);
  const admin = isAdmin(email, env);
  const body = method === "POST" ? await readJsonBody(request, url) : null;

  const db = env.REVIEW_DB;
  if (!db || typeof db.prepare !== "function" || typeof db.batch !== "function") {
    throw new ApiError(500, "misconfigured");
  }
  try {
    await ensureSchema(db);
  } catch (e) {
    console.error("review-api: schema", errType(e));
    throw new ApiError(503, "db_unavailable");
  }
  return HANDLERS[name]({ request, env, url, email, admin, body, db, now: new Date().toISOString() });
}

// ── Settings saves (/api/config/*; the rules live in config.js) ───────────────────────────────────

async function hConfigStatus(c) {
  return json(200, { server_save: serverSaveReady(c.env), admin: c.admin });
}

/** Admin → strict validation → D1 audit table ready → GitHub commit (sha refetch + retry) → audit row → {ok, sha}. */
async function hConfigSave(c) {
  if (!c.admin) throw new ApiError(403, "admin_only", { msg: CFG_MSG.admin_only });
  const v = validateSave(c.body);
  const db = c.env.REVIEW_DB;
  if (!db || typeof db.prepare !== "function" || typeof db.batch !== "function") throw new ApiError(500, "misconfigured");
  try {
    await ensureSchema(db);
  } catch (e) {
    console.error("config-api: schema", errType(e));
    throw new ApiError(503, "db_unavailable");
  }
  const row = { who: c.email, at: c.now, file: v.file, bytes: v.bytes, result: "ok", commit_sha: null };
  const audit = () => auditSave(db, row, (e) => console.error("config-api: audit", errType(e)));
  let r;
  try {
    const cfg = githubConfig(c.env);
    r = await commitConfig(cfg, v.file, v.text, `${v.file} — saved by ${c.email} via dashboard`);
  } catch (e) {
    row.result = e instanceof ApiError ? e.error : "server_error";
    await audit();
    throw e;
  }
  row.commit_sha = r.sha;
  await audit();
  const out = { ok: true, file: v.file, sha: r.sha };
  if (r.commit_url) out.commit_url = r.commit_url;
  return json(200, out);
}

const CONFIG_HANDLERS = { status: hConfigStatus, save: hConfigSave };

async function configApi(request, env, url) {
  const name = url.pathname.slice(CONFIG_PREFIX.length);
  if (!Object.prototype.hasOwnProperty.call(CONFIG_ROUTES, name)) throw new ApiError(404, "not_found");
  const method = CONFIG_ROUTES[name];
  if (request.method !== method) throw new ApiError(405, "method_not_allowed", { allow: method });

  const { email } = await verifyAccess(request, env);
  const admin = isAdmin(email, env);
  const body = method === "POST" ? await readJsonBody(request, url, CONFIG_MAX_BODY, { msg: CFG_MSG.too_large }) : null;
  return CONFIG_HANDLERS[name]({ request, env, url, email, admin, body, now: new Date().toISOString() });
}

// ── 📌 saved dates (/api/marks; the rules live in db.js) ──────────────────────────────────────

async function hMarksList(c) {
  return json(200, { marks: await listMarks(c.db), me: c.email, admin: c.admin });
}

/** Any logged-in user: a strictly validated mark → D1 (+ its audit row) → {ok, mark, dup, marks}. */
async function hMarksAdd(c) {
  const m = validateMark(c.body, c.now);
  const r = await addMark(c.db, m, c.email, c.now);
  return json(200, { ok: true, mark: r.mark, dup: r.dup, marks: await listMarks(c.db) });
}

/** The mark's author or an admin → marked deleted (+ its audit row) → {ok, id, marks}. */
async function hMarksDelete(c) {
  const id = validateDelete(c.body);
  await deleteMark(c.db, id, c.email, c.admin, c.now);
  return json(200, { ok: true, id, marks: await listMarks(c.db) });
}

async function marksApi(request, env, url) {
  const sub = url.pathname.slice(MARKS_PATH.length);
  if (!Object.prototype.hasOwnProperty.call(MARKS_ROUTES, sub)) throw new ApiError(404, "not_found");
  const allow = MARKS_ROUTES[sub];
  if (!allow.includes(request.method)) throw new ApiError(405, "method_not_allowed", { allow: allow.join(", ") });

  const { email } = await verifyAccess(request, env);
  const admin = isAdmin(email, env);
  const body = request.method === "POST" ? await readJsonBody(request, url, MAX_BODY, { msg: "Request bahut badi hai" }) : null;

  const db = env.REVIEW_DB;
  if (!db || typeof db.prepare !== "function" || typeof db.batch !== "function") {
    throw new ApiError(500, "misconfigured");
  }
  try {
    await ensureSchema(db);
  } catch (e) {
    console.error("marks-api: schema", errType(e));
    throw new ApiError(503, "db_unavailable");
  }
  const c = { request, env, url, email, admin, body, db, now: new Date().toISOString() };
  if (request.method === "GET") return hMarksList(c);
  return sub === "/delete" ? hMarksDelete(c) : hMarksAdd(c);
}

async function route(request, env) {
  const url = new URL(request.url);
  const p = url.pathname;
  if (p.startsWith(PREFIX)) return api(request, env, url);
  if (p.startsWith(CONFIG_PREFIX)) return configApi(request, env, url);
  if (p === MARKS_PATH || p.startsWith(MARKS_PATH + "/")) return marksApi(request, env, url);
  if (p === "/api" || p.startsWith("/api/")) throw new ApiError(404, "not_found");
  if (env && env.ASSETS && typeof env.ASSETS.fetch === "function") return env.ASSETS.fetch(request);
  throw new ApiError(404, "not_found");
}

export default {
  async fetch(request, env, ctx) {
    try {
      return await route(request, env || {}, ctx);
    } catch (e) {
      if (e instanceof ApiError) return errorResponse(e);
      console.error("review-api: error", errType(e));
      return errorResponse(new ApiError(500, "server_error"));
    }
  },
};
