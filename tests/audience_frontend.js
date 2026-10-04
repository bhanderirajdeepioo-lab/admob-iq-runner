// 👥 Audience tab (frontend/index.html) — the page side, run for real: the dashboard script (the page's largest <script>)
// in a node vm with stub browser globals, a small DOM, a FAKE browser history and the document listeners recorded (so
// clicks / changes / toggles / touches reach the page's own handlers), on the SYNTHETIC world tests/test_audience_frontend.py
// builds (made-up apps, ids and money — no real data). It reports:
//   * the render: every section, the tags (GA4 / andaza / being read), the strip, the table, the module panels;
//   * the numbers the page works out: buckets per app, the all-apps pool (dead / dead_lo on tiered months, journey,
//     long-term, money), the most dead / active month, $ and ₹ strings;
//   * the top bar drives the view: its App (setApp — a table row sets it too, so the top bar names the app tapped), the
//     phone's Back button (its 'app' step), an app the top bar has but Audience has no row for, its ₹ / $ (toggleCur);
//     no App picker / currency buttons / title block of the screen's own;
//   * the all-apps table's phone form (.au-ph: installed under the name, short numbers, a tip "t" with the full ones; a
//     tap on a number shows that tip and does not open the app, a tap on the name does);
//   * "Kyun? ▸" folds, the money mode chips, "Show all months";
//   * "Paise ka calculator": every app's one-open money, every lever combination (app and All apps), the card as it
//     renders (apps + All apps, $ and ₹), the all-apps table's money and its fixed order, the chips (set, lit, remembered,
//     restored by a page load's boot, bad saved values ignored), a row of the opens table as a lever;
//   * the 5-min refresh with a new build: the view comes back as it was (app, ₹, mode, opens, eCPM, day, open folds), silently;
//   * the tooltip rule: a mouse hovers, a TAP pins, a swipe never pins; the chart's numbers on hover;
//   * no pointer (the switch off): the screen says so and the nav item stays hidden.
// Prints ONE JSON report; tests/test_audience_frontend.py asserts on it.
//   usage: node audience_frontend.js <script.js> <fixture.json>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath, fxPath] = process.argv.slice(2);
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const ELS = {};
function mk(tag) {
  const cls = new Set(), attrs = {}, on = {};
  const el = {
    tagName: String(tag || 'div').toUpperCase(), id: '', innerHTML: '', textContent: '', dataset: {}, children: [], parentElement: null,
    style: { cssText: '', visibility: '', setProperty() {} }, clientWidth: 0, clientHeight: 0, offsetWidth: 0, offsetHeight: 0, on, hidden: false,
    classList: { add: (...a) => a.forEach(x => cls.add(x)), remove: (...a) => a.forEach(x => cls.delete(x)), contains: x => cls.has(x),
      toggle: (x, f) => { const o = f === undefined ? !cls.has(x) : !!f; o ? cls.add(x) : cls.delete(x); return o; } },
    get className() { return [...cls].join(' '); }, set className(v) { cls.clear(); String(v).split(/\s+/).filter(Boolean).forEach(x => cls.add(x)); },
    setAttribute(k, v) { attrs[k] = String(v); if (k === 'id') { el.id = String(v); ELS[el.id] = el; } }, getAttribute: k => (k in attrs ? attrs[k] : null),
    removeAttribute(k) { delete attrs[k]; }, hasAttribute: k => k in attrs,
    appendChild(c) { c.parentElement = el; el.children.push(c); return c; }, append(...cs) { cs.forEach(c => el.appendChild(c)); },
    addEventListener(t, f) { (on[t] = on[t] || []).push(f); }, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [], closest: () => null,
    contains: () => false, focus() {}, blur() {}, scrollIntoView() {}, replaceWith() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }),
  };
  return el;
}
const BODY = mk('body');
['tb-title', 'tb-sub', 'nav-alert', 'tab-alert', 'banner'].forEach(id => mk('div').setAttribute('id', id));
const SCREEN = { id: 'overview' };
const DOCL = {};
const document = new Proxy({
  getElementById: id => ELS[id] || null, createElement: mk, body: BODY, head: mk('head'), documentElement: mk('html'),
  querySelector: sel => (sel === '.screen.on' ? { dataset: { screen: SCREEN.id } } : null), querySelectorAll: () => [],
  addEventListener(t, f) { (DOCL[t] = DOCL[t] || []).push(f); }, removeEventListener() {},
}, { get: (t, k) => (k in t ? t[k] : any) });
const fire = (type, e) => (DOCL[type] || []).forEach(f => f(Object.assign({ preventDefault() {}, stopPropagation() {} }, e)));
const LOC = { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} };
const POP = [];
const HIST = { entries: [{ state: null, url: '/' }], idx: 0, pending: [] };
const history = {
  get length() { return HIST.entries.length; }, get state() { return HIST.entries[HIST.idx].state; },
  pushState(st, _t, url) { HIST.entries.splice(HIST.idx + 1); HIST.entries.push({ state: JSON.parse(JSON.stringify(st)), url: url || '/' }); HIST.idx++; },
  replaceState(st) { HIST.entries[HIST.idx].state = st == null ? null : JSON.parse(JSON.stringify(st)); },
  go(n) { HIST.pending.push(n); }, back() { history.go(-1); }, forward() { history.go(1); },
};
function land() { while (HIST.pending.length) { const n = HIST.pending.shift(), to = HIST.idx + n;
  if (to < 0 || to >= HIST.entries.length) continue; HIST.idx = to; POP.forEach(f => f({ type: 'popstate', state: HIST.entries[to].state })); } }
