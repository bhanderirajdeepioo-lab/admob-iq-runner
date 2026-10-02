"""🧭 Active users Studio — the Active users tab's All-apps view (the owner-approved "Active users Studio" design), build
step.

ONE compact lazy file, site/active_studio.json.gz, with exactly the data the page's Studio needs — every number of the
Studio (the "Users ka farak" lens, the KPIs, the map, "Installs vs asli", the timeline, "What changed?", the apps table,
the app drawer) is worked out in the browser from it, for any range / compare the viewer picks:

  * per app, SPAN days (ending on the latest GA4 day EVERY app has, so all apps are pooled on the same days) of compact
    integer arrays (enc): active users (a1), installs (nw), returning users (rt — never on the engine's tracking-check
    days), the recent installs coming back that day (y), came back on day 1 / 7 / 30 per install day (d1 / d7 / d30),
    AdMob revenue ×1000 (rv), the returning users' sessions (su, ×1000 per user) and seconds (tu) per user and their
    count (u), ads per active user ×1000 (im); the installs of the 31 days before the span (pre); the engine's normal
    band for the newest BAND_DAYS days (bnd);
  * per app: its per-day return curve (sh, the engine's split weights), the lens' own noise at the 91 earlier ends for a
    grid of window lengths (nz — the "pakka" test), the engine's install-week × day grid (tri — EVERY install week since
    the app's start, as the older "How many came back" table: weeks without data / with part data flagged), ALL its
    updates up to the span's end (📦, with the engine's verdict level), size class (badi / madhyam / chhoti: AdMob earnings + Google Ads spend a day), the
    engine's fast-change runs (steep) and the dashboard summary row's alert counts;
  * every open Active users alert, the ones closed in the last 7 days and the engine's installs / ad-price info rows;
  * the apps without GA4 data, and meta (the span, today, the build time, fx, the late / lag days, H0 = the oldest day
    any app's data has, hist = the older days' file).

The days BEFORE the span (back to H0: the owner, 2 Oct, "no trim" — a custom range / compare reaches the whole history)
go to a second file, site/active_studio_old.json.gz = {v, S: H0, n: its days, gen, apps: {app id: the same compact
arrays + pre (the 31 days of installs before H0) + stp (the fast-change runs before the span)}} — sliced from the very
same per-app series, so old + span = one series, cell for cell. The page loads it only when a chosen range or compare
needs a day before the span (the first load stays the span's small file).

It reads what the Uninstall step (Active users inside it) wrote this build — active_<key>.json.gz, the All-apps daily
file (DATA.active.portfolio) and uninstall.json.gz's lag — and the dashboard (in memory — exactly what dashboard.json.gz
will hold): the same inputs the approved demo generator read from the site, with the same arithmetic
(tests/active_studio_reference.py is that generator's data step, frozen: the parity test). No GA4 / AdMob call, no
alert, no notification. Nothing is trimmed, sampled or capped: every app, alert and day the generator kept.

  run(dashboard, out_dir, cfg_dir, s) → the site file names (for _headers); sets dashboard["active"]["studio"] =
  {"file", "v"} (the page shows the Studio only with it). off(out_dir): the switch (repo variable ACTIVE_STUDIO=false)
  — the file removed, no pointer, nothing printed: the site exactly as without the feature.

Failure-isolated: an app whose file is missing or broken is left out (counted); any other failure costs the Studio
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

FILE = "active_studio.json.gz"
HFILE = "active_studio_old.json.gz"   # the days before the span (loaded by the page only when a range needs them)
V = 1                 # the file's format (the page refuses another)
SPAN = 180            # days per app: 60-day range + 60-day compare + its 28-day normal + 30 install lags
BAND_DAYS = 70        # engine normal band kept only for the newest days (trend sparks, drawer chart)
LG = [1, 2, 3, 4, 5, 7, 11, 14, 21, 27, 42, 57]   # window lengths (settled days) of the noise grid
NULL_DAYS = 91        # 13 weeks of earlier ends (engine NULL_WEEKS)
NULL_MIN = 21
SIGMA_FLOOR = 0.01
SPREAD = 1.2533
TRI_COLS = [1, 3, 7, 14, 30]
MAX_GZ = 1500000      # a hard cap far above the ~90 KB a 27-app portfolio takes: past it the file is not written
                      # (counted, never a silent half file and never a trimmed one) — the page keeps its older views
LINE = None           # this build's counts line (build_static prints it)


def enabled(s):
    return bool((s or {}).get("active_studio", True))


# ---- dates / numbers (the demo generator's helpers) --------------------------------------------------------------
def _k1000(p):
    """A share (the engine's 4 decimals) ×1000, half rounded UP — as the older table prints it (0.0545 → 55 → "5.5%",
    never Python's half-to-even 54 → "5.4%")."""
    return int(math.floor(round(p * 1000, 6) + 0.5))


def D(s):
    return date.fromisoformat(s[:10])


def add(s, n):
    return (D(s) + timedelta(days=n)).isoformat()


def diff(a, b):
    return (D(b) - D(a)).days


def num(v):
    return (v is not None and isinstance(v, (int, float)) and not isinstance(v, bool)
            and not (isinstance(v, float) and math.isnan(v)))


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


def med(v):
    v = sorted(v)
    n = len(v)
    return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2) if n else None


