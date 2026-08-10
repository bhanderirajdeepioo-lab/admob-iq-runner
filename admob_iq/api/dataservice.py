"""build_dashboard(): computes EVERY dashboard screen's payload using the real
engine over a labeled demo dataset. This is the single contract the API serves
and the frontend renders. In production, swap `_demo_dataset()` for repo queries.
"""

from admob_iq.engine import metrics, trend, health, deduction, recommend, rootcause, mediation, compliance
from admob_iq.alerting import rules

PEER_ECPM = {"banner": 2.2, "native": 3.2, "interstitial": 8.0, "rewarded": 14.0, "app_open": 5.0}


def _lin(a, b, n=30):
    return [round(a + (b - a) * i / (n - 1), 2) for i in range(n)]


def _demo_dataset():
    """Labeled demo placements with realistic daily trajectories + latest-day facts.
    (In production this comes from network_daily / earnings_snapshots.)"""
    return [
        dict(id="ca~home_banner", name="Home_Feed_Banner", app="Puzzle Blast",
             account="Games Studio", fmt="banner", country="US",
             rev=_lin(62, 47), ivt=False,
             latest=dict(req=42000, matched=38640, impr=37094, clicks=260, earn=70_478_600),
             prior=dict(revenue=[62, 60, 58, 57, 55, 54, 52], ctr=[0.007] * 7,
                        requests=[42000] * 7, match_rate=[0.92] * 7),
             ded=[100.0, 96.0, 93.0, 91.0], native_ecpm=5.8, screen="feed", tier=1),
        dict(id="ca~level_int", name="LevelEnd_Interstitial", app="Puzzle Blast",
             account="Games Studio", fmt="interstitial", country="US",
             rev=_lin(110, 132), ivt=False,
             latest=dict(req=18000, matched=17460, impr=16762, clicks=503, earn=137_448_400),
             prior=dict(revenue=[110, 112, 115, 118, 120, 121, 124], ctr=[0.03] * 7,
                        requests=[18000] * 7, match_rate=[0.97] * 7),
             ded=[100.0, 99.0, 98.0, 98.0], native_ecpm=None, screen="game", tier=1),
        dict(id="ca~reward", name="Reward_Video", app="Word Master",
             account="Games Studio", fmt="rewarded", country="US",
             rev=_lin(100, 118), ivt=False,
             latest=dict(req=9000, matched=8550, impr=8208, clicks=574, earn=119_836_800),
             prior=dict(revenue=[100, 101, 103, 104, 106, 108, 110],
                        ecpm=[12.4, 12.5, 12.3, 12.6, 12.4, 12.5, 12.4],
                        requests=[9000] * 7, match_rate=[0.95] * 7),
             ded=[100.0, 99.0, 98.0, 98.0], native_ecpm=None, screen="game", tier=1,
             ecpm_now=14.6),
        dict(id="ca~appopen", name="AppOpen_Splash", app="Photo Editor Pro",
             account="Utility Apps", fmt="app_open", country="US",
             rev=_lin(80, 79), ivt=True,
             latest=dict(req=20000, matched=17800, impr=17088, clicks=718, earn=87_148_800),
             prior=dict(revenue=[80] * 7, ctr=[0.008] * 7,
                        requests=[20000] * 7, match_rate=[0.89] * 7),
             ded=[100.0, 96.0, 94.0, 93.0], native_ecpm=None, screen="other", tier=1,
             ctr_now=0.042),
        dict(id="ca~bottom_banner", name="Bottom_Banner", app="Photo Editor Pro",
             account="Utility Apps", fmt="banner", country="ID",
             rev=_lin(52, 4), ivt=True,
             latest=dict(req=14000, matched=8540, impr=8199, clicks=246, earn=1_803_780),
             prior=dict(revenue=[52, 50, 47, 44, 40, 36, 30],
                        requests=[14000, 13800, 14200, 13900, 14100, 13950, 14050],
                        match_rate=[0.61] * 7),
             ded=[100.0, 90.0, 84.0, 80.0], native_ecpm=None, screen="feed", tier=3,
             requests_now=0),
        dict(id="ca~coin_reward", name="Coin_Reward", app="Word Master",
             account="Games Studio", fmt="rewarded", country="IN",
             rev=_lin(40, 55), ivt=False,
             latest=dict(req=12000, matched=10680, impr=10253, clicks=615, earn=51_265_000),
             prior=dict(revenue=[40, 42, 45, 47, 50, 52, 54],
                        match_rate=[0.61, 0.62, 0.60, 0.63, 0.61, 0.60, 0.62],
                        requests=[12000] * 7),
             ded=[100.0, 99.0, 98.0, 98.0], native_ecpm=None, screen="game", tier=3,
             match_now=0.89),
    ]


def _placement_view(p, dates=None):
    L = p["latest"]
    ec = p.get("ecpm_now") or metrics.ecpm(L["earn"], L["impr"])
    mr = p.get("match_now") or metrics.match_rate(L["req"], L["matched"])
    sr = metrics.show_rate(L["matched"], L["impr"])
    ct = p.get("ctr_now") or metrics.ctr(L["impr"], L["clicks"])
    slope_norm = trend.slope(p["rev"]) / (sum(p["rev"]) / len(p["rev"]))
    hs = health.health_score(revenue_slope_norm=slope_norm, match_rate=mr, ecpm=ec,
                             peer_ecpm=PEER_ECPM[p["fmt"]], show_rate=sr, has_ivt_flag=p["ivt"])
    ded_snaps = [(str(i), v) for i, v in enumerate(p["ded"])]
    # synthetic per-day raw counts so the demo also drives the time-filter table.
    # Each day's counts scale with that day's revenue vs the latest day.
    rev = p["rev"]; base = rev[-1] or 1
    dates = dates or [str(i) for i in range(len(rev))]
    daily = []
    for i, rv in enumerate(rev):
        f = (rv / base) if base else 1
        daily.append([dates[i], int(round(rv * metrics.MICROS)),
                      int(round(L["impr"] * f)), int(round(L["req"] * f)),
                      int(round(L["matched"] * f)), int(round(L["clicks"] * f))])
    return dict(id=p["id"], name=p["name"], app=p["app"], account=p["account"],
                format=p["fmt"], country=p["country"], ecpm=round(ec, 2), match=round(mr, 3),
                ctr=round(ct, 4), show=round(sr, 3), health=hs, band=health.band(hs),
                verdict=trend.verdict(p["rev"]), change_pct=round(trend.pct_change_window(p["rev"], 9), 3),
                revenue=round(metrics.micros_to_currency(L["earn"]), 2),
                deduction_pct=round(deduction.deduction_pct(ded_snaps), 3),
                trend=p["rev"][-14:], daily=daily)


def _alerts(dataset):
    counts = {"improving": 0, "critical": 0, "warning": 0}
    items = []

    def emit(metric, current, prior, p, geo):
        sig = rules.evaluate(metric, current, prior)
        if not sig.is_alert:
            return
        key = "improving" if sig.severity == "good" else sig.severity
        counts[key] = counts.get(key, 0) + 1
        items.append(dict(severity=sig.severity, kind=sig.kind, metric=metric,
                          message=sig.message, place=p["name"], app=p["app"],
                          country=geo, current=round(current, 4)))
    for p in dataset:
        pr = p["prior"]
        if "requests" in pr and p.get("requests_now") is not None:
            emit("requests", p["requests_now"], pr["requests"], p, f'{p["country"]} (localized)')
        if "revenue" in pr and p["name"] == "Home_Feed_Banner":
            emit("revenue", 20, pr["revenue"], p, p["country"])
        if "ctr" in pr and p.get("ctr_now"):
            emit("ctr", p["ctr_now"], pr["ctr"], p, f'{p["country"]} (localized)')
        if "ecpm" in pr and p.get("ecpm_now"):
            emit("ecpm", p["ecpm_now"], pr["ecpm"], p, p["country"])
        if p.get("match_now"):
            emit("match_rate", p["match_now"], pr["match_rate"], p, p["country"])
    order = {"good": 0, "critical": 1, "warning": 2, "watch": 3}
    items.sort(key=lambda a: order.get(a["severity"], 9))
    return {"counts": counts, "items": items}


