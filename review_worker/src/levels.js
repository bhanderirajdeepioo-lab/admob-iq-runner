// 📉 CPI vs eCPM levels: the owner's level actions through the dashboard Worker — GET /api/levels, POST /api/levels/act.
//
// The page's History tab (Levels block) lets an admin set a level from named days or a typed value, go back to any
// earlier level, reject an automatic acceptance, accept a proposed level, go back to the automatic rule, and undo any
// of these. Each click is ONE action appended to config/cpi_levels.json in the PRIVATE repo (CONFIG_REPO, with the
// Worker's GITHUB_TOKEN secret, as config.js does for Settings); the next build reads the file and applies it
// (admob_iq/cpi_build.py resolve_actions). The file is append-only: an action is never edited or removed (undo is a
// new action), and a conflicting write re-reads the file and appends again — a concurrent action is never lost.
// Every action is audited in D1 (lv_log). It is not one of CONFIG_FILES: a whole-file Settings save could rewrite it.
//
// Secrets: as config.js — the token only in the Authorization header, never logged, never returned.

import { ApiError } from "./auth.js";
import { CFG_MSG, CTRL_RE, githubConfig, readConfig, putConfig, serverSaveReady } from "./config.js";

export const LEVELS_FILE = "cpi_levels";
// LIMIT: append-only with no compaction — at 256 KiB every new action is refused (413 too_large) until old ones are archived by hand
export const LEVELS_MAX_BYTES = 256 * 1024;        // the file after the append, as written (JSON, indent 1)
export const LEVELS_RETRIES = 3;                   // a conflicting PUT → re-read + re-append, up to 3 times
export const LEVELS_CACHE_MS = 30 * 1000;          // GET /api/levels: per isolate
export const ACTS = ["set", "rollback", "reject", "accept", "auto", "undo"];
export const FAMS = ["CPI", "ECPM", "GAP", "IPU", "ROAS_G", "ROAS_C0", "ROAS_C1", "ROAS_C7", "SPEND"];
export const NOTE_MAX = 200;
export const DAYS_MIN = 7;
export const DAYS_MAX = 120;
export const PAST_DAYS = 1500;

const APP_RE = /^ca-app-pub-\d{1,24}~\d{1,24}$/;
const LEVEL_RE = /^L-[0-9a-f]{10}$/;
const REF_RE = /^a-[0-9a-f]{12}$/;
const DAY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const IST_MS = 330 * 60 * 1000;

/** The keys each act may carry (beyond act / note); anything else is a 400. */
const KEYS = {
  set: ["app", "fam", "from", "days", "value"],
  rollback: ["app", "fam", "from", "level"],
  reject: ["app", "fam", "level"],
  accept: ["app", "fam", "from", "proposal"],
  auto: ["app", "fam", "from"],
  undo: ["ref"],
};

/** Hinglish text for every level error (the page shows it with the HTTP status, as the Settings toasts). */
export const LV_MSG = {
  admin_only: "Sirf admin level badal sakta hai",
  levels_broken: "Level file kharab hai — kuch save nahi hua, admin ko batao",
  unknown_ref: "Ye action nahi mila — page reload karo",
  already_undone: "Ye action pehle hi undo ho chuka hai",
  too_large: "Level history bahut badi ho gayi (256 KB tak)",
};

let cache = null;   // {at, repo, actions}

/** TEST ONLY: drop the per-isolate cache. */
export function _resetLevelsForTests() {
  cache = null;
}

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const invalid = (field, msg) => new ApiError(400, "bad_request", { field, msg });

function realDay(s) {
  const m = typeof s === "string" ? DAY_RE.exec(s) : null;
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3];
}

