"""🗂 Review Studio — the build step (admob_iq.review_studio_build + its build_static wiring), on the Daily App Review's
synthetic site (tests/review_studio_synth.py: tests/review_synth.py + icons, cohort files, an Active users file; the day's
cards frozen by the real review store). No real data.

  * the contract: the file (v1) belongs to ONE frozen card (day + card_built_at), every app and feature of the card is
    in it, the extras (14-day revenue pinned to the card's Yesterday, weekly same-day uninstall with not-final flags,
    returning users with their final day, every mediation network's share, icons by app id, late_days), the key numbers,
    the rate lines' actual count and total, the first-seen time; the pointer in review/index.json; byte-for-byte publish;
  * the owner's wording: never "100 me" / "per 1,000" / "/din"; "Same day uninstall"; the actual number first;
  * frozen: a later build keeps the file (the site's newer data never changes the reviewed card's Studio); a rebuilt
    card gets a new one;
  * failure isolation: a broken app is left out (counted); a broken extra costs only that chart; any other failure: no
    file, no pointer, the error TYPE only — every other output as without the Studio;
  * the switch (REVIEW_STUDIO=false) and the build wiring (only after this build's review step; the _headers bytes as
    with the review step alone);
  * the public log: ONE counts-only line."""

import contextlib
import gzip
import io
import json
import os
import re
import shutil
from datetime import date, timedelta

import pytest

from admob_iq import build_static
from admob_iq import review_studio_build as rsb
from admob_iq.config import settings
from admob_iq.review.store import review_run
from tests import review_studio_synth as ss
from tests import review_synth as rs

DAY, DS = rs.DAY, rs.DAY.isoformat()
LINE = re.compile(r"^Review Studio: day \d{4}-\d{2}-\d{2} · (built|kept) \(apps \d+, skipped \d+\) · kb \d+"
                  r" · past days \d+ \(kb \d+, skipped \d+\)$")
SECRETS = ([rs.A[i] for i in rs.A] + [rs.K[i] for i in rs.A] + list(rs.STORE.values()) + list(rs.PKG.values())
           + [rs.PUB, rs.PUB2, "Synth", "example", "$", "₹"])
FIDS = ["kamai", "uninstall", "active", "value", "update", "ads", "deduct", "mediation", "health", "setup"]
BANNED = ("100 me", "per 1,000", "har 1,000", "Har 1,000", "1,000 users", "1,000 ads", "/din")


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("rstudio"))
    return ss.make(root)


@pytest.fixture
def site(base, tmp_path):
    """A fresh copy of the module's frozen synthetic site → (site, data, dashboard)."""
    s0, d0, dash = base
    s, d = str(tmp_path / "site"), str(tmp_path / "data")
    shutil.copytree(s0, s)
    shutil.copytree(d0, d)
    return s, d, json.loads(json.dumps(dash))


def _gz(p):
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def _raw(p):
    with open(p, "rb") as f:
        return f.read()


def _step(site, data, dash, ran=True, **kw):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        paths = build_static._review_studio_step(dash, data, site, dict(settings(), **kw), ran=ran, now=rs.NOW)
    return paths, [x for x in err.getvalue().splitlines() if x]


def _file(site):
    return os.path.join(site, "review", "studio", f"{DS}.json.gz")


def _idx(site):
    with open(os.path.join(site, "review", "index.json"), encoding="utf-8") as f:
        return json.load(f)


def _doc(data):
    return _gz(os.path.join(data, "review", "days", f"{DS}.json.gz"))


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, list):
        for x in o:
            yield from _strings(x)
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)


