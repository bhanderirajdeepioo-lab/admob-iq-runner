"""📦 Compare any date (engine.impact_any + admob_iq.impact_any_build) — synthetic stores only (tests.uninstall_synth):
a chosen date is the engine's own pseudo-release (parity with the update card, an injected update on ANY date, the
fast returning-DAU memos byte-identical to the engine's), complete / early / running windows near today, the real
updates inside a window as notes, the file's contract (decode) and size, failure isolation, the input-signature cache
and the time budget, and the IMPACT_ANY switch (off: the site exactly as without it, nothing alerted)."""

import copy
import gzip
import json
import os
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq import impact_any_build as iab
from admob_iq.engine import impact as imp
from admob_iq.engine import impact_any as ia
from admob_iq.engine import uninstall as eng
from tests.test_impact_windows import _stores
from tests.uninstall_synth import END, make_impact_store, rollout

NOW = "2026-09-21T01:00:00Z"


def ctx(st, rv, E=END, fast=True):
    return ia.setup(dict(st, window_end=E.isoformat()), rv, 7, fast=fast)


def run_dates(st, rv, E=END, dates=None, fast=True):
    c = ctx(st, rv, E, fast)
    return c, dict(ia.each_date(c, "a", dates))


def engine(st, rv, E=END, rels_fn=None):
    """The engine's own impact_app on a first evaluation (fresh state) → {date: block}; rels_fn edits its releases."""
    store, ds, cd, whole, i0, rels, E, late = ia.prepare(dict(st, window_end=E.isoformat()), 7)
    if rels_fn:
        rels = rels_fn(rels)
    detail, _, _ = imp.impact_app(store, ds, cd, whole, i0, rels, rv, {}, "a", E, late, True, True, False, NOW)
    return {b["date"]: b for b in detail["updates"]}


def _w(W):
    W = copy.deepcopy(W)
    for k in ("late", "told", "told_by"):
        W["verdict"].pop(k, None)
    return W


def surge_store(days=260, surges=(), noise=0.03, seed=7, **kw):
    """An app whose updates are app_update surges (kind "update": no version, After from the day after)."""
    ds = set(surges)
    return make_impact_store(days, upd=lambda d: 6000 if d in ds else 300, noise=noise, seed=seed, noise_ar=0.9, **kw)


SURGES = tuple(END - timedelta(days=d) for d in (150, 95, 61, 40, 33, 12))


# ── 1. parity: a release date is the engine's own release card ────────────────────────────────────────────────────

def test_every_update_surge_date_is_byte_identical_to_the_engines_release_card():
    st, rv = surge_store(surges=SURGES, ipu=lambda d, v: 3.5 if d >= END - timedelta(days=60) else 4.0)
    eb = engine(st, rv)
    assert [b["kind"] for b in eb.values()] == ["update"] * 6
    c, res = run_dates(st, rv, dates={date.fromisoformat(k) for k in eb})
    n = 0
    for day, b in eb.items():
        r = res[date.fromisoformat(day)]
        assert r["same"] == [{"key": b["key"], "label": b["label"], "date": day}]
        assert r["7"]["windows"] == b["windows"] and r["7"]["rows"] == b["rows"], day
        assert r["7"]["verdict"] == b["verdict"] and r["7"]["notes"] == b["notes"], day
        for N, W in b["by_window"].items():
            assert r[N] == _w(W), (day, N)
            n += 1
    assert n == 18


@pytest.mark.parametrize("i", range(7))
def test_every_version_update_shares_its_rows_with_the_custom_date_when_its_after_window_starts_the_day_after(i):
    # a version's After starts once half the users run it (a0 ≥ R + 1): when that is R + 1, every row of every
    # window is the release's; later, the windows differ by design (the injected-update test covers those dates)
    st, rv = list(_stores())[i]
    eb = engine(st, rv)
    c, res = run_dates(st, rv, dates={date.fromisoformat(k) for k in eb})
    same = shifted = 0
    for day, b in eb.items():
        X = date.fromisoformat(day)
        if X not in res:                              # (before the candidate range: launch + 7)
            continue
        r = res[X]
        if b["windows"]["after"]["from"] != (X + timedelta(days=1)).isoformat():
            shifted += 1
            continue
        same += 1
        assert r["7"]["windows"]["before"] == b["windows"]["before"]
        assert r["7"]["rows"] == b["rows"], day
        for N, W in b["by_window"].items():
            assert r[N]["rows"] == W["rows"] and r[N]["after"] == W["after"] and r[N]["state"] == W["state"], (day, N)
    assert same + shifted == sum(1 for k in eb if date.fromisoformat(k) in res)


