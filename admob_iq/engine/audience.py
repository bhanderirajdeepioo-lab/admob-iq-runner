"""Audience engine — pure math behind "dead users by months since their last open" (no I/O, no prints).

Inputs, one app:
  * its Audience store (admob_iq.fetch.ga4_audience): E = the latest FINAL activity day, windows = [w_1, w_2, …] days
    (window N = "the last N months" = [E − w_N + 1, E]), by_fsd = {install day X: [GA4 activeUsers of X in window N …]},
    dau_by_fsd = {X: activeUsers of X on day E}, plus GA4's own totals / "(other)" / "(not set)" and flags;
  * its Uninstall store (admob_iq.fetch.ga4_uninstall): daily[X].new (GA4 new users = installs of X) and
    cohorts[X][lag] (app_remove users of X on day X + lag). Pass engine.uninstall.fill_days(store) to read the cells
    exactly as the Uninstall tab does.

PER INSTALL DAY X (history_start ≤ X ≤ E), as of E:
  installs        n         = daily[X].new
  uninstalled     U         = Σ cohorts[X][lag], lag ≤ E − X
  installed       I         = n − U                                   (clamped at 0, marked un_gt_new)
  for window N (start S_N = E − w_N + 1):
    act(N)        = GA4 activeUsers of X in the window: everyone who opened the app at least once in it — INCLUDING
                    users who opened and then uninstalled inside the window (GA4 keeps them in the count; they are
                    not on a phone any more)
    un_in(N)      = Σ cohorts[X][lag] with S_N ≤ X + lag ≤ E — X's uninstalls INSIDE the window
    alive(N)      = act − un_in                                     (installed now AND opened in the last N months)
    dead(N)       = I − alive                                       (installed now, not opened for ≥ N months)

  THE APPROXIMATION (alive = act − un_in): every user who uninstalled inside the window is taken to have OPENED the app
  in the window before uninstalling, so all of them sit inside act and come out of it. A user who uninstalled without
  opening it first (a phone clean-up of an app not opened for months) was never in act: then alive reads LOW by those
  users and dead reads HIGH by the same number. So dead(N) is an UPPER bound. dead_lo(N) = I − min(act, I) is the
  LOWER bound (no window uninstaller had opened: every opener is still installed); the truth lies between, and both are
  in every total. Uninstalls BEFORE the window need nothing: those users can't open the app in it (a reinstall is a new
  GA4 user with a new first-session day).

  A YOUNG cell — X inside window N (installed less than N months ago) — opened the app on its install day, so alive = I
  and dead = 0 by definition; it is never computed from act (GA4's user counts are sketches: ±1–2% noise must not make a
  young day look dead). act of the young cells of window 1 vs their installs is kept as a split self-check (young_cov
  ≈ 1: every new user is active on day one).

  CLAMPS, each counted with the users it moved (marks[code] = [cells, users]):
    un_gt_new    U > n                — installed would be < 0 → 0                        IMPOSSIBLE
    act_gt_inst  act − un_in > I      — more users opened (still installed) than are installed → I   IMPOSSIBLE
    un_gt_act    un_in > act          — alive would be < 0 → 0 (the approximation's floor: more window uninstalls
                                        than openers — the clean-up uninstallers above)
    non_mono     alive(N) < alive(N−1) — a longer window can't hold fewer users → raised to alive(N−1) (sketch noise,
                                        or the approximation: un_in grows with the window too)
  A window the store does not have (the store's windows stop short of the Uninstall history) for a cell that is not
  young is MISSING: that window's totals are None, never guessed (fetch.ga4_audience re-reads such an app).

BUCKETS (dead for … months): "1".."6" = dead(N) − dead(N+1); "7-12" = dead(7) − dead(12); "12+" = dead(12) (the demo's
bucket_of: whole months since the last open, 7–11 → "7-12", 12 and more → "12+"). dead(N) never rises with N (alive
never falls), so no bucket is negative. Windows past the store's last one — whose last window already holds every
install day — are all young: dead 0.

GROUPS: install day → install month ("YYYY-MM") → app → portfolio (sums; a ratio is computed from the sums, never
averaged). MOST dead / active install month, by count and by share of the month's installs, over MATURE months only (no
install day inside window 1 — the newest month's installs all opened within the month by definition), and for the
share only months with ≥ max(MIN_MONTH_INSTALLS, MIN_MONTH_SHARE of all installs) installs (a few test installs must not
win). "dead" = dead(1) (installed, not opened in the last month), "active" = alive(1). DAU on E by install month:
dau_by_fsd summed by month; users installed before the history ("before_history"), "(other)" and "(not set)" shown apart.
"""

