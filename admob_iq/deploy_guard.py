"""Cloudflare deploy guard: whatever content the robot produces, Cloudflare must never reject the deploy.

Why it exists. On 2 Oct 2026 `site/_headers` grew to 101 rules (one no-store rule per app per GA4 tab) and Cloudflare
stopped deploying the site for 9 hours, while every robot run kept succeeding (the rejection happens on Cloudflare's
side, after the push). The headers were fixed at the source; this guard makes the whole class impossible. It runs on
the FINISHED site folder, just before `build_static.build()` returns, and checks the Cloudflare Workers static-asset
limits (developers.cloudflare.com/workers/platform/limits):

  * `_headers`    at most 100 rules, 2,000 characters a line, one splat a rule. Over the limit it is REWRITTEN: the
                  `/*` rule and the `/index.html` no-cache rule stay, every no-store rule collapses into the fewest
                  splat rules that still cover every data file, and every previously covered file is verified.
  * `_redirects`  (when present) at most 2,000 static and 100 dynamic rules, 1,000 characters a rule. Reported only:
                  the guard cannot know which redirect to drop.
  * file count    at most 20,000 files (the free plan). Never deleted, only reported.
  * file size     at most 25 MiB a file. An oversize file never ships: the previous good copy (the build starts from a
                  copy of the live site) takes its place, otherwise the file is left out of the site. Data inside a
                  file is NEVER trimmed ("never trim history"): the report says the feature needs a split.
                  Exception, the CORE files (what the first page load needs: CORE_FILES): never left out. With no
                  good previous copy they ship as they are, the report says the deploy WILL be rejected, and
                  Cloudflare then keeps the old site live, which beats a dashboard that cannot open.
  * asset paths   a name the upload would reject (control characters, backslash, ? and # , a broken % escape, a path
                  over 512 characters) is left out of the site. Cloudflare publishes no path rule for Workers static
                  assets; these are conservative, and they only ever match a name this site never generates.

Output: ONE counts-only log line (`deploy guard: rules H/100, files N/20000, largest X MiB, fixed: ...`) and
`deploy_guard.json` NEXT to the site (not inside it, so it is never deployed), which the workflow turns into
counts-only `::warning::` lines (`python -m admob_iq.deploy_guard annotate`). The guard never raises into the build and
never blocks the push: a deploy can then stay stuck only for a reason outside our content.
"""

import json
import os
import re
import shutil
import sys
from bisect import bisect_left
from datetime import datetime, timezone
from functools import lru_cache

HEADERS_MAX_RULES = 100
HEADERS_MAX_LINE = 2000
REDIRECTS_MAX_STATIC = 2000
REDIRECTS_MAX_DYNAMIC = 100
REDIRECTS_MAX_LINE = 1000
MAX_FILES = 20000                       # Workers Free; Paid allows 100,000, but the free limit is the one to stay under
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_PATH_CHARS = 512
MAX_NAME_BYTES = 255
NOSTORE = "Cache-Control: no-store"
REPORT_NAME = "deploy_guard.json"
PREV_DIRNAME = ".deploy_guard_prev"
# What the page needs to open (frontend/index.html boot: loadDashboardData, loadAppSel / loadAccNames / loadAppNames,
# rvFetchIndex, and the head's manifest + icons). Left out of the site, the dashboard would not open at all.
CORE_FILES = ("index.html", "dashboard.json.gz", "dashboard.json", "selected_apps.json", "account_names.json",
              "app_names.json", "review/index.json", "manifest.webmanifest", "icon-180.png", "icon-192.png", "icon-512.png")
_META = ("_headers", "_redirects", ".assetsignore")     # read by Cloudflare, never uploaded as assets (and not counted)
_MAX_LISTED = 50                                         # names kept per list in the report (the log never has any)


# ── _headers primitives (build_static re-exports these) ─────────────────────────────────────────────────────────────

_PATH_LINE = re.compile(r"^([^\s]+://|/)")


def parse_headers(text):
    """A _headers text → [(pattern, [header lines])], the way Cloudflare's parser reads it (wrangler parseHeaders): each
    line is trimmed, blank lines and # comments mean nothing, a line starting with "/" (or "scheme://") opens a rule and
    every other line is a header of the rule above."""
    rules = []
    for raw in text.split("\n"):
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        if _PATH_LINE.match(ln):
            rules.append((ln, []))
        elif rules:
            rules[-1][1].append(ln)
    return rules


