// The Active users tab's frontend contract: runs the REAL dashboard script (frontend/index.html's <script>) in a node vm
// with stub browser globals, feeds it the committed fixtures (tests/fixtures/active_sample.json — the Active summary,
// the Uninstall summary and every app's active_<key>.json.gz detail, written by the real build code — plus
// tests/fixtures/uninstall_sample.json for the Uninstall tab's asset) and renders every Active-tab state: the All-apps
// page (every Period, every sort, every status chip opened), each app's detail in every chart / table mode, the 📦 Update
// impact blocks in this tab, the Alerts-screen section, phone and desktop widths, and made-up states the fixture may not
// hold (edge searching / waiting, an ⏳ Early-look row, an "Ads/user" revenue chip, other time zones), and the All-apps
// "📅 Daily — all apps" section on the fixture's active_portfolio file (or, until the fixture carries one, a stub built
// here from the per-app details by the contract's rules: pfStub). Prints one JSON report; tests/test_active_frontend.py
// asserts on it.   usage: node active_frontend.js <script.js> <active.json> <uninstall.json>
const fs = require('fs'), vm = require('vm');
const [scriptPath, fixturePath, uniPath] = process.argv.slice(2);
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
const FX = JSON.parse(fs.readFileSync(fixturePath, 'utf8')), UF = JSON.parse(fs.readFileSync(uniPath, 'utf8'));
ctx.__FX = FX; ctx.__UF = UF;
run(`DATA = {apps_catalog: [], today_date: '2026-09-25', alerts: {counts: {}, items: []}, uninstall: __FX.dashboard_uninstall, active: __FX.dashboard_active};
     UNI = __UF.asset; UNIERR = false; UNICOH = {}; ACTD = {}; ACTSIG = {};
     for (const [k, d] of Object.entries(__FX.app_files || {})) ACTD[k] = d;`);
// 📅 Daily — all apps: the fixture's own active_portfolio file (the build's, fixture key "portfolio"); a fixture made before
// it carried one gets a stub built here by the same contract (v1): each app's arrays from its first day with active users
// on / after its launch to its data_till (to its last such day when it stopped: none over its last 7 data days); every
// field null on a day without active users; d1 / d7 only where the install day's return data is usable (coh.ok = 1);
// u / s / t = the returning users' usage row; brk = its tracking-check days
const dd = (a, b) => Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 864e5);
const dadd = (a, n) => new Date(Date.parse(a + 'T00:00:00Z') + n * 864e5).toISOString().slice(0, 10);
function pfStub(fx) {
  const apps = [], missing = [];
  for (const r of fx.dashboard_active.apps) {
    const d = (fx.app_files || {})[r.key]; if (!d || !d.daily) { missing.push({ app_id: r.app_id, app: r.app, why: 'error' }); continue; }
    const D = d.daily, st = D.start || d.history_start, L = d.launch || {}, i0 = (L.hidden && L.day) ? Math.max(0, dd(st, L.day)) : 0, a1 = D.a1 || [];
    const known = []; for (let i = i0; i < a1.length; i++) if (a1[i]) known.push(i);
    if (!known.length) { missing.push({ app_id: r.app_id, app: r.app, why: 'no_data' }); continue; }
    const f = known[0], l = known[known.length - 1], iE = Math.min(a1.length - 1, dd(st, d.data_till)), stopped = iE - l >= 7, last = stopped ? l : iE;
    const C = D.coh || {}, ok = C.ok || [], F = d.flags || {}, o = { a1: [], new: [], ret: [], d1: [], d7: [], u: [], s: [], t: [], rev: [] };
    const g = (a, i) => (a && a[i] != null) ? a[i] : null;
    for (let i = f; i <= last; i++) { const has = !!a1[i], n = has ? g(D.new, i) : null, u = has ? g((D.u || {}).r, i) : null;
      o.a1.push(has ? a1[i] : null); o.new.push(n); o.ret.push(has ? g(D.ret, i) : null);
      for (const k of ['d1', 'd7']) { const v = g(C[k], i); o[k].push(has && v != null && n && ok[i] === 1 ? v : null); }
      o.u.push(u || null); o.s.push(u ? g((D.s || {}).r, i) : null); o.t.push(u ? g((D.t || {}).r, i) : null); o.rev.push(has ? g(D.rev, i) : null); }
    const fi = dadd(st, f), la = dadd(st, last);
    apps.push(Object.assign(o, { app_id: d.app_id, app: d.app, key: d.key, start: fi, to: la, data_till: d.data_till, settled_till: d.settled_till, stale: !!d.stale,
      stopped, start_why: i0 ? 'launch' : 'data', currency: d.currency, rev_est: !!(F.tz_blend || F.rev_est), brk: (D.breaks || []).filter(x => x >= fi && x <= la) }));
  }
  return { v: 1, currency: (apps.find(a => a.currency) || {}).currency || 'USD', missing, apps };
}
const PF = FX.portfolio || pfStub(FX), PF_SRC = FX.portfolio ? 'fixture' : 'stub';
ctx.__PF = PF;
run(`if(!DATA.active.portfolio) DATA.active.portfolio={file:'active_portfolio.json.gz',sig:'stub00000000'}; ACTPF=__PF; ACTPFSIG=DATA.active.portfolio.sig; ACTPFC=null;`);
const out = {};
function scen(name, code) { try { out[name] = String(run(code)); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 4).join(' < ')); } }
const RESET = `UNIAPP=''; APP=''; RANGE='30d'; innerWidth=375; ACTAPP=''; ACTRANGE='90d'; ACTSMOOTH='7d'; ACTUSEM='time'; ACTUSEPOP='r'; ACTREVM='k'; ACTRETN=1;
  ACTTRI='key'; ACTTRIEXP=false; ACTPRE=false; ACTSTEXP=''; ACTTILEEXP=''; ACTOLDEXP=false; ACTCLEXP=false; ACTTIMEXP=false; ACTVERALL=false;
  ACTSORT={k:'status',d:1}; ACTRELALL=false; ACTIMPOPEN=''; ACTIMPALL=false; ACTIMPHOW=false; ACTUPF=''; ACTUPALL=false; ACTIMPJUMP=''; ACTJUMP='';
  ACTIMPWIN=7; ACTIMPWK={}; UNIIMPWIN=7; UNIIMPWK={}; ACTPFR='90d'; ACTPFN=14; ACTPFMK=false;`;
const rows = FX.dashboard_active.apps, dets = FX.app_files;
const J = JSON.stringify;
const openApp = r => `ACTAPP=${J(r.app_id)}; APP=${J(r.app)};`;

// ── All apps ──
for (const r of ['today', '7d', '30d', '90d', 'month', 'lastmonth', 'all', 'custom'])
  scen('portfolio_' + r, `${RESET} RANGE='${r}'; RCUSTOM={from:'2026-08-01',to:'2026-09-30'}; actScreen()`);
const SORTS = ['app', 'ret', 'rel', 'd1', 'd7', 'sess', 'time', 'rev', 'status'];
for (const k of SORTS) for (const d of [1, -1]) scen(`sort|${k}|${d}`, `${RESET} ACTSORT={k:'${k}',d:${d}}; actPortfolio()`);
// every status chip opened on its own: exactly one list, the apps in it
const STRIPS = ['ret_dau', 'd1', 'd7', 'sess', 'time', 'arpdau'], XP = [];
for (const k of STRIPS) for (const st of [...new Set(rows.map(r => ((r.m || {})[k] || {}).st || 'wait'))]) {
  XP.push(k + ':' + st); scen('xp|' + k + ':' + st, `${RESET} ACTSTEXP='${k}:${st}'; actScreen()`); }
// the portfolio with no app file loaded (Older changes: "open an app"), and with every one loaded + opened
scen('portfolio_nofiles', `${RESET} (()=>{ const keep=ACTD; ACTD={}; try{ ACTOLDEXP=true; return actScreen(); } finally{ ACTD=keep; } })()`);
scen('portfolio_older_open', `${RESET} ACTOLDEXP=true; actScreen()`);
scen('portfolio_desktop', `${RESET} innerWidth=1280; actScreen()`);
scen('upd_filters', `${RESET} (()=>{ let s=''; for(const f of ['','halt','hold','continue','win','pending']){ ACTUPF=f; s+=actScreen(); } ACTUPALL=true; return s+actScreen(); })()`);
scen('timing_open', `${RESET} ACTTIMEXP=true; actScreen()`);
// no DATA.active at all / an app error row / a file that failed to load / one still loading / an app without GA4
scen('no_active', `${RESET} (()=>{ const k=DATA.active; delete DATA.active; try{ return actScreen(); } finally{ DATA.active=k; } })()`);
scen('alerts_no_active', `${RESET} (()=>{ const k=DATA.active, keep=screenDiv; delete DATA.active; screenDiv=id=>({dataset:{screen:id},innerHTML:''});
  try{ return renderAlerts().innerHTML; } finally{ DATA.active=k; screenDiv=keep; } })()`);
const r0 = rows[0];
scen('file_error', `${RESET} ${openApp(r0)} (()=>{ const k=ACTD[${J(r0.key)}]; delete ACTD[${J(r0.key)}]; ACTERR[${J(r0.key)}]=true; try{ return actScreen(); } finally{ ACTD[${J(r0.key)}]=k; ACTERR={}; } })()`);
scen('file_loading', `${RESET} ${openApp(r0)} (()=>{ const k=ACTD[${J(r0.key)}]; delete ACTD[${J(r0.key)}]; try{ return actScreen(); } finally{ ACTD[${J(r0.key)}]=k; ACTL={}; } })()`);
scen('row_error', `${RESET} ${openApp(r0)} (()=>{ const k=DATA.active.apps[0], keep=JSON.stringify(k); k.status='error';
  try{ return actScreen()+'<hr>'+(()=>{ APP=''; return actPortfolio(); })(); } finally{ Object.assign(k,JSON.parse(keep)); } })()`);
