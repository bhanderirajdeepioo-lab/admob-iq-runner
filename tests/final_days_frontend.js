// GA4_FINAL_DAYS — the page side at any final age (owner, 17 Nov 2026: "data jese jese aata jaye ese ese bharte jao · max
// to max 7 din me to aa hi jaata he"): every section reads its own file's edge, run for real — the modules of
// frontend/index.html cut out by their markers, each in its own node vm with stub page helpers — on SYNTHETIC files (no
// real names, ids or numbers) whose edges come from tests/test_final_days_frontend.py (the producing builds' own lags at
// GA4_FINAL_DAYS = F):
//   * 🆕 First open (firstopen_build: the app's "td" + "final_till"): today / yesterday from td, the 7 / 30 days ending
//     today − 2 as before the knob, the days after final till "not final" (All apps note, the mini note, the legend, the
//     board's ⏳ line, every day), the country view's Today / Yesterday;
//   * 📈 eCPM first session (nvr_build: "td" + "final_till" + "rw"): the periods, the ⏳ line's count, the measured days of a
//     picked country's ad units (older than today − rw);
//   * 🖼️ Screens (screens_build: "td" + "ft"): the 7 / 30 / 60 / 90 days ending td − 2 (its pwin's), "not final" on them,
//     the All apps and How it works lines, the reasons on a not-final day before Yesterday;
//   * ⚖️ Breakeven (be_build: the pointer's "pv" / "lag"): the ⏳ day, its words, a ROAS day's "N din me asli", the Organic
//     not-final word;
//   * 💰 Revenue by source (source_build: "final_till", the 🌍 file's own): the not-final mark on days, months, the period,
//     and the GA4 vs AdMob check on whole final months only.
// The edges JSON (argv 3): {"fo", "nvr", "rw", "scr", "pv", "lag", "src", "srcc"} — a missing / null one = a file written
// before the knob (no such field; its old fixed lag: the page's fallback). Prints ONE JSON report.
// usage: node final_days_frontend.js <index.html> '<edges JSON>'
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const html = fs.readFileSync(process.argv[2], 'utf8');
const E = JSON.parse(process.argv[3] || '{}') || {};
const out = {}, errors = [];
const cut = (a, b) => { const i = html.indexOf(a), j = html.indexOf(b, i); if (i < 0 || j < 0) throw new Error('not found: ' + a); return html.slice(i, j); };
const MONSRC = cut('// ---- the month mover', "// ---- a daily chart's period");
// (a test build has no today_date: the reference year is pinned so no test depends on the date it runs)
const YRSRC = cut('// ---- dates with their year ----', '// ---- end: dates with their year ----') + "\nrefYear=function(){ return '2026'; };\n";
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmtD = s => { const p = String(s).split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1]; };
const fmtMon = k => MON[+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4);
const DAY = 864e5, t0 = s => Date.parse(s + 'T00:00:00Z'), iso = t => new Date(t).toISOString().slice(0, 10), addD = (s, k) => iso(t0(s) + k * DAY);
const nDays = (a, b) => Math.round((t0(b) - t0(a)) / DAY) + 1;
const tick = () => new Promise(r => setImmediate(r));
const strip = h => String(h).replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, ' ').trim();
const TD = '2026-03-30', D0 = '2026-01-01';                    // the property's today; every file's first day
const BASE = { console, Math, JSON, Object, Array, String, Number, Set, Map, WeakMap, Promise, isFinite, encodeURIComponent, Error, Date, parseFloat };
function el(screen) {
  const e = { _html: '', dataset: screen ? { screen } : {}, style: { setProperty() {} }, isConnected: true, offsetHeight: 900, children: [],
    get innerHTML() { return e._html; }, set innerHTML(v) { e._html = String(v); },
    addEventListener(t, f) { e['on' + t] = f; }, querySelectorAll: () => [], querySelector: () => null, getBoundingClientRect: () => ({ top: 100, bottom: 120, height: 20 }) };
  return e;
}

