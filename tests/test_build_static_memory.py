"""The build's memory (the runner has 16 GB; the AdMob history is most of what the build holds): FileRepo drops its key
maps after flush() and builds a table's map again when a write comes later; release() frees a table nothing reads any
more (a later read reads its file back); build() computes the Mediation / Deductions daily files right after
build_from_db and writes them — or prints their "… skipped:" lines — at their own steps, frees the snapshot history and
placement × country there and the monthly rollup after the baseline report, and gives the revenue inputs the history's
own rows instead of the app-name wrapper's copies. Every output stays byte for byte as before. Synthetic data only."""

import copy
import gzip
import io
import json
import os
import socket
from datetime import date, timedelta

import pytest

from admob_iq import build_static, db, health
from admob_iq import stage_clock as sc
from admob_iq.api import dataservice
from admob_iq.db import FileRepo

PUB = "pub-0000000000000000"
TODAY = date(2026, 7, 23)
NET = dict(account_id=PUB, app_id="app~one", app_name="Synth One", country="US", format="banner",
           platform="ANDROID", ad_requests=10, matched_requests=9, impressions=8, clicks=1, currency_code="USD")


def _net(day, unit, micros=1000):
    return dict(NET, report_date=day, ad_unit_id=unit, estimated_earnings_micros=micros)


def _snap(day, sday, unit, micros):
    return {"report_date": day, "snapshot_date": sday, "account_id": PUB, "app_id": "app~one", "ad_unit_id": unit,
            "country": "US", "format": "banner", "estimated_earnings_micros": micros, "impressions": 8, "clicks": 1}


def _files(d):
    """Every file under d → its bytes (a .gz file: decompressed — its header carries the write time)."""
    out = {}
    for base, _dirs, names in os.walk(str(d)):
        for n in names:
            p = os.path.join(base, n)
            with open(p, "rb") as f:
                raw = f.read()
            out[os.path.relpath(p, str(d))] = gzip.decompress(raw) if n.endswith(".gz") else raw
    return out


def _put_gz(path, obj):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, default=str)


# ── F12: the key maps after flush() ─────────────────────────────────────────────────────────────────────────────────
def _history(d):
    """A stored history whose network file holds one key TWICE (rows 0 and 2: the map keeps the later one)."""
    os.makedirs(str(d), exist_ok=True)
    _put_gz(os.path.join(str(d), "network.json.gz"),
            [_net("2026-07-01", "u1", 100), _net("2026-07-01", "u2", 200), _net("2026-07-01", "u1", 300)])
    r = FileRepo(str(d))
    for i in range(4):
        r.append_snapshot(_snap("2026-07-0%d" % (i + 1), "2026-07-0%d" % (i + 2), "u1", 1000 - i))
    r.flush()


def test_flush_drops_the_key_maps_and_a_write_after_it_matches_a_repo_that_kept_them(tmp_path):
    _history(tmp_path / "a")
    _history(tmp_path / "b")
    a, b = FileRepo(str(tmp_path / "a")), FileRepo(str(tmp_path / "b"))
    for r in (a, b):                                    # the fetch: writes on the loaded history
        r.upsert_network(_net("2026-07-02", "u1", 400))
        r.append_snapshot(_snap("2026-07-05", "2026-07-06", "u1", 900))
        r.upsert_mediation_unit(dict(_net("2026-07-02", "u1"), ad_requests=12))
    assert a._pos["net"] == b._pos["net"] and a._pos["net"]["2026-07-01|%s|app~one|u1|US|banner|ANDROID" % PUB] == 2
    kept = {n: dict(m.items()) for n, m in b._pos.items()}   # (as plain {key: index} dicts: the code before)
    a.flush()
    b.flush()
    assert a._pos == {}                                 # the maps go with the flush …
    b._pos.update(kept)                                 # (b: the code before this change — its maps stayed)
    for r in (a, b):                                    # … and a write after it builds them again: the same maps
        r.upsert_network(_net("2026-07-01", "u1", 500))         # the key stored twice: row 2 again, never row 0
        r.upsert_network(_net("2026-07-03", "u3", 600))         # a new key: appended
        r.append_snapshot(_snap("2026-07-01", "2026-07-02", "u1", 1))   # already there: never overwritten
        r.append_snapshot(_snap("2026-07-06", "2026-07-07", "u1", 800))
        r.upsert_mediation_unit(dict(_net("2026-07-02", "u1"), ad_requests=13))
    assert a._pos == b._pos and a._rows == b._rows
    assert [x["estimated_earnings_micros"] for x in a.fetch_network()] == [100, 200, 500, 400, 600]
    a.flush()
    b.flush()
    assert _files(tmp_path / "a") == _files(tmp_path / "b") and a._pos == {} and b._pos == {}