def build_dashboard():
    import datetime as _dt
    dataset = _demo_dataset()
    # deterministic demo date axis ending at a fixed anchor (keeps tests stable)
    N0 = len(dataset[0]["rev"])
    _anchor = _dt.date(2025, 1, 30)
    demo_dates = [str(_anchor - _dt.timedelta(days=N0 - 1 - i)) for i in range(N0)]
    pv = [_placement_view(p, demo_dates) for p in dataset]

    total_rev = sum(x["revenue"] for x in pv)
    tot_impr = sum(p["latest"]["impr"] for p in dataset)
    tot_earn = sum(p["latest"]["earn"] for p in dataset)
    tot_req = sum(p["latest"]["req"] for p in dataset)
    tot_match = sum(p["latest"]["matched"] for p in dataset)

    # apps rollup
    apps = {}
    for x in pv:
        a = apps.setdefault(x["app"], dict(name=x["app"], account=x["account"],
                                           placements=0, revenue=0.0, healths=[], declining=0, at_risk=0))
        a["placements"] += 1
        a["revenue"] += x["revenue"]
        a["healths"].append(x["health"])
        if x["verdict"] == "declining":
            a["declining"] += 1
        if x["band"] == "risk":
            a["at_risk"] += 1
    apps_out = []
    for a in apps.values():
        hs = a.pop("healths")
        a["avg_health"] = round(sum(hs) / len(hs))
        a["revenue"] = round(a["revenue"], 2)
        apps_out.append(a)

    inc, dec, steady = trend.split_movers([dict(name=x["name"], app=x["app"],
                                                change_pct=x["change_pct"]) for x in pv])

    # deductions
    ded_rows = [dict(place=x["name"], app=x["app"], geo=x["country"], pct=x["deduction_pct"],
                     flag="ivt" if x["deduction_pct"] >= 0.15 else ("watch" if x["deduction_pct"] >= 0.05 else "normal"))
                for x in pv]
    ded_rows.sort(key=lambda r: r["pct"], reverse=True)

    # mediation
    med_rows = [dict(ad_source="AppLovin", type="bidding", fill=0.88, ecpm=4.10, revenue=22, latency_s=0.6),
                dict(ad_source="AdMob Network", type="bidding", fill=0.90, ecpm=3.20, revenue=34, latency_s=0.0),
                dict(ad_source="Meta Audience", type="bidding", fill=0.85, ecpm=3.80, revenue=16, latency_s=0.7),
                dict(ad_source="Unity Ads", type="both", fill=0.82, ecpm=3.10, revenue=12, latency_s=0.9),
                dict(ad_source="Mintegral", type="bidding", fill=0.79, ecpm=2.40, revenue=9, latency_s=1.1),
                dict(ad_source="ironSource", type="waterfall", fill=0.60, ecpm=1.90, revenue=7, latency_s=1.4)]

    # recommendations (+ uplift)
    recs = []
    hb = dataset[0]  # Home_Feed_Banner
    for r in recommend.recommend(dict(format="banner", screen_type="feed", tier=1,
                                      match_rate=0.92, ecpm=1.9, native_ecpm=5.8, has_bidding=True)):
        up = recommend.estimate_uplift(ecpm_old=1.9, ecpm_new=5.8, impr_per_dau_old=3,
                                       impr_per_dau_new=3, dau=5000) if "Native" in r["action"] else 0
        recs.append(dict(action=r["action"], reason=r["reason"], confidence=r["confidence"],
                         ab=r["ab"], uplift=round(up), place="Home_Feed_Banner (US)"))
    recs.append(dict(action="Enable bidding networks", reason="+10-30% typical",
                     confidence="high", ab=True, uplift=260, place="portfolio"))
    total_uplift = sum(r["uplift"] for r in recs)

    # root cause for the declining banner
    cause = rootcause.classify(ecpm_change=-0.15, match_change=-0.01, yoy_down=False)

    # account health
    ivt_flags = sum(1 for a in _alerts(dataset)["items"] if a["kind"] == "spike") \
        + sum(1 for x in pv if x["deduction_pct"] >= 0.15)
    health_summary = compliance.account_health(ivt_flags=ivt_flags, consent_gaps=2,
                                               app_ads_txt_ok=True, tcf_current=False)

    # --- extra data for full wireframe parity ---
    N = len(dataset[0]["rev"])
    revenue_trend = [round(sum(p["rev"][i] for p in dataset), 2) for i in range(max(0, N - 14), N)]
    ecpm_now = round(metrics.ecpm(tot_earn, tot_impr), 2)
    match_now = round(metrics.match_rate(tot_req, tot_match), 3)
    arp = round(metrics.arpdau(ecpm_now, 3), 3)

    def _kp(mult, dr):
        return {"revenue": round(total_rev * mult, 2), "ecpm": round(ecpm_now * (1 + dr), 2),
                "match_rate": match_now, "arpdau": arp}
    kpis_by_range = {"today": _kp(1.0, 0.04), "yesterday": _kp(0.96, 0.0),
                     "7d": _kp(6.9, 0.0), "30d": _kp(28.4, -0.02)}

    # rich per-country view (group placements by primary country)
    cmap = {}
    for x in pv:
        c = cmap.setdefault(x["country"], {"country": x["country"], "rev": 0.0, "ec": [], "mr": [], "n": 0})
        c["rev"] += x["revenue"]; c["ec"].append(x["ecpm"]); c["mr"].append(x["match"]); c["n"] += 1
    TIER = {"US": 1, "UK": 1, "DE": 1, "BR": 2, "IN": 3, "ID": 3}
    countries = []
    for c in cmap.values():
        ae = round(sum(c["ec"]) / len(c["ec"]), 2); am = round(sum(c["mr"]) / len(c["mr"]), 2)
        tier = TIER.get(c["country"], 3)
        if c["country"] == "US":
            sug, why, up = "→ Native (feed)", "native eCPM ~3x banner", 310
        elif am < 0.7:
            sug, why, up = "Fix fill (add networks)", f"match {am:.0%} — demand leak", 70
        elif tier == 3:
            sug, why, up = "Keep adaptive + rewarded", "native demand thin here", 40
        else:
            sug, why, up = "Healthy — keep", "format matched to geo", 0
        countries.append({"country": c["country"], "tier": tier, "ecpm": ae, "match": am,
                          "revenue": round(c["rev"], 2), "suggested": sug, "why": why, "uplift": up})
    countries.sort(key=lambda r: r["uplift"], reverse=True)

    # mediation rows: add revenue share + status label
    med_total = sum(r["revenue"] for r in med_rows) or 1
    for r in med_rows:
        r["rev_share"] = round(r["revenue"] / med_total, 3)
        r["status"] = ("stale" if r["type"] == "waterfall" and r["fill"] < 0.65
                       else "latency" if r["latency_s"] >= 1.2 else "ok")

    # per-app compliance + connected accounts (Settings screen)
    app_names = sorted({x["app"] for x in pv})
    per_app = [{"app": a, "app_ads_txt": "verified", "consent": "UMP",
                "tcf": "v2.3" if i % 2 == 0 else "v2.2",
                "ivt": "flag" if a == "Photo Editor Pro" else "clean", "serving": "ok"}
               for i, a in enumerate(app_names)]
    accounts_list = [
        {"account_id": "pub-1122334455667788", "label": "Games Studio", "connected": True,
         "token": "Valid", "apps": ["Puzzle Blast", "Word Master"], "last_sync": "12 min ago"},
        {"account_id": "pub-9988776655443322", "label": "Utility Apps", "connected": True,
         "token": "Valid", "apps": ["Photo Editor Pro", "Weather Now"], "last_sync": "12 min ago"}]

    return {
        "kpis": {"revenue": round(total_rev, 2),
                 "ecpm": round(metrics.ecpm(tot_earn, tot_impr), 2),
                 "match_rate": round(metrics.match_rate(tot_req, tot_match), 3),
                 "arpdau": round(metrics.arpdau(metrics.ecpm(tot_earn, tot_impr), 3) / 1000 * 1000, 3),
                 "accounts": 2, "apps": len(apps_out)},
        "currency": "USD",
        "is_demo": True,
        "placements": pv,
        "apps": apps_out,
        "movers": {"increasing": inc, "decreasing": dec, "steady": len(steady)},
        "alerts": _alerts(dataset),
        "deductions": {"rows": ded_rows,
                       "decay_example": {"place": "Bottom_Banner", "series": dataset[4]["ded"]},
                       "avg_pct": round(sum(r["pct"] for r in ded_rows) / len(ded_rows), 3)},
        "mediation": {"summary": mediation.summarize(med_rows), "rows": med_rows,
                      "suggestions": mediation.suggest(med_rows)},
        "recommendations": {"total_uplift": total_uplift, "items": recs, "root_cause": cause},
        "account_health": {**health_summary, "per_app": per_app},
        "accounts": accounts_list,
        "revenue_trend": revenue_trend,
        "kpis_by_range": kpis_by_range,
        "countries": countries,
        "countries_by_app": {},
        "countries_daily": {}, "country_tier": {},
        "country_window": {"from": "", "to": "", "days": 7},
        "today_date": str(_anchor + _dt.timedelta(days=1)),   # demo: today has no data yet
        "latest_complete": demo_dates[-1],
    }