def headers_rule_count(text):
    """The number of rules in a _headers text — Cloudflare rejects the deploy past HEADERS_MAX_RULES."""
    return len(parse_headers(text))


@lru_cache(maxsize=4096)
def _splat_re(pattern):
    return re.compile(".*".join(re.escape(x) for x in pattern.split("*")), re.S)


def _match(pattern, path):
    """Cloudflare's splat: * = any run of characters (slashes included)."""
    return _splat_re(pattern).fullmatch(path) is not None


def _cover_fn(text, header=NOSTORE):
    """text → a function path → True when a rule of the _headers text that sets `header` matches the path."""
    pats = [p for p, hdrs in parse_headers(text) if p.startswith("/") and header in hdrs]
    return lambda path: any(_match(p, path) for p in pats)


def headers_cover(text, name, header=NOSTORE):
    """True when a rule of the _headers `text` that sets `header` matches "/name" (Cloudflare's splat: * = any run of
    characters). Lets a check say "this file is never cached" without caring whether its rule is exact or a splat."""
    return _cover_fn(text, header)("/" + name.lstrip("/"))


# ── _headers: collapse into the fewest rules that still cover every data file ───────────────────────────────────────

def _group(files, never, min_cover=2):
    """Greedy cover of `files` by prefix splats ("/uninstall_c_*"): a splat may match NO path of `never` (the site's
    other files, /index.html first). Each round takes the splat covering the most still-open files (a tie: the shorter
    prefix, which also covers a file the next build adds) while it covers at least `min_cover`. → (splat patterns, files left for exact rules)."""
    files = sorted(set(files))
    never = sorted(set(never))
    top = chr(0x10FFFF)
    cands = {}
    for f in files:
        for i, ch in enumerate(f):
            if i >= 1 and i + 1 < len(f) and ch in "/_-.":
                pre = f[:i + 1]
                if pre not in cands:
                    lo, hi = bisect_left(files, pre), bisect_left(files, pre + top)
                    if bisect_left(never, pre) == bisect_left(never, pre + top):        # matches no never-file
                        cands[pre] = (lo, hi)
    alive = [True] * len(files)
    out = []
    while cands:
        ps = [0]
        for a in alive:
            ps.append(ps[-1] + (1 if a else 0))
        best = max(cands, key=lambda p: (ps[cands[p][1]] - ps[cands[p][0]], -len(p)))
        lo, hi = cands.pop(best)
        if ps[hi] - ps[lo] < min_cover:
            break
        out.append(best + "*")
        for j in range(lo, hi):
            alive[j] = False
    return out, [f for f, a in zip(files, alive) if a]


def _suffix(path):
    m = re.search(r"(\.[A-Za-z0-9]+(?:\.gz)?)$", path.rsplit("/", 1)[-1])
    return m.group(1) if m else ""


def _emit(keep, nostore):
    """The _headers text: the kept rules (/index.html's last), the no-store rules between, one blank line apart."""
    head = [(p, h) for p, h in keep if p != "/index.html"]
    tail = [(p, h) for p, h in keep if p == "/index.html"]
    blocks = head + [(p, [NOSTORE]) for p in sorted(set(nostore))] + tail
    return "\n\n".join(p + "".join("\n  " + h for h in hs) for p, hs in blocks) + "\n"


