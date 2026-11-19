"""Test-session defaults. 📦 Compare any date (IMPACT_ANY — on in the build) is OFF unless a test turns it on: it
evaluates every date of every app on each build, and the other tabs' tests run dozens of builds that never read it
(~10× their time). tests/test_impact_any.py runs it on, and checks every other output is byte-identical either way.
GA4_FINAL_DAYS (admob_iq.ga4_final, read once at import; 7 in the build) is pinned at 3: every GA4 store's read
windows as before the knob, the timelines the fetch suites are built on. A test of another F sets it for itself with
the final_days fixture below (tests/test_ga4_final_days.py). A GA4_FINAL_DAYS the caller exports wins (setdefault): the
session then runs at that F (the build's own 7: GA4_FINAL_DAYS=7 python -m pytest tests/test_final7_*.py) — a test
that compares another F with the pin takes the pin's modules from final_days.pin, never the session's own."""

import os
import sys

os.environ.setdefault("IMPACT_ANY", "false")
os.environ.setdefault("IMPACT_ANY_WORKERS", "0")   # its builds in the test's own process (tests patch the engine);
#                                                    tests/test_impact_any_pool.py runs them side by side
GIVEN_FINAL_DAYS = os.environ.get("GA4_FINAL_DAYS")    # the caller's own (None: unset — the pin below)
os.environ.setdefault("GA4_FINAL_DAYS", "3")       # before any admob_iq import: the knob is read once, at import
SESSION_FINAL_DAYS = os.environ["GA4_FINAL_DAYS"]  # what the knob reads at its import: the session's F (parse of it)

import pytest  # noqa: E402


def pytest_configure(config):
    """The alert policy OFF for the whole session by default (module-scoped fixtures build their sites before any
    function-scoped fixture runs); _alert_policy below turns it on for the modules that test it."""
    from admob_iq.engine import active, uninstall, value
    for mod in (active, uninstall, value):
        mod.ALERT_POLICY = False


@pytest.fixture(autouse=True)
def _alert_policy(request, monkeypatch):
    """The one alert policy of the GA4 tabs (engine.active / uninstall / value ALERT_POLICY — on in the build) gates which
    detected change becomes an alert. The older tests and the committed frontend fixtures pin the detection under it
    exactly as it was, so they run with the gate OFF; a module with ALERT_POLICY_TESTS = True (tests/test_alert_policy.py,
    tests/test_active_engine.py) runs it ON."""
    on = bool(getattr(request.module, "ALERT_POLICY_TESTS", False))
    from admob_iq.engine import active, uninstall, value
    for mod in (active, uninstall, value):
        monkeypatch.setattr(mod, "ALERT_POLICY", on)


_MISSING = object()


def _ours(name):
    """A module this repo can copy or import at another F: the package's own, or a test helper's."""
    return name.split(".", 1)[0] in ("admob_iq", "tests")


def _parent(name):
    """(the loaded package of a submodule's name or None, the submodule's attribute name in it)."""
    pkg, _, child = name.rpartition(".")
    return (sys.modules.get(pkg) if pkg else None), child


class FinalDays:
    """GA4_FINAL_DAYS = n for ONE test while the session stays at its own F, the pin unless the caller gave one (the
    final_days fixture below).

    fd(n, *modules) sets the knob, admob_iq.ga4_final.FINAL_DAYS (and the environment, for a fresh interpreter), to
    parse(n) for the test, then returns a fresh copy of each module given (one module: its copy, else a tuple in the
    same order). A copy is the module's source run again the way fetch.ga4_paid.instance runs a paid store (a sibling
    name), so whatever it derives at import (FINAL_LAG = ga4_final.lag(…), RECENT_DAYS …) is derived at F = n. Each copy
    then stands in for its module (sys.modules and its package's attribute) for the rest of the test: a module copied
    after it, or first imported during the test, binds the copy, so copy a store before the build that reads it.

    fd.pin(*modules) → the same modules AT THE PIN (3, the rollback), whatever F the session runs at: in a session at
    the pin (this file's default) the session's own — nothing copied, nothing set, the test exactly as with them —, else
    fd(3, *modules). Call it first in a test that compares another F with the pin (before any other F's copy), with
    every module the pin's side reads, each store before the build that reads it: a session at another F then runs
    that side as a session at the pin does.

    close() (the fixture's teardown) puts the package's sys.modules entries back as they were before the first call:
    the copies and every module first imported at F = n are removed, and an entry replaced (a paid store's instance
    among them) is put back. The monkeypatch then restores the knob and the environment. The real modules are never
    reloaded: never importlib.reload one under fd either, or its globals stay at F = n for the rest of the session."""

    def __init__(self, monkeypatch):
        self.mp, self.made, self.mods, self.attrs = monkeypatch, 0, None, None

    def __call__(self, n, *mods):
        from admob_iq import ga4_final
        from admob_iq.fetch.ga4_paid import instance
        if self.mods is None:
            self.mods = {k: v for k, v in sys.modules.items() if _ours(k)}
            self.attrs = {}
            for k in self.mods:
                parent, child = _parent(k)
                if parent is not None:
                    self.attrs[k] = vars(parent).get(child, _MISSING)
        self.mp.setenv("GA4_FINAL_DAYS", str(n))
        self.mp.setattr(ga4_final, "FINAL_DAYS", ga4_final.parse(str(n)))
        out = []
        for m in mods:
            pkg, _, base = m.__name__.rpartition(".")
            if not pkg or not _ours(m.__name__):
                raise ValueError("final_days: %s is not a module of this repo's packages" % m.__name__)
            self.made += 1
            c = instance(m, "%s._final_days_%d_%s" % (pkg, self.made, base))
            sys.modules[m.__name__] = c
            parent, child = _parent(m.__name__)
            if parent is not None:
                setattr(parent, child, c)
            out.append(c)
        return out[0] if len(out) == 1 else tuple(out)

    def pin(self, *mods):
        from admob_iq import ga4_final
        if ga4_final.parse(SESSION_FINAL_DAYS) == ga4_final.LO:
            return mods[0] if len(mods) == 1 else mods
        return self(ga4_final.LO, *mods)

    def close(self):
        if self.mods is None:
            return
        for k in [k for k in sys.modules if _ours(k) and k not in self.mods]:
            parent, child = _parent(k)
            if parent is not None and vars(parent).get(child, _MISSING) is sys.modules[k]:
                delattr(parent, child)
            del sys.modules[k]
        for k, v in self.mods.items():
            sys.modules[k] = v
            parent, child = _parent(k)
            if parent is None:
                continue
            a = self.attrs.get(k, _MISSING)
            if a is not _MISSING:
                setattr(parent, child, a)
            elif child in vars(parent):
                delattr(parent, child)
        self.mods = self.attrs = None


@pytest.fixture
def final_days(monkeypatch):
    """FinalDays for one test: `cu7 = final_days(7, ga4_cube)` → ga4_cube's copy at F = 7; `final_days(7)` → the knob
    alone (for code that calls ga4_final.lag or reads ga4_final.FINAL_DAYS when it runs);
    `cu3 = final_days.pin(ga4_cube)` → ga4_cube at the pin (the session's own in a session at the pin). Nothing of it
    outlives the test."""
    fd = FinalDays(monkeypatch)
    yield fd
    fd.close()
