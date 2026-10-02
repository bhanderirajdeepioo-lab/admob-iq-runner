// 📅 Compare any date (📦 Update impact's "📅 Any date" tab, Around a date) — the page contract, rendered for real: runs
// the dashboard script (frontend/index.html's largest <script>) in a node vm with stub browser globals and a SCRIPTED
// fetch (the synthetic impact_any files gzipped as the build writes them, the dashboard Worker's /api/marks), on the apps
// tests/test_impact_any_frontend.py builds with the real engine, and prints ONE JSON report; the Python test asserts on it.
//   usage: node impact_any_frontend.js <script.js> <dir with fx.json + impact_any_*.json.gz>
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path');
const [scriptPath, dir] = process.argv.slice(2);
const FX = JSON.parse(fs.readFileSync(path.join(dir, 'fx.json'), 'utf8'));
const errors = [];
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const store = () => ({ getItem: () => null, setItem() {}, removeItem() {} });

// ── the scripted network: static files + the marks API ──
const NET = { log: [], index: 'ok', api: 'ok', hold: null, confirm: false };
const SERVER = { marks: [], next: 1, me: 'team@example.test', admin: false };
const mk = (o) => Object.assign({ id: SERVER.next++, who: SERVER.me, at: '2026-09-20T05:00:00.000Z' }, o);
const res = (status, bytes, extra) => ({ ok: status >= 200 && status < 300, status, type: 'basic',
  arrayBuffer: async () => { const b = Buffer.from(bytes || ''); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); },
  json: async () => JSON.parse(Buffer.from(bytes || '').toString('utf8')), ...(extra || {}) });
const jres = (status, obj) => res(status, JSON.stringify(obj));
async function api(u, opt) {
  const m = NET.api;
  if (m === 'down') throw new TypeError('Failed to fetch');
  if (m === 'e500') return jres(500, { error: 'server_error', msg: 'Server me dikkat — thodi der baad try karo' });
  if (m === 'e401') return jres(401, { error: 'unauthorized', msg: 'Login zaroori — page reload karo' });
  if (m === 'e400') return jres(400, { error: 'bad_request', msg: 'Naam 1–80 akshar ka ho', field: 'name' });
  if (m === 'static404') return res(404, '<!doctype html><title>404</title>');
  if (m === 'hold') await new Promise(r => { NET.hold = r; });
  const method = (opt && opt.method) || 'GET', body = opt && opt.body ? JSON.parse(opt.body) : null;
  const live = () => SERVER.marks.slice().sort((p, q) => p.date < q.date ? 1 : (p.date > q.date ? -1 : q.id - p.id));
  if (method === 'GET' && u === '/api/marks') return jres(200, { marks: live(), me: SERVER.me, admin: SERVER.admin });
  if (method === 'POST' && u === '/api/marks') { const x = mk({ app_id: body.app_id, date: body.date, name: body.name }); SERVER.marks.push(x);
    return jres(200, { ok: true, mark: x, dup: false, marks: live() }); }
  if (method === 'POST' && u === '/api/marks/delete') { SERVER.marks = SERVER.marks.filter(x => x.id !== body.id); return jres(200, { ok: true, id: body.id, marks: live() }); }
  return jres(404, { error: 'not_found', msg: 'Nahi mila' });
}
async function fakeFetch(url, opt) {
  const u = String(url);
  NET.log.push({ url: u, method: (opt && opt.method) || 'GET', body: (opt && opt.body) || null, headers: (opt && opt.headers) || {},
    credentials: opt && opt.credentials, redirect: opt && opt.redirect });
  await Promise.resolve();
  if (u.startsWith('impact_any_index.json.gz?')) {
    if (NET.index === '404') return res(404, 'Not found');
    if (NET.index === 'net') throw new TypeError('Failed to fetch');
    return res(200, fs.readFileSync(path.join(dir, 'impact_any_index.json.gz')));
  }
  const f = u.match(/^(impact_any_[0-9a-f]{12}\.json\.gz)\?/);
  if (f) return fs.existsSync(path.join(dir, f[1])) ? res(200, fs.readFileSync(path.join(dir, f[1]))) : res(404, 'Not found');
  if (u.startsWith('/api/marks')) return api(u, opt);
  return new Promise(() => {});
}

