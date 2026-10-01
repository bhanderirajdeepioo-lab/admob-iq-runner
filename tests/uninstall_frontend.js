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
const RESET = `SMPF={}; SMPALL=false; UNIAPP=''; APP=''; UNICSRC='all'; UNICRANGE='90'; UNITRI='cp'; UNITRIPAGE=0; UNITRIEXP=false; UNIOLDEXP=false; UNICLEXP=false; UNICPEXP=false; UNIDRANGE='90d'; UNIPRE=false; UNISTEXP=''; UNITIMEXP=false; UNIIMPOPEN=''; UNIIMPALL=false; UNIIMPHOW=false; UNIUPF=''; UNIUPALL=false; UNIIMPJUMP=''; UNIIMPWIN=7; UNIIMPWK={};`;
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

// ── 📦 Update impact: the owner's verify gate — every block of every app rendered OPEN (UNIIMPOPEN = its key): its
// header, its 7 rows + the 2 version rows, its "Why:" footer; every release's key (the 📦 lines of the install-week
// table call uniImp with it) opens the block holding it, a folded (older) one too; All apps "Recent updates" with
// each verdict filter; the jump from another screen lands on the block (window.scrollTo recorded)
const impact = { blocks: [], jumps: [], tri_keys: [], portfolio: {}, jump_scroll: null, how: null, folded: null };
const itext = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ');
const openPart = h => { const p = h.split('<div class="uni-imp-b').filter(x => x.includes('data-open="1"'));
  return { n: p.length, html: p.length ? p[0].split('<div class="card"')[0] : '' }; };
