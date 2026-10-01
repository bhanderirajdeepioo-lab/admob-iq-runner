// The header App picker (owner: "isme icon nahi aaya abhi tak") — the page side, run for real: the dashboard script
// (frontend/index.html's largest <script>) in a node vm with stub browser globals and a small DOM that keeps ids, focus,
// attributes and event listeners, on a SYNTHETIC dashboard made up here (two same-named "Demo Gallery" apps in two accounts,
// an app hidden in Accounts & Apps, a logo-less app, an app name with HTML characters). Drives the picker the way a user
// would (click, ↑/↓, Enter, Esc, Tab, typing, a click outside, a touch open) with setApp() swapped for a spy, and prints
// ONE JSON report; tests/test_app_picker_frontend.py asserts on it.
//   usage: node app_picker_frontend.js <script.js>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath] = process.argv.slice(2);
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// ── a small DOM: elements by id (made on first use), focus, attributes, classes, listeners ────────────────────────────
const ELS = {};
const doc = { activeElement: null, listeners: [] };
const unesc = s => String(s).replace(/&lt;/g, '<').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
function mk(id) {
  const cls = new Set();
  const el = {
    _id: '', _html: '', attrs: {}, hidden: false, value: '', textContent: '', listeners: [], parent: null, children: [],
    get id() { return this._id; }, set id(v) { this._id = String(v); ELS[this._id] = this; },
    classList: { add: (...a) => a.forEach(x => cls.add(x)), remove: (...a) => a.forEach(x => cls.delete(x)), contains: x => cls.has(x),
      toggle: (x, f) => { const on = f === undefined ? !cls.has(x) : !!f; on ? cls.add(x) : cls.delete(x); return on; } },
    get className() { return [...cls].join(' '); }, set className(v) { cls.clear(); String(v).split(/\s+/).filter(Boolean).forEach(x => cls.add(x)); },
    style: { _p: {}, setProperty(k, v) { this._p[k] = v; } }, dataset: {},
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); for (const m of this._html.matchAll(/\sid="([^"]+)"/g)) byId(m[1]).parent = this; },   // ids inside = its children
    // the hidden <select>: its options, parsed from what render() put in (appSelHtml)
    get options() { const o = []; const re = /<option value="([^"]*)"[^>]*>([^<]*)<\/option>/g; let m;
      while ((m = re.exec(this._html))) o.push({ value: unesc(m[1]), textContent: unesc(m[2]) }); return o; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(type, fn, cap) { this.listeners.push({ type, fn, cap: !!cap }); }, removeEventListener() {},
    appendChild(c) { c.parent = this; this.children.push(c); return c; },
    contains(t) { for (let n = t; n; n = n.parent) if (n === this) return true; return false; },
    focus() { doc.activeElement = this; }, blur() { if (doc.activeElement === this) doc.activeElement = null; this.fire('blur'); },
    querySelector: () => null, querySelectorAll: () => [], closest: () => null, scrollIntoView() {},
    getBoundingClientRect: () => ({ left: 880, top: 18, right: 1182, bottom: 52, width: 302, height: 34 }),
    fire(type, props) { const e = Object.assign({ type, target: this, detail: 1, ctrlKey: false, metaKey: false, altKey: false,
      defaultPrevented: false, stopped: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; } }, props || {});
      this.listeners.filter(l => l.type === type).forEach(l => l.fn(e)); return e; },
  };
  if (id) el.id = id;
  return el;
}
const byId = id => (ELS[id] = ELS[id] || mk(id));
// the topbar as the page has it: <label id="apk"> ⊃ #appsel-ic, <select id="appsel">, <button id="apk-btn"> ⊃ #apk-nm
const W = byId('apk'); ['appsel-ic', 'appsel', 'apk-btn'].forEach(i => W.appendChild(byId(i))); byId('apk-btn').appendChild(byId('apk-nm'));
const BODY = mk('');
const document = new Proxy({
  getElementById: byId, createElement: () => mk(''), body: BODY, head: mk(''), documentElement: mk(''),
  get activeElement() { return doc.activeElement; },
  querySelector: () => null, querySelectorAll: () => [],
  addEventListener: (type, fn, cap) => doc.listeners.push({ type, fn, cap: !!cap }), removeEventListener() {},
}, { get: (t, k) => (k in t ? t[k] : any) });
const store = () => { const b = {}; return { getItem: k => (k in b ? b[k] : null), setItem: (k, v) => { b[k] = String(v); }, removeItem: k => { delete b[k]; } }; };
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document, localStorage: store(), sessionStorage: store(), navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} }, history: any,
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, cancelAnimationFrame() {}, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean, RegExp,
  Error, TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat,
  encodeURIComponent, decodeURIComponent, performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 1280,
  innerHeight: 900, scrollY: 0, scrollTo() {}, alert() {}, confirm: () => false, prompt: () => null,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any, Node: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);