for (const n of FX.dashboard_active.no_ga4 || []) scen('noga4|' + n.app, `${RESET} APP=${J(n.app)}; actScreen()`);

// ── each app ──
const MODES = [
  ['base', ''], ['day_all', `ACTSMOOTH='day'; ACTRANGE='all';`], ['30d', `ACTRANGE='30d';`], ['1y_pre', `ACTRANGE='1y'; ACTPRE=true;`],
  ['every_col', `ACTTRI='all'; ACTTRIEXP=true;`], ['tri_pre', `ACTPRE=true; ACTTRIEXP=true;`], ['sess_all', `ACTUSEM='sess'; ACTUSEPOP='all';`],
  ['time_new_day', `ACTUSEM='time'; ACTUSEPOP='n'; ACTSMOOTH='day';`], ['rev_ads', `ACTREVM='ads'; ACTSMOOTH='day';`], ['rev_ecpm', `ACTREVM='ecpm';`],
  ['ret7', `ACTRETN=7;`], ['ret30', `ACTRETN=30; ACTRANGE='all';`], ['folds', `ACTCLEXP=true; ACTOLDEXP=true; ACTTIMEXP=true; ACTVERALL=true; ACTRELALL=true;`],
  ['tile_open', `ACTTILEEXP='ret_dau';`], ['desktop', `innerWidth=1280;`], ['range_all', `RANGE='all';`], ['range_today', `RANGE='today';`]];
for (const r of rows) for (const [m, set] of MODES) scen(`detail|${r.app}|${m}`, `${RESET} ${openApp(r)} ${set} actScreen()`);

