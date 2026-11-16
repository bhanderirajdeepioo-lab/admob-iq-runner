// ⚖️ Breakeven · Google Ads | Organic — the page side of tests/test_be_paid_e2e.py: the CPX module of frontend/index.html (cut
// out by its own markers, as tests/cpx_frontend.js does, with the same stub page helpers) in a node vm, on EXACTLY the files the
// build wrote — admob_iq/roi_build.py's Google Ads users' pass → admob_iq/be_build.py with BE_PAID — never a hand-made shape:
// the build's Breakeven pointer entries laid onto tests/cpx_fixture.js build() (the CPX screen's own synthetic pointer: its
// apps Alpha, Beta … carry the build's entries in order — each entry's key / file / org / v exactly as written), its files
// served as they are. Renders the tab in both views of the users switch, $ then ₹: no day open, then every day open (all of
// a view's days on one page), and the Organic file's fetch through the screen's own taps (never asked for by the Google Ads
// view, once when Organic opens, not again when it opens again). Reports what a viewer sees — the switch, the lines, every
// row's cells (and the "—" whys) and its table's columns, the open days' tables and charts, every fetch, any junk word, any
// error — and the SHA-256 of every render. --old: the Google Ads view only, with the switch set either way (a file without
// "src": the page from before the switch must render it the same — the test pins that SHA-256).
// Prints ONE JSON report.   usage: node be_paid_page.js <index.html> <build.json> [--old]
//   build.json = {"be": dashboard["be"] as the build wrote it, "apps": [app id, …] (its order onto Alpha, Beta …),
//                 "files": {name: body}}
'use strict';
const fs = require('fs'), vm = require('vm'), path = require('path'), crypto = require('crypto');
const { build } = require(path.join(__dirname, 'cpx_fixture.js'));
const html = fs.readFileSync(process.argv[2], 'utf8'), IN = JSON.parse(fs.readFileSync(process.argv[3], 'utf8')), OLD = process.argv[4] === '--old';
const a = html.indexOf('const CPX=(()=>{'), b = html.indexOf('function renderCpx(){');
if (a < 0 || b < 0 || b < a) { console.log(JSON.stringify({ errors: ['CPX module not found'] })); process.exit(0); }
const MON0 = html.indexOf('// ---- the month mover'), MON1 = html.indexOf("// ---- a daily chart's period");
const src = (MON0 >= 0 && MON1 > MON0 ? html.slice(MON0, MON1) : '') + html.slice(a, b) + '\nthis.CPX=CPX;';
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const SCREEN = { _html: '', dataset: { screen: 'cpx' }, style: {}, isConnected: true, offsetHeight: 900, children: [], _on: {},
  get innerHTML() { return this._html; }, set innerHTML(v) { this._html = String(v); },
  addEventListener(t, f) { (this._on[t] = this._on[t] || []).push(f); }, querySelectorAll: () => [], querySelector: () => null };
