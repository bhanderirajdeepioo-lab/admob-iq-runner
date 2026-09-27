// The Install value tab's frontend contract: runs the REAL dashboard script (frontend/index.html's <script>) in a node vm
// with stub browser globals, feeds it the committed fixture (tests/fixtures/value_sample.json — dashboard["value"] plus
// every app's value_<key>.json.gz detail; all synthetic) and renders every Install value state: the All-apps page (every
// sort, every status chip opened, phone and desktop), each app's page in every table / sort / fold mode, the Alerts-screen
// section, $ and ₹, and made-up states the fixture may not hold (red without an alert, country weeks not clean, country
// cost on, a 180-day target, "Over 1 year"). Prints one JSON report; tests/test_value_frontend.py asserts on it.
// usage: node value_frontend.js <script.js> <value_fixture.json>
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
// the fixture: {dashboard_value, app_files: {<key> | value_<key>.json.gz: detail}} (a {dashboard: {value}} / {value} top works too)
const FX = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const DV = FX.dashboard_value || (FX.dashboard && FX.dashboard.value) || FX.value;
const FILES = {};
for (const [k, v] of Object.entries(FX.app_files || FX.files || {})) FILES[(k.match(/^value_([0-9a-f]+)\.json(\.gz)?$/) || [])[1] || k] = v;
const add = (s, n) => new Date(Date.parse(s + 'T00:00:00Z') + n * 864e5).toISOString().slice(0, 10);
const TODAY = FX.today_date || (DV.settled_till_max ? add(DV.settled_till_max, 5) : '2026-09-25');
ctx.__DV = DV; ctx.__FILES = FILES;
run(`DATA = {apps_catalog: [], today_date: ${JSON.stringify(TODAY)}, currency: 'USD', usd_inr: 84, alerts: {counts: {}, items: []}, value: __DV};
     VALD = {}; for (const [k, d] of Object.entries(__FILES)) VALD[k] = d;`);
const out = {};
function scen(name, code) { try { out[name] = String(run(code)); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 4).join(' < ')); } }
const RESET = `APP=''; VALAPP=''; innerWidth=375; CURVIEW=null; RANGE='30d'; VALWK='12'; VALSORT='n'; VALCM='d1'; VALCTYEXP=''; VALOLDEXP=false; VALCLEXP=false;
  VALTILEEXP=''; VALSTEXP=''; VALPSORT={k:'status',d:1}; VALTIMEXP=false; VALCHKEXP=false; VALJUMP=''; VALERR={}; VALL={};`;
const rows = DV.apps || [], J = JSON.stringify;
const det = r => FILES[r.key] || null;
const openApp = r => `VALAPP=${J(r.app_id)}; APP=${J(r.app)};`;

// ── All apps ──
scen('portfolio', `${RESET} valScreen()`);
scen('portfolio_desktop', `${RESET} innerWidth=1280; valScreen()`);
scen('portfolio_inr', `${RESET} CURVIEW='INR'; valScreen()`);
scen('portfolio_timing', `${RESET} VALTIMEXP=true; valScreen()`);
scen('portfolio_nofiles', `${RESET} (()=>{ const keep=VALD; VALD={}; try{ return valScreen(); } finally{ VALD=keep; } })()`);
const PSORTS = ['app', 'spend', 'cpi', 'b7', 'b30', 'pay', 'status'];
for (const k of PSORTS) for (const d of [1, -1]) scen(`psort|${k}|${d}`, `${RESET} VALPSORT={k:'${k}',d:${d}}; valPortfolio()`);
const STRIP_ST = {};
for (const k of ['pay', 'cpi', 'cty']) for (const st of [...new Set(rows.map(r => String(run(`valRowSt(${J(r)},'${k}')`))))]) {
  STRIP_ST[k + ':' + st] = true; scen('xp|' + k + ':' + st, `${RESET} VALSTEXP='${k}:${st}'; valScreen()`); }
scen('no_value', `${RESET} (()=>{ const k=DATA.value; delete DATA.value; try{ return valScreen(); } finally{ DATA.value=k; } })()`);
// a payload of the wrong shape: the tab still renders (renderValue never throws) and no alert is invented
scen('bad_payload', `${RESET} (()=>{ const k=DATA.value; DATA.value={apps:'x', alerts:7, consts:'y'}; let ok=true, h=''; try{ renderValue(); }catch(e){ ok=false; }
  try{ h=valScreen(); }catch(e){ h='THREW'; } try{ return h+'<hr>'+ok+'<hr>'+valAlertsFor().length; } finally{ DATA.value=k; } })()`);
const r0 = rows.find(r => det(r)) || rows[0];
scen('file_error', `${RESET} ${openApp(r0)} (()=>{ const k=VALD[${J(r0.key)}]; delete VALD[${J(r0.key)}]; VALERR[${J(r0.key)}]=true; try{ return valScreen(); } finally{ VALD[${J(r0.key)}]=k; VALERR={}; } })()`);
scen('file_loading', `${RESET} ${openApp(r0)} (()=>{ const k=VALD[${J(r0.key)}]; delete VALD[${J(r0.key)}]; try{ return valScreen(); } finally{ VALD[${J(r0.key)}]=k; VALL={}; } })()`);
scen('row_error', `${RESET} ${openApp(r0)} (()=>{ const k=DATA.value.apps.find(x=>x.key===${J(r0.key)}), keep=JSON.stringify(k); k.status='error';
  try{ return valScreen()+'<hr>'+(()=>{ APP=''; return valPortfolio(); })(); } finally{ Object.assign(k,JSON.parse(keep)); } })()`);
for (const n of DV.no_ga4 || []) scen('noga4|' + n.app, `${RESET} APP=${J(n.app)}; valScreen()`);
// an app whose install-day data has not arrived yet (the build's waiting row: no file, no numbers) — its page and the All-apps page
const WAIT_ROW = { app_id: 'ca-app-pub-0000000000000000~9', app: 'Waiting Demo', key: '000000000009', file: null, sig: null, status: 'wait', settled_till: null,
  iday: { from: null, to: null, cfrom: null, state: 'wait', pct: 0 }, pay: null, rpi: null, cpi: null, cty: null, alerts: { warning: 0, watch: 0, good: 0 },
  summary: { kind: 'wait', text: '⏳ Install-wise kamai ka data aa raha — agle fetch me.' }, s: { spend4: null, n4: null, rev7_4: null, rev30_4: null, n30_4: null, spend30_4: null } };
