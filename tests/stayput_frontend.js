// "Stay put" (frontend/index.html's SP layer) — owner, on his iPhone: "kuchh change karte he to upar chala jata he page"
// (change something and the page goes back up). The layer, taken out of the page script as it is, runs here in a node vm
// on a small SYNTHETIC page: elements with a document position (top), a window that scrolls (scrollY, clamped to the page),
// capture / bubble listeners on window, timers and animation frames run by hand. Each scenario taps (pointerdown + click,
// or a change) a control whose "handler" rebuilds the screen the way the dashboard does (new nodes, content above grown,
// the page thrown to the top as iOS Safari does) and reports where the control ended up on screen.
//   usage: node stayput_frontend.js <index.html>
// Prints ONE JSON report; tests/test_stayput_frontend.py asserts on it. No real data: every label is made up.
'use strict';
const fs = require('fs'), vm = require('vm');
const [htmlPath] = process.argv.slice(2);
const errors = [];
const page = fs.readFileSync(htmlPath, 'utf8');
const a = page.indexOf('const SP=(function(){'), b = page.indexOf('\n  return api;\n})();', a);
if (a < 0 || b < 0) { process.stdout.write(JSON.stringify({ errors: ['SP module not found'], out: {} })); process.exit(0); }
const SRC = page.slice(a, b + '\n  return api;\n})();'.length) + '\nglobalThis.__SP=SP;';

