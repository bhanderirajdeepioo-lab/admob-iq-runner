"""Google Ads cost by country in the Install value engine (SPEC_CD_GEO Part G, "GE:" in §G.13): the week envelope of
value_build._app_geo gives each country its own cost per install over exactly its install weeks — only when every
window week is whole and Google Ads' own country total covers its campaign cost (else no country cost at all, and the
reason) —, a country without Google Ads cost is "no ads" (never the cheapest), the unmapped and small parts count in
the totals but never get a row or an alert, geo_cost keeps its streak while a week is not covered and merges with the
same country's geo_move, and the legacy shapes behave exactly as at abd6ee8. All data is synthetic
(tests.value_synth.geo_envelope)."""

import copy
from datetime import date, timedelta

import pytest

from admob_iq.engine import value as V
from tests import test_value_cd_build as cdb
from tests import value_synth as vs

END = vs.END
S = END - timedelta(days=vs.LATE)
E = V._eval_end(S)
START = END - timedelta(days=60 * 7 - 1)
AID = "ca-app-pub-0000000000000000~0000000009"
NOW = "2026-09-21T12:00:00Z"
OLD = "2026-01-04"
NOCOST = ("top", "avg", "low", "few", "wait")


def ev(m, st=None, **kw):
    return V.evaluate_app(m["store"], m["ida"], m["rev"], m["spend"], m["fx"], [], st, {}, {"payback_days": 90}, NOW,
                          app_id=AID, app="Demo App", key="k", **kw)


def app(**kw):
    kw.setdefault("start", START)
    kw.setdefault("seed", 3)
    return vs.make_app(**kw)


def again(st, inputs=OLD):
    st = copy.deepcopy(st)
    st["eval"]["end_week"] = (E - timedelta(days=7)).isoformat()
    if inputs:
        st["eval"]["inputs"] = {k: inputs for k in st["eval"]["inputs"]}
    st["episodes"] = {}
    return st


def cty(det):
    return {r["cc"]: r for r in det["countries"]["rows"]}


def alerts(row, fam):
    return [a for a in row["_alerts"] if a["family"] == fam]


def win_weeks(det):
    w = det["countries"]["win"]
    a = date.fromisoformat(w["from"])
    return [(a + timedelta(days=7 * i)).isoformat() for i in range(w["weeks"])]


@pytest.fixture(scope="module")
def base():
    m = app()
    env = vs.geo_envelope(m, mult={"US": 0.5, "NG": 4.0, "DE": 0.7}, xx=0.01, small={"KE": 40})
    det, row, st = ev(m, geo=env)
    return m, env, det, row, st


def test_geo_envelope_cost_over_install_weeks_only(base):
    m, env, det, row, _ = base
    ws = win_weeks(det)
    c = cty(det)
    for cc in ("IN", "US", "NG"):
        cost = sum(env["weeks"][w]["by"][cc][0] for w in ws)
        dl = sum(env["weeks"][w]["by"][cc][1] for w in ws)
        assert c[cc]["cpi"]["v"] == pytest.approx(cost / c[cc]["n"], rel=1e-5)
        assert c[cc]["cpi"]["spend"] == pytest.approx(cost, rel=1e-5) and c[cc]["cpi"]["ads"] == pytest.approx(cost / dl, rel=1e-5)
        assert c[cc]["cpi"]["paid"] == pytest.approx(0.87, abs=0.01)
    other = copy.deepcopy(env)                            # a week outside the window: whatever it costs, no effect
    old = min(other["weeks"])
    for v in other["weeks"][old]["by"].values():
        v[0] *= 50
    det2, _, _ = ev(m, geo=other)
    assert {k: r["cpi"] for k, r in cty(det2).items()} == {k: r["cpi"] for k, r in c.items()}
    co = det["countries"]
    assert co["geo"] and co["geo_why"] == "ok" and row["cty"]["geo"]
    assert co["geo_cov"]["v"] == pytest.approx(1.0) and co["geo_cov"]["weeks"] == 4 and co["geo_cov"]["till"] == S.isoformat()
    assert co["cost"]["spend"] == pytest.approx(sum(env["weeks"][w]["spend"] for w in ws), rel=1e-5)


