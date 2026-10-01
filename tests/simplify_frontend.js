// SPEC_SIMPLIFY's page contract (one vocabulary for Uninstall / Active users / Install value + the Alerts screen): runs
// the REAL dashboard script (frontend/index.html's largest <script>) in a node vm with stub browser globals on the committed
// synthetic fixtures (tests/fixtures/uninstall_sample.json, active_sample.json, value_sample.json) and made-up rows, and
// prints ONE JSON report; tests/test_simplify_frontend.py asserts on it.
//   usage: node simplify_frontend.js <script.js> <uninstall_sample.json> <active_sample.json> <value_sample.json>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath, uniPath, actPath, valPath] = process.argv.slice(2);
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const errors = [];
const store = () => ({ getItem: () => null, setItem() {}, removeItem() {} });
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document: any, localStorage: store(), sessionStorage: store(), navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', reload() {} }, history: any,
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean,
  RegExp, Error, Set, Map, Float64Array, isNaN, isFinite, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
  performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 375, innerHeight: 812, scrollTo() {}, alert() {},
  confirm: () => false, IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const J = JSON.stringify;
const UF = JSON.parse(fs.readFileSync(uniPath, 'utf8')), AF = JSON.parse(fs.readFileSync(actPath, 'utf8')), VF = JSON.parse(fs.readFileSync(valPath, 'utf8'));
ctx.__U = UF; ctx.__A = AF; ctx.__V = VF;
const TODAY = '2026-09-25';
// one dashboard: the three sections of the fixtures, two synthetic ad-unit alerts, one approved-range breach
run(`DATA = {apps_catalog: [{app_id:'s~1', app_name:'Demo Small', account_id:'pub-0000000000000001'}], today_date: ${J(TODAY)}, latest_complete: '2026-09-24', generated_at: '2026-09-25T03:30:00Z', currency: 'USD', usd_inr: 84,
  placements: [], range_alerts: [{place:'demo_banner', app:'Demo App', severity:'warning', dir:'above', message:'eCPM $9.99 — approved range $1.00–$5.00 se upar', id:'u0'}],
  alerts: {counts: {critical: 1, warning: 1, watch: 1}, min_share: 0.005, min_usd: 10, floor: {}, items: [
    {place:'demo_banner', id:'u1', app:'Demo App', country:'All', base_rev:40, severity:'critical', kind:'spike', lost:0, started:'2026-09-22', metrics:[{metric:'ctr', message:'CTR spike', current:0.2, kind:'spike', started:'2026-09-22'}]},
    {place:'demo_inter', id:'u2', app:'Demo App', country:'All', base_rev:30, severity:'warning', kind:'drop', lost:12, started:'2026-08-30', metrics:[{metric:'revenue', message:'revenue down 45%', current:16, lost:12, kind:'drop', started:'2026-08-30'}]},
    {place:'demo_show', id:'u3', app:'Demo App', country:'All', base_rev:20, severity:'watch', kind:'drop', lost:0, started:'2026-09-24', metrics:[{metric:'show_rate', message:'show_rate down 20pt', current:0.4, kind:'drop', started:'2026-09-24'}]}]},
  uninstall: __U.dashboard_uninstall, active: __A.dashboard_active, value: __V.dashboard_value};
  UNI = __U.asset; UNIERR = false; UNICOH = {}; ACTD = {}; VALD = {}; CURVIEW = 'USD';
  ACTPF = __A.portfolio || null; ACTPFSIG = (DATA.active.portfolio || {}).sig || null; ACTPFC = null;`);   // KPIWINDOW: the pooled tiles now read this (not r.m) — preload it like active_frontend.js does
const RESET = `SMPF={}; SMPALL=false; APP=''; UNIAPP=''; ACTAPP=''; VALAPP=''; RANGE='30d'; innerWidth=375; UNISTEXP=''; ACTSTEXP=''; VALSTEXP=''; UNIUPALL=false;`;
const out = {};
function scen(name, code) { try { out[name] = String(run(`(()=>{ ${RESET} ${code} })()`)); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + ((e.stack || '').match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); out[name] = ''; } }
const text = h => String(h).replace(/<style[\s\S]*?<\/style>/g, '').replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
const R = {};

