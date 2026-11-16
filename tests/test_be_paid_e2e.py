"""⚖️ Breakeven · Google Ads | Organic — END TO END (owner, 16 Nov 2026: "haan sirf google ads wale users se karo ·
google ads and organic dono ka alag alag dekh saku esa kar do"; tests/test_roi_paid.py, test_be_paid.py and
test_cpx_frontend.py take each side alone). Made-up stores: tests/test_roi_build.py's country cube with more users, the
Google Ads users' cube in fetch.ga4_cube_paid.MOD's own folder (every cell of it ≤ the all-users one but on two days, two
reads apart: a country only its read names, a country whose cells it holds above the all-users read's) and both
first-session stores → the ROI step with its Google Ads users' pass (roi_build: the build's scratch folder) → the
Breakeven step with BE_PAID (be_build: the app src "p", its Organic file, the pointer's "org") → the page:
tests/be_paid_page.js runs the CPX module of frontend/index.html on EXACTLY those files, no hand-made shape between the
two sides. Covered: the page takes what the build writes — the users switch, the Google
Ads view's line and every day of the file; the Organic file fetched once Organic opens and accepted (never refused),
every one of its days in the table with the file's users (null while not final: "—"), revenue so far and "vs B" as the
file has them, every day opened (one row per card day it has lived, days 1 … 14 drawn when it has any), the drift days'
"GA4 farak" (left out, never clamped — and no other day: the same AdMob scale on both reads keeps every other cell inside
the rounding); a Google Ads users' walk
still running → every user's file with the walk's progress date on the page and no Organic file; with the switches off
every output — the ROI file, its packs, roi.json.gz, the Breakeven file, its caches, both pointers, the lines, stderr —
and the page's every render exactly the build's and the page's from before the switch (digests worked out once with
those, loaded next to this tree). The world's days have not lived to a breakeven (no covered country: no card), so the
day's calibrations are seeded empty — predict reads none of their maps; tests/test_be_paid.py makes real ones.
SYNTHETIC values only (the runner repo is public)."""
import contextlib
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
from datetime import date, datetime, timezone

import pytest

from admob_iq import be_build as be
from admob_iq import roi_build as rb
from admob_iq.fetch import ga4_cube_paid as cp
from tests.test_roi_build import CHS, CTODAY, _cc_cube, _cc_world, _stub_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "frontend", "index.html")
NODE = shutil.which("node")
KEY, AID = "aaaaaaaaaaaa", "a~1"
CI = {"AA": 80, "BB": 10, "CC": 6, "--": 4, "FF": 40}      # every new user's installs a day by country (made-up codes) …
CR = {"AA": 100000, "BB": 1000, "CC": 20000, "--": 10000, "FF": 1000}   # … their GA4 micros a day per install day
PI = {"AA": 40, "BB": 5, "CC": 3, "--": 2, "EE": 1, "FF": 10}           # the Google Ads users' (≤ CI) — but two reads
PR = {"AA": 40000, "BB": 500, "CC": 8000, "--": 4000, "EE": 3000, "FF": 5000}   # apart on two days: EE only their read
DRIFT, DRIFT2 = date(2026, 9, 5), date(2026, 9, 12)        # names (DRIFT), FF's cells above every user's (DRIFT2)
DAILY = ("AA", "BB", "CC", "--")                            # (the countries of every install day)
NOW = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)    # the build: the day after both cubes' newest
BUSY = {"from": "2026-08-01", "walk_at": "2026-10-13T05:00:00Z"}   # a Google Ads users' walk not through yet
GA_LINE = "Sirf Google Ads se aaye users ki kamai ÷ Google Ads spend (GA4: first user channel Cross-network + Paid Search)"
ORG_LINE = ("Organic = jo users Google Ads se nahi aaye (Play search, direct, baaki) — inka koi spend nahi, isliye ROAS / "
            "breakeven nahi; sirf ginti aur kamai, unke apne purane dino ke median se")
# sha256 (_digest) of the switch-off chain's outputs, and (the page's report "sha") of every render of its Breakeven file
# by tests/be_paid_page.js --old — worked out once with admob_iq/roi_build.py, admob_iq/be_build.py and
# frontend/index.html as they were before the switch existed (loaded next to this tree), on this same world
BEFORE = "ec9067fdff441d87a3d0de5eae5726370c34f4c3ec03a180ca3c876f8c14937c"
BEFORE_PAGE = "3073dec2dc0cc177b3fb549235e502a5c9ac0c367c0290ed4268f7edde63bdf2"