def spread(v):
    if len(v) < NULL_MIN:
        return None
    c = med(v)
    return max(SPREAD * sum(abs(x - c) for x in v) / len(v), SIGMA_FLOOR)


# ---- the lens (Python mirror of the page's lens(): the noise grid) ------------------------------------------------
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
def build_data(dash, PF, load, accn, appn, lag=2, counts=None):
    """dash = the dashboard (as dashboard.json.gz holds it), PF = the All-apps daily file (active_portfolio.json.gz),
    load(name) → a site file's JSON (active_<key>; raises when missing / broken), accn / appn = the account / app names
    files, lag = the Uninstall step's lag days → the Studio's data {meta, apps, alerts, noga} (compact arrays encoded),
    or None (no app to show). counts (optional dict): apps / skipped."""
    counts = counts if counts is not None else {}
    AC = dash.get('active') or {}
    fx = float(dash.get('usd_inr') or 83)
    today = dash['today_date']
    gen = dash['generated_at']
    K_ = AC.get('consts') or {}
    act_late = int(K_.get('act_late_days', 3))

    # ---- app names: "<store name> · <account>", never cut (same rule as Uninstall Studio) --------------------------
    cat = {c['app_id']: c for c in dash.get('apps_catalog') or [] if isinstance(c, dict) and c.get('app_id')}
    launch_by = {r['app_id']: r.get('launch_day') for r in AC.get('apps') or [] if isinstance(r, dict) and r.get('app_id')}
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
    rows = [r for r in AC.get('apps') or [] if isinstance(r, dict) and r.get('status') != 'error' and r.get('file')
            and isinstance(r.get('data_till'), str) and r.get('app_id')]
    if not rows:
        counts.update(apps=0, skipped=0)
        return None
    E = min(r['data_till'] for r in rows)
    S = add(E, -(SPAN - 1))
    SET = min(r.get('settled_till') or E for r in rows)    # common settled day
    pf_by = {a['app_id']: a for a in (PF or {}).get('apps') or [] if isinstance(a, dict) and a.get('app_id')}

    apps, skipped = [], 0
    for r in sorted(rows, key=lambda z: names.get(z['app_id'], {}).get('name', z.get('app'))):
        try:
            apps.append(_app(r, names, size_of, paisa, pf_by, load, E, S, SET))
        except Exception:
            skipped += 1                  # this app's file missing / broken: left out (counted), never the Studio
    counts.update(apps=len(apps), skipped=skipped)
    if not apps:
        return None
    idx_of = {x['id']: i for i, x in enumerate(apps)}
    H0 = min([S] + [x['_g0'] for x in apps])         # the oldest day any app's data has
    old = {}
    for x in apps:
        x.pop('_g0')
        mk = x.pop('_old')
        if diff(H0, S) > 0:
            c, pre, stp = mk(H0)
            old[x['id']] = dict({k: enc(v) for k, v in c.items()}, pre=enc(pre), stp=stp)

    # ---- alerts: open (DATA), recently closed, and the compact info rows (installs-only changes, ad price) -----------
    SEV = {'warning': 'bigda', 'watch': 'dhyan', 'good': 'behtar'}

    def pack(x, kind='open'):
        relx = x.get('release') or {}
        sp = x.get('sp')
        return {
            'a': idx_of.get(x.get('app_id'), -1), 'fam': x.get('family') or x.get('kind'), 'm': x.get('metric'),
            'sev': SEV.get(x.get('severity'), 'normal'), 'dir': x.get('dir'), 'now': x.get('now'), 'bef': x.get('before'),
            'rel': x.get('rel'), 'unit': x.get('unit'), 'users': x.get('users'), 'if': x.get('installs_from'),
            'it': x.get('installs_to'), 'bf': x.get('base_from'), 'bt': x.get('base_to'),
            'since': x.get('since') or x.get('from'), 'day': x.get('day'),
            'at': x.get('alert_at') or x.get('opened_at'), 'seeded': bool(x.get('seeded')), 'opened': x.get('opened'),
            'prov': bool(x.get('provisional') or x.get('prov')), 'est': bool(x.get('estimate')), 'started': x.get('started'),
            'dt': x.get('data_till') or x.get('to'), 'tags': x.get('tags') or [], 'rl': relx.get('label'),
            'rd': relx.get('date'),
            'sp': sp if (isinstance(sp, list) and sp and sp[0] == 'ret') else None,
            'net': (sp[1] if (isinstance(sp, list) and sp and sp[0] == 'pu' and len(sp) > 1) else None),
            'kind': kind, 'closed': x.get('closed'), 'cat': x.get('closed_at'), 'to': x.get('to'),
        }

    alerts = [pack(x) for x in AC.get('alerts') or [] if isinstance(x, dict) and x.get('app_id') in idx_of]
    for x in AC.get('closed') or []:
        if isinstance(x, dict) and x.get('app_id') in idx_of and x.get('closed') and diff(x['closed'], today) <= 7:
            alerts.append(pack(x, 'closed'))
    for x in AC.get('info') or []:
        if (isinstance(x, dict) and x.get('app_id') in idx_of and x.get('src') != 'older'
                and x.get('kind') in ('installs', 'price')):
            alerts.append(pack(x, 'info'))

    noga = []
    for x in AC.get('no_ga4') or []:
        if not isinstance(x, dict):
            continue
        nm = names.get(x.get('app_id'), {})
        noga.append({'id': x.get('app_id'), 'nm': nm.get('name') or x.get('app'), 'acc': nm.get('acct', ''),
                     'sz': size_of(x.get('app_id')), 'why': x.get('text') or 'GA4 data nahi'})

    for ap in apps:
        cols = ap.pop('raw')
        for k, arr in cols.items():
            e = enc(arr)
            if dec(e) != arr:
                raise ValueError('enc')
            ap[k] = e

    meta = {'S': S, 'E': E, 'n': SPAN, 'today': today, 'gen': gen, 'fx': round(fx, 4), 'actLate': act_late, 'lag': lag,
            'settled': SET, 'apps': len(apps), 'LG': LG, 'bandDays': BAND_DAYS, 'triCols': TRI_COLS,
            'pfSettled': (AC.get('portfolio') or {}).get('settled_till'), 'mk': ((AC.get('market') or {}).get('latest')),
            'H0': H0, 'hist': HFILE if diff(H0, S) > 0 else None}
    hist = ({'v': V, 'S': H0, 'n': diff(H0, S), 'gen': gen, 'apps': old} if diff(H0, S) > 0 else None)
    return {'meta': meta, 'apps': apps, 'alerts': alerts, 'noga': noga, '_hist': hist}


