// Dashboard-wide phone fixes (mobile audits A + B) — the page side, run for real: the dashboard script (frontend/index.html's
// largest <script>) in a node vm with stub browser globals, a small DOM and a FAKE browser history (entries, an index, popstate
// fired when a step back / forward lands — after the current task, as a browser does). On SYNTHETIC data made up here:
//   * B-18 Recommendations: one ad unit with 3 out-of-range metrics = ONE placement, its weekly $ counted once (card + totals);
//   * B-11 the phone's Back button: the More menu, the App picker sheet, a Studio drawer and an app picked in the header each
//     keep ONE history step — Back closes / leaves it, closing it on the page takes the step off (no double Back), a close +
//     an open in one tap reuse the step, a re-render adds none, a Review #hash left behind is dropped;
//   * B-13 the toast: pointer-events:none on the box (a tap goes through to the page);
//   * B-01 the trend chart: drawn at its real width under 700px (text ≥ 10px), the 1000-unit drawing above;
//   * B-12 Alerts: the Telegram / Email status text from DATA.notify.
// Prints ONE JSON report; tests/test_mobile_global_frontend.py asserts on it.
//   usage: node mobile_global_frontend.js <script.js>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath] = process.argv.slice(2);
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// ── a small DOM ───────────────────────────────────────────────────────────────────────────────────────────────────────
const ELS = {};
function mk(tag) {
  const cls = new Set(), attrs = {};
  const el = {
    tagName: String(tag || 'div').toUpperCase(), id: '', innerHTML: '', textContent: '', dataset: {}, children: [], parentElement: null,
    style: { cssText: '', opacity: '', transition: '', setProperty() {} },
    classList: { add: (...a) => a.forEach(x => cls.add(x)), remove: (...a) => a.forEach(x => cls.delete(x)), contains: x => cls.has(x),
      toggle: (x, f) => { const on = f === undefined ? !cls.has(x) : !!f; on ? cls.add(x) : cls.delete(x); return on; } },
    get className() { return [...cls].join(' '); }, set className(v) { cls.clear(); String(v).split(/\s+/).filter(Boolean).forEach(x => cls.add(x)); },
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
const SCREEN = { id: 'overview' };   // the screen on show (what document.querySelector('.screen.on') answers)
const document = new Proxy({
  getElementById: byId, createElement: mk, body: BODY, head: mk('head'), documentElement: mk('html'),
  querySelector: sel => (sel === '.screen.on' ? { dataset: { screen: SCREEN.id } } : null), querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
}, { get: (t, k) => (k in t ? t[k] : any) });
// ── a fake browser history: entries + index; go() lands after the current task and fires popstate ─────────────────────
const LOC = { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} };
const POP = [];   // popstate listeners
const HIST = { entries: [{ state: null, url: '/' }], idx: 0, calls: [], pending: [] };
const setUrl = u => { const h = String(u || '/').indexOf('#'); LOC.hash = h >= 0 ? String(u).slice(h) : ''; };
const history = {
  get length() { return HIST.entries.length; }, get state() { return HIST.entries[HIST.idx].state; },
  pushState(st, _t, url) { HIST.calls.push('push'); const u = url == null ? HIST.entries[HIST.idx].url : url;
    HIST.entries.splice(HIST.idx + 1); HIST.entries.push({ state: JSON.parse(JSON.stringify(st)), url: u }); HIST.idx++; setUrl(u); },
  replaceState(st, _t, url) { HIST.calls.push('replace'); const e = HIST.entries[HIST.idx]; e.state = st == null ? null : JSON.parse(JSON.stringify(st));
    if (url != null) { e.url = url; setUrl(url); } },
  go(n) { HIST.calls.push('go(' + n + ')'); HIST.pending.push(n); }, back() { history.go(-1); }, forward() { history.go(1); },
};
// a pending step back / forward lands: the index moves, the URL follows, popstate fires (null when it would leave the page)
function land() { while (HIST.pending.length) { const n = HIST.pending.shift(), to = HIST.idx + n;
  if (to < 0) { HIST.left = true; continue; } if (to >= HIST.entries.length) continue;
  HIST.idx = to; setUrl(HIST.entries[to].url); POP.forEach(f => f({ type: 'popstate', state: HIST.entries[to].state })); } }
const store = () => { const b = {}; return { getItem: k => (k in b ? b[k] : null), setItem: (k, v) => { b[k] = String(v); }, removeItem: k => { delete b[k]; } }; };
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  document, localStorage: store(), sessionStorage: store(), navigator: any, location: LOC, history,
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener: (type, fn) => { if (type === 'popstate') POP.push(fn); }, removeEventListener() {},
  DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean, RegExp,
  Error, TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat,
  encodeURIComponent, decodeURIComponent, performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 1280,
  innerHeight: 900, scrollY: 0, scrollTo() {}, alert() {}, confirm: () => false, prompt: () => null,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any, Node: any,
};
ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const tick = () => new Promise(r => setImmediate(r));          // the microtask that syncs the history steps runs
const settle = async () => { await tick(); land(); await tick(); land(); await tick(); };
const H = () => ({ idx: HIST.idx, len: HIST.entries.length, state: HIST.entries[HIST.idx].state, hash: LOC.hash, left: !!HIST.left,
  st: run('HB.st.map(x=>x.tag)'), depth: run('HB.depth'), busy: run('HB.busy'), calls: HIST.calls.splice(0) });
