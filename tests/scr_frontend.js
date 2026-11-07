// 🖼️ Screens tab — the page side, run for real: the SCR module of frontend/index.html (cut out by its own markers, with the
// page's month-mover helpers) in a node vm with stub page helpers, on SYNTHETIC files made up here in the shape of
// admob_iq/screens_build.py's (no real names, ids or numbers):
//   * the picker: every standard key (+ month keys, Custom swapped / clamped) → its GA4 dates (N days end at the last final
//     day; Today / Yesterday not final), the period's normal = the max(28, length) final days before it, the score muted
//     under 7 final days and "—" for All time;
//   * the sums: a row counts only the days whose grain carries its quantity (a day split per screen without the format
//     has no inline ads), screen views on every day beside them;
//   * the coverage strip: N / M apps whole per piece from the day-state strings (each app on its own calendar);
//   * the status words → chips (WD keys) and the Worse-first order of apps and rows;
//   * All apps and an app page (+ every drill-down section and fold, with its lazy files) for a normal app, an app whose ads
//     by screen are sampled every day, an app with screen-only days, an app with no AdMob placements, an app with no days
//     yet; a hostile class name escaped everywhere; hidden apps left out;
//   * the Copy report helper: the clipboard, a rejected clipboard → the selected textarea + execCommand, no API at all,
//     execCommand failing → "Select karke copy karein";
//   * the period saved per viewer: bad keys / months / half a Custom ignored, a throwing localStorage harmless;
//   * the chart's model (daily / weekly / monthly, no point under 100 views, the printed labels) and its drawing;
//   * keep(): the tapped control back to its place and its sideways row's scroll kept, the page's height held THROUGH the
//     repaint (paint() inside a keep() leaves the hold for unholdLater); ✕ Close on a phone: the row back where keep() left
//     it once the details' Back step has landed (the browser's own scroll restore of that step undone a frame later);
//   * the drill-down belongs to its app: another app opens with it closed (Back step dropped), "Show more" per app;
//   * "Details ▸" in Needs attention goes to the drill-down card; a table row's tap stays put;
//   * a late file redraws only the slots that use it, their scroll boxes kept;
//   * a whole month in the period comes from the build's month sums (ver_m / cc_m), the edge months from the shards;
//   * labels in simple English (the hints stay Hinglish); the status sort honours its direction; the report's Copy
//     control keeps its place while its files load (a failed load: Try again); All apps' period sums and coverage strip
//     kept per (build, period), no date string per day; a day whose store month file could not be read ("x"); a day
//     that is not whole never read as "GA4 sampled" (the how-it-works lines, a layer day never asked / not read);
//   * the build's why ("Not whole — …") whole and escaped in the crumb / All apps / Needs attention; all formats because
//     GA4 gave no screen × format split (allf 2: header, line, note with the measured share); a row under 1 % of the
//     app's ads of its kind: "score —" (and a "Too few ads" row never in Needs attention);
//   * Ads / user, per user per day, from file 2 (⏳ until it is here, its failed load says so + Try again; its late
//     arrival redraws the tiles and the table): the Screens column (Σ ads ÷ Σ the screen's daily users on the final days
//     with users — users varying by day, so the mean of the daily ratios reads differently — its days, the tooltips,
//     "—" for an aggregate row, for Today / Yesterday and for an app with no whole users day), its sort, the app tile
//     (inline + full-screen ÷ the app's daily users, "Format not recorded" left out; its parts add up to it; Today /
//     another stream's users: "—" + why); Users who saw ads in the drill-down (Σ ÷ Σ over the days both users reads are
//     whole; an aggregate row "—" and why; ⏳ while scr_l loads, never a reason).
//   * v 2 (owner, 6–7 Nov 2026): Imp / user / day — the 10-column Screens table on one day set (the chain exact), the
//     aggregates pinned, Today / Yesterday "—" + ads ⏳, the Full-screen table per app user, the App total block, All apps
//     from scr_all's "au", Needs attention per cause with ≈ Σ impact, the details and the chart per user, v 1 refused;
//     a users day without a time read out of the day set; per-user numbers under 1 with three places (the build's _q);
//     the aggregates' "x% of ads"; the share of the app's screen views in the details; Needs attention's W days from
//     scr_all alone; GA4's users mix hidden when GA4 ≠ AdMob.
//   * the column order (owner: users, then screen views, then the ads): every table (Screens, Full-screen, All apps, the
//     App total) on each period and file state as {row → {header → cell}} with its headers and each row's cell count, the
//     rows' own numbers, a tap on every sort header (on "sorty": five screens every column ranks differently); a row's
//     cells are read by the header they sit under everywhere, never by position.
//   * v 4 (owner, 8 Nov 2026): the one table (Users of the period, Views, Time / user, Ads, Revenue, %, Signal) with the
//     AdMob full-screen rows and the total, the signals card, a Custom range / a sampled month, the sort, the report,
//     All apps, the redraw when file 2 comes late.
// Prints ONE JSON report; tests/test_scr_frontend.py asserts on it.   usage: node scr_frontend.js <index.html>
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('const SCR=(()=>{'), b = html.indexOf('function renderScreens(){');
if (a < 0 || b < 0 || b < a) { console.log(JSON.stringify({ errors: ['SCR module not found'] })); process.exit(0); }
const MON0 = html.indexOf('// ---- the month mover'), MON1 = html.indexOf("// ---- a daily chart's period");
const MONSRC = MON0 >= 0 && MON1 > MON0 ? html.slice(MON0, MON1) : '';
const src = MONSRC + html.slice(a, b) + '\nthis.SCR=SCR;';
const out = {}, errors = [];
// ── a tiny element ──
function el(screen) {
  const e = { _html: '', dataset: screen ? { screen } : {}, style: { setProperty() {} }, isConnected: true, offsetHeight: 900, children: [],
    get innerHTML() { return e._html; }, set innerHTML(v) { e._html = String(v); },
    addEventListener(t, f) { e['on' + t] = f; }, querySelectorAll: () => [], querySelector: () => null };
  return e;
}
const SCREEN = el('scr');
let ON = 'scr', LOADS = [], FAIL = new Set(), SCROLL = [], LS = null, LS_THROW = false, EXEC = [], EXEC_OK = true, PUSHED = [], DROPPED = [];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const FILES = {};
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error, Date, parseFloat,
  setTimeout: (f) => { f(); return 0; }, clearTimeout: () => {},
  DATA: null, APP: '',
  document: {
    querySelector: s => s === '.screen.on' ? { dataset: { screen: ON } } : (s === '.screen[data-screen=scr]' ? SCREEN : null),
    getElementById: () => null,
    execCommand: c => { EXEC.push(c); return EXEC_OK; },
  },
  window: { scrollBy: (x, y) => { SCROLL.push(y); }, innerWidth: 1280, innerHeight: 800, scrollY: 0, addEventListener() {}, removeEventListener() {} },
  navigator: {},
  get localStorage() { if (LS_THROW) throw new Error('blocked'); return { getItem: k => (LS && k in LS ? LS[k] : null), setItem: (k, v) => { if (LS) LS[k] = String(v); } }; },
  SP: { quietly: f => f() },
  HB: { st: [] }, hbPush: (t) => { PUSHED.push(t); }, hbDrop: (t) => { DROPPED.push(t); },
  screenDiv: () => SCREEN,
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1]; },
  fmtMon: k => MON[+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4),
  setApp: n => { ctx.APP = n; },
  hubStChip: k => `<span class="hub-st st-${k}">${k}</span>`,
  appIconId: (id, name, size) => `<span class="aicon" data-iid="${id}" data-sz="${size}"></span>`,
  uniVis: id => id !== ID.hidden,
  appIdOf: name => { const c = (ctx.DATA && ctx.DATA.apps_catalog || []).filter(x => x.app_name === name); return c.length === 1 ? c[0].app_id : ''; },
  valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name ' + cc,
  money: n => '$' + Math.round(n).toLocaleString('en-US'), cm: (n, dp) => '$' + Number(n).toFixed(dp == null ? 2 : dp), cfx: () => 1,
  fetchGzJson: url => { const f = String(url).split('?')[0]; LOADS.push(f); if (FAIL.has(f) || !(f in FILES)) return Promise.reject(new Error('net')); return Promise.resolve(JSON.parse(JSON.stringify(FILES[f]))); },
};
vm.createContext(ctx);
// ── synthetic files ──
const D0 = '2026-01-01', FT = '2026-03-28', TD = '2026-03-30', ND = 89;
const day = k => new Date(Date.UTC(2026, 0, 1 + k)).toISOString().slice(0, 10);
const ID = { a: 'ca-app-pub-0000000000000000~21', b: 'ca-app-pub-0000000000000000~22', c: 'ca-app-pub-0000000000000000~23', d: 'ca-app-pub-0000000000000000~24',
  e: 'ca-app-pub-0000000000000000~25', h: 'ca-app-pub-0000000000000000~26', hidden: 'ca-app-pub-0000000000000000~27' };
const KEY = { a: 'a00000000001', b: 'a00000000002', c: 'a00000000003', d: 'a00000000004', e: 'a00000000005', h: 'a00000000006', hidden: 'a00000000007' };
const HOSTILE = '<img src=x onerror=alert(1)>Activity';
const READS = ['t', 'v', 'w', 'a', 'm', 'nV', 'nA', 'rV', 'rA', 'cV', 'cA', 'k', 'e', 'uV', 'uA', 's', 'x'];
function items(main) { return [[main || 'x.y.MainActivity', 's', 'inline'], ['x.y.EditorActivity', 's', 'inline'], ['', 'o', 'inline'], ['(not set)', 'ns', 'inline'],
  ['AdActivity', 'ad', 'inline'], ['(other)', 'g', 'inline'], ['Back press', 'fs', 'interstitial'], ['App resume', 'fs', 'appopen']]; }
// one app's scr_all entry: views per item, ads (inline on screens, full on triggers); opts: sampled (inline ads null every
// day, a 's'), cDays (inline null on every 3rd day: GA4 gave the screen without the format), st (read → string)
// the app's daily users per final day (varying: Σ ÷ Σ never the mean of the daily ratios), none after ft (Today / Yesterday)
const AU = Array.from({ length: 89 }, (_x, k) => (k > 86 ? null : 400 + 60 * (k % 6)));
// v 4: the periods the build offers (its pwin: today, yesterday, 7 / 30 / 60 / 90 days ending ft, this month, all time, the
// months from d0's) — the 30 days' key, the one most checks use
const P30 = '2026-02-27_2026-03-28';
const PW = [['2026-03-30_2026-03-30', '2026-03-30', '2026-03-30', 'day'], ['2026-03-29_2026-03-29', '2026-03-29', '2026-03-29', 'day'],
  ['2026-03-22_2026-03-28', '2026-03-22', '2026-03-28', 'roll'], [P30, '2026-02-27', '2026-03-28', 'roll'],
  ['2026-01-28_2026-03-28', '2026-01-28', '2026-03-28', 'roll'], ['2026-01-01_2026-03-28', '2026-01-01', '2026-03-28', 'roll'],
  ['2026-03-01_2026-03-30', '2026-03-01', '2026-03-30', 'day'], ['2026-01-01_2026-03-30', '2026-01-01', '2026-03-30', 'all'],
  ['2026-02-01_2026-02-28', '2026-02-01', '2026-02-28', 'month'], ['2026-01-01_2026-01-31', '2026-01-01', '2026-01-31', 'month']];
function mkAll(o) {
  const V = [], A = [], vis = [], ta = [];
  for (let k = 0; k < ND; k++) {
    const v = [1000 + k, 500, 300, 50, 400, 20, null, null];
    const low = k >= 79 ? 0.08 : 0.12;
    let ad = [Math.round((1000 + k) * low), 50, 30, 5, 2, 1, 40, 25];
    if (o.sampled || (o.cDays && k % 3 === 0)) ad = ad.map((x, i) => i < 6 ? null : x);
    V.push(v); A.push(ad); vis.push(1000 + k + 500 + 300 + 50 + 20);
    ta.push([Math.round((1000 + k) * low) + 50 + 30 + 5 + 2 + 1, 65, o.ns ? o.ns(k) : 0]);
  }
  const st = {}; for (const r of READS) st[r] = 'w'.repeat(ND); Object.assign(st, o.st || {});
  const bf = {}; for (const r of READS) bf[r] = [D0, true]; Object.assign(bf, o.bf || {});
  const e = { key: o.key, ft: FT, td: TD, d0: D0, items: items(o.main), vis, V, A, ta, st, bf, status: o.status || {}, app: o.app, dq: o.dq || [],
    ftu: o.ftu || FT, dk: o.dk || '0'.repeat(ND) };
  // v 2: the app's daily users per final day ≤ ftU (the App total and All apps from this file alone), else the build's why
  if (o.users) e.au = AU.slice(); else e.auw = 'none';
  // v 4: per day [GA4's revenue on every screen, AdMob's app total] (micros), the app's users per period, the signals' counts
  e.rv = Array.from({ length: ND }, (_x, k) => (k > 87 ? [500000, null] : [3000000 + 1000 * k, 3100000 + 1000 * k]));
  e.pt = { [P30]: 9000, '2026-02-01_2026-02-28': 7000 };
  e.sg = { [P30]: o.key === KEY.a ? [1, 1, 1] : [0, 0, 0] };
  if (o.nvr) e.nvr = o.nvr;
  return e;
}
function mkF2(o) {
  const screens = [[o.main || 'x.y.MainActivity', 's'], ['x.y.EditorActivity', 's'], ['x.y.Other1Activity', 's'], ['(not set)', 'ns'], ['AdActivity', 'ad'], ['(other)', 'g']];
  const units = [['unit_a', 'banner', ['ca-app-pub-0000000000000000/1001'], 'unit_a', 'name', ''],
    ['unit_b', 'interstitial', ['ca-app-pub-0000000000000000/1002'], 'unit_b', 'name', 'Back press'],
    ['unit_c', 'appopen', ['ca-app-pub-0000000000000000/1003'], 'unit_c', 'name', 'App resume'],
    ['0123456789abcdef', 'native', [], '', '', '']];
  const days = [], adm = o.noPlace ? {} : { 0: [], 1: [], 2: [] };
  for (let k = 0; k < ND; k++) {
    const g = o.cDays && k % 3 === 0 ? 'c' : o.cDays && k % 3 === 1 ? 'f' : 'fu';
    // the build's a rows: fu [class, unit, n] (the unit's format in units) · f [class, inline, full, notset] · c [class, n]
    days.push({ v: [[0, 1000 + k, 30000], [1, 500, 9000], [2, 300, 4000], [3, 50, 500], [4, 400, 2000], [5, 20, 100]],
      a: g === 'fu' ? { g, r: [[0, 0, 100], [1, 0, 50], [4, 1, 30]] } : g === 'f' ? { g, r: [[0, 100, 0, 0], [1, 50, 0, 0], [4, 0, 30, 0]] } : { g, r: [[0, 120], [1, 50]] },
      w: [[0, 160], [1, 40], [2, 25]], ta: [['banner', 160], ['interstitial', 40], ['app_open', 25]], dup: [0, 0], st: { v: 'w', a: 'w', w: 'w' } });
    if (!o.noPlace) { adm[0].push([2000, 1800, 165]); adm[1].push(k % 10 ? [100, 80, 41] : null); adm[2].push([60, 50, 25]); }
  }
  // v 4: revenue by screen per day (micros: Main 2 $, Editor 0.5 $, the ad screen 0.3 $), the AdMob full-screen
  // rows (their own days, none after the last complete AdMob day), the app's AdMob total, the users of two periods, signals
  days.forEach((d, k) => { d.m = [[0, 2000000, 2000000], [1, 500000, 500000], [4, 300000, 300000]]; d.st.m = 'w'; });
  const fsd = [Array.from({ length: ND }, (_x, k) => (k > 87 ? null : [100, 80, 41, 200000])), Array.from({ length: ND }, (_x, k) => (k > 87 ? null : [60, 50, 25, 100000]))];
  const f2 = { v: 4, key: o.key, app_id: o.id, ft: FT, td: TD, d0: D0, screens, units, trig: [['interstitial', 'Back press', [1]], ['appopen', 'App resume', [2]]], days, adm,
    pw: PW, fs4: [['interstitial', 'Back press', ['unit_b']], ['appopen', 'App resume', ['unit_c']]], fsd,
    adt: Array.from({ length: ND }, (_x, k) => (k > 87 ? null : [2160, 1930, 231, 3100000])),
    pu: { [P30]: { st: 'w', u: [[0, 3000], [1, 1500], [3, 400]], tot: 4000 }, '2026-02-01_2026-02-28': { st: 's' } },
    sig: o.key === KEY.a ? { [P30]: { s0: [['w', 'unit_a', 0.25, 0.3, 40000, 10000]], s1: [['b', 0.4, 0.01]], f0: [['d', 0.2, 0.15, '2026-01-28', '2026-02-26']] } } : {},
    rows: { s0: { st: ['Worse', 'gira', 66], z: -4.2, h: [70, 62], W: [10000, 880, 10], N: [28000, 3360, 28], cause: 'Lower fill', terms: { fill: -12.3, req: -3.1, tie: 0.4 },
      units: [[0, 2000, 2100, 0.9, 0.92, 0.092, 0.095, 0.97, 0.99]], fbd: '2026-03-20' } },
    notes: { zone: 'assumed', admob: o.noPlace ? 'none' : 'ok', allf: 0, runs: [['2026-02-01', '2026-02-05', 1, 0]], w: ['2026-03-19', FT], n: ['2026-02-19', '2026-03-18'], dq: [] } };
  // Ads / user (the build ships it in file 2): "Us" the top screens Main, Editor (screen indexes 0, 1), "U" their users per
  // FINAL day — varying by day; none every 10th day (the users read or the ads by screen not whole) and none after ft
  // (Today / Yesterday: never shipped) — and "au" the app's daily active users per final day, varying too; else "auw" why
  if (o.users) {
    f2.Us = [0, 1]; f2.U = Array.from({ length: ND }, (_x, k) => (k % 10 === 5 || k > 86 ? null : [500 + 100 * (k % 7), 200 + 30 * (k % 4)]));
    f2.au = AU.slice();
  } else f2.auw = 'none';
  return f2;
}
function mkL(o) {
  const days = [];
  for (let k = 0; k < ND; k++) days.push({
    nV: { st: 'w', g: 'c', r: [['new', 0, 300], ['returning', 0, 700 + k], ['new', 1, 100]] },
    nA: { st: 'w', g: 'cf', r: [['new', 0, 'banner', 30], ['returning', 0, 'banner', 80], ['new', 1, 'interstitial', 5]] },
    k: { st: 'w', g: 'c', r: o.noClick ? [] : [[0, 'ad_click', 3], [1, 'ad_reward', 1]], t: o.noClick ? {} : { ad_click: 3 } },
    // the users by screen and the users who saw ads by screen, varying by day (Σ ÷ Σ never the mean of the daily ratios)
    e: { st: 'w', g: 'c', r: [[0, 40000]] }, uV: { st: 'w', g: 'c', r: [[0, 900, 800 + 50 * (k % 5)], [1, 400, 350]] },
    // (Alpha's 26 Mar: GA4 sampled the users who saw ads — that day never counts in Users who saw ads)
    uA: o.key === KEY.a && k === 84 ? { st: 's', g: 'c', smp: 0.4 } : { st: 'w', g: 'c', r: [[0, 600 - 40 * (k % 3)], [1, 100]] },
    s: { st: 'w', g: 'fs', r: [['banner', 'Network A', 90], ['banner', 'Network <B>', 10], ['interstitial', 'Network A', 40]] },
    x: { st: 'w', ev: ['custom_ad_shown'], r: [[0, 'custom_ad_shown', 7]], t: [['custom_ad_shown', 9]] } });
  return { v: 4, key: o.key, d0: D0, days,
    // versions: items / same days by file 2's class index (-1 = app level)
    ver: { '1.0': { first: '2026-01-01', last: '2026-02-20', prev: null, items: { 0: [40000, 4800, 0], 1: [20000, 2000, 0], '-1': [30000, 1200, 3000] }, same_days: {} },
      '1.1<script>': { first: '2026-02-10', last: TD, prev: '1.0', items: { 0: [30000, 2700, 0], 1: [10000, 1000, 0], '-1': [30000, 2300, 2800] }, same_days: { 0: [5000, 550, 4000, 480] } } },
    ver_order: ['1.0', '1.1<script>'],
    ver_m: { '2026-02': [['1.0', 0, 10000, 1200, 0, 0], ['1.0', -1, 30000, 3000, 1200, 0]] },
    cc_m: { '2026-02': [['XA', 0, 20000, 2400, 0, 0], ['XB', 0, 8000, 800, 0, 0], ['(other)', 0, 500, 40, 0, 0], ['XA', -1, 40000, 4000, 1500, 0]] },
    shards: { r: {}, c: { 202603: 'cs1' } }, big: { r: [], c: ['202602'] }, failed: { r: ['202603'], c: [] },
    report: { app: 'App report\nline two\nline three', rows: { s0: 'Row report\nscreen x.y.MainActivity\nline 3\nline 4' } } };
}
function mkShard(key) {
  // the build's shard rows by index: V [dim, item, views] | [dim, views] (app level) · A cf [dim, item, inline, full, notset]
  const days = []; for (let j = 0; j < 30; j++) days.push({ V: { st: 'w', g: 'c', r: [[0, 0, 600], [1, 0, 300], [0, 1, 200]] }, A: { st: 'w', g: 'cf', r: [[0, 0, 70, 0, 0], [1, 0, 20, 0, 0], [0, 1, 0, 9, 0]] } });
  return { v: 1, key, m: '2026-03', dims: ['XA', 'XB'], items: [['x.y.MainActivity', 's'], ['x.y.EditorActivity', 's'], ['Other screens', 'o'], ['Not recorded', 'ns'], ['Ad screens', 'ad'], ['GA4 grouped', 'g']], days };
}
// v 2: [word, why, score, cause, its Needs attention group, impact (of the app's imp / user), W days (when given: an older
// file has none)] · the App row: [word, why, worse n, watch n, score, cause, parts, daily users move, AdMob check]
const S = (w, why, sc, cz, g, imp, dW) => [w, why, sc, cz, g == null ? cz : g, imp == null ? null : imp].concat(dW == null ? [] : [dW]);
const AP = (w, why, wn, an, more) => [w, why, wn, an].concat(more || [null, '', null, null, null]);
// Beta's why, as the build words it now (the W days it lacks, counted by their state)
const WHY_B = 'Not whole — 0 whole days of inline ads in the last 10 (GA4 sampled 10)';
const ALLF = { v: 4, apps: {
  // (Alpha: "Format not recorded" ads every 4th day — a copy-pattern day's duplicate copies: never in the app's Ads / user)
  [ID.a]: mkAll({ key: KEY.a, ns: k => (k % 4 === 0 ? 120 : 0), st: { uA: 'w'.repeat(84) + 's' + 'w'.repeat(4) }, dk: '0'.repeat(60) + '2' + '0'.repeat(28), nvr: { mix: 1.2, within: -20.5, vpu: -3.1 },
    app: AP('Worse', 'imp/user 1.20 → 0.90 (−25%) · z −5.1 · AdMob agrees (inline −28%)', 1, 1, [75, '', { avu: -2.0, adv: -23.0 }, 0.04, { st: 'agree', f: 'inline', g: -0.3, m: -0.28, gt: -0.25, mt: -0.24 }]),
    status: { 0: S('Worse', 'ads/100 34% gira', 66, 'Lower fill', 'Lower fill', -0.12, 9), 1: S('Normal', '', 99, ''), 2: S('Watch', 'thoda gira', 86, 'Fewer ad requests', 'Fewer ad requests', -0.03, 10), 6: S('Better', '', 118, ''), 7: S('Too early', 'kam data', null, '') } }),
  [ID.b]: mkAll({ key: KEY.b, sampled: true, app: AP('N/A', WHY_B, 0, 0), status: { 0: S('N/A', WHY_B, null, '') }, st: { a: 's'.repeat(ND), nA: 's'.repeat(ND), rA: 's'.repeat(ND), cA: 's'.repeat(ND) } }),
  [ID.c]: mkAll({ key: KEY.c, cDays: true, app: AP('Watch', '', 0, 1), status: { 1: S('Watch', '', 85, 'Not measurable (units not split)') },
    st: { rV: '-'.repeat(60) + 'w'.repeat(29), rA: '-'.repeat(60) + 'w'.repeat(29), cV: '-'.repeat(60) + 'w'.repeat(29), cA: '-'.repeat(60) + 'w'.repeat(29) },
    bf: { rV: ['2026-03-02', false], rA: ['2026-03-02', false], cV: ['2026-03-02', false], cA: ['2026-03-02', false] } }),
  [ID.d]: mkAll({ key: KEY.d, app: AP('Normal', '', 0, 0), dq: ['ns', 'some_new_code'], st: { e: 'w'.repeat(70) + 'p'.repeat(19) } }),
  [ID.e]: { key: KEY.e, ft: FT, td: TD, d0: null, items: [], vis: [], V: [], A: [], ta: [], st: {}, bf: { v: ['2026-03-20', false] }, status: {}, app: AP('Too early', 'history bhar rahi', 0, 0), dq: [] },
  [ID.h]: mkAll({ key: KEY.h, main: HOSTILE, app: AP('Better', '<b>bold</b>', 0, 0), status: { 0: S('Watch', '<script>x</script>', 88, '<i>cause</i>') } }),
  [ID.hidden]: mkAll({ key: KEY.hidden, app: AP('Worse', '', 5, 0) }),
} };
FILES['scr_all.json.gz'] = ALLF;
for (const k of ['a', 'b', 'c', 'd', 'h']) {
  const o = { key: KEY[k], id: ID[k], cDays: k === 'c', noPlace: k === 'd', main: k === 'h' ? HOSTILE : null, noClick: k === 'd', users: k === 'a' };
  if (k === 'a') Object.assign(ALLF.apps[ID.a], { au: AU.slice() }), delete ALLF.apps[ID.a].auw;
  FILES['scr_' + KEY[k] + '.json.gz'] = mkF2(o); FILES['scr_l_' + KEY[k] + '.json.gz'] = mkL(o);
}
FILES['scr_c_' + KEY.a + '_202603.json.gz'] = mkShard(KEY.a);
const CAT = [['a', 'Alpha App'], ['b', 'Beta App'], ['c', 'Gamma App'], ['d', 'Delta App'], ['e', 'Empty App'], ['h', 'Hostile App'], ['hidden', 'Hidden App']]
  .map(([k, n]) => ({ app_id: ID[k], app_name: n }));