def test_the_snapshot_key_check_after_a_flush(tmp_path):
    _history(tmp_path)
    r = FileRepo(str(tmp_path))
    assert r._snap_has_key(_snap("2026-07-01", "2026-07-02", "u1", 0)) is False and "snap" not in r._rows   # (no load)
    rows = r.fetch_snapshots()
    r.flush()
    assert r._pos == {}
    assert r._snap_has_key(rows[0]) and not r._snap_has_key(_snap("2026-07-09", "2026-07-10", "u1", 0))
    assert len(r._pos["snap"]) == len(rows)            # built again for the check
    # a later flush still sorts the part files nobody listed by that check: one with only known rows goes, one with
    # a row the history lacks stays (as with the maps kept)
    sd = os.path.join(str(tmp_path), db.SNAP_DIR)
    _put_gz(os.path.join(sd, "part-0098-aaaaaaaaaaaa.json.gz"), rows[:2])
    _put_gz(os.path.join(sd, "part-0099-bbbbbbbbbbbb.json.gz"), [_snap("2026-07-09", "2026-07-10", "u1", 0)])
    r._pos.clear()
    r.flush()
    left = sorted(os.listdir(sd))
    assert "part-0098-aaaaaaaaaaaa.json.gz" not in left and "part-0099-bbbbbbbbbbbb.json.gz" in left


# ── release(): free a table, read it back from its file when asked again ───────────────────────────────────────────────
def _full(d):
    r = FileRepo(str(d))
    r.init_schema()
    for i in range(3):
        r.upsert_network(_net("2026-07-0%d" % (i + 1), "u1"))
        r.append_snapshot(_snap("2026-07-0%d" % (i + 1), "2026-07-0%d" % (i + 2), "u1", 50 + i))
        r.upsert_placement_country(dict(NET, ad_unit_id="u%d" % i, estimated_earnings_micros=7))
    r.merge_adunit_country_monthly([dict(NET, ad_unit_id="u1", unit_name="Unit", month="2026-06", days=30,
                                         estimated_earnings_micros=9)])
    r.flush()
    return r


def test_release_frees_a_table_and_a_later_read_reads_it_back_from_its_file(tmp_path, monkeypatch):
    r = _full(tmp_path)
    before = {"snap": copy.deepcopy(r.fetch_snapshots()), "pc": copy.deepcopy(r.fetch_placement_country()),
              "acm": copy.deepcopy(r.fetch_adunit_country_monthly())}
    for name in ("snap", "pc", "acm"):
        assert r.release(name) is True
        assert r.release(name) is False                 # nothing left to free
    assert "snap" not in r._rows and "pc" not in r._rows and "acm" not in r._ac and "snap" not in r._pos
    assert r.release("med") is False                   # never loaded: nothing to free
    reads = []
    real_parts, real_any = db._snap_load_parts, db._read_json_any
    monkeypatch.setattr(db, "_snap_load_parts", lambda *a, **k: reads.append("snap parts") or real_parts(*a, **k))
    monkeypatch.setattr(db, "_read_json_any", lambda p, **k: reads.append(os.path.basename(p)) or real_any(p, **k))
    assert r.fetch_snapshots() == before["snap"]
    assert r.fetch_placement_country() == before["pc"]
    assert r.fetch_adunit_country_monthly() == before["acm"]
    assert reads == ["snap parts", "placement_country.json", "adunit_country_monthly.json"]   # read back from disk
    assert r.fetch_snapshots() == before["snap"] and len(reads) == 3                         # (once)
    r.append_snapshot(_snap("2026-07-01", "2026-07-02", "u1", 0))       # its map came back with the rows: a key
    assert len(r.fetch_snapshots()) == 3                                # it holds is still never appended twice