// ── 📦 Update impact in THIS tab: every block opened; every release chip / grid badge opens its block here ──
const imp = { blocks: [], jumps: [], chips: [], badges: [] };
for (const r of rows) {
  const d = dets[r.key]; if (!d) continue;
  for (const b of ((d.impact || {}).updates || [])) {
    const nm = `imp|${r.app}|${b.key}`;
    scen(nm, `${RESET} ${openApp(r)} ACTIMPOPEN=${J(b.key)}; actScreen()`);
    const h = out[nm] || '', open = h.split('<div class="uni-imp-b').filter(x => x.includes('data-open="1"'));
    imp.blocks.push({ app: r.app, key: b.key, n_open: open.length, open_key: open.length ? (open[0].match(/data-key="([^"]*)"/) || [])[1] : null,
      id_act: h.includes(`id="act-imp-${b.key}"`), id_uni: h.includes('id="uni-imp-'), rows: open.length ? [...open[0].matchAll(/<tr data-row="([a-z_0-9]+)"/g)].length : 0,
      acts: (h.split('id="act-impact"')[1] || '').split('id="act-kpis"')[0].match(/onclick="uni[A-Za-z]+\([^"]*\)"/g) || [] });
  }
  for (const rl of d.releases || []) {
    if (!rl.key) continue;
    let res = null;
    try { res = JSON.parse(run(`(()=>{ ${RESET} ${openApp(r)} uniImp(${J(rl.key)},'act'); const h=actScreen(); const o=h.split('<div class="uni-imp-b').filter(x=>x.includes('data-open="1"'));
      return JSON.stringify({open:ACTIMPOPEN, jump:ACTIMPJUMP, all:ACTIMPALL, rendered:o.length?(o[0].match(/data-key="([^"]*)"/)||[])[1]:null, uni_open:UNIIMPOPEN}); })()`)); }
    catch (e) { errors.push('uniImp act ' + rl.key + ': ' + e.message); continue; }
    imp.jumps.push(Object.assign({ app: r.app, key: rl.key }, res));
  }
  // every 📦 chip / grid line / badge in the tab (all modes) calls uniImp('<key>','act') with a key of this app's releases
  for (const [m] of MODES) { const h = out[`detail|${r.app}|${m}`] || '';
    for (const x of h.matchAll(/class="act-pkg" data-key="([^"]*)"[^>]*onclick="uniImp\('([^']*)','act'\)"/g)) imp.chips.push({ app: r.app, key: x[1], call: x[2], known: (d.releases || []).some(z => z.key === x[2]) });
    const tri = (h.split('id="act-tri"')[1] || '').split('id="act-use"')[0];
    for (const x of tri.matchAll(/onclick="uniImp\('([^']*)'(,'act')?\)"/g)) imp.badges.push({ app: r.app, key: x[1], act: !!x[2], known: (d.releases || []).some(z => z.key === x[1]) });
    const any_uni = (h.match(/uniImp\('[^']*'\)/g) || []).length; if (any_uni) errors.push(`detail|${r.app}|${m}: a uniImp without 'act'`);
  }
}
// the jump from another screen (Recent updates row / Alerts card): show('active'), that app, that block
try { imp.go = JSON.parse(run(`(()=>{ const keep={render, show, _navSave}, calls=[]; render=function(){ calls.push('render'); }; show=function(id){ calls.push('show:'+id); }; _navSave=function(){};
  try{ ${RESET} const r=DATA.active.apps.find(x=>ACTD[x.key]&&((ACTD[x.key].impact||{}).updates||[]).length), b=ACTD[r.key].impact.updates[0];
    uniImpGo(r.app_id,b.key,'act'); return JSON.stringify({calls, app:APP, want:r.app, actapp:ACTAPP, open:ACTIMPOPEN, key:b.key, uni:UNIIMPOPEN, screen:actScreen().includes('id="act-imp-'+b.key+'"')}); }
  finally{ render=keep.render; show=keep.show; _navSave=keep._navSave; } })()`)); } catch (e) { errors.push('imp go: ' + e.message); }


// ── 📦 Before / after windows in THIS tab (SPEC_WINDOWS §5): its own card default (independent of the Uninstall tab's),
// every onclick carrying 'act', the ⏰ late chip / Recent updates chip opening the block HERE at 30; the fixture's own
// by_window (impact v2) — every block at 30 — when it has them
run(fs.readFileSync(require('path').join(__dirname, 'impact_win_synth.js'), 'utf8'));
const win = { v2: false, blocks: [], syn: null };
for (const r of rows) { const d = dets[r.key]; if (!d) continue;
  for (const b of ((d.impact || {}).updates || [])) { if (!b.by_window) continue; win.v2 = true;
    const nm = `win|${r.app}|${b.key}`;
    scen(nm, `${RESET} ${openApp(r)} ACTIMPOPEN=${J(b.key)}; ACTIMPWK={${J(b.key)}:30}; actScreen()`);
    const h = out[nm] || '', o = h.split('<div class="uni-imp-b').filter(x => x.includes('data-open="1"'))[0] || '';
    win.blocks.push({ app: r.app, key: b.key, id_act: h.includes(`id="act-imp-${b.key}"`), rows: [...o.matchAll(/<tr data-row="([a-z_0-9]+)"/g)].map(m => m[1]),
      hdr: (o.match(/Verdict( \(\d+ days\))?:/) || [])[0] || null, acts: (h.split('id="act-impact"')[1] || '').split('id="act-kpis"')[0].match(/onclick="uni[A-Za-z]+\([^"]*\)"/g) || [] }); } }
try { win.syn = JSON.parse(run(`(()=>{ ${RESET} const r=DATA.active.apps.find(x=>ACTD[x.key]&&((ACTD[x.key].impact||{}).updates||[]).length), d=__winApp(ACTD[r.key]), B=uniImpBlocks(d), b=B[0];
  const ua=__winApp(UNI.apps.find(x=>uniImpBlocks(x).length)), saved=[], keepLS=localStorage, hdr=h=>[...h.matchAll(/Verdict( \\(\\d+ days\\))?:/g)].map(m=>m[1]||'');
  localStorage={getItem:()=>null,setItem:(k,v)=>saved.push([k,v]),removeItem(){}};
  try{ const o={};
    uniImpWinX(30,'act'); o.act=hdr(uniImpactCard(d,'act')); o.uni=hdr(uniImpactCard(ua)); o.acwin=ACTIMPWIN; o.uwin=UNIIMPWIN; o.saved=saved.slice();
    o.note=(uniImpactCard(d,'act').match(/<div class="faint act-imp-note"[^>]*>([^<]*)<\\/div>/)||[])[1]||null;
    uniImpWinX(60); o.act2=hdr(uniImpactCard(d,'act')); o.uni2=hdr(uniImpactCard(ua)); o.saved2=saved.slice();
    b.late={level:'hold',alert_id:'x',seeded:false}; ACTIMPOPEN=b.key; const h=uniImpactCard(d,'act');
    o.onclicks=h.match(/onclick="[^"]*"/g)||[]; o.late=(h.match(/<span class="pill [a-z-]+ uni-late"[^>]*onclick="([^"]*)">([^<]*)<\\/span>/)||[]).slice(1);
    o.ids=[...h.matchAll(/\\sid="([^"]*)"/g)].map(m=>m[1]);
    const s={app:r.app,app_id:r.app_id,updates:[{key:b.key,label:b.label,date:b.date,level:'continue',early:false,final:true,adoption:0.9,head:null,judged:7,late:{level:'halt',alert_id:'x'}}]};
    o.upd=(uniUpdatesCard([{s,a:d}],'act').match(/<span class="pill [a-z-]+ uni-late"[^>]*onclick="([^"]*)">([^<]*)<\\/span>/)||[]).slice(1);
    o.app_id=r.app_id; o.key=b.key; return JSON.stringify(o); }
  finally{ localStorage=keepLS; ${RESET} } })()`)); } catch (e) { errors.push('win act: ' + e.message); }

// ── ids: each app's Uninstall screen and Active screen — each duplicate-free, the two disjoint ──
const ids = [];
for (const r of rows) {
  if (!dets[r.key]) continue;
  let res = null;
  try { res = JSON.parse(run(`(()=>{ ${RESET} const u=(UNI.apps||[]).find(x=>x.app_id===${J(r.app_id)}); UNIAPP=${J(r.app_id)}; ${openApp(r)} UNIIMPOPEN=''; ACTIMPOPEN='';
    const U=u?uniScreen():'', A=actScreen(); return JSON.stringify({u:[...U.matchAll(/\\sid="([^"]*)"/g)].map(m=>m[1]), a:[...A.matchAll(/\\sid="([^"]*)"/g)].map(m=>m[1]), has_uni:!!u}); })()`)); }
  catch (e) { errors.push('ids ' + r.app + ': ' + e.message); continue; }
  const dup = l => l.filter((x, i) => l.indexOf(x) !== i);
  ids.push({ app: r.app, has_uni: res.has_uni, n_uni: res.u.length, n_act: res.a.length, dup_uni: dup(res.u), dup_act: dup(res.a),
    shared: res.a.filter(x => res.u.includes(x)), act_not_prefixed: res.a.filter(x => !x.startsWith('act-')) });
}

// ── the header follows the open app (actOpen → setApp), "← All apps" clears it (render / show stubbed) ──
let header = null;
try { header = JSON.parse(run(`(()=>{ const keep={render, show, _navSave}, calls=[]; render=function(){ calls.push('render'); }; show=function(id){ calls.push('show:'+id); }; _navSave=function(){};
  try{ ${RESET} const r=DATA.active.apps[0]; actOpen(r.app_id); const o={name:r.app, app:APP, actapp:ACTAPP, sel:appSelHtml(), calls:calls.slice(), screen:actScreen().slice(0,900)};
    actBack(); o.after={app:APP, actapp:ACTAPP, screen:actScreen().slice(0,300)}; return JSON.stringify(o); }
  finally{ render=keep.render; show=keep.show; _navSave=keep._navSave; } })()`)); } catch (e) { errors.push('header: ' + e.message); }
// an Alerts-screen "Open app →": this tab, that app, its "What changed?" pending
let gofrom = null;
try { gofrom = JSON.parse(run(`(()=>{ const keep={render, show, _navSave}, calls=[]; render=function(){}; show=function(id){ calls.push(id); }; _navSave=function(){};
  try{ ${RESET} const r=DATA.active.apps[0]; actGo(r.app_id); return JSON.stringify({calls, app:APP, want:r.app, jump:ACTJUMP}); }
  finally{ render=keep.render; show=keep.show; _navSave=keep._navSave; ACTJUMP=''; } })()`)); } catch (e) { errors.push('actGo: ' + e.message); }

// ── the Alerts screen: the Active section, each app filter; none when the filter leaves no alert ──
const alertsScen = (nm, pre) => scen(nm, `${RESET} (()=>{ const keep=screenDiv; screenDiv=id=>({dataset:{screen:id},innerHTML:''});
  try{ ${pre} return renderAlerts().innerHTML; } finally { screenDiv=keep; APP=''; } })()`);
alertsScen('alerts_all', `APP='';`);
for (const r of rows) alertsScen('alerts|' + r.app, `APP=${J(r.app)};`);
scen('alert_cards', `${RESET} actAlertCards(actAlertsFor())`);

// ── made-up states (a copy of one app's detail, changed, rendered, restored) ──
const synth = (nm, r, change, what) => scen(nm, `${RESET} (()=>{ const K=${J(r.key)}, keep=ACTD[K], d=JSON.parse(JSON.stringify(keep)), row=DATA.active.apps.find(x=>x.key===K), rk=JSON.stringify(row);
  ${change} ACTD[K]=d; try{ ${openApp(r)} ${what || 'return actScreen();'} } finally{ ACTD[K]=keep; Object.assign(row, JSON.parse(rk)); } })()`);
const withAds = rows.find(r => dets[r.key] && ((dets[r.key].tiles || {}).arpdau || {}).st !== 'noad') || rows[0];
const withTri = rows.find(r => dets[r.key] && ((dets[r.key].tri || {}).rows || []).length) || rows[0];
const withUse = rows.find(r => dets[r.key] && (dets[r.key].edges || {}).usage_state !== 'wait') || rows[0];
// the revenue tile took the ads-per-user state while revenue/user rose: the chip says "Ads/user …"
synth('ads_dir', withAds, `d.tiles.arpdau=Object.assign({},d.tiles.arpdau,{st:'maybe_dn',why:'ads_dir',rel:0.13});`, `return actSumCard(d,row);`);
// ⏳ an Early-look row on a provisional day: an Info row with a Provisional pill, never counted in "What changed? (n)"
synth('early', withAds, `d.changes=Object.assign({open:[],closed:[],info:[],older:[]},d.changes); d.changes.info=(d.changes.info||[]).concat([{kind:'early',metric:'ret_dau',dir:'down',from:d.data_till,to:d.data_till,rel:-0.6,
  text:'⏳ Test (abhi aa raha): active users normal ke aadhe se bhi kam — 3 din me pakka hoga',tags:[],prov:true}]);`, `return actChangesCard(d)+'<hr>'+String((d.changes.open||[]).length);`);
// other data time zones: the revenue note names them from the data, never a hard-coded "IST" / "GMT"
synth('zones', withAds, `d.tz='America/Los_Angeles'; d.rev_tz='Asia/Tokyo';`, `return actRevCard(d);`);
synth('zones_gmt', withAds, `d.tz='Etc/GMT'; d.rev_tz='Etc/GMT-5';`, `return actRevCard(d);`);
synth('zones_same', withAds, `d.tz='Asia/Kolkata'; d.rev_tz='Asia/Kolkata';`, `return actRevCard(d);`);
// a tile with a day missing ("6 of 7 days")
synth('six_days', rows[0], `d.tiles.ret_dau=Object.assign({},d.tiles.ret_dau,{n:6});`, `return actSumCard(d,row);`);
// the data edge while GA4 is still being searched / before any return data: the sentence renders, the grid waits / has no edge row
synth('edge_searching', withTri, `d.edges=Object.assign({},d.edges,{ret_state:'searching',ret_from:null,ret_oldest:'2026-04-26',text:['🔁 GA4 se purana wapsi data dhoondh rahe hain — abhi 26 Apr tak mila, roz ~4 mahine aur aayega.']}); d.tri=Object.assign({},d.tri,{edge:null});`);
synth('edge_wait', withTri, `d.edges=Object.assign({},d.edges,{ret_state:'wait',ret_from:null,text:['🔁 Wapsi (D1/D7) ka data agle GA4 fetch ke saath aayega.']}); d.tri=Object.assign({},d.tri,{rows:[],nmax:0,cols:[],cols_phone:[]});
  d.tiles.d1=Object.assign({},d.tiles.d1,{st:'wait',v:null,base:null,all:null,pp:null,rel:null,from:null,to:null}); d.tiles.d7=Object.assign({},d.tiles.d7,{st:'wait',v:null,base:null,all:null,pp:null,rel:null,from:null,to:null});`);
synth('edge_found', withTri, `d.edges=Object.assign({},d.edges,{ret_state:'found',ret_from:(d.tri.rows||[]).map(x=>x.from).sort()[0]||d.history_start}); d.tri=Object.assign({},d.tri,{edge:d.edges.ret_from});`, `ACTTRIEXP=true; return actTriCard(d);`);
// sessions / time not here yet
synth('usage_wait', withUse, `d.edges=Object.assign({},d.edges,{usage_state:'wait'}); d.tiles.sess=Object.assign({},d.tiles.sess,{st:'wait',v:null}); d.tiles.time=Object.assign({},d.tiles.time,{st:'wait',v:null});`);
// a tile says worse / better with NO open alert (never from the engine): shown blue, never red / green
synth('no_alert_red', rows[0], `d.tiles.sess=Object.assign({},d.tiles.sess,{st:'worse'}); d.tiles.time=Object.assign({},d.tiles.time,{st:'better'}); d.changes=Object.assign({},d.changes,{open:[]});
  DATA.active.apps.find(x=>x.key===K).m.sess=Object.assign({},row.m.sess,{st:'worse'});`, `const keepA=DATA.active.alerts; DATA.active.alerts=[]; try{ return actSumCard(d,row)+'<hr>'+(()=>{ APP=''; return actPortfolio(); })(); } finally{ DATA.active.alerts=keepA; }`);
// a pre-launch app detail with nothing but the wait sentences
synth('all_wait', rows[rows.length - 1], `for(const k of Object.keys(d.tiles||{})) d.tiles[k]=Object.assign({},d.tiles[k],{st:'wait',v:null,base:null,rel:null,pp:null,all:null,z:null,usual:null,from:null,to:null});
  d.changes={open:[],closed:[],info:[],older:[]}; d.versions=[]; d.versions_more=[]; d.releases=[];`);

// ── review fixes: the market-wide lines' counts and tense, the install part's sign, linked alerts, metric hints,
// honest waits on the All-apps page, no big % on a tile that is not judged ──
const withMk = rows.find(r => dets[r.key] && ((dets[r.key].tiles || {}).arpdau || {}).st !== 'noad') || rows[0];
const fx2 = {};
const mkWeek = `{from:'2026-09-01',to:'2026-09-07',dir:'down',share:0.8667,apps:15,of:13,median_rel:-0.1}`;
fx2.rev_market = String(run(`(()=>{ ${RESET} const M=DATA.active.market, keep=JSON.stringify(M); M.weeks=[${mkWeek}]; M.latest=M.weeks[0]; ACTRANGE='all';
  try{ return actRevCard(ACTD[${J(withMk.key)}]); } finally{ Object.assign(M, JSON.parse(keep)); } })()`));
const pfMk = to => String(run(`(()=>{ ${RESET} const A=DATA.active, keep=JSON.stringify(A.market), sM=A.settled_till_max;
  A.market={weeks:[], latest:{from:uniAdd(sM,${to}-6),to:uniAdd(sM,${to}),dir:'down',share:0.8667,apps:15,of:13,median_rel:-0.1}};
  try{ return actSumPortfolio(actRows().filter(r=>uniVis(r.app_id))); } finally{ A.market=JSON.parse(keep); } })()`));
fx2.pf_market_now = pfMk(-2); fx2.pf_market_old = pfMk(-29);
const instLine = (rel, part, irel) => String(run(`(()=>{ ${RESET} const r=DATA.active.apps.find(x=>x.key===${J(rows[0].key)}), d=JSON.parse(JSON.stringify(ACTD[r.key]));
  d.split=null; d.inst={mode:'elastic',rel:${irel},part:${part}}; d.tiles.ret_dau=Object.assign({},d.tiles.ret_dau,{rel:${rel}}); ACTTILEEXP='ret_dau'; return actSumCard(d,r); })()`));
fx2.inst_opp = instLine(0.075, -0.057, -0.33); fx2.inst_same = instLine(-0.12, -0.08, -0.4); fx2.inst_zero = instLine(0.02, 0.001, 0.05);
const oneAl = (extra) => `Object.assign({id:'x|active_act_drift_ads|down',source:'active',app_id:${J(rows[0].app_id)},app:${J(rows[0].app)},family:'act_drift',metric:'ads',also:[],dir:'down',
  severity:'watch',unit:'per1k',now:3600,before:4000,rel:-0.1,delta_pp:null,z:-5,since:'2026-09-01',day:null,installs_from:null,installs_to:null,base_from:null,base_to:null,users:1000,
  opened:'2026-09-10',last_seen:'2026-09-20',fresh:false,notify:false,provisional:false,estimate:true,tags:[],release:null,linked:false,data_till:'2026-09-20',
  text:'1 Sep se har user ko kam ads',message:'x'},${extra})`;
fx2.hint_ads = String(run(`${RESET} actAlertCards([${oneAl('{}')}])`));
fx2.hint_ret = String(run(`${RESET} actAlertCards([${oneAl(`{metric:'ret_dau',unit:'users'}`)}])`));
fx2.linked = String(run(`${RESET} actAlertCards([${oneAl(`{metric:'ret_dau',severity:'warning',linked:true,tags:['update'],release:{key:'ver:1.2@2026-09-11',label:'v1.2',date:'2026-09-11'}}`)}])`));
const alertsTotal = extra => String(run(`${RESET} (()=>{ const keep=screenDiv, A=DATA.active, ka=A.alerts; screenDiv=id=>({dataset:{screen:id},innerHTML:''}); A.alerts=[${oneAl(extra)}];
  try{ return renderAlerts().innerHTML; } finally{ screenDiv=keep; A.alerts=ka; } })()`));
fx2.alerts_linked = alertsTotal(`{severity:'warning',linked:true,release:{key:'k',label:'v1.2',date:'2026-09-11'},tags:['update']}`);
fx2.alerts_unlinked = alertsTotal(`{severity:'warning'}`);
fx2.pool_wait = String(run(`(()=>{ ${RESET} const keep=JSON.stringify(DATA.active.apps); DATA.active.apps.forEach(r=>{ for(const k of ['d1','d7','sess','time']) if(r.m&&r.m[k]) r.m[k]=Object.assign({},r.m[k],{st:'wait',v:null,s:null}); });
  try{ return actPortfolio(); } finally{ DATA.active.apps=JSON.parse(keep); } })()`));
fx2.young_tile = String(run(`(()=>{ ${RESET} const r=DATA.active.apps.find(x=>x.key===${J(rows[0].key)}), d=JSON.parse(JSON.stringify(ACTD[r.key]));
  d.tiles.ret_dau=Object.assign({},d.tiles.ret_dau,{st:'low',why:'young',rel:0.99}); d.tiles.arpdau=Object.assign({},d.tiles.arpdau,{st:'low',why:'few',rel:1.27}); return actSumCard(d,r); })()`));

// the return chart by install day: its points (none before the data edge)
const retc = [];
for (const r of rows) {
  const d = dets[r.key]; if (!d) continue;
  for (const N of [1, 7]) {
    let h = '';
    try { h = run(`(()=>{ ${RESET} ${openApp(r)} ACTRANGE='all'; ACTRETN=${N}; return actTriCard(ACTD[${J(r.key)}]); })()`); } catch (e) { errors.push('retc ' + r.app + ': ' + e.message); continue; }
    const seg = (h.split('id="act-ret-chart"')[1] || ''), m = seg.match(/data-pts='([^']*)'/);
    const pts = m ? JSON.parse(m[1].replace(/&#39;/g, "'").replace(/&amp;/g, '&')) : null;
    const first = pts && pts.length ? run(`(()=>{ const d=ACTD[${J(r.key)}], st=(d.daily||{}).start||d.history_start; for(let i=0;i<=uniDiff(st,d.data_till);i++){ const x=uniAdd(st,i); if(uniD(x)===${J(pts[0].l)}) return x; } return null; })()`) : null;
    retc.push({ app: r.app, N, has: !!m, n: pts ? pts.length : 0, first, edge_mark: seg.includes('>Data starts</text>'), nmax: (d.tri || {}).nmax || 0,
      state: (d.edges || {}).ret_state, ret_from: (d.edges || {}).ret_from || null, chips: [...h.matchAll(/onclick="actRN\((\d+)\)"/g)].map(x => +x[1]) });
  }
}
// the return chart's base: the install day's GA4 new users (daily.new — Firebase's "New users"), never the cohort's own
// total coh.t: t scaled changes nothing, new scaled moves the points
const retbase = [];
for (const r of rows) {
  const d = dets[r.key]; if (!d || !(d.daily || {}).coh || !(((d.tri || {}).nmax || 0) >= 1) || (d.edges || {}).ret_state === 'wait') continue;
  const vals = mut => { const h = run(`(()=>{ ${RESET} ${openApp(r)} ACTRANGE='all'; ACTRETN=1; const d=JSON.parse(JSON.stringify(ACTD[${J(r.key)}])), D=d.daily; ${mut} return actTriCard(d); })()`);
    const m = (h.split('id="act-ret-chart"')[1] || '').match(/data-pts='([^']*)'/);
    return m ? JSON.parse(m[1].replace(/&#39;/g, "'").replace(/&amp;/g, '&')).map(p => p.v) : null; };
  try {
    const base = vals(''), tx = vals('D.coh.t=D.coh.t.map(x=>x==null?x:x*3+7);'), nx = vals('D.new=D.new.map(x=>x==null?x:x*2);');
    retbase.push({ app: r.app, n: base ? base.filter(v => v !== '—').length : 0, t_same: J(base) === J(tx), new_moves: J(base) !== J(nx) });
  } catch (e) { errors.push('retbase ' + r.app + ': ' + e.message); }
}
// the grid: rows, year separators, test weeks, 📦 lines, provisional cells never coloured — phone (cols_phone) and desktop
const grid = [];
for (const r of rows) {
  const d = dets[r.key]; if (!d || !((d.tri || {}).rows || []).length) continue;
  for (const [w, pre, exp, mode] of [[375, false, false, 'key'], [1280, false, true, 'key'], [375, true, true, 'key'], [375, false, true, 'all']]) {
    let h = '';
    try { h = run(`(()=>{ ${RESET} ${openApp(r)} innerWidth=${w}; ACTPRE=${pre}; ACTTRIEXP=${exp}; ACTTRI='${mode}'; return actTriCard(ACTD[${J(r.key)}]); })()`); } catch (e) { errors.push('grid ' + r.app + ': ' + e.message); continue; }
    const tb = (h.split('<tbody>')[1] || '').split('</tbody>')[0];
    grid.push({ app: r.app, w, pre, exp, mode, heads: [...h.matchAll(/<th style="text-align:center">D(\d+)<\/th>/g)].map(x => +x[1]),
      weeks: [...tb.matchAll(/data-week="([^"]*)"/g)].map(x => x[1]), years: [...tb.matchAll(/── (\d{4}) ──/g)].map(x => x[1]),
      test_sep: tb.includes('🧪 '), rel_lines: [...tb.matchAll(/<tr class="uni-rel"><td class="nm">([\s\S]*?)<\/td>/g)].map(x => x[1]),
      order: [...tb.matchAll(/<tr (class="(uni-rel|uni-yr)"|[^>]*data-week="([^"]*)")/g)].map(x => x[2] ? x[2] : 'w:' + x[3]),
      prov_bad: [...tb.matchAll(/<td class="h" data-n="\d+" data-prov="1" style="([^"]*)"/g)].filter(x => /background/.test(x[1])).length,
      prov_cells: [...tb.matchAll(/data-prov="1"/g)].length, part_bad: [...tb.matchAll(/<td class="h" data-n="\d+"( data-prov="1")? style="(background[^"]*)"[^>]*>[^<]*<sup>½<\/sup>/g)].length,
      nodata: (tb.match(/>No data<\/td>/g) || []).length, more: h.includes('onclick="actTX()"'), edge_row: tb.includes('Install-day return data starts') });
  }
}

// ── 📅 Daily — all apps: every range, phone / desktop, paging, the app filter, $ ⇄ ₹, the loading / error / no-file
// states, a stale app, an app late by a day, a broken file, and a section that throws (the rest of the page still draws) ──
for (const r of ['30d', '90d', '180d', 'all']) scen('pf|' + r, `${RESET} ACTPFR='${r}'; actPortfolio()`);
scen('pf|desktop', `${RESET} innerWidth=1280; actPortfolio()`);
scen('pf|all_rows', `${RESET} ACTPFN=100000; ACTPFMK=true; ACTPFR='all'; actPortfolio()`);
scen('pf|more', `${RESET} (()=>{ const keep=actRerender; actRerender=()=>{}; try{ actPfMore(30); return actPortfolio(); } finally{ actRerender=keep; } })()`);
const PF_VIS = rows.filter((r, i) => i % 3 !== 1).map(r => r.app_id);
scen('pf|filter', `${RESET} (()=>{ const kc=DATA.apps_catalog, ks=APPSEL; DATA.apps_catalog=DATA.active.apps.map(r=>({app_id:r.app_id,account_id:'acc-x'}));
  APPSEL={accounts:{'acc-x':{decided:true,selected:${J(PF_VIS)}}}}; ACTPFN=100000; try{ return actPortfolio(); } finally{ DATA.apps_catalog=kc; APPSEL=ks; } })()`);
scen('pf|inr', `${RESET} (()=>{ const kv=CURVIEW; CURVIEW='INR'; ACTPFN=100000; try{ return actPortfolio(); } finally{ CURVIEW=kv; } })()`);
scen('pf|usd', `${RESET} ACTPFN=100000; actPortfolio()`);
const pfMut = (nm, mut) => scen(nm, `${RESET} (()=>{ const keep=ACTPF, F=JSON.parse(JSON.stringify(keep)); ${mut} ACTPF=F; ACTPFN=100000;
  try{ return actPortfolio(); } finally{ ACTPF=keep; ACTPFC=null; } })()`);
const PF_ARR = "['a1','new','ret','d1','d7','u','s','t','rev']";
const PF_STALE = (PF.apps.find(a => a.app === 'Demo Steady') || PF.apps[0]).app_id, PF_LATE = (PF.apps.find(a => a.app === 'Demo Old Drop') || PF.apps[1]).app_id;
pfMut('pf|stale', `const a=F.apps.find(x=>x.app_id===${J(PF_STALE)}); for(const k of ${PF_ARR}) a[k]=a[k].slice(0,a[k].length-6);
  a.data_till=uniAdd(a.data_till,-6); a.settled_till=uniAdd(a.settled_till,-6); a.stale=true;`);
pfMut('pf|late', `const a=F.apps.find(x=>x.app_id===${J(PF_LATE)}); for(const k of ${PF_ARR}) a[k]=a[k].slice(0,a[k].length-1);
  a.data_till=uniAdd(a.data_till,-1); a.settled_till=uniAdd(a.settled_till,-1);`);
pfMut('pf|broken', `F.apps=[null,5,'x',{app_id:'x1',app:'Broken',start:'2026-09-10',a1:[null,'abc',-3,{}]},{app_id:'x2',app:'Odd',start:'2026-09-15',data_till:'2026-09-17',
  a1:[10,20,'30'],new:[1,null,'a'],ret:[9,null,null],d1:[null,'q',2],d7:[],u:[5,0,null],s:[7,'s',null],t:[null,null,40],rev:['x',2,null]}];`);
pfMut('pf|empty', `F.apps=[];`);
// the biggest app (its last day's DAU) gone stale 6 days early / not built this run (in the file's missing list, or — a file
// without that list — its summary row an error): its missing DAU never reads as a drop, and it still counts in "k of n"
const PF_BIG = (() => { let b = null, bv = -1; for (const a of PF.apps) { const v = [...a.a1].reverse().find(x => x) || 0; if (v > bv) { bv = v; b = a.app_id; } } return b; })();
pfMut('pf|stalebig', `const a=F.apps.find(x=>x.app_id===${J(PF_BIG)}); for(const k of ${PF_ARR}) a[k]=a[k].slice(0,a[k].length-6);
  a.data_till=uniAdd(a.data_till,-6); a.settled_till=uniAdd(a.settled_till,-6); a.stale=true;`);
pfMut('pf|errbig', `const a=F.apps.find(x=>x.app_id===${J(PF_BIG)}); F.apps=F.apps.filter(x=>x!==a); F.missing=(F.missing||[]).concat([{app_id:a.app_id,app:a.app,why:'error'}]);`);
scen('pf|errrow', `${RESET} (()=>{ const keep=ACTPF, F=JSON.parse(JSON.stringify(keep)), r=DATA.active.apps.find(x=>x.app_id===${J(PF_BIG)}), ks=r.status;
  F.apps=F.apps.filter(x=>x.app_id!==r.app_id); delete F.missing; r.status='error'; ACTPF=F; ACTPFN=100000;
  try{ return actPortfolio(); } finally{ ACTPF=keep; ACTPFC=null; r.status=ks; } })()`);
// folded chips: the newest 8 + every chip of something drawn on the chart — a big app's tracking-check run behind ten newer
// one-day gaps of a tiny app still has its chip (and its band)
pfMut('pf|pin', `const N=60, f=v=>new Array(N).fill(v), E=()=>f(null), tiny=f(5); for(let i=30;i<=48;i+=2) tiny[i]=null;
  const base={start:'2026-01-01',to:'2026-03-01',data_till:'2026-03-01',settled_till:'2026-02-26',stale:false,stopped:false,currency:'USD',rev_est:false,d1:E(),d7:E(),u:E(),s:E(),t:E(),rev:E()};
  F.missing=[]; F.apps=[Object.assign({},base,{app_id:'pin1',app:'Pin Big',a1:f(1000),new:f(100),ret:f(900),brk:['2026-01-06','2026-01-07','2026-01-08','2026-01-09','2026-01-10','2026-01-11']}),
    Object.assign({},base,{app_id:'pin2',app:'Pin Tiny',a1:tiny,new:tiny.map(v=>v==null?null:1),ret:tiny.map(v=>v==null?null:4),brk:[]})];
  const solo=new Array(72).fill(3); solo[2]=null; const nul=()=>new Array(72).fill(null);   // alone in the set on 22 Dec: that day no app has data
  F.apps.push(Object.assign({},base,{app_id:'pin3',app:'Pin Solo',start:'2025-12-20',a1:solo,new:solo.map(v=>v==null?null:1),ret:solo.map(v=>v==null?null:2),d1:nul(),d7:nul(),u:nul(),s:nul(),t:nul(),rev:nul(),brk:[]}));
  ACTPFR='all';`);
// a portfolio past a million a day: every count in full ("1,234,567", never "1.2M" — a day-to-day change must show)
pfMut('pf|big', `for(const a of F.apps) for(const k of ['a1','new','ret']) a[k]=a[k].map(v=>v==null?v:v*1000);`);
scen('pf|noptr', `${RESET} (()=>{ const k=DATA.active.portfolio; delete DATA.active.portfolio; try{ return actPortfolio(); } finally{ DATA.active.portfolio=k; } })()`);
scen('pf|loading', `${RESET} (()=>{ ACTPF=null; try{ return actPortfolio(); } finally{ ACTPF=__PF; ACTPFC=null; } })()`);
scen('pf|error', `${RESET} (()=>{ ACTPF=null; ACTPFERR=true; try{ return actPortfolio(); } finally{ ACTPF=__PF; ACTPFERR=false; ACTPFC=null; } })()`);
scen('pf|throw', `${RESET} (()=>{ const keep=actPfSeries; actPfSeries=()=>{ throw new Error('boom'); }; try{ return actPortfolio(); } finally{ actPfSeries=keep; } })()`);
// the lazy load: opening All apps with no file in memory starts exactly one fetch of the pointer's file (never on an app's page)
let pfLoad = null;
try { pfLoad = JSON.parse(run(`(()=>{ const keepF=fetchGzJson, calls=[]; fetchGzJson=u=>{ calls.push(u); return new Promise(()=>{}); };
  try{ ${RESET} ACTPF=null; ACTPFL=false; actEnsure(); actEnsure(); const o={calls:calls.slice(), loading:ACTPFL};
    ACTPFL=false; calls.length=0; APP=DATA.active.apps[0].app; ACTAPP=DATA.active.apps[0].app_id; actEnsure(); o.on_app=calls.filter(u=>u.startsWith('active_portfolio')).length; return JSON.stringify(o); }
  finally{ fetchGzJson=keepF; ACTPF=__PF; ACTPFL=false; ACTPFC=null; ACTL={}; APP=''; ACTAPP=''; } })()`)); } catch (e) { errors.push('pf load: ' + e.message); }

// ── what the page says ──
const text = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/\s+/g, ' ');
const uiText = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/\sid="[^"]*"/g, '');   // markup + titles + chart labels, minus code
const bad = [], jargon = [], devanagari = [];
const JARGON = /cumulative|checkpoint|cohort|bharosa|headline/i, DEVA = /[ऀ-ॿ]/;
for (const [k, v] of Object.entries(out)) {
  for (const w of ['undefined', 'NaN', '[object Object]', 'Infinity']) if (v.includes(w)) bad.push(k + ': ' + w);
  if (!k.startsWith('alerts')) { const m = uiText(v).match(JARGON); if (m) jargon.push(k + ': ' + m[0] + ' …' + uiText(v).slice(Math.max(0, m.index - 80), m.index + 30)); }
  if (DEVA.test(v)) devanagari.push(k);
}
const T = k => text(out[k] || '');
const sec = (h, a, b) => (h.split(a)[1] || '').split(b)[0];
const secIn = (h, a, b) => sec(h, a, b).replace(/^[^>]*>/, '');   // the element's inside, after the rest of its opening tag
// per app: tiles (metric, state, chip class + text, the dates line), the "What changed?" rows, the version rows, the context line
const apps = {};
for (const r of rows) {
  const h = out[`detail|${r.app}|base`] || '', f = out[`detail|${r.app}|folds`] || '', d = dets[r.key] || {};
  const sum = sec(h, 'id="act-sum"', 'id="act-chg"');
  const tiles = [...sum.matchAll(/<div class="uni-st act-t[^"]*" data-m="([a-z0-9_]+)" data-st="([a-z_]+)"[\s\S]*?(?=<div class="uni-st act-t|<\/div><div class="uni-meta"|$)/g)].map(m => {
    const t = m[0], ch = t.match(/<span class="pill ([a-z0-9-]+)" data-st="[a-z_]+" title="[^"]*">([^<]*)<\/span>/);
    return { m: m[1], st: m[2], cls: ch ? ch[1] : null, chip: ch ? ch[2] : null, dates: (t.match(/<div class="c act-dt">([^<]*)<\/div>/) || [])[1] || null,
      big: text((t.match(/<div class="v">([\s\S]*?)<\/div>/) || [])[1] || '').trim(), rel: (t.match(/<span class="act-lg">([^<]*)<\/span>/) || [])[1] || null,
      short: (t.match(/<span class="act-sh">([^<]*)<\/span>/) || [])[1] || null, text: text(t).trim().slice(0, 400) }; });
  const chg = sec(h, 'id="act-chg"', 'id="act-impact"');
  const chgF = sec(f, 'id="act-chg"', 'id="act-impact"');
  apps[r.app] = { key: r.key, header: text(h.slice(0, 1500)).slice(0, 300), tiles, ctx: /Active users [\d,.kM—]+ ?\/day New installs [\d,.kM—]+ ?\/day/.test(text(secIn(h, 'id="act-ctx"', '</div>'))),
    ctx_text: text(secIn(h, 'id="act-ctx"', '</div>')).trim(), latest: text(secIn(h, 'id="act-latest"', '</div>')).trim(), latest_prov: sec(h, 'id="act-latest"', '</div>').includes('>Provisional</span>'),
    has_titles: ['📌 At a glance', '🔔 What changed? (', '📦 Update impact', 'When will I know?', '← All apps'].filter(x => T(`detail|${r.app}|base`).includes(x)),
    summary: (sum.match(/<div class="act-line" data-kind="([^"]*)">([^<]*)<\/div>/) || []).slice(1), edges: [...sum.matchAll(/<div class="act-edge">([^<]*)<\/div>/g)].map(m => m[1].replace(/&amp;/g, '&').replace(/&quot;/g, '"')),
    prov_note: /ℹ️ <b>Provisional:<\/b>/.test(sum), uni_link: sum.includes('Open Uninstall →'),
    chg_title: (chg.match(/🔔 What changed\? \((\d+)\)/) || [])[1], chg_rows: [...chg.matchAll(/<div class="uni-chg na" data-fam="([^"]*)"/g)].map(m => m[1]), all_normal: chg.includes('✅ All normal — no changes'),
    info_rows: [...chg.matchAll(/data-info="([^"]*)"/g)].map(m => m[1]), closed_rows: (chgF.match(/<div class="uni-chg na cl"/g) || []).length, older_rows: (chgF.match(/data-old="/g) || []).length,
    folds: [...chg.matchAll(/<span>([A-Za-z ]+) \((\d+)\)<\/span>/g)].map(m => [m[1], +m[2]]),
    sev_pills: [...chg.matchAll(/<span class="sv"><span class="pill ([a-z-]+)">([^<]*)<\/span>/g)].map(m => [m[1], m[2]]),
    // the note: "(upar chuno)" only right under a 7 / 14 / 30 / 60 selector (an app with updates); else today's words
    imp_card: h.includes('id="act-impact"') && h.includes('<h3>📦 Update impact</h3>') && (h.includes('uni-imp-cseg')
      ? h.includes('Ye card = har update ke 7 din pehle vs 7 din baad (upar chuno) · upar ke tiles = pichhle 7 pakke din') && h.indexOf('uni-imp-cseg') < h.indexOf('act-imp-note')
      : h.includes('Ye card = har update ke 7 din pehle vs 7 din baad · upar ke tiles = pichhle 7 pakke din') && !h.includes('(upar chuno)')),
    imp_seg: h.includes('uni-imp-cseg'),
    sections: ['act-sum', 'act-chg', 'act-impact', 'act-kpis', 'act-daily', 'act-tri', 'act-use', 'act-rev', 'act-timing'].map(s => h.indexOf('id="' + s + '"')),
    versions: [...(f.split('<table class="uni-sticky act-ver"')[1] || '').matchAll(/<tr data-ver="([^"]*)"><td class="nm">([^<]*)/g)].map(m => [m[1], m[2].replace(/&lt;/g, '<')]),
    versions_base: [...(h.split('<table class="uni-sticky act-ver"')[1] || '').matchAll(/<tr data-ver="([^"]*)"/g)].map(m => m[1]),
    use_modes: Object.fromEntries(['base', 'sess_all', 'time_new_day'].map(m => [m, { on: [...sec(out[`detail|${r.app}|${m}`] || '', 'id="act-use"', 'id="act-rev"').matchAll(/<span class="chip on" onclick="act(UM|UP|Sm)\('([a-z0-9]+)'\)">([^<]*)</g)].map(x => x[3]),
      band: /fill-opacity="\.12"/.test(sec(out[`detail|${r.app}|${m}`] || '', 'id="act-use"', 'By app version')), context: sec(out[`detail|${r.app}|${m}`] || '', 'id="act-use"', 'id="act-rev"').includes('context, not judged'),
      wait: sec(out[`detail|${r.app}|${m}`] || '', 'id="act-use"', 'id="act-rev"').includes('Sessions aur time agle GA4 fetch ke baad aayenge') }])),
    rev: { gaps: text(secIn(h, 'id="act-revgaps"', '</div>')).trim(), note: text(sec(h, 'class="faint act-revnote"', '</div>')).replace(/^[^>]*>/, '').trim(), zero_money: /\$0(\.0+)?(?![\d.])/.test(text(sec(h, 'id="act-sum"', 'id="act-chg"'))) },
    kpis: text(sec(out[`detail|${r.app}|range_all`] || '', 'id="act-kpis"', 'id="act-daily"')).trim().slice(0, 900),
    kpis_today: text(sec(out[`detail|${r.app}|range_today`] || '', 'id="act-kpis"', 'id="act-daily"')).trim().slice(0, 900),
    daily_title: h.includes('<h3>👥 Returning users — every day</h3>'), tri_title: h.includes('<h3>🔁 How many came back — install week × day</h3>'),
    use_title: h.includes('<h3>⏱️ Sessions &amp; time per user</h3>'), rev_title: h.includes('<h3>💰 Ad revenue per user</h3>'),
    chips_seen: [...new Set([...h.matchAll(/<span class="chip( on)?" onclick="act[A-Za-z]+\([^)]*\)">([^<]*)<\/span>/g)].map(m => m[2]))],
    tile_open: /class="uni-st act-t open" data-m="ret_dau"/.test(out[`detail|${r.app}|tile_open`] || ''),
    phone_short: tiles.every(t => !t.rel || (t.short && t.short.endsWith(' · 4 wks'))) };
}
// the All-apps page: count line, pooled tiles, strips (each chip's count), every opened chip's apps, the table order
const pH = out.portfolio_30d || '';
const chipsOf = h => Object.fromEntries([...h.matchAll(/data-k="([a-z0-9_]+:[a-z_]+)"[^>]*><i class="dt"><\/i>([^<]*) <b>\((\d+)\)<\/b>/g)].map(m => [m[1], { label: m[2], n: +m[3] }]));
const xp = { chips: chipsOf(pH), default_open: /data-xp="/.test(pH), open: {} };
for (const k of XP) { const h = out['xp|' + k] || '', seg = h.split('data-xp="')[1] || '';
  xp.open[k] = { panel: seg ? seg.slice(0, seg.indexOf('"')) : null, panels: (h.match(/data-xp="/g) || []).length, on: (h.match(/class="uni-sc [a-z-]+ on"/g) || []).length,
    apps: [...(seg.split('</div></div>')[0] || '').matchAll(/data-app="([^"]*)"/g)].map(m => m[1].replace(/&amp;/g, '&')), calls: [...(seg.split('</div></div>')[0] || '').matchAll(/onclick="actOpen\('([^']*)'\)"/g)].map(m => m[1]) }; }
const sorts = {};
for (const k of SORTS) for (const d of [1, -1]) sorts[k + '|' + d] = [...sec(out[`sort|${k}|${d}`] || '', 'id="act-table"', '</tbody>').matchAll(/<tr class="clk" data-app="([^"]*)"/g)].map(m => m[1].replace(/&amp;/g, '&'));
const pool = [...sec(pH, 'id="act-pool"', 'class="uni-sec"').matchAll(/<div class="uni-st act-t act-pt" data-m="([a-z0-9_]+)">([\s\S]*?)(?=<div class="uni-st act-t act-pt"|$)/g)].map(m => ({ m: m[1], text: text(m[2]).trim() }));
const portfolio = { text: T('portfolio_30d').slice(0, 6000), count: text(sec(pH, 'id="act-count">', '</div>')).trim(), pool, xp, sorts,
  chg_title: (sec(pH, 'id="act-chg"', 'id="act-updates"').match(/🔔 What changed\? \((\d+)\)/) || [])[1],
  chg_rows: [...sec(pH, 'id="act-chg"', 'id="act-updates"').matchAll(/<div class="uni-chg wa" data-fam="[^"]*" onclick="actOpen\('([^']*)'\)"/g)].map(m => m[1]),
  info_rows: (sec(pH, 'id="act-chg"', 'id="act-updates"').match(/data-info="/g) || []).length,
  older_open: (sec(out.portfolio_older_open || '', 'id="act-chg"', 'id="act-updates"').match(/data-old="/g) || []).length,
  older_nofiles: T('portfolio_nofiles').includes('open an app for its full history'),
  updates: { has: pH.includes('id="act-updates"') && pH.includes('<h3>📦 Recent updates</h3>'), rows: [...sec(pH, 'id="act-updates"', 'id="act-table"').matchAll(/onclick="uniImpGo\('([^']*)','([^']*)'(,'act')?\)"/g)].map(m => [m[1], m[2], !!m[3]]),
    uf: [...sec(pH, 'id="act-updates"', 'id="act-table"').matchAll(/onclick="uniUF\('([a-z]+)'(,'act')?\)"/g)].map(m => !!m[2]) },
  table_heads: [...sec(pH, 'id="act-table"', '</thead>').matchAll(/<th onclick="actSort\('([a-z0-9]+)'\)"[^>]*>([^<▲▼]*)/g)].map(m => [m[1], m[2].trim()]),
  table_pills: [...sec(pH, 'id="act-table"', '</tbody>').matchAll(/<span class="pill ([a-z0-9-]+)" data-st="([a-z_]+)"/g)].map(m => [m[1], m[2]]),
  strip_classes: [...sec(pH, 'class="act-strips"', 'class="uni-foot"').matchAll(/<span class="uni-sc ([a-z-]+)( on)?" data-k="([a-z0-9_]+):([a-z_]+)"/g)].map(m => [m[1], m[3], m[4]]),
  noga4: (pH.match(/<h3>🔌 Apps without GA4 data \((\d+)\)<\/h3>/) || [])[1], timing: T('timing_open').includes('D1 ~6 din, D7 ~12 din, D30 ~35 din baad.'),
  head: text(pH.slice(0, 700)).trim(), market: text(sec(pH, 'id="act-market">', '</div>')).trim(), prov_note: /ℹ️ <b>Provisional:<\/b>/.test(sec(pH, 'id="act-sum"', 'id="act-chg"')) };
// 📅 Daily — all apps: the section, its table rows (cells + tooltips), the chart's points / marks / hatch, the change chips
const pfSec = h => { const a = h.indexOf('<div class="card" id="act-pf"'), a2 = a < 0 ? h.indexOf('id="act-pf"') : a; if (a2 < 0) return '';
  const b = h.indexOf('id="act-table"', a2); return h.slice(a2, b < 0 ? undefined : b); };
const unq = x => x == null ? null : x.replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
const pfParse = h => { const s = pfSec(h), pm = s.match(/data-pts='([^']*)'/), vb = s.match(/<svg viewBox="0 0 (\d+) (\d+)"/);
  return { has: !!s, text: text(s).trim().slice(0, 3000),
    rows: [...s.matchAll(/<tr data-day="([^"]*)"( class="act-pfp")?>([\s\S]*?)<\/tr>/g)].map(m => ({ day: m[1], prov: !!m[2],
      cells: [...m[3].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(c => text(c[1]).trim()),
      tips: [...m[3].matchAll(/<td(?: class="([^"]*)")?(?: title="([^"]*)")?>/g)].map(c => unq(c[2] || null)),
      cls: [...m[3].matchAll(/<td(?: class="([^"]*)")?/g)].map(c => c[1] || ''), star: /class="act-pfs"/.test(m[3]), pill: m[3].includes('>Provisional</span>') })),
    heads: [...(s.split('<thead>')[1] || '').split('</thead>')[0].matchAll(/<th[^>]*>([^<]*)<\/th>/g)].map(m => m[1]),
    pts: pm ? JSON.parse(unq(pm[1])) : null, vbw: vb ? +vb[1] : null,
    marks: [...s.matchAll(/class="act-pf-mk" data-day="([^"]*)"/g)].map(m => m[1]), hatch: (s.match(/class="act-pf-prov"/g) || []).length,
    gmarks: [...s.matchAll(/class="act-pf-gk" data-day="([^"]*)"/g)].map(m => m[1]), inc: [...s.matchAll(/class="act-pf-inc" data-day="([^"]*)"/g)].map(m => m[1]),
    brk: [...s.matchAll(/class="act-pf-brk" data-from="([^"]*)" data-to="([^"]*)"/g)].map(m => [m[1], m[2]]), rh: (s.match(/<tr class="act-pfrh">/g) || []).length,
    rh_after: [...s.matchAll(/<tr class="act-pfrh">[\s\S]*?<\/tr><tr data-day="([^"]*)"/g)].map(m => m[1]),
    lines: [...s.matchAll(/<path class="act-pf-ln" data-s="([a-z]+)" data-f="([01])" d="([^"]*)"/g)].map(m => ({ s: m[1], f: +m[2], xs: [...m[3].matchAll(/[ML](-?[\d.]+) /g)].map(x => +x[1]) })),
    mlabels: [...s.matchAll(/class="act-pf-ml"[^>]*>([^<]*)<\/text>/g)].map(m => m[1]),
    chips: [...s.matchAll(/<span class="act-pfc" data-k="([a-z]+)" data-day="([^"]*)" title="[^"]*">([^<]*)<\/span>/g)].map(m => ({ k: m[1], day: m[2], text: unq(m[3]) })),
    chip_more: (s.match(/onclick="actPfMX\(\)">([^<]*)</) || [])[1] || null,
    ranges: [...s.matchAll(/<span class="chip( on)?" onclick="actPfR\('([a-z0-9]+)'\)">([^<]*)<\/span>/g)].map(m => [m[2], m[3], !!m[1]]),
    last: text(sec(s, 'id="act-pf-last"', '</div>').replace(/^[^>]*>/, '')).trim(), more: text(sec(s, 'class="act-pfmore"', '</div>').replace(/^[^>]*>/, '')).trim().slice(0, 300),
    more_calls: [...s.matchAll(/onclick="actPfMore\((\d+)\)"/g)].map(m => +m[1]), note: text(sec(s, 'class="faint act-pfnote"', '</div>').replace(/^[^>]*>/, '')).trim(),
    prov_note: /ℹ️ <b>Provisional:<\/b>/.test(s), lgd: text(sec(s, '<div class="lgd">', '</div>')).trim(),
    pool: [...sec(h, 'id="act-pool"', 'class="uni-sec"').matchAll(/<div class="uni-st act-t act-pt" data-m="([a-z0-9_]+)">([\s\S]*?)(?=<div class="uni-st act-t act-pt"|$)/g)].map(m => text(m[2]).trim()),
    order: ['id="act-sum"', 'id="act-chg"', 'id="act-updates"', 'id="act-pf"', 'id="act-table"'].map(k => h.indexOf(k)), full_len: h.length };
};
const pfWide = [];
for (const [k, v] of Object.entries(out)) { if (!k.startsWith('pf|') || k === 'pf|desktop') continue; const s = pfSec(v);
  for (const m of s.matchAll(/min-width:(\d+)px/g)) { const before = s.slice(Math.max(0, m.index - 400), m.index); if (+m[1] > 340 && !/<div class="uni-scroll[^"]*"[^>]*><table [^>]*$/.test(before)) pfWide.push(k + ': ' + m[1]); }
  for (const m of s.matchAll(/<table /g)) { const before = s.slice(Math.max(0, m.index - 60), m.index); if (!/<div class="uni-scroll[^"]*"[^>]*>$/.test(before)) pfWide.push(k + ': table outside a scroller'); }
  for (const m of s.replace(/<svg[\s\S]*?<\/svg>/g, '').matchAll(/\swidth="(\d+)"/g)) if (+m[1] > 340) pfWide.push(k + ': fixed width ' + m[1]);
  for (const m of s.matchAll(/<svg [^>]*>/g)) if (!/style="width:100%/.test(m[0])) pfWide.push(k + ': chart without a fluid width'); }
const pf = { src: PF_SRC, file: PF, vis: PF_VIS, big: PF_BIG, wide: pfWide, load: pfLoad, ptr: FX.dashboard_active.portfolio || null,
  s: Object.fromEntries(Object.keys(out).filter(k => k.startsWith('pf|')).map(k => [k.slice(3), pfParse(out[k])])),
  portfolio_30d: pfParse(out.portfolio_30d || ''), throw_rest: ['id="act-sum"', 'id="act-chg"', 'id="act-table"'].every(k => (out['pf|throw'] || '').includes(k)) };
// Alerts screen
const alertsOf = h => ({ sub: h.includes('👥 Active users (GA4)'), cards: (h.match(/data-metrics="active"/g) || []).length, open_app: [...h.matchAll(/onclick="actGo\('([^']*)'\)">Open app →/g)].map(m => m[1]),
  upd: [...h.matchAll(/onclick="uniImpGo\('([^']*)','([^']*)','act'\)">Update detail →/g)].map(m => [m[1], m[2]]), chip: h.includes(`onclick="filterAlerts('active')"`),
  total: (text(h).match(/Total issues (\d+)/) || [])[1] });
const alerts = { all: alertsOf(out.alerts_all || ''), per_app: Object.fromEntries(rows.map(r => [r.app, alertsOf(out['alerts|' + r.app] || '')])), no_active: alertsOf(out.alerts_no_active || ''), no_active_tab: T('no_active') };
const syn = {
  ads_dir: ((out.ads_dir || '').match(/data-m="arpdau" data-st="[a-z_]+"[\s\S]*?<span class="pill ([a-z0-9-]+)" data-st="maybe_dn"[^>]*>([^<]*)<\/span>/) || [])[2] || null,
  early: { row: /data-info="early"[\s\S]*?>Provisional<\/span>/.test(out.early || ''), pill: /data-info="early"><span class="sv"><span class="pill p-b"/.test(out.early || ''),
    title: ((out.early || '').match(/🔔 What changed\? \((\d+)\)/) || [])[1], open: (out.early || '').split('<hr>')[1], counted: /<div class="uni-chg na" data-fam/.test((out.early || '').split('data-info="early"')[1] || '') },
  zones: text(sec(out.zones || '', 'class="faint act-revnote"', '</div>')).replace(/^[^>]*>/, ''), zones_gmt: text(sec(out.zones_gmt || '', 'class="faint act-revnote"', '</div>')).replace(/^[^>]*>/, ''),
  zones_same: text(sec(out.zones_same || '', 'class="faint act-revnote"', '</div>')).replace(/^[^>]*>/, ''),
  six_days: T('six_days').includes('(6 of 7 days)'),
  searching: { text: T('edge_searching').includes('dhoondh rahe hain'), edge_row: (out.edge_searching || '').includes('Install-day return data starts'), grid: (out.edge_searching || '').includes('act-grid') },
  wait: { text: T('edge_wait').includes('🔁 Wapsi (D1/D7) ka data agle GA4 fetch ke saath aayega.'), tiles: [...(out.edge_wait || '').matchAll(/data-m="(d1|d7)" data-st="wait"[\s\S]*?>Waiting for data<\/span>/g)].length },
  found: { edge_row: (out.edge_found || '').includes('↧ Install-day return data starts') },
  usage_wait: { tiles: [...(out.usage_wait || '').matchAll(/data-m="(sess|time)" data-st="wait"[\s\S]*?>Waiting for data<\/span>/g)].length, card: T('usage_wait').includes('Sessions aur time agle GA4 fetch ke baad aayenge') },
  no_alert_red: { red: /<span class="pill p-r" data-st="worse"/.test(out.no_alert_red || ''), green: /<span class="pill p-g" data-st="better"/.test(out.no_alert_red || ''),
    blue: (out.no_alert_red || '').match(/<span class="pill p-b" data-st="(worse|better)"/g) || [] },
  all_wait: { dashes: [...(out.all_wait || '').matchAll(/data-m="[a-z0-9_]+" data-st="wait"[\s\S]*?<div class="v">—<\/div>/g)].length, zero_money: /\$0(\.0+)?(?![\d.])/.test(text((out.all_wait || '').replace(/<svg[\s\S]*?<\/svg>/g, ''))) },   // chart axis ticks aside
};
// red / green on the page: every red / green chip (tiles, table, strips) belongs to a metric with an open alert of that severity
const AM = { ret_dau: ['ret_dau'], d1: ['d1'], d7: ['d7'], sess: ['sess', 'usage'], time: ['time', 'usage'], arpdau: ['ads', 'arpdau'] };
const colour = [];
for (const r of rows) {
  const al = (FX.dashboard_active.alerts || []).filter(x => x.app_id === r.app_id).concat(((dets[r.key] || {}).changes || {}).open || []);
  for (const t of (apps[r.app] || { tiles: [] }).tiles) {
    if (t.cls === 'p-r' && !al.some(x => (AM[t.m] || []).includes(x.metric) && x.severity === 'warning')) colour.push(r.app + ' ' + t.m + ' red');
    if (t.cls === 'p-g' && !al.some(x => (AM[t.m] || []).includes(x.metric) && x.severity === 'good')) colour.push(r.app + ' ' + t.m + ' green');
  }
}
// the grid's "N installs" (the rate's base): unknown (null — a week without a rate day) reads "—", never 0
const ginst = [];
for (const r of rows) {
  const d = dets[r.key]; if (!d || !((d.tri || {}).rows || []).length || (d.edges || {}).ret_state === 'wait') continue;
  const lab = u => { const h = run(`(()=>{ ${RESET} ${openApp(r)} ACTPRE=true; ACTTRIEXP=true; const d=JSON.parse(JSON.stringify(ACTD[${J(r.key)}])); d.tri.rows.forEach(x=>{ x.users=${J(u)}; }); return actTriCard(d); })()`);
    const tb = (h.split('<tbody>')[1] || '').split('</tbody>')[0], m = tb.match(/data-week="[^"]*"><td class="nm"[\s\S]*?<\/td>/);
    return m ? text(m[0]).trim() : null; };
  try { ginst.push({ app: r.app, none: lab(null), some: lab(12345) }); } catch (e) { errors.push('ginst ' + r.app + ': ' + e.message); }
  break;
}
// the hourly refresh: the 📅 Daily file in memory is dropped when the pointer's sig changes — even with the tab's asset_v
// the same (an app's slice can fail / come back while every per-app file stays as it was) — and kept when it doesn't
async function pfRefreshCheck() {
  const o = {};
  for (const [nm, sig] of [['same', ''], ['changed', 'c0ffee000000'], ['gone', null]]) {
    o[nm] = await run(`(async()=>{ const keep={l:loadDashboardData, r:render, s:show, d:DATA}, ptr=DATA.active.portfolio;
      const act=Object.assign({}, DATA.active, {portfolio: ${sig === null ? 'null' : `Object.assign({}, ptr, ${sig ? `{sig:'${sig}'}` : '{}'})`}});
      const D2=Object.assign({}, DATA, {active: act}); loadDashboardData=async()=>D2; render=()=>{}; show=()=>{};
      ACTPF=__PF; ACTPFSIG=ptr.sig; ACTPFC=null; ACTVER=DATA.active.asset_v;
      try{ await refreshData(); return {kept: ACTPF===__PF, same_asset_v: ACTVER===act.asset_v}; }
      finally{ loadDashboardData=keep.l; render=keep.r; show=keep.s; DATA=keep.d; ACTPF=__PF; ACTPFSIG=ptr.sig; ACTPFC=null; } })()`);
  }
  return o;
}
(async () => {
try { pf.refresh = await pfRefreshCheck(); } catch (e) { errors.push('pf refresh: ' + e.message); }
console.log(JSON.stringify({
  scenarios: Object.keys(out).length, errors, bad, jargon: jargon.slice(0, 20), devanagari, titles: String(run('TITLES.active.join("|")')),
  apps, portfolio, pf, imp, win, ids, header, gofrom, alerts, syn, retc, retbase, ginst, grid, colour,
  fix: { rev_market: text(sec(fx2.rev_market, 'class="act-mk"', '</div></div>')).trim(), pf_market_now: text(sec(fx2.pf_market_now, 'id="act-market">', '</div>')).trim(),
    pf_market_old: text(sec(fx2.pf_market_old, 'id="act-market">', '</div>')).trim(), inst_opp: text(fx2.inst_opp), inst_same: text(fx2.inst_same), inst_zero: text(fx2.inst_zero),
    hint_ads: text(fx2.hint_ads), hint_ret: text(fx2.hint_ret), linked: text(fx2.linked),
    total_linked: (text(fx2.alerts_linked).match(/Total issues (\d+)/) || [])[1], total_unlinked: (text(fx2.alerts_unlinked).match(/Total issues (\d+)/) || [])[1],
    pool_wait: [...sec(fx2.pool_wait, 'id="act-pool"', 'class="uni-sec"').matchAll(/<div class="uni-st act-t act-pt" data-m="([a-z0-9_]+)">([\s\S]*?)(?=<div class="uni-st act-t act-pt"|$)/g)].map(m => ({ m: m[1], text: text(m[2]).trim() })),
    table_wait: text(sec(fx2.pool_wait, 'id="act-table-wait"', '</div>')).replace(/^[^>]*>/, '').trim(), young_tile: text(fx2.young_tile) },
  alert_cards: out.alert_cards || '', texts: Object.fromEntries(Object.entries(out).filter(([k]) => /^(detail\|[^|]*\|base|portfolio_30d|no_active|noga4\|)/.test(k)).map(([k, v]) => [k, T(k).slice(0, 8000)])),
}, null, 1));
})();