@pytest.mark.parametrize("make", ["surges", "versions", "young"])
def test_any_date_equals_the_engine_with_an_update_injected_on_that_date(make):
    if make == "surges":
        st, rv = surge_store(surges=(END - timedelta(days=70), END - timedelta(days=20)))
    elif make == "versions":
        st, rv = list(_stores())[6]
    else:
        st, rv = make_impact_store(90, versions=rollout("1.0", [(END - timedelta(days=40), "1.1", 0.6)]), noise=0.02)
    c = ctx(st, rv)
    real = {date.fromisoformat(r["date"]) for r in ia.prepare(dict(st, window_end=END.isoformat()), 7)[5]}
    lo, hi = c["rng"]
    picks = [X for X in (lo, lo + timedelta(days=9), END - timedelta(days=95), END - timedelta(days=64),
                         END - timedelta(days=45), END - timedelta(days=31), END - timedelta(days=18),
                         END - timedelta(days=9), END - timedelta(days=4), hi)
             if lo <= X <= hi and all(abs((X - R).days) > imp.CHAIN_DAYS for R in real)]
    assert len(picks) >= 5
    res = dict(ia.each_date(c, "a", set(picks)))
    for X in picks:
        def inject(rels, X=X):
            return sorted(rels + [{"date": X.isoformat(), "version": None, "kind": "update"}],
                          key=lambda r: (r["date"], r["kind"], r["version"] or ""))
        b = engine(st, rv, rels_fn=inject)[X.isoformat()]
        r = res[X]
        assert (r["7"]["windows"], r["7"]["rows"], r["7"]["verdict"], r["7"]["notes"]) == \
            (b["windows"], b["rows"], b["verdict"], b["notes"]), X
        for N, W in b["by_window"].items():
            assert r[N] == _w(W), (X, N)


def _stress():
    yield from _stores()
    yield surge_store(surges=(END - timedelta(days=80),))
    # missing return cohorts (imputed old-users level), no cohorts at all (raw), a launch / growth phase (steep)
    yield make_impact_store(200, versions=rollout("1.0", [(END - timedelta(days=60), "2.0", 0.6)]), noise=0.03, seed=2,
                            noise_ar=0.9, ret_ok=lambda c: c.toordinal() % 5 != 0)
    yield make_impact_store(200, versions=rollout("1.0", [(END - timedelta(days=60), "2.0", 0.6)]), noise=0.03, seed=3,
                            ret_ok=lambda c: False)
    yield make_impact_store(160, old=lambda d: 2000 * 1.4 ** ((d - (END - timedelta(days=159))).days / 7), noise=0.02,
                            versions=rollout("1.0", [(END - timedelta(days=30), "2.0", 0.6)]))


@pytest.mark.parametrize("i", range(11))
def test_the_fast_returning_dau_memos_give_the_engines_exact_floats_on_every_date(i):
    st, rv = list(_stress())[i]
    a = {X.isoformat(): r for X, r in run_dates(st, rv, fast=False)[1].items()}
    b = {X.isoformat(): r for X, r in run_dates(st, rv, fast=True)[1].items()}
    assert a and json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def test_prepare_hands_the_engine_exactly_what_evaluate_app_does(monkeypatch):
    st, rv = list(_stores())[1]
    store = dict(st, window_end=END.isoformat())
    got = {}
    real = imp.impact_app

    def spy(*a, **k):
        got["a"] = copy.deepcopy(a)                   # (as handed over: evaluate_app goes on using them)
        return real(*a, **k)
    monkeypatch.setattr(imp, "impact_app", spy)
    eng.evaluate_app(copy.deepcopy(store), "a", "App", {}, NOW, revenue=rv)
    s, ds, cd, whole, i0, rels, E, late = ia.prepare(copy.deepcopy(store), eng.LATE_DAYS)
    a = got["a"]
    memo = {k for k in a[1] if k.startswith("_")}                        # (the uninstall engine's own memos: "_expect")
    assert (s, ds, cd, whole, i0, rels) == (a[0], {k: v for k, v in a[1].items() if k not in memo}) + a[2:6]
    assert (E, late) == (a[9], a[10])


