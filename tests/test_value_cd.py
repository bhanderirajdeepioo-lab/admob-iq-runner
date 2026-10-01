"""C (new users by the app version of their install day) and D (long-term by install month) of the Install value tab
(admob_iq.engine.value_cd, SPEC_CD_GEO Parts C and D; "CD:" in §C.10 / §D.8): off unless cfg["cd"], versions from the
store's vuse only SPLIT install days (installs and returners come from x), a cell is complete or "in N days" — never a
small number from part of its days —, small samples are never judged, ver_ret / long_ret keep the value tab's
no-flood rules, a failure costs only its own part, and every text is Roman Hinglish. All data is synthetic
(tests.value_synth)."""

import copy
import json
import os
import re
from datetime import date, timedelta

import pytest

from admob_iq.engine import value as V
from admob_iq.engine import value_cd as VC
from tests import value_synth as vs

END = vs.END
S = END - timedelta(days=vs.LATE)
E = V._eval_end(S)
START = END - timedelta(days=60 * 7 - 1)
AID = "ca-app-pub-0000000000000000~0000000009"
NOW = "2026-09-21T12:00:00Z"
OLD = "2026-01-04"
VERS = (("1.0", START, 0), ("1.1", date(2026, 7, 20), 0), ("1.2", date(2026, 8, 10), 0))


def ev(m, st=None, cd=True, releases=(), **kw):
    cfg = {"payback_days": 90}
    if cd:
        cfg["cd"] = True
    return V.evaluate_app(m["store"], m["ida"], m["rev"], m["spend"], m["fx"], list(releases), st, {}, cfg, NOW,
                          app_id=AID, app="Demo App", key="k", **kw)


def app(**kw):
    kw.setdefault("start", START)
    kw.setdefault("seed", 3)
    return vs.make_app(**kw)


def again(st, inputs=OLD, episodes=False):
    """The state as if the weekly evaluation before this one had run (and every input seen long ago)."""
    st = copy.deepcopy(st)
    st["eval"]["end_week"] = (E - timedelta(days=7)).isoformat()
    if inputs:
        st["eval"]["inputs"] = {k: inputs for k in st["eval"]["inputs"]}
    if not episodes:
        st["episodes"] = {}
    return st


def rows(det):
    return {r["ver"]: r for r in det["by_version"]["rows"]}


def alerts(row, fam):
    return [a for a in row["_alerts"] if a["family"] == fam]


def days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def xn(m, ds):
    x = m["ida"]["x"]
    return sum((x.get(d.isoformat()) or {}).get("n", 0) for d in ds)


def xu(m, ds, slot):
    x = m["ida"]["x"]
    return sum(((x.get(d.isoformat()) or {}).get("u") or [0] * 13)[slot] for d in ds)


# ── C: off by default, the dominant version, the base ───────────────────────────────────────────

def test_ver_off_by_default_detail_unchanged():
    det0, row0, st0 = ev(app(), cd=False)
    det1, row1, st1 = ev(app(versions=VERS), cd=False)                 # vuse in the store, VALUE_CD off
    assert det1["by_version"] == [] and det1["long"] == []
    assert "ver" not in st1["eval"]["inputs"] and "long" not in st1["eval"]["inputs"]
    assert json.dumps(det1, sort_keys=True) == json.dumps(det0, sort_keys=True) and st1 == st0
    assert {k: v for k, v in row1.items() if k != "_alerts"} == {k: v for k, v in row0.items() if k != "_alerts"}


def test_ver_dominant_80pct_rollout_days_left_out_counted():
    d0 = date(2026, 6, 1)
    m = app(versions=(("1.0", START, 0), ("1.1", d0, (0.4, 0.4, 0.4, 0.85))))
    det, _, _ = ev(m)
    bv = det["by_version"]
    assert bv["left_out"] == {"days": 3, "n": xn(m, days(d0, d0 + timedelta(days=2)))}
    r = rows(det)
    assert r["1.1"]["from"] == (d0 + timedelta(days=3)).isoformat()      # 85% of the new users: dominant
    assert r["1.0"]["to"] == (d0 - timedelta(days=1)).isoformat()
    assert bv["no_vuse"] == {"days": 0, "n": 0}


def test_ver_base_is_x_not_vuse():
    m = app(versions=VERS)
    det, _, _ = ev(m)
    r = rows(det)["1.1"]
    ds = days(date(2026, 7, 20), date(2026, 8, 9))
    assert r["n"] == xn(m, ds) and r["days"] == len(ds)
    assert r["d1"]["v"] == pytest.approx(100 * xu(m, ds, 1) / xn(m, ds), abs=0.01)
    for d in m["store"]["vuse"].values():                               # 10× the version's users: only the split
        for v, a in d.items():
            d[v] = [x * 10 for x in a]
    det2, _, _ = ev(m)
    assert rows(det2)["1.1"]["n"] == r["n"] and rows(det2)["1.1"]["d1"] == r["d1"]


def test_ver_nosplit_nodata_low_single_states():
    det, _, _ = ev(app(versions=VERS, vsplit=False))
    assert det["by_version"]["state"] == "nosplit" and det["by_version"]["rows"] == []
    assert "version-wise data nahi" in det["by_version"]["text"]
    m = app(versions=VERS)
    del m["store"]["vuse"]
    det, _, _ = ev(m)
    assert det["by_version"]["state"] == "nodata" and det["by_version"]["text"] == "⏳ Version-wise data aa raha."
    many = tuple(("%d.0" % (i + 1), START + timedelta(days=30 * i), 0) for i in range(14))
    det, _, _ = ev(app(versions=many, base=2))
    assert det["by_version"]["state"] == "low" and det["by_version"]["short"]["versions"] == 14
    det, _, _ = ev(app(versions=(("4.0", START, 0),)))
    bv = det["by_version"]
    assert bv["state"] == "single" and len(bv["rows"]) == 1 and bv["rows"][0]["vs"] is None
    assert bv["text"] == "Abhi ek hi version (v4.0) — tulna ke liye agla update chahiye."


