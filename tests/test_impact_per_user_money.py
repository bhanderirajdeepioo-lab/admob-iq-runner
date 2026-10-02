"""Update impact's "Revenue per user/day" row: the engine stores it per 1,000 users (unit 'usd1k'); the page must show it
PER USER (÷1,000) under its per-user label — a per-1,000 number under a per-user label reads 1,000× too high."""
import json, os, re, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "frontend", "index.html")


def _fn(src, name):
    i = src.index("function %s(" % name)
    j = src.index("\n//", i)   # the function ends where the next comment block starts
    return src[i:j]


def test_usd1k_rows_are_formatted_per_user():
    src = open(PAGE, encoding="utf-8").read()
    assert "(u==='usd1k'?uniMoneyPU(+v,x.currency):" in src
    js = """
    const DATA={usd_inr:96}; let VIEW='USD';
    const baseCur=()=>'USD', cfx=()=>VIEW==='INR'?96:1, csym=()=>VIEW==='INR'?'₹':'$';
    %s
    const out=[uniMoneyPU(22.13,'USD'), uniMoneyPU(1850,'USD'), uniMoneyPU(0,'USD')];
    VIEW='INR'; out.push(uniMoneyPU(22.13,'USD'));
    console.log(JSON.stringify(out));
    """ % _fn(src, "uniMoneyPU")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    assert json.loads(r.stdout) == ["$0.0221", "$1.85", "$0", "₹2.12"]


# ── the split block under it (owner, 2 Oct: "per user $2x.xx" under "Revenue per user/day" — the per-1,000 value) ──────
# The row was fixed (uniMoneyPU); the installs vs per-user block under it printed its "per user" amounts with the
# per-1,000 formatter. Every place that draws a revenue split — the Uninstall tab's Update impact row, the Active users
# tile, an alert / Install value change carrying one — now says the amount PER USER, at $ and at ₹. Synthetic numbers.
SPLIT_JS = r"""
const fs = require('fs'), vm = require('vm');
const any = new Proxy(function () {}, { get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true });
const st = { getItem: () => null, setItem() {}, removeItem() {} };
const ctx = { console: { log() {}, warn() {}, error() {} }, window: any, document: any, localStorage: st, sessionStorage: st, navigator: any,
  location: { href: '', search: '', hash: '', pathname: '/', reload() {} }, history: any, fetch: () => new Promise(() => {}),
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {}, requestAnimationFrame: () => 0,
  matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }), addEventListener() {}, removeEventListener() {},
  DecompressionStream: any, Response: any, Blob: any, URLSearchParams, URL, TextDecoder, TextEncoder, Intl, Date, Math, JSON, Promise,
  Array, Object, Number, String, Set, Map, Float64Array, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
  performance: { now: () => 0 }, getComputedStyle: () => any, innerWidth: 375, innerHeight: 812, scrollTo() {}, alert() {}, confirm: () => false,
  IntersectionObserver: any, ResizeObserver: any, MutationObserver: any, Event: any, CustomEvent: any, HTMLElement: any };
ctx.globalThis = ctx; ctx.self = ctx; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), ctx);
const out = vm.runInContext(`(()=>{ DATA={apps_catalog:[],today_date:'2026-09-28',currency:'USD',usd_inr:96,alerts:{counts:{},items:[]},
    active:{currency:'USD',apps:[]}}; CURVIEW='USD';
  const txt=h=>String(h||'').replace(/<[^>]*>/g,' ').replace(/&amp;/g,'&').replace(/\\s+/g,' ').trim();
  // revenue per 1,000 users 17.50 → 18.60 (= $0.0175 → $0.0186 per user), users 500,000 → 520,000 a day
  const row={status:'same',before:17.5,after:18.6,unit:'usd1k',sp:['rev',500000,520000],extra:{currency:'USD'}};
  const tile={sp:['rev',500000,520000],base:17.5,v:18.6,st:'normal'};
  const draw=()=>({uni:txt(uniImpSplit('arpdau',row,{sl:true})),act:txt(actTileSplit({},'arpdau',tile,'USD')),
    val:txt(valSplit(Object.assign({},tile))),other:txt(splitHtml('rev',tile,{money:v=>actMoney(v),cur:'USD'}))});
  const usd=draw(); CURVIEW='INR'; const inr=draw(); CURVIEW='USD';
  return JSON.stringify({usd,inr}); })()`, ctx);
process.stdout.write(out);
"""


def test_the_revenue_split_says_per_user_amounts_everywhere(tmp_path):
    src = open(PAGE, encoding="utf-8").read()
    js = max(re.findall(r"<script>(.*?)</script>", src, re.S), key=len)
    (tmp_path / "app.js").write_text(js, encoding="utf-8")
    (tmp_path / "t.js").write_text(SPLIT_JS, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "t.js"), str(tmp_path / "app.js")], capture_output=True, text=True, check=True)
    out = json.loads(r.stdout)
    for where in ("uni", "act", "val", "other"):
        u, i = out["usd"][where], out["inr"][where]
        assert "Revenue/day:" in u, (where, u)
        assert "per user $0.0175 → $0.0186" in u and "(users +4%; per user $0.0175)" in u, (where, u)
        assert "per user ₹1.68 → ₹1.79" in i, (where, i)
        # never the per-1,000 number under the per-user label
        assert not re.search(r"per user \$1\d\.", u) and "$17.5" not in u and "$18.6" not in u, (where, u)
