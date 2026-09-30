// LOCAL E2E ONLY: prints throwaway test keys + tokens as JSON
//   {"jwks": {...}, "jwks_line": "<one-line JSON for ACCESS_JWKS_JSON>", "tokens": {"owner","team","expired"}}
// for `wrangler dev --local` with ACCESS_TEAM_DOMAIN="team.example.test", ACCESS_AUD="aud-test",
// ADMIN_EMAILS="owner@example.test". ACCESS_JWKS_JSON is honoured ONLY for localhost requests, so these keys
// can never log anyone into the real dashboard. A new key pair is generated on every run.
//
//   node review_worker/test/devkeys.mjs > devkeys.json
//   env: DEVKEYS_DAYS (token lifetime, default 7)

import { makeKey, jwksOf, signJwt, claims, OWNER, TEAMMATE } from "./jwt.js";

async function main() {
  const key = await makeKey(`dev-${Date.now().toString(36)}`);
  const now = Math.floor(Date.now() / 1000);
  const life = Math.max(1, Math.min(30, Number(process.env.DEVKEYS_DAYS) || 7)) * 86400;
  const jwks = jwksOf(key);
  const out = {
    jwks,
    jwks_line: JSON.stringify(jwks),
    tokens: {
      owner: await signJwt(key, claims(OWNER, { exp: now + life })),
      team: await signJwt(key, claims(TEAMMATE, { exp: now + life })),
      expired: await signJwt(key, claims(TEAMMATE, { iat: now - 7200, nbf: now - 7200, exp: now - 3600 })),
    },
  };
  process.stdout.write(JSON.stringify(out, null, 2) + "\n");
}

// `node --test` (no args) also runs every file under test/ — print nothing there.
if (!process.env.NODE_TEST_CONTEXT) await main();
