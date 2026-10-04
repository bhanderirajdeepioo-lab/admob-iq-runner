"""Audience engine — pure math behind "dead users by months since their last open" (no I/O, no prints).

Inputs, one app:
  * its Audience store (admob_iq.fetch.ga4_audience), complete: E = the latest FINAL activity day, months = [N_1, N_2 …]
    and windows = [w_1, w_2 …] days (window "N months" = [E − w + 1, E], w = window_days(N)), by_fsd = {install day X:
    [GA4 activeUsers of X in each window …]}, dau_by_fsd = {X: activeUsers of X on day E}, plus GA4's own totals /
    "(other)" / "(not set)" and flags. The months are TIERED (tier_months): 1, 2 … 12, then 15, 18, 21, 24, then every 6
    months (30, 36 …) up to the first window that holds the app's whole history;
  * its Uninstall store (admob_iq.fetch.ga4_uninstall): daily[X].new (GA4 new users = installs of X) and
    cohorts[X][lag] (app_remove users of X on day X + lag). Pass engine.uninstall.fill_days(store) to read the cells
    exactly as the Uninstall tab does.

PER INSTALL DAY X (history_start ≤ X ≤ E), as of E:
  installs        n         = daily[X].new
  uninstalled     U         = Σ cohorts[X][lag], lag ≤ E − X
  installed       I         = n − U                                   (clamped at 0, marked un_gt_new)
  for window N (start S = E − w_N + 1):
    act(N)        = GA4 activeUsers of X in the window: everyone who opened the app at least once in it — INCLUDING
                    users who opened and then uninstalled inside the window (GA4 keeps them in the count; they are
                    not on a phone any more)
    un_in(N)      = Σ cohorts[X][lag] with S ≤ X + lag ≤ E — X's uninstalls INSIDE the window
    alive(N)      = act − un_in                                     (installed now AND opened in the last N months)
    dead(N)       = I − alive                                       (installed now, not opened for ≥ N months)

  THE APPROXIMATION (alive = act − un_in): every user who uninstalled inside the window is taken to have OPENED the app
  in the window before uninstalling, so all of them sit inside act and come out of it. A user who uninstalled without
  opening it first (a phone clean-up of an app not opened for months) was never in act: then alive reads LOW by those
  users and dead reads HIGH by the same number. So dead(N) is the UPPER end of a range whose LOWER end is dead_lo(N) =
  I − min(act, I) (no window uninstaller had opened: every opener is still installed). The truth lies between; both
  ends are in every total and never hidden. Uninstalls BEFORE the window need nothing: those users can't open the app
  in it (a reinstall is a new GA4 user with a new first-session day).

  A YOUNG cell — X inside window N (installed less than N months ago) — opened the app on its install day, so alive = I
  and dead = dead_lo = 0 by definition; it is never computed from act (GA4's user counts are sketches: ±1–2% noise must
  not make a young day look dead). act of the young cells of window 1 vs their installs is kept as a split self-check
  (young_cov ≈ 1: every new user is active on day one).

  CLAMPS, each counted with the users it moved (marks[code] = [cells, users]; per window in clamps_by_month):
    un_gt_new    U > n                — installed would be < 0 → 0                                        IMPOSSIBLE
    act_gt_inst  act − un_in > I      — more users opened (still installed) than are installed → I     IMPOSSIBLE
    un_gt_act    un_in > act          — more of the day's users UNINSTALLED in the window than OPENED in it, so at least
                                        un_in − act of them uninstalled without opening first (clean-up uninstalls —
                                        the approximation's blind spot, here proven). alive → 0, dead → I: the cell's
                                        range is [I − min(act, I), I]. Per window, Σ users moved is a LOWER bound of
                                        that window's distinct clean-up uninstallers; summed over windows a user counts
                                        once per window that holds the uninstall.
    non_mono     alive(N) < alive(N−1) — a longer window can't hold fewer installed openers → raised to alive(N−1) (the
                                        same clean-up uninstalls: un_in grows with the window too; or sketch noise)
  dead_lo is kept non-increasing in N the same way (a longer window's lower end can't be higher).

LAST-OPEN DISTRIBUTION (last_open): every installed user by how many months ago they last opened the app, between two
consecutive windows: [0, 1) → "1" (opened within the last month: alive(1)), [1, 2) → "2" … [11, 12) → "12", [12, 15) →
"13-15", [15, 18) → "16-18" … [24, 30) → "25-30" …, and "<last>+" = dead(last window) (0 when the last window holds the
whole history). users = from the dead curve (the estimate), users_lo_curve = from the dead_lo curve; the buckets of one
curve add up to installed. dead(N) never rises with N (alive never falls), so no bucket is negative.

GROUPS: install day → install month ("YYYY-MM") → app → portfolio (sums; a ratio is computed from the sums, never
averaged). MOST dead / active install month, by count and by share of the month's installs, over MATURE months only (no
install day inside window 1 — the newest month's installs all opened within the month by definition), and for the
share only months with ≥ max(MIN_MONTH_INSTALLS, MIN_MONTH_SHARE of all installs) installs (a few test installs must not
win). "dead" = dead(1) (installed, not opened in the last month), "active" = alive(1). DAU on E by install month:
dau_by_fsd summed by month; users installed before the history ("before_history"), "(other)" and "(not set)" shown apart.

HISTORY + COMEBACK (the bottom of this file): each complete read's monthly aggregates are kept as one snapshot per E
(snapshot / hist_append), and comeback() measures from two snapshots one month apart how many users who had not opened
for N months opened again on their own. Not shown on the page yet.
"""