const ctx = {
  console: { log() {}, info() {}, warn() {}, error: (...a) => errors.push('console.error ' + a.join(' ')) },
  window: any, document: any, localStorage: store(), sessionStorage: store(), navigator: any,
  location: { href: 'http://localhost/', search: '', hash: '', pathname: '/', reload() {} }, history: any,
  fetch: fakeFetch, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0, matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
  addEventListener() {}, removeEventListener() {}, DecompressionStream, Response, Blob, AbortController: any,
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
ctx.__FX = FX;
const [A, B, C, D] = FX.apps;
run(`DATA = {apps_catalog: __FX.catalog, today_date: ${J(FX.today)}, latest_complete: ${J(FX.today)}, generated_at: ${J(FX.today + 'T03:30:00Z')},
  currency: 'USD', usd_inr: 84, placements: [], alerts: {counts: {}, items: []}, range_alerts: [],
  uninstall: {apps: __FX.apps.map(a => ({app_id: a.app_id, app: a.app})), asset: 'uninstall.json.gz', asset_v: 1, status: 'ok'}};
  UNI = {apps: __FX.apps.filter(a => a.impact).map(a => ({app_id: a.app_id, app: a.app, impact: a.impact})), consts: {lag_days: 2}};
  UNIERR = false; CURVIEW = 'USD'; APP = ''; UNIAPP = '';
  var __AP = __FX.apps.map(a => ({app_id: a.app_id, app: a.app, impact: a.impact}));
  setApp = function (a) { APP = a; };   // (the header's App selector re-draws every screen: not this harness's business)`);
const text = h => String(h).replace(/<style[\s\S]*?<\/style>/g, '').replace(/<[^>]*>/g, ' ').replace(/&amp;/g, '&').replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
const tight = h => String(h).replace(/<[^>]*>/g, '').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();   // as the eye reads it
const cut = (h, a, b) => { const i = h.indexOf(a); if (i < 0) return ''; const j = b ? h.indexOf(b, i + a.length) : -1; return h.slice(i, j < 0 ? undefined : j); };
const tick = async (n = 6) => { for (let i = 0; i < n; i++) await new Promise(r => setImmediate(r)); };
const settle = async () => { for (let i = 0; i < 4; i++) { await tick(); const p = run('[UANYP.idx, UANYP.marks, ...Object.values(UANYP.F)].filter(Boolean)'); if (!p.length) break; await Promise.all(p); } await tick(); };
const card = i => String(run(`uniImpactCard(__AP[${i}])`));
run(`UANY.tab = 'any'; UANY.mode = 'date'`);           // the 📅 Any date tab, Around a date (the tab's own tests: test_any_custom_frontend)
const box = i => String(run(`uniAnyBox(__AP[${i}])`));
const set = o => run(`Object.assign(UANY, ${J(o)})`);
const fetches = re => NET.log.filter(x => re.test(x.url)).length;
const R = { errors, words: {} };
const TEXTS = {};
async function step(name, fn) { try { await fn(); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + ((e.stack || '').match(/at [^\n]*/g) || []).slice(0, 4).join(' < ')); } }

