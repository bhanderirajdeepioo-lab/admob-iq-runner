// 🗂 Review Studio — the page side, run for real: the dashboard script (frontend/index.html's largest <script>) in a node
// vm with stub browser globals and a tiny DOM (elements that keep their children, ids and innerHTML), on a synthetic
// Studio file + card document the REAL build code made (tests/test_review_studio_frontend.py). The Review API is a mock
// fetch that answers like the Worker and records every request. Prints ONE JSON report; the Python test asserts on it.
//   usage: node review_studio_frontend.js <script.js> <fixture.json>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath, fixturePath] = process.argv.slice(2);
const FX = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// ── a tiny DOM ──
const cls = () => { const s = new Set(); return { add: (...a) => a.forEach(x => s.add(x)), remove: (...a) => a.forEach(x => s.delete(x)),
  toggle: (x, f) => { const on = f === undefined ? !s.has(x) : !!f; on ? s.add(x) : s.delete(x); return on; }, contains: x => s.has(x), get size() { return s.size; } }; };
let ROOT = null;
class El {
  constructor(tag, id) { this.tagName = String(tag || 'div').toUpperCase(); this.id = id || ''; this.children = []; this.parentNode = null; this._html = '';
    this.attrs = {}; this.classList = cls(); this.style = { setProperty() {}, getPropertyValue: () => '' }; this.dataset = {}; this.hidden = false;
    this.open = false; this.value = ''; this.textContent = ''; this.scrollTop = 0; this.className = ''; this.listeners = {}; this.disabled = false; }
  get innerHTML() { return this._html; } set innerHTML(v) { this._html = String(v); this.children.forEach(c => { c.parentNode = null; }); this.children = []; }
  get firstChild() { return this.children[0] || null; } get lastChild() { return this.children[this.children.length - 1] || null; }
  appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); this.children.push(c); c.parentNode = this; return c; }
  insertBefore(c, ref) { if (c.parentNode) c.parentNode.removeChild(c); const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(c); else this.children.splice(i, 0, c); c.parentNode = this; return c; }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; return c; }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  get isConnected() { let p = this; while (p) { if (p === ROOT) return true; p = p.parentNode; } return false; }
  contains(x) { while (x) { if (x === this) return true; x = x.parentNode; } return false; }
  find(id) { for (const c of this.children) { if (c.id === id) return c; const f = c.find(id); if (f) return f; } return null; }
  querySelector(sel) { return sel[0] === '#' && /^#[\w-]+$/.test(sel) ? this.find(sel.slice(1)) : null; }
  querySelectorAll() { return []; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'id') this.id = String(v); } getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; } hasAttribute(k) { return k in this.attrs; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); } removeEventListener() {}
  getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 20, right: 100, bottom: 20 }; }
  focus() {} blur() {} scrollIntoView() {} closest() { return null; } get offsetParent() { return {}; }
}
const body = new El('body', 'body'); ROOT = body;
const PH = {};      // ids that are not in the tree (panel slots, the layer's parts…): one stable stand-in each
const NOT_PH = new Set(['rs-root', 'rs-old']);
const document = new Proxy({
  body, head: new El('head'), documentElement: new El('html'), activeElement: null,
  getElementById: id => body.find(id) || (NOT_PH.has(id) ? null : (/^r[sv]-/.test(String(id)) ? (PH[id] = PH[id] || new El('div', id)) : any)),
  createElement: t => new El(t), querySelector: () => null, querySelectorAll: () => [], addEventListener() {}, removeEventListener() {},
}, { get: (t, k) => (k in t ? t[k] : any) });
const store = () => { const m = {}; return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: k => { delete m[k]; } }; };
// ── the Review API: a mock fetch answering like the Worker (§B.7), every request recorded ──
const REQ = []; let REV = 100, FID = 500, NID = 500, SID = 500; let NEXT = null;   // NEXT: a forced response for the next call
const NOW = '2026-10-01T06:00:00.000Z';
function apiAnswer(path, method, body) {
  const S = vm.runInContext('RV.S', ctx), me = FX.me.email, d = FX.day.day;
  const view = app => ({ ok: true, rev: ++REV, d, app, state: S.states[app] || null, notes: S.notes.filter(n => n.app === app),
    flags: S.flags.filter(f => f.app === app), snoozes: S.snoozes.filter(z => z.app === app) });
  if (path === 'action') {
    const a = body.app; const st = s => ({ st: s, who: me, at: NOW, snz: [] });
    if (body.act === 'ok' || body.act === 'kal') { const v = view(a); v.state = st(body.act); return v; }
    if (body.act === 'note') { const v = view(a); v.notes = v.notes.concat([{ id: ++NID, app: a, text: body.note, who: me, at: NOW }]); if (!v.state) v.state = st('ok'); return v; }
    if (body.act === 'flag') { const v = view(a); v.flags = v.flags.concat([{ id: ++FID, day: d, app: a, app_label: '', feature: body.feature, note: body.note || '', raised_by: me, raised_at: NOW, status: 'open', decision: null }]); if (body.feature == null) v.state = st('flag'); return v; }
    if (body.act === 'unflag') { const v = view(a); v.flags = v.flags.map(f => f.id === body.flag_id ? { ...f, status: 'withdrawn', wd_by: me, wd_at: NOW } : f); return v; }
    if (body.act === 'undo') { const v = view(a); v.state = null; v.notes = []; v.flags = v.flags.map(f => f.day === d && f.status === 'open' ? { ...f, status: 'withdrawn' } : f); return v; }
    if (body.act === 'snooze') { const v = view(a); v.snoozes = v.snoozes.filter(z => z.feature !== body.feature).concat([{ id: ++SID, app: a, feature: body.feature, day: d, until: '2026-10-' + String(1 + body.days).padStart(2, '0'), days: body.days, note: body.note || '', who: me, at: NOW }]); return v; }
    if (body.act === 'unsnooze') { const v = view(a); v.snoozes = v.snoozes.filter(z => z.feature !== body.feature); return v; }
    if (body.act === 'bulk_ok') { const ch = body.apps.filter(k => !S.states[k]); const states = {}; ch.forEach(k => { states[k] = st('ok'); }); return { ok: true, rev: ++REV, d, changed: ch, states }; }
  }
  if (path === 'decide') { const f = S.flags.find(x => x.id === body.flag_id); const dec = body.decision;
    return { ok: true, rev: ++REV, flag: { ...f, status: dec === 'kaam' ? 'kaam' : 'closed', decision: dec === 'done' ? f.decision : dec, dec_note: dec === 'done' ? f.dec_note : body.note, dec_by: me, dec_at: NOW, ...(dec === 'done' ? { done_note: body.note, done_by: me, done_at: NOW } : {}) } }; }
  if (path.startsWith('day')) return { ...FX.state, d };
  if (path.startsWith('calendar')) return { days: { [d]: { rev: 3, kal: 1, flag: 1, notes: 1, people: 2 } } };
  if (path === 'me') return FX.me;
  return { error: 'not_found', msg: 'Nahi mila' };
}
async function fetchMock(url, opt) {
  opt = opt || {};
  const u = String(url);
  if (!u.startsWith('/api/review/')) return new Promise(() => {});
  const path = u.slice('/api/review/'.length), body = opt.body ? JSON.parse(opt.body) : null;
  REQ.push({ url: u, method: opt.method, headers: opt.headers || {}, credentials: opt.credentials, body });
  let status = 200, j;
  if (NEXT) { ({ status, j } = NEXT); NEXT = null; } else j = apiAnswer(path.split('?')[0], opt.method, body);
  return { type: 'basic', status, ok: status >= 200 && status < 300, json: async () => j };
}
const timers = [];
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document, localStorage: store(), sessionStorage: store(), navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} }, history: { replaceState() {} },
  fetch: fetchMock, setTimeout: f => { timers.push(f); return timers.length; }, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: undefined,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean, RegExp, Error,
  TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
  performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 1280, innerHeight: 900, scrollY: 0, scrollTo() {}, alert() {},
  confirm: () => false, prompt: () => null, IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any, Node: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const out = { fns: {} };
