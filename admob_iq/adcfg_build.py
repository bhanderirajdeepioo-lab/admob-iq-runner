"""⚙️ Ad setting changes ("Ad setting badlav") — the build step (engine/adcfg.py does the measuring). Owner, 16 Oct 2026:
"aaj se start karo naapna" — frequency caps, splash / app-open, after-call … found in the data (Remote Config may not
be read). Runs inside the 📈 ROI step: roi_build.app_step calls app_step() for each app BEFORE its 🔮 forecast, with
the app's Uninstall store already in memory (GA4 DAU, versions, app_update users) and the build's own AdMob reports
(build_static hands them over as adcfg.Source: the mediation ad-unit report + the country report, no extra call).

Every build (hourly; the reports' days up to the last complete AdMob day, so the result moves once a day): the app's
FULL history is scanned (the backfill is just the first run) → its events. Kept for good in the private repo,
data/adcfg/<key>.json: every event with the build day it was first seen ("seen"; "bf" 1 = a backfill find, never
"new today": already older than BF_DAYS when first found, or — on the app's first run — old enough that yesterday's
data would have shown it too), the "checking" ones that did not hold (missing on MISS new data days in a row: status
"reverted", the day they went; one that is found again later is the same row again, its "seen" kept) and the steps
the country mix, the new users or GA4's users count explained (dropped, "why", for the record). Returned: the events,
the forecast's material steps (adcfg.fc_steps: its back-tests label them) and the page block (page(): Install value →
🔮 Forecast → "why", the "Ad setting badlav" list, the weekly ads-per-user chart's series and which back-tests had a
change inside).
"many apps": other apps' events within ±MERGE days the same way — this build's apps so far + every stored file.
Failure-isolated: an app's error costs only its block (counted). ONE counts-only log line (line())."""
import json
import os
from datetime import date, datetime, timedelta, timezone

from .engine import adcfg as A

DIR = "adcfg"
V = 1
BF_DAYS = 35                  # an event older than this when first found is a backfill find (not "new")
MISS = 3                      # a "checking" event missing on 3 new data days in a row did not hold: reverted
GONE_KEEP = 60                # reverted events kept per app (newest)
PAGE_FMTS = 4                 # the chart: the formats carrying the most revenue, at most this many
PAGE_ITEMS = 4                # per event: the steps listed under it (largest first)


def _path(data_dir, *p):
    return os.path.join(data_dir, DIR, *p)


