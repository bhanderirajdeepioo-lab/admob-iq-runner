"""GA4_FINAL_DAYS — the page side (owner, 17 Nov 2026: "data jese jese aata jaye ese ese bharte jao · max to max 7 din me to
aa hi jaata he", and his "ha" to marking the days younger than the final age not final — Revenue by source too).

tests/final_days_frontend.js renders the page's sections for real (node vms, stub page helpers) on SYNTHETIC files whose
edges are the ones the builds write at GA4_FINAL_DAYS = F — each producing module re-run at F by the final_days fixture
(tests/conftest.py); no F's edge is written here, only the old fixed ones a file had before the knob. First open
(firstopen_build.FIN_LAG → "final_till", "td"), eCPM first session (ga4_nvr's FINAL_LAG and the two stores' window
nvr_build._rw() → "final_till", "td", "rw"), Screens (screens_build.FT_LAG → "ft"; its periods: pwin), Breakeven
(be_build.PROV / LAG → the pointer's "pv" / "lag"), Revenue by source (ga4_source / ga4_source_cty FINAL_LAG →
"final_till"). Checked at F = 7 (the build's default) and 14 (the clamp's top): every not-final word counts the file's
own days, the 7 / 30 / 60 / 90 days end where they ended before the knob, the checks that judge final days only move
with the edge; at 3 (the rollback) every build writes its file as before the knob, so every section renders exactly as
before it; and a file written before the knob (no new field) renders exactly as one that states the old edges. Skipped
where node is not installed."""
import json
import os
import shutil
import subprocess
from datetime import date, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "frontend", "index.html")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
TD, D0 = date(2026, 3, 30), date(2026, 1, 1)          # tests/final_days_frontend.js: the property's today, the first day
FS = (7, 14)                                           # the default, the clamp's top (3, the rollback: its own test)
MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
_EDGES, _OUT = {}, {}


def _run(edges):
    k = json.dumps(edges, sort_keys=True)
    if k not in _OUT:
        r = subprocess.run([NODE, os.path.join(ROOT, "tests", "final_days_frontend.js"), PAGE, k], check=True,
                           capture_output=True, text=True, timeout=120)
        rep = json.loads(r.stdout)
        assert not rep["errors"], rep["errors"]
        _OUT[k] = rep["out"]
    return _OUT[k]


def _edges(final_days, f):
    """The edges the builds write at GA4_FINAL_DAYS = f (each module's copy re-run at f: its own lag; None = a field the
    build does not write there — at the rollback, the file as before the knob) and the Screens build's period list
    there; kept per f as plain data (the copies end with the test)."""
    if f not in _EDGES:
        from admob_iq import be_build, firstopen_build, nvr_build, screens_build, source_build
        from admob_iq.fetch import ga4_cohort, ga4_firstopen, ga4_nvr, ga4_nvr_uc, ga4_source, ga4_source_cty
        _, fb = final_days(f, ga4_firstopen, firstopen_build)
        _, _, nb = final_days(f, ga4_nvr, ga4_nvr_uc, nvr_build)
        sb = final_days(f, screens_build)
        _, bb = final_days(f, ga4_cohort, be_build)
        gs, gsc, srb = final_days(f, ga4_source, ga4_source_cty, source_build)
        e = {"fo": fb.FIN_LAG if fb.EDGES else None, "nvr": nb.FIN_LAG if nb.EDGES else None,
             "rw": nb._rw() if nb.EDGES else None, "scr": sb.FT_LAG, "pv": bb.PROV, "lag": bb.LAG,
             "src": gs.FINAL_LAG if srb.FINAL_TILL else None, "srcc": gsc.FINAL_LAG if srb.FINAL_TILL else None}
        roll = sorted((lo, hi) for _, lo, hi, kd in sb.pwin(TD.isoformat(), D0.isoformat()) if kd == "roll")
        _EDGES[f] = (e, roll)
    return _EDGES[f]


def ago(n):
    return TD - timedelta(days=n)


def dm(d):                                             # fmtDY (the reference year pinned to 2026)
    return "%d %s" % (d.day, MON[d.month - 1])


def dy(d):                                             # "24 Mar 2026"
    return "%s %d" % (dm(d), d.year)


def d2(d):                                             # Revenue by source's "24 Mar 26"
    return "%s %s" % (dm(d), str(d.year)[2:])


def per(o, k):
    return tuple(date.fromisoformat(x) for x in o["per"][k])


