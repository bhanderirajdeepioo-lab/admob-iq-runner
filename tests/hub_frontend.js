// ✨ App Hub (the new layout, BETA) — the page side, run for real: the dashboard script (frontend/index.html's largest
// <script>) in a node vm with stub browser globals, a small DOM (every screen a <section>, the hub's tab bar) and a FAKE
// browser history (entries, an index, popstate when a step back / forward lands — after the current task, as a browser
// does). render() and the lazy loaders are stand-ins (no dashboard fixture needed); show(), setApp(), the HB Back steps, the
// hub module and the switch are the page's own. On SYNTHETIC data made up here (no real names, ids or money):
//   * routing: hubResolve for every screen in both scopes, the tab fallbacks, the switch (?layout=hub / classic /
//     localStorage, a throwing localStorage), the old layout untouched when off;
//   * Back / Forward through tab and app changes (one step per tap), refresh / bookmark survival (#home/<key>/<tab>);
//   * the App Overview cards: status word + key line per feature, from a made-up Review card file, the eCPM tab's own
//     status, Audience (stub), Baseline, Alerts, Movers.
// Prints ONE JSON report; tests/test_hub_frontend.py asserts on it.   usage: node hub_frontend.js <script.js>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath] = process.argv.slice(2);
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// ── a small DOM ───────────────────────────────────────────────────────────────────────────────────────────────────────
const ELS = {};
function mk(tag) {
  const cls = new Set(), attrs = {};
  const el = {
    tagName: String(tag || 'div').toUpperCase(), id: '', textContent: '', dataset: {}, children: [], parentElement: null, hidden: false,
    style: { cssText: '', setProperty() {} }, scrollLeft: 0, clientWidth: 0, offsetLeft: 0, offsetWidth: 0, tabIndex: 0, _html: '',
    get innerHTML() { return el._html; }, set innerHTML(v) { el._html = String(v); el._kids = null; },
    classList: { add: (...a) => a.forEach(x => cls.add(x)), remove: (...a) => a.forEach(x => cls.delete(x)), contains: x => cls.has(x),
      toggle: (x, f) => { const on = f === undefined ? !cls.has(x) : !!f; on ? cls.add(x) : cls.delete(x); return on; } },
    get className() { return [...cls].join(' '); }, set className(v) { cls.clear(); String(v).split(/\s+/).filter(Boolean).forEach(x => cls.add(x)); },
    setAttribute(k, v) { attrs[k] = String(v); if (k === 'id') { el.id = String(v); ELS[el.id] = el; } }, getAttribute: k => (k in attrs ? attrs[k] : null),
    removeAttribute(k) { delete attrs[k]; }, hasAttribute: k => k in attrs,
    appendChild(c) { c.parentElement = el; el.children.push(c); if (c.id) ELS[c.id] = c; return c; }, append(...cs) { cs.forEach(c => el.appendChild(c)); },
    insertBefore(c) { c.parentElement = el; el.children.unshift(c); if (c.id) ELS[c.id] = c; return c; }, get firstChild() { return el.children[0] || null; },
    addEventListener() {}, removeEventListener() {}, querySelector: () => null, closest: () => null,
    // the tab bar: its buttons, from the HTML the hub wrote (kept between calls, like real nodes)
    querySelectorAll(sel) { if (sel !== '.hub-tab') return [];
      if (!el._kids) el._kids = [...el._html.matchAll(/data-tab="([a-z]+)"/g)].map(m => { const b = mk('button'); b.setAttribute('data-tab', m[1]); b.setAttribute('class', 'hub-tab'); return b; });
      return el._kids; },
    contains: () => false, focus() {}, blur() {}, scrollIntoView() {}, replaceWith() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }),
  };
  return el;
}
const idEl = id => { const e = mk('div'); e.setAttribute('id', id); return e; };
['tb-title', 'tb-sub', 'nav-alert', 'nav-alert-h', 'fresh-txt', 'tab-alert', 'hub-beta', 'hub-beta-s', 'rangesel', 'rangecustom', 'banner', 'screens'].forEach(idEl);
const BAR = idEl('hub-bar'); BAR.hidden = true;
const BODY = mk('body');
const SCREEN_IDS = ['overview', 'placements', 'reportcard', 'appdetail', 'movers', 'alerts', 'deductions', 'countries', 'baseline', 'mediation', 'roas',
  'active', 'uninstall', 'datewise', 'reco', 'health', 'settings', 'value', 'ecpm', 'audience', 'hubrv', 'review'];
