// 🆕 First open tab — the page side, run for real: the FO module of frontend/index.html (cut out by its markers) in a node
// vm with stub page helpers, on SYNTHETIC data made up here (no real names, ids or numbers):
//   * the pointer check, the lazy file (its format check, a failed load + Try again);
//   * All apps: the status chips (counts), the table (sorted Worse first, a column sort, the chip filter, hidden apps
//     left out), the app names the App picker uses;
//   * one app: Today / Yesterday / 7 days / usual, the steps, every month (sums), every day (newest first, not final
//     marked), GA4 sampling marked "≈";
//   * the hub card: status word + key line from the pointer (no file load), by app id first;
//   * the points label (no "−0 pts").
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
  console.log(JSON.stringify({ errors, out }));
})();