def test_release_keeps_a_table_with_changes_not_on_disk_yet(tmp_path):
    r = _full(tmp_path)
    r.upsert_network(_net("2026-07-09", "u9"))
    r.append_snapshot(_snap("2026-07-09", "2026-07-10", "u9", 1))
    r.merge_adunit_country_monthly([dict(NET, ad_unit_id="u9", unit_name="Unit", month="2026-05", days=31)])
    r.replace_adunit_country_daily([dict(NET, ad_unit_id="u9", report_date="2026-07-09")])
    for name in ("net", "snap", "acm", "acd"):
        assert r.release(name) is False                 # kept: these rows are only in memory
    assert len(r._rows["net"]) == 4 and len(r._rows["snap"]) == 4 and "u9" in r._ac["acm"]["data"]
    r.append_snapshot(_snap("2026-07-01", "2026-07-02", "u1", 0))       # (a key it has: no change)
    r.flush()
    assert r.release("net") and r.release("snap") and r.release("acm") and r.release("acd")
    assert len(FileRepo(str(tmp_path)).fetch_network()) == 4 == len(r.fetch_network())
    r.append_snapshot(_snap("2026-07-01", "2026-07-02", "u1", 0))       # a known key after the re-read: still no change
    assert r.release("snap") is True


def test_a_flush_after_a_release_leaves_the_released_file_alone(tmp_path, capsys):
    r = _full(tmp_path)
    p = os.path.join(str(tmp_path), "placement_country.json.gz")
    raw, mtime = open(p, "rb").read(), os.stat(p).st_mtime_ns
    assert r.release("pc")
    r.upsert_network(_net("2026-07-09", "u9"))
    capsys.readouterr()
    r.flush()
    assert open(p, "rb").read() == raw and os.stat(p).st_mtime_ns == mtime
    assert "repo flush: 1 file(s) written, 2 unchanged" in capsys.readouterr().err     # net written; snap, acm kept


# ── build(): a live build without any network (tests/test_review_build.py's way) ────────────────────────────────────
class _Spy(FileRepo):
    """The build's FileRepo, watched: every release() and every first read of a table, in order."""
    last = None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.log, self.freed = [], {}
        _Spy.last = self

    def release(self, name):
        self.freed.setdefault(name, (self._rows.get(name), self._ac.get(name)))     # (kept alive: their ids stay theirs)
        got = super().release(name)
        self.log.append(("release", name, got))
        return got

    def _load(self, name):
        if name not in self._rows:
            self.log.append(("read", name))
        return super()._load(name)

    def _load_ac(self, name, default):
        if name not in self._ac:
            self.log.append(("read", name))
        return super()._load_ac(name, default)


def _seed(data):
    """Older snapshots (a day after each report day, worth more than the build's own snapshot of it): the Deductions
    file has rows to show. And a monthly ad-unit rollup inside the baseline report's window, as every real history
    has: the baseline report is built, so baseline_write (its own `daily` series) runs before the daily steps."""
    from admob_iq.fetch.admob_client import MockAdMobClient
    from admob_iq.fetch.fetcher import build_snapshot
    r = FileRepo(data)
    for raw in MockAdMobClient(PUB).network_report(TODAY - timedelta(days=9), TODAY - timedelta(days=3)):
        s = build_snapshot(raw, raw["report_date"] + timedelta(days=1))
        s["estimated_earnings_micros"] = raw["estimated_earnings_micros"] * 2 + 1000
        r.append_snapshot(s)
    acm = dict(app_id="app~puzzle", app_name="Synth", country="US", currency_code="USD", days=30, ad_requests=100000,
               matched_requests=90000, impressions=80000, clicks=800, estimated_earnings_micros=50_000_000,
               ctr_min=0.005, ctr_max=0.02, match_min=0.8, match_max=0.95, show_min=0.8, show_max=0.95, ecpm_min=0.5,
               ecpm_max=0.8, ctr_avg=0.01, match_avg=0.9, show_avg=0.89, ecpm_avg=0.62)   # every db.ACM_FIELDS value
    r.merge_adunit_country_monthly([dict(acm, ad_unit_id=uid, unit_name=uid.split("~")[1], month=mo)
                                    for mo in ("2026-04", "2026-05", "2026-06")
                                    for uid in ("ca~home_banner", "ca~level_int")])
    r.flush()


