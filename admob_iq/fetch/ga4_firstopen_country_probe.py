"""One-off probe for 🆕 First open BY COUNTRY, run by .github/workflows/ga4-firstopen-country-probe.yml (owner, 20 Oct
2026: "country wise bhi dekh saku esa kara do"). It measures, on the real properties, what a country-wise strict funnel
costs before anything is built:

GA4's funnel breakdown returns at most 15 values per call, so EVERY country is read in rounds: round 1 = the 15 biggest
countries, round 2 = the same funnel with those countries left out of step 1 (first_open), … until a round returns no
row. Nothing is cut: the sum over all rounds must equal the app's own total (checked here, per day).

Per app with a First open store (its screens and property come from data/ga4_firstopen/<key>.json.gz, read-only), for
a few days (a final day, one a month back, one near the edge of GA4's retention):
  * the total strict funnel first_open → Splash (≤ 10 min) → Home (≤ 60 min), as the First open fetch reads it;
  * the same funnel by countryId, in rounds as above;
  → countries, rounds (calls), tokens per call, seconds per call, GA4 sampling, and the coverage (sum ÷ total).

Writes ga4/firstopen_country_probe.json in the PRIVATE repo (never data/ or site/). This repo's Actions log is PUBLIC:
counts only; stderr is hidden by the workflow step.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from admob_iq import ga4_probe
from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_d1d7_probe as pr
from admob_iq.fetch import ga4_firstopen as gf
from admob_iq.fetch import ga4_uninstall as gu

OUT_PATH = "ga4/firstopen_country_probe.json"
DATA_DIR = "_private"
BUDGET_SEC = 22 * 60
DAYS_BACK = (3, 30, 58)               # property-tz days before today: final, a month back, near the retention edge
MAX_ROUNDS = 40                       # 600 countries: far above the ~250 GA4 knows; a guard, not a cut
DIM = "countryId"
RT = "RESERVED_TOTAL"                 # GA4's own total row in a funnel breakdown


def country_body(splash, home, day, exclude=(), dim=DIM):
    """The First open fetch's strict Home funnel for ONE day, broken down by country, with `exclude` left out of step 1."""
    b = gf.funnel_body(splash, home, day, day, dim)
    if exclude:
        b["funnel"]["steps"][0]["filterExpression"] = {"andGroup": {"expressions": [
            {"funnelEventFilter": {"eventName": "first_open"}},
            {"notExpression": {"funnelFieldFilter": {"fieldName": dim, "inListFilter": {"values": sorted(exclude)}}}}]}}
    return b


def by_country(ga, steps, day, clock=time.monotonic):
    """Every country of one day, in rounds → {"countries": {cc: [first_open, splash, home]}, "rounds", "calls", "tokens",
    "sec", "sample"}. A round with no row ends it."""
    out, seen, rounds, smp, t0, tok0, rts = {}, set(), 0, None, clock(), ga.tok, []
    while rounds < MAX_ROUNDS:
        j = ga.funnel(country_body(steps["splash"], steps["home"], day, seen))
        rounds += 1
        t = gf.parse_table(j)
        fo, sp, st = t.get("first_open") or {}, t.get("splash") or {}, t.get("step") or {}
        # GA4 adds a RESERVED_TOTAL row: the whole population of THIS round (every country not yet left out); after the
        # last named country it is what GA4 counted but named no country for (its privacy thresholds)
        rts.append([fo.pop(RT, 0), sp.pop(RT, 0), st.pop(RT, 0)])
        got = (set(fo) | set(sp) | set(st)) - seen
        s = gf.sampling(j)
        if s is not None:
            smp = s if smp is None else min(smp, s)
        if not got:
            break
        for c in got:
            out[c] = [fo.get(c, 0), sp.get(c, 0), st.get(c, 0)]
        seen |= got
    return {"countries": out, "rounds": rounds, "tokens": ga.tok - tok0, "sec": round(clock() - t0, 1), "sample": smp,
            "capped": rounds >= MAX_ROUNDS, "rt": rts}


def total(ga, steps, day):
    j = ga.funnel(gf.funnel_body(steps["splash"], steps["home"], day, day, "date"))
    t = gf.parse_table(j)
    pick = lambda k: sum(v for b, v in (t.get(k) or {}).items() if b != RT)
    return {"first_open": pick("first_open"), "splash": pick("splash"), "home": pick("step"), "sample": gf.sampling(j)}


