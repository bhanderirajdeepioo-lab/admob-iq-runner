// 🗂 Alert history in the Studios — the page side, rendered for real: runs the dashboard script (frontend/index.html's largest
// <script>) in a node vm with stub browser globals and a small DOM (every "us-…" / "as-…" / "vs-…" id is a real element), on
// synthetic Studio files the REAL build code made (tests/test_alert_history_frontend.py), plus synthetic closed alerts and older
// changes put into the very lists the older views read (no real data). Prints ONE JSON report; the Python test asserts on it.
//   usage: node alert_history_frontend.js <script.js> <dir> <us|active|value>
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
  scrollTop: 0, scrollLeft: 0, scrollWidth: 0, clientWidth: 1000, offsetParent: {}, offsetWidth: 100, offsetHeight: 20, value: '',
  get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; },
  querySelector: () => mk('_q'), querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, appendChild() {},
  getBoundingClientRect: () => ({ left: 0, top: 400, right: 100, bottom: 420, width: 100, height: 20 }), focus() {}, scrollIntoView() {}, closest: () => null };
  return e; }
const ELS = {}, LST = {}, NULLIDS = new Set();
const document = new Proxy({
  getElementById: id => (NULLIDS.has(String(id)) ? null : (/^(us|as|vs)-/.test(String(id)) ? (ELS[id] = ELS[id] || mk(id)) : any)),
  createElement: () => mk('_new'), body: mk('body'), head: mk('head'), documentElement: mk('html'),
  querySelector: () => null, querySelectorAll: () => [], addEventListener(k, f) { (LST[k] = LST[k] || []).push(f); }, removeEventListener() {}, activeElement: null,
}, { get: (t, k) => (k in t ? t[k] : any) });
const LSB = {};
const timers = [], scrolls = [];
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: null, document, localStorage: { getItem: k => (k in LSB ? LSB[k] : null), setItem: (k, v) => { LSB[k] = String(v); }, removeItem: k => { delete LSB[k]; } },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} }, navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', reload() {} }, history: any,
  fetch: () => new Promise(() => {}), setTimeout: (f) => { timers.push(f); return timers.length; }, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String,
  Set, Map, Float64Array, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent, performance: { now: () => 0 },
  getComputedStyle: () => new Proxy({ position: 'static' }, { get: (t, k) => (k in t ? t[k] : any) }), innerWidth: 1280, innerHeight: 900, scrollY: 0, pageYOffset: 0,
  scrollTo: o => { scrolls.push(o); }, alert() {}, confirm: () => false,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any,
};
ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx; ctx.__LST = LST; ctx.__ELS = ELS; ctx.__NULL = NULLIDS; ctx.__SCROLLS = scrolls;
ctx.__flush = () => { let n = 0; while (timers.length && n++ < 500) { const f = timers.shift(); try { f(); } catch (e) { errors.push('timer ' + e.message); } } };
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
ctx.__text = h => String(h).replace(/<style[\s\S]*?<\/style>/g, '').replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
// a day N days from the dashboard's today; one fold's body (the <details data-fold="k"> … </details>) out of some markup
run(`function __D(n){ return new Date(Date.parse(smpToday()+'T00:00:00Z')+n*864e5).toISOString().slice(0,10); }
  function __fold(h,k){ const i=String(h).indexOf('data-fold="'+k+'"'); if(i<0) return null; const s=String(h).lastIndexOf('<details',i), e=String(h).indexOf('</details>',i); return String(h).slice(s,e+10); }
  function __sum(h,k){ const f=__fold(h,k); return f?__text((f.match(/<summary>[\\s\\S]*?<\\/summary>/)||[''])[0]):null; }
  function __toggle(k,open){ (__LST.toggle||[]).forEach(f=>{ try{ f({target:{closest:()=>({}),dataset:{fold:k},open,id:''}}); }catch(e){} }); }`);
const out = {};
function get(name, code) { try { const v = run(code); out[name] = typeof v === 'string' ? v : JSON.stringify(v); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); } }

