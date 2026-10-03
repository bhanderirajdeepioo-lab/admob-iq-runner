"""👥 Audience tab — the build step (admob_iq.audience_build + its build_static wiring), on a synthetic world
(tests/audience_tab_synth.py: made-up apps, ids and numbers; no real data):

  * the demo's formulas, recomputed here straight from the synthetic stores: the phone split (installed = Σ new − Σ un,
    sleeping = installed − (a28 − un28), "data kam"), the journey, the long-term return, the money model (own old users,
    and a young app's all-apps typical), "pakke" users, today's DAU by install age, the day-wise removals and flags;
  * dead users by months: a COMPLETE GA4 Audience store is engine.audience's own numbers (months from the store, the
    dead_lo … dead range, most dead / active month, DAU by install month), the portfolio on the engine's tiered months;
    no complete result (a partial read, a broken store, a failing derive) → the cohort-curve estimate on the same tiered
    months, marked "andaza" (+ "being read" while a partial is under way); the estimate's own arithmetic on a tiny case;
  * the step: one file + pointer, deterministic bytes, ONE counts-only log line, the size guard, failure isolation (an
    app, the GA4 part of an app, or the whole step), the switch AUDIENCE_TAB (off: the site exactly as without it),
    _headers (ONE splat rule covers the file — never a rule per app), the wiring in build_static and refresh.yml."""

import copy
import gzip
import json
import os
import re
import shutil
from datetime import date, timedelta

import pytest

from admob_iq import audience_build as ab
from admob_iq import build_static
from admob_iq.config import settings
from admob_iq.deploy_guard import HEADERS_MAX_RULES, headers_cover, headers_rule_count
from admob_iq.engine import audience as aud_eng
from admob_iq.engine import uninstall as ueng
from tests import audience_tab_synth as sy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = re.compile(r"^audience: apps \d+, skipped \d+, ga4 \d+, estimate \d+, reading \d+, kb \d+$")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("aud"))
    data, site, dash = sy.make_world(root)
    counts = {}
    body = ab.build_data(copy.deepcopy(dash), data, site, counts)
    return {"root": root, "data": data, "site": site, "dash": dash, "body": body, "counts": counts}


@pytest.fixture
def fresh(world, tmp_path):
    """A copy of the world each test may change → (data, site, dashboard)."""
    data, site = str(tmp_path / "data"), str(tmp_path / "site")
    shutil.copytree(world["data"], data)
    shutil.copytree(world["site"], site)
    return data, site, copy.deepcopy(world["dash"])


def _gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def _st(world, key):
    return _gz(os.path.join(world["data"], "ga4_uninstall", key + ".json.gz"))


def _app(world, name):
    return next(e for e in world["body"]["apps"] if e["n"] == name)


