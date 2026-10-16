// ⚙️ Ad setting badlav (a part of 🔮 Forecast in 📈 ROI, Install value) — the page side, run for real: the ROI module of
// frontend/index.html (cut out by its markers, as tests/roi_frontend.js does) in a node vm with stub page helpers, on
// SYNTHETIC data made up here (no real names, ids or money):
//   * the card: Today / Yesterday on top (the changes first seen today / yesterday, backfill finds never "new"; High /
//     Medium listed with their status word, Low counted "+N Low"), the full history below newest first with ONE status
//     word per row (Confirmed / Checking / With update / Reverted), Low confidence folded behind its own button —
//     checking or not —, "Aur dikhao" past the first rows, a tapped row's evidence (countries, new users, GA4 users,
//     a near update said as measured, days missing while checking);
//   * the weekly ads-per-user chart: one line per format, a ⚙ mark at every change with its size printed (newest first,
//     a row down on a clash), the last value of each line printed, a tooltip per week;
//   * the forecast's daily chart: a ⚙ mark at each change inside its 90 actual days (High / Medium), its size printed at
//     every width and horizon (the newest first, over the forecast's side too, a row down on a clash), said in
//     that day's tooltip and the legend; the back-test chart: ⚙ over the tests a change fell inside, said in its tooltip,
//     and the line of the material changes ("sirf label" while the forecast does not count them);
//   * nothing at all without the block or in the developer's view; the forecast card exactly as before without it.
// Prints ONE JSON report; tests/test_adcfg_frontend.py asserts on it.   usage: node adcfg_frontend.js <index.html>
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const END = '</details>`; }', a = html.indexOf('const ROI=(()=>{'), b = html.indexOf(END, html.indexOf('function roiWrap(html,aid)')) + END.length - 1;
const out = {}, errors = [];
if (a < 0 || b < 0) { console.log(JSON.stringify({ errors: ['ROI module not found'] })); process.exit(0); }
const src = html.slice(a, b + 1) + '\nthis.ROI=ROI;';
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error, Date, parseFloat,
  DATA: null, document: undefined, window: {},
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1]; },
  fmtMon: k => MON[+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4),
  hubStChip: k => `<span class="hub-st st-${k}">${k}</span>`,
  appIconId: (id, name, size) => `<span class="aicon" data-iid="${id}"></span>`,
  uniVis: () => true, valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Country ' + cc,
  csym: () => '$', cfx: () => 1, curView: () => 'USD', setApp: () => {}, hubAppId: () => '',
  fetchGzJson: () => Promise.reject(new Error('no file in this test')),
};
vm.createContext(ctx);
const fill = (n, v) => Array(n).fill(v);
const H = 90, f0 = '2026-10-14';
function app() {
  return { app_id: 'id-a', app: 'Alpha File', ccy: 'USD', life: [['2026-10-01', 100, 150, 15000]], life_till: '2026-10-01',
    fc: { v: 1, made: '2026-10-14', T: '2026-10-13', start: '2026-02-01', start_auto: '2026-02-01', start_set: null,
      p: { hl: 90, K: 30, w: 7, g: 0, W: 28, m: 'ratio' }, ready: { '30': true, '90': true, '180': false }, ready_from: { '180': '2027-01-10' },
      cal: { '30': { bias: 0, lo: -0.1, hi: 0.1, mape: 0.08, mape_normal: 0.05, n: 20, n_normal: 18, ev_rate: 0.1 },
             '90': { bias: 0, lo: -0.2, hi: 0.1, mape: 0.12, mape_normal: 0.1, n: 12, n_normal: 12, ev_rate: 0 } },
      f: { d0: f0, old: fill(H, 5), org: fill(H, 1), paid: fill(H, 4), dau: fill(H, 100), n: fill(H, 10), sp: fill(H, 8), spi: 800,
           dau_p: { old: fill(H, 60), org: fill(H, 20), paid: fill(H, 20) }, un: { old: fill(H, 3), org: fill(H, 1), paid: fill(H, 2) }, spd: 7 },
      hist: { d0: '2026-04-17', rev: fill(180, 9), sp: fill(180, 8), spi: fill(180, 800), dau: fill(180, 100), n: fill(180, 10), un: fill(180, 5) },
      bt: [['2026-07-04', 0.05, 0.1, null, []], ['2026-07-18', -0.2, null, null, [30]], ['2026-08-01', 0.1, null, null, []]],
      events: [{ at: '2026-08-20', kind: 'installs', x: 3.1 }], att: null, log: [], checks: [],
      drv: { installs: [10, 8], spend: [8, 6], cpi: [0.8, 0.75], d1: [0.3, 0.32], d7: [0.1, 0.1], dau: [100, 90], arpdau: [0.09, 0.08], cty: [] },
      parts: null } };
}
// made-up ad setting changes (the build's fc.acfg, adcfg_build.page): newest first
const B = (imp, req, match, show, rev, ecpm) => ({ imp, req, match, show, rev, ecpm });
function block() {
  return { v: 1, made: '2026-10-14', till: '2026-10-13', first: '2026-10-10', ax: 0, mat: 0.1, mx: 3,
    n: { all: 7, conf: 5, chk: 2, rel: 1, gone: 1 },
    wk: { d0: '2026-06-01', f: { app_open: fill(20, 0.4).map((v, i) => i >= 12 ? 0.56 : v), banner: fill(20, 2.0) } },
    steps: [{ at: '2026-08-24', x: 0.21, fmt: 'app_open' }],
    bt: { '30': ['2026-08-01'], '90': ['2026-07-04', '2026-08-01'] },
    ev: [
      { d: '2026-10-05', st: 'checking', lvl: 'f', fmt: 'native', m: 'imp', j: -0.35, kind: 'cap', conf: 'Low', cty: 'ok', seen: '2026-10-14', bf: 0,
        b: B(1.2, 2.2, 0.9, 0.6, 0.002, 2.0), a: B(0.78, 1.43, 0.9, 0.6, 0.0013, 2.1), na: 9, items: [['f', 'native', 'imp', -0.35]] },
      { d: '2026-10-03', st: 'checking', lvl: 'f', fmt: 'app_open', trig: 'resume', m: 'imp', j: 0.4, kind: 'cap', conf: 'Medium', cty: 'ok', seen: '2026-10-14', bf: 0,
        miss: 1, nu: [1.05, 1.33], brk: [0.45, 0.95], near: { d: '2026-10-01', v: '3.3' }, ramp: 4, z: 6.1,
        b: B(0.3, 1.0, 0.93, 0.3, 0.002, 7), a: B(0.42, 1.4, 0.93, 0.3, 0.0028, 7), na: 11, items: [['f', 'app_open', 'imp', 0.4]] },
      { d: '2026-09-28', st: 'confirmed', lvl: 'u', fmt: 'interstitial', unit: 'Demo_Inter_Exit', trig: 'exit', m: 'imp', j: -1, kind: 'removed placement', conf: 'High',
        cty: 'ok', seen: '2026-10-13', bf: 0, b: B(0.15, 0.4, 0.95, 0.4, 0.001, 6), a: B(0, 0, null, null, 0, null), off: ['Demo_Inter_Exit'], na: 14,
        items: [['u', 'Demo_Inter_Exit', 'imp', -1]] },
      { d: '2026-09-02', st: 'reverted', lvl: 'f', fmt: 'banner', m: 'req', j: 0.5, kind: 'cap', conf: 'Medium', cty: 'n/a', seen: '2026-09-10', bf: 0, gone: '2026-09-30',
        b: B(2, 2.1, 0.97, 0.95, 0.0016, 0.8), a: B(3, 3.1, 0.97, 0.95, 0.0024, 0.8), na: 14, items: [['f', 'banner', 'req', 0.5]] },
      { d: '2026-08-24', st: 'confirmed', lvl: 'f', fmt: 'app_open', unit: 'Demo_Splash_Open', trig: 'splash', m: 'imp', j: 0.4, kind: 'cap', conf: 'High', cty: 'ok',
        seen: '2026-10-10', bf: 1, rx: 0.21, near: { d: '2026-08-21', v: '3.2' }, b: B(0.4, 1.4, 0.93, 0.3, 0.0032, 8), a: B(0.56, 1.96, 0.93, 0.3, 0.0045, 8.1),
        na: 14, z: 9.4, ramp: 1, items: [['f', 'app_open', 'imp', 0.4], ['u', 'Demo_Splash_Open', 'imp', 0.52]] },
      { d: '2026-07-10', st: 'confirmed', lvl: 'f', fmt: 'native', m: 'match', j: -0.3, kind: 'SDK', conf: 'Medium', cty: 'ok', seen: '2026-10-10', bf: 1,
        rel: { d: '2026-07-05', v: '3.1' }, b: B(1.3, 2.4, 0.9, 0.6, 0.0026, 2), a: B(0.95, 2.4, 0.66, 0.6, 0.0019, 2), na: 14, items: [['f', 'native', 'match', -0.3]] },
      { d: '2026-06-20', st: 'confirmed', lvl: 'f', fmt: 'banner', m: 'imp', j: 0.31, kind: 'cap', conf: 'Low', cty: 'ok', seen: '2026-10-10', bf: 1,
        b: B(1.5, 1.6, 0.97, 0.95, 0.0012, 0.8), a: B(2, 2.1, 0.97, 0.95, 0.0016, 0.8), na: 14, items: [['f', 'banner', 'imp', 0.31]] }] };
}
try {
  vm.runInContext(src, ctx);
  const R = ctx.ROI, U = R._;
  U.set('FCH', '90'); U.set('FCM', 0);
  const d0 = app(), d = app();
  d.fc.acfg = block();
  // ── the card ──
  const c = U.fcAds(d);
  out.card_head = c.includes('⚙️ Ad setting badlav') && c.includes('Remote Config nahi padha') && c.includes('id="roi-ac"');
  // Today = first seen 14 Oct and not a backfill find: the Medium one listed with its status, the Low one counted;
  // Yesterday = 13 Oct (the removed placement)
  out.today = c.includes('Aaj (14 Oct 26): <b>1 naya</b> — 3 Oct 26 App open (resume) +40% <small>Checking</small> · +1 Low</span>');
  out.yesterday = c.includes('Kal: <b>1 naya</b> — 28 Sep 26 Interstitial (exit) off <small>Confirmed</small></span>');
  const lowOnly = block(); lowOnly.ev = lowOnly.ev.filter(e => e.d !== '2026-10-03');
  out.today_low = U.fcAds(Object.assign(app(), { fc: Object.assign(app().fc, { acfg: lowOnly }) })).includes('Aaj (14 Oct 26): sirf <b>1 Low</b> naya</span>');
  out.till = c.includes('Data <b>13 Oct 26</b> tak');
  out.history = c.includes('Pura history (1 Jun 2026 se): <b>6</b> badlav · High 2 · Medium 2 · Low 2') && c.includes('<b>2</b> abhi check ho rahe')
    && c.includes('1 update ke saath') && c.includes('1 wapas pehle jaise');
  const rows = [...c.matchAll(/<tr class="clk[^"]*" data-roi-acx="([^"]+)"/g)].map(m => m[1].split('|')[0]);
  out.rows = rows;                                    // newest first; Low hidden (the checking Low one too)
  out.status = [...c.matchAll(/<span class="hub-st st-(\w+)">([\w ]+)<\/span><\/td><\/tr>/g)].map(m => m[2]);
  out.kinds = c.includes('<td>Removed placement</td>') && c.includes('<td>SDK / fill</td>') && c.includes('<td>Cap / rule</td>');
  out.update_col = c.includes('📦 v3.1') && c.includes('<small>v3.2 (alag)</small>');
  out.sizes = c.includes('>off<') && c.includes('+40%') && c.includes('0.40 → <b>0.56</b>') && c.includes('<br><small>fill (match rate)</small>');
  out.low_btn = c.includes('data-roi-acl="1" aria-pressed="false">Low bhi dikhao (2)</button>');
  U.set('ACL', true);
  const cl = U.fcAds(d);
  out.low_on = [...cl.matchAll(/data-roi-acx="([^"]+)"/g)].length === 7 && cl.includes('Low chhupao')
    && (U.fcChart(d.fc, H, fill(H, 10), fill(H, 8)).match(/class="acm"/g) || []).length === 4;   // (+ the Low one's mark)
  U.set('ACN', 2);
  const cn = U.fcAds(d);
  out.more = [...cn.matchAll(/<tr class="clk/g)].length === 2 && cn.includes('data-roi-acn="1">Aur dikhao (5)</button>');
  U.set('ACN', 12); U.set('ACL', false);
  U.set('ACX', '2026-08-24|app_open|Demo_Splash_Open');
  const cx = U.fcAds(d);
  out.open_row = cx.includes('aria-expanded="true"') && cx.includes('class="roi-acr"') && cx.includes('requests per user 1.40 → <b>1.96</b>')
    && cx.includes('fill 93% → <b>93%</b>') && cx.includes('Is format ki kamai per user $0.0032 → <b>$0.0045</b>') && cx.includes('<b>+21%</b>')
    && cx.includes('har country me ad requests ka hissa wahi raha — countries ka mix nahi badla') && !cx.includes('users ka mix')
    && cx.includes('Update v3.2 bhi isi time aaya, par badlav update ke users badhne ke saath nahi chala (seedha step zyada fit), ek-do din me ho gaya')
    && cx.includes('Saath me: Demo_Splash_Open ads per user +52%') && cx.includes('noise se 9.4× bada') && cx.includes('1-2 din me hua');
  U.set('ACX', '2026-10-03|app_open|');                // a 4-day change near an update: never "ek-do din me"
  const cy = U.fcAds(d);
  out.open_near = cy.includes('Update v3.3 bhi isi time aaya, par badlav update ke users badhne ke saath nahi chala (seedha step zyada fit) — isliye setting')
    && !cy.includes('ek-do din') && cy.includes('4 din me hua')
    && cy.includes('Naye users: DAU me unka hissa ×1.05 (lagbhag wahi)')
    && cy.includes('GA4 users ×0.45 hue, app ke saare ads ×0.95') && cy.includes('1 naye data din se scan me nahi dikha — 3 din lagatar na dikha to <b>Reverted</b>');
  const nb = block(); nb.ev[1] = Object.assign(nb.ev[1], { nu: [1.4, 1.05], j: 0.4 });   // share and ads per new user moved alike
  U.set('ACX', '2026-10-03|app_open|');
  out.open_nu_alike = U.fcAds(Object.assign(app(), { fc: Object.assign(app().fc, { acfg: nb }) }))
    .includes('Naye users: DAU me unka hissa ×1.40 aur is ad ke ads per naya user ×1.05 (lagbhag wahi) — par ad roz ke naye users ke saath upar-neeche nahi chala');
  U.set('ACX', '2026-07-10|native|');
  out.open_rel = U.fcAds(d).includes('📦 Update <b>v3.1</b> ke saath');
  U.set('ACX', '');
  out.explain = c.includes('<b>30%+</b>') && c.includes('<b>Checking</b>') && c.includes('<b>Reverted</b>') && c.includes('<b>With update</b>')
    && c.includes('Forecast ke numbers pe asar nahi');
  // ── the weekly chart ──
  const ch = U.acChart(d.fc.acfg);
  out.chart_lines = (ch.match(/<path class="ln /g) || []).length === 2 && ch.includes('>App open<') && ch.includes('>Banner<');
  out.chart_marks = (ch.match(/class="acm"/g) || []).length;                 // the non-reverted, non-Low ones inside
  out.chart_labels = ch.includes('⚙ AO +40%') && ch.includes('>0.56<') && ch.includes('>2.00<');
  out.chart_tip = ch.includes('⚙️ 24 Aug 26 App open (splash): +40% · Confirmed');
  // ── the forecast chart ──
  const fc = U.fcChart(d.fc, H, fill(H, 10), fill(H, 8)), fc0 = U.fcChart(d0.fc, H, fill(H, 10), fill(H, 8));
  out.fc_marks = (fc.match(/class="acm"/g) || []).length;                    // the changes inside the 90 actual days
  // every ⚙ gets its number (review: 3 marks, 1 number): marks on 2 Aug, 24 Sep, 2 Oct at 1280 / 375 px × 30 / 90 / 365 days
  out.fc_all_labels = [];
  for (const w of [1280, 375]) {
    ctx.window.innerWidth = w;
    for (const hh of [30, 90, 365]) {
      const dd = app(), bb = block();
      bb.ev = [
        { d: '2026-10-02', st: 'checking', lvl: 'f', fmt: 'native', m: 'imp', j: -0.28, kind: 'cap', conf: 'Medium', seen: '2026-10-14', bf: 0, b: B(1, 1, 1, 1, 1, 1), a: B(0.72, 1, 1, 1, 1, 1) },
        { d: '2026-09-24', st: 'checking', lvl: 'f', fmt: 'interstitial', m: 'imp', j: 0.5, kind: 'cap', conf: 'Medium', seen: '2026-10-14', bf: 0, b: B(0.2, 1, 1, 1, 1, 1), a: B(0.3, 1, 1, 1, 1, 1) },
        { d: '2026-08-02', st: 'confirmed', lvl: 'f', fmt: 'interstitial', m: 'imp', j: -0.42, kind: 'cap', conf: 'High', seen: '2026-10-10', bf: 1, b: B(0.07, 1, 1, 1, 1, 1), a: B(0.04, 1, 1, 1, 1, 1) }];
      dd.fc.acfg = bb;
      const sv = U.fcChart(dd.fc, hh, fill(hh, 10), fill(hh, 8));
      const labs = [...sv.matchAll(/class="acmt" x="([\d.]+)" y="([\d.]+)">([^<]*)</g)].map(m => [+m[1], +m[2], m[3]]);
      const W = w < 640 ? 380 : 720;
      out.fc_all_labels.push([w, hh, (sv.match(/class="acm"/g) || []).length, labs.length, labs.every(l => l[0] >= 0 && l[0] + (l[2].length + 1) * 6.4 + 6 <= W + 0.5),
        labs.map(l => l[2]).sort().join('|')]);
      const cw = U.acChart(Object.assign(bb, { wk: { d0: '2026-06-01', f: { native: fill(20, 1), interstitial: fill(20, 0.2) } } }));
      out.fc_all_labels.push(['weekly', w, (cw.match(/class="acm"/g) || []).length, (cw.match(/class="acmt"/g) || []).length]);
    }
  }
  ctx.window.innerWidth = undefined;
  out.fc_tip = fc.includes('⚙️ Ad setting: App open (splash) ads per user 0.40 → 0.56 (+40%) · Confirmed') && fc.includes('⚙ ad setting badla (neeche list)');
  out.fc_same = !fc0.includes('acm') && !fc0.includes('ad setting');
  // ── the back-test chart ──
  const acc = U.fcAcc(d), acc0 = U.fcAcc(d0);
  out.bt_marks = (acc.match(/class="acmt"[^>]*>⚙</g) || []).length;          // 90 days picked: 2 tests had it inside
  out.bt_tip = acc.includes('⚙️ is test ke 90 din me ad setting badla: 24 Aug 26 App open');
  out.bt_line = acc.includes('⚙️ <b>Ad setting badlav</b> (jo app ki kamai per user 10%+ hilaaye) — upar ⚙ wale 1 test ke beech hue: 24 Aug 26 App open +21%')
    && acc.includes('Sirf label — forecast ke numbers aur range pe asar nahi');
  out.bt_same = !acc0.includes('acmt') && !acc0.includes('Ad setting');
  // ── where it sits, and when it is not there ──
  const v = U.fcView(d), v0 = U.fcView(d0);
  out.view_order = v.indexOf('Forecast kyun upar / neeche') < v.indexOf('id="roi-ac"') && v.indexOf('id="roi-ac"') < v.indexOf('Kitna sahi tha');
  out.view_none = !v0.includes('id="roi-ac"') && !v0.includes('⚙') && U.fcAds(d0) === '';
  const de = app(); de.fc.acfg = Object.assign(block(), { ev: [], n: { all: 0, conf: 0, chk: 0, rel: 0, gone: 0 } });
  out.empty = U.fcAds(de).includes('koi ad setting badlav nahi mila') && U.fcAds(de).includes('<b>koi naya nahi</b>');
  ctx.window.__DEV_VIEW__ = true;
  out.dev = U.fcAds(d) === '' && !U.fcChart(d.fc, H, fill(H, 10), fill(H, 8)).includes('acm') && !U.fcAcc(d).includes('acmt');
  ctx.window.__DEV_VIEW__ = false;
} catch (e) { errors.push(String(e && e.stack || e)); }
console.log(JSON.stringify({ errors, out }));
