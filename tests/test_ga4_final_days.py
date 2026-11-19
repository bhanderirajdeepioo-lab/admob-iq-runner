"""GA4_FINAL_DAYS, the one finality knob of every GA4 store (admob_iq.ga4_final; owner, 17 Nov 2026: "max to max 7 din
me to aa hi jaata he"): parse (unset, empty or not a whole number → DEFAULT 7, any number clamped to 3 … 14), read once
at import (a fresh interpreter: 7 when unset or empty, as GitHub passes an unset repo variable), lag(floor) =
max(floor, F) (at F = 3 every store's own lag before the knob: the rollback), the module pure (it imports os alone),
config's "ga4_final_days" the value in effect, the build step and both history jobs handed the repo variable as it is
(one default: the module's), the session pinned at 3 (tests/conftest.py; a value the caller exports wins) and the
final_days fixture leaving nothing of another F behind, its pin the session's own modules at the pin, else their copies
at 3. Every check holds in a session at any F. SYNTHETIC values only."""
import ast
import importlib
import importlib.util
import json.decoder
import os
import subprocess
import sys

import pytest
import yaml

from admob_iq import config, ga4_final
from tests.conftest import GIVEN_FINAL_DAYS, SESSION_FINAL_DAYS, FinalDays

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows")
VAR = "${{ vars.GA4_FINAL_DAYS }}"
F0 = ga4_final.parse(SESSION_FINAL_DAYS)               # the session's F: the pin (3) unless the caller gave another
F1 = 7 if F0 != 7 else 3                                # an F other than the session's (the build's 7 at the pin)


# ── parse, read once at import, lag ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("v, want", [
    (None, 7), ("", 7), ("   ", 7), ("x", 7), ("seven", 7), ("7.5", 7), ("3.0", 7), ("0x5", 7),   # not a whole number
    ("3", 3), ("4", 4), ("7", 7), ("10", 10), ("14", 14), (" 5 ", 5), ("+6", 6), ("007", 7),
    ("2", 3), ("0", 3), ("-4", 3), ("15", 14), ("99", 14),                                       # clamped to LO … HI
    (2, 3), (7, 7), (99, 14),
])
def test_parse_defaults_bad_values_and_clamps(v, want):
    assert (ga4_final.DEFAULT, ga4_final.LO, ga4_final.HI) == (7, 3, 14)
    assert ga4_final.parse(v) == want


def _fresh(monkeypatch, v):
    """admob_iq/ga4_final.py's source run again now, GA4_FINAL_DAYS = v (None: unset) → that copy (registered nowhere:
    the session's module is untouched)."""
    if v is None:
        monkeypatch.delenv("GA4_FINAL_DAYS", raising=False)
    else:
        monkeypatch.setenv("GA4_FINAL_DAYS", v)
    spec = importlib.util.spec_from_file_location("_ga4_final_fresh", ga4_final.__file__)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_read_once_at_import(monkeypatch):
    for v, want in ((None, 7), ("", 7), ("x", 7), ("2", 3), ("99", 14), ("10", 10), (" 5 ", 5), ("3", 3)):
        m = _fresh(monkeypatch, v)
        assert (m.FINAL_DAYS, m.lag(3), m.lag(35)) == (want, max(3, want), 35), v
    m = _fresh(monkeypatch, "9")
    monkeypatch.setenv("GA4_FINAL_DAYS", "4")              # a later change of the environment is not the knob
    assert (m.FINAL_DAYS, m.lag(3)) == (9, 9)
    assert ga4_final.FINAL_DAYS == F0                      # the session's module: read once, at its import (the pin)


def test_a_fresh_interpreter_reads_the_build_default():
    """The build's own path (admob_iq.config imports the knob): unset, or empty as GitHub passes an unset repo variable,
    it is 7; set, it is the variable's; not a number, 7."""
    env = {k: v for k, v in os.environ.items() if k != "GA4_FINAL_DAYS"}
    code = "from admob_iq import config, ga4_final; print(ga4_final.FINAL_DAYS, config.settings()['ga4_final_days'])"
    for v, want in ((None, "7 7"), ("", "7 7"), ("3", "3 3"), ("12", "12 12"), ("x", "7 7")):
        e = dict(env) if v is None else dict(env, GA4_FINAL_DAYS=v)
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=e, capture_output=True, text=True, timeout=60)
        assert (r.returncode, r.stdout.strip()) == (0, want), (v, r.stderr[-400:])


