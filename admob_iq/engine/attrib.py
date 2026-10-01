"""The installs vs per-user split of a change — "installs ki wajah se" / "asli badlaav" (SPEC_SPLIT). Pure: no I/O, no
prints, and nothing here ever feeds back into an engine decision (verdicts, alerts, sending and every number the engines
already show are untouched; this only ADDS an explanation).

WIRE FORM `sp` (what the engines write on a change object) — null, or a list whose first item is a code:
    ["ret", fi, yb, yw, nb, na, pb, pa, k, fl(, before)]
                                                    returning users (Active): fi = the installs' part (users / day) =
                                                    what the after days' own installs would bring back at the BEFORE
                                                    days' per-install return curve (per lag, S1) − the before days'
                                                    recent returners yb; yw = the recent returners after; nb / na = the
                                                    installs a day that feed them (weighted by that curve, so fi =
                                                    yb · (na ÷ nb − 1)); pb / pa = of 100 installs of the last k days,
                                                    how many come back a day (before / after: the recent installs' own
                                                    return, null: unknown); fl = 1 est (≈) | 2 elastic mode; `before`
                                                    only on an info row (kind "installs")
    ["imp", fi, tr(, nb, na)]                       returning users (Update impact): the installs' part and the trend
                                                    part of expected − before; nb / na on the 7-day rows only
    ["uc", ub, ua, xb, xa, nb, na, p100]            uninstalls / day: actual, expected-by-installs at the host's own
                                                    calibration (so ua ÷ xa − 1 is the alert's own per-install change;
                                                    it cancels in xa ÷ xb), installs / day, 100 × the usual share of an
                                                    install leaving within 28 days
    ["ur" | "rr", ib, ia]                           uninstall / return RATES: installs / day before / after (the
                                                    rates are the host's)
    ["rev", ub, ua, [note]…]                        revenue total: active users / day before / after (the per-1,000
                                                    users revenue is the host's) + optional notes
    ["ir", ib, ia]                                  revenue from installs: installs / week (per-install value: host's)
    ["spd", ib, ia, cb, ca]                         ad spend: installs / week, cost per install
    ["vpi", vb, va, cb, ca]                         money back per 100 spent: value per install, cost per install
    ["pu", [code, b, a]…]                           a per-user number: notes only (code new / net / rec / paid, the
                                                    share per 100 before / after)
    ["no", reason]                                  no split: cohorts / few / steep (steep_up / steep_dn: which way)
                                                    / base / apps / error
Counts are whole from 1,000 up and 4 significant digits below (a whole value is written as an int: a small app's 3.45
installs a day must not move a shown part), rates to 5 dp, money per 1,000 users to 4 dp, money per install to 6 dp
(the value engine's own precision), per-100 values to 2 dp.

EXPANDED FORM (expand(kind, host) — the page's splitOf mirrors it; a parity test checks both):
    {"v": 1, "code", "basis", "per": "day"|"week", "days": N|None,
     "total": {"before", "after", "abs", "rel"}, "installs": {"before", "after", "rel", "what"}|None,
     "from_installs": {"abs", "rel"}, "trend": {"abs", "rel"}|None,
     "per_user": {"abs", "rel", "own", "status"}, "per100": {"n", "before", "after", "k"}|None,
     "on_now": {"installs", "abs"}|None, "shown": {"total", "from_installs", "trend", "per_user", "count"},
     "form": "pct"|"count", "est": bool, "mode": "cohort"|"elastic"|None, "note": [[code, b, a]…]}
  a "no" wire → {"v": 1, "code", "basis", "none": reason}; "pu" → {"v": 1, "code": "pu", "basis": "per_user", "note"};
  None when the host has no split. per_user is ALWAYS the residual (total − from_installs − trend), so the parts add up
  exactly; shown.* = R(100 · part.abs / total.before) with R(x) = round half away from zero of round(x, 6), except
  shown.per_user = shown.total − shown.from_installs − (shown.trend or 0): the parts add up as printed.
  form "count" (shown.count = {"exp", "total", "from_installs", "trend", "per_user"}: integers × 10^exp, 2 significant
  digits of the largest part, per_user = total − the others: they add up as printed): when a % of the before total
  would mislead — a part at −100% or below, or (a per-unit own change known) the per-user % more than 1.5× / under ⅔ of
  that own change or the other way (installs moved a lot: the Δinstalls × Δrate part is measured on today's installs).
  per_user.status: the host's verdict (copied), kept only when the per-user part points its way (a worse / watch word
  with a part that moved the bad way, a better word with one that moved the good way); none for a closed change, a
  "maybe" / "unsure" (the host's own chip says it) or a host without a verdict.

KINDS (host → where before / after / rates come from):
    act_tile_ret   Active tiles.ret_dau             before = base, after = v                         ("ret")
    act_alert_ret  Active ret_dau alert             before = before, after = now                     ("ret")
    act_info_ret   Active info row (installs)       before = sp[10], after = sp[10] · (1 + rel)      ("ret")
    act_row_ret    All-apps row m.ret_dau           before = s[2] / s[3], after = s[0] / s[1]         ("ret")
    act_tile_rr    Active tiles.d1 / d7             rb = s[2] / s[3], ra = s[0] / s[1]; ib / ia = sp, else s[3] / nb,
                                                    s[1] / n
    rate           an "ur" / "rr" host: alert / old change (before → now; geo_move ÷ 100), uninstall table row
                   (prev-or-all.p → recent.p), head4 cell (prev → p), impact row (before → after)
    imp_rate       impact new_dN row (no sp): ib / ia = extra.installs_* ÷ extra.cohorts_*, rates before → after
    uni_verdict    uninstall survival verdict (no sp): per day = users ÷ k, rate = left (kept)
    imp_dau        impact returning_dau row         before → after, own = after ÷ expected − 1        ("imp")
    uc             rate_drift / rate_spike alert, rate_now (own = ua ÷ xa − 1)                     ("uc")
    rev            Active arpdau tile (base → v), impact 7-day arpdau row (before → after)          ("rev")
    ir             value rpi tile (base → v), geo_move rpi7 alert (before → now)                    ("ir")
    spd            value cpi tile                                                                   ("spd")
    vpi            value b7 tile / pay_slow alert                                                   ("vpi")
    pu             any per-user host                                                                ("pu")
"""