def _app(r, names, size_of, paisa, pf_by, load, E, S, SET):
    """One app's Studio entry (its compact arrays still raw: 'raw')."""
    aid = r['app_id']
    nmo = names.get(aid) or {'name': r['app'], 'store': r['app'], 'acct': ''}
    af = load(r['file'])
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
            for key, nk, dk, lst in (('se', 's', 'u', vse), ('tm', 't', 'u', vtm), ('rv', 'rv', 'a1', vrv),
                                     ('ad', 'imp', 'a1', vad)):
                a_ = ratio(X, nk, dk, w0, j)
                b_ = ratio(X, nk, dk, b0, b1)
                if a_ and b_ and a_ > 0 and b_ > 0:
                    lst.append(math.log(a_ / b_))
        for key, lst in (('t', vt), ('a', va), ('se', vse), ('tm', vtm), ('rv', vrv), ('ad', vad)):
            sg = spread(lst)
            nz[key].append(None if sg is None else int(round(sg * 1e4)))

    # ---- the span the page gets
    def sl(arr, f=None, lo=None, hi=None):
        out = []
        for i in range(i0s if lo is None else lo, (iE if hi is None else hi) + 1):
            v = arr[i] if 0 <= i < H else None
            out.append(None if v is None else (f(v, i) if f else int(round(v))))
        return out

    def cols_of(lo=None, hi=None):
        return {
            'a1': sl(X['a1'], None, lo, hi), 'nw': sl(X['nw'], None, lo, hi), 'rt': sl(X['rt'], None, lo, hi),
            'y': sl(X['y'], None, lo, hi), 'd1': sl(X['d1'], None, lo, hi), 'd7': sl(X['d7'], None, lo, hi),
            'd30': sl(X['d30'], None, lo, hi),
            'rv': sl(X['rv'], lambda v, i: int(round(v * 1000)), lo, hi),
            'u': sl(X['u'], None, lo, hi),
            'su': sl(X['s'], lambda v, i: int(round(v / X['u'][i] * 1000)) if X['u'][i] else None, lo, hi),
            'tu': sl(X['t'], lambda v, i: int(round(v / X['u'][i])) if X['u'][i] else None, lo, hi),
            'im': sl(X['imp'], lambda v, i: int(round(v / X['a1'][i] * 1000)) if X['a1'][i] else None, lo, hi),
        }

    def pre_of(i0):          # nw for the 31 lag days before day i0 (the oldest compare window's installs part)
        return [None if (i < 0 or i >= H or X['nw'][i] is None) else int(round(X['nw'][i])) for i in range(i0 - 31, i0)]

    cols = cols_of()
    pre = pre_of(i0s)

    def older(h0):
        """the days h0 .. S−1 (the older days' file): the same arrays, the 31 days of installs before h0, the
        fast-change runs before the span"""
        ih = diff(g0, h0)
        stp = [[max(f0, h0), min(t0, add(S, -1))] for f0, t0 in ((af.get('steep') or {}).get('ret_dau') or [])
               if f0 < S and t0 >= h0]
        return cols_of(ih, i0s - 1), pre_of(ih), stp
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

    # updates (📦) with the engine's verdict level — ALL of them up to the span's end (the owner: "no trim"): the
    # install-week grid draws its 📦 lines over the app's whole history, and a range reaches back as far as the data
    rel = []
    for u in (af.get('impact') or {}).get('updates') or []:
        if u.get('date') and u['date'] <= E:
            v = u.get('verdict') or {}
            rel.append([u['date'], u.get('label') or 'App update', v.get('level'), bool(v.get('final'))])
    seen = {x[0] for x in rel}
    for x in af.get('releases') or []:
        if x.get('date') and x['date'] <= E and x['date'] not in seen and not any(0 <= diff(z[0], x['date']) <= 3 for z in rel):
            rel.append([x['date'], ('v' + x['version']) if x.get('version') else 'App update', None, False])
            seen.add(x['date'])
    rel.sort()

    # return grid: EVERY install week (newest first) × day 1 / 3 / 7 / 14 / 30 — the engine's tri rows, all of them since
    # the app's start (the test installs before a launch stay out, as the older table hides them); a week with no
    # return data from GA4 / part data / GA4's old limit unchecked gets a 6th item, flags: 1 no data · 2 part · 4 '?'
    tw = []
    for row in (tri.get('rows') or []):
        if row.get('pre') or not row.get('from') or not row.get('to'):
            continue
        v = row.get('v') or []
        pv = row.get('prov') or []
        nd = bool(row.get('nodata'))
        vals = [None if nd else (_k1000(v[k]) if k < len(v) and num(v[k]) else None) for k in TRI_COLS]
        bits = 0 if nd else int(''.join('1' if (k < len(pv) and pv[k]) else '0' for k in TRI_COLS), 2)
        w = [row.get('from'), row.get('to'), row.get('users'), enc(vals), bits]
        fl = (1 if nd else 0) | (2 if row.get('part') else 0) | (4 if row.get('q') else 0)
        tw.append(w + [fl] if fl else w)
    tw.sort(key=lambda z: z[0], reverse=True)                # (newest first, as the older table)
    ref = tri.get('ref') or []
    tref = [_k1000(ref[k]) if k < len(ref) and num(ref[k]) else None for k in TRI_COLS]

    T = af.get('tiles') or {}
    st_rng = []
    for f0, t0 in ((af.get('steep') or {}).get('ret_dau') or []):
        if t0 >= S:
            st_rng.append([max(f0, S), t0])
    fl = af.get('flags') or {}
    return {
        'id': aid, 'k': r['key'], 'nm': nmo['name'], 'store': nmo.get('stag') or nmo['store'], 'acc': nmo['acct'],
        'sz': size_of(aid), 'paisa': round(paisa.get(aid, 0), 2),
        'first': add(g0, first), 'settled': r.get('settled_till') or SET, 'dt': r.get('data_till') or E,
        'stage': af.get('stage'), 'ready': bool(r.get('ready')), 'rs': (r.get('edges') or {}).get('ret_state'),
        'vs': (r.get('edges') or {}).get('rev_state'), 'est': bool(fl.get('rev_est') or fl.get('tz_blend')),
        'pkg': '', 'K': X['K'], 'sh': enc([int(round(x * 1e5)) for x in (X['sh'] or [])]),
        'nz': nz, 'u1': (T.get('d1') or {}).get('usual'), 'u7': (T.get('d7') or {}).get('usual'),
        'tst': (T.get('ret_dau') or {}).get('st'), 'steep': st_rng,
        'raw': cols, 'pre': enc(pre), 'bnd': bnd, 'rel': rel, '_g0': g0, '_old': older,
        'tri': {'w': tw, 'ref': enc(tref)},
        'al': (r.get('alerts') or {}),
    }


