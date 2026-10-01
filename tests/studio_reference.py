"""FROZEN REFERENCE — the owner-approved "Uninstall Studio" demo generator's data step, verbatim (only its file reads
take a site dir, and its private stderr note / cross-check dump are left out). tests/test_uninstall_studio_build.py
checks admob_iq.uninstall_studio_build against it on synthetic sites: the Studio's file must hold EXACTLY the numbers
the approved demo was made from. Never edit this to make a parity test pass — a difference is a bug in the builder.
Synthetic data only (the tests build their own sites)."""
import gzip, json, os, math
from collections import defaultdict
import datetime as dt

SPAN = 156            # days per app: 60-day range + 60-day compare + 35 days of 'normal' before the compare
COH_WEEKS = 12        # install weeks in the cohort heatmap
COH_COLS = [0, 1, 3, 7, 14, 30, 60, 90]


def D(s):
    return dt.date.fromisoformat(s[:10])


def add(s, n):
    return (D(s) + dt.timedelta(days=n)).isoformat()


def diff(a, b):
    return (D(b) - D(a)).days


def num(v):
    return v is not None and isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))


def r3(v):
    return None if not num(v) else round(v, 5)


# compact integer arrays: delta from the previous non-null value, zigzag, 5-bit groups as text
# ('A'..'Z','a'..'f' = last group; 'g'..'z','0'..'9','-','_'... = more groups follow), '~' = null
_ALPH = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'


def enc(arr):
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