import math
from decimal import ROUND_HALF_UP, Decimal

V = 1
ON = True            # config SPLIT (the builds set it): off → every sp is null and no Telegram tail
FAILS = 0            # builders that raised during this build (counts only: "split failed: N" on stderr when > 0)

CODES = ("ret", "imp", "uc", "ur", "rr", "rev", "ir", "spd", "vpi", "pu", "no")
REASONS = ("cohorts", "few", "steep", "steep_up", "steep_dn", "base", "apps", "error")
NOTE_CODES = ("new", "net", "rec", "paid")
BASIS = {"ret": "returning", "imp": "returning", "uc": "uninstall_count", "ur": "uninstall_rate",
         "uk": "uninstall_rate", "rr": "return_rate", "rev": "revenue_total", "ir": "revenue_total",
         "spd": "ad_spend", "vpi": "value_per_install", "pu": "per_user"}
KINDS = {"act_tile_ret": "ret", "act_alert_ret": "ret", "act_info_ret": "ret", "act_row_ret": "ret",
         "act_tile_rr": "rr", "rate": None, "imp_rate": "rr", "uni_verdict": "uk", "imp_dau": "imp", "uc": "uc",
         "rev": "rev", "ir": "ir", "spd": "spd", "vpi": "vpi", "pu": "pu"}
WEEKLY = ("ir", "spd", "vpi")
POOL_MIN = 0.9       # a pooled split needs the covered apps to hold ≥ 90% of the pooled before level
STATUS_WORDS = ("bigda", "dhyan", "behtar", "normal", "jaldi", "lagu_nahi")
# §2.4: the host's own verdict, copied (never recomputed)
# (a "maybe" tile / an "unsure" row gets no word: its own chip already says "maybe", never a flat "Normal" beside it)
TILE_ST = {"worse": "bigda", "never": "bigda", "watch": "dhyan", "slow": "dhyan", "break": "dhyan",
           "better": "behtar", "normal": "normal", "maybe": None, "maybe_dn": None, "maybe_up": None,
           "price_dn": "normal", "price_up": "normal", "growth": "jaldi", "low": "jaldi", "wait": "jaldi",
           "thin": "jaldi", "noad": "lagu_nahi", "nospend": "lagu_nahi"}
