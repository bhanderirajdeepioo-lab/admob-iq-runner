// 🆕 First open tab — the page side, run for real: the FO module of frontend/index.html (cut out by its markers) in a node
// vm with stub page helpers, on SYNTHETIC data made up here (no real names, ids or numbers):
//   * the pointer check, the lazy file (its format check, a failed load + Try again);
//   * All apps: the status chips (counts), the table (sorted Worse first, a column sort, the chip filter, hidden apps
//     left out), the app names the App picker uses;
//   * one app: Today / Yesterday / 7 days / usual, the steps, every month (sums), every day (newest first, not final
//     marked), GA4 sampling marked "≈";
//   * the hub card: status word + key line from the pointer (no file load), by app id first;
//   * the points label (no "−0 pts");
//   * BY COUNTRY (a second page context, its own synthetic files): the Country control (All + the top 6 + a <select> of
//     every country, in the file's order), the country file loaded once and only for the open app (the rest of the view
//     at once; a failed load = Try again in the country area only), the board (sorted, status filter, the GA4-unnamed row
//     last), a pick from a chip / the board / the select redraws the mini table, months and every day from that country's
//     rows, the pick kept across apps (+ the "no such country" message), the page height and the board's scroll kept on a
//     pick (no jump), and the All countries view = today's view + the two country blocks, nothing else;
//   * a country file with a HOLE and a status window that is not whole: the date range first – last, ONE warning on the
//     board and in the country view; EVERY day from the app's day 1 in Every day (a run not read yet = one row, a day
//     GA4's funnel no longer has = its own row with the report's first opens, a day GA4 named no country = its own row;
//     the oldest LAST), Every month from day 1 too, the chart's rows on the same calendar (no point there, the reason on
//     hover); tails before the country store's first day: mixed, and not read at all;
//   * hold() — the reader's place when the country file arrives late — on a small layout model at 375 and 1280 px: the card
//     being read stays (Every month just under the top bar, or mid-screen), nothing scrolls at the top of the page, the
//     chart stays when the board's slot is in the lower half;
//   * the SAME Country control inside the Every month / Every day cards (owner, 20 Oct): loading / failed / filled like the
//     top one, ONE picked country for all three, the card titles "Every day · <flag> <name>" + "✕ All countries", a
//     country's Every day columns + one line why the others are missing (once on the WHOLE screen: not again in the Steps
//     card or the board; the country data's dates once too), nothing new for an app without a country file; an app opened
//     with a country picked whose country file loads / fails: All countries at once + one line for the pick, the three
//     controls with loading / Try again (never a crumb alone); pick() from an in-card control on a layout model built from
//     the page's own html at 375 and 1280 px: that control's top moves ≤ 1 px although everything above it is redrawn.
// Prints ONE JSON report; tests/test_firstopen_frontend.py asserts on it.   usage: node firstopen_frontend.js <index.html>
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('const FO=(()=>{'), b = html.indexOf('function renderFirstOpen(){');
if (a < 0 || b < 0) { console.log(JSON.stringify({ errors: ['FO module not found'] })); process.exit(0); }
const src = html.slice(a, b) + '\nthis.FO=FO;';
const out = {}, errors = [];
// ── a tiny element: innerHTML + the attributes the module reads ──
function el(screen) {
  const e = { _html: '', dataset: screen ? { screen } : {}, style: {}, isConnected: true, offsetHeight: 900,
    get innerHTML() { return e._html; }, set innerHTML(v) { e._html = String(v); },
    addEventListener(t, f) { e['on' + t] = f; }, querySelectorAll: () => [], querySelector: () => null };
  return e;
}
const SCREEN = el('firstopen');
const TB = el();
let ON = 'firstopen', LOADS = 0, FAIL = false, APPSET = [];
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error,
  DATA: null, APP: '',
  document: {
    querySelector: s => s === '.screen.on' ? { dataset: { screen: ON } } : (s === '.screen[data-screen=firstopen]' ? SCREEN : null),
    getElementById: id => id === 'fo-tb' ? TB : null,
  },
  screenDiv: () => SCREEN,
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+p[1] - 1]; },
  fmtMon: k => ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4),
  setApp: n => { APPSET.push(n); },
  hubStChip: k => `<span class="hub-st st-${k}">${k}</span>`,
  appIconId: (id, name, size) => `<span class="aicon" data-iid="${id}" data-ian="${name}" data-sz="${size}"></span>`,
  WD: { sti: { bigda: '🔴 Worse', dhyan: '🟡 Watch', behtar: '🟢 Better', normal: '⚪ Normal', jaldi: '⏳ Too early', lagu: '— N/A' } },
  uniVis: id => id !== 'id-hidden',
  appIdOf: name => ({ 'Alpha Pick': 'id-a', 'Beta Pick': 'id-b' })[name] || '',
  fetchGzJson: () => { LOADS++; return FAIL ? Promise.reject(new Error('net')) : Promise.resolve(FILE); },
};
vm.createContext(ctx);
// ── synthetic file: 3 visible apps + 1 hidden ──
const day = i => { const d = new Date(Date.UTC(2026, 7, 1 + i)); return d.toISOString().slice(0, 10); };
const rows = (n, s2h, smp) => Array.from({ length: n }, (_, i) => [day(i), 120, 100, Math.round(100 * s2h), 101, Math.round(100 * s2h) + 1, 50, null, null, smp]);
const FILE = { v: 1,
  apps: [
    { key: 'ka', app: 'Alpha File', app_id: 'id-a', steps: { splash: 'S', home: 'H', language: 'L' }, steps_changed: [], first_day: day(0), final_till: day(57), days: rows(60, 0.5, null) },
    { key: 'kb', app: 'Beta File', app_id: 'id-b', steps: { splash: 'S', home: 'H' }, steps_changed: [{ at: day(30), from: {} }], first_day: day(0), final_till: day(57), days: rows(60, 0.9, 0.02) },
    { key: 'kc', app: 'Gamma', app_id: 'id-c', steps: { splash: 'S', home: 'H' }, steps_changed: [], first_day: day(0), final_till: day(57), days: rows(60, 0.7, null) },
    { key: 'kh', app: 'Hidden', app_id: 'id-hidden', steps: { splash: 'S', home: 'H' }, steps_changed: [], first_day: day(0), final_till: day(57), days: rows(60, 0.1, null) },
  ],
  summary: [
    { key: 'kc', app: 'Gamma', status: 'Normal', why: '', s2h: 0.7, usual: 0.7, change: 0.004, s2h_any: 0.7, opened: 0.83, opened_usual: 0.83, fo_day: 120, fo_day_usual: 120, steps: {}, final_days: 58, sample: null },
    { key: 'kb', app: 'Beta File', status: 'Better', why: '', s2h: 0.9, usual: 0.8, change: 0.1, s2h_any: 0.9, opened: 0.83, opened_usual: 0.83, fo_day: 900, fo_day_usual: 800, steps: {}, final_days: 58, sample: 0.02 },
    { key: 'ka', app: 'Alpha File', status: 'Worse', why: '', s2h: 0.5, usual: 0.6, change: -0.1, s2h_any: 0.5, opened: 0.83, opened_usual: 0.83, fo_day: 120, fo_day_usual: 130, steps: { language: [0.5, 0.55] }, final_days: 58, sample: null },
    { key: 'kh', app: 'Hidden', status: 'Worse', why: '', s2h: 0.1, usual: 0.6, change: -0.5, s2h_any: 0.1, opened: 0.83, opened_usual: 0.83, fo_day: 5000, fo_day_usual: 5000, steps: {}, final_days: 58, sample: null },
  ] };
