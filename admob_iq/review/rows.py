"""Daily App Review — rows: one row per change the dashboard found for an app (uninstall / active / install value /
ad unit / app kamai, the Aaj page rules), merged (M4, M7) and tiered; plus the review-only rows (approved range,
kal drop, ads, deductions, mediation, setup / data, update verdicts).

Every alert is turned into its row inside its own try: a row that cannot be read marks only that app's feature as
unreadable (ctx.fail), never the day."""

import re
from collections import defaultdict
from datetime import date, timedelta

from .const import (ADS_CPI_UP, ADS_ROAS_DROP, ADS_ROAS_UP, ADUNIT_MIN_LOSS, ADUNIT_RED_DAYS, DED_AMB_PCT,
                    DED_AMB_USD, DED_RED_PCT, DED_RED_USD, DROP_DAYS, KAL_DROP_ABS, KAL_DROP_REL, MED_DROP_SHARE,
                    NAYA_DAYS, PURANA_DAYS, PURANI_HALAT_DAYS, RED_REV_ABS, RED_REV_REL, UPDATE_DAYS)
from .fmt import D, age_days, back_w, cap, days_back, fd, fr, gone_w, mon_lab, money, p100, pct, pct1k, rate_txt, umar, \
    umar_se, unit_word, usd2, usd_txt, users, ver_of
from .series import avg, cross_start, day_series, late_days, month_run, ret_weeks, un_weeks, walk_back


def _add(ctx, **r):
    r.setdefault("saath", None)
    r.setdefault("prov_on", None)
    r.setdefault("andaza", False)
    r.setdefault("opened", None)
    r.setdefault("release", None)
    r.setdefault("purani", False)
    r.setdefault("level", None)
    r.setdefault("shown", True)
    ctx.rows_all.append(r)
    return r


def new_row(ctx, aid, **kw):
    """A review-only row (its tier is given)."""
    r = dict(app=aid, saath=None, prov_on=None, andaza=False, opened=None, release=None, purani=False, level=None,
             shown=True, seeded=False, topic="T3", rel=0)
    r.update(kw)
    r["age"] = age_days(ctx, r["started"])
    r["status"] = "naya" if r["age"] <= NAYA_DAYS else "chal_raha"
    return r


def row_id(r):
    """A row's identity across days (kind · metric · ad unit · network · release) — the same problem on the next
    day's cards has the same id, whatever its numbers are."""
    rel = r.get("release") or {}
    return "|".join(str(x or "") for x in (r.get("kind"), r.get("metric"), r.get("unit_id") or r.get("unit"),
                                            r.get("net"), rel.get("date") or r.get("ver")))


def seen_first(ctx, aid, rid):
    """The first review day of the unbroken run of earlier snapshots that showed this row, or None (not shown on the
    latest earlier snapshot, or no history yet)."""
    a = ctx.apps.get(aid) or {}
    return (ctx.seen.get(a.get("key")) or {}).get(rid)


def observed(ctx, aid, kind, metric):
    """(start, 'Kab se' text) for a row whose real start date is unknown (a setup / account-health state): the first
    review day it was shown on (today if new; the go-live day at the earliest)."""
    first = seen_first(ctx, aid, row_id({"kind": kind, "metric": metric})) or ctx.day
    age = (ctx.day - first).days
    kab = f"{fd(ctx, first)} · {umar_se(age)}"
    if first <= ctx.go_live:
        kab += " (jab se ye page dekh raha hai)"
    return first, kab


def vs_text(vs):
    if vs and "prev" in vs:
        return "vs previous 4 weeks"
    return "vs all-time normal"


# ── rows from the dashboard's alerts (the Aaj page rules) ─────────────────────────────────────────
def build_rows(ctx):
    """All rows of all selected apps → ctx.rows_all / by_app / shown (M4 + M7 applied, every row tiered)."""
    ctx.rows_all = []
    _uninstall_rows(ctx)
    _active_rows(ctx)
    _info_rows(ctx)
    _pay_never_rows(ctx)
    _adunit_rows(ctx)
    _kamai_rows(ctx)
    ctx.by_app = defaultdict(list)
    for r in ctx.rows_all:
        ctx.by_app[r["app"]].append(r)
    for aid, rs in ctx.by_app.items():
        try:
            _dedupe(rs)
        except Exception:
            for f in ("uninstall", "active", "update"):
                ctx.fail(aid, f)
    for r in ctx.rows_all:
        try:
            r["tier"] = row_tier(ctx, r)
            r["age"] = age_days(ctx, r["started"])
            r["status"] = "naya" if r["age"] <= NAYA_DAYS else "chal_raha"
            if r["tier"] == "info" and r["age"] > PURANA_DAYS:
                r["status"] = "purana"
        except Exception:
            r["shown"] = False
            ctx.fail(r["app"], feat_of(r) or "setup")
    ctx.shown = {aid: [r for r in ctx.by_app.get(aid, []) if r["shown"]] for aid in ctx.apps}


def _uninstall_rows(ctx):
    for a in (ctx.db.get("uninstall") or {}).get("alerts") or []:
        aid = a.get("app_id") if isinstance(a, dict) else None
        if aid not in ctx.apps:
            continue
        try:
            _uninstall_row(ctx, a)
        except Exception:
            ctx.fail(aid, "update" if a.get("family") == "impact" else "uninstall")