from datetime import date

MONTH_DAYS = 365.25 / 12              # window N = floor(N × 30.4375) days: 30, 60, 91, 121, 152, 182, … 365 (N = 12)
BUCKETS = (("1", 1, 2), ("2", 2, 3), ("3", 3, 4), ("4", 4, 5), ("5", 5, 6), ("6", 6, 7), ("7-12", 7, 12),
           ("12+", 12, None))         # (label, dead(lo) − dead(hi); hi None: dead(lo) itself)
BUCKET_N = 12                         # every result carries windows 1..12 at least (the buckets need them)
MIN_MONTH_INSTALLS = 100              # "most … by share": a month needs ≥ 100 installs …
MIN_MONTH_SHARE = 0.01                # … and ≥ 1% of the group's installs
IMPOSSIBLE = ("un_gt_new", "act_gt_inst")
CLAMPED = ("un_gt_act", "non_mono")
MARKS = IMPOSSIBLE + CLAMPED
ARRAYS = ("act", "un_in", "alive", "dead", "dead_lo", "young", "missing")


def window_days(n):
    """Days in window N ("the last N months"): floor(N × 30.4375) — 30, 60, 91, 121, …, 365 for N = 12."""
    return int(n * MONTH_DAYS)


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
    g = {"days": 0, "installs": 0, "uninstalled": 0, "installed": 0, "marks": {m: [0, 0] for m in MARKS}}
    for a in ARRAYS:
        g[a] = [0] * k
    return g


def _add(g, c):
    for f in ("days", "installs", "uninstalled", "installed"):
        g[f] += c[f]
    for a in ARRAYS:
        dst, src = g[a], c[a]
        if len(dst) < len(src):
            dst.extend([0] * (len(src) - len(dst)))
        for i, v in enumerate(src):
            dst[i] += v
    for m, (n, u) in c["marks"].items():
        g["marks"][m][0] += n
        g["marks"][m][1] += u


def _mark(mk, code, users):
    mk[code][0] += 1
    mk[code][1] += int(users)


def day_cell(x, n, lags, act, end, wd, m):
    """One install day → its cell (the module docstring's rules). x: the day; n: its installs; lags: [(lag, users)];
    act: GA4's actives per window (the store's m windows); wd: days of windows 1..K (K ≥ m). → a one-day group plus
    the per-window marks {N: code} of this day."""
    k, age = len(wd), (end - x).days
    c = _group(k)
    c["days"], c["installs"] = 1, n
    mk, codes = c["marks"], {}
    u_all = sum(u for lag, u in lags if 0 <= lag <= age)
    inst = n - u_all
    if inst < 0:
        _mark(mk, "un_gt_new", -inst)
        codes[0] = "un_gt_new"                         # 0: the install day itself (not a window)
        inst = 0
    c["uninstalled"], c["installed"] = u_all, inst
    prev = 0
    for i, w in enumerate(wd):
        if age < w:                                    # young: installed inside the window, opened on its first day
            c["alive"][i], c["young"][i], c["un_in"][i] = inst, 1, u_all
            c["act"][i] = act[i] if i < m else 0
            prev = inst
            continue
        if i >= m:                                     # not young, and the store has no such window
            c["missing"][i] = 1
            continue
        first = age - w + 1                            # lags ≥ first fall inside [E − w + 1, E]
        un_in = sum(u for lag, u in lags if first <= lag <= age)
        a = act[i]
        alive = a - un_in                              # the approximation (module docstring)
        if alive < 0:
            _mark(mk, "un_gt_act", -alive)
            codes[i + 1] = "un_gt_act"
            alive = 0
        if alive > inst:
            _mark(mk, "act_gt_inst", alive - inst)
            codes[i + 1] = "act_gt_inst"
            alive = inst
        if alive < prev:
            _mark(mk, "non_mono", prev - alive)
            codes.setdefault(i + 1, "non_mono")
            alive = prev
        dead = inst - alive
        c["act"][i], c["un_in"][i], c["alive"][i], c["dead"][i] = a, un_in, alive, dead
        c["dead_lo"][i] = min(dead, inst - min(a, inst))   # the lower bound (never above the estimate)
        prev = alive
    return c, codes


