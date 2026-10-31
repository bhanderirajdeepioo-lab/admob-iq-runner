// 📱 Devices (a view of 📈 ROI) — the page side, run for real: the ROI module of frontend/index.html (cut out as
// tests/roi_frontend.js does) in a node vm with stub page helpers, on SYNTHETIC data made up here: the waiting message, the
// status chips, the rows (Loss first, then by installs), names, paid %, ≈ cost, ROAS colours, money back labels, back next
// day, the "≈30" mark, the small models line, the coverage warning, a country pick and a column sort. Prints ONE JSON report.
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const END = '</details>`; }', a = html.indexOf('const ROI=(()=>{'), b = html.indexOf(END, html.indexOf('function roiWrap(html,aid)')) + END.length - 1;
if (a < 0 || b < 0) { console.log(JSON.stringify({ errors: ['ROI module not found'] })); process.exit(0); }
const src = html.slice(a, b + 1) + '\nthis.ROI=ROI;';
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error, Date, parseFloat,
  DATA: null, document: undefined, window: {},
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1]; },
  fmtMon: k => MON[+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4),
  hubStChip: k => `<span class="hub-st st-${k}">${k}</span>`, appIconId: () => '', uniVis: () => true,
  valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Country ' + cc,
  csym: () => '$', cfx: () => 1, curView: () => 'USD', setApp: () => {}, hubAppId: () => '',
  fetchGzJson: () => Promise.reject(new Error('no file in this test')),
};
vm.createContext(ctx);
const out = {}, errors = [];
try { vm.runInContext(src, ctx); } catch (e) { errors.push('load: ' + e.message); }
const R = ctx.ROI, strip = h => String(h).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
const row = (m, st, n, ps, cpi, r7, r30, r90, pb, d1, on) => ({ m, st, n, ps, cpi, r7, r30, r90, pb, px: pb === '365', d1, on, n30: n, n90: r90 == null ? 0 : n,
  rev: n * 0.1, rev30: n * 0.3, rev90: r90 == null ? null : n * 0.6 });
const dev = { F: '2026-10-28', win: { '7': ['2026-09-25', '2026-10-22'], '30': ['2026-09-02', '2026-09-29'], '90': ['2026-07-04', '2026-07-31'] },
  cov: { P: 1, D1: 1, R7: 1, n7: 1, R30: 1, n30: 1, R90: 1, n90: 1 }, cov_ok: 0.98, judge: 300, min_row: 30,
  names: { 'XM-1': ['XBrand', 'Phone One'], 'XM-2': ['XBrand', '(not set)'] },
  rows: [row('XM-1', 'Profit', 5000, 0.9, 0.42, 0.2, 0.9, 1.3, '90', 0.45, '90'), row('XM-2', 'Loss', 900, 0.95, 0.5, 0.05, 0.2, 0.4, 'never', 0.3, '90'),
         row('XM-3', 'Slow', 700, 0.8, 0.45, 0.1, 0.5, null, '365', 0.4, '30')],
  rest: { n: 120, models: 15, share: 0.0182 }, cc: [['XA', 4000], ['XB', 1500]],
  tot: { '7': { n: 6720, p: 6000, cost: 2400, rev: 672 }, '30': { n: 6720, p: 6000, cost: 2400, rev: 2016 }, '90': { n: 0, p: 0, cost: 0, rev: 0 }, d1: 0.4 },
  by: { XA: { rows: [row('XM-1', 'Profit', 3500, 0.9, 0.5, 0.2, 0.9, 1.2, '90', 0.45, '90')], rest: { n: 10, models: 2, share: 0.003 }, n: 4000,
    tot: { '7': { n: 4000, p: 3600, cost: 1800, rev: 400 }, '30': { n: 4000, p: 3600, cost: 1800, rev: 1200 }, '90': { n: 4000, p: 3600, cost: 1800, rev: 2400 }, d1: 0.45 } } } };
try {
  out.wait = strip(R._.devView({}));
  out.all = strip(R._.devView({ dev }));
  out.all_html = R._.devView({ dev });
  const lowcov = JSON.parse(JSON.stringify(dev)); lowcov.cov.R7 = 0.78;
  out.warn = strip(R._.devView({ dev: lowcov }));
  R._.dvSet('XA'); out.cc = strip(R._.devView({ dev }));
  R._.dvSet('', 'n', 1); out.sorted_n = strip(R._.devView({ dev }));
  R._.dvSet('', 'u30', 1); out.sorted_u30 = strip(R._.devView({ dev }));
  R._.dvSet('ZZ'); out.unknown_cc = strip(R._.devView({ dev }));
} catch (e) { errors.push(e.stack || e.message); }
out.errors = errors;
console.log(JSON.stringify(out));
