"""GA4_FINAL_DAYS (admob_iq.ga4_final; owner, 17 Nov 2026: "max to max 7 din me to aa hi jaata he") and 📉 CPI vs eCPM:
the knob moves the GA4 files' final edges (the ROI rows' "df", the nvr file's "final_till") and, with them, the alarm's
own ROAS_C shifts (engine.cpi_alarm.c_shift: the ROI rows' final lag − 2 + age), the level agent's LAGS (the same, by
construction) and cpi_build.C_LAG (ROAS_C0's shift + 2, the rows' final lag): every ROAS_C window reads final cohort days
only, and none of its days is missing — at the pin (1 / 2 / 8, C_LAG 3: exactly as before the knob) and at 7 (5 / 6 /
12, C_LAG 7). The first session / returning series reach the nvr file's today − NVR_END as before the knob (their days
after its final till marked not final on the page: notes.nvr_till). Made-up apps only (tests/test_cpi_build.make's
world, its ROI and nvr site files written as roi_build / nvr_build write them at the lag in force)."""
import gzip
import json
import os
from datetime import date, timedelta

import pytest

from admob_iq import cpi_build as cb
from admob_iq import nvr_build as nb
from admob_iq.db import write_json_gz_stable
from admob_iq.engine import cpi_alarm as CA
from admob_iq.engine import level_agent as LA
from admob_iq.fetch import ga4_cohort as gco
from admob_iq.fetch import ga4_nvr as gv
from admob_iq.fetch import ga4_uninstall as gu
from tests import test_cpi_build as TC


@pytest.fixture(autouse=True)
def _agent_off(monkeypatch):
    """The level agent off, as tests/test_cpi_build.py runs every build (its own tests switch it on) — a copy of the
    build at another F too (_off)."""
    _off(monkeypatch, cb)


def _off(monkeypatch, mod):
    monkeypatch.setattr(mod, "agent_cfg", lambda: dict(mod.CA.P_PROD["levels"]["agent"], mode="off"))


def _model():
    """make()'s own days of every app (the same seeds, the same order)."""
    every = TC.days(TC.DAY0, TC.TODAY)
    out = {}
    for i, k in enumerate(TC.NAMES):
        g = TC.prng(101 + i)
        out[k] = {x: TC.model(k, x, g) for x in every}
    return out


def _site_files(site, lag, nvr):
    """Alpha's and Beta's ROI and nvr site files as the builds write them: the ROI rows' "d" (every age read, 0 … 30)
    final through newest − lag ("df", roi_build._cohorts), "newest" = the cohort read's today; the nvr file's edges from
    nvr_build (`nvr`: the module at the F in force — FIN_LAG, and "td" / "rw" only off the rollback)."""
    M, newest = _model(), date.fromisoformat(TC.TODAY)
    for k in ("a", "b"):
        key = gu.file_key(TC.IDS[k])
        rows = []
        for x in TC.days(TC.DAY0, TC.TODAY):
            m, age = M[k][x], (newest - date.fromisoformat(x)).days
            obs = min(gco.LAGS - 1, age)
            sp = round(m["sp"] * TC.fxd(x), 2)
            r0 = sp * m["roas"] * 0.9
            d = [round(r0 * (1 + 0.05 * a), 4) for a in range(obs + 1)]
            rows.append([x, int(m["inst"] * 1.1), m["inst"], sp, d, max(0, min(obs, age - lag) + 1)])
        write_json_gz_stable(os.path.join(site, "roi_%s.json.gz" % key),
                             {"rows": rows, "newest": TC.TODAY, "consts": {"final_lag": lag}})
        nd = []
        for x in TC.days(TC.DAY0, TC.TODAY):
            m = M[k][x]
            nd.append([x, [round(m["rev"] * 0.24, 4), int(m["imp"] * 0.3), round(m["rev"] * 0.76, 4),
                           int(m["imp"] * 0.7), 0, 0], [100, int(m["inst"] * 1.1), 400, m["dau"]], {}, {}])
        body = {"days": nd, "final_till": (newest - timedelta(days=nvr.FIN_LAG)).isoformat()}
        if nvr.EDGES:
            body.update(td=TC.TODAY, rw=nvr._rw())
        write_json_gz_stable(os.path.join(site, "nvr_%s.json.gz" % key), body)


def _load(site, fn):
    with gzip.open(os.path.join(site, fn), "rt", encoding="utf-8") as f:
        return json.load(f)


def _world(tmp_path, lag, nvr, build=None):
    build = build or cb
    data, site, dash = TC.make(tmp_path)
    _site_files(site, lag, nvr)
    assert build.run(dash, data, site, {}, TC.NOW) == ["/cpi*"]
    build.pop_line()
    files = {k: _load(site, "cpi_%s.json.gz" % gu.file_key(TC.IDS[k])) for k in ("a", "b")}
    ptr = {k: v for k, v in dash["cpi"].items() if k not in ("at", "fv")}     # (its time; the files' hashes)
    ptr["apps"] = {aid: {k: v for k, v in a.items() if k != "v"} for aid, a in ptr["apps"].items()}
    return files, ptr