def test_geo_coverage_gate_hides_cost_and_says_why():
    m = app()
    w0 = win_weeks(ev(m)[0])[0]
    det, row, _ = ev(m, geo=vs.geo_envelope(m, cov={w0: 0.95}))
    co = det["countries"]
    assert co["geo_why"] == "cov" and co["cost"] is None and co["geo"] and not row["cty"]["geo"]
    assert all(r["cpi"] is None and r["pay"] is None and r["back"] is None and r["verdict"] in NOCOST for r in co["rows"])
    assert any(t.startswith("⚠️ Google Ads country-wise kharcha ") and "(95%)" in t for t in det["scale"]["text"])
    for cv in (0.98, 1.02):
        det, _, _ = ev(m, geo=vs.geo_envelope(m, cov={w0: cv}))
        assert det["countries"]["geo_why"] == "ok" and all(r["cpi"] for r in det["countries"]["rows"])
    det, _, _ = ev(m, geo=vs.geo_envelope(m, cov={w0: 1.04}))
    assert det["countries"]["geo_why"] == "cov"


def test_geo_wait_when_week_beyond_till():
    m = app()
    det, _, _ = ev(m, geo=vs.geo_envelope(m, till=S - timedelta(days=20)))
    co = det["countries"]
    assert co["geo_why"] == "wait" and all(r["cpi"] is None for r in co["rows"])
    assert any(t.startswith("Google Ads country-wise kharcha ") and t.endswith("tak aaya — naye hafton ka country cost "
                                                                              "uske baad") for t in det["scale"]["text"])


def test_geo_nostore_and_noads():
    m = app()
    env = vs.geo_envelope(m)
    for w in env["weeks"].values():                       # the app spent, but none of its stores is in the cache
        w.update(cov=None, geo=0.0, by={})
    det, _, _ = ev(m, geo=env)
    assert det["countries"]["geo_why"] == "nostore"
    assert "Is app ke Google Ads account ka country-wise data nahi mila — country cost nahi dikhaya" in det["scale"]["text"]
    m = app(spend=False)
    det, _, _ = ev(m, geo=vs.geo_envelope(m))
    assert det["countries"]["geo_why"] == "noads" and all(r["cpi"] is None for r in det["countries"]["rows"])


def test_geo_nostore_said_by_in_cache_even_before_the_weeks_are_whole():
    """value_build's envelope says how many of the app's spend stores the cache holds (in_cache): 0 with spend is
    "nostore" straight away — not "wait" while the cache's first refresh is still to come."""
    m = app()
    env = vs.geo_envelope(m, till=S - timedelta(days=20))  # the newest weeks not whole: "wait" on its own
    assert ev(m, geo=env)[0]["countries"]["geo_why"] == "wait"
    env.update(stores=1, in_cache=0)
    for w in env["weeks"].values():
        w.update(cov=None, geo=0.0, by={})
    assert ev(m, geo=env)[0]["countries"]["geo_why"] == "nostore"
    first = dict(env, till=None, first=None)               # nothing committed yet (a first refresh that failed):
    for w in first["weeks"].values():                      # pending, never "no data for this account"
        w["whole"] = False
    assert ev(m, geo=first)[0]["countries"]["geo_why"] == "wait"
    env = vs.geo_envelope(m)
    env.update(stores=1, in_cache=1)                       # in the cache: as without the key
    assert ev(m, geo=env)[0]["countries"]["geo_why"] == "ok"