# ── 2. windows near today: complete, early, running — never faked ──────────────────────────────────────────────────

def test_dates_near_today_carry_the_engines_pending_early_and_running_states():
    st, rv = list(_stores())[6]
    c, res = run_dates(st, rv)
    lo, hi = c["rng"]
    assert hi == END - timedelta(days=1) and lo == END - timedelta(days=ia.HISTORY_DAYS) and len(res) == 365
    last = res[hi]                                   # nothing settled yet: every row pending, ready_on said
    assert last["7"]["windows"]["after"]["settled"] == 0 and last["7"]["verdict"]["level"] is None
    assert last["7"]["verdict"]["early"] and all(r["status"] == "pending" for r in last["7"]["rows"].values())
    assert all(r["ready_on"] for k, r in last["7"]["rows"].items())
    for N in ("14", "30", "60"):
        W = last[N]
        assert W["state"] == "running" and W["verdict"]["ready_on"] == W["after"]["judged_on"]
        assert all(r["status"] in ("pending", "na") for r in W["rows"].values())
    early = res[END - timedelta(days=8)]             # 5 settled days: judged early (Z_EARLY), D7 not in yet
    assert early["7"]["windows"]["after"]["settled"] == 5 and early["7"]["verdict"]["early"]
    assert early["7"]["rows"]["new_d7"]["status"] == "pending"
    done = res[END - timedelta(days=20)]             # complete 7 days, D7 in: final; its 14 days still running
    assert done["7"]["verdict"]["final"] and done["14"]["state"] == "running"
    old = res[END - timedelta(days=100)]
    assert all(old[N]["state"] == "final" for N in ("14", "30", "60")) and old["7"]["verdict"]["final"]
    body = ia.build_app(dict(st, window_end=END.isoformat()), rv, "a", "0" * 12, "s", 7)[0]
    for X in (hi, END - timedelta(days=8), END - timedelta(days=20), END - timedelta(days=100)):
        d = ia.decode(body, X)
        assert d["7"]["verdict"]["final"] == res[X]["7"]["verdict"]["final"]
        assert [d[N]["state"] for N in ("14", "30", "60")] == [res[X][N]["state"] for N in ("14", "30", "60")]
    assert ia.decode(body, END) is None and ia.decode(body, lo - timedelta(days=1)) is None


def test_the_first_date_is_a_launched_week_and_a_young_long_window_says_so():
    st, rv = make_impact_store(50, noise=0.02)
    c, res = run_dates(st, rv)
    assert c["rng"][0] == c["cx"]["launch"] + timedelta(days=7) and c["rng"][1] == END - timedelta(days=1)
    W = res[c["rng"][0]]["60"]
    assert W["verdict"]["level"] is None and all(r["status"] == "na" for r in W["rows"].values())
    body = ia.build_app(dict(st, window_end=END.isoformat()), rv, "a", "0" * 12, "s", 7)[0]
    why = ia.decode(body, c["rng"][0])["60"]["verdict"]["why"]
    assert why.startswith("Ye date app launch ke ") and "Update" not in why


# ── 3. a real update inside a window: its note, as the engine says it for a release ───────────────────────────────