const tick = () => new Promise(r => setImmediate(r));
async function step(name, code) {
  try { let v = run(code); if (v && typeof v.then === 'function') v = await v; await tick(); out[name] = v === undefined ? '__undefined__' : JSON.parse(JSON.stringify(v)); }
  catch (e) { errors.push(name + ': ' + e.message + ' @ ' + ((e.stack || '').match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); }
}
(async () => {
  for (const f of ['RVS', 'rvAction', 'rvPost', 'rvApi', 'rvLayout', 'rvStOf']) out.fns[f] = run(`typeof ${f}`);
  ctx.__FX = FX;
  // the older tab's root, as rvShell builds it (its children as real nodes, so the fold can move them)
  run(`DATA={currency:'USD',usd_inr:__FX.day.fx||88,app_icons:{},apps:[],apps_catalog:__FX.day.apps.map(a=>({app_id:a.app_id,app_name:a.dname,selected:true}))}; CURVIEW='USD';
    (()=>{ const r=document.createElement('section'); r.id='rv-root'; document.body.appendChild(r);
      [['div','',' rv-head'],['div','','rv-tabs'],['div','rv-bans',''],['div','rv-v-today',''],['div','rv-v-sum',''],['div','rv-v-hist',''],['div','rv-toast','rv-toast']]
        .forEach(([t,id,c])=>{ const e=document.createElement(t); if(id) e.id=id; e.className=c; r.appendChild(e); });
      RV.root=r; })();
    RV.idx=__FX.index; RV.doc=__FX.day; RV.me=__FX.me; RV.S={...rvS(__FX.state,__FX.day.day),open_day:__FX.day.day,me:__FX.me}; RV.view='today';`);
  out.order0 = run(`RV.root.children.map(c=>c.id||c.className)`);
  // ── no file yet (loading): the Studio shell + the fold; the file arrives: the Studio ──
  await step('loading', `(()=>{ RVS._.syncNow(); return {on:RVS.on(), ready:RVS.ready(), st:document.getElementById('rs-root').getAttribute('data-st'), html:document.getElementById('rs-root').innerHTML}; })()`);
  await step('layout', `(()=>{ RVS._.load(__FX.studio); RVS._.syncNow(); const r=RV.root, f=document.getElementById('rs-old');
    return {on:RVS.on(), order:r.children.map(c=>c.id||c.className), fold:f.children.map(c=>c.tagName+':'+(c.className||'')), folded:f.lastChild.children.map(c=>c.id||c.className), rson:r.classList.contains('rs-on')}; })()`);
  // ── every app rendered, every view ──
  await step('apps', `RVS._.A.map(a=>({key:a.key, name:a.name, acct:a.acct, tag:a.tag, grp:a.grp, raw:!!a.raw}))`);
  await step('html', `(()=>{ const r={}; r.root=document.getElementById('rs-root').innerHTML; r.map=RVS._.mapHtml(); r.hero=RVS._.heroHtml(); r.list=RVS._.listHtml();
    RVS._.ST.mode='table'; r.table=RVS._.listHtml(); RVS._.ST.mode='cards';
    r.sum=RVS._.sumHtml(); r.hist=RVS._.histHtml(); r.drawers={}; RVS._.A.forEach(a=>{ r.drawers[a.key]=RVS._.drawerHtml(a.key); });
    r.tips={}; const T=RVS._.TIPS; RVS._.A.forEach(a=>{ r.tips[a.key]=['kamai','uninstall','active','value','update','ads','deduct','mediation','health','setup'].map(f=>T.cell(a.key,f,false)).join('|')+T.app(a.key); });
    r.frtips=['frozen','rev','ga4','final','next'].map(k=>T.fr(k)).join('|'); return r; })()`);
  await step('inr', `(()=>{ CURVIEW='INR'; const h=RVS._.heroHtml()+RVS._.drawerHtml(RVS._.A[0].key); CURVIEW='USD'; return h; })()`);
  // ── every action → the right endpoint, the right body (the older tab's own request shape) ──
  const K = FX.keys;
  const reqs = () => { const r = REQ.splice(0); return r.map(x => ({ url: x.url, method: x.method, ct: x.headers['Content-Type'] || null, cred: x.credentials, body: x.body })); };
  const stOf = k => run(`rvStOf(RV.S,${JSON.stringify(k)})`);
  const toast = () => run(`document.getElementById('rv-toast').textContent`);
  REQ.splice(0);
  await step('a_ok', `RVS._.doOk(${JSON.stringify(K.ok)}, null)`); out.r_ok = { req: reqs(), st: stOf(K.ok), toast: toast() };
  await step('a_ok_again', `RVS._.doOk(${JSON.stringify(K.ok)}, null)`); out.r_ok_again = { req: reqs(), toast: toast() };
  await step('a_kal', `RVS._.doKal(${JSON.stringify(K.kal)}, null)`); out.r_kal = { req: reqs(), st: stOf(K.kal), toast: toast() };
  await step('a_note', `(()=>{ RVS._.cardAct('note',${JSON.stringify(K.note)},null); const p=RVS._.PNL; document.getElementById('rs-pta').value='Synthetic note <b>x</b>'; return RVS._.panelAct('note-save',null); })()`);
  out.r_note = { req: reqs(), st: stOf(K.note), pnl: run('RVS._.PNL') };
  await step('a_note_empty', `(()=>{ RVS._.cardAct('note',${JSON.stringify(K.note)},null); document.getElementById('rs-pta').value='  '; RVS._.panelAct('note-save',null); const p=!!RVS._.PNL; RVS._.panelAct('close',null); return p; })()`);
  out.r_note_empty = { req: reqs(), toast: toast() };
  await step('a_imp', `(()=>{ RVS._.cardAct('imp',${JSON.stringify(K.imp)},null); document.getElementById('rs-pta').value='Admin dekho'; return RVS._.panelAct('imp-save',null); })()`);
  out.r_imp = { req: reqs(), st: stOf(K.imp), toast: toast() };
  await step('a_ok_flagged', `RVS._.doOk(${JSON.stringify(K.imp)}, null)`); out.r_ok_flagged = { req: reqs(), toast: toast() };
  await step('a_undo', `(()=>{ RVS._.cardAct('undo',${JSON.stringify(K.imp)},null); return RVS._.panelAct('undo-yes',null); })()`);
  out.r_undo = { req: reqs(), st: stOf(K.imp) };
  await step('a_fflag', `(()=>{ RVS._.featAct(${JSON.stringify(K.feat)},${JSON.stringify(K.f)},null); document.getElementById('rs-pta').value='Sirf ye'; return RVS._.panelAct('fflag-save',null); })()`);
  out.r_fflag = { req: reqs(), flags: run(`RV.S.flags.filter(x=>x.app===${JSON.stringify(K.feat)}).map(x=>[x.feature,x.status])`) };
  await step('a_unflag', `(()=>{ RVS._.featAct(${JSON.stringify(K.feat)},${JSON.stringify(K.f)},null); return RVS._.panelAct('fflag-off',null); })()`);
  out.r_unflag = { req: reqs(), flags: run(`RV.S.flags.filter(x=>x.app===${JSON.stringify(K.feat)}).map(x=>[x.feature,x.status])`) };
  await step('a_snz', `(()=>{ RVS._.snzAct(${JSON.stringify(K.feat)},${JSON.stringify(K.f)},null); RVS._.PNL.days=14; document.getElementById('rs-pta').value='Pata hai'; return RVS._.panelAct('snz-save',null); })()`);
  out.r_snz = { req: reqs(), eff: run(`rvEffSt(RV.doc,RV.S,${JSON.stringify(K.feat)},${JSON.stringify(K.f)})`) };
  await step('a_unsnz', `(()=>{ RVS._.snzAct(${JSON.stringify(K.feat)},${JSON.stringify(K.f)},null); return RVS._.panelAct('snz-off',null); })()`);
  out.r_unsnz = { req: reqs(), eff: run(`rvEffSt(RV.doc,RV.S,${JSON.stringify(K.feat)},${JSON.stringify(K.f)})`) };
  await step('a_bulk', `(()=>{ RVS._.prep(); const g=RVS._.A.some(a=>a.grp==='ok'&&rvStOf(RV.S,a.key)==='pend')?'ok':'small'; RVS._.bulkAct(g,null); return RVS._.panelAct('bulk-yes',null); })()`);
  out.r_bulk = { req: reqs() };
  await step('a_dec', `(async()=>{ const f=RV.S.flags.find(x=>x.status==='open'); RVS._.decAct(f.id,'kaam',null); document.getElementById('rs-pta').value=''; await RVS._.panelAct('dec-save',null);
    const empty=document.getElementById('rv-toast').textContent; document.getElementById('rs-pta').value='Developer ko bolo'; await RVS._.panelAct('dec-save',null);
    const a=RV.S.flags.find(x=>x.id===f.id).status; RVS._.decAct(f.id,'done',null); document.getElementById('rs-pta').value=''; await RVS._.panelAct('dec-save',null);
    return {id:f.id, empty, after_kaam:a, after_done:RV.S.flags.find(x=>x.id===f.id).status}; })()`);
  out.r_dec = { req: reqs() };
  // an API refusal: the older tab's own message (rvFail), nothing changes
  NEXT = { status: 409, j: { error: 'conflict', why: 'flagged', msg: 'Ye card 🚩 Re-review me hai — admin ke faisle tak aise hi rahega' } };
  const pend = FX.keys.pend;
  await step('a_409', `RVS._.doOk(${JSON.stringify(pend)}, null)`); out.r_409 = { req: reqs(), st: stOf(pend), toast: toast(), fail: run(`rvFailMsg({msg:'Ye card 🚩 Re-review me hai — admin ke faisle tak aise hi rahega'})`) };
  NEXT = { status: 401, j: { error: 'unauthorized', msg: 'Login zaroori — page reload karo' } };
  await step('a_401', `RVS._.doOk(${JSON.stringify(pend)}, null)`); out.r_401 = { req: reqs(), auth: run('RV.auth'), toast: toast(), canW: run('rvCanWrite()') };
  await step('a_ro', `RVS._.doOk(${JSON.stringify(pend)}, null)`); out.r_ro = { req: reqs(), toast: toast() };
  run('RV.auth=true; RV.meErr=null;');
  // ── the older views: no pointer / a failed load → the tab exactly as before (the nodes back in their order) ──
  await step('fallback', `(()=>{ const r={}; const ptr=RV.idx.studio; RV.idx={...RV.idx}; delete RV.idx.studio; RVS._.syncNow();
    r.noptr={on:RVS.on(), order:RV.root.children.map(c=>c.id||c.className), rson:RV.root.classList.contains('rs-on'), rs:!!document.getElementById('rs-root'), old:!!document.getElementById('rs-old')};
    RV.idx={...RV.idx,studio:ptr}; RVS._.load(__FX.studio); RVS._.syncNow(); r.back=RVS.on();
    RVS._.fail(); RVS._.syncNow(); r.failed={on:RVS.on(), order:RV.root.children.map(c=>c.id||c.className)};
    RVS._.load(__FX.studio); RVS._.syncNow(); r.back2=RVS.on();
    RV.doc={...RV.doc,built_at:'2026-10-01T05:00:00Z'}; RVS._.syncNow(); r.otherCard={on:RVS.on()}; RV.doc=__FX.day; RVS._.syncNow(); r.back3=RVS.on();
    return r; })()`);
  // ── an app the file left out (its card could not be read at build time): still shown, from the card itself ──
  await step('raw', `(()=>{ const j=JSON.parse(JSON.stringify(__FX.studio)); const k=j.apps[0].key; j.apps=j.apps.slice(1); RVS._.load(j); RVS._.syncNow(); RVS._.prep();
    const a=RVS._.A.find(x=>x.key===k), h=RVS._.listHtml(), m=RVS._.mapHtml(), d=RVS._.drawerHtml(k);
    const r={key:k, n:RVS._.A.length, raw:!!(a&&a.raw), card:h.indexOf('id="rs-c-'+k+'"')>=0, pill:h.indexOf('Studio data nahi — card ka text')>=0, map:m.indexOf('data-rsgo="'+k+'"')>=0, drawer:d.length>500};
    RVS._.load(__FX.studio); RVS._.syncNow(); return r; })()`);
  out.errors = errors;
  process.stdout.write(JSON.stringify(out));
})();