def collapse_headers(text, files, max_rules=HEADERS_MAX_RULES):
    """Rewrite a _headers `text` into at most `max_rules` rules without uncovering any data file.

    Kept as they are: every rule that is not a plain no-store rule (the `/*` noindex / referrer / frame rule, the
    `/index.html` no-cache rule, anything else). Every plain no-store rule is replaced: the fewest splat rules that
    cover everything the old rules covered (the exact paths, and every site file in `files` that an old splat matched),
    and that match no other site file; then, as a last resort, one `/*.<ext>` rule per file type (`/*.json.gz`,
    `/*.json`). `files` = the site's relative paths. → (new text, info) with info = {"stage", "before", "after",
    "uncovered" (previously covered files the new text does NOT cover — 0 unless even the last resort could not fit),
    "over_covered" (other site files that now are no-store too)}, or (None, info) when the kept rules alone are over
    the cap (nothing can be done to the text)."""
    rules = parse_headers(text)
    keep = [(p, h) for p, h in rules if not (h == [NOSTORE] and p.startswith("/"))]
    ns = list(dict.fromkeys(p for p, h in rules if h == [NOSTORE] and p.startswith("/")))
    site = ["/" + f.lstrip("/") for f in files]
    exact = [p for p in ns if "*" not in p]
    splats = [p for p in ns if "*" in p]
    covered = set(exact) | {u for u in site if any(_match(p, u) for p in splats)}
    covered.discard("/index.html")                         # the page is no-cache, never no-store
    never = (set(site) - covered) | {"/index.html"}
    info = {"before": len(rules), "after": len(rules), "uncovered": 0, "over_covered": 0, "stage": 0}
    budget = max_rules - len(keep)
    if budget < 0:
        return None, info

    def plan(stage, nostore):
        new = _emit(keep, nostore)
        cover = _cover_fn(new)
        info.update(stage=stage, after=headers_rule_count(new),
                    uncovered=sum(1 for p in covered if not cover(p)),
                    over_covered=sum(1 for u in site if u in never and cover(u)))
        return new

    # 1 - keep the old (valid) splat rules, group only the covered files they do not already match
    good = [p for p in splats if p.count("*") == 1 and len(p) <= HEADERS_MAX_LINE]
    left = [p for p in sorted(covered) if not any(_match(g, p) for g in good)]
    grp, rest = _group(left, never)
    new = plan(1, good + grp + rest)
    if info["after"] <= max_rules and not info["uncovered"]:
        return new, info
    # 2 - start over from the covered files alone
    grp, rest = _group(covered, never)
    new = plan(2, grp + rest)
    if info["after"] <= max_rules and not info["uncovered"]:
        return new, info
    # 3 - last resort: one splat per file type; a file without a type keeps an exact rule
    pats, rest = [], []
    for f in sorted(covered):
        suf = _suffix(f)
        pat = "/*" + suf
        if suf and not _match(pat, "/index.html"):
            if pat not in pats:
                pats.append(pat)
        else:
            rest.append(f)
    return plan(3, (pats + rest)[:budget]), info          # a file that still cannot fit is counted in "uncovered"


# ── the checks on the finished site folder ──────────────────────────────────────────────────────────────────────────

def bad_asset_path(rel):
    """Why a deploy would reject this site-relative path, or None. Cloudflare documents no path rule for Workers static
    assets; the upload API does insist on a URI-encodable manifest path, so a name with a URL delimiter or a broken
    % escape cannot ship, and a control character or a path far past any URL limit cannot either."""
    path = "/" + rel.replace(os.sep, "/")
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return "characters"
    if len(path) > MAX_PATH_CHARS:
        return "length"
    if any(len(seg.encode("utf-8")) > MAX_NAME_BYTES for seg in path.split("/")):
        return "length"
    if re.search(r"[\x00-\x1f\x7f\\?#]", path) or re.search(r"%(?![0-9A-Fa-f]{2})", path):
        return "characters"
    return None


def _inventory(out_dir):
    """[(relative posix path, size in bytes)] of every file Cloudflare would upload (not _headers / _redirects)."""
    out = []
    for root, _dirs, names in os.walk(out_dir):
        for n in names:
            full = os.path.join(root, n)
            rel = os.path.relpath(full, out_dir).replace(os.sep, "/")
            if rel in _META:
                continue
            try:
                out.append((rel, os.stat(full).st_size))
            except OSError:
                continue                                    # a broken link: nothing to upload
    return out