ctx.__WR = WAIT_ROW;
scen('wait_row', `${RESET} (()=>{ DATA.value.apps.push(__WR); try{ APP='Waiting Demo'; const a=valScreen(); APP=''; return a+'<hr>'+valScreen(); } finally{ DATA.value.apps.pop(); } })()`);
scen('noga4|unknown', `${RESET} APP='Some Other App'; valScreen()`);

// ── each app ──
const MODES = [['base', ''], ['desktop', 'innerWidth=1280;'], ['wk26', `VALWK='26';`], ['wkall', `VALWK='all'; innerWidth=1280;`], ['inr', `CURVIEW='INR';`],
  ['sort_d1', `valSort('d1');`], ['sort_d7_desk', `innerWidth=1280; valSort('d7');`], ['sort_d30', `valSort('d30');`], ['sort_rpi_desk', `innerWidth=1280; valSort('rpi');`],
  ['folds', `VALOLDEXP=true; VALCLEXP=true; VALCHKEXP=true; VALTIMEXP=true;`], ['folds_desk', `innerWidth=1280; VALOLDEXP=true; VALCLEXP=true; VALCHKEXP=true; VALTIMEXP=true;`],
  ['tile_open', `VALTILEEXP='pay';`]];
// valSort / valWK re-render through the page; in the vm that is a no-op, the state is what matters
for (const r of rows) {
  if (!det(r)) continue;
  for (const [m, set] of MODES) scen(`detail|${r.app}|${m}`, `${RESET} ${openApp(r)} ${set} valScreen()`);
  const C = (det(r).countries || {}), cc = ((C.rows || [])[0] || {}).cc;
  if (cc) { scen(`detail|${r.app}|cty_open`, `${RESET} ${openApp(r)} VALCTYEXP=${J(cc)}; valScreen()`);
    scen(`detail|${r.app}|cty_open_desk`, `${RESET} ${openApp(r)} innerWidth=1280; VALCTYEXP=${J(cc)}; valScreen()`); }
}

// ── ids: every id in this tab starts with val- and none repeats on a screen ──
const ids = [];
const idsOf = h => [...h.matchAll(/\sid="([^"]*)"/g)].map(m => m[1]);
for (const [k, v] of Object.entries(out)) {
  if (!(k.startsWith('detail|') || k.startsWith('portfolio') || k === 'no_value')) continue;
  const l = idsOf(v), dup = l.filter((x, i) => l.indexOf(x) !== i);
  ids.push({ scen: k, n: l.length, dup: [...new Set(dup)], bad: l.filter(x => !x.startsWith('val-')) });
}

// ── the header follows the open app (valOpen → setApp), "← All apps" clears it; an Alerts card's "Open app →" (render / show stubbed) ──
let header = null, gofrom = null;
try { header = JSON.parse(run(`(()=>{ const keep={render, show, _navSave}, calls=[]; render=function(){ calls.push('render'); }; show=function(id){ calls.push('show:'+id); }; _navSave=function(){};
  try{ ${RESET} const r=DATA.value.apps[0]; valOpen(r.app_id); const o={name:r.app, app:APP, valapp:VALAPP, sel:appSelHtml(), calls:calls.slice(), screen:valScreen().slice(0,1200)};
    valBack(); o.after={app:APP, valapp:VALAPP, screen:valScreen().slice(0,400)}; return JSON.stringify(o); }
  finally{ render=keep.render; show=keep.show; _navSave=keep._navSave; } })()`)); } catch (e) { errors.push('header: ' + e.message); }
try { gofrom = JSON.parse(run(`(()=>{ const keep={render, show, _navSave}, calls=[]; render=function(){}; show=function(id){ calls.push(id); }; _navSave=function(){};
  try{ ${RESET} const r=DATA.value.apps[0]; valGo(r.app_id); return JSON.stringify({calls, app:APP, want:r.app, jump:VALJUMP}); }
  finally{ render=keep.render; show=keep.show; _navSave=keep._navSave; VALJUMP=''; } })()`)); } catch (e) { errors.push('valGo: ' + e.message); }

// ── the Alerts screen: the Install value section (App filter), nothing at all when there are no value alerts ──
const alertsScen = (nm, pre, post) => scen(nm, `${RESET} (()=>{ const keep=screenDiv, kv=DATA.value, ka=(DATA.value||{}).alerts; screenDiv=id=>({dataset:{screen:id},innerHTML:''});
  try{ ${pre} return renderAlerts().innerHTML; } finally { screenDiv=keep; APP=''; DATA.value=kv; if(kv) kv.alerts=ka; } })()`);
alertsScen('alerts_all', `APP='';`);
for (const r of rows) alertsScen('alerts|' + r.app, `APP=${J(r.app)};`);
alertsScen('alerts_absent', `delete DATA.value;`);
alertsScen('alerts_empty', `DATA.value.alerts=[];`);
alertsScen('alerts_bad', `DATA.value.alerts='x';`);
scen('alert_cards', `${RESET} valAlertCards(valAlertsFor())`);

// ── made-up states (a copy of one app's detail, changed, rendered, restored) ──
const synth = (nm, r, change, what) => scen(nm, `${RESET} (()=>{ const K=${J(r.key)}, keep=VALD[K], d=JSON.parse(JSON.stringify(keep)), V=DATA.value, row=V.apps.find(x=>x.key===K), rk=JSON.stringify(row), ka=V.alerts;
  ${change} VALD[K]=d; try{ ${openApp(r)} ${what || 'return valScreen();'} } finally{ VALD[K]=keep; Object.assign(row, JSON.parse(rk)); V.alerts=ka; } })()`);
const judgedRow = x => x && x.clean !== false && !['wait', 'few'].includes(x.verdict);
const withCty = rows.find(r => det(r) && ((det(r).countries || {}).rows || []).some(judgedRow)) || rows.find(r => det(r) && ((det(r).countries || {}).rows || []).length) || r0;
const withPaid = rows.find(r => det(r) && (det(r).weeks || []).some(w => w.judged)) || r0;
// a tile / country says worse / watch / better with NO open alert (never from the engine): shown blue, never red / yellow / green
synth('no_red', withPaid, `for(const k of ['pay','b7','cpi']) d.tiles[k]=Object.assign({},d.tiles[k],{st:k==='cpi'?'better':(k==='b7'?'watch':'worse')}); d.changes=Object.assign({},d.changes,{open:[]}); V.alerts=[];
  row.pay=Object.assign({},row.pay,{st:'worse'}); row.cpi=Object.assign({},row.cpi,{st:'better'});`, `return valSumCard(d,row)+'<hr>'+valCtyCard(d,row)+'<hr>'+(()=>{ APP=''; VALSTEXP='pay:worse'; return valPortfolio(); })();`);
