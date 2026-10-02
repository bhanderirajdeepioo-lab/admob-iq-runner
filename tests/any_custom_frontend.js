// 📦 Update impact's two tabs and the 📅 Any date tab's Custom compare — rendered for real: runs the dashboard script
// (frontend/index.html's largest <script>) in a node vm with stub browser globals (a localStorage that records — or
// throws), a scripted /api/marks, and the files tests/test_any_custom_frontend.py writes (a synthetic app built by the
// real engines: its Uninstall detail, Active users detail, install-day cohorts and impact_any file; and hand-made daily
// series), and prints ONE JSON report; the Python test asserts on it.
//   usage: node any_custom_frontend.js <script.js> <dir with fx.json>
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const [scriptPath, dir] = process.argv.slice(2);
const FX = JSON.parse(fs.readFileSync(path.join(dir, 'fx.json'), 'utf8'));
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
// a localStorage that records every write, or throws on every call (a browser that blocks storage)
const LS = { data: {}, sets: [], throws: false };
const localStorage = {
  getItem: k => { if (LS.throws) throw new Error('SecurityError'); return Object.prototype.hasOwnProperty.call(LS.data, k) ? LS.data[k] : null; },
  setItem: (k, v) => { if (LS.throws) throw new Error('SecurityError'); LS.data[k] = String(v); LS.sets.push([k, String(v)]); },
  removeItem: k => { if (LS.throws) throw new Error('SecurityError'); delete LS.data[k]; },
};
const NET = { log: [], api: 'ok', confirm: true, old: false };
const SERVER = { marks: [], cmps: [], next: 1, nextc: 1, me: 'team@example.test', admin: false };
const jres = (status, obj) => ({ ok: status >= 200 && status < 300, status, type: 'basic', json: async () => JSON.parse(JSON.stringify(obj)) });
async function api(u, opt) {
  if (NET.api === 'down') throw new TypeError('Failed to fetch');
  const method = (opt && opt.method) || 'GET', b = opt && opt.body ? JSON.parse(opt.body) : null;
  const both = () => NET.old ? { marks: SERVER.marks } : { marks: SERVER.marks, compares: SERVER.cmps };
  if (method === 'GET') return jres(200, { ...both(), me: SERVER.me, admin: SERVER.admin });
  if (u === '/api/marks' && b && 'before_from' in b) {
    if (NET.old) { const m = { id: SERVER.next++, app_id: b.app_id, date: b.date, name: b.name }; return jres(400, { error: 'bad_request', field: 'date', msg: 'Date galat hai' }); }
    const c = { id: SERVER.nextc++, app_id: b.app_id, name: b.name, before_from: b.before_from, before_to: b.before_to, after_from: b.after_from, after_to: b.after_to, who: SERVER.me, at: '2026-09-20T05:00:00.000Z' };
    SERVER.cmps.push(c); return jres(200, { ok: true, compare: c, dup: false, ...both() }); }
  if (u === '/api/marks') { const m = { id: SERVER.next++, app_id: b.app_id, date: b.date, name: b.name, who: SERVER.me, at: '2026-09-20T05:00:00.000Z' };
    SERVER.marks.push(m); return jres(200, { ok: true, mark: m, dup: false, ...both() }); }
  if (u === '/api/marks/delete') { if (b.kind === 'compare') SERVER.cmps = SERVER.cmps.filter(x => x.id !== b.id); else SERVER.marks = SERVER.marks.filter(x => x.id !== b.id);
    return jres(200, { ok: true, id: b.id, kind: b.kind || 'date', ...both() }); }
  return jres(404, { error: 'not_found', msg: 'Nahi mila' });
}
async function fakeFetch(url, opt) {
  const u = String(url);
  NET.log.push({ url: u, method: (opt && opt.method) || 'GET', body: (opt && opt.body) || null });
  await Promise.resolve();
  if (u.startsWith('/api/marks')) return api(u, opt);
  return new Promise(() => {});                       // (every file is handed to the page directly)
}
const DOM = {};                                       // the few elements the handlers touch (by id)
const document = new Proxy({}, { get: (t, k) => k === 'getElementById' ? (id => (id in DOM ? DOM[id] : any)) : (k === 'activeElement' ? null : any) });
const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document, localStorage, sessionStorage: localStorage, navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', reload() {} }, history: any,
  fetch: fakeFetch, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream: any, Response: any, Blob: any, AbortController: any,
  URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise, Array, Object, Number, String, Boolean,
  RegExp, Error, TypeError, Set, Map, Float64Array, Uint8Array, isNaN, isFinite, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
  performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 375, innerHeight: 812, scrollTo() {}, alert() {},
  confirm: () => NET.confirm, IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any,
};
ctx.globalThis = ctx; ctx.self = ctx;
vm.createContext(ctx);
try { vm.runInContext(fs.readFileSync(scriptPath, 'utf8'), ctx, { filename: 'index.js' }); } catch (e) { errors.push('TOPLEVEL ' + e.message); }
const run = code => vm.runInContext(code, ctx);
const J = JSON.stringify;
const text = h => String(h).replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
const tight = h => String(h).replace(/<[^>]*>/g, '').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
const cut = (h, a, b) => { const i = h.indexOf(a); if (i < 0) return ''; const j = b ? h.indexOf(b, i + a.length) : -1; return h.slice(i, j < 0 ? undefined : j); };
const tick = async (n = 6) => { for (let i = 0; i < n; i++) await new Promise(r => setImmediate(r)); };
ctx.__FX = FX;
const R = { errors };
async function step(name, fn) { try { await fn(); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + ((e.stack || '').match(/at [^\n]*/g) || []).slice(0, 4).join(' < ')); } }
const rowsOf = h => { const out = {};
  for (const m of h.matchAll(/<tr data-row="([a-z_0-9]+)">([\s\S]*?)<\/tr>(?:<tr class="any-why" id="[^"]*" data-why="\1"(?: hidden)?><td colspan="5">([\s\S]*?)<\/td><\/tr>)?/g)) {
    const cells = [...m[2].matchAll(/<td class="any-n[^"]*" data-h="[^"]*">([\s\S]*?)<\/td>/g)].map(x => text(x[1]));
    const st = (m[2].match(/<td class="st">([\s\S]*?)<\/td>$/) || [])[1] || '';
    out[m[1]] = { cells, st: (st.match(/data-st="([a-z]+)"/) || [])[1] || null, stt: text(st), why: m[3] ? text(m[3]) : '' }; }
  return out; };

// ── the synthetic app (built by the real engines) on the page ──
run(`DATA = {apps_catalog: __FX.catalog, today_date: __FX.today, latest_complete: __FX.today, generated_at: __FX.today + 'T03:30:00Z', currency: 'USD', usd_inr: 84,
    placements: [], alerts: {counts: {}, items: []}, range_alerts: [], uninstall: {apps: [{app_id: __FX.app.app_id, app: __FX.app.app}], asset: 'uninstall.json.gz', asset_v: 1, status: 'ok'},
    active: {apps: [__FX.arow], currency: 'USD'}};
  UNI = {apps: [__FX.udet], consts: Object.assign({lag_days: 2, min_pp: 2, min_rel: 0.1}, {impact: __FX.consts})}; UNIERR = false; CURVIEW = 'USD'; APP = ''; UNIAPP = '';
  ACTD[__FX.arow.key] = __FX.adet; UNICOH[__FX.udet.key] = uniCohPrep(__FX.coh);
  UANY.idx = {v: 1, file_v: 1, apps: [__FX.entry]}; UANY.F[__FX.app.app_id] = __FX.body; UANY.marks = []; UANY.cmps = []; UANY.me = 'team@example.test';
  setApp = function (a) { APP = a; };`);
const A = () => run('UNI.apps[0]');
const card = () => String(run('uniImpactCard(UNI.apps[0])'));
const box = () => String(run('uniAnyBox(UNI.apps[0])'));

(async () => {
  // ── 1. the cross-check: Mode B with Before = X−N…X−1, After = X+1…X+N gives the engine's own before / after (the file) ──
  await step('xcheck', async () => {
    R.xcheck = JSON.parse(run(`(()=>{ const a=UNI.apps[0], P=anyPrepB(a), F=UANY.F[a.app_id], DP={users:0,pct:5,num:3,sec:1,usd1k:4}, out={};
      const rnd=(v,d)=>v==null?null:+(+v).toFixed(d), PER=['returning_dau','sessions','time','arpdau'];
      for(const N of [7,14,30,60]){ const o=out[N]={full:{},after:{},skipped:0};
        for(let i=0;i<F.n;i++){ const X=uniAdd(F.first,i), D=anyDecode(F,X), W=D&&D[String(N)]; if(!W) continue;
          const bf=uniAdd(X,-N), bt=uniAdd(X,-1), af=uniAdd(X,1), at=uniAdd(X,N);
          for(const sp of ANY_BM){ const [k,u,,,sh]=sp, R=W.rows[k], S=P.S[k]; if(!R||!S) continue;
            const fin=!!S.lf&&at<=S.lf, full=fin&&R.n_before===N&&R.n_after===N&&R.from_b===uniAdd(bf,-sh)&&R.to_b===uniAdd(bt,-sh)&&R.from_a===af&&R.to_a===at;
            const aOnly=!full&&N>=14&&fin&&PER.includes(k)&&R.n_after===N&&R.from_a===af&&R.to_a===at;
            if(!full&&!aOnly){ o.skipped++; continue; }
            const r=anyRowB(P,sp,bf,bt,af,at), d=DP[u], c=(full?o.full:o.after)[k]||((full?o.full:o.after)[k]={n:0,exact:0,digit:0,bad:[]});
            for(const [ev,mv] of full?[[R.before,r.b],[R.after,r.a]]:[[R.after,r.a]]){ if(ev==null) continue; c.n++; const m=rnd(mv,d);
              if(m===+ev) c.exact++; else if(m!=null&&Math.abs(m-ev)<=Math.pow(10,-d)*1.0001) c.digit++; else if(c.bad.length<3) c.bad.push([X,ev,m]); } } } }
      return JSON.stringify(out); })()`));
  });

  // ── 2. the computation on hand-made days (every number known): means, pooled per user, came back (install days shifted),
  //       same day uninstall, the final-day cut, ⏳ Too early, the noise test (a step / flat), short history, left-out days ──
  await step('hand', async () => {
    run(`ACTD[__FX.hand.arow.key] = __FX.hand.adet; UNICOH[__FX.hand.udet.key] = uniCohPrep(__FX.hand.coh);
      DATA.active.apps.push(__FX.hand.arow); UNI.apps.push(__FX.hand.udet);`);
    const H = R.hand = {};
    for (const c of FX.hand.cases) {
      const o = JSON.parse(run(`(()=>{ const a=UNI.apps[1], P=anyPrepB(a), C=${J(c)}, out={};
        for(const sp of ANY_BM){ const r=anyRowB(P,sp,C.bf,C.bt,C.af,C.at); out[sp[0]]={b:r.b,a:r.a,st:r.st,sub:r.sub,why:r.why,perDay:r.perDay,bs:r.bs,as:r.as,z:r.z==null?null:r.z,nulls:r.nulls||0}; }
        return JSON.stringify(out); })()`));
      H[c.id] = o; }
    // the card of one of them (ranges, its notes, the one-line note, the table)
    run(`UANY.app = ''; UANY.cmp.sub = 'rng'; uniAnyBox(UNI.apps[1]); Object.assign(UANY, {tab: 'any', mode: 'cmp'});
      Object.assign(UANY.cmp, ${J({ sub: 'rng', bf: FX.hand.cases[1].bf, bt: FX.hand.cases[1].bt, af: FX.hand.cases[1].af, at: FX.hand.cases[1].at, cid: 0 })});`);
    const h = String(run('uniAnyBox(UNI.apps[1])'));
    H.card = { title: tight(cut(h, '<div class="any-rt">', '</div>')), dl: tight(cut(h, '<div class="any-dl">', '</div>')),
      notes: [...cut(h, '<div class="any-res"', '<div class="uni-scroll">').matchAll(/<div class="uni-any-note">([\s\S]*?)<\/div>/g)].map(m => text(m[1])),
      foot: text(cut(h, '<div class="any-foot">', '</div></div>')), heads: [...cut(h, '<thead>', '</thead>').matchAll(/<th>([^<]*)<\/th>/g)].map(m => m[1]),
      rows: rowsOf(cut(h, '<div class="any-res"')), save: text(cut(h, '<div class="any-save"', '</div></div>')), pickers: (h.match(/>\d+ days<\/button>/g) || []).length };
    R.text_hand = text(h);
  });

  // ── 3. the ranges: two ranges / date vs date, the checks, the quick picks, the defaults ──
  await step('ranges', async () => {
    const G = R.ranges = {};
    const rg = o => JSON.parse(run(`(()=>{ Object.assign(UANY.cmp, ${J(o)}); return JSON.stringify(anyRangesB()); })()`));
    G.ok = rg({ sub: 'rng', bf: '2026-08-01', bt: '2026-08-07', af: '2026-09-01', at: '2026-09-07' });
    G.swap = rg({ sub: 'rng', bf: '2026-09-01', bt: '2026-09-07', af: '2026-08-01', at: '2026-08-07' });
    G.overlap = rg({ sub: 'rng', bf: '2026-08-01', bt: '2026-08-10', af: '2026-08-05', at: '2026-08-20' });
    G.backwards = rg({ sub: 'rng', bf: '2026-08-07', bt: '2026-08-01', af: '2026-09-01', at: '2026-09-07' });
    G.long = rg({ sub: 'rng', bf: '2025-01-01', bt: '2026-02-10', af: '2026-03-01', at: '2026-03-07' });
    G.wait = rg({ sub: 'rng', bf: '2026-08-01', bt: '', af: '2026-09-01', at: '2026-09-07' });
    G.dates = rg({ sub: 'dates', x: '2026-09-01', y: '2026-08-01', n: 7 });
    G.dates_close = rg({ sub: 'dates', x: '2026-08-01', y: '2026-08-05', n: 7 });
    G.dates_wait = rg({ sub: 'dates', x: '2026-08-01', y: '', n: 14 });
    // the quick picks and the first look: from the app's last final day (the Active users file's settled_till)
    const pre = k => JSON.parse(run(`(()=>{ anyPreset(${J(k)}, UNI.apps[0], true); const C=UANY.cmp; return JSON.stringify([C.bf,C.bt,C.af,C.at]); })()`));
    G.presets = { prev: pre('prev'), '4w': pre('4w'), prev30: pre('prev30') };
    G.last_final = run('anyLastFinal(UNI.apps[0])');
    run(`UANY.app = ''; UANY.mode = 'cmp'; UANY.tab = 'any'; Object.assign(UANY.cmp, {bf:'',bt:'',af:'',at:''})`);
    const h = box();
    G.first_look = JSON.parse(run('JSON.stringify([UANY.cmp.bf, UANY.cmp.bt, UANY.cmp.af, UANY.cmp.at])'));
    G.first_title = tight(cut(h, '<div class="any-rt">', '</div>'));
    // a validation message is said, nothing drawn; the swap is said
    run(`Object.assign(UANY.cmp, {sub:'rng', bf:'2026-08-01', bt:'2026-08-10', af:'2026-08-05', at:'2026-08-20'})`);
    G.overlap_html = text(cut(box(), '<div class="uni-any-note">⚠️', '</div>')); G.overlap_no_card = !box().includes('<div class="any-res"');
    const pick = '2026-07-01' < FX.app.first ? FX.app.first : '2026-07-01';
    run(`Object.assign(UANY.cmp, {sub:'rng', bf:${J(FX.swap[0])}, bt:${J(FX.swap[1])}, af:${J(FX.swap[2])}, at:${J(FX.swap[3])}})`);   // the later range given as Pehle
    G.swap_note = [...cut(box(), '<div class="any-res"', '<div class="uni-scroll">').matchAll(/<div class="uni-any-note">([\s\S]*?)<\/div>/g)].map(m => text(m[1]));
    // date vs date: ONE window picker (Days from each), its call
    run(`Object.assign(UANY.cmp, {sub:'dates', x:${J(FX.swap[0])}, y:${J(FX.swap[2])}, n:14})`);
    const hd = box();
    G.dates_pickers = (hd.match(/>\d+ days<\/button>/g) || []).length; G.dates_on = (hd.match(/<button class="on" onclick="uniAnyN\((\d+)\)">/) || [])[1];
    G.dates_title = tight(cut(hd, '<div class="any-rt">', '</div>'));
    run(`uniAnyN(30)`); G.n_after = run('UANY.cmp.n');
    run(`Object.assign(UANY.cmp, {sub:'rng'})`); G.rng_pickers = (box().match(/>\d+ days<\/button>/g) || []).length;
  });

  // ── 4. the tabs: 📦 Updates | 📅 Any date, remembered per browser (imp_tab_uni), a jump opens 📦 Updates; ONE picker ──
  await step('tabs', async () => {
    const T = R.tabs = {};
    run(`UANY.tab = undefined; UANY.mode = undefined; UANY.app = ''`); LS.data = {}; LS.sets = [];
    let h = card();
    T.default = (h.match(/aria-selected="true" aria-controls="uni-imp-pane" class="on" title="[^"]*" onclick="uniImpTab\('([a-z]+)'\)"/) || [])[1];
    T.tablist = /<div class="any-tabs" role="tablist" aria-label="Update impact"><button type="button" role="tab" id="uni-imp-tab-upd"/.test(h);
    T.labels = [...cut(h, '<div class="any-tabs"', '</div>').matchAll(/role="tab"[^>]*>([^<]*)<\/button>/g)].map(m => m[1]);
    T.updates_has_blocks = /class="uni-imp-b on"/.test(h) && !h.includes('<div class="uni-any"');
    T.section_picker = h.includes('uni-imp-cseg');
    T.block_pickers = (h.match(/<div class="uni-imp-seg">/g) || []).length;           // one, inside the open block
    T.open_blocks = (h.match(/class="uni-imp-b on"/g) || []).length;
    run(`uniImpTab('any')`); T.saved = LS.sets.slice();
    h = card(); T.any_box = h.includes('<div class="uni-any" id="uni-any" data-mode="date">') && !/class="uni-imp-b/.test(h);
    T.any_pickers = (h.match(/>\d+ days<\/button>/g) || []).length;
    run(`UANY.tab = undefined`); T.remembered = (card().match(/aria-selected="true"[^>]*onclick="uniImpTab\('([a-z]+)'\)"/) || [])[1];
    run(`uniAnyMode('cmp')`); T.mode_saved = LS.data.imp_any_mode;
    run(`UANY.mode = undefined`); T.mode_remembered = run('anyMode()');
    // a jump to an update's block opens 📦 Updates (not remembered as the choice)
    const key = run(`uniImpBlocks(UNI.apps[0])[1].key`);
    run(`UNIAPP = UNI.apps[0].app_id; uniImp(${J(key)})`); T.after_jump = run('UANY.tab'); T.jump_saved = LS.data.imp_tab_uni;
    T.after_jump_card = /aria-selected="true"[^>]*onclick="uniImpTab\('upd'\)"/.test(card());
    // a browser that blocks storage: no error, 📦 Updates
    LS.throws = true; run(`UANY.tab = undefined; UANY.mode = undefined`);
    let ok = true; try { card(); run(`uniImpTab('any')`); card(); } catch (e) { ok = false; }
    T.blocked_ok = ok; T.blocked_default = (() => { run('UANY.tab = undefined'); return run('anyTab()'); })(); LS.throws = false;
    // the uni card has no card-wide window any more (no hidden default from this browser)
    LS.data.imp_win_uni = '30'; run(`UNIIMPWIN = undefined`); T.uni_win = run('impS("uni").win');
    // an auto-refresh (a new build: every data object replaced, the screens re-drawn from state): the tab, the mode, the
    // ranges, the typed name and an open "Kyun?" are all still there
    run(`UANY.tab = 'any'; UANY.mode = 'cmp'; UANY.app = UNI.apps[0].app_id; UANY.name = 'Typed naam';
      Object.assign(UANY.cmp, {sub: 'rng', bf: ${J(FX.swap[2])}, bt: ${J(FX.swap[3])}, af: ${J(FX.swap[0])}, at: ${J(FX.swap[1])}, cid: 0}); UANY.why = {'b-returning_dau': true};`);
    const before = card();
    run(`DATA = JSON.parse(JSON.stringify(DATA)); UNI = JSON.parse(JSON.stringify(UNI)); ACTD[__FX.arow.key] = JSON.parse(JSON.stringify(ACTD[__FX.arow.key]));`);
    const after = card();
    T.refresh = { same: before === after, tab: /aria-selected="true"[^>]*onclick="uniImpTab\('any'\)"/.test(after), mode: after.includes('data-mode="cmp"'),
      ranges: [FX.swap[2], FX.swap[3], FX.swap[0], FX.swap[1]].every((d, i) => after.includes(`id="any-${['bf', 'bt', 'af', 'at'][i]}"`) && after.includes(`value="${d}"`)),
      name: after.includes('value="Typed naam"'), why: /<tr class="any-why" id="any-w-b-returning_dau" data-why="returning_dau"><td/.test(after),
      ids: ['any-bf', 'any-bt', 'any-af', 'any-at', 'uni-any-nm'].every(id => after.includes(`id="${id}"`)) };
    run(`UANY.name = ''; UANY.why = {}`);
  });

  // ── 5. 💾 a custom compare: saved through /api/marks (its ranges), listed, opened by a tap, deleted with kind "compare" ──
  await step('save', async () => {
    const S = R.save = {};
    run(`UANY.tab = 'any'; UANY.mode = 'cmp'; UANY.app = UNI.apps[0].app_id; UANY.name = ''; UANY.msg = ''; Object.assign(UANY.cmp, {sub:'rng', bf:${J(FX.swap[2])}, bt:${J(FX.swap[3])}, af:${J(FX.swap[0])}, at:${J(FX.swap[1])}, cid:0})`);
    let h = box();
    S.disabled = /id="uni-any-sv" disabled/.test(h); S.label = text(cut(h, '<label class="any-sl"', '</label>'));
    S.placeholder = (h.match(/id="uni-any-nm" maxlength="80" placeholder="([^"]*)"/) || [])[1];
    run(`uniAnyName('Diwali vs pehle')`); S.enabled = /<button type="button" class="uni-any-btn" id="uni-any-sv" onclick/.test(box());
    const n0 = NET.log.length; S.ok = await run('uniAnySave()');
    const p = NET.log.slice(n0).find(x => x.method === 'POST'); S.body = p ? JSON.parse(p.body) : null; S.msg = run('UANY.msg');
    h = box(); S.chips = [...cut(h, '<div class="uni-any-mks">', '</div>').matchAll(/<button type="button" class="uni-any-mk([^"]*)" data-cmp="(\d+)"[^>]*>([\s\S]*?)<\/button>/g)].map(m => [m[2], text(m[3]), m[1].includes('on')]);
    S.del_button = /data-delc="1"/.test(h); S.title = tight(cut(h, '<div class="any-rt">', '</div>'));
    // a tap on it (from Around a date): Custom compare, its ranges, its name
    run(`UANY.mode = 'date'; Object.assign(UANY.cmp, {bf:'',bt:'',af:'',at:'',cid:0}); UANY.name = ''; uniAnyCmp(1)`);
    S.opened = JSON.parse(run('JSON.stringify({mode: UANY.mode, r: [UANY.cmp.bf, UANY.cmp.bt, UANY.cmp.af, UANY.cmp.at], name: UANY.name, cid: UANY.cmp.cid})'));
    // the star: saved for every app
    run(`uniAnyName('Sab apps'); uniAnyStar(true)`); const n1 = NET.log.length; await run('uniAnySave()');
    const p2 = NET.log.slice(n1).find(x => x.method === 'POST'); S.star_app = p2 ? JSON.parse(p2.body).app_id : null; run('uniAnyStar(false)');
    // delete the one on screen (2, the "*" one): kind "compare"; it is no longer the open one
    S.cid_before = run('UANY.cmp.cid');
    const n2 = NET.log.length; await run('uniAnyDelC(2)'); const dp = NET.log.slice(n2).find(x => x.url === '/api/marks/delete');
    S.del_body = dp ? JSON.parse(dp.body) : null; S.gone = !run('UANY.cmps').some(x => x.id === 2) && run('UANY.cmps').some(x => x.id === 1); S.cid_after = run('UANY.cmp.cid');
    // a date mark's delete keeps the older body {id}
    SERVER.marks.push({ id: 7, app_id: FX.app.app_id, date: FX.swap[0], name: 'Ek date', who: 'team@example.test', at: '2026-09-20T05:00:00.000Z' });
    await run('anyMarksP()'); const n3 = NET.log.length; await run('uniAnyDel(7)');
    const dp2 = NET.log.slice(n3).find(x => x.url === '/api/marks/delete'); S.del_date_body = dp2 ? JSON.parse(dp2.body) : null;
    // a Worker from before compares: the list still reads (no compares), saving one says why it failed
    NET.old = true; run('UANY.marks = null; UANY.cmps = []'); await run('anyMarksP()'); S.old_list = JSON.parse(run('JSON.stringify([UANY.marks.length, UANY.cmps.length, UANY.marksErr])'));
    run(`uniAnyName('Purana server')`); S.old_ok = await run('uniAnySave()'); S.old_msg = run('UANY.msg'); NET.old = false;
  });

  R.text_any = text(box());
  process.stdout.write(JSON.stringify(R));
})().catch(e => { errors.push('MAIN ' + e.message); process.stdout.write(JSON.stringify(R)); });
