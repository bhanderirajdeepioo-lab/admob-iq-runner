"""Daily App Review — the build side (admob_iq.review + its build_static hook), on the synthetic site of
tests/review_synth.py: the day document follows the §A.5 contract (10 features per app, 5 answers only on red / amber,
rich text without HTML, well-formed money, no Devanagari, the hidden app nowhere), the build is deterministic and never
touches the dashboard, a day is frozen ONCE after the IST ready time (the single rebuild, failures retried, never a
broken day), index.json / publish follow §A.8–A.9, the hook is off by default and failure-isolated (every other site
file byte-identical), and the build log is ONE counts-only line."""

import contextlib
import copy
import gzip
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import pytest

from admob_iq import build_static
from admob_iq.review import FEATS, build_day, review_day_ist, run_review
from admob_iq.review import day as rday
from admob_iq.review import store as rstore
from admob_iq.review.apps import ReviewBuildError, file_key
from admob_iq.review.const import EXPAND_TOP, NAYA_DAYS
from admob_iq.review.fmt import plain, rt, money
from admob_iq.review.site import Site
from tests import review_synth as rs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = rs.DAY
DS = DAY.isoformat()
LOG = re.compile(r"^review: day \d{4}-\d{2}-\d{2} · ((re)?built \(apps \d+, top \d+, ok \d+, small \d+, failed \d+\)|exists"
                 r"|waiting \(ready \d\d:\d\d IST\) · open (\d{4}-\d{2}-\d{2}|none)|failed \([A-Za-z_]+\) · retry next "
                 r"run)( · rebuild ignored)? · days \d+ · published \d+ · \d+\.\ds$")
FEAT_IDS = [f for f, _ in FEATS]
ST = {"red", "amber", "green", "normal", "wait", "na", "nodata"}
SRC = {"Uninstall", "Active users", "Install value", "Ad unit", "Ads", "Deductions", "Mediation", "Setup",
       "Update impact"}
SECRETS = ([rs.A[i] for i in rs.A] + [rs.K[i] for i in rs.A] + list(rs.STORE.values()) + list(rs.PKG.values())
           + list(rs.UNIT.values()) + [rs.PUB, rs.PUB2, "Synth", "Synth Studio", "com.example", "$", "₹", "/day", "/din"])


def at_ist(d, hhmm):
    """The UTC instant of IST `hhmm` on day d."""
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc) - timedelta(hours=5, minutes=30)


@pytest.fixture
def site(tmp_path):
    p = str(tmp_path / "site")
    rs.make_site(p)
    return p


@pytest.fixture
def doc(site):
    return build_day(Site(site), DAY, now=rs.NOW)


def run(site, data, now, **kw):
    """review_run with a captured stderr → (result, the stderr lines)."""
    env = kw.pop("env", {})
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        res = rstore.review_run(None, data, site, now, env=env, **kw)
    return res, [x for x in err.getvalue().splitlines() if x]


def raw_of(path):
    with open(path, "rb") as f:
        return f.read()


def load_gz(path):
    return json.loads(gzip.decompress(raw_of(path)).decode("utf-8"))


# ── contract (§A.5) ─────────────────────────────────────────────────────────────────────────────
def check_rt(x, where):
    if isinstance(x, str):
        return
    assert isinstance(x, list) and x, where
    for seg in x:
        if isinstance(seg, str):
            assert seg, where
            continue
        assert isinstance(seg, dict) and set(seg) == {"usd", "s", "sign", "p"}, (where, seg)
        assert isinstance(seg["usd"], (int, float)) and not isinstance(seg["usd"], bool), where
        assert seg["s"] in ("/day", "") and seg["sign"] in (0, 1) and seg["p"] in (0, 2), (where, seg)


def check_chart(c, where):
    assert set(c) == {"cap", "labels", "vals", "fmt", "tips", "before", "after_idx", "marks"}, where
    assert isinstance(c["cap"], str) and c["cap"]
    assert isinstance(c["labels"], list) and all(isinstance(x, str) for x in c["labels"])
    assert isinstance(c["vals"], list) and len(c["vals"]) == len(c["labels"]) and c["vals"], where
    assert all(v is None or (isinstance(v, (int, float)) and v == v) for v in c["vals"]), where
    assert any(v is not None for v in c["vals"]), where
    assert c["fmt"] in ("usd", "n", "p100", "r1"), where
    assert c["tips"] is None or (len(c["tips"]) == len(c["labels"]) and all(isinstance(t, str) for t in c["tips"]))
    assert c["before"] is None or isinstance(c["before"], (int, float))
    assert c["after_idx"] is None or (isinstance(c["after_idx"], int) and 0 <= c["after_idx"] < len(c["vals"]))
    for m in c["marks"]:
        assert isinstance(m, list) and len(m) == 2 and isinstance(m[0], int) and 0 <= m[0] < len(c["vals"]), where
        assert isinstance(m[1], str) and m[1], where


def check_feat(fe, where):
    assert set(fe) == {"st", "t", "line", "q", "kis", "info", "detail", "snz_ph"}, where
    assert fe["st"] in ST, where
    assert isinstance(fe["t"], str) and 0 < len(fe["t"]) <= 160 and "\x00" not in fe["t"], where
    check_rt(fe["line"], where)
    assert (fe["q"] is not None) == (fe["st"] in ("red", "amber")), where            # q ⇔ red / amber
    if fe["q"] is not None:
        q = fe["q"]
        assert set(q) == {"kya", "kab", "kit", "naya", "karo", "kis", "abhi", "saath"}, where
        check_rt(q["kya"], where)
        check_rt(q["kit"], where)
        assert isinstance(q["kab"], str) and q["kab"], where
        assert isinstance(q["karo"], str) and q["karo"], where
        assert set(q["naya"]) == {"chip", "first"} and q["naya"]["chip"] in ("naya", "chal_raha", "purani"), where
        assert isinstance(q["naya"]["first"], str) and q["naya"]["first"], where
        for k in ("kis", "abhi", "saath"):
            assert q[k] is None or check_rt(q[k], where) is None
    assert fe["kis"] is None or check_rt(fe["kis"], where) is None
    assert isinstance(fe["info"], list) and len(fe["info"]) <= 2, where
    for x in fe["info"]:
        check_rt(x, where)
    if fe["detail"] is not None:
        d = fe["detail"]
        assert set(d) == {"chart", "more", "tab"} and isinstance(d["tab"], str) and d["tab"], where
        if d["chart"] is not None:
            check_chart(d["chart"], where)
        assert isinstance(d["more"], list) and len(d["more"]) <= 12, where
        for r in d["more"]:
            assert set(r) == {"w", "src", "fact", "meta"}, where
            assert r["w"] in ("red", "amber", "green", "info") and r["src"] in SRC, (where, r)
            check_rt(r["fact"], where)
            assert isinstance(r["meta"], str) and r["meta"], where
    assert fe["snz_ph"] is None or (isinstance(fe["snz_ph"], str) and fe["snz_ph"])