SEV_ST = {"warning": "bigda", "watch": "dhyan", "good": "behtar"}
ROW_ST = {"worse": "bigda", "better": "behtar", "same": "normal", "unsure": None, "market": "normal"}
JUDGED = ("worse", "better", "same", "unsure", "market")
MULT = ("rr", "ur", "uk", "uc", "rev", "ir", "spd", "vpi", "imp")    # per-user % = (volume factor) × its own change
BAD_UP = ("uc", "ur", "spd")        # the per-user part rising is the bad way (uninstalls, an install's price)
MONEY = ("rev", "ir", "spd", "vpi")
COUNT_LO, COUNT_HI = 2 / 3, 1.5     # the per-user % within ⅔–1.5× its own change: a % reads true; beyond: counts


# ── rounding (wire) ────────────────────────────────────────────────────────────────────────────────

def _fin(x):
    x = float(x)
    if not math.isfinite(x):
        raise ValueError("not finite")
    return x


def _whole(v):
    return int(v) if v == int(v) else v


def cnt(x):
    """A count per day / week: whole from 1,000 up, 4 significant digits below (an int when whole) — a small app's
    installs a day keep enough digits that no shown part moves on them."""
    if x is None:
        return None
    x = _fin(x)
    if abs(x) >= 1000:
        return int(round(x))
    if x == 0:
        return 0
    return _whole(round(x, 3 - int(math.floor(math.log10(abs(x))))) + 0.0)


def rate5(x):
    return None if x is None else round(_fin(x), 5) + 0.0


def m4(x):
    return None if x is None else round(_fin(x), 4) + 0.0


def m6(x):
    return None if x is None else round(_fin(x), 6) + 0.0


def p1(x):
    return None if x is None else _whole(round(_fin(x), 1) + 0.0)


def p2(x):
    return None if x is None else _whole(round(_fin(x), 2) + 0.0)


# ── builders (engines call them inside safe) ──────────────────────────────────────────────────────

def safe(fn, *a, **k):
    """fn(...) → its wire, None when the switch is off; any exception → ["no", "error"] (counted in FAILS) — a split
    can never raise into an engine."""
    global FAILS
    if not ON:
        return None
    try:
        return fn(*a, **k)
    except Exception:
        FAILS += 1
        return ["no", "error"]


def no(reason):
    return ["no", reason]


def ret(fi, yb, yw, nb, na, pb, pa, k, fl, before=None):
    out = ["ret", cnt(fi), cnt(yb), cnt(yw), cnt(nb), cnt(na), p2(pb), p2(pa), None if k is None else int(k), int(fl)]
    if before is not None:
        out.append(cnt(before))
    return out


def imp(fi, tr, nb=None, na=None):
    out = ["imp", cnt(fi), cnt(tr)]
    if nb is not None and na is not None:
        out += [cnt(nb), cnt(na)]
    return out


def uc(ub, ua, xb, xa, nb, na, p100):
    return ["uc", cnt(ub), cnt(ua), cnt(xb), cnt(xa), cnt(nb), cnt(na), p1(p100)]


def rate(code, ib, ia):
    if not (ib and ia) or ib <= 0 or ia <= 0:
        return no("few")
    return [code, cnt(ib), cnt(ia)]


def rev(ub, ua, notes=()):
    """notes: [(code, share before, share after)] (shares 0–1, written per 100)."""
    if not (ub and ua) or ub <= 0 or ua <= 0:
        return no("few")
    return ["rev", cnt(ub), cnt(ua)] + [[c, p1(100 * b), p1(100 * a)] for c, b, a in notes]


def ir(ib, ia):
    if not (ib and ia) or ib <= 0 or ia <= 0:
        return no("few")
    return ["ir", cnt(ib), cnt(ia)]


def spd(ib, ia, cb, ca):
    if not (ib and ia and cb and ca) or min(ib, ia, cb, ca) <= 0:
        return no("few")
    return ["spd", cnt(ib), cnt(ia), m6(cb), m6(ca)]


def vpi(vb, va, cb, ca):
    if not (vb and cb and ca) or va is None or min(vb, cb, ca) <= 0:
        return no("few")
    return ["vpi", m6(vb), m6(va), m6(cb), m6(ca)]


def pu(notes):
    """[(code, share before, share after)] (shares 0–1) → ["pu", [code, per-100 before, per-100 after]…] or None."""
    got = [[c, p1(100 * b) if b is not None else None, p1(100 * a) if a is not None else None] for c, b, a in notes]
    return (["pu"] + got) if got else None


# ── expand ─────────────────────────────────────────────────────────────────────────────────────────

def R(x):
    """Round half away from zero of round(x, 6) (float dust like 7.4999999 never flips a shown %)."""
    x = round(x, 6)
    n = math.floor(abs(x) + 0.5)
    return int(n) if x >= 0 else -int(n)