# ── the contract ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_contract_one_file_for_the_frozen_card_and_its_pointer(site):
    s, d, dash = site
    paths, err = _step(s, d, dash)
    assert paths == ["/review/*"] and len(err) == 1 and LINE.match(err[0]) and " built (apps 7, skipped 0)" in err[0]
    body, doc = _gz(_file(s)), _doc(d)
    assert set(body) == {"v", "day", "card_built_at", "built_at", "meta", "feats", "apps"}
    assert body["v"] == rsb.V and body["day"] == DS and body["card_built_at"] == doc["built_at"]
    assert [f[0] for f in body["feats"]] == FIDS
    assert [f[1] for f in body["feats"]] == ["Revenue · eCPM", "Uninstall", "Active users", "Install value",
                                             "Update impact", "Ads", "Deductions", "Mediation", "Account health",
                                             "Setup / data"]
    M = body["meta"]
    assert M["day"] == DS and M["wday"] == "Thursday" and M["built_ist"] == "09:47" and M["fx"] == rs.FX
    assert M["admob_till"] == doc["data"]["admob_till"] and len(M["d14"]) == 14 and M["d14"][-1] == M["admob_till"]
    assert M["counts"] == doc["counts"] and M["usual"] == doc["data"]["usual"]
    # every app and every feature of the card — nothing dropped, in the card's order
    order = doc["order"]["top"] + doc["order"]["ok"] + doc["order"]["small"]
    assert [a["key"] for a in body["apps"]] == order and len(order) == len(doc["apps"]) == 7
    A = {a["key"]: a for a in body["apps"]}
    for a in doc["apps"]:
        x = A[a["key"]]
        assert x["id"] == a["app_id"] and x["acct"] == a["acct"] and x["size"] == a["size"] and x["tier"] == a["tier"]
        assert x["nb"] == a["nb"] and x["y"] == a["y"] and x["us"] == a["us"] and x["k7"] == a["k7"]
        assert set(x["f"]) == set(FIDS)
        for f in FIDS:
            assert x["f"][f]["st"] == a["f"][f]["st"]                        # the card's status, never changed
            assert ("q" in x["f"][f]) == bool(a["f"][f].get("q"))
        assert len(x["ser"]) == 14 and x["ser"][-1] == round(a["y"], 4)      # Yesterday = the card's number
        assert x["late_days"] == (7 if a["key"] != rs.K[8] else 0)
    # the pointer names this file for this card, and the site copy is a byte copy of the kept one
    ptr = _idx(s)["studio"]
    assert ptr == {DS: {"file": f"review/studio/{DS}.json.gz", "v": ptr[DS]["v"], "card": doc["built_at"]}}
    assert re.fullmatch(r"[0-9a-f]{12}", ptr[DS]["v"])
    assert _raw(_file(s)) == _raw(os.path.join(d, "review", "studio", f"{DS}.json.gz"))


def test_the_extras_the_card_lacks(site):
    s, d, dash = site
    _step(s, d, dash)
    A = {a["key"]: a for a in _gz(_file(s))["apps"]}
    # icons by app id (only https), none for an app without one
    assert A[rs.K[1]]["icon"] == ss.ICON[1] and A[rs.K[8]]["icon"] is None
    # the weekly same-day uninstall: 8 install weeks ending on the card's GA4 day, the late weeks not final
    un = A[rs.K[3]]["x"]["un"]
    ga4 = DAY - timedelta(3)
    assert un["late"] == 7 and len(un["wk"]) == 8 and un["wk"][-1]["t"] == ga4.isoformat()
    assert all(w["n"] == 700 for w in un["wk"]) and [w["prov"] for w in un["wk"]] == [False] * 7 + [True]
    assert un["wk"][-1]["s"] == 210 and un["wk"][0]["s"] == 140                 # 30 / 20 of every 100 installs
    # the rate line: the actual count first, the % beside it, and its structured count / total
    u3 = A[rs.K[3]]["f"]["uninstall"]
    assert u3["line"] == "Same day uninstall 210 of 700 (30%) · was 20%" == u3["q"]["kya"]
    assert u3["rate"] == {"c": 210, "n": 700, "p": 30.0, "was": 20.0} and u3["k"] == "30%"
    u1 = A[rs.K[1]]["f"]["uninstall"]                                       # a normal line: the window's count
    assert u1["line"].startswith("Same day uninstall 140 of 700 installs (20%) · installs ")
    assert u1["rate"] == {"c": 140, "n": 700, "p": 20.0, "was": None}
    # returning users: 42 days ending on the card's GA4 day, final till the app's settled day
    ret = A[rs.K[4]]["x"]["ret"]
    assert len(ret["v"]) == len(ret["d"]) == 42 and ret["d"][-1] == ga4.isoformat()
    assert ret["final"] == (ga4 - timedelta(3)).isoformat() and all(isinstance(v, int) for v in ret["v"])
    # mediation: every network's share of the card's 7 days, with the revenue and fill
    med = A[rs.K[4]]["x"]["med"]
    assert [m["n"] for m in med] == ["Synth Network One", "Synth Network Two"]
    assert [m["s"] for m in med] == [66.7, 33.3] and [m["usd"] for m in med] == [2100.0, 1050.0]
    assert [m["f"] for m in med] == [85.7, 80.0] and [m["p"] for m in med] == [66.7, 33.3]
    # key numbers of the map's cells; the first time each issue was shown (a card's build time)
    assert A[rs.K[2]]["f"]["deduct"]["k"] == "4×" and A[rs.K[1]]["f"]["kamai"]["k"] == "−38%"
    assert A[rs.K[1]]["f"]["kamai"]["first"] == {"d": DS, "at": _doc(d)["built_at"], "why": "first card"}
    assert A[rs.K[3]]["f"]["uninstall"]["first"]["at"] is None                # an alert's own date: no time known
    for a in A.values():
        for f in FIDS:
            x = a["f"][f]
            if x["st"] in ("red", "amber"):
                assert x["k"] and x["age"] and x["first"] and "since" in x and "prov" in x