import calendar
from datetime import date, timedelta

MONTH_DAYS = 365.25 / 12              # window N months = floor(N × 30.4375) days: 30, 60, 91 … 365 (12) … 730 (24)
TIERS = ((12, 1), (24, 3), (None, 6))  # (up to N months, step): monthly to 12, quarterly to 24, then every 6 months
MIN_MONTH_INSTALLS = 100              # "most … by share": a month needs ≥ 100 installs …
MIN_MONTH_SHARE = 0.01                # … and ≥ 1% of the group's installs
UN_LATE_DAYS = 7                      # app_remove arrives up to ~7 days late (engine.uninstall.LATE_DAYS)
IMPOSSIBLE = ("un_gt_new", "act_gt_inst")
CLAMPED = ("un_gt_act", "non_mono")
MARKS = IMPOSSIBLE + CLAMPED
WINDOWED = ("act_gt_inst", "un_gt_act", "non_mono")
ARRAYS = ("act", "un_in", "alive", "dead", "dead_lo", "young")


def window_days(n):
    """Days in the window of N months: floor(N × 30.4375) — 30, 60, 91, 121, …, 365 for N = 12."""
    return int(n * MONTH_DAYS)


def tier_months(age_days):
    """The windows' months for an app whose history holds `age_days` install days: 1..12, 15, 18, 21, 24, 30, 36, …
    up to the first window that holds every install day."""
    out, n = [], 0
    while True:
        for top, step in TIERS:
            if top is None or n < top:
                n += step
                break
        out.append(n)
        if window_days(n) >= age_days:
            return out


def months_of(store):
    """The store's months (older stores without them: from their window days)."""
    m = store.get("months")
    if m:
        return [int(v) for v in m]
    return [int(round(int(w) / MONTH_DAYS)) for w in store.get("windows") or []]


def last_open_bins(months):
    """[(label, from, to)] for the last-open distribution between consecutive windows, + the tail (to None)."""
    out, prev = [], 0
    for m in months:
        out.append((str(m) if m - prev == 1 else "%d-%d" % (prev + 1, m), prev, m))
        prev = m
    out.append(("%d+" % (prev + 1), prev, None))
    return out


def _d(s):
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0


def _ratio(a, b):
    return round(a / b, 4) if a is not None and b else None


def _group(k):
    g = {"days": 0, "installs": 0, "uninstalled": 0, "installed": 0, "marks": {m: [0, 0] for m in MARKS},
         "marks_w": {m: [[0, 0] for _ in range(k)] for m in WINDOWED}}
    for a in ARRAYS:
        g[a] = [0] * k
    return g


def _add(g, c):
    for f in ("days", "installs", "uninstalled", "installed"):
        g[f] += c[f]
    for a in ARRAYS:
        dst = g[a]
        for i, v in enumerate(c[a]):
            dst[i] += v
    for m, (n, u) in c["marks"].items():
        g["marks"][m][0] += n
        g["marks"][m][1] += u
    for m, rows in c["marks_w"].items():
        for i, (n, u) in enumerate(rows):
            g["marks_w"][m][i][0] += n
            g["marks_w"][m][i][1] += u


def _mark(c, code, users, i=None):
    c["marks"][code][0] += 1
    c["marks"][code][1] += int(users)
    if i is not None:
        c["marks_w"][code][i][0] += 1
        c["marks_w"][code][i][1] += int(users)


def day_cell(x, n, lags, act, end, wd):
    """One install day → its cell (the module docstring's rules). x: the day; n: its installs; lags: [(lag, users)];
    act: GA4's actives per window; wd: the windows' days. → a one-day group and its marks {window number: code} (0: the
    install day itself)."""
    k, age = len(wd), (end - x).days
    c = _group(k)
    c["days"], c["installs"] = 1, n
    codes = {}
    u_all = sum(u for lag, u in lags if 0 <= lag <= age)
    inst = n - u_all
    if inst < 0:
        _mark(c, "un_gt_new", -inst)
        codes[0] = "un_gt_new"
        inst = 0
    c["uninstalled"], c["installed"] = u_all, inst
    prev = prev_lo = 0                                 # alive(N − 1), and the lower end's alive (min(act, I))
    for i, w in enumerate(wd):
        if age < w:                                    # young: installed inside the window, opened on its first day
            c["alive"][i], c["young"][i], c["un_in"][i], c["act"][i] = inst, 1, u_all, act[i]
            prev = prev_lo = inst
            continue
        first = age - w + 1                            # lags ≥ first fall inside [E − w + 1, E]
        un_in = sum(u for lag, u in lags if first <= lag <= age)
        a = act[i]
        alive = a - un_in                              # the approximation (module docstring)
        if alive < 0:
            _mark(c, "un_gt_act", -alive, i)
            codes[i + 1] = "un_gt_act"
            alive = 0
        if alive > inst:
            _mark(c, "act_gt_inst", alive - inst, i)
            codes[i + 1] = "act_gt_inst"
            alive = inst
        if alive < prev:
            _mark(c, "non_mono", prev - alive, i)
            codes.setdefault(i + 1, "non_mono")
            alive = prev
        lo_alive = max(prev_lo, min(a, inst))          # the lower end: every opener still installed
        c["act"][i], c["un_in"][i], c["alive"][i], c["dead"][i] = a, un_in, alive, inst - alive
        c["dead_lo"][i] = min(inst - alive, inst - lo_alive)
        prev, prev_lo = alive, lo_alive
    return c, codes