class _None(Exception):
    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _need(*vs):
    for v in vs:
        if not _num(v):
            raise _None("few")


def _core(before, after, F, T=None):
    _need(before, after, F)
    if before <= 0:
        raise _None("base")
    tot = after - before
    P = tot - F - (T or 0.0)
    st, sf = R(100 * (tot / before)), R(100 * (F / before))
    stt = R(100 * (T / before)) if T is not None else None
    return {"total": {"before": before, "after": after, "abs": tot, "rel": tot / before},
            "from_installs": {"abs": F, "rel": F / before},
            "trend": None if T is None else {"abs": T, "rel": T / before},
            "per_user": {"abs": P, "rel": P / before, "own": None, "status": None},
            "shown": {"total": st, "from_installs": sf, "trend": stt, "per_user": st - sf - (stt or 0)}}


def _inst(b, a, what="installs"):
    if not _num(b) or not _num(a) or b <= 0:
        return None
    return {"before": b, "after": a, "rel": a / b - 1, "what": what}


def _days_of(host, days, kind=None):
    if days is not None:
        return days
    if kind == "act_tile_rr":             # an Active d1 / d7 tile's n is its window (7 days), not the day after install:
        return None                       # the caller passes days (1 / 7), as the page does
    n = host.get("n")
    if isinstance(n, int) and not isinstance(n, bool):
        return n
    m = host.get("metric")
    if isinstance(m, str) and len(m) > 1 and m[0] == "d" and m[1:].isdigit():
        return int(m[1:])
    return None


def status_of(kind, host, alerts=None):
    """The host's verdict as one of the 6 words (§2.4) — copied, never recomputed; None where the host has none, and
    for a closed change (its word was the severity it had while open)."""
    if host.get("closed"):
        return None
    if kind == "act_info_ret":
        return "normal"
    if kind == "act_row_ret":
        return None
    if kind == "uni_verdict":
        return {"worse": "bigda", "better": "behtar"}.get(host.get("dir"), "normal")
    if "severity" in host:
        return SEV_ST.get(host.get("severity"))
    if kind == "uc" and "out_of_band" in host:           # rate_now: an open rate alert decides, else the band
        sev = [a.get("severity") for a in alerts or [] if a.get("family") in ("rate_drift", "rate_spike")
               and not a.get("closed")]
        for s in ("warning", "watch", "good"):
            if s in sev:
                return SEV_ST[s]
        r, lo, hi = host.get("last7"), host.get("lo"), host.get("hi")
        if _num(r) and _num(hi) and r > hi:
            return "dhyan"
        if _num(r) and _num(lo) and r < lo:
            return "behtar"
        return "normal"
    if "status" in host:
        return ROW_ST.get(host.get("status"))
    if "st" in host:
        return TILE_ST.get(host.get("st"))
    return None


def _form(x):
    """"pct" (the parts as % of the before total) or "count" (as numbers a day / week): counts when a % would mislead —
    a part at −100% or below, or the per-user % more than 1.5× / under ⅔ of its own per-unit change (or the other way:
    installs moved a lot, and the Δinstalls × Δrate part is measured on today's installs)."""
    s = x["shown"]
    if min(s["from_installs"], s["per_user"], s["trend"] if s["trend"] is not None else 0) <= -100:
        return "count"
    own, p = x["per_user"]["own"], x["per_user"]["rel"]
    if x["code"] in MULT and own is not None and (abs(own) >= 0.05 or abs(p) >= 0.05):
        if own == 0 or p / own < COUNT_LO - 1e-9 or p / own > COUNT_HI + 1e-9:     # (the bounds themselves: a %)
            return "count"
    return "pct"


def _counts(x):
    """The parts as numbers: integers × 10^exp, exp = 2 significant digits of the largest; per_user = total − the
    others, so they add up as printed."""
    D, F, P = x["total"]["abs"], x["from_installs"]["abs"], x["per_user"]["abs"]
    T = x["trend"]["abs"] if x["trend"] else None
    M = max(abs(D), abs(F), abs(P), abs(T or 0.0))
    e = int(math.floor(math.log10(M))) - 1 if M > 0 else 0

    def n(v):
        return R(v * 10 ** -e) if e < 0 else R(v / 10 ** e)
    nD, nF = n(D), n(F)
    nT = n(T) if T is not None else None
    return {"exp": e, "total": nD, "from_installs": nF, "trend": nT, "per_user": nD - nF - (nT or 0)}


