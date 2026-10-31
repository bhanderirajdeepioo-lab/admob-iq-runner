"""GA4 notification / organic / paid revenue probe (admob_iq.fetch.ga4_notif_probe) — offline, against a fake GA4 Data API
(ga4._call mocked), SYNTHETIC data only: every request shape answers, the month / day ties hold, the push share, the push
sessions' sources, the notification events, a refused read kept as its HTTP class, and a counts-only PUBLIC log."""

import re
from datetime import date, datetime, timedelta, timezone

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_notif_probe as npb
from admob_iq.fetch import ga4_uninstall as gu

NOW = datetime(2026, 10, 15, 6, 0, tzinfo=timezone.utc)
RT, TOK, PID, SID = "rt-PRIVATE-a", "tok-PRIVATE-a", "100200300", "9000000001"
AID = "ca-app-pub-0000000000000000~11"
KEY = gu.file_key(AID)
CAMP = "555000111"
PUSH = npb.PUSH
# (first-user channel, session channel, source, medium, campaign name, Google Ads campaign id, users a day, revenue a day)
ATOMS = (("Cross-network", "Cross-network", "google", "cpc", "(not set)", CAMP, 100, 1.0),
         ("Organic Search", "Organic Search", "google-play", "organic", "(organic)", "(not set)", 20, 0.2),
         ("Cross-network", PUSH, "firebase", "notification", "Msg A", CAMP, 5, 0.05),
         ("Direct", PUSH, "firebase", "notification", "Msg B", "(not set)", 2, 0.02))
SECRETS = [RT, TOK, PID, SID, AID, KEY, CAMP, "PRIVATE", "Cross-network", "Organic", PUSH, "firebase", "Msg A",
           "notification_open", "screen_view"]
START = date(2026, 3, 1)


def unit():
    return {"key": KEY, "app_id": AID, "app_ids": [AID], "property_id": PID, "stream_id": SID, "tz": "UTC",
            "owner": "o", "history_start": START.isoformat()}


class Fake:
    def __init__(self, refuse=()):
        self.refuse = set(refuse)

    @staticmethod
    def _ok(expr, a):
        f = expr.get("filter")
        if f:
            v = {"platform": "Android", "streamId": SID}.get(f["fieldName"], a.get(f["fieldName"]))
            if "inListFilter" in f:
                return v in f["inListFilter"]["values"]
            sf = f["stringFilter"]
            if sf.get("matchType") == "FULL_REGEXP":
                return re.fullmatch(sf["value"], v or "", re.I) is not None
            return v == sf["value"]
        return all(Fake._ok(e, a) for e in expr["andGroup"]["expressions"])

    def __call__(self, method, url, token, body=None, params=None):
        assert method == "POST" and token == TOK and url.endswith("properties/%s:runReport" % PID)
        dims = [x["name"] for x in body.get("dimensions") or []]
        mets = [x["name"] for x in body["metrics"]]
        if "+".join(dims) in self.refuse:
            raise RuntimeError("HTTP 400: INVALID_ARGUMENT: DETAIL-PRIVATE")
        rg = body["dateRanges"][0]
        s, t = date.fromisoformat(rg["startDate"]), date.fromisoformat(rg["endDate"])
        agg = {}
        d = max(s, START)
        while d <= t:
            for fu, se, src, med, cn, camp, n, rev in ATOMS:
                base = {npb.FU: fu, npb.SE: se, "sessionSource": src, "sessionMedium": med, "sessionCampaignName": cn,
                        npb.CAMP: camp, "date": d.strftime("%Y%m%d"), "yearMonth": d.strftime("%Y%m")}
                evs = [("screen_view", 3 * n), ("ad_impression", n)] + ([("notification_open", n)] if se == PUSH else [])
                for ev, cnt in (evs if "eventName" in dims else [(None, 0)]):
                    a = dict(base, eventName=ev)
                    if not self._ok(body["dimensionFilter"], a):
                        continue
                    e = agg.setdefault(tuple(a[k] for k in dims), dict.fromkeys(mets, 0))
                    for m in mets:
                        e[m] += {"newUsers": n // 10, "activeUsers": n, "sessions": 2 * n, "totalAdRevenue": rev,
                                 "totalRevenue": rev, "eventCount": cnt, "totalUsers": n}[m]
            d += timedelta(days=1)
        rows = [{"dimensionValues": [{"value": v} for v in k], "metricValues": [{"value": str(e[m])} for m in mets]}
                for k, e in sorted(agg.items())]
        off, lim = body.get("offset", 0), body.get("limit", 10000)
        return {"dimensionHeaders": [{"name": x} for x in dims], "metricHeaders": [{"name": x} for x in mets],
                "rows": rows[off:off + lim], "rowCount": len(rows), "metadata": {"currencyCode": "USD"},
                "propertyQuota": {"tokensPerDay": {"consumed": 1, "remaining": 199000}}}