def test_ver_cells_complete_part_wait_never_small_number():
    d0 = S - timedelta(days=4)
    m = app(versions=(("1.0", START, 0), ("1.1", d0, 0)))
    r = rows(ev(m)[0])["1.1"]
    assert r["d1"]["st"] == "part" and (r["d1"]["days"], r["d1"]["of"], r["d1"]["in"]) == (4, 5, 1)
    ds = days(d0, S - timedelta(days=1))                                # only the complete days are in the value
    assert r["d1"]["v"] == pytest.approx(100 * xu(m, ds, 1) / xn(m, ds), abs=0.01) and r["d1"]["n"] == xn(m, ds)
    for k in ("d7", "d30"):
        assert r[k]["st"] == "wait" and r[k]["v"] is None and r[k]["n"] == 0
    assert r["d7"]["in"] == 3 and r["d30"]["in"] == 26
    assert r["rpi"]["30"]["st"] == "wait" and r["rpi"]["30"]["v"] is None
    assert "back after 7 days ka number 3 din me" in r["text"]


def test_ver_version_that_comes_back_is_one_group_with_gaps():
    a, b = date(2026, 5, 4), date(2026, 5, 17)
    m = app(versions=(("1.0", START, 0), ("1.1", a, 0, b)))
    r = rows(ev(m)[0])
    assert r["1.0"]["gaps"] and r["1.0"]["from"] == START.isoformat() and r["1.0"]["to"] == S.isoformat()
    assert r["1.0"]["days"] == (S - START).days + 1 - 14 and not r["1.1"]["gaps"] and r["1.0"]["current"]


def test_ver_vs_previous_first28_vs_last28_same_age():
    m = app(versions=VERS)
    vs1 = rows(ev(m)[0])["1.2"]["vs"]
    d1 = vs1["d1"]
    one = days(date(2026, 8, 10), date(2026, 8, 10) + timedelta(days=27))       # the first 28 complete days
    zero = days(date(2026, 7, 20), date(2026, 8, 9))                            # 1.1 had 21: all of them
    assert (d1["from1"], d1["to1"], d1["days1"]) == (one[0].isoformat(), one[-1].isoformat(), 28)
    assert (d1["from0"], d1["to0"], d1["days0"]) == (zero[0].isoformat(), zero[-1].isoformat(), 21)
    assert d1["v1"] == pytest.approx(100 * xu(m, one, 1) / xn(m, one), abs=0.01)
    assert d1["v0"] == pytest.approx(100 * xu(m, zero, 1) / xn(m, zero), abs=0.01) and d1["st"] == "same"
    d7 = vs1["d7"]                                   # same age: at 7 days the new side ends 7 days before S
    assert d7["to1"] == (date(2026, 8, 10) + timedelta(days=27)).isoformat() and d7["days1"] == 28


def test_ver_hotfix_skipped_as_previous_and_named():
    m = app(versions=(("1.0", START, 0), ("1.1", date(2026, 6, 1), 0), ("1.1.1", date(2026, 7, 6), 0, date(2026, 7, 6)),
                      ("1.2", date(2026, 7, 7), 0)))
    r = rows(ev(m)[0])
    assert r["1.2"]["vs"]["ver"] == "1.1" and r["1.2"]["vs"]["skipped"] == ["1.1.1"]
    assert r["1.1.1"]["days"] == 1 and r["1.1.1"]["verdict"] == "short"        # a finished 1-day hotfix: never "wait"
    assert r["1.1.1"]["n"] >= VC.VER_JUDGE_N and r["1.1.1"]["vs"]["d1"]["st"] == "short"   # … nor "few installs"
    assert r["1.1.1"]["text"].startswith("v1.1.1: ") and "sirf 1 din naye users isi version pe aaye" in r["1.1.1"]["text"]


def test_ver_older_versions_are_sent_for_the_fold():
    """More than VER_ROWS versions: every row goes to the page (newest first) — it shows the newest VER_ROWS and folds
    the `older` rest, so "Older versions (k)" and a 📦 / 🧬 link to an older version have a row to open."""
    first = date(2026, 3, 2)
    vers = (("1.0", START, 0),) + tuple(("1.%d" % i, first + timedelta(days=14 * i), 0) for i in range(1, 12))
    det, _, _ = ev(app(versions=vers))
    bv = det["by_version"]
    got = [r["ver"] for r in bv["rows"]]
    assert got == ["1.%d" % i for i in range(11, 0, -1)] + ["1.0"]
    assert bv["older"] == len(got) - VC.VER_ROWS == 4
    assert bv["text"].startswith("v1.11 ")                                    # the summary: the newest shown rows


def test_ver_phi_within_version_days_capped_30():
    m = app(versions=VERS)
    det, _, _ = ev(m)
    assert det["by_version"]["phi"]["1"] == pytest.approx(1.0)             # the made-up days vary only binomially
    for i, (k, x) in enumerate(sorted(m["ida"]["x"].items())):             # every other day's D1 ×1.5 / ×0.5
        x["u"][1] = int(x["u"][1] * (1.5 if i % 2 else 0.5))
    det, _, _ = ev(m)
    assert det["by_version"]["phi"]["1"] == VC.VER_PHI_CAP


