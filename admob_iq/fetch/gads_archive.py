"""Google Ads ARCHIVE (GADS_ARCHIVE; private data/ only — nothing here is shown, and no existing number reads it).

Google keeps a campaign's CURRENT settings only, and its change history (change_event) for ~30 days: every day not
archived is lost for good. So once a day per account this keeps what the account looks like and what changed in it.

The build step (build_static._gads_archive_step, right after the geo step, its own try): archive_step(...) runs
  a. the per-campaign × day rows the spend fetch already downloaded → data/ads_campaign_day/ (fetch.gads_campaign_day;
     0 calls)
  b. this archive → data/ads_archive/ (below)
  c. spend by hour → data/ads_hourly/ (fetch.gads_hourly)
  d. the per-campaign backfill → data/ads_campaign_day/ (fetch.gads_campaign_day)
in that order, each in its own try, all sharing ONE call budget (ARCH_MAX_CALLS / ARCH_MAX_SEC; a quota error — HTTP 429 /
RESOURCE_EXHAUSTED / quotaError — stops every further request at once: the developer token's quota is the hourly spend
fetch's too). Country × day lives in the geo step (fetch.gads_geo_day). Public log: ONE counts-only line per part (no
ids, names, dates, money, countries or ratios).

What is asked (READ-ONLY, per account under the MCC whose roster status is ENABLED — or not said — once a day):
  cust    customer: name, currency, time zone, status, auto-tagging, test account, pay-per-conversion failure reasons
  camp    campaign (app campaigns, not REMOVED) + its campaign_budget: status, serving / primary status + reasons, channel,
          bidding strategy type + portfolio, target CPA / ROAS (incl. maximize-conversions / -value targets), app id /
          store / bidding goal (the optimisation goal), selective-optimisation conversion actions, optimisation goal
          types, geo target type setting, start / end date, budget id / amount / delivery / period / shared / status
  loc     campaign_criterion LOCATION + LANGUAGE (not removed) → per campaign {pos, neg, lang} (sorted constant ids)
  ads     ad_group_ad policy summary → per campaign counts by approval / review / primary status (disapprovals)
  asset   ad_group_ad_asset_view (enabled) → per campaign counts by approval / review / performance label / field type
  conv    conversion_action (ENABLED): category, type, counting, windows, primary / included, value settings, app id
  bill    billing_setup: status, start / end, payments account
  abud    account_budget: status, approved limit / end, amount served, adjustments, proposed limit
  recsub  recommendation_subscription: the auto-apply recommendation types and their status
  ev      change_event since the last day asked (≤ EV_BACK days: Google's 30-day limit, a day kept spare), ORDER BY time,
          LIMIT 10000 (a full answer is split in halves down to one day; a day still full is marked "trunc"). Each event:
          time, resource type / name, operation, client type (GOOGLE_ADS_RECOMMENDATIONS_SUBSCRIPTION = an auto-applied
          recommendation, GOOGLE_ADS_AUTOMATED_RULE, the web UI, the API …), campaign / ad group, the changed fields and
          their old → new values (a value over CAP_CHARS is kept as its length + hash). The user's e-mail is NOT asked.
  loc / ads / asset are not asked when camp answered no campaign. Optional fields are field-tolerant (gads_store.robust).
  A kind refused 3 days in a row (e.g. no billing permission) is asked again only weekly; an account answering 403
  CUSTOMER_NOT_ENABLED is skipped SKIP_DAYS. A kind that failed is asked again at the next build (≤ TRIES a day).

File data/ads_archive/<YYYY-MM>.json.gz (deterministic, only on change):
  {"v": 1, "month": "YYYY-MM", "acct": {account: {
      "ver":  {entity: [[day, value | null], ...]},   entity = "cust" | "<kind>/<id>"; a new version only when the value
              changed (null = gone while its kind answered); the month's first archived day repeats the carried-in state
              (so a month file is complete on its own)
      "days": {day: {"ok": [kinds answered], "err": {kind: error code}, "drop": {kind: [optional fields not asked]},
                     "ev": [events of that account-local day, deduped, sorted], "trunc": true}}}}}
  The state on day D = for each entity the last version with day ≤ D (state_on). Snapshot days are the build's report
  days; event days are the account's own (change_date_time). A field not asked on a day (refused by Google: the day's
  "drop") keeps its last answered value in that day's version — a slimmer query is never a change; an event day whose
  events were saved without some optional change_event fields lists them in its "drop" ("ev").
data/ads_archive/state.json.gz: cursors {"acct": {account: {"day", "ok", "tries", "ev", "evcov"}}, "streak", "skip",
  "drop", "roster": {"day", "n", "live"} (the day's MCC roster: a later build of the day with nothing due asks
  nothing)} (no time stamps).
"""

