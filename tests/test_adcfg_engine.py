"""⚙️ Ad setting changes — the engine (admob_iq/engine/adcfg.py) on SYNTHETIC apps only (tests/adcfg_synth.py: made-up
units, users and money, with the truth of every change beside them): precision and recall of the detector, the day it
puts a change on, its kind, the release shape test, the country-mix exclusion, the decoys (one-day spikes, a dip that
comes back, an eCPM-only move, a slow drift; an install surge under an onboarding ad, a break in GA4's users count)
never an event, a real change of the onboarding ad still found, a fresh change "checking" before it is "confirmed",
stray report days long before neither starting the history nor using up the launch skip, and the small pieces (the
report index, DAU, new users, releases, the forecast's steps and labels, the weekly chart series)."""
from datetime import date, timedelta

from tests import adcfg_synth as S
from admob_iq.engine import adcfg as A


def run(x, start=None, new=True):
    src = A.Source(x["mu"], x["cty"], x["till"])
    ad, cty = src.app([x["app_id"]]), src.country([x["app_id"]])
    dau = A.dau_of(x["store"])
    dropped = []
    ev = A.finish(A.detect(ad, dau, A.releases_of(x["store"]), cty, start=start, dropped=dropped,
                           new=A.new_of(x["store"]) if new else None))
    return ev, dropped, ad, dau


def _near(e, d, days=4):
    return abs((date.fromisoformat(e["d"]) - date.fromisoformat(d)).days) <= days


WANT = {"cap": "cap", "off": "removed placement", "on": "new placement", "sdk": "SDK", "rel": "cap"}


def test_precision_recall_dates_kinds_on_synthetic_apps():
    tp = fp = truth = found = 0
    exact = near = kind_ok = kinds = 0
    rel_ok = rel_n = null_ok = null_n = 0
    for seed in range(1, 21):
        x = S.make(seed)
        ev, _, _, _ = run(x)
        conf = [e for e in ev if e["st"] == "confirmed"]
        hit, miss, got = S.score(conf, x["truth"])
        tp += len(hit)
        fp += len(miss)
        truth += len(x["truth"])
        found += len(got)
        for e, t, gap in hit:
            exact += gap == 0
            near += gap <= 2
            kinds += 1
            kind_ok += e["kind"] == WANT[t["kind"]]
            if t["kind"] == "rel":
                rel_n += 1
                rel_ok += bool(e["rel"]) and e["rel"]["v"] == t["ver"]
            if t.get("relnull"):                        # an update on the same day that changed nothing
                null_n += 1
                null_ok += e["rel"] is None and (e["near"] or {}).get("v") == t["relnull"]
    assert tp / (tp + fp) >= 0.97                       # precision
    assert found / truth >= 0.97                        # recall
    assert exact / tp >= 0.8 and near / tp >= 0.97      # the day: mostly exact, almost always within 2 days
    assert kind_ok == kinds                             # cap / new / removed placement / SDK all right
    assert rel_n >= 5 and rel_ok == rel_n               # an update's ramp: "with update", its own version
    assert null_n >= 5 and null_ok == null_n            # a sharp setting change on an update day: a setting ("near")


def test_high_confidence_stays_right_when_noisy():
    hit_n = high_n = 0
    for seed in range(201, 216):
        x = S.make(seed, sigma=0.25)                    # ~ the noisiest quarter of real format series
        ev, _, _, _ = run(x)
        high = [e for e in ev if e["st"] == "confirmed" and e["conf"] == "High"]
        hit, miss, _ = S.score(high, x["truth"])
        hit_n += len(hit)
        high_n += len(high)
    assert high_n >= 20 and hit_n / high_n >= 0.95


def test_decoys_are_never_confirmed_and_the_mix_is_dropped():
    seen = {"spike": 0, "dip": 0, "ecpm": 0, "drift": 0, "mix": 0}
    mix_dropped = 0
    for seed in range(1, 21):
        x = S.make(seed)
        ev, dropped, _, _ = run(x)
        for d in x["decoys"]:
            D = date.fromisoformat(d["d"])
            bad = [e for e in ev if e["st"] == "confirmed" and abs((date.fromisoformat(e["d"]) - D).days) <= 3
                   and (d["fmt"] is None or e["fmt"] == d["fmt"])
                   and not any(abs((date.fromisoformat(t["d"]) - date.fromisoformat(e["d"])).days) <= 5
                               for t in x["truth"])]
            assert not bad, (seed, d, bad)
            seen[d["kind"]] += 1
            if d["kind"] == "mix":
                mix_dropped += any(abs((date.fromisoformat(e["d"]) - D).days) <= 7 for e in dropped)
    assert all(v >= 2 for v in seen.values())
    assert mix_dropped == seen["mix"]                   # the users' country move: found, then kept out


