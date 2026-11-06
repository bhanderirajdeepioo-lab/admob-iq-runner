"""GA4 devices all-time probe (admob_iq.fetch.ga4_devhist_probe + .github/workflows/ga4-devhist-probe.yml) — offline against a
fake GA4 with OLD install days (SYNTHETIC): the days picked, every read shape answers and ties on a whole fake, a fake that
drops activity past 427 days from the firstSessionDate-dimension reads is SEEN (the ties and the age bands say so), a
refusal / a Stop / a bug in the facts cost only themselves, and the PUBLIC log stays counts-only."""
import json
import os
import re
from datetime import date, datetime, timedelta, timezone

import yaml

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_devhist_probe as hp
from tests.test_ga4_device_probe import CAMP, CC, KEY, MODELS, PID, RT, SECRETS, TOK, Fake, unit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)
F = ga4.window_end_in("UTC", NOW) - timedelta(days=hp.LATE)
FIRST = date(2025, 2, 3)                              # the first install day (weekly from here): ~615 days before F
REV = 0.01


class OldFake:
    """Weekly install groups from FIRST on, one per (day, model, country, campaign) of n users; a user is active at ages
    0 … 30 and (an old app) at age 440, REV USD each active day. drop_old: a read with firstSessionDate as a DIMENSION
    loses the activity past age 427 (the hypothesis this probe tests). refuse: dimension lists answered with a 400."""

    def __init__(self, drop_old=False, refuse=(), late_age=440):
        self.drop_old, self.refuse, self.late_age, self.calls = drop_old, set(refuse), late_age, []
        self.atoms = []
        d = FIRST
        while d <= F + timedelta(days=3):
            for b, m, mk, osv, cat, n in MODELS[:3]:
                for c in CC:
                    for camp in (CAMP, "(not set)"):
                        self.atoms.append({"fsd": d, "mobileDeviceBranding": b, "mobileDeviceModel": m,
                                           "mobileDeviceMarketingName": mk, "operatingSystemVersion": osv,
                                           "deviceCategory": cat, "countryId": c,
                                           "firstUserGoogleAdsCampaignId": camp, "n": n})
            d += timedelta(days=7)

    def __call__(self, method, url, token, body=None, params=None):
        assert method == "POST" and token == TOK and url.endswith("properties/%s:runReport" % PID)
        dims = [x["name"] for x in body.get("dimensions") or []]
        mets = [x["name"] for x in body["metrics"]]
        self.calls.append((dims, mets, body["dateRanges"][0]))
        if tuple(dims) in self.refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: DETAIL-PRIVATE")
        rg = body["dateRanges"][0]
        s, t = date.fromisoformat(rg["startDate"]), date.fromisoformat(rg["endDate"])
        agg = {}
        for a in self.atoms:
            for age in tuple(range(31)) + (self.late_age,):
                d = a["fsd"] + timedelta(days=age)
                if not (s <= d <= t) or d > F + timedelta(days=3) or not Fake._ok(body["dimensionFilter"], a, d):
                    continue
                if self.drop_old and "firstSessionDate" in dims and age > hp.OLD_AGE:
                    continue
                key = tuple(Fake.val(a, k, d) for k in dims)
                e = agg.setdefault(key, dict.fromkeys(mets, 0))
                for m in mets:
                    e[m] += {"newUsers": a["n"] if age == 0 else 0, "activeUsers": a["n"], "totalAdRevenue": REV * a["n"]}[m]
        rows = [{"dimensionValues": [{"value": v} for v in k], "metricValues": [{"value": str(e[m])} for m in mets]}
                for k, e in sorted(agg.items())]
        off, lim = body.get("offset", 0), body.get("limit", 10000)
        return {"dimensionHeaders": [{"name": x} for x in dims], "metricHeaders": [{"name": x} for x in mets],
                "rows": rows[off:off + lim], "rowCount": len(rows), "metadata": {"currencyCode": "USD"},
                "propertyQuota": {"tokensPerDay": {"consumed": 3, "remaining": 199000}}}


def _unit(hs="2025-01-01"):
    return dict(unit(), history_start=hs)