import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from .gads_geo import _Run, _Stop, _is_quota
from .gads_store import Months, Session, code_of, cov_add, d, field, load_state, month_of, not_enabled, robust, \
    save_state, tail_id, usable

ARCH_V = 1
ARCH_DIR = "ads_archive"
ARCH_MAX_CALLS = 400                # Google Ads requests per build for the archive step (all its parts)
ARCH_MAX_SEC = 150                  # no new request after this many seconds of the step
ARCH_WORKERS = 4                    # accounts in parallel — one request at a time per account
TRIES = 3                           # builds a day that ask an account's failed kinds again
STREAK_DAYS = 3                     # a kind refused this many days in a row …
STREAK_WAIT = 7                     # … is asked again only after this many days
SKIP_DAYS = 7                       # an account answering 403 CUSTOMER_NOT_ENABLED
EV_BACK = 28                        # change_event: Google answers ≤ 30 days back (one day spare for time zones)
EV_OVERLAP = 2                      # days asked again before the last day asked (late events of a day)
EV_LIMIT = 10000                    # change_event's LIMIT (Google's maximum)
CAP_CHARS = 600                     # an old / new value longer than this (as JSON) is kept as {"_len", "_sha1"}
CAP_FIELDS = 40                     # changed fields kept per event (the rest counted in "_more")

CAMP_WHERE = "campaign.app_campaign_setting.app_id != '' AND campaign.status != 'REMOVED'"
NOT_REMOVED = "campaign.status != 'REMOVED'"