def check_doc(doc):
    """The §A.5 schema, written out (no library)."""
    assert set(doc) == {"v", "day", "weekday", "built_at", "ready_ist", "built_from", "data", "fx", "feats", "consts",
                        "counts", "order", "how", "apps"}
    assert doc["v"] == 1 and re.match(r"^\d{4}-\d{2}-\d{2}$", doc["day"])
    assert doc["weekday"] in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", doc["built_at"])
    assert re.match(r"^\d\d:\d\d$", doc["ready_ist"])
    assert set(doc["built_from"]) == {"generated_at"}
    dt = doc["data"]
    assert set(dt) == {"admob_till", "ga4_till", "settled_till", "ga4_lag", "w7", "p7", "usual", "ded"}
    for k in ("w7", "p7", "usual"):
        assert set(dt[k]) == {"from", "to"} and dt[k]["from"] <= dt[k]["to"]
    assert dt["ded"] is None or set(dt["ded"]) == {"from", "to"}
    assert doc["fx"] is None or doc["fx"] > 0
    assert doc["feats"] == [[f, lab] for f, lab in FEATS]
    assert doc["consts"] == {"small_usd": 30, "badi_usd": 300, "naya_days": NAYA_DAYS, "expand_top": EXPAND_TOP}
    assert set(doc["counts"]) == {"apps", "attn", "ok", "small", "nb", "red", "amber", "failed"}
    assert set(doc["order"]) == {"top", "ok", "small"}
    assert isinstance(doc["how"], list) and doc["how"]
    for x in doc["how"]:
        check_rt(x, "how")
    keys = [a["key"] for a in doc["apps"]]
    order = doc["order"]["top"] + doc["order"]["ok"] + doc["order"]["small"]
    assert order == keys and len(set(keys)) == len(keys)                      # order partitions every key once
    assert doc["counts"]["apps"] == len(keys) and doc["counts"]["attn"] == len(doc["order"]["top"])
    assert doc["counts"]["ok"] == len(doc["order"]["ok"]) and doc["counts"]["small"] == len(doc["order"]["small"])
    for a in doc["apps"]:
        w = a.get("key")
        assert set(a) == {"key", "app_id", "dname", "name", "acct", "pkg", "size", "small", "k7", "kp7", "y", "us",
                          "spend", "paisa", "tier", "nb", "head", "f"}, w
        assert re.match(r"^[0-9a-f]{12}$", a["key"]) and a["key"] == file_key(a["app_id"])
        assert all(isinstance(a[k], str) and a[k] for k in ("app_id", "dname", "name", "acct"))
        assert a["pkg"] is None or isinstance(a["pkg"], str)
        assert a["size"] in ("badi", "madhyam", "chhoti") and a["small"] == (a["size"] == "chhoti")
        for k in ("k7", "kp7", "y", "us", "spend", "paisa"):
            assert isinstance(a[k], (int, float)) and not isinstance(a[k], bool), (w, k)
        assert a["tier"] in ("red", "amber", "green", "normal")
        assert set(a["head"]) == {"text", "chip", "age"} and a["head"]["chip"] in (None, "naya", "chal_raha", "purani")
        check_rt(a["head"]["text"], w)
        assert list(a["f"]) == FEAT_IDS or set(a["f"]) == set(FEAT_IDS)
        assert len(a["f"]) == 10
        for f, fe in a["f"].items():
            check_feat(fe, (w, f))
        assert all(f in FEAT_IDS and a["f"][f]["st"] == "red" for f in a["nb"]), w
        worst = [fe["st"] for fe in a["f"].values() if fe["st"] in ("red", "amber")]
        want = "red" if "red" in worst else "amber" if worst else (
            "green" if any(fe["st"] == "green" for fe in a["f"].values()) else "normal")
        assert a["tier"] == want, w
    in_top = [a for a in doc["apps"] if a["key"] in doc["order"]["top"]]
    assert all(not a["small"] and a["tier"] in ("red", "amber") for a in in_top)
    assert all(a["small"] for a in doc["apps"] if a["key"] in doc["order"]["small"])
    assert all(not a["small"] and a["tier"] in ("green", "normal") for a in doc["apps"] if a["key"] in doc["order"]["ok"])


def test_the_day_document_follows_the_contract(doc):
    check_doc(doc)
    raw = json.dumps(doc, ensure_ascii=False)
    assert re.search(r"<[A-Za-z/]", raw) is None                                  # no HTML anywhere
    assert re.search(r"[\u0900-\u097F]", raw) is None                             # Roman Hinglish only
    assert "\x00" not in raw and "\\u0000" not in raw                              # no money token left over
    assert doc["day"] == DS and doc["weekday"] == "Thursday" and doc["built_at"] == "2026-10-01T04:17:09Z"
    assert doc["fx"] == rs.FX and doc["built_from"] == {"generated_at": "2026-10-01T04:13:55+00:00"}
    assert doc["data"]["admob_till"] == "2026-09-30" and doc["data"]["ga4_till"] == "2026-09-28"
    assert doc["data"]["ga4_lag"] == 3 and doc["data"]["w7"] == {"from": "2026-09-24", "to": "2026-09-30"}
    assert doc["data"]["p7"] == {"from": "2026-09-17", "to": "2026-09-23"}
    assert doc["data"]["usual"] == {"from": "2026-09-23", "to": "2026-09-29"}