def test_an_update_inside_the_windows_is_cut_by_overlap_and_mixed_as_for_a_release():
    R = END - timedelta(days=40)
    st, rv = surge_store(surges=(R,))
    body = ia.build_app(dict(st, window_end=END.isoformat()), rv, "a", "0" * 12, "s", 7)[0]
    up = [u for u in body["updates"] if u["date"] == R.isoformat()]
    assert up == [{"key": "upd@%s" % R.isoformat(), "label": "App update", "date": R.isoformat()}]
    cut = ia.decode(body, R - timedelta(days=4))["7"]         # the update 4 days after: the 7-day After stops before it
    assert cut["cut_by"]["date"] == R.isoformat() and cut["after"]["to"] == (R - timedelta(days=1)).isoformat()
    assert cut["after"]["days"] == 3 and "cut_by_next" in cut["notes"]
    assert ia.decode(body, R - timedelta(days=2))["7"]["verdict"]["why"] == imp.NA_CUT       # 1 day left: no card
    ov = ia.decode(body, R + timedelta(days=3))["7"]
    assert ov["overlap_before"]["label"] == "App update" and "before_overlap" in ov["notes"]
    mx = ia.decode(body, R - timedelta(days=10))
    assert [u["date"] for u in mx["14"]["mixed"]] == [R.isoformat()] and "mixed" in mx["14"]["notes"]
    if mx["14"]["state"] != "running":
        assert mx["14"]["verdict"]["why"].endswith(" · mila-jula (beech me 1 update)")
    mb = ia.decode(body, R + timedelta(days=10))
    assert [u["date"] for u in mb["30"]["mixed_before"]] == [R.isoformat()] and "mixed_before" in mb["30"]["notes"]
    same = ia.decode(body, R)
    assert [u["date"] for u in same["same"]] == [R.isoformat()] and same["7"]["cut_by"] is None


def test_custom_dates_never_say_update_or_rollout_in_their_texts():
    st, rv = list(_stores())[6]
    body = ia.build_app(dict(st, window_end=END.isoformat()), rv, "a", "0" * 12, "s", 7)[0]
    assert body["text"]
    for t in body["text"]:
        assert "rollout" not in t and "pdate se" not in t and "Update app" not in t and " aur update" not in t, t
    assert ia.custom_text(imp.LOW_NULL) == imp.LOW_NULL.replace("Update se pehle", "Is date se pehle")
    assert ia.custom_text("Koi pakka farak nahi — rollout chalne do") == "Koi pakka farak nahi"


# ── 4. the file: contract and size ────────────────────────────────────────────────────────────────────────────────

def test_decode_gives_every_date_back_as_the_engine_said_it_within_the_files_rounding():
    st, rv = list(_stores())[5]
    store = dict(st, window_end=END.isoformat())
    body = ia.build_app(store, rv, "a", "ab" * 6, "sig", 7)[0]
    raw = json.loads(json.dumps(body))                                   # (what the page gets: JSON only)
    _, res = run_dates(st, rv)
    assert raw["n"] == len(res) and raw["first"] == min(res).isoformat() and raw["last"] == max(res).isoformat()
    tol = {"users": 0.5, "pct": 5e-5, "num": 5e-3, "sec": 0.5, "usd1k": 5e-4}
    for X, r in res.items():
        d = ia.decode(raw, X)
        assert d["same"] == r["same"]
        for N in ("7", "14", "30", "60"):
            E, G = r[N], d[N]
            ev = E["verdict"]
            gw = E["windows"] if N == "7" else E
            assert G["after"]["to"] == gw["after"]["to"] and G["after"]["settled"] == gw["after"]["settled"]
            assert G["before"]["from"] == gw["before"]["from"] and G["before"]["to"] == gw["before"]["to"]
            assert (G["verdict"]["level"], G["verdict"]["final"], G["verdict"]["early"], G["verdict"]["ready_on"]) == \
                (ev["level"], ev["final"], ev["early"], ev["ready_on"]), (X, N)
            assert G["verdict"]["why"] == ia.custom_text(ev["why"])
            for k in ("worse", "better", "pending"):
                assert G["verdict"][k] == ev[k], (X, N, k)
            assert G["notes"] == E["notes"] and G["state"] == E.get("state")
            for k, er in E["rows"].items():
                gr = G["rows"][k]
                st_ = er.get("status", "na")
                assert gr["status"] == st_ and gr["reason"] == ia.custom_text(er.get("reason")), (X, N, k)
                assert gr["ready_on"] == er.get("ready_on") and gr["sp"] == er.get("sp"), (X, N, k)
                assert gr["basis"] == er.get("basis", imp.BASIS_LONG[imp.UNIT[k]]), (X, N, k)
                for f in ("before", "after", "expected", "after_prov"):
                    if er.get(f) is None:
                        assert gr[f] is None, (X, N, k, f)
                    else:
                        assert abs(gr[f] - er[f]) <= tol[imp.UNIT[k]] + 1e-9, (X, N, k, f)
                for f in ("change", "need"):
                    if er.get(f) is None:
                        assert gr[f] is None
                    else:
                        assert abs(gr[f] - er[f]) <= (5e-3 if imp.UNIT[k] == "pct" else 5e-4) + 1e-9, (X, N, k, f)
                assert gr["est"] == bool(er.get("est")) and gr["n_after"] == (er.get("n_after") or 0)
                for f in ("from_b", "to_b", "from_a", "to_a"):
                    if er.get(f) is not None:
                        assert gr[f] == er[f], (X, N, k, f)
                for short, ek, dp in ia.EXTRA[k]:
                    v = (er.get("extra") or {}).get(ek)
                    if v is not None and not (ek == "imputed_share" and round(v, 3) == 0):
                        assert abs(gr["extra"][ek] - v) <= 0.5 * 10 ** -dp + 1e-9, (X, N, k, ek)


