"""Shared parts of the Google Ads ARCHIVE stores (GADS_ARCHIVE; fetch.gads_archive, gads_campaign_day, gads_hourly,
gads_geo_day): month files, the build's Google Ads session (token + MCC roster + call budget) and field-tolerant queries.

Month files: <data>/<store dir>/<YYYY-MM>.json.gz, written with db.write_json_gz_stable (sorted keys, no gzip time
stamp, only on change) — the same inputs always give the same bytes, and an unchanged month is never rewritten. Nothing
is created (no folder, no file) until a store has something to keep.

Field-tolerant query (robust): a GAQL query is its core fields + optional fields. An HTTP 400 queryError that names
optional fields drops those and asks again (twice at most; a refusal naming none, or a third one, asks the core fields
only); the drop is remembered (per query kind, `drop` in the store's state) only when the smaller query then worked,
and tried again after DROP_RETRY_DAYS — so a field another API version renamed costs one refused call a month, not
the whole archive.
"""

import gzip
import json
import os
import re
import threading
from datetime import date, timedelta

from ..db import write_json_gz_stable
from . import google_ads as gads
from .gads_geo import _Stop, _is403

DROP_RETRY_DAYS = 30                # a refused optional field is asked for again after this long
ROSTER_CORE = ("customer_client.id", "customer_client.manager")
ROSTER_OPT = ("customer_client.currency_code", "customer_client.time_zone", "customer_client.status")
LIVE_STATUS = (None, "ENABLED")     # roster accounts asked (CANCELED / SUSPENDED / CLOSED answer 403: never asked)
MONTH_RE = re.compile(r"^(\d{4}-\d{2})\.json\.gz$")


# ── dates ─────────────────────────────────────────────────────────────────────────────────────────

def d(s):
    return s if isinstance(s, date) else date.fromisoformat(str(s)[:10])


def days(a, b):
    """Every ISO day of [a, b]."""
    a, b = d(a), d(b)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def month_of(day):
    return str(day)[:7]


# ── settings ──────────────────────────────────────────────────────────────────────────────────────

def usable(s):
    """The Google Ads secrets are all there (the same test as the spend fetch)."""
    need = ("google_ads_dev_token", "google_ads_login_customer_id", "google_ads_refresh_token")
    if not all(s.get(k) for k in need):
        return False
    return bool((s.get("google_ads_client_id") or s.get("google_client_id"))
                and (s.get("google_ads_client_secret") or s.get("google_client_secret")))


def spend_ok(spend):
    return isinstance(spend, dict) and not spend.get("error") and isinstance(spend.get("daily"), dict)


# ── files ─────────────────────────────────────────────────────────────────────────────────────────

def read_gz(path):
    try:
        with gzip.open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except Exception:
        return None


class Months:
    """Lazy {month: dict} over <dir>/<YYYY-MM>.json.gz. make(month) → a new empty month; ok(obj) → a file is usable
    (another version or a damaged file starts empty — and is replaced only once that month gets something)."""

    def __init__(self, dirpath, make, ok):
        self.dir, self.make, self.ok = dirpath, make, ok
        self.got, self.touched = {}, set()

    def on_disk(self):
        try:
            return sorted(m.group(1) for m in (MONTH_RE.match(f) for f in os.listdir(self.dir)) if m)
        except OSError:
            return []

    def months(self):
        return sorted(set(self.on_disk()) | set(self.got))

    def peek(self, m):
        if m not in self.got:
            obj = read_gz(os.path.join(self.dir, m + ".json.gz"))
            self.got[m] = obj if isinstance(obj, dict) and self.ok(obj) else self.make(m)
        return self.got[m]

    def get(self, m):
        """The month to change (saved by save())."""
        self.touched.add(m)
        return self.peek(m)

    def save(self):
        """Write the touched months (only on change) → how many were written."""
        n = 0
        for m in sorted(self.touched):
            if write_json_gz_stable(os.path.join(self.dir, m + ".json.gz"), self.got[m]):
                n += 1
        self.touched = set()
        return n


def load_state(dirpath, v, defaults):
    st = read_gz(os.path.join(dirpath, "state.json.gz"))
    if not isinstance(st, dict) or st.get("v") != v:
        st = {"v": v}
    for k, x in defaults.items():
        st.setdefault(k, json.loads(json.dumps(x)))
    return st


def save_state(dirpath, st):
    return write_json_gz_stable(os.path.join(dirpath, "state.json.gz"), st)


# ── rows ──────────────────────────────────────────────────────────────────────────────────────────

def _camel(p):
    parts = p.split("_")
    return parts[0] + "".join(x[:1].upper() + x[1:] for x in parts[1:])


def field(row, path):
    """A GAQL field (snake_case path, e.g. "campaign.target_roas.target_roas") out of a REST row (camelCase) → value
    or None."""
    cur = row
    for p in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(_camel(p))
    return cur


def tail_id(v):
    """'customers/1/campaigns/22' → '22'; '22' → '22'; None → None."""
    if v in (None, ""):
        return None
    return str(v).rsplit("/", 1)[-1] or None