def test_a_fresh_change_is_checking_then_confirmed():
    n = 400
    i = n - 10                                          # 10 days before the newest day
    x = S.make(7, n=n, sched=[("cap", i)])
    ev, _, _, _ = run(x)
    t = x["truth"][0]
    e = [e for e in ev if e["fmt"] == t["fmt"] and abs((date.fromisoformat(e["d"]) - date.fromisoformat(t["d"])).days) <= 2]
    assert e and e[0]["st"] == "checking" and e[0]["j2"] is None
    x = S.make(7, n=i + 40, sched=[("cap", i)])         # 40 days on: it held weeks 3–4
    ev, _, _, _ = run(x)
    e = [e for e in ev if e["fmt"] == t["fmt"] and abs((date.fromisoformat(e["d"]) - date.fromisoformat(t["d"])).days) <= 2]
    assert e and e[0]["st"] == "confirmed" and e[0]["j2"] is not None
    x = S.make(7, n=i + 5, sched=[("cap", i)])          # 5 days: not shown yet (≥ 7 days after it)
    ev, _, _, _ = run(x)
    assert not [e for e in ev if abs((date.fromisoformat(e["d"]) - date.fromisoformat(t["d"])).days) <= 2]


def test_a_quiet_app_has_no_events():
    x = S.make(3, sched=[])
    ev, dropped, _, _ = run(x)
    assert ev == [] and dropped == []


def test_the_scan_rule():
    v = [0.0] * 40 + [0.5] * 40                         # one clean step of +65 %
    out = A.scan(v)
    assert [o[0] for o in out] == [40] and abs(out[0][1] - 0.5) < 1e-9 and not out[0][4]
    v = [0.0] * 40 + [0.2] * 40                         # +22 %: under the 30 % rule
    assert A.scan(v) == []
    v = [0.0] * 40 + [0.5] * 20 + [0.0] * 40            # 20 days, then back: the rise did not hold weeks 3–4 …
    assert [(o[0], o[1] < 0, o[4]) for o in A.scan(v)] == [(60, True, False)]   # … the way back did (a change too)
    v = [0.0] * 40 + [0.5] * 20 + [0.0] * 10            # back 10 days ago: still checking
    assert [(o[0], o[1] < 0, o[4]) for o in A.scan(v)] == [(60, True, True)]
    v = [0.0] * 40 + [0.5] * 5                          # 5 days after: too fresh to show
    assert A.scan(v) == []
    v = [0.0] * 40 + [0.5] * 7                          # 7: checking
    assert [(o[0], o[4]) for o in A.scan(v)] == [(40, True)]
    v = [0.0] * 40 + [None] * 5 + [0.5] * 40            # gaps are skipped, the step still found
    assert len(A.scan(v)) == 1


def test_source_dau_releases():
    x = S.make(2, n=200, sched=[("rel", 100)])
    src = A.Source(x["mu"], x["cty"], "2025-05-01")
    ad = src.app([x["app_id"], x["app_id"]])            # (an id twice: counted once by the caller's dedupe)
    assert max(ad["days"]) == "2025-05-01" and set(ad["f"]) >= {"app_open", "interstitial", "banner", "native"}
    one = A.Source(x["mu"], None, None).app([x["app_id"]])
    d = "2025-03-01"
    assert one["f"]["banner"][d][2] == sum(r["impressions"] for r in x["mu"]
                                           if r["report_date"] == d and r["format"] == "banner")
    st = dict(x["store"], flags={"incomplete_days": {"2025-02-01": 1}})
    dau = A.dau_of(st)
    assert "2025-02-01" not in dau and dau["2025-02-02"] == x["store"]["daily"]["2025-02-02"]["a1"]
    rels = A.releases_of(x["store"])
    r = [r for r in rels if r["v"] == "2.100"]
    assert r and r[0]["full"] is not None and r[0]["d"] < r[0]["full"] and r[0]["sh"]


def test_forecast_steps_labels_weekly():
    evs = [{"d": "2026-01-10", "st": "confirmed", "rx": 0.25, "fmt": "app_open"},
           {"d": "2026-02-10", "st": "confirmed", "rx": 0.04, "fmt": "banner"},        # < 10 %: not material
           {"d": "2026-03-10", "st": "checking", "rx": 0.5, "fmt": "native"}]          # not confirmed yet
    st = A.fc_steps(evs)
    assert st == [{"at": "2026-01-10", "x": 0.25, "fmt": "app_open"}]
    lab = A.labels(["2025-12-20", "2026-01-10", "2025-10-01"], st, (30, 90, 180))
    assert lab == {"2025-12-20": {30: "2026-01-10", 90: "2026-01-10", 180: "2026-01-10"},
                   "2025-10-01": {180: "2026-01-10"}}      # T < s ≤ T + h (the origin's own day is not inside)
    x = S.make(4, n=60, sched=[])
    src = A.Source(x["mu"], None, x["till"])
    ad = src.app([x["app_id"]])
    wk = A.weekly(ad, A.dau_of(x["store"]), ["banner"])
    assert wk["d0"] == "2025-01-06" and len(wk["f"]["banner"]) == 9
    assert abs(wk["f"]["banner"][2] - 2.0) < 0.2        # the synthetic banner's ~2 ads per user a day


