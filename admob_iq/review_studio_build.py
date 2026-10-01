"""🗂 Review Studio — the Review tab's Studio (the owner-approved "Review Studio" design), build step.

ONE lazy file per review day, site/review/studio/<day>.json.gz, built ONCE from that day's FROZEN card document
(data/review/days/<day>.json.gz — the cards the team reviews: the same-day rule) and the site files the review step
read (the dashboard's placements and app icons, the Uninstall cohort files, the Active users files, mediation_daily
.json), with everything the Studio page shows that the card document lacks:

  * per app: the 14-day AdMob revenue series (the last day pinned to the card's "Yesterday"), the weekly same-day
    uninstall series (8 install weeks, each with its actual count of installs and a ⏳ not-final flag), the daily
    returning users (42 days, with the day they are final till), the mediation network shares (every network, the
    card's 7 days vs the 7 before, with fill), the app icon (by app id) and late_days;
  * per feature: the owner's wording (short English labels, Hinglish explanations; never "100 me" / "per 1,000";
    "Same day uninstall"; the actual number first with the % beside it), the key number of the feature map's cell
    (k), the actual count and total of a rate line (rate = {c, n, p, was}), the age chip (age), the first time the
    issue was shown (first = {d, at, why}: a card's build time, UTC) and ⏳ not final (prov).

The page shows the Studio only when the file belongs to the card on screen (day + card_built_at); without it — no file,
the switch off, a load failure — the Review tab is exactly the older one.

  run(dashboard, data_dir, out_dir, s, now) → the _headers patterns ([] or ["/review/*"]). Writes
  data/review/studio/<day>.json.gz ONCE per card (kept as long as the card is: frozen with it; a rebuilt card gets a
  new one), publishes it byte-for-byte to site/review/studio/ and names it in site/review/index.json["studio"].
  off(out_dir): the switch (repo variable REVIEW_STUDIO=false) — site/review/studio/ and the pointer removed, nothing
  printed: the site exactly as without the feature.

Failure-isolated: an app whose card cannot be read is left out (counted; the page shows that app from the card
document); a missing / broken extra file costs only that chart; any other failure: no file, no pointer, the error TYPE
only. Nothing is trimmed: every app, feature, row and point the card has is in the file. PRIVACY: the log line has the
day and counts only.
"""

import gzip
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from .db import write_json_gz_stable

DIR = "review/studio"   # site and data sub-dir of the day files
V = 1                   # the file's format (the page refuses another)
MAX_GZ = 1500000        # a hard cap far above the ~40 KB of a 30-app day: past it the file is not written (counted)
LINE = None             # this build's counts line (build_static prints it)

MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MI = {m: i + 1 for i, m in enumerate(MON)}
WDAY_EN = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

FEATS = [  # id, English name, short header, icon (the owner's feature names)
    ('kamai', 'Revenue · eCPM', 'Revenue', '💰'),
    ('uninstall', 'Uninstall', 'Uninstall', '🗑️'),
    ('active', 'Active users', 'Active', '👥'),
    ('value', 'Install value', 'Value', '💎'),
    ('update', 'Update impact', 'Update', '🔄'),
    ('ads', 'Ads', 'Ads', '📣'),
    ('deduct', 'Deductions', 'Deduct', '✂️'),
    ('mediation', 'Mediation', 'Mediation', '🔀'),
    ('health', 'Account health', 'Health', '🩺'),
    ('setup', 'Setup / data', 'Setup', '⚙️'),
]
FIDS = [f[0] for f in FEATS]
PRI = {'deduct': 0, 'update': 1, 'kamai': 2, 'uninstall': 3, 'active': 4, 'ads': 5, 'value': 6, 'setup': 7, 'health': 8,
       'mediation': 9}


def enabled(s):
    return bool((s or {}).get("review_studio", True))


def D(s):
    return date.fromisoformat(str(s)[:10])


# ------------------------------------------------------------------------------------------------------------------
# wording: the card's Hinglish text → the owner's rules (short labels English, explanations Hinglish)
# ------------------------------------------------------------------------------------------------------------------
def _tenth(x):
    """a 'per 1,000' number → the same as a %, trimmed ('18.1' → '1.81')."""
    return ('%.2f' % (float(x.replace(',', '')) / 10)).rstrip('0').rstrip('.')


def _per_user(x):
    return ('%.2f' % (float(x.replace(',', '')) / 1000)).rstrip('0').rstrip('.')


