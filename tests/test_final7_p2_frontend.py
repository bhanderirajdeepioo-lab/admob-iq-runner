"""GA4_FINAL_DAYS, step 2 — the page's words about when an Active users / Audience / Install value number is final
(👥 Active users: "When will I know?", the ⏳ Not final tip, the All apps line; 👥 Audience: the phone card's day line;
💰 Install value: "When will I know?", the At a glance card's wait line) read the files' own lags: the Active file's
consts.act_late_days (engine.active / impact: ga4_final.lag(5) − 2) and the Install value file's consts.iday_late
(value_build.consts: fetch.ga4_uninstall.IDAY_LATE, written off the rollback only). tests/final7_p2_frontend.js renders
them for real (the page's script in a node vm) on a SYNTHETIC pointer whose lags are the builds' own at GA4_FINAL_DAYS = F
(each producing module re-run at F by the final_days fixture, tests/conftest.py). At 3 (the rollback) and with no lag in
the file (a build before the knob) every text is exactly the text before it; at 7 every number follows. Skipped where
node is not installed."""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "frontend", "index.html")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
VCFG = {"payback_days": 90, "iap": False, "cpi": "ads", "deduct": False, "geo": False}
_OUT = {}

# the texts exactly as the page showed them before GA4_FINAL_DAYS (act_late_days 3, the install-day reads at age 5)
OLD = {
    "tip": "GA4 ~3 din tak late data jodta hai — ye number abhi badh sakta hai.",
    "act_timing": "▸ ⏱️ When will I know? Hide GA4 din ~2 din baad aata hai, activity 3 din me pakki (Uninstall 7 din me)."
                  " Old users ka badlaav ~6 din baad dikhta, alert ~9 din baad (2 baar pakka hone par). Back next day ~6"
                  " din, back after 7 days ~12 din, 30 din baad wapas ~35 din baad. Kamai har user ~6 din baad (AdMob ka ≈"
                  " andaza). Update impact: release + 7 din + 3 pakke din.",
    "val_timing": "▸ ⏱️ When will I know? Hide Pehle din ki kamai ~5 din baad pakki, 1 hafte wali ~12 din baad, 30 din wali"
                  " ~35 din baad. Paisa-wapas ka andaza hafte ke installs ke 7 din pure hone ke ~5 din baad. Country ka"
                  " faisla 4 hafte ke installs pe (chhote apps: 12 hafte). Alert tabhi jab 2 hafte lagatar ho.",
    "au_phone": "Aaj = 25 Mar 2026 (aakhri poora din — GA4 activity 3 din me final hoti hai)",
    "act_head": "Old users = roz ke active users − us din ke naye installs. GA4 ka data ~3 din me pakka hota hai — naye din"
                " ⏳ not final (kam dikhte, unpe faisla nahi).",
    "val_sum": "andaza hafte ke installs ke 7 din pure hone ke ~5 din baad",
}


def _script():
    with open(PAGE, encoding="utf-8") as f:
        return max(re.findall(r"<script>(.*?)</script>", f.read(), re.S), key=len)


def _run(tmp_path_factory, lags):
    k = json.dumps(lags, sort_keys=True)
    if k not in _OUT:
        js = tmp_path_factory.mktemp("p2page") / "index.js"
        js.write_text(_script(), encoding="utf-8")
        r = subprocess.run([NODE, os.path.join(ROOT, "tests", "final7_p2_frontend.js"), str(js), k], check=True,
                           capture_output=True, text=True, timeout=120)
        rep = json.loads(r.stdout)
        assert not rep["errors"], rep["errors"]
        _OUT[k] = rep
    return _OUT[k]


def _lags(final_days, f):
    """The lags the builds write at GA4_FINAL_DAYS = f: the Active file's act_late_days (engine.active.CONSTS) and the
    Install value file's iday_late (value_build.consts; None = not written — the rollback)."""
    from admob_iq import value_build
    from admob_iq.engine import active, impact
    from admob_iq.fetch import ga4_uninstall
    if f == 3:
        gu, imp, act, vb = final_days.pin(ga4_uninstall, impact, active, value_build)
    else:
        gu, imp, act, vb = final_days(f, ga4_uninstall, impact, active, value_build)
    return {"act": act.CONSTS["act_late_days"], "val": vb.consts(VCFG).get("iday_late")}


def test_at_the_rollback_and_with_no_lag_in_the_file_every_text_is_as_before(final_days, tmp_path_factory):
    lags = _lags(final_days, 3)
    assert lags == {"act": 3, "val": None}                    # (the rollback: value_build writes no iday_late)
    for given in (lags, {}, {"act": 3, "val": 3}):           # the build at 3 · a file before the knob · both stated
        rep = _run(tmp_path_factory, given)
        for k, v in OLD.items():
            assert rep[k] == v, (given, k)
        assert rep["pill"] == '<span class="pill p-b" title="%s">⏳ Not final</span>' % OLD["tip"]
    assert rep["src"] == {"old": [], "derived": [], "twice": []}   # no fixed number left; every derived text in the
    #                                                                 page; each helper defined once


def test_at_7_every_number_follows_the_files_lags(final_days, tmp_path_factory):
    lags = _lags(final_days, 7)
    assert lags == {"act": 5, "val": 5}
    rep = _run(tmp_path_factory, lags)
    assert rep["helpers"] == {"late": 5, "at1": 8, "at30": 37, "vlate": 5, "v0": 7, "v365": 372}
    assert rep["tip"] == "GA4 ~5 din tak late data jodta hai — ye number abhi badh sakta hai."
    assert rep["act_timing"] == (
        "▸ ⏱️ When will I know? Hide GA4 din ~2 din baad aata hai, activity 5 din me pakki (Uninstall 7 din me). Old users"
        " ka badlaav ~8 din baad dikhta, alert ~11 din baad (2 baar pakka hone par). Back next day ~8 din, back after 7"
        " days ~14 din, 30 din baad wapas ~37 din baad. Kamai har user ~8 din baad (AdMob ka ≈ andaza). Update impact:"
        " release + 7 din + 5 pakke din.")
    assert rep["val_timing"].startswith(
        "▸ ⏱️ When will I know? Hide Pehle din ki kamai ~7 din baad pakki, 1 hafte wali ~14 din baad, 30 din wali ~37 din"
        " baad. Paisa-wapas ka andaza hafte ke installs ke 7 din pure hone ke ~7 din baad.")
    assert rep["au_phone"] == "Aaj = 25 Mar 2026 (aakhri poora din — GA4 activity 5 din me final hoti hai)"
    assert "GA4 ka data ~5 din me pakka hota hai" in rep["act_head"]
    assert rep["val_sum"] == "andaza hafte ke installs ke 7 din pure hone ke ~7 din baad"
    # each file speaks for itself: an Active file at 7 beside an Install value file from before the knob
    mix = _run(tmp_path_factory, {"act": 5})
    assert mix["au_phone"] == "Aaj = 25 Mar 2026 (aakhri poora din — GA4 activity 5 din me final hoti hai)"
    assert mix["val_sum"] == OLD["val_sum"] and mix["val_timing"] == OLD["val_timing"]
