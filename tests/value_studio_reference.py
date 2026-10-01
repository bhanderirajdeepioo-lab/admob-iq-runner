"""FROZEN REFERENCE — the owner-approved "Value Studio" (Install value) demo generator's data step, verbatim (only its file
reads take a site dir, and its private cross-check dump is left out). tests/test_value_studio_build.py checks
admob_iq.value_studio_build against it on synthetic sites: the Studio's file must hold EXACTLY the numbers the approved
demo was made from. Never edit this to make a parity test pass — a difference is a bug in the builder.
Synthetic data only (the tests build their own sites)."""
import gzip, json, os, re, sys, math, datetime as dt
from collections import defaultdict

SITE = None                 # the site dir reference(site) reads

NW = 32                     # install weeks shipped per app (range 12 + compare 12 + the app's 8-week normal + slack)
T = [0, 1, 3, 7, 14, 30, 60, 90, 180, 365]


def jload(name):
    p = os.path.join(SITE, name)
    if name.endswith('.gz'):
        with gzip.open(p, 'rt') as f:
            return json.load(f)
    with open(p) as f:
        return json.load(f)


def D(s):
    return dt.date.fromisoformat(s[:10])


def add(s, n):
    return (D(s) + dt.timedelta(days=n)).isoformat()


def diff(a, b):
    return (D(b) - D(a)).days


def num(v):
    return v is not None and isinstance(v, (int, float)) and not isinstance(v, bool) and not (isinstance(v, float) and math.isnan(v))


def ri(v, k=1):
    return None if not num(v) else int(round(v * k))


_ALPH = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'


def enc(arr):
    """ints → compact text: delta from the previous non-null, zigzag, 5-bit groups; '~' = null (same as Uninstall Studio)."""
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


def E(arr):
    e = enc(arr)
    assert dec(e) == [None if v is None else int(v) for v in arr]
    return e



MONS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def fmt_n(v):
    v = int(round(v))
    if v >= 100000:
        x = v / 1e5
        return ('%.2f' % x).rstrip('0').rstrip('.') + ' lakh'
    return '{:,}'.format(v)


def pct(v):
    return (('%.1f' % v).rstrip('0').rstrip('.') if v < 10 else '%d' % round(v)) + '%'


def fix_long_text(t, LG):
    """The engine's long-term line says 'back after 90 days 4.3%' — the page says the people first, the % beside them
    ('back after 90 days 1,234 (4.3%)'). Lines built before the wording change ('90 din baad 100 me se 4.3 app khol
    rahe') get the same new words."""
    if not t:
        return t
    t = re.sub(r'(\d+) din baad 100 me se ([\d.]+) app khol rahe', r'back after \1 days \2%', t)
    t = re.sub(r' \(pichhle ([^()]*?): ~([\d.]+)\)', r' (pichhle \1: ~\2%)', t)
    m = re.match(r'^(\w{3}) (\d{4}) ke installs: back after (\d+) days ([\d.]+)%', t)
    q = re.match(r'^Q(\d) (\d{4}) \(\w+–\w+\) ke installs: back after (\d+) days ([\d.]+)%', t)
    row = None
    if m and m.group(1) in MONS:
        key = '%s-%02d' % (m.group(2), MONS.index(m.group(1)) + 1)
        row = next((x for x in LG.get('rows') or [] if x.get('key') == key), None)
        tt = m.group(3)
    elif q:
        key = '%s-Q%s' % (q.group(2), q.group(1))
        row = next((x for x in LG.get('rows') or [] if x.get('key') == key), None)
        tt = q.group(3)
    else:
        return t
    ret = (((row or {}).get('d') or {}).get(tt) or {}).get('ret')
    out = re.sub(r'back after (\d+) days ([\d.]+)%',
                 lambda z: 'back after %s days %s' % (z.group(1), ('%s (%s)' % (fmt_n(ret), pct(float(z.group(2))))
                                                                   if ret else pct(float(z.group(2))))), t, count=1)
    out = re.sub(r' \(pichhle ([^()]*?): ~([\d.]+)%\)',
                 lambda z: ' — normal ~%s (pichhle %s)' % (pct(float(z.group(2))), z.group(1)), out)
    return out