RULES = [
    # chart tips "Installs 10–16 Sep: 100 me 17 (1,954 installs)" → the actual number first
    (r'^Installs (.+?): 100 me ([\d.]+) \(([\d,]+) installs\)$',
     lambda m: 'Installs %s: ~%s of %s (%s%%)' % (m.group(1), format(round(float(m.group(2)) * int(m.group(3).replace(',', '')) / 100), ','),
                                               m.group(3), m.group(2))),
    # same day / within N days / come back
    (r'[Ii]nstall ke din (?:hi )?hataane wale', 'Same day uninstall'),
    (r'install ke din app hataana', 'same day uninstall'),
    (r'(\d+) din me hataane wale', r'Uninstall within \1 days'),
    (r'(\d+) din baad wapas aane wale', r'Back after \1 days'),
    (r'Agle din wapas aane wale', 'Back next day'),
    (r'agle din wapas aane wale', 'back next day'),
    (r'7ve din wapas aane wale naye users', 'back after 7 days (new users)'),
    (r'agle din wapas 100 me ([\d.]+)', r'next day back \1%'),
    (r'roz har 1,000 me ([\d.]+) hataate', lambda m: 'daily uninstall ' + _tenth(m.group(1)) + '% of users'),
    (r'Har 1,000 users me roz ([\d.]+) → ([\d.]+) hataate',
     lambda m: 'Roz ' + _tenth(m.group(1)) + '% → ' + _tenth(m.group(2)) + '% users app hataate'),
    (r'har 1,000 users me roz ([\d.]+) → ([\d.]+)',
     lambda m: 'daily uninstall ' + _tenth(m.group(1)) + '% → ' + _tenth(m.group(2)) + '% of users'),
    (r'Har 1,000 users me roz kitne app hataate', 'Daily uninstall · % of users'),
    (r'har 1,000 me roz ~([\d.]+)', lambda m: 'roz ~' + _tenth(m.group(1)) + '%'),
    (r'Har 1,000 users pe roz ([\d,]+) → ([\d,]+) AdMob ads',
     lambda m: 'AdMob ads per user / day ' + _per_user(m.group(1)) + ' → ' + _per_user(m.group(2))),
    (r'AdMob ads har 1,000 users pe', 'AdMob ads per user'),
    (r'[Aa]d rate \(1,000 ads ka\)', 'eCPM'),
    (r'eCPM \(1,000 ads ki kamai\)', 'eCPM'),
    (r'(\w{3}) me 1,000 ads ki kamai', r'\1 eCPM'),
    (r'1,000 ads ki kamai', 'eCPM'),
    (r'Splash ad dikhne ki dar', 'Splash ad show rate'),
    (r'(range [\d.]+–[\d.]+)(?!%)', r'\1%'),
    (r'(\w{3}) me 100 me ([\d.]+)', r'\1 \2%'),
    (r'100 me (\d[\d,]*(?:\.\d+)?) → (\d[\d,]*(?:\.\d+)?)', r'\1% → \2%'),
    (r'100 me (\d[\d,]*(?:\.\d+)?)', r'\1%'),
    (r' · 100 me · ', ' · % · '),
    (r'installs ke hafte', 'install weeks'),
    # revenue / ads lines
    (r'^Kal \(', 'Yesterday ('),
    (r'^Kal ', 'Yesterday '),
    (r'^Kharcha ', 'Spend '),
    (r' · kharcha ', ' · spend '),
    (r' · ek install ', ' · cost/install '),
    (r'Google Ads kharcha nahi \(pichhle 14 din\)', 'No Google Ads spend (last 14 days)'),
    (r'^(.+?) se Google Ads kharcha nahi$', r'No Google Ads spend since \1'),
    (r'Is app pe Google Ads kharcha nahi', 'No Google Ads spend on this app'),
    (r'^AdMob ne baad me $', ''),
    (r'^ kaata ', ' deducted by AdMob '),
    (r'kamai ka ([\d.]+)% se kam', r'under \1% of revenue'),
    (r'kamai ka ([\d.]+)%', r'\1% of revenue'),
    (r'Koi deduction nahi dikha', 'No deductions'),
    (r'kam fill:', 'low fill:'),
    (r'^(\d+) network · ', lambda m: m.group(1) + (' network · ' if m.group(1) == '1' else ' networks · ')),
    (r'Invalid traffic: saaf', 'Invalid traffic: clean'),
    (r'consent: data nahi', 'consent: no data'),
    (r'AdMob login: theek', 'AdMob login: OK'),
    (r'^AdMob (\d+ \w{3}(?: \d{4})?) tak · GA4 (\d+ \w{3}(?: \d{4})?) tak', r'AdMob till \1 · GA4 till \2'),
    (r'^AdMob (\d+ \w{3}(?: \d{4})?) tak', r'AdMob till \1'),
    # update
    (r'⏳ Abhi jaldi — install-wise kamai ka data aa raha', '⏳ Too early — install revenue data still coming'),
    (r'⏳ Abhi jaldi', '⏳ Too early'),
    (r'👍 Chalne do', '👍 Keep'),
    (r'Pichhle (\d+) din me koi update nahi', r'No update in last \1 days'),
    (r'^(\d+ \w{3}) wala update', r'Update of \1'),
    (r'✅ (v[\d.]+) update achha gaya: ', r'✅ \1 went well: '),
    (r'✅ Update achha gaya', '✅ Went well'),
    (r'🛑 Update roko', '🛑 Stop the update'),
    # value
    (r'^Ads ka paisa ~(\d+) din me wapas \(installs (.+?)\) · ≈ Andaza', r'Ad spend back in ~\1 days (installs \2) · ≈ estimate'),
    (r'^Google Ads ka paisa 1 saal me bhi pura wapas nahi \(~(\d+)% hi\)', r'Ad spend not back even in 1 year (only ~\1%)'),
    (r'^GA4 nahi juda — (.+?) ka data nahi', lambda m: 'GA4 not linked — no ' + m.group(1) + ' data'),
    # active
    (r'^Purane users \(roz\) (\d+)% kam: ([\d,]+) → ([\d,]+)', r'Returning users \2 → \3/day (−\1%)'),
    (r'^Purane users \(roz\) \+(\d+)%', r'Returning users/day +\1%'),
    (r'^Purane users roz ([\d,.]+(?: lakh)?)', r'Returning users \1/day'),
    (r'^Purane users \+(\d+)%', r'Returning users +\1%'),
    (r'^Roz ([\d,]+) → ([\d,]+) purane users', r'Returning users \1 → \2/day'),
    (r'^Roz (?:app )?hataane wale (\d+)% kam', r'Daily uninstalls −\1%'),
    (r'^Roz (?:app )?hataane wale (\d+)% badhe', r'Daily uninstalls +\1%'),
    # the same facts as the review now writes them (glossary names; the number first, the % beside it)
    (r'^Old users/day ([\d,.]+(?: lakh)?) → ([\d,.]+(?: lakh)?) \(([+−]\d+%)\)', r'Old users \1 → \2/day (\3)'),
    (r'^Roz ([\d,.]+(?: lakh)?) → ([\d,.]+(?: lakh)?) old users', r'Old users \1 → \2/day'),
    (r'Ads wale installs ka hissa', 'Ads installs share'),
    (r'^Google Ads kharcha (?!·)', 'Google Ads spend '),
    (r'\(4 hafte ka avg\)', '(4-week avg)'),
    (r'% dikhe; ([\d.]+) dikhte', r'% dikhe; \1% dikhte'),
    (r'≈ Andaza', '≈ estimate'),
    (r'^Kamai ([+−]\d+%)', r'Revenue \1'),
    (r'^Kamai ', 'Revenue '),
    (r'(v[\d.]+) update achha gaya$', r'\1 went well'),
    (r'(v[\d.]+) update went well$', r'\1 went well'),
    # the page's own words (the "how this works" lines)
    (r'Kamai · eCPM', 'Revenue · eCPM'),
    (r'🔁 Kal dobara dekho', '🔁 Check again tomorrow'),
    (r'“kal dobara dekho”', '“check again tomorrow”'),
    (r'👍 Theek hai · 🛠 Kaam do · ⛔ Band karo', '👍 Fine · 🛠 Assign fix · ⛔ Stop'),
    (r'💤 Pata hai', '💤 Snooze'),
    # general
    (r'(\$[\d,.]+)/din\b', r'\1/day'),
    (r'^Sab normal — koi badlav nahi$', 'All normal — no change'),
    (r'Abhi jaldi', 'Too early'),
]
# windows / "data kis pe" / chart captions (short English labels)
WRULES = [
    (r'⏳ Pakka nahi · (\d+ \w{3}(?: \d{4})?) ko pakka', r'⏳ Not final · final \1'),
    (r'⏳ Pakka nahi', '⏳ Not final'),
    (r'vs pichhle 4 hafte', 'vs previous 4 weeks'),
    (r'vs hamesha ka normal', 'vs usual'),
    (r'^Roz ka avg', 'Daily avg'),
    (r'≈ Andaza', '≈ estimate'),
    (r'^Installs (.+?) ka andaza$', r'Installs \1 · ≈ estimate'),
    (r'\(update se pehle\)', '(before update)'),
    (r'pehle vs baad ke installs', 'installs before vs after'),
    (r' ke installs', ' installs'),
    (r'GA4 vs AdMob kamai · hafte', 'GA4 vs AdMob revenue · weeks'),
    (r'AdMob mahine ka avg', 'AdMob monthly avg'),
    (r'vs tumhari approved range \((\w{3}) me approve\)', r'vs your approved range (approved \1)'),
    (r'Shuru (\d+ \w{3}(?: \d{4})?) \(1 din\)', r'Started \1 (1 day)'),
    (r'Shuru (\d+ \w{3}(?: \d{4})?) \((\d+) din\)', r'Started \1 (\2 days)'),
    (r'Shuru (\d+ \w{3}(?: \d{4})?) \((\d+) hafte\)', r'Started \1 (\2 weeks)'),
    (r'Shuru (\d+ \w{3}(?: \d{4})?) \((\d+) mahine\)', r'Started \1 (\2 months)'),
    (r'Shuru (\d+ \w{3}(?: \d{4})?) \(aaj\)', r'Started \1 (today)'),
    # chart captions
    (r'App ki AdMob kamai · \$/din', 'App AdMob revenue · /day'),
    (r'ad unit ki kamai · \$/din', 'ad unit revenue · /day'),
    (r'Google Ads kharcha · \$/din', 'Google Ads spend · /day'),
    (r'clicks per din', 'clicks/day'),
    (r'\(dotted = (.+?) ka avg\)', r'(dotted = \1 avg)'),
    (r'^Shuru$', 'Start'),
    (r'^Shuru · ', 'Start · '),
    (r'^pichhle 7 din$', 'last 7 days'),
    (r'\$/din', '/day'),
]
_RULES = [(re.compile(p), r) for p, r in RULES]
_WRULES = [(re.compile(p), r) for p, r in WRULES]