// a row of the 📅 card: its Pehle / Baad / Badlaav cells (visible text), its result key and words, its "Kyun?" text
function anyRows(h) {
  const out = {};
  for (const m of h.matchAll(/<tr data-row="([a-z_0-9]+)">([\s\S]*?)<\/tr>(?:<tr class="any-why" id="[^"]*" data-why="\1"(?: hidden)?><td colspan="5">([\s\S]*?)<\/td><\/tr>)?/g)) {
    const cells = [...m[2].matchAll(/<td class="any-n[^"]*" data-h="[^"]*">([\s\S]*?)<\/td>/g)].map(x => text(x[1]));
    const st = (m[2].match(/<td class="st">([\s\S]*?)<\/td>$/) || [])[1] || '';
    out[m[1]] = { cells, st: (st.match(/data-st="([a-z]+)"/) || [])[1] || null, stt: text(st), why: m[3] ? text(m[3]) : null, kyun: /class="any-why-b"/.test(st) };
  }
  return out;
}
// the first number of a cell as the owner reads it ("Actual: 12,345 Expected …" → "12,345")
const firstNum = c => /^—/.test(String(c)) ? '' : (String(c).replace(/^Actual: /, '').match(/\d+h \d+m|\d+m \d+s|[+−-]?[$₹]?\d[\d,]*(?:\.\d+)?%?/) || [''])[0];
// a row of a rendered block: its three value cells (visible text), its status (key + the numbers of its cell), its split
function rowsOf(h) {
  const out = {};
  for (const m of h.matchAll(/<tr data-row="([a-z_0-9]+)">([\s\S]*?)<\/tr>(?:<tr class="uni-imp-sp" data-sp="\1"><td colspan="5">([\s\S]*?)<\/td><\/tr>)?/g)) {
    const cells = [...m[2].matchAll(/<td class="uni-num"[^>]*>([\s\S]*?)<\/td>/g)].map(x => text(x[1]));
    const st = (m[2].match(/<td class="st">([\s\S]*?)<\/td>$/) || [])[1] || '';
    out[m[1]] = { cells, st: (st.match(/data-st="([a-z]+)"/) || [])[1] || null, stt: text(st), stn: (text(st).match(/\d[\d,.]*/g) || []), sp: m[3] ? text(m[3]) : null };
  }
  return out;
}
// two cell texts the same: every word equal, every number within one unit of its last shown digit (the file keeps a row's
// numbers to the precision the card shows — the engine's asset one more digit — so a last digit may round the other way)
const NUM = /[+−-]?\d[\d,]*(?:\.\d+)?/g;
function sameCell(a, b) {
  if (a === b) return 'exact';
  if (a.replace(NUM, '#') !== b.replace(NUM, '#')) return null;
  const x = a.match(NUM) || [], y = b.match(NUM) || [];
  for (let i = 0; i < x.length; i++) { const p = +x[i].replace(/[,]/g, '').replace('−', '-'), q = +y[i].replace(/[,]/g, '').replace('−', '-');
    const dp = Math.max((x[i].split('.')[1] || '').length, (y[i].split('.')[1] || '').length);
    if (Math.abs(p - q) > Math.pow(10, -dp) + 1e-9) return null; }
  return 'digit';
}

(async () => {
  // ── 1. the decoder: the page's anyDecode vs engine.impact_any.decode, every date of both files ──
  await step('decode', async () => {
    const files = {}; for (const a of [A, B]) files[a.app_id] = JSON.parse(require('zlib').gunzipSync(fs.readFileSync(path.join(dir, `impact_any_${a.key}.json.gz`))).toString('utf8'));
    ctx.__F = files;
    const canon = x => JSON.stringify(x, (k, v) => (v && typeof v === 'object' && !Array.isArray(v)) ? Object.keys(v).sort().reduce((o, kk) => (o[kk] = v[kk], o), {}) : v);
    let n = 0, same = 0; const diff = [];
    for (const a of [A, B]) for (const [iso, want] of Object.entries(FX.decoded[a.app_id])) { n++;
      const got = run(`JSON.stringify(anyDecode(__F[${J(a.app_id)}], ${J(iso)}))`);
      if (canon(JSON.parse(got)) === canon(want)) same++; else if (diff.length < 3) diff.push(iso); }
    const out = run(`[anyDecode(__F[${J(A.app_id)}], uniAdd(${J(A.first)}, -1)), anyDecode(__F[${J(A.app_id)}], uniAdd(${J(A.last)}, 1)), anyDecode(__F[${J(A.app_id)}], '2026-02-30x'), anyDecode(null, ${J(A.first)})]`);
    R.decode = { dates: n, same, diff, outside: JSON.parse(J(out)) };
  });

  // ── 2. the app page's box: the index, the marks and the app's file load lazily (once each) ──
  SERVER.marks.push(mk({ app_id: A.app_id, date: '2026-08-15', name: 'Notification shuru' }));
  SERVER.marks.push(mk({ app_id: '*', date: '2026-08-01', name: 'Sab apps ka SDK', who: 'owner@example.test' }));
  SERVER.marks.push(mk({ app_id: B.app_id, date: '2026-07-01', name: 'Doosri app ka', who: 'owner@example.test' }));
  const S = R.states = {};
  await step('load', async () => {
    S.loading = text(cut(box(0), '<div class="uni-any-note', '</div>'));
    await settle(); card(0); await settle();
    S.files_after_load = fetches(/^impact_any_a1a1/);
  });
  const P = FX.picks, fmt = {};
  const C = R.card = {};
  await step('card', async () => {
    const n0 = NET.log.length; let picks = 0;
    const at = (d, win, name) => { set({ date: d, win: win || 7, name: name || '' }); picks++; return box(0); };
    let h = at(P.update_dates[P.update_dates.length - 1]);
    TEXTS.card_update_day = text(h);
    const res = cut(h, '<div class="any-res"');
    C.block_class = (res.match(/<div class="(any-res)" id="uni-any-res"/) || [])[1];
    C.title = tight(cut(res, '<div class="any-rt">', '</div>'));
    C.dates_line = text(cut(res, '<div class="any-dl">', '</div>'));
    C.no_update_words = !/Verdict|Expected \(without update\)|Actual:|pakka: ≥|seedha|👍 Keep|Keep\b/.test(text(res));
    C.heads = [...cut(res, '<thead>', '</thead>').matchAll(/<th>([^<]*)<\/th>/g)].map(m => m[1]);
    C.one_table = (res.match(/<table/g) || []).length;
    const same = (h.match(/<div class="uni-any-note">(📦 Isi din[\s\S]*?)<\/div>/) || [])[1] || '';
    C.same_note = text(same); C.same_link = (same.match(/onclick="([^"]*)"/) || [])[1] || null;
    C.window_buttons = [...cut(h, 'Before / after:', '</span></span>').matchAll(/<button( class="on")?( disabled)?[^>]*>(\d+) days<\/button>/g)].map(m => [+m[3], !!m[1], !!m[2]]);
    C.pickers = (h.match(/>\d+ days<\/button>/g) || []).length;
    h = at(P.update_dates[P.update_dates.length - 1], 7, 'Banner ad hataya');
    C.title_named = tight(cut(h, '<div class="any-rt">', '</div>'));
    h = at(P.update_dates[P.update_dates.length - 1], 30);
    C.at_30 = { n: (h.match(/<div class="any-res" id="uni-any-res" data-kind="date" data-date="[^"]*" data-n="(\d+)"/) || [])[1], title: tight(cut(h, '<div class="any-rt">', '</div>')),
      d30: /<tr data-row="new_d30">/.test(h) };
    TEXTS.card_30 = text(h);
    // near today: every window still ⏳ — "⏳ Too early — <ready_on> ko poora hoga"
    h = at(P.last);
    C.pending_line = text((h.match(/<div class="uni-any-note"><b[^>]*>(⏳ Too early[\s\S]*?)<\/b>/) || [])[1] || '');
    C.pending_rows = (cut(h, '<div class="any-res"').match(/data-st="early"/g) || []).length;
    TEXTS.card_pending = text(h);
    const notes = hh => [...cut(hh, '<div class="any-res"', '<div class="uni-scroll">').matchAll(/<div class="uni-any-note">([\s\S]*?)<\/div>/g)].map(m => text(m[1]));
    h = at(P.cut); C.cut_note = notes(h).find(x => x.startsWith('⚠️') && x.includes('agla')) || ''; TEXTS.card_cut = text(h);
    h = at(P.overlap); C.overlap_note = notes(h).find(x => x.includes('(Pehle me)')) || ''; C.overlap_link = /onclick="uniImp\('upd@/.test(cut(h, '<div class="any-res"', '<div class="uni-scroll">')); TEXTS.card_overlap = text(h);
    h = at(P.cut, 30); C.mixed_notes_30 = notes(h); TEXTS.card_mixed = text(h);
    h = at(run(`uniAdd(${J(P.first)}, -3)`)); C.outside = text(cut(h, '<div class="uni-any-note">Ye date', '</div>'));
    for (const d of [P.last, P.cut, P.overlap, ...P.update_dates]) fmt[d] = run(`uniD(${J(d)})`);
    for (const d of Object.values(FX.decoded[A.app_id])) for (const N of ['7', '14', '30', '60']) { const w = d[N]; if (!w) continue;
      for (const x of [w.verdict.ready_on, w.cut_by && w.cut_by.date, w.overlap_before && w.overlap_before.date, ...(w.mixed || []).map(u => u.date)]) if (x && !fmt[x]) fmt[x] = run(`uniD(${J(x)})`);
      if (w.verdict.ready_on) fmt['lag:' + w.verdict.ready_on] = run(`uniD(uniAdd(${J(w.verdict.ready_on)}, 2))`); }
    S.picks_without_fetch = NET.log.length === n0 ? picks : 0;
    S.file_once = fetches(/^impact_any_a1a1/);
  });
  R.fmt = fmt;

  // ── 3. parity: a release date's 📅 card shows that update's own numbers and statuses, row for row, at every window ──
  // (the update block: the engine's full-precision asset; the 📅 card: the file's numbers at the precision the card shows —
  // a last shown digit may round the other way). Status: the same words — unsure = Watch the bad way, else No change
  await step('parity', async () => {
    const Pa = R.parity = { dates: 0, windows: 0, rows: 0, cells: 0, exact: 0, digit: 0, status_same: 0, diffs: [], no_version_table: true, no_adoption: true, titles_ok: true, kyun: 0 };
    const MAP = { worse: ['worse'], better: ['better'], same: ['same'], market: ['same'], unsure: ['watch', 'same'], low: ['early'], pending: ['early'], na: ['na'] };
    for (const d of P.update_dates) { Pa.dates++;
      const key = run(`uniImpFind(__AP[0], 'upd@${d}').b.key`), wins = [7].concat(Object.keys(run(`uniImpFind(__AP[0], ${J(key)}).b.by_window || {}`)).map(Number));
      for (const N of wins) { Pa.windows++;
        const real = String(run(`UNIIMPWK = {${J(key)}: ${N}}; uniImpBlock(__AP[0], uniImpFind(__AP[0], ${J(key)}).b, true, 'uni')`));
        set({ date: d, win: N, name: '' });
        const mine = cut(box(0), '<div class="any-res"');
        if (/Same days: new version vs old versions|uni-imp-vnote/.test(mine)) Pa.no_version_table = false;
        if (/ updated<\/span>|Adoption |On this update or newer/.test(mine)) Pa.no_adoption = false;
        if (!tight(cut(mine, '<div class="any-rt">', '</div>')).startsWith('📅 ' + run(`uniD(${J(d)})`) + ': pehle vs baad (' + N + ' days)')) Pa.titles_ok = false;
        const ro = rowsOf(cut(real, '<div', '<div class="uni-imp-sub">')), rm = anyRows(mine);
        if (J(Object.keys(ro)) !== J(Object.keys(rm))) { Pa.diffs.push({ d, N, rows: [Object.keys(ro), Object.keys(rm)] }); continue; }
        for (const k of Object.keys(ro)) { Pa.rows++; const x = ro[k], y = rm[k], bad = [];
          [0, 1].forEach(j => { const a = firstNum(x.cells[j]), b = firstNum(y.cells[j]); Pa.cells++;
            if (!a && (y.cells[j] === '—' || !b)) { Pa.exact++; return; }
            const s2 = sameCell(a, b); if (s2 === 'exact') Pa.exact++; else if (s2 === 'digit') Pa.digit++; else bad.push(['cell' + j, x.cells[j], y.cells[j]]); });
          if ((MAP[x.st] || []).includes(y.st)) Pa.status_same++; else bad.push(['status', x.st, y.st]);
          if (y.kyun) Pa.kyun++;
          if (bad.length && Pa.diffs.length < 6) Pa.diffs.push({ d, N, k, bad }); } } }
  });

  // ── 4. 📌 saved dates: the list (this app + "*"), 💾 Save (confirmed only on the API's OK, every error said), delete ──
  const M = R.marks = {};
  await step('marks', async () => {
    const g = NET.log.find(x => x.url === '/api/marks');
    M.get = g ? { url: g.url, method: g.method, credentials: g.credentials, redirect: g.redirect } : null;
    set({ date: P.cut, win: 7, name: '', msg: '', mc: '' });
    let h = box(0);
    const listed = hh => [...cut(hh, '<div class="uni-any-mks">', '</div>').matchAll(/<button type="button" class="uni-any-mk[^"]*"[^>]*>([\s\S]*?)<\/button>/g)].map(m => text(m[1]));
    M.listed = listed(h); M.other_app_hidden = !/Doosri app ka/.test(h);
    M.delete_buttons = [...h.matchAll(/data-del="(\d+)"/g)].map(m => +m[1]);
    TEXTS.marks_box = text(h);
    const s = M.save = {};
    s.disabled_without_name = /id="uni-any-sv" disabled/.test(h);
    run(`uniAnyName('Banner ad hataya')`);
    s.enabled_with_name = /<button type="button" class="uni-any-btn" id="uni-any-sv" onclick/.test(box(0));
    s.save_words = text(cut(box(0), '<div class="any-save"', '</div></div>'));
    s.name_required = /aria-required="true"/.test(box(0)) && /placeholder="Naam \(zaroori\)/.test(box(0));
    // the API holds its answer: "⏳ Save ho raha hai…", nothing listed yet
    NET.api = 'hold'; const n0 = NET.log.length;
    const p = run('uniAnySave()'); await tick();
    s.pending_msg = run('UANY.msg'); s.listed_before_ok = listed(box(0)).some(x => x.includes('Banner ad hataya'));
    const post = NET.log.slice(n0).find(x => x.method === 'POST');
    s.post = post ? { url: post.url, method: post.method, ct: post.headers['Content-Type'], credentials: post.credentials, body: JSON.parse(post.body) } : null;
    NET.api = 'ok'; NET.hold(); await p; await tick();
    s.ok_msg = run('UANY.msg'); s.listed_after_ok = listed(box(0)).some(x => x.includes('Banner ad hataya'));
    TEXTS.marks_saved = text(box(0));
    // "All apps" ticked: saved as "*"
    run(`uniAnyName('Sab apps pe naya SDK'); uniAnyStar(true)`); const n1 = NET.log.length; await run('uniAnySave()');
    const p2 = NET.log.slice(n1).find(x => x.method === 'POST'); s.star_body_app = p2 ? JSON.parse(p2.body).app_id : null; run('uniAnyStar(false)');
    // every failure: said, with the comparison still on screen and nothing listed
    for (const mode of ['down', 'e500', 'e401', 'static404', 'e400']) {
      NET.api = mode; const nm = 'Fail ' + mode; run(`uniAnyName(${J(nm)})`);
      const ok = await run('uniAnySave()'); const hh = box(0);
      s[mode] = { ok, msg: run('UANY.msg'), comparison_still_there: /<div class="any-res"/.test(hh) && /<tr data-row="returning_dau">/.test(hh), new_mark_listed: listed(hh).some(x => x.includes(nm)) };
      TEXTS['marks_err_' + mode] = text(hh); }
    NET.api = 'ok';
    // a name the API would refuse (a bidi control character) is never sent
    const n2 = NET.log.length; run(`uniAnyName('Banner' + String.fromCharCode(0x202E) + 'x')`); await run('uniAnySave()');
    s.bad_name_not_sent = NET.log.length === n2; s.bad_name_msg = run('UANY.msg');
    // a tap on a saved date re-opens that comparison
    run('uniAnyMk(1)'); h = box(0);
    M.pick_mark = { date: run('UANY.date'), name: run('UANY.name'), rendered: /<div class="any-res" id="uni-any-res" data-kind="date" data-date="2026-08-15"/.test(h) && /<span id="uni-any-nmt"> · Notification shuru<\/span>: pehle vs baad/.test(h) };
    // delete: cancelled → no call; confirmed → POST /api/marks/delete; a failure says so
    const dl = M.delete = {}; const n3 = NET.log.length;
    NET.confirm = false; await run('uniAnyDel(1)'); dl.cancelled_no_call = NET.log.length === n3;
    NET.confirm = true; await run('uniAnyDel(1)'); const dp = NET.log.slice(n3).find(x => x.url === '/api/marks/delete');
    dl.post = dp ? { url: dp.url, body: JSON.parse(dp.body) } : null; dl.gone = !run('UANY.marks').some(x => x.id === 1);
    const mine = run('UANY.marks').find(x => x.who === 'team@example.test'); NET.api = 'e500';
    await run(`uniAnyDel(${mine ? mine.id : -1})`); dl.fail_msg = run('UANY.msg'); NET.api = 'ok'; NET.confirm = false;
    // the marks API down from the start: the list says so, the comparison works
    run(`UANY.marks = null; UANY.marksErr = ''; UANY.msg = ''`); NET.api = 'down'; box(0); await settle();
    set({ date: P.cut, win: 7 }); h = box(0);
    M.list_down = text(cut(h, '<div class="uni-any-mks">', '</div>'));
    M.list_down_comparison = /<div class="any-res"/.test(h) && /<tr data-row="returning_dau">/.test(h);
    TEXTS.marks_down = text(h);
    NET.api = 'ok'; run(`UANY.marks = null; UANY.marksErr = ''`); box(0); await settle();
  });

  // ── 5. All apps: "📅 Ek date, sab apps" — progress, one row per app, worst first, 📌 markers, a row opens the card ──
  const T = R.all = {};
  await step('all', async () => {
    SERVER.marks.push(mk({ app_id: A.app_id, date: P.halt, name: 'Halt wala din' }));
    SERVER.marks.push(mk({ app_id: '*', date: P.halt, name: 'Sab pe' }));
    await run('anyMarksP()');
    TEXTS.all_before = text(run('uniAnyAllCard()'));
    run(`UANY.all.date = ${J(P.halt)}; UANY.all.win = 7`);
    const nf = fetches(/^impact_any_[0-9a-f]{12}\.json/);
    const p = run('uniAnyAllRun()');
    T.progress = [text(cut(run('uniAnyAllCard()'), '<div class="uni-any-note faint" id="uni-anyall-pg">', '</div>'))];
    await p; await tick();
    T.files_fetched = fetches(/^impact_any_[0-9a-f]{12}\.json/) - nf;
    const h = run('uniAnyAllCard()'); TEXTS.all = text(h);
    T.heads = [...cut(h, '<thead>', '</thead>').matchAll(/<th>([^<]*)<\/th>/g)].map(m => m[1]);
    const rows = [...h.matchAll(/<tr class="any-ar" data-st="([a-z]+)" data-app="([^"]*)" tabindex="0" onclick="([^"]*)"[^>]*>([\s\S]*?)<\/tr>/g)];
    T.rows = rows.map(m => ({ sw: m[1], id: m[2], go: m[3].replace(/&quot;/g, '"'), app: text((m[4].match(/<span class="n">([\s\S]*?)<\/span>/) || [])[1] || ''),
      word: text((m[4].match(/<span class="pill [^"]*" data-st="[a-z]+">([\s\S]*?)<\/span>/) || [])[1] || ''),
      metric: text((m[4].match(/<td class="any-m" data-h="Metric">([\s\S]*?)<\/td>/) || [])[1] || ''),
      cells: [...m[4].matchAll(/<td class="any-n[^"]*" data-h="[^"]*">([\s\S]*?)<\/td>/g)].map(x => text(x[1])),
      verdict: /data-lv=|Verdict|👍|🛑/.test(m[4]), pin: /uni-any-pin/.test(m[4]) }));
    T.marker_rows = T.rows.filter(r => r.pin).map(r => r.id).sort();
    T.star_named = /📌 Sab pe \(all apps\)/.test(text(cut(h, 'id="uni-anyall-sum"', '</div>')));
    T.marker_chips = (cut(h, '<div class="uni-any-mks">', '</div>').match(/class="uni-any-mk/g) || []).length;
    const n0 = NET.log.length; run('uniAnyAllWin(30)'); const h30 = run('uniAnyAllCard()');
    T.window_switch_instant = NET.log.length === n0 && /uni-anyall-sum/.test(h30) && /30 days before vs 30 days after/.test(text(h30));
    T.rows_30 = (h30.match(/<tr class="any-ar"/g) || []).length; TEXTS.all_30 = text(h30); run('uniAnyAllWin(7)');
    run(`uniAnyGo(${J(A.app_id)}, ${J(P.halt)}, 7)`);
    T.opened = JSON.parse(run('JSON.stringify({app: UANY.app, date: UANY.date, win: UANY.win, name: UANY.name})'));
    TEXTS.opened_card = text(box(0));
    T.sort_unit = JSON.parse(run(`JSON.stringify(anyAllSort([{id:'l',app:'l',res:'na',nw:0,hc:0},{id:'j',app:'j',res:'early',nw:0,hc:0},{id:'g',app:'g',res:'better',nw:0,hc:0},
      {id:'n',app:'n',res:'same',nw:0,hc:0},{id:'y',app:'y',res:'watch',nw:1,hc:-0.1},{id:'w1a',app:'w1a',res:'worse',nw:1,hc:-0.05},
      {id:'w1b',app:'w1b',res:'worse',nw:1,hc:-0.2},{id:'w2',app:'w2',res:'worse',nw:2,hc:0}]).map(o=>o.id))`));
    R.words.all_words = T.rows.map(r => r.word);
  });

  // ── 6. the other states: a stale file, a pending app, an app with no file, no index, the index unreachable ──
  await step('placement', async () => {       // the box: right under the card's title, on every app's card
    const h = card(0);
    S.box_at_top = /<div class="any-tabs" role="tablist"[\s\S]*?<\/div><div class="any-pane" id="uni-imp-pane" role="tabpanel" aria-labelledby="uni-imp-tab-any"><div class="uni-any" id="uni-any" data-mode="date">/.test(h);
    S.box_on_every_card = [1, 2, 3].map(i => card(i).includes('<div class="uni-any" id="uni-any"'));
  });
  await step('states', async () => {
    S.fresh_has_no_stale_line = !/⚠️ Ye tulna /.test(box(0));
    box(1); await settle(); set({ app: B.app_id, date: '', win: 7 });
    let h = box(1); S.stale = text(cut(h, '<div class="uni-any-note">⚠️ Ye tulna', '</div>')); TEXTS.card_stale = text(h);
    h = box(2); S.pending = text(cut(h, '<div class="uni-any-note">', '</div>')); TEXTS.card_pending_app = text(h);
    h = box(3); S.no_file = text(cut(h, '<div class="uni-any-note">', '</div>')); TEXTS.card_no_ga4 = text(h);
    run('var __IDX = UANY.idx; UANY.idx = null; UANY.idxErr = ""');
    NET.index = '404'; box(0); await settle(); h = box(0); S.no_index = text(cut(h, '<div class="uni-any-note">', '</div>')); TEXTS.card_no_index = text(h);
    TEXTS.all_no_index = text(run('uniAnyAllCard()'));
    run('UANY.idxErr = ""'); NET.index = 'net'; box(0); await settle(); h = box(0); S.net = text(cut(h, '<div class="uni-any-note">', '</div>'));
    TEXTS.card_net = text(h);
    run('UANY.idx = __IDX; UANY.idxErr = ""'); NET.index = 'ok';
  });

  R.words.texts = TEXTS; R.words.screens = Object.keys(TEXTS).length;
  process.stdout.write(JSON.stringify(R));
})().catch(e => { errors.push('MAIN ' + e.message); process.stdout.write(JSON.stringify(R)); });