def fix_ver_info(t, BV):
    """'v1.3.7 ke naye users back after 30 days zyada: 7.4%, pichhle v1.3.5 me 5%' → the people first, % beside
    ('… zyada: 1,234 (7.4%), pichhle v1.3.5 me 5%'). Lines built before the wording change ('30 din baad zyada: 100 me
    7.4, pichhle v1.3.5 me 5') get the same new words."""
    t = t or ''
    o = re.search(r'^(v\S+) ke naye users (\d+) din baad (\w+): 100 me ([\d.]+), pichhle (\S+) me ([\d.]+)$', t)
    if o:
        t = '%s ke naye users back after %s days %s: %s%%, pichhle %s me %s%%' % o.groups()
    m = re.search(r'^(v\S+) ke naye users back after (\d+) days (\w+): ([\d.]+)%, pichhle (\S+) me ([\d.]+)%$', t)
    if not m:
        return re.sub(r'100 me( se)? ([\d.]+)', lambda z: pct(float(z.group(2))), t)
    lab, tt = m.group(1), m.group(2)
    row = next((x for x in (BV or {}).get('rows') or [] if (x.get('label') or ('v' + str(x.get('ver')))) == lab), None)
    ret = ((row or {}).get('d' + tt) or {}).get('ret')
    now = ('%s (%s)' % (fmt_n(ret), pct(float(m.group(4))))) if ret else pct(float(m.group(4)))
    return '%s ke naye users back after %s days %s: %s, pichhle %s me %s' % (
        lab, tt, m.group(3), now, m.group(5), pct(float(m.group(6))))


VERD = {'keep': 'k', 'slow': 's', 'late': 'l', 'costly': 'c', 'top': 't', 'avg': 'a', 'low': 'w', 'few': 'f', 'wait': 'x'}
WHY = {None: '', 'nospend': 'n', 'thin': 't', 'wait': 'w', 'unknown': 'u', 'noproj': 'p'}