const SCREENS = SCREEN_IDS.map(id => { const s = mk('section'); s.className = 'screen'; s.dataset.screen = id; return s; });
SCREENS[0].classList.add('on');
const scr = id => SCREENS.find(s => s.dataset.screen === id) || null;
const document = new Proxy({
  getElementById: id => ELS[id] || null, createElement: mk, body: BODY, head: mk('head'), documentElement: mk('html'),
  querySelector: sel => { if (sel === '.screen.on') return SCREENS.find(s => s.classList.contains('on')) || null;
    const m = /^\.screen\[data-screen=([a-z]+)\]$/.exec(sel); if (m) return scr(m[1]); return null; },
  querySelectorAll: sel => (sel === '.screen' ? SCREENS : []),
  addEventListener() {}, removeEventListener() {},
}, { get: (t, k) => (k in t ? t[k] : any) });
// ── a fake browser history ────────────────────────────────────────────────────────────────────────────────────────────
const LOC = { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} };
const POP = [];
const HIST = { entries: [{ state: null, url: '/' }], idx: 0, calls: [], pending: [] };
const setUrl = u => { const s = String(u || '/'), h = s.indexOf('#'), b = h >= 0 ? s.slice(0, h) : s, q = b.indexOf('?');
  LOC.hash = h >= 0 ? s.slice(h) : ''; LOC.search = q >= 0 ? b.slice(q) : ''; };
const history = {
  get length() { return HIST.entries.length; }, get state() { return HIST.entries[HIST.idx].state; },
  pushState(st, _t, url) { HIST.calls.push('push'); const u = url == null ? HIST.entries[HIST.idx].url : url;
    HIST.entries.splice(HIST.idx + 1); HIST.entries.push({ state: JSON.parse(JSON.stringify(st)), url: u }); HIST.idx++; setUrl(u); },
  replaceState(st, _t, url) { HIST.calls.push('replace'); const e = HIST.entries[HIST.idx]; e.state = st == null ? null : JSON.parse(JSON.stringify(st));
    if (url != null) { e.url = url; setUrl(url); } },
  go(n) { HIST.calls.push('go(' + n + ')'); HIST.pending.push(n); }, back() { history.go(-1); }, forward() { history.go(1); },
};
function land() { while (HIST.pending.length) { const n = HIST.pending.shift(), to = HIST.idx + n;
  if (to < 0) { HIST.left = true; continue; } if (to >= HIST.entries.length) continue;
  HIST.idx = to; setUrl(HIST.entries[to].url); POP.forEach(f => f({ type: 'popstate', state: HIST.entries[to].state })); } }
let LS_THROW = false;
const store = () => { const b = {}; return { getItem: k => { if (LS_THROW) throw new Error('blocked'); return k in b ? b[k] : null; },
  setItem: (k, v) => { if (LS_THROW) throw new Error('blocked'); b[k] = String(v); }, removeItem: k => { if (LS_THROW) throw new Error('blocked'); delete b[k]; } }; };
