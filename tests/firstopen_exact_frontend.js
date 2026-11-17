// 🆕 First open tab — EXACT COUNTS on the page (firstopen_build, 17 Nov 2026): the FO module of frontend/index.html run
// for real in a node vm (the same stubs as tests/firstopen_frontend.js) on SYNTHETIC data made up here: a row whose
// First opens / Splash / Home came from the country store's exact read (x = 1) carries no "≈" on its day, only on the
// steps that stay GA4's sampled ones (Language … and Incl. late open); a sampled row (x = 0) keeps its day "≈"; an
// unsampled row none; All apps: Splash → Home "≈" only from the summary's "sample", Incl. late open and the steps from
// "sample_other"; the app's note says which numbers are exact. Prints ONE JSON report (tests/test_firstopen_exact_frontend.py).
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('const FO=(()=>{'), b = html.indexOf('function renderFirstOpen(){');
if (a < 0 || b < 0) { console.log(JSON.stringify({ errors: ['FO module not found'] })); process.exit(0); }
// the page's shared month-mover helpers (the owner's standard picker, 4 Nov 2026) — every period picker calls them
const MON0 = html.indexOf('// ---- the month mover'), MON1 = html.indexOf("// ---- a daily chart's period");
const MONSRC = MON0 >= 0 && MON1 > MON0 ? html.slice(MON0, MON1) : '';
// the page's shared date-with-year helpers (refYear / fmtDY / fmtRange)
const YR0 = html.indexOf('// ---- dates with their year ----'), YR1 = html.indexOf('// ---- end: dates with their year ----');
// (a test build has no today_date: the reference year is pinned so no test depends on the date it runs)
const YRSRC = (YR0 >= 0 && YR1 > YR0 ? html.slice(YR0, YR1) : '') + "\nrefYear=function(){ return '2026'; };\n";
const src = MONSRC + YRSRC + html.slice(a, b) + '\nthis.FO=FO;';
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
  appIdOf: name => ({ 'Xact': 'id-x' })[name] || '',
  fetchGzJson: () => { LOADS++; return FAIL ? Promise.reject(new Error('net')) : Promise.resolve(FILE); },
};
vm.createContext(ctx);

const day = i => { const d = new Date(Date.UTC(2026, 7, 1 + i)); return d.toISOString().slice(0, 10); };
// 60 days: 0 … 39 unsampled, 40 … 49 sampled (x 0), 50 … 59 sampled but exact three (x 1)
const row = i => [day(i), 120, 100, 60, 101, 61, 50, null, null, i >= 40 ? 0.2 : null, i >= 50 ? 1 : 0];
const FILE = { v: 1,
  apps: [{ key: 'kx', app: 'Xact', app_id: 'id-x', steps: { splash: 'S', home: 'H', language: 'L' }, steps_changed: [],
           first_day: day(0), final_till: day(57), days: Array.from({ length: 60 }, (_, i) => row(i)) }],
  summary: [{ key: 'kx', app: 'Xact', status: 'Normal', why: '', s2h: 0.6, usual: 0.6, change: 0, s2h_any: 0.6, opened: 0.83,
              opened_usual: 0.83, fo_day: 120, fo_day_usual: 120, steps: { language: [0.5, 0.5] }, final_days: 58,
              sample: null, sample_other: 0.2 }] };
const tick = () => new Promise(r => setTimeout(r, 0));
const SM = '<span class="fo-smp"[^>]*>≈</span>';
(async () => {
  try {
    vm.runInContext(src, ctx);
    const FO = ctx.FO;
    ctx.DATA = { firstopen: { file: 'firstopen.json.gz', v: 'v1', apps: { Xact: { status: 'Normal', s2h: 0.6, usual: 0.6, change: 0, fo_day: 120, id: 'id-x' } } },
                 apps_catalog: [{ app_id: 'id-x', app_name: 'Xact' }] };
    FO.render(); FO.paint(); await tick(); await tick();
    FO.paint();
    const h = SCREEN.innerHTML;
    out.all_s2h_plain = /<td><b>60%<\/b><\/td>/.test(h);                     // Splash → Home: exact all week, no ≈
    out.all_any_smp = new RegExp('<td>' + SM + '60%</td>').test(h);           // Incl. late open: still sampled
    out.all_steps_smp = new RegExp('<td>' + SM + 'Lang 50%</td>').test(h);
    ctx.APP = 'Xact'; FO.paint();
    const p = SCREEN.innerHTML;
    const tr = k => { const m = p.match(new RegExp('<tr><td class="fo-nm[^"]*">(?:' + SM + ')?' + k + '[\\s\\S]*?</tr>')); return m ? m[0] : ''; };
    const fmt = i => { const d = day(i).split('-'); return (+d[2]) + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+d[1] - 1] + ' 2026'; };
    const rx = tr(fmt(55)), rs = tr(fmt(45)), ru = tr(fmt(10));
    out.x_row = rx; out.s_row = rs; out.u_row = ru;
    out.x_day_plain = !!rx && !new RegExp('fo-nm[^"]*">' + SM).test(rx);
    out.x_smp_cells = (rx.match(new RegExp(SM, 'g')) || []).length;           // Language + Incl. late open
    out.x_lang_smp = new RegExp('<td>' + SM + '50</td>').test(rx);
    out.s_day_smp = new RegExp('fo-nm[^"]*">' + SM).test(rs) && (rs.match(new RegExp(SM, 'g')) || []).length === 1;
    out.u_none = !!ru && !ru.includes('fo-smp');
    out.note_pct = p.includes('sirf ~20% data padha');
    out.note_exact = p.includes('First opens · Splash · Home is hafte exact hain');
  } catch (e) { errors.push(String(e && e.stack || e)); }
  out.errors = errors;
  console.log(JSON.stringify(out));
})();
