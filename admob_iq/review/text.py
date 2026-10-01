"""Daily App Review — the texts of a card (Hinglish sentences, English metric names and short labels): the 5 answers
(what happened · since when · how big · new or old · next step), the one-line fallbacks of normal features, good-news
lines. Plain strings with money tokens (fmt.money), never HTML."""

import re
from datetime import timedelta

from .const import MON, TIER_RANK, UPDATE_DAYS
from .fmt import (D, age_days, back_w, cap, fd, fr, gone_w, mon_lab, money, p100, pct, pct1k, rate_txt, umar, umar_se,
                  unit_word, usd2, users, ver_of)
from .rows import row_id, seen_first
from .series import day_series, ecpm, rel_near, rel_update


def pakka_txt(ctx, on):
    return f"⏳ Not final · final on {fd(ctx, on)}"


def kis_data(ctx, r):
    t = r["period"]
    if r.get("andaza"):
        t += " · ≈ Andaza"
    if r.get("prov_on"):
        t += " · " + pakka_txt(ctx, r["prov_on"])
    return t


def kab_se(ctx, r):
    aid = r["app"]
    s = r["started"]
    pre = "Installs " if r["kind"] in ("cohort", "act_return") else ""
    base = f"{pre}{fd(ctx, s)} se" if pre else fd(ctx, s)
    if r.get("capped"):
        base = "6+ months ago"                       # (its own age would only repeat it: "6+ months ago" alone)
    t = base if r.get("capped") else f"{base} ({umar(r['age'])})"
    u = r.get("release") or rel_update(ctx, aid, s, 3)
    if u:
        v = ver_of(u["label"])
        v = "update" if v == "App update" else v
        t += f" · {v} usi din aaya" if D(u["date"]) == D(s) else f" · {v} {fd(ctx, u['date'])} ko aaya"
    else:
        u = rel_near(ctx, aid, s, 14)
        if u:
            v = ver_of(u["label"])
            v = "update" if v == "App update" else v
            t += f" · {v} {fd(ctx, u['date'])} ko aaya ({(D(s) - D(u['date'])).days} din pehle)"
    if r["kind"] == "impact":
        newer = [x for x in (ctx.ud.get(aid) or {}).get("updates") or [] if x["date"] > r["release"]["date"]]
        if newer:
            nv = max(newer, key=lambda x: x["date"])
            t += f" · {ver_of(nv['label'])} {fd(ctx, nv['date'])} ko aaya"
    return t


def app_size_txt(ctx, aid):
    a = ctx.apps[aid]
    if a["spend"] >= 1:
        return f"Kamai {money(a['k7'])} + ads kharcha {money(a['spend'])} (7 din ka avg)"
    return f"Kamai {money(a['k7'])} (7 din ka avg) · ads kharcha nahi"


def per_user(v):
    """A per-1,000-users count (ads) → per user: 3,213 → "3.2", 450 → "0.45"."""
    x = v / 1000
    return (f"{x:.1f}" if x >= 1 else f"{x:.2f}").rstrip("0").rstrip(".")