def test_launch_days_and_start_are_not_scanned():
    x = S.make(5, n=300, sched=[("cap", 30), ("cap", 150)])
    ev, _, _, _ = run(x)
    d30 = date(2025, 1, 6) + timedelta(days=30)
    assert not [e for e in ev if abs((date.fromisoformat(e["d"]) - d30).days) <= 3]   # inside the first 42 days
    ev2, _, _, _ = run(x, start="2025-07-01")
    assert all(e["d"] >= "2025-07-01" for e in ev2) and len(ev2) < len(ev)


def test_an_install_surge_under_an_onboarding_ad_is_the_new_users():
    """New users × 2 for 60 days; the app's onboarding unit shows k ads per NEW user (a small one: only the unit steps;
    a big one: its format steps too). No setting moved: never an event (up or back down), kept out as "new users" —
    and without the new users (the old check) it was confirmed, so the test bites. The real changes still found."""
    old_conf = 0
    for onb in (4, 12):
        for seed in range(1, 7):
            x = S.make(seed, n=420, sched=[("cap", 100), ("surge", 200), ("cap", 330)], onb=onb)
            ev, dropped, _, _ = run(x)
            for d in x["decoys"]:
                assert not [e for e in ev if _near(e, d["d"]) and e["fmt"] == "native"], (onb, seed, d)
                assert [e for e in dropped if _near(e, d["d"]) and e["why"] == "new users"], (onb, seed, d)
            assert len(S.score([e for e in ev if e["st"] == "confirmed"], x["truth"])[2]) == len(x["truth"])
            ev0, _, _, _ = run(x, new=False)
            old_conf += any(e["st"] == "confirmed" and _near(e, x["decoys"][0]["d"]) for e in ev0)
    assert old_conf >= 10


def test_a_real_change_of_the_onboarding_ad_is_still_found():
    for onb in (4, 12):
        for seed in range(1, 6):
            x = S.make(seed, n=420, sched=[("cap", 100), ("onbcap", 200), ("cap", 330)], onb=onb)
            ev, dropped, _, _ = run(x)
            hit, miss, got = S.score([e for e in ev if e["st"] == "confirmed"], x["truth"])
            assert len(got) == len(x["truth"]) and not miss and not dropped, (onb, seed)


def test_a_break_in_the_ga4_users_count_is_not_an_ad_change():
    """GA4's DAU (and new users) × 0.45 from a day on, every ad the same: every ads per user series × 2.2 — all of it
    kept out as "GA4 users", no event; the real changes before and after still found."""
    for seed in range(1, 7):
        x = S.make(seed, n=420, sched=[("cap", 100), ("users", 200), ("cap", 330)])
        ev, dropped, _, _ = run(x)
        D = x["decoys"][0]["d"]
        assert not [e for e in ev if _near(e, D)], (seed, [e["d"] for e in ev])
        assert [e for e in dropped if _near(e, D) and e["why"] == "GA4 users"]
        assert len(S.score([e for e in ev if e["st"] == "confirmed"], x["truth"])[2]) == len(x["truth"])


def test_stray_report_days_long_before_do_not_start_the_history():
    """4 report days a year before the app's real data: the history (and the launch skip) starts at the first 28 days
    with ≥ 21 days of both — a change 30 days into the real data is inside the skip, one at 150 found; the weekly chart
    starts at the real data's first week, no empty weeks before it."""
    x = S.make(5, n=300, sched=[("cap", 30), ("cap", 150)])
    d0 = date(2025, 1, 6)
    for k in (400, 390, 380, 371):                      # (copies of day 0, a year before: scattered, never 21 in 28)
        ds, src_d = (d0 - timedelta(days=k)).isoformat(), d0.isoformat()
        x["mu"] += [dict(r, report_date=ds) for r in x["mu"] if r["report_date"] == src_d]
        x["store"]["daily"][ds] = dict(x["store"]["daily"][src_d])
    ev, _, ad, dau = run(x)
    assert A.dense_start(sorted(set(ad["days"]) & set(dau))) == d0.isoformat()
    assert not [e for e in ev if _near(e, (d0 + timedelta(days=30)).isoformat(), 3)]
    assert [e for e in ev if _near(e, (d0 + timedelta(days=150)).isoformat(), 3)]
    wk = A.weekly(ad, dau, ["banner"])
    assert wk["d0"] == d0.isoformat() and wk["f"]["banner"][0] is not None and wk["f"]["banner"][-1] is not None
    assert A.dense_start(["2025-01-01", "2025-02-01"]) is None and A.weekly({"f": {}, "days": []}, {}) is None


def test_new_users_of_the_store():
    x = S.make(2, n=60, sched=[])
    st = dict(x["store"], flags={"incomplete_days": {"2025-02-01": 1}})
    nu = A.new_of(st)
    assert "2025-02-01" not in nu and nu["2025-02-02"] == x["store"]["daily"]["2025-02-02"]["new"] > 0