def _tree(root):
    out = {}
    for base, _dirs, names in os.walk(str(root)):
        for n in names:
            p = os.path.join(base, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, str(root))] = f.read()
    return out


def _nvr(data, folder, k, parts):
    """A first-session store (fetch.ga4_nvr's format; ⚖️ fetch.ga4_nvr_paid's: "c" only) of every install day: each
    real country's first session ("n": 10 impressions a user at a 4 USD eCPM) and a returning row — k of each for the
    Google Ads users; its history read back to the start (the backfill done)."""
    days, X = {}, CHS
    while X <= CTODAY:
        c = []
        for cc in DAILY:
            if cc != "--":
                c += [["n", cc, round(0.04 * CI[cc] * k, 6), int(10 * CI[cc] * k)], ["r", cc, 1.0, 400]]
        days[X.isoformat()] = dict({"c": c}, **({"u": [], "s": []} if parts else {}))
        X = date.fromordinal(X.toordinal() + 1)
    os.makedirs(os.path.join(data, folder), exist_ok=True)
    with gzip.open(os.path.join(data, folder, KEY + ".json.gz"), "wt", encoding="utf-8") as f:
        json.dump({"v": 2, "days": days, "backfill": {"oldest": CHS.isoformat(), "done": True}}, f)


def _chain(tmp, mp, on, mods=None, paid=None, head=None):
    """The world → the ROI step (start / app_step / finish) → the Breakeven step, the switches `on` (GA4_CUBEP and
    BE_PAID, as uninstall_build passes them) or off — the Google Ads users' stores on disk either way (GA4_CUBEP's reads
    run without BE_PAID); mods: (roi_build, be_build) — the build before the switch, for the digests; paid / head: the
    Google Ads users' cube (_cc_cube's arguments) / fields set on its head → every output, PAID and its folder."""
    rbm, bem = mods or (rb, be)
    data, P, pre, spend, acc0 = _cc_world(tmp, inst=CI, rate=CR, only={"FF": {DRIFT2}})
    _cc_cube(data, **dict({"cube_mod": cp.MOD, "inst": PI, "rate": PR, "only": {"EE": {DRIFT}, "FF": {DRIFT2}}},
                          **(paid or {})))
    if head:
        h = cp.MOD.load_head(str(data), AID)
        cp.MOD.write_json_gz_stable(cp.MOD.hot_path(str(data), AID), dict(h, **head))
    _nvr(str(data), "ga4_nvr", 1.0, True)
    _nvr(str(data), "ga4_nvr_paid", 0.5, False)
    os.makedirs(os.path.join(str(data), "be_tab"), exist_ok=True)
    for f in ("calib.json", "calib_p.json"):                  # (the day's, empty: no covered country reads a map;
        with open(os.path.join(str(data), "be_tab", f), "w", encoding="utf-8") as fh:     # calib.json made in the
            json.dump(dict({"v": 1, "built": NOW.date().isoformat(), "cv": be.CALV, "cty": {}, "pit": {}, "band": {}},
                           **({"bp": 1} if on and f == "calib.json" else {})), fh)     # chain's mode: stamped when on)
    _stub_app(mp, P, {"read_today": CTODAY.isoformat(), "stream_id": "222", "x": {}}, spend)
    out = tmp / "out"
    out.mkdir()
    before, err, dash = _tree(data), io.StringIO(), {}
    with contextlib.redirect_stderr(err):
        acc = rbm.start(cube=True, cmon=acc0.cmon, **({"cubep": on} if rbm is rb else {}))
        rbm.app_step(acc, {"history_start": CHS.isoformat(), "stream_id": "222"}, {"app_id": AID, "app_name": "Alpha"},
                     KEY, {"tz": "UTC"}, pre, {}, str(out), str(data), ids=[AID])
        hdr = rbm.finish(acc, dash, str(out))
        rl = rbm.pop_line()
        paths = bem.run(dash, str(data), str(out), {"be_paid": on}, NOW)
        bl = bem.pop_line()
    after = _tree(data)
    cache = {k: v for k, v in after.items() if k.startswith("be_tab" + os.sep)}
    assert {k: v for k, v in after.items() if k not in cache} == {k: v for k, v in before.items() if k not in cache}
    return {"out": _tree(out), "cache": cache, "dash": dash, "lines": [rl, bl], "err": err.getvalue(),
            "paths": [hdr, paths], "paid": dict(rb.PAID), "dir": rb.PAID_DIR, "tmp": tmp,
            "scratch": sorted(os.listdir(rb.PAID_DIR)) if rb.PAID_DIR else []}