def _buckets(dead):
    out = {}
    for lab, lo, hi in BUCKETS:
        a = dead[lo - 1] if lo - 1 < len(dead) else 0
        b = (dead[hi - 1] if hi - 1 < len(dead) else 0) if hi else 0
        out[lab] = None if a is None or b is None else a - b
    return out


def finish(g):
    """A summed group → its output: windows with a missing cell become None (never a partial sum), the buckets, the
    shares (of installs; dead also of installed), and the marks split into impossible / clamped."""
    out = {f: g[f] for f in ("days", "installs", "uninstalled", "installed")}
    miss = g["missing"]
    for a in ("act", "un_in", "alive", "dead", "dead_lo"):
        out[a] = [None if miss[i] else v for i, v in enumerate(g[a])]
    out["young_days"] = list(g["young"])
    out["missing_days"] = list(miss)
    out["buckets"] = _buckets(out["dead"])
    out["buckets_lo"] = _buckets(out["dead_lo"])        # (from the lower-bound curve: a range, not a bound per bucket)
    out["dead_share"] = [_ratio(v, g["installs"]) for v in out["dead"]]
    out["alive_share"] = [_ratio(v, g["installs"]) for v in out["alive"]]
    out["impossible"] = {m: list(g["marks"][m]) for m in IMPOSSIBLE if g["marks"][m][0]}
    out["clamped"] = {m: list(g["marks"][m]) for m in CLAMPED if g["marks"][m][0]}
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
            if g["young_days"][0] or not g["installs"] or g[key][0] is None:
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
    apart; checked against the Uninstall store's daily actives of E (cov)."""
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


def derive_app(aud, uni, per_day=False):
    """One app's Audience numbers (module docstring) from its Audience store `aud` and its Uninstall store `uni`. →
    {E, history_start, windows (days of windows 1..K), months_n K, full, installs … (the app's group), months
    {YYYY-MM: group}, most, dau, checks, flags} (+ per_day {X: …} when asked)."""
    end, hs = _d(aud["E"]), _d(uni["history_start"])
    w = [int(v) for v in aud.get("windows") or []]
    m = len(w)
    k = max(m, BUCKET_N)
    wd = w + [window_days(i + 1) for i in range(m, k)]
    full = bool(w) and (end - hs).days < w[-1]         # the last window already holds every install day
    daily, cells, by = uni.get("daily") or {}, uni.get("cohorts") or {}, aud.get("by_fsd") or {}
    lo, hi = hs.isoformat(), end.isoformat()
    days = sorted(x for x in set(daily) | set(by) if lo <= x <= hi)
    app, months, per = _group(k), {}, {}
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
        c, codes = day_cell(_d(x), n, lags, act, end, wd, m)
        _add(app, c)
        _add(months.setdefault(x[:7], _group(k)), c)
        if m and c["young"][0]:
            young1[0] += act[0]
            young1[1] += n
        if per_day:
            miss = c["missing"]
            per[x] = {"n": n, "U": c["uninstalled"], "I": c["installed"], "act": c["act"][:m],
                      "alive": [None if miss[i] else v for i, v in enumerate(c["alive"])],
                      "dead": [None if miss[i] else v for i, v in enumerate(c["dead"])],
                      "marks": {str(kk): v for kk, v in codes.items()}}
    out = finish(app)
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
                 un_incomplete_days=len(inc), un_unplaced=unpl, history_capped=bool(uni.get("history_capped")),
                 impossible_cells=sum(v[0] for v in out["impossible"].values()),
                 clamped_cells=sum(v[0] for v in out["clamped"].values()))
    mos = {mo: finish(g) for mo, g in sorted(months.items())}
    for g in [out] + list(mos.values()):
        g["act"] = g["act"][:m]                        # GA4's own count exists for the store's windows only
    out.update(E=hi, history_start=lo, windows=wd, months_n=k, full=full, months=mos, flags=flags,
               ga4_total=tot, other=oth, not_set=nst, before_history=before,
               checks={"young_cov": _ratio(young1[0], young1[1]),       # window 1's install days: actives ÷ installs
                       "split_cov": [_ratio(split[i], _int(tot[i])) if i < len(tot) and tot[i] else None
                                     for i in range(m)]})               # Σ rows ÷ GA4's TOTAL, per window
    out["most"] = most(mos, out["installs"])
    out["dau"] = dau_split(aud, lo, daily)
    if per_day:
        out["per_day"] = per
    return out