const tick = () => new Promise(r => setTimeout(r, 0));
(async () => {
  try {
    vm.runInContext(src, ctx);
    const FO = ctx.FO;
    // the pointer
    ctx.DATA = {};
    out.no_ptr = FO.ptr() === null;
    ctx.DATA = { firstopen: { file: '../x.json.gz', v: '1' } };
    out.bad_file = FO.ptr() === null;
    ctx.DATA = { firstopen: { file: 'firstopen.json.gz', v: 'v1', apps: { 'Alpha File': { status: 'Worse', s2h: 0.5, usual: 0.6, change: -0.1, fo_day: 120, id: 'id-a' },
      'Gamma': { status: 'Normal', s2h: 0.7, usual: 0.7, change: -0.004, fo_day: 120, id: 'id-c' } } },
      apps_catalog: [{ app_id: 'id-a', app_name: 'Alpha Pick' }, { app_id: 'id-b', app_name: 'Beta Pick' }] };
    out.ptr = !!FO.ptr();
    // the hub card: by id (the picker's name differs from the file's), the zero change, an app with no row
    out.card_alpha = FO.card('Alpha Pick');
    out.card_gamma = FO.card('Gamma');
    out.card_none = FO.card('Nobody');
    out.loads_before_open = LOADS;
    // a failed load, then Try again
    FAIL = true; FO.render(); FO.paint(); await tick(); await tick();
    out.fail_html = SCREEN.innerHTML.includes('data-fo-retry');
    FAIL = false;
    SCREEN.onclick({ target: { closest: s => s === '[data-fo-retry]' ? {} : null } }); await tick(); await tick();
    out.loads = LOADS;
    // All apps
    FO.paint();
    const h = SCREEN.innerHTML;
    out.all_chips = [...h.matchAll(/data-fo-filt="([^"]+)"[^>]*><span>[^<]*<\/span> <b>(\d+)<\/b>/g)].map(m => [m[1], +m[2]]);
    out.all_rows = [...h.matchAll(/<tr class="clk" data-fo-app="([^"]+)"/g)].map(m => m[1]);
    out.all_hidden = h.includes('Hidden');
    out.all_icons = [...h.matchAll(/<td class="fo-nm"><span class="fo-an"><span class="aicon" data-iid="([^"]+)" data-ian="([^"]+)" data-sz="22"><\/span><span>([^<]+)<\/span>/g)].map(m => [m[1], m[2], m[3]]);
    out.all_smp = /fo-smp[^>]*>≈<\/span><b>90%<\/b>/.test(h);
    out.all_zero_pts = h.includes('>0 pts<') && !h.includes('−0 pts');
    // a column sort (Splash → Home, high first) and the chip filter
    SCREEN.onclick({ target: { closest: s => s === '[data-fo-sort]' ? { dataset: { foSort: 's2h' } } : null } });
    out.sort_rows = [...TB.innerHTML.matchAll(/data-fo-app="([^"]+)"/g)].map(m => m[1]);
    SCREEN.onclick({ target: { closest: s => s === '[data-fo-filt]' ? { dataset: { foFilt: 'Worse' } } : null } });
    out.filt_rows = [...TB.innerHTML.matchAll(/data-fo-app="([^"]+)"/g)].map(m => m[1]);
    out.filt_minh = SCREEN.style.minHeight;
    SCREEN.onclick({ target: { closest: s => s === '[data-fo-filt]' ? { dataset: { foFilt: 'Too early' } } : null } });
    out.filt_empty = TB.innerHTML.includes('Is status me koi app nahi');
    SCREEN.onclick({ target: { closest: s => s === '[data-fo-filt]' ? { dataset: { foFilt: 'Too early' } } : null } });
    out.filt_off_rows = (TB.innerHTML.match(/data-fo-app=/g) || []).length;
    // a row tap = the picker's name
    SCREEN.onclick({ target: { closest: s => s === 'tr[data-fo-app]' ? { dataset: { foApp: 'Alpha Pick' } } : null } });
    out.row_tap = APPSET.slice();
    // one app (by the picker's name → id)
    ctx.APP = 'Beta Pick'; FO.paint();
    const p = SCREEN.innerHTML;
    out.app_mini = /<td>First opens <small class="faint">\/ day<\/small><\/td><td>120<\/td><td>120<\/td><td>900<\/td><td>800<\/td>/.test(p);
    out.app_months = [...p.matchAll(/<td class="fo-nm">([A-Z][a-z]{2} 2026) <small>· (\d+)d<\/small><\/td><td>([\d,]+)<\/td>/g)].map(m => [m[1], +m[2], m[3]]);
    out.app_days = (p.match(/<tr><td class="fo-nm[^"]*">(<span class="fo-smp"[^>]*>≈<\/span>)?\d+ [A-Z][a-z]{2} 2026/g) || []).length;
    out.app_first_day_row = /<td class="fo-nm fo-nf"><span class="fo-smp"[^>]*>≈<\/span>29 Sep 2026 · not final<\/td>/.test(p);
    out.app_changed = p.includes('screens badle 31 Aug');
    out.app_smp_note = p.includes('sirf ~2% data padha');
    out.app_lang_col = p.includes('<th>Language</th>');
    ctx.APP = 'Alpha Pick'; FO.paint();
    out.alpha_steps = /<span class="fo-bl">Language<\/span>.*?<b>50%<\/b> <small>usual 55%<\/small>/.test(SCREEN.innerHTML);
    out.alpha_lang_col = SCREEN.innerHTML.includes('<th>Language</th>');
    ctx.APP = 'Nobody'; FO.paint();
    out.app_missing = SCREEN.innerHTML.includes('Is app ka GA4 funnel data nahi');
    // no pointer: the plain note
    ctx.DATA = {}; ctx.APP = ''; FO.paint();
    out.no_ptr_note = SCREEN.innerHTML.includes('First open ka data is build me nahi bana');
  } catch (e) { errors.push(String(e && e.stack || e)); }
  try { await byCountry(); } catch (e) { errors.push(String(e && e.stack || e)); }
  console.log(JSON.stringify({ errors, out }));
})();

// ── by country: a fresh page context; getElementById finds an id only while it is in the current html (as the DOM would),
// and a rebuilt screen gets new elements ──
async function byCountry() {
  const S2 = el('firstopen'), IDS = {};
  let html2 = '';
  Object.defineProperty(S2, 'innerHTML', { get: () => html2, set: v => { html2 = String(v); for (const k of Object.keys(IDS)) delete IDS[k]; } });
  const live = () => html2 + Object.values(IDS).map(e => e._html).join('');
  const LD = {}, FAILCC = new Set();
  const CODES = ['XA', 'XB', 'XC', 'XD', 'XE', 'XF', 'XG', 'XH', 'XI'];
  const VAL = { XA: [500, 400, 200], XB: [300, 250, 200], XC: [200, 150, 100], XD: [100, 80, 40], XE: [50, 40, 20], XF: [20, 16, 8], XG: [10, 8, 4], XH: [5, 4, 2], XI: [1, 1, 0] };
  const ST = { XA: 'Worse', XB: 'Better', XC: 'Normal', XD: 'Watch' };
  const S2H = { XA: 0.5, XB: 0.8, XC: 0.66, XD: 0.5, XE: 0.5, XF: 0.5, XG: 0.5, XH: 0.5, XI: 0 };
  const FOD = { XA: 500, XB: 300, XC: 200, XD: 100, XE: 50, XF: 20, XG: 10, XH: 5, XI: 0.4 };
  const ccFile = (key, codes, more) => ({ v: 1, key, app_id: 'id-' + key, final_till: day(57), first_day: day(0), ...(more || {}),
    days: Array.from({ length: 60 }, (_, i) => { const c = {}; for (const k of codes) if (k !== 'XI' || i % 3 === 0) c[k] = VAL[k].slice();
      const t = [0, 1, 2].map(j => Object.values(c).reduce((s, v) => s + v[j], 0) + [9, 8, 7][j]); return [day(i), t[0], t[1], t[2], i === 40 ? 0.25 : null, c]; }),
    summary: codes.map(k => ({ cc: k, status: ST[k] || 'N/A', why: ST[k] ? '' : 'low data', s2h: S2H[k], usual: k === 'XA' ? 0.6 : S2H[k], change: k === 'XA' ? -0.1 : 0,
      opened: 0.8, opened_usual: 0.8, fo_day: FOD[k], fo_day_usual: FOD[k] + 10, final_days: 58, sample: k === 'XB' ? 0.25 : null, share: FOD[k] / 1300 })),
    unnamed: { summary: { fo_day: 9, opened: 0.89, s2h: 0.875, share: 9 / 1300 } } });
  const CCF = { 'firstopen_cc_0123456789ab.json.gz': ccFile('kb', CODES, { last_day: day(59), missing: 0 }),
    'firstopen_cc_abcdef012345.json.gz': ccFile('kc', ['XA', 'XB'], { last_day: day(59), missing: 0 }),
    'firstopen_cc_dddddddddddd.json.gz': ccFile('kd', ['XA', 'XB', 'XC']) };
  // Epsilon: its country store has a hole (days 20 … 39 not read yet), so the status window lacks 18 days → Too early
  const GAP = ccFile('ke', ['XA', 'XB'], { last_day: day(59), missing: 18 });
  GAP.days = GAP.days.filter((d, i) => i < 20 || i >= 40);
  GAP.summary.forEach(x => { x.status = 'Too early'; x.why = 'country data incomplete: 18 din missing'; });
  // GA4's funnel no longer has 5 days of the hole and the 3 days before the country store's first day (the app's day 1 is
  // 3 earlier): its report's first opens by country kept for them (31 Jul: XB only → XA 0; 23 Aug: an older record, no counts)
  GAP.gone = [day(-3), day(-2), day(-1), day(20), day(21), day(22), day(23), day(24)];
  GAP.gone_fo = { [day(-3)]: { XA: 11, XB: 3 }, [day(-2)]: { XA: 12 }, [day(-1)]: { XB: 2 }, [day(20)]: { XA: 21 }, [day(21)]: { XA: 22 },
    [day(23)]: { XA: 24 }, [day(24)]: { XA: 25 } };
  GAP.nobody = [];
  CCF['firstopen_cc_eeeeeeeeeeee.json.gz'] = GAP;
  // Eta: the app's day 1 six days before its country store's: 31 Jul not read, 30 Jul GA4 named no country, 29 Jul not
  // read, 28 Jul gone (first opens 7), 26 – 27 Jul not read; Theta: two days before, neither read yet
  CCF['firstopen_cc_cccccccccccc.json.gz'] = ccFile('kg', ['XA', 'XB'], { last_day: day(59), missing: 0, gone: [day(-4)],
    gone_fo: { [day(-4)]: { XA: 7 } }, nobody: [day(-2)] });
  CCF['firstopen_cc_bbbbbbbbbbbb.json.gz'] = ccFile('kt', ['XA', 'XB'], { last_day: day(59), missing: 0 });
  CCF['firstopen_cc_ffffffffffff.json.gz'] = ccFile('kf', ['XA', 'XB', 'XC'], { last_day: day(59), missing: 0 });
  const ptrOf = (f, n) => ({ file: f, v: 'c-' + f.slice(13, 17), from: day(0), n, days: 60 });
  const F2 = JSON.parse(JSON.stringify(FILE));
  F2.apps = F2.apps.filter(a => a.key !== 'kh');
  F2.apps[1].cc = ptrOf('firstopen_cc_0123456789ab.json.gz', 9);
  F2.apps[2].cc = ptrOf('firstopen_cc_abcdef012345.json.gz', 2);
  F2.apps.push({ ...JSON.parse(JSON.stringify(F2.apps[2])), key: 'kd', app: 'Delta', app_id: 'id-d', cc: ptrOf('firstopen_cc_dddddddddddd.json.gz', 3) });
  // the All countries table of an app whose day 1 is k days before the country store's (its rows really start there)
  const from = k => ({ first_day: day(-k), days: rows(60 + k, 0.7, null).map((r, i) => [day(i - k), ...r.slice(1)]) });
  F2.apps.push({ ...JSON.parse(JSON.stringify(F2.apps[2])), key: 'ke', app: 'Epsilon', app_id: 'id-e', cc: ptrOf('firstopen_cc_eeeeeeeeeeee.json.gz', 2), ...from(3) });
  F2.apps.push({ ...JSON.parse(JSON.stringify(F2.apps[2])), key: 'kf', app: 'Zeta', app_id: 'id-f', cc: ptrOf('firstopen_cc_ffffffffffff.json.gz', 3) });
  F2.apps.push({ ...JSON.parse(JSON.stringify(F2.apps[2])), key: 'kg', app: 'Eta', app_id: 'id-g', cc: ptrOf('firstopen_cc_cccccccccccc.json.gz', 2), ...from(6) });
  F2.apps.push({ ...JSON.parse(JSON.stringify(F2.apps[2])), key: 'kt', app: 'Theta', app_id: 'id-t', cc: ptrOf('firstopen_cc_bbbbbbbbbbbb.json.gz', 2), ...from(2) });
  F2.summary = F2.summary.filter(x => x.key !== 'kh').concat([{ ...F2.summary[0], key: 'kd', app: 'Delta' }, { ...F2.summary[0], key: 'ke', app: 'Epsilon' },
    { ...F2.summary[0], key: 'kf', app: 'Zeta' }, { ...F2.summary[0], key: 'kg', app: 'Eta' }, { ...F2.summary[0], key: 'kt', app: 'Theta' }]);
  const c2 = { ...ctx, DATA: { firstopen: { file: 'firstopen.json.gz', v: 'v2', apps: {} }, apps_catalog: [{ app_id: 'id-a', app_name: 'Alpha Pick' }, { app_id: 'id-b', app_name: 'Beta Pick' }] },
    APP: 'Beta Pick',
    document: { querySelector: s => s === '.screen.on' ? { dataset: { screen: 'firstopen' } } : (s === '.screen[data-screen=firstopen]' ? S2 : null),
      getElementById: id => id !== 'fo-chart' && live().includes('id="' + id + '"') ? (IDS[id] || (IDS[id] = el())) : null },
    screenDiv: () => S2, setApp: () => {},
    valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name ' + cc,
    fetchGzJson: u => { const f = String(u).split('?')[0]; LD[f] = (LD[f] || 0) + 1;
      if (FAILCC.has(f)) { FAILCC.delete(f); return Promise.reject(new Error('net')); }
      return Promise.resolve(f === 'firstopen.json.gz' ? F2 : JSON.parse(JSON.stringify(CCF[f]))); } };
  vm.createContext(c2);
  vm.runInContext(src, c2);
  const FO = c2.FO, R = {};
  const click = (sel, ds) => S2.onclick({ target: { closest: s => s === sel ? { dataset: ds } : null } });
  const rowsOf = h => [...h.matchAll(/<tr class="clk[^"]*" data-fo-ccr="([^"]+)"/g)].map(m => m[1]);
  FO.render(); FO.paint(); await tick(); await tick();          // the main file → the app view, then its country file
  R.loading_ctl = /<div class="fo-cc" id="fo-cc"[^>]*><span class="fo-ccl">Country<\/span><span class="fo-ccw">⏳ Country data loading…<\/span><\/div>/.test(html2) || null;
  // the in-card controls (Every month / Every day): the same loading state, the All-countries tables drawn at once
  const LOADING_CTL = '<span class="fo-ccl">Country</span><span class="fo-ccw">⏳ Country data loading…</span>';
  R.in_loading = ['m', 'd'].every(k => html2.includes(`<div class="fo-cc fo-cci" id="fo-cc-${k}" role="group" aria-label="Country">${LOADING_CTL}</div>`))
    && /<h3>Every month<\/h3><span[^>]*>[^<]*<\/span><\/div><div class="fo-cc fo-cci" id="fo-cc-m"[^>]*>.*?<\/div><div class="fo-tw"><table class="fo-t"><thead><tr><th>Month<\/th>/.test(html2)
    && /<h3>Every day<\/h3><span[^>]*>[^<]*<\/span><\/div><div class="fo-cc fo-cci" id="fo-cc-d"[^>]*>.*?<\/div><div class="fo-tw fo-tall"><table class="fo-t"><thead><tr><th>Day<\/th>.*?<th>Incl\. late open<\/th>/.test(html2);
  const loadingHtml = html2;
  await tick(); await tick();
  R.view_at_once = html2.includes('<td>First opens <small class="faint">/ day</small></td>') && html2.includes('<th>Incl. late open</th>');
  R.loads_main = LD['firstopen.json.gz'];
  R.loads_b = LD['firstopen_cc_0123456789ab.json.gz'];
  R.loads_other = (LD['firstopen_cc_abcdef012345.json.gz'] || 0) + (LD['firstopen_cc_dddddddddddd.json.gz'] || 0);
  const ctl = IDS['fo-cc'] ? IDS['fo-cc']._html : '';
  R.chips = [...ctl.matchAll(/<button type="button" class="fo-ccc" data-fo-cc="([^"]*)" aria-pressed="(true|false)"/g)].map(m => [m[1], m[2]]);
  R.chip_xa = ctl.includes('data-fo-cc="XA" aria-pressed="false" title="Name XA"><span class="fo-fl">[XA]</span> XA</button>');
  R.select = [...ctl.matchAll(/<option value="([^"]*)"[^>]*>([^<]*)<\/option>/g)].map(m => [m[1], m[2]]);
  R.select_placeholder = ctl.includes('<option value="" disabled selected>More countries ▾</option>');
  // the file arrived: the in-card controls are the top one (same chips, same select), filled in place
  R.in_arrived = !!ctl && ['fo-cc-m', 'fo-cc-d'].every(id => IDS[id] && IDS[id]._html === ctl);
  const board = IDS['fo-ccbx'] ? IDS['fo-ccbx']._html : '';
  R.board_rows = rowsOf(board);
  R.board_unnamed_last = /data-fo-ccr="XI"[\s\S]*<tr class="fo-un"><td class="fo-nm"><span class="fo-an"><span class="fo-fl">❔<\/span><span>Not named by GA4<\/span><\/span><\/td><td class="fo-stc"><small>no status<\/small><\/td><td>88%<\/td><td>—<\/td><td>—<\/td><td>89%<\/td><td>9<\/td><td>0.7%<\/td><\/tr><\/tbody>/.test(board);
  R.board_chips = [...board.matchAll(/data-fo-ccfilt="([^"]+)"[^>]*><span>[^<]*<\/span> <b>(\d+)<\/b>/g)].map(m => [m[1], +m[2]]);
  R.board_cells_xa = board.includes('<td class="down">−10 pts</td><td>80%</td><td>500</td><td>38%</td></tr>');
  R.board_cells_xi = board.includes('<td>0.4</td><td>&lt;0.1%</td></tr>') && board.includes('<td>5</td><td>0.4%</td></tr>');
  R.board_note = board.includes('Country data <b>1 Aug 2026 – 29 Sep 2026</b> ka hai (GA4 sirf ~2 mahine rakhta hai) aur sirf First open → Splash → Home');
  R.board_no_gap_note = !board.includes('fo-ccgap');
  // the board: a column sort, the status filter (no jump), back
  click('[data-fo-ccsort]', { foCcsort: 's2h' });
  R.sort_s2h = rowsOf(IDS['fo-ccbw']._html);
  R.sort_unnamed_last = /<tr class="fo-un">[\s\S]*<\/tbody>/.test(IDS['fo-ccbw']._html) && !/<tr class="fo-un">[\s\S]*data-fo-ccr=/.test(IDS['fo-ccbw']._html);
  click('[data-fo-ccsort]', { foCcsort: 'fo_day' });
  S2.style.minHeight = '';
  click('[data-fo-ccfilt]', { foCcfilt: 'N/A' });
  R.filt_rows = rowsOf(IDS['fo-ccbw']._html);
  R.filt_no_unnamed = !IDS['fo-ccbw']._html.includes('fo-un');
  R.filt_minh = S2.style.minHeight;
  click('[data-fo-ccfilt]', { foCcfilt: 'Too early' });
  R.filt_empty = IDS['fo-ccbw']._html.includes('Is status me koi country nahi');
  click('[data-fo-ccfilt]', { foCcfilt: 'Too early' });
  R.filt_off = rowsOf(IDS['fo-ccbw']._html).length;
  // the All countries view = today's view + the Country control + the board, nothing else
  FO.paint();
  const a = FO._.appOf('Beta Pick'), x = F2.summary.find(z => z.key === 'kb');
  const withCc = html2, top = FO._.ccTop(a), slot = FO._.ccSlot(a), inM = FO._.ccIn(a, 'm'), inD = FO._.ccIn(a, 'd');
  const cc0 = a.cc; delete a.cc; FO.paint(); const noCc = html2; a.cc = cc0;
  R.all_plus_four = [top, slot, inM, inD].every(x => withCc.includes(x)) && withCc.replace(top, '').replace(slot, '').replace(inM, '').replace(inD, '') === noCc;
  R.nocc_plain = !noCc.includes('fo-cc') && !noCc.includes('By country') && !noCc.includes('fo-ccx');
  // while the country file loads: today's view + the three controls (loading) + the empty board slot, nothing else
  R.loading_plus = loadingHtml.split(LOADING_CTL).length === 4
    && loadingHtml.replace(/<div class="fo-cc(?: fo-cci)?" id="fo-cc(?:-[md])?" role="group" aria-label="Country"><span class="fo-ccl">Country<\/span><span class="fo-ccw">⏳ Country data loading…<\/span><\/div>/g, '').replace('<div id="fo-ccbx"></div>', '') === noCc;
  // All countries: the in-card controls sit right under each card's title (titles as today, no ✕ in the cards), the same
  // control as the top one
  R.in_all = inM.includes('data-fo-cc="" aria-pressed="true"') && inM.replace('fo-cc fo-cci" id="fo-cc-m"', '') === inD.replace('fo-cc fo-cci" id="fo-cc-d"', '')
    && inM.replace('<div class="fo-cc fo-cci" id="fo-cc-m"', '<div class="fo-cc" id="fo-cc"') === top
    && withCc.includes('<h3>Every month</h3><span class="faint" style="font-size:11.5px">mahine ke aage = us mahine ke din</span></div>' + inM + '<div class="fo-tw">')
    && withCc.includes('<h3>Every day</h3><span class="faint" style="font-size:11.5px">sabse naya din upar</span></div>' + inD + '<div class="fo-tw fo-tall">')
    && !withCc.includes('fo-ccx');
  R.top_under_crumb = /<\/div><div class="fo-cc" id="fo-cc"/.test(withCc) && withCc.indexOf('id="fo-cc"') < withCc.indexOf('Today · Yesterday');
  R.board_after_grid = withCc.indexOf('id="fo-ccbx"') > withCc.indexOf('id="fo-chart"') && withCc.indexOf('id="fo-ccbx"') < withCc.indexOf('<h3>Every month</h3>');
  // a chip: the country's view from its own rows (no file load), the page keeps its height
  FO.paint(); S2.style.minHeight = '';
  click('[data-fo-cc]', { foCc: 'XB' });
  let h = html2;
  R.pick_cc = FO._.cc();
  R.pick_minh = S2.style.minHeight;
  R.pick_loads = LD['firstopen_cc_0123456789ab.json.gz'];
  R.pick_crumb = h.includes('<span class="fo-cct">[XB] Name XB</span>') && h.includes('data-fo-ccx="1">✕ All countries</button>') && h.includes('<span class="hub-st st-behtar">behtar</span>');
  R.pick_chip_on = h.includes('data-fo-cc="XB" aria-pressed="true"') && h.includes('data-fo-cc="" aria-pressed="false"');
  R.pick_mini = /<td>First opens <small class="faint">\/ day<\/small><\/td><td>300<\/td><td>300<\/td><td>300<\/td><td>310<\/td><\/tr><tr><td>Opened app<\/td><td>83%<\/td><td>83%<\/td><td>80%<\/td><td>80%<\/td><\/tr><tr><td>Splash → Home<\/td><td>80%<\/td><td>80%<\/td><td><b>80%<\/b><\/td><td>80%<\/td><\/tr><\/tbody>/.test(h);
  R.pick_no_late = !h.includes('Incl. late open') && !h.includes('<th>Language</th>');
  R.pick_steps = (h.match(/class="fo-bl"/g) || []).length === 1 && h.includes('<span class="fo-bl">Home</span>')
    && h.includes('<p class="fo-note">Country ke liye sirf <b>Home</b> ka step — baaki steps kyun nahi, wo neeche <b>Every day</b> card me likha hai.</p>');
  R.pick_note = h.includes('<p class="fo-note">🌍 Country data <b>1 Aug 2026 – 29 Sep 2026</b> ka hai (GA4 sirf ~2 mahine ka data rakhta hai');
  // the in-card controls follow the one pick; the card titles say the country + ✕ All countries (as the ROI card)
  R.pick_in_on = (h.match(/data-fo-cc="XB" aria-pressed="true"/g) || []).length === 3 && (h.match(/data-fo-cc="" aria-pressed="true"/g) || []).length === 0
    && h.includes('id="fo-cc-m"') && h.includes('id="fo-cc-d"');
  const X = '<button type="button" class="fo-back fo-ccx" data-fo-ccx="1">✕ All countries</button>';
  R.pick_titles = h.includes(`<div class="ct"><h3>Every month · [XB] Name XB</h3>${X}<span class="faint" style="font-size:11.5px">mahine ke aage = us mahine ke din</span></div><div class="fo-cc fo-cci" id="fo-cc-m"`)
    && h.includes(`<div class="ct"><h3>Every day · [XB] Name XB</h3>${X}<span class="faint" style="font-size:11.5px">sabse naya din upar</span></div><div class="fo-cc fo-cci" id="fo-cc-d"`);
  // Every day for a country: the columns it can fill, and ONE line (in that card, under its control) saying why the others
  // are not there — the text on screen once
  const dayCard = h.slice(h.indexOf('<h3>Every day · '));
  R.pick_day_cols = /<\/select><\/div><p class="fo-note">🌍 Country view me sirf <b>First open → Splash → Home<\/b> hai — Language \/ Permission \/ Intro aur "incl\. late open" country-wise nahi padhe, isliye wo columns yahan nahi\.<\/p><div class="fo-tw fo-tall"><table class="fo-t"><thead><tr><th>Day<\/th><th>First opens<\/th><th>Splash<\/th><th>Home<\/th><th>Splash → Home<\/th><th>Opened app<\/th><\/tr><\/thead>/.test(dayCard);
  // ... across the WHOLE country view (crumb, notes, Steps card, board, cards): the reason once, the dates once (the note
  // under the Country control), the board's note without either (the tab's lead line, on every view, only DEFINES "incl.
  // late open" — not counted)
  const cnt = (s, re) => (s.match(re) || []).length, hv = h.replace(/^<p class="fo-note fo-lead">.*?<\/p>/, '');
  R.pick_cols_once = hv.length < h.length && h.split(FO._.CC_COLS).length === 2 && cnt(h, /country-wise nahi padhe/g) === 1
    && cnt(h, /Language \/ Permission/g) === 1 && cnt(hv, /late open/g) === 1 && cnt(h, /Country view me sirf/g) === 1;
  R.pick_dates_once = cnt(h, /1 Aug 2026 – 29 Sep 2026/g) === 1 && cnt(h, /GA4 sirf ~2 mahine/g) === 1
    && /isse board app ke total tak judta hai\.<\/p><\/div><\/div><div class="card fo-card"><div class="ct"><h3>Every month · /.test(h);
  R.pick_no_gap = !h.includes('fo-gap') && !h.includes('fo-ccgap');
  R.pick_months = [...h.matchAll(/<td class="fo-nm">(?:<span class="fo-smp"[^>]*>≈<\/span>)?([A-Z][a-z]{2} 2026) <small>· (\d+)d<\/small><\/td><td>([\d,]+)<\/td><td>([\d,]+)<\/td><td>([\d,]+)<\/td><td><b>(\d+%)<\/b><\/td><td>(\d+%)<\/td>/g)].map(m => m.slice(1));
  R.pick_month_smp = /<td class="fo-nm"><span class="fo-smp"[^>]*>≈<\/span>Sep 2026/.test(h);
  R.pick_days = (h.match(/<tr><td class="fo-nm[^"]*">(<span class="fo-smp"[^>]*>≈<\/span>)?\d+ [A-Z][a-z]{2} 2026/g) || []).length;
  R.pick_nf = h.includes('<td class="fo-nm fo-nf">29 Sep 2026 · not final</td><td>300</td><td>250</td><td>200</td><td><b>80%</b></td><td>83%</td>');
  R.pick_smp_day = /<td class="fo-nm"><span class="fo-smp"[^>]*>≈<\/span>10 Sep 2026<\/td>/.test(h);
  R.pick_board_on = h.includes('<tr class="clk on" data-fo-ccr="XB" aria-current="true">');
  // a board row: the board's own scroll kept (the row stays where it was tapped)
  IDS['fo-ccbw'].scrollTop = 333; S2.style.minHeight = '';
  click('tr[data-fo-ccr]', { foCcr: 'XH' });
  R.row_cc = FO._.cc();
  R.row_scroll = IDS['fo-ccbw'] ? IDS['fo-ccbw'].scrollTop : null;
  R.row_minh = S2.style.minHeight;
  R.row_select_on = html2.includes('<select class="fo-ccs on" data-fo-ccsel="1"') && html2.includes('<option value="XH" selected>');
  // the select
  S2.onchange({ target: { closest: s => s === '[data-fo-ccsel]' ? { value: 'XG' } : null } });
  R.sel_cc = FO._.cc();
  R.sel_view = html2.includes('<span class="fo-cct">[XG] Name XG</span>') && html2.includes('<option value="XG" selected>');
  // another app: the pick stays; that app's file loads once; it has no XG → the message with the picker, never an empty table
  c2.APP = 'Gamma'; FO.paint();
  const ga = FO._.appOf('Gamma'), gx = F2.summary.find(z => z.key === 'kc'), gw = FO._.ccWait();
  R.g_loading = gw === '<div class="card fo-card"><div class="fo-ccm"><p class="fo-note">🌍 <b>[XG] Name XG</b> chuna hai — is app ka country data aate hi uska view khulega; tab tak neeche <b>All countries</b> ke numbers.</p><button type="button" class="fo-back" data-fo-ccx="1">✕ All countries</button></div></div>'
    && html2.split(LOADING_CTL).length === 4 && html2.includes(FO._.ccTop(ga) + gw)
    && html2.replace(gw, '').endsWith(FO._.appHtml(ga, gx, FO._.ccTop(ga), FO._.ccSlot(ga), FO._.ccIn(ga, 'm'), FO._.ccIn(ga, 'd')))
    && !html2.includes('fo-cct') && !html2.includes('class="fo-back fo-ccx"');
  await tick(); await tick();
  R.g_loads = LD['firstopen_cc_abcdef012345.json.gz'];
  R.g_missing = html2.includes('Is app me <b>[XG] Name XG</b> ka First open data nahi.') && !html2.includes('<table') && rowsOf(html2).length === 0;
  R.g_picker = [...html2.matchAll(/data-fo-cc="([^"]*)" aria-pressed="(true|false)"/g)].map(m => m[1]);
  c2.APP = 'Alpha Pick'; FO.paint();
  R.a_missing = html2.includes('Is app me <b>[XG] Name XG</b> ka First open data nahi (is app ka country-wise data abhi nahi bana).') && !html2.includes('<table') && !html2.includes('id="fo-cc"');
  c2.APP = 'Beta Pick'; FO.paint();
  R.back_b = html2.includes('<span class="fo-cct">[XG] Name XG</span>') && LD['firstopen_cc_0123456789ab.json.gz'] === 1;
  // a country picked (in the Every day card), then another app whose country file FAILS (hub "Change app" / the App picker):
  // All countries at once — the line for the pick + ✕, the three controls with Try again, every table — never the crumb and
  // a control alone; Try again → that country's view
  S2.onclick({ target: { closest: s => s === '[data-fo-cc]' ? { dataset: { foCc: 'XB' } } : s === '.fo-cc' ? { id: 'fo-cc-d' } : null } });
  FAILCC.add('firstopen_cc_ffffffffffff.json.gz');
  c2.APP = 'Zeta'; FO.paint();
  const za = FO._.appOf('Zeta'), zx = F2.summary.find(z => z.key === 'kf'), zw = FO._.ccWait(), TRY = '<span class="fo-ccl">Country</span><span class="fo-ccw">⚠️ Country data load nahi hua. <button type="button" class="fo-lnkb" data-fo-ccretry="1">Try again</button></span>';
  const allOf = () => FO._.appHtml(za, zx, FO._.ccTop(za), FO._.ccSlot(za), FO._.ccIn(za, 'm'), FO._.ccIn(za, 'd'));
  R.w_loading = FO._.cc() === 'XB' && html2.split(LOADING_CTL).length === 4 && html2.includes(FO._.ccTop(za) + zw) && html2.replace(zw, '').endsWith(allOf());
  await tick(); await tick();
  R.w_failed = html2.split(TRY).length === 4 && (html2.match(/data-fo-ccretry/g) || []).length === 3 && html2.includes(FO._.ccTop(za) + zw)
    && html2.replace(zw, '').endsWith(allOf()) && /<h3>Every day<\/h3>.*<th>Incl\. late open<\/th>/.test(html2) && html2.includes('<h3>Every month</h3>')
    && html2.includes('<td>First opens <small class="faint">/ day</small></td>') && !html2.includes('fo-cct') && !html2.includes('class="fo-back fo-ccx"') && FO._.cc() === 'XB';
  click('[data-fo-ccretry]', {});
  R.w_retry_loading = ['fo-cc', 'fo-cc-m', 'fo-cc-d'].every(id => IDS[id] && IDS[id]._html === LOADING_CTL);
  await tick(); await tick();
  R.w_view = LD['firstopen_cc_ffffffffffff.json.gz'] === 2 && html2.includes('<span class="fo-cct">[XB] Name XB</span>') && html2.includes('<h3>Every day · [XB] Name XB</h3>')
    && !html2.includes('chuna hai — is app ka country data aate hi');
  c2.APP = 'Beta Pick'; FO.paint();
  // ✕ All countries
  click('[data-fo-ccx]', {});
  R.x_cc = FO._.cc();
  R.x_all = html2.includes('data-fo-cc="" aria-pressed="true"') && html2.includes('<th>Incl. late open</th>') && html2.includes('By country · last 7 days vs usual');
  // ONE state for the three controls: a chip in the Every month card, the select in the Every day card, the ✕ in a card
  const tgt = (sel, ds, from) => ({ closest: s => s === sel ? { dataset: ds, value: ds.value } : s === '.fo-cc' && from ? { id: from } : null });
  S2.onclick({ target: tgt('[data-fo-cc]', { foCc: 'XC' }, 'fo-cc-m') });
  R.in_m_cc = FO._.cc();
  R.in_m_all3 = (html2.match(/data-fo-cc="XC" aria-pressed="true"/g) || []).length === 3 && html2.includes('<h3>Every day · [XC] Name XC</h3>');
  S2.onchange({ target: tgt('[data-fo-ccsel]', { value: 'XI' }, 'fo-cc-d') });
  R.in_d_cc = FO._.cc();
  R.in_d_all3 = (html2.match(/<option value="XI" selected>/g) || []).length === 3 && (html2.match(/<select class="fo-ccs on"/g) || []).length === 3
    && html2.includes('<span class="fo-cct">[XI] Name XI</span>') && html2.includes('<h3>Every month · [XI] Name XI</h3>');
  S2.onclick({ target: { closest: s => s === '[data-fo-ccx]' ? { dataset: {} } : s === '.fo-card' ? { querySelector: q => q === '.fo-cci' ? { id: 'fo-cc-d' } : null } : null } });
  R.in_x_cc = FO._.cc();
  R.in_x_all = (html2.match(/data-fo-cc="" aria-pressed="true"/g) || []).length === 3 && html2.includes('<h3>Every day</h3>') && !html2.includes('fo-ccx');
  R.from = [FO._.ccFrom(tgt('[data-fo-cc]', { foCc: 'XA' }, 'fo-cc-d')), FO._.ccFrom(tgt('[data-fo-cc]', { foCc: 'XA' }, '')),
    FO._.ccFrom({ closest: s => s === '.fo-card' ? { querySelector: () => null } : null }), FO._.ccFrom(null)];
  // a failed country load: Try again in the country area only; the rest drawn from the main file; the tap loads it again
  FAILCC.add('firstopen_cc_dddddddddddd.json.gz');
  c2.APP = 'Delta'; FO.paint(); await tick(); await tick();
  const all = live();
  const CCW = ['fo-cc', 'fo-cc-m', 'fo-cc-d'];
  R.f_retry_in_area = CCW.every(id => IDS[id] && IDS[id]._html === '<span class="fo-ccl">Country</span><span class="fo-ccw">⚠️ Country data load nahi hua. <button type="button" class="fo-lnkb" data-fo-ccretry="1">Try again</button></span>')
    && (all.match(/data-fo-ccretry/g) || []).length === 3;              // the top control + the two in-card ones, nowhere else
  R.f_rest = html2.includes('<td>First opens <small class="faint">/ day</small></td>') && html2.includes('<th>Incl. late open</th>') && !all.includes('data-fo-retry') && IDS['fo-ccbx']._html === '';
  click('[data-fo-ccretry]', {});
  R.f_loading = CCW.every(id => IDS[id]._html.includes('⏳ Country data loading…'));
  await tick(); await tick();
  R.f_loads = LD['firstopen_cc_dddddddddddd.json.gz'];
  R.f_ok = rowsOf(IDS['fo-ccbx']._html).join(',') === 'XA,XB,XC' && CCW.every(id => IDS[id]._html.includes('data-fo-cc="XC" aria-pressed="false"'));
  R.f_range_fallback = IDS['fo-ccbx']._html.includes('Country data <b>1 Aug 2026 – 29 Sep 2026</b> ka hai');   // no last_day: its last day
  // the strip: the top 6 chips in ONE sideways-scrolling row (the control keeps one height whatever it holds)
  R.strip = /<span class="fo-ccl">Country<\/span><button type="button" class="fo-ccc" data-fo-cc=""[^>]*>🌍 All countries<\/button><span class="fo-ccr">(<button type="button" class="fo-ccc"[^>]*>.*?<\/button>){3}<\/span><select /.test(IDS['fo-cc']._html);
  // a hole in the country store: the range, ONE warning, the gap row, the chart on the calendar
  c2.APP = 'Epsilon'; FO.paint(); await tick(); await tick();
  const gb = IDS['fo-ccbx'] ? IDS['fo-ccbx']._html : '';
  R.g_warn = (gb.match(/class="fo-note fo-ccgap"/g) || []).length === 1 && gb.includes('⚠️ Status ke liye 24 Aug – 27 Sep ke saare din ka country data chahiye — inme se <b>18 din</b> abhi nahi padhe (country data 1 Aug 2026 – 29 Sep 2026;')
    && gb.includes('Isliye abhi status <b>Too early</b>');
  R.g_why = gb.includes('<small>country data incomplete: 18 din missing</small>');
  click('[data-fo-cc]', { foCc: 'XA' });
  const gh = html2;
  R.g_view_warn = (gh.match(/class="fo-note fo-ccgap"/g) || []).length === 2;      // the view's note + the board's
  R.g_gap_rows = [...gh.matchAll(/<tr class="fo-gap"><td colspan="6">([^<]*)<\/td><\/tr>/g)].map(m => m[1]);
  // every day in its place, newest first: 10 Sep, the 15 days not read yet (one row), the 5 gone days (one row each, the
  // report's first opens, the funnel "—"), 20 Aug … 1 Aug, then the app's day 1 … 31 Jul (gone) LAST, right before </tbody>
  R.g_gap_between = /10 Sep 2026<\/td>(?:(?!<tr).)*<\/tr><tr class="fo-gap"><td colspan="6">↕ 15 din \(26 Aug – 9 Sep\)[^<]*<\/td><\/tr><tr class="fo-old"><td class="fo-nm">25 Aug 2026 <small>· First opens only<\/small><\/td><td>25<\/td><td>—<\/td><td>—<\/td><td>—<\/td><td>—<\/td><\/tr>(?:<tr class="fo-old">(?:(?!<tr).)*<\/tr>){4}<tr><td class="fo-nm">20 Aug 2026<\/td>/.test(gh);
  R.g_tail_last = /<tr><td class="fo-nm">1 Aug 2026<\/td>(?:(?!<tr).)*<\/tr><tr class="fo-old"><td class="fo-nm">31 Jul 2026 <small>· First opens only<\/small><\/td><td>0<\/td>(?:(?!<tr).)*<\/tr><tr class="fo-old">(?:(?!<tr).)*<\/tr><tr class="fo-old"><td class="fo-nm">29 Jul 2026 <small>· First opens only<\/small><\/td><td>11<\/td><td>—<\/td><td>—<\/td><td>—<\/td><td>—<\/td><\/tr><\/tbody>/.test(gh);
  R.g_old = [...gh.matchAll(/<tr class="fo-old"><td class="fo-nm">(\d+ [A-Z][a-z]{2}) 2026 <small>· ([^<]*)<\/small><\/td><td>([^<]*)<\/td>/g)].map(m => m.slice(1));
  R.g_old_note = (gh.match(/<b>First opens only<\/b> wale 8 din: GA4 ne un dino ka event data hata diya/g) || []).length;
  R.g_view_note = gh.includes('(GA4 sirf ~2 mahine ka data rakhta hai, usse purane dino ke country-wise sirf First opens milte hain).');
  R.g_days = (gh.match(/<tr><td class="fo-nm[^"]*">(<span class="fo-smp"[^>]*>≈<\/span>)?\d+ [A-Z][a-z]{2} 2026/g) || []).length;
  const MONTH_RE = /<tr(?: class="fo-old")?><td class="fo-nm">(?:<span class="fo-smp"[^>]*>≈<\/span>)?([A-Z][a-z]{2} 2026)(?: <small>· (\d+)d<\/small>)?((?: <small class="fo-mx">[^<]*<\/small>)*)<\/td><td>([^<]*)<\/td><td>([^<]*)<\/td>/g;
  const monthsOf = h => [...h.matchAll(MONTH_RE)].map(m => [m[1], m[2] == null ? null : +m[2], m[3].replace(/<[^>]*>/g, '').trim(), m[4], m[5]]);
  R.g_months = monthsOf(gh);
  const filled = FO._.ccFill(FO._.ccRows(GAP, 'XA'), day(-3));
  R.g_fill = [filled.length, filled.filter(r => r[1] == null).length, filled[0][0], filled[0][1], filled[23][0], filled[23][1], filled[43][0], filled[43][1]];
  R.g_fill_plain = FO._.ccFill(FO._.ccRows(GAP, 'XA')).length;          // no day 1 given: from the first row, as before
  const ch = { none: FO._.ccNone(GAP), cc: 'XA' };
  R.g_tips = [day(-3), day(-1), day(22), day(30)].map(k => FO._.noneTip(ch, k)).concat([FO._.noneTip({}, day(30))]);
  // Eta: a tail of not read / no country / gone / not read; Theta: a tail not read at all — each the last rows of Every day
  c2.APP = 'Eta'; FO.paint(); await tick(); await tick();
  click('[data-fo-cc]', { foCc: 'XA' });
  const eh = html2;
  R.e_tail = /<tr><td class="fo-nm">1 Aug 2026<\/td>(?:(?!<tr).)*<\/tr><tr class="fo-gap"><td colspan="6">↕ 1 din \(31 Jul – 31 Jul\): abhi padhe ja rahe hain \(backfill chal raha hai\)<\/td><\/tr><tr class="fo-old"><td class="fo-nm">30 Jul 2026 <small>· GA4 named no country<\/small><\/td><td>—<\/td><td>—<\/td><td>—<\/td><td>—<\/td><td>—<\/td><\/tr><tr class="fo-gap"><td colspan="6">↕ 1 din \(29 Jul – 29 Jul\)[^<]*<\/td><\/tr><tr class="fo-old"><td class="fo-nm">28 Jul 2026 <small>· First opens only<\/small><\/td><td>7<\/td>(?:(?!<tr).)*<\/tr><tr class="fo-gap"><td colspan="6">↕ 2 din \(26 Jul – 27 Jul\): abhi padhe ja rahe hain \(backfill chal raha hai\)<\/td><\/tr><\/tbody>/.test(eh);
  R.e_months = monthsOf(eh);
  R.e_note = (eh.match(/<b>First opens only<\/b> wale 1 din/g) || []).length;
  R.e_tip_nobody = FO._.noneTip({ none: FO._.ccNone(CCF['firstopen_cc_cccccccccccc.json.gz']), cc: 'XA' }, day(-2));
  c2.APP = 'Theta'; FO.paint(); await tick(); await tick();
  const th = html2;
  R.t_tail = /<tr><td class="fo-nm">1 Aug 2026<\/td>(?:(?!<tr).)*<\/tr><tr class="fo-gap"><td colspan="6">↕ 2 din \(30 Jul – 31 Jul\): abhi padhe ja rahe hain \(backfill chal raha hai\)<\/td><\/tr><\/tbody>/.test(th);
  R.t_no_old = !th.includes('fo-old"><td class="fo-nm">3') && !th.includes('First opens only') && th.includes('(GA4 sirf ~2 mahine ka data rakhta hai, usse purana country-wise nahi milta).');
  R.t_months = monthsOf(th);
  c2.APP = 'Epsilon'; FO.paint(); await tick();
  click('[data-fo-ccx]', {});
  out.cc = R;
  out.hold = holdModel(FO, c2, S2);
  c2.APP = 'Beta Pick'; FO.paint();
  out.pick = pickModel(FO, c2, S2, () => html2);
}

// hold(): a layout model (block heights, a sticky top bar, scrollY): the board's slot grows from 0 to the board's height
// while the reader is somewhere; what the reader looks at must not move (|Δ| ≤ 1 px), and nothing scrolls at the top
function holdModel(FO, c2, S2) {
  const R = {};
  const sizes = {
    375: { vh: 812, tb: 73, blocks: [['', 180], ['', 60], ['fo-cc', 92], ['mini', 400], ['grid', 900], ['fo-ccbx', 0], ['month', 300], ['day', 700]], board: 1037 },
    1280: { vh: 900, tb: 68, blocks: [['', 60], ['', 50], ['fo-cc', 48], ['mini', 300], ['grid', 330], ['fo-ccbx', 0], ['month', 300], ['day', 700]], board: 803 } };
  const QS = c2.document.querySelector;
  for (const w of [375, 1280]) {
    const S = sizes[w];
    const run = (place) => {
      const W = { scrollY: 0, innerHeight: S.vh, scrollBy(x, y) { W.scrollY += y; } };
      const els = S.blocks.map(([id, h]) => ({ id, h, isConnected: true }));
      const topOf = i => S.tb + els.slice(0, i).reduce((t, e) => t + e.h, 0) - W.scrollY;
      els.forEach((e, i) => { e.getBoundingClientRect = () => ({ top: topOf(i), bottom: topOf(i) + e.h, height: e.h }); e.nextElementSibling = els[i + 1] || null; });
      const at = id => topOf(els.findIndex(e => e.id === id));
      c2.window = W; S2.children = els;
      c2.document.querySelector = s => s === '.topbar' ? { getBoundingClientRect: () => ({ bottom: S.tb }) } : QS(s);
      const [id, y] = place; W.scrollY = id ? Math.max(0, at(id) - y) : 0;
      const before = { y: W.scrollY, mini: at('mini'), grid: at('grid'), month: at('month'), day: at('day') };
      FO._.hold(() => { els.find(e => e.id === 'fo-ccbx').h = S.board; }, els.find(e => e.id === 'fo-ccbx'));
      return { y: W.scrollY - before.y, mini: at('mini') - before.mini, grid: at('grid') - before.grid, month: at('month') - before.month, day: at('day') - before.day };
    };
    R[w] = {
      month_under_bar: run(['month', 120]).month,        // the old bug: a strip of the chart on screen kept the chart
      month_mid: run(['month', 300]).month,
      day_far: run(['day', 150]).day,
      top: run(['', 0]),                                 // at the top of the page: nothing scrolls
      slot_low: run(['month', S.vh - 120]),              // the slot in the lower half: the chart stays, the board below it
    };
  }
  c2.document.querySelector = QS; delete c2.window; S2.children = undefined;
  return R;
}

// pick() from a control INSIDE a card, on a layout model built from the page's OWN html (every block's height from what it
// holds: table rows, step bars, notes by their length, the chart, the controls, a card title that wraps; the steps and the
// chart side by side from 1180 px; the Country control 36 px, 80 px on a phone). The reader has the Every day (or Every
// month) card's control on screen and picks there; the whole view above it is redrawn with other heights (mini table, steps,
// a note, the chart, the board, the month card, the card's own title with ✕) — that control's top must not move (≤ 1 px).
// Worst case on purpose: the browser clamps the scroll the moment the new html is laid out (the screen's min-height is
// dropped by paint()), before pick() puts the page height back.
function pickModel(FO, c2, S2, html) {
  const blocksOf = (h, tags) => { const re = new RegExp('<(\\/?)(' + tags + ')\\b[^>]*>', 'g'), out = []; let d = 0, st = 0, open = '', m;
    while ((m = re.exec(h))) { if (!m[1]) { if (d === 0) { st = re.lastIndex; open = m[0]; } d++; } else { d--; if (d === 0) out.push({ open, inner: h.slice(st, m.index) }); } }
    return out; };
  const text = h => h.replace(/<[^>]+>/g, '').replace(/&[a-z#0-9]+;/g, 'x');
  const has = (o, c) => new RegExp('class="[^"]*\\b' + c + '\\b').test(o);
  const lines = (h, w, cw) => Math.max(1, Math.ceil(text(h).length * cw / w));
  const wrap = (items, w, gap, rgap) => { const rows = []; let cur = null;   // flex-wrap: [width, height] items in rows
    for (const [iw, ih] of items) { if (cur && cur.w + gap + iw <= w) { cur.w += gap + iw; cur.h = Math.max(cur.h, ih); } else { cur = { w: Math.min(iw, w), h: ih }; rows.push(cur); } }
    return rows.reduce((t, r) => t + r.h, 0) + Math.max(0, rows.length - 1) * rgap; };
  function model(vw) {
    const phone = vw <= 760, W = phone ? vw - 24 : vw - 240 - 48, CTL = (phone ? 80 : 36);
    const rowsH = inner => { const n = (inner.match(/<tr\b/g) || []).length; return n ? 41 + (n - 1) * 37 : 0; };
    const head = (inner, w) => { const it = [], h3 = /<h3>([\s\S]*?)<\/h3>/.exec(inner), sp = /<span class="faint"[^>]*>([\s\S]*?)<\/span>/.exec(inner);
      if (h3) it.push([text(h3[1]).length * 8, 20]); if (/<button/.test(inner)) it.push([130, 30]); if (sp) it.push([text(sp[1]).length * 5.6, 16]);
      return wrap(it, w, 12, 4) + 12; };
    const inBlock = (b, w) => { const o = b.open;
      if (has(o, 'ct')) return head(b.inner, w);
      if (has(o, 'fo-cc')) return CTL + 12;
      if (has(o, 'fo-tw')) return 1 + Math.min(has(o, 'fo-tall') ? 560 : 1e9, rowsH(b.inner));
      if (o.startsWith('<p')) return lines(b.inner, Math.min(w, 820), 6.3) * 18 + 12;
      if (has(o, 'fo-bar')) return 31;
      if (has(o, 'fo-chart')) return 210;
      if (has(o, 'fo-lg')) return 24;
      if (has(o, 'fo-chips')) { const n = (b.inner.match(/<button/g) || []).length, per = Math.max(1, Math.floor((w + 8) / 118)); return Math.ceil(n / per) * 44 - 8 + 14; }
      return 40; };
    const cardH = (inner, w) => 2 + 32 + blocksOf(inner, 'div|p').reduce((t, b) => t + inBlock(b, w - 36), 0) + 14;
    const crumb = inner => wrap(blocksOf(inner, 'button|span').map((b, i) => [Math.min(W, text(b.inner).length * 7 + 26), 36 + (i && text(b.inner).length * 6.3 > W ? 18 : 0)]), W, 12, 8) + 12;
    const blockH = b => { const o = b.open;
      if (o.startsWith('<p')) return lines(b.inner, Math.min(W, 820), 6.4) * 18 + 12;
      if (has(o, 'fo-crumb')) return crumb(b.inner);
      if (has(o, 'fo-cc')) return CTL + 12;
      if (has(o, 'card')) return cardH(b.inner, W);
      if (has(o, 'fo-grid')) { const cs = blocksOf(b.inner, 'div|p'); if (vw >= 1180) { const w1 = Math.max(300, (W - 14) / 3); return Math.max(cardH(cs[0].inner, w1), cardH(cs[1].inner, W - 14 - w1)); }
        return cs.reduce((t, c) => t + cardH(c.inner, W), 0); }
      if (/id="fo-ccbx"/.test(o)) return blocksOf(b.inner, 'div|p').reduce((t, c) => t + cardH(c.inner, W), 0);
      return 20; };
    // the top of the element with this id within the screen: a block of the screen, or a block inside one of its cards
    const docTop = (h, id) => { let y = 0; const k = 'id="' + id + '"';
      for (const b of blocksOf(h, 'div|p')) { if (b.open.includes(k)) return y;
        if (b.inner.includes(k)) { let yy = y + 1 + 16; for (const c of blocksOf(b.inner, 'div|p')) { if (c.open.includes(k)) return yy; yy += inBlock(c, W - 36); } return null; }
        y += blockH(b); }
      return null; };
    return { docTop, total: h => blocksOf(h, 'div|p').reduce((t, b) => t + blockH(b), 0), CTL };
  }
  const R = {}, QS = c2.document.querySelector, GE = c2.document.getElementById, IH = Object.getOwnPropertyDescriptor(S2, 'innerHTML'), OH = Object.getOwnPropertyDescriptor(S2, 'offsetHeight');
  for (const [vw, vh, tb] of [[375, 812, 73], [1280, 900, 68]]) {
    const M = model(vw), top0 = tb + 15;   // the screen starts under the sticky top bar + the content's padding
    const W = { scrollY: 0, innerHeight: vh, scrollBy(x, y) { W.scrollY = Math.max(0, Math.min(W.scrollY + y, maxY())); } };
    const pageH = () => Math.max(M.total(html()), parseFloat(S2.style.minHeight) || 0);
    const maxY = () => Math.max(0, top0 + pageH() + 32 - vh);
    c2.window = W;
    Object.defineProperty(S2, 'offsetHeight', { configurable: true, get: () => M.total(html()) });
    Object.defineProperty(S2, 'innerHTML', { configurable: true, get: IH.get, set: v => { IH.set(v); W.scrollY = Math.min(W.scrollY, maxY()); } });
    c2.document.getElementById = id => { const e = GE(id); if (e && /^fo-cc(-[md])?$/.test(id)) e.getBoundingClientRect = () => { const t = top0 + M.docTop(html(), id) - W.scrollY; return { top: t, bottom: t + M.CTL, height: M.CTL }; }; return e; };
    c2.document.querySelector = s => s === '.topbar' ? { getBoundingClientRect: () => ({ bottom: tb }) } : QS(s);
    const vt = id => top0 + M.docTop(html(), id) - W.scrollY;           // where the control is on screen now
    const place = (id, y) => { W.scrollY = Math.max(0, Math.min(top0 + M.docTop(html(), id) - y, maxY())); };
    const reset = () => { if (FO._.cc()) FO._.pick(''); S2.style.minHeight = ''; };
    const tap = (sel, ds, from) => ({ closest: s => s === sel ? { dataset: ds, value: ds.value } : s === '.fo-cc' && from ? { id: from } : null });
    const run = (id, y, act) => { place(id, y); const y0 = vt(id), d0 = M.docTop(html(), id), s0 = W.scrollY; act();
      return { dy: Math.round((vt(id) - y0) * 10) / 10, moved: M.docTop(html(), id) - d0, scrolled: W.scrollY - s0, at: Math.round(y0) }; };
    const r = {};
    reset();
    r.day_chip = run('fo-cc-d', 300, () => S2.onclick({ target: tap('[data-fo-cc]', { foCc: 'XB' }, 'fo-cc-d') }));   // All → a country
    r.day_cc = FO._.cc();
    r.day_chip2 = run('fo-cc-d', 300, () => S2.onclick({ target: tap('[data-fo-cc]', { foCc: 'XA' }, 'fo-cc-d') }));  // a country → another
    reset();
    r.day_sel = run('fo-cc-d', 420, () => S2.onchange({ target: tap('[data-fo-ccsel]', { value: 'XH' }, 'fo-cc-d') }));   // All → the select's country
    r.sel_cc = FO._.cc();
    r.day_x = run('fo-cc-d', 300, () => S2.onclick({ target: { closest: s => s === '[data-fo-ccx]' ? { dataset: {} } : s === '.fo-card' ? { querySelector: q => q === '.fo-cci' ? { id: 'fo-cc-d' } : null } : null } }));
    r.x_cc = FO._.cc();
    reset();
    r.month_chip = run('fo-cc-m', 200, () => S2.onclick({ target: tap('[data-fo-cc]', { foCc: 'XC' }, 'fo-cc-m') }));
    // the top control (under the crumb): the crumb above it grows for a country (its name, the ✕) — it stays too
    reset();
    r.top_chip = run('fo-cc', 200, () => S2.onclick({ target: tap('[data-fo-cc]', { foCc: 'XB' }, 'fo-cc') }));
    reset();
    R[vw] = r;
  }
  Object.defineProperty(S2, 'innerHTML', IH); Object.defineProperty(S2, 'offsetHeight', OH);
  c2.document.getElementById = GE; c2.document.querySelector = QS; delete c2.window;
  return R;
}
