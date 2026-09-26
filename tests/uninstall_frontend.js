// The Uninstall tab's frontend contract: runs the REAL dashboard script (frontend/index.html's <script>) in a node
// vm with stub browser globals, feeds it the committed fixture (tests/fixtures/uninstall_sample.json — written by
// the real build code) and renders every Uninstall-tab state: the portfolio (every Period, every sort, phone
// width and desktop — the markup is the same, the layout is CSS), each app's detail in every chart / table
// mode, the collapsed and expanded tables, the "Har din" triangle pages and the App filter. Prints one JSON
// report; tests/test_uninstall_frontend.py asserts on it. The All apps "At a glance" chips are opened one by one (each
// must list exactly its apps).   usage: node uninstall_frontend.js <script.js> <fixture.json>
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
const RESET = `UNIAPP=''; APP=''; UNICSRC='all'; UNICRANGE='90'; UNITRI='cp'; UNITRIPAGE=0; UNITRIEXP=false; UNIOLDEXP=false; UNICLEXP=false; UNICPEXP=false; UNIDRANGE='90d'; UNIPRE=false; UNISTEXP=''; UNITIMEXP=false;`;
for (const r of ['today', '7d', '30d', '90d', 'month', 'lastmonth', 'all', 'custom'])
  scen('portfolio_' + r, `${RESET} RANGE='${r}'; RCUSTOM={from:'2026-08-01',to:'2026-09-30'}; UNITRIEXP=${r === 'all'}; uniScreen()`);
for (const k of ['app', 'ins', 'outs', 'net', 'rate', 'S7', 'D0', 'D1', 'D7', 'D30', 'alert'])
  scen('sort_' + k, `${RESET} RANGE='30d'; UNISORT={k:'${k}',d:-1}; uniPortfolio()`);
// the All apps "At a glance" chips: every one opened (its app list shows), at phone width and desktop alike
const XP_KEYS = ['worse', 'wk_up', 'better', 'wk_dn', 'same', 'unsure', 'none', 'r_up', 'r_zero', 'r_dn', 'r_ok', 'r_none'];
for (const k of XP_KEYS) scen('xp|' + k, `${RESET} RANGE='30d'; UNISTEXP='${k}'; uniScreen()`);
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
// "⏱️ When will I know?" opened (a tap) — on the portfolio and on an app
scen('timing_open', `${RESET} RANGE='30d'; UNITIMEXP=true; uniScreen()+'<hr>'+(()=>{ UNIAPP=UNI.apps[0].app_id; APP=UNI.apps[0].app; return uniScreen(); })()`);
// the "worse" verdict (the fixture has only "better" and "jaisa"): one app's verdict turned around, then restored
scen('verdict_worse', `${RESET} (()=>{ const a=UNI.apps[0], sv=a.survival, keep=sv.verdict;
  sv.verdict=Object.assign({},keep,{fires:true,dir:'worse',recent:Object.assign({},keep.recent,{left:keep.prev.left-0.05})});
  try{ UNIAPP=a.app_id; APP=a.app; const d=uniScreen(); UNIAPP=''; APP=''; const p=uniScreen(); UNISTEXP='worse'; return d+'<hr>'+p+'<hr>'+uniScreen(); } finally { sv.verdict=keep; UNISTEXP=''; } })()`);
// the headline gap is the difference of the two numbers SHOWN (9.5 vs 12 → 2.5, not 12 − 9 = 3)
scen('verdict_decimal', `${RESET} (()=>{ const a=UNI.apps[0], sv=a.survival, keep=sv.verdict;
  sv.verdict=Object.assign({},keep,{fires:true,dir:'worse',recent:Object.assign({},keep.recent,{left:0.0949}),prev:Object.assign({},keep.prev,{left:0.1177})});
  try{ UNISTEXP='worse'; return uniSumCard(a)+'<hr>'+uniSumPortfolio(UNI.apps); } finally { sv.verdict=keep; UNISTEXP=''; } })()`);
