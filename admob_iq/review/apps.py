"""Daily App Review — the build context: the selected apps (names, accounts, keys, size) and the per-app / per-day
money series every feature reads. Everything the demo scripts kept in module globals lives on one `Ctx`."""

import hashlib
import re
from collections import Counter, defaultdict
from datetime import timedelta

from .const import BADI, CHHOTI
from .fmt import D, days_back

_SUFFIX = re.compile(r"\s·\s(.+)$")


class ReviewBuildError(Exception):
    """The day cannot be built (unreadable dashboard, no selected app, or too many apps failed)."""


def file_key(app_id):
    """The same opaque key as the uninstall_c_* / active_* / value_* files (ga4_uninstall.file_key)."""
    return hashlib.sha1(str(app_id).encode("utf-8")).hexdigest()[:12]


def _acct_short(acc):
    parts = str(acc or "").split("-")
    return "A/c " + (parts[1][:4] if len(parts) > 1 else str(acc or "")[:4])


class Ctx:
    """What the demo kept in globals. Built by make_ctx(); every builder takes it as its first argument."""

    def __init__(self, site, day):
        self.site = site
        self.day = day                    # the IST review day: ages and year display are relative to it
        self.db = {}
        self.un = {}
        self.today = day
        self.admob_till = self.ga4_till = self.settled = None
        self.ga4_lag = None
        self.fx = None
        self.uapp, self.ud, self.aapp, self.vapp = {}, {}, {}, {}
        self.name2id = {}
        self.apps = {}                    # aid -> app dict (catalog order)
        self.small = set()
        self.rev = defaultdict(lambda: defaultdict(float))       # aid -> day -> USD (placements[].daily, country All)
        self.unit = {}                    # ad unit id -> placement
        self.ad = defaultdict(lambda: defaultdict(lambda: [0.0, 0, 0, 0, 0]))   # aid -> day -> [earn, impr, req, match, clicks]
        self.w7 = self.p7 = self.u7 = self.d14 = []
        self.first_run = {}
        self.ro, self.ah, self.acct, self.no_ga4 = {}, {}, {}, {}
        self.kal = {}                     # aid -> (kal USD, usual USD/day)
        self.rows_all = []
        self.by_app = defaultdict(list)   # every row of an app (hidden ones too)
        self.shown = {}                   # aid -> the app's shown rows
        self.extra = defaultdict(list)    # aid -> review-only rows (range / ads / mediation)
        self.ads = {}
        self.deda = {}
        self.ded_dates, self.ded_win, self.ded_from, self.ded_to = [], set(), None, None
        self.med = {}
        self.bunit, self.blast, self.appr = {}, None, {}
        self.app_total_rel = {}
        # the store's history (earlier snapshots): the go-live day and, per app key, the first review day of the
        # current unbroken run of snapshots that showed each red/amber row (row_id) — "Naya ya purana" and the
        # "Kab se" of rows that have no real start date (setup / account health). Empty on the first day.
        self.go_live = day
        self.seen = {}                    # app key -> row_id -> date
        self.seen_out = {}                # app key -> [row_id] red/amber on THIS day's cards (the store saves it)
        self.feat_fail = defaultdict(set)  # aid -> features whose data could not be read
        self.app_fail = set()              # aids whose card could not be built

    # the lazy per-app files (None when missing / damaged)
    def afile(self, aid):
        a = self.aapp.get(aid)
        return self.site.gz(a.get("file")) if a and a.get("file") else None

    def vfile(self, aid):
        a = self.vapp.get(aid)
        return self.site.gz(a.get("file")) if a and a.get("file") else None

    def cfile(self, aid):
        u = self.uapp.get(aid)
        return self.site.gz(f"uninstall_c_{u['key']}.json.gz") if u and u.get("key") else None

    def fail(self, aid, feat):
        self.feat_fail[aid].add(feat)


def _by_id(rows):
    return {a["app_id"]: a for a in rows or [] if isinstance(a, dict) and a.get("app_id")}


