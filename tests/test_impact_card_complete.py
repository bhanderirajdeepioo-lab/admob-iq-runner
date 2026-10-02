"""Nothing is missing from 📦 Update impact (owner, 1 Oct: "update impact me bahot sari jankari thi aur bhi, vo sab kaha
gayi"): the Uninstall tab's per-app card and its All-apps "📦 Updates ka asar" list, rendered by the page script as it
was at 3339e07 (before SPEC_SIMPLIFY, when the card was shown on both Uninstall and Active users) and by today's, on the
committed synthetic fixture (tests/fixtures/uninstall_sample.json) — tests/impact_card_compare.js. Every app, every
update block opened in turn, at every window it carries (7 / 14 / 30 / 60): the same sections, block keys, row ids,
statuses, pills, every block's window buttons (the card-wide one is gone on purpose: owner, 2 Oct — one picker per
block), "How we compare" bullets, version table, notes, verdict reason and the same numbers
(label words may differ only as SPEC_SIMPLIFY §6.4 says). The list: every update the old one showed, with its verdict
and every number. Skipped where node or the 3339e07 page (git history) is not available."""

import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "tests", "fixtures", "uninstall_sample.json")
NODE, GIT = shutil.which("node"), shutil.which("git")
BEFORE = "3339e07"                      # the last commit before SPEC_SIMPLIFY: the card on both tabs
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def _script(html):
    return max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    old = subprocess.run([GIT, "-C", ROOT, "show", BEFORE + ":frontend/index.html"], capture_output=True, text=True) if GIT else None
    if old is None or old.returncode != 0:
        pytest.skip("the %s page is not in this checkout's history" % BEFORE)
    d = tmp_path_factory.mktemp("impcmp")
    paths = {}
    for name, html in (("old", old.stdout), ("new", open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read())):
        paths[name] = str(d / (name + ".js"))
        with open(paths[name], "w", encoding="utf-8") as f:
            f.write(_script(html))
        subprocess.run([NODE, "--check", paths[name]], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "impact_card_compare.js"), paths["old"], paths["new"], FX],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def test_renders_without_errors(report):
    assert report["errors"] == []


def test_every_card_section_row_and_number_of_3339e07_is_on_the_uninstall_app_page(report):
    C = report["cards"]
    assert report["apps"] >= 5 and report["blocks"] >= 5 and report["windows"] > report["blocks"]   # 14 / 30 / 60 too
    assert all(c["old"] and c["new"] for c in C), [c for c in C if not (c["old"] and c["new"])]
    bad = [c for c in C if not c["same"]]
    assert not bad, (bad[:3], report["diffs"][:1])
    assert sum(c["rows"] for c in C) >= 100 and sum(c["numbers"] for c in C) >= 1000


def test_the_all_apps_list_keeps_every_update_with_its_verdict_and_numbers(report):
    L = report["list"]
    assert L["old_has"] and L["new_has"] and L["old"] >= 5
    assert L["missing"] == [] and L["changed"] == [] and L["numbers_missing"] == [] and L["new"] >= L["old"]
