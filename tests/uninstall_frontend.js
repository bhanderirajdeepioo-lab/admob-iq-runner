// The Uninstall tab's frontend contract: runs the REAL dashboard script (frontend/index.html's <script>) in a node
// vm with stub browser globals, feeds it the committed fixture (tests/fixtures/uninstall_sample.json — written by
// the real build code) and renders every Uninstall-tab state: the portfolio (every Period, every sort, phone
// width and desktop — the markup is the same, the layout is CSS), each app's detail in every chart / table
// mode, the collapsed and expanded tables, the "Har din" triangle pages and the App filter. Prints one JSON
// report; tests/test_uninstall_frontend.py asserts on it.   usage: node uninstall_frontend.js <script.js> <fixture.json>
const fs = require('fs'), vm = require('vm');
const [scriptPath, fixturePath] = process.argv.slice(2);
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const errors = [];
const ctx = {
  console: { log() {}, warn() {}, error: (...a) => errors.push(a.join(' ')) },
  window: any, document: any, localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  navigator: any, location: { href: '', search: '', hash: '', pathname: '/', reload() {} }, history: any,
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String,
  Set, Map, Float64Array, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent, performance: { now: () => 0 },
  getComputedStyle: () => any, innerWidth: 375, innerHeight: 812, scrollTo() {}, alert() {}, confirm: () => false,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const FX = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
ctx.__FX = FX;
run(`DATA = {apps_catalog: [], today_date: '2026-09-25', alerts: {counts: {}, items: []}, uninstall: __FX.dashboard_uninstall};
     UNI = __FX.asset; UNIERR = false; UNICOH = {};
     for (const [n, j] of Object.entries(__FX.cohort_files || {})) UNICOH[n.slice(12, -8)] = uniCohPrep(j);`);
const out = {};
function scen(name, code) { try { out[name] = String(run(code)); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 4).join(' < ')); } }
const RESET = `UNIAPP=''; APP=''; UNICSRC='all'; UNICRANGE='90'; UNITRI='cp'; UNITRIPAGE=0; UNITRIEXP=false; UNIOLDEXP=false; UNICLEXP=false; UNICPEXP=false; UNIDRANGE='90d'; UNIPRE=false;`;
for (const r of ['today', '7d', '30d', '90d', 'month', 'lastmonth', 'all', 'custom'])
  scen('portfolio_' + r, `${RESET} RANGE='${r}'; RCUSTOM={from:'2026-08-01',to:'2026-09-30'}; UNITRIEXP=${r === 'all'}; uniScreen()`);
for (const k of ['app', 'ins', 'outs', 'net', 'rate', 'S7', 'D0', 'D1', 'D7', 'D30', 'alert'])
  scen('sort_' + k, `${RESET} RANGE='30d'; UNISORT={k:'${k}',d:-1}; uniPortfolio()`);
const apps = FX.asset.apps;
for (const a of apps) {
  // an app's detail is open the way uniOpen leaves it: UNIAPP + the header's App (render / show are not run here)
  const id = JSON.stringify(a.app_id) + '; APP=' + JSON.stringify(a.app);
  for (const [src, cr, tri, cp, old, exp] of [['all', '30', 'cp', false, false, false], ['all', '90', 'all', true, true, false],
    ['recent', 'all', 'cp', true, false, true], ['recent', '30', 'all', false, true, true], ['all', 'all', 'cp', false, false, false]])
    scen(`detail|${a.app}|${src}|${cr}|${tri}|${cp}`, `${RESET} RANGE='30d'; UNIAPP=${id}; UNICSRC='${src}'; UNICRANGE='${cr}'; UNITRI='${tri}'; UNICPEXP=${cp}; UNIOLDEXP=${old}; UNICLEXP=${old}; UNITRIEXP=${exp}; uniScreen()`);
  scen(`tripages|${a.app}`, `${RESET} UNIAPP=${id}; UNITRI='all'; (()=>{ let s=''; for (let p=0;p<12;p++){ UNITRIPAGE=p; s+=uniScreen(); } return s; })()`);
  // the test installs before the launch shown ("dikhao"): every card, both triangle modes, all rows
  for (const tri of ['cp', 'all'])
    scen(`pre|${a.app}|${tri}`, `${RESET} RANGE='all'; UNIAPP=${id}; UNIPRE=true; UNITRI='${tri}'; UNITRIEXP=true; UNIOLDEXP=true; UNICLEXP=true; UNIDRANGE='all'; uniScreen()`);
  scen(`appfilter|${a.app}`, `${RESET} APP=${JSON.stringify(a.app)}; uniScreen()`);
}
for (const n of FX.asset.no_ga4) scen(`appfilter_noga4|${n.app}`, `${RESET} APP=${JSON.stringify(n.app)}; uniScreen()`);
scen('alert_cards', `${RESET} uniAlertCards(uniAlertsFor())`);
// the "worse" verdict (the fixture has only "better" and "jaisa"): one app's verdict turned around, then restored
scen('verdict_worse', `${RESET} (()=>{ const a=UNI.apps[0], sv=a.survival, keep=sv.verdict;
  sv.verdict=Object.assign({},keep,{fires:true,dir:'worse',recent:Object.assign({},keep.recent,{left:keep.prev.left-0.05})});
  try{ UNIAPP=a.app_id; APP=a.app; const d=uniScreen(); UNIAPP=''; APP=''; return d+'<hr>'+uniScreen(); } finally { sv.verdict=keep; } })()`);