@pytest.mark.parametrize("f", FS)
def test_first_open_today_and_not_final_from_the_file(final_days, f):
    e, _ = _edges(final_days, f)
    o, old, n = _run(e)["fo"], _run({})["fo"], e["fo"]
    ft = ago(n)
    assert n >= 3 and o["all_note"].startswith("Final till %s (aakhri %d din GA4 me abhi badalte hain)." % (dm(ft), n))
    assert o["mini_note"] == o["cc_note"] == (
        "Pichhle %d din abhi final nahi (Last 7 days aur usual: %s tak ke final din)." % (n, dm(ft)))
    assert o["legend"] == o["cc_legend"] == "not final (last %d days)" % n
    # the 7 / 30 / 90 days end where they did before the knob (today − 2): "bharte jao" — and Today / Yesterday are td's
    assert o["per"] == old["per"] and per(o, "today") == (TD, TD) and per(o, "yday") == (ago(1), ago(1))
    lo, hi = per(o, "7")
    s0 = max(lo, ft + timedelta(days=1))
    nf = "final hone ke baad (%d din)" % n if lo > ft else "sirf %s tak ke dino ka" % dy(ft)
    assert o["board7"] == "⏳ %s%s abhi final nahi (GA4 aur Google Ads dono baad me bhi jodte hain): Not opened %s." % (
        dy(s0), " – " + dy(hi) if hi > s0 else "", nf)
    assert o["board_today"].endswith("Not opened final hone ke baad (%d din)." % n)
    assert o["nf_days"] == [dy(ago(k)) for k in range(n)]                   # every day after final till, newest first
    assert o["cc_today"] == old["cc_today"]                                 # the country view's Today / Yesterday: td's
    # before the knob: the old words
    assert old["mini_note"] == old["cc_note"] == "Today aur Yesterday abhi final nahi."
    assert old["legend"] == "not final (last 2 days)" and "(aakhri 2 din GA4 me abhi badalte hain)" in old["all_note"]
    assert old["board7"] == "" and old["board_today"].endswith("Not opened final hone ke baad (2 din).")


@pytest.mark.parametrize("f", FS)
def test_ecpm_first_session_periods_not_final_and_measured_days(final_days, f):
    e, _ = _edges(final_days, f)
    o, old, n = _run(e)["nvr"], _run({})["nvr"], e["nvr"]
    assert o["per"] == old["per"]                                           # the periods end where they did
    ft = ago(n)

    def line(lo, hi):                                                       # the period's OWN days after final till
        s0 = max(lo, ft + timedelta(days=1))
        return "%s%s abhi final nahi (GA4 me abhi badal rahe hain)." % (dy(s0), " – " + dy(hi) if hi > s0 else "")
    assert o["note"] == {"7": line(*per(o, "7")), "30": line(*per(o, "30")), "today": line(TD, TD)}
    if n == 7:                                                              # 7 days: its 5 newest not final, never "7 din"
        assert o["note"]["7"] == "24 Mar 2026 – 28 Mar 2026 abhi final nahi (GA4 me abhi badal rahe hain)."
    assert old["note"] == {"7": "", "30": "", "today": "aakhri 2 din GA4 me abhi badal rahe hain (final nahi)."}
    # a picked country's ad units are measured on the days neither store reads again: older than today − rw
    lo, _ = per(o, "30")
    assert o["meas30"] == (ago(e["rw"]) - lo).days + 1 and old["meas30"] == (ago(5) - lo).days + 1


