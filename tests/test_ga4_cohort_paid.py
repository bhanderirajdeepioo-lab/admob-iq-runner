"""⚖️ The D0 … D30 cells of Google Ads users only (admob_iq.fetch.ga4_cohort_paid), offline against a synthetic GA4
(tests/test_ga4_paid.Server: made-up rows of five first-user channels, two of them paid; no network): MOD is a second
instance of fetch.ga4_cohort with its own store folder, client, log label and call knob while the base's globals never
change; a whole run (refresh_all → step_app: the backfill's block reads, a block GA4 flags read again day by day — its
flagged day split by install-day halves and measured by the day's every-install-day read —, the refresh's block GA4
rolls into "(other)" read again day by day, its busy day split twice) sends EVERY request held to Google Ads users —
the paid in-list last in its filter; every request GA4 itself got, whichever client sent it — and keeps exactly the
paid users' cells in data/ga4_cohort_paid/ (ga4_cohort's format: the hot file, the older install days' file, the
state), while the base on the same GA4 reads everyone, unfiltered, into its own store; a property under Screens' quota
floors deferred by the paid read, never by the base; an app GA4 refuses run after run "stuck" on its third failed run;
the counts-only log line; the switches, the stage name and the workflow's repo variables. The build's wiring (before
the paid cube): tests/test_uninstall_build.py. SYNTHETIC values only (the runner repo is public)."""
import gzip
import importlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_cohort as gco
from admob_iq.fetch import ga4_cohort_paid as cop
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_paid as gp
from admob_iq.fetch import ga4_uninstall as gu
from tests.test_ga4_paid import BETWEEN, SID, Server, held, recording, refuse, serve, unheld

TODAY = date(2026, 10, 13)
NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
HS = date(2026, 7, 20)                              # the made-up apps' GA4 history start (install days before the hot
#                                                     file's cut, Aug 1: the older file too)
FLAGGED = date(2026, 8, 25)                         # GA4 flags dataLossFromOtherRow on every read holding it that
#                                                     carries an install-day in-list (never the day's whole read)
BUSY, CAP = date(2026, 10, 1), 10                   # … and rolls a read holding this day past CAP rows into "(other)"
CH = {"Cross-network": 3, "Paid Search": 1, "Organic Search": 2, "Direct": 1, "Unassigned": 1}   # channel weights
PW, AW = 4, 8                                       # the paid channels' weight, every channel's
APPS = [{"app_id": "x~1", "package": "com.example.alpha"}, {"app_id": "x~2", "package": "com.example.beta"},
        {"app_id": "x~3", "package": "com.example.none"}]
CFG = {"client_id": "c", "client_secret": "s", "refresh_tokens": json.dumps({"o": "rt"})}
NAME = "admob_iq.fetch._ga4_cohort_paid_impl"


def _days(a, b):
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def ymd(d):
    return d.strftime("%Y%m%d")


def rows():
    """Activity day D × install day X (HS … D, ages 0 … 30) × first-user channel: revenue (age + 1) × weight × 1000
    micros, users 10 × weight at age 0 (else the weight)."""
    out = []
    for D in _days(HS, TODAY):
        for L in range(min(30, (D - HS).days) + 1):
            for ch, w in CH.items():
                out.append({"date": ymd(D), "firstSessionDate": ymd(D - timedelta(days=L)),
                            "firstUserDefaultChannelGroup": ch, "platform": "Android", "streamId": SID,
                            "activeUsers": w * (10 if L == 0 else 1), "totalAdRevenue": (L + 1) * w * 1000})
    return out


def cell(X, w):
    """Install day X's stored cell {"r": micros, "u": users} at ages 0 … 30 of the users of channel weight w (a day not
    lived yet: 0)."""
    live = [X + timedelta(days=L) <= TODAY for L in range(gco.LAGS)]
    return {"r": [(L + 1) * w * 1000 if live[L] else 0 for L in range(gco.LAGS)],
            "u": [(w * (10 if L == 0 else 1)) if live[L] else 0 for L in range(gco.LAGS)]}


def _dims(body):
    return [d["name"] for d in body["dimensions"]]


def _inlist(body):
    """The read's own install-day in-list (None: none — the day's every-install-day read)."""
    for e in body["dimensionFilter"]["andGroup"]["expressions"]:
        if (e.get("filter") or {}).get("fieldName") == "firstSessionDate":
            return e["filter"]["inListFilter"]["values"]
    return None


def _holds(body, D):
    a, b = (date.fromisoformat(body["dateRanges"][0][k]) for k in ("startDate", "endDate"))
    return a <= D <= b


def flag(body):
    return {"dataLossFromOtherRow": True} if _holds(body, FLAGGED) and _inlist(body) is not None else {}


