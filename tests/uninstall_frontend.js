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
const RESET = `UNIAPP=''; APP=''; UNICSRC='all'; UNICRANGE='90'; UNITRI='cp'; UNITRIPAGE=0; UNITRIEXP=false; UNIOLDEXP=false; UNICPEXP=false; UNIDRANGE='90d';`;
for (const r of ['today', '7d', '30d', '90d', 'month', 'lastmonth', 'all', 'custom'])
  scen('portfolio_' + r, `${RESET} RANGE='${r}'; RCUSTOM={from:'2026-08-01',to:'2026-09-30'}; UNITRIEXP=${r === 'all'}; uniScreen()`);
for (const k of ['app', 'ins', 'outs', 'net', 'rate', 'S7', 'D0', 'D1', 'D7', 'D30', 'alert'])
  scen('sort_' + k, `${RESET} RANGE='30d'; UNISORT={k:'${k}',d:-1}; uniPortfolio()`);
const apps = FX.asset.apps;
for (const a of apps) {
  const id = JSON.stringify(a.app_id);
  for (const [src, cr, tri, cp, old, exp] of [['all', '30', 'cp', false, false, false], ['all', '90', 'all', true, true, false],
    ['recent', 'all', 'cp', true, false, true], ['recent', '30', 'all', false, true, true], ['all', 'all', 'cp', false, false, false]])
    scen(`detail|${a.app}|${src}|${cr}|${tri}|${cp}`, `${RESET} RANGE='30d'; UNIAPP=${id}; UNICSRC='${src}'; UNICRANGE='${cr}'; UNITRI='${tri}'; UNICPEXP=${cp}; UNIOLDEXP=${old}; UNITRIEXP=${exp}; uniScreen()`);
  scen(`tripages|${a.app}`, `${RESET} UNIAPP=${id}; UNITRI='all'; (()=>{ let s=''; for (let p=0;p<12;p++){ UNITRIPAGE=p; s+=uniScreen(); } return s; })()`);
  scen(`appfilter|${a.app}`, `${RESET} APP=${JSON.stringify(a.app)}; uniScreen()`);
}
for (const n of FX.asset.no_ga4) scen(`appfilter_noga4|${n.app}`, `${RESET} APP=${JSON.stringify(n.app)}; uniScreen()`);
scen('alert_cards', `${RESET} uniAlertCards(uniAlertsFor())`);
// the "worse" verdict (the fixture has only "better" and "jaisa"): one app's verdict turned around, then restored
scen('verdict_worse', `${RESET} (()=>{ const a=UNI.apps[0], sv=a.survival, keep=sv.verdict;
  sv.verdict=Object.assign({},keep,{fires:true,dir:'worse',recent:Object.assign({},keep.recent,{left:keep.prev.left-0.05})});
  try{ UNIAPP=a.app_id; const d=uniScreen(); UNIAPP=''; return d+'<hr>'+uniScreen(); } finally { sv.verdict=keep; } })()`);
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
try { run(`UNI.apps.map(a=>{ const C=UNICOH[a.key], T=a.triangle; if(!C) return [a.app,-1,[]]; const r=uniTriAll(C,0,C.nE,a.settled_till), bad=[];
    T.cols.forEach((N,j)=>{ const e=T.avg4[j], g=r.avg4[N]; if((e==null)!==(g==null)||(e&&(Math.abs(e.p-g.p)>1e-5||e.users!==g.users||e.from!==g.from||e.to!==g.to))) bad.push(N); });
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
// the curve card and the summary name the same install span for "Hamesha"
const spanBad = [];
for (const a of apps) {
  const t = T(`detail|${a.app}|all|30|cp|false`), s1 = (t.match(/ab tak ke saare pakke installs se \(([^·]+) ·/) || [])[1], s2 = (t.match(/Hamesha = (.+?) ke saare pakke installs/) || [])[1];
  if (!s1 || !s2 || s1.trim() !== s2.trim()) spanBad.push(a.app + ': ' + s1 + ' | ' + s2);
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
    avg4_row: has(`detail|${apps[0].app}|all|30|cp|false`, 'Pichhle 4 hafte ka average') && has(`detail|${apps[0].app}|all|90|all|true`, 'Pichhle 4 hafte ka average'),
    box_line: has(`detail|${apps[0].app}|all|30|cp|false`, 'Har box = us hafte install karne walon me se us din tak kitne % ne app hata diya'),
    mix_note_all: has('portfolio_30d', 'All apps me har hafte apps ka mix badalta hai — sahi tulna ke liye upar se ek app chuno'),
    no_pooled_triangle: !Object.entries(out).some(([k, v]) => k.startsWith('portfolio') && v.includes('uni-tri-all')),
    avg4_says_weeks: has(`detail|${apps[0].app}|all|30|cp|false`, 'har din ke sabse naye 4 pakke hafte — bade din ke liye purane installs'),
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