def run(monkeypatch, fake, units=None, opts=None):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    return hp.run_probe(units or [_unit()], "cid", "sec", [("o", RT)], dict({"app_calls": 200}, **(opts or {})), now=NOW,
                        tick=0)


# ── which days ──────────────────────────────────────────────────────────────────────────────────

def test_pick_days_takes_the_busiest_near_each_age_and_the_oldest():
    f = date(2026, 10, 10)
    counts = {f - timedelta(days=a): 5 for a in range(0, 700)}
    counts[f - timedelta(days=203)] = 50                 # the busiest within 10 days of F − 200
    counts[f - timedelta(days=446)] = 40                 # … of F − 450
    counts[f - timedelta(days=699)] = 9                  # the oldest 14 days: the busiest of them
    got = hp.pick_days(counts, f)
    assert [(lab, (f - x).days) for lab, x in got] == [("OLD", 699), ("A450", 446), ("A200", 203)]


def test_pick_days_skips_ages_the_app_does_not_reach_and_close_days():
    f = date(2026, 10, 10)
    young = {f - timedelta(days=a): 3 for a in range(0, 230)}
    assert [(lab, (f - x).days) for lab, x in hp.pick_days(young, f)] == [("OLD", 229)]     # A200 is within 30 days of it
    mid = {f - timedelta(days=a): 3 for a in range(0, 300)}
    assert [(lab, (f - x).days) for lab, x in hp.pick_days(mid, f)] == [("OLD", 299), ("A200", 210)]
    tiny = {f - timedelta(days=a): 3 for a in range(0, 120)}
    assert [(lab, (f - x).days) for lab, x in hp.pick_days(tiny, f)] == [("OLD", 119)]    # no age reached: the oldest only
    assert hp.pick_days({}, f) == [] and hp.pick_days({f: 0}, f) == []                    # no installs: nothing to read
    near = {f - timedelta(days=a): 3 for a in range(0, 215)}                              # OLD 214 and A200 14 days apart
    assert [lab for lab, _ in hp.pick_days(near, f)] == ["OLD"]


def test_the_read_shapes_are_the_fetchs_own():
    x = date(2025, 6, 15)
    rs = {k: (a, b, dims, mets, ex) for k, a, b, dims, mets, ex in hp.reads_for(x, F, oldest=False)}
    assert list(rs)[0] == "T1" and set(rs) == {"T1", "S", "SC", "SD", "T2", "MB", "S365"}
    assert rs["S"][:4] == (x, F, ("mobileDeviceModel", "countryId"), ("newUsers", "totalAdRevenue"))
    assert rs["S"][4] == [hp._fsd(x)] and rs["SD"][2] == ("date",) and "activeUsers" in rs["SD"][3]
    assert rs["T1"][0] == date(2025, 6, 1) and rs["T1"][2] == ("firstSessionDate", "date")
    days = rs["T1"][4][0]["filter"]["inListFilter"]["values"]
    assert days[0] == "20250601" and days[-1] == "20250630" and len(days) == 30 and rs["MB"][4] == rs["T1"][4]
    assert rs["MB"][2] == ("firstSessionDate", "mobileDeviceModel", "countryId")
    assert rs["S365"][:3] == (x, x + timedelta(days=364), ())
    fresh = date(2026, 5, 20)                                    # < 364 days of activity so far: no S365; month cut at F
    assert "S365" not in {r[0] for r in hp.reads_for(fresh, F)}
    old = {r[0]: r for r in hp.reads_for(x, F, oldest=True)}
    assert {"P", "PT", "D1", "D1T"} <= set(old) and old["P"][1:3] == (x, x)
    assert old["D1"][1] == x + timedelta(days=1) and old["D1"][5] == [hp._fsd(x)]
    assert old["P"][5][1]["filter"]["fieldName"] == "firstUserGoogleAdsCampaignId"
    last = date(2026, 10, 1)
    m0, m1, md = hp.month_of(last, F)
    assert m0 == date(2026, 10, 1) and m1 == F and md[-1] == F


# ── a whole fake ────────────────────────────────────────────────────────────────────────────────

