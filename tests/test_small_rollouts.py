"""📦 Small (staged / halted) rollouts — a new app version that never reached RELEASE_SHARE of a day's active users
(engine.uninstall.small_rollouts), on synthetic data only (made-up versions 9.9.x, made-up apps; no real data):

  * the rule: listed once it ran on ≥ ROLLOUT_MIN_USERS active users on ≥ ROLLOUT_MIN_DAYS days and was not on the
    store's first versions day; its date = its first day on that many users; measured shares only, rounded DOWN to 5
    decimals (its highest, the one on the newest day). Test builds and a few testers (fewer users or days, or a name
    with ROLLOUT_SKIP_WORDS), "(not set)" and a version already there on the first day are never listed;
  * still rolling out ("live") only while it runs on that many users AND nothing newer came — a newer release / rollout
    / later update surge is "newer" (its tail of users is no rollout); an update surge during its life (a staged ramp
    can make one) is linked ("surge"), the row stays (the version stays visible) and says that row measured it;
  * a rollout that reaches RELEASE_SHARE becomes a release (releases() lists it from that day) and leaves this list —
    day by day, never in both;
  * nothing else moves: releases, update impact, alerts, episodes, the summary and every other number are exactly what
    they are with small_rollouts() switched off; without a small rollout no new key anywhere (the files byte-identical);
  * the chain on the REAL build code (tests/active_studio_synth.py's site): the uninstall detail → the Active users
    detail (as it is) → both Studio files ("srl" rows, the rule in meta — only with them) → the page (rendered for real
    by tests/small_rollout_frontend.js): both Studios' Updates lists show a "Staged rollout" row in date order with the
    updates, the honest count in the header and the rule — and nothing else on the page changes."""

import copy
import gzip
import json
import math
import os
import re
import shutil
import subprocess
from datetime import date, timedelta

import pytest

from admob_iq import active_studio_build as asb
from admob_iq import build_static
from admob_iq import uninstall_studio_build as usb
from admob_iq.config import settings
from admob_iq.engine import active as act
from admob_iq.engine import uninstall as eng
from tests import active_studio_synth as ss
from tests.uninstall_synth import END, active_udet, make_active_store, make_store

AID = "ca-app-pub-0000000000000000~0000000001"
NOW = "2026-09-21T01:00:00Z"
A1 = 25000                     # make_store's active users a day (a28 100,000 ÷ 4)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")
DEVA = re.compile("[ऀ-ॿ]")


def iso(d):
    return d.isoformat()


def store_with(extra, days=120, **kw):
    """make_store with versions {"1.0": the rest of the day's A1 users, **extra(day)} — extra: fn(day) → {version:
    users} (made-up versions)."""
    def vers(d):
        x = {k: u for k, u in (extra(d) or {}).items() if u}
        return dict({"1.0": A1 - sum(x.values())}, **x)
    return make_store(days, 1000, versions=vers, **kw)


def evaluate(store, E=None, state=None):
    if E is not None:
        store = dict(store, window_end=iso(E))
    return eng.evaluate_app(store, AID, "Demo App", {} if state is None else state, NOW)


def vers_of(rels):
    return [r["version"] for r in rels if r.get("version")]


# ── the rule ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_staged_rollout_under_the_release_share_is_listed_with_its_measured_shares():
    r0 = END - timedelta(days=14)                          # made up: 50 → 218 users (0.2% → 0.87%) over 15 days, still out
    st = store_with(lambda d: {"9.9.1": 50 + 12 * (d - r0).days} if d >= r0 else {})
    d, _ = evaluate(st)
    assert d["small_rollouts"] == [{"date": iso(r0), "version": "9.9.1", "kind": "rollout", "max_share": 0.00872,
                                    "last_share": 0.00872, "days_seen": 15, "till": iso(END), "live": True,
                                    "surge": [], "newer": None}]
    assert "9.9.1" not in vers_of(d["releases"])           # never a release: no card, no verdict, no zoom
    assert not any("9.9.1" in json.dumps(u) for u in d["impact"].get("updates") or [])
    assert d["zoom"] is None or "9.9.1" not in d["zoom"]["label"]