// the same with an open warning: red is allowed (and only then)
synth('warn', withPaid, `d.tiles.pay=Object.assign({},d.tiles.pay,{st:'worse'}); const a=Object.assign({},(d.changes.open||[])[0]||{},{family:'pay_slow',metric:'b7',severity:'warning',dir:'down',app_id:d.app_id,app:d.app,cc:null,text:'Ads ka paisa wapas aane me der',closed:null});
  d.changes=Object.assign({},d.changes,{open:[a]});`, `return valSumCard(d,row)+'<hr>'+valChangesCard(d);`);
// every country week not clean: values ≈, verdict "Wait" (blue), never judged
synth('unclean', withCty, `d.countries.rows=d.countries.rows.map(x=>Object.assign({},x,{clean:false,verdict:'wait'}));`, `innerWidth=1280; return valCtyCard(d,row)+'<hr>'+(()=>{ innerWidth=375; return valCtyCard(d,row); })();`);
// country cost switched on: CPI + Money back columns, the Keep / Slow / Costly strip
synth('geo', withCty, `d.countries.geo=true; const V3=['keep','slow','costly']; d.countries.rows=d.countries.rows.map((x,i)=>x.few?x:Object.assign({},x,{clean:true,verdict:V3[i%3],cpi:{v:0.02+i*0.002,ads:0.023+i*0.002,spend:120+i},pay:{p:40+i*20,lo:30,hi:90}}));`,
  `innerWidth=1280; VALCTYEXP=d.countries.rows[0].cc; return valCtyCard(d,row);`);
// a 180-day target: the country earning shows the ≈180-day value
synth('h180', withCty, `d.horizon=180;`, `innerWidth=1280; return valCtyCard(d,row)+'<hr>'+valDetail(row,d).slice(0,3000);`);
// the newest judged week never pays back in a year
synth('never', withPaid, `d.tiles.pay=Object.assign({},d.tiles.pay,{st:'never',v:null,never:true,pct365:62,obs:false}); const w=d.weeks.find(x=>x.judged&&x.pay); if(w) w.pay={p:null,lo:null,hi:null,obs:false,never:true,pct365:62};
  d.changes=Object.assign({},d.changes,{open:[]}); V.alerts=[];`, `innerWidth=1280; return valSumCard(d,row)+'<hr>'+valPayCard(d,row);`);
// a sampled app / a gap in the country split
synth('smp', withCty, `d.countries.smp=true; d.countries.unassigned={n:900,rev_share:0.034};`, `innerWidth=1280; return valCtyCard(d,row);`);
// no countries yet / too few installs in every country
synth('cty_wait', withCty, `d.countries={win:null,rows:[]};`, `return valCtyCard(d,row);`);
synth('cty_low', withCty, `d.countries=Object.assign({},d.countries,{rows:[]});`, `return valCtyCard(d,row);`);
// an app with no weeks yet
synth('no_weeks', withPaid, `d.weeks=[];`, `return valPayCard(d,row);`);
// what a paid app can also hold: a release (📦 row + "After v1.4" chip → Active users' Update impact), a short GA4 day (≈),
// a week scaled with an out-of-range k (≈), a thin week and a week without ads, in-app purchases, closed and older changes
const WP = (det(withPaid).weeks || []).filter(w => w.judged).sort((p, q) => (p.from < q.from ? 1 : -1)), REL_FROM = (WP[1] || WP[0] || {}).from;
synth('extras', withPaid, `const W=d.weeks.filter(w=>w.judged).sort((p,q)=>p.from<q.from?1:-1), w1=W[1]||W[0], w2=W[2]||W[0], w3=W[3]||W[0], w4=W[4]||W[0], w5=W[5]||W[0];
  w1.release={date:w1.from,version:'1.4',kind:'ver'};
  const shown=j=>[1,3,5,7,9].includes(j);   // the table's columns (1 day · 1 week · 30 days · 90 days · 1 year)
  const jq=(w2.L||[]).findIndex((v,j)=>v!=null&&shown(j)); if(jq>=0) w2.Lq=w2.L.map((v,j)=>j===jq);
  const je=(w3.L||[]).findIndex((v,j)=>v!=null&&shown(j)); if(je>=0){ w3.est=w3.L.map((v,j)=>j===je); w3.Lq=w3.L.map(()=>false); }
  Object.assign(w4,{judged:false,why:'thin',pay:null,spend:12}); Object.assign(w5,{judged:false,why:'nospend',pay:null,spend:0});
  d.weeks.forEach(w=>{ if(Array.isArray(w.rpi)) w.iap=w.rpi.map(v=>v==null?null:v*0.012); });
  const a0=Object.assign({family:'pay_slow',metric:'b7',severity:'watch',dir:'down',text:'Ads ka paisa wapas aane me der'},(d.changes.open||[])[0]||{},{app_id:d.app_id,app:d.app});
  d.changes=Object.assign({},d.changes,{open:[Object.assign({},a0,{release:{key:'ver:1.4@'+w1.from,label:'v1.4',date:w1.from}})],closed:[Object.assign({},a0,{closed:'2026-06-01',fresh:false})],
    older:[{kind:'spend',from:'2025-11-03',to:'2025-11-16',text:'3 Nov 2025 se Google Ads kharcha badha'}]});`,
  `innerWidth=1280; VALWK='all'; VALOLDEXP=true; VALCLEXP=true; return valChangesCard(d)+'<hr>'+valPayCard(d,row);`);
// a fold that throws renders its own small notice, the rest of the page stays
synth('broken_part', withPaid, `Object.defineProperty(d,'countries',{get(){ throw new Error('boom'); }});`);
// wrong shapes inside one app's file: the page still renders, unknown stays "—"
synth('odd_shapes', withPaid, `d.countries={rows:{bad:1},win:{from:'2026-08-17'}}; d.weeks='x'; d.tiles={pay:7}; d.scale=null; d.iday=[]; d.changes={open:'x'};`);

