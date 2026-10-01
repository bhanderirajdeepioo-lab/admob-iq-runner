// The installs vs per-user split's frontend (SPEC_SPLIT §4, §6.2): runs the REAL dashboard script (frontend/index.html's
// <script>) in a node vm with stub browser globals and feeds it (1) synthetic vectors written by tests/test_split_frontend.py
// (every kind, a random grid, the spec's worked examples, the pooled All-apps tile, the week-over-week, the legacy
// fallback, the $ ⇄ ₹ toggle) and (2) the committed fixtures, whose every host carrying a split must draw its block.
// Prints one JSON report; tests/test_split_frontend.py asserts on it.
// usage: node split_frontend.js <script.js> <vectors.json> <active.json> <uninstall.json> <value.json>
const fs = require('fs'), vm = require('vm');
const [scriptPath, vecPath, actPath, uniPath, valPath] = process.argv.slice(2);
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
const J = JSON.stringify;
const text = h => String(h || '').replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
// a block's lines, as the owner reads them (one entry per line element)
const lines = h => [...String(h || '').matchAll(/<(?:div|span) class="(spk|spl|spn|sps)">([\s\S]*?)<\/(?:div|span)>/g)].map(m => ({ k: m[1], t: text(m[2]) }));
const V = JSON.parse(fs.readFileSync(vecPath, 'utf8'));
ctx.__V = V;
run(`DATA = {apps_catalog: [], today_date: '2026-09-28', currency: 'USD', usd_inr: 83, alerts: {counts: {}, items: []}}; CURVIEW = 'USD';`);
const out = { errors, vec: [], grid: [], pool: [], wow: [], legacy: {}, cur: {}, fixtures: {} };

// (1) every vector: the contract object, the one-line form, the block (html, its lines, its text) — at $ and at ₹
const MO = { act: `{money:v=>actMoney(v),big:v=>actMoney(v,undefined,true)}`, val: `VAL_SPLIT_O`, none: `{}` };
for (const v of V.vectors) {
  try {
    const r = JSON.parse(run(`(()=>{ const h=__V.vectors[${out.vec.length}].host, o=${MO[v.money || 'none']};
      CURVIEW='USD'; const S=splitOf(${J(v.kind)},h), html=splitHtml(${J(v.kind)},h,o), row=splitHtml(${J(v.kind)},h,Object.assign({tag:'span'},o)), line=splitTxt(${J(v.kind)},h);
      CURVIEW='INR'; const inr=splitHtml(${J(v.kind)},h,o); CURVIEW='USD';
      return JSON.stringify({S,html,row,line,inr}); })()`));
    out.vec.push({ id: v.id, kind: v.kind, S: r.S, line: r.line, html: r.html, text: text(r.html), lines: lines(r.html), row_lines: lines(r.row), row_text: text(r.row),
      row_end: /<\/span><\/span>$/.test(r.row) || r.row === '', inr_text: text(r.inr) });
  } catch (e) { errors.push('vec ' + v.id + ': ' + e.message); out.vec.push({ id: v.id, kind: v.kind, S: null }); }
}
// a random grid: only the shown numbers and the one-line form (10k vectors, fast)
try { out.grid = JSON.parse(run(`JSON.stringify(__V.grid.map(g=>{ const S=splitOf(g.kind,g.host); return S&&S.shown?[S.shown.total,S.shown.from_installs,S.shown.trend,S.shown.per_user,S.per_user.rel,S.total.rel,S.from_installs.rel,S.trend?S.trend.rel:null,splitLine(S)]:null; }))`)); }
catch (e) { errors.push('grid: ' + e.message); }
// the pooled All-apps tile: the contract object and its block
for (let i = 0; i < V.pool.length; i++) {
  try { out.pool.push(JSON.parse(run(`(()=>{ const S=splitPool(__V.pool[${i}]); return JSON.stringify({S,html:splitBlock(S),line:splitLine(S)}); })()`))); }
  catch (e) { errors.push('pool ' + i + ': ' + e.message); out.pool.push(null); }
}
for (const p of out.pool) if (p) p.text = text(p.html);
// the portfolio's week-over-week (dau): the same apps' new installs a week apart
for (let i = 0; i < V.wow.length; i++) {
  try { out.wow.push(String(run(`splitWow(__V.wow[${i}],7)`))); } catch (e) { errors.push('wow ' + i + ': ' + e.message); out.wow.push(null); }
}
// failure isolation: a host that throws inside → nothing, never an exception
try { out.isolated = JSON.parse(run(`(()=>{ const bad={get sp(){ throw new Error('x'); }}; return JSON.stringify([splitOf('rate',bad),splitHtml('rate',bad),splitTxt('rate',bad),splitPool([{get m(){ throw new Error('y'); }}]),splitWow(null,3)]); })()`)); }
catch (e) { errors.push('isolated: ' + e.message); }