def run(monkeypatch, fake):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    return npb.run_probe([unit()], "cid", "sec", [("o", RT)], {}, now=NOW, tick=0)


def test_every_read_answers_and_ties_hold(monkeypatch):
    rep = run(monkeypatch, Fake())
    a = rep["apps"][KEY]
    assert a["complete"] and set(a["reads"]) == set(npb.KINDS) and all(r["ok"] for r in a["reads"].values())
    f = a["facts"]
    for k in ("FUM", "SEM", "XM"):
        assert f["tie_" + k]["totalAdRevenue"]["all"] == 1.0 and f["tie_" + k]["totalAdRevenue"]["off2"] == 0, k
    assert all(f["tie_DAY"][m]["all"] == 1.0 for m in npb.DMETS)
    assert f["push_rev_share"] == round(0.07 / 1.27, 4)
    assert f["push_months"][0] == "202603" and f["push_months"][-1] == "202610"
    # the push sessions' sources: only firebase / notification rows, both messages
    assert sorted(r[2] for r in f["t_SRCN"]) == ["Msg A", "Msg B"] and {tuple(r[:2]) for r in f["t_SRCN"]} == {
        ("firebase", "notification")}
    # paid users only: their first-user channel is Cross-network
    assert {r[1] for r in f["t_PAIDM"]} == {"Cross-network"}
    assert f["notif_like"] == ["notification_open"] and {r[1] for r in f["t_EVM"]} == {"notification_open"}
    assert f["events_n"] == 3 and f["events"][0][0] == "screen_view"
    assert a["h0"] == START.isoformat() and a["r0"] == (date.fromisoformat(a["F"]) - timedelta(days=89)).isoformat()


def test_a_refused_read_is_kept_as_its_class(monkeypatch):
    rep = run(monkeypatch, Fake(refuse=("yearMonth+%s+%s" % (npb.FU, npb.SE),)))
    a = rep["apps"][KEY]
    assert a["reads"]["XM"]["ok"] is False and a["reads"]["XM"]["err"] == {"http": 400, "status": "INVALID_ARGUMENT"}
    assert "tie_XM" not in a["facts"] and a["facts"]["tie_SEM"]["totalAdRevenue"]["all"] == 1.0
    assert rep["counts"]["kinds"]["XM"]["refused"] == 1


def test_public_log_is_counts_only(monkeypatch, capsys):
    rep = run(monkeypatch, Fake())
    lines = npb.public_lines(rep["counts"])
    out = capsys.readouterr().out + "\n".join(lines)
    for s in SECRETS:
        assert s not in out, s
    for ln in lines[:-1]:
        assert re.fullmatch(r"notif probe: \w+ n \d+ ok \d+ refused \d+ other \d+ thresholded \d+ sampled \d+", ln), ln
    assert re.fullmatch(r"notif probe: apps 1, complete 1, stopped 0, apps with push sessions 1, with notification "
                        r"events 1, calls \d+, \d+s", lines[-1]), lines[-1]
