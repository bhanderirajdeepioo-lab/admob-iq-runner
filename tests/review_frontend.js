// The Review tab's frontend contract (SPEC_REVIEW §C.11): runs the REAL dashboard script (frontend/index.html's largest
// <script>) in a node vm with stub browser globals and calls its pure review functions — rvEsc, rvRt, rvMoney, rvEffSt,
// rvIsAttn, rvLayout, rvCardHtml, rvSummaryHtml, rvCalendarHtml, rvDayColor, rvChartSvg and the RV_TXT strings — on the
// committed synthetic fixture (tests/fixtures/review_sample.json: index.json + the open day's card document written by
// admob_iq.review, a synthetic GET day response and /me; see tests/review_synth.py). Prints ONE JSON report;
// tests/test_review_frontend.py asserts on it.   usage: node review_frontend.js <script.js> <review_sample.json>
'use strict';
const fs = require('fs'), vm = require('vm');
const [scriptPath, fixturePath] = process.argv.slice(2);
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const errors = [];
const store = () => ({ getItem: () => null, setItem() {}, removeItem() {} });
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document: any, localStorage: store(), sessionStorage: store(),
  navigator: any, location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', origin: 'http://localhost', reload() {} },
  history: any, fetch: () => new Promise(() => {}), setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0,
  clearInterval() {}, requestAnimationFrame: () => 0, cancelAnimationFrame() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean,
  RegExp, Error, TypeError, Set, Map, WeakMap, Symbol, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat,
  encodeURIComponent, decodeURIComponent, performance: { now: () => 0 },
  getComputedStyle: () => any, innerWidth: 375, innerHeight: 812, scrollTo() {}, alert() {}, confirm: () => false,
  prompt: () => null, IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any,
  HTMLElement: any, Node: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); }
catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const FX = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const DOC = FX.day, IDX = FX.index, ST = FX.state, ME = FX.me;
ctx.__DOC = DOC; ctx.__IDX = IDX;
ctx.__S = Object.assign({}, ST, { me: ME, open_day: IDX.open_day });
ctx.__S_TEAM = Object.assign({}, ST, { me: Object.assign({}, ME, { email: 'team@example.test', admin: false }), open_day: IDX.open_day });
ctx.__S0 = { d: DOC.day, open_day: IDX.open_day, writable: true, rev: 0, states: {}, notes: [], flags: [], snoozes: [],
             prev: null, log: [], me: ME };
const out = { errors, fns: {}, scen: {} };
const FNS = ['rvEsc', 'rvRt', 'rvMoney', 'rvEffSt', 'rvIsAttn', 'rvLayout', 'rvCardHtml', 'rvSummaryHtml',
             'rvCalendarHtml', 'rvDayColor', 'rvChartSvg'];
for (const f of FNS) { try { out.fns[f] = run(`typeof ${f}`); } catch (e) { out.fns[f] = 'error'; } }
try { out.rv_txt_type = run('typeof RV_TXT'); out.RV_TXT = run('typeof RV_TXT==="object"&&RV_TXT?JSON.parse(JSON.stringify(RV_TXT)):null'); }
catch (e) { out.rv_txt_type = 'error'; errors.push('RV_TXT: ' + e.message); }
// the dashboard globals the review functions may read (curView() via CURVIEW, DATA)
try {
  run(`DATA = Object.assign({}, (typeof DATA==='object'&&DATA)||{}, {currency:'USD', usd_inr: __DOC.fx || 88,
        apps: __DOC.apps.map(a => ({name: a.dname})), apps_catalog: __DOC.apps.map(a => ({app_id: a.app_id, app_name: a.dname, selected: true}))});
       CURVIEW = 'USD';`);
} catch (e) { errors.push('setup: ' + e.message); }
function scen(name, code) {
  try { const v = run(code); out.scen[name] = (v === undefined) ? '__undefined__' : JSON.parse(JSON.stringify(v)); }
  catch (e) { errors.push(name + ': ' + e.message + ' @ ' + ((e.stack || '').match(/at [^\n]*/g) || []).slice(0, 3).join(' < ')); }
}
const J = JSON.stringify;
const keys = DOC.apps.map(a => a.key);
// ── escaping + money ──
scen('esc', `rvEsc('<img src=x onerror="a(1)"> & \\'q\\'')`);
const RT = ['Note <img src=x onerror=alert(1)> & ', { usd: 166.2, s: '/din', sign: 0, p: 0 }, ' · ', { usd: -200, s: '', sign: 1, p: 0 }];
ctx.__RT = RT;
scen('rt_usd', `CURVIEW='USD'; rvRt(__RT)`);
scen('rt_plain', `CURVIEW='USD'; rvRt('plain <b>bold</b>')`);
scen('rt_inr', `(() => { CURVIEW='INR'; try { return rvRt(__RT); } finally { CURVIEW='USD'; } })()`);
const MONEY = [[166.2, '/din', 0, 0], [3.456, '', 0, 2], [12.5, '', 0, 2], [-200, '/din', 1, 0], [200, '', 1, 0], [3.5, '', 0, 0],
               [1234.5, '', 0, 0], [100, '', 0, 0], [2000, '/din', 0, 0], [200000, '', 0, 0], [0.5, '', 0, 2], [0, '', 1, 0]];