# kind, FROM, core fields, optional fields, WHERE, needs a campaign. Every filtered field is selected (Google refuses a
# WHERE on some fields the SELECT lacks — the geo probe's rule).
KINDS = (
    ("cust", "customer", ("customer.id",),
     ("customer.descriptive_name", "customer.currency_code", "customer.time_zone", "customer.status",
      "customer.auto_tagging_enabled", "customer.test_account",
      "customer.pay_per_conversion_eligibility_failure_reasons"), "", False),
    ("camp", "campaign", ("campaign.id", "campaign.status", "campaign.app_campaign_setting.app_id"),
     ("campaign.name", "campaign.serving_status", "campaign.primary_status", "campaign.primary_status_reasons",
      "campaign.advertising_channel_type", "campaign.advertising_channel_sub_type", "campaign.bidding_strategy_type",
      "campaign.bidding_strategy", "campaign.target_cpa.target_cpa_micros", "campaign.target_roas.target_roas",
      "campaign.maximize_conversions.target_cpa_micros", "campaign.maximize_conversion_value.target_roas",
      "campaign.app_campaign_setting.app_store", "campaign.app_campaign_setting.bidding_strategy_goal_type",
      "campaign.selective_optimization.conversion_actions", "campaign.optimization_goal_setting.optimization_goal_types",
      "campaign.geo_target_type_setting.positive_geo_target_type",
      "campaign.geo_target_type_setting.negative_geo_target_type", "campaign.start_date", "campaign.end_date",
      "campaign.start_date_time", "campaign.end_date_time", "campaign.campaign_budget", "campaign_budget.id",
      "campaign_budget.amount_micros", "campaign_budget.delivery_method", "campaign_budget.period",
      "campaign_budget.explicitly_shared", "campaign_budget.status", "campaign_budget.total_amount_micros"),
     CAMP_WHERE, False),
    ("loc", "campaign_criterion",
     ("campaign.id", "campaign.status", "campaign_criterion.criterion_id", "campaign_criterion.type",
      "campaign_criterion.negative"),
     ("campaign_criterion.status", "campaign_criterion.location.geo_target_constant",
      "campaign_criterion.language.language_constant"),
     "campaign_criterion.type IN ('LOCATION', 'LANGUAGE') AND " + NOT_REMOVED, True),
    ("ads", "ad_group_ad", ("campaign.id", "campaign.status", "ad_group_ad.ad.id", "ad_group_ad.status"),
     ("ad_group_ad.policy_summary.approval_status", "ad_group_ad.policy_summary.review_status",
      "ad_group_ad.primary_status"),
     "ad_group_ad.status != 'REMOVED' AND " + NOT_REMOVED, True),
    ("asset", "ad_group_ad_asset_view", ("campaign.id", "campaign.status", "ad_group_ad_asset_view.enabled"),
     ("ad_group_ad_asset_view.field_type", "ad_group_ad_asset_view.policy_summary.approval_status",
      "ad_group_ad_asset_view.policy_summary.review_status", "ad_group_ad_asset_view.performance_label"),
     "ad_group_ad_asset_view.enabled = TRUE AND " + NOT_REMOVED, True),
    ("conv", "conversion_action", ("conversion_action.id", "conversion_action.status"),
     ("conversion_action.name", "conversion_action.category", "conversion_action.type",
      "conversion_action.counting_type", "conversion_action.click_through_lookback_window_days",
      "conversion_action.view_through_lookback_window_days", "conversion_action.include_in_conversions_metric",
      "conversion_action.primary_for_goal", "conversion_action.value_settings.default_value",
      "conversion_action.value_settings.always_use_default_value", "conversion_action.app_id",
      "conversion_action.firebase_settings.event_name"),
     "conversion_action.status = 'ENABLED'", False),
    ("bill", "billing_setup", ("billing_setup.id", "billing_setup.status"),
     ("billing_setup.start_date_time", "billing_setup.end_date_time", "billing_setup.payments_account"), "", False),
    ("abud", "account_budget", ("account_budget.id", "account_budget.status"),
     ("account_budget.approved_spending_limit_micros", "account_budget.approved_spending_limit_type",
      "account_budget.approved_end_date_time", "account_budget.approved_end_time_type",
      "account_budget.amount_served_micros", "account_budget.total_adjustments_micros",
      "account_budget.proposed_spending_limit_micros"), "", False),
    ("recsub", "recommendation_subscription", ("recommendation_subscription.type", "recommendation_subscription.status"),
     ("recommendation_subscription.create_date_time", "recommendation_subscription.modify_date_time"), "", False),
)
KIND_NAMES = tuple(k[0] for k in KINDS)
EV_CORE = ("change_event.change_date_time", "change_event.change_resource_type", "change_event.change_resource_name",
           "change_event.client_type", "change_event.resource_change_operation", "change_event.changed_fields",
           "change_event.campaign")
EV_OPT = ("change_event.old_resource", "change_event.new_resource", "change_event.ad_group")
DEFAULTS = {"acct": {}, "streak": {}, "skip": {}, "drop": {}, "roster": {}}
# the entity key each optional field fills: the field without its own resource's prefix (OWN), or a count (AGG);
# loc's optional fields fill none of their own (the ids fall back to the criterion id, status only filters)
OWN = {"cust": "customer", "camp": "campaign", "conv": "conversion_action", "bill": "billing_setup",
       "abud": "account_budget", "recsub": "recommendation_subscription"}
AGG = {"ads": {"ad_group_ad.policy_summary.approval_status": "approval",
               "ad_group_ad.policy_summary.review_status": "review", "ad_group_ad.primary_status": "primary"},
       "asset": {"ad_group_ad_asset_view.field_type": "type",
                 "ad_group_ad_asset_view.policy_summary.approval_status": "approval",
                 "ad_group_ad_asset_view.policy_summary.review_status": "review",
                 "ad_group_ad_asset_view.performance_label": "perf"}}


# ── rows → entities ───────────────────────────────────────────────────────────────────────────────

def _entity(row, fields, own):
    """The selected fields of one row → {name: value} (a field of the row's own resource loses that prefix; its id — the
    entity key — and absent / null fields are left out: the REST API leaves out defaults)."""
    out = {}
    for f in fields:
        v = field(row, f)
        if v is None or f == own + ".id":                      # the id is the entity's key already
            continue
        out[f[len(own) + 1:] if f.startswith(own + ".") else f] = v
    return out