def empty_dashboard(accounts=1):
    """Honest 'no data yet' state for a LIVE account that returned zero rows (brand-new
    app, or first sync before AdMob has data). Same keys as the real dashboard so the
    UI never breaks — but clearly not fake demo numbers."""
    z = {"revenue": 0, "ecpm": 0, "match_rate": 0, "arpdau": 0}
    return {
        "kpis": {**z, "accounts": accounts, "apps": 0},
        "currency": "USD", "is_demo": False, "empty": True,
        "kpis_by_range": {k: dict(z) for k in ("today", "yesterday", "7d", "30d")},
        "revenue_trend": [0], "placements": [], "apps": [],
        "movers": {"increasing": [], "decreasing": [], "steady": 0},
        "alerts": {"counts": {"improving": 0, "critical": 0, "warning": 0}, "items": []},
        "deductions": {"rows": [], "avg_pct": 0, "decay_example": {"place": "—", "series": [0]}},
        "mediation": {"summary": {"networks": 0, "bidding_share": 0, "blended_fill": 0,
                                  "best_ecpm": {"ad_source": "—", "ecpm": 0}}, "rows": [], "suggestions": []},
        "recommendations": {"total_uplift": 0, "items": [], "root_cause": ["No data yet"]},
        "account_health": {**compliance.account_health(), "per_app": []},
        "accounts": [], "countries": [], "countries_by_app": {}, "country_window": {"from": "", "to": "", "days": 0},
        "countries_daily": {}, "country_tier": {}, "today_date": "", "latest_complete": "",
    }


def _common_currency(rows):
    """The account's report currency (rows carry it; default USD)."""
    from collections import Counter
    codes = Counter(r.get("currency_code") or "USD" for r in rows)
    return codes.most_common(1)[0][0] if codes else "USD"


def _clean_id(x):
    """Human-ish fallback when AdMob gives us no display name."""
    return (x or "").split("~")[-1].split("/")[-1] or "—"


def _plat_label(p):
    p = (p or "").upper()
    return {"ANDROID": "Android", "IOS": "iOS"}.get(p, (p.title() if p else "—"))


def build_mediation_daily(repo):
    """Compact daily-by-source mediation, so the Mediation screen can window to ANY period
    (Today / 7d / 30d …) with ZERO new AdMob fetch — the mediation report is already stored
    daily-by-ad-source (upsert_mediation). We collapse it to date × app × ad_source and ship
    only the five numbers each cell needs.

    Shape (mirrors adunit_country_daily for consistency):
      {"dates": ["YYYY-MM-DD", …],                 # sorted unique report dates (index = dayidx)
       "names": {src_key: "Display Name"},          # ad_source id -> human name
       "by_app": {app_name: {src_key: [[dayidx, rev_micros, impr, matched, req], …]}},
       "currency": "USD"}
    Portfolio (all-apps) view is summed from by_app in the UI, so we don't duplicate it here.
    Revenue stays in micros (integer) for exactness; the UI divides by 1e6."""
    from collections import defaultdict
    med = [dict(r) for r in repo.fetch_mediation()          # copies → safe to net down without touching the cache
           if str(r.get("report_date") or "") not in ("", "None")]
    if not med:
        return {"dates": [], "names": {}, "by_app": {}, "currency": "USD"}
    # Net each unit-day's mediation revenue DOWN by the same tracked deduction, so the Mediation total
    # stays equal to the (also-adjusted) Overview and the user's live AdMob.
    _apply_deduction(med, _deduction_by_unit_date(repo))
    dates = sorted({str(r.get("report_date")) for r in med})
    didx = {d: i for i, d in enumerate(dates)}
    names = {}
    # app_name -> src_key -> dayidx -> [rev_micros, impr, matched, req]
    agg = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0])))
    cur = None
    for r in med:
        d = str(r.get("report_date") or "")
        if d not in didx:
            continue
        app = r.get("app_name") or _clean_id(r.get("app_id"))
        k = r.get("ad_source")
        names.setdefault(k, r.get("source_name") or _clean_id(k))
        cur = cur or r.get("currency_code")
        cell = agg[app][k][didx[d]]
        cell[0] += r.get("estimated_earnings_micros", 0) or 0
        cell[1] += r.get("impressions", 0) or 0
        cell[2] += r.get("matched_requests", 0) or 0
        cell[3] += r.get("ad_requests", 0) or 0
    by_app = {}
    for app, srcs in agg.items():
        out = {}
        for k, days in srcs.items():
            out[k] = [[di, c[0], c[1], c[2], c[3]] for di, c in sorted(days.items())]
        by_app[app] = out
    return {"dates": dates, "names": names, "by_app": by_app, "currency": cur or "USD"}


def _deduction_by_unit_date(repo):
    """{(ad_unit_id, report_date): deduction_micros} — how much AdMob has revised each unit-day DOWN
    since it closed (first vs latest POST-CLOSE snapshot, only when it dropped). Same signal the
    Deductions tab shows; used to net revenue down to the user's LIVE AdMob (which already applied it).
    Only recent still-settling days carry a value; finalized days have none. Zero new fetch."""
    from collections import defaultdict
    cell = defaultdict(dict)
    for s in repo.fetch_snapshots():
        rd = str(s.get("report_date") or ""); sd = str(s.get("snapshot_date") or "")
        uid = s.get("ad_unit_id")
        if not uid or rd in ("", "None") or sd in ("", "None") or sd <= rd:
            continue                                        # post-close snapshots only
        cell[(uid, rd)][sd] = s.get("estimated_earnings_micros", 0) or 0
    out = {}
    for key, snaps in cell.items():
        if len(snaps) < 2:
            continue
        ks = sorted(snaps)
        first, latest = snaps[ks[0]], snaps[ks[-1]]
        if first > latest:
            out[key] = first - latest
    return out