def kitna(ctx, r):
    aid, k = r["app"], r["kind"]
    if k == "ivt":
        ir = (r["ia"] / r["ib"] - 1) if r.get("ib") else 0
        ads = "ads dikhe utne hi" if abs(ir) < 0.2 else f"ads dikhe {pct(ir)}"
        return f"Clicks roz ~{r['cb']:,.0f} → ~{r['ca']:,.0f} · {ads}"
    if k in ("kamai_drop", "kamai_up"):
        return f"Revenue {money(r['before'], din=False)} → {money(r['now'])} ({money(r['now'] - r['before'], sign=True)})"
    if k == "unit_drop":
        tr = ctx.app_total_rel[aid]
        w7, p7 = ctx.w7, ctx.p7
        return (f"Roz {money(-r['lost'])} · par poori app ki kamai {'phir bhi ' if tr >= 0 else 'sirf '}{pct(tr)} "
                f"({fr(ctx, w7[0], w7[-1])} vs {fr(ctx, p7[0], p7[-1])})")
    if k == "impact":
        n_ = r.get('users') or 0
        dd = n_ * abs(r['now'] - r['before'])
        if r["metric"].startswith("ret"):
            verb = "kam wapas aaye" if r["now"] < r["before"] else "zyada wapas aaye"
        else:
            verb = "zyada ne app hataya" if r["now"] > r["before"] else "kam ne app hataya"
        return f"{n_:,} naye users me se ~{dd:,.0f} {verb}"
    if k in ("cohort", "act_return"):
        extra = (r.get("users") or 0) * abs(r["now"] - r["before"])
        if r.get("purani"):
            return f"{r.get('users') or 0:,} installs me se ~{(r.get('users') or 0) * r['now']:,.0f} ne us din app hataya"
        if k == "cohort":
            word = "zyada ne app hataya" if r["up"] else "kam ne app hataya"
        else:
            word = "zyada wapas aaye" if r["up"] else "kam wapas aaye"
        return f"{r.get('users') or 0:,} installs me se ~{extra:,.0f} log {word}"
    if k == "rate":
        if r.get("count_flat"):
            return (f"Roz hataane wale ~{r['count_b']:,.0f} → ~{r['count_n']:,.0f} log (ginti nahi badhi) · "
                    f"mahine ke active users ~{users(r['a28_b'])} → ~{users(r['a28_n'])}")
        if r.get("count_b") is not None and r.get("count_n") is not None:
            return (f"Uninstall rate: roz ~{r['count_b']:,.0f} ({pct1k(r['before'])}) → ~{r['count_n']:,.0f} "
                    f"({pct1k(r['now'])}) users")
        return f"Uninstall rate {pct1k(r['before'])} → {pct1k(r['now'])}"
    if k == "act_drift":
        return f"Roz {users(r['before'])} → {users(r['now'])} old users"
    return ""


def abhi(ctx, r, story):
    """-> (the 'Abhi' line or None, the newer row it tells about or None)"""
    k = r["kind"]
    ga4 = ctx.ga4_till
    y = ctx.admob_till
    dev = [x for x in story["rows"] if x is not r and x["kind"] in ("cohort", "act_return", "rate")
           and k in ("impact", "cohort", "act_return", "rate") and TIER_RANK[x["tier"]] >= 3
           and x["started"] > r["started"]]
    if dev:
        x = sorted(dev, key=lambda x: x["started"])[-1]
        t = ("🆕 " if x["status"] == "naya" else "") + "Aur bigda: " + x["fact"][0].lower() + x["fact"][1:]
        if x.get("inst"):
            t += f" · installs {fr(ctx, *x['inst'])}"
        if x.get("prov_on"):
            t += " · ⏳ Not final"
        return t, x
    if k == "rate" and r["up"]:
        dl = (ctx.uapp.get(r["app"]) or {}).get("daily") or {}
        rt_ = dl.get("rate") or []
        if dl.get("start") and rt_:
            st = D(dl["start"])
            last3 = [rt_[i] for i in ((ga4 - timedelta(j) - st).days for j in (2, 1, 0))
                     if 0 <= i < len(rt_) and rt_[i] is not None]
            if len(last3) == 3:
                a3 = sum(last3) / 3
                if a3 > r["now"] * 1.15:
                    return f"Hissa aur badh raha: {fr(ctx, ga4 - timedelta(2), ga4)} me uninstall rate ~{pct1k(a3)}", None
                if a3 < r["now"] * 0.85:
                    return f"Sudhar raha: {fr(ctx, ga4 - timedelta(2), ga4)} me uninstall rate ~{pct1k(a3)}", None
        return None, None
    if k in ("ivt", "unit_drop", "kamai_drop"):
        ndays = (y - r["started"]).days + 1
        if k == "unit_drop" and ndays <= 2:
            return f"Sirf {ndays} din ka data — kal phir dekho", None
        if k == "ivt":
            ser = day_series(ctx, r["app"], "clicks", r["unit_id"])
            v0, v1 = ser.get(r["started"].isoformat()), ser.get(y.isoformat())
            if v0 and v1 and v1 > v0 * 1.1:
                return f"Aur bigad raha: clicks {v0:,.0f} ({fd(ctx, r['started'])}) → {v1:,.0f} ({fd(ctx, y)})", None
            return f"Waisa hi: {fd(ctx, y)} ko {v1:,.0f} clicks", None
        ser = day_series(ctx, r["app"], "kamai") if k == "kamai_drop" else day_series(ctx, r["app"], "rev", r["unit_id"])
        last = ser.get(y.isoformat()) or 0
        if last < r["now"] * 0.9:
            return f"Aur gir raha: {fd(ctx, y)} ko sirf {money(last, din=False)}", None
        if last > r["now"] * 1.1:
            return f"Sudhar raha: {fd(ctx, y)} ko {money(last, din=False)}", None
        return f"Waisa hi: {fd(ctx, y)} ko {money(last, din=False)}", None
    return None, None


