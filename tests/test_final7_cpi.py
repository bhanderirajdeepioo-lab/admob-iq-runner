"""GA4_FINAL_DAYS (admob_iq.ga4_final; owner, 17 Nov 2026: "max to max 7 din me to aa hi jaata he") and 📉 CPI vs eCPM:
the knob moves the GA4 files' final edges (the ROI rows' "df", the nvr file's "final_till"), never the alarm's inputs —
its ROAS_C families and the level agent read the ROI rows' ages as their own shifts encode (cpi_build.C_LAG), and the
first session / returning series reach the nvr file's today − NVR_END as before the knob (their days after its final
till marked not final on the page: notes.nvr_till), until the alarm's own shifts move after its replay (step 2).
Made-up apps only (tests/test_cpi_build.make's world, its ROI and nvr site files written as roi_build / nvr_build write
them at the lag in force)."""
import gzip
import json
import os
from datetime import date, timedelta

import pytest

from admob_iq import cpi_build as cb
from admob_iq import ga4_final
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
    """The level agent off, as tests/test_cpi_build.py runs every build (its own tests switch it on)."""
    monkeypatch.setattr(cb, "agent_cfg", lambda: dict(CA.P_PROD["levels"]["agent"], mode="off"))


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


def _world(tmp_path, lag, nvr):
    data, site, dash = TC.make(tmp_path)
    _site_files(site, lag, nvr)
    assert cb.run(dash, data, site, {}, TC.NOW) == ["/cpi*"]
    cb.pop_line()
    files = {k: _load(site, "cpi_%s.json.gz" % gu.file_key(TC.IDS[k])) for k in ("a", "b")}
    ptr = {k: v for k, v in dash["cpi"].items() if k not in ("at", "fv")}     # (its time; the files' hashes)
    ptr["apps"] = {aid: {k: v for k, v in a.items() if k != "v"} for aid, a in ptr["apps"].items()}
    return files, ptr


def test_the_alarms_lag_is_its_own_shifts_never_the_knob(final_days):
    """C_LAG is what the ROAS_C shifts encode (shift = C_LAG − 2 + age) and the level agent's LAGS the same; the knob
    moves the ROI rows' final lag (ga4_cohort), never these — at the pin and at 7."""
    g3, cb3 = final_days.pin(gco, cb)
    assert cb3.C_LAG == cb.C_LAG == 3 == g3.FINAL_LAG
    for age in (0, 1, 7):
        fam = "ROAS_C%d" % age
        assert CA.FAMILIES[fam]["shift"] == cb.C_LAG - 2 + age == LA.LAGS["c_r%d" % age], fam
    g7, cb7 = final_days(7, gco, cb)
    assert (g7.FINAL_LAG, cb7.C_LAG, cb7.NVR_END) == (7, 3, 2) and ga4_final.FINAL_DAYS == 7


def test_at_7_the_alarm_reads_every_series_as_at_the_pin(tmp_path, final_days):
    """The same apps built from the GA4 files of GA4_FINAL_DAYS 3 (the rollback: the ROI rows final through newest − 3,
    the nvr file's final till today − 2) and of 7 (newest − 7, today − 7 + "td" / "rw"): every series, normal, episode,
    level and the pointer the same — the c_r ages and the first session / returning days the alarm and the page read are
    the pin's; only notes.nvr_till moves (the page's not-final mark)."""
    g3, v3, nb3 = final_days.pin(gco, gv, nb)
    f3, p3 = _world(tmp_path / "f3", g3.FINAL_LAG, nb3)
    g7, v7, nb7 = final_days(7, gco, gv, nb)
    assert (g7.FINAL_LAG, nb7.FIN_LAG, nb7.EDGES) == (7, 7, True)
    f7, p7 = _world(tmp_path / "f7", g7.FINAL_LAG, nb7)
    for k in ("a", "b"):
        n3, n7 = f3[k].pop("notes"), f7[k].pop("notes")
        assert (n3.pop("nvr_till"), n7.pop("nvr_till")) == ("2026-03-28", "2026-03-23")
        assert n7 == n3
        assert f7[k] == f3[k], k
    assert p7 == p3
    # (at the pin, the rule before the knob: install day X's age a once X + a ≤ newest − 3; the first session days to
    # today − 2, the data day t)
    d, d0 = f3["a"]["d"], date.fromisoformat(f3["a"]["day0"])
    on = lambda k: [(d0 + timedelta(days=i)).isoformat() for i, v in enumerate(d[k]) if v is not None]
    assert on("c_r0")[-1] == "2026-03-27" and on("c_r1")[-1] == "2026-03-26" and on("c_r7")[-1] == "2026-03-20"
    assert on("fs_rev")[-1] == on("rt_imp")[-1] == f3["a"]["t"] == "2026-03-28"


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
