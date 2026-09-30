# Review API (Cloudflare Worker + D1)

The dashboard's **Review** tab shows one card per app per day. The cards themselves are static files built by
the refresh robot (`site/review/…`). This Worker stores what people **do** with them — `✅ Reviewed`, `📝 Note`,
`🚩 Important · Re-review` flags (per app or per feature), `🔁 Kal dobara dekho`, `💤 Pata hai` snoozes, and the
admin's decisions on flags — in a Cloudflare D1 database, so every device and every teammate sees the same state.

No runtime dependencies: WebCrypto, `fetch`, `DecompressionStream` and the D1 binding only.

```
src/index.js   routing, validation, CSRF, response headers; everything that is not /api/* goes to the static site
src/auth.js    Cloudflare Access JWT verification (fails closed)
src/db.js      D1 schema (created automatically), every query and state rule
schema.sql     the same DDL as db.js (documentation; a test keeps them equal)
test/          node:test suites, a D1 fake over node:sqlite, test-only JWT helpers, devkeys.mjs (local e2e keys)
```

## Request flow and security model

```
browser ──► Cloudflare Access (edge login) ──► Worker
                                                 ├─ /api/review/*  verify the Access JWT again → D1 (REVIEW_DB)
                                                 ├─ other /api/*   404
                                                 └─ everything else → static dashboard (ASSETS), unchanged
```

- **Access at the edge is not trusted alone.** Every `/api/review/*` request must carry the Access JWT
  (`Cf-Access-Jwt-Assertion` header, else the `CF_Authorization` cookie). `auth.js` verifies it itself:
  RS256 only (no `none`/`HS*`), signature against the team JWKS (`https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`,
  cached 10 min, one forced refetch per 30 s for an unknown `kid`), `iss`, `aud`, `exp`/`nbf`/`iat` (60 s skew) and
  a required `email`. Anything missing or wrong → `401`; missing config → `500`; JWKS unreachable → `503`. No data
  is ever served on any of these paths.
- **"Who"** on every action is the verified, lower-cased Access email. Nobody can act as someone else.
- **CSRF:** POSTs need `Content-Type: application/json` and an `Origin` equal to the request's own origin; bodies
  are capped at 8 KiB. No `Access-Control-*` (CORS) header is ever sent, and `OPTIONS` → `405`.
- **Logs:** the Worker never logs emails, notes, app names or money — errors log only their type.
- Every API response: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `X-Robots-Tag: noindex`, `X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'` (the static
  dashboard's `_headers` forbid framing too, so no other site can put the Review buttons under a clickjacking overlay).

### Why `workers_dev` and `preview_urls` stay `false`

Access protects the **custom domain**. A `*.workers.dev` URL or a preview URL would serve the same Worker (and the
same static dashboard) **without** Access in front of it. The API would still refuse requests without a valid JWT,
but the static files would be public. Without these two lines every `wrangler deploy` turns `workers_dev` back on,
so they must stay in the file.

## Configuration (private repo `wrangler.toml` — placeholders here, real values only in the private repo)

```toml
name = "admob-iq"
main = "worker/index.js"
compatibility_date = "2024-09-23"

workers_dev = false
preview_urls = false

[assets]
directory = "./site"
binding = "ASSETS"
run_worker_first = ["/api/*"]

[[d1_databases]]
binding = "REVIEW_DB"
database_name = "admob-review"
database_id = "REVIEW_DB_ID"

[vars]
ACCESS_TEAM_DOMAIN = "ACCESS_TEAM_DOMAIN"     # e.g. <team>.cloudflareaccess.com (no https://)
ACCESS_AUD = "ACCESS_AUD"                     # the Access application's AUD tag
ADMIN_EMAILS = "owner@example.test"           # comma list; only these can decide 🚩 flags
```

`wrangler.example.toml` holds the same block with comments. The refresh robot copies `review_worker/src/` into the
private repo's `worker/` folder on every run (only when `src/package.json` is there, every file passes
`node --check` — without that file newer Node versions let a broken ES module pass the check — and `index.js` really
imports, so a missing module or export never reaches the Workers build); until the private
`wrangler.toml` has `main = "worker/index.js"` that code is inert. If the build system rejects the array form of
`run_worker_first`, `run_worker_first = true` is also safe: the Worker forwards every non-`/api/` request to
`ASSETS` unchanged.

- **Admins:** `ADMIN_EMAILS` (comma or space separated, case-insensitive). Only admins can decide flags
  (`👍 Theek hai` · `🛠 Kaam do` · `⛔ Band karo` · `✅ Kaam ho gaya`) and correct older days. Everyone the Access
  policy lets in can review.