@pytest.mark.parametrize("f", FS)
def test_screens_periods_are_the_builds_and_not_final_from_ft(final_days, f):
    e, roll = _edges(final_days, f)
    o, old, n = _run(e)["scr"], _run({})["scr"], e["scr"]
    ft = ago(n)
    assert o["per"] == old["per"]
    # the page's 7 / 30 / 60 / 90 days are exactly the build's roll periods (their users and signals are read for those):
    # the page's key starts at the app's first day, as pwin's (pk)
    keys = sorted((max(lo, D0.isoformat()), hi) for lo, hi in (o["per"][k] for k in ("7", "30", "60", "90")))
    assert keys == [tuple(x) for x in roll]
    assert all(o["line"][k].endswith(" · not final") for k in ("7", "30", "yday"))
    assert not old["line"]["7"].endswith("not final") and old["line"]["yday"].endswith(" · not final")
    assert o["how"] == "GA4 data till %s ; pichhle %d din abhi final nahi." % (dy(ft), n)
    assert o["all_note"] == "GA4 data till %s (aakhri %d din GA4 me abhi badalte hain)." % (dy(ft), n)
    assert old["how"] == "GA4 data till %s ; Today / Yesterday abhi final nahi." % dy(ago(2))
    # the day after ft (before Yesterday): not final, never "users ~2 din baad" / "AdMob 1–2 din baad"; Yesterday as before
    assert o["why"] == {"nf1": "abhi final nahi", "yday": "users abhi nahi (~2 din baad)"}
    assert o["adm"] == {"nf1": "is period ke GA4 din abhi final nahi — Fill / Show rate sirf final din pe",
                        "yday": "AdMob ~1–2 din baad pura hota hai"}
    assert old["why"] == {"nf1": "users abhi nahi (~2 din baad)", "yday": "users abhi nahi (~2 din baad)"}
    # the 7 days' signals: on as many FINAL days ending ft, the build's own window (screens_build.sig_win) — never on the
    # 2 (at 7) or 0 (at 14) final days of the period itself (🔻 needs 7 on each side); This month on its own days
    from admob_iq import screens_build as sb
    lo7, hi7 = per(o, "7")
    sw = (ft - (hi7 - lo7), ft)
    assert o["sig7"] == {"sw": [d.isoformat() for d in sw], "fin": 7, "tm": [d.isoformat() for d in per(o, "tm")],
                         "note": "Signals pichhle 7 final din (%s – %s) pe judge hue — is period ke naye din abhi final "
                                 "nahi." % (dm(sw[0]), dm(sw[1]))}
    assert sb.sig_win(lo7.isoformat(), hi7.isoformat(), ft.isoformat(), D0.isoformat()) == tuple(o["sig7"]["sw"])
    assert old["sig7"] == {"sw": None, "fin": 7, "note": "", "tm": [d.isoformat() for d in per(old, "tm")]}
    # the App total's Fill / Show rate is AdMob's alone: its complete days to td − 2 at any F, as before the knob
    assert o["pool"] == old["pool"] == {"7": [7, ""], "30": [30, ""], "yday": [0, "AdMob ~1–2 din baad pura hota hai"]}
    # the App's "Ads / 100 views · vs own past": scored on the period's final days only — a quarter of the ads so far on
    # every day after ft never moves it (none to judge: no score)

    def fin(k):
        lo, hi = per(o, k)
        return max(0, (min(hi, ft) - lo).days + 1)
    assert o["score"] == {k: [100 if fin(k) else None, fin(k) < 7] for k in ("7", "30", "tm", "today")}
    assert old["score"] == {"7": [100, False], "30": [100, False], "tm": [100, False], "today": [None, True]}


PV0, LAG0 = 4, 3                                      # the page's fallbacks: be_build's PROV / LAG before the knob


@pytest.mark.parametrize("f", FS)
def test_breakeven_not_final_age_and_lag_from_the_pointer(final_days, f):
    e, _ = _edges(final_days, f)
    o, old = _run(e)["be"], _run({})["be"]
    pv, lag = e["pv"], e["lag"]
    if (pv, lag) == (PV0, LAG0):                                            # the rollback: the tab as before the knob
        assert o == old
    words = "2–3" if lag == LAG0 else str(lag)                              # (the old words at the old lag)
    assert o["young"]["wat"] == ["abhi final nahi — %d din se kam purana (GA4 country / first-session data aur Google Ads "
                                 "installs abhi badal sakte hain)" % pv] and o["old"]["wat"] == []
    assert o["at_lag"] == ['30 din ka data abhi final nahi (%s din me asli) — ab tak ka ROAS &quot;So far&quot; me' % words]
    assert o["past_lag"] == ["30 din ka data GA4 se poora nahi aaya — yahan asli number nahi (ab tak ka ROAS "
                             "&quot;So far&quot; me)"]
    assert o["det"] == "ye install din %d din se kam purana hai" % pv
    assert o["so_far"] == "aaj tak ka hisaab (pichhle %s din ka abhi badal sakta hai)" % words
    assert o["foot"] == "⏳ = abhi final nahi (%d din se kam purana)" % pv
    assert old["det"] == "ye install din %d din se kam purana hai" % PV0 and "(2–3 din me asli)" in old["at_lag"][0]


