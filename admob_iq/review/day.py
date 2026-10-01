"""Daily App Review — one day's cards: 10 features per selected app, the card tier / headline / 'naya aur bigda',
the build-time order and counts → the day document (v1). Plain JSON: strings, RT (rich text with money segments) and
chart data; no HTML anywhere."""

import re
from collections import defaultdict
from datetime import datetime, timezone

from .apps import ReviewBuildError, make_ctx
from .charts import ads14, chart_for, kamai14
from .const import (BADI, CHHOTI, DOC_V, DROP_DAYS, EXPAND_TOP, FAIL_RATIO, FEAT_PRI, FEAT_TAB, FEATS, MAX_MORE,
                    NAYA_DAYS, NO_CHART_KINDS, REVIEW_READY_IST_DEFAULT, SRC_TAG, TR, WDAY, WORD, EXTRA_KINDS)
from .fmt import fd, fr, money, pct, plain, rt, umar
from .rows import app_rows, build_rows, extra_rows, feature_of, row_id
from .text import fallback, good_text, kis_data, q_row

FEAT_FAIL_TXT = "Is feature ka data nahi padh paye"
APP_FAIL_TXT = "Is app ka card nahi ban paya (data me dikkat)"
CARD_FAIL_TXT = "Card nahi ban paya"
_HTML_LIKE = re.compile(r"<(?=[A-Za-z/!?])")


def tier_of(r):
    t = r["tier"]
    return "normal" if t == "info" else t


def _round(v):
    return round(float(v or 0), 4) + 0.0


# ── detail + rows ────────────────────────────────────────────────────────────────────────────────
def row_obj(ctx, x):
    """ROW of "Is feature me aur": {w, src, fact, meta}."""
    tier = x["tier"]
    if x["kind"] in EXTRA_KINDS:
        fact, meta = x["fact"], x["period"]
    else:
        meta = x["period"]
        if x.get("prov_on"):
            meta += " · ⏳ Not final"
        if x.get("andaza"):
            meta += " · ≈ Andaza"
        fact = x["fact"]
        if x.get("purani"):
            fact += " (old issue)"
        if x["kind"] == "impact" and x.get("level") == "win":
            fact = "✅ Update went well: " + fact
    w = tier if tier in WORD else "info"
    return {"w": w, "src": SRC_TAG.get(x["src"], "Setup"), "fact": rt(fact),
            "meta": f"{meta} · Started {fd(ctx, x['started'])} ({umar(x['age']) if x['age'] > 0 else 'today'})"}


def detail(ctx, f, head, rows, aid):
    """{"chart", "more", "tab"} — the feature's "Detail →"."""
    chart = None
    if head is not None and head["kind"] not in NO_CHART_KINDS:
        try:
            chart = chart_for(ctx, head)
        except Exception:
            chart = None
    if chart is None and f == "kamai":
        chart = kamai14(ctx, aid)
    if chart is None and f == "ads" and ctx.ads[aid]["has"]:
        chart = ads14(ctx, aid)
    others = [x for x in rows if x is not head]
    return {"chart": chart, "more": [row_obj(ctx, x) for x in others][:MAX_MORE], "tab": FEAT_TAB[f]}


def _nodata(msg):
    return {"st": "nodata", "t": msg, "line": msg, "q": None, "kis": None, "info": [], "detail": None, "snz_ph": None}


