"""Google Ads cost and downloads by COUNTRY × DAY (admob_iq.fetch.gads_geo_day, GADS_GEO + GADS_ARCHIVE) — offline,
against the geo tests' synthetic MCC (tests/test_gads_geo.py): the weekly cache (roas_geo_cache*.json.gz) is
byte-identical with or without the day capture (and when the capture breaks), every week cell = gads_geo.cell_cost(Σ of
its days), the day backfill (own budget, newest first, down to the spend cache's first day — the whole history, not the
weekly cache's 400 days; an archive done at a shallower floor resumes below its oldest day; more chunks a build while
behind, never more requests or time than its budget; own country map — the weekly map is only read; the gap an
out-of-order chunk leaves filled; the data edge counted only on stores that spent with every account asked; a store
that cannot answer now — a 403, an account that keeps failing, a cost row with no real rate — is a hole asked again,
given up after GD_HOLE_DAYS; an account gone from the MCC is unknown for good; a chunk cut by the budget is asked
again whole), what roi_build reads of it (old days known once covered, a day that
does not tie stays unknown), deterministic files, the counts-only line and the build wiring. All data is synthetic."""

import os
import re
import shutil
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq.fetch import gads_geo as gg
from admob_iq.fetch import gads_geo_day as gd
from admob_iq.fetch import google_ads
from tests.test_gads_geo import A1, A2, A3, FX, H, M, S1, S2, S3, SETTINGS, T0, TODAY, TOK, Clock, FakeAds, spend_of

DLINE = re.compile(r"^gads geo days: stores \d+, days \d+, backfill days \d+ \((filling|done|edge|waiting|off|skipped)\), "
                   r"ties \d+/\d+, calls \d+, errors \d+$")
PLAN = {A1: {S1: {"2840": 3, "2356": 2, None: 1}}, A2: {S2: {"2076": 1.5}}}


def files(d):
    out = {}
    for f in ("roas_geo_cache.json.gz", "roas_geo_cache.old.json.gz"):
        p = os.path.join(d, f)
        if os.path.exists(p):
            out[f] = open(p, "rb").read()
    return out


def build(data, spend, fake, t, today=TODAY, day=True, **kw):
    """One build's geo step (+ the day store) → (geo line, day line | None)."""
    store = gd.open_store(data, spend) if day else None
    g = gg.geo_step(SETTINGS, data, spend, today, now=lambda: t, clock=Clock(), search=fake.search, token=TOK,
                    fx_fn=FX.get, days=store)
    if store is None:
        return g, None
    return g, gd.day_step(SETTINGS, data, spend, today, store, clock=Clock(), search=fake.search, token=TOK,
                          fx_fn=FX.get, **kw)


@pytest.fixture
def dirs(tmp_path):
    return str(tmp_path / "plain"), str(tmp_path / "days")


def test_weekly_cache_byte_identical_with_the_day_capture(dirs):
    spend = spend_of(PLAN, "2025-01-01", "2026-09-23")
    plain, withd = dirs
    f1, f2 = FakeAds(PLAN, byid={"2076": {"cc": "BR"}}), FakeAds(PLAN, byid={"2076": {"cc": "BR"}})
    for i, t in enumerate((T0, T0 + H, T0 + 2 * H, T0 + 21 * H, T0 + 22 * H)):
        g1, _ = build(plain, spend, f1, t, day=False)
        g2, dl = build(withd, spend, f2, t)
        assert g1 == g2 and DLINE.match(dl), (g1, g2, dl)
        assert files(plain) == files(withd) and files(plain)
    assert sorted(os.listdir(os.path.join(withd, "ads_geo_day")))[-1] == "state.json.gz"


def test_every_week_cell_is_the_sum_of_its_days(dirs):
    spend = spend_of(PLAN, "2026-01-01", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN, ccy={A2: "USD"})
    g, dl = build(data, spend, fake, T0, max_calls=0)
    m = re.search(r"ties (\d+)/(\d+)", dl)
    assert int(m.group(1)) == int(m.group(2)) > 30, dl
    geo, day = gg.load_geo(data), gd.load(data)
    assert day["ccy"] == "INR"
    n = 0
    for sid, ws in geo["weeks"].items():
        for w, cells in ws.items():
            ds = [x for x in day["days"][sid] if gg._mon(x).isoformat() == w]
            assert ds, (sid, w)
            for cc, (cost, dl_) in cells.items():
                assert gg.cell_cost(sum((day["days"][sid][x].get(cc) or [0])[0] for x in ds)) == cost
                assert abs(sum((day["days"][sid][x].get(cc) or [0, 0])[1] for x in ds) - dl_) < 0.011 * len(ds)
                n += 1
    assert n > 30
    one = day["days"][S1]["2026-09-01"]
    assert one == {"US": [3 * 1_000_000, 0.3], "IN": [2 * 1_000_000, 0.2], "XX": [1_000_000, 0.1]}
    assert day["days"][S2]["2026-09-01"]["BR"] == [int(round(1.5 * 1_000_000 * FX["USD"] / FX["INR"])), 0.15]
    # keep: one app's stores only (the ROI country filter's read) — the same days, nothing of another store
    only = gd.load(data, keep={S1})
    assert only == {"ccy": day["ccy"], "days": {S1: day["days"][S1]}} and gd.load(data, keep=set())["days"] == {}
    assert gd.load(data) == day                                    # without keep: every store, as before