def test_ver_small_samples_few_no_verdict_no_alert():
    d0 = S - timedelta(days=40)
    m = app(base=12, versions=(("1.0", START, 0), ("1.1", d0, 0), ("1.2", d0 + timedelta(days=20), 0)),
            ver_drop=("1.2", 0.5))
    det, _, st = ev(m)
    r = rows(det)
    assert 100 <= r["1.1"]["n"] < VC.VER_JUDGE_N and r["1.1"]["verdict"] == "few" and r["1.1"]["vs"] is None
    assert r["1.1"]["text"].startswith("v1.1: sirf ") and "(300 chahiye)" in r["1.1"]["text"]
    _, row, _ = ev(m, st=again(st))
    assert not alerts(row, "ver_ret")
    det, _, _ = ev(app(base=12, versions=(("1.0", START, 0), ("1.1", d0, 0, d0 + timedelta(days=4)))))
    short = det["by_version"]["short"]                                  # 5 days of ~12 installs: no row of its own
    assert short["versions"] == 1 and 0 < short["n"] < VC.VER_SHOW_N and "1.1" not in rows(det)


# ── C: the ver_ret alert ────────────────────────────────────────────────────────────────────────

def test_ver_ret_needs_1000_installs_3_days_two_evaluations():
    m = app(versions=VERS, ver_drop=("1.2", 0.8))
    det, row, st = ev(m)
    assert rows(det)["1.2"]["verdict"] == "worse" and not alerts(row, "ver_ret")       # one evaluation: not yet
    assert st["eval"]["streak"] == {"ver_ret|1.2|d1|down": 1, "ver_ret|1.2|d7|down": 1}
    _, row, st2 = ev(m, st=again(st))
    a = alerts(row, "ver_ret")
    assert len(a) == 1 and a[0]["metric"] == "d1" and a[0]["also"] == ["d7"] and a[0]["dir"] == "down"
    assert a[0]["ver"] == "1.2" and a[0]["ver_label"] == "v1.2" and a[0]["pver_label"] == "v1.1"
    assert a[0]["unit"] == "pp" and a[0]["users"] >= VC.VER_ALERT_N and a[0]["notify"]
    assert a[0]["week_from"] == "2026-08-10" and a[0]["base_to"] == "2026-08-09"
    assert "v1.2 ke baad naye users kam ruk rahe: back next day 28%, pichhle v1.1 me 35%" in a[0]["text"]
    # the same drop on a small app (each side < 1,000 installs): shown in the table, never an alert
    small = app(base=40, versions=(VERS[0], (VERS[1][0], date(2026, 8, 24), 0), (VERS[2][0], date(2026, 9, 3), 0)),
                ver_drop=("1.2", 0.6))
    _, _, sst = ev(small)
    det, row, _ = ev(small, st=again(sst))
    s1 = rows(det)["1.2"]["vs"]["d1"]
    assert s1["st"] == "worse" and max(s1["n0"], s1["n1"]) < VC.VER_ALERT_N and not alerts(row, "ver_ret")
    assert [i["ver"] for i in det["changes"]["info"] if i["kind"] == "ver_mix"] == ["1.2"]   # said, never alerted
    two = app(versions=(VERS[0], VERS[1], ("1.2", S - timedelta(days=2), 0)), ver_drop=("1.2", 0.6))
    _, _, tst = ev(two)
    det, row, _ = ev(two, st=again(tst))                                # 2 complete days: never judged
    assert not alerts(row, "ver_ret") and rows(det)["1.2"]["vs"]["d1"]["st"] == "wait"


def test_ver_ret_seeded_first_eval_and_ver_burnin():
    m = app(versions=VERS, ver_drop=("1.2", 0.8))
    _, _, st = ev(m)
    assert st["eval"]["inputs"]["ver"] == E.isoformat()                 # ≥ 2 versions with ≥ 1,000 installs at D1
    st2 = again(st)
    st2["eval"]["inputs"]["ver"] = (E - timedelta(days=21)).isoformat()
    _, row, _ = ev(m, st=st2)
    assert not alerts(row, "ver_ret")[0]["notify"]
    st2["eval"]["inputs"]["ver"] = (E - timedelta(days=35)).isoformat()
    _, row, _ = ev(m, st=st2)
    assert alerts(row, "ver_ret")[0]["notify"]
    _, row, stf = ev(m)                                                 # the app's first evaluation: seeded
    assert all(e["seeded"] for e in stf["episodes"].values())


def test_ver_ret_linked_to_update_impact_not_sent():
    m = app(versions=VERS, ver_drop=("1.2", 0.8))
    _, _, st = ev(m)
    imp = {"1.2": {"worse": ["new_d1", "sessions"], "better": [], "key": "B7"}}
    _, row, _ = ev(m, st=again(st), impact=imp)
    a = alerts(row, "ver_ret")[0]
    assert a["linked"] and not a["notify"] and a["severity"] == "watch" and a["text"].endswith("(Update impact me bataya)")
    _, row, _ = ev(m, st=again(st), impact={"1.2": {"worse": [], "better": ["new_d1"], "key": "B7"}})
    assert not alerts(row, "ver_ret")[0]["linked"]                      # a verdict the other way: not the same news


