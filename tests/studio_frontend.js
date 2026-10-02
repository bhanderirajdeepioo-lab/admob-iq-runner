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
// the older app page (no Studio) as the Studio page's fold holds it: the 📦 Update impact card (exactly uniImpactCard's
// output for that app, ids normalised) replaced by the one line to the Studio page's section
run(`function __upLine(h){ const nz=x=>x.replace(/(id="|url\\(#|href="#)([A-Za-z_-]*?)\\d+/g,'$1$2#');
  const a=((UNI&&UNI.apps)||[]).find(z=>z.app_id===UNIAPP), c=a?nz(uniImpactCard(a)):''; if(!c||h.indexOf(c)<0) return '__no card__';
  return h.replace(c,nz(uniImpUpLine())); }`);

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
  KWIN='30'; const h30=uniScreen(); r.ext30=US._.W().L; r.win30=/\\(30 days\\)/.test(h30);
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
  US.openDrawer(0); const h=document.getElementById('us-drawer').innerHTML; r.open=US._.ST.drawer===0; r.full=(h.match(/Full app page →/g)||[]).length;
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
  // one app: the Studio app page, and the WHOLE older app page (as it is without the Studio) folded under it — but its
  // 📦 Update impact card, which is the Studio page's own section now (owner, 2 Oct), is one line there (drawn once)
  r.apppage_old_kept=p1.indexOf('<div class="uo-in">'+__upLine(p2)+'</div>')>=0; r.apppage_studio=p1.indexOf('id="us-root" class="us-app-pg"')>=0&&p1.indexOf('id="uni-old-app"')>p1.indexOf('id="us-apg"'); r.apppage_old_alone=p2.indexOf('us-root')<0; APP=''; UNIAPP='';
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
  r.fold=nz(h).indexOf('<div class="uo-in">'+__upLine(nz(old))+'</div>')>=0; r.oldNoStudio=old.indexOf('us-root')<0;
  const pg=h.slice(h.indexOf('id="us-apg"'),h.indexOf('id="uni-old-app"'));
  r.kpis=(pg.match(/class="us-kpi"/g)||[]).length; r.charts=(pg.match(/<svg viewBox="[^"]*" id="us-s\\d+" data-hv="1"/g)||[]).length;
  r.coh=pg.indexOf('class="us-coh"')>=0; r.daytable=pg.indexOf('Day by day')>=0; r.cards=(pg.match(/class="us-ac /g)||[]).length; r.alerts=US._.A().find(a=>a.id===id).al.length;
  r.ts=(pg.match(/🕒 Alert time: /g)||[]).length; r.labels=(pg.match(/<text class="us-lbl"/g)||[]).map?((pg.match(/<text class="us-lbl"[^>]*>[^<]*/g)||[]).map(t=>t.replace(/^.*>/,''))):[];
  r.text=__text(pg);
  // the same numbers as the drawer: the KPI tiles of both read one computation
  const i=US._.A().findIndex(a=>a.id===id); US.openDrawer(i); const dh=document.getElementById('us-drawer').innerHTML; US.closeDrawer();
  const kt=x=>__text((x.match(/<div class="us-dk[^"]*">[\\s\\S]*?<\\/div><\\/div><\\/div><div class="us-panel">/)||[''])[0]);
  r.sameKpis=kt(dh)!==''&&kt(dh)===kt(pg);
  // the shared range drives the page too
  US._.setRange('7'); r.after7=US._.W().L; r.html7=__text(document.getElementById('us-apg').innerHTML).indexOf('Day by day')>=0;
  // the Studio's file still loading: a short wait, the older page folded under it
  US._.load(null); const hl=uniScreen(); US._.load(__STUDIO); r.loading=hl.indexOf('Uninstall Studio load ho raha hai')>=0&&hl.indexOf('id="uni-old-app"')>=0&&hl.indexOf('id="us-root"')<0;
  // an app with no GA4 data: its older page as before
  APP='Demo Clock'; UNIAPP=''; const nh=uniScreen(); r.noGa4=nh.indexOf('us-root')<0;
  ${RESET} return JSON.stringify(r); })()`);
get('pageWords', `(()=>{ ${RESET} const T=[]; US._.A().forEach(a=>{ const row=DATA.uninstall.apps.find(x=>x.app_id===a.id); if(!row) return; APP=row.app; UNIAPP=a.id; for(const k of ['7','30','60']){ KWIN=k; const h=uniScreen(); T.push(__text(h.slice(h.indexOf('id="us-root"'),h.indexOf('id="uni-old-app"')))); } }); ${RESET} return JSON.stringify(T); })()`);

// ── 📦 Update impact on the app page (owner, 2 Oct: "update impact vala isme bhi kar do"): the WHOLE card as the page's own
// section — after the charts, right before the day-by-day table — drawn ONCE (the fold: one line to it); its windows,
// 📅 any date (a real impact_any file of the app when the test made one), 📌 saved dates through the same /api/marks
// calls, the 📦 jumps from elsewhere; and every fallback (Studio still loading / failing / not there) as before ─────────
ctx.__IA = fs.existsSync(path.join(dir, 'impact_any_app.json')) ? J('impact_any_app.json') : null;
get('imppage', `(()=>{ ${RESET} const r={}, ptr=DATA.uninstall.studio;
  const row=DATA.uninstall.apps.find(x=>{ const a=(UNI.apps||[]).find(z=>z.app_id===x.app_id); return a&&uniImpBlocks(a).length&&US._.A().some(s=>s.id===x.app_id); });
  const id=row.app_id, a=UNI.apps.find(z=>z.app_id===id), key=uniImpBlocks(a)[0].key; r.id=id; r.key=key; APP=row.app; UNIAPP=id;
  const ids=h=>{ const m={}; for(const x of h.matchAll(/\\sid="([^"]*)"/g)) m[x[1]]=(m[x[1]]||0)+1; return m; };
  const dups=h=>{ const m=ids(h); return Object.keys(m).filter(k=>m[k]>1); };
  const sec=h=>h.slice(h.indexOf('id="us-imp"'),h.indexOf('id="uni-old-app"'));
  const h=uniScreen(), I=ids(h), iA=h.indexOf('id="us-apg"'), iF=h.indexOf('id="uni-old-app"'), iS=h.indexOf('id="us-imp"'), iC=h.indexOf('id="uni-impact"');
  r.dups=dups(h); r.n={card:I['uni-impact']||0, any:I['uni-any']||0, block:I['uni-imp-'+key]||0, section:I['us-imp']||0, up:I['uni-imp-up']||0};
  const pg=h.slice(iA,iF), s=pg.indexOf('id="us-imp"');
  r.where={studio:iA>=0&&iA<iS&&iS<iC&&iC<iF, charts:pg.indexOf('data-hv="1"')>=0&&pg.lastIndexOf('data-hv="1"')<s,
    grid:pg.indexOf('class="us-cohw"')>=0&&pg.indexOf('class="us-cohw"')<s, gone:pg.indexOf('us-gbars')<s, alerts:pg.indexOf('class="us-ac ')<s,
    table:pg.indexOf('</div></section><div class="us-panel"><div class="us-ph"><div><div class="us-eyebrow">Day by day</div>')>s};
  r.head=pg.indexOf('<section class="us-panel us-imp" id="us-imp" aria-label="Update impact"><div class="us-ph"><div><div class="us-eyebrow">📦 Updates · before vs after</div><h2>📦 Update impact</h2>')>=0;
  r.shortList=pg.indexOf('Updates · since')>=0;                     // (the short list is not drawn a second time)
  r.lines=(pg.slice(s).match(/class="us-u"/g)||[]).length; r.rel=US._.A().find(x=>x.id===id).rel.length;
  r.secText=__text(pg.slice(s,pg.indexOf('<div class="us-impb">')));
  const fold=h.slice(iF); r.fold={line:fold.indexOf('id="uni-imp-up"')>=0&&fold.indexOf('onclick="usImpTo()"')>=0, card:fold.indexOf('id="uni-impact"')>=0,
    any:fold.indexOf('id="uni-any"')>=0, open:fold.indexOf('<details id="uni-old-app" class="uni-oldv" open')===0, open0:UNIOLDAPPOPEN,
    text:__text(fold.slice(0,fold.indexOf('</summary>')))+' | '+__text(uniImpUpLine())};
  // the very card of the older page: only its frame and title line are the section's now
  const old=uniImpactCard(a), bare=uniImpactCard(a,undefined,{bare:true});
  const fr='<div class="card" id="uni-impact" style="margin-bottom:14px"><div class="ct uni-ct"><h3>📦 Update impact</h3><span class="faint" style="font-size:11.5px">every app update · before vs after · newest first</span></div>';
  const H=x=>(x.match(/\\son(?:click|change|input)="[^"]*"/g)||[]).sort().join('|');
  r.same={frame:old.indexOf(fr)===0, body:bare==='<div class="uni-imp-bare" id="uni-impact">'+old.slice(fr.length), onPage:pg.indexOf(bare)>=0, handlers:H(old)===H(bare)&&H(bare).length>0};
  // the card's 7 / 14 / 30 / 60 (every block) and one block's own — on the Studio page
  r.wins={state:uniImpWinsState(a), seg:pg.indexOf('uni-imp-cseg')>=0};
  uniImpWinX(30); const p30=sec(uniScreen()); r.wins.c30={on:p30.indexOf('<button class="on" onclick="uniImpWinX(30)">30 days</button>')>=0, verdict:p30.indexOf('Verdict (30 days)')>=0, saved:localStorage.getItem('imp_win_uni')};
  uniImpWX(key,14); const p14=sec(uniScreen()); r.wins.b14={verdict:p14.indexOf('Verdict (14 days)')>=0, on:p14.indexOf('<button class="on" onclick="uniImpWX(')>=0};
  uniImpWinX(7); localStorage.removeItem('imp_win_uni'); UNIIMPWIN=undefined; UNIIMPWK={};
  r.wins.back7=sec(uniScreen()).indexOf('Verdict (30 days)')<0;
  // 📅 any date + 📌 saved dates: the box's inputs on the Studio page, a real comparison, the very calls to /api/marks
  const M={id:41,app_id:id,date:'',name:'Banner ad hataya',who:'team@example.test',at:'2026-09-20T05:00:00.000Z'};
  if(__IA){ UANY.idx={v:1,file_v:1,apps:[__IA.entry]}; UANY.idxErr=''; UANY.F[id]=__IA.body; M.date=uniAdd(__IA.body.first,120); }
  else { UANY.idx={v:1,file_v:1,apps:[]}; }
  UANY.marks=[M]; UANY.marksErr=''; UANY.me='team@example.test'; UANY.admin=false;
  const pa=sec(uniScreen()); r.any={file:!!__IA, inputs:pa.indexOf('id="uni-any-d"')>=0&&pa.indexOf('onchange="uniAnyPick(this.value)"')>=0, save:pa.indexOf('onclick="uniAnySave()"')>=0,
    mark:pa.indexOf('onclick="uniAnyMk(41)"')>=0, del:pa.indexOf('onclick="uniAnyDel(41)"')>=0, box:pa.indexOf(uniAnyBox(a))>=0};
  const flow=()=>{ const calls=[], kf=fetch, kc=confirm, out={};
    fetch=(u,o)=>{ calls.push({url:String(u),method:(o&&o.method)||'GET',body:o&&o.body?JSON.parse(o.body):null,credentials:o&&o.credentials,redirect:o&&o.redirect}); return new Promise(()=>{}); };
    try{ UANY.marks=null; UANY.marksErr=''; UANYP.marks=null; const h0=uniScreen();                     // the saved dates load with the page
      UANY.marks=[M]; UANYP.marks=null; Object.assign(UANY,{date:'',name:'',star:false,msg:'',mc:'',saving:false,win:7});
      const h1=uniScreen(), on=(re)=>(h1.match(re)||[])[1]||'';
      new Function('return function(){'+on(/id="uni-any-d"[^>]*\\sonchange="([^"]*)"/)+'}')().call({value:M.date});   // the date picked
      new Function('return function(){'+on(/id="uni-any-nm"[^>]*\\soninput="([^"]*)"/)+'}')().call({value:'Banner ad hataya'});
      out.picked={date:UANY.date, name:UANY.name};
      const h2=uniScreen(); out.result=__IA?h2.indexOf('<div class="uni-any-res" data-date="'+M.date+'"')>=0:null;
      out.rows=__IA?(h2.split('<div class="uni-any-res"')[1]||'').split('<tr data-row="').length-1:null;
      eval((h2.match(/id="uni-any-sv"[^>]*\\sonclick="([^"]*)"/)||[])[1]||'');                               // 💾 Save
      UANY.saving=false; confirm=()=>true; eval((h2.match(/\\sonclick="(uniAnyDel\\(41\\))"/)||[])[1]||'');   // × (the author's)
      eval((h2.match(/\\sonclick="(uniAnyMk\\(41\\))"/)||[])[1]||''); out.mk={date:UANY.date, name:UANY.name};   // a saved date re-opens
      out.where=[h0,h2].map(x=>{ const o=x.indexOf('id="uni-old-app"'), y=x.indexOf('id="uni-any"'), q=x.indexOf('id="us-imp"');
        return y<0?'none':(o>=0&&y>o?'fold':(q>=0&&y>q?'studio':'page')); });
    } finally{ fetch=kf; confirm=kc; UANY.saving=false; UANYP.marks=null; }
    out.calls=calls; return out; };
  r.flowStudio=flow(); delete DATA.uninstall.studio; r.flowOld=flow(); DATA.uninstall.studio=ptr;
  Object.assign(UANY,{date:'',name:'',star:false,msg:'',mc:'',win:7});
  // a 📦 jump from elsewhere (Alerts → "Update detail →", the Active users / Install value 📦 links): uniImpGo — the page is
  // drawn while the jump waits (setApp re-draws every screen), the block opens in the Studio section, the fold stays shut,
  // and the scroll waits for the page's own fit-to-width pass, then lands the block under the bars
  const keep={show, setApp, _navSave, st:setTimeout, ge:document.getElementById, w:window}, Q=[], sc=[]; let HJ='';
  show=()=>{}; _navSave=()=>{}; setApp=n=>{ APP=n; HJ=uniScreen(); }; setTimeout=f=>{ Q.push(f); return Q.length; };
  document.getElementById=x=>(x==='uni-imp-'+key)?{closest:q=>q==='#us-root'?{}:null,getBoundingClientRect:()=>({top:900,height:40})}:(x==='us-top'?null:keep.ge(x));
  window={scrollY:100,pageYOffset:100,scrollTo:o=>sc.push(o)};
  try{ APP=''; UNIAPP=''; UNIOLDAPPOPEN=false; uniImpGo(id,key,'uni');
    const pj=sec(HJ), fj=HJ.slice(HJ.indexOf('id="uni-old-app"'));
    r.jump={drawn:!!HJ, open:pj.indexOf('id="uni-imp-'+key+'" data-key="'+key+'" data-open="1"')>=0, fold:fj.indexOf('<details id="uni-old-app" class="uni-oldv" open')===0||UNIOLDAPPOPEN,
      waited:sc.length===0&&Q.length>=1, cleared:impS('uni').jump===''};
    Q.splice(0).forEach(f=>f()); r.jump.scroll=sc.slice(); sc.length=0;
    // the 📦 line in the install-week table (in the fold) → the same block, up in the section
    const mk=(fj.match(/\\sonclick="(uniImp\\('[^']*'\\))"/)||[])[1]||''; r.jump.marker=mk;
    if(mk){ impSet('uni',{open:'-'}); eval(mk); const pm=sec(uniScreen()); r.jump.markerOpen=pm.indexOf('data-open="1"')>=0&&uniImpFind(a,impS('uni').open).b.key===key;
      Q.splice(0).forEach(f=>f()); r.jump.markerScroll=sc.slice(); }
  } finally{ show=keep.show; setApp=keep.setApp; _navSave=keep._navSave; setTimeout=keep.st; document.getElementById=keep.ge; window=keep.w; }
  impSet('uni',{open:'',jump:'',all:false}); UNIOLDAPPOPEN=false; APP=row.app; UNIAPP=id;
  // the Studio's file still loading: no Studio page yet — the card in the fold as before, a waiting 📦 jump opens the fold
  US._.load(null); impSet('uni',{open:key,jump:key,jt:Date.now()}); const hl=uniScreen(); US._.load(__STUDIO); impSet('uni',{jump:'',open:''});
  r.loading={card:hl.indexOf('id="uni-impact"')>hl.indexOf('id="uni-old-app"')&&hl.indexOf('id="uni-old-app"')>=0, section:hl.indexOf('id="us-imp"')>=0, up:hl.indexOf('id="uni-imp-up"')>=0,
    open:hl.indexOf('<details id="uni-old-app" class="uni-oldv" open')>=0, dups:dups(hl)}; UNIOLDAPPOPEN=false;
  // the Studio failing to draw the page: the card stays in the fold (never lost, never twice)
  const kA=US.appScreen; US.appScreen=()=>{ throw new Error('boom'); }; const hx=uniScreen(); US.appScreen=kA;
  r.failed={card:(hx.match(/id="uni-impact"/g)||[]).length, inFold:hx.indexOf('id="uni-impact"')>hx.indexOf('id="uni-old-app"'), up:hx.indexOf('id="uni-imp-up"')>=0, dups:dups(hx)};
  // no Studio file: the older page, as it was (the framed card, no section, no fold, no line)
  const nz=x=>x.replace(/(id="|url\\(#|href="#)([A-Za-z_-]*?)\\d+/g,'$1$2#');
  delete DATA.uninstall.studio; const ho=uniScreen(), od=uniDetail(id,true); DATA.uninstall.studio=ptr;
  r.noStudio={same:nz(ho)===nz(od), frame:ho.indexOf(fr)>=0, section:ho.indexOf('id="us-imp"')>=0, up:ho.indexOf('id="uni-imp-up"')>=0, fold:ho.indexOf('uni-old-app')>=0, dups:dups(ho)};
  // the drawer keeps its short list, pointing at the app page
  const i=US._.A().findIndex(x=>x.id===id); US.openDrawer(i); const dh=document.getElementById('us-drawer').innerHTML; US.closeDrawer();
  r.drawer={short:dh.indexOf('Updates · since')>=0, hint:dh.indexOf('Poora Update impact card (kisi bhi date se tulna) app page pe')>=0, card:dh.indexOf('id="uni-impact"')>=0};
  // an app without updates: the section still there (📅 any date works without one), its empty note, no uninstall lines
  const row0=DATA.uninstall.apps.find(x=>{ const z=(UNI.apps||[]).find(q=>q.app_id===x.app_id); return z&&z.daily&&!uniImpBlocks(z).length&&US._.A().some(q=>q.id===x.app_id); });
  if(row0){ APP=row0.app; UNIAPP=row0.app_id; const h0=uniScreen(); r.noUpd={section:h0.indexOf('id="us-imp"')>=0, card:(h0.match(/id="uni-impact"/g)||[]).length, lines:(sec(h0).match(/class="us-u"/g)||[]).length, dups:dups(h0)}; }
  ${RESET} UANY.app=''; return JSON.stringify(r); })()`);

// ── every chart: one hover path (registered, no own listener), its numbers printed on it, labels never overlapping ──
get('charts', `(()=>{ ${RESET} const r={}, A=US._.A(); const ids=[];
  const scan=h=>{ (h.match(/<svg[^>]* id="(us-[sd]\\d+)"[^>]*data-hv="1"|<svg[^>]*data-hv="1"[^>]* id="(us-[sd]\\d+)"/g)||[]).forEach(t=>{ const m=t.match(/id="(us-[sd]\\d+)"/); ids.push(m[1]); }); };
  const h=uniScreen(); scan(h); const i=A.findIndex(a=>a.rel.length); US.openDrawer(i<0?0:i); const dh=document.getElementById('us-drawer').innerHTML; scan(dh);
  const SPK=US._.SPK(); r.n=ids.length; r.registered=ids.every(id=>SPK[id]&&typeof SPK[id].tip==='function'&&SPK[id].n>0);
  r.tips=ids.every(id=>{ const S=SPK[id]; const a=S.tip(0), b=S.tip(S.n-1); return typeof a==='string'&&a.length>10&&typeof b==='string'&&b.length>10; });
  r.oldHit=dh.indexOf('us-bigr')<0&&dh.indexOf('us-bigx')<0&&h.indexOf('us-bigr')<0;
  // the drawer's rate chart: its labels — the latest day, the range average, the normal, 📦 versions, 🔔 starts
  const big=(dh.match(/<svg viewBox="0 0 (\\d+) (\\d+)" id="us-d\\d+" data-hv="1" role="img" aria-label="Uninstall rate % chart">[\\s\\S]*?<\\/svg>/)||[])[0]||'';
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
// ── "Gone by day N" (tests/test_uninstall_studio_gone.py): the all-apps table, its cells, tooltips, the app view's bars ──
get('gd', `(()=>{ const r={}, A=US._.A(), GDL=US._.GDL;
  const cells=()=>A.map(a=>({id:a.id, c:GDL.map((_,k)=>{ const x=US._.gdCell(a,k); return {all:x.all||null,lat:x.lat||null,eng:x.eng||null,prev:x.prev||null,s:x.s,word:x.word,why:x.why||null,pend:x.pend||null,young:!!x.young,na:!!x.na}; })}));
  for(const k of ['7','30','60']){ ${RESET} KWIN=k; const h=uniScreen(); const T=US._.TIPS, tips=[];
    A.forEach((a,i)=>GDL.forEach((_,c)=>tips.push(__text(T.gd(i,c))))); GDL.forEach((_,c)=>tips.push(__text(T.gdh(c))));
    US.openDrawer(0); const dh=document.getElementById('us-drawer').innerHTML; US.closeDrawer();
    r[k]={screen:h.slice(h.indexOf('id="us-gd"'), h.indexOf('id="us-foot"')), panel:US._.gdHtml(), W:US._.W(), cells:cells(), tips, drawer:dh,
      afterTbl:h.indexOf('id="us-gd"')>h.indexOf('id="us-tbl"')&&h.indexOf('id="us-tbl"')>0&&h.indexOf('id="us-gd"')<h.indexOf('id="us-foot"')}; }
  // the sort switch: by the change (last pakka week − all time), Day 7
  ${RESET} uniScreen(); US._.GST.by='chg'; US._.GST.k=3; US._.GST.d=-1; r.chg=US._.gdHtml(); US._.GST.by='all'; US._.GST.k='sz'; US._.GST.d=-1;
  // the app page (mode p) has the same bars
  ${RESET} uniScreen(); r.page=US._.gdApp(0,'p');
  // a Studio file from before this table (no gt block): a short note, no table, nothing breaks
  const keep=__STUDIO.gt; delete __STUDIO.gt; US._.load(__STUDIO); ${RESET} const h0=uniScreen(); US.openDrawer(0); r.nogd={panel:US._.gdHtml(), drawer:document.getElementById('us-drawer').innerHTML, screen:h0.indexOf('id="us-root"')>=0}; US.closeDrawer();
  __STUDIO.gt=keep; US._.load(__STUDIO); ${RESET} uniScreen();
  return JSON.stringify(r); })()`);
// ── 📦 updates in the install-week grid (owner, 2 Oct: "agar kahi par bhi update aata he to vaha se divide kro"): the
// older table's own release list and dates, a line right above the week each fell in, a tap → that update's block ──────
get('crel', `(()=>{ ${RESET} const r={}, A=US._.A();
  const a=A.find(x=>{ const d=(UNI.apps||[]).find(z=>z.app_id===x.id); return d&&uniImpBlocks(d).length&&x.coh.w.length>=8; });
  const d=UNI.apps.find(z=>z.app_id===a.id), keep=d.releases, W=a.coh.w, row=DATA.uninstall.apps.find(x=>x.app_id===a.id);
  const toks=h=>[...h.matchAll(/<div class="us-(crel|rh|cyr)"([^>]*)>([\\s\\S]*?)<\\/div>/g)].map(m=>({k:m[1],rw:(m[2].match(/data-rw="([^"]*)"/)||[])[1]||null,t:__text(m[3]),h:m[3]}));
  r.weeks=W.map(w=>({w:w.w,f:w.f,t:w.t,part:!!w.part}));
  // the synthetic updates: a mid-week one, two in one week, one on a week's first day, one before the grid's first week
  const syn=[{date:uniAdd(W[1].f,3),kind:'version',version:'9.1'},{date:uniAdd(W[2].f,1),kind:'version',version:'9.2'},{date:uniAdd(W[2].f,5),kind:'version',version:'9.3'},
    {date:W[3].f,kind:'version',version:'9.4'},{date:uniAdd(W[0].f,-10),kind:'version',version:'9.0'}];
  r.orig=(keep||[]).map(x=>({date:x.date,version:x.version,key:uniRelKey(x),block:(uniImpFind(d,uniRelKey(x))||{b:{}}).b.key||null}));
  d.releases=(keep||[]).concat(syn);
  try{
    const out={};
    for(const m of ['abs','dev']){ US._.ST.cohMode=m; out[m]=toks(US._.cohFull(a)); }
    r.modes=out; US._.ST.cohMode='abs';
    // the app page and the drawer: the same lines, the legend under the grid
    APP=row.app; UNIAPP=a.id; const h=uniScreen(), pg=h.slice(h.indexOf('id="us-apg"'),h.indexOf('id="uni-old-app"'));
    const cw=pg.slice(pg.indexOf('class="us-cohw"')); r.page=toks(cw.slice(0,cw.indexOf('</div></div>')+12)).filter(x=>x.k!=='rh').map(x=>x.t);
    r.pageLg=__text((pg.match(/<div class="us-clg us-rlg">[\\s\\S]*?<\\/div>/)||[''])[0]);
    r.pageTaps=[...pg.matchAll(/data-rimp="([^"]*)"/g)].map(m=>m[1]);
    r.pageBlocks=[...pg.matchAll(/id="uni-imp-([^"]*)"/g)].map(m=>m[1]);
    r.secAfterGrid=pg.indexOf('id="us-imp"')>pg.indexOf('class="us-cohw"');
    // the older page's own "Install week × day" (key days, every week shown): its 📦 lines, by the week below each
    UNITRI='cp'; UNITRIEXP=true; const old=uniTriCard(d); UNITRIEXP=false;
    const ot=[...old.matchAll(/<tr class="uni-rel"><td class="nm">([\\s\\S]*?)<\\/td>|<tr(?: style="[^"]*")?><td class="nm" style="white-space:nowrap">([^<]*)/g)].map(m=>m[1]!=null?{rel:__text(m[1])}:{wk:m[2].trim()});
    r.old=[]; let pend=null; ot.forEach(x=>{ if(x.rel!=null) pend=x.rel; else { if(pend!=null) r.old.push({wk:x.wk,rel:pend}); pend=null; } });
    r.newByLabel=W.map(w=>({lab:uniSpan(w.f,w.t,true),w:w.w}));
    // a tap on a version: on the page → uniImp(key) (the older table's jump); in the drawer → closes it, uniImpGo(app, key)
    const calls=[], kI=uniImp, kG=uniImpGo; uniImp=(k,t)=>calls.push(['uniImp',k,t||null]); uniImpGo=(id,k,t)=>calls.push(['uniImpGo',id,k,t]);
    const key=r.pageTaps[0]||'';
    const el=inD=>({getAttribute:x=>x==='data-rimp'?key:null, closest:q=>q==='#us-drawer'?(inD?{}:null):null});
    const tg=inD=>({closest:q=>q==='#us-root,#us-layer'?{}:(q==='[data-rimp]'?el(inD):null), id:''});
    try{ US._.onClick({target:tg(false),preventDefault(){},stopPropagation(){}});
      const i=A.indexOf(a); US.openDrawer(i); const dh=document.getElementById('us-drawer').innerHTML;
      r.drawer=toks(dh.slice(dh.indexOf('class="us-cohw"'))).filter(x=>x.k!=='rh').map(x=>x.t);
      r.drawerTaps=[...dh.matchAll(/data-rimp="([^"]*)"/g)].map(m=>m[1]);
      US._.onClick({target:tg(true),preventDefault(){},stopPropagation(){}}); r.drawerClosed=US._.ST.drawer===-1;
    } finally{ uniImp=kI; uniImpGo=kG; }
    r.calls=calls; r.key=key; r.id=a.id;
    // the older detail not loaded (or failed): the Studio file's own updates, no tap
    const U0=UNI; UNI=null; try{ r.noUni=toks(US._.cohFull(a)).filter(x=>x.k==='crel').map(x=>({t:x.t,tap:/data-rimp/.test(x.h)})); r.rel=a.rel; } finally{ UNI=U0; }
    // weeks that cross a year: a "── 2026 ──" row over each year's weeks (and none on a page in one year)
    const mk=(w,f,t,part)=>Object.assign({},W[W.length-1],{w,f,t,part:!!part});
    const yA=Object.assign({},a,{coh:{ref:a.coh.ref,w:[mk('2025-12-15','2025-12-15','2025-12-21'),mk('2025-12-22','2025-12-22','2025-12-28'),mk('2025-12-29','2025-12-29','2026-01-04'),mk('2026-01-05','2026-01-05','2026-01-07',1)]}});
    d.releases=[{date:'2025-12-31',kind:'version',version:'5.0'},{date:'2025-12-23',kind:'update',version:null}];
    r.year=toks(US._.cohFull(yA)).map(x=>x.k+' '+x.t);
    r.yearPage=pg.indexOf('class="us-cyr"')>=0;
  } finally{ d.releases=keep; }
  ${RESET} uniScreen(); return JSON.stringify(r); })()`);
out.n = Object.keys(out).length;
process.stdout.write(JSON.stringify({ errors, out }));