def headline(ctx, r, story):
    aid, k = r["app"], r["kind"]
    u = r.get("release") or rel_update(ctx, aid, r["started"], 3)
    v = ver_of(u["label"]) if u else None
    pre = f"{v} ke baad " if (v and v != "App update") else ""
    if k == "ivt":
        x = round(r["ca"] / r["cb"]) if r.get("cb") else "kai"
        return f"Ek {unit_word(r['unit'])[0].lower()} pe clicks achanak {x} guna — invalid click ka khatra"
    if k == "kamai_drop":
        return f"{pre}app ki kamai {pct(r['rel'], False)} giri".capitalize() if not pre else f"{pre}app ki kamai {pct(r['rel'], False)} giri"
    if k == "impact":
        return r["fact"]
    if k == "unit_drop":
        if r["rel"] <= -0.9:
            return f"{pre}{r['short'].lower()} ki kamai lagbhag band: {money(r['before'], din=False)} → {money(r['now'])}"
        return f"{pre}{r['short']} ki kamai {money(r['before'], din=False)} → {money(r['now'])}"
    if k == "cohort":
        what = cap(gone_w(r["n"]))
        if r.get("purani"):
            return f"{what}: {p100(r['now'])}% — {MON[r['started'].month - 1]} se aisa hi"
        return f"{what}: {p100(r['before'])}% → {p100(r['now'])}%"
    if k == "rate":
        if r.get("count_flat"):
            return r["fact"]
        return f"Uninstall rate {pct(r['rel'], False)} {'badha' if r['up'] else 'kam hua'}"
    return r["fact"]


def kya_karo(ctx, r, story):
    aid, k = r["app"], r["kind"]
    u = r.get("release") or rel_update(ctx, aid, r["started"], 3)
    v = ver_of(u["label"]) if u else None
    if v == "App update":
        v = f"{fd(ctx, u['date'])} wale update"
    if k == "ivt":
        return f"{v or 'App'} me {r['unit']} kahan hai dekho; samajh na aaye to AdMob me ye ad unit pause karo."
    if k == "unit_drop":
        return f"{v + ' me ' if v else 'AdMob me '}{r['unit']} ad check karo (load hota hai? floor price?)."
    if k == "kamai_drop":
        ud = [x for x in ctx.by_app[aid] if x["kind"] == "unit_drop"]
        if ud:
            return f"{v + ' me ' if v else ''}{ud[0]['long']} ({ud[0]['unit']}) check karo; tab tak ads budget mat badhao."
        return f"{v or 'Pichhle update'} ke baad kya badla dekho; tab tak ads budget mat badhao."
    if k == "impact" and r.get("level") == "halt":
        newer = [x for x in (ctx.ud.get(aid) or {}).get("updates") or [] if x["date"] > r["release"]["date"]]
        if newer:
            nv = max(newer, key=lambda x: x["date"])
            ro = None
            for up in ((ctx.uapp.get(aid) or {}).get("impact") or {}).get("updates") or []:
                if up["key"] == nv["key"]:
                    ro = (up.get("verdict") or {}).get("ready_on")
            hint = " (pehla level, tutorial, pehla ad)" if r["metric"] == "ret_d1" else ""
            return f"{v} me jo badla{hint} wapas lo. {ver_of(nv['label'])} ka result {fd(ctx, ro) if ro else 'jald'}."
        return "Rollout stop karo, fix wala update bhejo."
    if k == "rate" and r.get("count_flat"):
        note = ((ctx.vapp.get(aid) or {}).get("pay") or {}).get("note") or ""
        m_ = re.match(r"(\d+ \w{3}(?: \d{4})?) se Google Ads (?:kharcha|spend) nahi", note)
        tail = f" {m_.group(1)} se is app pe Google Ads band hai." if m_ else ""
        return f"Hataane wale nahi badhe, users kam ho rahe hain — naye users laane ka plan dekho.{tail}"
    if r.get("purani"):
        mw = gone_w(0) if r.get("n") == 0 else "app hataana"
        return f"Old issue — jaldi nahi. Agle update me {mw} sudhaarne ka plan rakho."
    if story["topic"] == "T1":
        return f"{fd(ctx, r['started'])} ke aas-paas campaign, country ya update me kya badla, dekho."
    if story["topic"] == "T2":
        return f"{fd(ctx, r['started'])} ke aas-paas notification ya ads badle? Us update ke reviews dekho."
    if story["topic"] == "T4":
        return "Is campaign ka budget mat badhao jab tak paisa wapas aane ke din saaf na ho."
    return "Detail tab me dekho."