// ── a made-up dashboard (no real names, ids or URLs) ─────────────────────────────────────────────────────────────────
const A1 = 'pub-1000000000000001', A2 = 'pub-2000000000000002', id = (a, n) => `ca-app-${a}~00000000${n}`;
ctx.__DATA = {
  apps: [{ name: 'Demo Gallery · Alpha Studio' }, { name: 'Demo Gallery · pub-2000…' }, { name: 'Puzzle Quest' }, { name: 'Hidden Tool' },
         { name: 'Tom & Jerry "Run" <2>' }, { name: 'Very Long Name Calculator Pro Plus With Many Extra Words To Wrap Nicely' }],
  apps_catalog: [
    { account_id: A1, app_id: id(A1, 11), app_name: 'Demo Gallery · Alpha Studio', rev: 50 },
    { account_id: A2, app_id: id(A2, 12), app_name: 'Demo Gallery · pub-2000…', rev: 40 },
    { account_id: A1, app_id: id(A1, 13), app_name: 'Puzzle Quest', rev: 30 },
    { account_id: A2, app_id: id(A2, 14), app_name: 'Hidden Tool', rev: 5 },
    { account_id: A2, app_id: id(A2, 15), app_name: 'Tom & Jerry "Run" <2>', rev: 4 },
    { account_id: A2, app_id: id(A2, 16), app_name: 'Very Long Name Calculator Pro Plus With Many Extra Words To Wrap Nicely', rev: 3 }],
  app_icons: { [id(A1, 11)]: 'https://icons.example.test/g1.png', [id(A2, 12)]: 'https://icons.example.test/g2.png',
               [id(A1, 13)]: 'https://icons.example.test/pq.png', [id(A2, 15)]: 'https://icons.example.test/tj.png' },
  accounts: [{ account_id: A1, label: 'Main' }, { account_id: A2, label: 'Second' }],
};
ctx.__A2 = A2; ctx.__HIDE = [id(A2, 12), id(A2, 15), id(A2, 16)];   // A2 keeps 3 of its 4 apps: "Hidden Tool" is hidden
ctx.__CALLS = [];
run(`DATA=__DATA; ACCNAMES={'${A1}':'Alpha Studio'}; APPSEL={accounts:{[__A2]:{decided:true,selected:__HIDE}}}; APP='';
  // render()'s header sync (appSelSync), then the spy: setApp(name) records the name and refreshes the header the same way
  var __hdr=()=>appSelSync();
  setApp=function(a){ __CALLS.push(a); APP=a; __hdr(); };
  __hdr(); apkWire(); apkWire();`);   // wired twice on purpose: the second call must be a no-op

const $ = byId, out = {};
const S = () => ({ open: run('APK.open'), hidden: $('apk-pop').hidden, exp: $('apk-btn').getAttribute('aria-expanded'),
  focus: doc.activeElement ? doc.activeElement.id : null, list: $('apk-list').innerHTML, ad: $('apk-q').getAttribute('aria-activedescendant'),
  ad_list: $('apk-list').getAttribute('aria-activedescendant'), q: $('apk-q').value, none_hidden: $('apk-none').hidden,
  nm: $('apk-nm').textContent, label: $('apk-btn').getAttribute('aria-label'), APP: run('APP'), sel: $('appsel').value,
  calls: run('__CALLS.slice()'), quiet: $('apk-btn').classList.contains('apk-quiet'), act: run('APK.act'), rows: run('APK.rows.slice()') });