def _uninstall_row(ctx, a):
    aid, fam = a["app_id"], a["family"]
    base = dict(app=aid, src="uninstall", sev=a["severity"], opened=a.get("opened"), andaza=bool(a.get("estimate")),
                seeded=a.get("opened") == ctx.first_run.get("impact" if fam == "impact" else "uninstall"), raw=a)
    if fam == "cohort":
        n = a["n"]
        up = a["dir"] == "up"
        wk = un_weeks(ctx, aid, n, a["installs_to"])
        shuru, capped = walk_back(wk, a["before"], a["now"])
        shuru = shuru or D(a["installs_from"])
        fact = f"{cap(gone_w(n))}: {p100(a['before'])}% → {p100(a['now'])}%"
        prov_on = None
        if a.get("provisional"):
            prov_on = D(a["installs_to"]) + timedelta(n + late_days(ctx, aid, "uninstall") + ctx.ga4_lag)
        period = f"Installs {fr(ctx, a['installs_from'], a['installs_to'])} · {vs_text(a.get('vs'))}"
        _add(ctx, **base, kind="cohort", metric=f"un_d{n}", n=n, topic="T1" if n <= 7 else "T2", up=up,
             started=shuru, capped=capped, fact=fact, period=period, prov_on=prov_on,
             vs_prev="prev" in (a.get("vs") or []), inst=(a["installs_from"], a["installs_to"]),
             before=a["before"], now=a["now"], rel=a["now"] / a["before"] - 1 if a["before"] else 0,
             users=a.get("users"))
    elif fam == "rate_drift":
        up = a["dir"] == "up"
        rel = a["now"] / a["before"] - 1 if a["before"] else 0
        fact = f"Uninstall rate {pct(rel, False)} {'badha' if up else 'kam hua'}"
        prov_on = (ctx.ga4_till + timedelta(late_days(ctx, aid, "uninstall") + ctx.ga4_lag)) if a.get("provisional") else None
        till = a.get("data_till") or ctx.ga4_till
        period = f"Daily avg {fr(ctx, a['since'], till)} · vs {fr(ctx, a['base_from'], a['base_to'])}"
        cnt = {}
        dl_ = (ctx.uapp.get(aid) or {}).get("daily") or {}
        if dl_.get("start") and dl_.get("un") and dl_.get("a28"):
            st_ = D(dl_["start"])

            def _med(f, t, key):
                xs = sorted(v for v in (dl_[key][i] for i in range((D(f) - st_).days, (D(t) - st_).days + 1)
                                        if 0 <= i < len(dl_[key])) if v is not None)
                return xs[len(xs) // 2] if xs else None
            cnt = {"count_b": _med(a["base_from"], a["base_to"], "un"), "count_n": _med(a["since"], till, "un"),
                   "a28_b": _med(a["base_from"], a["base_to"], "a28"), "a28_n": _med(a["since"], till, "a28")}
        flat = bool(up and cnt.get("count_b") and cnt.get("count_n") is not None and cnt["count_n"] <= cnt["count_b"] * 1.05
                    and cnt.get("a28_n") and cnt.get("a28_b") and cnt["a28_n"] < cnt["a28_b"] * 0.9)
        if flat:
            fact = f"Users ghate, isliye uninstall rate {pct(rel, False)} badha"
        _add(ctx, **base, kind="rate", metric="un_rate", topic="T2", up=up, started=D(a["since"]), fact=fact,
             saath=f"uninstall rate {pct1k(a['before'])} → {pct1k(a['now'])}",
             period=period, prov_on=prov_on, vs_prev=True, before=a["before"], now=a["now"], rel=rel,
             count_flat=flat, **cnt)
    elif fam == "impact":
        rel_ = a["release"]
        rows_ = (a.get("rows") or {})
        head = (rows_.get("worse") or rows_.get("better") or [None])[0]
        v = ver_of(rel_["label"])
        what = {"new_d1": back_w(1), "new_d7": back_w(7)}.get(head, gone_w(0))
        fact = f"{v} ke baad {what}: {p100(a['before'])}% → {p100(a['now'])}%"
        period = (f"Installs {fr(ctx, a['installs_from'], a['installs_to'])} · vs "
                  f"{fr(ctx, a['base_from'], a['base_to'])} (update se pehle)")
        _add(ctx, **base, kind="impact", metric={"new_d1": "ret_d1", "new_d7": "ret_d7"}.get(head, "un_d0"),
             head=head, topic="T1", level=a.get("level"), release=rel_, started=D(rel_["date"]), fact=fact,
             period=period, vs_prev=True, inst=(a["installs_from"], a["installs_to"]), before=a["before"],
             now=a["now"], rel=a.get("rel") or 0, users=a.get("users"))


def _active_rows(ctx):
    act = [a for a in (ctx.db.get("active") or {}).get("alerts") or [] if isinstance(a, dict)]
    drift_keys = {(a.get("app_id"), a.get("metric")) for a in act if a.get("family") == "act_drift"}
    slow = {(a.get("app_id"), a.get("metric")): a for a in act if a.get("family") == "act_slow"}
    for a in act:
        aid = a.get("app_id")
        if aid not in ctx.apps:
            continue
        try:
            _active_row(ctx, a, drift_keys, slow)
        except Exception:
            ctx.fail(aid, "active")


def _active_row(ctx, a, drift_keys, slow):
    aid, fam, m = a["app_id"], a["family"], a.get("metric")
    base = dict(app=aid, src="active", sev=a["severity"], opened=a.get("opened"), andaza=bool(a.get("estimate")),
                seeded=a.get("opened") == ctx.first_run.get("active"), raw=a)
    up = a["dir"] == "up"
    if fam in ("act_drift", "act_slow") and m == "ret_dau":
        if fam == "act_slow" and (aid, m) in drift_keys:
            return                                                   # M5: merged into the drift row
        rel = a.get("rel") or 0
        fact = f"Old users/day {pct(rel, False)} {'badhe' if up else 'kam'}: {users(a['before'])} → {users(a['now'])}"
        saath = None
        s = slow.get((aid, m))
        if fam == "act_slow" or (s and fam == "act_drift"):
            saath = "3 mahine se dheere-dheere"
        mm = re.search(r"naye installs bhi ([−+-]?\d+%)", a.get("text") or "")
        if mm and not saath:
            saath = f"naye installs bhi {mm.group(1)} (ads campaign?)"
        period = (f"Daily avg {fr(ctx, a['since'], a.get('data_till') or ctx.ga4_till)} · vs "
                  f"{fr(ctx, a['base_from'], a['base_to'])}")
        _add(ctx, **base, kind="act_drift", metric="ret_dau", topic="T2", up=up, started=D(a["since"]), fact=fact,
             saath=saath, period=period, vs_prev=True, before=a["before"], now=a["now"], rel=rel)
    elif fam == "act_drift" and m == "ads":
        rel = a.get("rel") or 0
        ar = ((ctx.aapp.get(aid) or {}).get("m") or {}).get("arpdau") or {}
        arel = ar.get("rel")
        win = (ctx.aapp.get(aid) or {}).get("win") or {}
        rel_ = a.get("release") if isinstance(a.get("release"), dict) else None
        period = (f"Daily avg {fr(ctx, a['since'], a.get('data_till') or ctx.ga4_till)} · vs "
                  f"{fr(ctx, a['base_from'], a['base_to'])}")
        if not up and arel is not None and arel > -0.05:                # N1: not a problem -> info line
            _add(ctx, **base, kind="n1", metric="ads", topic="T3", up=up, started=D(a["since"]), release=rel_,
                 fact=f"Ads per user {pct(rel, False)} kam, par revenue per user {pct(arel)} — nuksaan nahi",
                 period=period, vs_prev=True, before=a["before"], now=a["now"], rel=rel, n1=True,
                 sev_override="info")
        else:
            _add(ctx, **base, kind="act_ads", metric="ads", topic="T3", up=up, started=D(a["since"]), release=rel_,
                 fact=f"Ads per user {pct(rel, False)} {'zyada' if up else 'kam'}",
                 saath=(f"revenue per user {fr(ctx, win.get('from'), win.get('to'))}: {pct(arel)}" if arel is not None and win else None),
                 period=period, vs_prev=True, before=a["before"], now=a["now"], rel=rel)
    elif fam == "act_return":
        N = int(m[1:])
        wk = ret_weeks(ctx, aid, N, a["installs_to"])
        shuru, capped = walk_back(wk, a["before"], a["now"])
        shuru = shuru or D(a["installs_from"])
        fact = f"{cap(back_w(N))}: {p100(a['before'])}% → {p100(a['now'])}%"
        mm = re.search(r"installs ([−+-]?\d+)%", a.get("text") or "")
        saath = f"us hafte naye installs {mm.group(1).replace('-', '−')}% (ads campaign?)" if mm else None
        both = "dono" in (a.get("text") or "") or "pichhle 4 hafte" in (a.get("text") or "")
        period = (f"Installs {fr(ctx, a['installs_from'], a['installs_to'])} · vs "
                  f"{fr(ctx, a['base_from'], a['base_to'])} ke installs")
        _add(ctx, **base, kind="act_return", metric=f"ret_d{N}", topic="T1" if N <= 7 else "T2", up=up, started=shuru,
             capped=capped, fact=fact, saath=saath, period=period, vs_prev=both,
             inst=(a["installs_from"], a["installs_to"]), before=a["before"], now=a["now"],
             rel=(a["now"] / a["before"] - 1) if a["before"] else 0, users=a.get("users"))


def _info_rows(ctx):
    """Info lines from the Active users + Install value per-app files."""
    for aid in ctx.apps:
        try:
            f = ctx.afile(aid) or {}
            for r in ((f.get("changes") or {}).get("info") or []):
                st_ = D(r.get("from"))
                if not st_ or age_days(ctx, st_) > DROP_DAYS:
                    continue
                if r.get("kind") == "price":
                    fact = f"Ad rate {pct(r['rel'])} — ads per user wahi"
                elif r.get("kind") == "installs":
                    fact = f"Old users {pct(r['rel'])} — naye installs zyada aane se"
                else:
                    continue
                _add(ctx, app=aid, src="active", sev="info", kind="info", metric=r.get("metric"),
                     topic="T3" if r.get("kind") == "price" else "T2", started=st_, fact=fact,
                     period=f"{fr(ctx, r['from'], r['to'])}", opened=None, seeded=False)
        except Exception:
            ctx.fail(aid, "active")
        try:
            f = ctx.vfile(aid) or {}
            for r in ((f.get("changes") or {}).get("info") or []):
                k = r.get("kind")
                if k != "paid":
                    continue                                   # country mix / new-country / old version rows stay in the tab
                st_ = D(r.get("from"))
                if not st_ or age_days(ctx, st_) > DROP_DAYS:
                    continue
                fact = re.sub(r"\s—\s.*$", "", r["text"])
                _add(ctx, app=aid, src="value", sev="info", kind="val_info", metric=k, topic="T4", started=st_,
                     fact=fact, period=f"Installs {fr(ctx, r['from'], r['to'])}", opened=None, seeded=False)
        except Exception:
            ctx.fail(aid, "value")


def _pay_never_rows(ctx):
    for aid in ctx.apps:
        try:
            pay = (ctx.vapp.get(aid) or {}).get("pay") or {}
            if pay.get("st") == "never" and pay.get("pct365") is not None and pay.get("from"):
                _add(ctx, app=aid, src="value", sev="watch", kind="pay_never", metric="pay", topic="T4",
                     started=D(pay["from"]),
                     fact=f"Ads money not back in 1 year (~{pay['pct365']:.0f}% hi wapas)",
                     period=f"Installs {fr(ctx, pay['from'], pay['to'])} ka andaza", andaza=False, opened=None,
                     seeded=False, notier=True)
        except Exception:
            ctx.fail(aid, "value")


def _adunit_rows(ctx):
    for al in (ctx.db.get("alerts") or {}).get("items") or []:
        aid = ctx.name2id.get(al.get("app")) if isinstance(al, dict) else None
        if aid not in ctx.apps:
            continue
        try:
            _adunit_row(ctx, aid, al)
        except Exception:
            ctx.fail(aid, "deduct" if al.get("severity") == "critical" and al.get("kind") == "spike" else "kamai")


def _adunit_row(ctx, aid, al):
    y = ctx.admob_till
    last = y.isoformat()
    if al["severity"] == "critical" and al.get("kind") == "spike":
        mt = next((m for m in al["metrics"] if m["metric"] == "ctr"), al["metrics"][0])
        ctr = day_series(ctx, aid, "ctr", al["id"])
        mm = re.search(r"([\d.]+)% vs ([\d.]+)%", mt.get("message") or "")
        now_c, bef_c = (float(mm.group(1)) / 100, float(mm.group(2)) / 100) if mm else (mt["current"], None)
        if bef_c is None:
            bef_c = avg(ctr, days_back(y - timedelta(7), 14))
        shuru = cross_start(ctr, last, bef_c, now_c) or y
        clicks = day_series(ctx, aid, "clicks", al["id"])
        impr = day_series(ctx, aid, "impr", al["id"])
        bdays = days_back(shuru - timedelta(1), 7)
        adays = [x for x in days_back(y, 14) if x >= shuru.isoformat()]
        cb, ca = avg(clicks, bdays), avg(clicks, adays)
        ib, ia = avg(impr, bdays), avg(impr, adays)
        _add(ctx, app=aid, src="adunit", sev="critical", kind="ivt", metric="ctr", topic="T5", started=shuru,
             unit=al["place"], unit_id=al["id"],
             fact=f"{al['place']} pe clicks {round(ca / cb) if cb else '?'} guna — invalid click ka khatra",
             period=f"AdMob {fr(ctx, shuru, y)} · vs {fr(ctx, bdays[0], bdays[-1])}", before=bef_c, now=now_c,
             cb=cb, ca=ca, ib=ib, ia=ia, rel=(ca / cb - 1) if cb else 0, opened=None, seeded=False)
    elif al.get("kind") == "drop" and (al.get("lost") or 0) >= ADUNIT_MIN_LOSS:
        rev = day_series(ctx, aid, "rev", al["id"])
        mt = next((m for m in al["metrics"] if m["metric"] == "revenue"), None)
        bef, now_ = al["base_rev"], (mt or {}).get("current")
        shuru = cross_start(rev, last, bef, now_) or y
        bdays = days_back(shuru - timedelta(1), 7)
        adays = [x for x in days_back(y, 14) if x >= shuru.isoformat()]
        b_, a_ = avg(rev, bdays), avg(rev, adays)
        short, long_ = unit_word(al["place"])
        _add(ctx, app=aid, src="adunit", sev="warning", kind="unit_drop", metric="unit_rev", topic="T3", started=shuru,
             unit=al["place"], unit_id=al["id"], short=short, long=long_,
             fact=f"{short} ({al['place']}) ki kamai {money(b_, din=False)} → {money(a_)}",
             period=f"AdMob {fr(ctx, shuru, y)} · vs {fr(ctx, bdays[0], bdays[-1])}", before=b_, now=a_,
             rel=(a_ / b_ - 1) if b_ else 0, lost=b_ - a_, opened=None, seeded=False)


def _kamai_rows(ctx):
    for aid, a in ctx.apps.items():
        try:
            k7, kp = a["k7"], a["kp7"]
            if kp <= 0:
                continue
            rel = k7 / kp - 1
            ser = day_series(ctx, aid, "kamai")
            w7, p7 = ctx.w7, ctx.p7
            if rel <= -RED_REV_REL and kp - k7 >= RED_REV_ABS:
                shuru = cross_start(ser, ctx.admob_till.isoformat(), kp, k7, 14) or D(w7[0])
                _add(ctx, app=aid, src="adunit", sev="warning", kind="kamai_drop", metric="kamai", topic="T3",
                     started=shuru, fact=f"App ki kamai {pct(rel, False)} giri: {money(kp, din=False)} → {money(k7)}",
                     period=f"AdMob {fr(ctx, w7[0], w7[-1])} · vs {fr(ctx, p7[0], p7[-1])}", before=kp, now=k7,
                     rel=rel, opened=None, seeded=False)
            elif rel >= RED_REV_REL and k7 - kp >= RED_REV_ABS:
                shuru = cross_start(ser, ctx.admob_till.isoformat(), kp, k7, 14) or D(w7[0])
                _add(ctx, app=aid, src="adunit", sev="good", kind="kamai_up", metric="kamai", topic="T3",
                     started=shuru, fact=f"App ki kamai {pct(rel)}: {money(kp, din=False)} → {money(k7)}",
                     period=f"AdMob {fr(ctx, w7[0], w7[-1])} · vs {fr(ctx, p7[0], p7[-1])}", before=kp, now=k7,
                     rel=rel, opened=None, seeded=False)
        except Exception:
            ctx.fail(aid, "kamai")


def _dedupe(rs):
    # M4: update verdict + cohort row on the same metric with overlapping install weeks -> keep the update row
    for u in [r for r in rs if r["kind"] == "impact"]:
        for c in rs:
            if c["kind"] == "cohort" and c["metric"] == u["metric"] and c["shown"]:
                a0, a1 = D(u["inst"][0]), D(u["inst"][1])
                b0, b1 = D(c["inst"][0]), D(c["inst"][1])
                if a0 <= b1 and b0 <= a1:
                    c["shown"] = False
                    c["why_hidden"] = "M4 (same as update row)"
    # M7: same metric better AND worse within 14 days -> keep the newest window only
    grp = defaultdict(list)
    for r in rs:
        if r["shown"] and r["kind"] in ("cohort", "act_return"):
            grp[r["metric"]].append(r)
    for m, g in grp.items():
        if len({x["sev"] == "good" for x in g}) > 1:
            g.sort(key=lambda x: D(x["inst"][1]))
            newest = g[-1]
            for x in g[:-1]:
                if (D(newest["inst"][1]) - D(x["inst"][1])).days <= 14:
                    x["shown"] = False
                    x["why_hidden"] = "M7 (newer window shown)"


def row_tier(ctx, r):
    k, sev = r["kind"], r["sev"]
    if r.get("sev_override") == "info" or sev == "info":
        return "info"
    if k == "ivt":
        return "red"                                                               # R1
    if k == "impact":
        return {"halt": "red", "hold": "amber", "win": "green"}.get(r.get("level"), "info")   # R2
    if k == "kamai_drop":
        return "red"                                                               # R3
    if k == "kamai_up":
        return "green"
    if k == "unit_drop":
        app_bad = any(x["kind"] == "kamai_drop" for x in ctx.by_app[r["app"]])
        young = (ctx.admob_till - r["started"]).days + 1 < ADUNIT_RED_DAYS
        return "red" if (app_bad and not young) else "amber"
    if k == "rate" and r.get("count_flat"):
        return "amber"                          # more *share*, not more people: the user base shrank
    if sev == "warning":
        if r.get("vs_prev") and age_days(ctx, r["started"]) <= PURANI_HALAT_DAYS:
            return "red"                                                           # R4
        if age_days(ctx, r["started"]) > PURANI_HALAT_DAYS:
            r["purani"] = True                                                     # D6
        return "amber"
    if sev == "watch":
        return "amber"
    if sev == "good":
        if not r.get("vs_prev") and age_days(ctx, r["started"]) > PURANI_HALAT_DAYS:
            r["purani"] = True                 # mirror of D6: a months-old good level is not news
            return "info"
        return "green"
    return "info"


def feat_of(r):
    """The card feature a row belongs to (None: shown nowhere)."""
    k = r["kind"]
    if k == "ivt":
        return "deduct"
    if k in ("kamai_drop", "kamai_up", "unit_drop", "range"):
        return "kamai"
    if k in ("cohort", "rate"):
        return "uninstall"
    if k in ("act_drift", "act_return", "act_ads", "n1") or (k == "info" and r.get("src") == "active"):
        return "active"
    if k in ("impact", "upd"):
        return "update"
    if k == "ads":
        return "ads"
    if k == "med":
        return "mediation"
    if r.get("src") == "value":
        return "value"
    return None


def feature_of(r):
    """feat_of with the review's overrides (setup rows → setup; account-health IVT and deductions → deduct)."""
    return {"setup": "setup", "ah_ivt": "deduct", "ded": "deduct"}.get(r["kind"]) or feat_of(r)


# ── review-only rows ─────────────────────────────────────────────────────────────────────────────
def extra_rows(ctx):
    """Approved-range rows, ads (spend / ROAS / cost per install), deductions and mediation totals, and the
    pay_never re-dating — everything the review adds on top of the Aaj rows."""
    _range_rows(ctx)
    _ads_rows(ctx)
    _deductions(ctx)
    _mediation(ctx)
    _pay_never_redate(ctx)


def _range_rows(ctx):
    """kamai: approved-range alerts (range_alerts) on an ad unit — one row per unit, show rate first. now is the
    LAST COMPLETE MONTH's value; Shuru is walked back on the unit's monthly series (baseline.json units[].series)."""
    base = ctx.site.js("baseline.json", {})
    base = base if isinstance(base, dict) else {}
    ctx.bunit = {u["id"]: u for u in base.get("units") or [] if isinstance(u, dict) and u.get("id")}
    ctx.blast = (base.get("data_range") or {}).get("last")
    appr = ctx.site.js("approved_ranges.json", {})
    ctx.appr = ((appr if isinstance(appr, dict) else {}).get("placements") or {})
    ras = defaultdict(list)
    for ra in ctx.db.get("range_alerts") or []:
        if isinstance(ra, dict):
            ras[ra.get("id")].append(ra)
    for _uid, lst in ras.items():
        lst = sorted(lst, key=lambda x: 0 if x.get("metric") == "show" else 1)
        ra, more = lst[0], lst[1:]
        aid = ctx.name2id.get(ra.get("app"))
        if aid not in ctx.apps:
            continue
        try:
            ctx.extra[aid].append(_range_row(ctx, aid, ra, more))
        except Exception:
            ctx.fail(aid, "kamai")


# approved-range metrics (engine.approvals._METS): rates are shown as %, eCPM as money (the ₹/$ toggle)
RANGE_WORD = {"show": "ka show rate", "ctr": "pe click rate", "match": "ka match rate", "ecpm": "ka eCPM"}
RANGE_LABEL = {"show": "Show rate", "ctr": "Click rate", "match": "Match rate", "ecpm": "eCPM"}


def range_val(metric, v):
    return usd2(v) if metric == "ecpm" else f"{rate_txt(v)}%"


def range_span(metric, lo, hi):
    return f"{usd2(lo)}–{usd2(hi)}" if metric == "ecpm" else f"{rate_txt(lo)}%–{rate_txt(hi)}%"


def _range_row(ctx, aid, ra, ra_more):
    y = ctx.admob_till
    ys = y.isoformat()
    p = ctx.unit.get(ra["id"]) or {}
    lo, hi = ra["range"]
    now = ra["now"]
    below = now < lo
    edge = lo if below else hi
    m0, at_first = month_run(ctx, ra["id"], ra["metric"], lo, hi, below)
    shuru = date(int(m0[:4]), int(m0[5:7]), 1) if m0 else y
    yrow = next((r for r in p.get("daily") or [] if r[0] == ys), None)
    lost_usd, y_rate = None, None
    if yrow and ra["metric"] == "show" and yrow[4]:
        y_rate = yrow[2] / yrow[4]
    elif yrow and ra["metric"] == "ctr" and yrow[2]:
        y_rate = yrow[5] / yrow[2]
    if ra["metric"] == "show" and yrow and yrow[2] and yrow[4]:
        e, im, ma = yrow[1] / 1e6, yrow[2], yrow[4]
        lost_impr = ma * lo - im
        if lost_impr > 0:
            lost_usd = lost_impr * e / im
    short = unit_word(ra["place"])[0]
    word = f"{short} {RANGE_WORD.get(ra['metric'], RANGE_WORD['ctr'])}"
    ml = mon_lab(ctx, ctx.blast) if ctx.blast else "pichhle mahine"
    appr_at = ((ctx.appr.get(ra["id"]) or {}).get("metrics") or {}).get(ra["metric"], {}).get("approved_at")
    row = new_row(
        ctx, aid, src="adunit", kind="range", metric=ra["metric"], sev="watch", tier="amber", started=shuru,
        unit=ra["place"], unit_id=ra["id"],
        fact=f"{word} ({ra['place']}): {range_val(ra['metric'], now)}, range {range_span(ra['metric'], lo, hi)}",
        before=edge, now=now, lost_usd=lost_usd, y_rate=y_rate, word=word, lo=lo, hi=hi, month=ml,
        period=(f"AdMob mahine ka avg · {ml} me {range_val(ra['metric'], now)} · vs tumhari approved range"
                + (f" ({mon_lab(ctx, appr_at)} me approve)" if appr_at else "")),
        andaza=lost_usd is not None, rel=(now / edge - 1) if edge else 0,
        saath=("; ".join(f"{RANGE_LABEL.get(x['metric'], RANGE_LABEL['ctr'])} {ml} me {range_val(x['metric'], x['now'])} "
                         f"(range {range_span(x['metric'], x['range'][0], x['range'][1])})" for x in ra_more) or None))
    row["purani"] = row["age"] > PURANI_HALAT_DAYS
    row["kab"] = (f"{mon_lab(ctx, m0)} se · {umar_se(row['age'])} (har mahine range {'ke neeche' if below else 'ke upar'}"
                  f"{', jab se data hai' if at_first else ''})") if m0 else f"{fd(ctx, shuru)} · {umar_se(row['age'])}"
    return row


def _ads_rows(ctx):
    """ads: Google Ads spend / ROAS / cost per install, 7 days vs the 7 before (same days as the kamai tile)."""
    for aid, a in ctx.apps.items():
        try:
            _ads_row(ctx, aid, a)
        except Exception:
            ctx.ads.setdefault(aid, dict(sp=0.0, spp=0.0, i7=0, ip7=0, roas=None, roasp=None, cpi=None, cpip=None,
                                         camps=0, active=0, has=False))
            ctx.fail(aid, "ads")


def _ads_row(ctx, aid, a):
    w7, p7, y = ctx.w7, ctx.p7, ctx.admob_till
    e = ctx.ro.get(a["dname"]) or {}
    dl, ins = e.get("daily") or {}, e.get("installs_daily") or {}
    sp = sum(dl.get(x, 0) for x in w7) / 1e6 / 7
    spp = sum(dl.get(x, 0) for x in p7) / 1e6 / 7
    i7, ip7 = sum(ins.get(x, 0) for x in w7), sum(ins.get(x, 0) for x in p7)
    roas = (a["k7"] / sp) if sp >= 1 else None
    roasp = (a["kp7"] / spp) if spp >= 1 else None
    cpi = (sp * 7 / i7) if (sp >= 1 and i7 >= 50) else None
    cpip = (spp * 7 / ip7) if (spp >= 1 and ip7 >= 50) else None
    camps = e.get("campaigns") or []
    ctx.ads[aid] = dict(sp=sp, spp=spp, i7=i7, ip7=ip7, roas=roas, roasp=roasp, cpi=cpi, cpip=cpip,
                        camps=len(camps), active=sum(1 for c in camps if str(c.get("status")) == "ENABLED"),
                        has=bool(e))
    st, fact, met = None, None, None
    if spp >= 1 and sp < spp * 0.3:
        pass                                   # spend cut hard: ROAS/cost per install not comparable, told as a line
    elif roas is not None and roasp is not None and roas <= roasp * (1 - ADS_ROAS_DROP):
        st, met = "amber", "roas"
        fact = f"ROAS (revenue ÷ spend) {roasp:.2f} → {roas:.2f}"
    elif cpi is not None and cpip is not None and cpi >= cpip * (1 + ADS_CPI_UP):
        st, met = "amber", "cpi"
        fact = f"Cost per install {usd2(cpip)} → {usd2(cpi)}"
    elif roas is not None and roasp is not None and roas >= roasp * (1 + ADS_ROAS_UP):
        st, met = "green", "roas"
        fact = f"ROAS (revenue ÷ spend) {roasp:.2f} → {roas:.2f}"
    if not st:
        return
    # Shuru: walk back the DAILY series (ROAS = AdMob kamai / Google Ads kharcha; or kharcha / installs) while a day
    # sits on the 'now' side of the halfway point; one odd day in between is tolerated. 28 days max.
    days = days_back(y, 40)
    if met == "roas":
        ser = {x: ctx.rev[aid].get(x, 0) / (dl[x] / 1e6) for x in days if dl.get(x, 0) / 1e6 >= 1}
        b, n = roasp, roas
    else:
        ser = {x: (dl[x] / 1e6) / ins[x] for x in days if dl.get(x, 0) / 1e6 >= 1 and ins.get(x, 0) >= 20}
        b, n = cpip, cpi
    half, down = (b + n) / 2, n < b
    d, start, miss = y, None, 0
    for _ in range(28):
        v = ser.get(d.isoformat())
        if v is None:
            break
        if (v <= half) if down else (v >= half):
            start, miss = d, 0
        else:
            miss += 1
            if miss > 1 or start is None:
                break
        d -= timedelta(1)
    capped = start is not None and (y - start).days >= 27
    row = new_row(ctx, aid, src="ads", kind="ads", metric=met, sev="warning" if st == "amber" else "good",
                  tier=st, started=start or D(w7[0]), fact=fact,
                  period=f"Google Ads {fr(ctx, w7[0], w7[-1])} · vs {fr(ctx, p7[0], p7[-1])}",
                  rel=((roas / roasp - 1) if (roas and roasp) else 0), topic="T4")
    row["kab"] = (f"4+ weeks ({fd(ctx, row['started'])} se pehle se)" if capped else
                  f"{fd(ctx, row['started'])} · {umar_se(row['age'])}" + ("" if start else " (7 din ki tulna)"))
    ctx.extra[aid].append(row)


def _deductions(ctx):
    """deductions: AdMob's later revisions (hourly snapshots), last 14 observed days."""
    ded = ctx.site.js("deductions_daily.json", {})
    ded = ded if isinstance(ded, dict) else {}
    ctx.ded_dates = ded.get("dates") or []
    ctx.ded_win = set(range(max(0, len(ctx.ded_dates) - 14), len(ctx.ded_dates)))
    units = ded.get("units") or {}
    for uid, rows in (ded.get("data") or {}).items():
        u = units.get(uid) or {}
        aid = u.get("app_id") if u.get("app_id") in ctx.apps else ctx.name2id.get(u.get("app_name"))
        if aid not in ctx.apps:
            continue
        try:
            got = []
            for r in rows:
                if r[0] in ctx.ded_win and r[1] > r[2]:
                    got.append((u.get("unit_name") or uid, ctx.ded_dates[r[0]], r[1] / 1e6, (r[1] - r[2]) / 1e6))
            if got:
                x = ctx.deda.setdefault(aid, {"ded": 0.0, "units": [], "days": set()})
                for g in got:
                    x["ded"] += g[3]
                    x["days"].add(g[1])
                    x["units"].append(g)
        except Exception:
            ctx.fail(aid, "deduct")
    ctx.ded_from = ctx.ded_dates[min(ctx.ded_win)] if ctx.ded_win else None
    ctx.ded_to = ctx.ded_dates[max(ctx.ded_win)] if ctx.ded_win else None


def _mediation(ctx):
    """mediation: network shares, 7 days vs the 7 before, from mediation_daily.json."""
    medj = ctx.site.js("mediation_daily.json", {})
    medj = medj if isinstance(medj, dict) else {}
    dates = medj.get("dates") or []
    mi = {d: i for i, d in enumerate(dates)}
    names = medj.get("names") or {}
    for aid, a in ctx.apps.items():
        try:
            srcs = (medj.get("by_app") or {}).get(a["dname"])
            if not srcs:
                continue
            w, pw = {mi[x] for x in ctx.w7 if x in mi}, {mi[x] for x in ctx.p7 if x in mi}
            cur, prv, fill = {}, {}, {}
            for sid, rows in srcs.items():
                nm = names.get(sid, sid)
                if nm in ("0", ""):
                    continue
                rv = sum(r[1] for r in rows if r[0] in w)
                rp = sum(r[1] for r in rows if r[0] in pw)
                ma = sum(r[3] for r in rows if r[0] in w)
                rq = sum(r[4] for r in rows if r[0] in w)
                if rv > 0:
                    cur[nm] = rv
                    fill[nm] = (ma / rq) if rq else None
                if rp > 0:
                    prv[nm] = rp
            tc, tp = sum(cur.values()), sum(prv.values())
            if not tc:
                continue
            sh = {k: v / tc for k, v in cur.items()}
            shp = {k: v / tp for k, v in prv.items()} if tp else {}
            ctx.med[aid] = dict(sh=sh, shp=shp, fill=fill)
            for nm, s0 in shp.items():
                s1 = sh.get(nm, 0.0)
                if s0 >= MED_DROP_SHARE and s1 < s0 / 3:
                    ctx.extra[aid].append(new_row(
                        ctx, aid, src="mediation", kind="med", metric="share", sev="watch", tier="amber",
                        started=D(ctx.w7[0]), fact=f"{nm} ka kamai me hissa {s0 * 100:.0f}% → {s1 * 100:.0f}%",
                        period=f"AdMob mediation {fr(ctx, ctx.w7[0], ctx.w7[-1])} · vs {fr(ctx, ctx.p7[0], ctx.p7[-1])}",
                        net=nm, rel=(s1 / s0 - 1)))
        except Exception:
            ctx.med.pop(aid, None)
            ctx.fail(aid, "mediation")


def _pay_never_redate(ctx):
    """value 'paisa 1 saal me wapas nahi' (pay_never): dated at the judged install week it reads as 'N din se';
    walk back the value file's install weeks (newest first) while each week was also 'never'."""
    for aid in ctx.apps:
        for r in ctx.shown.get(aid, []):
            if r["kind"] != "pay_never":
                continue
            try:
                wk = (ctx.vfile(aid) or {}).get("weeks") or []
                pay = (ctx.vapp.get(aid) or {}).get("pay") or {}
                i0 = next((i for i, w in enumerate(wk) if w.get("from") == pay.get("from")), None)
                start, at_first, j = D(pay.get("from")), False, None
                if i0 is not None:
                    j = i0
                    while j < len(wk) and (wk[j].get("pay") or {}).get("never"):
                        start = D(wk[j]["from"])
                        j += 1
                    at_first = j >= len(wk) or not wk[j].get("pay")
                r["started"] = start
                r["age"] = age_days(ctx, start)
                r["status"] = "naya" if r["age"] <= NAYA_DAYS else "chal_raha"
                r["purani"] = r["age"] > PURANI_HALAT_DAYS
                r["kab"] = f"Installs {fd(ctx, start)} se · {umar_se(r['age'])}" + (" (jab se data hai)" if at_first else "")
                r["weeks_never"] = (i0 is not None) and (j - i0)
            except Exception:
                r["shown"] = False
                ctx.fail(aid, "value")
        ctx.shown[aid] = [r for r in ctx.shown.get(aid, []) if r["shown"]]


# ── per-app rows (built inside the app's own try) ────────────────────────────────────────────────
def setup_rows(ctx, aid, a):
    rs = []
    day = ctx.day
    acc = ctx.acct.get(a["acc"]) or {}
    def seen_row(metric, **kw):              # no real start date: "Kab se" = the first review day that showed it
        st_, kab = observed(ctx, aid, "setup", metric)
        r_ = new_row(ctx, aid, src="setup", kind="setup", metric=metric, started=st_, **kw)
        r_["kab"] = kab
        return r_

    if acc and acc.get("token") not in (None, "Valid"):
        rs.append(seen_row("token", sev="warning", tier="red",
                           fact=f"AdMob account ka login token: {acc.get('token')}", period="Accounts"))
    if aid in ctx.no_ga4:
        if a.get("launch"):
            rs.append(new_row(ctx, aid, src="setup", kind="setup", metric="ga4", sev="watch", tier="amber",
                              started=D(a["launch"]), purani=True, fact="GA4 me is app ka Android stream nahi mila",
                              period="GA4 accounts"))
        else:
            rs.append(seen_row("ga4", sev="watch", tier="amber", purani=True,
                               fact="GA4 me is app ka Android stream nahi mila", period="GA4 accounts"))
    stale = [s for s, x in (("Active users", ctx.aapp.get(aid)), ("Uninstall", ctx.ud.get(aid))) if x and x.get("stale")]
    if stale:
        rs.append(seen_row("stale", sev="watch", tier="amber",
                           fact=f"{' aur '.join(stale)} ka data purana (naya nahi aaya)", period="GA4"))
    y, us = ctx.kal[aid]
    if y <= 0 and us >= 1:
        rs.append(new_row(ctx, aid, src="setup", kind="setup", metric="admob0", sev="watch", tier="amber",
                          started=ctx.admob_till,
                          fact=f"Yesterday ({fd(ctx, ctx.admob_till)}) ka AdMob data 0 — usual {usd_txt(us)}/day",
                          period=f"AdMob {fd(ctx, ctx.admob_till)}"))
    # GA4 logs the ad revenue ~2x (value engine: GA4 / AdMob >= 1.5 for 8+ weeks -> scale.double). Shuru = walk back
    # the weekly AdMob/GA4 factor (k_weeks, oldest first) while <= 1/1.5. GA4 far above AdMob (≥ 5x) is not double
    # logging: the app's ads run in an AdMob account the dashboard does not have ("AdMob me lagbhag nahi").
    vf = ctx.vfile(aid) or {}
    sc = vf.get("scale") or {}
    if sc.get("double"):
        kw = sc.get("k_weeks") or []
        i = len(kw) - 1
        while i >= 0 and kw[i][1] and kw[i][1] <= 1 / 1.5:
            i -= 1
        st_ = D(kw[i + 1][0]) if i + 1 < len(kw) else day
        m_ = re.search(r"AdMob ki (?:kamai|revenue) ka (\d+)%", " ".join(sc.get("text") or []))
        ratio = int(m_.group(1)) / 100 if m_ else None
        how = (f"AdMob ka {ratio * 100:.0f}%" if ratio and ratio < 5 else f"AdMob se {ratio:.0f} guna" if ratio
               else "AdMob se kaafi zyada")
        big = bool(ratio and ratio >= 5)
        fact = (f"GA4 me ad kamai hai par AdMob me lagbhag nahi ({how})" if big
                else f"GA4 me ad kamai shayad 2 baar log ho rahi ({how})")
        r_ = new_row(ctx, aid, src="setup", kind="setup", metric="admob_gap" if big else "double", sev="watch",
                     tier="amber", started=st_, fact=fact, ratio=ratio,
                     period=(f"GA4 vs AdMob revenue · weeks {fd(ctx, kw[i + 1][0]) if i + 1 < len(kw) else '?'}–"
                             f"{fd(ctx, D(kw[-1][0]) + timedelta(6)) if kw else '?'}"))
        r_["purani"] = r_["age"] > PURANI_HALAT_DAYS
        r_["kab"] = f"{fd(ctx, st_)} · {umar_se(r_['age'])}" + (" (jab se data hai)" if i < 0 else "")
        r_["snz_ph"] = ("Jaise: is app ke ads dusre AdMob account se chalte hain — pata hai" if big
                        else "Jaise: ye app ad_impression 2 baar log karta hai — pata hai, developer fix kar raha")
        rs.append(r_)
    return rs


def deduct_rows(ctx, aid):
    rs = []
    h = ctx.ah.get(aid) or {}
    if h and h.get("ivt") not in (None, "clean"):
        st_, kab = observed(ctx, aid, "ah_ivt", "ivt")
        r_ = new_row(ctx, aid, src="health", kind="ah_ivt", metric="ivt", sev="warning", tier="red",
                     started=st_, fact=f"Account health: invalid traffic '{h.get('ivt')}'", period="Account health")
        r_["kab"] = kab
        rs.append(r_)
    dd = ctx.deda.get(aid)
    if dd:
        worst = max(dd["units"], key=lambda u: (u[3] / u[2]) if u[2] else 0)
        wp = worst[3] / worst[2] if worst[2] else 0
        rv = sum(ctx.rev[aid].get(x, 0) for x in ctx.ded_dates[min(ctx.ded_win):])
        ap = dd["ded"] / rv if rv else 0
        per = f"Deductions {fr(ctx, ctx.ded_from, ctx.ded_to)}"
        if wp >= DED_RED_PCT and worst[3] >= DED_RED_USD:
            rs.append(new_row(ctx, aid, src="deduct", kind="ded", metric="ded", sev="warning", tier="red",
                              started=D(worst[1]),
                              fact=f"{worst[0]} ki {fd(ctx, worst[1])} ki kamai baad me {wp * 100:.0f}% kaati gayi",
                              period=per, ded=dd["ded"], ap=ap, rv=rv))
        elif wp >= DED_RED_PCT and worst[3] >= DED_AMB_USD:
            rs.append(new_row(ctx, aid, src="deduct", kind="ded", metric="ded", sev="watch", tier="amber",
                              started=D(worst[1]),
                              fact=f"{worst[0]} ki {fd(ctx, worst[1])} ki kamai baad me {wp * 100:.0f}% kaati gayi",
                              period=per, ded=dd["ded"], ap=ap, rv=rv))
        elif ap >= DED_AMB_PCT and dd["ded"] >= DED_AMB_USD:
            rs.append(new_row(ctx, aid, src="deduct", kind="ded", metric="ded", sev="watch", tier="amber",
                              started=D(worst[1]), fact=f"AdMob ne baad me kamai ka {ap * 100:.1f}% kaata",
                              period=per, ded=dd["ded"], ap=ap, rv=rv))
    return rs


def upd_rows(ctx, aid, have):
    """A judged update verdict (halt / hold / win) that has no alert row gets its own row."""
    if any(r["kind"] == "impact" for r in have):
        return []
    ups = [u for u in ((ctx.uapp.get(aid) or {}).get("impact") or {}).get("updates") or []
           if age_days(ctx, u["date"]) <= UPDATE_DAYS]
    if not ups:
        return []
    u = max(ups, key=lambda x: x["date"])
    vd = u.get("verdict") or {}
    lv = vd.get("level")
    if vd.get("early") or lv not in ("halt", "hold", "win"):
        return []
    v = ver_of(u["label"])
    v = f"{fd(ctx, u['date'])} wala update" if v == "App update" else v
    why = re.sub(r"\s*—\s*.*$", "", vd.get("why") or "").strip()
    fact = {"halt": f"{v} ke baad bigda — 🛑 Stop update", "hold": f"{v} ke baad kuch bigda — ⚠️ Wait and check",
            "win": f"✅ {v} update went well"}[lv]
    return [new_row(ctx, aid, src="impact", kind="upd", metric=lv, level=lv, sev="warning" if lv == "halt" else "watch",
                    tier={"halt": "red", "hold": "amber", "win": "green"}[lv], started=D(u["date"]), fact=fact, ver=v,
                    why=(why[0].upper() + why[1:]) if why else "",
                    period=f"Update impact · {v} ({fd(ctx, u['date'])}) · pehle vs baad ke installs")]


def kal_drop_rows(ctx, aid, rows):
    """kamai: a sudden drop yesterday vs usual (only if nothing else on kamai is red/amber)."""
    y, us = ctx.kal[aid]
    if ((us - y) >= KAL_DROP_ABS and us > 0 and (y / us - 1) <= -KAL_DROP_REL
            and not any(feat_of(r) == "kamai" and r["tier"] in ("red", "amber") for r in rows)):
        u7 = ctx.u7
        return [new_row(ctx, aid, src="adunit", kind="kal_drop", metric="kamai", sev="watch", tier="amber",
                        started=ctx.admob_till,
                        fact=f"Yesterday ({fd(ctx, ctx.admob_till)}) ki kamai usual se {pct(y / us - 1, False)} kam",
                        before=us, now=y, period=f"AdMob {fd(ctx, ctx.admob_till)} · vs {fr(ctx, u7[0], u7[-1])} ka avg",
                        rel=y / us - 1)]
    return []


def app_rows(ctx, aid):
    """Every row of one app, as the card reads them (the Aaj rows + the review-only rows)."""
    a = ctx.apps[aid]
    rows = list(ctx.shown.get(aid, [])) + list(ctx.extra.get(aid, []))
    for feat, fn in (("setup", lambda: setup_rows(ctx, aid, a)), ("deduct", lambda: deduct_rows(ctx, aid))):
        try:
            rows += fn()
        except Exception:
            ctx.fail(aid, feat)
    try:
        rows += upd_rows(ctx, aid, rows)
    except Exception:
        ctx.fail(aid, "update")
    try:
        rows += kal_drop_rows(ctx, aid, rows)
    except Exception:
        ctx.fail(aid, "kamai")
    return rows
