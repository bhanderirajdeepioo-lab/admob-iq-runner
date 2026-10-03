"""Synthetic GA4 users for the Audience tests (fetch.ga4_audience, engine.audience) — no real data anywhere.

A Population is a list of users, each (install day X, last open day L ≥ X, uninstall day R or None). A user is ACTIVE on
X and on L only (GA4 counts an open as activity; app_remove is not one), so "active in [S, E]" = X or L inside it. From
it: the Uninstall store (daily new, app_remove users by install day × lag), the Audience store as GA4 would answer it,
the TRUE dead users per install day / window, and FakeGA4 — a Data API runReport double (requests.post) that honours
named date ranges, the firstSessionDate dimension, the stream filter, firstSessionDate inList, limit / offset paging,
metricAggregations TOTAL per date range, and can fold rows into "(other)", threshold, sample, refuse TOTAL, fail or
report a low quota."""

import json
import random
from datetime import date, timedelta

from admob_iq.engine import audience as eng

E = date(2026, 9, 20)                         # the latest final day of the synthetic world
PID, PID_B = "900000001", "900000002"
SID, SID_B, SID_C = "7770000001", "7770000002", "7770000003"
EMAIL_A, RT_A, TOK_A = "owner.a@secret-ws.test", "rt-SECRET-a", "tok-SECRET-a"


def ymd(d):
    return d.strftime("%Y%m%d")


class Population:
    """`days` install days ending on E (start = E − days + 1); per install day `per_day` users. Each user's last open
    and uninstall come from a seeded random draw: `dormant_un` = the share of uninstallers who uninstall LATER than
    their last open by more than a month (they are not active when they uninstall); otherwise an uninstaller
    uninstalls on its last-open day (it opened, then uninstalled)."""

    def __init__(self, days=400, per_day=12, seed=7, un_share=0.4, dormant_un=0.0, end=E, extra=None):
        self.end, self.start = end, end - timedelta(days=days - 1)
        rnd = random.Random(seed)
        self.users = []
        for i in range(days):
            x = self.start + timedelta(days=i)
            for _ in range(per_day):
                age = (end - x).days
                last = x + timedelta(days=int(age * rnd.random() ** 2.5))     # most go quiet early
                r = None
                if rnd.random() < un_share:
                    if rnd.random() < dormant_un and (end - last).days > 31:
                        r = last + timedelta(days=31 + int((end - last - timedelta(days=31)).days * rnd.random()))
                    else:
                        r = last
                self.users.append((x, last, r))
        self.users += list(extra or [])

    # ── truth ──
    def active(self, u, a, b):
        x, last, _ = u
        return a <= x <= b or a <= last <= b

    def installed(self, u, at=None):
        r = u[2]
        return r is None or r > (at or self.end)

    def true_dead(self, x, w):
        """Users of install day x installed on E and not active in the last w days."""
        s = self.end - timedelta(days=w - 1)
        return sum(1 for u in self.users if u[0] == x and self.installed(u) and not self.active(u, s, self.end))

    # ── stores ──
    def uni_store(self, hs=None, window_end=None):
        """The Uninstall store as fetch.ga4_uninstall keeps it (the fields engine.audience reads)."""
        we = window_end or self.end + timedelta(days=3)
        daily, cohorts = {}, {}
        d = hs or self.start
        while d <= we:
            daily[d.isoformat()] = {"new": 0, "a1": 0, "a28": 0, "un": 0, "un_ev": 0, "upd": 0}
            d += timedelta(days=1)
        for x, last, r in self.users:
            if x.isoformat() in daily:
                daily[x.isoformat()]["new"] += 1
            if r is not None and r <= we:
                c = cohorts.setdefault(x.isoformat(), {})
                c[str((r - x).days)] = c.get(str((r - x).days), 0) + 1
                if r.isoformat() in daily:
                    daily[r.isoformat()]["un"] += 1
        for u in self.users:
            if self.active(u, self.end, self.end) and self.end.isoformat() in daily:
                daily[self.end.isoformat()]["a1"] += 1
        return {"v": 3, "history_start": (hs or self.start).isoformat(), "window_end": we.isoformat(),
                "daily": daily, "cohorts": cohorts, "unplaced": {}, "flags": {}, "time_zone": "UTC",
                "property_id": PID, "stream_id": SID}

    def actives(self, a, b):
        """{install day ISO: users active in [a, b]}."""
        out = {}
        for u in self.users:
            if self.active(u, a, b):
                out[u[0].isoformat()] = out.get(u[0].isoformat(), 0) + 1
        return out

    def aud_store(self, hs=None, months=None):
        """The complete Audience store GA4 would give on the tiered windows (exact counts; no "(other)", no
        thresholding). months: other window months (default: engine.audience.tier_months of the history)."""
        hs = hs or self.start
        months = list(months or eng.tier_months((self.end - hs).days + 1))
        windows = [eng.window_days(m) for m in months]
        by = {}
        tot = []
        for i, w in enumerate(windows):
            got = self.actives(self.end - timedelta(days=w - 1), self.end)
            for x, u in got.items():
                by.setdefault(x, [0] * len(windows))[i] = u
            tot.append(sum(got.values()))
        dau = self.actives(self.end, self.end)
        return {"v": 2, "complete": True, "E": self.end.isoformat(), "history_start": hs.isoformat(), "months": months,
                "windows": windows,
                "by_fsd": by, "total": tot, "other": [0] * len(windows), "not_set": [0] * len(windows),
                "dau_by_fsd": dau, "dau": {"total": sum(dau.values()), "other": 0, "not_set": 0}, "flags": {}}


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body or {}
        self.text = json.dumps(self._b)

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._b


