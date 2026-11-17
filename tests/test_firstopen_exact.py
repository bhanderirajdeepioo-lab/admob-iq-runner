"""🆕 First open tab — EXACT COUNTS (admob_iq.firstopen_build; 17 Nov 2026), on made-up stores: a day the First open store
read SAMPLED takes first_open / splash / home from the country store's exact day (final, unsampled, not held, not short,
the same screens) and says so (x = 1) — the status then from exact numbers; the summary's "sample" from the days still
sampled, "sample_other" for the steps that stay sampled; every other day as before (an unsampled day, a country day not
final / sampled / held / gone / collapsed / with other screens / malformed); no or a broken country store: the rows as
before; the switch off: every row and the summary exactly as before; the log line; the settings and the workflow."""
import gzip
import importlib
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import firstopen_build as fb
from admob_iq.db import write_json_gz_stable
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_firstopen_cc as fc
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc)
STEPS = {"splash": "SplashActivity", "home": "MainActivity", "language": "LanguageActivity"}
AID = "a~1"
SAMPLED = [(date(2026, 10, 1) + timedelta(days=i)).isoformat() for i in range(11)]     # Oct 1 … 11
EXACT = [1020, 1000, 600]                                       # the country store's day (exact)


def _main(data, sampled=SAMPLED, smp=0.2, steps=STEPS):
    """60 days to 13 Oct: Splash 1000, Home 600 (60 %) — but on the `sampled` days GA4's sampled estimate says Home 900."""
    d0, recs = date(2026, 10, 13) - timedelta(days=59), {}
    for i in range(60):
        d = (d0 + timedelta(days=i)).isoformat()
        s = d in sampled
        h = 900 if s else 600
        recs[d] = dict(first_open=1100 if s else 1020, splash=1000, home=h, splash_any=1000, home_any=h, language=500,
                       **({"sample": smp} if s else {}))
    write_json_gz_stable(gf.store_path(data, AID), {"v": gf.STORE_V, "app_id": AID, "package": "com.example.a",
                                                     "time_zone": "Asia/Kolkata", "steps": steps, "days": recs})


def _cc(data, days=SAMPLED, t=EXACT, age=3, odd=None, **kw):
    """The country store's records of `days`: unsampled, every user in a named country, read `age` days after the day
    (never after NOW: the newest final day read 2 days after, as a run of NOW reads it) — `kw` changes them; `odd`:
    {D: t} days of their own."""
    recs = {}
    for d in days:
        at = min(date.fromisoformat(d) + timedelta(days=age), NOW.date())
        tt = (odd or {}).get(d, t)
        r = {"c": {"XA": list(tt)} if isinstance(tt, list) else {}, "t": tt if not isinstance(tt, list) else list(tt),
             "smp": None, "fin": (at - date.fromisoformat(d)).days >= 3, "sg": fc.sig(STEPS),
             "at": at.isoformat() + "T00:05:00Z"}
        r.update(kw)
        recs[d] = r
    write_json_gz_stable(fc.store_path(data, AID), {"v": fc.STORE_V, "app_id": AID, "days": recs})


def _run(tmp_path, s=None):
    data, out = str(tmp_path / "data"), str(tmp_path / "site")
    os.makedirs(out, exist_ok=True)
    assert fb.run({}, data, out, {} if s is None else s, now=NOW) == ["/firstopen*"]
    with gzip.open(os.path.join(out, fb.FILE), "rt", encoding="utf-8") as f:
        body = json.load(f)
    rows = {r[0]: r for r in body["apps"][0]["days"]}
    return body["summary"][0], rows, fb.pop_line()


@pytest.fixture
def data(tmp_path):
    d = str(tmp_path / "data")
    os.makedirs(os.path.join(d, gf.DIR))
    os.makedirs(os.path.join(d, fc.DIR))
    return d