def _last_open(months, installed, dead, dead_lo):
    """The last-open buckets of one group (module docstring)."""
    out = []
    curve = {"users": dead, "users_lo_curve": dead_lo}
    for j, (lab, lo, hi) in enumerate(last_open_bins(months)):
        b = {"label": lab, "from": lo, "to": hi}
        for key, d in curve.items():
            if hi is None:
                v = d[-1] if d else installed
            else:
                above = installed if j == 0 else d[j - 1]
                v = None if above is None or d[j] is None else above - d[j]
            b[key] = v
        out.append(b)
    return out


def finish(g, months):
    """A summed group → its output: the arrays, the last-open buckets, the shares (of installs) and the marks split into
    impossible / clamped, with the clamped users per window month (clamps_by_month)."""
    out = {f: g[f] for f in ("days", "installs", "uninstalled", "installed")}
    for a in ("act", "un_in", "alive", "dead", "dead_lo"):
        out[a] = list(g[a])
    out["young_days"] = list(g["young"])
    out["last_open"] = _last_open(months, g["installed"], out["dead"], out["dead_lo"])
    out["dead_share"] = [_ratio(v, g["installs"]) for v in out["dead"]]
    out["alive_share"] = [_ratio(v, g["installs"]) for v in out["alive"]]
    out["impossible"] = {m: list(g["marks"][m]) for m in IMPOSSIBLE if g["marks"][m][0]}
    out["clamped"] = {m: list(g["marks"][m]) for m in CLAMPED if g["marks"][m][0]}
    out["clamps_by_month"] = {m: {str(months[i]): list(v) for i, v in enumerate(g["marks_w"][m]) if v[0]}
                              for m in WINDOWED if any(v[0] for v in g["marks_w"][m])}
    return out


def most(months, installs_total):
    """Most dead / most active install month, by count and by share of the month's installs, over MATURE months (no
    install day inside window 1); the share only for months with ≥ max(MIN_MONTH_INSTALLS, MIN_MONTH_SHARE × all
    installs). Ties → the earlier month. None when no month qualifies (or every value is 0)."""
    floor = max(MIN_MONTH_INSTALLS, MIN_MONTH_SHARE * installs_total)

    def pick(key, share):
        best = None
        for mo in sorted(months):
            g = months[mo]
            if not g["young_days"] or g["young_days"][0] or not g["installs"] or g[key][0] is None:
                continue
            if share and g["installs"] < floor:
                continue
            v = g[key][0] / g["installs"] if share else g[key][0]
            if best is None or v > best[1]:
                best = (mo, v)
        if not best or best[1] <= 0:
            return None
        g = months[best[0]]
        return {"month": best[0], "users": g[key][0], "installs": g["installs"],
                "share": _ratio(g[key][0], g["installs"])}
    return {"dead": {"count": pick("dead", False), "share": pick("dead", True)},
            "active": {"count": pick("alive", False), "share": pick("alive", True)}}


def dau_split(aud, hs, daily):
    """DAU on E by install month: dau_by_fsd summed by month; installs before the history, "(other)", "(not set)"
    apart; checked against the Uninstall store's daily actives of E (cov). (One day: a user who opened on E and
    uninstalled the same day is in it — not taken out.)"""
    e = str(aud.get("E"))
    by, before = {}, 0
    for x, u in (aud.get("dau_by_fsd") or {}).items():
        if x < hs:
            before += _int(u)
        elif x <= e:
            by[x[:7]] = by.get(x[:7], 0) + _int(u)
    meta = aud.get("dau") or {}
    other, not_set = _int(meta.get("other")), _int(meta.get("not_set"))
    users = sum(by.values()) + before + other + not_set
    a1 = (daily.get(e) or {}).get("a1")
    return {"day": e, "users": users, "by_month": dict(sorted(by.items())), "before_history": before,
            "other": other, "not_set": not_set, "ga4_total": meta.get("total"), "store_a1": a1,
            "cov": _ratio(users, _int(a1)) if a1 else None}