def test_every_shape_answers_and_ties_on_a_whole_fake(monkeypatch, capsys):
    rep = run(monkeypatch, OldFake())
    a = rep["apps"][KEY]
    assert a["complete"] and not a.get("stopped") and a["F"] == F.isoformat()
    assert [t["label"] for t in a["xs"]] == ["OLD", "A450", "A200"] and a["xs"][0]["age"] > 600
    assert all(r["ok"] for r in a["reads"].values())
    kinds = {k.split("@")[0] for k in a["reads"]}
    assert kinds == set(hp.KINDS)
    oldest = a["xs"][0]["x"]
    assert {"P@" + oldest, "D1@" + oldest, "PT@" + oldest, "D1T@" + oldest} <= set(a["reads"])
    assert not any(k.startswith(("P@", "D1@")) for k in a["reads"] if not k.endswith(oldest))
    for t in a["xs"]:
        f = a["facts"][t["x"]]
        for k, tie in f["ties"].items():
            assert all(v == 1.0 for v in tie.values()), (k, tie)
        xt = f["x_ties"]
        assert xt["MBcells_vs_S"] == 1.0 and all(v == 1.0 for v in xt["MB_vs_S"].values())
        assert all(v == 1.0 for v in xt["S_vs_SD"].values())
        assert all(v == 1.0 for v in xt["MBmonth_vs_T1month"].values())
        assert xt.get("S365_vs_SD364") == ({"totalAdRevenue": 1.0} if t["age"] >= 364 else None)    # S365 only when reached
    old = a["facts"][oldest]
    assert old["sd"]["bands"]["gt427"] > 0 and old["sd"]["share_gt427"] > 0 and old["sd"]["last_age"] == 440
    assert old["t1"]["old_rev"] == old["sd"]["bands"]["gt427"] and old["sd"]["act_gt427"] > 0
    cum = old["sd"]["cum"]
    assert cum["0"] < cum["30"] <= cum["365"] and cum["365"] == old["sd"]["rev364"]
    young = a["facts"][a["xs"][-1]["x"]]
    assert young["sd"]["bands"]["gt427"] == 0 and young["sd"]["cum"]["365"] is None      # not reached yet: no checkpoint
    assert a["facts"][oldest]["ties"]["P"] == {"newUsers": 1.0} and a["facts"][oldest]["ties"]["D1"] == {"activeUsers": 1.0}
    for r in a["reads"].values():                               # the cost of every call is kept
        assert r["tok"] >= 0 and "sec" in r and r["calls"] >= 1
    assert a["tokens"] > 0 and sum(v["calls"] for v in a["calls"].values()) == rep["counts"]["calls"]


def test_counts_and_the_public_log_are_counts_only(monkeypatch, capsys):
    rep = run(monkeypatch, OldFake(), opts={})
    c = rep["counts"]
    assert c["apps"] == 1 and c["complete"] == 1 and c["days"] == 3 and c["stopped"] == 0
    assert c["kinds"]["S"]["n"] == 3 and c["kinds"]["S"]["low"] == 0 and c["kinds"]["S"]["high"] == 0
    assert c["kinds"]["P"]["n"] == 1 and c["gt427"]["n"] > 0 and c["gt427"]["ok"] == c["gt427"]["n"]
    lines = hp.public_lines(c)
    out = capsys.readouterr().out + "\n".join(lines)
    for s in SECRETS + [FIRST.isoformat(), "2025"]:
        assert s not in out
    assert len(lines) == len(hp.KINDS) + 2
    assert all(re.fullmatch(r"devhist probe: (\w+ n \d+ ok \d+ refused \d+ tie<0\.98 \d+ tie>1\.02 \d+ other \d+|"
                            r"older than 427 days n \d+ ok \d+ refused \d+ tie<0\.98 \d+ tie>1\.02 \d+ other \d+|"
                            r"apps \d+, days \d+, complete \d+, stopped \d+, calls \d+, tokens \d+, \d+s)", ln)
               for ln in lines), lines


# ── the hypothesis, seen ────────────────────────────────────────────────────────────────────────