def build():
    dash = jload('dashboard.json.gz')
    V = dash['value']
    U = jload('uninstall.json.gz')
    accn = jload('account_names.json')
    appn = jload('app_names.json')
    fx_now = float(dash.get('usd_inr') or 83)
    today, gen = dash['today_date'], dash['generated_at']
    H = int(V.get('horizon') or 90)
    settled = V.get('settled_till_max') or V.get('settled_till_min')
    roas = dash.get('roas') or {}
    rfx = float(((roas.get('fx') or {}).get('INR')) or 0) or None           # roas daily = INR × rfx (USD micros)

    # ---- names: "<store name> · <account>" (the uninstall studio's rule), never cut ------------------------------
    cat = {c['app_id']: c for c in dash['apps_catalog'] if c.get('app_id')}
    launch_by = {}
    for r in dash['active'].get('apps') or []:
        if r.get('app_id') and r.get('launch_day'):
            launch_by[r['app_id']] = r['launch_day']
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
        tag = ' (%s wala)' % launch_by[aid][:4] if dup[v['store'] + '|' + v['acct']] > 1 and launch_by.get(aid) else ''
        v['name'] = v['store'] + tag + ' · ' + v['acct']
        v['store'] = v['store'] + tag                 # two same-named apps in one account: '(2024 wala)' stays in every view
    by_dname = {v['dname']: aid for aid, v in names.items()}

    # ---- size: AdMob kamai/day (last 7 finished days) + Google Ads spend/day (same rule as the uninstall studio) ----
    y = dash.get('latest_complete') or add(today, -1)
    w7 = {add(y, -i) for i in range(7)}
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
    spend28 = {}
    for v in V.get('apps') or []:
        s = float(((v.get('cpi') or {}).get('spend4')) or 0) / 28
        spend28[v['app_id']] = s
    paisa = {aid: k7[aid] + spend28.get(aid, 0) for aid in names}

    def size_of(aid):
        p = paisa.get(aid, 0)
        return 'badi' if p >= 300 else ('chhoti' if p < 30 else 'madhyam')

    # ---- the shipped install weeks: the NW newest Monday weeks up to the newest complete one ----------------------
    rows = [r for r in V['apps'] if r.get('status') == 'ok' and r.get('file')]
    files = {}
    newest = None
    for r in rows:
        d = jload(r['file'])
        files[r['app_id']] = d
        for w in d.get('weeks') or []:
            if newest is None or w['from'] > newest:
                newest = w['from']
    EW = newest
    SW = add(EW, -7 * (NW - 1))

    # GA4 daily installs (uninstall.json) — for the cross-check that week n = Σ daily new
    ub = {a['app_id']: a for a in U.get('apps') or []}

    info_by = defaultdict(list)
    for x in V.get('info') or []:
        info_by[x.get('app_id')].append(x)

    apps = []
    span_days = diff(SW, add(EW, 6)) + 1
    spend_till = None
    for r in sorted(rows, key=lambda z: names.get(z['app_id'], {}).get('name', z['app'])):
        aid = r['app_id']
        d = files[aid]
        nmo = names.get(aid) or {'name': r['app'], 'store': r['app'], 'acct': '', 'dname': r['app']}
        wk = {w['from']: w for w in d.get('weeks') or []}
        cols = {k: [] for k in ('n', 'sp', 'sr', 'na', 'jo', 'q', 'pp', 'plo', 'phi', 'pf', 'p365')}
        jud, why = [], []
        V10, LO, HI = [], [], []
        fx_last = None
        rels = {}
        for i in range(NW):
            ws = add(SW, 7 * i)
            w = wk.get(ws)
            if not w:
                for k in cols:
                    cols[k].append(None)
                jud.append('0')
                why.append('-')
                V10.extend([None] * 10)
                LO.extend([None] * 10)
                HI.extend([None] * 10)
                continue
            n = w.get('n')
            cols['n'].append(ri(n))
            sp = w.get('spend')
            cols['sp'].append(ri(sp, 100))
            cols['sr'].append(ri(w.get('spend_src')))
            if num(sp) and sp > 0 and num(w.get('spend_src')):
                fx_last = w['spend_src'] / sp
            cols['na'].append(ri(w.get('n_ads')))
            jo = None
            if w.get('t_o') is not None and w['t_o'] in T:
                jo = T.index(w['t_o'])
            cols['jo'].append(-1 if jo is None else jo)
            qm = 0
            for j in range(10):
                if (w.get('est') or [False] * 10)[j] or (w.get('Lq') or [False] * 10)[j]:
                    qm |= 1 << j
            cols['q'].append(qm)
            jud.append('1' if w.get('judged') else '0')
            why.append(WHY.get(w.get('why'), '?') or '.')
            rpi, rpip = w.get('rpi') or [None] * 10, w.get('rpip') or [None] * 10
            e = w.get('ecpi')
            for j in range(10):
                if jo is not None and j <= jo:
                    V10.append(ri(rpi[j], 1e6))
                    LO.append(None)
                    HI.append(None)
                else:
                    V10.append(ri(rpip[j], 1e6))
                    lo_ = (w.get('Llo') or [None] * 10)[j]
                    hi_ = (w.get('Lhi') or [None] * 10)[j]
                    LO.append(ri(lo_ * e / 100, 1e6) if (num(lo_) and num(e)) else None)
                    HI.append(ri(hi_ * e / 100, 1e6) if (num(hi_) and num(e)) else None)
            P = w.get('pay') or None
            if P:
                cols['pp'].append(ri(P.get('p')))
                cols['plo'].append(ri(P.get('lo')))
                cols['phi'].append(ri(P.get('hi')))
                cols['pf'].append((1 if P.get('obs') else 0) | (2 if P.get('never') else 0) | (4 if P.get('rough') else 0)
                                  | (8 if P.get('shape') == 'portfolio' else 0) | (16 if P.get('hi_over') else 0))
                cols['p365'].append(ri(P.get('pct365'), 10))
            else:
                for k in ('pp', 'plo', 'phi', 'pf', 'p365'):
                    cols[k].append(None)
            R = w.get('release')
            if R and R.get('date'):
                rels[R.get('key') or R['date']] = R
        # releases also from versions / long-term rows (dedupe by key / date)
        BV = d.get('by_version') if isinstance(d.get('by_version'), dict) else None
        for x in (BV or {}).get('rows') or []:
            R = x.get('release')
            if R and R.get('date'):
                rels.setdefault(R.get('key') or R['date'], R)
        LG = d.get('long') if isinstance(d.get('long'), dict) else None
        for x in (LG or {}).get('rows') or []:
            for R in x.get('release') or []:
                if R and R.get('date'):
                    rels.setdefault(R.get('key') or R['date'], R)
        rel = []
        seen = set()
        for R in sorted(rels.values(), key=lambda z: z['date']):
            if R['date'] < add(SW, -60):
                continue
            lab = ('v' + str(R['version'])) if R.get('version') else 'App update'
            if (R['date'], lab) in seen:
                continue
            seen.add((R['date'], lab))
            rel.append([R['date'], lab])

        # daily Google Ads spend (billed ₹) from the Marketing ROAS cache — the same cache the engine sums per week
        ra = (roas.get('by_app') or {}).get(nmo['dname']) or (roas.get('by_app') or {}).get(d.get('app'))
        spd = None
        if ra and rfx and any((ra.get('daily') or {}).values()):
            dd = ra.get('daily') or {}
            last = max(dd.keys()) if dd else None
            lc = dash.get('latest_complete') or add(today, -1)                 # today's spend is partial: never shown
            cap = min(x for x in (d.get('spend_till'), lc) if x) if (d.get('spend_till') or lc) else None
            if last and cap and last > cap:
                last = cap
            if last and last >= SW:
                spend_till = max(spend_till or last, last)
                spd = [ri((dd.get(add(SW, k)) or 0) / 1e6 / rfx) for k in range(diff(SW, last) + 1)]

        # countries (the engine's own window; Google Ads cost by country when geo is on)
        C = d.get('countries') or {}
        cty = None
        if C.get('win'):
            cost = C.get('cost') or {}
            cfx = (cost['total_src'] / cost['total']) if (num(cost.get('total')) and cost['total'] and num(cost.get('total_src'))) else (fx_last or fx_now)
            crow = []
            for x in [C.get('app')] + list(C.get('rows') or []):
                if not x or not x.get('cc'):
                    continue
                K = x.get('cpi') or {}
                P = x.get('pay') or {}
                B = x.get('back') or {}
                R30 = ((x.get('rpi') or {}).get('30')) or {}
                fl = ((1 if x.get('be_proj') else 0) | (2 if K.get('thin') else 0) | (4 if K.get('noads') else 0) | (8 if K.get('unknown') else 0)
                      | (16 if x.get('few') else 0) | (32 if x.get('clean') is False else 0) | (64 if P.get('never') else 0) | (128 if P.get('obs') else 0)
                      | (256 if R30.get('est') or R30.get('proj') else 0) | (512 if x.get('smp') else 0))
                crow.append({'cc': x['cc'], 'n': ri(x.get('n')), 'sp': ri(K.get('spend'), 100), 'cpi': ri(K.get('v'), 1e6), 'be': ri(x.get('be'), 1e6), 'fl': fl,
                             'vd': VERD.get(x.get('verdict'), '.'), 'why': {'gap': 'g', 'young': 'y', 'few_val': 'f'}.get(x.get('why'), '.' if not x.get('why') else '?'),
                             'pp': ri(P.get('p')), 'plo': ri(P.get('lo')), 'phi': ri(P.get('hi')), 'up': ri(P.get('upto')),
                             'b7': ri(B.get('7'), 10), 'b30': ri(B.get('30'), 10), 'b90': ri(B.get('90'), 10),
                             'd1': ri((x.get('d1') or {}).get('v'), 10), 'd7': ri((x.get('d7') or {}).get('v'), 10), 'd30': ri((x.get('d30') or {}).get('v'), 10),
                             'r30': ri(R30.get('v'), 1e6), 'sh': ri(x.get('share'), 1e4), 'ads': ri(K.get('ads'), 1e6), 'dl': ri(K.get('dl')), 'pd': ri(K.get('paid'), 1000)})
            Wn = C['win']
            sm = C.get('small') or {}
            numk = ['n', 'sp', 'cpi', 'be', 'fl', 'pp', 'plo', 'phi', 'up', 'b7', 'b30', 'b90', 'd1', 'd7', 'd30', 'r30', 'sh', 'ads', 'dl', 'pd']
            cty = {'f': Wn.get('from'), 't': Wn.get('to'), 'wk': Wn.get('weeks'), 'f30': Wn.get('from30'), 't30': Wn.get('to30'),
                   'fx': round(cfx, 4), 'geo': bool(C.get('geo')) and (C.get('geo_why') in (None, 'ok')), 'gw': C.get('geo_why'),
                   'smp': bool(C.get('smp')), 'st': C.get('state'),
                   'cc': ','.join(r_['cc'] for r_ in crow), 'vd': ''.join(r_['vd'] for r_ in crow), 'why': ''.join(r_['why'] for r_ in crow),
                   'small': [ri(sm.get('n')), ri(sm.get('countries')), ri(sm.get('cost'), 100), ri(sm.get('share'), 1e4)],
                   'unm': [ri(cost.get('unmapped'), 100), ri(cost.get('unmapped_share'), 1e4)],
                   'total': ri(cost.get('total'), 100), 'unas': ri(((C.get('unassigned') or {}).get('n')))}
            for k in numk:
                cty['c_' + k] = E([r_[k] for r_ in crow])

        # versions (🧬) — newest 8
        ver = None
        if BV and BV.get('state') in ('ok', 'single'):
            vr = []
            for x in sorted(BV.get('rows') or [], key=lambda z: z.get('from') or '', reverse=True)[:8]:
                def m(M):
                    M = M or {}
                    return [ri(M.get('v'), 100), ri(M.get('ret')), ri(M.get('n')), M.get('st') or '', ri(M.get('in')), 1 if M.get('q') else 0]
                Rp = x.get('rpi') or {}

                def mr(M):
                    M = M or {}
                    return [ri(M.get('v'), 1e6), M.get('st') or '', 1 if M.get('est') else 0, ri(M.get('in'))]
                VS = x.get('vs') or {}
                vsl = VS.get('label') or (('v' + str(VS['ver'])) if VS.get('ver') not in (None, '') else '')
                vr.append([x.get('label') or ('v' + str(x.get('ver'))), x.get('from'), x.get('to'), ri(x.get('n')), ri(x.get('days')), 1 if x.get('current') else 0,
                           m(x.get('d1')), m(x.get('d7')), m(x.get('d30')), mr(Rp.get('1')), mr(Rp.get('7')), mr(Rp.get('30')), x.get('verdict') or '',
                           vsl, ri(((VS.get('d1') or {}).get('v0')), 100), ri(((VS.get('d1') or {}).get('v1')), 100), ri(((VS.get('d7') or {}).get('v0')), 100), ri(((VS.get('d7') or {}).get('v1')), 100),
                           ((x.get('release') or {}).get('date'))])
            vt = BV.get('text') or ''
            ver = {'t': '', 'tail': (re.findall(r'\. ([^.]+\.)$', vt) or [''])[0], 'r': vr, 'older': BV.get('older') or 0}
        elif BV:
            ver = {'t': BV.get('text') or '', 'r': [], 'st': BV.get('state')}

        # long-term by install month (🗓️) — newest 18
        lng = None
        if LG and LG.get('state') == 'ok':
            L18 = sorted(LG.get('rows') or [], key=lambda z: z.get('key') or z.get('from') or '', reverse=True)[:15]
            ST = {'ok': 'o', 'wait': 'w', 'few': 'f', 'nodata': 'n', 'part': 'p', '': '.'}
            lng = {'t': fix_long_text(LG.get('text') or '', LG), 'g': LG.get('grain'), 'k': ','.join(str(x.get('key')) for x in L18),
                   'n': E([ri(x.get('n')) for x in L18]), 'part': ''.join('1' if x.get('part') else '0' for x in L18),
                   'b365': E([ri(x.get('b365'), 10) for x in L18]), 'bf': ''.join(str((1 if x.get('b365_proj') else 0) | (2 if x.get('b365_thin') else 0)) for x in L18),
                   'rel': E([len(x.get('release') or []) for x in L18])}
            for t in ('30', '60', '90', '180', '365'):
                Ms = [((x.get('d') or {}).get(t)) or {} for x in L18]
                lng['d' + t] = E([ri(M.get('v'), 100) for M in Ms])
                lng['dr' + t] = E([ri(M.get('ret')) for M in Ms])
                lng['ds' + t] = ''.join(ST.get(M.get('st') or '', '?') for M in Ms)
                lng['di' + t] = E([ri(M.get('in')) for M in Ms])
            for t in ('30', '90', '180', '365'):
                Ms = [((x.get('rpi') or {}).get(t)) or {} for x in L18]
                lng['r' + t] = E([ri(M.get('v'), 1e6) for M in Ms])
                lng['rf' + t] = ''.join(str((1 if M.get('proj') else 0) | (2 if M.get('est') else 0) | (4 if M.get('st') == 'wait' else 0)) for M in Ms)
                lng['ri' + t] = E([ri(M.get('in')) for M in Ms])
        elif LG:
            lng = {'t': LG.get('text') or '', 'k': '', 'st': LG.get('state')}

        T_ = d.get('tiles') or {}
        tp, tb, tc, tr = T_.get('pay') or {}, T_.get('b7') or {}, T_.get('cpi') or {}, T_.get('rpi') or {}
        S_ = r.get('s') or {}
        eng = {'st': tp.get('st'), 'why': tp.get('why'), 'p': tp.get('v'), 'p0': tp.get('base'), 'never': bool(tp.get('never')), 'pct': tp.get('pct365'),
               'lo': tp.get('lo'), 'hi': tp.get('hi'), 'obs': bool(tp.get('obs')), 'rough': bool(tp.get('rough')), 'shape': tp.get('shape'),
               'f': tp.get('from'), 't': tp.get('to'), 'note': tp.get('note'),
               'b7': tb.get('v'), 'b7b': tb.get('base'), 'b7f': tb.get('from'), 'b7t': tb.get('to'),
               'cpi': tc.get('v'), 'cpiF': tc.get('from'), 'cpiT': tc.get('to'), 'cst': tc.get('st'),
               'r30': tr.get('v'), 'r30f': tr.get('from'), 'r30t': tr.get('to'),
               'sum': (d.get('summary') or {}).get('text') or '', 'kind': (d.get('summary') or {}).get('kind'),
               'ads': d.get('ads'), 'curveN': (d.get('curve') or {}).get('normal'), 'shapeN': (d.get('curve') or {}).get('shape')}

        inf = []
        for x in info_by.get(aid, []):
            tx = x.get('text') or ''
            if x.get('kind') in ('ver_d30', 'ver_mix'):
                tx = fix_ver_info(tx, BV)
            inf.append([x.get('kind'), x.get('from'), x.get('to'), x.get('started'), x.get('cc') or '', tx])

        apps.append({
            'id': aid, 'k': d.get('key') or r.get('key'), 'nm': nmo['name'], 'store': nmo['store'], 'acc': nmo['acct'],
            'sz': size_of(aid), 'paisa': round(paisa.get(aid, 0), 2), 'settled': d.get('settled_till') or settled,
            'spT': d.get('spend_till'), 'revT': d.get('rev_till'), 'fxL': round(fx_last, 4) if fx_last else None,
            'n': E(cols['n']), 'sp': E(cols['sp']), 'sr': E(cols['sr']), 'na': E(cols['na']), 'jo': E(cols['jo']), 'q': E(cols['q']),
            'j': ''.join(jud), 'why': ''.join(why), 'v': E(V10), 'lo': E(LO), 'hi': E(HI),
            'pp': E(cols['pp']), 'plo': E(cols['plo']), 'phi': E(cols['phi']), 'pf': E(cols['pf']), 'p365': E(cols['p365']),
            'rel': rel, 'spd': E(spd) if spd else None, 'cty': cty, 'ver': ver, 'lng': lng, 'eng': eng, 'info': inf,
            'chk': ((d.get('scale') or {}).get('text') or [])[:1],
        })

    noga = []
    for x in V.get('no_ga4') or []:
        nm = names.get(x.get('app_id'), {})
        noga.append({'id': x.get('app_id'), 'store': nm.get('store') or x.get('app'), 'acc': nm.get('acct', ''), 'sz': size_of(x.get('app_id')),
                     'paisa': round(paisa.get(x.get('app_id'), 0), 2), 'why': x.get('text') or 'GA4 data nahi'})

    meta = {'SW': SW, 'EW': EW, 'nw': NW, 'today': today, 'gen': gen, 'fx': round(fx_now, 4), 'H': H, 'settled': settled,
            'spendTill': spend_till, 'T': T, 'alerts': len(V.get('alerts') or []), 'closed': len(V.get('closed') or []),
            'alertCounts': V.get('alert_counts'), 'apps': len(apps), 'consts': {k: (V.get('consts') or {}).get(k) for k in ('spend_min_week', 'n_min_week', 'cty_judge', 'win_weeks', 'pay_min_n', 'pay_base_weeks')}}
    return {'meta': meta, 'apps': apps, 'noga': noga}


def reference(site):
    """The demo generator's build() up to its data blob, reading the site dir `site` → data."""
    global SITE
    SITE = site
    return build()