def fx(s, rules=None):
    if not isinstance(s, str):
        return s
    for pat, rep in (rules or _RULES):
        s = pat.sub(rep, s)
    return s


def fw(s):
    return fx(fx(s), _WRULES) if isinstance(s, str) else s


def _money(seg):
    o = {k: seg[k] for k in ('usd', 's', 'sign', 'p') if k in seg}
    if o.get('s') == '/din':
        o['s'] = '/day'
    return o


def rt(x, w=False):
    """rich text: a string or [str | money] — every string rewritten, '/din' → '/day' on money"""
    f = fw if w else fx
    if x is None:
        return None
    if isinstance(x, str):
        return f(x)
    if not isinstance(x, list):
        return None
    return [f(seg) if isinstance(seg, str) else _money(seg) for seg in x if isinstance(seg, (str, dict))]


def plain(x):
    if x is None:
        return ''
    if isinstance(x, str):
        return x
    o = ''
    for seg in x:
        if isinstance(seg, str):
            o += seg
        elif isinstance(seg, dict):
            v = float(seg.get('usd') or 0)
            a = abs(v)
            t = ('{:,.0f}'.format(a) if a >= 10 else '%.1f' % a) if not seg.get('p') else ('%.2f' % a if a < 10 else '%.1f' % a)
            o += ('−' if v < 0 else ('+' if seg.get('sign') and v > 0 else '')) + '$' + t + str(seg.get('s', ''))
    return o


# ------------------------------------------------------------------------------------------------------------------
# dates in the card's text → start date, age, first shown
# ------------------------------------------------------------------------------------------------------------------
def _date_of(dd, mon, yr, day):
    y = int(yr) if yr else day.year
    d = date(y, MI[mon], int(dd))
    if d > day and not yr:
        d = date(y - 1, d.month, d.day)
    return d


def parse_start(kab, day):
    if not kab:
        return None, None
    m = re.search(r'(?:^|Installs )(\d{1,2}) (\w{3})(?: (\d{4}))?(?: se)?(?: ·|$)', kab)
    if m and m.group(2) in MI:
        return _date_of(m.group(1), m.group(2), m.group(3), day), None
    m = re.search(r'^(\w{3}) (\d{4}) se', kab)
    if m and m.group(1) in MI:
        return date(int(m.group(2)), MI[m.group(1)], 1), 'month'
    return None, None


def parse_age_phrase(kab):
    m = re.search(r'(\d+\+?) (din|hafte|mahine) se', kab or '')
    if m:
        return m.group(1), m.group(2)
    if re.search(r'aaj se', kab or ''):
        return '0', 'din'
    return None, None


