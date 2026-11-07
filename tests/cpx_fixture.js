// 📉 CPI vs eCPM — a SYNTHETIC build output in the exact shapes of SPEC §3.3 (admob_iq/cpi_build.py): the pointer DATA.cpi,
// the all-apps file cpi.json.gz and one cpi_<key>.json.gz per app, plus the slice of DATA the page sums its "now" numbers
// from (roas.by_app, placements, the catalog). Made-up apps, ids and numbers only — closed forms, so a test can do the hand
// math:
//   * the calendar: day0 2025-10-01 … t 2026-03-28 (the alarm's data day), today 2026-03-30;
//   * spend is billed in ₹ (one rate 0.012 USD per ₹ = roas.fx.INR; the dated rate 0.0122 / 0.0118 on alternate days);
//   * Alpha: ₹50,000 a day; 2,500 installs a day, 1,600 from 2026-03-10 (CPI ₹20 → ₹31.25); D0 value 40 % of spend, 30 % from
//     2026-03-10; eCPM $6 → $5 from 2026-03-10; ROAS_G ALERT open (c 2026-03-10, B 0.40), CPI WATCH open (B ₹20), ECPM WATCH open
//     (B $6), an old ROAS_G alarm closed (Dec 2025), a country and a campaign line;
//   * Beta: ₹20,000 a day, CPI ₹10 → ₹13 from 2026-03-15 (CPI WATCH open, B ₹10); Gamma: steady (OK); Delta: first spend
//     2026-03-20 (New: no normal); Epsilon: spend stops after 2026-03-24 (Paused); Hidden: hidden in Settings; Zeta: a hostile
//     name (OK).
// usage: const {build} = require('./cpx_fixture.js'); const {DATA, FILES, IDS, KEYS} = build();
'use strict';
const DAY0 = '2025-10-01', T = '2026-03-28', TODAY = '2026-03-30', C = '2026-03-10';
const DAY = 864e5, t0 = s => Date.parse(s + 'T00:00:00Z'), iso = t => new Date(t).toISOString().slice(0, 10);
const addD = (s, k) => iso(t0(s) + k * DAY), nD = (a, b) => Math.round((t0(b) - t0(a)) / DAY) + 1;
const FX1 = 0.012;                                             // USD per ₹ (the one rate)
const fxd = x => (nD(DAY0, x) % 2 ? 0.0122 : 0.0118);          // the day's own rate: day0 0.0122, the next 0.0118, …
const r2 = v => Math.round(v * 100) / 100, r6 = v => Math.round(v * 1e6) / 1e6;
const IDS = { a: 'ca-app-pub-0000000000000000~21', b: 'ca-app-pub-0000000000000000~22', c: 'ca-app-pub-0000000000000000~23',
  d: 'ca-app-pub-0000000000000000~24', e: 'ca-app-pub-0000000000000000~25', h: 'ca-app-pub-0000000000000000~26', z: 'ca-app-pub-0000000000000000~27' };