def test_a_live_shaped_app_keeps_its_file_under_150_kb_gzipped():
    # 520 days, an update every 10 days (many Mixed), noisy AR days, ad revenue moving: a year of dates × 4 windows
    rels = [(END - timedelta(days=40 + 10 * i), "3.%d" % i, 0.6) for i in range(30)]
    st, rv = make_impact_store(520, versions=rollout("1.0", sorted(rels)), noise=0.03, seed=5, noise_ar=0.9,
                               ipu=lambda d, v: 4.0 * (0.9 if v == "3.3" else 1.0))
    body = ia.build_app(dict(st, window_end=END.isoformat()), rv, "a", "0" * 12, "s", 7)[0]
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    assert body["n"] == 365 and len(gzip.compress(raw, 9)) <= 150000, len(gzip.compress(raw, 9))


# ── 5. the build step: switch, isolation, cache, budget ───────────────────────────────────────────────────────────

from tests.test_uninstall_build import A1, A2, A6, run, seed  # noqa: E402
from tests.test_uninstall_build import ga4_settings as _gs  # noqa: E402


def ga4_settings(**kw):
    """The Uninstall build's test settings with the feature ON (tests/conftest.py: off for every other test)."""
    return _gs(**dict({"impact_any": True}, **kw))


@pytest.fixture
def isite(tmp_path, monkeypatch):
    """The Uninstall build's synthetic site, its stores carrying update-impact data (42 days: the any-date step has
    dates to build)."""
    from admob_iq.fetch import ga4_uninstall as gu
    from tests import test_uninstall_build as tub
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    seed(data)
    for i, aid in enumerate((A1, A2, A6)):
        st, _ = make_impact_store(80, versions=rollout("1.0", [(END - timedelta(days=30), "1.1", 0.6)]), noise=0.02,
                                  seed=i + 1, app_id=aid)
        st.update(property_id=tub.PID, stream_id=tub.SID, package=tub.PKG[aid])
        gu.save_store(gu.store_path(data, aid), st)
    monkeypatch.setattr(gu, "refresh_all", lambda *a, **k: copy.deepcopy(tub.STATUS))
    return data, out


def _snap(out, data):
    files = {}
    for tag, root in (("site", out), ("data", os.path.join(data, "ga4_uninstall"))):
        for n in sorted(os.listdir(root)):
            if not n.startswith("impact_any_"):
                files[tag + "/" + n] = open(os.path.join(root, n), "rb").read()
    return files


