"""GA4 device probe (admob_iq.fetch.ga4_device_probe) — offline, against a fake GA4 Data API (ga4._call mocked), SYNTHETIC
data only: every request shape answers, the ties hold on a consistent fake, "(other)" lumping / refusals / a crash in the
facts are kept as shares, HTTP classes and a bug flag, and the PUBLIC log stays counts-only."""

import re
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_device_probe as dp
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)
RT, TOK, PID, SID = "rt-PRIVATE-a", "tok-PRIVATE-a", "100200300", "9000000001"
AID = "ca-app-pub-0000000000000000~11"
KEY = gu.file_key(AID)
CAMP = "555000111"                                   # a synthetic Google Ads campaign id
MODELS = (("XBrandA", "XM-001", "Phone One", "14", "mobile", 40), ("XBrandA", "XM-002", "(not set)", "13", "mobile", 30),
          ("XBrandB", "XM-003", "Phone Three", "14", "mobile", 20), ("XBrandC", "XM-004", "Tab Four", "12", "tablet", 6),
          ("XBrandC", "XM-005", "Phone Five", "11", "mobile", 4))
CC = ("XA", "XB")                                    # user-assigned ISO codes: never a real country
SECRETS = [RT, TOK, PID, SID, AID, KEY, CAMP, "PRIVATE"] + [m[1] for m in MODELS] + [m[2] for m in MODELS[:1]]
REV = 0.01                                           # USD per user a day, ages 0 .. 30


def unit():
    return {"key": KEY, "app_id": AID, "app_ids": [AID], "property_id": PID, "stream_id": SID, "tz": "UTC",
            "owner": "o", "history_start": "2026-01-01"}


class Fake:
    """Atoms: one install group per (install day, model, country, campaign) of n users, active ages 0 .. 30, REV each a
    day. lump: models whose rows a read with mobileDeviceModel answers as "(other)"; refuse: kinds answered 400."""

    def __init__(self, lump=(), refuse=()):
        self.lump, self.refuse, self.calls = set(lump), set(refuse), []
        f0 = date(2026, 1, 1)
        self.atoms = []
        for i in range((date(2026, 10, 13) - f0).days + 1):
            d = f0 + timedelta(days=i)
            for b, m, mk, osv, cat, n in MODELS:
                for c in CC:
                    for camp in (CAMP, "(not set)"):
                        self.atoms.append({"fsd": d, "mobileDeviceBranding": b, "mobileDeviceModel": m,
                                           "mobileDeviceMarketingName": mk, "operatingSystemVersion": osv,
                                           "deviceCategory": cat, "countryId": c,
                                           "firstUserGoogleAdsCampaignId": camp, "n": n})

    @staticmethod
    def _ok(expr, a, d):
        f = expr.get("filter")
        if f:
            name = f["fieldName"]
            v = {"platform": "Android", "streamId": SID}.get(name)
            if v is None:
                v = a["fsd"].strftime("%Y%m%d") if name == "firstSessionDate" else a.get(name)
            if "inListFilter" in f:
                return v in f["inListFilter"]["values"]
            sf = f["stringFilter"]
            if sf.get("matchType") == "FULL_REGEXP":
                return re.fullmatch(sf["value"], v or "", re.I) is not None
            return v == sf["value"]
        return all(Fake._ok(e, a, d) for e in expr["andGroup"]["expressions"])

    def __call__(self, method, url, token, body=None, params=None):
        assert method == "POST" and token == TOK and url.endswith("properties/%s:runReport" % PID)
        dims = [x["name"] for x in body.get("dimensions") or []]
        mets = [x["name"] for x in body["metrics"]]
        self.calls.append(dims)
        kind = self.kind(body, dims)
        if kind in self.refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: DETAIL-PRIVATE")
        agg = {}
        if "cohortSpec" in body:
            end = body["cohortSpec"]["cohortsRange"]["endOffset"]
            for c in body["cohortSpec"]["cohorts"]:
                x = date.fromisoformat(c["dateRange"]["startDate"])
                for a in self.atoms:
                    if a["fsd"] != x or not self._ok(body["dimensionFilter"], a, x):
                        continue
                    for age in range(end + 1):
                        key = tuple(c["name"] if k == "cohort" else "%04d" % age if k == "cohortNthDay"
                                    else self.val(a, k, x) for k in dims)
                        e = agg.setdefault(key, dict.fromkeys(mets, 0))
                        e["cohortTotalUsers"] += a["n"]
                        e["cohortActiveUsers"] += a["n"]
                        e["totalAdRevenue"] += REV * a["n"]
        else:
            rg = body["dateRanges"][0]
            s, t = date.fromisoformat(rg["startDate"]), date.fromisoformat(rg["endDate"])
            for a in self.atoms:
                for age in range(31):
                    d = a["fsd"] + timedelta(days=age)
                    if not (s <= d <= t) or not self._ok(body["dimensionFilter"], a, d):
                        continue
                    key = tuple(self.val(a, k, d) for k in dims)
                    e = agg.setdefault(key, dict.fromkeys(mets, 0))
                    for m in mets:
                        e[m] += {"newUsers": a["n"] if age == 0 else 0, "activeUsers": a["n"],
                                 "totalAdRevenue": REV * a["n"], "publisherAdImpressions": 10 * a["n"]}[m]
        if "mobileDeviceModel" in dims and self.lump:          # "(other)": the lumped models' rows folded together
            out = {}
            for k, e in agg.items():
                m = k[dims.index("mobileDeviceModel")]
                kk = tuple("(other)" if m in self.lump else v for v in k) if m in self.lump else k
                o = out.setdefault(kk, dict.fromkeys(mets, 0))
                for x in mets:
                    o[x] += e[x]
            agg = out
        rows = [{"dimensionValues": [{"value": v} for v in k], "metricValues": [{"value": str(e[m])} for m in mets]}
                for k, e in sorted(agg.items())]
        off, lim = body.get("offset", 0), body.get("limit", 10000)
        return {"dimensionHeaders": [{"name": x} for x in dims], "metricHeaders": [{"name": x} for x in mets],
                "rows": rows[off:off + lim], "rowCount": len(rows), "metadata": {"currencyCode": "USD"},
                "propertyQuota": {"tokensPerDay": {"consumed": 1, "remaining": 199000}}}

    @staticmethod
    def val(a, k, d):
        if k == "date":
            return d.strftime("%Y%m%d")
        if k == "yearMonth":
            return d.strftime("%Y%m")
        if k == "firstSessionDate":
            return a["fsd"].strftime("%Y%m%d")
        return a[k]

    @staticmethod
    def kind(body, dims):
        if "cohortSpec" in body:
            return "COH7" if len(body["cohortSpec"]["cohorts"]) > 1 else ("COHM" if "mobileDeviceModel" in dims else "COH0")
        return "+".join(dims)


