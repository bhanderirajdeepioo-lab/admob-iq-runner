"""⚖️ The small rows' "data kam" (owner, 21 Nov 2026: "haan, chhoti rows me data kam likh do"; BE_SMALL, settings
"be_small", be_build.SMALL_ON): a covered country row under $5 / 30 new users that day — a few installs' revenue is
noise — answers "data kam" (rk 7: no day, no range, no limit) in place of its curve's breakeven day. Nothing else
moves: a real fact (it broke even / it lived past its curve) stays; its curve stays in the app line and the card; its
other cells stay; the day's marks ("g" / "u" of its cells) and counts as before; counted ("data kam N (recent N)");
off: every output exactly as before it (pinned: a digest worked out once with 7e6eef6's admob_iq — the commit before
it — on the same world). No real data."""
import copy
import gzip
import json
import math
import os
import subprocess
import sys
from datetime import date

import pytest

from admob_iq import be_build as be
from tests import test_be_build as T
from tests import test_be_paid as P

L = math.log
NEWEST = "2030-12-31"
DAY = "2030-12-14"                                    # 17 days before the newest


def _fits(ccs):
    cv = [[j, [L(v), 0.0, 0.0], -0.2, 0.2, 40, L(v)] for j, v in enumerate(T.UP)]
    return {cc: {"k3": [L(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": cv, "rng": T.WIDE} for cc in ccs}


def _cty(sp, small, **kw):
    """A covered country's row on DAY: judged (its cells, nothing final: its curve unshifted) or small (under $5 / 30
    new users: only its card cells, as load() builds one); its so-far read day 6 at ROAS 0.2 (not broken even)."""
    base = dict(day=DAY, sp=sp, na=sp / 2, cpi=2.0, c=L(2.0), e=L(3.0), obs=6, oc=0.2 * sp)
    cells = [0.05 * sp, 0.1 * sp, 0.12 * sp, 0.15 * sp, 0.2 * sp]
    if small:
        base.update(n=10, jd=False, kc=cells + [None], kf=cells[:4] + [None, None])
    else:
        base.update(cum=cells + [None] * 8, fin=[None] * 13)
    base.update(kw)
    return T.R(**base)


def _day(cs, gaps=(), stats=None):
    """One install day through predict() → (its body, its "cty" rows by country)."""
    tot = sum(x.sp for x in cs.values())
    row = T.R(day=DAY, sp=tot, na=tot / 2, cum=[None] * 13, obs=0, oc=0.0)
    fc = {"origin": "2031-01-01", "fits": _fits(cs)}
    d = be.predict("k", fc, T.CAL0, (NEWEST, [row], {DAY: cs}, None, frozenset(gaps)), None, stats)["days"][0]
    return d, {c[0]: c for c in d["cty"]}


def test_a_small_row_says_data_kam_and_keeps_every_other_cell(monkeypatch):
    """Its day, low, high and lim null, rk 7; spend share, CPI, eCPM, K3's chances, B and its ROAS so far as before; a
    judged row, the app line, the card and every other field of the day as before."""
    cs = lambda: {"AA": _cty(100.0, False), "BB": _cty(4.0, True)}          # noqa: E731
    on, ron = _day(cs())
    monkeypatch.setattr(be, "SMALL_ON", False)
    off, roff = _day(cs())
    assert roff["BB"][11] == 0 and roff["BB"][7] is not None and roff["BB"][10] is not None   # (before: its curve's day)
    assert ron["BB"][7:12] == [None, None, None, None, be.RK_SMALL] and be.RK_SMALL == 7
    assert ron["BB"][:7] == roff["BB"][:7] and ron["BB"][12:] == roff["BB"][12:]
    assert ron["BB"][13] is not None                                          # (its "ROAS so far": [6, 0.2, B's])
    assert ron["AA"] == roff["AA"]
    assert {k: v for k, v in on.items() if k != "cty"} == {k: v for k, v in off.items() if k != "cty"}


def test_a_small_row_keeps_a_real_fact():
    """A small row that broke even keeps its real day (rk 1 … 4); one that lived past its curve without it keeps that
    (rk 5 / 6) — "data kam" is only ever in place of a forecast."""
    _, r = _day({"AA": _cty(100.0, False), "BB": _cty(4.0, True, rbe=(5, "x")),
                 "CC": _cty(3.0, True, obs=400, oc=2.0, sfa=400, sfv=2.0)})
    assert r["BB"][7:12] == [5, None, None, r["BB"][10], 1] and r["BB"][10] is not None
    assert r["CC"][7] == 400 and r["CC"][8:10] == [None, None] and r["CC"][11] in (5, 6)


def _marks(monkeypatch, gaps=(), ub=None):
    """The day with a judged row AA (its so-far read day 1: before the gap date) and a small row BB ≥ SAN_SHARE of the
    day (10 new users), on and off → (on, off, their counts)."""
    if ub is not None:
        monkeypatch.setattr(be, "_upi_bench", lambda byday, O: ub)
    cs = lambda: {"AA": _cty(100.0, False, obs=1, oc=10.0), "BB": _cty(40.0, True)}   # noqa: E731
    st_on, st_off = {}, {}
    on, ron = _day(cs(), gaps, st_on)
    monkeypatch.setattr(be, "SMALL_ON", False)
    off, roff = _day(cs(), gaps, st_off)
    monkeypatch.setattr(be, "SMALL_ON", True)
    assert ron["BB"][11] == be.RK_SMALL and roff["BB"][11] == 0
    return on, off, st_on, st_off


def test_a_small_row_keeps_its_gap_mark_and_the_days_data_check(monkeypatch):
    """Only the small row's cells hold a pack-gap date: its "g" (named), the day's "data check" ("chk", "ckw") and the
    "gap rows" count as before — they speak of its cells, and its "ROAS so far" is shown; it is counted "sml" (and
    "smlw" inside the last FSQ_WIN days)."""
    on, off, st_on, st_off = _marks(monkeypatch, gaps={date.fromisoformat(DAY).toordinal() + 2})
    assert off["ckc"] == {"BB": "g"} and off["chk"] == 1 and off["ckw"] == "g" and st_off["gap"] == 1
    assert {k: v for k, v in on.items() if k != "cty"} == {k: v for k, v in off.items() if k != "cty"}
    assert st_on["gap"] == st_off["gap"] and "sml" not in st_off
    assert st_on["sml"] == 1 and st_on.get("smlw", 0) == (1 if 17 <= be.FSQ_WIN else 0)


def test_a_small_row_keeps_its_users_per_install_mark(monkeypatch):
    """The small row's users per install (0.5) off its benchmark's (median 1.0, q10 … q90 0.9 … 1.1): its "u", its
    numbers ("cku") and the "users/install" count as before."""
    on, off, st_on, st_off = _marks(monkeypatch, ub={"BB": (1.0, 0.9, 1.1)})
    assert off["ckc"] == {"BB": "u"} and off["cku"] == {"BB": [0.5, 1.0]} and off["chk"] == 1 and st_off["upi"] == 1
    assert {k: v for k, v in on.items() if k != "cty"} == {k: v for k, v in off.items() if k != "cty"}
    assert st_on["upi"] == st_off["upi"]


def test_the_counts_line_names_the_small_rows():
    n = dict.fromkeys(("c1s", "c1o", "eco", "ecow", "gap", "gapw", "gapr", "gapl", "upi", "upiw", "lfail", "lfb", "lfbc",
                       "sml", "smlw"), 0)
    assert be._line5(n) == ""
    assert be._line5(dict(n, sml=12, smlw=3)) == ", data kam 12 (recent 3)"


# ── through the step: a world whose one country is small on about half its days ────────────────────────────────────

def small_world(tmp):
    """T.make's world, its app "a" with one more covered country SS: about $5 a day at CPI 0.15 (about 44 new users) —
    under $5 on about half its days, so it has a benchmark and small rows both."""
    site, data = str(tmp / "site"), str(tmp / "data")
    os.makedirs(site, exist_ok=True)
    os.makedirs(data, exist_ok=True)
    big = dict(T.CTY, SS=(5.0, 0.15, 4.0, 0.01), EE=(15.0, 0.5, 4.0, 0.01), **{cc: (1.0, 0.5, 4.0, 0.01) for cc in T.TINY})
    T.write_app(site, data, T.KEYS["a"], big, T.NDAYS, T.TODAY, 7, nvr=("AA", "BB", "CC", "SS"))
    T.write_app(site, data, T.KEYS["b"], {"EE": (40.0, 0.5, 4.0, 0.01)}, 60, T.TODAY, 11)
    dash = {"roi": {"file": "roi.json.gz", "apps": {T.APPS[k]: {"file": "roi_%s.json.gz" % T.KEYS[k], "st": "Normal"}
                                                    for k in "ab"}}}
    return site, data, dash


def _days(site):
    """{(file, day): the day without its "cty"} — every other field of every day."""
    out = {}
    for f in sorted(os.listdir(site)):
        if f.startswith("be_") and f.endswith(".json.gz"):
            with gzip.open(os.path.join(site, f), "rt", encoding="utf-8") as fh:
                for d in json.load(fh)["days"]:
                    out[(f, d["d"])] = {k: v for k, v in d.items() if k != "cty"}
    return out


def _rows(site):
    out = []
    for f in sorted(os.listdir(site)):
        if f.startswith("be_") and f.endswith(".json.gz") and not f.endswith("_o.json.gz"):
            with gzip.open(os.path.join(site, f), "rt", encoding="utf-8") as fh:
                for d in json.load(fh)["days"]:
                    out += [(d["d"], d["age"], c) for c in d.get("cty") or []]
    return out


# sha256 (tests/test_be_paid._digest) of small_world through the step — worked out once with 7e6eef6's admob_iq (the
# commit before BE_SMALL: loaded in place of this tree's, the same world and helpers), at GA4_FINAL_DAYS 3 and 7
OFF_BEFORE = {"3": "0b9e14a100b5a3b2bf06283c26e2f4908936b259bb6d72210dd56dcf3567a715",
              "7": "fb4d30ed6003149c43b5d2eef8db5f70978f6291932e191fd4eb81ca84e8ea5d"}


def test_through_the_step_small_rows_say_data_kam_and_are_counted(tmp_path):
    site, data, dash = small_world(tmp_path / "on")
    paths, line, err = P._go(copy.deepcopy(dash), data, site, {})
    rows = _rows(site)
    sm = [c for _, _, c in rows if c[11] == be.RK_SMALL]
    assert sm and all(c[7:11] == [None, None, None, None] for c in sm)
    assert {c[0] for c in sm} == {"SS"}                                       # (only the country that is small)
    recent = sum(1 for _, ag, c in rows if c[11] == be.RK_SMALL and ag <= be.FSQ_WIN)
    assert ", data kam %d (recent %d)" % (len(sm), recent) in line and err == ""
    site2, data2, dash2 = small_world(tmp_path / "off")
    paths2, line2, err2 = P._go(copy.deepcopy(dash2), data2, site2, {"be_small": False})
    rows2 = _rows(site2)
    assert not any(c[11] == be.RK_SMALL for _, _, c in rows2) and ", data kam " not in line2
    on = {(d, c[0]): c for d, _, c in rows}
    assert len(on) == len(rows2)
    for d, _, c in rows2:                                                     # every change: a forecast → "data kam",
        c1 = on[(d, c[0])]                                                    # its other cells as before
        if c1 != c:
            assert c[11] == 0 and c[10] is not None and c1[11] == be.RK_SMALL and c[0] == "SS"
            assert c1[:7] == c[:7] and c1[12:] == c[12:] and c1[7:11] == [None] * 4
    assert _days(site) == _days(site2)                                        # every other field of every day the same
    assert be.SMALL_ON is True                                                # (the step put the module's switch back)


def off_digest(tmp):
    site, data, dash = small_world(tmp)
    paths, line, err = P._go(dash, data, site, {"be_small": False})
    return P._digest(site, data, dash, paths, line, err)


def test_off_is_every_output_as_before_it(tmp_path):
    if be.LAG != be.LAG0:
        pytest.skip("pinned at the tests' GA4_FINAL_DAYS (3); the build's 7 has its own test below")
    assert off_digest(tmp_path) == OFF_BEFORE["3"]


def test_off_is_every_output_as_before_it_at_the_builds_ga4_final_days_7(tmp_path):
    """The same at the build's own GA4_FINAL_DAYS (7), in a fresh interpreter (every module reads the knob at import)."""
    code = ("import os, sys, pathlib; sys.path.insert(0, %r)\n"
            "from admob_iq.engine import active, uninstall, value\n"
            "for m in (active, uninstall, value): m.ALERT_POLICY = False\n"
            "from tests import test_be_small as S\n"
            "print(S.off_digest(pathlib.Path(%r)))\n" % (T.ROOT, str(tmp_path)))
    env = dict(os.environ, GA4_FINAL_DAYS="7", IMPACT_ANY="false", IMPACT_ANY_WORKERS="0")
    r = subprocess.run([sys.executable, "-c", code], env=env, cwd=T.ROOT, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.strip().splitlines()[-1] == OFF_BEFORE["7"]


@pytest.mark.parametrize("v,want", [(None, True), ("", True), ("true", True), ("false", False), (" 0", False),
                                    ("off", False), ("No", False)])
def test_the_switch_turns_off_on_every_usual_spelling(monkeypatch, v, want):
    from admob_iq import config
    if v is None:
        monkeypatch.delenv("BE_SMALL", raising=False)
    else:
        monkeypatch.setenv("BE_SMALL", v)
    assert config.settings()["be_small"] is want


def test_the_workflow_passes_the_switch_on_by_default():
    with open(os.path.join(T.ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        assert "BE_SMALL:             ${{ vars.BE_SMALL || 'true' }}" in f.read()