@pytest.mark.parametrize("f", FS)
def test_revenue_by_source_marks_days_after_final_till(final_days, f):
    e, _ = _edges(final_days, f)
    o, old, n = _run(e)["src"], _run({})["src"], e["src"]
    ft = ago(n)
    for k, (lo, hi) in {"7": (ago(7), ago(1)), "30": (ago(30), ago(1)), "today": (TD, TD)}.items():
        s0 = max(lo, ft + timedelta(days=1))
        assert o["app"][k] == (d2(s0) + (" – " + d2(hi) if hi > s0 else "")), k
    assert o["app"]["lm"] == "" and o["all"]["7"] == o["app"]["7"]          # last month: every day final
    assert o["nf_rows"][:2] == ["Today so far", "Yesterday"] and len(o["nf_rows"]) == n
    assert o["nf_month"] == [["Mar 2026", n]]
    # GA4 vs AdMob on 3 Apr: March judged only once its last day is final
    fa = date(2026, 4, 3) - timedelta(days=n)
    assert o["adm"] == (["2026-01", "2026-03", 3] if fa >= date(2026, 3, 31) else ["2026-01", "2026-02", 2])
    # 🌍 Source: its own file's edge
    s0 = max(ago(30), ago(e["srcc"]) + timedelta(days=1))
    assert o["x"] == "%s – %s" % (d2(s0), d2(ago(1)))
    # before the knob's files: no mark anywhere, the check as before
    assert old["app"] == old["all"] == {"7": "", "30": "", "today": "", "lm": ""}
    assert old["nf_rows"] == old["nf_month"] == []
    assert old["adm"] == ["2026-01", "2026-03", 3] and old["x"] == ""


def test_the_rollback_renders_every_section_exactly_as_before_the_knob(final_days):
    """GA4_FINAL_DAYS 3: every build writes its page file as before the knob (each page's old edge, no new field), so
    every section — html included — renders as the files before the knob did."""
    e, _ = _edges(final_days, 3)
    assert e == {"fo": None, "nvr": None, "rw": None, "scr": 2, "pv": PV0, "lag": LAG0, "src": None, "srcc": None}
    assert _run(e) == _run({})


def test_a_file_before_the_knob_renders_as_one_stating_the_old_edges():
    """No "td" / "rw" / "pv" / "lag" (a file built before the knob, or the fixtures of the other page tests): the page's
    fallbacks are the old fixed edges — the same output, html included, as files that state them (final till = today −
    2, rw 5, pv 4, lag 3)."""
    assert _run({}) == _run({"fo": 2, "nvr": 2, "rw": 5, "pv": 4, "lag": 3})


def test_the_pages_edges_are_the_files_never_a_number_of_its_own():
    """Every edge the page uses for GA4 finality comes from its file, falling back to the number before the knob; the
    old inferences ("today = final till + 2", the fixed 2 / 3 / 4 days in the words) are gone."""
    s = open(PAGE, encoding="utf-8").read()
    for frag in ("const foToday=a=>isD(a.td)?a.td:addD(a.final_till,2);",
                 "const foNfN=a=>dd(a.final_till,foToday(a));",
                 "const scNf=x=>okD(x.ft)?nD(x.ft,tdOf(x))-1:2;",
                 "const tdOf=d=>isD(d.td)?d.td:addD(d.final_till,2);",
                 "lastFinal=at(addD(tdOf(d),-(+d.rw>0?Math.round(+d.rw):5)))",
                 "const bePv=()=>beLim('pv',4), beLag=()=>beLim('lag',3);",
                 "const ftOf=a=>a&&isD(a.final_till)?a.final_till:null;"):
        assert s.count(frag) == 1, frag
    for gone in ("const T=addD(a.final_till,2);", "p=adsPtr(a), [lo,hi]=perRange(a,ad), T=addD(a.final_till,2);",
                 "const t=by[at(2)], y=by[at(1)]", "const ft=d.final_till, T=addD(ft,2)", "T=addD(d.final_till,2);",
                 "lastFinal=at(addD(d.final_till,-3))", "pv=ag!=null&&ag<4", "ag-H>3?", "if(n) return [addD(ft,-(n-1)),ft];",
                 "aakhri 2 din GA4", "4 din se kam purana", "(2–3 din me asli)", "GA4 ka data 2–3 din me final",
                 "(pichhle 2–3 din ka abhi badal sakta hai)", "not final (last 2 days)", "final hone ke baad (2 din)",
                 "(GA4 ~2 din baad final hota hai)"):
        assert gone not in s, gone
