// 🧭 Uninstall Studio — the page side, rendered for real: runs the dashboard script (frontend/index.html's largest <script>)
// in a node vm with stub browser globals and a small DOM (every "us-…" id is a real element holding its innerHTML), on a
// synthetic Studio file the REAL build code made (tests/test_uninstall_studio_frontend.py: tests/studio_synth.py + the
// build step), and prints ONE JSON report; the Python test asserts on it.
//   usage: node studio_frontend.js <script.js> <dir with dashboard.json + uninstall_studio.json + uninstall.json>
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const [scriptPath, dir] = process.argv.slice(2);
const J = n => JSON.parse(fs.readFileSync(path.join(dir, n), 'utf8'));
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// ── a small DOM: "us-…" ids are real (innerHTML kept), everything else is the inert stub ──
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
  getElementById: id => (/^us-/.test(String(id)) ? (ELS[id] = ELS[id] || mk(id)) : any),
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
ctx.__DASH = J('dashboard.json'); ctx.__STUDIO = J('uninstall_studio.json'); ctx.__UNI = J('uninstall.json');
const out = {};
function get(name, code) { try { out[name] = run(code); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); } }
const RESET = `KWIN='7'; KWCUSTOM={from:'',to:''}; KWERR=''; KCMP='prev'; KCMPCUSTOM={from:'',to:''}; KCMPERR=''; APP=''; UNIAPP=''; CURVIEW='USD';`;
run(`DATA=__DASH; UNI=__UNI; UNIERR=false; UNICOH={}; ${RESET} US._.load(__STUDIO);`);
const text = h => String(h).replace(/<style[\s\S]*?<\/style>/g, '').replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
ctx.__text = text;

// ── the screen, its order and the consistency rules ─────────────────────────────────────────────────────────────────
get('screen7', `(()=>{ ${RESET} return uniScreen(); })()`);
get('order7', `(()=>{ const R=US._.R(), A=US._.A();
  const first=(h,re)=>{ const m=re.exec(h); return m?+m[1]:null; };
  const map=US._.map(), story=US._.story(), tbl=US._.tbl(), src=US._.src();
  return JSON.stringify({
    names: A.map(a=>a.nm),
    map1: first(map.slice(map.indexOf('class="us-rk"')), /data-go="(\\d+)"/),
    fire: /🔥/.test(story)?first(story,/<button class="us-sc us-bad" data-app="(\\d+)"/):null,
    tbl1: first(tbl.slice(tbl.indexOf('<tbody')), /<tr data-app="(\\d+)"/),
    src1: first(src, /class="us-dvr[^"]*" data-app="(\\d+)"/),
    rank1: (R.find(o=>o.rank===1)||{a:{}}).a.i,
    rows: R.map(o=>({i:o.a.i,nm:o.a.nm,pill:o.pill,rank:o.rank,usd:o.usd,sig:o.sig,L:o.L.tot==null?{why:o.L.why}:{a:o.L.a,b:o.L.b,tot:o.L.tot,exp:o.L.exp,z:o.L.z,sig:o.L.sig,part:o.L.part,days:o.L.days},
      cells:[o.hd0.s,o.hr.s,o.hs7.s,o.hr1.s],ins:o.s.ins,outs:o.s.outs,rate:o.s.rate,arp:o.s.arp,d0:o.d0.p,s7:o.s7.p,r1:o.r1.p})),
    W: US._.W(), PT: (p=>({ins:p.ins,outs:p.outs,net:p.net,rate:p.rate,Ltot:p.Ltot,La:p.La,Lb:p.Lb,Lusd:p.Lusd}))(US._.PT()) }); })()`);
get('rows30', `(()=>{ ${RESET} KWIN='30'; uniScreen(); return JSON.stringify({W:US._.W(), rows:US._.R().map(o=>({i:o.a.i,pill:o.pill,rank:o.rank,L:o.L.tot==null?{why:o.L.why}:{a:o.L.a,b:o.L.b,tot:o.L.tot,exp:o.L.exp,z:o.L.z,sig:o.L.sig,part:o.L.part,days:o.L.days},cells:[o.hd0.s,o.hr.s,o.hs7.s,o.hr1.s]}))}); })()`);