def test_test_builds_a_few_testers_and_not_set_are_never_listed():
    r0 = END - timedelta(days=30)

    def extra(d):
        k = (d - r0).days
        x = {}
        if k >= 0:
            x["9.9.2"] = 49                                # every day, but never 50 users: noise
            x["(not set)"] = 2000
        if k in (3, 4):
            x["9.9.3"] = 500                               # 500 users, but on 2 days only: a test build
        if k in (2, 9, 20):
            x["9.9.4"] = 50                                # exactly 50 users on exactly 3 days: the rule's edge, listed
        if -5 <= k < 0:
            x["9.9.5"] = 3                                 # a few tester devices before …
        if 0 <= k < 5:
            x["9.9.5"] = 80                                # … then the rollout: its date is the first day on 50+
        if 10 <= k < 14:                                   # 80 users on 4 days, but the name says test build: never
            x.update({"9.9.6-test": 80, "9.9.6 - QA": 80, "9.9.6-Debug": 80, "9.9.6.internal": 80})
        if 22 <= k < 26:
            x["9.9.6-latest"] = 60                         # "test" inside a word is no test build: listed
        return x
    d, _ = evaluate(store_with(extra))
    got = {r["version"]: r for r in d["small_rollouts"]}
    assert set(got) == {"9.9.4", "9.9.5", "9.9.6-latest"}
    assert got["9.9.4"]["date"] == iso(r0 + timedelta(days=2)) and got["9.9.4"]["days_seen"] == 3
    assert got["9.9.5"]["date"] == iso(r0) and got["9.9.5"]["days_seen"] == 5
    assert not got["9.9.4"]["live"] and not got["9.9.5"]["live"] and got["9.9.5"]["last_share"] == 0.0
    # each one's "newer": the next rollout after it (the test builds never count)
    assert [got[v]["newer"] for v in ("9.9.5", "9.9.4", "9.9.6-latest")] == [
        iso(r0 + timedelta(days=2)), iso(r0 + timedelta(days=22)), None]


def test_a_version_already_there_on_the_first_versions_day_is_not_news():
    hs = END - timedelta(days=119)
    st = store_with(lambda d: {"9.9.6": 10 if d == hs else (300 if d >= END - timedelta(days=20) else 0)})
    d, _ = evaluate(st)
    assert "small_rollouts" not in d and "9.9.6" not in vers_of(d["releases"])


def test_a_halted_rollout_says_it_is_not_out_any_more():
    r0 = END - timedelta(days=30)
    st = store_with(lambda d: {"9.9.7": (200 if (d - r0).days < 8 else 20)} if d >= r0 else {})
    (r,) = evaluate(st)[0]["small_rollouts"]
    assert (r["date"], r["days_seen"], r["max_share"], r["last_share"], r["live"], r["newer"], r["surge"]) == (
        iso(r0), 8, 0.008, 0.0008, False, None, [])


