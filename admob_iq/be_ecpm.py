"""⚖️ Breakeven — the 14-day card's eCPM index (owner, 14 Nov 2026: "return session ke ecpm ko check karne ke liye day
1,2,3,4,7,14 … 100 number ke hisab se", with a benchmark "100 number ke hisab se" too; 15 Nov 2026: day 1 = the FIRST
session's eCPM, "haan pehla session wala lo"). A part of be_build, switched by GA4_CECPM_USE together with the reads
(GA4_CECPM): either off, be_build never calls it — its files exactly as without it.

  inputs (read only, one app at a time): fetch.ga4_cecpm's store (the install day's users by country on their days 2,
  3, 4, 7, 14 = ages 1, 2, 3, 6, 13: GA4's ad revenue and ad_impression events) and fetch.ga4_nvr's (the install day's
  FIRST session: "n" revenue and impressions by country — day 1's base, the same base the tab's benchmark uses).

  Words: eCPM = revenue ÷ impressions × 1000 (GA4's own, never AdMob-matched: a correction factor between day 1 and day
  14 would move the index); day 1 = the first session's eCPM, day k = the eCPM of the same users' sessions that day
  (age k − 1: every session of theirs then is a returning one); INDEX at day k = 100 × eCPM(day k) ÷ eCPM(day 1). A cell
  is VALID with ≥ MIN_IMP impressions on day k and on day 1, day 1's eCPM > 0, day 1's first-session read not a GA4
  sample and its activity day read whole (not sampled / cut / collapsed); a FINAL cell also comes from a folded day
  (never a hot copy).

  bench (with be_build's daily fit, cached in its fits as "ec" with its rule's stamp "ec_v" — a stamp of another rule
  is made again the same build): per app × country and card day the bot's median (be_build.rmed: |robust z| > 3
  dropped) over the country's PAST judged install days with final valid cells — of log index (kept in the fits and the stamp; the card no longer reads it) and
  of log eCPM (the benchmark eCPM, which the card's benchmark line chains; day 1: the first session's) — up to the first card day with < MIN_KEPT days. No
  look-ahead and never the days it judges: install day + max(age + LAG, SETTLE) ≤ the fit's origin (the ROAS
  benchmark's rule beside it). Every past day the stores hold, nothing trimmed.
  attach (every build): per judged install day the countries COUNT from day 1 (a day-1 base and a day-1 benchmark) for
  as long as their users' cells hold (owner, 16 Nov 2026: "sab din rakho · bs ak info add kar do jab se giravat ati he
  to konsi country count nahi hua vo bata do vo day"): from the first FINAL card day a country has no valid cell (under
  MIN_IMP, folded into "(other)", …) or no benchmark it is out from there on, and "dr" names it with that day, its
  spend share and why. A hot copy still filling drops nobody (its point: the counted countries that have a cell), nor
  does a day where no counted country has a cell (never read, GA4-unusable for every country, all under MIN_IMP) or
  none could stay — that point is null with its letter. Per card day, over its counted countries with a cell by the
  day's spend share: this day's eCPM $ and the benchmark's (each country's median eCPM). The INDEX is CHAINED: day 1 =
  100, each next drawn day = the last drawn day's index × the move between those two days on the countries counted
  both days (the owner's example: ₹100 → ₹20 = 20 against ₹90 → ₹25 = 28), the benchmark index the same on their
  benchmark eCPMs — a country leaving never moves either line; the $ rows are each day's own countries (after a drop
  the $ can step while the index does not). cv = that day's countries' share of its country spend (the page: "x %
  spend: data kam" for the rest).
  On an app whose country split GA4 samples (its busy days: fetch.ga4_cecpm keeps that day's no-country read, "pool"),
  a card with such a day is every country together: GA4's exact eCPM of all the install day's users, day 1 = the whole
  app's first session, against the app's own pooled benchmark (bench "*", from its judged install days) — "pl": 1 (the
  page says so). Never the sampled country split (the probe found it far off GA4's whole numbers).
  Every missing value says why (one letter a card day, "." = there):
    y not lived yet · w not read yet (GA4's history still filling, not folded, a hot copy still filling) · f GA4's
    reads of this app stopped days ago (the store is stale) · s GA4 sampled / cut that day (or day 1's first-session
    read) · l GA4 answered that day with far less than its own earlier reads, and kept it so · o GA4 folded the row
    into "(other)" · t GA4's thresholding may have hidden it · n too few impressions (< MIN_IMP, that day or on day 1)
    · z day 1's eCPM 0 · x no ad impression · k (app line) no country split of the day's spend · c (app line) the
    countries with an index have no benchmark · b (benchmark) < MIN_KEPT past days · h (benchmark) GA4's history
    still being read (the benchmark comes once it is)
  The app line's reason when no country has an index: the one carrying the most spend among the countries with a day-1
  eCPM (all of them when none has one). A value from a day not final yet is marked ("p": 1 a card day — day 1 while the
  install day is younger than fetch.ga4_nvr's FINAL_LAG (P1_AGE; at GA4_FINAL_DAYS 3, the rollback, its RECENT_DAYS as
  before the knob), a later day while its activity day is a hot copy) and from a day GA4 folded / thresholded ("q").

  site/be_<key>.json.gz gains (only with the switches on): days[i] "ec": {"x" [6 × this day's index], "b" [6 × the
  benchmark index], "e" [6 × this day's eCPM USD], "be" [6 × the benchmark eCPM USD], "cv" [6 × the covered share of
  the day's country spend], "w" / "wb" (why x / b is null), "p" / "q" (not final / folded or thresholded), "dr"
  [[card day, [[cc, spend share, why], …]], …] (the countries that stopped counting from that day; absent: none)}
  (judged days only; "pl": 1 = every country together) — nothing the page does not show.
A store whose newest final day is more than FINAL_LAG + LOW_WAIT + STALE_DAYS days old is stale ("f"; be_build prints
one "be ecpm skipped: StaleWarning" line a build). Never raises into be_build: load / bench / attach each fail alone
("be ecpm skipped: <Type>", the health banner) and cost the card's eCPM part only.
"""
import math
import os
import sys
from datetime import date, timedelta

