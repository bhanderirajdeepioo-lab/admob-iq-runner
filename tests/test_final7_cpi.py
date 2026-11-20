"""GA4_FINAL_DAYS (admob_iq.ga4_final; owner, 17 Nov 2026: "max to max 7 din me to aa hi jaata he") and 📉 CPI vs eCPM:
the knob moves the GA4 files' final edges (the ROI rows' "df", the nvr file's "final_till") and the alarm's own ROAS_C
shifts (engine.cpi_alarm.c_shift: the ROI rows' final lag − 2 + age: 1 / 2 / 8 at the pin, 5 / 6 / 12 at 7), so every
ROAS_C window reads final cohort days only and none of its days is missing. The cells themselves stay as before the
knob at every F (owner, 20 Nov 2026, "Confirm aaj jaisa"): cpi_build.C_LAG = cpi_alarm.C_LAG0 = 3 (the CPI page files do
not move), level_agent.LAGS = their availability (1 / 2 / 8), and the D0 ROAS confirm reads the AdMob D0 line at its
own shift 1, so Google's D0 ROAS alarm is the same at every F. The ledger switches over once when the ROAS_C shifts
move (st["cshift"]). The first session / returning series reach the nvr file's today − NVR_END as before the knob
(their days after its final till marked not final on the page: notes.nvr_till). Made-up apps only
(tests/test_cpi_build.make's world, its ROI and nvr site files written as roi_build / nvr_build write them at the lag in
force)."""
import copy
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


def test_the_roas_c_shifts_follow_the_final_lag_while_the_cells_their_lags_and_the_d0_confirm_stay(final_days):
    """shift(ROAS_C<age>) = the ROI rows' final lag (ga4_cohort's FINAL_LAG) − 2 + age: 1 / 2 / 8 at the pin (the shifts
    before the knob), 5 / 6 / 12 at 7, 12 / 13 / 19 at 14. At every F: C_LAG = C_LAG0 = 3, level_agent.LAGS["c_r<age>"]
    = C_LAG − 2 + age (1 / 2 / 8: the cells as the build fills them), the D0 ROAS confirm reads ROAS_C0 at C_LAG − 2 = 1;
    IPU's shift and the agent's dau lag stay 1, every other family's shift 0."""
    for f, want in ((3, (1, 2, 8)), (7, (5, 6, 12)), (14, (12, 13, 19))):
        g, ca, la, b = final_days.pin(gco, CA, LA, cb) if f == 3 else final_days(f, gco, CA, LA, cb)
        assert g.FINAL_LAG == want[0] + 2 and b.NVR_END == 2, f
        assert b.C_LAG == ca.C_LAG0 == 3 and b.C_SHIFT0 == 1 and b.CA is ca and la.CA is ca
        for age, sh in zip((0, 1, 7), want):
            fam = "ROAS_C%d" % age
            assert ca.FAMILIES[fam]["shift"] == ca.c_shift(age) == sh == g.FINAL_LAG - 2 + age, (f, age)
            assert la.LAGS["c_r%d" % age] == b.C_LAG - 2 + age == (1, 2, 8)[(0, 1, 7).index(age)], (f, age)
        assert la.LAGS["dau"] == ca.FAMILIES["IPU"]["shift"] == 1 and set(la.LAGS) == {"dau", "c_r0", "c_r1", "c_r7"}
        assert all(v["shift"] == 0 for k, v in ca.FAMILIES.items() if k not in ("IPU", "ROAS_C0", "ROAS_C1", "ROAS_C7"))
        for P in (ca.P_PARITY, ca.P_PROD):
            assert P["confirm"] == {"ROAS_G": ("ROAS_C0", 0.5, 1)}, f
        assert b.C_FAMS == {"ROAS_C0", "ROAS_C1", "ROAS_C7"}
        final_days.close()