const SCROLLS = [];
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  document, localStorage: store(), sessionStorage: store(), navigator: any, location: LOC, history,
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener: (type, fn) => { if (type === 'popstate') POP.push(fn); }, removeEventListener() {},
  DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean, RegExp,
  Error, TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat, unescape, escape,
  encodeURIComponent, decodeURIComponent, performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 375,
  innerHeight: 812, scrollY: 0, scrollTo: (a) => { SCROLLS.push(a && typeof a === 'object' ? a.top : a); }, alert() {}, confirm: () => false, prompt: () => null,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any, Node: any,
};
ctx.window = ctx; ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const tick = () => new Promise(r => setImmediate(r));
const settle = async () => { await tick(); land(); await tick(); land(); await tick(); };
const out = {};
const step = async (name, fn) => { try { out[name] = await fn(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };

// ── synthetic data: 3 apps (a big one with GA4, a small one with GA4, one without GA4), 40 days of AdMob days ──────────
const D0 = Date.UTC(2026, 0, 1), day = i => new Date(D0 + i * 864e5).toISOString().slice(0, 10);
const DAYS = Array.from({ length: 41 }, (_, i) => day(i));         // the last one = today (partial)
const TODAY = DAYS[40], LAST = DAYS[39];
// [date, earn_micros, impressions, requests, matched, clicks]: eCPM steady ~$4 with a small wobble, then $2.80 on the last
// complete day (a drop well beyond the usual swing → the eCPM tab's own "Worse")
const rowsFor = (usd, impr) => DAYS.map((d, i) => { const ec = i === 39 ? 2.8 : 4 * (1 + (i % 3 - 1) * 0.01); const im = impr; return [d, Math.round(ec * im / 1000 * 1e6), im, im + 100, im + 50, 10]; });
const IDS = { big: 'ca-app-pub-0000000000000001~1000000001', small: 'ca-app-pub-0000000000000002~2000000002', noga: 'ca-app-pub-0000000000000003~3000000003' };
ctx.__DATA = {
  currency: 'USD', usd_inr: 90, today_date: TODAY, latest_complete: LAST, generated_at: '2026-02-10T00:00:00Z', report_tz_label: 'UTC',
  apps: [{ name: 'Demo Gallery', revenue: 900, placements: 2 }, { name: 'Puzzle Quest', revenue: 40, placements: 1 }, { name: 'Tiny Notes', revenue: 5, placements: 1 }],
  apps_catalog: [{ app_id: IDS.big, app_name: 'Demo Gallery', rev: 900, account_id: 'pub-0000000000000001' },
    { app_id: IDS.small, app_name: 'Puzzle Quest', rev: 40, account_id: 'pub-0000000000000002' },
    { app_id: IDS.noga, app_name: 'Tiny Notes', rev: 5, account_id: 'pub-0000000000000003' }],
  app_icons: {}, app_store_ids: {}, accounts: [],
  placements: [
    { id: 'ca-app-pub-0000000000000001/1111111111', name: 'splash_open', app: 'Demo Gallery', daily: rowsFor(0, 200000) },
    { id: 'ca-app-pub-0000000000000001/2222222222', name: 'home_banner', app: 'Demo Gallery', daily: rowsFor(0, 50000) },
    { id: 'ca-app-pub-0000000000000002/3333333333', name: 'list_native', app: 'Puzzle Quest', daily: rowsFor(0, 8000) },
    { id: 'ca-app-pub-0000000000000003/4444444444', name: 'top_banner', app: 'Tiny Notes', daily: rowsFor(0, 1500) }],
  alerts: { counts: { critical: 0, warning: 1, watch: 0 }, items: [{ place: 'home_banner', id: 'ca-app-pub-0000000000000001/2222222222', app: 'Demo Gallery', severity: 'warning', lost: 12.5, metrics: [] }] },
  range_alerts: [{ id: 'ca-app-pub-0000000000000001/1111111111', place: 'splash_open', app: 'Demo Gallery', metric: 'show', severity: 'watch', message: 'Show rate 71% — below approved range 80%–84%' }],
  movers: { increasing: [], decreasing: [], steady: [] },
  active: { apps: [{ app_id: IDS.big, app: 'Demo Gallery', key: 'x', data_till: DAYS[37], latest: { day: DAYS[37], a1: 123456, ret_dau: 100000, prov: true } },
    { app_id: IDS.small, app: 'Puzzle Quest', key: 'y', data_till: DAYS[37], latest: { day: DAYS[37], a1: 4321, ret_dau: 4000, prov: false } }],
    alerts: [{ app: 'Demo Gallery', severity: 'watch' }, { app: 'Demo Gallery', severity: 'good' }] },
  uninstall: { apps: [{ app_id: IDS.big, app: 'Demo Gallery' }, { app_id: IDS.small, app: 'Puzzle Quest' }], alerts: [] },
  value: { apps: [{ app_id: IDS.big, app: 'Demo Gallery' }, { app_id: IDS.small, app: 'Puzzle Quest' }], alerts: [] },
};
// stand-ins: render() rebuilds nothing (the real one needs the whole dashboard) but ends like the real one; no fetch / Studio
run(`DATA=__DATA; CURVIEW=null;
  render=function(){ __renders++; HUB.hold++; try{ show('overview'); }finally{ HUB.hold--; } };
  var __renders=0, __ad=[];
  ecPaint=function(){}; loadBaseline=function(){}; loadMED=function(){}; loadDED=function(){}; loadUNI=function(){};
  actEnsure=function(){}; valEnsure=function(){}; rvEnsure=function(){ return Promise.resolve(); }; rvBadge=function(){};
  US.ensure=function(){}; AS.ensure=function(){}; VS.ensure=function(){}; AU.show=function(){}; AU.left=function(){};
  // the App Report: the page's own hooks around a stand-in body (the real one draws the whole report from DATA)
  openAppDetail=function(name){ if(hubOpenApp(name)) return; __ad.push(name); ADAPP=name;
    document.querySelectorAll('.screen').forEach(x=>x.classList.toggle('on',x.dataset.screen==='appdetail')); rvOnShow('appdetail'); if(HUB.on) hubPost('appdetail'); };`);
const S = () => run(`({scr:hubScr(),app:APP,inHub:HUB.inHub,tab:HUB.tab,on:HUB.on,bar:!document.getElementById('hub-bar').hidden,
  hubOn:document.body.classList.contains('hub-on'),hubIn:document.body.classList.contains('hub-in'),depth:HB.depth,st:HB.st.map(x=>x.tag)})`);
const H = () => ({ hash: LOC.hash, idx: HIST.idx, len: HIST.entries.length, urls: HIST.entries.map(e => e.url) });
const userBack = async () => { history.back(); HIST.calls.pop(); land(); await settle(); };
const userFwd = async () => { history.forward(); HIST.calls.pop(); land(); await settle(); };
const fresh = async (opt) => { opt = opt || {};   // a new page load: history, URL, storage and the hub state from scratch
  run(`HB.st.length=0; HB.busy=false; HB.mute=0; HB.depth=0; HUB.on=false; HUB.inHub=false; HUB.tab='overview'; HUB.cur=null; HUB.boot=false; HUB.nav=false; HUB.hold=0;
    HUB.kc={}; HUB.keys=null; HUB.keysFor=null; APP=''; ADAPP=''; UNIAPP=''; ACTAPP=''; VALAPP='';`);
  HIST.entries = [{ state: null, url: '/' + (opt.search || '') + (opt.hash || '') }]; HIST.idx = 0; HIST.calls = []; HIST.pending = []; HIST.left = false;
  LOC.search = opt.search || ''; LOC.hash = opt.hash || '';
  if (!opt.keepStore) { run(`try{ localStorage.removeItem('iq_layout'); localStorage.removeItem('navstate'); }catch(e){}`); }
  SCREENS.forEach(s => s.classList.toggle('on', s.dataset.screen === (opt.screen || 'overview'))); BODY.className = ''; BAR.hidden = true; BAR.innerHTML = '';
  run(`hubInit(); hubBoot(); hubReady();`); await settle(); };

(async () => {
  // ── sha-1 / keys / routes ───────────────────────────────────────────────────────────────────────────────────────────
  await step('keys', () => ({
    abc: run(`hubSha1('abc')`), empty: run(`hubSha1('')`), long: run(`hubSha1('a'.repeat(1000))`), utf8: run(`hubSha1('₹ जी')`),
    big: run(`hubKeyOf('Demo Gallery')`), small: run(`hubKeyOf('Puzzle Quest')`), noga: run(`hubKeyOf('Tiny Notes')`), all: run(`hubKeyOf('')`),
    back: run(`[hubNameOf(hubKeyOf('Demo Gallery')),hubNameOf('all'),hubNameOf('zzzzzzzzzzzz')]`),
    parse: run(`[hubParse('#home/all/active'),hubParse('#home'),hubParse('#home/abc123'),hubParse('#review/history'),hubParse('#home/AB/x'),hubParse('')]`),
    tabsAll: run(`hubTabs('')`), tabsApp: run(`hubTabs('Demo Gallery')`),
  }));
  await step('resolve', () => run(`(()=>{ const r={}, A='Demo Gallery';
    const ids=['home','overview','placements','appdetail','ecpm','active','uninstall','value','audience','mediation','roas','baseline','deductions','health','movers','alerts','hubrv','review','reco','settings','datewise','reportcard','countries'];
    for(const [sc,app] of [['all',''],['app',A]]) for(const inHub of [true,false]) for(const id of ids){ const x=hubResolve(id,app,{inHub,tab:'active'}); r[sc+'|'+(inHub?'in':'out')+'|'+id]=[x.inHub,x.tab,x.screen]; }
    r['app|in|home@alerts']=(x=>[x.inHub,x.tab,x.screen])(hubResolve('home',A,{inHub:true,tab:'alerts'}));
    r['all|in|home@alerts']=(x=>[x.inHub,x.tab,x.screen])(hubResolve('home','',{inHub:true,tab:'alerts'}));
    r['all|in|appdetail@revenue']=(x=>[x.inHub,x.tab,x.screen])(hubResolve('appdetail','',{inHub:true,tab:'revenue'}));
    r['app|in|placements@revenue']=(x=>[x.inHub,x.tab,x.screen])(hubResolve('placements',A,{inHub:true,tab:'revenue'}));
    r['all|in|datewise@movers']=(x=>[x.inHub,x.tab,x.screen])(hubResolve('datewise','',{inHub:true,tab:'movers'}));
    return r; })()`));
  // ── the switch ──────────────────────────────────────────────────────────────────────────────────────────────────────
  await step('switch_default_off', async () => { await fresh(); return { ...S(), ls: run(`localStorage.getItem('iq_layout')`), hash: LOC.hash, calls: HIST.calls.slice() }; });
  await step('switch_param_on', async () => { await fresh({ search: '?layout=hub&x=1' });
    return { ...S(), ls: run(`localStorage.getItem('iq_layout')`), url: HIST.entries[0].url, sw: [ELS['hub-beta'].getAttribute('aria-checked'), ELS['hub-beta-s'].textContent] }; });
  await step('switch_stored', async () => { await fresh({ keepStore: true }); return { on: run('HUB.on'), ls: run(`localStorage.getItem('iq_layout')`) }; });
  await step('switch_param_off', async () => { await fresh({ search: '?layout=classic', keepStore: true }); return { on: run('HUB.on'), ls: run(`localStorage.getItem('iq_layout')`), url: HIST.entries[0].url }; });
  await step('switch_storage_blocked', async () => { LS_THROW = true; let threw = null; try { await fresh({ keepStore: true }); run('hubToggle(true)'); } catch (e) { threw = e.message; } LS_THROW = false;
    return { threw, on: run('HUB.on') }; });
  // ── the old layout (off): no hub class, no #home, the old 'app' Back step, show() as before ────────────────────────────
  await step('off_untouched', async () => { await fresh(); HIST.calls = [];
    run(`show('active')`); const a = S(); run(`setApp('Demo Gallery')`); await settle(); const b = S(); const h = H();
    run(`show('alerts')`); const c = S();
    return { a, b, c, hash: h.hash, urls: h.urls, calls: HIST.calls.slice(), ov: run(`(()=>{ const s=document.createElement('section'); return hubOv(s)===s&&s.children.length===0; })()`) }; });
  // ── on: Home, tabs, the picker keeps the tab, fallbacks, one Back step per tap, Forward, the URL ───────────────────────
  await step('on_walk', async () => { await fresh({ search: '?layout=hub' }); const L = [];
    const snap = n => L.push({ n, ...S(), hash: LOC.hash, len: HIST.entries.length, idx: HIST.idx, renders: run('__renders') });
    snap('boot');
    run(`hubHome()`); await settle(); snap('home');
    run(`hubTab('movers')`); await settle(); snap('movers');
    run(`hubTab('movers')`); await settle(); snap('movers-again');
    run(`setApp('Demo Gallery')`); await settle(); snap('pick-app');
    run(`hubTab('alerts')`); await settle(); snap('alerts');
    run(`hubTab('revenue')`); await settle(); snap('revenue');
    run(`hubTab('review')`); await settle(); snap('review');
    run(`setApp('')`); await settle(); snap('pick-all');          // Review history is not an All-apps tab → Overview
    await userBack(); snap('back1'); await userBack(); snap('back2'); await userBack(); snap('back3'); await userBack(); snap('back4');
    await userFwd(); snap('fwd1'); await userFwd(); snap('fwd2');
    run(`hubGo('Puzzle Quest','value')`); await settle(); snap('go-small-value');   // an app + tab in one tap = ONE step
    return { L, ad: run('__ad.slice()'), scrolls: SCROLLS.splice(0).length };
  });
  await step('old_names', async () => { await fresh({ search: '?layout=hub' }); run(`hubGo('Demo Gallery','overview')`); await settle(); const r = {};
    for (const id of ['active', 'uninstall', 'value', 'baseline', 'mediation', 'placements', 'alerts', 'ecpm', 'datewise']) { run(`show('${id}')`); await settle(); r[id] = S(); }
    run(`setApp('')`); await settle(); r.toAll = S(); run(`show('alerts')`); await settle(); r.alertsAll = S();
    run(`hubNavPage('reco')`); await settle(); r.reco = { ...S(), hash: LOC.hash };
    run(`hubHome()`); await settle(); r.home = { ...S(), hash: LOC.hash };
    run(`openAppDetail('Puzzle Quest')`); await settle(); r.appdetail = S();
    run(`hubGo('','overview')`); await settle(); run(`HUB.inHub=true`); run(`openAppDetail('Tiny Notes')`); await settle(); r.ovList = S();
    return r; });
  await step('refresh', async () => {
    const k = run(`hubKeyOf('Puzzle Quest')`);
    await fresh({ search: '?layout=hub', hash: `#home/${k}/uninstall` }); const a = { ...S(), hash: LOC.hash };
    await fresh({ search: '?layout=hub', hash: `#home/all/movers` }); const b = { ...S(), hash: LOC.hash };
    await fresh({ search: '?layout=hub', hash: `#home/zzzzzzzzzzzz/active` }); const c = { ...S(), hash: LOC.hash };
    await fresh({ search: '?layout=hub', hash: `#home/${k}/nosuchtab` }); const d = { ...S(), hash: LOC.hash };
    await fresh({ hash: `#home/${k}/uninstall` }); const e = { ...S(), hash: LOC.hash };   // the switch off: a #home URL is ignored
    // the 5-min refresh / ₹⇄$ (a same-view rebuild): the tab stays, no Back step
    await fresh({ search: '?layout=hub', hash: `#home/${k}/value` }); const n0 = HIST.entries.length; run(`rerender()`); await settle(); const f = { ...S(), hash: LOC.hash, steps: HIST.entries.length - n0 };
    // navstate (a home-screen launch without a hash): the hub tab comes back
    run(`localStorage.setItem('navstate',JSON.stringify({screen:'active',app:'Puzzle Quest',range:'today',t:Date.now(),hub:{in:true,tab:'active'}}))`);
    await fresh({ keepStore: true }); run(`_navRestore(); hubBoot();`); await settle(); const g = { ...S(), hash: LOC.hash };
    return { a, b, c, d, e, f, g, k }; });
  await step('switch_off_live', async () => { await fresh({ search: '?layout=hub' }); run(`hubGo('Demo Gallery','review')`); await settle(); run(`hubTab('active')`); await settle();
    const before = { ...S(), hash: LOC.hash };
    run(`hubToggle(false)`); await settle(); const after = { ...S(), hash: LOC.hash, ls: run(`localStorage.getItem('iq_layout')`) };
    run(`show('uninstall')`); await settle(); const later = { ...S(), hash: LOC.hash };
    run(`hubToggle(true)`); await settle(); const again = { ...S(), hash: LOC.hash };
    return { before, after, later, again }; });

  // ── App Overview cards ──────────────────────────────────────────────────────────────────────────────────────────────
  const K = run(`hubKeyOf('Demo Gallery')`), money = (usd, s) => ({ usd, s: s || '', sign: 0, p: 0 });
  ctx.__RVF = { v: 1, day: LAST, feats: [['kamai', 'Revenue · eCPM', 'Revenue', '💰'], ['uninstall', 'Uninstall', 'Uninstall', '🗑️'], ['active', 'Active users', 'Active', '👥'],
      ['value', 'Install value', 'Value', '💎'], ['update', 'Update impact', 'Update', '🔄'], ['ads', 'Ads', 'Ads', '📣'], ['deduct', 'Deductions', 'Deduct', '✂️'],
      ['mediation', 'Mediation', 'Mediation', '🔀'], ['health', 'Account health', 'Health', '🩺'], ['setup', 'Setup / data', 'Setup', '⚙️']],
    meta: { fx: 90 }, apps: [{ key: K, id: IDS.big, name: 'Demo Gallery', dname: 'Demo Gallery', head: { text: 'Show rate below range' }, f: {
      kamai: { st: 'amber', k: 'ad 71%', t: 'Splash show rate 71%, range 80%–84%', line: 'Splash show rate 71%, range 80%–84%' },
      uninstall: { st: 'normal', line: 'Same day uninstall 1,200 of 4,000 installs (30%)' },
      active: { st: 'red', k: '12%', line: 'Back after 3 days: 15% → 12%' },
      value: { st: 'green', k: '+20%', line: 'Money back in ~40 days' },
      update: { st: 'wait', line: 'v2.0 (3 Jan) · Too early' },
      ads: { st: 'na', line: 'No Google Ads spend' },
      deduct: { st: 'normal', line: ['', money(4.2), ' deducted by AdMob · under 0.1% of revenue'] },
      mediation: { st: 'normal', line: '2 networks · AdMob Network 95%' },
      health: { st: 'nodata' } } }] };
  const parse = html => [...html.matchAll(/<div class="card hub-fc" data-st="([a-z_]+)" data-fc="([a-z]+)">.*?<span class="hub-st st-([a-z_]+)">([^<]*)<\/span><div class="hfc-l">(.*?)<\/div><button type="button" class="hfc-o" onclick="hubTab\('([a-z]+)'\)"/g)]
    .map(m => ({ id: m[2], st: m[1], chip: m[4], line: m[5].replace(/<[^>]+>/g, ''), tab: m[6] }));
  await step('cards', async () => { await fresh({ search: '?layout=hub' }); run(`hubGo('Demo Gallery','overview')`); await settle();
    run(`HUB.rv.idx={open_day:'${LAST}',days:[{d:'${LAST}'}],studio:{}}; HUB.rv.idxAt=Date.now(); HUB.rv.files['${LAST}']=__RVF;
      APPR={placements:{'ca-app-pub-0000000000000001/1111111111':{},'ca-app-pub-0000000000000002/3333333333':{}}};
      AU.ptr=()=>({file:'audience.json.gz',v:'1'}); AU.ready=()=>true;
      AU._=Object.assign({},AU._,{prep(){}, keyOfName:n=>n==='Demo Gallery'?'k1':'!', BYK:()=>({k1:{sl:2600000,kam:false,a1:50000}}),
        stripReach:()=>({push:707000,dz:524000,ads:1300000}), CN:v=>v==null?'—':(v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?Math.round(v/1e3)+'K':String(v))});`);
    const usd = parse(run(`hubCardsHtml('Demo Gallery')`));
    run(`CURVIEW='INR'`); const inr = parse(run(`hubCardsHtml('Demo Gallery')`)); run(`CURVIEW=null`);
    const small = parse(run(`hubCardsHtml('Puzzle Quest')`));
    run(`HUB.rv.files={}; HUB.rv.idx=null; HUB.rv.loading=false;`); const none = parse(run(`hubCardsHtml('Demo Gallery')`));
    const head = run(`hubOvHtml('Demo Gallery')`).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
    const ov = run(`(()=>{ const s=document.createElement('section'); const r=hubOv(s); return {same:r===s, kids:s.children.length, id:s.children[0]&&s.children[0].id}; })()`);
    run(`APP=''`); const ovAll = run(`(()=>{ const s=document.createElement('section'); hubOv(s); return s.children.length; })()`);
    return { usd, inr, small, none, head, ov, ovAll, day: LAST }; });
})().then(() => { process.stdout.write(JSON.stringify({ errors, out })); }, e => { errors.push('MAIN ' + (e.stack || e.message)); process.stdout.write(JSON.stringify({ errors, out })); });