def _apply_deduction(rows, ded_ud):
    """Subtract each (unit, date)'s tracked deduction from that unit-date's revenue rows, split
    proportionally across them and floored at 0. Mutates rows in place. Keeps totals matching across
    Overview/Mediation because every consumer nets down by the same per-unit-day amount."""
    if not ded_ud:
        return
    from collections import defaultdict
    ud = defaultdict(list)
    for r in rows:
        ud[(r.get("ad_unit_id"), str(r.get("report_date")))].append(r)
    for key, ded in ded_ud.items():
        rs = ud.get(key)
        if not rs or ded <= 0:
            continue
        tot = sum((r.get("estimated_earnings_micros") or 0) for r in rs)
        if tot <= 0:
            continue
        take = min(ded, tot)                                # never push a day below 0
        for r in rs:
            sh = (r.get("estimated_earnings_micros") or 0) / tot
            r["estimated_earnings_micros"] = int(round((r.get("estimated_earnings_micros") or 0) - take * sh))


def build_deductions_daily(repo):
    """Per (ad_unit, report_date) estimate DECAY from the append-only snapshots — 'pehle itna
    tha, ab itna hua'. AdMob revises a day's estimate DOWN after close (invalid-traffic removal);
    each hourly snapshot captures that, so first-vs-latest POST-CLOSE snapshot = the deduction.
    Zero new fetch (snapshots already stored). Country isn't in the snapshot (AdMob gives the
    network report un-split by geo), so the UI attributes a unit's deduction to its countries by
    that unit's revenue share from the already-shipped acd — labelled as such, never faked.

    Shape (mirrors acd/mediation_daily):
      {"dates": ["YYYY-MM-DD", …],                       # report dates that show a real decay
       "units": {uid: {"app_id","unit_name","app_name"}},
       "data":  {uid: [[dayidx, first_micros, latest_micros], …]}}   # only cells that actually decayed
    """
    from collections import defaultdict
    # names come from the network report (snapshots carry only ids)
    namemap = {}
    for r in repo.fetch_network():
        uid = r.get("ad_unit_id")
        if uid and uid not in namemap:
            namemap[uid] = {"app_id": r.get("app_id"),
                            "unit_name": r.get("unit_name") or _clean_id(uid),
                            "app_name": r.get("app_name") or _clean_id(r.get("app_id"))}
    # (unit, report_date) -> {snapshot_date: earnings_micros}, POST-CLOSE snapshots only
    cell = defaultdict(dict)
    for s in repo.fetch_snapshots():
        rd = str(s.get("report_date") or ""); sd = str(s.get("snapshot_date") or "")
        uid = s.get("ad_unit_id")
        if not uid or rd in ("", "None") or sd in ("", "None") or sd <= rd:
            continue                                    # keep only snapshots taken AFTER the day closed
        cell[(uid, rd)][sd] = s.get("estimated_earnings_micros", 0) or 0
    # keep only cells with an observed DROP (first > latest across >=2 post-close snapshots)
    per_unit = defaultdict(dict)                         # uid -> {report_date: (first, latest)}
    dates = set()
    for (uid, rd), snaps in cell.items():
        if len(snaps) < 2:
            continue
        ks = sorted(snaps)
        first, latest = snaps[ks[0]], snaps[ks[-1]]
        if first > latest and first > 0:                # a genuine deduction (not noise/uptick)
            per_unit[uid][rd] = (first, latest)
            dates.add(rd)
    dates = sorted(dates)
    didx = {d: i for i, d in enumerate(dates)}
    units, data = {}, {}
    for uid, days in per_unit.items():
        data[uid] = [[didx[rd], f, l] for rd, (f, l) in sorted(days.items(), key=lambda kv: kv[0])]
        units[uid] = namemap.get(uid, {"app_id": None, "unit_name": _clean_id(uid),
                                       "app_name": _clean_id(uid)})
    return {"dates": dates, "units": units, "data": data}


def _revenue_rows(repo):
    """The number the AdMob UI shows for an account/app/placement INCLUDES third-party
    mediated networks, so the source of truth is the MEDIATION report summed across ad
    sources — NOT the AdMob-Network-only report (which undercounts by the mediated share).

    Collapse mediation to one row per (date, app, ad_unit, format, platform): sum
    earnings/impressions/clicks across sources (each impression & dollar is distinct), and
    take request counts from the network report per (date, ad_unit) — summing ad_requests
    across bidding sources would multiply the same requests and wreck match-rate. If
    mediation isn't set up, fall back to the network report (the two are equal then)."""
    from collections import defaultdict
    med = [r for r in repo.fetch_mediation() if str(r.get("report_date") or "") not in ("", "None")]
    net = repo.fetch_network()
    if not med:
        return net
    reqs = defaultdict(lambda: {"ad_requests": 0, "matched_requests": 0})
    for r in net:
        k = (str(r.get("report_date")), r.get("ad_unit_id"))
        reqs[k]["ad_requests"] += r.get("ad_requests", 0) or 0
        reqs[k]["matched_requests"] += r.get("matched_requests", 0) or 0
    agg = {}
    for r in med:
        key = (str(r.get("report_date")), r.get("app_id"), r.get("ad_unit_id"),
               r.get("format"), r.get("platform"))
        a = agg.get(key)
        if a is None:
            a = {"report_date": r.get("report_date"), "account_id": r.get("account_id"),
                 "app_id": r.get("app_id"), "app_name": r.get("app_name"),
                 "ad_unit_id": r.get("ad_unit_id"), "unit_name": r.get("unit_name"),
                 "country": r.get("country") or "All", "format": r.get("format"),
                 "platform": r.get("platform"), "currency_code": r.get("currency_code") or "USD",
                 "impressions": 0, "clicks": 0, "estimated_earnings_micros": 0,
                 "ad_requests": 0, "matched_requests": 0}
            agg[key] = a
        a["impressions"] += r.get("impressions", 0) or 0
        a["clicks"] += r.get("clicks", 0) or 0
        a["estimated_earnings_micros"] += r.get("estimated_earnings_micros", 0) or 0
    for key, a in agg.items():                       # clean per-ad-unit requests from network
        rq = reqs.get((key[0], key[2]))
        if rq:
            a["ad_requests"], a["matched_requests"] = rq["ad_requests"], rq["matched_requests"]
    return list(agg.values())


