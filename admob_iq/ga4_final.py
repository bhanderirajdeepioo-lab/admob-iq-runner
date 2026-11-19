"""GA4_FINAL_DAYS: the one finality knob of every GA4 store (owner, 17 Nov 2026: "max to max 7 din me to aa hi jaata
he"). A GA4 day D is FINAL once the read a store keeps of it was made on the property's day D + FINAL_DAYS or later.
Until then the store reads D again (the costly stores read their older not-final days at most once a UTC day), and the
page marks D "not final".

FINAL_DAYS is read ONCE, at import, from the environment: the build and the history jobs pass the repo variable of the
same name. Unset, empty or not a whole number gives DEFAULT; any number is clamped to LO … HI. A store's own final lag
is lag(<its lag before this knob>), never less than FINAL_DAYS, so LO (3) is the rollback: every store then reads
exactly as it did before the knob, and every page is built exactly as before it (rollback(), page_lag()).

Pure: nothing from the package is imported, so an engine that never imports a fetch module reads it too. Read it as
ga4_final.FINAL_DAYS and ga4_final.lag(...) (the module's own attributes), so a test that sets another F reaches it."""
import os

DEFAULT, LO, HI = 7, 3, 14      # DEFAULT 7: the owner's "max to max 7 din". LO 3: every store's lag before this knob
#                                 (each keeps its own longer one: lag()). HI 14: ga4_firstopen keeps its 15-day window
#                                 (≥ F + 1), and the Uninstall re-read (GA4_REFETCH_DAYS 14, ages 2 … 15) still covers
#                                 the day turning final


def parse(v):
    """GA4_FINAL_DAYS as given (a str, or None when unset) → F: DEFAULT when unset, empty or not a whole number, else
    the number clamped to LO … HI."""
    try:
        n = DEFAULT if v in (None, "") else int(str(v).strip())
    except (TypeError, ValueError):
        n = DEFAULT
    return min(HI, max(LO, n))


FINAL_DAYS = parse(os.environ.get("GA4_FINAL_DAYS"))


def lag(floor):
    """A store's final lag: its own floor (its lag before this knob), never less than FINAL_DAYS. At FINAL_DAYS = LO
    every store's lag is exactly its old one."""
    return max(floor, FINAL_DAYS)


def rollback():
    """FINAL_DAYS at LO, the rollback: every store reads exactly as before this knob, and every build writes its page
    file exactly as before it too (page_lag: each page's own old edge; no edge field a page file did not have)."""
    return FINAL_DAYS <= LO


def page_lag(old, store_lag):
    """A build's final edge for its page: the producing store's lag — at the rollback `old`, that page's own edge
    before this knob (it showed days final while the store still read them again: as it was)."""
    return old if rollback() else store_lag