// the headline gap is the difference of the two numbers SHOWN (9.5 vs 12 → 2.5, not 12 − 9 = 3)
scen('verdict_decimal', `${RESET} (()=>{ const a=UNI.apps[0], sv=a.survival, keep=sv.verdict;
  sv.verdict=Object.assign({},keep,{fires:true,dir:'worse',recent:Object.assign({},keep.recent,{left:0.0949}),prev:Object.assign({},keep.prev,{left:0.1177})});
  try{ return uniSumCard(a)+'<hr>'+uniSumPortfolio(UNI.apps); } finally { sv.verdict=keep; } })()`);
// a real change judged on day 3 (a younger app): no arrow in the table's "7 din baad bache" column
scen('verdict_day3', `${RESET} RANGE='30d'; (()=>{ const a=UNI.apps.find(x=>x.survival.verdict&&x.survival.verdict.fires), sv=a.survival, keep=sv.verdict;
  sv.verdict=Object.assign({},keep,{n:3});
  try{ return uniPortfolio(); } finally { sv.verdict=keep; } })()`);
// a tiny app (under 300 settled installs: its whole curve "kam data") still gets its sentence, marked
scen('tiny_app', `${RESET} (()=>{ const a=UNI.apps.find(x=>x.app==='Demo QR Scanner'), c=a.survival.all, keep=c.thin_from;
  c.thin_from=0; try{ return uniSumCard(a); } finally { c.thin_from=keep; } })()`);
// an old app with no verdict (data gaps, not age)
scen('no_verdict_old', `${RESET} (()=>{ const a=UNI.apps[0], sv=a.survival, keep=sv.verdict; sv.verdict=null;
  try{ return uniSumCard(a); } finally { sv.verdict=keep; } })()`);

// the header's App selector follows the open app (uniOpen → setApp), "← Saari apps" clears it (render/show stubbed)
let header = null;
try { header = JSON.parse(run(`(()=>{ const keep={render, show, _navSave}, calls=[];
  render=function(){ calls.push('render'); }; show=function(id){ calls.push('show'); }; _navSave=function(){};
  try{ ${RESET} const a=UNI.apps[0]; uniOpen(a.app_id);
    const r={name:a.app, id:a.app_id, app:APP, uniapp:UNIAPP, sel:appSelHtml(), calls:calls.slice(), screen:uniScreen()};
    uniBack(); r.after={app:APP, uniapp:UNIAPP, sel:appSelHtml(), screen:uniScreen().slice(0,400)}; return JSON.stringify(r); }
  finally{ render=keep.render; show=keep.show; _navSave=keep._navSave; ${RESET} } })()`)); } catch (e) { errors.push('header: ' + e.message); }

