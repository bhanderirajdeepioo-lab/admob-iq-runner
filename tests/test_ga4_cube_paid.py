"""⚖️ The cohort cube of Google Ads users only (admob_iq.fetch.ga4_cube_paid), offline against a synthetic GA4
(tests/test_ga4_paid.Server: made-up rows of five first-user channels, two of them paid; no network): MOD is a second
instance of fetch.ga4_cube with its own store folder, client, log label and knobs (users off, the repair off, its own
call / q / refold knobs from GA4_CUBEP_*, everything else the cube's own env) while the base cube's globals never
change; a whole run (refresh_all → step_app: the walk's block read, each day alone, a day GA4 flags split once and
measured by its own total, a day past GA4's row limit split by countries, then by install days, the hot days, q's whole
reads in the app's run and in the history fill) sends EVERY request held to Google Ads users — the paid in-list last
in its filter; every request GA4 itself got, whichever client sent it — and folds exactly the paid users' revenue
into data/ga4_cube_paid/ (the cube's formats, q's whole reads too, no users file), while the base cube on the same GA4
reads everyone, unfiltered, into its own store; a property under Screens' quota floors deferred by the paid cube,
never by the cube; an app GA4 refuses run after run "stuck" on its third failed run; the counts-only log line; the
switches, the stage names and the workflow's repo variables (every GA4_CUBEP_* / GA4_NVRP_* knob the modules read).
The build's wiring (after Screens, the light paid read first): tests/test_uninstall_build.py. SYNTHETIC values only."""
import gzip
import importlib
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_cube as cu
from admob_iq.fetch import ga4_cube_paid as cp
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_nvr_paid as gnp
from admob_iq.fetch import ga4_paid as gp
from admob_iq.fetch import ga4_uninstall as gu
from tests.test_ga4_paid import BETWEEN, SID, Server, held, recording, refuse, serve, unheld

TODAY = date(2026, 10, 13)
NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
HS = TODAY - timedelta(days=20)                     # the made-up apps' GA4 history start
EDGE = TODAY - timedelta(days=cu.FINAL_LAG)         # the newest final day
FLAGGED = HS + timedelta(days=6)                    # GA4 flags dataLossFromOtherRow on every country read holding it
BUSY, CAP = HS + timedelta(days=12), 10             # … and rolls a country read holding this day past CAP rows into
#                                                     "(other)" (its 13 install days × 3 countries: split, then split)
CH = {"Cross-network": 3, "Paid Search": 1, "Organic Search": 2, "Direct": 1, "Unassigned": 1}   # channel weights
CC = {"XA": 3, "XB": 2, "(not set)": 1}             # country weights (made up)
APPS = [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~2", "package": "com.example.beta"},
        {"app_id": "x~3", "package": "com.example.none"}]
KNOBS = ("DIR", "APP", "NAME", "U_ON", "U_USE", "REPAIR_CALLS", "MAX_CALLS", "Q_CALLS", "Q_SEC", "RF_CALLS", "GUARD",
         "BUDGET_SEC")
ENV = ("GA4_CUBEP_REPAIR_CALLS", "GA4_CUBEP_MAX_CALLS", "GA4_CUBEP_Q_CALLS", "GA4_CUBEP_Q_SEC", "GA4_CUBEP_RF_CALLS")


def _days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def ymd(d):
    return d.strftime("%Y%m%d")


def rows():
    """Activity day D × install day X (HS … D) × country × first-user channel: revenue (age + 1) × weights × 1000
    micros, users 10 × weights at age 0 (else the weights)."""
    out = []
    for D in _days(HS, TODAY):
        for L in range((D - HS).days + 1):
            for cc, wc in CC.items():
                for ch, wh in CH.items():
                    out.append({"date": ymd(D), "firstSessionDate": ymd(D - timedelta(days=L)), "countryId": cc,
                                "firstUserDefaultChannelGroup": ch, "platform": "Android", "streamId": SID,
                                "activeUsers": wc * wh * (10 if L == 0 else 1),
                                "totalAdRevenue": (L + 1) * wc * wh * 1000})
    return out


def micros(D, paid=True):
    """Day D's whole revenue in micros — of Google Ads users (paid), else of everyone."""
    n = (D - HS).days + 1
    return 1000 * n * (n + 1) // 2 * sum(CC.values()) * sum(w for c, w in CH.items() if c in gp.PAID or not paid)


def _holds(body, D):
    a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
    return a <= D <= b and "countryId" in _dims(body)


def flag(body):
    return {"dataLossFromOtherRow": True} if _holds(body, FLAGGED) else {}