// ── 1. the small helpers (dates, age, IST time) ──
R.helpers = JSON.parse(run(`JSON.stringify({share:smpInfoTxt('3 Jul se purane users kam: roz ~10,000 → ~6,000 (−40%) · naye installs bhi −90% (ad spend?) — isme ~25.5 point unka'),
  share_upto:smpInfoTxt('naye installs bhi +40% (ad spend?) — isme ~12 point tak unka ho sakta'), pp:smpInfoTxt('agle din wapas aane wale naye users 26 point kam'),
  market:smpInfoTxt('Ad ka rate (eCPM) +50% (1–7 Sep), ads per user wahi — market/mediation/country mix ka asar'), umar:[0,3,30,31,89,90,200].map(smpUmar), ist:smpIst('2026-09-28T04:56:12Z'), ist_date:smpIst('2026-09-28'),
  ist_none:smpIst(null), d_this:smpD('2026-03-16'), d_last:smpD('2025-12-29'), pakka:smpPakka('2026-10-05'), pakka0:smpPakka(null),
  nw:[0,1,7,12].map(smpNW), rel:[0.137,-0.284,0,null].map(smpRel), count:[12345,250000,3450000].map(smpCount)})`));

// ── 2. one row's chip, fold and the grey 🕒 line (made-up rows) ──
const ROW = o => `Object.assign({src:'uninstall',type:'alert',sev:'bigda',app:'Demo App',appId:'x~1',key:'k',fact:'f',data:'Installs 19–25 Sep · vs pehle (22 Aug–18 Sep)'},${o})`;
R.rows = JSON.parse(run(`(()=>{ const r=o=>{ const x=${ROW('o')}; return {chip:smpChipOf(x), tip:smpChipTip(x), isnew:smpIsNew(x), fold:smpFoldOf(x,false), fold_app:smpFoldOf(x,true), ts:smpTs(x).replace(/<[^>]*>/g,'')}; };
  return JSON.stringify({
    naya: r({started:'2026-09-20', openedAt:'2026-09-21T05:00:00Z', opened:'2026-09-21'}),
    chal: r({started:'2026-09-01', opened:'2026-09-03', seeded:true}),
    old_red: r({started:'2026-07-01', opened:'2026-07-03'}),
    good: r({sev:'behtar', started:'2026-09-20', opened:'2026-09-21'}),
    cap: r({started:'2026-03-01', cap:true, opened:'2026-09-01'}),
    pakka: r({started:'2026-09-20', opened:'2026-09-21', pakka:'2026-10-05', andaza:true}),
    info30: r({type:'info', sev:'info', started:'2026-09-10'}),
    info60: r({type:'info', sev:'info', started:'2026-07-20'}),
    info120: r({type:'info', sev:'info', started:'2026-05-20'}),
    theek: r({type:'closed', theek:true, started:'2026-09-01', opened:'2026-09-03', openedAt:'2026-09-03T05:00:00Z', closed:'2026-09-22', closedAt:'2026-09-22T05:00:00Z', closeReason:'recovered'}),
    band: r({type:'closed', theek:false, started:'2026-09-01', opened:'2026-09-03', closed:'2026-09-22', closeReason:'superseded'}),
    not_iso: r({started:'2026-09-20', opened:'2026-09-21', openedAt:'seeded'}),
    small_info120: Object.assign(r({type:'info', sev:'info', started:'2026-05-20'}), {small_app: smpFoldOf(Object.assign(${ROW('{}')},{type:'info',sev:'info',started:'2026-05-20',appId:'s~1'}),false)}),
    n1_old: r({type:'info', sev:'info', alertInfo:true, started:'2026-05-20', opened:'2026-09-21'}),
    // the ALERT's age (owner, 1 Oct), IST calendar days up to the build's last check (generated_at 25 Sep 03:30 UTC = 09:00 IST)
    age_aaj_utc_yday: r({started:'2026-09-20', opened:'2026-09-22', alertAt:'2026-09-24T19:00:00Z'}),     // 25 Sep 00:30 IST
    age_kal_utc_same: r({started:'2026-09-20', opened:'2026-09-22', alertAt:'2026-09-24T18:29:00Z'}),     // 24 Sep 23:59 IST
    age_kal: r({started:'2026-09-20', opened:'2026-09-22', alertAt:'2026-09-24T03:00:00Z'}),
    age_2: r({started:'2026-09-20', opened:'2026-09-21', alertAt:'2026-09-23T10:00:00Z'}),
    age_29: r({started:'2026-08-20', opened:'2026-08-25', alertAt:'2026-08-27T10:00:00Z'}),
    age_30: r({started:'2026-08-20', opened:'2026-08-24', alertAt:'2026-08-26T10:00:00Z'}),
    age_old_year: r({started:'2025-12-01', opened:'2025-12-28', alertAt:'2025-12-30T10:00:00Z'}),
    age_seeded: r({started:'2026-09-01', opened:'2026-09-17', seeded:true, alertAt:'2026-09-19T12:00:00Z'}),
    age_seeded_today: r({started:'2026-09-01', opened:'2026-09-23', seeded:true, alertAt:'2026-09-25T01:00:00Z'}),
    // the time's fallback: opened_at → the engine's alert_at (notified_at) → the data day (never an invented time)
    fb_opened: r({started:'2026-09-20', opened:'2026-09-21', openedAt:'2026-09-24T04:00:00Z', alertAt:'2026-09-20T04:00:00Z'}),
    fb_alert_at: r({started:'2026-09-20', opened:'2026-09-21', alertAt:'2026-09-23T13:00:00Z'}),
    fb_bad_opened: r({started:'2026-09-20', opened:'2026-09-21', openedAt:'sent', alertAt:'2026-09-23T13:00:00Z'}),
    fb_none: r({started:'2026-09-20', opened:'2026-09-21'}),
    fb_none_closed: r({type:'closed', theek:false, started:'2026-09-01', opened:'2026-09-03', closed:'2026-09-22', closeReason:'window_end'}),
    info_dikha: r({type:'info', sev:'info', started:'2026-09-10', seen:'2026-09-12'}),
    info_nodata: r({type:'info', sev:'info', started:'2026-09-10', data:''}),
    theek_rule: [smpTheek({closed:'2026-09-22',opened:'2026-09-10',close_reason:'recovered',severity:'warning'}),
                 smpTheek({closed:'2026-09-22',opened:'2026-09-10',close_reason:'superseded',severity:'warning'}),
                 smpTheek({closed:'2026-09-10',opened:'2026-09-01',close_reason:'recovered',severity:'warning'}),
                 smpTheek({closed:'2026-09-22',opened:'2026-09-22',close_reason:'recovered',severity:'warning'}),
                 smpTheek({closed:'2026-09-22',opened:'2026-09-10',close_reason:'recovered',severity:'good'}),
                 smpTheek({closed:'2026-09-22',opened:'2026-09-10',close_reason:'recovered',severity:'watch'},{size:'chhoti'})]}); })()`));