@pytest.fixture
def live(monkeypatch):
    """build(mode="live") offline: fake creds, the mock AdMob pull, the GA4 tabs off (their AdMob revenue inputs still
    read — handed to `seen`), Google Ads / icons stubbed, sockets refused; one app renamed, one hidden."""
    from admob_iq.fetch import fetcher
    import admob_iq.fetch.app_icons as icons
    real = build_static.settings()

    def fake_settings():
        s = dict(real, google_client_id="cid-test", google_client_secret="cs-test", report_tz="America/Los_Angeles",
                 notify_dry_run=True, telegram_token="", telegram_chat="", google_ads_dev_token=None,
                 google_ads_refresh_token=None, google_ads_login_customer_id=None, ga4_active=True)
        s["smtp"] = dict(real["smtp"], host="")
        return s
    orig = fetcher.run_once
    seen = []
    monkeypatch.setattr(build_static, "settings", fake_settings)
    monkeypatch.setattr(build_static, "resolve_accounts", lambda: [
        {"account_id": PUB, "refresh_token": "rt-test", "reporting_tz": "America/Los_Angeles"}])
    monkeypatch.setattr(fetcher, "run_once", lambda accounts, repo, **kw: orig(
        accounts, repo, **dict(kw, mode="mock", full_history=False, ac_full_history=False)))
    monkeypatch.setattr(build_static, "_backfill_missing_accounts_ac", lambda *a, **k: None)
    monkeypatch.setattr(build_static, "_backfill_network_selected_apps", lambda *a, **k: None)
    monkeypatch.setattr(build_static, "_uninstall_step",
                        lambda dash, data_dir, out_dir, s, revenue=None: seen.append((dash, revenue)) or [])
    monkeypatch.setattr(build_static, "FileRepo", _Spy)
    monkeypatch.setattr(icons, "resolve_app_icons", lambda *a, **k: {})

    def no_net(*a, **k):
        raise OSError("network blocked in test")
    monkeypatch.setattr(socket.socket, "connect", no_net)
    monkeypatch.setattr(socket, "getaddrinfo", no_net)
    monkeypatch.setenv("REVIEW_ENABLED", "false")

    def build(root, mode="live"):
        data, cfg, out = os.path.join(root, "data"), os.path.join(root, "config"), os.path.join(root, "site")
        os.makedirs(data, exist_ok=True)
        os.makedirs(cfg, exist_ok=True)
        for m in (".backfilled", ".country_backfilled", ".ac_backfilled", build_static.MU_MARKER):
            with open(os.path.join(data, m), "w") as f:
                f.write("x\n")
        with open(os.path.join(cfg, "app_names.json"), "w") as f:
            json.dump({"app~puzzle": "Synth Renamed"}, f)
        with open(os.path.join(cfg, "selected_apps.json"), "w") as f:
            json.dump({"accounts": {PUB: {"decided": True, "selected": ["app~puzzle"]}}}, f)
        _seed(data)
        r = build_static.build(out_dir=out, data_dir=data, today=TODAY, mode=mode)
        assert r["mode"] == mode
        return out, data
    build.seen = seen
    return build


def _views(data):
    """The build's two views of the stored history: the name wrapper, and the hidden-app filter over it."""
    w = build_static._DisambiguatedRepo(FileRepo(data), build_static._account_names(data),
                                        build_static._app_names(data))
    hidden = build_static._hidden_app_ids(w, data)
    return w, (build_static._AppFilteredRepo(w, hidden) if hidden else w), hidden