def test_geo_trickle_week_off_by_cents_does_not_hide_the_window():
    """A window week with a few paise of spend (a campaign that stopped) can miss the 3% band by the cache's rounding
    alone: off by no more than that rounding (the envelope's "tol", GEO_COV_ABS at least) it still passes. A week
    with more missing than the rounding explains is not covered, however small — a genuinely unplaced dollar is never
    read as every country's cost."""
    m = app()
    w0 = win_weeks(ev(m)[0])[0]
    env = vs.geo_envelope(m)
    e = env["weeks"][w0]
    k = 0.03 / e["spend"]                                  # the week shrunk to 3 cents, its countries 20% short
    e.update(spend=0.03, geo=0.024, cov=0.8, by={cc: [v[0] * k * 0.8, v[1]] for cc, v in e["by"].items()})
    det, _, _ = ev(m, geo=env)
    co = det["countries"]
    assert co["geo_why"] == "ok" and co["geo_cov"]["min"] == 0.8 and any((r["cpi"] or {}).get("v") for r in co["rows"])
    k = 5.0 / 0.03                                         # $5 spent, $4 placed: $1 real cost missing — not covered
    e.update(spend=5.0, geo=4.0, by={cc: [v[0] * k, v[1]] for cc, v in e["by"].items()})
    assert ev(m, geo=env)[0]["countries"]["geo_why"] == "cov"
    e["tol"] = 1.25                                        # a USD-billed cache: 250 cells × half a cent each …
    assert ev(m, geo=env)[0]["countries"]["geo_why"] == "ok"   # … can explain that dollar
    e.update(tol=0.01, spend=0.5, geo=0.4)                 # the bound never below GEO_COV_ABS, never above what it says
    assert ev(m, geo=env)[0]["countries"]["geo_why"] == "cov"
    e.update(spend=0.5, geo=None, cov=None)                # unknown stays unknown, however small
    assert ev(m, geo=env)[0]["countries"]["geo_why"] != "ok"


def test_geo_week_with_unmapped_cost_is_not_covered_and_noads_needs_it_small():
    """Cost Google Ads put in no country (a failed country map, "XX") never reads as "No ads here" in a real country:
    a week whose unmapped part leaves the countries under GEO_COV_MIN of the campaign is not covered; below that, an
    unmapped share over GEO_XX_NOADS makes a country without cost of its own "unknown", not organic."""
    m = app()
    w0 = win_weeks(ev(m)[0])[0]
    det, _, _ = ev(m, geo=vs.geo_envelope(m, xx={w0: 1.0}))            # one window week all unmapped
    co = det["countries"]
    assert co["geo_why"] == "cov" and all(r["cpi"] is None for r in co["rows"])
    assert any("poora nahi mila (0%)" in t for t in det["scale"]["text"])      # what reached a country: none of it
    det, _, _ = ev(m, geo=vs.geo_envelope(m, xx=0.02, noads=("BR",)))
    br = cty(det)["BR"]
    assert det["countries"]["geo_why"] == "ok" and br["cpi"] == {"v": None, "spend": None, "unknown": True}
    assert br["verdict"] in NOCOST and br["pay"] is None
    det, _, _ = ev(m, geo=vs.geo_envelope(m, xx=0.004, noads=("BR",)))  # a trickle unmapped: organic, as it says
    assert cty(det)["BR"]["cpi"] == {"v": None, "spend": 0.0, "noads": True}


def test_geo_zero_cost_country_is_noads_not_cheapest():
    m = app()
    det, _, st = ev(m, geo=vs.geo_envelope(m, noads=("BR",)))
    br = cty(det)["BR"]
    assert br["cpi"] == {"v": None, "spend": 0.0, "noads": True} and br["pay"] is None and br["back"] is None
    assert br["verdict"] in NOCOST and br["trend"]["cpi"] == [None] * len(br["trend"]["cpi"])
    assert "install" not in br["text"].split("—")[-1] or "se sasta mile" in br["text"]
    det2, _, _ = ev(m, st=again(st), geo=vs.geo_envelope(m, noads=("BR",)))
    assert "BR" not in (det2["countries"].get("keep") or []) and "BR" not in det2["tiles"]["cty"].get("keep", [])


def test_geo_small_and_unmapped_in_totals_never_rows_or_alerts():
    m = app()
    env = vs.geo_envelope(m, xx=0.02, small={"KE": 400})
    det, row, st = ev(m, geo=env)
    co = det["countries"]
    c = co["cost"]
    assert c["unmapped_share"] == pytest.approx(0.02, abs=1e-4) and c["unmapped"] > 0 and c["small"] > 0
    assert c["total"] == pytest.approx(c["rows"] + c["small"] + c["unmapped"], rel=1e-5)
    assert co["small"]["cost"] == c["small"] and co["small"]["cpi"] == pytest.approx(c["small"] / co["small"]["n"])
    assert not {"XX", "KE"} & set(cty(det))
    assert any("kisi country se match nahi hua: 2%" in t for t in det["scale"]["text"])
    big = vs.geo_envelope(m, xx=0.5, small={"KE": 20000})        # most of the cost unmapped / small: still no alert
    _, row, st = ev(m, geo=big)
    _, row, _ = ev(m, st=again(st), geo=big)
    assert not [a for a in alerts(row, "geo_cost") if a["cc"] in ("XX", "KE", "--", "ZZ")]