// ── 🆕 First open ──
async function firstOpen() {
  const R = {}, n = nDays(D0, TD), ft = addD(TD, -(E.fo == null ? 2 : E.fo));
  const rows = Array.from({ length: n }, (_, i) => [addD(D0, i), 120 + i, 100, 70, 101, 71, null, null, null, null]);
  const A = { key: 'ka', app: 'Alpha', app_id: 'id-a', steps: { splash: 'S', home: 'H' }, steps_changed: [], first_day: D0, final_till: ft, days: rows,
    cc: { file: 'firstopen_cc_0123456789ab.json.gz', v: 'c1', from: D0, n: 1, days: n } };
  if (E.fo != null) A.td = TD;
  const X = { key: 'ka', app: 'Alpha', status: 'Normal', why: '', s2h: 0.7, usual: 0.7, change: 0, s2h_any: 0.7, opened: 0.83, opened_usual: 0.83,
    fo_day: 120, fo_day_usual: 120, steps: {}, final_days: 80, sample: null };
  const FILE = { v: 1, apps: [A], summary: [X] };
  // the country file: first opens of XA = 1000 + its day's index (Today / Yesterday told apart by their own numbers)
  const CC = { v: 1, key: 'ka', app_id: 'id-a', final_till: ft, first_day: D0, last_day: TD, missing: 0,
    days: rows.map((r, i) => [r[0], 1020 + i, 120, 84, null, { XA: [1000 + i, 100, 70], XB: [20, 20, 14] }]),
    summary: [{ cc: 'XA', status: 'Normal', why: '', s2h: 0.7, usual: 0.7, change: 0, opened: 0.8, opened_usual: 0.8, fo_day: 100, fo_day_usual: 100,
      final_days: 80, sample: null, share: 0.8 }] };
  const SCREEN = el('firstopen');
  const ctx = Object.assign({}, BASE, {
    DATA: { firstopen: { file: 'firstopen.json.gz', v: 'v1', apps: {} }, apps_catalog: [{ app_id: 'id-a', app_name: 'Alpha' }] }, APP: '',
    document: { querySelector: s => s === '.screen.on' ? { dataset: { screen: 'firstopen' } } : (s === '.screen[data-screen=firstopen]' ? SCREEN : null), getElementById: () => null },
    window: { scrollBy() {}, innerHeight: 800, scrollY: 0 },
    screenDiv: () => SCREEN, fmtD, fmtMon, setApp: () => {}, hubStChip: k => `<span class="hub-st st-${k}">${k}</span>`,
    appIconId: (id, name) => `<span class="aicon" data-iid="${id}"></span>`, uniVis: () => true, appIdOf: nm => nm === 'Alpha' ? 'id-a' : '',
    WD: { sti: { bigda: 'Worse', dhyan: 'Watch', behtar: 'Better', normal: 'Normal', jaldi: 'Too early', lagu: 'N/A' } },
    valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name ' + cc,
    fetchGzJson: u => Promise.resolve(JSON.parse(JSON.stringify(String(u).startsWith('firstopen.json.gz') ? FILE : CC))) });
  vm.createContext(ctx);
  vm.runInContext(MONSRC + YRSRC + cut('const FO=(()=>{', 'function renderFirstOpen(){') + '\nthis.FO=FO;', ctx);
  const FO = ctx.FO, _ = FO._;
  FO.render(); FO.paint(); await tick(); await tick(); FO.paint();
  R.all_note = strip((SCREEN.innerHTML.match(/<p class="fo-note">(Final till[^<]*)/) || [])[1] || '');
  ctx.APP = 'Alpha'; FO.paint(); await tick(); await tick(); FO.paint();
  const a = _.appOf('Alpha'), d = _.ccData(a), h = _.appHtml(a, X);
  R.mini_note = strip((h.match(/<\/table><\/div><p class="fo-note">(.*?) Screens counted/) || [])[1] || '');
  R.legend = (h.match(/<span class="c">([^<]*)<\/span>/) || [])[1];
  R.per = {}; for (const k of ['today', 'yday', '7', '30', '90', 'tm', 'all']) { _.setPer(k); R.per[k] = _.perRange(a, null); }
  _.setPer('7'); R.board7 = strip((_.ccBoard(a, d).match(/<p class="fo-note fo-plim"[^>]*>(.*?)<\/p>/) || [])[1] || '');
  _.setPer('today'); R.board_today = strip((_.ccBoard(a, d).match(/<p class="fo-note fo-plim"[^>]*>(.*?)<\/p>/) || [])[1] || '');
  _.setPer('7');
  R.nf_days = [...(_.dayTable(a).matchAll(/<td class="fo-nm fo-nf">(?:<span[^>]*>[^<]*<\/span>)?(\d+ [A-Z][a-z]{2} \d{4}) · not final<\/td>/g))].map(m => m[1]);
  // the country view (XA picked): Today / Yesterday are the property's today and the day before, from its own rows
  _.pick('XA'); const c = SCREEN.innerHTML;
  const mini = c.slice(c.indexOf('<table class="fo-t fo-mini">'), c.indexOf('</table>', c.indexOf('<table class="fo-t fo-mini">')));
  R.cc_today = [...mini.matchAll(/<tr><td>First opens <small class="faint">\/ day<\/small><\/td><td>([^<]*)<\/td><td>([^<]*)<\/td>/g)].map(m => [m[1], m[2]])[0];
  R.cc_note = strip((c.match(/<\/table><\/div><p class="fo-note">(.*?)<\/p>/) || [])[1] || '');
  R.cc_legend = (c.match(/<span class="c">([^<]*)<\/span>/) || [])[1];
  R.html = { app: h, board7: (_.setPer('7'), _.ccBoard(a, d)), cc: c };           // whole renders (the fallback ≡ test)
  return R;
}