def test_day_backfill_newest_first_to_the_spend_cache_first_day(dirs):
    spend = spend_of(PLAN, "2025-01-01", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN)
    seen = []
    for i in range(12):
        n0 = len(fake.calls)
        g, dl = build(data, spend, fake, T0 + i * H)
        seen.append((dl, fake.calls[n0:]))
    st = gd.load_state(os.path.join(data, "ads_geo_day"), gd.GD_V, gd.DEFAULTS)
    assert st["done"] and st["bfrom"] == "2025-01-01"     # the spend cache's first day — deeper than today − 400 days
    assert (TODAY - date(2025, 1, 1)).days > gg.GEO_KEEP_DAYS                    # (the weekly cache's depth: its own)
    full = gd.GD_BACKFILL_CHUNKS * gd.GD_CHUNK_DAYS
    assert re.search(r"backfill days %d \(filling\)" % full, seen[0][0]), seen[0][0]
    assert seen[-1][0].endswith("(done), ties 0/0, calls 0, errors 0")
    first = min(x for v in gd.load(data)["days"].values() for x in v)
    assert first == "2025-01-01"
    weekly = gg.load_geo(data)["weeks"]
    assert min(w for ws in weekly.values() for w in ws) == "2025-08-18"               # weekly: 400 days, as before
    spend2 = spend_of(PLAN, "2026-05-01", "2026-09-23")                    # the spend cache's first day bounds it
    d2 = data + "2"
    for i in range(6):
        build(d2, spend2, FakeAds(PLAN), T0 + i * H)
    got = gd.load(d2)["days"]
    assert min(x for v in got.values() for x in v) == "2026-04-27"                   # whole weeks, as the weekly cache
    assert all(x in got[S1] for x in ("2026-04-27", "2026-04-30", "2026-05-01"))


def test_day_backfill_fills_the_gap_of_an_out_of_order_chunk(dirs):
    spend = spend_of(PLAN, "2025-01-01", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN)
    build(data, spend, fake, T0, day=False)                  # GADS_ARCHIVE off: the weekly refresh + backfill chunks
    assert not gg.load_geo(data)["done"]
    for i in range(1, 12):                                   # on while the weekly backfill is mid-way, no refresh due:
        build(data, spend, fake, T0 + i * H)                 # its older chunks land first, above them a gap …
    for i in range(12, 16):                                  # … the next day's refresh lands above the gap
        build(data, spend, fake, T0 + 21 * H + i * H)
    st = gd.load_state(os.path.join(data, "ads_geo_day"), gd.GD_V, gd.DEFAULTS)
    assert st["done"] and st["cov"] == [["2025-01-01", "2026-09-23"]] and st["bfrom"] == "2025-01-01"
    got = gd.load(data)["days"]
    span = [x.isoformat() for x in (date(2025, 1, 1) + timedelta(days=i) for i in range(631))]
    assert span[-1] == "2026-09-23" and all(sorted(got[sid]) == span for sid in (S1, S2))   # every day, no gap


def test_day_backfill_own_country_map_weekly_map_only_read(dirs, monkeypatch):
    monkeypatch.setattr(gg, "GEO_KEEP_DAYS", 70)                           # the weekly backfill stops early …
    plan = {A1: {S1: {"2840": 3, "2344": lambda d: 2 if d < "2026-05-01" else 0}}}
    spend = spend_of(plan, "2026-01-01", "2026-09-23")
    _, data = dirs
    fake = FakeAds(plan, byid={"2344": {"cc": "HK"}})
    build(data, spend, fake, T0)
    before = files(data)
    assert "2344" not in (gg.load_geo(data)["iso"])
    for i in range(1, 6):                                                    # … the day backfill reaches the old days
        store = gd.open_store(data, spend)
        gd.day_step(SETTINGS, data, spend, TODAY, store, clock=Clock(), search=fake.search, token=TOK, fx_fn=FX.get)
    assert files(data) == before                                             # the weekly cache never changed
    st = gd.load_state(os.path.join(data, "ads_geo_day"), gd.GD_V, gd.DEFAULTS)
    assert st["iso"] == {"2344": "HK"}
    assert gd.load(data)["days"][S1]["2026-03-02"]["HK"][0] == 2 * 1_000_000