// ── review fixes: tokens, the ₹ the ads billed, one 4-week window, honest waits and ranges ──
const withW = rows.find(r => det(r) && (det(r).weeks || []).some(w => w.judged && w.spend_src != null)) || withPaid;
// a Google Ads week not in yet (spend unknown) next to one known to have none: "aa raha" vs "No ads"
synth('spend_wait', withW, `const W=d.weeks.filter(w=>w.judged).sort((p,q)=>p.from<q.from?1:-1), a=W[0], b=W[1]||W[0];
  Object.assign(a,{judged:false,why:'wait',spend:null,spend_src:null,ecpi:null,ecpi_src:null,pay:null,L:a.L.map(()=>null),Lp:a.Lp.map(()=>null)});
  Object.assign(b,{judged:false,why:'nospend',spend:0,spend_src:0,ecpi:null,pay:null,L:b.L.map(()=>null),Lp:b.Lp.map(()=>null)});
  globalThis.__SW=[a.from,b.from];`, `innerWidth=1280; return valPayCard(d,row);`);
// the context line over the weeks the window really has (3 here), and the ₹ the ads billed
synth('ctx3', withW, `d.tiles.cpi=Object.assign({},d.tiles.cpi,{v:0.1,v_src:8.4,spend4:300,spend4_src:25200,n4:3000,nw:3,ads:0.115,ads_src:9.66,paid_share:0.87});`,
  `return valSumCard(d,row)+'<hr>'+(()=>{ CURVIEW='INR'; const h=valSumCard(d,row); CURVIEW=null; return h; })();`);
// the "Back in 7 days" tile: its 30-day value is the SAME week's (≈ while projected); ≈ on the 7-day number when scaled ≈
synth('b7same', withPaid, `d.tiles.b7=Object.assign({},d.tiles.b7,{v:23,v30:50,v30_est:true,est:true,st:'normal'});`, `return valSumCard(d,row);`);
// a projected payback whose range rounds to one day: no "(46–46)"; its range stays under the number on a phone
synth('zerow', withPaid, `d.tiles.pay=Object.assign({},d.tiles.pay,{v:46,lo:46,hi:46,obs:false,never:false,st:'normal',rough:false,shape:null});`, `return valSumCard(d,row);`);
synth('rangeph', withPaid, `d.tiles.pay=Object.assign({},d.tiles.pay,{v:109,lo:107,hi:112,obs:false,never:false,st:'normal',rough:false,shape:null});`, `return valSumCard(d,row);`);
// the wait sub-line says WHY (the engine's note), and it draws its money tokens
synth('waitnote', withPaid, `d.tiles.pay={st:'wait',why:'curve',note:'abhi andaza nahi (curve ke liye is app ke 6 aise hafte chahiye jinke 180 din pure ho chuke) · pichhla pata: kamai {m:0.0123}'};`, `return valSumCard(d,row);`);
// the Data check when the mediation report was not read: the build's own lines, and the tooltip says "sirf AdMob network"
synth('network', withPaid, `d.scale=Object.assign({},d.scale,{src:'network',text:['✅ GA4 aur AdMob ki kamai mel khati (±10%)','AdMob ki kamai sirf AdMob network se (mediation ke baaki networks nahi) — isliye thodi kam dikh sakti','GA4 din property ke time me, AdMob / Google Ads India time me — hafte me milaya']});`,
  `VALCHKEXP=true; return valSumCard(d,row)+'<hr>'+valChkCard(d);`);
// countries: nothing judged / a Top verdict not (yet) on the Best list / few-install rows sorted after the judged ones
synth('strip_none', withCty, `d.countries.best=[]; d.countries.weak=[]; d.countries.rows=d.countries.rows.map(x=>Object.assign({},x,{verdict:x.few?'few':'wait',why:'young'}));`, `innerWidth=1280; return valCtyCard(d,row);`);
synth('strip_unranked', withCty, `d.countries.best=[]; d.countries.weak=[]; const R=d.countries.rows.filter(x=>!x.few); if(R[0]) R[0].verdict='top'; if(R[1]) R[1].verdict='low'; d.countries.rows.forEach(x=>{ if(x.clean===false) x.clean=true; });`, `innerWidth=1280; return valCtyCard(d,row);`);
synth('few_sort', withCty, `const J=d.countries.rows.filter(x=>!x.few); const F=Object.assign({},J[J.length-1],{cc:'KE',n:120,few:true,verdict:'few',rank:null,clean:true,rpi:{'1':{v:5},'7':{v:6},'30':{v:9},'90':null},d1:{v:99},d7:{v:98},d30:{v:97}}); d.countries.rows=d.countries.rows.concat([F]);`,
  `innerWidth=1280; VALSORT='rpi'; const a=valCtyCard(d,row); VALSORT='d1'; const b=valCtyCard(d,row); VALSORT='n'; return a+'<hr>'+b;`);
// All apps while every app is still waiting: never "All normal" / "0 apps slow"
scen('all_waiting', `${RESET} (()=>{ const keep=JSON.stringify(DATA.value.apps); DATA.value.apps.forEach(r=>{ r.summary={kind:'wait',text:'⏳ data aa raha'}; }); const ka=DATA.value.alerts; DATA.value.alerts=[];
  try{ return valPortfolio(); } finally{ DATA.value.apps=JSON.parse(keep); DATA.value.alerts=ka; } })()`);