// the header can never say "All apps" over one app's detail: picking "All apps" (or another app, then "All apps") in the
// header closes the detail; a detail saved without its header App (an older page's navstate) shows the portfolio
let header2 = null;
try { header2 = JSON.parse(run(`(()=>{ const keep={render, show, _navSave}; render=function(){}; show=function(){}; _navSave=function(){};
  const top=s=>s.slice(0,160);
  try{ ${RESET} const A=UNI.apps[0], B=UNI.apps[1], r={};
    uniOpen(A.app_id); setApp(''); r.all={app:APP, uniapp:UNIAPP, sel:appSelHtml(), screen:top(uniScreen())};
    uniOpen(A.app_id); setApp(B.app); r.other={app:APP, uniapp:UNIAPP, screen:top(uniScreen())}; setApp('');
    r.back={app:APP, uniapp:UNIAPP, screen:top(uniScreen())};
    ${RESET} UNIAPP=A.app_id; r.stale={screen:top(uniScreen())}; r.B=B.app; return JSON.stringify(r); }
  finally{ render=keep.render; show=keep.show; _navSave=keep._navSave; ${RESET} } })()`)); } catch (e) { errors.push('header2: ' + e.message); }
// an app with no AdMob row (picked from the Uninstall tab): Overview says so — no "$0" tiles, no "undefined placements"
scen('overview_no_admob', `${RESET} (()=>{ const keep=screenDiv; screenDiv=id=>({dataset:{screen:id},innerHTML:''});
  try{ APP='Demo Wallpapers'; return renderOverview().innerHTML; } finally { screenDiv=keep; APP=''; } })()`);
// "Har din" pages: every page names the 4-week set; with the test installs hidden, no page only they reach
const wal = apps.find(x => x.launch.hidden);
scen('tripage1_caller', `${RESET} UNIAPP=${JSON.stringify(apps[0].app_id)}; APP=${JSON.stringify(apps[0].app)}; UNITRI='all'; UNITRIPAGE=1; uniScreen()`);
let pages = null;
try { pages = JSON.parse(run(`(()=>{ ${RESET} const a=UNI.apps.find(x=>x.app_id===${JSON.stringify(wal.app_id)}), C=UNICOH[a.key], f0=uniDiff(C.start,a.launch.day);
  UNIAPP=a.app_id; APP=a.app; UNITRI='all'; UNITRIPAGE=99; const h=uniScreen(), hid=UNITRIPAGE, cols=[...h.matchAll(new RegExp('<th style="text-align:center">([0-9]+) din</th>','g'))].map(m=>+m[1]);
  UNIPRE=true; UNITRIPAGE=99; uniScreen(); const all=UNIPRE?UNITRIPAGE:-1; ${RESET}
  return JSON.stringify({hid, all, want_hid:Math.floor((C.nE-f0)/31), want_all:Math.floor(C.nE/31), last_col:Math.max(...cols), reach:C.nE-f0}); })()`)); } catch (e) { errors.push('pages: ' + e.message); }
// a young app (launched 40 days back after hidden test installs) with no verdict yet: its age, not "data gayab"
scen('no_verdict_young_launch', `${RESET} (()=>{ const a=UNI.apps.find(x=>x.app_id===${JSON.stringify(wal.app_id)}), sv=a.survival, keep=[sv.verdict,a.launch.day];
  sv.verdict=null; a.launch.day=uniAdd(a.settled_till,-40); try{ return uniSumCard(a); } finally { sv.verdict=keep[0]; a.launch.day=keep[1]; } })()`);
// hidden installs of more than a trickle a day: only "shayad test"
scen('maybe_test', `${RESET} (()=>{ const a=UNI.apps.find(x=>x.app_id===${JSON.stringify(wal.app_id)}); a.launch.sure=false;
  try{ UNIAPP=a.app_id; APP=a.app; const h=uniScreen(); UNIPRE=true; UNITRI='all'; UNITRIEXP=true; return h+'<hr>'+uniScreen(); } finally { a.launch.sure=true; } })()`);