const store = () => { const b = {}; return { getItem: k => (k in b ? b[k] : null), setItem: (k, v) => { b[k] = String(v); }, removeItem: k => { delete b[k]; } }; };
const FETCHED = [];
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  document, localStorage: store(), sessionStorage: store(), navigator: any, location: LOC, history,
  fetch: url => { FETCHED.push(String(url)); return new Promise(() => {}); }, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener: (type, fn) => { if (type === 'popstate') POP.push(fn); }, removeEventListener() {},
  DecompressionStream: any, Response: any, Blob: any, AbortController: any,
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
const J = code => JSON.parse(JSON.stringify(run(code)));
const tick = () => new Promise(r => setImmediate(r));
const settle = async () => { await tick(); land(); await tick(); land(); await tick(); };
const userBack = async () => { history.back(); land(); await settle(); };
ctx.__FX = JSON.parse(fs.readFileSync(fxPath, 'utf8'));
ctx.__setScreen = id => { SCREEN.id = id; };
const out = {};
const step = async (name, fn) => { try { out[name] = await fn(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };
const html = () => run('AU._.el().innerHTML');
// a fake event target inside the screen: closest() answers the selectors the handlers ask
const tgt = (m, extra) => Object.assign({ closest: sel => { if (sel === '#au-root') return {}; for (const k of Object.keys(m)) if (sel === k) return m[k]; return null; }, matches: () => false }, extra || {});

(async () => {
  run(`DATA=__FX.dashboard; APP=''; CURVIEW=null; RANGE='today'; window.__ax=null;`);
  run(`var __show0=show; show=function(id){ __setScreen(id); return __show0(id); };`);
  // render() rebuilds every tab; setApp / toggleCur (→ rerender) call it — here only the Audience shell is rebuilt
  run(`var __render0=render; render=function(){ window.__ax=null; renderAudience(); show('overview'); };`);
  run(`AU._.load(__FX.audience);`);

  // ── the render ────────────────────────────────────────────────────────────────────────────────────────────────────────
  await step('render', () => { run(`renderAudience(); show('audience');`);
    const h = html();
    return { screen: SCREEN.id, ids: [...h.matchAll(/<section class="au-card[^"]*" id="([^"]+)"/g)].map(m => m[1]), strip: (h.match(/class="au-st"/g) || []).length,
      title: run(`document.getElementById('tb-title').textContent`), html: h, S: J('AU._.S') }; });

  // ── the numbers the page works out ───────────────────────────────────────────────────────────────────────────────────
  await step('numbers', () => J(`(()=>{ const A=AU._.ALL(), apps={}; AU._.APPS().forEach(a=>{ apps[a.k]={bk:a.bk,deadTot:a.deadTot,
      w10:AU._.wake(a,'10'),wage:AU._.wake(a,'age'),d3:AU._.dAt(a.au,3),l3:AU._.loAt(a.au,3),c10:AU._.calc(a,AU._.FIX),wd:AU._.wakeDays(a)}; });
    return {apps, all:{mo:A.au.mo,d:A.au.d,lo:A.au.lo,src:A.au.src,inst:A.au.inst,ins:A.au.ins,m:A.au.m,most:A.au.most,j:A.j,lt:A.lt,arp:A.arp,pm:A.pm,
      inst2:A.inst,sl:A.sl,deadTot:A.deadTot,bk:A.bk,w10:AU._.wakeAll('10'),wage:AU._.wakeAll('age'),bands:A.au.bands},
      tier:[AU._.tierMonths(30),AU._.tierMonths(31),AU._.tierMonths(400),AU._.tierMonths(1300)],
      lab:[AU._.bLab(0,1),AU._.bLab(1,2),AU._.bLab(12,15),AU._.bLab(24,30),AU._.bLab(24,36),AU._.bLab(36,null),AU._.bLab(15,null)],
      p:[AU._.P(1,3),AU._.P(1,30000),AU._.P(0,5),AU._.P(5,0)]}; })()`));

  // ── "Paise ka calculator": one open's money, the levers, the result, the table, the eCPM box, all apps ──────────────
  await step('calc', async () => { const R = {}; SCREEN.id = 'audience';
    const MODES = ['5', '10', '20', 'age'], OPS = ['data', '1', '2', '5', '10', '20', '30'], ECS = ['-10', '0', '10', '20'];
    R.po = J(`(()=>{ const o={}; AU._.APPS().forEach(a=>{ o[a.k]=AU._.perOpen(a); }); return o; })()`);
    R.grid = {}; R.all = {};
    for (const m of MODES) for (const op of OPS) for (const ec of ECS) { const o = JSON.stringify({ mode: m, opens: op, ecpm: ec });
      R.grid[m + '|' + op + '|' + ec] = J(`(()=>{ const o={}; AU._.APPS().forEach(a=>{ const c=AU._.calc(a,${o}); delete c.p; o[a.k]=c; }); return o; })()`);
      R.all[m + '|' + op + '|' + ec] = J(`AU._.calcAll(${o})`); }
    R.mo = { USD: [], INR: [] };
    for (const c of ['USD', 'INR']) { run(`CURVIEW=${c === 'USD' ? 'null' : "'INR'"}`);
      R.mo[c] = J(`[12.345, 1.2345, 0.4321, 0.0123, 0.00517, 0.000204, 0].map(v=>AU._.MO(v))`); }
    run(`CURVIEW=null`);
    // the card as it renders: an app (each), All apps; at a few lever settings, in $ and ₹
    const card = () => { const h = html(), i = h.indexOf('<section class="au-card" id="au-s-money">'); return i < 0 ? '' : h.slice(i, h.indexOf('</section>', i) + 10); };
    const setL = (m, op, ec) => run(`AU._.S.mode='${m}'; AU._.S.opens='${op}'; AU._.S.ecpm='${ec}';`);
    R.cards = {};
    for (const [k, n] of J('AU._.APPS().map(a=>[a.k,a.n])').concat([['all', '']])) {
      for (const [m, op, ec, c] of [['10', 'data', '0', 'USD'], ['20', '5', '10', 'USD'], ['age', '30', '-10', 'INR'], ['5', 'data', '20', 'INR']]) {
        setL(m, op, ec); run(`CURVIEW=${c === 'USD' ? 'null' : "'INR'"}; AU._.S.pick='${k === 'all' ? '' : k}'; APP=${JSON.stringify(n)}; AU.paint();`);
        R.cards[[k, m, op, ec, c].join('|')] = card(); } }
    run(`CURVIEW=null; APP=''; AU.paint();`);
    // the all-apps table: money at the levers, the order fixed (10% · data se · eCPM 0)
    const order = () => { const h = html(), t = h.slice(h.indexOf('id="au-s-table"')); return [...t.matchAll(/<tr class="au-clk" tabindex="0" data-au-k="([^"]+)">/g)].map(x => x[1]); };
    const money = () => { const h = html(), t = h.slice(h.indexOf('id="au-s-table"')); return [...t.matchAll(/<td class="au-r au-m">(?:<span class="au-dk">([^<]*)<\/span>|—)/g)].map(x => x[1] || '—'); };
    R.table = {};
    for (const [m, op, ec] of [['10', 'data', '0'], ['age', '1', '20'], ['5', '30', '-10']]) { setL(m, op, ec); run('AU.paint()');
      R.table[[m, op, ec].join('|')] = { order: order(), money: money(), h2s: (html().slice(html().indexOf('id="au-s-table"')).match(/<div class="au-h2s">(.*?)<\/div>/s) || [])[1] }; }
    // the chips: a tap sets the lever, lights it, and is remembered (localStorage → a fresh page load's boot)
    setL('10', 'data', '0'); run(`localStorage.removeItem('audview'); AU.paint();`);
    fire('click', { target: tgt({ '[data-au-opens]': { dataset: { auOpens: '5' } } }) });
    fire('click', { target: tgt({ '[data-au-ecpm]': { dataset: { auEcpm: '20' } } }) });
    fire('click', { target: tgt({ '[data-au-mode]': { dataset: { auMode: '20' } } }) });
    R.chips = { S: J('[AU._.S.mode,AU._.S.opens,AU._.S.ecpm]'), on: ['mode="20"', 'opens="5"', 'ecpm="20"'].map(x => new RegExp('class="au-chip on" data-au-' + x).test(html())),
      ls: JSON.parse(run(`localStorage.getItem('audview')`) || 'null'), row: /<tr class="au-on" data-au-opens="5">/.test(html()) };
    run(`AU._.S.booted=false; AU._.S.mode='10'; AU._.S.opens='data'; AU._.S.ecpm='0'; AU._.boot();`);
    R.boot = J('[AU._.S.mode,AU._.S.opens,AU._.S.ecpm]');
    run(`localStorage.setItem('audview',JSON.stringify({mode:'7',opens:'7',ecpm:'15'})); AU._.S.booted=false; AU._.S.mode='10'; AU._.S.opens='data'; AU._.S.ecpm='0'; AU._.boot();`);
    R.bootBad = J('[AU._.S.mode,AU._.S.opens,AU._.S.ecpm]');
    // a row of the opens table is a lever too
    fire('click', { target: tgt({ '[data-au-opens]': { dataset: { auOpens: '10' } } }) });
    R.rowTap = run('AU._.S.opens');
    setL('10', 'data', '0'); run(`localStorage.removeItem('audview'); APP=''; AU.paint();`);
    // an app without the calculator's inputs (no eCPM): its card says so, the table shows "—", All apps leaves it out
    run(`var __raw2=AU._.RAW(); var __nd=JSON.parse(JSON.stringify(__raw2)); __nd.apps[1].ec=null; AU._.load(__nd); AU.paint();`);
    const k1 = run('__nd.apps[1].k'), n1 = run('__nd.apps[1].n');
    R.noData = { k: k1, po: J(`AU._.perOpen(AU._.BYK()['${k1}'])`), all: J(`AU._.calcAll({mode:'10',opens:'data',ecpm:'0'})`), w: run(`AU._.wake(AU._.BYK()['${k1}'],'10').w`),
      order: order(), money: money(), allCard: card() };
    run(`AU._.S.pick='${k1}'; APP=${JSON.stringify(n1)}; AU.paint();`); R.noData.card = card(); R.noData.strip = (html().match(/If 10% wake up: money \/ month<\/div><div class="au-n">([^<]*)</) || [])[1];
    run(`AU._.load(__raw2); AU._.S.pick=''; APP=''; AU.paint();`);
    // a fit without a range (fewer than 4 weeks with enough installs): the line says so
    run(`var __nr=JSON.parse(JSON.stringify(__raw2)); __nr.apps[0].kf.d10=null; __nr.apps[0].kf.d90=null; AU._.load(__nr); AU._.S.pick=__nr.apps[0].k; APP=__nr.apps[0].n; AU.paint();`);
    R.noRange = (html().match(/<div class="au-lvn">(.*?)<\/div>/) || [])[1];
    run(`AU._.load(__raw2); AU._.S.pick=''; APP=''; AU.paint();`);
    // an app without the build's fitted curve: "data se" = its day 1 / 7 / 30 points joined (as before the fit)
    run(`var __nf=JSON.parse(JSON.stringify(__raw2)); delete __nf.apps[2].kf; AU._.load(__nf); AU.paint();`);
    const k2 = run('__nf.apps[2].k'), n2 = run('__nf.apps[2].n');
    R.noFit = { k: k2, wd: run(`AU._.wakeDays(AU._.BYK()['${k2}'])`), Kd: run(`AU._.calc(AU._.BYK()['${k2}'],AU._.FIX).Kd`), K10: run(`AU._.calc(AU._.BYK()['${k2}'],AU._.FIX).K10`) };
    run(`AU._.S.pick='${k2}'; APP=${JSON.stringify(n2)}; AU.paint();`); R.noFit.card = card();
    run(`AU._.load(__raw2); AU._.S.pick=''; APP=''; AU.paint();`);
    return R; });

  // ── every app's own page (GA4 / estimate / being read / young) ─────────────────────────────────────────────────────
  await step('apps', () => { const R = {}; SCREEN.id = 'audience';
    for (const [k, n] of J('AU._.APPS().map(a=>[a.k,a.n])')) { run(`AU._.S.pick='${k}'; APP=${JSON.stringify(n)}; AU.paint();`); R[k] = html(); }
    run(`APP=''; AU.paint();`); return R; });

  // ── money strings in $ and ₹ ─────────────────────────────────────────────────────────────────────────────────────────
  await step('money', () => { const R = {};
    for (const c of ['USD', 'INR']) { run(`CURVIEW=${c === 'USD' ? 'null' : "'INR'"}; AU.paint();`);
      R[c] = { m: J(`[AU._.M(1234.4),AU._.M(2.25),AU._.M(0.0123,2),AU._.MC(12345),AU._.M(0)]`), html: html() }; }
    run(`CURVIEW=null; AU.paint();`); return R; });

  // ── the all-apps table on a phone: short numbers, the full ones in a tip; a tap on a number vs on the name ────────────
  await step('phone', async () => { const R = {};
    SCREEN.id = 'audience'; run(`APP=''; AU._.S.mode='10'; AU.paint();`);
    for (const c of ['USD', 'INR']) { run(`CURVIEW=${c === 'USD' ? 'null' : "'INR'"}; AU.paint();`);
      const h = html(), t = h.slice(h.indexOf('id="au-s-table"'));
      R[c] = { rows: J(`AU._.APPS().map(a=>a.k)`).map(k => { const tr = t.slice(t.indexOf(`data-au-k="${k}"`)); const row = tr.slice(0, tr.indexOf('</tr>'));
          return { k, inst: (row.match(/<small class="au-ph" data-at="t:[^"]+">([^<]*)<\/small>/) || [])[1],
            sl: (row.match(/<span class="au-ph" data-at="t:[^"]+">([^<]*)<\/span><small/) || [])[1],
            money: (row.match(/<td class="au-r au-m"><span class="au-dk">([^<]*)<\/span><span class="au-ph" data-at="t:([^"]+)">([^<]*)<\/span><\/td>/) || []).slice(1),
            slDk: (row.match(/<span class="au-dk">([\d,]+)<\/span>/) || [])[1] }; }),
        head: (t.match(/<thead>.*?<\/thead>/s) || [''])[0], hint: (t.match(/<div class="au-h2s">.*?<\/div>/s) || [''])[0],
        tip: run(`AU._.TIPS.t(AU._.APPS()[0].k)`) }; }
    run(`CURVIEW=null; AU.paint();`);
    // a tap on a number: its tip pins and the click that follows does NOT open the app; a tap on the name opens it
    run(`var __sets=[]; var __setApp2=setApp; setApp=function(a){ __sets.push(a); APP=a; AU.paint(); };`);
    const k = run(`AU._.APPS()[0].k`);
    const num = tgt({ '[data-at]': { getAttribute: () => 't:' + k }, '[data-au-k]': { getAttribute: () => k } });
    fire('touchstart', { target: num, touches: [{ clientX: 300, clientY: 400 }] }); fire('touchend', { target: num, changedTouches: [{ clientX: 301, clientY: 401 }] });
    fire('click', { target: num });
    R.numTap = { pinned: run('AU._.tipPinned()'), tip: ELS['au-tip'] && ELS['au-tip'].innerHTML, sets: J('__sets') };
    fire('click', { target: tgt({ '[data-au-k]': { getAttribute: () => k } }) });
    R.nameTap = { sets: J('__sets') };
    run(`setApp=__setApp2; APP=''; AU.paint(); document.getElementById('au-tip').classList.remove('au-on','au-pin');`);
    return R; });

  // ── the top bar's App drives the view; a table row sets it; the phone's Back button ─────────────────────────────────────
  await step('nav', async () => { const R = {};
    run(`HB.st.length=0; HB.busy=false; HB.mute=0;`); await settle(); HIST.entries = [{ state: null, url: '/' }]; HIST.idx = 0; HIST.pending = []; run(`HB.depth=0;`);
    SCREEN.id = 'overview'; run(`APP=''; show('audience')`); await settle();
    const k = run(`AU._.APPS()[0].k`), k2 = run(`AU._.APPS()[1].k`), n2 = run(`AU._.APPS()[1].n`);
    const st = () => J('HB.st.map(x=>x.tag)');
    // a table row (the click handler on the document) → the GLOBAL App (setApp) = that app; the top bar's Back step
    run(`var __sets=[]; var __setApp1=setApp; setApp=function(a){ __sets.push(a); return __setApp1(a); };`);
    fire('click', { target: tgt({ '[data-au-k]': { getAttribute: () => k } }) }); await settle();
    R.row = { app: run('AU._.S.app'), APP: run('APP'), sets: J('__sets'), st: st(), idx: HIST.idx, crumb: html().includes('class="au-crumb"'),
      title: run(`document.getElementById('tb-title').textContent`), table: html().includes('id="au-s-table"'), screen: SCREEN.id };
    await userBack();                                                                   // Back = All apps (hbAppUndo → setApp(''))
    R.back = { app: run('AU._.S.app'), APP: run('APP'), st: st(), idx: HIST.idx, table: html().includes('id="au-s-table"'), screen: SCREEN.id };
    // Enter on a focused row: the same
    fire('keydown', { key: 'Enter', target: Object.assign(tgt({}), { matches: sel => sel === 'tr[data-au-k]', getAttribute: () => k2 }) }); await settle();
    R.enter = { APP: run('APP'), app: run('AU._.S.app'), st: st() };
    run(`setApp('')`); await settle();
    // the top bar's App picker (apkPick → setApp) → this app's view at once
    run(`setApp(${JSON.stringify(n2)})`); await settle();
    R.header = { app: run('AU._.S.app'), want: k2, st: st(), crumb: html().includes(n2.split(' · ')[0]) && html().includes('class="au-crumb"'), table: html().includes('id="au-s-table"') };
    // "← All apps" on the page → the top bar's All apps, its Back step gone
    fire('click', { target: tgt({ '[data-au-all]': {} }) }); await settle();
    R.allBtn = { app: run('AU._.S.app'), APP: run('APP'), st: st(), idx: HIST.idx };
    // leaving the screen with an app open: the top bar keeps the app (as on every tab); coming back shows it again
    run(`setApp(${JSON.stringify(n2)})`); await settle(); run(`show('placements')`); await settle();
    R.left = { screen: SCREEN.id, st: st(), APP: run('APP') };
    run(`show('audience')`); await settle(); R.back2 = { app: run('AU._.S.app'), crumb: html().includes('class="au-crumb"') };
    run(`setApp('')`); await settle();
    // an app the top bar has but Audience has no row for: one line + "← All apps"
    run(`setApp('Not An Audience App')`); await settle();
    R.noApp = { app: run('AU._.S.app'), html: html(), st: st() };
    fire('click', { target: tgt({ '[data-au-all]': {} }) }); await settle();
    R.noAppBack = { APP: run('APP'), app: run('AU._.S.app'), st: st(), table: html().includes('id="au-s-table"') };
    // two apps with one name: the row tapped is the one shown
    run(`var __raw=AU._.RAW(); var __dup=JSON.parse(JSON.stringify(__raw)); __dup.apps[1].n=__dup.apps[0].n; AU._.load(__dup); AU._.S.pick='';`);
    const n0 = run(`__dup.apps[0].n`);
    R.dup = { none: run(`AU._.keyOfName(${JSON.stringify(n0)})`), picked: run(`AU._.S.pick=__dup.apps[1].k; AU._.keyOfName(${JSON.stringify(n0)})`),
      want: J(`[__dup.apps[0].k, __dup.apps[1].k]`) };
    run(`AU._.load(__raw); AU._.S.pick=''; setApp=__setApp1; APP=''; AU.paint();`); await settle();
    return R; });

  // ── folds, chips, currency buttons ───────────────────────────────────────────────────────────────────────────────────
  await step('controls', async () => { const R = {};
    SCREEN.id = 'audience'; run(`AU._.allApps(); AU._.S.open.clear(); AU._.S.mall.clear(); AU._.S.mode='10'; AU.paint();`); await settle();
    R.closed = /data-kyun="dead"(?! open)/.test(html()) && !/data-kyun="dead" open/.test(html());
    fire('toggle', { target: tgt({}, { dataset: { kyun: 'dead' }, open: true }) }); run('AU.paint()');
    R.opened = { set: J('[...AU._.S.open]'), attr: /data-kyun="dead" open/.test(html()) };
    fire('toggle', { target: tgt({}, { dataset: { kyun: 'dead' }, open: false }) }); run('AU.paint()');
    R.reclosed = { set: J('[...AU._.S.open]'), attr: /data-kyun="dead" open/.test(html()) };
    fire('click', { target: tgt({ '[data-au-mode]': { dataset: { auMode: 'age' } } }) });
    R.mode = { mode: run('AU._.S.mode'), on: /class="au-chip on" data-au-mode="age"/.test(html()), table: html().includes('By age wake up =') };
    fire('click', { target: tgt({ '[data-au-mode]': { dataset: { auMode: '10' } } }) });
    const before = (html().match(/data-at="m:[^"]*:d"/g) || []).length / 2;
    fire('click', { target: tgt({ '[data-au-more]': { dataset: { auMore: 'mdead' }, getBoundingClientRect: () => ({ top: 0 }) } }) });
    R.more = { before, after: (html().match(/data-at="m:[^"]*:d"/g) || []).length / 2, set: J('[...AU._.S.mall]'), btn: html().includes('Show top 6 only') };
    // the top bar's 💱 (toggleCur → rerender → this screen repainted at once, in ₹ then back in $)
    const el0 = run('AU._.el()');
    run(`toggleCur()`);
    R.inr = { cur: run('curView()'), rupee: html().includes('₹ / month') && !html().includes('$ / month'), screen: SCREEN.id, repainted: run('AU._.el()') !== el0,
      mode: run('AU._.S.mode'), own: /data-au-cur|class="au-seg"/.test(html()) };
    run(`toggleCur()`);
    R.usd = { cur: run('curView()'), dollar: html().includes('$ / month') && !html().includes('₹ / month'), screen: SCREEN.id };
    fire('change', { target: tgt({}, { id: 'au-dday', value: '2026-03-15' }) });
    R.day = { day: run('AU._.S.day'), val: html().includes('value="2026-03-15"') };
    fire('click', { target: tgt({ '[data-au-day]': { dataset: { auDay: '2026-01-01' } } }) });
    R.dayChip = { day: run('AU._.S.day'), on: /class="au-chip on" data-au-day="2026-01-01"/.test(html()) };
    return R; });

  // ── the 5-min refresh with a NEW build: the view comes back as it was, silently ─────────────────────────────────────
  await step('refresh', async () => {
    run(`HB.st.length=0; HB.busy=false; HB.mute=0;`); await settle(); HIST.entries = [{ state: null, url: '/' }]; HIST.idx = 0; HIST.pending = []; run(`HB.depth=0;`);
    SCREEN.id = 'overview'; run(`APP=''; show('audience');`); await settle();
    const k = run(`AU._.APPS()[1].k`);
    run(`AU._.openApp('${k}'); toggleCur(); AU._.S.mode='age'; AU._.S.opens='5'; AU._.S.ecpm='10'; AU._.S.day='2026-02-01'; AU._.S.open.add('money'); AU._.S.open.add('dead'); AU.paint();`); await settle();
    const scrolls = []; ctx.scrollTo = (...a) => scrolls.push(JSON.stringify(a)); ctx.scrollY = 1234;
    FETCHED.length = 0;
    run(`var __load0=loadDashboardData; loadDashboardData=function(){ const d=JSON.parse(JSON.stringify(__FX.dashboard)); d.generated_at='2026-09-23T07:30:00Z'; d.audience=Object.assign({},d.audience,{v:'0123456789ab'}); return Promise.resolve(d); };
         LAST_BUILD=__FX.dashboard.generated_at; var __old=DATA;`);
    await run(`refreshData()`); await settle();
    const h = html();
    const R = J(`({S:{app:AU._.S.app,mode:AU._.S.mode,opens:AU._.S.opens,ecpm:AU._.S.ecpm,day:AU._.S.day,open:[...AU._.S.open]}, st:HB.st.map(x=>x.tag), newData:DATA!==__old, silent:REFRESH_SILENT, cur:curView()})`);
    R.want = k; R.screen = SCREEN.id; R.scrolls = scrolls.filter(s => s.includes('"top":0')); R.hist = HIST.entries.length;
    R.crumb = h.includes('class="au-crumb"'); R.fold = /data-kyun="money" open/.test(h) && /data-kyun="dead" open/.test(h);
    R.ageOn = /class="au-chip on" data-au-mode="age"/.test(h); R.leversOn = /class="au-chip on" data-au-opens="5"/.test(h) && /class="au-chip on" data-au-ecpm="10"/.test(h);
    R.rupee = h.includes('₹') && !h.includes('$'); R.fetched = FETCHED.filter(u => u.includes('audience.json.gz'));
    run(`loadDashboardData=__load0; DATA=__FX.dashboard; AU._.load(__FX.audience); toggleCur(); AU._.S.opens='data'; AU._.S.ecpm='0'; AU._.allApps();`); await settle(); ctx.scrollTo = () => {}; ctx.scrollY = 0;
    return R; });

  // ── tooltips: a mouse hovers, a tap pins, a swipe never pins; the chart's numbers ────────────────────────────────────
  await step('tips', async () => { const R = {};
    SCREEN.id = 'audience'; run(`AU._.allApps(); AU.paint();`);
    const bar = { getAttribute: () => 'b:2' };
    fire('mousemove', { target: tgt({ '[data-at]': bar }), clientX: 100, clientY: 200 });
    const tip = () => ELS['au-tip'];
    R.hover = { on: tip() && tip().classList.contains('au-on'), pin: tip() && tip().classList.contains('au-pin'), html: tip() && tip().innerHTML, pinned: run('AU._.tipPinned()') };
    run(`document.getElementById('au-tip').classList.remove('au-on','au-pin')`);
    const t = tgt({ '[data-at]': bar });
    fire('touchstart', { target: t, touches: [{ clientX: 50, clientY: 60 }] }); fire('touchend', { target: t, changedTouches: [{ clientX: 53, clientY: 64 }] });
    R.tap = { on: tip().classList.contains('au-on'), pin: tip().classList.contains('au-pin'), pinned: run('AU._.tipPinned()') };
    run(`document.getElementById('au-tip').classList.remove('au-on','au-pin')`);
    fire('touchstart', { target: t, touches: [{ clientX: 50, clientY: 60 }] }); fire('touchmove', { touches: [{ clientX: 50, clientY: 90 }] });
    fire('touchend', { target: t, changedTouches: [{ clientX: 50, clientY: 61 }] });
    R.swipe = { on: tip().classList.contains('au-on') };
    // the month chart: drawn at the box's width, every point's numbers on hover, the latest-but-one read out under it
    const box = mk('div'); box.setAttribute('id', 'au-mline'); box.clientWidth = 600; const rd = mk('div'); rd.setAttribute('id', 'au-mread');
    run(`AU.paint()`);
    R.chart = { svg: box.innerHTML.slice(0, 200), labels: [...box.innerHTML.matchAll(/font-weight="800" fill="#fff">([^<]+)</g)].map(m => m[1]), read: rd.innerHTML,
      spk: J(`(()=>{ const g=AU._.SPK['au-mchart']; return g?{n:g.n,w:g.w,last:g.tip(g.n-1)}:null; })()`) };
    const xh = mk('line');
    const sv = { id: 'au-mchart', getBoundingClientRect: () => ({ left: 0, width: 600 }), querySelector: () => xh };
    ctx.__sv = sv; R.hov = run(`AU._.hov(__sv, 599, 40, true)`); R.hovTip = tip().innerHTML; R.hovPin = run('AU._.tipPinned()'); R.xh = xh.getAttribute('opacity');
    delete ELS['au-mline']; delete ELS['au-mread'];
    return R; });

  // ── a calculator lever redraws ONLY the money card, the strip and the all-apps table, in place (owner, iPhone: a chip
  // tap mid-page threw the page to the top — the whole screen was rebuilt). The rest of the screen is not touched. ────
  await step('levers_partial', async () => { const R = {};
    const ids = ['au-root', 'au-s-money', 'au-strip', 'au-s-table'];
    const stubs = () => { const o = {}; for (const id of ids) { o[id] = mk(id === 'au-strip' ? 'div' : 'section'); o[id].setAttribute('id', id); } return o; };
    const unstub = () => ids.forEach(id => { delete ELS[id]; });
    const sec = (h, id) => { const i = h.indexOf(`id="${id}"`); if (i < 0) return null; const s = h.lastIndexOf('<section', i); return h.slice(s, h.indexOf('</section>', i) + 10); };
    const strip = h => (h.match(/<div class="au-strip" id="au-strip">([\s\S]*?)<\/div><div class="au-grid">/) || [])[1];
    const clicks = () => { fire('click', { target: tgt({ '[data-au-opens]': { dataset: { auOpens: '5' } } }) });
      fire('click', { target: tgt({ '[data-au-mode]': { dataset: { auMode: '20' } } }) });
      fire('click', { target: tgt({ '[data-au-ecpm]': { dataset: { auEcpm: '10' } } }) }); };
    // All apps: three lever taps
    SCREEN.id = 'audience'; run(`localStorage.removeItem('audview'); APP=''; AU._.S.pick=''; AU._.S.mode='10'; AU._.S.opens='data'; AU._.S.ecpm='0'; AU._.S.open.clear(); AU._.S.open.add('money'); AU.paint();`);
    let E = stubs(); run(`AU._.el().innerHTML='SCREEN-KEPT'`);
    clicks();
    R.all = { screen: html(), money: E['au-s-money'].outerHTML || '', strip: E['au-strip'].innerHTML, table: E['au-s-table'].outerHTML || '',
      S: J('[AU._.S.mode,AU._.S.opens,AU._.S.ecpm]'), ls: JSON.parse(run(`localStorage.getItem('audview')`) || 'null') };
    unstub(); run('AU.paint()'); const full = html();   // the same levers, the whole screen painted: the three parts must match it
    R.all.want = { money: sec(full, 'au-s-money'), table: sec(full, 'au-s-table'), strip: strip(full) };
    // one app: its money card and strip; there is no all-apps table to redraw
    const [k1, n1] = J('AU._.APPS().filter(a=>!a.kam).map(a=>[a.k,a.n])[0]');
    run(`AU._.S.pick='${k1}'; APP=${JSON.stringify(n1)}; AU._.S.mode='10'; AU._.S.opens='data'; AU._.S.ecpm='0'; AU.paint();`);
    E = stubs(); E['au-s-table'].outerHTML = 'TABLE-UNTOUCHED'; run(`AU._.el().innerHTML='SCREEN-KEPT'`);
    clicks();
    R.app = { screen: html(), money: E['au-s-money'].outerHTML || '', table: E['au-s-table'].outerHTML };
    unstub(); run('AU.paint()'); R.app.want = sec(html(), 'au-s-money');
    // anything unexpected → the whole screen: the card not on screen; the top bar on another app since the last paint
    run(`AU.paint()`); E = stubs(); delete ELS['au-s-money']; run(`AU._.el().innerHTML='SCREEN-KEPT'`);
    fire('click', { target: tgt({ '[data-au-opens]': { dataset: { auOpens: '2' } } }) });
    R.noCard = html() !== 'SCREEN-KEPT' && html().includes('id="au-s-money"'); unstub();
    run(`AU.paint()`); E = stubs(); run(`APP=''; AU._.S.pick=''; AU._.el().innerHTML='SCREEN-KEPT'`);
    fire('click', { target: tgt({ '[data-au-opens]': { dataset: { auOpens: '1' } } }) });
    R.appMoved = html() !== 'SCREEN-KEPT' && html().includes('id="au-s-table"'); unstub();
    run(`localStorage.removeItem('audview'); APP=''; AU._.S.pick=''; AU._.S.mode='10'; AU._.S.opens='data'; AU._.S.ecpm='0'; AU._.S.open.clear(); AU.paint();`);
    return R; });

  // ── the switch off: no pointer in this build ─────────────────────────────────────────────────────────────────────────
  await step('off', () => { run(`var __a=DATA.audience; delete DATA.audience; AU.paint();`); const h = html(); const p = run('!!AU.ptr()'); run(`DATA.audience=__a; AU.paint();`); return { html: h, ptr: p }; });

  out.errors = errors;
  process.stdout.write(JSON.stringify(out));
})().catch(e => { errors.push('MAIN ' + (e.stack || e.message)); out.errors = errors; process.stdout.write(JSON.stringify(out)); });