def _agree(x, st):
    """The copied verdict word, kept only when the per-user part points its way: a worse / watch word with a part that
    moved the bad way, a better word with one that moved the good way — a word never contradicts its own line."""
    if st not in ("bigda", "dhyan", "behtar"):
        return st
    c = x["shown"]["count"]
    p = c["per_user"] if c else x["shown"]["per_user"]
    bad, good = (p > 0, p < 0) if x["code"] in BAD_UP else (p < 0, p > 0)
    return st if (bad if st != "behtar" else good) else None


def _finish(x, st):
    x["form"] = _form(x)
    x["shown"]["count"] = _counts(x) if x["form"] == "count" else None
    x["per_user"]["status"] = _agree(x, st)
    return x


def _rate_parts(ib, ia, rb, ra):
    _need(ib, ia, rb, ra)
    out = _core(ib * rb, ia * ra, (ia - ib) * rb)
    out["installs"] = _inst(ib, ia)
    out["per100"] = {"n": 100, "before": 100 * rb, "after": 100 * ra, "k": None}
    out["per_user"]["own"] = (ra / rb - 1) if rb > 0 else None
    out["on_now"] = {"installs": ia, "abs": out["per_user"]["abs"]}
    return out


def _host_rates(host):
    if isinstance(host.get("recent"), dict):              # uninstall table row: the base its arrow shows
        base = host.get("prev") or host.get("all") or {}
        return base.get("p"), host["recent"].get("p")
    if "p" in host and "prev" in host:                    # head4 cell
        return host.get("prev"), host.get("p")
    if "now" in host:                                     # alert / old change
        b, a = host.get("before"), host.get("now")
        if host.get("family") == "geo_move" and _num(b) and _num(a):
            b, a = b / 100, a / 100
        return b, a
    return host.get("before"), host.get("after")          # impact row