from . import be_build as bb
from . import ga4_final
from .fetch import ga4_cecpm as gce
from .fetch import ga4_nvr as gv

V = 1
BV = 1                               # the benchmark's rule: bump with any change to bench() or _cell()'s training path
CARD = (0, 1, 2, 3, 6, 13)           # card days 1, 2, 3, 4, 7, 14 = these ages (day 1: the first session)
KS = tuple(gce.AGES.index(a) for a in CARD[1:])     # the store's age slots of days 2 … 14
MIN_IMP = 100                        # impressions a cell needs (on day k and on day 1): measured on the stores (16 Nov
#                                      2026) — below it one country's index strays from its own benchmark far more than
#                                      the real day-to-day spread; at it, about as much (the owner: "ye kami galat he" — a
#                                      floor of 1,000 left most countries out though their data was whole)
FLOOR = 0.01                         # an index never below 1 % of day 1 (a log of 0)
STALE_DAYS = 3                       # days past the fetch's own slack (its edge + a held day's wait): stale
OK_ST = ("ok", "oth", "thr")
WHY = "ywfslotnzxkcbh"               # a tie between reasons: the first of these
P1_AGE = ga4_final.page_lag(gv.RECENT_DAYS, gv.FINAL_LAG)   # day 1 is not final ("p") while the install day is younger:
#                                      the first-session store's final lag (GA4_FINAL_DAYS); at the rollback its window
#                                      (RECENT_DAYS), the rule before the knob


def _fail(e):
    print("be ecpm skipped: %s" % type(e).__name__, file=sys.stderr)


def enabled(s):
    s = s or {}
    return bool(s.get("ga4_cecpm_use") and s.get("ga4_cecpm"))


def stamp():
    """The benchmark rule's stamp (a list: it comes back from JSON the same)."""
    return [V, BV, MIN_IMP, FLOOR, list(OK_ST), bb.LAG, bb.SETTLE, bb.MIN_KEPT, bb.ZBOT]