def make_ctx(site, day):
    """Read the dashboard + site files once into a Ctx for review day `day` (a date). Raises ReviewBuildError when
    the dashboard is unreadable or no app is selected."""
    db = site.dashboard()
    if not isinstance(db, dict) or not isinstance(db.get("apps_catalog"), list):
        raise ReviewBuildError("dashboard")
    ctx = Ctx(site, day)
    ctx.db = db
    un = site.gz("uninstall.json.gz")
    ctx.un = un if isinstance(un, dict) else {}
    try:
        ctx.today = D(db.get("today_date")) or day
    except ValueError:
        ctx.today = day
    ctx.admob_till = D(db.get("latest_complete")) if db.get("latest_complete") else ctx.today - timedelta(1)
    uni, act, val = db.get("uninstall") or {}, db.get("active") or {}, db.get("value") or {}
    ctx.ga4_till = D(uni.get("data_till_max")) if uni.get("data_till_max") else None
    ctx.settled = D(act.get("settled_till_max")) if act.get("settled_till_max") else None
    ctx.ga4_lag = (ctx.today - ctx.ga4_till).days if ctx.ga4_till else None
    try:
        ctx.fx = float(db.get("usd_inr") or 0) or None
    except (TypeError, ValueError):
        ctx.fx = None
    ctx.uapp, ctx.ud, ctx.aapp, ctx.vapp = (_by_id(ctx.un.get("apps")), _by_id(uni.get("apps")),
                                            _by_id(act.get("apps")), _by_id(val.get("apps")))
    _apps(ctx, site)
    if not ctx.apps:
        raise ReviewBuildError("no apps")
    _money(ctx)
    _first_runs(ctx)
    return ctx


def _apps(ctx, site):
    db = ctx.db
    acc_names = site.js("account_names.json", {})
    app_names = site.js("app_names.json", {})
    acc_names = acc_names if isinstance(acc_names, dict) else {}
    app_names = app_names if isinstance(app_names, dict) else {}
    cat = [c for c in db["apps_catalog"] if isinstance(c, dict) and c.get("selected") and c.get("app_id")]
    ctx.name2id = {c["app_name"]: c["app_id"] for c in db["apps_catalog"] if isinstance(c, dict) and "app_name" in c}
    store_ids = db.get("app_store_ids") if isinstance(db.get("app_store_ids"), dict) else {}
    for c in cat:
        aid, acc = c["app_id"], str(c.get("account_id") or "")
        dname = str(c.get("app_name") or aid)
        try:
            raw = app_names.get(aid) or _SUFFIX.sub("", dname)
            store = str(raw).replace("–", "-").replace("—", "-")
            acct = acc_names.get(acc) or _acct_short(acc)
            launch = (ctx.aapp.get(aid) or {}).get("launch_day") or (ctx.uapp.get(aid) or {}).get("launch")
            if isinstance(launch, dict):
                launch = launch.get("day") or launch.get("date")
            pkg = (ctx.uapp.get(aid) or {}).get("package") or store_ids.get(aid)
        except Exception:
            ctx.app_fail.add(aid)
            store, acct, launch, pkg = _SUFFIX.sub("", dname), _acct_short(acc), None, None
        ctx.apps[aid] = {"id": aid, "key": file_key(aid), "dname": dname, "store": store, "acct": str(acct),
                         "acc": acc, "launch": launch, "pkg": pkg if isinstance(pkg, str) else None,
                         "k7": 0.0, "kp7": 0.0, "spend": 0.0, "paisa": 0.0, "size": "chhoti"}
    dup = Counter((a["store"], a["acct"]) for a in ctx.apps.values())
    for a in ctx.apps.values():
        a["tag"] = ""
        if dup[(a["store"], a["acct"])] > 1 and a["launch"]:
            a["tag"] = f" ({str(a['launch'])[:4]} wala)"
        a["name"] = f"{a['store']}{a['tag']} · {a['acct']}"