def derive_app(aud, uni, per_day=False, un_late_days=UN_LATE_DAYS):
    """One app's Audience numbers (module docstring) from its COMPLETE Audience store `aud` (ValueError for one still
    being read) and its Uninstall store `uni`. → {E, history_start, months, windows, full, installs … (the app's group:
    act / un_in / alive / dead / dead_lo per window, last_open), months_by {YYYY-MM: group}, most, dau, checks, flags}
    (+ per_day {X: …} when asked). flags.un_provisional_days: the days up to E inside the Uninstall store's newest
    un_late_days (app_remove still arriving there: installed may read a little high, dead a little low)."""
    if aud.get("complete") is False or not aud.get("windows"):
        raise ValueError("audience store not complete")
    end, hs = _d(aud["E"]), _d(uni["history_start"])
    wd = [int(v) for v in aud["windows"]]
    months = months_of(aud)
    m = len(wd)
    full = (end - hs).days < wd[-1]                    # the last window already holds every install day
    daily, cells, by = uni.get("daily") or {}, uni.get("cohorts") or {}, aud.get("by_fsd") or {}
    lo, hi = hs.isoformat(), end.isoformat()
    days = sorted(x for x in set(daily) | set(by) if lo <= x <= hi)
    app, mos, per = _group(m), {}, {}
    young1 = [0, 0]                                    # window 1's young cells: Σ act, Σ installs (the split check)
    for x in days:
        n = _int((daily.get(x) or {}).get("new"))
        lags = []
        for lag, u in (cells.get(x) or {}).items():
            try:
                lags.append((int(lag), _int(u)))
            except (TypeError, ValueError):
                continue
        row = by.get(x) or []
        act = [_int(row[i]) if i < len(row) else 0 for i in range(m)]
        c, codes = day_cell(_d(x), n, lags, act, end, wd)
        _add(app, c)
        _add(mos.setdefault(x[:7], _group(m)), c)
        if c["young"][0]:
            young1[0] += act[0]
            young1[1] += n
        if per_day:
            per[x] = {"n": n, "U": c["uninstalled"], "I": c["installed"], "act": c["act"], "alive": c["alive"],
                      "dead": c["dead"], "dead_lo": c["dead_lo"], "marks": {str(kk): v for kk, v in codes.items()}}
    out = finish(app, months)
    tot, oth, nst = (list(aud.get(f) or []) for f in ("total", "other", "not_set"))
    before, split = [0] * m, [0] * m                   # actives installed before the history (can't be placed); Σ rows
    for x, row in by.items():
        for i in range(min(m, len(row))):
            split[i] += _int(row[i])
            if x < lo:
                before[i] += _int(row[i])
    for i in range(m):
        split[i] += _int(oth[i] if i < len(oth) else 0) + _int(nst[i] if i < len(nst) else 0)
    we = uni.get("window_end")
    inc = [d for d in ((uni.get("flags") or {}).get("incomplete_days") or {}) if lo <= d <= hi]
    unpl = sum(_int(v) for d, v in (uni.get("unplaced") or {}).items() if lo <= d <= hi)
    flags = dict(aud.get("flags") or {})
    flags.update(un_till=we, un_days_missing=max(0, (end - _d(we)).days) if we else None,
                 un_provisional_days=max(0, (end - _d(we)).days + un_late_days) if we else None,
                 un_incomplete_days=len(inc), un_unplaced=unpl, history_capped=bool(uni.get("history_capped")),
                 impossible_cells=sum(v[0] for v in out["impossible"].values()),
                 clamped_cells=sum(v[0] for v in out["clamped"].values()))
    out.update(E=hi, history_start=lo, months=months, windows=wd, full=full, flags=flags,
               months_by={mo: finish(g, months) for mo, g in sorted(mos.items())},
               ga4_total=tot, other=oth, not_set=nst, before_history=before,
               checks={"young_cov": _ratio(young1[0], young1[1]),       # window 1's install days: actives ÷ installs
                       "split_cov": [_ratio(split[i], _int(tot[i])) if i < len(tot) and tot[i] else None
                                     for i in range(m)]})               # Σ rows ÷ GA4's TOTAL, per window
    out["most"] = most(out["months_by"], out["installs"])
    out["dau"] = dau_split(aud, lo, daily)
    if per_day:
        out["per_day"] = per
    return out


def _align(g, months, glob, full):
    """A finished group on its own months → its sums on the portfolio's months `glob`: a month it has is taken as is;
    past its last window, a full app's install days are all young (alive = installed, dead 0); any other month is
    unknown (None)."""
    at = {mo: i for i, mo in enumerate(months)}
    out = {f: g[f] for f in ("days", "installs", "uninstalled", "installed")}
    young = {"alive": g["installed"], "dead": 0, "dead_lo": 0, "un_in": g["uninstalled"], "young_days": g["days"]}
    for f in ("alive", "dead", "dead_lo", "un_in", "young_days"):
        src = g[f]
        out[f] = [src[at[mo]] if mo in at else (young[f] if full and mo > months[-1] else None) for mo in glob]
    return out


def _sum_into(dst, src, k):
    for f in ("days", "installs", "uninstalled", "installed"):
        dst[f] = dst.get(f, 0) + src[f]
    for f in ("alive", "dead", "dead_lo", "un_in", "young_days"):
        cur = dst.setdefault(f, [0] * k)
        for i, v in enumerate(src[f]):
            cur[i] = None if cur[i] is None or v is None else cur[i] + v