def load(data_dir, key, cty):
    """One app's stores → {"fs": {(cc, X): (USD, impressions)}, "fa": {X: (USD, impressions)} (every country), "fsd"
    (the first-session store's days), "fsm" (its days read from a GA4 sample), "cells": {(cc, X): [micros, events] ×
    days 2 … 14}, "days": {D: (state, hot)}, "upto", "done"} for the install days of the app's country rows, or None
    (no store of this format)."""
    want = {x.day for rows in cty.values() for x in rows}
    got = gce.load_cells(data_dir, key, want=want)
    if got is None:
        return None
    pairs = {(cc, x.day) for cc, rows in cty.items() for x in rows}
    cells, pool = {}, {}
    for (cc, X), arr in got["cells"].items():
        v = [arr[j] if j < len(arr) else 0 for k in KS for j in (2 * k, 2 * k + 1)]
        p = pool.setdefault(X, [0] * len(v))          # every country together: a "pool" day's "*" cell, else the sum
        for i, n in enumerate(v):                     # of the day's countries (a day is one or the other)
            p[i] += n
        if (cc, X) in pairs:
            cells[(cc, X)] = v
    del got["cells"]
    fs, fa, fsd = {}, {}, set()
    st = gv.load_store(os.path.join(data_dir, gv.DIR, key + ".json.gz"))
    fsm = _sampled_base(st, want)
    for day, rv in ((st or {}).get("days") or {}).items():
        if day not in want:
            continue
        fsd.add(day)
        ra = ia = 0.0
        for k, cc, rev, im in (rv or {}).get("c") or []:
            if k != "n":
                continue
            ra += rev or 0
            ia += im or 0
            if (cc, day) in pairs:
                fs[(cc, day)] = (float(rev or 0), float(im or 0))
        fa[day] = (ra, ia)
    del st
    return {"fs": fs, "fa": fa, "fsd": fsd, "fsm": fsm, "cells": cells, "pool": pool, "days": got["days"],
            "upto": got["upto"], "done": got["done"], "hs": got.get("hs")}


def _sampled_base(st, want):
    """The first-session store's days whose day-1 base came from a GA4 sample: the COUNTRY read's own flag ("mp") where
    the store knows it — another read of the day being sampled never counts (owner, 16 Nov 2026: "sample data de esa ho
    hi nhi sakta … proper check kro"); the all-in-one "mark" only for a day read before the store kept its reads' own."""
    mk, mp = (st or {}).get("mark") or {}, (st or {}).get("mp") or {}
    return {d for d in want if (mp[d].get("c") == "s" if isinstance(mp.get(d), dict) else mk.get(d) == "s")}


def stale(m, O):
    """Is the store's newest final day — nothing folded yet (a new app): the day before its history start — more
    than the fetch's own slack + STALE_DAYS days before O?"""
    if m.get("upto"):
        last = date.fromisoformat(m["upto"]).toordinal()
    elif m.get("hs"):
        last = date.fromisoformat(m["hs"]).toordinal() - 1
    else:
        return True
    return O - last > gce.FINAL_LAG + gce.LOW_WAIT + STALE_DAYS


def _cell(m, key, X, j, O=None):
    """Card day j's cell of country key (None: every country together) → (eCPM USD, why) — why one of the letters
    (module doc), "." with a value. O: the fit's origin (a final cell only: folded)."""
    if X in m.get("fsm", ()):
        return None, "s"                   # day 1's first-session read was a GA4 sample: no base
    whole = key == gce.POOL_CC                     # every country together (the pooled line)
    fs = m["fa"].get(X) if whole else m["fs"].get((key, X))
    if fs is None or fs[1] <= 0:
        return None, "x" if X in m["fsd"] else "w"      # the first-session store has the day: no impression
    if fs[1] < MIN_IMP:
        return None, "n"
    if fs[0] <= 0:
        return None, "z"
    e1 = fs[0] / fs[1] * 1000
    if j == 0:
        return e1, "."
    D = (date.fromisoformat(X) + timedelta(days=CARD[j])).isoformat()
    st = m["days"].get(D)
    if st is None:
        return None, "f" if m.get("stale") and (not m.get("upto") or D > m["upto"]) else "w"
    if st[0] not in OK_ST and not (whole and st[0] == gce.POOL):
        return None, "l" if st[0] == gce.LOW else "s"     # (a "pool" day: GA4 sampled its country split)
    if O is not None and st[1]:
        return None, "w"                   # a hot copy never trains
    v = (m["pool"].get(X) if whole else m["cells"].get((key, X))) or ()
    k = j - 1
    r, i = (v[2 * k], v[2 * k + 1]) if len(v) > 2 * k + 1 else (0, 0)
    if i < MIN_IMP and st[1]:
        return None, "w"                   # a hot copy GA4 is still filling: not final yet, never "few" / "none"
    if i <= 0:
        return None, {"oth": "o", "thr": "t"}.get(st[0], "x")
    if i < MIN_IMP:
        return None, "n"
    return r / 1e6 / i * 1000, "."