def _digest(r):
    """sha256 of everything the two steps made: their site files (decompressed), the Breakeven caches, the board's
    pointers, the lines, stderr, the header rules."""
    files = {}
    for side in ("out", "cache"):
        for n, raw in sorted(r[side].items()):
            files[side + "/" + n] = hashlib.sha256(gzip.decompress(raw) if n.endswith(".gz") else raw).hexdigest()
    top = {"files": files, "dash": r["dash"], "lines": r["lines"], "err": r["err"], "paths": r["paths"]}
    return hashlib.sha256(json.dumps(top, sort_keys=True).encode()).hexdigest()


def _js(raw):
    return json.loads(gzip.decompress(raw))


def _page(r, old=False, page=PAGE):
    """tests/be_paid_page.js on the build's own Breakeven pointer and files (r) → its report (no error, no junk word)."""
    files = {n: _js(raw) for n, raw in r["out"].items() if n.startswith("be_")}
    inp = os.path.join(str(r["tmp"]), "page.json")
    with open(inp, "w", encoding="utf-8") as f:
        json.dump({"be": r["dash"]["be"], "apps": sorted(r["dash"]["be"]["apps"]), "files": files}, f)
    p = subprocess.run([NODE, os.path.join(ROOT, "tests", "be_paid_page.js"), page, inp] + (["--old"] if old else []),
                       check=True, capture_output=True, text=True, timeout=300)
    rep = json.loads(p.stdout)
    assert rep["errors"] == [] and rep["bad"] == [], (rep["errors"], rep.get("bad"))
    return rep


@pytest.fixture(scope="module")
def chains(tmp_path_factory):
    """The world built three times: the switches off, on, and on with the Google Ads users' walk still running."""
    out = {}
    for name, on, kw in (("off", False, {}), ("on", True, {}), ("busy", True, {"paid": {"done": False}, "head": BUSY})):
        with pytest.MonkeyPatch.context() as mp:
            out[name] = _chain(tmp_path_factory.mktemp("e2e_" + name), mp, on, **kw)
    rb.start()                                              # (the last pass's scratch folder let go)
    return out


needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


# ── the switches off: every output, and the page, as before the switch ──────────────────────────────────────────────
def test_switches_off_every_output_byte_for_byte_as_before_the_switch(chains):
    r = chains["off"]
    assert r["paid"] == {} and r["dir"] is None and r["scratch"] == []
    assert not [n for n in r["out"] if n.endswith("_o.json.gz") or re.search(r"_p\d*\.json\.gz$", n)]
    b = _js(r["out"]["be_%s.json.gz" % KEY])
    assert "src" not in b and "pw" not in b and not any("ecs" in d for d in b["days"])
    assert set(r["dash"]["be"]["apps"][AID]) == {"key", "file", "v", "n", "cov"}
    assert ", paid" not in r["lines"][0] and ", src" not in r["lines"][1] and r["err"] == ""
    assert _digest(r) == BEFORE


@needs_node
def test_switches_off_the_page_renders_the_file_byte_for_byte_as_before_the_switch(chains):
    rep = _page(chains["off"], old=True)
    for k, v in rep["apps"][AID].items():
        if not k.endswith("d/p") and not k.endswith("d/o"):
            assert v["sw"] == [] and not v["org"] and v["ga"], k          # (no switch, no Organic: today's tab)
    assert rep["sha"] == BEFORE_PAGE


def test_the_switch_on_leaves_every_all_users_output_as_it_was(chains):
    on, off = chains["on"], chains["off"]
    assert {n: v for n, v in on["out"].items() if not n.startswith("be_")} == \
        {n: v for n, v in off["out"].items() if not n.startswith("be_")}               # the ROI files, packs, roi.json
    assert on["dash"]["roi"] == off["dash"]["roi"] and on["paths"][0] == off["paths"][0]
    tail = "ads split unread 0"
    assert on["lines"][0] == off["lines"][0].replace(tail, tail + ", paid ok 1 busy 0 none 0 fail 0")
    assert on["err"] == "" and on["lines"][1].endswith(", src p 1 a 0, calib p no, org 1, org fail 0")