for (const a of apps) {
  const id = JSON.stringify(a.app_id) + '; APP=' + JSON.stringify(a.app);
  const B = (a.impact && a.impact.updates) || [];
  for (const b of B) {
    const name = `imp|${a.app}|${b.key}`;
    scen(name, `${RESET} RANGE='30d'; UNIAPP=${id}; UNIIMPOPEN=${JSON.stringify(b.key)}; uniScreen()`);
    const o = openPart(out[name] || ''), h = o.html;
    const vt = (h.split('Same days: new version vs old versions')[1] || '');
    impact.blocks.push({ app: a.app, key: b.key, n_open: o.n, open_key: (h.match(/data-key="([^"]*)"/) || [])[1] || null,
      header: itext(((h.split('class="uni-imp-h"')[1] || '').split('</div>')[0]).replace(/^[^>]*>/, '')).trim(),
      rows: [...(h.split('Same days: new version vs old versions')[0]).matchAll(/<tr data-row="([a-z_0-9]+)"/g)].map(m => m[1]),
      vrows: [...vt.matchAll(/<tr data-row="([a-z_0-9]+)"/g)].map(m => m[1]),
      labels: [...h.matchAll(/<td class="nm"[^>]*>([^<]*)/g)].map(m => m[1]),
      heads: [...h.matchAll(/<th>([^<]*)<\/th>/g)].map(m => m[1]),
      statuses: [...h.matchAll(/data-st="([a-z]+)"/g)].map(m => m[1]),
      why: /<div class="uni-imp-why"><b>Why:<\/b> \S/.test(h), text: itext(h).slice(0, 3000), html: h });
    for (const rk of b.rel_keys || []) {
      let r = null;
      try { r = JSON.parse(run(`(()=>{ ${RESET} UNIAPP=${id}; uniImp(${JSON.stringify(rk)}); const o=UNIIMPOPEN, all=UNIIMPALL, h=uniScreen();
        return JSON.stringify({o, all, h}); })()`)); } catch (e) { errors.push('uniImp ' + rk + ': ' + e.message); continue; }
      impact.jumps.push({ app: a.app, rk, want: b.key, open: r.o, rendered: (openPart(r.h).html.match(/data-key="([^"]*)"/) || [])[1] || null });
    }
  }
  // the install-week table's 📦 lines / badges: each uniImp key they carry names a block of this app
  for (const tri of ['cp', 'all']) {
    const h = run(`(()=>{ ${RESET} const a=UNI.apps.find(x=>x.app_id===${JSON.stringify(a.app_id)}); UNITRI='${tri}'; UNITRIEXP=true; UNIPRE=true; return uniTriCard(a); })()`);
    for (const m of h.matchAll(/uniImp\('([^']*)'\)/g))
      impact.tri_keys.push({ app: a.app, k: m[1].replace(/&#39;/g, "'").replace(/\\'/g, "'"), found: B.some(b => b.key === m[1] || (b.rel_keys || []).includes(m[1])) });
  }
}
// a folded block (older than IMPACT_SHOW — shown as 1 here): its key unfolds the older ones and opens it
try { impact.folded = JSON.parse(run(`(()=>{ const a=UNI.apps.find(x=>uniImpBlocks(x).length>1), c=UNI.consts.impact, keep=c.impact_show;
  c.impact_show=1; try{ ${RESET} UNIAPP=a.app_id; APP=a.app; const B=uniImpBlocks(a), k=B[B.length-1].rel_keys[0], shut=uniScreen();
    uniImp(k); const h=uniScreen(); return JSON.stringify({k, want:B[B.length-1].key, all:UNIIMPALL, shut_has:shut.includes('id="uni-imp-'+B[B.length-1].key+'"'),
      shut_fold:shut.includes('Show older updates ('+(B.length-1)+')'), open:(h.split('data-open="1"')[0].match(/id="uni-imp-([^"]*)"[^>]*$/)||[])[1]||null}); }
  finally{ c.impact_show=keep; ${RESET} } })()`)); } catch (e) { errors.push('folded: ' + e.message); }
scen('imp_how', `${RESET} UNIAPP=${JSON.stringify(apps[0].app_id)}; APP=${JSON.stringify(apps[0].app)}; UNIIMPHOW=true; uniScreen()`);
impact.how = itext((out.imp_how || '').split('How we compare')[1] || '').slice(0, 2000);
// a block the next update cut to under 3 days can never get a verdict: its chip says why (not "wait"), "No verdict"
try { impact.never = JSON.parse(run(`(()=>{ const a=UNI.apps.find(x=>uniImpBlocks(x).length), b=uniImpBlocks(a)[0], keep=b.verdict;
  b.verdict=Object.assign({},keep,{level:null,final:true,early:false,ready_on:null,why:'Agla update bahut jaldi aa gaya'});
  try{ ${RESET} UNIAPP=a.app_id; APP=a.app; const h=uniScreen(); UNIAPP=''; APP=''; RANGE='30d'; const p=uniScreen();
    return JSON.stringify({h:(h.split('id="uni-imp-'+b.key+'"')[1]||'').split('class="uni-imp-m"')[0], p:(p.split('id="uni-updates"')[1]||'').split('<div class="card')[0]}); }
  finally{ b.verdict=keep; ${RESET} } })()`)); } catch (e) { errors.push('never: ' + e.message); }
// the Recent updates card failing to render: a visible placeholder (never silently gone)
scen('upd_throw', `${RESET} RANGE='30d'; (()=>{ const keep=uniUpdatesCard; uniUpdatesCard=()=>{ throw new Error('x'); };
  try{ return uniScreen(); } finally{ uniUpdatesCard=keep; } })()`);
impact.upd_throw = /<div class="card faint" id="uni-updates"[^>]*>⚠️ 📦 Update impact — ye hissa abhi dikh nahi paya\.<\/div>/.test(out.upd_throw || '');
// All apps "📦 Recent updates": the counts, and each verdict's rows alone
for (const f of ['', 'open']) {
  scen('upd|' + f, `${RESET} RANGE='30d'; UNIUPALL=${f === 'open'}; uniScreen()`);
  const h = ((out['upd|' + f] || '').split('id="uni-updates"')[1] || '').split('<div class="card')[0];
  impact.portfolio[f] = { chips: Object.fromEntries([...h.matchAll(/data-uf="([a-z]+)"[^>]*>([^<]*)<b>\((\d+)\)<\/b>/g)].map(m => [m[1], { label: m[2].trim(), n: +m[3] }])),
    rows: [...h.matchAll(/class="uni-upd" data-lv="([a-z]+)"/g)].map(m => m[1]), on: [...h.matchAll(/class="uni-sc [a-z]+ on" data-uf="([a-z]+)"/g)].map(m => m[1]),
    text: itext(h).slice(0, 2500) };
}
// the display rule: a Low data / No data / Pending row never shows a model number (vs expected, trend-adjusted,
// "(judged)") — its plain Before → After "vs before", or —; the folded line and the Recent updates list show a change
// only from a Worse / Better row ("No clear change" when the verdict found none)
const IMP_JUDGED = ['worse', 'better', 'same', 'unsure', 'market'], IMP_MODEL = /vs expected|\(judged\)|net of the usual trend|>expected [\d,]|[Ee]xpected \((?:bina update ke|without update)\)|Actual:|pakka: ≥/;
impact.display = { rows: 0, judged: 0, bad: [], vs_expected: 0, vs_before: 0, mini_bad: [], heads: [], synth: null };
for (const blk of impact.blocks) {
  const main = blk.html.split('Same days: new version vs old versions')[0];
  for (const m of main.matchAll(/<tr data-row="([a-z_0-9]+)">([\s\S]*?)<\/tr>/g)) {
    const st = (m[2].match(/data-st="([a-z]+)"/) || [])[1];
    impact.display.rows++;
    if (IMP_JUDGED.includes(st)) { impact.display.judged++; impact.display.vs_expected += m[2].includes(' vs expected<') ? 1 : 0; continue; }
    impact.display.vs_before += m[2].includes(' vs before<') ? 1 : 0;
    if (IMP_MODEL.test(m[2])) impact.display.bad.push(blk.app + '|' + blk.key + '|' + m[1] + ': ' + itext(m[2]).slice(0, 200));
  }
}
const MINI_WORD = { same: 'normal', unsure: 'normal (not sure)', market: 'normal (bazaar)', low: 'Low data', pending: '⏳', na: '—' };   // (the six words, as UNI_IST)
for (const a of apps) for (const b of (a.impact && a.impact.updates) || []) {
  const h = run(`uniImpMini(${JSON.stringify(b)})`), spans = [...h.matchAll(/<span( class="(up|down)")?>([^<]*)<\/span>/g)].map(m => [m[2] || '', m[3]]);
  const rows = b.rows || {}, vrows = (b.versions_cmp && b.versions_cmp.rows) || {};
  const shorts = { returning_dau: 'Old users/day', new_d1: 'Back next day', new_d7: 'Back after 7 days', sessions: 'Sessions/user', time: 'Time/user', arpdau: 'Revenue per user', uninstall_d0: 'Same day uninstall' };
  // a Worse / Better row: the change it was JUDGED on, said so (vs expected — DAU's model level, sessions / time net of
  // the trend: one word with the open row, SPEC_WINDOWS §5 · ads/user), its sign the status's (up = better, but more
  // install-day uninstalls = worse) — never a plain change pointing the other way
  const judgedAs = { returning_dau: ['Old users/day', ' vs expected'], sessions: ['Sessions/user', ' vs expected'], time: ['Time/user', ' vs expected'], arpdau: ['AdMob ads/user', ''] };
  for (const [k, sh] of Object.entries(shorts)) {
    const st = rows[k].status, wbk = ['worse', 'better'].includes(st), [lb, sf] = wbk && judgedAs[k] ? judgedAs[k] : [sh, ''];
    const sp = spans.find(x => x[1].startsWith(lb + ' ')), sg = (st === 'worse') !== (k === 'uninstall_d0') ? '−' : '+';
    const sv = sp ? sp[1] : '';   // the display rule: a share's change is "+6%" (never "100 me +6", SPEC_SIMPLIFY §1.7)
    const ok = wbk ? (sp && sp[0] === (st === 'worse' ? 'down' : 'up') && sv.startsWith(lb + ' ' + sg) && new RegExp('^' + lb.replace(/[()]/g, '\\$&') + ' [−+][\\d.]+%?' + sf + '$').test(sv)) : (sp && sp[0] === '' && sp[1] === sh + ' ' + MINI_WORD[st]);
    if (!ok) impact.display.mini_bad.push(a.app + '|' + b.key + '|' + k + ': ' + (sp ? sp.join('|') : 'missing'));
  }
  const all = Object.values(Object.assign({}, rows, vrows)), wb = all.some(r => r && ['worse', 'better'].includes(r.status));
  const nj = all.filter(r => r && IMP_JUDGED.includes(r.status)).length, lead = nj ? 'No clear change' : '⏳ Too early';
  if (h.includes(lead) !== (!wb && !!(b.verdict && b.verdict.level)) || (nj ? h.includes('⏳ Too early ·') : h.includes('No clear change'))) impact.display.mini_bad.push(a.app + '|' + b.key + ': ' + lead + ' ' + h.includes(lead));
}
{ const h = ((out['upd|open'] || '').split('id="uni-updates"')[1] || '').split('<div class="card')[0];   // every update (the folded ⏳ / 👍 / — line opened)
  for (const m of h.matchAll(/<div class="uni-upd" data-lv="([a-z]+)" onclick="uniImpGo\('([^']*)','([^']*)'\)">([\s\S]*?)<span class="lnk go">/g)) {
    const a = apps.find(x => x.app_id === m[2]), b = ((a && a.impact && a.impact.updates) || []).find(x => x.key === m[3]);
    const hl = (m[4].match(/<span class="hl [a-z]+"[^>]*>([^<]*)<\/span>/) || [])[1] || null;
    const u = (FX.dashboard_uninstall.apps.find(r => r.app_id === m[2]) || { updates: [] }).updates.find(x => x.key === m[3]) || {};
    const r = u.head && b ? (b.rows[u.head.row] || b.versions_cmp.rows[u.head.row]) : null;
    impact.display.heads.push({ lv: m[1], hl, head_row: u.head ? u.head.row : null, head_status: r ? r.status : null, late: m[4].includes(' uni-late"') });
  }
}
// a young app that grew fast before its update (synthetic numbers): its rows Low data with a model level beside them
try { impact.display.synth = JSON.parse(run(`(()=>{ ${RESET} UNIUPALL=true; const a0=UNI.apps.find(x=>uniImpBlocks(x).length), a=JSON.parse(JSON.stringify(a0)), b=uniImpBlocks(a)[0];
  const itx=h=>h.replace(/<[^>]+>/g,' ').replace(/&amp;/g,'&').replace(/\\s+/g,' ').trim();
  const why='Update se pehle app tez badh raha tha (~×6.7/hafta) — normal trend pakka nahi, isliye sirf pehle vs baad';
  for (const r of Object.values(b.rows).concat(Object.values(b.versions_cmp.rows))) if(r.status==='worse'||r.status==='better'){ r.status=r.raw_status='same'; }
  Object.assign(b.rows.returning_dau,{status:'low',raw_status:'low',before:1200,after:1300,expected:9000,change:-0.8556,z:null,reason:why});
  Object.assign(b.rows.returning_dau.extra,{raw_change:0.08333,mu_week:1.9,mode:'raw'});
  Object.assign(b.rows.arpdau,{status:'low',raw_status:'low',before:8,after:8.4,change:0.05,z:null,reason:why.replace('app','kamai per user')});
  Object.assign(b.rows.arpdau.extra,{imp_adj:3.1,imp_change:0.4,ecpm_change:-0.3});
  Object.assign(b.rows.sessions,{status:'low',raw_status:'low',before:2,after:2.2,change:0.1,z:null,reason:why});
  Object.assign(b.rows.sessions.extra,{adj_change:-0.6});
  b.verdict=Object.assign({},b.verdict,{level:'continue',worse:[],better:[],early:false,final:true});
  const open=uniImpBlock(a,b,true), mini=uniImpMini(b), tr=k=>(open.split('<tr data-row="'+k+'">')[1]||'').split('</tr>')[0];
  const s={app:'Demo Young',app_id:a.app_id,updates:[{key:b.key,label:b.label,date:b.date,level:'continue',early:false,final:true,adoption:0.9,head:null},
    {key:b.key,label:b.label,date:b.date,level:'continue',early:false,final:true,adoption:0.9,head:{row:'returning_dau',change:-0.8556,unit:'rel'}}]};
  const upd=uniUpdatesCard([{s,a}]);
  return JSON.stringify({dau:itx(tr('returning_dau')), arp:itx(tr('arpdau')), ses:itx(tr('sessions')), mini:itx(mini), upd:itx(upd)}); })()`)); } catch (e) { errors.push('imp synth: ' + e.message); }
// a Worse / Better per-user row whose plain change points the other way (synthetic): a HALT on ads/user −35% while
// revenue/user rose +120% (eCPM), sessions −8% net of a trend while the number rose +3%; and a block nothing could
// measure (every row Low data / No data: "Not enough data yet", never "No clear change")
try { impact.display.contra = JSON.parse(run(`(()=>{ ${RESET} UNIUPALL=true; const a0=UNI.apps.find(x=>uniImpBlocks(x).length), a=JSON.parse(JSON.stringify(a0)), b=uniImpBlocks(a)[0];
  const itx=h=>h.replace(/<[^>]+>/g,' ').replace(/&amp;/g,'&').replace(/\\s+/g,' ').trim();
  for (const r of Object.values(b.rows).concat(Object.values(b.versions_cmp.rows))) if(r.status==='worse'||r.status==='better'){ r.status=r.raw_status='same'; }
  Object.assign(b.rows.arpdau,{status:'worse',raw_status:'worse',before:5,after:11,change:1.2,z:-9});
  Object.assign(b.rows.arpdau.extra,{imp_adj:-0.35,imp_change:-0.3,ecpm_change:2.1});
  Object.assign(b.rows.sessions,{status:'worse',raw_status:'worse',before:2,after:2.06,change:0.03,z:-6});
  Object.assign(b.rows.sessions.extra,{adj_change:-0.08});
  b.verdict=Object.assign({},b.verdict,{level:'halt',worse:['arpdau','sessions'],better:[],early:false,final:true});
  const open=uniImpBlock(a,b,true), mini=uniImpMini(b), tr=k=>(open.split('<tr data-row="'+k+'">')[1]||'').split('</tr>')[0];
  const cell=k=>(tr(k).split('<td class="uni-num"')[3]||'');
  const s={app:'Demo Contra',app_id:a.app_id,updates:[{key:b.key,label:b.label,date:b.date,level:'halt',early:false,final:true,adoption:0.9,head:{row:'arpdau',change:-0.35,unit:'rel'},judged:9}]};
  const upd=uniUpdatesCard([{s,a}]);
  const n=JSON.parse(JSON.stringify(b));
  for (const r of Object.values(n.rows).concat(Object.values(n.versions_cmp.rows))){ r.status=r.raw_status='low'; }
  n.verdict=Object.assign({},n.verdict,{level:'continue',worse:[],better:[],early:false,final:true});
  const s2={app:'Demo Nodata',app_id:a.app_id,updates:[{key:b.key,label:b.label,date:b.date,level:'continue',early:false,final:true,adoption:0.9,head:null,judged:0}]};
  const upd2=uniUpdatesCard([{s:s2,a:null}]);
  return JSON.stringify({mini:mini, arp_cell:cell('arpdau'), ses_cell:cell('sessions'), upd:itx(upd), upd_html:upd, nd_mini:itx(uniImpMini(n)), nd_upd:itx(upd2), nd_html:upd2}); })()`)); } catch (e) { errors.push('imp contra: ' + e.message); }
// "Update detail →" (Alerts screen) / a Recent updates row with the header's App ALREADY that app: the page ends on the
// block (it went back to the top: the jump was cancelled by uniOpen's scroll to the top)
try { impact.jump_scroll = JSON.parse(run(`(()=>{ const keep={render, show, _navSave, doc:document, win:window}, calls=[];
  const a=UNI.apps.find(x=>uniImpBlocks(x).length>1), B=uniImpBlocks(a), k=B[B.length-1].key;
  render=function(){}; show=function(){}; _navSave=function(){};
  document={getElementById:id=>id==='uni-imp-'+k?{getBoundingClientRect:()=>({top:1851,height:40})}:null, querySelector:()=>null};
  window={scrollTo:o=>calls.push(o), scrollY:0, pageYOffset:0};
  try{ ${RESET} APP=a.app; UNIAPP=a.app_id; uniImpGo(a.app_id,k); return JSON.stringify({k, calls, open:UNIIMPOPEN, pending:UNIIMPJUMP}); }
  finally{ render=keep.render; show=keep.show; _navSave=keep._navSave; document=keep.doc; window=keep.win; ${RESET} } })()`)); } catch (e) { errors.push('jump_scroll: ' + e.message); }

// ── 📦 Before / after windows (SPEC_WINDOWS §5): 7 / 14 / 30 / 60 days, Actual / Expected, Mixed, ⏰ late ──
// (a) the fixture's own by_window (impact v2) — every block at every window; (b) made-up windows (__mkW: the §4
// contract's shape, sparse rows) on a copy of an app, so every display rule is checked whatever the fixture holds
run(fs.readFileSync(require('path').join(__dirname, 'impact_win_synth.js'), 'utf8'));
const win = { src: null, blocks: [], syn: {} };
const V2 = apps.some(a => ((a.impact || {}).updates || []).some(b => b.by_window));
win.src = V2 ? 'fixture' : 'v1';
const segOf = h => { const m = h.match(/<div class="uni-imp-seg[^"]*"[^>]*><span>Before \/ after:<\/span><span class="seg">([\s\S]*?)<\/span><\/div>/);
  return m ? [...m[1].matchAll(/<button( class="on")?( disabled title="([^"]*)")?[^>]*>([^<]*)<\/button>/g)].map(x => ({ on: !!x[1], dis: !!x[2], tip: x[3] || null, t: x[4] })) : null; };
const blkOf = (h, key) => { const p = h.split('<div class="uni-imp-b').find(x => x.includes('data-key="' + key + '"')) || ''; return p.split('<div class="card"')[0]; };
const rowsOf = h => [...h.split('Same days: new version vs old versions')[0].matchAll(/<tr data-row="([a-z_0-9]+)">([\s\S]*?)<\/tr>/g)].map(m => ({ k: m[1], h: m[2], st: (m[2].match(/data-st="([a-z]+)"/) || [])[1] }));
// (a) the fixture's windows: every block opened at 7 / 14 / 30 / 60 (the block's own choice)
if (V2) for (const a of apps) for (const b of ((a.impact || {}).updates || [])) for (const N of [7, 14, 30, 60]) {
  const nm = `win|${a.app}|${b.key}|${N}`;
  scen(nm, `${RESET} RANGE='30d'; UNIAPP=${JSON.stringify(a.app_id)}; APP=${JSON.stringify(a.app)}; UNIIMPOPEN=${JSON.stringify(b.key)}; UNIIMPWK={${JSON.stringify(b.key)}:${N}}; uniScreen()`);
  const h = blkOf(out[nm] || '', b.key), W = N === 7 ? null : (b.by_window || {})[String(N)] || null, rs = rowsOf(h);
  win.blocks.push({ app: a.app, key: b.key, n: N, state: W ? W.state : null, has: !!W, open: h.includes('data-open="1"'),
    header: itext(((h.split('class="uni-imp-h"')[1] || '').split('</div>')[0]).replace(/^[^>]*>/, '')).trim(),
    rows: rs.map(r => r.k), statuses: rs.map(r => r.st), labels: [...h.split('Same days: new version vs old versions')[0].matchAll(/<td class="nm"[^>]*>([^<]*)/g)].map(m => m[1]),
    heads: [...h.matchAll(/<th>([^<]*)<\/th>/g)].map(m => m[1]), seg: segOf(h), vtable: h.includes('Same days: new version vs old versions'),
    vnote: h.includes('Naya vs purana version: sirf 7-din window me (baad me naye updates aa jaate hain)'),
    why: itext((h.split('<div class="uni-imp-why">')[1] || '').split('</div>')[0]).trim(), mixed: (W && W.mixed || []).map(m => m.label),
    mixed_pill: (h.match(/class="pill p-b uni-mixed" title="([^"]*)">([^<]*)</) || []).slice(1).map(x => x.replace(/&amp;/g, '&')),
    after_days: W ? W.after : null, late_lv: run(`uniImpLateLv(${JSON.stringify(b)})`), late_chip: (h.match(/<span class="pill [a-z-]+ uni-late"[^>]*onclick="([^"]*)">([^<]*)<\/span>/) || []).slice(1),
    dau: (rs.find(r => r.k === 'returning_dau') || {}).h || '', text: itext(h).slice(0, 2500) });
}
// the fixture's ⏰ late family on the other screens: Recent updates' chip, the What changed? rows (All apps, the app)
win.upd_late = [...((out['upd|open'] || '').split('id="uni-updates"')[1] || '').matchAll(/class="pill [a-z-]+ uni-late"[^>]*onclick="event\.stopPropagation\(\);uniImpGo\('([^']*)','([^']*)','uni',30\)">([^<]*)</g)].map(m => [m[1], m[2], m[3]]);
scen('portfolio_folds', `${RESET} RANGE='30d'; SMPALL=true; uniScreen()`);   // every "What changed?" fold open (SPEC_SIMPLIFY §6.3)
win.chg_late = [...(out.portfolio_folds || '').matchAll(/<div class="uni-chg wa"[^>]*onclick="uniImpGo\('([^']*)','([^']*)','uni',30\)"/g)].map(m => [m[1], m[2]]);
win.chg_late_app = [];
for (const a of apps) { scen(`detail_folds|${a.app}`, `${RESET} RANGE='30d'; SMPALL=true; UNIAPP=${JSON.stringify(a.app_id)}; APP=${JSON.stringify(a.app)}; uniScreen()`);
  const h = out[`detail_folds|${a.app}`] || '';
  for (const m of h.matchAll(/<span class="lnk" onclick="uniImp\('([^']*)','uni',30\)">Open →<\/span>/g)) win.chg_late_app.push([a.app_id, m[1]]); }
// (b) made-up windows: the card default, a block's own choice, what survives a re-render, remembered / blocked storage
const S = win.syn;
try { S.card = JSON.parse(run(`(()=>{ ${RESET} const a=__winApp(UNI.apps.find(x=>uniImpBlocks(x).length>1)), B=uniImpBlocks(a), k0=B[0].key, k1=B[B.length-1].key, hdr=h=>[...h.matchAll(/Verdict( \\(\\d+ days\\))?:/g)].map(m=>m[1]||'');
  const saved=[]; const keepLS=localStorage; localStorage={getItem:()=>null,setItem:(k,v)=>saved.push([k,v]),removeItem(){}};
  try{ UNIIMPWIN=undefined; const r={};
    r.first=hdr(uniImpactCard(a)); r.first_seg=uniImpactCard(a);
    uniImpWinX(30); r.w30=hdr(uniImpactCard(a)); r.win=UNIIMPWIN; r.saved=saved.slice();
    uniImpWX(k1,60); r.over=hdr(uniImpactCard(a)); r.again=hdr(uniImpactCard(a)); r.wk=JSON.parse(JSON.stringify(UNIIMPWK));
    uniImpWinX(14); r.w14=hdr(uniImpactCard(a)); r.wk2=JSON.parse(JSON.stringify(UNIIMPWK)); r.act_win=ACTIMPWIN===undefined?'unread':ACTIMPWIN;
    UNIIMPOPEN=k0; r.open30=(uniImpWinX(30),uniImpactCard(a)); r.k0=k0; r.k1=k1; r.nblocks=B.length;
    return JSON.stringify(r); } finally{ localStorage=keepLS; ${RESET} } })()`)); } catch (e) { errors.push('win card: ' + e.message); }
try { S.store = JSON.parse(run(`(()=>{ ${RESET} const a=__winApp(UNI.apps.find(x=>uniImpBlocks(x).length>1)), keepLS=localStorage, hdr=h=>[...h.matchAll(/Verdict( \\(\\d+ days\\))?:/g)].map(m=>m[1]||''), r={};
  try{ localStorage={getItem:()=>'30',setItem(){},removeItem(){}}; UNIIMPWIN=undefined; r.remembered=hdr(uniImpactCard(a)); r.rwin=UNIIMPWIN;
    localStorage={getItem:()=>{ throw new Error('blocked'); },setItem:()=>{ throw new Error('blocked'); },removeItem(){}}; UNIIMPWIN=undefined;
    r.blocked=hdr(uniImpactCard(a)); r.bwin=UNIIMPWIN; r.bseg=uniImpactCard(a); uniImpWinX(60); r.blocked60=hdr(uniImpactCard(a));
    // no default chosen: a block whose late episode is open (default_window 30) shows 30, the others 7; a chosen 7 wins
    const B=uniImpBlocks(a); B[0].default_window=30; localStorage={getItem:()=>null,setItem(){},removeItem(){}}; UNIIMPWIN=undefined; r.dflt=hdr(uniImpactCard(a));
    UNIIMPWIN=7; r.dflt7=hdr(uniImpactCard(a));
    return JSON.stringify(r); } finally{ localStorage=keepLS; ${RESET} } })()`)); } catch (e) { errors.push('win store: ' + e.message); }
// an asset from before the windows (no by_window): 14 / 30 / 60 disabled "Agle robot run ke baad"; built with the switch
// off (the engine's consts list the windows, no block has them): no selector at all
try { S.v1 = JSON.parse(run(`(()=>{ ${RESET} const a=__winApp(UNI.apps.find(x=>uniImpBlocks(x).length>1)), c=UNI.consts.impact, keep=c.windows; uniImpBlocks(a).forEach(b=>{ delete b.by_window; delete b.default_window; }); a.impact.v=1;
  try{ UNIIMPOPEN=uniImpBlocks(a)[0].key; delete c.windows; const off=uniImpactCard(a); c.windows=[7,14,30,60]; const hid=uniImpactCard(a);
    a.impact.v=2; const fail=uniImpactCard(a); a.impact.v=1;   // a v2 app whose windows failed this run: disabled, not hidden
    uniImpWinX(30); const after=uniImpactCard(a); return JSON.stringify({off, hid, fail, after_hdr:[...after.matchAll(/Verdict( \\(\\d+ days\\))?:/g)].map(m=>m[1]||'')}); }
  finally{ if(keep===undefined) delete c.windows; else c.windows=keep; ${RESET} } })()`)); } catch (e) { errors.push('win v1: ' + e.message); }
if (S.v1) { S.v1.off_seg = segOf(S.v1.off); S.v1.off_blk_seg = segOf(S.v1.off.split('data-open="1"')[1] || ''); S.v1.hid_has = S.v1.hid.includes('class="uni-imp-seg');
  S.v1.fail_seg = segOf(S.v1.fail); delete S.v1.off; delete S.v1.hid; delete S.v1.fail; }
if (S.card) { S.card.card_seg = segOf(S.card.first_seg); S.card.open30_seg = segOf(S.card.open30.split('data-open="1"')[1] || ''); S.card.open30_blk = rowsOf(blkOf(S.card.open30, S.card.k0)).map(r => r.k); delete S.card.first_seg; delete S.card.open30; }
if (S.store) { S.store.bseg = segOf(S.store.bseg); }
// every row's cells at 7 (v2-style rows), 14, 30 (judged: plain per-user, D30 pending, Mixed) and 60 (running), and a
// Low data ("young") 30; plus the late chip, the "already told" note, the Alerts card, What changed? and Recent updates
try { S.views = JSON.parse(run(`(()=>{ ${RESET} const a=__winApp(UNI.apps.find(x=>uniImpBlocks(x).length>1)), B=uniImpBlocks(a), b=B[B.length-1], k=b.key, r={}; try{
  const cells=h=>Object.fromEntries([...h.split('Same days: new version vs old versions')[0].matchAll(/<tr data-row="([a-z_0-9]+)">([\\s\\S]*?)<\\/tr>/g)].map(m=>{ const td=m[2].split('<td'); return [m[1],{after:'<td'+td[3],change:'<td'+td[4],status:'<td'+td[5]}]; }));
  for (const N of [7,14,30,60]){ UNIIMPWK={[k]:N}; const h=uniImpBlock(a,b,true); r[N]={h, cells:cells(h), mini:uniImpBlock(a,b,false)}; }
  // a running window no row can ever fill (the app is younger than its Before): the engine's why, no verdict day promised
  const w60=b.by_window['60'], keep60=JSON.stringify(w60), why0='Update app launch ke 60 din ke andar aaya — pehle ke poore 60 din nahi';
  Object.values(w60.rows).forEach(x=>{ x.status='na'; delete x.ready_on; delete x.after_prov; delete x.prov; x.reason=why0; });
  Object.assign(w60.verdict,{pending:[],ready_on:null,why:why0}); UNIIMPWK={[k]:60};
  r.never={h:uniImpBlock(a,b,true), mini:uniImpBlock(a,b,false)}; b.by_window['60']=JSON.parse(keep60);
  b.by_window['30']=__mkW(b,30,{state:'final',young:true,mixed:b.by_window['30'].mixed}); UNIIMPWK={[k]:30}; const hy=uniImpBlock(a,b,true); r.young={h:hy, cells:cells(hy)};
  // told: this update's own 7-day HOLD on ads per user, and one told by an update inside the window (its label)
  const m=B[0]; m.verdict=Object.assign({},m.verdict,{level:'hold',worse:['new_d1']}); b.verdict=Object.assign({},b.verdict,{level:'hold',worse:['arpdau']});
  b.by_window['30']=__mkW(b,30,{state:'judged',worse:['arpdau','new_d1'],told:['arpdau','new_d1'],mixed:[{key:m.key,label:m.label||'App update',date:m.date}]});
  const ht=uniImpBlock(a,b,true); r.told=cells(ht); r.told_h=ht;
  b.by_window['30'].verdict.told_by={new_d1:'v9.9'}; r.told_by=cells(uniImpBlock(a,b,true)); delete b.by_window['30'].verdict.told_by;   // the engine's own naming wins
  // ⏰ late: the header chip (the block's late alert, else its 30-day verdict), whatever window the block shows
  b.late={level:'halt',alert_id:'x',seeded:false}; UNIIMPWK={}; r.late_hdr=uniImpBlock(a,b,false); b.late=null;
  b.by_window['30'].verdict.late='hold'; r.late_v30=uniImpBlock(a,b,false); r.k=k; r.label=b.label; r.m_label=m.label;
  return JSON.stringify(r); } finally{ ${RESET} } })()`)); } catch (e) { errors.push('win views: ' + e.message); }
if (S.views) for (const N of ['7', '14', '30', '60', 'young']) { const v = S.views[N]; v.heads = [...v.h.matchAll(/<th>([^<]*)<\/th>/g)].map(m => m[1]);
  v.header = itext(((v.h.split('class="uni-imp-h"')[1] || '').split('</div>')[0]).replace(/^[^>]*>/, '')).trim(); v.seg = segOf(v.h); v.text = itext(v.h);
  v.mini_text = itext((v.mini || '').split('class="uni-imp-mini"')[1] || '').replace(/^[^>]*>/, '').trim(); out['win_view|' + N] = v.h; }
// the late chip's tap (the block's app on screen): that block, opened, at 30
try { S.late_tap = JSON.parse(run(`(()=>{ ${RESET} const a=__winApp(UNI.apps.find(x=>uniImpBlocks(x).length>1)), i=UNI.apps.findIndex(x=>x.app_id===a.app_id), keep=UNI.apps[i], B=uniImpBlocks(a), b=B[B.length-1];
  b.late={level:'hold',alert_id:'x',seeded:false}; UNI.apps[i]=a;
  try{ UNIAPP=a.app_id; APP=a.app; UNIIMPOPEN='-'; const h=uniScreen(), m=h.match(/<span class="pill [a-z-]+ uni-late"[^>]*onclick="([^"]*)">([^<]*)<\\/span>/);
    uniImp(b.key,'uni',30); const g=uniScreen(), o=g.split('<div class="uni-imp-b').find(x=>x.includes('data-open="1"'))||'';
    return JSON.stringify({call:m&&m[1], chip:m&&m[2], open:UNIIMPOPEN, wk:UNIIMPWK, want:b.key, hdr:(o.match(/Verdict( \\(\\d+ days\\))?:/)||[])[0]||null}); }
  finally{ UNI.apps[i]=keep; ${RESET} } })()`)); } catch (e) { errors.push('win late tap: ' + e.message); }
// the late family on the other screens: the Alerts card, What changed? rows (All apps / one app), Recent updates' chip
try { S.late_al = JSON.parse(run(`(()=>{ ${RESET} UNIUPALL=true; const a=UNI.apps.find(x=>uniImpBlocks(x).length), b=uniImpBlocks(a)[0];
  const al={family:'impact_late',level:'hold',severity:'watch',dir:'up',app:a.app,app_id:a.app_id,data_till:'2026-09-23',opened:'2026-09-23',fresh:true,
    release:{key:b.key,label:b.label||'App update',date:b.date},rows:{worse:['arpdau'],told:[]},mixed:[],window:30,
    text:(b.label||'App update')+' ke 30 din baad ads per user −14% · pehle 7 din me ye nahi dikha tha · HOLD — agla rollout roko, jaanch karo'};
  const s={app:a.app,app_id:a.app_id,updates:[{key:b.key,label:b.label,date:b.date,level:'continue',early:false,final:true,adoption:0.9,head:null,judged:7,late:{level:'hold',alert_id:'x'}},
    {key:b.key+'x',label:b.label,date:b.date,level:'continue',early:false,final:true,adoption:0.9,head:null,judged:7,late:null}]};
  return JSON.stringify({card:uniAlertCards([al]), row_all:uniChangeRow(al,true,false), row_app:uniChangeRow(al,false,false), when:uniWhen(al), sev:uniSev(al), plain:uniPlain(al),
    upd:uniUpdatesCard([{s,a}]), app_id:a.app_id, key:b.key, label:b.label||'App update', date:uniD(b.date)}); })()`)); } catch (e) { errors.push('win late alerts: ' + e.message); }
if (S.late_al) { out.win_late_card = S.late_al.card; out.win_late_upd = S.late_al.upd; }
// review fixes (2026-09-28): the 7-day verdict beside a long window, Mixed on a folded header, "Not enough data", a plain
// per-user row's one "vs before" number, the young line said once (the engine's own weeks), a window that failed alone
try { S.fix = JSON.parse(run(`(()=>{ ${RESET} const a=__winApp(UNI.apps.find(x=>uniImpBlocks(x).length>1)), B=uniImpBlocks(a), b=B[B.length-1], k=b.key, r={}; try{
  const cells=h=>Object.fromEntries([...h.split('Same days: new version vs old versions')[0].matchAll(/<tr data-row="([a-z_0-9]+)">([\\s\\S]*?)<\\/tr>/g)].map(m=>{ const td=m[2].split('<td'); return [m[1],{label:'<td'+td[1],after:'<td'+td[3],change:'<td'+td[4],status:'<td'+td[5]}]; }));
  const hdr=h=>(h.split('class="uni-imp-h"')[1]||'').split('</div>')[0];
  // a 7-day HALT (the alerts' verdict) while the card shows 30 — judged, and still running
  b.verdict=Object.assign({},b.verdict,{level:'halt',worse:['arpdau']}); UNIIMPWIN=30; UNIIMPWK={};
  r.halt30=hdr(uniImpBlock(a,b,false)); r.halt7=(UNIIMPWIN=7,hdr(uniImpBlock(a,b,false)));
  const keep30=JSON.stringify(b.by_window['30']); b.by_window['30']=__mkW(b,30,{state:'running'}); UNIIMPWIN=30;
  r.halt30run=hdr(uniImpBlock(a,b,false)); r.halt30run_mini=uniImpBlock(a,b,false);
  b.by_window['30']=__mkW(b,30,{state:'judged',mixed:[{key:'m1',label:'v8.1',date:'2026-09-01'},{key:'m2',label:'v8.2',date:'2026-09-08'}]});
  r.mix_closed=hdr(uniImpBlock(a,b,false)); r.mix_open=uniImpBlock(a,b,true);
  // a plain sessions row whose pooled change (+4%) and paired days' change it was judged on (−6%) differ in sign; an
  // ads/user row judged plain (imp_adj −6.5%, pooled impressions/user −2%)
  const W=b.by_window['30'], ses=W.rows.sessions, arp=W.rows.arpdau;
  Object.assign(ses,{status:'worse',z:-3.3,change:0.04,after:+(ses.before*1.04).toFixed(3),extra:{adj_change:-0.06,all_before:2.0,all_after:2.1}});
  Object.assign(arp,{status:'worse',z:-3.2,change:-0.01,extra:Object.assign({},arp.extra,{imp_adj:-0.065,imp_change:-0.02,ecpm_change:0.01})});
  W.verdict.worse=['sessions','arpdau']; W.verdict.level='hold';
  const hp=uniImpBlock(a,b,true); r.plain=cells(hp); r.plain_mini=uniImpMini(uniImpW(b,30));
  // the young line from the engine's reasons: D30 alone (its own 30 weeks), and no row repeats it under its pill
  const Y=__mkW(b,30,{state:'final'}); Y.rows.new_d30=Object.assign({},Y.rows.new_d30,{status:'low',z:null,noise:null,need:null,
    reason:'Update se pehle ka ~30 hafte ka data chahiye (30-din tulna ka aam utaar-chadhaav napne ke liye) — is update se pehle ~27 hafte ka tha'});
  Y.notes.push('young'); b.by_window['30']=Y; const hy=uniImpBlock(a,b,true); r.young1=hy; r.young1_cells=cells(hy);
  // two rows short with DIFFERENT needs (DAU 26 weeks, D30 its own 30): one line, "kai rows", neither row repeats its own
  Y.rows.returning_dau=Object.assign({},Y.rows.returning_dau,{status:'low',z:null,noise:null,need:null,expected:null,
    reason:'Update se pehle ka ~26 hafte ka data chahiye (30-din tulna ka aam utaar-chadhaav napne ke liye) — is update se pehle ~27 hafte ka tha'});
  const h2=uniImpBlock(a,b,true); r.young2_line=(h2.match(/<div class="faint uni-imp-young">([^<]*)<\\/div>/)||[])[1]||null; r.young2_cells=cells(h2);
  // no row measured at a long window: "Not enough data", never 👍 CONTINUE
  const Z=__mkW(b,30,{state:'final',young:true}); Object.values(Z.rows).forEach(x=>{ if(x.status!=='low'){ Object.assign(x,{status:'na',reason:'GA4 ab itna purana user data nahi rakhta',z:null,noise:null,need:null}); } });
  Z.verdict=Object.assign(Z.verdict,{level:'continue',worse:[],why:'Abhi koi number parkha nahi ja saka (data kam ya nahi) — rollout chalne do'}); b.by_window['30']=Z;
  r.nodata=hdr(uniImpBlock(a,b,false)); r.nodata_young_line=(uniImpBlock(a,b,true).match(/<div class="faint uni-imp-young">([^<]*)<\\/div>/)||[])[1]||null;
  b.by_window['30']=JSON.parse(keep30);
  // one window the engine could not build this run (flags.windows_failed): its button alone disabled
  delete b.by_window['60']; UNIIMPWK={[k]:7}; r.seg_fail=uniImpBlock(a,b,true); r.dau7=cells(uniImpBlock(a,b,true)).returning_dau;
  UNIIMPWK={[k]:30}; r.dau30=cells(uniImpBlock(a,b,true)).returning_dau; r.k=k;
  return JSON.stringify(r); } finally{ ${RESET} } })()`)); } catch (e) { errors.push('win fix: ' + e.message); }
if (S.fix) { S.fix.seg_fail = segOf(S.fix.seg_fail.split('data-open="1"')[1] || ''); S.fix.halt30run_mini = itext((S.fix.halt30run_mini.split('class="uni-imp-mini"')[1] || '').replace(/^[^>]*>/, '')).trim();
  S.fix.young1_line = (S.fix.young1.match(/<div class="faint uni-imp-young">([^<]*)<\/div>/) || [])[1] || null; delete S.fix.young1;
  S.fix.mix_open_hdr = (S.fix.mix_open.split('class="uni-imp-h"')[1] || '').split('</div>')[0];
  S.fix.mix_open_meta = S.fix.mix_open.includes('class="pill p-b uni-mixed"'); delete S.fix.mix_open; }
// "How we compare" at 7 and at the card's 30
try { S.how = JSON.parse(run(`(()=>{ ${RESET} UNIAPP=UNI.apps[0].app_id; APP=UNI.apps[0].app; UNIIMPHOW=true; const h7=uniImpHow(); UNIIMPWIN=30; const h30=uniImpHow(); ${RESET}
  return JSON.stringify({h7, h30}); })()`)); } catch (e) { errors.push('win how: ' + e.message); }
if (S.how) { S.how.t7 = itext(S.how.h7); S.how.t30 = itext(S.how.h30); delete S.how.h7; delete S.how.h30; }

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
  if (/Vs last month ⚪ Normal(?! · (?:installs|[−+]?[\d.]+%))/.test(t)) cohBad.push(a.app + ': plain same');
  for (const x of cs) if (!t.includes((x.dir === 'up' ? '🟡 Watch · installs ' : '🟢 Better · installs ') + run(`uniSpan(${JSON.stringify(x.installs_from)},${JSON.stringify(x.installs_to)})`))) cohBad.push(a.app + ': no alert chip');
}
// every verdict chip's number = the difference of the two numbers its comparison line shows
const gapBad = [];
for (const a of apps) {
  const t = text(run(`uniSumCard(UNI.apps.find(x=>x.app_id===${JSON.stringify(a.app_id)}))`));
  const h = t.match(/(?:🔴 Worse|🟢 Better|⚪ Normal) · [−+]([\d.]+)/), sb = t.match(/— still in app: (?:≈ ?)?([\d.]+)% — (?:pichhle 4|4 purane) pakke hafte ke installs \([^)]*\) · before ([\d.]+)%/);
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
  rel, impact, win, alert_cards: out.alert_cards || '',
  plain_what_changed: (T('portfolio_30d').match(/What changed\? \((\d+)\)/) || [])[1],
  what_changed_counts: (T('portfolio_30d').match(/What changed\? \(\d+\) Each app · (\d+) shown · (\d+) folded below/) || []).slice(1).map(Number),
  portfolio: T('portfolio_30d'),
  has: {
    curve_title: apps.every(a => has(`detail|${a.app}|all|30|cp|false`, '<h3>📉 How many stay</h3><span class="faint" style="font-size:11.5px">every day after install</span>')),
    modes: ['First 30 days', 'First 90 days', 'All days'].every(s => has(A0, s)),
    toggle: has(A0, 'Last 90 days of installs') && has(A0, 'All time (all installs)'),
    no_toggle_young: !has('detail|Demo Notes|all|30|cp|false', 'Last 90 days of installs'),
    what_changed: apps.every(a => has(`detail|${a.app}|all|30|cp|false`, '🔔 What changed? (')),
    all_normal: has('detail|Demo Notes|all|30|cp|false', '✅ All normal — no changes'),
    table_link: has(A0, 'Show full table') && !has(A0, 'Full table — new installs vs before'),
    table_open: has(A0open, '🧮 Full table — new installs vs before') && has(A0open, 'Hide full table'),
    table_cols: ['Days after install', 'Installs: % gone', '4 weeks before', 'All time', 'Change', 'Installs from', 'Status']
      .every(s => has(A0open, '<th>' + s + '</th>')),
    avg4_row: has(A0, '4-week average') && has(A0open, '4-week average')
      && !Object.values(out).some(v => /Pichhle 4 hafte ka average|Sabse naye 4 pakke hafte/.test(v)),
    tri_labels: has(A0, '🔺 Install week × day') && has(A0, '<th>Install week</th>') && has(A0, 'All-time normal') && has(A0, '>Key days</span>') && has(A0, '>Every day</span>')
      && has(`tripages|${apps[0].app}`, '<th style="text-align:center">Install day</th>') && has(`tripages|${apps[0].app}`, '<th style="text-align:center">1 day</th>')
      && has(`tripages|${apps[0].app}`, '<th style="text-align:center">7 days</th>'),
    tri_buttons: has(A0, '>Show all</span>') && has(`detail|${apps[0].app}|recent|all|cp|true`, '>Hide</span>'),
    box_line: has(A0, 'Har box = us hafte install karne walon me se us din tak kitne % ne app hata diya'),
    glance_app: apps.every(a => has(`detail|${a.app}|all|30|cp|false`, '📌 At a glance') && has(`detail|${a.app}|all|30|cp|false`, '>Vs last month<')
      && /<div class="l">Daily uninstall rate(?: · (?:last 7 days|pakke 7 din))?<\/div>/.test(out[`detail|${a.app}|all|30|cp|false`] || '')) && has(A0, '>new users<') && has(A0, '— still in app:') && has(A0, 'of daily active users'),
    daily_title: has(A0, '📊 Daily installs vs uninstalls') && ['30 days', '3 months', 'All time'].every(s => has(A0, '>' + s + '</span>')),
    back_link: has(A0, '<span class="backlnk" onclick="uniBack()">← All apps</span>'),
    portfolio_titles: ['<h2 class="sc">Uninstall</h2><p class="scd smp-top"><b style="color:var(--ink2)">UNINSTALL</b> · Each app (', 'ALL APPS TOGETHER (', '>App status <span>',
      '>Uninstall rate <span>', '🔔 What changed? (', '📋 All apps', '🔌 Apps without GA4 data (5)', '<b>When will I know?</b>']
      .every(s => has('portfolio_30d', s)),
    portfolio_cols: ['Still in app after 7 days', 'Installs', 'Uninstalls', 'Net', 'Uninstall rate', 'Same day uninstall', 'Uninstalled within 1 day', 'Uninstalled within 7 days', 'Uninstalled within 30 days', 'Alerts']
      .every(s => new RegExp('<th onclick="uniSort\\(\'[A-Za-z0-9]+\'\\)"[^>]*>' + s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&') + '( [▲▼])?</th>').test(out.portfolio_30d || '')),
    open_links: has('portfolio_30d', '<span class="lnk">Open →</span>') && has(A0, '>Open →</span>'),
    row_pills: has('portfolio_30d', '<span class="pill p-r smp-w">🔴 Worse</span>') && has('portfolio_30d', '<span class="pill p-y smp-w">🟡 Watch</span>') && has('portfolio_30d', '🟢 Good news ('),
    avg4_says_weeks: has(A0, ' ke installs — har column me yahi installs; · = abhi itne din nahi hue') && !Object.values(out).some(v => v.includes('bade din ke liye purane installs')),
    header_gone: has('portfolio_30d', 'Ek column = ek install hafta: jis app ka us hafte ka data nahi, wahan "—"') && has('portfolio_30d', '<tr class="smp-hw">'),
    decimal_gap: T('verdict_decimal').includes('🔴 Worse · −2.5') && T('verdict_decimal').includes('— still in app: 9.5% — pichhle 4 pakke hafte ke installs')
      && /data-xp="worse"[\s\S]*<span class="x bad">−2\.5<\/span>/.test(out.verdict_decimal || ''),
    s7_arrow_day7_only: !/▲ \d/.test((out.verdict_day3 || '').split('id="uni-table"')[1] || 'x▲ 1') && /▲ 12→16/.test(T('portfolio_30d')),
    s7_no_mixed_arrow: !/\d%\s*▲\d/.test(T('portfolio_30d')),
    tiny_says_it: /data-sd="1" data-sv="[^"]+"/.test(out.tiny_app || '') && (out.tiny_app || '').includes('>Low data</span>') && /title="Low data — sirf [\d.k]+ installs/.test(out.tiny_app || '')
      && !T('tiny_app').includes('~2 hafte ke pakke data ke baad'),
    old_no_verdict: T('no_verdict_old').includes('⏳ Too early') && T('no_verdict_old').includes('kai din ka GA4 data adhoora/gayab') && !T('no_verdict_old').includes('~2 mahine ke data ke baad'),
    unsure_not_same: T('detail|Demo QR Scanner|all|30|cp|false').includes('⚪ Normal · −3% (not sure)') && T('detail|Demo QR Scanner|all|30|cp|false').includes('abhi pakka nahi')
      && !T('detail|Demo QR Scanner|all|30|cp|false').includes('✅ Same as last month'),
    plain_words: !Object.values(out).some(v => /hamesha ka median|\(adhura\)|\b20\d\d-W\d\d\b/.test(text(v))),
    naye_installs_sub: !Object.values(out).some(v => /Naye installs \(\d/.test(text(v))),
    mix_note_all: has('portfolio_30d', 'All apps me har hafte apps ka mix badalta hai — sahi tulna ke liye upar se ek app chuno'),
    no_pooled_triangle: !Object.entries(out).some(([k, v]) => k.startsWith('portfolio') && v.includes('uni-tri-all')),
    mix_note_not_in_app: !has(A0, 'apps ka mix badalta hai'),
    s7_col: has('portfolio_30d', 'Still in app after 7 days'),
    pooled_tiles: has('portfolio_30d', 'id="uni-pool"') && has('portfolio_30d', 'ALL APPS TOGETHER'),
    provisional_tag: has('portfolio_30d', '⏳ Not final ·') && !Object.values(out).some(v => text(v).includes('Provisional')),
    new_tag: !Object.values(out).some(v => />New</.test(v)),
    old_title_gone: !Object.values(out).some(v => v.includes('Har checkpoint') || v.includes('(cumulative)')),
    worse_app: T('verdict_worse').includes('🔴 Worse · −5'),
    // the rate tile names its 7 days in the heading, their dates beside the number, the alert chip before "Not final"
    rate_window: /Daily uninstall rate · last 7 days<\/div><div class="uni-rv">[\d.]+%<small>of daily active users · \d+–\d+ Sep<\/small>/.test(out[`detail|Demo Launcher|all|30|cp|false`] || '')
      && /data-ra="1">⚠️ Spike · 23 Sep<\/span><span class="pill p-b"[^>]*>⏳ Not final</.test(out[`detail|Demo Launcher|all|30|cp|false`] || ''),
    // the full table's 🔍 pill in English (the engine's Hinglish label rewritten from its own parts)
    zoom_pill: has(A0open, '🔍 Alert (19 Sep) — every day till 10 Oct')
      && run(`uniZoomTxt({label:'Naya version 3.2 (10 Sep) — 1 Oct tak har din',reason:'release',until:'2026-10-01'})`) === 'Version 3.2 (10 Sep) — every day till 1 Oct'
      && run(`uniZoomTxt({label:'?',reason:'release',until:'2026-10-01'})`) === 'Every day till 1 Oct — after a new version',
    // "⏱️ When will I know?": one line by default, its points on a tap
    timing_fold: has('portfolio_30d', '⏱️ When will I know? Show') && !has('portfolio_30d', 'din der se aata hai')
      && (out.timing_open || '').split('<hr>').length === 2 && (out.timing_open || '').split('<hr>').every(h => text(h).includes('⏱️ When will I know? Hide') && text(h).includes('GA4 ka data 2 din der se aata hai')),
    fetched_english: /fetched (?:just now|\d+ min ago|\d+ h ago|\d+ days? ago)/.test(T(A0)) || !/fetched /.test(T(A0)),
    events_note: has('detail|Demo Caller – Test App|all|30|cp|false', '≈ 85 old days')
      && !apps.some(a => a.app !== 'Demo Caller – Test App' && /≈ \d+ old day/.test(out[`detail|${a.app}|all|30|cp|false`] || '')),
    incomplete_kept: has('detail|Demo Launcher|all|30|cp|false', '⚠️ Data incomplete · 1 day'),
    // a near-complete day filled up to its exact total: ONE "≈ Estimate" pill (its tooltip: how much came), a ≈ on the
    // numbers it moved; a row the still-incomplete day would empty takes OLDER installs and says so (English label,
    // Hinglish tooltip) — "Data incomplete" stays for that excluded day only
    estimate_pill: has('detail|Demo Launcher|all|30|cp|false', '≈ 1 partial day')
      && has('detail|Demo Launcher|all|30|cp|false', 'is din ka data ~89% aaya tha — total ke hisaab se poora kiya')
      && !apps.some(a => a.app !== 'Demo Launcher' && /≈ \d+ partial day/.test(out[`detail|${a.app}|all|30|cp|false`] || '')),
    estimate_cells: ['detail|Demo Launcher|all|90|all|true', 'detail|Demo Launcher|all|30|cp|false'].every(k => has(k, '<span class="uni-est"'))
      && has('detail|Demo Launcher|all|90|all|true', 'is din (20 Aug) ka data ~89% aaya tha — total ke hisaab se poora kiya')
      && !apps.some(a => a.app !== 'Demo Launcher' && has(`detail|${a.app}|all|90|all|true`, 'class="uni-est"')),
    older_installs: has('detail|Demo Launcher|all|90|all|true', '↩ Older installs · 3 Sep: data incomplete')
      && has('detail|Demo Launcher|all|90|all|true', 'purane installs liye — 3 Sep ka data adhoora')
      && has('detail|Demo Launcher|all|90|all|true', '↩ 4 weeks before: older installs · 3 Sep: data incomplete'),
      // (the portfolio's D cells: one column = one install week now — SPEC_SIMPLIFY §6.2 — a cell of another week is "—")
    worse_portfolio: (() => { const p = (out.verdict_worse || '').split('<hr>');
      return p.length === 3 && /data-k="worse"[^>]*><i class="dt"><\/i>🔴 Worse <b>\(1\)<\/b>/.test(p[1]) && !/data-xp="/.test(p[1])
        && /data-xp="worse"/.test(p[2]) && text(p[2].split('data-xp="worse"')[1] || '').includes(apps[0].app + ' −5'); })(),
  },
}, null, 1));
