// Repo-level guarantees for the Review Worker (node --test):
// 1. PUBLIC repo: nothing under review_worker/ holds a private value (ids, real domains, real emails).
// 2. Every src file passes `node --check` (the robot only syncs code that parses).
// 3. The robot's sync step — taken verbatim from .github/workflows/refresh.yml — never fails the push and only
//    ever replaces the private worker/ folder with code that parses (bash + git; skipped where unavailable).
import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));            // review_worker/
const SRC = join(ROOT, "src");
const WORKFLOW = join(ROOT, "..", ".github", "workflows", "refresh.yml");
const SKIP_DIRS = new Set(["node_modules", ".wrangler", ".state", ".git"]);

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name)) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

// ── 1. privacy ──────────────────────────────────────────────────────────────────────────────────

test("privacy: no publisher/app ids, long hex ids, UUIDs, real domains or real emails anywhere in review_worker/", () => {
  const files = walk(ROOT);
  assert.ok(files.length >= 10);
  const problems = [];
  // api.github.com / github.com: the public GitHub hosts of Settings saves (config.js). The config repo itself comes
  // from the CONFIG_REPO var, so a github.com URL here may only name a placeholder owner (checked below).
  const allowedUrlHost = (h) => /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(h) || /(^|\.)example\.test(:\d+)?$/.test(h) ||
    /^\$\{[A-Za-z_.]+\}$/.test(h) || h === "<team>.cloudflareaccess.com" || h === "api.github.com" || h === "github.com" ||
    h === "…" || h === ",";
  const allowedGhOwner = (o) => /^(example-[a-z-]+|owner|\$\{[A-Za-z_.]+\}|repos)$/.test(o);
  for (const f of files) {
    const rel = relative(ROOT, f);
    const text = readFileSync(f, "utf8");
    const bad = (why, m) => problems.push(`${rel}: ${why}: ${String(m).slice(0, 12)}…`);
    for (const m of text.match(/pub-\d{10,}/g) || []) bad("publisher id", m);
    for (const m of text.match(/\b[0-9a-f]{32,}\b/gi) || []) bad("long hex id", m);
    for (const m of text.match(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi) || []) {
      if (!/^[0-]+$/.test(m)) bad("uuid", m);
    }
    for (const m of text.matchAll(/([A-Za-z0-9<>_-]+)\.cloudflareaccess\.com/g)) if (m[1] !== "<team>") bad("team domain", m[0]);
    for (const m of text.matchAll(/https?:\/\/([^/\s"'`)]+)/g)) if (!allowedUrlHost(m[1])) bad("url host", m[1]);
    for (const m of text.matchAll(/https?:\/\/(?:api\.)?github\.com\/([^/\s"'`)]+)/g)) if (!allowedGhOwner(m[1])) bad("github owner", m[1]);
    for (const m of text.matchAll(/CONFIG_REPO\s*=\s*"([^"]*)"/g)) if (!/^owner\\?\/private-repo$/.test(m[1])) bad("config repo", m[1]);
    for (const m of text.matchAll(/[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)/g)) {
      if (m[1].toLowerCase() !== "example.test" && !m[0].endsWith("p@yload.sig")) bad("email", m[0]);
    }
  }
  assert.deepEqual(problems, []);
});

test("wrangler.example.toml: placeholders only, access-bypassing URLs off, no test-only JWKS, no GitHub token", () => {
  const t = readFileSync(join(ROOT, "wrangler.example.toml"), "utf8");
  assert.match(t, /^workers_dev = false$/m);
  assert.match(t, /^preview_urls = false$/m);
  assert.match(t, /^database_id = "REVIEW_DB_ID"$/m);
  assert.match(t, /^ACCESS_TEAM_DOMAIN = "ACCESS_TEAM_DOMAIN"/m);
  assert.match(t, /^ACCESS_AUD = "ACCESS_AUD"/m);
  assert.match(t, /^binding = "REVIEW_DB"$/m);
  assert.match(t, /^main = "worker\/index\.js"$/m);
  assert.match(t, /^run_worker_first = \["\/api\/\*"\]$/m);
  assert.equal(/^\s*ACCESS_JWKS_JSON/m.test(t), false);
  assert.match(t, /^CONFIG_REPO = "owner\/private-repo"/m);
  assert.equal(/^\s*GITHUB_TOKEN\s*=/m.test(t), false, "GITHUB_TOKEN is a Cloudflare Secret, never a var in the file");
  assert.match(t, /^# .*GITHUB_TOKEN.*Secret/m);
});

test("local-dev leftovers (wrangler state = a local D1 with clicked notes / app names, dev keys, local config) are git-ignored", () => {
  const top = spawnSync("git", ["rev-parse", "--show-toplevel"], { cwd: ROOT, encoding: "utf8" });
  if (top.status !== 0) return;                           // not a git checkout: nothing can be committed from here
  const repo = top.stdout.trim();
  const ignored = (p) => spawnSync("git", ["check-ignore", "-q", "--no-index", p], { cwd: repo, encoding: "utf8" }).status === 0;
  for (const p of ["review_worker/.state/v3/d1/miniflare-D1DatabaseObject/db.sqlite", "review_worker/.wrangler/tmp/x.js",
    "review_worker/devkeys.json", "review_worker/wrangler.toml", "review_worker/worker/index.js", "review_worker/site/index.html",
    ".state/x", ".wrangler/x", "review_worker/.dev.vars", ".dev.vars"]) {
    assert.equal(ignored(p), true, p);
  }
  for (const p of ["review_worker/src/index.js", "review_worker/wrangler.example.toml", "review_worker/test/devkeys.mjs",
    "review_worker/schema.sql"]) {
    assert.equal(ignored(p), false, p);
  }
});

// ── 2. syntax ───────────────────────────────────────────────────────────────────────────────────

test("every src/*.js passes node --check; src/package.json marks ES modules", () => {
  const js = readdirSync(SRC).filter((f) => f.endsWith(".js"));
  assert.deepEqual(js.sort(), ["auth.js", "config.js", "db.js", "index.js"]);
  for (const f of js) {
    const r = spawnSync(process.execPath, ["--check", join(SRC, f)], { encoding: "utf8" });
    assert.equal(r.status, 0, `${f}: ${r.stderr}`);
  }
  assert.deepEqual(JSON.parse(readFileSync(join(SRC, "package.json"), "utf8")), { type: "module" });
});

// ── 3. the robot's sync step (refresh.yml) ──────────────────────────────────────────────────────

const has = (cmd, args = ["--version"]) => spawnSync(cmd, args, { encoding: "utf8" }).status === 0;
const canRun = existsSync(WORKFLOW) && has("bash") && has("git");
const BASH = canRun ? spawnSync("bash", ["-c", "command -v bash"], { encoding: "utf8" }).stdout.trim() : "bash";

/** The push-step lines from `rm -rf data site` to `git add -A worker`, dedented — exactly what the robot runs. */
function syncSnippet() {
  const lines = readFileSync(WORKFLOW, "utf8").split("\n");
  const a = lines.findIndex((l) => l.trim() === "rm -rf data site && mkdir -p data site");
  const b = lines.findIndex((l) => l.trim() === "if [ -d worker ]; then git add -A worker; fi");
  assert.ok(a > 0 && b > a, "sync block found in refresh.yml");
  const indent = lines[a].match(/^\s*/)[0].length;
  return lines.slice(a, b + 1).map((l) => l.slice(indent)).join("\n");
}

const git = (cwd, ...args) => {
  const r = spawnSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.test", "-c", "init.defaultBranch=main", ...args],
    { cwd, encoding: "utf8" });
  assert.equal(r.status, 0, `git ${args.join(" ")}: ${r.stderr}`);
  return r.stdout;
};

/**
 * One robot run in a scratch checkout: <case>/{data,site,review_worker?} next to <case>/_private (a git repo that
 * may already hold worker/ files "from the remote"). Runs the snippet under `set -eo pipefail`.
 */
function runCase({ worker = null, remote = null, path = process.env.PATH }) {
  const dir = mkdtempSync(join(tmpdir(), "rv-sync-"));
  mkdirSync(join(dir, "data"));
  mkdirSync(join(dir, "site"));
  writeFileSync(join(dir, "data", "a.json"), "{}\n");
  writeFileSync(join(dir, "site", "b.html"), "<p>b</p>\n");
  const priv = join(dir, "_private");
  mkdirSync(priv);
  git(priv, "init", "-q");
  writeFileSync(join(priv, "wrangler.toml"), "name = \"x\"\n");
  if (remote) {
    mkdirSync(join(priv, "worker"));
    for (const [f, body] of Object.entries(remote)) writeFileSync(join(priv, "worker", f), body);
  }
  git(priv, "add", "-A");
  git(priv, "commit", "-q", "-m", "remote");
  if (worker) {
    mkdirSync(join(dir, "review_worker"));
    if (worker === "real") cpSync(SRC, join(dir, "review_worker", "src"), { recursive: true });
    else {
      mkdirSync(join(dir, "review_worker", "src"));
      for (const [f, body] of Object.entries(worker)) writeFileSync(join(dir, "review_worker", "src", f), body);
    }
  }
  const script = `set -eo pipefail\ncd "${priv}"\n${syncSnippet()}\necho SYNC_STEP_OK\n`;
  const r = spawnSync(BASH, ["-c", script], { encoding: "utf8", env: { ...process.env, PATH: path } });
  const staged = git(priv, "diff", "--cached", "--name-status").trim().split("\n").filter(Boolean).sort();
  const workerFiles = existsSync(join(priv, "worker")) ? readdirSync(join(priv, "worker")).sort() : null;
  const contents = Object.fromEntries((workerFiles || []).map((f) => [f, readFileSync(join(priv, "worker", f), "utf8")]));
  rmSync(dir, { recursive: true, force: true, maxRetries: 3 });
  return { r, staged, workerFiles, contents };
}

const REAL = ["auth.js", "config.js", "db.js", "index.js", "package.json"];
const OLD = { "index.js": "export default {};\n" };

test("sync step: review_worker missing → no worker/, push goes on (data + site staged)", { skip: !canRun }, () => {
  const c = runCase({});
  assert.equal(c.r.status, 0, c.r.stderr);
  assert.match(c.r.stdout, /SYNC_STEP_OK/);
  assert.equal(c.workerFiles, null);
  assert.deepEqual(c.staged, ["A\tdata/a.json", "A\tsite/b.html"]);
});

test("sync step: review_worker missing but the remote has worker/ → kept exactly as is", { skip: !canRun }, () => {
  const c = runCase({ remote: OLD });
  assert.equal(c.r.status, 0, c.r.stderr);
  assert.deepEqual(c.workerFiles, ["index.js"]);
  assert.deepEqual(c.staged, ["A\tdata/a.json", "A\tsite/b.html"]);
});

test("sync step: a src file with a syntax error → nothing synced, remote worker/ untouched, step still exits 0", { skip: !canRun }, () => {
  const pkg = '{"type":"module"}\n';
  for (const broken of ["export default {\n", "const = ;\n", "import x from 'y';\nexport default { fetch( };\n"]) {
    const c = runCase({ remote: OLD, worker: { "index.js": broken, "auth.js": "export const a = 1;\n", "package.json": pkg } });
    assert.equal(c.r.status, 0, c.r.stderr);
    assert.match(c.r.stdout, /SYNC_STEP_OK/);
    assert.deepEqual(c.workerFiles, ["index.js"], JSON.stringify(broken));
    assert.equal(c.contents["index.js"], OLD["index.js"]);
    assert.deepEqual(c.staged, ["A\tdata/a.json", "A\tsite/b.html"]);
  }
});

test("sync step: code that parses but does not LINK (missing export / missing module) → nothing synced", { skip: !canRun }, () => {
  const pkg = '{"type":"module"}\n';
  const real = Object.fromEntries(["auth.js", "config.js", "db.js", "index.js"].map((f) => [f, readFileSync(join(SRC, f), "utf8")]));
  const broken = [
    real["index.js"].replace("_resetAuthForTests }", "_resetAuthForTests, notThere }"),     // a named export auth.js lacks
    real["index.js"].replace('from "./db.js"', 'from "./dbx.js"'),                           // a module file that is not there
  ];
  for (const b of broken) assert.notEqual(b, real["index.js"], "the test edit applied");
  for (const b of broken) {
    const c = runCase({ remote: OLD, worker: { ...real, "index.js": b, "package.json": pkg } });
    assert.equal(c.r.status, 0, c.r.stderr);
    assert.match(c.r.stdout, /SYNC_STEP_OK/);
    assert.deepEqual(c.workerFiles, ["index.js"]);
    assert.equal(c.contents["index.js"], OLD["index.js"]);
    assert.deepEqual(c.staged, ["A\tdata/a.json", "A\tsite/b.html"]);
  }
});

test("sync step: src without package.json (a broken ES module could pass --check) → nothing synced", { skip: !canRun }, () => {
  const c = runCase({ remote: OLD, worker: { "index.js": "export default {\n" } });
  assert.equal(c.r.status, 0, c.r.stderr);
  assert.deepEqual(c.workerFiles, ["index.js"]);
  assert.deepEqual(c.staged, ["A\tdata/a.json", "A\tsite/b.html"]);
});

test("sync step: real src → worker/ = src byte for byte, all staged", { skip: !canRun }, () => {
  const c = runCase({ worker: "real" });
  assert.equal(c.r.status, 0, c.r.stderr);
  assert.deepEqual(c.workerFiles, REAL);
  for (const f of REAL) assert.equal(c.contents[f], readFileSync(join(SRC, f), "utf8"), f);
  assert.deepEqual(c.staged, ["A\tdata/a.json", "A\tsite/b.html", ...REAL.map((f) => `A\tworker/${f}`)]);
});

test("sync step: real src replaces a stale remote worker/ (old files removed, changed files updated)", { skip: !canRun }, () => {
  const c = runCase({ worker: "real", remote: { ...OLD, "old.js": "export {};\n" } });
  assert.equal(c.r.status, 0, c.r.stderr);
  assert.deepEqual(c.workerFiles, REAL);
  assert.deepEqual(c.staged, ["A\tdata/a.json", "A\tsite/b.html", "A\tworker/auth.js", "A\tworker/config.js",
    "A\tworker/db.js", "A\tworker/package.json", "D\tworker/old.js", "M\tworker/index.js"]);
});

test("sync step: no node on PATH → nothing synced, step still exits 0", { skip: !canRun }, () => {
  const bin = mkdtempSync(join(tmpdir(), "rv-bin-"));
  try {
    for (const tool of ["git", "rm", "mkdir", "cp"]) {
      const w = spawnSync("bash", ["-c", `command -v ${tool}`], { encoding: "utf8" }).stdout.trim();
      assert.ok(w, tool);
      symlinkSync(w, join(bin, tool));
    }
    const c = runCase({ remote: OLD, worker: "real", path: bin });
    assert.equal(c.r.status, 0, c.r.stderr);
    assert.deepEqual(c.workerFiles, ["index.js"]);
    assert.deepEqual(c.staged, ["A\tdata/a.json", "A\tsite/b.html"]);
  } finally {
    rmSync(bin, { recursive: true, force: true });
  }
});

test("refresh.yml hands the three REVIEW_* switches to the build step (off by default)", { skip: !existsSync(WORKFLOW) }, () => {
  const y = readFileSync(WORKFLOW, "utf8");
  assert.match(y, /^ {10}REVIEW_ENABLED: +\$\{\{ vars\.REVIEW_ENABLED \|\| 'false' \}\}$/m);
  assert.match(y, /^ {10}REVIEW_READY_IST: +\$\{\{ vars\.REVIEW_READY_IST \}\}$/m);
  assert.match(y, /^ {10}REVIEW_REBUILD_DAY: +\$\{\{ vars\.REVIEW_REBUILD_DAY \}\}$/m);
});
