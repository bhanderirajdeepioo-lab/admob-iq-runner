// Settings saves through the dashboard Worker: POST /api/config/save and GET /api/config/status.
//
// The Settings screen (account names, app names, app selection) and the Baseline approvals used to commit
// config/<file>.json to the PRIVATE repo straight from the browser, with a GitHub token kept in localStorage. Now the
// page sends the file here: index.js verifies the Access login (JWT), the same-origin JSON POST rules and the admin
// list, this file validates the content strictly and commits it with the Worker's own GITHUB_TOKEN (a Cloudflare
// Secret that only the owner sets) to the repo named by the CONFIG_REPO var.
//
// Secrets: the token is only ever placed in the Authorization header of the GitHub request. It is never logged and
// never returned, and no GitHub response body is passed on: only a validated commit sha / commit URL is read from it.

import { ApiError } from "./auth.js";

export const CONFIG_FILES = ["account_names", "app_names", "selected_apps", "approved_ranges"];
export const CONFIG_MAX_BYTES = 256 * 1024;        // every file, as written (JSON.stringify(obj, null, 1), UTF-8)
export const GH_USER_AGENT = "admob-iq-dashboard";
export const GH_RETRIES = 3;                       // 409 / 422 on the PUT → refetch the sha and retry, up to 3 times

