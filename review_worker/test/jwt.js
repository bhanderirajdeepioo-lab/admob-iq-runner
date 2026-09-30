// Test-only RSA keys and Access-style JWTs (WebCrypto). Nothing here is a real key or a real identity.

export const TEAM = "team.example.test";
export const AUD = "aud-test";
export const OWNER = "owner@example.test";
export const TEAMMATE = "team@example.test";

const enc = new TextEncoder();

export function b64url(input) {
  const bytes = typeof input === "string" ? enc.encode(input) : new Uint8Array(input);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** A fresh RS256 key pair: {kid, privateKey, publicKey, jwk (public, with kid/alg/use)}. */
export async function makeKey(kid = "test-kid-1") {
  const kp = await crypto.subtle.generateKey(
    { name: "RSASSA-PKCS1-v1_5", modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: "SHA-256" },
    true, ["sign", "verify"]);
  const pub = await crypto.subtle.exportKey("jwk", kp.publicKey);
  return { kid, privateKey: kp.privateKey, publicKey: kp.publicKey, jwk: { kty: "RSA", n: pub.n, e: pub.e, kid, alg: "RS256", use: "sig" } };
}

export function jwksOf(...keys) {
  return { keys: keys.map((k) => k.jwk) };
}

/** Access-like claims for `email`, valid for 1 h; `over` replaces / adds claims (undefined deletes one). */
export function claims(email, over = {}) {
  const now = Math.floor(Date.now() / 1000);
  const c = { iss: `https://${TEAM}`, aud: [AUD], email, sub: "0000", iat: now, nbf: now, exp: now + 3600, type: "app" };
  for (const [k, v] of Object.entries(over)) {
    if (v === undefined) delete c[k];
    else c[k] = v;
  }
  return c;
}

/** RS256-signed JWT. `header` overrides/extends {alg, kid, typ}. */
export async function signJwt(key, payload, header = {}) {
  const h = { alg: "RS256", kid: key.kid, typ: "JWT", ...header };
  const input = `${b64url(JSON.stringify(h))}.${b64url(JSON.stringify(payload))}`;
  const sig = await crypto.subtle.sign({ name: "RSASSA-PKCS1-v1_5" }, key.privateKey, enc.encode(input));
  return `${input}.${b64url(sig)}`;
}

/** HS256 JWT keyed with `secret` (the classic alg-confusion attack uses the public key as the secret). */
export async function signHs256(secret, payload, header = {}) {
  const h = { alg: "HS256", typ: "JWT", ...header };
  const input = `${b64url(JSON.stringify(h))}.${b64url(JSON.stringify(payload))}`;
  const k = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", k, enc.encode(input));
  return `${input}.${b64url(sig)}`;
}

/** alg "none" token (empty or junk signature part). */
export function unsignedJwt(payload, header = {}, sig = "") {
  const h = { alg: "none", typ: "JWT", ...header };
  return `${b64url(JSON.stringify(h))}.${b64url(JSON.stringify(payload))}.${sig}`;
}