// ── a small DOM with layout: every element has a document top + height; the window scrolls over it ──────────────────
const W = { scrollY: 0, innerHeight: 800, innerWidth: 400, docH: 6000 };
const clampY = y => Math.max(0, Math.min(y, W.docH - W.innerHeight));
let ROOT = null;
class El {
  constructor(tag, attrs, kids) {
    this.tagName = String(tag).toUpperCase(); this.nodeType = 1; this._a = []; this.children = []; this.parentElement = null;
    this.top = 0; this.h = 30; this.text = ''; this.style = {}; this.scrollHeight = 0; this.clientHeight = 0;
    for (const [k, v] of Object.entries(attrs || {})) { if (k === 'text') this.text = v; else if (k === 'top') this.top = v; else if (k === 'style') this.style = v; else this._a.push([k, String(v)]); }
    (kids || []).forEach(k => this.append(k));
  }
  get attributes() { return this._a.map(([name, value]) => ({ name, value })); }
  getAttribute(k) { const x = this._a.find(p => p[0] === k); return x ? x[1] : null; }
  setAttribute(k, v) { const x = this._a.find(p => p[0] === k); if (x) x[1] = String(v); else this._a.push([k, String(v)]); }
  get classList() { const c = String(this.getAttribute('class') || '').split(/\s+/).filter(Boolean); return { contains: x => c.includes(x) }; }
  get dataset() { const d = {}; for (const [k, v] of this._a) if (k.startsWith('data-')) d[k.slice(5).replace(/-([a-z])/g, (m, ch) => ch.toUpperCase())] = v; return d; }
  get type() { return this.getAttribute('type') || (this.tagName === 'INPUT' ? 'text' : ''); }
  get textContent() { return this.text + this.children.map(c => c.textContent).join(''); }
  append(c) { c.parentElement = this; this.children.push(c); return c; }
  remove() { const p = this.parentElement; if (p) { p.children.splice(p.children.indexOf(this), 1); this.parentElement = null; } }
  replaceChildren(...cs) { this.children.forEach(c => { c.parentElement = null; }); this.children = []; cs.forEach(c => this.append(c)); }
  contains(x) { for (; x; x = x.parentElement) if (x === this) return true; return false; }
  get isConnected() { let x = this; while (x.parentElement) x = x.parentElement; return x === ROOT; }
  getElementsByTagName(t) { const T = String(t).toUpperCase(), out = []; const walk = e => e.children.forEach(c => { if (c.tagName === T) out.push(c); walk(c); }); walk(this); return out; }
  getBoundingClientRect() {   // fixed / sticky: where the style says, whatever the scroll; else document top − scrollY
    if (!this.isConnected) return { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 };
    let fx = null; for (let x = this; x; x = x.parentElement) if (x.style.position === 'fixed' || x.style.position === 'sticky') { fx = x; break; }
    const top = fx ? (fx === this ? 0 : this.top - fx.top) + (parseFloat(fx.style.top) || 0) : this.top - W.scrollY;
    return { top, bottom: top + this.h, left: 0, right: 100, width: 100, height: this.h };
  }
  scrollIntoView() { W.scrollY = clampY(this.top); }
}
const el = (tag, attrs, kids) => new El(tag, attrs, kids);
const ON = { cap: {}, bub: {} };
const Q = { t: [], raf: [], now: 0 };
const document = {
  get body() { return ROOT.children[1]; }, get documentElement() { return { scrollHeight: W.docH }; },
  querySelector: sel => { if (sel !== '.screen.on') return null; let hit = null; const walk = e => e.children.forEach(c => { if (!hit && c.classList.contains('screen') && c.classList.contains('on')) hit = c; walk(c); }); walk(ROOT); return hit; },
};
const win = {
  get scrollY() { return W.scrollY; }, get innerHeight() { return W.innerHeight; }, get innerWidth() { return W.innerWidth; },
  scrollTo(x, y) { const t = (x && typeof x === 'object') ? x.top : y; W.scrollY = clampY(t); },
  scrollBy(x, y) { const d = (x && typeof x === 'object') ? x.top : y; W.scrollY = clampY(W.scrollY + d); },
  scroll(x, y) { win.scrollTo(x, y); },
  addEventListener(t, f, o) { const cap = o === true || !!(o && o.capture); (cap ? ON.cap : ON.bub)[t] = ((cap ? ON.cap : ON.bub)[t] || []).concat(f); },
};
const ctx = {
  window: win, document, Element: El, Date: { now: () => Q.now }, Math, JSON, Array, Object, String, Number, isFinite, Promise, RegExp, Error,
  getComputedStyle: e => ({ position: e.style.position || 'static', top: e.style.top || 'auto', overflowY: e.style.overflowY || 'visible' }),
  setTimeout: (f, ms) => { Q.t.push({ at: Q.now + (ms || 0), f }); return Q.t.length; },
  requestAnimationFrame: f => { Q.raf.push(f); return Q.raf.length; },
  APP: '',
};
ctx.globalThis = ctx;
vm.createContext(ctx);
try { vm.runInContext(SRC, ctx, { filename: 'stayput.js' }); } catch (e) { errors.push('LOAD ' + e.message); }
const SP = ctx.__SP;
const micro = () => new Promise(r => setImmediate(r));
// time passes: microtasks, then frames (each frame may queue the next), then timers in order
async function advance(ms) {
  await micro();
  for (let i = 0; i < 4 && Q.raf.length; i++) { const fs2 = Q.raf.splice(0); fs2.forEach(f => f()); await micro(); }
  const end = Q.now + ms;
  for (;;) { Q.t.sort((p, q) => p.at - q.at); const n = Q.t[0]; if (!n || n.at > end) break; Q.t.shift(); Q.now = n.at; n.f(); await micro();
    for (let i = 0; i < 4 && Q.raf.length; i++) { const fs2 = Q.raf.splice(0); fs2.forEach(f => f()); await micro(); } }
  Q.now = end;
}
// an event: window capture listeners → the page's handler (the target's) → window bubble listeners
function dispatch(type, target, extra, handler) {
  const e = Object.assign({ type, target, isTrusted: true, preventDefault() {}, stopPropagation() {} }, extra || {});
  (ON.cap[type] || []).forEach(f => f(e)); if (handler) handler(e); (ON.bub[type] || []).forEach(f => f(e));
}
async function tap(target, handler, opts) { opts = opts || {};
  dispatch('pointerdown', target); Q.now += 60;
  if (opts.between) opts.between();
  dispatch('click', target, null, handler);
  if (opts.after) opts.after();
  await advance(opts.ms || 500); }

