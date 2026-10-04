"""Synthetic users who COME BACK, for the history / comeback tests (engine.audience.comeback, fetch.ga4_audience's
history) — no real data anywhere.

Returners is a Population (tests.audience_synth) whose users have EXPLICIT open days, so the same people can be looked
at on any final day E (`at(E)`): the Uninstall store and the Audience store GA4 would have given on E, and — because
the generator knows its own rules — both the TRUE comeback counts (brute force over the open days) and the TRUE
comeback chances it was built with (RATES).

The generator, per user: opens on its install day and for a short spell after it (each day with chance SPELL_OPEN);
at the end of a spell it either UNINSTALLS right after its last open (UN_ACTIVE: "opened, then uninstalled") or goes
quiet. A quiet user comes back on a day with a daily chance that depends only on how long it has been quiet — the age
bands of RATES, written as the chance to come back within the next 30 days (hazard = 1 − (1 − p)^(1/30)) — and each
return starts a new spell. With dormant_un > 0 a quiet user may also uninstall while asleep without ever opening again
(a clean-up uninstall: the Audience approximation's blind spot, so the sleepers' range [dead_lo, dead] widens)."""

import bisect
import calendar
import math
import random
from datetime import date, timedelta

from admob_iq.engine import audience as eng
from tests.audience_synth import Population

# (sleeping for at least N months, the chance of coming back within the next 30 days) — the generator's own truth
RATES = ((1, 0.12), (2, 0.07), (4, 0.035), (7, 0.015))
ALIVE_DAILY = 0.01              # a user quiet for under a month re-opens on a day with this chance (still "alive")
SPELL_OPEN = 0.6                # inside a spell a day is an open day with this chance
SPELL_MEAN = 5                  # a spell lasts a geometric number of days with this mean
UN_ACTIVE = 0.25                # share of spells that end with an uninstall right after the last open
CLEAN_DAILY = 0.004             # (dormant_un only) daily chance a quiet user (31+ days) uninstalls without opening


def month_end(x):
    return date(x.year, x.month, calendar.monthrange(x.year, x.month)[1])


def hazard(p, days=30):
    return 1 - (1 - p) ** (1.0 / days)


def _first_success(rnd, hz):
    """Failures before the first success of a daily chance hz (0-based): inverse transform."""
    return int(math.log(1 - rnd.random()) / math.log(1 - hz))