def cap(body):
    return CAP if _holds(body, BUSY) else None


def _routes(monkeypatch):
    """Two made-up properties (one app each; com.example.none has no GA4), their history from HS."""
    route = {"property_id": "111", "stream_id": SID, "owner": "o"}
    monkeypatch.setattr(gco.gu, "load_state", lambda d: {"routes": {"by_package": {
        "com.example.alpha": route, "com.example.beta": dict(route, property_id="112")}},
        "tz": {"111": "UTC", "112": "UTC"}, "fetch": {}})
    monkeypatch.setattr(gco.gaud, "_uni_meta", lambda ust, d, aid, r: {"history_start": HS.isoformat()})


def _run(monkeypatch, tmp_path, paid=True, quota=None):
    """refresh_all over two made-up properties (one app each, + one with no GA4) on the synthetic GA4 (every answer
    carrying `quota`, None: no snapshot): the paid module's (its client recording every body) or the base's (gf.App
    recording) → (data dir, status, the bodies the client recorded, the Server: what GA4 itself got)."""
    data = str(tmp_path)
    _routes(monkeypatch)
    srv = Server(rows(), flag, cap, quota=quota)
    serve(monkeypatch, srv)
    sent = []
    m = cop.MOD if paid else gco
    monkeypatch.setattr(m, "MAX_CALLS", 200)                            # room for the whole run in one
    monkeypatch.setattr(m, "App", recording(gp.App if paid else gf.App, sent))
    out = (cop if paid else gco).refresh_all(CFG, data, APPS, NOW, clock=lambda: 0.0)
    return data, out, sent, srv