def test_a_broken_capture_never_touches_the_weekly_cache(dirs, monkeypatch):
    spend = spend_of(PLAN, "2026-01-01", "2026-09-23")
    plain, withd = dirs
    build(plain, spend, FakeAds(PLAN), T0, day=False)

    def boom(*a, **k):
        raise ZeroDivisionError
    monkeypatch.setattr(gd.DayStore, "commit", boom)
    g, dl = build(withd, spend, FakeAds(PLAN), T0)
    assert files(plain) == files(withd)
    assert dl.endswith("(skipped), ties 0/0, calls 0, errors 0") and not os.path.exists(os.path.join(withd, "ads_geo_day"))


def test_day_files_deterministic_and_only_on_change(dirs):
    spend = spend_of(PLAN, "2026-03-01", "2026-09-23")
    a, b = dirs
    for d in (a, b):
        build(d, spend, FakeAds(PLAN), T0)
    lst = sorted(os.listdir(os.path.join(a, "ads_geo_day")))
    assert lst == sorted(os.listdir(os.path.join(b, "ads_geo_day")))
    for f in lst:
        assert open(os.path.join(a, "ads_geo_day", f), "rb").read() == open(os.path.join(b, "ads_geo_day", f), "rb").read()
    p = os.path.join(a, "ads_geo_day", "2026-07.json.gz")
    os.utime(p, (1, 1))
    build(a, spend, FakeAds(PLAN), T0 + H)                                 # nothing due: nothing rewritten
    assert os.path.getmtime(p) == 1


def test_wiring_two_lines_with_the_archive_one_without(tmp_path, monkeypatch, capsys):
    fake = FakeAds(PLAN)
    monkeypatch.setattr(google_ads, "_search", fake.search)
    monkeypatch.setattr(google_ads, "_access_token", lambda *a: TOK)
    monkeypatch.setattr(google_ads, "_fx_to_usd", FX.get)
    spend = spend_of(PLAN, "2026-07-01", "2026-09-23")
    d1, d2 = str(tmp_path / "a"), str(tmp_path / "b")
    build_static._gads_geo_step(dict(SETTINGS), d1, spend, TODAY)
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and err[0].startswith("gads geo: ") and not os.path.exists(os.path.join(d1, "ads_geo_day"))
    build_static._gads_geo_step(dict(SETTINGS, gads_archive=True), d2, spend, TODAY)
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 2 and err[0].startswith("gads geo: ") and DLINE.match(err[1]), err
    assert files(d1) == files(d2)
    monkeypatch.setattr(gd, "day_step", lambda *a, **k: 1 / 0)
    shutil.rmtree(d2)
    build_static._gads_geo_step(dict(SETTINGS, gads_archive=True), d2, spend, TODAY)
    err = capsys.readouterr().err.splitlines()
    assert err[1] == "gads geo days skipped: ZeroDivisionError" and files(d1) == files(d2)


def test_day_line_counts_only(dirs):
    spend = spend_of(PLAN, "2025-01-01", "2026-09-23")
    _, data = dirs
    _, dl = build(data, spend, FakeAds(PLAN, byid={"2076": {"cc": "BR"}}), T0)
    assert DLINE.match(dl)
    for s_ in (A1, A2, S1, S2, TOK, "US", "IN", "BR", "XX", "2840", "2076", "2026", "2025", "INR", "synth", "com."):
        assert s_ not in dl, (s_, dl)
    assert date.fromisoformat("2026-09-24") == TODAY


# ── the whole history: depth, resume, chunks a build, the edge, the rate, what roi_build reads ─────────────────────

def day_only(data, spend, fake, today=TODAY, clock=None, **kw):
    """One build's day backfill alone (no weekly step: nothing captured) → the day line."""
    kw.setdefault("fx_fn", FX.get)
    store = gd.open_store(data, spend)
    return gd.day_step(SETTINGS, data, spend, today, store, clock=clock or Clock(), search=fake.search, token=TOK, **kw)


def gstate(data):
    return gd.load_state(os.path.join(data, "ads_geo_day"), gd.GD_V, gd.DEFAULTS)


def g1_ranges(fake, n0=0):
    return [re.search(r"BETWEEN '([\d-]+)' AND '([\d-]+)'", q).groups() for _, k, q in fake.calls[n0:] if k == "G1"]


