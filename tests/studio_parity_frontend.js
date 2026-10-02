// 🧭 / 💸 Active users and Install value Studios — the pieces brought in from the older views ("purane page me tha"), rendered
// for real: runs the dashboard script (frontend/index.html's largest <script>) in a node vm with stub browser globals and a
// small DOM, on synthetic Studio files the REAL build code made (tests/test_studio_parity_frontend.py), and prints ONE JSON
// report; the Python test asserts on it. Every number is checked against the OLD view's own helper on the same data.
//   usage: node studio_parity_frontend.js <script.js> <dir> <active|value>
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const [scriptPath, dir, mode] = process.argv.slice(2);
const J = n => JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8'));
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const classList = () => { const s = new Set(); return { add: (...a) => a.forEach(x => s.add(x)), remove: (...a) => a.forEach(x => s.delete(x)),
  toggle: (x, f) => { const on = f === undefined ? !s.has(x) : !!f; on ? s.add(x) : s.delete(x); return on; }, contains: x => s.has(x), _s: s }; };
function mk(id) { const e = { id, _html: '', attrs: {}, classList: classList(), style: { setProperty() {} }, dataset: {}, hidden: false, open: false,
  scrollTop: 0, scrollLeft: 0, scrollWidth: 0, clientWidth: 1000, offsetParent: {}, value: '',
  get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; },
  querySelector: () => mk('_q'), querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, appendChild() {},
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 20 }), focus() {}, scrollIntoView() {}, closest: () => null };
  return e; }
const ELS = {};
const document = new Proxy({
  getElementById: id => (/^(as|vs)-/.test(String(id)) ? (ELS[id] = ELS[id] || mk(id)) : any),
  createElement: () => mk('_new'), body: mk('body'), head: mk('head'), documentElement: mk('html'),
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, activeElement: null,
}, { get: (t, k) => (k in t ? t[k] : any) });
const LSB = {};
const timers = [];
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document, localStorage: { getItem: k => (k in LSB ? LSB[k] : null), setItem: (k, v) => { LSB[k] = String(v); }, removeItem: k => { delete LSB[k]; } },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} }, navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', reload() {} }, history: any,
  fetch: () => new Promise(() => {}), setTimeout: (f) => { timers.push(f); return timers.length; }, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String,
  Set, Map, Float64Array, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent, performance: { now: () => 0 },
  getComputedStyle: () => any, innerWidth: 1280, innerHeight: 900, scrollY: 0, scrollTo() {}, alert() {}, confirm: () => false,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
ctx.__flush = () => { while (timers.length) { const f = timers.shift(); try { f(); } catch (e) { errors.push('timer ' + e.message); } } };
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const text = h => String(h).replace(/<style[\s\S]*?<\/style>/g, '').replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
ctx.__text = text;
// a table's body rows → their cells' text (the old tables and the Studio's, compared cell by cell)
ctx.__rows = h => { const H = String(h), e = H.indexOf('</tbody>'), b = H.slice(Math.max(0, H.indexOf('<tbody')), e < 0 ? H.length : e); return (b.match(/<tr[^>]*>[\s\S]*?<\/tr>/g) || [])
  .map(tr => ({ attrs: (tr.match(/^<tr([^>]*)>/) || ['', ''])[1], cells: (tr.match(/<td[^>]*>[\s\S]*?<\/td>/g) || []).map(td => text(td)) })); };
const out = {};
function get(name, code) { try { const v = run(code); out[name] = typeof v === 'string' ? v : JSON.stringify(v); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); } }