class FakeGA4:
    """runReport over Populations: truths = {(property id, stream id): Population}. Options: other_over = N (a range
    with more than N first-session days and no inList filter folds the rest into "(other)", with dataLossFromOtherRow),
    thresholded / sampled (metadata), no_total (a 400 on metricAggregations), fail(body) → HTTP status or None,
    quota = {bucket: remaining} (fixed, reported with every call), hourly = {bucket: remaining at the start} (each call's
    tokens come off it), tokens = tokens a call costs (a number, or a function of the request body), loss_only = the
    dataLossFromOtherRow flag without any "(other)" row, other_slices = "(other)" even under an inList filter."""

    def __init__(self, truths, other_over=None, thresholded=False, sampled=False, no_total=False, fail=None,
                 quota=None, tokens=7, not_set=0, loss_only=False, hourly=None, other_slices=False):
        self.truths, self.other_over, self.thresholded, self.sampled = truths, other_over, thresholded, sampled
        self.loss_only = loss_only              # dataLossFromOtherRow on a read without inList, but no "(other)" row
        self.hourly = dict(hourly or {})        # {bucket: remaining at the start}: each call's tokens come off it
        self.other_slices = other_slices        # fold into "(other)" even under an inList filter
        self.hour_left = {}
        self.no_total, self.fail, self.quota, self.tokens, self.not_set = no_total, fail, dict(quota or {}), tokens, not_set
        self.bodies = []
        self.day_left = {}

    def post(self, url, headers=None, json=None, timeout=None):
        pid = url.split("/properties/")[1].split(":")[0]
        body = json
        self.bodies.append((pid, body))
        st = self.fail(body) if self.fail else None
        if st:
            return Resp(st, {"error": {"code": st, "status": "INTERNAL" if st >= 500 else "RESOURCE_EXHAUSTED"
                                       if st == 429 else "INVALID_ARGUMENT", "message": "SECRETDETAIL " + pid}})
        if self.no_total and body.get("metricAggregations"):
            return Resp(400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "metricAggregations"}})
        ex = body["dimensionFilter"]["andGroup"]["expressions"]
        pinned = {(e["filter"]["fieldName"], e["filter"]["stringFilter"]["value"]) for e in ex
                  if "stringFilter" in e["filter"]}
        sid = dict(pinned).get("streamId")
        assert ("platform", "Android") in pinned and body.get("returnPropertyQuota") is True
        pop = self.truths[(pid, sid)]
        in_list = None
        for e in ex:
            if "inListFilter" in e["filter"]:
                assert e["filter"]["fieldName"] == "firstSessionDate"
                in_list = set(e["filter"]["inListFilter"]["values"])
        resp = self.answer(pop, body, in_list)
        tok = self.tokens(body) if callable(self.tokens) else self.tokens
        left = self.day_left.setdefault(pid, 200000) - tok
        self.day_left[pid] = left
        q = {"tokensPerDay": {"consumed": tok, "remaining": left}}
        for k, v in self.quota.items():
            q[k] = {"consumed": tok, "remaining": v}
        for k, v in self.hourly.items():
            left = self.hour_left.setdefault((pid, k), v) - tok
            self.hour_left[(pid, k)] = left
            q[k] = {"consumed": tok, "remaining": left}
        resp["propertyQuota"] = q
        return Resp(body=resp)

    def answer(self, pop, body, in_list):
        assert [d["name"] for d in body["dimensions"]] == ["firstSessionDate"]
        assert [m["name"] for m in body["metrics"]] == ["activeUsers"]
        rngs = body["dateRanges"]
        assert 1 <= len(rngs) <= 4
        multi = len(rngs) > 1
        names = ["firstSessionDate"] + (["dateRange"] if multi else [])
        rows, totals, lost = [], [], False
        for i, rg in enumerate(rngs):
            name = rg.get("name") or "date_range_%d" % i
            got = pop.actives(date.fromisoformat(rg["startDate"]), date.fromisoformat(rg["endDate"]))
            cells = {ymd(date.fromisoformat(x)): u for x, u in got.items()}
            if in_list is not None:
                cells = {f: u for f, u in cells.items() if f in in_list}
            elif self.not_set:
                cells["(not set)"] = self.not_set
            tot = sum(cells.values())
            if self.other_over and (in_list is None or self.other_slices) and len(cells) > self.other_over:
                keep = sorted(cells)[-(self.other_over - 1):]
                folded = sum(u for f, u in cells.items() if f not in keep)
                cells = {f: cells[f] for f in keep}
                cells["(other)"] = folded
                lost = True
            for f, u in cells.items():
                if u:
                    rows.append({"firstSessionDate": f, "dateRange": name, "activeUsers": u})
            totals.append({"dateRange": name, "activeUsers": tot})
        rows.sort(key=lambda r: (r["firstSessionDate"], r["dateRange"]))
        off, lim = int(body.get("offset") or 0), int(body.get("limit") or 10000)

        def enc(r):
            return {"dimensionValues": [{"value": r[n]} for n in names],
                    "metricValues": [{"value": str(r["activeUsers"])}]}
        resp = {"dimensionHeaders": [{"name": n} for n in names], "metricHeaders": [{"name": "activeUsers"}],
                "rows": [enc(r) for r in rows[off:off + lim]], "rowCount": len(rows),
                "metadata": {"currencyCode": "USD"}}
        if lost or (self.loss_only and in_list is None):
            resp["metadata"]["dataLossFromOtherRow"] = True
        if self.thresholded:
            resp["metadata"]["subjectToThresholding"] = True
        if self.sampled:
            resp["metadata"]["samplingMetadatas"] = [{"samplesReadCount": "1", "samplingSpaceSize": "2"}]
        if "TOTAL" in (body.get("metricAggregations") or []):
            resp["totals"] = [{"dimensionValues": [{"value": "RESERVED_TOTAL"}] + ([{"value": t["dateRange"]}]
                                                                                    if multi else []),
                               "metricValues": [{"value": str(t["activeUsers"])}]} for t in totals]
        return resp