def run(monkeypatch, fake, capsys=None):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    return dp.run_probe([unit()], "cid", "sec", [("o", RT)], {"win": 90}, now=NOW, tick=0)


def test_every_read_answers_and_ties_hold(monkeypatch):
    rep = run(monkeypatch, Fake())
    a = rep["apps"][KEY]
    assert a["complete"] and not a.get("stopped")
    assert set(a["reads"]) == set(dp.KINDS) and all(r["ok"] for r in a["reads"].values())
    f = a["facts"]
    for k in ("MOD", "OSV", "CAT", "PAID"):
        assert f["tie_" + k] == {"newUsers": 1.0, "totalAdRevenue": 1.0}, k
    assert f["tie_CELL"] == 1.0 and f["tie_CD"]["all"] == 1.0 and f["tie_CD"]["off2"] == 0
    assert all(f["tie_IDM"][m]["all"] == 1.0 for m in dp.NR)
    assert all(f["tie_DFM"][m]["all"] == 1.0 for m in dp.DAY_METS)
    assert all(f["tie_COHM"][m]["all"] == 1.0 for m in dp.COH_METS)
    assert f["hist"]["tie_rev"]["all"] == 1.0 and f["hist"]["first"] == "202601" and f["hist"]["first_model"] == "202601"
    assert f["hist"]["other_rev"] == 0 and f["hist"]["worst_month_other_rev"] == 0
    # the model facts: 5 models, the steps / coverage by installs (90 days × 2 countries × 2 campaigns × n)
    m = f["mod"]
    assert m["models"] == 5 and m["keys"] == 5
    assert m["steps"] == {"100": 5, "300": 5, "1000": 5, "3000": 3}
    assert m["cover_installs"] == {"0.5": 2, "0.8": 3, "0.9": 3, "0.95": 4}
    top = f["top"]
    assert [t["model"] for t in top] == ["XM-001", "XM-002", "XM-003", "XM-004", "XM-005"]
    assert top[0]["installs"] == 90 * 4 * 40 and top[0]["share"] == 0.4 and top[0]["paid_installs"] == 90 * 2 * 40
    assert top[1]["name"] == "(not set)"                       # a model without a marketing name still counts
    assert f["paid"]["paid_share"] == 0.5 and f["cell"]["cells"] == 10
    assert [c["c"] for c in f["cat"]] == ["mobile", "tablet"]
    assert f["osv"]["versions"] == 4 and f["osv"]["top"][0]["v"] == "14"


