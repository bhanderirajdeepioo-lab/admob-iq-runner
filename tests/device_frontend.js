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
// a period's row: [model, installs, paid, cost USD, revenue so far USD, back next day]
const per = (rows, tot, by) => ({ rows, rest: { n: 120, models: 15, share: 0.0182 }, tot, by: by || {}, days: 30, known: true,
  from: '2026-10-01', to: '2026-10-30' });
const dev = { v: 2, F: '2026-10-28', today: '2026-10-31', cov: { R7: 1, R30: 1, R90: 1, S: 1, n: 1, P: 1 }, cov_ok: 0.98, judge: 300,
  names: { 'XM-1': ['XBrand', 'Phone One'], 'XM-2': ['XBrand', '(not set)'] },
  periods: [['today', 'Today'], ['yday', 'Yesterday'], ['7', '7 days'], ['30', '30 days'], ['tm', 'This month'], ['lm', 'Last month'], ['90', '90 days']],
  V: { 'XM-1': ['Profit', '90', '90', false], 'XM-2': ['Loss', '90', 'never', true], 'XM-3': ['Slow', '30', '365', true] },
  Vc: { XA: { 'XM-1': ['Profit', '90', '90', false] } }, vcount: { Loss: 1, Slow: 1, Profit: 1 },
  cc: [['XA', 4000], ['XB', 1500]],
  P: {
    '30': per([['XM-1', 5000, 4500, 1800, 2250, 0.45], ['XM-2', 900, 855, 427.5, 90, 0.3], ['XM-3', 700, 560, 252, 140, 0.4]],
      { n: 6720, p: 6000, cost: 2400, rev: 2600, d1: 0.42 },
      { XA: { rows: [['XM-1', 3500, 3150, 1575, 1750, 0.45]], rest: { n: 10, models: 2, share: 0.003 }, tot: { n: 4000, p: 3600, cost: 1800, rev: 2000, d1: 0.45 } } }),
    today: Object.assign(per([['XM-1', 200, 180, 72, 9, null]], { n: 260, p: 230, cost: 92, rev: 11, d1: null }), { from: '2026-10-31', to: '2026-10-31' }),
  } };
try {
  out.wait = strip(R._.devView({}));
  out.all = strip(R._.devView({ dev }));
  out.all_html = R._.devView({ dev });
  const lowcov = JSON.parse(JSON.stringify(dev)); lowcov.cov.S = 0.78;
  out.warn = strip(R._.devView({ dev: lowcov }));
  R._.dvSet('XA'); out.cc = strip(R._.devView({ dev }));
  R._.dvSet('', 'n', 1); out.sorted_n = strip(R._.devView({ dev }));
  R._.dvSet('', 'vs', 1); out.sorted_vs = strip(R._.devView({ dev }));
  R._.dvSet('', 'st', 1, 'today'); out.today = strip(R._.devView({ dev }));
  R._.dvSet('', 'st', 1, 'lm'); out.missing_period = strip(R._.devView({ dev }));
  const half = JSON.parse(JSON.stringify(dev)); half.P['30'].days = 20; R._.dvSet('', 'st', 1, '30'); out.partial = strip(R._.devView({ dev: half }));
  out.old_format = strip(R._.devView({ dev: { rows: [] } }));
  R._.dvSet('ZZ'); out.unknown_cc = strip(R._.devView({ dev }));
} catch (e) { errors.push(e.stack || e.message); }
out.errors = errors;
console.log(JSON.stringify(out));