def _expand(kind, host, k=None, days=None, alerts=None):
    code = KINDS[kind]
    sp = host.get("sp")
    derived = kind in ("imp_rate", "uni_verdict") or (kind == "act_tile_rr" and not sp)
    if not derived:
        if not isinstance(sp, list) or not sp:
            return None
        if sp[0] == "no":
            c = code or "ur"
            return {"v": V, "code": c, "basis": BASIS.get(c), "none": sp[1] if len(sp) > 1 else "error"}
        if code is None:
            code = sp[0]
        if sp[0] != code:
            return None
    if code == "pu":
        return {"v": V, "code": "pu", "basis": BASIS["pu"], "note": [list(x) for x in sp[1:]]}
    st = status_of(kind, host, alerts)
    if kind in ("imp_rate", "imp_dau") or (kind == "rate" and "status" in host) or (kind == "rev" and "status" in host):
        if host.get("status") not in JUDGED:
            return None
    out = {"v": V, "code": code, "basis": BASIS[code], "per": "week" if code in WEEKLY else "day", "days": None,
           "installs": None, "trend": None, "per100": None, "on_now": None, "form": "pct", "est": False, "mode": None,
           "note": []}
    try:
        if code == "ret":
            fi, yb, yw, nb, na, pb, pa, kk, fl = sp[1:10]
            if kind == "act_tile_ret":
                before, after = host.get("base"), host.get("v")
            elif kind == "act_alert_ret":
                before, after = host.get("before"), host.get("now")
            elif kind == "act_info_ret":
                before = sp[10]
                _need(before, host.get("rel"))
                after = before * (1 + host["rel"])
            else:
                s = host.get("s") or [None] * 4
                _need(*s)
                if s[1] <= 0 or s[3] <= 0:
                    raise _None("few")
                before, after = s[2] / s[3], s[0] / s[1]
            _need(fl)
            body = _core(before, after, fi)
            body["installs"] = _inst(nb, na)
            mode = "elastic" if int(fl) & 2 else "cohort"
            if _num(pb) and _num(pa):
                body["per100"] = {"n": 100, "before": pb, "after": pa, "k": k if k is not None else kk}
            if mode == "cohort" and _num(yb) and _num(yw) and before - yb > 0:
                body["per_user"]["own"] = (after - yw) / (before - yb) - 1       # the 30+ day old users themselves
            out.update(body, est=bool(int(fl) & 1), mode=mode)
        elif code in ("rr", "ur", "uk"):
            if kind == "imp_rate":
                ex = host.get("extra") or {}
                _need(ex.get("installs_before"), ex.get("cohorts_before"), ex.get("installs_after"),
                      ex.get("cohorts_after"))
                if not ex["cohorts_before"] or not ex["cohorts_after"]:
                    raise _None("few")
                ib, ia = ex["installs_before"] / ex["cohorts_before"], ex["installs_after"] / ex["cohorts_after"]
                rb, ra = host.get("before"), host.get("after")
            elif kind == "uni_verdict":
                p, r = host.get("prev") or {}, host.get("recent") or {}
                _need(p.get("users"), p.get("k"), r.get("users"), r.get("k"))
                if not p["k"] or not r["k"]:
                    raise _None("few")
                ib, ia, rb, ra = p["users"] / p["k"], r["users"] / r["k"], p.get("left"), r.get("left")
            elif kind == "act_tile_rr":
                s = host.get("s") or [None] * 4
                _need(*s)
                if s[1] <= 0 or s[3] <= 0:
                    raise _None("few")
                rb, ra = s[2] / s[3], s[0] / s[1]
                if isinstance(sp, list) and len(sp) >= 3 and sp[0] == "rr":
                    ib, ia = sp[1], sp[2]
                else:
                    _need(host.get("n"), host.get("nb"))
                    if not host["n"] or not host["nb"]:
                        raise _None("few")
                    ib, ia = s[3] / host["nb"], s[1] / host["n"]
            else:
                ib, ia = sp[1], sp[2]
                rb, ra = _host_rates(host)
            out.update(_rate_parts(ib, ia, rb, ra), days=_days_of(host, days, kind))
        elif code == "imp":
            fi, tr = sp[1], sp[2]
            before, after = host.get("before"), host.get("after")
            body = _core(before, after, fi, tr)
            if len(sp) >= 5:
                body["installs"] = _inst(sp[3], sp[4])
            ex = host.get("expected")
            if _num(ex) and ex > 0:
                body["per_user"]["own"] = after / ex - 1
            out.update(body, mode="cohort")
        elif code == "uc":
            ub, ua, xb, xa, nb, na, p100 = sp[1:8]
            _need(ub, ua, xb, xa)
            if xb <= 0 or xa <= 0 or ub <= 0:
                raise _None("base")
            body = _core(ub, ua, ub * (xa / xb - 1))
            body["installs"] = _inst(nb, na)
            body["per100"] = {"n": 100, "before": p100, "after": None, "k": 28} if _num(p100) else None
            body["per_user"]["own"] = ua / xa - 1               # the alert's own per-install change (calibrated xa)
            out.update(body)
        elif code == "rev":
            ub, ua = sp[1], sp[2]
            if kind == "rev" and "status" in host:           # impact 7-day row
                ab, aa = host.get("before"), host.get("after")
            else:                                            # Active tile
                ab, aa = host.get("base"), host.get("v")
            _need(ub, ua, ab, aa)
            body = _core(ub * ab / 1000, ua * aa / 1000, (ua - ub) * ab / 1000)
            body["installs"] = _inst(ub, ua, "users")
            body["per100"] = {"n": 1000, "before": ab, "after": aa, "k": None}
            body["per_user"]["own"] = (aa / ab - 1) if ab > 0 else None
            out.update(body, note=[list(x) for x in sp[3:]])
        elif code == "ir":
            ib, ia = sp[1], sp[2]
            if "severity" in host:
                vb, va = host.get("before"), host.get("now")
            else:
                vb, va = host.get("base"), host.get("v")
            _need(ib, ia, vb, va)
            body = _core(ib * vb, ia * va, (ia - ib) * vb)
            body["installs"] = _inst(ib, ia)
            body["per100"] = {"n": 1, "before": vb, "after": va, "k": None}
            body["per_user"]["own"] = (va / vb - 1) if vb > 0 else None
            out.update(body)
        elif code == "spd":
            ib, ia, cb, ca = sp[1:5]
            _need(ib, ia, cb, ca)
            body = _core(ib * cb, ia * ca, (ia - ib) * cb)
            body["installs"] = _inst(ib, ia)
            body["per100"] = {"n": 1, "before": cb, "after": ca, "k": None}
            body["per_user"]["own"] = (ca / cb - 1) if cb > 0 else None
            out.update(body)
        elif code == "vpi":
            vb, va, cb, ca = sp[1:5]
            _need(vb, va, cb, ca)
            if cb <= 0 or ca <= 0 or vb <= 0:
                raise _None("base")
            before = 100 * vb / cb
            body = _core(before, 100 * va / ca, before * (cb / ca - 1))
            body["installs"] = _inst(cb, ca, "cost")
            body["per100"] = {"n": 1, "before": vb, "after": va, "k": None}
            body["per_user"]["own"] = va / vb - 1
            out.update(body)
        else:
            return None
    except _None as e:
        return {"v": V, "code": code, "basis": BASIS[code], "none": e.reason}
    return _finish(out, st)