def _check_files(out_dir, prev_dir, rep, fixed, unfixed):
    """Asset paths and sizes: a file a deploy would reject never ships. Then the file count (reported, never deleted)."""
    bad, over = [], []
    for rel, size in _inventory(out_dir):
        full = os.path.join(out_dir, rel)
        why = bad_asset_path(rel)
        if why:
            os.remove(full)
            bad.append({"file": rel, "reason": why, "action": "left_out"})
        elif size > MAX_FILE_BYTES:
            prev = os.path.join(prev_dir, rel) if prev_dir else None
            if prev and os.path.isfile(prev) and os.path.getsize(prev) <= MAX_FILE_BYTES:
                if os.path.islink(full):
                    os.remove(full)                           # never write through a link
                shutil.copyfile(prev, full)
                action = "kept_previous_copy"
            elif rel in CORE_FILES:
                action = "core_shipped_as_is"                 # the page cannot open without it: the deploy is rejected,
            else:                                             # Cloudflare keeps the old site live
                os.remove(full)
                action = "left_out"
            over.append({"file": rel, "mib": round(size / 1048576, 2), "action": action})
    inv = _inventory(out_dir)
    rep["files"] = {"count": len(inv), "max": MAX_FILES, "over_limit": len(inv) > MAX_FILES,
                    "largest_mib": round(max([s for _r, s in inv] or [0]) / 1048576, 2)}
    n = {a: sum(1 for o in over if o["action"] == a) for a in ("kept_previous_copy", "left_out", "core_shipped_as_is")}
    rep["oversize"] = {"max_mib": MAX_FILE_BYTES // 1048576, "count": len(over), "kept_previous": n["kept_previous_copy"],
                       "left_out": n["left_out"], "core_shipped": n["core_shipped_as_is"],
                       "files": over[:_MAX_LISTED], "needs_split": [o["file"] for o in over][:_MAX_LISTED]}
    rep["bad_paths"] = {"count": len(bad), "files": bad[:_MAX_LISTED]}
    if n["kept_previous_copy"]:
        fixed.append(f"{n['kept_previous_copy']} oversize file{'s' if n['kept_previous_copy'] != 1 else ''} at the previous copy")
    if n["left_out"]:
        fixed.append(f"{n['left_out']} oversize file{'s' if n['left_out'] != 1 else ''} left out")
    if n["core_shipped_as_is"]:
        unfixed.append(f"core files over {MAX_FILE_BYTES // 1048576} MiB with no previous copy: {n['core_shipped_as_is']} "
                       f"(shipped as is, the deploy will be rejected)")
    if bad:
        fixed.append(f"{len(bad)} bad asset name{'s' if len(bad) != 1 else ''} left out")
    return [rel for rel, _s in inv]


def _check_headers(out_dir, files, rep, fixed, unfixed):
    path = os.path.join(out_dir, "_headers")
    h = rep["headers"] = {"present": os.path.isfile(path), "max": HEADERS_MAX_RULES, "rules_before": 0,
                          "rules_after": 0, "rewritten": False, "uncovered": 0, "long_lines": 0, "multi_splat": 0}
    if not h["present"]:
        return
    with open(path, encoding="utf-8") as f:
        text = f.read()
    rules = parse_headers(text)
    h["rules_before"] = h["rules_after"] = len(rules)

    def invalid(p, hdrs):
        return p.count("*") > 1 or len(p) > HEADERS_MAX_LINE or any(len(x) > HEADERS_MAX_LINE for x in hdrs)

    if len(rules) > HEADERS_MAX_RULES or any(invalid(p, hd) for p, hd in rules if hd == [NOSTORE]):
        new, info = collapse_headers(text, files)
        if new is not None and (info["after"] < len(rules) or info["after"] <= HEADERS_MAX_RULES):
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            h.update(rewritten=True, rules_after=info["after"], uncovered=info["uncovered"],
                     over_covered=info["over_covered"], stage=info["stage"])
            text, rules = new, parse_headers(new)
            fixed.append(f"headers collapsed {info['before']}->{info['after']} rules")
    h["long_lines"] = sum(1 for p, hd in rules if len(p) > HEADERS_MAX_LINE or any(len(x) > HEADERS_MAX_LINE for x in hd))
    h["multi_splat"] = sum(1 for p, _hd in rules if p.count("*") > 1)
    if h["rules_after"] > HEADERS_MAX_RULES:
        unfixed.append(f"headers rules {h['rules_after']}>{HEADERS_MAX_RULES}")
    if h["uncovered"]:
        unfixed.append(f"headers {h['uncovered']} data files lost no-store")
    if h["long_lines"]:
        unfixed.append(f"headers {h['long_lines']} lines over {HEADERS_MAX_LINE} characters")
    if h["multi_splat"]:
        unfixed.append(f"headers {h['multi_splat']} rules with more than one splat")


