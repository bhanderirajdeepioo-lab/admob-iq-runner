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
  r.apppage_same=p1===p2; if(!r.apppage_same){ let i=0; while(p1[i]===p2[i]) i++; r.apppage_diff=[p1.slice(i-60,i+60),p2.slice(i-60,i+60)]; } r.apppage_no_studio=p1.indexOf('id="us-root"')<0; APP=''; UNIAPP='';
  delete DATA.uninstall.studio; const old=uniScreen(); DATA.uninstall.studio=ptr;
  r.old_view={kw:old.indexOf('uni-kw-bar')>=0, studio:old.indexOf('us-root')>=0||old.indexOf('uni-old')>=0, table:old.indexOf('uni-table')>=0};
  const st=uniScreen(); r.studio_view={root:st.indexOf('id="us-root"')>=0, kw:st.indexOf('uni-kw-bar')>=0, fold:st.indexOf('id="uni-old"')>=0,
    folded:['uni-updates','uni-anyall','uni-table','uni-alerts'].map(id=>{ const i=st.indexOf('id="'+id+'"'); return i>st.indexOf('id="uni-old"'); })};
  return JSON.stringify(r); })()`);
get('loading', `(()=>{ ${RESET} US._.load(null); const h=uniScreen(); US._.load(__STUDIO); const h2=uniScreen();
  return JSON.stringify({wait:h.indexOf('Uninstall Studio load ho raha hai')>=0&&h.indexOf('id="uni-old"')>=0&&h.indexOf('us-root')<0, back:h2.indexOf('id="us-root"')>=0}); })()`);
out.n = Object.keys(out).length;
process.stdout.write(JSON.stringify({ errors, out }));
