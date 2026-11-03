"""GA4 new vs returning probe (admob_iq.fetch.ga4_nvr_probe) — offline against a small fake GA4 (SYNTHETIC: made-up
countries, ad formats, ad units and money): every read answers and ties to the read without the split, the two eCPMs
come out of the "new" / "returning" rows, a refused read is kept as refused while the others go on, and the PUBLIC log
stays counts-only."""
import re
from datetime import date, timedelta

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_nvr_probe as nv
from tests.test_ga4_device_probe import NOW, PID, RT, SECRETS, TOK, unit

CC = ("XA", "XB")
UNITS = (("App open", "unit-open-PRIVATE"), ("Interstitial", "unit-inter-PRIVATE"), ("Banner", "unit-banner-PRIVATE"))
ECPM = {"new": 1.0, "returning": 2.0}                      # USD per 1000 impressions
IMPS = 5                                                   # impressions per user a day


class FakeGA:
    """Groups of 10 users installed every day of 2026 to 13 Oct, per country × ad unit, active ages 0 .. 30: age 0 is
    their first session ("new"), every later day "returning"; refuse: read kinds (dimension lists) answered 400."""

    def __init__(self, refuse=()):
        self.refuse, self.calls = set(refuse), []
        f0 = date(2026, 1, 1)
        self.atoms = [{"fsd": f0 + timedelta(days=i), "countryId": c, "adFormat": fm, "adUnitName": un, "n": 10}
                      for i in range((date(2026, 10, 13) - f0).days + 1) for c in CC for fm, un in UNITS]

    def __call__(self, method, url, token, body=None, params=None):
        assert method == "POST" and token == TOK and url.endswith("properties/%s:runReport" % PID)
        dims = [x["name"] for x in body.get("dimensions") or []]
        mets = [x["name"] for x in body["metrics"]]
        self.calls.append(dims)
        if "+".join(dims) in self.refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: DETAIL-PRIVATE")
        s = date.fromisoformat(body["dateRanges"][0]["startDate"])
        t = date.fromisoformat(body["dateRanges"][0]["endDate"])
        agg = {}
        for a in self.atoms:
            for age in range(31):
                d = a["fsd"] + timedelta(days=age)
                if not s <= d <= t:
                    continue
                nvr = "new" if age == 0 else "returning"
                v = {"newVsReturning": nvr, "date": d.strftime("%Y%m%d")}
                key = tuple(v.get(k) or a[k] for k in dims)
                e = agg.setdefault(key, dict.fromkeys(mets, 0))
                n = a["n"]
                for m in mets:
                    e[m] += {"newUsers": n if age == 0 else 0, "activeUsers": n, "sessions": n,
                             "publisherAdImpressions": IMPS * n, "eventCount": IMPS * n,
                                 "totalAdRevenue": IMPS * n * ECPM[nvr] / 1000}[m]
        rows = [{"dimensionValues": [{"value": v} for v in k], "metricValues": [{"value": str(e[m])} for m in mets]}
                for k, e in sorted(agg.items())]
        off, lim = body.get("offset", 0), body.get("limit", 10000)
        return {"dimensionHeaders": [{"name": x} for x in dims], "metricHeaders": [{"name": x} for x in mets],
                "rows": rows[off:off + lim], "rowCount": len(rows), "metadata": {"currencyCode": "USD"},
                "propertyQuota": {"tokensPerDay": {"consumed": 1, "remaining": 199000}}}


def _run(monkeypatch, fake):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    return nv.run_probe([unit()], "cid", "sec", [("o", RT)], {"app_calls": 50}, now=NOW)


def test_reads_tie_and_the_two_ecpms(monkeypatch, capsys):
    rep = _run(monkeypatch, FakeGA())
    a = list(rep["apps"].values())[0]
    assert a["complete"] and a["F"] == "2026-10-10" and a["from"] == "2026-09-13"
    assert set(a["reads"]) == {"T", "NR", "NRD", "NRC", "NRF", "NRU"} and all(r["ok"] for r in a["reads"].values())
    for k, r in a["reads"].items():
        if k != "T":
            assert all(abs(v - 1.0) < 1e-9 for v in r["tie"].values()), (k, r["tie"])
    f = a["facts"]
    assert f["new"]["ecpm"] == 1.0 and f["returning"]["ecpm"] == 2.0
    assert f["new"]["users"] == 28 * len(CC) * len(UNITS) * 10                  # one first session a user, 28 days
    assert len(a["reads"]["NRD"]["data"]) == 2 * 28 and len(a["reads"]["NRC"]["data"]) == 2 * len(CC)
    assert {row[1] for row in a["reads"]["NRF"]["data"]} == {fm for fm, _ in UNITS}
    lines = nv.public_lines(rep["counts"])
    out = capsys.readouterr().out + "\n".join(lines)
    for s in SECRETS + ["unit-open", "XA", "XB"]:
        assert s not in out
    assert all(re.fullmatch(r"nvr probe: (\w+ n \d+ ok \d+ refused \d+ tie<0\.98 \d+ other \d+|apps \d+, complete \d+, "
                            r"calls \d+, \d+s)", ln) for ln in lines), lines


def test_a_refused_read_is_kept_and_the_others_go_on(monkeypatch):
    rep = _run(monkeypatch, FakeGA(refuse=("newVsReturning+adFormat",)))
    a = list(rep["apps"].values())[0]
    assert not a["reads"]["NRF"]["ok"] and a["reads"]["NRF"]["err"]["http"] == 400
    assert a["reads"]["NRU"]["ok"] and a["complete"]
    assert rep["counts"]["kinds"]["NRF"] == {"n": 1, "ok": 0, "refused": 1, "low": 0, "other": 0}
