// "Nothing may be missing from Update impact" (owner, 1 Oct): renders the Uninstall tab's 📦 Update impact card — every
// app, every update block opened in turn, at every window the block carries (7 / 14 / 30 / 60) — and the All-apps
// "📦 Updates ka asar" list with the REAL dashboard script of two versions (the card as it was at 3339e07, when it was
// shown on both Uninstall and Active users, and today's), in node vms with stub browser globals, on the same data. Each
// render is reduced to its structure (sections, block keys, row ids, statuses, pills, windows, buttons) and the numbers
// it shows — label words may differ (SPEC_SIMPLIFY §6.4: "D1 return" → "Back next day", "pts" → "100 me", HALT →
// "Update roko" …; §1.1: a date's year only outside this year), so both texts go through today's smpInfoTxt and the
// "100 me" / "1,000 users" / year words come out before the numbers are read. Prints ONE JSON report;
// tests/test_impact_card_complete.py asserts on it.
//   usage: node impact_card_compare.js <old_script.js> <new_script.js> <data.json>
//   data.json: {dashboard_uninstall, asset, today_date?, generated_at?} (tests/fixtures/uninstall_sample.json has both)
'use strict';
const fs = require('fs'), vm = require('vm');
const [oldPath, newPath, dataPath] = process.argv.slice(2);
const F = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
const errors = [];

function makeCtx(scriptPath, tag) {
  const any = new Proxy(function () {}, {
    get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
    apply: () => any, construct: () => any, set: () => true, has: () => true,
  });
  const store = () => ({ getItem: () => null, setItem() {}, removeItem() {} });
  const ctx = {
    console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push(tag + ' console.error ' + a.join(' ')) },
    window: any, document: any, localStorage: store(), sessionStorage: store(), navigator: any,
    location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', reload() {} }, history: any,
    fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
    requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
    addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
    URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean,
    RegExp, Error, Set, Map, Float64Array, isNaN, isFinite, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
    performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 1280, innerHeight: 900, scrollTo() {}, alert() {},
    confirm: () => false, IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any,
  };
  ctx.globalThis = ctx; ctx.self = ctx;
  vm.createContext(ctx);
  try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: tag + '.js' }); } catch (e) { errors.push(tag + ' TOPLEVEL ' + e.message); }
  ctx.__U = F;
  const du = F.dashboard_uninstall || {};
  const today = F.today_date || du.data_till_max || '2026-09-25';
  vm.runInContext(`DATA = {apps_catalog: [], today_date: ${JSON.stringify(today)}, latest_complete: ${JSON.stringify(today)},
    generated_at: ${JSON.stringify(F.generated_at || today + 'T03:30:00Z')}, currency: 'USD', usd_inr: 84, placements: [],
    alerts: {counts: {}, items: []}, range_alerts: [], uninstall: __U.dashboard_uninstall};
    UNI = __U.asset; UNIERR = false; UNICOH = {}; CURVIEW = 'USD';`, ctx);
  return ctx;
}
const OLD = makeCtx(oldPath, 'old'), NEW = makeCtx(newPath, 'new');
const run = (ctx, code) => vm.runInContext(code, ctx);
const RESET = `APP=''; UNIAPP=''; RANGE='30d'; UNIIMPOPEN=''; UNIIMPALL=true; UNIIMPHOW=true; UNIIMPWK={}; UNIIMPWIN=null; UNIUPF=''; UNIUPALL=true; UNICPEXP=false; UNIPRE=false;`;
function render(ctx, tag, code) {
  try { return String(run(ctx, `(()=>{ ${RESET} ${code} })()`)); }
  catch (e) { errors.push(tag + ': ' + e.message); return ''; }
}

// ── reading a render ──
const dec = s => String(s).replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
// (a date's year: §1.1 prints it only outside the current year — 3339e07 also printed it for a date ~4 months back;
// the day and month are compared, the year word is not)
const norm = s => String(run(NEW, `smpInfoTxt(${JSON.stringify(dec(s))})`)).replace(/100 me /g, ' ').replace(/1,000 (users|ads)/g, ' ')
  .replace(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (19|20)\d\d\b/g, '$1');
