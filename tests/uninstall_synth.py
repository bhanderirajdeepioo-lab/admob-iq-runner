"""Synthetic GA4 for the Uninstall-tab tests and the frontend fixture — no network, no real data.

  * make_store(...)  → one app's store exactly as fetch.ga4_uninstall writes it (engine tests).
  * Truth            → one app's GA4 "reality": installs, per-install-day uninstall cells, actives,
                       updates, versions. Mutable, so late GA4 data can be simulated.
  * UniStub          → a Ga4App whose runReport answers from a Truth: honours the dimensions, the
                       event filter, the date range, orderBys and limit/offset paging, and checks every
                       request is pinned to the app's Android stream.
  * AdminFake        → the Admin API (accountSummaries / dataStreams / property meta) per owner token.
"""

import math
import random
import re
from datetime import date, timedelta

from admob_iq.fetch import ga4

END = date(2026, 9, 19)                   # the last settled GA4 day in most engine tests
# uninstalling users per 1,000 installs ON lag day N — D0 60%, D1 72%, D2 80%, D7 88.7%, D14 90.5%, D30
# 92.1%, then a thin tail to 93.1% by D60 (well under 100%, even with rounding and noise)
BASE_LAGS = {0: 600, 1: 120, 2: 80, 3: 30, 4: 20, 5: 15, 6: 12, 7: 10, 8: 4, 9: 3, 10: 3, 11: 2, 12: 2, 13: 2, 14: 2}
BASE_LAGS.update({n: 1 for n in range(15, 31)})
BASE_LAGS.update({n: 1 for n in range(33, 61, 3)})


def iso(d):
    return d.isoformat()


