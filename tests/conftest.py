"""Test-session defaults. 📦 Compare any date (IMPACT_ANY — on in the build) is OFF unless a test turns it on: it
evaluates every date of every app on each build, and the other tabs' tests run dozens of builds that never read it
(~10× their time). tests/test_impact_any.py runs it on, and checks every other output is byte-identical either way."""

import os

os.environ.setdefault("IMPACT_ANY", "false")

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
