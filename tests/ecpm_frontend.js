// 📈 eCPM trend (frontend/index.html) — the page side, run for real: the dashboard script (the page's largest <script>) in a
// node vm with stub browser globals, a small DOM and a FAKE browser history (as tests/mobile_global_frontend.js), on the
// SYNTHETIC dashboard tests/test_ecpm_frontend.py writes (made-up apps, ids and money — no real data). It reports:
//   * the maths: the windows, yesterday / 7-day / 30-day / month-to-date sums, every app row (change, impact, swing,
//     status), the Day and Month chart points (today's partial day never in them), what the chart prints;
//   * the Overview "Avg eCPM" tile = the view's tiles for the same period (Yesterday / 7 days / 30 days), USD and INR;
//   * the entry (the tile is a button into the view; an app picked in the header opens that app's view), the phone's Back
//     button steps, leaving the view, sorting (default biggest loss first, low data last, every column toggles);
//   * the chart's tap rule: a tap (under 10px) pins the tooltip, a swipe / a cancelled pointer never does, a mouse hovers.
// Prints ONE JSON report; tests/test_ecpm_frontend.py asserts on it (and recomputes the maths independently in Python).
//   usage: node ecpm_frontend.js <script.js> <fixture.json>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath, fxPath] = process.argv.slice(2);
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// ── a small DOM ───────────────────────────────────────────────────────────────────────────────────────────────────────
const ELS = {};
function mk(tag) {
  const cls = new Set(), attrs = {}, on = {};
  const el = {
    tagName: String(tag || 'div').toUpperCase(), id: '', innerHTML: '', textContent: '', dataset: {}, children: [], parentElement: null,
    style: { cssText: '', visibility: '', setProperty() {} }, clientWidth: 0, clientHeight: 0, offsetWidth: 0, offsetHeight: 0, on,
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
const document = new Proxy({
  getElementById: id => ELS[id] || null, createElement: mk, body: BODY, head: mk('head'), documentElement: mk('html'),
  querySelector: sel => (sel === '.screen.on' ? { dataset: { screen: SCREEN.id } } : null), querySelectorAll: () => [],
  addEventListener() {}, removeEventListener() {},
}, { get: (t, k) => (k in t ? t[k] : any) });
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
const J = code => JSON.parse(JSON.stringify(run(code)));
const tick = () => new Promise(r => setImmediate(r));
const settle = async () => { await tick(); land(); await tick(); land(); await tick(); };
const userBack = async () => { history.back(); land(); await settle(); };
ctx.__FX = JSON.parse(fs.readFileSync(fxPath, 'utf8'));
ctx.__setScreen = id => { SCREEN.id = id; };
const out = {};
const step = async (name, fn) => { try { out[name] = await fn(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };

(async () => {
  run(`DATA=__FX.dashboard; APP=''; CURVIEW=null; RANGE='today'; window.__ax=null;`);
  // show(): the real one, plus the screen bookkeeping this small DOM cannot do (which screen is "on")
  run(`var __show0=show; show=function(id){ __setScreen(id); return __show0(id); };`);

  // ── the maths ────────────────────────────────────────────────────────────────────────────────────────────────────────
  await step('win', () => J(`(()=>{ const W=ecWin(); return {L:W.L,T:W.T,y:W.y,d7:W.d7,d30:W.d30,mtd:W.mtd,lm:W.lm,p7:W.p7,p30:W.p30,sw:W.sw,s30:W.s30,ncomp:W.comp.length,first:W.comp[0],last:W.comp[W.comp.length-1]}; })()`));
  await step('agg', () => J(`(()=>{ const A=ecAgg(); return {pfDays:Object.keys(A.pf).length, hasToday:(DATA.today_date in A.pf)||Object.values(A.apps).some(a=>DATA.today_date in a), apps:Object.keys(A.apps).sort()}; })()`));
  await step('pf_sums', () => J(`(()=>{ const W=ecWin(), pf=ecAgg().pf, s=d=>ecSum(pf,d); return {y:s(W.y),d7:s(W.d7),d30:s(W.d30),mtd:s(W.mtd),lm:s(W.lm),p7:s(W.p7),p30:s(W.p30)}; })()`));
  await step('rows', () => J(`(()=>{ const W=ecWin(), A=ecAgg().apps, o={}; Object.keys(A).forEach(n=>{ const r=ecRow(A[n],W); delete r.spark; o[n]=r; }); return o; })()`));
  await step('units', () => J(`(()=>{ const W=ecWin(); EC.app='Demo Gallery'; return ecUnits('Demo Gallery').map(u=>{ const r=ecRow(u.dm,W); return {id:u.id,format:u.format,y:r.y,w7:r.w7,imp:r.imp,st:r.st}; }); })()`));
  await step('status_fn', () => J(`[ecStatus(-0.25,0.03,5000),ecStatus(-0.07,0.05,5000),ecStatus(0.2,0.05,5000),ecStatus(0.06,0.05,5000),ecStatus(-0.03,0.01,5000),
      ecStatus(-0.05,0.01,5000),ecStatus(-0.5,0.03,999),ecStatus(-0.5,null,5000),ecStatus(null,0.03,0)]`));
  await step('pts_day', () => J(`(()=>{ const W=ecWin(), pf=ecAgg().pf; return ['30','90','365','all'].map(r=>{ const p=ecPts(pf,W,W.comp[0],r,'day'); return {r,n:p.length,first:p[0].k,last:p[p.length-1].k,
      lastEc:p[p.length-1].ec,firstPv:p[0].pv,anyToday:p.some(x=>x.k===DATA.today_date)}; }); })()`));
  await step('pts_month', () => J(`(()=>{ const W=ecWin(), pf=ecAgg().pf; return {all:ecPts(pf,W,W.comp[0],'all','month'),m30:ecPts(pf,W,W.comp[0],'30','month').map(p=>p.k),
      app:ecPts(ecAgg().apps['New Timer'],W,ecFirst(ecAgg().apps['New Timer']),'all','month')}; })()`));
  await step('chart', () => J(`(()=>{ const W=ecWin(), pf=ecAgg().pf, p=ecPts(pf,W,W.comp[0],'30','day'), g=ecChartSvg(p,800,false), S=ecPtStats(p);
      const pm=ecPts(pf,W,W.comp[0],'all','month'), gm=ecChartSvg(pm,360,true);
      return {svg:g.svg, n:g.xs.length, W:g.W, H:g.H, S, avgTxt:'avg '+cm(S.avg), maxTxt:'max '+cm(p[S.max].ec), minTxt:'min '+cm(p[S.min].ec), lastTxt:cm(p[S.last].ec),
        msvg:gm.svg, mW:gm.W, empty:ecChartSvg([],800,false), tipDay:ecTipHtml(p[p.length-1],false,false), tipPin:ecTipHtml(p[p.length-1],false,true), tipMonth:ecTipHtml(pm[pm.length-1],true,false)}; })()`));

  // ── the Overview tile = the view, for the same period (USD, then INR) ──────────────────────────────────────────────────
  const tileVal = html => { const m = /class="card kpi ec-kpi"[\s\S]*?<div class="v[^"]*">([^<]*)<\/div>/.exec(html); return m ? m[1] : null; };
  for (const cur of ['USD', 'INR']) {
    await step('consistency_' + cur, () => { run(cur === 'INR' ? `CURVIEW='INR';` : `CURVIEW=null;`); const res = {};
      for (const [rg, key] of [['yesterday', 'y'], ['7d', 'd7'], ['30d', 'd30'], ['month', 'mtd']]) {
        run(`RANGE='${rg}'; window.__ax=null;`); const html = run(`renderOverview().innerHTML`);
        res[rg] = { overview: tileVal(html), view: run(`ecCm(ecSum(ecAgg().pf,ecWin().${key}).ec)`) }; }
      // the view's own tiles (the first three: Yesterday, Last 7 days, Last 30 days) carry the same text
      run(`RANGE='today'; window.__ax=null; renderEcpm(); EC.app=''; EC.hdr=''; EC.booted=true; ecPaint();`);
      res.tiles = [...run(`EC.el.innerHTML`).matchAll(/<div class="card kpi"><div class="l">([^<]*)<\/div><div class="v[^"]*">([^<]*)<\/div>/g)].map(m => [m[1], m[2]]);
      res.html = run(`EC.el.innerHTML`);
      return res; });
  }
  run(`CURVIEW=null; RANGE='today'; window.__ax=null;`);
  await step('money_fmt', () => { run(`CURVIEW='INR'`); const r = J(`[ecCm(2),ecCmS(-0.26),ecCmS(0.000001),ecMoneyS(-1234.5),ecMoneyS(0.5),ecMoneyS(0),ecPct(-0.0812),ecPct(0.0004),ecPct(null),ecAx(0),ecAx(250/90),ecAx(12000/90)]`);
    run(`CURVIEW=null`); return { inr: r, usd: J(`[ecCm(2),ecCmS(-0.26),ecMoneyS(-1234.5),ecMoneyS(0.5),ecAx(2.5)]`) }; });

  // ── the entry: the Overview tile is a button into the view ─────────────────────────────────────────────────────────────
  await step('entry_tile', () => { run(`RANGE='7d'; window.__ax=null;`); const html = run(`renderOverview().innerHTML`); run(`RANGE='today'; window.__ax=null;`);
    const tile = (/<div class="card kpi ec-kpi"[^>]*>/.exec(html) || [''])[0];
    return { tile, n: (html.match(/ec-kpi/g) || []).length, hint: html.includes('<span class="ec-hint" aria-hidden="true">Trend →</span>'),
      label: /class="card kpi ec-kpi"[\s\S]*?<div class="l">Avg eCPM<\/div>/.test(html) }; });
  await step('entry_open', async () => { run(`renderEcpm(); localStorage.removeItem('ecpmview'); HB.st.length=0; HB.depth=0; HB.mute=0; APP=''; EC.booted=false;`); SCREEN.id = 'overview';
    run(`EC.r='365'; EC.g='month'; ecOpen();`); await settle();
    const a = J(`({screen:'${''}', app:EC.app, r:EC.r, g:EC.g, st:HB.st.map(x=>x.tag), title:document.getElementById('tb-title').textContent, html:EC.el.innerHTML.slice(0,4000)})`);
    a.screen = SCREEN.id;
    // with an app picked in the header, the tile opens THAT app's view
    run(`ecClose();`); await settle(); run(`APP='Puzzle Quest';`); run(`ecOpen();`); await settle();
    const b = J(`({app:EC.app, st:HB.st.map(x=>x.tag), title:document.getElementById('tb-title').textContent, all:EC.el.innerHTML.includes('All apps · yesterday vs last 7 days'), units:EC.el.innerHTML.includes('Ad units · yesterday vs last 7 days'), back:EC.el.innerHTML.includes('← All apps (eCPM)')})`);
    b.screen = SCREEN.id; run(`ecClose(); APP='';`); await settle(); return { a, b }; });

  // ── the phone's Back button ──────────────────────────────────────────────────────────────────────────────────────────
  await step('back', async () => { const R = {};
    run(`HB.st.length=0; HB.busy=false; HB.mute=0;`); await settle(); HIST.entries = [{ state: null, url: '/' }]; HIST.idx = 0; HIST.pending = []; run(`HB.depth=0;`);
    SCREEN.id = 'overview'; run(`APP=''; renderEcpm(); ecOpen();`); await settle();
    R.open = { screen: SCREEN.id, st: J(`HB.st.map(x=>x.tag)`), hist: HIST.entries.length, idx: HIST.idx };
    run(`ecApp('Demo Gallery')`); await settle();
    R.app = { screen: SCREEN.id, app: run('EC.app'), st: J(`HB.st.map(x=>x.tag)`), idx: HIST.idx };
    await userBack();
    R.back1 = { screen: SCREEN.id, app: run('EC.app'), st: J(`HB.st.map(x=>x.tag)`), idx: HIST.idx, all: run(`EC.el.innerHTML.includes('All apps · yesterday vs last 7 days')`) };
    await userBack();
    R.back2 = { screen: SCREEN.id, st: J(`HB.st.map(x=>x.tag)`), idx: HIST.idx };
    // "← Overview" on the page takes its steps off (no Back press left over)
    run(`ecOpen(); ecApp('Puzzle Quest');`); await settle(); R.reopen = { st: J(`HB.st.map(x=>x.tag)`), idx: HIST.idx };
    run(`ecClose()`); await settle(); R.closed = { screen: SCREEN.id, st: J(`HB.st.map(x=>x.tag)`), idx: HIST.idx };
    // "← All apps (eCPM)" on the page takes the app step off
    run(`ecOpen(); ecApp('Puzzle Quest');`); await settle(); run(`ecAllApps()`); await settle();
    R.allapps = { screen: SCREEN.id, app: run('EC.app'), st: J(`HB.st.map(x=>x.tag)`), idx: HIST.idx };
    // leaving the view another way (the menu): its steps go too
    run(`show('placements')`); await settle(); R.left = { screen: SCREEN.id, st: J(`HB.st.map(x=>x.tag)`), idx: HIST.idx };
    // a re-render of the open view (₹⇄$, the 5-min refresh) adds no step
    run(`show('overview'); ecOpen();`); await settle(); const before = HIST.entries.length;
    run(`HB.mute++; try{ show('ecpm'); }finally{ HB.mute--; }`); await settle(); R.rerender = { st: J(`HB.st.map(x=>x.tag)`), added: HIST.entries.length - before, screen: SCREEN.id };
    run(`ecClose()`); await settle();
    return R; });

  // ── sorting ──────────────────────────────────────────────────────────────────────────────────────────────────────────
  await step('sort', () => { run(`APP=''; EC.app=''; EC.hdr=''; EC.booted=true; EC.sort={k:'imp',d:'asc'}; EC.idle.a=false; renderEcpm(); ecPaint();`);
    const keys = (S) => J(`ecSortRows(EC.rows.a.filter(r=>r.act),${JSON.stringify(S)}).map(r=>r.key)`);
    const R = { def: keys({ k: 'imp', d: 'asc' }), rows: J(`EC.rows.a.map(r=>({key:r.key,imp:r.imp,st:r.st,act:r.act,pct:r.pct,yi:r.yi,y:r.y}))`) };
    R.toggles = [];
    for (const k of ['imp', 'imp', 'name', 'y', 'pct', 'st', 'yi', 'w7']) { run(`ecSort('a','${k}')`); R.toggles.push(J(`({k:EC.sort.k,d:EC.sort.d,order:ecSortRows(EC.rows.a.filter(r=>r.act),EC.sort).map(r=>r.key)})`)); }
    R.html = run(`ecTableHtml('a')`);
    run(`EC.sort={k:'imp',d:'asc'}`);
    R.idleHidden = run(`ecTableHtml('a')`).includes('Old Radio'); run(`ecIdle('a')`); R.idleShown = run(`ecTableHtml('a')`).includes('Old Radio'); run(`ecIdle('a')`);
    return R; });

  // ── the chart's tap rule (the listeners ecDraw attaches; ecTip stubbed to record what it was asked) ───────────────────
  await step('tap', () => { const w = mk('div'); w.setAttribute('id', 'ec-chw'); w.clientWidth = 600; const box = mk('div'), tip = mk('div');
    w.querySelector = s => (s === '.ec-svgw' ? box : (s === '.ec-tip' ? tip : null));
    run(`EC.ch={pts:ecPts(ecAgg().pf,ecWin(),ecWin().comp[0],'30','day'),month:false}; ecDraw(); var __tips=[]; var __ecTip0=ecTip; ecTip=function(x,pin){ __tips.push([x,!!pin]); };`);
    const fire = (t, e) => (w.on[t] || []).forEach(f => f(e));
    const R = { drawn: box.innerHTML.startsWith('<svg'), listeners: Object.keys(w.on).sort() };
    fire('pointermove', { pointerType: 'mouse', clientX: 100, clientY: 50 }); R.hover = J('__tips.splice(0)');
    fire('pointerdown', { pointerType: 'touch', clientX: 200, clientY: 80 }); fire('pointerup', { pointerType: 'touch', clientX: 204, clientY: 85 }); R.tap = J('__tips.splice(0)');
    fire('pointerdown', { pointerType: 'touch', clientX: 200, clientY: 80 }); fire('pointermove', { pointerType: 'touch', clientX: 200, clientY: 60 });
    fire('pointerup', { pointerType: 'touch', clientX: 201, clientY: 82 }); R.swipeBack = J('__tips.splice(0)');           // moved 20px, came back: still a swipe
    fire('pointerdown', { pointerType: 'touch', clientX: 200, clientY: 80 }); fire('pointerup', { pointerType: 'touch', clientX: 200, clientY: 91 }); R.swipe = J('__tips.splice(0)');
    fire('pointerdown', { pointerType: 'touch', clientX: 200, clientY: 80 }); fire('pointercancel', {}); fire('pointerup', { pointerType: 'touch', clientX: 200, clientY: 80 }); R.cancel = J('__tips.splice(0)');
    fire('pointerdown', { pointerType: 'pen', clientX: 300, clientY: 80 }); fire('pointerup', { pointerType: 'pen', clientX: 309, clientY: 80 }); R.pen = J('__tips.splice(0)');
    run(`ecTip=__ecTip0;`); delete ELS["ec-chw"]; return R; });

  out.errors = errors;
  process.stdout.write(JSON.stringify(out));
})().catch(e => { errors.push('MAIN ' + (e.stack || e.message)); out.errors = errors; process.stdout.write(JSON.stringify(out)); });