def good_text(ctx, r):
    k = r["kind"]
    if k == "impact":
        v = ver_of(r["release"]["label"])
        what = {"new_d1": back_w(1), "new_d7": back_w(7)}.get(r.get("head"), gone_w(0))
        return f"✅ {v} update went well: {what} {p100(r['before'])}% → {p100(r['now'])}%"
    if k == "kamai_up":
        return f"revenue {pct(r['rel'])}"
    if k == "act_drift":
        return f"old users/day {pct(r['rel'])}"
    if k == "rate":
        return f"uninstall rate {pct(r['rel'], False)} kam"
    if k == "cohort":
        return f"{gone_w(r['n'])} {p100(r['before'])}% → {p100(r['now'])}%"
    return r["fact"]


def first_shown(ctx, rows):
    """'Naya ya purana → Pehli baar dikha'. A dashboard alert carries its own 'opened' date. Anything else: the first
    review day of the unbroken run of snapshots that showed the same row (ctx.seen, from the store's history) — only
    the go-live day says '(jab ye page shuru hua)', a row new on this day says '(aaj)'."""
    ops = [x for x in rows if x.get("opened")]
    if not ops:
        firsts = [f for f in (seen_first(ctx, x["app"], row_id(x)) for x in rows) if f]
        first = min(firsts) if firsts else ctx.day
        if first <= ctx.go_live:
            return f"{fd(ctx, ctx.go_live)} (jab ye page shuru hua)"
        return fd(ctx, first) + (" (today)" if first >= ctx.day else "")
    x = min(ops, key=lambda x: x["opened"])
    return fd(ctx, x["opened"]) + (" (jab ye feature shuru hua)" if x.get("seeded") else "")