def test_country_payback_obs_flag(base):
    _, _, det, _, _ = base
    c = cty(det)
    assert c["US"]["verdict"] == "keep" and c["US"]["pay"]["obs"] is True          # paid back on its own points
    assert c["IN"]["pay"]["obs"] is False and c["NG"]["pay"]["never"]              # beyond 90 days: ≈
    assert 30 < c["BR"]["pay"]["p"] <= 90 and c["BR"]["pay"]["obs"] is True        # seen on its own 60 / 90-day weeks' cost
    assert V._pay_obs({1: {"v": 1, "est": False}, 7: {"v": 2, "est": True}}, 5) is False
    assert V._pay_obs({1: {"v": 1, "est": False}, 7: {"v": 2, "est": False}}, 5) is True


def test_geo_back_per_100(base):
    _, _, det, _, _ = base
    for r in det["countries"]["rows"]:
        cpi = r["cpi"]["v"]
        assert r["back"]["7"] == pytest.approx(100 * r["rpi"]["7"]["v"] / cpi, rel=1e-3)
        assert r["back"]["30"] == pytest.approx(100 * r["rpi"]["30"]["v"] / cpi, rel=1e-3)
        assert r["back"]["90"] == pytest.approx(100 * r["rpi"]["90"]["v"] / cpi, rel=1e-3)
        assert r["back"]["90_proj"] == r["rpi"]["90"]["proj"]
        tc = [v for v in r["trend"]["cpi"] if v is not None]
        assert len(r["trend"]["cpi"]) == len(r["trend"]["d1"]) and tc and all(v > 0 for v in tc)


def test_geo_input_seen_when_window_ok_and_reset_when_off():
    m = app()
    w0 = win_weeks(ev(m)[0])[0]
    _, _, st = ev(m, geo=vs.geo_envelope(m))
    assert st["eval"]["inputs"]["geo"] == E.isoformat()
    _, _, st = ev(m, geo=vs.geo_envelope(m, cov={w0: 0.9}))
    assert st["eval"]["inputs"]["geo"] is None                       # not covered: not seen yet
    s2 = again(st)
    _, _, st3 = ev(m, st=s2, geo=vs.geo_envelope(m, cov={w0: 0.9}))
    assert st3["eval"]["inputs"]["geo"] == OLD                       # seen before: kept while the input is on
    _, _, st4 = ev(m, st=s2)
    assert st4["eval"]["inputs"]["geo"] is None                      # GADS_GEO off: back to never seen


def test_geo_cost_two_evaluations_or_r30_under_0_3():
    m = app()
    env = vs.geo_envelope(m, mult={"IN": 0.5})
    det, row, st = ev(m, geo=env)
    c = cty(det)
    assert c["IN"]["back"]["30"] >= 30 and c["IN"]["be_hi"] < c["IN"]["cpi"]["v"]   # q80 at H under its cost
    assert c["NG"]["back"]["30"] < 30                                              # 30-day earning < 0.3 × cost
    assert "IN" not in [a["cc"] for a in alerts(row, "geo_cost")] and "NG" in [a["cc"] for a in alerts(row, "geo_cost")]
    assert st["eval"]["streak"]["geo_cost|IN"] == 1
    _, row, _ = ev(m, st=again(st), geo=env)
    got = {a["cc"]: a for a in alerts(row, "geo_cost")}
    assert "IN" in got and got["IN"]["notify"] and got["IN"]["unit"] == "usd" and got["IN"]["severity"] == "watch"
    _, row, _ = ev(m, geo=vs.geo_envelope(m, mult={"NG": 4.0}))                  # ≥ 25% of the cost, q80 < ½ cost
    ng = next(a for a in alerts(row, "geo_cost") if a["cc"] == "NG")
    assert ng["severity"] == "warning" and "{cc:NG} me ads mehenge" in ng["text"]