def _read(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    try:
        with open(path, encoding="utf-8") as f:
            if f.read() == text:
                return
    except OSError:
        pass
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Run:
    def __init__(self, src, data_dir, now):
        self.src, self.data_dir, self.now = src, data_dir, now
        self.today = now.date().isoformat()
        self.others = {}                                 # key → [(iso day, up)] of every app's events
        self.apps = self.events = self.checking = self.with_update = self.new = self.fails = 0
        try:
            for f in sorted(os.listdir(_path(data_dir))):
                if f.endswith(".json") and len(f) == 17:
                    st = _read(_path(data_dir, f), {})
                    self.others[f[:12]] = [(e["d"], (e.get("j") or 0) > 0) for e in st.get("events") or []
                                           if e.get("d")]
        except OSError:
            pass


def start(src, data_dir, now=None):
    return Run(src, data_dir, now or datetime.now(timezone.utc))


def _same(a, b):
    """Two finds of one event (another build's): the same format, the same direction, within a week."""
    return (a.get("fmt") == b.get("fmt") and ((a.get("j") or 0) > 0) == ((b.get("j") or 0) > 0)
            and abs((date.fromisoformat(a["d"]) - date.fromisoformat(b["d"])).days) <= 7)


def merge(old, evs, today, till=None):
    """Today's events + the stored file → (events with their "seen" (the build day first found) / "bf" (1: a backfill
    find — already older than BF_DAYS when first found, or on the app's first run (no stored file) a day before
    till − (EARLY − 1): yesterday's data would have shown it too — never "new today"), reverted ones). till: the
    data's last day (None: every call a new data day). Each event is matched to the stored ones (_same) and to the
    reverted ones (found again: that row back, its "seen" / "bf" kept — never the same change twice). A stored
    "checking" event today's scan does not find stays a "checking" row (its "miss" days counted, one per new data day;
    found again → reset) and is "reverted" (the day it went) once it is missing on MISS new data days in a row."""
    prev = list(old.get("events") or [])
    gone = list(old.get("gone") or [])
    new_day = till is None or old.get("till") != till
    out, used, back = [], set(), set()
    old_day = (date.fromisoformat(today) - timedelta(days=BF_DAYS)).isoformat()
    fresh = (date.fromisoformat(till) - timedelta(days=A.EARLY - 1)).isoformat() if till and not old else None
    for e in evs:
        k = next((i for i, p in enumerate(prev) if i not in used and _same(e, p)), None)
        g = None if k is not None else next((i for i, p in enumerate(gone) if i not in back and _same(e, p)), None)
        if k is not None:
            used.add(k)
            e = dict(e, seen=prev[k].get("seen") or today, bf=prev[k].get("bf", 0))
        elif g is not None:
            back.add(g)
            e = dict(e, seen=gone[g].get("seen") or today, bf=gone[g].get("bf", 0))
        else:
            e = dict(e, seen=today, bf=1 if e["d"] < old_day or (fresh and e["d"] < fresh) else 0)
        out.append(e)
    gone = [p for i, p in enumerate(gone) if i not in back]
    for i, p in enumerate(prev):
        if i in used or p.get("st") != "checking":
            continue
        miss = (p.get("miss") or 0) + (1 if new_day else 0)
        if miss < MISS:
            out.append(dict(p, miss=miss))           # (one noisy day does not flip it: still checking)
        elif not any(_same(p, x) for x in gone):
            gone.append(dict(p, st="reverted", gone=today, miss=miss))
    out.sort(key=lambda e: (e["d"], e.get("fmt") or ""))
    return out, gone[-GONE_KEEP:]


def app_step(run, aid, key, store, ids=None):
    """One app → {"events", "steps", "page"} (None: nothing to scan). Never raises."""
    try:
        ids = list(dict.fromkeys([aid] + list(ids or [])))
        ad = run.src.app(ids)
        dau = A.dau_of(store)
        if not ad.get("days") or not dau:
            return None
        rels = A.releases_of(store)
        cty = run.src.country(ids) if run.src.cty else None
        dropped = []
        evs = A.detect(ad, dau, rels, cty, dropped=dropped, new=A.new_of(store))
        A.finish(evs, [x for k, xs in run.others.items() if k != key for x in xs])
        run.others[key] = [(e["d"], (e.get("j") or 0) > 0) for e in evs]
        path = _path(run.data_dir, key + ".json")
        old = _read(path, {})
        first = old.get("first") or run.today
        till = max(set(ad["days"]) & set(dau))
        evs, gone = merge(old, evs, run.today, till)
        body = {"v": V, "app_id": aid, "first": first, "till": till, "events": evs, "gone": gone,
                "dropped": [{k: e.get(k) for k in ("d", "fmt", "unit", "m", "j", "why", "mix", "nu", "brk")}
                            for e in dropped]}
        if old.get("till") != till or old.get("events") != evs or old.get("gone") != gone or not old.get("made"):
            body["made"] = run.today
        else:
            body["made"] = old["made"]
        _write(path, body)
        run.apps += 1
        run.events += len(evs)
        run.checking += sum(1 for e in evs if e["st"] == "checking")
        run.with_update += sum(1 for e in evs if e.get("rel"))
        run.new += sum(1 for e in evs if e.get("seen") == run.today and not e.get("bf"))
        return {"events": evs, "gone": gone, "steps": A.fc_steps(evs), "till": till, "first": first,
                "made": run.today, "wk": A.weekly(ad, dau, _top_formats(ad, dau))}
    except Exception:
        run.fails += 1
        return None


def _top_formats(ad, dau):
    rev = {}
    for f, by in (ad.get("f") or {}).items():
        rev[f] = sum(x[3] for d, x in by.items() if d in dau)
    tot = sum(rev.values())
    return [f for f, v in sorted(rev.items(), key=lambda kv: -kv[1]) if tot > 0 and v / tot >= A.FMT_SHARE][:PAGE_FMTS]


def _ev_out(e):
    keep = ("d", "st", "lvl", "fmt", "unit", "trig", "m", "j", "j2", "kind", "conf", "cty", "wide", "rx", "seen", "bf",
            "na", "ramp", "z", "gone", "miss", "nu", "brk")
    o = {k: e.get(k) for k in keep if e.get(k) is not None}
    o["b"] = {k: v for k, v in (e.get("b") or {}).items() if v is not None}
    o["a"] = {k: v for k, v in (e.get("a") or {}).items() if v is not None}
    for k in ("rel", "near"):
        if e.get(k):
            o[k] = {"d": e[k].get("d"), "v": e[k].get("v")}
    if e.get("mix"):
        o["mix"] = e["mix"]
    for k in ("on", "off"):
        if e.get(k):
            o[k] = list(e[k])[:3]
    o["items"] = [x for x in (e.get("items") or [])][:PAGE_ITEMS]
    return o


def page(res, fc=None, ax=0):
    """The page block (fc["acfg"]): the events newest first (+ the reverted ones), the weekly ads-per-user series, the
    forecast's material steps and which of its back-tests had one inside ({"30": [origin, …], …}; the chips outside
    30 / 90 / 180 from fc.hz.btx), ax = whether the forecast counts them as its sudden changes (forecast_vd.AX)."""
    if not res:
        return None
    evs = sorted([_ev_out(e) for e in res["events"]] + [_ev_out(g) for g in res.get("gone") or []],
                 key=lambda e: (e["d"], e.get("fmt") or ""), reverse=True)
    steps = res.get("steps") or []
    bt = {}
    if fc:
        hs = [30, 90, 180]
        ors = [r[0] for r in fc.get("bt") or [] if r]
        lab = A.labels(ors, steps, hs)
        for T, by in lab.items():
            for h in by:
                bt.setdefault(str(h), []).append(T)
        for h, rows in (((fc.get("hz") or {}).get("btx")) or {}).items():
            lab = A.labels([r[0] for r in rows if r], steps, [int(h)])
            bt[str(h)] = sorted(T for T in lab)
        bt = {h: sorted(v) for h, v in bt.items() if v}
    conf = [e for e in res["events"] if e.get("st") == "confirmed"]
    return {"v": V, "made": res.get("made"), "till": res.get("till"), "first": res.get("first"), "ev": evs,
            "wk": res.get("wk"),
            "steps": [{"at": s["at"], "x": s["x"], "fmt": s["fmt"]} for s in steps], "bt": bt, "ax": int(ax),
            "mat": A.MATERIAL, "mx": MISS,
            "n": {"all": len(res["events"]), "conf": len(conf), "chk": len(res["events"]) - len(conf),
                  "rel": sum(1 for e in res["events"] if e.get("rel")), "gone": len(res.get("gone") or [])}}


def line(run):
    """The build log's line: counts only."""
    return ("ad settings: apps %d, events %d (checking %d, with update %d), new today %d, failed %d"
            % (run.apps, run.events, run.checking, run.with_update, run.new, run.fails))
