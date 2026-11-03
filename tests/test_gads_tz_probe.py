"""Google Ads time zone probe (admob_iq.fetch.gads_tz_probe) — offline with a fake search (SYNTHETIC ids and zones):
the roster with the zone, a refused zone field kept as Google's error, the per-account reads, counts only."""
from admob_iq.fetch import gads_tz_probe as tp

S = {"google_ads_login_customer_id": "111-000-0000", "google_ads_dev_token": "dev-PRIVATE"}


def fake(refuse_tz=False):
    def search(cid, mcc, dev, tok, q):
        if "customer_client.time_zone" in q:
            if refuse_tz:
                raise RuntimeError("HTTP 400: UNRECOGNIZED_FIELD customer_client.time_zone")
            return [{"customerClient": {"id": "201", "timeZone": "Asia/Calcutta"}}, {"customerClient": {"id": "202"}},
                    {"customerClient": {"id": "900", "manager": True}}]
        if "FROM customer_client" in q:
            return [{"customerClient": {"id": "201"}}, {"customerClient": {"id": "202"}}]
        return [{"customer": {"id": cid, "timeZone": "Asia/Calcutta" if cid == "201" else "America/New_York"}}]
    return search


def test_counts_and_a_refused_zone_field():
    r = tp.run_probe(S, "tok", search=fake())
    assert r["CC"]["ok"] and r["CC"]["accounts"] == 2 and r["CC"]["with_tz"] == 1
    assert r["counts"] == {"cc_ok": True, "cc_with_tz": 1, "accounts": 2, "cus_ok": 2, "cus_with_tz": 2}
    r2 = tp.run_probe(S, "tok", search=fake(refuse_tz=True))
    assert not r2["CC"]["ok"] and "UNRECOGNIZED_FIELD" in r2["CC"]["err"] and r2["counts"]["cus_with_tz"] == 2