def test_geo_cost_streak_frozen_when_week_not_ok():
    m = app()
    env = vs.geo_envelope(m, mult={"IN": 0.5})
    _, _, st = ev(m, geo=env)
    assert st["eval"]["streak"]["geo_cost|IN"] == 1
    w0 = win_weeks(ev(m)[0])[0]
    _, row, st2 = ev(m, st=again(st), geo=vs.geo_envelope(m, mult={"IN": 0.5}, cov={w0: 0.9}))
    assert not alerts(row, "geo_cost") and st2["eval"]["streak"]["geo_cost|IN"] == 1     # nothing judged, kept
    _, row, _ = ev(m, st=again(st2), geo=env)
    assert "IN" in [a["cc"] for a in alerts(row, "geo_cost")]


def test_geo_cost_and_move_same_country_one_episode():
    m = app(drop=("NG", date(2026, 8, 31), 0.6))
    _, row, _ = ev(m)
    assert [a["cc"] for a in alerts(row, "geo_move")] == ["NG"]
    _, row, st = ev(m, geo=vs.geo_envelope(m, mult={"NG": 4.0}))
    assert not alerts(row, "geo_move")
    a = alerts(row, "geo_cost")
    ng = next(x for x in a if x["cc"] == "NG")
    assert ng["also"] == ["d1"] and ng["move"]["metric"] == "d1" and ng["move"]["now"] < ng["move"]["before"]
    assert len([e for e in st["episodes"].values() if e.get("cc") == "NG"]) == 1


def _gcond(cc="NG"):
    return {"key": "a|geo_cost|%s" % cc, "family": "geo_cost", "metric": "cost", "dir": "down", "cc": cc,
            "severity": "watch", "seed": False, "week_from": "2026-08-17", "week_to": "2026-09-13"}


def test_geo_cost_reopen_within_42_days_seeded():
    assert V.REOPEN_SEED_DAYS["geo_cost"] == 42
    e0 = date(2026, 6, 7)
    st, _ = V.episodes(V.empty_state(), AID, e0, [_gcond()], True, "2026-06-08T00:00:00Z")
    st["episodes"]["a|geo_cost|NG"]["notified_at"] = "2026-06-08T01:00:00Z"
    for i in (1, 2):
        st, _ = V.episodes(st, AID, e0 + timedelta(days=7 * i), [], True, "2026-06-20T00:00:00Z")
    closed = date.fromisoformat(st["closed"][-1]["closed"])
    soon, _ = V.episodes(st, AID, closed + timedelta(days=35), [_gcond()], True, "2026-07-30T00:00:00Z")
    assert soon["episodes"]["a|geo_cost|NG"]["seeded"]
    other, _ = V.episodes(st, AID, closed + timedelta(days=35), [_gcond("IN")], True, "2026-07-30T00:00:00Z")
    assert other["episodes"]["a|geo_cost|IN"]["notified_at"] is None          # another country: its own
    late, _ = V.episodes(st, AID, closed + timedelta(days=49), [_gcond()], True, "2026-08-15T00:00:00Z")
    assert late["episodes"]["a|geo_cost|NG"]["notified_at"] is None


def test_geo_cost_seeded_in_burnin_sent_after():
    m = app()
    env = vs.geo_envelope(m, mult={"NG": 4.0})
    _, _, st = ev(m, geo=env)
    s2 = again(st)
    s2["eval"]["inputs"]["geo"] = (E - timedelta(days=14)).isoformat()
    _, row, _ = ev(m, st=s2, geo=env)
    assert alerts(row, "geo_cost") and not any(a["notify"] for a in alerts(row, "geo_cost"))
    s2["eval"]["inputs"]["geo"] = (E - timedelta(days=35)).isoformat()
    _, row, _ = ev(m, st=s2, geo=env)
    got = alerts(row, "geo_cost")
    assert [a["cc"] for a in got if a["notify"]] == ["NG"]              # burn-in over: sent — one per app and week


def test_geo_tile_keep_costly_after_two_evaluations():
    m = app()
    env = vs.geo_envelope(m, mult={"US": 0.5, "NG": 4.0, "DE": 0.7})
    det, _, st = ev(m, geo=env)
    assert det["tiles"]["cty"]["keep"] == [] and det["tiles"]["cty"]["costly"] == []   # one evaluation: not yet
    det, row, _ = ev(m, st=again(st), geo=env)
    assert "US" in det["tiles"]["cty"]["keep"] and "NG" in det["tiles"]["cty"]["costly"]
    assert set(det["tiles"]["cty"]["keep"]) <= set(row["cty"]["best"])
    det, _, _ = ev(m, st=again(st), geo=vs.geo_envelope(m, till=S - timedelta(days=20)))
    assert "keep" not in det["tiles"]["cty"]                            # no country cost: the tile as before


