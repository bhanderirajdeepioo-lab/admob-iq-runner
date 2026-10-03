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
"""

from datetime import date

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
    """Every app's derive_app result (a list; an entry with "err" is skipped) → the portfolio on the union of their
    months (an app without one of them: young past its own last window when that window held all its history, else
    None), calendar install months summed across apps, the last-open buckets, the most dead / active month, the DAU on
    each app's E by install month, the marks, and the apps' E range."""
    ok = [a for a in apps if isinstance(a, dict) and "err" not in a and "installs" in a]
    glob = sorted({mo for a in ok for mo in a["months"]}) or [1]
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