ctx.__MONEY = MONEY;
scen('money_usd', `CURVIEW='USD'; __MONEY.map(a => rvMoney(a[0], a[1], a[2], a[3]))`);
scen('money_inr', `(() => { CURVIEW='INR'; try { return __MONEY.map(a => rvMoney(a[0], a[1], a[2], a[3])); } finally { CURVIEW='USD'; } })()`);
// ── layout rules (§C.5) ──
scen('layout', `rvLayout(__DOC, __S)`);
scen('layout_empty', `rvLayout(__DOC, __S0)`);
scen('eff', `(() => { const o = {}; for (const a of __DOC.apps) { o[a.key] = {}; for (const [f] of __DOC.feats) o[a.key][f] = rvEffSt(__DOC, __S, a.key, f); } return o; })()`);
scen('attn', `(() => { const o = {}; for (const a of __DOC.apps) o[a.key] = rvIsAttn(__DOC, __S, a.key); return o; })()`);
scen('attn_empty', `(() => { const o = {}; for (const a of __DOC.apps) o[a.key] = rvIsAttn(__DOC, __S0, a.key); return o; })()`);
// ── cards ──
for (const mode of ['live', 'history', 'history_admin']) {
  scen('cards_' + mode, `(() => { const o = {}; for (const a of __DOC.apps) o[a.key] = String(rvCardHtml(__DOC, __S, a.key, ${J(mode)})); return o; })()`);
}
scen('cards_team', `(() => { const o = {}; for (const a of __DOC.apps) o[a.key] = String(rvCardHtml(__DOC, __S_TEAM, a.key, 'live')); return o; })()`);
scen('cards_inr', `(() => { CURVIEW='INR'; try { return String(rvCardHtml(__DOC, __S, (__DOC.apps.find(a => a.f.kamai.st === 'red') || __DOC.apps[0]).key, 'live')); } finally { CURVIEW='USD'; } })()`);
scen('cards_empty', `(() => { const o = {}; for (const a of __DOC.apps) o[a.key] = String(rvCardHtml(__DOC, __S0, a.key, 'live')); return o; })()`);
// ── summary ──
scen('summary_admin', `String(rvSummaryHtml(__DOC, __S, __S.me))`);
scen('summary_team', `String(rvSummaryHtml(__DOC, __S_TEAM, __S_TEAM.me))`);
scen('summary_empty', `String(rvSummaryHtml(__DOC, __S0, __S0.me))`);
// ── history calendar ──
const CAL = {}; const days = IDX.days.map(x => x.d);
if (days[0]) CAL[days[0]] = { rev: IDX.days[0].apps, kal: 0, flag: 1, notes: 2, people: 2 };
if (days[1]) CAL[days[1]] = { rev: 3, kal: 1, flag: 0, notes: 0, people: 1 };
ctx.__CAL = CAL;
scen('cal_days', J(days));
scen('calendar', `String(rvCalendarHtml(__IDX, __CAL, __IDX.open_day))`);
scen('calendar_sel', `String(rvCalendarHtml(__IDX, __CAL, ${J(days[0] || '')}))`);
scen('daycolor', `[rvDayColor(7,{rev:7}), rvDayColor(7,{rev:9}), rvDayColor(7,{rev:3}), rvDayColor(7,{rev:0}), rvDayColor(7,undefined),
                   rvDayColor(0,undefined), rvDayColor(undefined,undefined), rvDayColor(1,{rev:1})]`);