def test_ver_ret_mix_tag_caps_watch():
    m = app(versions=VERS, ver_drop=("1.2", 0.8), organic=(date(2026, 8, 10), S, 3.0))
    _, _, st = ev(m)
    _, row, _ = ev(m, st=again(st))
    a = alerts(row, "ver_ret")[0]
    assert "mix" in a["tags"] and a["severity"] == "watch" and "shayad installs ka mix badla (ads wale" in a["text"]
    _, _, st = ev(app(versions=VERS, ver_drop=("1.2", 0.8)))
    _, row, _ = ev(app(versions=VERS, ver_drop=("1.2", 0.8)), st=again(st))
    assert alerts(row, "ver_ret")[0]["severity"] == "warning"           # unmixed, current, big, clear: red


def _rpi_drop(m, ver_first, f):
    """Earnings of the install days from ver_first on, over their first week (bands 0–7 days) × f."""
    for k, x in m["ida"]["x"].items():
        if date.fromisoformat(k) >= ver_first:
            for b in range(4):
                x["r"][b] = int(x["r"][b] * f)
    return m


def test_ver_ret_rpi7_market_held():
    m = _rpi_drop(app(versions=VERS), date(2026, 8, 10), 0.6)
    _, _, st = ev(m)
    _, row, _ = ev(m, st=again(st))
    a = alerts(row, "ver_ret")
    assert len(a) == 1 and a[0]["metric"] == "rpi7" and a[0]["unit"] == "usd" and a[0]["notify"]
    assert "v1.2 ke naye users ki earning (7 din) kam:" in a[0]["text"]
    mk = {"weeks": [{"from": "2026-08-10", "to": "2026-08-16", "dir": "down", "apps": 9, "of": 10}]}
    _, row, _ = ev(m, st=again(st), market=mk)
    a = alerts(row, "ver_ret")[0]
    assert "market_wide" in a["tags"] and not a["notify"]


def test_ver_ret_old_version_never_alerts():
    old = (("1.0", START, 0), ("1.1", date(2026, 5, 4), 0), ("1.2", date(2026, 6, 15), 0))
    m = app(versions=old, ver_drop=("1.2", 0.8))
    det, _, st = ev(m)
    assert rows(det)["1.2"]["verdict"] == "worse"
    _, row, st2 = ev(m, st=again(st))
    assert not alerts(row, "ver_ret") and not any(k.startswith("ver_ret") for k in st2["eval"]["streak"])


def _vcond(ver, dr="down"):
    return {"key": "a|ver_ret|%s|%s" % (ver, dr), "family": "ver_ret", "metric": "d1", "dir": dr, "cc": None, "ver": ver,
            "severity": "watch", "seed": False, "week_from": "2026-08-10", "week_to": "2026-08-20"}


def test_ver_ret_one_notification_per_7_days():
    e0 = date(2026, 8, 30)
    st, _ = V.episodes(V.empty_state(), AID, e0, [_vcond("1.2"), _vcond("1.3")], True, "2026-08-31T00:00:00Z")
    sent = sorted(e["last"]["ver"] for e in st["episodes"].values() if e["notified_at"] is None)
    assert sent == ["1.2"]                                               # one per app, direction and evaluation
    ids = {e["last"]["ver"]: e["id"] for e in st["episodes"].values()}
    assert ids["1.2"] != ids["1.3"]                                      # one episode per version
    for e in st["episodes"].values():
        e["notified_at"] = e["notified_at"] or "2026-08-31T01:00:00Z"
    st2, _ = V.episodes(st, AID, e0 + timedelta(days=7), [_vcond("1.2"), _vcond("1.3"), _vcond("1.4")], True,
                        "2026-09-04T00:00:00Z")
    assert st2["episodes"]["a|ver_ret|1.4|down"]["seeded"]              # within 7 days of the one sent: shown only
    st3, _ = V.episodes(st, AID, e0 + timedelta(days=14), [_vcond("1.4")], True, "2026-09-14T00:00:00Z")
    assert st3["episodes"]["a|ver_ret|1.4|down"]["notified_at"] is None
    up, _ = V.episodes(st, AID, e0 + timedelta(days=7), [_vcond("1.4", "up")], True, "2026-09-04T00:00:00Z")
    assert up["episodes"]["a|ver_ret|1.4|up"]["notified_at"] is None     # the other direction: its own


def test_ver_ret_warning_only_current_big_clear_unmixed():
    m = app(versions=VERS + (("1.3", S - timedelta(days=1), 0),), ver_drop=("1.2", 0.8))
    _, _, st = ev(m)
    _, row, _ = ev(m, st=again(st))
    a = alerts(row, "ver_ret")
    assert len(a) == 1 and a[0]["ver"] == "1.2" and a[0]["severity"] == "watch"      # 1.2 is not current any more
    m = app(versions=VERS, ver_drop=("1.2", 0.88))
    _, _, st = ev(m)
    _, row, _ = ev(m, st=again(st))
    assert alerts(row, "ver_ret")[0]["severity"] == "watch"             # not 2 × the threshold
    m = app(versions=VERS, ver_drop=("1.2", 1.25))
    _, _, st = ev(m)
    _, row, _ = ev(m, st=again(st))
    a = alerts(row, "ver_ret")
    assert [x["severity"] for x in a] == ["good"] and "zyada ruk rahe" in a[0]["text"]