def expand(kind, host, k=None, days=None, alerts=None):
    """The host's split (the module docstring's expanded form), {"none": reason} when it can't be computed, or None
    when the host carries no split. k = the return days K behind a "ret" per-100 (Active daily.old_k); days = the N of a
    rate host that does not carry it (a head4 cell, an impact row); alerts = the app's open alerts (rate_now's status).
    Never raises."""
    try:
        if not isinstance(host, dict) or kind not in KINDS:
            return None
        return _expand(kind, host, k, days, alerts)
    except Exception:
        return None


def pool(ms):
    """The All-apps pooled Returning-users split over the visible apps' row m.ret_dau (with or without a split; the
    caller leaves out a stale app, and a waiting / no-data one is left out here — the same apps the tile adds up) →
    the expanded form + "apps": {"of": apps with a before level, "with": apps whose split is counted}, or
    {"none": "apps"} when the covered apps hold < POOL_MIN of the pooled before level, or None without any."""
    try:
        allb = cov = 0.0
        of = 0
        S = {"b": 0.0, "a": 0.0, "fi": 0.0, "yb": 0.0, "yw": 0.0, "nb": 0.0, "na": 0.0, "db": 0.0, "da": 0.0}
        n, p100, est, modes, ks = 0, True, False, set(), set()
        for m in ms:
            m = m or {}
            s = m.get("s")
            if m.get("st") in ("wait", "noad") or not s or len(s) < 4 or not all(_num(x) for x in s) or s[1] <= 0 \
                    or s[3] <= 0:
                continue
            b, a = s[2] / s[3], s[0] / s[1]
            of += 1
            allb += b
            sp = m.get("sp")
            if not isinstance(sp, list) or len(sp) < 10 or sp[0] != "ret":
                continue
            fi, yb, yw, nb, na, pb, pa, kk, fl = sp[1:10]
            if not all(_num(x) for x in (fi, yb, yw, nb, na, fl)):
                continue
            n += 1
            cov += b
            S["b"], S["a"], S["fi"], S["yb"], S["yw"] = S["b"] + b, S["a"] + a, S["fi"] + fi, S["yb"] + yb, S["yw"] + yw
            S["nb"], S["na"] = S["nb"] + nb, S["na"] + na
            est = est or bool(int(fl) & 1)
            modes.add("elastic" if int(fl) & 2 else "cohort")
            ks.add(kk)
            if _num(pb) and _num(pa) and pb > 0 and pa > 0 and yb > 0 and yw > 0:
                S["db"] += 100 * yb / pb
                S["da"] += 100 * yw / pa
            else:
                p100 = False
        if not of:
            return None
        if not n or allb <= 0 or cov < POOL_MIN * allb:
            return {"v": V, "code": "ret", "basis": BASIS["ret"], "none": "apps", "apps": {"of": of, "with": n}}
        out = {"v": V, "code": "ret", "basis": BASIS["ret"], "per": "day", "days": None, "installs": None,
               "trend": None, "per100": None, "on_now": None, "form": "pct", "est": est,
               "mode": "cohort" if modes == {"cohort"} else "elastic" if modes == {"elastic"} else "mixed",
               "note": [], "apps": {"of": of, "with": n}}
        out.update(_core(S["b"], S["a"], S["fi"]))
        out["installs"] = _inst(S["nb"], S["na"])
        if p100 and S["db"] > 0 and S["da"] > 0:
            k1 = next(iter(ks)) if len(ks) == 1 else None
            out["per100"] = {"n": 100, "before": 100 * S["yb"] / S["db"], "after": 100 * S["yw"] / S["da"],
                             "k": k1 if _num(k1) else None}
        if modes == {"cohort"} and S["b"] - S["yb"] > 0:
            out["per_user"]["own"] = (S["a"] - S["yw"]) / (S["b"] - S["yb"]) - 1
        return _finish(out, None)
    except Exception:
        return None


# ── the compact one-liner (Alerts cards, tooltips, Telegram) ────────────────────────────────────────

def pct(n):
    """A shown integer % with its sign: "+20%", "−12%" (U+2212), "0%"."""
    return ("+%d%%" % n) if n > 0 else ("−%d%%" % -n) if n < 0 else "0%"