def test_the_owners_wording_everywhere(site):
    s, d, dash = site
    _step(s, d, dash)
    body = _gz(_file(s))
    text = list(_strings(body))
    for t in text:
        for b in BANNED:
            assert b not in t, (b, t)
    for a in body["apps"]:
        for f in FIDS:
            x = a["f"][f]
            for seg in (x["line"] if isinstance(x["line"], list) else []):
                if isinstance(seg, dict):
                    assert seg.get("s") in ("", "/day") and set(seg) <= {"usd", "s", "sign", "p"}
    assert any(t.startswith("Same day uninstall") for t in text)
    assert not any(re.search(r"[Ii]nstall ke din (hi )?hataane", t) for t in text)
    A = {a["key"]: a for a in body["apps"]}
    assert A[rs.K[6]]["f"]["uninstall"]["line"] == "Uninstall rate +50%"
    assert A[rs.K[5]]["f"]["update"]["line"] == "✅ v1.0.8 went well"
    assert A[rs.K[5]]["f"]["kamai"]["line"][0] == "Revenue +38%: "


def test_counts_that_do_not_give_the_cards_percent_are_not_shown(site):
    s, d, dash = site
    with gzip.open(os.path.join(s, f"uninstall_c_{rs.K[1]}.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(ss.cohort(DAY, 25, 40, 25), f)
    _step(s, d, dash)
    u1 = next(a for a in _gz(_file(s))["apps"] if a["key"] == rs.K[1])["f"]["uninstall"]
    assert u1["line"].startswith("Same day uninstall: 20% (installs ") and "rate" not in u1


def test_frozen_with_the_card_and_rebuilt_with_it(site):
    s, d, dash = site
    _step(s, d, dash)
    b1, i1 = _raw(_file(s)), _raw(os.path.join(s, "review", "index.json"))
    # newer site data (a later hourly build) never changes the reviewed card's Studio
    p = os.path.join(s, f"uninstall_c_{rs.K[3]}.json.gz")
    with gzip.open(p, "wt", encoding="utf-8") as f:
        json.dump(ss.cohort(DAY, 50, 23, 60), f)
    paths, err = _step(s, d, dash)
    assert paths == ["/review/*"] and " kept (apps 7, skipped 0)" in err[0]
    assert _raw(_file(s)) == b1 and _raw(os.path.join(s, "review", "index.json")) == i1
    # the review step rewrites index.json without the pointer every build; the Studio step puts it back unchanged
    idx = _idx(s)
    idx.pop("studio")
    with open(os.path.join(s, "review", "index.json"), "w", encoding="utf-8") as f:
        json.dump(idx, f)
    _step(s, d, dash)
    assert _raw(os.path.join(s, "review", "index.json")) == i1
    # a rebuilt card (REVIEW_REBUILD_DAY) gets a new Studio file, from the site as it is then
    with contextlib.redirect_stderr(io.StringIO()):
        res = review_run(None, d, s, rs.NOW + timedelta(hours=1), today=DAY,
                         env={"REVIEW_READY_IST": "09:00", "REVIEW_REBUILD_DAY": DS})
    assert res["ok"]
    paths, err = _step(s, d, dash)
    body = _gz(_file(s))
    assert " built (" in err[0] and body["card_built_at"] == _doc(d)["built_at"] != json.loads(gzip.decompress(b1))["card_built_at"]
    assert _idx(s)["studio"][DS]["card"] == body["card_built_at"]
    a3 = next(a for a in body["apps"] if a["key"] == rs.K[3])
    assert a3["x"]["un"]["wk"][-1]["s"] == 420                                  # 60 of every 100: the new data
    assert "rate" not in a3["f"]["uninstall"]          # counts that no longer give the card's own % are not shown


def _past_history(s, d, n):
    """n synthetic PAST review days before DS (go-live = the oldest), each with its own frozen card (a copy of DS's,
    its own day + build time) and its kept Studio file (a copy of DS's, that day's card) → {i: day}; the review step
    then lists them all in index.json. Day i=2: its Studio file is another card's (a rebuilt card); i=3: not gzip;
    i=4: no Studio file (before the Studio); i=5: another format; i=n+1: before go-live."""
    doc, body = _doc(d), _gz(os.path.join(d, "review", "studio", f"{DS}.json.gz"))
    days = {i: (DAY - timedelta(i)).isoformat() for i in range(1, n + 2)}
    for i, p in days.items():
        c = dict(doc, day=p, built_at=f"{p}T04:00:00Z")
        with gzip.open(os.path.join(d, "review", "days", f"{p}.json.gz"), "wt", encoding="utf-8") as f:
            json.dump(c, f)
        if i == 4:
            continue
        b = dict(body, day=p, card_built_at=c["built_at"] if i != 2 else f"{p}T01:00:00Z", meta=dict(body["meta"], day=p))
        if i == 5:
            b["v"] = rsb.V + 1
        sp = os.path.join(d, "review", "studio", f"{p}.json.gz")
        if i == 3:
            with open(sp, "wb") as f:
                f.write(b"not gzip")
        else:
            with gzip.open(sp, "wt", encoding="utf-8") as f:
                json.dump(b, f)
    mp = os.path.join(d, "review", "meta.json")
    with open(mp, encoding="utf-8") as f:
        meta = json.load(f)
    meta["go_live"] = days[n]
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    with contextlib.redirect_stderr(io.StringIO()):
        assert review_run(None, d, s, rs.NOW, today=DAY, env={"REVIEW_READY_IST": "09:00"})["ok"]
    return days


def test_every_past_days_kept_file_is_published_and_named_never_trimmed(site):
    s, d, dash = site
    _step(s, d, dash)
    ptr0 = _idx(s)["studio"][DS]
    N = 45                                                     # more past days than any "last N" cap would keep
    days = _past_history(s, d, N)
    sd = os.path.join(s, "review", "studio")
    for stale in ("2026-08-01.json.gz", f"{days[2]}.json.gz"):  # a day with no kept file, a rebuilt card's old copy
        with open(os.path.join(sd, stale), "wb") as f:
            f.write(b"old")
    kept = {p: _raw(os.path.join(d, "review", "studio", f"{p}.json.gz")) for i, p in days.items() if i != 4}
    paths, err = _step(s, d, dash)
    assert paths == ["/review/*"] and len(err) == 1 and LINE.match(err[0]), err
    good = [p for i, p in days.items() if i not in (2, 3, 4, 5, N + 1)]
    assert len(good) == N - 4 and f" past days {N - 4} (kb " in err[0] and err[0].endswith(", skipped 3)")
    idx = _idx(s)
    assert [x["d"] for x in idx["days"]] == sorted(list(days.values())[:N] + [DS])     # (go-live onwards)
    ptr = idx["studio"]
    assert sorted(ptr) == sorted(good + [DS]) and ptr[DS] == ptr0                       # the open day's: unchanged
    for p in good:
        card = _gz(os.path.join(d, "review", "days", f"{p}.json.gz"))["built_at"]
        assert ptr[p]["file"] == f"review/studio/{p}.json.gz" and ptr[p]["card"] == card
        assert re.fullmatch(r"review/studio/\d{4}-\d{2}-\d{2}\.json\.gz", ptr[p]["file"])   # (the page's own pattern)
        assert re.fullmatch(r"[0-9a-f]{12}", ptr[p]["v"])
        assert _raw(os.path.join(sd, f"{p}.json.gz")) == kept[p]                       # a byte copy of the kept file
    assert sorted(os.listdir(sd)) == sorted(f"{p}.json.gz" for p in good + [DS])       # nothing else on the site
    # exactly as built that day: the kept files are never rewritten (also not the ones left out)
    for p, raw in kept.items():
        assert _raw(os.path.join(d, "review", "studio", f"{p}.json.gz")) == raw
    # a second build changes nothing (same bytes, same index, no file rewritten)
    m0 = {n: os.stat(os.path.join(sd, n)).st_mtime_ns for n in os.listdir(sd)}
    i0 = _raw(os.path.join(s, "review", "index.json"))
    _step(s, d, dash)
    assert {n: os.stat(os.path.join(sd, n)).st_mtime_ns for n in os.listdir(sd)} == m0
    assert _raw(os.path.join(s, "review", "index.json")) == i0
    # a past day's file that becomes unusable costs only that day
    with open(os.path.join(d, "review", "studio", f"{good[0]}.json.gz"), "wb") as f:
        f.write(b"broken")
    paths, err = _step(s, d, dash)
    assert paths == ["/review/*"] and good[0] not in _idx(s)["studio"] and len(_idx(s)["studio"]) == N - 4
    assert not os.path.exists(os.path.join(sd, f"{good[0]}.json.gz")) and err[0].endswith(", skipped 4)")


# ── failure isolation ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_broken_app_is_left_out_and_counted(site, monkeypatch):
    s, d, dash = site
    real = rsb.build_app

    def boom(a, *x, **k):
        if a["key"] == rs.K[2]:
            raise KeyError(rs.STORE[2])
        return real(a, *x, **k)
    monkeypatch.setattr(rsb, "build_app", boom)
    paths, err = _step(s, d, dash)
    assert paths == ["/review/*"] and LINE.match(err[0]) and "(apps 6, skipped 1)" in err[0]
    keys = [a["key"] for a in _gz(_file(s))["apps"]]
    assert rs.K[2] not in keys and len(keys) == 6


def test_a_broken_extra_file_costs_only_its_chart(site):
    s, d, dash = site
    with open(os.path.join(s, f"uninstall_c_{rs.K[3]}.json.gz"), "wb") as f:
        f.write(b"\x1f\x8bnot gzip")
    with open(os.path.join(s, f"active_{rs.K[4]}.json.gz"), "wb") as f:
        f.write(gzip.compress(b'{"daily": {"ret": "x", "start": 5}, "data_till": "nope"}'))
    paths, err = _step(s, d, dash)
    assert "(apps 7, skipped 0)" in err[0]
    A = {a["key"]: a for a in _gz(_file(s))["apps"]}
    assert "un" not in A[rs.K[3]]["x"] and "ret" not in A[rs.K[4]]["x"] and "med" in A[rs.K[4]]["x"]
    assert A[rs.K[3]]["f"]["uninstall"]["rate"]["c"] == 210                 # still counted: from the card's own chart
    assert A[rs.K[1]]["x"]["un"]


def test_any_other_failure_leaves_no_file_no_pointer_and_only_the_error_type(site, monkeypatch):
    s, d, dash = site
    _step(s, d, dash)                                                        # an earlier good build
    review_idx = _idx(s)
    review_idx.pop("studio")
    with open(os.path.join(s, "review", "index.json"), "w", encoding="utf-8") as f:   # (as the review step writes it)
        json.dump(review_idx, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    before = _raw(os.path.join(s, "review", "index.json"))
    shutil.rmtree(os.path.join(d, "review", "studio"))

    def boom(*a, **k):
        raise RuntimeError(f"{rs.STORE[1]} {rs.A[1]} $320")
    monkeypatch.setattr(rsb, "build_data", boom)
    paths, err = _step(s, d, dash)
    assert paths == [] and err == ["Review Studio skipped: RuntimeError"]
    assert not os.path.exists(os.path.join(s, "review", "studio"))
    assert "studio" not in _idx(s) and _raw(os.path.join(s, "review", "index.json")) == before


def test_no_open_day_or_no_card_means_no_file(site):
    s, d, dash = site
    _step(s, d, dash)
    os.remove(os.path.join(d, "review", "days", f"{DS}.json.gz"))
    os.remove(os.path.join(s, "review", "days", f"{DS}.json.gz"))
    paths, err = _step(s, d, dash)
    assert paths == [] and err == [f"Review Studio: day {DS} · no card"]
    assert not os.path.exists(os.path.join(s, "review", "studio")) and "studio" not in _idx(s)
    os.remove(os.path.join(s, "review", "index.json"))
    assert _step(s, d, dash) == ([], [])


def test_the_size_cap_skips_the_whole_file(site, monkeypatch):
    s, d, dash = site
    monkeypatch.setattr(rsb, "MAX_GZ", 100)
    paths, err = _step(s, d, dash)
    assert paths == [] and re.fullmatch(rf"Review Studio: day {DS} · too big \(\d+ kb\), not written", err[0])
    assert not os.path.exists(os.path.join(s, "review", "studio")) and "studio" not in _idx(s)


# ── the switch and the build wiring ───────────────────────────────────────────────────────────────────────────────

def test_the_switch_off_removes_the_file_and_the_pointer(site, monkeypatch):
    s, d, dash = site
    _step(s, d, dash)
    monkeypatch.setenv("REVIEW_STUDIO", "false")
    assert settings()["review_studio"] is False
    monkeypatch.setenv("REVIEW_STUDIO", "true")
    assert settings()["review_studio"] is True
    paths, err = _step(s, d, dash, review_studio=False)
    assert paths == [] and err == []
    assert not os.path.exists(os.path.join(s, "review", "studio")) and "studio" not in _idx(s)
    # off without a review step: still nothing left behind, nothing printed
    assert _step(s, d, dash, ran=False, review_studio=False) == ([], [])


def test_without_this_builds_review_step_nothing_is_touched(site):
    s, d, dash = site
    snap = {n: _raw(os.path.join(dp, n)) for dp, _, fs in os.walk(s) for n in fs}
    assert _step(s, d, dash, ran=False) == ([], [])
    assert {n: _raw(os.path.join(dp, n)) for dp, _, fs in os.walk(s) for n in fs} == snap
    assert not os.path.exists(os.path.join(d, "review", "studio"))


def test_the_headers_stay_as_with_the_review_step_alone():
    dash = {"active": {}, "value": {}}
    review_only = build_static.headers_text(["uninstall.json.gz"], dash, extra=["/review/*"])
    rp, sp = ["/review/*"], ["/review/*"]
    both = build_static.headers_text(["uninstall.json.gz"], dash, extra=list(rp) + [p for p in sp if p not in rp])
    assert both == review_only and "/review/*\n  Cache-Control: no-store" in both


def test_the_build_runs_the_step_only_after_the_review_step(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(build_static, "_review_step", lambda *a, **k: [])
    monkeypatch.setattr(build_static, "_review_studio_step", lambda *a, **k: calls.append(k.get("ran")) or [])
    build_static.build(out_dir=str(tmp_path / "site"), data_dir=str(tmp_path / "data"), today=date(2026, 7, 23), mode="mock")
    assert calls == [False] and not os.path.exists(str(tmp_path / "site" / "review"))


# ── the public log ────────────────────────────────────────────────────────────────────────────────────────────────

def test_every_log_line_is_counts_only(site, monkeypatch):
    s, d, dash = site
    lines = _step(s, d, dash)[1] + _step(s, d, dash)[1]
    real = rsb.build_app
    monkeypatch.setattr(rsb, "build_app", lambda a, *x, **k: (_ for _ in ()).throw(ValueError(rs.STORE[1]))
                        if a["key"] == rs.K[1] else real(a, *x, **k))
    shutil.rmtree(os.path.join(d, "review", "studio"))
    lines += _step(s, d, dash)[1]
    assert len(lines) == 3 and all(LINE.match(x) for x in lines), lines
    for ln in lines:
        for sec in SECRETS:
            assert sec not in ln, (sec, ln)