def test_the_level_agents_cut_hides_each_cell_the_build_would_not_have_had_yet(final_days):
    """level_agent.cut (the agent's as-of view, no look-ahead): as of day d a c_r<age> cell later than d − (1 / 2 / 8) is
    unknown — what a build on day d had (the cells are filled at C_LAG 3 at every F), not the family's shift."""
    for f in (3, 7):
        ca, la = final_days.pin(CA, LA) if f == 3 else final_days(f, CA, LA)
        e = ca.Ent("app", "x", "x", "x", "2026-01-01", {k: [1.0] * 40 for k in ("dau", "c_r0", "c_r1", "c_r7", "c_sp")})
        c = la.cut(e, "2026-01-31")                                  # index 30
        for k, lag in (("dau", 1), ("c_r0", 1), ("c_r1", 2), ("c_r7", 8)):
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
    nvr file's edges): the CPI file holds c_r<age> of install day X exactly while X + age ≤ newest − C_LAG (3) at every
    F — the cells (and the whole CPI file but its not-final mark) as at the pin — and the alarm's newest ROAS_C day
    b = t − shift has its whole L7 / L14 window (P_PROD reads a window with an unknown day as no value: a family quietly
    reading fewer days would never alarm); at the pin b is the newest cell, at 7 the cells after b are there, unread
    (test_the_roas_c_families_never_read_a_cell_after_their_newest_day). The first session / returning days still end at
    the data day t, as before the knob."""
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
        assert days[-1] == (t - timedelta(days=b.C_LAG - 2 + age)).isoformat(), (f, age)   # the cells: as at the pin
        assert days[-1] == b_.isoformat() if f == 3 else days[-1] > b_.isoformat(), (f, age)
        win = [(b_ - timedelta(days=j)).isoformat() for j in range(14)]
        assert set(win) <= set(days), (f, age)                       # L7 / L14: whole
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


# ── the ledger's switch-over (review P2-1): a ROAS_C shift move replays their openings elsewhere ─────────────────────

def _app(*eps):
    """One made-up app with the given ALERT episodes (TC._alert_app's shape: ROI rows, so a D0 ROAS one is checked)."""
    a = TC._alert_app(120)
    return dict(a, view=dict(a["view"], eps=[dict(a["view"]["eps"][0], **e) for e in eps]))


def _told(st, t, *eps, b=cb):
    """A ledger whose episodes were all sent at their opening (mark_notified_cpi's marks) and the app's push day."""
    b.alerts(st, False, [_app(*eps)], t, TC.NOW)
    for r in st["eps"].values():
        for n in r["notices"].values():
            if "notified_at" in n:
                n["notified_at"] = "2026-03-06T05:00:00Z"
    st["push"][TC.IDS["a"]] = "2026-03-04"
    st["due"] = {}


def _due(st):
    return {(k, d) for v in st["due"].values() for k, d in v}


def _shifts(monkeypatch, c0, ca=CA):
    """The ROAS_C shifts at another final lag (c_shift: ROAS_C0's + 0 / 1 / 7), as GA4_FINAL_DAYS sets them."""
    for fam, age in (("ROAS_C0", 0), ("ROAS_C1", 1), ("ROAS_C7", 7)):
        monkeypatch.setitem(ca.FAMILIES[fam], "shift", c0 + age)


def _sent(st, day):
    """mark_notified_cpi after a build: every due notice sent, the app's push day = `day`."""
    for v in st["due"].values():
        for k, nk in v:
            st["eps"][k]["notices"][nk]["notified_at"] = day + "T05:00:00Z"
    st["push"][TC.IDS["a"]], st["due"] = day, {}


def test_a_roas_c_shift_move_sends_nothing_already_told_on_the_switch_build_or_later(monkeypatch, final_days):
    """Written at the pin (no "cshift": C_SHIFT0 1), built at shift 5 (GA4_FINAL_DAYS 7): the D7 ROAS alarm told on 5 Mar
    replays as opened 14 Mar (9 days > MATCH_DAYS: the same record, widened by the 4-day move), the install-day ROAS
    one's re-notice moved 9 days (the same notice), the D1 ROAS one moved 14 days (a new record: seeded on the switch
    build), a re-notice the old shifts had not reached yet shown, not sent — none is due. D0 ROAS (its confirm keeps its
    shift) does not move: its new alarm is due as always, and so is another family's. A later build at 5: the D7 ROAS
    alarm told on 5 Mar now opens on 15 Mar (10 days: still the same alarm, never re-sent), and a genuinely new D1 ROAS
    alarm is sent (a record written at 5 has no widening). The rollback flip (5 → 1) switches over the same way (a new
    D7 ROAS record seeded once, a new D0 ROAS alarm sent) and drops "cshift"."""
    ca, cb_ = final_days.pin(CA, cb)                                 # (the pin's, in a session at another F too)
    assert cb_.C_SHIFT0 == ca.FAMILIES["ROAS_C0"]["shift"] == 1 and cb_.C_FAMS == {"ROAS_C0", "ROAS_C1", "ROAS_C7"}
    aid = TC.IDS["a"]
    key = lambda f, d: "%s|%s|%s" % (aid, f, d)                      # noqa: E731
    g_old = {"fam": "ROAS_G", "opened": "2026-03-04", "c": "2026-03-01", "confirm": "confirmed"}
    c7_old = {"fam": "ROAS_C7", "opened": "2026-03-05", "c": "2026-03-02", "confirm": None}
    c0_old = {"fam": "ROAS_C0", "opened": "2026-03-03", "c": "2026-02-28", "confirm": None,
              "esc": [["2026-03-06", "step"]]}
    c1_old = {"fam": "ROAS_C1", "opened": "2026-03-01", "c": "2026-02-26", "confirm": None}
    st = {"v": cb_.STATE_V, "eps": {}, "push": {}, "due": {}}
    _told(st, date(2026, 3, 7), g_old, c7_old, c0_old, c1_old, b=cb_)
    assert "cshift" not in st and len(st["eps"]) == 4 and not any("wide" in r for r in st["eps"].values())
    old = {r["fam"]: k for k, r in st["eps"].items()}

    _shifts(monkeypatch, 5, ca)                                           # GA4_FINAL_DAYS 3 → 7
    g_new = {"fam": "ROAS_G", "opened": "2026-03-24", "c": "2026-03-21", "confirm": "confirmed"}
    c7_new = dict(c7_old, opened="2026-03-14", esc=[["2026-03-23", "slide"]])   # (a re-notice the old shifts had
    #                                                                   not reached yet: shown on the switch build)
    c0_new = dict(c0_old, esc=[["2026-03-15", "step"]])
    c1_new = dict(c1_old, opened="2026-03-15")
    cpi = {"fam": "CPI", "opened": "2026-03-24", "c": "2026-03-21", "confirm": None}
    cb_.alerts(st, False, [_app(dict(g_old, closed="2026-03-10"), c7_new, c0_new, c1_new, g_new, cpi)],
              date(2026, 3, 25), TC.NOW)
    assert st["cshift"] == 5
    assert _due(st) == {(key("ROAS_G", "2026-03-24"), "open"), (key("CPI", "2026-03-24"), "open")}
    assert all(st["eps"][old[f]]["wide"] == 4 for f in ("ROAS_C0", "ROAS_C1", "ROAS_C7"))
    assert "wide" not in st["eps"][old["ROAS_G"]]
    assert key("ROAS_C7", "2026-03-14") not in st["eps"]             # the told record, matched 9 days off
    assert set(st["eps"][old["ROAS_C0"]]["notices"]) == {"open", "2026-03-06"}           # the re-notice, moved
    assert st["eps"][old["ROAS_C7"]]["notices"]["2026-03-23"] == {"day": "2026-03-23", "seeded": True}
    new_c1 = st["eps"][key("ROAS_C1", "2026-03-15")]
    assert new_c1["seeded"] is True and new_c1["notices"]["open"] == {"day": "2026-03-15", "seeded": True}
    _sent(st, "2026-03-24")

    c7_later = dict(c7_new, opened="2026-03-15")                      # the alarm told on 5 Mar, restated a day more
    c1_2 = dict(c1_old, opened="2026-04-04", c="2026-04-01")          # a new D1 ROAS alarm
    cb_.alerts(st, False, [_app(c7_later, dict(c1_new, closed="2026-03-20"), c1_2)], date(2026, 4, 5), TC.NOW)
    assert st["cshift"] == 5 and key("ROAS_C7", "2026-03-15") not in st["eps"]          # (never re-sent)
    assert _due(st) == {(key("ROAS_C1", "2026-04-04"), "open")}                         # a new alarm: sent
    assert "wide" not in new_c1 and "wide" not in st["eps"][key("ROAS_C1", "2026-04-04")]
    _sent(st, "2026-04-04")

    _shifts(monkeypatch, 1, ca)                                           # the rollback flip, 5 → 1
    g3 = dict(g_new, opened="2026-04-20", c="2026-04-17")
    c7_3 = dict(c7_old, opened="2026-04-19", c="2026-04-16")
    cb_.alerts(st, False, [_app(dict(c1_2, opened="2026-03-31"), c7_3, g3)], date(2026, 4, 21), TC.NOW)
    assert "cshift" not in st and _due(st) == {(key("ROAS_G", "2026-04-20"), "open")}
    assert key("ROAS_C1", "2026-03-31") not in st["eps"]             # (the record written at 5, 4 days off)
    assert st["eps"][key("ROAS_C7", "2026-04-19")]["seeded"] is True                     # new on the flip: seeded
    assert st["eps"][key("ROAS_C1", "2026-04-04")]["wide"] == 4 and new_c1["wide"] == 4


def test_without_a_shift_move_a_new_roas_alarm_is_sent_as_before(final_days):
    """At the pin with a ledger of no "cshift" (every ledger before the knob): no switch-over — a new D7 ROAS alarm is
    due, and the ledger file keeps no "cshift" (as before the knob)."""
    _, cb_ = final_days.pin(CA, cb)
    st = {"v": cb_.STATE_V, "eps": {}, "push": {}, "due": {}}
    cb_.alerts(st, False, [_app({"fam": "ROAS_C7", "opened": "2026-03-13", "confirm": None})], date(2026, 3, 14),
              TC.NOW)
    assert "cshift" not in st and [d for v in st["due"].values() for _, d in v] == ["open"]
    assert not any("wide" in r for r in st["eps"].values())


def test_the_ledger_keeps_its_shift_across_load_and_save(tmp_path, monkeypatch):
    _shifts(monkeypatch, 5)
    st = {"v": cb.STATE_V, "eps": {}, "push": {}, "due": {}, "cshift": 5}
    cb.alerts(st, False, [_app({"fam": "ROAS_C7", "opened": "2026-03-13", "confirm": None})], date(2026, 3, 14),
              TC.NOW)
    assert [d for v in st["due"].values() for _, d in v] == ["open"]  # (a ledger at 5 already: an ordinary build)
    cb.save_state(str(tmp_path), st)
    back, first = cb.load_state(str(tmp_path))
    assert not first and back["cshift"] == 5                          # (mark_notified_cpi saves what it loaded)


def test_the_switch_follows_the_knob(final_days):
    """At 7 the build's own copy has ROAS_C0's shift 5: a ledger without "cshift" switches over once (a new D7 ROAS
    alarm shown, not sent; a new D0 ROAS one sent as always)."""
    ca, b = final_days(7, CA, cb)
    assert b.C_SHIFT0 == 1 and ca.FAMILIES["ROAS_C0"]["shift"] == 5 and b.C_FAMS == {"ROAS_C0", "ROAS_C1", "ROAS_C7"}
    st = {"v": b.STATE_V, "eps": {}, "push": {}, "due": {}}
    b.alerts(st, False, [_app({"fam": "ROAS_C7", "opened": "2026-03-13", "confirm": None},
                              {"fam": "ROAS_G", "opened": "2026-03-13", "confirm": "confirmed"})], date(2026, 3, 14),
             TC.NOW)
    assert st["cshift"] == 5 and _due(st) == {("%s|ROAS_G|2026-03-13" % TC.IDS["a"], "open")}
    final_days.close()


# ── the engine at 7 (owner, 20 Nov 2026): D0 ROAS as at the pin; the ROAS_C families read their final days only ──────

def _i2(ca, noise=0.02):
    """tests/test_cpi_alarm.py's case I2 (Google's D0 value and the AdMob-matched D0 line both down 20 % from day 300)
    with the cells the build has: c_r<age> up to t − (C_LAG0 − 2 + age) — the module ca's own Ent."""
    from tests import test_cpi_alarm as TA
    s = TA.synth(cohort=True, noise=noise)
    TA.mul(s, "d0_inr", 300, TA.N, 0.8)
    TA.mul(s, "c_r0", 300, TA.N, 0.8)
    for age in (0, 1, 7):
        k = "c_r%d" % age
        s[k][TA.N - (ca.C_LAG0 - 2 + age):] = [None] * (ca.C_LAG0 - 2 + age)
    return ca.Ent("app", TA.APP, TA.APP, "Alpha App", TA.DAY0, s), TA


def _strip(ep):
    return {k: v for k, v in ep.items() if k != "ctx"}


def test_d0_roas_at_7_is_exactly_the_pins_its_confirm_reading_the_d0_line_at_its_own_shift(final_days):
    """At 7 the AdMob D0 line (ROAS_C0) is judged 4 days later (shift 5), but D0 ROAS's confirm still reads it at
    shift 1: every D0 ROAS episode — opening, change start, confirm, tier, re-notices, money — is the pin's (its ctx
    shows the other families' own readings, ROAS_C0's at its shift); with the confirm at ROAS_C0's own shift it opens
    later (the replay's finding the owner turned down)."""
    out = {}
    for f in (3, 7):
        ca = final_days.pin(CA) if f == 3 else final_days(f, CA)
        e, TA = _i2(ca)
        for name, P in (("parity", ca.P_PARITY), ("prod", ca.P_PROD)):
            r = ca.run([e], P, TA.T)
            out[f, name] = [ep for ep in r["episodes"] if ep["fam"] in ("ROAS_G", "ROAS_C0")]
        if f == 7:
            P = copy.deepcopy(ca.P_PROD)
            P["confirm"] = {"ROAS_G": ("ROAS_C0", 0.5)}                 # (the family's own shift: 5)
            out[7, "own"] = [ep for ep in ca.run([e], P, TA.T)["episodes"] if ep["fam"] == "ROAS_G"]
        final_days.close()
    for name in ("parity", "prod"):
        g3 = [_strip(ep) for ep in out[3, name] if ep["fam"] == "ROAS_G"]
        g7 = [_strip(ep) for ep in out[7, name] if ep["fam"] == "ROAS_G"]
        assert g3 and g3 == g7 and g3[0]["confirm"] == "confirmed" and g3[0]["opened"] == "2024-11-03", name
        c3 = [ep["opened"] for ep in out[3, name] if ep["fam"] == "ROAS_C0"]
        c7 = [ep["opened"] for ep in out[7, name] if ep["fam"] == "ROAS_C0"]
        assert c3 == ["2024-11-04"] and c7 == ["2024-11-08"], name   # the D0 line itself: 4 days later
    assert [ep["opened"] for ep in out[7, "own"]] == ["2024-11-06"]                # (3 days late)


def test_the_roas_c_families_never_read_a_cell_after_their_newest_day(final_days):
    """At 7 the series hold cells after b = t − shift (final at C_LAG0 only): any value there leaves every ROAS_C
    episode, state, normal / healthy line, level row and proposal exactly as it was — the swing, the normals, the
    strict unknown rule, the money, the entity's ends and the level rows read up to b only. (The D0 confirm reads its
    own shift: not this check.)"""
    ca = final_days(7, CA)
    e, TA = _i2(ca, noise=0.12)                                      # (noisy: the thresholds read the swing)
    junk = {k: list(v) for k, v in e.s.items()}
    for age in (0, 1, 7):
        k, sh = "c_r%d" % age, ca.FAMILIES["ROAS_C%d" % age]["shift"]
        lo, hi = TA.N - sh, TA.N - (ca.C_LAG0 - 2 + age)          # (b, the newest cell]
        assert hi - lo == 4
        for i in range(lo, hi):
            junk[k][i] = junk[k][i] * 0.05                          # (a crash: any read of it would show)
    e2 = ca.Ent(e.kind, e.id, e.app, e.label, e.day0, junk)
    fams = ("ROAS_C0", "ROAS_C1", "ROAS_C7")
    for P in (ca.P_PARITY, ca.P_PROD):
        a, b = ca.run([e], P, TA.T), ca.run([e2], P, TA.T)
        key = ("app", TA.APP)
        assert [x for x in a["episodes"] if x["fam"] in fams] == [x for x in b["episodes"] if x["fam"] in fams]
        assert [x for x in a["episodes"] if x["fam"] in fams]
        assert {f: a["state"][key][f] for f in fams} == {f: b["state"][key][f] for f in fams}
        for part in ("normal", "healthy"):
            assert a[part][key]["ROAS_C0"] == b[part][key]["ROAS_C0"]
        if P.get("levels"):
            assert {f: a["levels"][key].get(f) for f in fams} == {f: b["levels"][key].get(f) for f in fams}
            assert [x for x in a["proposals"][key] if x["fam"] in fams] == \
                [x for x in b["proposals"][key] if x["fam"] in fams]
    final_days.close()


def test_the_cpi_files_series_at_7_are_the_pins(tmp_path, final_days, monkeypatch):
    """The same apps built from the GA4 files of 3 and of 7: every series the CPI file carries ("d": spend, installs,
    GA4, the c_r<age> cells …) is the pin's — the cells stay at C_LAG at every F; what differs is only what the 7-day
    rule itself moves (the nvr not-final mark, the ROAS_C families' own readings)."""
    got = {}
    for f in (3, 7):
        mods = (gco, gv, nb, CA, LA, cb)
        g, v, n, ca, la, b = final_days.pin(*mods) if f == 3 else final_days(f, *mods)
        _off(monkeypatch, b)
        got[f] = _world(tmp_path / str(f), g.FINAL_LAG, n, b)[0]
        final_days.close()
    for k in ("a", "b"):
        assert got[3][k]["d"] == got[7][k]["d"], k
        assert got[3][k]["t"] == got[7][k]["t"] and got[3][k]["day0"] == got[7][k]["day0"]
