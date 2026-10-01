"""FROZEN REFERENCE — the owner-approved "Active users Studio" demo generator's data step, verbatim (only its file reads
take a site dir; its HTML page, its stdout notes and the writing of its private cross-check file are left out).
tests/test_active_studio_build.py checks admob_iq.active_studio_build against it on synthetic sites: the Studio's file
must hold EXACTLY the numbers the approved demo was made from. Never edit this to make a parity test pass — a
difference is a bug in the builder. Synthetic data only (the tests build their own sites)."""
import gzip, json, os, math, datetime as dt
from collections import defaultdict


def _jload(site, name):
    p = os.path.join(site, name)
    if name.endswith('.gz'):
        with gzip.open(p, 'rt') as f:
            return json.load(f)
    with open(p) as f:
        return json.load(f)


SPAN = 180            # days per app: 60-day range + 60-day compare + its 28-day normal + 30 install lags
BAND_DAYS = 70        # engine normal band kept only for the newest days (trend sparks, drawer chart)
LG = [1, 2, 3, 4, 5, 7, 11, 14, 21, 27, 42, 57]   # window lengths (settled days) of the noise grid
NULL_DAYS = 91        # 13 weeks of earlier ends (engine NULL_WEEKS)
NULL_MIN = 21
SIGMA_FLOOR = 0.01
SPREAD = 1.2533
TRI_WEEKS = 10
TRI_COLS = [1, 3, 7, 14, 30]


def D(s):
    return dt.date.fromisoformat(s[:10])


def add(s, n):
    return (D(s) + dt.timedelta(days=n)).isoformat()


def diff(a, b):
    return (D(b) - D(a)).days


def num(v):
    return v is not None and isinstance(v, (int, float)) and not isinstance(v, bool) and not (isinstance(v, float) and math.isnan(v))


_ALPH = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'


def enc(arr):
    """compact integer arrays: delta from the previous non-null value, zigzag, 5-bit groups as text, '~' = null"""
    out, prev = [], 0
    for v in arr:
        if v is None:
            out.append('~')
            continue
        v = int(v)
        d = v - prev
        prev = v
        z = (-2 * d - 1) if d < 0 else (2 * d)
        while True:
            g = z & 31
            z >>= 5
            if z:
                out.append(_ALPH[32 + g])
            else:
                out.append(_ALPH[g])
                break
    return ''.join(out)


def dec(s):
    out, prev, z, sh = [], 0, 0, 0
    for ch in s:
        if ch == '~':
            out.append(None)
            continue
        k = _ALPH.index(ch)
        z |= (k & 31) << sh
        if k >= 32:
            sh += 5
            continue
        d = (-(z + 1) // 2) if (z & 1) else (z // 2)
        prev += d
        out.append(prev)
        z, sh = 0, 0
    return out


def med(v):
    v = sorted(v)
    n = len(v)
    return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2) if n else None


def spread(v):
    if len(v) < NULL_MIN:
        return None
    c = med(v)
    return max(SPREAD * sum(abs(x - c) for x in v) / len(v), SIGMA_FLOOR)


# ---------------------------------------------------------------------------------------------
# the lens (Python mirror of the page's lens(); used for the noise grid and the cross-check)
# ---------------------------------------------------------------------------------------------
def shape_of(ref, K):
    """the app's per-day return curve ρ_k (k = 1..K) from tri.ref; gaps filled log-linearly; normalised to Σ = 1"""
    pts = [(k, ref[k]) for k in range(1, len(ref)) if k <= K and num(ref[k]) and ref[k] > 0]
    if not pts:
        return None
    out = []
    for k in range(1, K + 1):
        lo = max([p for p in pts if p[0] <= k], default=None, key=lambda p: p[0])
        hi = min([p for p in pts if p[0] >= k], default=None, key=lambda p: p[0])
        if lo and hi and lo[0] != hi[0]:
            t = (k - lo[0]) / (hi[0] - lo[0])
            out.append(math.exp(math.log(lo[1]) * (1 - t) + math.log(hi[1]) * t))
        elif lo:
            out.append(lo[1])
        else:
            out.append(hi[1])
    s = sum(out)
    return [x / s for x in out]