def _count(dst, key, v):
    if v is not None:
        b = dst.setdefault(key, {})
        b[str(v)] = b.get(str(v), 0) + 1


def reduce_rows(kind, rows, used):
    """One kind's answer → {entity key: value} (the archive's entities)."""
    spec = next(k for k in KINDS if k[0] == kind)
    fields = list(spec[2]) + list(used)
    out = {}
    if kind == "cust":
        for row in rows[:1]:
            out["cust"] = _entity(row, fields, OWN[kind])
    elif kind in ("camp", "conv", "bill", "abud"):
        own = OWN[kind]
        for row in rows:
            i = field(row, own + ".id")
            if i not in (None, ""):
                out["%s/%s" % (kind, i)] = _entity(row, fields, own)
    elif kind == "recsub":
        for row in rows:
            t = field(row, "recommendation_subscription.type")
            if t:
                out["recsub/%s" % t] = _entity(row, fields, OWN[kind])
    elif kind == "loc":
        for row in rows:
            c = field(row, "campaign.id")
            if c in (None, "") or field(row, "campaign_criterion.status") == "REMOVED":
                continue
            e = out.setdefault("loc/%s" % c, {"pos": [], "neg": [], "lang": []})
            if field(row, "campaign_criterion.type") == "LANGUAGE":
                e["lang"].append(tail_id(field(row, "campaign_criterion.language.language_constant"))
                                 or str(field(row, "campaign_criterion.criterion_id")))
            else:
                g = tail_id(field(row, "campaign_criterion.location.geo_target_constant")) \
                    or str(field(row, "campaign_criterion.criterion_id"))
                e["neg" if field(row, "campaign_criterion.negative") else "pos"].append(g)
        for e in out.values():
            for k in ("pos", "neg", "lang"):
                e[k] = sorted(set(e[k]), key=lambda x: (len(x), x))
    elif kind in ("ads", "asset"):
        for row in rows:
            c = field(row, "campaign.id")
            if c in (None, ""):
                continue
            e = out.setdefault("%s/%s" % (kind, c), {"n": 0})
            e["n"] += 1
            if kind == "ads":
                _count(e, "status", field(row, "ad_group_ad.status"))
            for f, key in AGG[kind].items():
                _count(e, key, field(row, f))
    return out


def _key_of(kind, f):
    """The entity key optional field `f` of `kind` fills (None: none of its own)."""
    if kind in AGG:
        return AGG[kind].get(f)
    own = OWN.get(kind)
    if not own:
        return None
    return f[len(own) + 1:] if f.startswith(own + ".") else f


def _cap(v):
    s = json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(s) <= CAP_CHARS:
        return v
    return {"_len": len(s), "_sha1": hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]}


def _walk(obj, path):
    """A FieldMask path (REST: camelCase, dotted) inside a resource dict → value or None."""
    cur = obj
    for p in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _inner(res):
    """ChangeEventResource {"campaign": {...}} → the one resource dict inside (or {})."""
    if not isinstance(res, dict):
        return {}
    for k in sorted(res):
        if isinstance(res[k], dict) and res[k]:
            return res[k]
    return {}


def event_of(row):
    """A change_event row → the archived event (compact; only the changed fields' old → new values)."""
    ce = row.get("changeEvent") or {}
    f = ce.get("changedFields")
    fields = [x.strip() for x in (f.split(",") if isinstance(f, str) else (f or {}).get("paths") or []) if x.strip()]
    ev = {"t": str(ce.get("changeDateTime") or ""), "rt": ce.get("changeResourceType"),
          "rn": ce.get("changeResourceName"), "op": ce.get("resourceChangeOperation"), "ct": ce.get("clientType"),
          "f": fields[:CAP_FIELDS], "c": tail_id(ce.get("campaign")), "ag": tail_id(ce.get("adGroup"))}
    if len(fields) > CAP_FIELDS:
        ev["_more"] = len(fields) - CAP_FIELDS
    for side, key in (("old", "oldResource"), ("new", "newResource")):
        r = _inner(ce.get(key))
        vals = {p: _cap(_walk(r, p)) for p in fields[:CAP_FIELDS] if _walk(r, p) is not None}
        if vals:
            ev[side] = vals
    return {k: v for k, v in ev.items() if v not in (None, "", [])}


