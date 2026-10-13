// 📈 ROI (a section of 💸 Install value) — the page side, run for real: the ROI module + roiWrap of frontend/index.html (cut
// out by their markers) in a node vm with stub page helpers, on SYNTHETIC data made up here (no real names, ids or money):
//   * where the block goes (between the Value Studio and "🗂 Old views"; nothing without the pointer);
//   * Day-wise ROI: day-by-day columns when the exact store has them, the checkpoints for older days, Today / Yesterday
//     only from the store's own today, week / month rows only when every day is complete, ROAS / revenue / per install /
//     delta cells, breakeven, the KPI tiles;
//   * Countries: decision chips, what cutting saves, sorting, a country's months;
//   * Lifetime P/L: totals only up to the day both sides are in, profit since, every month;
//   * All apps: every app with its icon, sorted Worse first; the hub card's ROI line.
// Prints ONE JSON report; tests/test_roi_frontend.py asserts on it.   usage: node roi_frontend.js <index.html>
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const END = '</details>`; }', a = html.indexOf('const ROI=(()=>{'), b = html.indexOf(END, html.indexOf('function roiWrap(html,aid)')) + END.length - 1;
const c0 = html.indexOf('function roiCardLine(x,name)'), c1 = html.indexOf('function hubCardsPaint(){');
const out = {}, errors = [];
if (a < 0 || b < 0 || c0 < 0) { console.log(JSON.stringify({ errors: ['ROI module not found'] })); process.exit(0); }
const src = html.slice(a, b + 1) + html.slice(c0, c1) + '\nthis.ROI=ROI;this.roiWrap=roiWrap;this.roiCardLine=roiCardLine;';
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error, Date, parseFloat,
  DATA: null, document: undefined, window: {},
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1]; },
  fmtMon: k => MON[+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4),
  hubStChip: k => `<span class="hub-st st-${k}">${k}</span>`,
  appIconId: (id, name, size) => `<span class="aicon" data-iid="${id}"></span>`,
  uniVis: id => id !== 'id-hidden', valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Country ' + cc,
  csym: () => '$', cfx: () => 1, curView: () => 'USD', setApp: () => {}, hubAppId: n => ({ 'Alpha Pick': 'id-a' })[n] || '',
  fetchGzJson: () => Promise.reject(new Error('no file in this test')),
};
vm.createContext(ctx);
const T = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365];
const iso = d => d.toISOString().slice(0, 10);
const day = (s, n) => { const d = new Date(s + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
// an app file: 70 install days to 13 Oct; the newest 40 with day-by-day revenue ($1 a day, spend $10)
function appFile() {
  const rows = [], newest = '2026-10-13';
  for (let i = 69; i >= 0; i--) {
    const X = day(newest, -i), age = i, exact = i < 40;
    const obs = Math.min(30, age), df = Math.max(0, Math.min(obs, age - 3) + 1);
    const d = exact ? Array.from({ length: obs + 1 }, (_, L) => L + 1) : null;
    const t = T.map(a => (a <= age - 3 ? (exact && a <= 30 ? a + 1 : a + 1) : null));
    rows.push([X, 100, 80, 10, d, exact ? df : 0, exact ? d.map(() => 50) : null, t, d ? d[d.length - 1] : t.filter(v => v != null).pop(), X,
      (exact && df > 9) ? [9, true] : null, age >= 10 ? 'Normal' : 'Too early', 0]);
  }
  return { v: 1, app: 'Alpha File', T, lags: 31, newest, S: '2026-10-07', rows,
    months: [['2026-08', 1000, 100, [10, 20, 40, 80, null, null, null, null, null, null], 10, 10],
             ['2026-09', 3000, 300, [30, 60, 120, 240, 450, null, null, null, null, null], 30, 30]],
    sum: { st: 'Watch', r7: 0.4, u7: 0.5, pb: 12, pbm: '2026-09', best: [14, 1.5, '2026-09'], cpi: 0.1,
      pools: { '0': { r: { roas: 0.1 }, u: { roas: 0.12 } }, '7': { r: { roas: 0.4 }, u: { roas: 0.5 } } },
      ret: { '1': { r: 0.3, u: 0.35 } }, cov: 0.8, tie: { checked: 30, off: 1 }, today: rows.slice(-2) },
    life: [['2026-09-29', 5, 20], ['2026-09-30', 30, 5], ['2026-10-01', 10, 5], ['2026-10-02', 1, 50]],
    life_till: '2026-10-01',
    cty: { win: { weeks: 4, from: '2026-09-07', to: '2026-10-04' }, H: 90,
      cut: { n: 1, spend: 400, rev90: 100, spend_all: 1000 },
      rows: [{ cc: 'AA', dec: 'Keep', n: 500, share: 0.5, spend: 300, cpi: 0.6, back: { '7': 50, '30': 90, '90': 120 }, pay: { p: 60, lo: 40, hi: 80 }, ret: { d1: 30 } },
             { cc: 'BB', dec: 'Cut', n: 300, share: 0.3, spend: 400, cpi: 1.3, back: { '7': 10, '30': 15, '90': 25 }, pay: { never: true }, ret: { d1: 20 } },
             { cc: 'CC', dec: 'Scale', n: 200, share: 0.2, spend: 300, cpi: 1.5, back: { '7': 80, '30': 140, '90': 200 }, pay: { p: 20, obs: true }, ret: {} }],
      months: { AA: [['2026-08', 100, 50, 90, 0.4, 0.8, null, 4, 4, 4, 0], ['2026-09', 200, 100, 180, 0.5, null, null, 5, 5, 2, 0]] } },
    consts: { n_recent: 7, n_usual: 28, final_lag: 3 } };
}
(async () => {
  try {
    vm.runInContext(src, ctx);
    const R = ctx.ROI, U = R._;
    // no pointer → nothing added
    ctx.DATA = {};
    out.no_ptr = ctx.roiWrap('<div>studio</div><details id="val-oldapp">old</details>', 'id-a') === '<div>studio</div><details id="val-oldapp">old</details>';
    ctx.DATA = { roi: { file: 'roi.json.gz', v: 'v1', apps: { 'id-a': { file: 'roi_aaaaaaaaaaaa.json.gz', st: 'Watch', r7: 0.4, u7: 0.5, pb: 12 } } } };
    const w = ctx.roiWrap('<div>studio</div><details id="val-oldapp">old</details>', 'id-a');
    out.wrap_order = w.indexOf('id="roi-root"') < w.indexOf('id="val-more"') && w.indexOf('id="val-more"') < w.indexOf('studio')
      && w.indexOf('studio') < w.indexOf('val-oldapp');                         // ROI first; the Studio + old views folded
    out.wrap_loading = w.includes('ROI load ho raha hai');
    // the app file, put in place as if loaded
    const d = appFile();
    const data = U.data();
    data.AF['roi_aaaaaaaaaaaa.json.gz'] = Object.assign(d, { _v: 'v1' });
    const C = U.cols(d, d.rows);
    out.cols = [C.length, C[0].lab, C[30].lab, C[31].lab, C[C.length - 1].lab];       // D0 … D30 + D60 … D365
    const old = d.rows[0];                                                       // no day-by-day cells: checkpoints
    out.old_fallback = [U.cum(old, C[7], T), U.cum(old, C[8], T)];
    const html1 = U.dayView(d);
    out.day_today = html1.includes('Today · 13 Oct') && html1.includes('Yesterday · 12 Oct');
    out.day_tiles = ['D0 ROAS', 'D30 ROAS', 'LTV D30', 'Back next day'].every(s => html1.includes(s));
    const hh = U.hero('id-a');
    out.hero = ['Money back in', '~12 days', 'D7 ROAS', 'Cost / install', 'Lifetime profit / loss', 'Ads profit me'].every(s => hh.includes(s));
    out.day_rows = (html1.match(/<tr><td class="roi-nm">/g) || []).length;          // the first 60 install days
    out.day_more = html1.includes('Show all 70');
    out.day_be = html1.includes('day 9');
    out.day_tie = html1.includes('1 din ka GA4 read match nahi hua');
    U.set('GRAIN', 'month');
    const gm = U.groupRows(d);
    out.months = gm.map(g => [g.k, g.rows.length]);
    const Cm = U.cols(d, d.rows);
    out.month_cols = Cm.map(c => c.lab).slice(0, 6);
    const sep = gm.find(g => g.k === '2026-09');
    out.month_d0 = U.agg(sep, Cm[0], T)[0];
    out.month_d30 = U.agg(sep, Cm[5], T)[0];                                       // some Sep days not 33 days old yet → null
    U.set('GRAIN', 'day');
    out.cells = [U.cell(20, 10, 'roas', null, 100), U.cell(20, 10, 'rev', null, 100), U.cell(20, 10, 'ltv', null, 100), U.cell(20, 10, 'delta', 15, 100)];
    // countries
    const hc = U.ctyView(d);
    out.cty_cut = hc.includes('Hatane se har hafte ~<b>$75</b>');
    out.cty_order = [...hc.matchAll(/data-roi-cty="([A-Z]+)"/g)].map(m => m[1]);   // Cut, then Scale, then Keep
    out.cty_chips = (hc.match(/class="roi-cc"/g) || []).length;
    // lifetime: totals to 1 Oct (2 Oct is live)
    const hl = U.lifeView(d.life, d.life_till, d);
    out.life_total = hl.includes('$45') && hl.includes('$30') && hl.includes('+$15');
    out.life_since = hl.includes('Profit me since') && hl.includes('30 Sep 2026');
    out.life_live = hl.includes('Today · live');
    ctx.curView = () => 'INR'; ctx.cfx = () => 100; ctx.csym = () => '₹';
    const hlr = U.lifeView([['2026-09-29', 5, 20, 1800], ['2026-09-30', 30, 5, 450]], '2026-09-30', Object.assign({}, d, { ccy: 'INR' }));
    out.life_inr = hlr.includes('₹2,250') && hlr.includes('₹3,500') && hlr.includes('+₹1,250');   // spend as billed (not 25 × 100)
    ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
    // all apps
    U.setAll({ v: 1, T, apps: [{ app_id: 'id-b', app: 'Beta', st: 'Normal', r7: 0.5, u7: 0.5, r30: 0.9, life: [10, 5], cut: 0 },
      { app_id: 'id-a', app: 'Alpha', st: 'Worse', r7: 0.2, u7: 0.5, pb: null, best: [30, 0.6, '2026-09'], life: [5, 10], cut: 2 },
      { app_id: 'id-hidden', app: 'Hidden', st: 'Worse', life: [1, 1], cut: 0 }], life: [], months: [], rows: [] });
    const ha = U.allView();
    out.all_order = [...ha.matchAll(/data-roi-app="([^"]+)"/g)].map(m => m[1]);
    out.all_icons = (ha.match(/class="aicon"/g) || []).length;
    const hA = U.hero('');
    out.hero_all = hA.includes('Sabse bada loss') && hA.includes('Best ROI') && hA.includes('Sabse zyada gira');
    // the hub card line
    const x = { st: 'normal', line: 'Money back in ~108 days' };
    ctx.roiCardLine(x, 'Alpha Pick');
    out.card = x.line;
  } catch (e) { errors.push(String(e && e.stack || e)); }
  console.log(JSON.stringify({ errors, out }));
})();