def test_window_and_cohort_shapes(monkeypatch):
    fake = Fake()
    rep = run(monkeypatch, fake)
    a = rep["apps"][KEY]
    F = date(2026, 10, 15) - timedelta(days=2 + dp.LATE)       # window_end_in: today − 2, then − LATE
    assert a["F"] == F.isoformat() and a["w0"] == (F - timedelta(days=89)).isoformat()
    assert a["x"] == (F - timedelta(days=dp.COH_AGE)).isoformat() and a["h0"] == "2026-01-01"
    assert a["reads"]["COH7"]["rows"] == dp.COH7_N * (dp.COH_AGE + 1) * 5
    assert a["reads"]["COHM"]["trunc"] is False


def test_other_lumping_is_measured_not_hidden(monkeypatch):
    rep = run(monkeypatch, Fake(lump=("XM-004", "XM-005")))
    a = rep["apps"][KEY]
    s = a["reads"]["MOD"]["s"]
    assert s["newUsers"]["other"] == 0.1 and s["totalAdRevenue"]["other"] == 0.1
    assert a["facts"]["tie_MOD"]["newUsers"] == 1.0              # Σ of all rows still ties: lumped, not lost
    assert a["facts"]["mod"]["models"] == 3
    assert a["facts"]["hist"]["other_rev"] == 0.1 and a["facts"]["hist"]["months"] == 10
    assert a["facts"]["tie_IDM"]["newUsers"]["all"] == 1.0 and a["facts"]["tie_IDM"]["newUsers"]["off2"] == 90
    assert rep["counts"]["kinds"]["MOD"]["other"] == 1 and rep["counts"]["kinds"]["TOT"]["other"] == 0


def test_a_refused_read_is_kept_as_its_class(monkeypatch):
    rep = run(monkeypatch, Fake(refuse=("COHM",)))
    a = rep["apps"][KEY]
    assert a["reads"]["COHM"] == dict(a["reads"]["COHM"], ok=False, err={"http": 400, "status": "INVALID_ARGUMENT"})
    assert a["reads"]["COH7"]["ok"] and "tie_COHM" not in a["facts"]
    assert rep["counts"]["kinds"]["COHM"]["refused"] == 1


def test_a_bug_in_the_facts_costs_the_facts_only(monkeypatch):
    monkeypatch.setattr(dp, "facts", lambda raw: [][1])
    rep = run(monkeypatch, Fake())
    a = rep["apps"][KEY]
    assert a["facts"] == {"bug": True, "err": {"type": "IndexError"}} and all(r["ok"] for r in a["reads"].values())


def test_public_log_is_counts_only(monkeypatch, capsys):
    rep = run(monkeypatch, Fake(lump=("XM-005",), refuse=("COH7",)))
    lines = dp.public_lines(rep["counts"])
    out = capsys.readouterr().out + "\n".join(lines)
    for s in SECRETS:
        assert s not in out
    for ln in lines:
        assert re.fullmatch(r"device probe: (\w+ n \d+ ok \d+ refused \d+ other \d+ thresholded \d+ sampled \d+|"
                            r"apps \d+, complete \d+, stopped \d+, calls \d+, \d+s)", ln), ln
    assert len(lines) == len(dp.KINDS) + 1


def test_options_clamp_and_inputs_win(monkeypatch):
    o = dp.options({"win": "1000", "apps": "A,b"}, {"DEVICE_MAX_CALLS": "9"})
    assert o["win"] == 365 and o["apps"] == {"a", "b"} and o["max_calls"] == 9
    assert dp.options({}, {})["win"] == dp.WIN