def ev_key(ev):
    return (ev.get("t") or "", ev.get("rn") or "", ev.get("op") or "", ev.get("ct") or "", ",".join(ev.get("f") or []))


# ── the archive files ─────────────────────────────────────────────────────────────────────────────

def _empty(m):
    return {"v": ARCH_V, "month": m, "acct": {}}


def months(data_dir):
    return Months(os.path.join(data_dir, ARCH_DIR), _empty, lambda o: o.get("v") == ARCH_V and
                  isinstance(o.get("acct"), dict))


def state_at(ver, day):
    """{entity: value} on `day` from a version map (gone / not yet = left out)."""
    out = {}
    for k, vs in ver.items():
        cur = None
        for dd, x in vs:
            if dd > day:
                break
            cur = (x,)
        if cur and cur[0] is not None:
            out[k] = cur[0]
    return out


def _carried(mf, acct, day):
    """The account's archived state on `day`: the newest month (≤ day's) holding a version of the account on or before
    `day` (a month's first archived day can be later than `day` — then the month before holds the state)."""
    for m in sorted((x for x in mf.months() if x <= month_of(day)), reverse=True):
        ver = (mf.peek(m)["acct"].get(acct) or {}).get("ver") or {}
        if min((vs[0][0] for vs in ver.values() if vs), default="9999") <= day:
            return state_at(ver, day)
    return {}


def _put(ver, key, day, v):
    """A value seen on `day` → a new version only when it differs (same day: replaced) → True when a version changed."""
    vs = ver.setdefault(key, [])
    if vs and vs[-1][0] == day:
        if vs[-1][1] == v:
            return False
        if len(vs) >= 2 and vs[-2][1] == v:
            vs.pop()
        else:
            vs[-1][1] = v
        return True
    if (vs[-1][1] if vs else None) == v:
        if not vs:
            del ver[key]
        return False
    vs.append([day, v])
    return True


def state_on(data_dir, acct, day):
    """The archived settings of one account on `day` → {entity: value} (read API)."""
    return _carried(months(data_dir), str(acct), str(day))


def events(data_dir, first=None, last=None):
    """Every archived event in [first, last] → [(account, event)] sorted by time (read API)."""
    mf = months(data_dir)
    out = []
    for m in mf.months():
        for a, rec in sorted(mf.peek(m)["acct"].items()):
            for dd, r in sorted((rec.get("days") or {}).items()):
                if (first and dd < str(first)) or (last and dd > str(last)):
                    continue
                out += [(a, e) for e in r.get("ev") or []]
    return sorted(out, key=lambda x: (ev_key(x[1]), x[0]))


# ── asking one account ────────────────────────────────────────────────────────────────────────────