def test_ver_ids_of_existing_families_unchanged():
    from admob_iq.alerting.rules import fingerprint
    for c in ({"family": "geo_move", "metric": "d1", "cc": "NG", "dir": "down"},
              {"family": "pay_slow", "metric": "b7", "cc": None, "dir": "up"},
              {"family": "iv_link", "metric": "link", "dir": "down"}):
        assert V._eid(AID, c, "2026-09-06") == fingerprint(AID, "value_%s_%s" % (c["family"], c["metric"]), c.get("cc"),
                                                          c["dir"], "2026-09-06")
    c = {"family": "ver_ret", "metric": "d1", "cc": None, "ver": "1.2", "dir": "down"}
    assert V._eid(AID, c, "2026-09-06") == fingerprint(AID, "value_ver_ret_d1", "1.2", "down", "2026-09-06")


def test_ver_error_isolated(monkeypatch):
    m = app(versions=VERS)
    det0, row0, _ = ev(m)

    def boom(*a, **k):
        raise KeyError("x")
    monkeypatch.setattr(VC, "versions", boom)
    det, row, st = ev(m)
    assert det["by_version"] == {"state": "error", "rows": [], "text": None}
    assert det["long"] == det0["long"] and st["eval"]["inputs"]["ver"] is None
    for k in ("tiles", "weeks", "countries", "summary", "scale", "curve"):
        assert det[k] == det0[k], k


# ── D: long-term by install month ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def long_det():
    m = app()
    det, row, st = ev(m)
    return m, det


def test_long_off_by_default_detail_unchanged():
    det, _, st = ev(app(), cd=False)
    assert det["long"] == [] and "long" not in st["eval"]["inputs"]


def test_long_month_cells_complete_or_in_n_days_never_partial(long_det):
    _, det = long_det
    lg = det["long"]
    assert lg["state"] == "ok" and lg["grain"] == "month"
    for r in lg["rows"]:
        to = date.fromisoformat(r["to"])
        for t in VC.LONG_T:
            c = r["d"][str(t)]
            if to + timedelta(days=t) <= S:
                assert c["st"] in ("ok", "few") and c["v"] is not None, (r["key"], t)
            else:
                assert c["v"] is None and c["st"] == "wait" and c["in"] == (to + timedelta(days=t) - S).days
    assert all(date.fromisoformat(r["to"]) <= S for r in lg["rows"])       # the running month is never a row
    assert [r["key"] for r in lg["rows"]] == sorted((r["key"] for r in lg["rows"]), reverse=True)


def test_long_single_day_lags_from_x_base_x_n(long_det):
    m, det = long_det
    r = next(x for x in det["long"]["rows"] if x["key"] == "2026-02")        # 28 Feb + 180 days ≤ S
    ds = days(date(2026, 2, 1), date(2026, 2, 28))
    assert r["n"] == xn(m, ds) and r["days"] == 28 and r["d"]["365"]["st"] == "wait"
    for t, slot in ((30, 5), (60, 7), (90, 8), (180, 10)):
        assert r["d"][str(t)]["v"] == pytest.approx(100 * xu(m, ds, slot) / xn(m, ds), abs=0.001)
        assert r["d"][str(t)]["ret"] == xu(m, ds, slot)


def test_long_quarter_grain_and_low_state():
    det, _, _ = ev(app(base=20))
    lg = det["long"]
    assert lg["grain"] == "quarter" and lg["note"].startswith("Is app me mahine ke install 1,000 se kam")
    r = next(x for x in lg["rows"] if x["key"] == "2026-Q1")
    assert r["label"] == "Q1 2026 (Jan–Mar)" and r["from"] == "2026-01-01" and r["to"] == "2026-03-31"
    det, _, _ = ev(app(base=5))
    assert det["long"]["state"] == "low" and det["long"]["rows"] == [] and "pakka nahi" in det["long"]["text"]


def test_long_partial_first_month_marked_and_kept_out_of_alerts():
    start = date(2025, 5, 17)
    m = app(start=start, long_drop=(date(2025, 5, 1), 1, 0.5))
    det, _, st = ev(m)
    first = det["long"]["rows"][-1]
    assert first["key"] == "2025-05" and first["part"] and first["from"] == "2025-05-17"
    assert first["d"]["60"]["v"] < 0.6 * det["long"]["rows"][-2]["d"]["60"]["v"]
    _, row, _ = ev(m, st=again(st))
    assert not alerts(row, "long_ret")


def test_long_edge_cells_nodata():
    m = app()
    m["ida"]["days"][(S - timedelta(days=100)).isoformat()]["st"] = "retry"   # one activity day not read yet
    det, _, _ = ev(m)
    got = {(r["key"], t): r["d"][str(t)]["st"] for r in det["long"]["rows"] for t in VC.LONG_T}
    hole = S - timedelta(days=100)
    for r in det["long"]["rows"]:
        a, b = date.fromisoformat(r["from"]), date.fromisoformat(r["to"])
        for t in VC.LONG_T:
            if b + timedelta(days=t) <= S and a <= hole <= b + timedelta(days=t):
                assert got[(r["key"], t)] == "nodata"
    assert "nodata" in got.values()
    m = app()
    m["ida"]["edge"] = "2025-09-10"
    det, _, _ = ev(m)
    assert det["long"]["edge"] == "2025-09-10" and det["long"]["rows"][-1]["key"] == "2025-09"
    assert det["long"]["rows"][-1]["part"] and det["long"]["rows"][-1]["from"] == "2025-09-10"