// ── the synthetic page: a sticky top bar, two screens, a fixed drawer ─────────────────────────────────────────────────
function chip(k, top, text) { return el('button', { type: 'button', class: 'chip', 'data-k': k, top, text: text || 'Chip ' + k }); }
function screenKids(shift) {   // the same view, drawn again; `shift` px more content above the chips
  return [el('div', { class: 'card', top: 100, text: 'Intro' }),
    el('div', { class: 'card', top: 2000 + shift }, [chip('a', 2900 + shift), chip('b', 2900 + shift, 'Chip b'), el('button', { top: 3100 + shift, text: 'Show all' })]),
    el('select', { id: 'pick', top: 3300 + shift }),
    el('input', { type: 'text', id: 'q', top: 3400 + shift }),
    el('div', { class: 'box', top: 3500 + shift, style: { overflowY: 'auto' } }, [el('div', { 'data-row': '1', top: 3520 + shift, text: 'row 1' })])];
}
let SCR, SCR2, BAR, CUR, DRAWER, DBTN;
function build() {
  CUR = el('button', { id: 'curtoggle', onclick: 'toggleCur()', top: 10, text: '$' });
  BAR = el('div', { class: 'topbar', top: 0, style: { position: 'sticky', top: '0px' } }, [CUR]);
  SCR = el('section', { class: 'screen on', 'data-screen': 'one' }, screenKids(0));
  SCR2 = el('section', { class: 'screen', 'data-screen': 'two' }, [el('div', { top: 100 })]);
  DBTN = el('button', { 'data-d': '1', top: 50, text: 'In drawer' });
  DRAWER = el('div', { class: 'drawer', style: { position: 'fixed', top: '0px' } }, [DBTN]);
  const body = el('body', {}, [BAR, el('main', {}, [SCR, SCR2]), DRAWER]);
  ROOT = el('html', {}, [el('head'), body]);
  ctx.APP = ''; W.docH = 6000;
}
const q = (root, pred) => { let hit = null; const walk = e => e.children.forEach(c => { if (!hit && pred(c)) hit = c; walk(c); }); walk(root); return hit; };
const chipA = () => q(SCR, x => x.getAttribute('data-k') === 'a');
const onScreen = x => Math.round(x.getBoundingClientRect().top);
const out = {};
const step = async (name, fn) => { try { build(); W.scrollY = 0; Q.t = []; Q.raf = []; Q.now += 5000; out[name] = await fn(); } catch (e) { errors.push(name + ': ' + (e.stack || e.message)); } };
// the dashboard's re-render on iOS: the screen rebuilt (new nodes, 172px more above), the page thrown to the top
const rebuildJump = (shift) => () => { SCR.replaceChildren(...screenKids(shift == null ? 172 : shift)); W.scrollY = 0; };

