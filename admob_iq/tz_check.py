"""Time zone self-check: every zone NAME the build's data uses must load on THIS machine.

Python's zoneinfo reads the machine's own zone files first and the tzdata package second. On 1 Nov 2026 GitHub moved
ubuntu-latest to Ubuntu 26.04, whose zone files no longer carry the old alias names Google still sends (tzdata-legacy is
not installed there), and every day-boundary number that reads such a zone quietly fell back to a guess — the
install-day ("By date") D0 stopped, the eCPM "same time yesterday" line was dropped, the AdMob "today" turned to the UTC
date at night — while every build stayed green. The fix is tzdata in requirements.txt and a pinned runner image; this
check makes the next such fault LOUD instead of silent:
  dashboard["build_faults"]  [{"kind": "tz", "names": the names that did not load, "of": names checked}] — the page's
                             red banner (zone names only); absent when every name loads
  out_path (ZONE_CHECK_OUT)  {"names", "bad"} counts only, in the job's working directory (never pushed): the public
                             log's line (`python -m admob_iq.tz_check public <file>`)
Names checked: the AdMob report zone and each AdMob account's, each Google Ads account's (google_ads.ACCOUNT_TZ, filled
by this build's roster read) and each GA4 property's (the Uninstall state's "tz"). Never raises."""
import json
import os
import sys


def loads(name):
    """True when this machine's zoneinfo (its zone files, else the tzdata package) knows the zone name."""
    from zoneinfo import ZoneInfo
    try:
        ZoneInfo(str(name))
        return True
    except Exception:
        return False


def names(report_tz=None, account_tzs=None, data_dir=None):
    """The zone names this build's data uses (see the module docstring) → set of str."""
    out = {str(n) for n in [report_tz] + list((account_tzs or {}).values()) if n}
    try:
        from .fetch import google_ads
        out |= {str(n) for n in google_ads.ACCOUNT_TZ if n}
    except Exception:
        pass
    if data_dir:
        try:
            from .fetch import ga4_uninstall as gu
            with open(os.path.join(data_dir, gu.DIR, "state.json"), encoding="utf-8") as f:
                tz = (json.load(f) or {}).get("tz")
            out |= {str(n) for n in (tz.values() if isinstance(tz, dict) else ()) if n}
        except Exception:
            pass
    return out


def run(dashboard, report_tz=None, account_tzs=None, data_dir=None, out_path=None):
    """Check every name; set / clear dashboard["build_faults"]'s "tz" entry; write the counts file when out_path.
    → the names that did not load (sorted), None when the check itself failed (its error TYPE goes to stderr)."""
    try:
        ns = names(report_tz, account_tzs, data_dir)
        bad = sorted(n for n in ns if not loads(n))
        faults = [f for f in dashboard.get("build_faults") or () if isinstance(f, dict) and f.get("kind") != "tz"]
        if bad:
            faults.append({"kind": "tz", "names": bad, "of": len(ns)})
        if faults:
            dashboard["build_faults"] = faults
        else:
            dashboard.pop("build_faults", None)
        if bad:
            print("zone check: %d of %d time zone name(s) not found on this machine: %s"
                  % (len(bad), len(ns), ", ".join(bad)), file=sys.stderr)
        if out_path:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"names": len(ns), "bad": len(bad)}, f)
        return bad
    except Exception as e:
        print("zone check skipped: %s" % type(e).__name__, file=sys.stderr)
        return None


def public(path):
    """The public log's line from run()'s counts file: counts only, never a name."""
    try:
        with open(path, encoding="utf-8") as f:
            r = json.load(f)
        n, b = int(r.get("names") or 0), int(r.get("bad") or 0)
    except Exception:
        print("zone check: no result (the build did not reach it)")
        return
    if b:
        print("::warning::zone check: %d of %d time zone name(s) not found on this runner — the day-boundary numbers "
              "(By date D0, eCPM same time yesterday, today's date) are paused; the dashboard shows a red banner"
              % (b, n))
    else:
        print("zone check: %d time zone name(s), all found" % n)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "public":
        public(sys.argv[2])