def test_geo_legacy_shapes_byte_identical():
    """Plain {cc: {cost, dl}} and day-grain {cc: {"daily": …}} inputs: exactly abd6ee8's countries block, tiles, row,
    alerts and state (the pinned digest of tests.test_value_cd_build)."""
    assert cdb.legacy_geo_digest() == cdb.ABD6EE8_LEGACY_GEO
    m = app()
    det, _, _ = ev(m, geo={"US": {"cost": 10.0, "dl": 5}})
    assert not {"geo_why", "geo_cov", "cost"} & set(det["countries"])
    assert "back" not in cty(det)["US"] and "cpi" not in cty(det)["US"]["trend"]


# ── the review's fixes (a country's own cost judged only when it is real, honest, and alerted once) ─────────────

def _with(env, m, fn):
    """A copy of the envelope with each window week's country cells rewritten: fn(cc, n_c, [usd, dl, billed]) → the
    cell (or None to drop it); a week's geo / spend follow (coverage stays 1)."""
    e = copy.deepcopy(env)
    cset = m["ida"]["cset"]
    for W, w in e["weeks"].items():
        cells = m["ida"]["c"].get(W) or {}
        n_c = {cset[int(k)]: v["n"] for k, v in cells.items() if k != "gap"}
        by = {}
        for cc, v in w["by"].items():
            got = fn(cc, n_c.get(cc, 0), list(v))
            if got is not None:
                by[cc] = got
        w["by"] = by
        tot = sum(v[0] for v in by.values())
        rate = w["rate"]
        w.update(geo=tot, spend=tot, cov=1.0 if tot else w["cov"])
        for v in by.values():
            v[2] = v[0] / rate
    return e


def test_geo_thin_ads_country_is_shown_never_judged():
    """A few cents of spillover, a handful of Google Ads downloads, or ads bringing 1% of a country's installs: its
    cost is shown ("thin"), but it gets no Keep / Slow / Costly, no money back, no ₹ per ₹100, no geo_cost — never
    "ads chalu rakh sakte ho" on a blended cost the ads did not earn."""
    m = app()
    env = vs.geo_envelope(m)

    def spill(cc, n, v):                                   # DE: 1 cent a week, no download
        return [0.01, 0.0, v[2]] if cc == "DE" else v

    def organic(cc, n, v):                                 # IN: $0.015 per install, ads bring 1% of them
        return [0.015 * n, round(0.01 * n, 2), v[2]] if (cc == "IN" and n) else v

    def few_dl(cc, n, v):                                  # BR: a real spend, 3 Google Ads downloads a week
        return [v[0], 3.0, v[2]] if cc == "BR" else v
    for fn, cc, why in ((spill, "DE", "spend"), (organic, "IN", "paid"), (few_dl, "BR", "dl")):
        e = _with(env, m, fn)
        det, row, st = ev(m, geo=e)
        r = cty(det)[cc]
        assert r["cpi"]["thin"] == why and r["cpi"]["v"] is not None, (cc, r["cpi"])
        assert r["verdict"] in NOCOST and r["pay"] is None and r["back"] is None, cc
        assert "ads chalu rakh sakte ho" not in r["text"] and r["text"].endswith("isliye ads ka faisla nahi"), r["text"]
        _, row, _ = ev(m, st=again(st), geo=e)
        assert cc not in [a["cc"] for a in alerts(row, "geo_cost")], cc
        d2, _, _ = ev(m, st=again(st), geo=e)
        assert cc not in (d2["tiles"]["cty"].get("keep") or []) + (d2["tiles"]["cty"].get("costly") or [])
    assert V._geo_thin(79.9, 500, 1000, 4) == "spend" and V._geo_thin(80, 49, 1000, 4) == "dl"
    assert V._geo_thin(80, 299, 1000, 4) == "paid" and V._geo_thin(80, 300, 1000, 4) is None
    assert V._geo_thin(80, None, 1000, 4) is None                     # downloads unknown: the spend rule only