def age_of(kab, day):
    """→ {'k': 'today'|'yday'|'open', 'n': days, 'txt': '📌 Open 7 days', 'start': 'YYYY-MM-DD'|None} or None"""
    st, gran = parse_start(kab, day)
    num, unit = parse_age_phrase(kab)
    n = None
    if st and gran is None:
        n = (day - st).days
    if num is not None and unit == 'din' and n is None:
        n = int(num.rstrip('+'))
    s = st.isoformat() if st else None
    if n is not None and n <= 0:
        return {'k': 'today', 'n': 0, 'txt': '🆕 Today', 'start': s}
    if n == 1:
        return {'k': 'yday', 'n': 1, 'txt': '🆕 Yesterday', 'start': s}
    if n is not None and n < 60:
        return {'k': 'open', 'n': n, 'txt': f'📌 Open {n} days', 'start': s}
    if num is not None:
        u = {'din': 'days', 'hafte': 'weeks', 'mahine': 'months'}[unit]
        nn = num
        if n is not None and unit == 'din':
            nn, u = str(round(n / 30)), 'months'
        return {'k': 'open', 'n': n, 'txt': f'📌 Open {nn} {u}', 'start': s}
    if n is not None:
        return {'k': 'open', 'n': n, 'txt': f'📌 Open {round(n / 30)} months', 'start': s}
    return None


def kab_rest(kab):
    """what is left of 'Kab se' after the start date and the age: release context, in short English"""
    parts = [p.strip() for p in (kab or '').split('·')]
    keep = []
    for p in parts[1:]:
        if re.fullmatch(r'(\d+\+? (din|hafte|mahine)|aaj) se.*', p) and not re.search(r'\(.+\)', p):
            continue
        p = re.sub(r'^(\d+\+? (?:din|hafte|mahine)|aaj) se ', '', p)
        p = re.sub(r'(v[\d.]+|update) (\d+ \w{3}) ko aaya \((\d+) din pehle\)', r'\1 released \2 (\3 days before)', p)
        p = re.sub(r'(v[\d.]+|update) (\d+ \w{3}) ko aaya', r'\1 released \2', p)
        p = re.sub(r'(v[\d.]+|update) usi din aaya', r'\1 released same day', p)
        p = (p.replace('(7 din ki tulna)', '(7-day compare)').replace('(jab se data hai)', '(since data starts)')
             .replace('(har mahine range ke neeche)', '(below range every month)')
             .replace('(jab se ye page dekh raha hai)', '(since this page started)'))
        keep.append(p)
    return ' · '.join(x for x in keep if x)


def first_of(q, day, card_at, at_of):
    """'Naya ya purana → Pehli baar dikha' → {d, at, why}: at = the build time (UTC) of the card that first showed it
    (this card, or an earlier snapshot's), None when only a date is known (a dashboard alert's own opened date)."""
    f = ((q or {}).get('naya') or {}).get('first') or ''
    m = re.match(r'(\d{1,2}) (\w{3})(?: (\d{4}))?', f)
    if not m or m.group(2) not in MI:
        return None
    d = _date_of(m.group(1), m.group(2), m.group(3), day)
    why = 'first card' if 'page shuru' in f else ('feature started' if 'feature shuru' in f else '')
    at = None
    if why != 'feature started':
        at = card_at if d == day else at_of(d.isoformat())
    return {'d': d.isoformat(), 'at': at, 'why': why}


# ------------------------------------------------------------------------------------------------------------------
# the key number of a feature map cell (currency-free)
# ------------------------------------------------------------------------------------------------------------------
def _pnum(s):
    return float(s.replace(',', '').replace('−', '-'))


def key_num(fid, f):
    st = f['st']
    if st not in ('red', 'amber', 'green'):
        return None
    q = f.get('q') or {}
    cands = [plain(f.get('line')), f.get('t') or '', plain(q.get('saath')), plain(q.get('kit'))]
    for s in cands:
        if not s:
            continue
        m = re.search(r'(\d+) guna', s)
        if m:
            return m.group(1) + '×'
        if fid == 'value':
            m = re.search(r'only ~(\d+)%', s)
            if m:
                return '~' + m.group(1) + '%'
        m = re.search(r'ROAS (?:\(kamai ÷ kharcha\) )?([\d.]+) → ([\d.]+)', s)
        if m:
            return m.group(2)
        m = re.search(r'\(([\d.]+)%\) · was ([\d.]+)%', s)
        if m:
            return m.group(1) + '%'
        m = re.search(r'([\d.]+)% → ([\d.]+)%', s)
        if m:
            return m.group(2) + '%'
        m = re.search(r'\(−(\d+)%\)', s)
        if m:
            return '−' + m.group(1) + '%'
        m = re.search(r'(\d+)% (giri|kam)', s)
        if m:
            return '−' + m.group(1) + '%'
        m = re.search(r'(\d+)% (badhe|badha|zyada)', s)
        if m:
            return '+' + m.group(1) + '%'
        m = re.search(r'([+−])(\d+)%', s)
        if m:
            return m.group(1) + m.group(2) + '%'
        m = re.search(r'\$([\d,.]+) → \$([\d,.]+)', s)
        if m:
            a, b = _pnum(m.group(1)), _pnum(m.group(2))
            if a:
                r = round((b / a - 1) * 100)
                return ('+' if r > 0 else '−') + str(abs(r)) + '%'
        m = re.search(r'^Same day uninstall:? (?:[\d,]+ of [\d,]+ (?:installs )?\()?(\d+)%', s)
        if m:
            return m.group(1) + '%'
        m = re.search(r'show rate .*?([\d.]+)%', s)
        if m:
            return m.group(1) + '%'
        m = re.search(r'\(AdMob ka (\d+)%\)', s)
        if m:
            return m.group(1) + '%'
        if 'Stop the update' in s:
            return 'Stop'
        if 'went well' in s.lower():
            return '✅'
    if fid == 'setup':
        return '!'
    return None


# ------------------------------------------------------------------------------------------------------------------
# the extra charts (the site files the review step read, cut to the card's own data windows)
# ------------------------------------------------------------------------------------------------------------------
def _days(a, b):
    a, b = D(a), D(b)
    return [(a + timedelta(i)).isoformat() for i in range((b - a).days + 1)]


