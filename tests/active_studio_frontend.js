// 🧭 Active users Studio — the page side, rendered for real: runs the dashboard script (frontend/index.html's largest
// <script>) in a node vm with stub browser globals and a small DOM (every "as-…" id is a real element holding its
// innerHTML), on a synthetic Studio file the REAL build code made (tests/test_active_studio_frontend.py:
// tests/active_studio_synth.py + the build step), and prints ONE JSON report; the Python test asserts on it.
//   usage: node active_studio_frontend.js <script.js> <dir with dashboard.json + active_studio.json>
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const [scriptPath, dir] = process.argv.slice(2);
const J = n => JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8'));
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// ── a small DOM: "as-…" ids are real (innerHTML kept), everything else is the inert stub ──
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
const body = mk('body');
const document = new Proxy({
  getElementById: id => (/^as-/.test(String(id)) ? (ELS[id] = ELS[id] || mk(id)) : any),
  createElement: () => mk('_new'), body, head: mk('head'), documentElement: mk('html'),
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, activeElement: null,
}, { get: (t, k) => (k in t ? t[k] : any) });
const LSB = {};
const localStorage = { getItem: k => (k in LSB ? LSB[k] : null), setItem: (k, v) => { LSB[k] = String(v); }, removeItem: k => { delete LSB[k]; } };
const timers = [];
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document, localStorage, sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} }, navigator: any,
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
ctx.__DASH = J('dashboard.json'); ctx.__STUDIO = J('active_studio.json'); ctx.__ACTFILES = J('active_files.json');
const out = {};
function get(name, code) { try { out[name] = run(code); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); } }
const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; ACTAPP=''; CURVIEW='USD'; ACTJUMP=''; ACTIMPJUMP='';`;
run(`DATA=__DASH; ${RESET} AS._.load(__STUDIO); Object.assign(ACTD,__ACTFILES);`);   // (each app's own file: the older app page in full)
const text = h => String(h).replace(/<style[\s\S]*?<\/style>/g, '').replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
ctx.__text = text;
// the Studio's own words (the older views folded under it are the tab's earlier screens, kept exactly as they were)
const STUDIO_ONLY = h => { const a = h.indexOf('id="as-root"'), b = h.indexOf('id="act-old"'); return h.slice(a < 0 ? 0 : a, b < 0 ? h.length : b); };
ctx.__studio = STUDIO_ONLY;

// ── the screen, its order and the consistency rules ─────────────────────────────────────────────────────────────────
const ROWS = `o=>({i:o.a.i,nm:o.a.nm,id:o.a.id,pill:o.pill,rank:o.rank,ready:o.a.ready,steep:o.steep,alP:o.alP?o.alP.sev:null,
  L:(!o.L||o.L.far==null)?{why:o.L&&o.L.why}:{far:o.L.far,fi:o.L.fi,asli:o.L.asli,base:o.L.base,relT:o.L.relT,relA:o.L.relA,zT:o.L.zT,zA:o.L.zA,sigT:o.L.sigT,sigA:o.L.sigA,n:o.L.n,f:o.L.f,t:o.L.t,usd:o.L.usd,usdA:o.L.usdA,alR:!!o.L.alR},
  cells:[o.h1.s,o.h7.s,o.hse.s,o.htm.s]})`;
get('screen7', `(()=>{ ${RESET} const h=actScreen(); __flush(); return h; })()`);
get('order7', `(()=>{ const R=AS._.R(), A=AS._.A();
  const first=(h,re)=>{ const m=re.exec(h); return m?+m[1]:null; };
  const map=AS._.map(), story=AS._.story(), tbl=AS._.tbl();
  return JSON.stringify({
    names: A.map(a=>a.nm),
    map1: first(map.slice(map.indexOf('class="as-rk"')), /data-go="(\\d+)"/),
    loss: /Biggest real loss/.test(story)?first(story,/<button class="as-sc as-bad" data-app="(\\d+)"/):null,
    gain: /Biggest real gain/.test(story)?first(story,/<button class="as-sc as-good" data-app="(\\d+)"/):null,
    tbl1: first(tbl.slice(tbl.indexOf('<tbody')), /<tr data-app="(\\d+)"/),
    rank1: (R.find(o=>o.rank===1)||{a:{}}).a.i,
    rows: R.map(${ROWS}), W: AS._.W(), M: AS._.M(),
    PT: (p=>({Lfar:p.Lfar,Lfi:p.Lfi,Lasli:p.Lasli,Lnone:p.Lnone,Lusd:p.Lusd,LusdA:p.LusdA,nL:p.nL,ret:p.ret,ins:p.ins}))(AS._.PT()) }); })()`);
get('rows30', `(()=>{ ${RESET} KWIN='30'; actScreen(); __flush(); return JSON.stringify({W:AS._.W(), rows:AS._.R().map(${ROWS})}); })()`);

// ── the shared KPIWINDOW / compare / currency ───────────────────────────────────────────────────────────────────────
get('kwin', `(()=>{ ${RESET} const r={};
  KWIN='30'; const h30=actScreen(); r.ext30=AS._.W().L; r.win30=/\\(30 days\\)/.test(h30);
  AS._.setRange('14'); r.after14={KWIN, L:AS._.W().L, saved:JSON.parse(localStorage.getItem('kwin_v1')).win};
  AS._.setRange('c'); r.custom={KWIN, from:KWCUSTOM.from, to:KWCUSTOM.to, L:AS._.W().L};
  AS._.setCmp('month'); r.month={KCMP, saved:JSON.parse(localStorage.getItem('kwin_v1')).cmp, W:AS._.W()};
  AS._.setDate('as-ct1', AS._.M().E); AS._.setDate('as-cf1', AS._.dOf(AS._.ix(AS._.M().E)-9)); r.dates={KWIN, L:AS._.W().L, from:KWCUSTOM.from, to:KWCUSTOM.to};
  AS._.setDate('as-cf2', AS._.M().E); AS._.setDate('as-ct2', AS._.dOf(AS._.ix(AS._.M().E)-30)); r.cdates={KCMP, from:KCMPCUSTOM.from, to:KCMPCUSTOM.to};
  ${RESET} CURVIEW='INR'; r.inr=AS._.money(10); r.inrTiny=AS._.moneyL(0.05); CURVIEW='USD'; r.usd=AS._.money(10); r.usdTiny=AS._.moneyL(0.05);
  r.fx=DATA.usd_inr; ${RESET} return JSON.stringify(r); })()`);
get('header', `(()=>{ ${RESET} KWIN='60'; KCMP='month'; const h=actScreen(); ${RESET} return JSON.stringify({p60:/data-r="60" aria-pressed="true"/.test(h), month:/<option value="month" selected>/.test(h), usd:/data-c="USD" aria-pressed="true"/.test(h)}); })()`);

// ── the drawer → the app's page; a refresh keeps it; an app page closes it ─────────────────────────────────────────
get('drawer', `(()=>{ ${RESET} actScreen(); __flush(); const A=AS._.A(), r={}; const calls=[]; const keep=actOpen; actOpen=function(id){ calls.push(id); };
  AS.openDrawer(0); const h=document.getElementById('as-drawer').innerHTML; r.open=AS._.ST.drawer===0; r.full=(h.match(/Poora app page →/g)||[]).length;
  r.dataFull=(h.match(/data-full="([^"]+)"/)||[])[1]===A[0].id; r.lock=document.body.classList.contains('as-lock');
  actScreen(); __flush(); r.afterRefresh=AS._.ST.drawer===0&&AS._.ST.did===A[0].id&&document.getElementById('as-drawer').classList.contains('as-on');
  AS._.fullPage(A[0].id); r.calls=calls; r.closed=AS._.ST.drawer===-1&&!document.body.classList.contains('as-lock');
  actOpen=keep;
  AS.openDrawer(1); const nm=actRows().find(x=>x.app_id===A[1].id).app; APP=nm; ACTAPP=A[1].id; renderActive(); __flush(); r.closedOnAppPage=AS._.ST.drawer===-1; ${RESET}
  return JSON.stringify(r); })()`);
// ── one app's full page: the Studio's page + the WHOLE older page folded under it ─────────────────────────────────
get('page', `(()=>{ ${RESET} const r={}, A=AS._.A(), a=A.find(x=>x.ready&&x.rel.length)||A[0], row=actRows().find(x=>x.app_id===a.id);
  APP=row.app; ACTAPP=a.id; const h=actScreen(); __flush(); r.html=h; r.mode=AS._.MODE();
  r.order=[h.indexOf('id="as-root"'), h.indexOf('class="as-pgroot"'), h.indexOf('id="as-pg"'), h.indexOf('id="act-old"')];
  const nz=x=>x.replace(/(id="|url\\(#|href="#|data-bc=")([A-Za-z_-]*?)\\d+/g,'$1$2#');   // (the page's own chart-id counters)
  r.old=actAppOld(row); r.oldInFold=nz(h).indexOf(nz(r.old))>h.indexOf('id="act-old"'); r.oldFull=r.old.indexOf('⏳')!==0&&r.old.indexOf('id="act-')>=0;
  const ptr=DATA.active.studio; delete DATA.active.studio; r.noPtr=actScreen(); DATA.active.studio=ptr; r.noPtrSame=nz(r.noPtr)===nz(r.old);
  KWIN='30'; const h30=actScreen(); __flush(); r.win30=/\\(30 days\\)/.test(h30);
  ACTJUMP='act-chg'; ACTJT=Date.now(); r.foldOpenOnJump=/<details id="act-old" open/.test(actScreen()); ACTJUMP='';
  ${RESET} return JSON.stringify(r); })()`);

// ── every word the Studio shows (all ranges, the alert table, every drawer, the page, every tooltip) ────────────────
get('texts', `(()=>{ const T=[]; for(const k of ['7','14','30','60']){ for(const c of ['prev','month']){ ${RESET} KWIN=k; KCMP=c; T.push(__text(__studio(actScreen()))); __flush(); } }
  ${RESET} actScreen(); __flush(); AS._.ST.chgView='table'; T.push(__text(AS._.chg())); AS._.ST.chgView='cards';
  AS._.A().forEach((a,i)=>{ AS.openDrawer(i); T.push(__text(document.getElementById('as-drawer').innerHTML)); });
  AS.closeDrawer();
  const TP=AS._.TIPS, A=AS._.A(); A.forEach((a,i)=>{ ['app','far'].forEach(k=>T.push(__text(TP[k](i)))); ['d1','d7','d30','se','tm','rv','ad'].forEach(k=>T.push(__text(TP.cell(i,k))));
    a.tri.w.forEach(w=>[0,1,2,3,4].forEach(k=>T.push(__text(TP.tri(i,w.f,k))))); a.rel.forEach(r=>T.push(__text(TP.upd(i,r[0]))));
    T.push(__text(TP.io(i,AS._.ix(AS._.M().settled)))); });
  AS._.ALERTS().forEach(x=>T.push(__text(TP.al(x.k)))); T.push(__text(TP.ptl())); T.push(__text(TP.prov()));
  AS._.tl(); Object.keys(AS._.tl.ups||{}).forEach(d=>T.push(__text(TP.tlu(d)))); Object.keys(AS._.tl.als||{}).forEach(d=>T.push(__text(TP.tla(d))));
  A.forEach(a=>{ const row=actRows().find(x=>x.app_id===a.id); if(!row) return; APP=row.app; ACTAPP=a.id; T.push(__text(__studio(actScreen()))); __flush(); }); ${RESET}
  CURVIEW='INR'; T.push(__text(__studio(actScreen()))); __flush(); CURVIEW='USD';
  return JSON.stringify(T); })()`);
get('alerts', `JSON.stringify(AS._.ALERTS().map(x=>({k:x.k,a:x.a,sev:x.sev,kind:x.kind,at:x.at})))`);
get('chg', `(()=>{ ${RESET} actScreen(); __flush(); AS._.ST.folds=new Set(['achhi','info','theek','chhoti','purana']); return AS._.chg(); })()`);
get('chgTable', `(()=>{ ${RESET} actScreen(); __flush(); AS._.ST.chgView='table'; const h=AS._.chg(); AS._.ST.chgView='cards'; return h; })()`);

// ── the numbers printed on the charts ────────────────────────────────────────────────────────────────────────────
get('charts', `(()=>{ ${RESET} actScreen(); __flush(); const r={}, A=AS._.A();
  const k=AS._.kpis(), k2=AS._.kpis2(), m=AS._.map(), tl=AS._.tl();
  const spans=h=>(h.match(/<div class="as-spl2"[^>]*>(.*?)<\\/div>/g)||[]).map(x=>(x.match(/<span[^>]*>([^<]*)<\\/span>/g)||[]).map(s=>s.replace(/<[^>]*>/g,'')));
  r.kpis=spans(k); r.kpis2=spans(k2); r.map=spans(m).length; r.tl=(tl.match(/<text class="as-cl"[^>]*>([^<]*)<\\/text>/g)||[]).map(s=>s.replace(/<[^>]*>/g,''));
  const a=A.find(x=>x.rel.length&&x.al.length)||A.find(x=>x.rel.length)||A[0]; AS.openDrawer(a.i); const d=document.getElementById('as-drawer').innerHTML;
  r.drawer=(d.match(/<text class="as-cl"[^>]*>([^<]*)<\\/text>/g)||[]).map(s=>s.replace(/<[^>]*>/g,'').replace(/&amp;/g,'&')); r.rel=a.rel.map(x=>x[1]); AS.closeDrawer();
  // the placement rule: never two printed labels on top of each other, the higher priority kept
  const fit=AS._.fitLabels, L=[]; for(let i=0;i<60;i++) L.push({x:(i*37)%300,y:(i*53)%120,t:'label '+i,p:i%7,a:['start','end','middle'][i%3]});
  const got=fit(L,320,130), tw=AS._.TW, box=l=>{ const fs=l.fs||10.5, w=tw(l.t,fs)+3, h=fs+3, x0=l.a==='end'?l.x-w:(l.a==='middle'?l.x-w/2:l.x); return {x:x0,y:l.y-h/2,w,h}; };
  r.fitN=got.length; r.overlap=got.some((p,i)=>got.some((q,j)=>j>i&&(()=>{ const a=box(p), b=box(q); return a.x<b.x+b.w&&b.x<a.x+a.w&&a.y<b.y+b.h&&b.y<a.y+a.h; })()));
  r.inside=got.every(l=>{ const b=box(l); return b.x>=-.5&&b.y>=-.5&&b.x+b.w<=320.5&&b.y+b.h<=130.5; });
  const two=fit([{x:10,y:50,t:'low',p:5},{x:10,y:52,t:'high',p:1}],200,100); r.prio=two.map(l=>l.t);
  return JSON.stringify(r); })()`);

// ── the rest of the page: unaffected ──────────────────────────────────────────────────────────────────────────────
get('others', `(()=>{ const r={}; ${RESET}
  const ptr=DATA.active.studio, snap=()=>{ APP=''; const u=uniScreen(), v=valScreen(); return {u,v}; };
  const on=snap(); delete DATA.active.studio; const off=snap(); DATA.active.studio=ptr;
  r.uninstall_same=on.u===off.u; r.value_same=on.v===off.v;
  delete DATA.active.studio; const old=actScreen(); DATA.active.studio=ptr;
  r.old_view={studio:old.indexOf('as-root')>=0||old.indexOf('act-old')>=0, sum:old.indexOf('id="act-sum"')>=0, table:old.indexOf('id="act-table"')>=0, note:old.indexOf('Studio load nahi hua')>=0};
  r.old_is_portfolio=old===actPortfolio();
  const st=actScreen(); __flush(); r.studio_view={root:st.indexOf('id="as-root"')>=0, fold:st.indexOf('id="act-old"')>=0,
    folded:['act-sum','act-chg','act-upd-link','act-table'].map(id=>{ const i=st.indexOf('id="'+id+'"'); return i>st.indexOf('id="act-old"'); }),
    splitBlocks:(st.slice(st.indexOf('id="act-old"')).match(/act-sum/g)||[]).length>0};
  return JSON.stringify(r); })()`);
get('loading', `(()=>{ ${RESET} AS._.load(null); const h=actScreen(); AS._.fail(); const f=actScreen(); AS._.load(__STUDIO); const h2=actScreen(); __flush();
  return JSON.stringify({wait:h.indexOf('Active users Studio load ho raha hai')>=0&&h.indexOf('id="act-old"')>=0&&h.indexOf('as-root')<0,
    failed:f.indexOf('Active users Studio load nahi hua')>=0&&f.indexOf('Try again')>=0&&f.indexOf('as-root')<0&&f.indexOf('id="act-old"')<0,
    back:h2.indexOf('id="as-root"')>=0}); })()`);
out.n = Object.keys(out).length;
process.stdout.write(JSON.stringify({ errors, out }));