// a real change judged on day 3 (a younger app): no arrow in the table's "7 din baad bache" column
scen('verdict_day3', `${RESET} RANGE='30d'; (()=>{ const a=UNI.apps.find(x=>x.survival.verdict&&x.survival.verdict.fires), sv=a.survival, keep=sv.verdict;
  sv.verdict=Object.assign({},keep,{n:3});
  try{ return uniPortfolio(); } finally { sv.verdict=keep; } })()`);
// a tiny app (under 300 settled installs: its whole curve "low data") still gets its tiles, marked
scen('tiny_app', `${RESET} (()=>{ const a=UNI.apps.find(x=>x.app==='Demo QR Scanner'), c=a.survival.all, keep=c.thin_from;
  c.thin_from=0; try{ return uniSumCard(a); } finally { c.thin_from=keep; } })()`);
// an old app with no verdict (data gaps, not age)
scen('no_verdict_old', `${RESET} (()=>{ const a=UNI.apps[0], sv=a.survival, keep=sv.verdict; sv.verdict=null;
  try{ return uniSumCard(a); } finally { sv.verdict=keep; } })()`);

// the header's App selector follows the open app (uniOpen → setApp), "← All apps" clears it (render/show stubbed)
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
  UNIAPP=a.app_id; APP=a.app; UNITRI='all'; UNITRIPAGE=99; const h=uniScreen(), hid=UNITRIPAGE, cols=[...h.matchAll(new RegExp('<th style="text-align:center">([0-9]+) days?</th>','g'))].map(m=>+m[1]);
  UNIPRE=true; UNITRIPAGE=99; uniScreen(); const all=UNIPRE?UNITRIPAGE:-1; ${RESET}
  return JSON.stringify({hid, all, want_hid:Math.floor((C.nE-f0)/31), want_all:Math.floor(C.nE/31), last_col:Math.max(...cols), reach:C.nE-f0}); })()`)); } catch (e) { errors.push('pages: ' + e.message); }
// a young app (launched 40 days back after hidden test installs) with no verdict yet: its age, not "data missing"
scen('no_verdict_young_launch', `${RESET} (()=>{ const a=UNI.apps.find(x=>x.app_id===${JSON.stringify(wal.app_id)}), sv=a.survival, keep=[sv.verdict,a.launch.day];
  sv.verdict=null; a.launch.day=uniAdd(a.settled_till,-40); try{ return uniSumCard(a); } finally { sv.verdict=keep[0]; a.launch.day=keep[1]; } })()`);
// hidden installs of more than a trickle a day: only "maybe test"
scen('maybe_test', `${RESET} (()=>{ const a=UNI.apps.find(x=>x.app_id===${JSON.stringify(wal.app_id)}); a.launch.sure=false;
  try{ UNIAPP=a.app_id; APP=a.app; const h=uniScreen(); UNIPRE=true; UNITRI='all'; UNITRIEXP=true; return h+'<hr>'+uniScreen(); } finally { a.launch.sure=true; } })()`);

// app updates in the install-week table ("🔺 Install week × day"): every 📦 line sits right ABOVE the week its update(s)
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
  if (lines !== badges || res.h.includes('📦 = new update.') !== lines > 0) rel.bad.push(name + ': legend / badges');
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
// "Every day" pages are columns (days after install), not weeks: page 2 has the same weeks, so the same 📦 lines
for (const a of apps) for (const pre of [false, true])
  relCheck(`${a.app}|all|${pre}|page2`, a, `UNITRI='all'; UNITRIPAGE=1; UNIPRE=${pre}; UNITRIEXP=true;`);

// ── what the page says ──
const text = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ');
const uiText = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/\sid="[^"]*"/g, '');   // markup + titles + chart labels, minus code
const bad = [], jargon = [], devanagari = [];
const JARGON = /cumulative|checkpoint|cohort|bharosa|headline/i, DEVA = /[ऀ-ॿ]/;
for (const [k, v] of Object.entries(out)) {
  for (const w of ['undefined', 'NaN', '[object Object]', 'Infinity']) if (v.includes(w)) bad.push(k + ': ' + w);
  if (k !== 'alert_cards') { const m = uiText(v).match(JARGON); if (m) jargon.push(k + ': ' + m[0] + ' …' + uiText(v).slice(Math.max(0, m.index - 80), m.index + 30)); }
  if (DEVA.test(v)) devanagari.push(k);
}
// every "How many stay" chart: the line never rises and stays within 0..100% (data-pts y grows downwards)
const charts = [];
for (const [k, v] of Object.entries(out)) {
  if (!k.startsWith('detail|')) continue;
  const i = v.indexOf('id="uni-curve"'); if (i < 0) continue;
  const m = v.slice(i).match(/data-pts='([^']*)'/); if (!m) continue;
  const pts = JSON.parse(m[1].replace(/&#39;/g, "'").replace(/&amp;/g, '&'));
  const ys = pts.map(p => p.y), stay = pts.map(p => parseFloat(p.v));
  charts.push({ k, n: pts.length, first: pts[0].v, never_rises: ys.every((y, j) => j === 0 || y >= ys[j - 1] - 1e-9),
                within: stay.every(b => b >= 0 && b <= 100), hover_both: pts.slice(1).every(p => /% stay( \(|$)/.test(p.v) && /^\S+ gone that day$/.test(p.s)) });
}
// the "Every day" triangle's 4-week row (worked out in the page from the raw cells) = the engine's, day for day
let avg4Checked = 0; const avg4Bad = [];
try { run(`UNI.apps.map(a=>{ const C=UNICOH[a.key], T=a.triangle; if(!C) return [a.app,-1,[]]; const L=uniLaunch(a), r=uniTriAll(C,0,C.nE,a.settled_till,null,L?uniDiff(C.start,L.day):0), bad=[];
    T.cols.forEach((N,j)=>{ const e=T.avg4[j], g=r.avg4[N]; if((e==null)!==(g==null)||(e&&(Math.abs(e.p-g.p)>1e-5||e.users!==g.users||e.from!==g.from||e.to!==g.to||e.prov!==g.prov))) bad.push(N); });
    const got=r.avg4.filter(Boolean); for(let k=1;k<got.length;k++){ if(got[k].p<got[k-1].p-1e-12) bad.push('down@'+k); if(got[k].from!==got[0].from||got[k].users!==got[0].users) bad.push('set@'+k); }
    const pre=r.rows.filter(x=>x.pre), T2=T.rows.filter(x=>x.pre); if(pre.length!==T2.length||pre.some((x,k)=>x.from!==T2[k].from||x.to!==T2[k].to||x.users!==T2[k].users)) bad.push('pre-rows');
    return [a.app,T.cols.length,bad]; })`).forEach(([app, n, b]) => { if (n < 0) avg4Bad.push(app + ': no cells'); else { avg4Checked += n; if (b.length) avg4Bad.push(app + ': ' + b.join(',')); } });
} catch (e) { errors.push('avg4: ' + e.message); }
const T = k => text(out[k] || '');
// the "Every day" triangle's All-time normal row = the engine's (1 − the app's survival curve), day for day
let refChecked = 0; const refBad = [];
try { run(`UNI.apps.map(a=>{ const C=UNICOH[a.key], T=a.triangle; if(!C) return [a.app,-1,[]]; const r=uniTriAll(C,0,C.nE,a.settled_till,a.survival.all.left), bad=[];
    T.cols.forEach((N,j)=>{ const e=T.ref[j], g=r.ref[N]; if((e==null)!==(g==null)||(e!=null&&Math.abs(e-g)>1e-5)) bad.push(N); });
    for(let N=1;N<r.ref.length;N++) if(r.ref[N]!=null&&r.ref[N-1]!=null&&r.ref[N]<r.ref[N-1]-1e-9) bad.push('down@'+N);
    return [a.app,T.cols.length,bad]; })`).forEach(([app, n, b]) => { if (n < 0) refBad.push(app + ': no cells'); else { refChecked += n; if (b.length) refBad.push(app + ': ' + b.join(',')); } });
} catch (e) { errors.push('ref: ' + e.message); }
// every app's "Daily uninstall rate" tile: never a state chip (Normal / High / Low) next to an open rate alert's chip,
// and exactly one state chip when no rate alert is open (and a normal range exists)
const rateTiles = run(`UNI.apps.map(a=>{ const S=uniRateState(a); return [a.app, uniRateTile(a), S.has&&S.band]; })`);
const rateBad = rateTiles.filter(([, h, band]) => { const al = h.includes('data-ra="1"'), st = (h.match(/data-rs="/g) || []).length;
  return al ? st > 0 : (band ? st !== 1 : st > 0); }).map(([a]) => a);
const rateStates = Object.fromEntries(rateTiles.map(([a, h]) => [a, { state: (h.match(/data-rs="([^"]+)"/) || [])[1] || null,
  alerts: [...h.matchAll(/data-ra="1">([^<]*)</g)].map(m => m[1]) }]));
// every app with an open install (cohort) alert: its verdict chip is never a plain "✅ Same as last month" (it names its
// own installs) and the alert's own chip ("Some install weeks worse · 17–23 Sep") is right there
const cohBad = [];
for (const a of apps) {
  const cs = (a.alerts || []).filter(x => x.family === 'cohort'); if (!cs.length) continue;
  const t = text(run(`uniSumCard(UNI.apps.find(x=>x.app_id===${JSON.stringify(a.app_id)}))`));
  if (/✅ Same as last month(?! · installs)/.test(t)) cohBad.push(a.app + ': plain same');
  for (const x of cs) if (!t.includes((x.dir === 'up' ? '⚠️ Some install weeks worse · ' : '🟢 Some install weeks better · ') + run(`uniSpan(${JSON.stringify(x.installs_from)},${JSON.stringify(x.installs_to)})`))) cohBad.push(a.app + ': no alert chip');
}
// every verdict chip's number = the difference of the two numbers its comparison line shows
const gapBad = [];
for (const a of apps) {
  const t = text(run(`uniSumCard(UNI.apps.find(x=>x.app_id===${JSON.stringify(a.app_id)}))`));
  const h = t.match(/(?:Worse|Better|Maybe worse|Maybe better) than last month [−+]([\d.]+)/), sb = t.match(/After (?:install day|\d+ days?): ([\d.]+) of 100 stay in the last 4 settled weeks \([^)]*\) vs ([\d.]+) in the 4 weeks before/);
  if (h && (!sb || Math.abs(Math.abs(parseFloat(sb[1]) - parseFloat(sb[2])) - parseFloat(h[1])) > 1e-9)) gapBad.push(a.app);
}
// the curve's value labels (phone, the default 90 days and 30 days): the latest key day shown and day 7 always get one
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
// the honest totals meta: every install since the launch, and the install DAYS the "Stay" numbers come from; the curve
// card's "All time" starts at the same first install day
const spanBad = [], totals = {};
for (const a of apps) {
  const h = out[`detail|${a.app}|all|30|cp|false`] || '', t = T(`detail|${a.app}|all|30|cp|false`), tot = (h.match(/<span id="uni-tot">([^<]*)<\/span>/) || [])[1];
  totals[a.app] = { line: tot == null ? null : tot.replace(/&amp;/g, '&'), installs: run(`fmtN(${a.launch.installs})`), day: run(`uniD(${JSON.stringify(a.launch.day)})`) };
  const s2 = (t.match(/All time = (.+?) ke saare pakke installs/) || [])[1], want = run(`uniSpan(${JSON.stringify(a.survival.all.from)},${JSON.stringify(a.settled_till)})`);
  if (!s2 || s2.trim() !== want) spanBad.push(a.app + ': ' + s2 + ' | ' + want);
}
const has = (k, s) => (out[k] || '').includes(s) || T(k).includes(s);
// the big "Stay after N days" tiles: [day, number shown] — an app's (its "At a glance" card), the portfolio's pooled ones
const tilesOf = h => [...h.matchAll(/data-sd="(\d+)" data-sv="([^"]*)"/g)].map(m => [+m[1], m[2]]);
const summary = {};
for (const a of apps) summary[a.app] = tilesOf(((out[`detail|${a.app}|all|30|cp|false`] || '').split('id="uni-sum"')[1] || '').split('id="uni-verdict"')[0]);
const pooled = tilesOf(((out.portfolio_30d || '').split('id="uni-pool"')[1] || '').split('class="uni-sec"')[0]);
// the All apps "At a glance" chips: their counts by default (no app list open), then each chip opened on its own —
// exactly one list, the apps in it (app chips) and its short text
const chipsOf = h => Object.fromEntries([...h.matchAll(/data-k="([^"]+)"[^>]*><i class="dt"><\/i>([^<]*) <b>\((\d+)\)<\/b>/g)].map(m => [m[1], { label: m[2], n: +m[3] }]));
const glanceOf = h => (h.split('id="uni-sum"')[1] || '').split('id="uni-alerts"')[0].replace(/^[^>]*>/, '').replace(/<div class="card"[^>]*$/, '');
const xp = { chips: chipsOf(out.portfolio_30d || ''), default_open: /data-xp="/.test(out.portfolio_30d || '') || /data-app="/.test(glanceOf(out.portfolio_30d || '')),
  glance: text(glanceOf(out.portfolio_30d || '')), open: {} };
for (const k of XP_KEYS) {
  const h = out['xp|' + k] || '', seg = (h.split('data-xp="')[1] || '');
  xp.open[k] = { panel: seg ? seg.slice(0, seg.indexOf('"')) : null, panels: (h.match(/data-xp="/g) || []).length, on: (h.match(/class="uni-sc [a-z]+ on"/g) || []).length,
    apps: [...h.matchAll(/data-app="([^"]*)"/g)].map(m => m[1].replace(/&amp;/g, '&')), text: text(seg.replace(/^[^>]*>/, '').split('<span class="uni-sc')[0].split('class="uni-sec"')[0].split('class="uni-foot"')[0].replace(/<div[^>]*$/, '')).trim().slice(0, 1500) };
}
// the English titles / labels of every card (details may stay Hinglish), and none of the old Hinglish titles anywhere
const A0 = `detail|${apps[0].app}|all|30|cp|false`, A0open = `detail|${apps[0].app}|all|90|all|true`;
const OLD_TITLES = ['Ek nazar me', 'Kya badla', 'Roz ka hisaab', '← Saari apps', '📋 Saari apps', 'Poori table', 'Install hafta', 'Usi din', 'usi din',
  '>kaccha<', '>naya<', 'kholo', 'Khaas din', '>Har din<', 'dikhao', 'chhupao', 'GA4 data nahi (', 'Hamesha (', 'Pehle 30 din', 'Poori umar',
  '4 hafte ka average', 'Kitne din me', '>Haal<', '>Farak<', 'Naya update', 'Phir try karo', 'Kam data', 'kam data', 'Data adhoora', 'Data gayab',
  'Roz ka uninstall rate:', 'me kuch dino ke installs', 'pichhle mahine jaisa', '100 naye users me se', 'tak har din', 'Naya version',
  '>Data nahi<', '>Lifetime<', 'Faded = low data (', 'kitne aaye', 'fetched abhi', 'min pehle', 'ghante pehle'];
const oldTitles = [];
for (const [k, v] of Object.entries(out)) if (k !== 'overview_no_admob' && k !== 'alert_cards') for (const w of OLD_TITLES) if (v.includes(w)) oldTitles.push(k + ': ' + w);
console.log(JSON.stringify({
  scenarios: Object.keys(out).length, errors, bad, titles: String(run('TITLES.uninstall.join("|")')), jargon: jargon.slice(0, 20), devanagari, old_titles: oldTitles.slice(0, 30),
  charts: { count: charts.length, all_never_rise: charts.every(c => c.never_rises), all_within: charts.every(c => c.within),
            all_hover_both: charts.every(c => c.hover_both), all_start_100: charts.every(c => c.first === '100% stay') },
  summary, pooled, xp, rate_states: rateStates, avg4: { checked: avg4Checked, bad: avg4Bad }, ref: { checked: refChecked, bad: refBad },
  rate_bad: rateBad, coh_bad: cohBad, gap_bad: gapBad, label_bad: labelBad, tip_big: tipBig, span_bad: spanBad,
  totals, header, header2, pages, texts: Object.fromEntries(Object.entries(out).filter(([k]) => /^(pre\||detail\|[^|]*\|all\|90\|all\|true|portfolio_30d|detail\|[^|]*\|all\|30\|cp\|false|overview_no_admob|tripage1_caller|no_verdict_young_launch|maybe_test|rel\|(two|newest|none|test)\||rel\|[^|]*\|(cp|all)\|false\|false$)/.test(k)).map(([k, v]) => [k, T(k)])),
  rel,
  plain_what_changed: (T('portfolio_30d').match(/What changed\? \((\d+)\)/) || [])[1],
  portfolio: T('portfolio_30d'),
  has: {
    curve_title: apps.every(a => has(`detail|${a.app}|all|30|cp|false`, '📉 How many stay — of 100 new users')),
    modes: ['First 30 days', 'First 90 days', 'All days'].every(s => has(A0, s)),
    toggle: has(A0, 'Recent installs (90 days)') && has(A0, 'All time (all installs)'),
    no_toggle_young: !has('detail|Demo Notes|all|30|cp|false', 'Recent installs (90 days)'),
    what_changed: apps.every(a => has(`detail|${a.app}|all|30|cp|false`, '🔔 What changed? (')),
    all_normal: has('detail|Demo Notes|all|30|cp|false', '✅ All normal — no changes'),
    table_link: has(A0, 'Show full table') && !has(A0, 'Full table — new installs vs before'),
    table_open: has(A0open, '🧮 Full table — new installs vs before') && has(A0open, 'Hide full table'),
    table_cols: ['Days after install', 'New installs: % gone', '4 weeks before', 'All time', 'Change', 'New installs from', 'Status']
      .every(s => has(A0open, '<th>' + s + '</th>')),
    avg4_row: has(A0, '4-week average') && has(A0open, '4-week average')
      && !Object.values(out).some(v => /Pichhle 4 hafte ka average|Sabse naye 4 pakke hafte/.test(v)),
    tri_labels: has(A0, '🔺 Install week × day') && has(A0, '<th>Install week</th>') && has(A0, 'All-time normal') && has(A0, '>Key days</span>') && has(A0, '>Every day</span>')
      && has(`tripages|${apps[0].app}`, '<th style="text-align:center">Install day</th>') && has(`tripages|${apps[0].app}`, '<th style="text-align:center">1 day</th>')
      && has(`tripages|${apps[0].app}`, '<th style="text-align:center">7 days</th>'),
    tri_buttons: has(A0, '>Show all</span>') && has(`detail|${apps[0].app}|recent|all|cp|true`, '>Hide</span>'),
    box_line: has(A0, 'Har box = us hafte install karne walon me se us din tak kitne % ne app hata diya'),
    glance_app: apps.every(a => has(`detail|${a.app}|all|30|cp|false`, '📌 At a glance') && has(`detail|${a.app}|all|30|cp|false`, '>Vs last month<')
      && /<div class="l">Daily uninstall rate(?: · (?:last|settled) 7 days)?<\/div>/.test(out[`detail|${a.app}|all|30|cp|false`] || '')) && has(A0, 'of 100 new users') && has(A0, '>Stay after 7 days<') && has(A0, 'per 1,000 active users'),
    daily_title: has(A0, '📊 Daily installs vs uninstalls') && ['30 days', '3 months', 'All time'].every(s => has(A0, '>' + s + '</span>')),
    back_link: has(A0, '<span class="backlnk" onclick="uniBack()">← All apps</span>'),
    portfolio_titles: ['<h2 class="sc">Uninstall</h2><p class="scd"><b style="color:var(--ink2)">Installs vs uninstalls (GA4)</b>', '📌 At a glance', '>App status <span>',
      '>Daily uninstall rate <span>', '🔔 What changed? (', '📋 All apps', '🔌 Apps without GA4 data (5)', '<b>When will I know?</b>']
      .every(s => has('portfolio_30d', s)),
    portfolio_cols: ['Stay after 7 days', 'Installs', 'Uninstalls', 'Net', 'Daily rate /1k', 'Gone on install day', 'Gone in 1 day', 'Gone in 7 days', 'Gone in 30 days', 'Alerts']
      .every(s => new RegExp('<th onclick="uniSort\\(\'[A-Za-z0-9]+\'\\)"[^>]*>' + s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&') + '( [▲▼])?</th>').test(out.portfolio_30d || '')),
    open_links: has('portfolio_30d', '<span class="lnk">Open →</span>') && has(A0, '>Open →</span>'),
    row_pills: has('portfolio_30d', '<span class="pill p-r">Worse</span>') && has('portfolio_30d', '<span class="pill p-g">Better</span>') && has('portfolio_30d', '<span class="pill p-y">Watch</span>'),
    avg4_says_weeks: has(A0, ' ke installs — har column me yahi installs; · = abhi itne din nahi hue') && !Object.values(out).some(v => v.includes('bade din ke liye purane installs')),
    header_gone: has('portfolio_30d', 'Stay = saare pakke installs') && has('portfolio_30d', 'Gone in … = sabse naye 7 install-din (alag installs — jud kar 100 nahi)'),
    decimal_gap: T('verdict_decimal').includes('⚠️ Worse than last month −2.5') && T('verdict_decimal').includes('After 7 days: 9.5 of 100 stay in the last 4 settled weeks')
      && /data-xp="worse"[\s\S]*<span class="x bad">−2\.5<\/span>/.test(out.verdict_decimal || ''),
    s7_arrow_day7_only: !/▲ \d/.test((out.verdict_day3 || '').split('id="uni-table"')[1] || 'x▲ 1') && /▲ 12→16/.test(T('portfolio_30d')),
    s7_no_mixed_arrow: !/\d%\s*▲\d/.test(T('portfolio_30d')),
    tiny_says_it: /data-sd="1" data-sv="[^"]+"/.test(out.tiny_app || '') && (out.tiny_app || '').includes('>Low data</span>') && /title="Low data — sirf [\d.k]+ installs/.test(out.tiny_app || '')
      && !T('tiny_app').includes('~2 hafte ke pakke data ke baad'),
    old_no_verdict: T('no_verdict_old').includes('ℹ️ Not enough data') && T('no_verdict_old').includes('kai din ka GA4 data adhoora/gayab') && !T('no_verdict_old').includes('~2 mahine ke data ke baad'),
    unsure_not_same: T('detail|Demo QR Scanner|all|30|cp|false').includes('ℹ️ Maybe ') && T('detail|Demo QR Scanner|all|30|cp|false').includes('abhi pakka nahi')
      && !T('detail|Demo QR Scanner|all|30|cp|false').includes('✅ Same as last month'),
    plain_words: !Object.values(out).some(v => /hamesha ka median|\(adhura\)|\b20\d\d-W\d\d\b/.test(text(v))),
    naye_installs_sub: !Object.values(out).some(v => /Naye installs \(\d/.test(text(v))),
    mix_note_all: has('portfolio_30d', 'All apps me har hafte apps ka mix badalta hai — sahi tulna ke liye upar se ek app chuno'),
    no_pooled_triangle: !Object.entries(out).some(([k, v]) => k.startsWith('portfolio') && v.includes('uni-tri-all')),
    mix_note_not_in_app: !has(A0, 'apps ka mix badalta hai'),
    s7_col: has('portfolio_30d', 'Stay after 7 days'),
    pooled_tiles: has('portfolio_30d', 'id="uni-pool"') && has('portfolio_30d', 'Saari apps ke pakke installs milakar'),
    provisional_tag: has('portfolio_30d', '>Provisional</span>'),
    new_tag: Object.values(out).some(v => v.includes('<span class="pill p-p">New</span>')) === apps.some(a => (a.alerts || []).some(x => x.fresh)),
    old_title_gone: !Object.values(out).some(v => v.includes('Har checkpoint') || v.includes('(cumulative)')),
    worse_app: T('verdict_worse').includes('⚠️ Worse than last month −5'),
    // the rate tile names its 7 days in the heading, their dates beside the number, the alert chip before "Provisional"
    rate_window: /Daily uninstall rate · last 7 days<\/div><div class="uni-rv">[\d.]+<small>per 1,000 active users · \d+–\d+ Sep<\/small>/.test(out[`detail|Demo Launcher|all|30|cp|false`] || '')
      && /data-ra="1">⚠️ Spike · 23 Sep<\/span><span class="pill p-b"[^>]*>Provisional</.test(out[`detail|Demo Launcher|all|30|cp|false`] || ''),
    // the full table's 🔍 pill in English (the engine's Hinglish label rewritten from its own parts)
    zoom_pill: has(A0open, '🔍 Alert (19 Sep) — every day till 10 Oct')
      && run(`uniZoomTxt({label:'Naya version 3.2 (10 Sep) — 1 Oct tak har din',reason:'release',until:'2026-10-01'})`) === 'New version 3.2 (10 Sep) — every day till 1 Oct'
      && run(`uniZoomTxt({label:'?',reason:'release',until:'2026-10-01'})`) === 'Every day till 1 Oct — after a new version',
    // "⏱️ When will I know?": one line by default, its points on a tap
    timing_fold: has('portfolio_30d', '⏱️ When will I know? Show') && !has('portfolio_30d', 'din der se aata hai')
      && (out.timing_open || '').split('<hr>').length === 2 && (out.timing_open || '').split('<hr>').every(h => text(h).includes('⏱️ When will I know? Hide') && text(h).includes('GA4 ka data 2 din der se aata hai')),
    fetched_english: /fetched (?:just now|\d+ min ago|\d+ h ago|\d+ days? ago)/.test(T(A0)) || !/fetched /.test(T(A0)),
    events_note: has('detail|Demo Caller – Test App|all|30|cp|false', 'ℹ️ Estimate · 85 old days')
      && !apps.some(a => a.app !== 'Demo Caller – Test App' && has(`detail|${a.app}|all|30|cp|false`, 'ℹ️ Estimate ·')),
    incomplete_kept: has('detail|Demo Launcher|all|30|cp|false', '⚠️ Data incomplete · 1 day'),
    worse_portfolio: (() => { const p = (out.verdict_worse || '').split('<hr>');
      return p.length === 3 && /data-k="worse"[^>]*><i class="dt"><\/i>Worse than last month <b>\(1\)<\/b>/.test(p[1]) && !/data-xp="/.test(p[1])
        && /data-xp="worse"/.test(p[2]) && text(p[2].split('data-xp="worse"')[1] || '').includes(apps[0].app + ' −5'); })(),
  },
}, null, 1));
