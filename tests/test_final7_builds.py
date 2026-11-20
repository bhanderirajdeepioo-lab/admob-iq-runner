"""GA4_FINAL_DAYS in the builds (owner, 17 Nov 2026: "max to max 7 din me to aa hi jaata he"): every build takes its
edge from the store that produced its data (ga4_final through the store's FINAL_LAG), never a literal. At the pin (3,
the rollback — final_days.pin: the session's own modules, or their copies at 3 in a session the caller runs at another
F): every page file exactly as before the knob (ga4_final.page_lag: each page's own old edge, no new field); at 7: a
day is final once 7 days old. Checked here, at 3 and at 7: the derived constants and their equalities; the
files' edge fields ("final_till" / "ft", "td", "rw"; the Breakeven pointer's "pv" / "lag" only off the old values);
Breakeven's caches made again at once when the lag moves and byte for byte back at the rollback; the card's final cells,
the "so far" flag, the maturity age and the pack-gap limit at CLAG / LAG 7; be_ecpm's day-1 rule; First open's status
on final days and its exact counts only from reads made once final; Screens' final edge while its periods keep ending
on the page's latest day; Revenue by source's final till. Made-up worlds only (the existing suites' helpers)."""
import copy
import gzip
import json
import math
import os
from datetime import date, datetime, timedelta, timezone

from admob_iq import be_build as be
from admob_iq import be_ecpm as bec
from admob_iq import firstopen_build as fb
from admob_iq import ga4_final
from admob_iq import nvr_build as nb
from admob_iq import screens_build as scb
from admob_iq import source_build as srb
from admob_iq.db import write_json_gz_stable
from admob_iq.fetch import ga4_cecpm as gce
from admob_iq.fetch import ga4_cohort as gco
from admob_iq.fetch import ga4_cube as gcu
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_firstopen_cc as gfc
from admob_iq.fetch import ga4_nvr as gv
from admob_iq.fetch import ga4_nvr_uc as gnc
from admob_iq.fetch import ga4_screens as gs
from admob_iq.fetch import ga4_source as gsrc
from admob_iq.fetch import ga4_source_cty as gsc
from admob_iq.fetch import ga4_uninstall as gu
from tests import test_be_build as TB
from tests import test_be_ecpm as TE
from tests import test_firstopen_build as TF
from tests import test_firstopen_exact as TX
from tests import test_ga4_source as TS
from tests import test_ga4_source_split as TSS
from tests import test_nvr_build as TN
from tests import test_screens_build as TSC


def _gz(path):
    with gzip.open(str(path), "rt", encoding="utf-8") as f:
        return json.load(f)