def q_extra(ctx, r, a):
    """The 5 answers for the rows the review adds (range / ads / med / kal-drop / setup / deductions / update)."""
    k, aid = r["kind"], r["app"]
    y = ctx.admob_till
    if k == "range" and r["metric"] in ("ecpm", "match"):
        if r["metric"] == "ecpm":
            kit = (f"{r['month']} me eCPM {usd2(r['now'])} vs range {usd2(r['lo'])}–{usd2(r['hi'])}"
                   + (" (range se upar — kamai ke liye achha)" if r["now"] > r["hi"] else ""))
            karo = ("Range dobara approve karo agar ye naya normal hai; agle mahine phir dekho."
                    if r["now"] > r["hi"] else f"AdMob me {r['unit']} ka floor price aur mediation check karo.")
        else:
            kit = f"{r['month']} me {rate_txt(r['now'])}% vs range {rate_txt(r['lo'])}%–{rate_txt(r['hi'])}%"
            karo = f"AdMob me {r['unit']} ki ad requests aur fill check karo."
        return dict(kya=r["fact"], kit=kit, karo=karo, saath=r.get("saath"))
    if k == "range":
        yr = f"Yesterday ({fd(ctx, y)}) {rate_txt(r['y_rate'])}%" if r.get("y_rate") is not None else ""
        if r.get("lost_usd"):
            kit = (f"{yr} dikhe; {rate_txt(r['lo'])}% dikhte to ≈ {money(r['lost_usd'], din=False)} zyada kamai hoti · "
                   f"≈ Andaza")
        else:
            kit = ((yr + " · " if yr else "") + f"{r['month']} me {rate_txt(r['now'])}% vs range "
                   f"{rate_txt(r['lo'])}%–{rate_txt(r['hi'])}%")
        if r["metric"] == "show":
            karo = f"{r['unit']} kyun kam dikh raha, developer se check karao (ad ka wait time / timeout)."
            if r.get("purani"):
                karo = (f"{mon_lab(ctx, r['started'].isoformat()[:7])} se aisa hi — developer se {r['unit']} ka wait "
                        f"time check karao, ya range dobara approve karo.")
        else:
            karo = f"{r['unit']} pe clicks ka pattern AdMob me dekho; galti se click to nahi?"
        return dict(kya=r["fact"], kit=kit, karo=karo, saath=r.get("saath"))
    if k == "setup":
        m = r["metric"]
        if m == "double":
            kit = (f"GA4 wale kamai ke number (Install value, ROAS) ~{r['ratio']:.1f} guna; dashboard unhe AdMob ke "
                   f"hisaab se ghatata hai (≈)" if r.get("ratio") and r["ratio"] < 5 else
                   "GA4 wale kamai ke number bharose layak nahi; dashboard AdMob ke hisaab se ghatata hai (≈)")
            karo = ("Developer se check karao: ad_impression Firebase link aur app ka apna code, dono se to nahi ja "
                    "raha? Ek hi rakho.")
        elif m == "admob_gap":
            kit = ("GA4 wale kamai ke number (Install value, ROAS) is app ke liye bharose layak nahi; dashboard AdMob "
                   "ke hisaab se ghatata hai (≈)")
            karo = ("Check karo: app me kaunsa AdMob app ID laga hai — kya wo dashboard wale AdMob account me hai? "
                    "Nahi to wo account jodo.")
        elif m == "ga4":
            kit = "Is app ka Uninstall, Active users aur Install value ka data nahi"
            karo = "GA4 me is app ka Android data stream jodo (Firebase project link)."
        elif m == "token":
            kit = "Is account ki sab apps ka AdMob data ruk sakta hai"
            karo = "Settings me AdMob account dobara connect karo."
        elif m == "stale":
            kit = "Is app ke GA4 wale number purane"
            karo = "GA4 / Firebase link check karo; kal bhi purana ho to Settings dekho."
        else:
            kit = app_size_txt(ctx, aid)
            karo = "Kal ka AdMob data check karo; aaj bhi 0 ho to AdMob console dekho."
        return dict(kya=r["fact"], kit=kit, karo=karo)
    if k == "ads":
        x = ctx.ads[aid]
        kit = (f"Spend {money(x['spp'], din=False)} → {money(x['sp'])} · revenue {money(a['kp7'], din=False)} → "
               f"{money(a['k7'])}")
        if x["cpi"] and x["cpip"]:
            kit += f" · cost per install {usd2(x['cpip'])} → {usd2(x['cpi'])}"
        karo = ("Budget badhane se pehle campaign-wise ROAS dekho; jo campaign kamai nahi la raha, uska budget kam karo."
                if r["tier"] == "amber" else "Achha chal raha — jo campaign kaam kar raha, use hi badhao.")
        kya = ("Ads pe kharcha badha, par kamai utni nahi badhi" if (r["tier"] == "amber" and x["sp"] > x["spp"])
               else r["fact"])
        return dict(kya=kya, kit=kit, karo=karo, saath=r["fact"] if kya != r["fact"] else None)
    if k == "upd":
        v = r["ver"]
        if r["level"] == "halt":
            karo = (f"{v} ka rollout ho chuka ({umar(r['age'])} ago) — ab fix wala update bhejo: {v} me jo badla, "
                    f"wo wapas lo." if r["age"] > 14 else f"{v} ka rollout stop karo, fix wala update bhejo.")
        elif r["level"] == "hold":
            karo = f"{v} ka rollout abhi mat badhao; result pakka hone tak ruko."
        else:
            karo = f"{v} me jo badla, wahi raasta aage bhi rakho."
        return dict(kya=r["fact"], kit=r["why"], karo=karo)
    if k == "ded":
        return dict(kya=r["fact"],
                    kit=(f"AdMob ne {fr(ctx, ctx.ded_from, ctx.ded_to)} me {money(r['ded'], din=False)} kaata · app ki "
                         f"kamai ka {r['ap'] * 100:.1f}%"),
                    karo="AdMob me us ad unit ka invalid traffic dekho; ad ki jagah (galti se click) check karao.")
    if k == "ah_ivt":
        return dict(kya=r["fact"], kit="Poore account pe asar ho sakta hai (ads limit)",
                    karo=("AdMob console me Policy / invalid traffic dekho; jis ad unit pe clicks achanak badhe, use "
                          "pause karo."))
    if k == "med":
        return dict(kya=r["fact"], kit="Us network se aane wali kamai lagbhag band",
                    karo=f"AdMob mediation me {r['net']} ka setup / bidding check karo.")
    if k == "kal_drop":
        return dict(kya=r["fact"],
                    kit=(f"Yesterday {money(r['now'], din=False)} vs usual {money(r['before'])} "
                         f"({money(r['now'] - r['before'], din=False, sign=True)})"),
                    karo="Aaj ka number bhi dekho; do din lagatar kam ho to ad units check karo.")
    return dict(kya=r["fact"], kit="", karo="Detail dekho.")