def make_store(days, new_per_day=1000, lags=None, bump=None, end=END, a28=100000, rate_fn=None, upd=None,
               versions=None, app_id="ca-app-pub-0000000000000000~0000000001", package="com.synthetic.app"):
    """`days` of history ending at `end`. new_per_day: int or fn(date). lags: {lag: per 1,000 installs}.
    bump: fn(install date) → {lag: ± per 1,000} added for that install day. a28: int or fn(date).
    rate_fn: fn(date) → uninstall rate per 1,000 a28 users (daily series, independent of the cells here).
    upd: fn(date) → app_update users. versions: fn(date) → {version: active users}."""
    lags = BASE_LAGS if lags is None else lags
    hs = end - timedelta(days=days - 1)
    daily, cohorts, vers = {}, {}, {}
    for i in range(days):
        c = hs + timedelta(days=i)
        n = new_per_day(c) if callable(new_per_day) else new_per_day
        per = dict(lags)
        for lag, u in ((bump(c) if bump else None) or {}).items():
            per[lag] = per.get(lag, 0) + u
        cells = {}
        for lag, u in per.items():
            if lag <= (end - c).days:
                v = int(round(n * u / 1000.0))
                if v:
                    cells[str(lag)] = v
        if cells:
            cohorts[iso(c)] = cells
        a = a28(c) if callable(a28) else a28
        r = rate_fn(c) if rate_fn else 5.0
        un = int(round(r * a / 1000.0))
        daily[iso(c)] = {"new": n, "a1": a // 4, "a28": a, "un": un, "un_ev": un, "upd": upd(c) if upd else 0}
        if versions:
            vers[iso(c)] = versions(c)
    from admob_iq.fetch.ga4_uninstall import STORE_V
    return {"v": STORE_V, "app_id": app_id, "package": package, "property_id": "p", "stream_id": "s",
            "time_zone": "Asia/Kolkata", "den": "a28", "history_start": iso(hs), "window_end": iso(end),
            "history_capped": False, "covered": [[iso(hs), iso(end)]], "daily": daily, "cohorts": cohorts,
            "unplaced": {}, "versions": vers,
            "flags": {"truncated": [], "thresholded": False, "kept_old_before": None},
            "full_at": "2026-09-21T01:00:00Z", "fetched_at": "2026-09-21T01:00:00Z",
            "next_rebuild": iso(end + timedelta(days=30))}


def rollout(first="1.0", rels=(), speed=0.3, cap=0.97):
    """Version shares by day → fn(day) → {version: share}: from each release (day, version[, speed[, cap]]) the new
    version takes `speed` more of the users every day, up to `cap`, from the versions before it."""
    def shares(d):
        out = {first: 1.0}
        for r in rels:
            day, v = r[0], r[1]
            sp, cp = (r[2] if len(r) > 2 else speed), (r[3] if len(r) > 3 else cap)
            if d >= day:
                x = min(cp, sp * ((d - day).days + 1))
                out = {k: y * (1 - x) for k, y in out.items()}
                out[v] = out.get(v, 0.0) + x
        return out
    return shares


def make_impact_store(days=120, end=END, new=2000, rho=None, old=30000, act=None, versions=None, spu=None, tpu=None,
                      ipu=None, ecpm=None, noise=0.0, seed=1, weekend=1.0, split=True, bump=None, lags=None,
                      tz="Asia/Kolkata", rev_tz=None, revenue=True, ret_ok=None, ret_from=None, upd=None,
                      app_id="ca-app-pub-0000000000000000~0000000001", noise_ar=0.0):
    """One app's store WITH the update-impact data (usage, vuse, ret, versions, impact_v) as the fetch writes it, and
    its AdMob revenue → (store, revenue). Every number adds up like GA4's: a day's actives = its installs + the recent
    installs coming back (exactly the cohorts' day-k actives) + the older users' activity.
    new: int or fn(day) installs · rho: fn(install day, k) → share back on day k (default DEFAULT_RET) · old: int or
    fn(day) older users active a day · act: fn(day, version) → their activity × on that version · versions: fn(day) →
    {version: share} (rollout) · spu / tpu: fn(day, version, is_new) → sessions / seconds per user · ipu: fn(day,
    version) → ad impressions per user (default 4) · ecpm: fn(day) → USD per 1,000 impressions (default 2) · noise: the
    lognormal day-to-day noise of every per-day number (old users, per-user usage, impressions) · weekend: the weekend
    × of the older users' activity · split False: GA4 could not split new / returning by version · bump / lags: the
    uninstall cells (make_store) · ret_ok: fn(install day) → the cohort read complete · revenue False: no AdMob
    revenue; rev_tz: the AdMob report's timezone (default the store's) · upd: fn(day) → app_update users · noise_ar: the
    day-to-day persistence of that noise (AR(1): 0 = independent days; ~0.9 = like live returning DAU, whose weekly change
    of one day and the next correlate ~0.87 — a level that drifts for days)."""
    rnd = random.Random(seed)
    newf = new if callable(new) else (lambda c: new)
    rhof = rho or (lambda c, k: DEFAULT_RET(k))
    oldf = old if callable(old) else (lambda d: old)
    verf = versions or (lambda d: {"1.0": 1.0})
    st = make_store(days, newf, lags=lags, bump=bump, end=end, app_id=app_id, upd=upd)
    st["time_zone"] = tz
    hs = end - timedelta(days=days - 1)
    dl = [hs + timedelta(days=i) for i in range(days)]

    arst = {}

    def nz(series=""):
        if not noise:
            return 1.0
        if not noise_ar:
            return math.exp(rnd.gauss(0, noise) - noise * noise / 2)
        e = noise_ar * arst.get(series, 0.0) + math.sqrt(1 - noise_ar * noise_ar) * rnd.gauss(0, noise)
        arst[series] = e
        return math.exp(e - noise * noise / 2)
    ret, usage, vuse, vers, rev_days = {}, {}, {}, {}, {}
    for c in dl:
        n = newf(c)
        m = min(30, (end - c).days)
        ret[c.isoformat()] = {"t": n, "a": [n] + [int(n * rhof(c, k)) for k in range(1, m + 1)], "cov": 1.0,
                              "ok": True if ret_ok is None else bool(ret_ok(c)), "at": end.isoformat()}
    for d in dl:
        n = newf(d)
        y = sum(int(newf(d - timedelta(days=k)) * rhof(d - timedelta(days=k), k)) for k in range(1, 31))
        sh = verf(d)
        o = oldf(d) * (weekend if d.weekday() >= 5 else 1.0) * nz("old")
        per = {v: (int(round(n * x)), int(round(y * x + o * x * (act(d, v) if act else 1.0)))) for v, x in sh.items()}
        st["daily"][d.isoformat()]["a1"] = n + sum(b for _, b in per.values())
        u = {"n": [0, 0, 0], "r": [0, 0, 0], "o": [0, 0, 0]}
        vu, imp = {}, 0.0
        pz = nz("use")
        for v, (an, ar) in per.items():
            sn = int(round(an * (spu(d, v, True) if spu else 1.6)))
            tn = int(round(an * (tpu(d, v, True) if tpu else 150.0)))
            sr = int(round(ar * (spu(d, v, False) if spu else 2.4) * pz))
            tr = int(round(ar * (tpu(d, v, False) if tpu else 280.0) * pz))
            if not split:
                an, sn, tn, ar, sr, tr = 0, 0, 0, an + ar, sn + sr, tn + tr
            vu[v] = [an, sn, tn, ar, sr, tr]
            imp += (an + ar) * (ipu(d, v) if ipu else 4.0)
            for j, x in enumerate((an, sn, tn)):
                u["n"][j] += x
            for j, x in enumerate((ar, sr, tr)):
                u["r"][j] += x
        if not split:                          # usage itself still splits new / returning (its own report)
            nn = st["daily"][d.isoformat()]["new"]
            u["n"] = [nn, int(round(nn * 1.6)), int(round(nn * 150.0))]
            u["r"] = [u["r"][0] - nn, u["r"][1] - u["n"][1], u["r"][2] - u["n"][2]]
        usage[d.isoformat()], vuse[d.isoformat()] = u, vu
        vers[d.isoformat()] = {v: a + b for v, (a, b) in per.items() if a + b}
        imp *= nz("imp")
        rev_days[d.isoformat()] = [int(round(imp * (ecpm(d) if ecpm else 2.0) / 1000 * 1e6)), int(round(imp))]
    st.update(usage=usage, vuse=vuse, versions=vers, ret=ret, impact_v=1,
              ret_from=(ret_from or hs).isoformat(), ret_to=hs.isoformat())
    st["flags"]["impact"] = {"vuse_split": split, "ret_k": 1.0, "usage_kept": 0, "vuse_kept": 0,
                             "thresholded": False, "ret_short": {k: 1.0 for k, e in ret.items() if not e["ok"]}}
    rv = None
    if revenue:
        rv = {"tz": rev_tz or tz, "currency": "USD", "till": end.isoformat(), "days": rev_days}
    return st, rv


def run_daily(store, first, last, app_id="ca-app-pub-0000000000000000~0000000001", app="App", state=None):
    """The daily build, day after day: evaluate_app with window_end = each day from `first` to `last`, and
    after every run each alert that was due is marked sent (as mark_notified does) → (sent, state), sent =
    [(E, severity, family, text)] — every notification the owner would have got, in order."""
    from admob_iq.engine import uninstall as eng
    state = {} if state is None else state
    sent, E = [], first
    while E <= last:
        d, _ = eng.evaluate_app(dict(store, window_end=E.isoformat()), app_id, app, state, E.isoformat() + "T12:00:00Z")
        due = {a["id"]: a for a in d["alerts"] if a["notify"]}
        sent += [(E.isoformat(), a["severity"], a["family"], a["text"]) for a in due.values()]
        for ep in state.get("episodes", {}).values():
            if ep["id"] in due:
                ep["notified_at"] = E.isoformat() + "T12:00:00Z"
        E += timedelta(days=1)
    return sent, state


def rate_year(store, days=365):
    """run_daily for the daily-RATE alerts only (spikes, zero days, drift) over the store's last `days` days —
    the same engine steps evaluate_app takes (advance_streaks → rate_ready → update_episodes), without the
    cohort math, so a year of noise runs in a fraction of a second → {family: notifications}."""
    from admob_iq.engine import uninstall as eng
    ds = eng.daily_series(store)
    state, streak, since = {}, {}, {}
    out = {"rate_drift": 0, "rate_spike": 0, "rate_zero": 0}
    for n in range(ds["n"] - days + 1, ds["n"] + 1):
        E = ds["start"] + timedelta(days=n - 1)
        drift = eng.drift_now(ds, n)
        eng.advance_streaks(streak, since, {"drift|up": bool(drift and drift["dir"] == "up"),
                                            "drift|down": bool(drift and drift["dir"] == "down")}, E)
        first = n == ds["n"] - days + 1
        for ep in eng.update_episodes(state, "a", E, eng.rate_ready(ds, drift, "a", streak, since, E, first, n),
                                      True, first, "now"):
            if ep["notified_at"] is None:
                out[ep["family"]] += 1
                ep["notified_at"] = "sent"
    return out


def noisy_store(sigma, seed, days=400, end=END, a28=100000, rate=5.0, weekend=1.07, poisson=False):
    """A STEADY app (nothing changes) whose daily uninstalls wobble: lognormal day-to-day noise `sigma` and a
    weekend bump, or pure counting (Poisson) noise → make_store."""
    rnd = random.Random(seed)
    memo = {}

    def rate_fn(c):
        if c not in memo:
            r = rate * (weekend if c.weekday() >= 5 else 1.0) * math.exp(rnd.gauss(0, sigma) - sigma * sigma / 2)
            if poisson:
                lam, k, t = r * a28 / 1000, 0, rnd.expovariate(1.0)
                while t < lam:
                    k, t = k + 1, t + rnd.expovariate(1.0)
                r = k * 1000 / a28
            memo[c] = r
        return memo[c]
    return make_store(days, 1000, end=end, a28=a28, rate_fn=rate_fn)


def truth_store(truth, end, app_id="ca-app-pub-0000000000000000~0000000001"):
    """What the full GA4 fetch stores for a Truth (installs, uninstalls and cells that add up, like real
    GA4 — make_store's daily uninstalls are independent of its cells)."""
    from admob_iq.fetch import ga4_uninstall as gu
    st = gu.fetch_full(UniStub(truth, "tok", "p", "s"), end, 1300)
    st.update(app_id=app_id, package="com.synthetic.app", property_id="p", stream_id="s", time_zone="UTC",
              fetched_at="2026-09-21T01:00:00Z")
    return st


# ── the fake GA4 Data API ────────────────────────────────────────────────────────────────────────

def ymd(d):
    return d.strftime("%Y%m%d")


class Truth:
    """One app's GA4 reality from `start` to `end`. cells[(install day | "(other)" , event day)] = users.
    Users whose first session is before `start` (old installs) uninstall too: `old[d]` per event day.
    LATE DATA: with `asof` (the fetch's day) and `late` = fn(age in days) → share of a day's app_remove GA4
    already shows (`late_new` the same for newUsers), every report answers with what has arrived by then.
    `short` = fn(start, end) → share of the cells a firstSessionDate × date report over that range returns
    (the live undercount of long ranges); `short_day` = {event day: share} short at ANY range; `other` =
    fn(start, end) → share of every cell folded into one "(other)" row per event day (GA4's high-cardinality
    answer: the users are all there, their install day is not). Those three hit the users AND the events
    (eventCount) cells alike. `users_day` = fn(event day) → share of the USERS cells only (the live loss of
    users by install day on days older than ~2 months, at any range); `events_day` = fn(event day) → share of
    the EVENTS cells only (~85% on recent days on some apps). A cell of u users has u + u // 20 events (ev)."""

    def __init__(self, start, end, new, lags=None, bump=None, old_per_day=0, hazard_x=None, upd=None,
                 versions=None, active_frac=0.25, a28_frac=0.5, base0=None, seed=7, noise=0.0, ret=None, old_act=None,
                 spu=None, tpu=None):
        self.start, self.end = start, end
        self.reject_a28 = False
        self.reject_nvr = False               # the property rejects newVsReturning with appVersion (HTTP 400)
        self.ret, self.ret_day = ret, None    # ret(install day, N) → share back on day N; ret_day(age) → share of a
        self.spu, self.tpu = spu, tpu         # cohort GA4 still returns (user data lost by age); sessions / seconds
        self.thresholded = False              # per user: fn(day, version, is_new)
        self.asof = self.late = self.late_new = self.short = self.other = self.users_day = self.events_day = None
        self.short_day = {}
        self.new, self.cells, self.old, self.upd, self.vers = {}, {}, {}, {}, {}
        self.a1, self.a28 = {}, {}
        rnd = random.Random(seed)
        lags = BASE_LAGS if lags is None else lags
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        for c in days:
            n = new(c) if callable(new) else new
            self.new[c] = n
            per = dict(lags)
            for lag, u in ((bump(c) if bump else None) or {}).items():
                per[lag] = per.get(lag, 0) + u
            for lag, u in per.items():
                d = c + timedelta(days=lag)
                if d > end:
                    continue
                x = (hazard_x(d, lag) if hazard_x else 1.0) * u
                if noise:
                    x *= max(0.0, 1 + rnd.gauss(0, noise))
                v = int(round(n * x / 1000.0))
                if v > 0:
                    self.cells[(c, d)] = self.cells.get((c, d), 0) + v
        for d in days:
            self.old[d] = old_per_day(d) if callable(old_per_day) else old_per_day
            self.upd[d] = upd(d) if upd else 0
        un = self.un_by_day()
        # actives: everyone who opened the app in the window (a new install counts, even if it left the
        # same day) + a share of the installed base (users from before `start` included)
        # (ret: the day's actives = its installs + the recent installs coming back — exactly what the cohort report
        # answers — + the older users' activity × old_act(day); without ret the old formula, unchanged)
        base = float(20 * self.new[days[0]] if base0 is None else base0)
        for i, d in enumerate(days):
            base = max(0.0, base + self.new[d] - un.get(d, 0))
            last28 = sum(self.new[x] for x in days[max(0, i - 27):i + 1])
            if ret is None:
                self.a1[d] = int(self.new[d] + base * active_frac)
            else:
                back = sum(self.back(d - timedelta(days=k), k) for k in range(1, 31))
                recent = sum(self.new.get(d - timedelta(days=k), 0) for k in range(31))
                self.a1[d] = int(self.new[d] + back + max(0.0, base - recent) * active_frac * (old_act(d) if old_act else 1))
            self.a28[d] = int(last28 + base * a28_frac)
            if versions:
                self.vers[d] = versions(d, self.a1[d])
            elif self.a1[d]:
                self.vers[d] = {"1.0": self.a1[d]}

    def ret_share(self, c, k):
        return self.ret(c, k) if self.ret else DEFAULT_RET(k)

    def back(self, c, k):
        """Users of install day c active on day k after it (k ≥ 1) — the cohort report's cohortActiveUsers."""
        return int(self.new.get(c, 0) * self.ret_share(c, k))

    def use_split(self, d):
        """[(version, "new" | "returning", active users, sessions, engagement seconds)] of day d: new and returning
        users spread over the day's versions by their shares (largest remainder: whole users adding up exactly)."""
        a1 = self.a1.get(d, 0)
        new = min(self.new.get(d, 0), a1)
        vers = self.vers.get(d) or ({"1.0": a1} if a1 else {})
        tot = sum(vers.values())
        out = []
        for nvr, n in (("new", new), ("returning", a1 - new)):
            if not n or not tot:
                continue
            raw = [(v, u * n / tot) for v, u in sorted(vers.items())]
            got = {v: int(x) for v, x in raw}
            for v, x in sorted(raw, key=lambda vx: (int(vx[1]) - vx[1], vx[0]))[:n - sum(got.values())]:
                got[v] += 1
            for v, u in sorted(got.items()):
                if u:
                    isnew = nvr == "new"
                    sp = self.spu(d, v, isnew) if self.spu else (1.6 if isnew else 2.4)
                    tp = self.tpu(d, v, isnew) if self.tpu else (150.0 if isnew else 280.0)
                    out.append((v, nvr, u, int(round(u * sp)), int(round(u * tp))))
        return out

    def cohort_rows(self, cohorts):
        """The cohort report of `cohorts` [(name, install day)]: day 0..30 up to the data's last day, empty rows left
        out (as GA4 does), every count × ret_day(the cohort's age) — user data GA4 no longer keeps."""
        out = []
        top = self.end if not self.asof else min(self.end, self.asof - timedelta(days=1))
        for name, c in cohorts:
            n = self.new.get(c, 0)
            if not n:
                continue
            loss = self.ret_day(((self.asof or self.end) - c).days) if self.ret_day else 1.0
            tot = int(n * loss)
            for k in range(min(30, (top - c).days) + 1):
                a = int((n if k == 0 else self.back(c, k)) * loss)
                if a or k == 0 and tot:
                    out.append(({"cohort": name, "cohortNthDay": "%04d" % k},
                                {"cohortActiveUsers": a, "cohortTotalUsers": tot}))
        return out

    def un_by_day(self, cells=None, old=None):
        """app_remove users per event day (every install day + the old installs)."""
        out = dict(self.old if old is None else old)
        for (c, d), u in (self.cells if cells is None else cells).items():
            out[d] = out.get(d, 0) + u
        return out

    def _share(self, fn, d):
        return 1.0 if not (fn and self.asof) else min(1.0, max(0.0, fn((self.asof - d).days)))

    def seen(self):
        """(cells, old) as GA4 shows them on `asof`: each event day's app_remove users scaled to late(age),
        spread over its cells by largest remainder, so a day's cells always add up to its events total."""
        if not (self.late and self.asof):
            return self.cells, self.old
        by_day = {}
        for k, u in self.cells.items():
            by_day.setdefault(k[1], []).append((k, u))
        for d, u in self.old.items():
            if u:
                by_day.setdefault(d, []).append((("old", d), u))
        cells, old = {}, {}
        for d, items in by_day.items():
            tot = sum(u for _, u in items)
            want = int(round(tot * self._share(self.late, d)))
            raw = [(k, u * want / tot) for k, u in items]
            got = {k: int(x) for k, x in raw}
            for k, x in sorted(raw, key=lambda kx: (int(kx[1]) - kx[1], str(kx[0])))[:want - sum(got.values())]:
                got[k] += 1
            for k, v in got.items():
                if k[0] == "old":
                    old[d] = v
                elif v:
                    cells[k] = v
        return cells, old

    def rows(self, dims, mets, start, end, events):
        """Every row GA4 would return (unsorted, unpaged) — zero rows are left out, as GA4 does."""
        days = [d for d in sorted(self.new) if start <= d <= end]
        cells, old = self.seen()
        un = self.un_by_day(cells, old)
        out = []
        if dims == ["date"] and not events:
            for d in days:
                vals = {"newUsers": int(round(self.new[d] * self._share(self.late_new, d))),
                        "activeUsers": self.a1[d], "active28DayUsers": self.a28[d]}
                if any(vals[m] for m in mets):
                    out.append(({"date": ymd(d)}, {m: vals[m] for m in mets}))
        elif dims == ["date", "eventName"]:
            evs = {d: ev(u) for d, u in old.items()}             # a day's events = its cells' events, added up
            for (c, d), u in cells.items():
                evs[d] = evs.get(d, 0) + ev(u)
            for d in days:
                if "app_remove" in events and un.get(d):
                    out.append(({"date": ymd(d), "eventName": "app_remove"},
                                {"totalUsers": un[d], "eventCount": evs.get(d, 0)}))
                if "app_update" in events and self.upd[d]:
                    out.append(({"date": ymd(d), "eventName": "app_update"},
                                {"totalUsers": self.upd[d], "eventCount": self.upd[d]}))
        elif dims == ["firstSessionDate", "date"]:
            assert events == ["app_remove"] and len(mets) == 1 and mets[0] in ("totalUsers", "eventCount")
            m = mets[0]
            k = self.short(start, end) if self.short else 1.0          # a long range's silent undercount
            fold, other = self.other(start, end) if self.other else 0.0, {}
            only = self.events_day if m == "eventCount" else self.users_day

            def share(d):
                return k * self.short_day.get(d, 1.0) * (only(d) if only else 1.0)

            def val(u):
                return ev(u) if m == "eventCount" else u
            for (c, d), u in cells.items():
                if start <= d <= end:
                    v = int(val(u) * share(d))
                    h = int(v * fold)
                    other[d] = other.get(d, 0) + h
                    if v - h:
                        out.append(({"firstSessionDate": ymd(c) if isinstance(c, date) else c, "date": ymd(d)},
                                    {m: v - h}))
            out += [({"firstSessionDate": "(other)", "date": ymd(d)}, {m: h}) for d, h in other.items() if h]
            for d in days:
                v = int(val(old.get(d, 0)) * share(d))
                if v:                         # old installs: a first-session day before the data starts
                    out.append(({"firstSessionDate": ymd(self.start - timedelta(days=400)), "date": ymd(d)},
                                {m: v}))
        elif dims == ["date", "appVersion"] and mets == ["activeUsers"]:
            for d in days:
                for v, u in sorted((self.vers.get(d) or {}).items()):
                    if u:
                        out.append(({"date": ymd(d), "appVersion": v}, {"activeUsers": u}))
        elif dims in (["date", "newVsReturning"], ["date", "appVersion", "newVsReturning"], ["date", "appVersion"]):
            assert mets == ["activeUsers", "sessions", "userEngagementDuration"], mets
            for d in days:
                acc = {}
                for v, nvr, a, sess, sec in self.use_split(d):
                    key = tuple({"date": ymd(d), "appVersion": v, "newVsReturning": nvr}[x] for x in dims)
                    m = acc.setdefault(key, [0, 0, 0])
                    m[0], m[1], m[2] = m[0] + a, m[1] + sess, m[2] + sec
                for key, (a, sess, sec) in sorted(acc.items()):
                    out.append((dict(zip(dims, key)), {"activeUsers": a, "sessions": sess, "userEngagementDuration": sec}))
        else:
            raise AssertionError("unexpected report %s" % dims)
        return out


def DEFAULT_RET(k):
    """Share of an install day's users active again on day k (k ≥ 1): 30% the next day, ~11% on day 7, ~5.5% on day 30."""
    return 0.30 * k ** -0.5 if k >= 1 else 1.0


def ev(u):
    """app_remove EVENTS of a cell of u uninstalling users: a few uninstall more than once (~5% on big cells)."""
    return u + u // 20


def _event_filter(body):
    ex = [e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]
          if e["filter"]["fieldName"] == "eventName"]
    if not ex:
        return None
    f = ex[0]
    return [f["stringFilter"]["value"]] if "stringFilter" in f else list(f["inListFilter"]["values"])


