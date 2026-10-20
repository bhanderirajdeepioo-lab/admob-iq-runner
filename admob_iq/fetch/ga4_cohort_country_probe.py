"""One-off probe for the Install value cohort table BY COUNTRY, run by .github/workflows/ga4-cohort-country-probe.yml
(owner, 20 Oct 2026: "USA select kru to date wise country ka aa jayega konsa din kaha pahocha", and no D365 limit:
"jitna purana app utna date"). Before anything is built it measures, on the real properties, what reading install day
× country × age costs and how much of it GA4 still names.

Per app with a Day-wise ROI store (data/ga4_cohort/<key>.json.gz: its property, stream, time zone, history start), for
three 30-day ACTIVITY blocks (the newest final one, one about a year back, the oldest the app has):
  early  dims [date, firstSessionDate(, countryId)], firstSessionDate in-list a − 30 … b  → ages 0 … 30
  late   dims [date, firstSessionDate(, countryId)], no in-list                         → every age (folded ≥ 31)
  total  dims [date]                                                                    → the block's ad revenue
each with and without countryId → rows, pages, seconds, GA4 tokens; ad revenue named by country vs the same read
without country (what GA4 gives "(other)" / "(not set)"), countries, (country, install day) pairs, and the entries a
store folded to (country, install day, 30-day age bucket, activity month) would hold.

Writes ga4/cohort_country_probe.json in the PRIVATE repo (never data/ or site/). This repo's Actions log is PUBLIC:
counts only; stderr is hidden by the workflow step.
"""
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_cohort as gco
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_uninstall as gu

OUT_PATH = "ga4/cohort_country_probe.json"
DATA_DIR = "_private"
BUDGET_SEC = 24 * 60
BLOCK = 30
DIM = "countryId"


def _iso8(s):
    s = str(s or "")
    return date(int(s[:4]), int(s[4:6]), int(s[6:])) if len(s) == 8 and s.isdigit() else None


def body(a, b, dims, rev_only=False):
    return {"dateRanges": [{"startDate": a.isoformat(), "endDate": b.isoformat()}], "dimensions": ga4._dim(*dims),
            "metrics": ga4._dim(*(("totalAdRevenue",) if rev_only else gco.METS)), "currencyCode": "USD",
            "keepEmptyRows": False}