def rev14(dash, app_id, d14):
    """{day: USD} of the app's AdMob earnings (placements, country All) on the 14 card days."""
    name = next((c.get('app_name') for c in dash.get('apps_catalog') or [] if c.get('app_id') == app_id), None)
    if not name:
        return None
    want, out = set(d14), defaultdict(float)
    for p in dash.get('placements') or []:
        if p.get('app') != name or p.get('country', 'All') != 'All':
            continue
        for r in p.get('daily') or []:
            if r and r[0] in want:
                out[r[0]] += (r[1] or 0) / 1e6
    return out


def un_weeks(c, ga4_till, late):
    """8 install weeks of same-day uninstalls ending on the GA4 day of the card: [{f, t, n, s, prov}]."""
    st0 = D(c['start'])
    new, lags = c.get('new') or [], c.get('lags') or []
    wk = []
    for w in range(7, -1, -1):
        e = ga4_till - timedelta(7 * w)
        s = e - timedelta(6)
        N = S = 0
        for i, (n, lg) in enumerate(zip(new, lags)):
            dd = st0 + timedelta(i)
            if s <= dd <= e:
                N += int(n or 0)
                S += sum(int(x[1] or 0) for x in (lg or []) if x and x[0] == 0)
        wk.append({'f': s.isoformat(), 't': e.isoformat(), 'n': N, 's': S, 'prov': bool(e > ga4_till - timedelta(late))})
    return wk


def win_counts(c, w0, w1):
    st0 = D(c['start'])
    N = S = 0
    for i, (n, lg) in enumerate(zip(c.get('new') or [], c.get('lags') or [])):
        dd = st0 + timedelta(i)
        if w0 <= dd <= w1:
            N += int(n or 0)
            S += sum(int(x[1] or 0) for x in (lg or []) if x and x[0] == 0)
    return N, S


def ret_daily(act, ga4_till):
    """42 days of returning users per day, ending on the app's GA4 day (never past the card's): {v, d, final}."""
    Dd = act.get('daily') or {}
    if not Dd.get('ret') or not Dd.get('start') or not act.get('data_till'):
        return None
    st0 = D(Dd['start'])
    till = min(D(act['data_till']), ga4_till) if ga4_till else D(act['data_till'])
    vals, labs = [], []
    for i in range(41, -1, -1):
        dd = till - timedelta(i)
        j = (dd - st0).days
        v = Dd['ret'][j] if 0 <= j < len(Dd['ret']) else None
        vals.append(v if isinstance(v, (int, float)) and not isinstance(v, bool) else None)
        labs.append(dd.isoformat())
    if all(v is None for v in vals):
        return None
    fin = act.get('settled_till')
    fin = min(D(fin), till).isoformat() if fin else None
    return {'v': vals, 'd': labs, 'final': fin}


def med_shares(medj, dname, w7, p7):
    """Every network's share of the app's mediation revenue on the card's 7 days (and the 7 before) + fill:
    [{n, s, p, f, usd}] (s / p / f in %, one decimal; usd = the network's revenue those 7 days), biggest first."""
    if not isinstance(medj, dict):
        return None
    srcs = (medj.get('by_app') or {}).get(dname)
    if not srcs:
        return None
    dates = medj.get('dates') or []
    mi = {d: i for i, d in enumerate(dates)}
    names = medj.get('names') or {}
    w = {mi[x] for x in w7 if x in mi}
    pw = {mi[x] for x in p7 if x in mi}
    cur, prv, ma, rq = defaultdict(float), defaultdict(float), defaultdict(float), defaultdict(float)
    for sid, rows in srcs.items():
        nm = names.get(sid, sid)
        if nm in ('0', ''):
            continue
        for r in rows or []:
            if not r:
                continue
            if r[0] in w:
                cur[nm] += r[1] or 0
                ma[nm] += r[3] or 0
                rq[nm] += r[4] or 0
            if r[0] in pw:
                prv[nm] += r[1] or 0
    tc, tp = sum(cur.values()), sum(prv.values())
    if tc <= 0:
        return None
    usd = (medj.get('currency') or 'USD') == 'USD'
    out = []
    for nm in sorted(set(cur) | set(prv), key=lambda k: (-cur.get(k, 0), k)):
        c = cur.get(nm, 0.0)
        if c <= 0 and prv.get(nm, 0) <= 0:
            continue
        out.append({'n': nm, 's': round(100 * c / tc, 1),
                    'p': round(100 * prv.get(nm, 0.0) / tp, 1) if tp else None,
                    'f': round(100 * ma[nm] / rq[nm], 1) if rq.get(nm) else None,
                    'usd': round(c / 1e6, 2) if usd else None})
    return out


# ------------------------------------------------------------------------------------------------------------------
# one feature, one app
# ------------------------------------------------------------------------------------------------------------------
def _chart(ch):
    ch = dict(ch)
    vals = list(ch.get('vals') or [])
    if ch.get('fmt') == 'r1' and 'Har 1,000' in (ch.get('cap') or ''):   # per 1,000 users → % of users
        vals = [None if v is None else v / 10 for v in vals]
        ch['before'] = None if ch.get('before') is None else ch['before'] / 10
        ch['fmt'] = 'pct2'
    ch['vals'] = vals
    ch['cap'] = fw(ch.get('cap') or '')
    tips = []
    for i, t in enumerate(ch.get('tips') or []):
        m = re.match(r'^Installs (.+?): 100 me ([\d.]+) \(([\d,]+) installs\)$', t or '')
        v = vals[i] if i < len(vals) else None
        if m and v is not None and ch.get('fmt') == 'p100':
            n = int(m.group(3).replace(',', ''))
            tips.append(f'Installs {m.group(1)}: {round(v * n / 100):,} of {n:,} ({m.group(2)}%)')
        else:
            tips.append(fx(t))
    ch['tips'] = tips or None
    ch['marks'] = [[i, fw(t)] for i, t in ch.get('marks') or [] if i is not None]
    return ch