def probe_app(store, token, prop, over, today_of=None, clock=time.monotonic):
    steps = store.get("steps") or {}
    res = {"app_id": store.get("app_id"), "steps_ok": bool(steps.get("splash") and steps.get("home")), "days": {}}
    if not res["steps_ok"] or not token:
        res["err"] = "no_steps" if token else "auth"
        return res
    tz = store.get("time_zone") or "UTC"
    today = (today_of or (lambda z: datetime.now(timezone.utc).astimezone(ZoneInfo(z)).date()))(tz)
    ga = gf.App(token, store["property_id"], store["stream_id"], prop, over=over, max_calls=10 ** 6)
    try:
        for back in DAYS_BACK:
            day = today - timedelta(days=back)
            tot = total(ga, steps, day)
            bc = by_country(ga, steps, day, clock)
            sums = [sum(v[i] for v in bc["countries"].values()) for i in range(3)]
            cov = {k: (round(sums[i] / tot[k], 4) if tot[k] else None) for i, k in enumerate(("first_open", "splash", "home"))}
            sizes = sorted((v[0] for v in bc["countries"].values()), reverse=True)
            res["days"][day.isoformat()] = dict(bc, back=back, total=tot, coverage=cov, n=len(bc["countries"]),
                                                top15_share=(round(sum(sizes[:15]) / sum(sizes), 4) if sum(sizes) else None),
                                                under10=sum(1 for x in sizes if x < 10))
        res["complete"] = True
    except gf.Stop as e:
        res["stopped"] = str(e)
    except Exception as e:
        res["err"] = pr._err(e)
    res.update(calls=ga.calls, tokens=ga.tok)
    return res


def counts(apps):
    a = list(apps.values())
    days = [d for x in a for d in (x.get("days") or {}).values()]
    return {"apps": len(a), "complete": sum(1 for x in a if x.get("complete")),
            "stopped": sum(1 for x in a if x.get("stopped")), "errors": sum(1 for x in a if x.get("err")),
            "days": len(days), "calls": sum(int(x.get("calls") or 0) for x in a),
            "tokens": sum(int(x.get("tokens") or 0) for x in a),
            "max_rounds": max([d["rounds"] for d in days], default=0),
            "full_cover": sum(1 for d in days if d.get("coverage", {}).get("first_open") == 1.0)}


def public_line(c):
    return ("firstopen country probe: apps %(apps)d, complete %(complete)d, stopped %(stopped)d, errors %(errors)d, "
            "app-days %(days)d, calls %(calls)d, tokens %(tokens)d, max rounds %(max_rounds)d, "
            "days fully covered %(full_cover)d" % c)


def main(env=None, clock=time.monotonic):
    env = os.environ if env is None else env
    cid = env.get("GA4_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
    sec = env.get("GA4_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
    tokens, _ = ga4_probe.owner_tokens(env)
    if not (cid and sec and tokens):
        sys.exit("GA4 client or refresh tokens missing")
    data_dir = os.path.join(env.get("FIRSTOPEN_DATA_DIR") or DATA_DIR, "data")
    routes = (gu.load_state(data_dir).get("routes") or {}).get("by_package") or {}
    d = os.path.join(data_dir, gf.DIR)
    stores = []
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        s = gf.load_store(os.path.join(d, fn)) if fn.endswith(".json.gz") else None
        if s and s.get("property_id") and s.get("stream_id"):
            stores.append(s)
    cap = pr._int(env.get("FIRSTOPEN_MAX_APPS"))
    if cap > 0:                                         # the biggest apps first: they decide the cost
        stores = sorted(stores, key=lambda s: -sum(int((v or {}).get("first_open") or 0)
                                                   for _, v in sorted((s.get("days") or {}).items())[-7:]))[:cap]
    print("firstopen country probe: %d app(s)" % len(stores), flush=True)
    t0, budget = clock(), pr._int(env.get("FIRSTOPEN_BUDGET_SEC")) or BUDGET_SEC
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
        print("firstopen country probe: apps %d/%d, %ds" % (i + 1, len(stores), int(clock() - t0)), flush=True)
        if over():
            break
    report = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "dim": DIM, "days_back": list(DAYS_BACK),
              "counts": counts(out), "apps": out}
    print(public_line(report["counts"]), flush=True)
    if not pr.write_private(OUT_PATH, pr._dump(report), "ga4 first-open country probe"):
        sys.exit("private repo write failed")
    print("firstopen country probe: report written", flush=True)


if __name__ == "__main__":
    main()