const GH_API = "https://api.github.com";
const PUB_RE = /^pub-\d{1,24}$/;
const APP_RE = /^ca-app-pub-(\d{1,24})~\d{1,24}$/;
const REPO_RE = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\/[A-Za-z0-9._-]{1,100}$/;
const SHA_RE = /^[0-9a-f]{40}$/;
const COMMIT_URL_RE = /^https:\/\/github\.com\/[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+\/commit\/[0-9a-f]{40}$/;
const CTRL_RE = /[\u0000-\u001F\u007F-\u009F\u202A-\u202E\u2066-\u2069]/;
const CTRL_RE_G = new RegExp(CTRL_RE.source, "g");
const REPO_PLACEHOLDER = "owner/private-repo";   // the value in wrangler.example.toml (an unedited copy saves nothing)

/** Hinglish toast text for every config-save error (the page shows it with the HTTP status). */
export const CFG_MSG = {
  admin_only: "Sirf admin settings badal sakta hai",
  token_missing: "GitHub token abhi Cloudflare me nahi daala",
  repo_missing: "Config repo (CONFIG_REPO) abhi Cloudflare me set nahi",
  github_auth: "GitHub token expire/galat",
  github_forbidden: "Token ko repo me likhne ki permission nahi",
  github_conflict: "Kisi aur ne abhi save kiya — dobara try karo",
  github_unavailable: "GitHub se jud nahi paaye — thodi der baad try karo",
  too_large: "File bahut badi hai (256 KB tak)",
};

// ── config (vars + secret) ──────────────────────────────────────────────────────────────────────

function repoOf(env) {
  const r = String((env && env.CONFIG_REPO) || "").trim();
  return REPO_RE.test(r) && r.toLowerCase() !== REPO_PLACEHOLDER ? r : null;
}

function tokenOf(env) {
  const t = env && env.GITHUB_TOKEN;
  return typeof t === "string" && t.trim() ? t.trim() : null;
}

/** GET /api/config/status: can this Worker save (token + repo set)? */
export function serverSaveReady(env) {
  return Boolean(tokenOf(env) && repoOf(env));
}

/** {token, repo} or 503 with the Hinglish reason (token first: that is the one the owner must add). */
export function githubConfig(env) {
  const token = tokenOf(env);
  if (!token) throw new ApiError(503, "token_missing", { msg: CFG_MSG.token_missing });
  const repo = repoOf(env);
  if (!repo) throw new ApiError(503, "repo_missing", { msg: CFG_MSG.repo_missing });
  return { token, repo };
}

// ── validation (400 with a Hinglish reason; the size cap is 413) ─────────────────────────────────

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const show = (s) => JSON.stringify(String(s).replace(CTRL_RE_G, "").slice(0, 48));
const invalid = (msg) => new ApiError(400, "bad_request", { field: "content", msg });

function checkName(v, max) {
  if (typeof v !== "string" || CTRL_RE.test(v) || !v.trim()) return false;
  const n = [...v].length;
  return n >= 1 && n <= max;
}

function vAccountNames(c) {
  if (!isObj(c)) throw invalid("account_names ek object hona chahiye: {\"pub-…\": \"naam\"}");
  for (const [k, v] of Object.entries(c)) {
    if (!PUB_RE.test(k)) throw invalid(`Account id galat: ${show(k)} (pub-<digits> hona chahiye)`);
    if (!checkName(v, 60)) throw invalid(`${show(k)} ka naam 1–60 akshar ka text hona chahiye`);
  }
}

function vAppNames(c) {
  if (!isObj(c)) throw invalid("app_names ek object hona chahiye: {\"ca-app-pub-…~…\": \"naam\"}");
  for (const [k, v] of Object.entries(c)) {
    if (!APP_RE.test(k)) throw invalid(`App id galat: ${show(k)} (ca-app-pub-<digits>~<digits> hona chahiye)`);
    if (!checkName(v, 80)) throw invalid(`${show(k)} ka naam 1–80 akshar ka text hona chahiye`);
  }
}

function vSelectedApps(c) {
  if (!isObj(c) || Object.keys(c).length !== 1 || !isObj(c.accounts)) {
    throw invalid("selected_apps me sirf \"accounts\" (object) hona chahiye");
  }
  for (const [acc, a] of Object.entries(c.accounts)) {
    if (!PUB_RE.test(acc)) throw invalid(`Account id galat: ${show(acc)} (pub-<digits> hona chahiye)`);
    const keys = isObj(a) ? Object.keys(a).sort().join(",") : "";
    if (keys !== "decided,selected" || typeof a.decided !== "boolean" || !Array.isArray(a.selected)) {
      throw invalid(`${show(acc)}: sirf decided (true/false) aur selected (app id list) chahiye`);
    }
    for (const id of a.selected) {
      const m = typeof id === "string" ? APP_RE.exec(id) : null;
      if (!m) throw invalid(`${show(acc)} me app id galat: ${show(id)}`);
      if ("pub-" + m[1] !== acc) throw invalid(`App ${show(id)} account ${show(acc)} ki nahi hai (publisher id alag)`);
    }
  }
}

function vApprovedRanges(c) {
  // Structural check only (the shape is owned by admob_iq/engine/approvals.py, old flat entries included).
  if (!isObj(c) || Object.keys(c).length !== 1 || !isObj(c.placements)) {
    throw invalid("approved_ranges me sirf \"placements\" (object) hona chahiye");
  }
  for (const [uid, p] of Object.entries(c.placements)) {
    if (!uid || uid.length > 200 || CTRL_RE.test(uid)) throw invalid(`Placement id galat: ${show(uid)}`);
    if (!isObj(p)) throw invalid(`Placement ${show(uid)} ek object hona chahiye`);
    for (const f of ["metrics", "range", "countries"]) {
      if (p[f] !== undefined && !isObj(p[f])) throw invalid(`Placement ${show(uid)}: "${f}" object hona chahiye`);
    }
    for (const [cc, cv] of Object.entries(p.countries || {})) {
      if (!isObj(cv)) throw invalid(`Placement ${show(uid)}: country ${show(cc)} object hona chahiye`);
    }
  }
}

const VALIDATORS = {
  account_names: vAccountNames, app_names: vAppNames, selected_apps: vSelectedApps, approved_ranges: vApprovedRanges,
};

/**
 * The request body {file, content} → {file, text, bytes}: `text` is exactly what gets committed.
 * @throws {ApiError} 400 bad_request (Hinglish reason in msg) · 413 payload_too_large
 */
export function validateSave(body) {
  for (const k of Object.keys(body)) {
    if (k !== "file" && k !== "content") throw new ApiError(400, "bad_request", { field: "body" });
  }
  const file = body.file;
  if (typeof file !== "string" || !Object.prototype.hasOwnProperty.call(VALIDATORS, file)) {
    throw new ApiError(400, "bad_request", { field: "file", msg: "Galat file — " + CONFIG_FILES.join(" / ") + " me se ek" });
  }
  VALIDATORS[file](body.content);
  const text = JSON.stringify(body.content, null, 1);
  const bytes = new TextEncoder().encode(text).length;
  if (bytes > CONFIG_MAX_BYTES) throw new ApiError(413, "payload_too_large", { msg: CFG_MSG.too_large });
  return { file, text, bytes };
}

// ── GitHub contents API ─────────────────────────────────────────────────────────────────────────

function b64utf8(text) {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

async function discard(res) {
  try {
    if (res && res.body) await res.body.cancel();
  } catch {
    /* ignore */
  }
}

/** Only the status of a failed GitHub call is kept (never its body). */
function ghError(status) {
  const x = { gh_status: status || 0 };
  if (status === 401) return new ApiError(502, "github_auth", { ...x, msg: CFG_MSG.github_auth });
  if (status === 403 || status === 404) return new ApiError(502, "github_forbidden", { ...x, msg: CFG_MSG.github_forbidden });
  if (status === 409 || status === 422) return new ApiError(409, "github_conflict", { ...x, msg: CFG_MSG.github_conflict });
  return new ApiError(502, "github_unavailable", { ...x, msg: CFG_MSG.github_unavailable });
}

async function gh(cfg, url, method, payload) {
  const headers = {
    Authorization: "Bearer " + cfg.token,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": GH_USER_AGENT,
  };
  if (payload) headers["Content-Type"] = "application/json";
  try {
    return await fetch(url, { method, headers, body: payload ? JSON.stringify(payload) : undefined });
  } catch {
    throw ghError(0);   // network failure; the thrown error (which could mention the request) is dropped
  }
}

/** The file's current blob sha, or null when it does not exist yet (GitHub 404). */
async function currentSha(cfg, url) {
  const res = await gh(cfg, url, "GET");
  if (res.status === 404) {
    await discard(res);
    return null;
  }
  if (res.status !== 200) {
    await discard(res);
    throw ghError(res.status);
  }
  let j = null;
  try {
    j = await res.json();
  } catch {
    j = null;
  }
  if (!isObj(j) || typeof j.sha !== "string" || !SHA_RE.test(j.sha)) throw ghError(502);
  return j.sha;
}

/**
 * Commit `text` to config/<file>.json in CONFIG_REPO: GET the sha (404 = new file) → PUT; a 409 / 422 answer means
 * the file changed in between, so the sha is fetched again and the PUT retried (up to GH_RETRIES times).
 * @returns {Promise<{sha: string|null, commit_url: string|null}>}
 * @throws {ApiError} 502 github_auth / github_forbidden / github_unavailable · 409 github_conflict
 */
export async function commitConfig(cfg, file, text, message) {
  const url = `${GH_API}/repos/${cfg.repo}/contents/config/${file}.json`;
  const content = b64utf8(text);
  for (let attempt = 0; ; attempt++) {
    const sha = await currentSha(cfg, url);
    const res = await gh(cfg, url, "PUT", sha ? { message, content, sha } : { message, content });
    if (res.status === 200 || res.status === 201) {
      let j = null;
      try {
        j = await res.json();
      } catch {
        j = null;
      }
      const commit = isObj(j) && isObj(j.commit) ? j.commit : {};
      return {
        sha: typeof commit.sha === "string" && SHA_RE.test(commit.sha) ? commit.sha : null,
        commit_url: typeof commit.html_url === "string" && COMMIT_URL_RE.test(commit.html_url) ? commit.html_url : null,
      };
    }
    await discard(res);
    if ((res.status === 409 || res.status === 422) && attempt < GH_RETRIES) continue;
    throw ghError(res.status);
  }
}

// ── audit (D1 table config_log; created by db.js SCHEMA / MIGRATIONS[3]) ─────────────────────────

/** Append one save attempt. Never throws: a failed audit write must not hide a commit that already happened. */
export async function auditSave(db, row, onError) {
  try {
    await db.prepare("INSERT INTO config_log (who, at, file, bytes, result, commit_sha) VALUES (?, ?, ?, ?, ?, ?)")
      .bind(row.who, row.at, row.file, row.bytes, row.result, row.commit_sha || null)
      .run();
  } catch (e) {
    if (onError) onError(e);
  }
}