def _money(ctx):
    """AdMob kamai per app per day (ONLY placements[].daily, country All), the 7-day windows, size, and the
    per-app ad totals (kamai, impressions, requests, matched, clicks)."""
    for p in ctx.db.get("placements") or []:
        if not isinstance(p, dict) or p.get("country", "All") != "All":
            continue
        ctx.unit[p.get("id")] = p
        aid = ctx.name2id.get(p.get("app"))
        if not aid:
            continue
        for r in p.get("daily") or []:
            try:
                ctx.rev[aid][r[0]] += r[1] / 1e6
            except (TypeError, IndexError, KeyError):
                ctx.fail(aid, "kamai")
    for p in ctx.unit.values():
        aid = ctx.name2id.get(p.get("app"))
        if aid not in ctx.apps:
            continue
        for r in p.get("daily") or []:
            try:
                x = ctx.ad[aid][r[0]]
                x[0] += r[1] / 1e6
                x[1] += r[2]
                x[2] += r[3]
                x[3] += r[4]
                x[4] += r[5]
            except (TypeError, IndexError, KeyError):
                ctx.fail(aid, "kamai")
    y = ctx.admob_till
    ctx.w7 = days_back(y, 7)
    ctx.p7 = days_back(y - timedelta(7), 7)
    ctx.u7 = days_back(y - timedelta(1), 7)          # 'usual' = the 7 days before kal
    ctx.d14 = days_back(y, 14)
    ys = y.isoformat()
    for aid, a in ctx.apps.items():
        try:
            a["k7"] = sum(ctx.rev[aid].get(x, 0) for x in ctx.w7) / 7
            a["kp7"] = sum(ctx.rev[aid].get(x, 0) for x in ctx.p7) / 7
            v = ctx.vapp.get(aid) or {}
            sp = ((v.get("cpi") or {}).get("spend4_src") or 0) / 28
            a["spend"] = (sp / ctx.fx) if ctx.fx else 0.0
            a["paisa"] = a["k7"] + a["spend"]
            a["size"] = "badi" if a["paisa"] >= BADI else ("chhoti" if a["paisa"] < CHHOTI else "madhyam")
            ctx.kal[aid] = (ctx.rev[aid].get(ys, 0.0), sum(ctx.rev[aid].get(x, 0.0) for x in ctx.u7) / 7)
            ctx.app_total_rel[aid] = (a["k7"] / a["kp7"] - 1) if a["kp7"] else 0
        except Exception:
            ctx.app_fail.add(aid)
            ctx.kal.setdefault(aid, (0.0, 0.0))
            ctx.app_total_rel.setdefault(aid, 0)
    ctx.small = {aid for aid, a in ctx.apps.items() if a["size"] == "chhoti"}
    ctx.ro = ((ctx.db.get("roas") or {}).get("by_app") or {}) if isinstance(ctx.db.get("roas"), dict) else {}
    ctx.ah = {ctx.name2id.get(x.get("app")): x for x in ((ctx.db.get("account_health") or {}).get("per_app") or [])
              if isinstance(x, dict)}
    ctx.acct = {a["account_id"]: a for a in ctx.db.get("accounts") or [] if isinstance(a, dict) and a.get("account_id")}
    ctx.no_ga4 = _by_id((ctx.db.get("active") or {}).get("no_ga4"))


def _first_runs(ctx):
    """First-run dates per source (rows opened on that day were created by the feature's first run = 'seeded')."""
    uni = ctx.db.get("uninstall") or {}
    closed = [c for u in ctx.un.get("apps") or [] if isinstance(u, dict) for c in (u.get("alerts_closed") or [])]
    for a in list(uni.get("alerts") or []) + closed:
        if not isinstance(a, dict):
            continue
        k = "impact" if a.get("family") == "impact" else "uninstall"
        if a.get("opened"):
            ctx.first_run[k] = min(ctx.first_run.get(k, "9999"), a["opened"])
    for a in (ctx.db.get("active") or {}).get("alerts") or []:
        if isinstance(a, dict) and a.get("opened"):
            ctx.first_run["active"] = min(ctx.first_run.get("active", "9999"), a["opened"])
