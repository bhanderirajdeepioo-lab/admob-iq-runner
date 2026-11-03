"""One-off Google Ads TIME ZONE probe, run by .github/workflows/gads-tz-probe.yml: since 1 Nov 2026 the spend cache's
install-day ("Day") D0 moments are all at the guessed zone (google_ads.D0_NO_TZ), so no "By date" number was taken —
the roster's account time zones came back empty. This asks Google Ads, read-only, the ways an account's zone can be read:
  CC   the MCC roster WITH customer_client.time_zone (the build's query) — its rows or Google's own refusal
  CCN  the roster without it (the build's fallback)
  CUS  each client account's own `SELECT customer.time_zone FROM customer` (one call each, the first MAX_ACCOUNTS)
Output ga4/gads_tz_probe.json in the PRIVATE repo: per read ok / the HTTP error text, the accounts with a zone and the
zones (account ids kept there only). PUBLIC LOG: counts only."""
import os
import sys
import time
from collections import Counter

from admob_iq.fetch import gads_geo_probe as gp
from admob_iq.fetch import google_ads as gads
from admob_iq.fetch.ga4_d1d7_probe import _dump, write_private

OUT_PATH = "ga4/gads_tz_probe.json"
MAX_ACCOUNTS = 80
Q = ("SELECT customer_client.id, customer_client.currency_code, customer_client.descriptive_name, "
     "customer_client.manager%s FROM customer_client")


def run_probe(s, token, search=None):
    search = search or gads._search
    mcc = str(s["google_ads_login_customer_id"]).replace("-", "")
    dev = s["google_ads_dev_token"]
    rep = {"v": 1, "kind": "gads_tz_probe", "api": gads.API_VERSION, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        rows = search(mcc, mcc, dev, token, Q % ", customer_client.time_zone")
        cc = [r.get("customerClient") or {} for r in rows]
        kids = [c for c in cc if not c.get("manager")]
        rep["CC"] = {"ok": True, "accounts": len(kids), "with_tz": sum(1 for c in kids if c.get("timeZone")),
                     "zones": dict(Counter(str(c.get("timeZone")) for c in kids)),
                     "keys": sorted({k for c in kids for k in c})}
    except Exception as e:
        rep["CC"] = {"ok": False, "err": str(e)[:600]}
    ids = []
    try:
        rows = search(mcc, mcc, dev, token, Q % "")
        ids = [str((r.get("customerClient") or {}).get("id")) for r in rows if not (r.get("customerClient") or {}).get("manager")]
        rep["CCN"] = {"ok": True, "accounts": len(ids)}
    except Exception as e:
        rep["CCN"] = {"ok": False, "err": str(e)[:600]}
    cus = {}
    for cid in ids[:MAX_ACCOUNTS]:
        try:
            rows = search(cid, mcc, dev, token, "SELECT customer.id, customer.time_zone FROM customer")
            cus[cid] = {"ok": True, "tz": ((rows[0] if rows else {}).get("customer") or {}).get("timeZone")}
        except Exception as e:
            cus[cid] = {"ok": False, "err": str(e)[:300]}
    rep["CUS"] = cus
    rep["counts"] = {"cc_ok": bool(rep["CC"].get("ok")), "cc_with_tz": rep["CC"].get("with_tz", 0),
                     "accounts": len(ids), "cus_ok": sum(1 for v in cus.values() if v.get("ok")),
                     "cus_with_tz": sum(1 for v in cus.values() if v.get("tz"))}
    return rep


def main(env=None):
    env = os.environ if env is None else env
    s = gp.ads_settings(env)
    if not all(s.values()):
        sys.exit("Google Ads secrets missing")
    try:
        token = gads._access_token(s["client_id"], s["client_secret"], s["google_ads_refresh_token"])
    except Exception:
        print("gads tz probe: Google Ads sign-in failed", flush=True)
        sys.exit(1)
    rep = run_probe(s, token)
    c = rep["counts"]
    print("gads tz probe: roster with time zone %s (%d with a zone), accounts %d, per-account read ok %d (%d with a zone)"
          % ("ok" if c["cc_ok"] else "refused", c["cc_with_tz"], c["accounts"], c["cus_ok"], c["cus_with_tz"]), flush=True)
    if not write_private(OUT_PATH, _dump(rep), "gads tz probe"):
        sys.exit("private repo write failed")
    print("gads tz probe: report written", flush=True)


if __name__ == "__main__":
    main()