def portfolio(apps):
    """Every app's derive_app result (a list; an entry with "err" is skipped) → the portfolio on the tiered months up to
    the longest window (an app without one of them: young past its own last window when that window held all its
    history, else None), calendar install months summed across apps, the last-open buckets, the most dead / active month, the DAU on
    each app's E by install month, the marks, and the apps' E range."""
    ok = [a for a in apps if isinstance(a, dict) and "err" not in a and "installs" in a]
    # the tiered months up to the longest window any app has (an app read on another step — e.g. monthly — has every
    # one of them below its own last window)
    glob = tier_months(window_days(max([mo for a in ok for mo in a["months"]] or [1])))
    k = len(glob)
    tot, mos, marks = {}, {}, {}
    _sum_into(tot, {"days": 0, "installs": 0, "uninstalled": 0, "installed": 0,
                    **{f: [0] * k for f in ("alive", "dead", "dead_lo", "un_in", "young_days")}}, k)
    dau = {"users": 0, "by_month": {}, "before_history": 0, "other": 0, "not_set": 0}
    for a in ok:
        _sum_into(tot, _align(a, a["months"], glob, a["full"]), k)
        for mo, g in a["months_by"].items():
            _sum_into(mos.setdefault(mo, {}), _align(g, a["months"], glob, a["full"]), k)
        for grp in ("impossible", "clamped"):
            for code, (n, u) in a.get(grp, {}).items():
                cur = marks.setdefault(code, [0, 0])
                cur[0] += n
                cur[1] += u
        d = a.get("dau") or {}
        for f in ("users", "before_history", "other", "not_set"):
            dau[f] += _int(d.get(f))
        for mo, u in (d.get("by_month") or {}).items():
            dau["by_month"][mo] = dau["by_month"].get(mo, 0) + _int(u)
    for g in [tot] + list(mos.values()):
        g["last_open"] = _last_open(glob, g["installed"], g["dead"], g["dead_lo"])
        g["dead_share"] = [_ratio(v, g["installs"]) for v in g["dead"]]
        g["alive_share"] = [_ratio(v, g["installs"]) for v in g["alive"]]
    dau["by_month"] = dict(sorted(dau["by_month"].items()))
    es = sorted(a["E"] for a in ok)
    return dict(tot, apps=len(ok), skipped=len(apps) - len(ok), months=glob,
                windows=[window_days(mo) for mo in glob], E_min=es[0] if es else None, E_max=es[-1] if es else None,
                months_by=dict(sorted(mos.items())), most=most(mos, tot["installs"]), dau=dau, marks=marks)


# ── history: one compact snapshot per complete read, and the COMEBACK measured from it ───────────────────────────────
#
# Each complete read REPLACES the store, so on its own it keeps no history. fetch.ga4_audience therefore appends, for
# every NEW E, one snapshot of the read's monthly aggregates to data/ga4_audience_hist/<key>.json.gz — never replaced,
# never trimmed:
#     {"v": 1, "snaps": {E: {"months": [N_1 … N_K],
#                            "m": {install month: [installs, installed, alive_1 … alive_K, act_1 … act_K,
#                                                  dead_lo_1 … dead_lo_K]},
#                            "q": [flags]}}}
# installs / installed / alive / dead_lo are derive_app's own monthly sums (installed = installs − uninstalls up to E;
# alive_N = installed AND opened in the last N months; dead_lo_N = the dead range's lower end), act_N = GA4's raw
# activeUsers of the window summed over the month's install days (UNclamped, uninstalled users included). `q` = the
# store's data-quality flags (thresholded / other / …) the snapshot was read with.
#
# THE COMEBACK IDENTITY. GA4 windows are cumulative DISTINCT users: act_k(E) = users who opened at least once in
# [E − w_k + 1, E]. Take two snapshots E1 < E2 with g = E2 − E1 days and a window j at E2 whose length is the window k
# at E1 plus g (w_j = w_k + g; consecutive months' windows are 30 or 31 days apart, so j = k + 1 when g = w_{k+1} − w_k).
# Both windows then start on the same day, so, exactly:
#       window_j(E2)  =  window_k(E1)  ∪  (E1, E2]
#       act_j(E2) − act_k(E1)  =  | opened in (E1, E2]  but NOT in window_k(E1) |  =: back_k
# back_k is a plain set difference — no uninstall bookkeeping, no clamp: everybody in it was INSTALLED on E1 (a user opens
# only while installed) and had not opened for ≥ k months at E1, and opened at least once in the next g days. That is the
# number we want: sleepers (dead ≥ k months at E1) who came back on their own. A user who opens in (E1, E2] and then
# uninstalls inside it still counts (he did open). A reinstall is a NEW GA4 user (new first-session day): never a comeback.
# The windows differ by exactly g days, so the pair of snapshots is picked per k with E2 − E1 = w_{k+1} − w_k (30 or 31).
# A pair even one day off adds or drops the one day at the window's edge — the users whose last open was that very day —
# and that is NOT small: on a synthetic population with known truth back_k came out 13–17% off at k = 1, 15–47% at
# k = 2 … 4 and over 100% off for the older sleepers (k ≥ 7), so such pairs are never used.
#
# THE SLEEPERS (the denominator) at E1 are dead_k(E1) = installed − alive_k — the Audience tab's own number — and, like
# the page, it is a RANGE: [dead_lo, dead]. The upper end counts every user who uninstalled inside the window as having
# opened in it (see "THE APPROXIMATION" above); a clean-up uninstall without an open makes dead read high by exactly those
# users. back_k does not depend on that approximation, only the rate does: rate = back ÷ dead (the page's number; the
# lower end of the rate), rate_max = back ÷ dead_lo (its upper end). The true rate is between them.
#
# A CELL is one install month: mature months only (the month's last day ≤ E1), so no install of the interval itself
# (those users opened on their install day and are not sleepers) enters act_j(E2). A month's back_k can wobble below 0
# (GA4's distinct counts are sketches, ±1–2% per install day; the month's sum averages some of it out): it is kept as
# is inside sums (clamping each month would bias the total up) and only the final total is floored at 0.
#
# WHAT AGGREGATES CANNOT TELL (stated, not hidden):
#   * WHO — only counts. Nothing follows a user from one snapshot to the next, so "came back" means "opened at least once
#     in the g days after E1", and a user can come back in two different intervals (when he went quiet again for ≥ k months).
#   * the exact sleep age — the rows are cumulative ("dead ≥ k months"), a mix of ages. The page's By-age brackets
#     (BANDS) are differences of rows (back_a − back_b over sleepers_a − sleepers_b); the two rows may come from pairs 30
#     and 31 days apart (an error of about one day's comebacks of the older sleepers — ~3% of back_b).
#   * the denominator's clean-up uninstallers — the range above.
#   * 12+ months asleep — the monthly windows stop at 12, and 12 → 15 months is a 91-day step, so ≥ 12 months is not
#     measured on the one-month step; it sits inside the open "7+" band.
#   * seasonality — one interval is one month; the chain below adds the months that follow each other (earliest first,
#     intervals never overlap; a snapshot missing at E1 + g just skips ahead to the next one that has its partner).
#   * noise — back_k is a small difference of two big sketched counts: a row is `enough` only with ≥ MIN_BACK comebacks
#     out of ≥ MIN_SLEEPERS sleepers.
#   The first number needs two snapshots 30 days apart: with daily snapshots, the 31st day of the history.