def _load(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _files(root):
    return sorted(os.path.relpath(os.path.join(b, n), root) for b, _, ns in os.walk(root) for n in ns)


# ── the instance ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_instance_its_knob_and_the_base_untouched(monkeypatch):
    monkeypatch.delenv("GA4_COHORTP_MAX_CALLS", raising=False)
    m = importlib.reload(cop).MOD
    assert m is not gco and m.__name__ == NAME and sys.modules[NAME] is m and m.step_app is not gco.step_app
    assert (m.DIR, m.NAME, m.App, m.MAX_CALLS) == ("ga4_cohort_paid", "ga4 cohort paid", gp.App, gco.MAX_CALLS)
    assert cop.BUDGET_SEC == m.BUDGET_SEC == gco.BUDGET_SEC
    assert (gco.DIR, gco.NAME, gco.App) == ("ga4_cohort", "ga4 cohort", gf.App)    # the base: its own
    assert m.gcu is gco.gcu and m.gu is gco.gu and m.Stop is gco.Stop is gf.Stop    # the same modules under both
    assert cop.log_line({"counts": {"selected": 3}}).startswith("ga4 cohort paid: apps 3, with GA4 0, ")
    assert gco.log_line({"counts": {"selected": 3}}).startswith("ga4 cohort: apps 3, with GA4 0, ")
    assert gco.log_line({"counts": {}, "error": "KeyError"}).endswith(", calls 0, tokens 0, error KeyError")
    assert m.store_path("d", "x~1") == os.path.join("d", "ga4_cohort_paid", gu.file_key("x~1") + ".json.gz")


def test_its_call_knob_from_the_environment(monkeypatch):
    """GA4_COHORTP_MAX_CALLS (read at import; empty = ga4_cohort's MAX_CALLS) is the paid read's own — the base's
    MAX_CALLS never changes."""
    c0 = gco.MAX_CALLS
    try:
        monkeypatch.setenv("GA4_COHORTP_MAX_CALLS", "9")
        assert importlib.reload(cop).MOD.MAX_CALLS == 9 and gco.MAX_CALLS == c0
        monkeypatch.setenv("GA4_COHORTP_MAX_CALLS", "")
        assert importlib.reload(cop).MOD.MAX_CALLS == c0
    finally:
        monkeypatch.delenv("GA4_COHORTP_MAX_CALLS", raising=False)
        importlib.reload(cop)


# ── a whole run ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_run_holds_every_read_to_google_ads_users_and_keeps_only_their_cells_in_its_own_store(monkeypatch, tmp_path):
    data, out, sent, srv = _run(monkeypatch, tmp_path)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and "error" not in out
    c = out["counts"]
    assert c["calls"] == len(sent) and c["stuck"] == 0 and c["oth_blocks"] == 4      # (a flagged block, a busy one)
    assert c["alone"] == 2 * (len(_days(date(2026, 8, 19), date(2026, 9, 8))) + len(_days(date(2026, 9, 9), TODAY)))
    assert (c["loss_days"], c["flagged"], c["hidden"]) == (0, 0, 0)                 # every part read back whole
    assert sent and all(held(b) for b in sent)                      # EVERY request, whatever its own filters …
    assert len(srv.bodies) == len(sent) and all(held(b) for b in srv.bodies)    # … and every one GA4 itself got
    kinds = set()
    for b in sent:
        assert _dims(b) == ["date", "firstSessionDate"]
        a, z = b["dateRanges"][0]["startDate"], b["dateRanges"][0]["endDate"]
        il = _inlist(b)
        if a != z:
            kinds.add("block")
        elif il is None:
            kinds.add("total")
        elif len(il) == gco.LAGS:
            kinds.add("day")
        else:
            kinds.add("part")
    assert kinds == {"block", "day", "part", "total"}               # the blocks, a day alone, its install-day halves,
    #                                                                 the day's every-install-day read
    assert sorted(os.listdir(data)) == ["ga4_cohort_paid"]          # its own store only (never ga4_cohort's)
    root = os.path.join(data, "ga4_cohort_paid")
    keys = sorted(gu.file_key(a) for a in ("x~1", "x~2"))
    assert _files(root) == sorted(["state.json"] + [k + s for k in keys for s in (".json.gz", ".old.json.gz")])
    for aid in ("x~1", "x~2"):
        hot = _load(os.path.join(root, gu.file_key(aid) + ".json.gz"))
        old = _load(os.path.join(root, gu.file_key(aid) + ".old.json.gz"))
        assert hot["cut"] == "2026-08-01" and min(hot["x"]) == "2026-08-01" and max(old["x"]) == "2026-07-31"
        st = cop.MOD.load_store(data, aid)                          # (ga4_cohort's own reader, on the paid store)
        assert (st["stream_id"], st["hs"], st["read_today"]) == (SID, HS.isoformat(), TODAY.isoformat())
        assert st["backfill"]["done"] and st["backfill"]["from"] == HS.isoformat()
        assert "lo" not in st and "lf" not in st
        assert sorted(st["x"]) == [X.isoformat() for X in _days(HS, TODAY)]
        for X in _days(HS, TODAY):                                  # the Google Ads users' cells, every micro of them
            assert st["x"][X.isoformat()] == cell(X, PW), X
        assert gco.load_store(data, aid) is None                    # (nothing in ga4_cohort's own folder)
    state = json.load(open(os.path.join(root, "state.json"), encoding="utf-8"))
    assert sorted(state["fetch"]) == ["x~1", "x~2"] and all("fails" not in v for v in state["fetch"].values())
    line = cop.log_line(out)
    assert line.startswith("ga4 cohort paid: apps 3, with GA4 2, fetched 2, fresh 0, failed 0, deferred 0, "
                           "waiting 0, blocks with (other) 4, days read alone %d, " % c["alone"])
    assert ", error" not in line
    for s in ("example", "x~", SID, "111", "2026", "Cross-network"):
        assert s not in line


def test_the_base_on_the_same_ga4_reads_everyone_unfiltered_into_its_own_store(monkeypatch, tmp_path):
    data, out, sent, srv = _run(monkeypatch, tmp_path, paid=False)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and sent and all(unheld(b) for b in sent)
    assert len(srv.bodies) == len(sent) and all(unheld(b) for b in srv.bodies) and "stuck" not in out["counts"]
    assert sorted(os.listdir(data)) == ["ga4_cohort"]
    st = gco.load_store(data, "x~1")
    assert all(st["x"][X.isoformat()] == cell(X, AW) for X in _days(HS, TODAY))   # every user's cells
    assert gco.log_line(out).startswith("ga4 cohort: apps 3, with GA4 2, fetched 2, ")
    assert cop.MOD.load_store(data, "x~1") is None


# ── the quota: Screens' floors ──────────────────────────────────────────────────────────────────────────────────────
def test_a_property_under_screens_floors_is_deferred_by_the_paid_read_never_by_the_base(monkeypatch, tmp_path):
    """Every answer's snapshot sits under Screens' floor of the day (40 %) but above every live step's (10 %): the paid
    read makes each property's first call (no snapshot yet) and defers its app there — its history backfill never takes
    what the live steps of the next build need —, while the base on the same GA4 and snapshot reads on."""
    low = BETWEEN[1]                                                    # (35 % of the day left)
    data, out, sent, srv = _run(monkeypatch, tmp_path / "paid", quota=low)
    assert out["apps"] == {"x~1": "deferred", "x~2": "deferred"} and "error" not in out
    assert out["counts"]["calls"] == len(sent) == len(srv.bodies) == 2 and all(held(b) for b in srv.bodies)
    assert out["counts"]["stuck"] == 0 and ", deferred 2, " in cop.log_line(out)
    st = json.load(open(os.path.join(data, "ga4_cohort_paid", "state.json"), encoding="utf-8"))["fetch"]
    assert all(st[a]["deferred"] and not st[a].get("fail") for a in ("x~1", "x~2"))     # its turn next build
    bf = cop.MOD.load_store(data, "x~1")["backfill"]                    # (the first block kept: the backfill goes on
    assert not bf.get("done") and bf["next"] == "2026-08-19"             # from the next one)
    data, out, sent, srv = _run(monkeypatch, tmp_path / "base", paid=False, quota=low)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and len(srv.bodies) > 2     # the live floors: on


# ── a stuck app ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_an_app_ga4_refuses_run_after_run_is_stuck_on_its_third_failed_run(monkeypatch, tmp_path):
    """ga4_cohort retries a failed app every RETRY_HOURS and never counts it; the paid wrapper keeps ga4_cecpm's streak
    ("fails" in the paid state): GA4 refusing every read, runs 1 and 2 fail (stuck 0), run 3 → both apps stuck (the
    build prints the banner's line); a run inside RETRY_HOURS holds them back (failed, not tried: still stuck); GA4
    answering again → fetched, the streak over, stuck 0."""
    data = str(tmp_path)
    _routes(monkeypatch)
    serve(monkeypatch, Server(rows(), flag, cap))
    monkeypatch.setattr(cop.MOD, "MAX_CALLS", 200)
    monkeypatch.setattr(ga4, "_call", refuse)
    path = os.path.join(data, "ga4_cohort_paid", "state.json")
    for h, stuck, fails in ((0, 0, 1), (4, 0, 2), (8, 2, 3), (9, 2, 3)):
        out = cop.refresh_all(CFG, data, APPS, NOW + timedelta(hours=h), clock=lambda: 0.0)
        assert out["apps"] == {"x~1": "failed", "x~2": "failed"} and "error" not in out, h
        assert out["counts"]["stuck"] == stuck and out["counts"]["calls"] == (0 if h == 9 else 2), h
        st = json.load(open(path, encoding="utf-8"))["fetch"]
        assert [st[a]["fails"] for a in ("x~1", "x~2")] == [fails] * 2 and st["x~1"]["fail"] == "http", h
    assert cop.log_line(out).startswith("ga4 cohort paid: apps 3, with GA4 2, fetched 0, fresh 0, failed 2, ")
    serve(monkeypatch, Server(rows(), flag, cap))                       # GA4 answers again
    out = cop.refresh_all(CFG, data, APPS, NOW + timedelta(hours=12), clock=lambda: 0.0)
    assert out["apps"] == {"x~1": "fetched", "x~2": "fetched"} and out["counts"]["stuck"] == 0
    st = json.load(open(path, encoding="utf-8"))["fetch"]
    assert not any("fails" in st[a] or st[a].get("fail") for a in ("x~1", "x~2"))


# ── the switch, the stage name, the workflow ────────────────────────────────────────────────────────────────────────
def test_the_switch_the_stage_name_and_the_workflow(monkeypatch):
    import yaml
    from admob_iq import stage_clock as sc
    from admob_iq.config import settings
    for k in ("GA4_COHORTP", "GA4_COHORTP_BUDGET_SEC"):
        monkeypatch.delenv(k, raising=False)
    s = settings()
    assert (s["ga4_cohortp"], s["ga4_cohortp_budget_sec"]) == (False, 0)
    monkeypatch.setenv("GA4_COHORTP", "TRUE")
    monkeypatch.setenv("GA4_COHORTP_BUDGET_SEC", "90")
    assert (settings()["ga4_cohortp"], settings()["ga4_cohortp_budget_sec"]) == (True, 90)
    monkeypatch.setenv("GA4_COHORTP_BUDGET_SEC", "x")                   # (a bad number never breaks the build)
    assert settings()["ga4_cohortp_budget_sec"] == 0
    i = sc.STAGES.index("ga4_nvr_paid")
    assert sc.STAGES[i + 1:i + 3] == ("ga4_cohort_paid", "ga4_cube_paid")    # the light reads first, the paid cube
    #                                                                          the last GA4 step
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        wf = yaml.safe_load(f)                                          # (the file still parses)
    env = [st for st in wf["jobs"]["refresh"]["steps"] if st.get("name") == "Build dashboard + send alerts"][0]["env"]
    assert env["GA4_COHORTP"] == "${{ vars.GA4_COHORTP || 'true' }}"
    for k in ("GA4_COHORTP_BUDGET_SEC", "GA4_COHORTP_MAX_CALLS"):
        assert env[k] == "${{ vars.%s }}" % k, k