function dayDiff(a, b) {
  return Math.round((Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / 86400000);
}

/** Today's date in IST (the page's dates are IST). */
export function todayIst(nowIso) {
  return new Date(Date.parse(nowIso) + IST_MS).toISOString().slice(0, 10);
}

function checkDay(v, field, today) {
  if (!realDay(v)) throw invalid(field, `${field}: YYYY-MM-DD wali sahi date chahiye`);
  if (v > today) throw invalid(field, `${field}: aaj (IST) ke baad ki date nahi chalegi`);
  if (dayDiff(v, today) > PAST_DAYS) throw invalid(field, `${field}: ${PAST_DAYS} din se purani date nahi chalegi`);
}

function checkDays(v, field, today, upTo) {
  if (!Array.isArray(v) || v.length !== 2) throw invalid(field, `${field}: [pehla din, aakhri din] chahiye`);
  checkDay(v[0], field, today);
  checkDay(v[1], field, today);
  const n = dayDiff(v[0], v[1]) + 1;
  if (n < DAYS_MIN || n > DAYS_MAX) throw invalid(field, `${field}: ${DAYS_MIN} se ${DAYS_MAX} din chuno`);
  if (upTo && v[1] > upTo) throw invalid(field, `${field}: aakhri din "from" ke baad nahi ho sakta`);
}

/** NFC + trim; at most NOTE_MAX characters, no control / bidi character (a 400 instead of a silent strip). */
export function normLevelNote(v) {
  if (v === undefined || v === null) return "";
  if (typeof v !== "string") throw invalid("note", "Note text hona chahiye");
  const s = v.normalize("NFC").trim();
  if (CTRL_RE.test(s)) throw invalid("note", "Note me control / direction wale akshar nahi chalenge");
  if ([...s].length > NOTE_MAX) throw invalid("note", `Note ${NOTE_MAX} akshar tak`);
  return s;
}

/**
 * The request body → the action without id / at / by (the Worker adds those). Strict: only the act's own keys.
 * @throws {ApiError} 400 bad_request with field + a Hinglish msg
 */
export function validateAction(body, nowIso) {
  const act = body.act;
  if (typeof act !== "string" || !ACTS.includes(act)) throw invalid("act", "act: " + ACTS.join(" / ") + " me se ek");
  const allowed = new Set(["act", "note", ...KEYS[act]]);
  for (const k of Object.keys(body)) if (!allowed.has(k)) throw invalid(k, `"${String(k).slice(0, 24)}" is action me nahi chalta`);
  const today = todayIst(nowIso);
  const out = { act };
  if (act === "undo") {
    if (typeof body.ref !== "string" || !REF_RE.test(body.ref)) throw invalid("ref", "ref: a-<12 hex> chahiye");
    out.ref = body.ref;
  } else {
    if (typeof body.app !== "string" || !APP_RE.test(body.app)) throw invalid("app", "App id galat (ca-app-pub-<digits>~<digits>)");
    if (typeof body.fam !== "string" || !FAMS.includes(body.fam)) throw invalid("fam", "fam: " + FAMS.join(" / ") + " me se ek");
    out.app = body.app;
    out.fam = body.fam;
    if (act !== "reject") {
      checkDay(body.from, "from", today);
      out.from = body.from;
    }
  }
  if (act === "set") {
    const hasDays = body.days !== undefined && body.days !== null;
    const hasValue = body.value !== undefined && body.value !== null;
    if (hasDays === hasValue) throw invalid("days", "Ya din chuno ya value likho — dono ek saath nahi");
    if (hasDays) {
      checkDays(body.days, "days", today, body.from);
      out.days = [body.days[0], body.days[1]];
    } else {
      const v = body.value;
      if (typeof v !== "number" || !Number.isFinite(v) || v <= 0 || v >= 1e9) throw invalid("value", "Value 0 se badi number honi chahiye");
      out.value = v;
    }
  }
  if (act === "rollback" || act === "reject") {
    if (typeof body.level !== "string" || !LEVEL_RE.test(body.level)) throw invalid("level", "level: L-<10 hex> chahiye");
    out.level = body.level;
  }
  if (act === "accept") {
    const p = body.proposal;
    if (!isObj(p) || Object.keys(p).sort().join(",") !== "day,days") throw invalid("proposal", "proposal: {day, days} chahiye");
    checkDay(p.day, "proposal", today);
    checkDays(p.days, "proposal", today, body.from);
    out.proposal = { day: p.day, days: [p.days[0], p.days[1]] };
  }
  const note = normLevelNote(body.note);
  if (note) out.note = note;
  return out;
}

/** The file's text → its actions; anything but {v: 1, actions: [objects]} is broken (nothing gets written). */
function parseFile(text) {
  // LIMIT: null = a GitHub 404 = "no file yet"; a wrong repo / branch or a token without access answers 404 too (not told apart)
  if (text === null) return [];
  let j;
  try {
    j = typeof text === "string" ? JSON.parse(text) : null;
  } catch {
    j = null;
  }
  if (!isObj(j) || j.v !== 1 || !Array.isArray(j.actions) || !j.actions.every(isObj)) {
    throw new ApiError(409, "levels_broken", { msg: LV_MSG.levels_broken });
  }
  return j.actions;
}

function randomId() {
  const b = new Uint8Array(6);
  crypto.getRandomValues(b);
  return "a-" + [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
}

/** An undo must name an action that exists, is not itself an undo, and is not undone yet (409 otherwise). */
function checkUndo(actions, ref) {
  const hit = actions.find((a) => a && a.id === ref);
  if (!hit || hit.act === "undo") throw new ApiError(409, "conflict", { why: "unknown_ref", msg: LV_MSG.unknown_ref });
  if (actions.some((a) => a && a.act === "undo" && a.ref === ref)) {
    throw new ApiError(409, "conflict", { why: "already_undone", msg: LV_MSG.already_undone });
  }
}

/** GET /api/levels (admin): {actions, me, admin, server_save}; the file read through the contents API, cached 30 s. */
export async function levelsList(c) {
  if (!c.admin) throw new ApiError(403, "admin_only", { msg: LV_MSG.admin_only });
  const ready = serverSaveReady(c.env);
  let actions = [];
  if (ready) {
    const cfg = githubConfig(c.env);
    const now = Date.now();
    if (cache && cache.repo === cfg.repo && now - cache.at < LEVELS_CACHE_MS) {
      actions = cache.actions;
    } else {
      const r = await readConfig(cfg, LEVELS_FILE);
      actions = parseFile(r.text);
      cache = { at: now, repo: cfg.repo, actions };
    }
  }
  return { actions, me: c.email, admin: true, server_save: ready };
}

/**
 * POST /api/levels/act (admin): one validated action → appended to config/cpi_levels.json → {ok, action, actions,
 * commit_url?}. by = the verified Access email (never from the body), at = server time, id = a-<12 random hex>.
 * A conflicting write re-reads the file and appends to the NEW content (up to LEVELS_RETRIES), then github_conflict.
 * @param {{env, email, admin, body, now, audit: (row) => Promise<void>}} c
 */
export async function levelsAct(c) {
  if (!c.admin) throw new ApiError(403, "admin_only", { msg: LV_MSG.admin_only });
  const v = validateAction(c.body, c.now);
  const row = { at: c.now, who: c.email, act: v.act, app: v.app || null, fam: v.fam || null, action_id: null,
    result: "ok", commit_sha: null };
  try {
    const cfg = githubConfig(c.env);
    const action = { id: randomId(), at: c.now, by: String(c.email).toLowerCase(), ...v };
    row.action_id = action.id;
    for (let attempt = 0; ; attempt++) {
      const cur = await readConfig(cfg, LEVELS_FILE);
      const actions = parseFile(cur.text);
      if (v.act === "undo") {
        const ref = actions.find((a) => a && a.id === v.ref && a.act !== "undo");
        row.app = ref ? ref.app || null : null;
        row.fam = ref ? ref.fam || null : null;
        checkUndo(actions, v.ref);
      }
      const next = [...actions, action];
      const text = JSON.stringify({ v: 1, actions: next }, null, 1);
      // LIMIT: the 256 KiB cap above — no compaction, so a full file stays full (the page shows LV_MSG.too_large)
      if (new TextEncoder().encode(text).length > LEVELS_MAX_BYTES) {
        throw new ApiError(413, "payload_too_large", { msg: LV_MSG.too_large });
      }
      let r;
      try {
        r = await putConfig(cfg, LEVELS_FILE, text, `cpi_levels — ${v.act} by ${c.email} via dashboard`, cur.sha);
      } catch (e) {
        if (e instanceof ApiError && e.error === "github_conflict" && attempt < LEVELS_RETRIES) continue;
        throw e;
      }
      row.commit_sha = r.sha;
      cache = { at: Date.now(), repo: cfg.repo, actions: next };
      await c.audit(row);
      const out = { ok: true, action, actions: next };
      if (r.commit_url) out.commit_url = r.commit_url;
      return out;
    }
  } catch (e) {
    row.result = e instanceof ApiError ? (e.extra && e.extra.why) || e.error : "server_error";
    await c.audit(row);
    throw e;
  }
}

/** Append one lv_log row. Never throws: a failed audit write must not hide a commit that already happened. */
export async function auditLevel(db, row, onError) {
  try {
    await db.prepare("INSERT INTO lv_log (at, who, act, app, fam, action_id, result, commit_sha) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
      .bind(row.at, row.who, row.act, row.app, row.fam, row.action_id, row.result, row.commit_sha || null)
      .run();
  } catch (e) {
    if (onError) onError(e);
  }
}

export { CFG_MSG };