def test_geo_cost_is_the_apps_when_every_country_is_alike_and_sent_once():
    """The whole app not paying back is pay_loss / pay_slow's news: countries whose cost ÷ value is the app's own
    raise no geo_cost at all; one much worse than the app does — and several countries at once send ONE
    notification per app (the biggest), the rest shown."""
    m = app()
    base = vs.geo_envelope(m)
    det0, _, _ = ev(m, geo=base)
    hi = {r["cc"]: r["be_hi"] for r in det0["countries"]["rows"] if r["be_hi"]}

    def alike(k, worse=None):                              # every country at k × its own q80 earning at H
        return lambda cc, n, v: ([k * (4 if cc == worse else 1) * hi[cc] * n, v[1], v[2]] if cc in hi and n else v)
    e = _with(base, m, alike(1.3))
    _, _, st = ev(m, geo=e)
    _, row, st2 = ev(m, st=again(st), geo=e)
    assert not alerts(row, "geo_cost")
    assert not any(v for k, v in st2["eval"]["streak"].items() if k.startswith("geo_cost|"))
    e = _with(base, m, alike(1.3, worse="NG"))                        # NG 4× worse than the rest: its own news
    _, _, st = ev(m, geo=e)
    _, row, _ = ev(m, st=again(st), geo=e)
    assert [a["cc"] for a in alerts(row, "geo_cost")] == ["NG"]
    e = _with(base, m, alike(0.5, worse="XXX"))                       # the app pays back; 3 countries 3× too costly
    e = _with(e, m, lambda cc, n, v: [v[0] * 6, v[1], v[2]] if cc in ("IN", "NG", "BR") else v)
    _, _, st = ev(m, geo=e)
    _, row, _ = ev(m, st=again(st), geo=e)
    got = alerts(row, "geo_cost")
    assert len(got) >= 2 and len([a for a in got if a["notify"]]) == 1
    sent = next(a for a in got if a["notify"])
    assert sent["severity"] == min((a["severity"] for a in got), key=V.SEV_ORDER.get)          # red first, then
    assert sent["spend"] == max(a["spend"] for a in got if a["severity"] == sent["severity"])   # the biggest


def test_geo_cost_streak_ends_when_the_country_stops_qualifying():
    """A streak of 1 is kept only across a window that could not be judged (a week not covered); a country that stops
    qualifying (too little cost, a trickle) or leaves the window's cost starts again from 0 — a first bad evaluation
    months later never alerts on its own."""
    m = app()
    env = _with(vs.geo_envelope(m), m, lambda cc, n, v: [0.25 * n, v[1], v[2]] if cc == "DE" else v)
    ws = win_weeks(ev(m)[0])
    _, row, st = ev(m, geo=env)
    assert st["eval"]["streak"].get("geo_cost|DE") == 1 and "DE" not in [a["cc"] for a in alerts(row, "geo_cost")]
    low = _with(env, m, lambda cc, n, v: [10.0 / len(ws), v[1], v[2]] if cc == "DE" else v)   # $10 in the window
    _, _, st2 = ev(m, st=again(st), geo=low)
    assert not st2["eval"]["streak"].get("geo_cost|DE")
    _, row, st3 = ev(m, st=again(st2), geo=env)
    assert "DE" not in [a["cc"] for a in alerts(row, "geo_cost")] and st3["eval"]["streak"]["geo_cost|DE"] == 1
    gone = _with(env, m, lambda cc, n, v: None if cc == "DE" else v)  # DE's cost gone from the window
    _, _, st4 = ev(m, st=again(st), geo=gone)
    assert not st4["eval"]["streak"].get("geo_cost|DE")
    _, _, st5 = ev(m, st=again(st))                                   # GADS_GEO off: no streak kept either
    assert not any(k.startswith("geo_cost|") for k in st5["eval"]["streak"])


