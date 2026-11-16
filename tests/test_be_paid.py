"""⚖️ Breakeven — Google Ads users only (admob_iq.be_build with BE_PAID; owner, 16 Nov 2026: "haan sirf google ads wale
users se karo · google ads and organic dono ka alag alag dekh saku esa kar do") on made-up apps: tests/test_be_build.py's
world + a made-up Google Ads users' pass in a scratch folder, in the shapes roi_build's paid pass writes (its file, its
packs, fetch.ga4_nvr_paid's store). Covered: with the switch off every output of the step byte for byte as before the
switch existed (digests worked out once with that build); src "p" only when roi_build's pass is "ok" for the app, its
file is there and their first-session store is read back (its backfill done) — its rows, packs and first-session store
read, AdMob's daily revenue and the pack gaps' reference (every user's All rows: a paid-cube date folded near-empty marks
the card) from the all-users file — every other app src "a" with the paid walk's progress ("pw"), one whose source cannot
be told too; the caches and the calibration per source, never mixed, once a UTC day each, none for a source without an
app, calib.json stamped with its mode (a same-day rollback answers every app as a build that never had the switch); too
few Google Ads users' days for a first calibration: a state, not a failure; "ecs" beside the eCPM card; the counts line;
the Organic file worked by hand (users — final only —, revenue at the card ages from final cells only, "--" / "ZZ"
revenue once, per user, fin, a drift left out and counted — never clamped, the 30-day columns' double rounding never one
—, the benchmark's weights and cv), and on roi_build's own paid files; each paid pack read once a build and the Organic
pass only after the app's file, timed as its own stage of the tab; a Google Ads users' [X] row on a day of unknown
spend; failure isolation (an Organic
failure costs only it; a Google Ads source that fails goes on as every user's); stale Organic files cleaned. SYNTHETIC
values only (the runner repo is public): apps "app~synth-…", countries AA … DH, the calendars 2026 and 2030–2031."""
import contextlib
import copy
import gzip
import hashlib
import io
import json
import os
from datetime import date, timedelta

import pytest

from admob_iq import be_build as be
from admob_iq import health
from admob_iq import roi_build as rb
from admob_iq.fetch import ga4_uninstall as gu
from tests import test_be_build as T
from tests import test_be_ecpm as TE

KA, KB, KC = T.KEYS["a"], T.KEYS["b"], T.KEYS["c"]
AD = "app~synth-d"
KD = gu.file_key(AD)
FU, FR = 0.6, 0.55                     # the Google Ads users' share of each pack row's users / of its revenue cells
FS = (0.6, 0.5)                        # … of the first session's revenue / impressions (their eCPM_fs = 1.2 × every user's)
TD = T.TODAY.isoformat()