// ── 3. every list of the three tabs: All apps (no per-app file loaded, then every one loaded) and each app ──
// (reviewer) every All-apps list's input rows and where each one lands (visible '' / a fold / null = listed nowhere)
run(`__LISTS={}; const __smpList=smpList; smpList=function(rows,o){ if(['uni','act','val'].includes(o.id)) __LISTS[o.id]=rows.map(r=>({type:r.type,info:!!r.alertInfo,key:r.key,fold:smpFoldOf(r,false)})); return __smpList(rows,o); };`);
scen('uni_pf', `return uniScreen();`);
scen('uni_pf_open', `SMPALL=true; return uniScreen();`);
scen('act_pf_nofiles', `SMPALL=true; return actScreen();`);
scen('val_pf_nofiles', `SMPALL=true; return valScreen();`);
run(`for (const r of DATA.active.apps) if (__A.app_files[r.key]) ACTD[r.key]=__A.app_files[r.key];
     for (const r of DATA.value.apps) if (__V.app_files[r.key]) VALD[r.key]=__V.app_files[r.key];`);
scen('act_pf_files', `SMPALL=true; return actScreen();`);
scen('val_pf_files', `SMPALL=true; return valScreen();`);
const card = (h, id) => { const i = h.indexOf(`id="${id}"`); if (i < 0) return null; const j = h.indexOf('<div class="card', i + 10); return h.slice(i, j < 0 ? undefined : j); };
R.same_lists = { act: card(out.act_pf_nofiles, 'act-chg') === card(out.act_pf_files, 'act-chg') && !!card(out.act_pf_files, 'act-chg'),
                 val: card(out.val_pf_nofiles, 'val-chg') === card(out.val_pf_files, 'val-chg') && !!card(out.val_pf_files, 'val-chg') };
