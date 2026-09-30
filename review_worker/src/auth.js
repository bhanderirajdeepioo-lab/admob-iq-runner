// Cloudflare Access JWT verification for the Review API. FAILS CLOSED: any doubt → no data.
//
// Access already guards the whole host at the edge, but this Worker never trusts that alone
// (owner rule: the AdMob data must never become public, e.g. through a mis-set route or a
// workers.dev / preview URL). Every /api/review/* request must carry an Access JWT that this file
// verifies itself: RS256 signature against the team's JWKS, then iss, aud, exp/nbf/iat and email.
//
// Runtime: WebCrypto + fetch only (no dependencies). Nothing here logs a token, email or claim.

export class ApiError extends Error {
  /** @param {number} status  @param {string} error  @param {object} [extra] {why, field, flag_id} */
  constructor(status, error, extra) {
    super(error);
    this.name = "ApiError";
    this.status = status;
    this.error = error;
    this.extra = extra || null;
  }
}

const JWKS_TTL_MS = 10 * 60 * 1000;   // JWKS cached per isolate for 10 min
const REFETCH_MIN_MS = 30 * 1000;     // unknown kid → at most one forced refetch per 30 s
const SKEW_S = 60;                    // clock skew allowed on exp / nbf / iat
const MAX_TOKEN_LEN = 16384;
const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]{1,190}$/;
const B64URL_RE = /^[A-Za-z0-9_-]+$/;
const DOMAIN_RE = /^[a-z0-9-]+(\.[a-z0-9-]+)+$/;
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const PLACEHOLDERS = new Set(["ACCESS_TEAM_DOMAIN", "ACCESS_AUD"]);   // an unedited example config

let jwksCache = null;   // {domain, fetchedAt, keys: Map<kid, {jwk, key}>}
let inflight = null;    // one JWKS fetch at a time per isolate

const unauthorized = () => new ApiError(401, "unauthorized");

/** Test-only: forget the cached JWKS. */
export function _resetAuthForTests() {
  jwksCache = null;
  inflight = null;
}

