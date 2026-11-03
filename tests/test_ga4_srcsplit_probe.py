"""GA4 revenue by source split probe (admob_iq.fetch.ga4_srcsplit_probe) — offline against a small fake GA4 (SYNTHETIC:
made-up countries, phone models and money): every read answers and ties to its truth and key by key, the groups' shares
come out of the channel rows, "(other)" lumping is flagged per key, a refused read is kept as refused while the others go
on, and the PUBLIC log stays counts-only."""
import re
from datetime import date, timedelta

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_srcsplit_probe as ss
from tests.test_ga4_device_probe import NOW, PID, RT, SECRETS, SID, TOK, unit

CC = ("XA", "XB")                                          # user-assigned ISO codes: never a real country
MODELS = (("XS-101", 30), ("XS-102", 20), ("XS-103", 10))   # (model, users an install day)
REV = 0.01                                                 # USD per user a day, ages 0 .. 30


def channel(age):
    """The install day is paid; later days rotate notification → organic → paid."""
    return ("Cross-network", "Mobile Push Notifications", "Direct")[age % 3] if age else "Cross-network"


class FakeGA:
    """Groups installed every day of 2026 to 13 Oct per country × model, active ages 0 .. 30, one session a user a day,
    the session's channel by age (channel). lump: models a read with BOTH the channel and the model answers as one
    "(other)" row; refuse: read kinds (dimension lists) answered 400."""

    def __init__(self, lump=(), refuse=()):
        self.lump, self.refuse, self.calls = set(lump), set(refuse), []
        f0 = date(2026, 1, 1)
        self.atoms = [{"fsd": f0 + timedelta(days=i), "countryId": c, "mobileDeviceModel": m, "n": n}
                      for i in range((date(2026, 10, 13) - f0).days + 1) for c in CC for m, n in MODELS]

    @staticmethod
    def _ok(expr, a):
        f = expr.get("filter")
        if f:
            v = {"platform": "Android", "streamId": SID}.get(f["fieldName"])
            if v is None:
                assert f["fieldName"] == "firstSessionDate", f
                v = a["fsd"].strftime("%Y%m%d")
            if "inListFilter" in f:
                return v in f["inListFilter"]["values"]
            return v == f["stringFilter"]["value"]
        return all(FakeGA._ok(e, a) for e in expr["andGroup"]["expressions"])

    def __call__(self, method, url, token, body=None, params=None):
        assert method == "POST" and token == TOK and url.endswith("properties/%s:runReport" % PID)
        dims = [x["name"] for x in body.get("dimensions") or []]
        mets = [x["name"] for x in body["metrics"]]
        self.calls.append(dims)
        if "+".join(dims) in self.refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: DETAIL-PRIVATE")
        s = date.fromisoformat(body["dateRanges"][0]["startDate"])
        t = date.fromisoformat(body["dateRanges"][0]["endDate"])
        lump = "sessionDefaultChannelGroup" in dims and "mobileDeviceModel" in dims
        agg = {}
        for a in self.atoms:
            if not self._ok(body["dimensionFilter"], a):
                continue
            for age in range(31):
                d = a["fsd"] + timedelta(days=age)
                if not s <= d <= t:
                    continue
                v = {"sessionDefaultChannelGroup": channel(age), "date": d.strftime("%Y%m%d"),
                     "firstSessionDate": a["fsd"].strftime("%Y%m%d")}
                key = tuple(v.get(k) or a[k] for k in dims)
                if lump and a["mobileDeviceModel"] in self.lump:
                    key = ("(other)",) * len(dims)
                e = agg.setdefault(key, dict.fromkeys(mets, 0))
                for m in mets:
                    e[m] += {"totalRevenue": REV * a["n"], "sessions": a["n"]}[m]
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
    return ss.run_probe([unit()], "cid", "sec", [("o", RT)], {"app_calls": 80}, now=NOW)


def test_reads_tie_whole_and_key_by_key(monkeypatch, capsys):
    rep = _run(monkeypatch, FakeGA())
    a = list(rep["apps"].values())[0]
    assert a["complete"] and a["F"] == "2026-10-10" and a["X"] == "2026-09-13"
    assert set(a["reads"]) == {k for k, *_ in ss.READS} and all(r["ok"] for r in a["reads"].values())
    for k, r in a["reads"].items():
        if k in ss.TRUTH:
            assert all(abs(v - 1.0) < 1e-9 for v in r["tie"].values()), (k, r["tie"])
        if k in ss.PAIRS:
            assert all(t["w2"] == 1.0 and t["off2"] == 0 for t in r["keys"].values()), (k, r["keys"])
    assert a["reads"]["CHF"]["keys"]["totalRevenue"]["keys"] == ss.DAYS
    f = a["facts"]
    assert abs(sum(f["app"]["r"]) - 1.0) < 1e-6 and f["app"]["r"][3] == 0
    day = dict(f["CHF"])["20260913"]                       # X: ages 0 .. 27 → paid 10, notification 9, organic 9 days
    assert day["r"] == [round(10 / 28, 4), round(9 / 28, 4), round(9 / 28, 4), 0]          # shares: 4 decimals
    assert {k for k, _ in f["CHC"]} == set(CC) and [k for k, _ in f["CHM"]] == [m for m, _ in MODELS]
    lines = ss.public_lines(rep["counts"])
    out = capsys.readouterr().out + "\n".join(lines)
    for s in SECRETS + list(CC) + [m for m, _ in MODELS] + ["Cross-network", "Direct"]:
        assert s not in out
    assert all(re.fullmatch(r"srcsplit probe: (\w+ n \d+ ok \d+ refused \d+ tie<0\.98 \d+ other \d+|apps \d+, "
                            r"complete \d+, calls \d+, \d+s)", ln) for ln in lines), lines


def test_other_lumping_keeps_the_tie_but_misses_key_by_key(monkeypatch):
    rep = _run(monkeypatch, FakeGA(lump=("XS-103",)))
    a = list(rep["apps"].values())[0]
    chm = a["reads"]["CHM"]
    assert abs(chm["tie"]["totalRevenue"] - 1.0) < 1e-9 and chm["s"]["totalRevenue"]["other"] > 0
    k = chm["keys"]["totalRevenue"]
    assert k["off2"] == 1 and k["w2"] == round(50 / 60, 4)            # XS-103 holds 10 of 60 users
    c = rep["counts"]["kinds"]
    assert c["CHM"]["other"] == 1 and c["M"]["other"] == 0 and c["CHC"]["other"] == 0


def test_a_refused_read_is_kept_and_the_others_go_on(monkeypatch):
    rep = _run(monkeypatch, FakeGA(refuse=("sessionDefaultChannelGroup+countryId+date",)))
    a = list(rep["apps"].values())[0]
    assert not a["reads"]["CHCD"]["ok"] and a["reads"]["CHCD"]["err"]["http"] == 400
    assert a["reads"]["XCHM"]["ok"] and a["complete"]
    assert rep["counts"]["kinds"]["CHCD"] == {"n": 1, "ok": 0, "refused": 1, "low": 0, "other": 0}