def code_of(e):
    """A failed call → its Google Ads error code ('authorizationError=USER_PERMISSION_DENIED'), else 'HTTP nnn', else
    the exception class (PRIVATE files only; never printed)."""
    s = str(e)
    c = re.search(r"\b([A-Za-z]+Error=[A-Z0-9_]+)", s)
    if c:
        return c.group(1)
    m = re.match(r"HTTP (\d{3})", s)
    return "HTTP " + m.group(1) if m else type(e).__name__


def not_enabled(e):
    """HTTP 403 for the whole account (cancelled / not enabled), not a refused field or resource."""
    return _is403(e) and "CUSTOMER_NOT_ENABLED" in str(e)


# ── the build's Google Ads session ────────────────────────────────────────────────────────────────

class Session:
    """One build's Google Ads context for the archive stores: the token, the MCC roster {account: {"ccy", "tz",
    "status"}} and the call budget (gads_geo._Run), made lazily and once. `drop` = the state's remembered refused
    optional fields ({kind: {"f": [...], "at": day}}); new ones collect in self.new_drop (merged by the caller)."""

    def __init__(self, s, run, search=None, token=None, today=None, drop=None):
        self.s, self.run, self.today = s, run, d(today or date.today())
        self.search = run.counted(search or gads._search)
        self.token = token
        self.mcc = str(s.get("google_ads_login_customer_id") or "").replace("-", "")
        self.dev = s.get("google_ads_dev_token")
        self.ok = None
        self.accounts = {}
        self.drop = dict(drop or {})
        self.new_drop = {}
        self.lock = threading.Lock()

    def ready(self):
        if self.ok is not None:
            return self.ok
        self.ok = False
        if not self.token:
            try:
                s = self.s
                self.token = gads._access_token(s.get("google_ads_client_id") or s.get("google_client_id"),
                                                s.get("google_ads_client_secret") or s.get("google_client_secret"),
                                                s.get("google_ads_refresh_token"))
            except Exception:
                self.run.errors += 1
                return False
        try:
            rows, _used = robust(self, self.mcc, "roster", "customer_client", ROSTER_CORE, ROSTER_OPT)
        except Exception as e:
            if _is403(e):
                self.run.errors += 1                    # on the MCC a 403 is a real error (counted once)
            return False
        for row in rows or []:
            cc = row.get("customerClient") or {}
            if cc.get("manager") or cc.get("id") in (None, ""):
                continue
            self.accounts[str(cc.get("id"))] = {"ccy": cc.get("currencyCode") or "USD", "tz": cc.get("timeZone"),
                                                "status": cc.get("status")}
        self.ok = True
        return True

    def live(self):
        """Accounts that can answer (status ENABLED, or not said), sorted."""
        return sorted(a for a, v in self.accounts.items() if v.get("status") in LIVE_STATUS)

    def ccy(self, acct):
        return (self.accounts.get(acct) or {}).get("ccy") or "USD"

    def _remembered(self, kind):
        """The state's refused optional fields of `kind` still in force (younger than DROP_RETRY_DAYS)."""
        x = self.drop.get(kind) or {}
        if x.get("at") and (self.today - d(x["at"])).days < DROP_RETRY_DAYS:
            return set(x.get("f") or [])
        return set()

    def dropped(self, kind):
        with self.lock:
            nd = self.new_drop.get(kind)
            return set(nd["f"]) if nd else self._remembered(kind)

    def refused(self, kind, fields):
        """New refusals join the ones still in force (one list per kind, dated today)."""
        with self.lock:
            nd = self.new_drop.get(kind)
            cur = set(nd["f"]) if nd else self._remembered(kind)
            self.new_drop[kind] = {"f": sorted(cur | set(fields)), "at": self.today.isoformat()}


NAMED_DROPS = 2                     # refusals naming optional fields dropped one by one before the core-only ask


def robust(sess, cust, kind, frm, core, opt, where="", tail=""):
    """SELECT core + the optional fields Google accepts → (rows, optional fields used). An HTTP 400 queryError naming
    optional fields drops them and asks again (NAMED_DROPS times); one naming none — or one more after those — asks
    the core fields only, so a kind never fails for its optional fields (≤ NAMED_DROPS + 2 requests). Remembered (only
    when a smaller query then worked): the fields Google named, or every field a nameless refusal dropped — so the next
    builds ask the remaining optional fields again and learn any further bad one. _Stop and other errors raise."""
    use = [f for f in opt if f not in sess.dropped(kind)]
    bad = []
    last = None
    for i in range(NAMED_DROPS + 2):
        q = "SELECT %s FROM %s%s%s" % (", ".join(list(core) + use), frm, (" WHERE " + where) if where else "", tail)
        try:
            rows = sess.search(cust, sess.mcc, sess.dev, sess.token, q)
        except _Stop:
            raise
        except Exception as e:
            msg = str(e)
            if not (msg.startswith("HTTP 400") and "queryError=" in msg) or not use:
                raise
            last = e
            named = [f for f in use if re.search(r"(?<![\w.])%s(?![\w.])" % re.escape(f), msg)]
            bad += named or list(use)
            gone = named if named and i < NAMED_DROPS else list(use)
            use = [f for f in use if f not in gone]
            continue
        if bad:
            sess.refused(kind, bad)
        return rows or [], use
    raise last