const userBack = async () => { history.back(); HIST.calls.pop(); land(); await settle(); };   // the reader's Back (not the page's)
const reset = async () => { run('HB.st.length=0; HB.busy=false; HB.mute=0;'); await settle();
  HIST.entries = [{ state: null, url: '/' }]; HIST.idx = 0; HIST.calls = []; HIST.pending = []; HIST.left = false; LOC.hash = '';
  run('HB.depth=0;'); BODY.classList.remove('nav-open'); SCREEN.id = 'overview'; };
const out = {};
const step = async (name, fn) => { try { out[name] = await fn(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };

(async () => {
  // ── B-18: Recommendations on a made-up dashboard (no real names, ids or money) ──────────────────────────────────────
  const days = ['2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04', '2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08'];
  const daily = usdPerDay => days.map(d => [d, Math.round(usdPerDay * 1e6), 1000, 1200, 1100, 10]);
  ctx.__DATA = {
    today_date: '2026-01-08', currency: 'USD', apps: [], app_icons: {}, apps_catalog: [],
    placements: [
      { id: 'ca-app-pub-0000000000000001/1111111111', name: 'splash_open', app: 'Demo Gallery', daily: daily(1000) },   // $7,000 / 7 days
      { id: 'ca-app-pub-0000000000000001/2222222222', name: 'home_banner', app: 'Demo Gallery', daily: daily(300) },    // $2,100
      { id: 'ca-app-pub-0000000000000002/3333333333', name: 'list_native', app: 'Puzzle Quest', daily: daily(100) },    // $700
    ],
    range_alerts: [   // splash_open: 3 metrics out of range (CTR, show rate, eCPM) — one placement; home_banner: 1 metric
      { id: 'ca-app-pub-0000000000000001/1111111111', place: 'splash_open', app: 'Demo Gallery', metric: 'ctr', message: 'CTR 4.1% — below approved range 4.5%–5.2%' },
      { id: 'ca-app-pub-0000000000000001/1111111111', place: 'splash_open', app: 'Demo Gallery', metric: 'show', message: 'Show rate 71.0% — below approved range 80.0%–84.0%' },
      { id: 'ca-app-pub-0000000000000001/1111111111', place: 'splash_open', app: 'Demo Gallery', metric: 'ecpm', message: 'eCPM $11.60 — above approved range $4.00–$10.40' },
      { id: 'ca-app-pub-0000000000000001/2222222222', place: 'home_banner', app: 'Demo Gallery', metric: 'ctr', message: 'CTR 0.9% — above approved range 0.4%–0.8%' },
    ],
    recommendations: { items: [   // engine recs: list_native once, and splash_open AGAIN (a second action for the same placement)
      { action: 'Add mediation networks / enable bidding', place: 'list_native (Puzzle Quest)', app: 'Puzzle Quest', reason: 'fill sirf 60%', confidence: 'high' },
      { action: 'Add mediation networks / enable bidding', place: 'splash_open (Demo Gallery)', app: 'Demo Gallery', reason: 'fill sirf 70%', confidence: 'high' },
    ], root_cause: [] },
    deductions: { rows: [] },
  };
  await step('reco_rows', () => { run('DATA=__DATA; APP=""; CURVIEW=null;');
    run('var __revCalls=0;');
    const rows = run(`recoRangeRows(DATA.range_alerts,(p,a)=>{ __revCalls++; return p==='splash_open'?7000:2100; })`);
    return { rows: JSON.parse(JSON.stringify(rows)), revCalls: run('__revCalls'),
      byName: JSON.parse(JSON.stringify(run(`recoRangeRows([{place:'x',app:'A',message:'m1'},{place:'x',app:'A',message:'m1'},{place:'x',app:'B',message:'m2'}],()=>5)`))),
      empty: JSON.parse(JSON.stringify(run('recoRangeRows([],()=>1)'))) }; });
  await step('reco_totals', () => JSON.parse(JSON.stringify(run(`recoTotals([{rows:[{place:'a',app:'X',rev:10},{place:'b',app:'X',rev:5}]},{rows:[{place:'a (X)',app:'X',rev:10},{place:'c',app:'Y',rev:1}]}],r=>String(r.place).replace(/\\s*\\([^)]*\\)\\s*$/,'')+'|'+r.app)`))));
  await step('reco_screen', () => { const s = run('renderReco()'); return { html: s.innerHTML }; });
  await step('reco_screen_inr', () => { run('DATA.usd_inr=90; CURVIEW="INR";'); const s = run('renderReco()'); run('CURVIEW=null; delete DATA.usd_inr;'); return { html: s.innerHTML }; });

  // ── B-11: the phone's Back button ──────────────────────────────────────────────────────────────────────────────────
  run(`var __CALLS=[]; render=function(){ __CALLS.push('render'); }; show=function(id){ __CALLS.push('show:'+id); __setScreen(id); };
       uniBack=function(){ __CALLS.push('uniBack'); setApp(''); }; actBack=function(){ __CALLS.push('actBack'); setApp(''); };
       valBack=function(){ __CALLS.push('valBack'); setApp(''); };`);
  ctx.__setScreen = id => { SCREEN.id = id; };
  const calls = () => run('__CALLS.splice(0)');
  await step('boot', () => ({ listeners: POP.length, depth: run('HB.depth'), st: run('HB.st.length') }));
  await step('nav_open', async () => { await reset(); run('toggleNav()'); await settle(); return { open: BODY.classList.contains('nav-open'), h: H() }; });
  await step('nav_back', async () => { await userBack(); return { open: BODY.classList.contains('nav-open'), h: H() }; });
  await step('nav_close_on_page', async () => { await reset(); run('toggleNav()'); await settle(); H();
    run('closeNav()'); await settle(); const h = H(); await userBack(); return { h, after_extra_back: H() }; });   // one Back would now leave the page
  await step('nav_toggle_twice', async () => { await reset(); run('toggleNav(); toggleNav();'); await settle(); return H(); });
  await step('drawer', async () => { await reset(); run('var __closed=0; hbOv("vs-drawer",true,()=>{ __closed++; });'); await settle(); const a = H();
    run('hbOv("vs-drawer",true,()=>{ __closed++; })'); await settle(); const again = H();   // ‹ › re-opens: still one step
    await userBack(); return { a, again, b: H(), closed: run('__closed') }; });
  await step('drawer_x', async () => { await reset(); run('var __closed=0; hbOv("us-drawer",true,()=>{ __closed++; });'); await settle(); H();
    run('hbOv("us-drawer",false)'); await settle(); return { h: H(), closed: run('__closed') }; });
  await step('app_pick', async () => { await reset(); run('APP=""'); SCREEN.id = 'value';
    run('hbPush("apk",()=>{})'); await settle(); const sheet = H();
    run('hbDrop("apk"); setApp("Demo Gallery");'); await settle(); const picked = H(); calls();   // the sheet's close + the pick: one tap
    await userBack(); return { sheet, picked, back: H(), APP: run('APP'), calls: calls() }; });
  await step('app_back_overview', async () => { await reset(); run('APP=""'); SCREEN.id = 'overview'; run('setApp("Puzzle Quest")'); await settle(); calls();
    await userBack(); return { h: H(), APP: run('APP'), calls: calls() }; });
  await step('app_all_apps_on_page', async () => { await reset(); run('APP=""'); SCREEN.id = 'uninstall'; run('setApp("Puzzle Quest")'); await settle(); H();
    run('setApp("")'); await settle(); return { h: H(), APP: run('APP') }; });   // "← All apps" / the picker's All apps: the step goes too
  await step('app_switch', async () => { await reset(); run('APP=""; setApp("Puzzle Quest");'); await settle(); H();
    run('setApp("Demo Gallery")'); await settle(); return H(); });   // one app → another: still one step
  await step('muted', async () => { await reset(); run('HB.mute++; hbPush("appdetail",()=>{}); HB.mute--;'); await settle(); return H(); });
  await step('stack', async () => { await reset(); run('var __u=[]; hbPush("app",()=>__u.push("app")); hbPush("vs-drawer",()=>__u.push("drawer"));'); await settle(); const two = H();
    await userBack(); const one = { h: H(), u: run('__u.slice()') }; await userBack(); return { two, one, zero: H(), u: run('__u.slice()') }; });
  await step('forward', async () => { await reset(); run('hbPush("nav",()=>{})'); await settle(); await userBack(); H();
    history.forward(); HIST.calls.pop(); land(); await settle(); return H(); });   // a Forward onto a closed step: stepped back off
  await step('review_hash', async () => { await reset(); HIST.entries[0].url = '/#review'; LOC.hash = '#review'; SCREEN.id = 'review';
    run('toggleNav()'); await settle(); const open = H();
    SCREEN.id = 'deductions'; history.replaceState(null, '', '/'); HIST.calls.pop();   // what Review's rvOnShow does on leaving
    run('closeNav()'); await settle(); return { open, after: H(), base_url: HIST.entries[0].url }; });
  await step('structure', () => ({ hbAppUndo: run('String(hbAppUndo)'), hbAdUndo: run('String(hbAdUndo)'), apkOpen: run('String(apkOpen)'),
    apkClose: run('String(apkClose)'), adBack: run('String(adBack)') }));

  // ── B-13: the toast ─────────────────────────────────────────────────────────────────────────────────────────────────
  await step('toast', () => { run('bToast("Saved")'); const t = byId('btoast'); return t ? { css: t.style.cssText, role: t.getAttribute('role'), text: t.textContent, inBody: BODY.children.includes(t) } : null; });

  // ── B-01: the trend chart ───────────────────────────────────────────────────────────────────────────────────────────
  await step('chart', () => { const m = days.slice(0, 7), v = [120, 340, 560, 410, 980, 1500, 1320];
    const narrow = run(`bTrendChart(${JSON.stringify(m)},${JSON.stringify(v)},{cw:319,fmt:v=>'$'+Math.round(v),xlab:fmtD,spend:[100,200,300,400,500,600,700]})`);
    const wide = run(`bTrendChart(${JSON.stringify(m)},${JSON.stringify(v)},{fmt:v=>'$'+Math.round(v),xlab:fmtD})`);
    run('innerWidth=375'); const phone = run(`bTrendChart(${JSON.stringify(m)},${JSON.stringify(v)},{fmt:v=>'$'+Math.round(v),xlab:fmtD})`); run('innerWidth=1280');
    // btcFit: the drawn chart measured on screen at another width → redrawn there (same data, same id); 700px+ → 1000 units
    const id = /id="([^"]+)"/.exec(narrow)[1], fit = w => { const sv = { id, isConnected: true, html: null, getAttribute: k => (k === 'data-w' ? '319' : null),
      getBoundingClientRect: () => ({ width: w }), set outerHTML(v) { this.html = v; } }; ctx.__sv = sv; run('btcFit(__sv)'); return sv.html; };
    // 30 days on a wide chart: the date labels never touch (the coordinator saw "30 Sep" on "1 Oct" at 1680px), the last kept
    const d30 = Array.from({ length: 30 }, (_, i) => '2026-01-' + String(i + 1).padStart(2, '0')), v30 = d30.map((_, i) => 500 + (i * 37) % 300);
    const wide30 = run(`bTrendChart(${JSON.stringify(d30)},${JSON.stringify(v30)},{fmt:v=>'$'+Math.round(v),xlab:fmtD})`);
    const narrow30 = run(`bTrendChart(${JSON.stringify(d30)},${JSON.stringify(v30)},{cw:304,fmt:v=>'$'+Math.round(v),xlab:fmtD})`);
    return { wide30, narrow30, narrow, wide, phone, guess: [run('btcGuessW(0)'), run('btcGuessW(320)')], id, kept: run('BTC.has(' + JSON.stringify(id) + ')'),
      fit400: fit(400), fit325: fit(325), fit0: fit(0), fit980: fit(980) }; });

  // ── B-12: Alerts notification status (read-only text) ───────────────────────────────────────────────────────────────
  await step('notify', () => { const o = {};
    run('delete DATA.notify'); o.none = [run('ntSt("telegram")'), run('ntNote()')];
    run('DATA.notify={dry_run:true,telegram:false,email:false}'); o.dry = [run('ntSt("telegram")'), run('ntSt("email")'), run('ntNote()')];
    run('DATA.notify={dry_run:false,telegram:true,email:false}'); o.tg = [run('ntSt("telegram")'), run('ntSt("email")'), run('ntNote()')];
    run('delete DATA.notify'); return o; });

  process.stdout.write(JSON.stringify({ errors, out }));
})().catch(e => { errors.push('MAIN ' + (e.stack || e.message)); process.stdout.write(JSON.stringify({ errors, out })); });
