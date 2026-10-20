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
//     pick (no jump), and the All countries view = today's view + the two country blocks, nothing else.
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
  const ccFile = (key, codes) => ({ v: 1, key, app_id: 'id-' + key, final_till: day(57), first_day: day(0),
    days: Array.from({ length: 60 }, (_, i) => { const c = {}; for (const k of codes) if (k !== 'XI' || i % 3 === 0) c[k] = VAL[k].slice();
      const t = [0, 1, 2].map(j => Object.values(c).reduce((s, v) => s + v[j], 0) + [9, 8, 7][j]); return [day(i), t[0], t[1], t[2], i === 40 ? 0.25 : null, c]; }),
    summary: codes.map(k => ({ cc: k, status: ST[k] || 'N/A', why: ST[k] ? '' : 'low data', s2h: S2H[k], usual: k === 'XA' ? 0.6 : S2H[k], change: k === 'XA' ? -0.1 : 0,
      opened: 0.8, opened_usual: 0.8, fo_day: FOD[k], fo_day_usual: FOD[k] + 10, final_days: 58, sample: k === 'XB' ? 0.25 : null, share: FOD[k] / 1300 })),
    unnamed: { summary: { fo_day: 9, opened: 0.89, s2h: 0.875, share: 9 / 1300 } } });
  const CCF = { 'firstopen_cc_0123456789ab.json.gz': ccFile('kb', CODES), 'firstopen_cc_abcdef012345.json.gz': ccFile('kc', ['XA', 'XB']),
    'firstopen_cc_dddddddddddd.json.gz': ccFile('kd', ['XA', 'XB', 'XC']) };
  const ptrOf = (f, n) => ({ file: f, v: 'c-' + f.slice(13, 17), from: day(0), n, days: 60 });
  const F2 = JSON.parse(JSON.stringify(FILE));
  F2.apps = F2.apps.filter(a => a.key !== 'kh');
  F2.apps[1].cc = ptrOf('firstopen_cc_0123456789ab.json.gz', 9);
  F2.apps[2].cc = ptrOf('firstopen_cc_abcdef012345.json.gz', 2);
  F2.apps.push({ ...JSON.parse(JSON.stringify(F2.apps[2])), key: 'kd', app: 'Delta', app_id: 'id-d', cc: ptrOf('firstopen_cc_dddddddddddd.json.gz', 3) });
  F2.summary = F2.summary.filter(x => x.key !== 'kh').concat([{ ...F2.summary[0], key: 'kd', app: 'Delta' }]);
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
  const board = IDS['fo-ccbx'] ? IDS['fo-ccbx']._html : '';
  R.board_rows = rowsOf(board);
  R.board_unnamed_last = /data-fo-ccr="XI"[\s\S]*<tr class="fo-un"><td class="fo-nm"><span class="fo-an"><span class="fo-fl">❔<\/span><span>Not named by GA4<\/span><\/span><\/td><td class="fo-stc"><small>no status<\/small><\/td><td>88%<\/td><td>—<\/td><td>—<\/td><td>89%<\/td><td>9<\/td><td>0.7%<\/td><\/tr><\/tbody>/.test(board);
  R.board_chips = [...board.matchAll(/data-fo-ccfilt="([^"]+)"[^>]*><span>[^<]*<\/span> <b>(\d+)<\/b>/g)].map(m => [m[1], +m[2]]);
  R.board_cells_xa = board.includes('<td class="down">−10 pts</td><td>80%</td><td>500</td><td>38%</td></tr>');
  R.board_cells_xi = board.includes('<td>0.4</td><td>&lt;0.1%</td></tr>') && board.includes('<td>5</td><td>0.4%</td></tr>');
  R.board_note = board.includes('Country data <b>1 Aug 2026</b> se hai (GA4 sirf ~2 mahine rakhta hai) aur sirf First open → Splash → Home');
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
  const withCc = html2, top = FO._.ccTop(a), slot = FO._.ccSlot(a);
  const cc0 = a.cc; delete a.cc; FO.paint(); const noCc = html2; a.cc = cc0;
  R.all_plus_two = withCc.includes(top) && withCc.includes(slot) && withCc.replace(top, '').replace(slot, '') === noCc;
  R.nocc_plain = !noCc.includes('fo-cc') && !noCc.includes('By country');
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
  R.pick_steps = (h.match(/class="fo-bl"/g) || []).length === 1 && h.includes('<span class="fo-bl">Home</span>') && h.includes('Country-wise sirf Home tak padha jata hai');
  R.pick_note = h.includes('Country view me sirf <b>First open → Splash → Home</b> hai') && h.includes('country data <b>1 Aug 2026</b> se hai');
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
  R.g_loading = html2.includes('<span class="fo-cct">[XG] Name XG</span>') && html2.includes('⏳ Country data loading…') && !html2.includes('<table');
  await tick(); await tick();
  R.g_loads = LD['firstopen_cc_abcdef012345.json.gz'];
  R.g_missing = html2.includes('Is app me <b>[XG] Name XG</b> ka First open data nahi.') && !html2.includes('<table') && rowsOf(html2).length === 0;
  R.g_picker = [...html2.matchAll(/data-fo-cc="([^"]*)" aria-pressed="(true|false)"/g)].map(m => m[1]);
  c2.APP = 'Alpha Pick'; FO.paint();
  R.a_missing = html2.includes('Is app me <b>[XG] Name XG</b> ka First open data nahi (is app ka country-wise data abhi nahi bana).') && !html2.includes('<table') && !html2.includes('id="fo-cc"');
  c2.APP = 'Beta Pick'; FO.paint();
  R.back_b = html2.includes('<span class="fo-cct">[XG] Name XG</span>') && LD['firstopen_cc_0123456789ab.json.gz'] === 1;
  // ✕ All countries
  click('[data-fo-ccx]', {});
  R.x_cc = FO._.cc();
  R.x_all = html2.includes('data-fo-cc="" aria-pressed="true"') && html2.includes('<th>Incl. late open</th>') && html2.includes('By country · last 7 days vs usual');
  // a failed country load: Try again in the country area only; the rest drawn from the main file; the tap loads it again
  FAILCC.add('firstopen_cc_dddddddddddd.json.gz');
  c2.APP = 'Delta'; FO.paint(); await tick(); await tick();
  const all = live();
  R.f_retry_in_area = IDS['fo-cc'] && IDS['fo-cc']._html.includes('data-fo-ccretry="1">Try again</button>') && (all.match(/data-fo-ccretry/g) || []).length === 1;
  R.f_rest = html2.includes('<td>First opens <small class="faint">/ day</small></td>') && !all.includes('data-fo-retry') && IDS['fo-ccbx']._html === '';
  click('[data-fo-ccretry]', {});
  R.f_loading = IDS['fo-cc']._html.includes('⏳ Country data loading…');
  await tick(); await tick();
  R.f_loads = LD['firstopen_cc_dddddddddddd.json.gz'];
  R.f_ok = rowsOf(IDS['fo-ccbx']._html).join(',') === 'XA,XB,XC';
  out.cc = R;
}
