// 💰 Revenue by source — the page side, run for real: the SRC module of frontend/index.html (cut out by its markers) in a node
// vm with stub page helpers, on SYNTHETIC data made up here (no real names, ids or numbers): the pointer check, the lazy
// files, All apps (sums per period, sorted by total, the All apps row, the %), a period tap (the control kept in place),
// one app (tiles, months newest first with "so far", days with Today / Yesterday, a day not read yet), the GA4 channels
// card from the app's channel file, ₹ view, and a tap on an app row. Prints ONE JSON report.
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('const SRC=(()=>{'), b = html.indexOf('// the Install value page: 📈 ROI first');
if (a < 0 || b < 0 || b < a) { console.log(JSON.stringify({ errors: ['SRC module not found'] })); process.exit(0); }
const src = html.slice(a, b) + '\nthis.SRC=SRC;';
const out = {}, errors = [];
const ROOT = { dataset: { aid: '' }, _html: '', get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  querySelector: () => ({ getBoundingClientRect: () => ({ top: 100 }) }) };
const handlers = {};
let CUR = 'USD', APPSET = [], SCROLL = 0;
const DAYS = 40, TODAY = '2026-10-31';
const iso = t => new Date(t).toISOString().slice(0, 10);
const d0 = iso(Date.parse(TODAY + 'T00:00:00Z') - (DAYS - 1) * 864e5);
// app A: every day paid 10, notif 5, organic 4, other 1 (USD); day index 20 not read yet; app B: paid 1, notif 0, organic 1, other 0
const rev = (p, n, o, x) => Array.from({ length: DAYS }, (_, i) => [p, n, o, x]);
const A = { app_id: 'ca-app-pub-0000000000000000~1', key: '000000000001', app: 'Alpha', tz: 'UTC', today: TODAY, d0,
  rev: rev(10, 5, 4, 1), ses: rev(100, 50, 40, 10), mk: { '38': 's' }, bf: true, ch: ['Cross-network', 'Mobile Push Notifications', 'Direct', '(other)'],
  file: 'source_000000000001.json.gz' };
A.rev[20] = null; A.ses[20] = null;
const B = { app_id: 'ca-app-pub-0000000000000000~2', key: '000000000002', app: 'Beta', tz: 'UTC', today: TODAY, d0,
  rev: rev(1, 0, 1, 0), ses: rev(10, 0, 10, 0), mk: {}, bf: false, ch: ['Cross-network', 'Direct'], file: 'source_000000000002.json.gz' };
const ALLF = { v: 1, at: '2026-10-31T00:00:00Z', groups: [['paid', 'Paid', ['Cross-network']], ['notif', 'Notification', ['Mobile Push Notifications']],
  ['org', 'Organic', ['Direct']], ['oth', 'Other', ['(other)']]], apps: [A, B] };
const CHF = { v: 1, key: A.key, app_id: A.app_id, d0, ch: A.ch, days: Array.from({ length: DAYS }, (_, i) => i === 20 ? null : [[100, 50, 10, 10], [50, 25, 5, 5], [40, 20, 4, 4], [10, 5, 1, 1]]) };
let LOADS = [];
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error, Date,
  DATA: { source: { file: 'source.json.gz', v: 'abc', apps: { [A.app_id]: { file: A.file, v: 'a1' }, [B.app_id]: { file: B.file, v: 'b1' } } },
          apps_catalog: [{ app_id: A.app_id, app_name: 'Alpha App' }, { app_id: B.app_id, app_name: 'Beta App' }] },
  document: { getElementById: id => id === 'src-root' ? ROOT : null, addEventListener: (t, f) => { handlers[t] = f; } },
  window: { scrollBy: (x, y) => { SCROLL += y; } },
  fetchGzJson: url => { LOADS.push(url); return Promise.resolve(url.startsWith('source.json.gz') ? ALLF : CHF); },
  cfx: () => CUR === 'INR' ? 88 : 1, csym: () => CUR === 'INR' ? '₹' : '$', curView: () => CUR,
  appIcon: n => `<i data-icon="${n}"></i>`, setApp: n => { APPSET.push(n); },
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+p[1] - 1]; },
  fmtMon: k => ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4),
};
vm.createContext(ctx);
try { vm.runInContext(src, ctx); } catch (e) { errors.push('load: ' + e.message); }
const SRC = ctx.SRC;
const flush = () => new Promise(r => setImmediate(r));
const strip = h => String(h).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
const tap = (sel) => handlers.click({ target: { closest: s => s === '#src-root' ? ROOT : (s === sel.k ? { dataset: sel.d, getBoundingClientRect: () => ({ top: 100 }) } : null) } });
(async () => {
  try {
    const noPtr = (() => { const p = ctx.DATA.source; ctx.DATA.source = null; const r = SRC.block(''); ctx.DATA.source = p; return r; })();
    out.no_pointer = noPtr;
    ROOT.dataset.aid = '';
    const first = SRC.block('');
    out.loading = strip(first);
    await flush(); await flush();
    out.all = strip(ROOT.innerHTML);
    out.loads1 = LOADS.slice();
    tap({ k: '[data-src-per]', d: { srcPer: 'yday' } });
    out.yday = strip(ROOT.innerHTML);
    out.scroll_after_tap = SCROLL;
    tap({ k: '[data-src-per]', d: { srcPer: 'all' } });
    out.all_time = strip(ROOT.innerHTML);
    tap({ k: '[data-src-app]', d: { srcApp: A.app_id } });
    out.appset = APPSET.slice();
    // one app
    ROOT.dataset.aid = A.app_id;
    tap({ k: '[data-src-per]', d: { srcPer: '30' } });
    out.app_loading_channels = strip(ROOT.innerHTML);
    await flush(); await flush();
    out.app = strip(ROOT.innerHTML);
    out.app_html = ROOT.innerHTML;
    out.loads2 = LOADS.slice();
    CUR = 'INR'; SRC.repaint(); out.app_inr = strip(ROOT.innerHTML);
  } catch (e) { errors.push(e.stack || e.message); }
  out.errors = errors;
  console.log(JSON.stringify(out));
})();
