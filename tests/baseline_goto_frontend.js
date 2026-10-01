// The Baseline ad-unit jump (bGotoUnit — an alert / recommendation row → that placement's page) and the header App
// picker — the page side, run for real: the dashboard script (frontend/index.html's largest <script>) in a node vm with
// stub browser globals and a small DOM (ids, attributes, a <select> whose value follows its rebuilt list as a browser's
// does), on a SYNTHETIC dashboard made up here. The jump sets APP='' without a render(); the header must say so at once.
// render / setApp / bRerender are spies, show() is wrapped (it still runs) — ONE JSON report on stdout;
// tests/test_baseline_goto_frontend.py asserts on it.
//   usage: node baseline_goto_frontend.js <script.js>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath] = process.argv.slice(2);
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const ELS = {};
const unesc = s => String(s).replace(/&lt;/g, '<').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
function mk(id) {
  const cls = new Set();
  const el = {
    _id: '', _html: '', _value: '', attrs: {}, hidden: false, textContent: '', listeners: [], dataset: {},
    get id() { return this._id; }, set id(v) { this._id = String(v); ELS[this._id] = this; },
    classList: { add: (...a) => a.forEach(x => cls.add(x)), remove: (...a) => a.forEach(x => cls.delete(x)), contains: x => cls.has(x),
      toggle: (x, f) => { const on = f === undefined ? !cls.has(x) : !!f; on ? cls.add(x) : cls.delete(x); return on; } },
    style: { setProperty() {} },
    get innerHTML() { return this._html; },
    // a rebuilt <select>: its value = the `selected` option, else the first (as a browser)
    set innerHTML(v) { this._html = String(v); const o = this.options; if (!o.length) return;
      const s = /<option value="([^"]*)" selected>/.exec(this._html); this._value = s ? unesc(s[1]) : o[0].value; },
    get value() { return this._value; }, set value(v) { this._value = String(v); },
    get options() { const o = []; const re = /<option value="([^"]*)"[^>]*>([^<]*)<\/option>/g; let m;
      while ((m = re.exec(this._html))) o.push({ value: unesc(m[1]), textContent: unesc(m[2]) }); return o; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    removeAttribute(k) { delete this.attrs[k]; }, addEventListener() {}, removeEventListener() {}, appendChild: c => c,
    contains: () => false, focus() {}, blur() {}, querySelector: () => null, querySelectorAll: () => [], closest: () => null,
  };
  if (id) el.id = id;
  return el;
}
const byId = id => (ELS[id] = ELS[id] || mk(id));
const document = new Proxy({
  getElementById: byId, createElement: () => mk(''), body: mk(''), head: mk(''), documentElement: mk(''), activeElement: null,
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {},
}, { get: (t, k) => (k in t ? t[k] : any) });
const store = () => { const b = {}; return { getItem: k => (k in b ? b[k] : null), setItem: (k, v) => { b[k] = String(v); }, removeItem: k => { delete b[k]; } }; };
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document, localStorage: store(), sessionStorage: store(), navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} }, history: any,
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean, RegExp,
  Error, TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat,
  encodeURIComponent, decodeURIComponent, performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 1280,
  innerHeight: 900, scrollY: 0, scrollTo() {}, alert() {}, confirm: () => false, prompt: () => null,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any, Node: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);

// ── a made-up dashboard (no real names, ids or URLs) ─────────────────────────────────────────────────────────────────
const A1 = 'pub-1000000000000001', id = n => `ca-app-${A1}~00000000${n}`;
ctx.__DATA = {
  apps: [{ name: 'Demo Gallery' }, { name: 'Puzzle Quest' }],
  apps_catalog: [{ account_id: A1, app_id: id(11), app_name: 'Demo Gallery', rev: 50 },
                 { account_id: A1, app_id: id(12), app_name: 'Puzzle Quest', rev: 30 }],
  app_icons: { [id(11)]: 'https://icons.example.test/dg.png', [id(12)]: 'https://icons.example.test/pq.png' },
  accounts: [{ account_id: A1, label: 'Main' }],
};
ctx.__BASE = { units: [{ id: 'unit-101', app: 'Puzzle Quest', name: 'Banner · Home' },
                       { id: 'unit-102', app: 'Demo Gallery', name: 'Interstitial · Exit' }] };
ctx.__CALLS = [];
run(`DATA=__DATA; APP='';
  render=function(){ __CALLS.push('render'); };                   // the jump must not need a full render
  setApp=function(a){ __CALLS.push('setApp:'+a); };
  bRerender=function(){ __CALLS.push('bRerender'); };
  var __show=show; show=function(id){ __CALLS.push('show:'+id+' APP='+JSON.stringify(APP)+' nm='+document.getElementById('apk-nm').textContent); return __show(id); };`);

const $ = byId, out = {};
const H = () => ({ APP: run('APP'), nm: $('apk-nm').textContent, label: $('apk-btn').getAttribute('aria-label'),
  ic: $('appsel-ic').innerHTML, sel: $('appsel').value, opts: $('appsel').options.map(o => o.value),
  BUNIT: run('BUNIT'), BSEL: run('BSEL'), BLOADING: run('BLOADING'), calls: run('__CALLS.slice()') });
const step = (name, fn) => { try { out[name] = fn(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };
// the header as render() leaves it for `app` (the spy render is not the real one) — spelled out, not appSelSync(), so the
// setup is the same with or without the fix
const viewing = app => { run(`APP=${JSON.stringify(app)}; document.getElementById('appsel').innerHTML=appSelHtml(); appSelIcon();
  __CALLS.length=0;`); return H(); };

// an app in view, Baseline loaded → an alert row's jump to a placement of that app
step('before', () => viewing('Puzzle Quest'));
step('goto', () => { run(`BASELINE=__BASE; BSEL=null; BUNIT=null; bGotoUnit('unit-101')`); return H(); });
// an app in view with no AdMob row (an Uninstall-tab app, listed only while in view), Baseline not loaded yet → lazy jump
step('ghost_before', () => { run(`BASELINE=null; BLOADING=false; BSEL=null; BUNIT=null;`); return viewing('Ghost App'); });
step('ghost_goto', () => { run(`bGotoUnit('unit-102')`); return H(); });
// already on "All apps": the jump changes nothing in the header
step('all_goto', () => { viewing(''); run(`BASELINE=__BASE; BLOADING=false; BSEL=null; BUNIT=null; bGotoUnit('unit-102')`); return H(); });
process.stdout.write(JSON.stringify({ errors, out }));