// SPEC_SIMPLIFY's display rule (owner, 1 Oct): a bare point delta ("0 pts" / "−1.5") now always carries its own "%"
// ("0%" / "−1.5%") — same number, a trailing unit the old page omitted — so the % is stripped before comparing values
const nums = s => (norm(s).match(/[+−-]?\d[\d,]*(?:\.\d+)?%?/g) || []).map(x => x.replace(/%$/, '')).sort();
const cut = (h, a, b) => { const i = h.indexOf(a); if (i < 0) return ''; const j = b ? h.indexOf(b, i + a.length) : -1; return h.slice(i, j < 0 ? undefined : j); };
const pillClasses = s => [...s.matchAll(/<span class="pill ([^"]+)"/g)].map(m => m[1]).sort();
// "Revenue per user/day" (row arpdau): the engine stores it per 1,000 users; the old card printed that number (its label
// said "har 1,000 users se"), today's prints it PER USER (÷1,000, 3 significant digits below 1). On the OLD side the main
// value of the before / after cells is turned into today's per-user form, so the comparison still checks it exactly
const perUser = v => { const x = parseFloat(String(v).replace(/,/g, '')) / 1000, a = Math.abs(x); return a >= 1 ? a.toFixed(2) : String(+a.toPrecision(3)); };
let SIDE = 'new';
function rowsOf(t) {   // one table: every row id → {status, numbers in its value cells (not its label), its status cell's}
  const out = {};
  for (const m of t.matchAll(/<tr data-row="([a-z_0-9]+)">([\s\S]*?)<\/tr>/g)) {
    const cells = [...m[2].matchAll(/<td class="uni-num"[^>]*>([\s\S]*?)<\/td>/g)].map(x => x[1]);
    const st = (m[2].match(/<td class="st">([\s\S]*?)<\/td>/) || [])[1] || '';
    let cn = cells.map(nums);
    if (m[1] === 'arpdau' && SIDE === 'old') cn = cn.map((ns, i) => {
      if (i > 1 || !ns.length) return ns;   // before / after only (the change cell is a relative %, unchanged)
      const first = (norm(cells[i]).match(/[+−-]?\d[\d,]*(?:\.\d+)?%?/) || [])[0]; if (!first || /%$/.test(first)) return ns;
      const k = ns.indexOf(first); if (k < 0) return ns; const c = ns.slice(); c[k] = perUser(first); return c.sort(); });
    out[m[1]] = { st: (st.match(/data-st="([a-z]+)"/) || [])[1] || null, cells: cn, stn: nums(st) };
  }
  return out;
}
function cardOf(h) {
  const c = cut(h, 'id="uni-impact"', '<div class="card');
  if (!c) return null;
  const B = c.split('<div class="uni-imp-b').slice(1);
  const head = c.split('<div class="uni-imp-b')[0];
  // (the card-wide 7 / 14 / 30 / 60 is gone on purpose — owner, 2 Oct: ONE picker per update block, the open block's own
  // window buttons below are compared as before; the 📅 Any date tab is not part of the 3339e07 card)
  return {
    flags: (cut(head, 'class="uni-imp-m"', '</div>').match(/<span class="pill /g) || []).length,
    how: (cut(c, '<ul class="uni-imp-how">', '</ul>').match(/<li>/g) || []).length,
    empty: /class="uni-empty"/.test(head),
    older: nums(cut(c, 'Show older updates', '</span>')),
    blocks: B.map(b => {
      const hd = cut(b, '<div class="uni-imp-h"', '</div>'), open = /data-open="1"/.test(b.slice(0, 200));
      const o = { key: (b.match(/data-key="([^"]*)"/) || [])[1], open, lv: (hd.match(/data-lv="([a-z]+)"/) || [])[1] || null,
        head_pills: pillClasses(hd), head_nums: nums(hd) };
      if (!open) { o.mini = nums(cut(b, 'class="uni-imp-mini"', '</div>')); return o; }
      const main = cut(b, '<table class="uni-imp-t', '</table>');
      const ver = b.includes('Same days: new version vs old versions') || b.includes('uni-imp-sub') ? cut(b.slice(b.indexOf('uni-imp-sub')), '<table class="uni-imp-t', '</table>') : '';
      Object.assign(o, {
        seg: [...cut(b, 'class="uni-imp-seg"', '</span></div>').matchAll(/<button( class="on")?( disabled)?[^>]*>(\d+) days<\/button>/g)].map(m => [+m[3], !!m[1], !!m[2]]),
        meta: nums(cut(b, 'class="uni-imp-m"', '</div>')), meta_pills: pillClasses(cut(b, 'class="uni-imp-m"', '</div>')),
        young: /class="faint uni-imp-young"/.test(b), young_nums: nums(cut(b, 'class="faint uni-imp-young"', '</div>')),
        rows: rowsOf(main), heads: (main.match(/<th>/g) || []).length, head_nums: nums(cut(main, '<thead>', '</thead>')),
        split_rows: [...b.matchAll(/<tr class="uni-imp-sp" data-sp="([a-z_0-9]+)">/g)].map(m => m[1]),
        notes: /class="split[^"]*uni-imp-notes/.test(b), vnote: /class="faint uni-imp-vnote"/.test(b),
        ver_rows: ver ? rowsOf(ver) : {}, ver_sub: nums(cut(b, 'class="uni-imp-sub"', '<div class="uni-scroll"')),
        why: nums(cut(b, 'class="uni-imp-why"', '</div>')), verlnk: /class="uni-imp-ver"/.test(b) });
      return o; }) };
}
function updatesOf(h) {
  const c = cut(h, 'id="uni-updates"', '<div class="card');
  return [...c.matchAll(/<div class="uni-upd" data-lv="([a-z]+)" onclick="uniImpGo\('([^']*)','([^']*)'\)">([\s\S]*?)<span class="lnk go">/g)]
    .map(m => ({ app_id: m[2], key: m[3], lv: m[1], nums: nums(m[4]), late: /uni-late/.test(m[4]), pills: pillClasses(m[4]) }));
}

// ── every app × every block × every window it carries ──
const R = { renders: 0, apps: 0, blocks: 0, windows: 0, cards: [], diffs: [], list: null };
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
for (const a of (F.asset && F.asset.apps) || []) {
  const B = ((a.impact || {}).updates || []).filter(b => b && b.key);
  R.apps++;
  const cases = [['first', '']];
  for (const b of B) { R.blocks++; const W = [7].concat(Object.keys(b.by_window || {}).map(Number).filter(n => [14, 30, 60].includes(n)));
    for (const n of W) { cases.push([b.key + '@' + n, `UNIIMPOPEN=${JSON.stringify(b.key)}; UNIIMPWK={${JSON.stringify(b.key)}:${n}};`]); R.windows++; } }
  for (const [nm, set] of cases) {
    const code = `APP=${JSON.stringify(a.app)}; UNIAPP=${JSON.stringify(a.app_id)}; ${set} return uniScreen();`;
    const ho = render(OLD, 'old ' + a.app + ' ' + nm, code), hn = render(NEW, 'new ' + a.app + ' ' + nm, code);
    R.renders += 2;
    SIDE = 'old'; const co = cardOf(ho); SIDE = 'new'; const cn = cardOf(hn);
    const item = { app_id: a.app_id, case: nm, old: !!co, new: !!cn, same: eq(co, cn), blocks: co ? co.blocks.length : 0,
      rows: co ? co.blocks.reduce((t, b) => t + Object.keys(b.rows || {}).length + Object.keys(b.ver_rows || {}).length, 0) : 0,
      numbers: co ? JSON.stringify(co).match(/"[+−-]?\d[\d,]*(?:\.\d+)?%?"/g)?.length || 0 : 0 };
    R.cards.push(item);
    if (!item.same && R.diffs.length < 12) R.diffs.push({ app_id: a.app_id, case: nm, old: co, new: cn });
  }
}
// ── the All-apps "📦 Updates ka asar" list: every update of the old "Recent updates" (all shown), nothing dropped ──
{ const ho = render(OLD, 'old list', 'return uniScreen();'), hn = render(NEW, 'new list', 'return uniScreen();');
  const lo = updatesOf(ho), ln = updatesOf(hn), key = x => x.app_id + '|' + x.key;
  const N = new Map(ln.map(x => [key(x), x]));
  const missing = lo.filter(x => !N.has(key(x))).map(key), changed = [], fewer = [];
  for (const x of lo) { const y = N.get(key(x)); if (!y) continue;
    if (x.lv !== y.lv || x.late !== y.late) changed.push(key(x));
    const left = y.nums.slice(); for (const v of x.nums) { const i = left.indexOf(v); if (i < 0) { fewer.push([key(x), v]); break; } left.splice(i, 1); } }
  R.list = { old: lo.length, new: ln.length, missing, changed, numbers_missing: fewer, extra: ln.length - lo.length + missing.length,
    old_has: /id="uni-updates"/.test(ho), new_has: /id="uni-updates"/.test(hn) }; }

process.stdout.write(JSON.stringify({ errors, ...R }));