HIST_V = 1
HIST_FLAGS = ("thresholded", "other", "loss_other", "sampled", "truncated", "cov_off")
COMEBACK_KS = tuple(range(1, 12))       # dead ≥ k months, k = 1 … 11: the windows up to 12 months are 30–31 days apart
BANDS = ((1, 2), (2, 4), (4, 7), (7, None))   # months asleep — the page's "By age" brackets (frontend GROUPS)
MIN_BACK = 30                           # a row is quoted only with ≥ 30 comebacks …
MIN_SLEEPERS = 200                      # … out of ≥ 200 sleepers


def snapshot(out):
    """One complete read, derived (derive_app's result) → its compact history snapshot (the layout above). Install
    months without installs are left out; everything else is kept, every window."""
    months = [int(m) for m in out["months"]]
    rows = {}
    for mo, g in sorted(out["months_by"].items()):
        if g["installs"]:
            rows[mo] = [int(g["installs"]), int(g["installed"])] + [int(v) for v in g["alive"]] \
                + [int(v) for v in g["act"]] + [int(v) for v in g["dead_lo"]]
    flags = out.get("flags") or {}
    return {"months": months, "m": rows, "q": [f for f in HIST_FLAGS if flags.get(f)]}


def hist_append(hist, e, snap):
    """Add the snapshot of final day `e` (ISO) to `hist` (in place: {"v", "snaps": {E: snapshot}}) → True when added,
    False when that E is already there. A snapshot is never replaced and never dropped: the history only grows."""
    snaps = hist.setdefault("snaps", {})
    hist.setdefault("v", HIST_V)
    e = str(e)[:10]
    if e in snaps:
        return False
    snaps[e] = snap
    return True


def _view(e, snap):
    """A stored snapshot → its parts (the final day as a date, months → column, install month → ints)."""
    months = [int(v) for v in snap.get("months") or []]
    k = len(months)
    rows = {mo: [_int(v) for v in r] for mo, r in (snap.get("m") or {}).items() if len(r) >= 2 + 3 * k}
    return {"e": _d(e), "months": months, "K": k, "at": {n: i for i, n in enumerate(months)}, "rows": rows,
            "q": [str(f) for f in snap.get("q") or []]}


def _month_end(mo):
    y, m = int(mo[:4]), int(mo[5:7])
    return date(y, m, calendar.monthrange(y, m)[1])