# ── the derivations ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_every_build_edge_is_its_stores_lag_at_3_and_7(final_days):
    (gcu3, gco3, gce3, gv3, gnc3, gf3, gfc3, gs3, gsrc3, gsc3, be3, bec3, nb3, fb3, scb3, srb3) = final_days.pin(
        gcu, gco, gce, gv, gnc, gf, gfc, gs, gsrc, gsc, be, bec, nb, fb, scb, srb)
    assert ga4_final.FINAL_DAYS == 3 and ga4_final.rollback()      # (the pin: the rollback)
    # Breakeven: exactly as before the knob; its lag IS the exact store's (the cube's the same)
    assert (be3.LAG, be3.PROV, be3.CLAG) == (be3.LAG0, be3.PROV0, 4) == (3, 4, 4)
    assert be3.LAG == gco3.FINAL_LAG == gcu3.FINAL_LAG
    # the page edges at the pin, the rollback: each page's own edge before the knob (td − 2; no "td" / "rw" / source
    # final till; day 1 not final while the first-session store reads it again) — the stores' lags as before (3 / 4 / 5)
    assert (fb3.FIN_LAG, fb3.EX_AGE, fb3.EX_AGE0, fb3.EDGES) == (2, 2, 2, False)
    assert gf3.FINAL_LAG == gfc3.FINAL_LAG == 3
    assert (nb3.FIN_LAG, nb3.EDGES) == (2, False) and gv3.FINAL_LAG == gnc3.FINAL_LAG == 4
    assert nb3._rw() == gv3.RECENT_DAYS == gnc3.RECENT_DAYS == 5 and bec3.P1_AGE == gv3.RECENT_DAYS
    assert (scb3.FT_LAG, scb3.ST_LAG) == (2, gs3.FINAL_LAG) == (2, 5) and scb3.PE_LAG == gs3.PU_LAG == 2
    assert gsrc3.FINAL_LAG == gsc3.FINAL_LAG == 4 and not srb3.FINAL_TILL
    stamp3 = bec3.stamp()
    # at 7: the stores first, then the builds that read them (each copy binds the copies made before it)
    (gcu7, gco7, gv7, gnc7, gf7, gfc7, gs7, gsrc7, gsc7, be7, bec7, nb7, fb7, scb7, srb7) = final_days(
        7, gcu, gco, gv, gnc, gf, gfc, gs, gsrc, gsc, be, bec, nb, fb, scb, srb)
    assert (be7.LAG, be7.PROV, be7.CLAG) == (7, 7, 7) and be7.LAG == gco7.FINAL_LAG == gcu7.FINAL_LAG
    assert be7.LAG0 == be3.LAG0 and be7.PROV0 == be3.PROV0                     # (the old values, at every F)
    assert bec7.bb is be7 and bec7.stamp() != stamp3                          # the eCPM benchmark: made again too
    assert bec7.P1_AGE == gv7.FINAL_LAG == 7
    assert fb7.FIN_LAG == fb7.EX_AGE == gf7.FINAL_LAG == gfc7.FINAL_LAG == 7 and fb7.EX_AGE0 == 2 and fb7.EDGES
    assert nb7.FIN_LAG == gv7.FINAL_LAG == gnc7.FINAL_LAG == 7 and nb7.EDGES
    assert nb7._rw() == gv7.RECENT_DAYS == gnc7.RECENT_DAYS == 8
    assert scb7.FT_LAG == scb7.ST_LAG == gs7.FINAL_LAG == 7 and scb7.PE_LAG == gs7.PU_LAG == 2
    assert gsrc7.FINAL_LAG == gsc7.FINAL_LAG == 7 and srb7.gs is gsrc7 and srb7.FINAL_TILL
    # the Screens periods the page offers are still the ones the fetch reads the users of
    for td in (date(2026, 11, 4), date(2026, 3, 1), date(2024, 2, 29), date(2026, 12, 31)):
        for d0 in (td, td - timedelta(days=1), td - timedelta(days=45), td - timedelta(days=400), td.replace(day=1)):
            assert scb7.pwin(td, d0) == [(k, lo.isoformat(), hi.isoformat(), kd) for k, lo, hi, kd in gs7.pu_wanted(td, d0)]


# ── 📈 eCPM: the file's edges ───────────────────────────────────────────────────────────────────────────────────────

def test_the_ecpm_file_carries_its_edges_and_only_they_move(tmp_path, final_days):
    gv3, gnc3, nb3 = final_days.pin(gv, gnc, nb)

    def run(mod, tag):
        data, out = tmp_path / tag / "data", tmp_path / tag / "site"
        (data / gv.DIR).mkdir(parents=True)
        out.mkdir()
        write_json_gz_stable(str(data / gv.DIR / (gu.file_key(TN.AID) + ".json.gz")), TN.store())
        assert mod.run({}, str(data), str(out), {}, TN.NOW) == ["/nvr*"]
        return _gz(out / ("nvr_%s.json.gz" % gu.file_key(TN.AID)))
    b3 = run(nb3, "f3")                             # the rollback: the file as before the knob (today − 2, no new
    #                                                 field)
    assert b3["final_till"] == "2026-10-31" and not {"td", "rw"} & set(b3)
    gv7, gnc7, nb7 = final_days(7, gv, gnc, nb)
    b7 = run(nb7, "f7")                             # a day final once 7 days old; the newest 8 read again
    assert (b7["final_till"], b7["td"], b7["rw"]) == ("2026-10-26", "2026-11-02", 8)
    rest = lambda b: {k: v for k, v in b.items() if k not in ("final_till", "td", "rw")}     # noqa: E731
    assert rest(b7) == rest(b3)                     # every day as it was: only the edges move


