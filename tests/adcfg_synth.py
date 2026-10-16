"""⚙️ Ad setting changes — a SYNTHETIC app (made up here: no real names, ids or money) in the shape of the build's own
inputs: AdMob mediation ad-unit rows, AdMob country rows and a GA4 Uninstall store (daily active users, app versions,
app_update users). Every number comes from a seeded random walk, and the truth — which ad settings really changed,
when, how — is returned beside it, so the detector's precision and recall can be measured.

make(seed, …) → {"mu": rows, "cty": rows, "store": store, "truth": [real changes], "decoys": [moves that are NOT ad
setting changes], "app_id", "till"}. Real changes: "cap" (a unit's ads per user × k from a day on), "off" (a unit
stops), "on" (a new unit starts), "sdk" (a format's fill × k), "rel" (an update that changes a unit's ads for the
users who take it: the app's ads follow the version's adoption). Decoys: "spike" (one day × 3), "dip" (6 days ×
0.5, then back), "ecpm" (the price × 1.6, ads the same), "mix" (one low-ads country's users × 4: fewer ads per user
for the app, the same in every country), "drift" (+40 % over 150 days), "relnull" (an update that changes nothing,
on the day of a real "cap"); only in an explicit schedule (never in plan(): the seeds' apps stay as they were):
"surge" (new users × 2 for 60 days, the app's users + 5 %: with onb=k the app has an onboarding unit showing k ads
per NEW user, so its ads per daily user step up and back with no setting moved) and "users" (GA4's users count — its
DAU and new users — × 0.45 from a day on, every ad the same: each ads per user series × 2.2); and a real change for
them: "onbcap" (the onboarding unit's ads per new user × 1.8)."""
import math
import random
from datetime import date, timedelta

APP = "ca-app-pub-0000000000000000~1111111111"
UNITS = [  # (id, name, format, ads per user, fill, show, eCPM USD)
    ("u1", "Demo_Splash_Open", "app_open", 0.35, 0.93, 0.55, 8.0),
    ("u2", "Demo_Resume_Open", "app_open", 0.20, 0.93, 0.30, 7.0),
    ("u3", "Demo_Inter_Home", "interstitial", 0.30, 0.95, 0.45, 6.0),
    ("u4", "Demo_Inter_Exit", "interstitial", 0.15, 0.95, 0.40, 5.0),
    ("u5", "Demo_Banner_Main", "banner", 2.00, 0.97, 0.95, 0.8),
    ("u6", "Demo_Native_Cad", "native", 0.80, 0.90, 0.60, 2.0),
    ("u7", "Demo_Native_Lang", "native", 0.30, 0.90, 0.60, 2.5),
]
NEW_UNIT = ("u8", "Demo_Inter_Settings", "interstitial", 0.25, 0.95, 0.45, 5.5)
ONB_UNIT = ("u9", "Demo_Native_Onboarding", "native", None, 0.90, 0.60, 2.5)   # (ads per NEW user: make(onb=k))
UNIT_BASE = {u[0]: (u[4], u[5]) for u in UNITS + [NEW_UNIT, ONB_UNIT]}
COUNTRIES = (("AA", 0.45, 1.25), ("BB", 0.35, 1.0), ("CC", 0.20, 0.30))   # (code, users share, ads factor)


def _iso(d):
    return d.isoformat()


def plan(rng, n, start_i=70):
    """A random schedule of real changes and decoys over n days (each ≥ 45 days from the last; the first after
    start_i)."""
    kinds = ["cap", "cap", "cap", "off", "on", "sdk", "rel", "spike", "dip", "ecpm", "mix", "drift", "relnull"]
    rng.shuffle(kinds)
    out, i = [], start_i
    for k in kinds:
        if i >= n - 40:
            break
        out.append((k, i))
        i += 45 + rng.randint(0, 15)
    return out