def test_the_alarms_lag_is_the_roi_rows_final_lag_at_the_pin_and_at_7(final_days):
    """shift(ROAS_C<age>) = C_LAG − 2 + age = level_agent.LAGS["c_r<age>"], C_LAG = the ROI rows' final lag (ga4_cohort's
    FINAL_LAG): 1 / 2 / 8 and 3 at the pin (the shifts before the knob), 5 / 6 / 12 and 7 at 7; IPU's shift and the
    agent's dau lag stay 1, every other family's shift 0."""
    for f, want in ((3, (1, 2, 8)), (7, (5, 6, 12)), (14, (12, 13, 19))):
        g, ca, la, b = final_days.pin(gco, CA, LA, cb) if f == 3 else final_days(f, gco, CA, LA, cb)
        assert b.C_LAG == g.FINAL_LAG == want[0] + 2 and b.NVR_END == 2, f
        assert b.CA is ca and la.CA is ca
        for age, sh in zip((0, 1, 7), want):
            fam = "ROAS_C%d" % age
            assert ca.FAMILIES[fam]["shift"] == ca.c_shift(age) == sh == b.C_LAG - 2 + age == la.LAGS["c_r%d" % age]
        assert la.LAGS["dau"] == ca.FAMILIES["IPU"]["shift"] == 1 and set(la.LAGS) == {"dau", "c_r0", "c_r1", "c_r7"}
        assert all(v["shift"] == 0 for k, v in ca.FAMILIES.items() if k not in ("IPU", "ROAS_C0", "ROAS_C1", "ROAS_C7"))
        final_days.close()


def test_the_level_agents_cut_hides_each_roas_c_cell_until_its_shift_matured(final_days):
    """level_agent.cut (the agent's as-of view, no look-ahead): as of day d a c_r<age> cell later than d − its shift is
    unknown — the alarm's own shift at every F."""
    for f in (3, 7):
        ca, la = final_days.pin(CA, LA) if f == 3 else final_days(f, CA, LA)
        e = ca.Ent("app", "x", "x", "x", "2026-01-01", {k: [1.0] * 40 for k in ("dau", "c_r0", "c_r1", "c_r7", "c_sp")})
        c = la.cut(e, "2026-01-31")                                  # index 30
        for k in ("dau", "c_r0", "c_r1", "c_r7"):
            lag = la.LAGS[k]
            assert c.s[k][30 - lag] == 1.0 and c.s[k][30 - lag + 1:] == [None] * lag, (f, k)
        assert c.s["c_sp"][30] == 1.0
        final_days.close()


def _cr_days(f):
    d, d0 = f["d"], date.fromisoformat(f["day0"])
    return {k: [(d0 + timedelta(days=i)).isoformat() for i, v in enumerate(d[k]) if v is not None]
            for k in ("c_r0", "c_r1", "c_r7", "fs_rev", "rt_imp")}


@pytest.mark.parametrize("f", [3, 7])
def test_every_roas_c_window_reads_final_cohort_days_only_and_none_is_missing(tmp_path, final_days, monkeypatch, f):
    """The same apps built from the GA4 files of GA4_FINAL_DAYS f (the ROI rows final through newest − FINAL_LAG, the
    nvr file's edges): the CPI file holds c_r<age> of install day X exactly while X + age ≤ newest − C_LAG (final), so
    the alarm's newest ROAS_C day b = t − shift has its cell and the day after it has none — every L7 / L14 window of the
    family is whole (P_PROD reads a window with an unknown day as no value: a family quietly reading fewer days would
    never alarm). The first session / returning days still end at the data day t, as before the knob."""
    mods = (gco, gv, nb, CA, LA, cb)
    g, v, n, ca, la, b = final_days.pin(*mods) if f == 3 else final_days(f, *mods)
    _off(monkeypatch, b)
    fs, ptr = _world(tmp_path, g.FINAL_LAG, n, b)
    a = fs["a"]
    t, on = date.fromisoformat(a["t"]), _cr_days(a)
    assert a["t"] == "2026-03-28" and on["fs_rev"][-1] == on["rt_imp"][-1] == a["t"]
    assert a["notes"]["nvr_till"] == ("2026-03-28" if f == 3 else "2026-03-23")   # (the page's not-final mark)
    for age in (0, 1, 7):
        sh = ca.FAMILIES["ROAS_C%d" % age]["shift"]
        b_ = t - timedelta(days=sh)
        days = on["c_r%d" % age]
        assert days[-1] == b_.isoformat(), (f, age)                  # the newest cell = the family's newest day
        win = [(b_ - timedelta(days=j)).isoformat() for j in range(14)]
        assert set(win) <= set(days), (f, age)                       # L7 / L14: whole
    if f == 7:                                                         # (the pin's newest days: 4 days later)
        assert (on["c_r0"][-1], on["c_r1"][-1], on["c_r7"][-1]) == ("2026-03-23", "2026-03-22", "2026-03-16")
    else:
        assert (on["c_r0"][-1], on["c_r1"][-1], on["c_r7"][-1]) == ("2026-03-27", "2026-03-26", "2026-03-20")


def test_a_file_without_the_edges_reads_as_before(tmp_path):
    """An ROI file with no "newest" (a build before it, the committed fixtures) takes each row's own df; an nvr file
    with no "td" ends its series at its final till — tests/test_cpi_build.py's world, untouched."""
    data, site, dash = TC.make(tmp_path)
    assert cb.run(dash, data, site, {}, TC.NOW) == ["/cpi*"]
    cb.pop_line()
    f = _load(site, "cpi_%s.json.gz" % gu.file_key(TC.IDS["a"]))
    d, d0 = f["d"], date.fromisoformat(f["day0"])
    last = lambda k: max((d0 + timedelta(days=i)).isoformat() for i, v in enumerate(d[k]) if v is not None)
    assert f["notes"]["nvr_till"] == last("fs_rev") == "2026-03-27"        # (make's nvr final till: no "td")
    assert last("c_r0") == "2026-03-27" and last("c_r7") == "2026-03-20"   # (make's df = age − 2: c_r7 from age 10)