def test_long_rpi_projection_marked_only_from_30(long_det):
    _, det = long_det
    by = {r["key"]: r for r in det["long"]["rows"]}
    jun = by["2026-06"]                              # complete at 60, not at 90: 90 d earning ≈ projected
    assert jun["rpi"]["30"]["proj"] is False and jun["rpi"]["30"]["st"] == "ok"
    assert jun["rpi"]["90"]["proj"] and jun["rpi"]["90"]["shape"] == "app" and jun["rpi"]["90"]["from"] == 60
    assert jun["rpi"]["90"]["lo"] <= jun["rpi"]["90"]["v"] <= jun["rpi"]["90"]["hi"]
    aug = by["2026-08"]                              # not even 30 days old: no projection, "in N days"
    assert all(aug["rpi"][t]["st"] == "wait" and aug["rpi"][t]["v"] is None for t in ("30", "90", "180", "365"))
    assert all("proj" not in c and (c["v"] is None) == (c["st"] in ("wait", "nodata"))   # retention: never projected
               for r in det["long"]["rows"] for c in r["d"].values())


def test_long_b365_only_inside_spend_span():
    m = app()
    m["spend"]["first"] = "2025-11-01"
    det, _, _ = ev(m)
    by = {r["key"]: r for r in det["long"]["rows"]}
    assert by["2025-10"]["b365"] is None and by["2025-11"]["b365"] is not None and by["2025-11"]["b365_proj"]
    r = by["2025-11"]
    spent = sum(v / 1e6 * vs._fx_at(m["fx"]["series"], date.fromisoformat(d))
                for d, v in m["spend"]["daily"].items() if "2025-11-01" <= d <= "2025-11-30")
    assert r["b365"] == pytest.approx(100 * r["rpi"]["365"]["v"] * r["n"] / spent, rel=1e-3)
    det, _, _ = ev(app(spend=False))
    assert all(r["b365"] is None for r in det["long"]["rows"])


def test_long_year_on_every_label(long_det):
    _, det = long_det
    for r in det["long"]["rows"]:
        assert r["label"].endswith(" %d" % r["year"]) and r["key"].startswith("%d-" % r["year"])
    assert VC.fmt_month(date(2025, 12, 3)) == "Dec 2025"
    assert VC._span_months(date(2025, 12, 1), date(2026, 1, 1)) == "Dec 2025–Jan 2026"
    assert VC._span_months(date(2026, 6, 1), date(2026, 7, 1)) == "Jun–Jul 2026"
    assert re.match(r"^\S+ 20\d\d ke installs: back after 90 days [\d.]+% \(pichhle 6 mahine, "
                    r"[A-Z][a-z]{2} 20\d\d–[A-Z][a-z]{2} 20\d\d: ~[\d.]+%\)"
                    r" · 1 saal me earning per install ≈\{m:[\d.e-]+\} \(andaza\)$", det["long"]["text"]), det["long"]["text"]


LONG_DROP = (date(2026, 5, 1), 2, 0.7)


def test_long_ret_two_rows_below_base_z_and_sizes():
    m = app(long_drop=LONG_DROP)
    _, _, st = ev(m)
    _, row, _ = ev(m, st=again(st))
    a = alerts(row, "long_ret")
    assert len(a) == 1 and a[0]["metric"] == "d60" and a[0]["months"] == ["2026-05", "2026-06"]
    assert (a[0]["week_from"], a[0]["week_to"]) == ("2026-05-01", "2026-06-30") and a[0]["base_from"] == "2025-11-01"
    assert a[0]["unit"] == "pp" and a[0]["notify"] and a[0]["users"] > 2 * VC.LONG_JUDGE_N
    assert a[0]["text"] == "May–Jun 2026 ke installs back after 60 days kam: 3.8%, pehle 5.5% (pichhle 6 mahine ka normal)"
    one = app(long_drop=(date(2026, 6, 1), 1, 0.7))                    # only the newest month: not both below
    _, _, st = ev(one)
    _, row, _ = ev(one, st=again(st))
    assert not alerts(row, "long_ret")
    small = app(base=60, long_drop=LONG_DROP)                           # < 3,000 installs a month: never judged
    _, _, st = ev(small)
    _, row, _ = ev(small, st=again(st))
    assert not alerts(row, "long_ret")
    rp = app(long_drop=(date(2026, 1, 1), 2, 0.3))                     # the 6-month earning of Jan–Feb
    _, _, st = ev(rp)
    _, row, _ = ev(rp, st=again(st))
    a = alerts(row, "long_ret")
    assert [x["metric"] for x in a] == ["rpi180"] and a[0]["unit"] == "usd"
    assert a[0]["text"].startswith("Jan–Feb 2026 ke installs ki 6 mahine ki earning per install kam: {m:")


def test_long_ret_watch_only_never_warning():
    m = app(long_drop=(date(2026, 5, 1), 2, 0.2))
    _, _, st = ev(m)
    _, row, _ = ev(m, st=again(st))
    assert [a["severity"] for a in alerts(row, "long_ret")] == ["watch"]


def test_long_ret_seeded_first_eval_and_long_burnin():
    m = app(long_drop=LONG_DROP)
    _, row, st = ev(m)
    assert alerts(row, "long_ret") and not any(a["notify"] for a in row["_alerts"])        # the first evaluation
    assert st["eval"]["inputs"]["long"] == E.isoformat()
    s2 = again(st)
    s2["eval"]["inputs"]["long"] = (E - timedelta(days=14)).isoformat()
    _, row, _ = ev(m, st=s2)
    assert not alerts(row, "long_ret")[0]["notify"]
    young = app(start=S - timedelta(days=150))                          # < 6 whole months complete at 60
    _, _, yst = ev(young)
    assert yst["eval"]["inputs"]["long"] is None