def bench(cty, m, O, app=None):
    """The fit's "ec": {cc: [[j, log index median, n, log eCPM median], …]} (card days j = 0 … 5 as a prefix); "*":
    every country together, from the app's own judged install days (the pooled line's benchmark)."""
    out = {}
    for cc, rows in list(cty.items()) + ([(gce.POOL_CC, app)] if app else []):
        if cc in bb.SKIP_CC:
            continue
        res = []
        for j in range(len(CARD)):
            li, le = [], []
            for x in rows:
                if not x.jd or x.X + max(CARD[j] + bb.LAG, bb.SETTLE) > O:
                    continue                # (the past only: never the days the card judges)
                e1, _ = _cell(m, cc, x.day, 0, O)
                if e1 is None:
                    continue
                ek = e1 if j == 0 else _cell(m, cc, x.day, j, O)[0]
                if ek is None:
                    continue
                li.append(math.log(max(ek, FLOOR * e1) / e1))
                le.append(math.log(max(ek, 1e-9)))
            if len(li) < bb.MIN_KEPT:
                break
            res.append([j, round(bb.rmed(li), 5), len(li), round(bb.rmed(le), 5)])
        if res:
            out[cc] = res
    return out


def _r(v, n):
    return None if v is None else round(v, n)


def _most(why):
    """[(spend, letter)] → the letter carrying the most spend ("." skipped; a tie: the first of WHY; none: "x")."""
    t = {}
    for sp, c in why:
        if c != ".":
            t[c] = t.get(c, 0.0) + (sp or 0.0)
    if not t:
        return "x"
    return max(sorted(t, key=WHY.index), key=t.get)


