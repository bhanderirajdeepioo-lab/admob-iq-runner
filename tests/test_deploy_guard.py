"""Cloudflare deploy guard (admob_iq/deploy_guard.py): whatever the robot produces, Cloudflare must never reject a deploy.

On 2 Oct `site/_headers` grew past Cloudflare's 100-rule cap and every deploy was rejected for 9 hours while the robot
kept succeeding. These tests use SYNTHETIC sites only (made-up file names and sizes) and check, on the finished site:
  * _headers: any number of per-file rules collapses to <= 100, every previously covered file still no-store, the `/*`
    and `/index.html` rules intact, nothing else newly cached; a normal site is left byte-identical;
  * an oversize file never ships (previous copy, else left out) and is never trimmed; the file count is reported and
    nothing is deleted for it; bad asset names are left out; _redirects limits are checked;
  * one counts-only log line, deploy_guard.json NEXT to the site, counts-only workflow annotations;
  * build() runs it last, failure-isolated, and the workflow still pushes after a warning."""

import hashlib
import json
import os
import random
import re
import shutil
from datetime import date

import pytest
import yaml

from admob_iq import build_static, deploy_guard as dg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _put(root, name, data=b"x"):
    p = os.path.join(root, *name.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return p


def _site(tmp_path, names, headers=None):
    site = str(tmp_path / "site")
    os.makedirs(site, exist_ok=True)
    for n in names:
        _put(site, n)
    if headers is not None:
        with open(os.path.join(site, "_headers"), "w", encoding="utf-8") as f:
            f.write(headers)
    return site


def _tree(root):
    """{relative path: bytes} of a folder."""
    out = {}
    for r, _d, fs in os.walk(root):
        for n in fs:
            p = os.path.join(r, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = f.read()
    return out


def _keys(n, base=0xb0b000000000):
    return ["%012x" % (base + i) for i in range(n)]


def _app_files(keys):
    return (["uninstall.json.gz", "active_portfolio.json.gz"]
            + ["uninstall_c_%s.json.gz" % k for k in keys]
            + ["active_%s.json.gz" % k for k in keys]
            + ["value_%s.json.gz" % k for k in keys])


def _dash(keys):
    return {"active": {"apps": [{"file": "active_%s.json.gz" % k} for k in keys],
                       "portfolio": {"file": "active_portfolio.json.gz"}},
            "value": {"apps": [{"file": "value_%s.json.gz" % k} for k in keys]}}


FIXED_NAMES = ["dashboard.json.gz", "baseline.json", "baseline_geo.json.gz", "adunit_country_daily.json.gz",
               "baseline_daily.json.gz", "baseline_daily_old.json.gz", "selected_apps.json", "account_names.json",
               "app_names.json", "index.html", "robots.txt", "icon-192.png", "manifest.webmanifest"]
NEVER_NOSTORE = ("index.html", "robots.txt", "icon-192.png", "manifest.webmanifest")


def _normal_headers(keys, extra=()):
    return build_static.headers_text(["uninstall.json.gz"] + ["uninstall_c_%s.json.gz" % k for k in keys], _dash(keys),
                                     extra=list(extra))


def _rule_block(text, pattern):
    return [b for b in text.split("\n\n") if b.strip().startswith(pattern + "\n") or b.strip() == pattern]


# ── _headers ────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_500_apps_keep_headers_under_the_cap_and_the_guard_leaves_them_byte_identical(tmp_path):
    keys = _keys(500)
    text = _normal_headers(keys, extra=["/review/*", "/impact_any_*"])
    names = FIXED_NAMES + _app_files(keys) + ["review/2026-10-01.json", "impact_any_abc.json.gz"]
    site = _site(tmp_path, names, text)
    before = _tree(site)
    rep = dg.run(site)
    assert dg.headers_rule_count(text) <= 40                                    # the splat rules: not one per app
    assert open(os.path.join(site, "_headers"), encoding="utf-8").read() == text
    assert _tree(site) == before                                                # nothing at all was touched
    assert rep["ok"] and rep["fixed"] == [] and rep["headers"]["rewritten"] is False
    assert rep["files"]["count"] == len(names)


def test_a_new_per_app_feature_cannot_push_headers_past_the_cap(tmp_path):
    """The 2 Oct failure, in general: a feature whose per-app files each get their OWN rule (not one of the known
    splat rules) — 500 apps — would be 500+ rules. The guard collapses them; every file stays no-store."""
    keys = _keys(500)
    new = ["newtab_%s.json.gz" % k for k in keys]
    text = _normal_headers(keys, extra=["/" + n for n in new] + ["/review/*"])
    assert dg.headers_rule_count(text) > 500
    names = FIXED_NAMES + _app_files(keys) + new + ["review/2026-10-01.json"]
    site = _site(tmp_path, names, text)
    rep = dg.run(site)
    out = open(os.path.join(site, "_headers"), encoding="utf-8").read()
    assert dg.headers_rule_count(out) <= dg.HEADERS_MAX_RULES and dg.headers_rule_count(out) <= 40
    assert rep["headers"]["rewritten"] and rep["headers"]["rules_before"] > 500
    assert rep["headers"]["rules_after"] == dg.headers_rule_count(out) and rep["ok"]
    for n in names:
        if n not in NEVER_NOSTORE:
            assert build_static.headers_cover(out, n), n                        # every data file: still never cached
    for n in NEVER_NOSTORE:
        assert not build_static.headers_cover(out, n), n                        # nothing else became no-store
    assert build_static.headers_cover(out, "index.html", "Cache-Control: no-cache")
    assert rep["fixed"] and rep["fixed"][0].startswith("headers collapsed")


def test_150_exact_rules_collapse_keep_the_global_and_index_rules_and_cover_every_file(tmp_path):
    names = (FIXED_NAMES + ["feat_%03d.json.gz" % i for i in range(60)] + ["other-%03d.json" % i for i in range(60)]
             + ["review/2026-10-%02d.json" % i for i in range(1, 25)])
    data = [n for n in names if n not in NEVER_NOSTORE]
    glob = ("/*\n  X-Robots-Tag: noindex, nofollow, noarchive, nosnippet\n  Referrer-Policy: no-referrer\n"
            "  X-Frame-Options: DENY\n  Content-Security-Policy: frame-ancestors 'none'\n\n")
    text = glob + "".join("/%s\n  Cache-Control: no-store\n\n" % n for n in data) + "/index.html\n  Cache-Control: no-cache\n"
    assert dg.headers_rule_count(text) >= 150
    site = _site(tmp_path, names, text)
    rep = dg.run(site)
    out = open(os.path.join(site, "_headers"), encoding="utf-8").read()
    assert out.startswith(glob) and out.endswith("/index.html\n  Cache-Control: no-cache\n")     # kept, byte for byte
    assert dg.headers_rule_count(out) <= 14
    for n in data:
        assert build_static.headers_cover(out, n), n
    for n in NEVER_NOSTORE:
        assert not build_static.headers_cover(out, n), n
    assert rep["headers"]["uncovered"] == 0 and rep["ok"]
    assert out.count("Cache-Control: no-store") == dg.headers_rule_count(out) - 2


def test_last_resort_is_one_splat_per_file_type(tmp_path):
    """Names with nothing in common (no shared prefix): /*.json.gz and /*.json — and still no other file is cached."""
    data = (["%s.json.gz" % hashlib.md5(b"g%d" % i).hexdigest() for i in range(80)]
            + ["%s.json" % hashlib.md5(b"j%d" % i).hexdigest() for i in range(80)])
    names = data + ["index.html", "robots.txt", "icon-192.png"]
    text = ("/*\n  X-Robots-Tag: noindex\n\n" + "".join("/%s\n  Cache-Control: no-store\n\n" % n for n in data)
            + "/index.html\n  Cache-Control: no-cache\n")
    site = _site(tmp_path, names, text)
    rep = dg.run(site)
    out = open(os.path.join(site, "_headers"), encoding="utf-8").read()
    assert rep["headers"]["stage"] == 3
    assert "/*.json.gz\n  Cache-Control: no-store" in out and "/*.json\n  Cache-Control: no-store" in out
    assert dg.headers_rule_count(out) == 4                                      # /*, the two splats, /index.html
    assert all(build_static.headers_cover(out, n) for n in data)
    assert not any(build_static.headers_cover(out, n) for n in ("index.html", "robots.txt", "icon-192.png"))


def test_old_splat_rules_and_exact_rules_both_stay_covered_after_a_collapse(tmp_path):
    keys = _keys(40)
    names = (["uninstall_c_%s.json.gz" % k for k in keys] + ["feat_%03d.json.gz" % i for i in range(120)]
             + ["icon-192.png", "index.html"])
    text = ("/*\n  X-Robots-Tag: noindex\n\n/uninstall_c_*\n  Cache-Control: no-store\n\n"
            + "".join("/feat_%03d.json.gz\n  Cache-Control: no-store\n\n" % i for i in range(120))
            + "/index.html\n  Cache-Control: no-cache\n")
    site = _site(tmp_path, names, text)
    dg.run(site)
    out = open(os.path.join(site, "_headers"), encoding="utf-8").read()
    assert "/uninstall_c_*\n  Cache-Control: no-store" in out                    # a valid splat is kept as it was
    assert "/feat_*\n  Cache-Control: no-store" in out and dg.headers_rule_count(out) == 4
    assert all(build_static.headers_cover(out, n) for n in names if n not in ("icon-192.png", "index.html"))


def test_a_rule_with_two_splats_is_rewritten_into_valid_ones(tmp_path):
    """Cloudflare allows a single splat per rule; a no-store rule with two is rewritten, the files it matched stay covered."""
    names = ["a_1_b.json", "a_2_b.json", "a_3_b.json", "a_x_c.json", "index.html", "icon-192.png"]
    text = ("/*\n  X-Robots-Tag: noindex\n\n/a_*_b*\n  Cache-Control: no-store\n\n/index.html\n  Cache-Control: no-cache\n")
    site = _site(tmp_path, names, text)
    rep = dg.run(site)
    out = open(os.path.join(site, "_headers"), encoding="utf-8").read()
    assert all(p.count("*") <= 1 for p, _h in dg.parse_headers(out)) and rep["ok"] and rep["headers"]["rewritten"]
    assert all(build_static.headers_cover(out, n) for n in ("a_1_b.json", "a_2_b.json", "a_3_b.json"))
    assert not build_static.headers_cover(out, "icon-192.png")


def test_130_splat_rules_collapse_too_and_a_second_run_changes_nothing(tmp_path):
    names = ["fam%03d_%d.json" % (i, j) for i in range(130) for j in (1, 2)] + ["index.html", "icon-192.png"]
    text = ("/*\n  X-Robots-Tag: noindex\n\n" + "".join("/fam%03d_*\n  Cache-Control: no-store\n\n" % i for i in range(130))
            + "/index.html\n  Cache-Control: no-cache\n")
    site = _site(tmp_path, names, text)
    rep = dg.run(site)
    out = open(os.path.join(site, "_headers"), encoding="utf-8").read()
    assert rep["ok"] and rep["headers"]["rewritten"] and dg.headers_rule_count(out) <= 4
    assert all(build_static.headers_cover(out, n) for n in names if n.startswith("fam"))
    assert not any(build_static.headers_cover(out, n) for n in ("index.html", "icon-192.png"))
    rep2 = dg.run(site)
    assert open(os.path.join(site, "_headers"), encoding="utf-8").read() == out and not rep2["headers"]["rewritten"]


def test_headers_the_guard_cannot_shrink_are_reported_and_left_alone(tmp_path):
    """Rules that are not plain no-store rules are not the guard's to merge: 120 of them stay as they are, loudly."""
    text = "".join("/p%03d\n  X-Custom: v%d\n\n" % (i, i) for i in range(120))
    site = _site(tmp_path, ["index.html"], text)
    rep = dg.run(site)
    assert open(os.path.join(site, "_headers"), encoding="utf-8").read() == text
    assert not rep["ok"] and any(u.startswith("headers rules 120>100") for u in rep["unfixed"])


def test_collapse_never_uncovers_a_file_whatever_the_names(tmp_path):
    """Random synthetic sites: families of prefixed files, odd one-offs, directories, 101-400 exact rules."""
    rnd = random.Random(20261002)
    for trial in range(25):
        fams = ["fam%d_" % i for i in range(rnd.randint(1, 8))] + ["dir%d/" % i for i in range(rnd.randint(0, 3))] + [""]
        data = sorted({rnd.choice(fams) + "".join(rnd.choice("abcdef0123456789-_.") for _ in range(rnd.randint(3, 14)))
                       + rnd.choice([".json"] * 4 + [".json.gz"] * 4 + [".csv", ""]) for _ in range(rnd.randint(101, 400))})
        data = [d for d in data if not d.endswith(("/", ".", "_")) and "//" not in d and d != "index.html"]
        others = ["index.html", "robots.txt", "icon-192.png", "dirx/readme.txt", "fam0_logo.png"]
        text = ("/*\n  X-Robots-Tag: noindex\n\n" + "".join("/%s\n  Cache-Control: no-store\n\n" % n for n in data)
                + "/index.html\n  Cache-Control: no-cache\n")
        new, info = dg.collapse_headers(text, data + others)
        assert new is not None and info["after"] <= dg.HEADERS_MAX_RULES, (trial, info)
        assert info["uncovered"] == 0, (trial, info)
        for n in data:
            assert build_static.headers_cover(new, n), (trial, n)
        assert not build_static.headers_cover(new, "index.html")
        assert new.startswith("/*\n  X-Robots-Tag: noindex\n\n") and new.endswith("/index.html\n  Cache-Control: no-cache\n")


def test_headers_primitives_read_cloudflares_format():
    text = ("# a comment\n/*\n  X-Robots-Tag: noindex\n\n\n/a.json\n  Cache-Control: no-store\n"
            "/b_*\n  Cache-Control: no-store\n  X-Other: 1\n")
    assert dg.headers_rule_count(text) == 3                                    # blank lines mean nothing, comments too
    assert dg.headers_cover(text, "a.json") and dg.headers_cover(text, "/b_x/y.gz") and not dg.headers_cover(text, "c.json")
    assert dg.headers_cover(text, "anything", "X-Robots-Tag: noindex")
    assert build_static.headers_cover is dg.headers_cover and build_static.HEADERS_MAX_RULES == 100


# ── file size, count, names ─────────────────────────────────────────────────────────────────────────────────────────

def test_a_30_mib_file_keeps_the_previous_copy_and_is_reported(tmp_path, capsys):
    site = _site(tmp_path, ["a.json", "b.json.gz"])
    prev = str(tmp_path / "prev")
    _put(prev, "big.json.gz", b"previous good copy")
    _put(prev, "a.json", b"older a")
    _put(site, "big.json.gz", b"\0" * (30 << 20))
    others = {k: v for k, v in _tree(site).items() if k != "big.json.gz"}
    rep = dg.run(site, prev_dir=prev)
    assert open(os.path.join(site, "big.json.gz"), "rb").read() == b"previous good copy"
    assert {k: v for k, v in _tree(site).items() if k != "big.json.gz"} == others          # nothing else touched
    ov = rep["oversize"]
    assert ov["count"] == 1 and ov["kept_previous"] == 1 and ov["needs_split"] == ["big.json.gz"]
    assert ov["files"][0] == {"file": "big.json.gz", "mib": 30.0, "action": "kept_previous_copy"}
    assert rep["files"]["largest_mib"] < 1 and rep["ok"]
    err = capsys.readouterr().err
    assert re.search(r"1 oversize file at the previous copy", err) and "1 file(s) over 25 MiB need a split" in err
    assert "big.json.gz" not in err                                                         # the log never names a file
    ann = "\n".join(dg.annotations(rep))
    assert "::warning::" in ann and "needs a split" in ann and "Nothing was trimmed" in ann and "big.json" not in ann


def test_an_oversize_file_with_no_good_previous_copy_is_left_out(tmp_path):
    site = _site(tmp_path, ["keep.json"])
    _put(site, "new_big.json.gz", b"\0" * (26 << 20))
    _put(site, "old_big.json.gz", b"\0" * (26 << 20))
    prev = str(tmp_path / "prev")
    _put(prev, "old_big.json.gz", b"\0" * (27 << 20))                  # the previous copy was over the cap too
    rep = dg.run(site, prev_dir=prev)
    assert sorted(os.listdir(site)) == ["keep.json"]
    assert [o["action"] for o in sorted(rep["oversize"]["files"], key=lambda o: o["file"])] == ["left_out", "left_out"]
    assert rep["oversize"]["kept_previous"] == 0 and "2 oversize files left out" in rep["fixed"]
    assert rep["ok"]                                                  # handled; the warning still tells the owner


def test_exactly_25_mib_ships_one_byte_more_does_not(tmp_path):
    site = _site(tmp_path, [])
    _put(site, "edge.json.gz", b"\0" * dg.MAX_FILE_BYTES)
    _put(site, "over.json.gz", b"\0" * (dg.MAX_FILE_BYTES + 1))
    rep = dg.run(site)
    assert sorted(os.listdir(site)) == ["edge.json.gz"] and rep["oversize"]["count"] == 1


def test_oversize_file_under_a_folder_is_found(tmp_path):
    site = _site(tmp_path, ["x.json"])
    _put(site, "review/2026-10-01.json", b"\0" * (26 << 20))
    prev = str(tmp_path / "prev")
    _put(prev, "review/2026-10-01.json", b"{}")
    rep = dg.run(site, prev_dir=prev)
    assert open(os.path.join(site, "review", "2026-10-01.json"), "rb").read() == b"{}"
    assert rep["oversize"]["files"][0]["file"] == "review/2026-10-01.json"


def test_the_file_count_is_reported_and_nothing_is_deleted_for_it(tmp_path, monkeypatch, capsys):
    site = _site(tmp_path, ["f%02d.json" % i for i in range(15)], "/*\n  X-Robots-Tag: noindex\n")
    before = _tree(site)
    rep = dg.run(site)
    assert rep["files"]["count"] == 15 and rep["files"]["max"] == 20000 and rep["ok"]            # _headers is not an asset
    assert "files 15/20000" in capsys.readouterr().err
    monkeypatch.setattr(dg, "MAX_FILES", 10)
    rep = dg.run(site)
    assert rep["files"]["over_limit"] and not rep["ok"] and "files 15>10" in rep["unfixed"]
    assert _tree(site) == before                                                                 # never deleted
    assert any("files 15>10" in a and a.startswith("::warning::") for a in dg.annotations(rep))


def test_bad_asset_names_are_left_out_and_odd_but_legal_ones_stay(tmp_path):
    long_dir = "/".join(["d" * 200, "e" * 200, "f" * 200]) + "/x.json"                             # 600 characters
    bad = ["q?x.json", "h#x.json", "pct%zz.json", "back\\slash.json", "ctl\x01.json", long_dir]
    good = ["with space.json", "café.json", "100%25.json", "a+b=c,d.json", ".hidden.json", "sub/dir/ok.json"]
    site = _site(tmp_path, bad + good)
    rep = dg.run(site)
    import unicodedata
    left = sorted(unicodedata.normalize("NFC", os.path.relpath(os.path.join(r, n), site)) for r, _d, fs in os.walk(site) for n in fs)
    assert left == sorted(unicodedata.normalize("NFC", g) for g in good)
    assert rep["bad_paths"]["count"] == len(bad) and f"{len(bad)} bad asset names left out" in rep["fixed"]
    assert {b["reason"] for b in rep["bad_paths"]["files"]} == {"characters", "length"}
    assert dg.bad_asset_path("x/y.json.gz") is None and dg.bad_asset_path("a" * 600) == "length"


def test_redirects_limits(tmp_path):
    ok = "# comment\n\n" + "".join("/old%d /new%d 301\n" % (i, i) for i in range(2000)) \
        + "".join("/blog/:slug /posts/:slug 301\n" if i == 0 else "/g%d/* /h%d/:splat 302\n" % (i, i) for i in range(100))
    site = _site(tmp_path, ["a.json"])
    open(os.path.join(site, "_redirects"), "w").write(ok)
    rep = dg.run(site)
    assert (rep["redirects"]["static"], rep["redirects"]["dynamic"]) == (2000, 100) and rep["ok"]
    open(os.path.join(site, "_redirects"), "w").write(ok + "/one-more /x 301\n/another/* /y/:splat 301\n")
    rep = dg.run(site)
    assert not rep["ok"] and "redirects static 2001>2000" in rep["unfixed"] and "redirects dynamic 101>100" in rep["unfixed"]
    assert open(os.path.join(site, "_redirects")).read().endswith("/another/* /y/:splat 301\n")   # reported, never edited
    assert rep["files"]["count"] == 1                                                              # _redirects: not an asset


def test_no_redirects_file_no_redirects_part_in_the_line(tmp_path, capsys):
    site = _site(tmp_path, ["a.json"], "/*\n  X-Robots-Tag: noindex\n")
    rep = dg.run(site)
    assert rep["redirects"]["present"] is False
    assert re.fullmatch(r"deploy guard: rules 1/100, files 1/20000, largest 0.0 MiB, fixed: none\n", capsys.readouterr().err)


# ── the report and the workflow's annotations ───────────────────────────────────────────────────────────────────────

def test_report_is_written_next_to_the_site_not_inside_it(tmp_path):
    site = _site(tmp_path, ["a.json"], "/*\n  X-Robots-Tag: noindex\n")
    dg.run(site)
    assert os.path.exists(tmp_path / "deploy_guard.json") and not os.path.exists(os.path.join(site, "deploy_guard.json"))
    rep = json.load(open(tmp_path / "deploy_guard.json", encoding="utf-8"))
    assert rep["ok"] is True and rep["files"]["count"] == 1 and rep["summary"].startswith("deploy guard: rules 1/100")
    assert "deploy_guard.json" not in _tree(site)


def test_annotations_carry_counts_only_and_a_missing_report_is_itself_a_warning(tmp_path, capsys):
    rep = {"unfixed": ["files 25000>20000", "headers rules 140>100"], "fixed": [], "ok": False,
           "oversize": {"count": 2, "kept_previous": 1, "max_mib": 25,
                        "files": [{"file": "secret_app_name_ab12.json.gz", "mib": 31.5, "action": "left_out"}]},
           "bad_paths": {"count": 1, "files": [{"file": "name with AMOUNT_MARKER.json", "reason": "x", "action": "left_out"}]},
           "headers": {"rewritten": True, "rules_before": 150, "rules_after": 7}}
    lines = dg.annotations(rep)
    text = "\n".join(lines)
    assert all(ln.startswith(("::warning::", "::notice::")) for ln in lines) and len(lines) == 5
    assert "secret_app_name" not in text and "AMOUNT_MARKER" not in text and "31.5" not in text and "ab12" not in text
    assert "150->7" in text and "files 25000>20000" in text
    assert dg.annotations({"unfixed": [], "oversize": {"count": 0}, "bad_paths": {"count": 0}, "headers": {}}) == []
    p = tmp_path / "r.json"
    p.write_text(json.dumps(rep))
    assert dg.annotate(str(p)) == 0
    assert capsys.readouterr().out.count("::warning::") == 4
    assert dg.annotate(str(tmp_path / "missing.json")) == 0
    assert "::warning::deploy guard: no readable report" in capsys.readouterr().out
    p.write_text(json.dumps({"unfixed": [], "oversize": {"count": 0}, "bad_paths": {"count": 0}, "headers": {}}))
    dg.annotate(str(p))
    assert capsys.readouterr().out.strip() == "deploy guard: ok"


def test_a_check_that_crashes_is_recorded_and_never_raises(tmp_path, monkeypatch, capsys):
    site = _site(tmp_path, ["a.json"], "/*\n  X-Robots-Tag: noindex\n")
    monkeypatch.setattr(dg, "_check_redirects", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    rep = dg.run(site)
    assert not rep["ok"] and rep["unfixed"] == ["redirects check failed (RuntimeError)"]
    assert "boom" not in capsys.readouterr().err and rep["files"]["count"] == 1


def test_snapshot_keeps_the_live_site_beside_it_and_replaces_a_leftover(tmp_path):
    site = _site(tmp_path, ["a.json", "review/x.json"])
    os.makedirs(tmp_path / dg.PREV_DIRNAME)
    _put(str(tmp_path / dg.PREV_DIRNAME), "stale.json")
    prev = dg.snapshot(site)
    assert prev == str(tmp_path / dg.PREV_DIRNAME) and _tree(prev) == _tree(site)
    _put(site, "a.json", b"overwritten by the build")
    assert open(os.path.join(prev, "a.json"), "rb").read() == b"x"                # the copy is independent of the build
    dg.discard(prev)
    assert not os.path.exists(prev)
    assert dg.snapshot(str(tmp_path / "no_such_site")) is None


# ── build() wiring ──────────────────────────────────────────────────────────────────────────────────────────────────

def _mock_build(tmp_path, **kw):
    return build_static.build(out_dir=str(tmp_path / "site"), data_dir=str(tmp_path / "data"),
                              today=date(2026, 7, 23), mode="mock", **kw)


def test_build_runs_the_guard_last_and_leaves_a_normal_site_byte_identical(tmp_path, monkeypatch, capsys):
    seen = {}
    real = dg.run

    def spy(out_dir, prev_dir=None, **kw):
        seen["headers"] = open(os.path.join(out_dir, "_headers"), "rb").read()
        seen["tree"] = _tree(out_dir)
        seen["prev"] = prev_dir
        return real(out_dir, prev_dir=prev_dir, **kw)

    monkeypatch.setattr(dg, "run", spy)
    _mock_build(tmp_path)
    site = str(tmp_path / "site")
    assert open(os.path.join(site, "_headers"), "rb").read() == seen["headers"]      # byte-identical _headers
    assert _tree(site) == seen["tree"]                                                # and every other file
    assert os.path.exists(tmp_path / "deploy_guard.json") and not os.path.exists(os.path.join(site, "deploy_guard.json"))
    rep = json.load(open(tmp_path / "deploy_guard.json", encoding="utf-8"))
    assert rep["ok"] and rep["fixed"] == [] and rep["headers"]["rewritten"] is False
    assert rep["files"]["count"] == len([n for n in _tree(site) if n != "_headers"])
    assert re.search(r"^deploy guard: rules \d+/100, files \d+/20000, largest [\d.]+ MiB, fixed: none$",
                     capsys.readouterr().err, re.M)
    assert seen["prev"] is None or not os.path.exists(seen["prev"])                  # the copy of the live site is gone


def test_build_collapses_a_bloated_headers_text(tmp_path, monkeypatch):
    keys = _keys(150)
    real = build_static.headers_text

    def bloated(uni, dash, extra=()):
        return real(uni, dash, extra=list(extra) + ["/zz_%s.json.gz" % k for k in keys])

    monkeypatch.setattr(build_static, "headers_text", bloated)
    # the site must hold the files those rules name, as a real feature's would
    real_guard = dg.run

    def with_files(out_dir, prev_dir=None, **kw):
        for k in keys:
            _put(out_dir, "zz_%s.json.gz" % k)
        return real_guard(out_dir, prev_dir=prev_dir, **kw)

    monkeypatch.setattr(dg, "run", with_files)
    _mock_build(tmp_path)
    out = open(tmp_path / "site" / "_headers", encoding="utf-8").read()
    assert dg.headers_rule_count(out) <= 20 and "/zz_*\n  Cache-Control: no-store" in out
    assert all(build_static.headers_cover(out, "zz_%s.json.gz" % k) for k in keys)
    assert build_static.headers_cover(out, "dashboard.json.gz") and not build_static.headers_cover(out, "index.html")
    assert json.load(open(tmp_path / "deploy_guard.json"))["headers"]["rewritten"] is True


def test_build_starts_from_the_live_site_so_an_oversize_file_falls_back_to_it(tmp_path, monkeypatch, capsys):
    """The workflow pulls the live site into site/ before the build. A file that then comes out over the cap is put back
    as it was in the live site (here the cap is lowered to 1 MiB so the 2 MiB page is the one over it)."""
    site = tmp_path / "site"
    os.makedirs(site)
    (site / "index.html").write_bytes(b"<html>the live page</html>")
    monkeypatch.setattr(dg, "MAX_FILE_BYTES", 1 << 20)
    _mock_build(tmp_path)
    assert (site / "index.html").read_bytes() == b"<html>the live page</html>"
    rep = json.load(open(tmp_path / "deploy_guard.json"))
    assert rep["oversize"]["kept_previous"] == 1 and rep["oversize"]["needs_split"] == ["index.html"]
    assert "need a split" in capsys.readouterr().err
    assert not os.path.exists(tmp_path / dg.PREV_DIRNAME)


def test_build_with_no_live_site_leaves_an_oversize_file_out(tmp_path, monkeypatch):
    monkeypatch.setattr(dg, "MAX_FILE_BYTES", 1 << 20)
    _mock_build(tmp_path)
    assert not os.path.exists(tmp_path / "site" / "index.html")
    assert os.path.exists(tmp_path / "site" / "dashboard.json.gz")                    # the rest of the site is whole
    assert json.load(open(tmp_path / "deploy_guard.json"))["oversize"]["files"][0]["action"] == "left_out"


def test_a_crashing_guard_never_breaks_the_build_and_leaves_no_stale_report(tmp_path, monkeypatch, capsys):
    (tmp_path / "deploy_guard.json").write_text('{"ok": true, "summary": "from an older run"}')
    monkeypatch.setattr(dg, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = _mock_build(tmp_path)
    assert r["revenue"] > 0 and os.path.exists(tmp_path / "site" / "dashboard.json.gz")
    assert "deploy guard skipped: RuntimeError" in capsys.readouterr().err
    assert not os.path.exists(tmp_path / "deploy_guard.json") and not os.path.exists(tmp_path / dg.PREV_DIRNAME)


def test_the_guard_is_the_last_step_of_build():
    import inspect
    src = inspect.getsource(build_static.build)
    assert src.index("_guard_snapshot(out_dir)") < src.index("settings()")
    assert src.index("_uninstall_mark_sent(") < src.index("_deploy_guard_step(out_dir, guard_prev)") < src.index("return {")


# ── the workflow ────────────────────────────────────────────────────────────────────────────────────────────────────

def _steps():
    with open(os.path.join(ROOT, ".github", "workflows", "refresh.yml"), encoding="utf-8") as f:
        return yaml.safe_load(f)["jobs"]["refresh"]["steps"]


def test_workflow_warns_with_counts_only_and_still_pushes():
    steps = _steps()
    run = [str(s.get("run") or "") for s in steps]
    b = next(i for i, r in enumerate(run) if "admob_iq.build_static" in r)
    g = next(i for i, r in enumerate(run) if "admob_iq.deploy_guard annotate" in r)
    p = next(i for i, s in enumerate(steps) if str(s.get("name", "")).startswith("Push refreshed data"))
    assert b < g < p                                                          # build → report → push
    assert steps[g].get("continue-on-error") is True and "if" not in steps[g]  # a warning never stops the push
    assert "if" not in steps[p]
    assert "deploy_guard.json" in run[g] and "tee" not in run[g] and "cat " not in run[g]    # the report itself is never dumped