# ── the switches on: what the build writes is what the page reads ─────────────────────────────────────────────────
def test_the_build_hands_its_google_ads_users_files_to_the_breakeven_step(chains):
    r = chains["on"]
    assert r["paid"] == {KEY: {"st": "ok", "file": "roi_%s_p.json.gz" % KEY}}
    assert r["scratch"] == ["roi_%s_p.json.gz" % KEY, "roi_%s_p00.json.gz" % KEY]
    b, o = _js(r["out"]["be_%s.json.gz" % KEY]), _js(r["out"]["be_%s_o.json.gz" % KEY])
    assert b["src"] == "p" and "pw" not in b and b["key"] == KEY
    e = r["dash"]["be"]["apps"][AID]
    assert (e["key"], e["file"], e["org"]) == (KEY, "be_%s.json.gz" % KEY, "be_%s_o.json.gz" % KEY)
    raw = gzip.decompress(r["out"][e["file"]])
    assert e["v"] == hashlib.sha1(raw + hashlib.sha1(gzip.decompress(r["out"][e["org"]])).digest()).hexdigest()[:12]
    assert (o["v"], o["key"], o["origin"]) == (1, KEY, NOW.date().isoformat())
    assert o["ages"] == [0, 1, 2, 3, 6, 13, 30, 60] and o["ages"] == [g for g in be.GRID if g <= 60]
    days = [x["d"] for x in o["days"]]
    assert days == sorted(days) and days[0] == CHS.isoformat() and days[-1] == CTODAY.isoformat()
    dr = [x for x in o["days"] if "dr" in x]
    assert [(x["d"], x["dr"]) for x in dr] == [(DRIFT.isoformat(), [1, 0]),            # EE: only their read names it;
                                               (DRIFT2.isoformat(), [1, 30])]          # FF: 30 organic users left out
    n = sum(CI[cc] - PI[cc] for cc in DAILY)
    fold = _js(r["out"]["roi_%s.json.gz" % KEY])["cd"]["fthru"]                       # (both cubes folded through it)
    assert {x["n"] for x in o["days"] if x["d"] <= fold} == {n}   # every country's organic users (a drift's: none counted)
    young = [x for x in o["days"] if x["d"] > fold]               # day 0 not folded by both: two hot reads — not final
    assert [x["d"] for x in young] == ["2026-10-11", "2026-10-12", "2026-10-13"]
    assert all(x["n"] is None and x["r"] == [] and x["s"] == {"pu": [], "b": [], "cv": []} and "dr" not in x
               for x in young)
    x = {x["d"]: x for x in o["days"]}[date(2026, 8, 20).isoformat()]
    assert x["s"]["cv"][0] == round(40 / 50, 4)                                       # (AA's 40 alone have a benchmark)


def _lived(x, ages):
    return [i for i, g in enumerate(ages) if isinstance(x.get("age"), int) and 0 <= g <= x["age"]]


def _at(v, i):
    return v[i] if isinstance(v, list) and i < len(v) else None


def _ol(g):
    """The page's card day of an age: day k = age k − 1 (the 30-day columns by their age, as the Google Ads table's)."""
    return g + 1 if g < 30 else g


def _near(s, v):
    """A number the page printed (s: "$0.65", "0.013" …) is the file's v to its printed decimals (half a unit of the
    last one, + float noise: 0.645 prints as 0.65)."""
    s = s.lstrip("$")
    return abs(float(s) - v) <= 0.5 * 10 ** -len(s.partition(".")[2]) + 1e-9


