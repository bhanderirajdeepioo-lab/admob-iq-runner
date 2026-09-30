// Settings saves (SPEC_CONFIG_SAVE), frontend side: runs the REAL dashboard script (frontend/index.html's largest
// <script>) in a node vm with stub browser globals and a scripted fetch, then checks
//   - the pure helpers: cfgFileKey, cfgStatusOf, cfgApiErrMsg, ghErrMsg (the error texts with their HTTP status);
//   - ghCommitFile's path: /api/config/save first; the browser-token GitHub path ONLY when the API is unreachable
//     (404 / network error on /api/config/status, or the save call itself); its 401 / 403 / 404 / 409-422 handling;
//   - ghCommit (approvals) going the same way;
//   - the Settings screen: the token box replaced by the server note, save buttons off for a non-admin.
// Prints ONE JSON report; tests/test_config_save_frontend.py asserts on it.   usage: node config_save_frontend.js <script.js>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath] = process.argv.slice(2);
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const errors = [];
let TOK = null;                                   // the browser's GitHub token (localStorage gh_tok) per scenario
const local = { getItem: k => (k === 'gh_tok' ? TOK : null), setItem() {}, removeItem() {} };
const session = { getItem: () => null, setItem() {}, removeItem() {} };
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document: any, localStorage: local, sessionStorage: session,
  navigator: any, location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} },
  history: any, fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0,
  clearInterval() {}, requestAnimationFrame: () => 0, cancelAnimationFrame() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean,
  RegExp, Error, TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat,
  encodeURIComponent, decodeURIComponent, unescape, escape, btoa, atob, performance: { now: () => 0 },
  getComputedStyle: () => any, innerWidth: 375, innerHeight: 812, scrollTo() {}, alert() {}, confirm: () => false,
  prompt: () => null, IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any,
  HTMLElement: any, Node: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); }
catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const out = { errors, fns: {}, pure: {}, flows: {}, render: {} };
for (const f of ['ghCommitFile', 'ghCommit', 'cfgFileKey', 'cfgStatusOf', 'cfgApiErrMsg', 'ghErrMsg', 'cfgStatus', 'renderSettings']) {
  try { out.fns[f] = run(`typeof ${f}`); } catch (e) { out.fns[f] = 'error'; }
}
const J = JSON.stringify;
function pure(name, code) {
  try { out.pure[name] = JSON.parse(J(run(code))); } catch (e) { errors.push(name + ': ' + e.message); }
}

// ── pure helpers ──
pure('file_keys', `['config/account_names.json','config/app_names.json','config/selected_apps.json','config/approved_ranges.json',
  'config/other.json','approved_ranges.json','config/app_names.json.bak','../config/app_names.json',''].map(cfgFileKey)`);
pure('status_of', `[{status:0,data:null},{status:404,data:{error:'not_found'}},{status:200,data:{server_save:true,admin:true}},
  {status:200,data:{server_save:false,admin:false}},{status:200,data:null},{status:200,data:{hello:1}},{status:401,data:null},
  {status:503,data:{error:'x'}}].map(cfgStatusOf)`);
pure('api_err', `[cfgApiErrMsg(403,{error:'admin_only',msg:'Sirf admin settings badal sakta hai'}),
  cfgApiErrMsg(503,{error:'token_missing',msg:'GitHub token abhi Cloudflare me nahi daala'}),
  cfgApiErrMsg(502,{error:'github_auth',msg:'GitHub token expire/galat',gh_status:401}),
  cfgApiErrMsg(502,{error:'github_forbidden',msg:'Token ko repo me likhne ki permission nahi',gh_status:403}),
  cfgApiErrMsg(409,{error:'github_conflict',msg:'Kisi aur ne abhi save kiya — dobara try karo',gh_status:409}),
  cfgApiErrMsg(400,{error:'bad_request',msg:'Account id galat.',field:'content'}),
  cfgApiErrMsg(401,null), cfgApiErrMsg(500,{error:'server_error'}), cfgApiErrMsg(502,{msg:'x',gh_status:0})]`);
pure('gh_err', `[401,403,404,409,422,500,0].map(ghErrMsg)`);