def test_the_switch_off_leaves_every_output_as_without_the_feature_and_nothing_is_ever_alerted(tmp_path, isite,
                                                                                                capsys):
    import shutil
    data, out = isite
    d0 = str(tmp_path / "data0")
    shutil.copytree(data, d0)
    dash_on, files_on = run(data, out, ga4_settings(impact_any=True))
    log_on = capsys.readouterr().err
    extra_on = build_static._impact_any_tail(out)                         # (build_static.build, right after the step)
    assert capsys.readouterr().err.startswith("impact any: apps 3, built 3,") and extra_on == ["/impact_any_*"]
    names = sorted(os.listdir(out))
    feat = [n for n in names if n.startswith("impact_any_")]
    assert "impact_any_index.json.gz" in feat and len(feat) == 4
    out0 = str(tmp_path / "site0")
    dash_off, files_off = run(d0, out0, ga4_settings(impact_any=False))
    log_off = capsys.readouterr().err
    assert not [n for n in os.listdir(out0) if n.startswith("impact_any_")]
    assert dash_on == dash_off and log_on == log_off and files_on == files_off     # the Uninstall step: as it was
    on, off = _snap(out, data), _snap(out0, d0)
    assert on.keys() == off.keys()
    for k in on:                                                          # site + private state (nothing alerted)
        assert on[k] == off[k], k
    assert build_static._impact_any_tail(out0) == [] and capsys.readouterr().err == ""
    h_on = build_static.headers_text(files_on, dash_on, extra=extra_on)
    rule = "/impact_any_*\n  Cache-Control: no-store\n\n"
    assert rule in h_on and h_on.replace(rule, "") == build_static.headers_text(files_off, dash_off)
    run(data, out, ga4_settings(impact_any=False))                        # switched off later: its files go
    assert not [n for n in os.listdir(out) if n.startswith("impact_any_")]
    assert iab.pop_line() is None


def test_the_step_writes_one_file_per_app_an_index_and_one_counts_line_through_build_static(isite, capsys):
    data, out = isite
    dash, files = run(data, out, ga4_settings())
    assert capsys.readouterr().err.count("\n") == 1                     # run_uninstall itself: its one line
    with gzip.open(os.path.join(out, iab.INDEX), "rt", encoding="utf-8") as f:
        idx = json.load(f)
    assert idx["v"] == 1 and idx["file_v"] == ia.V and idx["windows"] == [7, 14, 30, 60]
    from admob_iq.fetch import ga4_uninstall as gu
    keys = {r["app_id"]: gu.file_key(r["app_id"]) for r in dash["uninstall"]["apps"]}
    assert sorted(a["app_id"] for a in idx["apps"]) == sorted(keys)
    for a in idx["apps"]:
        assert a["file"] == "impact_any_%s.json.gz" % keys[a["app_id"]] and a["fresh"] is True
        body = ia.read_head(os.path.join(out, a["file"]))
        assert (body["first"], body["last"], body["n"]) == (a["first"], a["last"], a["dates"])
        assert body["data_till"] == a["data_till"] == END.isoformat()
        assert a["settled_till"] == (END - timedelta(days=imp.ACT_LATE_DAYS)).isoformat()
    line = iab.pop_line()
    assert line == "impact any: apps 3, built 3, kept 0, stale 0, pending 0, failed 0, dates %d, failed windows 0" % (
        sum(a["dates"] for a in idx["apps"]))
    assert iab.pop_line() is None
    for s in ("@", "property", "987654321", "5550001234"):
        assert s not in line