# ── 🆕 First open: the status on final days, exact counts from final reads ───────────────────────────────────────────

def test_first_open_at_7_judges_the_status_on_final_days_and_says_today(tmp_path, final_days):
    gf7, gfc7, fb7 = final_days(7, gf, gfc, fb)
    now = datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc) + timedelta(days=7)     # final till 11 Oct at 7
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(os.path.join(data, gf.DIR))
    os.makedirs(out)
    for i, (h7, h28, kw) in enumerate([(0.50, 0.60, {}), (0.57, 0.60, {}), (0.70, 0.60, {}), (0.61, 0.60, {}),
                                       (0.61, 0.60, {"days": 20}), (0.61, 0.60, {"splash": 10})], 1):
        TF._store(data, "a~%d" % i, kw.pop("days", 60), h7, h28, **kw)
    TF._cc_store(data, "a~1")
    assert fb7.run({}, data, out, {}, now=now) == ["/firstopen*"]
    body = _gz(os.path.join(out, fb.FILE))
    st = {x["key"]: x["status"] for x in body["summary"]}
    assert [st[gu.file_key("a~%d" % i)] for i in range(1, 7)] == ["Worse", "Watch", "Better", "Normal", "Too early", "N/A"]
    a1 = next(a for a in body["apps"] if a["app_id"] == "a~1")
    assert (a1["final_till"], a1["td"]) == ("2026-10-11", "2026-10-18") and a1["days"][-1][0] == "2026-10-13"
    x1 = next(x for x in body["summary"] if x["key"] == a1["key"])
    assert abs(x1["s2h"] - 0.5) < 1e-6 and x1["final_days"] == 58          # the 7 final days to 11 Oct, never 12 / 13
    cc = _gz(os.path.join(out, fb.cc_file(a1["key"])))
    assert cc["final_till"] == "2026-10-11" and cc["missing"] == 0 and cc["summary"][0]["status"] == "Worse"


def _cc_reads(data, ages, lag):
    """The country store of TX.AID: {day: read age} → each day's exact funnel (TX.EXACT), whole and unsampled, read
    that many days after it — kept final ("fin") when read `lag` days on or later (the store's lag in force then)."""
    recs = {}
    for d, age in ages.items():
        at = date.fromisoformat(d) + timedelta(days=age)
        recs[d] = {"c": {"XA": list(TX.EXACT)}, "t": list(TX.EXACT), "smp": None, "fin": age >= lag,
                   "sg": gfc.sig(TX.STEPS), "at": at.isoformat() + "T00:05:00Z"}
    write_json_gz_stable(gfc.store_path(data, TX.AID), {"v": gfc.STORE_V, "app_id": TX.AID, "days": recs})


def test_exact_counts_come_only_from_a_country_read_made_once_the_day_is_final(tmp_path, final_days):
    gf3, gfc3, fb3 = final_days.pin(gf, gfc, fb)
    data = str(tmp_path / "data")
    os.makedirs(os.path.join(data, gf.DIR))
    os.makedirs(os.path.join(data, gfc.DIR))
    TX._main(data)                                                  # Oct 1 … 11 read sampled by the First open store
    _cc_reads(data, {d: (7 if d <= "2026-10-04" else 6) for d in TX.SAMPLED}, lag=7)    # the store's reads at 7
    store = gf.load_store(gf.store_path(data, TX.AID))
    assert sorted(fb3.exact_days(data, store)) == TX.SAMPLED       # at 3: every read 2+ days after its day counts
    gf7, gfc7, fb7 = final_days(7, gf, gfc, fb)
    ex = fb7.exact_days(data, store, till="2026-10-11")             # at 7: only the reads made once the day was final
    assert sorted(ex) == TX.SAMPLED[:4] and all(v == TX.EXACT for v in ex.values())   # (one at 6: a not-final read)