// ── charts ──
const charts = [];
for (const a of DOC.apps) for (const [f] of DOC.feats) { const d = a.f[f].detail; if (d && d.chart) charts.push(d.chart); }
charts.push({ cap: 'Synthetic gaps', labels: ['1 Sep', '2 Sep', '3 Sep', '4 Sep'], vals: [null, 3, null, 0], fmt: 'usd', tips: null,
              before: null, after_idx: null, marks: [] });
charts.push({ cap: 'Synthetic flat', labels: ['1 Sep', '2 Sep'], vals: [0, 0], fmt: 'p100', tips: ['a', 'b'], before: 0,
              after_idx: 1, marks: [[1, 'Shuru · v1.0.8']] });
ctx.__CHARTS = charts;
scen('charts', `__CHARTS.map(c => String(rvChartSvg(c)))`);
scen('chart_caps', J(charts.map(c => c.cap)));
// ── review fixes: decided whole-app 🚩, today's 🚩 lifts, small-app chip, decision review days, a newer day ──
const APP = k => DOC.apps.find(a => a.key === k);
ctx.__K = keys;
ctx.__SMALL_NB = (DOC.apps.find(a => a.small && (a.nb || []).length) || {}).key || null;
// a whole-app flag raised today: open → "flag"; once decided (theek / kaam) → reviewed (+ note when there is one)
scen('st_flag', `(() => { const k = __K[0], base = JSON.parse(JSON.stringify(__S));
  base.states[k] = {st: 'flag', who: 'team@example.test', at: __DOC.day + 'T05:00:00.000Z', snz: []};
  const f = {id: 90, day: __DOC.day, app: k, app_label: '', feature: null, note: '', raised_by: 'team@example.test',
             raised_at: __DOC.day + 'T05:00:00.000Z', status: 'open', decision: null};
  const S1 = {...base, flags: base.flags.concat([f])};
  const S2 = {...base, flags: base.flags.concat([{...f, status: 'closed', decision: 'theek', dec_by: 'owner@example.test',
             dec_at: __DOC.day + 'T06:00:00.000Z', dec_day: __DOC.day}])};
  const S3 = {...S2, notes: base.notes.concat([{id: 9, app: k, text: 'n', who: 'team@example.test', at: 'x'}])};
  return {open: rvStOf(S1, k), decided: rvStOf(S2, k), decided_note: rvStOf(S3, k), card: String(rvCardHtml(__DOC, S2, k, 'live')),
          hist_later: rvStOf(rvHistS({...S2, flags: S2.flags.map(x => x.id === 90 ? {...x, dec_day: '2099-01-01'} : x)}, __DOC.day), k)}; })()`);
// a 🚩 raised TODAY on a card of the "Sab theek" / small group lifts it to the top
scen('lift_today', `(() => { const L0 = rvLayout(__DOC, __S0), k = L0.ok[0] || L0.small[0];
  const f = {id: 91, day: __DOC.day, app: k, feature: 'ads', status: 'open', decision: null};
  const L1 = rvLayout(__DOC, {...__S0, flags: [f]}), L2 = rvLayout(__DOC, {...__S0, flags: [{...f, status: 'kaam', decision: 'kaam'}]});
  return {k, before: L0.top.indexOf(k), after: L1.top.indexOf(k), kaam: L2.top.indexOf(k)}; })()`);
scen('small_chip', `__SMALL_NB ? {small: String(rvCardHtml(__DOC, __S0, __SMALL_NB, 'live')),
  lifted: String(rvCardHtml(__DOC, {...__S0, flags: [{id: 92, day: __DOC.day, app: __SMALL_NB, feature: null, status: 'open'}]}, __SMALL_NB, 'live'))} : null`);
// History: a decision made while the day was still open (dec_day = that day) counts for it even when the IST clock had
// moved on; a decision on a later review day is shown as still open
scen('hist_decday', `(() => { const d = __DOC.day, k = __K[1];
  const f = {id: 93, day: d, app: k, feature: 'kamai', note: '', raised_by: 'team@example.test', raised_at: d + 'T05:00:00.000Z',
             status: 'closed', decision: 'theek', dec_by: 'owner@example.test', dec_note: null,
             dec_at: rvAddDays(d, 1) + 'T00:30:00.000Z', dec_day: d};
  const same = rvHistS({...__S0, flags: [f]}, d).flags[0], later = rvHistS({...__S0, flags: [{...f, dec_day: rvAddDays(d, 1)}]}, d).flags[0];
  const legacy = rvHistS({...__S0, flags: [{...f, dec_day: null}]}, d).flags[0];
  return {same: same.status, later: later.status, legacy: legacy.status,
          log_same: String(rvLogHtml(__DOC, {...__S0, flags: [f]}, k)), log_next: String(rvLogHtml({...__DOC, day: rvAddDays(d, 1)}, {...__S0, d: rvAddDays(d, 1), flags: [f]}, k))}; })()`);