def test_a_rollout_a_newer_release_replaced_is_not_live_though_its_tail_stays():
    r0, rel = END - timedelta(days=40), END - timedelta(days=20)

    def extra(d):
        if d >= rel:
            return {"9.9.2": 120, "9.9.3": A1 * 3 // 5}    # a newer version out to 60%; 120 users never updated
        return {"9.9.2": 250} if d >= r0 else {}           # staged to 1% before it
    d, _ = evaluate(store_with(extra))
    assert {"date": iso(rel), "version": "9.9.3", "kind": "version"} in d["releases"]
    (r,) = d["small_rollouts"]
    assert (r["version"], r["date"], r["max_share"], r["last_share"], r["newer"], r["live"]) == (
        "9.9.2", iso(r0), 0.01, 0.0048, iso(rel), False)
    # a newer small rollout replaces it the same way; the newest one is live
    st = store_with(lambda d: dict({"9.9.4": 250} if d >= r0 else {}, **({"9.9.5": 200} if d >= rel else {})))
    a, b = evaluate(st)[0]["small_rollouts"]
    assert (a["version"], a["newer"], a["live"], b["version"], b["newer"], b["live"]) == (
        "9.9.4", iso(rel), False, "9.9.5", None, True)


def test_a_share_just_under_the_release_share_is_rounded_down_never_up():
    r0 = END - timedelta(days=10)
    st = store_with(lambda d: {"9.9.1": 1249} if d >= r0 else {})          # 4.996% of the users, 11 days
    d, _ = evaluate(st)
    (r,) = d["small_rollouts"]
    assert r["max_share"] == r["last_share"] == 0.04996 < eng.RELEASE_SHARE and "9.9.1" not in vers_of(d["releases"])
    assert eng._share5(1, 2000000) == 0.0 and eng._share5(60, 2000000) == 0.00003 and eng._share5(37, 10000) == 0.0037


def test_crossing_the_release_share_makes_it_a_release_and_takes_it_off_the_list():
    r0, up = END - timedelta(days=20), END - timedelta(days=10)
    st = store_with(lambda d: {"9.9.8": 1500 if d >= up else (100 if d >= r0 else 0)})      # 0.4% … then 6%
    seen = []
    for k in range(20, -1, -1):
        E = END - timedelta(days=k)
        d, _ = evaluate(st, E)
        small, rel = vers_of(d.get("small_rollouts") or []), vers_of(d["releases"])
        assert not ("9.9.8" in small and "9.9.8" in rel)                       # never both
        seen.append((iso(E), "small" if "9.9.8" in small else "release" if "9.9.8" in rel else None))
        if E >= up:
            assert {"date": iso(up), "version": "9.9.8", "kind": "version"} in d["releases"]
            assert "small_rollouts" not in d                                   # moved out, nothing left behind
    assert [w for _, w in seen] == [None] * 2 + ["small"] * 8 + ["release"] * 11      # listed from its 3rd day on 50+


def test_an_update_surge_during_the_rollout_is_linked_and_the_version_stays_visible():
    r0 = END - timedelta(days=20)
    roll = lambda d: {"9.9.9": 100} if d >= r0 else {}                         # noqa: E731
    near = store_with(roll, upd=lambda d: 2000 if d == r0 + timedelta(days=1) else 300)
    d, _ = evaluate(near)
    assert {"date": iso(r0 + timedelta(days=1)), "version": None, "kind": "update"} in d["releases"]
    (r,) = d["small_rollouts"]                             # listed, linked to that update row (which measured it)
    assert (r["version"], r["surge"], r["live"], r["newer"]) == ("9.9.9", [iso(r0 + timedelta(days=1))], True, None)
    far = store_with(roll, upd=lambda d: 2000 if d == r0 - timedelta(days=30) else 300)
    d, _ = evaluate(far)
    assert {"date": iso(r0 - timedelta(days=30)), "version": None, "kind": "update"} in d["releases"]
    (r,) = d["small_rollouts"]
    assert (r["version"], r["surge"], r["newer"], r["live"]) == ("9.9.9", [], None, True)


def test_a_surge_from_the_ramp_long_after_the_first_day_is_linked_too():
    r0 = END - timedelta(days=30)                          # 100 users (0.4%), ramped to 750 (3%, never 5%) 10 days on
    ramp = r0 + timedelta(days=10)
    st = store_with(lambda d: {"9.9.1": 750 if d >= ramp else 100} if d >= r0 else {},
                    upd=lambda d: 3000 if d == ramp else 300)
    d, _ = evaluate(st)
    assert d["releases"] == [{"date": iso(ramp), "version": None, "kind": "update"}]
    assert [u["date"] for u in d["impact"]["updates"]] == [iso(ramp)]     # its own card and verdict, untouched
    (r,) = d["small_rollouts"]
    assert (r["date"], r["surge"], r["live"], r["max_share"]) == (iso(r0), [iso(ramp)], True, 0.03)


def test_an_update_surge_after_a_halted_rollout_is_the_newer_update():
    r0 = END - timedelta(days=40)
    up = r0 + timedelta(days=20)                           # 9.9.2 stopped after 8 days; an update 12 days later
    st = store_with(lambda d: {"9.9.2": 150} if r0 <= d < r0 + timedelta(days=8) else {},
                    upd=lambda d: 3000 if d == up else 300)
    (r,) = evaluate(st)[0]["small_rollouts"]
    assert (r["surge"], r["newer"], r["live"]) == ([], iso(up), False)


# ── nothing else moves ─────────────────────────────────────────────────────────────────────────────────────────────

def test_nothing_but_the_new_rows_changes_day_after_day(monkeypatch):
    rel, r0 = END - timedelta(days=60), END - timedelta(days=25)

    def extra(d):
        x = {"9.9.1": A1 // 2} if d >= rel else {}                             # a real release (50% of the users)
        if d >= r0:
            x["9.9.2"] = 120                                                   # and a staged rollout after it
        return x
    st = store_with(extra, days=200, upd=lambda d: 2500 if d == END - timedelta(days=40) else 300,
                    bump=lambda c: {1: 30} if c >= END - timedelta(days=30) else None)   # an alert to carry along
    on, off = {}, {}
    days = [END - timedelta(days=k) for k in range(6, -1, -1)]
    outs_on = [evaluate(st, E, on) for E in days]
    monkeypatch.setattr(eng, "small_rollouts", lambda *a, **k: [])
    outs_off = [evaluate(st, E, off) for E in days]
    assert on == off                                                           # episodes, eval state: the same
    for (d1, r1), (d2, r2) in zip(outs_on, outs_off):
        assert vers_of(d1["small_rollouts"]) == ["9.9.2"] and "small_rollouts" not in d2
        d1 = dict(d1)
        d1.pop("small_rollouts")
        assert json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True) and r1 == r2
    assert outs_on[-1][0]["releases"] == outs_off[-1][0]["releases"] and vers_of(outs_on[-1][0]["releases"]) == ["9.9.1"]


def test_without_a_small_rollout_the_detail_has_no_new_key(monkeypatch):
    st = store_with(lambda d: {"9.9.1": A1 // 2} if d >= END - timedelta(days=30) else {})
    d1, r1 = evaluate(st)
    monkeypatch.setattr(eng, "small_rollouts", lambda *a, **k: [])
    d2, r2 = evaluate(st)
    assert "small_rollouts" not in d1 and json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True) and r1 == r2


def test_the_active_users_detail_carries_them_as_they_are():
    st, rv = make_active_store(200, noise=0.01)
    rows = [{"date": iso(END - timedelta(days=9)), "version": "9.9.1", "kind": "rollout", "max_share": 0.0055,
             "last_share": 0.0042, "days_seen": 10, "till": iso(END), "live": True, "surge": [], "newer": None}]
    u_on, u_off = active_udet(st), active_udet(st)
    u_on["small_rollouts"] = rows
    d_on, row_on = act.evaluate(st, "a", "App", {}, NOW, u_on, "0123456789ab", rv, None)
    d_off, row_off = act.evaluate(st, "a", "App", {}, NOW, u_off, "0123456789ab", rv, None)
    assert d_on["small_rollouts"] == rows and d_on["small_rollouts"] is not rows and "small_rollouts" not in d_off
    d_on.pop("small_rollouts")
    assert json.dumps(d_on, sort_keys=True) == json.dumps(d_off, sort_keys=True) and row_on == row_off


# ── the chain on the real build code: files and page ───────────────────────────────────────────────────────────────

ROLL = END - timedelta(days=12)        # Demo Torch: 9.9.1 staged to 60 → 108 users (~0.6–1%), still out, no update
HALT = END - timedelta(days=25)        # Demo Photos: 9.9.3 on 100 users for 6 days, then a tail of 60 who never updated —
G1_REL = END - timedelta(days=17)      # its 2.1 update (the synth's own) replaced it: not live, "newer" = that day
TEST = (END - timedelta(days=30), END - timedelta(days=29))   # Demo Photos: a test build 9.9.2, 80 users on 2 days
TEST_N = END - timedelta(days=35)      # … and one named so: 9.9.4-test, 80 users on 4 days
REL_N = END - timedelta(days=40)       # Demo Notes: a real release 3.1 (60% of the users) …
ROLL_N = END - timedelta(days=8)       # … then 9.9.5 staged to 70 → 102 users, still out — NEWER than the release


def _stores(orig):
    def f():
        S = orig()
        t = S[ss.T1][0]["versions"]
        for d, v in t.items():
            k = (date.fromisoformat(d) - ROLL).days
            if k >= 0:
                v["1.0"] -= 60 + 4 * k
                v["9.9.1"] = 60 + 4 * k
        g = S[ss.G1][0]["versions"]
        for d, v in g.items():
            k = (date.fromisoformat(d) - HALT).days
            if k >= 0:
                big = max(sorted(v), key=v.get)
                v[big] -= 100 if k < 6 else 60
                v["9.9.3"] = 100 if k < 6 else 60
            if d in map(iso, TEST):
                v["2.0"] -= 80
                v["9.9.2"] = 80
            if 0 <= (date.fromisoformat(d) - TEST_N).days < 4:
                v["2.0"] -= 80
                v["9.9.4-test"] = 80
        n = S[ss.N1][0]["versions"]
        for d, v in n.items():
            if date.fromisoformat(d) >= REL_N:
                m = int(v["1.0"] * 0.6)
                v["1.0"] -= m
                v["3.1"] = m
            k = (date.fromisoformat(d) - ROLL_N).days
            if k >= 0:
                v["3.1"] -= 70 + 4 * k
                v["9.9.5"] = 70 + 4 * k
        return S
    return f


def _gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def sites(tmp_path_factory):
    """The Active users Studio's synthetic site with the rollouts above, built twice by the REAL build code (the
    Uninstall step with Active users, then both Studio steps): "on" as is, "off" with small_rollouts() → [] — the site
    exactly as without the feature → {v: (root, site, dashboard)}."""
    out = {}
    orig = ss.stores
    for v in ("on", "off"):
        root = str(tmp_path_factory.mktemp("srl_" + v))
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(ss, "stores", _stores(orig))
            if v == "off":
                mp.setattr(eng, "small_rollouts", lambda *a, **k: [])
            site, cfg, dash = ss.make_site(root)
            data = os.path.join(root, "data")
            assert build_static._active_studio_step(dash, data, site, dict(settings())) == [
                "/active_studio.json.gz", "/active_studio_old.json.gz"]
            assert build_static._studio_step(dash, data, site, dict(settings())) == [
                "/uninstall_studio.json.gz", "/uninstall_studio_old.json.gz"]
        out[v] = (root, site, json.loads(json.dumps(dash)))
    return out


def _expect(site_root, aid, ver, newer=None):
    """The rollout's row worked out here, straight from the store on disk (independently of the engine; shares rounded
    down to 5 decimals); newer = the day a newer version came (known from the setup above)."""
    from admob_iq.fetch import ga4_uninstall as gu
    st = gu.load_store(gu.store_path(os.path.join(site_root, "data"), aid))
    days = sorted(d for d in st["versions"] if d <= st["window_end"])
    sh = {d: math.floor(st["versions"][d].get(ver, 0) * 100000 / st["daily"][d]["a1"]) / 100000 for d in days}
    on = [d for d in days if st["versions"][d].get(ver, 0) >= eng.ROLLOUT_MIN_USERS]
    till = days[-1]
    return {"date": on[0], "version": ver, "kind": "rollout", "max_share": max(sh.values()),
            "last_share": sh[till], "days_seen": len(on), "till": till,
            "live": st["versions"][till].get(ver, 0) >= eng.ROLLOUT_MIN_USERS and newer is None, "surge": [],
            "newer": newer and iso(newer)}


SRL_APPS = (ss.T1, ss.G1, ss.N1)


def test_the_chain_carries_the_rows_to_both_studio_files(sites):
    root, site, dash = sites["on"]
    uni = {a["app_id"]: a for a in _gz(os.path.join(site, "uninstall.json.gz"))["apps"]}
    t1, g1, n1 = (_expect(root, ss.T1, "9.9.1"), _expect(root, ss.G1, "9.9.3", G1_REL),
                  _expect(root, ss.N1, "9.9.5"))
    assert t1["date"] == iso(ROLL) and t1["live"] and t1["days_seen"] == 13 and 0.005 < t1["max_share"] < eng.RELEASE_SHARE
    assert g1["date"] == iso(HALT) and not g1["live"] and g1["days_seen"] == 26 and g1["last_share"] > 0   # a tail …
    assert n1["date"] == iso(ROLL_N) and n1["live"] and n1["days_seen"] == 9
    assert uni[ss.T1]["small_rollouts"] == [t1] and uni[ss.G1]["small_rollouts"] == [g1]     # (9.9.2, 9.9.4-test: test
    assert uni[ss.N1]["small_rollouts"] == [n1]                                              # builds — never listed)
    assert all("small_rollouts" not in a for k, a in uni.items() if k not in SRL_APPS)
    assert vers_of(uni[ss.G1]["releases"]) == ["2.1"] and not vers_of(uni[ss.T1]["releases"])
    assert {"date": iso(G1_REL), "version": "2.1", "kind": "version"} in uni[ss.G1]["releases"]
    assert vers_of(uni[ss.N1]["releases"]) == ["3.1"] and uni[ss.N1]["releases"][0]["date"] == iso(REL_N)
    for r in dash["active"]["apps"]:                                   # the Active users detail: as it is
        af = _gz(os.path.join(site, r["file"]))
        assert af.get("small_rollouts") == uni[r["app_id"]].get("small_rollouts")
    row = lambda x: [x["date"], "v" + x["version"], x["max_share"], x["last_share"], x["days_seen"], x["till"],  # noqa: E731
                     1 if x["live"] else 0, x["surge"], x["newer"]]
    for name, mod in ((asb.FILE, asb), (usb.FILE, usb)):
        body = _gz(os.path.join(site, name))
        srl = {a["id"]: a.get("srl") for a in body["apps"]}
        assert srl[ss.T1] == [row(t1)] and srl[ss.G1] == [row(g1)] and srl[ss.N1] == [row(n1)], name
        assert all(v is None for k, v in srl.items() if k not in SRL_APPS), name
        assert body["meta"]["srl"] == {"share": eng.RELEASE_SHARE, "users": eng.ROLLOUT_MIN_USERS,
                                       "days": eng.ROLLOUT_MIN_DAYS, "skip": list(eng.ROLLOUT_SKIP_WORDS)} == mod.srl_rule()


def test_the_span_end_cuts_the_rows_like_the_updates():
    E = iso(END)
    nxt = iso(END + timedelta(days=1))
    rows = [{"date": nxt, "version": "9.9.1"}, {"date": E, "version": "v9.9.2", "live": True, "surge": [E, nxt],
                                                "newer": nxt}, {"date": E, "version": None}, "x"]
    for mod in (asb, usb):
        assert mod._srl(rows, E) == [[E, "v9.9.2", None, None, None, None, 1, [E], None]] and mod._srl(None, E) == []


def _strip(o, keys):
    for k in keys:
        o.pop(k, None)
    return o


def _unhash(d):
    """A dashboard without the content hashes of the files that gained the rows (the pointers' v / asset_v / sig)."""
    d = copy.deepcopy(d)
    for t in ("uninstall", "active"):
        d[t].pop("asset_v", None)
        (d[t].get("studio") or {}).pop("v", None)
    for r in d["active"]["apps"]:
        r.pop("sig", None)
    return d


def test_nothing_else_changes_in_the_site(sites):
    (r_on, s_on, dash_on), (r_off, s_off, dash_off) = sites["on"], sites["off"]
    names = sorted(os.listdir(s_on))
    assert names == sorted(os.listdir(s_off))
    changed = set()
    for n in names:
        a, b = os.path.join(s_on, n), os.path.join(s_off, n)
        if open(a, "rb").read() == open(b, "rb").read():
            continue
        changed.add(n)
        x, y = _gz(a), _gz(b)
        if n == "uninstall.json.gz":
            x["apps"] = [_strip(d, ["small_rollouts"]) for d in x["apps"]]
        elif n.startswith("active_") and "studio" not in n:
            _strip(x, ["small_rollouts"])
        elif n in (asb.FILE, usb.FILE):
            _strip(x["meta"], ["srl"])
            x["apps"] = [_strip(d, ["srl"]) for d in x["apps"]]
        elif n == "dashboard.json.gz":
            x, y = _unhash(x), _unhash(y)
        assert x == y, n
    keys = {r["app_id"]: r["file"] for r in dash_on["active"]["apps"]}
    assert changed == {"uninstall.json.gz", keys[ss.T1], keys[ss.G1], keys[ss.N1], asb.FILE, usb.FILE,
                       "dashboard.json.gz"}
    for dn in ("data",):                                  # the engine's state (episodes, eval): byte for byte the same
        for base, _, files in os.walk(os.path.join(r_on, dn)):
            for f in files:
                p = os.path.join(base, f)
                q = os.path.join(r_off, os.path.relpath(p, r_on))
                assert open(p, "rb").read() == open(q, "rb").read(), p
    assert _unhash(dash_on) == _unhash(dash_off)          # the dashboard (with the Studio pointers) likewise


# ── the page ───────────────────────────────────────────────────────────────────────────────────────────────────────

EDGE_APP = ss.Y1                       # the "edge" variant: made-up rows on an app without one, at the rule's edges
E_ = END


def _edge_rows():
    d = lambda k: iso(END - timedelta(days=k))                                 # noqa: E731
    return [[d(30), "v9.9.5", 0.012, 0.0, 6, iso(END), 0, [d(28)], d(20)],     # a surge during it, then a newer update
            [d(20), "v9.9.6", 0.00003, 0.0, 5, iso(END), 0, [], None],         # halted, a tiny share
            [d(3), "v9.9.7", 0.04996, 0.04996, 4, iso(END), 1, [], None]]      # still out, just under the share


@pytest.fixture(scope="module")
def report(sites, tmp_path_factory):
    if NODE is None:
        pytest.skip("node is not installed")
    fx = str(tmp_path_factory.mktemp("srl_fe"))

    def write(v, name, body):
        with open(os.path.join(fx, "%s_%s.json" % (name, v)), "w", encoding="utf-8") as f:
            json.dump(body, f)
    for v, (root, site, dash) in sites.items():
        files = {r["key"]: _gz(os.path.join(site, r["file"])) for r in dash["active"]["apps"]}
        for name, body in (("dashboard", dash), ("uninstall", _gz(os.path.join(site, "uninstall.json.gz"))),
                           ("active_files", files), ("as", dict(_gz(os.path.join(site, asb.FILE)), v=asb.V)),
                           ("us", dict(_gz(os.path.join(site, usb.FILE)), v=usb.V))):
            write(v, name, body)
            if v == "on":                              # "edge": the same files, made-up rows on EDGE_APP (Studio files)
                if name in ("as", "us"):
                    body = copy.deepcopy(body)
                    (a,) = [a for a in body["apps"] if a["id"] == EDGE_APP]
                    assert "srl" not in a
                    a["srl"] = _edge_rows()
                write("edge", name, body)
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        js = max(re.findall(r"<script>(.*?)</script>", f.read(), re.S), key=len)
    path = os.path.join(fx, "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "small_rollout_frontend.js"), path, fx],
                         check=True, capture_output=True, text=True, timeout=600)
    rep = json.loads(out.stdout)
    assert rep["errors"] == [] and sorted(rep["out"]) == ["edge", "off", "on"]
    return {v: json.loads(x) for v, x in rep["out"].items()}


def _text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", h).replace("&lt;", "<").replace("&amp;", "&")).strip()


def _fd(d):
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return "%d %s" % (d.day, d.strftime("%b"))


def _rows(h, px):
    return re.findall(r'<div class="%s-u %s-sr">(.*?)</div>' % (px, px), h)


def _pct(p):
    """A share as the page prints it (srP): ROUNDED DOWN — 2 decimals under 1% and in the last 0.1 point under the
    release share, else 1; trailing zeros dropped; above 0 but under 0.01% → '<0.01%'."""
    v = p * 100
    if v <= 0:
        return "0%"
    if v < 0.01:
        return "<0.01%"
    th = eng.RELEASE_SHARE * 100
    k = 2 if (v < 1 or th - 0.1 <= v < th) else 1
    t = "%.*f" % (k, math.floor(v * 10 ** k + 1e-6) / 10 ** k)
    return (t.rstrip("0").rstrip(".") if "." in t else t) + "%"


def _upd_head(h, px):
    return re.findall(r'<div class="%s-eyebrow">(📦 Updates · [^<]*)</div>' % px, h)


NOTE = ("Staged rollout = naya version jo 5% users tak nahi pahuncha, par kam se kam 3 din 50+ users pe chala. Nahi "
        "dikhate: isse kam users ya din wale (test build / testers), naam me test / debug / qa / internal wale (test "
        "build) aur data ke pehle din se maujood version (unki shuruaat data se pehle ki). Asar tab napte hain jab ye 5% "
        "tak pahunche — tab ye normal update ban jata hai.")


def test_both_studios_show_the_staged_rollout_rows(report, sites):
    on = report["on"]
    srl = {a["id"]: a["srl"][0] for a in _gz(os.path.join(sites["on"][1], asb.FILE))["apps"] if a.get("srl")}
    t, g, n = srl[ss.T1], srl[ss.G1], srl[ss.N1]
    live = "— asar napne layak users nahi, 5% par pahunchte hi asar dikhega"
    want = {ss.T1: "%s v9.9.1 Staged rollout abhi sirf %s users tak (max %s) %s" % (_fd(ROLL), _pct(t[3]), _pct(t[2]), live),
            ss.N1: "%s v9.9.5 Staged rollout abhi sirf %s users tak (max %s) %s" % (_fd(ROLL_N), _pct(n[3]), _pct(n[2]), live),
            # a newer update replaced it: its tail of users is no "abhi sirf" (not live), the day the newer one came
            ss.G1: "%s v9.9.3 Staged rollout max %s users tak pahuncha, 5%% tak nahi — asar napne layak users nahi the · "
                   "%s ko naya update aa gaya" % (_fd(HALT), _pct(g[2]), _fd(G1_REL))}
    for px in ("as", "us"):
        for kind in ("d", "p"):
            for aid, w in want.items():
                h = on[px]["%s:%s" % (kind, aid)]
                assert [_text(r) for r in _rows(h, px)] == [w], (px, kind, aid)
                note = re.findall(r'<div class="%s-faint %s-srn">(.*?)</div>' % (px, px), h)   # the rule, once, under
                assert [_text(x) for x in note] == [NOTE], (px, kind, aid)                     # the rows
                assert "9.9.2" not in h and "9.9.4-test" not in h                 # the test builds: nowhere
            # date order with the updates, newest first — an older rollout below the update (Demo Photos: 2.1 at E−17
            # above 9.9.3 at E−25), a NEWER one above it (Demo Notes: 9.9.5 at E−8 above 3.1 at E−40)
            g1, n1 = on[px]["%s:%s" % (kind, ss.G1)], on[px]["%s:%s" % (kind, ss.N1)]
            assert g1.index("<b>v2.1</b>") < g1.index("<b>v9.9.3</b>"), (px, kind)
            assert n1.index("<b>v9.9.5</b>") < n1.index("<b>v3.1</b>"), (px, kind)
    # the Uninstall app page's Update impact section: its "7 din pehle → 7 din baad" line only over real updates
    line = "Uninstalls per day — 7 din pehle → 7 din baad"
    assert line in on["us"]["p:" + ss.G1] and line not in on["us"]["p:" + ss.T1] and _rows(on["us"]["p:" + ss.T1], "us")
    # the header: the honest count, "since" the oldest row shown
    for px in ("as", "us"):
        assert "📦 Updates · 1 staged rollout · since %s" % _fd(ROLL) in _upd_head(on[px]["d:" + ss.T1], px)
        assert "📦 Updates · all 1 (+1 staged rollout) · since %s" % _fd(HALT) in _upd_head(on[px]["d:" + ss.G1], px)
        assert "📦 Updates · all 1 (+1 staged rollout) · since %s" % _fd(REL_N) in _upd_head(on[px]["d:" + ss.N1], px)
    for v in on.values():                              # Roman-script Hinglish, no broken numbers
        for h in v.values():
            assert not DEVA.search(_text(h)) and "NaN" not in h and "undefined" not in h


def _upd_line(h):
    m = re.findall(r'<div class="card" id="act-impact"[^>]*>(.*?)</div>', h, re.S)
    return [_text(x) for x in m]


def test_the_old_views_update_line_names_a_newer_staged_rollout(report, sites):
    """The Active users app page's '🗂 Old views' line ("Is app ka aakhri update …" / "… koi update nahi") says a staged
    rollout that came after that update (with none: one within the list's days) — never "the latest" while a newer
    version is out; the older rollout (Demo Photos' 9.9.3, before its 2.1) is not repeated there."""
    on, off = report["on"], report["off"]
    uni = {a["app_id"]: a for a in _gz(os.path.join(sites["on"][1], "uninstall.json.gz"))["apps"]}
    t, n = uni[ss.T1]["small_rollouts"][0], uni[ss.N1]["small_rollouts"][0]
    (lt,), (ln,), (lg,) = (_upd_line(on["as"]["p:" + a]) for a in (ss.T1, ss.N1, ss.G1))
    assert lt == ("📦 Pichhle 60 din me koi update nahi · staged rollout v9.9.1 (%s, abhi %s users tak) — normal update "
                  "nahi bana, iska asar nahi napa" % (_fd(ROLL), _pct(t["last_share"])))
    assert ln.startswith("📦 Is app ka aakhri update: v3.1 (%s)" % _fd(REL_N)) and ln.endswith(
        "Full card in Uninstall › · baad me staged rollout v9.9.5 (%s, abhi %s users tak) — normal update nahi bana, iska "
        "asar nahi napa" % (_fd(ROLL_N), _pct(n["last_share"])))
    assert lg.startswith("📦 Is app ka aakhri update: v2.1") and "staged rollout" not in lg
    for a in (ss.T1, ss.N1, ss.G1):                    # without the rows: the line as before
        (x,) = _upd_line(off["as"]["p:" + a])
        assert "staged rollout" not in x
    assert _upd_line(off["as"]["p:" + ss.T1]) == ["📦 Pichhle 60 din me koi update nahi"]
    assert _upd_line(off["as"]["p:" + ss.N1])[0] == ln.split(" · baad me staged rollout")[0]


def test_the_rows_at_the_edges_of_the_rule(report):
    """Made-up Studio rows (variant "edge"): a share just under the release share never reads as it (4.996% → 4.99%), a
    tiny share reads '<0.01%' (not 0%), a rollout with an update surge during it says that row measured it (no
    "nothing measurable"), and a later update is named."""
    ed = report["edge"]
    r = {x[1]: x for x in _edge_rows()}
    d = lambda k: _fd(END - timedelta(days=k))                                 # noqa: E731
    want = ["%s v9.9.7 Staged rollout abhi sirf 4.99%% users tak (max 4.99%%) — asar napne layak users nahi, 5%% par "
            "pahunchte hi asar dikhega" % d(3),
            "%s v9.9.6 Staged rollout max <0.01%% users tak pahuncha, 5%% tak nahi — asar napne layak users nahi the" % d(20),
            "%s v9.9.5 Staged rollout max 1.2%% users tak pahuncha, 5%% tak nahi — is rollout ke dauran %s ko app update "
            "spike aaya: uska asar us din ki update row me napa gaya · %s ko naya update aa gaya" % (d(30), d(28), d(20))]
    assert _pct(r["v9.9.7"][2]) == "4.99%" and _pct(r["v9.9.6"][2]) == "<0.01%" and _pct(r["v9.9.5"][2]) == "1.2%"
    for px in ("as", "us"):
        for kind in ("d", "p"):
            h = ed[px]["%s:%s" % (kind, EDGE_APP)]
            assert [_text(x) for x in _rows(h, px)] == want, (px, kind)
            assert "5%</" not in h.split('%s-srn' % px)[0].split('Staged rollout')[1]


NZ = re.compile(r'(id="|url\(#|href="#|data-bc=")([A-Za-z_-]*?)\d+')


def _plain(h, px):
    """A rendering with the staged-rollout rows, the rule under them, the header's count and the old-views line's
    rollout note taken out — what the page showed before them (an Updates panel left empty, which only the rollouts
    filled, taken out too); "since" dropped."""
    h = re.sub(r'<div class="%s-u %s-sr">.*?</div>' % (px, px), "", h)
    h = re.sub(r'<div class="%s-faint %s-srn">.*?</div>' % (px, px), "", h)
    h = re.sub(r'📦 Updates · all (\d+) \(\+\d+ staged rollouts?\)', r"📦 Updates · all \1", h)
    h = re.sub(r'(📦 Updates · all \d+) · since [^<]*', r"\1", h)
    h = re.sub(r'<div class="%s-panel"><div class="%s-ph"><div><div class="%s-eyebrow">📦 Updates · \d+ staged rollouts?'
               r'( · since [^<]*)?</div>.*?<div class="%s-upd"></div></div>' % (px, px, px, px), "", h)
    h = h.replace('<div class="%s-upd"></div>' % px, "")      # (the app page's Update impact section: the same)
    h = re.sub(r' · <span class="faint">(?:baad me )?staged rollout <b[^>]*>[^<]*</b> \([^)]*\) — normal update nahi '
               r'bana(?:, iska asar nahi napa)?</span>', "", h)
    return NZ.sub(r"\1\2#", h)


def test_nothing_else_changes_on_the_page(report):
    on, off = report["on"], report["off"]
    for px in ("as", "us"):
        assert sorted(on[px]) == sorted(off[px])
        for k in on[px]:
            if not any(k.endswith(a) for a in SRL_APPS):
                assert NZ.sub(r"\1\2#", on[px][k]) == NZ.sub(r"\1\2#", off[px][k]), (px, k)   # no rollout: as before
            else:
                assert _plain(on[px][k], px) == _plain(off[px][k], px), (px, k)
            assert not re.search(r'%s-sr"|%s-roll"|%s-srn"|Staged rollout<| staged rollouts?\b(?! rok)' % (px, px, px),
                                 off[px][k])