// app updates in the install-week table ("🔺 Install hafta × din"): every 📦 line sits right ABOVE the week its update(s)
// fell in (after that week's year row), names each of their dates, that week — and only it — carries the 📦 badge, and
// the legend comes only with the lines. Every app × both modes × test weeks hidden / shown × 12 / all rows, then the
// same app with made-up updates: two or more in one week, one in the newest (partial) week, one among the test
// installs, none. Each table is a scenario too (no errors / "undefined" / jargon)
const rel = { checked: 0, lines: 0, bad: [], tips: {}, pages: {} };
function relCheck(name, app, set, over) {
  let res;
  try {
    res = JSON.parse(run(`(()=>{ ${RESET} const a=UNI.apps.find(x=>x.app_id===${JSON.stringify(app.app_id)}), keep=a.releases; ${set}
      ${over ? `a.releases=${JSON.stringify(over)};` : ''}
      try{ const h=uniTriCard(a), L=uniLaunch(a); let rows=a.triangle.rows;
        if(UNITRI==='all'){ const C=UNICOH[a.key]; rows=uniTriAll(C,0,0,a.settled_till,null,L?uniDiff(C.start,L.day):0).rows; }
        rows=UNIPRE?rows.filter(r=>!r.pre||r.users>0):rows.filter(r=>!r.pre); if(!UNITRIEXP) rows=rows.slice(0,12);
        return JSON.stringify({h, pg:UNITRIPAGE, rows:rows.map(r=>[r.from,r.to]), rels:(a.releases||[]).map(x=>[x.date,uniD(x.date)])}); }
      finally{ a.releases=keep; ${RESET} } })()`));
  } catch (e) { errors.push('rel ' + name + ': ' + e.message); return; }
  const trs = ((res.h.split('<tbody>')[1] || '').split('</tbody>')[0]).split('<tr').slice(1);
  let wi = 0, pend = null, badges = 0;
  for (const tr of trs.slice(2)) {                                   // after the All-time normal and 4-week rows
    if (tr.startsWith(' class="uni-yr"')) { if (pend) rel.bad.push(name + ': a year row under a 📦 line'); continue; }
    if (tr.startsWith(' class="uni-rel"')) { if (pend) rel.bad.push(name + ': two 📦 lines'); pend = tr; rel.lines++; continue; }
    const [f, t] = res.rows[wi++] || [], want = res.rels.filter(([d]) => d >= f && d <= t), badge = tr.includes('class="uni-relb"');
    if (badge) badges++;
    if (!!want.length !== !!pend || !!want.length !== badge) rel.bad.push(`${name}: ${f}–${t} line ${!!pend} badge ${badge} updates ${want.length}`);
    for (const [, d] of pend ? want : []) if (!pend.includes('(' + d + ')') && !pend.includes('— ' + d + ' (')) rel.bad.push(`${name}: ${d} not on its line`);
    pend = null; rel.checked++;
  }
  const lines = trs.filter(x => x.startsWith(' class="uni-rel"')).length;
  if (pend || wi !== res.rows.length) rel.bad.push(`${name}: weeks ${wi}/${res.rows.length}`);
  if (lines !== badges || res.h.includes('📦 = naya update.') !== lines > 0) rel.bad.push(name + ': legend / badges');
  out['rel|' + name] = res.h;
  rel.tips[name] = [...res.h.matchAll(/class="uni-relb" title="([^"]*)"/g)].map(m => m[1]);
  rel.pages[name] = res.pg;
}
for (const a of apps) for (const tri of ['cp', 'all']) for (const pre of [false, true]) for (const exp of [false, true])
  relCheck(`${a.app}|${tri}|${pre}|${exp}`, a, `UNITRI='${tri}'; UNIPRE=${pre}; UNITRIEXP=${exp};`);
for (const tri of ['cp', 'all']) {
  relCheck('two|' + tri, apps[0], `UNITRI='${tri}';`, [{ date: '2026-09-08', version: '3.2', kind: 'version' },
    { date: '2026-09-11', version: null, kind: 'update' }, { date: '2026-09-12', version: 'v3.2.1', kind: 'version' }]);
  relCheck('newest|' + tri, apps[0], `UNITRI='${tri}';`, [{ date: '2026-09-22', version: '3.3', kind: 'version' }]);
  relCheck('none|' + tri, apps[0], `UNITRI='${tri}';`, []);
  for (const pre of [false, true])
    relCheck(`test|${tri}|${pre}`, wal, `UNITRI='${tri}'; UNIPRE=${pre}; UNITRIEXP=true;`, [{ date: '2025-12-24', version: '1.1', kind: 'version' }]);
  // the launch cuts a week in two: one on the launch day goes above the first launched week; one on the last day of
  // the newest test week that has installs, above that week — only while the test installs are shown
  for (const pre of [false, true])
    relCheck(`launch|${tri}|${pre}`, wal, `UNITRI='${tri}'; UNIPRE=${pre}; UNITRIEXP=true;`, [{ date: wal.launch.day, version: '1.0', kind: 'version' },
      { date: wal.triangle.rows.find(r => r.pre && r.users > 0).to, version: '0.9', kind: 'version' }]);
}
// "Har din" pages are columns (days after install), not weeks: page 2 has the same weeks, so the same 📦 lines
for (const a of apps) for (const pre of [false, true])
  relCheck(`${a.app}|all|${pre}|page2`, a, `UNITRI='all'; UNITRIPAGE=1; UNIPRE=${pre}; UNITRIEXP=true;`);