def _measure(v1, v2, k):
    """{install month: [back, dead_lo, dead, installs drift]} for k months at v1's E1 and the next month's window at v2's
    E2 (the identity above), over the mature install months both snapshots have; None when a window is missing."""
    i1, i2 = v1["at"].get(k), v2["at"].get(k + 1)
    if i1 is None or i2 is None:
        return None
    out = {}
    for mo, r1 in v1["rows"].items():
        r2 = v2["rows"].get(mo)
        if r2 is None or _month_end(mo) > v1["e"]:
            continue
        out[mo] = [r2[2 + v2["K"] + i2] - r1[2 + v1["K"] + i1],          # act_{k+1}(E2) − act_k(E1)
                   r1[2 + 2 * v1["K"] + i1],                             # dead_lo_k(E1)
                   r1[1] - r1[2 + i1],                                   # dead_k(E1) = installed − alive_k
                   abs(r2[0] - r1[0])]
    return out


def _chain(dates, gap, ok):
    """Non-overlapping intervals [(E1, E2 = E1 + gap)] over the sorted snapshot days, earliest first: each next E1 is
    the first snapshot on or after the previous E2 whose partner E1 + gap exists (and ok(E1, E2))."""
    have, out, free = set(dates), [], None
    for d in dates:
        if free is not None and d < free:
            continue
        e2 = d + timedelta(days=gap)
        if e2 in have and ok(d, e2):
            out.append((d, e2))
            free = e2
    return out


def _sums(ivs):
    """Σ over intervals and months → back (raw), dead_lo, dead, installs drift, {install month: [back, lo, dead]}."""
    back = lo = hi = drift = 0
    by = {}
    for iv in ivs:
        for mo, (b, l, h, dr) in iv["m"].items():
            back, lo, hi, drift = back + b, lo + l, hi + h, drift + dr
            c = by.setdefault(mo, [0, 0, 0])
            c[0], c[1], c[2] = c[0] + b, c[1] + l, c[2] + h
    return back, lo, hi, drift, by


def _numbers(n, back, lo, hi, min_back, min_sleepers):
    """One table row's numbers from its counts: back (floored at 0; back_raw as summed), the sleepers' range, the rate
    on the page's dead number (rate) and on its lower end (rate_max), and whether the row can be quoted (enough)."""
    if not n:                                              # nothing measured yet: no numbers, not zeros
        return {"intervals": 0, "sleepers": None, "sleepers_lo": None, "back": None, "back_raw": None, "rate": None,
                "rate_max": None, "enough": False}
    b = max(0, back)
    return {"intervals": n, "sleepers": hi, "sleepers_lo": lo, "back": b, "back_raw": back, "rate": _ratio(b, hi),
            "rate_max": _ratio(b, lo), "enough": bool(back >= min_back and hi >= min_sleepers)}


def comeback(hist, min_back=MIN_BACK, min_sleepers=MIN_SLEEPERS):
    """One app's COMEBACK table (the identity and its limits above) from its history ({"v", "snaps": {E: snapshot}}, or
    the snaps dict itself): per months slept k = 1 … 11, the sleepers (dead ≥ k months) on each interval's first day E1,
    how many of them opened again within the next 30–31 days, and the rate. → {status, enough, ready_on, snapshots, first,
    last, rows, bands, by_month, flags, installs_drift, min_back, min_sleepers}:
      status    "no_history" (under 2 snapshots), "too_short" (no two snapshots exactly w_{k+1} − w_k days apart yet:
                ready_on = the first day one can exist), "thin" (measured, but no row has min_back comebacks out of
                min_sleepers sleepers), "ok". enough = (status == "ok").
      rows      [{slept k, gap_days, intervals n, span [first E1, last E2], sleepers (dead), sleepers_lo, back, back_raw,
                rate, rate_max, enough, q}] — cumulative: "slept ≥ k months".
      bands     the page's By-age brackets (BANDS) as differences of rows, over the intervals both rows have: [{label,
                from, to, intervals, sleepers, sleepers_lo, back, back_raw, rate, rate_max, enough}].
      by_month  {install month: {k: [back, dead_lo, dead]}} — the rows' sums split by install month (mature months).
      flags     the data-quality flags (q) of the snapshots behind the rows; installs_drift = the most users any row's
                months gained or lost in `installs` between the two snapshots of its intervals (0 normally).
    Pure: no I/O, no prints."""
    snaps = hist.get("snaps", hist) if isinstance(hist, dict) else {}
    views = {}
    for e, snap in snaps.items():
        try:
            v = _view(e, snap)
        except (TypeError, ValueError, AttributeError):
            continue
        views[v["e"]] = v
    dates = sorted(views)
    per = {}
    for k in COMEBACK_KS:
        gap = window_days(k + 1) - window_days(k)
        pairs = _chain(dates, gap, lambda a, b, k=k: bool(_measure(views[a], views[b], k)))
        per[k] = {"gap": gap, "ivs": [{"pair": (a, b), "m": _measure(views[a], views[b], k),
                                       "q": set(views[a]["q"]) | set(views[b]["q"])} for a, b in pairs]}
    rows, by_month, flags, drift = [], {}, set(), 0
    for k in COMEBACK_KS:
        gap, ivs = per[k]["gap"], per[k]["ivs"]
        if not ivs and not any(k in v["at"] and k + 1 in v["at"] for v in views.values()):
            continue                                       # this app has no such window (a young app's short list)
        back, lo, hi, dr, by = _sums(ivs)
        row = {"slept": k, "gap_days": gap, "span": None, "q": []}
        if ivs:
            q = set().union(*[iv["q"] for iv in ivs])
            row.update(span=[ivs[0]["pair"][0].isoformat(), ivs[-1]["pair"][1].isoformat()], q=sorted(q))
            flags |= q
        row.update(_numbers(len(ivs), back, lo, hi, min_back, min_sleepers))
        rows.append(row)
        drift = max(drift, dr)
        for mo, c in by.items():
            by_month.setdefault(mo, {})[str(k)] = c
    bands = []
    for a, b in BANDS:
        ks = [a] + ([b] if b else [])
        n = min([len(per[k]["ivs"]) for k in ks])
        band = {"label": "%d–%d months" % (a, b) if b else "%d+ months" % a, "from": a, "to": b}
        sa = _sums(per[a]["ivs"][:n])
        sb = _sums(per[b]["ivs"][:n]) if b else (0, 0, 0, 0, {})
        band.update(_numbers(n, sa[0] - sb[0], sa[1] - sb[1], sa[2] - sb[2], min_back, min_sleepers))
        bands.append(band)
    measured = any(r["intervals"] for r in rows)
    if len(dates) < 2:
        status = "no_history"
    elif not measured:
        status = "too_short"
    else:
        status = "ok" if any(r["enough"] for r in rows) else "thin"
    return {"v": HIST_V, "status": status, "enough": status == "ok",
            "ready_on": (dates[0] + timedelta(days=min(per[k]["gap"] for k in COMEBACK_KS))).isoformat()
            if dates and not measured else None,
            "snapshots": len(dates), "first": dates[0].isoformat() if dates else None,
            "last": dates[-1].isoformat() if dates else None, "rows": rows, "bands": bands,
            "by_month": dict(sorted(by_month.items())), "flags": sorted(flags), "installs_drift": drift,
            "min_back": min_back, "min_sleepers": min_sleepers}


