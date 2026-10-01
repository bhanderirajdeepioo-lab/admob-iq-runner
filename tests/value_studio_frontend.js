// 💸 Install value Studio — the page side, rendered for real: runs the dashboard script (frontend/index.html's largest
// <script>) in a node vm with stub browser globals and a small DOM (every "vs-…" id is a real element holding its
// innerHTML), on a synthetic Studio file the REAL build code made (tests/test_value_studio_frontend.py:
// tests/value_studio_synth.py + the build step), and prints ONE JSON report; the Python test asserts on it.
//   usage: node value_studio_frontend.js <script.js> <dir with dashboard.json + value_studio.json>
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const [scriptPath, dir] = process.argv.slice(2);
const J = n => JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8'));
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// ── a small DOM: "vs-…" ids are real (innerHTML kept), everything else is the inert stub ──
const classList = () => { const s = new Set(); return { add: (...a) => a.forEach(x => s.add(x)), remove: (...a) => a.forEach(x => s.delete(x)),
  toggle: (x, f) => { const on = f === undefined ? !s.has(x) : !!f; on ? s.add(x) : s.delete(x); return on; }, contains: x => s.has(x), _s: s }; };
function mk(id) { const e = { id, _html: '', attrs: {}, classList: classList(), style: { setProperty() {} }, dataset: {}, hidden: false, open: false,
  scrollTop: 0, scrollLeft: 0, scrollWidth: 0, clientWidth: 1000, offsetParent: {}, value: '',
  get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return this.attrs[k] == null ? null : this.attrs[k]; },
  querySelector: () => mk('_q'), querySelectorAll: () => [], addEventListener() {}, removeEventListener() {}, appendChild() {},
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 20, right: 100, bottom: 20 }), focus() {}, scrollIntoView() {}, closest: () => null };
  return e; }