const KEYS = { a: 'c0000000000a', b: 'c0000000000b', c: 'c0000000000c', d: 'c0000000000d', e: 'c0000000000e', h: 'c00000000001', z: 'c00000000002' };
const NAMES = { a: 'Alpha App', b: 'Beta App', c: 'Gamma App', d: 'Delta App', e: 'Epsilon App', h: 'Hidden App', z: '<img src=x onerror=alert(1)>Zeta' };
// each app's day model (x = ISO day): ₹ spend, installs, D0 value share, AdMob rev $ and impressions, DAU, first session share
const M = {
  a: x => ({ sp: 50000, inst: x >= C ? 1600 : 2500, d0: x >= C ? 0.30 : (x >= '2025-12-01' && x <= '2025-12-15' ? 0.33 : 0.40),
    imp: 50000, ecpm: x >= C ? 5 : 6, dau: 20000 }),
  b: x => ({ sp: 20000, inst: x >= '2026-03-15' ? 20000 / 13 : 2000, d0: 0.35, imp: 20000, ecpm: 3, dau: 8000 }),
  c: x => ({ sp: 10000, inst: 500, d0: 0.25, imp: 10000, ecpm: 3, dau: 5000 }),
  d: x => ({ sp: x >= '2026-03-20' ? 8000 : 0, inst: x >= '2026-03-20' ? 400 : 0, d0: 0.20, imp: x >= '2026-03-20' ? 4000 : 0, ecpm: 2, dau: 1000 }),
  e: x => ({ sp: x <= '2026-03-24' ? 6000 : 0, inst: x <= '2026-03-24' ? 400 : 0, d0: 0.30, imp: 3000, ecpm: 2.5, dau: 900 }),
  h: x => ({ sp: 5000, inst: 250, d0: 0.30, imp: 2000, ecpm: 2, dau: 500 }),
  z: x => ({ sp: 4000, inst: 200, d0: 0.30, imp: 2000, ecpm: 2, dau: 500 }),
};
const days = (a, b) => { const o = []; for (let x = a; x <= b; x = addD(x, 1)) o.push(x); return o; };
function build() {
  const ALLD = days(DAY0, TODAY), TD = days(DAY0, T);
  const by_app = {}, placements = [], catalog = [];
  for (const k of Object.keys(M)) {
    const nm = NAMES[k], daily = {}, dated = {}, inst = {}, cv1 = {}, rows = [];
    for (const x of ALLD) { const m = M[k](x);
      if (m.sp > 0) { daily[x] = Math.round(m.sp * FX1 * 1e6); dated[x] = Math.round(m.sp * fxd(x) * 1e6); inst[x] = r2(m.inst); cv1[x] = r2(m.sp * m.d0 * FX1); }   // (plain USD, as roas.by_app ships it)
      if (m.imp > 0) rows.push([x, Math.round(m.imp * m.ecpm / 1000 * 1e6), m.imp, m.imp * 2, m.imp * 2, 10]); }
    by_app[nm] = { store_id: 'com.synth.' + k, daily, daily_dated: dated, installs_daily: inst, convval_day1_daily: cv1, campaigns: [] };
    placements.push({ id: 'ca-app-pub-0000000000000000/' + (1000 + Object.keys(M).indexOf(k)), name: nm + ' · banner', app: nm, account: 'pub-0000000000000000', format: 'banner', daily: rows });
    catalog.push({ account_id: 'pub-0000000000000000', app_id: IDS[k], app_name: nm, rev: 1, selected: k !== 'h', account_decided: true });
  }
  // ---- episodes (Episode dicts; the pointer / cpi.json.gz carry their tuples) ----
  const ep = (o) => Object.assign({ kind: 'app', id: '', app: '', fam: 'CPI', opener: 'SUDDEN', tier: 'WATCH', c: C, opened: '2026-03-13', seen: '2026-03-15',
    closed: null, why: null, base: 1, base_src: 'before', thr_open: 0.25, max_worse: 0.3, esc: [], confirm: null, ctx: {}, money: null }, o);
  const EP = {
    a: [ep({ id: IDS.a, app: IDS.a, fam: 'ROAS_G', tier: 'ALERT', c: C, opened: '2026-03-14', seen: '2026-03-16', base: 0.4, max_worse: 0.25, confirm: 'confirmed',
          money: { since_c_usd: 2852.5, since_c_inr: 237500, cost_usd: 11400, cost_inr: 950000 } }),
        ep({ id: IDS.a, app: IDS.a, fam: 'CPI', tier: 'WATCH', c: C, opened: '2026-03-13', seen: '2026-03-15', base: 20, max_worse: 0.5625 }),
        ep({ id: IDS.a, app: IDS.a, fam: 'ECPM', tier: 'WATCH', c: C, opened: '2026-03-13', seen: '2026-03-15', base: 6, max_worse: 0.1667 }),
        ep({ id: IDS.a, app: IDS.a, fam: 'ROAS_G', tier: 'ALERT', c: '2025-12-01', opened: '2025-12-04', seen: '2025-12-06', closed: '2025-12-20', why: 'recovered', base: 0.4, max_worse: 0.175,
          money: { since_c_usd: 12345.67, since_c_inr: 1028806, cost_usd: 1, cost_inr: 1 } }),
        ep({ id: IDS.a, app: IDS.a, fam: 'ROAS_C0', tier: 'LINE', opener: 'DRIFT', c: '2026-03-11', opened: '2026-03-20', seen: '2026-03-22', base: 0.5, max_worse: 0.2 })],
    b: [ep({ id: IDS.b, app: IDS.b, fam: 'CPI', tier: 'WATCH', c: '2026-03-15', opened: '2026-03-18', seen: '2026-03-20', base: 10, max_worse: 0.3 })],
    c: [], d: [], e: [], h: [], z: [],
  };
  const tup = e => [e.fam, e.opener, e.tier, e.c, e.opened, e.closed, e.why, e.base];
  // money lost on the default window [t − 13, t] (the build's own numbers: Σ cost − D0 value ÷ B, ₹ as billed / $ dated)
  const def0 = addD(T, -13);
  const lostOf = k => { const G = EP[k].filter(e => e.fam === 'ROAS_G' && e.c <= T && (!e.closed || e.closed >= def0)); if (!G.length) return null;
    let inr = 0, usd = 0, si = 0, su = 0; for (const e of G) for (const x of days(e.c, e.closed && e.closed < T ? e.closed : T)) { const m = M[k](x); const l = m.sp - m.sp * m.d0 / e.base;
      si += l; su += l * fxd(x); if (x >= def0) { inr += l; usd += l * fxd(x); } }
    return { inr: r2(inr), usd: r2(usd), from: G.map(e => e.c).sort()[0], sc: { inr: r2(si), usd: r2(su) }, fam: 'ROAS_G' }; };   // sc: the same from c (the "since c" line)
  // ---- the per-app files ----
  const FILES = {}, apps = {}, allApps = {};
  const hOf = k => { const cpi = [], ecpm = [], roas = [];
    for (const x of TD) { const m = M[k](x), live = k !== 'd' && x >= addD(DAY0, 28);
      const mb = k === 'a' ? M.a('2026-01-01') : k === 'b' ? M.b('2026-01-01') : m;      // the healthy level leaves the problem days out
      cpi.push(live && mb.inst > 0 ? Math.round(mb.sp / mb.inst * 100) : null); ecpm.push(live && mb.imp > 0 ? Math.round(mb.ecpm * 10000) : null); roas.push(live ? Math.round(mb.d0 * 10000) : null); }
    return { CPI: cpi, ECPM: ecpm, ROAS_G: roas }; };
  for (const k of Object.keys(M)) {
    const id = IDS[k], key = KEYS[k], file = 'cpi_' + key + '.json.gz';
    const first = TD.find(x => M[k](x).sp > 0), f0 = addD(first, -28) < DAY0 ? DAY0 : addD(first, -28), FD = days(f0, T), N = FD.length;
    const d = {}; for (const s of ['sp_inr', 'sp_usd', 'inst', 'd0_inr', 'rev', 'imp', 'dau', 'fs_rev', 'fs_imp', 'fs_u', 'rt_rev', 'rt_imp', 'rt_u', 'c_n', 'c_sp', 'c_r0', 'c_r1', 'c_r7']) d[s] = [];
    FD.forEach((x, i) => { const m = M[k](x), age = nD(x, T) - 1, fsh = k === 'a' && x >= C ? 0.5 : 0.3;
      d.sp_inr.push(r2(m.sp)); d.sp_usd.push(r2(m.sp * fxd(x))); d.inst.push(r2(m.inst)); d.d0_inr.push(r2(m.sp * m.d0));
      d.rev.push(r2(m.imp * m.ecpm / 1000)); d.imp.push(m.imp); d.dau.push(age < 2 ? null : m.dau);
      // GA4 first session / returning: the first session's eCPM is 0.8 × the returning one's (the mix moves Alpha's eCPM)
      const er = m.ecpm / (fsh * 0.8 + (1 - fsh)), ef = er * 0.8;
      d.fs_imp.push(Math.round(m.imp * fsh)); d.rt_imp.push(Math.round(m.imp * (1 - fsh))); d.fs_rev.push(r2(m.imp * fsh * ef / 1000)); d.rt_rev.push(r2(m.imp * (1 - fsh) * er / 1000));
      d.fs_u.push(Math.round(m.inst * 1.1)); d.rt_u.push(m.dau);
      const sp = r2(m.sp * fxd(x)), on = m.sp > 0;
      d.c_n.push(on ? Math.round(m.inst * 1.1) : 0); d.c_sp.push(on ? sp : 0);
      d.c_r0.push(age < 3 ? null : r2(sp * m.d0 * 0.9)); d.c_r1.push(age < 4 ? null : r2(sp * m.d0 * 1.2)); d.c_r7.push(age < 10 ? null : r2(sp * m.d0 * 1.8)); });
    const hh = hOf(k), off = nD(DAY0, f0) - 1;
    const nrm = { CPI: hh.CPI.slice(off).map(v => v == null ? null : v / 100), ECPM: hh.ECPM.slice(off).map(v => v == null ? null : v / 10000),
      ROAS_G: hh.ROAS_G.slice(off).map(v => v == null ? null : v / 10000), GAP: FD.map(() => null), IPU: FD.map(() => null), ROAS_C0: hh.ROAS_G.slice(off).map(v => v == null ? null : r6(v / 10000 * 0.9)) };
    // the open episodes keep their frozen baseline in the normal
    EP[k].forEach(e => { if (e.closed || !nrm[e.fam]) return; FD.forEach((x, i) => { if (x >= e.opened) nrm[e.fam][i] = e.base; }); });
    const camps = k === 'a' ? [
      { id: '9000000001', name: 'Alpha · Search · tROAS', status: 'ENABLED', bid: 'TARGET_ROAS', troas: [['2026-02-20', 0.45], ['2026-03-12', 0.55]], from: f0,
        d: { sp_inr: d.sp_inr.map(v => r2(v * 0.7)), sp_usd: d.sp_usd.map(v => r2(v * 0.7)), inst: d.inst.map(v => r2(v * 0.7)), d0_inr: d.d0_inr.map(v => r2(v * 0.7)) },
        ep: [tup(ep({ kind: 'camp', id: '9000000001', app: id, fam: 'ROAS_G', tier: 'LINE', c: C, opened: '2026-03-15', base: 0.4 }))] },
      { id: '9000000002', name: 'Alpha · Display', status: 'ENABLED', bid: 'TARGET_CPA', troas: [], from: f0,
        d: { sp_inr: d.sp_inr.map(v => r2(v * 0.3)), sp_usd: d.sp_usd.map(v => r2(v * 0.3)), inst: d.inst.map(v => r2(v * 0.3)), d0_inr: d.d0_inr.map(v => r2(v * 0.3)) }, ep: [] },
      { id: '9000000003', name: 'Alpha · Old', status: 'PAUSED', bid: 'TARGET_ROAS', troas: [], from: f0,
        d: { sp_inr: FD.map(() => 0), sp_usd: FD.map(() => 0), inst: FD.map(() => 0), d0_inr: FD.map(() => 0) }, ep: [] }] : [];
    const share = { IN: 0.6, US: 0.25, BR: 0.1 };
    const ctys = Object.keys(share).map(cc => { const q = share[cc], pr = cc === 'US' ? 1.6 : cc === 'BR' ? 0.6 : 0.9;
      return { cc, from: f0, d: { sp_inr: d.sp_inr.map(v => r2(v * q)), sp_usd: d.sp_usd.map(v => r2(v * q)), dl: d.inst.map(v => r2(v * q * (cc === 'BR' && k === 'a' ? 0.8 : 1))),
        rev: d.rev.map(v => r2(v * q * pr)), imp: d.imp.map(v => Math.round(v * q)),
        // the country's AdMob-matched D0 (its share of the app's c_r0: US 1.2 × its spend share, IN 0.9 ×); BR: none in this build
        ...(cc === 'BR' ? {} : { r0: d.c_r0.map(v => v == null ? null : r2(v * q * (cc === 'US' ? 1.2 : 0.9))) }) },
      // its normal per day (CPI ₹, eCPM $, D0 ROAS AdMob-matched): the build's (its own B while open, else H)
      nrm: Object.assign({ CPI: FD.map((x, i) => i < 28 ? null : 20), ECPM: FD.map((x, i) => i < 28 ? null : r6(6 * pr)) }, cc === 'BR' ? {} : { ROAS: FD.map((x, i) => i < 28 ? null : (cc === 'US' ? 0.432 : 0.324)) }),
        ep: cc === 'BR' && k === 'a' ? [tup(ep({ kind: 'country', id: id + '|BR', app: id, fam: 'CPI', tier: 'LINE', c: '2026-03-12', opened: '2026-03-16', base: 20 }))] : [] }; });
    const src = [{ name: 'AdMob Network', from: f0, d: { rev: d.rev.map(v => r2(v * 0.7)), imp: d.imp.map(v => Math.round(v * 0.6)) } },
      { name: 'Synth Ads', from: f0, d: { rev: d.rev.map(v => r2(v * 0.3)), imp: d.imp.map(v => Math.round(v * 0.4)) } }];
    FILES[file] = { v: 1, app_id: id, name: NAMES[k], key, t: T, day0: f0, d, nrm, camps, ctys, src, ep: EP[k],
      notes: { clock: 'IST', ga4_sampled: [], admob_cty_from: '2025-11-01', troas_from: '2026-02-15' } };
    allApps[id] = { h: hh, ep: EP[k].map(tup) };
    const open = EP[k].filter(e => !e.closed).map(e => [e.fam, e.opener, e.tier, e.c, e.opened, e.base]);
    // the build's rule: an episode still open at T → alarm (ALERT) / watch (WATCH); else an ALERT that closed inside the window → fixed
    const w = EP[k].filter(e => (e.tier === 'ALERT' || e.tier === 'WATCH') && e.c <= T && (!e.closed || e.closed >= def0));
    const live = w.filter(e => !e.closed || e.closed > T);
    const st = live.some(e => e.tier === 'ALERT') ? 'alarm' : live.length ? 'watch' : w.some(e => e.tier === 'ALERT') ? 'fixed'
      : k === 'e' ? 'paused' : k === 'd' ? 'new' : 'ok';
    const top = (st === 'fixed' ? w.filter(e => e.tier === 'ALERT') : live.filter(e => e.tier === (st === 'alarm' ? 'ALERT' : 'WATCH'))).map(e => e.c).sort()[0] || null;
    const ix = nD(DAY0, addD(def0, -1)) - 1, nv = (f, s) => { const o = EP[k].find(e => e.fam === f && !e.closed); if (o) return o.base; const v = hh[f][ix]; return v == null ? null : v / s; };
    apps[id] = { name: NAMES[k], key, file, v: 'v' + key.slice(-6), st, since: top, open,
      nrm: { CPI: nv('CPI', 100), ECPM: nv('ECPM', 10000), ROAS_G: nv('ROAS_G', 10000) }, lost: lostOf(k) };
  }
  FILES['cpi.json.gz'] = { v: 1, t: T, day0: DAY0, apps: allApps };
  const counts = { alarm: 0, watch: 0, fixed: 0, ok: 0, new: 0, paused: 0 }; Object.values(apps).forEach(a => { counts[a.st]++; });
  const cpi = { v: 1, t: T, at: '2026-03-30T05:22:00Z', day0: DAY0, till: { spend: T, d0: T, admob: addD(TODAY, -1), ga4: addD(T, -1) },
    file: 'cpi.json.gz', fv: 'f00000000001', apps, counts, unlinked: { inr: 12345.6, usd: 148.15, n: 3 }, alerts: [], closed: [] };
  const DATA = { currency: 'USD', usd_inr: 1 / FX1, today_date: TODAY, latest_complete: addD(TODAY, -1), generated_at: '2026-03-30T05:22:00Z',
    roas: { configured: true, by_app, currency_src: 'INR', fx: { INR: FX1 }, spend_fx: 'dated', d0: { fixed_till: T } },
    placements, apps_catalog: catalog, app_icons: {}, cpi };
  return { DATA, FILES, IDS, KEYS, NAMES, T, TODAY, DAY0, C, FX1, fxd, M };
}
// ── 🤖 the level agent's ship fields (AGENT SPEC §6.3–§6.6, exact shapes) laid onto a build() output: the scoreboard
// (DATA.cpi.agent), the row tags (apps[id].ag), every app file's decision rows (ag.rows — Alpha carries one per status word
// but trial, which is Beta's), the proposals' answers (lp[i].ag) and the agent's marks on level rows (lv rows' st / ag).
// Made-up numbers and words in the shapes of the rule's sentences, dates inside the fixture's calendar:
//   * Alpha: kept D0 ROAS proposal (spend ×2.6, its first ask a wait) · waiting install-day D7 proposal (narrow: countries) ·
//     an install-day D0 proposal the owner accepted (overridden) · the engine's CPI settle of 24 Mar blocked (spend ×3.5;
//     extra paid ₹90,000 since) · its GAP settle on hold (app only) · an eCPM accept applied 21 Mar (live) · a Spend family
//     the owner holds · an older eCPM accept reverted 25 Feb (r3) · a closed install-day D1 keep (came back) · a CPI settle of
//     10 Jan that passed (the closed / overridden / held rows carry a stale next check, as an older build shipped them: the
//     page shows none; an end carries the alarm's own close day, the overridden one an older build's end without it);
//   * Beta: a CPI accept in trial; Gamma: a CPI proposal without the agent's answer (the 🆕 line, "not a loss"); Delta: a
//     waiting eCPM row and no level history; Zeta: hostile text in its row and tag, a level block with no family.
//   usage: const fx = build(); agent(fx);
function agent(fx) {
  const { DATA, FILES } = fx, P = DATA.cpi, F = k => FILES['cpi_' + KEYS[k] + '.json.gz'];
  const sums = (k, f, a, b) => { const s = {}, add = (q, v) => { s[q] = (s[q] || 0) + v; };   // the per-day arrays' own rounding
    for (const x of days(a, b)) { const m = M[k](x);
      if (f === 'CPI') { add('sp_inr', r2(m.sp)); add('sp_usd', r2(m.sp * fxd(x))); add('inst', r2(m.inst)); }
      if (f === 'ECPM') { add('rev', r2(m.imp * m.ecpm / 1000)); add('imp', m.imp); }
      if (f === 'ROAS_G') { add('d0_inr', r2(m.sp * m.d0)); add('sp_inr', r2(m.sp)); } }
    return s; };
  P.agent = { v: 1, mode: 'on', rule: 'C1', th: '0123456789ab', since: '2026-01-20', ms: 12,
    trial: { st: 'live', since: '2026-01-20', day: 67, need: 28, why: 'start', exit: '2026-02-17' },
    n: { accepted: 2, right: 0, wrong: 1, unclear: 0, pending: 1, kept: 2, waiting: 2, trial: 1, reverted: 1, overridden: 1, held: 1 },
    settle: { checked: 3, passed: 1, blocked: 1, hold: 1, later: 0 }, parity: { checked: 40, bad: 0 }, vintage: { done: 6, flips: 0, accept_flips: 0 }, bt: null };
  P.apps[IDS.a].ag = { st: 'accepted', fam: 'ECPM', short: 'eCPM market move', day: '2026-03-21', more: 4 };
  P.apps[IDS.b].ag = { st: 'trial', fam: 'CPI', short: 'CPI market move', day: null, more: 0 };
  P.apps[IDS.d].ag = { st: 'waiting', fam: 'ECPM', short: 'still moving', day: '2026-04-03', more: 1 };
  P.apps[IDS.z].ag = { st: 'kept', fam: 'ECPM', short: '<img src=x onerror=alert(3)>', day: null, more: 0 };
  P.apps[IDS.c].lp = 1;                                                     // a proposal without the agent's answer: the 🆕 tag stays
  const row = o => Object.assign({ id: '', fam: 'CPI', why: 'money', st: 'kept', dec: 'keep', branch: 'spend_scaled', part: null, cause: '', short: '',
    first: '2026-03-20', last: '2026-03-27', next: '2026-04-03', n: 1, ep: { opened: '2026-03-14', c: C }, applied: null, trial: false, level: null,
    h: [], k: {}, k0: {}, chk: null, vd: 'pending', ve: 'pending', rev: null, ovr: null, held: false, end: null, xp: null }, o);
  const cS = 'CPI part 140% of the move: seen with spend ×2.6 since the old level (your lever)', sS = 'seen with spend ×3.5 since the old level (your lever)';
  const cW = 'CPI part 120% of the move: narrow: countries moving the same way = 61% of spend (opposite 9%)';
  const cE = "other apps' eCPM moved the same way (4 other apps: median −18% vs own −17%, 75% moved the same way); ads per user +2%";
  const cG = 'eCPM part 85% of the move: eCPM moved on this app only — the cause is not in the data (ad sources / mediation / units)';
  const cC = "other apps' CPI moved the same way (3 other apps: median +6% vs own +5%, 67% moved the same way)";
  const cT = "other apps' CPI moved the same way (3 other apps: median +29% vs own +30%, 100% moved the same way)";
  const kS = { old: 0.4, new: 0.3, mv: -0.25, bands: 3.2, l14p14: -0.01, st56: 0.04, spx: 2.6, mkt_n: 4, mkt_med: -0.03, own: -0.25, cost: 1.4, val: -0.4 };
  const kW = { old: 0.72, new: 0.54, mv: -0.25, bands: 2.4, same: 0.61, opp: 0.09, nl: 0.05, cost: 1.2, val: -0.2, pf: 'A7' };
  const kB = { old: 20, new: 31.25, mv: 0.5625, bands: 4.5, l14p14: 0.01, st56: 0.03, spx: 3.5, mkt_n: 3, mkt_med: 0.02, turn: 0.12 };
  const kE = { old: 6, new: 5, mv: -0.1667, bands: 2.6, st56: 0.05, l14p14: 0, mkt_n: 4, mkt_med: -0.18, own: -0.17, ipu: 0.02 };
  F('a').ag = { rows: [
    row({ id: 'D-00000000p1', fam: 'ROAS_G', cause: cS, short: 'spend ×2.6 (your lever)', n: 2, ep: { opened: '2026-03-14', c: C },
      h: [['2026-03-27', '2026-03-27', 1, 'keep', 'spend_scaled', null, 'spend ×2.6 (your lever)'], ['2026-03-20', '2026-03-20', 1, 'wait', 'not_steady', null, 'not steady']],
      k: kS, k0: { old: 0.4, new: 0.31, mv: -0.225, bands: 2.9, l14p14: -0.06, st56: 0.13, spx: 1.9 } }),
    row({ id: 'D-00000000w1', fam: 'ROAS_C7', st: 'waiting', dec: 'wait', branch: 'narrow', part: 'cpi', cause: cW, short: 'narrow: countries 61%',
      first: '2026-03-13', last: '2026-03-26', n: 2, ep: { opened: '2026-03-12', c: '2026-03-11' },
      h: [['2026-03-13', '2026-03-26', 2, 'wait', 'narrow', 'cpi', 'narrow: countries 61%']], k: kW, k0: kW }),
    row({ id: 'D-00000000o1', fam: 'ROAS_C0', st: 'overridden', branch: 'campaign_mix', part: 'cpi', short: 'campaign mix 62%',
      cause: 'CPI part 130% of the move: seen with 62% of spend in campaigns new since / gone after the old level', first: '2026-03-20', last: '2026-03-24', next: '2026-03-27',
      n: 2, ep: { opened: '2026-03-20', c: '2026-03-11' }, ovr: { at: '2026-03-25T09:30:00Z', act: 'accept' }, end: { t: '2026-03-25', why: 'owner' },
      h: [['2026-03-20', '2026-03-24', 2, 'keep', 'campaign_mix', 'cpi', 'campaign mix 62%']], k: { old: 0.5, new: 0.4, mv: -0.2, bands: 2.2, turn: 0.62 } }),
    row({ id: 'D-00000000s1', fam: 'CPI', why: 'settle', st: 'blocked', cause: sS, short: 'spend ×3.5 (your lever)', first: '2026-03-24', last: '2026-03-24',
      ep: { opened: '2026-03-13', c: C }, level: 'L-00000000b1', h: [['2026-03-24', '2026-03-24', 1, 'keep', 'spend_scaled', null, 'spend ×3.5 (your lever)']],
      k: kB, k0: kB, xp: { inr: 90000, usd: 1080, from: '2026-03-24' } }),
    row({ id: 'D-00000000s2', fam: 'GAP', why: 'settle', st: 'hold', dec: 'wait', branch: 'app_only', part: 'ecpm', cause: cG, short: 'app only',
      first: '2026-03-06', last: '2026-03-23', n: 3, ep: { opened: '2025-12-28', c: '2025-12-20' }, level: 'L-00000000g1',
      h: [['2026-03-06', '2026-03-23', 3, 'wait', 'app_only', 'ecpm', 'app only']], k: { old: 4.2, new: 5.5, mv: 0.31, bands: 3, cpi: 0.15, ecpm: 0.85, ipu: -0.02 } }),
    row({ id: 'D-00000000p2', fam: 'ECPM', why: 'open', st: 'accepted', dec: 'accept', branch: 'ecpm_market', cause: cE, short: 'eCPM market move',
      first: '2026-03-14', last: '2026-03-21', next: null, n: 2, ep: { opened: '2025-11-12', c: '2025-11-10' },
      applied: { day: '2026-03-21', days: ['2026-03-10', '2026-03-21'] }, level: 'L-00000000e2', end: { t: '2026-03-21', day: '2026-03-21', why: 'agent' },
      chk: { p: '2026-03-21', old: 6, new: 5, v: { 28: null, 56: null, 84: null }, final: false },
      h: [['2026-03-21', '2026-03-21', 1, 'accept', 'ecpm_market', null, 'eCPM market move'], ['2026-03-14', '2026-03-14', 1, 'wait', 'engine_steady', null, 'not steady']],
      k: kE, k0: { old: 6, new: 5.1, mv: -0.15, bands: 2.3, st56: 0.12, mkt_n: 4, mkt_med: -0.16, own: -0.15 } }),
    row({ id: 'D-00000000h1', fam: 'SPEND', why: 'open', st: 'held', branch: 'spend', short: 'budget (your lever)', first: '2026-03-06', last: '2026-03-06', next: '2026-03-13',
      cause: 'budget / bid limit (your lever): spend −45%, campaign C1 carries 80% of the change', ep: { opened: '2025-11-01', c: '2025-10-29' }, held: true,
      h: [['2026-03-06', '2026-03-06', 1, 'keep', 'spend', null, 'budget (your lever)']], k: { old: 600, new: 330, mv: -0.45, bands: 5 } }),
    row({ id: 'D-00000000r1', fam: 'ECPM', why: 'open', st: 'reverted', dec: 'accept', branch: 'ecpm_market', short: 'eCPM market move', first: '2026-02-13', last: '2026-02-20', next: null,
      cause: "other apps' eCPM moved the same way (5 other apps: median −12% vs own −14%, 80% moved the same way)", n: 2, ep: { opened: '2025-10-15', c: '2025-10-12' },
      applied: { day: '2026-02-20', days: ['2026-01-24', '2026-02-20'] }, level: 'L-00000000e1', rev: { by: 'r3', day: '2026-02-25', old: 6, v: 5.9 }, end: { t: '2026-02-25', day: '2026-02-25', why: 'recovered' },
      chk: { p: '2026-02-20', old: 6, new: 5.2, v: { 28: 5.9, 56: null, 84: null }, final: false }, vd: 'wrong', ve: 'wrong',
      h: [['2026-02-20', '2026-02-20', 1, 'accept', 'ecpm_market', null, 'eCPM market move'], ['2026-02-13', '2026-02-13', 1, 'wait', 'not_steady', null, 'not steady']],
      k: { old: 6, new: 5.2, mv: -0.133, bands: 2.1, st56: 0.06, mkt_n: 5, mkt_med: -0.12, own: -0.14 } }),
    row({ id: 'D-00000000c1', fam: 'ROAS_C1', st: 'closed', short: 'spend ×0.6 (your lever)', cause: 'CPI part 110% of the move: seen with spend ×0.6 since the old level (your lever)',
      first: '2026-01-24', last: '2026-02-21', next: '2026-02-27', n: 5, ep: { opened: '2025-10-20', c: '2025-10-18' }, end: { t: '2026-03-27', day: '2026-02-28', why: 'recovered' },
      chk: { p: '2026-01-24', old: 0.6, new: 0.45, v: { 28: 0.5, 56: 0.58, 84: null }, final: false }, vd: 'pending', ve: 'came_back',
      h: [['2026-01-24', '2026-02-21', 5, 'keep', 'spend_scaled', 'cpi', 'spend ×0.6 (your lever)']], k: { old: 0.6, new: 0.45, mv: -0.25, bands: 3.5, spx: 0.6 } }),
    row({ id: 'D-00000000s3', fam: 'CPI', why: 'settle', st: 'passed', dec: 'accept', branch: 'cpi_market', cause: cC, short: 'CPI market move', first: '2026-01-10', last: '2026-01-10',
      next: null, ep: { opened: '2025-11-15', c: '2025-11-12' }, level: 'L-00000000b2', end: { t: '2026-01-20', day: '2026-01-10', why: 'settled' },
      chk: { p: '2026-01-10', old: 20, new: 21, v: { 28: 21.1, 56: 20.9, 84: null }, final: false },
      h: [['2026-01-10', '2026-01-10', 1, 'accept', 'cpi_market', null, 'CPI market move']], k: { old: 20, new: 21, mv: 0.05, bands: 2.3, st56: 0.04, mkt_n: 3, mkt_med: 0.06, own: 0.05 } }),
  ] };
  const lp = (o) => Object.assign({ sums: null, gap: null }, o);
  F('a').lp = [
    lp({ fam: 'ROAS_G', opened: '2026-03-14', day: '2026-03-20', why: 'money', v: 0.3, days: ['2026-03-10', T], sums: sums('a', 'ROAS_G', '2026-03-10', T), old: 0.4,
      gap: { inr: 123456, usd: 1500 }, ag: { id: 'D-00000000p1', st: 'kept', short: 'spend ×2.6 (your lever)', cause: cS, next: '2026-04-03' } }),
    lp({ fam: 'ROAS_C7', opened: '2026-03-12', day: '2026-03-13', why: 'money', v: 0.54, days: ['2026-02-19', '2026-03-18'], old: 0.72, gap: { inr: 40000, usd: 480 },
      ag: { id: 'D-00000000w1', st: 'waiting', short: 'narrow: countries 61%', cause: cW, next: '2026-04-03' } })];
  const lv = o => Object.assign({ id: '', from: '2025-12-01', to: null, v: 1, days: null, sums: null, src: 'auto', ep: null, act: null, st: 'earlier', seen: '2026-03-30T05:22:00Z', rs: null, gone: null, rejected: null }, o);
  const b1 = sums('a', 'CPI', '2026-03-10', '2026-03-23'), b0 = sums('a', 'CPI', '2026-02-24', '2026-03-09'), b3 = sums('a', 'CPI', '2025-11-01', '2025-11-14');
  const e2 = sums('a', 'ECPM', '2026-03-10', '2026-03-21'), e0 = sums('a', 'ECPM', '2025-11-01', '2025-11-14');
  F('a').lv = {
    CPI: [lv({ id: 'L-00000000b1', src: 'accepted', from: '2026-03-24', v: b1.sp_inr / b1.inst, days: ['2026-03-10', '2026-03-23'], sums: b1, st: 'blocked', ep: { opened: '2026-03-13', old: 20 },
            ag: { st: 'blocked', dec: 'D-00000000s1', short: 'spend ×3.5 (your lever)', cause: sS, next: '2026-04-03' } }),
          lv({ id: 'L-00000000b0', src: 'alarm', from: '2026-03-13', v: b0.sp_inr / b0.inst, days: ['2026-02-24', '2026-03-09'], sums: b0, st: 'now', ep: { opened: '2026-03-13', c: C, why: null, opener: 'SUDDEN' } }),
          lv({ id: 'L-00000000b2', src: 'accepted', from: '2026-01-10', to: '2026-03-12', v: 21, days: ['2025-12-13', '2026-01-09'], st: 'rest', ep: { opened: '2025-11-15', old: 20 },
            ag: { st: 'passed', dec: 'D-00000000s3', short: 'CPI market move', cause: cC, next: null } }),
          lv({ id: 'L-00000000b3', src: 'first', from: '2025-12-01', to: '2026-01-09', v: b3.sp_inr / b3.inst, days: ['2025-11-01', '2025-11-14'], sums: b3, st: 'earlier' })],
    ECPM: [lv({ id: 'L-00000000e2', src: 'accepted_agent', from: '2026-03-21', v: e2.rev / e2.imp * 1000, days: ['2026-03-10', '2026-03-21'], sums: e2, st: 'now', ep: { opened: '2025-11-12', old: 6 },
             act: 'D-00000000p2', ag: { st: 'agent', dec: 'D-00000000p2', short: 'eCPM market move', cause: cE, next: null } }),
           lv({ id: 'L-00000000e1', src: 'accepted_agent', from: '2026-02-20', to: '2026-02-25', v: 5.2, days: ['2026-01-24', '2026-02-20'], st: 'reverted', ep: { opened: '2025-10-15', old: 6 },
             act: 'D-00000000r1', ag: { st: 'reverted', dec: 'D-00000000r1', short: 'eCPM market move', cause: "other apps' eCPM moved the same way", next: null } }),
           lv({ id: 'L-00000000e0', src: 'first', from: '2025-12-01', to: '2026-02-19', v: e0.rev / e0.imp * 1000, days: ['2025-11-01', '2025-11-14'], sums: e0, st: 'earlier' })],
    GAP: [lv({ id: 'L-00000000g1', src: 'accepted', from: '2026-03-06', v: 5.5, days: ['2026-02-06', '2026-03-05'], st: 'hold', ep: { opened: '2025-12-28', old: 4.2 },
            ag: { st: 'hold', dec: 'D-00000000s2', short: 'app only', cause: cG, next: '2026-04-03' } }),
          lv({ id: 'L-00000000g0', src: 'first', from: '2025-12-01', v: 4.2, st: 'now' })] };
  F('b').ag = { rows: [row({ id: 'D-00000000t1', fam: 'CPI', why: 'open', st: 'trial', dec: 'accept', branch: 'cpi_market', cause: cT, short: 'CPI market move', trial: true,
    first: '2026-03-25', last: '2026-03-27', n: 2, ep: { opened: '2026-03-18', c: '2026-03-15' }, xp: { inr: 30000, usd: 360, from: '2026-03-25' },
    h: [['2026-03-25', '2026-03-27', 2, 'accept', 'cpi_market', null, 'CPI market move']], k: { old: 10, new: 13, mv: 0.3, bands: 2.8, st56: 0.03, mkt_n: 3, mkt_med: 0.29, own: 0.3 } })] };
  F('b').lp = [lp({ fam: 'CPI', opened: '2026-03-18', day: '2026-03-25', why: 'open', v: 13, days: ['2026-03-15', '2026-03-27'], old: 10, gap: { inr: 30000, usd: 360 },
    ag: { id: 'D-00000000t1', st: 'trial', short: 'CPI market move', cause: cT, next: '2026-04-03' } })];
  F('b').lv = { CPI: [lv({ id: 'L-00000000t0', src: 'first', from: '2025-12-01', v: 10, st: 'now' })] };
  F('c').lp = [lp({ fam: 'CPI', opened: '2026-03-01', day: '2026-03-24', why: 'open', v: 20, days: ['2026-02-25', '2026-03-24'], old: 16, gap: { inr: 60000, usd: 720 } })];
  F('c').lv = { CPI: [lv({ id: 'L-00000000c0', src: 'first', from: '2025-12-01', v: 16, st: 'now' })] };
  F('d').ag = { rows: [row({ id: 'D-00000000d1', fam: 'ECPM', why: 'open', st: 'waiting', dec: 'wait', branch: 'still_sliding', short: 'still moving', first: '2026-03-27', last: '2026-03-27',
    cause: "other apps' eCPM moved the same way (3 other apps: median −10% vs own −12%, 67% moved the same way); but coming back / still moving: last 14 days −6% vs the 14 before",
    ep: { opened: '2026-03-22', c: '2026-03-20' }, h: [['2026-03-27', '2026-03-27', 1, 'wait', 'still_sliding', null, 'still moving']], k: { old: 2.2, new: 2, mv: -0.12, l14p14: -0.06 } })] };
  F('z').ag = { rows: [row({ id: 'D-"><img src=x onerror=alert(6)>', fam: 'ECPM', why: 'open', short: '<img src=x onerror=alert(3)>', cause: '<script>alert(4)</script>',
    ep: { opened: '2026-03-20', c: '2026-03-18' }, h: [['2026-03-20', '2026-03-27', 2, 'keep', 'app_side', null, '<b>x</b>']], k: { old: 2, new: 1.5, mv: -0.25 } })] };
  F('z').lv = {};
  return fx;
}
module.exports = { build, agent, addD, nD, days };