def _close(a, b, tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


E = sy.E
GA4, EST, PART, YOUNG = "Demo Gallery · Studio Nine", "Demo Notes", "Demo Timer · A/c 77", "Demo Young"


# ── the demo's formulas, recomputed ─────────────────────────────────────────────────────────────────────────────────
def test_counts_and_who_is_left_out(world):
    c = world["counts"]
    assert c["skipped"] == 1                                        # Demo Broken: its cohort file is missing
    assert c["ga4"] == 1 and c["andaza"] == 3 and c["coming"] == 1
    assert sorted(e["n"] for e in world["body"]["apps"]) == sorted([GA4, EST, PART, YOUNG])
    assert [e["inst"] for e in world["body"]["apps"]] == sorted((e["inst"] for e in world["body"]["apps"]), reverse=True)
    assert world["body"]["no_ga4"] == ["Demo Clock"] and world["body"]["cur"] == "USD" and world["body"]["fx"] == sy.FX


def test_phone_split_is_installs_minus_uninstalls(world):
    for e in world["body"]["apps"]:
        st = _st(world, e["k"])
        days = [k for k in st["daily"] if k <= E.isoformat()]
        new = sum(st["daily"][k]["new"] for k in days)
        un = sum(st["daily"][k]["un"] for k in days)
        w28 = [(E - timedelta(days=i)).isoformat() for i in range(28)]
        un28 = sum(st["daily"][k]["un"] for k in w28)
        a1, a28 = st["daily"][E.isoformat()]["a1"], st["daily"][E.isoformat()]["a28"]
        inst = new - un
        raw = inst - (a28 - un28)
        kam = inst <= 0 or raw < -max(50, 0.02 * inst) or (a28 - un28) < a1
        assert (e["ins"], e["rem"], e["inst"], e["a1"], e["a28"], e["un28"], e["a28k"]) == (new, un, inst, a1, a28, un28, a28 - un28)
        assert e["sl"] == max(0, raw) and e["kam"] == kam


def test_journey_opened_is_the_active_tabs_return_and_removed_its_survival(world):
    U = {a["key"]: a for a in _gz(os.path.join(world["site"], "uninstall.json.gz"))["apps"]}
    for e in world["body"]["apps"]:
        st = _st(world, e["k"])
        left = U[e["k"]]["survival"]["all"]["left"]
        for N in (1, 7, 30):
            num = den = 0
            for c, r in st["ret"].items():
                cd = date.fromisoformat(c)
                if cd + timedelta(days=N) <= E and st["daily"][c]["new"] > 0:
                    num += r["a"][N]
                    den += st["daily"][c]["new"]
            o, gone = num / den, 1 - left[N]
            j = e["j"][str(N)]
            assert _close(j[0], round(o, 5)) and _close(j[2], round(gone, 5)) and _close(j[1], round(max(0, 1 - gone - o), 5))
            assert j[3] == den                                       # the installs behind it (the page prints counts)


def test_long_term_needs_enough_installs_behind_each_day(world):
    e = _app(world, GA4)
    iday = _gz(os.path.join(world["data"], "ga4_uninstall", "iday", e["k"] + ".json.gz"))
    j = ab.ULAGS.index(90)
    num = den = days = 0
    for X, r in iday["x"].items():
        if date.fromisoformat(X) + timedelta(days=90) <= E:
            num, den, days = num + r["u"][j], den + r["n"], days + 1
    assert e["lt"]["90"] == [round(num / den, 5), den]
    old = [r for X, r in iday["x"].items() if date.fromisoformat(X) + timedelta(days=365) <= E]
    assert len(old) >= 21 and e["lt"]["365"] == [round(sum(r["u"][-1] for r in old) / sum(r["n"] for r in old), 5),
                                                 sum(r["n"] for r in old)]
    assert "270" not in _app(world, PART)["lt"]                     # 210 days of history: no install day 270 days old
    assert list(_app(world, YOUNG)["lt"]) == ["30"]                 # no install-day data: day 30 = the Active tab's own


def test_money_is_the_demos_old_user_model(world):
    body = world["body"]
    own = []
    for e in body["apps"]:
        st = _st(world, e["k"])
        pf = {a["key"]: a for a in _gz(os.path.join(world["site"], "active_portfolio.json.gz"))["apps"]}[e["k"]]
        p0 = date.fromisoformat(pf["start"])
        rev = a1 = 0.0
        for i in range(28):
            d = E - timedelta(days=i)
            j = (d - p0).days
            if 0 <= j < len(pf["a1"]) and pf["a1"][j]:
                rev, a1 = rev + pf["rev"][j], a1 + pf["a1"][j]
        assert _close(e["arp"], round(rev / a1, 8), 1e-6) and e["rev28"] == round(rev, 2) and e["a128"] == round(a1)
        assert _close(e["pm"], round(rev / e["a28"] * 30 / 28, 8), 1e-6)
        if e["own"]:
            own.append(e)
    assert sorted(x["n"] for x in own) == sorted([GA4, EST, PART])
    y = _app(world, YOUNG)                                          # a young app: the all-apps typical frequency and ratio
    assert y["own"] is False and y["fq"] is not None and y["ra"] is not None
    ratios = sorted(x["ra"] / x["arp"] for x in own)
    assert _close(y["ra"], round(y["arp"] * ratios[len(ratios) // 2], 8), 1e-4)


def test_pakke_and_todays_users_by_install_age_are_the_iday_bands(world):
    e = _app(world, GA4)
    de = _gz(os.path.join(world["data"], "ga4_uninstall", "iday", e["k"] + ".json.gz"))["days"][E.isoformat()]
    ga, ab_ = de["a"], de["ab"]
    assert e["pk"] == round((ab_[4] + ab_[5] + max(0, ga - de["a4"])) * e["a1"] / ga)
    want = [round(v * e["a1"] / ga) for v in (ab_[0] + ab_[1] + ab_[2], ab_[3], ab_[4], ab_[5] + max(0, ga - de["a4"]))]
    assert e["au"]["bands"] == want
    assert _app(world, YOUNG)["pk"] is None and _app(world, YOUNG)["au"]["bands"] is None


def test_day_wise_is_the_uninstall_tabs_cells_and_flags_every_day_since_the_launch(world):
    e = _app(world, EST)
    cf = _gz(os.path.join(world["site"], "uninstall_c_%s.json.gz" % e["k"]))
    dw = e["dw"]
    s = date.fromisoformat(dw["s"])
    assert len(dw["n"]) == (E - s).days + 1 == len(dw["f"]) and len(dw["u"]) == 5 * len(dw["n"])   # never trimmed
    for i in (0, 37, 250, len(dw["n"]) - 1):
        d = s + timedelta(days=i)
        j = (d - date.fromisoformat(cf["start"])).days
        age = (E - d).days
        bk = [0] * 5
        for lag, u in cf["lags"][j]:
            if lag <= age:
                bk[0 if lag == 0 else 1 if lag <= 7 else 2 if lag <= 30 else 3 if lag <= 90 else 4] += u
        assert dw["n"][i] == cf["new"][j] and dw["u"][5 * i:5 * i + 5] == bk
    f = {(s + timedelta(days=i)).isoformat(): ch for i, ch in enumerate(dw["f"])}
    inc, est = (E - timedelta(days=100)).isoformat(), (E - timedelta(days=200)).isoformat()
    assert f[inc] == "1" and f[(E - timedelta(days=110)).isoformat()] == "2" and f[est] == "3"
    assert f[(E - timedelta(days=150)).isoformat()] == "0" and f[E.isoformat()] == "4"


# ── dead users by months ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_complete_ga4_store_is_the_engines_own_numbers(world):
    e = _app(world, GA4)
    store = _gz(os.path.join(world["data"], "ga4_audience", e["k"] + ".json.gz"))
    out = aud_eng.derive_app(store, ueng.fill_days(_st(world, e["k"])))
    au = e["au"]
    assert au["src"] == "ga4" and au["E"] == out["E"] and au["mo"] == store["months"] == out["months"]
    assert (au["ins"], au["inst"], au["d"], au["lo"]) == (out["installs"], out["installed"], out["dead"], out["dead_lo"])
    assert au["lo"] != au["d"] and all(lo <= d for lo, d in zip(au["lo"], au["d"]))      # a real range
    assert au["most"] == json.loads(json.dumps(out["most"]))
    rows = {r[0]: r for r in au["m"]}
    for mo, g in out["months_by"].items():
        if g["installs"]:
            r = rows[mo]
            assert r[1:6] == [g["installs"], g["installed"], g["dead"][0], g["dead_lo"][0], 1 if g["young_days"][0] else 0]
            assert r[6] == out["dau"]["by_month"].get(mo, 0)
    assert au["clamps"] == json.loads(json.dumps(out["clamps_by_month"])) and au["clamps"].get("un_gt_act")
    # the page's buckets between consecutive months = engine.audience's last_open
    inst, d = au["inst"], au["d"]
    mine = [inst - d[0]] + [d[i - 1] - d[i] for i in range(1, len(d))] + [d[-1]]
    assert mine == [b["users"] for b in out["last_open"]]


def test_the_portfolio_is_the_engines_on_its_tiered_months(world):
    ga4 = [e for e in world["body"]["apps"] if e["au"]["src"] == "ga4" and not e["kam"]]
    mine = ab.portfolio_au(ga4)
    outs = []
    for e in ga4:
        store = _gz(os.path.join(world["data"], "ga4_audience", e["k"] + ".json.gz"))
        outs.append(aud_eng.derive_app(store, ueng.fill_days(_st(world, e["k"]))))
    pf = aud_eng.portfolio(outs)
    assert mine["mo"] == pf["months"] and mine["d"] == pf["dead"] and mine["lo"] == pf["dead_lo"]
    assert mine["inst"] == pf["installed"] and mine["ins"] == pf["installs"]
    mixed = world["body"]["all"]["au"]
    assert mixed["src"] == "mix" and mixed["n_ga4"] == 1 and mixed["n_andaza"] == 3
    assert mixed["mo"] == aud_eng.tier_months(aud_eng.window_days(max(e["au"]["mo"][-1] for e in world["body"]["apps"])))


def test_the_estimate_uses_the_same_tiered_months_and_adds_up(world):
    for name in (EST, PART, YOUNG):
        e = _app(world, name)
        au = e["au"]
        hist = (E - date.fromisoformat(e["L"])).days + 1
        assert au["src"] == "andaza" and au["lo"] is None and au["mo"] == aud_eng.tier_months(hist) and au["full"]
        assert all(a >= b for a, b in zip(au["d"], au["d"][1:])) and au["d"][-1] == 0      # never rising; all young past it
        assert au["d"][0] == sum(r[3] for r in au["m"])
        assert au["m"][-1][0] == E.isoformat()[:7] and au["m"][-1][5] == 1 and au["m"][-1][3] == 0   # all < 1 month old: 0
        assert all(0 <= r[3] <= r[2] <= r[1] for r in au["m"])
        assert au["inst"] == sum(r[2] for r in au["m"]) and au["ins"] == sum(r[1] for r in au["m"])
        if name != YOUNG:                                                                  # mature months only
            assert au["most"]["dead"]["count"]["month"] < E.isoformat()[:7]
        else:                                                                              # (45 days: none yet)
            assert au["most"]["dead"]["count"] is None
    assert _app(world, PART)["au"]["coming"] is True and _app(world, EST)["au"]["coming"] is False
    assert [ab.andaza_window(m) for m in range(1, 13)] == [30, 61, 91, 122, 152, 183, 213, 244, 274, 304, 335, 365]


def test_the_estimates_arithmetic_on_a_tiny_case():
    # one install day of 100 users, nobody uninstalls, every opener stays at 10% a day from day 28: the 28-day actives
    # still installed = 40 → k = 4 (S = 0.4 from day 28) → 60 users left the pool on day 28, 60 days ago: not opened
    # for ≥ 1 month (30 days) — and not for ≥ 2 months (61 days)
    A = 60
    r = [1.0] + [0.1] * A
    total, k, how, per = ab.dead_model([100], [[1.0] * (A + 1)], [A], [1.0], r, 40, 0.0, [30, 61])
    assert how == "ok" and abs(k - 4) < 1e-9 and abs(total - 60) < 1e-6
    assert [round(v, 6) for v in per[0]] == [60.0, 0.0]
    assert ab.dead_model([100], [[1.0] * (A + 1)], [A], [1.0], r, 0, 0.0, [30])[2] == "zero"
    assert ab.dead_model([100], [[1.0] * (A + 1)], [A], [1.0], r, 500, 0.0, [30])[2] == "over"


def test_the_return_curve_never_rises_past_its_last_knot():
    ret = {N: (0.3 * N ** -0.5, 10000, 100) for N in range(1, 31)}
    longr = {90: (0.03, 50000, 200), 180: (0.02, 40000, 150)}
    r, knots, b, last = ab.curve(ret, longr, 800, 100000)
    assert last == 180 and b <= 0 and all(r[t + 1] <= r[t] + 1e-12 for t in range(last, 800))
    assert abs(r[90] - 0.03) < 1e-12 and abs(r[180] - 0.02) < 1e-12


def test_a_partial_store_is_never_used_and_a_complete_one_always_is(fresh):
    data, site, dash = fresh
    keys = {sy.APPS[i][1]: sy.key_of(sy.APPS[i][0]) for i in range(len(sy.APPS))}
    path = lambda n: os.path.join(data, "ga4_audience", keys[n] + ".json.gz")
    full = _gz(path(GA4))
    sy._wgz(path(GA4), dict(full, partial={"E": "2026-09-21", "ranges": {}}))          # a newer read under way
    v1 = {k: v for k, v in full.items() if k not in ("complete", "months", "v")}          # the first probe's format
    sy._wgz(path(EST), dict(v1, windows=full["windows"]))
    with open(path(PART), "wb") as f:
        f.write(b"not a gzip")                                                            # broken: the estimate
    counts = {}
    body = ab.build_data(dash, data, site, counts)
    by = {e["n"]: e for e in body["apps"]}
    assert by[GA4]["au"]["src"] == "ga4" and by[EST]["au"]["src"] == "ga4"
    assert by[EST]["au"]["mo"] == [int(round(w / aud_eng.MONTH_DAYS)) for w in full["windows"]]
    assert by[PART]["au"]["src"] == "andaza" and by[PART]["au"]["coming"] is False and counts["store_bad"] == 1


def test_a_failing_ga4_derive_costs_that_apps_ga4_part_only(fresh, monkeypatch):
    data, site, dash = fresh
    monkeypatch.setattr(aud_eng, "derive_app", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    counts = {}
    body = ab.build_data(dash, data, site, counts)
    assert counts["ga4_bad"] == 1 and counts["ga4"] == 0 and len(body["apps"]) == 4
    assert {e["au"]["src"] for e in body["apps"]} == {"andaza"}


def test_missing_inputs_cost_only_that_app(fresh):
    data, site, dash = fresh
    os.remove(os.path.join(data, "ga4_uninstall", sy.key_of(sy.APPS[1][0]) + ".json.gz"))
    counts = {}
    body = ab.build_data(dash, data, site, counts)
    assert counts["skipped"] == 2 and len(body["apps"]) == 3


def test_install_months_reach_the_launch(world):
    for e in world["body"]["apps"]:
        months = [r[0] for r in e["au"]["m"]]
        assert months[0] == e["L"][:7] and months[-1] == E.isoformat()[:7]


# ── the step ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_file_pointer_and_deterministic_bytes(fresh, capsys):
    data, site, dash = fresh
    paths = ab.run(dash, data, site, settings())
    assert paths == ["/audience*"]
    p = os.path.join(site, ab.FILE)
    body = _gz(p)
    assert body["v"] == ab.V and len(body["apps"]) == 4 and set(body["all"]) >= {"j", "lt", "rev28", "a1_28", "au"}
    assert dash["audience"]["file"] == ab.FILE and re.fullmatch(r"[0-9a-f]{12}", dash["audience"]["v"])
    line = ab.pop_line()
    assert LINE.match(line) and ab.pop_line() is None
    raw, m0 = open(p, "rb").read(), os.path.getmtime(p)
    os.utime(p, (m0 - 100, m0 - 100))
    d2 = copy.deepcopy(dash)
    ab.run(d2, data, site, settings())
    assert open(p, "rb").read() == raw and os.path.getmtime(p) == m0 - 100 and d2["audience"] == dash["audience"]


def test_the_log_line_names_nothing(fresh, capsys):
    data, site, dash = fresh
    build_static._audience_step(dash, data, site, settings())
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and LINE.match(err[0])
    for a in sy.APPS:
        assert a[1].split(" · ")[0] not in err[0] and a[0] not in err[0]


def test_without_active_users_data_no_file(fresh):
    data, site, dash = fresh
    open(os.path.join(site, ab.FILE), "w").write("stale")
    dash.pop("active")
    assert ab.run(dash, data, site, settings()) == [] and not os.path.exists(os.path.join(site, ab.FILE))
    assert "audience" not in dash and ab.pop_line().startswith("audience: apps 0")


def test_past_the_size_cap_nothing_is_written(fresh, monkeypatch):
    data, site, dash = fresh
    monkeypatch.setattr(ab, "MAX_GZ", 100)
    assert ab.run(dash, data, site, settings()) == [] and not os.path.exists(os.path.join(site, ab.FILE))
    assert "audience" not in dash and ab.pop_line().startswith("audience: too big")


def test_any_other_failure_costs_this_tab_only(fresh, monkeypatch, capsys):
    data, site, dash = fresh
    open(os.path.join(site, ab.FILE), "w").write("stale")
    before = copy.deepcopy(dash)
    monkeypatch.setattr(ab, "build_data", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret detail")))
    assert build_static._audience_step(dash, data, site, settings()) == []
    assert dash == before and not os.path.exists(os.path.join(site, ab.FILE))
    err = capsys.readouterr().err
    assert err.strip() == "audience skipped: RuntimeError" and "secret" not in err
    monkeypatch.setattr(ab, "run", lambda *a, **k: (_ for _ in ()).throw(KeyError("x")))
    assert build_static._audience_step(dash, data, site, settings()) == [] and "audience" not in dash


def test_switched_off_the_site_is_exactly_as_without_the_feature(fresh, capsys):
    data, site, dash = fresh
    before = sorted(os.listdir(site))
    open(os.path.join(site, ab.FILE), "w").write("from an earlier build")
    d0 = copy.deepcopy(dash)
    s = dict(settings(), audience_tab=False)
    assert build_static._audience_step(dash, data, site, s) == []
    assert sorted(os.listdir(site)) == before and dash == d0 and capsys.readouterr().err == ""
    assert build_static.headers_text([], dash, extra=[]) == build_static.headers_text([], d0)


def test_headers_one_splat_rule_covers_the_file(fresh):
    data, site, dash = fresh
    paths = ab.run(dash, data, site, settings())
    base = build_static.headers_text(["uninstall.json.gz"], dash)
    text = build_static.headers_text(["uninstall.json.gz"], dash, extra=paths)
    assert headers_rule_count(text) == headers_rule_count(base) + 1 <= HEADERS_MAX_RULES
    assert headers_cover(text, ab.FILE) and headers_cover(text, "audience_0123456789ab.json.gz")
    assert not headers_cover(base, ab.FILE)
    assert "/audience*\n  Cache-Control: no-store" in text and text.count("audience") == 1


def test_settings_and_workflow_pass_the_switch(monkeypatch):
    y = open(os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8").read()
    assert "AUDIENCE_TAB:         ${{ vars.AUDIENCE_TAB || 'true' }}" in y
    monkeypatch.delenv("AUDIENCE_TAB", raising=False)
    assert settings()["audience_tab"] is True
    monkeypatch.setenv("AUDIENCE_TAB", "false")
    assert settings()["audience_tab"] is False and ab.enabled(settings()) is False


def test_build_static_runs_the_step_after_the_studios_and_before_the_dashboard_is_written():
    src = open(os.path.join(ROOT, "admob_iq", "build_static.py"), encoding="utf-8").read()
    body = src[src.index("def build("):]
    i_v, i_a = body.index("_value_studio_step(dashboard"), body.index("_audience_step(dashboard")
    i_d, i_h = body.index('_shipgz(out_dir, "dashboard.json", dashboard)'), body.index("headers_text(uni_files")
    assert i_v < i_a < i_d < i_h and "+ aud_paths + any_paths" in body


def test_it_runs_on_the_files_the_real_uninstall_build_writes(tmp_path):
    """The shapes drift guard: the real uninstall build's synthetic site (tests/active_studio_synth.py) through the step."""
    from tests import active_studio_synth as ss
    site, cfg, dash = ss.make_site(str(tmp_path))
    counts = {}
    body = ab.build_data(dash, os.path.join(str(tmp_path), "data"), site, counts)
    assert counts.get("skipped", 0) == 0 and len(body["apps"]) == len(dash["active"]["apps"])
    for e in body["apps"]:
        assert len(e["dw"]["n"]) == (date.fromisoformat(e["E"]) - date.fromisoformat(e["dw"]["s"])).days + 1
        assert e["au"]["mo"] == aud_eng.tier_months((date.fromisoformat(e["E"]) - date.fromisoformat(e["L"])).days + 1)