class UniStub(ga4.Ga4App):
    """Ga4App answering runReport from a Truth (per stream). `log` records every request body."""

    def __init__(self, truth, token, property_id, stream_id, log=None, quota=None, fail=None):
        super().__init__(token, property_id, stream_id)
        self.truth, self.log, self.quota_fn, self.fail = truth, log if log is not None else [], quota, fail

    def _post(self, method, body):
        self.calls += 1
        self.log.append((self.property_id, self.stream_id, body))
        assert method == "runReport"
        ex = [e["filter"] for e in body["dimensionFilter"]["andGroup"]["expressions"]]
        assert ex[0] == {"fieldName": "platform", "stringFilter": {"matchType": "EXACT", "value": "Android"}}
        assert ex[1] == {"fieldName": "streamId", "stringFilter": {"matchType": "EXACT", "value": self.stream_id}}
        assert body["returnPropertyQuota"] is True
        if self.fail:
            self.fail(body)                   # may raise, like _call does on an HTTP error
        dims = [d["name"] for d in body["dimensions"]]
        mets = [m["name"] for m in body["metrics"]]
        if "active28DayUsers" in mets and self.truth.reject_a28:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: Field active28DayUsers is not a valid metric")
        if self.truth.reject_nvr and "appVersion" in dims and "newVsReturning" in dims:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: Please remove newVsReturning to make the request compatible")
        if "cohortSpec" in body:                  # a cohort request: its dates live in each cohort, none on top
            assert "dateRanges" not in body and dims == ["cohort", "cohortNthDay"]
            assert mets == ["cohortActiveUsers", "cohortTotalUsers"]
            spec = body["cohortSpec"]
            assert spec["cohortsRange"] == {"granularity": "DAILY", "startOffset": 0, "endOffset": 30}
            cs = spec["cohorts"]
            assert 1 <= len(cs) <= 14 and len({c["name"] for c in cs}) == len(cs)
            assert all(c["dimension"] == "firstSessionDate" and c["dateRange"]["startDate"] == c["dateRange"]["endDate"]
                       and c["name"] == "c" + c["dateRange"]["startDate"].replace("-", "") for c in cs)
            rows = self.truth.cohort_rows([(c["name"], date.fromisoformat(c["dateRange"]["startDate"])) for c in cs])
        else:
            rng = body["dateRanges"][0]
            start, end = date.fromisoformat(rng["startDate"]), date.fromisoformat(rng["endDate"])
            rows = self.truth.rows(dims, mets, start, end, _event_filter(body))
            order = body.get("orderBys") or []
            assert {o["dimension"]["dimensionName"] for o in order} == set(dims), "every page needs a TOTAL order"
            for o in reversed(order):             # stable sorts, last key first
                k = o["dimension"]["dimensionName"]
                rows.sort(key=lambda r: r[0][k], reverse=bool(o.get("desc")))
        off, lim = int(body.get("offset") or 0), int(body.get("limit") or 10000)
        page = rows[off:off + lim]
        q = self.quota_fn(self) if self.quota_fn else {
            "tokensPerDay": {"consumed": 10, "remaining": 150000},
            "tokensPerHour": {"consumed": 10, "remaining": 35000},
            "tokensPerProjectPerHour": {"consumed": 10, "remaining": 13000}}
        return {"dimensionHeaders": [{"name": n} for n in dims], "metricHeaders": [{"name": n} for n in mets],
                "rows": [{"dimensionValues": [{"value": dv[n]} for n in dims],
                          "metricValues": [{"value": str(mv[n])} for n in mets]} for dv, mv in page],
                "rowCount": len(rows), "propertyQuota": q,
                "metadata": {"subjectToThresholding": True} if self.truth.thresholded else {}}


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body or {}
        self.text = ""

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._b


