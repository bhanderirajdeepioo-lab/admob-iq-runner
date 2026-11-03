// 📈 eCPM · first session vs returning — the page side, run for real: the NVR module of frontend/index.html (cut out by its
// markers) in a node vm with stub page helpers, on SYNTHETIC data made up here (no real names, ids or numbers): the
// pointer check, the lazy file (loading, a failed load + Try again), the period (Today … Last month, All time, Custom
// reversed → swapped; 7 / 30 days = the last final days), the tiles (both eCPMs, their ratio, impressions per session,
// the revenue split), the daily chart (both lines, the values printed), the ad unit / format / country tables (most revenue
// first, a column sort, the top 15 then "Show all", the unnamed country), a day not read yet, ₹ view, and the tapped control
// kept in place. Prints ONE JSON report.
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('const NVR=(()=>{'), b = html.indexOf('// the Install value page: 📈 ROI first');
if (a < 0 || b < 0 || b < a) { console.log(JSON.stringify({ errors: ['NVR module not found'] })); process.exit(0); }
const src = html.slice(a, b) + '\nthis.NVR=NVR;';
const out = {}, errors = [];
const ROOT = { dataset: { aid: '' }, _html: '', get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  querySelector: () => ({ getBoundingClientRect: () => ({ top: 100 }) }) };
const handlers = {};
let CUR = 'USD', SCROLL = 0, FAIL = false, LOADS = 0;
const iso = t => new Date(t).toISOString().slice(0, 10), DAY = 864e5, D0 = '2026-09-01';
const day = i => iso(Date.parse(D0 + 'T00:00:00Z') + i * DAY);
// 63 days 1 Sep … 2 Nov (final till 31 Oct); 11 Sep not read yet. A day: first session $2 / 1,000 impressions, returning
// $3 / 3,000 (not set $0.01 / 2); sessions 100 / 500, users 90 / 300; ad units: App open, Banner + 18 tiny ones; XA ($2 / $1
// eCPM), XB ($4 / $0.50), none named
const UNITS = [['unit_open', 'App open'], ['unit_banner', 'Banner']].concat(Array.from({ length: 18 }, (_, i) => ['unit_tiny_' + i, 'Native']));
const F = { v: 1, key: '000000000009', app_id: 'id-x', first_day: D0, last_day: day(62), final_till: day(60), units: UNITS,
  days: Array.from({ length: 63 }, (_, i) => i === 10 ? null : [day(i), [2, 1000, 3, 3000, 0.01, 2], [100, 90, 500, 300],
    Object.assign({ 0: [1.5, 600, 0.5, 500], 1: [0.5, 400, 2.5, 2500] }, ...UNITS.slice(2).map((u, j) => ({ [j + 2]: [0.001, 1, 0, 0] }))),
    { '--': [0.01, 2, 0, 0], XA: [1.2, 600, 2, 2000], XB: [0.8, 200, 1, 2000] }]) };
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error, Date,
  DATA: { nvr: { v: 1, apps: { 'id-x': { file: 'nvr_000000000009.json.gz', v: 'n1', from: D0, last: day(62) } } } },
  document: { getElementById: id => id === 'nvr-root' ? ROOT : null, addEventListener: (t, f) => { handlers[t] = f; } },
  window: { scrollBy: (x, y) => { SCROLL += y; } },
  fetchGzJson: url => { LOADS++; return FAIL ? Promise.reject(new Error('net')) : Promise.resolve(JSON.parse(JSON.stringify(F))); },
  cfx: () => CUR === 'INR' ? 88 : 1, csym: () => CUR === 'INR' ? '₹' : '$', curView: () => CUR,
  cm: (n, dp) => (CUR === 'INR' ? '₹' : '$') + (Number(n) * (CUR === 'INR' ? 88 : 1)).toFixed(dp == null ? 2 : dp),
  valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name ' + cc,
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+p[1] - 1]; },
};
vm.createContext(ctx);
try { vm.runInContext(src, ctx); } catch (e) { errors.push('load: ' + e.message); }
const NVR = ctx.NVR;
const flush = () => new Promise(r => setImmediate(r));
const strip = h => String(h).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
const tap = (sel, ds) => handlers.click({ target: { closest: s => s === '#nvr-root' ? ROOT : (s === sel ? { dataset: ds, getBoundingClientRect: () => ({ top: 100 }) } : null) } });
const change = (which, value) => handlers.change({ target: { value, closest: s => s === '#nvr-root' ? ROOT : (s === which ? {} : null) } });
const h = () => ROOT.innerHTML;
const tbl = (title) => { const i = h().indexOf(`<h3>${title}</h3>`); return i < 0 ? '' : h().slice(i, h().indexOf('</table>', i)); };
(async () => {
  try {
    out.no_pointer = (() => { const p = ctx.DATA.nvr; ctx.DATA.nvr = null; const r = NVR.block('id-x'); ctx.DATA.nvr = p; return r; })();
    out.no_app = strip(NVR.block('id-other'));
    ROOT.dataset.aid = 'id-x';
    ROOT.innerHTML = NVR.block('id-x').replace(/^<section[^>]*>|<\/section>$/g, '');
    out.loading = strip(h());
    await flush(); await flush();
    out.loads = LOADS;
    // 30 days = the last 30 FINAL days: 2 Oct … 31 Oct
    out.title30 = (h().match(/<h3>👥 First session vs Returning · eCPM<\/h3><span class="roi-note">([^<]*)<\/span>/) || [])[1];
    out.tiles30 = [...h().matchAll(/<div class="roi-kl">([^<]*)<\/div><div class="roi-kv">([^<]*)<\/div><div class="roi-ks">([^<]*)<\/div>/g)].map(m => [m[1], m[2], m[3]]);
    out.chart = /<path d="M[^"]+" class="n"\/><path d="M[^"]+" class="r"\/>/.test(h()) && h().includes('class="n">$2.00</text>') && h().includes('class="r">$1.00</text>');
    // the card that stays on top while the tables scroll: the title, the period, the country and the tiles in it; the chart
    // and the tables after it (owner, 3 Nov 2026)
    { const x = h(), i = x.indexOf('<div class="roi-card nvr-stk" id="nvr-stk">'), j = x.indexOf('</div><div class="roi-card">', i);
      const stk = i >= 0 && j > i ? x.slice(i, j) : '';
      out.sticky = { first: i === 0, period: stk.includes('data-nvr-per="30"'), country: stk.includes('data-nvr-cc=""'),
        tiles: stk.includes('First session eCPM'), chart_out: !stk.includes('data-nvr-ch') && x.indexOf('data-nvr-ch') > j,
        tables_out: x.indexOf('<h3>Ad units</h3>') > j }; }
    out.units_rows = [...tbl('Ad units').matchAll(/<tr><td class="roi-nm">([^<]*)/g)].map(m => m[1]);
    out.unit_open = tbl('Ad units').includes('<td class="roi-nm">unit_open <small>App open</small></td><td><b>$2.50</b></td><td>$1.00</td><td>2.5×</td><td>18,000</td><td>15,000</td><td>$45</td><td>$15</td></tr>');
    out.units_more = h().includes('data-nvr-all="u">Sab 20 dikhao</button>');
    out.formats = [...tbl('Ad formats').matchAll(/<tr><td class="roi-nm">([^<]*)<\/td><td><b>([^<]*)<\/b><\/td><td>([^<]*)<\/td><td>([^<]*)<\/td>/g)].map(m => m.slice(1));
    out.countries = [...tbl('Countries').matchAll(/<tr><td class="roi-nm"><span class="nvr-fl">[^<]*<\/span> ([^<]*)<\/td><td><b>([^<]*)<\/b><\/td><td>([^<]*)<\/td>/g)].map(m => m.slice(1));
    out.note = h().includes('GA4 ne 0.2% kamai kisi session group me nahi daali');
    // a column sort: returning eCPM, high first; again: low first
    tap('[data-nvr-sort]', { nvrSort: 'u:er' });
    out.sort_er = [...tbl('Ad units').matchAll(/<tr><td class="roi-nm">([^<]*)/g)].map(m => m[1]).slice(0, 2);
    tap('[data-nvr-sort]', { nvrSort: 'u:er' });
    out.sort_er2 = [...tbl('Ad units').matchAll(/<tr><td class="roi-nm">([^<]*)/g)].map(m => m[1]).slice(-2);
    tap('[data-nvr-sort]', { nvrSort: 'u:rev' });
    tap('[data-nvr-all]', { nvrAll: 'u' });
    out.units_all = [...tbl('Ad units').matchAll(/<tr><td class="roi-nm">/g)].length;
    // the periods (the tapped control kept: no scroll needed when nothing above it moved)
    const per = k => { tap('[data-nvr-per]', { nvrPer: k }); return (h().match(/<h3>👥 First session vs Returning · eCPM<\/h3><span class="roi-note">([^<]*)<\/span>/) || [])[1]; };
    out.periods = { today: per('today'), yday: per('yday'), '7': per('7'), tm: per('tm'), lm: per('lm'), all: per('all') };
    out.all_miss = h().includes('⏳ 1 din ka data abhi aa raha hai (purani history har build me thodi aur) · aakhri 2 din GA4 me abhi badal rahe hain (final nahi).');
    out.scroll = SCROLL;
    // Custom: from / to (reversed → swapped)
    change('[data-nvr-pf]', '2026-10-20'); change('[data-nvr-pto]', '2026-10-11');
    out.custom = [per2(), h().includes('<input type="date" data-nvr-pf="1" value="2026-10-11" min="2026-09-01" max="2026-11-02">'),
      (h().match(/First session eCPM<\/div><div class="roi-kv">([^<]*)/) || [])[1]];
    function per2() { return (h().match(/<h3>👥 First session vs Returning · eCPM<\/h3><span class="roi-note">([^<]*)<\/span>/) || [])[1]; }
    // the Country control: All countries + the period's top 5 by revenue + every country in a list; a pick → its own tiles
    // and chart (its impressions instead of a per-session figure), its row marked, one line saying so; All countries back
    tap('[data-nvr-per]', { nvrPer: '30' });
    const ccCtl = (h().match(/<div class="nvr-cc"[\s\S]*?<\/select><\/div>/) || [''])[0];
    out.cc_chips = [...ccCtl.matchAll(/data-nvr-cc="([^"]*)" aria-pressed="(true|false)"/g)].map(m => [m[1], m[2]]);
    out.cc_list = [...ccCtl.matchAll(/<option value="([^"]+)">([^<]*)<\/option>/g)].map(m => [m[1], m[2]]);
    tap('[data-nvr-cc]', { nvrCc: 'XB' });
    out.cc_xb = { title: (h().match(/<h3>(👥 First session vs Returning · eCPM[^]*?)<\/h3>/) || [])[1],
      tiles: [...h().matchAll(/<div class="roi-kl">([^<]*)<\/div><div class="roi-kv">([^<]*)<\/div>/g)].map(m => [m[1], m[2]]),
      chart: h().includes('class="n">$4.00</text>') && h().includes('class="r">$0.50</text>'),
      row_on: /<tr class="on" aria-current="true"><td class="roi-nm"><span class="nvr-fl">\[XB\]<\/span> Name XB/.test(h()), note: h().includes('<b>Name XB</b> chuna hai') };
    change('[data-nvr-ccsel]', 'XA');
    out.cc_xa = (h().match(/First session eCPM<\/div><div class="roi-kv">([^<]*)/) || [])[1];
    tap('[data-nvr-cc]', { nvrCc: '' });
    out.cc_all = [(h().match(/First session eCPM<\/div><div class="roi-kv">([^<]*)/) || [])[1], h().includes('chuna hai')];
    // ₹
    CUR = 'INR'; tap('[data-nvr-per]', { nvrPer: '30' });
    out.inr = (h().match(/First session eCPM<\/div><div class="roi-kv">([^<]*)<\/div><div class="roi-ks">([^<]*)/) || []).slice(1);
    CUR = 'USD';
    // a failed load: Try again
    for (const k of Object.keys(NVR._.AF)) delete NVR._.AF[k];
    FAIL = true; NVR.repaint(); await flush(); await flush();
    out.fail = h().includes('⚠️ First session vs Returning load nahi hua. <button type="button" class="roi-lnk" data-nvr-retry="1">Try again</button>');
    FAIL = false; tap('[data-nvr-retry]', {}); await flush(); await flush();
    out.retry = h().includes('First session eCPM');
    // a picked country's ad unit / format tables (owner, 3 Nov 2026): the app's "uc" shard holding the country (XA → 1,
    // XB → 2 of 8), loaded on the pick; XA whole (✓), XB a part only (⚠️ the share GA4 gave + the kept eCPM's gap),
    // days the country read has not reached counted, and no "uc" yet → said, the tables all countries'
    let QI = 1;                                            // XA's impressions in its shard ÷ this (revenue always whole)
    const shard = (n) => ({ v: 1, key: '000000000009', s: n, d0: D0, units: [['unit_open', 'App open'], ['unit_banner', 'Banner']],
      c: n === 1 ? { XA: [].concat(...Array.from({ length: 63 }, (_, i) => i === 10 ? [] : [[i, 0, 0, 0.6, 300 / QI], [i, 0, 1, 1, 1000 / QI], [i, 1, 0, 0.6, 300 / QI], [i, 1, 1, 1, 1000 / QI]])) }
        : n === 2 ? { XB: [].concat(...Array.from({ length: 63 }, (_, i) => i === 10 ? [] : [[i, 0, 0, 0.3, 50], [i, 0, 1, 0.25, 500]])) } : {} });
    const UCL = [];
    ctx.fetchGzJson = url => { UCL.push(url); const m = /^nvr_uc_000000000009_(\d)\.json\.gz/.exec(url);
      return Promise.resolve(m ? shard(+m[1]) : JSON.parse(JSON.stringify(F))); };
    const ptr = ctx.DATA.nvr.apps['id-x'];
    ptr.uc = { n: 8, files: Array.from({ length: 8 }, (_, i) => ['nvr_uc_000000000009_' + i + '.json.gz', 'u' + i]), from: D0, last: day(62),
      rd: [[0, 9], [11, 62]], bf: true, daily: false };
    const card = (t) => { const i = h().indexOf('<h3>' + t); return i < 0 ? '' : h().slice(i, h().indexOf('</table>', i) > 0 ? h().indexOf('</table>', i) : i + 600); };
    tap('[data-nvr-per]', { nvrPer: '30' }); tap('[data-nvr-cc]', { nvrCc: 'XA' });
    out.uc_loading = strip(card('Ad units'));
    await flush(); await flush();
    out.uc_xa = { units: strip(card('Ad units')), formats: strip(card('Ad formats')) };
    tap('[data-nvr-cc]', { nvrCc: 'XB' }); await flush(); await flush();
    out.uc_xb = strip(card('Ad units'));
    ptr.uc.rd = [[0, 9], [11, 40]]; NVR.repaint();
    out.uc_miss = strip(card('Ad units'));
    ptr.uc.rd = [[0, 9], [11, 62]];
    tap('[data-nvr-per]', { nvrPer: 'yday' }); out.uc_yday = strip(card('Ad units'));           // a recent day: not measured
    change('[data-nvr-pf]', '2026-08-01'); change('[data-nvr-pto]', '2026-08-20'); out.uc_before = strip(card('Ad units'));
    tap('[data-nvr-per]', { nvrPer: '30' });
    delete ptr.uc; NVR.repaint();
    out.uc_none = strip(card('Ad units'));
    out.uc_loads = UCL.filter(u => u.startsWith('nvr_uc_'));
    // revenue whole but a quarter of the impressions (GA4's one-day reads of this split): ⚠️, never ✓
    QI = 4; ptr.uc = { n: 8, files: Array.from({ length: 8 }, (_, i) => ['nvr_uc_000000000009_' + i + '.json.gz', 'w' + i]), from: D0, last: day(62),
      rd: [[0, 9], [11, 62]], bf: true };
    tap('[data-nvr-cc]', { nvrCc: 'XA' }); await flush(); await flush();
    out.uc_imps = strip(card('Ad units'));
    tap('[data-nvr-cc]', { nvrCc: '' });
  } catch (e) { errors.push(String(e && e.stack || e)); }
  console.log(JSON.stringify({ errors, out }));
})();