if (mode === 'us') {
  ctx.__DASH = J('dashboard.json'); ctx.__STUDIO = J('uninstall_studio.json'); ctx.__UNI = J('uninstall.json');
  const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; UNIAPP=''; CURVIEW='USD';`;
  run(`DATA=JSON.parse(JSON.stringify(__DASH)); UNI=JSON.parse(JSON.stringify(__UNI)); UNIERR=false; UNICOH={}; ${RESET} US._.load(__STUDIO); uniScreen(); __flush();`);
  // synthetic history on the first two Studio apps: a recovered install-week alert (both run times kept), a rate alert closed
  // before reasons were kept (data days only), an update's alert a newer update replaced, and three older changes
  run(`(()=>{ const A=US._.A(), u=id=>UNI.apps.find(z=>z.app_id===id); const u0=u(A[0].id), u1=u(A[1].id);
    u0.alerts_closed=(u0.alerts_closed||[]).concat([
      {id:'h1',app_id:A[0].id,family:'cohort',dir:'up',severity:'warning',n:0,now:0.30,before:0.20,users:700,installs_from:__D(-20),installs_to:__D(-14),base_from:__D(-48),base_to:__D(-21),vs:['prev'],unit:'pct',
       opened:__D(-12),opened_at:__D(-10)+'T05:00:00Z',alert_at:__D(-10)+'T05:00:00Z',closed:__D(-3),closed_at:__D(-1)+'T06:30:00Z',close_reason:'recovered',started:__D(-20)},
      {id:'h2',app_id:A[0].id,family:'rate_drift',dir:'up',severity:'watch',now:12.0,before:9.0,since:__D(-40),data_till:__D(-30),unit:'per1k',opened:__D(-30),alert_at:__D(-28)+'T05:00:00Z',closed:__D(-25),close_reason:null,started:__D(-40)}]);
    u1.alerts_closed=(u1.alerts_closed||[]).concat([{id:'h3',app_id:A[1].id,family:'impact',dir:'up',severity:'warning',level:'halt',release:{key:'ver:9.9@'+__D(-60),label:'v9.9',date:__D(-60)},
       rows:{worse:['uninstall_d0'],better:[]},now:0.3,before:0.2,users:500,installs_from:__D(-60),installs_to:__D(-54),opened:__D(-52),opened_at:__D(-50)+'T04:00:00Z',closed:__D(-40),closed_at:__D(-38)+'T06:00:00Z',close_reason:'superseded',started:__D(-60)}]);
    const oc=(n,f)=>({n,dir:'up',now:0.6,before:0.5,users:300,installs_from:__D(f),installs_to:__D(f+6),base_from:__D(f-28),base_to:__D(f-1),started:__D(f),vs:[]});
    u0.old_changes=(u0.old_changes||[]).concat([oc(7,-120),oc(30,-150)]); u1.old_changes=(u1.old_changes||[]).concat([oc(14,-130)]); })()`);
  const EXP = `(()=>{ const ids=new Set(US._.A().map(a=>a.id)), L=UNI.apps.filter(a=>ids.has(a.app_id)); return {cl:L.reduce((t,a)=>t+(a.alerts_closed||[]).length,0), old:L.reduce((t,a)=>t+(a.old_changes||[]).length,0)}; })()`;
  get('all', `(()=>{ ${RESET} uniScreen(); __flush(); const ST=US._.ST; ST.folds=new Set(); ST.chgView='cards'; const shut=US._.chg(); ST.folds=new Set(['hold','hcl']); const open=US._.chg();
    ST.chgView='table'; const tbl=US._.chg(); ST.chgView='cards'; ST.folds=new Set();
    return {exp:${EXP}, shut, open, tbl, sumOld:__sum(shut,'hold'), sumCl:__sum(shut,'hcl'), theekFold:shut.indexOf('data-fold="theek"')>=0, hint:__text((shut.match(/<div class="us-hint"[^>]*>[^<]*/)||[''])[0])}; })()`);
  // Open → from All apps: the app's page (PJ waits for it); an update → its 📦 block (uniImpGo); impact_late at 30 days
  get('go', `(()=>{ ${RESET} uniScreen(); __flush(); const A=US._.A(), calls=[], keep={o:uniOpen,g:uniImpGo}; uniOpen=id=>calls.push(['open',id]); uniImpGo=(id,k,t,n)=>calls.push(['impgo',id,k,t,n===undefined?null:n]);
    const H=US._.hist(null), sp=x=>US._.goOf(x), h1=H.cl.find(x=>x.fam==='cohort'&&x.if===__D(-20)), h2=H.cl.find(x=>x.fam==='rate_drift'&&x.opened===__D(-30)), h3=H.cl.find(x=>x.rk==='ver:9.9@'+__D(-60));
    const specs={h1:sp(h1),h2:sp(h2),h3:sp(h3),late:sp(Object.assign({},h3,{fam:'impact_late'})),old:sp(H.old[0])};
    US._.goH(specs.h1,false); const pj=US._.PJ(); US._.goH(specs.h3,false); uniOpen=keep.o; uniImpGo=keep.g;
    return {specs,calls,pj:pj&&{id:pj.id,s:pj.s},a0:A[0].id,a1:A[1].i,a1id:A[1].id,a0i:A[0].i,from:__D(-20),to:__D(-14),key:'ver:9.9@'+__D(-60)}; })()`);
  // the app page: its folds (this app's lists), the jump targets' ids, a jump on the page, the waiting jump, the quick look
  get('page', `(()=>{ ${RESET} uniScreen(); __flush(); const A=US._.A(), a=A[0], row=(DATA.uninstall.apps||[]).find(x=>x.app_id===a.id), d=UNI.apps.find(z=>z.app_id===a.id);
    const calls=[], keep=uniOpen; uniOpen=id=>calls.push(id); const H=US._.hist(a.id), coh=H.cl.find(x=>x.fam==='cohort'&&x.if===__D(-20)); US._.goH(US._.goOf(coh),false); uniOpen=keep;
    APP=row.app; UNIAPP=a.id; US._.ST.folds=new Set(['pghold','pghcl']); const h=uniScreen(); Object.keys(__ELS).forEach(k=>__ELS[k].classList.remove('us-ahj'));
    US._.pjNow(); const waited=__ELS['us-pg-coh'].classList.contains('us-ahj'), pjAfter=US._.PJ();
    const rate=H.cl.find(x=>x.fam==='rate_drift'&&x.opened===__D(-30)); US._.goH(US._.goOf(rate),false); const rateFl=__ELS['us-pg-rate'].classList.contains('us-ahj');
    const view=US._.view(); US._.ST.folds=new Set(); APP=''; UNIAPP=''; uniScreen(); US.openDrawer(a.i); const dr=document.getElementById('us-drawer').innerHTML; US.closeDrawer();
    return {page:h, view, exp:{cl:(d.alerts_closed||[]).length, old:(d.old_changes||[]).length}, calls, waited, pjAfter, rateFl, drawer:dr, sumOld:__sum(h,'pghold'), sumCl:__sum(h,'pghcl')}; })()`);
  // the 5-minute refresh repaints with render(): the folds the viewer opened (the toggle listener) stay open, the others shut
  get('refresh', `(()=>{ ${RESET} uniScreen(); __flush(); US._.ST.folds=new Set(); __toggle('hcl',true); __toggle('hold',true); __toggle('hold',false); const h=uniScreen();
    return {cl:/data-fold="hcl" open/.test(h), old:/data-fold="hold" open/.test(h), folds:[...US._.ST.folds]}; })()`);
} else if (mode === 'active') {
  ctx.__DASH = J('dashboard.json'); ctx.__STUDIO = J('active_studio.json'); ctx.__ACTFILES = J('active_files.json'); ctx.__PF = J('active_portfolio.json');
  const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; ACTAPP=''; CURVIEW='USD'; ACTJUMP=''; ACTIMPJUMP='';`;
  const FRESH = `ACTD={}; Object.assign(ACTD,JSON.parse(JSON.stringify(__ACTFILES))); ACTPF=JSON.parse(JSON.stringify(__PF)); ACTPFC=null;`;
  run(`DATA=JSON.parse(JSON.stringify(__DASH)); ${RESET} AS._.load(__STUDIO); ${FRESH} actScreen(); __flush();`);
  // synthetic history: the dashboard's lists (All apps) and the first app's own file (its page)
  run(`(()=>{ const A=AS._.A(), a0=A[0], a1=A[1];
    const c1={app_id:a0.id,app:a0.nm,family:'act_drift',metric:'ret_dau',severity:'warning',dir:'down',now:900,before:1000,rel:-0.1,since:__D(-30),data_till:__D(-10),opened:__D(-20),opened_at:__D(-18)+'T05:00:00Z',alert_at:__D(-18)+'T05:00:00Z',closed:__D(-4),closed_at:__D(-2)+'T05:00:00Z',close_reason:'recovered',started:__D(-30)};
    const c2={app_id:a1.id,app:a1.nm,family:'act_return',metric:'d7',severity:'watch',dir:'down',now:0.08,before:0.12,users:400,installs_from:__D(-50),installs_to:__D(-44),opened:__D(-40),closed:__D(-30),close_reason:'window_end',started:__D(-50)};
    const c3={app_id:a0.id,app:a0.nm,family:'act_drift',metric:'sess',severity:'watch',dir:'down',now:2.0,before:2.5,rel:-0.2,since:__D(-90),data_till:__D(-80),opened:__D(-85),closed:__D(-70),close_reason:null,started:__D(-90)};
    const o=(a,k,m,f)=>({app_id:a.id,src:'older',kind:k,metric:m,dir:'down',from:__D(f),to:__D(f+20),rel:-0.3,text:'old users ke sessions per user kam: 3.0 → 2.1/day (−30%)',tags:[],prov:false,started:__D(f)});
    DATA.active.closed=[c1,c2]; DATA.active.info=(DATA.active.info||[]).filter(x=>x&&x.src!=='older').concat([o(a0,'act_drift','sess',-60),o(a1,'act_drift','ads',-70)]);
    const d=AS._.detOf(a0); d.changes=Object.assign({},d.changes,{closed:[c1,c3],older:[o(a0,'act_drift','sess',-60),o(a0,'act_drift','ret_dau',-65),o(a0,'price','ecpm',-75)]}); })()`);
  const PAGE = `(()=>{ const a=AS._.A()[0], row=actRows().find(x=>x.app_id===a.id); APP=row.app; ACTAPP=a.id; const h=actScreen(); __flush(); return h; })()`;
  get('all', `(()=>{ ${RESET} actScreen(); __flush(); const ST=AS._.ST, ids=new Set(AS._.A().map(a=>a.id)); ST.folds=new Set(); ST.chgView='cards'; const shut=AS._.chg(); ST.folds=new Set(['hold','hcl']); const open=AS._.chg();
    ST.chgView='table'; const tbl=AS._.chg(); ST.chgView='cards'; ST.folds=new Set();
    return {exp:{cl:DATA.active.closed.filter(x=>ids.has(x.app_id)).length, old:DATA.active.info.filter(x=>x.src==='older'&&ids.has(x.app_id)).length}, shut, open, tbl,
      sumOld:__sum(shut,'hold'), sumCl:__sum(shut,'hcl'), theekFold:/Closed — last 7 days/.test(shut), olderFold:/🗄 Older \\(/.test(shut)}; })()`);
  get('go', `(()=>{ ${RESET} actScreen(); __flush(); const A=AS._.A(), a0=A[0], P=(m,f)=>AS._.goOf({a:a0.i,m,fam:f});
    const specs={ret:P('ret_dau','act_drift'),d7:P('d7','act_return'),sess:P('sess','act_drift'),time:P('time','act_drift'),ads:P('ads','act_drift'),arpdau:P('arpdau','act_drift'),price:P('ecpm','price'),brk:P('a1','act_break'),
      old:AS._.goOld({a:a0,o:{metric:'sess',kind:'act_drift'}}),oldPrice:AS._.goOld({a:a0,o:{metric:'ecpm',kind:'price'}})};
    const calls=[], keep=actOpen; actOpen=id=>calls.push(['open',id,ACTJUMP]); AS._.goH(specs.ret,false); const pj=AS._.PJ(); ACTJUMP=''; AS._.goH(specs.sess,false); const aj=ACTJUMP; actOpen=keep; ACTJUMP='';
    return {specs,calls,pj:pj&&{id:pj.id,sec:pj.sec},aj,a0:a0.id,i0:a0.i}; })()`);
  get('page', `(()=>{ ${RESET} const h=${PAGE}; const d=AS._.detOf(AS._.A()[0]); AS._.ST.folds=new Set(['pghold','pghcl']); const h2=${PAGE};
    Object.keys(__ELS).forEach(k=>__ELS[k].classList.remove('as-ahj')); AS._.goH(AS._.goOf({a:AS._.A()[0].i,m:'d7',fam:'act_return'}),false); const triFl=__ELS['as-pg-tri'].classList.contains('as-ahj');
    const rr=[], keep2=actRerender; actRerender=()=>rr.push(ACTJUMP); AS._.goH(AS._.goOf({a:AS._.A()[0].i,m:'time',fam:'act_drift'}),false); actRerender=keep2; const aj=ACTJUMP; ACTJUMP='';
    const mode=AS._.MODE(); AS._.ST.folds=new Set(); ${RESET} actScreen(); __flush();
    return {page:h2, exp:{cl:d.changes.closed.length, old:d.changes.older.length}, triFl, rr, aj, mode, sumOld:__sum(h2,'pghold'), sumCl:__sum(h2,'pghcl')}; })()`);
  get('refresh', `(()=>{ ${RESET} actScreen(); __flush(); AS._.ST.folds=new Set(); __toggle('hcl',true); __toggle('hold',true); const h=actScreen(); __toggle('hold',false); const h2=actScreen();
    return {cl:/data-fold="hcl" open/.test(h)&&/data-fold="hcl" open/.test(h2), old:/data-fold="hold" open/.test(h), oldShut:!/data-fold="hold" open/.test(h2)}; })()`);
} else {
  ctx.__DASH = J('dashboard.json'); ctx.__STUDIO = J('value_studio.json'); ctx.__VALFILES = J('value_files.json');
  const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; VALAPP=''; CURVIEW='USD'; VALJUMP=''; VALCHKEXP=false;`;
  const FRESH = `VALD={}; Object.assign(VALD,JSON.parse(JSON.stringify(__VALFILES)));`;
  run(`DATA=JSON.parse(JSON.stringify(__DASH)); ${RESET} VS._.load(__STUDIO); ${FRESH} valScreen(); __flush();`);
  // synthetic history: one closed value alert in the dashboard's list; info rows over 30 days old in this file; the first
  // app's own file: two closed alerts and one older info row only it has
  run(`(()=>{ const A=VS._.A(), a0=A[0], a1=A[1];
    const v1={app_id:a0.id,app:a0.nm,family:'pay_slow',metric:'pay',severity:'warning',dir:'down',p0:60,p:120,opened:__D(-30),opened_at:__D(-28)+'T05:00:00Z',alert_at:__D(-28)+'T05:00:00Z',closed:__D(-3),closed_at:__D(-1)+'T05:00:00Z',close_reason:'recovered',started:__D(-37),week_from:__D(-37),week_to:__D(-31)};
    const v2={app_id:a0.id,app:a0.nm,family:'geo_move',metric:'d7',cc:'IN',severity:'watch',dir:'down',now:8,before:12,users:300,opened:__D(-90),closed:__D(-60),close_reason:'window_end',started:__D(-97),week_from:__D(-97),week_to:__D(-91)};
    DATA.value.closed=[v1];
    a0.info=a0.info.concat([['mix',__D(-70),__D(-64),__D(-70),'IN','Country mix badla']]); a1.info=a1.info.concat([['spend',__D(-45),__D(-39),__D(-45),'','Ads spend badla']]);
    const d=VS._.detV(a0); d.changes=Object.assign({},d.changes,{closed:[v1,v2],info:(d.changes&&d.changes.info||[]).concat([{kind:'k',from:__D(-80),to:__D(-74),started:__D(-80),text:'Data scale badla'}])}); })()`);
  const PAGE = `(()=>{ const a=VS._.A()[0], row=valRows().find(x=>x.app_id===a.id); APP=row.app; VALAPP=a.id; const h=valScreen(); __flush(); return h; })()`;
  get('all', `(()=>{ ${RESET} valScreen(); __flush(); const ST=VS._.ST, ids=new Set(VS._.A().map(a=>a.id)), today=smpToday(); ST.folds=new Set(); ST.chgView='cards'; const shut=VS._.chg(); ST.folds=new Set(['hold','hcl']); const open=VS._.chg();
    ST.chgView='table'; const tbl=VS._.chg(); ST.chgView='cards'; ST.folds=new Set();
    const old=VS._.A().reduce((t,a)=>t+a.info.filter(x=>{ const d=x[3]||x[1]; return d&&uniDiff(d,VS._.M().today)>30; }).length,0);
    return {exp:{cl:DATA.value.closed.filter(x=>ids.has(x.app_id)).length, old}, shut, open, tbl, sumOld:__sum(shut,'hold'), sumCl:__sum(shut,'hcl'), oldFold:/🗄 Old info/.test(shut), bandFold:/Band hue value alerts/.test(shut)}; })()`);
  get('go', `(()=>{ ${RESET} valScreen(); __flush(); const A=VS._.A(), a0=A[0], z=(f,x)=>VS._.goAl({a:a0,x:Object.assign({family:f},x||{})}), I=k=>VS._.goInf(a0,[k,null,null,null,'','']);
    const specs={pay:z('pay_slow'),loss:z('pay_loss'),geo:z('geo_move'),cost:z('geo_cost'),ver:z('ver_ret',{ver:'9.9',ver_label:'v9.9'}),lng:z('long_ret'),link:z('iv_link'),
      mix:I('mix'),spend:I('spend'),k:I('k'),vd:I('ver_d30'),lu:I('long_up')};
    const calls=[], keep=valOpen; valOpen=id=>calls.push(id); VS._.goH(specs.cost,false); const pj=VS._.PJ(); valOpen=keep;
    return {specs,calls,pj:pj&&{id:pj.id,s:pj.s},a0:a0.id,i0:a0.i}; })()`);
  get('page', `(()=>{ ${RESET} VS._.ST.folds=new Set(['pghold','pghcl']); const h=${PAGE}; const a=VS._.A()[0], d=VS._.detV(a);
    Object.keys(__ELS).forEach(k=>__ELS[k].classList.remove('vs-ahj')); VS._.goH(VS._.goAl({a,x:{family:'geo_move'}}),false); const ctyFl=__ELS['vs-pg-cty'].classList.contains('vs-ahj');
    __NULL.add('vs-pg-chk'); const keep=valRerender, rr=[]; valRerender=()=>rr.push([VALJUMP,VALCHKEXP]); VS._.goH(VS._.goAl({a,x:{family:'iv_link'}}),false); valRerender=keep; __NULL.delete('vs-pg-chk');
    const mode=VS._.MODE(); VS._.ST.folds=new Set(); ${RESET} valScreen(); __flush();
    return {page:h, exp:{cl:d.changes.closed.length, oldInfo:a.info.filter(x=>{ const t=x[3]||x[1]; return t&&uniDiff(t,VS._.M().today)>30; }).length}, ctyFl, rr, mode, sumOld:__sum(h,'pghold'), sumCl:__sum(h,'pghcl')}; })()`);
  get('refresh', `(()=>{ ${RESET} valScreen(); __flush(); VS._.ST.folds=new Set(); __toggle('hcl',true); __toggle('hold',true); const h=valScreen(); __toggle('hold',false); const h2=valScreen();
    return {cl:/data-fold="hcl" open/.test(h)&&/data-fold="hcl" open/.test(h2), old:/data-fold="hold" open/.test(h), oldShut:!/data-fold="hold" open/.test(h2)}; })()`);
}
out.n = Object.keys(out).length;
process.stdout.write(JSON.stringify({ errors, out }));