def lens(X, i0, i1, b0, b1):
    """X: per-app arrays (global index), first, wd0 (weekday of index 0), sh, K. → dict or None"""
    rt, y, nw = X['rt'], X['y'], X['nw']
    if b0 < X['first'] or b0 < 0:
        return None
    B = [i for i in range(b0, b1 + 1) if rt[i] is not None and y[i] is not None]
    if len(B) < NULL_MIN:
        return None
    W = [i for i in range(max(i0, X['first']), i1 + 1) if rt[i] is not None and y[i] is not None]
    if not W:
        return None
    base = sum(rt[i] for i in B) / len(B)
    ws, wc = [0.0] * 7, [0] * 7
    for i in B:
        w = (X['wd0'] + i) % 7
        ws[w] += rt[i]
        wc[w] += 1
    far = 0.0
    for i in W:
        w = (X['wd0'] + i) % 7
        far += rt[i] - (ws[w] / wc[w] if wc[w] else base)
    far /= len(W)
    yb = sum(y[i] for i in B) / len(B)
    fi = None
    sh, K = X['sh'], X['K']
    if sh and K:
        def wn(days):
            s = 0.0
            for k in range(1, K + 1):
                t = 0.0
                for i in days:
                    c = i - k
                    if c < 0:
                        return None
                    t += nw[c] or 0
                s += sh[k - 1] * t / len(days)
            return s
        nb, na = wn(B), wn(W)
        if nb and na is not None and nb > 0:
            fi = yb * (na / nb - 1)
    return {'far': far, 'base': base, 'fi': fi, 'yb': yb, 'n': len(W), 'nb': len(B)}


def ratio(X, num_k, den_k, i0, i1):
    a = b = 0.0
    n = 0
    N, Dn = X[num_k], X[den_k]
    for i in range(max(0, i0), i1 + 1):
        if N[i] is None or not Dn[i]:
            continue
        a += N[i]
        b += Dn[i]
        n += 1
    return (a / b) if b > 0 and n else None