let LOADS = [], CURV = 'USD';
const FX = build(), SLOT = ['a', 'b', 'c', 'd', 'e', 'z'], ON = {};
// the build's pointer onto the fixture's apps (the entries themselves untouched) and its files beside the fixture's
FX.DATA.be = Object.assign({}, IN.be, { apps: {} });
IN.apps.forEach((id, i) => { ON[SLOT[i]] = id; FX.DATA.be.apps[FX.IDS[SLOT[i]]] = IN.be.apps[id]; });
Object.assign(FX.FILES, IN.files);
const ctx = {
  console, Math, JSON, Object, Array, String, Number, Set, Map, WeakMap, Promise, isFinite, encodeURIComponent, Error, Date, parseFloat,
  setTimeout: (f) => { f(); return 0; }, clearTimeout: () => {},
  DATA: FX.DATA, APP: '',
  document: { querySelector: s => s === '.screen.on' ? { dataset: { screen: 'cpx' } } : (s === '.screen[data-screen=cpx]' ? SCREEN : null), getElementById: () => null },
  window: { scrollBy: () => {}, innerWidth: 1280, innerHeight: 800, scrollY: 0, addEventListener() {}, removeEventListener() {} },
  get localStorage() { return { getItem: () => null, setItem: () => {} }; },
  SP: { quietly: f => f() }, HB: { st: [] }, hbPush: () => {}, hbDrop: () => {},
  screenDiv: () => SCREEN,
  fmtD: s => { const p = String(s).split('-'); return (+p[2]) + ' ' + MON[+p[1] - 1]; },
  appIconId: (id, name, size, cls) => `<span class="aicon ${cls}" data-iid="${id}" data-sz="${size}"></span>`,
  appVisibleByName: nm => nm !== 'Hidden App',
  curView: () => CURV, baseCur: () => 'USD',
  roasFxDated: () => true,
  roasDaily: e => (e && ((CURV === 'USD' && e.daily_dated) || e.daily)) || {},
  valFlag: cc => '[' + cc + ']', valCtyName: cc => 'Name ' + cc,
  show: () => {},
  fetchGzJson: url => { const f = String(url).split('?')[0]; LOADS.push(f); if (!(f in FX.FILES)) return Promise.reject(new Error('net')); return Promise.resolve(JSON.parse(JSON.stringify(FX.FILES[f]))); },
};
ctx.window.show = ctx.show;
vm.createContext(ctx);
try { vm.runInContext(src, ctx); } catch (e) { console.log(JSON.stringify({ errors: ['TOPLEVEL ' + e.message] })); process.exit(0); }
const CPX = ctx.CPX, _ = CPX._;
const tick = () => new Promise(r => setImmediate(r)), settle = async () => { for (let i = 0; i < 6; i++) await tick(); };
const dec = s => String(s).replace(/&#39;/g, "'").replace(/&quot;/g, '"').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const txt = h => dec(String(h).replace(/<br>/g, ' | ').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim());
const reset = () => { for (const k in _.FILES) delete _.FILES[k]; Object.assign(_.ALLF, { raw: null, v: null, busy: false, err: false }); _.set({ PER: '14', PF: '', PTO: '', OPEN: null, TAB: 'ch', DN: 30, PREAD: true }); ctx.APP = ''; };
const tbOf = h => { const i = h.indexOf('id="cpx-tb">'); if (i < 0) return ''; const j = h.indexOf('<div class="cpx-row', i), k = h.indexOf('<p class="cpx-ft">', i);   // the tab body only
  const e = [j, k].filter(x => x > 0).sort((x, y) => x - y)[0]; return h.slice(i + 12, e == null ? h.length : e); };
const clickD = (sel, ds) => SCREEN._on.click[0]({ target: { closest: s => s === sel ? { dataset: ds || {} } : null } });
const R = [];                                                                // every render (the junk words, the SHA-256)
// a render of the tab: the app file first, then (Organic) its own file — each fetched as the screen does, then painted again
const go = async (o) => { reset(); _.set(Object.assign({ TAB: 'be', BOPEN: null, BUNC: false, BSRC: 'p' }, o)); CPX.paint(); await settle(); CPX.paint();
  if (o.BSRC === 'o') { await settle(); CPX.paint(); } const h = tbOf(SCREEN.innerHTML); R.push(h); return h; };
const cellsOf = r => [...r.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(c => txt(c[1]));
const rowsOf = h => [...h.matchAll(/<tr class="(cpx-ber[^"]*)" data-cpx-bed="([^"]+)">([\s\S]*?)<\/tr>/g)].map(m => ({ d: dec(m[2]), cells: cellsOf(m[3]),
  titles: [...m[3].matchAll(/title="([^"]*)"/g)].map(t => dec(t[1])) }));
const swOf = h => [...h.matchAll(/<button type="button" class="cpx-besb" data-cpx-besrc="([a-z])" aria-pressed="(true|false)">([^<]*)<\/button>/g)].map(m => [m[1], m[2] === 'true', m[3]]);
const linesOf = h => [...h.matchAll(/<p class="cpx-(fn|note|vm)(?: cpx-wait)?">([\s\S]*?)<\/p>/g)].map(m => [m[1], txt(m[2])]);
const bedOf = h => { const i = h.indexOf('<div class="cpx-bed"'); if (i < 0) return ''; const j = h.indexOf('<tr class="cpx-ber', i), e = j < 0 ? h.lastIndexOf('</tbody></table></div>') : j; return h.slice(i, e); };
const tblOf = (h, head) => { const i = h.indexOf(head); if (i < 0) return null; const t = h.slice(i, h.indexOf('</table>', i));
  return { head: [...t.matchAll(/<th[^>]*>([^<]*)<\/th>/g)].map(m => m[1]), rows: [...t.matchAll(/<tr><td>([\s\S]*?)<\/tr>/g)].map(m => cellsOf('<td>' + m[1])) }; };
const headOf = h => { const m = h.match(/<thead><tr>([\s\S]*?)<\/tr><\/thead>/); return m ? [...m[1].matchAll(/<th[^>]*>([^<]*)<\/th>/g)].map(x => x[1]) : []; };   // the view's own table's columns
const view = h => ({ sw: swOf(h), lines: linesOf(h), rows: rowsOf(h), head: headOf(h), more: /data-cpx-more="1"/.test(h), ga: h.includes('id="cpx-bex"'), org: h.includes('id="cpx-beox"') });
const out = { errors: [], apps: {} };
(async () => {
  try {
    for (const s of Object.keys(ON)) {
      const id = FX.IDS[s], e = IN.be.apps[ON[s]], F = IN.files[e.file], O = e.org ? IN.files[e.org] : null, A = {};
      out.apps[ON[s]] = A;
      for (const cur of ['USD', 'INR']) { CURV = cur;
        for (const sw of OLD ? ['p', 'o'] : ['p']) {                         // (--old: the switch either way — no "src", no switch)
          A[cur + '/ga' + (OLD ? '/' + sw : '')] = view(await go({ OPEN: id, BSRC: sw }));
          A[cur + '/gad' + (OLD ? '/' + sw : '')] = [];
          for (const x of F.days) { const h = await go({ OPEN: id, BSRC: sw, BOPEN: x.d, DN: 100000 });
            A[cur + '/gad' + (OLD ? '/' + sw : '')].push({ d: x.d, open: (h.match(/class="cpx-bedr"/g) || []).length, tt: [...bedOf(h).matchAll(/class="cpx-tt">([^<]*)</g)].map(m => m[1]) }); } }
        if (OLD) continue;
        A[cur + '/org'] = view(await go({ OPEN: id, BSRC: 'o' }));
        A[cur + '/orgall'] = rowsOf(await go({ OPEN: id, BSRC: 'o', DN: 100000 }));
        A[cur + '/orgd'] = [];
        for (const x of O ? O.days : []) { const h = await go({ OPEN: id, BSRC: 'o', BOPEN: x.d, DN: 100000 }), d = bedOf(h);
          A[cur + '/orgd'].push({ d: x.d, open: (h.match(/class="cpx-bedr"/g) || []).length, tbl: tblOf(d, '<table class="cpx-t cpx-beot">'), lines: linesOf(d),
            svg: (d.match(/<svg class="cpx-svg cpx-bes"/g) || []).length, ax: [...d.matchAll(/class="cpx-ax" text-anchor="middle">([^<]*)</g)].map(m => m[1]) }); } }
      CURV = 'USD';
      if (OLD) continue;
      // the Organic file through the screen's taps: the Google Ads view never asks for it; Organic does, once
      reset(); _.set({ OPEN: id, TAB: 'be', BOPEN: null, BSRC: 'p' }); LOADS = []; CPX.paint(); await settle(); CPX.paint();
      const ga = LOADS.slice(); clickD('[data-cpx-besrc]', { cpxBesrc: 'o' }); await settle(); CPX.paint();
      const on = LOADS.slice(), shown = SCREEN.innerHTML.includes('id="cpx-beox"');
      clickD('[data-cpx-besrc]', { cpxBesrc: 'p' }); clickD('[data-cpx-besrc]', { cpxBesrc: 'o' }); await settle(); CPX.paint();
      A.lazy = { ga, on, again: LOADS.slice(), shown, src: _.get().BSRC };
      _.set({ BSRC: 'p' });
    }
    out.bad = ['undefined', 'NaN', '[object Object]', 'Infinity', 'null'].filter(w => R.some(h => txt(h).includes(w)));
    out.n = R.length;
    out.sha = crypto.createHash('sha256').update(R.join('\u0000')).digest('hex');
  } catch (e) { out.errors.push(String(e && e.stack || e)); }
  console.log(JSON.stringify(out));
})();