def _lcond(dr="down"):
    return {"key": "a|long_ret|%s" % dr, "family": "long_ret", "metric": "d60", "dir": dr, "cc": None,
            "severity": "watch", "seed": False, "week_from": "2026-05-01", "week_to": "2026-06-30"}


def test_long_ret_one_notification_per_28_days_reopen_91_seeded():
    e0 = date(2026, 8, 30)
    st, _ = V.episodes(V.empty_state(), AID, e0, [_lcond()], True, "2026-08-31T00:00:00Z")
    ep = st["episodes"]["a|long_ret|down"]
    assert ep["notified_at"] is None
    ep["notified_at"] = "2026-08-31T01:00:00Z"
    for i in (1, 2):
        st, _ = V.episodes(st, AID, e0 + timedelta(days=7 * i), [], True, "2026-09-10T00:00:00Z")
    assert not st["episodes"] and st["closed"]
    back, _ = V.episodes(st, AID, e0 + timedelta(days=21), [_lcond()], True, "2026-09-20T00:00:00Z")
    assert back["episodes"]["a|long_ret|down"]["seeded"]               # within 28 days of the one sent
    closed = date.fromisoformat(st["closed"][-1]["closed"])
    back, _ = V.episodes(st, AID, closed + timedelta(days=84), [_lcond()], True, "2026-12-10T00:00:00Z")
    assert back["episodes"]["a|long_ret|down"]["seeded"]               # a reopen within 91 days of its close
    back, _ = V.episodes(st, AID, closed + timedelta(days=98), [_lcond()], True, "2026-12-24T00:00:00Z")
    assert back["episodes"]["a|long_ret|down"]["notified_at"] is None


def test_long_up_is_info_row_not_alert():
    m = app(long_drop=(date(2026, 5, 1), 2, 1.4))
    _, _, st = ev(m)
    det, row, _ = ev(m, st=again(st))
    assert not alerts(row, "long_ret")
    info = [i for i in det["changes"]["info"] if i["kind"] == "long_up"]
    assert len(info) == 1 and info[0]["text"] == "May–Jun 2026 ke installs back after 60 days zyada: 7.7%, pehle 5.5%"


def test_long_error_isolated(monkeypatch):
    m = app(versions=VERS)
    det0, _, _ = ev(m)

    def boom(*a, **k):
        raise ZeroDivisionError()
    monkeypatch.setattr(VC, "long_term", boom)
    det, _, st = ev(m)
    assert det["long"] == {"state": "error", "rows": [], "text": None} and st["eval"]["inputs"]["long"] is None
    assert det["by_version"] == det0["by_version"]
    for k in ("tiles", "weeks", "countries", "summary"):
        assert det[k] == det0[k], k


# ── texts ───────────────────────────────────────────────────────────────────────────────────────

BANNED = re.compile(r"cohort|checkpoint|cumulative|bharosa|headline|\bLTV\b", re.I)
DEVANAGARI = re.compile("[ऀ-ॿ]")