// ── the shared KPIWINDOW / compare / currency ───────────────────────────────────────────────────────────────────────
get('kwin', `(()=>{ ${RESET} const r={};
  KWIN='30'; const h30=uniScreen(); r.ext30=US._.W().L; r.win30=/\\(30 din\\)/.test(h30);
  US._.setRange('14'); r.after14={KWIN, L:US._.W().L, saved:JSON.parse(localStorage.getItem('kwin_v1')).win, other:kwWin('2026-01-01','2026-09-19').days};
  US._.setRange('c'); r.custom={KWIN, from:KWCUSTOM.from, to:KWCUSTOM.to, L:US._.W().L};
  US._.setCmp('month'); r.month={KCMP, saved:JSON.parse(localStorage.getItem('kwin_v1')).cmp, W:US._.W()};
  US._.setDate('us-ct1', US._.M().E); US._.setDate('us-cf1', US._.dOf(US._.ix(US._.M().E)-9)); r.dates={KWIN, L:US._.W().L, from:KWCUSTOM.from, to:KWCUSTOM.to};
  US._.setDate('us-cf2', US._.M().E); US._.setDate('us-ct2', US._.dOf(US._.ix(US._.M().E)-30)); r.cdates={KCMP, from:KCMPCUSTOM.from, to:KCMPCUSTOM.to};
  ${RESET} CURVIEW='INR'; r.inr=US._.money(10); r.inrTiny=US._.moneyL(0.05); CURVIEW='USD'; r.usd=US._.money(10); r.usdTiny=US._.moneyL(0.05);
  r.fx=DATA.usd_inr; ${RESET} return JSON.stringify(r); })()`);
// the header's own controls are rendered from the shared state
get('header', `(()=>{ ${RESET} KWIN='60'; KCMP='month'; const h=uniScreen(); ${RESET} return JSON.stringify({p60:/data-r="60" aria-pressed="true"/.test(h), month:/<option value="month" selected>/.test(h), inr:/data-c="USD" aria-pressed="true"/.test(h)}); })()`);

// ── the drawer → the app's full page; a refresh keeps it; another view closes it ───────────────────────────────────
get('drawer', `(()=>{ ${RESET} uniScreen(); const A=US._.A(), r={}; const calls=[]; const keep=uniOpen; uniOpen=function(id){ calls.push(id); };
  US.openDrawer(0); const h=document.getElementById('us-drawer').innerHTML; r.open=US._.ST.drawer===0; r.full=(h.match(/Poora app page →/g)||[]).length;
  r.dataFull=(h.match(/data-full="([^"]+)"/)||[])[1]===A[0].id; r.lock=document.body.classList.contains('us-lock');
  uniScreen(); r.afterRefresh=US._.ST.drawer===0&&US._.ST.did===A[0].id;          // the 5-minute refresh re-renders the screen
  US._.fullPage(A[0].id); r.calls=calls; r.closed=US._.ST.drawer===-1&&!document.body.classList.contains('us-lock');
  uniOpen=keep;
  US.openDrawer(1); APP='x'; renderUninstall(); r.closedOnAppPage=US._.ST.drawer===-1; APP='';
  return JSON.stringify(r); })()`);