def _extend(g, k, full):
    """An app's (or month's) finished group → its sums on k windows: past its own, a full app's install days are all
    young (alive = installed, dead 0); otherwise unknown (None)."""
    out = dict(g)
    for a in ("alive", "dead", "dead_lo", "un_in"):
        v = list(g[a])
        extra = {"alive": g["installed"], "dead": 0, "dead_lo": 0, "un_in": g["uninstalled"]}[a] if full else None
        out[a] = v + [extra] * (k - len(v))
    out["young_days"] = list(g["young_days"]) + ([g["days"]] if full else [0]) * (k - len(g["young_days"]))
    return out


def _sum_lists(dst, src):
    for i, v in enumerate(src):
        dst[i] = None if dst[i] is None or v is None else dst[i] + v


def portfolio(apps):
    """Every app's derive_app result (a list; an entry with "err" is skipped) → the portfolio: the summed group (per
    window, an app without that window counts as young when its own windows held all its history, else the window
    is None), calendar install months summed across apps, the most dead / active month, the DAU on each app's E by
    install month, and the apps' E range."""
    ok = [a for a in apps if isinstance(a, dict) and "err" not in a and "installs" in a]
    k = max([a["months_n"] for a in ok] + [BUCKET_N])
    tot = {"days": 0, "installs": 0, "uninstalled": 0, "installed": 0, "alive": [0] * k, "dead": [0] * k,
           "dead_lo": [0] * k, "un_in": [0] * k, "young_days": [0] * k}
    months, marks = {}, {}
    dau = {"users": 0, "by_month": {}, "before_history": 0, "other": 0, "not_set": 0}
    for a in ok:
        for src, dst in [(a, tot)] + [(g, months.setdefault(mo, {f: 0 for f in ("days", "installs", "uninstalled",
                                                                                  "installed")}))
                                      for mo, g in a["months"].items()]:
            e = _extend(src, k, a["full"])
            for f in ("days", "installs", "uninstalled", "installed"):
                dst[f] += e[f]
            for f in ("alive", "dead", "dead_lo", "un_in", "young_days"):
                if f not in dst:
                    dst[f] = [0] * k
                _sum_lists(dst[f], e[f])
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
    for g in [tot] + list(months.values()):
        g["buckets"] = _buckets(g["dead"])
        g["buckets_lo"] = _buckets(g["dead_lo"])
        g["dead_share"] = [_ratio(v, g["installs"]) for v in g["dead"]]
        g["alive_share"] = [_ratio(v, g["installs"]) for v in g["alive"]]
    dau["by_month"] = dict(sorted(dau["by_month"].items()))
    es = sorted(a["E"] for a in ok)
    return dict(tot, apps=len(ok), skipped=len(apps) - len(ok), months_n=k, windows=[window_days(i + 1) for i in range(k)],
                E_min=es[0] if es else None, E_max=es[-1] if es else None,
                months=dict(sorted(months.items())), most=most(months, tot["installs"]), dau=dau,
                marks=marks)