def _feature(ctx, f, frs, aid, a):
    """-> (internal {st, head, line…}, FEAT dict)."""
    tiered = [r for r in frs if tier_of(r) in ("red", "amber", "green")]
    info = [r for r in frs if tier_of(r) == "normal" and r["age"] <= DROP_DAYS]
    q, kis, info_lines, det = None, None, [], None
    if tiered:
        def hk(r):
            return (-TR[tier_of(r)], 1 if r.get("purani") else 0,
                    0 if r["kind"] in ("impact", "ivt", "kamai_drop", "ads") else 1,
                    0 if r["status"] == "naya" else 1, -abs(r.get("rel") or 0))
        tiered.sort(key=hk)
        head = tiered[0]
        st = tier_of(head)
        rows = tiered + info
        if st in ("red", "amber"):
            q = q_row(ctx, head, tiered, a)
            line = q["kya"]
        else:
            line = (good_text(ctx, head) if head["kind"] not in ("ads", "range", "med", "kal_drop", "setup", "upd")
                    else head["fact"])
            if head["kind"] == "kamai_up":
                line = f"Revenue {pct(head['rel'])}: {money(head['before'], din=False)} → {money(head['now'])}"
            line = line[0].upper() + line[1:]
            kis = kis_data(ctx, head) if head.get("period") else None
        det = detail(ctx, f, head, rows, aid)
    else:
        head, rows = None, info
        st, line = fallback(ctx, f, aid, a)
        info_lines = [x["fact"] for x in info][:2]
        if st in ("normal", "wait") and f in ("kamai", "ads"):
            det = detail(ctx, f, None, info, aid)
    feat = {"st": st, "t": plain(line)[:160], "line": rt(line), "q": _q_obj(q), "kis": rt(kis) if kis else None,
            "info": [rt(x) for x in info_lines], "detail": det,
            "snz_ph": next((x["snz_ph"] for x in rows if x.get("snz_ph")), None)}
    return {"f": f, "st": st, "head": head, "line": line}, feat


def _q_obj(q):
    if q is None:
        return None
    return {"kya": rt(q["kya"]), "kab": q["kab"], "kit": rt(q.get("kit") or ""), "naya": q["naya"],
            "karo": q["karo"], "kis": rt(q["kis"]) if q.get("kis") else None,
            "abhi": rt(q["abhi"]) if q.get("abhi") else None, "saath": rt(q["saath"]) if q.get("saath") else None}


# ── one app ──────────────────────────────────────────────────────────────────────────────────────
def _app_base(ctx, aid):
    a = ctx.apps[aid]
    y, us = ctx.kal.get(aid, (0.0, 0.0))
    return {"key": a["key"], "app_id": aid, "dname": a["dname"], "name": a["store"] + a["tag"], "acct": a["acct"],
            "pkg": a["pkg"], "size": a["size"], "small": a["size"] == "chhoti", "k7": _round(a["k7"]),
            "kp7": _round(a["kp7"]), "y": _round(y), "us": _round(us), "spend": _round(a["spend"]),
            "paisa": _round(a["paisa"])}


def _failed_app(ctx, aid):
    out = _app_base(ctx, aid)
    out.update(tier="normal", nb=[], head={"text": APP_FAIL_TXT, "chip": None, "age": None},
               f={f: _nodata(CARD_FAIL_TXT) for f, _ in FEATS})
    return out, []


def build_app(ctx, aid):
    """-> (APP dict, the red/amber internal features sorted as the card shows them)."""
    a = ctx.apps[aid]
    rows = app_rows(ctx, aid)
    # what this day's card shows as red / amber (the store keeps it: tomorrow's "Pehli baar dikha" / setup "Kab se")
    ctx.seen_out[a["key"]] = sorted({row_id(r) for r in rows if tier_of(r) in ("red", "amber")})
    byf = defaultdict(list)
    for r in rows:
        f = feature_of(r)
        if f:
            byf[f].append(r)
    fx, feats = {}, {}
    for f, _lab in FEATS:
        if f in ctx.feat_fail.get(aid, ()):
            fx[f], feats[f] = {"f": f, "st": "nodata", "head": None, "line": FEAT_FAIL_TXT}, _nodata(FEAT_FAIL_TXT)
            continue
        try:
            fx[f], feats[f] = _feature(ctx, f, byf.get(f, []), aid, a)
        except Exception:
            fx[f], feats[f] = {"f": f, "st": "nodata", "head": None, "line": FEAT_FAIL_TXT}, _nodata(FEAT_FAIL_TXT)
    bad = [x for x in fx.values() if x["st"] in ("red", "amber")]
    bad.sort(key=lambda x: (-TR[x["st"]], 1 if x["head"].get("purani") else 0, FEAT_PRI[x["f"]],
                            0 if x["head"]["status"] == "naya" else 1))
    goods = [x for x in fx.values() if x["st"] == "green"]
    tier = bad[0]["st"] if bad else ("green" if goods else "normal")
    nb = [x["f"] for x in bad if x["st"] == "red" and x["head"]["status"] == "naya" and not x["head"].get("purani")]
    if bad:
        h = bad[0]
        hl, hst, hage, hpur = feats[h["f"]]["q"]["kya"], h["head"]["status"], h["head"]["age"], bool(h["head"].get("purani"))
    elif goods:
        g = sorted(goods, key=lambda x: FEAT_PRI[x["f"]])[0]
        hl, hst, hage, hpur = feats[g["f"]]["line"], g["head"]["status"], g["head"]["age"], False
    else:
        hl, hst, hage, hpur = "Sab normal — koi badlav nahi", None, None, False
    out = _app_base(ctx, aid)
    out.update(tier=tier, nb=nb,
               head={"text": hl, "chip": ("purani" if hpur else hst) if hst else None,
                     "age": (umar(hage) if hage > 0 else "today") if hage is not None else None},
               f=feats)
    return out, bad


