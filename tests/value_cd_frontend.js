// The Install value tab's additions (SPEC_CD_GEO): 🌍 country cost from Google Ads (G), 🧬 new users by app version (C) and
// 🗓️ long-term by install month (D), rendered for real: runs the REAL dashboard script (frontend/index.html's <script>) in a
// node vm with stub browser globals — the same loader as tests/value_frontend.js, which is not edited — on the committed
// fixture (tests/fixtures/value_sample.json). Every C / D / G state is made up here from the addendum's contract (all
// synthetic; dates follow each detail's own settled day), so this runs the same on a fixture from before C / D and after:
// the section states, every cell kind, the chips (coloured only with an open alert), the rows and cards opened, phone and
// desktop, $ and ₹, the 📦 links both ways (Update impact block → 🧬, money-back 📦 row → 🧬), the Alerts screen cards and
// "What changed?" rows of the new families, and the old files (by_version / long arrays) drawing nothing.
// Prints one JSON report; tests/test_value_cd_frontend.py asserts on it.
// usage: node value_cd_frontend.js <script.js> <value_fixture.json>
const fs = require('fs'), vm = require('vm');
const [scriptPath, fixturePath] = process.argv.slice(2);
const any = new Proxy(function () {}, {
  get: (t, k) => k === Symbol.toPrimitive ? (() => '') : (k === 'then' ? undefined : (k === 'length' ? 0 : any)),
  apply: () => any, construct: () => any, set: () => true, has: () => true,
});
const errors = [];
const ctx = {
  console: { log() {}, warn() {}, error: (...a) => errors.push(a.join(' ')) },
  window: any, document: any, localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
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
const FX = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const DV = FX.dashboard_value || (FX.dashboard && FX.dashboard.value) || FX.value;
const FILES = {};
for (const [k, v] of Object.entries(FX.app_files || FX.files || {})) FILES[(k.match(/^value_([0-9a-f]+)\.json(\.gz)?$/) || [])[1] || k] = v;
const addDay = (s, n) => new Date(Date.parse(s + 'T00:00:00Z') + n * 864e5).toISOString().slice(0, 10);
const TODAY = FX.today_date || (DV.settled_till_max ? addDay(DV.settled_till_max, 5) : '2026-09-25');
ctx.__DV = DV; ctx.__FILES = FILES;
run(`DATA = {apps_catalog: [], today_date: ${JSON.stringify(TODAY)}, currency: 'USD', usd_inr: 84, alerts: {counts: {}, items: []}, placements: [], value: __DV};
     VALD = {}; for (const [k, d] of Object.entries(__FILES)) VALD[k] = d;`);
const out = {};
function scen(name, code) { try { out[name] = String(run(code)); } catch (e) { errors.push(name + ': ' + e.message + ' @ ' + (e.stack.match(/at [^\n]*/g) || []).slice(0, 4).join(' < ')); } }
const RESET = `APP=''; VALAPP=''; innerWidth=375; CURVIEW=null; RANGE='30d'; VALWK='12'; VALSORT='n'; VALCM='d1'; VALCTYEXP=''; VALOLDEXP=false; VALCLEXP=false;
  VALTILEEXP=''; VALSTEXP=''; VALPSORT={k:'status',d:1}; VALTIMEXP=false; VALCHKEXP=false; VALJUMP=''; VALERR={}; VALL={}; VALVEROPEN=''; VALVEROLD=false; VALLONG='18'; VALVERAPP=''; VALVERDATE='';`;
const rows = DV.apps || [], J = JSON.stringify;
const det = r => FILES[r.key] || null;
const openApp = r => `VALAPP=${J(r.app_id)}; APP=${J(r.app)};`;
const withD = rows.filter(r => det(r));
const judgedRow = x => x && x.clean !== false && !['wait', 'few'].includes(x.verdict);
const withCty = withD.find(r => ((det(r).countries || {}).rows || []).filter(judgedRow).length >= 3) || withD[0];
const withPaid = withD.find(r => (det(r).weeks || []).some(w => w.judged)) || withD[0];
const fixCd = !!(DV.consts && DV.consts.cd === true);

// ── synth: begin (the addendum's contract, all made up — tests/test_value_cd_frontend.py and the scratch stub read the same) ──
const SYN = String.raw`
function synAdd(s,n){ return new Date(Date.parse(s+'T00:00:00Z')+n*864e5).toISOString().slice(0,10); }
function synDiff(a,b){ return Math.round((Date.parse(b+'T00:00:00Z')-Date.parse(a+'T00:00:00Z'))/864e5); }
// 🧬 by_version: 10 versions newest first — a new one still coming in (part / wait), a worse one with a release and a skipped
// hotfix, a same, a better one with a gap, a few-installs one, one whose 30-day cell is past the install-day edge, older ones
function synVer(d, state){
  const S=d.settled_till||'2026-09-16', ok=(v,x)=>Object.assign({v,lo:+(v*0.95).toFixed(2),hi:+(v*1.05).toFixed(2),n:9000,ret:Math.round(v*90),st:'ok',days:20,of:20,in:null,q:false},x||{});
  const m=(v,x)=>Object.assign({v,lo:+(v*0.9).toFixed(6),hi:+(v*1.1).toFixed(6),est:false,n:9000,st:'ok',days:20,of:20,in:null},x||{});
  const wait=n=>({v:null,lo:null,hi:null,n:0,ret:null,st:'wait',days:0,of:5,in:n,q:false});
  const side=(v0,v1,st,x)=>Object.assign({v0,v1,delta:v1==null?null:+(v1-v0).toFixed(2),rel:v1==null?null:+((v1-v0)/v0).toFixed(4),z:v1==null?null:+((v1-v0)*1.4).toFixed(2),
    n0:14000,n1:9000,days0:28,days1:20,from0:synAdd(S,-75),to0:synAdd(S,-48),from1:synAdd(S,-40),to1:synAdd(S,-21),st},x||{});
  const rel=(ver,off)=>({date:synAdd(S,off),version:ver,kind:'version',key:'ver:'+ver+'@'+synAdd(S,off)});
  const R=(ver,a,b,n,o)=>Object.assign({ver,label:'v'+ver,from:synAdd(S,a),to:synAdd(S,b),days:b-a+1,n,share_dom:0.95,current:false,gaps:false,release:null},o);
  const rows=[
    R('2.3',-4,0,2600,{current:true,release:rel('2.3',-5),d1:ok(30.9,{st:'part',days:3,of:5,in:2}),d7:wait(3),d30:wait(26),
      rpi:{'1':m(0.0043,{st:'part',days:3,of:5,in:2}),'7':Object.assign(wait(3),{est:false}),'30':Object.assign(wait(26),{est:false})},
      vs:{ver:'2.2',label:'v2.2',skipped:[],d1:side(27.1,30.9,'wait',{days1:3}),d7:side(11.2,null,'wait'),d30:side(4.9,null,'wait'),rpi7:{v0:0.0112,v1:null,rel:null,z:null,st:'wait'}},
      verdict:'wait',text:'v2.3: 2,600 installs — agle din wala number 2 din me'}),
    R('2.2',-40,-5,14000,{release:rel('2.2',-41),share_dom:0.96,d1:ok(27.1),d7:ok(11.2),d30:ok(4.9,{st:'part',days:11,of:36,in:25}),
      rpi:{'1':m(0.0041),'7':m(0.0112),'30':m(0.0208,{st:'part',days:11,of:36,in:25})},
      vs:{ver:'2.1',label:'v2.1',skipped:['2.1.1'],d1:side(31.8,27.1,'worse'),d7:side(13.5,11.2,'worse'),d30:side(5.4,4.9,'same'),rpi7:{v0:0.0125,v1:0.0112,rel:-0.104,z:-1.2,st:'same'}},
      verdict:'worse',text:'v2.2: 100 me se 27 agle din wapas, 7 din baad 11 (pichhla v2.1: 32, 13.5) — 30 din me kamai per install {m:0.0208} — naye users kam ruk rahe'}),
    R('2.1',-75,-41,16500,{d1:ok(31.8),d7:ok(13.5),d30:ok(5.4),rpi:{'1':m(0.0044),'7':m(0.0125),'30':m(0.0231)},
      vs:{ver:'2.0',label:'v2.0',skipped:[],d1:side(31.5,31.8,'same'),d7:side(13.7,13.5,'same'),d30:side(5.5,5.4,'same'),rpi7:{v0:0.0121,v1:0.0125,rel:0.033,z:0.4,st:'same'}},
      verdict:'same',text:'v2.1: 100 me se 32 agle din wapas, 7 din baad 13.5 (pichhla v2.0: 31.5, 13.7) — 30 din me kamai per install {m:0.0231}'}),
    R('2.0',-110,-76,12000,{gaps:true,release:rel('2.0',-111),d1:ok(31.5),d7:ok(13.7),d30:ok(5.5),rpi:{'1':m(0.0042,{est:true}),'7':m(0.0121),'30':m(0.0226)},
      vs:{ver:'1.9',label:'v1.9',skipped:[],d1:side(27.4,31.5,'better'),d7:side(12.1,13.7,'same'),d30:side(5.1,5.5,'same'),rpi7:{v0:0.0117,v1:0.0121,rel:0.034,z:0.5,st:'same'}},
      verdict:'better',text:'v2.0: 100 me se 32 agle din wapas, 7 din baad 14 (pichhla v1.9: 27, 12) — 30 din me kamai per install {m:0.0226} — naye users zyada ruk rahe'}),
    R('1.9',-130,-111,240,{d1:ok(27.4,{st:'few',ret:66}),d7:ok(12.1,{st:'few',ret:9}),d30:ok(5.1,{st:'few',ret:4}),rpi:{'1':m(0.0039,{st:'few'}),'7':m(0.0117,{st:'few'}),'30':m(0.0219,{st:'few'})},
      vs:null,verdict:'few',text:'v1.9: sirf 240 installs — tulna ke liye kam (300 chahiye)'}),
    R('1.8',-160,-131,5400,{d1:ok(29.9,{q:true}),d7:ok(12.8),d30:{v:null,lo:null,hi:null,n:0,ret:null,st:'nodata',days:0,of:30,in:null,q:false},
      rpi:{'1':m(0.004),'7':m(0.0119),'30':{v:null,st:'nodata',in:null}},vs:null,verdict:'wait',text:'v1.8: 5,400 installs'}),
    R('1.7',-190,-161,7000,{d1:ok(30.2),d7:ok(13.0),d30:ok(5.2),rpi:{'1':m(0.004),'7':m(0.012),'30':m(0.022)},vs:null,verdict:'same',text:'v1.7'}),
    R('1.6',-220,-191,6900,{d1:ok(30.0),d7:ok(12.9),d30:ok(5.1),rpi:{'1':m(0.004),'7':m(0.012),'30':m(0.022)},vs:null,verdict:'same',text:'v1.6'}),
    R('1.5',-250,-221,6800,{d1:ok(29.8),d7:ok(12.7),d30:ok(5.0),rpi:{'1':m(0.004),'7':m(0.012),'30':m(0.022)},vs:null,verdict:'same',text:'v1.5'}),
    R('1.4.2',-280,-251,6700,{d1:ok(29.5),d7:ok(12.5),d30:ok(4.9),rpi:{'1':m(0.004),'7':m(0.012),'30':m(0.021)},vs:null,verdict:'same',text:'v1.4.2'})];
  const T={ok:'v2.2 (14,000 installs): 100 me se 27 agle din wapas — pichhle v2.1 me 32; 7 din baad 11 vs 13.5. Naye users kam ruk rahe.',
    single:'Abhi ek hi version (v2.3) — tulna ke liye agla update chahiye.',nosplit:'GA4 is app ke naye users ka version alag nahi deta — version-wise data nahi.',
    nodata:'⏳ Version-wise data aa raha.',low:'Kisi version pe 100+ installs nahi — version-wise faisla nahi.',error:null};
  const st=state||'ok', R0=st==='ok'?rows:(st==='single'?[Object.assign({},rows[0],{vs:null,verdict:'wait'})]:[]);
  return {state:st,text:T[st]===undefined?null:T[st],dom_min:0.8,left_out:{days:3,n:410},phi:{'1':2.9,'7':2.2,'30':2.0},short:{versions:1,n:80},older:st==='ok'?2:0,rows:R0};
}
// 🗓️ long: one row per install month (or quarter), newest first; complete at t only when the whole month is — else "in N
// days"; the earning past what is seen projected (≈) from 30 days on; ₹100 of ads → 1 year inside the spend history
function synLong(d, grain, state){
  const S=d.settled_till||'2026-09-16', MO=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], rows=[], q=grain==='quarter';
  const base={30:9.1,60:7.0,90:5.9,180:4.1,365:2.6}, rb={30:0.021,90:0.033,180:0.045,365:0.062}, g={30:1,90:1.55,180:2.1,365:2.9};
  const last=(y,mm)=>new Date(Date.UTC(y,mm,0)).toISOString().slice(0,10);
  const per=[]; let y=+S.slice(0,4), mo=+S.slice(5,7)-1;          // the running month is never a row
  if(q){ let yy=+S.slice(0,4), qq=Math.floor((+S.slice(5,7)-1)/3)-1; if(qq<0){ qq=3; yy--; }                 // the running quarter is never a row
    for(let i=0;i<9;i++){ const a=qq*3+1; per.push({key:yy+'-Q'+(qq+1),label:'Q'+(qq+1)+' '+yy+' ('+MO[a-1]+'–'+MO[a+1]+')',year:yy,from:yy+'-'+String(a).padStart(2,'0')+'-01',to:last(yy,a+2)}); qq--; if(qq<0){ qq=3; yy--; } } }
  else { if(mo===0){ mo=12; y--; } for(let i=0;i<20;i++){ per.push({key:y+'-'+String(mo).padStart(2,'0'),label:MO[mo-1]+' '+y,year:y,from:y+'-'+String(mo).padStart(2,'0')+'-01',to:last(y,mo)}); mo--; if(mo===0){ mo=12; y--; } } }
  per.forEach((p,i)=>{ const wig=1+((i*7)%5-2)*0.02, dd={}, rr={};
    for(const t of [30,60,90,180,365]){ const inn=synDiff(S,synAdd(p.to,t)); dd[t]=inn>0?{v:null,lo:null,hi:null,ret:null,st:'wait',in:inn}:{v:+(base[t]*wig).toFixed(2),lo:+(base[t]*wig*0.95).toFixed(2),hi:+(base[t]*wig*1.05).toFixed(2),ret:Math.round(base[t]*wig*300),st:'ok',in:null}; }
    let seen=null; for(const t of [30,90,180,365]){ const inn=synDiff(S,synAdd(p.to,t));
      if(inn<=0){ seen=t; rr[t]={v:+(rb[t]*wig).toFixed(6),lo:null,hi:null,est:false,proj:false,shape:null,st:'ok',in:null}; }
      else if(seen){ const v=rr[seen].v*g[t]/g[seen]; rr[t]={v:+v.toFixed(6),lo:+(v*0.85).toFixed(6),hi:+(v*1.2).toFixed(6),est:false,proj:true,shape:'app',st:'wait',in:inn}; }
      else rr[t]={v:null,lo:null,hi:null,est:false,proj:false,shape:null,st:'wait',in:inn}; }
    const r365=rr[365], b=i<(q?3:9)&&r365.v!=null?+(100*r365.v/0.071).toFixed(1):null;
    rows.push(Object.assign({},p,{n:q?5100+i*37:41000+i*113,days:synDiff(p.from,p.to)+1,part:false,q:false,d:dd,rpi:rr,b365:b,b365_proj:b!=null&&!!r365.proj,release:[]})); });
  const R=rows; if(R.length){ const o=R[R.length-1]; o.part=true; o.from=synAdd(o.from,14); o.d['365']={v:null,lo:null,hi:null,ret:null,st:'nodata',in:null}; o.rpi['365']={v:null,st:'nodata',in:null}; }
  if(R[12]) R[12].d['180']=Object.assign({},R[12].d['180'],{st:'few',ret:8});
  if(R[3]) R[3].q=true;
  if(R[1]) R[1].release=[{date:synAdd(R[1].from,11),version:'2.2',key:'ver:2.2@'+synAdd(R[1].from,11)},{date:synAdd(R[1].from,20),version:'2.2.1'}];
  const st=state||'ok';
  const T={ok:q?'Q1 2026 ke installs: 90 din baad 100 me se 5.9 app khol rahe (pichhle 6 quarter, Q3 2024–Q4 2025: ~5.9) · 1 saal me kamai per install ≈{m:0.061} (andaza)':'Jun 2026 ke installs: 90 din baad 100 me se 5.8 app khol rahe (pichhle 6 mahine, Dec 2025–May 2026: ~5.9) · 1 saal me kamai per install ≈{m:0.061} (andaza)',
    young:'⏳ Abhi koi mahina 60 din purana nahi — pehla number Aug 2026 ke installs ka, 45 din me.',low:'Is app me mahine ke install kam — lambi wapsi ka number pakka nahi.',error:null};
  return {state:st,grain:q?'quarter':'month',text:T[st]===undefined?null:T[st],edge:R.length?R[R.length-1].from:null,phi:{'30':2,'60':2,'90':2,'180':2,'365':2},
    rows:st==='low'||st==='error'?[]:(st==='young'?R.slice(0,2):R),
    base:st==='ok'?{'60':{v:7.0,rows:6,from:R[7]?R[7].from:null,to:R[2]?R[2].to:null},'90':{v:5.9,rows:6,from:R[8]?R[8].from:null,to:R[3]?R[3].to:null},'rpi180':{v:0.045,rows:5,from:R[12]?R[12].from:null,to:R[8]?R[8].to:null}}:{}};
}
// 🌍 the Google Ads cost envelope on the Countries block: why ∈ ok | cov | wait | nostore | noads
function synGeo(d, why){
  const C=d.countries, S=d.settled_till||'2026-09-16', w=why||'ok', V=['keep','slow','costly'];
  C.geo=true; C.geo_why=w; C.geo_cov={v:w==='cov'?0.9512:0.9997,min:w==='cov'?0.93:0.9991,weeks:4,from:C.win&&C.win.from,to:C.win&&C.win.to,till:w==='wait'?synAdd(S,-10):synAdd(S,3)};
  const R=(C.rows||[]).filter(x=>x&&x.cc);
  if(w==='ok'){ let own=0; const J=R.filter(x=>!x.few&&x.clean!==false);
    J.forEach((x,i)=>{ if(i===J.length-1){ x.cpi={v:null,spend:0,noads:true}; x.pay=null; x.back=null; x.verdict=x.verdict==='few'?'few':'avg'; return; }
      const cpi=0.02+i*0.004, sp=+(cpi*x.n).toFixed(2); own+=sp; x.cpi={v:cpi,ads:+(cpi*1.3).toFixed(6),spend:sp,dl:Math.round(x.n*0.77),paid:0.77,src:+(cpi*90).toFixed(6),spend_src:+(sp*90).toFixed(2),ads_src:+(cpi*1.3*90).toFixed(6)};
      x.pay=i===0?{p:34,lo:34,hi:34,never:false,obs:true,q80_365:null}:(i===1?{p:61,lo:48,hi:80,never:false,obs:false,q80_365:null}:{p:null,lo:null,hi:null,never:true,obs:false,q80_365:0.02});
      x.back={'7':+(100*0.011/cpi).toFixed(1),'30':+(100*0.024/cpi).toFixed(1),'90':+(100*0.041/cpi).toFixed(1),'90_proj':i>0};
      x.trend=Object.assign({},x.trend||{},{cpi:[cpi*0.9,cpi*0.95,null,cpi,cpi*1.02,cpi*0.98,cpi,cpi*1.01,cpi*1.03,cpi,cpi*0.99,cpi]}); x.trend.cpi_src=x.trend.cpi.map(v=>v==null?null:+(v*90).toFixed(6)); x.verdict=V[i%3]; });
    const sm=C.small||(C.small={countries:0,n:0}); if(!(sm.n>0)){ sm.n=4200; } if(!(sm.countries>0)) sm.countries=7; sm.cost=+(own*0.04).toFixed(2); sm.cpi=+(sm.cost/sm.n).toFixed(6);
    const unm=+(own*0.012).toFixed(2), tot=+(own+sm.cost+unm).toFixed(2);
    sm.share=+(sm.cost/tot).toFixed(4); sm.dl=Math.round(sm.n*0.3); sm.cpi_ads=+(sm.cost/sm.dl).toFixed(6); sm.cost_src=+(sm.cost*90).toFixed(2);
    C.cost={total:tot,rows:+own.toFixed(2),small:sm.cost,unmapped:unm,unmapped_share:+(unm/tot).toFixed(4),spend:+(tot/0.9997).toFixed(2),total_src:+(tot*90).toFixed(2),small_src:sm.cost_src,unmapped_src:+(unm*90).toFixed(2)};
    const t=d.tiles.cty=Object.assign({},d.tiles.cty||{}); t.keep=J.filter(x=>x.verdict==='keep').map(x=>x.cc).slice(0,2); t.costly=J.filter(x=>x.verdict==='costly').map(x=>x.cc).slice(0,2); }
  else { R.forEach(x=>{ x.cpi=null; x.pay=null; x.back=null; if(V.includes(x.verdict)) x.verdict='avg'; }); C.cost=null;   // the engine's no-cost path (a fixture built with country cost on carries cost verdicts)
    if(d.tiles&&d.tiles.cty){ d.tiles.cty=Object.assign({},d.tiles.cty); delete d.tiles.cty.keep; delete d.tiles.cty.costly; } }
  return d;
}
// the alerts of the new families (and a geo_cost that absorbed a "fewer came back" move)
function synAlerts(d, which){
  const S=d.settled_till||'2026-09-16', base={app:d.app,app_id:d.app_id,source:'value',fresh:true,closed:null,opened:synAdd(S,-10),estimate:false,linked:false,tags:[],also:[],cc:null,data_till:S};
  const A={ver_watch:Object.assign({},base,{family:'ver_ret',severity:'watch',dir:'down',metric:'d1',ver:'2.2',ver_label:'v2.2',pver_label:'v2.1',unit:'pp',delta_pp:-4.7,now:27.1,before:31.8,
      week_from:synAdd(S,-40),week_to:synAdd(S,-21),base_from:synAdd(S,-75),base_to:synAdd(S,-48),users:9000,release:{date:synAdd(S,-41),version:'2.2',kind:'version',key:'ver:2.2@'+synAdd(S,-41)},tags:['update'],
      text:'v2.2 ke baad naye users kam ruk rahe: 100 me 27 agle din wapas, pichhle v2.1 me 32 (9,000 installs, 2 hafte se)'}),
    ver_warn:Object.assign({},base,{family:'ver_ret',severity:'warning',dir:'down',metric:'d7',ver:'2.2',ver_label:'v2.2',pver_label:'v2.1',unit:'pp',week_from:synAdd(S,-40),week_to:synAdd(S,-21),
      text:'v2.2 ke baad naye users kam ruk rahe: 100 me 11 hafte baad wapas, pichhle v2.1 me 13.5 (9,000 installs, 2 hafte se)'}),
    ver_good:Object.assign({},base,{family:'ver_ret',severity:'good',dir:'up',metric:'d1',ver:'2.0',ver_label:'v2.0',pver_label:'v1.9',unit:'pp',week_from:synAdd(S,-110),week_to:synAdd(S,-83),
      text:'v2.0 ke baad naye users zyada ruk rahe: 100 me 32 agle din wapas, pichhle v1.9 me 27'}),
    long_watch:Object.assign({},base,{family:'long_ret',severity:'watch',dir:'down',metric:'d90',unit:'pp',months:['2026-05','2026-04'],installs_from:'2026-04-01',installs_to:'2026-05-31',
      week_from:'2026-04-01',week_to:'2026-05-31',base_from:'2025-10-01',base_to:'2026-03-31',users:83000,text:'Apr–May 2026 ke installs 90 din baad kam bache: 100 me 4.1, pehle 5.9 (pichhle 6 mahine ka normal)'}),
    geo_also:Object.assign({},base,{family:'geo_cost',severity:'watch',dir:'down',metric:'pay',cc:'NG',also:['d1'],move:{now:17,before:28},week_from:synAdd(S,-30),week_to:synAdd(S,-3),
      text:'{cc:NG} me install mehenga, kamai kam: install {m:0.031}, 90 din me kamai {m:0.012}'})};
  return (which||Object.keys(A)).map(k=>A[k]);
}
`;
// ── synth: end ──
run(SYN);

// ── the section rendered from a copy of one app's detail, changed and restored (the fixture is never touched) ──
const synth = (nm, r, change, what) => scen(nm, `${RESET} (()=>{ const K=${J(r.key)}, keep=VALD[K], d=JSON.parse(JSON.stringify(keep)), V=DATA.value, row=V.apps.find(x=>x.key===K), rk=JSON.stringify(row), ka=V.alerts, kc=V.consts;
  V.consts=Object.assign({},kc,{cd:true}); ${change} VALD[K]=d; try{ ${openApp(r)} ${what || 'return valScreen();'} } finally{ VALD[K]=keep; Object.assign(row, JSON.parse(rk)); V.alerts=ka; V.consts=kc; } })()`);
const P = withPaid, O = withD.find(r => r !== P) || P;
// 🧬 New users by app version
synth('ver|desk', P, `d.by_version=synVer(d);`, `innerWidth=1280; return valVerCard(d);`);
synth('ver|phone', P, `d.by_version=synVer(d);`, `return valVerCard(d);`);
synth('ver|open_desk', P, `d.by_version=synVer(d); VALVEROPEN='2.2';`, `innerWidth=1280; return valVerCard(d);`);
// a 🧬 link (valVerGo) to a version with no row of its own: said on that app's section only; a version with a row: no note
synth('ver|link_norow', P, `d.by_version=synVer(d); VALVEROPEN='9.9'; VALVERAPP=d.app_id;`, `innerWidth=1280; return valVerCard(d);`);
synth('ver|link_norow_phone', P, `d.by_version=synVer(d); VALVEROPEN='9.9'; VALVERAPP=d.app_id;`, `return valVerCard(d);`);
synth('ver|link_row', P, `d.by_version=synVer(d); VALVEROPEN='2.2'; VALVERAPP=d.app_id;`, `innerWidth=1280; return valVerCard(d);`);
synth('ver|link_other_app', P, `d.by_version=synVer(d); VALVEROPEN='9.9'; VALVERAPP='ca-app-pub-0000000000000000~1';`, `innerWidth=1280; return valVerCard(d);`);
synth('ver|open_phone', P, `d.by_version=synVer(d); VALVEROPEN='2.2';`, `return valVerCard(d);`);
synth('ver|older', P, `d.by_version=synVer(d); VALVEROLD=true;`, `innerWidth=1280; return valVerCard(d);`);
synth('ver|open_old', P, `d.by_version=synVer(d); VALVEROPEN='1.4.2';`, `innerWidth=1280; return valVerCard(d);`);
synth('ver|inr', P, `d.by_version=synVer(d); CURVIEW='INR';`, `innerWidth=1280; return valVerCard(d);`);
for (const st of ['nosplit', 'nodata', 'low', 'single', 'error']) synth('ver|state|' + st, P, `d.by_version=synVer(d,'${st}');`, `return valVerCard(d);`);
synth('ver|state|unknown', P, `d.by_version={state:'x',rows:'y'};`, `return valVerCard(d);`);
for (const [k, al] of [['watch', 'ver_watch'], ['warn', 'ver_warn'], ['good', 'ver_good']])
  synth('ver|alert|' + k, P, `d.by_version=synVer(d); d.changes=Object.assign({},d.changes,{open:synAlerts(d,['${al}'])}); V.alerts=[];`, `innerWidth=1280; return valVerCard(d)+'<hr>'+(()=>{ innerWidth=375; return valVerCard(d); })();`);
synth('ver|alert_closed', P, `d.by_version=synVer(d); d.changes=Object.assign({},d.changes,{open:synAlerts(d,['ver_warn']).map(a=>Object.assign(a,{closed:'2026-09-01'}))}); V.alerts=[];`, `innerWidth=1280; return valVerCard(d);`);
// 🗓️ Long-term by install month
synth('long|desk', P, `d.long=synLong(d);`, `innerWidth=1280; return valLongCard(d);`);
synth('long|phone', P, `d.long=synLong(d);`, `return valLongCard(d);`);
synth('long|all', P, `d.long=synLong(d); VALLONG='all';`, `innerWidth=1280; return valLongCard(d);`);
synth('long|inr', P, `d.long=synLong(d); CURVIEW='INR';`, `innerWidth=1280; return valLongCard(d);`);
synth('long|quarter', P, `d.long=synLong(d,'quarter');`, `innerWidth=1280; return valLongCard(d);`);
synth('long|quarter_all', P, `d.long=synLong(d,'quarter'); VALLONG='all';`, `innerWidth=1280; return valLongCard(d);`);
synth('long|quarter_phone', P, `d.long=synLong(d,'quarter');`, `return valLongCard(d);`);
for (const st of ['young', 'low', 'error']) synth('long|state|' + st, P, `d.long=synLong(d,'month','${st}');`, `innerWidth=1280; return valLongCard(d);`);
synth('long|state|unknown', P, `d.long={state:'x',rows:7};`, `return valLongCard(d);`);
// 🌍 country cost (the week envelope)
const geoScen = (nm, why, what) => synth(nm, withCty, `synGeo(d,'${why}');`, what);
geoScen('geo|ok|desk', 'ok', `innerWidth=1280; return valCtyCard(d,row);`);
geoScen('geo|ok|phone', 'ok', `return valCtyCard(d,row);`);
geoScen('geo|ok|open_desk', 'ok', `innerWidth=1280; VALCTYEXP=d.countries.rows.filter(x=>x.cpi&&x.cpi.v!=null)[1].cc; return valCtyCard(d,row);`);
geoScen('geo|ok|open_phone', 'ok', `VALCTYEXP=d.countries.rows.filter(x=>x.cpi&&x.cpi.v!=null)[0].cc; return valCtyCard(d,row);`);
geoScen('geo|ok|tile', 'ok', `return valSumCard(d,row);`);
geoScen('geo|ok|inr', 'ok', `innerWidth=1280; CURVIEW='INR'; return valCtyCard(d,row);`);
geoScen('geo|ok|inr_open', 'ok', `innerWidth=1280; CURVIEW='INR'; VALCTYEXP=d.countries.rows.filter(x=>x.cpi&&x.cpi.v!=null)[0].cc; return valCtyCard(d,row);`);
for (const w of ['cov', 'wait', 'nostore', 'noads']) { geoScen('geo|' + w + '|desk', w, `innerWidth=1280; return valCtyCard(d,row);`); geoScen('geo|' + w + '|phone', w, `return valCtyCard(d,row);`); }
synth('geo|small_unmapped', withCty, `synGeo(d,'ok'); d.countries.cost.unmapped_share=0.004;`, `innerWidth=1280; return valCtyCard(d,row);`);
// the review's fixes: a trickle of ads ("Little ads", never judged) · not paid back within the curve ("late", "Over 90
// days") · a country whose cost may sit in the unmapped part ("—", never "No ads here") · ₹ back ≈ when those weeks'
// cost is not all known · a big small-countries share said in bold
const geoFix = `synGeo(d,'ok'); const J=d.countries.rows.filter(x=>x.cpi&&x.cpi.v!=null);
  Object.assign(J[0].cpi,{thin:'paid',paid:0.01,dl:30}); J[0].pay=null; J[0].back=null; J[0].verdict='low'; globalThis.__THIN=J[0].cc;
  J[1].pay={p:null,lo:null,hi:null,never:false,obs:false,q80_365:null,upto:90}; J[1].verdict='late'; J[1].back=Object.assign({},J[1].back,{'30_est':true}); globalThis.__LATE=J[1].cc;
  if(J[2]){ J[2].cpi={v:null,spend:null,unknown:true}; J[2].pay=null; J[2].back=null; J[2].verdict='avg'; globalThis.__UNK=J[2].cc; }
  d.countries.small.share=0.24;`;
synth('geo|fix|desk', withCty, geoFix, `innerWidth=1280; return valCtyCard(d,row);`);
synth('geo|fix|phone', withCty, geoFix, `return valCtyCard(d,row);`);
synth('geo|fix|open_thin', withCty, geoFix, `innerWidth=1280; VALCTYEXP=__THIN; return valCtyCard(d,row);`);
synth('geo|fix|open_late', withCty, geoFix, `innerWidth=1280; VALCTYEXP=__LATE; return valCtyCard(d,row);`);
synth('geo|fix|open_unk', withCty, geoFix, `innerWidth=1280; VALCTYEXP=globalThis.__UNK||__LATE; return valCtyCard(d,row);`);
// 🧬: a finished 1-day version with many installs ("Too short to compare", never "few installs" / "wait"), a part cell on
// few installs (grey), the phone's pair = the comparison's own (first 28 days vs the previous version's last 28)
const verFix = `d.by_version=synVer(d); const R=d.by_version.rows, x=R[2];
  Object.assign(x,{days:1,n:1824,to:x.from,verdict:'short',text:'v2.1: 1,824 installs, sirf 1 din naye users isi version pe aaye — tulna ke liye 3+ din chahiye'});
  x.vs=Object.assign({},x.vs,{d1:Object.assign({},x.vs.d1,{st:'short',days1:1}),d7:Object.assign({},x.vs.d7,{st:'short',days1:1})});
  R[0].d1=Object.assign({},R[0].d1,{n:260,ret:37,few:true}); R[1].d1=Object.assign({},R[1].d1,{v:34.29});
  R[1].vs=Object.assign({},R[1].vs,{d1:Object.assign({},R[1].vs.d1,{v0:34.51,v1:34.51,delta:0.001})});`;
synth('ver|fix|desk', P, verFix, `innerWidth=1280; return valVerCard(d);`);
synth('ver|fix|phone', P, verFix, `return valVerCard(d);`);
// a 🧬 link to an update released after the newest install-day data: "abhi naya", never "rollout / under 100"
synth('ver|link_new', P, `d.by_version=synVer(d); VALVEROPEN='9.9'; VALVERAPP=d.app_id; VALVERDATE=synAdd(d.settled_till,3);`, `innerWidth=1280; return valVerCard(d);`);
synth('ver|link_old', P, `d.by_version=synVer(d); VALVEROPEN='9.9'; VALVERAPP=d.app_id; VALVERDATE=synAdd(d.settled_till,-60);`, `innerWidth=1280; return valVerCard(d);`);
// 🗓️: an age not old enough and not projected reads "6 mo in N days" in the combined cell; a month with a trickle of spend: "Little ads"
synth('long|fix', P, `d.long=synLong(d); const R=d.long.rows; for(const x of R){ for(const t of ['90','180','365']){ const c=x.rpi[t]; if(c&&c.proj){ x.rpi[t]={v:null,lo:null,hi:null,est:false,proj:false,shape:null,st:'wait',in:c.in}; } } }
  R[5].b365=null; R[5].b365_proj=false; R[5].b365_thin=true; R[6].b365=null; R[6].b365_thin=false;
  d.long.base['90']=Object.assign({},d.long.base['60']); d.long.base.rpi180=Object.assign({},d.long.base['60'],{v:0.045});`, `innerWidth=1280; return valLongCard(d);`);
// the whole page with everything on: phone and desktop, $ and ₹
const allOn = `d.by_version=synVer(d); d.long=synLong(d); synGeo(d,'ok'); const W=(d.weeks||[]).filter(w=>w.judged).sort((p,q)=>p.from<q.from?1:-1)[1]||(d.weeks||[])[1];
  if(W) W.release={date:W.from,version:'2.2',kind:'version',key:'ver:2.2@'+W.from,label:'v2.2'}; d.changes=Object.assign({},d.changes,{open:(d.changes.open||[]).concat(synAlerts(d,['ver_watch','long_watch','geo_also'])),
  info:(d.changes.info||[]).concat([{kind:'ver_d30',from:d.settled_till,to:d.settled_till,text:'v2.1 ke naye users 30 din baad kam: 100 me 5.4, pichhle v2.0 me 5.5'},{kind:'long_up',from:'2026-03-01',to:'2026-04-30',text:'Mar–Apr 2026 ke installs 90 din baad zyada bache: 100 me 6.4, pehle 5.9'}])});`;
synth('page|phone', withCty, allOn);
synth('page|desk', withCty, allOn, `innerWidth=1280; return valScreen();`);
synth('page|inr', withCty, allOn, `innerWidth=1280; CURVIEW='INR'; return valScreen();`);
synth('page|folds', withCty, allOn + ` VALOLDEXP=true; VALCLEXP=true; VALCHKEXP=true; VALTIMEXP=true; VALVEROPEN='2.2';`);
// the same page with C / D / G off (arrays, no envelope): the Countries slice and the money-back table are the same as before
synth('page|off_desk', withCty, `d.by_version=[]; d.long=[];`, `innerWidth=1280; return valScreen();`);
synth('page|cd_desk', withCty, `d.by_version=synVer(d); d.long=synLong(d);`, `innerWidth=1280; return valScreen();`);
synth('page|off_phone', withCty, `d.by_version=[]; d.long=[];`, `return valScreen();`);
synth('page|cd_phone', withCty, `d.by_version=synVer(d); d.long=synLong(d);`, `return valScreen();`);
// an old file: by_version / long arrays (or missing) → nothing at all
synth('old|arrays', P, `d.by_version=[]; d.long=[];`, `return JSON.stringify([valVerCard(d),valLongCard(d),valVerLnk(d,{version:'2.2'})]);`);
synth('old|missing', P, `delete d.by_version; delete d.long;`, `return JSON.stringify([valVerCard(d),valLongCard(d)]);`);
// the money-back table's 📦 row → the 🧬 row (only when 🧬 has that version)
const relScen = (nm, ver) => synth(nm, P, `d.by_version=synVer(d); const W=(d.weeks||[]).filter(w=>w.judged).sort((p,q)=>p.from<q.from?1:-1), w1=W[1]||W[0];
  w1.release={date:w1.from,version:'${ver}',kind:'version',key:'ver:${ver}@'+w1.from}; globalThis.__RELW=w1.from;`, `innerWidth=1280; VALWK='all'; return valPayCard(d,row)+'<hr>'+(()=>{ innerWidth=375; return valPayCard(d,row); })();`);
relScen('rel|has', '2.2');
relScen('rel|missing', '9.9');
synth('rel|no_cd', P, `d.by_version=[]; const W=(d.weeks||[]).filter(w=>w.judged).sort((p,q)=>p.from<q.from?1:-1), w1=W[1]||W[0]; w1.release={date:w1.from,version:'2.2',kind:'version',key:'ver:2.2@'+w1.from};`,
  `innerWidth=1280; VALWK='all'; return valPayCard(d,row);`);
// "What changed?" rows of the new families (on the app's page, and on All apps)
synth('chg|app', P, `d.changes=Object.assign({},d.changes,{open:synAlerts(d),info:[{kind:'ver_d30',from:'2026-09-01',to:'2026-09-14',text:'v2.1 ke naye users 30 din baad kam: 100 me 5.4, pichhle v2.0 me 5.5'},
  {kind:'ver_mix',from:'2026-09-01',to:'2026-09-14',text:'v2.2 ke baad naye users kam ruk rahe — installs kam, alert nahi'},{kind:'long_up',from:'2026-03-01',to:'2026-04-30',text:'Mar–Apr 2026 ke installs 90 din baad zyada bache: 100 me 6.4, pehle 5.9'}]});`,
  `return valChangesCard(d);`);
synth('chg|all', P, `V.alerts=synAlerts(d);`, `APP=''; VALAPP=''; return valPortfolio();`);
// the Alerts screen: the new families' cards (title, what, Open → its own row / section, Update detail →)
scen('alerts|cd', `${RESET} (()=>{ const keep=screenDiv, V=DATA.value, ka=V.alerts, d=VALD[${J(P.key)}]; screenDiv=id=>({dataset:{screen:id},innerHTML:''}); V.alerts=synAlerts(d);
  try{ return renderAlerts().innerHTML; } finally { screenDiv=keep; APP=''; V.alerts=ka; } })()`);
scen('alerts|cards', `${RESET} (()=>{ const V=DATA.value, ka=V.alerts, d=VALD[${J(P.key)}]; V.alerts=synAlerts(d); try{ return valAlertCards(valAlertsFor()); } finally { V.alerts=ka; } })()`);
// 📦 Update impact (Uninstall / Active): an open version block links to 🧬 — only with DATA.value, consts.cd and the app's value page
const IMP = `const b={key:'ver:2.2@2026-08-06',rel_keys:['ver:2.1.9@2026-08-04','ver:2.2@2026-08-06'],kind:'version',versions:['2.1.9','2.2'],label:'v2.1.9 → v2.2',date:'2026-08-04',
  verdict:{level:'continue',final:true,why:'Koi pakka nuksaan nahi'},windows:{before:{from:'2026-07-28',to:'2026-08-03'},after:{from:'2026-08-06',to:'2026-08-12',days:7,settled:7}},rows:{},versions_cmp:null,notes:[]};`;
const impScen = (nm, pre, a, open, t) => scen(nm, `${RESET} (()=>{ const V=DATA.value, kc=V&&V.consts; ${IMP} ${pre}
  try{ return uniImpBlock(${a},b,${open},${J(t)}); } finally { if(V){ DATA.value=V; V.consts=kc; } } })()`);
const AID = J((P || {}).app_id || '');
impScen('imp|on_act', `V.consts=Object.assign({},kc,{cd:true});`, `{app_id:${AID},app:${J(P.app)}}`, true, 'act');
impScen('imp|on_uni', `V.consts=Object.assign({},kc,{cd:true});`, `{app_id:${AID},app:${J(P.app)}}`, true, 'uni');
impScen('imp|closed', `V.consts=Object.assign({},kc,{cd:true});`, `{app_id:${AID},app:${J(P.app)}}`, false, 'act');
impScen('imp|cd_off', `V.consts=Object.assign({},kc,{cd:false});`, `{app_id:${AID},app:${J(P.app)}}`, true, 'act');
impScen('imp|no_value', `delete DATA.value;`, `{app_id:${AID},app:${J(P.app)}}`, true, 'act');
impScen('imp|other_app', `V.consts=Object.assign({},kc,{cd:true});`, `{app_id:'ca-app-pub-0000000000000000~1',app:'Nope'}`, true, 'act');
impScen('imp|update_kind', `V.consts=Object.assign({},kc,{cd:true}); b.kind='update'; b.versions=[];`, `{app_id:${AID},app:${J(P.app)}}`, true, 'act');
impScen('imp|base_act', `delete DATA.value; b.kind='update'; b.versions=[];`, `{app_id:${AID},app:${J(P.app)}}`, true, 'act');
impScen('imp|base_act_cd', `V.consts=Object.assign({},kc,{cd:true}); b.kind='update'; b.versions=[];`, `{app_id:${AID},app:${J(P.app)}}`, true, 'act');
// an update newer than the app's install-day data: the link says the numbers come in a few days (never promises them)
impScen('imp|newer', `V.consts=Object.assign({},kc,{cd:true}); const r0=V.apps.find(x=>x.app_id===${AID}); b.date=synAdd(r0.settled_till,2);`, `{app_id:${AID},app:${J(P.app)}}`, true, 'act');
// the jumps: an Alerts card / a 📦 block → the tab, that app, the version row open (show / render stubbed)
let jumps = null;
try { jumps = JSON.parse(run(`(()=>{ const keep={render, show, _navSave}, calls=[]; render=function(){}; show=function(id){ calls.push(id); }; _navSave=function(){};
  try{ ${RESET} const r=DATA.value.apps.find(x=>x.key===${J(P.key)}); valVerGo(r.app_id,'2.2'); const a={calls:calls.slice(), app:APP, open:VALVEROPEN, jump:VALJUMP, vapp:VALVERAPP===r.app_id};
    ${RESET} calls.length=0; valGoTo(r.app_id,'val-long'); const b={calls:calls.slice(), app:APP, jump:VALJUMP};
    ${RESET} VALVEROPEN=''; valVX('2.2'); const c1=VALVEROPEN; valVX('2.2'); const c2=VALVEROPEN; valVOX(); const o1=VALVEROLD; valLG('all'); const l1=VALLONG; valLG('18'); const l2=VALLONG;
    VALVEROPEN='2.2'; VALVEROLD=true; VALVERAPP='x'; valBack(); const bk={open:VALVEROPEN, old:VALVEROLD, app:VALVERAPP};
    return JSON.stringify({ver:a, long:b, toggles:{c1,c2,o1,l1,l2}, back:bk}); }
  finally{ render=keep.render; show=keep.show; _navSave=keep._navSave; VALJUMP=''; ${RESET} } })()`)); } catch (e) { errors.push('jumps: ' + e.message); }

// ── what the page says ──
const text = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&quot;/g, '"').replace(/\s+/g, ' ').trim();
const uiText = h => h.replace(/\son\w+="[^"]*"/g, '').replace(/\sid="[^"]*"/g, '');
const sec = (h, a, b) => (h.split(a)[1] || '').split(b)[0];
const T = k => text(out[k] || '');
const bad = [], jargon = [], devanagari = [], tokens = [];
const JARGON = /cumulative|checkpoint|cohort|bharosa|headline|\bLTV\b/i, DEVA = /[ऀ-ॿ]/, TOK = /\{(m|b|s|q|p|cc|c)(:[^{}]*)?\}/;
for (const [k, v] of Object.entries(out)) {
  for (const w of ['undefined', 'NaN', '[object Object]', 'Infinity']) if (v.includes(w)) bad.push(k + ': ' + w);
  const m = uiText(v).match(JARGON); if (m) jargon.push(k + ': ' + m[0]);
  if (DEVA.test(v)) devanagari.push(k);
  if (TOK.test(text(v))) tokens.push(k);
}
// numbers never coloured: no red / green text colour, no up / down classes, anywhere in the tab's own sections
const COLOR_RE = /var\(--bad\)|var\(--good\)|class="(up|down)"|#ff6b6b|#34d99a|rgba\(255,107,107|rgba\(52,217,154/;
const coloured = Object.entries(out).filter(([k, v]) => !k.startsWith('alerts|') && COLOR_RE.test(v)).map(([k]) => k);
// ids: prefixed, never twice on one screen
const idsOf = h => [...h.matchAll(/\sid="([^"]*)"/g)].map(m => m[1]);
const ids = Object.entries(out).filter(([k, v]) => /^(ver|long|geo|page|rel)\|/.test(k) && !v.includes('<hr>')).map(([k, v]) => { const l = idsOf(v); return { scen: k, dup: [...new Set(l.filter((x, i) => l.indexOf(x) !== i))], bad: l.filter(x => !x.startsWith('val-')) }; });
// phone: every table in a scroller; nothing else wider than a phone
const wide = [];
for (const [k, v] of Object.entries(out)) {
  if (!/\|(phone|open_phone|quarter_phone)$/.test(k) && !/^ver\|state\|/.test(k)) continue;
  for (const m of v.matchAll(/min-width:(\d+)px/g)) { const before = v.slice(Math.max(0, m.index - 400), m.index); if (+m[1] > 340 && !/<div class="uni-scroll"[^>]*><table [^>]*$/.test(before)) wide.push(k + ': ' + m[1]); }
  for (const m of v.matchAll(/<table /g)) { const before = v.slice(Math.max(0, m.index - 60), m.index); if (!/<div class="uni-scroll"[^>]*>$/.test(before)) wide.push(k + ': table outside a scroller'); }
  for (const m of v.replace(/<svg[\s\S]*?<\/svg>/g, '').matchAll(/\swidth="(\d+)"/g)) if (+m[1] > 340) wide.push(k + ': fixed width ' + m[1]);
}
const heads = s => [...sec(s, '<thead>', '</thead>').matchAll(/<th[^>]*>([^<]*)/g)].map(m => m[1]);
const pillsV = h => [...h.matchAll(/<span class="pill ([a-z0-9-]+)" data-vst="([a-z_]+)"[^>]*>([^<]*)<\/span>/g)].map(m => [m[1], m[2], m[3]]);
// 🧬 rows: data-ver → its cells (text) and chip
const verRows = h => [...h.matchAll(/<tr class="clk( on)?" data-ver="([^"]*)"( id="val-vopen")? onclick="valVX\('([^']*)'\)">([\s\S]*?)<\/tr>/g)].map(m => ({ ver: m[2], on: !!m[1], id: !!m[3], call: m[4],
  cells: [...m[5].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(c => text(c[1])), chip: (pillsV(m[5])[0] || null), few: m[5].includes('>few installs</span>'),
  titles: [...m[5].matchAll(/title="([^"]*)"/g)].map(t => t[1]) }));
const verCards = h => [...h.matchAll(/<div class="val-vc( open)?" data-ver="([^"]*)"( id="val-vopen")? onclick="valVX\('([^']*)'\)">([\s\S]*?)(?=<div class="val-vc|<\/div><div style="padding:8px|<\/div><div class="val-foot"|$)/g)]
  .map(m => ({ ver: m[2], open: !!m[1], h: text((m[5].match(/<div class="h">([\s\S]*?)<\/div>/) || [])[1] || ''), m: text((m[5].match(/<div class="m">([\s\S]*?)<\/div>/) || [])[1] || ''),
    chip: pillsV(m[5])[0] || null, detail: text(sec(m[5], '<div class="val-vxd">', '</div></div>')) }));
