// 📦 Staged rollouts on the Studios' Updates lists — the page side, rendered for real: runs the dashboard script
// (frontend/index.html's largest <script>) in a node vm with stub browser globals and a small DOM (every "as-…" / "us-…"
// id is a real element holding its innerHTML), as tests/active_studio_frontend.js and tests/studio_frontend.js do, on
// TWO builds of the same synthetic site (tests/test_small_rollouts.py): "on" (the engine's small rollouts) and "off"
// (small_rollouts() → [] — the site exactly as without the feature), plus any other variant the test writes (every
// {name}_{variant}.json set in the folder: e.g. "edge", the "on" files with made-up rows at the edges of the rule).
// Prints ONE JSON report: per variant, both Studios' All-apps screen and every app's drawer and full app page.
//   usage: node small_rollout_frontend.js <script.js> <dir with {dashboard,uninstall,active_files,as,us}_{variant}.json>
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const [scriptPath, dir] = process.argv.slice(2);
const J = n => JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8'));
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const classList = () => { const s = new Set(); return { add: (...a) => a.forEach(x => s.add(x)), remove: (...a) => a.forEach(x => s.delete(x)),
  toggle: (x, f) => { const on = f === undefined ? !s.has(x) : !!f; on ? s.add(x) : s.delete(x); return on; }, contains: x => s.has(x), _s: s }; };
function mk(id) { const e = { id, _html: '', attrs: {}, classList: classList(), style: { setProperty() {} }, dataset: {}, hidden: false, open: false,
  scrollTop: 0, scrollLeft: 0, scrollWidth: 0, clientWidth: 1000, offsetParent: {}, value: '',
  get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; },
  querySelector: () => mk('_q'), querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, appendChild() {},
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 20 }), focus() {}, scrollIntoView() {}, closest: () => null };
  return e; }
const ELS = {};
const body = mk('body');
const document = new Proxy({
  getElementById: id => (/^(as|us)-/.test(String(id)) ? (ELS[id] = ELS[id] || mk(id)) : any),
  createElement: () => mk('_new'), body, head: mk('head'), documentElement: mk('html'),
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, activeElement: null,
}, { get: (t, k) => (k in t ? t[k] : any) });
const LSB = {};
const localStorage = { getItem: k => (k in LSB ? LSB[k] : null), setItem: (k, v) => { LSB[k] = String(v); }, removeItem: k => { delete LSB[k]; } };
const timers = [];
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document, localStorage, sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} }, navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', reload() {} }, history: any,
  fetch: () => new Promise(() => {}), setTimeout: (f) => { timers.push(f); return timers.length; }, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String,
  Set, Map, Float64Array, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent, performance: { now: () => 0 },
  getComputedStyle: () => any, innerWidth: 1280, innerHeight: 900, scrollY: 0, scrollTo() {}, alert() {}, confirm: () => false,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
ctx.__flush = () => { while (timers.length) { const f = timers.shift(); try { f(); } catch (e) { errors.push('timer ' + e.message); } } };
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const out = {};
function get(name, code) { try { out[name] = run(code); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); } }
const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; ACTAPP=''; UNIAPP=''; CURVIEW='USD'; ACTJUMP=''; ACTIMPJUMP='';`;
const VARIANTS = fs.readdirSync(dir).map(n => (n.match(/^as_(\w+)\.json$/) || [])[1]).filter(Boolean).sort();
for (const v of VARIANTS) {
  ctx.__V = { dash: J(`dashboard_${v}.json`), uni: J(`uninstall_${v}.json`), files: J(`active_files_${v}.json`), as: J(`as_${v}.json`), us: J(`us_${v}.json`) };
  get(v, `(()=>{ const V=__V, o={as:{},us:{}};
    DATA=V.dash; UNI=V.uni; UNIERR=false; UNICOH={}; Object.keys(ACTD).forEach(k=>{ delete ACTD[k]; }); Object.assign(ACTD,V.files);
    ${RESET} AS._.load(V.as); US._.load(V.us);
    o.as.screen=actScreen(); __flush();
    AS._.A().forEach((a,i)=>{ actScreen(); __flush(); AS.openDrawer(i); o.as['d:'+a.id]=document.getElementById('as-drawer').innerHTML; AS.closeDrawer();
      const row=actRows().find(x=>x.app_id===a.id); if(row){ APP=row.app; ACTAPP=a.id; o.as['p:'+a.id]=actScreen(); __flush(); } ${RESET} });
    ${RESET} o.us.screen=uniScreen();
    US._.A().forEach((a,i)=>{ uniScreen(); US.openDrawer(i); o.us['d:'+a.id]=document.getElementById('us-drawer').innerHTML; US.closeDrawer();
      const row=DATA.uninstall.apps.find(x=>x.app_id===a.id); if(row){ APP=row.app; UNIAPP=a.id; o.us['p:'+a.id]=uniScreen(); } ${RESET} });
    ${RESET} return JSON.stringify(o); })()`);
}
process.stdout.write(JSON.stringify({ errors, out }));