def feature(fid, f, day, card_at, at_of):
    q = f.get('q')
    o = {'st': f.get('st') or 'nodata', 'line': rt(f.get('line')), 't': fx(f.get('t')),
         'info': [rt(x) for x in f.get('info') or []], 'kis': rt(f.get('kis'), True)}
    if q:
        o['q'] = {'kya': rt(q.get('kya')), 'kit': rt(q.get('kit')), 'karo': fx(q.get('karo')), 'kis': rt(q.get('kis'), True),
                  'abhi': rt(q.get('abhi')), 'saath': rt(q.get('saath')), 'chip': (q.get('naya') or {}).get('chip')}
        o['age'] = age_of(q.get('kab'), day)
        o['since'] = kab_rest(q.get('kab'))
        o['first'] = first_of(q, day, card_at, at_of)
        kis = plain(o['q']['kis'])
        m = re.search(r'⏳ Not final(?: · final (\d+ \w{3}(?: \d{4})?))?', kis)
        o['prov'] = (m.group(1) or '') if m else None
        o['q']['kis'] = re.sub(r' · ⏳ Not final(?: · final \d+ \w{3}(?: \d{4})?)?', '', kis)
    det = f.get('detail')
    if det:
        o['chart'] = _chart(det['chart']) if det.get('chart') else None
        o['more'] = [{'w': r.get('w'), 'src': r.get('src'), 'fact': rt(r.get('fact')), 'meta': fw(r.get('meta'))}
                     for r in det.get('more') or []]
        o['tab'] = det.get('tab')
    return o


def _rate_lines(F, X, day):
    """'Same day uninstall: 22% → 28%' → 'Same day uninstall 854 of 3,098 (28%) · was 22%' (the actual number first,
    counted from the cohort file for the window the card names, or from the chart's own tip) + rate = {c, n, p, was}."""
    uwk = {(w['f'], w['t']): w for w in (X.get('un') or {}).get('wk', [])}
    for fid in ('uninstall', 'active', 'update'):
        f = F[fid]
        line = f['line'] if isinstance(f['line'], str) else None
        m = re.match(r'^(.*?):? (\d[\d.]*)% → (\d[\d.]*)%$', line or '')
        if not m:
            continue
        kis = plain((f.get('q') or {}).get('kis')) or plain(f.get('kis'))
        mw = re.match(r'^Installs (\d+)(?: (\w{3}))?–(\d+) (\w{3})', kis or '')
        if not mw or mw.group(4) not in MI or (mw.group(2) and mw.group(2) not in MI):
            continue
        d1, m1, d2, m2 = mw.groups()
        w1 = _date_of(d2, m2, None, day)
        w0 = _date_of(d1, m1 or m2, None, day)
        wl = f'{d1}{" " + m1 if m1 else ""}–{d2} {m2}'
        C = N = None
        w = uwk.get((w0.isoformat(), w1.isoformat()))
        if m.group(1).endswith('Same day uninstall') and w and w['n']:
            C, N = w['s'], w['n']
            if round(100 * C / N) != round(float(m.group(3))):
                C = N = None
        ch = f.get('chart') or {}
        if C is None and ch.get('tips'):
            for t in ch['tips']:
                mt = re.match(r'^Installs ' + re.escape(wl) + r': ([\d,]+) of ([\d,]+) \(([\d.]+)%\)', t or '')
                if mt and round(float(mt.group(3))) == round(float(m.group(3))):
                    C, N = int(mt.group(1).replace(',', '')), int(mt.group(2).replace(',', ''))
        if C is None:
            continue
        lab = m.group(1).rstrip(':')
        new = f'{lab} {C:,} of {N:,} ({m.group(3)}%) · was {m.group(2)}%'
        old = line
        f['line'] = new
        if f.get('t') == old:
            f['t'] = new
        if f.get('q') and f['q'].get('kya') == old:
            f['q']['kya'] = new
        f['rate'] = {'c': C, 'n': N, 'p': float(m.group(3)), 'was': float(m.group(2))}


def _same_day_line(F, X, ga4_till):
    """the normal uninstall line: the actual count of the window the card names first, the % beside it."""
    uw = X.get('un_win')
    if not uw or not isinstance(F['uninstall']['line'], str):
        return
    mm = re.match(r'^Same day uninstall: (\d+(?:\.\d+)?)% \(installs (.+?)\)(.*)$', F['uninstall']['line'])
    if not mm or not uw['n'] or round(100 * uw['s'] / uw['n']) != round(float(mm.group(1))):
        return                                  # (counts that do not give the card's own % are not shown)
    new = f"Same day uninstall {uw['s']:,} of {uw['n']:,} installs ({mm.group(1)}%) · installs {mm.group(2)}{mm.group(3)}"
    late = (X.get('un') or {}).get('late') or 0
    if D(uw['t']) > ga4_till - timedelta(late):
        new += ' · ⏳ not final'
    F['uninstall']['line'] = new
    F['uninstall']['t'] = new
    F['uninstall']['rate'] = {'c': uw['s'], 'n': uw['n'], 'p': float(mm.group(1)), 'was': None}