def _dump(obj):
    buf = io.StringIO()
    json.dump(obj, buf, ensure_ascii=False, separators=(",", ":"))
    return buf.getvalue().encode("utf-8")


def test_the_daily_files_hold_what_their_functions_give_on_the_stored_history(tmp_path, live):
    sc.begin()
    try:
        out, data = live(str(tmp_path))
    finally:
        prof = sc.finish(None)
    w, frepo, hidden = _views(data)
    med, ded = dataservice.build_mediation_daily(frepo), dataservice.build_deductions_daily(frepo)
    assert hidden == {"app~photo"} and list(med["by_app"]) == ["Synth Renamed"] and ded["data"]   # (worth checking)
    assert open(os.path.join(out, "mediation_daily.json"), "rb").read() == _dump(med)
    assert open(os.path.join(out, "deductions_daily.json"), "rb").read() == _dump(ded)
    # baseline_write ran before them (the stored rollup builds the baseline report), and the steps after them too
    assert os.path.exists(os.path.join(out, "baseline.json")) and os.path.exists(os.path.join(out, "_headers"))
    # timed under their own names: the work at dashboard_build, the write at the step of each
    by = {(e.get("parent"), e["name"]) for e in prof["stages"]}
    assert {("dashboard_build", "mediation_daily"), ("dashboard_build", "deductions_daily"),
            (None, "mediation_daily"), (None, "deductions_daily")} <= by


@pytest.fixture
def steps(monkeypatch):
    """Each top-level step's start written into stderr ("@step <name>"), so a line's place among the steps shows."""
    real = sc.step

    def step(name):
        print("@step " + name, file=build_static.sys.stderr)
        real(name)
    monkeypatch.setattr(sc, "step", step)


def _between(err, line, a, b):
    lines = err.splitlines()
    return lines.count(line) == 1 and lines.index("@step " + a) < lines.index(line) < lines.index("@step " + b)


def test_a_daily_file_failure_is_said_at_its_own_step_as_before(tmp_path, live, steps, monkeypatch):
    def boom(repo):
        raise RuntimeError("synthetic boom")

    def other(repo):
        raise ValueError("synthetic other")
    monkeypatch.setattr(dataservice, "build_mediation_daily", boom)
    monkeypatch.setattr(dataservice, "build_deductions_daily", other)
    monkeypatch.setattr(health, "FAULTS", {})
    real_attach, attached = health.attach, []
    monkeypatch.setattr(health, "attach", lambda d: attached.append(dict(health.FAULTS)) or real_attach(d))
    buf = io.StringIO()
    monkeypatch.setattr(build_static.sys, "stderr", health._Tee(buf))       # the build's own reader (health.watch)
    out, _ = live(str(tmp_path / "fail"))
    err = buf.getvalue()
    assert _between(err, "mediation daily ship skipped: synthetic boom", "mediation_daily", "deductions_daily")
    assert _between(err, "deductions daily ship skipped: synthetic other", "deductions_daily", "static_files")
    assert not os.path.exists(os.path.join(out, "mediation_daily.json"))
    assert not os.path.exists(os.path.join(out, "deductions_daily.json"))
    # the page's red banner is attached before those steps (as before): only the public log's line names them
    assert attached and not {"mediation daily ship", "deductions daily ship"} & set(attached[-1])
    assert health.FAULTS["mediation daily ship"] == "error" and health.FAULTS["deductions daily ship"] == "error"
    # a failure while WRITING a file (its contents built fine at dashboard_build) is said at its step too
    monkeypatch.setattr(dataservice, "build_mediation_daily", lambda repo: {"by_app": {"x": object()}})
    buf.seek(0)
    buf.truncate()
    live(str(tmp_path / "write"))
    assert _between(buf.getvalue(), "mediation daily ship skipped: Object of type object is not JSON serializable",
                    "mediation_daily", "deductions_daily")