// admin view "Band": flags closed within the last 14 REVIEW days
scen('band', `(() => { const d = __DOC.day, k = __K[1];
  const mk = (id, back) => ({id, day: rvAddDays(d, -back - 1), app: k, app_label: '', feature: 'ads', note: '', raised_by: 'team@example.test',
    raised_at: rvAddDays(d, -back - 1) + 'T05:00:00.000Z', status: 'closed', decision: 'band', dec_note: 'band karo', dec_by: 'owner@example.test',
    dec_at: rvAddDays(d, -back) + 'T05:00:00.000Z', dec_day: rvAddDays(d, -back)});
  const S = {...__S0, flags: [mk(94, 1), mk(95, 14), mk(96, 20)], me: __S.me};
  const h = String(rvSummaryHtml(__DOC, S, __S.me)), p = h.split('<summary>Closed (')[1]; return p ? parseInt(p, 10) : -1; })()`);
// a newer open day: Aaj view goes read-only; a 409 day_moved does the same; an OLDER open_day (stale cache) does not
scen('newday', `(() => { const d = __DOC.day, r = {};
  RV.doc = __DOC; RV.S = {...__S, writable: true}; RV.me = __S.me; RV.auth = true; RV.newDay = null;
  r.can0 = rvCanWrite();
  rvFail({ok: false, err: 'conflict', why: 'day_moved', msg: 'x', data: {open_day: rvAddDays(d, -1)}}); r.older = RV.newDay;
  rvFail({ok: false, err: 'conflict', why: 'day_moved', msg: 'x', data: {open_day: rvAddDays(d, 1)}}); r.newer = RV.newDay; r.can1 = rvCanWrite();
  r.msg = rvRoMsg(); RV.newDay = null;
  rvApplyDay({...__S, d, open_day: rvAddDays(d, 1), rev: 99}, true); r.poll = RV.newDay;
  RV.newDay = null;
  let body = null; const f0 = fetch; fetch = (u, o) => { body = o && o.body; return new Promise(() => {}); };
  try { rvAction(null, 't', d, {app: __K[0], act: 'ok'}, null, null); r.live_body = body ? JSON.parse(body) : null;
        body = null; RV.histDay = d; RV.hS[d] = {...__S}; rvAction(null, 'h', d, {app: __K[0], act: 'note', note: 'n'}, null, null);
        r.hist_body = body ? JSON.parse(body) : null; } finally { fetch = f0; }
  RV.doc = null; RV.S = null; RV.me = null; return r; })()`);
// index.json load: only a real 404 / an empty list is "not started"; a network error (offline, Access login redirect) or
// a 5xx is a load failure with "Phir koshish karo" (async: rvLoad awaits the stubbed fetch)
async function ascen(name, code) {
  try { const v = await vm.runInContext(code, ctx); out.scen[name] = JSON.parse(JSON.stringify(v === undefined ? '__undefined__' : v)); }
  catch (e) { errors.push(name + ': ' + e.message); }
}
(async () => {
  const idxErr = (stub) => `(async () => { const f0 = fetch; fetch = ${stub}; RV.idx = null; RV.doc = null; RV.S = null; RV.idxErr = null;
    try { await rvLoad(); return RV.idxErr; } finally { fetch = f0; RV.idx = null; RV.idxErr = null; } })()`;
  await ascen('idx_net', idxErr(`() => Promise.reject(new TypeError('Failed to fetch'))`));
  await ascen('idx_404', idxErr(`() => Promise.resolve({ ok: false, status: 404 })`));
  await ascen('idx_503', idxErr(`() => Promise.resolve({ ok: false, status: 503 })`));
  await ascen('idx_empty', idxErr(`() => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ v: 1, days: [], open_day: null }) })`));
  process.stdout.write(JSON.stringify(out));
})();