def build_app(a, gi, rank, grp, doc, site, dash, ctx):
    """One app → its Studio entry (raises on a card it cannot read; the caller counts it as skipped)."""
    day = D(doc['day'])
    data = doc['data']
    key = a['key']
    F = {}
    for fid in FIDS:
        F[fid] = feature(fid, a['f'][fid], day, doc['built_at'], ctx['at_of'])
    # the 14-day revenue series: the card's own kamai chart when it has one (frozen with the card), else placements
    d14 = ctx['d14']
    ser = None
    snap = ((a['f'].get('kamai') or {}).get('detail') or {}).get('chart') or {}
    if (snap.get('cap') or '').startswith('App ki') and len(snap.get('vals') or []) == 14:
        ser = [None if v is None else round(float(v), 4) for v in snap['vals']]
    else:
        try:
            R = rev14(dash, a.get('app_id'), d14)
            if R is not None:
                ser = [round(R.get(d, 0.0), 4) for d in d14]
        except Exception:
            ser = None
    if ser is not None:
        ser[-1] = round(float(a.get('y') or 0), 4)            # Yesterday = the card's number
    X = {}
    ga4_till = D(data['ga4_till']) if data.get('ga4_till') else None
    late = ctx['late'].get(key) or 0
    if ga4_till:
        try:
            c = site.gz(f'uninstall_c_{key}.json.gz')
            if c and c.get('new') and c.get('start'):
                X['un'] = {'wk': un_weeks(c, ga4_till, late), 'late': late}
                mt = re.search(r'installs (\d+)(?: (\w{3}))?–(\d+) (\w{3})', a['f']['uninstall'].get('t') or '')
                if mt and mt.group(4) in MI and (not mt.group(2) or mt.group(2) in MI):
                    d1, m1, d2, m2 = mt.groups()
                    w0, w1 = _date_of(d1, m1 or m2, None, day), _date_of(d2, m2, None, day)
                    N, S = win_counts(c, w0, w1)
                    X['un_win'] = {'f': w0.isoformat(), 't': w1.isoformat(), 'n': N, 's': S}
        except Exception:
            X.pop('un', None)
            X.pop('un_win', None)
        try:
            act = site.gz(f'active_{key}.json.gz')
            r = ret_daily(act, ga4_till) if isinstance(act, dict) else None
            if r:
                X['ret'] = r
        except Exception:
            pass
    try:
        md = med_shares(ctx['medj'], a.get('dname'), ctx['w7'], ctx['p7'])
        if md:
            X['med'] = md
    except Exception:
        pass
    _rate_lines(F, X, day)
    if ga4_till:
        _same_day_line(F, X, ga4_till)
    for fid in FIDS:
        o = F[fid]
        o['k'] = key_num(fid, o)
        if fid == 'kamai' and o['k'] and re.search(r'ad ki kamai|ad unit|Splash ad', plain(o['line'])):
            o['k'] = 'ad ' + o['k']
    # the top issue = the feature whose "kya" is the card's headline, else the first Worse / Watch by priority
    bad = [fid for fid in FIDS if F[fid]['st'] in ('red', 'amber')]
    bad.sort(key=lambda x: (0 if F[x]['st'] == 'red' else 1, PRI[x]))
    head = a.get('head') or {}
    ht = plain(head.get('text'))
    top = next((fid for fid in bad if plain(((a['f'][fid].get('q') or {}).get('kya'))) == ht), None)
    if top is None and bad:
        top = bad[0]
    if top is None:
        good = [fid for fid in FIDS if F[fid]['st'] == 'green']
        top = next((fid for fid in good if plain(a['f'][fid].get('line')) == ht), good[0] if good else None)
    if top and F[top].get('q') and plain((a['f'][top].get('q') or {}).get('kya')) == ht:
        head_text = F[top]['q']['kya']
    elif top and plain(a['f'][top].get('line')) == ht:
        head_text = F[top]['line']
    else:
        head_text = rt(head.get('text'))
    name, tag = a.get('name') or a.get('dname') or key, ''
    m = re.search(r' \((\d{4}) wala\)$', name)
    if m:
        tag, name = f'({m.group(1)} wala)', name[:m.start()]
    icon = ctx['icons'].get(a.get('app_id'))
    return {
        'key': key, 'id': a.get('app_id'), 'name': name, 'tag': tag, 'acct': a.get('acct') or '', 'pkg': a.get('pkg') or '',
        'dname': a.get('dname') or '', 'size': a.get('size'), 'small': bool(a.get('small')), 'grp': grp, 'gi': gi,
        'rank': rank, 'k7': a.get('k7'), 'kp7': a.get('kp7'), 'y': a.get('y'), 'us': a.get('us'), 'spend': a.get('spend'),
        'tier': a.get('tier'), 'nb': list(a.get('nb') or []),
        'head': {'text': head_text, 'chip': head.get('chip'), 'age': head.get('age')}, 'top': top,
        'icon': icon if isinstance(icon, str) and icon.startswith('https://') and len(icon) < 600 else None,
        'late_days': late, 'ser': ser, 'f': F, 'x': X,
    }


# ------------------------------------------------------------------------------------------------------------------
# the day
# ------------------------------------------------------------------------------------------------------------------
def build_data(doc, site, dash=None, at_of=None, now=None, counts=None):
    """The Studio file's body for the card document `doc` (v1), from the built site (review.site.Site). counts gets
    {"skipped": n}. Raises when the card document itself cannot be read (the caller writes no file)."""
    counts = {} if counts is None else counts
    dash = dash if isinstance(dash, dict) else (site.dashboard() or {})
    day = D(doc['day'])
    data = doc['data']
    built = datetime.fromisoformat(doc['built_at'].replace('Z', '+00:00'))
    admob_till = D(data['admob_till'])
    d14 = [(admob_till - timedelta(i)).isoformat() for i in range(13, -1, -1)]
    un = site.gz('uninstall.json.gz') or {}
    late = {}
    for x in un.get('apps') or []:
        if isinstance(x, dict) and x.get('key') and isinstance(x.get('late_days'), (int, float)):
            late[x['key']] = int(x['late_days'])
    w7 = _days(data['w7']['from'], data['w7']['to']) if data.get('w7') else []
    p7 = _days(data['p7']['from'], data['p7']['to']) if data.get('p7') else []
    icons = dash.get('app_icons') if isinstance(dash.get('app_icons'), dict) else {}
    ctx = {'d14': d14, 'late': late, 'w7': w7, 'p7': p7, 'icons': icons, 'medj': site.js('mediation_daily.json', None),
           'at_of': at_of or (lambda d: None)}
    order = doc.get('order') or {}
    grp = {}
    for g in ('top', 'ok', 'small'):
        for i, k in enumerate(order.get(g) or []):
            grp.setdefault(k, (g, i))
    seq = [k for g in ('top', 'ok', 'small') for k in (order.get(g) or [])]
    A = {a['key']: a for a in doc.get('apps') or [] if isinstance(a, dict) and a.get('key')}
    seq += [k for k in A if k not in grp]                       # (never drop a card the order does not list)
    apps, skipped = [], 0
    for rank, key in enumerate(seq):
        a = A.get(key)
        if a is None:
            continue
        g, gi = grp.get(key, ('small' if a.get('small') else 'ok', 0))
        try:
            apps.append(build_app(a, gi, rank + 1, g, doc, site, dash, ctx))
        except Exception:
            skipped += 1
    counts['skipped'] = skipped
    meta = {
        'day': doc['day'], 'wday': WDAY_EN[day.weekday()], 'built_at': doc['built_at'],
        'built_ist': (built + timedelta(hours=5, minutes=30)).strftime('%H:%M'),
        'admob_till': data['admob_till'], 'ga4_till': data.get('ga4_till'), 'settled_till': data.get('settled_till'),
        'ga4_lag': data.get('ga4_lag'), 'w7': data.get('w7'), 'p7': data.get('p7'), 'usual': data.get('usual'),
        'ded': data.get('ded'), 'fx': doc.get('fx'), 'counts': doc.get('counts'), 'd14': d14,
        'gen': (doc.get('built_from') or {}).get('generated_at'), 'how': [rt(x) for x in doc.get('how') or []],
        'consts': doc.get('consts'),
    }
    n = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {'v': V, 'day': doc['day'], 'card_built_at': doc['built_at'], 'built_at': n, 'meta': meta,
            'feats': [list(x) for x in FEATS], 'apps': apps}