// ── what the page says ──
const text = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ');
const uiText = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/\sid="[^"]*"/g, '');   // markup + titles + chart labels, minus code
const bad = [], jargon = [], devanagari = [];
const JARGON = /cumulative|checkpoint|cohort|bharosa|headline/i, DEVA = /[\u0900-\u097F]/;
for (const [k, v] of Object.entries(out)) {
  for (const w of ['undefined', 'NaN', '[object Object]', 'Infinity']) if (v.includes(w)) bad.push(k + ': ' + w);
  if (k !== 'alert_cards') { const m = uiText(v).match(JARGON); if (m) jargon.push(k + ': ' + m[0] + ' …' + uiText(v).slice(Math.max(0, m.index - 80), m.index + 30)); }
  if (DEVA.test(v)) devanagari.push(k);
}
// every "kitne bache" chart: the line never rises and stays within 0..100% (data-pts y grows downwards)
const charts = [];
for (const [k, v] of Object.entries(out)) {
  if (!k.startsWith('detail|')) continue;
  const i = v.indexOf('id="uni-curve"'); if (i < 0) continue;
  const m = v.slice(i).match(/data-pts='([^']*)'/); if (!m) continue;
  const pts = JSON.parse(m[1].replace(/&#39;/g, "'").replace(/&amp;/g, '&'));
  const ys = pts.map(p => p.y), bache = pts.map(p => parseFloat(p.v));
  charts.push({ k, n: pts.length, first: pts[0].v, never_rises: ys.every((y, j) => j === 0 || y >= ys[j - 1] - 1e-9),
                within: bache.every(b => b >= 0 && b <= 100), hover_both: pts.slice(1).every(p => / bache/.test(p.v) && /^us din .* gaye$/.test(p.s)) });
}
// the "Har din" triangle's 4-week row (worked out in the page from the raw cells) = the engine's, day for day
let avg4Checked = 0; const avg4Bad = [];
try { run(`UNI.apps.map(a=>{ const C=UNICOH[a.key], T=a.triangle; if(!C) return [a.app,-1,[]]; const L=uniLaunch(a), r=uniTriAll(C,0,C.nE,a.settled_till,null,L?uniDiff(C.start,L.day):0), bad=[];
    T.cols.forEach((N,j)=>{ const e=T.avg4[j], g=r.avg4[N]; if((e==null)!==(g==null)||(e&&(Math.abs(e.p-g.p)>1e-5||e.users!==g.users||e.from!==g.from||e.to!==g.to||e.prov!==g.prov))) bad.push(N); });
    const got=r.avg4.filter(Boolean); for(let k=1;k<got.length;k++){ if(got[k].p<got[k-1].p-1e-12) bad.push('down@'+k); if(got[k].from!==got[0].from||got[k].users!==got[0].users) bad.push('set@'+k); }
    const pre=r.rows.filter(x=>x.pre), T2=T.rows.filter(x=>x.pre); if(pre.length!==T2.length||pre.some((x,k)=>x.from!==T2[k].from||x.to!==T2[k].to||x.users!==T2[k].users)) bad.push('pre-rows');
    return [a.app,T.cols.length,bad]; })`).forEach(([app, n, b]) => { if (n < 0) avg4Bad.push(app + ': no cells'); else { avg4Checked += n; if (b.length) avg4Bad.push(app + ': ' + b.join(',')); } });
} catch (e) { errors.push('avg4: ' + e.message); }
const T = k => text(out[k] || '');
// the "Har din" triangle's All-time normal row = the engine's (1 − the app's survival curve), day for day
let refChecked = 0; const refBad = [];
try { run(`UNI.apps.map(a=>{ const C=UNICOH[a.key], T=a.triangle; if(!C) return [a.app,-1,[]]; const r=uniTriAll(C,0,C.nE,a.settled_till,a.survival.all.left), bad=[];
    T.cols.forEach((N,j)=>{ const e=T.ref[j], g=r.ref[N]; if((e==null)!==(g==null)||(e!=null&&Math.abs(e-g)>1e-5)) bad.push(N); });
    for(let N=1;N<r.ref.length;N++) if(r.ref[N]!=null&&r.ref[N-1]!=null&&r.ref[N]<r.ref[N-1]-1e-9) bad.push('down@'+N);
    return [a.app,T.cols.length,bad]; })`).forEach(([app, n, b]) => { if (n < 0) refBad.push(app + ': no cells'); else { refChecked += n; if (b.length) refBad.push(app + ': ' + b.join(',')); } });
} catch (e) { errors.push('ref: ' + e.message); }
// every app: its rate line never shows a state word ("normal", "normal se kam/zyada") next to an open rate alert
const rateLines = run(`UNI.apps.map(a=>[a.app, uniRateLine(a)])`);
const rateBad = rateLines.filter(([, l]) => /⚠️|🟡|🟢/.test(l) && /<b[^>]*>normal/.test(l)).map(([a]) => a);
// every app with an open install (cohort) alert: its summary never shows a plain "✅ Pichhle mahine jaisa" and says
// the alert's installs right there
const cohBad = [];
for (const a of apps) {
  const cs = (a.alerts || []).filter(x => x.family === 'cohort'); if (!cs.length) continue;
  const t = text(run(`uniSumCard(UNI.apps.find(x=>x.app_id===${JSON.stringify(a.app_id)}))`));
  if (t.includes('✅ Pichhle mahine jaisa')) cohBad.push(a.app + ': plain jaisa');
  for (const x of cs) if (!t.includes(run(`uniSpan(${JSON.stringify(x.installs_from)},${JSON.stringify(x.installs_to)})`) + ' ke installs ' + (x.dir === 'up' ? 'zyada' : 'kam') + ' hata rahe')) cohBad.push(a.app + ': no alert line');
}
// every verdict headline's number = the difference of the two numbers its sub-line shows
const gapBad = [];
for (const a of apps) {
  const t = text(run(`uniSumCard(UNI.apps.find(x=>x.app_id===${JSON.stringify(a.app_id)}))`));
  const h = t.match(/Pichhle mahine se ([\d.]+) (kam|zyada) bache/), sb = t.match(/: (?:usi din|\d+ din baad) ([\d.]+) bache · usse pehle ke 4 hafte \([^)]*\): ([\d.]+)/);
  if (h && (!sb || Math.abs(Math.abs(parseFloat(sb[1]) - parseFloat(sb[2])) - parseFloat(h[1])) > 1e-9)) gapBad.push(a.app);
}
// the curve's value labels (phone, the default 90 din and 30 din): the latest key day shown and day 7 always get one
const labelBad = [];
for (const m of ['30', '90']) for (const a of apps) {
  const h = run(`UNICRANGE='${m}'; UNICSRC='all'; uniCurveCard(UNI.apps.find(x=>x.app_id===${JSON.stringify(a.app_id)}))`);
  const got = [...h.matchAll(/data-day="(\d+)"/g)].map(x => +x[1]), top = Math.min(a.survival.all.left.length - 1, +m);
  const want = a.survival.key_days.filter(N => N <= top), need = [Math.max(...want)].concat(want.includes(7) ? [7] : []);
  for (const N of need) if (!got.includes(N)) labelBad.push(`${a.app} ${m}: ${N}`);
}
// on a phone the curve's tooltip is drawn 1.5× (readable once the chart is scaled down to the screen)
const tipBig = apps.every(a => { const h = run(`UNICRANGE='90'; uniCurveCard(UNI.apps.find(x=>x.app_id===${JSON.stringify(a.app_id)}))`);
  return /data-ts="1.5"/.test(h) && /class="bctd" font-size="16.5"/.test(h) && /class="bctr" font-size="20.25"/.test(h); });