def test_exact_counts_keep_the_reads_the_country_store_kept_final_before_the_knob(tmp_path, final_days):
    """The deploy: the country store's records read final at D+3 before GA4_FINAL_DAYS (fin: never read again) stay
    exact for every day final here — never for a day after the final till; a read made at 5 under 7 (fin false: a
    not-final read) never counts. At the pin: every read 2+ days on, as before the knob."""
    gf3, gfc3, fb3 = final_days.pin(gf, gfc, fb)
    data = str(tmp_path / "data")
    os.makedirs(os.path.join(data, gf.DIR))
    os.makedirs(os.path.join(data, gfc.DIR))
    TX._main(data)
    _cc_reads(data, {d: 3 for d in TX.SAMPLED}, lag=3)             # the pin's reads: final at D+3
    store = gf.load_store(gf.store_path(data, TX.AID))
    gf7, gfc7, fb7 = final_days(7, gf, gfc, fb)
    ex = fb7.exact_days(data, store, till="2026-10-08")
    assert sorted(ex) == TX.SAMPLED[:8] and all(v == TX.EXACT for v in ex.values())   # ≤ final till only
    assert fb7.exact_days(data, store) == {}                        # (no final till given: only reads made at 7+)
    _cc_reads(data, {d: 5 for d in TX.SAMPLED}, lag=7)             # read at 5 under 7: not final when read
    assert fb7.exact_days(data, store, till="2026-10-11") == {}
    assert sorted(fb3.exact_days(data, store)) == TX.SAMPLED       # the pin: 2+ days on, as before the knob
    # through the build at 7 (final till 11 Oct): the pin's D+3 reads of the final days are the rows' exact counts
    _cc_reads(data, {d: 3 for d in TX.SAMPLED}, lag=3)
    out = str(tmp_path / "site")
    os.makedirs(out)
    now = datetime(2026, 10, 11, 6, 0, tzinfo=timezone.utc) + timedelta(days=7)
    assert fb7.run({}, data, out, {}, now=now) == ["/firstopen*"]
    rows = {r[0]: r for r in _gz(os.path.join(out, fb.FILE))["apps"][0]["days"]}
    assert [d for d in TX.SAMPLED if rows[d][fb.XI] == 1] == TX.SAMPLED and rows[TX.SAMPLED[0]][1:4] == TX.EXACT


# ── 🖼️ Screens: the final edge moves, the periods keep the page's latest day ─────────────────────────────────────────