const optTarget = i => ({ closest: () => ({ getAttribute: k => (k === 'data-i' ? String(i) : null) }) });
const step = (name, fn) => { try { out[name] = fn(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };
const key = (el, k, extra) => el.fire('keydown', Object.assign({ key: k }, extra || {}));
const reset = () => { run('APK.open&&apkClose(false); __CALLS.length=0;'); doc.activeElement = null; };

step('wired', () => ({ pop_children: BODY.children.length, pop_id: BODY.children[0] && BODY.children[0].id,
  pop_html: BODY.children[0] && BODY.children[0].innerHTML, select_opts: $('appsel').options }));
step('closed', () => S());
step('open_click', () => { $('apk-btn').fire('click', { detail: 1 }); return S(); });
step('search_alpha', () => { $('apk-q').value = 'alpha'; $('apk-q').fire('input'); return S(); });
step('search_puzzle', () => { $('apk-q').value = '  PUZZLE '; $('apk-q').fire('input'); return S(); });
step('search_two_words', () => { $('apk-q').value = 'second gallery'; $('apk-q').fire('input'); return S(); });
step('search_none', () => { $('apk-q').value = 'zzqx'; $('apk-q').fire('input'); const s = S(); const e = key($('apk-box'), 'Enter'); s.enter_prevented = e.defaultPrevented; s.after = S(); return s; });
step('search_cleared', () => { $('apk-q').value = ''; $('apk-q').fire('input'); return S(); });
step('keys', () => { const box = $('apk-box'), o = {};
  key(box, 'ArrowUp'); o.up_at_top = run('APK.act');
  key(box, 'ArrowDown'); key(box, 'ArrowDown'); o.after_two_down = S();
  key(box, 'PageDown'); o.pagedown_clamps = run('APK.act') === run('APK.rows.length') - 1;
  key(box, 'PageUp'); o.pageup_clamps = run('APK.act');
  key(box, 'ArrowDown'); key(box, 'ArrowDown');
  o.want = run('APK.items[APK.rows[APK.act]].v');
  const e = key(box, 'Enter'); o.enter_prevented = e.defaultPrevented; o.after = S(); return o; });
step('esc', () => { reset(); $('apk-btn').focus(); key($('apk-btn'), 'ArrowDown'); const o = { opened: S() };
  key($('apk-box'), 'ArrowDown'); const e = key($('apk-box'), 'Escape'); o.prevented = e.defaultPrevented; o.stopped = e.stopped; o.after = S(); return o; });
step('click_pick', () => { reset(); $('apk-btn').fire('click', { detail: 1 }); const o = { opened: S() };
  o.want = run('APK.items[3].v'); $('apk-list').fire('mousemove', { target: optTarget(3) }); o.hover_act = S().ad;
  const md = $('apk-list').fire('mousedown', { target: optTarget(3) }); o.mousedown_prevented = md.defaultPrevented;
  $('apk-list').fire('click', { target: optTarget(3) }); o.after = S(); return o; });
step('same_app', () => { reset(); $('apk-btn').fire('click', { detail: 1 }); const k = run('APK.act');
  $('apk-list').fire('click', { target: optTarget(run('APK.rows[APK.act]')) }); return { k, after: S() }; });
step('all_apps', () => { reset(); $('apk-btn').fire('click', { detail: 1 }); const o = { opened: S() };
  $('apk-list').fire('click', { target: optTarget(0) }); o.after = S(); return o; });
step('type_on_button', () => { reset(); $('apk-btn').focus(); const e = key($('apk-btn'), 'q'); const o = S(); o.prevented = e.defaultPrevented; o.stopped = e.stopped;
  const sp = key($('apk-btn'), ' '); o.space_prevented = sp.defaultPrevented; return o; });   // Space while open: not ours
step('tab', () => { const e = key($('apk-box'), 'Tab'); const o = S(); o.prevented = e.defaultPrevented; return o; });
step('outside', () => { reset(); $('apk-btn').fire('click', { detail: 1 }); const o = {};
  const fireDoc = t => doc.listeners.filter(l => l.type === 'pointerdown').forEach(l => l.fn({ type: 'pointerdown', target: t }));
  fireDoc($('apk-q')); o.inside = S().open; fireDoc($('apk-nm')); o.on_button = S().open;
  fireDoc(mk('elsewhere')); o.after = S(); o.capture = doc.listeners.some(l => l.type === 'pointerdown' && l.cap); return o; });
step('scrim', () => { reset(); $('apk-btn').fire('click', { detail: 1 }); $('apk-scrim').fire('click'); return S(); });
step('toggle_btn', () => { reset(); $('apk-btn').fire('click', { detail: 1 }); $('apk-btn').fire('click', { detail: 1 }); return S(); });
step('touch_open', () => { reset(); $('apk').fire('pointerdown', { pointerType: 'touch' }); $('apk-btn').fire('click', { detail: 1 }); const o = S();
  key($('apk-box'), 'g', { target: $('apk-list') }); /* a key on the list bubbles to the box */ o.type_goes_to_search = doc.activeElement && doc.activeElement.id; return o; });
step('keyboard_open_after_touch', () => { reset(); run('APK.ptT=0'); $('apk-btn').fire('click', { detail: 0 }); return S(); });
step('refresh_while_open', () => { reset(); $('apk-btn').fire('click', { detail: 1 }); key($('apk-box'), 'ArrowDown'); key($('apk-box'), 'ArrowDown');
  const was = run('APK.items[APK.rows[APK.act]].v'); run('__hdr()'); return { was, now: run('APK.items[APK.rows[APK.act]].v'), open: run('APK.open') }; });
step('ghost', () => { reset(); run(`APP='Ghost App'; __hdr();`); $('apk-btn').fire('click', { detail: 1 }); const o = S(); reset(); run(`APP=''; __hdr();`); return o; });
step('place', () => { reset(); $('apk-btn').fire('click', { detail: 1 }); const p = Object.assign({}, $('apk-pop').style._p); reset(); return p; });
process.stdout.write(JSON.stringify({ errors, out }));