@needs_node
def test_the_page_shows_both_views_of_exactly_these_files(chains):
    r = chains["on"]
    rep = _page(r)
    b, o = _js(r["out"]["be_%s.json.gz" % KEY]), _js(r["out"]["be_%s_o.json.gz" % KEY])
    A, ages = rep["apps"][AID], o["ages"]
    # the Google Ads view: the switch (Google Ads on), its one line, today's table of the file's days (newest first, 30)
    for cur in ("USD", "INR"):
        ga = A[cur + "/ga"]
        assert ga["sw"] == [["p", True, "Google Ads"], ["o", False, "Organic"]] and ga["ga"] and not ga["org"]
        assert ga["lines"][0] == ["fn", GA_LINE] and ga["more"]
        assert [x["d"] for x in ga["rows"]] == sorted((x["d"] for x in b["days"]), reverse=True)[:30]
        gad = A[cur + "/gad"]                                   # (every day of the file opened: one open at a time)
        assert [d["d"] for d in gad] == [x["d"] for x in b["days"]] and all(d["open"] == 1 for d in gad)
    # the Organic view: the switch (Organic on), its note, the file taken (never "load nahi hua" / "abhi nahi bana")
    for cur in ("USD", "INR"):
        og = A[cur + "/org"]
        assert og["sw"] == [["p", False, "Google Ads"], ["o", True, "Organic"]] and og["org"] and not og["ga"]
        assert og["lines"][0] == ["fn", ORG_LINE] and og["more"]
        assert og["head"] == ["Date", "vs benchmark", "Revenue so far", "Organic users"]     # (the answer first)
        assert not any("load nahi hua" in t or "abhi nahi bana" in t for _, t in og["lines"])
        assert [x["d"] for x in og["rows"]] == sorted((x["d"] for x in o["days"]), reverse=True)[:30]
        assert [x["d"] for x in A[cur + "/orgall"]] == sorted((x["d"] for x in o["days"]), reverse=True)
    # every Organic day's row ($), the answer first: the newest FINAL card day's "vs B" (a drift day's "GA4 farak" beside
    # it), revenue so far (total · per user, its newest card day with a number: "day N tak") and its users ("—" while not
    # final) — the file's own numbers, never recomputed
    rows = {x["d"]: x for x in A["USD/orgall"]}
    n_vs = 0
    for x in o["days"]:
        c = rows[x["d"]]["cells"]                               # Date | vs benchmark | Revenue so far | Organic users
        assert (c[3] == "—") if x["n"] is None else int(c[3].replace(",", "")) == x["n"], (x["d"], c[3])
        assert c[1].endswith(" GA4 farak") == ("dr" in x) and "data check" not in " ".join(c), x["d"]   # (the drift's word)
        vs = c[1][:-len(" GA4 farak")] if "dr" in x else c[1]
        L = _lived(x, ages)
        j = max([i for i in L if _at(x["r"], i) is not None], default=-1)
        if j < 0:
            assert c[2] == "—", x["d"]
        else:
            m = re.fullmatch(r"\$([\d.]+) · \$([\d.]+)/user day (\d+) tak( \(not final\))?", c[2])
            assert m, (x["d"], c[2])
            assert _near(m.group(1), x["r"][j]) and _near(m.group(2), x["pu"][j]), (x["d"], c[2])
            assert int(m.group(3)) == _ol(ages[j]) and bool(m.group(4)) == (_at(x["fin"], j) != 1), x["d"]
        s = x["s"]
        jf = max([i for i in L if _at(x["fin"], i) == 1 and (_at(s["b"], i) or 0) > 0 and _at(s["pu"], i) is not None
                  and s["pu"][i] >= 0], default=-1)
        if jf < 0:
            assert vs == "—", (x["d"], c[1])
            continue
        n_vs += 1
        m = re.match(r"([+−±])(\d+)% vs B on day (\d+)(?: (\d+)% users: data kam)?$", vs)
        assert m, (x["d"], c[1])
        q = s["pu"][jf] / s["b"][jf] - 1
        assert abs((-1 if m.group(1) == "−" else 1) * int(m.group(2)) - 100 * q) <= 0.5 + 1e-9, (x["d"], c[1], q)
        assert int(m.group(3)) == _ol(ages[jf]), (x["d"], c[1])
        assert int(m.group(4) or 0) == round(100 * (1 - s["cv"][jf])), (x["d"], c[1])    # (cv < 1: "x% users: data kam")
    assert n_vs > 30 and sum(1 for x in o["days"] if x["n"] is None) == 3
    # every Organic day opened: one row per card day it has lived, the answer first (%, the benchmark countries' per user,
    # their benchmark per user, the day's revenue — as the file has them, or "—"), days 1 … 14 drawn when it has any
    for d in A["USD/orgd"]:
        x = {x["d"]: x for x in o["days"]}[d["d"]]
        L, s = _lived(x, ages), x["s"]
        assert d["open"] == 1 and d["tbl"]["head"] == ["Day", "%", "Per user", "Benchmark per user", "Revenue (total)"]
        assert [rw[0] for rw in d["tbl"]["rows"]] == ["Day %d" % _ol(ages[i]) for i in L], d["d"]
        for i, rw in zip(L, d["tbl"]["rows"]):
            for k, v in ((2, _at(s["pu"], i)), (3, _at(s["b"], i)), (4, _at(x["r"], i))):   # (the file's, or "—")
                assert rw[k].startswith("—") if v is None else _near(rw[k].split()[0], v), (d["d"], i, k, rw)
            sp, sb = _at(s["pu"], i), _at(s["b"], i)            # (the % = that per user ÷ its benchmark − 1)
            if sp is None or not sb:
                assert rw[1] == "—", (d["d"], i, rw)
            else:
                m = re.fullmatch(r"([+−±])(\d+)%", rw[1])
                assert m and abs((-1 if m.group(1) == "−" else 1) * int(m.group(2)) - 100 * (sp / sb - 1)) <= 0.5 + 1e-9, \
                    (d["d"], i, rw)
        drawn = any(_at(s["pu"], i) is not None or _at(s["b"], i) is not None for i in range(len(ages)) if ages[i] <= 13)
        assert d["svg"] == drawn and d["ax"] == (["1 day", "2 days", "3 days", "4 days", "7 days", "14 days"] if drawn
                                                 else []), d["d"]
        assert drawn == (x["n"] is not None), d["d"]            # (a day not final for users: nothing to draw)
        dl = [t for _, t in d["lines"] if t.startswith("GA4 farak")]
        want = ["GA4 farak — kuch din GA4 ke do reads me farak — un countries ko chhoda."] if "dr" in x else []
        assert dl == want, (d["d"], dl)
        assert not [t for _, t in d["lines"] if "data check" in t or "nahi gine" in t], d["d"]   # (no count of its own)
    assert len(A["USD/orgd"]) == len(o["days"]) == len(A["INR/orgd"])
    # the Organic file: never asked for by the Google Ads view, once when Organic opens, not again
    lz, org = A["lazy"], "be_%s_o.json.gz" % KEY
    assert org not in lz["ga"] and lz["on"].count(org) == 1 and lz["again"].count(org) == 1 and lz["shown"]
    assert lz["src"] == "o"