def test_screens_final_edge_is_the_stores_and_the_periods_end_on_the_pages_latest_day(tmp_path, final_days):
    gs3, scb3 = final_days.pin(gs, scb)
    data, out, dash = TSC.build(tmp_path / "f3")
    assert scb3.run(dash, str(data), str(out), {}, TSC.NOW) == ["/scr_*"]
    one3 = _gz(out / "scr_all.json.gz")["apps"][TSC.AID]
    assert (one3["ft"], one3["td"]) == ("2026-11-02", "2026-11-04")          # at 3, the rollback: td − 2 as before
    gs7, scb7 = final_days(7, gs, scb)
    data7, out7, dash7 = TSC.build(tmp_path / "f7")
    assert scb7.run(dash7, str(data7), str(out7), {}, TSC.NOW) == ["/scr_*"]
    one = _gz(out7 / "scr_all.json.gz")["apps"][TSC.AID]
    f2 = _gz(out7 / ("scr_%s.json.gz" % TSC.KEY))
    assert (one["ft"], one["td"], f2["ft"], f2["td"]) == ("2026-10-28", "2026-11-04", "2026-10-28", "2026-11-04")
    assert dash7["scr"]["apps"][TSC.AID]["ft"] == "2026-10-28"
    # the status window, the app's daily users and the screens' users: final days only (≤ ft)
    assert f2["notes"]["w"][1] <= one["ftu"] <= one["ft"] and f2["notes"]["ftu"] == one["ftu"]
    days = TSC._days(one["d0"], "2026-11-04")
    k = days.index(one["ftu"])
    assert one["au"][k] and all(v is None for v in one["au"][k + 1:]) and all(v is None for v in f2["U"][k + 1:])
    # the periods: still the 7 / 30 / 60 / 90 days ending td − 2 (their days after ft not final), the fetch's own
    assert f2["pw"] == [list(x) for x in scb7.pwin("2026-11-04", one["d0"])]
    assert ["2026-10-27_2026-11-02", "2026-10-27", "2026-11-02", "roll"] in f2["pw"]
    assert set(one["sg"]) == {w[0] for w in f2["pw"]}
    # a store month file that cannot be read: the days it may have held end at the store's own edge
    assert scb7.lost_span({"reads": {}}, "t", "2026-10", date(2026, 11, 4)) == ("2026-10-01", "2026-10-28")
    assert scb3.lost_span({"reads": {}}, "t", "2026-10", date(2026, 11, 4)) == ("2026-10-01", "2026-10-30")


def test_screens_signals_of_a_rolling_period_ending_after_ft_are_judged_on_as_many_final_days(tmp_path, final_days):
    """tests/test_screens_build.py's world whose main screen's banner shows 36 % of its fills and 40 % fewer ads per user
    from W0 (24 Oct): at 7 (ft 28 Oct) the 7 days ending td − 2 (27 Oct … 2 Nov, two of them final) are judged on the 7
    FINAL days ending ft (sig_win) — ⚠️ on them, 🔻 against the 7 before — never on 2 days (🔻 needs 7 days with users
    on each side: it was never judged); a period ending at ft (every one at the pin) on its own days."""
    gs7, scb7 = final_days(7, gs, scb)
    data, out, dash = TSC.build(tmp_path, {"show_w": 0.6})
    assert scb7.run(dash, str(data), str(out), {}, TSC.NOW) == ["/scr_*"]
    f2, one = _gz(out / ("scr_%s.json.gz" % TSC.KEY)), _gz(out / "scr_all.json.gz")["apps"][TSC.AID]
    k7, main = "2026-10-27_2026-11-02", "s%d" % {c: i for i, (c, _) in enumerate(f2["screens"])}[TSC.MAIN]
    assert one["ft"] == "2026-10-28" and [k7, "2026-10-27", "2026-11-02", "roll"] in f2["pw"]
    assert scb7.sig_win("2026-10-27", "2026-11-02", one["ft"], one["d0"]) == ("2026-10-22", "2026-10-28")
    codes = {x[0]: x for x in f2["sig"][k7][main]}
    assert set(codes) == {"w", "d"} and one["sg"][k7] == [0, 1, 1]
    assert codes["d"][3:] == ["2026-10-15", "2026-10-21"] and codes["d"][2] <= (1 - scb.SIG_DROP) * codes["d"][1]
    assert codes["w"][1] == "unit_a" and codes["w"][2] < scb.SIG_SHOW
    # the rule: a rolling period ending after ft → as many days ending ft, never before d0; one ending at ft → itself
    assert scb.sig_win("2026-10-27", "2026-11-02", "2026-11-02", "2026-08-01") == ("2026-10-27", "2026-11-02")
    assert scb.sig_win("2026-10-27", "2026-11-02", "2026-10-28", "2026-10-25") == ("2026-10-25", "2026-10-28")


# ── 💰 Revenue by source: the final till for the page's not-final mark ──────────────────────────────────────────────