const ELS = {};
const body = mk('body');
const document = new Proxy({
  getElementById: id => (/^vs-/.test(String(id)) ? (ELS[id] = ELS[id] || mk(id)) : any),
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
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
ctx.__DASH = J('dashboard.json'); ctx.__STUDIO = J('value_studio.json');
const out = {};
function get(name, code) { try { out[name] = run(code); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); } }
const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; VALAPP=''; CURVIEW='USD'; VALJUMP='';`;
run(`DATA=__DASH; ${RESET} VS._.load(__STUDIO);`);
const text = h => String(h).replace(/<style[\s\S]*?<\/style>/g, '').replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
ctx.__text = text;
const STUDIO_ONLY = h => { const a = h.indexOf('id="vs-root"'), b = h.indexOf('id="val-old'); return h.slice(a < 0 ? 0 : a, b < 0 ? h.length : b); };
ctx.__studio = STUDIO_ONLY;

// ── the screen and the numbers ────────────────────────────────────────────────────────────────────────────────────
get('screen7', `(()=>{ ${RESET} return valScreen(); })()`);
const ROWS = `JSON.stringify({W:VS._.W(), M:{SW:VS._.M().SW,nw:VS._.M().nw,H:VS._.M().H},
  rows:VS._.R().map(o=>({id:o.a.id,nm:o.a.nm,pill:o.pill,todo:o.todo.v,profD:o.s.profD,marg:o.s.marg,jw:o.s.jw,ads:o.s.ads,thin:o.s.thin,never:!!(o.s.pb&&o.s.pb.never),cprofD:o.c.profD})),
  PT:{profD:VS._.PT().profD,nJ:VS._.PT().nJ}})`;
get('rows7', `(()=>{ ${RESET} valScreen(); return ${ROWS}; })()`);
get('rows30', `(()=>{ ${RESET} KWIN='30'; valScreen(); return ${ROWS}; })()`);
get('rows30m', `(()=>{ ${RESET} KWIN='30'; KCMP='month'; valScreen(); return ${ROWS}; })()`);

// ── the shared KPIWINDOW / compare / currency ───────────────────────────────────────────────────────────────────────
get('kwin', `(()=>{ ${RESET} const r={};
  r.weeks={}; for(const k of ['7','14','30','60']){ KWIN=k; valScreen(); r.weeks[k]=VS._.W().L; }
  KWIN='30'; const h30=valScreen(); r.win30=/\\(4 weeks\\)/.test(h30)&&/data-r="30" aria-pressed="true"/.test(h30);
  VS._.setRange('14'); r.after14={KWIN, L:VS._.W().L, saved:JSON.parse(localStorage.getItem('kwin_v1')).win};
  VS._.setRange('c'); r.custom={KWIN, from:KWCUSTOM.from, to:KWCUSTOM.to, L:VS._.W().L};
  VS._.setDate('vs-cf1', VS._.wS(VS._.W().i1-5)); r.dates={KWIN, L:VS._.W().L};
  VS._.setCmp('month'); const W=VS._.W(); r.month={KCMP, saved:JSON.parse(localStorage.getItem('kwin_v1')).cmp, gap:W.i0-W.c0, overlap:W.c1>=W.i0};
  VS._.setCmp('prev'); VS._.setRange('30'); const W2=VS._.W(); r.prev={L:W2.L, cL:W2.cL, adj:W2.c1===W2.i0-1};
  VS._.setDate('vs-cf2', VS._.wS(VS._.W().i0-10)); VS._.setDate('vs-ct2', VS._.wE(VS._.W().i0-9)); r.cdates={KCMP, cL:VS._.W().cL};
  ${RESET} CURVIEW='INR'; valScreen(); r.inr=VS._.mT(1000); r.inrTiny=VS._.mL(0.05); r.inrP=VS._.mP(2.5);
  CURVIEW='USD'; valScreen(); r.usd=VS._.mT(1000); r.usdTiny=VS._.mL(0.05); r.usdP=VS._.mP(0.042);
  r.fx=DATA.usd_inr; ${RESET} return JSON.stringify(r); })()`);
get('header', `(()=>{ ${RESET} KWIN='60'; KCMP='month'; CURVIEW='INR'; const h=valScreen(); ${RESET} return JSON.stringify({p60:/data-r="60" aria-pressed="true"/.test(h), month:/<option value="month" selected>/.test(h), inr:/data-c="INR" aria-pressed="true"/.test(h)}); })()`);

// ── the drawer → the full app page; a refresh keeps the drawer; the app page closes it ───────────────────────────────
get('drawer', `(()=>{ ${RESET} valScreen(); const A=VS._.A(), r={}; const calls=[]; const keep=valOpen; valOpen=function(id){ calls.push(id); };
  const i=A.findIndex(a=>a.sz==='badi'); VS.openDrawer(i); const h=document.getElementById('vs-drawer').innerHTML; r.open=VS._.ST.drawer===i; r.full=(h.match(/Full app page →/g)||[]).length;
  r.dataFull=(h.match(/data-full="([^"]+)"/)||[])[1]===A[i].id; r.lock=document.body.classList.contains('vs-lock');
  r.labels=(h.match(/<text class="vs-cl"[^>]*>[^<]+</g)||[]).map(x=>x.replace(/<[^>]*>/g,'').replace(/<$/,''));
  valScreen(); r.afterRefresh=VS._.ST.drawer===i&&VS._.ST.did===A[i].id;
  VS._.fullPage(A[i].id); r.calls=calls; r.closed=VS._.ST.drawer===-1&&!document.body.classList.contains('vs-lock');
  valOpen=keep; return JSON.stringify(r); })()`);
get('page', `(()=>{ ${RESET} valScreen(); const A=VS._.A(), a=A.find(x=>x.sz==='badi'), row=valRows().find(x=>x.app_id===a.id), r={};
  VS.openDrawer(a.i); APP=row.app; VALAPP=row.app_id; const h=valScreen(); r.closedDrawer=VS._.ST.drawer===-1; r.mode=VS._.MODE();
  r.root=h.indexOf('id="vs-root"')>=0; r.pg=h.indexOf('id="vs-pgbody"')>=0; r.fold=h.indexOf('id="val-oldapp"')>=0;
  r.foldAfter=h.indexOf('id="val-oldapp"')>h.indexOf('id="vs-pgbody"'); r.back=/data-back="1"/.test(h);
  const old=valAppOld(row); r.oldInside=h.indexOf(old)>h.indexOf('id="val-oldapp"');
  r.sections=['Money back — how many days','Each install week','Week by week','Countries'].every(t=>h.indexOf(t)>=0);
  r.labels=(h.match(/<text class="vs-cl"[^>]*>[^<]+</g)||[]).map(x=>x.replace(/<[^>]*>/g,'').replace(/<$/,''));
  KWIN='60'; const h60=valScreen(); r.range60=VS._.W().L===8&&/data-r="60" aria-pressed="true"/.test(h60);
  const ptr=DATA.value.studio; delete DATA.value.studio; r.noPtrSame=valScreen()===valAppOld(row); DATA.value.studio=ptr;
  const nog=(DATA.value.no_ga4||[])[0]; if(nog){ APP=nog.app; VALAPP=''; const hn=valScreen(); r.nogaOld=hn.indexOf('vs-root')<0; }
  APP=''; VALAPP=''; return JSON.stringify(r); })()`);

// ── what's new: every engine alert with the owner's timestamp line; the Studio's own items say they are not alerts ────
get('chg', `(()=>{ ${RESET} valScreen(); return VS._.chg(); })()`);
get('alerts', `JSON.stringify(VS._.ALS().map(z=>({id:z.x.id,app:z.x.app_id,closed:!!z.closed})))`);
get('chgTable', `(()=>{ ${RESET} valScreen(); VS._.ST.chgView='table'; const t=VS._.chg(); VS._.ST.chgView='cards'; return t; })()`);

// ── the printed numbers on the charts ──────────────────────────────────────────────────────────────────────────────
get('labels', `(()=>{ ${RESET} KWIN='30'; valScreen(); const k=VS._.kpis(), tl=VS._.tl(), m=VS._.map();
  const L=h=>(h.match(/<span class="vs-sl[^"]*" data-p="\\d"[^>]*>(?:<i><\\/i>)?[^<]+</g)||[]).map(x=>x.replace(/<[^>]*>/g,'').replace(/<$/,''));
  return JSON.stringify({kpi:L(k), map:L(m).length, tl:(tl.match(/<text class="vs-cl"[^>]*>[^<]+</g)||[]).map(x=>x.replace(/<[^>]*>/g,'').replace(/<$/,'')), PT:VS._.PT().profD}); })()`);

// ── every word the Studio shows (all ranges, both currencies, the tables, every drawer, every app page, every tooltip) ──
get('texts', `(()=>{ const T=[]; for(const k of ['7','14','30','60']) for(const c of ['USD','INR']){ ${RESET} KWIN=k; CURVIEW=c; T.push(__text(__studio(valScreen()))); }
  ${RESET} valScreen(); VS._.ST.chgView='table'; T.push(__text(VS._.chg())); VS._.ST.chgView='cards';
  VS._.ST.open=new Set(VS._.A().map(a=>a.i)); T.push(__text(VS._.tbl())); VS._.ST.open=new Set();
  VS._.A().forEach((a,i)=>{ VS.openDrawer(i); T.push(__text(document.getElementById('vs-drawer').innerHTML)); }); VS.closeDrawer();
  valRows().filter(r=>VS._.A().some(a=>a.id===r.app_id)).forEach(r=>{ APP=r.app; VALAPP=r.app_id; T.push(__text(__studio(valScreen()))); }); APP=''; VALAPP=''; valScreen();
  const TP=VS._.TIPS, A=VS._.A();
  A.forEach((a,i)=>{ ['app','prof'].forEach(k=>T.push(__text(TP[k](i)))); ['cpi','b7','v90','pb'].forEach(k=>T.push(__text(TP.cell(i,k)))); T.push(__text(TP.ptl()));
    for(let w=0;w<VS._.M().nw;w+=5) T.push(__text(TP.dwk(i,w))); a.rel.forEach(r=>T.push(__text(TP.drel(i,r[0])))); (a.cty&&a.cty.rows||[]).forEach(x=>T.push(__text(TP.crow(i,x.cc)))); });
  VS._.CT().forEach(g=>T.push(__text(TP.cty(g.cc))));
  return JSON.stringify(T); })()`);

// ── the rest of the page: unaffected ──────────────────────────────────────────────────────────────────────────────
get('others', `(()=>{ const r={}; ${RESET}
  const ptr=DATA.value.studio, snap=()=>{ APP=''; let u='', a=''; try{ u=uniScreen(); }catch(e){ u='ERR'; } try{ a=actScreen(); }catch(e){ a='ERR'; } return {u,a}; };
  const on=snap(); delete DATA.value.studio; const off=snap(); DATA.value.studio=ptr;
  r.uninstall_same=on.u===off.u; r.active_same=on.a===off.a;
  delete DATA.value.studio; const old=valScreen(); r.old_is_portfolio=old===valPortfolio(); DATA.value.studio=ptr;
  r.old_view={studio:old.indexOf('vs-root')>=0||old.indexOf('val-old')>=0, kw:old.indexOf('val-kw-bar')>=0, table:old.indexOf('val-table')>=0};
  const st=valScreen(); r.studio_view={root:st.indexOf('id="vs-root"')>=0, kw:st.indexOf('val-kw-bar')>=0, fold:st.indexOf('id="val-old"')>=0,
    folded:['val-paytop','val-chg','val-table','val-ctyall','val-timing'].map(id=>{ const i=st.indexOf('id="'+id+'"'); return i>st.indexOf('id="val-old"'); }),
    pend:st.indexOf('Install-wise kamai ka data aa raha')>=0};
  return JSON.stringify(r); })()`);
get('states', `(()=>{ ${RESET} const r={};
  VS._.load(null); const h=valScreen(); r.wait=h.indexOf('Value Studio load ho raha hai')>=0&&h.indexOf('id="val-old"')>=0&&h.indexOf('vs-root')<0;
  VS._.load(__STUDIO); r.back=valScreen().indexOf('id="vs-root"')>=0;
  VS._.fail(); const f=valScreen(); r.failed=f.indexOf('vs-root')<0&&f.indexOf('Value Studio load nahi hua')>=0&&f.indexOf('VS.retry()')>=0;
  r.failedRest=f.replace(/<div class="note">⚠️ Value Studio load nahi hua[\\s\\S]*?<\\/div>/,'')===(()=>{ const p=DATA.value.studio; delete DATA.value.studio; const o=valScreen(); DATA.value.studio=p; return o; })();
  VS._.load(__STUDIO);
  const id='ca-app-pub-0000000000000000~999'; DATA.apps_catalog.push({app_id:id,app_name:'Demo Pending',account_id:'pub-0000000000000000',selected:true});
  DATA.value.apps.push({app_id:id,app:'Demo Pending',key:'000000000999',status:'wait'}); SMPAPPS=null;
  const hp=valScreen(); r.pend=VS._.PEND().length===1&&VS._.tbl().indexOf('Demo Pending')>=0;
  DATA.value.apps.pop(); DATA.apps_catalog.pop(); SMPAPPS=null; VS._.load(__STUDIO); valScreen();
  return JSON.stringify(r); })()`);
out.n = Object.keys(out).length;
process.stdout.write(JSON.stringify({ errors, out }));
