// App icons everywhere (owner: "sab jagah app ka icon aana chahiye") — the page side, rendered for real: runs the
// dashboard script (frontend/index.html's largest <script>) in a node vm with stub browser globals and a small DOM, on
//   * a synthetic Uninstall Studio site the REAL build code made (tests/studio_synth.py: two same-named "Demo Gallery"
//     apps under one account — one with GA4, one without) with SYNTHETIC icon URLs added to dashboard.app_icons, and
//   * the committed synthetic Review fixture (tests/fixtures/review_sample.json),
// and prints ONE JSON report; tests/test_app_icons_frontend.py asserts on it.
//   usage: node app_icons_frontend.js <script.js> <dir with dashboard.json + uninstall_studio.json + uninstall.json> <review_sample.json>
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const [scriptPath, dir, reviewPath] = process.argv.slice(2);
const J = n => JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8'));
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const classList = () => { const s = new Set(); return { add: (...a) => a.forEach(x => s.add(x)), remove: (...a) => a.forEach(x => s.delete(x)),
  toggle: (x, f) => { const on = f === undefined ? !s.has(x) : !!f; on ? s.add(x) : s.delete(x); return on; }, contains: x => s.has(x) }; };
function mk(id) { return { id, _html: '', attrs: {}, classList: classList(), style: { setProperty() {} }, dataset: {}, hidden: false, open: false,
  scrollTop: 0, scrollLeft: 0, scrollWidth: 0, clientWidth: 1000, offsetParent: {}, value: '',
  get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; },
  querySelector: () => mk('_q'), querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, appendChild() {},
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 20 }), focus() {}, scrollIntoView() {}, closest: () => null }; }
const ELS = {};
const document = new Proxy({
  getElementById: id => (/^(us-|appsel)/.test(String(id)) ? (ELS[id] = ELS[id] || mk(id)) : any),
  createElement: () => mk('_new'), body: mk('body'), head: mk('head'), documentElement: mk('html'),
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, activeElement: null,
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
ctx.__DASH = J('dashboard.json'); ctx.__STUDIO = J('uninstall_studio.json'); ctx.__UNI = J('uninstall.json');
const RV = JSON.parse(fs.readFileSync(reviewPath, 'utf8'));
ctx.__RDOC = RV.day; ctx.__RS = Object.assign({}, RV.state, { me: RV.me, open_day: RV.index.open_day });
const out = {};
function get(name, code) { try { out[name] = run(code); } catch (e) { errors.push(name + ': ' + e.message); } }

// ── the helpers on their own (a crafted catalog: two apps with the SAME name, only the first has a logo) ──────────────
get('helpers', `(()=>{ const keep=DATA;
  DATA={app_icons:{'id-one':'https://icons.example.test/one.png','id-bad':'javascript:void(0)'},
        apps_catalog:[{app_id:'id-one',app_name:'Same Name',rev:50},{app_id:'id-two',app_name:'Same Name',rev:10},{app_id:'id-bad',app_name:'Bad Url',rev:1}]};
  try { return JSON.stringify({
    own: appIconId('id-one','Same Name',16), twin: appIconId('id-two','Same Name',16), unknown: appIconId('id-none','Zed',20),
    by_name: appIcon('Same Name',16), no_id: appIconId('','Same Name',16), bad: appIconId('id-bad','Bad Url',16),
    inline: appIconId('id-one','Same Name',14,'ail'), big: appIconId('id-one','Same Name',32), chip: appChip('Same Name',18,'id-two'),
    chip_name: appChip('Same Name',18), sel_all: (APP='', appSelIcon(), document.getElementById('appsel-ic').innerHTML),
    sel_app: (APP='Same Name', appSelIcon(), document.getElementById('appsel-ic').innerHTML) }); }
  finally { DATA=keep; APP=''; } })()`);

// ── the Uninstall Studio, rendered: every name it prints carries its own icon ─────────────────────────────────────────
const RESET = `KWIN='30'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; UNIAPP=''; CURVIEW='USD';`;
run(`DATA=__DASH; UNI=__UNI; UNIERR=false; UNICOH={}; ${RESET} US._.load(__STUDIO);`);
get('studio', `(()=>{ ${RESET} uniScreen(); const A=US._.A(), N=US._.NOGA(), R=US._.R();
  const i0=R.length?R[0].a.i:0; US.openDrawer(i0);
  const o={ apps: A.map(a=>({i:a.i,id:a.id,nm:a.nm})), noga: N.map(n=>({id:n.id,nm:n.nm})),
    map: US._.map(), tbl: US._.tbl(), story: US._.story(), chg: US._.chg(), drawer: US._.drawer(),
    page: A.length?US._.page(A[0].id):'', tip_app: US._.TIPS.app(i0) };
  US.closeDrawer(); return JSON.stringify(o); })()`);

// ── the Review tab: the card heading and the Summary name each app with its icon (by app_id) ──────────────────────────
get('review', `(()=>{ const keep=DATA; const a0=__RDOC.apps[0];
  DATA={app_icons:{[a0.app_id]:'https://icons.example.test/review.png'},apps_catalog:[]};
  try { const cards={}; for(const a of __RDOC.apps) cards[a.key]=String(rvCardHtml(__RDOC,__RS,a.key,'live'));
    return JSON.stringify({first:a0.key, first_id:a0.app_id, keys:__RDOC.apps.map(a=>a.key), cards, summary:String(rvSummaryHtml(__RDOC,__RS,__RS.me))}); }
  finally { DATA=keep; } })()`);
process.stdout.write(JSON.stringify({ errors, out }));
