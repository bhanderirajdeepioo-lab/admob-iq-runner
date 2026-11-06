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
    // years: the period line / spans never print a date from another year without its year (reference year = the alarm's data day)
    const pdOf = h => ((h.match(/class="cpx-pd">([^<]*)/) || [])[1] || '').replace(/ · $/, '');
    reset(); _.set({ PER: 'all' }); CPX.paint(); const yAll = pdOf(SCREEN.innerHTML);
    reset(); _.set({ PER: 'cus', PF: '2025-12-20', PTO: '2026-01-06' }); CPX.paint(); const yCus = pdOf(SCREEN.innerHTML);
    reset(); _.set({ PER: 'mon:2025-12' }); CPX.paint(); const yMon = pdOf(SCREEN.innerHTML);
    reset(); _.set({ PER: 'cus', PF: '2026-02-03', PTO: '2026-02-03' }); CPX.paint(); const yOne = pdOf(SCREEN.innerHTML);
    reset(); _.set({ PER: '14' }); CPX.paint(); const y14 = pdOf(SCREEN.innerHTML);
    out.yr = { all: yAll, cus: yCus, mon: yMon, one: yOne, d14: y14,
      rg: [_.rg('2025-03-01', '2025-03-31'), _.rg('2026-03-01', '2026-03-10'), _.rg('2025-12-23', '2026-01-05'), _.rg('2026-03-04', '2026-03-04'), _.rg('2025-03-04', '2025-03-04'), _.rg('2026-03-01', '2026-03-10', true)],
      fd: [_.fd('2026-03-04'), _.fd('2025-03-04')] };
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
    // ── 🌍 the Chart tab's country picker: All countries first (the app's three charts), then the file's countries by the
    // period's spend share; a country = the SAME three charts from its own lines; remembered per app (lazy, try/catch) ──
    reset(); LS = {}; _.set({ OPEN: ID.a, TAB: 'ch', CTY: null }); CPX.paint(); await tick(); await tick(); CPX.paint();
    const chOf = () => { const h = det2(SCREEN.innerHTML); return { opts: [...h.matchAll(/<option value="([^"]*)"( selected)?>([^<]*)</g)].map(m => [m[1], !!m[2], m[3]]),
      titles: [...h.matchAll(/class="cpx-tt">([^<]+)</g)].map(m => m[1]), labels: [...h.matchAll(/class="cpx-(?:pt|nt)"[^>]*>([^<]+)</g)].map(m => m[1]),
      svgs: (h.match(/<svg class="cpx-svg"/g) || []).length, shade: (h.match(/class="cpx-sw2"/g) || []).length + (h.match(/class="cpx-sb"/g) || []).length, text: strip(h) }; };
    const Fa = _.FILES['cpi_' + KEY.a + '.json.gz'].raw, rA2 = _.rows(...R['14']).find(r => r.id === ID.a), US = Fa.ctys.find(c => c.cc === 'US');
    out.cty = { all: chOf(), list: _.ctyList(rA2, Fa).map(z => [z.c.cc, z.sh]), ls_read: LS.cpx_cty_v1 === undefined };
    const pickC = v => SCREEN._on.change[0]({ target: { value: v, closest: s => s === '[data-cpx-cty]' ? {} : null } });
    pickC('US'); out.cty.us = chOf(); out.cty.ls = LS.cpx_cty_v1;
    // hand math: the 14-day sums of the country's own arrays
    const hand = (keys, x, fn) => { const i1 = Math.round((Date.parse(x) - Date.parse(US.from)) / 864e5); const s = {}; keys.forEach(k => { s[k] = 0; }); for (let i = i1 - 13; i <= i1; i++) for (const k of keys) { const v = US.d[k][i]; if (v == null) return null; s[k] += v; } return fn(s); };
    out.cty.us_roas = _.cSeries(US, '2026-03-20', '2026-03-28', 'ROAS_G').map(p => [p.x, p.v, p.n, hand(['r0', 'sp_usd'], p.x, s => s.r0 / s.sp_usd)]);
    out.cty.us_cpi = _.cSeries(US, '2026-03-27', '2026-03-28', 'CPI').map(p => [p.x, p.v, p.n, hand(['sp_inr', 'dl'], p.x, s => s.sp_inr / s.dl)]);
    out.cty.us_ecpm = _.cSeries(US, '2026-03-28', '2026-03-28', 'ECPM').map(p => [p.x, p.v, p.n, hand(['rev', 'imp'], p.x, s => s.rev / s.imp * 1000)]);
    CURV = 'USD'; out.cty.us_cpi_usd = _.cSeries(US, '2026-03-28', '2026-03-28', 'CPI').map(p => [p.x, p.v, p.n, hand(['sp_usd', 'sp_inr', 'dl'], p.x, s => [s.sp_usd / s.dl, 20 * s.sp_usd / s.sp_inr])]); CURV = 'INR';
    pickC('BR'); out.cty.br = chOf();                                          // no country D0 in this build: a note, never a 0 chart
    pickC('ZZ'); out.cty.bad = _.get().CTY[ID.a];                             // a code the file does not have: refused
    pickC(''); out.cty.back = chOf(); out.cty.ls2 = LS.cpx_cty_v1;
    // remembered per app: read once (a fresh viewer), a code the file lost → All countries; a throwing storage is harmless
    LS = { cpx_cty_v1: JSON.stringify({ [ID.a]: 'IN', [ID.b]: 'XX' }) }; _.set({ CTY: null });
    const Fb = Fa; out.cty.read = [_.ctyOf(ID.a, _.ctyList(rA2, Fa)), _.ctyOf(ID.b, _.ctyList(rA2, Fb))];
    LS_THROW = true; _.set({ CTY: null }); CPX.paint(); out.cty.throw = { titles: chOf().titles, err: chOf().text.includes('padha nahi') }; pickC('US'); out.cty.throw.after = chOf().titles; LS_THROW = false; LS = null;
    // keep(): the picker back in its place after the repaint (the charts above it never move it)
    reset(); _.set({ OPEN: ID.a, TAB: 'ch', CTY: {} }); CPX.paint(); await tick(); await tick(); CPX.paint(); SCROLL = [];
    let n0 = 0; SCREEN.querySelector = s => s === '[data-cpx-cty]' ? { getBoundingClientRect: () => ({ top: n0++ ? 452 : 400 }) } : null;
    pickC('US'); out.cty.keep = { dy: SCROLL.slice(), cty: _.get().CTY[ID.a] }; SCREEN.querySelector = () => null;
    // an app whose file has no country: no picker, the three charts as before
    reset(); _.set({ OPEN: ID.a, TAB: 'ch' }); CPX.paint(); await tick(); await tick(); const Fn = _.FILES['cpi_' + KEY.a + '.json.gz'].raw; Fn.ctys = []; CPX.paint(); out.cty.none = chOf();
    _.set({ CTY: {} });   // the blocks below start from All countries (the picker remembered US above)
    // ── 🕘 History · Levels (a synthetic level history on Alpha's file: sums from the fixture's closed forms) ──
    const T = FX.T;
    const FA = FX.FILES['cpi_' + KEY.a + '.json.gz'], sumOf = (f, a, b) => { const s = {}; for (const x of require(path.join(__dirname, 'cpx_fixture.js')).days(a, b)) { const m = FX.M.a(x);
      const add = (k, v) => { s[k] = (s[k] || 0) + v; };
      if (f === 'CPI') { add('sp_inr', m.sp); add('sp_usd', Math.round(m.sp * FX.fxd(x) * 100) / 100); add('inst', m.inst); }
      if (f === 'ECPM') { add('rev', Math.round(m.imp * m.ecpm / 1000 * 100) / 100); add('imp', m.imp); }
      if (f === 'ROAS_G') { add('d0_inr', Math.round(m.sp * m.d0 * 100) / 100); add('sp_inr', m.sp); } }
      return s; };
    const lvr = (o) => Object.assign({ id: 'L-0000000000', from: '2025-12-01', to: null, v: 1, days: null, sums: null, src: 'auto', ep: null, act: null, st: 'earlier', seen: '2026-03-30T05:22:00Z', rs: null, gone: null, rejected: null }, o);
    const cA = sumOf('CPI', '2026-02-24', '2026-03-09'), cF = sumOf('CPI', '2025-11-01', '2025-11-14'), eF = sumOf('ECPM', '2025-11-01', '2025-11-14'), rP = sumOf('ROAS_G', '2026-03-01', '2026-03-28');
    const tam = Object.assign({}, cF, { inst: cF.inst * 1.01 });
    FA.lv = { CPI: [
        lvr({ id: 'L-00000000a1', src: 'alarm', from: '2026-03-13', v: cA.sp_inr / cA.inst, days: ['2026-02-24', '2026-03-09'], sums: cA, st: 'now', ep: { opened: '2026-03-13', c: FX.C, why: null, opener: 'SUDDEN' } }),
        lvr({ id: 'L-00000000a2', src: 'accepted', from: '2026-01-10', to: '2026-03-12', v: 21, days: ['2025-12-14', '2026-01-10'], sums: null, st: 'rest', ep: { opened: '2025-11-15', old: 20 } }),
        lvr({ id: 'L-00000000a3', src: 'first', from: '2025-12-01', to: '2026-01-09', v: cF.sp_inr / cF.inst, days: ['2025-11-01', '2025-11-14'], sums: cF, st: 'earlier' }),
        lvr({ id: 'L-00000000a4', src: 'auto', from: '2025-11-20', to: '2025-11-30', v: tam.sp_inr / tam.inst, days: ['2025-11-01', '2025-11-14'], sums: tam, st: 'gone', gone: '2026-03-01T00:00:00Z' }),
        lvr({ id: 'L-00000000a5', src: 'manual', from: '2025-11-10', to: '2025-11-19', v: 19.5, days: null, sums: null, st: 'earlier', act: 'a-0000000000c1' })],
      ECPM: [lvr({ id: 'L-00000000e1', src: 'first', from: '2025-12-01', v: eF.rev / eF.imp * 1000, days: ['2025-11-01', '2025-11-14'], sums: eF, st: 'now' })],
      SPEND: [lvr({ id: 'L-00000000s1', src: 'first', from: '2025-12-01', v: 600, days: null, st: 'now' })] };
    FA.lp = [{ fam: 'ROAS_G', opened: '2026-03-14', day: '2026-03-20', why: 'money', v: rP.d0_inr / rP.sp_inr, days: ['2026-03-01', '2026-03-28'], sums: rP, old: 0.4, gap: { inr: 123456, usd: 1500 } }];
    FA.la = [{ id: 'a-0000000000c1', at: '2026-03-29T10:12:00Z', act: 'set', fam: 'CPI', from: '2025-11-10', value: 19.5, note: '<img src=x onerror=alert(2)>', st: 'applied' },
      { id: 'a-0000000000c2', at: '2026-03-29T10:13:00Z', act: 'rollback', fam: 'CPI', from: T, level: 'L-ffffffffff', st: 'bad', why: 'UnknownLevel' }];
    const POSTS = [], TOASTS = []; let ANS = null;
    ctx.bToast = m => { TOASTS.push(String(m)); }; ctx.confirm = () => true;
    ctx.fetch = async (u, o) => { const b = o && o.body ? JSON.parse(o.body) : null; if (o && o.method === 'POST') POSTS.push({ u, b });
      const a = ANS ? ANS(u, o, b) : { status: 404, j: null }; return { status: a.status, type: 'basic', json: async () => a.j }; };
    const settle = async () => { for (let i = 0; i < 6; i++) await tick(); };
    const lvTab = async (o) => { reset(); _.set(Object.assign({ OPEN: ID.a, TAB: 'hi', LVQ: { st: 'ok', admin: true, save: true, acts: [] }, PEND: [] }, o || {})); CPX.paint(); await settle(); CPX.paint(); await settle(); CPX.paint(); return det2(SCREEN.innerHTML); };
    const clickD = (sel, ds) => SCREEN._on.click[0]({ target: { closest: s => s === sel ? { dataset: ds || {} } : null } });
    // read-only (no API: GET answers 404) — the history, ✓ / ⚠, no buttons
    ANS = () => ({ status: 404, j: null });
    reset(); _.set({ OPEN: ID.a, TAB: 'hi', LVQ: { st: null, admin: false, save: false, acts: [] }, PEND: [] }); CPX.paint(); await settle(); CPX.paint(); await settle(); CPX.paint();
    const ro = det2(SCREEN.innerHTML);
    out.lv = { ro: { text: strip(ro), checks: (ro.match(/class="cpx-lvc"/g) || []).length, warn: (ro.match(/Day-wise ka jod is level se nahi milta/g) || []).length, typed: (ro.match(/>typed</g) || []).length,
      buttons: /data-cpx-lv(act|set|undo)=/.test(ro), q: _.LVQ().st, hostile_raw: ro.includes('<img src=x onerror=alert(2)>'), hostile_esc: ro.includes('&lt;img src=x onerror=alert(2)&gt;'),
      fams: [...ro.matchAll(/data-cpx-lvf="([^"]+)"/g)].map(m => m[1]), more: ro.includes('data-cpx-lvmore'), classes: [...new Set([...ro.matchAll(/class="([^"]+)"/g)].flatMap(m => m[1].split(/\s+/)))] } };
    ANS = () => ({ status: 403, j: { error: 'admin_only', msg: 'Sirf admin level badal sakta hai' } });
    reset(); _.set({ OPEN: ID.a, TAB: 'hi', LVQ: { st: null, admin: false, save: false, acts: [] }, PEND: [] }); CPX.paint(); await settle(); CPX.paint(); await settle(); CPX.paint();
    out.lv.ro403 = { q: _.LVQ().st, text: strip(det2(SCREEN.innerHTML)).includes('Sirf admin level badal sakta hai'), buttons: /data-cpx-lv(act|set|undo)=/.test(SCREEN.innerHTML) };
    // the checks against the fixture's hand math (₹ and $)
    const rowA3 = FA.lv.CPI[2]; CURV = 'INR'; out.lv.v_inr = _.lvV(FA, 'CPI', rowA3); out.lv.chk = _.lvCheck(FA, 'CPI', rowA3).k; CURV = 'USD'; out.lv.v_usd = _.lvV(FA, 'CPI', rowA3);
    out.lv.chk_tam = _.lvCheck(FA, 'CPI', FA.lv.CPI[3]).k; out.lv.chk_typed = _.lvCheck(FA, 'CPI', FA.lv.CPI[4]).k; out.lv.chk_e = _.lvCheck(FA, 'ECPM', FA.lv.ECPM[0]).k; CURV = 'INR';
    out.lv.v_ecpm = _.lvV(FA, 'ECPM', FA.lv.ECPM[0]);
    // admin: the buttons and every POST body
    const ACTION = (b) => Object.assign({ id: 'a-00000000ab' + String(POSTS.length).padStart(2, '0'), at: '2026-03-30T06:40:00Z', by: 'x@example.test' }, b);
    ANS = (u, o, b) => o && o.method === 'POST' ? { status: 200, j: { ok: true, action: ACTION(b), actions: [] } } : { status: 200, j: { actions: [], me: 'x', admin: true, server_save: true } };
    const adm = await lvTab();
    out.lv.adm = { set: adm.includes('data-cpx-lvset'), rollback: [...adm.matchAll(/data-cpx-lvact="rollback" data-cpx-lvid="([^"]+)"/g)].map(m => m[1]),
      reject: [...adm.matchAll(/data-cpx-lvact="reject" data-cpx-lvid="([^"]+)"/g)].map(m => m[1]), auto: adm.includes('data-cpx-lvact="auto"'),
      undo: [...adm.matchAll(/data-cpx-lvundo="([^"]+)"/g)].map(m => m[1]), fams: [...adm.matchAll(/data-cpx-lvf="([^"]+)"/g)].map(m => m[1]) };
    _.set({ LVF: 'ROAS_G' }); CPX.paint(); out.lv.adm.accept = SCREEN.innerHTML.includes('data-cpx-lvact="accept" data-cpx-lvp="0"'); out.lv.adm.prop = strip(det2(SCREEN.innerHTML)).includes('🆕 New level ready: 33.2%'); _.set({ LVF: 'CPI' }); CPX.paint();
    clickD('[data-cpx-lvact]', { cpxLvact: 'rollback', cpxLvid: 'L-00000000a3' }); await tick(); await tick();
    clickD('[data-cpx-lvact]', { cpxLvact: 'reject', cpxLvid: 'L-00000000a2' }); await tick(); await tick();
    clickD('[data-cpx-lvact]', { cpxLvact: 'auto' }); await tick(); await tick();
    _.set({ LVF: 'ROAS_G' }); clickD('[data-cpx-lvact]', { cpxLvact: 'accept', cpxLvp: '0' }); await tick(); await tick(); _.set({ LVF: 'CPI' });
    clickD('[data-cpx-lvundo]', { cpxLvundo: 'a-0000000000c1' }); await tick(); await tick();
    clickD('[data-cpx-lvset]'); const form = det2(SCREEN.innerHTML); out.lv.form = { open: form.includes('id="cpx-lvx"'), set: _.get().LVSET, text: strip(form) };
    SCREEN._on.change[0]({ target: { value: '2026-03-10', closest: s => s === '[data-cpx-lva]' ? {} : null } }); out.lv.form.after = _.get().LVSET;
    out.lv.form.preview = strip(det2(SCREEN.innerHTML)).match(/Level [^·]+= [^✓]+✓/) ? strip(det2(SCREEN.innerHTML)).match(/Level [^·]+= [^✓]+✓/)[0] : null;
    SCREEN._on.input && SCREEN._on.input[0]({ target: { value: 'naya normal <b>', closest: s => s === '[data-cpx-lvnote]' ? {} : null } });
    clickD('[data-cpx-lvsave]'); await tick(); await tick();
    _.set({ LVSET: { fam: 'CPI', mode: 'val', a: addD(T, -27), b: T, val: '31.5', note: '' } }); clickD('[data-cpx-lvsave]'); await tick(); await tick();
    _.set({ LVF: 'ROAS_G', LVSET: { fam: 'ROAS_G', mode: 'val', a: addD(T, -27), b: T, val: '35', note: '' } }); clickD('[data-cpx-lvsave]'); await tick(); await tick(); _.set({ LVF: 'CPI' });
    _.set({ LVSET: { fam: 'CPI', mode: 'days', a: addD(T, -3), b: T, val: '', note: '' } }); const nP = POSTS.length; clickD('[data-cpx-lvsave]'); await tick(); out.lv.short_days = POSTS.length - nP;
    out.lv.posts = POSTS.map(p => ({ u: p.u, b: p.b })); out.lv.toasts = TOASTS.slice();
    // pending: the saved actions show until the build's la has them
    _.set({ LVSET: null }); CPX.paint(); const pend = strip(det2(SCREEN.innerHTML)); out.lv.pending = (pend.match(/⏳ Saved/g) || []).length; out.lv.pending_txt = pend.includes('agle update me lagega (1–1½ ghante)');
    const ids = _.PEND().map(a => a.id), LF = _.FILES['cpi_' + KEY.a + '.json.gz'].raw, la0 = LF.la;
    LF.la = la0.concat(ids.map(id => ({ id, at: '2026-03-30T06:40:00Z', act: 'set', fam: 'CPI', st: 'applied' })));
    CPX.paint(); out.lv.pending_after = (strip(det2(SCREEN.innerHTML)).match(/⏳ Saved/g) || []).length; LF.la = la0;
    // an error answer: the API's Hinglish reason + the HTTP status in the toast
    TOASTS.length = 0; ANS = (u, o) => o && o.method === 'POST' ? { status: 409, j: { error: 'github_conflict', msg: 'Kisi aur ne abhi save kiya — dobara try karo', gh_status: 409 } } : { status: 200, j: { actions: [], admin: true, server_save: true } };
    clickD('[data-cpx-lvact]', { cpxLvact: 'auto' }); await tick(); await tick(); out.lv.err_toast = TOASTS.slice();
    // keep(): the family switch puts the tapped button back (1280 / 375)
    out.lv.keep = {};
    for (const w of [1280, 375]) { await lvTab(); ctx.window.innerWidth = w; SCROLL = []; let n = 0;
      const BTN = { getBoundingClientRect: () => ({ top: n++ === 0 ? 400 : 520 }) }; SCREEN.querySelector = s => s === '[data-cpx-lvf="ECPM"]' ? BTN : null;
      clickD('[data-cpx-lvf]', { cpxLvf: 'ECPM' }); out.lv.keep[w] = { dy: SCROLL.slice(), f: _.get().LVF }; SCREEN.querySelector = () => null; }
    ctx.window.innerWidth = 1280;
    // ── review fixes (the Levels block): Save only for a level the build takes · From never before the file's first day · one save at a
    // time · the $ view's typed CPI goes out in ₹ · the owner's actions and Undo stay when the build shipped no history ──
    const FXM = require(path.join(__dirname, 'cpx_fixture.js')), r2 = v => Math.round(v * 100) / 100;
    const saveTag = h => (h.match(/<button[^>]*data-cpx-lvsave="1"[^>]*>/) || [''])[0], lvb = h => [...h.matchAll(/<button[^>]*class="cpx-lvb[^"]*"[^>]*>/g)].map(m => m[0]);
    const setDays = (fam, a, b2) => ({ LVF: fam, LVSET: { fam, mode: 'days', a, b: b2, val: '', note: '' } }), setVal = (fam, val) => ({ LVF: fam, LVSET: { fam, mode: 'val', a: addD(T, -27), b: T, val, note: '' } });
    ANS = (u, o, b) => o && o.method === 'POST' ? { status: 200, j: { ok: true, action: ACTION(b), actions: [] } } : { status: 200, j: { actions: [], me: 'x', admin: true, server_save: true } };
    out.lvfix = { save: {} };
    let hx = await lvTab(setDays('CPI', '2026-03-10', T));                                         // data for every day, worth more than 0: Save on
    out.lvfix.save.ok = !/disabled/.test(saveTag(hx));
    hx = await lvTab(setDays('CPI', '2025-09-01', '2025-10-14'));                                  // 30 of its 44 days are before the file's first day
    out.lvfix.save.nodata = { disabled: /disabled/.test(saveTag(hx)), text: strip(hx).includes('In dino ka data poora nahi') };
    const i0 = FXM.nD(FA.day0, '2025-11-01') - 1, rev0 = FA.d.rev.slice(); for (let i = i0; i < i0 + 14; i++) FA.d.rev[i] = 0;   // no revenue on 1–14 Nov: eCPM exactly 0
    hx = await lvTab(setDays('ECPM', '2025-11-01', '2025-11-14'));
    out.lvfix.save.zero = { disabled: /disabled/.test(saveTag(hx)), text: strip(hx).includes('Is level ki value 0 hai'), shown: /Level <b>/.test(hx) };
    const nz = POSTS.length; clickD('[data-cpx-lvsave]'); await tick(); await tick(); out.lvfix.save.zero_posts = POSTS.length - nz;   // (a stray tap sends nothing)
    FA.d.rev = rev0;
    hx = await lvTab(setDays('CPI', '2026-03-10', T));                                             // a date before the file's first day is moved to it
    SCREEN._on.change[0]({ target: { value: '2025-09-01', closest: s => s === '[data-cpx-lva]' ? {} : null } });
    out.lvfix.from_clamp = [_.get().LVSET.a, FA.day0, _.get().LVSET.b];
    const d00 = FA.day0; FA.day0 = addD(T, -9); await lvTab(); clickD('[data-cpx-lvset]'); out.lvfix.from_default = [_.get().LVSET.a, FA.day0, _.get().LVSET.b]; FA.day0 = d00;   // a young file: the default From is its first day
    await lvTab(); clickD('[data-cpx-lvset]'); out.lvfix.from_default_old = _.get().LVSET.a;                                                                              // an old file: the last 28 days as before
    // one save at a time: a double tap commits once, the owner buttons are disabled while it is in flight and enabled after
    const BT = [{ disabled: false }, { disabled: false }];
    await lvTab(); SCREEN.querySelectorAll = s => s === 'button.cpx-lvb' ? BT : []; const n1 = POSTS.length;
    clickD('[data-cpx-lvact]', { cpxLvact: 'auto' }); const mid = BT.map(b => b.disabled), busy = _.get().LVBUSY;
    clickD('[data-cpx-lvact]', { cpxLvact: 'auto' }); clickD('[data-cpx-lvundo]', { cpxLvundo: 'a-0000000000c1' });    // the second tap · another button
    await tick(); await tick();
    out.lvfix.dbl = { posts: POSTS.length - n1, mid, busy, after: BT.map(b => b.disabled), idle: _.get().LVBUSY };
    SCREEN.querySelectorAll = () => [];
    await lvTab(setDays('CPI', '2026-03-10', T)); const hb0 = lvb(det2(SCREEN.innerHTML));         // a repaint during the flight keeps them disabled
    _.set({ LVBUSY: true }); CPX.paint(); const hb1 = lvb(det2(SCREEN.innerHTML)); _.set({ LVBUSY: false });
    out.lvfix.lock_paint = { n: hb1.length, off: hb0.filter(x => /disabled/.test(x)).length, on: hb1.filter(x => /disabled/.test(x)).length };
    const nf = POSTS.length; clickD('[data-cpx-lvsave]'); clickD('[data-cpx-lvsave]'); await tick(); await tick();   // the form's Save: a double tap, one commit
    out.lvfix.save_dbl = POSTS.length - nf;
    // the $ view: a typed CPI is in $ — sent in ₹ at the view's rate (Σ$ ÷ Σ₹ of the 14 days ending the data day), and the form says so
    // (the last 14 days' $ cost is raised 10 % in this file so that the 14-day rate differs from the page's one flat rate)
    const su0 = FA.d.sp_usd.slice(); for (let i = FA.d.sp_usd.length - 14; i < FA.d.sp_usd.length; i++) FA.d.sp_usd[i] = r2(FA.d.sp_usd[i] * 1.1);
    CURV = 'USD'; const kD = FXM.days(addD(T, -13), T).reduce((q, x) => q + r2(r2(50000 * FX.fxd(x)) * 1.1), 0) / (14 * 50000);
    hx = await lvTab(setVal('CPI', ''));
    out.lvfix.usd = { text: strip(hx), save_off: /disabled/.test(saveTag(hx)), k: kD };
    const nu = POSTS.length; _.set(setVal('CPI', '0.38')); clickD('[data-cpx-lvsave]'); await tick(); await tick();
    out.lvfix.usd.body = POSTS.slice(nu).map(p => p.b);
    const si0 = FA.d.sp_inr.slice(); for (let i = FA.d.sp_inr.length - 14; i < FA.d.sp_inr.length; i++) FA.d.sp_inr[i] = 0;   // no spend in those 14 days: no rate
    hx = await lvTab(setVal('CPI', '0.38'));
    out.lvfix.usd_norate = { text: strip(hx).includes('rate nahi mila'), save_off: /disabled/.test(saveTag(hx)) };
    const nn = POSTS.length; TOASTS.length = 0; clickD('[data-cpx-lvsave]'); await tick(); await tick(); out.lvfix.usd_norate.posts = POSTS.length - nn; out.lvfix.usd_norate.toast = TOASTS.slice();
    FA.d.sp_inr = si0; FA.d.sp_usd = su0;
    hx = await lvTab(setVal('ECPM', ''));                                                          // eCPM is $ per 1000 in both views: no conversion note
    out.lvfix.usd_ecpm = { unit: strip(hx).includes('$ per 1000 impressions'), note: strip(hx).includes('₹ me badal') };
    CURV = 'INR'; hx = await lvTab(setVal('CPI', ''));                                             // the ₹ view: ₹ per install, nothing converted
    out.lvfix.inr = { unit: strip(hx).includes('₹ per install'), note: strip(hx).includes('₹ me badal'), save_off: /disabled/.test(saveTag(hx)) };
    // the owner's actions and Undo without a history block (the build shipped none: its history file / step failed)
    const lv0 = FA.lv, la0x = FA.la; delete FA.lv;
    hx = await lvTab();
    out.lvfix.nolv = { note: strip(hx).includes('Is build me level history nahi bani'), actions: strip(hx).includes('Owner actions'),
      undo: [...hx.matchAll(/data-cpx-lvundo="([^"]+)"/g)].map(m => m[1]), switches: (hx.match(/data-cpx-lvf=/g) || []).length, set: hx.includes('data-cpx-lvset') };
    hx = await lvTab({ LVQ: { st: 'ro', admin: false, save: false, acts: [] } });
    out.lvfix.nolv_ro = { actions: strip(hx).includes('Owner actions'), undo: (hx.match(/data-cpx-lvundo=/g) || []).length };
    delete FA.la;                                                                                  // … nor the actions (the whole step skipped): the saved ones show as pending
    const q = [{ id: 'a-0000000000d1', at: '2026-03-29T10:12:00Z', act: 'set', app: ID.a, fam: 'CPI', from: T, value: 19.5 }];
    hx = await lvTab({ LVQ: { st: 'ok', admin: true, save: true, acts: q } });
    out.lvfix.nolv_pending = { pending: (strip(hx).match(/⏳ Saved/g) || []).length, undo: [...hx.matchAll(/data-cpx-lvundo="([^"]+)"/g)].map(m => m[1]) };
    const nq = POSTS.length; clickD('[data-cpx-lvundo]', { cpxLvundo: 'a-0000000000d1' }); await tick(); await tick(); out.lvfix.nolv_pending.undo_post = POSTS.slice(nq).map(p => p.b);
    const p1 = _.PEND().length; FA.lv = lv0; FA.la = la0x; out.lvfix.nolv_pending.pend = p1;
    // the chart: a marker + printed label per level change inside the days; the proposal hollow; the tooltip names the level
    await lvTab({ TAB: 'ch', PER: 'all' }); const chH = SCREEN.innerHTML;
    out.lv.chart = { marks: (chH.match(/class="cpx-lvm"/g) || []).length, labels: [...chH.matchAll(/class="cpx-lvn"[^>]*>([^<]+)</g)].map(m => m[1]), hollow: (chH.match(/class="cpx-lvo"/g) || []).length };
    out.lv.ticks = [...chH.matchAll(/class="cpx-ax">([^<]+)</g)].map(m => m[1]);
    // a chart wholly inside the reference year: the month ticks stay as short as before (no year on the first one)
    const cy = []; for (let d = new Date(Date.UTC(2026, 4, 1)); d <= Date.UTC(2026, 8, 1); d = new Date(+d + 864e5)) cy.push({ x: d.toISOString().slice(0, 10), v: 10, n: 10 });
    out.lv.ticks_cur = [..._.chart('cx-y', 'T', cy, 'CPI', [], 'cpx-ok', null, false).matchAll(/class="cpx-ax">([^<]+)</g)].map(m => m[1]);
    // … and one that starts on 1 Jan of the reference year: no year on the January tick either
    const cj = []; for (let d = new Date(Date.UTC(2026, 0, 1)); d <= Date.UTC(2026, 3, 1); d = new Date(+d + 864e5)) cj.push({ x: d.toISOString().slice(0, 10), v: 10, n: 10 });
    out.lv.ticks_jan = [..._.chart('cx-j', 'T', cj, 'CPI', [], 'cpx-ok', null, false).matchAll(/class="cpx-ax">([^<]+)</g)].map(m => m[1]);
    const c1 = _.CHD['cpx-c1']; out.lv.tip = c1 ? strip(_.tipHtml(c1, c1.P.length - 1)) : null;
    // a country picked: its own three charts carry no app level marker / proposal and the tooltip names no app level;
    // back to All countries: the app's markers again
    pickC('US'); const cH = SCREEN.innerHTML, cc1 = _.CHD['cpx-c1'];
    out.lv.cty = { svgs: (cH.match(/<svg class="cpx-svg"/g) || []).length, marks: (cH.match(/class="cpx-lvm"|class="cpx-lvo"/g) || []).length,
      F: cc1 ? cc1.F : 'none', tip: cc1 ? strip(_.tipHtml(cc1, cc1.P.length - 1)) : null };
    pickC(''); out.lv.cty.back = (SCREEN.innerHTML.match(/class="cpx-lvm"/g) || []).length; _.set({ CTY: {} });
    // the row tag (pointer lp) and the proposal line in the details
    const pA2 = FX.DATA.cpi.apps[ID.a]; FX.DATA.cpi.apps[ID.a] = Object.assign({}, pA2, { lp: 1 }); reset(); _.set({ OPEN: ID.a }); CPX.paint(); await tick(); await tick(); CPX.paint();
    out.lv.tag = { row: SCREEN.innerHTML.includes('class="cpx-lvt"'), det: strip(det2(SCREEN.innerHTML)).includes('D0 ROAS: new level ready') };
    FX.DATA.cpi.apps[ID.a] = pA2; delete FA.lv; delete FA.lp; delete FA.la; delete ctx.fetch;
  } catch (e) { errors.push(String(e && e.stack || e)); }
  console.log(JSON.stringify({ errors, out }));
})();
