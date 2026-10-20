"""Google Ads cost and downloads by COUNTRY × DAY (admob_iq.fetch.gads_geo_day, GADS_GEO + GADS_ARCHIVE) — offline,
against the geo tests' synthetic MCC (tests/test_gads_geo.py): the weekly cache (roas_geo_cache*.json.gz) is
byte-identical with or without the day capture (and when the capture breaks), every week cell = gads_geo.cell_cost(Σ of
its days), the day backfill (own budget, newest first, bounded by 400 days / the spend cache's first day, own country
map — the weekly map is only read, the gap an out-of-order chunk leaves filled), deterministic files, the counts-only
line and the build wiring. All data is synthetic."""

import os
import re
import shutil
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq.fetch import gads_geo as gg
from admob_iq.fetch import gads_geo_day as gd
from admob_iq.fetch import google_ads
from tests.test_gads_geo import A1, A2, FX, H, S1, S2, SETTINGS, T0, TODAY, TOK, Clock, FakeAds, spend_of

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


def test_day_backfill_newest_first_bounded_own_budget(dirs):
    spend = spend_of(PLAN, "2025-01-01", "2026-09-23")
    _, data = dirs
    fake = FakeAds(PLAN)
    seen = []
    for i in range(12):
        n0 = len(fake.calls)
        g, dl = build(data, spend, fake, T0 + i * H)
        seen.append((dl, fake.calls[n0:]))
    st = gd.load_state(os.path.join(data, "ads_geo_day"), gd.GD_V, gd.DEFAULTS)
    assert st["done"] and st["bfrom"] == "2025-08-18"     # today − 400 days (the weekly backfill's chunks, captured
                                                          # too, start on that week's Monday)
    assert re.search(r"backfill days 56 \(filling\)", seen[0][0]), seen[0][0]
    assert seen[-1][0].endswith("(done), ties 0/0, calls 0, errors 0")
    first = min(x for v in gd.load(data)["days"].values() for x in v)
    assert first == "2025-08-18"
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
    assert st["done"] and st["cov"] == [["2025-08-18", "2026-09-23"]] and st["bfrom"] == "2025-08-18"
    got = gd.load(data)["days"]
    span = [x.isoformat() for x in (date(2025, 8, 18) + timedelta(days=i) for i in range(402))]
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
