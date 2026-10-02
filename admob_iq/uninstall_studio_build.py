"""🧭 Uninstall Studio — the Uninstall tab's All-apps view (the owner-approved "Uninstall Studio" design), build step.

ONE compact lazy file, site/uninstall_studio.json.gz, with exactly the data the page's Studio needs — every number of
the Studio (the "Nuksaan" loss lens, the KPIs, the map, "Kahan se aaya", the timeline, "Kya badla?", the apps table,
the app drawer) is worked out in the browser from it, for any range / compare the viewer picks:

  * per app, SPAN days (ending on the latest GA4 day EVERY app has, so all apps are pooled on the same days) of compact
    integer arrays (enc): installs (nw), uninstalls (un), the rate's 28-day active users (a28 — only on the days the
    engine's daily rate is valid), the engine's normal band ×1000 (md / lo / hi), uninstalls ON install day (g0) and
    exactly L days after install (c1..c7) per install day, next-day returners (r1), AdMob revenue in cents (rv) and
    active users (a1) for the revenue per user;
  * "Gone by day N" — its own block gt = {cols, apps: {app id: …}} (see _gtable): per app and day N (GT_COLS), the
    engine's own checkpoint numbers — the ALL-TIME share of installs gone by day N (the dashboard table's "All time"),
    the LATEST final week (the engine's settled comparison: its newest install days whose day N is pakka) and the 4
    weeks before it, with counts, dates and the engine's alert / arrow — not tied to the range;
  * per app: its install-week × day grid (% still installed, ×1000) — EVERY install week since the app's history start
    (its launch, or the oldest day of data), never only the newest ones — + the engine's all-time reference row, ALL its
    updates up to the span's end (📦, with the engine's verdict level — the grid's 📦 lines reach its oldest week), size class (badi / madhyam / chhoti: AdMob earnings + Google Ads spend a day),
    the engine's own verdict kind and the dashboard summary row's alert counts;
  * every open uninstall alert (with its alert time / Badlaav shuru / data window) + the recently recovered ones;
  * the apps without GA4 data, and meta (the span, today, the build time, fx, the late / lag days).

It reads what the Uninstall step wrote this build (uninstall.json.gz, uninstall_c_<key>.json.gz, active_<key>.json.gz)
and the dashboard (in memory — exactly what dashboard.json.gz will hold) — the same inputs the approved demo generator
read from the site, with the same arithmetic (tests/studio_reference.py is that generator's data step, frozen: the
parity test). No GA4 / AdMob call, no alert, no notification.

  run(dashboard, out_dir, cfg_dir, s) → the site file names (for _headers); sets dashboard["uninstall"]["studio"] =
  {"file", "v"} (the page shows the Studio only with it). off(out_dir): the switch (repo variable UNINSTALL_STUDIO=false)
  — the file removed, no pointer, nothing printed: the site exactly as without the feature.

Failure-isolated: an app whose files are missing or broken is left out (counted); any other failure costs the Studio
only (no file, no pointer — the page then shows the older All-apps views). PRIVACY: the log line has counts only.
"""

import gzip
import hashlib
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

from .db import write_json_gz_stable

FILE = "uninstall_studio.json.gz"
V = 1                 # the file's format (the page refuses another)
SPAN = 156            # days per app: 60-day range + 60-day compare + 35 days of 'normal' before the compare
COH_COLS = [0, 1, 3, 7, 14, 30, 60, 90]
GT_COLS = [0, 1, 3, 7, 14, 30, 45, 60, 90]   # "Gone by day N" (the owner's columns; 0 = the same day as the install)
GT_LAGS = 90          # (the cohort cells read: lags 0..90 per install day)
MAX_GZ = 1500000      # a hard cap far above the ~300 KB target: past it the file is not written (counted, never a
                      # silent half file) — the page then keeps its older All-apps views
LINE = None           # this build's counts line (build_static prints it)


def enabled(s):
    return bool((s or {}).get("uninstall_studio", True))


# ---- dates / numbers (the demo generator's helpers) --------------------------------------------------------------
def D(s):
    return date.fromisoformat(s[:10])


def add(s, n):
    return (D(s) + timedelta(days=n)).isoformat()