def test_baseline_write_runs_first_and_the_daily_files_are_still_written(tmp_path, live, steps, capsys):
    """baseline_write runs whenever the baseline report is built (so on every real history) and binds `daily` to its
    own series before the daily steps: the two files computed at dashboard_build keep a name of their own, so they
    are still written at their steps and the build goes on to its end."""
    out, _ = live(str(tmp_path))
    err = capsys.readouterr().err
    order = [ln[len("@step "):] for ln in err.splitlines() if ln.startswith("@step ")]
    assert order.index("baseline_write") < order.index("mediation_daily") < order.index("deductions_daily")
    assert "daily series skipped" not in err            # baseline_write's own series was built
    for name in ("baseline.json", "baseline_daily.json.gz", "mediation_daily.json", "deductions_daily.json",
                 "index.html", "_headers"):
        assert os.path.exists(os.path.join(out, name)), name


@pytest.mark.parametrize("mode", ["live", "mock"])
def test_released_tables_are_never_read_again(tmp_path, live, mode):
    live(str(tmp_path), mode=mode)
    log = _Spy.last.log
    rel = [x for x in log if x[0] == "release"]
    assert rel == [("release", "snap", True), ("release", "pc", True), ("release", "acm", True)]
    for _, name, _ in rel:                              # no read of a freed table after its release
        assert ("read", name) not in log[log.index(("release", name, True)):]
    assert not {"snap", "pc"} & set(_Spy.last._rows) and "acm" not in _Spy.last._ac and _Spy.last._pos == {}


def _ids(obj, seen=None):
    """The ids of every dict / list / tuple reachable from obj."""
    seen = set() if seen is None else seen
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, (dict, list, tuple)) and id(o) not in seen:
            seen.add(id(o))
            stack.extend(o.values() if isinstance(o, dict) else o)
            if isinstance(o, dict):
                stack.extend(k for k in o if isinstance(k, tuple))
    return seen


def test_no_step_after_build_from_db_can_change_a_row_the_daily_files_read(tmp_path, live):
    """The daily files are built at dashboard_build instead of at their steps: the same only while no step in between
    changes a mediation, network or snapshot row. Those steps get the dashboard and the revenue inputs (never the repo):
    neither holds such a row, so none can."""
    live(str(tmp_path))
    dash, revenue = live.seen[-1]
    held = _ids(dash) | _ids({k: v for k, v in revenue.items() if k != "adsrc"})
    repo = _Spy.last
    lists = [repo._rows["net"], repo._rows["med"], repo.freed["snap"][0]]
    assert all(lists) and not held & {id(r) for rows in lists for r in rows} and not held & {id(x) for x in lists}


# ── F5: the revenue inputs read the history's own rows ──────────────────────────────────────────────────────────────
def _old_revenue(w, currency, today, tz_by_account):
    """_uninstall_with_revenue's inputs as built before this change: every reader on the name wrapper's rows."""
    from admob_iq.engine import adcfg, fc_calendar
    rev = build_static.admob_revenue(w.fetch_network(), "America/Los_Angeles", currency, today, tz_by_account)
    rev["all_apps"] = build_static.mediation_revenue(w.fetch_mediation(), rev["till"])
    rev["country"] = build_static.admob_country(w.fetch_country(), rev["till"])
    rev["country_m"] = build_static.admob_country_months(w.fetch_country(), rev["till"])
    till = date.fromisoformat(rev["till"])
    rev["cal"] = fc_calendar.seasons(w.fetch_mediation_unit(), till)
    rev["cal"]["hol"] = fc_calendar.holidays(w.fetch_country(), till)
    rev["cal"]["wk"] = fc_calendar.trigger_days(w.fetch_mediation_unit(), (till - timedelta(days=140)).isoformat(),
                                                till.isoformat())
    rev["adsrc"] = adcfg.Source(w.fetch_mediation_unit(), w.fetch_country(), rev["till"])
    return rev


def _src_out(src, ids):
    return {aid: (src.app([aid]), src.country([aid])) for aid in ids}