def test_a_fake_that_drops_old_ages_from_the_dimension_reads_is_seen(monkeypatch):
    rep = run(monkeypatch, OldFake(drop_old=True))
    a = rep["apps"][KEY]
    oldest, mid = a["xs"][0]["x"], a["xs"][1]["x"]
    for x in (oldest, mid):                                    # both past 427 days of activity
        f = a["facts"][x]
        assert f["sd"]["share_gt427"] > 0                       # the date read (no fsd dimension) keeps the old ages …
        assert all(v == 1.0 for v in f["x_ties"]["S_vs_SD"].values())          # … and so does the S split (a filter) …
        assert f["ties"]["S"]["totalAdRevenue"] > hp.TIE_HI                    # … which is MORE than the truth T1 gave
        assert f["ties"]["T2"]["totalAdRevenue"] == 1.0                        # the two truth shapes drop the same
        assert f["x_ties"]["MB_vs_S"]["totalAdRevenue"] < hp.TIE_LO            # the month-batched read lost them
        assert f["x_ties"]["MBcells_vs_S"] < 1.0
        assert f["t1"]["old_rev"] == 0 and f["t1"]["last_age"] == 30
    young = a["facts"][a["xs"][-1]["x"]]
    assert young["ties"]["S"]["totalAdRevenue"] == 1.0         # an install day under 427 days of activity is untouched
    c = rep["counts"]
    assert c["kinds"]["S"]["high"] == 2 and c["kinds"]["MB"]["low"] == 0       # MB vs T1 (both drop): equal
    assert c["gt427"]["high"] >= 2


def test_a_refused_shape_is_kept_as_its_class_and_the_rest_goes_on(monkeypatch):
    rep = run(monkeypatch, OldFake(refuse=[("firstSessionDate",)]))        # T2 and PICK use this dimension list alone
    a = rep["apps"][KEY]
    assert a["reads"]["PICK"] == dict(a["reads"]["PICK"], ok=False, err={"http": 400, "status": "INVALID_ARGUMENT"})
    assert not a["complete"] and a["xs"] == []                            # no PICK: no day to read
    rep = run(monkeypatch, OldFake(refuse=[("countryId",)]))               # SC alone
    a = rep["apps"][KEY]
    assert a["complete"] and all(r["ok"] for k, r in a["reads"].items() if not k.startswith("SC@"))
    assert all(r["err"] == {"http": 400, "status": "INVALID_ARGUMENT"} for k, r in a["reads"].items() if k.startswith("SC@"))
    assert rep["counts"]["kinds"]["SC"]["refused"] == 3 and "SC" not in a["facts"][a["xs"][0]["x"]]["ties"]


def test_a_stop_keeps_what_was_read_and_a_bug_in_the_facts_costs_the_facts_only(monkeypatch):
    rep = run(monkeypatch, OldFake(), opts={"max_calls": 2})
    a = rep["apps"][KEY]
    assert a["stopped"] == "calls" and not a["complete"] and len(a["xs"]) == 1
    f = a["facts"][a["xs"][0]["x"]]
    assert "vals" in f and "T1" in f["vals"] and not f["ties"]             # PICK + T1 were read: no tie yet
    monkeypatch.setattr(hp, "facts_for", lambda *a: [][1])
    rep = run(monkeypatch, OldFake())
    a = rep["apps"][KEY]
    assert all(v == {"bug": True, "err": {"type": "IndexError"}} for v in a["facts"].values())
    assert a["complete"] and all(r["ok"] for r in a["reads"].values())


def test_no_token_is_an_auth_error_and_a_crash_costs_one_app(monkeypatch):
    monkeypatch.setattr(ga4, "_call", OldFake())
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    rep = hp.run_probe([_unit()], "cid", "sec", [("other", RT)], {}, now=NOW, tick=0)
    assert rep["apps"][KEY] == dict(rep["apps"][KEY], err={"type": "auth"}, complete=False)
    monkeypatch.setattr(hp, "probe_app", lambda *a: [][1])
    rep = hp.run_probe([_unit()], "cid", "sec", [("o", RT)], {}, now=NOW, tick=0)
    assert rep["apps"][KEY]["crash"] == "IndexError" and rep["counts"]["complete"] == 0


