// "Stay put" (frontend/index.html's SP layer) — owner, on his iPhone: "kuchh change karte he to upar chala jata he page"
// (change something and the page goes back up). The layer, taken out of the page script as it is, runs here in a node vm
// on a small SYNTHETIC page: elements with a document position (top), a window that scrolls (scrollY, clamped to the page),
// capture / bubble listeners on window, timers and animation frames run by hand. Each scenario taps (pointerdown + click,
// or a change) a control whose "handler" rebuilds the screen the way the dashboard does (new nodes, content above grown,
// the page thrown to the top as iOS Safari does) and reports where the control ended up on screen.
//   usage: node stayput_frontend.js <index.html> [ecpm_ctl.json]
//   ecpm_ctl.json: the eCPM tables' REAL control rows before / after each tap (tests/ecpm_frontend.js … ctl), replayed here.
// Prints ONE JSON report; tests/test_stayput_frontend.py asserts on it. No real data: every label is made up.
'use strict';
const fs = require('fs'), vm = require('vm');
const [htmlPath, ctlPath] = process.argv.slice(2);
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
  // 🧪 two cards with the same controls one under the other (ROI's "Every install day" card and its Benchmark copy, 22 Oct
  // 2026): a control of the SECOND card, the view rebuilt with more above it → back where it was (its index among twins)
  const all = (root, pred) => { const hit = []; const walk = e => e.children.forEach(c => { if (pred(c)) hit.push(c); walk(c); }); walk(root); return hit; };
  const ccx = (v, top) => el('button', { type: 'button', class: 'roi-lnk roi-ccx', 'data-roi-ccx': v, top, text: '✕ All countries' });
  const twinCards = (shift, xa, xb) => [el('div', { top: 100, text: 'chart' }),
    el('div', { class: 'roi-card', id: 'roi-coh', top: 1500 }, [el('h3', { top: 1500, text: 'Every install day' })].concat(xa ? [ccx(xa, 1510)] : [],
      [el('button', { type: 'button', 'data-roi-grain': 'week', top: 1600, text: 'Week' })])),
    el('div', { class: 'roi-card', id: 'roi-bmk', top: 2600 + shift }, [el('h3', { top: 2600 + shift, text: 'Benchmark · Every install day' })].concat(xb ? [ccx(xb, 2610 + shift)] : [],
      [el('button', { type: 'button', 'data-roi-grain': 'week', top: 2700 + shift, text: 'Week' })]))];
  await step('twin_cards_second', async () => {
    SCR.replaceChildren(...twinCards(0)); W.scrollY = 2300;
    const wk = () => all(SCR, x => x.getAttribute('data-roi-grain') === 'week'); const before = onScreen(wk()[1]);
    await tap(wk()[1], () => { SCR.replaceChildren(...twinCards(180)); W.scrollY = 0; });
    return { before, after: onScreen(wk()[1]), n: wk().length };
  });
  // a ✕ that goes with the tap while the OTHER card still shows its own ✕: with one mark on both, the layer takes the other
  // card's for it and scrolls the page there (the hazard: twin_gone_same_mark); the Benchmark's ✕ carries its own mark
  // ("b"): no twin, the page stays (twin_gone_marked) — and the cohort card's ✕ the same way round
  const gone = (xa, xb, tapB) => async () => {
    SCR.replaceChildren(...twinCards(0, xa, xb)); W.scrollY = tapB ? 2300 : 1200;
    const x = all(SCR, e => e.getAttribute('data-roi-ccx') != null)[tapB ? 1 : 0];
    await tap(x, () => { SCR.replaceChildren(...twinCards(0, tapB ? xa : null, tapB ? null : xb)); });
    return { y: W.scrollY, want: tapB ? 2300 : 1200 };
  };
  await step('twin_gone_marked', gone('1', 'b', true));
  await step('twin_gone_marked_coh', gone('1', 'b', false));
  await step('twin_gone_same_mark', gone('1', '1', true));
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
  // 📈 the eCPM tables' comparison row (the page's own attributes): a tap repaints the whole view (ecPaint) — the title above
  // the row can grow a line, the ‹ › / chip can turn disabled, the twin rows (Ad units + Countries cards) are both rebuilt
  const ecCtl = (top, mode, hiOff) => el('div', { class: 'ec-cmp', top }, [
    el('div', { class: 'ec-seg', role: 'group', 'aria-label': 'Compare', top }, [
      el('button', { type: 'button', class: mode === 'y' ? 'on' : '', 'aria-pressed': String(mode === 'y'), onclick: "ecCmpM('y')", top, text: 'Yesterday vs' }),
      el('button', { type: 'button', class: mode === 'm' ? 'on' : '', 'aria-pressed': String(mode === 'm'), onclick: "ecCmpM('m')", top, text: 'Month vs month' })]),
    el('div', { class: 'ec-mnav', top }, [
      el('button', { type: 'button', class: 'ec-ma', onclick: 'ecCmpMon(-1)', 'aria-label': 'Previous month', top, text: '‹' }),
      el('span', { class: 'ec-ml', top, text: mode === 'm' ? 'Mar 2026 (1–10) vs Feb 2026' : 'Feb 2026' }),
      el('button', Object.assign({ type: 'button', class: 'ec-ma', onclick: 'ecCmpMon(1)', 'aria-label': 'Next month', top, text: '›' }, hiOff ? { disabled: '' } : {}))])]);
  const ecView = (grow, mode, hiOff) => [el('div', { top: 100, text: 'chart' }),
    el('div', { class: 'card ec-tc', top: 1800 }, [el('h3', { top: 1800, text: 'Ad units' }), ecCtl(1840 + grow, mode, hiOff)]),
    el('div', { class: 'card ec-tc', top: 2600 + grow }, [el('h3', { top: 2600 + grow, text: 'Countries' }), ecCtl(2640 + 2 * grow, mode, hiOff)])];
  await step('ecpm_cmp_twin_arrow', async () => {   // the Countries card's › (the 2nd of two), now the newest month: disabled
    SCR.replaceChildren(...ecView(0, 'y', false)); W.scrollY = 2400;
    const nx = () => all(SCR, x => x.getAttribute('onclick') === 'ecCmpMon(1)'); const before = onScreen(nx()[1]);
    await tap(nx()[1], () => { SCR.replaceChildren(...ecView(22, 'y', true)); W.scrollY = 0; });
    return { before, after: onScreen(nx()[1]), n: nx().length, disabled: nx()[1].getAttribute('disabled') === '' };
  });
  await step('ecpm_cmp_mode_chip', async () => {   // "Month vs month" in the Ad units card: the row's content changes, the chip stays
    SCR.replaceChildren(...ecView(0, 'y', false)); W.scrollY = 1500;
    const ch = () => all(SCR, x => x.getAttribute('onclick') === "ecCmpM('m')"); const before = onScreen(ch()[0]);
    await tap(ch()[0], () => { SCR.replaceChildren(...ecView(19, 'm', true)); W.scrollY = 0; });
    return { before, after: onScreen(ch()[0]), y: W.scrollY };
  });
  // 📈 the same, from the page's REAL control rows (tests/ecpm_frontend.js "ctl" mode: each table card's head before / after a
  // tap — title, chips, ‹ label ›), laid out by a small flex-wrap model at 375 px and 1280 px: the title can wrap to another
  // line, the row can wrap differently (Month adds ‹ ›, Month vs month drops the baseline chips for its two pickers
  // "‹ current › vs ‹ compared ›", the second wrapping as one piece), the twin Countries card moves with the one above it.
  // The tapped control (found by its onclick, the n-th of its twins) must come back where it was.
  if (ctlPath) {
    const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'" };
    const dec = t => String(t).replace(/&(amp|lt|gt|quot|#39);/g, (m, k) => ENT[k]);
    function parse(h) {   // the subset the cards use: div / span / b / h3 / button, attributes in double quotes or bare
      const root = el('div', {}), st = [root], re = /<(\/?)([a-zA-Z0-9]+)([^>]*)>|([^<]+)/g; let m;
      while ((m = re.exec(h))) {
        if (m[4] !== undefined) { const t = dec(m[4]).replace(/\s+/g, ' '); if (t.trim()) st[st.length - 1].text += t; continue; }
        const tag = m[2].toUpperCase();
        if (m[1]) { for (let i = st.length - 1; i > 0; i--) if (st[i].tagName === tag) { st.length = i; break; } continue; }
        const at = {}, ar = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:="([^"]*)")?/g; let a;
        while ((a = ar.exec(m[3]))) if (a[1] !== 'style') at[a[1]] = a[2] === undefined ? '' : dec(a[2]);
        const e = el(tag, at); st[st.length - 1].append(e); if (tag !== 'BR' && tag !== 'IMG' && tag !== 'INPUT') st.push(e); }
      return root.children.slice(); }
    const cls = (x, c) => x.classList.contains(c), kids = x => x.children, setTop = (x, t) => { x.top = t; kids(x).forEach(k => setTop(k, t)); };
    // the page's CSS, as numbers: ≤ 430 px chips 12px / 9px padding, ≤ 760 px 40px-high row items, ‹ › 40 / 36 px, label 11.2em.
    // Each control row laid out is noted in ROWS: its lines, and whether an item that cannot shrink is wider than the card
    let ROWS = [];
    function layoutHead(nodes, top, VW) {
      const phone = VW <= 760, IW = (phone ? VW - 24 : Math.min(VW - 300, 1200)) - 32, H = phone ? 40 : 36;
      const cw = VW <= 430 ? 6.6 : 6.9, pad = VW <= 430 ? 9 : (phone ? 11 : 12), bw = t => 2 * pad + String(t).length * cw + 1;
      let y = top;
      for (const n of nodes) {
        if (cls(n, 'ct')) {   // title + hint: one line if both fit, else wrapped
          const h3 = n.children.find(k => k.tagName === 'H3'), hint = n.children.find(k => k.tagName === 'SPAN');
          const tw = h3 ? h3.textContent.length * 8.4 : 0, hw = hint ? hint.textContent.length * 6 : 0;
          const l3 = Math.max(1, Math.ceil(tw / IW)), lh = Math.max(1, Math.ceil(hw / IW));
          setTop(n, y + 14); if (h3) setTop(h3, y + 14);
          y += 14 + (tw + 12 + hw <= IW ? 22 : l3 * 22 + 4 + lh * 16) + 6; if (hint) setTop(hint, y - 22);
        } else if (cls(n, 'ec-cmp')) {   // flex-wrap: an item goes to the next line when it does not fit; a chip group shrinks (scrolls) to the line
          let x = 0, line = 0, over = false; y += 2; setTop(n, y);
          const navW = 2 * (phone ? 40 : 36) + 11.2 * 12.5 + 10;
          for (const it of kids(n)) {
            const w = cls(it, 'ec-mnav') ? navW : (cls(it, 'ec-mvs') ? 2 * cw + 6 + navW : Math.min(IW, kids(it).reduce((s, b) => s + bw(b.textContent), 2)));
            if (x > 0 && x + 10 + w > IW) { line++; x = 0; }
            if (w > IW) over = true;
            setTop(it, y + line * (H + 8)); x += (x ? 10 : 0) + w; }
          ROWS.push({ lines: line + 1, over, pickers: kids(n).filter(it => cls(it, 'ec-mnav') || cls(it, 'ec-mvs')).length, IW });
          y += (line + 1) * H + line * 8 + 10;
        } else { setTop(n, y); y += 30; } }
      return y; }
    function viewOf(heads, VW) {   // the view: the chart above, then each table card (its head, then its note + table)
      const cards = [], gap = 900; let y = 1800;
      heads.forEach(h => { const nodes = parse(h), card = el('div', { class: 'card ec-tc', top: y }, nodes); y = layoutHead(nodes, y, VW) + gap; cards.push(card); });
      return [el('div', { top: 100, text: 'chart' })].concat(cards); }
    const pick = (root, code, i) => all(root, x => x.getAttribute('onclick') === code)[i];
    const T = JSON.parse(fs.readFileSync(ctlPath, 'utf8')).ctl || [];
    for (const VW of [375, 1280]) for (const t of T) {
      await step(`ecpm_real_${VW}_${t.name}`, async () => {
        W.innerWidth = VW; SCR.replaceChildren(...viewOf(t.before, VW)); W.docH = 9000;
        const i = t.card, b0 = pick(SCR, t.code, i); if (!b0) throw new Error('tapped control not in the card: ' + t.code);
        const twins = all(SCR, x => x.getAttribute('onclick') === t.code).length;
        W.scrollY = Math.max(0, b0.top - 420); const before = onScreen(b0), docBefore = b0.top;
        await tap(b0, () => { SCR.replaceChildren(...viewOf(t.after, VW)); W.scrollY = 0; });   // ecPaint: the whole view rebuilt; iOS → top
        const b1 = pick(SCR, t.code, i);
        ROWS = []; viewOf(t.after, VW); const rows = ROWS; ROWS = [];   // the rows after the tap, as laid out
        return { before, after: b1 ? onScreen(b1) : null, moved: b1 ? b1.top - docBefore : null, twins, y: W.scrollY,
          disabled: b1 ? b1.getAttribute('disabled') === '' : null, rows }; });
    }
    W.innerWidth = 400;
  }
  await step('wrapped', () => ({ to: !!win.scrollTo.__sp, by: !!win.scrollBy.__sp, sc: !!win.scroll.__sp, siv: !!El.prototype.scrollIntoView.__sp }));
  process.stdout.write(JSON.stringify({ errors, out }));
})().catch(e => { errors.push('MAIN ' + (e.stack || e.message)); process.stdout.write(JSON.stringify({ errors, out })); });