def test_the_revenue_inputs_are_the_history_rows_with_the_same_numbers(tmp_path, live):
    out, data = live(str(tmp_path))
    _, revenue = live.seen[-1]
    repo = _Spy.last
    w = build_static._DisambiguatedRepo(repo, build_static._account_names(data), build_static._app_names(data))
    assert w._map == {"app~puzzle": "Synth Renamed"}
    assert any(a is not b for a, b in zip(w.fetch_country(), repo._rows["country"]))   # (the wrapper copies those)
    src = revenue["adsrc"]
    assert src.mu is repo._rows["mu"] and src.cty is repo._rows["country"]            # the history's own lists
    old = _old_revenue(w, revenue["currency"], TODAY, {PUB: "America/Los_Angeles"})
    ids = sorted({r["app_id"] for r in repo._rows["mu"]})
    assert len(ids) == 2 and _src_out(src, ids) == _src_out(old.pop("adsrc"), ids)
    assert {k: v for k, v in revenue.items() if k != "adsrc"} == old


class _Strict(dict):
    """A history row that fails on any read of its app name and on any change."""

    def __getitem__(self, k):
        assert k != "app_name", "reads app_name"
        return super().__getitem__(k)

    def get(self, k, default=None):
        assert k != "app_name", "reads app_name"
        return super().get(k, default)

    def _no(self, *a, **k):
        raise AssertionError("changes a row")
    __setitem__ = __delitem__ = __ior__ = pop = popitem = setdefault = update = clear = _no


def _rows_for_readers():
    """Android ad-unit rows and country rows over two whole years (every season / holiday window the readers look at)."""
    mu, cty = [], []
    d = date(2024, 1, 1)
    while d <= date(2025, 12, 31):
        k = d.isoformat()
        for app, unit, name in (("app~one", "u1", "Splash_Ad"), ("app~two", "u2", "after_call_native")):
            mu.append(dict(report_date=k, account_id=PUB, app_id=app, app_name="Synth", ad_unit_id=unit,
                           unit_name=name, format="native", platform="Android", ad_requests=5000, matched_requests=4500,
                           impressions=4000 + d.day * 10, clicks=40, estimated_earnings_micros=6_000_000 + d.day * 1000,
                           currency_code="USD"))
            for cc in ("IN", "SA", "US"):
                cty.append(dict(report_date=k, account_id=PUB, app_id=app, app_name="Synth", country=cc,
                                ad_requests=900, matched_requests=800, impressions=700 + d.month,
                                clicks=7, estimated_earnings_micros=900_000 + d.day * 100, currency_code="USD"))
        d += timedelta(days=1)
    return mu, cty


def test_the_revenue_readers_never_read_app_name_nor_change_a_row():
    """F5's ground: each reader _uninstall_with_revenue hands the history's rows to reads no "app_name" and changes no
    row — so the name wrapper's copies (which differ only in "app_name") give the very same numbers."""
    from admob_iq.engine import adcfg, fc_calendar
    mu, cty = _rows_for_readers()
    net = [dict(r, country="US") for r in mu]
    till, tday = "2025-12-30", date(2025, 12, 30)

    def run(rows_mu, rows_cty, rows_net):
        src = adcfg.Source(rows_mu, rows_cty, till)
        return [build_static.admob_revenue(rows_net, "UTC", "USD", date(2025, 12, 31), {PUB: "Asia/Kolkata"}),
                build_static.mediation_revenue(rows_net, till), build_static.admob_country(rows_cty, till),
                build_static.admob_country_months(rows_cty, till), fc_calendar.seasons(rows_mu, tday),
                fc_calendar.holidays(rows_cty, tday), fc_calendar.trigger_days(rows_mu, "2025-08-01", till),
                src.app(["app~one", "app~two"]), src.country(["app~one"]), bool(src.cty)]
    plain = run(mu, cty, net)
    strict = run([_Strict(r) for r in mu], [_Strict(r) for r in cty], [_Strict(r) for r in net])
    assert strict == plain
    assert plain[4]["s"] and plain[6] and plain[7]["u"] and plain[8]          # (each reader read rows: not vacuous)