def diff(a, b):
    return (D(b) - D(a)).days


def num(v):
    return v is not None and isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))


def r3(v):
    return None if not num(v) else round(v, 5)


# compact integer arrays: delta from the previous non-null value, zigzag, 5-bit groups as text
# ('A'..'Z','a'..'f' = last group; 'g'..'z','0'..'9','-','_' = more groups follow), '~' = null
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


def _gz(path):
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        return json.load(f)


def _raw_json(path):
    """A config file as the site serves it (build_static copies it verbatim) — {} when missing / broken."""
    try:
        with open(path, encoding='utf-8') as f:
            v = json.load(f)
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


# ---- the data (the demo generator's data step, on the build's own inputs) ----------------------------------------
def build_data(dash, U, load, accn, appn, counts=None):
    """dash = the dashboard (as dashboard.json.gz holds it), U = uninstall.json.gz, load(name) → a site file's JSON
    (uninstall_c_<key> / active_<key>; raises when missing), accn / appn = the account / app names files → the
    Studio's data {meta, apps, alerts, noga, gt} (compact arrays encoded). counts (optional dict): apps / skipped / gt
    (the apps with their "Gone by day N" block)."""
    counts = counts if counts is not None else {}
    fx = float(dash.get('usd_inr') or 83)
    today = dash['today_date']
    gen = dash['generated_at']
    K = U.get('consts') or {}
    late, lag = int(K.get('late_days', 7)), int(K.get('lag_days', 2))
    ACT = dash.get('active') or {}
    AK = ACT.get('consts') or {}
    act_late = int(AK.get('act_late_days', 3))

    # ---- app names: "<store name> · <account>" (the dashboard's smpApps rule), never cut --------------------------
    cat = {c['app_id']: c for c in dash.get('apps_catalog') or [] if isinstance(c, dict) and c.get('app_id')}
    launch_by = {}
    for r in ACT.get('apps') or []:
        if isinstance(r, dict) and r.get('app_id') and r.get('launch_day'):
            launch_by[r['app_id']] = r['launch_day']
    for a in U.get('apps') or []:
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

    # ---- size (smpApps): AdMob kamai/day over the last 7 finished days + Google Ads spend/day ---------------------
    y = dash.get('latest_complete') or add(today, -1)
    w7 = {add(y, -i) for i in range(7)}
    k7 = defaultdict(float)
    for p in dash.get('placements') or []:
        if not isinstance(p, dict):
            continue
        if p.get('country') and p['country'] != 'All':
            continue
        aid = by_dname.get(p.get('app'))
        if not aid:
            continue
        for r in p.get('daily') or []:
            if isinstance(r, (list, tuple)) and len(r) > 1 and r[0] in w7 and num(r[1]):
                k7[aid] += r[1] / 1e6 / 7
    spend = defaultdict(float)
    VAL = dash.get('value') or {}
    for v in VAL.get('apps') or []:
        if not isinstance(v, dict) or not v.get('app_id'):
            continue
        s = float(((v.get('cpi') or {}).get('spend4_src')) or 0) / 28
        if s <= 0:
            continue
        src = v.get('src_ccy') or VAL.get('spend_ccy') or 'INR'
        spend[v['app_id']] = s / fx if src == 'INR' else s
    paisa = {aid: k7[aid] + spend[aid] for aid in names}

    def size_of(aid):
        p = paisa.get(aid, 0)
        return 'badi' if p >= 300 else ('chhoti' if p < 30 else 'madhyam')

    # ---- common end: the latest GA4 day every app has ------------------------------------------------------------
    ga = [a for a in U.get('apps') or [] if a.get('data_till') and a.get('daily')]
    if not ga:
        return None
    E = min(a['data_till'] for a in ga)
    S = add(E, -(SPAN - 1))
    settled_min = min(a.get('settled_till') or E for a in ga)

    UNS = dash.get('uninstall') or {}
    srow = {x['app_id']: x for x in UNS.get('apps') or [] if isinstance(x, dict) and x.get('app_id')}
    open_alerts = UNS.get('alerts') or []

    apps = []
    skipped = 0
    for a in sorted(ga, key=lambda z: names.get(z['app_id'], {}).get('name', z['app'])):
        try:
            apps.append(_app(a, names, size_of, paisa, srow, load, E, S))
        except Exception:
            skipped += 1                  # this app's files missing / broken: left out (counted), never the Studio
    counts.update(apps=len(apps), skipped=skipped)
    if not apps:
        return None
    idx_of = {x['id']: i for i, x in enumerate(apps)}

    # ---- alerts: the open ones (DATA) + the recently recovered ones ("Theek ho gaya") ----------------------------
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

    alerts = [pack_alert(x) for x in open_alerts if isinstance(x, dict) and x.get('app_id') in idx_of]
    for a in ga:
        if a['app_id'] not in idx_of:
            continue
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

    gone = {'cols': GT_COLS, 'apps': {}}                    # "Gone by day N": its own block, by app id
    for ap in apps:
        g = ap.pop('_gt', None)
        if g is not None:
            gone['apps'][ap['id']] = g
    counts.update(gt=len(gone['apps']))
    for ap in apps:
        cols = ap.pop('raw')
        for k, arr in cols.items():
            e = enc(arr)
            if dec(e) != arr:
                raise ValueError('enc')
            ap[k] = e
    for al in alerts:
        al.pop('id', None)

    meta = {
        'cohCols': COH_COLS, 'S': S, 'E': E, 'n': SPAN, 'today': today, 'gen': gen, 'fx': round(fx, 4), 'late': late,
        'lag': lag, 'actLate': act_late, 'settled': settled_min, 'apps': len(apps), 'noga': len(noga),
        'portfolioSettled': ACT.get('settled_till_min'),
    }
    return {'meta': meta, 'apps': apps, 'alerts': alerts, 'noga': noga, 'gt': gone}