class AdminFake:
    """Admin API: `sees` = {access token: [property ids]}, `streams` = {property id: [(stream id, package)]}.
    `fail_streams` = {(token, property)} whose dataStreams call fails. Every call is logged."""

    def __init__(self, sees, streams, tz="Asia/Kolkata"):
        self.sees, self.streams, self.tz = sees, streams, tz
        self.fail_streams, self.calls = set(), []

    def get(self, url, headers=None, params=None, timeout=None):
        tok = headers["Authorization"].split(" ", 1)[1]
        self.calls.append(url)
        if url.endswith("/accountSummaries"):
            return Resp(body={"accountSummaries": [{"account": "accounts/1", "propertySummaries": [
                {"property": "properties/" + p, "displayName": "Prop " + p} for p in self.sees.get(tok, [])]}]})
        pid = url.split("/properties/")[1].split("/")[0]
        assert pid in self.sees.get(tok, [])
        if url.endswith("/dataStreams"):
            if (tok, pid) in self.fail_streams:
                return Resp(503, {"error": {"code": 503, "status": "UNAVAILABLE", "message": "down"}})
            return Resp(body={"dataStreams": [
                {"name": "properties/%s/dataStreams/%s" % (pid, s), "type": "ANDROID_APP_DATA_STREAM",
                 "androidAppStreamData": {"packageName": p}} for s, p in self.streams.get(pid, [])]})
        return Resp(body={"timeZone": self.tz, "currencyCode": "INR"})

    def post(self, url, headers=None, json=None, timeout=None):
        raise AssertionError("Data API calls go through UniStub")


def wave(d, amp=0.08, period=7):
    """A weekly swing (weekends differ), deterministic per date."""
    return 1 + amp * math.sin(2 * math.pi * (d.toordinal() % period) / period)


# ── the §5 data contract, checked field by field ─────────────────────────────────────────────────

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEX12 = re.compile(r"^[0-9a-f]{12}$")


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _iso(v):
    return isinstance(v, str) and bool(_ISO.match(v))


def _keys(obj, keys, where):
    assert isinstance(obj, dict), where
    assert set(obj) == set(keys), "%s: %s" % (where, sorted(set(obj) ^ set(keys)))


def _frac_or_none(v):
    return v is None or (_num(v) and v >= 0)


def check_head(h, where):
    if h is None:
        return
    _keys(h, ("p", "prev", "delta_pp", "dir", "alert", "low_sample", "from", "to", "prov", "est", "fb"), where)
    assert isinstance(h["est"], bool), where
    if h["fb"] is not None:                                            # older installs: compare's fall-back, as the row's
        _keys(h["fb"], ("recent", "prev", "n", "days", "kind"), where)
        assert h["fb"]["kind"] in ("inc", "brk", "both") and all(_iso(x) for x in h["fb"]["days"]), where
    assert _frac_or_none(h["p"]) and _frac_or_none(h["prev"]) and (h["delta_pp"] is None or _num(h["delta_pp"]))
    assert h["dir"] in ("up", "down", None) and isinstance(h["alert"], bool) and isinstance(h["low_sample"], bool)
    assert _iso(h["from"]) and _iso(h["to"]), where
    assert isinstance(h["prov"], bool) and not (h["dir"] == "down" and h["prov"]), where   # ▼ only from settled data


ALERT_KEYS = ("id", "source", "app_id", "app", "family", "dir", "severity", "unit", "checkpoint", "n", "also", "vs",
              "now", "before", "delta_pp", "rel", "z", "installs_from", "installs_to", "base_from", "base_to",
              "since", "day", "users", "opened", "last_seen", "fresh", "notify", "data_till", "message", "text",
              "provisional", "estimate")


IMPACT_ALERT_KEYS = ("release", "level", "rows")
IMPACT_TEXT = re.compile(r"^(v.+?|App update) \(\d{1,2} [A-Z][a-z]{2}( \d{4})?\) ke baad .+ · "
                         r"(HALT — staged rollout rok do, hotfix bhejo|HOLD — agla rollout roko, jaanch karo|"
                         r"WIN — isi disha me aage badho)( · shuruaati — D7 abhi baaki)?")