(async () => {
  await step('rebuild_restored', async () => {
    W.scrollY = 2600; const before = onScreen(chipA());
    await tap(chipA(), rebuildJump());
    return { before, after: onScreen(chipA()), y: W.scrollY, sameNode: false };
  });
  await step('restored_without_a_timer', async () => {   // the check right after the handlers (microtask) already fixes it
    W.scrollY = 2600; const before = onScreen(chipA());
    dispatch('pointerdown', chipA()); dispatch('click', chipA(), null, rebuildJump()); await micro();
    return { before, after: onScreen(chipA()), pendingRaf: Q.raf.length };
  });
  await step('late_shift_at_150ms', async () => {   // iOS settles late: the content above grows 100 ms after the tap
    W.scrollY = 2600; const before = onScreen(chipA());
    await tap(chipA(), () => { ctx.setTimeout(() => { SCR.replaceChildren(...screenKids(300)); }, 100); });
    return { before, after: onScreen(chipA()) };
  });
  await step('intentional_scrollTo_kept', async () => {   // a drill-down / "Open →" / Back: the code scrolls on purpose
    W.scrollY = 2600;
    await tap(chipA(), () => { rebuildJump()(); win.scrollTo({ top: 0 }); });
    return { y: W.scrollY, intent: SP.st.intent > 0 };
  });
  await step('intentional_scrollIntoView_kept', async () => {
    W.scrollY = 2600; let target = null;
    await tap(chipA(), () => { rebuildJump()(); target = q(SCR, x => x.getAttribute('class') === 'box'); target.scrollIntoView(); });
    return { y: W.scrollY, want: target ? Math.min(target.top, W.docH - W.innerHeight) : null };
  });
  await step('reader_scrolls_after_tap', async () => {   // a touchmove / wheel after the tap: never fight the reader
    W.scrollY = 2600;
    await tap(chipA(), () => { ctx.setTimeout(() => { SCR.replaceChildren(...screenKids(300)); }, 100); },
      { after: () => { ctx.setTimeout(() => { (ON.cap.touchmove || []).forEach(f => f({ type: 'touchmove' })); W.scrollY = 1234; }, 120); } });
    return { y: W.scrollY };
  });
  await step('wheel_cancels', async () => {
    W.scrollY = 2600;
    await tap(chipA(), () => { rebuildJump()(); (ON.cap.wheel || []).forEach(f => f({ type: 'wheel' })); W.scrollY = 777; });
    return { y: W.scrollY };
  });
  await step('screen_changed', async () => {   // another screen came on: real navigation
    W.scrollY = 2600;
    await tap(chipA(), () => { SCR.setAttribute('class', 'screen'); SCR2.setAttribute('class', 'screen on'); W.scrollY = 0; });
    return { y: W.scrollY };
  });
  await step('app_changed', async () => {
    W.scrollY = 2600;
    await tap(chipA(), () => { ctx.APP = 'Demo App'; rebuildJump()(); });
    return { y: W.scrollY };
  });
  await step('control_gone', async () => {   // the view under it changed (a drill-down without a scroll call): leave it
    W.scrollY = 2600;
    await tap(chipA(), () => { SCR.replaceChildren(el('div', { top: 100, text: 'Another view' })); W.scrollY = 500; });
    return { y: W.scrollY };
  });
  await step('small_move_left', async () => {   // ≤ 3px is not a jump
    W.scrollY = 2600; const before = onScreen(chipA());
    await tap(chipA(), () => { SCR.replaceChildren(...screenKids(2)); });
    return { before, after: onScreen(chipA()), y: W.scrollY };
  });
  await step('same_node_moved', async () => {   // nothing rebuilt, only content above it grew (a fold opened above)
    W.scrollY = 2600; const before = onScreen(chipA());
    await tap(chipA(), () => { const c = chipA(); c.top += 240; c.parentElement.top += 240; });
    return { before, after: onScreen(chipA()) };
  });
  await step('path_signature', async () => {   // a plain <button> (no id / data / onclick): found again by its path + text
    W.scrollY = 2800; const btn = () => q(SCR, x => x.tagName === 'BUTTON' && x.text === 'Show all'); const before = onScreen(btn());
    await tap(btn(), rebuildJump(400));
    return { before, after: onScreen(btn()) };
  });
  await step('state_in_onclick', async () => {   // a fold header whose onclick says open ⇄ closed: found again by its path + text
    const hdr = (st, top) => el('div', { class: 'imp-h', onclick: `fold('${st}')`, top, text: '▸ Update 2 Jun' });
    SCR.replaceChildren(el('div', { top: 1000 }, [hdr('k1', 2900), el('div', { top: 2950, text: 'details' })]));
    W.scrollY = 2600; const h = () => q(SCR, x => x.getAttribute('class') === 'imp-h'); const before = onScreen(h());
    await tap(h(), () => { SCR.replaceChildren(el('div', { top: 1000 }, [hdr('-', 1789), el('div', { top: 1840, text: 'details' })])); });
    return { before, after: onScreen(h()) };
  });
  await step('twin_chips_by_index', async () => {   // two controls with the same signature: the one tapped, by its index
    W.scrollY = 2600; const twins = () => [el('button', { 'data-x': 'same', top: 2900, text: 'one' }), el('button', { 'data-x': 'same', top: 2950, text: 'two' })];
    SCR.replaceChildren(...twins());
    const second = () => SCR.children[1]; const before = onScreen(second());
    await tap(second(), () => { SCR.replaceChildren(...twins().map(t => { t.top += 500; return t; })); W.scrollY = 0; });
    return { before, after: onScreen(second()) };
  });
  await step('top_bar_keeps_scrollY', async () => {   // ₹/$ in the sticky top bar: the page shrinks, rebuilds, keeps scrollY
    W.scrollY = 2600;
    await tap(CUR, () => { SCR.replaceChildren(); W.scrollY = 0; SCR.replaceChildren(...screenKids(0)); });
    return { y: W.scrollY };
  });
  await step('fixed_layer_left_alone', async () => {   // a control in a drawer / sheet: not the page's business
    W.scrollY = 2600;
    await tap(DBTN, () => { W.scrollY = 100; });
    return { y: W.scrollY };
  });
  await step('select_change', async () => {   // a <select>: no click arm; its change keeps it in place
    W.scrollY = 3000; const sel = () => q(SCR, x => x.getAttribute('id') === 'pick'); const before = onScreen(sel());
    dispatch('click', sel()); Q.now += 900;
    dispatch('change', sel(), null, rebuildJump()); await advance(500);
    return { before, after: onScreen(sel()) };
  });
  await step('text_field_ignored', async () => {   // the phone keyboard scrolls a text field into view on purpose
    W.scrollY = 3000; const inp = () => q(SCR, x => x.getAttribute('id') === 'q');
    await tap(inp(), () => { W.scrollY = 3200; });
    return { y: W.scrollY };
  });
  await step('scroll_box_anchor', async () => {   // a row inside a box that scrolls on its own: the box is kept in place
    const box = () => q(SCR, x => x.getAttribute('class') === 'box'); box().scrollHeight = 900; box().clientHeight = 300;
    W.scrollY = 3200; const row = q(SCR, x => x.getAttribute('data-row') === '1'); const before = onScreen(box());
    await tap(row, () => { rebuildJump(250)(); const b2 = box(); b2.scrollHeight = 900; b2.clientHeight = 300; });
    return { before, after: onScreen(box()) };
  });
  await step('keyboard_enter', async () => {   // Enter on a chip: armed by the keydown, its click is the same tap
    W.scrollY = 2600; const before = onScreen(chipA());
    dispatch('keydown', chipA(), { key: 'Enter' }); dispatch('click', chipA(), { isTrusted: true }, rebuildJump()); await advance(500);
    return { before, after: onScreen(chipA()) };
  });
  await step('stale_pointerdown_not_used', async () => {   // finger down, a scroll (touchmove), finger up elsewhere: no old snapshot
    W.scrollY = 2600;
    dispatch('pointerdown', chipA()); (ON.cap.touchmove || []).forEach(f => f({ type: 'touchmove' })); W.scrollY = 2000; Q.now += 300;
    const before = onScreen(chipA());
    dispatch('click', chipA(), null, rebuildJump()); await advance(500);
    return { before, after: onScreen(chipA()) };
  });
  await step('keepY', async () => {   // rerender(): back to the reader's place, clamped to the new page; not "intentional"
    const i0 = SP.st.intent; W.scrollY = 0; W.docH = 9000; SP.keepY(2500); const a1 = W.scrollY;
    W.scrollY = 0; W.docH = 2000; SP.keepY(2500); const a2 = W.scrollY; const quiet = SP.st.intent === i0;
    win.scrollTo(0, 10); const i1 = SP.st.intent;
    return { a1, a2, quiet, intentAfterCodeScroll: i1 > i0 };
  });
  await step('wrapped', () => ({ to: !!win.scrollTo.__sp, by: !!win.scrollBy.__sp, sc: !!win.scroll.__sp, siv: !!El.prototype.scrollIntoView.__sp }));
  process.stdout.write(JSON.stringify({ errors, out }));
})().catch(e => { errors.push('MAIN ' + (e.stack || e.message)); process.stdout.write(JSON.stringify({ errors, out })); });