def cap(body):
    return CAP if _holds(body, BUSY) else None


def _dims(body):
    return [d["name"] for d in body["dimensions"]]


CFG = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}


def _routes(monkeypatch):
    """Two made-up properties (one app each; com.example.none has no GA4), their history from HS."""
    route = {"property_id": "111", "stream_id": SID, "owner": "o"}
    monkeypatch.setattr(cu.gu, "load_state", lambda d: {"routes": {"by_package": {
        "com.example.alpha": route, "com.example.beta": dict(route, property_id="112")}},
        "tz": {"111": "UTC", "112": "UTC"}, "fetch": {}})
    monkeypatch.setattr(cu.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": HS.isoformat()})


def _run(monkeypatch, tmp_path, paid=True, quota=None):
    """refresh_all over two made-up properties (one app each, + one with no GA4) on the synthetic GA4 (every answer
    carrying `quota`, None: no snapshot): the paid module's (its client recording every body) or the base cube's
    (gf.App recording) → (data dir, status, the bodies the client recorded, the Server: what GA4 itself got)."""
    data = str(tmp_path)
    _routes(monkeypatch)
    srv = Server(rows(), flag, cap, quota=quota)
    serve(monkeypatch, srv)
    sent = []
    m = cp.MOD if paid else cu
    monkeypatch.setattr(m, "MAX_CALLS", 200)                            # room for the whole run (the cap: the cube's)
    if paid:
        monkeypatch.setattr(m, "APP", recording(gp.App, sent))
        out = cp.refresh_all(CFG, data, APPS, NOW, clock=lambda: 0.0)
    else:
        monkeypatch.setattr(cu.gf, "App", recording(gf.App, sent))     # (APP None: the cube builds gf.App)
        out = cu.refresh_all(CFG, data, APPS, NOW, clock=lambda: 0.0)
    return data, out, sent, srv


def _load(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _files(root):
    return sorted(os.path.relpath(os.path.join(b, n), root) for b, _, ns in os.walk(root) for n in ns)


# ── the instance ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_instance_its_knobs_and_the_base_cube_untouched(monkeypatch):
    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    m = importlib.reload(cp).MOD
    assert m is not cu and m.__name__ == "admob_iq.fetch._ga4_cube_paid_impl" and m.Cube is not cu.Cube
    assert (m.DIR, m.NAME, m.APP, m.U_ON, m.U_USE) == ("ga4_cube_paid", "ga4 cube paid", gp.App, False, False)
    assert (m.REPAIR_CALLS, m.MAX_CALLS, m.Q_CALLS, m.Q_SEC, m.RF_CALLS) == (0, cu.MAX_CALLS, 120, 20.0, 30)
    assert cp.BUDGET_SEC == m.BUDGET_SEC == cu.BUDGET_SEC and not m._u_fills()
    assert (cu.DIR, cu.APP, cu.NAME) == ("ga4_cube", None, "ga4 cube")     # the base: its own
    assert m.gf is cu.gf and m.Stop is cu.Stop and m.gu is cu.gu           # the same modules under both
    before = {k: getattr(cu, k) for k in KNOBS}
    twin = gp.instance(cu, "admob_iq.fetch._test_cube_twin", DIR="elsewhere", U_ON=not cu.U_ON, Q_CALLS=1)
    try:
        assert {k: getattr(cu, k) for k in KNOBS} == before and twin.DIR == "elsewhere"
    finally:
        sys.modules.pop("admob_iq.fetch._test_cube_twin", None)
    assert cp.log_line({"counts": {"selected": 3}}).startswith("ga4 cube paid: apps 3, with GA4 0, ")
    assert cu.log_line({"counts": {"selected": 3}}).startswith("ga4 cube: apps 3, with GA4 0, ")


def test_its_own_knobs_from_the_environment_the_rest_the_cubes(monkeypatch):
    """GA4_CUBEP_* (read at import; empty = the default) set the paid cube's knobs; the cube's GA4_CUBE_Q_CALLS is never
    its own; any other GA4_CUBE_* setting (here the fold guard) is the cube's for both."""
    g0, q0 = cu.GUARD, cu.Q_CALLS
    try:
        for k, v in zip(ENV, ("4", "9", "7", "3.5", "0")):
            monkeypatch.setenv(k, v)
        monkeypatch.setenv("GA4_CUBE_Q_CALLS", "1")
        monkeypatch.setenv("GA4_CUBE_GUARD", "false")
        m = importlib.reload(cp).MOD
        assert (m.REPAIR_CALLS, m.MAX_CALLS, m.Q_CALLS, m.Q_SEC, m.RF_CALLS, m.GUARD) == (4, 9, 7, 3.5, 0, False)
        assert (cu.GUARD, cu.Q_CALLS) == (g0, q0)                       # (the base read its env at its own import)
        for k in ENV:
            monkeypatch.setenv(k, "")                                   # empty: the defaults
        m = importlib.reload(cp).MOD
        assert (m.REPAIR_CALLS, m.MAX_CALLS, m.Q_CALLS, m.Q_SEC, m.RF_CALLS) == (0, cu.MAX_CALLS, 120, 20.0, 30)
    finally:
        for k in ENV + ("GA4_CUBE_Q_CALLS", "GA4_CUBE_GUARD"):
            monkeypatch.delenv(k, raising=False)
        importlib.reload(cp)


def test_the_properties_side_by_side_from_the_environment_reach_the_cube_run(monkeypatch, tmp_path):
    """GA4_CUBEP_WORKERS (read at import; unset / empty: the cube's WORKERS, never below 1) is what refresh_all hands
    the cube's run as its workers — the base cube's own WORKERS never changes."""
    w0 = cu.WORKERS
    try:
        for v, want in (("8", 8), ("", cu.WORKERS), ("0", 1)):
            monkeypatch.setenv("GA4_CUBEP_WORKERS", v)
            m = importlib.reload(cp)
            got = {}

            def run(cfg, data_dir, apps, now, clock, budget=None, workers=None):
                got.update(budget=budget, workers=workers)
                return {"counts": {}, "apps": {}}
            monkeypatch.setattr(m.MOD, "refresh_all", run)
            out = m.refresh_all({}, str(tmp_path), [], budget=33)
            assert (m.WORKERS, got, out["counts"]) == (want, {"budget": 33, "workers": want}, {"stuck": 0})
        assert cu.WORKERS == w0
    finally:
        monkeypatch.delenv("GA4_CUBEP_WORKERS", raising=False)
        importlib.reload(cp)


# ── a whole run ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_run_holds_every_read_to_google_ads_users_and_folds_only_theirs_into_its_own_store(monkeypatch, tmp_path):
    data, out, sent, srv = _run(monkeypatch, tmp_path)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and "error" not in out
    c = out["counts"]
    n_final = (EDGE - HS).days + 1
    assert c["days"] == 2 * n_final and c["calls"] == len(sent) and c["q_days"] > 0 and c["u_kept"] == 0
    assert c["stuck"] == 0
    assert sent and all(held(b) for b in sent)                      # EVERY request, whatever its own filters …
    assert len(srv.bodies) == len(sent) and all(held(b) for b in srv.bodies)    # … and every one GA4 itself got
    #                                                                 (never a read of another client of the run's)
    kinds = set()
    for b in sent:
        dims, (rng,) = _dims(b), b["dateRanges"]
        own = b["dimensionFilter"]["andGroup"]["expressions"][2:-1]  # the read's own filters
        if dims == list(cu.DIMS):
            if rng["startDate"] != rng["endDate"]:
                kinds.add("block")
            elif own:
                kinds.add("part")
                kinds.update("install days" for e in own if "firstSessionDate" in repr(e))
            else:
                kinds.add("day")
        elif dims == ["date"]:
            kinds.add("total")
        elif dims == list(cu.QDIMS):
            kinds.add("q")
    assert kinds == {"block", "day", "part", "install days", "total", "q"}   # the walk, a day alone, its split (by
    #                                                                          countries, then install days), the day's
    #                                                                          total, q's whole reads
    assert sorted(os.listdir(data)) == ["ga4_cube_paid"]             # its own store only (never the cube's)
    root = os.path.join(data, "ga4_cube_paid")
    files = _files(root)
    assert "state.json" in files and not [f for f in files if f.endswith("u.json.gz")]     # users off: no u file
    for aid in ("x~1", "x~2"):
        key = gu.file_key(aid)
        mine = [f[len(key) + 1:] for f in files if f.startswith(key + os.sep)]
        assert {"2026-09.json.gz", "2026-10.json.gz", "hot.json.gz"} <= set(mine), mine
        assert all(f == "hot.json.gz" or f[:7] in ("2026-09", "2026-10") for f in mine)
        qs = sorted(f[:7] for f in mine if f.endswith(cu.QSUF))      # q's whole reads: the cube's q files …
        qdays = {D: r for k in qs for D, r in cp.MOD.load_q(data, aid, SID, k)["days"].items()}
        assert qdays and all(r["qs"] == "ok" and r["qt"] == micros(date.fromisoformat(D)) < micros(
            date.fromisoformat(D), paid=False) for D, r in qdays.items()), qdays     # … the paid users' revenue only
        led = {**_load(os.path.join(root, key, "2026-09.json.gz"))["days"],
               **_load(os.path.join(root, key, "2026-10.json.gz"))["days"]}
        assert sorted(led) == [D.isoformat() for D in _days(HS, EDGE)]
        for D in _days(HS, EDGE):                                     # the paid users' revenue, every micro of it
            r = led[D.isoformat()]
            assert r["t"] == micros(D) < micros(D, paid=False) and r["loss"] == 0 and r["fl"] == 0, D
        assert led[FLAGGED.isoformat()]["via"] == "day" and led[FLAGGED.isoformat()]["fu"] == 1   # split, measured
        busy = led[BUSY.isoformat()]                                  # split and split again: every cell back
        assert busy["via"] == "split" and busy["dp"] >= 2 and busy["ol"] == 0 and busy["n"] > 3
        head = cp.MOD.load_head(data, aid)                            # (the cube's own reader, on the paid store)
        hot = _days(EDGE + timedelta(days=1), TODAY)
        assert head == _load(os.path.join(root, key, "hot.json.gz")) and head["done"] and head["stream_id"] == SID
        assert head["next"] == hot[0].isoformat()
        assert {D: v["t"] for D, v in head["d"].items()} == {D.isoformat(): micros(D) for D in hot}   # (the paid
        #                                                                                    users' hot days too)
    st = json.load(open(os.path.join(root, "state.json"), encoding="utf-8"))
    assert sorted(st["fetch"]) == ["x~1", "x~2"] and "u" not in st["fetch"]["x~1"]
    # the store is the cube's own format: the cube's readers read it
    m = cp.MOD
    assert [k for k, _ in m.months(data, "x~1", SID)] == ["2026-09", "2026-10"]
    line = cp.log_line(out)
    assert line.startswith("ga4 cube paid: apps 3, with GA4 2, fetched 2, fresh 0, failed 0, deferred 0, waiting 0, "
                           "days folded %d, " % (2 * n_final))
    assert ", u kept" not in line and ", error" not in line
    for s in ("example", "x~", SID, "111", "XA", "2026", "Cross-network"):
        assert s not in line


def test_the_base_cube_on_the_same_ga4_reads_everyone_unfiltered_into_its_own_store(monkeypatch, tmp_path):
    data, out, sent, srv = _run(monkeypatch, tmp_path, paid=False)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and sent and all(unheld(b) for b in sent)
    assert len(srv.bodies) == len(sent) and all(unheld(b) for b in srv.bodies) and "stuck" not in out["counts"]
    assert "ga4_cube_paid" not in os.listdir(data) and os.path.isdir(os.path.join(data, cu.DIR))
    led = _load(cu.month_path(data, "x~1", "2026-10"))["days"]
    assert all(led[D.isoformat()]["t"] == micros(D, paid=False) for D in _days(date(2026, 10, 1), EDGE))
    assert cu.log_line(out).startswith("ga4 cube: apps 3, with GA4 2, fetched 2, ")


# ── the quota: Screens' floors ──────────────────────────────────────────────────────────────────────────────────────
def test_a_property_under_screens_floors_is_deferred_by_the_paid_cube_never_by_the_cube(monkeypatch, tmp_path):
    """Every answer's snapshot sits under Screens' floor of the day (40 %) but above every live step's (10 %): the paid
    cube makes each property's first call (no snapshot yet) and defers its app there — its history backfill never
    takes what the live steps of the next build need —, while the base cube on the same GA4 and snapshot reads on."""
    low = BETWEEN[1]                                                    # (35 % of the day left)
    data, out, sent, srv = _run(monkeypatch, tmp_path / "paid", quota=low)
    assert out["apps"] == {"x~1": "deferred", "x~2": "deferred"} and "error" not in out
    assert out["counts"]["calls"] == len(sent) == len(srv.bodies) == 2 and all(held(b) for b in srv.bodies)
    assert out["counts"]["stuck"] == 0 and ", deferred 2, " in cp.log_line(out)
    st = json.load(open(os.path.join(data, "ga4_cube_paid", "state.json"), encoding="utf-8"))["fetch"]
    assert all(st[a]["deferred"] and not st[a].get("fail") for a in ("x~1", "x~2"))     # its turn next build
    data, out, sent, srv = _run(monkeypatch, tmp_path / "base", paid=False, quota=low)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and len(srv.bodies) > 2     # the live floors: on


# ── a stuck app ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_an_app_ga4_refuses_run_after_run_is_stuck_on_its_third_failed_run(monkeypatch, tmp_path):
    """The cube retries a failed app every RETRY_HOURS and never counts it; the paid wrapper keeps ga4_cecpm's streak
    ("fails" in the paid state): GA4 refusing every read, runs 1 and 2 fail (stuck 0), run 3 → both apps stuck (the
    build prints the banner's line); a run inside RETRY_HOURS holds them back (failed, not tried: still stuck); GA4
    answering again → fetched, the streak over, stuck 0."""
    data = str(tmp_path)
    _routes(monkeypatch)
    serve(monkeypatch, Server(rows(), flag, cap))
    monkeypatch.setattr(cp.MOD, "MAX_CALLS", 200)
    monkeypatch.setattr(ga4, "_call", refuse)
    path = os.path.join(data, "ga4_cube_paid", "state.json")
    for h, stuck, fails in ((0, 0, 1), (4, 0, 2), (8, 2, 3), (9, 2, 3)):
        out = cp.refresh_all(CFG, data, APPS, NOW + timedelta(hours=h), clock=lambda: 0.0)
        assert out["apps"] == {"x~1": "failed", "x~2": "failed"} and "error" not in out, h
        assert out["counts"]["stuck"] == stuck and out["counts"]["calls"] == (0 if h == 9 else 2), h
        st = json.load(open(path, encoding="utf-8"))["fetch"]
        assert [st[a]["fails"] for a in ("x~1", "x~2")] == [fails] * 2 and st["x~1"]["fail"] == "http", h
    assert cp.log_line(out).startswith("ga4 cube paid: apps 3, with GA4 2, fetched 0, fresh 0, failed 2, ")
    serve(monkeypatch, Server(rows(), flag, cap))                       # GA4 answers again
    out = cp.refresh_all(CFG, data, APPS, NOW + timedelta(hours=12), clock=lambda: 0.0)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and out["counts"]["stuck"] == 0
    st = json.load(open(path, encoding="utf-8"))["fetch"]
    assert not any("fails" in st[a] or st[a].get("fail") for a in ("x~1", "x~2"))


# ── the switches, the stage names, the workflow ─────────────────────────────────────────────────────────────────────
def test_the_switches_the_stage_names_and_the_workflow(monkeypatch):
    import yaml
    from admob_iq import stage_clock as sc
    from admob_iq.config import settings
    names = ("GA4_CUBEP", "GA4_CUBEP_BUDGET_SEC", "GA4_NVRP", "GA4_NVRP_BUDGET_SEC")
    for k in names:
        monkeypatch.delenv(k, raising=False)
    s = settings()
    assert (s["ga4_cubep"], s["ga4_cubep_budget_sec"], s["ga4_nvrp"], s["ga4_nvrp_budget_sec"]) == (False, 0, False, 0)
    for k, v in zip(names, ("true", "90", "TRUE", "x")):
        monkeypatch.setenv(k, v)
    s = settings()                                                     # (a bad number never breaks the build)
    assert (s["ga4_cubep"], s["ga4_cubep_budget_sec"], s["ga4_nvrp"], s["ga4_nvrp_budget_sec"]) == (True, 90, True, 0)
    i = sc.STAGES.index("ga4_screens")
    assert sc.STAGES[i + 1:i + 3] == ("ga4_nvr_paid", "ga4_cube_paid")    # after every other GA4 step
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        wf = yaml.safe_load(f)                                          # (the file still parses)
    env = [st for st in wf["jobs"]["refresh"]["steps"] if st.get("name") == "Build dashboard + send alerts"][0]["env"]
    assert env["GA4_CUBEP"] == "${{ vars.GA4_CUBEP || 'true' }}" and env["GA4_NVRP"] == "${{ vars.GA4_NVRP || 'true' }}"
    knobs = set()                                                       # every knob the paid modules read from the
    for mod in (cp, gnp):                                               # environment reaches the runner (a repo
        with open(mod.__file__, encoding="utf-8") as f:                 # variable never set in vain)
            knobs |= set(re.findall(r'"(GA4_(?:CUBEP|NVRP)_[A-Z_]+)"', f.read()))
    assert knobs == {"GA4_CUBEP_REPAIR_CALLS", "GA4_CUBEP_MAX_CALLS", "GA4_CUBEP_Q_CALLS", "GA4_CUBEP_Q_SEC",
                     "GA4_CUBEP_RF_CALLS", "GA4_CUBEP_WORKERS", "GA4_NVRP_MAX_CALLS"}
    for k in sorted(knobs | {"GA4_CUBEP_BUDGET_SEC", "GA4_NVRP_BUDGET_SEC"}):
        assert env[k] == "${{ vars.%s }}" % k, k
