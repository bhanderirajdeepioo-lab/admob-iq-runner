// 📱 Devices v3 (All time + the standard picker + Custom) — the page side, run for real: the ROI module of
// frontend/index.html (cut out as tests/device_frontend.js does) in a node vm, its files read from a folder the Python test
// filled with device_build's own output on SYNTHETIC data: the loading message, the picker in the owner's order with the
// month mover, All time by default, the JS sums (devRange) against the build's own lists for EVERY standard button and
// country (parity), Custom, an old month, a country, the period's warnings. Prints ONE JSON report.
//   usage: node device_frontend_v3.js <index.html> <folder with stub.json + the roi_*_dv* files> [scenario]
'use strict';
const fs = require('fs'), vm = require('vm'), zlib = require('zlib'), path = require('path');
const [htmlPath, dir] = process.argv.slice(2);
const html = fs.readFileSync(htmlPath, 'utf8');
const END = '</details>`; }', a = html.indexOf('const ROI=(()=>{'), b = html.indexOf(END, html.indexOf('function roiWrap(html,aid)')) + END.length - 1;
if (a < 0 || b < 0) { console.log(JSON.stringify({ errors: ['ROI module not found'] })); process.exit(0); }
const MON0 = html.indexOf('// ---- the month mover'), MON1 = html.indexOf("// ---- a daily chart's period");
const src = (MON0 >= 0 && MON1 > MON0 ? html.slice(MON0, MON1) : '') + html.slice(a, b + 1) + '\nthis.ROI=ROI;';
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const asked = [];
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error, Date, parseFloat,
  DATA: null, document: undefined, window: {},
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1]; },
  fmtMon: k => MON[+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4),
  hubStChip: k => `<span class="hub-st st-${k}">${k}</span>`, appIconId: () => '', uniVis: () => true,
  valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Country ' + cc,
  csym: () => '$', cfx: () => 1, curView: () => 'USD', setApp: () => {}, hubAppId: () => '',
  fetchGzJson: url => { const name = String(url).split('?')[0]; asked.push(name); const p = path.join(dir, name);
    if (!fs.existsSync(p)) return Promise.reject(new Error('http 404'));
    return Promise.resolve(JSON.parse(zlib.gunzipSync(fs.readFileSync(p)).toString('utf8'))); },
};
vm.createContext(ctx);
const out = {}, errors = [];
try { vm.runInContext(src, ctx); } catch (e) { errors.push('load: ' + e.message); }
const R = ctx.ROI, strip = h => String(h).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
const tick = () => new Promise(r => setTimeout(r, 0));
const ROW_MIN = { today: 5, yday: 5, '7': 20 };
const close = (x, y) => (x == null && y == null) || (x != null && y != null && Math.abs(x - y) <= 1e-3 + 1e-9 * Math.abs(x));
function same(L, B) {                                  // a JS list vs the build's: row for row, totals, rest
  const bad = [];
  if ((L.rows || []).length !== (B.rows || []).length) bad.push('len ' + (L.rows || []).length + ' vs ' + (B.rows || []).length);
  (B.rows || []).forEach((r, i) => { const x = (L.rows || [])[i]; if (!x || x[0] !== r[0] || r.some((v, j) => j && !close(+v, +x[j]))) bad.push('row ' + i + ' ' + r[0]); });
  for (const k of ['n', 'p', 'cost', 'rev', 'd1', 'dn', 'pk']) if (!close(+(L.tot || {})[k], +(B.tot || {})[k])) bad.push('tot ' + k);
  if (!close(+(L.rest || {}).n, +(B.rest || {}).n) || (L.rest || {}).models !== (B.rest || {}).models) bad.push('rest');
  return bad;
}
function sameU(a, b) {                                 // two units: counts equal, the oldest date equal, sums close
  return (a || []).length === (b || []).length && (a || []).every((v, i) => i === 5 ? v === b[i] : close(+v, +b[i]));
}
async function range(D, lo, hi, cc, min) {
  for (let i = 0; i < 50; i++) { const g = R._.devRange(D, lo, hi, cc, min); if (!g.busy) return g; await tick(); }
  return { err: 'busy' };
}
(async () => {
  try {
    const stub = JSON.parse(fs.readFileSync(path.join(dir, 'stub.json'), 'utf8'));
    const d = { dev: stub, app_id: 'x~1' };
    out.loading = strip(R._.devView(d));
    await tick();
    out.all = strip(R._.devView(d));
    out.all_html = R._.devView(d);
    const D = R._.DVK[stub.file + '?' + stub.sha].j;
    out.months = D.months.length;
    // parity: every standard button and country, summed here from the month / day files = the build's own lists
    const par = {};
    for (const pid of ['today', 'yday', '7', 'tm', 'lm', '30', '60', '90', 'all']) {
      const B = D.P[pid], min = ROW_MIN[pid] || D.rmin;
      const g = await range(D, B.from, B.to, '', min);
      const bad = g.err ? ['load'] : same(g, B);
      let ccRows = 0;
      for (const [cc] of D.cc) {
        const h = await range(D, B.from, B.to, cc, min);
        bad.push(...(h.err ? ['load ' + cc] : same(h.by[cc], B.by[cc]).map(x => cc + ' ' + x)));
        ccRows += (B.by[cc].rows || []).length;
        if (!h.err && !sameU(h.u, B.u)) bad.push('units ' + cc);
      }
      if (!g.err && !sameU(g.u, B.u)) bad.push('units');
      par[pid] = { rows: (B.rows || []).length, cc_rows: ccRows, bad };
    }
    out.parity = par;
    out.asked_files = Array.from(new Set(asked)).length;
    // Custom (two partial months + a whole one between), an old month (its own file), a country
    R._.dvSet('', 'st', 1, 'cus', '2026-02-10', '2026-04-20');
    out.custom_busy = strip(R._.devView(d));
    for (let i = 0; i < 20; i++) await tick();
    out.custom = strip(R._.devView(d));
    out.custom_html = R._.devView(d);
    R._.dvSet('', 'st', 1, 'mon:2026-03');
    R._.devView(d); for (let i = 0; i < 20; i++) await tick();
    out.mon = strip(R._.devView(d));
    R._.dvSet('', 'st', 1, 'mon:' + D.today.slice(0, 7));
    out.mon_cur = strip(R._.devView(d));
    R._.dvSet('XA', 'st', 1, 'all');
    out.cc = strip(R._.devView(d));
    R._.dvSet('', 'st', 1, 'nonsense');
    out.fallback = strip(R._.devView(d));
    // a stub of another build than its file: stale, Try again
    const st2 = Object.assign({}, stub, { today: '2020-01-01', sha: '000000000000' });
    R._.devView({ dev: st2 }); await tick();
    out.stale = strip(R._.devView({ dev: st2 }));
    // Try again on a stale load: the app file and every Devices file (the index too) are read again
    const af = 'roi_' + D.key + '.json.gz';
    ctx.DATA = { roi: { file: 'roi.json.gz', v: 'v1', apps: { 'x~1': { file: af } } } };
    R._.data().AF[af] = { rows: [], _v: 'v1' };
    R._.devView(d); await tick();
    asked.length = 0;
    R._.dvRetry('x~1');
    R._.dvSet('', 'st', 1, 'all');
    R._.devView(d); for (let i = 0; i < 5; i++) await tick();
    out.retry_asked = Array.from(new Set(asked));
    out.retry_after = strip(R._.devView(d));
    // the sums' cache is the index's own: another app / another build with the same days never answers from it
    const g1 = await range(D, '2026-03-01', '2026-03-31', '');
    const D2 = Object.assign({}, D, { key: 'bbbbbbbbbbbb', months: D.months.map(e => [e[0], e[1], null, null]) });
    const g2 = await range(D2, '2026-03-01', '2026-03-31', '');
    out.switch = [g1.tot.n, g2.tot.n];
    // a Custom range wholly before the first day: never upside down
    const g3 = await range(D, '2019-01-01', '2019-02-01', '');
    out.outside = [g3.from, g3.to];
    // Custom opens on the build's Last 30 days: its lists, no day file read
    asked.length = 0;
    R._.dvSet('', 'st', 1, 'cus', '', '');
    out.cus30 = strip(R._.devView(d));
    out.cus30_asked = asked.filter(n => /_dvd_/.test(n)).length;
    // a month without its file (over the limit, no copy): said; a stopped history job: said
    const D3 = Object.assign({}, D, { months: D.months.map(e => e[0] === '2026-03' ? e.slice(0, 4).concat([1]) : e) });
    out.gap = strip(R._.dvWarn(D3, D.P.all));
    out.gap_other = strip(R._.dvWarn(D3, D.P['30']));
    const D4 = Object.assign({}, D, { hist: { on: true, stale: true } });
    out.hstale = strip(R._.dvWarn(D4, Object.assign({}, D.P['30'], { old: 5 })));
    // an app whose first install day is in the current month: the mover never offers an earlier month
    R._.dvSet('', 'st', 1, 'all');
    out.mover_new = R._.dvCtl(Object.assign({}, D, { first: D.today.slice(0, 7) + '-01' }));
  } catch (e) { errors.push(e.stack || e.message); }
  out.errors = errors;
  console.log(JSON.stringify(out));
})();