def test_a_sampled_day_takes_the_country_stores_exact_three(tmp_path, data):
    _main(data)
    _cc(data)
    x, rows, line = _run(tmp_path)
    for d in SAMPLED:
        assert rows[d][1:4] == EXACT and rows[d][fb.XI] == 1 and rows[d][fb.SX] == 0.2   # exact, said so
        assert rows[d][5] == 900 and rows[d][6] == 500                  # the other steps: GA4's (sampled) as they were
    assert rows["2026-09-30"][1:4] == [1020, 1000, 600] and rows["2026-09-30"][fb.XI] == 0
    assert abs(x["s2h"] - 0.6) < 1e-9 and abs(x["usual"] - 0.6) < 1e-9     # the status from exact numbers (sampled:
    assert x["status"] == "Normal"                                  # 0.9 — "Better" by 30 points that never were)
    assert x["sample"] is None and x["sample_other"] == 0.2         # the three exact all week; the rest still sampled
    assert line.endswith(", exact days 11")


def test_without_the_swap_the_sampled_estimate_would_rule_the_status(tmp_path, data):
    _main(data)
    _cc(data)
    x, rows, line = _run(tmp_path, {"firstopen_exact": False})
    assert abs(x["s2h"] - 0.9) < 1e-9 and x["status"] == "Better" and x["sample"] == 0.2


@pytest.mark.parametrize("kw", [{"age": 1}, {"smp": 0.5}, {"ho": 1}, {"sg": "other"}, {"none": True},
                                {"t": [1020, 1000]}, {"t": "x"}, {"t": [40, 30, 20], "c": {"XA": [40, 30, 20]}},
                                {"c": {"XA": [500, 500, 300]}}])
def test_only_a_final_unsampled_whole_country_day_with_the_same_screens(tmp_path, data, kw):
    """Read before the day was final here / sampled / held (an earlier read kept) / other screens / gone / malformed /
    collapsed (far under the First open store's count) / half the first opens in no named country: the row as GA4's
    sampled read had it."""
    _main(data)
    _cc(data, **kw)
    x, rows, line = _run(tmp_path)
    for d in SAMPLED:
        assert rows[d][1:4] == [1100, 1000, 900] and rows[d][fb.XI] == 0
    assert x["sample"] == 0.2 and line.endswith(", exact days 0")


def test_an_unsampled_day_is_never_swapped(tmp_path, data):
    _main(data, sampled=[])
    _cc(data, t=[1, 1, 1], c={"XA": [1, 1, 1]})                    # (even a country day far off: never used)
    x, rows, line = _run(tmp_path)
    assert all(r[1:4] == [1020, 1000, 600] and r[fb.XI] == 0 for r in rows.values()) and x["sample"] is None
    assert x["sample_other"] is None


def test_some_days_swapped_the_summary_marks_the_rest(tmp_path, data):
    _main(data)
    _cc(data, days=SAMPLED[:8])                                     # Oct 1 … 8 exact; 9 … 11 still sampled
    x, rows, line = _run(tmp_path)
    assert [rows[d][fb.XI] for d in SAMPLED] == [1] * 8 + [0] * 3 and x["sample"] == 0.2 and x["sample_other"] == 0.2
    assert abs(x["s2h"] - (4 * 600 + 3 * 900) / 7000) < 1e-6        # the week: 4 exact days + 3 sampled (Oct 5 … 11)


def test_no_or_a_broken_country_store_leaves_the_rows_as_they_are(tmp_path, data):
    _main(data)
    x, rows, line = _run(tmp_path)
    assert all(r[fb.XI] == 0 for r in rows.values()) and rows[SAMPLED[0]][1:4] == [1100, 1000, 900]
    with open(fc.store_path(data, AID), "wb") as f:
        f.write(b"not a gzip")
    x, rows, line = _run(tmp_path)
    assert all(r[fb.XI] == 0 for r in rows.values()) and line.endswith(", exact days 0")
    assert fb.exact_days(data, {"app_id": AID, "days": {SAMPLED[0]: {"sample": 0.2}}}) == {}


