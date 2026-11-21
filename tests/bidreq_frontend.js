// 📡 Meta won % / Bid requests (frontend/index.html) — the page side, run for real: the dashboard script (the page's largest
// <script>) in a node vm with stub browser globals, on the SYNTHETIC dashboard + mediation file tests/test_bidreq_frontend.py
// writes (made-up apps, source ids and counts — no real data). It reports:
//   * bqWin: the Period's sums per app (AdMob Network requests, Meta bidding requests, Meta won) for many windows, its states
//     (the file on its way / failed / nothing for the Period / a Period day the file lacks / no "AdMob Network" source / a
//     stale file) and its cache (a new file or another Period never reads an old answer);
//   * the two Overview tiles (All apps: buttons into the list; an app: its own numbers, no button), their texts and titles,
//     and their in-place repaint (bqOvPaint) once the file lands;
//   * the Overview's tile row (its class, the tiles in order) with and without Google Ads;
//   * the list (rows, cells, the All apps row, an app picked in the header, the empty states), bqN's rounding edges;
//   * loadMED: one fetch for several callers, every caller called back (also on a failure), a new build fetched again, a
//     new build landing while the file is on its way;
//   * the page's own show('overview'): the file is fetched once the Overview really is on screen, never when render() only
//     passes through it; the list's wiring: its title, the hub's drill map, the Back step it pushes / drops.
// Prints ONE JSON report; tests/test_bidreq_frontend.py asserts on it (with the expected numbers worked out by hand).
//   usage: node bidreq_frontend.js <script.js> <fixture.json>      (the test runs it with LC_ALL=en_US.UTF-8)
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath, fxPath] = process.argv.slice(2);
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
function mk(tag) {
  const el = { tagName: String(tag || 'div').toUpperCase(), dataset: {}, style: {}, className: '', _h: '', children: [],
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} }, setAttribute() {}, getAttribute: () => null,
    appendChild(c) { el.children.push(c); return c; }, append(...cs) { cs.forEach(c => el.children.push(c)); },
    addEventListener() {}, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [], insertBefore() {},
    replaceWith() {}, focus() {}, blur() {}, scrollIntoView() {}, closest: () => null, contains: () => false };
  Object.defineProperty(el, 'innerHTML', { get: () => el._h, set: v => { el._h = String(v); } });
  return el;
}
const SCREEN = { id: 'overview' };
const LIST = mk('section'); LIST.dataset.screen = 'bidreq';
const QSA = {};                                   // selector → the elements a step puts "on the page"
const document = new Proxy({
  createElement: mk, body: mk('body'), head: mk('head'), documentElement: mk('html'),
  querySelector: sel => (sel === '.screen.on' ? { dataset: { screen: SCREEN.id } } : sel === '.screen[data-screen=bidreq]' ? LIST : null),
  querySelectorAll: sel => QSA[sel] || [], getElementById: () => mk('div'), addEventListener() {}, removeEventListener() {},
}, { get: (t, k) => (k in t ? t[k] : any) });
const store = () => { const b = {}; return { getItem: k => (k in b ? b[k] : null), setItem: (k, v) => { b[k] = String(v); }, removeItem: k => { delete b[k]; } }; };
// the page's fetch: mediation_daily.json answers from the fixture (or fails / waits, as a step asks); everything else never settles
const NET = { calls: 0, mode: 'ok', body: null, held: [] };
function fetchStub(url) {
  if (String(url).indexOf('mediation_daily.json') !== 0) return new Promise(() => {});
  NET.calls++;
  const answer = () => (NET.mode === 'fail' ? Promise.reject(new TypeError('synthetic network error'))
    : Promise.resolve({ ok: NET.mode !== '404', json: () => Promise.resolve(JSON.parse(JSON.stringify(NET.body))) }));
  if (NET.mode === 'hold') return new Promise((res, rej) => NET.held.push(() => { NET.mode = 'ok'; answer().then(res, rej); }));
  return answer();
}
const history = { length: 1, state: null, pushState() {}, replaceState() {}, go() {}, back() {} };
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  document, localStorage: store(), sessionStorage: store(), navigator: any, history,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} },
  fetch: fetchStub, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean, RegExp,
  Error, TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat, unescape, escape,
  encodeURIComponent, decodeURIComponent, performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 1280,
  innerHeight: 900, scrollY: 0, scrollTo() {}, alert() {}, confirm: () => false, prompt: () => null,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any, Node: any,
};
ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const FX = JSON.parse(fs.readFileSync(fxPath, 'utf8'));
ctx.__FX = FX; NET.body = FX.med;
const tick = async () => { for (let i = 0; i < 8; i++) await new Promise(r => setImmediate(r)); };
const rep = {};
const step = async (name, f) => { try { rep[name] = await f(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };
const reset = (dash, app, range) => run(`DATA=JSON.parse(JSON.stringify(__FX[${JSON.stringify(dash)}])); window.__ax=null; RANGE=${JSON.stringify(range)};
  RCUSTOM={from:'',to:''}; APP=${JSON.stringify(app)}; CURVIEW=null; 1`);
const loadFile = () => run(`MED=JSON.parse(JSON.stringify(__FX.med)); MEDB=medBuild(); MEDERR=false; MEDLOADING=false; MEDCB=[]; 1`);
const noFile = (extra) => run(`MED=null; MEDB=null; MEDERR=false; MEDLOADING=false; MEDCB=[]; ${extra || ''} 1`);
const J = v => JSON.parse(run(`JSON.stringify(${v})`));
const tiles = () => J(`['won','req'].map(k=>bqTile(k))`);

(async () => {
  await step('wiring', () => J(`{title:TITLES.bidreq, drill:HUB_DRILL.bidreq, render:String(render).indexOf('root.append(renderBidReq())')>=0}`));
  // ── the sums, for every window the tests name ──
  await step('win', () => {
    reset('dash', '', 'all'); loadFile();
    const o = {};
    for (const [k, w] of Object.entries(FX.windows)) o[k] = J(`bqWin(${JSON.stringify(w)})`);
    return o;
  });
  await step('states', () => {
    reset('dash', '', 'yesterday');
    const o = {};
    noFile(); o.notYet = J('bqWin(curWinArr())');
    run('MEDLOADING=true;'); o.loading = J('bqWin(curWinArr())');
    run('MEDLOADING=false; MEDERR=true;'); o.failed = J('bqWin(curWinArr())');
    run('MEDERR=false; MED={dates:[],names:{},by_app:{}}; MEDB=medBuild();'); o.empty = J('bqWin(curWinArr())');
    loadFile(); o.noWin = J('bqWin([])');
    o.before = J(`bqWin(['2025-12-31','2026-01-01'])`);        // starts before the file: "—", not the part inside it
    o.after = J(`bqWin(['2026-01-11'])`);                      // after it, same build: nothing for it
    o.gapIn = J(`bqWin(${JSON.stringify(FX.gapIn)})`);         // a day inside its range that it lacks: "—", never a part-sum
    run(`MEDB='an older build';`); o.afterStale = J(`bqWin(['2026-01-11'])`);   // after it, an older build's file: on its way
    run(`MEDERR=true;`); o.afterStaleFailed = J(`bqWin(['2026-01-11'])`);
    o.staleCovered = J(`bqWin(curWinArr())`);                  // an older build's file that has every day: its numbers
    loadFile(); run(`MEDB='an older build';`);                 // its last day was that build's partial day: never a whole one
    o.staleLastDay = J(`bqWin([MED.dates[MED.dates.length-1]])`); o.staleWeek = J(`bqWin(${JSON.stringify(FX.windows.w7)})`);
    run(`MEDERR=true;`); o.staleLastDayFailed = J(`bqWin([MED.dates[MED.dates.length-1]])`);
    loadFile(); run(`MED.names={};`); o.noSource = J('bqWin(curWinArr())');
    loadFile(); run(`Object.keys(MED.names).forEach(k=>{ if(/meta/i.test(MED.names[k])) delete MED.names[k]; });`);
    o.noMeta = J('bqWin(curWinArr())');
    loadFile(); run(`Object.keys(MED.names).forEach(k=>{ MED.names[k]=' '+MED.names[k].toUpperCase()+' '; });`);
    o.namesCase = J('bqWin(curWinArr())');
    loadFile();
    return o;
  });
  await step('cache', () => {                                   // no hand reset: a new file / another Period is never read from the cache
    reset('dash', '', 'yesterday'); loadFile();
    const o = { first: J(`bqWin(['2026-01-09']).t`), other: J(`bqWin(['2026-01-06']).t`), again: J(`bqWin(['2026-01-09']).t`) };
    run(`(()=>{ const m=JSON.parse(JSON.stringify(MED)); Object.values(m.by_app).forEach(s=>Object.values(s).forEach(rs=>rs.forEach(r=>{ r[3]*=2; r[4]*=2; }))); MED=m; })()`);
    o.newFile = J(`bqWin(['2026-01-09']).t`);
    return o;
  });
  // ── the tiles ──
  await step('tiles', () => {
    const o = {};
    for (const r of ['today', 'yesterday', '7d', 'all']) { reset('dash', '', r); loadFile(); o['all|' + r] = { t: tiles(), label: run('curWinLabel()'), win: J('curWinArr()') }; }
    for (const a of FX.apps) { reset('dash', a, '7d'); loadFile(); o['app|' + a] = { t: tiles(), label: run('curWinLabel()') }; }
    reset('dash', '', '7d'); noFile('MEDLOADING=true;'); o.loading = { t: tiles(), label: run('curWinLabel()') };
    run('MEDLOADING=false; MEDERR=true;'); o.failed = { t: tiles(), label: run('curWinLabel()') };
    run('MEDERR=false; MED={dates:[],names:{},by_app:{}}; MEDB=medBuild();'); o.empty = { t: tiles(), label: run('curWinLabel()') };
    loadFile();
    return o;
  });
  await step('repaint', () => {                                 // the file landed: each tile on the page is redrawn in place
    reset('dash', '', 'yesterday'); loadFile();
    const el = k => { const e = mk('div'); e.dataset.mk = k; e._o = null; Object.defineProperty(e, 'outerHTML', { get: () => e._o || '', set: v => { e._o = String(v); } }); return e; };
    const a = el('won'), b = el('req'); QSA['.mk-kpi[data-mk]'] = [a, b];
    run('bqOvPaint()'); delete QSA['.mk-kpi[data-mk]'];
    return { won: a._o, req: b._o, want: tiles() };
  });
  await step('overview', () => {
    const o = {};
    for (const dash of ['dash', 'dashAds']) {
      reset(dash, '', '7d'); loadFile();
      const h = run('renderOverview().innerHTML');
      const row = /<div class="ov-kpi row ([^"]*)">([\s\S]*?)<\/div>\s*<div class="ov-note/.exec(h);
      o[dash] = { cls: row ? row[1] : null, labels: [...(row ? row[2] : '').matchAll(/<div class="l">([^<]*)<\/div>/g)].map(m => m[1]),
        mk: (h.match(/data-mk="/g) || []).length };
    }
    return o;
  });
  // ── the list ──
  await step('list', () => {
    const o = {};
    for (const r of ['yesterday', '7d', 'all']) { reset('dash', '', r); loadFile(); o[r] = run('bqHtml()'); }
    for (const a of ['Tiny Notes', 'Quiet App']) { reset('dash', a, '7d'); loadFile(); o['app|' + a] = run('bqHtml()'); }
    reset('dash', '', '7d'); noFile('MEDLOADING=true;'); o.loading = run('bqHtml()');
    run('MEDLOADING=false; MEDERR=true;'); o.failed = run('bqHtml()');
    run('MEDERR=false; MED={dates:[],names:{},by_app:{}}; MEDB=medBuild();'); o.empty = run('bqHtml()');
    loadFile(); run(`MED.names={};`); o.noSource = run('bqHtml()');
    // a file day on which only other sources have rows: the Period has data, but no bid request
    loadFile(); run(`MED.by_app={'Demo Gallery':{[${JSON.stringify(FX.other)}]:[[0,1000000,50,100,1111]]}};`);
    o.noRows = run(`(()=>{ const keep=curWinArr; curWinArr=()=>[MED.dates[0]]; try{ return bqHtml(); } finally { curWinArr=keep; } })()`);
    loadFile();
    return o;
  });
  await step('fmt', () => J(`[0,7,9999,9999.4,10000,52149,999949,999950,1234567,999949999,999950000,9300000000].map(bqN)
    .concat([bqPct(0,0),bqPct(0,5),bqPct(1,3),bqPct(5,5)])`));
  // ── the loader ──
  await step('loader', async () => {
    reset('dash', '', '7d'); noFile('__n={a:0,b:0};');
    const o = {};
    NET.calls = 0; NET.mode = 'hold';
    run(`loadMED(()=>__n.a++); loadMED(()=>__n.b++); 1`);                                   // two callers, one fetch in flight
    o.inFlight = { calls: NET.calls, waiting: run('MEDCB.length'), loading: run('MEDLOADING') };
    NET.held.splice(0).forEach(f => f()); await tick();
    o.landed = { calls: NET.calls, n: J('__n'), medb: run('MEDB'), build: run('medBuild()'), err: run('MEDERR'), waiting: run('MEDCB.length') };
    run(`loadMED(()=>__n.a++); 1`); await tick();                                          // same build: no fetch, called back at once
    o.cached = { calls: NET.calls, n: J('__n') };
    run(`DATA.generated_at='2026-01-10T07:00:00Z'; loadMED(()=>__n.b++); 1`);              // a new build: fetched again
    o.newBuildCalls = NET.calls; await tick();
    o.newBuild = { calls: NET.calls, n: J('__n'), medb: run('MEDB') };
    NET.mode = 'fail'; run(`DATA.generated_at='2026-01-10T08:00:00Z'; loadMED(()=>__n.a++); 1`); await tick();   // a failure: called back, old file kept
    o.failed = { calls: NET.calls, n: J('__n'), err: run('MEDERR'), kept: run('!!MED&&MED.dates.length'), medb: run('MEDB'), loading: run('MEDLOADING') };
    NET.mode = 'ok'; run(`loadMED(()=>__n.b++); 1`); await tick();                        // the next ask tries again
    o.retry = { calls: NET.calls, n: J('__n'), err: run('MEDERR'), medb: run('MEDB') };
    // a newer build lands while the file is on its way: the waiting caller is answered with the newer build's file
    NET.mode = 'hold'; run(`DATA.generated_at='2026-01-10T09:00:00Z'; loadMED(()=>__n.a++); DATA.generated_at='2026-01-10T10:00:00Z'; 1`);
    const c0 = NET.calls; NET.held.splice(0).forEach(f => f()); await tick();
    o.race = { fetches: NET.calls - c0 + 1, n: J('__n'), medb: run('MEDB'), loading: run('MEDLOADING'), waiting: run('MEDCB.length') };
    NET.mode = '404'; run(`DATA.generated_at='2026-01-10T11:00:00Z'; loadMED(()=>__n.a++); 1`); await tick();     // no file: an empty one, as before
    o.missing = { calls: NET.calls, dates: run('MED.dates.length'), err: run('MEDERR') };
    NET.mode = 'ok';
    return o;
  });
  // ── the page's own show('overview'): the file once the Overview really is on screen ──
  await step('ovFetch', async () => {
    reset('dash', '', '7d'); noFile(); run('HUB.on=false;'); NET.mode = 'ok';
    const o = {};
    SCREEN.id = 'overview'; NET.calls = 0; run(`show('overview')`); await tick();
    o.onOverview = { calls: NET.calls, med: run('!!MED') };
    noFile(); NET.calls = 0; run(`show('overview')`); SCREEN.id = 'review'; await tick();   // render() passing through it: the real screen is another
    o.passThrough = { calls: NET.calls, med: run('!!MED') };
    loadFile(); SCREEN.id = 'bidreq'; LIST._h = ''; NET.calls = 0; run(`show('bidreq')`); await tick();   // the list shown: painted
    o.showList = { rows: ((LIST._h.split('<tbody>')[1] || '').match(/<tr>/g) || []).length, total: LIST._h.indexOf('<tr class="dw-tot">') >= 0, calls: NET.calls };
    SCREEN.id = 'overview';
    return o;
  });
  // ── the list's screen: shown, Back step, left (who asked show() for what) ──
  await step('screen', async () => {
    reset('dash', '', '7d'); loadFile(); run('HUB.on=false; HB.st=[]; HB.mute=0;');
    const o = {};
    SCREEN.id = 'overview';
    run(`show=(id)=>{ __shown=id; }; 1`);
    run('bqOpen()'); o.open = { shown: run('__shown'), steps: run(`HB.st.map(x=>x.tag).join(',')`) };
    SCREEN.id = 'bidreq';
    run('bqUndo()'); o.undo = run('__shown');
    run('bqClose()'); o.close = { shown: run('__shown'), steps: run(`HB.st.map(x=>x.tag).join(',')`) };
    run('bqOpen()'); SCREEN.id = 'alerts'; run('bqLeft()'); await tick(); o.left = run(`HB.st.map(x=>x.tag).join(',')`);
    run('HUB.on=true; HB.st=[]; bqOpen()'); o.hubSteps = run(`HB.st.map(x=>x.tag).join(',')`); run('HUB.on=false;');
    SCREEN.id = 'bidreq'; LIST._h = ''; noFile(); NET.mode = 'ok';
    run('bqPaint()'); o.paintFirst = LIST._h.indexOf('load ho raha hai') >= 0; await tick();
    o.paintAfter = LIST._h.indexOf('<tr class="dw-tot">') >= 0;
    return o;
  });
  process.stdout.write(JSON.stringify({ errors, rep }));
})().catch(e => { errors.push('MAIN ' + (e.stack || e.message)); process.stdout.write(JSON.stringify({ errors, rep })); });