def read(ga, a, b, dims, early, clock=time.monotonic):
    """One read → its measure: rows, pages, seconds, tokens, revenue (all / named / unnamed), countries, pairs."""
    t0, tok0, c0 = clock(), ga.tok, ga.calls
    extra = [ga4._in_list("firstSessionDate", gco.in_list(a, b))] if early else None
    rows = ga.report_all(body(a, b, dims, rev_only=not early), extra=extra, page_rows=gu.UNI_PAGE_ROWS)
    m = {"rows": len(rows), "calls": ga.calls - c0, "sec": round(clock() - t0, 1), "tokens": ga.tok - tok0,
         "truncated": bool(ga.truncated(rows)), "rev": 0.0, "named": 0.0, "unnamed_x": 0.0, "unnamed_cc": 0.0}
    cc_set, pairs, fold = set(), set(), set()
    for r in rows:
        v = float(r.get("totalAdRevenue") or 0)
        D, X = _iso8(r.get("date")), _iso8(r.get("firstSessionDate"))
        if D is None:
            continue
        if X is None:
            m["unnamed_x"] += v                        # GA4 "(other)" / "(not set)" install day
            continue
        L = (D - X).days
        if (early and not 0 <= L < gco.LAGS) or (not early and L < gco.LAGS):
            continue
        m["rev"] += v
        if DIM in dims:
            cc = str(r.get(DIM) or "")
            if not cc or cc in ga4.NOT_SET:
                m["unnamed_cc"] += v
                continue
            cc_set.add(cc)
            pairs.add((cc, X))
            if not early:
                fold.add((cc, X, (L - 1) // 30, D.strftime("%Y-%m")))
        m["named"] += v
    m.update(countries=len(cc_set), pairs=len(pairs), fold_entries=len(fold))
    for k in ("rev", "named", "unnamed_x", "unnamed_cc"):
        m[k] = round(m[k], 2)
    return m


def blocks(hs, today):
    newest = (today - timedelta(days=4 + BLOCK - 1), today - timedelta(days=4))
    out = {"newest": newest}
    yr = today - timedelta(days=365)
    if yr - timedelta(days=BLOCK - 1) >= hs + timedelta(days=gco.LAGS):
        out["year_back"] = (yr - timedelta(days=BLOCK - 1), yr)
    old = hs + timedelta(days=gco.LAGS)
    if old + timedelta(days=BLOCK - 1) < (out.get("year_back") or newest)[0]:
        out["oldest"] = (old, old + timedelta(days=BLOCK - 1))
    return out


def probe_app(store, token, prop, over, today_of=None, clock=time.monotonic):
    res = {"app_id": store.get("app_id"), "hs": store.get("hs"), "blocks": {}}
    if not token:
        res["err"] = "auth"
        return res
    tz = store.get("time_zone") or "UTC"
    today = (today_of or (lambda z: datetime.now(timezone.utc).astimezone(ZoneInfo(z)).date()))(tz)
    hs = gu._d(store["hs"])
    res["age_days"] = (today - hs).days
    ga = gf.App(token, store["property_id"], store["stream_id"], prop, over=over, max_calls=10 ** 6)
    try:
        for name, (a, b) in blocks(hs, today).items():
            r = {"a": a.isoformat(), "b": b.isoformat()}
            r["total"] = read(ga, a, b, ("date",), early=False)
            r["early_all"] = read(ga, a, b, ("date", "firstSessionDate"), early=True)
            r["early_cc"] = read(ga, a, b, ("date", "firstSessionDate", DIM), early=True)
            r["late_all"] = read(ga, a, b, ("date", "firstSessionDate"), early=False)
            r["late_cc"] = read(ga, a, b, ("date", "firstSessionDate", DIM), early=False)
            res["blocks"][name] = r
        res["complete"] = True
    except gf.Stop as e:
        res["stopped"] = str(e)
    except Exception as e:
        res["err"] = pr._err(e)
    res.update(calls=ga.calls, tokens=ga.tok)
    return res


def counts(apps):
    a = list(apps.values())
    bl = [b for x in a for b in (x.get("blocks") or {}).values()]
    return {"apps": len(a), "complete": sum(1 for x in a if x.get("complete")),
            "stopped": sum(1 for x in a if x.get("stopped")), "errors": sum(1 for x in a if x.get("err")),
            "blocks": len(bl), "calls": sum(int(x.get("calls") or 0) for x in a),
            "tokens": sum(int(x.get("tokens") or 0) for x in a),
            "truncated": sum(1 for b in bl for k in ("early_cc", "late_cc") if (b.get(k) or {}).get("truncated"))}


def public_line(c):
    return ("cohort country probe: apps %(apps)d, complete %(complete)d, stopped %(stopped)d, errors %(errors)d, "
            "blocks %(blocks)d, calls %(calls)d, tokens %(tokens)d, truncated reads %(truncated)d" % c)


def main(env=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    data_dir = os.path.join(env.get("COHORT_DATA_DIR") or DATA_DIR, "data")
    routes = (gu.load_state(data_dir).get("routes") or {}).get("by_package") or {}
    d = os.path.join(data_dir, gco.DIR)
    stores = []
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not fn.endswith(".json.gz") or fn.endswith(".old.json.gz"):
            continue
        s = gu.load_store(os.path.join(d, fn))
        if isinstance(s, dict) and s.get("property_id") and s.get("stream_id") and s.get("hs") and s.get("app_id"):
            s["_n"] = len(s.get("x") or {})
            stores.append(s)
    cap = pr._int(env.get("COHORT_MAX_APPS"))
    stores.sort(key=lambda s: (gu._d(s["hs"]), -s["_n"]))      # the oldest apps first: they decide the history cost
    if cap > 0:
        stores = stores[:cap]
    print("cohort country probe: %d app(s)" % len(stores), flush=True)
    t0, budget = clock(), pr._int(env.get("COHORT_BUDGET_SEC")) or BUDGET_SEC
    over = lambda: "budget" if clock() - t0 >= budget else None
    rt, access, props, out = dict(tokens), {}, {}, {}
    for i, s in enumerate(stores):
        owner = (routes.get(s.get("package")) or {}).get("owner")
        if owner not in access:
            try:
                access[owner] = ga4.access_token(cid, sec, rt[owner]) if owner in rt else None
            except Exception:
                access[owner] = None
        prop = props.setdefault(s["property_id"], {"quota": None, "stop": None})
        out[gu.file_key(s["app_id"])] = probe_app(s, access.get(owner), prop, over, clock=clock)
        print("cohort country probe: apps %d/%d, %ds" % (i + 1, len(stores), int(clock() - t0)), flush=True)
        if over():
            break
    report = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "block_days": BLOCK, "counts": counts(out),
              "apps": out}
    print(public_line(report["counts"]), flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 cohort country probe"):
        sys.exit("private repo write failed")
    print("cohort country probe: report written", flush=True)


if __name__ == "__main__":
    main()