// ── every word the Studio shows (all ranges, the alert table, every drawer, every tooltip) ──────────────────────────
// (the Studio's own words: the older views folded under it are the tab's earlier screens, kept as they were)
const STUDIO_ONLY = h => { const a = h.indexOf('id="us-root"'), b = h.indexOf('id="uni-old"'); return h.slice(a < 0 ? 0 : a, b < 0 ? h.length : b); };
ctx.__studio = STUDIO_ONLY;
get('texts', `(()=>{ const T=[]; for(const k of ['7','14','30','60']){ ${RESET} KWIN=k; T.push(__text(__studio(uniScreen()))); }
  ${RESET} uniScreen(); US._.ST.chgView='table'; T.push(__text(US._.chg())); US._.ST.chgView='cards';
  US._.A().forEach((a,i)=>{ US.openDrawer(i); T.push(__text(document.getElementById('us-drawer').innerHTML)); US._.ST.cohMode='dev'; T.push(__text(US._.drawer())); US._.ST.cohMode='abs'; });
  US.closeDrawer();
  const TP=US._.TIPS, A=US._.A(); A.forEach((a,i)=>{ ['app','inr'].forEach(k=>T.push(__text(TP[k](i)))); ['d0','rate','s7','r1'].forEach(k=>T.push(__text(TP.cell(i,k))));
    a.coh.w.forEach(w=>T.push(__text(TP.coh(i,w.w,3)))); a.rel.forEach(r=>T.push(__text(TP.upd(i,r[0])))); });
  US._.ALERTS().forEach(x=>T.push(__text(TP.al(x.k)))); T.push(__text(TP.ptl()));
  CURVIEW='INR'; T.push(__text(__studio(uniScreen()))); CURVIEW='USD';
  return JSON.stringify(T); })()`);
get('alerts', `JSON.stringify(US._.ALERTS().map(x=>({k:x.k,a:x.a,sev:x.sev,closed:!!x.closed,at:x.at})))`);
get('chg', `(()=>{ ${RESET} uniScreen(); return US._.chg(); })()`);

// ── the rest of the page: unaffected ──────────────────────────────────────────────────────────────────────────────
get('others', `(()=>{ const r={}; ${RESET}
  const ptr=DATA.uninstall.studio, snap=()=>{ APP=''; const a=actScreen(), v=valScreen(); return {a,v}; };
  const on=snap(); delete DATA.uninstall.studio; const off=snap(); DATA.uninstall.studio=ptr;
  r.active_same=on.a===off.a; r.value_same=on.v===off.v;
  const nm=DATA.uninstall.apps[0].app; APP=nm; UNIAPP=DATA.uninstall.apps[0].app_id; const nz=h=>h.replace(/(id="|url\\(#|href="#)([A-Za-z_-]*?)\\d+/g,'$1$2#');   // (the page's own chart-id counters)
  const p1=nz(uniScreen()); delete DATA.uninstall.studio; const p2=nz(uniScreen()); DATA.uninstall.studio=ptr;
  // one app: the Studio app page, and the WHOLE older app page (as it is without the Studio) folded under it
  r.apppage_old_kept=p1.indexOf('<div class="uo-in">'+p2+'</div>')>=0; r.apppage_studio=p1.indexOf('id="us-root" class="us-app-pg"')>=0&&p1.indexOf('id="uni-old-app"')>p1.indexOf('id="us-apg"'); r.apppage_old_alone=p2.indexOf('us-root')<0; APP=''; UNIAPP='';
  delete DATA.uninstall.studio; const old=uniScreen(); DATA.uninstall.studio=ptr;
  r.old_view={kw:old.indexOf('uni-kw-bar')>=0, studio:old.indexOf('us-root')>=0||old.indexOf('uni-old')>=0, table:old.indexOf('uni-table')>=0};
  const st=uniScreen(); r.studio_view={root:st.indexOf('id="us-root"')>=0, kw:st.indexOf('uni-kw-bar')>=0, fold:st.indexOf('id="uni-old"')>=0,
    folded:['uni-updates','uni-anyall','uni-table','uni-alerts'].map(id=>{ const i=st.indexOf('id="'+id+'"'); return i>st.indexOf('id="uni-old"'); })};
  return JSON.stringify(r); })()`);
get('loading', `(()=>{ ${RESET} US._.load(null); const h=uniScreen(); US._.load(__STUDIO); const h2=uniScreen();
  return JSON.stringify({wait:h.indexOf('Uninstall Studio load ho raha hai')>=0&&h.indexOf('id="uni-old"')>=0&&h.indexOf('us-root')<0, back:h2.indexOf('id="us-root"')>=0}); })()`);