if (mode === 'active') {
  ctx.__DASH = J('dashboard.json'); ctx.__STUDIO = J('active_studio.json'); ctx.__ACTFILES = J('active_files.json'); ctx.__PF = J('active_portfolio.json');
  const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; ACTAPP=''; CURVIEW='USD'; ACTJUMP=''; ACTIMPJUMP='';`;
  const FRESH = `ACTD={}; Object.assign(ACTD,JSON.parse(JSON.stringify(__ACTFILES))); ACTPF=JSON.parse(JSON.stringify(__PF)); ACTPFC=null;`;
  run(`DATA=JSON.parse(JSON.stringify(__DASH)); ${RESET} AS._.load(__STUDIO); ${FRESH}`);
  const PAGE = i => `(()=>{ const a=AS._.A()[${i}], row=actRows().find(x=>x.app_id===a.id); APP=row.app; ACTAPP=a.id; const h=actScreen(); __flush(); return h; })()`;
  // 1 · by app version: the Studio's table = the old actVerTable (rows, cells, verdict words); "Show all versions" adds the rest
  get('ver', `(()=>{ ${RESET} ${FRESH} actScreen(); __flush(); return AS._.A().map((a,i)=>{ const d=AS._.detOf(a); const h=${PAGE('i')};
    const st=__rows(AS._.verHtml(AS._.R()[i])).map(r=>r.cells), old=__rows(actVerTable(d)).map(r=>r.cells); ${RESET} return {nm:a.nm,st,old,inPage:h.indexOf('Users by app version')>=0}; }); })()`);
  get('verAll', `(()=>{ ${RESET} ${FRESH} const a=AS._.A().find(x=>(AS._.detOf(x).versions||[]).filter(v=>!v.kind).length>=2), d=AS._.detOf(a), V=d.versions.filter(v=>!v.kind);
    d.versions_more=[V[V.length-1]]; d.versions=d.versions.filter(v=>v!==V[V.length-1]); actScreen(); __flush(); const o=AS._.R()[a.i];
    const few=__rows(AS._.verHtml(o)).length, btn=/data-verall="1"[^>]*>Show all versions \\((\\d+)\\)/.exec(AS._.verHtml(o)); AS._.ST.verAll=true;
    const all=__rows(AS._.verHtml(o)).length, oldAll=(ACTVERALL=true,__rows(actVerTable(d)).length); ACTVERALL=false; AS._.ST.verAll=false; ${FRESH} return {few,all,oldAll,btn:btn&&+btn[1]}; })()`);
  // 2 · ad rate: the Studio's helper on the engine tile's own window = the tile's number (and its 4-weeks-before base)
  get('adrate', `(()=>{ ${RESET} ${FRESH} actScreen(); __flush(); const ix=AS._.ix; return AS._.A().map(a=>{ const T=(AS._.detOf(a).tiles||{}).ecpm||{};
    const x=T.from?AS._.adRate(a,ix(T.from),ix(T.to)):null, b=T.bfrom?AS._.adRate(a,ix(T.bfrom),ix(T.bto)):null; return {nm:a.nm,v:x&&x.v,tv:T.v,b:b&&b.v,tb:T.base,im:x&&x.im}; }); })()`);
  get('adratePage', `(()=>{ ${RESET} ${FRESH} const h=${PAGE(0)}; const o=AS._.R().find(x=>x.a.id===ACTAPP); ${RESET} return {txt:__text(h.slice(h.indexOf('id="as-pg"'),h.indexOf('id="act-old"'))), v:o.ar&&actMoney(o.ar.v,baseCur()), tip:__text(AS._.TIPS.ar(o.a.i))}; })()`);
  // 3 · other ad networks: "other networks add ~x% more" (the old actOther) only when their share is known
  get('other', `(()=>{ ${RESET} ${FRESH} const a=AS._.A()[0], d=AS._.detOf(a); const off=__text(${PAGE(0)}); d.flags=Object.assign({},d.flags,{other_share:0.3}); const on=__text(${PAGE(0)}); const x=actOther(d.flags);
    const tip=__text(AS._.TIPS.oth(a.i)); ${RESET} ${FRESH} return {off:off.indexOf('other networks add')>=0, on, x, tip}; })()`);
  // 4 · the engine's older findings: the All-apps "▸ Older changes (N)" fold (DATA.active.info, src older) and the app page's (its file's)
  get('older', `(()=>{ ${RESET} ${FRESH} const A=AS._.A(), mkO=(a,k)=>({app_id:a.id,src:'older',kind:'act_drift',metric:k?'sess':'ret_dau',dir:'down',from:AS._.dOf(40+k),to:AS._.dOf(100),rel:-0.42+k/100,
      text:'old users ke sessions per user kam: 6.08 → 3.51/day (−42%)',tags:[],prov:false,release:{date:AS._.dOf(38),key:'ver:9.9@x',label:'v9.9'},started:AS._.dOf(40+k)});
    DATA.active.info=(DATA.active.info||[]).concat([mkO(A[0],0),mkO(A[1],1)]); AS._.detOf(A[0]).changes.older=[mkO(A[0],0),mkO(A[0],2),mkO(A[0],3)];
    actScreen(); __flush(); AS._.ST.folds=new Set(['hold','pghold']); const chg=AS._.chg(); AS._.ST.chgView='table'; const tbl=AS._.chg(); AS._.ST.chgView='cards'; const page=${PAGE(0)}; AS._.ST.folds=new Set();
    DATA=JSON.parse(JSON.stringify(__DASH)); ${RESET} ${FRESH} return {chg, tbl, page:page.slice(page.indexOf('id="as-pg"'),page.indexOf('id="act-old"'))}; })()`);
  // 5 · All apps day by day: the old date-wise view's guards (actPfSeries) in the Studio's table, markers and the guard line
  get('hon', `(()=>{ ${RESET} ${FRESH} KWIN='60'; actScreen(); __flush(); const S=actPfSeries(actRows().filter(r=>uniVis(r.app_id))), W=AS._.W(), ix=AS._.ix, dOf=AS._.dOf;
    const led=AS._.ledger(), rows=__rows(led), head=(led.match(/<th[^>]*>[^<]*<\\/th>/g)||[]).map(x=>__text(x));
    const exp=[]; for(let i=ix(W.t);i>=ix(W.f);i--){ const j=uniDiff(S.from,dOf(i)); exp.push({d:dOf(i),k:S.ap[j],n:S.nn[j],wow:S.wow[j]!=null?uniChg(S.wow[j]):'—',inc:!!(S.inc[j]&&S.ap[j]>0),marks:actPfMarks(S,0).filter(m=>m.i===j).map(m=>m.o.map(c=>c.s))}); }
    const r={head,cells:rows.map(x=>x.cells),exp,hon:AS._.honHtml(),ev:AS._.evOf(W.f,W.t),kpis:AS._.kpis(),kpis2:AS._.kpis2(),PD:{d7:AS._.PD().d7,d7k:AS._.PD().d7k,se:AS._.PD().se},
      S:{from:S.from,d7n:S.d7n,d7d:S.d7d,sS:S.sS,sU:S.sU}};
    // a big app's day missing (its active users unknown that day) → ⏸️ on that day, "Big app data missing" in the guard line
    const big=ACTPF.apps.slice().sort((p,q)=>(q.a1[q.a1.length-3]||0)-(p.a1[p.a1.length-3]||0))[0], k=big.a1.length-5; big.a1[k]=null; ACTPF=JSON.parse(JSON.stringify(ACTPF)); ACTPFC=null;
    actScreen(); __flush(); r.missDay=uniAdd(big.start,k); r.missLed=__rows(AS._.ledger()).map(x=>x.cells); r.missHon=AS._.honHtml(); r.missEv=AS._.evOf(AS._.W().f,AS._.W().t);
    const ri=ix(r.missDay); r.missTip=__text(AS._.TIPS.hon(ri));
    ${FRESH} ${RESET} return r; })()`);
  get('honNone', `(()=>{ ${RESET} ${FRESH} ACTPF=null; ACTPFC=null; actScreen(); __flush(); const r={led:AS._.ledger(),hon:AS._.honHtml()}; ${FRESH} return r; })()`);
  // 6 · a return's change: the arrow follows the rate (the table cell's rule) everywhere
  get('retdl', `(()=>{ ${RESET} ${FRESH} actScreen(); __flush(); const k=AS._.kpis(), k2=AS._.kpis2(); return {k:__text(k), k2:__text(k2)}; })()`);
  // 7 · the old views' small fixes: Revenue per user said per user; the old "Installs / day" tile is a daily number; the pointers
  get('oldfix', `(()=>{ ${RESET} ${FRESH} DATA.active.studio=null; delete DATA.active.studio; const rows=actRows().filter(r=>uniVis(r.app_id)); const P=actPortfolio(true);
    const tiles=actPoolKwTiles(rows), S=actPfSeries(rows); const appRow=rows.find(r=>ACTD[r.key]); const d=ACTD[appRow.key];
    const sum=actSumCard(d,appRow), tri=actTriCard(d); DATA=JSON.parse(JSON.stringify(__DASH)); const hint=asAppPage(appRow);
    return {table:P.table, tiles:tiles.html, arpdau:(d.tiles||{}).arpdau, arpTxt:rows.map(r=>{ const v=((r.m||{}).arpdau||{}).v; return actOk(v)?'≈ '+actMoneyU(v,DATA.active.currency||undefined):null; }).filter(Boolean),
      perK:rows.map(r=>{ const v=((r.m||{}).arpdau||{}).v; return actOk(v)?'≈ '+actMoney(v,DATA.active.currency||undefined):null; }).filter(Boolean), sum, tri, hint, cur:actCurOf(d)}; })()`);
  // 8 · every word the new pieces show
  get('words', `(()=>{ ${RESET} ${FRESH} const T=[]; for(const k of ['7','30','60']){ KWIN=k; T.push(__text(AS._.ledger())); T.push(__text(AS._.honHtml())); T.push(__text(AS._.kpis())); actScreen(); __flush(); }
    AS._.A().forEach((a,i)=>{ T.push(__text(AS._.verHtml(AS._.R()[i]))); T.push(__text(AS._.TIPS.ar(i))); (AS._.verRows(a).rows||[]).forEach((v,k)=>T.push(__text(AS._.TIPS.ver(i,k)))); });
    for(let i=AS._.ix(AS._.W().f);i<=AS._.ix(AS._.W().t);i++){ T.push(__text(AS._.TIPS.hon(i))); T.push(__text(AS._.TIPS.wow(i))); }
    ${RESET} return T; })()`);
} else {
  ctx.__DASH = J('dashboard.json'); ctx.__STUDIO = J('value_studio.json'); ctx.__VALFILES = J('value_files.json');
  const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; VALAPP=''; CURVIEW='USD'; VALJUMP='';`;
  const FRESH = `VALD={}; Object.assign(VALD,JSON.parse(JSON.stringify(__VALFILES)));`;
  run(`DATA=JSON.parse(JSON.stringify(__DASH)); ${RESET} VS._.load(__STUDIO); ${FRESH}`);
  const PAGE = id => `(()=>{ const row=valRows().find(x=>x.app_id===${id}); APP=row.app; VALAPP=row.app_id; const h=valScreen(); __flush(); return h; })()`;
  // 1 · week by week: every week of the app's detail file, = the old "Money back by install week" table (All weeks)
  get('weeks', `(()=>{ ${RESET} ${FRESH} valScreen(); __flush(); return VS._.A().map(a=>{ const d=VS._.detV(a), row=valRows().find(x=>x.app_id===a.id); if(!d) return {nm:a.nm,nodet:1};
    VALWK='all'; const old=__rows(valPayCard(d,row)).filter(r=>/data-week=/.test(r.attrs)).map(r=>({w:(r.attrs.match(/data-week="([^"]+)"/)||[])[1],c:r.cells})); VALWK='12';
    const WA=VS._.wkAll(a); return {nm:a.nm,src:WA.src,paid:(d.weeks||[]).some(w=>w.judged),old,st:WA.rows.map(r=>({w:r.from,n:r.n,sp:r.sp,v:r.v,p100:r.p100||null,jo:r.jo,pay:VS._.payTxt(r.pay,r.jd),vt:r.v.map(x=>x==null?null:VS._.mP(x))}))}; }); })()`);
  get('modes', `(()=>{ ${RESET} ${FRESH} valScreen(); __flush(); const a=VS._.A().find(x=>VS._.detV(x)&&(VS._.detV(x).weeks||[]).length>12)||VS._.A()[0], o=VS._.R()[a.i], r={n:VS._.wkAll(a).rows.length};
    for(const m of ['12','26','all','rng']){ VS._.ST.wk=m; const h=VS._.weekTable(o); r[m]=__rows(h).filter(x=>!/vs-wk-rel/.test(x.attrs)).length; r[m+'p']=/aria-pressed="true">([^<]*)</.exec(h)[1]; }
    VS._.ST.wk='12'; const W=VS._.W(); r.rngExp=VS._.wkAll(a).rows.filter(x=>x.from>=VS._.wS(Math.min(W.c0,W.i0))&&x.from<=VS._.wE(W.i1)).length;
    const page=${PAGE('a.id')}; r.inPage=page.indexOf('data-wk="all"')>=0; ${RESET} return r; })()`);
  // 2 · a no-ads app: its 30-day earning per install (= the old row's rpi.d30) where the Studio said "—"
  get('r30', `(()=>{ ${RESET} ${FRESH} valScreen(); __flush(); const o=VS._.R().find(x=>!x.s.ads&&x.a.eng&&x.a.eng.r30!=null), a=o.a, row=valRows().find(x=>x.app_id===a.id);
    const tbl=VS._.tbl(), map=VS._.map(); VS.openDrawer(a.i); const dr=document.getElementById('vs-drawer').innerHTML; VS.closeDrawer(); const page=${PAGE('a.id')};
    ${RESET} valScreen(); __flush(); CURVIEW='INR'; valScreen(); __flush(); const inr=VS._.r30Of(VS._.R()[a.i]); const inrTxt=VS._.mP(inr.v), oldInr=valMoney(a.eng.r30); CURVIEW='USD'; valScreen(); __flush();
    return {nm:a.nm, r30:VS._.r30Of(VS._.R()[a.i]), eng:a.eng.r30, old:(row.rpi||{}).d30, oldTxt:valMoney((row.rpi||{}).d30), mp:VS._.mP(a.eng.r30), inrTxt, oldInr,
      tblRow:__rows(tbl).find(x=>x.attrs.indexOf('data-app="'+a.i+'"')>=0), mapHas:map.indexOf('vs-noads')>=0&&map.indexOf('data-tk="r30:'+a.i+'"')>=0, map:__text(map.slice(map.indexOf('vs-noads'))),
      drawer:__text(dr), page:__text(page.slice(page.indexOf('id="vs-root"'),page.indexOf('id="val-oldapp"'))), tip:__text(VS._.TIPS.r30(a.i))}; })()`);
  // 3 · the app page's closed alerts: a "▸ Closed alerts (N)" fold, each with its 🕒 line (from the app's file, the old page's list)
  get('closed', `(()=>{ ${RESET} ${FRESH} const a=VS._.A()[0], d=VS._.detV(a);
    d.changes=Object.assign({},d.changes,{closed:[{app_id:a.id,app:a.nm,family:'pay_slow',metric:'pay',severity:'warning',dir:'down',now:140,before:80,opened:'2026-08-10',closed:'2026-09-01',closed_at:'2026-09-02T03:30:00Z',alert_at:'2026-08-11T04:00:00Z',started:'2026-08-03',text:'Paisa wapas ab 140 din me (pehle 80)',data_till:'2026-08-30',reason:'recovered'}]});
    VS._.ST.folds=new Set(['pghcl']); const h=${PAGE('a.id')}; VS._.ST.folds=new Set(); const n=VS._.closedOf(a).length; ${FRESH} ${RESET}
    return {n, page:h.slice(h.indexOf('id="vs-root"'),h.indexOf('id="val-oldapp"'))}; })()`);
  // 4 · "Other small countries (0)" is not a row (the GA4 'other' bucket alone); the unmatched Google Ads cost stays said
  get('small', `(()=>{ ${RESET} ${FRESH} valScreen(); __flush(); const a=VS._.A().find(x=>x.cty&&x.cty.rows&&x.cty.rows.length), C=a.cty, keep=[C.small,C.unm];
    C.small=[1200,0,5000,500]; C.unm=[3000,100]; VS.openDrawer(a.i); const zero=document.getElementById('vs-drawer').innerHTML;
    C.small=[1200,3,5000,500]; VS.openDrawer(a.i); const three=document.getElementById('vs-drawer').innerHTML; VS.closeDrawer(); C.small=keep[0]; C.unm=keep[1];
    return {zero:__text(zero), three:__text(three)}; })()`);
  get('mp', `(()=>{ ${RESET} return [VS._.mP(0.00000087), VS._.mP(0.006), VS._.mP(0.0042), VS._.mP(0.042), VS._.mP(1.5)]; })()`);
  get('news', `(()=>{ ${RESET} ${FRESH} valScreen(); __flush(); const h=VS._.chg(); const cards=(h.match(/<div class="vs-ac vs-s-(behtar|bigda)"[^>]*><div class="vs-l1"><span class="vs-chip vs-st-([a-z]+)"/g)||[]); return {cards, h:__text(h)}; })()`);
  get('words', `(()=>{ ${RESET} ${FRESH} const T=[]; valScreen(); __flush(); VS._.A().forEach(a=>{ const o=VS._.R()[a.i]; for(const m of ['12','26','all','rng']){ VS._.ST.wk=m; T.push(__text(VS._.weekTable(o))); }
      VS.openDrawer(a.i); T.push(__text(document.getElementById('vs-drawer').innerHTML)); if(VS._.r30Of(o)) T.push(__text(VS._.TIPS.r30(a.i))); });
    VS.closeDrawer(); VS._.ST.wk='12'; T.push(__text(VS._.map())); T.push(__text(VS._.tbl())); ${RESET} return T; })()`);
}
out.n = Object.keys(out).length;
process.stdout.write(JSON.stringify({ errors, out }));