def test_lag_is_the_store_floor_never_below_f(monkeypatch):
    monkeypatch.setattr(ga4_final, "FINAL_DAYS", ga4_final.LO)            # (the pin, whatever F the session runs at)
    assert [ga4_final.lag(f) for f in (3, 4, 5, 35)] == [3, 4, 5, 35]      # at the pin: every store's own old lag
    for f in range(ga4_final.LO, ga4_final.HI + 1):
        monkeypatch.setattr(ga4_final, "FINAL_DAYS", f)
        assert all(ga4_final.lag(floor) == max(floor, f) for floor in range(40)), f
    monkeypatch.setattr(ga4_final, "FINAL_DAYS", 7)
    assert [ga4_final.lag(f) for f in (3, 4, 5, 35)] == [7, 7, 7, 35]      # the default: final at 7, longer kept


def test_the_module_is_pure_and_its_names():
    """It imports os alone (never a module of the package), so any engine reads it without an import cycle; these are
    the names every store, build and test uses."""
    tree = ast.parse(open(ga4_final.__file__, encoding="utf-8").read())
    got = [(type(n).__name__, getattr(n, "module", None), [a.name for a in n.names])
           for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert got == [("Import", None, ["os"])]
    assert {k for k in vars(ga4_final) if not k.startswith("_")} == {"os", "DEFAULT", "LO", "HI", "parse",
                                                                     "FINAL_DAYS", "lag", "rollback", "page_lag"}


def test_the_rollback_gives_each_page_its_old_edge(monkeypatch):
    """At LO every page edge is its own before the knob (the files as they were); above it, the store's lag."""
    monkeypatch.setattr(ga4_final, "FINAL_DAYS", ga4_final.LO)            # (the pin, whatever F the session runs at)
    assert ga4_final.rollback() and ga4_final.page_lag(2, 5) == 2          # the pin
    for f in range(ga4_final.LO + 1, ga4_final.HI + 1):
        monkeypatch.setattr(ga4_final, "FINAL_DAYS", f)
        assert not ga4_final.rollback() and ga4_final.page_lag(2, ga4_final.lag(5)) == max(5, f), f


def test_config_reports_the_knob_in_effect(monkeypatch):
    assert config.settings()["ga4_final_days"] == ga4_final.FINAL_DAYS == F0      # (the session's: the pin, 3)
    monkeypatch.setenv("GA4_FINAL_DAYS", "9" if F0 != 9 else "4")     # read once, at import: the environment later
    assert config.settings()["ga4_final_days"] == F0                  # is not it
    monkeypatch.setattr(ga4_final, "FINAL_DAYS", F1)       # (a test's own F: the final_days fixture)
    assert config.settings()["ga4_final_days"] == F1


# ── the workflows ───────────────────────────────────────────────────────────────────────────────────────────────────
def _steps(name):
    with open(os.path.join(WF, name), encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    return [s for j in (wf.get("jobs") or {}).values() for s in (j.get("steps") or [])]


def test_the_build_and_both_history_jobs_get_the_repo_variable():
    """Every job that writes GA4 store days runs at the build's F: the build step and the two history jobs' run step
    get the repo variable AS IT IS (empty when unset → the module's DEFAULT: one default, never a second one in a
    workflow); no other step gets it."""
    for name, step in (("refresh.yml", "Build dashboard + send alerts"), ("screens-backfill.yml", "Run"),
                       ("devices-backfill.yml", "Run")):
        got = [(s.get("name"), s["env"]["GA4_FINAL_DAYS"]) for s in _steps(name)
               if "GA4_FINAL_DAYS" in (s.get("env") or {})]
        assert got == [(step, VAR)], name
    for name in sorted(n for n in os.listdir(WF) if n.endswith((".yml", ".yaml"))):
        with open(os.path.join(WF, name), encoding="utf-8") as f:
            assert "vars.GA4_FINAL_DAYS ||" not in f.read(), name
        for s in _steps(name):
            run = str(s.get("run") or "")
            if "admob_iq.build_static" in run or "--backfill" in run:
                assert (s.get("env") or {}).get("GA4_FINAL_DAYS") == VAR, (name, s.get("name"))


# ── the final_days fixture, then the session's pin ──────────────────────────────────────────────────────────────────
SRC = {   # made-up modules of the package: a store deriving from the knob, a build reading it, a paid instance of it,
    #       one first imported only later
    "_fdt_store": "from . import ga4_final\n\nFINAL_LAG = ga4_final.lag(3)\nRECENT_DAYS = max(5, FINAL_LAG + 1)\n",
    "_fdt_build": "from . import _fdt_store as st\n\nLAG = st.FINAL_LAG\n",
    "_fdt_paid": "from . import _fdt_store as st\nfrom .fetch import ga4_paid\n\n"
                 "MOD = ga4_paid.instance(st, \"admob_iq._fdt_paid_impl\")\n",
    "_fdt_late": "from . import _fdt_store as st\n\nFINAL_LAG = st.FINAL_LAG\n",
}


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    """SRC as modules of the package (its __path__ + tmp_path, this test only); the store, the build and the paid one
    imported at the pin."""
    import admob_iq
    for n, src in SRC.items():
        (tmp_path / ("%s.py" % n)).write_text(src, encoding="utf-8")
    monkeypatch.setattr(admob_iq, "__path__", list(admob_iq.__path__) + [str(tmp_path)])
    importlib.invalidate_caches()
    try:
        yield tuple(importlib.import_module("admob_iq." + n) for n in ("_fdt_store", "_fdt_build", "_fdt_paid"))
    finally:
        for n in list(SRC) + ["_fdt_paid_impl"]:
            sys.modules.pop("admob_iq." + n, None)
            vars(admob_iq).pop(n, None)


def test_final_days_copies_at_f_and_leaves_nothing_behind(synthetic):
    """Copies at F1 (7; 3 in a session the caller runs at 7) beside the session's own modules (at F0: the pin, 3)."""
    import admob_iq
    st, bu, pa = synthetic
    L0, L1 = max(3, F0), max(3, F1)                                    # the made-up store's lag at each (pin: 3, 7)
    assert (st.FINAL_LAG, st.RECENT_DAYS, bu.LAG, pa.MOD.FINAL_LAG) == (L0, max(5, L0 + 1), L0, L0)   # the session's

    def ours():
        return {k: v for k, v in sys.modules.items() if k.split(".", 1)[0] in ("admob_iq", "tests")}
    importlib.import_module("admob_iq.fetch.ga4_paid")
    before, attrs, impl = ours(), dict(vars(admob_iq)), sys.modules["admob_iq._fdt_paid_impl"]
    with pytest.MonkeyPatch.context() as mp:
        fd = FinalDays(mp)
        st7, bu7, pa7 = fd(F1, st, bu, pa)
        assert (st7.FINAL_LAG, st7.RECENT_DAYS) == (L1, max(5, L1 + 1))                      # derived at F = F1
        assert bu7.st is st7 and bu7.LAG == L1                                               # the build binds the copy
        assert pa7.MOD.FINAL_LAG == L1 and sys.modules["admob_iq._fdt_paid_impl"] is pa7.MOD  # an instance replaced
        assert (st.FINAL_LAG, bu.LAG, pa.MOD.FINAL_LAG) == (L0, L0, L0) and bu.st is st      # the real ones untouched
        assert sys.modules["admob_iq._fdt_store"] is st7 and admob_iq._fdt_store is st7     # each copy stands in
        late = importlib.import_module("admob_iq._fdt_late")                                 # first imported at F = F1
        assert late.FINAL_LAG == L1 and late.st is st7
        assert (ga4_final.FINAL_DAYS, os.environ["GA4_FINAL_DAYS"], config.settings()["ga4_final_days"]) == (
            F1, str(F1), F1)
        assert fd(99) == () and ga4_final.FINAL_DAYS == 14                                   # parsed, as the build does
        with pytest.raises(ValueError):
            fd(7, json.decoder)                                                              # not a module of the repo
        fd.close()
        assert ours() == before and dict(vars(admob_iq)) == attrs                           # every entry as it was
        assert sys.modules["admob_iq._fdt_paid_impl"] is impl and admob_iq._fdt_store is st
        fd.close()                                                                           # (again: nothing more)
    assert (ga4_final.FINAL_DAYS, os.environ["GA4_FINAL_DAYS"]) == (F0, SESSION_FINAL_DAYS)   # the session's knob
    late = importlib.import_module("admob_iq._fdt_late")                                     # imported again: the
    assert late.FINAL_LAG == L0 and late.st is st                                            # session's F


def test_pin_gives_the_session_modules_at_the_pin_else_their_copies_at_3(synthetic, monkeypatch):
    """final_days.pin: in a session at the pin, the session's own modules (nothing copied, nothing set); in a session
    the caller runs at another F, each module's copy at 3 standing in for it — the knob at 3 —, as fd(3) gives."""
    import tests.conftest as cf
    st, bu, pa = synthetic
    for session, copied in (("3", False), ("2", False), ("7", True), ("14", True)):
        monkeypatch.setattr(cf, "SESSION_FINAL_DAYS", session)
        with pytest.MonkeyPatch.context() as mp:
            fd = FinalDays(mp)
            mp.setattr(ga4_final, "FINAL_DAYS", 11)                    # (whatever the knob is when it is called)
            got = fd.pin(st, bu)
            if not copied:
                assert got == (st, bu) and fd.pin(pa) is pa and fd.mods is None and ga4_final.FINAL_DAYS == 11
            else:
                s3, b3 = got
                assert (s3.FINAL_LAG, s3.RECENT_DAYS, b3.LAG, b3.st is s3) == (3, 5, 3, True) and s3 is not st
                assert sys.modules["admob_iq._fdt_store"] is s3 and (ga4_final.FINAL_DAYS, os.environ[
                    "GA4_FINAL_DAYS"]) == (3, "3")
                assert fd.pin(pa).MOD.FINAL_LAG == 3
            fd.close()
        assert sys.modules["admob_iq._fdt_store"] is st and bu.st is st


def test_the_fixture_sets_f_for_its_own_test(final_days):
    assert final_days(7) == () and (ga4_final.FINAL_DAYS, ga4_final.lag(3), ga4_final.lag(35)) == (7, 7, 35)
    assert os.environ["GA4_FINAL_DAYS"] == "7"


def test_the_session_runs_at_the_pin():
    """tests/conftest.py sets GA4_FINAL_DAYS 3 before any admob_iq import, so every fetch suite runs on the stores'
    timelines before the knob (this test runs after the ones above, which ran at other F); a value the caller exports
    wins (setdefault: never overwritten) — the session then runs at that F."""
    with open(os.path.join(ROOT, "tests", "conftest.py"), encoding="utf-8") as f:
        src = f.read()
    pin = 'os.environ.setdefault("GA4_FINAL_DAYS", "3")'
    assert pin in src and src.index(pin) < src.index("import pytest") < src.index("from admob_iq")
    if GIVEN_FINAL_DAYS is None:                                       # unset: the pin
        assert os.environ.get("GA4_FINAL_DAYS") == "3" and ga4_final.FINAL_DAYS == 3
    else:                                                               # the caller's own, as given
        assert os.environ.get("GA4_FINAL_DAYS") == GIVEN_FINAL_DAYS
        assert ga4_final.FINAL_DAYS == ga4_final.parse(GIVEN_FINAL_DAYS)
    assert config.settings()["ga4_final_days"] == ga4_final.FINAL_DAYS == F0