def _events(sess, acct, lo, hi, out, depth=0):
    """change_event rows of [lo, hi] (account-local days) → out["ev"] (+ out["trunc"] days); a full answer is split."""
    where = ("change_event.change_date_time >= '%s 00:00:00' AND change_event.change_date_time <= '%s 23:59:59'"
             % (lo.isoformat(), hi.isoformat()))
    rows, used = robust(sess, acct, "ev", "change_event", EV_CORE, EV_OPT, where=where,
                        tail=" ORDER BY change_event.change_date_time LIMIT %d" % EV_LIMIT)
    had = out["used"].get("ev")
    out["used"]["ev"] = [f for f in used if had is None or f in had]       # a split: the fields every part had
    if len(rows) >= EV_LIMIT and depth < 8:
        if lo < hi:
            mid = lo + timedelta(days=(hi - lo).days // 2)
            _events(sess, acct, lo, mid, out, depth + 1)
            _events(sess, acct, mid + timedelta(days=1), hi, out, depth + 1)
            return
        out["trunc"].append(lo.isoformat())
    out["ev"] += [event_of(r) for r in rows]


def ask_account(sess, acct, kinds, ev_window):
    """One account, one request at a time → {"res": {kind: entities}, "used", "err": {kind: code}, "stop", "gone",
    "ev": [events] | None, "ev_lo", "ev_hi", "trunc"}."""
    out = {"res": {}, "used": {}, "err": {}, "stop": False, "gone": False, "ev": None, "trunc": []}
    for kind, frm, core, opt, where, needs in KINDS:
        if kind not in kinds:
            continue
        if needs and out["res"].get("camp") == {}:
            out["res"][kind], out["used"][kind] = {}, list(opt)  # no campaign: nothing to ask (nothing dropped)
            continue
        try:
            rows, used = robust(sess, acct, kind, frm, core, opt, where=where)
        except _Stop:
            out["stop"] = True
            return out
        except Exception as e:
            if not_enabled(e):
                out["gone"] = True
                return out
            if _is_quota(e):                                    # the quota: no refusal of this kind, a stop
                out["stop"] = True
                return out
            out["err"][kind] = code_of(e)
            continue
        out["res"][kind], out["used"][kind] = reduce_rows(kind, rows, used), used
    if ev_window:
        lo, hi = ev_window
        got = {"ev": [], "trunc": [], "used": out["used"]}
        try:
            _events(sess, acct, lo, hi, got)
        except _Stop:
            out["stop"] = True
            return out
        except Exception as e:
            if not_enabled(e):
                out["gone"] = True
            elif _is_quota(e):
                out["stop"] = True
            else:
                out["err"]["ev"] = code_of(e)
            return out
        out["ev"], out["trunc"], out["ev_lo"], out["ev_hi"] = got["ev"], got["trunc"], lo.isoformat(), hi.isoformat()
    return out


# ── the archive part ──────────────────────────────────────────────────────────────────────────────

def _plan(state, acct, today):
    """→ (kinds to ask, change_event window | None, kinds waiting out a refusal streak)."""
    ts = today.isoformat()
    rec = state["acct"].get(acct) or {}
    same = rec.get("day") == ts
    if same and int(rec.get("tries") or 0) >= TRIES:
        return [], None, []
    done = set(rec.get("ok") or []) if same else set()
    wait = []
    kinds = []
    for k in KIND_NAMES:
        if k in done:
            continue
        sk = (state["streak"].get(acct) or {}).get(k)
        if sk and int(sk[0]) >= STREAK_DAYS and (today - d(sk[1])).days < STREAK_WAIT:
            wait.append(k)
            continue
        kinds.append(k)
    ev = None
    if not (same and rec.get("ev") == ts):
        lo = today - timedelta(days=EV_BACK)
        if rec.get("ev"):
            lo = max(lo, d(rec["ev"]) - timedelta(days=EV_OVERLAP))
        ev = (lo, today + timedelta(days=1))                 # the account's day may already be tomorrow here
    return kinds, ev, wait


def commit(mf, state, acct, today, got, st):
    """One account's answers → the month files + the state (main thread; deterministic)."""
    ts = today.isoformat()
    rec = state["acct"].setdefault(acct, {})
    if rec.get("day") != ts:
        rec.update(day=ts, ok=[], tries=0)
    if got["stop"] and not got["res"] and got["ev"] is None and not got["err"]:
        return                                                  # nothing asked (the budget): not a try
    rec["tries"] = int(rec.get("tries") or 0) + (0 if got["stop"] else 1)
    answered = sorted(got["res"])
    if answered:
        carried = _carried(mf, acct, ts)
        f = mf.get(month_of(ts))
        arec = f["acct"].setdefault(acct, {"ver": {}, "days": {}})
        if not arec["ver"]:
            for k, v in sorted(carried.items()):                # the month's base: the carried-in state
                arec["ver"][k] = [[ts, v]]
        new = {}
        for k in answered:
            new.update(got["res"][k])
        for kind in answered:
            keys = {k for k in carried if k.split("/")[0] == kind} | {k for k in new if k.split("/")[0] == kind}
            spec = next(x for x in KINDS if x[0] == kind)
            unasked = {_key_of(kind, f) for f in spec[3] if f not in (got["used"].get(kind) or [])} - {None}
            for k in sorted(keys):
                v = new.get(k)
                if unasked and isinstance(v, dict) and isinstance(carried.get(k), dict):
                    v = {**v, **{x: carried[k][x] for x in sorted(unasked) if x in carried[k]}}   # last answered
                if _put(arec["ver"], k, ts, v):
                    st["changes"] += 1
        day = arec["days"].setdefault(ts, {})
        day["ok"] = sorted(set(day.get("ok") or []) | set(answered))
        drop = {k: sorted(set(next(x[3] for x in KINDS if x[0] == k)) - set(got["used"].get(k) or []))
                for k in answered}
        drop = {k: v for k, v in drop.items() if v}
        if drop:
            day["drop"] = dict(sorted({**(day.get("drop") or {}), **drop}.items()))
        err = {k: v for k, v in (day.get("err") or {}).items() if k not in day["ok"]}
        err.update({k: v for k, v in got["err"].items() if k != "ev"})
        if err:
            day["err"] = dict(sorted(err.items()))
        else:
            day.pop("err", None)
        rec["ok"] = sorted(set(rec.get("ok") or []) | set(answered))
        st["snapshots"].add(acct)
    if got["err"]:
        st["refused"] += len(got["err"])
        sk = state["streak"].setdefault(acct, {})
        for k, code in sorted(got["err"].items()):
            prev = sk.get(k)
            n = int(prev[0]) if prev else 0
            sk[k] = [n + (0 if prev and prev[1] == ts else 1), ts, code]
    for k in answered + (["ev"] if got["ev"] is not None else []):
        (state["streak"].get(acct) or {}).pop(k, None)
    if not state["streak"].get(acct):
        state["streak"].pop(acct, None)
    if got["ev"] is not None:
        evdrop = sorted(set(EV_OPT) - set(got["used"].get("ev") or []))
        touched = {}
        for ev in got["ev"]:
            dd = ev["t"][:10]
            if len(dd) != 10:
                continue
            touched.setdefault(dd, []).append(ev)
        for dd in sorted(set(touched) | set(got["trunc"])):
            arec = mf.get(month_of(dd))["acct"].setdefault(acct, {"ver": {}, "days": {}})
            day = arec["days"].setdefault(dd, {})
            have = {ev_key(e): e for e in day.get("ev") or []}
            added = 0
            for e in touched.get(dd, []):
                if ev_key(e) not in have:
                    st["events"] += 1
                    added += 1
                    have[ev_key(e)] = e
                elif not evdrop:                                # a slimmer answer never replaces a kept event
                    have[ev_key(e)] = e
            if have:
                day["ev"] = [have[k] for k in sorted(have)]
            if added and evdrop:                                # events saved without those fields
                dr = day.get("drop") or {}
                dr["ev"] = sorted(set(dr.get("ev") or []) | set(evdrop))
                day["drop"] = dict(sorted(dr.items()))
            if dd in got["trunc"]:
                day["trunc"] = True
        rec["ev"] = ts
        rec["evcov"] = cov_add(rec.get("evcov"), got["ev_lo"], min(got["ev_hi"], ts))


def _complete(state, live, plans, ts):
    return all((state["acct"].get(a) or {}).get("day") == ts and (state["acct"][a].get("ev") == ts)
               and set(KIND_NAMES) <= set(state["acct"][a].get("ok") or []) | set(plans[a][2])
               for a in live if a not in state["skip"])


def archive_part(sess, data_dir, today, st):
    """Ask what is due today, commit, save → state word ("done" | "partial")."""
    dirpath = os.path.join(data_dir, ARCH_DIR)
    state = load_state(dirpath, ARCH_V, DEFAULTS)
    sess.drop = dict(state["drop"])
    ts = today.isoformat()
    state["skip"] = {k: v for k, v in state["skip"].items() if isinstance(v, str) and v > ts}
    ros = state["roster"]
    if ros.get("day") == ts:                                    # a later build of the day: anything due?
        live = [a for a in ros.get("live") or [] if a not in state["skip"]]
        plans = {a: _plan(state, a, today) for a in live}
        if not any(p[0] or p[1] for p in plans.values()):       # no: no token, no roster request
            st["skipped"] = int(ros.get("n") or 0) - len(live)
            st["accounts"] = len(live)
            st["waiting"] = sum(len(p[2]) for p in plans.values())
            return "done" if _complete(state, live, plans, ts) else "partial"
    if not sess.ready():
        return "partial"
    state["roster"] = {"day": ts, "n": len(sess.accounts), "live": sess.live()}
    live = [a for a in sess.live() if a not in state["skip"]]
    st["skipped"] = len(sess.accounts) - len(live)
    plans = {a: _plan(state, a, today) for a in live}
    due = [a for a in live if plans[a][0] or plans[a][1]]
    st["accounts"] = len(live)
    st["waiting"] = sum(len(p[2]) for p in plans.values())
    res = {}
    if due and not sess.run.stop:
        with ThreadPoolExecutor(max_workers=min(ARCH_WORKERS, len(due))) as ex:
            res = dict(zip(due, ex.map(lambda a: ask_account(sess, a, plans[a][0], plans[a][1]), due)))
    mf = months(data_dir)
    until = (today + timedelta(days=SKIP_DAYS)).isoformat()
    for a in sorted(res):
        if res[a]["gone"]:
            state["skip"][a] = until
            st["skipped"] += 1
            continue
        commit(mf, state, a, today, res[a], st)
    mf.save()
    if sess.new_drop:
        state["drop"] = dict(sorted({**state["drop"], **sess.new_drop}.items()))
    if res or sess.new_drop or os.path.exists(os.path.join(dirpath, "state.json.gz")):
        save_state(dirpath, state)
    return "done" if _complete(state, live, plans, ts) else "partial"


# ── the step ──────────────────────────────────────────────────────────────────────────────────────

def archive_line(st, state, calls, errors):
    return ("gads archive: accounts %d (skipped %d), snapshots %d, changes %d, events %d, refused %d, waiting %d, "
            "calls %d, errors %d (%s)" % (st["accounts"], st["skipped"], len(st["snapshots"]), st["changes"],
                                          st["events"], st["refused"], st["waiting"], calls, errors, state))


def _arch_stats():
    return {"accounts": 0, "skipped": 0, "snapshots": set(), "changes": 0, "events": 0, "refused": 0, "waiting": 0}


def archive_step(s, data_dir, spend, today, *, now=time.time, clock=time.monotonic, search=None, token=None,
                 max_calls=ARCH_MAX_CALLS, max_sec=ARCH_MAX_SEC, taken=None):
    """The build's archive step (GADS_ARCHIVE on) → its public lines (counts only, one per part). `spend` = the merged
    spend cache (read only). `taken` = google_ads.take_rows() (taken here when None). search / token / now / clock:
    injectable. Each part in its own try: a failure costs only that part's update this build."""
    from . import gads_campaign_day as gcd
    from . import gads_hourly as ghr
    from . import google_ads as gads
    today = d(today)
    if taken is None:
        taken = gads.take_rows()
    lines = []
    cst, hst, ast = gcd.stats(), ghr.stats(), _arch_stats()
    try:                                                        # a. the fetched rows (0 calls)
        gcd.capture(data_dir, taken, spend, cst)
    except Exception as e:
        lines.append("gads campaign days skipped: %s" % type(e).__name__)
        cst = None
    if not usable(s):
        lines.insert(0, archive_line(ast, "off", 0, 0))
        if cst is not None:
            lines.append(gcd.public_line(cst, "off", 0, 0))
        lines.append(ghr.public_line(hst, "off", 0, 0))
        return lines
    run = _Run(clock, max_calls, max_sec)
    sess = Session(s, run, search, token, today)
    calls = errors = 0
    try:                                                        # b. the archive (first: its history is lost if late)
        word = archive_part(sess, data_dir, today, ast)
        lines.insert(0, archive_line(ast, word, run.calls, run.errors))
    except Exception as e:
        lines.insert(0, "gads archive skipped: %s" % type(e).__name__)
    calls, errors = run.calls, run.errors
    try:                                                        # c. spend by hour
        word = ghr.hourly_part(sess, data_dir, spend, today, hst, now=now)
        lines.append(ghr.public_line(hst, word, run.calls - calls, run.errors - errors))
    except Exception as e:
        lines.append("gads hours skipped: %s" % type(e).__name__)
    calls, errors = run.calls, run.errors
    if cst is not None:
        try:                                                    # d. the per-campaign backfill
            word = gcd.backfill(sess, data_dir, spend, today, cst)
            lines.append(gcd.public_line(cst, word, run.calls - calls, run.errors - errors))
        except Exception as e:
            lines.append("gads campaign days skipped: %s" % type(e).__name__)
    return lines