def _rd(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _raw(body):
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _wr(path, body):
    with open(path, "wb") as f:
        f.write(gzip.compress(_raw(body), mtime=0))


# ── the step with the switch off: byte for byte as before it ───────────────────────────────────────────────────────

def _digest(site, data, dash, paths, line, err):
    """sha256 of everything the step made: its files (decompressed), its caches, the pointer, the line, its stderr."""
    files = {}
    for f in sorted(os.listdir(site)):
        if f.startswith("be_"):
            with open(os.path.join(site, f), "rb") as fh:
                files[f] = hashlib.sha256(gzip.decompress(fh.read())).hexdigest()
    cd = os.path.join(data, "be_tab")
    for f in sorted(os.listdir(cd)) if os.path.isdir(cd) else ():
        with open(os.path.join(cd, f), "rb") as fh:
            raw = fh.read()
        files["cache/" + f] = hashlib.sha256(gzip.decompress(raw) if f.endswith(".gz") else raw).hexdigest()
    top = {"paths": paths, "ptr": dash.get("be"), "line": line, "err": err, "files": files}
    return hashlib.sha256(json.dumps(top, sort_keys=True).encode()).hexdigest()


def _swap(mod, name, fn):
    old = getattr(mod, name)
    setattr(mod, name, fn(old))
    return lambda: setattr(mod, name, old)


def _no_cal(mod):
    def boom(*a, **k):
        raise KeyError("x")
    return _swap(mod, "calibrate", lambda old: boom)


def _bad_load(mod):
    def wrap(old):
        def bad(out_dir, data_dir, key, fn, *a):
            if key == KB:
                return 1 / 0
            return old(out_dir, data_dir, key, fn, *a)
        return bad
    return _swap(mod, "load", wrap)


N0 = T.NOW
SCENARIOS = {                          # name → (the world's extra, [(settings, now, patch)])
    "plain": (None, [({}, N0, None), ({}, N0 + timedelta(hours=5), None), ({}, N0 + timedelta(days=1), None),
                     ({"be_paid": False}, N0 + timedelta(days=1, hours=2), None)]),
    "ecpm": ("ecpm", [(TE.ON, N0, None), (dict(TE.ON, be_paid=False), N0 + timedelta(days=1), None)]),
    "nocal": (None, [({}, N0, _no_cal), ({}, N0 + timedelta(hours=1), None)]),
    "keepcal": (None, [({}, N0, None), ({}, N0 + timedelta(days=1), _no_cal)]),
    "badload": (None, [({"be_paid": False}, N0, _bad_load)]),
}
# sha256 (_digest) of each step's outputs — worked out once with admob_iq/be_build.py as it was before BE_PAID existed
# (loaded next to this tree), on these same worlds and steps
BEFORE = {
    "plain": ["dfeaccb3de66f5598a423f9c76e3095ddb53b40e7f506acb9ab987614b0e42e6",
              "0c430bac1d5623bae32f3ffa75631e51581d4e213b6d40ff5c8a49be940cee4b",
              "2554f4bff47c8cf05ce59091b08f55b00ff3d46570abc9ea0efd289df964b5b0",
              "130527ea965fb796c7d1fd2a8fc5c0f084f4237aa44d7edcd61c9078acf87421"],
    "ecpm": ["085998793e33589313ccb61516b287548c31ff66aa3ff5d048dd9f7b2e614808",
             "7ffe7a1b9ee6212f5ac6cad24f0bdd45890f63e4d6d575e0216d18ed351f962e"],
    "nocal": ["024f9de8a72973aa3daeb6aae1a075d5787ea9e5bd24e241f3c9533354b171bc",
              "58e69430bd995fd681304d907cff96821a2ad703e077903d5200b0b4a12fc918"],
    "keepcal": ["dfeaccb3de66f5598a423f9c76e3095ddb53b40e7f506acb9ab987614b0e42e6",
                "e26282ade2e89a5d0e3e61258dd25b00afb0297f101a0839fb6459d363c23ccd"],
    "badload": ["4f581a717eb0937b067ee9e7ca8933b85ed34f93171dfdef5fd793551e2751b1"],
}


def scenario(mod, tmp, name):
    """One SCENARIOS entry through module `mod` (be_build, or the build before the switch) → its steps' digests."""
    extra, steps = SCENARIOS[name]
    site, data, dash = T.make(tmp)
    if extra == "ecpm":
        TE.write_store(data, KA)
    out = []
    for s, now, patch in steps:
        d = copy.deepcopy(dash)
        err = io.StringIO()
        undo = patch(mod) if patch else None
        try:
            with contextlib.redirect_stderr(err):
                paths = mod.run(d, data, site, s, now)
        finally:
            if undo:
                undo()
        out.append(_digest(site, data, d, paths, mod.pop_line(), err.getvalue()))
    return out


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_switch_off_every_output_byte_for_byte_as_before_it(tmp_path, name):
    assert scenario(be, tmp_path, name) == BEFORE[name]


# ── a made-up Google Ads users' pass: roi_build's paid file + its pack in a scratch folder, fetch.ga4_nvr_paid's store ─

def _scale(r):
    """A pack row → its Google Ads users' row: FU of its users, FR of every revenue cell, the same spend / installs."""
    q = list(r)
    q[1] = int(r[1] * FU)
    q[4] = [round(v * FR, 6) for v in r[4]]
    q[8] = q[4][-1] if q[4] else None
    if len(r) > 14:
        q[14] = [round(v * FR, 6) for v in r[14]]
    return q


def _fold(q, D, keep):
    """A Google Ads users' row whose activity date D the paid cube folded near-empty: its revenue of that date × keep (its
    cumulative cells from that age on, its 30-day columns too)."""
    a = (D - date.fromisoformat(q[0])).days
    d = q[4]
    if not d or not 0 <= a < len(d):
        return q
    lost = (d[a] - (d[a - 1] if a else 0.0)) * (1 - keep)
    q[4] = [round(v - lost, 6) if i >= a else v for i, v in enumerate(d)]
    q[8] = q[4][-1]
    if len(q) > 14:
        q[14] = [round(v - lost, 6) for v in q[14]]
    return q


def paid_world(tmp, twin=True, life=None, fold=None):
    """tests/test_be_build.py's world (+ app d, every user's: a twin of app a's covered countries) and app a's Google Ads
    users' pass in tmp/scratch — its file (the paid All rows: Σ its pack's rows a day), its one pack (each country row
    _scale'd) and its first-session store (FS of each "c" row); app a's all-users "cd" gets its edges (read and folded
    through the newest day) and `life` (AdMob's daily revenue); fold: (D, keep) — the paid cube's activity date D folded
    near-empty (_fold: its All rows too, Σ of its pack) → (site, data, dashboard, the scratch folder)."""
    site, data, dash = T.make(tmp)
    if twin:
        T.write_app(site, data, KD, dict(T.CTY), T.NDAYS, T.TODAY, 29)
        dash["roi"]["apps"][AD] = {"file": "roi_%s.json.gz" % KD, "st": "Normal"}
    scr = tmp / "scratch"
    scr.mkdir()
    fn = os.path.join(site, "roi_%s.json.gz" % KA)
    roi = _rd(fn)
    roi["cd"].update(thru=TD, fthru=TD, newest=TD)
    if life is not None:
        roi["life"] = life
    _wr(fn, roi)
    pk = _rd(os.path.join(site, roi["cd"]["packs"][0][0]))
    pc, allr = {}, {}
    for cc, rows in pk["c"].items():
        pc[cc] = [_scale(r) if fold is None else _fold(_scale(r), *fold) for r in rows]
        for q in pc[cc]:
            a = allr.setdefault(q[0], [0, 0.0, 0.0, [0.0] * len(q[4]), [0.0] * (len(q[14]) if len(q) > 14 else 0)])
            a[0] += q[1]
            a[1] += q[2]
            a[2] += q[3]
            a[3] = [x + y for x, y in zip(a[3], q[4])]
            a[4] = [x + y for x, y in zip(a[4], q[14] if len(q) > 14 else [])]
    rows = [T.roi_row(x, a[0], round(a[1], 2), round(a[2], 6), [round(v, 6) for v in a[3]], [round(v, 6) for v in a[4]])
            for x, a in sorted(allr.items())]
    pn = "roi_%s_p00.json.gz" % KA
    praw = _raw({"v": 1, "b": "synthb", "key": KA, "ix": 0, "c": pc})
    with open(os.path.join(str(scr), pn), "wb") as f:
        f.write(gzip.compress(praw, mtime=0))
    _wr(os.path.join(str(scr), "roi_%s_p.json.gz" % KA),
        {"v": 1, "key": KA, "b": "synthb", "rows": rows, "packs": [[pn, hashlib.sha1(praw).hexdigest()[:12]]],
         "thru": TD, "fthru": TD, "newest": TD, "loss": {"days": 0, "share": 0.0}})
    nv = _rd(os.path.join(data, "ga4_nvr", KA + ".json.gz"))
    for rv in nv["days"].values():
        rv["c"] = [[k, cc, round(rev * FS[0], 6), int(im * FS[1])] for k, cc, rev, im in rv["c"]]
        rv.pop("u", None)
        rv.pop("s", None)
    nv["backfill"] = {"oldest": min(nv["days"]), "done": True}               # (its history read back to the start)
    os.makedirs(os.path.join(data, "ga4_nvr_paid"), exist_ok=True)
    _wr(os.path.join(data, "ga4_nvr_paid", KA + ".json.gz"), nv)
    return site, data, dash, str(scr)


def _state(mp, scr, **over):
    """roi_build's PAID / PAID_DIR as its pass leaves them: app a "ok", b busy (with its progress), d no paid store; c
    no entry (no pass ran for it). over: {key: entry | None (no entry)}."""
    st = {KA: {"st": "ok", "file": "roi_%s_p.json.gz" % KA},
          KB: {"st": "busy", "from": "2030-01-01", "next": "2031-02-01", "at": "2031-06-01"},
          KD: {"st": "none"}}
    st.update(over)
    mp.setattr(rb, "PAID", {k: v for k, v in st.items() if v is not None})
    mp.setattr(rb, "PAID_DIR", scr)


def _go(dash, data, site, s, now=T.NOW):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        paths = be.run(dash, data, site, s, now)
    return paths, be.pop_line(), err.getvalue()


def _be(site, k):
    return _rd(os.path.join(site, "be_%s.json.gz" % k))


def _bytes(path):
    with open(path, "rb") as f:
        return f.read()


def _snap(site, data):
    out = {f: _bytes(os.path.join(site, f)) for f in sorted(os.listdir(site)) if f.startswith("be_")}
    for f in sorted(os.listdir(os.path.join(data, "be_tab"))):
        out["cache/" + f] = _bytes(os.path.join(data, "be_tab", f))
    return out


@pytest.fixture(scope="module")
def paid(tmp_path_factory):
    """The made-up world built once with be_paid on (app a src "p") and once with it off (every app every user's)."""
    out = {}
    for name, s in (("on", {"be_paid": True}), ("off", {})):
        tmp = tmp_path_factory.mktemp("bep_" + name)
        site, data, dash, scr = paid_world(tmp)
        with pytest.MonkeyPatch.context() as mp:
            _state(mp, scr)
            paths, line, err = _go(dash, data, site, s)
        out[name] = {"site": site, "data": data, "dash": dash, "scr": scr, "paths": paths, "line": line, "err": err}
    return out


# ── the source of each app ──────────────────────────────────────────────────────────────────────────────────────────

def test_src_p_only_when_the_pass_is_ok_and_its_file_is_there(paid):
    on, off = paid["on"], paid["off"]
    assert on["paths"] == off["paths"] == ["/be_*"] and on["err"] == off["err"] == ""
    a = _be(on["site"], KA)
    assert a["src"] == "p" and "pw" not in a                                  # roi_build's pass "ok", its file there
    assert _be(on["site"], KB)["src"] == "a"
    assert _be(on["site"], KB)["pw"] == {"st": "busy", "from": "2030-01-01", "next": "2031-02-01"}   # (its progress)
    assert _be(on["site"], KC)["pw"] == {"st": "off"} and _be(on["site"], KD)["pw"] == {"st": "none"}
    for k in (KA, KB, KC, KD):                                                # the switch off: no "src" at all, the
        b = _be(off["site"], k)                                               # same PAID notwithstanding
        assert "src" not in b and "pw" not in b and not any("ecs" in d for d in b["days"])
    assert not [f for f in os.listdir(off["site"]) if f.endswith("_o.json.gz")]
    assert sorted(os.listdir(os.path.join(off["data"], "be_tab"))) == sorted(
        ["calib.json"] + ["fits_%s.json.gz" % k for k in (KA, KB, KC, KD)])


def test_src_p_also_needs_the_google_ads_users_first_session_store_read_back(tmp_path):
    """roi_build's pass "ok" and its file there, but their first-session store missing (GA4_NVRP off, or none yet),
    empty, unreadable or of another version: no country of theirs would have an eCPM_fs — every user's file, "off"
    (their data not made this build — never "none": the page says GA4 has none of them, and their cube read them), no
    failure; there with its backfill still running (its history read newest first: the models would train on its recent
    days only): "busy"; read back to the start: src "p"."""
    class R:
        PAID = {KA: {"st": "ok", "file": "roi_%s_p.json.gz" % KA}}
        PAID_DIR = str(tmp_path / "scr")
    os.makedirs(R.PAID_DIR)
    open(os.path.join(R.PAID_DIR, "roi_%s_p.json.gz" % KA), "wb").close()
    data = str(tmp_path / "data")
    assert be._source(KA, R, data) == ("a", {"st": "off"})
    os.makedirs(os.path.join(data, "ga4_nvr_paid"))
    st = os.path.join(data, "ga4_nvr_paid", KA + ".json.gz")
    open(st, "wb").close()
    assert be._source(KA, R, data) == ("a", {"st": "off"})                       # (an empty file: nothing read)
    day = {"2030-03-01": {"c": [["n", "AA", 1.0, 100]]}}
    for body, want in (({"v": 1, "days": day, "backfill": {"done": True}}, ("a", {"st": "off"})),    # another version
                       ({"v": 2, "days": {}, "backfill": {"done": True}}, ("a", {"st": "off"})),     # nothing in it
                       ({"v": 2, "days": day}, ("a", {"st": "busy"})),                              # no backfill yet
                       ({"v": 2, "days": day, "backfill": {"oldest": "2030-03-01"}}, ("a", {"st": "busy"})),
                       ({"v": 2, "days": day, "backfill": {"oldest": "2030-01-01", "done": True}},
                        ("p", (R.PAID_DIR, "roi_%s_p.json.gz" % KA)))):
        _wr(st, body)
        assert be._source(KA, R, data) == want, body
    os.remove(os.path.join(R.PAID_DIR, "roi_%s_p.json.gz" % KA))
    assert be._source(KA, R, data) == ("x", {"st": "fail"})                     # (its file gone: said)
    R.PAID = {KA: {"st": "ok", "file": "../roi_%s_p.json.gz" % KA}}             # (only its own name, never a path)
    assert be._source(KA, R, data)[0] == "x"
    for e, pw in (({"st": "busy", "from": "x", "next": "y", "at": "z"}, {"st": "busy", "from": "x", "next": "y"}),
                  ({"st": "none"}, {"st": "none"}), ({"st": "fail"}, {"st": "fail"}), (None, {"st": "off"}),
                  ("junk", {"st": "off"})):
        R.PAID = {KA: e} if e is not None else {}
        assert be._source(KA, R, data) == ("a", pw)


def test_a_source_that_cannot_be_told_costs_only_that_app(tmp_path, monkeypatch):
    """Telling an app's source raises (fetch.ga4_nvr_paid cannot load — say a repo variable its import reads that is no
    number): that app goes on as every user's ("fail": counted, its health line); every other app's file, and the tab,
    stand."""
    site, data, dash, scr = paid_world(tmp_path)
    _state(monkeypatch, scr)

    def boom():
        raise ValueError("x")
    monkeypatch.setattr(be, "_nvp", boom)
    paths, line, err = _go(dash, data, site, {"be_paid": True})
    assert paths == ["/be_*"] and set(dash["be"]["apps"]) == {T.APPS["a"], T.APPS["b"], T.APPS["c"], AD}
    assert _be(site, KA)["src"] == "a" and _be(site, KA)["pw"] == {"st": "fail"}
    assert _be(site, KB)["pw"]["st"] == "busy" and _be(site, KD)["pw"] == {"st": "none"}
    assert err == "be paid skipped: ValueError\n"
    assert line.endswith(", src p 0 a 4, calib p no, org 0, org fail 0, paid failed 1")
    health.FAULTS.clear()
    try:
        health.scan(err.strip())
        assert health.FAULTS == {"be paid": "ValueError"}
    finally:
        health.FAULTS.clear()


def test_src_a_is_the_file_without_the_switch_plus_src_and_pw(tmp_path, monkeypatch):
    """Every app src "a" (a's pass "ok" but its file gone, b busy, c failed, d no entry): every file the one the step
    makes without the switch + "src": "a" and "pw"; the caches, the pointer and the line as without it (+ its clause)."""
    site, data, dash = T.make(tmp_path / "off")
    p0, l0, e0 = _go(dash, data, site, {})
    f0, c0 = {k: _be(site, k) for k in (KA, KB, KC)}, _snap(site, data)
    site, data, d2 = T.make(tmp_path / "on")
    empty = tmp_path / "empty"
    empty.mkdir()
    _state(monkeypatch, str(empty), **{KC: {"st": "fail"}, KD: None})
    p1, l1, e1 = _go(d2, data, site, {"be_paid": True})
    assert p1 == p0 and e0 == ""
    assert e1 == "be paid skipped: FileNotFoundError\n"                     # (a's file gone: said, never silent)
    pw = {KA: {"st": "fail"}, KB: {"st": "busy", "from": "2030-01-01", "next": "2031-02-01"}, KC: {"st": "fail"}}
    for k in (KA, KB, KC):
        assert _be(site, k) == dict(f0[k], src="a", pw=pw[k])
    drop = lambda p: {a: {f: v for f, v in e.items() if f != "v"} for a, e in p["apps"].items()}   # noqa: E731
    assert drop(d2["be"]) == drop(dash["be"]) and {f: v for f, v in d2["be"].items() if f != "apps"} == \
        {f: v for f, v in dash["be"].items() if f != "apps"}
    for app, e in d2["be"]["apps"].items():                                 # ("v": its own file's content)
        with open(os.path.join(site, e["file"]), "rb") as f:
            assert e["v"] == hashlib.sha1(gzip.decompress(f.read())).hexdigest()[:12]
    c1 = _snap(site, data)
    cache = lambda c: {f: v for f, v in c.items() if f.startswith("cache/") and f != "cache/calib.json"}   # noqa: E731
    assert cache(c1) == cache(c0)
    ca1, ca0 = json.loads(c1["cache/calib.json"]), json.loads(c0["cache/calib.json"])
    assert ca1.pop("bp") == 1 and ca1 == ca0                                  # (made with the switch on: stamped)
    assert l1 == l0 + ", src p 0 a 3, calib p no, org 0, org fail 0, paid failed 1"


def test_src_p_reads_the_google_ads_users_rows_packs_and_first_session_store(paid):
    on, off = paid["on"], paid["off"]
    p, a = _be(on["site"], KA), _be(off["site"], KA)
    assert [d["d"] for d in p["days"]] == [d["d"] for d in a["days"]]        # the same install days, spend, installs
    n = 0
    for dp, da in zip(p["days"], a["days"]):
        assert (dp["sp"], dp["inst"], dp["age"]) == (da["sp"], da["inst"], da["age"])
        for vp, va in zip(dp["real"], da["real"]):                            # ROAS: the Google Ads users' revenue only
            assert (vp is None) == (va is None) and (vp is None or abs(vp - FR * va) <= 2e-4), (dp["d"], vp, va)
        ep = {x[0]: x[3] for x in dp["cty"]}
        for x in da["cty"]:                                                   # eCPM_fs: fetch.ga4_nvr_paid's store
            if x[0] in ep:
                n += 1
                assert abs(ep[x[0]] - 1.2 * x[3]) <= 0.002, (dp["d"], x[0])
    assert n > 100
    assert p["grid"] == a["grid"] and set(p) == set(a) | {"src"}


def test_load_takes_admob_and_the_gaps_reference_from_the_all_users_file(tmp_path, monkeypatch):
    life = [[(T.TODAY - timedelta(days=i)).isoformat(), 100.0 + i, 0.0, 0.0] for i in range(5)]
    site, data, dash, scr = paid_world(tmp_path, twin=False, life=life)
    seen = {}
    real = be.pack_gaps_p

    def spy(S_ref, S_cty, newest, fthru=None, ref_newest=None):
        seen.update(S_ref=dict(S_ref), S_cty=dict(S_cty), newest=newest, fthru=fthru, ref=ref_newest)
        return real(S_ref, S_cty, newest, fthru, ref_newest)
    monkeypatch.setattr(be, "pack_gaps_p", spy)
    monkeypatch.setattr(be, "pack_gaps", lambda *a, **k: 1 / 0)             # (never every user's rule on src "p")
    pf = (scr, "roi_%s_p.json.gz" % KA)
    newest, app, cty, adm, gaps = be.load(site, data, KA, "roi_%s.json.gz" % KA, True, pf)
    assert newest == TD and adm == {date.fromisoformat(d).toordinal(): v for d, v, _, _ in life}   # AdMob: every user's
    assert seen["newest"] == T.TODAY.toordinal() and seen["fthru"] == T.TODAY.toordinal()      # the paid file's edge
    assert seen["ref"] == T.TODAY.toordinal()                                 # (every user's file's newest day)
    S = {}
    for r in _rd(os.path.join(site, "roi_%s.json.gz" % KA))["rows"]:
        be._fday(S, r)
    assert seen["S_ref"] == S and sum(S.values()) > 0                         # every user's All rows (an independent
    pb = _rd(os.path.join(scr, pf[1]))                                        # read) against …
    S2 = {}
    for rows in _rd(os.path.join(scr, pb["packs"][0][0]))["c"].values():
        for r in rows:
            be._fday(S2, r)
    assert seen["S_cty"] == S2 and gaps == set()                              # … the paid packs' (no gap here)
    x = {r.day: r for r in app}[T.TODAY.isoformat()]
    assert x.n == sum(int(r[1] * FU) for rows in _rd(os.path.join(site, "roi_%s_c00.json.gz" % KA))["c"].values()
                      for r in rows if r[0] == TD)
    _, app_a, _ = be.load(site, data, KA, "roi_%s.json.gz" % KA)             # (every user's, the same file)
    assert {r.day: r.n for r in app_a}[TD] > x.n


def test_a_paid_cube_date_folded_near_empty_marks_the_card(tmp_path, monkeypatch):
    """The paid cube folds an activity date D near-empty (3 % of it): their All row and their packs are ONE read — both
    sink, their ratio stays, so the src "a" rule (packs against All rows) sees nothing; held against every user's All
    rows (an independent read) D is a pack gap, and each card day whose window [X, X + day] holds D is "data check"
    (chk 1) — no other point."""
    D = T.TODAY - timedelta(days=40)
    site, data, dash, scr = paid_world(tmp_path / "fold", fold=(D, 0.03))
    _state(monkeypatch, scr)
    _, line, err = _go(dash, data, site, {"be_paid": True})
    a = _be(site, KA)
    assert a["src"] == "p" and err == ""
    pf = (scr, "roi_%s_p.json.gz" % KA)
    assert be.load(site, data, KA, "roi_%s.json.gz" % KA, True, pf)[4] == {D.toordinal()}
    pb = _rd(os.path.join(scr, pf[1]))
    S_all, S_cty = {}, {}
    for r in pb["rows"]:
        be._fday(S_all, r)
    for rows in _rd(os.path.join(scr, pb["packs"][0][0]))["c"].values():
        for r in rows:
            be._fday(S_cty, r)
    assert S_cty[D.toordinal()] < 0.05 * S_cty[D.toordinal() - 1]             # (the date folded near-empty …)
    assert be.pack_gaps(S_all, S_cty, T.TODAY.toordinal(), T.TODAY.toordinal()) == set()     # (… blind on one read)
    n = 0
    for x in a["days"]:
        if not x.get("card"):
            continue
        X = date.fromisoformat(x["d"])
        want = [1 if X <= D <= X + timedelta(days=be.GRID[j]) else 0 for j in be.CARD_J]
        assert x["card"]["chk"] == want, x["d"]
        n += sum(want)
    assert n > 20
    site, data, dash, scr = paid_world(tmp_path / "whole")                    # nothing folded: no gap, no "data check"
    _state(monkeypatch, scr)
    _go(dash, data, site, {"be_paid": True})
    days = [x for x in _be(site, KA)["days"] if x.get("card")]
    assert len(days) > 100 and not any(any(x["card"]["chk"]) for x in days)


def test_the_paid_pack_gaps_follow_the_apps_own_share(tmp_path):
    """pack_gaps_p by hand: the Google Ads users' packs carry 20 % of every user's revenue a date (an app's own level) —
    a date at 5 % is a gap, one at 10 % is not (≥ 0.35 × 20 %); a gap never sets the baseline after it (three in a row
    stay gaps); under 3 dates before: no claim; a date the packs usually carry < 1 USD of: no claim; past the edges
    (newest − CLAG, the packs' fthru, every user's newest − CLAG): no claim."""
    S_ref = {D: 100.0 for D in range(1, 41)}
    S_cty = {D: 20.0 for D in S_ref}
    S_cty.update({2: 1.0, 20: 5.0, 21: 10.0, 30: 1.0, 31: 1.0, 32: 1.0})
    assert be.pack_gaps_p(S_ref, S_cty, 50) == {20, 30, 31, 32}               # (2: only one date before it)
    assert be.pack_gaps_p(S_ref, S_cty, 50, 31) == {20, 30, 31}               # (the packs folded through 31)
    assert be.pack_gaps_p(S_ref, S_cty, 50, None, 35) == {20, 30, 31}         # (every user's read final through 31)
    assert be.pack_gaps_p(S_ref, S_cty, 34) == {20, 30}                       # (newest 34: through 30)
    small = {D: 4.0 for D in S_ref}                                           # 20 % of 4 USD = 0.8 USD a date: noise
    assert be.pack_gaps_p(small, {D: v * 0.2 for D, v in small.items()} | {20: 0.0}, 50) == set()
    assert be.pack_gaps_p(S_ref, {D: 0.0 for D in S_ref}, 50) == set()       # (a share of 0: nothing to lose)


# ── the caches and the calibration: one set per source ─────────────────────────────────────────────────────────────

def test_caches_per_source_never_mix(tmp_path, monkeypatch):
    site, data, dash, scr = paid_world(tmp_path)
    _state(monkeypatch, scr)
    _go(copy.deepcopy(dash), data, site, {"be_paid": True})
    cache = os.path.join(data, "be_tab")
    assert sorted(os.listdir(cache)) == sorted(["calib.json", "calib_p.json", "fitsp_%s.json.gz" % KA] +
                                               ["fits_%s.json.gz" % k for k in (KB, KC, KD)])
    with open(os.path.join(cache, "calib_p.json"), encoding="utf-8") as f:
        cp = json.load(f)
    with open(os.path.join(cache, "calib.json"), encoding="utf-8") as f:
        ca = json.load(f)
    assert set(cp["skill"]) == {KA} and set(ca["skill"]) == {KB, KC, KD}      # each from its own source's apps only
    assert cp["cv"] == ca["cv"] == be.CALV and cp["built"] == ca["built"] == TD
    first, a1 = _snap(site, data), _be(site, KA)
    _go(copy.deepcopy(dash), data, site, {})                                  # the same day, the switch off: app a
    assert os.path.exists(os.path.join(cache, "fits_%s.json.gz" % KA))         # refits from its own (every user's) cache
    after = _snap(site, data)
    for f in ("cache/calib_p.json", "cache/fitsp_%s.json.gz" % KA):
        assert after[f] == first[f]                                           # (the other source's left alone)
    assert "src" not in _be(site, KA) and after["cache/calib.json"] != first["cache/calib.json"]   # (made again: below)
    calls = {}
    real = be.fit

    def spy(app, cty, O):
        calls["fit"] = calls.get("fit", 0) + 1
        return real(app, cty, O)
    monkeypatch.setattr(be, "fit", spy)
    _go(copy.deepcopy(dash), data, site, {"be_paid": True})                   # back to src "p": its own cache again
    assert calls == {} and _be(site, KA) == a1


def test_switch_off_the_same_utc_day_answers_every_app_as_a_build_that_never_had_it(tmp_path, monkeypatch):
    """BE_PAID on at the day's first build (app a src "p": calib.json made from b, c and d only — stamped "bp"), then off
    the same UTC day (a rollback): calib.json made again at once from every app (no stamp, no growth bound of the
    switch-on one), app a keeps its skill ("kitna pakka"), and every file and cache of every user's is exactly a build's
    that never had the switch on; back on the same day: made again from the src "a" apps, stamped."""
    site0, data0, dash0, _ = paid_world(tmp_path / "never")
    _go(copy.deepcopy(dash0), data0, site0, {})
    _go(copy.deepcopy(dash0), data0, site0, {}, T.NOW + timedelta(hours=2))
    never = _snap(site0, data0)
    site, data, dash, scr = paid_world(tmp_path / "rollback")
    _state(monkeypatch, scr)
    cpath = os.path.join(data, "be_tab", "calib.json")
    _go(copy.deepcopy(dash), data, site, {"be_paid": True})
    with open(cpath, encoding="utf-8") as f:
        ca = json.load(f)
    assert ca["bp"] == 1 and set(ca["skill"]) == {KB, KC, KD}
    calls = []
    real = be.calibrate

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(be, "calibrate", spy)
    _, line, err = _go(copy.deepcopy(dash), data, site, {}, T.NOW + timedelta(hours=2))
    assert len(calls) == 1 and err == "" and ", calib yes" in line
    with open(cpath, encoding="utf-8") as f:
        ca = json.load(f)
    assert "bp" not in ca and set(ca["skill"]) == {KA, KB, KC, KD}
    assert _be(site, KA)["skill"] == _be(site0, KA)["skill"] and _be(site, KA)["skill"]["n"] > 0
    now = _snap(site, data)
    assert {f: v for f, v in now.items() if f not in ("cache/calib_p.json", "cache/fitsp_%s.json.gz" % KA)} == never
    _, line, err = _go(copy.deepcopy(dash), data, site, {"be_paid": True}, T.NOW + timedelta(hours=4))
    assert len(calls) == 2 and err == ""                                      # (its src "a" one again; calib_p: kept)
    with open(cpath, encoding="utf-8") as f:
        ca = json.load(f)
    assert ca["bp"] == 1 and set(ca["skill"]) == {KB, KC, KD} and _be(site, KA)["src"] == "p"


def test_each_calibration_once_a_utc_day_and_none_for_a_source_without_an_app(tmp_path, monkeypatch):
    site, data, dash, scr = paid_world(tmp_path)
    _state(monkeypatch, scr)
    calls = []
    real = be.calibrate

    def spy(*a, **k):
        calls.append(1)
        return real(*a, **k)
    monkeypatch.setattr(be, "calibrate", spy)
    _, line, _ = _go(copy.deepcopy(dash), data, site, {"be_paid": True})
    assert len(calls) == 2 and "calib yes" in line and "calib p yes" in line
    first = _snap(site, data)
    _, line, _ = _go(copy.deepcopy(dash), data, site, {"be_paid": True}, T.NOW + timedelta(hours=5))
    assert len(calls) == 2 and "calib no" in line and "calib p no" in line and _snap(site, data) == first
    with open(os.path.join(data, "be_tab", "calib_p.json"), "rb") as f:
        cp = f.read()
    monkeypatch.setattr(rb, "PAID", {})                                       # the next day no app is src "p":
    _, line, _ = _go(copy.deepcopy(dash), data, site, {"be_paid": True}, T.NOW + timedelta(days=1))
    assert len(calls) == 3 and ", src p 0 a 4, calib p no" in line            # only every user's calibration made
    with open(os.path.join(data, "be_tab", "calib_p.json"), "rb") as f:
        assert f.read() == cp                                                 # (not even "tried")
    _state(monkeypatch, scr)
    _, line, _ = _go(copy.deepcopy(dash), data, site, {"be_paid": True}, T.NOW + timedelta(days=1, hours=2))
    assert len(calls) == 4 and "calib no" in line and "calib p yes" in line   # its day's own, once it has an app
    with open(os.path.join(data, "be_tab", "calib_p.json"), encoding="utf-8") as f:
        assert json.load(f)["built"] == (T.TODAY + timedelta(days=1)).isoformat()


def test_ecs_beside_the_ecpm_card_on_src_p_days_only(tmp_path, monkeypatch):
    site, data, dash, scr = paid_world(tmp_path)
    for k in (KA, KD):
        TE.write_store(data, k)                                               # every user's returning-eCPM reads
    _state(monkeypatch, scr)
    _, line, err = _go(dash, data, site, dict(TE.ON, be_paid=True))
    assert err == "" and ", ecpm apps 2, ecpm failed 0" in line
    a, d = _be(site, KA), _be(site, KD)
    with_ec = [x for x in a["days"] if "ec" in x]
    assert with_ec and all(x["ecs"] == "a" for x in with_ec)                  # src "p": its card's read is every user's
    assert not any("ecs" in x for x in a["days"] if "ec" not in x)
    assert any("ec" in x for x in d["days"]) and not any("ecs" in x for x in d["days"])     # src "a": nothing said


def test_the_counts_line_names_nothing(paid):
    on, off = paid["on"], paid["off"]
    nd = sum(len(_be(on["site"], k)["days"]) for k in (KA, KB, KC, KD))
    assert on["line"].startswith("be: apps 4, days %d, covered " % nd)
    assert on["line"].endswith(", refit yes, calib yes, src p 1 a 3, calib p yes, org 1, org fail 0"), on["line"]
    assert ", src" not in off["line"] and off["line"].endswith(", refit yes, calib yes")
    for bad in [AD, KD, "2030", "2031", "$", "AA", "EE"] + list(T.APPS.values()) + list(T.KEYS.values()):
        assert bad not in on["line"]


# ── the pointer, the Organic file's shape on the made-up world ─────────────────────────────────────────────────────

def test_the_pointer_names_the_organic_file_and_its_version_covers_both(paid):
    on = paid["on"]
    ptr = on["dash"]["be"]["apps"]
    org = "be_%s_o.json.gz" % KA
    assert ptr[T.APPS["a"]]["org"] == org and not any("org" in v for k, v in ptr.items() if k != T.APPS["a"])
    with open(os.path.join(on["site"], "be_%s.json.gz" % KA), "rb") as f:
        raw = gzip.decompress(f.read())
    with open(os.path.join(on["site"], org), "rb") as f:
        oraw = gzip.decompress(f.read())
    assert ptr[T.APPS["a"]]["v"] == hashlib.sha1(raw + hashlib.sha1(oraw).digest()).hexdigest()[:12]
    for k, app in ((KB, T.APPS["b"]), (KD, AD)):
        with open(os.path.join(on["site"], "be_%s.json.gz" % k), "rb") as f:
            assert ptr[app]["v"] == hashlib.sha1(gzip.decompress(f.read())).hexdigest()[:12]
    from admob_iq import build_static as bs
    from admob_iq.deploy_guard import headers_cover
    text = bs.headers_text(["uninstall.json.gz"], on["dash"], extra=on["paths"])
    assert be.HEADER_PATHS == ["/be_*"] and headers_cover(text, org)          # (the one splat rule covers it)


def test_the_organic_file_on_the_made_up_world(paid):
    on = paid["on"]
    o = _rd(os.path.join(on["site"], "be_%s_o.json.gz" % KA))
    assert set(o) == {"v", "key", "origin", "ages", "days"} and (o["v"], o["key"], o["origin"]) == (1, KA, TD)
    assert o["ages"] == list(be.GRID)                                         # (its oldest day lived every column)
    days = o["days"]
    assert [x["d"] for x in days] == sorted(x["d"] for x in days) and len(days) == T.NDAYS
    pk = _rd(os.path.join(on["site"], "roi_%s_c00.json.gz" % KA))["c"]
    for x in days[::37]:
        assert set(x) == {"d", "age", "n", "r", "pu", "fin", "s"} and set(x["s"]) == {"pu", "b", "cv"}
        rows = {cc: {r[0]: r for r in rs}[x["d"]] for cc, rs in pk.items() if cc != "XX"}   # ("XX": Google Ads cost only)
        assert x["n"] == sum(r[1] - int(r[1] * FU) for r in rows.values())              # organic users, every country
        assert x["age"] == (T.TODAY - date.fromisoformat(x["d"])).days
        assert not any(r[12] & 16 for cc, r in rows.items() if cc not in be.SKIP_CC)    # (named rows: own k_c — "--"
        for i, v in enumerate(x["r"]):                                        # users counted, their revenue once: in
            g = be.GRID[i]                                                    # the named countries' k_c)
            want = sum(be._fin(r)[i] - be._fin(_scale(r))[i] for cc, r in rows.items() if cc not in be.SKIP_CC)
            assert v == pytest.approx(want, abs=1e-3) and x["pu"][i] == pytest.approx(v / x["n"], abs=1e-6)
            assert x["fin"][i] == (1 if g <= x["age"] - be.CLAG else 0)
        assert len(x["r"]) == sum(1 for g in be.GRID if g <= x["age"])        # (every lived cell final here)


# ── 🌱 the Organic file, worked by hand ────────────────────────────────────────────────────────────────────────────
OKEY = "0123456789ab"                        # a made-up app key
HO = date(2031, 2, 28)                       # the build's day = both cubes' newest day, read through it …
HF = HO - timedelta(days=3)                  # … and folded (final) through this one
DAYS = [date(2031, 1, 1) + timedelta(days=i) for i in range((HO - date(2031, 1, 1)).days + 1)]
ALL = {"AA": (100, 0.5), "BB": (50, 0.4), "--": (10, 0.06), "CC": (5, 0.05)}   # users, USD a day at every age
GADS = {"AA": (40, 0.2), "BB": (10, 0.1), "--": (4, 0.03)}     # … of the Google Ads users (CC: none, never in their pack)
LO = [g for g in be.GRID if g <= 30]


def feb(d):
    return date(2031, 2, d)


def _hrow(X, n, usd, bump=None, thru=HO, fthru=HF, bits=16):
    """roi_build's row of install day X: n users, usd of revenue every day of age 0 … as cumulative cells read through
    `thru`, final through `fthru` (bump: {age: + USD on the cumulative cells from that age on}); bits: its ≈ bits (16:
    a month of its revenue on the app's k — the default here; 0: every month on its own / pooled k_c)."""
    obs = min(30, (thru - X).days)
    d = [round(usd * (a + 1) + sum(v for b, v in (bump or {}).items() if a >= b), 4) for a in range(obs + 1)]
    return [X.isoformat(), n, None, 0.0, d, max(0, min(obs, (fthru - X).days) + 1), None, [None] * len(be.T), d[-1],
            (X + timedelta(days=obs)).isoformat(), None, "N/A", bits, None]


def _xx(X):
    """A "Not split" row (Google Ads' cost with no country: no user, no revenue cell)."""
    return [X.isoformat(), None, None, 1.0, None, 0, None, [None] * len(be.T), None, None, None, "N/A", 0, 1.0]


def _pair(tmp, a, p, key=OKEY, thru=HO, fthru=HF, ng=None):
    """The all-users pack (+ its ROI file's "cd" edges; ng: {month: "own" | "app"} — roi_build's verdicts per activity
    month, "ng" "m") in tmp/site and the Google Ads users' pack (+ their file) in tmp/scr, as roi_build writes them →
    (site, the ROI file's name, (scratch folder, the paid file's name))."""
    site, scr = tmp / "site", tmp / "scr"
    site.mkdir(parents=True)
    scr.mkdir(parents=True)
    for folder, tag, c in ((site, "c", a), (scr, "p", p)):
        name = "roi_%s_%s00.json.gz" % (key, tag)
        raw = _raw({"v": 1, "b": "hb", "key": key, "ix": 0, "c": c})
        with open(os.path.join(str(folder), name), "wb") as f:
            f.write(gzip.compress(raw, mtime=0))
        edges = {"packs": [[name, hashlib.sha1(raw).hexdigest()[:12]]], "thru": thru.isoformat(),
                 "fthru": fthru.isoformat(), "newest": thru.isoformat()}
        if tag == "c":
            if ng:
                edges["ng"] = {"m": {M: [0.0, 0.0, v] for M, v in ng.items()}}
            _wr(os.path.join(str(folder), "roi_%s.json.gz" % key), {"v": 1, "key": key, "rows": [], "cd": edges})
        else:
            _wr(os.path.join(str(folder), "roi_%s_p.json.gz" % key), dict(edges, v=1, key=key, b="hb", rows=[]))
    return str(site), "roi_%s.json.gz" % key, (str(scr), "roi_%s_p.json.gz" % key)


def hand_world(tmp):
    """One made-up app: every install day 1 Jan … 28 Feb of ALL / GADS, "XX" on both sides, and these days:
      20 Feb  AA's Google Ads users earned 0.1 USD a day, not 0.2 (AA's organic 0.4 a day: above its benchmark)
      10 Feb  60 Google Ads users of BB against its 50 users (a drift: BB left out — its organic users unknown)
      12 Feb  AA's Google Ads users' cells from age 3 on 0.01 USD above its users' (a drift: AA left out, 60 users)
      14 Feb  DD: one Google Ads user the all-users read never named (a drift)
      24 Feb  the "--" Google Ads users' row written [X] (none: every "--" user that day organic)
      25 Feb  80 of AA's 100 users Google Ads ones (its organic 20: the benchmark's weights move)
      27 Feb  55 Google Ads users of BB against its 50 users — a day not folded yet (26 … 28 Feb: both reads hot, made
              at different times): never a drift, its users not final."""
    a = {cc: [_hrow(X, n, usd) for X in DAYS] for cc, (n, usd) in ALL.items()}
    p = {cc: [] for cc in GADS}
    for X in DAYS:
        for cc, (n, usd) in GADS.items():
            if (X, cc) == (feb(20), "AA"):
                r = _hrow(X, n, 0.1)
            elif (X, cc) == (feb(25), "AA"):
                r = _hrow(X, 80, usd)
            elif (X, cc) == (feb(10), "BB"):
                r = _hrow(X, 60, usd)
            elif (X, cc) == (feb(12), "AA"):
                r = _hrow(X, n, usd, {3: 1.21})            # (age 3: 0.8 + 1.21 = 2.01 against 2.0)
            elif (X, cc) == (feb(24), "--"):
                r = [X.isoformat()]
            elif (X, cc) == (feb(27), "BB"):
                r = _hrow(X, 55, usd)
            else:
                r = _hrow(X, n, usd)
            p[cc].append(r)
    p["DD"] = [_hrow(feb(14), 1, 0.0)]
    a["XX"] = [_xx(X) for X in DAYS]
    p["XX"] = [_xx(X) for X in DAYS]
    return _pair(tmp, a, p)


def _lin(k, n):
    """k × day for the first n card ages (day = age + 1)."""
    return [k * (g + 1) for g in LO[:n]]


def _close(got, want, tol=1e-6):
    return len(got) == len(want) and all(abs(x - y) <= tol for x, y in zip(got, want))


def test_the_organic_file_worked_by_hand(tmp_path):
    site, fn, pf = hand_world(tmp_path)
    o = be.organic(site, OKEY, fn, pf, HO.toordinal())
    assert (o["v"], o["key"], o["origin"]) == (1, OKEY, HO.isoformat())
    assert o["ages"] == LO                               # (the oldest day is 58 days old: no 30-day column lived)
    by = {x["d"]: x for x in o["days"]}
    assert [x["d"] for x in o["days"]] == [X.isoformat() for X in DAYS]          # every day, oldest first
    # an ordinary old day: AA 60 + BB 40 + "--" 6 + CC 5 = 111 organic users; organic revenue a day AA 0.3, BB 0.3,
    # "--" 0.03, CC 0.05 = 0.68 USD; final at every card age (10 Jan + 30 ≤ 25 Feb), 4 days old by then
    x = by["2031-01-10"]
    assert x["age"] == 49 and x["n"] == 111 and "dr" not in x
    assert _close(x["r"], _lin(0.68, 7), 1e-4) and _close(x["pu"], [v / 111 for v in _lin(0.68, 7)])
    assert x["fin"] == [1] * 7
    # the benchmark: AA's own settled days (1 … 29 Jan, 60 organic users each): 0.3 ÷ 60 = 0.005 a user a day, BB's
    # 0.3 ÷ 40 = 0.0075 — joined by the day's organic users share over the two (60 : 40) = 0.006; the day's own per user
    # over the same two = 0.6 ÷ 100 = 0.006; "--" and CC (5 organic users: no benchmark) are the rest: cv = 100 ÷ 111
    assert _close(x["s"]["b"], _lin(0.006, 7)) and _close(x["s"]["pu"], _lin(0.006, 7))
    assert x["s"]["cv"] == [round(100 / 111, 4)] * 7
    # 22 Feb (6 days old): lived ages 0 … 6; final through 25 Feb = age 3; age 3 only 3 days old: not final for fin
    x = by["2031-02-22"]
    assert x["age"] == 6 and _close(x["r"], _lin(0.68, 4), 1e-4) and x["fin"] == [1, 1, 1, 0]
    assert _close(x["s"]["pu"], _lin(0.006, 4)) and _close(x["s"]["b"], _lin(0.006, 6))   # (the benchmark ahead:
    assert x["s"]["cv"] == [round(100 / 111, 4)] * 6                                        # the card days 1 … 14)
    # 20 Feb: AA's organic 0.4 a day → the day 0.78; the benchmark countries' own per user 0.7 ÷ 100 against 0.006
    x = by["2031-02-20"]
    assert x["n"] == 111 and _close(x["r"], _lin(0.78, 4), 1e-4) and x["fin"] == [1, 1, 1, 1]
    assert _close(x["s"]["pu"], _lin(0.007, 4)) and _close(x["s"]["b"], _lin(0.006, 6))
    # 10 Feb: BB left out (more Google Ads users than users: two reads apart) — counted, never clamped
    x = by["2031-02-10"]
    assert x["dr"] == [1, 0] and x["n"] == 60 + 6 + 5 and _close(x["r"], _lin(0.38, 6), 1e-4)
    assert x["fin"] == [1] * 6 and _close(x["s"]["b"], _lin(0.005, 6)) and _close(x["s"]["pu"], _lin(0.005, 6))
    assert x["s"]["cv"] == [round(60 / 71, 4)] * 6                          # (the set: AA alone)
    # 12 Feb: AA's cell at age 3 above its users' by 0.01 USD — AA out of every number that day (its 60 users counted)
    x = by["2031-02-12"]
    assert x["dr"] == [1, 60] and x["n"] == 40 + 6 + 5 and _close(x["r"], _lin(0.38, 6), 1e-4)
    assert x["fin"] == [1, 1, 1, 1, 1, 0] and _close(x["s"]["pu"], _lin(0.0075, 6)) and _close(x["s"]["b"], _lin(0.0075, 6))
    assert x["s"]["cv"] == [round(40 / 51, 4)] * 6
    # 14 Feb: DD, named by the Google Ads users' read only — out, counted; the day otherwise ordinary
    x = by["2031-02-14"]
    assert x["dr"] == [1, 0] and x["n"] == 111 and _close(x["r"], _lin(0.68, 5), 1e-4) and x["fin"] == [1] * 5
    # 25 Feb: AA's organic users 20 → the weights 20 : 40 → benchmark (20 × 0.005 + 40 × 0.0075) ÷ 60 a day; the same
    # two countries' own per user (0.3 + 0.3) ÷ 60; its age 0 final (folded through 25 Feb) but not 4 days old: fin 0
    x = by["2031-02-25"]
    assert x["n"] == 20 + 40 + 6 + 5 and _close(x["r"], [0.68], 1e-4) and x["fin"] == [0]
    assert _close(x["s"]["pu"], [0.01]) and _close(x["s"]["b"], _lin(0.4 / 60, 6))
    assert x["s"]["cv"] == [round(60 / 71, 4)] * 6
    # 24 Feb: "--" [X] on the Google Ads side = none of them: its 10 users organic, its 0.06 USD a day too; final
    # through 25 Feb (ages 0 and 1), age 0 four days old
    x = by["2031-02-24"]
    assert x["n"] == 60 + 40 + 10 + 5 and _close(x["r"], _lin(0.71, 2), 1e-4) and x["fin"] == [1, 0]
    assert _close(x["s"]["pu"], _lin(0.006, 2)) and _close(x["s"]["b"], _lin(0.006, 6))
    assert x["s"]["cv"] == [round(100 / 115, 4)] * 6
    # 26 … 28 Feb: day 0 not folded by both cubes — their users are two hot reads made at different times: no organic
    # count ("n" null: not final), no benchmark set, no drift test (27 Feb: BB's 55 Google Ads users against its 50)
    for d in (26, 27, 28):
        x = by[feb(d).isoformat()]
        assert x["age"] == 28 - d and x["n"] is None and "dr" not in x, x
        assert x["r"] == x["pu"] == x["fin"] == [] and x["s"] == {"pu": [], "b": [], "cv": []}
    assert sum(1 for x in o["days"] if "dr" in x) == 3                      # (only those three)


def test_the_benchmark_needs_20_settled_days_with_30_organic_users(tmp_path):
    """BB with 29 organic users a day never has a benchmark; AA's only from install days settled at the build's day
    (X + 30 ≤ O): with 19 of them, none — every user is "data kam" (no set)."""
    days = DAYS[-49:]                                       # 11 Jan … 28 Feb: 19 days settled at 28 Feb (11 … 29 Jan)
    a = {"AA": [_hrow(X, 100, 0.5) for X in days], "BB": [_hrow(X, 39, 0.4) for X in days]}
    p = {"AA": [_hrow(X, 40, 0.2) for X in days], "BB": [_hrow(X, 10, 0.1) for X in days]}
    site, fn, pf = _pair(tmp_path / "a", a, p)
    o = be.organic(site, OKEY, fn, pf, HO.toordinal())
    assert all(x["s"] == {"pu": [], "b": [], "cv": []} for x in o["days"])
    site, fn, pf = _pair(tmp_path / "b", dict(a, AA=[_hrow(X, 100, 0.5) for X in DAYS]),
                         dict(p, AA=[_hrow(X, 40, 0.2) for X in DAYS]))   # AA from 1 Jan: 29 settled days
    o = be.organic(site, OKEY, fn, pf, HO.toordinal())
    x = {x["d"]: x for x in o["days"]}["2031-02-01"]
    assert _close(x["s"]["b"], _lin(0.005, 6)) and x["s"]["cv"] == [round(60 / 89, 4)] * 6   # AA alone: BB 29 users
    o2 = be.organic(site, OKEY, fn, pf, (HO - timedelta(days=10)).toordinal())  # ten days earlier: 19 settled
    assert all(x["s"]["b"] == [] for x in o2["days"])


def test_a_drift_is_more_than_the_rounding_never_less(tmp_path):
    """A cell the Google Ads side holds one unit of the 4th decimal above the all-users one is rounding (organic 0 there);
    two units are a drift (the country-day left out, counted); so are more Google Ads users than users."""
    X0, X1, X2 = feb(1), feb(2), feb(3)
    a = {"AA": [_hrow(X, 100, 0.5) for X in (X0, X1, X2)]}
    p = {"AA": [_hrow(X0, 30, 0.5, {0: 0.0001}), _hrow(X1, 30, 0.5, {0: 0.0002}), _hrow(X2, 101, 0.2)]}
    site, fn, pf = _pair(tmp_path, a, p)
    o = {x["d"]: x for x in be.organic(site, OKEY, fn, pf, HO.toordinal())["days"]}
    x = o[X0.isoformat()]
    assert "dr" not in x and x["n"] == 70 and x["r"][0] == 0.0 and all(v == 0.0 for v in x["r"])   # never negative
    assert o[X1.isoformat()]["dr"] == [1, 70] and o[X1.isoformat()]["n"] == 0 and o[X1.isoformat()]["r"] == []
    assert o[X2.isoformat()]["dr"] == [1, 0] and o[X2.isoformat()]["n"] == 0
    assert be._otol(0, 0.5) < 2e-4 and be._otol(0, 0.5) > 1e-4 and be._otol(360, 0.5) > be._otol(0, 0.5)


def _mrow(X, n, d30, m):
    """A row with its 30-day columns, every cell final: the daily cells 0 … 29 at 1.0 USD, day 30 at d30, the columns m
    (day 60, 90 …) as written — round(round(cum30, 4) + their buckets, 4): rounded twice."""
    d = [1.0] * 30 + [d30]
    return [X.isoformat(), n, None, 0.0, d, 31, None, [None] * len(be.T), m[-1],
            (X + timedelta(days=30 * (len(m) + 1))).isoformat(), None, "N/A", 16, None, list(m), len(m)]


def test_a_30_day_column_carries_two_rounding_units(tmp_path):
    """Two reads 4 micros apart (every user's day 30 1.234549 + a bucket 0.000049, the Google Ads users' 1.234551 +
    0.000051) are written 1.2345 / 1.2346 at day 30 and 1.2345 / 1.2347 at days 60 and 90 (rounded twice): rounding,
    never drift (organic 0 there); three units at day 60 are drift, so are two units on the once-rounded day 30."""
    X0, X1, X2 = date(2030, 11, 1), date(2030, 11, 2), date(2030, 11, 3)
    a = {"AA": [_mrow(X, 8, 1.2345, [1.2345, 1.2345]) for X in (X0, X1, X2)]}
    p = {"AA": [_mrow(X0, 5, 1.2346, [1.2347, 1.2347]), _mrow(X1, 5, 1.2346, [1.2348, 1.2348]),
                _mrow(X2, 5, 1.2347, [1.2347, 1.2347])]}
    site, fn, pf = _pair(tmp_path, a, p)
    o = be.organic(site, OKEY, fn, pf, HO.toordinal())
    assert o["ages"] == LO + [60, 90]
    x = {x["d"]: x for x in o["days"]}
    assert "dr" not in x[X0.isoformat()] and x[X0.isoformat()]["n"] == 3 and x[X0.isoformat()]["r"] == [0.0] * 9
    assert x[X1.isoformat()]["dr"] == [1, 3] and x[X1.isoformat()]["n"] == 0                # (3 units at day 60)
    assert x[X2.isoformat()]["dr"] == [1, 3] and x[X2.isoformat()]["r"] == []               # (2 units at day 30)
    assert be._otol(30, 1.2347) < 2e-4 < be._otol(60, 1.2347) < be._otol(90, 1.2347) < 3e-4


def test_not_set_revenue_counts_once_by_roi_builds_month_verdicts(tmp_path):
    """With roi_build's verdict per activity month (cd "ng" "m": January "own" — most of its named revenue on own /
    pooled k_c —, February "app"): each step of the "--" revenue between two card ages whose days all lie in January is
    left out (AdMob booked those users under their countries: inside the named k_c), every other step kept — a step
    across both months kept whole (its split is not measured); the users always counted. The named rows' bits (16 off
    here) no longer decide: 5 Feb keeps its "--" revenue."""
    X1, X2, X3 = date(2031, 1, 10), date(2031, 1, 27), date(2031, 2, 5)
    a = {"AA": [_hrow(x, 100, 0.5, bits=0) for x in (X1, X2, X3)], "--": [_hrow(x, 10, 0.06) for x in (X1, X2, X3)]}
    p = {"AA": [_hrow(x, 40, 0.2, bits=0) for x in (X1, X2, X3)], "--": [_hrow(x, 4, 0.03) for x in (X1, X2, X3)]}
    site, fn, pf = _pair(tmp_path, a, p, ng={"2031-01": "own", "2031-02": "app"})
    o = {x["d"]: x for x in be.organic(site, OKEY, fn, pf, HO.toordinal())["days"]}
    aa, ns = (lambda g: 0.3 * (g + 1)), (lambda g: 0.03 * (g + 1))     # AA's / "--"'s organic through age g
    want = {X1: [aa(g) + (0.0 if g <= 13 else ns(g) - ns(13)) for g in LO],     # 10 Jan: 0 … 13 January (out); the
            #                                                                     step to 30 (24 Jan … 9 Feb): across
            X2: [aa(g) + (0.0 if g <= 3 else ns(g) - ns(3)) for g in LO],       # 27 Jan: 0 … 3 out; 6 (31 Jan … 2
            #                                                                     Feb) across, 13 and 30 February: kept
            X3: [aa(g) + ns(g) for g in LO]}                                     # 5 Feb: February, kept
    for x, w in want.items():
        e = o[x.isoformat()]
        assert e["n"] == 60 + 6 and len(e["r"]) == (7 if x == X1 else 6) and _close(e["r"], w[:len(e["r"])], 1e-4), \
            (x, e["r"])
    assert be._once(X1.toordinal(), [0.0] * 6 + [None] * 7, set()) == [0.0] * 6 + [None] * 7      # (no own month)


def test_not_set_revenue_counts_once_without_month_verdicts(tmp_path):
    """A file without roi_build's month verdicts: the day's named rows decide — "--" / "ZZ" (GA4: no country) users are
    organic users every day, but their revenue joins the day's line only where its named rows are mostly on the app's k
    (bit 16, weighted by their revenue so far): on their own / pooled k_c AdMob already booked those users under their
    real countries (roi_build: the "--" row's revenue is inside the named countries' k_c) — counted twice otherwise. AA
    earns five times BB here."""
    X = [feb(d) for d in (1, 2, 3, 4)]
    bits = {feb(1): (0, 0), feb(2): (16, 16), feb(3): (0, 16), feb(4): (16, 0)}     # AA's, BB's
    a = {"AA": [_hrow(x, 100, 0.5, bits=bits[x][0]) for x in X], "BB": [_hrow(x, 50, 0.1, bits=bits[x][1]) for x in X],
         "--": [_hrow(x, 10, 0.06) for x in X], "ZZ": [_hrow(x, 4, 0.02) for x in X]}
    p = {"AA": [_hrow(x, 40, 0.2, bits=bits[x][0]) for x in X], "BB": [_hrow(x, 10, 0.05, bits=bits[x][1]) for x in X],
         "--": [_hrow(x, 4, 0.03) for x in X]}
    site, fn, pf = _pair(tmp_path, a, p)
    o = {x["d"]: x for x in be.organic(site, OKEY, fn, pf, HO.toordinal())["days"]}
    for x, own in ((feb(1), True), (feb(2), False), (feb(3), True), (feb(4), False)):
        e = o[x.isoformat()]
        per = 0.3 + 0.05 + (0.0 if own else 0.03 + 0.02)           # named organic a day (+ "--" 0.03 and "ZZ" 0.02)
        assert e["n"] == 60 + 40 + 6 + 4 and _close(e["r"], _lin(per, 6), 1e-4), (x, e["r"])
        assert _close(e["pu"], [v / 110 for v in _lin(per, 6)], 2e-6) and e["fin"] == [1] * 6


def test_a_google_ads_users_x_row_on_an_unknown_spend_day_has_no_spend(tmp_path):
    """roi_build's Google Ads users' file lists the days its [X] rows' spend is unknown ("unk": inclusive ranges) and
    "billed": such a row expands with spend null (a known day: 0, "--": null; not billed: no billed spend); a file of the
    format before it as before (null); the cells — all the Organic pass reads — the same either way."""
    site, fn, pf = _pair(tmp_path, {"AA": [_hrow(feb(1), 10, 0.1)]}, {"AA": [[feb(1).isoformat()]]})
    oi = be._org_in(site, fn, pf)
    assert oi.unk is None and be._xrow(oi, "p", feb(4).toordinal(), "AA")[3] is None     # (before "unk": as before)
    cells = be._fin(be._xrow(oi, "p", feb(4).toordinal(), "AA"))
    pb = _rd(os.path.join(pf[0], pf[1]))
    pb.update(unk=[["2031-02-02", "2031-02-03"], ["2031-02-20", "2031-02-20"]], billed=True)
    _wr(os.path.join(pf[0], pf[1]), pb)
    oi = be._org_in(site, fn, pf)
    assert oi.unk == {feb(d).toordinal() for d in (2, 3, 20)}
    for d, cc, sp in ((2, "AA", None), (3, "AA", None), (20, "AA", None), (4, "AA", 0.0), (4, "--", None)):
        r = be._xrow(oi, "p", feb(d).toordinal(), cc)
        assert (r[3], r[13], r[1]) == (sp, sp, 0), (d, cc, r)
    assert be._fin(be._xrow(oi, "p", feb(4).toordinal(), "AA")) == cells
    pb["billed"] = False
    _wr(os.path.join(pf[0], pf[1]), pb)
    r = be._xrow(be._org_in(site, fn, pf), "p", feb(4).toordinal(), "AA")
    assert (r[3], r[13]) == (0.0, None)
    assert be.organic(site, OKEY, fn, pf, HO.toordinal()) is not None
    assert be._xrow(oi, "a", feb(4).toordinal(), "AA")[3] is None            # (every user's side: as before)


def test_a_day_one_cube_has_not_read_has_no_organic_number(tmp_path):
    """The Google Ads users' cube read through 26 Feb, the all-users one through 28 Feb: 27 / 28 Feb are not in the file
    (no organic number without both reads); the ages count from the older newest day; finality is each cube's own."""
    pt, pft = feb(26), feb(22)
    a = {"AA": [_hrow(X, 100, 0.5) for X in DAYS]}
    p = {"AA": [_hrow(X, 40, 0.2, thru=pt, fthru=pft) for X in DAYS if X <= pt]}
    site, fn, pf = _pair(tmp_path, a, p)
    pb = _rd(os.path.join(pf[0], pf[1]))
    pb.update(thru=pt.isoformat(), fthru=pft.isoformat(), newest=pt.isoformat())
    _wr(os.path.join(pf[0], pf[1]), pb)
    o = be.organic(site, OKEY, fn, pf, HO.toordinal())
    assert o["days"][-1]["d"] == "2031-02-26" and o["days"][-1]["age"] == 0
    x = {x["d"]: x for x in o["days"]}["2031-02-20"]
    assert x["age"] == 6 and _close(x["r"], _lin(0.3, 3), 1e-4)            # final through 22 Feb on the paid side
    assert x["fin"] == [1, 1, 1]                                            # (22 Feb: 4 days before the older newest)
    x = {x["d"]: x for x in o["days"]}["2031-02-21"]
    assert _close(x["r"], _lin(0.3, 2), 1e-4) and x["fin"] == [1, 1]        # (age 2 = 23 Feb: not folded on that side)


def test_nothing_to_subtract_is_no_file(tmp_path):
    site, fn, pf = _pair(tmp_path, {"AA": [_hrow(feb(1), 10, 0.1)]}, {"AA": [_hrow(feb(1), 10, 0.1)]})
    assert be.organic(site, OKEY, fn, pf, HO.toordinal()) is None          # every user a Google Ads one
    roi = _rd(os.path.join(site, fn))
    roi["cd"] = {}                                                          # no country part: nothing to subtract from
    _wr(os.path.join(site, fn), roi)
    assert be.organic(site, OKEY, fn, pf, HO.toordinal()) is None


def test_the_organic_file_on_roi_builds_own_paid_files(tmp_path, monkeypatch):
    """roi_build's own paid pass (tests/test_roi_paid.py's world: users a day AA 40 / BB 5 / CC 3 / "--" 2, of them
    Google Ads 10 / 1 / 1 / 1; GA4 micros a day 100000 / 1000 / 20000 / 10000, of them 25000 / 1000 / 5000 / 2000; the
    AdMob scale AA 1.5 in Aug, 1.0 in Sep, the app's 1.2 in Oct; CC 3× clamped to 2.0 in Aug / Sep, 1.2 in Oct; BB and
    "--" the app's 1.2) → the Organic file from its real files: 37 organic users a day (BB 4 users, no revenue; final
    through the cubes' fold, 10 Oct — a later day's: null), the revenue a day 0.075 USD × AA's scale + 0.015 × CC's, +
    "--"'s 0.008 × 1.2 counted once — each step between two card ages left out whose days all lie in a month roi_build
    calls "own" (Aug / Sep: AdMob already booked the "--" users under their countries; October on the app's k: kept) —,
    final through the fold."""
    from tests import test_roi_paid as RP
    r = RP._run(tmp_path, monkeypatch, "on", paid={})
    assert r["paid"] == {RP.KEY: {"st": "ok", "file": "roi_%s_p.json.gz" % RP.KEY}}
    O = (RP.CTODAY + timedelta(days=1)).toordinal()
    o = be.organic(str(r["od"]), RP.KEY, "roi_%s.json.gz" % RP.KEY, (r["dir"], r["paid"][RP.KEY]["file"]), O)
    assert o["ages"] == LO + [60] and [x["d"] for x in o["days"]] == RP.DAYS and not any("dr" in x for x in o["days"])
    k = {"AA": {"2026-08": 1.5, "2026-09": 1.0, "2026-10": 1.2}, "CC": {"2026-08": 2.0, "2026-09": 2.0, "2026-10": 1.2}}
    fold, newest = date(2026, 10, 10), RP.CTODAY
    ng = {M: v[2] for M, v in json.loads(r["body"])["cd"]["ng"]["m"].items()}      # roi_build's verdicts per month
    assert ng == {"2026-08": "own", "2026-09": "own", "2026-10": "app"}

    def ns(X, g):                                           # "--"'s organic revenue through age g, counted once: a
        tot, last = 0.0, -1                                 # step of card ages whose days are all in own months out
        for a in be.GRID:
            if a > g:
                break
            days = [X + timedelta(days=L) for L in range(last + 1, a + 1)]
            if not all(ng.get(d.isoformat()[:7]) == "own" for d in days):
                tot += 0.008 * 1.2 * len(days)
            last = a
        return tot

    def cum(X, a, cc):                                      # organic revenue of install day X through age a
        per = {"AA": 0.075, "CC": 0.015}[cc]
        return sum(per * k[cc][(X + timedelta(days=L)).isoformat()[:7]] for L in range(a + 1))
    aa = {}
    for x in o["days"]:
        X = date.fromisoformat(x["d"])
        assert x["n"] == (37 if X <= fold else None) and x["age"] == (newest - X).days
        assert len(x["r"]) == sum(1 for g in o["ages"] if X + timedelta(days=g) <= fold)   # (every final age, no more)
        for i, v in enumerate(x["r"]):
            g = be.GRID[i]
            want = None if X + timedelta(days=g) > fold else cum(X, g, "AA") + cum(X, g, "CC") + ns(X, g)
            assert (v is None) == (want is None) and (v is None or abs(v - want) <= 5e-4), (x["d"], g, v, want)
            assert x["fin"][i] == (1 if want is not None and X + timedelta(days=g) <= newest - timedelta(days=be.CLAG)
                                   else 0)
        if X + timedelta(days=30) <= date.fromordinal(O):
            aa[X] = x
    # the benchmark: AA alone (30 organic users; BB 4, CC 2, "--" 1: none) — its settled days' median per user
    for i, g in enumerate(LO):
        vals = sorted(cum(X, g, "AA") / 30 for X in aa if X + timedelta(days=g) <= fold)
        med = (vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2)
        for x in o["days"][::9]:
            if (g <= 13 or g <= x["age"]) and date.fromisoformat(x["d"]) <= fold:
                assert abs(x["s"]["b"][i] - med) <= 2e-5 and x["s"]["cv"][i] == round(30 / 37, 4), (x["d"], g)


# ── failure isolation, the clean-up ─────────────────────────────────────────────────────────────────────────────────

def test_an_organic_failure_costs_only_the_organic_file(tmp_path, monkeypatch):
    site, data, dash, scr = paid_world(tmp_path, twin=True)
    _state(monkeypatch, scr)
    monkeypatch.setattr(be, "organic", lambda *a, **k: 1 / 0)
    paths, line, err = _go(dash, data, site, {"be_paid": True})
    assert paths == ["/be_*"] and _be(site, KA)["src"] == "p"                 # the Google Ads users' file stands
    assert "org" not in dash["be"]["apps"][T.APPS["a"]] and not os.path.exists(os.path.join(site, "be_%s_o.json.gz" % KA))
    assert line.endswith(", src p 1 a 3, calib p yes, org 0, org fail 1") and ", failed" not in line
    assert err == "be organic skipped: ZeroDivisionError\n"
    health.FAULTS.clear()
    try:
        health.scan(err.strip())
        assert health.FAULTS == {"be organic": "ZeroDivisionError"}          # the health banner names it
    finally:
        health.FAULTS.clear()


def test_a_failing_google_ads_source_goes_on_as_every_users(tmp_path, monkeypatch):
    # its pack unreadable: app a every user's this build, said and counted; nothing of the Organic file
    site, data, dash, scr = paid_world(tmp_path / "pack")
    os.remove(os.path.join(scr, "roi_%s_p00.json.gz" % KA))
    _state(monkeypatch, scr)
    paths, line, err = _go(dash, data, site, {"be_paid": True})
    a = _be(site, KA)
    assert a["src"] == "a" and a["pw"] == {"st": "fail"} and err == "be paid skipped: FileNotFoundError\n"
    assert line.endswith(", src p 0 a 4, calib p no, org 0, org fail 0, paid failed 1")
    assert not [f for f in os.listdir(site) if f.endswith("_o.json.gz")]
    # no Google Ads users' calibration yet and its first one failing: its app goes on as every user's ("cal"), the
    # every-user calibration made with it
    site, data, dash, scr = paid_world(tmp_path / "cal")
    _state(monkeypatch, scr)
    real, calls = be.calibrate, []

    def first_fails(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("x")
        return real(*a, **k)
    monkeypatch.setattr(be, "calibrate", first_fails)
    paths, line, err = _go(dash, data, site, {"be_paid": True})
    assert len(calls) == 2 and err == "be paid skipped: ValueError\n"
    assert _be(site, KA)["pw"] == {"st": "cal"} and not os.path.exists(os.path.join(data, "be_tab", "calib_p.json"))
    with open(os.path.join(data, "be_tab", "calib.json"), encoding="utf-8") as f:
        assert set(json.load(f)["skill"]) == {KA, KB, KC, KD}
    assert line.endswith(", calib yes, src p 0 a 4, calib p no, org 0, org fail 0, paid failed 1")
    assert "org" not in dash["be"]["apps"][T.APPS["a"]] and not os.path.exists(os.path.join(site, "be_%s_o.json.gz" % KA))
    # … and with be_paid on, no every-user calibration yet and its first one failing costs only its apps
    site, data, dash, scr = paid_world(tmp_path / "acal")
    _state(monkeypatch, scr)
    calls.clear()

    def second_fails(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise KeyError("x")
        return real(*a, **k)
    monkeypatch.setattr(be, "calibrate", second_fails)
    paths, line, err = _go(dash, data, site, {"be_paid": True})
    assert paths == ["/be_*"] and set(dash["be"]["apps"]) == {T.APPS["a"]} and err == "be skipped: KeyError\n"
    assert dash["be"]["apps"][T.APPS["a"]]["org"] == "be_%s_o.json.gz" % KA
    assert sorted(f for f in os.listdir(site) if f.startswith("be_")) == ["be_%s.json.gz" % KA, "be_%s_o.json.gz" % KA]
    assert line.startswith("be: apps 1, ") and ", failed 3, src p 1 a 0, calib p yes, org 1, org fail 0" in line


def test_too_few_google_ads_users_days_for_a_first_calibration_is_a_state_not_a_failure(tmp_path, monkeypatch):
    """No Google Ads users' calibration yet and their back-test with no covered country (too few of their breakeven
    days): never a failure — no health line, nothing counted as failed, a stub calib_p.json (no maps: load_calib refuses
    it), the app every user's ("cal"), no Organic pass; the same UTC day with the same apps nothing of them is read or
    tried again (no paid load, no back-test); with a new app among them, or the next UTC day: tried again."""
    site, data, dash, scr = paid_world(tmp_path)
    _state(monkeypatch, scr)
    thin, seen = {"on": True}, {"bt": [], "load": [], "org": 0}
    real_bt, real_load, real_org = be.backtest, be.load, be.organic

    def bt(key, *a, **k):
        seen["bt"].append(key)
        return ([], []) if key == KA and thin["on"] else real_bt(key, *a, **k)

    def ld(out_dir, data_dir, key, fn, *a):
        if len(a) > 1 and a[1] is not None:
            seen["load"].append(key)                                          # (a Google Ads users' load)
        return real_load(out_dir, data_dir, key, fn, *a)

    def og(*a, **k):
        seen["org"] += 1
        return real_org(*a, **k)
    monkeypatch.setattr(be, "backtest", bt)
    monkeypatch.setattr(be, "load", ld)
    monkeypatch.setattr(be, "organic", og)
    cp = os.path.join(data, "be_tab", "calib_p.json")

    def build(at):
        seen.update(bt=[], load=[], org=0)
        return _go(copy.deepcopy(dash), data, site, {"be_paid": True}, at)
    _, line, err = build(T.NOW)
    assert err == "" and line.endswith(", src p 0 a 4, calib p no, org 0, org fail 0")      # (no "paid failed")
    assert _be(site, KA)["src"] == "a" and _be(site, KA)["pw"] == {"st": "cal"}
    assert seen["load"] == [KA] and KA in seen["bt"] and seen["org"] == 0
    with open(cp, encoding="utf-8") as f:
        assert json.load(f) == {"v": 1, "tried": TD, "apps": [KA]}
    assert be.load_calib(data, "p") is None and not [f for f in os.listdir(site) if f.endswith("_o.json.gz")]
    _, line, err = build(T.NOW + timedelta(hours=3))                          # the same day, the same apps: nothing
    assert err == "" and seen == {"bt": [], "load": [], "org": 0} and _be(site, KA)["pw"] == {"st": "cal"}
    assert line.endswith(", src p 0 a 4, calib p no, org 0, org fail 0")
    with open(cp, encoding="utf-8") as f:
        stub = json.load(f)
    with open(cp, "w", encoding="utf-8") as f:                                # a new app among them: tried again
        json.dump(dict(stub, apps=["0" * 12]), f)
    _, line, err = build(T.NOW + timedelta(hours=4))
    assert err == "" and seen["load"] == [KA] and seen["bt"] == [KA] and seen["org"] == 0
    thin["on"] = False                                                        # the next UTC day, enough of their days
    _, line, err = build(T.NOW + timedelta(days=1))
    assert err == "" and seen["load"] == [KA] and seen["org"] == 1 and ", calib p yes, org 1" in line
    assert _be(site, KA)["src"] == "p" and be.load_calib(data, "p")["built"] == (T.TODAY + timedelta(days=1)).isoformat()
    assert os.path.exists(os.path.join(site, "be_%s_o.json.gz" % KA))


def test_each_paid_pack_read_once_a_build_and_the_organic_pass_only_after_its_file(tmp_path, monkeypatch):
    """Each Google Ads users' pack is read ONCE a build (load() collects the Organic pass's cells), and so is each file
    of the app — on the day's calibration build (the app held for it) and on one answered from the caches; the Organic
    pass runs only once the app's src "p" file exists: that file failing (predict raising there), no Organic pass."""
    from collections import Counter
    site, data, dash, scr = paid_world(tmp_path)
    _state(monkeypatch, scr)
    reads, real_read = Counter(), be._read

    def rd(path):
        reads[os.path.basename(path)] += 1
        return real_read(path)
    monkeypatch.setattr(be, "_read", rd)
    for at in (T.NOW, T.NOW + timedelta(hours=2)):
        reads.clear()
        _, line, err = _go(copy.deepcopy(dash), data, site, {"be_paid": True}, at)
        assert err == "" and _be(site, KA)["src"] == "p" and ", org 1, org fail 0" in line
        for f in ("roi_%s_p00.json.gz", "roi_%s_p.json.gz", "roi_%s.json.gz", "roi_%s_c00.json.gz"):
            assert reads[f % KA] == 1, (at, f, reads[f % KA])                 # (paid pack / file: load; every user's
    org = os.path.join(site, "be_%s_o.json.gz" % KA)                          # file: load; its packs: the Organic pass)
    assert os.path.exists(org)
    calls, real_pred, real_org = {"pred": 0, "org": 0}, be.predict, be.organic

    def pred(key, *a, **k):
        if key == KA and not calls["pred"]:
            calls["pred"] += 1
            raise ValueError("x")                                             # (its src "p" file fails, once)
        return real_pred(key, *a, **k)

    def og(*a, **k):
        calls["org"] += 1
        return real_org(*a, **k)
    monkeypatch.setattr(be, "predict", pred)
    monkeypatch.setattr(be, "organic", og)
    _, line, err = _go(copy.deepcopy(dash), data, site, {"be_paid": True}, T.NOW + timedelta(hours=3))
    assert calls == {"pred": 1, "org": 0} and err == "be paid skipped: ValueError\n"
    assert _be(site, KA)["src"] == "a" and _be(site, KA)["pw"] == {"st": "fail"} and not os.path.exists(org)


def test_the_organic_pass_is_its_own_stage_of_the_tab(tmp_path, monkeypatch):
    """⏱ The build's stage clock (measure only) times the Organic pass as its own child of the tab — "be_organic", summed
    over the src "p" apps — so its share of be_tab's time shows; the switch off: no such row, nothing else changed."""
    from admob_iq import stage_clock as sc
    assert sc.STAGES[sc.STAGES.index("be_tab") + 1] == "be_organic"
    site, data, dash, scr = paid_world(tmp_path)
    _state(monkeypatch, scr)
    got = {}
    for name, s in (("on", {"be_paid": True}), ("off", {})):
        sc.begin()
        try:
            with sc.stage("be_tab"):
                err = _go(copy.deepcopy(dash), data, site, s)[2]
        finally:
            prof = sc.finish(None)
        assert err == ""
        got[name] = {(e.get("parent"), e["name"]): e.get("n", 1) for e in prof["stages"]}
    assert got == {"on": {(None, "be_tab"): 1, ("be_tab", "be_organic"): 1}, "off": {(None, "be_tab"): 1}}


def test_stale_organic_files_go(tmp_path, monkeypatch):
    site, data, dash, scr = paid_world(tmp_path)
    _state(monkeypatch, scr)
    stray = os.path.join(site, "be_%s_o.json.gz" % ("f" * 12))
    open(stray, "wb").close()
    _go(copy.deepcopy(dash), data, site, {"be_paid": True})
    org = os.path.join(site, "be_%s_o.json.gz" % KA)
    assert os.path.exists(org) and not os.path.exists(stray)                  # (an app with none: removed)
    d2 = copy.deepcopy(dash)
    _go(d2, data, site, {})                                                   # the switch off: no Organic file at all
    assert not os.path.exists(org) and "org" not in d2["be"]["apps"][T.APPS["a"]]
    _go(copy.deepcopy(dash), data, site, {"be_paid": True})
    assert os.path.exists(org)
    monkeypatch.setattr(rb, "PAID", {})                                       # app a every user's again: its file goes
    _go(copy.deepcopy(dash), data, site, {"be_paid": True})
    assert not os.path.exists(org)
    _state(monkeypatch, scr)
    _go(copy.deepcopy(dash), data, site, {"be_paid": True})
    assert os.path.exists(org)
    be.off(site)                                                              # the tab off: every file of it
    assert not [f for f in os.listdir(site) if f.startswith("be_")]