def attach(body, pin, fc, m, O=None):
    """The eCPM index into one app's be body (in place): each judged day's "ec" (module doc). O: the build's day (the
    store's staleness) → True when the store is stale."""
    if not m:
        return False
    m["stale"] = O is not None and stale(m, O)
    ok = fc.get("ec_v") == stamp()           # (a benchmark of another rule is never set against this one's days)
    B = {cc: {j: (mi, n, me) for j, mi, n, me in v} for cc, v in ((fc.get("ec") if ok else None) or {}).items()}
    nw = date.fromisoformat(pin[0]).toordinal()
    byday = pin[2]
    hb = "h" if fc.get("ec_h") or not m.get("done") else "b"     # no benchmark: GA4's history still being read when
    #                                                              it was made (or now), else too few past days
    for out in body.get("days") or []:
        if out.get("jd") == 0:
            continue
        X = out["d"]
        Xo = date.fromisoformat(X).toordinal()
        cs = byday.get(X) or {}
        tot = sum(x.sp for x in cs.values()) or 1.0
        rows = {}
        for cc, x in cs.items():
            if cc in bb.SKIP_CC:
                continue
            e, w = [], []
            for j in range(6):
                v, why = (None, "y") if Xo + CARD[j] > nw else _cell(m, cc, X, j)
                e.append(v)
                w.append(why)
            ix = [None if e[0] is None or e[j] is None else 100 * max(e[j], FLOOR * e[0]) / e[0] for j in range(6)]
            rows[cc] = (x.sp, e, ix, w)
        st_of = [m["days"].get((date.fromisoformat(X) + timedelta(days=CARD[j])).isoformat()) for j in range(6)]
        lived = [j for j in range(6) if Xo + CARD[j] <= nw]

        def final(j):                       # a folded day (never a hot copy still filling)
            return j == 0 or bool(st_of[j] and not st_of[j][1])
        # the owner, 16 Nov 2026: "sab din rakho · bs ak info add kar do jab se giravat ati he to konsi country count
        # nahi hua vo bata do vo day" — a country counts from day 1 (a day-1 base and a day-1 benchmark) for as long as
        # its users' cells hold: from the first FINAL card day it has no valid cell (or no benchmark) it is out from there
        # on, and "dr" names it with that day, its spend share and why. A hot copy still filling drops nobody; nor does a
        # day where no counted country has a cell (never read, GA4-unusable for every country, all under MIN_IMP) or
        # where no counted country could stay — that point is null.
        cur = [cc for cc, (sp, e, ix, w) in rows.items() if e[0] is not None and 0 in B.get(cc, {})]
        sets, dr = [], []
        for j in range(6):
            if j and j in lived and final(j) and any(rows[cc][1][j] is not None for cc in cur):
                keep = [cc for cc in cur if rows[cc][1][j] is not None and j in B.get(cc, {})]
                if keep:
                    gone = sorted((cc for cc in cur if cc not in keep), key=lambda c: (-rows[c][0], c))
                    if gone:
                        dr.append([j, [[cc, round(rows[cc][0] / tot, 4),
                                        rows[cc][3][j] if rows[cc][1][j] is None else "c"] for cc in gone]])
                    cur = keep
            sets.append(list(cur))

        def _why_out(j):                    # nobody counted: the most-spend reason among the countries with a day-1
            if not rows:                    # eCPM (all of them when none has one) — a missing cell first, then "c"
                return "k"
            lt = [(sp, (w[0] if e[0] is None else w[j] if e[j] is None else "c"), e[0] is not None)
                  for cc, (sp, e, ix, w) in rows.items()]
            return _most([(sp, c) for sp, c, b1 in lt if b1] or [(sp, c) for sp, c, _ in lt])
        er, br, cv, wx, wb, ex, eb = [], [], [], [], [], [], []
        xp = bp = jp = None                 # the last drawn day: its index, its benchmark index, its card day
        for j in range(6):
            S = sets[j]
            M = [cc for cc in S if rows[cc][1][j] is not None and j in B.get(cc, {})] if j in lived else []
            Mp = M if j == 0 or jp is None else [cc for cc in M if rows[cc][1][jp] is not None and jp in B.get(cc, {})]
            Msp = sum(rows[cc][0] for cc in M)
            if M and Msp > 0 and (j == 0 or (jp is not None and Mp)):
                E = sum(rows[cc][0] * rows[cc][1][j] for cc in M) / Msp
                Bj = sum(rows[cc][0] * math.exp(B[cc][j][2]) for cc in M) / Msp
                if j == 0:
                    x = b = 100.0
                else:
                    # CHAINED: the move since the last drawn day, on the countries counted both days, onto its index
                    # (the owner's example: ₹100 → ₹20 = 20 against ₹90 → ₹25 = 28) — a country leaving moves nothing
                    num = sum(rows[cc][0] * rows[cc][1][j] for cc in Mp)
                    den = sum(rows[cc][0] * rows[cc][1][jp] for cc in Mp)
                    bnum = sum(rows[cc][0] * math.exp(B[cc][j][2]) for cc in Mp)
                    bden = sum(rows[cc][0] * math.exp(B[cc][jp][2]) for cc in Mp)
                    x = max(xp * num / den, 100 * FLOOR) if den > 0 else None
                    b = bp * bnum / bden if bden > 0 else None
                if x is not None and b is not None:
                    er.append(E)
                    br.append(Bj)
                    ex.append(_r(x, 1))
                    eb.append(_r(b, 1))
                    cv.append(round(Msp / tot, 4))
                    wx.append(".")
                    wb.append(".")
                    xp, bp, jp = x, b, j
                    continue
            er.append(None)
            br.append(None)
            ex.append(None)
            eb.append(None)
            cv.append(0.0)
            why = "y" if j not in lived else _why_out(j)      # (the documented rule: the most spend's missing piece)
            wx.append(why)
            wb.append(hb if why == "c" else ".")
        ee = [_r(v, 4) for v in er]
        ebe = [_r(v, 4) for v in br]
        pl = any(j and st_of[j] and st_of[j][0] == gce.POOL for j in range(6))
        if pl:                              # GA4 sampled the country split on a day of this card: the whole card is
            P = B.get(gce.POOL_CC, {})      # every country together (exact), against the app's own pooled benchmark
            for j in range(6):
                v, why = (None, "y") if Xo + CARD[j] > nw else _cell(m, gce.POOL_CC, X, j)
                ee[j] = _r(v, 4)
                v0 = ee[0] if j else v
                ex[j] = None if v is None or v0 is None else _r(100 * max(v, FLOOR * v0) / v0, 1)
                if ex[j] is None:
                    eb[j] = ebe[j] = None
                    wx[j], wb[j] = (why if v is None else "z"), "."
                elif j in P and 0 in P:             # (the benchmark index = its eCPMs' ratio, like the table)
                    eb[j], ebe[j], wx[j], wb[j] = (_r(100 * math.exp(P[j][2] - P[0][2]), 1), _r(math.exp(P[j][2]), 4),
                                                   ".", ".")
                else:
                    eb[j] = ebe[j] = None
                    wx[j], wb[j] = ".", hb
                cv[j] = None
        p = ("1" if nw - Xo < P1_AGE else "0") + "".join(              # (day 1: younger than the first-session
            "1" if st_of[j] and st_of[j][1] else "0" for j in range(1, 6))  # store's final lag — the page's not final)
        q = "".join("1" if j and st_of[j] and st_of[j][0] in ("oth", "thr") else "0" for j in range(6))
        out["ec"] = {"x": ex, "b": eb, "e": ee, "be": ebe, "cv": cv, "w": "".join(wx), "wb": "".join(wb), "p": p,
                     "q": q}
        if dr and not pl:
            out["ec"]["dr"] = dr            # (the page: which country stopped counting from which day, and why)
        if pl:
            out["ec"]["pl"] = 1             # (the page: "saari countries mila ke" and why)
    return m["stale"]
