// The shared KPIWINDOW selector (frontend/index.html): the period + comparison controls that drive the top KPI
// numbers of Uninstall / Active users / Install value (owner: "7 days pe hi kyu? 14/30/60/custom?"). Runs the
// real page script in a node vm with a REAL (in-memory) localStorage stub — several of these checks are about
// persistence surviving a storage error — and exercises: the pure window / comparison math (kwWin, kwPrevWin,
// kwMonthWin, kwCustomCmpWin, kwValidCustom, kwCmpLine, kwCmpStale), real sums against the committed Uninstall /
// Active fixtures (cross-checked independently in tests/test_kpiwindow_frontend.py), the All-apps "common end
// date" fix, persistence, and that Overview / the global RANGE are never touched by any of this.
// Prints one JSON report; tests/test_kpiwindow_frontend.py asserts on it.
// usage: node kpiwindow_frontend.js <script.js> <uninstall_fixture.json> <active_fixture.json> <value_fixture.json>
const fs = require('fs'), vm = require('vm');
const [scriptPath, uniFx, actFx, valFx] = process.argv.slice(2);
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const errors = [];
// a REAL in-memory localStorage — persistence is the point of several checks. LS.fail() makes every call throw
// (to check the code survives a blocked/private-mode browser) while in-memory state is tracked separately here
// so the test can tell "did the page still behave correctly" apart from "did the write actually land".
const LS_BACKING = {};
let LS_FAIL = false;
const localStorage = {
  getItem(k) { if (LS_FAIL) throw new Error('blocked'); return Object.prototype.hasOwnProperty.call(LS_BACKING, k) ? LS_BACKING[k] : null; },
  setItem(k, v) { if (LS_FAIL) throw new Error('blocked'); LS_BACKING[k] = String(v); },
  removeItem(k) { if (LS_FAIL) throw new Error('blocked'); delete LS_BACKING[k]; },
};
const ctx = {
  console: { log() {}, warn() {}, error: (...a) => errors.push(a.join(' ')) },
  window: any, document: any, localStorage, sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  __lsFail: v => { LS_FAIL = !!v; },   // a bridge: scenario code runs inside the vm, LS_FAIL lives out here
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
const UNI = JSON.parse(fs.readFileSync(uniFx, 'utf8'));
const ACT = JSON.parse(fs.readFileSync(actFx, 'utf8'));
const VAL = JSON.parse(fs.readFileSync(valFx, 'utf8'));
ctx.__UNI = UNI; ctx.__ACT = ACT; ctx.__VAL = VAL;
run(`DATA = {apps_catalog: [], today_date: '2026-09-25', alerts: {counts: {}, items: []},
     uninstall: __UNI.dashboard_uninstall, active: __ACT.dashboard_active, value: __VAL.dashboard_value};
   UNI = __UNI.asset; UNIERR = false; UNICOH = {};
   ACTD = {}; for (const [k, v] of Object.entries(__ACT.app_files || {})) ACTD[k] = v;
   ACTPF = __ACT.portfolio || null; ACTPFSIG = (DATA.active.portfolio || {}).sig || null;
   VALD = {}; for (const [k, v] of Object.entries(__VAL.app_files || {})) VALD[k] = v;`);
const out = {};
function get(name, code) { try { out[name] = run(code); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); } }
// every scenario starts from the documented default (7 din, compare = previous period) and the header's own
// RANGE/APP untouched, so a leak between scenarios (or into RANGE) shows up immediately
const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; UNIAPP=''; ACTAPP=''; VALAPP='';`;
run(RESET);

// ---------------------------------------------------------------------------------------------------------------
// pure window math (no fixture needed)
get('win_presets', `JSON.stringify(['7','14','30','60'].map(n=>{ const keep=KWIN; KWIN=n; const w=kwWin('2026-01-01','2026-09-23'); KWIN=keep; return w; }))`);
get('win_custom_valid', `${RESET} KWIN='custom'; KWCUSTOM={from:'2026-08-01',to:'2026-08-20'}; JSON.stringify(kwWin('2026-01-01','2026-09-23'))`);
get('win_custom_clip_hs', `${RESET} KWIN='custom'; KWCUSTOM={from:'2025-01-01',to:'2026-01-10'}; JSON.stringify(kwWin('2026-01-01','2026-09-23'))`);
get('win_custom_f_gt_t', `${RESET} KWIN='custom'; KWCUSTOM={from:'2026-08-20',to:'2026-08-01'}; JSON.stringify(kwWin('2026-01-01','2026-09-23'))`);
get('win_custom_too_long', `${RESET} KWIN='custom'; KWCUSTOM={from:'2024-01-01',to:'2026-01-10'}; JSON.stringify(kwWin('2026-01-01','2026-09-23'))`);
get('win_no_data', `${RESET} JSON.stringify(kwWin('', ''))`);
get('win_hs_after_till', `${RESET} JSON.stringify(kwWin('2026-09-23','2026-01-01'))`);

get('prev_14', `(()=>{ ${RESET} KWIN='14'; const w=kwWin('2026-01-01','2026-09-23'); return JSON.stringify(kwPrevWin(w,'2026-01-01')); })()`);
get('prev_clipped', `(()=>{ ${RESET} KWIN='30'; const w=kwWin('2026-08-20','2026-09-23'); return JSON.stringify(kwPrevWin(w,'2026-08-20')); })()`);   // hs cuts the previous period short → full:false
get('prev_none_room', `(()=>{ ${RESET} KWIN='7'; const w=kwWin('2026-09-20','2026-09-23'); return JSON.stringify(kwPrevWin(w,'2026-09-20')); })()`);   // hs == w.from → no room at all before it

get('shift_month', `JSON.stringify(['2026-01-31','2026-03-31','2028-03-31','2026-05-15'].map(kwShiftMonth))`);
get('month_win', `(()=>{ ${RESET} KWIN='30'; const w=kwWin('2026-01-01','2026-09-23'); return JSON.stringify(kwMonthWin(w,'2026-01-01','2026-09-23')); })()`);
get('month_win_out_of_data', `(()=>{ ${RESET} KWIN='7'; const w=kwWin('2026-09-05','2026-09-10'); return JSON.stringify(kwMonthWin(w,'2026-09-05','2026-09-10')); })()`);

get('custom_cmp', `${RESET} KCMPCUSTOM={from:'2026-07-01',to:'2026-07-20'}; JSON.stringify(kwCustomCmpWin('2026-01-01','2026-09-23'))`);
get('custom_cmp_unequal', `${RESET} KCMPCUSTOM={from:'2026-07-01',to:'2026-07-14'}; JSON.stringify(kwCustomCmpWin('2026-01-01','2026-09-23'))`);
get('custom_cmp_outside', `${RESET} KCMPCUSTOM={from:'2025-01-01',to:'2025-01-10'}; JSON.stringify(kwCustomCmpWin('2026-01-01','2026-09-23'))`);

get('valid_custom', `JSON.stringify(['2026-08-01|2026-08-20','2026-08-20|2026-08-01','|2026-08-20','2026-08-01|',
  '2024-01-01|2026-09-23','2026-08-01|2026-08-01'].map(s=>{ const [f,t]=s.split('|'); return kwValidCustom(f,t); }))`);

// cmp dispatcher: prev / month / custom
get('cmp_dispatch', `(()=>{ ${RESET} KWIN='30'; const w=kwWin('2026-01-01','2026-09-23');
  const r={}; KCMP='prev'; r.prev=kwCmpWin(w,'2026-01-01','2026-09-23');
  KCMP='month'; r.month=kwCmpWin(w,'2026-01-01','2026-09-23');
  KCMP='custom'; KCMPCUSTOM={from:'2026-06-01',to:'2026-06-10'}; r.custom=kwCmpWin(w,'2026-01-01','2026-09-23');
  return JSON.stringify(r); })()`);

// kwCmpLine: COUNT tiles — always "roz ~<avg> (±%)"; the two periods' totals in grey ONLY when lengths differ
get('cmpline_equal', `kwCmpLine(900,30,3000,{from:'2026-07-01',to:'2026-07-30',days:30,empty:false},v=>Math.round(v).toLocaleString('en-US'))`);
get('cmpline_unequal', `kwCmpLine(27600,30,25100,{from:'2026-08-01',to:'2026-08-14',days:14,empty:false},v=>Math.round(v).toLocaleString('en-US'))`);
get('cmpline_missing_prev', `kwCmpLine(100,7,null,{from:'',to:'',days:0,empty:true},String)`);
get('cmpline_missing_range', `kwCmpLine(100,7,null,{from:'2026-01-01',to:'2026-01-07',days:0,empty:true},String)`);

// kwPct: one decimal from 10%, two below 10%, no trailing zeros, never "0%" for a real non-zero rate
get('pct_fmt', `JSON.stringify([0.28,0.244,0.0097,0.00005,0,-0.09,0.1,0.05].map(kwPct))`);
// kwRatePctLine: the OWNER's final rule — the actual number is primary, percentages beside it, no "100 me" /
// "har 1,000 me" / "Matlab" text anywhere. A daily-rate tile (perDay) shows the actual number AS a daily figure.
get('ratepct_period_total', `kwRatePctLine(0.28,30,0.22,{from:'2026-08-01',to:'2026-08-30',days:30,empty:false},{base:3098,what:'uninstall'})`);
get('ratepct_daily', `kwRatePctLine(0.0097,7,0.0081,{from:'2026-09-01',to:'2026-09-07',days:7,empty:false},{base:7000,perDay:true,what:'uninstall',est:true})`);
get('ratepct_missing', `kwRatePctLine(0.28,30,null,{from:'',to:'',days:0,empty:true},{base:1000})`);
get('ratepct_no_base', `kwRatePctLine(0.28,30,0.22,{from:'2026-08-01',to:'2026-08-30',days:30,empty:false},{})`);
// same underlying daily rates → the SAME % change regardless of the compare window's length (no base → no actual-
// number part, so the raw strings must be byte-identical across 7/14/30-day windows)
get('ratepct_len_invariant', `JSON.stringify([7,14,30].map(n=>kwRatePctLine(0.0097,n,0.0081,{from:'x',to:'y',days:n,empty:false},{})))`);
// kwRateMoneyLine: actual money per day + the per-user values, never a %
get('ratemoney', `kwRateMoneyLine(2.31,30,1.92,{from:'2026-08-01',to:'2026-08-30',days:30,empty:false},v=>'₹'+Math.round(v).toLocaleString('en-US'),v=>'₹'+v.toFixed(4),{base:50000*30})`);
get('ratemoney_missing', `kwRateMoneyLine(2.31,30,null,{from:'',to:'',days:0,empty:true},v=>String(v),v=>String(v),{})`);
// kwRateAvgLine: a plain continuous average (sessions, time, purane users roz) — before → after with a plain %
get('rateavg', `kwRateAvgLine(2.3,7,2.1,{from:'2026-09-01',to:'2026-09-07',days:7,empty:false},v=>v.toFixed(1))`);
get('rateavg_missing', `kwRateAvgLine(2.3,7,null,{from:'',to:'',days:0,empty:true},v=>v.toFixed(1))`);

// uniPoolSums: pools a list of uniSums()-shaped objects (nulls skipped, not a fake 0)
get('pool_sums', `JSON.stringify(uniPoolSums([{ins:10,outs:4,rU:4,rA:1000,bU:4,bA:1000,eL:10,eH:20},
  {ins:20,outs:null,rU:6,rA:1000,bU:6,bA:1000,eL:15,eH:25},null]))`);

// kwCmpStale / kwCheckStale: a saved custom compare range entirely outside the data → resets to 'prev' and persists
get('stale_reset', `${RESET} localStorage.setItem('x','y'); KCMP='custom'; KCMPCUSTOM={from:'2020-01-01',to:'2020-01-10'};
  const before=kwCmpStale('2026-01-01','2026-09-23'); kwCheckStale('2026-01-01','2026-09-23');
  JSON.stringify({before, after:KCMP, saved:JSON.parse(localStorage.getItem('kwin_v1')||'null')})`);
get('stale_keep_in_range', `${RESET} KCMP='custom'; KCMPCUSTOM={from:'2026-06-01',to:'2026-06-10'};
  kwCheckStale('2026-01-01','2026-09-23'); KCMP`);

// ---------------------------------------------------------------------------------------------------------------
// persistence: a fresh "reload" reads back exactly what was saved; a blocked store never throws and never loses
// the in-memory choice for the rest of the session
get('persist_roundtrip', `(()=>{ ${RESET} KWIN='30'; KWCUSTOM={from:'2026-07-01',to:'2026-07-30'}; KCMP='month'; kwSave();
  KWIN='7'; KWCUSTOM={from:'',to:''}; KCMP='prev';   // simulate a fresh load
  kwLoad();
  return JSON.stringify({win:KWIN, custom:KWCUSTOM, cmp:KCMP}); })()`);
get('persist_survives_error', `(()=>{ ${RESET} let threw=false; __lsFail(true);
  try{ KWIN='60'; kwSave(); }catch(e){ threw=true; } __lsFail(false);
  return JSON.stringify({threw, kwin:KWIN}); })()`);
get('persist_bad_json', `(()=>{ ${RESET} localStorage.setItem('kwin_v1','not json{{'); let threw=false;
  try{ kwLoad(); }catch(e){ threw=true; } return JSON.stringify({threw, win:KWIN}); })()`);

// ---------------------------------------------------------------------------------------------------------------
// real fixtures: Uninstall — an app's own window + previous-period sums (cross-checked independently in Python)
const UNI_APP_ID = UNI.asset.apps.find(a => a.app === 'Demo Caller – Test App').app_id;
get('uni_app_sums', `(()=>{ ${RESET} const a=UNI.apps.find(x=>x.app_id===${JSON.stringify(UNI_APP_ID)});
  const out={}; for (const n of ['7','14','30','60']) { KWIN=n; const w=uniWindow(a), sm=uniSums(a,w);
    out[n]={w, sm:sm?{ins:sm.ins,outs:sm.outs,net:sm.net}:null};
    KCMP='prev'; const cw=kwCmpWin(w,uniFirst(a)||a.data_till,a.data_till), csm=uniSums(a,cw); out[n].cmp={w:cw, sm:csm?{ins:csm.ins,outs:csm.outs,net:csm.net}:null}; }
  return JSON.stringify(out); })()`);

// App page KPI row renders with the selector, for every preset + a custom range, without throwing / "undefined" / "NaN"
for (const n of ['7', '14', '30', '60'])
  get('uni_detail_' + n, `${RESET} KWIN='${n}'; UNIAPP=${JSON.stringify(UNI_APP_ID)}; uniScreen()`);
get('uni_detail_custom', `${RESET} KWIN='custom'; KWCUSTOM={from:'2026-08-01',to:'2026-08-20'}; UNIAPP=${JSON.stringify(UNI_APP_ID)}; uniScreen()`);
get('uni_detail_custom_invalid', `${RESET} KWIN='custom'; KWCUSTOM={from:'2026-08-20',to:'2026-08-01'}; KWERR='From date, To date ke baad nahi ho sakti'; UNIAPP=${JSON.stringify(UNI_APP_ID)}; uniScreen()`);
get('uni_portfolio_30', `${RESET} KWIN='30'; uniScreen()`);
get('uni_portfolio_month_cmp', `${RESET} KWIN='30'; KCMP='month'; uniScreen()`);
get('uni_portfolio_custom_cmp', `${RESET} KWIN='30'; KCMP='custom'; KCMPCUSTOM={from:'2026-06-01',to:'2026-06-14'}; uniScreen()`);

// the retention tile's note (app page + pooled) — never driven by the selector
get('uni_retention_note_app', `${RESET} UNIAPP=${JSON.stringify(UNI_APP_ID)}; const a=UNI.apps.find(x=>x.app_id===${JSON.stringify(UNI_APP_ID)}); uniSumCard(a)`);
get('uni_retention_note_pool', `${RESET} uniScreen()`);

// common end date: two apps, one a day "behind" — the pooled band must use the EARLIER (common) day for both,
// never each app's own last-N-days (the bug the owner's spec calls out)
get('uni_common_till', `(()=>{ ${RESET} const keep=UNI.apps.map(a=>a.data_till);
  const a0=UNI.apps[0], a1=UNI.apps[1]; a1.data_till=uniAdd(a0.data_till,-1);
  try{ KWIN='14'; const html=uniScreen();
    const w0=uniWindow(a0,uniCommonTill(UNI.apps)), w1=uniWindow(a1,uniCommonTill(UNI.apps));
    return JSON.stringify({html_has_note: html.includes('sab ko barabar rakhne ke liye'), to0:w0.to, to1:w1.to, common:uniCommonTill(UNI.apps)}); }
  finally{ UNI.apps.forEach((a,i)=>{ a.data_till=keep[i]; }); } })()`);

// ---------------------------------------------------------------------------------------------------------------
// Active: app page (actWinSums) direct window + comparison, cross-checked independently in Python (respects the
// "settled days only" clip, same as before — just now for an arbitrary window, not a hardcoded 7)
const ACT_KEY = Object.keys(ACT.app_files)[0];
const ACT_APP_ID = (ACT.dashboard_active.apps.find(r => r.key === ACT_KEY) || {}).app_id;
get('act_app_sums', `(()=>{ ${RESET} const d=ACTD[${JSON.stringify(ACT_KEY)}];
  const out={}; for (const n of ['7','14','30','60']) { KWIN=n; const w=actWin(d), S=actWinSums(d,w);
    out[n]={w, S:S?{nR:S.nR,R:S.R,nw:S.nw,from:S.from,to:S.to,days:S.days,prov:S.prov}:null}; }
  return JSON.stringify(out); })()`);
for (const n of ['7', '14', '30', '60'])
  get('act_detail_' + n, `${RESET} KWIN='${n}'; ACTAPP=${JSON.stringify(ACT_APP_ID)}; APP=${JSON.stringify((ACT.dashboard_active.apps.find(r=>r.key===ACT_KEY)||{}).app)}; actScreen()`);
get('act_portfolio_30', `${RESET} KWIN='30'; actScreen()`);
get('act_portfolio_14_custom_cmp', `${RESET} KWIN='14'; KCMP='custom'; KCMPCUSTOM={from:'2026-08-01',to:'2026-08-20'}; actScreen()`);

// ---------------------------------------------------------------------------------------------------------------
// Install value: the selector shows (shared state) but the judged-week card is untouched by it
get('val_portfolio_30', `${RESET} KWIN='30'; valScreen()`);
const VAL_KEY = Object.keys(VAL.app_files)[0];
const VAL_APP = VAL.dashboard_value.apps.find(r => r.key === VAL_KEY);
get('val_detail_30', `${RESET} KWIN='30'; VALAPP=${JSON.stringify(VAL_APP.app_id)}; APP=${JSON.stringify(VAL_APP.app)}; valScreen()`);
get('val_detail_7_vs_30_pay_unchanged', `(()=>{ ${RESET} VALAPP=${JSON.stringify(VAL_APP.app_id)}; APP=${JSON.stringify(VAL_APP.app)};
  KWIN='7'; const a=valScreen(); KWIN='30'; const b=valScreen();
  const pay=s=>(s.match(/val-sum[\\s\\S]*?val-chg/)||[''])[0]; return JSON.stringify({same: pay(a)===pay(b)}); })()`);

// ---------------------------------------------------------------------------------------------------------------
// Other tabs / the global RANGE: untouched. Overview + Placements render byte-identical regardless of KWIN/KCMP,
// and RANGE itself is never mutated by any kw* call.
// Overview's own window machinery (curWinArr / curWinLabel) reads only the global RANGE/RCUSTOM — never KWIN/KCMP
get('overview_unaffected', `(()=>{ ${RESET} RANGE='30d'; const a=curWinLabel(), aw=JSON.stringify(curWinArr());
  KWIN='60'; KWCUSTOM={from:'2026-01-01',to:'2026-01-10'}; KCMP='month'; KCMPCUSTOM={from:'2026-02-01',to:'2026-02-05'};
  const b=curWinLabel(), bw=JSON.stringify(curWinArr());
  return JSON.stringify({same:a===b&&aw===bw, range_after:RANGE}); })()`);
get('range_not_mutated_by_kw', `(()=>{ ${RESET} RANGE='90d'; kwSet('30','uni'); kwCmpSet('month','uni'); const r=RANGE; KWIN='7'; KCMP='prev'; return r; })()`);

const n = Object.keys(out).length;
process.stdout.write(JSON.stringify({ n, errors, out }));