def _check_redirects(out_dir, rep, unfixed):
    """Counted the way Cloudflare's parser does (wrangler parseRedirects): a rule needs 2 or 3 tokens; it is static until
    the FIRST dynamic one (a splat * or a :placeholder in its source), and every rule after that counts as dynamic."""
    path = os.path.join(out_dir, "_redirects")
    r = rep["redirects"] = {"present": os.path.isfile(path), "static": 0, "dynamic": 0, "long_lines": 0}
    if not r["present"]:
        return
    can_static = True
    with open(path, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            if len(ln) > REDIRECTS_MAX_LINE:
                r["long_lines"] += 1
            tokens = re.sub(r"\s+#.*$", "", ln).split()
            if not 2 <= len(tokens) <= 3:
                continue                                    # Cloudflare ignores a line like that
            if can_static and "*" not in tokens[0] and not re.search(r":[A-Za-z]", tokens[0]):
                r["static"] += 1
            else:
                r["dynamic"] += 1
                can_static = False
    if r["static"] > REDIRECTS_MAX_STATIC:
        unfixed.append(f"redirects static {r['static']}>{REDIRECTS_MAX_STATIC}")
    if r["dynamic"] > REDIRECTS_MAX_DYNAMIC:
        unfixed.append(f"redirects dynamic {r['dynamic']}>{REDIRECTS_MAX_DYNAMIC}")
    if r["long_lines"]:
        unfixed.append(f"redirects {r['long_lines']} rules over {REDIRECTS_MAX_LINE} characters")


def summary_line(rep):
    """The ONE log line — counts only (the log is private, but nothing in it names an app or an amount)."""
    parts = []
    h, r, f = rep.get("headers") or {}, rep.get("redirects") or {}, rep.get("files") or {}
    if h:
        parts.append(f"rules {h.get('rules_after', 0)}/{HEADERS_MAX_RULES}")
    if r.get("present"):
        parts.append(f"redirects {r['static']}/{REDIRECTS_MAX_STATIC}+{r['dynamic']}/{REDIRECTS_MAX_DYNAMIC}")
    if f:
        parts.append(f"files {f['count']}/{MAX_FILES}")
        parts.append(f"largest {f['largest_mib']} MiB")
    parts.append("fixed: " + (", ".join(rep.get("fixed") or []) or "none"))
    if (rep.get("oversize") or {}).get("count"):
        parts.append(f"{rep['oversize']['count']} file(s) over {rep['oversize']['max_mib']} MiB need a split")
    if rep.get("unfixed"):
        parts.append("NOT FIXED: " + ", ".join(rep["unfixed"]))
    return "deploy guard: " + ", ".join(parts)


def run(out_dir, prev_dir=None, report_path=None, log=True):
    """Check (and, where it is safe, fix) the finished site folder `out_dir`; write `deploy_guard.json` next to it
    (`report_path` overrides) and print the one counts-only line. `prev_dir` = the copy of the site the build started
    from (the previous good copies). Never raises: a check that fails records its error type and the rest still run.
    → the report dict."""
    out_dir = os.path.abspath(out_dir)
    rep = {"checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "ok": True,
           "fixed": [], "unfixed": [], "limits": {"headers_rules": HEADERS_MAX_RULES, "files": MAX_FILES,
                                                  "file_mib": MAX_FILE_BYTES // 1048576}}
    fixed, unfixed = rep["fixed"], rep["unfixed"]
    files = []
    try:
        files = _check_files(out_dir, prev_dir, rep, fixed, unfixed)
    except Exception as e:                                    # the guard must never break a build
        unfixed.append(f"files check failed ({type(e).__name__})")
    for name, check in (("headers", lambda: _check_headers(out_dir, files, rep, fixed, unfixed)),
                        ("redirects", lambda: _check_redirects(out_dir, rep, unfixed))):
        try:
            check()
        except Exception as e:
            unfixed.append(f"{name} check failed ({type(e).__name__})")
    if (rep.get("files") or {}).get("over_limit"):
        unfixed.append(f"files {rep['files']['count']}>{MAX_FILES}")
    rep["ok"] = not unfixed
    line = summary_line(rep)
    rep["summary"] = line
    path = report_path or os.path.join(os.path.dirname(out_dir), REPORT_NAME)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1, sort_keys=True)
    except OSError as e:
        print(f"deploy guard: report not written ({type(e).__name__})", file=sys.stderr)
    if log:
        print(line, file=sys.stderr)
    return rep


# ── the previous good copy ──────────────────────────────────────────────────────────────────────────────────────────

def snapshot(out_dir):
    """Copy the site the build STARTS from (the live site: the workflow pulls it from the private repo into site/) to a
    hidden folder next to it, so an oversize file can fall back to its previous good copy after the build overwrote
    it. → the folder, or None (no site yet, or no room to copy). Replaces a leftover of an earlier run that died."""
    out_dir = os.path.abspath(out_dir)
    prev = os.path.join(os.path.dirname(out_dir), PREV_DIRNAME)
    shutil.rmtree(prev, ignore_errors=True)
    if not os.path.isdir(out_dir):
        return None
    try:
        shutil.copytree(out_dir, prev, copy_function=shutil.copyfile, symlinks=True)
        return prev
    except (OSError, shutil.Error):
        shutil.rmtree(prev, ignore_errors=True)
        return None


def discard(prev_dir):
    if prev_dir:
        shutil.rmtree(prev_dir, ignore_errors=True)


# ── the workflow's side: counts-only GitHub Actions annotations ─────────────────────────────────────────────────────

def annotations(rep):
    """A report → the GitHub Actions lines for the workflow log. The log of a public repo is world-readable, so these
    carry COUNTS only: no file name, no app, no amount."""
    out = []
    for u in rep.get("unfixed") or []:
        if u.startswith("core files over"):
            continue                                          # its own, plainer line below
        out.append(f"::warning::deploy guard could not fix: {u}. Cloudflare may reject the deploy; the data is still pushed.")
    ov = (rep.get("oversize") or {})
    if ov.get("core_shipped"):
        out.append(f"::warning::deploy guard: {ov['core_shipped']} core file(s) over {ov.get('max_mib', 25)} MiB with no good "
                   f"previous copy were shipped as they are: Cloudflare WILL reject this deploy and keep the old site live "
                   f"until that file is split. Nothing was trimmed; the data is still pushed.")
    if ov.get("count") and ov["count"] > ov.get("core_shipped", 0):
        out.append(f"::warning::deploy guard: {ov['count'] - ov.get('core_shipped', 0)} file(s) over {ov.get('max_mib', 25)} MiB "
                   f"({ov.get('kept_previous', 0)} kept at the previous copy, {ov.get('left_out', 0)} left out): that feature "
                   f"needs a split. Nothing was trimmed.")
    bp = (rep.get("bad_paths") or {})
    if bp.get("count"):
        out.append(f"::warning::deploy guard: {bp['count']} file name(s) a deploy would reject were left out.")
    hd = (rep.get("headers") or {})
    if hd.get("rewritten"):
        out.append(f"::notice::deploy guard collapsed _headers {hd['rules_before']}->{hd['rules_after']} rules "
                   f"(the limit is {HEADERS_MAX_RULES}); a feature is adding one rule per file.")
    return out


def annotate(path=REPORT_NAME):
    """Print the annotations of the report at `path`; a missing or unreadable report is itself a warning. Always 0."""
    try:
        with open(path, encoding="utf-8") as f:
            rep = json.load(f)
        lines = annotations(rep) or ["deploy guard: ok"]
    except Exception:
        lines = ["::warning::deploy guard: no readable report (the guard did not run); the data is still pushed."]
    for ln in lines:
        print(ln)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "annotate":
        return annotate(argv[1] if len(argv) > 1 else REPORT_NAME)
    if argv and argv[0] == "run" and len(argv) > 1:          # by hand, on a COPY of a site: it fixes what it finds
        return 0 if run(argv[1])["ok"] else 1
    print("usage: python -m admob_iq.deploy_guard annotate [deploy_guard.json] | run <site dir>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
