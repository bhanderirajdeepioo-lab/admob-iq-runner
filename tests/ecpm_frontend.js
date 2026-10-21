// 📈 eCPM trend (frontend/index.html) — the page side, run for real: the dashboard script (the page's largest <script>) in a
// node vm with stub browser globals, a small DOM and a FAKE browser history (as tests/mobile_global_frontend.js), on the
// SYNTHETIC dashboard tests/test_ecpm_frontend.py writes (made-up apps, ids and money — no real data). It reports:
//   * the maths: the windows, yesterday / 7-day / 30-day / month-to-date sums, every app row (change, impact, swing,
//     status), the Day and Month chart points (today's partial day never in them), what the chart prints;
//   * the Overview "Avg eCPM" tile = the view's tiles for the same period (Yesterday / 7 days / 30 days), USD and INR;
//   * the entry (the tile is a button into the view; an app picked in the header opens that app's view), the phone's Back
//     button steps, leaving the view, the 5-min auto-refresh with a new build (the view back as it was, no jump), sorting
//     (default biggest loss first, low data last, every column toggles);
//   * the chart's tap rule: a tap (under 10px) pins the tooltip, a swipe / a cancelled pointer never does, a mouse hovers.
//   * 🔀 the tables' comparison picker (Yesterday vs 7 / 14 / 30 / 60 days / a month ‹ ›, Month vs month: ‹ current month ›
//     vs ‹ compared month ›, each moved on its own): every pick's rows, the month bounds, the labels, Ad units / Countries
//     following it (or saying why not), the viewer's pick restored (an old stored shape migrated), a long SYNTHETIC history
//     (fixture "long") for the month-to-month status, Oct vs Sep / Aug / Jul on SYNTHETIC October histories ("octs", "ramp").
// Prints ONE JSON report; tests/test_ecpm_frontend.py asserts on it (and recomputes the maths independently in Python).
//   usage: node ecpm_frontend.js <script.js> <fixture.json> [snap|ysnap|ctl]
//   snap: only the default view (All apps + one app, ₹ and $, every sort) with the comparison row taken out — run on the
//   page before the picker and on this one, the two must be byte-identical.
//   ysnap: every "Yesterday vs" pick and its taps (All apps + two apps, ₹ and $), comparison row included — run on the page
//   before the two Month vs month pickers and on this one, the two must be byte-identical.
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath, fxPath, mode] = process.argv.slice(2);
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

  if (mode === 'snap') {   // the default view, the comparison row (if this page has one) taken out
    const strip = h => (run(`typeof ecCmpCtl`) === 'function' ? h.split(run(`ecCmpCtl(EC.W,EC.C)`)).join('') : h);
    const rowsOf = t => J(`(EC.rows.${t}||[]).map(r=>{ const o=Object.assign({},r); delete o.lbl; return o; })`);
    await step('snap', () => { const S = {};
      for (const cur of ['USD', 'INR']) {
        run(`CURVIEW=${cur === 'INR' ? "'INR'" : 'null'}; renderEcpm(); APP=''; EC.app=''; EC.hdr=''; EC.booted=true; EC.sort={k:'imp',d:'asc'}; EC.usort={k:'imp',d:'asc'}; EC.csort={k:'imp',d:'asc'}; ecPaint();`);
        S['all_' + cur] = strip(run(`EC.el.innerHTML`)); S['rows_a_' + cur] = rowsOf('a');
        for (const k of ['imp', 'imp', 'name', 'y', 'w7', 'pct', 'yi', 'st']) { run(`ecSort('a','${k}')`); S[`sort_a_${cur}_${k}_${run('EC.sort.d')}`] = run(`ecTableHtml('a')`); }
        run(`ecIdle('a')`); S['idle_a_' + cur] = run(`ecTableHtml('a')`); run(`ecIdle('a'); EC.sort={k:'imp',d:'asc'};`);
        for (const app of ['Demo Gallery', 'Puzzle Quest']) {
          run(`EC.app=${JSON.stringify(app)}; ecPaint();`);
          S[`app_${cur}_${app}`] = strip(run(`EC.el.innerHTML`)); S[`rows_u_${cur}_${app}`] = rowsOf('u'); S[`rows_c_${cur}_${app}`] = rowsOf('c');
          for (const k of ['name', 'pct', 'yi']) { run(`ecSort('u','${k}'); ecSort('c','${k}')`); S[`sort_uc_${cur}_${app}_${k}`] = run(`ecTableHtml('u')+ecTableHtml('c')`); }
          run(`EC.usort={k:'imp',d:'asc'}; EC.csort={k:'imp',d:'asc'}; ecCAll();`); S[`call_${cur}_${app}`] = run(`ecTableHtml('c')`); run(`ecCAll()`);
        }
        run(`EC.app='';`);
      }
      run(`CURVIEW=null;`);
      return { S, hasCtl: run(`typeof ecCmpCtl`) === 'function' }; });
    out.errors = errors; process.stdout.write(JSON.stringify(out)); return;
  }
  if (mode === 'ysnap') {   // "Yesterday vs": every pick, then its taps, as HTML + rows (the stored pick itself is not compared)
    const rowsOf = t => J(`(EC.rows.${t}||[]).map(r=>{ const o=Object.assign({},r); delete o.lbl; return o; })`);
    const R0 = `localStorage.removeItem('ecpmcmp'); APP=''; EC.hdr=''; EC.booted=true; EC.cValid=null; EC.sort={k:'imp',d:'asc'}; EC.usort={k:'imp',d:'asc'}; EC.csort={k:'imp',d:'asc'}; EC.idle={a:false,u:false,c:false};`;
    await step('ysnap', () => { const S = {};
      const picks = [{ b: '7' }, { b: '14' }, { b: '30' }, { b: '60' }, { b: 'mon' }, { b: 'mon', bm: '2026-01' }, { b: 'mon', bm: '2025-12' }, { b: 'mon', bm: '2026-03' }];
      const look = k => { run(`EC.app=''; ecPaint();`); S['all_' + k] = run(`EC.el.innerHTML`); S['rows_a_' + k] = rowsOf('a');
        for (const app of ['Demo Gallery', 'New Timer']) { run(`EC.app=${JSON.stringify(app)}; ecPaint();`);
          S[`app_${app}_${k}`] = run(`EC.el.innerHTML`); S[`rows_u_${app}_${k}`] = rowsOf('u'); S[`rows_c_${app}_${k}`] = rowsOf('c'); }
        run(`EC.app='';`); };
      for (const cur of ['USD', 'INR']) {
        run(`CURVIEW=${cur === 'INR' ? "'INR'" : 'null'}; renderEcpm(); ` + R0);
        for (const p of picks) { run(`EC.cmp=${JSON.stringify(Object.assign({ m: 'y', b: '7', bm: '', cm: '' }, p))};`); look(cur + JSON.stringify(p)); }
        run(R0 + `EC.cmp=null; EC.app=''; ecPaint();`);
        ["ecCmpB('mon')", 'ecCmpMon(-1)', 'ecCmpMon(-1)', 'ecCmpMon(-1)', 'ecCmpMon(1)', 'ecCmpMon(1)', 'ecCmpMon(1)', 'ecCmpMon(1)', "ecCmpB('30')", "ecCmpB('mon')", "ecCmpB('7')"]
          .forEach((code, i) => { run(code); S[`tap_${cur}_${i}_${code}`] = run(`EC.el.innerHTML`); });
        run(`EC.app='Demo Gallery'; ecPaint();`);
        ["ecCmpB('14')", "ecCmpB('mon')", 'ecCmpMon(-1)', "ecCmpB('60')", "ecCmpB('7')"].forEach((code, i) => { run(code); S[`tapu_${cur}_${i}_${code}`] = run(`EC.el.innerHTML`); });
        run(`EC.app='';`);
      }
      run(`CURVIEW=null;`); return { S }; });
    out.errors = errors; process.stdout.write(JSON.stringify(out)); return;
  }
  if (mode === 'ctl') {   // the REAL comparison rows, before / after each tap (for tests/stayput_frontend.js): each table card's head
    const heads = () => run(`EC.el.innerHTML`).split('<div class="card ec-tc">').slice(1).map(c => c.split('<div class="ec-note')[0]);
    const T = [], go = (name, code, card) => { const before = heads(); run(code); T.push({ name, code, card, before, after: heads() }); };
    await step('ctl', () => {
      run(`localStorage.removeItem('ecpmcmp'); EC.cmp=null; EC.cValid=null; APP=''; EC.hdr=''; EC.booted=true; renderEcpm(); EC.app=''; ecPaint();`);
      go('y7_to_month', `ecCmpB('mon')`, 0); go('month_prev', `ecCmpMon(-1)`, 0);           // Feb → Jan (kept for later)
      go('y_to_m', `ecCmpM('m')`, 0);                                                      // Mar (1–10) vs Feb
      go('vs_prev', `ecCmpVs(-1)`, 0); go('vs_prev_first', `ecCmpVs(-1)`, 0);               // vs Jan, vs Dec (20–31): ‹ greys out
      go('vs_next', `ecCmpVs(1)`, 0);                                                      // vs Jan
      go('cur_prev', `ecCmpCur(-1)`, 0); go('cur_prev_push', `ecCmpCur(-1)`, 0);            // Feb vs Jan, Jan vs Dec (pushed)
      go('cur_next', `ecCmpCur(1)`, 0); go('cur_next_last', `ecCmpCur(1)`, 0);              // Feb vs Dec, Mar (1–10) vs Dec: › greys out
      go('m_to_y_stored_month', `ecCmpM('y')`, 0); go('month_next', `ecCmpMon(1)`, 0);       // back to Yesterday vs Jan 2026, then Feb
      go('month_to_14', `ecCmpB('14')`, 0); go('b14_to_7', `ecCmpB('7')`, 0);
      run(`EC.app='Demo Gallery'; ecPaint();`);                                   // one app: the Ad units + Countries twins
      go('app_y_to_m_countries', `ecCmpM('m')`, 1); go('app_vs_next_countries', `ecCmpVs(1)`, 1); go('app_cur_prev_countries', `ecCmpCur(-1)`, 1);
      go('app_cur_next_units', `ecCmpCur(1)`, 0); go('app_m_to_y_units', `ecCmpM('y')`, 0);
      go('app_7_to_month_countries', `ecCmpB('mon')`, 1);
      return T; });
    out.errors = errors; process.stdout.write(JSON.stringify(out)); return;
  }

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
      // Today (live): the tile = today's rows only, summed here on their own (and one app's)
      res.today = J(`(()=>{ const T=DATA.today_date; let e=0,i=0,ea=0,ia=0; (DATA.placements||[]).forEach(p=>(p.daily||[]).forEach(r=>{ if(r[0]===T){ e+=r[1]; i+=r[2]; if(p.app==='New Timer'){ ea+=r[1]; ia+=r[2]; } } }));
        return {T, own:i?ecCm(e/(i*1000)):null, fn:ecCm(ecToday('').ec), app:ia?ecCm(ea/(ia*1000)):null, appFn:ecCm(ecToday('New Timer').ec), none:(()=>{ const k=DATA.today_date; DATA.today_date=''; const x=ecToday(''); DATA.today_date=k; return x; })()}; })()`);
      return res; });
  }
  run(`CURVIEW=null; RANGE='today'; window.__ax=null;`);
  // 📈 same time yesterday (DATA.ecpm_intraday, made up here): yesterday at 10:00 = between its 09:00 and 11:00 points;
  // the last hour = today's 10:00 point minus its 09:00 one, and the same hour yesterday
  await step('intra', () => { const T = run(`DATA.today_date`), tiles = () => run(`EC.app=''; ecPaint(); EC.el.innerHTML.split('class="card ec-cc"')[0]`);
    const X = { v: 1, today: T, yday: 'x', since: '2026-01-01', t: [[540, 2e6, 1000], [600, 6e6, 2000]], y: [[540, 3e6, 1000], [660, 6e6, 2000]], apps: {} };
    run(`DATA.ecpm_intraday=${JSON.stringify(X)}`); const full = tiles(), ix = J(`ecIntra('')`);
    run(`DATA.ecpm_intraday.y=[[480,3e6,1000],[900,9e6,3000]]`); const gap = J(`ecIntra('')`);           // 7 h apart, 2 h after the first: none
    run(`DATA.ecpm_intraday.y=[[540,3e6,1000],[900,9e6,3000]]`); const gapNear = J(`ecIntra('')`);       // 6 h apart, 1 h after the first: that point
    run(`DATA.ecpm_intraday.y=[[500,3e6,1000]]`); const late = J(`ecIntra('')`);                            // its last point 100 min before: none
    run(`DATA.ecpm_intraday.y=[[530,3e6,1000]]`); const near = J(`ecIntra('')`);                            // 70 min before: that point
    run(`DATA.ecpm_intraday.y=[]; DATA.ecpm_intraday.since=DATA.today_date`); const first = tiles();        // the first day: "from tomorrow"
    run(`DATA.ecpm_intraday.since='2026-01-01'`); const missing = tiles();
    run(`DATA.ecpm_intraday.today='1999-01-01'`); const stale = tiles(); run(`delete DATA.ecpm_intraday`); const none = tiles();
    // the tile's small chart: today's line + yesterday's, a point on a sliver of the day's impressions left out
    run(`DATA.ecpm_intraday={v:1,today:DATA.today_date,since:'2026-01-01',apps:{},t:[[30,5e3,10],[540,2e6,1000],[600,6e6,2000]],y:[[540,3e6,1000],[660,6e6,2000],[1430,9e6,3000]]};`);
    const spk = run(`ecTodaySpark('')`), pts = J(`ecSpkPts(DATA.ecpm_intraday.t)`), val = J(`[ecSpkVal(DATA.ecpm_intraday.y,600), ecSpkVal(DATA.ecpm_intraday.y,1000), ecSpkVal(DATA.ecpm_intraday.y,10)]`);
    run(`DATA.ecpm_intraday.y=[]`); const spk1 = run(`ecTodaySpark('')`); const tileSpk = tiles().includes('class="ec-spk"'); const rowSpk = run(`EC.rows={a:ecRowsFor('a',ecWin())}; ecTableHtml('a')`); run(`delete DATA.ecpm_intraday`);
    return { full, ix, gap, gapNear, late, near, first, spk, pts, val, spk1, tileSpk, rowSpk, missing, stale, none, next: run(`fmtD(ecNextDay(DATA.today_date))`) }; });
  // every tile's chart + the 12-hour clock
  await step('tilecharts', () => { const T = run(`DATA.today_date`);
    run(`DATA.ecpm_intraday={v:1,today:DATA.today_date,since:DATA.today_date,apps:{},t:[[540,2e6,1000],[600,6e6,2000]],y:[]};`);
    const h = run(`EC.app=''; ecPaint(); EC.el.innerHTML.split('class="card ec-cc"')[0]`); run(`delete DATA.ecpm_intraday`);
    const legends = [...h.matchAll(/<div class="ec-spl">([\s\S]*?)<\/div>/g)].map(m => [...m[1].matchAll(/<span class="ec-spl-[a-z]">([^<]*)<\/span>/g)].map(x => x[1]));
    const gap = J(`(()=>{ const dm={'2026-01-01':[3e6,1000],'2026-01-03':[4e6,1000],'2026-01-04':[5e6,1000]}; const s=ecPairSpark(dm,['2026-01-01','2026-01-02','2026-01-03','2026-01-04'],null,'x',''); return (/class="ec-spt0" ?|<path d="([^"]*)" class="ec-spt0"/.exec(s)||[])[1]||''; })()`);
    return { hm: J(`[0,600,720,785,1439].map(ecHm)`), n: (h.match(/class="ec-spk"/g) || []).length, legends,
      avgLine: (h.match(/class="ec-spa"/g) || []).length, prevLines: (h.match(/class="ec-spy"/g) || []).length,
      onePt: run(`ecPairSpark({'2026-01-01':[1e6,100]},['2026-01-01'],null,'x','')`), gap, next: run(`fmtD(ecNextDay(DATA.today_date))`) }; });
  // the Date-wise report's Month rows (owner: "date-wise to aa hi raha hai, ek option month ka bhi … table me hi")
  await step('datewise_month', () => { run(`RANGE='all'; window.__ax=null;`);
    const rows = J(`dateWiseRows(curWinArr())`), mon = J(`dwMonthRows(dateWiseRows(curWinArr()))`);
    const tblM = run(`dateWiseTable(dateWiseRows(curWinArr()),'month')`), tblD = run(`dateWiseTable(dateWiseRows(curWinArr()),'day')`);
    run(`DWMODE='month'`); const box = run(`dwBoxHtml()`); run(`dwSetMode('day')`);
    const res = { rows, mon, tblM, tblD, box, ls: run(`localStorage.getItem('iq_dwmode')`), mode: run(`DWMODE`) };
    run(`RANGE='today'; window.__ax=null;`); return res; });
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

  // ── the 5-min auto-refresh with a NEW build: the view comes back as it was (app, range, Day/Month, sort), silently ────
  await step('refresh', async () => {
    run(`HB.st.length=0; HB.busy=false; HB.mute=0;`); await settle(); HIST.entries = [{ state: null, url: '/' }]; HIST.idx = 0; HIST.pending = []; run(`HB.depth=0;`);
    SCREEN.id = 'overview'; run(`APP=''; renderEcpm(); ecOpen(); ecApp('Demo Gallery'); ecSetR('365'); ecSetG('month'); ecSort('u','name');`); await settle();
    const scrolls = []; ctx.scrollTo = (...a) => scrolls.push(JSON.stringify(a)); ctx.scrollY = 1234;
    run(`var __render0=render; render=function(){ window.__ax=null; renderEcpm(); show('overview'); };   // the real render(): every screen rebuilt (empty), ends on Overview
         var __load0=loadDashboardData; loadDashboardData=function(){ const d=JSON.parse(JSON.stringify(__FX.dashboard)); d.generated_at='2026-03-11T07:00:00+00:00'; return Promise.resolve(d); };
         LAST_BUILD='2026-03-11T06:00:00+00:00'; var __old=DATA;`);
    await run(`refreshData()`); await settle();
    const R = J(`({app:EC.app, r:EC.r, g:EC.g, usort:EC.usort, st:HB.st.map(x=>x.tag), newData:DATA!==__old, rebuilt:EC.cacheD===DATA,
      units:EC.el.innerHTML.includes('Ad units · yesterday vs last 7 days'), month:EC.el.innerHTML.includes('Monthly eCPM'), silent:REFRESH_SILENT})`);
    R.screen = SCREEN.id; R.scrolls = scrolls.filter(s => s.includes('"top":0')); R.hist = HIST.entries.length;
    run(`render=__render0; loadDashboardData=__load0; DATA=__FX.dashboard; ecClose();`); await settle(); ctx.scrollTo = () => {}; ctx.scrollY = 0;
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

  // ── 🔀 the tables' comparison picker ──────────────────────────────────────────────────────────────────────────────────
  const CMP0 = `localStorage.removeItem('ecpmcmp'); EC.cmp=null; EC.cValid=null; APP=''; EC.hdr=''; EC.booted=true; EC.sort={k:'imp',d:'asc'}; EC.usort={k:'imp',d:'asc'}; EC.csort={k:'imp',d:'asc'}; EC.idle={a:false,u:false,c:false};`;
  const cards = () => run(`EC.el.innerHTML`).split('<div class="card ec-tc">').slice(1);
  const ctlSigs = h => [...h.matchAll(/<button type="button"[^>]*onclick="(ecCmp[A-Za-z]+\([^)]*\))"[^>]*>/g)].map(m => m[1] + (/aria-label="([^"]*)"/.exec(m[0]) || ['', ''])[1]);
  // every pick's rows (all apps + one app's ad units), the days on each side, the labels
  await step('cmp_math', () => J(`(()=>{ const W=ecWin(), A=ecAgg().apps, out={};
    const sels={b7:{m:'y',b:'7'},b14:{m:'y',b:'14'},b30:{m:'y',b:'30'},b60:{m:'y',b:'60'},mon:{m:'y',b:'mon'},monJan:{m:'y',b:'mon',bm:'2026-01'},
      monDec:{m:'y',b:'mon',bm:'2025-12'},monMar:{m:'y',b:'mon',bm:'2026-03'},mm:{m:'m'},mmFeb:{m:'m',cm:'2026-02'},mmJan:{m:'m',cm:'2026-01'},
      mmVsJan:{m:'m',vm:'2026-01'},mmVsDec:{m:'m',vm:'2025-12'},mmFebDec:{m:'m',cm:'2026-02',vm:'2025-12'}};
    for(const k in sels){ const C=ecCmpC(W,sels[k]), rows={}; Object.keys(A).forEach(n=>{ const r=ecRow(A[n],W,C); delete r.spark; rows[n]=r; });
      out[k]={def:!!C.def,m:C.m,g:C.g,cur:C.cur,base:C.base,ncur:C.ncur,curL:C.curL,baseL:C.baseL,title:C.title,colCur:C.colCur,colBase:C.colBase,colImp:C.colImp,
        S:C.S,swm:(C.swm||[]).map(o=>o.k),rows,units:ecUnits('Demo Gallery').map(u=>{ const r=ecRow(u.dm,W,C); return {id:u.id,y:r.y,w7:r.w7,chg:r.chg,imp:r.imp,yi:r.yi,st:r.st}; })}; }
    const M=ecMon(W); out.bounds={bMin:M.bMin,bMax:M.bMax,bDef:M.bDef,bOk:M.bOk,cMin:M.cMin,cMax:M.cMax,cOk:M.cOk,vMin:M.vMin,ks:M.ks};
    out.gap=[ecMGap('2026-09','2026-10'),ecMGap('2026-07','2026-10'),ecMGap('2025-11','2026-02'),ecMGap('2025-12','2025-12')];
    out.madd=[ecMAdd('2026-01',-1),ecMAdd('2025-12',1),ecMAdd('2026-03',-14),ecMAdd('2026-11',2)];
    out.perL=[ecPerL('2026-02',M.by['2026-02']),ecPerL('2025-12',M.by['2025-12']),ecPerL('2026-03',M.by['2026-03']),ecPerL('2026-03',['2026-03-01'])];
    return out; })()`));
  // the control row, tap by tap: chips, ‹ › to the bounds and back, what the card says; the tapped control is still there
  // (same signature, same count — the stay-put layer finds it again) and the pick is saved for this viewer
  await step('cmp_nav', () => { run(CMP0 + `EC.app=''; renderEcpm(); ecPaint();`); const R = { taps: [] };
    const st = () => Object.assign(J(`({cmp:EC.cmp,title:EC.C.title,curL:EC.C.curL,baseL:EC.C.baseL,ls:localStorage.getItem('ecpmcmp'),ctl:ecCmpCtl(EC.W,EC.C)})`),
      { card: cards()[0].split('<div id="ec-tb-a">')[0] });
    const tap = (code, sig) => { const b = ctlSigs(run(`EC.el.innerHTML`)); run(code); const a = ctlSigs(run(`EC.el.innerHTML`));
      R.taps.push({ code, sig, before: b.filter(x => x === sig).length, after: a.filter(x => x === sig).length }); return st(); };
    R.def = st();
    R.b14 = tap(`ecCmpB('14')`, `ecCmpB('14')`); R.b60 = tap(`ecCmpB('60')`, `ecCmpB('60')`);
    R.feb = tap(`ecCmpB('mon')`, `ecCmpB('mon')`);
    R.jan = tap(`ecCmpMon(-1)`, `ecCmpMon(-1)Previous month`); R.dec = tap(`ecCmpMon(-1)`, `ecCmpMon(-1)Previous month`); R.decStay = tap(`ecCmpMon(-1)`, `ecCmpMon(-1)Previous month`);
    tap(`ecCmpMon(1)`, `ecCmpMon(1)Next month`); R.feb2 = tap(`ecCmpMon(1)`, `ecCmpMon(1)Next month`);
    R.mar = tap(`ecCmpMon(1)`, `ecCmpMon(1)Next month`); R.marStay = tap(`ecCmpMon(1)`, `ecCmpMon(1)Next month`);
    // Month vs month: two pickers — ‹ current month › vs ‹ compared month ›, each moved on its own
    const CP = 'ecCmpCur(-1)Current month: previous', CN = 'ecCmpCur(1)Current month: next', VP = 'ecCmpVs(-1)Compared month: previous', VN = 'ecCmpVs(1)Compared month: next';
    R.m = tap(`ecCmpM('m')`, `ecCmpM('m')`); R.mCurStay = tap(`ecCmpCur(1)`, CN); R.mVsStay = tap(`ecCmpVs(1)`, VN);   // both at their newest: stay
    R.vJan = tap(`ecCmpVs(-1)`, VP); R.vDec = tap(`ecCmpVs(-1)`, VP); R.vDecStay = tap(`ecCmpVs(-1)`, VP);            // the compared month alone
    R.vJan2 = tap(`ecCmpVs(1)`, VN);
    R.cFeb = tap(`ecCmpCur(-1)`, CP); R.cJan = tap(`ecCmpCur(-1)`, CP); R.cJanStay = tap(`ecCmpCur(-1)`, CP);        // Jan reaches Jan: pushed to Dec
    R.cFeb2 = tap(`ecCmpCur(1)`, CN); R.cMar = tap(`ecCmpCur(1)`, CN);                                               // the compared month stays (Dec)
    tap(`ecCmpVs(1)`, VN); R.vFeb = tap(`ecCmpVs(1)`, VN);                                                           // Dec → Jan → Feb: the default pair again
    run(`ecCmpMon(-1)`); R.monInM = st(); run(`ecCmpVs(1)`);                                                         // the Yesterday-vs ‹ (never shown here) = the compared month's
    R.backY = tap(`ecCmpM('y')`, `ecCmpM('y')`);   // back to Yesterday: its month (Mar, navigated) is still picked
    R.b7 = tap(`ecCmpB('7')`, `ecCmpB('7')`);
    R.b7html = run(`EC.el.innerHTML`);
    run(CMP0 + `ecPaint();`); return R; });
  // the table under each pick: icons, row tap, N/A last, sorting, the notes; the app view (Ad units / Countries) follows
  await step('cmp_table', async () => { const R = {};
    run(CMP0 + `EC.app=''; ecPaint();`);
    for (const [k, sel] of [['b14', { m: 'y', b: '14' }], ['mon', { m: 'y', b: 'mon' }], ['monDec', { m: 'y', b: 'mon', bm: '2025-12' }], ['monMar', { m: 'y', b: 'mon', bm: '2026-03' }], ['mm', { m: 'm' }], ['mmJan', { m: 'm', cm: '2026-01' }]]) {
      run(`EC.cmp=${JSON.stringify(Object.assign({ m: 'y', b: '7', bm: '', cm: '' }, sel))}; EC.sort={k:'imp',d:'asc'}; ecPaint();`);
      const o = { card: cards()[0], order: J(`ecSortRows(EC.rows.a.filter(r=>r.act),EC.sort).map(r=>r.key)`),
        rows: J(`EC.rows.a.map(r=>({key:r.key,imp:r.imp,st:r.st,act:r.act,yi:r.yi,y:r.y,w7:r.w7,pct:r.pct,label:r.label}))`), toggles: [] };
      for (const s of ['pct', 'name', 'yi', 'w7', 'y', 'st']) { run(`ecSort('a','${s}')`); o.toggles.push(J(`({k:EC.sort.k,d:EC.sort.d,order:ecSortRows(EC.rows.a.filter(r=>r.act),EC.sort).map(r=>r.key)})`)); }
      run(`ecIdle('a')`); o.idle = run(`ecTableHtml('a')`); run(`ecIdle('a')`);
      R[k] = o; }
    // a row tap opens that app's view under the same pick: Ad units + Countries follow it
    run(`HB.st.length=0; HB.busy=false; HB.mute=0; EC.cmp={m:'m',b:'7',bm:'',cm:''}; EC.sort={k:'imp',d:'asc'}; ecPaint();`); await settle();
    run(`ecApp('Demo Gallery')`); await settle();
    const c = cards(); R.app = { app: run('EC.app'), units: c[0], countries: c[1] || '', u: J(`EC.rows.u.map(r=>({key:r.key,y:r.y,w7:r.w7,imp:r.imp,yi:r.yi,st:r.st}))`),
      c: J(`EC.rows.c.map(r=>({key:r.key,y:r.y,w7:r.w7,imp:r.imp,yi:r.yi,st:r.st}))`), nav: run(`EC.el.innerHTML.split('<div class="ec-hd">')[0]`),
      order: J(`ecSortRows(Object.keys(ecAgg().apps).map(n=>Object.assign(ecRow(ecAgg().apps[n],EC.W,EC.C),{key:n,label:ecAppLbl(n).label})).filter(r=>r.act||r.key==='Demo Gallery'),EC.sort).map(r=>r.key)`) };
    run(`ecAllApps()`); await settle(); R.back = { app: run('EC.app'), title: run(`EC.C.title`) };
    // the app view under a compared month 2 back (Mar vs Jan): Ad units + Countries follow both picks
    run(`EC.cmp={m:'m',vm:'2026-01'}; EC.app='Demo Gallery'; ecPaint();`);
    { const c2 = cards(), rw = t => J(`EC.rows.${t}.map(r=>({key:r.key,y:r.y,w7:r.w7,chg:r.chg,pct:r.pct,imp:r.imp,yi:r.yi,swing:r.swing,st:r.st}))`);
      R.appVs = { units: c2[0], countries: c2[1] || '', ct: J(`({u:EC.Ct.u.title,c:EC.Ct.c.title})`), u: rw('u'), c: rw('c') }; }
    run(`EC.app=''; ecPaint();`);
    // an app younger than the baseline: its card says from when it has data (its rows are its own days, never padded)
    run(`EC.cmp={m:'y',b:'14',bm:'',cm:''}; EC.app='New Timer'; ecPaint();`); R.young = cards()[0].split('<div id="ec-tb-u">')[0];
    run(`EC.cmp={m:'y',b:'7',bm:'',cm:''}; ecPaint();`); R.youngDef = cards()[0].split('<div id="ec-tb-u">')[0];
    run(CMP0 + `EC.app=''; ecPaint();`); return R; });
  // Countries: its own report and history — a pick it does not cover keeps its last covered view and says so in one line
  await step('cmp_cards', () => { run(CMP0 + `EC.app='Demo Gallery'; ecPaint();`); const R = {};
    const look = () => { const c = cards(); return { units: c[0].split('<div id="ec-tb-u">')[0], countries: (c[1] || '').split('<div id="ec-tb-c">')[0], cmp: J('EC.cmp'),
      ct: J(`({u:EC.Ct.u.title,c:EC.Ct.c.title,cb:EC.Ct.c.base.length})`), u: J(`EC.rows.u.map(r=>({key:r.key,w7:r.w7,imp:r.imp}))`), c: J(`EC.rows.c.map(r=>({key:r.key,w7:r.w7,imp:r.imp,y:r.y}))`),
      ctlN: (run(`EC.el.innerHTML`).match(/<div class="ec-cmp">/g) || []).length }; };
    R.def = look();
    run(`ecCmpB('14')`); R.full14 = look();
    run(`var __cd0=DATA.countries_daily['Demo Gallery']; DATA.countries_daily['Demo Gallery']=Object.fromEntries(Object.entries(__cd0).map(([c,rows])=>[c,rows.filter(r=>r[0]>='2026-02-15')]));`);
    run(`ecPaint()`); R.short14 = look();
    run(`ecCmpB('mon')`); R.shortMon = look();
    run(`ecCmpB('60')`); R.short60 = look();
    run(`ecCmpM('m')`); R.shortMm = look();
    run(`EC.cValid=null; ecPaint()`); R.fresh = look();
    run(`ecCmpM('y'); ecCmpB('7')`); R.shortDef = look();
    run(`DATA.countries_daily['Demo Gallery']=__cd0;`); run(CMP0 + `EC.app=''; ecPaint();`); return R; });
  // this viewer's pick comes back (a reload, a new day); a stored month outside the history / junk / blocked storage → safe
  await step('cmp_restore', () => { const R = {};
    const paint = ls => { if (ls === undefined) run(`localStorage.removeItem('ecpmcmp')`); else run(`localStorage.setItem('ecpmcmp', ${JSON.stringify(ls)})`);
      run(`EC.cmp=null; EC.app=''; ecPaint();`); return J(`({cmp:EC.cmp,title:EC.C.title,ls:localStorage.getItem('ecpmcmp')})`); };
    // the shape stored before the two Month vs month pickers (no v; its cm moved BOTH months): the Yesterday-vs pick kept,
    // the month pair → this month vs the month before; saved back in the new shape
    R.oldMm = paint(JSON.stringify({ m: 'm', b: '7', bm: '', cm: '2026-02' }));
    R.oldMmMon = paint(JSON.stringify({ m: 'm', b: 'mon', bm: '2026-01', cm: '' }));
    R.monJan = paint(JSON.stringify({ m: 'y', b: 'mon', bm: '2026-01', cm: '' }));
    R.b30 = paint(JSON.stringify({ m: 'y', b: '30', bm: '', cm: '' }));
    // the new shape
    R.mFeb = paint(JSON.stringify({ v: 2, m: 'm', b: '7', bm: '', cm: '2026-02', vm: '' }));
    R.mFebDec = paint(JSON.stringify({ v: 2, m: 'm', b: '7', bm: '', cm: '2026-02', vm: '2025-12' }));
    R.mVsJan = paint(JSON.stringify({ v: 2, m: 'm', b: '7', bm: '', cm: '', vm: '2026-01' }));
    R.vmSame = paint(JSON.stringify({ v: 2, m: 'm', b: '7', bm: '', cm: '2026-02', vm: '2026-02' }));     // not older than the current
    R.vmAfter = paint(JSON.stringify({ v: 2, m: 'm', b: '7', bm: '', cm: '2026-02', vm: '2026-03' }));
    R.vmBefore = paint(JSON.stringify({ v: 2, m: 'm', b: '7', bm: '', cm: '', vm: '2025-06' }));        // before the history
    R.vmJunk = paint(JSON.stringify({ v: 2, m: 'm', b: '7', bm: '', cm: '', vm: 202601 }));
    R.vmDefault = paint(JSON.stringify({ v: 2, m: 'm', b: '7', bm: '', cm: '2026-02', vm: '2026-01' }));  // = the default: kept as ''
    R.future = paint(JSON.stringify({ v: 3, m: 'm', b: '14', bm: '', cm: '2026-02', vm: '2025-12' }));   // an unknown shape: months reset
    R.before = paint(JSON.stringify({ v: 2, m: 'y', b: 'mon', bm: '2024-05', cm: '', vm: '' }));
    R.after = paint(JSON.stringify({ v: 2, m: 'm', b: '7', bm: '', cm: '2026-09', vm: '' }));
    R.junk = paint(JSON.stringify({ m: 'x', b: '99', bm: 5, cm: '2026-13' }));
    R.arr = paint(JSON.stringify([1, 2]));
    R.bad = paint('not json'); R.none = paint(undefined);
    // a new build with less history: the stored 60 days / month no longer fit → the default, saved back
    R.b60 = paint(JSON.stringify({ v: 2, m: 'y', b: '60', bm: '2025-12', cm: '', vm: '2025-12' }));
    run(`var __D1=DATA; DATA=JSON.parse(JSON.stringify(DATA)); DATA.placements.forEach(p=>{ p.daily=p.daily.filter(r=>r[0]>='2026-02-01'); }); window.__ax=null;`);
    run(`EC.cmp=null; ecPaint();`); R.shorter = J(`({cmp:EC.cmp,title:EC.C.title,ls:localStorage.getItem('ecpmcmp'),bounds:(()=>{ const M=ecMon(EC.W); return [M.bMin,M.bMax,M.cMin,M.cMax,M.cOk]; })(),ctl:ecCmpCtl(EC.W,EC.C)})`);
    run(`DATA=__D1; window.__ax=null;`);
    // storage that throws (a private window): the default, then a tap still works, no error
    run(`var __ls0=localStorage; localStorage={getItem(){ throw new Error('blocked'); },setItem(){ throw new Error('blocked'); },removeItem(){}};`);
    run(`EC.cmp=null; ecPaint();`); R.blocked0 = J(`({cmp:EC.cmp,title:EC.C.title})`);
    run(`ecCmpB('30')`); R.blocked = J(`({cmp:EC.cmp,title:EC.C.title})`);
    run(`localStorage=__ls0;`); run(CMP0 + `EC.app=''; ecPaint();`); return R; });
  // a long SYNTHETIC history (14 months): the month-to-month swing and status, the month-mode table
  await step('cmp_long', () => { run(`var __D0=DATA; DATA=__FX.long; window.__ax=null; EC.cache=null; EC.ucache={};`); const R = {};
    R.sel = J(`(()=>{ const W=ecWin(), A=ecAgg().apps, o={}; for(const s of [{m:'m'},{m:'m',cm:'2026-02'},{m:'m',cm:'2025-09'},{m:'m',cm:'2025-08'},{m:'y',b:'mon'},{m:'y',b:'60'}]){ const C=ecCmpC(W,s), rows={};
      Object.keys(A).forEach(n=>{ const r=ecRow(A[n],W,C); delete r.spark; rows[n]=r; }); o[JSON.stringify(s)]={swm:(C.swm||[]).map(x=>x.k),title:C.title,cur:C.cur,base:C.base,ncur:C.ncur,rows}; } return o; })()`);
    run(CMP0 + `EC.cmp={m:'m',b:'7',bm:'',cm:''}; EC.app=''; ecPaint();`);
    R.card = cards()[0]; R.order = J(`ecSortRows(EC.rows.a.filter(r=>r.act),EC.sort).map(r=>r.key)`);
    run(`DATA=__D0; window.__ax=null; EC.cache=null; EC.ucache={};`); run(CMP0 + `EC.app=''; ecPaint();`); return R; });
  // edges (SYNTHETIC fixtures): a launch ramp just before a month ends (a baseline of a few hundred impressions), a row
  // that starts inside the period, the 1st of a month (the month of yesterday is whole), a history shorter than 7 days
  const useFx = k => run(`var __Dk=DATA; DATA=__FX.${k}; window.__ax=null; EC.cache=null; EC.ucache={}; EC.cValid=null;`);
  const unFx = () => { run(`DATA=__FX.dashboard; window.__ax=null; EC.cache=null; EC.ucache={};`); run(CMP0 + `EC.app=''; ecPaint();`); };
  const rowsUnder = sel => J(`(()=>{ const W=ecWin(), A=ecAgg().apps, C=ecCmpC(W,${JSON.stringify(sel)}), o={}; Object.keys(A).forEach(n=>{ const r=ecRow(A[n],W,C); delete r.spark; o[n]=r; });
    return {title:C.title,dn:C.dn,cur:C.cur,base:C.base,rows:o}; })()`);
  await step('cmp_edge', () => { const R = {};
    useFx('ramp');
    for (const [k, sel] of [['mon', { m: 'y', b: 'mon' }], ['mm', { m: 'm' }], ['b30', { m: 'y', b: '30' }], ['b7', { m: 'y', b: '7' }]]) {
      run(CMP0 + `EC.cmp=${JSON.stringify(Object.assign({ m: 'y', b: '7', bm: '', cm: '' }, sel))}; EC.app=''; ecPaint();`);
      R[k] = Object.assign(rowsUnder(sel), { card: cards()[0], order: J(`ecSortRows(EC.rows.a.filter(r=>r.act),EC.sort).map(r=>r.key)`) }); }
    useFx('first');
    for (const [k, sel] of [['first_mon', { m: 'y', b: 'mon' }], ['first_mm', { m: 'm' }]]) {
      run(CMP0 + `EC.cmp=${JSON.stringify(Object.assign({ m: 'y', b: '7', bm: '', cm: '' }, sel))}; EC.app=''; ecPaint();`);
      R[k] = Object.assign(rowsUnder(sel), { card: cards()[0] }); }
    useFx('short');
    run(CMP0 + `EC.app=''; ecPaint();`); R.short = { ctl: run(`ecCmpCtl(EC.W,EC.C)`), title: run(`EC.C.title`) };
    unFx(); return R; });
  // a month-to-month status on noise only (SYNTHETIC: steady eCPM, ±8% random day to day, 15 months): the first days of a
  // month (Nov (1) … Nov (1–5), Nov (1–8)) vs the whole October — measured like the comparison, not whole month vs whole month
  await step('cmp_noise', () => { const R = {};
    for (const T of ['2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06', '2026-11-09', '2026-12-01']) {
      run(`(()=>{ const D=__FX.noise, L=new Date(Date.parse('${T}T00:00:00Z')-864e5).toISOString().slice(0,10);
        DATA=Object.assign({},D,{today_date:'${T}',latest_complete:L,placements:D.placements.map(p=>Object.assign({},p,{daily:p.daily.filter(r=>r[0]<='${T}')}))}); })();
        window.__ax=null; EC.cache=null; EC.ucache={};`);
      const r = rowsUnder({ m: 'm' }); Object.values(r.rows).forEach(x => { delete x.ye; delete x.wi; });
      R[T] = { title: r.title, dn: r.dn, rows: r.rows, swm: J(`ecCmpC(ecWin(),{m:'m'}).swm.map(o=>o.k)`), note: run(`ecStatusNote(ecCmpC(ecWin(),{m:'m'}))`) }; }
    unFx(); return R; });
  // Countries, day by day: a hole (a failed chunk) inside the pick, a hole in the last 7 days, a young app's report
  await step('cmp_holes', () => { const R = {};
    run(CMP0 + `EC.app='Demo Gallery'; ecPaint();`);
    const look = () => { const c = cards(); return { countries: (c[1] || '').split('<div id="ec-tb-c">')[0], ct: J(`({u:EC.Ct.u.title,c:EC.Ct.c.title})`),
      c: J(`EC.rows.c.map(r=>({key:r.key,y:r.y,w7:r.w7,imp:r.imp,yi:r.yi,nc:r.nc}))`) }; };
    run(`var __cd0=DATA.countries_daily['Demo Gallery']; DATA.countries_daily['Demo Gallery']=Object.fromEntries(Object.entries(__cd0).map(([c,rows])=>[c,rows.filter(r=>!(r[0]>='2026-02-01'&&r[0]<='2026-02-20'))]));`);
    run(`ecPaint()`); R.febDef = look();
    run(`ecCmpB('mon')`); R.febMon = look();
    run(`ecCmpM('m')`); R.febMm = look();
    run(`ecCmpM('y'); ecCmpB('14')`); R.feb14 = look();
    run(`DATA.countries_daily['Demo Gallery']=Object.fromEntries(Object.entries(__cd0).map(([c,rows])=>[c,rows.filter(r=>!(r[0]>='2026-03-03'&&r[0]<='2026-03-05'))]));`);
    run(`ecPaint()`); R.mar14 = look();
    run(`ecCmpB('7')`); R.marDef = look();
    run(`DATA.countries_daily['Demo Gallery']=__cd0; DATA.countries_daily['New Timer']={US:DATA.placements.find(p=>p.app==='New Timer').daily.map(r=>[r[0],Math.round(r[1]/2),Math.round(r[2]/2),0,0,0])};`);
    run(CMP0 + `EC.cmp={m:'y',b:'14',bm:'',cm:''}; EC.app='New Timer'; ecPaint();`); R.young14 = look();
    run(`delete DATA.countries_daily['New Timer'];`);
    R.ranges = J(`[ecRanges(['2026-02-01','2026-02-02','2026-02-03']),ecRanges(['2026-02-28','2026-03-01','2026-03-05']),ecRanges(['2026-01-01','2026-01-03','2026-01-05','2026-01-07','2026-01-09','2026-01-11']),ecRanges([])]`);
    unFx(); return R; });
  // 🔀 Month vs month's two pickers on SYNTHETIC October histories (today 21 Oct 2026): the default "Oct 2026 (1–20) vs Sep
  // 2026", then the compared month's ‹ alone → vs Aug → vs Jul (the current month stays October), tapped as on the page
  await step('cmp_pickers', () => { const R = {};
    for (const fx of ['octs', 'ramp']) { useFx(fx); const o = R[fx] = {};
      run(CMP0 + `EC.cmp={m:'m'}; EC.app=''; ecPaint();`);
      for (const k of ['sep', 'aug', 'jul']) {
        if (k !== 'sep') run(`ecCmpVs(-1)`);
        o[k] = Object.assign(J(`({title:EC.C.title,cm:EC.C.cm,pm:EC.C.pm,g:EC.C.g,dn:EC.C.dn,cur:EC.C.cur,base:EC.C.base,swm:EC.C.swm.map(x=>x.k),
            colCur:EC.C.colCur,colBase:EC.C.colBase,colImp:EC.C.colImp,cmp:EC.cmp,ls:localStorage.getItem('ecpmcmp'),ctl:ecCmpCtl(EC.W,EC.C),note:ecStatusNote(EC.C),
            rows:(()=>{ const A=ecAgg().apps, o={}; Object.keys(A).forEach(n=>{ const r=ecRow(A[n],EC.W,EC.C); delete r.spark; o[n]=r; }); return o; })()})`),
          { card: cards()[0], order: J(`ecSortRows(EC.rows.a.filter(r=>r.act),EC.sort).map(r=>r.key)`) }); }
      // to the oldest month and back to the default pair: the current month never moved
      run(`for(let i=0;i<40;i++) ecCmpVs(-1);`); o.oldest = J(`({title:EC.C.title,pm:EC.C.pm,ctl:ecCmpCtl(EC.W,EC.C)})`);
      run(`for(let i=0;i<40;i++) ecCmpVs(1);`); o.back = J(`({title:EC.C.title,cmp:EC.cmp})`); }
    unFx(); return R; });

  out.errors = errors;
  process.stdout.write(JSON.stringify(out));
})().catch(e => { errors.push('MAIN ' + (e.stack || e.message)); out.errors = errors; process.stdout.write(JSON.stringify(out)); });