def check_alert(a, closed=False):
    imp = a.get("family") == "impact"
    _keys(a, ALERT_KEYS + (IMPACT_ALERT_KEYS if imp else ()) + (("closed",) if closed else ()), "alert")
    assert a["source"] == "uninstall" and a["family"] in ("cohort", "rate_spike", "rate_drift", "rate_zero", "impact")
    assert a["dir"] in ("up", "down") and a["severity"] in ("warning", "watch", "good")
    assert a["unit"] == {"cohort": "pct", "impact": "rel"}.get(a["family"], "per1k")
    assert a["id"].startswith(a["app_id"] + "|uninstall_" + a["family"] + "|ALL|" + a["dir"] + "|")
    if a["family"] == "cohort":
        assert a["checkpoint"] == "D%d" % a["n"] and isinstance(a["n"], int)
        assert all(x.startswith("D") for x in a["also"]) and set(a["vs"]) <= {"prev", "all"} and a["vs"]
        assert _num(a["delta_pp"]) and _num(a["z"]) and _iso(a["installs_from"]) and _iso(a["installs_to"])
    elif imp:                                                  # an update's HOLD / HALT (up = bad news) or WIN (down)
        assert a["checkpoint"] is None and a["n"] is None and a["also"] == [] and a["vs"] == []
        assert a["delta_pp"] is None or _num(a["delta_pp"])
        assert {"halt": "warning", "hold": "watch", "win": "good"}[a["level"]] == a["severity"]
        assert (a["dir"] == "down") == (a["level"] == "win")
        _keys(a["release"], ("key", "label", "date"), "impact release")
        assert _iso(a["release"]["date"]) and a["since"] == a["release"]["date"] and a["day"] is None
        rk = a["release"]["key"]                                  # the update: its first version (its date can move)
        assert re.search(r"\|%s\|(hold|halt|win)$" % re.escape(rk.split("@")[0] if rk.startswith("ver:") else rk),
                         a["id"])
        _keys(a["rows"], ("worse", "better"), "impact alert rows")
        assert set(a["rows"]["worse" if a["dir"] == "up" else "better"]) <= set(IMPACT_ROWS + IMPACT_VROWS)
        assert a["rows"]["worse" if a["dir"] == "up" else "better"]
        assert _iso(a["installs_from"]) and _iso(a["installs_to"]) and _iso(a["base_from"]) and _iso(a["base_to"])
        assert IMPACT_TEXT.match(a["text"]), a["text"]
    else:
        assert a["checkpoint"] is None and a["n"] is None and a["delta_pp"] is None and a["also"] == []
    if a["family"] == "rate_drift":
        assert _iso(a["since"]) and a["day"] is None
    if a["family"] in ("rate_spike", "rate_zero"):
        assert _iso(a["day"]) and a["since"] is None
    assert _num(a["now"]) and _num(a["before"]) and _num(a["rel"]) and isinstance(a["users"], int)
    for k in ("base_from", "base_to"):
        assert a[k] is None or _iso(a[k])
    assert _iso(a["opened"]) and _iso(a["last_seen"]) and _iso(a["data_till"])
    assert isinstance(a["fresh"], bool) and isinstance(a["notify"], bool)
    assert isinstance(a["provisional"], bool) and not (a["provisional"] and a["dir"] == "down")   # good news: settled
    assert a["text"].endswith(" · abhi ka data kaccha — number aur badh sakta hai") == a["provisional"]
    assert isinstance(a["estimate"], bool) and not (a["estimate"] and a["family"] not in ("cohort", "impact"))
    assert (" · kuch din ka GA4 data adhoora tha — total ke hisaab se poora kiya (andaza)" in a["text"]) == a["estimate"]
    assert a["message"] == a["app"] + ": " + a["text"]
    assert re.search("[%s-%s]" % (chr(0x900), chr(0x97F)), a["message"]) is None
    if closed:
        assert _iso(a["closed"])


def check_summary(s):
    _keys(s, ("v", "status", "asset", "asset_v", "data_till_min", "data_till_max", "counts", "apps", "alerts",
              "alert_counts", "impact_counts"), "summary")
    assert s["v"] == 1 and s["status"] in ("ok", "partial", "stale", "error") and s["asset"] == "uninstall.json.gz"
    assert _HEX12.match(s["asset_v"])
    for k in ("data_till_min", "data_till_max"):
        assert s[k] is None or _iso(s[k])
    _keys(s["counts"], ("selected", "with_ga4", "ready", "no_ga4", "failed", "deferred", "stale"), "counts")
    assert all(isinstance(v, int) for v in s["counts"].values())
    for r in s["apps"]:
        _keys(r, ("app_id", "app", "data_till", "stale", "ready", "stage", "rate7", "rate_med", "rate_dir", "head4",
                  "alerts", "updates"), "summary app")
        check_updates(r["updates"], r["data_till"])
        assert r["stage"] in ("naya", "badh_raha", "stable", None) and r["rate_dir"] in ("up", "down", "flat", None)
        assert (r["data_till"] is None or _iso(r["data_till"])) and isinstance(r["stale"], bool)
        assert r["rate7"] is None or _num(r["rate7"])
        _keys(r["head4"], ("D0", "D1", "D7", "D30"), "head4")
        for k, h in r["head4"].items():
            check_head(h, k)
        _keys(r["alerts"], ("warning", "watch", "good"), "row alerts")
    assert [r["app"].casefold() for r in s["apps"]] == sorted(r["app"].casefold() for r in s["apps"])
    for a in s["alerts"]:
        check_alert(a)
    _keys(s["alert_counts"], ("warning", "watch", "good"), "alert_counts")
    for sev in ("warning", "watch", "good"):
        assert s["alert_counts"][sev] == sum(1 for a in s["alerts"] if a["severity"] == sev)
    _keys(s["impact_counts"], ("halt", "hold", "continue", "win", "pending"), "impact_counts")
    for lvl in ("halt", "hold", "continue", "win"):
        assert s["impact_counts"][lvl] == sum(1 for r in s["apps"] for u in r["updates"] if u["level"] == lvl)
    assert s["impact_counts"]["pending"] == sum(1 for r in s["apps"] for u in r["updates"] if u["level"] is None)