# ── run options, the private write, the workflow ───────────────────────────────────────────────

def test_options_and_the_output_path():
    o = hp.options({"apps": "A, b", "ages": "300, 9999, x, 600", "tag": "../R2!", "max_calls": "9"}, {})
    assert o["apps"] == {"a", "b"} and o["ages"] == (300, 600) and o["tag"] == "r2" and o["max_calls"] == 9
    assert hp.out_path("r2") == "ga4/devices_alltime_probe_r2.json" and hp.out_path("") == hp.OUT_PATH
    dflt = hp.options({}, {"DEVHIST_BUDGET_SEC": "30"})
    assert dflt["ages"] == hp.AGES and dflt["tag"] == "" and dflt["budget"] == 30 and dflt["max_calls"] == hp.MAX_CALLS


def test_main_writes_one_private_report_and_prints_counts_only(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ga4, "_call", OldFake())
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    monkeypatch.setattr(hp.sp, "load_state", lambda root: {"root": root})
    monkeypatch.setattr(hp.cp, "units_from_state", lambda st: [_unit()])
    monkeypatch.setattr(hp.ga4_probe, "owner_tokens", lambda env: ([("o", RT)], None))
    put = {}
    monkeypatch.setattr(hp.pr, "write_private", lambda path, text, msg: bool(put.update({path: text})) or True)
    ev = tmp_path / "event.json"
    ev.write_text(json.dumps({"inputs": {"apps": "nomatch-" + KEY, "tag": "t1"}}))
    env = {"GA4_CLIENT_ID": "cid", "GA4_CLIENT_SECRET": "sec", "GITHUB_EVENT_PATH": str(ev), "DEVHIST_DATA_DIR": str(tmp_path)}
    try:
        hp.main(env, now=NOW)
        assert False, "no app matched: the run must stop"
    except SystemExit as e:
        assert "none matched" in str(e) and not put
    ev.write_text(json.dumps({"inputs": {"apps": KEY, "tag": "t1"}}))
    capsys.readouterr()
    hp.main(env, now=NOW)
    out = capsys.readouterr().out
    assert list(put) == ["ga4/devices_alltime_probe_t1.json"]
    rep = json.loads(put["ga4/devices_alltime_probe_t1.json"])
    assert rep["probe"] == "ga4_devhist" and rep["apps"][KEY]["complete"] and rep["counts"]["days"] == 3
    for s in SECRETS:
        assert s not in out
    assert out.strip().splitlines()[-1] == "devhist probe: report written"


def test_the_workflow_keeps_secrets_and_details_off_the_public_log():
    with open(os.path.join(ROOT, ".github", "workflows", "ga4-devhist-probe.yml"), encoding="utf-8") as fh:
        text = fh.read()
    wf = yaml.safe_load(text)
    on = wf.get("on", wf.get(True))
    assert set(on) == {"workflow_dispatch"} and set(on["workflow_dispatch"]["inputs"]) == {"apps", "ages", "tag"}
    assert "inputs.apps" not in text and "inputs.ages" not in text and "inputs.tag" not in text    # event file only
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["probe"]
    assert job["runs-on"] == "ubuntu-24.04" and job["timeout-minutes"] == 40 and hp.BUDGET_SEC < 30 * 60
    steps = job["steps"]
    assert steps[0]["with"]["persist-credentials"] is False
    for st in steps:
        env = st.get("env") or {}
        if st.get("name") == "Run":
            assert st["run"].startswith("python -m admob_iq.fetch.ga4_devhist_probe 2>/tmp/")
            assert "details kept off the public log" in st["run"] and env["DEVHIST_DATA_DIR"] == "_private"
        else:
            assert not any(k.startswith("GA4_") for k in env), st.get("name")
            assert "secrets.GA4_" not in json.dumps(st)
        if "clone" in (st.get("run") or ""):
            assert "> /dev/null 2>&1" in st["run"] and "@github.com" not in st["run"]
            assert "http.extraheader" in st["run"] and "::add-mask::" in st["run"]
