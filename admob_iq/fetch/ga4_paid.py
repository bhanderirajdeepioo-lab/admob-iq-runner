"""⚖️ Google Ads users only — the shared piece of the paid GA4 stores (owner, 16 Nov 2026: "haan sirf google ads wale
users se karo · google ads and organic dono ka alag alag dekh saku esa kar do"). GA4 marks a user Google Ads brought by
the FIRST-USER channel group: firstUserDefaultChannelGroup in PAID — the owner's grouping, "Cross-network" + "Paid
Search"; every other group (organic, direct, unassigned …) is everyone else. Measured before any store was built
(fetch/ga4_paid_probe.py, the cohort cube's own request shape with this filter): GA4 accepts the filtered read, it adds
up with its complement to the unfiltered one, and GA4's paid new users match the Google Ads installs.

  * expr(): that in-list, a fresh filter expression on every call (a request never shares one);
  * App: ga4_firstopen.App (the property's quota gate, the run's clock, the app's call cap, the token count — all as
    they are) whose every runReport is held to those users: Ga4App.report builds the request's dimensionFilter as
    stream_filter's andGroup (platform, streamId, the event filters, every extra expression), and App.report adds the
    paid in-list after the caller's own extra expressions — so it is AND-ed into EVERY read whatever its own filters
    (a split part's country / install-day lists, a day's total, a whole no-country read); report_all pages through
    report(): every page carries it too. Every runReport first passes Screens' STRICTER quota floors too
    (ga4_screens.quota_gate: 60 % of an hourly bucket, 40 % of the day's, 60 thresholded requests left — where the
    App's own gate, every live step's, stops at 50 % / 10 % / 5): the paid steps run after Screens, so their history
    backfill never takes what the live steps need on the next build (Screens' own rule). A property under one of them
    stops as at the App's own floors: prop["stop"] (every later call on it stops too), Stop raised before the call
    (the app "deferred"). _post, Stop and paging stay the App's;
  * instance(base, name, **over): a SECOND, independent instance of a fetch module's own source file — its own module
    globals (the store's folder, the client's class, the log line's label, its knobs), the same shared modules under
    it — so a paid store runs the fetch's whole code as it is: never a copy, never a refactor (fetch.ga4_cube_paid:
    the cohort cube; fetch.ga4_nvr_paid: the first-session country read). The base module is never touched;
  * streak(mod, data_dir, out, now): ga4_cecpm's stuck rule beside a paid store's run (the base fetches retry a failed
    app every RETRY_HOURS and never count it): an app failing FAIL_LINE runs in a row counts "stuck" — the build
    prints the health banner's line, so a paid read GA4 refuses run after run never fails silently.
No GA4 call or print of its own (streak: the paid store's state.json only, through the instance's own load / save).
"""
import importlib.util
import sys

from . import ga4
from . import ga4_firstopen as gf
from . import ga4_screens as gs
from . import ga4_uninstall as gu

CHANNEL = "firstUserDefaultChannelGroup"     # the FIRST-USER channel group (never the session's)
PAID = ("Cross-network", "Paid Search")      # the owner's grouping: the users Google Ads brought
FAIL_LINE = 3                                # an app failing this many runs in a row is "stuck" (ga4_cecpm's line):
#                                              the health banner


def expr():
    """The paid filter expression: CHANNEL in PAID — a fresh dict on every call."""
    return ga4._in_list(CHANNEL, PAID)


class App(gf.App):
    """ga4_firstopen.App whose every runReport (each page of report_all too) is held to Google Ads users: the paid
    in-list AND-ed after the caller's own extra expressions (the caller's list is never changed) — and first passes
    Screens' stricter quota floors (ga4_screens.quota_gate on the property's last snapshot; under one: prop["stop"],
    Stop before the call). runReport only — the funnel and realtime reads (never made by the stores built on it) stay
    the App's own, unfiltered."""

    def report(self, body, event=None, events=None, extra=None):
        why = None if self.prop.get("stop") else gs.quota_gate(self.prop.get("quota"))
        if why:                                 # under Screens' floors: the property stops for this run, as at the
            self.prop["stop"] = why             # App's own (every later call on it stops too)
            raise gf.Stop(why)
        return super().report(body, event, events, list(extra or []) + [expr()])


def instance(base, name, **over):
    """A second, independent instance of module `base`'s source file → the new module (registered as sys.modules[name]
    before it runs, as an import does), with each module global of `over` set on it — every name one the module
    defines (an unknown one raises AttributeError: a typo never adds a dead knob). `name` is a sibling of base
    ("admob_iq.fetch.<something>", never base's own): its relative imports resolve against that package, so it shares
    every module under it (ga4, ga4_firstopen, ga4_uninstall …) and only its own globals differ. The base module and
    its globals are never touched. A failure leaves sys.modules as it was."""
    pkg = base.__name__.rpartition(".")[0]
    if name == base.__name__ or name.rpartition(".")[0] != pkg:
        raise ValueError("instance(): the name must be a sibling of the base module, never the base itself")
    spec = importlib.util.spec_from_file_location(name, base.__file__)
    mod = importlib.util.module_from_spec(spec)
    prev = sys.modules.get(name)                # (an earlier instance of that name: back in place on a failure)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
        bad = sorted(k for k in over if k not in vars(mod))
        if bad:
            raise AttributeError("instance(): %s defines no %s" % (base.__name__, ", ".join(bad)))
        for k, v in over.items():
            setattr(mod, k, v)
    except BaseException:
        if sys.modules.get(name) is mod:
            if prev is None:
                del sys.modules[name]
            else:
                sys.modules[name] = prev
        raise
    return mod


def streak(mod, data_dir, out, now):
    """ga4_cecpm's stuck rule after a run of a paid store's instance `mod` (its refresh_all, run at `now`, returned
    `out`): each app's failed runs in a row, "fails" in the store's state (mod.load_state / save_state) — a run that
    tried the app and failed adds one (its "last_try" is this run's), a fetched / fresh one ends the streak, a deferred
    or waiting app and one the RETRY_HOURS gate held back (failed, not tried) keep theirs — and out["counts"]["stuck"]
    = the apps failed in this run with FAIL_LINE or more in a row (the build prints the step's health line with the
    type StuckAppError: the health banner). A run that ended in an "error" is left as it is (its own line is the
    banner); a failure here → out["error"]. → out. Never raises."""
    if out.get("error"):
        return out
    try:
        state, now_iso, stuck = mod.load_state(data_dir), gu._now_iso(now), 0
        for aid, v in out["apps"].items():
            st = state["fetch"].get(aid)
            if not isinstance(st, dict):
                continue
            if v == "failed" and st.get("last_try") == now_iso:
                st["fails"] = int(st.get("fails") or 0) + 1
            elif v in ("fetched", "fresh"):
                st.pop("fails", None)
            stuck += v == "failed" and int(st.get("fails") or 0) >= FAIL_LINE
        mod.save_state(data_dir, state)
        out["counts"]["stuck"] = stuck
    except Exception as e:                      # a bug here must never cost the build
        out["error"] = type(e).__name__
    return out
