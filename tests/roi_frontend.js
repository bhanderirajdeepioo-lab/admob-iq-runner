// 📈 ROI (a section of 💸 Install value) — the page side, run for real: the ROI module + roiWrap of frontend/index.html (cut
// out by their markers) in a node vm with stub page helpers, on SYNTHETIC data made up here (no real names, ids or money):
//   * where the block goes (between the Value Studio and "🗂 Old views"; nothing without the pointer);
//   * Day-wise ROI: day-by-day columns when the exact store has them, the checkpoints for older days, Today / Yesterday
//     only from the store's own today, week / month rows only when every day is complete, ROAS / revenue / per install /
//     delta cells, breakeven, the KPI tiles;
//   * Countries: decision chips, what cutting saves, sorting, a country's months;
//   * Lifetime P/L: totals only up to the day both sides are in, profit since, every month;
//   * All apps: every app with its icon, sorted Worse first; the hub card's ROI line;
//   * ⚖️ the four forms of ROI: the hero block (the payback-target age or the longest complete one, ranges from the
//     file's own consts, an age GA4 measured: its paid share + premium said so, the budget call, the organic-heavy /
//     mostly-organic warning, the help + paid share per install day), and the All-apps table (biggest blended-vs-paid
//     gap first, flagged rows, ✓ GA4 rows, spend-weighted total, ₹ as billed, sorting); a paused app (whatever its call)
//     out of the total and of the ⚖️ hero card, "✓ GA4" only where GA4 measured, the premium range's own age named.
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
    // install-month P/L: Dec paid back (its own curve crosses between day 3 and 7), Jan not yet; ₹ = as billed, % in ₹ too
    const co = { T, rows: [['2025-12-01', 100, 10, 900, 15], ['2025-12-02', 100, 10, 900, 15], ['2026-01-01', 100, 10, 900, 4]],
      months: [['2025-12', 20, [4, 8, 12, 24, null, null, null, null, null, null], 1800], ['2026-01', 10, [1, null, null, null, null, null, null, null, null, null], 900]] };
    const cp = U.cohortPL(co);
    out.co_rows = [...cp.matchAll(/<td class="roi-nm">([^<]+?)\s*(?:<small>([^<]+)<\/small>)?<\/td>/g)].map(m => m[1] + (m[2] ? ' · ' + m[2] : ''));
    out.co_paid = cp.includes('✅ Wapas aa gaya · ~day 5') && cp.includes('⏳ 44% wapas');
    out.co_total = cp.includes('₹3,400') && cp.includes('+₹700') && cp.includes('₹2,700');   // 3,400 − 2,700 billed
    ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
    const cpu = U.cohortPL(co);
    out.co_usd = cpu.includes('⏳ 40% wapas') && cpu.includes('✅ Wapas aa gaya · ~day 6');
    // all apps
    U.setAll({ v: 1, T, apps: [{ app_id: 'id-b', app: 'Beta', st: 'Normal', r7: 0.5, u7: 0.5, r30: 0.9, life: [10, 5], cut: 0 },
      { app_id: 'id-a', app: 'Alpha', st: 'Worse', r7: 0.2, u7: 0.5, pb: null, best: [30, 0.6, '2026-09'], life: [5, 10], cut: 2 },
      { app_id: 'id-hidden', app: 'Hidden', st: 'Worse', life: [1, 1], cut: 0 }], life: [], months: [], rows: [] });
    const ha = U.allView();
    out.all_order = [...ha.matchAll(/data-roi-app="([^"]+)"/g)].map(m => m[1]);
    out.all_icons = (ha.match(/class="aicon"/g) || []).length;
    const hA = U.hero('');
    out.hero_all = hA.includes('Sabse bada loss') && hA.includes('Best ROI') && hA.includes('Sabse zyada gira');
    // ⚖️ the four forms — synthetic ranges unlike any default, so the page provably prints the file's own
    const F4C = { p: [1.1, 1.5, 3], b: [0.9, 0.5, 0.1], beta: [-0.2, -0.1, -0.05], ages: [7, 30, 90], gap: 0.25 };
    const e30 = { bl: 0.8, s: 0.5, na: 250, nn: 500, n: 500, days: 7, days_na: 7, sp: 100, spi: 8000, rev: 80, from: '2026-09-01', to: '2026-09-07',
      paid: [0.4, 0.45, 0.6], inc: [0.5, 0.6, 0.75], mar: [0.4, 0.55, 0.72], gap: [0.25, 0.44, 0.5] };
    const e7 = Object.assign({}, e30, { bl: 0.3, rev: 30, paid: [0.15, 0.17, 0.22], inc: [0.2, 0.22, 0.27], mar: [0.16, 0.2, 0.26], from: '2026-09-24', to: '2026-09-30' });
    d.consts.f4 = F4C;
    d.f4 = { h: 90, by: { '7': e7, '30': e30 }, dec: { a: 90, v: 'early', mar: null } };
    const fh = U.hero('id-a');
    out.f4_hero = ['4 kinds of ROI · D30', 'pichhle 7 install-din', 'Blended', '80%', 'Paid-only', '45%', 'range 40–60%', 'Incremental', '60%',
      'range 50–75%', 'Marginal · next $100', '55%', 'range 40–72%', '⏳ Too early', 'D90 abhi complete nahi', 'disabled title="D90 abhi complete nahi"',
      'aria-pressed="true">D30', 'Organic-heavy:', 'paid share sirf <b>50%</b>', '~<b>44%</b> kam', '(range 25–50%)', 'Paid share <b>50%</b> = Google Ads installs 250 ÷ GA4 installs 500',
      'Spend $100 → kamai: blended $80 · paid-only ~$45 ($40–$60)', 'Range until GA4 paid/organic data arrives (research)', '×1.1–×3 kamata (beech ×1.5)',
      '0.10–0.90 (beech 0.50)', 'β −0.05 se −0.20 (beech −0.10; sab apps ka ek, har app ka alag abhi measure nahi)', 'What are these 4?',
      'Paid-only · Incremental · Marginal = range until GA4 paid/organic data arrives'].filter(t => !fh.includes(t));
    d.f4.beta = [-0.15, -0.06, -0.02]; d.f4.bsrc = 'app';                      // the app's own measured beta range
    out.f4_own_beta = U.hero('id-a').includes('β −0.02 se −0.15 (beech −0.06; is app ka apna measured)');
    delete d.f4.beta; delete d.f4.bsrc;
    // GA4 measured the paid split at D7: its paid share (30% of 6 of the 7 days) + premium replace the range
    d.f4.by['7'] = Object.assign({}, e7, { src: 'ga4', paid: [0.12, 0.12, 0.12], gap: [0.6, 0.6, 0.6],
      m: { p: 1.6, s: 0.31, rs: 0.42, np: 4000, no: 9000, w: 4, from: '2026-08-17', to: '2026-09-07', sw: 0.3, days: 6 } });
    U.set('F4H', '7');
    const fm = U.hero('id-a');
    out.f4_measured = ['4 kinds of ROI · D7', '12%', '✓ measured · GA4', 'Paid-only = ✓ measured (GA4 paid installs) · Incremental · Marginal = range until GA4 paid/organic data arrives',
      '✓ <b>GA4 measured:</b> paid share <b>30%</b>', '6 of 7 din', 'Ads count: 50% = Google Ads installs 250 ÷ GA4 installs 500',
      'paid install organic se <b>×1.6</b> kamata', '4,000 paid + 9,000 organic', 'Mostly organic:', 'paid share sirf <b>30%</b>',
      'blended se <b>60%</b> kam (GA4 measured)', 'Spend $100 → kamai: blended $30 · paid-only $12.', 'kamata (D7, install weeks', 'Range until GA4 paid/organic data arrives (research): organic jo bina spend ke bhi aate',
      'range 20–27%'].filter(t => !fm.includes(t));
    out.f4_measured_no_p_range = !fm.includes('beech ×1.5') && !fm.includes('paid-only ~') && !fm.includes('range 12–12%')
      && fm.split('×1.6').length === 2;                                         // the measured premium said once
    U.set('F4H', '30');                                                         // a range age names the measured one
    const fr = U.hero('id-a');
    out.f4_measured_elsewhere = fr.includes('aria-pressed="false">D7 ✓') && fr.includes('· ✓ GA4 measured at D7') && fr.includes('aria-pressed="true">D30<');
    U.set('F4H', '7');
    U.set('F4X', true);
    out.f4_measured_help = U.hero('id-a').includes('GA4 ne paid aur organic alag measure kiya');
    U.set('F4X', false); U.set('F4H', null); d.f4.by['7'] = e7;
    out.f4_hero_help_closed = !fh.includes('Budget badhana / ghatana marginal ROI se');
    U.set('F4H', '7');
    out.f4_hero7 = U.hero('id-a').includes('4 kinds of ROI · D7') && U.hero('id-a').includes('aria-pressed="true">D7');
    U.set('F4H', '90');                                                         // not complete for this app: its longest age
    out.f4_hero90 = U.hero('id-a').includes('4 kinds of ROI · D30');
    U.set('F4H', null); U.set('F4X', true);
    const fx = U.hero('id-a');
    out.f4_help = ['Budget badhana / ghatana marginal ROI se', 'Paid share · every install day', 'Close ▾', 'agla extra $ kitna laayega',
      'upar ya neeche dono ho sakta hai'].filter(t => !fx.includes(t)).concat(fx.includes('upper limit') ? ['upper limit'] : []);   // the Ads-count share: no bound
    out.f4_share_bars = (fx.match(/class="bar"/g) || []).length;              // the newest 30 install days with spend
    out.f4_share_nums = (fx.match(/<text class="lv"[^>]*>80%<\/text>/g) || []).length;   // numbers printed on the chart
    U.set('F4X', false);
    d.f4.dec = { a: 90, v: 'down', mar: [0.4, 0.5, 0.8] }; d.f4.by['90'] = Object.assign({}, e30, { gap: [0.05, 0.1, 0.12] });
    const fd90 = U.hero('id-a');
    out.f4_down = fd90.includes('4 kinds of ROI · D90') && fd90.includes('⬇️ Cut budget') && fd90.includes('sirf $40–$80 laata hai')
      && !fd90.includes('Mostly organic');                                     // small gap at D90: no warning
    d.f4.dec = { a: 90, v: 'up', mar: [1.1, 1.2, 1.4], live: true };
    out.f4_up = U.hero('id-a').includes('⬆️ Raise budget') && U.hero('id-a').includes('$110–$140');
    const by0 = d.f4.by;                                                        // no Google Ads install count: blended only
    d.f4.by = { '30': { bl: 0.8, sp: 100, spi: 8000, rev: 80, n: 500, days: 7, from: '2026-09-01', to: '2026-09-07' } };
    d.f4.dec = { a: 90, v: 'na', mar: null, live: true };
    const fn = U.hero('id-a');
    out.f4_na = fn.includes('— No paid share') && fn.includes('Paid share nahi (Google Ads installs ki ginti nahi)')
      && !fn.includes('Marginal = range until') && !fn.includes('Mostly organic') && fn.includes('80%');
    d.f4.by = by0;
    d.f4.dec = { a: 90, v: 'down', mar: [0.4, 0.5, 0.8], live: false };          // spend paused: no raise / cut call
    const fo4 = U.hero('id-a');
    out.f4_off = fo4.includes('⏸️ Spend paused') && fo4.includes('abhi Google Ads spend band') && fo4.includes('dobara chalane layak nahi')
      && !fo4.includes('Cut budget');
    delete d.f4;
    out.f4_none = !U.hero('id-a').includes('4 kinds of ROI');
    // All apps: biggest gap first, flagged, spend-weighted total; hidden apps and apps without ads out
    const fa = (h, v, mar, sp, spi, s, gap, by) => ({ h: 90, by: by || { '30': Object.assign({}, e30, { bl: v, s, na: s * 1000, nn: 1000, sp, spi,
      paid: [v * 0.9, v * 0.95, v], inc: [v * 0.92, v * 0.96, v], mar, gap }) }, dec: h });
    U.setAll({ v: 1, T, f4c: F4C, ccy: 'INR', life: [], months: [], rows: [], apps: [
      { app_id: 'id-b', app: 'Beta', st: 'Normal', life: [10, 5], cut: 0, f4: fa({ a: 90, v: 'down', mar: [0.5, 0.6, 0.7] }, 0.6, [0.47, 0.54, 0.58], 300, 24000, 0.9, [0.02, 0.03, 0.04]) },
      { app_id: 'id-a', app: 'Alpha', st: 'Worse', life: [5, 10], cut: 0, f4: fa({ a: 90, v: 'mixed', mar: [0.9, 1.05, 1.2] }, 0.8, [0.9, 1.05, 1.2], 100, 8000, 0.5, [0.44, 0.44, 0.44]) },
      { app_id: 'id-c', app: 'Gamma', st: 'Too early', life: [1, 2], cut: 0, f4: fa({ a: 90, v: 'early', mar: null }, 0, null, 0, 0, 0, null, { '7': e7 }) },
      { app_id: 'id-p', app: 'Pi', st: 'Normal', life: [3, 4], cut: 0, f4: fa({ a: 90, v: 'down', mar: [0.2, 0.3, 0.4], live: false }, 0.5, [0.2, 0.3, 0.4], 50, 4000, 0.9, [0.01, 0.02, 0.03]) },
      { app_id: 'id-z', app: 'Zeta', st: 'N/A', life: [1, 0], cut: 0, ads: false, f4: { h: 90, by: {}, dec: { a: 90, v: 'early', mar: null } } },
      { app_id: 'id-hidden', app: 'Hidden', st: 'Worse', life: [1, 1], cut: 0, f4: fa({ a: 90, v: 'up', mar: [2, 3, 4] }, 3, [2, 3, 4], 10, 800, 0.1, [0.6, 0.8, 0.9]) }] });
    const al = U.data().ALL.apps.find(x => x.app_id === 'id-a').f4.by['30'];      // Alpha: GA4 measured its paid split
    Object.assign(al, { src: 'ga4', paid: [0.76, 0.76, 0.76], m: { p: 1.3, sw: 0.5, days: 7, np: 2000, no: 2000, w: 4, from: '2026-08-03', to: '2026-08-24' } });
    const fA = U.f4All(U.data().ALL.apps.filter(x => x.app_id !== 'id-hidden'));
    out.f4_all_order = [...fA.matchAll(/<tr class="clk[^"]*" data-roi-app="([^"]+)"/g)].map(m => m[1]);
    out.f4_all_flag = [...fA.matchAll(/<tr class="clk roi-flag" data-roi-app="([^"]+)"/g)].map(m => m[1]);
    out.f4_all_icons = (fA.match(/class="aicon"/g) || []).length;
    out.f4_all = ['⚖️ 4 kinds of ROI · every app · D30', 'D30 abhi complete nahi', '⚠️ −44%', 'All apps', '<td>65%</td>', '$400',
      '↔️ Not sure yet', '⬇️ Cut budget', '⏸️ Spend paused', 'D90 90–120%', 'Budget badhana / ghatana marginal ROI se', 'Range until GA4 paid/organic data arrives',
      'Paid-only = ✓ GA4 measured on 1 app · the rest + Incremental · Marginal = range until GA4 paid/organic data arrives', 'har app ka alag abhi measure nahi',
      '<td>50% <small>✓ GA4</small></td>', '<td>76% <small>✓ GA4</small></td>', '−44% <small>Organic-heavy</small>', '✓ GA4 measured <b>1</b>'].filter(t => !fA.includes(t));
    out.f4_all_chips = [...fA.matchAll(/<span class="roi-cc">.*?<b>(\d+)<\/b><\/span>/g)].map(m => +m[1]);   // up, mixed, down, off, early, organic, GA4
    const tot = fA.slice(fA.indexOf('All apps <small>'));
    out.f4_all_tot = ['<td>70%</td>', '<td>65%</td>', '−5%'].filter(t => !tot.includes(t));   // paid share 1,400 of 2,000; paid-only 247 of 260
    U.set('FSORT', { k: 'sp', dir: 1 });
    out.f4_all_sp = [...U.f4All(U.data().ALL.apps.filter(x => x.app_id !== 'id-hidden')).matchAll(/<tr class="clk[^"]*" data-roi-app="([^"]+)"/g)].map(m => m[1]);
    U.set('FSORT', { k: 'gap', dir: 1 });
    ctx.curView = () => 'INR'; ctx.cfx = () => 100; ctx.csym = () => '₹';
    U.hero('');                                                                 // sets the view's billing currency
    const fI = U.allView();
    out.f4_all_inr = fI.includes('₹32,000') && fI.includes('id="roi-f4all"');  // spend as billed (8,000 + 24,000), not 400 × 100
    ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
    const pz = U.data().ALL.apps.find(x => x.app_id === 'id-p').f4;           // a paused app with a bigger gap …
    const pz0 = pz.by['30'].gap; pz.by['30'].gap = [0.5, 0.6, 0.7];
    const hA4 = U.hero('');                                                     // … is never featured, nor counted (Alpha D30 + Gamma D7)
    pz.by['30'].gap = pz0;
    out.f4_hero_all = hA4.includes('⚖️ Organic-heavy') && hA4.includes('80% → 76%') && hA4.includes('paid share 50% (GA4)') && !hA4.includes('spend band')
      && hA4.includes('· 2 apps aise') && hA4.includes('⬆️ 0 · ↔️ 1 · ⬇️ 1') && hA4.includes('⏸️ 1 paused') && !hA4.includes('Hidden');
    out.f4_all_pa = fA.includes('×1.1–×3 kamata (beech ×1.5) (research ne ye range D30 pe measure ki; D90 pe wahi maani hai)');   // the budget column's age
    // a paused app still too early (call "early", spend stopped): ⏸️ Spend paused, out of the total and of the ⚖️ card;
    // an all-paid app (Google Ads installs ≥ GA4 installs: s capped at 1, so paid-only = blended) is one number, never "✓ GA4"
    const ALL0 = U.data().ALL, ep = o => Object.assign({}, e30, { src: 'range' }, o);
    U.set('F4H', null);
    U.setAll({ v: 1, T, f4c: F4C, ccy: 'USD', life: [], months: [], rows: [], apps: [
      { app_id: 'id-1', app: 'One', st: 'Normal', life: [1, 1], cut: 0, f4: { h: 90, by: { '30': ep({ bl: 0.6, s: 1, sp: 100, spi: 100, paid: [0.6, 0.6, 0.6],
        inc: [0.6, 0.6, 0.6], mar: [0.49, 0.56, 0.58], gap: [0, 0, 0] }) }, dec: { a: 90, v: 'down', mar: [0.4, 0.5, 0.6], live: true } } },
      { app_id: 'id-2', app: 'Two', st: 'Normal', life: [1, 1], cut: 0, f4: { h: 90, by: { '30': ep({ sp: 50, spi: 50, gap: [0.5, 0.6, 0.7] }) },
        dec: { a: 90, v: 'early', mar: null, live: false } } },
      { app_id: 'id-3', app: 'Three', st: 'Normal', life: [1, 1], cut: 0, f4: { h: 90, by: { '7': ep({ bl: 0.3, s: 0.6, sp: 100, spi: 100,
        paid: [0.2, 0.21, 0.22], gap: [0.25, 0.3, 0.35] }), '30': ep({ s: 0.6, sp: 100, spi: 100, gap: [0.05, 0.1, 0.15] }) },
        dec: { a: 90, v: 'mixed', mar: [0.9, 1, 1.1], live: true } } }] });
    const fP = U.f4All(U.data().ALL.apps), rowOf = id => { const i = fP.indexOf(`data-roi-app="${id}"`); return fP.slice(i, fP.indexOf('</tr>', i)); };
    const totP = fP.slice(fP.indexOf('All apps <small>')), totR = totP.slice(0, totP.indexOf('</tr>'));
    out.f4_paused_early = rowOf('id-2').includes('⏸️ Spend paused') && !rowOf('id-2').includes('Too early')
      && (fP.match(/Spend paused<\/span> <b>(\d+)/) || [])[1] === '1' && !fP.includes('Too early</span> <b>')
      && totR.includes('<td>$200</td>') && !totR.includes('$250') && !totR.includes('✓ GA4');   // spend on: the two live apps only
    out.f4_allpaid = rowOf('id-1').includes('<td>60%</td>') && !rowOf('id-1').includes('✓ GA4') && !fP.includes('✓ GA4 measured');
    const hP = U.hero('');
    out.f4_paused_hero_all = hP.includes('data-roi-app="id-3"><span class="roi-hl">⚖️ Organic-heavy') && hP.includes('30% → 21%')
      && hP.includes('blended → paid-only · D7 · paid share 60%') && !hP.includes('apps aise') && hP.includes('⬆️ 0 · ↔️ 1 · ⬇️ 1')
      && hP.includes('⏸️ 1 paused');
    const g7 = U.data().ALL.apps[2].f4.by['7'].gap; U.data().ALL.apps[2].f4.by['7'].gap = [0.05, 0.1, 0.15];
    out.f4_paused_hero_none = !U.hero('').includes('roi-hl">⚖️');               // no live app organic-heavy: no card
    U.data().ALL.apps[2].f4.by['7'].gap = g7;
    U.setAll(ALL0);
    // the app's own hero: a paused app still too early; the premium range's age (research: D30) named at any other age
    const hp = U.f4Hero({ consts: { f4: F4C }, rows: [], f4: { h: 90, by: { '30': ep({}) }, dec: { a: 90, v: 'early', mar: null, live: false } } });
    out.f4_paused_early_hero = hp.includes('⏸️ Spend paused') && !hp.includes('Too early')
      && hp.includes('abhi Google Ads spend band (pichhle 14 spend din) — D90 abhi complete nahi, faisla nahi') && !hp.includes('wahi maani');
    const m7 = ep({ src: 'ga4', paid: [0.12, 0.12, 0.12], m: { p: 1.6, s: 0.31, rs: 0.42, np: 4000, no: 9000, w: 4, from: '2026-08-17', to: '2026-09-07', sw: 0.3, days: 6 } });
    const fq = { h: 90, by: { '7': ep({}), '30': ep({}) }, dec: { a: 90, v: 'mixed', mar: [0.9, 1, 1.1], live: true } };
    U.set('F4H', '7');
    const hq = U.f4Hero({ consts: { f4: F4C }, rows: [], f4: fq });
    out.f4_pa_hero = hq.includes('(beech ×1.5) (research ne ye range D30 pe measure ki; D7, D90 pe wahi maani hai)');
    out.f4_pa_own = U.f4Hero({ consts: { f4: Object.assign({}, F4C, { pa: 7 }) }, rows: [], f4: fq }).includes('(research ne ye range D7 pe measure ki; D90 pe wahi maani hai)');
    fq.by['7'] = m7;                                                            // GA4 measured D7; the D90 budget call still uses the range
    const hm = U.f4Hero({ consts: { f4: F4C }, rows: [], f4: fq });
    out.f4_pa_measured = hm.includes('(beech ×1.5) (research ne ye range D30 pe measure ki; D90 pe wahi maani hai)') && hm.includes('<b>×1.6</b> kamata');
    U.set('F4H', null);
    // 🔮 forecast: 90 days ready; spend +50% scales only the paid part; breakeven from the lifetime P/L
    const f0 = '2026-10-14', H = 180;
    d.fc = { v: 1, made: '2026-10-14', T: '2026-10-13', start: '2026-02-01', start_auto: '2026-02-01', start_set: null,
      p: { hl: 90, K: 30, w: 7, g: 0, W: 28, m: 'ratio' }, ready: { '30': true, '90': true, '180': false }, ready_from: { '180': '2027-01-10' },
      cal: { '30': { bias: 0, lo: -0.1, hi: 0.1, mape: 0.08, mape_normal: 0.05, n: 20, n_normal: 18, ev_rate: 0.1 },
             '90': { bias: 0, lo: -0.2, hi: 0.1, mape: 0.12, mape_normal: 0.1, n: 12, n_normal: 12, ev_rate: 0 } },
      f: { d0: f0, old: Array(H).fill(5), org: Array(H).fill(1), paid: Array(H).fill(4), dau: Array(H).fill(100), n: Array(H).fill(10),
           sp: Array(H).fill(8), spi: 800 },
      hist: { d0: '2026-04-17', rev: Array(180).fill(9), sp: Array(180).fill(8), spi: Array(180).fill(800), dau: Array(180).fill(100), n: Array(180).fill(10) },
      bt: [['2026-08-01', 0.05, 0.1, null, []], ['2026-08-15', -0.2, null, null, [30]]], events: [{ at: '2026-08-20', kind: 'installs', x: 3.1 }],
      att: { installs: 0.2, retention: 0.3, arpdau: 0.5 }, log: [{ d: '2026-10-14', p: { w: 7 }, sc_old: 0.09, sc: 0.06, changed: ['w'], cause: 'arpdau', bias30: 0.02 }],
      checks: [], drv: { installs: [10, 8], spend: [8, 6], cpi: [0.8, 0.75], d1: [0.3, 0.32], d7: [0.1, 0.1], dau: [100, 90], arpdau: [0.09, 0.08],
                         cty: [{ cc: 'AA', share: [0.5, 0.4], d1: [30, 32], rpi7: [0.1, 0.09], cpi: [1, 0.9], dec: 'Watch', ecpm: [2.5, 2] }],
                         split: { rev: [12, 10], imp: [5000, 4500], ecpm: [2.4, 2.2], users: 0.1, ipu: 0.01, mix: 0.05, rate: 0.03,
                                  mix_top: [['AA', 0.04, 0.5, 0.4, 2]], rate_top: [['AA', 0.02, 2.5, 2]] } },
      parts: { mix: 1.12, mix_on: true, org: 4 } };
    // users / installs / uninstalls by who: DAU 100 = 60 old + 20 organic + 20 paid; installs 10 = 4 organic + 6 paid
    d.fc.f.dau_p = { old: Array(H).fill(60), org: Array(H).fill(20), paid: Array(H).fill(20) };
    d.fc.f.un = { old: Array(H).fill(3), org: Array(H).fill(1), paid: Array(H).fill(2) };
    d.fc.f.spd = 7; d.fc.f.spi30 = 700; d.fc.f.sp30 = 7;
    d.fc.hist.un = Array(180).fill(5); d.fc.cal['90'].un_mape = 0.12; d.fc.cal['90'].un_n = 9;
    d.life = [['2026-10-01', 100, 150, 15000]]; d.life_till = '2026-10-01';
    U.set('FCH', '90'); U.set('FCM', 0);
    const fv = U.fcView(d);
    out.fc_tiles = fv.includes('Revenue · agle 90 din') && fv.includes('$900') && fv.includes('$720') && fv.includes('+$180');
    out.fc_ready = fv.includes('180 din <small>10 Jan') && fv.includes('±10% normal din');   // 90 days picked: its own accuracy
    out.fc_be = fv.includes('Profit me aayega');                   // −$50 lifetime + $2 a day → crosses in ~25 days
    out.fc_parts = ['Forecast kyun upar', 'Kitna sahi tha', 'Model kya seekh raha hai', 'start date', 'Achanak jhatke'].every(s => fv.includes(s));
    // why: revenue +20% = users +10% × ads per user +1% × country mix +5% × eCPM +3%; the installs' country value
    out.fc_split = ['Revenue / din', '▲ +20%', '= Users (DAU)', '▲ +10%', '× Ads per user', '▲ +1.0%', '× Country mix', '▲ +5.0%',
      '× eCPM (same country)', '▲ +3.0%', 'Country mix</b> kisne badla', '40% → <b>50%</b>', 'eCPM ' + '$2.00 → <b>$2.50</b>', '×1.12', 'country-wise curves</b> pe chal raha',
      'eCPM abhi / X'].every(s => fv.includes(s));
    // users card: installs 10/day (as the last 30), uninstalls 6 vs 5 (+20%, worse), DAU 100 vs 100, the 30-day blocks
    out.fc_users = ['Users, installs &amp; uninstalls', 'Installs / din · agle 30 din', 'Uninstalls / din · agle 30 din', '▲ +20%',
      'DAU · din 90', 'Din 1–30', 'Din 61–90', 'Pichhle 30 din', 'Pichhle 7 din', 'abhi (7 din)', 'data-roi-fcu="un"', 'back-test me ±12%', 'pichhle 7 din',
      '30 din avg'].every(s => fv.includes(s)) && !fv.includes('Din 91–120');
    U.set('FCM', 1);                                             // spend ×2: paid users / installs / uninstalls double
    const fu2 = U.fcOut(d);
    out.fc_users_slider = fu2.includes('>16<') && fu2.includes('>8<') && fu2.includes('>120<');
    U.set('FCM', 0);
    const d2 = JSON.parse(JSON.stringify(d)); delete d2.fc.drv.split; d2.fc.parts = { mix: null }; d2.fc.drv.cty[0].ecpm = undefined;
    const fv2 = U.fcView(d2);
    out.fc_split_off = !fv2.includes('× Country mix') && !fv2.includes('average install se') && !fv2.includes('eCPM abhi / X');
    U.set('FCM', 0.5);
    const fo = U.fcOut(d);
    out.fc_slider = (fo.match(/\$1,080/g) || []).length === 2 && fo.includes('$0.00');   // revenue 900 + 0.5 × 360 = spend 720 × 1.5
    // engine vd: its three mix weights as simple labels and %, the two models explained, country curves always on
    const d3 = JSON.parse(JSON.stringify(d)); d3.fc.p = { bo: 0.5, bn: 1, cq: 0 }; d3.fc.parts = { mix: 1.12, mix_on: true, org: 4, engine: 'vd' };
    const fv3 = U.fcView(d3);
    out.fc_vd = fv3.includes('Old installs · model B share: <b>50%</b>') && fv3.includes('New installs · model B share: <b>100%</b>')
      && fv3.includes('Newest eCPM move used: <b>0%</b>') && fv3.includes('Model A = har install-din') && fv3.includes('countries ke apne curves');
    // 🌍 GA4's extension cells: the old installs' revenue past day 90 measured vs carried, the switch on / off, and the
    // paid vs organic split's source (measured from GA4's paid users, or the Google Ads count) — numbers printed
    const d4 = JSON.parse(JSON.stringify(d3));
    d4.fc.p = { bo: 0.5, bn: 1, cq: 0, gc: 2, pc: 0 };
    d4.fc.parts = Object.assign({}, d3.fc.parts, { gx: { on: true, old: 0.32, meas: 0.105, umeas: 0.864, weeks: [2, 0, 0, 14, 14, 9, 7] },
      nv: { org: [5, 0.2], paid: [5, 0.3] }, nvsrc: 'cp', pc: false });
    const g4 = U.fcView(d4);
    d4.fc.parts.gx = { on: false, old: 0.4, meas: 0, umeas: 0, weeks: [0, 0, 0, 0, 0, 0, 0] }; d4.fc.parts.nvsrc = 'ads';
    const g5 = U.fcView(d4);
    out.fc_gx = g4.includes('Old installs after day 90') && g4.includes('<b>32%</b>') && g4.includes('<b>11%</b> kamai')
      && g4.includes('<b>86%</b> users') && g4.includes('Model me <b>on</b>') && g4.includes('×1.50') && g4.includes('<b>measured</b>.')
      && g4.includes('Country curves after day 90 (GA4): <b>on</b>') && g4.includes('Paid vs organic (GA4 paid users): <b>off</b>')
      && g5.includes('backfill') && g5.includes('Google Ads install count se andaaza') && !g5.includes('Model me <b>on</b>');
    // the learning log: the first entry of the new engine says so (its error is a different measure); later ones do not
    d3.fc.log = d.fc.log.concat([{ d: '2026-10-15', eng: 'vd', p: d3.fc.p, sc: 0.1, changed: ['bn', 'bo', 'cq'] }]);
    const sw = U.fcView(d3);
    d3.fc.log = d3.fc.log.concat([{ d: '2026-10-16', eng: 'vd', p: d3.fc.p, sc: 0.09, sc_old: 0.1, changed: ['bo'] }]);
    const sw2 = U.fcView(d3);
    out.fc_vd_switch = (sw.match(/New model \(A \+ B\)/g) || []).length === 1 && sw.includes('badla: New installs · model B share, Old installs')
      && (sw2.match(/New model \(A \+ B\)/g) || []).length === 1 && !sw.includes('Old model</b>');
    U.set('FCM', 0);
    // the hub card line
    const x = { st: 'normal', line: 'Money back in ~108 days' };
    ctx.roiCardLine(x, 'Alpha Pick');
    out.card = x.line;
  } catch (e) { errors.push(String(e && e.stack || e)); }
  console.log(JSON.stringify({ errors, out }));
})();
