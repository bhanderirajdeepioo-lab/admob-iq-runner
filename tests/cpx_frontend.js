// 📉 CPI vs eCPM — the page side, run for real: the CPX module of frontend/index.html (cut out by its own markers, with the
// page's month-mover helpers) in a node vm with stub page helpers, on the SYNTHETIC build output of tests/cpx_fixture.js
// (SPEC §3.3 shapes; no real names, ids or numbers):
//   * the picker: every key (Last 14 days first, the standard list, month keys, Custom swapped / clamped) → its dates (N days
//     end at the alarm's data day t; Today / Yesterday after t), the saved choice (bad keys / months / half a Custom ignored,
//     a throwing localStorage harmless);
//   * the "now" sums per app from DATA in ₹ (as billed) and $ (each day's own rate), CPI judged in ₹;
//   * normal / status / since / money of §1.2 for the default view (the pointer) and any other period (cpi.json.gz): the
//     frozen baseline of an episode open at the period's end (a settled one never), else the healthy level the day before;
//     the worst overlapping tier; Paused / New; money lost in ₹ and $ with its "since c" line;
//   * the list (sorted Alarm, Watch, OK, New, Paused; then money lost; then spend), the summary, the footer, one app;
//   * the details: the verdict, the money line, every tab (Chart printed numbers, Day-wise paging, Countries + Rest,
//     Campaigns' tROAS, eCPM kyun, Loss math, History) and the file states (⏳ Loading… / ⚠️ + Try again / no file);
//   * keep(): the tapped row back to its place at 375 and 1280 px; one row open at a time;
//   * the developer copy renders nothing; a hostile app name escaped; the hub card + the Alerts note + the nav count.
// Prints ONE JSON report; tests/test_cpx_frontend.py asserts on it.   usage: node cpx_frontend.js <index.html>
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const { build, addD } = require(path.join(__dirname, 'cpx_fixture.js'));
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('const CPX=(()=>{'), b = html.indexOf('function renderCpx(){');
if (a < 0 || b < 0 || b < a) { console.log(JSON.stringify({ errors: ['CPX module not found'] })); process.exit(0); }
const MON0 = html.indexOf('// ---- the month mover'), MON1 = html.indexOf("// ---- a daily chart's period");
const src = (MON0 >= 0 && MON1 > MON0 ? html.slice(MON0, MON1) : '') + html.slice(a, b) + '\nthis.CPX=CPX;';
const out = {}, errors = [];
function el(screen) {
  const e = { _html: '', dataset: screen ? { screen } : {}, style: {}, isConnected: true, offsetHeight: 900, children: [],
    get innerHTML() { return e._html; }, set innerHTML(v) { e._html = String(v); },
    addEventListener(t, f) { (e._on[t] = e._on[t] || []).push(f); }, _on: {}, querySelectorAll: () => [], querySelector: () => null };
  return e;
}
const SCREEN = el('cpx');
let ON = 'cpx', LOADS = [], FAIL = new Set(), SCROLL = [], LS = null, LS_THROW = false, PUSHED = [], DROPPED = [], CURV = 'INR', SHOWN = [];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
let FX = build();
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, WeakMap, Promise, isFinite, encodeURIComponent, Error, Date, parseFloat,
  setTimeout: (f) => { f(); return 0; }, clearTimeout: () => {},
  DATA: FX.DATA, APP: '',
  document: { querySelector: s => s === '.screen.on' ? { dataset: { screen: ON } } : (s === '.screen[data-screen=cpx]' ? SCREEN : null), getElementById: () => null },
  window: { scrollBy: (x, y) => { SCROLL.push(y); }, innerWidth: 1280, innerHeight: 800, scrollY: 0, addEventListener() {}, removeEventListener() {} },
  get localStorage() { if (LS_THROW) throw new Error('blocked'); return { getItem: k => (LS && k in LS ? LS[k] : null), setItem: (k, v) => { if (LS) LS[k] = String(v); } }; },
  SP: { quietly: f => f() }, HB: { st: [] }, hbPush: (t) => { PUSHED.push(t); }, hbDrop: (t) => { DROPPED.push(t); },
  screenDiv: () => SCREEN,
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1]; },
  appIconId: (id, name, size, cls) => `<span class="aicon ${cls}" data-iid="${id}" data-sz="${size}"></span>`,
  appVisibleByName: nm => nm !== 'Hidden App',
  curView: () => CURV, baseCur: () => 'USD',
  roasFxDated: () => true,
  roasDaily: e => (e && ((CURV === 'USD' && e.daily_dated) || e.daily)) || {},
  valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name ' + cc,
  show: id => { SHOWN.push(id); },   // (the page's own; the module calls it as window.show)
  fetchGzJson: url => { const f = String(url).split('?')[0]; LOADS.push(f); if (FAIL.has(f) || !(f in FX.FILES)) return Promise.reject(new Error('net')); return Promise.resolve(JSON.parse(JSON.stringify(FX.FILES[f]))); },
};
ctx.window.show = ctx.show;
vm.createContext(ctx);
try { vm.runInContext(src, ctx); } catch (e) { console.log(JSON.stringify({ errors: ['TOPLEVEL ' + e.message] })); process.exit(0); }
const CPX = ctx.CPX, _ = CPX._, ID = FX.IDS, KEY = FX.KEYS;
const tick = () => new Promise(r => setImmediate(r));
const strip = h => String(h).replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim();
const by_id = rows => Object.fromEntries(rows.map(r => [r.id, r]));
const reset = () => { for (const k in _.FILES) delete _.FILES[k]; Object.assign(_.ALLF, { raw: null, v: null, busy: false, err: false }); _.set({ PER: '14', PF: '', PTO: '', OPEN: null, TAB: 'ch', DN: 30, PREAD: true }); ctx.APP = ''; };
const rowJ = r => ({ id: r.id, st: r.st, since: r.since, wait: r.wait, fam: r.fam, nrm: Object.fromEntries(Object.entries(r.nrm).map(([k, v]) => [k, v ? [v.v, v.b] : null])),
  s: { sp: r.s.sp, spi: r.s.spi, n: r.s.n, cpi: r.s.cpi, cpiV: r.s.cpiV, ecpm: r.s.ecpm, roas: r.s.roas, k: r.s.k, last3: r.s.last3 },
  lost: r.lost ? { inr: r.lost.inr, usd: r.lost.usd, sinr: r.lost.sinr, susd: r.lost.susd, from: r.lost.from, pre: !!r.lost.pre, ptr: !!r.lost.ptr, na: !!r.lost.na } : null });