# ── the day ──────────────────────────────────────────────────────────────────────────────────────
def _how(ctx, n):
    w7, p7, u7, y = ctx.w7, ctx.p7, ctx.u7, ctx.admob_till
    ded = (f"Deductions: {fr(ctx, ctx.ded_from, ctx.ded_to)} ke AdMob snapshots; " if ctx.ded_from and ctx.ded_to
           else "Deductions: AdMob ke snapshots; ")
    lines = [
        (f"Har app ka ek card. Line: pehle wo apps jinme koi 🔴 baat 🆕 New ({NAYA_DAYS} din ke andar shuru) hai, "
         f"ya koi khula 🚩 Re-review flag (admin ka faisla baaki) / kal ka “🔁 Check again tomorrow” — phir "
         f"baaki kamai (pichhle 7 din ka avg, {fr(ctx, w7[0], w7[-1])}) ke hisaab se."),
        f"Yesterday = {fd(ctx, y)} (AdMob ka aakhri poora din). Usual = {fr(ctx, u7[0], u7[-1])} ka daily avg.",
        (f"Uninstall, Active users, Install value, Update aur ad-unit ki baatein dashboard ke unhi tabs ke rules se "
         f"bani. Ads: {fr(ctx, w7[0], w7[-1])} vs {fr(ctx, p7[0], p7[-1])}; ROAS 20%+ gira ya cost per install "
         f"30%+ badha to 🟡. {ded}kisi ad unit ka 15%+ aur {money(20.0, din=False)}+ kata to 🔴. Mediation: kisi "
         f"network ka hissa 10%+ se 1/3 se neeche gira to 🟡."),
        f"Small apps: kamai + ads spend {money(CHHOTI)} se kam. Inke 🔴 bhi unke group me dikhte hain, upar nahi aate.",
        "Jin features ka is app ke liye data nahi, unka dot grey (“No data”).",
        ("States: ✅ Reviewed · 📝 Reviewed + note · 🚩 Re-review (Important) · 🔁 Check again tomorrow. 🚩 Important · "
         "Re-review = admin dobara dekhega — poori app pe (card ke niche wala button) ya sirf ek feature pe (har feature "
         "ke aage chhota 🚩, note ke saath; jaise sirf “Revenue · eCPM” ya sirf “Uninstall”). Har flag alag item hai aur "
         "admin har ek ka alag faisla karta hai (👍 OK · 🛠 Assign task · ⛔ Close). Faisla hone tak card upar "
         "focus me rehta hai; khula flag agle din ke card pe “🚩 Revenue · eCPM · Open N days” jaisa dikhta hai. "
         "🛠 Assign task wala flag card pe sirf chip dikhata hai."),
        ("🔁 Check again tomorrow alag hai — ye sirf khud ke liye kal ka reminder hai, admin ko nahi jaata. 💤 Snooze = "
         "ek baat 7 ya 14 din ke liye chhupao (note ke saath)."),
        (f"Ye cards {fd(ctx, ctx.day)} ko ek baar bane (us waqt ka data) aur din bhar wahi rehte hain — isliye History "
         f"me wahi dikhta hai jo review ke waqt tha."),
        f"Sab {n} apps review hote hi Summary khulta hai.",
    ]
    return [rt(x) for x in lines]