EXTRA_Q = ("range", "ads", "med", "kal_drop", "setup", "ded", "ah_ivt", "upd")


def q_row(ctx, r, frows, a):
    """The 5 questions for one row: kya hua · kab se · kitna bada · naya ya purana · kya karo (+ kis / abhi / saath)."""
    story = {"topic": r.get("topic", "T3"), "rows": frows}
    if r["kind"] in EXTRA_Q:
        q = q_extra(ctx, r, a)
    else:
        kit = kitna(ctx, r)
        if not kit:
            if r["kind"] == "act_ads":
                kit = f"Ads per user/day {per_user(r['before'])} → {per_user(r['now'])}"
            elif r["kind"] == "pay_never":
                pay = (ctx.vapp.get(r["app"]) or {}).get("pay") or {}
                kit = (f"Google Ads spend {money(a['spend'])} (4 weeks avg) · saal bhar me "
                       f"~{pay.get('pct365', 0):.0f}% hi wapas · ≈ Andaza")
            else:
                kit = app_size_txt(ctx, r["app"])
        karo = kya_karo(ctx, r, story)
        if r["kind"] == "impact" and r.get("level") == "hold":
            karo = f"{ver_of(r['release']['label'])} ka rollout abhi mat badhao; result pakka hone tak ruko."
        elif r["kind"] == "act_ads":
            karo = "AdMob me dekho kaunsa ad unit kam dikh raha; revenue per user bhi gire to pichhla update check karo."
        elif r["kind"] == "pay_never":
            karo = ("Old issue — naye campaign ka budget tabhi badhao jab ROAS sudhre; Install value tab dekho."
                    if r.get("purani") else "Is campaign ka budget mat badhao jab tak paisa 1 saal me wapas na aaye.")
        q = dict(kya=headline(ctx, r, story), kit=kit, karo=karo)
        try:
            ab = abhi(ctx, r, story)[0]
        except Exception:
            ab = None
        if ab:
            q["abhi"] = ab
    if r.get("kab"):
        kab = r["kab"]
    elif r["kind"] in EXTRA_Q:
        kab = f"{fd(ctx, r['started'])} · {umar_se(r['age'])}"
    else:
        kab = re.sub(r"\((\d+ (?:days?|weeks|months))\)", r"· \1 ago", kab_se(ctx, r)).replace("· 0 days ago", "· today")
    q["kab"] = kab
    q["kis"] = kis_data(ctx, r) if r.get("period") else ""
    q["naya"] = {"chip": "purani" if r.get("purani") else r["status"], "first": first_shown(ctx, [r])}
    return q