def test_the_switch_off_gives_every_row_and_the_summary_as_before(tmp_path, data):
    _main(data)
    _cc(data)
    x, rows, line = _run(tmp_path, {"firstopen_exact": False})
    assert all(len(r) == fb.SX + 1 for r in rows.values()) and rows[SAMPLED[0]][1:4] == [1100, 1000, 900]
    assert "sample_other" not in x and "exact days" not in line
    assert fb.exact_on({}) and fb.exact_on({"firstopen_exact": True}) and not fb.exact_on({"firstopen_exact": False})


def test_the_country_file_is_never_touched_by_it(tmp_path, data):
    _main(data)
    _cc(data)
    out = str(tmp_path / "site")
    _run(tmp_path)
    with gzip.open(os.path.join(out, fb.cc_file(gu.file_key(AID))), "rb") as f:
        on = f.read()
    _run(tmp_path, {"firstopen_exact": False})
    with gzip.open(os.path.join(out, fb.cc_file(gu.file_key(AID))), "rb") as f:
        assert f.read() == on


def test_the_newest_final_day_counts_once_read_two_days_after_it(tmp_path, data):
    """Oct 11 (final here on Oct 13) read by the country store on Oct 13: used — the 7 days all exact, no "≈"."""
    _main(data)
    _cc(data)
    x, rows, line = _run(tmp_path)
    assert rows["2026-10-11"][fb.XI] == 1 and x["sample"] is None


def test_a_step_collapsed_against_the_days_around_it_nothing_or_no_splash_is_refused(tmp_path, data):
    _main(data)
    _cc(data, odd={"2026-10-04": [1020, 1000, 30], "2026-10-05": [1020, 300, 200], "2026-10-06": [0, 0, 0],
                   "2026-10-07": [1020, 0, 0], "2026-10-08": [150, 140, 90]})
    x, rows, line = _run(tmp_path)
    assert [rows[d][fb.XI] for d in SAMPLED] == [1, 1, 1, 0, 0, 0, 0, 0, 1, 1, 1]
    assert rows["2026-10-04"][1:4] == [1100, 1000, 900]           # as GA4's sampled read had it


def _main_days(data, recs_over, sampled=SAMPLED):
    """_main, then some days of the First open store changed: {D: {field: value}}."""
    _main(data, sampled=sampled)
    st = gf.load_store(gf.store_path(data, AID))
    for d, kv in recs_over.items():
        st["days"][d].update(kv)
    write_json_gz_stable(gf.store_path(data, AID), st)


def test_a_partial_collapse_under_half_of_every_reference_is_refused(tmp_path, data):
    """Oct 5: 400 first opens — under half the First open store's count (1100) AND the days around (1020): refused;
    Oct 6: 600 against a sampled 1300 (0.46) but 0.59 of the days around — one reference may be off: used."""
    _main_days(data, {"2026-10-06": {"first_open": 1300}})
    _cc(data, odd={"2026-10-05": [400, 390, 240], "2026-10-06": [600, 590, 350]})
    x, rows, line = _run(tmp_path)
    assert rows["2026-10-05"][fb.XI] == 0 and rows["2026-10-06"][fb.XI] == 1


def test_first_opens_far_under_the_days_around_are_refused_even_over_a_low_sampled_count(tmp_path, data):
    """Oct 5: GA4's sampled count low (150), the country day 100 (0.67 of it) — but under a fifth of the days around
    (1020): refused (EX_LOW)."""
    _main_days(data, {"2026-10-05": {"first_open": 150, "splash": 140, "home": 90}})
    _cc(data, odd={"2026-10-05": [100, 95, 60]})
    x, rows, line = _run(tmp_path)
    assert rows["2026-10-05"][fb.XI] == 0 and rows["2026-10-04"][fb.XI] == 1


def test_with_no_days_around_a_home_collapse_is_judged_by_the_reads_own_rate(tmp_path, data):
    """One country day only (no days around): Home 30 of Splash 1000 against the First open read's own 90 %: refused;
    a Home of 700 (70 %, within the sampled read's error): used."""
    _main(data)
    _cc(data, days=["2026-10-05"], t=[1020, 1000, 30])
    x, rows, line = _run(tmp_path)
    assert rows["2026-10-05"][fb.XI] == 0
    _cc(data, days=["2026-10-05"], t=[1020, 1000, 700])
    x, rows, line = _run(tmp_path)
    assert rows["2026-10-05"][fb.XI] == 1 and rows["2026-10-05"][1:4] == [1020, 1000, 700]