(async () => {
  try {
    // ── load: inert until the first paint (no fetch, no storage) ──
    out.inert = { loads: LOADS.length, html: SCREEN.innerHTML };
    // ── the picker ──
    const R = {}; for (const k of ['today', 'yday', '7', '14', '30', '60', '90', 'tm', 'lm', 'all', 'mon:2026-02', 'mon:2026-03', 'mon:2025-06', 'bogus']) R[k] = _.rng(k);
    R.cus = _.rng('cus', '2026-03-20', '2026-03-10'); R.cus_clamp = _.rng('cus', '2020-01-01', '2030-01-01'); R.cus_empty = _.rng('cus', '', '');
    out.rng = R; out.cal = _.cal();
    out.restore = { k14: _.perRestore('{"k":"14"}', FX.DAY0, FX.TODAY), mon: _.perRestore('{"k":"mon:2026-01"}', FX.DAY0, FX.TODAY), monOld: _.perRestore('{"k":"mon:2024-01"}', FX.DAY0, FX.TODAY),
      monNew: _.perRestore('{"k":"mon:2026-05"}', FX.DAY0, FX.TODAY), bad: _.perRestore('{"k":"365"}', FX.DAY0, FX.TODAY), junk: _.perRestore('not json', FX.DAY0, FX.TODAY),
      half: _.perRestore('{"k":"cus","f":"2026-03-01"}', FX.DAY0, FX.TODAY), cus: _.perRestore('{"k":"cus","f":"2026-03-20","t":"2025-01-01"}', FX.DAY0, FX.TODAY) };
    LS_THROW = true; _.set({ PREAD: false }); _.perLoad(FX.DAY0, FX.TODAY); out.ls_throw = _.get().PER; LS_THROW = false;
    LS = { cpx_per_v1: '{"k":"30"}' }; _.set({ PREAD: false }); _.perLoad(FX.DAY0, FX.TODAY); out.ls_read = _.get().PER; reset(); LS = null;
    // ── the sums (₹ / $) ──
    out.sums = {};
    for (const cur of ['INR', 'USD']) { CURV = cur; const s14 = _.sums(...R['14']), s7 = _.sums(...R['7']), sy = _.sums(...R.yday);
      out.sums[cur] = { a14: s14['Alpha App'], b14: s14['Beta App'], c14: s14['Gamma App'], e7: s7['Epsilon App'], ay: sy['Alpha App'], memo: _.sums(...R['14']) === s14 }; }
    CURV = 'INR';
    // ── the default view: the pointer only (no file) ──
    reset(); CPX.paint(); await tick();
    const H0 = SCREEN.innerHTML;
    out.def = { loads: LOADS.slice(), rows: _.rows(...R['14']).map(rowJ), text: strip(H0), html_len: H0.length };
    out.def.order = [...H0.matchAll(/data-cpx-app="([^"]+)"/g)].map(m => m[1]);
    out.def.hostile_raw = H0.includes('<img src=x onerror'); out.def.hostile_esc = H0.includes('&lt;img src=x onerror=alert(1)&gt;Zeta');
    CURV = 'USD'; out.def_usd = { rows: _.rows(...R['14']).map(rowJ), text: strip((CPX.paint(), SCREEN.innerHTML)) }; CURV = 'INR';
    // ── another period: cpi.json.gz (⏳ while it loads, then judged by the page) ──
    LOADS = []; _.set({ PER: '7' }); CPX.paint(); out.p7_wait = { text: strip(SCREEN.innerHTML), rows: _.rows(...R['7']).map(rowJ) }; await tick(); await tick();
    out.p7 = { loads: LOADS.slice(), rows: _.rows(...R['7']).map(rowJ) };
    out.pdec = _.rows('2025-12-01', '2025-12-31').map(rowJ);
    out.pfeb = _.rows('2026-02-01', '2026-02-28').map(rowJ);
    out.pyday = _.rows(...R.yday).map(rowJ);
    CURV = 'USD'; out.pdec_usd = _.rows('2025-12-01', '2025-12-31').map(rowJ); CURV = 'INR';
    out.p14_from_file = _.rows(...R['14']).map(rowJ);            // the default view still the pointer's (file loaded)
    // normal(): a settled episode never gives the normal; an episode closed by the period's end neither
    const A = _.ALLF.raw.apps[ID.a];
    out.normal = { settled: _.normal('CPI', [{ fam: 'CPI', opened: '2026-03-01', closed: '2026-03-28', why: 'settled', c: '2026-02-20', base: 99 }], A, '2026-03-15', '2026-03-20'),
      open: _.normal('CPI', [{ fam: 'CPI', opened: '2026-03-01', closed: null, why: null, c: '2026-02-20', base: 33 }], A, '2026-03-15', '2026-03-20'),
      closed: _.normal('CPI', [{ fam: 'CPI', opened: '2026-03-01', closed: '2026-03-18', why: 'recovered', c: '2026-02-20', base: 33 }], A, '2026-03-15', '2026-03-20'),
      later: _.normal('CPI', [{ fam: 'CPI', opened: '2026-03-25', closed: null, why: null, c: '2026-03-20', base: 33 }], A, '2026-03-15', '2026-03-20'),
      h: _.normal('ECPM', [], A, '2026-02-01', '2026-02-28'), after_t: _.normal('ECPM', [], A, FX.TODAY, FX.TODAY) };
    out.judge = { line: _.judge([{ fam: 'ROAS_C0', tier: 'LINE', c: '2026-03-01', closed: null }], '2026-03-15', '2026-03-28'),
      two: _.judge([{ fam: 'CPI', tier: 'WATCH', c: '2026-03-01', closed: null }, { fam: 'ROAS_G', tier: 'ALERT', c: '2026-03-12', closed: null }, { fam: 'GAP', tier: 'ALERT', c: '2026-03-05', closed: '2026-03-10' }], '2026-03-01', '2026-03-28'),
      fixed: _.judge([{ fam: 'GAP', tier: 'ALERT', c: '2026-03-05', opened: '2026-03-07', closed: '2026-03-10' }, { fam: 'ECPM', tier: 'WATCH', c: '2026-03-02', opened: '2026-03-04', closed: '2026-03-08' }], '2026-03-01', '2026-03-28'),
      late: _.judge([{ fam: 'CPI', tier: 'ALERT', c: '2026-03-20', opened: '2026-03-30', closed: null }], '2026-03-01', '2026-03-28') };
    // the footer's "Not linked spend" follows the picked period (per-day arrays + the store ids' runs of days); the old one-total shape stays as it was
    const U0 = FX.DATA.cpi.unlinked;
    FX.DATA.cpi.unlinked = { d0: '2026-03-20', inr: Array(9).fill(100), usd: Array(9).fill(1), n: 2, runs: [[[0, 8]], [[5, 8]]] };
    const foot = (per, f, t) => { _.set({ PER: per, PF: f || '', PTO: t || '' }); CPX.paint(); const m = strip(SCREEN.innerHTML).match(/Not linked spend:[^—]*—/); return m ? m[0] : null; };
    reset(); out.foot = { d14: foot('14'), d7: foot('7'), cus: foot('cus', '2026-03-20', '2026-03-24'), cus_late: foot('cus', '2026-03-26', '2026-03-28'),
      yday: foot('yday'), before: foot('cus', '2025-11-01', '2025-11-30'), all: foot('all') };
    CURV = 'USD'; out.foot.d7_usd = foot('7'); CURV = 'INR';
    FX.DATA.cpi.unlinked = { d0: 'junk', inr: [1, 2], n: 1 }; out.foot.junk = foot('14');
    FX.DATA.cpi.unlinked = U0; reset(); out.foot.old_shape = foot('7'); await tick(); await tick();    // (the loads these paints started settle here)
    // the all file fails: the default view keeps working; another period says so + Try again
    reset(); FAIL.add('cpi.json.gz'); _.set({ PER: '30' }); CPX.paint(); await tick(); await tick(); CPX.paint();
    out.all_fail = { text: strip(SCREEN.innerHTML), retry: SCREEN.innerHTML.includes('data-cpx-allretry') };
    FAIL.delete('cpi.json.gz'); LOADS = [];
    SCREEN._on.click[0]({ target: { closest: s => s === '[data-cpx-allretry]' ? {} : null } }); await tick(); await tick();
    out.all_retry = { loads: LOADS.slice(), wait: _.rows(...R['30']).some(r => r.wait) };
    // ── the details: a tap opens one row (one at a time), its file loads, every tab ──
    reset(); CPX.paint(); LOADS = [];
    const tap = (sel) => SCREEN._on.click[0]({ target: { closest: s => s === sel ? { dataset: sel.startsWith('[data-cpx-app') ? { cpxApp: tapId } : sel.startsWith('[data-cpx-tab') ? { cpxTab: tapTab } : {} } : null } });
    let tapId = ID.a, tapTab = 'ch';
    tap('[data-cpx-app]'); out.open1 = { open: _.get().OPEN, wait: strip(SCREEN.innerHTML).includes('⏳ Loading…'), loads: LOADS.slice() };
    await tick(); await tick(); CPX.paint();
    const det = h => { const i = h.indexOf('class="cpx-det"'); return i < 0 ? '' : h.slice(i); };
    out.tabs = {};
    for (const [k] of [['ch'], ['dw'], ['cc'], ['cp'], ['ek'], ['lm'], ['hi']]) { tapTab = k; tap('[data-cpx-tab]'); const h = det(SCREEN.innerHTML); out.tabs[k] = { text: strip(h), html: h.length, err: h.includes('padha nahi ja saka') }; }
    tapTab = 'ch'; tap('[data-cpx-tab]');
    out.tabs.ch.svgs = (SCREEN.innerHTML.match(/<svg class="cpx-svg"/g) || []).length;
    out.tabs.ch.labels = [...SCREEN.innerHTML.matchAll(/class="cpx-(?:pt|nt)"[^>]*>([^<]+)</g)].map(m => m[1]);
    out.chd = Object.keys(_.CHD);
    const F = _.FILES['cpi_' + KEY.a + '.json.gz'].raw;
    out.series = _.series(F, '2026-03-01', '2026-03-28', 'CPI').map(p => [p.x, p.v, p.n]);
    out.series_usd = (CURV = 'USD', _.series(F, '2026-03-20', '2026-03-28', 'CPI').map(p => [p.x, p.v, p.n])); CURV = 'INR';
    const rA = _.rows(...R['14']).find(r => r.id === ID.a);
    out.verdict = strip(_.verdict(rA)); out.money = strip(_.moneyLine(rA));
    const dr = _.dayRows(rA, F); out.day = { n: dr.length, first: dr.slice(0, 4).map(z => [z.x, z.nf, z.spi, z.n, z.ro]), t: dr.find(z => z.x === FX.T) };
    tapTab = 'dw'; tap('[data-cpx-tab]'); const n30 = (det(SCREEN.innerHTML).match(/<tr/g) || []).length;
    SCREEN._on.click[0]({ target: { closest: s => s === '[data-cpx-more]' ? {} : null } }); const n60 = (det(SCREEN.innerHTML).match(/<tr/g) || []).length;
    out.day.rows = [n30, n60, _.get().DN];
    // a second row: the first closes (one open at a time), its tab back to Chart
    tapId = ID.b; tap('[data-cpx-app]'); out.open2 = { open: _.get().OPEN, tab: _.get().TAB, dets: (SCREEN.innerHTML.match(/class="cpx-det"/g) || []).length };
    tap('[data-cpx-app]'); out.close = { open: _.get().OPEN, dets: (SCREEN.innerHTML.match(/class="cpx-det"/g) || []).length };
    // file states of the details: failed → ⚠️ + Try again; the retry loads again; a file of another key is refused; no key
    reset(); FAIL.add('cpi_' + KEY.c + '.json.gz'); _.set({ OPEN: ID.c }); CPX.paint(); await tick(); await tick(); CPX.paint();
    out.app_fail = { text: strip(det(SCREEN.innerHTML)), retry: SCREEN.innerHTML.includes('data-cpx-retry="cpi_' + KEY.c + '.json.gz"') };
    FAIL.delete('cpi_' + KEY.c + '.json.gz'); LOADS = [];
    SCREEN._on.click[0]({ target: { closest: s => s === '[data-cpx-retry]' ? { dataset: { cpxRetry: 'cpi_' + KEY.c + '.json.gz' } } : null } }); await tick(); await tick(); CPX.paint();
    out.app_retry = { loads: LOADS.slice(), ok: !strip(det(SCREEN.innerHTML)).includes('⚠️') };
    reset(); const fz = FX.FILES['cpi_' + KEY.z + '.json.gz']; FX.FILES['cpi_' + KEY.z + '.json.gz'] = Object.assign({}, fz, { key: 'ffffffffffff' });
    _.set({ OPEN: ID.z }); CPX.paint(); await tick(); await tick(); CPX.paint(); out.wrong_key = strip(det(SCREEN.innerHTML)); FX.FILES['cpi_' + KEY.z + '.json.gz'] = fz;
    reset(); const pz = FX.DATA.cpi.apps[ID.z]; FX.DATA.cpi.apps[ID.z] = Object.assign({}, pz, { key: 'NOT-HEX', file: '../x.json.gz' });
    _.set({ OPEN: ID.z }); LOADS = []; CPX.paint(); out.bad_key = { text: strip(det(SCREEN.innerHTML)), loads: LOADS.slice() }; FX.DATA.cpi.apps[ID.z] = pz;
    // ── one app (classic APP / the hub's app page): only its row, its details open, no name beside the top bar's ──
    reset(); ctx.APP = 'Alpha App'; CPX.paint(); await tick(); await tick(); CPX.paint();
    out.one = { rows: (SCREEN.innerHTML.match(/data-cpx-app="/g) || []).length, open: _.get().OPEN, det: SCREEN.innerHTML.includes('class="cpx-det"'), name: SCREEN.innerHTML.includes('>Alpha App<'),
      sum: SCREEN.innerHTML.includes('id="cpx-sum"') };
    tapId = ID.a; tap('[data-cpx-app]'); out.one.after_tap = _.get().OPEN;
    ctx.APP = 'Nope App'; CPX.paint(); out.one.none = strip(SCREEN.innerHTML); ctx.APP = '';
    // ── keep(): the tapped row back to its place (1280 and 375 px; the phone takes a Back step) ──
    // (the row above the tapped one closes: the tapped row would move up 120 px — keep() scrolls it back; the page's height
    // is held through the repaint)
    out.keep = {};
    for (const w of [1280, 375]) { reset(); ctx.window.innerWidth = w; _.set({ OPEN: ID.a }); CPX.paint(); SCROLL = []; PUSHED = []; DROPPED = [];
      const ROW = { getBoundingClientRect: () => ({ top: _.get().OPEN === ID.a ? 500 : 380 }) }; SCREEN.querySelector = s => s === '[data-cpx-app="' + ID.c + '"]' ? ROW : null;
      let held = null; const p0 = SCREEN.style.minHeight;
      tapId = ID.c; const paint0 = CPX.paint;
      tap('[data-cpx-app]');
      out.keep[w] = { dy: SCROLL.slice(), open: _.get().OPEN, held: SCREEN.style.minHeight, before: p0, pushed: PUSHED.slice() };
      SCROLL = []; tap('[data-cpx-app]'); out.keep[w].close = { open: _.get().OPEN, dy: SCROLL.slice(), dropped: DROPPED.slice() };
      SCREEN.querySelector = () => null; void held; void paint0; }
    // a phone: opening a row from none takes one Back step (the Back closes it); a desktop never
    for (const w of [375, 1280]) { reset(); ctx.window.innerWidth = w; CPX.paint(); PUSHED = []; tapId = ID.c; tap('[data-cpx-app]'); out.keep['push_' + w] = PUSHED.slice(); }
    ctx.window.innerWidth = 1280;
    // ── the period select / month mover through the screen's own handlers ──
    reset(); CPX.paint();
    SCREEN._on.change[0]({ target: { value: '60', closest: s => s === '[data-cpx-sel]' ? {} : null } }); out.sel = _.get().PER;
    SCREEN._on.change[0]({ target: { value: '999', closest: s => s === '[data-cpx-sel]' ? {} : null } }); out.sel_bad = _.get().PER;
    SCREEN._on.click[0]({ target: { closest: s => s === '[data-cpx-per]' ? { dataset: { cpxPer: 'mon:2026-02' } } : null } }); out.mon = [_.get().PER, _.rng()];
    SCREEN._on.change[0]({ target: { value: '2026-03-02', closest: s => s === '[data-cpx-pf]' ? {} : null } }); out.cus = [_.get().PER, _.rng()];
    out.mover = [...SCREEN.innerHTML.matchAll(/data-cpx-per="([^"]+)"/g)].map(m => m[1]);
    SCREEN._on.click[0]({ target: { closest: s => s === '[data-cpx-roas]' ? {} : null } }); out.roas_link = SHOWN.slice();
    // ── outside the screen: the nav count, the Alerts note, the hub card ──
    reset(); out.alarmN = CPX.alarmN(); out.note = CPX.alertNote(); ctx.APP = 'Beta App'; out.note_beta = CPX.alertNote(); out.alarmN_beta = CPX.alarmN(); ctx.APP = '';
    out.card = { a: CPX.card('Alpha App'), b: CPX.card('Beta App'), c: CPX.card('Gamma App'), d: CPX.card('Delta App'), none: CPX.card('Nope App') };
    // ── the developer copy: nothing ──
    ctx.window.__DEV_VIEW__ = true; reset(); CPX.paint();
    out.dev = { ptr: CPX.ptr(), html: SCREEN.innerHTML, n: CPX.alarmN(), note: CPX.alertNote(), card: CPX.card('Alpha App') }; ctx.window.__DEV_VIEW__ = false;
    // ── no pointer / a bad pointer ──
    const P0 = ctx.DATA.cpi; ctx.DATA.cpi = undefined; reset(); CPX.paint(); out.no_ptr = { ptr: CPX.ptr(), text: strip(SCREEN.innerHTML), n: CPX.alarmN(), card: CPX.card('Alpha App') };
    ctx.DATA.cpi = Object.assign({}, P0, { v: 2 }); out.bad_v = CPX.ptr(); ctx.DATA.cpi = Object.assign({}, P0, { apps: [] }); out.bad_apps = CPX.ptr();
    await tick(); await tick(); ctx.DATA.cpi = Object.assign({}, P0, { file: '../evil.json.gz' }); reset(); LOADS = []; _.set({ PER: '30' }); CPX.paint(); await tick(); out.bad_file = { loads: LOADS.slice(), text: strip(SCREEN.innerHTML) };
    ctx.DATA.cpi = P0;
    // the whole screen's classes: cpx- only (+ the page's card)
    reset(); _.set({ OPEN: ID.a }); CPX.paint(); await tick(); await tick(); const all = []; for (const k of ['ch', 'dw', 'cc', 'cp', 'ek', 'lm', 'hi']) { _.set({ TAB: k }); CPX.paint(); all.push(SCREEN.innerHTML); }
    out.classes = [...new Set(all.join('').match(/class="[^"]*"/g).flatMap(c => c.slice(7, -1).split(/\s+/)).filter(Boolean))];
    out.ids = [...new Set(all.join('').match(/\sid="[^"]*"/g).map(c => c.trim()))];
    out.bad_words = ['undefined', 'NaN', '[object Object]', 'Infinity'].filter(w => all.concat([H0]).some(h => strip(h).includes(w)));
    // ── review round (owner decisions D1–D4 + the minors) ──
    const det2 = h => { const i = h.indexOf('class="cpx-det"'); return i < 0 ? '' : h.slice(i); };
    const paintP = async (o) => { reset(); _.set(o); CPX.paint(); await tick(); await tick(); CPX.paint(); return strip(SCREEN.innerHTML); };
    const rowT = (txt, nm) => { const i = txt.indexOf(nm); return i < 0 ? '' : txt.slice(i, i + 230); };
    // D1: a settled episode counts as open until its close — B on [opened, closed), then H; skipped only when closed by the period's end
    await paintP({ PER: '7' });
    const A1 = _.ALLF.raw.apps[ID.a], se = (closed) => [{ fam: 'CPI', opened: '2026-03-01', closed, why: 'settled', c: '2026-02-20', base: 99 }];
    out.d1 = { open: _.normal('CPI', se('2026-03-28'), A1, '2026-03-15', '2026-03-20'), on_close: _.normal('CPI', se('2026-03-20'), A1, '2026-03-15', '2026-03-20'),
      closed: _.normal('CPI', se('2026-03-18'), A1, '2026-03-15', '2026-03-20') };
    // D2: money ONLY from the D0 ROAS episodes — an AdMob install-day (ROAS_C0) alarm and a pointer number of that line give none
    reset(); const gA = FX.FILES['cpi.json.gz'].apps[ID.c].ep, gF = FX.FILES['cpi_' + KEY.c + '.json.gz'].ep, lB = FX.DATA.cpi.apps[ID.b].lost;
    FX.FILES['cpi.json.gz'].apps[ID.c].ep = [['ROAS_C0', 'DRIFT', 'ALERT', '2026-03-10', '2026-03-14', null, null, 0.5]];
    FX.FILES['cpi_' + KEY.c + '.json.gz'].ep = [{ kind: 'app', id: ID.c, app: ID.c, fam: 'ROAS_C0', opener: 'DRIFT', tier: 'ALERT', c: '2026-03-10', opened: '2026-03-14', closed: null, why: null, base: 0.5 }];
    FX.DATA.cpi.apps[ID.b].lost = { inr: 999, usd: 12, from: '2026-03-12', fam: 'ROAS_C0', sc: { inr: 999, usd: 12 } };
    const t2 = await paintP({ PER: '7', OPEN: ID.c }); const g2 = _.rows(..._.rng('7')).find(r => r.id === ID.c), b2 = _.rows(..._.rng('14')).find(r => r.id === ID.b);
    out.d2 = { gamma: { st: g2.st, lost: g2.lost }, beta_def: b2.lost, sum: (t2.match(/Money lost: [^·]*/) || [''])[0].trim(), money_line: _.moneyLine(g2) };
    FX.FILES['cpi.json.gz'].apps[ID.c].ep = gA; FX.FILES['cpi_' + KEY.c + '.json.gz'].ep = gF; FX.DATA.cpi.apps[ID.b].lost = lB;
    // D3: All time / an early Custom / a period before H exists never turns every app "New"; the cell says which normal it is
    const t3a = await paintP({ PER: 'all' }), r3a = by_id(_.rows(..._.rng('all')));
    const t3b = await paintP({ PER: 'cus', PF: '2025-10-01', PTO: '2025-11-15' }), r3b = by_id(_.rows(..._.rng('cus', '2025-10-01', '2025-11-15')));
    const t3c = await paintP({ PER: 'cus', PF: '2025-10-01', PTO: '2025-10-20' }), r3c = by_id(_.rows(..._.rng('cus', '2025-10-01', '2025-10-20')));
    out.d3 = { all: { st: Object.fromEntries(Object.entries(r3a).map(([k, v]) => [k, v.st])), nrm: r3a[ID.c].nrm, a: r3a[ID.a].nrm, cell: rowT(t3a, 'Gamma App'), verdict: strip(_.verdict(r3a[ID.c])) },
      early: { st: Object.fromEntries(Object.entries(r3b).map(([k, v]) => [k, v.st])), nrm: r3b[ID.c].nrm, cell: rowT(t3b, 'Gamma App') },
      pre: { st: Object.fromEntries(Object.entries(r3c).map(([k, v]) => [k, v.st])), cell: rowT(t3c, 'Gamma App'), verdict: strip(_.verdict(r3c[ID.c])) },
      h: _.hLvl([null, null, 5, 6], '2025-10-01', '2025-10-01', '2025-10-04', 1), h0: _.hLvl([5, 6, 7, 8], '2025-10-01', '2025-10-03', '2025-10-04', 1),
      h_none: _.hLvl([null, null], '2025-10-01', '2025-10-01', '2025-10-02', 1), h_after: _.hLvl([5, 6, 7], '2025-10-01', '2025-10-09', '2025-10-10', 1) };
    // D4: a period that runs past t counts D0 ROAS on the days ≤ t only and says "till <t>"; one with no final day says so
    const sTm = _.sums(..._.rng('tm'))['Alpha App'], sTd = _.sums(..._.rng('today'))['Alpha App'], s14 = _.sums(..._.rng('14'))['Alpha App'];
    const t4 = await paintP({ PER: 'tm' }), t4n = await paintP({ PER: 'today' }), t4d = await paintP({ PER: '14' });
    out.d4 = { tm: { roas: sTm.roas, till: sTm.till, nf: sTm.nf, sp1: sTm.sp1 }, today: { roas: sTd.roas, till: sTd.till, nf: sTd.nf }, d14: { till: s14.till, nf: s14.nf },
      text_tm: rowT(t4, 'Alpha App'), text_today: rowT(t4n, 'Alpha App'), till_in_14: rowT(t4d, 'Alpha App').includes('till 28 Mar') };
    // since: "N din se" only while the since-episode is open at the period's end; else its span
    const t5 = await paintP({ PER: 'cus', PF: '2025-12-01', PTO: '2025-12-31' }), r5 = by_id(_.rows(..._.rng('cus', '2025-12-01', '2025-12-31')))[ID.a];
    const t5o = await paintP({ PER: 'cus', PF: '2025-12-01', PTO: '2025-12-10' }), r5o = by_id(_.rows(..._.rng('cus', '2025-12-01', '2025-12-10')))[ID.a];
    out.since = { closed: { since: r5.since, open: r5.sinceOpen, to: r5.sinceTo, text: rowT(t5, 'Alpha App'), din: t5.includes('din se'), verdict: strip(_.verdict(r5)) },
      open_at_b: { open: r5o.sinceOpen, text: rowT(t5o, 'Alpha App'), verdict: strip(_.verdict(r5o)) } };
    reset(); const pG = FX.DATA.cpi.apps[ID.c]; FX.DATA.cpi.apps[ID.c] = Object.assign({}, pG, { st: 'alarm', since: '2026-03-20', open: [] });   // a closed alarm the pointer still shows
    CPX.paint(); out.since.def_closed = { text: rowT(strip(SCREEN.innerHTML), 'Gamma App'), n: CPX.alarmN() }; FX.DATA.cpi.apps[ID.c] = pG;
    // the pointer's lost.sc is the default view's "since c" line
    reset(); const pA = FX.DATA.cpi.apps[ID.a]; FX.DATA.cpi.apps[ID.a] = Object.assign({}, pA, { lost: Object.assign({}, pA.lost, { sc: { inr: 111111, usd: 1333.33 } }) });
    CPX.paint(); out.sc = strip(SCREEN.innerHTML).includes('since 10 Mar: ≈₹1.1 L'); FX.DATA.cpi.apps[ID.a] = pA;
    // the nav badge / Alerts note: an OPEN ALERT episode in the pointer counts; a closed one the window still touches does not
    reset(); const pB = FX.DATA.cpi.apps[ID.b]; FX.DATA.cpi.apps[ID.c] = Object.assign({}, pG, { st: 'alarm', since: '2026-03-20', open: [] });
    out.alarm0 = CPX.alarmN(); FX.DATA.cpi.apps[ID.b] = Object.assign({}, pB, { open: pB.open.concat([['ROAS_G', 'SUDDEN', 'ALERT', '2026-03-20', '2026-03-23', 0.3]]) });
    out.alarm1 = { n: CPX.alarmN(), note: CPX.alertNote() }; ctx.APP = 'Beta App'; out.alarm1.note_beta = CPX.alertNote(); ctx.APP = ''; FX.DATA.cpi.apps[ID.b] = pB; FX.DATA.cpi.apps[ID.c] = pG;
    // Loss math: the AdMob baseline by the same normal rule (open at the end, else H the day before / the first known inside); Ratio right after Month
    const lm = async (o) => strip(det2(await (async () => { await paintP(Object.assign({ OPEN: ID.a, TAB: 'lm' }, o)); return SCREEN.innerHTML; })()));
    out.lm = { feb: await lm({ PER: 'mon:2026-02' }), early: await lm({ PER: 'cus', PF: '2025-10-01', PTO: '2025-12-31' }), def: await lm({ PER: '14' }) };
    out.lm_head = SCREEN.innerHTML.includes('<th>Month</th><th>Ratio</th><th>Days</th>');
    // the history's money: D0 ROAS episodes only
    out.hist = await lm({ PER: '14', TAB: 'hi' });
  } catch (e) { errors.push(String(e && e.stack || e)); }
  console.log(JSON.stringify({ errors, out }));
})();