# ------------------------------------------------------------------------------------------------------------------
# the build step
# ------------------------------------------------------------------------------------------------------------------
def _read_gz(path):
    try:
        with open(path, 'rb') as f:
            return json.loads(gzip.decompress(f.read()).decode('utf-8'))
    except Exception:
        return None


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path, obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    try:
        with open(path, 'rb') as f:
            if f.read() == raw:
                return False
    except OSError:
        pass
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(raw)
    os.replace(tmp, path)
    return True


def _site_dir(out_dir):
    return os.path.join(out_dir, *DIR.split('/'))


def _data_dir(data_dir):
    return os.path.join(data_dir, *DIR.split('/'))


def _strip_pointer(out_dir):
    p = os.path.join(out_dir, 'review', 'index.json')
    idx = _read_json(p)
    if isinstance(idx, dict) and 'studio' in idx:
        idx.pop('studio', None)
        _write_json(p, idx)


def _remove(out_dir):
    d = _site_dir(out_dir)
    try:
        for n in os.listdir(d):
            try:
                os.remove(os.path.join(d, n))
            except OSError:
                pass
        os.rmdir(d)
    except OSError:
        pass
    try:
        _strip_pointer(out_dir)
    except Exception:
        pass


def _valid(body, day, card_at):
    return (isinstance(body, dict) and body.get('v') == V and body.get('day') == day
            and body.get('card_built_at') == card_at and isinstance(body.get('apps'), list))


def run(dashboard, data_dir, out_dir, s=None, now=None):
    """The open day's Studio file → ["/review/*"] (for _headers; the review step's own pattern covers it) or [] (no
    open day, no card, a failure: no file, no pointer). Never raises."""
    global LINE
    LINE = None
    try:
        from .review.site import Site
        from .review.store import read_doc
        ip = os.path.join(out_dir, 'review', 'index.json')
        idx = _read_json(ip)
        od = idx.get('open_day') if isinstance(idx, dict) else None
        if not isinstance(od, str) or not _DAY.match(od):
            _remove(out_dir)
            return []
        doc = read_doc(os.path.join(data_dir, 'review', 'days', f'{od}.json.gz'), od) \
            or read_doc(os.path.join(out_dir, 'review', 'days', f'{od}.json.gz'), od)
        if doc is None:
            _remove(out_dir)
            LINE = f"Review Studio: day {od} · no card"
            return []
        canon = os.path.join(_data_dir(data_dir), f'{od}.json.gz')
        body = _read_gz(canon)
        status = 'kept'
        counts = {'skipped': 0}
        if not _valid(body, od, doc.get('built_at')):
            site = Site(out_dir, dashboard)

            def at_of(d):                       # the build time of the earlier card that first showed an issue
                if not _DAY.match(d or ''):
                    return None
                x = read_doc(os.path.join(data_dir, 'review', 'days', f'{d}.json.gz'), d)
                return x.get('built_at') if x else None
            body = build_data(doc, site, dashboard, at_of, now, counts)
            raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
            gz = len(gzip.compress(raw, 9, mtime=0))
            if gz > MAX_GZ:
                _remove(out_dir)
                LINE = f"Review Studio: day {od} · too big ({gz // 1024} kb), not written"
                return []
            write_json_gz_stable(canon, body)
            if not _valid(_read_gz(canon), od, doc.get('built_at')):
                raise OSError('studio file not readable')
            status = 'built'
        # publish: the open day's file only (byte copy), every other day's copy removed from the site
        with open(canon, 'rb') as f:
            raw_gz = f.read()
        sd = _site_dir(out_dir)
        os.makedirs(sd, exist_ok=True)
        name = f'{od}.json.gz'
        dst = os.path.join(sd, name)
        try:
            with open(dst, 'rb') as f:
                same = f.read() == raw_gz
        except OSError:
            same = False
        if not same:
            tmp = dst + '.tmp'
            with open(tmp, 'wb') as f:
                f.write(raw_gz)
            os.replace(tmp, dst)
        for n in os.listdir(sd):
            if n != name:
                try:
                    os.remove(os.path.join(sd, n))
                except OSError:
                    pass
        raw = json.dumps(_read_gz(canon), ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
        idx['studio'] = {od: {'file': f'{DIR}/{name}', 'v': hashlib.sha1(raw).hexdigest()[:12],
                              'card': doc.get('built_at')}}
        _write_json(ip, idx)
        LINE = (f"Review Studio: day {od} · {status} (apps {len((_read_gz(canon) or {}).get('apps') or [])}, "
                f"skipped {counts.get('skipped', 0)}) · kb {len(raw_gz) // 1024}")
        return ['/review/*']
    except Exception as e:
        _remove(out_dir)
        LINE = None
        print("Review Studio skipped: %s" % re.sub(r'[^A-Za-z_]', '', type(e).__name__), file=sys.stderr)
        return []


def off(out_dir):
    """The switch off: site/review/studio/ and the pointer removed (the site exactly as without the feature), no line."""
    global LINE
    LINE = None
    _remove(out_dir)


def pop_line():
    """This build's counts line (None when the step did not run) — once."""
    global LINE
    line, LINE = LINE, None
    return line