// (2) the fixtures: the page's own call sites, every tab
const FA = JSON.parse(fs.readFileSync(actPath, 'utf8')), FU = JSON.parse(fs.readFileSync(uniPath, 'utf8')), FV = JSON.parse(fs.readFileSync(valPath, 'utf8'));
ctx.__FA = FA; ctx.__FU = FU; ctx.__FV = FV;
run(`DATA = {apps_catalog: [], today_date: '2026-09-25', currency: 'USD', usd_inr: 83, alerts: {counts: {}, items: []}, uninstall: __FU.dashboard_uninstall,
       active: __FA.dashboard_active, value: __FV.dashboard_value};
     UNI = __FU.asset; UNIERR = false; UNICOH = {}; ACTD = {}; VALD = {};
     for (const [k, d] of Object.entries(__FA.app_files || {})) ACTD[k] = d;
     for (const [k, d] of Object.entries(__FV.app_files || {})) VALD[k] = d; CURVIEW='USD';
     ACTPF = __FA.portfolio || null; ACTPFSIG = (DATA.active.portfolio || {}).sig || null; ACTPFC = null;`);   // KPIWINDOW: the pooled tiles now read this (not r.m) — preload it like active_frontend.js does
const has = h => h && typeof h === 'object' && h.sp != null;
const drawn = sp => Array.isArray(sp) && !(sp[0] === 'no' && (sp[1] === 'error' || !sp[1])) && !(sp[0] === 'pu' && sp.length < 2);
const F = { hosts: 0, blocks: 0, missing: [], bad: [], texts: [], pooled: null, any: false };
const chk = (name, h) => { const bad = ['undefined', 'NaN', '[object Object]', 'Infinity'].filter(w => h.includes(w)); if (bad.length) F.bad.push(name + ': ' + bad.join(',')); };
function expect(name, host, html, card) {
  if (!has(host)) return; F.any = true; if (!drawn(host.sp) || (card && ['no', 'pu'].includes(host.sp[0]))) return; F.hosts++;   // a card: the one-line form (none for notes / pata nahi)
  if (/class="split( [a-z-]+)*"/.test(html)) F.blocks++; else F.missing.push(name);
  chk(name, html); F.texts.push(...[...html.matchAll(/<(div|span) class="split[^"]*"[^>]*>([\s\S]*?)<\/\1><\/(?:div|span)>/g)].map(m => text(m[2])).slice(0, 3));
}
const RESET = `APP=''; RANGE='30d'; innerWidth=375; ACTTILEEXP=''; UNIIMPWIN=7; UNIIMPWK={}; VALTILEEXP='';`;
try {
  for (const r of FA.dashboard_active.apps) {
    const d = (FA.app_files || {})[r.key]; if (!d) continue;
    for (const k of ['ret_dau', 'd1', 'd7', 'arpdau']) {
      const M = (d.tiles || {})[k]; if (!has(M) || (M.sp || [])[0] === 'pu') continue;
      const h = String(run(`(()=>{ ${RESET} ACTTILEEXP=${J(k)}; const r=DATA.active.apps.find(x=>x.key===${J(r.key)}); return actSumCard(ACTD[${J(r.key)}],r); })()`));
      const tile = (h.split(`data-m="${k}"`)[1] || '').split('<div class="uni-st act-t')[0];
      expect(`act tile ${r.app} ${k}`, M, tile);
    }
    // the per-user tiles' "Saath me:" notes (sessions, time, ads per user, ad rate, revenue per user): once, under the tiles
    { const h = String(run(`(()=>{ ${RESET} const r=DATA.active.apps.find(x=>x.key===${J(r.key)}); return actSumCard(ACTD[${J(r.key)}],r); })()`));
      const nb = (h.match(/<div class="split act-notes"[^>]*>([\s\S]*?)<\/div><\/div>/) || [""])[0];
      const said = [...nb.matchAll(/<div class="sps">(Saath me: [^<]*)<\/div>/g)].map(m => m[1]);
      F.notes = (F.notes || 0) + said.length; if (new Set(said).size !== said.length) F.bad.push(`act notes twice ${r.app}`);
      if ((h.match(/Saath me: /g) || []).length !== said.length) F.bad.push(`act notes outside the card line ${r.app}`);
      for (const k of ['sess', 'time', 'ads', 'ecpm', 'arpdau']) { const M = (d.tiles || {})[k]; if (!has(M) || !drawn(M.sp)) continue;
        const S = run(`JSON.stringify(splitOf(${J((M.sp || [])[0] === 'rev' ? 'rev' : 'pu')},ACTD[${J(r.key)}].tiles[${J(k)}]))`), nt = (JSON.parse(S) || {}).note || [];
        for (const x of nt) { F.any = true; F.hosts++; if (said.some(t => t.startsWith('Saath me: ' + ({ new: 'naye users', net: 'dusre ad', rec: 'haal ke', paid: 'ads wale' })[x[0]]))) F.blocks++; else F.missing.push(`act notes ${r.app} ${k} ${x[0]}`); } } }
    const C = d.changes || {};
    (C.open || []).forEach((x, i) => expect(`act row ${r.app} ${i}`, x, String(run(`actChangeRow(ACTD[${J(r.key)}].changes.open[${i}],false,false)`))));
    (C.info || []).forEach((o, i) => expect(`act info ${r.app} ${i}`, o, String(run(`actInfoRow(ACTD[${J(r.key)}].changes.info[${i}])`))));
  }
  (FA.dashboard_active.alerts || []).forEach((x, i) => {
    expect(`act card ${i}`, x, String(run(`(()=>{ const c=actAlertCards([DATA.active.alerts[${i}]]); return c.replace('class="split-c"','class="split"'); })()`)), true);
    chk(`act all-apps row ${i}`, String(run(`actChangeRow(DATA.active.alerts[${i}],true,false)`)));
  });
  const pf = String(run(`(()=>{ ${RESET} return actSumPortfolio(actRows()); })()`)); chk('act portfolio', pf);
  F.pooled = { any: FA.dashboard_active.apps.some(r => has(((r.m || {}).ret_dau))), text: text((pf.match(/<div class="split act-pool-split[^"]*"[^>]*>[\s\S]*?<\/div><\/div>/) || [''])[0]),
    d1: text((pf.split('data-m="d1"')[1] || '').split('<div class="uni-st')[0]),
    ret: text((pf.split('data-m="ret_dau"')[1] || '').split('<div class="uni-st')[0]) };
  for (const a of FU.asset.apps) {
    const id = J(a.app_id);
    (a.alerts || []).forEach((x, i) => { if (x.family === 'impact' || x.family === 'impact_late') return;
      expect(`uni row ${a.app} ${i}`, x, String(run(`uniChangeRow(UNI.apps.find(z=>z.app_id===${id}).alerts[${i}],false,false)`)));
      expect(`uni card ${a.app} ${i}`, x, String(run(`uniAlertCards([UNI.apps.find(z=>z.app_id===${id}).alerts[${i}]]).replace('class="split-c"','class="split"')`)), true); });
    (a.old_changes || []).forEach((o, i) => expect(`uni old ${a.app} ${i}`, o, String(run(`uniOldRow(UNI.apps.find(z=>z.app_id===${id}).old_changes[${i}])`))));
    if (has(a.rate_now) && a.rate_now.last7 != null) expect(`uni rate ${a.app}`, a.rate_now, String(run(`uniRateTile(UNI.apps.find(z=>z.app_id===${id}))`)));
    const tb = String(run(`uniCpCard(UNI.apps.find(z=>z.app_id===${id}))`)); chk(`uni table ${a.app}`, tb);
    (a.table || []).forEach((t, i) => { if (has(t) && drawn(t.sp)) { F.hosts++; if (/<td class="uni-num" title="[^"]*(installs se|users se)[^"]*">/.test(tb)) F.blocks++; else F.missing.push(`uni table ${a.app} ${i}`); } });
    const blocks = ((a.impact || {}).updates || []);
    blocks.forEach((b, bi) => { for (const N of [7, 14, 30, 60]) {
      const R = N === 7 ? (b.rows || {}) : (((b.by_window || {})[String(N)] || {}).rows || {});
      if (N !== 7 && !(b.by_window || {})[String(N)]) continue;
      const h = String(run(`(()=>{ ${RESET} const a=UNI.apps.find(z=>z.app_id===${id}), b=uniImpBlocks(a).find(x=>x.key===${J(b.key)}); UNIIMPWK={[b.key]:${N}}; return uniImpBlock(a,b,true); })()`));
      chk(`uni impact ${a.app} ${bi} ${N}`, h);
      // the window's "Saath me:" notes: once each, under the table (never on every row)
      const said = [...h.matchAll(/Saath me: [^<]*/g)].map(m => m[0]), nb = (h.match(/<div class="split uni-imp-notes"[\s\S]*?<\/div><\/div>/) || [''])[0];
      if (new Set(said).size !== said.length) F.bad.push(`impact notes twice ${a.app} ${bi} ${N}`);
      if ((nb.match(/Saath me: /g) || []).length !== said.length) F.bad.push(`impact notes outside the table line ${a.app} ${bi} ${N}`);
      F.impNotes = (F.impNotes || 0) + said.length;
      for (const [k, r] of Object.entries(R)) { if (!has(r) || !drawn(r.sp) || !['worse', 'better', 'same', 'unsure', 'market'].includes(r.status)) continue; F.any = true; F.hosts++;
        if (h.includes(`<tr class="uni-imp-sp" data-sp="${k}">`)) F.blocks++; else F.missing.push(`impact ${a.app} ${b.key} ${N} ${k}`); }
    } });
  }
  const up = String(run(`(()=>{ ${RESET} return uniScreen(); })()`)); chk('uni portfolio', up);
  for (const r of FV.dashboard_value.apps || []) {
    const d = (FV.app_files || {})[r.key]; if (!d) continue;
    for (const k of ['b7', 'rpi', 'cpi']) { const M = (d.tiles || {})[k]; if (!has(M)) continue;
      const h = String(run(`(()=>{ ${RESET} VALTILEEXP=${J(k)}; const r=DATA.value.apps.find(x=>x.key===${J(r.key)}); return valSumCard(VALD[${J(r.key)}],r); })()`));
      expect(`val tile ${r.app} ${k}`, M, (h.split(`data-m="${k}"`)[1] || '').split('<div class="uni-st val-t')[0]); }
    ((d.changes || {}).open || []).forEach((x, i) => expect(`val row ${r.app} ${i}`, x, String(run(`valChangeRow(VALD[${J(r.key)}].changes.open[${i}],false,false)`))));
  }
  (FV.dashboard_value.alerts || []).forEach((x, i) => expect(`val card ${i}`, x, String(run(`valAlertCards([DATA.value.alerts[${i}]]).replace('class="split-c"','class="split"')`)), true));
} catch (e) { errors.push('fixtures: ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); }
F.texts = F.texts.slice(0, 400);
out.fixtures = F;
// the All-apps pooled block: drawn only while the data carries the split (a synthetic live row / every sp stripped)
try {
  out.pool_page = JSON.parse(run(`(()=>{ ${RESET} const A=DATA.active, keep=JSON.stringify({apps:A.apps,alerts:A.alerts});
    try{ A.alerts=[]; A.apps=JSON.parse(keep).apps; A.apps.forEach((r,i)=>{ const M=r.m&&r.m.ret_dau; if(M) M.sp=i===0?['ret',10,100,110,50,55,10,10,30,0]:null; });
      const live=/class="split act-pool-split/.test(actSumPortfolio(actRows()));
      A.apps.forEach(r=>{ if(r.m&&r.m.ret_dau) delete r.m.ret_dau.sp; }); const legacy=/class="split act-pool-split/.test(actSumPortfolio(actRows()));
      return JSON.stringify({live,legacy}); } finally{ const k=JSON.parse(keep); A.apps=k.apps; A.alerts=k.alerts; } })()`));
} catch (e) { errors.push('pool page: ' + e.message); }

// the SPLIT switch off (every sp null) draws exactly what an older file (no sp key at all) draws: every screen, byte for byte
try {
  const strip = (o, del) => { if (Array.isArray(o)) o.forEach(x => strip(x, del)); else if (o && typeof o === 'object') for (const k of Object.keys(o)) { if (k === 'sp') { if (del) delete o[k]; else o[k] = null; } else strip(o[k], del); } return o; };
  const screens = del => { ctx.__SA = strip(JSON.parse(J(FA)), del); ctx.__SU = strip(JSON.parse(J(FU)), del); ctx.__SV = strip(JSON.parse(J(FV)), del);
    return JSON.parse(run(`(()=>{ const keep={D:DATA,U:UNI,A:ACTD,V:VALD};
      try{ DATA=Object.assign({},DATA,{uninstall:__SU.dashboard_uninstall,active:__SA.dashboard_active,value:__SV.dashboard_value}); UNI=__SU.asset; ACTD={}; VALD={};
        for(const [k,d] of Object.entries(__SA.app_files||{})) ACTD[k]=d; for(const [k,d] of Object.entries(__SV.app_files||{})) VALD[k]=d;
        const r=[]; APP=''; RANGE='30d'; r.push(actScreen(), uniScreen());
        for(const x of DATA.active.apps) for(const t of ['ret_dau','d1','arpdau']){ ACTTILEEXP=t; ACTCLEXP=true; if(ACTD[x.key]) r.push(actDetail(x,ACTD[x.key])); }
        for(const a of UNI.apps){ APP=a.app; UNIAPP=a.app_id; UNIOLDEXP=true; UNICPEXP=true; r.push(uniScreen()); APP='';
          for(const b of uniImpBlocks(a)) for(const N of [7,14,30,60]){ UNIIMPWK={[b.key]:N}; r.push(uniImpBlock(a,b,true)); } }
        for(const x of ['worse','better','unsure']){ UNISTEXP=x; r.push(uniScreen()); } UNISTEXP='';
        for(const x of (DATA.value.apps||[])) for(const t of ['b7','rpi','cpi']){ VALTILEEXP=t; if(VALD[x.key]) r.push(valSumCard(VALD[x.key],x)+valChangesCard(VALD[x.key],x)); }
        r.push(actAlertCards(DATA.active.alerts)+uniAlertCards(DATA.uninstall.alerts)+valAlertCards(DATA.value.alerts));
        return JSON.stringify(r); }
      finally{ DATA=keep.D; UNI=keep.U; ACTD=keep.A; VALD=keep.V; ${RESET} UNIAPP=''; UNIOLDEXP=false; UNICPEXP=false; ACTCLEXP=false; } })()`)); };
  const norm = h => h.replace(/(id="|url\(#|href="#)([A-Za-z-]+?)\d+/g, '$1$2#');   // the charts' running gradient ids
  const off = screens(false).map(norm), old = screens(true).map(norm);
  const d0 = off.findIndex((h, i) => h !== old[i]); let at = -1; if (d0 >= 0) { at = 0; while (off[d0][at] === old[d0][at]) at++; }
  out.switch_off = { screens: off.length, differ: off.filter((h, i) => h !== old[i]).length, splits: off.filter(h => /class="split/.test(h)).length,
    first: d0 < 0 ? null : [d0, off[d0].slice(Math.max(0, at - 150), at + 150), old[d0].slice(Math.max(0, at - 150), at + 150)] };
} catch (e) { errors.push('switch off: ' + e.message); }

// (3) legacy fallback + the tile's own words: the same tile with and without its split
try {
  const r0 = FA.dashboard_active.apps.find(r => ((FA.app_files[r.key] || {}).tiles || {}).ret_dau && FA.app_files[r.key].tiles.ret_dau.base) || FA.dashboard_active.apps[0];
  out.legacy = JSON.parse(run(`(()=>{ ${RESET} ACTTILEEXP='ret_dau'; const r=DATA.active.apps.find(x=>x.key===${J(r0.key)}), d=JSON.parse(JSON.stringify(ACTD[r.key]));
    d.split=null; d.inst={mode:'elastic',rel:-0.33,part:-0.057}; const T=d.tiles.ret_dau, b=T.base;
    const nosp=Object.assign({},T,{rel:0.075,v:b*1.075}); delete nosp.sp; d.tiles.ret_dau=nosp; const legacy=actSumCard(d,r);
    d.tiles.ret_dau=Object.assign({},nosp,{sp:null}); const nul=actSumCard(d,r);
    d.tiles.ret_dau=Object.assign({},nosp,{sp:['ret',-0.057*b,0,0,1000,670,null,null,null,3]}); const withSp=actSumCard(d,r);
    d.tiles.ret_dau=Object.assign({},nosp,{sp:['no','cohorts']}); const none=actSumCard(d,r);
    d.tiles.ret_dau=Object.assign({},nosp,{sp:['no','error']}); const err=actSumCard(d,r);
    const al={id:'x',family:'act_drift',metric:'ret_dau',severity:'warning',dir:'down',app:r.app,app_id:r.app_id,before:20000,now:18000,rel:-0.1,tags:['installs'],text:'x',since:'2026-09-01',data_till:'2026-09-20'};
    const row0=actChangeRow(al,false,false), row1=actChangeRow(Object.assign({},al,{sp:['ret',-1500,3375,1785,900,500,10.4,9.9,30,0]}),false,false);
    const row2=actChangeRow(Object.assign({},al,{metric:'ads',sp:['pu',['new',5,9]]}),false,false), row3=actChangeRow(Object.assign({},al,{sp:['no','cohorts']}),false,false);
    return JSON.stringify({legacy,nul,withSp,none,err,row0,row1,row2,row3}); })()`));
  const L = out.legacy; for (const k of Object.keys(L)) L[k] = { html: L[k].slice(0, 20000), text: text((L[k].split('data-m="ret_dau"')[1] || L[k]).split('data-m="d1"')[0]), split: /class="split/.test((L[k].split('data-m="ret_dau"')[1] || L[k]).split('data-m="d1"')[0]) };
} catch (e) { errors.push('legacy: ' + e.message); }
console.log(JSON.stringify(out));
