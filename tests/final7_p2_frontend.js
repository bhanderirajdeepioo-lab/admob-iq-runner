// GA4_FINAL_DAYS, step 2 — the page's words about when an Active users / Audience / Install value number turns final,
// read from the files' own lags (the Active file's consts.act_late_days, the Install value file's consts.iday_late), run
// for real: the dashboard script (the page's largest <script>) in a node vm with stub browser globals, on a SYNTHETIC
// pointer (no real names, ids or numbers) whose lags come from tests/test_final7_p2_frontend.py.
// The lags JSON (argv 3): {"act", "val"} — a missing / null one = a file written before the knob (no such field: the
// page's fallback, the old lag 3). Prints ONE JSON report.
// usage: node final7_p2_frontend.js <script.js> '<lags JSON>'
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath, lagsJson] = process.argv.slice(2);
const L = JSON.parse(lagsJson || '{}') || {};
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
function mk(tag) {
  const el = { tagName: String(tag || 'div').toUpperCase(), id: '', innerHTML: '', textContent: '', dataset: {}, children: [],
    style: { setProperty() {} }, classList: { add() {}, remove() {}, contains: () => false, toggle: () => false },
    setAttribute() {}, getAttribute: () => null, removeAttribute() {}, hasAttribute: () => false, appendChild: c => c, append() {},
    addEventListener() {}, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [], closest: () => null,
    contains: () => false, focus() {}, blur() {}, scrollIntoView() {}, replaceWith() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }) };
  return el;
}
const document = new Proxy({ getElementById: () => null, createElement: mk, body: mk('body'), head: mk('head'), documentElement: mk('html'),
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {} },
{ get: (t, k) => (k in t ? t[k] : any) });
const store = () => { const b = {}; return { getItem: k => (k in b ? b[k] : null), setItem: (k, v) => { b[k] = String(v); }, removeItem: k => { delete b[k]; } }; };
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  document, localStorage: store(), sessionStorage: store(), navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} },
  history: { length: 1, state: null, pushState() {}, replaceState() {}, go() {}, back() {}, forward() {} },
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean, RegExp,
  Error, TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat,
  encodeURIComponent, decodeURIComponent, performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 1280,
  innerHeight: 900, scrollY: 0, scrollTo() {}, scrollBy() {}, alert() {}, confirm: () => false, prompt: () => null,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any, Node: any,
};
ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const strip = h => String(h).replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, ' ').trim();
const out = {};
const step = (name, fn) => { try { out[name] = fn(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };

// the synthetic pointer: the Active file's and the Install value file's consts (a null lag: the key left out)
const act = { tile_days: 7 }, val = { h: 90 };
if (L.act != null) act.act_late_days = L.act;
if (L.val != null) val.iday_late = L.val;
ctx.__DATA = { active: { consts: act, apps: [] }, value: { consts: val, apps: [] } };
run('DATA=__DATA; UNI=null; APP="";');

step('helpers', () => JSON.parse(JSON.stringify(run('({late:actLate(), at1:actFinalAt(1), at30:actFinalAt(30), vlate:valLate(), v0:valFinalAt(0), v365:valFinalAt(365)})'))));
step('tip', () => run('actProvTip()'));
step('pill', () => run('actProvPill()'));
step('act_timing', () => strip(run('ACTTIMEXP=true; actTimingNote()')));
step('val_timing', () => strip(run('VALTIMEXP=true; valTimingNote()')));
// 👥 Audience: the phone card's day line (a made-up app's numbers)
step('au_phone', () => {
  const h = run(`AU._.sec.phone({a1:100,a28k:400,sl:500,inst:1000,kam:false,E:'2026-03-25',all:false,hs:'2025-01-01'})`);
  return strip((String(h).match(/<div class="au-h2s">(.*?)<\/div>/s) || [])[1] || '');
});
// 👥 Active users, All apps: the head's line under the strip (no app: only its words)
step('act_head', () => { const t = strip(run('actPortfolio([]).head')); return (t.match(/Old users = .*?faisla nahi\)\./) || [''])[0]; });
// 💰 Install value, an app's At a glance card while the money back waits (a made-up app with no weeks yet)
step('val_sum', () => { const t = strip(run('valSumCard({},{})')); return (t.match(/andaza hafte ke installs[^.]*?din baad/) || [''])[0]; });
// the page's source of every text this step derives (the fixed numbers before it never reappear)
step('src', () => {
  const src = fs.readFileSync(scriptPath, 'utf8');
  const OLD = ['GA4 activity 3 din me final hoti hai', "GA4 ~3 din tak late data jodta hai", 'activity 3 din me pakki',
    'GA4 ka data ~3 din me pakka hota hai', 'Old users ka badlaav ~6 din baad', 'Back next day ~6 din', 'Kamai har user ~6 din baad',
    'release + 7 din + 3 pakke din', '7 din pure hone ke ~5 din baad', 'Agle din wala number ~5 din baad',
    'mahina khatam hone ke ~95 din baad', 'Pehle din ki kamai ~5 din baad', 'ACT_PROV_TIP', 'ACT_PROV_PILL'];
  return { old: OLD.filter(s => src.includes(s)),
    derived: ['GA4 ka data ~${actLate()} din me pakka hota hai', 'andaza hafte ke installs ke 7 din pure hone ke ~${valFinalAt(0)} din baad',
      'Agle din wala number ~${valFinalAt(0)} din baad pakka, hafte wala ~${valFinalAt(7)} din baad, 30 din wala ~${valFinalAt(30)} din baad.',
      'mahina khatam hone ke ~${valFinalAt(90)} din baad; 1 saal wala ~${valFinalAt(365)} din baad.'].filter(s => !src.includes(s)),
    // each helper defined once (a second function of the same name would silently replace the page's own)
    twice: ['actLate', 'actFinalAt', 'actProvTip', 'actProvPill', 'valLate', 'valFinalAt']
      .filter(n => src.split('function ' + n + '(').length !== 2) };
});
out.errors = errors;
process.stdout.write(JSON.stringify(out));