- **Open day:** the Worker reads `site/review/index.json` through the `ASSETS` binding (the same file the page
  reads). Writes go to its `open_day`; other days get `403 day_closed` (admins may still fix `ok`/`note`/`undo`/
  `bulk_ok` on an older snapshot day from History). The page's "Aaj ka review" sends `live: true`: if a newer
  snapshot opened while the page was open, that click gets `409 day_moved` (+ `open_day`) instead of landing on
  yesterday. With no index yet, every action POST gets `409 review_not_started`.
- **`ACCESS_JWKS_JSON` is TEST-ONLY.** It is honoured only when the request itself is for `localhost`,
  `127.0.0.1` or `[::1]` (wrangler dev, node tests); on any other host it is ignored and the real team JWKS is
  fetched. Never put it in the private `wrangler.toml`.

## Database

- **No manual migration:** the Worker creates its tables (`rv_meta`, `rv_state`, `rv_actions`, `rv_notes`,
  `rv_flags`, `rv_snoozes`) on the first request of each isolate (`CREATE … IF NOT EXISTS`, idempotent) and
  records `schema_version` (now 2). A new database gets the current DDL directly; an older one is upgraded by
  `MIGRATIONS` in `db.js` (2: `rv_flags.dec_day` / `done_day`, the review day of a flag decision).
- `rv_actions` is append-only (the "who did what" history); every write adds its row in the same transaction.
- **Backup / undo:** D1 Time Travel can restore the database to any minute of the last 30 days (Workers Paid;
  7 days on the Free plan) with `wrangler d1 time-travel restore <db> --timestamp=…`, run by the operator.
  Rolling back the Worker (or the review feature) never deletes D1 data.
- **Stays inside the D1 Free limits:** at most ~25 D1 statements per request, cold start included (Free allows
  50 and counts every statement of a batch), whatever the group size of `✅ Sab reviewed` (`bulk_ok` expands its
  keys inside SQLite with `json_each`), and ≤ 100 bound parameters per statement. The page polls `day` every
  60 s; that read uses indexes only for the open day (`test/limits.test.js` guards the budget).

## API (all JSON, all under `/api/review/`)

| Method | Path | What |
|---|---|---|
| GET | `me` | `{email, admin, open_day, go_live, server_time}` |
| GET | `day?d=YYYY-MM-DD` | the day's states, notes, flags (incl. carried-over open ones), snoozes, `prev.kal`, log, `rev` |
| GET | `calendar?from=&to=` | per-day counts for History (≤ 400 days) |
| POST | `action` | `{d, act, app?, feature?, note?, days?, apps?, flag_id?, live?}` — `ok, note, kal, flag, unflag, undo, snooze, unsnooze, bulk_ok` |
| POST | `decide` | admin only: `{flag_id, decision: theek|kaam|band|done, note}` (note required for kaam / band) |

Errors: `{"error": code, "msg": "<short Hinglish>", "why"?, "field"?}` with 400 / 401 / 403 / 404 / 405 / 409 /
413 / 415 / 500 / 503.

## Tests

```bash
cd review_worker
npm test              # = node --test "test/*.test.js"   (Node ≥ 22.5 for node:sqlite; no npm install needed)
node --check src/index.js && node --check src/auth.js && node --check src/db.js
```

The tests run the real Worker entry against a D1 fake over `node:sqlite` and sign JWTs with an RSA key generated
in the test (valid, expired, wrong `aud`/`iss`/`kid`, bad signature, `alg` confusion, missing header, …).
`test/repo.test.js` also runs the robot's sync step — read straight from `.github/workflows/refresh.yml` — under
`bash -eo pipefail` in seven states (folder missing, remote-only, syntax error, parses but does not link, no
`package.json`, ok, no node) and
scans this folder for anything that looks like a private value. From the repo root:
`node --test "review_worker/test/*.test.js"` (a bare directory argument does not work on Node ≥ 22).

## Local development (no Cloudflare account, nothing remote)

```bash
node test/devkeys.mjs > devkeys.json     # throwaway key pair + tokens {owner, team, expired}; localhost only
```

Make a local `wrangler.toml` next to a built `site/` (with `site/review/…`) and a copy of `src/` as `worker/`:
use `ACCESS_TEAM_DOMAIN = "team.example.test"`, `ACCESS_AUD = "aud-test"`, `ADMIN_EMAILS = "owner@example.test"`,
a dummy `database_id`, and `ACCESS_JWKS_JSON = '<devkeys.json .jwks_line>'`. Then:

```bash
WRANGLER_SEND_METRICS=false npx wrangler@4 dev --local --port 8787 --persist-to ./.state
curl -s -H "Cf-Access-Jwt-Assertion: $(jq -r .tokens.owner devkeys.json)" localhost:8787/api/review/me
```

Only `--local`: never `--remote`, never `wrangler deploy` from a laptop — the private repo's push deploys.
The local `wrangler.toml`, `worker/`, `devkeys.json`, `.state/` and `.wrangler/` are git-ignored (the local D1 in
`.state/` holds whatever notes / flags / app names you clicked — never commit it). Better still, keep the whole
local setup outside this repo.