def test_revenue_by_source_carries_its_final_till(tmp_path, final_days):
    gsrc3, gsc3, srb3 = final_days.pin(gsrc, gsc, srb)
    e3, b3 = srb3.build_app(TS._store(), TS.AID, "Alpha", TS.NOW)
    assert e3["today"] == "2026-10-31" and "final_till" not in e3  # at 3, the rollback: no mark, as before the knob
    data, out = str(tmp_path / "data"), tmp_path / "site"
    out.mkdir()
    TSS._country_store(data)
    P3 = _gz(out / srb3.cc_files(data, str(out), TSS.AID, TSS.NOW)["file"])
    assert P3["today"] == "2026-10-31" and "final_till" not in P3
    gsrc7, gsc7, srb7 = final_days(7, gsrc, gsc, srb)
    e7, b7 = srb7.build_app(TS._store(), TS.AID, "Alpha", TS.NOW)
    assert e7["final_till"] == "2026-10-24" and b7 == b3
    assert {k: v for k, v in e7.items() if k != "final_till"} == e3
    P7 = _gz(out / srb7.cc_files(data, str(out), TSS.AID, TSS.NOW)["file"])
    assert P7["final_till"] == "2026-10-24" and P7["P"] == P3["P"]          # the periods' sums as they were


# ── ⚖️ Breakeven ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _cal(data, name="calib.json"):
    with open(os.path.join(data, "be_tab", name), encoding="utf-8") as f:
        return json.load(f)


def test_breakeven_caches_are_made_again_at_once_when_the_lag_moves_and_byte_for_byte_back(tmp_path, final_days):
    gcu3, gco3, gce3, gv3, be3, bec3 = final_days.pin(gcu, gco, gce, gv, be, bec)
    site, data, dash = TB.make(tmp_path)
    d3 = copy.deepcopy(dash)
    assert be3.run(d3, data, site, {}, TB.NOW) == ["/be_*"] and TB._l4(be3.pop_line()).endswith("refit yes, calib yes")
    first = TB._snap(site, data)
    fits = lambda: _gz(be3._fits_path(data, TB.KEYS["a"]))                    # noqa: E731
    assert "lag" not in _cal(data) and "lag" not in fits() and not {"pv", "lag"} & set(d3["be"])   # (as before)
    gcu7, gco7, be7 = final_days(7, gcu, gco, be)
    d7 = copy.deepcopy(dash)                        # GA4_FINAL_DAYS 7 deployed the same UTC day: made again at once
    assert be7.run(d7, data, site, {}, TB.NOW + timedelta(hours=2)) == ["/be_*"]
    assert TB._l4(be7.pop_line()).endswith("refit yes, calib yes")
    assert _cal(data)["lag"] == 7 and fits()["lag"] == 7 and (d7["be"]["pv"], d7["be"]["lag"]) == (7, 7)
    d7b = copy.deepcopy(dash)                       # … once: the next build that day reads the caches
    be7.run(d7b, data, site, {}, TB.NOW + timedelta(hours=3))
    assert TB._l4(be7.pop_line()).endswith("refit no, calib no") and d7b["be"] == d7["be"]
    d3b = copy.deepcopy(dash)                       # the rollback (3 again, the same day): made again at once, and
    be3.run(d3b, data, site, {}, TB.NOW + timedelta(hours=4))    # every file and cache byte for byte the first build's
    assert TB._l4(be3.pop_line()).endswith("refit yes, calib yes")
    assert TB._snap(site, data) == first and d3b["be"] == d3["be"]


def _row(mod, **kw):
    """tests.test_be_build.R on the given be_build module (its own row class)."""
    x = mod._R()
    for k in mod._R.__slots__:
        setattr(x, k, None)
    x.n, x.jd = 100, True
    for k, v in kw.items():
        setattr(x, k, v)
    x.sfa, x.sfv = x.obs, x.oc
    x.X = date.fromisoformat(x.day).toordinal()
    return x