# ---- the build step -----------------------------------------------------------------------------------------------
def _remove(out_dir, which=(FILE, HFILE)):
    for f in which:
        try:
            os.remove(os.path.join(out_dir, f))
        except OSError:
            pass


def _lag(dashboard, out_dir):
    """The Uninstall step's lag days (its file's consts; 2 when it is not there) — the demo generator's own rule."""
    try:
        uni = dashboard.get("uninstall") or {}
        return int((_gz(os.path.join(out_dir, uni.get("asset") or "uninstall.json.gz")).get("consts") or {})
                   .get("lag_days", 2))
    except Exception:
        return 2


def run(dashboard, out_dir, cfg_dir, s=None):
    """The Studio's file for this build → [FILE] (for _headers), or [] (nothing to show: no Active users data this
    build, or a failure — the file removed, no pointer). Sets dashboard["active"]["studio"] last. Never raises."""
    global LINE
    LINE = None
    act = dashboard.get("active") if isinstance(dashboard, dict) else None
    if not isinstance(act, dict):
        _remove(out_dir)                       # (an old file never outlives the tab's own data)
        return []
    act.pop("studio", None)                    # (the pointer only ever names THIS build's file)
    try:
        port = act.get("portfolio")
        PF = _gz(os.path.join(out_dir, port["file"])) if isinstance(port, dict) and port.get("file") else None
        accn = _raw_json(os.path.join(cfg_dir, "account_names.json"))
        appn = _raw_json(os.path.join(cfg_dir, "app_names.json"))
        counts = {}
        data = None
        if PF is not None:                     # (no All-apps daily file this build: nothing the Studio can pool)
            data = build_data(dashboard, PF, lambda n: _gz(os.path.join(out_dir, n)), accn, appn,
                              _lag(dashboard, out_dir), counts)
        if data is None:
            _remove(out_dir)
            LINE = "active studio: apps 0, skipped %d, alerts 0, no ga4 0, kb 0, older days kb 0" % counts.get("skipped", 0)
            return []
        hist = data.pop("_hist", None)
        hgz = 0
        if hist is not None:                   # the days before the span: their own file (a size cap of its own — past
            hraw = json.dumps(hist, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
            hgz = len(gzip.compress(hraw, 9, mtime=0))     # it the span's file stands alone: ranges stop at the span)
            if hgz > MAX_GZ:
                hist, hgz = None, 0
        if hist is None:
            data["meta"].update(H0=data["meta"]["S"], hist=None)
        body = dict(data, v=V)
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        gz = len(gzip.compress(raw, 9, mtime=0))
        if gz > MAX_GZ:
            _remove(out_dir)
            LINE = "active studio: too big (%d kb), not written" % (gz // 1024)
            return []
        write_json_gz_stable(os.path.join(out_dir, FILE), body)
        if hist is not None:
            write_json_gz_stable(os.path.join(out_dir, HFILE), hist)
        else:
            _remove(out_dir, (HFILE,))
        act["studio"] = {"file": FILE, "v": hashlib.sha1(raw).hexdigest()[:12]}
        LINE = ("active studio: apps %d, skipped %d, alerts %d, no ga4 %d, kb %d, older days kb %d"
                % (len(data["apps"]), counts.get("skipped", 0), len(data["alerts"]), len(data["noga"]), gz // 1024,
                   hgz // 1024))
        return [FILE, HFILE] if hist is not None else [FILE]
    except Exception as e:
        act.pop("studio", None)
        _remove(out_dir)
        LINE = None
        print("active studio skipped: %s" % type(e).__name__, file=sys.stderr)
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