// ── what the page says ──
const text = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&quot;/g, '"').replace(/\s+/g, ' ');
const uiText = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/\sid="[^"]*"/g, '');
const bad = [], jargon = [], devanagari = [];
const JARGON = /cumulative|checkpoint|cohort|bharosa|headline|\bLTV\b/i, DEVA = /[ऀ-ॿ]/;
for (const [k, v] of Object.entries(out)) {
  for (const w of ['undefined', 'NaN', '[object Object]', 'Infinity']) if (v.includes(w)) bad.push(k + ': ' + w);
  const m = uiText(v).match(JARGON); if (m) jargon.push(k + ': ' + m[0] + ' …' + uiText(v).slice(Math.max(0, m.index - 80), m.index + 30));
  if (DEVA.test(v)) devanagari.push(k);
}
const sec = (h, a, b) => (h.split(a)[1] || '').split(b)[0];
const T = k => text(out[k] || '');
const tokRe = /\{(m|b|s|q|p|cc|c)(:[^{}]*)?\}/;
const fix = {
  tokens: Object.entries(out).filter(([k, v]) => tokRe.test(text(v))).map(([k]) => k),
  spend_wait: (() => { const h = out.spend_wait || '', sw = run('JSON.stringify(globalThis.__SW||[])'); const [a, b] = JSON.parse(sw);
    const row = f => (h.match(new RegExp(`<tr data-week="${f}">([\\s\\S]*?)</tr>`)) || [])[1] || '';
    return { wait: text(row(a)), none: text(row(b)) }; })(),
  ctx3: text(sec(out.ctx3 || '', 'id="val-ctx"', '</div>')), ctx3_inr: text(sec((out.ctx3 || '').split('<hr>')[1] || '', 'id="val-ctx"', '</div>')),
  cpi3_inr: text(sec((out.ctx3 || '').split('<hr>')[1] || '', 'data-m="cpi"', 'data-m="cty"')),
  b7same: text(sec(out.b7same || '', 'data-m="b7"', 'data-m="rpi"')), zerow: text(sec(out.zerow || '', 'data-m="pay"', 'data-m="b7"')),
  rangeph: (sec(out.rangeph || '', 'data-m="pay"', 'data-m="b7"').match(/<small class="val-rgb">([^<]*)<\/small>/) || [])[1] || '',
  waitnote: text(sec(out.waitnote || '', 'data-m="pay"', 'data-m="b7"')),
  network: { chk: text((out.network || '').split('<hr>')[1] || ''), tip: /data-m="rpi"[^>]*><div class="l" title="[^"]*sirf AdMob network/.test(out.network || '') },
  strip_none: text(sec(out.strip_none || '', 'id="val-cstrip">', '</div>')), strip_unranked: text(sec(out.strip_unranked || '', 'id="val-cstrip">', '</div>')),
  few_sort: (out.few_sort || '').split('<hr>').map(h => [...sec(h, 'id="val-ctbl"', '</tbody>').matchAll(/<tr class="clk" data-cc="([^"]*)"/g)].map(m => m[1])),
  all_waiting: { count: text(sec(out.all_waiting || '', 'id="val-count">', '</div>')), chg: text(sec(out.all_waiting || '', 'id="val-chg"', 'id="val-table"')) },
  spendfmt: JSON.parse(run(`(()=>{ ${RESET} const a=[valSpendBig(100,8000,'INR'),valSpendMoney(0.06,5.07,'INR'),valSpendBig(100,null,'INR')]; CURVIEW='INR'; const b=[valSpendBig(100,8000,'INR'),valSpendMoney(0.06,5.07,'INR'),valSpendBig(100,null,'INR'),valSpendBig(100,8000,'USD')]; CURVIEW=null;
    const t=[valTxt('a {m:0.0042} b {q:0.06|5.07} c {s:1335|111000} d {p:0.04} e {c}100 f {cc:NG} g {b:20}')]; CURVIEW='INR'; t.push(valTxt('c {s:1335|111000} q {q:0.06|5.07}')); CURVIEW=null; return JSON.stringify({a,b,t}); })()`)),
  paytd: text(run(`valPayTd({p:109,lo:107,hi:112,obs:false,never:false,from:'2026-08-31',to:'2026-09-06'})`)),
};