// the honest totals line: every install since the launch, and the install DAYS the "bache" numbers come from; the curve
// card's "Hamesha" starts at the same first install day
const spanBad = [], totals = {};
for (const a of apps) {
  const t = T(`detail|${a.app}|all|30|cp|false`), tot = (t.match(/((?:Launch|GA4 data shuru) \([^)]*\) se ab tak .*?)(?= 🧪| ✅| ⚠️| 🟢| ℹ️)/) || [])[1];
  totals[a.app] = { line: tot || null, installs: run(`fmtN(${a.launch.installs})`), day: run(`uniD(${JSON.stringify(a.launch.day)})`) };
  const s2 = (t.match(/Hamesha = (.+?) ke saare pakke installs/) || [])[1], want = run(`uniSpan(${JSON.stringify(a.survival.all.from)},${JSON.stringify(a.settled_till)})`);
  if (!s2 || s2.trim() !== want) spanBad.push(a.app + ': ' + s2 + ' | ' + want);
}
const has = (k, s) => (out[k] || '').includes(s) || T(k).includes(s);
const summary = {};
for (const a of apps) summary[a.app] = (T(`detail|${a.app}|all|30|cp|false`).match(/100 naye users me se:[^📊]*?(?=(✅|⚠️|🟢|ℹ️))/) || [''])[0].trim();
console.log(JSON.stringify({
  scenarios: Object.keys(out).length, errors, bad, jargon: jargon.slice(0, 20), devanagari,
  charts: { count: charts.length, all_never_rise: charts.every(c => c.never_rises), all_within: charts.every(c => c.within),
            all_hover_both: charts.every(c => c.hover_both), all_start_100: charts.every(c => c.first === '100% bache') },
  summary, avg4: { checked: avg4Checked, bad: avg4Bad }, ref: { checked: refChecked, bad: refBad },
  rate_bad: rateBad, coh_bad: cohBad, gap_bad: gapBad, label_bad: labelBad, tip_big: tipBig, span_bad: spanBad,
  totals, header, header2, pages, texts: Object.fromEntries(Object.entries(out).filter(([k]) => /^(pre\||detail\|[^|]*\|all\|90\|all\|true|portfolio_30d|detail\|[^|]*\|all\|30\|cp\|false|overview_no_admob|tripage1_caller|no_verdict_young_launch|maybe_test|rel\|(two|newest|none|test)\||rel\|[^|]*\|(cp|all)\|false\|false$)/.test(k)).map(([k, v]) => [k, T(k)])),
  rel,
  plain_kya_badla: T('portfolio_30d').match(/Kya badla\? \((\d+)\)/)[1],
  portfolio_lines: (T('portfolio_30d').match(/Ek nazar me(.*?)📊 Roz ka uninstall rate/) || ['', ''])[1],
  portfolio: T('portfolio_30d'),
  pooled: (T('portfolio_30d').match(/100 naye users me se \(saari apps milakar\):[^📊✅⚠️🟢ℹ️]*?(?= saari apps)/) || [''])[0].trim(),
  has: {
    curve_title: apps.every(a => has(`detail|${a.app}|all|30|cp|false`, '100 me se kitne bache — install ke baad har din')),
    modes: ['Pehle 30 din', 'Pehle 90 din', 'Poori umar'].every(s => has(`detail|${apps[0].app}|all|30|cp|false`, s)),
    toggle: has(`detail|${apps[0].app}|all|30|cp|false`, 'Abhi ke installs (90 din)') && has(`detail|${apps[0].app}|all|30|cp|false`, 'Hamesha (saare installs)'),
    no_toggle_young: !has('detail|Demo Notes|all|30|cp|false', 'Abhi ke installs (90 din)'),
    kya_badla: apps.every(a => has(`detail|${a.app}|all|30|cp|false`, 'Kya badla?')),
    sab_normal: has('detail|Demo Notes|all|30|cp|false', '✅ Sab normal — koi badlaav nahi'),
    table_link: has(`detail|${apps[0].app}|all|30|cp|false`, 'Poori table dikhao') && !has(`detail|${apps[0].app}|all|30|cp|false`, 'Poori table — naye installs vs pehle'),
    table_open: has(`detail|${apps[0].app}|all|90|all|true`, 'Poori table — naye installs vs pehle'),
    avg4_row: has(`detail|${apps[0].app}|all|30|cp|false`, '4 hafte ka average') && has(`detail|${apps[0].app}|all|90|all|true`, '4 hafte ka average')
      && !Object.values(out).some(v => /Pichhle 4 hafte ka average|Sabse naye 4 pakke hafte/.test(v)),
    box_line: has(`detail|${apps[0].app}|all|30|cp|false`, 'Har box = us hafte install karne walon me se us din tak kitne % ne app hata diya'),
    mix_note_all: has('portfolio_30d', 'All apps me har hafte apps ka mix badalta hai — sahi tulna ke liye upar se ek app chuno'),
    no_pooled_triangle: !Object.entries(out).some(([k, v]) => k.startsWith('portfolio') && v.includes('uni-tri-all')),
    avg4_says_weeks: has(`detail|${apps[0].app}|all|30|cp|false`, ' ke installs — har column me yahi installs; · = abhi itne din nahi hue') && !Object.values(out).some(v => v.includes('bade din ke liye purane installs')),
    header_gaye: has('portfolio_30d', '"7 din baad bache" sirf pakke installs se; "… gaye" sabse naye 7 install-din se'),
    decimal_gap: T('verdict_decimal').includes('⚠️ Pichhle mahine se 2.5 kam bache (7 din baad)') && T('verdict_decimal').includes('7 din baad 9.5 bache · usse pehle ke 4 hafte')
      && /\(−2\.5\)/.test(T('verdict_decimal')),
    s7_arrow_day7_only: !/▲ \d/.test((out.verdict_day3 || '').split('id="uni-table"')[1] || 'x▲ 1') && /▲ 12→16/.test(T('portfolio_30d')),
    s7_no_mixed_arrow: !/\d%\s*▲\d/.test(T('portfolio_30d')),
    tiny_says_it: /100 naye users me se: 1 din baad \S+ bache/.test(T('tiny_app')) && T('tiny_app').includes('kam data — sirf') && !T('tiny_app').includes('~2 hafte ke pakke data ke baad'),
    old_no_verdict: T('no_verdict_old').includes('kai din ka GA4 data adhoora/gayab') && !T('no_verdict_old').includes('~2 mahine ke data ke baad'),
    unsure_not_jaisa: T('detail|Demo QR Scanner|all|30|cp|false').includes('abhi pakka nahi') && !T('detail|Demo QR Scanner|all|30|cp|false').includes('✅ Pichhle mahine jaisa'),
    plain_words: !Object.values(out).some(v => /hamesha ka median|\(adhura\)|\b20\d\d-W\d\d\b/.test(text(v))),
    naye_installs_sub: !Object.values(out).some(v => /Naye installs \(\d/.test(text(v))),
    mix_note_not_in_app: !has(`detail|${apps[0].app}|all|30|cp|false`, 'apps ka mix badalta hai'),
    s7_col: has('portfolio_30d', '7 din baad bache'),
    pooled: has('portfolio_30d', '100 naye users me se (saari apps milakar):'),
    kaccha_tag: has('portfolio_30d', '>kaccha</span>'),
    old_title_gone: !Object.values(out).some(v => v.includes('Har checkpoint') || v.includes('(cumulative)')),
    worse_app: T('verdict_worse').includes('⚠️ Pichhle mahine se 5 kam bache (7 din baad)'),
    events_note: has('detail|Demo Caller – Test App|all|30|cp|false', 'ℹ️ 85 purane din ka data uninstall ginti (events) se andaza')
      && !apps.some(a => a.app !== 'Demo Caller – Test App' && has(`detail|${a.app}|all|30|cp|false`, '(events) se andaza')),
    adhoora_kept: has('detail|Demo Launcher|all|30|cp|false', '1 din ka data adhoora'),
    worse_portfolio: /⚠️ 1 app me pichhle mahine se kam bache \(7 din baad\): \S.* \(−5\)/.test(T('verdict_worse')),
  },
}, null, 1));
