"""Test-session defaults. 📦 Compare any date (IMPACT_ANY — on in the build) is OFF unless a test turns it on: it
evaluates every date of every app on each build, and the other tabs' tests run dozens of builds that never read it
(~10× their time). tests/test_impact_any.py runs it on, and checks every other output is byte-identical either way."""

import os

os.environ.setdefault("IMPACT_ANY", "false")

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _alert_policy(request, monkeypatch):
    """The one alert policy of the GA4 tabs (engine.uninstall / engine.value ALERT_POLICY — on in the build) gates which
    detected change becomes an alert. The older Uninstall / Install value tests pin the detection under it exactly as it
    was, so they run with the gate OFF; a module with ALERT_POLICY_TESTS = True (tests/test_alert_policy.py) runs it ON.
    The Active users engine has the policy built in (always on: tests/test_active_engine.py runs it)."""
    on = bool(getattr(request.module, "ALERT_POLICY_TESTS", False))
    from admob_iq.engine import uninstall, value
    monkeypatch.setattr(uninstall, "ALERT_POLICY", on)
    if hasattr(value, "ALERT_POLICY"):
        monkeypatch.setattr(value, "ALERT_POLICY", on)