// ── the full app page (one app on the Uninstall tab) ────────────────────────────────────────────────────────────────
get('page', `(()=>{ ${RESET} const r={}, row=DATA.uninstall.apps.find(x=>US._.A().some(a=>a.id===x.app_id)), id=row.app_id; APP=row.app; UNIAPP=id;
  const ptr=DATA.uninstall.studio, nz=h=>h.replace(/(id="|url\\(#|href="#)([A-Za-z_-]*?)\\d+/g,'$1$2#');
  const h=uniScreen(); r.view=US._.view(); r.id=id;
  r.root=h.indexOf('id="us-root" class="us-app-pg"')>=0; r.apg=h.indexOf('id="us-apg"')>=0; r.back=/data-back="1"[^>]*>← All apps/.test(h);
  r.nav=(h.match(/data-pnav="(-1|1)"/g)||[]).length; r.top=/id="us-rng"/.test(h); r.kwbar=h.indexOf('uni-kw-bar')>h.indexOf('id="uni-old-app"');
  delete DATA.uninstall.studio; const old=uniScreen(); DATA.uninstall.studio=ptr;
  r.fold=nz(h).indexOf('<div class="uo-in">'+nz(old)+'</div>')>=0; r.oldNoStudio=old.indexOf('us-root')<0;
  const pg=h.slice(h.indexOf('id="us-apg"'),h.indexOf('id="uni-old-app"'));
  r.kpis=(pg.match(/class="us-kpi"/g)||[]).length; r.charts=(pg.match(/<svg viewBox="[^"]*" id="us-s\\d+" data-hv="1"/g)||[]).length;
  r.coh=pg.indexOf('class="us-coh"')>=0; r.daytable=pg.indexOf('Din-ba-din')>=0; r.cards=(pg.match(/class="us-ac /g)||[]).length; r.alerts=US._.A().find(a=>a.id===id).al.length;
  r.ts=(pg.match(/🕒 Alert aaya: /g)||[]).length; r.labels=(pg.match(/<text class="us-lbl"/g)||[]).map?((pg.match(/<text class="us-lbl"[^>]*>[^<]*/g)||[]).map(t=>t.replace(/^.*>/,''))):[];
  r.text=__text(pg);
  // the same numbers as the drawer: the KPI tiles of both read one computation
  const i=US._.A().findIndex(a=>a.id===id); US.openDrawer(i); const dh=document.getElementById('us-drawer').innerHTML; US.closeDrawer();
  const kt=x=>__text((x.match(/<div class="us-dk[^"]*">[\\s\\S]*?<\\/div><\\/div><\\/div><div class="us-panel">/)||[''])[0]);
  r.sameKpis=kt(dh)!==''&&kt(dh)===kt(pg);
  // the shared range drives the page too
  US._.setRange('7'); r.after7=US._.W().L; r.html7=__text(document.getElementById('us-apg').innerHTML).indexOf('Din-ba-din')>=0;
  // the Studio's file still loading: a short wait, the older page folded under it
  US._.load(null); const hl=uniScreen(); US._.load(__STUDIO); r.loading=hl.indexOf('Uninstall Studio load ho raha hai')>=0&&hl.indexOf('id="uni-old-app"')>=0&&hl.indexOf('id="us-root"')<0;
  // an app with no GA4 data: its older page as before
  APP='Demo Clock'; UNIAPP=''; const nh=uniScreen(); r.noGa4=nh.indexOf('us-root')<0;
  ${RESET} return JSON.stringify(r); })()`);
get('pageWords', `(()=>{ ${RESET} const T=[]; US._.A().forEach(a=>{ const row=DATA.uninstall.apps.find(x=>x.app_id===a.id); if(!row) return; APP=row.app; UNIAPP=a.id; for(const k of ['7','30','60']){ KWIN=k; const h=uniScreen(); T.push(__text(h.slice(h.indexOf('id="us-root"'),h.indexOf('id="uni-old-app"')))); } }); ${RESET} return JSON.stringify(T); })()`);