// numbers never coloured: no red / green text colour, no up / down classes anywhere in the tab's own screens
const COLOR_RE = /var\(--bad\)|var\(--good\)|class="(up|down)"|#ff6b6b|#34d99a|rgba\(255,107,107|rgba\(52,217,154/;
const coloured = Object.entries(out).filter(([k, v]) => !k.startsWith('alert') && COLOR_RE.test(v)).map(([k]) => k);
// every red / green / yellow pill on the tab: its state and whether an alert backs it
const pills = h => [...h.matchAll(/<span class="pill (p-r|p-g|p-y)" data-st="([a-z_]+)"/g)].map(m => [m[1], m[2]]);
const apps = {};
for (const r of rows) {
  const d = det(r); if (!d) continue;
  const h = out[`detail|${r.app}|base`] || '', hd = out[`detail|${r.app}|desktop`] || '', f = out[`detail|${r.app}|folds_desk`] || '';
  const sum = sec(h, 'id="val-sum"', 'id="val-chg"');
  const tiles = [...sum.matchAll(/<div class="uni-st val-t[^"]*" data-m="([a-z0-9_]+)" data-st="([a-z_]+)"[\s\S]*?(?=<div class="uni-st val-t|<\/div><div class="uni-meta"|$)/g)].map(m => {
    const t = m[0], ch = t.match(/<span class="pill ([a-z0-9-]+)" data-st="([a-z_]+)" title="[^"]*">([^<]*)<\/span>/);
    return { m: m[1], st: m[2], cls: ch ? ch[1] : null, chip: ch ? ch[3] : null, big: text((t.match(/<div class="v[^"]*">([\s\S]*?)<\/div>/) || [])[1] || '').trim(),
      span: text((t.match(/<div class="c val-dt">([\s\S]*?)<\/div>/) || [])[1] || '').trim(), sub: text((t.match(/<div class="val-sl">([\s\S]*?)<\/div>/) || [])[1] || '').trim() }; });
  const pay = sec(h, 'id="val-pay"', 'id="val-cty"'), payD = sec(hd, 'id="val-pay"', 'id="val-cty"'), payAll = sec(out[`detail|${r.app}|wkall`] || '', 'id="val-pay"', 'id="val-cty"');
  const heads = s => [...sec(s, '<thead>', '</thead>').matchAll(/<th[^>]*>([^<]*)/g)].map(m => m[1]);
  const cells = s => [...s.matchAll(/<td class="uni-num[^"]*"([^>]*)>([\s\S]*?)<\/td>/g)].map(m => ({ a: m[1], t: text(m[2]).trim() }));
  const ctyD = sec(hd, 'id="val-cty"', 'id="val-chk"'), ctyP = sec(h, 'id="val-cty"', 'id="val-chk"');
  const chk = sec(f, 'id="val-chk"', 'id="val-timing"');
  apps[r.app] = { key: r.key, header: text(h.slice(0, 1600)).slice(0, 400),
    sections: ['val-sum', 'val-chg', 'val-pay', 'val-cty', 'val-chk', 'val-timing'].map(s => h.indexOf('id="' + s + '"')),
    titles: ['📌 At a glance', '🔔 What changed? (', '💸 Money back by install week', '🌍 Countries', 'Data check', 'When will I know?', '← All apps', 'Target: paisa'].filter(x => T(`detail|${r.app}|base`).includes(x)),
    tiles, tile_open: /class="uni-st val-t open" data-m="pay"/.test(out[`detail|${r.app}|tile_open`] || ''),
    summary: (sum.match(/<div class="val-line" data-kind="([^"]*)">([^<]*)<\/div>/) || []).slice(1), ctx: text(sec(sum, 'id="val-ctx"', '</div>')).replace(/^[^>]*>/, '').trim(),
    data_line: text(sec(sum, 'id="val-data"', '</div>')).replace(/^[^>]*>/, '').trim(),
    chg_title: (h.match(/🔔 What changed\? \((\d+)\)/) || [])[1], chg_rows: [...sec(h, 'id="val-chg"', 'id="val-pay"').matchAll(/<div class="uni-chg na" data-fam="([^"]*)"/g)].map(m => m[1]),
    all_normal: h.includes('✅ All normal — no changes'), info_rows: [...sec(h, 'id="val-chg"', 'id="val-pay"').matchAll(/data-info="([^"]*)"/g)].map(m => m[1]),
    closed_rows: (sec(f, 'id="val-chg"', 'id="val-pay"').match(/<div class="uni-chg na cl"/g) || []).length, older_rows: (sec(f, 'id="val-chg"', 'id="val-pay"').match(/data-old="/g) || []).length,
    rel_chips: [...sec(h, 'id="val-chg"', 'id="val-pay"').matchAll(/onclick="event\.stopPropagation\(\);uniImpGo\('([^']*)','([^']*)','act'\)">After ([^<]*)</g)].map(m => [m[1], m[2], m[3]]),
    pay: { heads_phone: heads(pay), heads_desk: heads(payD), weeks_12: (pay.match(/<tr data-week="/g) || []).length, weeks_all: (payAll.match(/<tr data-week="/g) || []).length,
      imm: cells(payD).filter(c => /data-imm="1"/.test(c.a)).map(c => c.t), proj: cells(payD).filter(c => /data-proj="1"/.test(c.a)).map(c => c.t),
      proj_cls: (payD.match(/<td class="uni-num val-proj" data-proj="1"/g) || []).length, q: cells(payAll).filter(c => /data-q="1"/.test(c.a)).map(c => c.t),
      rel_rows: [...payAll.matchAll(/<tr class="uni-rel"><td class="nm">([\s\S]*?)<\/td>/g)].map(m => text(m[1]).trim()),
      rel_calls: [...payAll.matchAll(/onclick="uniImpGo\('([^']*)','([^']*)','act'\)"/g)].map(m => [m[1], m[2]]),
      chart: /id="val-curve"/.test(pay), chart_ph: (sec(pay, 'id="val-curve"', '</svg>').match(/data-ph="(\d)"/) || [])[1],
      chart_x_phone: [...sec(pay, 'id="val-curve"', '</svg>').matchAll(/<text x="[^"]*" y="[^"]*" text-anchor="middle" font-size="11" fill="#8496b5">([^<]*)<\/text>/g)].map(m => m[1]),
      chart_x_desk: [...sec(payD, 'id="val-curve"', '</svg>').matchAll(/<text x="[^"]*" y="[^"]*" text-anchor="middle" font-size="12.5" fill="#8496b5">([^<]*)<\/text>/g)].map(m => m[1]),
      line100: sec(payD, 'id="val-curve"', '</svg>').includes('>Paisa wapas</text>'), caption: T(`detail|${r.app}|desktop`).includes('Line 100 ke upar gayi = ads ka poora paisa wapas.'),
      foot: text(sec(payD, 'id="val-payfoot"', '</div></div>')).replace(/^[^>]*>/, '').trim(),
      money_back: [...payD.matchAll(/<tr data-week="[^"]*">[\s\S]*?<\/tr>/g)].map(m => text((m[0].match(/<td[^>]*>((?:(?!<td)[\s\S])*?)<\/td><\/tr>$/) || [])[1] || '').trim()),
      inr: sec(out[`detail|${r.app}|inr`] || '', 'id="val-pay"', 'id="val-cty"').includes('₹') },
    cty: { cards: ctyP.includes('id="val-ccards"'), table_phone: ctyP.includes('id="val-ctbl"'), table_desk: ctyD.includes('id="val-ctbl"'), cards_desk: ctyD.includes('id="val-ccards"'),
      rows_desk: [...ctyD.matchAll(/<tr class="clk" data-cc="([^"]*)"/g)].map(m => m[1]), rows_phone: [...ctyP.matchAll(/<div class="val-cc[^"]*" data-cc="([^"]*)" onclick/g)].map(m => m[1]),
      all_row: ctyD.includes('<tr class="val-all"'), heads: [...sec(ctyD, '<thead>', '</thead>').matchAll(/<th[^>]*>([^<]*)/g)].map(m => m[1]),
      few_badges: [...ctyD.matchAll(/<tr class="clk" data-cc="([^"]*)"[^>]*>[\s\S]*?<\/tr>/g)].filter(m => m[0].includes('>few installs</span>')).map(m => m[1]),
      verdicts: Object.fromEntries([...ctyD.matchAll(/<tr class="clk" data-cc="([^"]*)"[\s\S]*?<span class="pill ([a-z0-9-]+)" data-st="([a-z_]+)"[^>]*>([^<]*)<\/span><\/td><\/tr>/g)].map(m => [m[1], [m[2], m[3], m[4]]])),
      names: [...ctyD.matchAll(/<tr class="clk" data-cc="([^"]*)"[^>]*><td class="nm">([^<]*)/g)].map(m => [m[1], m[2].trim()]),
      strip: text(sec(ctyD, 'id="val-cstrip">', '</div>')).trim(), win: text(sec(ctyD, 'id="val-cwin"', '</div>')).replace(/^[^>]*>/, '').trim(),
      rest: [...sec(ctyD, 'id="val-rest">', '<div style="padding:4px 17px 14px">').matchAll(/<div>([\s\S]*?)<\/div>/g)].map(m => text(m[1]).trim()),
      nogeo: ctyD.includes('id="val-nogeo"'), smp: ctyD.includes('id="val-smp"'), link: ctyD.includes(`onclick="show('countries')">AdMob eCPM by country → Country Strategy</span>`),
      open_desk: text(sec(out[`detail|${r.app}|cty_open_desk`] || '', '<tr class="val-cx"', '</tr>')), open_phone: text(sec(out[`detail|${r.app}|cty_open`] || '', '<div class="val-cxd">', '</div></div></div>')),
      open_sparks: (sec(out[`detail|${r.app}|cty_open_desk`] || '', '<tr class="val-cx"', '</tr>').match(/<svg /g) || []).length,
      sort_d1: [...sec(out[`detail|${r.app}|sort_d1`] || '', 'id="val-ccards"', 'id="val-rest"').matchAll(/<div class="val-cc[^"]*" data-cc="([^"]*)" onclick/g)].map(m => m[1]),
      sort_d1_line: (sec(out[`detail|${r.app}|sort_d30`] || '', 'id="val-ccards"', 'id="val-rest"').match(/<div class="m">([\s\S]*?)<\/div>/) || [])[1] || '' },
    chk: { folded: sec(h, 'id="val-chk"', 'id="val-timing"').includes('<ul') === false, open: chk.includes('<ul class="tb">'), chart: chk.includes('id="val-ratio"'), text: text(chk).trim() },
    pills: pills(h + hd + f), phone_tiles: /class="uni-tiles val-tiles" id="val-tiles" style="--n:3"/.test(h) };
}
// the All-apps page
const pH = out.portfolio || '', pD = out.portfolio_desktop || '';
const psorts = {}; for (const k of PSORTS) for (const d of [1, -1]) psorts[k + '|' + d] = [...sec(out[`psort|${k}|${d}`] || '', 'id="val-table"', '</tbody>').matchAll(/<tr class="clk" data-app="([^"]*)"/g)].map(m => m[1].replace(/&amp;/g, '&'));
const xp = { chips: Object.fromEntries([...pH.matchAll(/data-k="([a-z0-9_]+:[a-z_]+)"[^>]*><i class="dt"><\/i>([^<]*) <b>\((\d+)\)<\/b>/g)].map(m => [m[1], { label: m[2], n: +m[3] }])), open: {} };
for (const k of Object.keys(STRIP_ST)) { const h = out['xp|' + k] || '', seg = h.split('data-xp="')[1] || '';
  xp.open[k] = { panel: seg ? seg.slice(0, seg.indexOf('"')) : null, panels: (h.match(/data-xp="/g) || []).length,
    apps: [...(seg.split('</div></div>')[0] || '').matchAll(/data-app="([^"]*)"/g)].map(m => m[1].replace(/&amp;/g, '&')) }; }
const portfolio = { head: text(pH.slice(0, 900)).trim(), count: text(sec(pH, 'id="val-count">', '</div>')).trim(),
  pool: [...sec(pH, 'id="val-pool"', 'class="uni-sec"').matchAll(/<div class="uni-st val-t val-pt" data-m="([a-z0-9_]+)">([\s\S]*?)(?=<div class="uni-st val-t val-pt"|$)/g)].map(m => ({ m: m[1], text: text(m[2]).trim() })),
  chg_title: (sec(pH, 'id="val-chg"', 'id="val-table"').match(/🔔 What changed\? \((\d+)\)/) || [])[1],
  chg_rows: [...sec(pH, 'id="val-chg"', 'id="val-table"').matchAll(/<div class="uni-chg wa" data-fam="[^"]*" onclick="valOpen\('([^']*)'\)"/g)].map(m => m[1]),
  table_heads: [...sec(pH, 'id="val-table"', '</thead>').matchAll(/<th onclick="valPSort\('([a-z0-9]+)'\)"[^>]*>([^<▲▼]*)/g)].map(m => [m[1], m[2].trim()]),
  table_rows: [...sec(pH, 'id="val-table"', '</tbody>').matchAll(/<tr class="clk" data-app="([^"]*)" onclick="valOpen\('([^']*)'\)"/g)].map(m => [m[1], m[2]]),
  table_pills: [...sec(pH, 'id="val-table"', '</tbody>').matchAll(/<span class="pill ([a-z0-9-]+)" data-st="([a-z_]+)"/g)].map(m => [m[1], m[2]]),
  strip_classes: [...sec(pH, 'class="act-strips"', 'id="val-chg"').matchAll(/<span class="uni-sc ([a-z-]+)( on)?" data-k="([a-z0-9_]+):([a-z_]+)"/g)].map(m => [m[1], m[3], m[4]]),
  ctyall: text(sec(pH, 'id="val-ctyall"', 'id="val-noads"')).slice(0, 1500), ctyall_rows: [...sec(pH, 'id="val-ctyall"', '</tbody>').matchAll(/<tr data-cc="([^"]*)"/g)].map(m => m[1]),
  ctyall_nofiles: T('portfolio_nofiles').includes('App kholo — uske countries yahan jud jayenge'),
  noads: (pH.match(/<h3>ℹ️ Apps without Google Ads \((\d+)\)<\/h3>/) || [])[1], noga4: (pH.match(/<h3>🔌 Apps without GA4 data \((\d+)\)<\/h3>/) || [])[1],
  timing: T('portfolio_timing').includes('Alert tabhi jab 2 hafte lagatar ho.'), inr: (out.portfolio_inr || '').includes('₹'), xp, psorts };
// Alerts screen
const alertsOf = h => ({ sub: h.includes('💸 Install value (GA4 + Ads)'), cards: (h.match(/data-metrics="value"/g) || []).length, chip: h.includes(`onclick="filterAlerts('value')"`),
  open_app: [...h.matchAll(/onclick="valGo\('([^']*)'\)">Open app →/g)].map(m => m[1]), upd: [...h.matchAll(/onclick="uniImpGo\('([^']*)','([^']*)','act'\)">Update detail →/g)].map(m => [m[1], m[2]]),
  total: (text(h).match(/Total issues (\d+)/) || [])[1] });
const alerts = { all: alertsOf(out.alerts_all || ''), per_app: Object.fromEntries(rows.map(r => [r.app, alertsOf(out['alerts|' + r.app] || '')])),
  absent: out.alerts_absent || '', empty: out.alerts_empty || '', bad: out.alerts_bad || '' };
// phone layout: every table sits in a scroller; nothing else asks for more than a phone's width
const wide = [];
for (const [k, v] of Object.entries(out)) {
  if (!(k.startsWith('detail|') || k.startsWith('portfolio')) || !(k.endsWith('|base') || k === 'portfolio' || k.endsWith('|cty_open') || k.endsWith('|folds'))) continue;
  for (const m of v.matchAll(/min-width:(\d+)px/g)) { const before = v.slice(Math.max(0, m.index - 400), m.index); if (+m[1] > 340 && !/<div class="uni-scroll"[^>]*><table [^>]*$/.test(before)) wide.push(k + ': ' + m[1]); }
  for (const m of v.matchAll(/<table /g)) { const before = v.slice(Math.max(0, m.index - 60), m.index); if (!/<div class="uni-scroll"[^>]*>$/.test(before)) wide.push(k + ': table outside a scroller'); }
  for (const m of v.replace(/<svg[\s\S]*?<\/svg>/g, '').matchAll(/\swidth="(\d+)"/g)) if (+m[1] > 340) wide.push(k + ': fixed width ' + m[1]);   // a chart's inner layout scales with its viewBox
  for (const m of v.matchAll(/<svg [^>]*>/g)) if (!/style="width:100%|max-width:100%/.test(m[0]) && !/\swidth="([0-9]|[1-2][0-9]|3[0-3])?[0-9]"/.test(m[0])) wide.push(k + ': chart without a fluid width');
}
const syn = {
  no_red: { pills: pills(out.no_red || ''), blue: [...(out.no_red || '').matchAll(/<span class="pill p-b" data-st="(worse|watch|better)"/g)].map(m => m[1]),
    strip: [...(out.no_red || '').matchAll(/<span class="uni-sc ([a-z-]+)( on)?" data-k="(pay|cpi):(worse|better)"/g)].map(m => [m[1], m[4]]) },
  warn: { red_tile: /data-m="pay" data-st="worse"[\s\S]*?<span class="pill p-r" data-st="worse"/.test(out.warn || ''), row: (out.warn || '').includes('<span class="pill p-r">Worse</span>') },
  unclean: { wait: [...(out.unclean || '').matchAll(/<span class="pill p-b" data-st="wait" title="([^"]*)">Wait<\/span>/g)].length, judged: [...(out.unclean || '').matchAll(/data-st="(keep|slow|costly|top|avg|low)"/g)].length,
    approx: (sec(out.unclean || '', '<tr class="clk"', '</tbody>').match(/≈\d/g) || []).length, tip: (out.unclean || '').includes('In hafton me GA4 ne kuch installs/kamai kisi country me nahi baante'),
    text: text(out.unclean || '').slice(0, 600) },
  geo: { heads: [...sec(out.geo || '', '<thead>', '</thead>').matchAll(/<th[^>]*>([^<]*)/g)].map(m => m[1]), strip: text(sec(out.geo || '', 'id="val-cstrip">', '</div>')).trim(),
    nogeo: (out.geo || '').includes('id="val-nogeo"'), open: text(sec(out.geo || '', '<tr class="val-cx"', '</tr>')) },
  h180: { rpi: [...(out.h180 || '').matchAll(/\(180 d\)/g)].length, target: (out.h180 || '').includes('Target: paisa 180 din me wapas'), nogeo: text(sec(out.h180 || '', 'id="val-nogeo"', '</div>')) },
  never: { big: ((out.never || '').match(/data-m="pay" data-st="never"[\s\S]*?<div class="v">([^<]*)<\/div>/) || [])[1], chip: ((out.never || '').match(/data-m="pay" data-st="never"[\s\S]*?<span class="pill ([a-z0-9-]+)" data-st="never"[^>]*>([^<]*)</) || []).slice(1),
    cell: (out.never || '').includes('>Over 1 year</td>'), sub: text(out.never || '').includes('saal bhar me ≈62% wapas') },
  smp: { note: text(sec(out.smp || '', 'id="val-smp"', '</div>')).replace(/^[^>]*>/, '').trim(), unassigned: [...sec(out.smp || '', 'id="val-rest">', '<div style="padding:4px 17px 14px">').matchAll(/<div>([\s\S]*?)<\/div>/g)].map(m => text(m[1]).trim()),
    approx: (sec(out.smp || '', '<tr class="clk"', '</tbody>').match(/≈\d/g) || []).length },
  extras: (() => { const x = out.extras || ''; return { rel_row: new RegExp(`<tr class="uni-rel"><td class="nm"><span class="uni-rl"[^>]*onclick="uniImpGo\\('[^']*','ver:1\\.4@${REL_FROM}','act'\\)">📦 v1\\.4[\\s\\S]*?</tr><tr data-week="${REL_FROM}">`).test(x),
    chip: new RegExp(`uniImpGo\\('[^']*','ver:1\\.4@${REL_FROM}','act'\\)">After v1\\.4<`).test(x), q: [...x.matchAll(/data-q="1" title="([^"]*)">([^<]*)</g)].map(m => [m[1], m[2]]),
    closed: (x.match(/<div class="uni-chg na cl"/g) || []).length, older: (x.match(/data-old="/g) || []).length, iap: text(x).includes('In-app kharidari alag:'),
    thin: x.includes('>Little spend</td>'), noads: (x.match(/>No ads</g) || []).length }; })(),
  cty_wait: T('cty_wait'), cty_low: T('cty_low'), no_weeks: T('no_weeks'), broken: T('broken_part'), odd: T('odd_shapes'),
  wait_row: { page: T('wait_row').split('<hr>')[0], row: /<tr class="clk" data-app="Waiting Demo"[\s\S]*?⏳ data aa raha/.test((out.wait_row || '').split('<hr>')[1] || ''), html: (out.wait_row || '').split('<hr>')[0] },
  no_value: T('no_value'), no_value_html: out.no_value || '', bad_payload: T('bad_payload'), file_error: T('file_error'), file_loading: T('file_loading'), row_error: T('row_error'),
  noga4: Object.fromEntries(Object.keys(out).filter(k => k.startsWith('noga4|')).map(k => [k.slice(6), T(k)])),
};
// small helpers checked on their own
const fmt = JSON.parse(run(`(()=>{ ${RESET} const V=[0,0.0042,0.00004,0.0099,0.021,0.35,0.123,1.2345,12.5,-0.003,null,'x',undefined];
  const usd=V.map(valMoney); CURVIEW='INR'; const inr=V.map(valMoney); CURVIEW=null;
  const big=[0,12.345,1234.5,null].map(valBig), p100=[4.25,42.4,142.6,null].map(valP100), p100s=[0.042,0.0049,0].map(valP100);
  const names=['US','IN','NG','DE','GB','BR','--','ZZ','zz','XX'].map(c=>[c,valCtyName(c),valFlag(c)]);
  return JSON.stringify({usd,inr,big,p100,p100s,names}); })()`));
console.log(JSON.stringify({
  scenarios: Object.keys(out).length, errors, bad, jargon: jargon.slice(0, 20), devanagari, coloured, wide, ids, titles: String(run('TITLES.value.join("|")')),
  apps, portfolio, alerts, header, gofrom, syn, fmt, fix, alert_cards: out.alert_cards || '',
  texts: Object.fromEntries(Object.entries(out).filter(([k]) => /^(detail\|[^|]*\|(base|desktop)|portfolio|portfolio_desktop)$/.test(k)).map(([k]) => [k, T(k).slice(0, 12000)])),
}, null, 1));