// ── 📈 eCPM · first session vs returning ──
async function nvr() {
  const R = {}, n = nDays(D0, TD), ft = addD(TD, -(E.nvr == null ? 2 : E.nvr));
  const F = { v: 1, key: '000000000009', app_id: 'id-x', first_day: D0, last_day: TD, final_till: ft, units: [['unit_open', 'App open']],
    days: Array.from({ length: n }, (_, i) => [addD(D0, i), [2, 1000, 3, 3000, 0, 0], [100, 90, 500, 300], { 0: [2, 1000, 3, 3000] }, { XA: [2, 1000, 3, 3000] }]) };
  if (E.nvr != null) Object.assign(F, { td: TD, rw: E.rw });
  const ROOT = { dataset: { aid: 'id-x' }, _html: '', get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
    querySelector: () => ({ getBoundingClientRect: () => ({ top: 100 }), closest: () => null }) };
  const ctx = Object.assign({}, BASE, { DATA: { nvr: { v: 1, apps: { 'id-x': { file: 'nvr_000000000009.json.gz', v: 'n1', from: D0, last: TD } } } },
    document: { getElementById: id => id === 'nvr-root' ? ROOT : null, addEventListener() {} }, window: { scrollBy() {} },
    fetchGzJson: () => Promise.resolve(JSON.parse(JSON.stringify(F))), cfx: () => 1, csym: () => '$', curView: () => 'USD',
    cm: (v, dp) => '$' + Number(v).toFixed(dp == null ? 2 : dp), valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name ' + cc, fmtD });
  vm.createContext(ctx);
  vm.runInContext(MONSRC + YRSRC + cut('const NVR=(()=>{', '// the Install value page: 📈 ROI first') + '\nthis.NVR=NVR;', ctx);
  const NVR = ctx.NVR, _ = NVR._;
  ROOT.innerHTML = NVR.block('id-x'); await tick(); await tick();
  const d = _.AF['nvr_000000000009.json.gz'];
  R.per = {}; for (const k of ['today', 'yday', '7', '30', '90', 'tm', 'all']) { _.set('PER', k); R.per[k] = _.rng(d); }
  R.note = {}; for (const k of ['7', '30', 'today']) { _.set('PER', k); NVR.repaint(); R.note[k] = strip((ROOT.innerHTML.match(/<p class="roi-note nvr-lim">⏳ ([^<]*)<\/p>/) || [])[1] || ''); }
  // a picked country's ad units: the days measured against the country's whole total = read by both stores and older
  // than every day either still re-reads (30 days: every day read)
  _.set('PER', '30'); const [lo, hi] = _.rng(d), j = { d0: D0, c: { XA: Array.from({ length: n }, (_, i) => [i, 0, 0, 2, 1000]) }, units: [['unit_open', 'App open']] };
  R.meas30 = _.ucView(d, j, 'XA', lo, hi, [[0, n - 1]]).nMeas;
  R.html = { '30': (NVR.repaint(), ROOT.innerHTML) };
  return R;
}

// ── 🖼️ Screens ──
async function screens() {
  const R = {}, n = nDays(D0, TD), ft = addD(TD, -(E.scr == null ? 2 : E.scr));
  // one app, one full-screen trigger (its ads every day, the app's daily users on every final day): every file of Screens
  // carries "td" — before the knob its ft was td − 2
  const x = { key: 'a00000000001', ft, td: TD, d0: D0, items: [['Back press', 'fs', 'interstitial']], vis: Array(n).fill(1000), V: Array(n).fill([null]),
    A: Array(n).fill([40]), ta: Array(n).fill([0, 40, 0]), st: {}, bf: {}, status: {}, app: ['Normal', '', 0, 0], dq: [], ftu: ft,
    au: Array.from({ length: n }, (_, k) => addD(D0, k) <= ft ? 400 : null), dk: '0'.repeat(n) };
  const SCREEN = el('scr'), FILES = { 'scr_all.json.gz': { v: 4, apps: { 'ca-app-pub-0000000000000000~21': x } } };
  const ctx = Object.assign({}, BASE, { setTimeout: f => { f(); return 0; }, clearTimeout: () => {},
    DATA: { scr: { v: 4, file: 'scr_all.json.gz', fv: 'f1', apps: { 'ca-app-pub-0000000000000000~21': { key: x.key, v: 'va', vl: 'la', from: D0, ft } } },
      apps_catalog: [{ app_id: 'ca-app-pub-0000000000000000~21', app_name: 'Alpha App' }] }, APP: '',
    document: { querySelector: s => s === '.screen.on' ? { dataset: { screen: 'scr' } } : (s === '.screen[data-screen=scr]' ? SCREEN : null), getElementById: () => null, execCommand: () => true },
    window: { scrollBy() {}, innerWidth: 1280, innerHeight: 800, scrollY: 0, addEventListener() {}, removeEventListener() {} }, navigator: {},
    localStorage: { getItem: () => null, setItem() {} }, SP: { quietly: f => f() }, HB: { st: [] }, hbPush() {}, hbDrop() {},
    screenDiv: () => SCREEN, fmtD, fmtMon, setApp: nm => { ctx.APP = nm; }, hubStChip: k => `<span class="hub-st st-${k}">${k}</span>`,
    appIconId: id => `<span class="aicon" data-iid="${id}"></span>`, uniVis: () => true, appIdOf: nm => nm === 'Alpha App' ? 'ca-app-pub-0000000000000000~21' : '',
    valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name ' + cc, money: v => '$' + Math.round(v), cm: (v, dp) => '$' + Number(v).toFixed(dp == null ? 2 : dp), cfx: () => 1,
    fetchGzJson: u => { const f = String(u).split('?')[0]; return f in FILES ? Promise.resolve(JSON.parse(JSON.stringify(FILES[f]))) : Promise.reject(new Error('net')); } });
  vm.createContext(ctx);
  vm.runInContext(MONSRC + cut('const SCR=(()=>{', 'function renderScreens(){') + '\nthis.SCR=SCR;', ctx);
  const SCR = ctx.SCR, _ = SCR._;
  R.per = {}; for (const k of ['today', 'yday', '7', '30', '60', '90', 'tm', 'all']) R.per[k] = _.rng(x, k, '', '');
  R.line = {}; for (const k of ['7', '30', 'yday']) { _.set({ PER: k }); R.line[k] = _.perLine(x, ...R.per[k]); }
  _.set({ PER: '30' });
  R.how = strip((_.foldsHtml(x, 'nope', ...R.per['30']).match(/GA4 data till <b>[^<]*<\/b>;[^<]*/) || [])[0] || '');
  SCR.render(); SCR.paint(); await tick(); await tick(); SCR.paint();
  R.all_note = strip((SCREEN.innerHTML.match(/<p class="sc-note">(GA4 data till [^<]*)/) || [])[1] || '');
  // a not-final day before Yesterday (the day after ft) and Yesterday: the per-user chart's reason, the Fill / Show rate's
  const y = addD(TD, -1), nf1 = addD(ft, 1);
  R.why = {}; for (const [k, dd] of [['nf1', nf1], ['yday', y]]) { const r = _.userDays(x, null, 0, dd, dd)[0]; R.why[k] = r ? r[3] : null; }
  const f2 = { v: 4, key: x.key, d0: D0, ft, td: TD, screens: [], units: [['u', 'interstitial', ['ca-app-pub-0000000000000000/1']]], trig: [['interstitial', 'Back press', [0]]],
    days: Array.from({ length: n }, () => ({ w: [[0, 40]], st: { w: 'w' } })), adm: { 0: Array.from({ length: n }, () => [100, 90, 80]) }, rows: {}, notes: {} };
  R.adm = {}; for (const [k, dd] of [['nf1', nf1], ['yday', y]]) R.adm[k] = _.abTrig(x, f2, 0, dd, dd).why;
  // the App total's Fill / Show rate (every AdMob unit pooled, nothing of GA4 in it): AdMob's own complete days to the
  // page's latest day (td − 2), never GA4's final day — [AdMob days used, why]
  R.pool = {}; for (const k of ['7', '30', 'yday']) { const p = _.abPool(f2, x, [0], ...R.per[k]); R.pool[k] = [p.nK, p.why]; }
  // the 7 days' signals (one of the build's "roll" periods): judged on as many FINAL days ending ft once the period ends
  // after it (screens_build.sig_win) — the days judged (null: the period's own), its final days, the note; This month
  // (not a "roll" period) on its own days
  const [l7, h7] = R.per['7'], pw7 = [_.pk(x, l7, h7), l7 < D0 ? D0 : l7, h7, 'roll'], [lm, hm] = R.per.tm;
  const R7 = _.v4Rows(x, Object.assign({}, f2, { pw: [pw7], sig: {} }), l7, h7);
  R.sig7 = { sw: R7.sw, fin: R7.fin, note: _.sigNote(R7), tm: _.sigWin(x, [_.pk(x, lm, hm), lm, hm, 'day'], lm, hm) };
  // the App's "Ads / 100 views · vs own past" score: on the period's FINAL days only — GA4 still adding ads to every day
  // after ft (a quarter of them so far) never moves it; [full-screen score, muted]
  const x2 = Object.assign({}, x, { ta: x.ta.map((t, k) => addD(D0, k) > ft ? [0, 10, 0] : t) });
  R.score = {}; for (const k of ['7', '30', 'tm', 'today']) { const s = _.appScore(x2, ...R.per[k], false); R.score[k] = [s.fs, s.muted]; }
  return R;
}

// ── ⚖️ Breakeven (the CPI vs eCPM tab; tests/cpx_fixture.js be(): the build's pointer and files) ──
async function breakeven() {
  const R = {}, FXM = require(path.join(__dirname, 'cpx_fixture.js')), FX = FXM.be(FXM.build());
  if (E.pv != null) FX.DATA.be.pv = E.pv;
  if (E.lag != null) FX.DATA.be.lag = E.lag;
  const SCREEN = el('cpx');
  const ctx = Object.assign({}, BASE, { setTimeout: f => { f(); return 0; }, clearTimeout: () => {}, DATA: FX.DATA, APP: '',
    document: { querySelector: s => s === '.screen.on' ? { dataset: { screen: 'cpx' } } : (s === '.screen[data-screen=cpx]' ? SCREEN : null), getElementById: () => null },
    window: { scrollBy() {}, innerWidth: 1280, innerHeight: 800, scrollY: 0, addEventListener() {}, removeEventListener() {} },
    localStorage: { getItem: () => null, setItem() {} }, SP: { quietly: f => f() }, HB: { st: [] }, hbPush() {}, hbDrop() {},
    screenDiv: () => SCREEN, fmtD, appIconId: id => `<span class="aicon" data-iid="${id}"></span>`, appVisibleByName: () => true,
    curView: () => 'USD', baseCur: () => 'USD', roasFxDated: () => true, roasDaily: e => (e && (e.daily_dated || e.daily)) || {},
    valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name ' + cc, show() {},
    fetchGzJson: u => { const f = String(u).split('?')[0]; return f in FX.FILES ? Promise.resolve(JSON.parse(JSON.stringify(FX.FILES[f]))) : Promise.reject(new Error('net')); } });
  ctx.window.show = ctx.show;
  vm.createContext(ctx);
  vm.runInContext(MONSRC + cut('const CPX=(()=>{', 'function renderCpx(){') + '\nthis.CPX=CPX;', ctx);
  const _ = ctx.CPX._, G = [0, 1, 2, 3, 6, 13, 30, 60, 90, 120, 180, 270, 360], pv = E.pv == null ? 4 : E.pv, lag = E.lag == null ? 3 : E.lag;
  const row = (age, now) => { const h = _.beRow({ d: '2026-02-10', age, sp: 100, inst: 10, real: [], app: null, unc: [], cty: [], now: now || ['no', age, 0.5] }, 'Alpha App', G);
    return { wat: [...h.matchAll(/<span class="cpx-wat" title="([^"]*)">⏳<\/span>/g)].map(m => m[1]), titles: [...h.matchAll(/title="([^"]*)"/g)].map(m => m[1]) }; };
  // the day turning final (age pv) and the one before it (pv − 1)
  R.young = row(pv - 1); R.old = row(pv);
  // the 30-day ROAS of a day lived past 30 days: not final while the 30th day is at most lag days back, then not whole
  R.at_lag = row(30 + lag, ['no', 95, 0.7]).titles.filter(t => t.startsWith('30 din ka data'));
  R.past_lag = row(31 + lag, ['no', 95, 0.7]).titles.filter(t => t.startsWith('30 din ka data'));
  R.det = strip((_.beDet({ d: '2026-02-10', age: pv - 1, cty: [], unc: [], now: ['no', 1, 0.1] }, 1, true).match(/⏳ <b>Abhi final nahi<\/b> — ([^:]*):/) || [])[1] || '');
  // the table's header and footnote (the app's file as loaded)
  const id = FX.IDS.a, a = FX.DATA.be.apps[id];
  _.FILES[a.file] = { raw: JSON.parse(JSON.stringify(FX.FILES[a.file])), v: a.v };
  const h = _.beHtml({ id, name: 'Alpha App' });
  R.so_far = (h.match(/<th title="([^"]*)">So far<\/th>/) || [])[1];
  R.foot = (h.match(/⏳ = abhi final nahi \([^)]*\)/) || [])[0];
  return R;
}

// ── 💰 Revenue by source ──
async function source() {
  const R = {}, n = nDays(D0, TD), ft = E.src == null ? null : addD(TD, -E.src);
  const rev = Array.from({ length: n }, () => [10, 5, 4, 1]);
  const A = { app_id: 'ca-app-pub-0000000000000000~1', key: '000000000001', app: 'Alpha', tz: 'UTC', today: TD, d0: D0, rev, ses: rev.map(() => [100, 50, 40, 10]),
    mk: {}, bf: true, ch: ['Cross-network'], file: 'source_000000000001.json.gz',
    cc: { file: 'source_cc_000000000001.json.gz', v: 'c1', days: 'source_ccd_000000000001.json.gz', dv: 'd1', bf: true } };
  if (ft) A.final_till = ft;
  // the GA4 vs AdMob check early in a month (3 Apr): the month before is whole and read, its last days final or not
  const TA = '2026-04-03', nA = nDays(D0, TA), ftA = E.src == null ? null : addD(TA, -E.src);
  const C = { app_id: 'ca-app-pub-0000000000000000~3', key: '000000000003', app: 'Gamma', tz: 'UTC', today: TA, d0: D0,
    rev: Array.from({ length: nA }, () => [2, 1, 1, 0]), ses: Array.from({ length: nA }, () => [1, 1, 1, 0]), mk: {}, bf: true, ch: ['Cross-network'],
    file: 'source_000000000003.json.gz', adm: [['2026-01', 62], ['2026-02', 56], ['2026-03', 62]] };
  if (ftA) C.final_till = ftA;
  const ALLF = { v: 1, at: TD + 'T00:00:00Z', groups: [['paid', 'Paid', ['Cross-network']], ['notif', 'Notification', ['Mobile Push Notifications']],
    ['org', 'Organic', ['Direct']], ['oth', 'Other', ['(other)']]], apps: [A, C] };
  const CCP = { v: 1, key: A.key, d0: D0, today: TD, P: { '30': { lo: addD(TD, -30), hi: addD(TD, -1), miss: 0, c: { XA: [30, 15, 7.5, 0, 570] } } } };
  if (E.srcc != null) CCP.final_till = addD(TD, -E.srcc);
  const ROOT = { dataset: { aid: '' }, _html: '', get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); }, querySelector: () => null };
  const XROOT = { dataset: { kind: 'cty', aid: A.app_id }, _html: '', get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); }, querySelector: () => null };
  const ctx = Object.assign({}, BASE, {
    DATA: { source: { file: 'source.json.gz', v: 'abc', apps: { [A.app_id]: { file: A.file, v: 'a1' }, [C.app_id]: { file: C.file, v: 'c1' } } },
      apps_catalog: [{ app_id: A.app_id, app_name: 'Alpha App' }, { app_id: C.app_id, app_name: 'Gamma App' }] },
    document: { getElementById: id => id === 'src-root' ? ROOT : id === 'srcx-root' ? XROOT : null, addEventListener() {} }, window: { scrollBy() {} },
    valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name-' + cc, cfx: () => 1, csym: () => '$', curView: () => 'USD', appIcon: () => '', setApp() {}, fmtD, fmtMon,
    fetchGzJson: u => Promise.resolve(JSON.parse(JSON.stringify(u.startsWith('source.json.gz') ? ALLF : u.startsWith('source_cc_') ? CCP
      : { v: 1, key: A.key, app_id: A.app_id, d0: D0, ch: A.ch, days: [] }))) });
  vm.createContext(ctx);
  vm.runInContext(MONSRC + cut('const SRC=(()=>{', '// the Install value page: 📈 ROI first') + '\nthis.SRC=SRC;', ctx);
  const SRC = ctx.SRC, _ = SRC._;
  _.set('ALL', ALLF);
  const note = h => strip((h.match(/<p class="roi-note">⏳ ([^<]*) abhi final nahi — GA4 in dino me baad me bhi jodta hai, inke amounts abhi badal sakte hain\.<\/p>/) || [])[1] || '');
  R.app = {}; R.all = {};
  for (const k of ['7', '30', 'today', 'lm']) { _.set('PER', k); R.app[k] = note(_.appView(A)); R.all[k] = note(_.allView()); }
  _.set('PER', '30'); const h = _.appView(A);
  R.nf_rows = [...h.matchAll(/<tr><td class="roi-nm">([^<]*(?:<small>so far<\/small>)?) <small>· not final<\/small>/g)].map(m => strip(m[1]));
  R.nf_month = [...h.matchAll(/<tr><td class="roi-nm">([A-Z][a-z]{2} \d{4})(?: <small>so far<\/small>)? <small>· (\d+) din abhi final nahi<\/small>/g)].map(m => [m[1], +m[2]]);
  const ck = _.admChk(C); R.adm = ck ? [ck.from, ck.to, ck.n] : null;
  R.x = note(SRC.xCty(A.app_id)); await tick(); await tick(); R.x = note(XROOT.innerHTML);
  return R;
}

(async () => {
  for (const [k, f] of [['fo', firstOpen], ['nvr', nvr], ['scr', screens], ['be', breakeven], ['src', source]]) {
    try { out[k] = await f(); } catch (e) { errors.push(k + ': ' + (e && e.stack || e)); } }
  console.log(JSON.stringify({ errors, out }));
})();
