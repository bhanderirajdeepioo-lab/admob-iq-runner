"""python -m admob_iq.review --site DIR --data DIR [--today YYYY-MM-DD] [--now ISO8601] [--force] [--rebuild]

Runs ONLY the Daily App Review builder over an already-built site dir (reads DIR/dashboard.json.gz and the other site
files; writes DIR/review/… and DATA/review/…). Ignores REVIEW_ENABLED. Prints the same one counts-only line as the
build. Exit 0 on success (built / exists / waiting), 1 when the day's build failed."""

import argparse
import sys
from datetime import date, datetime, timezone

from .store import review_day_ist, review_run


def _parse_now(s):
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m admob_iq.review", description="Daily App Review snapshot builder")
    ap.add_argument("--site", required=True, help="built site dir (has dashboard.json.gz)")
    ap.add_argument("--data", required=True, help="data dir (snapshots go to DATA/review/)")
    ap.add_argument("--today", help="review day YYYY-MM-DD (default: the IST day of --now)")
    ap.add_argument("--now", help="the clock, ISO 8601 (default: now)")
    ap.add_argument("--force", action="store_true", help="ignore the ready time")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the --today snapshot once")
    a = ap.parse_args(argv)
    try:
        now = _parse_now(a.now) if a.now else datetime.now(timezone.utc)
        today = date.fromisoformat(a.today) if a.today else review_day_ist(now)
    except ValueError:
        print("review: bad --now / --today", file=sys.stderr)
        return 1
    try:
        res = review_run(None, a.data, a.site, now, today=today, force=a.force, rebuild=a.rebuild)
    except Exception as e:                                   # the error TYPE only (the log may be public)
        print(f"review skipped: {type(e).__name__}", file=sys.stderr)
        return 1
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