def _app(a, names, size_of, paisa, srow, load, E, S):
    """One app's Studio entry (its compact arrays still raw: 'raw')."""
    aid = a['app_id']
    nmo = names.get(aid) or {'name': a['app'], 'store': a['app'], 'acct': '', 'acc_id': ''}
    Dy = a['daily']
    st = Dy['start']
    den = Dy.get('a1') if (a.get('den') == 'dau' and Dy.get('a1')) else Dy.get('a28')
    brk = {diff(st, b) for b in (Dy.get('breaks') or [])}

    def g(k, i):
        arr = Dy.get(k)
        if arr is None or i < 0 or i >= len(arr):
            return None
        v = arr[i]
        return v if num(v) else None

    L = a.get('launch') or {}
    first = L['day'] if (L.get('hidden') and L.get('day')) else (a.get('history_start') or st)

    # cohort file → gone-by-day-N per install day
    c = load('uninstall_c_%s.json.gz' % a['key'])
    cst, cnew, lags = c['start'], c['new'], c['lags']
    cend = c.get('end') or E

    def cum(i, N):
        return sum(cnt for lg, cnt in (lags[i] or []) if lg <= N)

    def at(i, N):   # uninstalls exactly N days after install
        return sum(cnt for lg, cnt in (lags[i] or []) if lg == N)

    # active file → active users, revenue, next-day returners (Active users off: none of them)
    try:
        act = load('active_%s.json.gz' % a['key'])
    except Exception:
        act = {}
    AD = act.get('daily') or {}
    ast = AD.get('start') or S
    aok = (AD.get('coh') or {}).get('ok') or []
    ad1 = (AD.get('coh') or {}).get('d1') or []
    anew = AD.get('new') or []
    ret_from = ((act.get('edges') or {}).get('ret_from')) or AD.get('start') or S
    aset = act.get('settled_till') or a.get('settled_till')

    cols = {k: [] for k in ('nw', 'un', 'a28', 'md', 'lo', 'hi', 'g0', 'c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'r1',
                            'rv', 'a1')}
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
            for Lg in range(1, 8):
                cols['c%d' % Lg].append(at(ci, Lg) if age >= Lg else None)
        else:
            cols['g0'].append(None)
            for Lg in range(1, 8):
                cols['c%d' % Lg].append(None)
        ai = diff(ast, day)
        r1 = None
        if 0 <= ai < len(aok) and aok[ai] == 1 and day >= ret_from:
            an = anew[ai] if ai < len(anew) else None
            v1 = ad1[ai] if ai < len(ad1) else None
            if num(an) and an > 0 and num(v1):
                r1 = int(v1)
        cols['r1'].append(r1)
        rv = AD['rev'][ai] if 0 <= ai < len(AD.get('rev') or []) else None
        cols['rv'].append(int(round(rv * 100)) if num(rv) else None)
        a1 = AD['a1'][ai] if 0 <= ai < len(AD.get('a1') or []) else None
        cols['a1'].append(int(a1) if num(a1) else None)

    # updates (📦) with the engine's verdict level — ALL of them up to the span's end (the owner: "no trim"): the
    # install-week grid draws its 📦 lines over the app's whole history, and a range reaches back as far as the data
    rel = []
    for u in (a.get('impact') or {}).get('updates') or []:
        if u.get('date') and u['date'] <= E:
            v = u.get('verdict') or {}
            rel.append([u['date'], u.get('label') or 'App update', v.get('level'), bool(v.get('final'))])
    seen = {r[0] for r in rel}
    for r in a.get('releases') or []:
        if r.get('date') and r['date'] <= E and r['date'] not in seen and not any(0 <= diff(x[0], r['date']) <= 3 for x in rel):
            rel.append([r['date'], ('v' + r['version']) if r.get('version') else 'App update', None, False])
    rel.sort()

    # install-week × day-since-install: % still installed — EVERY ISO week from the one the app's history starts in
    # (its launch / the oldest cohort day) to the newest, as the older "Install week × day" table shows them
    lastMon = add(E, -D(E).weekday())
    f_all = max(first, cst)
    firstMon = add(f_all, -D(f_all).weekday())
    weeks = []
    for w in range(diff(firstMon, lastMon) // 7, -1, -1):
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
        prov = [1 if (add(t0, N) > (a.get('settled_till') or E) and row[k] is not None) else 0
                for k, N in enumerate(COH_COLS)]
        weeks.append({'w': ws, 'f': f0, 't': t0, 'n': n, 'v': row, 'p': prov,
                      'part': 1 if (f0 != ws or t0 != we) else 0})
    tri = a.get('triangle') or {}
    tcols, tref = tri.get('cols') or [], tri.get('ref') or []
    ref = []
    for N in COH_COLS:
        if N in tcols and tcols.index(N) < len(tref) and num(tref[tcols.index(N)]):
            ref.append(int(round((1 - tref[tcols.index(N)]) * 1000)))
        else:
            ref.append(None)

    # "Gone by day N" (its own block of the file, see _gtable; a failure costs only this app's block)
    try:
        gt = _gtable(a, c)
    except Exception:
        gt = None

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
    return {
        'id': aid, 'k': a['key'], 'nm': nmo['name'], 'store': nmo['store'], 'acc': nmo['acct'],
        'sz': size_of(aid), 'paisa': round(paisa.get(aid, 0), 2),
        'first': first, 'settled': a.get('settled_till') or E, 'aset': aset, 'retFrom': ret_from,
        'stage': a.get('stage'), 'ready': bool(sr.get('ready', True)), 'vk': vk, 'pkg': a.get('package') or '',
        'ac': sr.get('alerts') or {},
        'raw': cols, 'rel': rel, '_gt': gt,
        'coh': {'ref': ref, 'w': [[w['w'], w['n'], enc(w['v']), int(''.join(map(str, w['p'])) or '0', 2), w['f'], w['t']]
                                  if w['part'] else [w['w'], w['n'], enc(w['v']), int(''.join(map(str, w['p'])) or '0', 2)]
                                  for w in weeks]},
    }


# ---- "Gone by day N" ----------------------------------------------------------------------------------------------
def _engine_cd(a, c):
    """The engine's cohort data for one app, as evaluate_app builds it, from its cohort file c (the cells the engine
    reads: uninstall_c_<key>, written from the same fill_days store) and its detail a: cumulative uninstalls by lag
    (0..GT_LAGS), the incomplete days, the tracking breaks (engine mark_breaks: nb / ni / lmat), cut at the launch the
    engine cuts at (test installs before it never counted)."""
    from .engine import uninstall as eng
    hs, new, lags = c['start'], c['new'], c['lags']
    H = len(new)
    n = [int(v or 0) for v in new]
    raw, cum = [], []
    for i in range(H):
        r = {int(lg): int(u) for lg, u in (lags[i] or []) if 0 <= int(lg) <= H - 1 - i}
        raw.append(r)
        row, run = [], 0
        for lg in range(min(H - 1 - i, GT_LAGS) + 1):
            run += r.get(lg, 0)
            row.append(run)
        cum.append(row)
    inc = sorted({diff(hs, d) for d in ((a.get('flags') or {}).get('incomplete_days') or {}) if 0 <= diff(hs, d) < H})
    broken = [False] * H
    for b in ((a.get('daily') or {}).get('breaks') or []):
        if 0 <= diff(hs, b) < H:
            broken[diff(hs, b)] = True
    whole = {'hs': D(hs), 'E': D(c.get('end') or add(hs, H - 1)), 'H': H, 'n': n, 'cum': cum, 'raw': raw, 'inc': inc,
             'est': {}, 'addc': {}, 'flags': {}}
    eng.mark_breaks(whole, broken)
    L = a.get('launch') or {}
    i0 = max(0, min(H, diff(hs, L['day']))) if (L.get('hidden') and L.get('day')) else 0
    return eng.mark_breaks(eng.cut_cohorts(whole, i0), broken[i0:]) if i0 else whole


def _gtable(a, c):
    """One app's "Gone by day N" block → {"since": the first install day counted (launch / data start), "cap": the store's
    history is capped (older GA4 data not kept), "c": per GT_COLS one cell or None (no install day's day N is pakka yet)}.
    A cell (counts exact, dates ISO; x = uninstalled by day N, n = installs, k = install days):
      a   all time  [x, n, from, to, k] — the engine table's own "All time" (table[N].all, as the dashboard shows it); an
          app too young for it (the engine needs 8 weeks of install days): every pakka install day since the launch,
          and "ay": 1;
      r   latest    [x, n, from, to, k] — the engine's SETTLED comparison (compare(cd, N, late): its newest install days
          whose day N is final, an older stretch when incomplete days spoil them: "fb"); p = the 4 weeks before it;
      u   the engine table's own newer row when it shows one [x, n, from, to, k] (its newest install days, day N not
          final yet: the table shows them when they already rise, or by default) — what its arrow / alert is about;
      az / af  the engine's own test of that row vs all time: z (after the day-to-day swings) / 1 = a real change;
      ls  1 = the engine calls the latest sample too small; al = 1: an open engine alert at day N; d = the table's
          arrow ("up" / "down" / None); fb = [kind, newest days passed] when the latest fell back past spoiled days."""
    from .engine import uninstall as eng
    cd = _engine_cd(a, c)
    late = int(a['late_days']) if num(a.get('late_days')) else 7
    hs, H = cd['hs'].isoformat(), cd['H']
    tab = {r.get('n'): r for r in a.get('table') or [] if isinstance(r, dict)}
    w = lambda o, k='users': [int(o['x']), int(o[k]), o['from'], o['to']]   # noqa: E731
    cells = []
    for N in GT_COLS:
        if H - 1 - N - late < 0:
            cells.append(None)                              # no install day has a pakka day N yet
            continue
        s = eng.compare(cd, N, late=late)
        r = tab.get(N) or {}
        cell = {}
        al = r.get('all')
        if al and al.get('users') and al.get('from') and al.get('to'):
            x, n, k = eng._pool(cd, diff(hs, al['from']), diff(hs, al['to']), N, clean=True)
            if n != al['users'] or not n or abs(x / n - al['p']) > 6e-6:
                x, k = int(round(al['p'] * al['users'])), None   # (the table's own numbers win; never seen)
            cell['a'] = [int(x), int(al['users']), al['from'], al['to'], k]
            if num(al.get('z')):
                cell['az'] = round(float(al['z']), 2)          # the engine's own test of its row vs all time: z after
            if al.get('fires'):                                # the day-to-day swings, and "a real change" (fires)
                cell['af'] = 1
        else:
            top = H - 1 - N - late
            x, n, k = eng._pool(cd, 0, top, N, clean=True)
            if n:
                cell['a'] = [int(x), int(n), hs, add(hs, top), k]
                cell['ay'] = 1
        rec = s['recent']
        if rec.get('users'):
            cell['r'] = w(rec) + [int(rec['k'])]
        tr = r.get('recent') or {}
        if tr.get('users') and tr.get('from') and (tr.get('from'), tr.get('to')) != (rec.get('from'), rec.get('to')):
            nw = eng.compare(cd, N)['recent']               # the table's newer row (compare(cd, N): its own numbers)
            if (nw.get('from'), nw.get('to'), nw.get('users')) == (tr['from'], tr['to'], tr['users']):
                cell['u'] = w(nw) + [int(nw['k'])]
            elif num(tr.get('p')):
                cell['u'] = [int(round(tr['p'] * tr['users'])), int(tr['users']), tr['from'], tr['to'], tr.get('k')]
        if s.get('prev') and s['prev'].get('users'):
            cell['p'] = w(s['prev'])
        cell['ls'] = 1 if s.get('low_sample') else 0
        cell['al'] = 1 if r.get('alert') else 0
        cell['d'] = r.get('dir') if r.get('dir') in ('up', 'down') else None
        fb = s.get('fallback')
        if fb and fb.get('recent'):
            cell['fb'] = [fb.get('kind'), list(fb.get('days') or [])]
        cells.append(cell if ('a' in cell or 'r' in cell) else None)
    return {'since': hs, 'cap': bool(a.get('history_capped')), 'c': cells}


# ---- the build step -----------------------------------------------------------------------------------------------
def _remove(out_dir):
    try:
        os.remove(os.path.join(out_dir, FILE))
    except OSError:
        pass


def run(dashboard, out_dir, cfg_dir, s=None):
    """The Studio's file for this build → [FILE] (for _headers), or [] (nothing to show: no Uninstall data this build,
    or a failure — the file removed, no pointer). Sets dashboard["uninstall"]["studio"] last. Never raises."""
    global LINE
    LINE = None
    uni = dashboard.get("uninstall") if isinstance(dashboard, dict) else None
    if not isinstance(uni, dict):
        _remove(out_dir)                       # (an old file never outlives the tab's own data)
        return []
    uni.pop("studio", None)                    # (the pointer only ever names THIS build's file)
    try:
        U = _gz(os.path.join(out_dir, uni.get("asset") or "uninstall.json.gz"))
        accn = _raw_json(os.path.join(cfg_dir, "account_names.json"))
        appn = _raw_json(os.path.join(cfg_dir, "app_names.json"))
        counts = {}
        data = build_data(dashboard, U, lambda n: _gz(os.path.join(out_dir, n)), accn, appn, counts)
        if data is None:
            _remove(out_dir)
            LINE = "uninstall studio: apps 0, skipped %d, alerts 0, no ga4 0, kb 0" % counts.get("skipped", 0)
            return []
        body = dict(data, v=V)
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        gz = len(gzip.compress(raw, 9, mtime=0))
        if gz > MAX_GZ:
            _remove(out_dir)
            LINE = "uninstall studio: too big (%d kb), not written" % (gz // 1024)
            return []
        write_json_gz_stable(os.path.join(out_dir, FILE), body)
        uni["studio"] = {"file": FILE, "v": hashlib.sha1(raw).hexdigest()[:12]}
        LINE = ("uninstall studio: apps %d, skipped %d, alerts %d, no ga4 %d, kb %d"
                % (len(data["apps"]), counts.get("skipped", 0), len(data["alerts"]), len(data["noga"]), gz // 1024))
        return [FILE]
    except Exception as e:
        uni.pop("studio", None)
        _remove(out_dir)
        LINE = None
        print("uninstall studio skipped: %s" % type(e).__name__, file=sys.stderr)
        return []


def off(out_dir):
    """The switch off: the file removed (a rollback leaves the site as without the feature), no pointer, no line."""
    global LINE
    LINE = None
    _remove(out_dir)


def pop_line():
    """This build's counts line (None when the step did not run) — once."""
    global LINE
    line, LINE = LINE, None
    return line