// ── every chart: one hover path (registered, no own listener), its numbers printed on it, labels never overlapping ──
get('charts', `(()=>{ ${RESET} const r={}, A=US._.A(); const ids=[];
  const scan=h=>{ (h.match(/<svg[^>]* id="(us-[sd]\\d+)"[^>]*data-hv="1"|<svg[^>]*data-hv="1"[^>]* id="(us-[sd]\\d+)"/g)||[]).forEach(t=>{ const m=t.match(/id="(us-[sd]\\d+)"/); ids.push(m[1]); }); };
  const h=uniScreen(); scan(h); const i=A.findIndex(a=>a.rel.length); US.openDrawer(i<0?0:i); const dh=document.getElementById('us-drawer').innerHTML; scan(dh);
  const SPK=US._.SPK(); r.n=ids.length; r.registered=ids.every(id=>SPK[id]&&typeof SPK[id].tip==='function'&&SPK[id].n>0);
  r.tips=ids.every(id=>{ const S=SPK[id]; const a=S.tip(0), b=S.tip(S.n-1); return typeof a==='string'&&a.length>10&&typeof b==='string'&&b.length>10; });
  r.oldHit=dh.indexOf('us-bigr')<0&&dh.indexOf('us-bigx')<0&&h.indexOf('us-bigr')<0;
  // the drawer's rate chart: its labels — the latest day, the range average, the normal, 📦 versions, 🔔 starts
  const big=(dh.match(/<svg viewBox="0 0 (\\d+) (\\d+)" id="us-d\\d+" data-hv="1" role="img" aria-label="Roz hataaye % chart">[\\s\\S]*?<\\/svg>/)||[])[0]||'';
  const vb=(big.match(/viewBox="0 0 (\\d+) (\\d+)"/)||[]).slice(1).map(Number);
  const L=[...big.matchAll(/<text class="us-lbl" x="([\\d.-]+)" y="([\\d.-]+)" font-size="([\\d.]+)"[^>]*>([^<]*)<\\/text>/g)].map(m=>({x:+m[1],y:+m[2],fs:+m[3],t:m[4]}));
  r.bigLabels=L.map(l=>l.t); r.vb=vb;
  const box=l=>[l.x,l.y-l.fs+1,l.x+String(l.t).replace(/&amp;/g,'&').length*l.fs*.56+3,l.y+3];
  r.inside=L.every(l=>{ const b=box(l); return b[0]>=0&&b[2]<=vb[0]+0.5&&b[1]>=0&&b[3]<=vb[1]; });
  r.overlap=0; for(let p=0;p<L.length;p++) for(let q=p+1;q<L.length;q++){ const a=box(L[p]), b=box(L[q]); if(a[0]<b[2]&&a[2]>b[0]&&a[1]<b[3]&&a[3]>b[1]) r.overlap++; }
  const io=(dh.match(/aria-label="Installs vs uninstalls chart">[\\s\\S]*?<\\/svg>/)||[''])[0]; r.ioLabels=[...io.matchAll(/<text class="us-lbl"[^>]*>([^<]*)<\\/text>/g)].map(m=>m[1]);
  US.closeDrawer();
  const tl=US._.tl(); r.tlLabels=[...tl.matchAll(/<text class="us-lbl"[^>]*>([^<]*)<\\/text>/g)].map(m=>m[1]);
  const kp=US._.kpis(); r.kpiLabels=[...kp.matchAll(/<span class="us-sl[^"]*"[^>]*>([^<]*)<\\/span>/g)].map(m=>m[1]);
  // the helper itself: a crowded set → all inside, none overlapping, the lower priority dropped
  const out=US._.labels([{x:50,y:20,t:'Aaaa 1,000 (1.0%)',a:'start',p:1,dys:[0]},{x:52,y:21,t:'Bbbb 2,000 (2.0%)',a:'start',p:2,dys:[0]},{x:52,y:21,t:'Cccc 3,000 (3.0%)',a:'start',p:3,dys:[0,14]},{x:195,y:20,t:'Dddd 4,000',a:'start',p:4}],[0,0,200,60],[[0,40,200,60]]);
  r.helper=[...out.matchAll(/x="([\\d.]+)" y="([\\d.]+)"[^>]*>([^<]*)</g)].map(m=>[+m[1],+m[2],m[3]]);
  return JSON.stringify(r); })()`);
out.n = Object.keys(out).length;
process.stdout.write(JSON.stringify({ errors, out }));