def fallback(ctx, f, aid, a):
    """(state, one line) when no row drives the feature."""
    y = ctx.admob_till
    w7, p7 = ctx.w7, ctx.p7
    if f == "kamai":
        yv, us = ctx.kal[aid]
        if us <= 0 and yv <= 0:
            return "nodata", "Pichhle 8 din me AdMob kamai nahi"
        e1, e0 = ecpm(ctx, aid, [y.isoformat()]), ecpm(ctx, aid, ctx.u7)
        t = f"Yesterday {money(yv, din=False)} · usual {money(us)}"
        if e1 and e0:
            t += f" · eCPM {usd2(e0)} → {usd2(e1)}"
        return "normal", t
    if f == "uninstall":
        if aid in ctx.no_ga4 or aid not in ctx.ud:
            return "nodata", "GA4 nahi juda — uninstall ka data nahi"
        u = ctx.ud[aid]
        if not u.get("ready"):
            return "wait", "⏳ Too early — data kam"
        h = (u.get("head4") or {}).get("D0") or {}
        t = "Koi pakka badlav nahi"
        if h.get("p") is not None:
            t = f"Same day uninstall: {p100(h['p'])}% (installs {fr(ctx, h['from'], h['to'])})"
        if u.get("rate7"):
            t += f" · uninstall rate {pct1k(u['rate7'])}"
        return "normal", t
    if f == "active":
        if aid in ctx.no_ga4 or aid not in ctx.aapp:
            return "nodata", "GA4 nahi juda — active users ka data nahi"
        m = (ctx.aapp[aid].get("m") or {})
        rd, d1 = m.get("ret_dau") or {}, m.get("d1") or {}
        w = ctx.aapp[aid].get("win") or {}
        if rd.get("st") in ("low", "growth", None) and not rd.get("v"):
            return "wait", "⏳ Too early"
        t = f"Old users/day {users(rd['v'])}" if rd.get("v") else "Old users: data kam"
        if rd.get("rel") is not None and w and all(w.get(x) for x in ("from", "to", "bfrom", "bto")):
            t += f" ({pct(rd['rel'])} · {fr(ctx, w['from'], w['to'])} vs {fr(ctx, w['bfrom'], w['bto'])})"
        if d1.get("v") is not None:
            t += f" · back next day {p100(d1['v'])}%"
        st = "wait" if rd.get("st") in ("low", "growth") else "normal"
        return st, t
    if f == "value":
        v = ctx.vapp.get(aid)
        if aid in ctx.no_ga4 or not v:
            return "nodata", "GA4 nahi juda — install value ka data nahi"
        pay = v.get("pay") or {}
        st = pay.get("st")
        if st == "nospend":
            note = re.sub(r"\s—\s.*$", "", pay.get("note") or "") or "No Google Ads spend"
            return "na", note
        if st in ("wait", "thin", "low", "few") or not pay.get("from"):
            return "wait", "⏳ Too early — install-wise earning ka data aa raha"
        if pay.get("p"):
            return "normal", f"Money back in ~{pay['p']} days (installs {fr(ctx, pay['from'], pay['to'])}) · ≈ Andaza"
        return "normal", "Normal"
    if f == "update":
        ups = [u for u in ((ctx.uapp.get(aid) or {}).get("impact") or {}).get("updates") or []
               if age_days(ctx, u["date"]) <= UPDATE_DAYS]
        if not ups:
            return "na", f"Pichhle {UPDATE_DAYS} din me koi update nahi"
        u = max(ups, key=lambda x: x["date"])
        v = ver_of(u["label"])
        v = f"{fd(ctx, u['date'])} wala update" if v == "App update" else v
        vd = u.get("verdict") or {}
        if vd.get("early"):
            ro = vd.get("ready_on")
            return "wait", f"{v} ({fd(ctx, u['date'])}) · ⏳ Too early" + (f" · result {fd(ctx, ro)}" if ro else "")
        lv = vd.get("level")
        w = {"continue": "👍 Keep", "win": "✅ Update went well", "hold": "⚠️ Wait and check",
             "halt": "🛑 Stop update"}.get(lv, "No clear change")
        return "normal", f"{v} ({fd(ctx, u['date'])}) · {w}"
    if f == "ads":
        x = ctx.ads[aid]
        if x["sp"] < 1 and x["spp"] < 1:
            return "na", "No Google Ads spend (last 14 days)"
        t = f"Spend {money(x['sp'])}"
        if x["roas"] is not None:
            t += f" · ROAS {x['roas']:.2f}"
        if x["cpi"] is not None:
            t += f" · cost per install {usd2(x['cpi'])}"
        if x["spp"] >= 1 and x["sp"] < x["spp"] * 0.3:
            t += f" · spend {money(x['spp'], din=False)} → {money(x['sp'])} (kam kiya?)"
        return "normal", t + f" ({fr(ctx, w7[0], w7[-1])})"
    if f == "deduct":
        dd = ctx.deda.get(aid)
        rv = sum(ctx.rev[aid].get(x, 0) for x in ctx.ded_dates[min(ctx.ded_win):]) if ctx.ded_win else 0
        if not dd and rv <= 0:
            return "nodata", "Deduction ka data nahi"
        if not dd:
            return "normal", f"Koi deduction nahi dikha ({fr(ctx, ctx.ded_from, ctx.ded_to)})"
        if not rv:
            return "normal", f"AdMob ne {money(dd['ded'], din=False)} kaata ({fr(ctx, ctx.ded_from, ctx.ded_to)})"
        sh = dd["ded"] / rv * 100
        return "normal", (f"AdMob ne baad me {money(dd['ded'], din=False)} kaata ({fr(ctx, ctx.ded_from, ctx.ded_to)})"
                          f" · kamai ka {'0.1% se kam' if sh < 0.1 else f'{sh:.1f}%'}")
    if f == "mediation":
        m = ctx.med.get(aid)
        if not m:
            return "nodata", "Mediation ka data nahi"
        top = sorted(m["sh"].items(), key=lambda kv: -kv[1])[:2]
        t = f"{len(m['sh'])} network · " + " · ".join(f"{k} {v * 100:.0f}%" for k, v in top)
        low = [k for k, fl in m["fill"].items() if fl is not None and fl < 0.5 and m["sh"].get(k, 0) >= 0.02]
        if low:
            t += f" · kam fill: {', '.join(low)}"
        return "normal", t + f" ({fr(ctx, w7[0], w7[-1])})"
    if f == "health":
        h = ctx.ah.get(aid)
        if not h:
            return "nodata", "Account health ka data nahi"
        t = (f"Invalid traffic: {'saaf' if h.get('ivt') == 'clean' else h.get('ivt')} · ads serving: "
             f"{'ok' if h.get('serving') == 'ok' else h.get('serving')}")
        if all((h.get(k) or "—") == "—" for k in ("app_ads_txt", "consent", "tcf")):
            t += " · app-ads.txt / consent: data nahi"
        return "normal", t
    if f == "setup":
        acc = ctx.acct.get(a["acc"]) or {}
        tok = acc.get("token")
        bits = [f"AdMob till {fd(ctx, y)}"]
        if aid in ctx.aapp:
            bits.append(f"GA4 till {fd(ctx, ctx.aapp[aid].get('data_till') or ctx.ga4_till)}")
        if tok:
            bits.append(f"AdMob login: {'OK' if tok == 'Valid' else tok}")
        return "normal", " · ".join(bits)
    return "nodata", "No data"