def check_asset(asset, summary=None):
    _keys(asset, ("v", "consts", "apps", "no_ga4", "lateness"), "asset")
    _keys(asset["consts"], ("lag_days", "band_days", "band_k", "recent_k", "prev_k", "head_k", "z", "min_pp",
                            "min_rel", "min_recent_users", "big_recent_users", "zoom_days", "late_days", "thin_min_days",
                            "thin_min_users", "surv_recent_days", "verdict_k", "tri_avg_weeks", "alert_recent_days",
                            "year_clear_days", "impute_min_coverage", "est_mark_pp", "impact"), "consts")
    _keys(asset["consts"]["impact"], IMPACT_CONSTS, "consts.impact")
    check_lateness(asset["lateness"])
    for n in asset["no_ga4"]:
        _keys(n, ("app_id", "app", "package", "reason", "text"), "no_ga4")
        assert n["reason"] in ("no_package", "no_stream", "stream_list_failed", "not_fetched_yet", "fetch_failed",
                               "same_package")
    for a in asset["apps"]:
        _keys(a, ("app_id", "app", "package", "key", "tz", "den", "history_start", "data_till", "settled_till",
                  "late_days", "fetched_at", "stale", "history_capped", "flags", "daily", "rate_now", "stage", "stage_why",
                  "zoom", "checkpoints", "nmax", "curve", "table", "head4", "lifetime", "triangle", "survival",
                  "releases", "lateness", "alerts", "alerts_closed", "launch", "old_changes", "impact"), "detail")
        check_impact(a["impact"], a)
        assert _HEX12.match(a["key"]) and a["den"] in ("a28", "dau") and _iso(a["history_start"]) and _iso(a["data_till"])
        assert a["late_days"] == asset["consts"]["late_days"] and _iso(a["settled_till"])
        assert (date.fromisoformat(a["data_till"]) - date.fromisoformat(a["settled_till"])).days == a["late_days"]
        assert a["fetched_at"] is None or _TS.match(a["fetched_at"])
        _keys(a["flags"], ("truncated", "thresholded", "unplaced_users", "over_100", "kept_old_before",
                           "incomplete_days", "estimated_days", "outdated", "cell_days", "events_span"), "flags")
        assert isinstance(a["flags"]["outdated"], bool)
        for d, cov in a["flags"]["incomplete_days"].items():             # {day: coverage}, inside the history
            assert _iso(d) and a["history_start"] <= d <= a["data_till"] and _num(cov) and cov < 1
        for d, cov in a["flags"]["estimated_days"].items():              # {day: coverage}: filled, used (≈)
            assert _iso(d) and a["history_start"] <= d <= a["data_till"] and _num(cov)
            assert cov >= asset["consts"]["impute_min_coverage"] and d not in a["flags"]["incomplete_days"]
        check_lateness(a["lateness"])
        H = (date.fromisoformat(a["data_till"]) - date.fromisoformat(a["history_start"])).days + 1
        L = a["launch"]                                                    # test installs before it: hidden, kept
        _keys(L, ("day", "hidden", "pre_installs", "pre_uninstalls", "installs", "sure"), "launch")
        assert isinstance(L["sure"], bool) and (L["sure"] or L["hidden"])     # "shayad test": only about hidden ones
        assert _iso(L["day"]) and a["history_start"] <= L["day"] <= a["data_till"] and isinstance(L["hidden"], bool)
        assert all(isinstance(L[k], int) and L[k] >= 0 for k in ("pre_installs", "pre_uninstalls", "installs"))
        assert L["hidden"] == (L["pre_installs"] > 0)
        assert L["pre_installs"] <= 0.10 * (L["pre_installs"] + L["installs"])        # tests: a sliver, never history
        start = L["day"] if L["hidden"] else a["history_start"]            # where every install-day number starts
        Hp = (date.fromisoformat(a["data_till"]) - date.fromisoformat(start)).days + 1
        cdays, span = a["flags"]["cell_days"], a["flags"]["events_span"]   # every day: users | events | incomplete
        _keys(cdays, ("users", "events", "estimated", "incomplete"), "cell_days")
        assert all(isinstance(v, int) and v >= 0 for v in cdays.values()) and sum(cdays.values()) == H
        assert cdays["incomplete"] == len(a["flags"]["incomplete_days"])
        assert cdays["estimated"] == len(a["flags"]["estimated_days"])
        assert (span is None) == (cdays["events"] == 0)
        assert span is None or (a["history_start"] <= span[0] <= span[1] <= a["data_till"])
        _keys(a["daily"], ("start", "new", "un", "a28", "upd", "rate", "med", "lo", "hi", "breaks"), "daily")
        assert a["daily"]["start"] == a["history_start"]
        assert all(_iso(b) and a["history_start"] <= b <= a["data_till"] for b in a["daily"]["breaks"])
        for k in ("new", "un", "a28", "upd", "rate", "med", "lo", "hi"):
            assert len(a["daily"][k]) == H, k                              # every day, through data_till
        _keys(a["rate_now"], ("last7", "med", "lo", "hi", "dir", "out_of_band", "drift", "from", "to", "prov"), "rate_now")
        rn = a["rate_now"]
        assert _iso(rn["from"]) and _iso(rn["to"]) and rn["from"] <= rn["to"] <= a["data_till"]
        assert rn["prov"] == (rn["to"] > a["settled_till"]) and not (rn["dir"] == "down" and rn["prov"])
        if rn["drift"]:
            _keys(rn["drift"], ("since", "before", "now", "rel", "z", "prov"), "drift")
            assert not (rn["drift"]["prov"] and rn["drift"]["now"] < rn["drift"]["before"])
        assert a["stage"] in ("naya", "badh_raha", "stable") and isinstance(a["stage_why"], str)
        if a["zoom"]:
            _keys(a["zoom"], ("until", "reason", "label"), "zoom")
            assert a["zoom"]["reason"] in ("release", "alert")
        assert a["checkpoints"] == sorted(set(a["checkpoints"])) and all(0 <= n <= a["nmax"] for n in a["checkpoints"])
        assert a["nmax"] == Hp - 7
        _keys(a["curve"], ("p", "lo", "hi", "users", "k", "inc"), "curve")
        assert all(len(v) == Hp for v in a["curve"].values())            # index = N, 0..Hp-1 (from the launch)
        assert [t["n"] for t in a["table"]] == a["checkpoints"]
        for t in a["table"]:
            _keys(t, ("n", "key", "head", "recent", "prev", "all", "dir", "alert", "low_sample", "break_day", "prov",
                      "inc_day", "fallback"), "table row")
            fb = t["fallback"]                                             # older installs: what it passed, said
            if fb is not None:
                _keys(fb, ("recent", "prev", "n", "days", "kind"), "table fallback")
                assert (fb["recent"] or fb["prev"]) and fb["kind"] in ("inc", "brk", "both") and fb["n"] >= len(fb["days"]) >= 1
                assert all(_iso(x) for x in fb["days"]) and fb["days"] == sorted(fb["days"])
                assert fb["kind"] == "brk" or set(fb["days"]) & set(a["flags"]["incomplete_days"])
            assert t["key"] == "D%d" % t["n"] and (t["break_day"] is None or t["break_day"] in a["daily"]["breaks"])
            assert t["inc_day"] is None or t["inc_day"] in a["flags"]["incomplete_days"]
            assert isinstance(t["prov"], bool) and not (t["dir"] == "down" and t["prov"])
            if t["recent"]["to"]:                                          # prov = its day N is not settled yet
                assert t["prov"] == ((date.fromisoformat(t["recent"]["to"]) + timedelta(days=t["n"])).isoformat()
                                     > a["settled_till"]), t
            _keys(t["head"], ("p", "lo", "hi", "users"), "table head")
            _keys(t["recent"], ("p", "users", "from", "to", "k", "est"), "table recent")
            assert isinstance(t["recent"]["k"], int) and 0 <= t["recent"]["k"] <= 7
            for b in ("prev", "all"):
                if t[b] is not None:
                    _keys(t[b], ("p", "users", "from", "to", "delta_pp", "z", "fires", "est"), "table " + b)
            for o in (t["recent"], t["prev"], t["all"]):                  # ≈: how much rests on filled days
                if o is not None and o["est"] is not None:
                    _keys(o["est"], ("days", "first", "last", "lo", "hi", "share", "pp"), "table est")
                    assert o["est"]["pp"] >= 0.1
                    assert o["est"]["days"] >= 1 and o["est"]["first"] in a["flags"]["estimated_days"]
                    assert o["est"]["last"] in a["flags"]["estimated_days"] and 0 < o["est"]["share"] < 1
        _keys(a["head4"], ("D0", "D1", "D7", "D30"), "detail head4")
        _keys(a["lifetime"], ("p", "users", "un", "rate_all_med"), "lifetime")
        tri = a["triangle"]
        _keys(tri, ("cols", "ref", "ref_users", "avg4", "avg4_set", "rows"), "triangle")
        assert tri["cols"] == a["checkpoints"] and len(tri["ref"]) == len(tri["ref_users"]) == len(tri["avg4"]) == len(tri["cols"])
        got = [(N, av) for N, av in zip(tri["cols"], tri["avg4"]) if av is not None]
        for N, av in got:                                                 # ONE set: the 4 newest settled full weeks
            _keys(av, ("p", "users", "from", "to", "prov", "est"), "triangle avg4")
            assert isinstance(av["est"], bool)
            f, t = date.fromisoformat(av["from"]), date.fromisoformat(av["to"])
            assert f.weekday() == 0 and (t - f).days == 27 and av["to"] <= a["settled_till"] and av["from"] >= start
            assert (t + timedelta(days=N)).isoformat() <= a["data_till"]   # every one of them reached day N
            assert av["prov"] == ((t + timedelta(days=N)).isoformat() > a["settled_till"])
            assert (av["from"], av["to"], av["users"]) == (got[0][1]["from"], got[0][1]["to"], got[0][1]["users"])
        assert all(x[1]["p"] <= y[1]["p"] for x, y in zip(got, got[1:]))   # never down, left to right
        aset = tri["avg4_set"]                                           # the set on its own (named on every page)
        if aset is not None:
            _keys(aset, ("from", "to", "users"), "triangle avg4_set")
            assert aset["from"] >= start and aset["to"] <= a["settled_till"]
        assert all((av["from"], av["to"], av["users"]) == (aset["from"], aset["to"], aset["users"]) for _, av in got)
        check_survival(a["survival"], a, asset["consts"])
        assert sum(r["days"] for r in tri["rows"]) == H                   # ALL rows, newest first (test weeks last)
        assert sum(r["days"] for r in tri["rows"] if r["pre"]) == H - Hp
        assert [r["pre"] for r in tri["rows"]] == sorted((r["pre"] for r in tri["rows"]))
        for r in tri["rows"]:
            _keys(r, ("week", "from", "to", "days", "users", "partial", "p", "pre", "est"), "triangle row")
            assert len(r["p"]) == len(tri["cols"]) and (r["to"] < start) == r["pre"]
            assert r["est"] == sorted(set(r["est"])) and all(r["p"][j] is not None for j in r["est"])   # ≈ cells
            assert not r["est"] or a["flags"]["estimated_days"]
        for r in a["releases"]:
            _keys(r, ("date", "version", "kind"), "release")
        old = (date.fromisoformat(a["data_till"]) - timedelta(days=asset["consts"]["alert_recent_days"])).isoformat()
        for al in a["alerts"]:
            check_alert(al)
            assert al["family"] != "cohort" or al["installs_to"] >= old      # alerts: recent installs only
        for al in a["alerts_closed"]:
            check_alert(al, closed=True)
        for o in a["old_changes"]:                                         # older ones: info only
            _keys(o, ("n", "checkpoint", "dir", "vs", "now", "before", "delta_pp", "z", "users", "installs_from",
                      "installs_to", "base_from", "base_to", "text"), "old change")
            assert o["installs_to"] < old and o["dir"] in ("up", "down") and o["checkpoint"] == "D%d" % o["n"]
    if summary is not None:
        assert [a["app_id"] for a in asset["apps"]] == [r["app_id"] for r in summary["apps"]]
        for a, r in zip(asset["apps"], summary["apps"]):                  # the All-apps list: the detail's newest blocks
            assert [(u["key"], u["level"]) for u in r["updates"]] == [
                (b["key"], b["verdict"]["level"]) for b in a["impact"]["updates"] if b["key"] in {x["key"] for x in r["updates"]}]
        assert sorted(al["id"] for a in asset["apps"] for al in a["alerts"]) == sorted(al["id"] for al in summary["alerts"])
        for a, r in zip(asset["apps"], summary["apps"]):
            assert a["head4"] == r["head4"] and a["app"] == r["app"]