/** ACCESS_TEAM_DOMAIN / ACCESS_AUD from the Worker vars. Missing or placeholder → 500 misconfigured. */
export function accessConfig(env) {
  const rawDomain = String((env && env.ACCESS_TEAM_DOMAIN) || "").trim();
  const aud = String((env && env.ACCESS_AUD) || "").trim();
  const domain = rawDomain.toLowerCase().replace(/^https?:\/\//, "").replace(/\/+$/, "");
  if (!domain || !aud || PLACEHOLDERS.has(rawDomain) || PLACEHOLDERS.has(aud) || !DOMAIN_RE.test(domain)) {
    throw new ApiError(500, "misconfigured");
  }
  return { domain, aud };
}

/** The raw token: header Cf-Access-Jwt-Assertion, else cookie CF_Authorization. */
export function readToken(request) {
  const h = request.headers.get("Cf-Access-Jwt-Assertion");
  if (h && h.trim()) return h.trim();
  const cookie = request.headers.get("Cookie") || "";
  for (const part of cookie.split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    if (part.slice(0, i).trim() === "CF_Authorization") {
      const v = part.slice(i + 1).trim();
      if (v) return v;
    }
  }
  return null;
}

function b64urlBytes(s) {
  if (typeof s !== "string" || !B64URL_RE.test(s) || s.length % 4 === 1) throw unauthorized();
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  let bin;
  try {
    bin = atob(b64);
  } catch {
    throw unauthorized();
  }
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function b64urlJson(s) {
  let v;
  try {
    v = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(b64urlBytes(s)));
  } catch {
    throw unauthorized();
  }
  if (!v || typeof v !== "object" || Array.isArray(v)) throw unauthorized();
  return v;
}

/** {keys:[…]} → Map kid → {jwk, key:null}. Only RSA signing keys usable with RS256. */
function jwkMap(set) {
  const out = new Map();
  const keys = set && Array.isArray(set.keys) ? set.keys : [];
  for (const k of keys) {
    if (!k || typeof k !== "object" || k.kty !== "RSA") continue;
    if (typeof k.kid !== "string" || !k.kid || typeof k.n !== "string" || typeof k.e !== "string") continue;
    if (k.alg !== undefined && k.alg !== "RS256") continue;
    if (k.use !== undefined && k.use !== "sig") continue;
    out.set(k.kid, { jwk: { kty: "RSA", n: k.n, e: k.e }, key: null });
  }
  return out;
}

async function refreshJwks(cfg) {
  if (inflight) return inflight;
  inflight = (async () => {
    let res;
    try {
      res = await fetch(`https://${cfg.domain}/cdn-cgi/access/certs`, { headers: { accept: "application/json" } });
    } catch {
      throw new ApiError(503, "auth_unavailable");
    }
    if (!res || !res.ok) throw new ApiError(503, "auth_unavailable");
    let body;
    try {
      body = await res.json();
    } catch {
      throw new ApiError(503, "auth_unavailable");
    }
    const keys = jwkMap(body);
    if (!keys.size) throw new ApiError(503, "auth_unavailable");
    jwksCache = { domain: cfg.domain, fetchedAt: Date.now(), keys };
    return jwksCache;
  })();
  try {
    return await inflight;
  } finally {
    inflight = null;
  }
}

async function importJwk(jwk) {
  try {
    return await crypto.subtle.importKey(
      "jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
  } catch {
    throw unauthorized();
  }
}

async function findKey(kid, cfg, env, request) {
  // TEST ONLY: a fixed JWKS from the env, honoured ONLY when the request itself is for localhost
  // (wrangler dev / node tests). On the real host this var is ignored and the team JWKS is fetched.
  if (env && env.ACCESS_JWKS_JSON && LOCAL_HOSTS.has(new URL(request.url).hostname)) {
    let set;
    try {
      set = JSON.parse(String(env.ACCESS_JWKS_JSON));
    } catch {
      throw new ApiError(500, "misconfigured");
    }
    const entry = jwkMap(set).get(kid);
    if (!entry) throw unauthorized();
    return importJwk(entry.jwk);
  }
  const now = Date.now();
  let c = jwksCache;
  if (!c || c.domain !== cfg.domain || now - c.fetchedAt >= JWKS_TTL_MS) c = await refreshJwks(cfg);
  let entry = c.keys.get(kid);
  if (!entry && now - c.fetchedAt >= REFETCH_MIN_MS) {   // key rotation: one forced refetch per 30 s
    c = await refreshJwks(cfg);
    entry = c.keys.get(kid);
  }
  if (!entry) throw unauthorized();
  if (!entry.key) entry.key = await importJwk(entry.jwk);
  return entry.key;
}

function checkClaims(p, cfg) {
  const now = Math.floor(Date.now() / 1000);
  if (p.iss !== "https://" + cfg.domain) throw unauthorized();
  const auds = typeof p.aud === "string" ? [p.aud] : Array.isArray(p.aud) ? p.aud : [];
  if (!auds.includes(cfg.aud)) throw unauthorized();
  if (typeof p.exp !== "number" || !Number.isFinite(p.exp) || !(p.exp > now - SKEW_S)) throw unauthorized();
  if (p.nbf !== undefined && (typeof p.nbf !== "number" || !(p.nbf <= now + SKEW_S))) throw unauthorized();
  if (p.iat !== undefined && (typeof p.iat !== "number" || !(p.iat <= now + SKEW_S))) throw unauthorized();
  if (typeof p.email !== "string" || !EMAIL_RE.test(p.email)) throw unauthorized();   // service tokens: no email
  return p.email.toLowerCase();
}

/**
 * Verify the Access JWT of this request.
 * @returns {Promise<{email: string}>}  lower-cased verified email
 * @throws {ApiError} 401 unauthorized · 500 misconfigured · 503 auth_unavailable
 */
export async function verifyAccess(request, env) {
  const token = readToken(request);
  if (!token) throw unauthorized();
  const cfg = accessConfig(env);
  if (token.length > MAX_TOKEN_LEN) throw unauthorized();
  const parts = token.split(".");
  if (parts.length !== 3 || parts.some((x) => !x)) throw unauthorized();
  const header = b64urlJson(parts[0]);
  if (header.alg !== "RS256") throw unauthorized();                 // never none / HS* / anything else
  if (typeof header.kid !== "string" || !header.kid || header.kid.length > 256) throw unauthorized();
  if (header.crit !== undefined) throw unauthorized();              // no critical extensions supported
  const payload = b64urlJson(parts[1]);
  const sig = b64urlBytes(parts[2]);
  const key = await findKey(header.kid, cfg, env, request);
  let ok = false;
  try {
    ok = await crypto.subtle.verify(
      { name: "RSASSA-PKCS1-v1_5" }, key, sig, new TextEncoder().encode(parts[0] + "." + parts[1]));
  } catch {
    ok = false;
  }
  if (!ok) throw unauthorized();
  return { email: checkClaims(payload, cfg) };
}

/** ADMIN_EMAILS (comma / space list) contains this verified email. */
export function isAdmin(email, env) {
  if (!email) return false;
  return String((env && env.ADMIN_EMAILS) || "")
    .split(/[,\s]+/)
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s.includes("@"))
    .includes(String(email).toLowerCase());
}