def test_an_unchanged_app_keeps_its_file_byte_for_byte_and_a_new_store_or_code_rebuilds_it(isite, monkeypatch):
    from admob_iq.fetch import ga4_uninstall as gu
    data, out = isite
    run(data, out, ga4_settings())
    iab.pop_line()
    f = os.path.join(out, sorted(n for n in os.listdir(out) if iab.FILE_RE.match(n))[0])
    st0 = os.stat(f).st_mtime_ns
    called = []
    real = ia.build_app
    monkeypatch.setattr(ia, "build_app", lambda *a, **k: called.append(1) or real(*a, **k))
    run(data, out, ga4_settings())
    assert called == [] and os.stat(f).st_mtime_ns == st0
    assert iab.pop_line().startswith("impact any: apps 3, built 0, kept 3,")
    p = gu.store_path(data, A1)                                          # GA4 fetched again for one app
    st = gu.load_store(p)
    st["daily"][END.isoformat()]["a1"] += 50
    gu.save_store(p, st)
    run(data, out, ga4_settings())
    assert len(called) == 1 and iab.pop_line().startswith("impact any: apps 3, built 1, kept 2,")
    monkeypatch.setattr(ia, "code_sig", lambda: "new-code")              # an engine change: every app again
    run(data, out, ga4_settings())
    assert len(called) == 4


def test_past_its_budget_an_app_keeps_its_older_file_or_waits_and_the_next_build_goes_on(isite):
    from admob_iq.fetch import ga4_uninstall as gu
    data, out = isite
    tiny = 1e-9                                                          # past it after the first app built
    run(data, out, ga4_settings(impact_any_budget_sec=tiny))
    assert iab.pop_line().startswith("impact any: apps 3, built 1, kept 0, stale 0, pending 2,")
    with gzip.open(os.path.join(out, iab.INDEX), "rt", encoding="utf-8") as f:
        idx = json.load(f)
    assert sorted(bool(a.get("pending")) for a in idx["apps"]) == [False, True, True]
    assert all(a["file"] is None for a in idx["apps"] if a.get("pending"))
    run(data, out, ga4_settings(impact_any_budget_sec=tiny))
    assert iab.pop_line().startswith("impact any: apps 3, built 1, kept 1, stale 0, pending 1,")
    run(data, out, ga4_settings())
    assert iab.pop_line().startswith("impact any: apps 3, built 1, kept 2,")
    for aid in (A1, A2, A6):                                              # every store new, a tight budget
        p = gu.store_path(data, aid)
        st = gu.load_store(p)
        st["daily"][END.isoformat()]["a1"] += 5
        gu.save_store(p, st)
    run(data, out, ga4_settings(impact_any_budget_sec=tiny))
    assert iab.pop_line().startswith("impact any: apps 3, built 1, kept 0, stale 2, pending 0,")
    with gzip.open(os.path.join(out, iab.INDEX), "rt", encoding="utf-8") as f:
        idx = json.load(f)
    assert sorted(a["fresh"] for a in idx["apps"]) == [False, False, True]
    assert all(os.path.exists(os.path.join(out, a["file"])) for a in idx["apps"])


def test_a_crash_costs_only_that_apps_file_and_a_window_crash_only_that_window(isite, monkeypatch):
    data, out = isite
    real = ia.build_app
    calls = []

    def boom(store, rev, app_id, *a, **k):
        calls.append(app_id)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real(store, rev, app_id, *a, **k)
    monkeypatch.setattr(ia, "build_app", boom)
    dash, files = run(data, out, ga4_settings())
    assert dash["uninstall"]["status"] and len(dash["uninstall"]["apps"]) == 3
    assert iab.pop_line().startswith("impact any: apps 3, built 2, kept 0, stale 0, pending 0, failed 1,")
    with gzip.open(os.path.join(out, iab.INDEX), "rt", encoding="utf-8") as f:
        assert len(json.load(f)["apps"]) == 2
    monkeypatch.setattr(ia, "build_app", real)
    st, rv = list(_stores())[0]
    real_lw = imp._long_window

    def lw(cx, blk, blocks, j, N, *a, **k):
        if N == 30:
            raise ValueError("x")
        return real_lw(cx, blk, blocks, j, N, *a, **k)
    monkeypatch.setattr(imp, "_long_window", lw)
    body, failed = ia.build_app(dict(st, window_end=END.isoformat()), rv, "a", "0" * 12, "s", 7)
    assert failed == body["n"] and "lv" not in body["w"]["30"]
    d = ia.decode(body, END - timedelta(days=40))
    assert set(d) == {"date", "same", "7", "14", "60"}
    monkeypatch.setattr(imp, "_long_window", real_lw)
    real_ed = ia.evaluate_date

    def ed(cx, blocks, X, *a, **k):
        if X == END - timedelta(days=40):
            raise ZeroDivisionError
        return real_ed(cx, blocks, X, *a, **k)
    monkeypatch.setattr(ia, "evaluate_date", ed)
    body, failed = ia.build_app(dict(st, window_end=END.isoformat()), rv, "a", "0" * 12, "s", 7)
    assert failed == 1 and ia.decode(body, END - timedelta(days=40)) == {"date": (END - timedelta(days=40)).isoformat(),
                                                                         "same": []}
    assert "7" in ia.decode(body, END - timedelta(days=41))