# what the one-liner counts, named first (its "kul" is that count's change, never the headline's rate or per-1,000)
# (the page's SPLIT_SUBJ / SPLIT_FW / SPLIT_PW must say the very same words — tests/test_split_frontend compares the
# lines). "ur" counts the PEOPLE uninstalling a day (F12) — never "uninstall rate", which is the headline's rate.
SUBJ = {"ret": "old users, daily", "imp": "old users, daily", "uc": "daily uninstalls", "ur": "daily uninstalls",
        "uk": "still in app, daily", "rr": "daily returns", "rev": "daily revenue", "ir": "weekly revenue",
        "spd": "weekly ads spend", "vpi": "money back", "dau": "active users"}
F_WORD = {"rev": "from users", "vpi": "from price", "dau": "from new installs"}
P_WORD = {"imp": "update", "vpi": "from revenue", "dau": "from old users"}


def _fix(y, n):
    """y (≥ 0) to n decimals exactly as the page's toFixed does it: from the float's exact binary value, a tie up."""
    return str(Decimal(y).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


def num(a):
    """A count as the page writes it (splitNum, a ≥ 0): "12.5 lakh" · "1.22 lakh" · "18,003" · "3.4"."""
    def d1(y):
        t = _fix(y, 1)
        return t[:-2] if t.endswith(".0") else t

    def d(y):
        if y >= 10:
            return d1(y)
        t = _fix(y, 2)
        return t.rstrip("0").rstrip(".") if "." in t else t
    if a >= 1e7:
        return d(a / 1e7) + " crore"
    if a >= 1e5:
        return d(a / 1e5) + " lakh"
    if a < 10:
        return d1(a)
    return "{:,}".format(int(math.floor(a + 0.5)))


def cnum(n, e):
    """An integer n × 10^e as an about-number with its sign, its decimals the unit's (so the parts add up as printed):
    "~+180" · "~−1.5 lakh" · "~+0.85" · "~0"."""
    sg = "+" if n > 0 else "−" if n < 0 else ""
    if e >= 0:
        return "~" + sg + num(abs(n) * 10 ** e)
    t = str(abs(n)).rjust(-e + 1, "0")
    t = (t[:e] + "." + t[e:]).rstrip("0").rstrip(".")
    return "~" + sg + t


def line(split):
    """The one-liner, its counted thing first and the parts as an equation that adds up as printed:
    `daily returns: kul +8% = from installs +20% + real −12%` (≤ 12 words); from users … (revenue total), from price …
    + from revenue … (money back), from installs … + trend … + update … (update impact; the trend only when its shown %
    isn't 0). The count form: `daily uninstalls: ~−150 = from installs ~−180 + real ~+30 (kul −75%)` (a money split in the
    count form has none: its amounts need the page's currency). "" for none / notes only / no split."""
    try:
        if not split or split.get("none") or "shown" not in split:
            return ""
        s, code = split["shown"], split.get("code")
        c = s.get("count") if split.get("form") == "count" else None
        if c and code in MONEY:
            return ""
        f = (lambda k: cnum(c[k], c["exp"])) if c else (lambda k: pct(s[k]))
        parts = [F_WORD.get(code, "from installs") + " " + f("from_installs")]
        if (c or s)["trend"]:
            parts.append("trend " + f("trend"))
        parts.append(P_WORD.get(code, "real") + " " + f("per_user"))
        subj = SUBJ.get(code, "kul")
        if c:
            return "%s: %s = %s (kul %s)" % (subj, cnum(c["total"], c["exp"]), " + ".join(parts), pct(s["total"]))
        return "%s: kul %s = %s" % (subj, pct(s["total"]), " + ".join(parts))
    except Exception:
        return ""


def alert_kind(a):
    """The expand kind of an alert object's split (None: no split, and never for an update-impact alert)."""
    if not isinstance(a, dict) or a.get("family") in ("impact", "impact_late"):
        return None
    sp = a.get("sp")
    if not isinstance(sp, list) or not sp:
        return None
    return {"ret": "act_alert_ret", "ur": "rate", "rr": "rate", "uc": "uc", "vpi": "vpi", "ir": "ir",
            "pu": "pu"}.get(sp[0])


def alert_line(a):
    """An alert's compact split line for Telegram / e-mail ("" when none, or the switch is off)."""
    if not ON:
        return ""
    try:
        k = alert_kind(a)
        return line(expand(k, a)) if k else ""
    except Exception:
        return ""
