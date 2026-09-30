"""Daily App Review — the snapshot store: freeze today's cards ONCE (at the first build on or after REVIEW_READY_IST,
IST), never rewrite or delete a snapshot (except one requested rebuild of today), publish every snapshot to the site
and write site/review/index.json.

    data/review/days/<YYYY-MM-DD>.json.gz   canonical snapshots (persist in the private repo's data/)
    data/review/meta.json                   {"v":1, "go_live", "rebuilt": {day: built_at}, "fails": {day: n}}
    data/review/seen/<YYYY-MM-DD>.json      {"v":1, "day", "apps": {app key: [row_id]}} — the red / amber rows each
                                            snapshot showed (private data/ only; never published): the next days'
                                            "Pehli baar dikha" and the "Kab se" of rows without a real start date
    site/review/days/<YYYY-MM-DD>.json.gz   byte copies the page reads
    site/review/index.json                  open day, days list, open apps (the page + the Worker read it)

The build log gets exactly ONE line, counts and dates only."""

import gzip
import json
import os
import re
import sys
import time
from datetime import datetime, time as dtime, timedelta, timezone

from ..db import write_json_gz_stable
from .const import DOC_V, REVIEW_READY_IST_DEFAULT
from .day import build_day
from .site import Site

IST = timedelta(hours=5, minutes=30)
_DAY_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json\.gz$")
_READY = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def review_day_ist(now):
    """The IST calendar day of a UTC instant (naive = UTC)."""
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    return (now + IST).date()


def parse_ready(value):
    """'HH:MM' (24 h) → 'HH:MM'; empty or invalid → the default 09:00."""
    m = _READY.match(value or "")
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"
    return REVIEW_READY_IST_DEFAULT


def _now_utc(now):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def is_ready(now, day, ready):
    """True when the IST ready time of `day` has passed at `now` (a past day is always ready)."""
    h, m = (int(x) for x in ready.split(":"))
    now_ist = (now.astimezone(timezone.utc).replace(tzinfo=None) + IST)
    return now_ist >= datetime.combine(day, dtime(h, m))


def _days_dir(data_dir):
    return os.path.join(data_dir, "review", "days")


def day_path(data_dir, d):
    return os.path.join(_days_dir(data_dir), f"{d}.json.gz")


def read_doc(path, d=None):
    """The snapshot at `path` if it is VALID (gunzips, parses, v == 1, day == d), else None."""
    try:
        with open(path, "rb") as f:
            doc = json.loads(gzip.decompress(f.read()).decode("utf-8"))
    except Exception:                                  # missing, damaged, not gzip, not JSON
        return None
    if not isinstance(doc, dict) or doc.get("v") != DOC_V or (d is not None and doc.get("day") != d):
        return None
    return doc


def _meta_path(data_dir):
    return os.path.join(data_dir, "review", "meta.json")


def load_meta(data_dir):
    try:
        with open(_meta_path(data_dir), encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, ValueError):
        m = {}
    if not isinstance(m, dict):
        m = {}
    out = {"v": 1, "go_live": m.get("go_live") if isinstance(m.get("go_live"), str) else None,
           "rebuilt": m.get("rebuilt") if isinstance(m.get("rebuilt"), dict) else {},
           "fails": m.get("fails") if isinstance(m.get("fails"), dict) else {}}
    return out


def _write_stable_json(path, obj, indent=None):
    """Write plain JSON (sorted keys) only when the bytes change. -> True when written."""
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=indent,
                     separators=(",", ":") if indent is None else (",", ": ")).encode("utf-8")
    try:
        with open(path, "rb") as f:
            if f.read() == raw:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, path)
    return True


def save_meta(data_dir, meta):
    return _write_stable_json(_meta_path(data_dir), meta, indent=1)


def snapshot_days(data_dir):
    """Every VALID canonical snapshot → {day: doc}, oldest first."""
    out = {}
    try:
        names = sorted(os.listdir(_days_dir(data_dir)))
    except OSError:
        return out
    for n in names:
        m = _DAY_FILE.match(n)
        if not m:
            continue
        doc = read_doc(os.path.join(_days_dir(data_dir), n), m.group(1))
        if doc is not None:
            out[m.group(1)] = doc
    return out