def test_the_input_signature_reads_only_the_revenue_a_ga4_day_can_touch():
    E = END
    rv = {"tz": "America/Los_Angeles", "currency": "USD", "till": (E + timedelta(days=2)).isoformat(),
          "days": {(E - timedelta(days=i)).isoformat(): [1000 * i, 10] for i in range(-2, 30)}}
    a = ia.input_sig("s", rv, E, 7, "c", "Asia/Kolkata")
    later = copy.deepcopy(rv)                         # a GA4 day in IST ends before the Pacific day E does
    later["days"][(E + timedelta(days=1)).isoformat()] = [9, 9]
    later["till"] = (E + timedelta(days=3)).isoformat()
    assert ia.input_sig("s", later, E, 7, "c", "Asia/Kolkata") == a
    for d in (E, E - timedelta(days=20)):
        moved = copy.deepcopy(rv)
        moved["days"][d.isoformat()] = [1, 1]
        assert ia.input_sig("s", moved, E, 7, "c", "Asia/Kolkata") != a
    assert ia.rev_reach(E, "Asia/Kolkata", "America/Los_Angeles") == E      # IST day E ends 11:30 PDT on E
    assert ia.rev_reach(E, "America/Los_Angeles", "Asia/Kolkata") == E + timedelta(days=1)
    assert ia.rev_reach(E, "UTC", "UTC") == E
    for x in ("s2", None):
        assert ia.input_sig(x or "s", rv if x else None, E, 7, "c", "Asia/Kolkata") != a
    assert ia.input_sig("s", rv, E, 3, "c", "Asia/Kolkata") != a
    assert ia.input_sig("s", rv, E, 7, "d", "Asia/Kolkata") != a


def test_the_workflow_passes_the_impact_any_switch(monkeypatch):
    from admob_iq.config import settings
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        y = f.read()
    assert "IMPACT_ANY:           ${{ vars.IMPACT_ANY || 'true' }}" in y
    monkeypatch.setenv("IMPACT_ANY", "false")
    assert settings()["impact_any"] is False
    monkeypatch.delenv("IMPACT_ANY")
    assert settings()["impact_any"] is True and settings()["impact_any_budget_sec"] == iab.BUDGET_SEC


def test_build_static_prints_the_line_after_the_uninstall_step_and_adds_one_no_store_rule(isite, capsys):
    from tests.test_uninstall_build import NOW as UNOW, dashboard
    data, out = isite
    files = build_static._uninstall_step(dashboard(), data, out, ga4_settings(ga4_active=False), now=UNOW)
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and err[0].startswith("ga4 uninstall: ") and files == [f for f in files
                                                                                if not f.startswith("impact_any")]
    assert build_static._impact_any_tail(out) == ["/impact_any_*"]
    assert capsys.readouterr().err.splitlines() == [
        "impact any: apps 3, built 3, kept 0, stale 0, pending 0, failed 0, dates 216, failed windows 0"]
    assert build_static._impact_any_tail(out) == ["/impact_any_*"] and capsys.readouterr().err == ""   # once
    h = build_static.headers_text(files, {}, extra=["/impact_any_*"])
    assert "/impact_any_*\n  Cache-Control: no-store\n\n/index.html" in h
    build_static._uninstall_step(dashboard(), data, out, ga4_settings(ga4_active=False, impact_any=False), now=UNOW)
    assert build_static._impact_any_tail(out) == [] and "impact any" not in capsys.readouterr().err