def test_depth_is_the_spend_cache_first_day_not_400_days(dirs):
    # ~2.3 years of spend: the day archive reaches its first day; the weekly cache keeps its own 400 days
    spend = spend_of(PLAN, "2024-06-03", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN)
    lines = [build(data, spend, fake, T0 + i * H)[1] for i in range(10)]
    st = gstate(data)
    assert st["done"] and st["cov"] == [["2024-06-03", "2026-09-23"]] and st["edge"] is None
    got = gd.load(data)["days"]
    assert min(min(v) for v in got.values()) == "2024-06-03" and (TODAY - date(2024, 6, 3)).days > 2 * gg.GEO_KEEP_DAYS
    assert len(got[S1]) == len(got[S2]) == (date(2026, 9, 23) - date(2024, 6, 3)).days + 1     # every day, no hole
    assert got[S1]["2024-06-03"] == {"US": [3 * M, 0.3], "IN": [2 * M, 0.2], "XX": [M, 0.1]}
    weekly = gg.load_geo(data)
    wfirst = min(w for ws in weekly["weeks"].values() for w in ws)
    assert wfirst >= (TODAY - timedelta(days=gg.GEO_KEEP_DAYS + 7)).isoformat()
    assert [ln.split("(")[1].split(")")[0] for ln in lines][-1] == "done" and "(filling)" in lines[0]


def test_a_done_archive_resumes_below_its_oldest_day(dirs):
    # done at a shallower floor (the spend cache then began later); the spend cache now goes deeper → "filling" again,
    # from the day below the archive's oldest — no covered day asked again — down to the new first day
    _, data = dirs
    fake = FakeAds(PLAN)
    shallow = spend_of(PLAN, "2026-03-02", "2026-09-23")
    for i in range(4):
        build(data, shallow, fake, T0 + i * H)
    st = gstate(data)
    assert st["done"] and st["cov"] == [["2026-03-02", "2026-09-23"]]
    deep = spend_of(PLAN, "2025-01-01", "2026-09-23")
    n0 = len(fake.calls)
    line = day_only(data, deep, fake)
    asked = g1_ranges(fake, n0)
    assert line.startswith("gads geo days:") and "(filling)" in line and not gstate(data)["done"]
    assert asked[0] == ("2026-02-02", "2026-03-01") and all(b <= "2026-03-01" for _, b in asked)   # newest first, below
    for _ in range(6):
        n1 = len(fake.calls)
        day_only(data, deep, fake)
        assert all(b < "2026-03-02" for _, b in g1_ranges(fake, n1))
    st = gstate(data)
    assert st["done"] and st["cov"] == [["2025-01-01", "2026-09-23"]] and st["bfrom"] == "2025-01-01"
    every = [(c, q) for c, k, q in fake.calls[n0:] if k == "G1"]
    assert len(every) == len(set(every))                                    # no chunk asked twice
    assert sorted(gd.load(data)["days"][S1]) == [x.isoformat() for x in (date(2025, 1, 1) + timedelta(days=i)
                                                                         for i in range(631))]