def test_a_walk_still_running_is_every_users_file_with_its_progress(chains):
    r, off = chains["busy"], chains["off"]
    assert r["paid"] == {KEY: {"st": "busy", "from": "2026-08-01", "next": "2026-10-11", "at": "2026-10-13"}}
    assert r["scratch"] == [] and "org" not in r["dash"]["be"]["apps"][AID]
    assert not [n for n in r["out"] if n.endswith("_o.json.gz")]
    b = _js(r["out"]["be_%s.json.gz" % KEY])
    assert b["src"] == "a" and b["pw"] == {"st": "busy", "from": "2026-08-01", "next": "2026-10-11"}   # (no "at")
    assert {k: v for k, v in b.items() if k not in ("src", "pw")} == _js(off["out"]["be_%s.json.gz" % KEY])
    assert r["lines"][1].endswith(", src p 0 a 1, calib p no, org 0, org fail 0") and r["err"] == ""


@needs_node
def test_a_walk_still_running_shows_its_progress_on_the_page(chains):
    rep = _page(chains["busy"])
    A = rep["apps"][AID]
    for cur in ("USD", "INR"):
        ga, og = A[cur + "/ga"], A[cur + "/org"]
        assert ga["sw"] == [["p", True, "Google Ads"], ["o", False, "Organic"]] and ga["ga"]
        assert ga["lines"][0] == ["vm", "Google Ads users ka data GA4 se abhi aa raha hai — tab tak ye saare users ka hai "
                                        "(11 Oct se pehle ke din padh liye)"]
        assert og["lines"] == [["fn", ORG_LINE], ["note", "Organic data abhi nahi bana — Google Ads users ka data aane ke "
                                                          "baad banega"]] and og["rows"] == [] and not og["org"]
    assert not [f for f in A["lazy"]["on"] + A["lazy"]["again"] if f.endswith("_o.json.gz")]