def reference(site):
    """The demo generator's main() up to its data blob, reading the site dir `site` → data."""
    def jload(name):
        p = os.path.join(site, name)
        if name.endswith('.gz'):
            with gzip.open(p, 'rt') as f:
                return json.load(f)
        with open(p) as f:
            return json.load(f)

    dash = jload('dashboard.json.gz')
    U = jload('uninstall.json.gz')
    accn = jload('account_names.json')
    appn = jload('app_names.json')
    fx = float(dash.get('usd_inr') or 83)
    today = dash['today_date']
    gen = dash['generated_at']
    K = U['consts']
    late, lag = int(K.get('late_days', 7)), int(K.get('lag_days', 2))
    AK = dash['active'].get('consts') or {}
    act_late = int(AK.get('act_late_days', 3))

    # ---- app names: "<store name> · <account>" (smpApps rule), never cut -------------------------
    cat = {c['app_id']: c for c in dash['apps_catalog'] if c.get('app_id')}
    launch_by = {}
    for r in dash['active'].get('apps') or []:
        if r.get('app_id') and r.get('launch_day'):
            launch_by[r['app_id']] = r['launch_day']
    for a in U['apps']:
        L = a.get('launch') or {}
        if a['app_id'] not in launch_by and (L.get('day') or L.get('date')):
            launch_by[a['app_id']] = L.get('day') or L.get('date')
    names = {}
    for aid, c in cat.items():
        acc = str(c.get('account_id') or '')
        nm = str(c.get('app_name') or aid)
        store = str(appn.get(aid) or (nm.rsplit(' · ', 1)[0] if ' · ' in nm else nm)).replace('–', '-').replace('—', '-')
        acct = accn.get(acc) or ('A/c ' + (acc.split('-')[1][:4] if '-' in acc else acc[:4]))
        names[aid] = {'store': store, 'acct': acct, 'dname': nm, 'acc_id': acc}
    dup = defaultdict(int)
    for v in names.values():
        dup[v['store'] + '|' + v['acct']] += 1
    for aid, v in names.items():
        tag = ''
        if dup[v['store'] + '|' + v['acct']] > 1 and launch_by.get(aid):
            tag = ' (%s wala)' % launch_by[aid][:4]
        v['name'] = v['store'] + tag + ' · ' + v['acct']
    by_dname = {v['dname']: aid for aid, v in names.items()}

    # ---- size (smpApps): AdMob kamai/day over the last 7 finished days + Google Ads spend/day -------
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

    # ---- common end: the latest GA4 day every app has ------------------------------------------
    ga = [a for a in U['apps'] if a.get('data_till') and a.get('daily')]
    E = min(a['data_till'] for a in ga)
    S = add(E, -(SPAN - 1))
    settled_min = min(a.get('settled_till') or E for a in ga)

    # dashboard summary rows (status counts, head4 for cross-check)
    srow = {x['app_id']: x for x in dash['uninstall'].get('apps') or []}
    open_alerts = dash['uninstall'].get('alerts') or []

    apps = []
    for a in sorted(ga, key=lambda z: names.get(z['app_id'], {}).get('name', z['app'])):
        aid = a['app_id']
        nmo = names.get(aid) or {'name': a['app'], 'store': a['app'], 'acct': '', 'acc_id': ''}
        Dy = a['daily']
        st = Dy['start']
        den = Dy.get('a1') if (a.get('den') == 'dau' and Dy.get('a1')) else Dy.get('a28')
        brk = {diff(st, b) for b in (Dy.get('breaks') or [])}
        n_d = len(Dy.get('new') or Dy.get('un') or [])

        def g(k, i):
            arr = Dy.get(k)
            if arr is None or i < 0 or i >= len(arr):
                return None
            v = arr[i]
            return v if num(v) else None

        L = a.get('launch') or {}
        first = L['day'] if (L.get('hidden') and L.get('day')) else (a.get('history_start') or st)

        # cohort file → gone-by-day-N per install day
        c = jload('uninstall_c_%s.json.gz' % a['key'])
        cst, cnew, lags = c['start'], c['new'], c['lags']
        cend = c.get('end') or E

        def cum(i, N):
            return sum(cnt for lg, cnt in (lags[i] or []) if lg <= N)

        def at(i, N):   # uninstalls exactly N days after install
            return sum(cnt for lg, cnt in (lags[i] or []) if lg == N)

        # active file → active users, revenue, next-day returners
        act = jload('active_%s.json.gz' % a['key'])
        AD = act['daily']
        ast = AD['start']
        aok = (AD.get('coh') or {}).get('ok') or []
        ad1 = (AD.get('coh') or {}).get('d1') or []
        anew = AD.get('new') or []
        ret_from = ((act.get('edges') or {}).get('ret_from')) or AD['start']
        aset = act.get('settled_till') or a.get('settled_till')

        cols = {k: [] for k in ('nw', 'un', 'a28', 'md', 'lo', 'hi', 'g0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'r1', 'rv', 'a1')}
        mism = 0
        for j in range(SPAN):
            day = add(S, j)
            i = diff(st, day)
            nw, un, d_, rt = g('new', i), g('un', i), None, g('rate', i)
            if den is not None and 0 <= i < len(den) and num(den[i]):
                d_ = den[i]
            ok_rate = (un is not None and d_ is not None and d_ > 0 and rt is not None and i not in brk)
            md, lo, hi = g('med', i), g('lo', i), g('hi', i)
            band = ok_rate and md is not None and lo is not None and hi is not None
            cols['nw'].append(nw)
            cols['un'].append(un)
            cols['a28'].append(int(d_) if ok_rate else None)
            cols['md'].append(int(round(md * 1000)) if band else None)
            cols['lo'].append(int(round(lo * 1000)) if band else None)
            cols['hi'].append(int(round(hi * 1000)) if band else None)
            ci = diff(cst, day)
            if 0 <= ci < len(cnew) and day <= cend and num(cnew[ci]):
                age = diff(day, cend)
                cols['g0'].append(cum(ci, 0))
                for L in range(1, 8):
                    cols['c%d' % L].append(at(ci, L) if age >= L else None)
                if nw is not None and cnew[ci] != nw:
                    mism += 1
            else:
                cols['g0'].append(None)
                for L in range(1, 8):
                    cols['c%d' % L].append(None)
            ai = diff(ast, day)
            r1 = None
            if 0 <= ai < len(aok) and aok[ai] == 1 and day >= ret_from:
                an = anew[ai] if ai < len(anew) else None
                v1 = ad1[ai] if ai < len(ad1) else None
                if num(an) and an > 0 and num(v1):
                    r1 = int(v1)
                    if nw is not None and an != nw:
                        mism += 1
            cols['r1'].append(r1)
            rv = AD['rev'][ai] if 0 <= ai < len(AD.get('rev') or []) else None
            cols['rv'].append(int(round(rv * 100)) if num(rv) else None)
            a1 = AD['a1'][ai] if 0 <= ai < len(AD.get('a1') or []) else None
            cols['a1'].append(int(a1) if num(a1) else None)

        # updates (📦) inside the span, with the engine's verdict level
        rel = []
        for u in (a.get('impact') or {}).get('updates') or []:
            if u.get('date') and S <= u['date'] <= E:
                v = u.get('verdict') or {}
                rel.append([u['date'], u.get('label') or 'App update', v.get('level'), bool(v.get('final'))])
        seen = {r[0] for r in rel}
        for r in a.get('releases') or []:
            if S <= r['date'] <= E and r['date'] not in seen and not any(0 <= diff(x[0], r['date']) <= 3 for x in rel):
                rel.append([r['date'], ('v' + r['version']) if r.get('version') else 'App update', None, False])
        rel.sort()

        # install-week × day-since-install: % still installed (12 newest ISO weeks)
        lastMon = add(E, -D(E).weekday())
        weeks = []
        for w in range(COH_WEEKS - 1, -1, -1):
            ws = add(lastMon, -7 * w)
            we = add(ws, 6)
            f0 = max(ws, first, cst)
            t0 = min(we, E)
            if f0 > t0:
                continue
            idx = [diff(cst, add(f0, k)) for k in range(diff(f0, t0) + 1)]
            idx = [i for i in idx if 0 <= i < len(cnew)]
            n = sum(cnew[i] for i in idx if num(cnew[i]))
            row = []
            for N in COH_COLS:
                if add(t0, N) > E or n <= 0:
                    row.append(None)
                    continue
                gsum = sum(cum(i, N) for i in idx)
                row.append(int(round((1 - gsum / n) * 1000)))
            prov = [1 if (add(t0, N) > (a.get('settled_till') or E) and row[k] is not None) else 0 for k, N in enumerate(COH_COLS)]
            weeks.append({'w': ws, 'f': f0, 't': t0, 'n': n, 'v': row, 'p': prov, 'part': 1 if (f0 != ws or t0 != we) else 0})
        tri = a.get('triangle') or {}
        tcols, tref = tri.get('cols') or [], tri.get('ref') or []
        ref = []
        for N in COH_COLS:
            if N in tcols and tcols.index(N) < len(tref) and num(tref[tcols.index(N)]):
                ref.append(int(round((1 - tref[tcols.index(N)]) * 1000)))
            else:
                ref.append(None)

        # engine status (the dashboard's own verdict words)
        v = (a.get('survival') or {}).get('verdict')
        vk = 'none'
        if v:
            if v.get('fires'):
                vk = 'worse' if v.get('dir') == 'worse' else 'better'
            elif v.get('low_sample'):
                vk = 'low'
            else:
                vk = 'same'
        sr = srow.get(aid, {})
        apps.append({
            'id': aid, 'k': a['key'], 'nm': nmo['name'], 'store': nmo['store'], 'acc': nmo['acct'],
            'sz': size_of(aid), 'paisa': round(paisa.get(aid, 0), 2),
            'first': first, 'settled': a.get('settled_till') or E, 'aset': aset, 'retFrom': ret_from,
            'stage': a.get('stage'), 'ready': bool(sr.get('ready', True)), 'vk': vk, 'pkg': a.get('package') or '',
            'ac': sr.get('alerts') or {},
            'raw': cols, 'rel': rel,
            'coh': {'ref': ref, 'w': [[w['w'], w['n'], enc(w['v']), int(''.join(map(str, w['p'])) or '0', 2), w['f'], w['t']] if w['part']
                                    else [w['w'], w['n'], enc(w['v']), int(''.join(map(str, w['p'])) or '0', 2)] for w in weeks]},
        })

    idx_of = {x['id']: i for i, x in enumerate(apps)}

    # ---- alerts: the open ones (DATA) + the recently recovered ones ("Theek ho gaya") -------------
    def arpdau28(ap):
        rv = sum(x for x in ap['raw']['rv'][-28:] if x is not None) / 100
        a1 = sum(x for x in ap['raw']['a1'][-28:] if x is not None)
        return rv / a1 if a1 else None

    def avg_den(ap, f, t):
        xs = [ap['raw']['a28'][diff(S, add(f, k))] for k in range(diff(f, t) + 1) if 0 <= diff(S, add(f, k)) < SPAN]
        xs = [x for x in xs if x]
        return sum(xs) / len(xs) if xs else None

    def people(x, ap):
        """signed people / day for an alert, + = more of what the alert measures; kind: gaye | wapas | None"""
        fam = x.get('family')
        now, bef, users = x.get('now'), x.get('before'), x.get('users')
        if fam == 'cohort' and num(now) and num(bef) and num(users) and x.get('installs_from') and x.get('installs_to'):
            days = diff(x['installs_from'], x['installs_to']) + 1
            return users * (now - bef) / max(1, days), 'gaye'
        if fam in ('rate_drift', 'rate_spike') and num(now) and num(bef) and ap is not None:
            f = x.get('since') or x.get('day')
            t = x.get('data_till') if fam == 'rate_drift' else x.get('day')
            dn = avg_den(ap, f, t) if f and t else None
            if dn:
                return (now - bef) / 1000 * dn, 'gaye'
        if fam in ('impact', 'impact_late'):
            rows = (x.get('rows') or {})
            m = (rows.get('worse') or rows.get('better') or [None])[0]
            if m in ('uninstall_d0',) and num(now) and num(bef) and num(users) and x.get('installs_from'):
                days = diff(x['installs_from'], x['installs_to']) + 1
                return users * (now - bef) / max(1, days), 'gaye'
            if m in ('new_d1', 'new_d7', 'new_d30') and num(now) and num(bef) and num(users) and x.get('installs_from'):
                days = diff(x['installs_from'], x['installs_to']) + 1
                return users * (now - bef) / max(1, days), 'wapas'
            if m == 'returning_dau' and num(now) and num(bef):
                return now - bef, 'wapas'
        return None, None

    def sev_of(x):
        fam = x.get('family')
        if fam in ('impact', 'impact_late'):
            lv = {'halt': 'bigda', 'hold': 'dhyan', 'win': 'behtar'}.get(x.get('level'))
            if lv:
                return lv
        if fam == 'rate_zero':
            return 'dhyan'
        s = x.get('severity')
        return 'bigda' if s in ('warning', 'critical') else ('behtar' if s == 'good' else ('dhyan' if s == 'watch' else 'normal'))

    def metric_of(x):
        fam = x.get('family')
        if fam == 'cohort':
            return 'D%d' % int(x.get('n') or 0)
        if fam in ('impact', 'impact_late'):
            rows = (x.get('rows') or {})
            return (rows.get('worse') or rows.get('better') or [''])[0]
        return fam

    def pack_alert(x, closed=False):
        ap = apps[idx_of[x['app_id']]] if x.get('app_id') in idx_of else None
        ppl, kind = people(x, ap)
        arp = arpdau28(ap) if ap else None
        rel = x.get('release') or {}
        return {
            'id': x.get('id'), 'a': idx_of.get(x.get('app_id'), -1), 'fam': x.get('family'), 'm': metric_of(x),
            'sev': sev_of(x), 'dir': x.get('dir'), 'n': x.get('n'), 'now': r3(x.get('now')), 'bef': r3(x.get('before')),
            'unit': x.get('unit'), 'users': x.get('users'), 'if': x.get('installs_from'), 'it': x.get('installs_to'),
            'bf': x.get('base_from'), 'bt': x.get('base_to'), 'since': x.get('since'), 'day': x.get('day'),
            'at': x.get('opened_at') or x.get('alert_at'), 'seeded': bool(x.get('seeded')), 'opened': x.get('opened'),
            'prov': bool(x.get('provisional')), 'est': bool(x.get('estimate')), 'started': x.get('started'),
            'cap': bool(x.get('started_cap')), 'dt': x.get('data_till'), 'vs': x.get('vs') or [],
            'rl': rel.get('label'), 'rd': rel.get('date'), 'lv': x.get('level'), 'tx': x.get('text') or '',
            'ppl': None if ppl is None else round(ppl, 1), 'kind': kind,
            'usd': None if (ppl is None or kind != 'gaye' or not arp) else round(ppl * arp, 3),
            'closed': x.get('closed') if closed else None, 'cr': x.get('close_reason') if closed else None,
            'cat': x.get('closed_at') if closed else None,
        }

    alerts = [pack_alert(x) for x in open_alerts if x.get('app_id') in idx_of]
    for a in ga:
        for x in a.get('alerts_closed') or []:
            if x.get('close_reason') != 'recovered' or not x.get('closed'):
                continue
            if diff(x['closed'], today) > 7 or x.get('severity') not in ('warning', 'watch'):
                continue
            if x.get('opened') and x['closed'] <= x['opened']:
                continue
            if size_of(a['app_id']) == 'chhoti':
                continue
            alerts.append(pack_alert(dict(x, app_id=a['app_id']), closed=True))

    noga = []
    for x in U.get('no_ga4') or []:
        nm = names.get(x.get('app_id'), {})
        noga.append({'id': x.get('app_id'), 'nm': nm.get('name') or x.get('app'), 'acc': nm.get('acct', ''),
                     'sz': size_of(x.get('app_id')), 'paisa': round(paisa.get(x.get('app_id'), 0), 2),
                     'why': x.get('text') or 'GA4 data nahi'})

    for ap in apps:
        cols = ap.pop('raw')
        for k, arr in cols.items():
            e = enc(arr)
            assert dec(e) == arr, k
            ap[k] = e
    for al in alerts:
        al.pop('id', None)

    meta = {
        'cohCols': COH_COLS, 'S': S, 'E': E, 'n': SPAN, 'today': today, 'gen': gen, 'fx': round(fx, 4), 'late': late, 'lag': lag,
        'actLate': act_late, 'settled': settled_min, 'apps': len(apps), 'noga': len(noga),
        'portfolioSettled': dash['active'].get('settled_till_min'),
    }
    data = {'meta': meta, 'apps': apps, 'alerts': alerts, 'noga': noga}
    return data