def test_chunks_a_build_while_behind_and_the_budget(dirs):
    spend = spend_of(PLAN, "2023-06-05", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN)
    build(data, spend, fake, T0)                                                  # the refresh: the newest range
    # far behind: GD_BACKFILL_CHUNKS chunks a build, each whole (Q-G1 + Q-G2 of both accounts), the request budget kept
    n0 = len(fake.calls)
    line = day_only(data, spend, fake)
    asked = g1_ranges(fake, n0)
    assert len(asked) == 2 * gd.GD_BACKFILL_CHUNKS and len(fake.calls) - n0 <= gd.GD_MAX_CALLS
    assert re.search(r"backfill days %d \(filling\), ties \d+/\d+, calls %d, errors 0$"
                     % (gd.GD_BACKFILL_CHUNKS * gd.GD_CHUNK_DAYS, len(fake.calls) - n0), line), line
    # the call budget: a chunk is never started without its accounts' calls + the country map's reserve
    for mc in (1, 6, 10, 13):                     # the roster, then 4 requests a chunk (2 accounts × Q-G1, Q-G2)
        n0 = len(fake.calls)
        line = day_only(data, spend, fake, max_calls=mc)
        used = len(fake.calls) - n0
        n = len(g1_ranges(fake, n0)) // 2
        room = (mc - 1 - 4 - gg.ISO_RESERVE) // 4 + 1 if mc - 1 >= 4 + gg.ISO_RESERVE else 0
        assert used <= mc and n == room and used == 1 + 4 * n, (mc, used, n)      # no chunk cut half-way
    # the time budget: a chunk is not started without the longest chunk's time left (every request moves the clock)
    clk = Clock(step=1.0)
    fake.clock = clk
    n0 = len(fake.calls)
    cov0 = gstate(data)["cov"]
    t0 = clk.t
    line = day_only(data, spend, fake, clock=clk, max_sec=10)
    n = len(g1_ranges(fake, n0)) // 2
    assert n == 2 and len(fake.calls) - n0 == 1 + 4 * n and clk.t - t0 <= 10, (n, clk.t, line)   # no request wasted
    down = date.fromisoformat(cov0[-1][0]) - timedelta(days=2 * gd.GD_CHUNK_DAYS)
    assert gstate(data)["cov"][-1][0] == down.isoformat()
    fake.clock = None
    # on to the first day: never more than GD_BACKFILL_CHUNKS chunks a build, nor than the calls allow
    for mc in (gd.GD_MAX_CALLS, 1 + 4 * 3 + gg.ISO_RESERVE) + (gd.GD_MAX_CALLS,) * 12:
        if gstate(data)["done"]:
            break
        n0 = len(fake.calls)
        togo = -(-(date.fromisoformat(gstate(data)["cov"][-1][0]) - date(2023, 6, 5)).days // gd.GD_CHUNK_DAYS)
        day_only(data, spend, fake, max_calls=mc)
        n = len(g1_ranges(fake, n0)) // 2
        assert n == min(togo, gd.GD_BACKFILL_CHUNKS, (mc - 1 - 4 - gg.ISO_RESERVE) // 4 + 1), (togo, n, mc)
    assert gstate(data)["done"] and gstate(data)["cov"] == [["2023-06-05", "2026-09-23"]]
    assert (gd.GD_MAX_CALLS, gd.GD_MAX_SEC, gg.GEO_MAX_CALLS, gg.GEO_MAX_SEC) == (80, 90, 160, 150)   # weekly: its own
    assert (gg.GEO_BACKFILL_CHUNKS, gg.GEO_KEEP_DAYS) == (2, 400)                              # weekly: as before


def test_the_edge_counts_only_stores_that_spent_with_every_account_asked(dirs):
    young = {A1: {S1: {"2840": 3}}, A2: {S2: {"2076": lambda d: 1.5 if d >= "2026-06-01" else 0}}}
    spend = spend_of(young, "2024-01-01", "2026-09-23")
    plain, data = dirs
    # a young store (no spend before it began: its account not even asked there) never makes an edge
    fake = FakeAds(young)
    build(data, spend, fake, T0)
    for _ in range(8):
        day_only(data, spend, fake)
    st = gstate(data)
    assert st["done"] and st["edge"] is None and st["cov"] == [["2024-01-01", "2026-09-23"]]
    assert all(r[0] >= "2026" for r in fake.ranges("G1", A2)) and min(gd.load(data)["days"][S1]) == "2024-01-01"
    # Google Ads has no row before 2025-02-01 though the old store spent: two such chunks in a row = the edge; the days
    # before it are not written (unknown), the line says "edge"
    fake = FakeAds(young, lo="2025-02-01")
    build(plain, spend, fake, T0)
    lines = [day_only(plain, spend, fake) for _ in range(8)]
    st = gstate(plain)
    edge = date.fromisoformat(st["edge"])               # the second chunk in a row wholly before the rows' first day
    assert st["done"] and date(2025, 2, 1) - timedelta(days=3 * gd.GD_CHUNK_DAYS) <= edge \
        <= date(2025, 2, 1) - timedelta(days=gd.GD_CHUNK_DAYS) and "(edge)" in lines[-1]
    got = gd.load(plain)["days"][S1]
    assert all(got[x] == {} for x in got if x < "2025-02-01")       # the chunk across the first row: those days {} …
    assert min(got) == (edge + timedelta(days=gd.GD_EDGE_CHUNKS * gd.GD_CHUNK_DAYS)).isoformat()   # … the empty ones,
    assert gstate(plain)["cov"][0][0] == st["edge"]                                         # settled, nothing written
    # a store whose old spend was another account's (gone from the MCC): the account still there answers nothing —
    # no evidence of the edge ("skip": nothing written, those days unknown), the backfill goes on to the first day
    # (and before that, a store of that account alone: nothing to ask — settled, nothing written, no days counted)
    s4 = "com.synth.delta"
    gone = {A1: {S1: {"2840": lambda d: 3 if d >= "2026-01-01" else 0}, S3: {"2840": 0}},
            A3: {S3: {"2840": lambda d: 2 if "2025-04-01" <= d < "2026-01-01" else 0},
                 s4: {"2840": lambda d: 1 if d < "2025-04-01" else 0}}}
    spend = spend_of(gone, "2025-01-01", "2026-09-23")
    d3 = data + "3"
    fake = FakeAds(gone)
    fake.gone = {A3}
    build(d3, spend, fake, T0)
    top = gstate(d3)["cov"][-1][0]
    lines = [day_only(d3, spend, fake) for _ in range(6)]
    st = gstate(d3)
    assert st["done"] and st["edge"] is None and st["cov"][0][0] == "2025-01-01", st
    assert not st["holes"] and {x[2] for x in st["lost"]} == {S3, s4}          # gone: unknown for good, no hole
    assert not fake.ranges("G1", A3) and S3 not in gd.load(d3)["days"] and s4 not in gd.load(d3)["days"]
    assert "(done)" in lines[-1] and st["first"] >= "2025-12-01"            # nothing committed below S1's spend …
    bdays = sum(int(re.search(r"backfill days (\d+)", ln).group(1)) for ln in lines)
    assert bdays <= (date.fromisoformat(top) - date(2025, 12, 1)).days     # … and no settled-empty day counted


def every(a, b):
    return [x.isoformat() for x in (date.fromisoformat(a) + timedelta(days=i)
                                    for i in range((date.fromisoformat(b) - date.fromisoformat(a)).days + 1))]


def test_no_rate_for_an_account_holds_only_its_stores(dirs, monkeypatch):
    # an account billed in a currency the rate source has no rate for, its store spending only in May 2025: the cost
    # rows it returns are never written at a guessed rate (that store-range is a hole, errors counted); every other
    # store goes on to the spend cache's first day; a hole is not asked while there is still no rate (0 calls); once the
    # rate is there, only the hole is asked and its cost goes ccy → USD → base
    old = {A1: {S1: {"2840": 3}}, A2: {S2: {"2076": lambda d: 1.5 if "2025-05-01" <= d < "2025-06-01" else 0}}}
    spend = spend_of(old, "2024-01-01", "2026-09-23")
    _, data = dirs
    fake = FakeAds(old, ccy={A2: "EUR"})
    build(data, spend, fake, T0)
    lines = [day_only(data, spend, fake) for _ in range(8)]
    st = gstate(data)
    assert st["cov"] == [["2024-01-01", "2026-09-23"]] and not st["done"] and st["bfails"] == 0
    got = gd.load(data)["days"]
    assert sorted(got[S1]) == every("2024-01-01", "2026-09-23") and S2 not in got   # base store: whole history
    assert {h[2] for h in st["holes"]} == {S2} and st["holes"][0][0] <= "2025-05-01" <= "2025-05-31" <= st["holes"][-1][1]
    assert fake.ranges("G1", A2) and all(b >= "2025-05-01" and a <= "2025-05-31" for a, b in fake.ranges("G1", A2))
    assert sum(int(re.search(r"errors (\d+)$", ln).group(1)) for ln in lines) == len(fake.ranges("G1", A2))
    assert "(filling)" in lines[-1] and lines[-1].endswith("calls 0, errors 0")    # still no rate: the hole waits
    n0 = len(fake.calls)
    assert "(filling)" in day_only(data, spend, fake, today=TODAY + timedelta(days=1)) and len(fake.calls) - n0 <= 1
    fx = dict(FX, EUR=1.08)
    n0 = len(fake.calls)
    lines = [day_only(data, spend, fake, today=TODAY + timedelta(days=2), fx_fn=fx.get) for i in range(2)]
    st = gstate(data)
    assert st["done"] and not st["holes"] and "(done)" in lines[-1]
    assert {c for c, k, _ in fake.calls[n0:] if k in ("G1", "G2")} == {A2}             # only the hole's account
    cell = gd.load(data)["days"][S2]["2025-05-05"]["BR"]
    assert cell[0] == int(round(1.5 * M * fx["EUR"] / fx["INR"])) and cell[1] == 0.15
    # the default rate source: google_ads._fx_to_usd's blind 1.0 for a currency it knows nothing of is no rate
    monkeypatch.setattr(google_ads, "_fx_to_usd", lambda c: {"EUR": 1.08, "INR": 0.012}.get(c, 1.0))
    assert (gd._fx_real("XYZ"), gd._fx_real("EUR"), gd._fx_real("USD"), gd._fx_real("INR")) == (None, 1.08, 1.0, 0.012)


def test_a_403_blip_is_a_hole_asked_again_once_the_skip_ends(dirs):
    # one HTTP 403 of an account in the deep backfill: its store's days are not written (the 7-day skip holds it in the
    # chunks after too) — holes, not settled for good; the 7 days pass: only those store-ranges are asked again
    spend = spend_of(PLAN, "2024-06-03", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN)
    build(data, spend, fake, T0)
    top = gstate(data)["cov"][-1][0]
    blip = []

    def fail(acct, kind, q):
        if acct == A2 and kind == "G1" and not blip:
            blip.append(q)
            return "HTTP 403 PERMISSION_DENIED"
    fake.fail = fail
    lines = [day_only(data, spend, fake) for _ in range(8)]
    st = gstate(data)
    assert blip and st["cov"] == [["2024-06-03", "2026-09-23"]] and not st["done"] and "(filling)" in lines[-1]
    assert {h[2] for h in st["holes"]} == {S2} and st["skip"][A2] == (TODAY + timedelta(days=7)).isoformat()
    got = gd.load(data)["days"]
    gone = [x for x in every("2024-06-03", top) if x not in got[S2]]
    assert gone == every("2024-06-03", (date.fromisoformat(top) - timedelta(days=1)).isoformat())
    assert sorted(x for h in st["holes"] for x in every(h[0], h[1])) == gone          # every unwritten day a hole
    assert sorted(got[S1]) == every("2024-06-03", "2026-09-23")
    hr = sorted({(h[0], h[1]) for h in st["holes"]})
    n0 = len(fake.calls)
    assert day_only(data, spend, fake, today=TODAY + timedelta(days=6)).endswith("calls 0, errors 0")  # skip holds
    later = TODAY + timedelta(days=7)
    lines = [day_only(data, spend, fake, today=later) for _ in range(8)]
    st = gstate(data)
    assert st["done"] and not st["holes"] and "(done)" in lines[-1]
    asked = [(c, k) for c, k, _ in fake.calls[n0:] if k in ("G1", "G2")]
    assert {c for c, _ in asked} == {A2} and sorted(g1_ranges(fake, n0)) == hr       # each hole once, nothing else
    assert all("backfill days 0 " in ln for ln in lines)                     # holes filled: no new days counted
    got = gd.load(data)["days"]
    assert sorted(got[S2]) == sorted(got[S1]) == every("2024-06-03", "2026-09-23")
    assert got[S2]["2024-06-03"] == {"BR": [int(round(1.5 * M)), 0.15]}


def test_a_hole_that_never_answers_is_given_up_unknown(dirs):
    # an account that answers 403 for good (cancelled, still listed): asked again once a skip (one request, not one a
    # hole); after GD_HOLE_DAYS its holes are given up — those store-days stay unknown ("lost"), the archive is done
    spend = spend_of(PLAN, "2025-01-01", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN)
    build(data, spend, fake, T0)
    fake.fail = lambda acct, kind, q: "HTTP 403 CUSTOMER_NOT_ENABLED" if acct == A2 and kind == "G1" else None
    for _ in range(5):
        day_only(data, spend, fake)
    st = gstate(data)
    n_holes, n0 = len(st["holes"]), fake.n("G1", A2)
    assert n_holes > 10 and not st["done"] and st["cov"] == [["2025-01-01", "2026-09-23"]]
    lines = [day_only(data, spend, fake, today=TODAY + timedelta(days=k)) for k in range(1, gd.GD_HOLE_DAYS + 3)]
    st = gstate(data)
    assert st["done"] and not st["holes"] and len(st["lost"]) == n_holes and "(done)" in lines[-1]
    assert all("(filling)" in ln for ln in lines[:gd.GD_HOLE_DAYS - 1])
    assert fake.n("G1", A2) - n0 == len(range(7, gd.GD_HOLE_DAYS, 7))      # once a skip: days 7, 14, 21, 28
    assert min(gd.load(data)["days"][S2]) >= st["lost"][-1][1]


def test_an_account_that_keeps_failing_holds_only_its_stores_after_the_back_off(dirs):
    # a non-403 error of one account on old dates: the chunk fails (asked again, GD_FAIL_BACKOFF tries a day); the next
    # day that account's stores are a hole and every other store goes on below; the error gone, the hole is filled
    spend = spend_of(PLAN, "2025-01-01", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN)
    build(data, spend, fake, T0)
    bad = {"on": True}
    fake.fail = lambda acct, kind, q: ("HTTP 500 INTERNAL" if bad["on"] and acct == A2 and kind == "G1"
                                       and re.search(r"BETWEEN '([\d-]+)'", q).group(1) < "2025-06-01" else None)
    for _ in range(6):
        day_only(data, spend, fake)
    st = gstate(data)
    assert st["bfails"] == gd.GD_FAIL_BACKOFF and st["cov"][-1][0] >= "2025-05-01" and not st["holes"]
    lines = [day_only(data, spend, fake, today=TODAY + timedelta(days=1)) for _ in range(4)]
    st = gstate(data)
    assert st["cov"] == [["2025-01-01", "2026-09-23"]] and {h[2] for h in st["holes"]} == {S2} and not st["done"]
    assert sorted(gd.load(data)["days"][S1]) == every("2025-01-01", "2026-09-23") and "(filling)" in lines[-1]
    bad["on"] = False
    lines = [day_only(data, spend, fake, today=TODAY + timedelta(days=2)) for _ in range(3)]
    st = gstate(data)
    assert st["done"] and not st["holes"] and sorted(gd.load(data)["days"][S2]) == every("2025-01-01", "2026-09-23")


def test_a_chunk_cut_by_the_budget_is_asked_again_never_settled(dirs, monkeypatch):
    # the time stop (or a quota error) between an account's Q-G1 and its Q-G2: the chunk is dropped, not settled with
    # downloads unknown — asked again next build, whole
    spend = spend_of(PLAN, "2025-01-01", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN)
    build(data, spend, fake, T0)
    cov0 = gstate(data)["cov"]
    monkeypatch.setattr(gg, "GEO_WORKERS", 1)                     # one request at a time: the order is fixed
    clk = Clock(step=1.0)
    fake.clock = clk
    n0 = len(fake.calls)
    line = day_only(data, spend, fake, clock=clk, max_sec=3.5)
    assert [k for _, k, _ in fake.calls[n0:]] == ["ROSTER", "G1", "G2", "G1"]          # Q-G2 of the 2nd refused
    assert gstate(data)["cov"] == cov0 and "backfill days 0 (filling)" in line
    dl_null = [(s, x) for s, v in gd.load(data)["days"].items() for x, c in v.items() for w in c.values() if w[1] is None]
    assert not dl_null
    fake.clock = None
    hit = []
    fake.fail = lambda acct, kind, q: ("HTTP 429 RESOURCE_EXHAUSTED" if acct == A1 and kind == "G2" and not hit
                                       and not hit.append(1) else None)
    day_only(data, spend, fake)
    assert hit and gstate(data)["cov"] == cov0                                           # a quota stop: the same
    day_only(data, spend, fake)
    st = gstate(data)
    a = date.fromisoformat(cov0[-1][0]) - timedelta(days=gd.GD_CHUNK_DAYS)
    assert st["cov"][-1][0] < a.isoformat()
    got = gd.load(data)["days"]
    assert got[S2][a.isoformat()] == {"BR": [int(round(1.5 * M)), 0.15]} and got[S1][a.isoformat()]["US"] == [3 * M, 0.3]
    # the first chunk of a build is not started past half the time budget (no chunk's time measured yet)
    clk = Clock(step=1.0)
    fake.clock = clk
    n0 = len(fake.calls)
    day_only(data, spend, fake, clock=clk, max_sec=1.5)
    assert [k for _, k, _ in fake.calls[n0:]] == ["ROSTER"] and gstate(data)["cov"] == st["cov"]


def test_roi_reads_old_days_known_once_covered_and_untied_days_unknown(dirs):
    # roi_build._geo_app over the archive: a day older than the weekly cache's 400 days is unknown until the day
    # backfill covers it, then known with the real country split; a covered day whose split does not tie to the spend
    # cache stays unknown ("off"), never forced
    from admob_iq import roi_build as rb
    _, data = dirs
    fake = FakeAds(PLAN)
    shallow = spend_of(PLAN, "2025-08-18", "2026-09-23")
    for i in range(4):
        build(data, shallow, fake, T0 + i * H)
    deep = spend_of(PLAN, "2024-06-03", "2026-09-23")
    off = "2024-07-10"
    deep["daily"][S1][off] = int(deep["daily"][S1][off] * 1.2)            # the spend cache says 20% more that day
    old = [date(2024, 7, 8) + timedelta(days=i) for i in range(5)]
    sp = {"first": "2024-06-03", "till": "2026-09-23"}

    def read():
        return rb._geo_app(gd.load(data, keep={S1}), [S1], deep["daily"], sp, old)
    cost, unk, st = read()
    assert unk == set(old) and st["known_days"] == 0 and st["untied_days"] == 0 and not cost
    for _ in range(8):
        day_only(data, deep, fake)
    assert gstate(data)["done"]
    cost, unk, st = read()
    assert unk == {date(2024, 7, 10)} and st["untied_days"] == 1 and st["known_days"] == 4
    assert cost["US"][date(2024, 7, 8)] == (3 * M, 0.3) and cost["XX"][date(2024, 7, 12)] == (M, 0.1)
    assert date(2024, 7, 10) not in cost["US"]
