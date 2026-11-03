// 💰 Revenue by source — the page side, run for real: the SRC module of frontend/index.html (cut out by its markers) in a node
// vm with stub page helpers, on SYNTHETIC data made up here (no real names, ids or numbers): the pointer check, the lazy
// files, All apps (sums per period, sorted by total, the All apps row, the %), a period tap (the control kept in place),
// one app (tiles, months newest first with "so far", days with Today / Yesterday, a day not read yet), the GA4 channels
// card from the app's channel file, ₹ view, and a tap on an app row. Prints ONE JSON report.
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('const SRC=(()=>{'), b = html.indexOf('// the Install value page: 📈 ROI first');
if (a < 0 || b < 0 || b < a) { console.log(JSON.stringify({ errors: ['SRC module not found'] })); process.exit(0); }
const src = html.slice(a, b) + '\nthis.SRC=SRC;';
const out = {}, errors = [];
const ROOT = { dataset: { aid: '' }, _html: '', get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  querySelector: () => ({ getBoundingClientRect: () => ({ top: 100 }) }) };
const handlers = {};
let CUR = 'USD', APPSET = [], SCROLL = 0;
const DAYS = 40, TODAY = '2026-10-31';
const iso = t => new Date(t).toISOString().slice(0, 10);
const d0 = iso(Date.parse(TODAY + 'T00:00:00Z') - (DAYS - 1) * 864e5);
// app A: every day paid 10, notif 5, organic 4, other 1 (USD); day index 20 not read yet; app B: paid 1, notif 0, organic 1, other 0
const rev = (p, n, o, x) => Array.from({ length: DAYS }, (_, i) => [p, n, o, x]);
const A = { app_id: 'ca-app-pub-0000000000000000~1', key: '000000000001', app: 'Alpha', tz: 'UTC', today: TODAY, d0,
  rev: rev(10, 5, 4, 1), ses: rev(100, 50, 40, 10), mk: { '38': 's' }, bf: true, ch: ['Cross-network', 'Mobile Push Notifications', 'Direct', '(other)'],
  file: 'source_000000000001.json.gz' };
A.rev[20] = null; A.ses[20] = null;
const B = { app_id: 'ca-app-pub-0000000000000000~2', key: '000000000002', app: 'Beta', tz: 'UTC', today: TODAY, d0,
  rev: rev(1, 0, 1, 0), ses: rev(10, 0, 10, 0), mk: {}, bf: false, ch: ['Cross-network', 'Direct'], file: 'source_000000000002.json.gz' };
const ALLF = { v: 1, at: '2026-10-31T00:00:00Z', groups: [['paid', 'Paid', ['Cross-network']], ['notif', 'Notification', ['Mobile Push Notifications']],
  ['org', 'Organic', ['Direct']], ['oth', 'Other', ['(other)']]], apps: [A, B] };
const CHF = { v: 1, key: A.key, app_id: A.app_id, d0, ch: A.ch, days: Array.from({ length: DAYS }, (_, i) => i === 20 ? null : [[100, 50, 10, 10], [50, 25, 5, 5], [40, 20, 4, 4], [10, 5, 1, 1]]) };
let LOADS = [];
const XROOT = { dataset: { kind: '', aid: '' }, _html: '', get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  querySelector: () => ({ getBoundingClientRect: () => ({ top: 100 }) }) };
// the 🌍 / 📱 Source view files of app A (SYNTHETIC): the period sums, the days (Custom), the phone windows
const CCP = { v: 1, key: '000000000001', d0, today: TODAY, P: {
  '30': { lo: '2026-10-01', hi: '2026-10-30', miss: 0, c: { XA: [30, 15, 7.5, 0, 570], XB: [6, 0, 0, 1.5, 90], '--': [0, 0, 0.3, 0, 30], '(other)': [0, 0, 0, 9, 90] } },
  all: { lo: d0, hi: TODAY, miss: 2, c: { XA: [40, 20, 10, 0, 760] } } } };
const CCD = { v: 1, key: '000000000001', d0, rd: [[0, 35], [38, 39]], c: {
  XA: Array.from({ length: 40 }, (_, i) => [i, 1, 0.5, 0.25, 0, 19]), XB: Array.from({ length: 40 }, (_, i) => [i, 0.2, 0, 0, 0.05, 3]) } };