const V = k => { const h = out[k] || ''; return { heads: heads(h), rows: verRows(h), cards: verCards(h), lead: text(sec(h, 'id="val-vlead">', '</div>')), vnone: text(sec(h, 'id="val-vnone">', '</div>')), empty: text(sec(h, '<div class="uni-empty"', '</div>')).replace(/^[^>]*>/, '').trim(),
  foot: [...(sec(h, 'id="val-vfoot">', '</div></div></div>') + '</div>').matchAll(/<div>([\s\S]*?)<\/div>/g)].map(m => text(m[1])),
  more: text(sec(h, '<div style="padding:8px 17px 0;display:grid;gap:4px">', '<div class="val-foot"')), fold: /onclick="valVOX\(\)"/.test(h),
  open: text(sec(h, '<tr class="val-vx"', '</tr>')), open_rel: [...h.matchAll(/onclick="event\.stopPropagation\(\);uniImpGo\('([^']*)','([^']*)','act'\)">([^<]*)</g)].map(m => [m[1], m[2], m[3]]),
  table: h.includes('id="val-vtbl"'), cardsbox: h.includes('id="val-vcards"'), id: h.includes('id="val-ver"'), html_len: h.length }; };
const ver = {};
for (const k of Object.keys(out).filter(k => k.startsWith('ver|'))) ver[k.slice(4)] = V(k);
for (const k of ['watch', 'warn', 'good']) { const [a, b] = (out['ver|alert|' + k] || '').split('<hr>'); ver['alert|' + k] = { desk: pillsV(a || ''), phone: pillsV(b || '') }; }
// 🗓️ rows: separators and month rows in order
const longRows = h => [...sec(h, '<tbody>', '</tbody>').matchAll(/<tr (class="val-yr" data-yr="([^"]*)"|data-month="([^"]*)")>([\s\S]*?)<\/tr>/g)].map(m => m[2] ? { yr: m[2], t: text(m[4]) }
  : { key: m[3], cells: [...m[4].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(c => text(c[1])), label: text((m[4].match(/<td class="nm">([\s\S]*?)<\/td>/) || [])[1] || ''),
    part_tip: (m[4].match(/<b style="color:#fff" title="([^"]*)">/) || [])[1] || null, proj: (m[4].match(/class="val-lproj" data-proj="1"/g) || []).length,
    rel: [...m[4].matchAll(/<span class="val-lrel" title="([^"]*)"( onclick="uniImpGo\('([^']*)','([^']*)','act'\)")?>/g)].map(x => [x[1], x[4] || null]),
    titles: [...m[4].matchAll(/title="([^"]*)"/g)].map(t => t[1]) });
const Lg = k => { const h = out[k] || ''; return { heads: heads(h), rows: longRows(h), lead: text(sec(h, 'id="val-llead">', '</div>')), base: text(sec(h, 'id="val-lbase">', '</div>')),
  empty: text(sec(h, '<div class="uni-empty"', '</div>')).replace(/^[^>]*>/, '').trim(), foot: [...(sec(h, 'id="val-lfoot">', '</div></div></div>') + '</div>').matchAll(/<div>([\s\S]*?)<\/div>/g)].map(m => text(m[1])),
  chips: [...h.matchAll(/<span class="chip( on)?" onclick="valLG\('([^']*)'\)">([^<]*)<\/span>/g)].map(m => [m[2], m[3], !!m[1]]), minw: (h.match(/id="val-ltbl" style="min-width:(\d+)px"/) || [])[1],
  sticky: /<table class="uni-sticky val-ltbl"/.test(h), scroller: /<div class="uni-scroll"[^>]*><table class="uni-sticky val-ltbl"/.test(h), id: h.includes('id="val-long"'), html_len: h.length }; };
const long = {};
for (const k of Object.keys(out).filter(k => k.startsWith('long|'))) long[k.slice(5)] = Lg(k);
// 🌍 geo
const G = k => { const h = out[k] || ''; const ct = sec(h, 'id="val-ctbl"', '</tbody>');
  return { heads: heads(h), notes: [...h.matchAll(/<div class="val-note" id="(val-[a-z]+)">([\s\S]*?)<\/div>/g)].map(m => [m[1], text(m[2])]),
    rows: [...ct.matchAll(/<tr class="clk" data-cc="([^"]*)"[^>]*>([\s\S]*?)<\/tr>/g)].map(m => { const c = [...m[2].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(x => x[1]);
      return { cc: m[1], cells: c.map(text), raw: c, verdict: (m[2].match(/data-st="([a-z_]+)"/) || [])[1] || null }; }),
    all: (() => { const m = ct.match(/<tr class="val-all"[^>]*>([\s\S]*?)<\/tr>/); return m ? [...m[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(x => text(x[1])) : []; })(),
    rest: [...sec(h, 'id="val-rest">', '<div style="padding:4px 17px 14px">').matchAll(/<div>([\s\S]*?)<\/div>/g)].map(m => text(m[1])),
    strip: text(sec(h, 'id="val-cstrip">', '</div>')), open: text(sec(h, '<tr class="val-cx"', '</tr>')), open_sparks: (sec(h, '<tr class="val-cx"', '</tr>').match(/<svg /g) || []).length,
    cards: [...h.matchAll(/<div class="val-cc[^"]*" data-cc="([^"]*)" onclick[^>]*>([\s\S]*?)<div class="p">/g)].map(m => [m[1], text((m[2].match(/<div class="m">([\s\S]*?)<\/div>/) || [])[1] || '')]),
    open_phone: text(sec(h, '<div class="val-cxd">', '</div></div></div>')), html: k.endsWith('|desk') ? '' : '', minw: (h.match(/id="val-ctbl" style="min-width:(\d+)px"/) || [])[1] }; };
const geo = {};
for (const k of Object.keys(out).filter(k => k.startsWith('geo|'))) geo[k.slice(4)] = G(k);
const tileH = out['geo|ok|tile'] || '', tcty = (tileH.match(/data-m="cty"[\s\S]*$/) || [''])[0];
geo.tile = { big: text((tcty.match(/<div class="v[^"]*">([\s\S]*?)<\/div>/) || [])[1] || ''), sub: text((tcty.match(/<div class="val-sl">([\s\S]*?)<\/div>/) || [])[1] || '') };
// the geo tooltips (cost / money back cells)
geo.tips = [...sec(out['geo|ok|desk'] || '', 'id="val-ctbl"', '</tbody>').matchAll(/<td class="uni-num"><span( class="faint")? title="([^"]*)">([^<]*)<\/span><\/td>/g)].map(m => [m[3], m[2], !!m[1]]);
// the whole page
const order = h => ['val-sum', 'val-chg', 'val-pay', 'val-cty', 'val-ver', 'val-long', 'val-chk', 'val-timing'].map(s => h.indexOf('id="' + s + '"'));
// the Countries slice the existing harness reads (tests/value_frontend.js): the same with C / D on as off
const ctySlice = h => { const c = sec(h, 'id="val-cty"', 'id="val-chk"');
  return { heads: heads(c), rows: [...c.matchAll(/<tr class="clk" data-cc="([^"]*)"/g)].map(m => m[1]), phone: [...c.matchAll(/<div class="val-cc[^"]*" data-cc="([^"]*)" onclick/g)].map(m => m[1]),
    verdicts: [...c.matchAll(/<tr class="clk" data-cc="([^"]*)"[\s\S]*?<span class="pill ([a-z0-9-]+)" data-st="([a-z_]+)"[^>]*>([^<]*)<\/span><\/td><\/tr>/g)].map(m => [m[1], m[2], m[3], m[4]]),
    few: [...c.matchAll(/<tr class="clk" data-cc="([^"]*)"[^>]*>[\s\S]*?<\/tr>/g)].filter(m => m[0].includes('>few installs</span>')).map(m => m[1]),
    rest: [...sec(c, 'id="val-rest">', '<div style="padding:4px 17px 14px">').matchAll(/<div>([\s\S]*?)<\/div>/g)].map(m => text(m[1])),
    ccards: c.includes('id="val-ccards"'), ctbl: c.includes('id="val-ctbl"'), nogeo: c.includes('id="val-nogeo"'), link: c.includes(`onclick="show('countries')">AdMob eCPM by country → Country Strategy</span>`),
    strip: text(sec(c, 'id="val-cstrip">', '</div>')), win: text(sec(c, 'id="val-cwin"', '</div>')), m: (sec(c, 'id="val-ccards"', 'id="val-rest"').match(/<div class="m">([\s\S]*?)<\/div>/) || [])[1] || '',
    stpills: [...c.matchAll(/<span class="pill (p-r|p-g|p-y)" data-st="([a-z_]+)"/g)].map(m => m[1] + ':' + m[2]) }; };
const paySlice = h => sec(h, 'id="val-pay"', 'id="val-cty"');
const page = { phone: order(out['page|phone'] || ''), desk: order(out['page|desk'] || ''), off: order(out['page|off_desk'] || ''),
  titles: ['🧬 New users by app version', '🗓️ Long-term by install month'].filter(x => T('page|desk').includes(x)),
  slice_same_desk: J(ctySlice(out['page|off_desk'] || '')) === J(ctySlice(out['page|cd_desk'] || '')), slice_same_phone: J(Object.assign(ctySlice(out['page|off_phone'] || ''), { heads: null })) === J(Object.assign(ctySlice(out['page|cd_phone'] || ''), { heads: null })),   // a phone's Countries has no table (cards): its first <thead> is not its own
  pay_same: paySlice(out['page|off_desk'] || '') === paySlice(out['page|cd_desk'] || ''), slice_off: ctySlice(out['page|off_desk'] || ''),
  off_has: ['val-ver', 'val-long', 'uni-imp-ver', 'val-vlk'].filter(x => (out['page|off_desk'] || '').includes(x) || (out['page|off_phone'] || '').includes(x)),
  inr_b365: heads(sec(out['page|inr'] || '', 'id="val-long"', 'id="val-chk"')).find(h => /^1 yr per/.test(h)) || null,
  folds_open: (out['page|folds'] || '').includes('id="val-vopen"'), chg_fams: [...sec(out['page|desk'] || '', 'id="val-chg"', 'id="val-pay"').matchAll(/<div class="uni-chg na" data-fam="([^"]*)"/g)].map(m => m[1]) };
// the money-back 📦 row
const relOf = k => { const [a, b] = (out[k] || '').split('<hr>'); const f = h => [...(h || '').matchAll(/<tr class="uni-rel"><td class="nm">[\s\S]*?<\/td><td colspan="(\d+)">([\s\S]*?)<\/td><\/tr>/g)].map(m => ({ span: +m[1], cell: m[2] }));
  return { desk: f(a), phone: f(b), calls: [...(out[k] || '').matchAll(/onclick="valVerJump\('([^']*)'\)">([^<]*)</g)].map(m => [m[1], m[2]]) }; };
const rel = { has: relOf('rel|has'), missing: relOf('rel|missing'), no_cd: relOf('rel|no_cd') };
// "What changed?"
const chgRows = h => [...h.matchAll(/<div class="uni-chg (na|wa)( cl)?" data-fam="([^"]*)"(?: onclick="([^"]*)")?>([\s\S]*?)<\/span><\/span><\/div>/g)].map(m => ({ fam: m[3], call: m[4] || (m[5].match(/<span class="lnk" onclick="([^"]*)">Open →/) || [])[1] || null, t: text(m[5]) }));
const chg = { app: chgRows(out['chg|app'] || ''), all: chgRows(sec(out['chg|all'] || '', 'id="val-chg"', 'id="val-table"')),
  info: [...(out['chg|app'] || '').matchAll(/data-info="([^"]*)"[\s\S]*?<span class="lnk" onclick="([^"]*)">Open →/g)].map(m => [m[1], m[2]]), info_tags: [...(out['chg|app'] || '').matchAll(/data-info="([^"]*)"[\s\S]*?<span class="pill uni-pz">([^<]*)<\/span>/g)].map(m => [m[1], m[2]]) };
// the Alerts screen
const cards = h => [...h.matchAll(/<div class="alert ([a-z]+)" data-sev="([a-z]+)" data-metrics="value">([\s\S]*?)<div class="aact">([\s\S]*?)<\/div><\/div><\/div>/g)].map(m => ({ sev: m[2], title: text((m[3].match(/<div class="atitle">([\s\S]*?)<span class="pill/) || [])[1] || ''),
  cause: text((m[3].match(/<div class="acause"[^>]*>([\s\S]*?)<\/div>/) || [])[1] || ''), btns: [...m[4].matchAll(/<span class="abtn[^"]*" onclick="([^"]*)">([^<]*)<\/span>/g)].map(b => [b[1], b[2]]) }));
const alerts = { cards: cards(out['alerts|cards'] || ''), screen: cards(out['alerts|cd'] || ''), sub: (out['alerts|cd'] || '').includes('💸 Install value (GA4 + Ads)') };
// 📦 Update impact block
const imp = Object.fromEntries(Object.keys(out).filter(k => k.startsWith('imp|')).map(k => [k.slice(4), { link: (out[k].match(/<div class="uni-imp-ver">([\s\S]*?)<\/div>/) || [])[0] || null, len: out[k].length,
  call: (out[k].match(/onclick="valVerGo\('([^']*)','([^']*)'(?:,'([^']*)')?\)"/) || []).slice(1), text: text((out[k].match(/<div class="uni-imp-ver">([\s\S]*?)<\/div>/) || [])[1] || ''), ends: out[k].slice(-12) }]));
imp.base_same = (out['imp|base_act'] || '') === (out['imp|base_act_cd'] || '');
// helpers checked on their own
const fmt = JSON.parse(run(`JSON.stringify({lab:['2.4.1','v2.4.1','V3',7,null].map(valVLabel), pts:[-3,-0.46,0.5,4.04,0,null,12.6].map(valPts),
  per:[['2026-06','2026-07'],['2025-12','2026-01'],['2026-05','2026-05'],['2026-Q1','2026-Q2'],['2026-04-01','2026-05-31'],[null,null]].map(([a,b])=>valPerSpan(a,b)),
  llab:[{label:'Sep 2025',key:'2025-09'},{label:'Q3 2025 (Jul–Sep)',key:'2025-Q3'},{key:'2025-Q1'},{key:'2026-02'},{from:'2024-11-15'}].map(valLLab),
  months:[{family:'long_ret',months:['2026-05','2026-04']},{family:'long_ret',installs_from:'2025-12-01',installs_to:'2026-01-31'}].map(valAlMonths)})`));
// the fixture itself, once the build writes C / D into it (consts.cd): its pages carry the sections in order
const fixture = { cd: fixCd, apps: {} };
for (const r of withD) {
  const d = det(r), h = String(run(`(()=>{ ${RESET} ${openApp(r)} innerWidth=1280; return valScreen(); })()`)), hp = String(run(`(()=>{ ${RESET} ${openApp(r)} return valScreen(); })()`));
  // a country row with its own cost opened (desktop and phone): the engine's own cpi / pay / back / trend.cpi drawn
  const cx = (((d.countries || {}).rows) || []).find(x => x && x.cpi && x.cpi.v != null), cxs = cx ? `VALCTYEXP=${J(cx.cc)};` : '';
  const hx = cx ? String(run(`(()=>{ ${RESET} ${openApp(r)} ${cxs} innerWidth=1280; return valScreen(); })()`)) + String(run(`(()=>{ ${RESET} ${openApp(r)} ${cxs} return valScreen(); })()`)) : '';
  const bv = d.by_version, lg = d.long, cs = sec(h, 'id="val-cty"', 'id="val-chk"');
  fixture.apps[r.app] = { bv: Array.isArray(bv) ? 'array' : (bv && typeof bv === 'object' ? String(bv.state) : String(bv)), long: Array.isArray(lg) ? 'array' : (lg && typeof lg === 'object' ? String(lg.state) : String(lg)),
    order: order(h), order_phone: order(hp), ver_rows: verRows(h).map(x => x.ver), ver_cards: verCards(hp).map(x => x.ver), long_rows: longRows(sec(h, 'id="val-long"', 'id="val-chk"')).filter(x => x.key).map(x => x.key),
    geo_why: ((d.countries || {}).geo_why) || null, cost_cols: heads(cs).includes('Cost per install'), noads: (cs.match(/>No ads here</g) || []).length,
    geo_note: cs.includes('id="val-geowhy"'), nogeo: cs.includes('id="val-nogeo"'), opened: cx ? (hx.match(/Cost per install \(12 weeks\)|₹100 ke ads pe|\$100 ke ads pe/g) || []).length : null,
    bad: ['undefined', 'NaN', '[object Object]', 'Infinity'].filter(w => h.includes(w) || hp.includes(w) || hx.includes(w)), deva: DEVA.test(h + hp + hx), jargon: JARGON.test(uiText(h + hp + hx)), tokens: TOK.test(text(h + hp + hx)) };
}
console.log(JSON.stringify({
  scenarios: Object.keys(out).length, errors, bad, jargon, devanagari, tokens, coloured, wide, ids, ver, long, geo, page, rel, chg, alerts, imp, jumps, fmt, fixture,
  old: { arrays: JSON.parse(out['old|arrays'] || 'null'), missing: JSON.parse(out['old|missing'] || 'null') },
  texts: Object.fromEntries(Object.entries(out).filter(([k]) => /^(ver|long|geo)\|/.test(k)).map(([k]) => [k, T(k).slice(0, 6000)])),
}, null, 1));