def reference(site):
    """The demo generator's data step on `site` → {meta, apps, alerts, noga} (exactly what it embedded)."""
    jload = lambda name: _jload(site, name)
    dash = jload('dashboard.json.gz')
    AC = dash['active']
    PF = jload('active_portfolio.json.gz')
    accn = jload('account_names.json')
    appn = jload('app_names.json')
    fx = float(dash.get('usd_inr') or 83)
    today = dash['today_date']
    gen = dash['generated_at']
    K_ = AC.get('consts') or {}
    act_late = int(K_.get('act_late_days', 3))
    lag = 2
    try:
        lag = int((jload('uninstall.json.gz').get('consts') or {}).get('lag_days', 2))
    except Exception:
        pass

    # ---- app names: "<store name> · <account>", never cut (same rule as Uninstall Studio) --------------------------
    cat = {c['app_id']: c for c in dash['apps_catalog'] if c.get('app_id')}
    launch_by = {r['app_id']: r.get('launch_day') for r in AC.get('apps') or [] if r.get('app_id')}
    names = {}
    for aid, c in cat.items():
        acc = str(c.get('account_id') or '')
        nm = str(c.get('app_name') or aid)
        store = str(appn.get(aid) or (nm.rsplit(' · ', 1)[0] if ' · ' in nm else nm)).replace('–', '-').replace('—', '-')
        acct = accn.get(acc) or ('A/c ' + (acc.split('-')[1][:4] if '-' in acc else acc[:4]))
        names[aid] = {'store': store, 'acct': acct, 'dname': nm}
    dup = defaultdict(int)
    for v in names.values():
        dup[v['store'] + '|' + v['acct']] += 1
    for aid, v in names.items():
        tag = ''
        if dup[v['store'] + '|' + v['acct']] > 1 and launch_by.get(aid):
            tag = ' (%s wala)' % launch_by[aid][:4]
        v['name'] = v['store'] + tag + ' · ' + v['acct']
        v['stag'] = v['store'] + tag
    by_dname = {v['dname']: aid for aid, v in names.items()}

    # ---- size: AdMob kamai/day (last 7 finished days) + Google Ads spend/day (smpApps rule) ------------------------
    yd = dash.get('latest_complete') or add(today, -1)
    w7 = {add(yd, -i) for i in range(7)}
    k7 = defaultdict(float)
    for p in dash.get('placements') or []:
        if p.get('country') and p['country'] != 'All':
            continue
        aid = by_dname.get(p.get('app'))
        if not aid:
            continue
        for r in p.get('daily') or []:
            if isinstance(r, list) and r and r[0] in w7 and num(r[1]):
                k7[aid] += r[1] / 1e6 / 7
    spend = defaultdict(float)
    for v in (dash.get('value') or {}).get('apps') or []:
        s = float(((v.get('cpi') or {}).get('spend4_src')) or 0) / 28
        if s <= 0:
            continue
        src = v.get('src_ccy') or (dash['value'].get('spend_ccy')) or 'INR'
        spend[v['app_id']] = s / fx if src == 'INR' else s
    paisa = {aid: k7[aid] + spend[aid] for aid in names}

    def size_of(aid):
        p = paisa.get(aid, 0)
        return 'badi' if p >= 300 else ('chhoti' if p < 30 else 'madhyam')

    rows = [r for r in AC.get('apps') or [] if r.get('status') != 'error' and r.get('file')]
    E = min(r['data_till'] for r in rows)                  # common end: the latest GA4 day every app has
    S = add(E, -(SPAN - 1))
    SET = min(r.get('settled_till') or E for r in rows)    # common settled day
    pf_by = {a['app_id']: a for a in PF.get('apps') or []}

    apps, X_by, xcheck = [], {}, {'E': E, 'S': S, 'settled': SET, 'apps': {}}
    for r in sorted(rows, key=lambda z: names.get(z['app_id'], {}).get('name', z['app'])):
        aid = r['app_id']
        nmo = names.get(aid) or {'name': r['app'], 'store': r['app'], 'acct': ''}
        af = jload(r['file'])
        Dy = af['daily']
        ast = Dy['start']
        pa = pf_by.get(aid)
        g0 = min(ast, pa['start']) if pa else ast
        H = diff(g0, E) + 1
        first = diff(g0, pa['start']) if pa else diff(g0, ast)

        def from_af(arr, start=ast):
            out = [None] * H
            for j, v in enumerate(arr or []):
                i = diff(g0, start) + j
                if 0 <= i < H and num(v):
                    out[i] = v
            return out

        def from_pf(key):
            if not pa:
                return [None] * H
            return from_af(pa.get(key), pa['start'])

        okc = from_af(Dy['coh'].get('ok'))
        X = {
            'a1': from_pf('a1'), 'nw': from_pf('new'), 'rt': from_pf('ret'), 'd1': from_pf('d1'), 'd7': from_pf('d7'),
            'rv': from_pf('rev'), 's': from_pf('s'), 't': from_pf('t'), 'u': from_pf('u'),
            'y': from_af(Dy.get('y')), 'imp': from_af(Dy.get('imp')),
            'd30': [v if okc[i] == 1 else None for i, v in enumerate(from_af(Dy['coh'].get('d30')))],
        }
        # the engine's tracking-check days never count as a returning-users day
        for b in (pa or {}).get('brk') or []:
            i = diff(g0, b)
            if 0 <= i < H:
                X['rt'][i] = None
        # nothing before the counted start (hidden test installs before launch)
        for k in X:
            for i in range(0, min(first, H)):
                if k != 'nw':
                    X[k][i] = None
        X['first'] = first
        X['wd0'] = D(g0).weekday()
        K = Dy.get('old_k') or 30
        tri = af.get('tri') or {}
        X['sh'] = shape_of(tri.get('ref') or [], K)
        X['K'] = K if X['sh'] else 0
        steep = [False] * H
        for f0, t0 in ((af.get('steep') or {}).get('ret_dau') or []):
            for i in range(max(0, diff(g0, f0)), min(H, diff(g0, t0) + 1)):
                steep[i] = True
        X['steep'] = steep
        X_by[aid] = X

        iS = diff(g0, SET)          # the settled day (index)
        iE = H - 1
        i0s = iE - (SPAN - 1)       # span start (index)

        # ---- noise grid: the lens' own spread at the 91 earlier ends, per window length (window ends on the settled day)
        nz = {'t': [], 'a': [], 'se': [], 'tm': [], 'rv': [], 'ad': []}
        for L in LG:
            f = iS - L + 1
            vt, va, vse, vtm, vrv, vad = [], [], [], [], [], []
            for j in range(f - NULL_DAYS, f):
                w0, b0, b1 = j - L + 1, j - L - 27, j - L
                if b0 < first or w0 < 0 or steep[j]:
                    continue
                Lx = lens(X, w0, j, b0, b1)
                if Lx and Lx['base'] > 0 and Lx['n'] >= min(L, 5):
                    rt_ = Lx['far'] / Lx['base']
                    if rt_ > -1:
                        vt.append(math.log1p(rt_))
                    if Lx['fi'] is not None and (Lx['far'] - Lx['fi']) / Lx['base'] > -1:
                        va.append(math.log1p((Lx['far'] - Lx['fi']) / Lx['base']))
                for key, nk, dk, lst in (('se', 's', 'u', vse), ('tm', 't', 'u', vtm), ('rv', 'rv', 'a1', vrv), ('ad', 'imp', 'a1', vad)):
                    a_ = ratio(X, nk, dk, w0, j)
                    b_ = ratio(X, nk, dk, b0, b1)
                    if a_ and b_ and a_ > 0 and b_ > 0:
                        lst.append(math.log(a_ / b_))
            for key, lst in (('t', vt), ('a', va), ('se', vse), ('tm', vtm), ('rv', vrv), ('ad', vad)):
                sg = spread(lst)
                nz[key].append(None if sg is None else int(round(sg * 1e4)))

        # ---- the span the page gets
        def sl(arr, f=None):
            out = []
            for i in range(i0s, iE + 1):
                v = arr[i] if 0 <= i < H else None
                out.append(None if v is None else (f(v, i) if f else int(round(v))))
            return out

        cols = {
            'a1': sl(X['a1']), 'nw': sl(X['nw']), 'rt': sl(X['rt']), 'y': sl(X['y']),
            'd1': sl(X['d1']), 'd7': sl(X['d7']), 'd30': sl(X['d30']),
            'rv': sl(X['rv'], lambda v, i: int(round(v * 1000))),
            'u': sl(X['u']),
            'su': sl(X['s'], lambda v, i: int(round(v / X['u'][i] * 1000)) if X['u'][i] else None),
            'tu': sl(X['t'], lambda v, i: int(round(v / X['u'][i])) if X['u'][i] else None),
            'im': sl(X['imp'], lambda v, i: int(round(v / X['a1'][i] * 1000)) if X['a1'][i] else None),
        }
        # nw for the 30 lag days before the span (the oldest compare window's installs part)
        pre = [None if (i < 0 or X['nw'][i] is None) else int(round(X['nw'][i])) for i in range(i0s - 31, i0s)]
        bands = af.get('bands', {}).get('ret_dau') or {}
        bo = (diff(g0, ast) - i0s)
        bnd = {}
        for k2 in ('lo', 'hi', 'med'):
            arr = bands.get(k2) or []
            o = []
            for jj in range(SPAN - BAND_DAYS, SPAN):
                i = jj - bo
                v = arr[i] if 0 <= i < len(arr) else None
                o.append(int(round(v)) if num(v) else None)
            bnd[k2] = enc(o)

        # updates (📦) inside the span with the engine's verdict level
        rel = []
        for u in (af.get('impact') or {}).get('updates') or []:
            if u.get('date') and S <= u['date'] <= E:
                v = u.get('verdict') or {}
                rel.append([u['date'], u.get('label') or 'App update', v.get('level'), bool(v.get('final'))])
        seen = {x[0] for x in rel}
        for x in af.get('releases') or []:
            if S <= x['date'] <= E and x['date'] not in seen and not any(0 <= diff(z[0], x['date']) <= 3 for z in rel):
                rel.append([x['date'], ('v' + x['version']) if x.get('version') else 'App update', None, False])
                seen.add(x['date'])
        rel.sort()

        # return grid: newest install weeks × day 1 / 3 / 7 / 14 / 30 (the engine's tri rows)
        tw = []
        for row in (tri.get('rows') or []):
            if row.get('pre') or row.get('nodata'):
                continue
            v = row.get('v') or []
            pv = row.get('prov') or []
            vals = [int(round(v[k] * 1000)) if k < len(v) and num(v[k]) else None for k in TRI_COLS]
            if all(x is None for x in vals):
                continue
            bits = int(''.join('1' if (k < len(pv) and pv[k]) else '0' for k in TRI_COLS), 2)
            tw.append([row.get('from'), row.get('to'), row.get('users'), enc(vals), bits])
            if len(tw) >= TRI_WEEKS:
                break
        ref = tri.get('ref') or []
        tref = [int(round(ref[k] * 1000)) if k < len(ref) and num(ref[k]) else None for k in TRI_COLS]

        T = af.get('tiles') or {}
        stp = [[max(S, add(g0, i)), None] for i in []]
        st_rng = []
        for f0, t0 in ((af.get('steep') or {}).get('ret_dau') or []):
            if t0 >= S:
                st_rng.append([max(f0, S), t0])
        apps.append({
            'id': aid, 'k': r['key'], 'nm': nmo['name'], 'store': nmo.get('stag') or nmo['store'], 'acc': nmo['acct'],
            'sz': size_of(aid), 'paisa': round(paisa.get(aid, 0), 2),
            'first': add(g0, first), 'settled': r.get('settled_till') or SET, 'dt': r.get('data_till') or E,
            'stage': af.get('stage'), 'ready': bool(r.get('ready')), 'rs': (r.get('edges') or {}).get('ret_state'),
            'vs': (r.get('edges') or {}).get('rev_state'), 'est': bool((af.get('flags') or {}).get('rev_est') or (af.get('flags') or {}).get('tz_blend')),
            'pkg': '', 'K': X['K'], 'sh': enc([int(round(x * 1e5)) for x in (X['sh'] or [])]),
            'nz': nz, 'u1': (T.get('d1') or {}).get('usual'), 'u7': (T.get('d7') or {}).get('usual'),
            'tst': (T.get('ret_dau') or {}).get('st'), 'steep': st_rng,
            'raw': cols, 'pre': enc(pre), 'bnd': bnd, 'rel': rel,
            'tri': {'w': tw, 'ref': enc(tref)},
            'al': (r.get('alerts') or {}),
        })
        # the engine's own numbers for the cross-check (its 7 settled days vs the 28 before)
        xcheck['apps'][nmo['name']] = {
            'win': r.get('win'), 'tiles': {k: {kk: (T.get(k) or {}).get(kk) for kk in ('v', 'base', 'rel', 'z', 'usual', 'st', 's', 'sp', 'from', 'to', 'bfrom', 'bto')} for k in ('ret_dau', 'd1', 'd7', 'sess', 'time', 'arpdau', 'ads')},
            'py_lens_tile': None,
        }
        tl = (T.get('ret_dau') or {})
        if tl.get('from') and tl.get('bfrom'):
            Lp = lens(X, diff(g0, tl['from']), diff(g0, tl['to']), diff(g0, tl['bfrom']), diff(g0, tl['bto']))
            xcheck['apps'][nmo['name']]['py_lens_tile'] = Lp

    idx_of = {x['id']: i for i, x in enumerate(apps)}

    # ---- alerts: open (DATA), recently closed, and the compact info rows (installs-only changes, ad price) -----------
    SEV = {'warning': 'bigda', 'watch': 'dhyan', 'good': 'behtar'}

    def pack(x, kind='open'):
        relx = x.get('release') or {}
        sp = x.get('sp')
        return {
            'a': idx_of.get(x.get('app_id'), -1), 'fam': x.get('family') or x.get('kind'), 'm': x.get('metric'),
            'sev': SEV.get(x.get('severity'), 'normal'), 'dir': x.get('dir'), 'now': x.get('now'), 'bef': x.get('before'),
            'rel': x.get('rel'), 'unit': x.get('unit'), 'users': x.get('users'), 'if': x.get('installs_from'), 'it': x.get('installs_to'),
            'bf': x.get('base_from'), 'bt': x.get('base_to'), 'since': x.get('since') or x.get('from'), 'day': x.get('day'),
            'at': x.get('alert_at') or x.get('opened_at'), 'seeded': bool(x.get('seeded')), 'opened': x.get('opened'),
            'prov': bool(x.get('provisional') or x.get('prov')), 'est': bool(x.get('estimate')), 'started': x.get('started'),
            'dt': x.get('data_till') or x.get('to'), 'tags': x.get('tags') or [], 'rl': relx.get('label'), 'rd': relx.get('date'),
            'sp': sp if (isinstance(sp, list) and sp and sp[0] == 'ret') else None, 'net': (sp[1] if (isinstance(sp, list) and sp and sp[0] == 'pu' and len(sp) > 1) else None),
            'kind': kind, 'closed': x.get('closed'), 'cat': x.get('closed_at'), 'to': x.get('to'),
        }

    alerts = [pack(x) for x in AC.get('alerts') or [] if x.get('app_id') in idx_of]
    for x in AC.get('closed') or []:
        if x.get('app_id') in idx_of and x.get('closed') and diff(x['closed'], today) <= 7:
            alerts.append(pack(x, 'closed'))
    for x in AC.get('info') or []:
        if x.get('app_id') in idx_of and x.get('src') != 'older' and x.get('kind') in ('installs', 'price'):
            alerts.append(pack(x, 'info'))

    noga = []
    for x in AC.get('no_ga4') or []:
        nm = names.get(x.get('app_id'), {})
        noga.append({'id': x.get('app_id'), 'nm': nm.get('name') or x.get('app'), 'acc': nm.get('acct', ''),
                     'sz': size_of(x.get('app_id')), 'why': x.get('text') or 'GA4 data nahi'})

    for ap in apps:
        cols = ap.pop('raw')
        for k, arr in cols.items():
            e = enc(arr)
            assert dec(e) == arr, k
            ap[k] = e

    meta = {'S': S, 'E': E, 'n': SPAN, 'today': today, 'gen': gen, 'fx': round(fx, 4), 'actLate': act_late, 'lag': lag,
            'settled': SET, 'apps': len(apps), 'LG': LG, 'bandDays': BAND_DAYS, 'triCols': TRI_COLS,
            'pfSettled': (AC.get('portfolio') or {}).get('settled_till'), 'mk': ((AC.get('market') or {}).get('latest'))}
    return {'meta': meta, 'apps': apps, 'alerts': alerts, 'noga': noga}
