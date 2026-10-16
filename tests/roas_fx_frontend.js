// 💰 Marketing ROAS tab — the $ view at each day's own INR→USD rate (owner-approved), run for real: the dashboard script
// (frontend/index.html's largest <script>) in a node vm with stub browser globals; renderRoas() is the page's own. The
// dashboards come from tests/test_roas_fx_dated.py (the REAL build code on SYNTHETIC data: made-up names, ids and money):
//   dated — the roas payload WITH daily_dated (spend_fx "dated"), one — the same spend WITHOUT it (the payload as before),
//   eur — the dated payload re-labelled as a non-INR spend currency (the page must keep ONE rate and its old note).
// Each is rendered in $ and in ₹ (CURVIEW), all apps and one app; and the screens one tap away read in both views
// (spendByApp = the app page, hubSpend, the date-wise table, Overview) — they must show the tab's own spend.
// Prints ONE JSON report the pytest asserts on.
// usage: node roas_fx_frontend.js <script.js> <fixture.json>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath, fixturePath] = process.argv.slice(2);
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
function mk(tag) {
  const el = { tagName: String(tag || 'div').toUpperCase(), dataset: {}, style: {}, className: '', _h: '', children: [],
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} }, setAttribute() {}, getAttribute: () => null,
    appendChild(c) { el.children.push(c); return c; }, addEventListener() {}, removeEventListener() {},
    querySelector: () => null, querySelectorAll: () => [] };
  Object.defineProperty(el, 'innerHTML', { get: () => el._h, set: v => { el._h = String(v); } });
  return el;
}
const document = new Proxy({ createElement: mk, body: mk('body'), head: mk('head'), documentElement: mk('html') },
  { get: (t, k) => (k in t ? t[k] : any) });
const store = () => { const b = {}; return { getItem: k => (k in b ? b[k] : null), setItem: (k, v) => { b[k] = String(v); }, removeItem: k => { delete b[k]; } }; };
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  document, localStorage: store(), sessionStorage: store(), navigator: any, history: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} },
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean, RegExp,
  Error, TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat, unescape, escape,
  encodeURIComponent, decodeURIComponent, performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 375,
  innerHeight: 812, scrollY: 0, scrollTo() {}, alert() {}, confirm: () => false, prompt: () => null,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any, Node: any,
};
ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
ctx.__FX = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const out = {}, other = {};
const set = (dash, view, app) => `DATA=JSON.parse(JSON.stringify(__FX[${JSON.stringify(dash)}])); window.__ax=null; RANGE='all';
  RCUSTOM={from:'',to:''}; APP=${JSON.stringify(app)}; CURVIEW=${JSON.stringify(view)};`;
for (const dash of Object.keys(ctx.__FX).filter(k => k !== 'app')) {
  for (const view of ['USD', 'INR']) {
    for (const app of ['', ctx.__FX.app]) {
      const k = `${dash}|${view}|${app ? 'app' : 'all'}`;
      try { out[k] = run(set(dash, view, app) + 'renderRoas().innerHTML'); } catch (e) { errors.push(k + ': ' + (e.stack || e.message)); }
    }
    const k = `${dash}|${view}`;
    try {
      other[k] = JSON.parse(run(set(dash, view, '') + `JSON.stringify({spa: spendByApp(curWin()), hub: hubSpend(__FX.app),
        dw: dateWiseRows(curWinArr()).reduce((t, r) => t + r.spend, 0), ov: renderOverview().innerHTML})`));
    } catch (e) { errors.push(k + ' other: ' + (e.stack || e.message)); }
  }
}
run(`CURVIEW=null; APP='';`);
process.stdout.write(JSON.stringify({ errors, out, other }));