def test_a_small_apps_rates_are_never_judged_on_a_handful_of_users(tmp_path, data):
    """Splash 40 / Home 10 a day (under REF_MIN at Home): a day's Home of 2 is not a collapse to judge — used."""
    d0, recs = date(2026, 10, 13) - timedelta(days=59), {}
    for i in range(60):
        d = (d0 + timedelta(days=i)).isoformat()
        recs[d] = dict(first_open=45, splash=40, home=12, sample=0.3) if d in SAMPLED else dict(first_open=45, splash=40,
                                                                                                 home=10)
    write_json_gz_stable(gf.store_path(data, AID), {"v": gf.STORE_V, "app_id": AID, "package": "com.example.a",
                                                     "time_zone": "Asia/Kolkata", "steps": STEPS, "days": recs})
    _cc(data, t=[44, 40, 10], odd={"2026-10-05": [44, 40, 2]})
    x, rows, line = _run(tmp_path)
    assert rows["2026-10-05"][fb.XI] == 1 and rows["2026-10-05"][1:4] == [44, 40, 2]


def test_the_screens_of_each_days_last_read(tmp_path, data):
    """The screens changed on Oct 8 (from OLD): the First open store's days up to Sep 23 were last read with OLD (it reads
    a day again for 14 days), later ones with the current screens — a country day counts only with the same."""
    old = {"splash": "OldSplash", "home": "OldHome"}
    d0, recs = date(2026, 10, 13) - timedelta(days=59), {}
    for i in range(60):
        d = (d0 + timedelta(days=i)).isoformat()
        recs[d] = dict(first_open=1100, splash=1000, home=900, sample=0.2)
    write_json_gz_stable(gf.store_path(data, AID), {"v": gf.STORE_V, "app_id": AID, "package": "com.example.a",
                                                     "time_zone": "Asia/Kolkata", "steps": STEPS, "days": recs,
                                                     "steps_changed": [{"at": "2026-10-08", "from": old}]})
    days = ["2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-26"]
    _cc(data, days=days, sg=fc.sig(old))
    x, rows, line = _run(tmp_path)
    assert [rows[d][fb.XI] for d in days] == [1, 1, 1, 1, 0, 0, 0]
    _cc(data, days=days)                                            # read with the current screens
    x, rows, line = _run(tmp_path)
    assert [rows[d][fb.XI] for d in days] == [0, 0, 0, 0, 1, 1, 1]


def test_a_steps_share_of_splash_stays_its_own_reads(tmp_path, data):
    """Language (sampled, 500) ÷ the Splash of the SAME read (1000), never ÷ the exact Splash (800)."""
    _main(data)
    _cc(data, t=[1020, 800, 480])
    x, rows, line = _run(tmp_path)
    assert rows["2026-10-05"][1:4] == [1020, 800, 480] and x["steps"]["language"][0] == 0.5
    assert abs(x["s2h"] - 0.6) < 1e-6 and abs(x["opened"] - 800 / 1020) < 1e-6


def test_a_failure_says_so(tmp_path, data, monkeypatch, capsys):
    _main(data)
    _cc(data)
    monkeypatch.setattr(fc, "load_store", lambda p: 1 / 0)
    x, rows, line = _run(tmp_path)
    assert all(r[fb.XI] == 0 for r in rows.values()) and line.endswith(", exact days 0")
    assert "first open exact skipped: ZeroDivisionError" in capsys.readouterr().err


def test_settings_and_the_workflow(monkeypatch):
    from admob_iq import config
    src = open(config.__file__, encoding="utf-8").read()
    assert '"firstopen_exact": _env("FIRSTOPEN_EXACT", "true").lower() == "true"' in src
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        y = f.read()
    assert "FIRSTOPEN_EXACT:      ${{ vars.FIRSTOPEN_EXACT || 'true' }}" in y
