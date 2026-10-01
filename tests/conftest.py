"""Test-session defaults. 📦 Compare any date (IMPACT_ANY — on in the build) is OFF unless a test turns it on: it
evaluates every date of every app on each build, and the other tabs' tests run dozens of builds that never read it
(~10× their time). tests/test_impact_any.py runs it on, and checks every other output is byte-identical either way."""

import os

os.environ.setdefault("IMPACT_ANY", "false")