def test_order_tiers_and_groups_match_the_synthetic_apps(doc):
    inv = {v: k for k, v in rs.K.items()}
    assert {g: [inv[k] for k in doc["order"][g]] for g in doc["order"]} == {
        "top": rs.EXPECT["top"], "ok": rs.EXPECT["ok"], "small": rs.EXPECT["small"]}
    assert doc["counts"] == rs.EXPECT["counts"]
    by = {inv[a["key"]]: a for a in doc["apps"]}
    assert 7 not in by                                                           # the hidden app: no card
    for i, a in by.items():
        assert a["tier"] == rs.EXPECT["tier"][i], i
        assert a["nb"] == rs.EXPECT["nb"][i], i
        assert a["size"] == rs.EXPECT["size"][i], i
        assert a["app_id"] == rs.A[i] and a["dname"] == rs.DNAME[i]
    for i, f in rs.EXPECT["red_feat"].items():
        assert by[i]["f"][f]["st"] == "red" and by[i]["f"][f]["q"]["naya"]["chip"] == "naya"
    for i, f in rs.EXPECT["amber_feat"].items():
        assert by[i]["f"][f]["st"] == "amber"
    assert by[6]["small"] and by[6]["size"] == "chhoti"                           # a6: small (its 🔴 stays in the group)
    assert by[4]["head"] == {"text": "Sab normal — koi badlav nahi", "chip": None, "age": None}
    assert all(fe["st"] not in ("red", "amber") for fe in by[4]["f"].values())
    assert by[5]["tier"] == "green" and by[5]["f"]["kamai"]["st"] == "green" and by[5]["f"]["update"]["st"] == "green"
    assert by[5]["name"] == "Synth Echo Editor - Pro"                            # the owner's own name, dash normalised
    assert by[8]["f"]["setup"]["st"] == "amber" and by[8]["f"]["uninstall"]["st"] == "nodata"
    assert by[8]["f"]["active"]["st"] == "nodata" and by[8]["pkg"] == rs.PKG[8]
    assert by[4]["acct"] == "A/c 1111" and by[1]["acct"] == "Synth Studio"
    # money: USD in the doc, the kamai numbers of the site
    assert by[1]["k7"] == 320.0 and by[1]["kp7"] == 520.0 and by[1]["y"] == 320.0
    assert abs(by[1]["us"] - (520 + 6 * 320) / 7) < 1e-3
    assert by[4]["spend"] == 50.0 and by[4]["paisa"] == 500.0
    # the 5 answers of a red feature
    q = by[1]["f"]["kamai"]["q"]
    assert plain(q["kya"]) == "App ki kamai 38% giri"
    assert plain(q["kit"]) == "Revenue $520 → $320/day (−$200/day)"
    assert q["kab"].startswith("24 Sep") and q["naya"]["chip"] == "naya"
    assert by[1]["f"]["kamai"]["detail"]["chart"]["fmt"] == "usd"
    assert by[1]["head"]["chip"] == "naya" and by[1]["head"]["age"] == "7 days"


def test_every_feature_is_readable_on_the_synthetic_site(site):
    """No feature of the synthetic site silently fell back to 'data nahi padh paye' (a port bug would)."""
    from admob_iq.review.apps import make_ctx
    from admob_iq.review.rows import app_rows, build_rows, extra_rows
    ctx = make_ctx(Site(site), DAY)
    build_rows(ctx)
    extra_rows(ctx)
    for aid in ctx.apps:
        app_rows(ctx, aid)
    assert dict(ctx.feat_fail) == {} and ctx.app_fail == set()
    doc = build_day(Site(site), DAY, now=rs.NOW)
    raw = json.dumps(doc, ensure_ascii=False)
    assert rday.FEAT_FAIL_TXT not in raw and rday.APP_FAIL_TXT not in raw


def test_the_hidden_app_is_nowhere_in_the_document(doc):
    raw = json.dumps(doc, ensure_ascii=False)
    for s in (rs.A[7], rs.K[7], rs.STORE[7], rs.PKG[7], rs.UNIT[7]):
        assert s not in raw


def test_money_segments_are_usd_and_follow_the_rt_format(doc):
    segs = []

    def walk(o):
        if isinstance(o, dict):
            if set(o) == {"usd", "s", "sign", "p"}:
                segs.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(doc)
    assert segs and all(s["s"] in ("", "/day") for s in segs)
    assert any(s["s"] == "/day" for s in segs) and any(s["sign"] == 1 for s in segs)
    assert rt(f"a {money(12.5)} b") == ["a ", {"usd": 12.5, "s": "/day", "sign": 0, "p": 0}, " b"]
    assert plain(rt(f"x {money(-3.456, din=False, p=2)}")) == "x −$3.46"
    assert plain(f"{money(1234.5, sign=True)}") == "+$1,234/day"
    assert rt("plain text") == "plain text" and rt(None) is None


def test_html_in_names_never_reaches_the_document(site):
    names = os.path.join(site, "app_names.json")
    with open(names, "w", encoding="utf-8") as f:
        json.dump({rs.A[5]: "<script>alert(1)</script> Synth", rs.A[4]: "</b><img src=x onerror=y>"}, f)
    doc = build_day(Site(site), DAY, now=rs.NOW)
    raw = json.dumps(doc, ensure_ascii=False)
    assert re.search(r"<[A-Za-z/!?]", raw) is None
    by = {a["app_id"]: a for a in doc["apps"]}
    assert by[rs.A[5]]["name"].startswith("‹script>")


def test_file_key_is_the_uninstall_file_key():
    from admob_iq.fetch import ga4_uninstall as gu
    for i in rs.A:
        assert file_key(rs.A[i]) == gu.file_key(rs.A[i]) == rs.K[i]