def comeback_portfolio(results, min_back=MIN_BACK, min_sleepers=MIN_SLEEPERS):
    """Every app's comeback() result (a list; an entry with "err" or without rows is skipped) → the portfolio's table: per
    row and band the counts summed over the apps that have it (a rate from the sums, never an average of rates), the
    number of apps and intervals behind it, and the same status / enough / ready_on flags (ready_on: the earliest of the
    apps')."""
    ok = [r for r in results if isinstance(r, dict) and "err" not in r and "rows" in r]
    rows, bands = {}, {}
    for r in ok:
        for src, dst, key in ((r["rows"], rows, "slept"), (r["bands"], bands, "label")):
            for x in src:
                if not x.get("intervals"):
                    continue
                c = dst.setdefault(x[key], {f: x[f] for f in ((key, "gap_days") if key == "slept" else
                                                                  ("label", "from", "to"))})
                for f in ("apps", "intervals", "sleepers", "sleepers_lo", "back_raw"):
                    c[f] = c.get(f, 0) + (1 if f == "apps" else x[f])
    out_rows, out_bands = [], []
    for k in COMEBACK_KS:
        c = rows.get(k)
        if c:
            c.update(_numbers(c["intervals"], c["back_raw"], c["sleepers_lo"], c["sleepers"], min_back, min_sleepers))
            out_rows.append(c)
    for a, b in BANDS:
        label = "%d–%d months" % (a, b) if b else "%d+ months" % a
        c = bands.get(label) or {"label": label, "from": a, "to": b, "apps": 0}
        c.update(_numbers(c.get("intervals", 0), c.get("back_raw", 0), c.get("sleepers_lo", 0), c.get("sleepers", 0),
                          min_back, min_sleepers))
        out_bands.append(c)
    stats = [r["status"] for r in ok]
    measured = any(s in ("ok", "thin") for s in stats)
    if measured:
        status = "ok" if any(r["enough"] for r in out_rows) else "thin"
    else:
        status = "too_short" if any(s == "too_short" for s in stats) else "no_history"
    ready = [r["ready_on"] for r in ok if r.get("ready_on")]
    return {"v": HIST_V, "status": status, "enough": status == "ok", "ready_on": min(ready) if ready and not measured
            else None, "apps": len(ok), "measured_apps": sum(1 for s in stats if s in ("ok", "thin")),
            "skipped": len(results) - len(ok), "rows": out_rows, "bands": out_bands,
            "flags": sorted(set().union(*[set(r.get("flags") or []) for r in ok])),
            "min_back": min_back, "min_sleepers": min_sleepers}


def comeback_all(hists, min_back=MIN_BACK, min_sleepers=MIN_SLEEPERS):
    """{app key: its history} (fetch.ga4_audience.load_all_hist) → {"apps": {key: comeback(history)}, "portfolio":
    comeback_portfolio(...)}: the per-app and the portfolio "comeback by months slept" tables in one call."""
    apps = {k: comeback(h, min_back, min_sleepers) for k, h in sorted((hists or {}).items())}
    return {"apps": apps, "portfolio": comeback_portfolio(list(apps.values()), min_back, min_sleepers)}