def _seen_path(data_dir, d):
    return os.path.join(data_dir, "review", "seen", f"{d}.json")


def load_seen(data_dir, d):
    """{app key: set(row_id)} that snapshot day d showed, or None (missing / unreadable)."""
    try:
        with open(_seen_path(data_dir, d), encoding="utf-8") as f:
            j = json.load(f)
        if not isinstance(j, dict) or j.get("day") != d or not isinstance(j.get("apps"), dict):
            return None
        return {k: {str(x) for x in v} for k, v in j["apps"].items() if isinstance(v, list)}
    except (OSError, ValueError):
        return None


def load_history(data_dir, day, go_live):
    """The store's history for building `day`: {"go_live": date, "seen": {app key: {row_id: first date}}} — for
    every row the LATEST earlier snapshot showed, the first day of its unbroken run of snapshots (walking back while
    each earlier snapshot's seen file still lists it). A missing seen file ends every run there."""
    ds = day.isoformat()
    prev = sorted((d for d in snapshot_names(data_dir) if d < ds), reverse=True)
    seen, alive = {}, None
    for d in prev:
        s = load_seen(data_dir, d)
        if s is None:
            break
        dd = datetime.strptime(d, "%Y-%m-%d").date()
        if alive is None:
            alive = {k: set(v) for k, v in s.items()}
        else:
            alive = {k: v & s.get(k, set()) for k, v in alive.items()}
            alive = {k: v for k, v in alive.items() if v}
        if not alive:
            break
        for k, v in alive.items():
            for rid in v:
                seen.setdefault(k, {})[rid] = dd
    gl = datetime.strptime(go_live, "%Y-%m-%d").date() if go_live else day
    return {"go_live": min(gl, day), "seen": seen}


def save_seen(data_dir, d, apps):
    _write_stable_json(_seen_path(data_dir, d), {"v": 1, "day": d, "apps": {k: sorted(v) for k, v in apps.items()}})


def snapshot_names(data_dir):
    """The days that have a canonical snapshot FILE (validity is not checked — cheap)."""
    try:
        return sorted(m.group(1) for m in map(_DAY_FILE.match, os.listdir(_days_dir(data_dir))) if m)
    except OSError:
        return []


def publish(data_dir, out_dir, days):
    """Copy every canonical snapshot byte-for-byte to site/review/days/ when the site copy is missing or differs.
    Nothing under site/review/ is ever deleted. -> number of files copied."""
    n = 0
    dst_dir = os.path.join(out_dir, "review", "days")
    for d in days:
        src = day_path(data_dir, d)
        dst = os.path.join(dst_dir, f"{d}.json.gz")
        with open(src, "rb") as f:
            raw = f.read()
        try:
            with open(dst, "rb") as f:
                if f.read() == raw:
                    continue
        except OSError:
            pass
        os.makedirs(dst_dir, exist_ok=True)
        tmp = dst + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, dst)
        n += 1
    return n


def index_doc(docs, go_live, today, ready, ready_passed):
    """site/review/index.json (no per-run timestamps: it changes only when its content does)."""
    days = [d for d in sorted(docs) if go_live is None or d >= go_live]
    open_day = max((d for d in days if d <= today.isoformat()), default=None)
    pending = today.isoformat() not in docs
    retry = bool(pending and ready_passed)
    if not pending:
        nxt = today + timedelta(1)
    elif not ready_passed:
        nxt = today
    else:
        nxt = None
    open_apps = {}
    if open_day:
        for a in docs[open_day].get("apps") or []:
            if isinstance(a, dict) and a.get("key"):
                open_apps[a["key"]] = f"{a.get('name', '')} · {a.get('acct', '')}"
    return {
        "v": 1,
        "go_live": go_live,
        "today_ist": today.isoformat(),
        "open_day": open_day,
        "pending_today": pending,
        "retry": retry,
        "ready_ist": ready,
        "next_snapshot": f"{nxt.isoformat()}T{ready}:00+05:30" if nxt else None,
        "days": [{"d": d, "apps": len(docs[d].get("apps") or []),
                  "top": len((docs[d].get("order") or {}).get("top") or []),
                  "small": len((docs[d].get("order") or {}).get("small") or []),
                  "file": f"review/days/{d}.json.gz"} for d in days],
        "open_apps": open_apps,
    }