class Returners(Population):
    """`days` install days ending on `horizon`, `per_day` users each (seeded). users = [(install day, open days
    (sorted tuple), uninstall day or None)]; `end` = the final day the stores / truths are for (at(E) moves it)."""

    def __init__(self, days=420, per_day=40, seed=3, horizon=None, dormant_un=0.0, rates=RATES):
        from tests.audience_synth import E
        self.horizon = horizon or E
        self.end = self.horizon
        self.start = self.horizon - timedelta(days=days - 1)
        self.rates = rates
        self._last = {}
        rnd = random.Random(seed)
        w = eng.window_days
        h = [hazard(p) for _, p in rates]
        # (first age in days, last age in days, daily chance) of a quiet user — the age is days since its last open
        self.segs = [(1, w(1) - 1, ALIVE_DAILY), (w(1), w(2) - 1, h[0]), (w(2), w(4) - 1, h[1]),
                     (w(4), w(7) - 1, h[2]), (w(7), 10 ** 6, h[3])]
        self.dormant_un = dormant_un
        self.users = []
        for i in range(days):
            x = self.start + timedelta(days=i)
            for _ in range(per_day):
                self.users.append(self._life(rnd, x))

    def _spell(self, rnd, t):
        """The open days of a spell starting on t (t itself is one)."""
        out = [t]
        n = 1 + _first_success(rnd, 1.0 / SPELL_MEAN)
        for d in range(1, n + 1):
            if t + timedelta(days=d) <= self.horizon and rnd.random() < SPELL_OPEN:
                out.append(t + timedelta(days=d))
        return out

    def _return_after(self, rnd, last):
        """The day a user quiet since `last` comes back (None: not before the horizon)."""
        for lo, hi, hz in self.segs:
            start = last + timedelta(days=lo)
            if start > self.horizon:
                return None
            d = start + timedelta(days=_first_success(rnd, hz))
            if d <= last + timedelta(days=hi):
                return d if d <= self.horizon else None
        return None

    def _life(self, rnd, x):
        opens, t, r = [], x, None
        while True:
            opens += self._spell(rnd, t)
            last = opens[-1]
            if rnd.random() < UN_ACTIVE:
                r = last                                        # opened, then uninstalled
                break
            back = self._return_after(rnd, last)
            if self.dormant_un:
                un = last + timedelta(days=31 + _first_success(rnd, CLEAN_DAILY))
                if un <= self.horizon and (back is None or un < back):
                    r = un                                      # a clean-up uninstall: never opened again
                    break
            if back is None:
                break
            t = back
        return (x, tuple(opens), r)

    # ── the one Population hook that changes: activity = any open day in the window ──
    def active(self, u, a, b):
        opens = u[1]
        i = bisect.bisect_left(opens, a)
        return i < len(opens) and opens[i] <= b

    def at(self, end):
        """The same people looked at on final day `end` (a shallow copy: users are shared)."""
        c = object.__new__(Returners)
        c.__dict__.update(self.__dict__)
        c.end, c._last = end, {}
        return c

    def _last_le(self):
        """Every user's last open on or before self.end (None before the first), cached per end."""
        got = self._last.get(self.end)
        if got is None:
            got = []
            for u in self.users:
                i = bisect.bisect_right(u[1], self.end)
                got.append(u[1][i - 1] if i else None)
            self._last[self.end] = got
        return got

    def actives(self, a, b):
        if b != self.end:
            return super().actives(a, b)
        out = {}
        for u, last in zip(self.users, self._last_le()):
            if last is not None and last >= a:
                k = u[0].isoformat()
                out[k] = out.get(k, 0) + 1
        return out

    # ── truth ──
    def truth(self, e1, e2, k, mature=True):
        """(came back, sleepers) for k months at e1 and the next g days: users installed on e1 (not uninstalled by e1)
        with no open in the last w_k days up to e1 — the sleepers — and, of them, those with an open in (e1, e2].
        mature=True: only install months that ended on or before e1 (the comeback table's cells)."""
        s = e1 - timedelta(days=eng.window_days(k) - 1)
        back = sleepers = 0
        for x, opens, r in self.users:
            if x > e1 or (r is not None and r <= e1) or (mature and month_end(x) > e1):
                continue
            i = bisect.bisect_left(opens, s)
            if i < len(opens) and opens[i] <= e1:
                continue
            sleepers += 1
            j = bisect.bisect_right(opens, e1)
            if j < len(opens) and opens[j] <= e2:
                back += 1
        return back, sleepers

    def true_rate(self, e1, e2, lo_k, hi_k=None, mature=True):
        """The chance of coming back within e1 → e2 of users quiet from lo_k up to hi_k months (None: for ever)."""
        b1, s1 = self.truth(e1, e2, lo_k, mature)
        b2, s2 = self.truth(e1, e2, hi_k, mature) if hi_k else (0, 0)
        return (b1 - b2) / (s1 - s2) if s1 - s2 else None

    def expected_back(self, e1, e2, k, mature=True):
        """(mean, variance) of the number of comebacks in (e1, e2] the generator's own rules give THIS set of sleepers
        (the same users truth() counts): per sleeper, 1 − Π over the days of (1 − the day's chance at the age it will
        have that day) — dormant_un = 0 only (a clean-up uninstall would compete with the return)."""
        assert not self.dormant_un
        s = e1 - timedelta(days=eng.window_days(k) - 1)
        view = self.at(e1)
        mean = var = 0.0
        for u, last in zip(view.users, view._last_le()):
            x, opens, r = u
            if x > e1 or (r is not None and r <= e1) or (mature and month_end(x) > e1) or last >= s:
                continue
            q = 1.0
            for d in range(1, (e2 - e1).days + 1):
                age = (e1 - last).days + d
                hz = next(h for lo, hi, h in self.segs if lo <= age <= hi)
                q *= 1 - hz
            mean += 1 - q
            var += q * (1 - q)
        return mean, var