def _texts(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("text", "message", "note") and isinstance(v, str):
                yield v
            else:
                yield from _texts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _texts(v)


def test_cd_texts_hinglish_no_banned_no_devanagari():
    got = []
    for kw in (dict(versions=VERS, ver_drop=("1.2", 0.8), long_drop=LONG_DROP),
               dict(versions=VERS, ver_drop=("1.2", 1.25), long_drop=(date(2026, 5, 1), 2, 1.4)),
               dict(versions=VERS, vsplit=False, base=20), dict(versions=(("4.0", START, 0),), base=5),
               dict(versions=VERS + (("1.3", S - timedelta(days=1), 0),), organic=(date(2026, 8, 10), S, 3.0),
                    ver_drop=("1.2", 0.8)),
               dict(start=S - timedelta(days=50), versions=(("1.0", S - timedelta(days=50), 0),))):
        m = app(**kw)
        _, _, st = ev(m)
        det, row, _ = ev(m, st=again(st))
        got += list(_texts(det["by_version"])) + list(_texts(det["long"])) + list(_texts(row["_alerts"]))
        got += [i["text"] for i in det["changes"]["info"] if i["kind"].startswith(("ver", "long"))]
    got += [VC.ver_alert_text({"metric": "d7", "dir": "down", "ver_label": "v2", "now": 12, "before": 15, "users": 4000,
                               "mix": {"i0": 800, "i1": 2400}, "linked": True})]
    assert len(got) > 25
    for t in got:
        assert t and not BANNED.search(t) and not DEVANAGARI.search(t), t
        assert "None" not in t and "nan" not in t.lower().split(), t


def test_no_date_literal_in_value_cd_py():
    src = open(os.path.join(os.path.dirname(VC.__file__), "value_cd.py"), encoding="utf-8").read()
    assert not re.search(r"\b(19|20)\d\d-\d\d-\d\d\b", src)
    assert not re.search(r"\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", src)


# ── the review's fixes ──────────────────────────────────────────────────────────────────────────

def _two_weeks(vers, drop, **kw):
    """Two weekly evaluations a week apart on the same made-up history (every input seen long ago)."""
    st, out = None, []
    for end in (END - timedelta(days=7), END):
        m = app(end=end, versions=vers, ver_drop=drop, **kw)
        if st is not None:
            st = copy.deepcopy(st)
            st["eval"]["inputs"] = {k: OLD for k in st["eval"]["inputs"]}
        det, row, st = ev(m, st=st)
        out.append((det, row, st))
    return out


def test_ver_ret_bad_release_then_two_hotfixes_still_alerts_and_the_fix_is_no_good_news():
    """A bad release followed within days by two hotfixes and a new version: the hotfixes never push it out of the
    versions that can alert before its second evaluation — and the fix, "higher" only against the bad release it
    replaced (a recovery), sends no "good"."""
    D = lambda k: S - timedelta(days=k)
    vers = (("1.0", START, 0), ("2.3", D(60), 0), ("2.4", D(18), 0), ("2.4.1", D(11), 0), ("2.4.2", D(9), 0),
            ("2.5", D(5), 0))
    (_, r1, s1), (d2, r2, s2) = _two_weeks(vers, ("2.4", 0.6))
    assert not alerts(r1, "ver_ret") and s1["eval"]["streak"]["ver_ret|2.4|d1|down"] == 1
    a = alerts(r2, "ver_ret")
    assert [(x["ver"], x["dir"], x["notify"]) for x in a] == [("2.4", "down", True)]
    fix = rows(d2)["2.4.2"]
    assert fix["verdict"] == "better" and fix["vs"]["ver"] == "2.4"                 # shown in the table as it is
    assert not any(v for k, v in s2["eval"]["streak"].items() if k.startswith("ver_ret|2.4.2|"))


def test_ver_ret_a_version_every_4_days_still_gets_its_second_evaluation():
    vers, d, i = [("1.0", START, 0)], S - timedelta(days=70), 0
    while d <= S:
        vers.append(("2.%d" % i, d, 0))
        d += timedelta(days=4)
        i += 1
    (_, r1, _), (_, r2, s2) = _two_weeks(tuple(vers), ("2.14", 0.6))
    assert not alerts(r1, "ver_ret")
    assert [(x["ver"], x["dir"], x["notify"]) for x in alerts(r2, "ver_ret")] == [("2.14", "down", True)]
    assert not any(v for k, v in s2["eval"]["streak"].items() if k.startswith("ver_ret|2.15|"))   # the fix: no "good"


def test_ver_short_finished_version_is_too_short_not_few_installs():
    """A version finished in under VER_MIN_DAYS days is "short" (never comparable) however many installs it had —
    "few" stays for a version with too few installs."""
    D = lambda k: S - timedelta(days=k)
    m = app(versions=(("1.0", START, 0), ("1.1", D(40), 0), ("1.1.1", D(20), 0, D(19)), ("1.2", D(18), 0)))
    r = rows(ev(m)[0])
    x = r["1.1.1"]
    assert x["n"] >= VC.VER_JUDGE_N and x["days"] == 2 and x["verdict"] == "short"
    assert x["vs"]["d1"]["st"] == "short" and "tulna ke liye 3+ din chahiye" in x["text"]


def test_ver_part_cell_on_few_installs_is_flagged():
    """A version still coming in whose complete days hold fewer than VER_JUDGE_N installs: its "31*" cell is flagged
    few (the page greys it) — never a settled-looking number."""
    m = app(versions=(("1.0", START, 0), ("1.1", S - timedelta(days=60), 0), ("1.2", S - timedelta(days=8), 0)),
            base=120)
    r = rows(ev(m)[0])["1.2"]
    assert r["n"] >= VC.VER_JUDGE_N and r["d7"]["st"] == "part" and r["d7"]["n"] < VC.VER_JUDGE_N
    assert r["d7"]["few"] is True and "few" not in r["d1"]                           # D1's part: big enough


def test_cd_switched_off_then_on_restarts_burn_in_and_streaks():
    """VALUE_CD on → off → on: the state switched off is exactly one that was never on (no ver / long input, no
    ver_ret streak), so the first evaluation back seeds everything and needs 2 evaluations again."""
    m = app(versions=VERS, ver_drop=("1.2", 0.8), long_drop=LONG_DROP)
    _, _, s_on = ev(m)
    s_on = again(s_on)
    s_on["eval"]["streak"] = {k: 1 for k in s_on["eval"]["streak"]}
    _, _, s_off = ev(m, st=s_on, cd=False)
    assert "ver" not in s_off["eval"]["inputs"] and "long" not in s_off["eval"]["inputs"]
    assert not any(k.startswith("ver_ret|") for k in s_off["eval"]["streak"])
    assert set(s_off["eval"]["inputs"]) == set(ev(m, cd=False)[2]["eval"]["inputs"])     # as if never on
    back = again(s_off, inputs=None)
    _, row, s_back = ev(m, st=back)
    assert all(not a["notify"] for a in row["_alerts"] if a["family"] in ("ver_ret", "long_ret"))
    assert not alerts(row, "ver_ret") and s_back["eval"]["streak"].get("ver_ret|1.2|d1|down") == 1


def test_long_b365_needs_a_month_of_real_ads_spend():
    """"1 yr per ₹100" only for a month whose spend passes B's own floor (SPEND_MIN_WEEK a week): a trickle of spend
    against a whole month's installs (organic too) is no return on ads — null, and said ("b365_thin")."""
    m = app()
    for d in list(m["spend"]["daily"]):
        if d.startswith("2026-03"):
            m["spend"]["daily"][d] = 0
    m["spend"]["daily"]["2026-03-10"] = 40 * 10 ** 6                        # one day of ₹40 in the month
    det, _, _ = ev(m)
    by = {r["key"]: r for r in det["long"]["rows"]}
    assert by["2026-03"]["b365"] is None and by["2026-03"]["b365_thin"] is True and not by["2026-03"]["b365_proj"]
    assert by["2026-02"]["b365"] is not None and by["2026-02"]["b365_thin"] is False
    assert all(r["b365_thin"] is False for r in ev(app(spend=False))[0]["long"]["rows"])   # no ads at all: not "thin"