SURV_KEYS = ("from", "to", "installs", "gap_days", "gap_inc", "gap_brk", "x", "r", "n", "k", "left", "lo", "hi", "gone",
             "thin_from", "clipped")


def check_curve(c, consts):
    """One survival curve: never rises, stays in 0..1, the bars (gone) add up to the line, the installs behind
    a day only shrink, and "kam data" (thin_from) is a tail."""
    _keys(c, SURV_KEYS, "survival curve")
    L = len(c["left"])
    assert all(len(c[k]) == L for k in ("x", "r", "n", "k", "left", "lo", "hi", "gone"))
    assert all(0 <= v <= 1 for v in c["left"]) and all(a >= b for a, b in zip(c["left"], c["left"][1:]))
    assert all(lo <= v <= hi for lo, v, hi in zip(c["lo"], c["left"], c["hi"]))
    assert all(g >= 0 for g in c["gone"])
    run = 0.0
    for g, v in zip(c["gone"], c["left"]):
        run += g
        assert abs(run - (1 - v)) < 1e-6 * (L + 1)
    assert all(a >= b for a, b in zip(c["n"], c["n"][1:])) and all(a >= b for a, b in zip(c["k"], c["k"][1:]))
    assert all(k > 0 for k in c["k"]) and c["installs"] >= (c["n"][0] if L else 0)
    assert isinstance(c["gap_days"], int) and c["gap_days"] == len(c["gap_inc"]) + len(c["gap_brk"])   # named by kind
    assert all(_iso(d) and c["from"] <= d <= c["to"] for d in c["gap_inc"] + c["gap_brk"])
    assert c["gap_inc"] == sorted(c["gap_inc"]) and c["gap_brk"] == sorted(c["gap_brk"])
    assert not set(c["gap_inc"]) & set(c["gap_brk"])
    thin = [k < consts["thin_min_days"] or n < consts["thin_min_users"] for k, n in zip(c["k"], c["n"])]
    assert c["thin_from"] == (thin.index(True) if True in thin else None)
    assert all(thin[c["thin_from"]:]) if c["thin_from"] is not None else True
    assert _iso(c["from"]) and _iso(c["to"]) and c["from"] <= c["to"]


def check_survival(sv, a, consts):
    _keys(sv, ("all", "recent", "verdict", "key_days", "with_test"), "survival")
    check_curve(sv["all"], consts)
    start = a["launch"]["day"] if a["launch"]["hidden"] else a["history_start"]    # test installs: not in "all"
    assert sv["all"]["from"] == start and sv["all"]["to"] == a["data_till"]
    assert sv["all"]["installs"] == a["launch"]["installs"]
    if a["launch"]["hidden"]:                                             # … kept in "with_test"
        check_curve(sv["with_test"], consts)
        assert sv["with_test"]["from"] == a["history_start"] and sv["with_test"]["to"] == a["data_till"]
        assert sv["with_test"]["installs"] == sv["all"]["installs"] + a["launch"]["pre_installs"]
    else:
        assert sv["with_test"] is None
    # every day N counted only settled data: N ≤ settled_till − the first install day counted
    assert len(sv["all"]["left"]) <= (date.fromisoformat(a["settled_till"]) - date.fromisoformat(start)).days + 1
    H = (date.fromisoformat(a["data_till"]) - date.fromisoformat(start)).days + 1
    if sv["recent"] is None:
        assert H <= consts["surv_recent_days"]
    else:
        check_curve(sv["recent"], consts)
        assert sv["recent"]["to"] == a["data_till"]
        assert (date.fromisoformat(a["data_till"]) - date.fromisoformat(sv["recent"]["from"])).days + 1 == consts["surv_recent_days"]
    assert sv["key_days"] == sorted(sv["key_days"]) and len(sv["key_days"]) <= 4
    assert set(sv["key_days"]) <= set(a["checkpoints"])
    solid = sv["all"]["thin_from"] if sv["all"]["thin_from"] is not None else len(sv["all"]["left"])
    # days with enough installs — or, for a tiny app with none, the days its curve reached (marked "kam data")
    assert all(N < solid for N in sv["key_days"]) or (
        all(N < len(sv["all"]["left"]) for N in sv["key_days"]) and not any(N < solid for N in a["checkpoints"]))
    v = sv["verdict"]
    if v is not None:
        _keys(v, ("n", "recent", "prev", "delta_pp", "z", "fires", "dir", "low_sample", "fallback", "est"), "verdict")
        for w in ("recent", "prev"):
            _keys(v[w], ("from", "to", "users", "k", "left"), "verdict " + w)
        assert v["n"] in (7, 3, 1, 0) and isinstance(v["fires"], bool) and isinstance(v["low_sample"], bool)
        assert (date.fromisoformat(v["recent"]["to"]) + timedelta(days=v["n"])).isoformat() <= a["settled_till"]
        assert v["prev"]["to"] < v["recent"]["from"]
        assert v["dir"] == (("worse" if v["delta_pp"] < 0 else "better") if v["fires"] else None)
        assert not (v["fires"] and v["low_sample"])


def check_lateness(L):
    """None (nothing re-read yet) or {"ages", "un", "new", "final_age", "fetches"}: per age the share of the
    final count already there — rising to 1.0 at final_age, None where too few re-reads to say."""
    if L is None:
        return
    _keys(L, ("ages", "un", "new", "a1", "final_age", "fetches"), "lateness")
    assert L["ages"] == list(range(L["ages"][0], L["final_age"] + 1)) and isinstance(L["fetches"], int)
    for m in ("un", "new", "a1"):
        v = L[m]
        assert len(v) == len(L["ages"]) and v[-1] == 1.0
        known = [x for x in v if x is not None]
        assert all(_num(x) and x > 0 for x in known)
        assert all(x is not None for x in v[v.index(known[0]):])        # the chain only ever stops at the young end


# ── the update-impact card (engine.impact, spec §4) ─────────────────────────────────────────────────

IMPACT_ROWS = ("returning_dau", "new_d1", "new_d7", "sessions", "time", "arpdau", "uninstall_d0")
IMPACT_VROWS = ("ver_sessions", "ver_time")
IMPACT_ROW_KEYS = ("before", "after", "expected", "after_prov", "change", "change_unit", "unit", "z", "status",
                   "raw_status", "streak", "prov", "est", "n_before", "n_after", "from_b", "to_b", "from_a", "to_a",
                   "reason", "ready_on", "extra")
IMPACT_VROW_KEYS = ("old", "new", "diff", "adj", "bias", "z", "status", "raw_status", "streak", "n_days", "reason", "prov")
IMPACT_EXTRA = {"returning_dau": ("raw_change", "mode", "k_days", "imputed_share", "mu_week"),
                "new_d1": ("installs_before", "installs_after", "swing", "cohorts_before", "cohorts_after", "phi"),
                "new_d7": ("installs_before", "installs_after", "swing", "cohorts_before", "cohorts_after", "phi"),
                "sessions": ("all_before", "all_after", "adj_change"), "time": ("all_before", "all_after", "adj_change"),
                "arpdau": ("imp_change", "imp_adj", "ecpm_change", "newshare_before", "newshare_after", "tz_blend",
                           "currency"),
                "uninstall_d0": ("read", "phi", "est")}
IMPACT_UNITS = {"returning_dau": "users", "new_d1": "pct", "new_d7": "pct", "sessions": "num", "time": "sec",
                "arpdau": "usd1k", "uninstall_d0": "pct"}
IMPACT_STATUS = ("worse", "better", "same", "unsure", "low", "pending", "na", "market")
IMPACT_NOTES = ("installs_swing", "newshare_swing", "diluted", "slow_rollout", "no_cohorts", "no_revenue", "tz_blend",
                "before_overlap", "cut_by_next", "prov", "est", "thresholded")
IMPACT_CONSTS = ("impact_v", "act_late_days", "cohort_days", "win_days", "pre_days", "adopt_after", "rollout_wait",
                 "adopt_low", "chain_days", "impact_min_days", "z_final", "z_early", "dau_min_rel", "ret_min_pp",
                 "ret_min_rel", "use_min_rel", "arpdau_min_rel", "imp_min_rel", "ver_min_rel", "big_x", "persist",
                 "min_dau", "min_installs", "min_events", "ver_min_users", "install_swing", "newshare_swing",
                 "sigma_floor", "noise_lag", "null_weeks", "null_min", "recent_swing", "bias_min", "bias_max", "vuse_min_share", "coh_batch", "coh_min_users", "coh_min_coverage",
                 "coh_edge_run", "coh_max_calls", "impact_alert_days", "impact_list_days", "impact_show")
IMPACT_LABEL = re.compile(r"^(v.+|App update)$")               # (a version name may hold a space: "v2.1 (45)")
_DPS = {"users": 0, "pct": 5, "num": 3, "sec": 1, "usd1k": 4}


