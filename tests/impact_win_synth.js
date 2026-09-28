// Made-up 📦 Before / after windows for the frontend harnesses (tests/uninstall_frontend.js, tests/active_frontend.js):
// the SPEC_WINDOWS §4 contract's shape — by_window {"14","30","60"} with SPARSE rows (no unit / change_unit / raw_status /
// streak, the window's own dates left out), W.verdict {…, n, state, mixed, told, late}, notes — and the §2.8 additions on
// the 7-day rows. Numbers are invented; the rules the page follows (Actual / Expected, "pakka", running windows, Mixed,
// ⏰ late, told) are checked on them whatever the committed fixture holds. Run inside the page's vm context (it calls the
// page's own uniAdd / uniImpBlocks).
function __mkW(b, N, o) {
  o = o || {}; const R = b.date, a0 = ((b.windows || {}).after || {}).from || uniAdd(R, 1), end = uniAdd(a0, N - 1), st = o.state || 'final';
  const set = st === 'running' ? (o.settled != null ? o.settled : Math.min(12, N)) : N, jo = uniAdd(end, 10), fo = N === 14 ? jo : uniAdd(end, 33);
  const W = { n: N, state: st, before: { from: uniAdd(R, -N), to: uniAdd(R, -1), days: N },
    after: { from: a0, to: end, days: N, settled: set, settled_till: set ? uniAdd(a0, set - 1) : null, judged_on: jo, final_on: fo },
    mixed: o.mixed || [], mixed_before: o.mixed_before || [], adoption_mean: 0.8, rows: {}, notes: [] };
  const RATE = ['new_d1', 'new_d7', 'new_d30', 'uninstall_d0'], NZ = { returning_dau: 0.245, sessions: 0.057, time: 0.097, arpdau: 0.185, new_d1: 2.48, new_d7: 1.54, new_d30: 1.37, uninstall_d0: 4.22 };
  const keys = ['returning_dau', 'new_d1', 'new_d7', 'sessions', 'time', 'arpdau', 'uninstall_d0'].concat(N >= 30 ? ['new_d30'] : []);
  for (const k of keys) {
    const r7 = (b.rows || {})[k] || {}, rate = RATE.includes(k), bv = k === 'new_d30' ? 0.048 : (r7.before != null ? r7.before : (rate ? 0.3 : 2));
    const r = { status: 'same', before: bv, basis: rate ? 'rate' : (k === 'returning_dau' ? 'expected' : 'plain'), n_before: N };
    if (st === 'running' || (k === 'new_d30' && st === 'judged')) { r.status = 'pending'; r.ready_on = k === 'new_d30' ? fo : jo;
      if (st === 'running' && !rate) { r.after_prov = r7.after != null ? r7.after : bv; r.prov = true; } W.rows[k] = r; continue; }
    if (k === 'returning_dau') { r.after = Math.round(bv * 0.98); r.expected = Math.round(bv * 1.01); r.change = +(r.after / r.expected - 1).toFixed(4); r.extra = { raw_change: +(r.after / bv - 1).toFixed(5), mode: 'cohort' }; }
    else if (rate) { r.after = +(bv + 0.004).toFixed(5); r.change = 0.4; if (k !== 'uninstall_d0') r.from_b = uniAdd(R, -N - (k === 'new_d1' ? 1 : (k === 'new_d7' ? 7 : 30))); }
    else if (k === 'arpdau') { r.after = +(bv * 0.9).toFixed(4); r.change = -0.1; r.extra = { currency: 'USD', imp_change: -0.12, imp_adj: -0.12, ecpm_change: 0.02, imp_before: 4.4, imp_after: 3.872 }; }
    else { r.after = +(bv * 0.97).toFixed(2); r.change = -0.03; }
    r.noise = NZ[k]; r.need = rate ? +(3 * NZ[k]).toFixed(2) : -(+Math.max(1 - Math.exp(-3 * NZ[k]), 0.05).toFixed(4)); r.z = rate ? 0.16 : -0.3; r.n_after = N;
    if (o.young && (k === 'returning_dau' || k === 'uninstall_d0')) { Object.assign(r, { status: 'low', z: null, noise: null, need: null, expected: null,
      reason: 'Update se pehle ka ~' + Math.ceil((5 * N + 31) / 7) + ' hafte ka data chahiye (' + N + '-din tulna ka aam utaar-chadhaav napne ke liye) — is update se pehle ~20 hafte ka tha' }); }
    if (o.worse && o.worse.includes(k)) Object.assign(r, { status: 'worse', raw_status: 'worse', z: -3.4 });
    W.rows[k] = r; }
  const worse = keys.filter(k => W.rows[k].status === 'worse'), mix = W.mixed.length;
  W.verdict = { level: st === 'running' ? null : (worse.length ? 'hold' : 'continue'), early: st === 'judged', final: st === 'final',
    why: st === 'running' ? 'x' : (worse.length ? 'Ads per user pakka kam' : 'Koi pakka nuksaan nahi') + (mix ? ' · mila-jula (beech me ' + mix + ' aur update)' : ''),
    worse, better: [], pending: keys.filter(k => W.rows[k].status === 'pending'), ready_on: st === 'final' ? null : (st === 'running' ? jo : fo),
    settled_days: set, min_days: 3, n: N, state: st, mixed: !!mix, told: o.told || [], late: o.late || null };
  if (o.young) W.notes.push('young'); if (mix) W.notes.push('mixed'); if (W.mixed_before.length) W.notes.push('mixed_before');
  if (st !== 'running') { W.notes.push('plain'); if (N >= 30) W.notes.push('trend_capped'); }
  return W; }
function __v2(b) {   // the §2.8 additions on a 7-day block (made up): basis / noise / need, sessions / time expected, ads per user
  for (const [k, r] of Object.entries(b.rows)) { const x = r.extra || (r.extra = {}), J = ['worse', 'better', 'same', 'unsure', 'market'].includes(r.status);
    r.basis = ['new_d1', 'new_d7', 'uninstall_d0'].includes(k) ? 'rate' : 'expected';
    if ((k === 'sessions' || k === 'time') && J && r.after != null) { if (x.adj_change == null) x.adj_change = r.change || 0; r.expected = +(r.after / (1 + x.adj_change)).toFixed(k === 'time' ? 0 : 2); }
    if (k === 'arpdau') { if (x.imp_adj == null) x.imp_adj = x.imp_change || 0; x.imp_before = 4.4; x.imp_after = +(4.4 * (1 + (x.imp_change || 0))).toFixed(3); x.imp_expected = +(x.imp_after / (1 + x.imp_adj)).toFixed(3); }
    r.noise = J ? (r.basis === 'rate' ? 1.46 : 0.064) : null; r.need = J ? (r.basis === 'rate' ? 4.38 : -0.175) : null; }
  return b; }
function __winApp(a0) {   // a copy of an app (its updates' blocks), each block given 14 / 30 / 60 (30: judged, the oldest block Mixed)
  const a = JSON.parse(JSON.stringify(a0)), B = uniImpBlocks(a), ref = x => ({ key: x.key, label: x.label || 'App update', date: x.date });
  B.forEach((b, i) => { __v2(b); const older = i === B.length - 1;
    b.by_window = { '14': __mkW(b, 14, { state: 'final' }), '30': __mkW(b, 30, { state: 'judged', mixed: older ? B.slice(0, -1).map(ref).reverse() : [], mixed_before: older ? [] : [ref(B[B.length - 1])] }),
      '60': __mkW(b, 60, { state: 'running', settled: 12 }) };
    b.default_window = 7; b.late = null; });
  a.impact.v = 2; return a; }