const PTR = { v: 2, file: 'scr_all.json.gz', fv: 'f1', apps: {} };
for (const k of ['a', 'b', 'c', 'd', 'e', 'h']) PTR.apps[ID[k]] = { key: KEY[k], v: 'v' + k, vl: 'l' + k, from: D0, ft: FT };
const tick = async (n = 4) => { for (let i = 0; i < n; i++) await new Promise(r => setImmediate(r)); };
const names = h => [...h.matchAll(/<tr class="sc-clk" data-sc-app="([^"]+)"/g)].map(m => m[1]);
(async () => {
  try {
    vm.runInContext(src, ctx);
    const SCR = ctx.SCR, _ = SCR._;
    // ── the pointer ──
    ctx.DATA = {}; out.no_ptr = SCR.ptr() === null;
    ctx.DATA = { scr: { file: '../x.json.gz', apps: {} } }; out.bad_file = SCR.ptr() === null;
    ctx.DATA = { scr: { file: 'scr_all.json.gz', fv: 'f1' } }; out.no_apps = SCR.ptr() === null;
    SCR.render(); ctx.DATA = {}; SCR.paint(); out.no_ptr_note = SCREEN.innerHTML.includes('Screens ka data is build me nahi bana');
    // ── a failed load, then Try again ──
    ctx.DATA = { scr: PTR, apps_catalog: CAT, generated_at: '2026-03-30T06:00:00Z' };
    // a v 1 scr_all (an older build's: ads per 100 views) is refused, never mislabelled — "Data load nahi hua" + Try again
    FILES['scr_all.json.gz'] = Object.assign({}, ALLF, { v: 2 }); SCR.paint(); await tick(); out.v1_all = SCREEN.innerHTML.includes('data-sc-allretry');
    FILES['scr_all.json.gz'] = ALLF;
    FAIL.add('scr_all.json.gz'); SCR.paint(); out.loading = SCREEN.innerHTML.includes('⏳ Loading…') || SCREEN.innerHTML.includes('data-sc-allretry'); await tick();
    out.fail_html = SCREEN.innerHTML.includes('data-sc-allretry');
    FAIL.clear(); SCREEN.onclick({ target: { closest: s => s === '[data-sc-allretry]' ? {} : null } }); await tick();
    out.loads_all = LOADS.filter(f => f === 'scr_all.json.gz').length;
    // ── the picker ──
    const x = ALLF.apps[ID.a], R = (k, f, t) => _.rng(x, k, f || '', t || '');
    out.rng = { today: R('today'), yday: R('yday'), '7': R('7'), tm: R('tm'), lm: R('lm'), '30': R('30'), '60': R('60'), '90': R('90'), all: R('all'),
      cus: R('cus', '2026-03-20', '2026-03-10'), cus_clamp: R('cus', '2025-06-01', '2027-01-01'), cus_empty: R('cus'), mon_feb: R('mon:2026-02'), mon_mar: R('mon:2026-03'), bogus: R('zz') };
    out.notfinal = Object.fromEntries(['today', 'yday', '7', '30', 'tm'].map(k => [k, R(k)[1] > x.ft]));
    out.norm = { d7: _.normWin(x, '2026-03-22', '2026-03-28'), d30: _.normWin(x, '2026-02-27', '2026-03-28'), today: _.normWin(x, TD, TD), d60: _.normWin(x, '2026-01-28', '2026-03-28') };
    const ps = (lo, hi, all) => { const p = _.perScore(x, 1, lo, hi, all); return { muted: p.muted, fin: p.fin, score: p.score }; };
    out.muted = { today: ps(TD, TD), d7: ps('2026-03-22', '2026-03-28'), short: ps('2026-03-25', TD), all: ps(D0, TD, true) };
    // the sums: Gamma's screen-only days (every 3rd) carry no inline ads
    const xc = ALLF.apps[ID.c], si = _.sumItem(xc, 1, '2026-02-27', '2026-03-28');
    out.sum_c = [si.v, si.a, si.n, si.nv, si.nd, si.vAll, si.rate];
    const sa = _.sumItem(ALLF.apps[ID.b], 0, '2026-02-27', '2026-03-28'); out.sum_sampled = [sa.v, sa.a, sa.n, sa.rate, sa.vAll];
    const sf = _.sumItem(ALLF.apps[ID.b], 6, '2026-02-27', '2026-03-28'); out.sum_fs = [sf.v, sf.a, sf.n, sf.rate];
    // ── status words, order ──
    out.wdk = _.WDK; out.rank = _.RANK;
    // ── All apps ──
    ctx.APP = ''; _.set({ PER: '30', PREAD: true }); SCR.paint();
    let h = SCREEN.innerHTML; out.all_html = h.length;
    out.all_rows = names(h); out.all_hidden = h.includes('Hidden App');
    out.all_icons = [...h.matchAll(/data-sc-app="[^"]+"[^>]*><td class="sc-nm"><span class="sc-an"><span class="aicon" data-iid="([^"]+)"/g)].map(m => m[1]);
    out.all_chips = [...h.matchAll(/<tr class="sc-clk" data-sc-app="[^"]+"[^>]*><td class="sc-nm">.*?<span class="sc-stl"><span class="hub-st st-([a-z]+)">/g)].map(m => m[1]);
    out.cov = [...h.matchAll(/data-sc-cov="([a-z])"[^>]*><span>([^<]+)<\/span> <b>(\d+)\/(\d+)<\/b>/g)].map(m => [m[1], +m[3], +m[4]]);
    const L = Object.keys(ALLF.apps).filter(id => id !== ID.hidden).map(id => ({ id, x: ALLF.apps[id], name: id }));
    out.cov_fn = _.coverAll(L).map(c => [c.code, c.w, c.m]);
    out.all_hostile_why = h.includes('&lt;b&gt;bold&lt;/b&gt;') && !h.includes('<b>bold</b>');
    out.all_hist = [...h.matchAll(/<td><span title="[^"]*">([^<]+)<\/span><\/td><\/tr>/g)].map(m => m[1]);   // the History column
    out.all_period = /30 days \(GA4 · 27 Feb – 28 Mar\)/.test(h);
    out.all_why_b = (/<tr class="sc-clk" data-sc-app="Beta App"[^>]*>.*?<\/span><\/span><small>([^<]*)<\/small><\/td>/.exec(h) || [])[1] || null;   // its why, under the name
    // the coverage chip: the apps not whole with why
    _.set({ COVP: 'r' }); SCREEN.paint ? 0 : 0; SCR.paint(); h = SCREEN.innerHTML;
    const covl = h.slice(h.indexOf('id="sc-covl"'));
    out.cov_list = [...covl.matchAll(/<div class="sc-covr"><span class="sc-an"><span class="aicon" data-iid="([^"]+)"[^>]*><\/span><span>[^<]*<\/span><\/span><small>([^<]*)<\/small>/g)].map(m => [m[1], m[2]]);
    _.set({ COVP: '' });
    // sort order: by status (Worse first) and a column
    out.sort_rank = out.all_rows;
    _.set({ SORT: { k: 'dau', dir: -1 } }); SCR.paint(); out.sort_v = names(SCREEN.innerHTML); _.set({ SORT: { k: 'rank', dir: 1 } });
    // All time: no score
    _.set({ PER: 'all' }); SCR.paint(); out.all_time = SCREEN.innerHTML.includes('All time pe own past nahi — vs own past ke liye koi aur period chunein') && !SCREEN.innerHTML.includes('normal nahi') && !/score <b/.test(SCREEN.innerHTML); _.set({ PER: '30' });
    // a row tap opens the app
    SCREEN.onclick({ target: { closest: s => s === 'tr[data-sc-app]' ? { dataset: { scApp: 'Gamma App' } } : null } });
    out.row_tap = ctx.APP;
    // ── app pages: every app, every section, every fold ──
    const pages = {};
    for (const k of ['a', 'b', 'c', 'd', 'e', 'h']) {
      const nm = CAT.find(c => c.app_id === ID[k]).app_name; ctx.APP = nm; _.set({ OPEN: null, SEC: 'ov', SEG: 's', MORE: false });
      SCR.paint(); await tick(8); SCR.paint();
      const pg = { html: SCREEN.innerHTML.length, sections: {}, errors: [] };
      pg.empty = SCREEN.innerHTML.includes('Is app ka Screens data abhi aa raha hai');
      pg.attn = SCREEN.innerHTML.includes('id="sc-attn"'); pg.ok_all = SCREEN.innerHTML.includes('✅ Is period me koi signal nahi');
      pg.rows = [...SCREEN.innerHTML.matchAll(/<tr class="sc-clk[^"]*" data-sc-open="(\d+)"/g)].map(m => +m[1]);
      pg.more = (/Show (\d+) more screens/.exec(SCREEN.innerHTML) || [])[1] || null;
      pg.basis = (/<b>[\d.,]+<\/b><small>(\d+\/\d+ [a-z]+)<\/small>/.exec(SCREEN.innerHTML.slice(SCREEN.innerHTML.indexOf('id="sc-ttw"'))) || [])[1] || null;   // a row's days
      pg.crumb = (/<div class="sc-crumb">.*?<\/span> <small>([^<]*)<\/small> · history/.exec(SCREEN.innerHTML) || [])[1] || null;   // the app's why
      pg.attn_why = (/Abhi koi screen judge nahi ho saki: ([^<]*) — numbers neeche hain/.exec(SCREEN.innerHTML) || [])[1] || null;
      if (k !== 'e') {
        for (const seg of ['s', 'f']) for (const i of [0, 1, 2, 3, 6]) for (const [sec] of _.SECS) {
          _.set({ SEG: seg, OPEN: i, SEC: sec });
          try { SCR.paint(); await tick(4); SCR.paint(); pg.sections[sec + ':' + i] = SCREEN.innerHTML.slice(SCREEN.innerHTML.indexOf('id="sc-dd"')); }
          catch (e) { pg.errors.push(sec + ':' + i + ' ' + e.message); }
        }
      }
      pg.loaded = LOADS.filter(f => f.includes(KEY[k]));
      pages[k] = pg;
    }
    out.pages = Object.fromEntries(Object.entries(pages).map(([k, p]) => [k, { html: p.html, empty: p.empty, attn: p.attn, ok_all: p.ok_all, rows: p.rows, more: p.more, basis: p.basis, crumb: p.crumb, attn_why: p.attn_why, errors: p.errors, loaded: [...new Set(p.loaded)], n_sections: Object.keys(p.sections).length }]));
    const sec = (k, s) => pages[k].sections[s] || '';
    out.alpha = {
      ov_terms: sec('a', 'ov:0').includes('Lower fill') && sec('a', 'ov:0').includes('−12.3%') && sec('a', 'ov:0').includes('First bad day: <b>20 Mar 2026</b> (us din se imp / user'),
      ov_months: [...sec('a', 'ov:0').matchAll(/<td class="sc-nm">([A-Z][a-z]{2} \d{4}) <small>· (\d+)d<\/small>/g)].map(m => [m[1], +m[2]]),
      ov_days: (sec('a', 'ov:0').match(/<td class="sc-nm[^"]*">\d+ [A-Z][a-z]{2} 2026/g) || []).length,
      ov_first_day: (/<td class="sc-nm[^"]*">(\d+ [A-Z][a-z]{2} 2026)/.exec(sec('a', 'ov:0').slice(sec('a', 'ov:0').indexOf('id="sc-dtw"'))) || [])[1],
      un: [...sec('a', 'un:0').matchAll(/<tr><td class="sc-nm"><span class="sc-n">([^<]+)<\/span>/g)].map(m => m[1]),
      un_cz: (/Units in the status window[\s\S]*?<tr><td class="sc-nm"><span class="sc-n">unit_a<\/span><\/td>(.*?)<\/tr>/.exec(sec('a', 'un:0')) || [])[1] || null,
      un_fs: [...sec('a', 'un:6').matchAll(/<tr><td class="sc-nm"><span class="sc-n">([^<]+)<\/span>/g)].map(m => m[1]),
      un_row: (/<tr><td class="sc-nm"><span class="sc-n">unit_a<\/span>.*?<\/tr>/.exec(sec('a', 'un:0')) || [''])[0],
      ver: sec('a', 'ver:0').includes('1.1&lt;script&gt;') && !sec('a', 'ver:0').includes('1.1<script>') && sec('a', 'ver:0').includes('picker yahan lagu nahi'),
      ver_same: /10\.0 vs 11\.0 <small>−9%<\/small>|11\.0 vs 12\.0/.test(sec('a', 'ver:0')) ? (/([\d.]+) vs ([\d.]+) <small>([^<]+)<\/small>/.exec(sec('a', 'ver:0')) || []).slice(1) : (/([\d.]+) vs ([\d.]+) <small>([^<]+)<\/small>/.exec(sec('a', 'ver:0')) || []).slice(1),
      cc_notes: [sec('a', 'cc:0').includes('Feb 2026: din-wise file bahut badi thi'), sec('a', 'ver:0').includes('Mar 2026: is build me file nahi ban saki')],
      cc: [...sec('a', 'cc:0').matchAll(/<tr><td class="sc-nm">([^<]+)<\/td><td>([^<]+)<\/td><td>([^<]+)<\/td><td><b>([^<]+)<\/b>/g)].map(m => m.slice(1)),
      nvr: [...sec('a', 'nvr:0').matchAll(/<tr><td class="sc-nm">([^<]+)<\/td><td>([^<]+)<\/td><td>([^<]+)<\/td>/g)].map(m => m.slice(1)),
      eng: [...sec('a', 'eng:0').matchAll(/<div class="sc-kl">([^<]+)<\/div><div class="sc-kv">([^<]*)<\/div>/g)].map(m => m.slice(1)),
      // Users who saw ads: a top screen (Σ ÷ Σ over the days both users reads are whole) · an aggregate row (none)
      eng_users: ['eng:0', 'eng:2'].map(s => (/<div class="sc-k"(?: title="([^"]*)")?><div class="sc-kl">Users who saw ads<\/div><div class="sc-kv">([^<]*)<\/div><div class="sc-ks">([^<]*)<\/div>/.exec(sec('a', s)) || []).slice(1)),
      x: sec('a', 'x:0').includes('custom_ad_shown'),
      rep: sec('a', 'rep:0').includes('data-sc-copy="row"') && sec('a', 'rep:0').includes('5 lines') && !/data-sc-copy="row"[^>]*disabled/.test(sec('a', 'rep:0')),
      rep_none: sec('a', 'rep:2').includes('Is row pe is period me koi signal nahi'),
      // the row's share of the app's screen views in the Ads / 100 tile: a screen, an aggregate row — never a trigger
      ov_share: ['ov:0', 'ov:2', 'ov:6'].map(s => (/<br>([\d.]+%) of the app's screen views/.exec(sec('a', s)) || [])[1] || null),
      // the Overview tiles' order: a screen, an aggregate row, a trigger
      ov_tiles: ['ov:0', 'ov:2', 'ov:6'].map(s => [...sec('a', s).matchAll(/<div class="sc-kl">([^<]+)<\/div>/g)].map(m => m[1])),
    };
    // labels in simple English (owner rule); the faint hints / why lines stay Hinglish
    out.labels = {
      terms: sec('a', 'ov:0').includes('<th>Part of the change</th><th>% of normal ads per view</th>'),
      un: sec('a', 'un:0').includes("<th>GA4 ads (this row)</th><th>Share of the unit's ads</th><th>Requests / day</th>")
        && sec('a', 'un:6').includes('<th>GA4 ads</th><th>Requests / day</th>'),
      cz: sec('a', 'un:0').includes('<h4 class="sc-h4">Units in the status window <small class="sc-faint">pichhle 10 final din vs 28 pehle (cause inhi se)</small></h4>'),
      ver: sec('a', 'ver:0').includes('<h4 class="sc-h4">This period · by version</h4>')
        && sec('a', 'ver:0').includes('<h4 class="sc-h4">Every version · whole life <small class="sc-faint">(picker yahan lagu nahi)</small></h4>')
        && sec('a', 'ver:0').includes('<th>Same days: this vs previous</th>') && sec('a', 'ver:0').includes('<p class="sc-note">"Same days" = jin dino dono versions'),
    };
    out.shard_loads = LOADS.filter(f => /^scr_c_/.test(f));
    out.delta = { un_noplace: sec('d', 'un:0').includes('AdMob data (placements) nahi'), eng_noclick: sec('d', 'eng:0').includes('ad_click log nahi hua') };
    out.gamma = { un_split: sec('c', 'un:1').includes('units not split'), ov_why: sec('c', 'ov:1').includes('format not split'),
      month_days: [...sec('c', 'ov:1').matchAll(/<small>(\d+\/\d+ [a-z]+)<\/small><\/td><\/tr>/g)].map(m => m[1]) };
    out.beta = { tbl_null: sec('b', 'ov:0').includes('GA4 sampled') };
    // the app page parts on Alpha (30 days)
    ctx.APP = 'Alpha App'; _.set({ OPEN: null, SEG: 's', MORE: false, SEC: 'ov', PER: '30' }); SCR.paint(); h = SCREEN.innerHTML;
    out.a_page = {
      crumb: h.includes('data-sc-all="1"') && h.includes('history from 1 Jan 2026'),
      total: h.includes('id="sc-total"') && h.includes('<tr><td>Imp / user / day</td>') && h.includes('<tr><td>Daily users</td>') && h.includes('<tr><td>Views / user / day</td>'),
      attn: [...h.slice(h.indexOf('id="sc-attn"'), h.indexOf('id="sc-tcard"')).matchAll(/<span class="hub-st st-([a-z]+)">[a-z]+<\/span><span class="sc-atn"[^>]*>([^<]+(?:<wbr>[^<]+)*)<\/span><span class="sc-atr">([^<]+)<\/span>/g)].map(m => [m[1], m[2].replace(/<wbr>/g, ''), m[3]]),
      mini: h.includes('<th>Today <small>30 Mar</small></th>') && h.includes('<th>Yesterday <small>29 Mar</small></th>') && h.includes('<th>Normal <small>')
        && h.includes('daily users ~2 din baad aate hain'),
      seg: /data-sc-seg="s" aria-pressed="true">Screens <small>6<\/small>/.test(h) && /data-sc-seg="f" aria-pressed="false">Full-screen <small>2<\/small>/.test(h),
      rows: [...h.matchAll(/<tr class="sc-clk[^"]*" data-sc-open="(\d+)"/g)].map(m => +m[1]),
      wbr: h.includes('Main</span>') || h.includes('<span class="sc-n">Main</span>'),
      editor: h.includes('<span class="sc-n">Editor</span>'),
      title: h.includes('title="x.y.MainActivity"'),
      unjudged: (h.match(/not judged/g) || []).length,
      folds: [...h.matchAll(/data-sc-fold="([a-z]+)"/g)].map(m => m[1]),
      how: h.includes('5:30 AM IST se agle din 5:30 AM IST tak') && h.includes('GA4 data till <b>28 Mar 2026</b>') && h.includes('Build: 30 Mar 11:30 IST'),
      // how a day that is not whole reads: the N/A line and the score's days (never "GA4 sampled" for every such day)
      how_na: [(/Kam data = Too early; ([^<]*) = N\/A\./.exec(h) || [])[1] || null],
      how_v2: h.includes('<b>Imp / user / day</b>: screen row pe us screen ke ads ÷ us screen ke users') && h.includes('<b>Chain</b>: Views / user / day × Time / view × Ads / min ÷ 60')
        && h.includes('app ke imp / user ka ≥ 1% ho; aur 2 din lagatar ho') && h.includes('"Worse (AdMob)"'),
      cov_fold: h.includes('<td class="sc-nm">Screen views</td><td>30</td><td>0</td><td>0</td><td>0</td>'),
      rep_fold: h.includes('data-sc-copy="app"') && h.includes('3 lines'),
      src_fold: h.includes('Network &lt;B&gt;') && !h.includes('Network <B>'),
      notes: h.includes('AdMob account ka time zone nahi mila') && h.includes('Duplicate ad_impression 1 Feb 2026 – 5 Feb 2026: AdMob se confirm (copy hata di).'),
      period: h.includes('30 days (GA4 · 27 Feb – 28 Mar)'),
      cus_row: h.includes('data-sc-pf="1" aria-label="From" value="2026-02-27"') && h.includes('data-sc-pto="1" aria-label="To" value="2026-03-28"'),
      mover: [...h.matchAll(/data-sc-per="(mon:[^"]+)" aria-pressed="(true|false)"( disabled)? aria-label="([^"]+)">([^<]+)</g)].map(m => [m[1], m[2], !!m[3], m[5]]),
      chips: [...h.matchAll(/class="sc-pb" data-sc-per="([^"]+)"/g)].map(m => m[1]),
    };
    // Show more / the 90 % split on a screen-heavy period
    _.set({ MORE: true }); SCR.paint(); out.a_more_rows = [...SCREEN.innerHTML.matchAll(/<tr class="sc-clk[^"]*" data-sc-open="(\d+)"/g)].map(m => +m[1]); _.set({ MORE: false });
    // ── v 2: Imp / user / day (owner, 6–7 Nov 2026) — the Screens table's 10 columns on ONE day set (the chain holds), the
    // aggregates pinned with "x % of the screen ads", Today / Yesterday "—" + ads ⏳, the Full-screen table's 5 columns
    // per app user, the App total block from scr_all alone (3 rows, its parts adding up, copy days left out), All apps
    // from scr_all's "au", Needs attention one line per cause with ≈ Σ impact, the chart per user ──
    const tds = (hh, i) => [...((new RegExp('<tr class="sc-clk[^"]*" data-sc-open="' + i + '"[^>]*>(.*?)</tr>').exec(hh) || [])[1] || '')
      .matchAll(/<td((?: [^>]*)?)>(.*?)<\/td>/g)].map(m => [m[1], m[2]]);
    const F2A = () => _.FILES['scr_' + KEY.a + '.json.gz'].raw, P30 = ['2026-02-27', '2026-03-28'];
    const heads = hh => [...(/<thead><tr>(.*?)<\/tr><\/thead>/.exec(hh.slice(hh.indexOf('id="sc-ttw"'))) || [, ''])[1].matchAll(/<th[^>]*>(?:<button[^>]*>)?([^<]*)/g)].map(m => m[1]);
    // a row's cells by the header they sit under, {header → cell} — never by position (the owner's column order, users →
    // views → time → ads → Imp / user / day, is checked on its own): the Screens / Full-screen table (#sc-ttw), All apps
    const txt = s => String(s).replace(/<small[^>]*>.*?<\/small>/g, '').replace(/<[^>]+>/g, '').trim();
    const hdOf = (hh, id) => { const s = hh.indexOf('id="' + id + '"'), t = s < 0 ? '' : hh.slice(s, hh.indexOf('</table>', s));
      return [...((/<thead><tr>(.*?)<\/tr><\/thead>/.exec(t) || [, ''])[1]).matchAll(/<th([^>]*)>(.*?)<\/th>/g)].map(m => txt(m[2])); };
    const by = (H, cs) => Object.fromEntries(cs.map((c, j) => [H[j] == null ? '#' + j : H[j], c]));
    const cm = (hh, i) => by(hdOf(hh, 'sc-ttw'), tds(hh, i).map(c => c[1]));
    const am = (hh, n) => by(hdOf(hh, 'sc-atw'), [...((new RegExp('<tr class="sc-clk" data-sc-app="' + n + '"[^>]*>(.*?)</tr>').exec(hh) || [])[1] || '')
      .matchAll(/<td(?: [^>]*)?>(.*?)<\/td>/g)].map(m => m[1]));
    { ctx.APP = 'Alpha App'; _.set({ OPEN: null, SEG: 's', MORE: true, PER: '30', TS: { k: 'st', dir: 1 } }); SCR.paint(); await tick(); SCR.paint(); h = SCREEN.innerHTML;
      const f2 = F2A(), k0 = 57, k1 = 86;                                    // 27 Feb … 28 Mar on Alpha's calendar
      // by hand: Main's ads ÷ its users on the days file 2 gives them (every day has its time read)
      let a = 0, u = 0, v = 0, g = 0, n = 0; for (let k = k0; k <= k1; k++) { const r = f2.U[k]; if (!r || !(r[0] > 0)) continue; a += x.A[k][0]; u += r[0]; v += x.V[k][0]; g += f2.days[k].v[0][2]; n++; }
      const s0 = _.sumScr(x, f2, 0, ...P30), s1 = _.sumScr(x, f2, 1, ...P30), tm = _.sumScr(x, f2, 0, '2026-03-01', TD);
      // a day with the screen's users but no time read — file 2's "v" missing (day 70), or views without engagement anywhere
      // (day 71: a GA4 gap, never "0 s") — is left out of the one day set: n, the ads, the users, Time / view
      const f2t = JSON.parse(JSON.stringify(f2)); delete f2t.days[70].v; f2t.days[71].v = f2t.days[71].v.map(q => [q[0], q[1], 0]);
      const st_ = _.sumScr(x, f2t, 0, ...P30);
      let a7 = 0, u7 = 0, v7 = 0, g7 = 0, n7 = 0; for (let k = k0; k <= k1; k++) { const r = f2.U[k]; if (!r || !(r[0] > 0) || k === 70 || k === 71) continue; a7 += x.A[k][0]; u7 += r[0]; v7 += x.V[k][0]; g7 += f2.days[k].v[0][2]; n7++; }
      out.v2 = { heads: heads(h), main: cm(h, 0), other: cm(h, 2), hand: [a / u, n, v / u, g / v, a / (g / 60), u / n], fn: [s0.r, s0.n, s0.vu, s0.tv, s0.am, s0.ud, s0.nd],
        notime: { fn: [st_.n, st_.r, st_.tv, st_.u], hand: [n7, a7 / u7, g7 / v7, u7], users: [f2t.U[70] && f2t.U[70][0], f2t.U[71] && f2t.U[71][0]] },
        chain: [_.chainOf(s0) / s0.r - 1, _.chainOf(s1) / s1.r - 1, _.chainOf(tm) / tm.r - 1, s0.tu * s0.am / 60 / s0.r - 1], tm_n: [tm.n, tm.nd],
        reach: [s0.reach, (() => { let du = 0, d = 0; for (let k = k0; k <= k1; k++) { const r = f2.U[k]; if (r && r[0] > 0 && AU[k] > 0) { du += r[0]; d += AU[k]; } } return du / d; })()],
        agg: [_.sumScr(x, f2, 2, ...P30).agg, _.sumScr(x, f2, 2, ...P30).r], nofile: [_.sumScr(x, null, 0, ...P30).wait, _.sumScr(x, null, 0, ...P30).r],
        share: (() => { let t = 0, o = 0; for (let k = k0; k <= k1; k++) { for (let i = 0; i < 6; i++) t += x.A[k][i]; o += x.A[k][2]; } return o / t; })(),
        th_r: (/<th aria-sort="none" title="([^"]*)"><button type="button" data-sc-tsort="r">/.exec(h) || [])[1] || null };
      // the aggregates stay pinned at the bottom (Other · Not recorded · Ad screens · GA4 grouped) under every sort
      out.v2.pinned = {}; for (const [kk, d] of [['r', -1], ['r', 1], ['ud', -1], ['tv', 1], ['am', -1], ['st', -1], ['name', 1]]) { _.set({ TS: { k: kk, dir: d } }); out.v2.pinned[kk + d] = _.sortItems(_.tableRows(x, ...P30, 's', f2)).map(z => z.i); }
      _.set({ TS: { k: 'st', dir: 1 } });
      // the Full-screen table: 5 columns, per app user
      _.set({ SEG: 'f' }); SCR.paint(); h = SCREEN.innerHTML; const t6 = _.sumTrig(x, 6, ...P30);
      let ta6 = 0, ua6 = 0; for (let k = k0; k <= k1; k++) { ta6 += x.A[k][6]; ua6 += AU[k]; }
      out.v2.fs = { heads: heads(h), cell: cm(h, 6), fn: [t6.r, t6.n], hand: ta6 / ua6, th: (/<th aria-sort="none" title="([^"]*)"><button type="button" data-sc-tsort="r">/.exec(h) || [])[1] || null };
      _.set({ SEG: 's' });
      // Today / Yesterday: no users — the main cell "—" + "ads N ⏳", the chain columns "—"
      for (const [kk, kd] of [['today', 88], ['yday', 87]]) { _.set({ PER: kk }); SCR.paint(); out.v2[kk] = { cells: cm(SCREEN.innerHTML, 0), ads: x.A[kd][0] }; }
      _.set({ PER: '30' }); SCR.paint(); h = SCREEN.innerHTML;
      // the App total: 3 rows · the period, Normal, 7 days, Yesterday, Today (no daily users yet: "—" + the ads so far ⏳)
      const tot = h.slice(h.indexOf('id="sc-total"'), h.indexOf('id="sc-attn"')), P = _.appU(x, ...P30);
      let il = 0, fl = 0, ns = 0, uu = 0, cp = 0; for (let k = k0; k <= k1; k++) { il += x.ta[k][0]; fl += x.ta[k][1]; if (k === 60) cp++; else ns += x.ta[k][2]; uu += AU[k]; }
      out.v2.total = { rows: [...tot.matchAll(/<tr><td>([^<]+)<\/td>/g)].map(m => m[1]), heads: [...tot.matchAll(/<th>([^<]+) <small>/g)].map(m => m[1]),
        imp: [...((/<tr><td>Imp \/ user \/ day<\/td>(.*?)<\/tr>/.exec(tot) || [])[1] || '').matchAll(/<td(?: title="([^"]*)")?>(.*?)<\/td>/g)].map(m => [m[1] || '', m[2]]),
        fn: [P.r, P.ir, P.fr, P.nr, P.ud, P.n, P.cp], hand: [(il + fl + ns) / uu, uu / 30, cp], note: tot.includes(_.PU ? 'daily users ~2 din baad aate hain' : ''),
        nvr: tot.includes('New vs returning (ads / 100 views): new-user mix <b>+1.2%</b> · within groups <b>−20.5%</b> · views / user −3.1%'),
        tiles: [...tot.matchAll(/<div class="sc-kl">((?:Inline|Full-screen|Not recorded) \/ user)<\/div><div class="sc-kv">([^<]*)<\/div>/g)].map(m => m.slice(1)),
        crumb: (/<div class="sc-crumb">(.*?)<\/div>/.exec(h) || [])[1] || '', no_tiles: !h.includes('id="sc-tiles"') && !h.includes('Today · Yesterday · 7 days') };
      // Needs attention: the App row first, then one line per (word, cause group) with ≈ Σ impact; the rows open under it
      const at = h.slice(h.indexOf('id="sc-attn"'), h.indexOf('id="sc-tcard"'));
      out.v2.attn = { app: (/<div class="sc-at sc-ata">(.*?)<\/div>/.exec(at) || [])[1] || null, groups: [...at.matchAll(/<summary><span class="hub-st st-([a-z]+)">[a-z]+<\/span><span class="sc-atn">([^<]+)<\/span><span class="sc-atr">([^<]+)<\/span>/g)].map(m => m.slice(1)) };
      const xg = JSON.parse(JSON.stringify(x)); xg.status['6'] = ['Worse', 'imp/app user 0.10 → 0.06 (−40%) · z −6.0', 60, 'Mixed: Lower fill + Fewer ad requests', 'Lower fill', -0.021];
      const ag = _.attnHtml(xg, null);
      out.v2.attn.sum = [...ag.matchAll(/<summary><span class="hub-st st-([a-z]+)">[a-z]+<\/span><span class="sc-atn">([^<]+)<\/span><span class="sc-atr">([^<]+)<\/span>/g)].map(m => m.slice(1));
      const atl = hh => [...hh.matchAll(/<div class="sc-atl"><span class="sc-atn"[^>]*>([^<]+(?:<wbr>[^<]+)*)<\/span><span class="sc-atr">([^<]+)<\/span>/g)].map(m => [m[1].replace(/<wbr>/g, ''), m[2]]);
      out.v2.attn.list = atl(ag);
      // the W days come from scr_all's status alone: a status without them prints none — never file 2's (loaded here: its
      // row s0 has W days 10), which arrives after the first paint and never redraws this card
      const xd = JSON.parse(JSON.stringify(x)); xd.status['0'] = xd.status['0'].slice(0, 6);
      out.v2.attn.no_dw = atl(_.attnHtml(xd, ID.a)); out.v2.attn.f2_w = F2A().rows.s0.W[2];
      const xn = JSON.parse(JSON.stringify(x)); xn.app = AP('N/A', 'Not measurable (GA4 ≠ AdMob) — GA4 +30% ≠ AdMob −40% — GA4 logging changed', 0, 0); xn.status = {};
      out.v2.attn.na = (/<div class="sc-at sc-ata">(.*?)<\/div>/.exec(_.attnHtml(xn, null)) || [])[1] || null;
      const xb = JSON.parse(JSON.stringify(x)); xb.app = AP('Worse', 'AdMob imp/user 4.0 → 2.1 (−48%) · z −8.0 · GA4 +35% ≠ AdMob −48% — GA4 logging changed', 0, 0, [52, 'GA4 logging changed', null, null, { st: 'admob' }]);
      out.v2.attn.admob = (/<div class="sc-at sc-ata">(.*?)<\/div>/.exec(_.attnHtml(xb, null)) || [])[1] || null;
      // All apps: drawn from scr_all alone (its "au": no file 2 asked for), the App row's word, "(AdMob)", a data N/A's score muted
      ctx.APP = ''; const l0 = LOADS.length; _.set({ PER: '30', SORT: { k: 'rank', dir: 1 } }); SCR.paint(); h = SCREEN.innerHTML;
      out.v2.all = { heads: [...(/<table class="sc-t"><thead><tr>(.*?)<\/tr>/.exec(h.slice(h.indexOf('id="sc-atw"'))) || [, ''])[1].matchAll(/<button type="button" data-sc-sort="([a-z]+)">([^<]+)/g)].map(m => [m[1], m[2]]),
        alpha: am(h, 'Alpha App'), loads: LOADS.slice(l0), fn: _.PQ(P.r),
        mute: (() => { const r = _.appRow({ id: ID.a, name: 'Alpha App', x: Object.assign({}, x, { app: AP('N/A', 'Logging changed — duplicate ad_impression logging started 2026-03-10', 0, 0) }) }); return [!!r.mute, r.sc, r.ru != null]; })(),
        keep: (() => { const r = _.appRow({ id: ID.a, name: 'Alpha App', x: Object.assign({}, x, { app: AP('N/A', WHY_B, 0, 0) }) }); return [!!r.mute, r.sc != null]; })(),
      };
      { const xp = _.apps().find(r => r.id === ID.a).x, keepApp = xp.app; xp.app = AP('Worse', 'AdMob imp/user 4.0 → 2.1', 0, 0, [52, '', null, null, { st: 'admob' }]);
        try { SCR.paint(); out.v2.all.admob = /data-sc-app="Alpha App"[^>]*><td class="sc-nm">.*?<span class="sc-stl"><span class="hub-st st-bigda">bigda<\/span> <small class="sc-adm">\(AdMob\)<\/small>/.test(SCREEN.innerHTML);
          // an AdMob-judged App row (B3): its GA4 period score is muted like a data N/A's (S3) — All apps, the App total, the
          // crumb's "vs" and the details' Ads / 100 scores; the GA4 Imp / user number stays
          const ac = am(SCREEN.innerHTML, 'Alpha App');
          ctx.APP = 'Alpha App'; SCR.paint(); const hp = SCREEN.innerHTML, tp = hp.slice(hp.indexOf('id="sc-total"'), hp.indexOf('id="sc-attn"'));
          const c0 = (/<tr><td>Imp \/ user \/ day<\/td><td[^>]*>(.*?)<\/td>/.exec(tp) || [])[1] || '';
          out.v2.all.admob_mute = { all: [ac['Imp / user / day'], ac['Low'], _.appRow({ id: ID.a, name: 'Alpha App', x: xp }).sc], total: c0,
            crumb: (/<div class="sc-crumb">(.*?)<\/div>/.exec(hp) || [])[1] || '', tile: (/<div class="sc-kl">Ads \/ 100 views<\/div><div class="sc-kv">[^<]*<\/div><div class="sc-ks">(.*?)<\/div><\/div>/.exec(tp) || [])[1] || '',
            // GA4's new vs returning split comes from the GA4 logging that changed: not in the details (nor Needs attention)
            nvr: [tp.includes('New vs returning'), hp.slice(hp.indexOf('id="sc-attn"'), hp.indexOf('id="sc-tcard"')).includes('new-user mix'),
              _.totalHtml(Object.assign({}, xp, { app: AP('N/A', 'Not measurable (GA4 ≠ AdMob) — GA4 +30% ≠ AdMob −40% — GA4 logging changed', 0, 0, [null, '', null, null, { st: 'na', gt: 0.3, mt: -0.4 }]) }), ID.a, ...P30).includes('New vs returning')] };
        } finally { xp.app = keepApp; ctx.APP = ''; } }
      for (const kk of ['r', 'dau', 'sc']) { _.set({ SORT: { k: kk, dir: -1 } }); out.v2.all['sort_' + kk] = names((SCR.paint(), SCREEN.innerHTML)); }
      _.set({ SORT: { k: 'rank', dir: 1 } }); ctx.APP = 'Alpha App';
      // the drill-down: Ads / 100 (+ views · ads), Screen users / day (+ reach), Why it moved (the parts), the chart per user
      const box = { clientWidth: 600, _h: '', set innerHTML(v) { box._h = v; }, get innerHTML() { return box._h; },
        querySelector: () => ({ querySelector: () => ({ setAttribute() {} }), addEventListener() {}, getBoundingClientRect: () => ({ width: 600, left: 0 }), setAttribute() {}, style: {}, hidden: true }) };
      f2.rows.s0.parts = { vpu: -3.2, tpv: 1.1, apm: -31.9 }; f2.rows.s0.reach = [0.4, 0.5];
      ctx.document.getElementById = id => id === 'sc-chart' ? box : null; _.set({ OPEN: 0, SEC: 'ov', SEG: 's', PER: '30' }); SCR.paint(); ctx.document.getElementById = () => null;
      h = SCREEN.innerHTML; const dd = h.slice(h.indexOf('id="sc-dd"'));
      out.v2.dd = { tiles: [...dd.matchAll(/<div class="sc-kl">([^<]+)<\/div><div class="sc-kv">([^<]*)<\/div><div class="sc-ks">(.*?)<\/div><\/div>/g)].map(m => m.slice(1)),
        parts: [...dd.matchAll(/<tr><td>(Views per user|Time per view|Ads per minute)<\/td><td[^>]*>([^<]+)<\/td><\/tr>/g)].map(m => m.slice(1)), why: /Why it moved vs own past <small class="sc-faint">% of normal · jod −34% = vs own past/.test(dd),
        head: (/<span class="sc-dds">(.*?)<\/span><button/.exec(dd) || [])[1] || null, adlogic: dd.includes('Ad logic (AdMob): <b>Lower fill</b>') && dd.includes('<th>% of normal ads per view</th>'),
        months: [...dd.matchAll(/<thead><tr><th>(Month|Day)<\/th>(.*?)<\/tr><\/thead>/g)].map(m => [m[1], [...m[2].matchAll(/<th>([^<]+)<\/th>/g)].map(q => q[1])]),
        svg: { aria: /aria-label="Impressions per user per day and users, by day"/.test(box._h), normal: /class="sc-nt">Normal [\d.]+<\/text>/.test(box._h), last: /class="sc-rl"[^>]*>[\d.]+<\/text>/.test(box._h), avg: /class="sc-al">Avg [\d.]+<\/text>/.test(box._h), bars: (box._h.match(/<rect /g) || []).length },
        ch: { pu: _.get().CH && _.get().CH.pu, last: _.get().CH && _.get().CH.labels.last, norm: _.get().CH && _.get().CH.labels.norm } };
      // the chart model per user: a point only on ≥ 100 user-days; Today / Yesterday no point (no users)
      const ud = _.userDays(x, f2, 0, '2026-03-20', TD);
      out.v2.days = { n: ud.length, last2: ud.slice(-2).map(r => [r[1], r[2] != null, r[3]]), gap: ud.filter(r => r[1] == null).map(r => r[0]) };
      const mu = _.chartModel([['2026-03-01', 50, 40, ''], ['2026-03-02', 500, 400, ''], ['2026-03-03', null, 300, 'users abhi nahi (~2 din baad)']], 0.9, '2026-03-02', true);
      out.v2.chart = [mu.B.map(b => b.r), mu.labels, mu.pu, _.tipText(mu.B[2], 'd', true), _.tipText(mu.B[0], 'd', true)];
      _.set({ OPEN: null, SEC: 'ov', MORE: false }); }
    out.fmt = [0, 0.3, 0.6, 1, 38, 38.4, 59.4, 59.6, 60, 79.5, 561, 3599, 3599.6, 3600, 3900, 7140, 7170, 86400, null, undefined, NaN, -5].map(v => _.fmtT(v));
    // the printed parts add up to the printed total (the rounding difference to the part rounded furthest)
    out.addup = [_.addUp(0.5, [0.375, 0.125]), _.addUp(1, [1 / 3, 1 / 3, 1 / 3]), _.addUp(123.4, [100.2, 23.2]), _.addUp(12.34, [6.17, 6.17])];
    // an Imp / user / day number as the build's why prints it (under 1: three places) — test_scr_frontend.py holds the
    // build's own _q against the same values
    out.pq = [0, 0.0004, 0.0451, 0.412, 0.4126, 0.9996, 1, 4.517, 12.34, 123.4, 1234.6, null].map(v => _.PQ(v));
    // file 2 not here yet: the per-user screen cells wait (⏳ — never a number); its load failed: "—" + why; a v 1 file 2 is
    // refused the same way (visibly, never mislabelled); the App total never waits (scr_all only)
    const nA2 = 'scr_' + KEY.a + '.json.gz', keepA2 = _.FILES[nA2], keepF = FILES[nA2];
    try {
      delete _.FILES[nA2]; FAIL.add(nA2); _.set({ MORE: true }); SCR.paint(); h = SCREEN.innerHTML;
      out.v2_wait = { main: cm(h, 0)['Imp / user / day'], ud: cm(h, 0)['Users / day'], other: cm(h, 2)['Imp / user / day'], total: /<tr><td>Imp \/ user \/ day<\/td><td[^>]*><b>[\d.]+<\/b>/.test(h) };
      out.v4wait = { wait: h.includes('⏳ Screens aa rahe hain') };
      await tick(); SCR.paint(); h = SCREEN.innerHTML; out.v2_wait.err = cm(h, 0)['Imp / user / day'];
      out.v4wait.err = h.includes('data-sc-retry="' + nA2 + '"');
      FAIL.delete(nA2); delete _.FILES[nA2]; FILES[nA2] = Object.assign({}, keepF, { v: 2 }); SCR.paint(); await tick(); SCR.paint();
      out.v2_wait.v1 = cm(SCREEN.innerHTML, 0)['Imp / user / day'];
      out.v4wait.v3 = SCREEN.innerHTML.includes('data-sc-retry="' + nA2 + '"');
    } finally { FAIL.delete(nA2); FILES[nA2] = keepF; _.FILES[nA2] = keepA2; _.set({ MORE: false }); }
    SCR.paint(); await tick();
    out.top = [..._.topSplit(_.tableRows(x, '2026-02-27', '2026-03-28', 's'))].sort((p, q) => p - q);
    // the 90 % split on many screens: 10 screens (5000, 3000, 1000, 500, 200, 100, 4 × 50 views a day) + one Worse far down
    const many = { ft: FT, td: TD, d0: '2026-03-01', items: [5000, 3000, 1000, 500, 200, 100, 50, 50, 50, 50].map((v, j) => ['x.y.S' + j + 'Activity', 's', 'inline']).concat([['(not set)', 'ns', 'inline']]),
      vis: [], V: [], A: [], ta: [], st: {}, status: { 9: ['Worse', '', 50, ''] } };
    for (let k = 0; k < 30; k++) { many.V.push([5000, 3000, 1000, 500, 200, 100, 50, 50, 50, 50, 10]); many.A.push([500, 300, 100, 50, 20, 10, 5, 5, 5, 5, 1]); many.vis.push(10010); many.ta.push([1001, 0, 0]); }
    out.top_many = [..._.topSplit(_.tableRows(many, '2026-03-01', '2026-03-28', 's'))].sort((p, q) => p - q);
    ctx.DATA.scr.apps.many = { key: 'a00000000009', v: 'm', vl: 'm', from: D0, ft: FT }; ALLF.apps.many = many;
    ctx.DATA.scr.fv = 'f2'; ctx.APP = 'many'; _.set({ OPEN: null, SEG: 's', MORE: false, PER: '30' }); SCR.paint(); await tick(); SCR.paint();
    out.many_less = [[...SCREEN.innerHTML.matchAll(/<tr class="sc-clk[^"]*" data-sc-open="(\d+)"/g)].map(m => +m[1]), (/Show (\d+) more screens/.exec(SCREEN.innerHTML) || [])[1]];
    SCREEN.onclick({ target: { closest: s => s === '[data-sc-more]' ? {} : null } });
    out.many_more = [[...SCREEN.innerHTML.matchAll(/<tr class="sc-clk[^"]*" data-sc-open="(\d+)"/g)].map(m => +m[1]).length, SCREEN.innerHTML.includes('Show fewer screens')];
    _.set({ MORE: false }); delete ALLF.apps.many; delete ctx.DATA.scr.apps.many; ctx.APP = 'Alpha App'; ctx.DATA.scr.fv = 'f3'; SCR.paint(); out.reload_no_loading = !SCREEN.innerHTML.includes('⏳ Loading…') && SCREEN.innerHTML.includes('id="sc-tcard"'); await tick();
    out.reload_quiet = LOADS.filter(f => f === 'scr_all.json.gz').length;
    out.sort_items = _.sortItems(_.tableRows(x, '2026-02-27', '2026-03-28', 's')).map(z => z.i);
    // the short period: muted, Today not final
    _.set({ PER: 'today' }); SCR.paint(); h = SCREEN.innerHTML;
    out.today = { line: h.includes('Today (GA4 · 30 Mar) · not final'), muted: h.includes('short period') };
    _.set({ PER: '30' });
    // Delta's dq codes: known words, an unknown code as itself (escaped)
    ctx.APP = 'Delta App'; SCR.paint(); h = SCREEN.innerHTML;
    out.delta.dq = h.includes('Is app ka AdMob data (placements) nahi') && h.includes('some_new_code');
    out.delta.cov_exposure = h.includes('<td class="sc-nm">Exposure</td><td>13</td><td>17</td><td>0</td><td>0</td>') && h.includes('GA4 grouped 17 din (57% din)');
    // the Hostile class name: escaped in the table, the title, the drill-down, the Needs attention row
    ctx.APP = 'Hostile App'; _.set({ OPEN: 0, SEC: 'ov' }); SCR.paint(); h = SCREEN.innerHTML;
    out.hostile = { raw: h.includes('<img src=x'), esc: h.includes('&lt;img src=x onerror=alert(1)&gt;'), why: h.includes('&lt;script&gt;x&lt;/script&gt;') && !h.includes('<script>x'),
      cause: h.includes('&lt;i&gt;cause&lt;/i&gt;') && !h.includes('<i>cause</i>'), disp: _.dispName(HOSTILE), item: _.itemName(['a.b.<x>"y\'Activity', 's', '']) };
    // a phone opens the drill-down with a Back step; the empty app says so
    ctx.window.innerWidth = 375; _.set({ OPEN: null }); SCREEN.onclick({ target: { closest: s => s === '[data-sc-open]' ? { tagName: 'TR', dataset: { scOpen: '1' } } : null } });
    out.phone_push = PUSHED.slice(); out.open_after = _.get().OPEN; ctx.window.innerWidth = 1280;
    SCREEN.onclick({ target: { closest: s => s === '[data-sc-close]' ? {} : null } }); out.closed = _.get().OPEN;
    ctx.APP = 'Empty App'; SCR.paint(); out.empty_msg = (/Is app ka Screens data abhi aa raha hai — history bhar rahi hai: ([^<]+)\./.exec(SCREEN.innerHTML) || [])[1] || null;
    // an app not in the file
    ctx.APP = 'Hidden App'; SCR.paint(); out.hidden_page = SCREEN.innerHTML.includes('Is app ka Screens data nahi');
    // ── Copy report ──
    const ta = { value: 'a\nb\nc', focus(o) { ta.f = o; }, setSelectionRange(p, q) { ta.sel = [p, q]; } }, line = { textContent: '' };
    ctx.navigator = {}; EXEC = []; EXEC_OK = true; out.copy_noapi = [_.copy('a\nb\nc', ta, line), line.textContent, EXEC.slice(), ta.sel, ta.f];
    ctx.navigator = { clipboard: { writeText: () => Promise.reject(new Error('denied')) } }; EXEC = []; line.textContent = '';
    const r1 = _.copy('a\nb\nc', ta, line); await tick(); out.copy_reject = [r1, line.textContent, EXEC.slice()];
    ctx.navigator = { clipboard: { writeText: () => Promise.resolve() } }; EXEC = []; line.textContent = '';
    const r2 = _.copy('a\nb', ta, line); await tick(); out.copy_ok = [r2, line.textContent, EXEC.length];
    ctx.navigator = {}; EXEC_OK = false; line.textContent = ''; out.copy_manual = [_.copy('a', ta, line), line.textContent];
    ctx.navigator = { get clipboard() { throw new Error('blocked'); } }; EXEC_OK = true; line.textContent = ''; out.copy_throw = [_.copy('a', ta, line), line.textContent];
    // ── the period saved per viewer ──
    const PR = (raw) => _.perRestore(raw, D0, TD);
    out.per = { bogus: PR('{"k":"bogus"}'), notjson: PR('{oops'), old_mon: PR('{"k":"mon:2025-12"}'), future_mon: PR('{"k":"mon:2026-05"}'), mon: PR('{"k":"mon:2026-02"}'),
      half: PR('{"k":"cus","f":"2026-03-10"}'), bad_date: PR('{"k":"cus","f":"2026-3-1","t":"2026-03-10"}'), cus: PR('{"k":"cus","f":"2026-03-20","t":"2025-12-01"}'),
      cus_hi: PR('{"k":"cus","f":"2026-03-01","t":"2027-01-01"}'), ok90: PR('{"k":"90"}'), num: PR('{"k":7}'), nul: PR('null'), arr: PR('[1]') };
    // lazily read on the first paint; a throwing localStorage is harmless, a bad stored key is ignored
    _.set({ PER: '30', PREAD: false }); LS_THROW = true; ctx.APP = 'Alpha App'; SCR.paint(); out.per_throw = [_.get().PER, SCREEN.innerHTML.includes('30 days (GA4')]; LS_THROW = false;
    _.set({ PER: '30', PREAD: false }); LS = { scr_per_v1: '{"k":"mon:2020-01"}' }; SCR.paint(); out.per_badkey = _.get().PER;
    _.set({ PER: '30', PREAD: false }); LS = { scr_per_v1: '{"k":"60"}' }; SCR.paint(); out.per_good = _.get().PER;
    // a tap saves it
    SCREEN.onclick({ target: { closest: s => s === '[data-sc-per]' ? { dataset: { scPer: '7' } } : null } }); out.per_saved = LS.scr_per_v1;
    _.set({ PER: '30' });
    // ── the chart ──
    const days = n => Array.from({ length: n }, (_x, k) => [day(k), k === 2 ? 50 : 1000, k === 2 ? 5 : (k === 3 ? null : 100), k === 3 ? 'GA4 sampled' : '']);
    const m1 = _.chartModel(days(30), 12.34, day(27)), m2 = _.chartModel(days(200), 10, day(197)), m3 = _.chartModel(days(600), null, day(597));
    out.chart = { d: [m1.by, m1.B.length, m1.B[2].r, m1.B[3].r, m1.B[3].why, m1.B[29].nf, m1.B[27].nf, m1.labels], w: [m2.by, m2.B.length, m2.B[0].v, m2.B[0].a, Math.round(m2.B[0].r * 100) / 100],
      m: [m3.by, m3.B.length, m3.labels.norm] };
    // drawing it into a box: the printed labels in the SVG
    const box = { clientWidth: 600, _h: '', set innerHTML(v) { box._h = v; }, get innerHTML() { return box._h; },
      querySelector: s => ({ querySelector: () => ({ setAttribute() {} }), addEventListener() {}, getBoundingClientRect: () => ({ width: 600, left: 0 }), setAttribute() {}, style: {}, hidden: true }) };
    ctx.document.getElementById = id => id === 'sc-chart' ? box : null;
    ctx.APP = 'Alpha App'; _.set({ OPEN: 0, SEC: 'ov', PER: '30' }); SCR.paint();
    out.chart_svg = { normal: /class="sc-nt">Normal [\d.]+<\/text>/.test(box._h), last: /class="sc-rl"[^>]*>[\d.]+<\/text>/.test(box._h), avg: /class="sc-al">Avg [\d.]+<\/text>/.test(box._h), bars: (box._h.match(/<rect /g) || []).length };
    ctx.document.getElementById = () => null;
    // ── years: a date outside the reference year (the file's last final day) is never printed without its year ──
    { _.set({ PER: 'all' });
      const pl = (lo, hi, ft) => _.perLine({ ft: ft || '2026-03-28' }, lo, hi);
      const mk = (a, b) => { const days = []; for (let t = Date.parse(a + 'T00:00:00Z'); t <= Date.parse(b + 'T00:00:00Z'); t += 864e5) days.push([new Date(t).toISOString().slice(0, 10), 100, 10, '']); return days; };
      const mAll = _.chartModel(mk('2024-06-20', '2026-03-28'), 5, '2026-03-28'); _.set({ CH: mAll });
      const box2 = { clientWidth: 600, _h: '', set innerHTML(v) { box2._h = v; }, get innerHTML() { return box2._h; }, querySelector: () => null };
      ctx.document.getElementById = id => id === 'sc-chart' ? box2 : null; _.drawChart(); ctx.document.getElementById = () => null;
      const mJan = _.chartModel(mk('2025-12-09', '2026-01-07'), 5, '2026-01-07'); _.set({ CH: mJan }); box2._h = ''; ctx.document.getElementById = id => id === 'sc-chart' ? box2 : null; _.drawChart(); ctx.document.getElementById = () => null;
      out.years = { all: pl('2024-06-20', '2026-03-30'), jan: pl('2025-12-09', '2026-01-07', '2026-01-07'), old: pl('2025-03-01', '2025-03-31'), cur: pl('2026-02-27', '2026-03-28'),
        one_old: pl('2025-03-04', '2025-03-04'), one_cur: pl('2026-03-04', '2026-03-04'),
        tip_week: _.tipText({ d0: '2025-12-28', d1: '2026-01-03', v: 5, vr: 0, a: 0, n: 0, nd: 7, nf: false, why: '' }), tip_one: _.tipText({ d0: '2025-12-28', d1: '2025-12-28', v: 5, vr: 0, a: 0, n: 0, nd: 1, nf: false, why: '' }),
        ticks_all: null, ticks_jan: null };
      _.set({ CH: mAll }); box2._h = ''; ctx.document.getElementById = id => id === 'sc-chart' ? box2 : null; _.drawChart(); ctx.document.getElementById = () => null;
      out.years.ticks_all = [...box2._h.matchAll(/y="214" text-anchor="(?:start|middle|end)">([^<]+)<\/text>/g)].map(m => m[1]);
      _.set({ CH: mJan }); box2._h = ''; ctx.document.getElementById = id => id === 'sc-chart' ? box2 : null; _.drawChart(); ctx.document.getElementById = () => null;
      out.years.ticks_jan = [...box2._h.matchAll(/y="214" text-anchor="(?:start|middle|end)">([^<]+)<\/text>/g)].map(m => m[1]);
      _.set({ CH: null, PER: '30' }); }
    // ── keep(): the tapped control back to its place, its sideways row's scroll kept ──
    let top = 300; const ROW = { scrollLeft: 140 }; const BTN = { getBoundingClientRect: () => ({ top }), closest: s => s === '.sc-x' ? ROW : null };
    SCREEN.querySelector = s => s === '[data-sc-per="90"]' ? BTN : null; SCROLL = [];
    _.keep('[data-sc-per="90"]', () => { top = 360; ROW.scrollLeft = 0; });
    out.keep = { dy: SCROLL.slice(), row: ROW.scrollLeft, minh: SCREEN.style.minHeight };
    // the real taps repaint inside keep(): the hold must survive paint() (it starts by clearing a stale hold)
    SCREEN.style.minHeight = ''; top = 300; SCROLL = []; let heldIn = null;
    _.keep('[data-sc-per="90"]', () => { _.set({ PER: '90' }); SCR.paint(); heldIn = SCREEN.style.minHeight; top = 280; });
    out.keep_paint = { held_in: heldIn, held_after: SCREEN.style.minHeight, dy: SCROLL.slice() };
    SCR.paint(); out.keep_paint.plain_paint = SCREEN.style.minHeight;          // a paint outside keep() drops a stale hold
    SCREEN.querySelector = () => null; _.set({ PER: '30' });
    // ── the drill-down belongs to its app ──
    ctx.APP = 'Alpha App'; _.set({ OPEN: null, SEC: 'ov', MORE: false }); SCR.paint(); DROPPED = []; PUSHED = [];
    ctx.window.innerWidth = 375;
    SCREEN.onclick({ target: { closest: s => s === '[data-sc-open]' ? { tagName: 'TR', dataset: { scOpen: '3' } } : null } });
    ctx.window.innerWidth = 1280; _.set({ SEC: 'cc', MORE: true }); SCR.paint();
    out.switch = { same: [_.get().OPEN, _.get().SEC, _.get().MORE, SCREEN.innerHTML.includes('id="sc-dd"'), _.get().OPENAPP], pushed: PUSHED.slice() };
    ctx.APP = 'Beta App'; SCR.paint(); h = SCREEN.innerHTML;
    out.switch.other = [_.get().OPEN, _.get().MORE, h.includes('id="sc-dd"'), / sc-on"/.test(h), DROPPED.slice()];
    ctx.APP = 'Alpha App'; SCR.paint(); out.switch.back = [_.get().OPEN, SCREEN.innerHTML.includes('id="sc-dd"')];
    ctx.APP = ''; _.set({ OPEN: 2 }); ctx.APP = 'Alpha App'; SCR.paint(); out.switch.from_all = _.get().OPEN;   // opened nowhere → closed
    _.set({ OPEN: null, SEC: 'ov', MORE: false });
    // ── "Details ▸" in Needs attention goes to the drill-down; a table row's tap stays put ──
    const STK = { offsetHeight: 60 }, DD = { getBoundingClientRect: () => ({ top: 1500 }) }, AT = { getBoundingClientRect: () => ({ top: 200 }), closest: () => null };
    ctx.document.getElementById = id => id === 'sc-dd' ? DD : id === 'sc-stk' ? STK : null;
    SCREEN.querySelector = s => /data-sc-open="2"/.test(s) ? AT : null; SCROLL = [];
    SCREEN.onclick({ target: { closest: s => s === '[data-sc-open]' ? { tagName: 'BUTTON', dataset: { scOpen: '2' } } : null } });
    out.attn = { open: [_.get().OPEN, SCROLL.slice()] }; SCROLL = [];
    SCREEN.onclick({ target: { closest: s => s === '[data-sc-open]' ? { tagName: 'BUTTON', dataset: { scOpen: '2' } } : null } });
    out.attn.close = [_.get().OPEN, SCROLL.slice()]; SCROLL = [];
    SCREEN.onclick({ target: { closest: s => s === '[data-sc-open]' ? { tagName: 'TR', dataset: { scOpen: '2' } } : null } });
    out.attn.row = [_.get().OPEN, SCROLL.slice()];
    SCREEN.querySelector = () => null; _.set({ OPEN: null });
    // ── a late file: only the slots using it, their scroll boxes kept ──
    const mkBoxes = () => [{ id: 'sc-dtw', scrollLeft: 0, scrollTop: 0 }, { id: '', scrollLeft: 0, scrollTop: 0 }];
    const slot = () => { const o = { boxes: mkBoxes(), writes: 0, _h: '', set innerHTML(v) { o._h = v; o.writes++; o.boxes = mkBoxes(); }, get innerHTML() { return o._h; },
      querySelectorAll: q => q === '.sc-x' ? o.boxes : [] }; return o; };
    const SL = { 'sc-ddb': slot(), 'sc-f-src': slot(), 'sc-f-ver': slot(), 'sc-f-cov': slot(), 'sc-f-rep': slot(), 'sc-total': slot(), 'sc-tb': slot() };
    ctx.document.getElementById = id => SL[id] || null;
    ctx.APP = 'Alpha App'; _.set({ OPEN: 0, SEC: 'ov', PER: '30' });
    SL['sc-ddb'].boxes[0].scrollTop = 300; SL['sc-ddb'].boxes[1].scrollLeft = 50; SL['sc-f-cov'].boxes[1].scrollLeft = 25;
    const w = () => Object.fromEntries(Object.entries(SL).map(([k, o]) => [k, o.writes]));
    _.arrive(ID.a, '2');
    out.arrive = { f2: w(), kept: [SL['sc-ddb'].boxes[0].scrollTop, SL['sc-ddb'].boxes[1].scrollLeft, SL['sc-f-cov'].boxes[1].scrollLeft], dd: SL['sc-ddb']._h.includes('id="sc-chart"'),
      // file 2's screen users drawn into the table it brought them to (the App total never: scr_all only)
      tb: [SL['sc-tb']._h.includes('data-sc-v4sort="users"'), SL['sc-tb']._h.includes('⏳'), (/<span class="sc-n">Main<\/span><\/td><td>([^<]*)<\/td>/.exec(SL['sc-tb']._h) || [])[1] || null] };
    _.set({ SEC: 'ver' }); _.arrive(ID.a, 'c'); out.arrive.c_on_ver = w();
    _.arrive(ID.a, 'r'); out.arrive.r_on_ver = w();
    _.arrive(ID.a, 'l'); out.arrive.l_on_ver = w();
    ctx.document.getElementById = () => null; _.set({ OPEN: null, SEC: 'ov' });
    // ── the Cause stretch (.sc-endsnap on #sc-ttw): ON only when the table, measured without it, is wider than its box; the
    // box's sideways scroll is put back; a box that fits (or is not shown: width 0) has it OFF ──
    { const mk = (natural, box, on) => { const cl = new Set(on ? ['sc-endsnap'] : []); let sl = 0;
        const o = { clientWidth: box, classList: { add: c => cl.add(c), remove: c => cl.delete(c), contains: c => cl.has(c) },
          get scrollWidth() { return !box ? 0 : Math.max(box, cl.has('sc-endsnap') ? natural + 800 : natural); },
          get scrollLeft() { return Math.min(sl, Math.max(0, o.scrollWidth - o.clientWidth)); }, set scrollLeft(v) { sl = v; }, on: () => cl.has('sc-endsnap') }; return o; };
      const run = (natural, box, on, left, arg) => { const o = mk(natural, box, on); o.scrollLeft = left || 0; ctx.document.getElementById = id => id === 'sc-ttw' ? o : null; _.endSnap(arg); return [o.on(), o.scrollLeft]; };
      out.es = { fits1136: run(1100, 1136, false), fitsWasOn: run(1100, 1136, true), over1000: run(1250, 1000, false), over1240: run(1250, 1240, false), edge1250: run(1250, 1250, false),
        hidden: run(1250, 0, true), keepScroll: run(1250, 1000, true, 180), argScroll: run(1250, 1000, false, 0, 120), none: (ctx.document.getElementById = () => null, _.endSnap(), 'ok') };
      ctx.document.getElementById = () => null; }
    // ── a whole month: the build's month sums (cc_m / ver_m), no "not read" note ──
    const rowsOf = hh => [...hh.matchAll(/<tr><td class="sc-nm">([^<]+)<\/td><td>([^<]+)<\/td><td>([^<]+)<\/td><td><b>([^<]+)<\/b>/g)].map(m => m.slice(1));
    ctx.APP = 'Alpha App'; _.set({ PER: 'lm', OPEN: 0, SEC: 'cc' }); SCR.paint(); h = SCREEN.innerHTML.slice(SCREEN.innerHTML.indexOf('id="sc-dd"'));
    out.month = { cc: rowsOf(h), cc_miss: h.includes('abhi nahi (padha nahi gaya)') };
    _.set({ PER: 'mon:2026-02', SEC: 'ver' }); SCR.paint(); h = SCREEN.innerHTML.slice(SCREEN.innerHTML.indexOf('id="sc-dd"'));
    out.month.ver = rowsOf(h.slice(0, h.indexOf('whole life'))); out.month.ver_miss = h.includes('abhi nahi (padha nahi gaya)');
    const lp = _.layerPeriod(ALLF.apps[ID.a], ID.a, 0, 'r', '2026-02-01', '2026-02-28');
    out.month.lp_r = { it: lp.it, app: lp.app, miss: lp.miss };
    const lc = _.layerPeriod(ALLF.apps[ID.a], ID.a, 0, 'c', '2026-02-01', '2026-03-28');
    out.month.lp_c_mixed = { XA: lc.it.XA, miss: lc.miss, wait: lc.wait };
    _.set({ PER: '30', OPEN: null, SEC: 'ov' });
    // ── the Screens table's default sort (status) honours its direction: a second tap on its header reverses it ──
    ctx.APP = 'Alpha App'; _.set({ OPEN: null, SEG: 's', MORE: false, PER: '30', TS: { k: 'st', dir: 1 } }); SCR.paint();
    const tRows = () => [...SCREEN.innerHTML.matchAll(/<tr class="sc-clk[^"]*" data-sc-open="(\d+)"/g)].map(m => +m[1]);
    const tAria = () => (/<th aria-sort="([a-z]+)"><button type="button" data-sc-tsort="st">/.exec(SCREEN.innerHTML) || [])[1] || null;
    const tTap = () => SCREEN.onclick({ target: { closest: s => s === '[data-sc-tsort]' ? { dataset: { scTsort: 'st' } } : null } });
    out.tsort = { asc: [tRows(), tAria()] }; tTap(); out.tsort.desc = [tRows(), tAria()]; tTap(); out.tsort.back = [tRows(), tAria()];
    _.set({ TS: { k: 'st', dir: -1 } }); out.sort_items_desc = _.sortItems(_.tableRows(x, '2026-02-27', '2026-03-28', 's')).map(z => z.i);
    _.set({ TS: { k: 'st', dir: 1 } });
    // ── the report before its files arrive: the same disabled Copy button + reserved line (the control keeps its place);
    // a failed load: the error + Try again; no file in this build: says so ──
    const FL = _.FILES, nL = 'scr_l_' + KEY.a + '.json.gz', n2 = 'scr_' + KEY.a + '.json.gz', xa0 = ALLF.apps[ID.a], keepL = FL[nL], keep2 = FL[n2];
    const repAt = id => { _.set({ SEC: 'rep', OPEN: 0 }); return _.secHtml(xa0, id || ID.a, 0, '2026-02-27', '2026-03-28'); };
    const foldRep = () => { const f = _.foldsHtml(xa0, ID.a, '2026-02-27', '2026-03-28'); return f.slice(f.indexOf('data-sc-fold="rep"'), f.indexOf('data-sc-fold="how"')); };
    const rep = {}, ready = repAt();
    rep.ready_head = ready.slice(0, ready.indexOf('<textarea'));
    try {
      FL[nL] = { busy: true }; rep.l_loading = repAt(); rep.fold_loading = foldRep();
      FL[nL] = { err: true, v: 'la' }; rep.l_err = repAt(); rep.fold_err = foldRep();
      FL[nL] = keepL; FL[n2] = { busy: true }; rep.f2_loading = repAt();
      FL[n2] = { err: true, v: 'va' }; rep.f2_err = repAt();
    } finally { FL[nL] = keepL; FL[n2] = keep2; }
    rep.nofile = repAt('ca-app-pub-0000000000000000~99'); rep.after = repAt() === ready;
    out.rep = rep; _.set({ SEC: 'ov', OPEN: null });
    // ── a section needing both files when file 2 failed but scr_l came: the error + Try again, never "Loading" for good;
    // a section needing scr_l only is drawn ──
    const secAt = s => { _.set({ SEC: s, OPEN: 0 }); return _.secHtml(xa0, ID.a, 0, '2026-02-27', '2026-03-28'); }, gate = {};
    try {
      FL[n2] = { err: true, v: 'va' }; for (const s of ['ver', 'nvr', 'x', 'cc']) gate[s] = secAt(s);
      FL[n2] = { busy: true }; gate.ver_loading = secAt('ver');
      FL[n2] = keep2; FL[nL] = { err: true, v: 'la' }; gate.nvr_l_err = secAt('nvr');
    } finally { FL[nL] = keepL; FL[n2] = keep2; }
    out.gate = Object.fromEntries(Object.entries(gate).map(([k, v]) => [k, [(/data-sc-retry="([^"]+)">Try again<\/button>/.exec(v) || [])[1] || null,
      v.includes('⏳ Loading data…'), v.includes('<table')]]));
    // ── Users who saw ads: scr_l on its way → ⏳ "aa raha hai…" (never a reason); an aggregate row "—" and why; a day whose
    // users who saw ads GA4 sampled; a day GA4 gave them for the app only (not per screen) ──
    const usT = hh => (/<div class="sc-k"(?: title="[^"]*")?><div class="sc-kl">Users who saw ads<\/div><div class="sc-kv">([^<]*)<\/div><div class="sc-ks">([^<]*)<\/div>/.exec(hh) || []).slice(1);
    const engAt = (i, lo, hi) => { _.set({ SEC: 'eng', OPEN: i }); return usT(_.secHtml(xa0, ID.a, i, lo, hi)); };
    const uA80 = FL[nL].raw.days[80].uA;
    try {
      FL[nL] = { busy: true }; out.eng_wait = [engAt(0, ...P30), engAt(2, ...P30)];
      FL[nL] = keepL; FL[nL].raw.days[80].uA = { st: 'w', g: 'a', r: [[700]] };
      out.eng_none = [engAt(0, '2026-03-26', '2026-03-26'), engAt(0, '2026-03-22', '2026-03-22')];
    } finally { FL[nL] = keepL; FL[nL].raw.days[80].uA = uA80; _.set({ SEC: 'ov', OPEN: null }); }
    // ── a unit GA4 logs that AdMob does not have: "Not in AdMob" under its name ──
    const f2a = FL[n2].raw, dday = f2a.days[84];                                      // 26 Mar, inside the period
    dday.a.r.push([0, 3, 7]);
    try { out.not_in_admob = (/<span class="sc-n">0123456789abcdef<\/span>(<small[^>]*>[^<]*<\/small>)<\/td>/.exec(secAt('un')) || [])[1] || null; }
    finally { dday.a.r.pop(); }
    // ── a layer day GA4 was never asked about (the fetch's "skip" record) and a day not read at all: left out and
    // counted, the note never puts them on GA4 ──
    const lA = FL[nL].raw.days, kV = lA[84].nV, kA = lA[85].nA;
    lA[84].nV = { st: '-', g: 'c', skip: 'gate', tried: [], fv: 1 }; delete lA[85].nA;           // (scr_l ships "-", as scr_all)
    try { out.nvr_note = (/<p class="sc-note">(\d+\/\d+ din ye layer[^<]*)<\/p>/.exec(secAt('nvr')) || [])[1] || null; }
    finally { lA[84].nV = kV; lA[85].nA = kA; }
    _.set({ SEC: 'ov', OPEN: null });
    // ── All apps: the period sums and the coverage strip are kept per (build, period) — a sort tap, a chip tap and the
    // refresh reuse them; a new period / a new build's data counts again (same numbers); no date string per day ──
    ctx.APP = ''; _.set({ PER: '30', COVP: '', SORT: { k: 'rank', dir: 1 } }); SCR.paint();
    const LA = _.apps(), C1 = _.coverAll(LA);
    SCREEN.onclick({ target: { closest: s => s === '[data-sc-sort]' ? { dataset: { scSort: 'dau' } } : null } });
    SCREEN.onclick({ target: { closest: s => s === '[data-sc-cov]' ? { dataset: { scCov: 'r' } } : null } });
    SCR.paint();
    const C2 = _.coverAll(_.apps());
    _.set({ PER: '7' }); const C7 = _.coverAll(_.apps()); _.set({ PER: '30' }); const C30 = _.coverAll(_.apps());
    const xa = LA[0].x, xcopy = JSON.parse(JSON.stringify(xa)), CL2 = _.coverAll(LA.map((r, j) => j ? r : { id: r.id, x: xcopy, name: r.name }));
    const A1 = _.appSum(xa, '2026-02-27', '2026-03-28'), A2 = _.appSum(xcopy, '2026-02-27', '2026-03-28');
    let isoN = 0; const isoReal = Date.prototype.toISOString, iso = [];
    Date.prototype.toISOString = function () { isoN++; return isoReal.call(this); };
    try {
      isoN = 0; _.cover(xcopy, ['v', 'a'], '2026-02-27', '2026-03-28'); iso.push(isoN);
      isoN = 0; _.appSum(JSON.parse(JSON.stringify(xa)), '2026-02-27', '2026-03-28'); iso.push(isoN);
      isoN = 0; _.sumItem(xcopy, 0, '2026-02-27', '2026-03-28'); iso.push(isoN);                // (reads each day's date)
    } finally { Date.prototype.toISOString = isoReal; }
    out.memo = { same_build: C2 === C1, new_period: C7 !== C1 && C30 !== C7 && JSON.stringify(C30) === JSON.stringify(C1),
      new_data: CL2 !== C30 && JSON.stringify(CL2) === JSON.stringify(C30),
      sum_same: _.appSum(xa, '2026-02-27', '2026-03-28') === A1, sum_period: _.appSum(xa, '2026-03-01', '2026-03-28') !== A1,
      sum_data: A2 !== A1 && JSON.stringify(A2) === JSON.stringify(A1), iso };
    _.set({ SORT: { k: 'rank', dir: 1 }, COVP: '' });
    // ── a day the build could not read (its store month file: "x") and any other unknown state ──
    const xs = { key: 'a00000000008', ft: FT, td: TD, d0: '2026-03-01', items: [], vis: Array(30).fill(100), V: [], A: [], ta: [],
      st: { v: 'w'.repeat(10) + 'x'.repeat(5) + 'z'.repeat(2) + 'w'.repeat(13), a: 'w'.repeat(30) }, bf: {}, status: {}, app: ['Normal', '', 0, 0], dq: [] };
    const cvx = _.cover(xs, ['v'], '2026-03-01', '2026-03-30'), fx = _.foldsHtml(xs, 'nope', '2026-03-01', '2026-03-30');
    out.xstate = { c: [cvx.c.x, cvx.c['?'], cvx.c.w, cvx.nd, cvx.whole], why: _.covWhy(xs, ['v'], cvx),
      day: [_.dayState(xs, ['v', 'a'], 12), _.dayState(xs, ['v'], 15), _.dayState(xs, ['v'], 0)],
      vrow: (/<td class="sc-nm">Screen views<\/td>(.*?)<\/tr>/.exec(fx) || [])[1] || null };
    // ── all formats because GA4 gave no screen × format split (allf 2): the header, the table's line, the note with the
    // measured full-screen share on app screens (none measured: says so); allf 1 keeps its own note ──
    const xA = _.apps().find(r => r.id === ID.a).x;
    const noteOf = hh => [...hh.matchAll(/<li>((?:GA4 is app ke|Format kam record)[^<]*)<\/li>/g)].map(m => m[1]);
    ctx.APP = 'Alpha App'; _.set({ OPEN: null, SEG: 's', MORE: false, SEC: 'ov', PER: '30' });
    try {
      xA.allf = 2; xA.allfs = 0.0023; SCR.paint(); h = SCREEN.innerHTML;
      out.allf2 = { head: /<th aria-sort="none" title="is screen ke ads \(saare formats[^"]*"><button type="button" data-sc-tsort="r">Imp \/ user \/ day<\/button>/.test(h),
        sub: h.includes('<p class="sc-sub">Har screen pe uske users ko kitne ads (all formats) — kyun, Data coverage me · row pe tap = details</p>'), note: noteOf(h) };
      xA.allfs = null; SCR.paint(); out.allf2.none = noteOf(SCREEN.innerHTML);
      xA.allf = 1; delete xA.allfs; SCR.paint(); out.allf2.one = noteOf(SCREEN.innerHTML);
    } finally { delete xA.allf; delete xA.allfs; }
    SCR.paint(); out.allf2.off = [noteOf(SCREEN.innerHTML), /title="is screen ke inline ads ÷/.test(SCREEN.innerHTML)];
    // ── a row under 1 % of the app's ads of its kind in the period and its normal: "score —" (titled, no colour) in the
    // table and the drill-down; one the build left N/A "Too few ads" is never in Needs attention ──
    _.set({ OPEN: null, SEG: 's', MORE: true, PER: '30' }); SCR.paint(); h = SCREEN.innerHTML;
    out.low = { cells: [1, 3, 4, 5].map(i => cm(h, i)['Ads / view']),
      ps: [1, 3, 4, 5].map(i => { const p = _.perScoreU(xA, F2A(), i, '2026-02-27', '2026-03-28'); return [p.low, p.score]; }),
      share: [3, 4, 5, 6].map(i => Math.round(_.itemShare(xA, i, '2026-02-27', '2026-03-28') * 1e4) / 1e4) };
    _.set({ OPEN: 5, SEC: 'ov' }); SCR.paint(); out.low.dd = (/<span class="sc-dds">(.*?)<\/span><button/.exec(SCREEN.innerHTML) || [])[1] || null;
    _.set({ OPEN: null, MORE: false });
    const tiny = { key: 'a0000000000a', ft: FT, td: TD, d0: '2026-03-01', items: [['x.y.BigActivity', 's', 'inline'], ['x.y.TinyActivity', 's', 'inline'], ['(not set)', 'ns', 'inline']],
      vis: [], V: [], A: [], ta: [], st: {}, bf: {}, dq: [], app: AP('Worse', '1 row Worse', 1, 0), au: Array(30).fill(500),
      status: { 0: S('Worse', 'imp/screen user 5.00 → 3.00 · z −9.0', 64, 'Lower fill', 'Lower fill', -0.4), 1: S('N/A', "Too few ads — 0.5% of the app's inline ads", null, '') } };
    for (let k = 0; k < 30; k++) { const w = k >= 21; tiny.V.push([5000, 1000, 10]); tiny.A.push([w ? 1500 : 2500, w ? 8 : 1, 2]); tiny.vis.push(6010); tiny.ta.push([w ? 1510 : 2503, 0, 0]); }
    ALLF.apps.tiny = tiny; ctx.DATA.scr.apps.tiny = { key: tiny.key, v: 't', vl: 't', from: tiny.d0, ft: FT }; ctx.DATA.scr.fv = 'f4';
    try {
      ctx.APP = 'tiny'; _.set({ PER: '7' }); SCR.paint(); await tick(); SCR.paint(); h = SCREEN.innerHTML;
      out.tiny = { attn: [...h.slice(h.indexOf('id="sc-attn"'), h.indexOf('id="sc-tcard"')).matchAll(/data-sc-open="(\d+)"/g)].map(m => +m[1]),
        big: cm(h, 0)['Ads / view'], small: cm(h, 1)['Ads / view'], why: cm(h, 1).Screen };
    } finally { delete ALLF.apps.tiny; delete ctx.DATA.scr.apps.tiny; ctx.DATA.scr.fv = 'f5'; _.set({ PER: '30' }); ctx.APP = 'Alpha App'; }
    SCR.paint(); await tick();
    // ── no whole screen users day (GA4 sampled the users read: no "U") and the daily users of another stream (no "au",
    // the build's why): "—" and why — in the screen's cell and the App total ──
    const nu = { key: 'a0000000000b', ft: FT, td: TD, d0: '2026-03-01', items: [['x.y.OneActivity', 's', 'inline'], ['', 'o', 'inline']], vis: [], V: [], A: [], ta: [],
      st: { uV: 's'.repeat(30), uA: 's'.repeat(30) }, bf: {}, dq: [], app: AP('N/A', 'Not whole — 0 whole days of ads in the last 10 (users not in yet 10)', 0, 0), status: {}, auw: 'stream' };
    for (let k = 0; k < 30; k++) { nu.V.push([1000, 100]); nu.A.push([90, 5]); nu.vis.push(1100); nu.ta.push([95, 10, 0]); }
    const nu2 = 'scr_' + nu.key + '.json.gz';
    FILES[nu2] = { v: 4, key: nu.key, d0: nu.d0, ft: FT, td: TD, screens: [['x.y.OneActivity', 's']], units: [], trig: [], days: Array.from({ length: 30 }, () => ({ v: [[0, 1000, 9000]] })), adm: {}, rows: {}, notes: {}, auw: 'stream' };
    ALLF.apps.nu = nu; ctx.DATA.scr.apps.nu = { key: nu.key, v: 'n', vl: 'n', from: nu.d0, ft: FT }; ctx.DATA.scr.fv = 'f6';
    try {
      ctx.APP = 'nu'; _.set({ PER: '7', OPEN: null, SEG: 's', MORE: false }); SCR.paint(); await tick(); SCR.paint(); h = SCREEN.innerHTML;
      out.v2_none = { one: cm(h, 0)['Imp / user / day'], total: (/<tr><td>Imp \/ user \/ day<\/td><td( title="[^"]*")?>(.*?)<\/td>/.exec(h) || []).slice(1), fn: _.sumScr(nu, _.FILES[nu2].raw, 0, '2026-03-22', '2026-03-28').r };
    } finally { delete ALLF.apps.nu; delete ctx.DATA.scr.apps.nu; delete FILES[nu2]; ctx.DATA.scr.fv = 'f7'; _.set({ PER: '30' }); ctx.APP = 'Alpha App'; }
    SCR.paint(); await tick();
    // ── more than one ad per screen view (Ads / 100 above 100) with a known time per view: the banner-refresh line under the
    // Ads / 100 cell — a top screen only (never an aggregate row), never at or under 1 ad per view, never without time per
    // view (no engagement), never in the Full-screen table ──
    const bn = { key: 'a0000000000c', ft: FT, td: TD, d0: '2026-03-01', items: [['x.y.HotActivity', 's', 'inline'], ['x.y.NoTimeActivity', 's', 'inline'], ['x.y.CalmActivity', 's', 'inline'], ['', 'o', 'inline']],
      vis: [], V: [], A: [], ta: [], st: {}, bf: {}, dq: [], app: ['Normal', '', 0, 0], status: {} };
    for (let k = 0; k < 30; k++) { bn.V.push([1000, 1000, 1000, 1000]); bn.A.push([1500, 1500, 900, 1500]); bn.vis.push(4000); bn.ta.push([5400, 0, 0]); }
    const bn2 = 'scr_' + bn.key + '.json.gz';
    FILES[bn2] = { v: 4, key: bn.key, d0: bn.d0, ft: FT, td: TD, screens: [['x.y.HotActivity', 's'], ['x.y.NoTimeActivity', 's'], ['x.y.CalmActivity', 's'], ['x.y.RareActivity', 's']], units: [], trig: [],
      days: Array.from({ length: 30 }, () => ({ v: [[0, 1000, 44600], [1, 1000, 0], [2, 1000, 30000], [3, 1000, 20000]] })), adm: {}, rows: {}, notes: {}, auw: 'none' };
    ALLF.apps.bn = bn; ctx.DATA.scr.apps.bn = { key: bn.key, v: 'b', vl: 'b', from: bn.d0, ft: FT }; ctx.DATA.scr.fv = 'f8';
    try {
      ctx.APP = 'bn'; _.set({ PER: '7', OPEN: null, SEG: 's', MORE: true }); SCR.paint(); await tick(); SCR.paint(); h = SCREEN.innerHTML;
      const bnOf = i => { _.set({ OPEN: i, SEC: 'ov' }); SCR.paint(); const d = SCREEN.innerHTML.slice(SCREEN.innerHTML.indexOf('id="sc-dd"'));
        return [(/<div class="sc-kl">Ads \/ 100 views<\/div><div class="sc-kv">([^<]*)<\/div>/.exec(d) || [])[1] || null, ...(/<span title="([^"]*)">(1 view me[^<]*)<\/span>/.exec(d) || []).slice(1)]; };
      out.bn = { hot: bnOf(0), notime: bnOf(1), calm: bnOf(2), agg: bnOf(3), table: h.includes('1 view me 1 se zyada ad'),
        fn: [_.bannerSec(bn, _.FILES[bn2].raw, 0, 150, '2026-03-22', '2026-03-28'), _.bannerSec(bn, _.FILES[bn2].raw, 0, 100, '2026-03-22', '2026-03-28'), _.bannerSec(bn, _.FILES[bn2].raw, 3, 150, '2026-03-22', '2026-03-28'), _.bannerSec(bn, null, 0, 150, '2026-03-22', '2026-03-28')],
        n: 0 };
      _.set({ OPEN: null });
      _.set({ SEG: 'f' }); SCR.paint(); out.bn.full = SCREEN.innerHTML.includes('sc-bn');
    } finally { delete ALLF.apps.bn; delete ctx.DATA.scr.apps.bn; delete FILES[bn2]; ctx.DATA.scr.fv = 'f9'; _.set({ PER: '30', SEG: 's', MORE: false }); ctx.APP = 'Alpha App'; }
    SCR.paint(); await tick();
    out.bn_alpha = SCREEN.innerHTML.includes('sc-bn');                                       // Alpha: ~10 ads / 100 — never
    // ── the column order (owner: "pehle user hota he fir screen view hota he fir ads impression hota he"): users, then screen
    // views, then the ads. Every table as {row → {header → [cell attrs, cell]}} on each period and file state — read by the
    // header a cell sits under, so the same whatever the order — with its headers [label, sort key, title, aria-sort] and
    // each row's cell count (colspan); the rows' own numbers (each header's key bound to the cells under it); a tap on every
    // sort header, twice: the rows' order, the page's own sort for it, the column under the header tapped ("sorty": five
    // screens that every column ranks differently) ──
    { const read = (hh, id) => { const s = hh.indexOf('id="' + id + '"'), t = s < 0 ? '' : hh.slice(s, hh.indexOf('</table>', s));
        const H = [...((/<thead><tr>(.*?)<\/tr><\/thead>/.exec(t) || [, ''])[1]).matchAll(/<th([^>]*)>(.*?)<\/th>/g)].map(m => [txt(m[2]),
          (/data-sc-t?sort="([a-z]+)"/.exec(m[2]) || [])[1] || null, (/ title="([^"]*)"/.exec(m[1]) || [])[1] || null, (/aria-sort="([a-z]+)"/.exec(m[1]) || [])[1] || null]);
        const rows = [], map = {};
        for (const m of ((/<tbody>(.*?)<\/tbody>/.exec(t) || [, ''])[1]).matchAll(/<tr([^>]*)>(.*?)<\/tr>/g)) {
          const cs = [...m[2].matchAll(/<td((?: [^>]*)?)>(.*?)<\/td>/g)].map(c => [c[1], c[2]]);
          const k = (/data-sc-(?:open|app)="([^"]+)"/.exec(m[1]) || [])[1] || (id === 'sc-total' && cs.length ? txt(cs[0][1]) : 'empty');
          rows.push([k, cs.length, +((/colspan="(\d+)"/.exec(cs.length ? cs[0][0] : '') || [])[1] || 0)]); map[k] = by(H.map(q => q[0]), cs); }
        return { heads: H, rows, map }; };
      // (an app's first paint folds "Show more" again: every row is shown here)
      const show = o => { _.set(Object.assign({ OPEN: null, SEG: 's', MORE: true, PER: '30', TS: { k: 'st', dir: 1 }, SORT: { k: 'rank', dir: 1 } }, o)); SCR.paint();
        if (!_.get().MORE) { _.set({ MORE: true }); SCR.paint(); } return SCREEN.innerHTML; };
      const T = {}, n2 = 'scr_' + KEY.a + '.json.gz', k2 = _.FILES[n2], kf = FILES[n2], xa = ALLF.apps[ID.a], { PF: pf0, PTO: pt0 } = _.get();
      const xOf = id => _.apps().find(r => r.id === id).x, f2Of = xx => _.FILES['scr_' + xx.key + '.json.gz'].raw;
      ctx.APP = 'Alpha App';
      for (const per of ['30', '7', 'today', 'yday', 'lm', 'all', 'mon:2026-02', 'cus']) { const hh = show({ PER: per, PF: '2026-03-10', PTO: '2026-03-20' });
        T['s a ' + per] = read(hh, 'sc-ttw'); T['tot a ' + per] = read(hh, 'sc-total'); T['f a ' + per] = read(show({ PER: per, SEG: 'f' }), 'sc-ttw'); }
      _.set({ PF: pf0, PTO: pt0 });
      for (const [k, nm] of [['b', 'Beta App'], ['c', 'Gamma App'], ['d', 'Delta App'], ['h', 'Hostile App']]) {
        ctx.APP = nm; show({}); await tick(8); const hh = show({}); T['s ' + k + ' 30'] = read(hh, 'sc-ttw'); T['tot ' + k + ' 30'] = read(hh, 'sc-total'); T['f ' + k + ' 30'] = read(show({ SEG: 'f' }), 'sc-ttw'); }
      // file 2 on its way (⏳) / failed ("data load nahi hua"); no screens / no triggers: the one colspan row
      ctx.APP = 'Alpha App';
      try { delete _.FILES[n2]; FAIL.add(n2); T['s a wait'] = read(show({}), 'sc-ttw'); await tick(); T['s a err'] = read(show({}), 'sc-ttw'); }
      finally { FAIL.delete(n2); FILES[n2] = kf; _.FILES[n2] = k2; }
      show({}); _.set({ SEG: 'f' }); T['f none'] = read(_.tableHtml(Object.assign({}, xa, { items: xa.items.filter(it => it[1] !== 'fs') }), ID.a, ...P30), 'sc-ttw');
      _.set({ SEG: 's' }); T['s none'] = read(_.tableHtml(Object.assign({}, xa, { items: xa.items.filter(it => it[1] === 'fs') }), ID.a, ...P30), 'sc-ttw');
      // All apps: the periods, an AdMob-judged App row (its score muted)
      ctx.APP = ''; for (const per of ['30', '7', 'today', 'all']) T['all ' + per] = read(show({ PER: per }), 'sc-atw');
      { const xp = xOf(ID.a), ka = xp.app; xp.app = AP('Worse', 'AdMob imp/user 4.0 → 2.1', 0, 0, [52, '', null, null, { st: 'admob' }]);
        try { T['all admob'] = read(show({}), 'sc-atw'); ctx.APP = 'Alpha App'; T['tot a admob'] = read(show({}), 'sc-total'); } finally { xp.app = ka; ctx.APP = ''; } }
      // "sorty": five top screens, each column ranking them differently — users / day SU, views / user SV ÷ SU, time / view
      // SG ÷ SV, time / user SG ÷ SU, ads / min, imp / user (the period's ads SA ÷ SU), normal (the 30 days before: SN ÷ SU),
      // score — + All other screens, Not recorded; the screens' users every final day, the app's 3,000 daily users
      const SU = [1000, 800, 600, 400, 200], SV = [2000, 4000, 1500, 2400, 300], SG = [60000, 40000, 72000, 12000, 10500], SA = [300, 400, 480, 100, 300], SN = [500, 320, 457, 91, 316];
      const zk = 'a0000000000d', zn = 'scr_' + zk + '.json.gz', zs = SU.map((_u, j) => 'x.y.S' + j + 'Activity');
      const zx = { key: zk, ft: FT, td: TD, d0: D0, items: zs.map(c => [c, 's', 'inline']).concat([['', 'o', 'inline'], ['(not set)', 'ns', 'inline']]), vis: [], V: [], A: [], ta: [], st: {}, bf: {},
        dq: [], status: {}, app: AP('Normal', '', 0, 0), ftu: FT, dk: '0'.repeat(ND), au: [] };
      const zf = { v: 4, key: zk, d0: D0, ft: FT, td: TD, screens: zs.map(c => [c, 's']).concat([['x.y.RestActivity', 's'], ['(not set)', 'ns']]), units: [], trig: [], days: [], adm: {}, rows: {}, notes: {},
        Us: [0, 1, 2, 3, 4], U: [], au: [] };
      for (let k = 0; k < ND; k++) { const ad = k >= 57 ? SA : SN; zx.V.push(SV.concat([100, 10])); zx.A.push(ad.concat([5, 1])); zx.vis.push(SV.reduce((s, v) => s + v, 110));
        zx.ta.push([ad.reduce((s, v) => s + v, 6), 0, 0]); zx.au.push(k > 86 ? null : 3000); zf.au.push(k > 86 ? null : 3000);
        zf.days.push({ v: SV.map((v, j) => [j, v, SG[j]]).concat([[5, 100, 1000], [6, 10, 100]]) }); zf.U.push(k > 86 ? null : SU.slice()); }
      for (const r of READS) zx.st[r] = 'w'.repeat(ND);
      ALLF.apps.sorty = zx; FILES[zn] = zf; ctx.DATA.scr.apps.sorty = { key: zk, v: 'z', vl: 'z', from: D0, ft: FT }; ctx.DATA.scr.fv = 'f10';
      try {
        ctx.APP = 'sorty'; show({}); await tick(8); show({}); await tick(8); const hz = show({}); T['s z 30'] = read(hz, 'sc-ttw'); T['tot z 30'] = read(hz, 'sc-total');
        ctx.APP = ''; T['all z'] = read(show({}), 'sc-atw');
        // the rows' own numbers (30 days): the Screens rows (Alpha, sorty) per sort key, All apps' per sort key
        // (Fill / Show rate as printed: in %)
        const mS = id => { const xx = xOf(id), pc = v => v == null ? null : v * 100; return Object.fromEntries(_.tableRows(xx, ...P30, 's', f2Of(xx)).map(z => [String(z.i), { agg: z.agg, ud: z.ud, vu: z.vu, tv: z.tv, tu: z.tu, am: z.am, r: z.r, n: z.n, sc: z.sc, av: z.av, fl: pc(z.fl), sr: pc(z.sr) }])); };
        const M = { a: mS(ID.a), z: mS('sorty'), all: Object.fromEntries(_.apps().map(_.appRow).map(z => [z.r.name, { dau: z.dau, r: z.ru, n: z.n, sc: z.sc, lo: z.low, wn: z.wn, an: z.an }])) };
        // a tap on every sort header, twice (its direction turns)
        const S = {}, tap = (a, k) => SCREEN.onclick({ target: { closest: s => s === '[data-sc-' + a + ']' ? { dataset: a === 'tsort' ? { scTsort: k } : { scSort: k } } : null } });
        const rec = (t, l, k, want) => ({ head: l, aria: (t.heads.find(q => q[1] === k) || [])[3], rows: t.rows.map(r => r[0]), col: t.rows.map(r => (t.map[r[0]][l] || [])[1]), want });
        ctx.APP = 'sorty';
        for (const [l, k] of T['s z 30'].heads.filter(q => q[1])) { show({}); for (const n of [1, 2]) { tap('tsort', k);
          S['s ' + k + ' ' + n] = rec(read(SCREEN.innerHTML, 'sc-ttw'), l, k, _.sortItems(_.tableRows(xOf('sorty'), ...P30, 's', f2Of(xOf('sorty')))).map(z => String(z.i))); } }
        ctx.APP = '';
        for (const [l, k] of T['all z'].heads.filter(q => q[1])) { show({}); for (const n of [1, 2]) { tap('sort', k);
          S['all ' + k + ' ' + n] = rec(read(SCREEN.innerHTML, 'sc-atw'), l, k, _.sortApps(_.apps().map(_.appRow)).map(z => z.r.name)); } }
        out.order = { T, M, S };
      } finally { delete ALLF.apps.sorty; delete ctx.DATA.scr.apps.sorty; delete FILES[zn]; ctx.DATA.scr.fv = 'f11'; ctx.APP = 'Alpha App';
        _.set({ OPEN: null, SEG: 's', MORE: false, PER: '30', TS: { k: 'st', dir: 1 }, SORT: { k: 'rank', dir: 1 } }); }
      SCR.paint(); await tick(); }
    // ── v 3: the absolute status (owner, 7 Nov 2026: "ye normal nahi he — ye kam he na?") on "absy":
    // Home (a native unit shared 80 / 20 with List, an unmatched banner unit beside it), List (native 20 % + a shared banner
    // unit), Rare (few ads per view), All other screens; unit-split days ("fu") up to 21 Mar, screen-only after (σ falls back
    // to the newest 28 split days); a synthetic format benchmark; the build's W numbers in rows.s0.ab ──
    { const ak = 'a0000000000e', an2 = 'scr_' + ak + '.json.gz', W = ['2026-03-19', FT];
      const ST = (w, why, sc, cz, aw, ac, wk) => [w, why, sc, cz, cz, null, 10, aw, ac, wk];
      const ax = { key: ak, ft: FT, td: TD, d0: D0, items: [['x.y.HomeActivity', 's', 'inline'], ['x.y.ListActivity', 's', 'inline'], ['x.y.RareActivity', 's', 'inline'], ['', 'o', 'inline']],
        vis: [], V: [], A: [], ta: [], st: {}, bf: {}, dq: [], app: AP('Normal', '', 0, 0), ftu: FT, dk: '0'.repeat(ND), au: [], lo: 2,
        status: { 0: ST('Normal', '', 101, '', 'Low', 'Show rate 20% (native median 70%): ads filled but not shown; Fill 60% (native median 90%): requests not filled', [['show', 'native', 0.2, 0.7, 0.5], ['fill', 'native', 0.6, 0.9, 0.75]]),
          1: ST('Worse', 'imp/user 0.30 → 0.20 (−33%)', 67, 'Lower show rate', 'Low', 'Show rate 15% (native median 70%): ads filled but not shown', [['show', 'native', 0.15, 0.7, 0.5]]),
          2: ST('Normal', '', 100, '', 'Few ads', 'Ads / view 3.0% (banner median 12%): few ads per view', [['av', 'banner', 3, 12, 5]]),
          3: ST('Normal', '', 100, '', '', '', []) } };
      const units = [['nat_a', 'native', ['ca-app-pub-0000000000000000/2001'], 'nat_a', 'name', ''], ['ban_b', 'banner', ['ca-app-pub-0000000000000000/2002'], 'ban_b', 'name', ''], ['ghost', 'banner', [], '', '', '']];
      const af = { v: 4, key: ak, app_id: 'absy', ft: FT, td: TD, d0: D0, screens: [['x.y.HomeActivity', 's'], ['x.y.ListActivity', 's'], ['x.y.RareActivity', 's'], ['x.y.RestActivity', 's']], units, ufmt: ['native', 'banner', null], trig: [],
        days: [], adm: { 0: [], 1: [] }, notes: {}, Us: [0, 1, 2], U: [], au: [],
        rows: { s0: { st: ['Normal', '', 101], ab: { av: 30, fill: 0.6, show: 0.2, p: { native: [0.8889, 80000, 48000, 9600] }, sig: ['W', 3, '2026-03-19', '2026-03-21'], unm: 0.1111, why: '' } } } };
      for (let k = 0; k < ND; k++) { const fu = k <= 79;
        ax.V.push([1000, 500, 400, 50]); ax.A.push([300, 40, 12, 5]); ax.vis.push(1950); ax.ta.push([357, 0, 0]); ax.au.push(k > 86 ? null : 1000); af.au.push(k > 86 ? null : 1000);
        af.days.push({ v: [[0, 1000, 30000], [1, 500, 10000], [2, 400, 8000], [3, 50, 500]], a: fu ? { g: 'fu', r: [[0, 0, 80], [1, 0, 20], [0, 2, 10], [1, 1, 30], [2, 1, 5]] } : { g: 'c', r: [[0, 300], [1, 40], [2, 12], [3, 5]] },
          w: [[0, 100], [1, 40], [2, 10]], st: { v: 'w', a: 'w', w: 'w' } });
        af.adm[0].push(k > 86 ? null : [10000, k < 77 ? 7000 : 6000, k < 77 ? 1760 : 1200]); af.adm[1].push(k > 86 ? null : [5000, 4500, 4050]); af.U.push(k > 86 ? null : [400, 200, 100]); }
      for (const r of READS) { ax.st[r] = 'w'.repeat(ND); ax.bf[r] = [D0, true]; }
      const BENCH = { fmt: { native: { fill: [0.4, 0.75, 0.9, 0.97, 30], show: [0.2, 0.5, 0.7, 0.85, 30], av: [3, 8, 20, 22], nall: 60 }, banner: { fill: [0.5, 0.8, 0.9, 0.95, 40], show: [0.5, 0.7, 0.85, 0.9, 45], av: [2, 5, 12, 25], nall: 80 },
        rewarded: { fill: null, show: null, av: null, nall: 4 } }, min: { req: 1000, mt: 300, ads: 300, n: 20 }, apps: 3 };
      ALLF.apps.absy = ax; ALLF.bench = BENCH; FILES[an2] = af; ctx.DATA.scr.apps.absy = { key: ak, v: 'ab', vl: 'ab', from: D0, ft: FT }; ctx.DATA.scr.fv = 'f12';
      try {
        ctx.APP = 'absy'; _.set({ OPEN: null, SEG: 's', PER: '30', TS: { k: 'st', dir: 1 } }); SCR.paint(); await tick(8); _.set({ MORE: true }); SCR.paint(); h = SCREEN.innerHTML;
        const f2 = _.FILES[an2].raw, rr = (i, lo, hi) => { const e = _.abRates(ax, f2, i, lo, hi); return { fill: e.fill, show: e.show, unm: e.unm, sig: e.sig, sh: e.sh, p: e.p, nK: e.nK, why: e.why }; };
        const titleOf = (hh, i, lab) => { const H = hdOf(hh, 'sc-ttw'), c = tds(hh, i)[H.indexOf(lab)]; return c ? [(/ title="([^"]*)"/.exec(c[0]) || [])[1] || '', / class="sc-lo"/.test(c[0])] : null; };
        out.abs = { heads: heads(h), rows: [0, 1, 2, 3].map(i => cm(h, i)), lo: [0, 1, 2].map(i => ({ fill: titleOf(h, i, 'Fill'), show: titleOf(h, i, 'Show rate'), av: titleOf(h, i, 'Ads / view') })),
          r30: [0, 1, 2, 3].map(i => rr(i, ...P30)), r7: rr(0, '2026-03-22', FT), rW: rr(0, ...W), abW: f2.rows.s0.ab, today: rr(0, TD, TD), order: _.sortItems(_.tableRows(ax, ...P30, 's', f2)).map(z => z.i),
          attn: h.slice(h.indexOf('id="sc-attn"'), h.indexOf('id="sc-tcard"')), tot: h.slice(h.indexOf('id="sc-totw"'), h.indexOf('id="sc-attn"')),
          pool: (() => { const e = _.abPool(f2, ax, [0, 1, 2], ...P30); return [e.fill, e.show, e.nK]; })(), trig: _.abPool(f2, ax, [2], ...P30).why };
        // the W numbers: the period = the status window (Custom) — the page's own Fill / Show = the build's rows.s0.ab
        _.set({ PER: 'cus', PF: W[0], PTO: W[1] }); SCR.paint(); out.abs.cusW = cm(SCREEN.innerHTML, 0);
        _.set({ PER: 'today' }); SCR.paint(); out.abs.todayCells = cm(SCREEN.innerHTML, 0);
        _.set({ PER: '30', OPEN: 0, SEC: 'ov' }); SCR.paint(); h = SCREEN.innerHTML; out.abs.dd = h.slice(h.indexOf('id="sc-dd"'));
        out.abs.dds = (/<span class="sc-dds">(.*?)<\/span><button/.exec(h) || [])[1] || null;
        _.set({ OPEN: null }); ctx.APP = ''; SCR.paint(); h = SCREEN.innerHTML; out.abs.all = am(h, 'absy'); out.abs.allHeads = [...(/<table class="sc-t"><thead><tr>(.*?)<\/tr>/.exec(h.slice(h.indexOf('id="sc-atw"'))) || [, ''])[1].matchAll(/data-sc-sort="([a-z]+)"/g)].map(m => m[1]);
        // the How it works fold: the benchmark as measured, with its basis
        ctx.APP = 'absy'; SCR.paint(); h = SCREEN.innerHTML; out.abs.how = h.slice(h.indexOf('data-sc-fold="how"'));
        // the benchmark failed (abs word ""): "—", never a word; no benchmark shipped: nothing marked; a status without the abs
        // fields (an older shape): its own word and cause
        const xb = JSON.parse(JSON.stringify(ax)); xb.status['0'][7] = ''; xb.status['0'][8] = ''; xb.status['0'][9] = [];
        out.abs.failed = cm(_.tableHtml(xb, 'absy', ...P30), 0).Screen;
        const xo = JSON.parse(JSON.stringify(ax)); for (const k in xo.status) xo.status[k] = xo.status[k].slice(0, 7);
        out.abs.older = cm(_.tableHtml(xo, 'absy', ...P30), 1);
        // N/A and Too early (the old judge's words, an empty abs cause): the line under the chip is still their why; OK: none
        out.abs.naWhy = [['N/A', "Too few ads — 0.4% of the app's inline ads", 'N/A'], ['Too early', '21 ads expected (needs 30)', 'Too early'], ['Normal', 'imp/user 1.00 → 1.02 (+2%)', 'OK']]
          .map(([w, why, aw]) => _.stWhy([w, why, null, '', '', null, 10, aw, '', []], ['x.y.HomeActivity', 's', 'inline']));
        // the details' status line of an N/A screen: its word and why once (the abs word is the old judge's)
        out.abs.ddNa = _.ddSt(['N/A', "Too few ads — 0.4% of the app's inline ads", null, '', '', null, 10, 'N/A', '', []], ['x.y.HomeActivity', 's', 'inline']);
        // the abs word on W against the period's own marks (30 days): Home OK on W with its cells marked, Rare Low on W with no
        // Fill / Show mark → "(last 10 days)" on the chip; List Low with its marks → the plain chip
        const xd = JSON.parse(JSON.stringify(ax)); xd.status['0'][7] = 'OK'; xd.status['0'][8] = ''; xd.status['0'][9] = [];
        xd.status['2'][7] = 'Low'; xd.status['2'][8] = 'Fill 50% (banner median 90%): requests not filled'; xd.status['2'][9] = [['fill', 'banner', 0.5, 0.9, 0.8]];
        out.abs.dis = [0, 1, 2].map(i => cm(_.tableHtml(xd, 'absy', ...P30), i).Screen);
        // a screen with NO ads of its own in the period (Rare from 22 Mar; its views go on) — the period has no unit-split day, so
        // σ falls back to the split days up to 21 Mar, when Rare still had ban_b's ads: no Fill / Show from them, "—" + the why
        { const xz = JSON.parse(JSON.stringify(ax)); for (let k = 80; k < ND; k++) xz.A[k][2] = 0;
          const rz = (xx, i) => { const e = _.abRates(xx, f2, i, '2026-03-22', FT); return { fill: e.fill, show: e.show, why: e.why, p: e.p, sig: e.sig }; };
          _.set({ MORE: true }); out.abs.noads = { z: rz(xz, 2), ctl: rz(ax, 2), cells: cm(_.tableHtml(xz, 'absy', '2026-03-22', FT), 2), home: rz(xz, 0) }; }
        // the app's ABSOLUTE state (owner: "ye normal nahi he — ye kam he"): its screens' abs words, vs own past a labelled second line
        { const vx = (st, lo, app) => { const y = JSON.parse(JSON.stringify(ax)); for (const k in st) y.status[k][7] = st[k]; y.lo = lo; if (app) y.app = app; return y; };
          const one = y => { const z = _.appAbs(y); return z ? [_.absAppChip(z), _.appSub(z, y.app)] : null; };
          out.abs.app = { low: one(ax), few: one(vx({ 0: 'OK', 1: 'OK' }, 0)), ok: one(vx({ 0: 'OK', 1: 'OK', 2: 'OK' }, 0)),
            noneNa: one(vx({ 0: 'N/A', 1: 'Too few ads', 2: 'No ads' }, 0, AP('N/A', 'Not whole — 3 whole days', 0, 0))),
            noneOwn: one(vx({ 0: 'N/A', 1: 'Too few ads', 2: 'No ads' }, 0)), failed: one(vx({ 0: '', 1: '', 2: '' }, null)),
            older: (() => { const y = JSON.parse(JSON.stringify(ax)); for (const k in y.status) y.status[k] = y.status[k].slice(0, 7); return _.appAbs(y); })(),
            own: [AP('Better', 'App imp/user 1.00 → 1.31 (+31%)', 0, 0, [131, '', null, null, null]), AP('Worse', 'AdMob imp/user −35%', 1, 0, [65, 'GA4 logging changed', null, null, { st: 'admob' }]),
              AP('Normal', 'App imp/user 3.53 → 3.42 (−3%)', 0, 0, [97, '', null, null, null]), AP('Watch', 'x', 0, 1, [88, '', null, null, null]), AP('Too early', 'y', 0, 0)].map(_.ownLine) };
          // the All apps sort by status: absolute first (Low by its Low screens, most first · Few ads · OK · — · N/A), then the old keys
          const zr = (name, w, n, st, dau) => ({ r: { name }, ab: w == null ? null : { w, n }, st, low: w === 'Low' ? n : 0, wn: st === 'Worse' ? 1 : 0, an: 0, dau });
          _.set({ SORT: { k: 'rank', dir: 1 } });
          out.abs.appSort = _.sortApps([zr('ok', 'OK', 3, 'Worse', 9), zr('na', 'N/A', 0, 'Normal', 99), zr('low1', 'Low', 1, 'Better', 50), zr('few', 'Few ads', 2, 'Normal', 5),
            zr('low3', 'Low', 3, 'Normal', 1), zr('dash', '', 0, 'Worse', 7), zr('early', 'Too early', 0, 'Too early', 3)]).map(z => z.r.name);
          // the app page's top line, All apps, Needs attention (a Worse App row: labelled, after the absolute lines; all OK: "Sab OK")
          ctx.APP = 'absy'; SCR.paint(); h = SCREEN.innerHTML; out.abs.appCrumb = (/<div class="sc-crumb">(.*?)<\/div>/.exec(h) || [])[1] || '';
          _.set({ PER: 'yday' }); SCR.paint(); out.abs.appCrumbYday = (/<div class="sc-crumb">(.*?)<\/div>/.exec(SCREEN.innerHTML) || [])[1] || ''; _.set({ PER: '30' });
          const xw = JSON.parse(JSON.stringify(ax)); xw.app = AP('Worse', 'App imp/user 1.00 → 0.70 (−30%)', 1, 0, [70, 'Lower show rate', null, null, null]);
          const xo = vx({ 0: 'OK', 1: 'OK', 2: 'OK' }, 0); xo.status['1'][0] = 'Normal';
          out.abs.attnApp = [_.attnHtml(xw, 'absy'), _.attnHtml(xo, 'absy')];
          ctx.APP = ''; SCR.paint(); h = SCREEN.innerHTML; out.abs.allCell = am(h, 'absy')['App · status']; out.abs.allNote = h.slice(h.indexOf('<h3>All apps</h3>'), h.indexOf('id="sc-atw"'));
          ctx.APP = 'absy'; SCR.paint(); h = SCREEN.innerHTML; out.abs.howApp = (/<b>App ka status<\/b>[^<]*/.exec(h) || [''])[0]; }
        // keep() at the page's end (a held height bigger than the content — the "Show N more screens" tap): the held height grows
        // by what the page below the window lacks, so the tapped button moves 0 px; the reader's scroll lets the blank go
        { const W = ctx.window, D = ctx.document, sv = { sb: W.scrollBy, ae: W.addEventListener, re: W.removeEventListener, se: D.scrollingElement, qs: SCREEN.querySelector, ch: SCREEN.children, oh: Object.getOwnPropertyDescriptor(SCREEN, 'offsetHeight') };
          const P = { y: 2200, vh: 800, content: 2500, bt: 2400 }, on = {}, btn = { getBoundingClientRect: () => ({ top: P.bt - P.y, bottom: P.bt - P.y + 40, height: 40 }) };
          try {
            Object.defineProperty(SCREEN, 'offsetHeight', { configurable: true, get: () => Math.max(P.content, parseFloat(SCREEN.style.minHeight) || 0) });
            SCREEN.getBoundingClientRect = () => ({ top: -P.y, height: SCREEN.offsetHeight, bottom: SCREEN.offsetHeight - P.y });
            SCREEN.children = [{ hidden: false, getBoundingClientRect: () => ({ top: -P.y, bottom: P.content - P.y, height: P.content }) }];
            SCREEN.querySelector = q => q === '[data-sc-more]' ? btn : null; SCREEN.style.minHeight = '3000px';
            D.scrollingElement = { get scrollHeight() { return SCREEN.offsetHeight; } }; Object.defineProperty(W, 'scrollY', { configurable: true, get: () => P.y });
            W.scrollBy = (x, dy) => { P.y = Math.max(0, Math.min(P.y + dy, SCREEN.offsetHeight - P.vh)); }; W.innerHeight = P.vh;
            W.addEventListener = (t, f) => { on[t] = f; }; W.removeEventListener = t => { delete on[t]; };
            const y0 = btn.getBoundingClientRect().top;
            _.keep('[data-sc-more]', () => { P.content += 300; P.bt += 300; });
            const r = { moved: btn.getBoundingClientRect().top - y0, held: SCREEN.style.minHeight, wait: !!on.scroll };
            P.y -= 600; if (on.scroll) on.scroll(); r.after = SCREEN.style.minHeight; r.blank = SCREEN.offsetHeight - P.content;
            // a held height that gives the page 8 px less than it adds (its last block's margin): room() measures again
            // (the page at its end, no hold; the rows add 300 px, the button moves 300.5: a first raise of 1 px loses 8)
            SCREEN.style.minHeight = ''; P.content = 2500; P.y = 1700; P.bt = 1900; const sh0 = Object.getOwnPropertyDescriptor(D.scrollingElement, 'scrollHeight');
            Object.defineProperty(D.scrollingElement, 'scrollHeight', { configurable: true, get: () => { const m = parseFloat(SCREEN.style.minHeight) || 0; return m > P.content ? m - 8 : Math.max(m, P.content); } });
            W.scrollBy = (x, dy) => { P.y = Math.max(0, Math.min(P.y + dy, D.scrollingElement.scrollHeight - P.vh)); };
            const y1 = btn.getBoundingClientRect().top; _.keep('[data-sc-more]', () => { P.content += 300; P.bt += 300.5; }); r.margin = btn.getBoundingClientRect().top - y1;
            Object.defineProperty(D.scrollingElement, 'scrollHeight', sh0); if (on.scroll) { P.y = 0; on.scroll(); }
            // room() alone: only a scroll DOWN past the page's end raises the held height
            SCREEN.style.minHeight = '1000px'; P.content = 900; P.y = 150; r.small = [(_.roomBelow(SCREEN, 40), SCREEN.style.minHeight), (_.roomBelow(SCREEN, -300), SCREEN.style.minHeight), (_.roomBelow(SCREEN, 120), SCREEN.style.minHeight)];
            out.abs.keepEnd = r;
          } finally { W.scrollBy = sv.sb; W.addEventListener = sv.ae; W.removeEventListener = sv.re; D.scrollingElement = sv.se; SCREEN.querySelector = sv.qs; SCREEN.children = sv.ch; delete SCREEN.getBoundingClientRect;
            delete SCREEN.offsetHeight; if (sv.oh) Object.defineProperty(SCREEN, 'offsetHeight', sv.oh); delete W.scrollY; W.scrollY = 0; W.innerHeight = 800; SCREEN.style.minHeight = ''; } }
        // late() inside the table: file 2 grows the ⏳ cells of the rows above the reading line — the row being read stays put
        { const W = ctx.window, D = ctx.document, sv = { sb: W.scrollBy, qs: D.querySelector, ch: SCREEN.children };
          const P = { y: 1000, card: 900, head: 100, h: Array(10).fill(40) };
          const rowAt = i => { let t = P.card + P.head; for (let j = 0; j < i; j++) t += P.h[j]; return { dataset: { scOpen: String(i) }, getBoundingClientRect: () => ({ top: t - P.y, bottom: t + P.h[i] - P.y, height: P.h[i] }) }; };
          const tbl = () => ({ getBoundingClientRect: () => ({ top: P.card + P.head - P.y, bottom: P.card + P.head + P.h.reduce((a, b) => a + b, 0) - P.y }), querySelectorAll: () => P.h.map((_h, i) => rowAt(i)) });
          const card = { getBoundingClientRect: () => ({ top: P.card - P.y, bottom: P.card + 2000 - P.y, height: 2000 }), querySelector: q => q === '#sc-ttw' ? tbl() : null };
          const res = {};
          try {
            SCREEN.children = [{ getBoundingClientRect: () => ({ top: -P.y, bottom: P.card - P.y, height: P.card }) }, card]; Object.defineProperty(W, 'scrollY', { configurable: true, get: () => P.y });
            ctx.getComputedStyle = e => ({ position: e && e.sticky ? 'sticky' : 'static' });
            W.scrollBy = (x, dy) => { P.y += dy; };
            D.querySelector = q => { const m = /^#sc-ttw tbody tr\[data-sc-open="(\d+)"\]$/.exec(q); return m ? rowAt(+m[1]) : sv.qs(q); };
            // the reading line (30 % of 800 = 240 px): row 6 (its top at 240) is the first at or below it; rows 0–5 grow by 23 px each
            let y0 = rowAt(6).getBoundingClientRect().top; _.late(() => { for (let j = 0; j < 6; j++) P.h[j] += 23; }); res.row = rowAt(6).getBoundingClientRect().top - y0;
            // every row above the line (the note under the table being read): the last row's bottom stays
            P.y = 1900; P.h = Array(10).fill(40); y0 = rowAt(9).getBoundingClientRect().bottom; _.late(() => { for (let j = 0; j < 10; j++) P.h[j] += 23; }); res.below = rowAt(9).getBoundingClientRect().bottom - y0;
            // the period bar stuck at the top (sticky, down to 280 px): it never anchors (it does not move with the page) and the
            // reading line goes below it — row 7 (its top at 280) is the one being read
            P.y = 1000; P.h = Array(10).fill(40); SCREEN.children.splice(1, 0, { sticky: true, getBoundingClientRect: () => ({ top: 0, bottom: 280, height: 280 }) });
            y0 = rowAt(7).getBoundingClientRect().top; _.late(() => { for (let j = 0; j < 7; j++) P.h[j] += 23; }); res.sticky = rowAt(7).getBoundingClientRect().top - y0;
            out.abs.lateRow = res;
          } finally { W.scrollBy = sv.sb; D.querySelector = sv.qs; SCREEN.children = sv.ch; delete W.scrollY; W.scrollY = 0; delete ctx.getComputedStyle; } }
        // ✕ Close on a phone: the details' Back step goes with them (hbDrop → history.go(-1)) and, as that step back lands, the
        // browser puts back the scroll it saved when they opened (scrollRestoration 'auto') — after keep() put the row back.
        // Once OUR step back has landed the row goes back again a frame later (0 px, room made below; the blank goes as the
        // reader scrolls); another step back still on its way: it waits for that one; the tab left before the frame: nothing;
        // no landing: the 1.5 s timer takes the listener off; a tap that keeps the step, a close with no step (a wide
        // screen), a step dropped with no step back started: nothing waits
        { const W = ctx.window, D = ctx.document, sv = { sb: W.scrollBy, ae: W.addEventListener, re: W.removeEventListener, se: D.scrollingElement, qs: SCREEN.querySelector, ch: SCREEN.children,
            oh: Object.getOwnPropertyDescriptor(SCREEN, 'offsetHeight'), hd: ctx.hbDrop, hb: ctx.HB, st: ctx.setTimeout, iw: W.innerWidth, app: ctx.APP };
          // the page: the reader scrolled down to the details' ✕ Close (the row 1000 px above the window); they opened at 1700
          const P = { y: 3000, vh: 800, content: 5200 }, on = {}, fr = [], tm = [], row = { getBoundingClientRect: () => ({ top: 2000 - P.y, bottom: 2040 - P.y, height: 40 }) };
          const L = t => (on[t] || []).length, frames = () => { while (fr.length) fr.shift()(); }, fire = t => (on[t] || []).slice().forEach(f => f());
          // our step back lands: hbPop's turn (busy off unless another step back starts), the popstate listeners, the browser's
          // restore of the scroll saved at the open, its scroll event; then the frames
          const land = busyAgain => { ctx.HB.busy = !!busyAgain; fire('popstate'); P.y = 1700; fire('scroll'); };
          const close = async (st, busy) => { P.y = 3000; P.content = 5200; SCREEN.style.minHeight = ''; ctx.HB = { st: st || [{ tag: 'scr-dd' }], busy: false, go: busy !== false }; _.set({ OPEN: 1 });
            const y0 = row.getBoundingClientRect().top; SCREEN.onclick({ target: { closest: s => s === '[data-sc-close]' ? {} : null } }); await tick(); return y0; };
          const res = {};
          try {
            ctx.APP = ''; Object.defineProperty(SCREEN, 'offsetHeight', { configurable: true, get: () => Math.max(P.content, parseFloat(SCREEN.style.minHeight) || 0) });
            SCREEN.getBoundingClientRect = () => ({ top: -P.y, height: SCREEN.offsetHeight, bottom: SCREEN.offsetHeight - P.y });
            SCREEN.children = [{ hidden: false, getBoundingClientRect: () => ({ top: -P.y, bottom: P.content - P.y, height: P.content }) }];
            SCREEN.querySelector = q => q === 'tr[data-sc-open="1"]' ? row : null;
            D.scrollingElement = { get scrollHeight() { return SCREEN.offsetHeight; } }; Object.defineProperty(W, 'scrollY', { configurable: true, get: () => P.y });
            W.scrollBy = (x, dy) => { P.y = Math.max(0, Math.min(P.y + dy, SCREEN.offsetHeight - P.vh)); }; W.innerHeight = P.vh; W.innerWidth = 375;
            W.addEventListener = (t, f) => { (on[t] = on[t] || []).push(f); }; W.removeEventListener = (t, f) => { on[t] = (on[t] || []).filter(g => g !== f); };
            ctx.requestAnimationFrame = f => { fr.push(f); return fr.length; }; ctx.setTimeout = (f, ms) => { tm.push([f, ms]); return tm.length; };
            // hbDrop → hbSync's stand-in: the step goes off HB.st and our step back is on its way (go); the repaint without the
            // details card (1500 px)
            ctx.hbDrop = t => { if (!ctx.HB.st.some(z => z.tag === t)) return; ctx.HB.st = ctx.HB.st.filter(z => z.tag !== t); ctx.HB.busy = ctx.HB.go; P.content -= 1500; };
            const lim = () => { const x = tm.filter(z => z[1] === 1500); return x.length ? x[x.length - 1] : null; };
            let y0 = await close(); res.wait = [L('popstate'), (lim() || [])[1] || null, row.getBoundingClientRect().top - y0];
            land(); res.landed = L('popstate'); frames(); res.moved = row.getBoundingClientRect().top - y0;
            P.y -= 600; fire('scroll'); P.y = 0; fire('scroll'); res.blank = SCREEN.offsetHeight - P.content; res.scrollLeft = L('scroll');
            y0 = await close(); land(true); res.again = [L('popstate'), fr.length]; land(); frames(); res.againMoved = row.getBoundingClientRect().top - y0;
            y0 = await close(); land(); ON = 'x'; frames(); ON = 'scr'; res.left = row.getBoundingClientRect().top - y0;
            tm.length = 0; await close(); const tt = lim(); if (tt) tt[0](); res.timeout = [tt ? tt[1] : null, L('popstate')];
            const none = [];
            ctx.HB = { st: [{ tag: 'scr-dd' }], busy: false }; _.set({ OPEN: 1 }); _.keep('tr[data-sc-open="1"]', () => {}); await tick(); none.push(L('popstate')); _.set({ OPEN: null });
            await close([]); none.push(L('popstate')); await close(null, false); none.push(L('popstate'));
            res.none = none; out.abs.closeBack = res;
          } finally { SCREEN.style.minHeight = ''; fire('scroll'); W.scrollBy = sv.sb; W.addEventListener = sv.ae; W.removeEventListener = sv.re; D.scrollingElement = sv.se; SCREEN.querySelector = sv.qs; SCREEN.children = sv.ch;
            delete SCREEN.getBoundingClientRect; delete SCREEN.offsetHeight; if (sv.oh) Object.defineProperty(SCREEN, 'offsetHeight', sv.oh); delete W.scrollY; W.scrollY = 0; W.innerHeight = 800; W.innerWidth = sv.iw;
            ctx.hbDrop = sv.hd; ctx.HB = sv.hb; ctx.setTimeout = sv.st; delete ctx.requestAnimationFrame; ctx.APP = sv.app; _.set({ OPEN: null }); } }
        delete ALLF.bench; ctx.DATA.scr.fv = 'f12b'; SCR.paint(); await tick(); SCR.paint(); h = SCREEN.innerHTML;
        out.abs.nobench = [h.includes('data-sc-open="0"'), /class="sc-lo"/.test(h.slice(h.indexOf('id="sc-ttw"')))];
      } finally { delete ALLF.apps.absy; delete ALLF.bench; delete FILES[an2]; delete ctx.DATA.scr.apps.absy; ctx.DATA.scr.fv = 'f13'; ctx.APP = 'Alpha App';
        _.set({ OPEN: null, SEG: 's', MORE: false, PER: '30', TS: { k: 'st', dir: 1 }, SORT: { k: 'rank', dir: 1 } }); }
      SCR.paint(); await tick(); }
    // ── the full-screen triggers on the same absolute rule (owner, 7 Nov 2026: Normal + Score out there too) on "trigy":
    // Back press (int_back + house_exit, no AdMob id) and Save / apply (int_save) share ONE AdMob interstitial unit 90 / 10
    // (σ), its show rate under the interstitial p25; Save / apply rewarded (no benchmark: shown, never judged); App resume
    // without ads from 19 Mar; one Low screen beside them; a synthetic benchmark; the build's W numbers in rows.t0.ab ──
    { const tk = 'a0000000000f', tn2 = 'scr_' + tk + '.json.gz', W = ['2026-03-19', FT];
      const ST = (w, why, sc, cz, aw, ac, wk) => [w, why, sc, cz, cz, null, 10, aw, ac, wk];
      const tx = { key: tk, ft: FT, td: TD, d0: D0, items: [['x.y.HomeActivity', 's', 'inline'], ['', 'o', 'inline'], ['Back press', 'fs', 'interstitial'], ['Save / apply', 'fs', 'interstitial'],
        ['Save / apply', 'fs', 'rewarded'], ['App resume', 'fs', 'appopen']], vis: [], V: [], A: [], ta: [], st: {}, bf: {}, dq: [], app: AP('Normal', '', 1, 0), ftu: FT, dk: '0'.repeat(ND), au: [], lo: 1, lt: 2,
        status: { 0: ST('Normal', '', 100, '', 'Low', 'Fill 60% (banner median 90%): requests not filled', [['fill', 'banner', 0.6, 0.9, 0.8]]),
          2: ST('Worse', 'imp/app user 0.15 → 0.10 (−33%)', 67, 'Lower show rate', 'Low', 'Show rate 21% (interstitial median 50%): ads filled but not shown', [['show', 'interstitial', 0.2072, 0.5, 0.3]]),
          3: ST('Normal', '', 100, '', 'Low', 'Show rate 21% (interstitial median 50%): ads filled but not shown', [['show', 'interstitial', 0.2072, 0.5, 0.3]]),
          4: ST('Normal', '', 100, '', 'No benchmark', 'rewarded: no benchmark (n < 20)', []), 5: ST('Normal', '', 100, '', 'No ads', '10 din me is trigger ke koi ad nahi', []) } };
      const U = ['ca-app-pub-0000000000000000/3001', 'ca-app-pub-0000000000000000/3002', 'ca-app-pub-0000000000000000/3003', 'ca-app-pub-0000000000000000/3004'];
      const units = [['ban_h', 'banner', [U[0]], 'ban_h', 'name', ''], ['int_back', 'interstitial', [U[1]], 'int_back', 'name', 'Back press'], ['int_save', 'interstitial', [U[1]], 'int_back', 'name', 'Save / apply'],
        ['aoa_res', 'appopen', [U[2]], 'aoa_res', 'name', 'App resume'], ['house_exit', 'interstitial', [], '', '', 'Back press'], ['rew_save', 'rewarded', [U[3]], 'rew_save', 'name', 'Save / apply']];
      const tf = { v: 4, key: tk, app_id: 'trigy', ft: FT, td: TD, d0: D0, screens: [['x.y.HomeActivity', 's'], ['x.y.RestActivity', 's']], units, ufmt: ['banner', 'interstitial', 'interstitial', 'appopen', null, 'rewarded'],
        trig: [['interstitial', 'Back press', [1, 4]], ['interstitial', 'Save / apply', [2]], ['rewarded', 'Save / apply', [5]], ['appopen', 'App resume', [3]]], days: [], adm: { 0: [], 1: [], 2: [], 3: [], 5: [] }, notes: {}, Us: [0], U: [], au: [],
        rows: { t0: { st: ['Worse', 'imp/app user 0.15 → 0.10 (−33%)', 67], ab: { av: null, fill: 0.83, show: 0.2072, p: { interstitial: [0.9, 90000, 74700, 15480] }, sig: ['W', 10, W[0], W[1]], unm: 0.1, why: '' } } } };
      for (let k = 0; k < ND; k++) { const ar = k < 77 ? 50 : 0;
        tx.V.push([1000, 100, null, null, null, null]); tx.A.push([300, 20, 100, 10, 40, ar]); tx.vis.push(2000); tx.ta.push([320, 150 + ar, 0]); tx.au.push(k > 86 ? null : 1000); tf.au.push(k > 86 ? null : 1000);
        tf.days.push({ v: [[0, 1000, 30000], [1, 100, 1000]], a: { g: 'fu', r: [[0, 0, 300]] }, w: [[0, 300], [1, 90], [2, 10], [3, ar], [4, 10], [5, 40]], st: { v: 'w', a: 'w', w: 'w' } });
        const c = k > 86; tf.adm[0].push(c ? null : [5000, 4500, 4000]); tf.adm[1].push(c ? null : [10000, k < 80 ? 9000 : 8000, k < 80 ? 2000 : 1600]); tf.adm[2].push(tf.adm[1][k]);
        tf.adm[3].push(c ? null : [3000, 2700, 900]); tf.adm[5].push(c ? null : [800, 700, 600]); tf.U.push(c ? null : [400]); }
      for (const r of READS) { tx.st[r] = 'w'.repeat(ND); tx.bf[r] = [D0, true]; }
      const BENCH = { fmt: { interstitial: { fill: [0.4, 0.8, 0.9, 0.95, 30], show: [0.2, 0.3, 0.5, 0.7, 30], av: null, nall: 40 }, appopen: { fill: [0.4, 0.8, 0.9, 0.95, 25], show: [0.1, 0.2, 0.3, 0.5, 25], av: null, nall: 30 },
        banner: { fill: [0.5, 0.8, 0.9, 0.95, 40], show: [0.5, 0.7, 0.85, 0.9, 45], av: [2, 5, 12, 25], nall: 80 }, rewarded: { fill: null, show: null, av: null, nall: 3 } }, min: { req: 1000, mt: 300, ads: 300, n: 20 }, apps: 3 };
      ALLF.apps.trigy = tx; ALLF.bench = BENCH; FILES[tn2] = tf; ctx.DATA.scr.apps.trigy = { key: tk, v: 'tg', vl: 'tg', from: D0, ft: FT }; ctx.DATA.scr.fv = 'f14';
      try {
        ctx.APP = 'trigy'; _.set({ OPEN: null, SEG: 'f', PER: '30', TS: { k: 'st', dir: 1 } }); SCR.paint(); await tick(8); SCR.paint(); h = SCREEN.innerHTML;
        const f2 = _.FILES[tn2].raw, rt = (i, lo, hi) => { const e = _.abTrig(tx, f2, i, lo, hi); return { fill: e.fill, show: e.show, unm: e.unm, sig: e.sig, sh: e.sh, p: e.p, nK: e.nK, why: e.why }; };
        const ttl = (hh, i, lab) => { const H = hdOf(hh, 'sc-ttw'), c = tds(hh, i)[H.indexOf(lab)]; return c ? [(/ title="([^"]*)"/.exec(c[0]) || [])[1] || '', / class="sc-lo"/.test(c[0])] : null; };
        out.trg = { heads: heads(h), rows: [2, 3, 4, 5].map(i => cm(h, i)), lo: [2, 4].map(i => ({ fill: ttl(h, i, 'Fill'), show: ttl(h, i, 'Show rate') })), note: (/<p class="sc-note"><b>Imp \/ app user \/ day<\/b>.*?<\/p>/.exec(h) || [''])[0],
          r30: [2, 3, 4, 5].map(i => rt(i, ...P30)), rW: rt(2, ...W), abW: f2.rows.t0.ab, r7: rt(5, '2026-03-22', FT), today: rt(2, TD, TD), order: _.sortItems(_.tableRows(tx, ...P30, 'f', f2)).map(z => z.i),
          attn: h.slice(h.indexOf('id="sc-attn"'), h.indexOf('id="sc-tcard"')), crumb: (/<div class="sc-crumb">(.*?)<\/div>/.exec(h) || [])[1] || '' };
        _.set({ PER: 'cus', PF: W[0], PTO: W[1] }); SCR.paint(); out.trg.cusW = cm(SCREEN.innerHTML, 2);
        _.set({ PER: '7' }); SCR.paint(); out.trg.d7 = cm(SCREEN.innerHTML, 5);
        _.set({ PER: '30', OPEN: 2, SEC: 'ov' }); SCR.paint(); h = SCREEN.innerHTML; out.trg.dd = h.slice(h.indexOf('id="sc-dd"')); out.trg.dds = (/<span class="sc-dds">(.*?)<\/span><button/.exec(h) || [])[1] || null;
        _.set({ OPEN: null }); ctx.APP = ''; SCR.paint(); h = SCREEN.innerHTML; out.trg.all = am(h, 'trigy');
        // an older file (no "lt": its triggers ship ""): their own word, as before; the benchmark failed ("lt" null): "—"
        const xo = JSON.parse(JSON.stringify(tx)); delete xo.lt; for (const k of ['2', '3', '4', '5']) xo.status[k] = xo.status[k].slice(0, 7).concat(['', '', []]);
        const xb = JSON.parse(JSON.stringify(tx)); xb.lt = null; xb.lo = null; for (const k in xb.status) xb.status[k] = xb.status[k].slice(0, 7).concat(['', '', []]);
        _.set({ SEG: 'f' }); out.trg.older = [cm(_.tableHtml(xo, 'trigy', ...P30), 2), cm(_.tableHtml(xo, 'trigy', ...P30), 4)]; out.trg.olderApp = _.appAbs(xo);
        out.trg.failed = cm(_.tableHtml(xb, 'trigy', ...P30), 2).Trigger; out.trg.failedApp = _.appAbs(xb);
        out.trg.onlyT = (() => { const y = JSON.parse(JSON.stringify(tx)); y.lo = 0; y.status['0'][7] = 'OK'; const z = _.appAbs(y); return _.absAppChip(z); })();
      } finally { delete ALLF.apps.trigy; delete ALLF.bench; delete FILES[tn2]; delete ctx.DATA.scr.apps.trigy; ctx.DATA.scr.fv = 'f15'; ctx.APP = 'Alpha App';
        _.set({ OPEN: null, SEG: 's', MORE: false, PER: '30', TS: { k: 'st', dir: 1 }, SORT: { k: 'rank', dir: 1 } }); }
      SCR.paint(); await tick(); }
    // ── v 4 (owner, 8 Nov 2026): Firebase's numbers, the AdMob full-screen rows, three signals ──
    {
      const cellsOf = (hh, id) => { const t = hh.slice(hh.indexOf('id="' + id + '"')); const hd = [...((/<thead><tr>(.*?)<\/tr><\/thead>/.exec(t) || [, ''])[1]).matchAll(/<th[^>]*>(?:<button[^>]*>)?([^<]*)/g)].map(m => m[1]);
        const body = (/<tbody>(.*?)<\/tbody>/.exec(t) || [, ''])[1]; const rows = {};
        for (const m of body.matchAll(/<tr[^>]*>(.*?)<\/tr>/g)) { const tds = [...m[1].matchAll(/<td[^>]*>(.*?)<\/td>/g)].map(q => q[1]); const nm = (/<span class="sc-n">([^<]*)/.exec(tds[0] || '') || [])[1];
          if (nm != null) rows[nm.trim()] = Object.fromEntries(hd.map((hh2, j) => [hh2, (tds[j] || '').replace(/<small[^>]*>.*?<\/small>/g, '').replace(/<[^>]+>/g, '').trim()])); }
        return { hd, rows }; };
      ctx.APP = 'Alpha App'; _.set({ OPEN: null, PER: '30', MORE: false, PREAD: true }); SCR.paint(); await tick(8); SCR.paint();
      let hh = SCREEN.innerHTML;
      const T = cellsOf(hh, 'sc-ttw');
      out.v4 = { heads: T.hd, rows: T.rows, attn: hh.slice(hh.indexOf('id="sc-attn"'), hh.indexOf('id="sc-tcard"')),
        note: (/<p class="sc-note" id="sc-tnote">.*?<\/p>/.exec(hh) || [''])[0], crumb: (/<div class="sc-crumb">(.*?)<\/div>/.exec(hh) || [, ''])[1],
        old: ['Needs attention', 'App total', 'data-sc-seg', 'score', 'Normal'].filter(w => hh.includes(w)) };
      // the period's sums (the page's own, over file 2's days): the 30 days of Alpha's synthetic file
      const f2a = _.FILES['scr_' + KEY.a + '.json.gz'].raw, R30 = _.v4Rows(ALLF.apps[ID.a], f2a, '2026-02-27', '2026-03-28');
      out.v4.sums = { tot: R30.tot, n: [R30.nd, R30.nv, R30.na, R30.nm], fs: R30.rows.filter(r => r.t === 'f').map(r => [r.name, r.ads, r.rev, r.dn, r.dd]) };
      // a Custom range the build does not offer: no users, no signals — said why
      _.set({ PER: 'cus', PF: '2026-03-02', PTO: '2026-03-20' }); SCR.paint(); hh = SCREEN.innerHTML;
      out.v4.cus = { rows: cellsOf(hh, 'sc-ttw').rows, attn: hh.slice(hh.indexOf('id="sc-attn"'), hh.indexOf('id="sc-tcard"')) };
      // a Custom range that IS one of the build's periods: its users and signals
      _.set({ PER: 'cus', PF: '2026-02-27', PTO: '2026-03-28' }); SCR.paint(); out.v4.cus30 = cellsOf(SCREEN.innerHTML, 'sc-ttw').rows;
      // a month whose users GA4 sampled
      _.set({ PER: 'mon:2026-02' }); SCR.paint(); hh = SCREEN.innerHTML; out.v4.feb = { rows: cellsOf(hh, 'sc-ttw').rows, note: (/<p class="sc-note" id="sc-tnote">.*?<\/p>/.exec(hh) || [''])[0] };
      // Today: no final day — no signals (said why), the full-screen rows kept with "—" (AdMob's day not complete)
      _.set({ PER: 'today' }); SCR.paint(); hh = SCREEN.innerHTML;
      out.v4.today = { attn: hh.slice(hh.indexOf('id="sc-attn"'), hh.indexOf('id="sc-tcard"')), rows: cellsOf(hh, 'sc-ttw').rows,
        fsWhy: /<td title="AdMob ka din abhi poora nahi[^"]*">—<\/td>/.test(hh) };
      // a month before the app's first day: not "Custom" — the app has no data there
      _.set({ PER: 'mon:2025-12' }); SCR.paint(); hh = SCREEN.innerHTML; out.v4.before = hh.slice(hh.indexOf('id="sc-attn"'), hh.indexOf('id="sc-tcard"'));
      // the sort: Views, then again (the other way)
      _.set({ PER: '30' }); SCR.paint();
      const order = () => Object.keys(cellsOf(SCREEN.innerHTML, 'sc-ttw').rows);
      out.v4.order_rev = order();
      SCREEN.onclick({ target: { closest: q => q === '[data-sc-v4sort]' ? { dataset: { scV4sort: 'views' } } : null } }); out.v4.order_views = order();
      SCREEN.onclick({ target: { closest: q => q === '[data-sc-v4sort]' ? { dataset: { scV4sort: 'views' } } : null } }); out.v4.order_views_up = order();
      _.set({ PER: '30' }); SCREEN.onclick({ target: { closest: q => q === '[data-sc-v4sort]' ? { dataset: { scV4sort: 'rev' } } : null } });
      // the report: the period's signals, English, no money
      out.v4.rep = _.v4Report(ALLF.apps[ID.a], ID.a, '2026-02-27', '2026-03-28');
      // the drill-down's header: its own signals
      _.set({ OPEN: 0, SEC: 'ov' }); SCR.paint(); out.v4.dds = (/<span class="sc-dds">(.*?)<\/span><button/.exec(SCREEN.innerHTML) || [])[1] || null; _.set({ OPEN: null });
      // All apps: Users of the period, Views, Ads, Revenue (AdMob), the signals' counts
      ctx.APP = ''; SCR.paint(); hh = SCREEN.innerHTML;
      const A4 = (() => { const t = hh.slice(hh.indexOf('id="sc-atw"')); const hd = [...((/<thead><tr>(.*?)<\/tr><\/thead>/.exec(t) || [, ''])[1]).matchAll(/<button[^>]*>([^<]*)/g)].map(m => m[1]); const rows = {};
        for (const m of t.matchAll(/<tr class="sc-clk" data-sc-app="([^"]+)"[^>]*>(.*?)<\/tr>/g)) { const tds = [...m[2].matchAll(/<td[^>]*>(.*?)<\/td>/g)].map(q => q[1].replace(/<[^>]+>/g, '').trim()); rows[m[1]] = Object.fromEntries(hd.map((x2, j) => [x2, tds[j]])); }
        return { hd, rows }; })();
      out.v4.all = A4;
      ctx.APP = 'Hostile App'; SCR.paint(); await tick(8); SCR.paint(); hh = SCREEN.innerHTML; const tw = hh.slice(hh.indexOf('id="sc-ttw"'), hh.indexOf('</table>', hh.indexOf('id="sc-ttw"')));
      out.v4.hostile = tw.includes('&lt;img src=x onerror=alert(1)&gt;') && !tw.includes('<img src=x');
      ctx.APP = 'Alpha App'; _.set({ PER: '30' }); SCR.paint();
    }
    // hub card none: the pointer alone never loads a file
    out.ready = SCR.ready();
  } catch (e) { errors.push(String(e && e.stack || e)); }
  console.log(JSON.stringify({ errors, out }));
})();