// ── flows: a scripted fetch (server routes + GitHub contents API) ──
const b64dec = s => Buffer.from(s, 'base64').toString('utf8');
function resp(status, json) {
  return { status, ok: status >= 200 && status < 300, type: 'basic',
           json: async () => { if (json === undefined) throw new SyntaxError('not json'); return JSON.parse(J(json)); } };
}
/**
 * plan: {status: [code, json] | 'throw', statusQ: [one answer per status call, …], save: [[code, json] | 'throw', …], ghGet: [[code, json], …], ghPut: [code, …]}
 * Queues are consumed in order; an exhausted GitHub queue answers GET 200 {sha:'s-last'} / PUT 200.
 */
function scripted(plan) {
  const calls = [];
  const statusQ = (plan.statusQ || []).slice(), saveQ = (plan.save || []).slice(), getQ = (plan.ghGet || []).slice(), putQ = (plan.ghPut || []).slice();
  const fetch = async (url, opt = {}) => {
    url = String(url);
    const method = opt.method || 'GET';
    const c = { url, method, body: opt.body ? JSON.parse(opt.body) : null, cache: opt.cache || null,
                auth: (opt.headers && opt.headers.Authorization) || null };
    calls.push(c);
    if (url === '/api/config/status') {
      const st = statusQ.length ? statusQ.shift() : plan.status;
      if (st === 'throw') throw new TypeError('Failed to fetch');
      return resp(...(st || [404, { error: 'not_found' }]));
    }
    if (url === '/api/config/save') {
      const r = saveQ.shift() || [404, { error: 'not_found' }];
      if (r === 'throw') throw new TypeError('Failed to fetch');
      return resp(...r);
    }
    if (url.startsWith('https://api.github.com/repos/')) {
      if (method === 'GET') return resp(...(getQ.shift() || [200, { sha: 's-last' }]));
      if (method === 'PUT') { const s = putQ.shift() || 200; return resp(s, s < 300 ? { content: {}, commit: {} } : { message: 'no' }); }
    }
    throw new Error('unexpected fetch ' + method + ' ' + url);
  };
  return { calls, fetch };
}
async function flow(name, plan, code) {
  try {
    TOK = plan.token === undefined ? 'test-browser-token' : plan.token;
    const s = scripted(plan);
    ctx.fetch = s.fetch;
    ctx.__toasts = [];
    run(`CFGST = null; CFGST_P = null; bToast = function (m) { __toasts.push(String(m)); };`);
    const ret = await run(code);
    const calls = s.calls.map(c => {
      const o = { url: c.url.replace(/^https:\/\/api\.github\.com\/repos\/[^/]+\/[^/]+\/contents\//, 'GH:'), method: c.method };
      if (c.body) o.body = c.body.content && typeof c.body.content === 'string' && o.url.startsWith('GH:')
        ? { message: c.body.message, sha: c.body.sha === undefined ? null : c.body.sha, content: b64dec(c.body.content) } : c.body;
      if (c.cache) o.cache = c.cache;
      if (c.auth) o.auth = c.auth;
      return o;
    });
    out.flows[name] = { ret: ret === undefined ? '__undefined__' : ret, toasts: ctx.__toasts.slice(), calls,
                        st: JSON.parse(J(run('CFGST'))) };
  } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + ((e.stack || '').match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); }
}
const SRV = [200, { server_save: true, admin: true }];
const OBJ = `{accounts:{'pub-1001':{decided:true,selected:['ca-app-pub-1001~1']}}}`;
const SAVE = `ghCommitFile('config/selected_apps.json', ${OBJ}, 'select apps', 'OK-MSG')`;

(async () => {
  await flow('server_ok', { status: SRV, save: [[200, { ok: true, file: 'selected_apps', sha: 'c1' }]] }, SAVE);
  await flow('server_gh401', { status: SRV, save: [[502, { error: 'github_auth', msg: 'GitHub token expire/galat', gh_status: 401 }]] }, SAVE);
  await flow('server_admin403', { status: [200, { server_save: true, admin: false }],
    save: [[403, { error: 'admin_only', msg: 'Sirf admin settings badal sakta hai' }]] }, SAVE);
  await flow('server_no_token503', { status: [200, { server_save: false, admin: true }],
    save: [[503, { error: 'token_missing', msg: 'GitHub token abhi Cloudflare me nahi daala' }]] }, SAVE);
  await flow('server_auth401', { status: [401, { error: 'unauthorized', msg: 'Login zaroori — page reload karo' }],
    save: [[401, { error: 'unauthorized', msg: 'Login zaroori — page reload karo' }]] }, SAVE);
  await flow('fallback_404_ok', { status: [404, { error: 'not_found' }], ghGet: [[200, { sha: 's1' }]], ghPut: [200] }, SAVE);
  await flow('fallback_net_ok_new_file', { status: 'throw', ghGet: [[404, { message: 'Not Found' }]], ghPut: [201] }, SAVE);
  await flow('fallback_html_status', { status: [200, undefined], ghGet: [[200, { sha: 's1' }]], ghPut: [200] }, SAVE);
  await flow('fallback_put401', { status: 'throw', ghGet: [[200, { sha: 's1' }]], ghPut: [401] }, SAVE);
  await flow('fallback_get401', { status: 'throw', ghGet: [[401, { message: 'Bad credentials' }]] }, SAVE);
  await flow('fallback_put403', { status: 'throw', ghGet: [[200, { sha: 's1' }]], ghPut: [403] }, SAVE);
  await flow('fallback_put404', { status: 'throw', ghGet: [[404, {}]], ghPut: [404] }, SAVE);
  await flow('fallback_409_retry_ok', { status: 'throw', ghGet: [[200, { sha: 's1' }], [200, { sha: 's2' }]], ghPut: [409, 200] }, SAVE);
  await flow('fallback_422_twice', { status: 'throw', ghGet: [[200, { sha: 's1' }], [200, { sha: 's2' }]], ghPut: [422, 422] }, SAVE);
  await flow('fallback_500', { status: 'throw', ghGet: [[200, { sha: 's1' }]], ghPut: [500] }, SAVE);
  await flow('fallback_no_token', { status: 'throw', token: null }, SAVE);
  await flow('save_net_then_fallback', { status: SRV, save: ['throw'], ghGet: [[200, { sha: 's1' }]], ghPut: [200] }, SAVE);
  await flow('save_404_then_fallback', { status: SRV, save: [[404, { error: 'not_found' }]], ghGet: [[200, { sha: 's1' }]], ghPut: [200] }, SAVE);
  await flow('status_cached', { status: SRV, save: [[200, { ok: true }], [200, { ok: true }]] },
    `(async () => { await ${SAVE}; return await ${SAVE}; })()`);
  await flow('reask_after_unreachable', { statusQ: ['throw', SRV], save: [[200, { ok: true }]], ghGet: [[200, { sha: 's1' }]], ghPut: [200] },
    `(async () => { const a = await ${SAVE}; const b = await ${SAVE}; return [a, b]; })()`);
  await flow('approvals_server', { status: SRV, save: [[200, { ok: true }]] },
    `(() => { APPR = {placements:{'ca-app-pub-1001/2001':{metrics:{}}}}; return ghCommit('approve X · eCPM'); })()`);
  await flow('approvals_fallback_no_token', { status: 'throw', token: null }, `ghCommit('approve X · eCPM')`);
  await flow('approvals_fallback_ok', { status: 'throw', ghGet: [[200, { sha: 's1' }]], ghPut: [200] },
    `(() => { APPR = {placements:{}}; return ghCommit('approve X · eCPM'); })()`);

  // ── Settings screen render (plain object instead of a DOM element) ──
  try {
    run(`screenDiv = function (id) { return {dataset:{screen:id}, classList:{add(){}, contains(){ return false; }}, innerHTML:''}; };
      DATA = Object.assign({}, (typeof DATA==='object'&&DATA)||{}, {currency:'USD', usd_inr:88,
        accounts:[{account_id:'pub-1001', label:'Acct One', token:'ok', apps:[1], last_sync:'today'}],
        apps_catalog:[{account_id:'pub-1001', app_id:'ca-app-pub-1001~1', app_name:'App One', rev:12}]});
      CURVIEW = 'USD'; APPSEL = {accounts:{}}; ACCNAMES = {};`);
    const states = { none: 'null', unreachable: '{reach:false}', server_admin: '{reach:true,server_save:true,admin:true}',
                     server_team: '{reach:true,server_save:true,admin:false}', noserver_admin: '{reach:true,server_save:false,admin:true}',
                     noserver_team: '{reach:true,server_save:false,admin:false}', auth_unknown: '{reach:true,server_save:false,admin:null,status:401}' };
    for (const [k, st] of Object.entries(states)) {
      for (const tok of [null, 'test-browser-token']) {
        TOK = tok;
        out.render[k + (tok ? '_tok' : '')] = String(run(`(() => { CFGST = ${st}; return renderSettings().innerHTML; })()`));
      }
    }
  } catch (e) { errors.push('render: ' + e.message); }
  process.stdout.write(J(out));
})();