def build_from_db(repo, today=None):
    """Same dashboard structure, computed from REAL fetched rows in the store.

    `today` (a date or 'YYYY-MM-DD') marks the LIVE/partial day; if omitted it's
    derived in the report timezone. The newest day is treated as partial ONLY if it
    equals today — otherwise (e.g. today's row hasn't landed yet for a low-traffic
    app) every returned day is complete and none is hidden from trends."""
    from collections import defaultdict
    import statistics
    # Revenue source of truth = mediation (all ad sources), so totals match the AdMob app;
    # drop rows with a missing/garbage date ("None" would sort as the NEWEST day and hijack "today")
    net = [r for r in _revenue_rows(repo) if str(r.get("report_date") or "") not in ("", "None")]
    if not net:
        return build_dashboard()
    # Net revenue DOWN by AdMob's tracked estimate-revision (deductions), so every number matches the
    # user's LIVE AdMob (which already applied it). Only recent still-settling days move; finalized
    # days are untouched. The Deductions tab still shows the raw revision — this is where it's applied.
    _apply_deduction(net, _deduction_by_unit_date(repo))
    snaps = list(repo.fetch_snapshots())
    med = list(repo.fetch_mediation())
    cur = _common_currency(net)

    by_unit = defaultdict(list)
    for r in net:
        if not r.get("ad_unit_id"):
            continue
        by_unit[r["ad_unit_id"]].append(r)
    if not by_unit:
        return build_dashboard()
    snap_by = defaultdict(list)
    for s in snaps:
        snap_by[(str(s["report_date"]), s["ad_unit_id"])].append(s)

    # per-placement country mix (geo drill) from the placement_country store — top geos per unit
    _pc_raw = defaultdict(lambda: defaultdict(lambda: {"rev": 0, "impr": 0, "req": 0, "matched": 0}))
    for r in repo.fetch_placement_country():
        u = r.get("ad_unit_id")
        if not u:
            continue
        c = _pc_raw[u][r.get("country") or "All"]
        c["rev"] += r.get("estimated_earnings_micros", 0) or 0
        c["impr"] += r.get("impressions", 0) or 0
        c["req"] += r.get("ad_requests", 0) or 0
        c["matched"] += r.get("matched_requests", 0) or 0
    pc_by_unit = {}
    for u, cc in _pc_raw.items():
        tot = sum(v["rev"] for v in cc.values()) or 1
        cr = [dict(country=name, revenue=round(metrics.micros_to_currency(v["rev"]), 2),
                   ecpm=round(metrics.ecpm(v["rev"], v["impr"]), 2),
                   match=round(metrics.match_rate(v["req"], v["matched"]), 3),
                   share=round(v["rev"] / tot, 3)) for name, v in cc.items() if v["rev"] > 0]
        cr.sort(key=lambda x: x["revenue"], reverse=True)
        pc_by_unit[u] = cr[:30]

    # Today's report date is a LIVE, PARTIAL day (we re-fetch it hourly). If we let
    # a half-finished day into trends/verdicts/alerts, every morning would look like
    # a crash ("revenue down 96%"). So finished days drive analysis; today is shown
    # separately as a live number.
    if today is None:
        from datetime import datetime as _dt, timezone as _tz
        try:
            from zoneinfo import ZoneInfo
            import os as _os
            today = _dt.now(ZoneInfo(_os.getenv("REPORT_TIMEZONE", "America/Los_Angeles"))).date()
        except Exception:
            today = _dt.now(_tz.utc).date()
    today_str = str(today)
    all_dates_g = sorted({str(r["report_date"]) for r in net})
    # newest day is "partial/live" ONLY if it's actually today; else it's a finished day
    partial_day = all_dates_g[-1] if (all_dates_g and all_dates_g[-1] == today_str) else None
    complete_set = set(all_dates_g[:-1]) if partial_day else set(all_dates_g)
    if not complete_set:                     # only the partial day exists → use it
        complete_set = set(all_dates_g)
    # RECENCY GATE for alerts: only a placement that is STILL ACTIVE may raise a "revenue
    # dropped / lost $X/day" alert. A placement whose newest FINISHED day is more than a few
    # days behind the portfolio's newest finished day has been dormant for weeks/months — its
    # "drop" already happened long ago, so flagging it now as a live loss is misleading (this is
    # exactly what surfaced dead placements like one last seen in Feb as today's top alerts).
    from datetime import date as _date
    _portfolio_latest = max(complete_set) if complete_set else ""
    ALERT_RECENCY_DAYS = 3

    def _alert_recent(day):
        """True if `day` (a placement's newest finished day) is within ALERT_RECENCY_DAYS
        calendar days of the portfolio's newest finished day. Bad/blank dates → treat as
        recent (fail open) so a parse hiccup never silently drops a real alert."""
        if not _portfolio_latest or not day:
            return True
        try:
            return (_date.fromisoformat(_portfolio_latest) - _date.fromisoformat(day)).days <= ALERT_RECENCY_DAYS
        except Exception:
            return True

    def _chg(ser, w=7):
        """Signed fractional change of the latest finished day vs the prior ~week mean."""
        if not ser or len(ser) < 4:
            return None
        prior = ser[-min(w, len(ser) - 1) - 1:-1]
        base = (sum(prior) / len(prior)) if prior else 0
        return ((ser[-1] - base) / base) if base else None

    pv, alerts_items, alert_cand = [], [], []
    app_base = defaultdict(float)          # per-app baseline daily revenue (sum of placement 7-day medians)
    last_decay = []
    ac = {"improving": 0, "critical": 0, "warning": 0}
    for unit, rows in by_unit.items():
        dates = sorted({str(r["report_date"]) for r in rows})
        drev = defaultdict(int)
        for r in rows:
            drev[str(r["report_date"])] += r["estimated_earnings_micros"]
        cdates = [d for d in dates if d in complete_set] or dates     # finished days only
        series = [round(metrics.micros_to_currency(drev[d]), 2) for d in cdates]
        latest = cdates[-1]                                           # latest COMPLETE (full) day
        lr = [r for r in rows if str(r["report_date"]) == latest]
        req = sum(r["ad_requests"] for r in lr); matched = sum(r["matched_requests"] for r in lr)
        impr = sum(r["impressions"] for r in lr); clicks = sum(r["clicks"] for r in lr)
        earn = sum(r["estimated_earnings_micros"] for r in lr)
        ec = metrics.ecpm(earn, impr); mr = metrics.match_rate(req, matched)
        ct = metrics.ctr(impr, clicks); sr = metrics.show_rate(matched, impr)
        fmt = lr[0]["format"]
        aname = lr[0].get("app_name") or _clean_id(lr[0].get("app_id"))
        pname = lr[0].get("unit_name") or _clean_id(unit)
        cc = defaultdict(int)
        for r in lr:
            cc[r["country"]] += r["estimated_earnings_micros"]
        country = max(cc, key=cc.get) if cc else ""
        lvl = (sum(series) / len(series)) if series else 0
        slope_norm = (trend.slope(series) / lvl) if lvl else 0
        hs = health.health_score(revenue_slope_norm=slope_norm, match_rate=mr, ecpm=ec,
                                 peer_ecpm=PEER_ECPM.get(fmt, 2.2), show_rate=sr, has_ivt_flag=False)
        # deduction/decay: newest FINISHED day with >=2 POST-CLOSE snapshots (a day
        # only "decays" after it closes; the intraday snapshot is excluded).
        ded = 0.0
        for rd_ in reversed(cdates):
            sn = sorted((str(s["snapshot_date"]), round(metrics.micros_to_currency(s["estimated_earnings_micros"]), 2))
                        for s in snap_by.get((rd_, unit), []) if str(s["snapshot_date"]) > rd_)
            if len(sn) >= 3:      # need ≥3 post-close snapshots; 2 is too noisy (and the recent
                ded = deduction.deduction_pct(sn); last_decay = [v for _, v in sn]; break   # tz switch made 2-point diffs meaningless
        today_rev = (round(metrics.micros_to_currency(drev.get(partial_day, 0)), 2)
                     if partial_day and partial_day not in complete_set else None)
        # per-day series → root-cause + multi-metric alerts (finished days only)
        _da = defaultdict(lambda: {"req": 0, "matched": 0, "impr": 0, "clicks": 0})
        for r in rows:
            d0 = str(r["report_date"])
            _da[d0]["req"] += r["ad_requests"]; _da[d0]["matched"] += r["matched_requests"]
            _da[d0]["impr"] += r["impressions"]; _da[d0]["clicks"] += r["clicks"]
        match_ser = [round(metrics.match_rate(_da[d]["req"], _da[d]["matched"]), 4) for d in cdates]
        ctr_ser = [round(metrics.ctr(_da[d]["impr"], _da[d]["clicks"]), 5) for d in cdates]
        show_ser = [round(min(1.0, metrics.show_rate(_da[d]["matched"], _da[d]["impr"])), 4) for d in cdates]  # cap 100% (impr are mediation, matched network)
        ecpm_ser = [round(metrics.ecpm(drev[d], _da[d]["impr"]), 3) for d in cdates]
        req_ser = [_da[d]["req"] for d in cdates]
        cause = rootcause.classify(ecpm_change=_chg(ecpm_ser), match_change=_chg(match_ser),
                                   show_change=_chg(show_ser), ctr_change=_chg(ctr_ser),
                                   deduction_high=(ded >= 0.15))
        _mean = (sum(series) / len(series)) if series else 0
        vol = round(((sum((v - _mean) ** 2 for v in series) / len(series)) ** 0.5 / _mean), 3) if _mean else 0.0
        # per-placement RAW daily counts for EVERY day we have (incl. partial today),
        # so the frontend can sum ANY time window (today / 7d / 30d / 90d / month / all /
        # custom) and derive revenue, impr, req, match, show, ctr, ecpm for that window.
        # [date, earn_micros, impressions, ad_requests, matched_requests, clicks]
        daily = [[d, drev[d], _da[d]["impr"], _da[d]["req"], _da[d]["matched"], _da[d]["clicks"]]
                 for d in dates[-400:]]        # cap ~13 months so the payload stays bounded as history grows
        pv.append(dict(id=unit, name=pname, app=aname,
                       account=(lr[0].get("account_id") or "—"),
                       platform=(lr[0].get("platform") or ""),
                       format=fmt, country=country, ecpm=round(ec, 2), match=round(mr, 3),
                       ctr=round(ct, 4), show=round(sr, 3), health=hs, band=health.band(hs),
                       verdict=trend.verdict(series),
                       change_pct=round(trend.pct_change_window(series, min(9, len(series) - 1)), 3) if len(series) > 1 else 0.0,
                       revenue=round(metrics.micros_to_currency(earn), 2), today_revenue=today_rev,
                       deduction_pct=round(ded, 3), trend=series[-14:], hist=series,
                       cause=cause[0], cause_text=cause[1], volatility=vol,
                       by_country=pc_by_unit.get(unit, []), daily=daily))
        # base_rev = MEDIAN of the 7 complete days BEFORE the latest complete day — the SAME
        # reference rules.evaluate() uses to detect a drop, so the % and the $ lost reconcile.
        # (Median, not average, so one odd day doesn't skew it.) Accumulate per app for the gate.
        prior7 = series[:-1][-7:]
        base_rev = round(statistics.median(prior7), 2) if prior7 else round(series[-1] if series else 0, 2)
        app_base[aname] += base_rev
        # Collect PROBLEM alerts only (no "improving" — that lives in Movers). Filtered AFTER the
        # loop to placements that are a meaningful share of their APP, so micro-placements can't spam.
        # `_alert_recent(latest)` skips DORMANT placements (last active days/months ago) so a stale,
        # long-past drop can't masquerade as a live "you're losing $X/day now" alert.
        if len(series) >= 3 and _alert_recent(latest):
            for metric, ser in (("revenue", series), ("match_rate", match_ser), ("show_rate", show_ser),
                                ("ctr", ctr_ser), ("requests", req_ser)):
                sig = rules.evaluate(metric, ser[-1], ser[:-1])
                if sig.is_alert and sig.severity != "good":
                    # a show-rate drop is a lower-urgency (technical) signal → "watch", matching
                    # the rules panel; revenue/requests/match/ctr keep the engine's severity.
                    sev = "watch" if (metric == "show_rate" and sig.kind == "drop") else sig.severity
                    alert_cand.append(dict(severity=sev, kind=sig.kind, metric=metric,
                                           message=sig.message, place=pname, id=unit, app=aname,
                                           country=country, current=round(ser[-1], 4),
                                           base_rev=base_rev,
                                           lost=(round(base_rev - series[-1], 2) if metric == "revenue" else None)))

    # Materiality gate: a placement must earn >= ALERT_MIN_SHARE of ITS OWN APP's baseline
    # revenue to alert (self-scaling per app, so a smaller app's important placements still fire
    # instead of being drowned out by the big apps). Rank by dollars at stake, keep the top few.
    ALERT_MIN_SHARE = 0.005                         # 0.5% of that APP's daily revenue (tunable)
    ALERT_MIN_USD = 10.0                            # + absolute noise floor: never alert on a placement < this/day
    # app_base (per-app sum of placement 7-day medians) was accumulated in the loop above.
    # threshold = max(app's own 0.5%, $10). App-wise so a smaller app's important placements
    # still fire; the $10 floor stops tiny placements from a small app re-flooding the screen.
    def _floor(app):
        return max(app_base.get(app, 0) * ALERT_MIN_SHARE, ALERT_MIN_USD)
    material = [c for c in alert_cand if c["base_rev"] >= _floor(c["app"])]
    # GROUP by placement — ONE card per placement listing every metric that dropped, instead of
    # the same placement appearing 2-3 times (revenue + requests + match). Card severity = worst
    # of its metrics; $ loss = the revenue loss.
    _sevr = {"critical": 0, "warning": 1, "watch": 2}
    by_place = {}
    for c in material:
        g = by_place.get(c["id"])                   # key by ad-unit ID, not name (names can collide)
        if g is None:
            g = by_place[c["id"]] = dict(place=c["place"], id=c["id"], app=c["app"], country=c["country"],
                                         base_rev=c["base_rev"], severity=c["severity"],
                                         kind=c["kind"], lost=0.0, metrics=[])
        g["metrics"].append(dict(metric=c["metric"], message=c["message"],
                                 current=c["current"], lost=c.get("lost"), kind=c["kind"]))
        if _sevr.get(c["severity"], 9) < _sevr.get(g["severity"], 9):
            g["severity"], g["kind"] = c["severity"], c["kind"]
        if c["metric"] == "revenue" and c.get("lost"):
            g["lost"] = c["lost"]
    groups = list(by_place.values())
    for g in groups:                                # revenue first, then the rest — stable order
        g["metrics"].sort(key=lambda m: (m["metric"] != "revenue", m["metric"]))
    groups.sort(key=lambda g: (g["lost"] if g["lost"] else g["base_rev"]), reverse=True)
    ac = {"critical": 0, "warning": 0, "watch": 0}
    for g in groups:                                # count PLACEMENTS, not per-metric instances
        ac[g["severity"]] = ac.get(g["severity"], 0) + 1
    alerts_items = groups[:15]                       # top problem placements by $ at stake
    # per-app effective $ floors, surfaced so the UI can show each app's own threshold
    alert_floor = {a: round(_floor(a), 2) for a in app_base}
    alert_min_usd = ALERT_MIN_USD

    # headline = latest FINISHED day (a full day), never the partial today
    cdates_all = sorted(complete_set)
    latest_all = cdates_all[-1]
    la = [r for r in net if str(r["report_date"]) == latest_all]
    tot_earn = sum(r["estimated_earnings_micros"] for r in la); tot_impr = sum(r["impressions"] for r in la)
    tot_req = sum(r["ad_requests"] for r in la); tot_match = sum(r["matched_requests"] for r in la)
    ecpm_now = round(metrics.ecpm(tot_earn, tot_impr), 2); match_now = round(metrics.match_rate(tot_req, tot_match), 3)
    total_rev = round(metrics.micros_to_currency(tot_earn), 2)
    arp = round(metrics.arpdau(ecpm_now, 3), 3)

    # real per-range KPIs: Today = live/partial; the rest use FINISHED days
    def _kpis_for(dset):
        rr = [r for r in net if str(r["report_date"]) in dset]
        e = sum(r["estimated_earnings_micros"] for r in rr); im = sum(r["impressions"] for r in rr)
        rq = sum(r["ad_requests"] for r in rr); ma = sum(r["matched_requests"] for r in rr)
        ecp = round(metrics.ecpm(e, im), 2)
        return {"revenue": round(metrics.micros_to_currency(e), 2), "ecpm": ecp,
                "match_rate": round(metrics.match_rate(rq, ma), 3),
                "arpdau": round(metrics.arpdau(ecp, 3), 3)}
    _zero = {"revenue": 0, "ecpm": 0, "match_rate": 0, "arpdau": 0}

    def _range(day_list):
        """KPIs for a set of days PLUS the exact date window, so the UI can show
        '17–23 Jul (7 days)' and the user can verify the same range in the AdMob app.
        Sum of AdMob's own daily numbers == AdMob's range total (not an approximation)."""
        ks = _kpis_for(set(day_list))
        if day_list:
            ks["from"], ks["to"], ks["days"] = day_list[0], day_list[-1], len(day_list)
        return ks

    kbr = {"today": ({**_kpis_for({partial_day}), "from": partial_day, "to": partial_day, "days": 1}
                     if partial_day else dict(_zero)),        # 0 until today's data lands
           "yesterday": _range([latest_all]),
           "7d": _range(cdates_all[-7:]),
           "30d": _range(cdates_all[-30:])}

    day_tot = defaultdict(int)     # trend line = finished days only (no partial-today cliff)
    for r in net:
        if str(r["report_date"]) in complete_set:
            day_tot[str(r["report_date"])] += r["estimated_earnings_micros"]
    rt = [round(metrics.micros_to_currency(day_tot[d]), 2) for d in sorted(day_tot)][-14:]

    # app-level rollup from raw rows → REAL eCPM, WoW trend, platform (not demo-only)
    app_day = defaultdict(lambda: defaultdict(int))
    app_latest = defaultdict(lambda: {"earn": 0, "impr": 0})
    app_plat = defaultdict(set)
    for r in net:
        an = r.get("app_name") or _clean_id(r.get("app_id"))
        dd = str(r["report_date"])
        if dd in complete_set:
            app_day[an][dd] += r["estimated_earnings_micros"]
        if dd == latest_all:
            app_latest[an]["earn"] += r["estimated_earnings_micros"]
            app_latest[an]["impr"] += r["impressions"]
        if r.get("platform"):
            app_plat[an].add(r["platform"])

    apps = {}
    for x in pv:
        a = apps.setdefault(x["app"], dict(name=x["app"], account=x.get("account", "—"),
                                           placements=0, revenue=0.0, healths=[], declining=0,
                                           at_risk=0, dist={"good": 0, "watch": 0, "risk": 0}))
        a["placements"] += 1; a["revenue"] += x["revenue"]; a["healths"].append(x["health"])
        a["dist"][x["band"]] = a["dist"].get(x["band"], 0) + 1
        if x["verdict"] == "declining":
            a["declining"] += 1
        if x["band"] == "risk":
            a["at_risk"] += 1
    apps_out = []
    for a in apps.values():
        an = a["name"]
        h = a.pop("healths"); a["avg_health"] = round(sum(h) / len(h)); a["revenue"] = round(a["revenue"], 2)
        al = app_latest.get(an, {"earn": 0, "impr": 0})
        a["ecpm"] = round(metrics.ecpm(al["earn"], al["impr"]), 2)
        ser = [round(metrics.micros_to_currency(app_day[an][d]), 2) for d in sorted(app_day[an])]
        a["change_pct"] = round(trend.pct_change_window(ser, min(9, len(ser) - 1)), 3) if len(ser) > 1 else 0.0
        dd = a.pop("dist"); a["health_dist"] = [dd["good"], dd["watch"], dd["risk"]]
        plats = sorted(app_plat.get(an, set()))
        a["platform"] = " · ".join(_plat_label(p) for p in plats) if plats else "—"
        apps_out.append(a)

    inc, dec, steady = trend.split_movers([dict(name=x["name"], app=x["app"], change_pct=x["change_pct"]) for x in pv])
    ded_rows = sorted([dict(place=x["name"], app=x["app"], geo=x["country"], pct=x["deduction_pct"],
                            revenue=x["revenue"], ecpm=x["ecpm"],
                            flag="ivt" if x["deduction_pct"] >= 0.15 else ("watch" if x["deduction_pct"] >= 0.05 else "normal"))
                       for x in pv], key=lambda r: r["revenue"], reverse=True)
    # honest estimates: daily $ lost to deductions × 30; worst IVT-flagged placement (or none)
    at_risk_monthly = round(sum(x["deduction_pct"] * x["revenue"] for x in pv) * 30, 2)
    ivt_example = next(({"place": r["place"], "geo": r["geo"], "pct": r["pct"]}
                        for r in ded_rows if r["flag"] == "ivt"), None)

    def _mediation_rows(rows):
        msrc = defaultdict(lambda: dict(revenue=0, impr=0, matched=0, req=0, name=None))
        for r in rows:
            k = r.get("ad_source"); v = msrc[k]
            v["revenue"] += r["estimated_earnings_micros"]; v["impr"] += r["impressions"]
            v["matched"] += r["matched_requests"]; v["req"] += r["ad_requests"]
            v["name"] = v["name"] or r.get("source_name") or _clean_id(k)
        out = []
        for k, v in msrc.items():
            fill = round(metrics.match_rate(v["req"], v["matched"]), 2)
            # AdMob's report doesn't label bidding vs waterfall or adapter latency, so we don't
            # fake them: type is the honest "mediation", status is derived from real fill.
            out.append(dict(ad_source=v["name"], type="mediation", fill=fill,
                            ecpm=round(metrics.ecpm(v["revenue"], v["impr"]), 2),
                            revenue=round(metrics.micros_to_currency(v["revenue"]), 2),
                            latency_s=None, rev_share=0.0,
                            status=("low fill" if v["req"] and fill < 0.5 else "ok")))
        out.sort(key=lambda r: r["revenue"], reverse=True)
        tot = sum(r["revenue"] for r in out) or 1
        for r in out:
            r["rev_share"] = round(r["revenue"] / tot, 3)
        return out

    med_rows = _mediation_rows(med)
    _mba = defaultdict(list)
    for r in med:
        _mba[r.get("app_name") or _clean_id(r.get("app_id"))].append(r)
    mediation_by_app = {}
    for app, rows in _mba.items():
        mr = _mediation_rows(rows)
        mediation_by_app[app] = {"rows": mr,
                                 "summary": (mediation.summarize(mr) if mr else
                                             {"networks": 0, "bidding_share": 0, "blended_fill": 0, "best_ecpm": None}),
                                 "suggestions": (mediation.suggest(mr) if mr else [])}

    # Real per-country breakdown from the country report, last 7 complete days. Computed
    # BOTH portfolio-wide AND per-app so the App filter can drill into a single app.
    cwin = set(cdates_all[-7:])
    TIER = {"US": 1, "GB": 1, "UK": 1, "DE": 1, "CA": 1, "AU": 1, "FR": 1, "JP": 1, "NL": 1, "SE": 1,
            "BR": 2, "MX": 2, "RU": 2, "TR": 2, "PL": 2, "TH": 2, "ZA": 2, "SA": 2, "AE": 2, "MY": 2,
            "IN": 3, "ID": 3, "PK": 3, "BD": 3, "NG": 3, "PH": 3, "VN": 3, "EG": 3, "KE": 3}

    def _country_view(rows):
        cg = defaultdict(lambda: {"rev": 0, "impr": 0, "req": 0, "matched": 0})
        for r in rows:
            c = cg[r.get("country") or "All"]
            c["rev"] += r.get("estimated_earnings_micros", 0) or 0
            c["impr"] += r.get("impressions", 0) or 0
            c["req"] += r.get("ad_requests", 0) or 0
            c["matched"] += r.get("matched_requests", 0) or 0
        tot = sum(c["rev"] for c in cg.values()) or 1
        out = []
        for name, c in cg.items():
            if c["rev"] <= 0:
                continue                      # only geos that actually earned in the window
            mrc = metrics.match_rate(c["req"], c["matched"])
            out.append(dict(country=name, tier=TIER.get(name, 3),
                            ecpm=round(metrics.ecpm(c["rev"], c["impr"]), 2),
                            match=round(mrc, 3), impressions=c["impr"],
                            revenue=round(metrics.micros_to_currency(c["rev"]), 2),
                            share=round(c["rev"] / tot, 3),
                            why=f'{round(100 * c["rev"] / tot)}% of revenue',
                            suggested=("Low fill" if c["req"] and mrc < 0.7 else
                                       "Premium geo" if TIER.get(name, 3) == 1 else "—"), uplift=0))
        out.sort(key=lambda r: r["revenue"], reverse=True)
        return out

    cwin_rows = [r for r in repo.fetch_country() if str(r.get("report_date") or "") in cwin]
    countries = _country_view(cwin_rows)
    _cba = defaultdict(list)
    for r in cwin_rows:
        _cba[r.get("app_name") or _clean_id(r.get("app_id"))].append(r)
    countries_by_app = {app: _country_view(rows) for app, rows in _cba.items()}
    country_window = {"from": (sorted(cwin)[0] if cwin else ""),
                      "to": (sorted(cwin)[-1] if cwin else ""), "days": len(cwin)}

    # Per-country DAILY raw counts (per app) so the frontend can window the Countries
    # screen to ANY range (today…custom) with FULL metrics (revenue/impr/req/match/show/
    # ctr/eCPM). Cap to top-50 countries/app by revenue — the long tail is a fraction of a
    # percent, and this keeps the payload small.  countries_daily[app][country] = daily rows.
    _capp = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"e": 0, "i": 0, "q": 0, "m": 0, "c": 0})))
    for r in repo.fetch_country():
        d0 = str(r.get("report_date") or "")
        if d0 in ("", "None"):
            continue
        appn = r.get("app_name") or _clean_id(r.get("app_id"))
        cn = r.get("country") or "All"
        cell = _capp[appn][cn][d0]
        cell["e"] += r.get("estimated_earnings_micros", 0) or 0
        cell["i"] += r.get("impressions", 0) or 0
        cell["q"] += r.get("ad_requests", 0) or 0
        cell["m"] += r.get("matched_requests", 0) or 0
        cell["c"] += r.get("clicks", 0) or 0
    countries_daily = {}
    for appn, cc in _capp.items():
        ranked = sorted(cc.items(), key=lambda kv: sum(v["e"] for v in kv[1].values()), reverse=True)
        top = [(cn, days) for cn, days in ranked if sum(v["e"] for v in days.values()) > 0][:50]
        countries_daily[appn] = {cn: [[d, days[d]["e"], days[d]["i"], days[d]["q"], days[d]["m"], days[d]["c"]]
                                      for d in sorted(days)[-400:]] for cn, days in top}
    country_tier = {cn: TIER.get(cn, 3) for app in countries_daily.values() for cn in app}

    # Recommendations from REAL placement signals (biggest-revenue placements first).
    recs = []
    for x in sorted(pv, key=lambda p: p["revenue"], reverse=True):
        picked = None
        if x["match"] and x["match"] < 0.7:
            picked = ("Add mediation networks / enable bidding",
                      f'fill sirf {round(x["match"] * 100)}% — demand leak, revenue chhut raha hai', "high")
        elif x["deduction_pct"] >= 0.15:
            picked = ("Traffic source check karo (IVT)",
                      f'deduction {round(x["deduction_pct"] * 100)}% — invalid-traffic ka risk', "high")
        elif x["format"] == "banner" and x["ecpm"] and x["ecpm"] < 3.0:
            picked = ("Banner → Native / Adaptive try karo",
                      f'banner eCPM {x["ecpm"]} — native format usually 2-3x kamata hai', "medium")
        elif x["band"] == "risk":
            picked = ("Placement review karo", f'health {x["health"]} — kaafi low', "medium")
        if picked:
            recs.append(dict(action=picked[0], reason=picked[1], confidence=picked[2], ab=True,
                             place=f'{x["name"]} ({x["app"]})', app=x["app"], uplift=0))
    recs = sorted(recs, key=lambda r: r["confidence"] == "high", reverse=True)[:20]
    rec_root = ["fill & format", "sabse bada lever: low-fill placements aur banner→native"]

    # Account health from REAL signals: IVT = placements with >=15% deduction + CTR-spike alerts.
    # Consent / app-ads.txt / TCF / Policy Center aren't in the AdMob API → shown as "not connected".
    ivt_flags = sum(1 for x in pv if x["deduction_pct"] >= 0.15) + sum(1 for a in alerts_items if a.get("kind") == "spike")
    per_app_health = [dict(app=a["name"],
                           ivt=("flag" if any(x["app"] == a["name"] and x["deduction_pct"] >= 0.15 for x in pv) else "clean"),
                           app_ads_txt="—", consent="—", tcf="—", serving="ok")
                      for a in apps_out]
    account_health_out = {**compliance.account_health(ivt_flags=ivt_flags), "per_app": per_app_health}

    accts = sorted({r["account_id"] for r in net})
    acct_apps = defaultdict(set)
    for x in pv:
        acct_apps[x.get("account")].add(x["app"])
    med_summary = (mediation.summarize(med_rows) if med_rows else
                   {"networks": 0, "bidding_share": 0, "blended_fill": 0, "best_ecpm": {"ad_source": "—", "ecpm": 0}})
    return {
        "kpis": {"revenue": total_rev, "ecpm": ecpm_now, "match_rate": match_now, "arpdau": arp,
                 "accounts": len(accts), "apps": len(apps_out)},
        "currency": cur,
        "is_demo": False,
        "kpis_by_range": kbr,
        "revenue_trend": rt or [total_rev],
        "placements": pv, "apps": apps_out,
        "movers": {"increasing": inc, "decreasing": dec, "steady": len(steady)},
        "alerts": {"counts": ac, "items": alerts_items,
                   "min_share": ALERT_MIN_SHARE, "min_usd": alert_min_usd, "floor": alert_floor},
        "deductions": {"rows": ded_rows, "avg_pct": round(sum(r["pct"] for r in ded_rows) / len(ded_rows), 3) if ded_rows else 0,
                       "at_risk_monthly": at_risk_monthly, "ivt_example": ivt_example,
                       "decay_example": {"place": pv[0]["name"] if pv else "—", "series": last_decay or [0]}},
        "mediation": {"summary": med_summary, "rows": med_rows, "by_app": mediation_by_app,
                      "suggestions": mediation.suggest(med_rows) if med_rows else []},
        "recommendations": {"total_uplift": 0, "items": recs, "root_cause": rec_root},
        "account_health": account_health_out,
        "accounts": [dict(account_id=a, label=a, connected=True, token="Valid",
                          apps=sorted(acct_apps.get(a, set())), last_sync="—") for a in accts],
        "countries": countries,
        "countries_by_app": countries_by_app,
        "countries_daily": countries_daily,   # per-app per-country daily counts → window to any range
        "country_tier": country_tier,
        "country_window": country_window,
        "today_date": today_str,          # the live/partial day (may be absent from data yet)
        "latest_complete": latest_all,    # newest FINISHED day — the "yesterday" anchor
    }