def test_geo_money_back_uses_the_earning_weeks_own_cost():
    """₹ back per ₹100 after 30 days = the 30-day weeks' earnings ÷ THOSE weeks' Google Ads cost, never a newer cost
    over older earnings; the money back reads "seen" only when those weeks cost about what the window does."""
    m = app()
    env = vs.geo_envelope(m, mult={"DE": 0.6})
    det, _, _ = ev(m, geo=env)
    de = cty(det)["DE"]
    assert de["pay"]["obs"] is True and de["back"]["30_est"] is False and de["back"]["7_est"] is False
    wd = win_weeks(det)
    e2 = copy.deepcopy(env)
    for W in wd:                                          # DE's bid doubled in the 4 newest (cost) weeks only
        e2["weeks"][W]["by"]["DE"][0] *= 2
        e2["weeks"][W]["by"]["DE"][2] *= 2
    det2, _, _ = ev(m, geo=e2)
    de2 = cty(det2)["DE"]
    assert de2["cpi"]["v"] == pytest.approx(2 * de["cpi"]["v"], rel=1e-4)
    assert de2["back"]["30"] == pytest.approx(de["back"]["30"], rel=1e-3)     # older installs: their own cost
    assert de2["pay"]["obs"] is False                                        # the cost moved: ≈, not "seen"
    far = copy.deepcopy(env)                                                 # the 30-day weeks' cost not covered
    w30 = det["countries"]["win"]["from30"]
    far["weeks"][w30].update(cov=0.5, geo=0.5 * far["weeks"][w30]["spend"])
    det3, _, _ = ev(m, geo=far)
    assert det3["countries"]["geo_why"] == "ok" and cty(det3)["DE"]["back"]["30_est"] is True


def test_geo_not_paid_back_within_the_curve_is_late_not_few():
    """With country cost, a big country not paid back by the last age its curve reaches (no curve beyond) is "late"
    ("Not paid back in N days") — never "Few installs"; the legacy shapes keep their old verdicts."""
    m = app(start=vs.END - timedelta(days=30 * 7 - 1))
    det, _, _ = ev(m, geo=vs.geo_envelope(m, mult={"NG": 4.0, "IN": 2.0}))
    c = cty(det)
    for cc in ("NG", "IN"):
        assert c[cc]["n"] >= 1000 and c[cc]["verdict"] == "late", c[cc]["verdict"]
        assert c[cc]["pay"]["p"] is None and not c[cc]["pay"]["never"] and c[cc]["pay"]["upto"] == 90
        assert "90 din me paisa wapas nahi aaya" in c[cc]["text"]
    assert V._cost_verdict({"pay": {"p": None, "lo": None, "hi": None, "never": False, "q80_365": None, "upto": 30},
                            "cpi": {"v": 1.0}}, 90, env=True) == "wait"
    assert V._cost_verdict({"pay": {"p": 200, "lo": 150, "hi": None, "never": False, "q80_365": None},
                            "cpi": {"v": 1.0}}, 90, env=True) == "slow"
    assert V._cost_verdict({"pay": {"p": 200, "lo": 150, "hi": None, "never": False, "q80_365": None},
                            "cpi": {"v": 1.0}}, 90) == "few"             # the legacy path: as before


def test_geo_billed_currency_and_small_countries_share():
    """The ₹ view shows what Google Ads billed (a country's cost in the base currency, never today's rate); the small
    countries say their share of the cost and their cost per Google Ads download."""
    m = app()
    env = vs.geo_envelope(m, xx=0.01, small={"KE": 400})
    det, _, _ = ev(m, geo=env)
    ws = win_weeks(det)
    us = cty(det)["US"]
    billed = sum(env["weeks"][w]["by"]["US"][2] for w in ws)
    assert us["cpi"]["spend_src"] == pytest.approx(billed, rel=1e-5) and us["cpi"]["src"] == pytest.approx(billed / us["n"], rel=1e-5)
    co = det["countries"]
    assert co["cost"]["total_src"] == pytest.approx(sum(v[2] for w in ws for v in env["weeks"][w]["by"].values()), rel=1e-5)
    sm = co["small"]
    assert sm["share"] == pytest.approx(co["cost"]["small"] / co["cost"]["total"], abs=1e-3)
    assert sm["dl"] > 0 and sm["cpi_ads"] == pytest.approx(co["cost"]["small"] / sm["dl"], rel=1e-4)
    assert sm["cost_src"] == pytest.approx(co["cost"]["small_src"], rel=1e-6)
    assert sm["cpi_ads_src"] == pytest.approx(sm["cost_src"] / sm["dl"], rel=1e-4)
    tc = list(zip(us["trend"]["cpi"], us["trend"]["cpi_src"]))                  # the sparkline as billed, week by week
    assert any(a is not None for a, _ in tc) and all((a is None) == (b is None) and (a is None or b > 10 * a) for a, b in tc)