const DVF = { v: 1, key: '000000000001', names: { 'XP-1': ['XBrand', 'Phone One'] }, w: {
  '30': { lo: '2026-10-01', hi: '2026-10-30', rows: [['XP-1', 4, 1, 0, 0, 50], ['XP-2', 0, 0, 2, 0, 30], ['(other)', 0, 0, 0, 0.5, 5]] },
  all: { lo: '2026-01-01', hi: '2026-10-30', rows: [['XP-2', 0, 0, 20, 0, 300], ['XP-1', 10, 2, 0, 0, 90]] } } };
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error, Date,
  DATA: { source: { file: 'source.json.gz', v: 'abc', apps: { [A.app_id]: { file: A.file, v: 'a1' }, [B.app_id]: { file: B.file, v: 'b1' } } },
          apps_catalog: [{ app_id: A.app_id, app_name: 'Alpha App' }, { app_id: B.app_id, app_name: 'Beta App' }] },
  document: { getElementById: id => id === 'src-root' ? ROOT : id === 'srcx-root' ? XROOT : null,
    addEventListener: (t, f) => { (handlers[t] = handlers[t] || []).push(f); } },
  valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name-' + cc,
  window: { scrollBy: (x, y) => { SCROLL += y; } },
  fetchGzJson: url => { LOADS.push(url); return Promise.resolve(url.startsWith('source.json.gz') ? ALLF : url.startsWith('source_ccd_') ? CCD
    : url.startsWith('source_cc_') ? CCP : url.startsWith('source_dv_') ? DVF : CHF); },
  cfx: () => CUR === 'INR' ? 88 : 1, csym: () => CUR === 'INR' ? '₹' : '$', curView: () => CUR,
  appIcon: n => `<i data-icon="${n}"></i>`, setApp: n => { APPSET.push(n); },
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+p[1] - 1]; },
  fmtMon: k => ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4),
};
vm.createContext(ctx);
try { vm.runInContext(src, ctx); } catch (e) { errors.push('load: ' + e.message); }
const SRC = ctx.SRC;
const flush = () => new Promise(r => setImmediate(r));
const strip = h => String(h).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
const fire = (type, ev) => (handlers[type] || []).forEach(f => f(ev));
const tap = (sel) => fire('click', { target: { closest: s => s === '#src-root' ? ROOT : (s === sel.k ? { dataset: sel.d, getBoundingClientRect: () => ({ top: 100 }) } : null) } });
const tapX = (sel) => fire('click', { target: { closest: s => s === '#srcx-root' ? XROOT : (s === sel.k ? { dataset: sel.d, getBoundingClientRect: () => ({ top: 100 }) } : null) } });
(async () => {
  try {
    const noPtr = (() => { const p = ctx.DATA.source; ctx.DATA.source = null; const r = SRC.block(''); ctx.DATA.source = p; return r; })();
    out.no_pointer = noPtr;
    ROOT.dataset.aid = '';
    const first = SRC.block('');
    out.loading = strip(first);
    await flush(); await flush();
    out.all = strip(ROOT.innerHTML);
    out.loads1 = LOADS.slice();
    tap({ k: '[data-src-per]', d: { srcPer: 'yday' } });
    out.yday = strip(ROOT.innerHTML);
    out.scroll_after_tap = SCROLL;
    tap({ k: '[data-src-per]', d: { srcPer: 'all' } });
    out.all_time = strip(ROOT.innerHTML);
    tap({ k: '[data-src-app]', d: { srcApp: A.app_id } });
    out.appset = APPSET.slice();
    // one app
    ROOT.dataset.aid = A.app_id;
    tap({ k: '[data-src-per]', d: { srcPer: '30' } });
    out.app_loading_channels = strip(ROOT.innerHTML);
    await flush(); await flush();
    out.app = strip(ROOT.innerHTML);
    out.app_html = ROOT.innerHTML;
    out.loads2 = LOADS.slice();
    CUR = 'INR'; SRC.repaint(); out.app_inr = strip(ROOT.innerHTML);
    CUR = 'USD';
    // Custom: the from / to inputs (a change keeps the input in place), every app's own days, reversed dates swapped
    ROOT.dataset.aid = '';
    tap({ k: '[data-src-per]', d: { srcPer: 'cus' } });
    out.cus_html = ROOT.innerHTML;
    const change = (attr, value, rootSel, root) => fire('change', { target: { value, getBoundingClientRect: () => ({ top: 100 }),
      closest: s => s === (rootSel || '#src-root') ? (root || ROOT) : (s === attr ? {} : null) } });
    SCROLL = 0;
    change('[data-src-pf]', '2026-10-10'); change('[data-src-pto]', '2026-10-01');
    out.cus = strip(ROOT.innerHTML); out.cus_scroll = SCROLL;
    // GA4 vs AdMob (the build's AdMob months) and the first $0 months folded: app C earns from Jun 2026, GA4 2× AdMob
    const dC = '2026-03-01', nC = Math.round((Date.parse(TODAY) - Date.parse(dC)) / 864e5) + 1;
    const C = { app_id: 'ca-app-pub-0000000000000000~3', key: '000000000003', app: 'Gamma', tz: 'UTC', today: TODAY, d0: dC,
      rev: Array.from({ length: nC }, (_, i) => iso(Date.parse(dC) + i * 864e5) < '2026-06-01' ? [0, 0, 0, 0] : [2, 1, 1, 0]),
      ses: Array.from({ length: nC }, () => [1, 1, 1, 0]), mk: {}, bf: true, ch: ['Cross-network'], file: 'source_000000000003.json.gz',
      adm: [['2026-06', 60], ['2026-07', 62], ['2026-08', 62], ['2026-09', 60], ['2026-10', 40]] };
    ctx.DATA.apps_catalog.push({ app_id: C.app_id, app_name: 'Gamma App' });
    SRC._.set('ALL', Object.assign({}, ALLF, { apps: [A, B, C] })); SRC._.set('PER', '30');
    out.adm = SRC._.admChk(C); out.adm_a = SRC._.admChk(A);
    out.adm_old = SRC._.admChk(Object.assign({}, C, { adm: [['2026-06', 500], ['2026-07', 20], ['2026-08', 20], ['2026-09', 20]] }));
    ROOT.dataset.aid = ''; SRC.repaint(); out.all_adm = strip(ROOT.innerHTML);
    ROOT.dataset.aid = C.app_id; SRC.repaint(); out.app_c = strip(ROOT.innerHTML);
    // 🌍 Source (the Countries tab's switch): the period's sums per country, GA4's unknown rows last, Custom from the days
    const A2 = Object.assign({}, A, { cc: { file: 'source_cc_000000000001.json.gz', v: 'c1', days: 'source_ccd_000000000001.json.gz', dv: 'd1', bf: false },
      dv: { file: 'source_dv_000000000001.json.gz', v: 'v1' } });
    SRC._.set('ALL', Object.assign({}, ALLF, { apps: [A2, B, C] }));
    ROOT.dataset.aid = ''; XROOT.dataset.kind = 'cty'; XROOT.dataset.aid = A.app_id;
    out.x_loading = strip(SRC.xCty(A.app_id));
    await flush(); await flush();
    out.x_cty = strip(XROOT.innerHTML);
    tapX({ k: '[data-srcx-per]', d: { srcxPer: 'all' } }); out.x_all = strip(XROOT.innerHTML);
    SCROLL = 0;
    tapX({ k: '[data-srcx-per]', d: { srcxPer: 'cus' } });
    change('[data-srcx-pf]', '2026-10-10', '#srcx-root', XROOT); change('[data-srcx-pto]', '2026-09-30', '#srcx-root', XROOT);
    out.x_cus_loading = strip(XROOT.innerHTML);
    await flush(); await flush();
    out.x_cus = strip(XROOT.innerHTML); out.x_scroll = SCROLL;
    // Custom outside the app's days: kept to them (no days "coming" that never will)
    change('[data-srcx-pf]', '2026-01-01', '#srcx-root', XROOT); change('[data-srcx-pto]', '2026-12-31', '#srcx-root', XROOT);
    out.x_cus_wide = strip(XROOT.innerHTML);
    // no source pointer (the step off): said, never an endless "loading"
    const sp = ctx.DATA.source; ctx.DATA.source = null; out.x_off = strip(SRC._.xCtyIn(A.app_id)); ctx.DATA.source = sp;
    // 📱 Source: whole windows only, the phone's name, GA4's "(other)" row last
    XROOT.dataset.kind = 'dev';
    out.x_dev_loading = strip(SRC.xDev(A.app_id));
    await flush(); await flush();
    out.x_dev = strip(XROOT.innerHTML); out.x_dev_html = XROOT.innerHTML;
    tapX({ k: '[data-srcx-win]', d: { srcxWin: 'all' } }); out.x_dev_all = strip(XROOT.innerHTML);
    out.loads_x = LOADS.filter(u => /source_(cc|ccd|dv)_/.test(u));
  } catch (e) { errors.push(e.stack || e.message); }
  out.errors = errors;
  console.log(JSON.stringify(out));
})();