def _card_day(mod, age=10):
    """One install day `age` days old, one covered country with a cell at card days 1 … 7 (ages 0 … 6; day 14 not
    lived), every lived cell final, its so-far read at age 5 → its body through mod.predict."""
    nw = date(2031, 1, 1)
    day = (nw - timedelta(days=age)).isoformat()
    cum = [30.0, 60.0, 90.0, 120.0, 150.0] + [None] * 8
    cv = [[j, [math.log(0.2), 0.0, 0.0], -0.2, 0.2, 40, math.log(0.2)] for j in range(6)]
    fits = {"AA": {"k3": [math.log(31.0), 0.0, 0.0, 0.5, 400, 30, 0, 10], "cv": cv, "rng": TB.WIDE}}
    cs = {"AA": _row(mod, day=day, sp=300.0, na=150.0, cpi=2.0, c=math.log(2.0), e=math.log(3.0), cum=cum,
                     fin=list(cum), obs=5)}
    app = _row(mod, day=day, sp=300.0, na=150.0, cum=[None] * 13, obs=5, oc=60.0)
    fc = {"origin": nw.isoformat(), "fits": fits}
    return mod.predict("k", fc, TB.CAL0, (nw.isoformat(), [app], {day: cs}, None, frozenset()))["days"][0]


def test_breakeven_final_cells_the_so_far_flag_maturity_and_pack_gaps_at_clag_7(final_days):
    gcu3, gco3, gce3, gv3, be3, bec3 = final_days.pin(gcu, gco, gce, gv, be, bec)
    d3 = _card_day(be3)                 # 10 days old: a cell is final 4 days on (CLAG), the so-far read 3 (LAG)
    assert d3["card"]["fin"] == [1, 1, 1, 1, 1, 0] and d3["now"][-1] == 1
    assert be3._mature(36, None, 40, 30) == "gt"
    nw = date(2031, 1, 1).toordinal()
    assert be3.pack_gaps({nw - 5: 10.0, nw - 8: 10.0}, {}, nw) == {nw - 5, nw - 8}
    gcu7, gco7, be7 = final_days(7, gcu, gco, be)
    d7 = _card_day(be7)                 # at 7: day 7's cell (age 6) is 4 days old — not final; the so-far read not
    assert d7["card"]["fin"] == [1, 1, 1, 1, 0, 0] and d7["now"][-1] == 0
    assert d7["card"]["roas"] == d3["card"]["roas"]                  # the values as they were: only "final" moves
    assert be7._mature(36, None, 40, 30) is None and be7._mature(37, None, 40, 30) == "gt"
    assert be7.pack_gaps({nw - 5: 10.0, nw - 8: 10.0}, {}, nw) == {nw - 8}


def test_breakeven_ecpm_day_1_stays_not_final_until_the_first_session_stores_lag(final_days):
    def p0(mod, age):
        X = "2030-01-10"
        nw = (date(2030, 1, 10) + timedelta(days=age)).isoformat()
        body = {"days": [{"d": X, "age": age}]}
        fc = {"ec": {"BB": [[0, 0.0, 30, 0.0]]}, "ec_v": mod.stamp()}
        mod.attach(body, (nw, [], {X: {"BB": TE._Row(10.0)}}), fc, TE._m({}, {("BB", X): (5.0, 5000.0)}, {}))
        return body["days"][0]["ec"]["p"][0]
    gcu3, gco3, gce3, gv3, be3, bec3 = final_days.pin(gcu, gco, gce, gv, be, bec)
    assert [p0(bec3, a) for a in (3, 4, 5)] == ["1", "1", "0"]      # at 3, the rollback: its window (5), as before
    gv7, gco7, be7, bec7 = final_days(7, gv, gco, be, bec)
    assert [p0(bec7, a) for a in (4, 6, 7)] == ["1", "1", "0"]      # at 7: final once 7 days old