const apps = [];
for (const a of UF.asset.apps) { scen(`uni|${a.app}`, `SMPALL=true; UNIAPP=${J(a.app_id)}; APP=${J(a.app)}; return uniScreen();`); apps.push(`uni|${a.app}`); }
for (const r of AF.dashboard_active.apps) if (AF.app_files[r.key]) { scen(`act|${r.app}`, `SMPALL=true; ACTAPP=${J(r.app_id)}; APP=${J(r.app)}; return actScreen();`); apps.push(`act|${r.app}`); }
for (const r of VF.dashboard_value.apps) if (VF.app_files[r.key]) { scen(`val|${r.app}`, `SMPALL=true; VALAPP=${J(r.app_id)}; APP=${J(r.app)}; return valScreen();`); apps.push(`val|${r.app}`); }
// each "What changed?" row: its status word, chip, the 🕒 line's parts, and whether it is an alert row
const rowsOf = h => [...String(h).matchAll(/<div class="uni-chg [^"]*"[^>]*><div class="smp-row">([\s\S]*?class="smp-ts">[\s\S]*?)<\/div><\/div><\/div>/g)].map(m => {
  const t = text(m[1]);
  return { words: (m[1].match(/class="pill [a-z-]+ smp-w"/g) || []).length, word: (m[1].match(/smp-w">([^<]*)</) || [])[1] || '',
    chips: (m[1].match(/class="smp-chip( band)?"/g) || []).length, clock: t.includes('🕒 Alert aaya: '),
    ts_clock: /^🕒 /.test(text((m[1].match(/class="smp-ts">([\s\S]*)$/) || [])[1] || '')), fallback: / tak ke data pe/.test(text((m[1].match(/class="smp-ts">([\s\S]*)$/) || [])[1] || '').split(' · ')[0]),
    chip: (m[1].match(/class="smp-chip(?: band)?"[^>]*>([^<]*)</) || [])[1] || '', shuru: /Badlaav shuru: (\d{1,2} [A-Z][a-z]{2}( \d{4})? · \d+ (din|hafte|mahine)|6\+ mahine se|—)/.test(t),
    data: t.includes(' Data: ') || t.startsWith('Data: ') || / Data: /.test(t), info: (m[1].match(/smp-w">ℹ️ Jaankari</) || []).length > 0, t: t.slice(0, 300) }; });
R.rows_all = {};
for (const k of ['uni_pf_open', 'act_pf_files', 'val_pf_files', ...apps]) R.rows_all[k] = rowsOf(out[k]);
R.legend = {};
for (const k of ['uni_pf', 'uni_pf_open', 'act_pf_nofiles', 'act_pf_files', 'val_pf_files', ...apps]) { const h = out[k] || '';
  R.legend[k] = { lists: (h.match(/<h3>🔔 What changed\? \(/g) || []).length, legends: (h.match(/<div class="smp-legend">🆕 = naya alert \(aaj\/kal\) · 📌 = pehle se khula · 🕒 = kab aaya \/ kis data pe<\/div>/g) || []).length,
    order: h.indexOf('<h3>🔔 What changed? (') < h.indexOf('class="smp-legend"') && h.indexOf('class="smp-legend"') < (h.indexOf('<div class="uni-chg ') < 0 ? Infinity : h.indexOf('<div class="uni-chg ')) }; }
// the tab heads: "🆕 n naye alert (aaj/kal)" counts the rows whose chip is 🆕
R.naye = { uni: (text(out.uni_pf_open).match(/🆕 (\d+) naye alert \(aaj\/kal\)/) || [])[1],
  uni_rows: rowsOf(out.uni_pf_open).filter(x => /^🆕/.test(x.chip)).length, act: (text(out.act_pf_files).match(/🆕 (\d+) naye alert \(aaj\/kal\)/) || [])[1],
  act_rows: rowsOf(out.act_pf_files).filter(x => /^🆕/.test(x.chip)).length };

// ── 3b. reviewer: the "How we compare" note, the full table and the pooled tiles in the six words / lakh ──
{ const a0 = UF.asset.apps[0];
  scen('how', `UNIAPP=${J(a0.app_id)}; APP=${J(a0.app)}; impSet('uni',{how:true}); try{ return uniImpHow('uni'); } finally{ impSet('uni',{how:false}); }`);
  scen('uni_cp_all', `SMPALL=true; UNICPEXP=true; let h=''; for(const a of UNI.apps){ UNIAPP=a.app_id; APP=a.app; h+=uniScreen(); } UNICPEXP=false; return h;`);
  // the "Purane users (roz)" pooled tile now reads ACTPF (not r.m — KPIWINDOW): inflate ITS a1/ret arrays so the
  // pooled total crosses into lakh territory, same intent as before (a big number must say "lakh", never "…M")
  scen('act_pool_big', `const rows=actRows(), keepPF=ACTPF, F=JSON.parse(JSON.stringify(ACTPF));
    F.apps.forEach(a=>{ a.a1=(a.a1||[]).map(v=>v==null?v:v*1000); a.ret=(a.ret||[]).map(v=>v==null?v:v*1000); });
    ACTPF=F; ACTPFC=null;
    try{ return actSumPortfolio(rows); } finally{ ACTPF=keepPF; ACTPFC=null; }`); }
// ── 4. visible words on every screen of the three tabs + the Alerts screen ──
scen('alerts', `const keep=screenDiv; screenDiv=id=>({dataset:{screen:id},innerHTML:''}); try{ return renderAlerts().innerHTML; } finally{ screenDiv=keep; }`);
scen('alerts_app', `const keep=screenDiv; screenDiv=id=>({dataset:{screen:id},innerHTML:''}); APP='Demo App'; try{ return renderAlerts().innerHTML; } finally{ screenDiv=keep; APP=''; }`);
R.pool_big = text(out.act_pool_big || '');
R.lists = JSON.parse(run('JSON.stringify(__LISTS)'));
R.open_alerts = { uni: (UF.dashboard_uninstall.alerts || []).map(a => a.id), act: (AF.dashboard_active.alerts || []).map(a => a.id),
  act_slow_merged: (AF.dashboard_active.alerts || []).filter(a => a.family === 'act_slow' && (AF.dashboard_active.alerts || []).some(z => z.family === 'act_drift' && z.app_id === a.app_id && z.metric === a.metric)).map(a => a.id),
  val: (VF.dashboard_value.alerts || []).map(a => a.id) };
R.texts = Object.fromEntries(Object.entries(out).map(([k, v]) => [k, text(v)]));
R.alerts = { html: out.alerts, ga4_cards: (out.alerts.match(/data-metrics="(uninstall|active|value)"/g) || []).length,
  total: (text(out.alerts).match(/Total issues (\d+)/) || [])[1], chips: [...out.alerts.matchAll(/<span class="smp-chip">([^<]*)<\/span> Shuru: ([^<]*)</g)].map(m => [m[1], m[2]]) };

// ── 4b. the Active users tab's ONE update line (owner, 1 Oct: "rehne do, Uninstall se dekh lunga"): per app "📦 Is app ka
// aakhri update: vX (date) · <verdict> → Uninstall me poora card ›" (or "📦 Pichhle 60 din me koi update nahi"), and its
// tap: the Uninstall tab, that app, that update's block opened in the full card ──
R.updline = JSON.parse(run(`(()=>{ const out=[]; const keep={show, render, _navSave, scrollTo:globalThis.scrollTo}; const calls=[];
  try{ show=id=>calls.push('show:'+id); render=()=>calls.push('render'); _navSave=()=>{};
    for(const r of DATA.uninstall.apps){ ${RESET} calls.length=0; UNIIMPOPEN=''; UNIIMPJUMP=''; UNIIMPWK={};
      const h=actUpdLine({app_id:r.app_id}), t=h.replace(/<[^>]*>/g,' ').replace(/\\s+/g,' ').trim(), go=(h.match(/onclick="([^"]*)"/)||[])[1]||'';
      const o={app_id:r.app_id, app:r.app, n:(r.updates||[]).length, text:t, go, newest:((r.updates||[]).slice().sort((p,q)=>p.date<q.date?1:-1)[0]||{}).key||null};
      if(go){ eval(go); const page=uniScreen(); const open=page.split('<div class="uni-imp-b').filter(x=>x.includes('data-open="1"'));
        Object.assign(o,{calls:calls.slice(), APP, UNIAPP, open:UNIIMPOPEN, jump:UNIIMPJUMP, rendered_open:open.map(x=>(x.match(/data-key="([^"]*)"/)||[])[1]),
          card:page.includes('id="uni-impact"'), detail:page.includes('Sirf ye app:')}); }
      out.push(o); }
    // the All-apps line
    out.push({all:true, text:(actPortfolio().split('id="act-upd-link"')[1]||'').split('</div>')[0].replace(/<[^>]*>/g,' ').replace(/^[^>]*>/,'').replace(/\\s+/g,' ').trim(),
      go:((actPortfolio().split('id="act-upd-link"')[1]||'').match(/onclick="([^"]*)"/)||[])[1]||''});
  } finally{ show=keep.show; render=keep.render; _navSave=keep._navSave; APP=''; UNIAPP=''; }
  return JSON.stringify(out); })()`));
// impact / impact_late alerts stay in the Uninstall tab's "What changed?" (All apps and the app's own): their rows
R.imp_rows = { all: rowsOf(out.uni_pf_open).filter(x => /Update roko|Ruk ke jaancho|Update achha gaya|30 din baad:/.test(x.t)).map(x => ({ chip: x.chip, clock: x.clock, ts: x.ts_clock })),
  want: (UF.dashboard_uninstall.alerts || []).filter(a => a.family === 'impact' || a.family === 'impact_late').length };

// ── 5. the Alerts badges: ad units (critical + warning) + approved-range breaches — the GA4 tabs are not in it ──
R.badge = { n: run('alertsBadgeN()'), ga4_warnings: run(`[DATA.uninstall,DATA.active,DATA.value].reduce((t,x)=>t+(((x||{}).alert_counts||{}).warning||0),0)`) };

// ── 6. ✅ Review as the landing screen (an index with a day, no recent saved view, no #review… hash, still on Overview) ──
R.landing = JSON.parse(run(`(()=>{ const keep={show, document:globalThis.document}, calls=[]; show=id=>calls.push(id);
  const doc=cur=>({querySelector:()=>({dataset:{screen:cur}})}); const idx=n=>({ok:true, idx:{days:Array.from({length:n},(_,i)=>({d:'2026-09-2'+i}))}});
  const o={};
  try{
    document=doc('overview'); RVLANDOK=true; location.hash=''; o.day=rvLanding(idx(1)); o.day_calls=calls.splice(0);
    o.none=rvLanding(idx(0)); o.none_calls=calls.splice(0);
    o.err=rvLanding({ok:false,status:404}); o.err_calls=calls.splice(0);
    RVLANDOK=false; o.saved=rvLanding(idx(2)); o.saved_calls=calls.splice(0); RVLANDOK=true;
    location.hash='#review/summary'; o.hash=rvLanding(idx(2)); o.hash_calls=calls.splice(0); location.hash='';
    document=doc('uninstall'); o.moved=rvLanding(idx(2)); o.moved_calls=calls.splice(0);
  } finally { show=keep.show; document=keep.document; RVLANDOK=false; }
  return JSON.stringify(o); })()`));

process.stdout.write(J({ errors, ...R }));