def test_importing_the_package_reads_prints_and_computes_nothing():
    code = ("import builtins, sys; real = builtins.open\n"
            "def no(*a, **k): raise AssertionError('open at import')\n"
            "builtins.open = no\n"
            "import admob_iq.review, admob_iq.review.__main__, admob_iq.review.rows, admob_iq.review.text\n"
            "import admob_iq.review.charts, admob_iq.review.day, admob_iq.review.store\n"
            "builtins.open = real\n"
            "assert not [m for m in sys.modules if m == 'admob_iq.fetch' or m.startswith('admob_iq.fetch.')]\n"
            "assert not [m for m in sys.modules if m.split('.')[0] in ('requests', 'google', 'httpx', 'yaml')]\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "" and out.stderr == ""


# ── determinism + read-only input ───────────────────────────────────────────────────────────────
def test_the_build_is_deterministic_and_never_touches_the_dashboard(site):
    dash = rs.dashboard(DAY)
    before = json.dumps(dash, sort_keys=True)
    a = build_day(Site(site, dash), DAY, now=rs.NOW)
    b = build_day(Site(site, dash), DAY, now=rs.NOW + timedelta(hours=3))
    assert json.dumps(dash, sort_keys=True) == before                            # the caller's dict is unchanged
    assert a["built_at"] != b["built_at"]
    a.pop("built_at")
    b.pop("built_at")
    assert a == b
    c = build_day(Site(site), DAY, now=rs.NOW)                                    # the file == the in-memory dashboard
    c.pop("built_at")
    assert c == a
    # run_review with the build's in-memory dashboard: still unchanged
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        run_review(dash, os.path.join(os.path.dirname(site), "data"), site, now=rs.NOW, env={})
    assert json.dumps(dash, sort_keys=True) == before


# ── failure isolation inside the builder (§A.6) ─────────────────────────────────────────────────
def test_a_failing_feature_becomes_nodata_and_a_failing_app_a_placeholder_card(site, monkeypatch):
    real_feature, real_app = rday._feature, rday.build_app

    def bad_feature(ctx, f, frs, aid, a):
        if f == "mediation" and aid == rs.A[4]:
            raise KeyError("x")
        return real_feature(ctx, f, frs, aid, a)

    def bad_app(ctx, aid):
        if aid == rs.A[3]:
            raise ValueError("x")
        return real_app(ctx, aid)
    monkeypatch.setattr(rday, "_feature", bad_feature)
    monkeypatch.setattr(rday, "build_app", bad_app)
    doc = build_day(Site(site), DAY, now=rs.NOW)
    check_doc(doc)
    by = {a["app_id"]: a for a in doc["apps"]}
    m = by[rs.A[4]]["f"]["mediation"]
    assert m["st"] == "nodata" and m["t"] == "Is feature ka data nahi padh paye" and m["q"] is None
    a3 = by[rs.A[3]]
    assert a3["tier"] == "normal" and a3["head"]["text"] == "Is app ka card nahi ban paya (data me dikkat)"
    assert all(fe["st"] == "nodata" and fe["t"] == "Card nahi ban paya" and fe["q"] is None for fe in a3["f"].values())
    assert doc["counts"]["failed"] == 1 and a3["key"] in doc["order"]["ok"]
    assert a3["name"] == rs.STORE[3] and a3["k7"] == 350.0                       # the header still shows the app


def test_a_broken_day_is_refused(site, monkeypatch):
    monkeypatch.setattr(rday, "build_app", lambda ctx, aid: (_ for _ in ()).throw(ValueError("x")))
    with pytest.raises(ReviewBuildError):
        build_day(Site(site), DAY, now=rs.NOW)
    real = rs.dashboard(DAY)
    with pytest.raises(ReviewBuildError):                                         # nothing selected
        build_day(Site(site, dict(real, apps_catalog=[dict(c, selected=False) for c in real["apps_catalog"]])), DAY)
    os.remove(os.path.join(site, "dashboard.json.gz"))
    with pytest.raises(ReviewBuildError):                                         # no dashboard
        build_day(Site(site), DAY)


def test_up_to_two_failed_apps_still_make_a_day(site, monkeypatch):
    real = rday.build_app
    monkeypatch.setattr(rday, "build_app", lambda ctx, aid: (_ for _ in ()).throw(ValueError("x"))
                        if aid in (rs.A[1], rs.A[2]) else real(ctx, aid))
    doc = build_day(Site(site), DAY, now=rs.NOW)
    assert doc["counts"]["failed"] == 2
    monkeypatch.setattr(rday, "build_app", lambda ctx, aid: (_ for _ in ()).throw(ValueError("x"))
                        if aid in (rs.A[1], rs.A[2], rs.A[3], rs.A[4]) else real(ctx, aid))
    with pytest.raises(ReviewBuildError):                                         # 4 of 7 > max(2, 3.5)
        build_day(Site(site), DAY, now=rs.NOW)


def test_missing_ga4_blocks_make_nodata_not_errors(site):
    dash = rs.dashboard(DAY)
    for k in ("uninstall", "active", "value", "roas", "account_health", "accounts", "alerts", "range_alerts"):
        dash.pop(k)
    for n in os.listdir(site):
        if n != "dashboard.json.gz":
            os.remove(os.path.join(site, n))
    doc = build_day(Site(site, dash), DAY, now=rs.NOW)
    check_doc(doc)
    assert doc["counts"]["failed"] == 0 and doc["data"]["ga4_till"] is None and doc["data"]["ded"] is None
    for a in doc["apps"]:
        for f in ("uninstall", "active", "value", "mediation", "health"):
            assert a["f"][f]["st"] == "nodata", (a["key"], f)


# ── freeze rule (§A.7) ──────────────────────────────────────────────────────────────────────────
def test_review_day_is_the_ist_calendar_day():
    assert review_day_ist(datetime(2026, 9, 30, 18, 29, tzinfo=timezone.utc)) == date(2026, 9, 30)
    assert review_day_ist(datetime(2026, 9, 30, 18, 31, tzinfo=timezone.utc)) == date(2026, 10, 1)
    assert review_day_ist(datetime(2026, 9, 30, 18, 31)) == date(2026, 10, 1)        # naive = UTC
    assert not rstore.is_ready(datetime(2026, 9, 30, 18, 31, tzinfo=timezone.utc), date(2026, 10, 1), "09:00")
    assert rstore.is_ready(at_ist(DAY, "09:00"), DAY, "09:00")
    assert not rstore.is_ready(at_ist(DAY, "08:59"), DAY, "09:00")


@pytest.mark.parametrize("value, want", [("", "09:00"), (None, "09:00"), ("25:00", "09:00"), ("9", "09:00"),
                                         ("abc", "09:00"), ("09:60", "09:00"), ("7:05", "07:05"), (" 10:30 ", "10:30")])
def test_ready_time_parsing(value, want):
    assert rstore.parse_ready(value) == want


def test_before_ready_nothing_is_frozen_and_at_ready_the_day_is(site, tmp_path):
    data = str(tmp_path / "data")
    res, lines = run(site, data, at_ist(DAY, "08:59"))
    assert lines == [lines[0]] and LOG.match(lines[0]) and res["ok"]
    assert " · waiting (ready 09:00 IST) · open none · days 0 · published 0 · " in lines[0]
    assert not os.path.exists(rstore.day_path(data, DS))
    idx = json.load(open(os.path.join(site, "review", "index.json"), encoding="utf-8"))
    assert idx["pending_today"] is True and idx["retry"] is False and idx["open_day"] is None
    assert idx["next_snapshot"] == "2026-10-01T09:00:00+05:30" and idx["days"] == [] and idx["go_live"] is None
    assert res["paths"] == ["/review/*"]                                          # site/review/ exists (index.json)
    res, lines = run(site, data, at_ist(DAY, "09:00"))
    assert LOG.match(lines[0]) and "· built (apps 7, top 4, ok 2, small 1, failed 0) · days 1 · published 1 ·" in lines[0]
    doc = rstore.read_doc(rstore.day_path(data, DS), DS)
    check_doc(doc)
    assert doc["built_at"] == "2026-10-01T03:30:00Z" and doc["ready_ist"] == "09:00"
    meta = json.load(open(os.path.join(data, "review", "meta.json"), encoding="utf-8"))
    assert meta == {"v": 1, "go_live": DS, "rebuilt": {}, "fails": {}}


def test_a_frozen_day_is_never_rewritten(site, tmp_path):
    data = str(tmp_path / "data")
    run(site, data, at_ist(DAY, "09:30"))
    path = rstore.day_path(data, DS)
    first = raw_of(path)
    dash = rs.dashboard(DAY)
    dash["placements"][0]["daily"][-1][1] = 1                                      # the data moved on
    with gzip.open(os.path.join(site, "dashboard.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(dash, f)
    res, lines = run(site, data, at_ist(DAY, "11:00"))
    assert "· exists · days 1 · published 0 ·" in lines[0] and LOG.match(lines[0])
    assert raw_of(path) == first
    # REVIEW_REBUILD_DAY for another day: ignored (and said so)
    res, lines = run(site, data, at_ist(DAY, "12:00"), env={"REVIEW_REBUILD_DAY": "2026-09-30"})
    assert "· exists · rebuild ignored · days 1 ·" in lines[0] and LOG.match(lines[0]) and raw_of(path) == first
    # REVIEW_REBUILD_DAY = today: rebuilt ONCE
    res, lines = run(site, data, at_ist(DAY, "12:30"), env={"REVIEW_REBUILD_DAY": DS})
    assert "· rebuilt (apps 7, top 4, ok 2, small 1, failed 0) · days 1 · published 1 ·" in lines[0]
    assert LOG.match(lines[0]) and raw_of(path) != first
    second = raw_of(path)
    meta = json.load(open(os.path.join(data, "review", "meta.json"), encoding="utf-8"))
    assert meta["rebuilt"] == {DS: "2026-10-01T07:00:00Z"} and meta["go_live"] == DS
    res, lines = run(site, data, at_ist(DAY, "13:30"), env={"REVIEW_REBUILD_DAY": DS})
    assert "· exists · days 1 · published 0 ·" in lines[0] and raw_of(path) == second


def test_a_failed_build_writes_nothing_and_the_next_run_retries(site, tmp_path, monkeypatch):
    data = str(tmp_path / "data")

    def boom(*a, **k):
        raise KeyError("secret-name")
    monkeypatch.setattr(rstore, "build_day", boom)
    res, lines = run(site, data, at_ist(DAY, "09:10"))
    assert not res["ok"] and LOG.match(lines[0])
    assert "· failed (KeyError) · retry next run · days 0 · published 0 ·" in lines[0] and "secret" not in lines[0]
    assert not os.path.exists(rstore.day_path(data, DS))
    idx = json.load(open(os.path.join(site, "review", "index.json"), encoding="utf-8"))
    assert idx["retry"] is True and idx["pending_today"] is True and idx["next_snapshot"] is None
    meta = json.load(open(os.path.join(data, "review", "meta.json"), encoding="utf-8"))
    assert meta["fails"] == {DS: 1} and meta["go_live"] is None
    res, lines = run(site, data, at_ist(DAY, "09:20"))
    assert not res["ok"] and json.load(open(os.path.join(data, "review", "meta.json")))["fails"] == {DS: 2}
    monkeypatch.undo()
    res, lines = run(site, data, at_ist(DAY, "10:10"))
    assert res["ok"] and "· built (" in lines[0] and rstore.read_doc(rstore.day_path(data, DS), DS)
    idx = json.load(open(os.path.join(site, "review", "index.json"), encoding="utf-8"))
    assert idx["retry"] is False and idx["open_day"] == DS and idx["go_live"] == DS


def test_a_failed_rebuild_keeps_the_snapshot_and_tries_again(site, tmp_path, monkeypatch):
    data = str(tmp_path / "data")
    run(site, data, at_ist(DAY, "09:30"))
    first = raw_of(rstore.day_path(data, DS))
    monkeypatch.setattr(rstore, "build_day", lambda *a, **k: (_ for _ in ()).throw(ValueError("x")))
    res, lines = run(site, data, at_ist(DAY, "10:00"), env={"REVIEW_REBUILD_DAY": DS})
    assert "failed (ValueError)" in lines[0] and raw_of(rstore.day_path(data, DS)) == first
    monkeypatch.undo()
    res, lines = run(site, data, at_ist(DAY, "11:00"), env={"REVIEW_REBUILD_DAY": DS})
    assert "· rebuilt (" in lines[0]


def test_a_damaged_snapshot_is_rebuilt_when_ready(site, tmp_path):
    data = str(tmp_path / "data")
    os.makedirs(os.path.dirname(rstore.day_path(data, DS)))
    with open(rstore.day_path(data, DS), "wb") as f:
        f.write(b"not gzip")
    res, lines = run(site, data, at_ist(DAY, "09:30"))
    assert "· built (" in lines[0] and rstore.read_doc(rstore.day_path(data, DS), DS)
    # a valid file of ANOTHER day under today's name is not today's snapshot either
    other = rstore.day_path(data, "2026-10-02")
    shutil.copyfile(rstore.day_path(data, DS), other)
    assert rstore.read_doc(other, "2026-10-02") is None
    assert "2026-10-02" not in rstore.snapshot_days(data)


def test_ready_time_from_the_environment(site, tmp_path):
    data = str(tmp_path / "data")
    res, lines = run(site, data, at_ist(DAY, "10:00"), env={"REVIEW_READY_IST": "10:30"})
    assert "waiting (ready 10:30 IST)" in lines[0]
    idx = json.load(open(os.path.join(site, "review", "index.json"), encoding="utf-8"))
    assert idx["ready_ist"] == "10:30" and idx["next_snapshot"] == "2026-10-01T10:30:00+05:30"
    res, lines = run(site, data, at_ist(DAY, "09:00"), env={"REVIEW_READY_IST": "nonsense"})
    assert "· built (" in lines[0]
    assert rstore.read_doc(rstore.day_path(data, DS), DS)["ready_ist"] == "09:00"


# ── index.json (§A.9) + publish (§A.8) ──────────────────────────────────────────────────────────
def test_the_index_lists_every_day_and_names_the_open_one(site, tmp_path):
    data = str(tmp_path / "data")
    for back in (2, 1, 0):
        d = DAY - timedelta(back)
        run(site, data, at_ist(d, "09:15"))
    ip = os.path.join(site, "review", "index.json")
    idx = json.load(open(ip, encoding="utf-8"))
    assert [x["d"] for x in idx["days"]] == ["2026-09-29", "2026-09-30", DS]
    assert idx["days"][-1] == {"d": DS, "apps": 7, "top": 4, "small": 1, "file": f"review/days/{DS}.json.gz"}
    assert idx["go_live"] == "2026-09-29" and idx["open_day"] == DS and idx["today_ist"] == DS
    assert idx["pending_today"] is False and idx["retry"] is False
    assert idx["next_snapshot"] == "2026-10-02T09:00:00+05:30" and idx["ready_ist"] == "09:00" and idx["v"] == 1
    assert idx["open_apps"] == {rs.K[i]: f"{rs.STORE[i] if i != 5 else 'Synth Echo Editor - Pro'} · "
                                         f"{rs.ACCT_NAME.get(rs.ACC[i], 'A/c 1111')}" for i in rs.A if i != 7}
    for x in idx["days"]:                                                        # every day published
        assert raw_of(os.path.join(site, x["file"])) == raw_of(rstore.day_path(data, x["d"]))
    # nothing new → index bytes (and mtime) untouched
    before, mt = raw_of(ip), os.stat(ip).st_mtime_ns
    res, lines = run(site, data, at_ist(DAY, "16:00"))
    assert raw_of(ip) == before and os.stat(ip).st_mtime_ns == mt and "· exists · days 3 · published 0 ·" in lines[0]
    # the next day before its ready time: yesterday stays open
    nxt = DAY + timedelta(1)
    res, lines = run(site, data, at_ist(nxt, "08:00"))
    idx = json.load(open(ip, encoding="utf-8"))
    assert f"review: day {nxt.isoformat()} · waiting (ready 09:00 IST) · open {DS} · days 3 ·" in lines[0]
    assert idx["open_day"] == DS and idx["pending_today"] is True and idx["retry"] is False
    assert idx["next_snapshot"] == "2026-10-02T09:00:00+05:30" and idx["go_live"] == "2026-09-29"
    # the go-live day never moves, even when meta.json is lost
    os.remove(os.path.join(data, "review", "meta.json"))
    run(site, data, at_ist(nxt, "08:30"))
    assert json.load(open(ip, encoding="utf-8"))["go_live"] == "2026-09-29"


def test_publish_restores_missing_copies_and_never_deletes(site, tmp_path):
    data = str(tmp_path / "data")
    run(site, data, at_ist(DAY - timedelta(1), "09:15"))
    run(site, data, at_ist(DAY, "09:15"))
    sd = os.path.join(site, "review", "days")
    os.remove(os.path.join(sd, f"{DS}.json.gz"))
    with open(os.path.join(sd, "2026-09-30.json.gz"), "wb") as f:
        f.write(b"stale")
    with open(os.path.join(sd, "stray.txt"), "w") as f:
        f.write("keep me")
    res, lines = run(site, data, at_ist(DAY, "10:15"))
    assert "· published 2 ·" in lines[0]
    assert raw_of(os.path.join(sd, f"{DS}.json.gz")) == raw_of(rstore.day_path(data, DS))
    assert raw_of(os.path.join(sd, "2026-09-30.json.gz")) == raw_of(rstore.day_path(data, "2026-09-30"))
    assert open(os.path.join(sd, "stray.txt")).read() == "keep me"


def test_only_review_dirs_are_written(site, tmp_path):
    data = str(tmp_path / "data")
    os.makedirs(data)
    before_site = sorted(os.listdir(site))
    run(site, data, at_ist(DAY, "09:30"))
    assert sorted(os.listdir(site)) == sorted(before_site + ["review"])
    assert os.listdir(data) == ["review"]
    # seen/<day>.json: the red / amber rows each snapshot showed (history for the next days) — never published
    assert sorted(os.listdir(os.path.join(data, "review"))) == ["days", "meta.json", "seen"]
    assert sorted(os.listdir(os.path.join(site, "review"))) == ["days", "index.json"]


# ── the build_static hook (§A.10) ───────────────────────────────────────────────────────────────
def test_headers_text_extra_is_optional_and_lands_before_index_html():
    dash = {"active": {}, "value": {}}
    base = build_static.headers_text(["uninstall.json.gz"], dash)
    assert build_static.headers_text(["uninstall.json.gz"], dash, extra=()) == base
    got = build_static.headers_text(["uninstall.json.gz"], dash, extra=["/review/*"])
    assert "/review/*\n  Cache-Control: no-store\n\n/index.html\n  Cache-Control: no-cache\n" in got
    assert got.replace("/review/*\n  Cache-Control: no-store\n\n", "") == base


def test_the_hook_is_off_unless_enabled(site, tmp_path, monkeypatch, capsys):
    data = str(tmp_path / "data")
    dash = rs.dashboard(DAY)
    monkeypatch.delenv("REVIEW_ENABLED", raising=False)
    assert build_static._review_step(dash, data, site) == []
    for v in ("", "false", "0", "no"):
        monkeypatch.setenv("REVIEW_ENABLED", v)
        assert build_static._review_step(dash, data, site) == []
    assert not os.path.exists(data) and not os.path.exists(os.path.join(site, "review"))
    assert capsys.readouterr().err == ""
    monkeypatch.setenv("REVIEW_ENABLED", "true")
    monkeypatch.setenv("REVIEW_READY_IST", "09:00")
    assert build_static._review_step(dash, data, site, now=at_ist(DAY, "09:30")) == ["/review/*"]
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and LOG.match(err[0]) and "· built (apps 7," in err[0]
    assert rstore.read_doc(rstore.day_path(data, DS), DS)["built_from"]["generated_at"] == dash["generated_at"]


def test_a_crashing_review_step_changes_nothing(site, tmp_path, monkeypatch, capsys):
    data = str(tmp_path / "data")
    snap = {n: raw_of(os.path.join(site, n)) for n in os.listdir(site)}
    monkeypatch.setenv("REVIEW_ENABLED", "true")
    import admob_iq.review as review_pkg

    def boom(*a, **k):
        raise RuntimeError("Synth Alpha Player $320")
    monkeypatch.setattr(review_pkg, "run_review", boom)
    assert build_static._review_step(rs.dashboard(DAY), data, site) == []
    assert capsys.readouterr().err == "review skipped: RuntimeError\n"
    assert {n: raw_of(os.path.join(site, n)) for n in os.listdir(site)} == snap and not os.path.exists(data)


def test_mock_mode_build_is_unchanged_by_the_hook(tmp_path, monkeypatch, capsys):
    """Mock mode never runs the review step: same _headers bytes and dashboard keys as a build without the hook."""
    def build(tag, enabled, hook):
        monkeypatch.setenv("REVIEW_ENABLED", "true" if enabled else "false")
        if not hook:
            monkeypatch.setattr(build_static, "_review_step", lambda *a, **k: [])
        out, data = str(tmp_path / tag / "site"), str(tmp_path / tag / "data")
        build_static.build(out_dir=out, data_dir=data, today=date(2026, 7, 23), mode="mock")
        monkeypatch.undo()
        return out, data
    a_out, a_data = build("a", True, True)
    b_out, b_data = build("b", False, False)
    assert raw_of(os.path.join(a_out, "_headers")) == raw_of(os.path.join(b_out, "_headers"))
    assert "/review/" not in raw_of(os.path.join(a_out, "_headers")).decode()
    assert set(load_gz(os.path.join(a_out, "dashboard.json.gz"))) == set(load_gz(os.path.join(b_out, "dashboard.json.gz")))
    assert sorted(os.listdir(a_out)) == sorted(os.listdir(b_out)) and "review" not in os.listdir(a_out)
    assert not os.path.exists(os.path.join(a_data, "review"))
    assert "review" not in capsys.readouterr().err


@pytest.fixture
def live_like(monkeypatch):
    """build(mode="live") without any network: fake creds, the mock AdMob pull, every GA4 / Google Ads / icon call
    stubbed, and sockets refused — so the live-only review wiring runs for real."""
    from admob_iq.fetch import fetcher
    import admob_iq.fetch.app_icons as icons
    real = build_static.settings()

    def fake_settings():
        s = dict(real, google_client_id="cid-test", google_client_secret="cs-test", report_tz="America/Los_Angeles",
                 notify_dry_run=True, telegram_token="", telegram_chat="", google_ads_dev_token=None,
                 google_ads_refresh_token=None, google_ads_login_customer_id=None)
        s["smtp"] = dict(real["smtp"], host="")
        return s
    orig = fetcher.run_once
    monkeypatch.setattr(build_static, "settings", fake_settings)
    monkeypatch.setattr(build_static, "resolve_accounts", lambda: [{"account_id": rs.PUB, "refresh_token": "rt-test"}])
    monkeypatch.setattr(fetcher, "run_once", lambda accounts, repo, **kw: orig(
        accounts, repo, **dict(kw, mode="mock", full_history=False, ac_full_history=False)))
    monkeypatch.setattr(build_static, "_backfill_missing_accounts_ac", lambda *a, **k: None)
    monkeypatch.setattr(build_static, "_backfill_network_selected_apps", lambda *a, **k: None)
    monkeypatch.setattr(build_static, "_uninstall_with_revenue", lambda *a, **k: [])
    monkeypatch.setattr(icons, "resolve_app_icons", lambda *a, **k: {})

    def no_net(*a, **k):
        raise OSError("network blocked in test")
    monkeypatch.setattr(socket.socket, "connect", no_net)
    monkeypatch.setattr(socket, "getaddrinfo", no_net)
    monkeypatch.setenv("REVIEW_READY_IST", "00:00")
    monkeypatch.delenv("REVIEW_REBUILD_DAY", raising=False)

    def build(root):
        data = os.path.join(root, "data")
        os.makedirs(data, exist_ok=True)
        for m in (".backfilled", ".country_backfilled", ".ac_backfilled"):
            with open(os.path.join(data, m), "w") as f:
                f.write("x\n")
        r = build_static.build(out_dir=os.path.join(root, "site"), data_dir=data, today=date(2026, 7, 23), mode="live")
        assert r["mode"] == "live"
        return os.path.join(root, "site"), data
    return build


def _site_files(out):
    got = {}
    for dp, _dn, fn in os.walk(out):
        for n in fn:
            p = os.path.join(dp, n)
            rel = os.path.relpath(p, out)
            if rel == "dashboard.json.gz":
                d = load_gz(p)
                d.pop("generated_at", None)
                got[rel] = json.dumps(d, sort_keys=True)
            else:
                got[rel] = raw_of(p)
    return got


def test_live_build_runs_the_review_step_once_and_a_crash_leaves_every_file_alone(tmp_path, live_like, monkeypatch,
                                                                                   capsys):
    monkeypatch.setenv("REVIEW_ENABLED", "false")
    off_site, off_data = live_like(str(tmp_path / "off"))
    off_err = capsys.readouterr().err
    assert "review" not in off_err and not os.path.exists(os.path.join(off_site, "review"))
    # enabled: exactly ONE counts-only review line, the snapshot + index written, _headers gains /review/*
    monkeypatch.setenv("REVIEW_ENABLED", "true")
    on_site, on_data = live_like(str(tmp_path / "on"))
    lines = [x for x in capsys.readouterr().err.splitlines() if x.startswith("review")]
    assert len(lines) == 1 and LOG.match(lines[0]) and " · built (apps " in lines[0], lines
    assert os.path.exists(os.path.join(on_site, "review", "index.json"))
    assert os.listdir(os.path.join(on_data, "review", "days"))
    hdr = raw_of(os.path.join(on_site, "_headers")).decode()
    assert hdr == raw_of(os.path.join(off_site, "_headers")).decode().replace(
        "/index.html\n", "/review/*\n  Cache-Control: no-store\n\n/index.html\n")
    on = _site_files(on_site)
    off = _site_files(off_site)
    assert {k: v for k, v in on.items() if not k.startswith("review") and k != "_headers"} == \
           {k: v for k, v in off.items() if k != "_headers"}
    # enabled but crashing: the build completes, one "review skipped" line, every site file as with the hook off
    import admob_iq.review as review_pkg
    monkeypatch.setattr(review_pkg, "run_review", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    bad_site, bad_data = live_like(str(tmp_path / "bad"))
    err = capsys.readouterr().err
    assert [x for x in err.splitlines() if x.startswith("review")] == ["review skipped: RuntimeError"]
    assert _site_files(bad_site) == off
    assert not os.path.exists(os.path.join(bad_data, "review"))


# ── privacy (§A.10, §D.6) ───────────────────────────────────────────────────────────────────────
def test_every_log_line_is_counts_only(site, tmp_path, monkeypatch):
    data = str(tmp_path / "data")
    lines = []
    lines += run(site, data, at_ist(DAY, "08:00"))[1]
    lines += run(site, data, at_ist(DAY, "09:05"))[1]
    lines += run(site, data, at_ist(DAY, "09:35"))[1]
    lines += run(site, data, at_ist(DAY, "09:45"), env={"REVIEW_REBUILD_DAY": DS})[1]
    lines += run(site, data, at_ist(DAY, "09:55"), env={"REVIEW_REBUILD_DAY": "2026-01-01"})[1]
    monkeypatch.setattr(rstore, "build_day", lambda *a, **k: (_ for _ in ()).throw(KeyError(rs.STORE[1])))
    lines += run(site, data, at_ist(DAY + timedelta(1), "09:05"))[1]
    assert len(lines) == 6
    for ln in lines:
        assert LOG.match(ln), ln
        for s in SECRETS:
            assert s not in ln, (s, ln)


# ── the committed frontend fixture is what the build code writes ────────────────────────────────
def test_the_frontend_fixture_is_current(tmp_path):
    fx = rs.make_fixture(str(tmp_path))
    with open(rs.FIXTURE, encoding="utf-8") as f:
        committed = f.read()
    assert rs.fixture_text(fx) == committed, "run: python -m tests.review_synth --write"
    check_doc(fx["day"])
    raw = json.dumps(fx["day"], ensure_ascii=False)
    assert re.search(r"<[A-Za-z/]", raw) is None
    st = fx["state"]
    keys = {a["key"] for a in fx["day"]["apps"]}
    assert set(st["states"]) <= keys and set(st["prev"]["kal"]) <= keys
    assert {f["app"] for f in st["flags"]} <= keys and {s["app"] for s in st["snoozes"]} <= keys
    assert fx["index"]["open_day"] == fx["day"]["day"] == st["d"] == fx["me"]["open_day"]


# ── review fixes: history-based "Pehli baar dikha" / setup "Kab se", eCPM range wording, no framing ─────────────
def _set_dash(site_dir, fn):
    p = os.path.join(site_dir, "dashboard.json.gz")
    d = load_gz(p)
    fn(d)
    with open(p, "wb") as f:
        f.write(gzip.compress(json.dumps(d).encode("utf-8")))


def _day_doc(data, d):
    return load_gz(os.path.join(data, "review", "days", f"{d.isoformat()}.json.gz"))


def _feat(doc, i, f):
    return next(a for a in doc["apps"] if a["key"] == rs.K[i])["f"][f]


def test_first_shown_and_setup_kab_se_follow_the_snapshot_history(site, tmp_path):
    """'Pehli baar dikha' is the first review day of the run of snapshots that showed the row (only the go-live day says
    'jab ye page shuru hua'); a setup state with no real start date counts from the day it was first shown — never
    '<today> · 0 din se' every day."""
    data = str(tmp_path / "data")
    d0, d1, d2 = DAY - timedelta(2), DAY - timedelta(1), DAY
    for d in (d0, d1):
        res, _ = run(site, data, at_ist(d, "09:30"), today=d)
        assert res["ok"]
    assert os.path.exists(os.path.join(data, "review", "seen", f"{d1.isoformat()}.json"))
    assert not os.path.exists(os.path.join(site, "review", "seen")), "the history stays in data/"
    # on the third day a NEW setup problem appears (the login token of a1's account), a8's "no GA4 stream" continues
    _set_dash(site, lambda d: d["accounts"].__setitem__(0, {"account_id": rs.PUB, "token": "Expired"}))
    res, _ = run(site, data, at_ist(d2, "09:30"), today=d2)
    assert res["ok"]
    doc = _day_doc(data, d2)
    a1 = _feat(doc, 1, "kamai")                                   # a row without a dashboard "opened" date
    assert a1["q"]["naya"]["first"] == "29 Sep (jab ye page shuru hua)"
    ga4 = _feat(doc, 8, "setup")                                  # shown since go-live, no launch date
    assert ga4["q"]["kab"] == "29 Sep · 2 days ago (jab se ye page dekh raha hai)", ga4["q"]["kab"]
    tok = _feat(doc, 1, "setup")                                  # new today
    assert tok["st"] == "red" and tok["q"]["kab"] == "1 Oct · today", tok["q"]["kab"]
    assert tok["q"]["naya"]["first"] == "1 Oct (today)"
    raw = json.dumps(doc, ensure_ascii=False)
    assert "0 days ago" not in raw and "(0 days)" not in raw and "0 din se" not in raw
    # a snapshot whose history file is missing ends every run there (never a made-up older date)
    os.remove(os.path.join(data, "review", "seen", f"{d1.isoformat()}.json"))
    res, _ = run(site, data, at_ist(d2, "10:30"), today=d2, rebuild=True)
    assert res["ok"]
    assert _feat(_day_doc(data, d2), 8, "setup")["q"]["kab"] == "1 Oct · today"


def test_the_first_day_says_page_started_and_later_new_rows_say_aaj(site, tmp_path):
    data = str(tmp_path / "data")
    res, _ = run(site, data, at_ist(DAY, "09:30"))
    doc = _day_doc(data, DAY)
    assert _feat(doc, 1, "kamai")["q"]["naya"]["first"] == "1 Oct (jab ye page shuru hua)"
    assert _feat(doc, 8, "setup")["q"]["kab"] == "1 Oct · today (jab se ye page dekh raha hai)"
    h = rstore.load_history(data, DAY + timedelta(1), "2026-10-01")
    assert h["go_live"] == DAY and h["seen"][rs.K[1]] and all(v == DAY for v in h["seen"][rs.K[1]].values())


def test_an_ecpm_range_alert_is_money_never_a_rate_per_100(site):
    ra = lambda uid, app, metric, lo, hi, now: {"id": uid, "app": app, "place": "main_banner", "metric": metric,
                                                  "range": [lo, hi], "now": now, "severity": "watch"}
    _set_dash(site, lambda d: d.__setitem__("range_alerts", [
        ra(rs.UNIT[4], rs.DNAME[4], "ctr", 0.4, 0.5, 0.3), ra(rs.UNIT[4], rs.DNAME[4], "ecpm", 40.74, 104.11, 116.034),
        ra(rs.UNIT[5], rs.DNAME[5], "ecpm", 40.74, 104.11, 12.5), ra(rs.UNIT[5], rs.DNAME[5], "match", 0.9, 1.0, 0.7),
        ra(rs.UNIT[8], rs.DNAME[8], "ecpm", 40.74, 104.11, 116.034)]))
    doc = build_day(Site(site), DAY, now=rs.NOW)
    k4, k5 = _feat(doc, 4, "kamai"), _feat(doc, 5, "kamai")
    assert k4["st"] == "amber" and k5["st"] == "amber"
    t4, t5 = plain(k4["q"]["kya"]) + " · " + plain(k4["q"]["saath"]), plain(k5["q"]["kya"]) + " · " + plain(k5["q"]["saath"])
    assert "pe click rate" in t4 and ": 30%, range 40%–50%" in t4            # the rate head: a % (R3)
    assert "eCPM Aug me $116.0 (range $40.7–$104.1)" in t4, t4
    assert "11603" not in json.dumps(doc) and "4074" not in json.dumps(doc)
    assert "ka eCPM (main_banner): $12.5, range $40.7–$104.1" in t5, t5    # an eCPM head
    assert "click rate" not in plain(k5["q"]["kya"]) and "Match rate Aug me 70% (range 90%–100%)" in t5, t5
    assert "clicks" in k4["q"]["karo"] and "floor price" in k5["q"]["karo"]
    k8 = _feat(doc, 8, "kamai")                                               # an eCPM ABOVE its range
    assert "Range dobara approve" in k8["q"]["karo"] and "range se upar" in plain(k8["q"]["kit"])
    assert "100 me" not in plain(k8["q"]["kya"]) + plain(k8["q"]["kit"]) + k8["t"]
    assert "%" not in plain(k8["q"]["kya"]) + plain(k8["q"]["kit"])           # an eCPM is money, never a rate
    usd = [s for s in (k5["q"]["kya"] if isinstance(k5["q"]["kya"], list) else []) if isinstance(s, dict)]
    assert [s["usd"] for s in usd] == [12.5, 40.74, 104.11] and all(s["p"] == 2 for s in usd)   # money follows ₹/$


def test_headers_forbid_framing_everywhere():
    h = build_static.headers_text(["uninstall.json.gz"], {"active": {}, "value": {}})
    first = h.split("\n\n")[0]
    assert first.startswith("/*\n") and "  X-Frame-Options: DENY\n" in first + "\n"
    assert "  Content-Security-Policy: frame-ancestors 'none'" in first