def _dp_ok(v, dp):
    return v is None or (isinstance(v, int) if dp == 0 else _num(v) and abs(round(v, dp) - v) < 1e-9)


def check_updates(ups, data_till):
    """A summary row's "updates" (the All apps "Recent updates" list)."""
    for u in ups:
        _keys(u, ("key", "label", "date", "level", "early", "final", "adoption", "head"), "summary update")
        assert IMPACT_LABEL.match(u["label"]) and _iso(u["date"]) and u["level"] in ("halt", "hold", "continue", "win", None)
        assert isinstance(u["early"], bool) and u["early"] == (not u["final"])
        assert u["adoption"] is None or 0 <= u["adoption"] <= 1.0001
        assert (date.fromisoformat(data_till) - date.fromisoformat(u["date"])).days <= 60
        if u["head"] is not None:
            _keys(u["head"], ("row", "change", "unit"), "update head")
            assert u["head"]["row"] in IMPACT_ROWS + IMPACT_VROWS and u["head"]["unit"] in ("rel", "pp")
    assert [u["date"] for u in ups] == sorted((u["date"] for u in ups), reverse=True)


def check_impact(imp, detail=None):
    """One app's detail["impact"]: every update block with EXACTLY the owner's 7 rows + the 2 version rows + the verdict
    (the verify gate: a missing row fails here), every key of the contract, statuses / notes / levels from their lists,
    the rounding, the windows, and "na" / "pending" / "low" rows always saying why."""
    _keys(imp, ("v", "updates", "flags"), "impact")
    assert imp["v"] == 1
    fl = imp["flags"]
    _keys(fl, ("ret_from", "vuse_split", "revenue", "tz_blend", "usage_from"), "impact flags")
    assert fl["revenue"] in ("ok", "none", "partial") and isinstance(fl["vuse_split"], bool)
    assert isinstance(fl["tz_blend"], bool) and all(fl[k] is None or _iso(fl[k]) for k in ("ret_from", "usage_from"))
    assert [b["date"] for b in imp["updates"]] == sorted((b["date"] for b in imp["updates"]), reverse=True)
    assert len({b["key"] for b in imp["updates"]}) == len(imp["updates"])
    for b in imp["updates"]:
        _keys(b, ("key", "rel_keys", "kind", "versions", "label", "date", "adoption", "windows", "rows", "versions_cmp",
                  "verdict", "notes", "alert_id"), "impact block")
        assert b["kind"] in ("version", "update") and b["key"] == b["rel_keys"][0] and IMPACT_LABEL.match(b["label"])
        assert (b["kind"] == "version") == bool(b["versions"]) and (b["label"] == "App update") == (b["kind"] == "update")
        for k in b["rel_keys"]:
            assert re.match(r"^(ver:.+|upd)@\d{4}-\d{2}-\d{2}$", k), k
        assert b["key"].endswith("@" + b["date"])
        ad = b["adoption"]
        _keys(ad, ("days", "share", "at_start", "mean", "last", "slow"), "adoption")
        assert len(ad["days"]) == len(ad["share"]) and all(0 <= x <= 1.0001 for x in ad["share"])
        assert isinstance(ad["slow"], bool) and (b["kind"] == "version" or (ad["days"] == [] and ad["mean"] is None))
        w = b["windows"]
        _keys(w, ("before", "after", "pre_from", "overlap_before"), "windows")
        _keys(w["before"], ("from", "to"), "before")
        _keys(w["after"], ("from", "to", "days", "settled", "settled_till", "cut_by"), "after")
        R = date.fromisoformat(b["date"])
        assert w["before"] == {"from": (R - timedelta(days=7)).isoformat(), "to": (R - timedelta(days=1)).isoformat()}
        a0 = date.fromisoformat(w["after"]["from"])
        assert R + timedelta(days=1) <= a0 <= R + timedelta(days=3) and 0 <= w["after"]["settled"] <= w["after"]["days"] <= 7
        assert w["after"]["days"] == max(0, (date.fromisoformat(w["after"]["to"]) - a0).days + 1)
        assert (w["after"]["cut_by"] is None) == (w["after"]["days"] == 7 or w["after"]["cut_by"] is None)
        assert w["pre_from"] == (R - timedelta(days=35)).isoformat()
        if detail is not None and w["after"]["settled_till"]:
            assert w["after"]["settled_till"] <= (date.fromisoformat(detail["data_till"]) - timedelta(days=3)).isoformat()
        _keys(b["rows"], IMPACT_ROWS, "impact rows")                    # exactly the 7: none ever dropped
        for k, r in b["rows"].items():
            _keys(r, IMPACT_ROW_KEYS, "impact row " + k)
            _keys(r["extra"], IMPACT_EXTRA[k], "impact row extra " + k)
            assert r["unit"] == IMPACT_UNITS[k] and r["change_unit"] == ("pp" if r["unit"] == "pct" else "rel")
            assert r["status"] in IMPACT_STATUS and r["raw_status"] in IMPACT_STATUS
            assert isinstance(r["streak"], int) and isinstance(r["prov"], bool) and isinstance(r["est"], bool)
            assert (r["expected"] is None) or k == "returning_dau"
            for x in ("before", "after", "expected", "after_prov"):
                assert _dp_ok(r[x], _DPS[r["unit"]]), (k, x, r[x])
            assert _dp_ok(r["change"], 2 if r["change_unit"] == "pp" else 4) and _dp_ok(r["z"], 2)
            if r["status"] in ("na", "low", "market"):                  # never a bare "—": it says why
                assert isinstance(r["reason"], str) and r["reason"], (k, r)
            if r["status"] == "pending":
                assert r["ready_on"] is None or _iso(r["ready_on"])
            if r["status"] in ("worse", "better"):
                assert r["raw_status"] == r["status"] and r["change"] is not None and r["z"] is not None
            if r["status"] == "unsure" and r["raw_status"] in ("worse", "better"):
                assert r["reason"] == "pakka hone ke liye kal ka data bhi"
            for x in ("from_a", "to_a", "from_b", "to_b"):
                assert r[x] is None or _iso(r[x])
            if r["from_a"]:
                assert r["from_a"] >= w["after"]["from"] and r["to_b"] < b["date"]
        vc = b["versions_cmp"]
        _keys(vc, ("new_label", "days", "adoption_mean", "split", "bias", "rows"), "versions_cmp")
        _keys(vc["days"], ("from", "to", "n"), "versions_cmp days")
        _keys(vc["bias"], ("releases", "sessions", "time"), "versions_cmp bias")
        _keys(vc["rows"], IMPACT_VROWS, "version rows")                 # the 2 version rows: never dropped
        for k, r in vc["rows"].items():
            _keys(r, IMPACT_VROW_KEYS, "version row " + k)
            assert r["status"] in IMPACT_STATUS and r["raw_status"] in IMPACT_STATUS
            if r["status"] in ("na", "low"):
                assert r["reason"]
            if b["kind"] == "update":
                assert r["status"] == "na" and r["reason"] == "Is update ka version number nahi"
            if not vc["split"] or vc["bias"]["releases"] < 3:          # never worse / better without its gap
                assert r["status"] not in ("worse", "better")
        v = b["verdict"]
        _keys(v, ("level", "early", "final", "why", "worse", "better", "pending", "ready_on", "settled_days", "min_days"),
              "verdict")
        assert v["level"] in ("halt", "hold", "continue", "win", None) and v["early"] == (not v["final"])
        assert isinstance(v["why"], str) and v["why"] and v["min_days"] == 3 and v["settled_days"] == w["after"]["settled"]
        allr = dict(b["rows"], **vc["rows"])
        for lst, st in (("worse", "worse"), ("better", "better"), ("pending", "pending")):
            assert v[lst] == [k for k in IMPACT_ROWS + IMPACT_VROWS if allr[k]["status"] == st], (lst, v)
        if v["settled_days"] < 3:
            assert v["level"] is None
        if v["level"] == "win":
            assert v["final"] and not v["worse"] and v["better"]
        if v["level"] in ("hold", "halt"):
            assert v["worse"]
        assert v["ready_on"] is None or _iso(v["ready_on"])
        assert b["notes"] == [n for n in IMPACT_NOTES if n in b["notes"]]
        assert b["alert_id"] is None or isinstance(b["alert_id"], str)
        if detail is not None and b["alert_id"]:
            assert b["alert_id"] in {a["id"] for a in detail["alerts"]}


def check_cohort_file(c, detail):
    _keys(c, ("v", "app_id", "start", "end", "new", "lags", "unplaced"), "cohort file")
    assert c["app_id"] == detail["app_id"] and c["start"] == detail["history_start"] and c["end"] == detail["data_till"]
    H = len(c["new"])
    assert len(c["lags"]) == H
    for i, lags in enumerate(c["lags"]):
        assert [l for l, _ in lags] == sorted(l for l, _ in lags) and all(0 <= l <= H - 1 - i for l, _ in lags)