def make(seed=1, n=520, start="2025-01-06", sched=None, sigma=0.07, dau0=60000, onb=0):
    rng = random.Random(seed)
    d0 = date.fromisoformat(start)
    days = [d0 + timedelta(days=i) for i in range(n)]
    sched = plan(rng, n) if sched is None else sched
    units = {u[0]: {"name": u[1], "fmt": u[2], "ipu": [u[3]] * n, "fill": [u[4]] * n, "show": [u[5]] * n,
                    "ecpm": [u[6]] * n} for u in UNITS}
    nu = NEW_UNIT
    units[nu[0]] = {"name": nu[1], "fmt": nu[2], "ipu": [0.0] * n, "fill": [nu[4]] * n, "show": [nu[5]] * n,
                    "ecpm": [nu[6]] * n}
    if onb:                                          # an onboarding unit: onb ads per NEW user (its ads per user
        ou = ONB_UNIT                                # set day by day from the new users, below)
        units[ou[0]] = {"name": ou[1], "fmt": ou[2], "ipu": [0.0] * n, "fill": [ou[4]] * n, "show": [ou[5]] * n,
                        "ecpm": [ou[6]] * n}
    nk, gk, onbk = [1] * n, [1.0] * n, [1.0] * n     # new users × (a surge); GA4's users × (a break); onboarding ×
    mult = {u: [1.0] * n for u in units}            # one day / a few days only (decoys)
    share_b = [COUNTRIES[2][1]] * n                  # the low-ads country's share of users
    vers = [None] * n                                # (version, its share) per day
    rel_k, rel_unit = [1.0] * n, None
    truth, decoys = [], []
    big = ["u1", "u3", "u5", "u6"]
    for kind, i in sched:
        if kind == "cap":
            u = rng.choice(big)
            k = rng.choice([0.45, 0.55, 0.65, 1.5, 1.7, 2.0])
            for t in range(i, n):
                units[u]["ipu"][t] *= k
            truth.append({"kind": "cap", "i": i, "d": _iso(days[i]), "unit": u, "fmt": units[u]["fmt"], "k": k})
        elif kind == "off":
            u = rng.choice(["u2", "u4", "u7"])
            for t in range(i, n):
                units[u]["ipu"][t] = 0.0
            truth.append({"kind": "off", "i": i, "d": _iso(days[i]), "unit": u, "fmt": units[u]["fmt"], "k": 0.0})
        elif kind == "on":
            for t in range(i, n):
                units["u8"]["ipu"][t] = nu[3]
            truth.append({"kind": "on", "i": i, "d": _iso(days[i]), "unit": "u8", "fmt": nu[2], "k": None})
        elif kind == "sdk":
            f = rng.choice(["interstitial", "app_open"])
            for u, x in units.items():
                if x["fmt"] == f:
                    for t in range(i, n):
                        x["fill"][t] *= 0.55
            truth.append({"kind": "sdk", "i": i, "d": _iso(days[i]), "unit": None, "fmt": f, "k": 0.55})
        elif kind == "rel":
            rel_unit = rng.choice(["u3", "u6"])
            k = rng.choice([0.4, 1.9])
            for t in range(i - 6, n):
                sh = 0.9 / (1 + math.exp(-(t - i) / 2.2))
                vers[t] = ("2.%d" % i, sh)
                rel_k[t] = 1 + sh * (k - 1)
            truth.append({"kind": "rel", "i": i, "d": _iso(days[i]), "unit": rel_unit, "fmt": units[rel_unit]["fmt"],
                          "k": k, "ver": "2.%d" % i})
        elif kind == "relnull":                     # an update with no ad change, on the day of a real cap
            for t in range(i - 6, n):
                sh = 0.9 / (1 + math.exp(-(t - i) / 2.2))
                vers[t] = ("3.%d" % i, sh)
            u = rng.choice(big)
            k = rng.choice([0.5, 1.8])
            for t in range(i, n):
                units[u]["ipu"][t] *= k
            truth.append({"kind": "cap", "i": i, "d": _iso(days[i]), "unit": u, "fmt": units[u]["fmt"], "k": k,
                          "relnull": "3.%d" % i})
        elif kind == "spike":
            u = rng.choice(big)
            mult[u][i] *= 3.0
            decoys.append({"kind": "spike", "i": i, "d": _iso(days[i]), "fmt": units[u]["fmt"]})
        elif kind == "dip":
            u = rng.choice(big)
            for t in range(i, min(n, i + 6)):
                mult[u][t] *= 0.5
            decoys.append({"kind": "dip", "i": i, "d": _iso(days[i]), "fmt": units[u]["fmt"]})
        elif kind == "ecpm":
            f = rng.choice(["app_open", "interstitial", "banner", "native"])
            for u, x in units.items():
                if x["fmt"] == f:
                    for t in range(i, n):
                        x["ecpm"][t] *= 1.6
            decoys.append({"kind": "ecpm", "i": i, "d": _iso(days[i]), "fmt": f})
        elif kind == "mix":
            for t in range(i, n):
                share_b[t] = 0.5
            decoys.append({"kind": "mix", "i": i, "d": _iso(days[i]), "fmt": None})
        elif kind == "surge":
            for t in range(i, min(n, i + 60)):
                nk[t] = 2
            decoys.append({"kind": "surge", "i": i, "d": _iso(days[i]), "fmt": ONB_UNIT[2]})
            if i + 60 < n:
                decoys.append({"kind": "surge end", "i": i + 60, "d": _iso(days[i + 60]), "fmt": ONB_UNIT[2]})
        elif kind == "onbcap":                       # a REAL change of the onboarding unit: ads per new user × 1.8
            for t in range(i, n):
                onbk[t] = 1.8
            truth.append({"kind": "cap", "i": i, "d": _iso(days[i]), "unit": ONB_UNIT[0], "fmt": ONB_UNIT[2], "k": 1.8})
        elif kind == "users":
            for t in range(i, n):
                gk[t] = 0.45
            decoys.append({"kind": "users", "i": i, "d": _iso(days[i]), "fmt": None})
        elif kind == "drift":
            u = rng.choice(big)
            for t in range(i, n):
                units[u]["ipu"][t] *= 1 + 0.4 * min(1.0, (t - i) / 150.0)
            decoys.append({"kind": "drift", "i": i, "d": _iso(days[i]), "fmt": units[u]["fmt"]})
    mu, cty, daily, versions = [], [], {}, {}
    rng_new = random.Random(seed * 7919 + 1)
    prev_sh = 0.0
    for t, D in enumerate(days):
        wk = (1.0, 0.99, 1.0, 1.02, 1.03, 1.05, 1.04)[D.weekday()]
        dau = int(dau0 * (1 + 0.15 * math.sin(t / 90.0)) * wk * math.exp(rng.gauss(0, 0.03)))
        # new users: ~5 % of the day's users, noisier than DAU (their own seeded stream: the ads' draws stay as
        # they were); the surge's extra new users are users of the day too
        new = int(dau // 20 * nk[t] * math.exp(rng_new.gauss(0, 0.12)))
        dau += dau // 20 * (nk[t] - 1)
        if onb:
            units[ONB_UNIT[0]]["ipu"][t] = onb * onbk[t] * new / dau
        sB = share_b[t]
        rest = 1 - sB
        cs = [(COUNTRIES[0][0], rest * COUNTRIES[0][1] / 0.8, COUNTRIES[0][2]),
              (COUNTRIES[1][0], rest * COUNTRIES[1][1] / 0.8, COUNTRIES[1][2]),
              (COUNTRIES[2][0], sB, COUNTRIES[2][2])]
        cf = sum(s * f for _, s, f in cs) / sum(s * f for _, s, f in ((c[0], c[1], c[2]) for c in COUNTRIES))
        cby = {c: [0, 0, 0, 0.0] for c, _, _ in cs}
        for u, x in units.items():
            ipu = x["ipu"][t] * mult[u][t] * cf * (rel_k[t] if u == rel_unit else 1.0)
            if ipu <= 0:
                continue
            b = UNIT_BASE[u]                             # requests per user = the unit's ads ÷ its BASE fill × show
            req = int(dau * ipu / (b[0] * b[1]) * math.exp(rng.gauss(0, sigma)))
            fill = min(0.999, x["fill"][t] * math.exp(rng.gauss(0, 0.01)))
            show = min(0.999, x["show"][t] * math.exp(rng.gauss(0, 0.02)))
            mat = int(req * fill)
            imp = int(mat * show)
            if imp <= 0:
                continue
            earn = imp * x["ecpm"][t] / 1000 * math.exp(rng.gauss(0, 0.05))
            mu.append({"account_id": "pub-0000000000000000", "ad_unit_id": "ca-app-pub-0000000000000000/" + u,
                       "app_id": APP, "app_name": "Synthetic App", "unit_name": x["name"], "format": x["fmt"],
                       "platform": "Android", "report_date": _iso(D), "ad_requests": req, "matched_requests": mat,
                       "impressions": imp, "clicks": imp // 100, "estimated_earnings_micros": int(earn * 1e6),
                       "currency_code": "USD"})
            tot = sum(s * f for _, s, f in cs)
            for c, s, f in cs:
                w = s * f / tot
                e = cby[c]
                e[0] += int(req * w)
                e[1] += int(mat * w)
                e[2] += int(imp * w)
                e[3] += earn * w
        for c, e in cby.items():
            cty.append({"account_id": "pub-0000000000000000", "app_id": APP, "app_name": "Synthetic App",
                        "country": c, "report_date": _iso(D), "ad_requests": e[0], "matched_requests": e[1],
                        "impressions": e[2], "clicks": e[2] // 100, "estimated_earnings_micros": int(e[3] * 1e6),
                        "currency_code": "USD"})
        v = vers[t]
        sh = v[1] if v else 0.0
        upd = int(dau * max(0.0, sh - prev_sh)) + int(dau * 0.002)
        prev_sh = sh
        g = gk[t]                                    # (GA4's count: the ads above saw every real user)
        daily[_iso(D)] = {"a1": int(dau * g), "a28": int(dau * 3 * g), "new": int(new * g), "un": int(dau // 40 * g),
                          "upd": upd}
        base = {"1.0": int((dau - int(dau * sh)) * g)}
        if v:
            base[v[0]] = int(int(dau * sh) * g)
        versions[_iso(D)] = base
    store = {"app_id": APP, "history_start": _iso(days[0]), "window_end": _iso(days[-1]), "daily": daily,
             "versions": versions, "flags": {}}
    return {"mu": mu, "cty": cty, "store": store, "truth": truth, "decoys": decoys, "app_id": APP,
            "till": _iso(days[-1])}


def score(events, truth, tol=3):
    """Each detected event matched to a real change of the same format within ±tol days (an update: ±tol + 2, it ramps
    with its users) and the same direction of ads per user → (matched events, unmatched events, real changes found)."""
    hit, miss, found = [], [], set()
    for e in events:
        S = date.fromisoformat(e["d"])
        up = (e["a"]["imp"] or 0) >= (e["b"]["imp"] or 0)
        best = None
        for k, t in enumerate(truth):
            gap = abs((S - date.fromisoformat(t["d"])).days)
            if gap > (tol + 2 if t["kind"] == "rel" else tol) or t["fmt"] != e["fmt"]:
                continue
            tup = (t["k"] is None) or (t["k"] > 1)
            if t["kind"] == "sdk":
                tup = False
            if tup != up:
                continue
            if best is None or gap < best[0]:
                best = (gap, k)
        if best is None:
            miss.append(e)
        else:
            hit.append((e, truth[best[1]], best[0]))
            found.add(best[1])
    return hit, miss, found
