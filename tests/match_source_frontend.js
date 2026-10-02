// The page's own match / show arithmetic (frontend/index.html) over SYNTHETIC placement daily rows
// [date, earn_micros, impressions, ad_requests, matched_requests, clicks]: sumDaily (Ad-units table, Report Card, app
// totals), adDailySeries (the App report's daily panel) and the Countries tab's per-country rates. Runs the real page
// script in a node vm with inert browser stubs. Prints one JSON report; tests/test_match_source_frontend.py asserts on it.
// usage: node match_source_frontend.js <script.js>
const fs = require('fs'), vm = require('vm');
const [scriptPath] = process.argv.slice(2);
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const errors = [];
const store = { getItem: () => null, setItem() {}, removeItem() {} };
const ctx = {
  console: { log() {}, warn() {}, error: (...a) => errors.push(a.join(' ')) },
  window: any, document: any, localStorage: store, sessionStorage: store,
  navigator: any, location: { href: '', search: '', hash: '', pathname: '/', reload() {} }, history: any,
  fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String,
  Set, Map, Float64Array, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent, performance: { now: () => 0 },
  getComputedStyle: () => any, innerWidth: 375, innerHeight: 812, scrollTo() {}, alert() {}, confirm: () => false,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const out = {};
function get(name, code) { try { out[name] = JSON.parse(run(code)); } catch (e) { errors.push(name + ': ' + e.message); } }
// two days of one ad unit: day 1 a normal day, day 2 shows more impressions than it matched (an ad matched the day
// before and shown that day) — AdMob reports that ratio as is
run(`DATA = {placements: [{id: 'u1', app: 'Demo App', daily: [
        ['2026-07-20', 95000000, 9800, 11500, 10900, 98],
        ['2026-07-21', 50000000, 5500, 6000, 5000, 55]]}],
      countries_daily: {'Demo App': {'XX': [['2026-07-21', 50000000, 5500, 6000, 5000, 55]]}},
      today_date: '2026-07-22', latest_complete: '2026-07-21'};`);
get('sum_both', `JSON.stringify(sumDaily(DATA.placements[0].daily, new Set(['2026-07-20','2026-07-21'])))`);
get('sum_day2', `JSON.stringify(sumDaily(DATA.placements[0].daily, new Set(['2026-07-21'])))`);
get('series', `JSON.stringify(adDailySeries('Demo App'))`);
process.stdout.write(JSON.stringify({ errors, out }));