def _err_name(e):
    return re.sub(r"[^A-Za-z_]", "", type(e).__name__) or "Error"


def run_review(dashboard, data_dir, out_dir, now=None, **kw):
    """Freeze today's snapshot (once, after the ready time), publish every snapshot and write site/review/index.json.
    → ["/review/*"] when site/review/ exists afterwards (for _headers), else []. Prints ONE counts-only line.

    dashboard: the build's in-memory dashboard (None: read <out_dir>/dashboard.json.gz). now: UTC clock (tests).
    Keyword options (the CLI): today (the review day; default the IST day of `now`), force (ignore the ready time),
    rebuild (rebuild today's snapshot once — the REVIEW_REBUILD_DAY=<today> rule), env (os.environ; tests)."""
    return review_run(dashboard, data_dir, out_dir, now, **kw)["paths"]


def review_run(dashboard, data_dir, out_dir, now=None, *, today=None, force=False, rebuild=False, env=None,
               site=None):
    """run_review's body → {"paths", "ok" (False only when today's build failed), "line"}."""
    t0 = time.monotonic()
    env = os.environ if env is None else env
    now = _now_utc(now)
    day = today or review_day_ist(now)
    ds = day.isoformat()
    ready = parse_ready(env.get("REVIEW_READY_IST"))
    ready_passed = is_ready(now, day, ready)
    rb_env = (env.get("REVIEW_REBUILD_DAY") or "").strip()
    meta = load_meta(data_dir)
    path = day_path(data_dir, ds)
    existing = read_doc(path, ds)
    status, ignored = None, bool(rb_env) and rb_env != ds
    want_rebuild = (rebuild or rb_env == ds) and ds not in meta["rebuilt"]
    if existing is not None and not want_rebuild:
        status = "exists"
    elif existing is not None or ready_passed or force:
        try:
            try:
                hist = load_history(data_dir, day, meta["go_live"])
            except Exception:                              # history only improves two texts; never blocks a day
                hist = None
            seen_out = {}
            doc = build_day(site or Site(out_dir, dashboard), day, now=now, ready_ist=ready, history=hist,
                            seen_out=seen_out)
            write_json_gz_stable(path, doc)
            if read_doc(path, ds) is None:
                raise OSError("snapshot not readable")
            try:
                save_seen(data_dir, ds, seen_out)
            except Exception:                              # tomorrow's "Pehli baar dikha" restarts; the day stands
                pass
            c = doc["counts"]
            word = "rebuilt" if existing is not None else "built"
            status = (f"{word} (apps {c['apps']}, top {c['attn']}, ok {c['ok']}, small {c['small']}, "
                      f"failed {c['failed']})")
            if existing is not None or want_rebuild:  # a requested rebuild is used up by this build either way
                meta["rebuilt"][ds] = doc["built_at"]
            if not meta["go_live"]:
                meta["go_live"] = ds
        except Exception as e:
            meta["fails"][ds] = int(meta["fails"].get(ds) or 0) + 1
            status = f"failed ({_err_name(e)}) · retry next run"   # (a failed rebuild keeps the snapshot as it was)
    docs = snapshot_days(data_dir)
    if not meta["go_live"] and docs:
        meta["go_live"] = min(docs)
    save_meta(data_dir, meta)
    published = publish(data_dir, out_dir, [d for d in sorted(docs)])
    idx = index_doc(docs, meta["go_live"], day, ready, ready_passed or force)
    _write_stable_json(os.path.join(out_dir, "review", "index.json"), idx)
    if status is None:
        status = f"waiting (ready {ready} IST) · open {idx['open_day'] or 'none'}"
    line = (f"review: day {ds} · {status}{' · rebuild ignored' if ignored else ''} · days {len(idx['days'])} · "
            f"published {published} · {time.monotonic() - t0:.1f}s")
    print(line, file=sys.stderr)
    return {"paths": ["/review/*"] if os.path.isdir(os.path.join(out_dir, "review")) else [],
            "ok": not status.startswith("failed"), "line": line}
