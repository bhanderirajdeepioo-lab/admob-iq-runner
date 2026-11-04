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
        dw: dateWiseRows(curWinArr()).reduce((t, r) => t + r.spend, 0), ov: renderOverview().innerHTML,
        fb: faultBannerText()})`));
    } catch (e) { errors.push(k + ' other: ' + (e.stack || e.message)); }
  }
}
run(`CURVIEW=null; APP='';`);
// the dashboard's Period windows (the owner's standard picker, 3 Nov 2026) on a SYNTHETIC 100-day axis, 1 Aug – 8 Nov 2026
// (8 Nov = the AdMob day of the build: partial) → [days, first, last] per range
let wd = null;
try {
  wd = JSON.parse(run(`(()=>{ const ax=[]; for(let i=0;i<100;i++) ax.push(new Date(Date.UTC(2026,7,1)+i*864e5).toISOString().slice(0,10));
    const keep=DATA; DATA={today_date:ax[99], latest_complete:ax[98]}; const o={};
    ['today','yesterday','7d','month','lastmonth','30d','60d','90d','all'].forEach(r=>{ const w=windowDates(ax,r,'',''); o[r]=[w.length,w[0],w[w.length-1]]; });
    o.labels=["60d","90d"].map(r=>pRangeLabel(r));
    // a daily chart's period (stdSpan) on the same dates, the chart's own last date 7 Nov (8 Nov not in the chart): first / last
    const cx=ax.slice(0,99), sp={}; ['today','yesterday','7d','month','lastmonth','30d','60d','90d','all'].forEach(r=>{ const q=stdSpan(cx,r,'',''); sp[r]=q?[cx[q[0]],cx[q[1]]]:null; });
    sp.custom=stdSpan(cx,'custom','2026-09-10','2026-09-01').map(i=>cx[i]); sp.year=stdSpan(cx,'1y','','',{'1y':365}).map(i=>cx[i]);
    o.span=sp;
    // the eCPM chart's points: Last month by day (31) and by month (1); 60 days by day (60); Today none (the day still runs)
    const dm={}; cx.forEach(d=>{ dm[d]=[1e6,1000]; }); const W={comp:cx,L:cx[98]};
    o.ec={lmDay:ecPts(dm,W,'','lastmonth','day').length, lmMon:ecPts(dm,W,'','lastmonth','month').map(p=>p.k), d60:ecPts(dm,W,'','60','day').length,
      today:ecPts(dm,W,'','today','day').length, all:ecPts(dm,W,'','all','day').length, mon:ecPts(dm,W,'','month','month').map(p=>p.k)};
    // the month mover (4 Nov 2026): its helpers, the dashboard Period's month windows, a chart's month, the eCPM chart's month
    const bt=(k,l,on,dis)=>k+'|'+l+'|'+(on?1:0)+'|'+(dis?1:0)+';';
    o.mon={add:[monAdd('2026-01',-1),monAdd('2026-12',1),monAdd('2026-11',-14)], last:[monLastDay('2026-02'),monLastDay('2028-02'),monLastDay('2026-10')],
      span:monSpan('mon:2026-11','2026-11-04'), past:monSpan('mon:2026-10','2026-11-04'), none:monSpan('7d','2026-11-04'),
      mvLast:monMover('7d','2026-11-08','2026-08-01',bt), mvPicked:monMover('mon:2026-08','2026-11-08','2026-08-01',bt),
      mvTm:monMover('month','2026-11-08','2026-08-01',bt), mvCap:monMover('mon:2026-10','2026-11-08','2026-08-01',bt,'2026-09'),
      win10:(w=>[w.length,w[0],w[w.length-1]])(windowDates(ax,'mon:2026-10','','')), win11:(w=>[w.length,w[0],w[w.length-1]])(windowDates(ax,'mon:2026-11','','')),
      chart:(q=>[cx[q[0]],cx[q[1]]])(stdSpan(cx,'mon:2026-09','','')), word:stdWord('mon:2026-09'), label:pRangeLabel('mon:2026-09'),
      ecDay:ecPts(dm,W,'','mon:2026-10','day').length, ecMon:ecPts(dm,W,'','mon:2026-10','month').map(p=>p.k)};
    DATA=keep; return JSON.stringify(o); })()`));
} catch (e) { errors.push('wd: ' + (e.stack || e.message)); }
process.stdout.write(JSON.stringify({ errors, out, other, wd }));
