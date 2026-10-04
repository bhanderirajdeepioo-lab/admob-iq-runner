// Auto-refresh (frontend/index.html's setInterval(refreshData, 300000)): the owner's report — "page pe niche me data
// dekh raha hota he aur thodi der me auto refresh hoke blink hota he aur page ke starting me chala jata he" (reading
// lower down the page, the 5-min poll fires, the page blinks and jumps back to the top). Two causes, both fixed in
// refreshData()/show():
//   1. refreshData() used to call render() + show() on EVERY tick even when the robot hadn't produced a new build —
//      it now compares the fetched DATA.generated_at against LAST_BUILD and, when unchanged, only updates the "X min
//      ago" text (no DOM touched at all).
//   2. When the build DID change, render() always ends with show('overview') (a plain scrollTo(top:0)), and the
//      caller then shows the real screen again — so the page always ended at scrollY 0 regardless of where the
//      reader was. refreshData() now sets REFRESH_SILENT while it rebuilds; show() (and openApp/openAppDetail/
//      setApp's own trailing scrollTo) skip the jump-to-top while it's set, and refreshData() restores the reader's
//      exact scrollY afterward (requestAnimationFrame, clamped to the rebuilt page's height) and never leaves a new
//      Back-button step (HB.mute, already the mechanism for "the same view rebuilt").
// Runs the real page script in a node vm with a small fake DOM (same recipe as mobile_global_frontend.js for the
// Back-button fix) — render()/show()/loadDashboardData() are swapped for lightweight stand-ins per scenario so this
// stays fast and needs no dashboard fixture; one scenario calls the REAL show() to check its own scrollTo/closeNav
// gating directly. Prints ONE JSON report; tests/test_refresh_frontend.py asserts on it.
//   usage: node refresh_frontend.js <script.js>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath] = process.argv.slice(2);
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// ── a small DOM (same shape as mobile_global_frontend.js) ───────────────────────────────────────────────────────────
const ELS = {};
function mk(tag) {
  const cls = new Set(), attrs = {};
  const el = {
    tagName: String(tag || 'div').toUpperCase(), id: '', innerHTML: '', textContent: '', dataset: {}, children: [], parentElement: null,
    style: { cssText: '', setProperty() {} },
    classList: { add: (...a) => a.forEach(x => cls.add(x)), remove: (...a) => a.forEach(x => cls.delete(x)), contains: x => cls.has(x),
      toggle: (x, f) => { const on = f === undefined ? !cls.has(x) : !!f; on ? cls.add(x) : cls.delete(x); return on; } },
    setAttribute(k, v) { attrs[k] = String(v); if (k === 'id') { el.id = String(v); ELS[el.id] = el; } }, getAttribute: k => (k in attrs ? attrs[k] : null),
    removeAttribute(k) { delete attrs[k]; }, hasAttribute: k => k in attrs,
    appendChild(c) { c.parentElement = el; el.children.push(c); if (c.id) ELS[c.id] = c; return c; }, append(...cs) { cs.forEach(c => el.appendChild(c)); },
    addEventListener() {}, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [], closest: () => null,
    contains: () => false, focus() {}, blur() {}, scrollIntoView() {}, replaceWith() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }),
  };
  return el;
}
const byId = id => ELS[id] || null;
const BODY = mk('body');
const DOC_ROOT = mk('html');   // document.documentElement — its .scrollHeight drives the clamped scroll-restore
const SCREEN = { id: 'overview' };   // what document.querySelector('.screen.on') answers
const document = new Proxy({
  getElementById: byId, createElement: mk, body: BODY, head: mk('head'), documentElement: DOC_ROOT,
  querySelector: sel => (sel === '.screen.on' ? { dataset: { screen: SCREEN.id } } : null), querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
}, { get: (t, k) => (k in t ? t[k] : any) });
['tb-title', 'tb-sub', 'nav-alert', 'fresh-txt', 'tab-alert'].forEach(id => { const e = mk('div'); e.setAttribute('id', id); });
let RAF_Q = [];
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  document, localStorage: { getItem: () => null, setItem() {}, removeItem() {} }, sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  navigator: any, location: { href: '', search: '', hash: '', pathname: '/', reload() {} },
  history: { state: null, pushState() {}, replaceState() {}, go() {}, back() {}, forward() {}, length: 1 },
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: fn => { RAF_Q.push(fn); return RAF_Q.length; }, cancelAnimationFrame() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean,
  Error, TypeError, Set, Map, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat,
  encodeURIComponent, decodeURIComponent, performance: { now: () => 0 }, getComputedStyle: () => any,
  innerWidth: 1280, innerHeight: 900, scrollY: 0,
  scrollTo(...a) { ctx.__scrollCalls.push(a); if (a.length === 1 && a[0] && typeof a[0] === 'object') { if ('top' in a[0]) ctx.scrollY = a[0].top; } else ctx.scrollY = a[1]; },
  alert() {}, confirm: () => false, prompt: () => null,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any, Node: any,
};
ctx.__scrollCalls = [];
ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const tick = () => new Promise(r => setImmediate(r));
const flushRAF = () => { const q = RAF_Q.splice(0); RAF_Q = []; q.forEach(fn => { try { fn(); } catch (e) { errors.push('raf: ' + e.message); } }); };
const out = {};
const step = async (name, fn) => { try { out[name] = await fn(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };
run('var __REAL_SHOW = show;');   // scenarios 1-3 stub out show() — scenario 4 needs the REAL one back

(async () => {
  // ── 1. same build: refreshData() must not touch the DOM at all — only the fetched DATA + LAST_BUILD update ────────
  await step('same_build_skips_render', async () => {
    run(`DATA = {generated_at: 'B1', v: 1};
         LAST_BUILD = 'B1';
         var __render = 0, __show = [];
         render = function () { __render++; };
         show = function (id) { __show.push(id); };
         openApp = function () { __show.push('openApp'); };
         openAppDetail = function () { __show.push('openAppDetail'); };
         goPlacement = function () { __show.push('goPlacement'); };
         var __fresh = 0;
         updateFreshness = function () { __fresh++; };
         loadDashboardData = function () { return Promise.resolve({generated_at: 'B1', v: 2}); };`);
    SCREEN.id = 'uninstall';
    await run('refreshData()');
    await tick();
    return {
      render: run('__render'), show: run('__show.slice()'), fresh: run('__fresh'),
      dataV: run('DATA.v'), lastBuild: run('LAST_BUILD'), muteAfter: run('HB.mute'), silentAfter: run('REFRESH_SILENT'),
    };
  });

  // ── 2. changed build: refreshData() DOES rebuild, in place, silently — and restores the reader's exact scroll ─────
  await step('changed_build_renders_silently_and_restores_scroll', async () => {
    run(`DATA = {generated_at: 'B1', v: 1};
         LAST_BUILD = 'B1';
         var __renderSilent = null, __showSilent = null, __muteDuring = null, __showId = null;
         render = function () { __renderSilent = REFRESH_SILENT; __muteDuring = HB.mute; };
         show = function (id) { __showSilent = REFRESH_SILENT; __showId = id; scrollY = 0; };   // the rebuild itself nudges
           // the browser's scroll (as a real DOM teardown/rebuild can) — the restore below must undo exactly this
         loadDashboardData = function () { return Promise.resolve({generated_at: 'B2', v: 2}); };`);
    SCREEN.id = 'uninstall';
    ctx.scrollY = 743; ctx.innerHeight = 900; DOC_ROOT.scrollHeight = 5000;   // plenty of room: the exact Y comes back
    ctx.__scrollCalls.length = 0;
    await run('refreshData()');
    await tick();
    const silentRightAfter = run('REFRESH_SILENT'), muteRightAfter = run('HB.mute');   // finally{} already ran by here
    flushRAF();   // the scheduled silentScrollRestore(preY) fires
    return {
      renderSilentDuring: run('__renderSilent'), showSilentDuring: run('__showSilent'), showId: run('__showId'),
      muteDuring: run('__muteDuring'), silentRightAfter, muteRightAfter,
      lastBuild: run('LAST_BUILD'), dataV: run('DATA.v'),
      scrollYAfterRaf: ctx.scrollY, scrollCalls: ctx.__scrollCalls.length,
    };
  });

  // ── 3. the restore clamps to the NEW page height — never scrolls past the bottom of a page that got shorter ──────
  await step('scroll_restore_clamps_to_new_height', async () => {
    run(`DATA = {generated_at: 'B2', v: 2};
         LAST_BUILD = 'B2';
         render = function () {}; show = function (id) {};
         loadDashboardData = function () { return Promise.resolve({generated_at: 'B3', v: 3}); };`);
    SCREEN.id = 'overview';
    ctx.scrollY = 5000; ctx.innerHeight = 900; DOC_ROOT.scrollHeight = 1200;   // only ~300px of room after the rebuild
    ctx.__scrollCalls.length = 0;
    await run('refreshData()');
    await tick();
    flushRAF();
    return { scrollY: ctx.scrollY, calls: ctx.__scrollCalls.slice() };
  });

  // ── 4. the REAL show(): REFRESH_SILENT suppresses scrollTo(top:0) AND closeNav(); unset, it behaves as before ────
  await step('show_real_no_scroll_or_navclose_when_silent', async () => {
    SCREEN.id = 'overview';
    BODY.classList.add('nav-open');
    ctx.__scrollCalls.length = 0;
    run('REFRESH_SILENT = true;');
    run(`__REAL_SHOW('overview')`);
    const duringSilent = { scrollCalls: ctx.__scrollCalls.length, navOpen: BODY.classList.contains('nav-open') };
    BODY.classList.add('nav-open');   // put it back open for the control case
    ctx.__scrollCalls.length = 0;
    run('REFRESH_SILENT = false;');
    run(`__REAL_SHOW('overview')`);
    const normal = { scrollCalls: ctx.__scrollCalls.length, navOpen: BODY.classList.contains('nav-open') };
    run('REFRESH_SILENT = false;');
    return { duringSilent, normal };
  });

  // ── 5. rerender() — ₹/$, Period, a lazy file landing: the SAME view rebuilt. Owner (iPhone): "kuchh change karte he to upar
  // chala jata he page". The real show() must not jump to the top inside it, and the reader's place comes back (clamped). ──
  await step('rerender_keeps_place', async () => {
    run(`render = function () { scrollY = 0; };   // the teardown: #screens emptied, the page clamped to the top
         show = __REAL_SHOW; REFRESH_SILENT = false;`);
    const one = (fn, y, h) => { ctx.scrollY = y; ctx.innerHeight = 900; DOC_ROOT.scrollHeight = h; ctx.__scrollCalls.length = 0;
      const i0 = run('SP.st.intent'); run(fn);
      return { scrollY: ctx.scrollY, calls: ctx.__scrollCalls.slice(), keep: run('SP.keep'), mute: run('HB.mute'), quiet: run('SP.st.intent') === i0 }; };
    SCREEN.id = 'movers';
    const r = { rerender: one('rerender()', 2500, 6000), cur: one('toggleCur()', 1800, 6000), short: one('rerender()', 5000, 3000) };
    run('REFRESH_SILENT = false;');
    ctx.__scrollCalls.length = 0; const i0 = run('SP.st.intent'); run(`__REAL_SHOW('overview')`);   // a real screen change still jumps — on purpose
    r.nav = { calls: ctx.__scrollCalls.slice(), intent: run('SP.st.intent') > i0 };
    return r;
  });

  process.stdout.write(JSON.stringify({ errors, out }));
})().catch(e => { errors.push('MAIN ' + (e.stack || e.message)); process.stdout.write(JSON.stringify({ errors, out })); });