def _clean(o):
    """No HTML-like text anywhere in the document ('<' + letter or '/' becomes '‹')."""
    if isinstance(o, str):
        return _HTML_LIKE.sub("‹", o.replace("\x00", ""))
    if isinstance(o, list):
        return [_clean(x) for x in o]
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    return o


def build_day(site, day, now=None, ready_ist=REVIEW_READY_IST_DEFAULT, history=None, seen_out=None):
    """The day document for review day `day` (date) from a built site (review.site.Site). Raises ReviewBuildError
    when the dashboard is unreadable, no app is selected, or more than max(2, FAIL_RATIO × apps) apps failed.
    history: {"go_live": date, "seen": {app key: {row_id: date}}} from the store (None: this is the first day).
    seen_out: a dict that receives {app key: [row_id]} — the red / amber rows on this day's cards."""
    now = now or datetime.now(timezone.utc)
    ctx = make_ctx(site, day)
    if history:
        ctx.go_live = min(history.get("go_live") or day, day)
        ctx.seen = history.get("seen") or {}
    build_rows(ctx)
    extra_rows(ctx)
    cards = []
    failed = 0
    for aid in ctx.apps:
        try:
            if aid in ctx.app_fail:
                raise ReviewBuildError("app")
            app, bad = build_app(ctx, aid)
        except Exception:
            failed += 1
            ctx.seen_out.pop((ctx.apps.get(aid) or {}).get("key"), None)   # a placeholder card showed nothing
            app, bad = _failed_app(ctx, aid)
        cards.append((app, bad))
    if seen_out is not None:
        seen_out.update(ctx.seen_out)
    if failed > max(2, FAIL_RATIO * len(cards)):
        raise ReviewBuildError(f"failed {failed} of {len(cards)}")
    cards.sort(key=lambda c: -c[0]["k7"])
    attn = [c for c in cards if c[1] and not c[0]["small"]]
    okg = [c for c in cards if not c[1] and not c[0]["small"]]
    smallg = [c for c in cards if c[0]["small"]]
    top = sorted(attn, key=lambda c: (0 if c[0]["nb"] else 1, -c[0]["k7"]))
    order = {"top": [c[0]["key"] for c in top], "ok": [c[0]["key"] for c in okg],
             "small": [c[0]["key"] for c in smallg]}
    w7, p7, u7 = ctx.w7, ctx.p7, ctx.u7
    doc = {
        "v": DOC_V,
        "day": day.isoformat(),
        "weekday": WDAY[day.weekday()],
        "built_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ready_ist": ready_ist,
        "built_from": {"generated_at": ctx.db.get("generated_at")},
        "data": {"admob_till": ctx.admob_till.isoformat(),
                 "ga4_till": ctx.ga4_till.isoformat() if ctx.ga4_till else None,
                 "settled_till": ctx.settled.isoformat() if ctx.settled else None,
                 "ga4_lag": ctx.ga4_lag,
                 "w7": {"from": w7[0], "to": w7[-1]}, "p7": {"from": p7[0], "to": p7[-1]},
                 "usual": {"from": u7[0], "to": u7[-1]},
                 "ded": {"from": ctx.ded_from, "to": ctx.ded_to} if ctx.ded_from and ctx.ded_to else None},
        "fx": ctx.fx,
        "feats": [[f, lab] for f, lab in FEATS],
        "consts": {"small_usd": int(CHHOTI), "badi_usd": int(BADI), "naya_days": NAYA_DAYS, "expand_top": EXPAND_TOP},
        "counts": {"apps": len(cards), "attn": len(top), "ok": len(okg), "small": len(smallg),
                   "nb": sum(1 for c in top if c[0]["nb"]), "red": sum(1 for c in top if c[0]["tier"] == "red"),
                   "amber": sum(1 for c in top if c[0]["tier"] == "amber"), "failed": failed},
        "order": order,
        "how": _how(ctx, len(cards)),
        "apps": [c[0] for c in top + okg + smallg],
    }
    return _clean(doc)
