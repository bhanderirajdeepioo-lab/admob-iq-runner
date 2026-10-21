// 📈 ROI (a section of 💸 Install value) — the page side, run for real: the ROI module + roiWrap of frontend/index.html (cut
// out by their markers) in a node vm with stub page helpers, on SYNTHETIC data made up here (no real names, ids or money):
//   * where the block goes (between the Value Studio and "🗂 Old views"; nothing without the pointer);
//   * Day-wise ROI: day-by-day columns when the exact store has them, the checkpoints for older days, past D30 every 30
//     days up to the oldest install day's age when the file has m (the late read; else 60 / 90 / 180 / 365), Today / Yesterday
//     only from the store's own today, week / month rows only when every day is complete, ROAS / revenue / per install /
//     delta cells, breakeven, the KPI tiles;
//   * Countries: decision chips, what cutting saves, sorting, a country's months;
//   * Lifetime P/L: totals only up to the day both sides are in, profit since, every month;
//   * All apps: every app with its icon, sorted Worse first; the hub card's ROI line;
//   * ⚖️ the four forms of ROI: the hero block (the payback-target age or the longest complete one, ranges from the
//     file's own consts, an age GA4 measured: its paid share + premium said so, the budget call, the organic-heavy /
//     mostly-organic warning, the help + paid share per install day), and the All-apps table (biggest blended-vs-paid
//     gap first, flagged rows, ✓ GA4 rows, spend-weighted total, ₹ as billed, sorting); a paused app (whatever its call)
//     out of the total and of the ⚖️ hero card, "✓ GA4" only where GA4 measured, the premium range's own age named;
//   * 🧮 the cohort card's totals strip, two groups ("Spend pata wale din": Revenue − Spend = Profit over ONE set of days;
//     "Poori history"): All / a country (Unknown, Not split), the owner's case in its shape, loading / error / missing, ₹ /
//     $, its skeleton the same in every state;
//   * "Show 60 more" / "Show all" (the install-day tables and the lifetime "Every day" table): on a parsed DOM with a layout
//     model + the page's own stay-put layer, the reader's row stays put, the box keeps its scroll, no second scroll;
//     sideways by column (the Day table's columns change with the rows shown), and a Mode switch keeps the box's place too.
// Prints ONE JSON report; tests/test_roi_frontend.py asserts on it.   usage: node roi_frontend.js <index.html>
'use strict';
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const END = '</details>`; }', a = html.indexOf('const ROI=(()=>{'), b = html.indexOf(END, html.indexOf('function roiWrap(html,aid)')) + END.length - 1;
const c0 = html.indexOf('function roiCardLine(x,name)'), c1 = html.indexOf('function hubCardsPaint(){');
const out = {}, errors = [];
if (a < 0 || b < 0 || c0 < 0) { console.log(JSON.stringify({ errors: ['ROI module not found'] })); process.exit(0); }
const src = html.slice(a, b + 1) + html.slice(c0, c1) + '\nthis.ROI=ROI;this.roiWrap=roiWrap;this.roiCardLine=roiCardLine;';
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, Promise, isFinite, encodeURIComponent, Error, Date, parseFloat,
  DATA: null, document: undefined, window: {},
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1]; },
  fmtMon: k => MON[+String(k).slice(5, 7) - 1] + ' ' + String(k).slice(0, 4),
  hubStChip: k => `<span class="hub-st st-${k}">${k}</span>`,
  appIconId: (id, name, size) => `<span class="aicon" data-iid="${id}"></span>`,
  uniVis: id => id !== 'id-hidden', valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Country ' + cc,
  csym: () => '$', cfx: () => 1, curView: () => 'USD', setApp: () => {}, hubAppId: n => ({ 'Alpha Pick': 'id-a' })[n] || '',
  fetchGzJson: () => Promise.reject(new Error('no file in this test')),
};
const CTX0 = Object.assign({}, ctx);                     // the stubs as made (a fresh module: the default digest)
vm.createContext(ctx);
const T = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365];
const iso = d => d.toISOString().slice(0, 10);
const day = (s, n) => { const d = new Date(s + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
// an app file: 70 install days to 13 Oct; the newest 40 with day-by-day revenue ($1 a day, spend $10)
function appFile() {
  const rows = [], newest = '2026-10-13';
  for (let i = 69; i >= 0; i--) {
    const X = day(newest, -i), age = i, exact = i < 40;
    const obs = Math.min(30, age), df = Math.max(0, Math.min(obs, age - 3) + 1);
    const d = exact ? Array.from({ length: obs + 1 }, (_, L) => L + 1) : null;
    const t = T.map(a => (a <= age - 3 ? (exact && a <= 30 ? a + 1 : a + 1) : null));
    rows.push([X, 100, 80, 10, d, exact ? df : 0, exact ? d.map(() => 50) : null, t, d ? d[d.length - 1] : t.filter(v => v != null).pop(), X,
      (exact && df > 9) ? [9, true] : null, age >= 10 ? 'Normal' : 'Too early', 0]);
  }
  return { v: 1, app: 'Alpha File', T, lags: 31, newest, S: '2026-10-07', rows,
    months: [['2026-08', 1000, 100, [10, 20, 40, 80, null, null, null, null, null, null], 10, 10],
             ['2026-09', 3000, 300, [30, 60, 120, 240, 450, null, null, null, null, null], 30, 30]],
    sum: { st: 'Watch', r7: 0.4, u7: 0.5, pb: 12, pbm: '2026-09', best: [14, 1.5, '2026-09'], cpi: 0.1,
      pools: { '0': { r: { roas: 0.1 }, u: { roas: 0.12 } }, '7': { r: { roas: 0.4 }, u: { roas: 0.5 } } },
      ret: { '1': { r: 0.3, u: 0.35 } }, cov: 0.8, tie: { checked: 30, off: 1 }, today: rows.slice(-2) },
    life: [['2026-09-29', 5, 20], ['2026-09-30', 30, 5], ['2026-10-01', 10, 5], ['2026-10-02', 1, 50]],
    life_till: '2026-10-01',
    cty: { win: { weeks: 4, from: '2026-09-07', to: '2026-10-04' }, H: 90,
      cut: { n: 1, spend: 400, rev90: 100, spend_all: 1000 },
      rows: [{ cc: 'AA', dec: 'Keep', n: 500, share: 0.5, spend: 300, cpi: 0.6, back: { '7': 50, '30': 90, '90': 120 }, pay: { p: 60, lo: 40, hi: 80 }, ret: { d1: 30 } },
             { cc: 'BB', dec: 'Cut', n: 300, share: 0.3, spend: 400, cpi: 1.3, back: { '7': 10, '30': 15, '90': 25 }, pay: { never: true }, ret: { d1: 20 } },
             { cc: 'CC', dec: 'Scale', n: 200, share: 0.2, spend: 300, cpi: 1.5, back: { '7': 80, '30': 140, '90': 200 }, pay: { p: 20, obs: true }, ret: {} }],
      months: { AA: [['2026-08', 100, 50, 90, 0.4, 0.8, null, 4, 4, 4, 0], ['2026-09', 200, 100, 180, 0.5, null, null, 5, 5, 2, 0]] } },
    consts: { n_recent: 7, n_usual: 28, final_lag: 3 } };
}
// the late read's file: 230 install days to 13 Oct, the newest 40 day by day; a row ≥ 60 days old has m = its revenue at
// D60, D90 … (one more each 30 days of age), final while ≥ 3 days old
function lateFile() {
    const rows = [], newest = '2026-10-13';
    for (let age = 229; age >= 0; age--) {
      const X = day(newest, -age), exact = age < 40, obs = Math.min(30, age), df = Math.max(0, Math.min(obs, age - 3) + 1);
      const dd = exact ? Array.from({ length: obs + 1 }, (_, L) => L + 1) : null;
      const t = T.map(a => (a <= age - 3 ? a + 1 : null));
      const r = [X, 100, 80, 50, dd, exact ? df : 0, exact ? dd.map(() => 50) : null, t, null, X, null, 'Normal', age === 100 ? 2 : 0, 4000];
      const nm = Math.floor(age / 30) - 1;
      if (nm > 0) { r.push(Array.from({ length: nm }, (_, k) => 31 + 10 * (k + 1)), Array.from({ length: nm }, (_, k) => k).filter(k => 30 * (k + 2) <= age - 3).length); r[8] = r[14][nm - 1]; }
      if (age === 150) r[10] = [120, false];                                     // breakeven in a 30-day column
      rows.push(r);
    }
    return { v: 1, app: 'Late File', T, lags: 31, newest, S: '2026-10-07', rows, months: [], sum: { today: rows.slice(-2), pools: {} },
      late: { days: 200, oth: 3, omax: 0.025, from: '2026-03-28', till: newest }, consts: { final_lag: 3 } };
}
// the default view's digest: a FRESH module (nothing picked, nothing toggled), both made-up files, every grain × mode, the
// Day view and the Countries board — GOLDEN_DEFAULT. 🎯 The Breakeven column moved next to CPI (21 Oct 2026): the
// digest changed on purpose; [1] = the same parts with the Breakeven column (its <th>, each row's breakeven cell) and its
// note cut out — GOLDEN_NO_BE, worked out on the page BEFORE the move (its far-right cell cut): nothing else changed
// (the two later changes below are cut out of [1] too: the strip by kpiCut, the rows' key by noK inside beStrip).
// The rows' key (data-roi-k, added 21 Oct 2026 so "Show 60 more" / "Show all" keep the reader's row): noK cuts it out;
// [4] = every part with the key cut (the strip stays) = GOLDEN_DEFAULT_NOK, the page before the key byte for byte
const noK = s => s.replace(/<tr data-roi-k="[^"]*">/g, '<tr>');
function beStrip(s) {
  return noK(s).replace(/<p class="roi-note"><b>Breakeven<\/b>[^]*?<\/p>/g, '')
    .replace(/<table class="roi-t roi-heat">[^]*?<\/table>/g, t => t.replace('<th>Breakeven</th>', '')
      .replace(/<tr><td class="roi-nm">[^]*?<\/tr>/g, tr => { const tds = tr.slice(4, -5).split('</td>').slice(0, -1);
        tds.splice(5, 1); return '<tr>' + tds.map(x => x + '</td>').join('') + '</tr>'; }));
}
// 🧮 the cohort card's totals strip (21 Oct 2026): it sits between the card's title row and its control row, i.e. right
// before what cohortTable returns (its "top" line or its control row). kpiCut = the page without it; [2] of the digest =
// every part with the strip cut out (the key stays) = GOLDEN_DEFAULT_NOKPI; [3] = how many parts carry the strip;
// [5] = both cut (strip + key) = GOLDEN_PRE_KPI, the page before both byte for byte (nothing else moved by a byte)
const KPI_RE = /<div class="roi-cks"[^]*?(?=<p class="roi-note roi-ccm0">|<div class="roi-ctl">)/g;
const kpiCut = s => s.replace(KPI_RE, '');
function defaultDigest() {
  const c3 = Object.assign({}, CTX0, { DATA: null, window: {} });
  vm.createContext(c3);
  vm.runInContext(src, c3);
  const U = c3.ROI._, crypto = require('crypto'), h = x => crypto.createHash('sha256').update(x).digest('hex');
  const d0 = appFile(), dm = lateFile(), parts = [];
  for (const g of ['day', 'week', 'month']) for (const m of ['roas', 'rev', 'ltv', 'delta']) {
    U.set('GRAIN', g); U.set('MET', m); parts.push(U.cohortTable(d0), U.cohortTable(dm)); }
  U.set('GRAIN', 'day'); U.set('MET', 'roas');
  parts.push(U.dayView(d0), U.dayView(dm), U.ctyView(d0));
  U.set('SHOW', 1e9); parts.push(U.cohortTable(dm));
  return [h(parts.join('\u0001')), h(parts.map(x => beStrip(kpiCut(x))).join('\u0001')), h(parts.map(kpiCut).join('\u0001')),
    parts.filter(x => x.includes('<div class="roi-cks"')).length, h(parts.map(noK).join('\u0001')),
    h(parts.map(x => noK(kpiCut(x))).join('\u0001'))];
}
// No page jump (owner: "kuchh change karte he to upar chala jata he page"): the ROI block in a FRESH module on a small
// made-up DOM whose layout is the page's own markup — an element's document top = its offset in the block's HTML × a
// line factor (a narrow phone: taller), the window scrolls over it. A tap / a list change / "✕ All countries" / the
// Countries board's "📅 Day-wise" goes through the real listeners; the tapped control (or what it opens) must stay where
// it was on screen, before and after its pack arrives. → [moves in px …] (0 = stayed).
async function noJump(width, file, packs, failOnce, mode) {
  const failed = new Set();
  const k = 0.05 * 1280 / width, W = { scrollY: 0, innerWidth: width, scrollBy(x, y) { this.scrollY = Math.max(0, this.scrollY + y); } };
  const L = {};
  const P = { hero: '', body: '' };
  let HD = '';                                                              // the view tabs (the block's own header)
  // 🧮 the totals strip above the chips is ONE height in every state (CSS: one-line values, two-line subs, fixed group heads
  // + coverage line, a note that never changes — pinned in test_roi_frontend.py, its skeleton the same in every state
  // below): one fixed-size block here
  const full = () => '<section id="roi-root"><div id="roi-hero">' + P.hero + '</div>' + HD + '<div id="roi-body">'
    + P.body.replace(KPI_RE, '<div class="roi-cks">' + '.'.repeat(400) + '</div>') + '</div></section>';
  const attrs = tag => { const a = {}; for (const m of tag.matchAll(/([a-zA-Z0-9:-]+)="([^"]*)"/g)) a[m[1]] = m[2]; return a; };
  const find = sel => {
    const H = full(); let i = -1, m;
    if ((m = /^#([\w-]+) (\w+)$/.exec(sel))) { const j = H.indexOf(`id="${m[1]}"`); i = j < 0 ? -1 : H.indexOf('<' + m[2], j); }
    else if ((m = /^#([\w-]+)$/.exec(sel))) { const j = H.indexOf(`id="${m[1]}"`); i = j < 0 ? -1 : H.lastIndexOf('<', j); }
    else if ((m = /^\[([\w-]+)="([^"]*)"\]$/.exec(sel))) { const j = H.indexOf(` ${m[1]}="${m[2]}"`); i = j < 0 ? -1 : H.lastIndexOf('<', j); }
    else if ((m = /^\[([\w-]+)\]$/.exec(sel))) { const j = H.search(new RegExp(` ${m[1]}(=|>| )`)); i = j < 0 ? -1 : H.lastIndexOf('<', j); }
    else return null;
    if (i < 0) return null;
    return el(i, H.slice(i, H.indexOf('>', i) + 1));
  };
  const el = (i, tag) => {
    const a = attrs(tag), ds = {};
    for (const [n, v] of Object.entries(a)) if (n.startsWith('data-')) ds[n.slice(5).replace(/-([a-z])/g, (x, c) => c.toUpperCase())] = v;
    const e = { _i: i, dataset: ds, value: a.value || '', style: {},
      getAttribute: n => a[n] == null ? null : a[n], setAttribute: (n, v) => { a[n] = String(v); },
      getBoundingClientRect: () => ({ top: e._i * k - W.scrollY, left: 0, width: 10, height: 10 }),
      closest: sel => sel === '#roi-root' ? ROOT : matches(sel) ? e : null };
    const matches = sel => { let m;
      if ((m = /^\[([\w-]+)\]$/.exec(sel))) return a[m[1]] != null;
      if ((m = /^\[([\w-]+)="([^"]*)"\]$/.exec(sel))) return a[m[1]] === m[2];
      return false; };
    return e;
  };
  const SETS = { body: 0, hero: 0 };                                       // how often the block was painted
  const box = key => ({ set innerHTML(v) { P[key] = v; SETS[key]++; }, get innerHTML() { return P[key]; } });
  const ROOT = { dataset: { aid: 'id-c' }, style: {}, get offsetHeight() { return full().length * k; },
    getBoundingClientRect: () => ({ top: -W.scrollY, left: 0, width: width, height: full().length * k }),
    querySelector: sel => sel === '#roi-body' ? box('body') : sel === '#roi-hero' ? box('hero') : sel === '.roi-tip' ? null : find(sel),
    querySelectorAll: sel => { const H = full(), out_ = []; if (sel !== '[data-roi-view]') return out_;
      for (const m of H.matchAll(/<button[^>]* data-roi-view="[^"]*"[^>]*>/g)) out_.push(el(m.index, m[0])); return out_; } };
  const doc = { addEventListener: (t, f) => { (L[t] = L[t] || []).push(f); }, getElementById: id => id === 'roi-root' ? ROOT : null };
  const c = Object.assign({}, CTX0, { document: doc, window: W, setTimeout, DATA: { roi: { file: 'roi.json.gz', v: 'v1', apps: { 'id-c': { file: 'roi_cccccccccccc.json.gz', st: 'Watch' } } } },
    fetchGzJson: u => new Promise((ok_, no) => setTimeout(() => { const f = u.split('?')[0];
      if ((failOnce || []).includes(f) && !failed.has(f)) { failed.add(f); return no(new Error('x')); }
      return packs[f] ? ok_(JSON.parse(JSON.stringify(packs[f]))) : no(new Error('x')); }, 0)) });
  vm.createContext(c);
  vm.runInContext(src, c);
  const R = c.ROI, U = R._;
  U.data().AF['roi_cccccccccccc.json.gz'] = Object.assign(JSON.parse(JSON.stringify(file)), { _v: 'v1' });
  R.block('id-c');                                                          // wires the listeners
  const I = U.inner('id-c');
  HD = I.slice(I.indexOf('<div class="roi-hd">'), I.indexOf('<div id="roi-body">'));
  R.repaint();
  const flush = () => new Promise(r => setTimeout(r, 5));
  const fire = (t, e) => (L[t] || []).forEach(f => f(Object.assign({ clientX: 0, clientY: 0 }, e)));
  const moves = [];
  if (mode === 'late') {                                                    // a pack that lands after the reader moved on:
    fire('click', { target: find('[data-roi-cc="AA"]') }); await flush();   // AA's pack in hand
    const sel = find('[data-roi-ccs]'); sel.value = 'GG'; fire('change', { target: sel });   // GG: its pack on its way…
    fire('click', { target: find('[data-roi-cc="AA"]') });                  // … AA again at once (its table from memory)
    const n0 = SETS.body, aaNow = P.body.includes('[AA] Country AA</h3>');
    await flush();                                                          // GG's pack lands: the AA table is not painted again
    return { late: [aaNow, SETS.body - n0, P.body.includes('[AA] Country AA</h3>')] };
  }
  const tap = async (sel, after, ev) => {                                  // a control mid-screen; where it is after
    let b = find(sel); W.scrollY = Math.max(0, b._i * k - 300); b = find(sel); const y0 = b.getBoundingClientRect().top;
    if (ev) { b.value = ev; fire('change', { target: b }); } else fire('click', { target: b });
    let a = find(after || sel); moves.push(a ? Math.round(a.getBoundingClientRect().top - y0) : 'gone');
    await flush();                                                         // its pack arrives: nothing above moves
    a = find(after || sel); moves.push(a ? Math.round(a.getBoundingClientRect().top - y0) : 'gone');
  };
  await tap('[data-roi-cc="AA"]');                                          // a chip: the title grows above it
  await tap('[data-roi-grain="week"]');                                     // the grain keeps the country
  const keptWeek = P.body.includes('[AA] Country AA</h3>');
  await tap('[data-roi-grain="day"]');
  await tap('[data-roi-ccs]', null, 'GG');                                  // the full list (another pack)
  const h3 = find('#roi-coh h3'), y3 = h3.getBoundingClientRect().top;
  fire('click', { target: find('[data-roi-ccx]') });                        // ✕ All countries: the title row stays
  moves.push(Math.round(find('#roi-coh h3').getBoundingClientRect().top - y3));
  const backAll = !P.body.includes('✕ All countries') && U.getCTY() === '';
  fire('click', { target: find('[data-roi-view="cty"]') });                 // 🌍 Countries → "📅 Day-wise" of BB
  await tap('[data-roi-pick="BB"]', '#roi-coh');
  const picked = U.getCTY() === 'BB' && P.body.includes('[BB] Country BB</h3>');
  // a pack that does not load: "Try again" in the table area reads it again (and only then)
  await tap('[data-roi-cc="EE"]');
  const errShown = P.body.includes('data-roi-ccr="1">Try again') && P.body.includes('[EE] Country EE ka data load nahi hua');
  fire('click', { target: find('[data-roi-ccr]') });
  await flush();
  const retried = P.body.includes('[EE] Country EE</h3>') && !P.body.includes('Try again') && /<td class="roi-[gwb]/.test(P.body);
  return { moves, keptWeek, backAll, picked, errShown, retried };
}
// ── "Show 60 more" / "Show all" keep the reader's row (owner, 21 Oct 2026: "show 60 more krte he to table pehle se scroll
// hoke uppar se start hota he") ───────────────────────────────────────────────────────────────────────────────────────
// The ROI block (a FRESH module) + the page's own stay-put layer (SP, cut out of the page as tests/stayput_frontend.js does)
// in one vm, on a small DOM PARSED from the block's own markup and laid out by a model: blocks stack, text wraps at the
// width, a body row is 31px (on a phone taller when its first cell wraps: max-width 150px), a .roi-tw box is at most 640px
// high and scrolls on its own, down and sideways (a new box starts at 0, 0, as in a browser); the page scrolls over it all;
// a table's columns are as wide as their widest cell, side by side, the first one sticky at the box's left.
// The reader scrolls the page to the table, the box down near its end and sideways, then taps "Show 60 more" / "Show all":
// pointerdown, then click through window capture (SP) → the block's listener → window bubble (SP), then SP's microtask,
// frames and 0 / 150 / 400 ms checks. Per tap: how far the reader's row (the last one in sight, found by its own label —
// never by the page's key, so the page before this fix is measured the same way) moved on screen, the box's scrollLeft
// before / after, how far the page scrolled and how many scroll calls ran, the rows before / after; sideways: the column
// under the box's visible right edge (by its header) and its x before / after, the right end before / after. A Mode
// button (ROAS % / Revenue / …) the same way: the page at its row, the box half way down.
const SPSRC = (() => { const a = html.indexOf('const SP=(function(){'), b = html.indexOf('\n  return api;\n})();', a);
  return a < 0 || b < 0 ? null : html.slice(a, b + '\n  return api;\n})();'.length); })();
function miniDom(VW, VH) {
  const phone = VW <= 760, W = { y: 0, docH: 0, calls: 0 }, WL = { cap: {}, bub: {} }, DL = {};
  const INL = new Set(['SPAN', 'B', 'I', 'SMALL', 'A', 'BUTTON', 'EM', 'STRONG', 'LABEL', 'SELECT', 'OPTION', 'OPTGROUP', 'INPUT', 'BR', 'IMG', 'CODE', 'SUP', 'SUB', 'U', 'S', 'MARK', 'TIME', 'ABBR', 'WBR']);
  const VOID = new Set(['BR', 'IMG', 'INPUT', 'HR', 'META', 'LINK', 'WBR', 'COL', 'SOURCE', 'AREA', 'BASE', 'EMBED', 'PARAM', 'TRACK']);
  let dirty = true, DOC = null;
  const hooks = { set: null };                                         // a test hook on innerHTML (content above grows)
  class Txt { constructor(t) { this.nodeType = 3; this.data = t; this.parentElement = null; } get textContent() { return this.data; } }
  const SELC = new Map();
  function compound(s) {
    const re = /([a-zA-Z][a-zA-Z0-9]*)|(\*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]/y, ps = []; let pos = 0;
    while (pos < s.length) { re.lastIndex = pos; const m = re.exec(s); if (!m) throw new Error('selector not modelled: ' + s); ps.push(m); pos = re.lastIndex; }
    return e => ps.every(m => m[2] ? true : m[1] ? e.tagName === m[1].toUpperCase() : m[3] ? e.getAttribute('id') === m[3] : m[4] ? e.classList.contains(m[4])
      : (v => v != null && (m[6] === undefined || v === m[6]))(e.getAttribute(m[5])));
  }
  function compile(sel) {
    let f = SELC.get(sel); if (f) return f;
    const alts = sel.split(',').map(s => s.trim().split(/\s+/).map(compound));
    f = e => alts.some(ch => { let i = ch.length - 1; if (!ch[i](e)) return false; i--;
      for (let x = e.parentElement; i >= 0 && x; x = x.parentElement) if (ch[i](x)) i--; return i < 0; });
    SELC.set(sel, f); return f;
  }
  const walk = (e, fn) => { for (const c of e.childNodes) if (c.nodeType === 1) { fn(c); walk(c, fn); } };
  class El {
    constructor(tag, at) { this.tagName = tag; this.nodeType = 1; this._a = at || []; this.childNodes = []; this.parentElement = null; this.style = {}; this._st = 0; this._sl = 0; this._L = null; }
    get children() { return this.childNodes.filter(n => n.nodeType === 1); }
    get attributes() { return this._a.map(([name, value]) => ({ name, value })); }
    getAttribute(k) { const x = this._a.find(p => p[0] === k); return x ? x[1] : null; }
    hasAttribute(k) { return this.getAttribute(k) != null; }
    setAttribute(k, v) { const x = this._a.find(p => p[0] === k); if (x) x[1] = String(v); else this._a.push([k, String(v)]); dirty = true; }
    removeAttribute(k) { this._a = this._a.filter(p => p[0] !== k); dirty = true; }
    get id() { return this.getAttribute('id') || ''; }
    get classList() { const c = String(this.getAttribute('class') || '').split(/\s+/).filter(Boolean); return { contains: x => c.includes(x) }; }
    get dataset() { const d = {}; for (const [k, v] of this._a) if (k.startsWith('data-')) d[k.slice(5).replace(/-([a-z])/g, (m, ch) => ch.toUpperCase())] = v; return d; }
    get hidden() { return this.hasAttribute('hidden'); }
    set hidden(v) { if (v) this.setAttribute('hidden', ''); else this.removeAttribute('hidden'); }
    get type() { return this.getAttribute('type') || ''; }
    get value() { return this.getAttribute('value') || ''; }
    get isContentEditable() { return false; }
    get textContent() { return this.childNodes.map(n => n.textContent).join(''); }
    get previousElementSibling() { const p = this.parentElement; if (!p) return null; const c = p.children, i = c.indexOf(this); return i > 0 ? c[i - 1] : null; }
    append(n) { n.parentElement = this; this.childNodes.push(n); dirty = true; return n; }
    get innerHTML() { return ''; }
    set innerHTML(h) { if (hooks.set) h = hooks.set(this, h); this.childNodes.forEach(n => { n.parentElement = null; }); this.childNodes = []; parse(h).forEach(n => this.append(n)); dirty = true; }
    contains(x) { for (; x; x = x.parentElement) if (x === this) return true; return false; }
    get isConnected() { let x = this; while (x.parentElement) x = x.parentElement; return x === DOC; }
    matches(sel) { return compile(sel)(this); }
    closest(sel) { const f = compile(sel); for (let x = this; x; x = x.parentElement) if (f(x)) return x; return null; }
    querySelectorAll(sel) { const f = compile(sel), out = []; walk(this, e => { if (f(e)) out.push(e); }); return out; }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
    getElementsByTagName(t) { const T = String(t).toUpperCase(), out = []; walk(this, e => { if (T === '*' || e.tagName === T) out.push(e); }); return out; }
    get nextElementSibling() { const p = this.parentElement; if (!p) return null; const c = p.children, i = c.indexOf(this); return i >= 0 && i < c.length - 1 ? c[i + 1] : null; }
    getBoundingClientRect() { lay(); const L = this._L;
      if (!L || !this.isConnected) return { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 };
      // inside a box that scrolls on its own: down always; sideways unless a table's first column (sticky left:0)
      let top = L.top - W.y, left = L.x || 0; const w = L.box ? L.cw : L.w != null ? L.w : 100;
      if (L.bx) { top -= L.bx.scrollTop; if (!L.stk) left -= L.bx.scrollLeft; }
      return { top, bottom: top + L.h, left, right: left + w, width: w, height: L.h }; }
    get offsetHeight() { lay(); return this._L ? this._L.h : 0; }
    get scrollHeight() { lay(); const L = this._L; return L ? (L.box ? L.ch : L.h) : 0; }
    get clientHeight() { lay(); return this._L ? this._L.h : 0; }
    get scrollWidth() { lay(); const L = this._L; return L ? (L.box ? L.sw : L.w || 0) : 0; }
    get clientWidth() { lay(); const L = this._L; return L ? (L.box ? L.cw : L.w || 0) : 0; }
    get scrollTop() { lay(); const L = this._L; return L && L.box ? Math.max(0, Math.min(this._st, L.ch - L.h)) : 0; }
    set scrollTop(v) { lay(); const L = this._L; this._st = L && L.box ? Math.max(0, Math.min(+v || 0, L.ch - L.h)) : 0; }
    get scrollLeft() { lay(); const L = this._L; return L && L.box ? Math.max(0, Math.min(this._sl, L.sw - L.cw)) : 0; }
    set scrollLeft(v) { lay(); const L = this._L; this._sl = L && L.box ? Math.max(0, Math.min(+v || 0, L.sw - L.cw)) : 0; }
    scrollIntoView() {}
    focus() {}
  }
  function parse(h) {
    const root = new El('#F'), st = [root];
    const re = /<!--[^]*?-->|<(\/?)([a-zA-Z][a-zA-Z0-9]*)((?:[^>"']|"[^"]*"|'[^']*')*)>|([^<]+)/g; let m;
    while ((m = re.exec(h))) {
      if (m[4] !== undefined) { st[st.length - 1].append(new Txt(m[4])); continue; }
      if (!m[2]) continue;
      const tag = m[2].toUpperCase();
      if (m[1]) { for (let i = st.length - 1; i > 0; i--) if (st[i].tagName === tag) { st.length = i; break; } continue; }
      const at = [], ar = /([^\s="'\/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g, self = /\/\s*$/.test(m[3]); let a;
      while ((a = ar.exec(m[3].replace(/\/\s*$/, '')))) at.push([a[1], a[2] ?? a[3] ?? a[4] ?? '']);
      const e = new El(tag, at); st[st.length - 1].append(e);
      if (!VOID.has(tag) && !self) st.push(e);
    }
    return root.childNodes.slice();
  }
  // ── the layout model ──
  const flat = (e, y, h, bx) => { e._L = { top: y, h, bx }; walk(e, k => { k._L = { top: y, h: 0, bx }; }); };
  const tlen = e => e.textContent.replace(/\s+/g, ' ').trim().length;
  function inl(e, y, bx) { e._L = { top: y, h: 18, bx }; let n = e.tagName === 'BUTTON' ? 4 : 0;
    for (const c of e.childNodes) n += c.nodeType === 3 ? c.data.replace(/\s+/g, ' ').length : inl(c, y, bx); return n; }
  // a table: every column as wide as its widest cell (a cell: 7px a character + 20; the first column at most 150px on a
  // phone, the others at least 48px), cells side by side from x 0; the first column sticks at the box's left (left:0)
  const cellW = (c, i) => { const n = tlen(c); return i === 0 ? (phone ? Math.min(150, n * 7 + 20) : n * 7 + 20) : Math.max(48, n * 7 + 20); };
  function tbl(t, y, aw, bx) {
    const L = t._L = { top: y, h: 0, bx }; let cy = y;
    const trsOf = s => (s.tagName === 'TR' ? [s] : s.children.filter(r => r.tagName === 'TR'));
    const span = cs => cs.length === 1 && cs[0].getAttribute('colspan');
    const cw = []; for (const s of t.children) for (const tr of trsOf(s)) { const cs = tr.children; if (!span(cs)) cs.forEach((c, i) => { cw[i] = Math.max(cw[i] || 0, cellW(c, i)); }); }
    const cx = []; let tw = 0; cw.forEach((w, i) => { cx[i] = tw; tw += w; });
    for (const s of t.children) { s._L = { top: cy, h: 0, bx };
      for (const tr of trsOf(s)) {
        const cs = tr.children, head = s.tagName === 'THEAD'; let rh = head ? 36 : 31;
        if (span(cs)) rh = 16 + Math.ceil(tlen(cs[0]) * 7 / Math.max(120, aw - 20)) * 18;
        else if (phone && cs[0]) rh += (Math.max(1, Math.ceil(tlen(cs[0]) * 7 / 130)) - 1) * 16;   // the first column wraps at 150px
        tr._L = { top: cy, h: rh, bx, w: tw };
        cs.forEach((c, i) => { flat(c, cy, rh, bx); Object.assign(c._L, span(cs) ? { x: 0, w: tw } : { x: cx[i], w: cw[i], stk: i === 0 }); });
        cy += rh; }
      s._L.h = cy - s._L.top; }
    L.w = Math.max(t.classList.contains('roi-sub') ? 560 : 640, tw); return (L.h = cy - y);
  }
  function blk(e, y, aw, bx) {
    const L = e._L = { top: y, h: 0, bx };
    if (e.hasAttribute('hidden')) { flat(e, y, 0, bx); return 0; }
    if (e.tagName === 'SVG') { flat(e, y, 240, bx); return 240; }
    if (e.tagName === 'TABLE') return tbl(e, y, aw, bx);
    const box = e.tagName === 'DIV' && e.classList.contains('roi-tw'), kb = box ? e : bx;
    const pad = e.classList.contains('roi-card') ? (phone ? 12 : 16) : 0, iw = Math.max(60, aw - 2 * pad);
    let cy = y + pad, run = 0;
    const flush = () => { if (run) cy += Math.ceil(run * 7 / iw) * 20; run = 0; };
    for (const c of e.childNodes) {
      if (c.nodeType === 3) { const t = c.data.replace(/\s+/g, ' '); if (t.trim()) run += t.length; continue; }
      if (INL.has(c.tagName)) { run += inl(c, cy + Math.floor(run * 7 / iw) * 20, kb); continue; }
      flush(); cy += blk(c, cy, iw, kb) + 6; }
    flush(); cy += pad;
    let h = cy - y; const mh = parseFloat(e.style.minHeight) || 0; if (mh > h) h = mh;
    if (box) { L.box = true; L.ch = h; L.h = Math.min(640, h); L.cw = iw; L.sw = e.getElementsByTagName('TABLE').reduce((s, t) => Math.max(s, t._L.w), iw); return L.h; }
    return (L.h = h);
  }
  const clampY = y => Math.max(0, Math.min(y, Math.max(0, W.docH - VH)));
  function lay() { if (!dirty || !DOC) return; dirty = false;
    W.docH = blk(DOC.getElementsByTagName('BODY')[0], 0, phone ? VW - 32 : Math.min(VW - 260, 1180), null); W.y = clampY(W.y); }
  const win = {
    get scrollY() { return W.y; }, get pageYOffset() { return W.y; }, innerWidth: VW, innerHeight: VH,
    scrollTo(x, y) { lay(); W.calls++; W.y = clampY(+((x && typeof x === 'object') ? x.top : y) || 0); },
    scrollBy(x, y) { lay(); W.calls++; W.y = clampY(W.y + (+((x && typeof x === 'object') ? x.top : y) || 0)); },
    scroll(x, y) { win.scrollTo(x, y); },
    addEventListener(t, f, o) { const s = (o === true || !!(o && o.capture)) ? WL.cap : WL.bub; (s[t] = s[t] || []).push(f); },
  };
  const doc = {
    get body() { return DOC.getElementsByTagName('BODY')[0]; },
    get documentElement() { lay(); return { scrollHeight: W.docH, clientHeight: VH }; },
    getElementById: id => DOC.querySelector('#' + id), querySelector: s => DOC.querySelector(s), querySelectorAll: s => DOC.querySelectorAll(s),
    addEventListener: (t, f) => { (DL[t] = DL[t] || []).push(f); },
  };
  const gcs = e => ({ position: 'static', top: 'auto', overflowY: e.classList && e.classList.contains('roi-tw') ? 'auto' : 'visible' });
  // an event the way a browser runs it: window capture → the document's listeners (the ROI block) → window bubble
  const fire = (type, target) => { const e = { type, target, clientX: 0, clientY: 0, isTrusted: true, key: '', preventDefault() {}, stopPropagation() {} };
    (WL.cap[type] || []).forEach(f => f(e)); (DL[type] || []).forEach(f => f(e)); (WL.bub[type] || []).forEach(f => f(e)); };
  return { El, win, doc, gcs, fire, W, lay, hooks, setDoc: h => { DOC = new El('#DOC'); parse(h).forEach(n => DOC.append(n)); dirty = true; }, q: s => DOC.querySelector(s) };
}
// ~5½ years of install days, one every 6 days: Day 334 rows, Week ~286, Month 66 — each past 60. mFrom: the late read
// (month columns past D30) only on install days at least that old — the newest 60 then have none, so the Day table's
// columns past D30 change with the rows shown (60: T's D60 D90 D180 D365; 120 on: D60 … D390 — D365 gone)
function longFile(mFrom) {
  const rows = [], newest = '2026-10-13';
  for (let age = 1998; age >= 0; age -= 6) {
    const X = day(newest, -age), exact = age < 40, obs = Math.min(30, age), df = Math.max(0, Math.min(obs, age - 3) + 1);
    const dd = exact ? Array.from({ length: obs + 1 }, (_, L) => L + 1) : null;
    const t = T.map(a => (a <= age - 3 ? a + 1 : null));
    const r = [X, 100, 80, 50, dd, exact ? df : 0, exact ? dd.map(() => 50) : null, t, null, X, null, 'Normal', age === 120 ? 2 : 0, 4000];
    const nm = age >= (mFrom || 0) ? Math.min(12, Math.floor(age / 30) - 1) : 0;
    if (nm > 0) { r.push(Array.from({ length: nm }, (_, k) => 31 + 10 * (k + 1)), Array.from({ length: nm }, (_, k) => k).filter(k => 30 * (k + 2) <= age - 3).length); r[8] = r[14][nm - 1]; }
    rows.push(r);
  }
  const life = []; for (let i = 199; i >= 0; i--) life.push([day(newest, -i), 5 + (i % 7), 4 + (i % 5)]);
  return { v: 1, app: 'Long File', T, lags: 31, newest, S: '2026-10-07', rows, months: [], sum: { today: rows.slice(-2), pools: {} },
    life, life_till: day(newest, -1), late: { days: 200, from: '2021-04-23', till: newest }, consts: { final_lag: 3 } };
}
// one vm per (width, file): the block painted inside a screen (made-up text above and below it), the reader's taps
async function keepHarness(VW, file, packs) {
  const VH = VW <= 760 ? 740 : 900, D = miniDom(VW, VH), Q = { t: [], raf: [], now: 0, n: 0 };
  const c = Object.assign({}, CTX0, { document: D.doc, window: D.win, Element: D.El, HTMLElement: D.El, getComputedStyle: D.gcs,
    setTimeout: (f, ms) => { Q.t.push({ at: Q.now + (ms || 0), f, n: Q.n++ }); return Q.n; }, requestAnimationFrame: f => { Q.raf.push(f); return Q.raf.length; },
    DATA: { roi: { file: 'roi.json.gz', v: 'v1', apps: { 'id-c': { file: 'roi_cccccccccccc.json.gz', st: 'Watch' } } } },
    fetchGzJson: u => { const f = u.split('?')[0]; return packs && packs[f] ? Promise.resolve(JSON.parse(JSON.stringify(packs[f]))) : Promise.reject(new Error('x')); } });
  vm.createContext(c);
  vm.runInContext(SPSRC + '\n' + src + '\nthis.__SP=SP;', c);
  const R = c.ROI, U = R._, SP = c.__SP;
  U.data().AF['roi_cccccccccccc.json.gz'] = Object.assign(JSON.parse(JSON.stringify(file)), { _v: 'v1' });
  D.setDoc('<html><head></head><body><main><section class="screen on" data-screen="value"><div class="above">' + 'Install value overview. '.repeat(60)
    + '</div>' + R.block('id-c') + '<div class="below">' + 'More details below. '.repeat(400) + '</div></section></main></body></html>');
  const micro = () => new Promise(r => setImmediate(r));
  async function drain(ms) {   // microtasks, frames, then the timers in order (SP's 0 / 150 / 400 ms checks)
    await micro(); for (let i = 0; i < 4 && Q.raf.length; i++) { Q.raf.splice(0).forEach(f => f()); await micro(); }
    const end = Q.now + ms;
    for (;;) { Q.t.sort((p, q) => p.at - q.at || p.n - q.n); const n = Q.t[0]; if (!n || n.at > end) break; Q.t.shift(); Q.now = n.at; n.f(); await micro();
      for (let i = 0; i < 4 && Q.raf.length; i++) { Q.raf.splice(0).forEach(f => f()); await micro(); } }
    Q.now = end; }
  const lab = tr => { const c0 = tr.children[0]; return c0 ? c0.textContent.replace(/\s+/g, ' ').trim() : ''; };
  // the tapped table's box: the lifetime one holds its buttons, the install days' sits right above them; a Mode button's
  // row (.roi-ctl) sits right above its box
  const boxOf = (b, kind) => kind === 'met' ? b.closest('.roi-ctl').nextElementSibling : b.closest('.roi-tw') || b.closest('.roi-more').previousElementSibling;
  // the box's columns as the reader sees them: each header (not the sticky first) → [label, x in the box, width]
  const colsOf = bx => { const x0 = bx.getBoundingClientRect().left;
    return bx.querySelectorAll('thead th').slice(1).map(th => { const q = th.getBoundingClientRect(); return [th.textContent.replace(/\s+/g, ' ').trim(), q.left - x0, q.width]; }); };
  const r1 = v => Math.round(v * 10) / 10;
  // st: the view; kind: 'more' / 'lmore' / 'met'; seq: the buttons tapped in turn; o.pre: "Show …" taps first (unmeasured);
  // o.sx: the box's sideways scroll before each tap — 260 px (default), 0, 'max' (the right end: "So far" in sight) or
  // { edge: label } (that column under the box's visible right edge)
  async function run(st, kind, seq, name, o) {
    o = o || {};
    U.set('VIEW', st.VIEW); if (st.GRAIN) U.set('GRAIN', st.GRAIN); if (st.MET) U.set('MET', st.MET); if (st.LG) U.set('LG', st.LG);
    U.set('SHOW', 60); if (st.CTY != null) U.setCTY(st.CTY);
    R.repaint(); await drain(0); R.repaint(); await drain(0);                       // a country's pack in hand
    for (const w of o.pre || []) { const b = D.q(`[data-roi-more="${w}"]`); if (b) { D.fire('pointerdown', b); D.fire('click', b); await drain(500); } }
    const taps = [];
    for (const w of seq) {
      const b = D.q(`[data-roi-${kind}="${w}"]`); if (!b) { taps.push({ w, gone: true }); break; }
      const box = boxOf(b, kind); D.lay();
      // the reader: the page so the box ends ~140px above the window's bottom (the buttons in sight; a Mode button: its row
      // ~60px from the top), the box scrolled down (near its end; "Show all" at once or a Mode switch: half way) and sideways
      D.W.y = Math.max(0, kind === 'met' ? b.closest('.roi-ctl')._L.top - 60 : box._L.top + box._L.h - (VH - 140)); D.lay();
      const mx = box.scrollHeight - box.clientHeight, smx = box.scrollWidth - box.clientWidth;
      box.scrollTop = kind === 'lmore' ? mx : seq.length === 1 || kind === 'met' ? Math.floor(mx / 2) : mx - 45;
      box.scrollLeft = 0;
      const ec = o.sx && o.sx.edge ? colsOf(box).find(c => c[0] === o.sx.edge) : null;
      if (o.sx && o.sx.edge && !ec) throw new Error(`${name}: no ${o.sx.edge} column`);
      box.scrollLeft = o.sx === 'max' ? smx : ec ? ec[1] + ec[2] / 2 - box.clientWidth : o.sx != null ? o.sx : 260;
      const br = box.getBoundingClientRect(), lo = Math.max(0, br.top), hi = Math.min(VH, br.bottom);
      const trs = box.querySelectorAll('tbody tr'), seen = trs.filter(tr => { const q = tr.getBoundingClientRect(); return q.bottom > lo && q.top < hi; });
      const a = seen[seen.length - 1], L0 = lab(a), y0 = a.getBoundingClientRect().top, sl0 = box.scrollLeft, sy0 = D.W.y, n0 = trs.length, i0 = trs.indexOf(a), c0 = D.W.calls, in0 = SP.st.intent;
      // sideways: the columns whose left edge is in sight, right to left — [0] = the one under the box's visible right edge
      const vis = colsOf(box).filter(c => c[1] < box.clientWidth).reverse(), nc0 = colsOf(box).length, end0 = smx > 0 && sl0 >= smx - 1;
      const gn = o.grow ? o.grow * (taps.length + 1) : 0;                        // (more each tap: it grows every time)
      if (gn) D.hooks.set = (el, h) => el.id === 'roi-hero' ? h + '<div class="grown">' + 'grown above '.repeat(gn) + '</div>' : h;
      D.fire('pointerdown', b); D.fire('click', b); await drain(500);
      D.hooks.set = null;
      const trs2 = D.q('#roi-body').querySelectorAll('tbody tr'), a2 = trs2.find(tr => lab(tr) === L0), box2 = a2 && a2.closest('.roi-tw');
      const h1 = new Map(box2 ? colsOf(box2).map(c => [c[0], c[1]]) : []), kc = vis.find(c => h1.has(c[0]));
      taps.push({ w, label: L0, move: a2 ? r1(a2.getBoundingClientRect().top - y0) : 'gone', sl: [sl0, box2 ? box2.scrollLeft : null],
        dy: D.W.y - sy0, calls: D.W.calls - c0, rows: [n0, trs2.length], idx: [i0, a2 ? trs2.indexOf(a2) : -1], key: a2 ? a2.getAttribute('data-roi-k') : null,
        intent: SP.st.intent > in0, inView: a2 ? (r => r.bottom > 0 && r.top < VH)(a2.getBoundingClientRect()) : false,
        // the column the reader was on (the right-edge one; gone → the next one to its left): its x before / after
        col: { edge: vis[0] ? vis[0][0] : null, gone: vis[0] ? !h1.has(vis[0][0]) : null, lab: kc ? kc[0] : null, x: kc ? [r1(kc[1]), r1(h1.get(kc[0]))] : null,
          soFar: [r1((vis.find(c => c[0] === 'So far') || [0, NaN])[1]), r1(h1.has('So far') ? h1.get('So far') : NaN)],
          end: [end0, box2 ? box2.scrollLeft >= box2.scrollWidth - box2.clientWidth - 1 : null], n: [nc0, h1.size] } });
    }
    return { name, taps };
  }
  return { run, D, U, SP };
}
async function moreKeepAll(dc, packs) {
  const res = { coh: [], cty: [], life: [], grow: [], side: [], met: [] };
  for (const VW of [375, 1280]) {
    const H = await keepHarness(VW, longFile(), null);         // All countries: every grain × mode, 60 more … then all; all at once
    for (const g of ['day', 'week', 'month']) for (const m of ['roas', 'rev', 'ltv', 'delta']) for (const seq of [['60', '60', 'all'], ['all']])
      res.coh.push(await H.run({ VIEW: 'day', GRAIN: g, MET: m, CTY: '' }, 'more', seq, `${VW} ${g} ${m} ${seq.join('+')}`));
    const C = await keepHarness(VW, dc, packs);                // every country's table (its 70 install days: Day has the buttons)
    for (const cc of ['AA', 'BB', 'XX', '']) for (const m of ['roas', 'rev', 'ltv', 'delta']) for (const seq of [['60'], ['all']])
      res.cty.push(await C.run({ VIEW: 'day', GRAIN: 'day', MET: m, CTY: cc }, 'more', seq, `${VW} ${cc || 'All'} ${m} ${seq.join('+')}`));
    for (const seq of [['60', '60', 'all'], ['all']])          // 💰 Lifetime P/L → Every day (its own buttons, inside its box)
      res.life.push(await (await keepHarness(VW, longFile(), null)).run({ VIEW: 'life', LG: 'day' }, 'lmore', seq, `${VW} life ${seq.join('+')}`));
    // something above the table grows in the same repaint: the page takes it back once, the layer adds no second scroll
    res.grow.push(await (await keepHarness(VW, longFile(), null)).run({ VIEW: 'day', GRAIN: 'day', MET: 'roas', CTY: '' }, 'more', ['60', 'all'], `${VW} grow`, { grow: 40 }));
    // sideways (review, 21 Oct 2026): the Day table's columns past D30 change with the rows shown — the reader's column
    // stays at its x: at the right end ("So far"), with the right-edge column kept, gone (D365 → the next one left), at 0
    const S = await keepHarness(VW, longFile(), null), S4 = await keepHarness(VW, longFile(400), null);
    for (const g of ['day', 'week', 'month']) for (const seq of [['60', '60', 'all'], ['all']])
      res.side.push(await S.run({ VIEW: 'day', GRAIN: g, MET: 'roas', CTY: '' }, 'more', seq, `${VW} ${g} max ${seq.join('+')}`, { sx: 'max' }));
    for (const [sx, nm] of [['max', 'max'], [{ edge: 'D365' }, 'D365'], [{ edge: 'D90' }, 'D90'], [{ edge: 'D20' }, 'D20'], [0, '0']])
      for (const seq of nm === 'D365' ? [['60'], ['all']] : [['60', '60', 'all'], ['all']])   // (D365: only in the first 60)
        res.side.push(await S4.run({ VIEW: 'day', GRAIN: 'day', MET: 'rev', CTY: '' }, 'more', seq, `${VW} m400 ${nm} ${seq.join('+')}`, { sx }));
    res.side.push(await (await keepHarness(VW, longFile(), null)).run({ VIEW: 'life', LG: 'day' }, 'lmore', ['60', 'all'], `${VW} life max`, { sx: 'max' }));
    // Mode switches (ROAS % / Revenue / Per install / Delta) after "Show all": the box keeps its row and its column
    const M = await keepHarness(VW, longFile(), null), MC = await keepHarness(VW, dc, packs);
    for (const g of ['day', 'week', 'month']) for (const [sx, nm] of [['max', 'max'], [{ edge: 'D30' }, 'D30'], [{ edge: 'D270' }, 'D270']])
      res.met.push(await M.run({ VIEW: 'day', GRAIN: g, MET: 'roas', CTY: '' }, 'met', ['rev', 'ltv', 'delta', 'roas'], `${VW} ${g} ${nm} met`, { pre: ['all'], sx }));
    res.met.push(await M.run({ VIEW: 'day', GRAIN: 'day', MET: 'roas', CTY: '' }, 'met', ['rev', 'roas'], `${VW} day 60 met`, { sx: 'max' }));   // 60 shown
    for (const cc of ['AA', 'XX'])
      res.met.push(await MC.run({ VIEW: 'day', GRAIN: 'day', MET: 'roas', CTY: cc }, 'met', ['rev', 'ltv', 'delta', 'roas'], `${VW} ${cc} met`, { pre: ['all'], sx: { edge: 'D14' } }));
  }
  return res;
}
(async () => {
  try {
    vm.runInContext(src, ctx);
    const R = ctx.ROI, U = R._;
    // no pointer → nothing added
    ctx.DATA = {};
    out.no_ptr = ctx.roiWrap('<div>studio</div><details id="val-oldapp">old</details>', 'id-a') === '<div>studio</div><details id="val-oldapp">old</details>';
    ctx.DATA = { roi: { file: 'roi.json.gz', v: 'v1', apps: { 'id-a': { file: 'roi_aaaaaaaaaaaa.json.gz', st: 'Watch', r7: 0.4, u7: 0.5, pb: 12 } } } };
    const w = ctx.roiWrap('<div>studio</div><details id="val-oldapp">old</details>', 'id-a');
    out.wrap_order = w.indexOf('id="roi-root"') < w.indexOf('id="val-more"') && w.indexOf('id="val-more"') < w.indexOf('studio')
      && w.indexOf('studio') < w.indexOf('val-oldapp');                         // ROI first; the Studio + old views folded
    out.wrap_loading = w.includes('ROI load ho raha hai');
    // the app file, put in place as if loaded
    const d = appFile();
    const data = U.data();
    data.AF['roi_aaaaaaaaaaaa.json.gz'] = Object.assign(d, { _v: 'v1' });
    const C = U.cols(d, d.rows);
    out.cols = [C.length, C[0].lab, C[30].lab, C[31].lab, C[C.length - 1].lab];       // D0 … D30 + D60 … D365
    const old = d.rows[0];                                                       // no day-by-day cells: checkpoints
    out.old_fallback = [U.cum(old, C[7], T), U.cum(old, C[8], T)];
    const html1 = U.dayView(d);
    out.day_today = html1.includes('Today · 13 Oct') && html1.includes('Yesterday · 12 Oct');
    out.day_tiles = ['D0 ROAS', 'D30 ROAS', 'LTV D30', 'Back next day'].every(s => html1.includes(s));
    const hh = U.hero('id-a');
    out.hero = ['Money back in', '~12 days', 'D7 ROAS', 'Cost / install', 'Lifetime profit / loss', 'Ads profit me'].every(s => hh.includes(s));
    out.day_rows = (html1.match(/<tr data-roi-k="\d{4}-\d{2}-\d{2}"><td class="roi-nm">/g) || []).length;   // the first 60 install days, each keyed
    out.day_more = html1.includes('Show all 70');
    out.day_be = html1.includes('day 9');
    out.day_tie = html1.includes('1 din ka GA4 read match nahi hua');
    U.set('GRAIN', 'month');
    const gm = U.groupRows(d);
    out.months = gm.map(g => [g.k, g.rows.length]);
    const Cm = U.cols(d, d.rows);
    out.month_cols = Cm.map(c => c.lab).slice(0, 6);
    const sep = gm.find(g => g.k === '2026-09');
    out.month_d0 = U.agg(sep, Cm[0], T)[0];
    out.month_d30 = U.agg(sep, Cm[5], T)[0];                                       // some Sep days not 33 days old yet → null
    U.set('GRAIN', 'day');
    out.cells = [U.cell(20, 10, 'roas', null, 100), U.cell(20, 10, 'rev', null, 100), U.cell(20, 10, 'ltv', null, 100), U.cell(20, 10, 'delta', 15, 100)];
    // countries
    const hc = U.ctyView(d);
    out.cty_cut = hc.includes('Hatane se har hafte ~<b>$75</b>');
    out.cty_order = [...hc.matchAll(/data-roi-cty="([A-Z]+)"/g)].map(m => m[1]);   // Cut, then Scale, then Keep
    out.cty_chips = (hc.match(/class="roi-cc"/g) || []).length;
    // lifetime: totals to 1 Oct (2 Oct is live)
    const hl = U.lifeView(d.life, d.life_till, d);
    out.life_total = hl.includes('$45') && hl.includes('$30') && hl.includes('+$15');
    out.life_since = hl.includes('Profit me since') && hl.includes('30 Sep 2026');
    out.life_live = hl.includes('Today · live');
    ctx.curView = () => 'INR'; ctx.cfx = () => 100; ctx.csym = () => '₹';
    const hlr = U.lifeView([['2026-09-29', 5, 20, 1800], ['2026-09-30', 30, 5, 450]], '2026-09-30', Object.assign({}, d, { ccy: 'INR' }));
    out.life_inr = hlr.includes('₹2,250') && hlr.includes('₹3,500') && hlr.includes('+₹1,250');   // spend as billed (not 25 × 100)
    // install-month P/L: Dec paid back (its own curve crosses between day 3 and 7), Jan not yet; ₹ = as billed, % in ₹ too
    const co = { T, rows: [['2025-12-01', 100, 10, 900, 15], ['2025-12-02', 100, 10, 900, 15], ['2026-01-01', 100, 10, 900, 4]],
      months: [['2025-12', 20, [4, 8, 12, 24, null, null, null, null, null, null], 1800], ['2026-01', 10, [1, null, null, null, null, null, null, null, null, null], 900]] };
    const cp = U.cohortPL(co);
    out.co_rows = [...cp.matchAll(/<td class="roi-nm">([^<]+?)\s*(?:<small>([^<]+)<\/small>)?<\/td>/g)].map(m => m[1] + (m[2] ? ' · ' + m[2] : ''));
    out.co_paid = cp.includes('✅ Wapas aa gaya · ~day 5') && cp.includes('⏳ 44% wapas');
    out.co_total = cp.includes('₹3,400') && cp.includes('+₹700') && cp.includes('₹2,700');   // 3,400 − 2,700 billed
    ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
    const cpu = U.cohortPL(co);
    out.co_usd = cpu.includes('⏳ 40% wapas') && cpu.includes('✅ Wapas aa gaya · ~day 6');
    // all apps
    U.setAll({ v: 1, T, apps: [{ app_id: 'id-b', app: 'Beta', st: 'Normal', r7: 0.5, u7: 0.5, r30: 0.9, life: [10, 5], cut: 0 },
      { app_id: 'id-a', app: 'Alpha', st: 'Worse', r7: 0.2, u7: 0.5, pb: null, best: [30, 0.6, '2026-09'], life: [5, 10], cut: 2 },
      { app_id: 'id-hidden', app: 'Hidden', st: 'Worse', life: [1, 1], cut: 0 }], life: [], months: [], rows: [] });
    const ha = U.allView();
    out.all_order = [...ha.matchAll(/data-roi-app="([^"]+)"/g)].map(m => m[1]);
    out.all_icons = (ha.match(/class="aicon"/g) || []).length;
    const hA = U.hero('');
    out.hero_all = hA.includes('Sabse bada loss') && hA.includes('Best ROI') && hA.includes('Sabse zyada gira');
    // ⚖️ the four forms — synthetic ranges unlike any default, so the page provably prints the file's own
    const F4C = { p: [1.1, 1.5, 3], b: [0.9, 0.5, 0.1], beta: [-0.2, -0.1, -0.05], ages: [7, 30, 90], gap: 0.25 };
    const e30 = { bl: 0.8, s: 0.5, na: 250, nn: 500, n: 500, days: 7, days_na: 7, sp: 100, spi: 8000, rev: 80, from: '2026-09-01', to: '2026-09-07',
      paid: [0.4, 0.45, 0.6], inc: [0.5, 0.6, 0.75], mar: [0.4, 0.55, 0.72], gap: [0.25, 0.44, 0.5] };
    const e7 = Object.assign({}, e30, { bl: 0.3, rev: 30, paid: [0.15, 0.17, 0.22], inc: [0.2, 0.22, 0.27], mar: [0.16, 0.2, 0.26], from: '2026-09-24', to: '2026-09-30' });
    d.consts.f4 = F4C;
    d.f4 = { h: 90, by: { '7': e7, '30': e30 }, dec: { a: 90, v: 'early', mar: null } };
    const fh = U.hero('id-a');
    out.f4_hero = ['4 kinds of ROI · D30', 'pichhle 7 install-din', 'Blended', '80%', 'Paid-only', '45%', 'range 40–60%', 'Incremental', '60%',
      'range 50–75%', 'Marginal · next $100', '55%', 'range 40–72%', '⏳ Too early', 'D90 abhi complete nahi', 'disabled title="D90 abhi complete nahi"',
      'aria-pressed="true">D30', 'Organic-heavy:', 'paid share sirf <b>50%</b>', '~<b>44%</b> kam', '(range 25–50%)', 'Paid share <b>50%</b> = Google Ads installs 250 ÷ GA4 installs 500',
      'Spend $100 → kamai: blended $80 · paid-only ~$45 ($40–$60)', 'Range until GA4 paid/organic data arrives (research)', '×1.1–×3 kamata (beech ×1.5)',
      '0.10–0.90 (beech 0.50)', 'β −0.05 se −0.20 (beech −0.10; sab apps ka ek, har app ka alag abhi measure nahi)', 'What are these 4?',
      'Paid-only · Incremental · Marginal = range until GA4 paid/organic data arrives'].filter(t => !fh.includes(t));
    d.f4.beta = [-0.15, -0.06, -0.02]; d.f4.bsrc = 'app';                      // the app's own measured beta range
    out.f4_own_beta = U.hero('id-a').includes('β −0.02 se −0.15 (beech −0.06; is app ka apna measured)');
    delete d.f4.beta; delete d.f4.bsrc;
    // GA4 measured the paid split at D7: its paid share (30% of 6 of the 7 days) + premium replace the range
    d.f4.by['7'] = Object.assign({}, e7, { src: 'ga4', paid: [0.12, 0.12, 0.12], gap: [0.6, 0.6, 0.6],
      m: { p: 1.6, s: 0.31, rs: 0.42, np: 4000, no: 9000, w: 4, from: '2026-08-17', to: '2026-09-07', sw: 0.3, days: 6 } });
    U.set('F4H', '7');
    const fm = U.hero('id-a');
    out.f4_measured = ['4 kinds of ROI · D7', '12%', '✓ measured · GA4', 'Paid-only = ✓ measured (GA4 paid installs) · Incremental · Marginal = range until GA4 paid/organic data arrives',
      '✓ <b>GA4 measured:</b> paid share <b>30%</b>', '6 of 7 din', 'Ads count: 50% = Google Ads installs 250 ÷ GA4 installs 500',
      'paid install organic se <b>×1.6</b> kamata', '4,000 paid + 9,000 organic', 'Mostly organic:', 'paid share sirf <b>30%</b>',
      'blended se <b>60%</b> kam (GA4 measured)', 'Spend $100 → kamai: blended $30 · paid-only $12.', 'kamata (D7, install weeks', 'Range until GA4 paid/organic data arrives (research): organic jo bina spend ke bhi aate',
      'range 20–27%'].filter(t => !fm.includes(t));
    out.f4_measured_no_p_range = !fm.includes('beech ×1.5') && !fm.includes('paid-only ~') && !fm.includes('range 12–12%')
      && fm.split('×1.6').length === 2;                                         // the measured premium said once
    U.set('F4H', '30');                                                         // a range age names the measured one
    const fr = U.hero('id-a');
    out.f4_measured_elsewhere = fr.includes('aria-pressed="false">D7 ✓') && fr.includes('· ✓ GA4 measured at D7') && fr.includes('aria-pressed="true">D30<');
    U.set('F4H', '7');
    U.set('F4X', true);
    out.f4_measured_help = U.hero('id-a').includes('GA4 ne paid aur organic alag measure kiya');
    U.set('F4X', false); U.set('F4H', null); d.f4.by['7'] = e7;
    out.f4_hero_help_closed = !fh.includes('Budget badhana / ghatana marginal ROI se');
    U.set('F4H', '7');
    out.f4_hero7 = U.hero('id-a').includes('4 kinds of ROI · D7') && U.hero('id-a').includes('aria-pressed="true">D7');
    U.set('F4H', '90');                                                         // not complete for this app: its longest age
    out.f4_hero90 = U.hero('id-a').includes('4 kinds of ROI · D30');
    U.set('F4H', null); U.set('F4X', true);
    const fx = U.hero('id-a');
    out.f4_help = ['Budget badhana / ghatana marginal ROI se', 'Paid share · every install day', 'Close ▾', 'agla extra $ kitna laayega',
      'upar ya neeche dono ho sakta hai'].filter(t => !fx.includes(t)).concat(fx.includes('upper limit') ? ['upper limit'] : []);   // the Ads-count share: no bound
    out.f4_share_bars = (fx.match(/class="bar"/g) || []).length;              // the newest 30 install days with spend
    out.f4_share_nums = (fx.match(/<text class="lv"[^>]*>80%<\/text>/g) || []).length;   // numbers printed on the chart
    U.set('F4X', false);
    d.f4.dec = { a: 90, v: 'down', mar: [0.4, 0.5, 0.8] }; d.f4.by['90'] = Object.assign({}, e30, { gap: [0.05, 0.1, 0.12] });
    const fd90 = U.hero('id-a');
    out.f4_down = fd90.includes('4 kinds of ROI · D90') && fd90.includes('⬇️ Cut budget') && fd90.includes('sirf $40–$80 laata hai')
      && !fd90.includes('Mostly organic');                                     // small gap at D90: no warning
    d.f4.dec = { a: 90, v: 'up', mar: [1.1, 1.2, 1.4], live: true };
    out.f4_up = U.hero('id-a').includes('⬆️ Raise budget') && U.hero('id-a').includes('$110–$140');
    const by0 = d.f4.by;                                                        // no Google Ads install count: blended only
    d.f4.by = { '30': { bl: 0.8, sp: 100, spi: 8000, rev: 80, n: 500, days: 7, from: '2026-09-01', to: '2026-09-07' } };
    d.f4.dec = { a: 90, v: 'na', mar: null, live: true };
    const fn = U.hero('id-a');
    out.f4_na = fn.includes('— No paid share') && fn.includes('Paid share nahi (Google Ads installs ki ginti nahi)')
      && !fn.includes('Marginal = range until') && !fn.includes('Mostly organic') && fn.includes('80%');
    d.f4.by = by0;
    d.f4.dec = { a: 90, v: 'down', mar: [0.4, 0.5, 0.8], live: false };          // spend paused: no raise / cut call
    const fo4 = U.hero('id-a');
    out.f4_off = fo4.includes('⏸️ Spend paused') && fo4.includes('abhi Google Ads spend band') && fo4.includes('dobara chalane layak nahi')
      && !fo4.includes('Cut budget');
    delete d.f4;
    out.f4_none = !U.hero('id-a').includes('4 kinds of ROI');
    // All apps: biggest gap first, flagged, spend-weighted total; hidden apps and apps without ads out
    const fa = (h, v, mar, sp, spi, s, gap, by) => ({ h: 90, by: by || { '30': Object.assign({}, e30, { bl: v, s, na: s * 1000, nn: 1000, sp, spi,
      paid: [v * 0.9, v * 0.95, v], inc: [v * 0.92, v * 0.96, v], mar, gap }) }, dec: h });
    U.setAll({ v: 1, T, f4c: F4C, ccy: 'INR', life: [], months: [], rows: [], apps: [
      { app_id: 'id-b', app: 'Beta', st: 'Normal', life: [10, 5], cut: 0, f4: fa({ a: 90, v: 'down', mar: [0.5, 0.6, 0.7] }, 0.6, [0.47, 0.54, 0.58], 300, 24000, 0.9, [0.02, 0.03, 0.04]) },
      { app_id: 'id-a', app: 'Alpha', st: 'Worse', life: [5, 10], cut: 0, f4: fa({ a: 90, v: 'mixed', mar: [0.9, 1.05, 1.2] }, 0.8, [0.9, 1.05, 1.2], 100, 8000, 0.5, [0.44, 0.44, 0.44]) },
      { app_id: 'id-c', app: 'Gamma', st: 'Too early', life: [1, 2], cut: 0, f4: fa({ a: 90, v: 'early', mar: null }, 0, null, 0, 0, 0, null, { '7': e7 }) },
      { app_id: 'id-p', app: 'Pi', st: 'Normal', life: [3, 4], cut: 0, f4: fa({ a: 90, v: 'down', mar: [0.2, 0.3, 0.4], live: false }, 0.5, [0.2, 0.3, 0.4], 50, 4000, 0.9, [0.01, 0.02, 0.03]) },
      { app_id: 'id-z', app: 'Zeta', st: 'N/A', life: [1, 0], cut: 0, ads: false, f4: { h: 90, by: {}, dec: { a: 90, v: 'early', mar: null } } },
      { app_id: 'id-hidden', app: 'Hidden', st: 'Worse', life: [1, 1], cut: 0, f4: fa({ a: 90, v: 'up', mar: [2, 3, 4] }, 3, [2, 3, 4], 10, 800, 0.1, [0.6, 0.8, 0.9]) }] });
    const al = U.data().ALL.apps.find(x => x.app_id === 'id-a').f4.by['30'];      // Alpha: GA4 measured its paid split
    Object.assign(al, { src: 'ga4', paid: [0.76, 0.76, 0.76], m: { p: 1.3, sw: 0.5, days: 7, np: 2000, no: 2000, w: 4, from: '2026-08-03', to: '2026-08-24' } });
    const fA = U.f4All(U.data().ALL.apps.filter(x => x.app_id !== 'id-hidden'));
    out.f4_all_order = [...fA.matchAll(/<tr class="clk[^"]*" data-roi-app="([^"]+)"/g)].map(m => m[1]);
    out.f4_all_flag = [...fA.matchAll(/<tr class="clk roi-flag" data-roi-app="([^"]+)"/g)].map(m => m[1]);
    out.f4_all_icons = (fA.match(/class="aicon"/g) || []).length;
    out.f4_all = ['⚖️ 4 kinds of ROI · every app · D30', 'D30 abhi complete nahi', '⚠️ −44%', 'All apps', '<td>65%</td>', '$400',
      '↔️ Not sure yet', '⬇️ Cut budget', '⏸️ Spend paused', 'D90 90–120%', 'Budget badhana / ghatana marginal ROI se', 'Range until GA4 paid/organic data arrives',
      'Paid-only = ✓ GA4 measured on 1 app · the rest + Incremental · Marginal = range until GA4 paid/organic data arrives', 'har app ka alag abhi measure nahi',
      '<td>50% <small>✓ GA4</small></td>', '<td>76% <small>✓ GA4</small></td>', '−44% <small>Organic-heavy</small>', '✓ GA4 measured <b>1</b>'].filter(t => !fA.includes(t));
    out.f4_all_chips = [...fA.matchAll(/<span class="roi-cc">.*?<b>(\d+)<\/b><\/span>/g)].map(m => +m[1]);   // up, mixed, down, off, early, organic, GA4
    const tot = fA.slice(fA.indexOf('All apps <small>'));
    out.f4_all_tot = ['<td>70%</td>', '<td>65%</td>', '−5%'].filter(t => !tot.includes(t));   // paid share 1,400 of 2,000; paid-only 247 of 260
    U.set('FSORT', { k: 'sp', dir: 1 });
    out.f4_all_sp = [...U.f4All(U.data().ALL.apps.filter(x => x.app_id !== 'id-hidden')).matchAll(/<tr class="clk[^"]*" data-roi-app="([^"]+)"/g)].map(m => m[1]);
    U.set('FSORT', { k: 'gap', dir: 1 });
    ctx.curView = () => 'INR'; ctx.cfx = () => 100; ctx.csym = () => '₹';
    U.hero('');                                                                 // sets the view's billing currency
    const fI = U.allView();
    out.f4_all_inr = fI.includes('₹32,000') && fI.includes('id="roi-f4all"');  // spend as billed (8,000 + 24,000), not 400 × 100
    ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
    const pz = U.data().ALL.apps.find(x => x.app_id === 'id-p').f4;           // a paused app with a bigger gap …
    const pz0 = pz.by['30'].gap; pz.by['30'].gap = [0.5, 0.6, 0.7];
    const hA4 = U.hero('');                                                     // … is never featured, nor counted (Alpha D30 + Gamma D7)
    pz.by['30'].gap = pz0;
    out.f4_hero_all = hA4.includes('⚖️ Organic-heavy') && hA4.includes('80% → 76%') && hA4.includes('paid share 50% (GA4)') && !hA4.includes('spend band')
      && hA4.includes('· 2 apps aise') && hA4.includes('⬆️ 0 · ↔️ 1 · ⬇️ 1') && hA4.includes('⏸️ 1 paused') && !hA4.includes('Hidden');
    out.f4_all_pa = fA.includes('×1.1–×3 kamata (beech ×1.5) (research ne ye range D30 pe measure ki; D90 pe wahi maani hai)');   // the budget column's age
    // a paused app still too early (call "early", spend stopped): ⏸️ Spend paused, out of the total and of the ⚖️ card;
    // an all-paid app (Google Ads installs ≥ GA4 installs: s capped at 1, so paid-only = blended) is one number, never "✓ GA4"
    const ALL0 = U.data().ALL, ep = o => Object.assign({}, e30, { src: 'range' }, o);
    U.set('F4H', null);
    U.setAll({ v: 1, T, f4c: F4C, ccy: 'USD', life: [], months: [], rows: [], apps: [
      { app_id: 'id-1', app: 'One', st: 'Normal', life: [1, 1], cut: 0, f4: { h: 90, by: { '30': ep({ bl: 0.6, s: 1, sp: 100, spi: 100, paid: [0.6, 0.6, 0.6],
        inc: [0.6, 0.6, 0.6], mar: [0.49, 0.56, 0.58], gap: [0, 0, 0] }) }, dec: { a: 90, v: 'down', mar: [0.4, 0.5, 0.6], live: true } } },
      { app_id: 'id-2', app: 'Two', st: 'Normal', life: [1, 1], cut: 0, f4: { h: 90, by: { '30': ep({ sp: 50, spi: 50, gap: [0.5, 0.6, 0.7] }) },
        dec: { a: 90, v: 'early', mar: null, live: false } } },
      { app_id: 'id-3', app: 'Three', st: 'Normal', life: [1, 1], cut: 0, f4: { h: 90, by: { '7': ep({ bl: 0.3, s: 0.6, sp: 100, spi: 100,
        paid: [0.2, 0.21, 0.22], gap: [0.25, 0.3, 0.35] }), '30': ep({ s: 0.6, sp: 100, spi: 100, gap: [0.05, 0.1, 0.15] }) },
        dec: { a: 90, v: 'mixed', mar: [0.9, 1, 1.1], live: true } } }] });
    const fP = U.f4All(U.data().ALL.apps), rowOf = id => { const i = fP.indexOf(`data-roi-app="${id}"`); return fP.slice(i, fP.indexOf('</tr>', i)); };
    const totP = fP.slice(fP.indexOf('All apps <small>')), totR = totP.slice(0, totP.indexOf('</tr>'));
    out.f4_paused_early = rowOf('id-2').includes('⏸️ Spend paused') && !rowOf('id-2').includes('Too early')
      && (fP.match(/Spend paused<\/span> <b>(\d+)/) || [])[1] === '1' && !fP.includes('Too early</span> <b>')
      && totR.includes('<td>$200</td>') && !totR.includes('$250') && !totR.includes('✓ GA4');   // spend on: the two live apps only
    out.f4_allpaid = rowOf('id-1').includes('<td>60%</td>') && !rowOf('id-1').includes('✓ GA4') && !fP.includes('✓ GA4 measured');
    const hP = U.hero('');
    out.f4_paused_hero_all = hP.includes('data-roi-app="id-3"><span class="roi-hl">⚖️ Organic-heavy') && hP.includes('30% → 21%')
      && hP.includes('blended → paid-only · D7 · paid share 60%') && !hP.includes('apps aise') && hP.includes('⬆️ 0 · ↔️ 1 · ⬇️ 1')
      && hP.includes('⏸️ 1 paused');
    const g7 = U.data().ALL.apps[2].f4.by['7'].gap; U.data().ALL.apps[2].f4.by['7'].gap = [0.05, 0.1, 0.15];
    out.f4_paused_hero_none = !U.hero('').includes('roi-hl">⚖️');               // no live app organic-heavy: no card
    U.data().ALL.apps[2].f4.by['7'].gap = g7;
    U.setAll(ALL0);
    // the app's own hero: a paused app still too early; the premium range's age (research: D30) named at any other age
    const hp = U.f4Hero({ consts: { f4: F4C }, rows: [], f4: { h: 90, by: { '30': ep({}) }, dec: { a: 90, v: 'early', mar: null, live: false } } });
    out.f4_paused_early_hero = hp.includes('⏸️ Spend paused') && !hp.includes('Too early')
      && hp.includes('abhi Google Ads spend band (pichhle 14 spend din) — D90 abhi complete nahi, faisla nahi') && !hp.includes('wahi maani');
    const m7 = ep({ src: 'ga4', paid: [0.12, 0.12, 0.12], m: { p: 1.6, s: 0.31, rs: 0.42, np: 4000, no: 9000, w: 4, from: '2026-08-17', to: '2026-09-07', sw: 0.3, days: 6 } });
    const fq = { h: 90, by: { '7': ep({}), '30': ep({}) }, dec: { a: 90, v: 'mixed', mar: [0.9, 1, 1.1], live: true } };
    U.set('F4H', '7');
    const hq = U.f4Hero({ consts: { f4: F4C }, rows: [], f4: fq });
    out.f4_pa_hero = hq.includes('(beech ×1.5) (research ne ye range D30 pe measure ki; D7, D90 pe wahi maani hai)');
    out.f4_pa_own = U.f4Hero({ consts: { f4: Object.assign({}, F4C, { pa: 7 }) }, rows: [], f4: fq }).includes('(research ne ye range D7 pe measure ki; D90 pe wahi maani hai)');
    fq.by['7'] = m7;                                                            // GA4 measured D7; the D90 budget call still uses the range
    const hm = U.f4Hero({ consts: { f4: F4C }, rows: [], f4: fq });
    out.f4_pa_measured = hm.includes('(beech ×1.5) (research ne ye range D30 pe measure ki; D90 pe wahi maani hai)') && hm.includes('<b>×1.6</b> kamata');
    U.set('F4H', null);
    // 🔮 forecast: 90 days ready; spend +50% scales only the paid part; breakeven from the lifetime P/L
    const f0 = '2026-10-14', H = 180;
    d.fc = { v: 1, made: '2026-10-14', T: '2026-10-13', start: '2026-02-01', start_auto: '2026-02-01', start_set: null,
      p: { hl: 90, K: 30, w: 7, g: 0, W: 28, m: 'ratio' }, ready: { '30': true, '90': true, '180': false }, ready_from: { '180': '2027-01-10' },
      cal: { '30': { bias: 0, lo: -0.1, hi: 0.1, mape: 0.08, mape_normal: 0.05, n: 20, n_normal: 18, ev_rate: 0.1 },
             '90': { bias: 0, lo: -0.2, hi: 0.1, mape: 0.12, mape_normal: 0.1, n: 12, n_normal: 12, ev_rate: 0 } },
      f: { d0: f0, old: Array(H).fill(5), org: Array(H).fill(1), paid: Array(H).fill(4), dau: Array(H).fill(100), n: Array(H).fill(10),
           sp: Array(H).fill(8), spi: 800 },
      hist: { d0: '2026-04-17', rev: Array(180).fill(9), sp: Array(180).fill(8), spi: Array(180).fill(800), dau: Array(180).fill(100), n: Array(180).fill(10) },
      bt: [['2026-08-01', 0.05, 0.1, null, []], ['2026-08-15', -0.2, null, null, [30]]], events: [{ at: '2026-08-20', kind: 'installs', x: 3.1 }],
      att: { installs: 0.2, retention: 0.3, arpdau: 0.5 }, log: [{ d: '2026-10-14', p: { w: 7 }, sc_old: 0.09, sc: 0.06, changed: ['w'], cause: 'arpdau', bias30: 0.02 }],
      checks: [], drv: { installs: [10, 8], spend: [8, 6], cpi: [0.8, 0.75], d1: [0.3, 0.32], d7: [0.1, 0.1], dau: [100, 90], arpdau: [0.09, 0.08],
                         cty: [{ cc: 'AA', share: [0.5, 0.4], d1: [30, 32], rpi7: [0.1, 0.09], cpi: [1, 0.9], dec: 'Watch', ecpm: [2.5, 2] }],
                         split: { rev: [12, 10], imp: [5000, 4500], ecpm: [2.4, 2.2], users: 0.1, ipu: 0.01, mix: 0.05, rate: 0.03,
                                  mix_top: [['AA', 0.04, 0.5, 0.4, 2]], rate_top: [['AA', 0.02, 2.5, 2]] } },
      parts: { mix: 1.12, mix_on: true, org: 4 } };
    // users / installs / uninstalls by who: DAU 100 = 60 old + 20 organic + 20 paid; installs 10 = 4 organic + 6 paid
    d.fc.f.dau_p = { old: Array(H).fill(60), org: Array(H).fill(20), paid: Array(H).fill(20) };
    d.fc.f.un = { old: Array(H).fill(3), org: Array(H).fill(1), paid: Array(H).fill(2) };
    d.fc.f.spd = 7; d.fc.f.spi30 = 700; d.fc.f.sp30 = 7;
    d.fc.hist.un = Array(180).fill(5); d.fc.cal['90'].un_mape = 0.12; d.fc.cal['90'].un_n = 9;
    d.life = [['2026-10-01', 100, 150, 15000]]; d.life_till = '2026-10-01';
    U.set('FCH', '90'); U.set('FCM', 0);
    const fv = U.fcView(d);
    out.fc_tiles = fv.includes('Revenue · agle 90 din') && fv.includes('$900') && fv.includes('$720') && fv.includes('+$180');
    out.fc_ready = fv.includes('<b>180 din</b><small>10 Jan 27 se</small>') && fv.includes('±10% <small>(90 din, 12 tests)</small>')   // 90 days picked: its own accuracy
      && fv.includes('normal din · koi jhatka nahi') && !fv.includes('roi-fc-hz') && !fv.includes('(max)')   // an older file: no N, no note
    out.fc_be = fv.includes('Profit me aayega');                   // −$50 lifetime + $2 a day → crosses in ~25 days
    out.fc_parts = ['Forecast kyun upar', 'Kitna sahi tha', 'Model kya seekh raha hai', 'start date', 'Achanak jhatke'].every(s => fv.includes(s));
    // why: revenue +20% = users +10% × ads per user +1% × country mix +5% × eCPM +3%; the installs' country value
    out.fc_split = ['Revenue / din', '▲ +20%', '= Users (DAU)', '▲ +10%', '× Ads per user', '▲ +1.0%', '× Country mix', '▲ +5.0%',
      '× eCPM (same country)', '▲ +3.0%', 'Country mix</b> kisne badla', '40% → <b>50%</b>', 'eCPM ' + '$2.00 → <b>$2.50</b>', '×1.12', 'country-wise curves</b> pe chal raha',
      'eCPM abhi / X'].every(s => fv.includes(s));
    // users card: installs 10/day (as the last 30), uninstalls 6 vs 5 (+20%, worse), DAU 100 vs 100, the 30-day blocks
    out.fc_users = ['Users, installs &amp; uninstalls', 'Installs / din · agle 30 din', 'Uninstalls / din · agle 30 din', '▲ +20%',
      'DAU · din 90', 'Din 1–30', 'Din 61–90', 'Pichhle 30 din', 'Pichhle 7 din', 'abhi (7 din)', 'data-roi-fcu="un"', 'back-test me ±12%', 'pichhle 7 din',
      '30 din avg'].every(s => fv.includes(s)) && !fv.includes('Din 91–120');
    U.set('FCM', 1);                                             // spend ×2: paid users / installs / uninstalls double
    const fu2 = U.fcOut(d);
    out.fc_users_slider = fu2.includes('>16<') && fu2.includes('>8<') && fu2.includes('>120<');
    U.set('FCM', 0);
    const d2 = JSON.parse(JSON.stringify(d)); delete d2.fc.drv.split; d2.fc.parts = { mix: null }; d2.fc.drv.cty[0].ecpm = undefined;
    const fv2 = U.fcView(d2);
    out.fc_split_off = !fv2.includes('× Country mix') && !fv2.includes('average install se') && !fv2.includes('eCPM abhi / X');
    U.set('FCM', 0.5);
    const fo = U.fcOut(d);
    out.fc_slider = (fo.match(/\$1,080/g) || []).length === 2 && fo.includes('$0.00');   // revenue 900 + 0.5 × 360 = spend 720 × 1.5
    // engine vd: its three mix weights as simple labels and %, the two models explained, country curves always on
    const d3 = JSON.parse(JSON.stringify(d)); d3.fc.p = { bo: 0.5, bn: 1, cq: 0 }; d3.fc.parts = { mix: 1.12, mix_on: true, org: 4, engine: 'vd' };
    const fv3 = U.fcView(d3);
    out.fc_vd = fv3.includes('Old installs · model B share: <b>50%</b>') && fv3.includes('New installs · model B share: <b>100%</b>')
      && fv3.includes('Newest eCPM move used: <b>0%</b>') && fv3.includes('Model A = har install-din') && fv3.includes('countries ke apne curves');
    // 🌍 GA4's extension cells: the old installs' revenue past day 90 measured vs carried, the switch on / off, and the
    // paid vs organic split's source (measured from GA4's paid users, or the Google Ads count) — numbers printed
    const d4 = JSON.parse(JSON.stringify(d3));
    d4.fc.p = { bo: 0.5, bn: 1, cq: 0, gc: 3, pc: 0 };
    d4.fc.parts = Object.assign({}, d3.fc.parts, { gx: { on: true, old: 0.32, meas: 0.105, umeas: 0.864, weeks: [2, 0, 0, 14, 14, 9, 7] },
      nv: { org: [5, 0.2], paid: [5, 0.3] }, nvsrc: 'cp', pc: false });
    const g4 = U.fcView(d4);
    d4.fc.parts.gx = { on: false, old: 0.4, meas: 0, umeas: 0, weeks: [0, 0, 0, 0, 0, 0, 0] }; d4.fc.parts.nvsrc = 'ads';
    const g5 = U.fcView(d4);
    out.fc_gx = g4.includes('Old installs after day 90') && g4.includes('<b>32%</b>') && g4.includes('<b>11%</b> kamai')
      && g4.includes('<b>86%</b> users') && g4.includes('Model me <b>on</b>') && g4.includes('×1.50') && g4.includes('<b>measured</b>.')
      && g4.includes('Country curves after day 90 (GA4): <b>on</b>') && g4.includes('Paid vs organic (GA4 paid users): <b>off</b>')
      && g5.includes('backfill') && g5.includes('Google Ads install count se andaaza') && !g5.includes('Model me <b>on</b>');
    // a split nothing measured (no paid installs: paid = organic by construction) or an older payload without a source:
    // no paid ÷ organic line at all (never a made-up ×1.00)
    d4.fc.parts.nvsrc = null; const gn1 = U.fcView(d4);
    delete d4.fc.parts.nvsrc; const gn2 = U.fcView(d4);
    out.fc_gx_nosrc = !gn1.includes("data-fc-pc") && !gn1.includes("paid vs organic:") && !gn2.includes("data-fc-pc") && gn1.includes("Old installs after day 90");
    // the switches held off for every app (tun false): said so, never "is app ka back-test isse behtar nahi hua";
    // a setting stored before the switches existed: never checked yet; gc 2 = users only; gc 3 = on
    d4.fc.parts.nvsrc = 'ads'; d4.fc.parts.gx = { on: 0, old: 0.4, meas: 0.2, umeas: 0.8, weeks: [1, 0, 0, 3, 3, 1, 0] };
    d4.fc.parts.tun = { gc: false, pc: false }; const h1 = U.fcView(d4);
    d4.fc.parts.tun = { gc: true, pc: true }; d4.fc.p = { bo: 0.5, bn: 1, cq: 0 }; const h2 = U.fcView(d4);
    d4.fc.p = { bo: 0.5, bn: 1, cq: 0, gc: 0, pc: 0 }; const h3 = U.fcView(d4);
    d4.fc.parts.gx.on = 2; d4.fc.p.gc = 2; const h4 = U.fcView(d4);
    d4.fc.parts.gx.on = 3; d4.fc.p.gc = 3; const h5 = U.fcView(d4);
    out.fc_gx_held = h1.includes('Model me abhi <b>off</b> (sab apps me)') && h1.includes('isliye sab apps me off') && !h1.includes('behtar nahi hua;')
      && h2.includes('Back-test ne abhi ise check nahi kiya') && h2.includes('GA4 paid cells: back-test ne abhi check nahi kiya') && !h2.includes('Model me abhi <b>off</b>')
      && h3.includes('is app ka back-test isse abhi behtar nahi hua') && h3.includes('ya back-test me behtar nahi')
      && h4.includes('Model me <b>users ke liye on</b>') && h4.includes('Country curves after day 90 (GA4): <b>users on</b>')
      && h5.includes('Model me <b>on</b>') && h5.includes('Country curves after day 90 (GA4): <b>on</b>');
    // the learning log: the first entry of the new engine says so (its error is a different measure); later ones do not
    d3.fc.log = d.fc.log.concat([{ d: '2026-10-15', eng: 'vd', p: d3.fc.p, sc: 0.1, changed: ['bn', 'bo', 'cq'] }]);
    const sw = U.fcView(d3);
    d3.fc.log = d3.fc.log.concat([{ d: '2026-10-16', eng: 'vd', p: d3.fc.p, sc: 0.09, sc_old: 0.1, changed: ['bo'] }]);
    const sw2 = U.fcView(d3);
    out.fc_vd_switch = (sw.match(/New model \(A \+ B\)/g) || []).length === 1 && sw.includes('badla: New installs · model B share, Old installs')
      && (sw2.match(/New model \(A \+ B\)/g) || []).length === 1 && !sw.includes('Old model</b>');
    U.set('FCM', 0);
    // 💸 Budget by country: today's plan = the forecast; a payload without the rows' own revenue per $ (rs): one
    // value for every country, "Same for all" — a row shows spend / installs / CPI / revenue / ROI / source for the
    // chosen days only (fits 1280 px);
    // −/+ keeps the total (Keep total on); a row out of its measured range warned; hidden in a developer view; the
    // slider ×m (installs ×m^(1−e) only when the forecast itself follows the country model, fc_cs 1)
    const dp = JSON.parse(JSON.stringify(d));
    dp.app_id = 'id-plan';
    dp.fc.plan = { v: 2, weeks: ['2026-09-28', '2026-10-05'], e: 0.1, en: 1234, s: 8, org: 4, n0: 5, fc_cs: 0, h: [30, 90, 180],
      old: [150, 450, 900], orgr: [30, 90, 180], paid: [210, 630, 1050],
      rows: [{ cc: 'AA', s0: 6, sb: 6, ppu: 0.5, lo: 4, hi: 6.5, r: [26.25, 78.75, 131.25] },
             { cc: 'OT', s0: 2, sb: 2, ppu: 1, lo: 1, hi: 1.5, r: [26.25, 78.75, 131.25] }] };   // OT: today above its weeks
    U.set('PLAN', null); U.set('FCH', '90');
    const pv = U.fcView(dp);
    // revenue 90 = 450 old + 90 organic + 630 paid; AA: 6 × 78.75 = $473 (Other $158); ROI (paid) 630 ÷ 720 = 88%
    out.pl_card = pv.includes('💸 Budget by country') && pv.includes('Revenue · 90 days') && pv.includes('$1,170') && pv.includes('today $1,170')
      && pv.includes('<td>$2.00</td><td>$473</td><td>88%</td><td class="roi-q">Same for all</td></tr>') && pv.includes('<td>$158</td>') && pv.includes('88%') && pv.includes('+$450')
      && pv.includes('Installs / day') && pv.includes('Spend / day') && pv.includes('>9<') && pv.includes('Keep total on')
      && pv.includes('data-roi-pl="AA|+"') && pv.includes('<th>Revenue 90 days</th><th>ROI 90 days</th><th>Source</th></tr>') && !pv.includes('Revenue 180 days')
      && !pv.includes('Next-$ ROI') && !pv.includes('pooled curve') && !U.fcPlan(dp).includes('aaj $') && !U.fcPlan(dp).includes(' din</th>')
      && pv.includes('e 0.10') && pv.includes('1,234') && pv.includes('Revenue per $ (90 din) har country ke liye same') && pv.includes('Is app ke GA4 paid users ka 90 din tak ka data abhi country-wise ke liye kaafi nahi')
      && pv.includes('30 / 90 din pe har country ka apna dikhega') && pv.includes('zyadatar apps pe behtar')
      && pv.includes('β upar se lagane pe back-test haara')
      && !pv.includes('Measured range ke bahar:') && (U.fcPlan(dp).match(/<th>/g) || []).length === 7;
    // each row's own revenue per $ at 30 / 90 days where it won this app's own back-test (rs "cp" its own GA4 slot,
    // "pool" the rest measured together; rt how much of it is the row's own data), one value past 90 (rs null); today's
    // plan still = the forecast (6 × 60 + 2 × 135 = 630); moving spend to the row that earns more per $ raises the revenue
    const dq = JSON.parse(JSON.stringify(dp));
    dq.app_id = 'id-plan-own';
    Object.assign(dq.fc.plan.rows[0], { r: [20, 60, 131.25], rs: ['cp', 'cp', null], rt: [0.9, 0.834, null] });
    Object.assign(dq.fc.plan.rows[1], { r: [45, 135, 131.25], rs: ['pool', 'pool', null], rt: [0.7, 0.62, null] });
    dq.fc.plan.rw = { '30': { w: ['2026-08-03', '2026-09-27'], n: 8, np: 5000 }, '90': { w: ['2026-06-01', '2026-07-26'], n: 8, np: 4000 } };
    dq.fc.plan.rbt = { '30': { n: 14, b: 12, w: 2, need: 4 }, '90': { n: 12, b: 10, w: 2, need: 4 } };
    U.set('PLAN', null);
    const pq = U.fcPlan(dq);
    out.pl_own = pq.includes('<td>$360</td><td>67%</td><td class="roi-q">Own GA4 · 83%</td>') && pq.includes('<td>$270</td><td>150%</td><td class="roi-q">Pooled · 62%</td>')
      && pq.includes('Revenue per $ (90 din) har country ka apna:') && pq.includes('8 complete install hafton (1 Jun 26 – 26 Jul 26)')
      && pq.includes('Pooled" = jin countries ka GA4 me apna slot nahi') && pq.includes('installs aur revenue dono badalte hain')
      && pq.includes('is app pe 12 me se 10 test behtar, 2 kharab.') && pq.includes('Source ka % = value me us country ke apne data ka hissa')
      && pq.includes('today $1,170') && !pq.includes('Same for all') && !pq.includes('roi-q">Mostly app avg');
    U.plStep(dq, 'AA', '-');                                     // AA 6 → 5.4, Other 2 → 2.6: revenue 450 + 90 + 324 + 351
    out.pl_own_move = U.fcPlan(dq).includes('$1,215') && U.fcPlan(dq).includes('▲ +3.8%');
    // own values that are mostly the app's average (each row's own data under half of it): said so, row by row
    const dw = JSON.parse(JSON.stringify(dq));
    dw.app_id = 'id-plan-weak';
    dw.fc.plan.rows[0].rt = [0.02, 0.49, null]; dw.fc.plan.rows[1].rt = [0.3, 0.1, null];
    U.set('PLAN', null);
    const pw = U.fcPlan(dw);
    out.pl_own_weak = (pw.match(/<td class="roi-q">Mostly app avg<\/td>/g) || []).length === 2 && !pw.includes('Own GA4')
      && pw.includes('har country ka apna nikala, par abhi kisi country ka spend itna nahi') && !pw.includes('Revenue per $ (90 din) har country ka apna:')
      && pw.includes('(thoda) dono badalte hain');
    dw.fc.plan.rows[0].rt = [0.02, 0.5, null];                   // one row at half its own data: that row says it
    U.set('PLAN', null);
    const pw2 = U.fcPlan(dw);
    out.pl_own_weak2 = pw2.includes('<td class="roi-q">Own GA4 · 50%</td>') && pw2.includes('<td class="roi-q">Mostly app avg</td>')
      && pw2.includes('Revenue per $ (90 din) har country ka apna:');
    // this app's own back-test at the chosen days: too few origins yet (waits), or lost (one value) — said which
    const dn = JSON.parse(JSON.stringify(dp));
    dn.app_id = 'id-plan-bt';
    dn.fc.plan.rbt = { '30': { n: 2, b: 2, w: 0, need: 4 }, '90': { n: 6, b: 1, w: 5, need: 4 } };
    U.set('PLAN', null);
    const pn90 = U.fcPlan(dn);
    U.set('PLAN', null); U.set('FCH', '30');
    const pn30 = U.fcPlan(dn);
    out.pl_bt = pn90.includes('Country-wise is app ke apne back-test me haara (6 me se 1 test behtar, 5 kharab)') && pn90.includes('Revenue per $ (90 din) har country ke liye same')
      && !pn90.includes('kaafi nahi') && (pn90.match(/Same for all/g) || []).length === 2
      && pn30.includes('Country-wise is app pe abhi test nahi ho saka (2 test, 4 chahiye') && pn30.includes('Revenue per $ (30 din) har country ke liye same')
      && pn30.includes('is app ka back-test jeetega, 30 / 90 din pe har country ka apna dikhega');
    U.set('PLAN', null); U.set('FCH', '30');
    out.pl_h = U.fcPlan(dp).includes('<th>Revenue 30 days</th>') && U.fcPlan(dp).includes('<td>$53</td>')      // Other 2 × 26.25
      && U.fcPlan(dp).includes('Profit · 30 days');
    U.set('FCH', '90');
    // the INR view: spend as billed (₹840 a day at the billing rate, as the forecast card above), revenue at today's rate
    ctx.curView = () => 'INR'; ctx.cfx = () => 100; ctx.csym = () => '₹';
    const di = JSON.parse(JSON.stringify(dp)); di.ccy = 'INR'; di.fc.f.spi = 840;
    const pvi = U.fcView(di);
    out.pl_inr = pvi.includes('₹840') && pvi.includes('+₹41,400') && pvi.includes('83%') && pvi.includes('₹630') && pvi.includes('₹210.0');
    ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
    U.set('PLAN', null);
    U.fcView(dp);
    const st = U.plState(dp);
    U.plStep(dp, 'AA', '+');                                    // AA 6 → 6.6, Other 2 → 1.4: the total stays 8
    out.pl_keep = Math.abs(st.s.AA - 6.6) < 1e-9 && Math.abs(st.s.OT - 1.4) < 1e-9;
    const pv2 = U.fcPlan(dp);
    out.pl_warn = pv2.includes('Measured range ke bahar:') && pv2.includes('⚠️') && pv2.includes('$8.0')   // AA above 6.5
      && pv2.includes('[OT]') === false && !/Other kam/.test(pv2);   // OT 1.4: inside 1 … today's 2 (today's level counts as seen)
    st.keep = false; U.plStep(dp, 'OT', '-');
    out.pl_nokeep = Math.abs(st.s.OT - 1.26) < 1e-9 && Math.abs(st.s.AA - 6.6) < 1e-9;
    U.set('PLAN', null);
    ctx.window.__DEV_VIEW__ = true; out.pl_dev = U.fcPlan(dp) === '' && !U.fcView(dp).includes('Budget by country'); ctx.window.__DEV_VIEW__ = false;
    out.pl_none = !U.fcView(d).includes('Budget by country');
    const mu = U.fcMul(dp.fc, 2), m0 = U.fcMul(d.fc, 2), dc = JSON.parse(JSON.stringify(dp));
    dc.fc.plan.fc_cs = 1;
    const mc = U.fcMul(dc.fc, 2);
    out.pl_slider = mu.i === 2 && mu.r === 2 && m0.i === 2 && m0.r === 2 && !U.fcView(dp).includes('sab countries')
      && Math.abs(mc.i - Math.pow(2, 0.9)) < 1e-12 && mc.r === 2 && U.fcMul(dc.fc, 0).i === 0 && U.fcView(dc).includes('sab countries');
    U.set('PLAN', null); U.set('FCH', '90');
    // 🔎 "Agle N din" (engine vd's verified horizon, fc.hz): chips 30 / 90 / 180 / N (max) in fixed widths, the
    // standard 365 locked with its day, the Hinglish note (why not longer, when the next unlocks); tiles, chart band,
    // users card, planner and the accuracy card at the chosen horizon; an app without a chip falls back to its N
    // (synthetic values throughout)
    const HN = 198, g = JSON.parse(JSON.stringify(dp)), fill = (n, v) => Array(n).fill(v);
    g.app_id = 'id-hz';
    Object.assign(g.fc.f, { old: fill(HN, 5), org: fill(HN, 1), paid: fill(HN, 4), dau: fill(HN, 100), n: fill(HN, 10), sp: fill(HN, 8),
      dau_p: { old: fill(HN, 60), org: fill(HN, 20), paid: fill(HN, 20) }, un: { old: fill(HN, 3), org: fill(HN, 1), paid: fill(HN, 2) } });
    const cc = (n, m, mn, lo, hi, nn, ev) => ({ bias: 0, lo, hi, mape: m, mape_normal: mn, n, n_normal: nn == null ? n : nn, ev_rate: ev || 0, un_mape: 0.2, un_n: n });
    Object.assign(g.fc, { v: 2, ready: { '30': true, '90': true, '180': true, '365': false }, ready_from: { '365': '2027-03-16' },
      cal: { '30': cc(16, 0.08, 0.06, -0.1, 0.1), '44': cc(15, 0.1, 0.07, -0.12, 0.1), '90': cc(11, 0.12, 0.1, -0.2, 0.15),
             '180': cc(5, 0.15, 0.15, -0.25, 0.2), '198': cc(4, 0.2, 0.18, -0.3, 0.22, 3, 0.25) },
      hz: { n: HN, chips: [30, 90, 180, 198], lock: { '365': '2027-03-16' }, next: [212, '2026-10-30'], lag: 2, x: 0,
            band: [[30, -0.1, 0.1], [44, -0.12, 0.1], [90, -0.2, 0.15], [180, -0.25, 0.2], [198, -0.3, 0.22]],
            btx: { '198': [['2025-11-02', 0.1, 0, 0], ['2025-11-16', -0.4, 1, 0], ['2025-11-30', 0.05, 0, 0], ['2025-12-14', -0.15, 0, 0]] } },
      checks: [{ made: '2026-01-01', h: 198, pred: 1, act: 1, err: 0.05 }, { made: '2026-01-02', h: 30, pred: 1, act: 1, err: -0.3 }] });
    g.fc.plan = Object.assign({}, dp.fc.plan, { h: [30, 90, 180, 198], old: [150, 450, 900, 990], orgr: [30, 90, 180, 198], paid: [210, 630, 1050, 1155],
      rows: dp.fc.plan.rows.map(x => Object.assign({}, x, { r: x.r.concat([144.375]) })) });
    U.set('PLAN', null); U.set('FCH', 'max');
    const gv = U.fcView(g);
    out.hz_chips = (gv.match(/class="roi-fch"/g) || []).length === 5 && gv.includes('data-roi-fch="max" aria-pressed="true"><b>198 din</b><small>(max)</small>')
      && gv.includes('data-roi-fch="90" aria-pressed="false"><b>90 din</b><small>±10%</small>') && gv.includes('roi-fchs')
      && gv.includes('disabled title="Data kam — 16 Mar 27 se"><b>365 din</b><small>16 Mar 27 se</small>') && !gv.includes('data-roi-fch="198"');
    out.hz_note = gv.includes('🔎 <b>Agle 198 din</b> tak hi kyun') && gv.includes('4 baar check') && gv.includes('kam se kam 4 chahiye')
      && gv.includes('<b>212 din — 30 Oct 26 se</b> · 365 din — 16 Mar 27 se') && gv.includes('har 2 hafte ~14 din badhta hai');
    // the range = where the ACTUAL fell around the forecast: 1,980 ÷ 1.22 … 1,980 ÷ 0.70 (tests that ran 22% high / 30% low)
    out.hz_tiles = gv.includes('Revenue · agle 198 din') && gv.includes('$1,980') && gv.includes('80% chance: $1,623 – $2,829')
      && gv.includes('Google Ads spend · 198 din') && gv.includes('±20% <small>(198 din, 4 tests)</small>')   // 3 normal: all 4 (as its range)
      && gv.includes('sab tests (jhatkon samet) · normal din ±18% (sirf 3 tests — kam se kam 4 chahiye) · 25% me achanak jhatka')
      && !gv.includes('range forecast se');
    out.hz_users = gv.includes('DAU · din 198') && gv.includes('ARPDAU · agle 198 din') && gv.includes('Din 181–198') && !gv.includes('Din 181–210')
      && gv.includes('back-test me ±20% (198 din, 4 tests)');
    out.hz_plan = gv.includes('<th>Revenue 198 days</th>') && gv.includes('Revenue · 198 days') && gv.includes('Profit · 198 days');
    // past 90 days one revenue per $ for every row ("Same for all"), said why; the 30 / 90 chips have their own
    const go = JSON.parse(JSON.stringify(g));
    go.app_id = 'id-hz-own';
    go.fc.plan.rows = go.fc.plan.rows.map((x, i) => Object.assign({}, x, { rs: i ? ['pool', 'pool', null, null] : ['cp', 'cp', null, null] }));
    go.fc.plan.rw = dq.fc.plan.rw;
    U.set('PLAN', null); U.set('FCH', '180');
    const p180 = U.fcPlan(go);
    out.pl_own_180 = (p180.match(/Same for all/g) || []).length === 2 && p180.includes('Revenue per $ (180 din) har country ke liye same')
      && p180.includes('90 din se aage country-wise abhi test nahi ho saka') && p180.includes('30 / 90 din chip pe har country ka apna dikhta hai')
      && go.fc.plan.h.length === 4
      && p180.includes('<th>ROI 180 days</th>');
    const g72 = JSON.parse(JSON.stringify(go));
    g72.app_id = 'id-hz-72';
    g72.fc.plan.h = [30, 72, 90, 180];
    g72.fc.plan.rows = g72.fc.plan.rows.map((x, i) => Object.assign({}, x, { rs: i ? ['pool', null, 'pool', null] : ['cp', null, 'cp', null] }));
    g72.fc.hz.chips = [30, 72, 90, 180]; g72.fc.cal['72'] = g72.fc.cal['44'];
    U.set('PLAN', null); U.set('FCH', '72');
    const p72 = U.fcPlan(g72);
    out.pl_own_72 = p72.includes('Country-wise sirf 30 aur 90 din pe test hua, 72 din pe nahi') && p72.includes('30 / 90 din chip pe har country ka apna dikhta hai')
      && p72.includes('Revenue · 72 days');
    U.set('PLAN', null); U.set('FCH', 'max');
    const bd = U.fcBand(g.fc, HN);
    out.hz_band = JSON.stringify(bd(0)) === '[-0.1,0.1]' && JSON.stringify(bd(29)) === '[-0.1,0.1]' && Math.abs(bd(36)[1] - 0.1) < 1e-12
      && Math.abs(bd(66)[0] + 0.16) < 1e-9 && JSON.stringify(bd(197)) === '[-0.3,0.22]' && JSON.stringify(U.fcBand(d.fc, 90)(5)) === '[-0.2,0.1]';
    const ch = U.fcChart(g.fc, HN, fill(HN, 10), fill(HN, 8));
    out.hz_chart = ch.includes('range $9.1 – $11&lt;br&gt;') && ch.includes('range $8.2 – $14&lt;br&gt;') && ch.includes('>$14<') && ch.includes('>$8.2<');   // day 1 … day 198, its ends printed
    // a very wide range (a test 95% low): the band drawn to the chart's top, the lines not squashed, its end marked ↑
    const gw = JSON.parse(JSON.stringify(g.fc)); gw.hz.band = [[30, -0.1, 0.1], [198, -0.95, 0.2]];
    const cw2 = U.fcChart(gw, HN, fill(HN, 10), fill(HN, 8));
    const axes = (cw2.match(/class="ax" x="[0-9.]+" y="[0-9.]+" text-anchor="end">\$[^<]*/g) || []).map(t => t.split('>').pop());   // the y axis
    out.hz_chart_wide = cw2.includes('range $8.3 – $200&lt;br&gt;') && axes[axes.length - 1] === '$30' && cw2.includes('class="band"');
    // no normal test at a horizon: said so (never "koi jhatka nahi"); a step in the daily line > 20%: said under the chart
    const gn = JSON.parse(JSON.stringify(g)); gn.fc.cal['198'] = cc(4, 0.3, null, -0.3, 0.2, 0, 1);
    const gnv = U.fcView(gn);
    out.hz_no_normal = gnv.includes('±30% <small>(198 din, 4 tests)</small>') && gnv.includes('sab 4 tests me achanak jhatka — normal din ka error abhi measure nahi');
    const gj = JSON.parse(JSON.stringify(g)); gj.fc.f.old = gj.fc.f.old.map((v, i) => i < 180 ? 5 : 2);
    const gjo = U.fcOut(gj);
    out.hz_jump = gjo.includes('📏 Line din 181 pe <b>−30%</b> badalti hai') && !U.fcOut(g).includes('📏');
    const ga = U.fcAcc(g);
    out.hz_acc = ga.includes('198 din <small>(max)</small>') && (ga.match(/<tr class="roi-act">/g) || []).length === 1
      && ga.includes('Har horizon ka error') && ga.includes('aria-label="Back-test error by horizon"') && ga.includes('>±18%<') && ga.includes('>±10%<')
      && ga.includes('(198 din)') && ga.includes('⚡ is beech achanak jhatka') && ga.includes('purane din se 198 din aage')
      && ga.includes('<b>Asli check</b>') && ga.includes('+5%') && !ga.includes('−30%') && !ga.includes('newest 26 test-dino');
    // a few-test horizon (not a chip) past ±100%: its bar cut at ±100%, said so; its tooltip keeps the real error
    const gx = JSON.parse(JSON.stringify(g)); gx.fc.cal['44'] = cc(4, 2.5, null, -0.9, 5, 0, 1);
    const gxa = U.fcAcc(gx);
    out.hz_acc_cut = gxa.includes('±100% se upar wale bar wahin kate') && gxa.includes('sab tests (koi normal nahi) &lt;b&gt;±250%') && !U.fcAcc(g).includes('wahin kate');
    // 352 / 365 days rest on two origins older than the newest 26: said so under that chip's tests
    const g365 = JSON.parse(JSON.stringify(g)); g365.fc.hz.btx = { '198': g.fc.hz.btx['198'].map(r => r.slice(0, 3).concat([r[0] < '2025-11-20' ? 1 : 0])) };
    out.hz_old_origins = U.fcAcc(g365).includes('198 din ke 4 tests me se 2 newest 26 test-dino se pehle ke hain') && U.fcAcc(g365).includes('sirf 2 baar check');
    // a standard chip picked: its own numbers; an app without that chip: its own N (max), nothing jumps to another app's
    U.set('FCH', '90');
    const g90 = U.fcView(g);
    out.hz_pick = g90.includes('data-roi-fch="90" aria-pressed="true"') && g90.includes('data-roi-fch="max" aria-pressed="false"')
      && g90.includes('Revenue · agle 90 din') && g90.includes('±10% <small>(90 din, 11 tests)</small>') && g90.includes('🔎 <b>Agle 198 din</b>');
    const yg = JSON.parse(JSON.stringify(g));
    yg.fc.hz = { n: 72, chips: [30, 72], lock: { '90': '2026-11-20', '180': '2027-02-12', '365': '2027-09-03' }, next: [100, '2026-11-20'], band: [[30, -0.1, 0.1], [72, -0.2, 0.2]], btx: { '72': [] }, lag: 2, x: 0 };
    yg.fc.cal = { '30': g.fc.cal['30'], '72': cc(4, 0.1, 0.1, -0.2, 0.2) }; yg.fc.ready = { '30': true, '90': false, '180': false, '365': false };
    yg.fc.ready_from = { '90': '2026-11-20', '180': '2027-02-12', '365': '2027-09-03' };
    const yv = U.fcView(yg);
    out.hz_young = U.fcHN(yg.fc) === 72 && yv.includes('data-roi-fch="max" aria-pressed="true"><b>72 din</b>') && yv.includes('Revenue · agle 72 din')
      && (yv.match(/disabled title=/g) || []).length === 3 && yv.includes('<b>100 din — 20 Nov 26 se</b> (90 din bhi) · 180 din — 12 Feb 27 se · 365 din — 3 Sep 27 se')
      && !yv.includes('90 din — 20 Nov');                                       // (90 unlocks with 100: said once)
    const ng = JSON.parse(JSON.stringify(yg)); ng.fc.hz = { n: null, chips: [], lock: { '30': '2026-11-01' }, next: [30, '2026-11-01'], band: [], btx: {}, lag: 2, x: 0 };
    ng.fc.cal = {}; ng.fc.ready = { '30': false, '90': false, '180': false, '365': false }; ng.fc.ready_from = { '30': '2026-11-01' };
    out.hz_none = U.fcView(ng).includes('30 din ka forecast <b>1 Nov 26</b> se') && !U.fcView(ng).includes('data-roi-fch');
    const g365b = JSON.parse(JSON.stringify(g)); g365b.fc.hz.n = 365; g365b.fc.hz.chips = [30, 90, 180, 365]; g365b.fc.hz.lock = {}; g365b.fc.hz.next = null;
    g365b.fc.cal['365'] = cc(4, 0.25, 0.22, -0.3, 0.3);
    out.hz_365 = U.fcView(g365b).includes('1 saal se lamba forecast model nahi banata') && U.fcView(g365b).includes('<b>365 din</b><small>(max)</small>')
      && !U.fcView(g365b).includes('disabled');
    // All apps: each app's own longest verified horizon beside 30 / 90 / 180 (an older file: —)
    const A0 = U.data().ALL;
    U.setAll({ v: 1, T: A0 ? A0.T : [], life: [], months: [], rows: [], apps: [
      { app_id: 'id-n', app: 'Nn', st: 'Normal', life: [1, 1], fc: { ready: { '30': true, '90': true, '180': true }, a30: 300, r30: 330, r90: 990, r180: 1980, e30: 0.06, n: 198, rn: 2178, en: 0.18 } },
      { app_id: 'id-o', app: 'Oo', st: 'Normal', life: [1, 1], fc: { ready: { '30': true, '90': false, '180': false }, a30: 100, r30: 90, r90: 270, r180: 540, e30: 0.1 } }] });
    const fz9 = U.fcAll();
    out.hz_all = fz9.includes('<th>Agle N din (max)</th>') && fz9.includes('$2,178 <small>198 din · ±18%</small>') && (fz9.match(/<td>—<\/td>/g) || []).length >= 1;
    U.setAll(A0);
    // the 80% range beside the forecast (every test missed one way, the bias only partly taken back): said on the tile
    // with its shrink — 4 tests: 2 newer → 2 ÷ 5 = 40%; 5 tests: 3 → 50%
    U.set('FCH', 'max');
    const gs = JSON.parse(JSON.stringify(g)); gs.fc.cal['198'] = cc(4, 0.2, 0.18, 0.05, 0.25);
    const gso = U.fcOut(gs);
    const gu = JSON.parse(JSON.stringify(g)); gu.fc.cal['198'] = cc(5, 0.2, 0.18, -0.4, -0.1, 5);
    const guo = U.fcOut(gu);
    out.hz_side = gso.includes('80% chance: $1,584 – $1,886 <small>(range forecast se neeche: 4 tests me zyadatar asli forecast se kam aaya, aur model is galti (bias) ka sirf 40% theek karta hai — naye 2 tests se')
      && guo.includes('80% chance: $2,200 – $3,300 <small>(range forecast se upar: 5 tests me zyadatar asli forecast se zyada aaya') && guo.includes('sirf 50% theek')
      && !U.fcOut(g).includes('range forecast se');
    // a chip's ± and the accuracy table from the same tests as its range: fewer than 4 normal → every test's error
    const gq = JSON.parse(JSON.stringify(g)); gq.fc.cal['90'] = cc(11, 0.12, 0.1, -0.2, 0.15, 2, 0.8);
    const gqv = U.fcView(gq);
    out.hz_nm = gqv.includes('data-roi-fch="90" aria-pressed="false"><b>90 din</b><small>±12%</small>') && gqv.includes('<b>±10%</b> <small>(sirf 2 tests)</small>')
      && U.fcView(g).includes('<small>±10%</small>') && !U.fcView(g).includes('<b>±10%</b> <small>(sirf');
    // no live check yet: the day the first one shows; the growing N: why it never comes on its chip, and 365's day
    const gc = JSON.parse(JSON.stringify(g)); gc.fc.checks = []; gc.fc.hz.chk = { '30': '2026-11-20', '198': '2027-05-10', '365': '2027-10-22' };
    const gca = U.fcAcc(gc);
    U.set('FCH', '30');
    const gc30 = U.fcAcc(gc);
    U.set('FCH', 'max');
    const gc365 = JSON.parse(JSON.stringify(g365b)); gc365.fc.checks = []; gc365.fc.hz.chk = { '365': '2027-10-22' };
    out.hz_chk = gca.includes('198 din (max) ka asli check is chip pe nahi aayega') && gca.includes('max ka pehla asli check <b>22 Oct 27</b> ko (365 din ka)')
      && !gca.includes('10 May 27') && gc30.includes('30 din ka pehla milan (pehle bana forecast vs asli) <b>20 Nov 26</b> ko yahan dikhega')
      && U.fcAcc(gc365).includes('365 din ka pehla milan (pehle bana forecast vs asli) <b>22 Oct 27</b>')
      && U.fcAcc(d).includes('90 din baad har din ka asli se milan yahan dikhega');     // an older file: as before
    // a verified chip whose calibrated total can not be shown (series' _fit): no chip, not "locked", said in the note
    const gd = JSON.parse(JSON.stringify(g365b)); gd.fc.hz.n = 180; gd.fc.hz.chips = [30, 90, 180]; gd.fc.hz.drop = [365];
    const gdv = U.fcView(gd);
    out.hz_drop = U.fcHN(gd.fc) === 180 && !gdv.includes('<b>365 din</b><small>') && gdv.includes('<b>365 din</b> ke bhi 4+ tests hain')
      && gdv.includes('5 baar check ho chuka hai. <b>365 din') && !gdv.includes('badhta hai: .')
      && gdv.includes('180 din ke sudhre total se bas thoda hi zyada (ya kam) aata') && gdv.includes('data-roi-fch="max" aria-pressed="true"><b>180 din</b>');
    // x labels never overlap on a phone's 380-unit drawing: no first day at 365 days (it would touch "aaj"), no middle
    // at 72 / 100 (it would touch the last day); both where there is room
    const xl = (H, W, s) => { const n0 = 90, n = n0 + H, X = i => 44 + (W - 44 - 54) * i / (n - 1), lab = () => s || '17 Jul 26';
      return (U.fcXs(X, n0, n, H > 60 ? n0 - 1 + Math.round(H / 2) : null, lab, 220).match(/<text /g) || []).length; };
    // (node: no canvas — 6 units a character, the widest a "D Mon YY" runs in the page's font)
    out.hz_axis = xl(365, 380) === 3 && xl(254, 380) === 4 && xl(180, 380) === 4 && xl(72, 380) === 3 && xl(100, 380) === 3
      && xl(365, 720) === 4 && xl(30, 380) === 3
      && !U.fcXs(i => 44 + 282 * i / 454, 90, 455, 271, () => '17 Jul 26', 220).includes('text-anchor="start"');
    U.set('FCH', '90'); U.set('PLAN', null);
    // 📅 the eCPM calendar: a marker per event week with its measured %, the day's tooltip line, the Hinglish note
    // (old users in full, new installs × φv, the bidding link), the moving holidays NOT in the forecast; owner-only
    const fk = JSON.parse(JSON.stringify(d.fc)); fk.f.d0 = '2026-11-01';
    const ev0 = (k, a, b, e) => ({ k, a, b, e, o: e, nv: 0.61 * e, np: -0.48 * e });
    // (synthetic values throughout)
    fk.fcal = { n: 3, ys: [[2023, 2], [2024, 4], [2025, 5]], phi: [0.61, -0.48], ev: [Object.assign(ev0('bf', '2026-11-23', '2026-11-29', 0.05), { lo: -0.02, hi: 0.11 }), ev0('cyber', '2026-11-30', '2026-12-06', 0.03),
      ev0('xmas', '2026-12-22', '2026-12-31', -0.07), ev0('j1', '2027-01-01', '2027-01-07', -0.15), ev0('j2', '2027-01-08', '2027-01-14', -0.17),
      ev0('hold', '2027-02-12', null, -0.25)],
      hol: [{ k: 'diwali', a: '2026-11-01', b: '2026-11-11', x: 0.07, xt: 0.03, xc: -0.04, y: 2025, s: 0.4, app: 0.028, c: [4, 20] },
            { k: 'ramadan', a: '2027-02-08', b: '2027-03-09', x: -0.05, y: 2026, s: null, app: null }] };
    const ck = U.fcChart(fk, 90, Array(90).fill(10), Array(90).fill(0));
    out.cal_marks = (ck.match(/class="ev up"/g) || []).length === 2 && (ck.match(/class="ev dn"/g) || []).length === 3
      && ck.includes('>BF +5%<') && ck.includes('>Xmas −7%<') && !ck.includes('>Cyber') && !ck.includes('>Jan')   // labels never overlap
      && ck.includes('eCPM calendar week');
    const c180 = U.fcChart(fk, 180, Array(180).fill(10), Array(180).fill(0));
    out.cal_180 = c180.includes('then it stays there') && c180.includes('Ramadan') && c180.includes('Muslim-majority desh me eCPM baaki desh se <b>−5%</b> alag')
      && !c180.includes('Muslim-majority desh khud')                            // (an older measure without its two parts)
      && !c180.includes('mukable ~−');                                          // (no share known: no app %)
    out.cal_tip = ck.includes('Black Friday week: eCPM +5% (measured, seasons −2% … +11%)') && ck.includes('January week 2: eCPM −17% (measured)');
    out.cal_note = ['📅 <b>eCPM calendar</b>', 'Black Friday week', '+5%', 'January slide', '−15% → −17%',
      'pichhle 3 season (2023–24: 2 apps, 2024–25: 4 apps, 2025–26: 5 apps) me', '<b class="roi-up">+5%</b> <small>[−2% … +11%]</small>',
      'bold = un season ka average, [ ] = sabse kam … sabse zyada season', 'Purane users ki kamai pe pura asar', 'naye installs pe ~61%', 'installs per $ −4.8%', 'ROAS ~+1.3%',
      '(1 Jan 27 – 14 Jan 27)',
      'Forecast me <b>nahi</b> joda', 'Diwali week', 'India me eCPM baaki desh se <b>+7%</b> alag <small>(India khud +3%, baaki −4%)</small>',
      '2025 me ek baar measured, 4 app×desh cells vs 20 baaki', 'is app ki 40% kamai wahan → baaki desh ke mukable ~+3%',
      'eCPM calendar week (green up, red down)']
      .every(x => ck.includes(x)) && !ck.includes('Ramadan') && !ck.includes('then it stays there');   // (past the 90 days)
    const fs = JSON.parse(JSON.stringify(fk)); fs.fcal.hol = [{ k: 'ramadan', a: '2026-11-20', b: '2026-12-19', x: -0.05, y: 2026, s: 0.06, app: -0.003, c: [10, 40] }];
    const hs = U.fcHol(fs, 90);                                                  // a small app effect: one decimal, never "~−0%"
    out.cal_small = hs.includes('is app ki 6% kamai wahan → baaki desh ke mukable ~−0.3%') && hs.includes('10 app×desh cells vs 40 baaki') && !hs.includes('~−0%');
    // an app (almost) not earning there: no item at all — never "is app ki 0% kamai wahan → ~+0.0%"
    const fz = JSON.parse(JSON.stringify(fk)); fz.fcal.hol = [{ k: 'diwali', a: '2026-11-01', b: '2026-11-11', x: 0.07, y: 2025, s: 0.004, app: 0.0003, c: [4, 20] }];
    const fz2 = JSON.parse(JSON.stringify(fz)); fz2.fcal.hol.push({ k: 'ramadan', a: '2026-11-20', b: '2026-12-19', x: -0.05, y: 2026, s: 0.005, app: -0.00025, c: [10, 40] });
    const hz2 = U.fcHol(fz2, 90);
    out.cal_zero = U.fcHol(fz, 90) === '' && !hz2.includes('Diwali') && hz2.includes('Ramadan') && hz2.includes('is app ki 1% kamai wahan')
      && !hz2.includes('0% kamai');
    const c30 = U.fcChart(fk, 30, Array(30).fill(10), Array(30).fill(0));
    out.cal_30 = (c30.match(/class="ev /g) || []).length === 2 && !c30.includes('January slide') && c30.includes('Diwali week');
    ctx.window.__DEV_VIEW__ = true;
    const cdev = U.fcChart(fk, 90, Array(90).fill(10), Array(90).fill(0));
    out.cal_dev = !cdev.includes('eCPM calendar') && !cdev.includes('class="ev ') && !cdev.includes('Diwali');
    ctx.window.__DEV_VIEW__ = false;
    out.cal_none = !U.fcView(d).includes('eCPM calendar') && !U.fcView(d).includes('class="ev ');
    const fu = JSON.parse(JSON.stringify(fk)); fu.fcal.use = 0;                // measured, NOT in the forecast
    const cu = U.fcChart(fu, 90, Array(90).fill(10), Array(90).fill(0));
    out.cal_off = cu.includes('class="ev up off"') && cu.includes('Forecast me <b>nahi</b> joda: back-test me Nov–Dec')
      && cu.includes('(measured, seasons −2% … +11%, forecast me nahi)') && cu.includes('[−2% … +11%]') && !cu.includes('Purane users ki kamai pe pura asar');
    const fw = JSON.parse(JSON.stringify(d.fc)); fw.fcal = { ev: [], wk: [1.02, 1.03, 1.01, 1.01, 1, 0.99, 0.94] };
    const cw = U.fcChart(fw, 30, Array(30).fill(10), Array(30).fill(0));
    out.cal_wk = cw.includes('Hafte ki chaal: is app ke ad triggers') && cw.includes('<b>Sun −6%</b>, Tue +3%') && cw.includes('total wahi rehta hai')
      && !cw.includes('class="ev ');
    // 📅 past D30 every 30 days (the late read's m, mf): 230 install days to 13 Oct, the newest 40 day by day; a row
    // ≥ 60 days old has m = its revenue at D60, D90 … (one more each 30 days of age), final while ≥ 3 days old
    const dm = lateFile();
    U.set('GRAIN', 'day');
    const CM = U.cols(dm, dm.rows);
    out.m_cols = [CM.length, CM[0].lab, CM[30].lab, CM[31].lab, CM[32].lab, CM[CM.length - 1].lab, CM.filter(c => c.mi != null).length];
    const rOld = dm.rows[0], rTwo = dm.rows.find(r => r[0] === day('2026-10-13', -91)), rYoung = dm.rows.find(r => r[0] === day('2026-10-13', -70));
    out.m_cells = [U.cum(rOld, CM[31], T), U.cum(rOld, CM[CM.length - 1], T), U.cum(rTwo, CM[32], T), U.cum(rYoung, CM[32], T),
      U.cum(rYoung, CM[31], T), U.cum(dm.rows[dm.rows.length - 1], CM[31], T)];   // D60 / D210 / D90 not final / none
    const fd150 = (() => { const k = day('2026-10-13', -150), p = k.split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1] + ' ' + k.slice(2, 4); })();
    U.set('SHOW', 1e9);                                                         // every install day on screen
    const tm = U.cohortTable(dm), dv = U.dayView(dm);
    U.set('SHOW', 60);
    out.m_title = dv.includes('Every install day · D0 se D210 tak') && U.dayView(d).includes('Every install day · D0 se D365 tak');
    out.m_note = dv.includes('D30 ke baad har 30 din ka column (D60, D90 … D210), app ki umar tak') && dv.includes('wahin ruk jata hai (·)')
      && dv.includes('≈ = D30 ke baad GA4 ne kuch revenue kisi install din ko nahi diya (GA4 ka "(other)") — 3 din me, sabse zyada us din ki kamai ka 2.5%')
      && !U.cohortTable(d).includes('D30 ke baad har 30 din');
    out.m_q = tm.includes('D30 ke baad GA4 ne kuch revenue kisi install din ko nahi diya (GA4 ka &quot;(other)&quot;) — numbers ≈');
    out.m_head = (tm.match(/<th>D\d+<\/th>/g) || []).length === CM.length && tm.includes('<th>D210</th>') && !tm.includes('<th>D365</th>');
    out.m_nf = tm.includes('<td class="roi-g roi-nf" title="D90: $51 · ROAS 102% · not final">') && tm.includes('<td class="roi-w" title="D60: $41 · ROAS 82%">');
    const r150 = tm.slice(tm.indexOf(fd150 + '</td>')), r150e = r150.slice(0, r150.indexOf('</tr>'));
    out.m_be = r150e.includes('<td class="roi-g">≤ day 120</td>') && r150e.includes('<td>$71 <small>142%</small></td>')   // breakeven + so far via m (D150)
      && r150e.includes('<td>$50</td><td>$0.500</td><td class="roi-g">≤ day 120</td><td class="roi-b" title="D0: $1.0');   // … right after CPI, before D0
    U.set('GRAIN', 'month');
    const CMm = U.cols(dm, dm.rows), gmm = U.groupRows(dm);
    out.m_month_cols = CMm.map(c => c.lab);
    const jun = gmm.find(g => g.k === '2026-06'), mar = gmm.find(g => g.k === '2026-03');   // Jun: 104 … 134 days old
    out.m_month = [U.agg(jun, CMm[6], T), U.agg(jun, CMm[7], T), U.agg(jun, CMm[8], T), U.agg(mar, CMm[CMm.length - 1], T)];
    U.set('GRAIN', 'week');
    out.m_week_cols = U.cols(dm, dm.rows).map(c => c.lab).slice(5, 8);
    U.set('GRAIN', 'day');
    // the default Day view (the newest 60 install days, none 60 days old yet): no row on screen has m → the columns as
    // before the late read (60 / 90 / 180 / 365), and the note says the older rows go on to D210
    const t60 = U.cohortTable(dm), hd60 = (t60.match(/<th>D\d+<\/th>/g) || []).map(h => h.slice(4, -5));
    out.m_default = [hd60.length, hd60.slice(31).join(','), t60.includes('Abhi dikh rahe install din D60 tak nahi pahunche — purane (Show all / Week / Month) me D210 tak column.')];
    // a file whose late read gave the oldest row only D60 (every row's install-day checkpoints through D365 where
    // complete): no checkpoint column lost, a row without m keeps its own D60 / D90 / D180 / D365
    const dpm = (() => {
      const rows = [], newest = '2026-10-13';
      for (let age = 399; age >= 0; age--) {
        const X = day(newest, -age), t = T.map(a => (a <= age - 3 ? a + 1 : null));
        const r = [X, 100, 80, 50, null, 0, null, t, null, X, null, 'Normal', 0, 4000];
        if (age === 399) r.push([61], 1);
        rows.push(r);
      }
      return { v: 1, app: 'Part File', T, lags: 31, newest, S: '2026-10-07', rows, months: [], sum: { today: rows.slice(-2), pools: {} },
        late: { days: 30, oth: 1, omax: 0.00003, loss: 4, from: '2025-10-15', till: '2025-11-13' }, consts: { final_lag: 3 } };
    })();
    U.set('SHOW', 1e9);
    const CP = U.cols(dpm, dpm.rows), r200 = dpm.rows.find(r => r[0] === day('2026-10-13', -200)), tp = U.cohortTable(dpm), dvp = U.dayView(dpm);
    U.set('SHOW', 60);
    out.m_part_cols = CP.map(c => c.lab);
    out.m_part_cells = CP.slice(6).map(c => U.cum(r200, c, T));
    out.m_part = [dvp.includes('Every install day · D0 se D365 tak'), tp.includes('<th>D365</th>') && tp.includes('<th>D180</th>'),
      tp.includes('D30 ke baad har 30 din ka column (D60), app ki umar tak'),
      tp.includes('sabse zyada us din ki kamai ka <0.1%'), tp.includes('≈ = 4 din ke D30-ke-baad wale GA4 report pe data loss / thresholding / sampling ka flag tha'),
      tp.includes('asli se thodi alag (kam ya zyada) ho sakti hai'), !tp.includes('thodi kam dikh sakti')];
    // the column list as far as the 30-day columns go: one → (D60), two → (D60, D90), more → (D60, D90 … Dn)
    const nt = k => U.lateNote({ rows: [[0, 0, 0, 0, null, 0, null, [], null, null, null, null, 0, 0, Array(k).fill(1), 0]], late: {} });
    out.m_list = [nt(1).includes('(D60), app'), nt(2).includes('(D60, D90), app'), nt(3).includes('(D60, D90 … D120), app'), nt(0) === ''];
    // the cube's first walk still on its way: no 30-day column, the note says so (and how far it read)
    const busy = (l, rows) => U.cohortTable({ T, lags: 31, newest: '2026-10-13', rows: rows || [], late: l });
    out.m_busy = [busy({ busy: 1, from: '2024-01-01', next: '2025-03-02' }).includes('abhi GA4 se padhe ja rahe hain'),
      busy({ busy: 1, from: '2024-01-01', next: '2025-03-02' }).includes('2 Mar 25 se pehle ke din padh liye'),
      busy({ busy: 1, from: '2024-01-01', next: '2024-01-01' }).includes('abhi shuru hua'),
      !busy({}).includes('padhe ja rahe hain'), !busy({ days: 1 }).includes('padhe ja rahe hain'),
      busy({ busy: 1, from: '2024-01-01', next: '2025-03-02', at: '2026-10-11' }).includes('padh liye (aakhri baar 11 Oct 26 ko aage badha).'),
      !busy({ busy: 1, from: '2024-01-01', next: '2025-03-02' }).includes('aakhri baar')];
    // a stalled cube (done): the page says how far every day was read — the newest columns wait for it; none when whole
    const thn = (l, nw) => U.lateNote({ newest: nw, rows: [[0, 0, 0, 0, null, 0, null, [], null, null, null, null, 0, 0, [1], 0]], late: l });
    out.m_thru = [thn({ thru: '2026-09-28', till: '2026-10-13' }, '2026-10-13').includes('GA4 cube abhi 28 Sep 26 tak hi poora padha gaya hai'),
      thn({ thru: '2026-10-01', till: '2026-10-01' }, '2026-10-13').includes('abhi 1 Oct 26 tak hi'),
      thn({ thru: '2026-10-01', till: '2026-10-13' }, null).includes('abhi 1 Oct 26 tak hi'),
      !thn({ thru: '2026-10-13', till: '2026-10-13' }, '2026-10-13').includes('tak hi poora padha'),
      !thn({ thru: '2026-10-13', till: '2026-10-13' }, '2026-10-12').includes('tak hi poora padha'),
      !thn({}, '2026-10-13').includes('tak hi poora padha'),
      U.lateNote({ newest: '2026-10-13', rows: [], late: { thru: '2026-09-28', till: '2026-10-13' } }).includes('28 Sep 26 tak hi')];
    // q bit 4: a flagged late block
    const dmq = JSON.parse(JSON.stringify(dm)); dmq.rows[dmq.rows.length - 1][12] = 4;
    out.m_q4 = U.cohortTable(dmq).includes('D30 ke baad GA4 ke report pe data loss / thresholding / sampling ka flag tha — asli kamai thodi alag (kam ya zyada) ho sakti hai')
      && !U.cohortTable(dmq).includes('thodi zyada ho sakti');
    // ── 🎯 Breakeven right after CPI, before D0 (owner, 21 Oct 2026: "D0 ke pehle ak column add kar do — konse day pe
    // breakeven milta he") ──────────────────────────────────────────────────────────────────────────────────────
    const ths = t => [...t.matchAll(/<th>([^<]*)<\/th>/g)].map(m => m[1]);
    const trs = t => [...noK(t).matchAll(/<tr><td class="roi-nm">[^]*?<\/tr>/g)].map(m => m[0].slice(4, -5).split('</td>').slice(0, -1).map(x => x + '</td>'));
    // the breakeven cell: only the cells' own classes (green / muted; faded + "not final" only on a "≤"), no inline style
    const BE_TD = /^(<td class="roi-g">(≤ )?day \d+<\/td>|<td class="roi-g roi-nf" title="not final">≤ day \d+<\/td>|<td class="roi-(g|na)">\d+% back<\/td>|<td class="roi-na">—<\/td>)$/;
    // a ROAS table's week / month rows: "(≤) day N" = the row's FIRST green (ROAS ≥ 100%) cell is DN, faded exactly when
    // that cell is (not final); "% back" / "—" = no green cell at all — the breakeven never names a day the cells do not show
    const beByCells = t => { const H = ths(t), hs = H.slice(6, H.length - 1); return trs(t).map(r => {
      const cs = r.slice(6, H.length - 1), k = cs.findIndex(x => /^<td class="roi-g[ "]/.test(x)),
        m = /^<td class="roi-g( roi-nf)?"(?: title="not final")?>(?:≤ )?day (\d+)<\/td>$/.exec(r[5]);
      return m ? k >= 0 && hs[k] === 'D' + m[2] && !!m[1] === cs[k].startsWith('<td class="roi-g roi-nf"') : k < 0 && /(% back|—)<\/td>$/.test(r[5]); }); };
    // every grain × mode × both files × 60 rows / all: … Spend, CPI, Breakeven, D0 …, "So far" last (no far-right
    // Breakeven any more); every row's 6th cell its breakeven, as many cells as heads
    out.be_order = [];
    for (const g of ['day', 'week', 'month']) for (const m of ['roas', 'rev', 'ltv', 'delta']) for (const f of [appFile, lateFile]) for (const sh of [60, 1e9]) {
      U.set('GRAIN', g); U.set('MET', m); U.set('SHOW', sh);
      const t = U.cohortTable(f()), H = ths(t), rows = trs(t);
      out.be_order.push(H.slice(3, 7).join(',') === 'Spend,CPI,Breakeven,D0' && H.filter(x => x === 'Breakeven').length === 1
        && H[H.length - 1] === 'So far' && !t.includes('<th>So far</th><th>Breakeven</th>') && rows.length > 0
        && rows.every(r => r.length === H.length && BE_TD.test(r[5]))); }
    // week / month (ROAS): the group's breakeven is the first green cell, both files
    out.be_cells = [];
    for (const g of ['week', 'month']) for (const f of [appFile, lateFile]) { U.set('GRAIN', g); U.set('MET', 'roas'); U.set('SHOW', 1e9);
      const t = U.cohortTable(f()), ok_ = beByCells(t); out.be_cells.push([ok_.length, ok_.every(Boolean), (t.match(/<td class="roi-g[^>]*>≤ day \d+<\/td>/g) || []).length > 0]); }
    U.set('GRAIN', 'day'); U.set('MET', 'roas'); U.set('SHOW', 60);
    // Day: the row's own breakeven from the build — exact "day N", "≤ day N"; not yet: so far ÷ spend "back" (muted,
    // green once ≥ 100%); no spend / spend 0 / nothing measured: —; a "≤" whose day's cell is seen but not final (D1
    // after a final D0, or D0 itself): faded + "not final" like that cell — "≤" there is no gap between two columns
    const beRow = (X, sp, s, be, dd, df) => [X, 100, 80, sp, dd || null, df || 0, null, T.map(() => null), s, X, be, 'Normal', 0, sp];
    const dbe = { v: 1, T, lags: 31, newest: '2026-10-13', rows: [beRow('2026-01-01', 10, 30, [9, true]), beRow('2026-01-02', 10, 30, [120, false]),
      beRow('2026-01-03', 10, 6.3, null), beRow('2026-01-04', 10, 10.4, null), beRow('2026-01-05', null, 5, null), beRow('2026-01-06', 0, 5, null),
      beRow('2026-01-07', 10, null, null), beRow('2026-01-08', 5, 6, [1, false], [4, 6], 1), beRow('2026-01-09', 10, 12, [0, false], [12], 0),
      beRow('2026-01-10', 5, 6, [1, true], [4, 6], 2)] };
    const tbe = U.cohortTable(dbe);
    out.be_day = trs(tbe).map(r => r[5]).reverse();
    out.be_day_cells = trs(tbe).reverse().slice(7).map(r => [r[6], r[7]]);
    // week / month: the group's own, from agg over its rows (the cells' numbers) — two rows a month, spend 5 each:
    // D0 reached → "day 0"; D0 below + D1 reached (both final) → "day 1"; D3 after D1 → "≤ day 3" (between two
    // columns); D1 reached, not final → "≤ day 1"; a row without D1 → "≤ day 3"; D60 after D30 → "≤ day 60"; none →
    // "% back"; no spend → —
    const tOf = (v0, v1, v3, v30, v60) => T.map(a => ({ 0: v0, 1: v1, 3: v3, 7: v3 == null ? null : v3 + 1, 14: v3 == null ? null : v3 + 2,
      30: v30 != null ? v30 : v3 == null ? null : v3 + 3, 60: v60 })[a] ?? null);
    const mRow = (X, sp, t, s, dd, df) => [X, 100, 80, sp, dd || null, df || 0, null, t, s, X, null, 'Normal', 0, sp];
    const nf = [4, 5.5, 6, 6, 6, 6, 6, 6];                                         // seen day by day, only day 0 final
    const dgm = { v: 1, T, lags: 31, newest: '2026-10-13', rows: [
      mRow('2026-01-01', 5, tOf(6, 7, 8), 9), mRow('2026-01-02', 5, tOf(6, 7, 8), 9),                         // Jan: D0
      mRow('2026-02-01', 5, tOf(4, 5, 6), 9), mRow('2026-02-02', 5, tOf(4, 5, 6), 9),                         // Feb: D1 exact
      mRow('2026-03-01', 5, tOf(4, 4.5, 6), 9), mRow('2026-03-02', 5, tOf(4, 4.5, 6), 9),                     // Mar: ≤ D3
      mRow('2026-04-01', 5, tOf(4, null, null, 9), 9, nf, 1), mRow('2026-04-02', 5, tOf(4, null, null, 9), 9, nf, 1),   // Apr: D1 not final
      mRow('2026-05-01', 5, tOf(4, 7, 8), 9), mRow('2026-05-02', 5, tOf(4, null, 8), 9),                      // May: a row lacks D1
      mRow('2026-06-01', 5, tOf(1, 1, 1, 4, 6), 6), mRow('2026-06-02', 5, tOf(1, 1, 1, 4, 6), 6),             // Jun: ≤ D60
      mRow('2026-07-01', 5, tOf(1, 1, 1, 3, 3), 3), mRow('2026-07-02', 5, tOf(1, 1, 1, 3, 3), 3.3),           // Jul: 63% back
      mRow('2026-08-01', null, tOf(6, 7, 8), 9), mRow('2026-08-02', 5, tOf(6, 7, 8), 9),                      // Aug: spend unknown
      mRow('2026-09-01', 5, tOf(1, 1, 1, 3, 3), 3), mRow('2026-09-02', 5, tOf(1, 1, 1, 3, 3), null)] };      // Sep: a day's so far not read
    U.set('GRAIN', 'month');
    const tgm = U.cohortTable(dgm), Cg = U.cols(dgm, dgm.rows), gg = U.groupRows(dgm);
    out.be_month = trs(tgm).map(r => [r[0].replace(/<[^>]+>/g, ''), r[5]]).reverse();
    out.be_month_cells = beByCells(tgm).every(Boolean);
    out.be_grp = [U.beGrp(gg.find(g => g.k === '2026-02'), Cg, T, 10), U.beGrp(gg.find(g => g.k === '2026-02'), Cg, T, 0),
      U.beGrp(gg.find(g => g.k === '2026-02'), Cg, T, null), U.beGrp(gg.find(g => g.k === '2026-07'), Cg, T, 10),
      U.beGrp(gg.find(g => g.k === '2026-04'), Cg, T, 10), U.beGrp(gg.find(g => g.k === '2026-03'), Cg, T, 10)];
    U.set('GRAIN', 'week');
    out.be_week = trs(U.cohortTable({ v: 1, T, lags: 31, newest: '2026-10-13', rows: [mRow('2026-02-02', 5, tOf(4, 5, 6), 9), mRow('2026-02-03', 5, tOf(4, 5, 6), 9)] })).map(r => r[5]);
    // "% back" only from measured so far: spend 10 a day, 5 + 6 Oct read ($8 each), 12–14 Oct not read yet (s null) —
    // Day: — on those days; the week of 12 Oct: — (not "0% back"); October: — (not 16 ÷ 50 = "32% back"); 5–11 Oct: 80%
    const dns = { v: 1, T, lags: 31, newest: '2026-10-14', rows: ['2026-10-05', '2026-10-06', '2026-10-12', '2026-10-13', '2026-10-14']
      .map((X, i) => mRow(X, 10, T.map(() => null), i < 2 ? 8 : null)) };
    out.be_nos = ['day', 'week', 'month'].map(g => { U.set('GRAIN', g); return trs(U.cohortTable(dns)).map(r => [r[0].replace(/<[^>]+>/g, ''), r[5]]); });
    // the Hinglish note under the table, per grain; none while the table waits (loading / error)
    const bn = {};
    for (const g of ['day', 'week', 'month']) { U.set('GRAIN', g); bn[g] = U.cohortTable(appFile()); }
    out.be_note = [bn.day.includes('<p class="roi-note"><b>Breakeven</b> = jis din tak us install din ki kamai ne spend wapas kar diya (ROAS 100%); ≤ = us din ya usse pehle (do column ke beech kisi din, ya halka = us column ka number abhi final nahi); "% back" = abhi tak spend ka itna wapas.</p>'),
      bn.week.includes('us install hafte ki kamai ne spend wapas'), bn.month.includes('us install mahine ki kamai ne spend wapas'),
      bn.day.indexOf('<b>Breakeven</b>') > bn.day.indexOf('</table>'), !U.cohortTable(appFile(), { msg: '<p>x</p>' }).includes('Breakeven')];
    U.set('GRAIN', 'day'); U.set('MET', 'roas'); U.set('SHOW', 60);
    // ── 🌍 the install-day table by country ─────────────────────────────────────────────────────────────────────
    // the default view (no country part in the file) byte for byte as the page made it before the country filter: one
    // digest over every grain × mode of both made-up files, the Day view and the Countries board (worked out on the
    // page before this change)
    [out.cc_default_digest, out.cc_default_nobe, out.cc_default_nokpi, out.cc_default_kpis, out.cc_default_nok,
      out.cc_default_nokpi_nok] = defaultDigest();
    out.cc_src_null = U.cohortTable(appFile(), null) === U.cohortTable(appFile()) && U.cohortTable(appFile(), undefined) === U.cohortTable(appFile());
    {
    // a made-up app with the country part: 8 named countries (6 chips + the rest in the list), GA4's "(not set)" and
    // Google Ads' "Not split"; two packs
    const ccRowsOf = (cc, sp0, short) => {
      const rows = [], newest = '2026-10-13';
      for (let age = 69; age >= 0; age--) {
        const X = day(newest, -age), obs = Math.min(30, age), df = Math.max(0, Math.min(obs, age - 3) + 1);
        if (short && short(age)) { rows.push([X]); continue; }
        const dd = Array.from({ length: obs + 1 }, (_, L) => (L + 1) * 0.5), t = T.map(a => (a <= 30 && a < df ? dd[a] : null));
        const sp = X < '2026-09-01' || X > '2026-10-12' ? null : sp0;
        const r = [X, 20, null, sp, dd, df, null, t, dd[dd.length - 1], X, null, age >= 10 && sp != null ? 'Normal' : 'N/A',
          age === 20 ? 16 : age === 21 ? 8 : 0, sp];
        if (age >= 63) { r.push([dd[30] + 5], 1); t[T.indexOf(60)] = dd[30] + 5; r[8] = dd[30] + 5; }
        rows.push(r);
      }
      return rows;
    };
    const CCS = ['AA', 'BB', 'CC', 'DD', 'EE', 'FF', 'GG', 'HH'];
    const cdx = () => ({ v: 1, b: 'b0b0b0b0b0b0', packs: [['roi_aaaaaaaaaaaa_c00.json.gz', '0123456789ab'], ['roi_aaaaaaaaaaaa_c01.json.gz', 'ba9876543210']],
      c: CCS.map((cc, i) => [cc, 1000 - i * 100, 50 - i * 5, null, i < 4 ? 0 : 1, 3, i === 1 ? 0.25 : 0, i === 1 ? 0.125 : 0])
        .concat([['--', 40, null, null, 1, 70, 1, 0], ['XX', null, 12, null, 1, null, null, null]]),
      from: '2026-08-05', to: '2026-10-13', thru: '2026-10-13', fthru: '2026-10-10', newest: '2026-10-13',
      kc: { own_months: 5, pool_months: 1, near_months: 2, app_months: 3, est_months: 1, tzh: 12.5,
        unp: { '2026-08': 0.004, '2026-09': 0.031, '2026-10': 0.012 }, unp_all: 0.018, unp_lim: 0.02 },
      geo: { from: '2026-09-01', till: '2026-10-12', known_days: 42, unknown_days: 28, untied_days: 2, unk: [['2026-08-05', '2026-08-31'], ['2026-10-13', '2026-10-13']],
        xx_share: 0.08, cov: 0.97, billed: 1, tzh: -9.5, tzs: 1 },
      loss: { days: 2, max_share: 0.012, flag_days: 1, usd: 3.5 }, diff: { age: 30, days: 12, all: 100, cty: 96.4, rel: -0.036, n_all: 1200, n_cty: 1190, unk: 1.5 } });
    const PACKS = {
      'roi_aaaaaaaaaaaa_c00.json.gz': { v: 1, b: 'b0b0b0b0b0b0', key: 'aaaaaaaaaaaa', ix: 0, c: { AA: ccRowsOf('AA', 10, a => a % 10 === 3), BB: ccRowsOf('BB', 5), CC: ccRowsOf('CC', 4), DD: ccRowsOf('DD', 3) } },
      'roi_aaaaaaaaaaaa_c01.json.gz': { v: 1, b: 'b0b0b0b0b0b0', key: 'aaaaaaaaaaaa', ix: 1, c: { EE: ccRowsOf('EE', 2, a => a !== 5), FF: ccRowsOf('FF', 2), GG: ccRowsOf('GG', 1),
        HH: ccRowsOf('HH', 1), '--': ccRowsOf('--', null), XX: ccRowsOf('XX', 1).map((r, i) => i % 3 ? [r[0], null, null, r[3], null, 0, null, T.map(() => null), null, null, null, 'N/A', 0, r[3]] : [r[0]]) } } };
    const fetched = [];
    let failPack = null;
    ctx.fetchGzJson = u => { fetched.push(u); const f = u.split('?')[0];
      return new Promise((ok_, no) => setTimeout(() => (f === failPack || !PACKS[f] ? no(new Error('x')) : ok_(JSON.parse(JSON.stringify(PACKS[f])))), 0)); };
    const flush = () => new Promise(r => setTimeout(r, 5));
    const dc = Object.assign(appFile(), { cd: cdx() });
    U.set('GRAIN', 'day'); U.set('MET', 'roas'); U.set('SHOW', 60); U.setCTY('');
    // the picker: All countries + the 6 with the most installs as chips; EVERY country in the list (flag, name,
    // installs), then "Unknown country" / "Not split"
    const pick = U.ccPick(dc.cd);
    out.cc_chips = [...pick.matchAll(/<button type="button" data-roi-cc="([^"]*)"/g)].map(m => m[1]);
    out.cc_list = [...pick.matchAll(/<option value="([^"]*)"/g)].map(m => m[1]);
    out.cc_list_txt = pick.includes('[GG] Country GG · 400 installs') && pick.includes('[--] Unknown country · 40 installs')
      && pick.includes('🧩 Not split') && pick.includes('<optgroup label="Every country (8)">') && pick.includes('More countries ▾')
      && pick.includes('aria-pressed="true">🌍 All countries');
    // All countries (the default): the same table — only the picker joins the control row, first
    const ccAll = U.cohCard(dc), tAll = U.cohortTable(dc);
    out.cc_all_same = ccAll.includes(tAll.replace('<div class="roi-ctl">', '<div class="roi-ctl">' + pick))
      && U.cohortTable(dc, { ctl: pick }) === tAll.replace('<div class="roi-ctl">', '<div class="roi-ctl">' + pick)
      && ccAll.indexOf('data-roi-cc=""') < ccAll.indexOf('data-roi-grain="day"') && !fetched.length
      && U.dayView(dc).replace(pick, '').replace(' id="roi-coh"', '') === U.dayView(appFile());
    // picking a country: its pack is fetched once (?v=its sha), "loading" only inside the table area
    U.setCTY('AA');
    const ld = U.cohCard(dc);
    out.cc_loading = ld.includes('<div class="roi-tw roi-ccm"><p class="roi-note">⏳ [AA] Country AA ka data load ho raha hai…</p></div>')
      && ld.includes('data-roi-grain="week"') && ld.includes('data-roi-cc="AA" aria-pressed="true"');
    await flush();
    const ta = U.cohCard(dc);
    U.cohCard(dc); U.setCTY('BB'); U.cohCard(dc); U.setCTY('AA');                // same pack: no new read
    out.cc_fetch = fetched.slice();
    const C0 = U.cols(dc, dc.rows), rA = PACKS['roi_aaaaaaaaaaaa_c00.json.gz'].c.AA;
    const hdA = (ta.match(/<th>D\d+<\/th>/g) || []).map(x => x.slice(4, -5));
    out.cc_table = [ta.includes('Every install day · D0 se D60 tak · [AA] Country AA</h3>'), ta.includes('data-roi-ccx="1">✕ All countries'),
      hdA.length, hdA[0], hdA[30], hdA[31], (noK(ta).match(/<tr><td class="roi-nm">/g) || []).length, ta.includes('Show all 70'),
      ta.includes('id="roi-coh"'), C0.length];
    // a short [X] expanded: the row the build would have written (zero installs, cells 0 as far as read)
    const zrow = U.ccSrc(dc).rows.find(r => r[0] === day('2026-10-13', -63));
    out.cc_zero = [zrow.length, zrow[1], zrow[4].length, zrow[5], zrow[14], zrow[15], zrow[3], zrow[11]];
    // ROAS from the country's own spend; unknown spend → '—' and '·'; the ≈ texts of a country row
    out.cc_cells = [ta.includes('title="D7: $4.0 · ROAS 40%"'), ta.includes('<td>—</td><td>—</td>'),
      ta.includes('app ka k laga — numbers ≈'), ta.includes('0.8–1.25 se bahar tha (0.5–2 pe roka) — numbers ≈')];
    // the same grains and modes, the same code: week / month rows of the country, each mode's cells
    const gm = {};
    for (const g of ['week', 'month']) for (const m of ['roas', 'rev', 'ltv', 'delta']) {
      U.set('GRAIN', g); U.set('MET', m); const x = U.cohCard(dc);
      gm[g + m] = x.includes(`Every install ${g} · D0`) && x.includes('[AA] Country AA') && /<td class="roi-[gwb]/.test(x); }
    U.set('GRAIN', 'day'); U.set('MET', 'roas');
    out.cc_grains = Object.values(gm).every(Boolean) && Object.keys(gm).length === 8;
    // the note: every limitation with its measured size, in Hinglish
    U.setCTY('BB');
    const nb = U.cohCard(dc);
    out.cc_note = ['installs = GA4 ke is country ke naye users (ads + organic) — isliye ROAS blended',
      'k_c = us country ka AdMob ÷ GA4, mahine ke hisaab se', '25% revenue pe milan nahi mila, wahan app ka k laga (≈)',
      'Ads ka country ≠ GA4 ka country', '1 Sep 26 se 12 Oct 26 tak', "28 install din pe country-wise spend nahi pata ('—', ROAS '·')",
      'country split = kul Ads spend ka 97%', 'usme 8.0% "Not split"', 'AdMob ka din GA4 ke din se 12.5 ghante baad shuru hota hai',
      'GA4 ne revenue "(other)" me daala (2 din, sabse zyada us din ki kamai ka 1.2%)', '1 din GA4 report pe thresholding / sampling flag',
      'Status sirf ≥ $5 spend aur ≥ 30 installs wale din: 3 din N/A', 'Sab countries ka jod "All countries" se −3.6% alag (D30, 12 install din: $96 vs $100)',
      'Is card ke Total tiles = sirf is country ke; upar ke baaki tiles / charts = poora app (sab countries).',
      // the k_c of a month not whole yet: borrowed, its revenue share said; GA4 revenue without a country: measured
      '13% revenue ke mahine abhi adhoore (AdMob ya GA4 ka poora mahina nahi) — unka k_c padosi poore mahino se liya (≈)',
      'GA4 ka kuch revenue bina country ka hai ("(not set)" + "(other)": kul 1.8%, kisi mahine sabse zyada 3.1%) — AdMob un users ko asli country me ginta hai, isliye k_c utna tak zyada ho sakta hai; 1 mahine 2.0% se zyada — un mahino wale row pe ≈.',
      // the days whose Ads split did not tie, the Ads day's time zone
      "28 install din pe country-wise spend nahi pata ('—', ROAS '·') — inme 2 din Ads ka country-wise jod Ads ke kul kharche se nahi mila",
      'Ads ka din GA4 ke din se 9.5 ghante pehle shuru hota hai (Ads account ka time zone) — ek install din ka spend aur installs utne ghante khiske hue',
      // Σ countries vs All: every cause named, with its measured size
      'Wajah: All me app ka hafte wala k aur GA4 ka install-day read, countries me har country ka mahine wala k_c aur GA4 cube ka read; bina country wala GA4 revenue (kul 1.8%) AdMob ke hisaab se countries ke k_c me hai, aur "Unknown country" ka $1.5 is jod me dobara gina gaya.'
    ].filter(t => !nb.includes(t));
    // the Ads time zone unknown / mixed: said too; the Unknown country row: its money is also inside the named countries' k_c
    const tzs = g => U.ccNote(appFile(), Object.assign(cdx(), { geo: Object.assign(cdx().geo, g) }), dc.cd.c[0]);
    out.cc_tz = [tzs({ tzh: null, tzs: 2 }).includes('app ke Ads accounts 2 alag time zone me'), tzs({ tzh: null, tzs: 0 }).includes('Ads ka din Ads account ke time zone ka hai (yahan pata nahi)'),
      tzs({ tzh: 0 }).includes('Ads aur GA4 ka din ek hi time zone me')];
    // the full list: a country past the 6 chips (another pack: one more read), then the two that are not a country
    U.setCTY('GG'); U.cohCard(dc); await flush();
    const tg = U.cohCard(dc);
    out.cc_more = [tg.includes('<option value="GG" selected>'), tg.includes('<option value="" >') || !tg.includes('<option value="" selected>'),
      tg.includes('· [GG] Country GG</h3>'), fetched.length];
    U.setCTY('--');
    const tn = U.cohCard(dc);
    out.cc_unknown = [tn.includes('[--] Unknown country</h3>'), tn.includes('bina country wale'), tn.includes("Spend: Google Ads me aisa koi country nahi — '—'."),
      !tn.includes('ROAS 4'), tn.includes('AdMob me aisa koi country nahi, isliye sab ≈'),
      tn.includes('yahi kamai un countries ke k_c me bhi hai — sab countries jodte waqt ise dobara na jodein'), !tn.includes('GA4 ka kuch revenue bina country ka hai')];
    U.setCTY('XX');
    const tx = U.cohCard(dc), txr = U.ccSrc(dc).rows;
    out.cc_notsplit = [tx.includes('🧩 Not split</h3>'), tx.includes('<b>🧩 Not split</b> = Google Ads ka wo kharcha'),
      tx.includes('GA4 ne bhi 2 din ka kuch revenue') && tx.includes('GA4 ki taraf wo kisi row me nahi, par AdMob un users ko asli country me ginta hai') && !tx.includes('wo bhi kisi row me nahi'), txr.every(r => r[1] == null && r[4] == null), txr.filter(r => r[3] === 0).length > 0,
      !/<td class="roi-[gwb]/.test(tx), tx.includes('<td>—</td><td>$1.0</td><td>—</td>')];   // installs '—', its spend, no CPI
    // the pick stays across grain / mode and across apps; an app without that country says so, the picker stays
    U.setCTY('AA'); U.set('GRAIN', 'month'); U.set('MET', 'rev');
    const keep1 = U.cohCard(dc).includes('[AA] Country AA</h3>');
    U.set('GRAIN', 'day'); U.set('MET', 'roas');
    const other = Object.assign(appFile(), { cd: Object.assign(cdx(), { c: [['QQ', 10, 1, null, 0, 0, 0]], packs: [['roi_bbbbbbbbbbbb_c00.json.gz', 'aaaaaaaaaaaa']] }) });
    const n0 = fetched.length, to = U.cohCard(other);
    out.cc_persist = [keep1, U.getCTY() === 'AA', to.includes('Is app me [AA] Country AA ka data nahi'), to.includes('data-roi-cc="QQ"'),
      fetched.length === n0, !to.includes('✕ All countries'), U.cohCard(dc).includes('[AA] Country AA</h3>')];
    // a pack that does not load: the error and "Try again" only in the table area; the next try reads it again
    failPack = 'roi_aaaaaaaaaaaa_c01.json.gz';
    const de = Object.assign(appFile(), { cd: Object.assign(cdx(), { packs: [['roi_aaaaaaaaaaaa_c00.json.gz', '0123456789ab'], ['roi_aaaaaaaaaaaa_c01.json.gz', 'cccccccccccc']] }) });
    U.setCTY('EE'); U.cohCard(de); await flush();
    const te = U.cohCard(de);
    out.cc_err = [te.includes('<div class="roi-tw roi-ccm"><p class="roi-note">⚠️ [EE] Country EE ka data load nahi hua. <button type="button" class="roi-lnk" data-roi-ccr="1">Try again</button>'),
      te.includes('data-roi-grain="day"'), te.includes('Every install day')];
    failPack = null;
    // a bad file name never fetched
    const dbad = Object.assign(appFile(), { cd: Object.assign(cdx(), { packs: [['../x.json.gz', 'a'], ['roi_aaaaaaaaaaaa_c01.json.gz', 'b']] }) });
    U.setCTY('AA'); const nb0 = fetched.length;
    out.cc_badname = U.cohCard(dbad).includes('ka data file nahi mila') && fetched.length === nb0;
    // the cube still on its way (no country part yet): a disabled chip says when
    U.setCTY('');
    out.cc_busy = U.cohCard(Object.assign(appFile(), { late: { busy: 1, from: '2024-01-01', next: '2025-01-01' } }))
      .includes('<button type="button" disabled title="GA4 cube poora padhne ke baad country-wise table">🌍 Country · after GA4 cube read</button>');
    // the 🌍 Countries board: "📅 Day-wise" on each country the cube has (none without the country part)
    const cv = U.ctyView(dc);
    out.cc_board = [[...cv.matchAll(/data-roi-pick="([A-Z-]+)"/g)].map(m => m[1]), U.ctyView(appFile()).includes('data-roi-pick')];
    // the build's _zrow (tests/test_roi_frontend.py hands its rows over) == the page's zx
    if (process.argv[3]) {
      const zc = JSON.parse(require('fs').readFileSync(process.argv[3], 'utf8'));
      const one = (cd, c) => JSON.stringify(U.zx(c.x, cd, c.cc, T)) === JSON.stringify(c.row) ? 1 : [c.x, c.cc, U.zx(c.x, cd, c.cc, T), c.row];
      out.cc_zx = zc.cases.map(c => one(zc.cd, c)).concat(zc.cases0.map(c => one(zc.cd0, c)));
    }
    // the ≈ bits of a borrowed k_c month / a month with GA4 revenue without a country say what they are
    const qn = U.ccQ(32 | 64, dc.cd).filter(Boolean);
    out.cc_q_new = qn.length === 2 && qn[0].includes('mahina abhi adhoora (AdMob / GA4 poora nahi), padosi poore mahino se liya')
      && qn[1].includes('GA4 ka 2% se zyada revenue bina country ka tha');
    // the picker: a chip's country picked → the list shows "More countries ▾" (one option selected, never the chip's)
    U.setCTY('AA');
    const pa = U.ccPick(dc.cd);
    out.cc_pick_sel = (pa.match(/ selected>/g) || []).length === 1 && pa.includes('<option value="" selected>More countries ▾')
      && !pa.includes('<option value="AA" selected>');
    // 🧩 Not split: the same columns as every country (D0 … D30 day by day, then the 30-day / checkpoint ones), cells '—'
    U.setCTY('XX');
    const txc = U.cohCard(dc), hx = (txc.match(/<th>D\d+<\/th>/g) || []).map(x => x.slice(4, -5));
    out.cc_xx_cols = [hx.length, hx[1], hx[2], hx[30], txc.includes('<td class="roi-na">·</td>'), txc.includes('<td class="roi-na">—</td>'),
      txc.includes("installs aur har din wala column '—'"), txc.includes('Every install day · D0 se D365 tak · 🧩 Not split</h3>')];
    // 🎯 a country's table: the same Breakeven column right after CPI, every grain (Day: the row's own; week / month:
    // the group's, = its first green cell); Not split: no revenue → — on every row
    out.be_cty = [];
    for (const cc of ['AA', 'BB', 'XX']) for (const g of ['day', 'week', 'month']) {
      U.setCTY(cc); U.set('GRAIN', g); U.set('MET', 'roas'); U.set('SHOW', 1e9);
      const t = U.cohCard(dc), H = ths(t), rows = trs(t), bes = rows.map(r => r[5]);
      out.be_cty.push([cc, g, H.slice(3, 7).join(','), H[H.length - 1], rows.length > 0 && rows.every(r => r.length === H.length && BE_TD.test(r[5])),
        g === 'day' || beByCells(t).every(Boolean), cc === 'XX' ? bes.every(x => x === '<td class="roi-na">—</td>') : cc !== 'BB' || g !== 'week' || bes.some(x => /day \d+</.test(x)),
        t.includes('<b>Breakeven</b> = jis din tak')]); }
    U.set('GRAIN', 'day'); U.set('SHOW', 60); U.setCTY('BB');
    const fdOf = k => { const p = k.split('-'); return '<td class="roi-nm">' + (+p[2]) + ' ' + MON[+p[1] - 1] + ' ' + k.slice(2, 4); }, tbb = trs(U.cohCard(dc));
    out.be_cty_day = [12, 2].map(a => tbb.find(r => r[0].startsWith(fdOf(day('2026-10-13', -a))))[5]);
    U.setCTY('XX');
    // the country view: the app-wide "(other)" / flag sentences of the 30-day columns are left to the country's own note
    const dlt = Object.assign(lateFile(), { cd: cdx() });
    U.setCTY('');
    const tl0 = U.cohCard(dlt);
    U.setCTY('AA');
    const tl1 = U.cohCard(dlt);
    out.cc_noq = [tl0.includes('≈ = D30 ke baad GA4 ne kuch revenue kisi install din ko nahi diya'), !tl1.includes('≈ = D30 ke baad GA4 ne'),
      tl1.includes('≈ = row ke kuch din GA4 ne revenue "(other)" me daala (2 din'), tl1.includes('D30 ke baad har 30 din ka column (D60)')];
    // the country rows end before the All table's newest day: said, with how many days
    const dto = Object.assign(appFile(), { cd: Object.assign(cdx(), { to: '2026-10-11' }) });
    out.cc_to = U.cohCard(dto).includes('Country table 11 Oct 26 tak — GA4 cube ne uske baad ke 2 din abhi poore nahi padhe (All countries 13 Oct 26 tak)')
      && !U.cohCard(dc).includes('Country table ');
    // an app without the country part while a country is picked: the All table + one line (never a silent drop)
    const nocd = U.cohCard(appFile()), nbusy = U.cohCard(Object.assign(appFile(), { late: { busy: 1, from: '2024-01-01', next: '2025-01-01' } }));
    out.cc_nocd = [nocd.includes('Is app me [AA] Country AA ki country-wise table nahi (GA4 cube se banti hai; is app ke liye abhi nahi bani) — neeche All countries.'),
      nocd.includes('data-roi-ccx="1">✕ All countries'), nocd.includes('<th>D30</th>'), !nocd.includes('data-roi-cc='), !nocd.includes('· [AA]'),
      nbusy.includes('abhi nahi — GA4 cube poora padhne ke baad banegi') && nbusy.includes('🌍 Country · after GA4 cube read')];
    // a row past the index's last day (another build's pack) is never expanded (no negative array length)
    out.cc_zx_guard = U.zx('2026-10-15', dc.cd, 'AA', T) === null && U.zx('2026-10-15', dc.cd, 'XX', T) === null && Array.isArray(U.zx('2026-10-13', dc.cd, 'AA', T));
    // a pack of another build than the index in hand (its "b"; the site serves a pack's newest copy whatever ?v= says):
    // never shown — the app file is read again once, then that build's pack; still another build after it: said + Try again
    {
      const DATA0 = ctx.DATA;
      ctx.DATA = { roi: { file: 'roi.json.gz', v: 'v2', apps: { 'id-s': { file: 'roi_dddddddddddd.json.gz', st: 'Watch' } } } };
      const mk = (b, shas) => Object.assign(appFile(), { app_id: 'id-s', cd: Object.assign(cdx(), { b,
        packs: shas.map((h, i) => ['roi_dddddddddddd_c0' + i + '.json.gz', h]) }) });
      const oldF = Object.assign(mk('old0old0old0', ['111111111111', '222222222222', '555555555555']), { _v: 'v1' });
      oldF.cd.c = oldF.cd.c.map(x => x[0] === 'EE' ? Object.assign(x.slice(), { 4: 2 }) : x);   // EE's pack: gone from the site
      const newF = mk('new0new0new0', ['333333333333', '444444444444']);
      const pk = (f, b) => Object.assign(JSON.parse(JSON.stringify(PACKS[f])), { b });
      let SITE = { 'roi_dddddddddddd_c00.json.gz': pk('roi_aaaaaaaaaaaa_c00.json.gz', 'new0new0new0'),
                   'roi_dddddddddddd_c01.json.gz': pk('roi_aaaaaaaaaaaa_c01.json.gz', 'new0new0new0'), 'roi_dddddddddddd.json.gz': newF };
      const got = [];
      ctx.fetchGzJson = u => { got.push(u); const f = u.split('?')[0];
        return new Promise((ok_, no) => setTimeout(() => SITE[f] ? ok_(JSON.parse(JSON.stringify(SITE[f]))) : no(new Error('http 404')), 0)); };
      const AFs = U.data().AF, F = 'roi_dddddddddddd.json.gz';
      AFs[F] = oldF;
      U.setCTY('AA');
      const s1 = U.cohCard(AFs[F]); await flush();
      const s2 = U.cohCard(AFs[F]), s2b = U.cohCard(AFs[F]); await flush(); // another build's pack → the app file again
      const s3 = U.cohCard(AFs[F]); await flush();                          // the new index → its own pack
      const s4 = U.cohCard(AFs[F]);
      out.cc_stale = [s1.includes('ka data load ho raha hai'), s2.includes('ka data load ho raha hai') && !s2.includes('<td class="roi-') && s2b === s2,
        AFs[F].cd.b === 'new0new0new0' && AFs[F]._v === 'v2', s4.includes('· [AA] Country AA</h3>') && /<td class="roi-[gwb]/.test(s4),
        got.join(' ') === 'roi_dddddddddddd_c00.json.gz?v=111111111111 roi_dddddddddddd.json.gz?v=v2 roi_dddddddddddd_c00.json.gz?v=333333333333'];
      // a pack the old index names that the new build no longer has (404): the app file again, then EE in its new pack
      AFs[F] = Object.assign(JSON.parse(JSON.stringify(oldF)), { _v: 'v1' });
      AFs[F].cd.b = 'old1old1old1';                                         // (one read again per file and build)
      U.setCTY('EE'); got.length = 0;
      U.cohCard(AFs[F]); await flush(); U.cohCard(AFs[F]); await flush(); U.cohCard(AFs[F]); await flush();
      const g4 = U.cohCard(AFs[F]);
      out.cc_gone = [g4.includes('· [EE] Country EE</h3>') && /<td class="roi-[gwb]/.test(g4), got.join(' ') === 'roi_dddddddddddd_c02.json.gz?v=555555555555 roi_dddddddddddd.json.gz?v=v2 roi_dddddddddddd_c01.json.gz?v=444444444444'];
      // the site still on the other build after the read again (the app file did not move): said, "Try again" reads anew
      SITE = Object.assign({}, SITE, { 'roi_dddddddddddd.json.gz': Object.assign(JSON.parse(JSON.stringify(oldF)), { cd: Object.assign(JSON.parse(JSON.stringify(oldF.cd)),
        { b: 'old2old2old2', packs: [['roi_dddddddddddd_c00.json.gz', '666666666666'], oldF.cd.packs[1], oldF.cd.packs[2]] }) }) });
      AFs[F] = Object.assign(JSON.parse(JSON.stringify(SITE[F])), { _v: 'v1' });
      U.setCTY('AA'); got.length = 0;
      U.cohCard(AFs[F]); await flush(); U.cohCard(AFs[F]); await flush(); U.cohCard(AFs[F]); await flush();
      const h4 = U.cohCard(AFs[F]);
      out.cc_stale_again = [h4.includes('⚠️ [AA] Country AA ka data abhi badal raha hai (site pe naya build aa raha hai). <button type="button" class="roi-lnk" data-roi-ccr="1">Try again</button>'),
        got.filter(u => u.startsWith('roi_dddddddddddd.json.gz')).length === 1];
      U.setCTY('');
      ctx.DATA = DATA0;
    }
    // only the newest PK_KEEP packs are kept in memory (their expanded rows go with them); the one in use stays
    {
      const LP = {};
      for (let i = 0; i < 5; i++) LP['roi_eeeeeeeeeeee_c0' + i + '.json.gz'] = { v: 1, b: 'lru0lru0lru0', key: 'eeeeeeeeeeee', ix: i, c: { ['L' + i]: ccRowsOf('AA', 1) } };
      const lf = Object.assign(appFile(), { cd: Object.assign(cdx(), { b: 'lru0lru0lru0', packs: Object.keys(LP).map((f, i) => [f, String(i).repeat(12)]),
        c: [0, 1, 2, 3, 4].map(i => ['L' + i, 100 - i, 1, null, i, 0, 0, 0]) }) });
      ctx.fetchGzJson = u => new Promise((ok_, no) => setTimeout(() => { const f = u.split('?')[0]; return LP[f] ? ok_(JSON.parse(JSON.stringify(LP[f]))) : no(new Error('x')); }, 0));
      for (let i = 0; i < 5; i++) { U.setCTY('L' + i); U.cohCard(lf); await flush(); U.cohCard(lf); }
      const keys = Object.keys(U.PK).filter(k => U.PK[k].j);
      out.cc_lru = [keys.length, keys.every(k => /_c0[234]\.json\.gz/.test(k)), U.PKL.length,
        Object.keys(U.CR).every(k => !/_c0[01]\.json\.gz/.test(k)), U.cohCard(lf).includes('· [L4] Country L4</h3>')];
      U.setCTY('');
    }
    U.setCTY('');
    // ── 🧮 the totals strip (owner, 21 Oct 2026: "kpi add karo yaha pe ki kitna total spend gaya he kitna total revenue aaya
    // he — all country and jo country select kru uska kpi change ho jayega — total hi aayega"; then "profit loss me wrong lag
    // raha he": two groups, each over ONE set of days — "Spend pata wale din" (Spend, Revenue, Profit / loss, ROAS) and
    // "Poori history" (Total revenue, Installs, Install days) + the days with no spend data) ─────────────────────────────────
    {
      const kOf = h => { const i = h.indexOf('<div class="roi-cks"'); if (i < 0) return null;
        return h.slice(i, h.indexOf('</p></div>', h.indexOf('<p class="roi-note roi-ckn">', i)) + 10); };
      const kT = h => [...kOf(h).matchAll(/<div class="roi-k roi-ck( roi-k[gb])?"><div class="roi-kl">([^<]*)<\/div><div class="roi-kv">([^]*?)<\/div><div class="roi-ks">([^<]*)<\/div><\/div>/g)]
        .map(m => [m[2], m[3].replace(/<[^>]+>/g, ''), m[4]]);
      const kCls = h => [...kOf(h).matchAll(/<div class="roi-k roi-ck( roi-k[gb])?"><div class="roi-kl">[^<]*<\/div><div class="roi-kv">(?:<span class="([^"]*)">)?/g)].map(m => [(m[1] || '').trim(), m[2] || '']);
      // the two group heads [title, its days] and the coverage line under them
      const kH = h => [...kOf(h).matchAll(/<div class="roi-ckh"><b>([^<]*)<\/b><span>([^<]*)<\/span><\/div>/g)].map(m => [m[1], m[2]]);
      const kL = h => (/<p class="roi-note roi-ckm">([^<]*)<\/p>/.exec(kOf(h)) || [])[1];
      // the box without its numbers / reasons / days / coverage text: the same in every state (groups, tiles, labels, the
      // note) — with the CSS pins (fixed heads, fixed coverage line, one-line values, two-line reasons), one height
      const kSk = h => kOf(h).replace(/<div class="roi-kv">[^]*?<\/div>/g, '<div class="roi-kv"></div>').replace(/<div class="roi-ks">[^<]*<\/div>/g, '<div class="roi-ks"></div>')
        .replace(/(<div class="roi-ckh"><b>[^<]*<\/b><span>)[^<]*(<\/span>)/g, '$1$2').replace(/(<p class="roi-note roi-ckm">)[^<]*/, '$1')
        .replace(/ roi-k[gb]"/g, '"').replace(' aria-busy="true"', '');
      const KS = [], seen = h => { KS.push(h); return h; };
      const fm = (x, sg, dp) => { const a = Math.abs(x); return (x < 0 ? '−' : sg && x > 0 ? '+' : '') + '$' + (dp ? a.toFixed(dp) : Math.round(a).toLocaleString('en-US')); };
      const pm = v => (v.startsWith('−') ? -1 : 1) * +v.replace(/[^0-9.]/g, '');          // a printed money value → its number
      const num = td => { const t = td.replace(/<small>[^]*?<\/small>/g, '').replace(/<[^>]+>/g, '').trim(); return t === '—' ? null : +t.replace(/[^0-9.]/g, ''); };
      const colSum = (h, i) => trs(h).reduce((a, r) => a + (num(r[i < 0 ? r.length + i : i]) || 0), 0);
      // an independent recount of the group "Spend pata wale din" (+ Poori history's revenue): mode 'usd' (the $ view: $ as
      // the rows hold them), 'inr' (a ₹ view of a file not billed in ₹: $ × today), 'bill' (₹ as billed: the bill + the so far
      // at the day's billed rate — the row's ₹ ÷ $, a spend-0 day: rate[X] of the All rows, else today); rounded as printed
      const rcA = (rows, mode, today, rate) => { const o = { s: 0, r: 0, n: 0, lo: '', hi: '', rv: 0, nrv: 0, kx: 0, nz: 0, nt: 0 };
        for (const q of rows) { const u = q[3], so = q[8];
          if (so != null) { o.rv += so; o.nrv++; }
          if (u == null) continue; if (so == null) { o.kx++; continue; }
          const d1 = u > 0 ? q[13] / u : rate && rate[q[0]];
          if (mode === 'bill' && !(u > 0) && d1 == null && so) o.nt++;
          o.s += mode === 'bill' ? q[13] : mode === 'inr' ? u * today : u;
          o.r += mode === 'bill' ? so * (d1 != null ? d1 : today) : mode === 'inr' ? so * today : so;
          o.n++; if (!(u > 0)) o.nz++; if (!o.lo) o.lo = q[0]; o.hi = q[0]; }
        const mx = Math.max(o.s, o.r), dp = mx >= 10 ? 0 : mx >= 1 ? 1 : 2, f = 10 ** dp;
        return Object.assign(o, { S: Math.round(o.s * f) / f, R: Math.round(o.r * f) / f, P: (Math.round(o.r * f) - Math.round(o.s * f)) / f, dp }); };
      // the printed group "Spend pata wale din": [Spend, Revenue, Profit, ROAS] as numbers + whether Revenue − Spend = Profit exactly
      const aNum = h => { const k = kT(h); const v = k.slice(0, 4).map(x => x[1]); const [S, R, P_] = v.slice(0, 3).map(pm);
        return [S, R, P_, v[3], Math.round((R - S) * 100) === Math.round(P_ * 100)]; };
      ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$'; U.lifeView([], null, {});
      U.setCTY(''); U.set('GRAIN', 'day'); U.set('MET', 'roas'); U.set('SHOW', 60);
      // made up by hand: 5 install days — 2 Jan: spend not known; 3 Jan: so far not read yet; 4 Jan: ads paused (spend 0, 0)
      const kr = (X, n, sp, spi, s_) => [X, n, null, sp, null, 0, null, T.map(() => null), s_, X, null, 'N/A', 0, spi];
      const dk = { v: 1, T, lags: 31, newest: '2026-01-05', rows: [kr('2026-01-01', 100, 10, 900, 30), kr('2026-01-02', 50, null, null, 5),
        kr('2026-01-03', 20, 4, 360, null), kr('2026-01-04', 0, 0, 0, 0), kr('2026-01-05', 30, 6, 540, 3)] };
      const hk = seen(U.cohCard(dk));
      out.k_usd = [kT(hk), kH(hk), kL(hk)];
      out.k_usd_cls = kCls(hk);
      // the same numbers the table prints: Σ its Spend column, Σ its "So far" column, Σ its Installs column
      out.k_usd_table = [colSum(hk, 3), colSum(hk, -1), colSum(hk, 2)];
      // where it sits: under the title row, right above the control row (country chips · grain · mode), above the table
      out.k_place = [hk.includes('cell pe ruko = detail</span></div>' + kOf(hk) + '<div class="roi-ctl">'), (hk.match(/class="roi-cks"/g) || []).length,
        hk.indexOf('roi-cks') < hk.indexOf('<table'), (U.dayView(dk).match(/class="roi-cks"/g) || []).length, U.ctyView(appFile()).includes('roi-cks'),
        kOf(hk).includes('<p class="roi-note roi-ckn">Do group kyun: country ka spend data ~1 saal ka hi hai — Profit / loss + ROAS sirf un dino ka jinka spend pata hai (upar: Revenue − Spend = Profit); har din ki kamai Poori history me.</p>')];
      // ₹ billed (₹90 a $ on every day, today ₹100): the bill + each day's so far at its own billed rate; a ₹ view of a file
      // not billed in ₹: $ × 100 throughout
      ctx.curView = () => 'INR'; ctx.cfx = () => 100; ctx.csym = () => '₹';
      U.lifeView([], null, { ccy: 'INR' });
      const hki = seen(U.cohCard(dk));
      out.k_inr = [kT(hki), kL(hki)];
      out.k_inr_table = colSum(hki, 3);
      U.lifeView([], null, {});
      out.k_inr_usd = kT(seen(U.cohCard(dk)));
      ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
      // 🧾 the owner's case, made up (21 Oct 2026, a country in ₹: "profit loss me wrong lag raha he"): 30 old days with
      // revenue but no spend data, 20 ads days at a loss, 5 ads-paused days (spend 0 + revenue), 3 ads days at a gain, the 2
      // newest days' so far not read yet; each day billed at its own rate (₹82 / 82.5 / 83 / 83.5 a $), today ₹88
      const ow = [];
      for (let i = 0; i < 60; i++) { const rt = 82 + (i % 4) * 0.5, u = i < 30 ? null : i >= 50 && i < 55 ? 0 : 20;
        ow.push(kr(day('2025-03-01', i), 10, u, u == null ? null : u * rt, i >= 58 ? null : i < 30 ? 10 : i < 50 ? 18 : i < 55 ? 4 : 30)); }
      const dow = { v: 1, T, lags: 31, newest: ow[59][0], rows: ow };
      const how = seen(U.cohCard(dow));
      out.k_own_usd = [kT(how), kCls(how), kH(how), kL(how), aNum(how), rcA(ow, 'usd')];
      ctx.curView = () => 'INR'; ctx.cfx = () => 88; ctx.csym = () => '₹'; U.lifeView([], null, { ccy: 'INR' });
      const hob = seen(U.cohCard(dow));
      out.k_own_inr = [kT(hob), kCls(hob), kH(hob), kL(hob), aNum(hob), rcA(ow, 'bill', 88)];
      U.lifeView([], null, {});
      const hon = seen(U.cohCard(dow));
      out.k_own_inr_usd = [kT(hon).slice(0, 4), aNum(hon), rcA(ow, 'inr', 88)];
      ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
      // days with no ads (spend 0) are IN the group with their revenue: 3 × ($0, $100) + 3 × ($100, $80)
      const dz = { v: 1, T, lags: 31, newest: '2026-01-06', rows: [1, 2, 3].map(i => kr('2026-01-0' + i, 10, 0, 0, 100))
        .concat([4, 5, 6].map(i => kr('2026-01-0' + i, 10, 100, 8300, 80))) };
      const hz = seen(U.cohCard(dz));
      out.k_zero = [kT(hz), kCls(hz).slice(2, 4), trs(hz).filter(r => r[3].replace(/<[^>]+>/g, '') !== '$0.00').map(r => r[r.length - 1].replace(/<[^>]+>/g, ''))];
      // a ₹-billed file, the rupee moved (billed at ₹83, today ₹88): the same days in ₹ and $, the same sign
      const dr = { v: 1, T, lags: 31, newest: '2026-01-02', rows: [kr('2026-01-01', 10, 100, 8300, 98), kr('2026-01-02', 10, 100, 8300, 98)] };
      const kr$ = [kT(seen(U.cohCard(dr))), kCls(U.cohCard(dr)).slice(2, 4)];
      ctx.curView = () => 'INR'; ctx.cfx = () => 88; ctx.csym = () => '₹'; U.lifeView([], null, { ccy: 'INR' });
      const hr = seen(U.cohCard(dr));
      out.k_rate = [kr$, [kT(hr), kCls(hr).slice(2, 4)], trs(hr).map(r => [r[3], r[r.length - 1]].map(x => x.replace(/<[^>]+>/g, '')))];
      // crore-size ₹ (billed) totals: printed in full — 14+ characters a size smaller (roi-ckw), the tile one height
      const dc7 = { v: 1, T, lags: 31, newest: '2026-01-02', rows: [kr('2026-01-01', 1234567, 2800000, 234567890, 1600000), kr('2026-01-02', 10, 100, 8300, 98)] };
      const dc8 = { v: 1, T, lags: 31, newest: '2026-01-02', rows: [kr('2026-01-01', 1234567, 28000000, 2345678900, 16000000), kr('2026-01-02', 10, 100, 8300, 98)] };
      const hc7 = seen(U.cohCard(dc7)), hc8 = seen(U.cohCard(dc8));
      out.k_big = [kT(hc7).map(x => x[1]), kT(hc8).map(x => x[1]),
        [hc7, hc8].map(h => [...kOf(h).matchAll(/<div class="roi-kv">([^]*?)<\/div>/g)].map(m => m[1].startsWith('<span class="roi-ckw">'))), aNum(hc7), aNum(hc8)];
      U.lifeView([], null, {});
      ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
      // a loss (red), no spend at all (organic: no ROAS), nothing at all
      const hl = seen(U.cohCard({ v: 1, T, lags: 31, newest: '2026-01-02', rows: [kr('2026-01-01', 10, 50, null, 10), kr('2026-01-02', 10, 10, null, 2)] }));
      out.k_loss = [kT(hl).slice(0, 4), kCls(hl).slice(2, 4)];
      const hg = seen(U.cohCard({ v: 1, T, lags: 31, newest: '2026-01-02', rows: [kr('2026-01-01', 10, 0, null, 4), kr('2026-01-02', 10, 0, null, 2)] }));
      out.k_org = [kT(hg).slice(0, 4), kH(hg)];
      const hn = seen(U.cohCard({ v: 1, T, lags: 31, newest: '2026-01-02', rows: [] }));
      out.k_none = [kT(hn), kH(hn), kL(hn)];
      // the grain, the mode and "Show more" never change it (every install day, not the rows on screen)
      const kb = kOf(U.cohCard(appFile()));
      out.k_inv = [];
      for (const g of ['day', 'week', 'month']) for (const m of ['roas', 'rev', 'ltv', 'delta']) for (const sh of [60, 1e9]) {
        U.set('GRAIN', g); U.set('MET', m); U.set('SHOW', sh); out.k_inv.push(kOf(U.cohCard(appFile())) === kb); }
      U.set('GRAIN', 'day'); U.set('MET', 'roas'); U.set('SHOW', 60);
      // All countries (spend known on every day): both groups shown, "Poori history" without a second revenue
      const hall = seen(U.cohCard(appFile()));
      out.k_all = [kT(hall), kH(hall), kL(hall), rcA(appFile().rows, 'usd')];
      // 🌍 countries: a pick loads (… , aria-busy) then its own totals; All with the country part = All without it
      const KF = new Set();
      ctx.fetchGzJson = u => new Promise((ok_, no) => setTimeout(() => { const f = u.split('?')[0];
        return !KF.has(f) && PACKS[f] ? ok_(JSON.parse(JSON.stringify(PACKS[f]))) : no(new Error('x')); }, 0));
      const P0 = 'roi_aaaaaaaaaaaa_c00.json.gz', P1 = 'roi_aaaaaaaaaaaa_c01.json.gz';
      const dkc = Object.assign(appFile(), { cd: Object.assign(cdx(), { packs: [[P0, 'k0k0k0k0k0k0'], [P1, 'k1k1k1k1k1k1']] }) });
      const fd4 = x => { const p_ = x.split('-'); return (+p_[2]) + ' ' + MON[+p_[1] - 1] + ' ' + p_[0]; };
      // what the strip must print for a country's rows ($ view): the recount + every reason
      // "Not split": the group is its known-spend days (spend only — no revenue to pair)
      const rcK = rows => { const k = rows.filter(r => r[3] != null), s = k.reduce((a, r) => a + r[3], 0), dp = s >= 10 ? 0 : s >= 1 ? 1 : 2;
        return { s, S: Math.round(s * 10 ** dp) / 10 ** dp, dp, n: k.length, lo: k.length ? k[0][0] : '', hi: k.length ? k[k.length - 1][0] : '', kx: 0, nz: 0, nrv: 0, rv: 0 }; };
      const exp = (rows, cc) => { const o = cc === 'XX' ? rcK(rows) : rcA(rows, 'usd'), D = rows.length, has = o.n > 0 && cc !== 'XX', nn = rows.filter(r => r[1] != null);
        const K = D - o.nrv, unk = rows.filter(r => r[3] == null).length, mr = rows.filter(r => r[3] == null && r[8] != null).length, same = cc !== 'XX' && o.nrv > 0 && !mr;
        return [['Spend', o.n ? fm(o.S, false, o.dp) : '—', cc === '--' ? 'Google Ads me ye country nahi' : cc === 'XX' ? 'Not split · Google Ads' : !(D - unk) ? 'spend data nahi' : o.kx ? `${o.kx} din bahar: kamai nahi padhi` : has && !(o.s > 0) ? 'Is country me koi ads din nahi' : o.nz ? `Google Ads · ${o.nz} din spend 0` : 'Google Ads'],
          ['Revenue', has ? fm(o.R, false, o.dp) : '—', cc === 'XX' ? 'Not split: koi kamai nahi' : 'so far · AdMob-matched'],
          ['Profit / loss', has ? fm(o.P, true, o.dp) : '—', cc === 'XX' ? 'Not split: sirf spend' : 'revenue − spend'],
          ['ROAS', has && o.S > 0 ? Math.round(o.R / o.S * 100) + '%' : '—', cc === 'XX' ? 'Not split: sirf spend' : has && !(o.S > 0) ? 'spend 0 — ROAS nahi' : 'revenue ÷ spend'],
          ['Total revenue', same ? 'Same days' : o.nrv ? fm(o.rv, false, o.rv >= 10 ? 0 : 1) : '—', cc === 'XX' ? 'Not split: koi kamai nahi' : same ? 'upar wala Revenue — wahi din' : 'so far · AdMob-matched'],
          ['Installs', nn.length ? nn.reduce((a, r) => a + r[1], 0).toLocaleString('en-US') : '—', cc === 'XX' ? 'Not split: installs nahi' : 'GA4 · ads + organic'],
          ['Install days', String(D), cc === 'XX' ? 'Not split: kamai nahi' : K ? `${K} din ki kamai abhi nahi padhi` : 'har din ki kamai padhi'],
          [['Spend pata wale din', o.n ? `${fd4(o.lo)} – ${fd4(o.hi)} (${o.n} din)` : cc === '--' ? 'Google Ads me ye country nahi' : 'Is country me spend wala koi din nahi'],
            ['Poori history', `${fd4(rows[0][0])} – ${fd4(rows[D - 1][0])}`]]]; };
      const kAll = h => kT(h).concat([kH(h)]);
      out.k_allcd = [kOf(seen(U.cohCard(dkc))) === kb];
      U.setCTY('AA');
      const kl = seen(U.cohCard(dkc)); await flush(); const ka = seen(U.cohCard(dkc)), ra = U.ccSrc(dkc).rows;
      out.k_load = [kT(kl).map(x => x[1]), kOf(kl).includes('aria-busy="true"'), !kOf(ka).includes('aria-busy'), kl.includes('ka data load ho raha hai'), kH(kl), kL(kl)];
      const oa = rcA(ra, 'usd');
      out.k_aa = [kAll(ka), exp(ra, 'AA'), kL(ka), ra.length, ra.filter(r => r[3] == null).length, oa.n, oa.nz, aNum(ka)];
      out.k_aa_inv = [];
      for (const g of ['day', 'week', 'month']) for (const m of ['roas', 'rev', 'ltv', 'delta']) {
        U.set('GRAIN', g); U.set('MET', m); out.k_aa_inv.push(kOf(U.cohCard(dkc)) === kOf(ka)); }
      U.set('GRAIN', 'day'); U.set('MET', 'roas');
      U.setCTY('BB'); const kbb = seen(U.cohCard(dkc));                          // the same pack: at once, its own totals
      out.k_bb = [kAll(kbb), exp(U.ccSrc(dkc).rows, 'BB'), kOf(kbb) !== kOf(ka)];
      // "Unknown country": no Google Ads spend → '—' (never 0), its revenue only in Poori history; "Not split": spend only
      U.setCTY('--'); seen(U.cohCard(dkc)); await flush();
      const kn = seen(U.cohCard(dkc));
      out.k_unk = [kAll(kn), exp(U.ccSrc(dkc).rows, '--'), kL(kn)];
      U.setCTY('XX');
      const kx = seen(U.cohCard(dkc)), rx = U.ccSrc(dkc).rows;
      out.k_xx = [kAll(kx), exp(rx, 'XX'), kL(kx), rx.filter(r => r[3] == null).length, rx.filter(r => r[8] != null).length];
      // a country in ₹ as billed whose ads-paused days take that day's rate from the All rows (the app billed that day):
      // odd paise everywhere — Revenue − Spend = Profit to the rupee, = an independent recount
      const ca = [], cr = [], rate = {};
      for (let i = 0; i < 40; i++) { const X = day('2025-06-01', i), rt = 82.11 + (i % 5) * 0.23, uA = 50.17 + i, sA = Math.round(uA * rt * 100) / 100;
        ca.push([X, 100, 80, uA, null, 0, null, T.map(() => null), 60.5, X, null, 'Normal', 0, sA]); rate[X] = sA / uA;
        const u = i < 15 ? null : i >= 30 && i < 35 ? 0 : i < 30 ? 7.31 + (i % 3) * 0.13 : 9.07;
        cr.push([X, 20, null, u, null, 0, null, T.map(() => null), i >= 38 ? null : i < 15 ? 3.17 : i < 30 ? 6.83 : i < 35 ? 2.41 : 12.9, X, null, 'N/A', 0,
          u == null ? null : u ? Math.round(u * rt * 100) / 100 : 0]); }
      PACKS['roi_cccccccccccc_c00.json.gz'] = { v: 1, b: 'b0b0b0b0b0b0', key: 'cccccccccccc', ix: 0, c: { AA: cr } };
      const dcr = Object.assign(appFile(), { rows: ca, newest: ca[39][0], cd: Object.assign(cdx(), { packs: [['roi_cccccccccccc_c00.json.gz', 'c0c0c0c0c0c0'], [P1, 'k1k1k1k1k1k1']] }) });
      U.setCTY('AA'); ctx.curView = () => 'INR'; ctx.cfx = () => 88; ctx.csym = () => '₹'; U.lifeView([], null, { ccy: 'INR' });
      seen(U.cohCard(dcr)); await flush();
      const hcr = seen(U.cohCard(dcr)), rcr = U.ccSrc(dcr).rows;
      out.k_cty_inr = [kT(hcr), kH(hcr), kL(hcr), aNum(hcr), rcA(rcr, 'bill', 88, rate), rcA(rcr, 'bill', 88)];
      U.lifeView([], null, {}); ctx.curView = () => 'USD'; ctx.cfx = () => 1; ctx.csym = () => '$';
      const hcu = seen(U.cohCard(dcr));
      out.k_cty_usd = [kT(hcu), aNum(hcu), rcA(rcr, 'usd')];
      // a pack that does not load / a country the app does not have / an app without the country part: '—' or All's own
      KF.add(P1);
      const dke = Object.assign(appFile(), { cd: Object.assign(cdx(), { packs: [[P0, 'k0k0k0k0k0k0'], [P1, 'k2k2k2k2k2k2']] }) });
      U.setCTY('EE'); seen(U.cohCard(dke)); await flush();
      const ke = seen(U.cohCard(dke));
      KF.clear();
      out.k_err = [kT(ke).map(x => x[1]), !kOf(ke).includes('aria-busy'), ke.includes('ka data load nahi hua'), kH(ke), kL(ke)];
      U.setCTY('AA');
      const dko = Object.assign(appFile(), { cd: Object.assign(cdx(), { c: [['QQ', 10, 1, null, 0, 0, 0]], packs: [['roi_bbbbbbbbbbbb_c00.json.gz', 'aaaaaaaaaaaa']] }) });
      const kq = seen(U.cohCard(dko));
      out.k_miss = [kT(kq).map(x => x[1]), kq.includes('ka data nahi')];
      const kno = seen(U.cohCard(appFile()));
      out.k_nocd = [kOf(kno) === kb, kno.includes('ki country-wise table nahi')];
      U.setCTY('');
      // one height in every state: the same box (groups, tiles, labels, the note), fixed heads + coverage line, one-line
      // values / two-line reasons that fit a 360 px phone
      out.k_skel = [new Set(KS.map(kSk)).size, KS.length];
      // every label / value / reason printed in those states (crore-size ₹ included), each value with its group and size
      // (roi-ckw or not): test_roi_frontend.py measures them against each width's value box (the page's own CSS numbers)
      out.k_print = KS.flatMap(h => { const g = kOf(h).indexOf('<b>Poori history</b>');
        return [...kOf(h).matchAll(/<div class="roi-kl">([^<]*)<\/div><div class="roi-kv">([^]*?)<\/div><div class="roi-ks">([^<]*)<\/div>/g)]
          .map(m => [m[1], m[2].replace(/<[^>]+>/g, ''), m[2].startsWith('<span class="roi-ckw">'), m[3], m.index > g ? 'B' : 'A']); });
      out.k_texts = KS.map(h => [kH(h), kL(h)]);
    }
    const F1 = ['roi_aaaaaaaaaaaa_c01.json.gz'];
    out.cc_nojump = { w375: await noJump(375, dc, PACKS, F1), w1280: await noJump(1280, dc, PACKS, F1) };
    out.cc_late = (await noJump(375, dc, PACKS, [], 'late')).late;
    out.more_keep = await moreKeepAll(dc, PACKS);
    }
    // the hub card line
    const x = { st: 'normal', line: 'Money back in ~108 days' };
    ctx.roiCardLine(x, 'Alpha Pick');
    out.card = x.line;
  } catch (e) { errors.push(String(e && e.stack || e)); }
  console.log(JSON.stringify({ errors, out }));
})();
