"""Synthetic site for the 🗂 Review Studio tests — the Daily App Review's own synthetic site (tests/review_synth.py) with
the extra files the Studio reads: synthetic app icons (https://example.test/…), Uninstall cohort files for three apps,
an Active users file with a daily returning-users series, and the day's cards FROZEN by the real review store. No real
data: every id, name, package, URL and amount is made up.

  make(root)  → (site dir, data dir, dashboard dict)  — the day DAY frozen at rs.NOW (09:47 IST)
"""

import contextlib
import gzip
import io
import json
import os
from datetime import timedelta

from tests import review_synth as rs

ICON = {i: f"https://example.test/icons/synth-{i}.png" for i in (1, 2, 3, 4, 5)}


def _gz(path, obj):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def _days(end, n):
    return [end - timedelta(days=i) for i in range(n - 1, -1, -1)]


def cohort(day, base, turn_back, after):
    """90 install days ending on the GA4 day: 100 installs a day, `base` of them gone the same day, `after` from the
    install day `turn_back` days before the review day."""
    ga4 = day - timedelta(3)
    days = _days(ga4, 90)
    turn = day - timedelta(turn_back)
    return {"start": (ga4 - timedelta(89)).isoformat(), "end": ga4.isoformat(), "new": [100 for _ in days],
            "lags": [[[0, after if d >= turn else base], [2, 5]] for d in days]}


def active_file(day):
    """active_<key>.json.gz with 120 days of returning users (the last 3 days not final yet)."""
    ga4 = day - timedelta(3)
    days = _days(ga4, 120)
    return {"changes": {"info": []}, "act_late_days": 3, "data_till": ga4.isoformat(),
            "settled_till": (ga4 - timedelta(3)).isoformat(),
            "daily": {"start": days[0].isoformat(), "ret": [10000 + 7 * i for i in range(len(days))]}}


def make(root, day=rs.DAY):
    site, data = os.path.join(root, "site"), os.path.join(root, "data")
    dash = rs.make_site(site, day)
    dash["app_icons"] = {rs.A[i]: u for i, u in ICON.items()}
    _gz(os.path.join(site, "dashboard.json.gz"), dash)
    _gz(os.path.join(site, f"uninstall_c_{rs.K[3]}.json.gz"), cohort(day, 20, 23, 30))
    _gz(os.path.join(site, f"uninstall_c_{rs.K[1]}.json.gz"), cohort(day, 20, 40, 20))
    _gz(os.path.join(site, f"uninstall_c_{rs.K[6]}.json.gz"), cohort(day, 30, 12, 34))
    _gz(os.path.join(site, f"active_{rs.K[4]}.json.gz"), active_file(day))
    from admob_iq.review.store import review_run
    with contextlib.redirect_stderr(io.StringIO()):
        res = review_run(None, data, site, rs.NOW, today=day, env={"REVIEW_READY_IST": "09:00"})
    if not res["ok"]:
        raise RuntimeError("synthetic review build failed")
    return site, data, dash
