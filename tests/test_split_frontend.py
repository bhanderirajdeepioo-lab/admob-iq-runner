"""The installs vs per-user split on the page (SPEC_SPLIT §4, §6.2), rendered for real: tests/split_frontend.js runs the
page's own script in node on synthetic vectors written here (every kind, the spec's worked examples, a 10k random grid,
the pooled All-apps tile, the portfolio's week-over-week, the legacy fallback, the $ ⇄ ₹ toggle) and on the committed
fixtures (every host that carries a split draws its block). Checked: the parts add up to the total as shown (whole %s,
the installs part rounded on its own, the per-user part = shown total − the others), float dust never flips a %, the
status word only when the host has a verdict (copied, never recomputed), "pata nahi" (never a fake 0) when a part
cannot be computed, words (≤ 14 a line, no banned codes, Roman Hinglish only), the row markup, failure isolation, the
old lines kept for a host without a split, and parity with the engine's Python expand / line when it exists.
Synthetic data only. Skipped where node is not installed."""

import json
import math
import os
import random
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "tests", "fixtures")
ACT = os.environ.get("ACTIVE_FE_FIXTURE") or os.path.join(FX, "active_sample.json")
UNI = os.environ.get("UNINSTALL_FE_FIXTURE") or os.path.join(FX, "uninstall_sample.json")
VAL = os.environ.get("VALUE_FE_FIXTURE") or os.path.join(FX, "value_sample.json")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")
MINUS = "−"
BANNED = re.compile(r"\b(pts|pp|point|points|ARPDAU|cohort|headline)\b|/1k|\bD\d{1,3}\b", re.I)
DEVA = re.compile(r"[ऀ-ॿ]")
WORDS = {"bigda": "🔴 Bigda", "dhyan": "🟡 Dhyan do", "behtar": "🟢 Behtar", "normal": "⚪ Normal", "jaldi": "⏳ Abhi jaldi", "lagu_nahi": "— Lagu nahi"}


def R(x):
    """S4: to 6 decimals first (float dust never flips it), then half away from zero."""
    y = round(x, 6)
    a = math.floor(abs(y) + 0.5)
    return 0 if a == 0 else (-a if y < 0 else a)


def pct(n):
    return "0%" if n == 0 else ("+%d%%" % n if n > 0 else MINUS + "%d%%" % -n)


# ── the vectors ────────────────────────────────────────────────────────────────────────────────────────────────────
EX = [  # (id, kind, host, money) — SPEC_SPLIT §4.4's worked examples and one of every other kind
    ("rr", "rate", {"sp": ["rr", 5000, 6000], "before": 0.30, "now": 0.27, "severity": "warning", "metric": "d1"}, None),
    ("uc", "uc", {"sp": ["uc", 1200, 1824, 1200, 1440, 4000, 5000, 45], "severity": "warning"}, None),
    ("imp", "imp_dau", {"sp": ["imp", 800, 400, 4000, 4600], "before": 40000, "after": 38800, "expected": 41200, "status": "worse"}, None),
    ("rev", "rev", {"sp": ["rev", 500000, 450000], "base": 2.0, "v": 920 * 1000 / 450000, "st": "normal"}, "act"),
    ("vpi", "vpi", {"sp": ["vpi", 5, 4.8, 10, 12], "st": "watch"}, "val"),
    ("ret", "act_tile_ret", {"sp": ["ret", 10000, 200000, 206000, 50000, 56000, 14.0, 13.1, 30, 0], "base": 1000000, "v": 1070000, "st": "better", "_k": 30}, None),
    ("ur", "rate", {"sp": ["ur", 1000, 1200], "before": 0.30, "now": 0.33, "n": 1, "severity": "watch"}, None),
    ("uk", "uni_verdict", {"prev": {"users": 28000, "k": 28, "left": 0.6}, "recent": {"users": 33600, "k": 28, "left": 0.55}, "n": 7, "dir": "worse"}, None),
    ("ir", "ir", {"sp": ["ir", 1000, 1200], "base": 0.05, "v": 0.045, "st": "watch"}, "val"),
    ("spd", "spd", {"sp": ["spd", 1000, 1500, 0.08, 0.1], "st": "worse"}, "val"),
    ("dau", "dau", {"before": 100000, "after": 107000, "nb": 5000, "na": 7000}, None),
    ("info", "act_info_ret", {"sp": ["ret", 2400, 8000, 10400, 1000, 1300, 10, 10, 30, 0, 20000], "rel": 0.12, "kind": "installs"}, None),
    ("alert_ret", "act_alert_ret", {"sp": ["ret", -1500, 3375, 1785, 900, 500, 10.4, 9.9, 30, 1], "before": 20000, "now": 18000, "severity": "warning"}, None),
    ("elastic", "act_tile_ret", {"sp": ["ret", -0.057 * 21180, 0, 0, 1000, 670, None, None, None, 3], "base": 21180, "v": 21180 * 1.075, "st": "normal"}, None),
    ("row_ret", "act_row_ret", {"sp": ["ret", 300, 1200, 1440, 800, 1000, 6.25, 6.0, 30, 0], "s": [7 * 10500, 7, 28 * 10000, 28], "st": "normal"}, None),
    ("tile_rr", "act_tile_rr", {"sp": ["rr", 500, 750], "s": [1470, 5250, 4200, 14000], "n": 7, "nb": 28, "st": "worse", "_days": 1}, None),
    ("imp_rate", "imp_rate", {"before": 0.30, "after": 0.28, "status": "worse", "_days": 7,
                              "extra": {"installs_before": 7000, "installs_after": 10500, "cohorts_before": 7, "cohorts_after": 7}}, None),
    ("d0_row", "rate", {"sp": ["ur", 1000, 800], "before": 0.30, "after": 0.33, "status": "same", "_days": 0}, None),
    ("cell", "rate", {"sp": ["ur", 900, 1100], "p": 0.45, "prev": 0.40, "alert": False, "_days": 7}, None),
    ("cp_row", "rate", {"sp": ["ur", 5000, 5000], "n": 30, "recent": {"p": 0.5}, "prev": {"p": 0.45}, "all": {"p": 0.4}}, None),
    ("cp_all", "rate", {"sp": ["ur", 5000, 5000], "n": 30, "recent": {"p": 0.5}, "prev": None, "all": {"p": 0.4}}, None),
    ("geo_pp", "rate", {"sp": ["rr", 120, 310], "before": 28.0, "now": 16.79, "unit": "pp", "family": "geo_move", "severity": "watch", "metric": "d1"}, None),
    ("geo_ir", "ir", {"sp": ["ir", 120, 310], "before": 0.021, "now": 0.018, "severity": "watch"}, "val"),
    ("imp_long", "imp_dau", {"sp": ["imp", 500, -300], "before": 30000, "after": 31000, "status": "better"}, None),
    ("rev_note", "rev", {"sp": ["rev", 20000, 21000, ["new", 4.1, 6.3]], "base": 7.9, "v": 8.0, "st": "normal"}, "act"),
    ("pu", "pu", {"sp": ["pu", ["new", 5, 9]]}, None),
    ("pu_net", "pu", {"sp": ["pu", ["net", 20, 30]]}, None),
    ("none", "act_tile_ret", {"sp": ["no", "cohorts"], "base": 100, "v": 110}, None),
    ("none_steep", "imp_dau", {"sp": ["no", "steep"], "before": 1, "after": 2, "status": "worse"}, None),
    ("none_err", "rate", {"sp": ["no", "error"], "before": 0.3, "now": 0.2}, None),
    ("base0", "rate", {"sp": ["rr", 0, 100], "before": 0.3, "now": 0.2, "severity": "watch"}, None),
    ("null", "rate", {"sp": None, "before": 0.3, "now": 0.2}, None),
    ("absent", "rate", {"before": 0.3, "now": 0.2}, None),
    ("pending", "imp_dau", {"sp": ["imp", 1, 1], "before": 10, "after": 12, "status": "pending"}, None),
    ("dust", "dau", {"before": 100, "after": 107.49999999, "nb": 10, "na": 10}, None),
    ("mask", "rate", {"sp": ["rr", 1000, 2000], "before": 0.5, "now": 0.2525, "severity": "good", "metric": "d1"}, None),
    # the review's findings: installs ×0.1 / ×6 (counts, never −300% or +15% beside "100 me 20 → 50"), per-100 values
    # that round alike, a per-user part under one person a day, which way a steep app moves, a closed change
    ("x01", "rate", {"sp": ["ur", 1000, 100], "before": 0.20, "now": 0.50, "severity": "warning", "n": 0}, None),
    ("x6", "rate", {"sp": ["ur", 100, 600], "before": 0.40, "now": 0.20, "severity": "good", "n": 0}, None),
    ("x4_d1", "act_tile_rr", {"sp": ["rr", 1000, 4000], "s": [4200, 28000, 8400, 28000], "n": 7, "nb": 28, "st": "worse", "_days": 1}, None),
    ("p100eq", "rate", {"sp": ["ur", 1000, 1000], "before": 0.124, "now": 0.116, "severity": "good", "n": 1}, None),
    ("p100near", "act_alert_ret", {"sp": ["ret", -100, 1000, 800, 1000, 900, 10.4, 9.9, 30, 0], "before": 20000, "now": 19700, "severity": "watch"}, None),
    ("tiny", "rate", {"sp": ["rr", 3, 3], "before": 0.30, "now": 0.31, "severity": "good", "metric": "d1"}, None),
    ("steep_up", "imp_dau", {"sp": ["no", "steep_up"], "before": 1, "after": 2, "status": "low"}, None),
    ("steep_dn", "imp_dau", {"sp": ["no", "steep_dn"], "before": 2, "after": 1, "status": "low"}, None),
    ("closed", "act_alert_ret", {"sp": ["ret", -500, 3000, 2600, 900, 750, 10, 10, 30, 0], "before": 20000, "now": 18000, "severity": "warning",
                                 "closed": "2026-09-24"}, None),
    ("spd_x2", "spd", {"sp": ["spd", 1000, 2000, 0.06, 0.096], "st": "watch"}, "val"),
    ("vpi_cost", "vpi", {"sp": ["vpi", 0.022, 0.0222, 0.06, 0.096], "st": "worse"}, "val"),
]
# the status copy map (§2.4) on one rate host: [host keys, the word or None] — the rate fell (the bad way for a return
# rate) on every host but a "better" one, where it rose: a word is kept only beside a part that points its way; a
# "maybe" / "unsure" gets none (its own chip says it), nor does a closed change
STATUS = [({"severity": "warning"}, "bigda"), ({"severity": "watch"}, "dhyan"), ({"severity": "good", "now": 0.32}, "behtar"),
          ({"status": "worse"}, "bigda"), ({"status": "better", "now": 0.32}, "behtar"), ({"status": "same"}, "normal"), ({"status": "unsure"}, None),
          ({"status": "market"}, "normal"), ({}, None), ({"_st": None, "severity": "warning"}, None),
          ({"severity": "good"}, None), ({"severity": "warning", "now": 0.32}, None), ({"severity": "warning", "closed": "2026-09-24"}, None)]
ACT_ST = {"worse": "bigda", "watch": "dhyan", "slow": "dhyan", "break": "dhyan", "better": "behtar", "normal": "normal", "maybe_dn": None,
          "maybe_up": None, "price_dn": "normal", "price_up": "normal", "growth": "jaldi", "low": "jaldi", "wait": "jaldi", "noad": "lagu_nahi"}
VAL_ST = {"worse": "bigda", "never": "bigda", "watch": "dhyan", "better": "behtar", "normal": "normal", "maybe": None, "maybe_up": None,
          "low": "jaldi", "wait": "jaldi", "thin": "jaldi", "nospend": "lagu_nahi"}


def vectors():
    V = [{"id": i, "kind": k, "host": h, "money": m} for i, k, h, m in EX]
    for j, (extra, _) in enumerate(STATUS):
        V.append({"id": "st%d" % j, "kind": "rate", "host": dict({"sp": ["rr", 1000, 1100], "before": 0.3, "now": 0.28}, **extra), "money": None})
    for s, w in ACT_ST.items():   # the share came back: 30 → 28 of 100 (the bad way), 30 → 32 beside a "better"
        V.append({"id": "act_" + s, "kind": "act_tile_rr", "host": {"sp": ["rr", 1, 1], "s": [320 if w == "behtar" else 280, 1000, 1200, 4000],
                                                                    "n": 7, "nb": 28, "st": s}, "money": None})
    for s, w in VAL_ST.items():   # the cost per install rose (the bad way), fell beside a "better"
        V.append({"id": "val_" + s, "kind": "spd", "host": {"sp": ["spd", 100, 110, 1.0, 0.9 if w == "behtar" else 1.1], "st": s}, "money": "val"})
    return V


def grid(n=10000):
    rnd = random.Random(20260928)
    G = []
    for i in range(n):
        t = i % 3
        if t == 0:   # a rate: installs and the share both move (incl. tiny totals with big opposite parts)
            ib = rnd.choice([rnd.uniform(1, 50), rnd.uniform(50, 5e4)])
            G.append({"kind": "rate", "host": {"sp": ["rr", ib, ib * rnd.uniform(0.2, 3)], "before": rnd.uniform(0.01, 0.9), "now": rnd.uniform(0.01, 0.9)}})
        elif t == 1:   # returning users: before, after, the installs' part
            b = rnd.uniform(100, 2e6)
            fi = b * rnd.uniform(-0.4, 0.4)
            G.append({"kind": "act_alert_ret", "host": {"sp": ["ret", fi, b * 0.1, b * 0.1 + fi * rnd.uniform(0, 1.2), 10, 12, None, None, None, 0], "before": b, "now": b * rnd.uniform(0.5, 1.6)}})
        else:   # update impact: with a trend
            b = rnd.uniform(100, 2e5)
            G.append({"kind": "imp_dau", "host": {"sp": ["imp", b * rnd.uniform(-0.2, 0.2), b * rnd.uniform(-0.1, 0.1)], "before": b, "after": b * rnd.uniform(0.6, 1.5), "status": "same"}})
    return G


def pool_rows():
    def row(before, after, sp, st="normal"):
        m = {"s": [7 * after, 7, 28 * before, 28], "st": st}
        if sp is not None:
            m["sp"] = sp
        return {"app": "a", "m": {"ret_dau": m}}
    full = [row(1000000, 1080000, ["ret", 12000, 140000, 150000, 40000, 45000, 11.7, 11.5, 30, 0]),
            row(400000, 410000, ["ret", -3000, 50000, 49000, 15000, 13000, 11.1, 11.9, 30, 1]),
            row(50000, 52000, ["ret", 500, 6000, 6400, 2000, 2200, 10.0, 9.5, 30, 0])]
    part = full[:2] + [row(2000000, 2100000, ["no", "cohorts"])]
    most = full + [row(40000, 41000, ["no", "cohorts"])]      # 3% of the level without a split: counted, and said
    legacy = [row(1000, 1100, None), row(2000, 2100, None)]
    wait = full + [row(900000, 950000, None, st="wait")]   # a waiting app is not in the pool at all
    return [full, part, legacy, wait, most]


def wow_series():
    z = [0] * 8
    ok = {"wnc": z[:7] + [3], "wowc": z[:7] + [3], "wow": [None] * 7 + [0.07], "wa0": z[:7] + [100000], "wa1": z[:7] + [107000],
          "wn0": z[:7] + [5000], "wn1": z[:7] + [7000]}
    miss = dict(ok, wnc=z[:7] + [2])   # one of the 3 apps has no installs number on one of the days: no split
    return [ok, miss]


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        html = f.read()
    d = tmp_path_factory.mktemp("split")
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    (d / "app.js").write_text(js, encoding="utf-8")
    subprocess.run([NODE, "--check", str(d / "app.js")], check=True, capture_output=True)
    vec = {"vectors": vectors(), "grid": grid(), "pool": pool_rows(), "wow": wow_series()}
    (d / "vec.json").write_text(json.dumps(vec), encoding="utf-8")
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "split_frontend.js"), str(d / "app.js"), str(d / "vec.json"), ACT, UNI, VAL],
                         check=True, capture_output=True, text=True, timeout=300)
    r = json.loads(out.stdout)
    r["by"] = {v["id"]: v for v in r["vec"]}
    r["input"] = vec
    return r


def lines(r, i):
    return [x["t"] for x in r["by"][i]["lines"]]


def test_the_page_runs_every_vector_without_errors(report):
    assert report["errors"] == []
    assert len(report["vec"]) == len(report["input"]["vectors"]) and len(report["grid"]) == 10000


def test_the_spec_worked_examples_read_exactly(report):
    assert lines(report, "rr") == ["Roz wapas aane wale (agle din): +8% (1,500 → 1,620)",
                                   "• installs ki wajah se: +20% (installs +20%; 100 me 30 wapas aate)",
                                   "• asli badlaav: −12% (100 me 30 → 27) → 🔴 Bigda",
                                   "roz ~6,000 installs pe ~180 kam wapas"]
    assert report["by"]["rr"]["line"] == "roz wapas aane wale: kul +8% = installs se +20% + asli −12%"
    assert lines(report, "uc") == ["Roz uninstall: +52% (1,200 → 1,824)",
                                   "• installs ki wajah se: +20% (installs +25%; 100 me ~45 pehle 28 din me hata dete)",
                                   "• asli badlaav: +32% (har install pe +27%) → 🔴 Bigda"]
    assert lines(report, "imp") == ["Purane users roz: −3% (40,000 → 38,800)", "• installs ki wajah se: +2% (installs +15%)",
                                    "• pehle se chal raha trend: +1%", "• update ka asar: −6% → 🔴 Bigda"]
    assert report["by"]["imp"]["line"] == "purane users roz: kul −3% = installs se +2% + trend +1% + update −6%"
    assert lines(report, "rev") == ["Kamai roz: −8% ($1,000 → $920)", "• users ki ginti se: −10% (users −10%; har 1,000 users se $2.00)",
                                    "• asli badlaav (har user se kamai): +2% (har 1,000 users se $2.00 → $2.04) → ⚪ Normal"]
    assert report["by"]["rev"]["line"] == "kamai roz: kul −8% = users se −10% + asli +2%"
    assert lines(report, "vpi") == ["$100 pe wapas (7 din me): −20% ($50 → $40)", "• install ke daam ki wajah se: −17% (ek install $10.00 → $12.00)",
                                    "• asli badlaav (kamai per install): −3% (ek install se $5.00 → $4.80) → 🟡 Dhyan do"]
    assert report["by"]["vpi"]["line"] == "paisa wapas: kul −20% = daam se −17% + kamai se −3%"
    # returning users: the installs moving at the before return per install; the per-user part holds the 30+ day old
    # users and the recent installs' own return (its per-100 before → after on its own line)
    assert lines(report, "ret") == ["Purane users roz: +7% (10 lakh → 10.7 lakh)",
                                    "• installs ki wajah se: +1% (installs +12%; 30 din ke 100 installs me se ~14 roz aate)",
                                    "• asli badlaav: +6% (30+ din purane users khud +8%) → 🟢 Behtar",
                                    "naye users ki wapsi: 100 me ~14 → ~13.1 roz"]


def test_every_kind_reads_as_its_basis_says(report):
    assert lines(report, "ur") == ["Roz hataane wale (agle din): +32% (300 → 396)", "• installs ki wajah se: +20% (installs +20%; 100 me 30 hataate)",
                                   "• asli badlaav: +12% (100 me 30 → 33) → 🟡 Dhyan do", "roz ~1,200 installs pe ~36 zyada hataate"]
    assert lines(report, "uk") == ["Roz bache hue (7 din baad): +10% (600 → 660)", "• installs ki wajah se: +20% (installs +20%; 100 me 60 bache rehte)",
                                   "• asli badlaav: −10% (100 me 60 → 55) → 🔴 Bigda", "roz ~1,200 installs pe ~60 kam bache"]
    assert lines(report, "ir") == ["Installs se kamai / hafta: +8% ($50 → $54)", "• installs ki wajah se: +20% (installs +20%; ek install se $0.050)",
                                   "• asli badlaav (har install se kamai): −12% ($0.050 → $0.045) → 🟡 Dhyan do"]
    assert lines(report, "spd")[0] == "Ads kharcha / hafta: +88% ($80 → $150)" and lines(report, "spd")[1].startswith("• installs ki wajah se: +50% (installs +50%; ek install $0.080 ka)")
    assert lines(report, "dau") == ["Active users (pichhle hafte ke same din se): +7% (1 lakh → 1.07 lakh)", "• naye installs se: +2% (installs +40%)", "• purane users se: +5%"]
    assert report["by"]["dau"]["line"] == "active users: kul +7% = naye installs se +2% + purane users se +5%"
    # the per-100's days travel with the split (an info row / an alert say "30 din ke" as the tile does)
    assert lines(report, "info") == ["Purane users roz: +12% (20,000 → 22,400)", "• installs ki wajah se: +12% (installs +30%; 30 din ke 100 installs me se ~10 roz aate)",
                                     "• asli badlaav: 0% → ⚪ Normal"]
    # an estimate (elastic mode / est flag) says so; khud only when it differs from the shown per-user part
    assert lines(report, "alert_ret") == ["Purane users roz: −10% (20,000 → 18,000)",
                                          "• installs ki wajah se: −8% (installs −44%; 30 din ke 100 installs me se ~10.4 roz aate) · ≈ Andaza",
                                          "• asli badlaav: −2% → 🔴 Bigda", "naye users ki wapsi: 100 me ~10.4 → ~9.9 roz"]
    assert lines(report, "elastic") == ["Purane users roz: +8% (21,180 → 22,769)", "• installs ki wajah se: −6% (installs −33%) · ≈ Andaza",
                                        "• asli badlaav: +14% → ⚪ Normal"]
    assert lines(report, "imp_rate")[0] == "Roz wapas aane wale (7 din baad): +40% (300 → 420)"
    assert lines(report, "d0_row")[0].startswith("Roz hataane wale (install ke din hi): ")
    assert lines(report, "cell")[0].startswith("Roz hataane wale (7 din me): ") and not any(w in t for w in WORDS.values() for t in lines(report, "cell"))
    # a checkpoint row's base: the one its arrow shows (4 weeks before, else all time)
    assert "(100 me 45 → 50)" in lines(report, "cp_row")[2] and "(100 me 40 → 50)" in lines(report, "cp_all")[2]
    # Install value's per-100 country rates (unit pp) read as a share of 100
    assert "(100 me 28 → 17; roz ~310 installs pe)" in lines(report, "geo_pp")[2] and lines(report, "geo_pp")[0].startswith("Roz wapas aane wale (agle din): ")
    assert lines(report, "imp_long")[1] == "• installs ki wajah se: +2%"                   # 14 / 30 / 60 days: no installs %
    assert lines(report, "rev_note")[-1] == "Saath me: naye users ka hissa 100 me 4.1 → 6.3"
    assert lines(report, "pu") == ["Saath me: naye users ka hissa 100 me 5 → 9"] and report["by"]["pu"]["line"] == ""
    assert lines(report, "pu_net") == ["Saath me: dusre ad networks ka hissa badla"]
    assert report["by"]["row_ret"]["S"]["total"]["before"] == 10000 and report["by"]["row_ret"]["S"]["total"]["after"] == 10500
    assert report["by"]["tile_rr"]["S"]["installs"]["before"] == 500 and report["by"]["tile_rr"]["S"]["installs"]["after"] == 750


def test_parts_add_up_as_shown(report):
    for v in report["vec"]:
        S = v["S"]
        if not S or "shown" not in S:
            continue
        s, T = S["shown"], S["total"]
        assert s["total"] == R(100 * T["rel"]) and s["from_installs"] == R(100 * S["from_installs"]["rel"]), v["id"]
        assert s["per_user"] == s["total"] - s["from_installs"] - (s["trend"] or 0), v["id"]
        assert abs(S["from_installs"]["abs"] + ((S["trend"] or {}).get("abs") or 0) + S["per_user"]["abs"] - (T["after"] - T["before"])) <= 1e-6 * max(1, abs(T["before"]))
        # the printed parts add up too: Kul % = the bullets' %s, or (the count form) the numbers a day add up
        txt = " ".join(lines(report, v["id"]))
        if S["form"] == "count":
            C = s["count"]
            assert C["total"] == C["from_installs"] + (C["trend"] or 0) + C["per_user"], v["id"]
            assert len(re.findall(r": ~[+−]?", txt)) == 2 + (1 if C["trend"] else 0), (v["id"], txt)
            continue
        nums = [int(x.replace(MINUS, "-")) for x in re.findall(r": ([+−]?\d+)%", txt)]
        if nums:
            assert nums[0] == sum(nums[1:]), (v["id"], nums)
    worst = 0
    for g, x in zip(report["input"]["grid"], report["grid"]):
        assert x is not None
        t, f, tr, p, prel, trel, frel, rrel, line = x
        assert t == R(100 * trel) and f == R(100 * frel) and (tr is None or tr == R(100 * rrel))
        assert p == t - f - (tr or 0)
        worst = max(worst, abs(p - 100 * prel))
        assert abs(p - 100 * prel) <= (1.5 if tr is not None else 1.0 + 1e-9), (g, x)
        assert line.endswith(" (kul %s)" % pct(t)) if "~" in line else (": kul %s = " % pct(t) in line and pct(p) in line)
    assert worst > 0.5                                                               # the grid does reach the rounding edge


def test_float_dust_never_flips_a_percent(report):
    assert report["by"]["dust"]["S"]["shown"]["total"] == 8                           # 7.49999999 → 7.5 → +8%
    # installs ×2 masking a halved rate: counts a day (never "−99%"), and no "Behtar" beside a part that fell
    assert lines(report, "mask") == ["Roz wapas aane wale (agle din): +1% (500 → 505)", "• installs ki wajah se: ~+500 roz (installs +100%; 100 me 50 wapas aate)",
                                     "• asli badlaav: ~−490 roz (100 me 50 → 25; roz ~2,000 installs pe)"]


def test_unknown_is_said_never_a_fake_zero(report):
    by = report["by"]
    assert lines(report, "none") == ["Installs ka hissa: pata nahi — naye users ki wapsi ka data nahi"] and by["none"]["line"] == ""
    assert lines(report, "none_steep") == ["Installs ka hissa: pata nahi — app tezi se badal rahi"]
    assert lines(report, "steep_up") == ["Installs ka hissa: pata nahi — app tezi se badh rahi"]
    assert lines(report, "steep_dn") == ["Installs ka hissa: pata nahi — app tezi se ghat rahi"]
    assert lines(report, "base0") == ["Installs ka hissa: pata nahi — pehle ka number nahi"] and by["base0"]["S"]["none"] == "base"
    for i in ("none_err", "null", "absent", "pending"):
        assert by[i]["html"] == "" and by[i]["line"] == "", i
    assert by["none_err"]["S"]["none"] == "error" and by["null"]["S"] is None and by["pending"]["S"] is None


def test_the_status_word_is_copied_from_the_verdict_only(report):
    for j, (extra, want) in enumerate(STATUS):
        S = report["by"]["st%d" % j]["S"]
        assert S["per_user"]["status"] == want, (extra, S["per_user"]["status"])
        last = lines(report, "st%d" % j)[2]
        assert (WORDS[want] in last) if want else not any(w in last for w in WORDS.values()), last
    for s, w in ACT_ST.items():
        assert report["by"]["act_" + s]["S"]["per_user"]["status"] == w, s
    for s, w in VAL_ST.items():
        assert report["by"]["val_" + s]["S"]["per_user"]["status"] == w, s


def test_words_are_short_roman_and_free_of_codes(report):
    for v in report["vec"]:
        for t in [x["t"] for x in v["lines"]] + [v["line"]]:
            assert "NaN" not in t and "undefined" not in t and "[object Object]" not in t and "Infinity" not in t, (v["id"], t)
            assert not DEVA.search(t), (v["id"], t)
            assert not BANNED.search(t), (v["id"], t)
            assert len([w for w in t.split() if re.search(r"[A-Za-z]", w)]) <= 14, (v["id"], t)
        assert len([w for w in v["line"].split() if re.search(r"[A-Za-z]", w)]) <= 12, v["line"]


def test_a_row_block_keeps_the_row_markup(report):
    """In a "What changed?" row the block is the row's last child, span markup: the row still ends the way every row does."""
    for v in report["vec"]:
        assert v["row_end"], v["id"]
        assert [x["t"] for x in v["row_lines"]] == [x["t"] for x in v["lines"]], v["id"]


def test_the_reviews_findings_read_as_the_owner_needs(report):
    """Installs ×0.1 / ×6 read as numbers a day that add up (never "−300%", never "+15%" beside 100 me 20 → 50); a
    per-100 or money pair never prints one number twice; no line about a fraction of a person; the verdict word only
    beside a part that points its way, never on a closed change; the price of an install named apart from its role."""
    assert lines(report, "x01") == ["Roz hataane wale (install ke din hi): −75% (200 → 50)",
                                    "• installs ki wajah se: ~−180 roz (installs −90%; 100 me 20 hataate)",
                                    "• asli badlaav: ~+30 roz (100 me 20 → 50; roz ~100 installs pe) → 🔴 Bigda"]
    assert report["by"]["x01"]["line"] == "roz hataane wale: ~−150 = installs se ~−180 + asli ~+30 (kul −75%)"
    assert lines(report, "x6")[2] == "• asli badlaav: ~−120 roz (100 me 40 → 20; roz ~600 installs pe) → 🟢 Behtar"
    assert lines(report, "x4_d1")[2] == "• asli badlaav: ~−600 roz (100 me 30 → 15; roz ~4,000 installs pe) → 🔴 Bigda"
    assert lines(report, "p100eq")[2] == "• asli badlaav: −6% (100 me 12.4 → 11.6) → 🟢 Behtar"
    assert lines(report, "p100near")[-1] == "naye users ki wapsi: 100 me ~10.4 → ~9.9 roz"
    assert lines(report, "tiny") == ["Roz wapas aane wale (agle din): +3% (0.90 → 0.93)",
                                     "• installs ki wajah se: 0% (installs 0%; 100 me 30 wapas aate)",
                                     "• asli badlaav: +3% (100 me 30 → 31) → 🟢 Behtar"]           # no "~0.03 zyada" line
    assert not any(w in t for w in WORDS.values() for t in lines(report, "closed"))
    assert lines(report, "spd_x2")[2].startswith("• asli badlaav (ek install ka daam): ~+$70 / hafta ($0.060 → $0.096)")
    assert report["by"]["spd_x2"]["line"] == ""                                   # money counts: only in the block
    assert lines(report, "vpi_cost") == ["$100 pe wapas (7 din me): −37% ($37 → $23)",
                                         "• install ke daam ki wajah se: −38% (ek install $0.060 → $0.096)",
                                         "• asli badlaav (kamai per install): +1% (ek install se $0.022 → $0.0222)"]
    for v in report["vec"]:                                                       # never an impossible-looking %
        S = v["S"]
        if S and S.get("form") == "pct":
            assert min(S["shown"]["from_installs"], S["shown"]["per_user"]) > -100, v["id"]
        for t in [x["t"] for x in v["lines"]]:
            assert "e-" not in t and not re.search(r"~0\.\d+ (kam|zyada)", t), (v["id"], t)
            m = re.search(r"100 me ~?([\d.]+) → ~?([\d.]+)", t)
            if m and S and S.get("per_user") and abs(S["per_user"]["own"] or 0) >= 0.01:
                assert m.group(1) != m.group(2), (v["id"], t)


def test_the_currency_toggle_changes_only_money(report):
    for i in ("rev", "ir", "vpi", "spd", "rev_note"):
        usd, inr = report["by"][i]["text"], report["by"][i]["inr_text"]
        assert "₹" in inr and "$" not in inr and "$" in usd, i
        assert re.findall(r"[+−]?\d+%", usd) == re.findall(r"[+−]?\d+%", inr), i
    assert report["by"]["rev"]["inr_text"].startswith("Kamai roz: −8% (₹83,000 → ₹76,360)")
    assert report["by"]["vpi"]["inr_text"].startswith("₹100 pe wapas (7 din me): −20% (₹50 → ₹40)")


def pool_ref(rows):
    """The pooled All-apps tile, by hand (SPEC_SPLIT F1): Σ of the covered apps' own parts over every app with a level."""
    el, cov = [], []
    for r in rows:
        m = r["m"]["ret_dau"]
        s = m["s"]
        el.append(s[2] / s[3])
        if isinstance(m.get("sp"), list) and m["sp"][0] == "ret":
            cov.append((s[2] / s[3], s[0] / s[1], m["sp"]))
    B, A = sum(c[0] for c in cov), sum(c[1] for c in cov)
    fi, yb, yw = sum(c[2][1] for c in cov), sum(c[2][2] for c in cov), sum(c[2][3] for c in cov)
    return {"B": B, "A": A, "fi": fi, "cov": len(cov), "of": len(el), "all": sum(el), "own": (A - yw) / (B - yb) - 1,
            "pb": 100 * yb / sum(100 * c[2][2] / c[2][6] for c in cov), "pa": 100 * yw / sum(100 * c[2][3] / c[2][7] for c in cov),
            "nb": sum(c[2][4] for c in cov), "na": sum(c[2][5] for c in cov)}


def test_the_pooled_all_apps_tile(report):
    full, part, legacy, wait, most = report["pool"]
    assert most["text"].startswith("3 apps ke purane users roz (4 me se): ")
    ref = pool_ref(report["input"]["pool"][0])
    S = full["S"]
    assert S["apps"] == {"of": 3, "with": 3} and abs(S["total"]["before"] - ref["B"]) < 1e-6 and abs(S["total"]["after"] - ref["A"]) < 1e-6
    assert abs(S["from_installs"]["abs"] - ref["fi"]) < 1e-9 and abs(S["per_user"]["own"] - ref["own"]) < 1e-12
    assert abs(S["per100"]["before"] - ref["pb"]) < 1e-9 and abs(S["per100"]["after"] - ref["pa"]) < 1e-9
    assert S["installs"]["before"] == ref["nb"] and S["installs"]["after"] == ref["na"]
    assert S["est"] is True and S["per_user"]["status"] is None                     # one app's part is an estimate; no verdict pooled
    assert full["text"].startswith("Purane users roz (sab 3 apps): ") and "≈ Andaza" in full["text"]
    assert not any(w in full["text"] for w in WORDS.values())
    # an app without a split holds more than 10% of the pooled level → said, never a partial number
    assert part["S"]["none"] == "apps" and part["S"]["apps"] == {"of": 3, "with": 2}
    assert part["text"] == "Installs ka hissa: pata nahi — kuch apps ka hisaab nahi"
    assert legacy["S"]["none"] == "apps" and legacy["S"]["apps"] == {"of": 2, "with": 0}   # (the page never asks without a split)
    assert wait["S"]["apps"] == {"of": 3, "with": 3} and wait["text"] == full["text"]   # a waiting app: not in the tile, not here
    assert report["pool_page"] == {"live": True, "legacy": False}                     # the All-apps page: only with the split


def test_the_portfolio_week_over_week(report):
    ok, miss = report["wow"]
    assert ok == "active users: kul +7% = naye installs se +2% + purane users se +5%"
    assert miss == ""


def test_every_helper_is_failure_isolated(report):
    assert report["isolated"] == [None, "", "", None, ""]


def test_a_host_without_a_split_keeps_its_old_lines(report):
    L = report["legacy"]
    assert not L["legacy"]["split"] and "Installs −33% vs 4 weeks" in L["legacy"]["text"]         # an older file: today's line
    assert not L["nul"]["split"] and "Installs −33% vs 4 weeks" in L["nul"]["text"]               # SPLIT off (sp: null): the same
    t = L["withSp"]["text"]
    assert L["withSp"]["split"] and "Installs −33% vs 4 weeks" not in t and "pts" not in t        # the block replaces it
    assert "Purane users roz: +8% (" in t and "installs ki wajah se: −6% (installs −33%) · ≈ Andaza" in t and "asli badlaav: +14%" in t
    # a split that can't be worked out adds its grey line and takes no shown fact away: the installs' own change stays,
    # never the old installs part beside a "pata nahi" (no fake number, no "pts")
    n = L["none"]["text"]
    assert L["none"]["split"] and "Installs ka hissa: pata nahi — naye users ki wapsi ka data nahi" in n
    assert "Installs −33% vs 4 weeks" in n and "vs 4 weeks —" not in n and "pts" not in n
    e = L["err"]["text"]                                                                           # an engine failure: no block
    assert not L["err"]["split"] and "Installs −33% vs 4 weeks" in e and "vs 4 weeks —" not in e and "pts" not in e
    # a "What changed?" row: the Installs tag goes when the block tells it
    assert ">Installs</span>" in L["row0"]["html"] and 'class="split' not in L["row0"]["html"]
    assert ">Installs</span>" not in L["row1"]["html"] and 'class="split' in L["row1"]["html"] and L["row1"]["html"].endswith("</span></span></div>")
    # …but a notes-only or a "pata nahi" split does not tell the installs' part: the tag stays beside it
    assert ">Installs</span>" in L["row2"]["html"] and "Saath me: naye users ka hissa 100 me 5 → 9" in L["row2"]["text"]
    assert ">Installs</span>" in L["row3"]["html"]


def close(a, b, path=""):
    """a == b, floats to 1e-9 (relative)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in set(a) | set(b):
            out += close(a.get(k), b.get(k), path + "." + k)
        return out
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            return [path]
        return [x for i, (p, q) in enumerate(zip(a, b)) for x in close(p, q, "%s[%d]" % (path, i))]
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return [] if a == b else [path + ": %r != %r" % (a, b)]
    return [] if abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b)) else [path + ": %r != %r" % (a, b)]


def test_parity_with_the_engine_expand_line_and_pool(report):
    attrib = pytest.importorskip("admob_iq.engine.attrib")
    if not all(hasattr(attrib, f) for f in ("expand", "line", "pool")):
        pytest.skip("admob_iq.engine.attrib has no expand / line / pool yet")
    bad = []
    for v in report["input"]["vectors"]:
        if v["kind"] == "dau":                                                       # JS only (the portfolio file has no Python side)
            continue
        h = {k: x for k, x in v["host"].items() if not k.startswith("_")}
        py = attrib.expand(v["kind"], h, k=v["host"].get("_k"), days=v["host"].get("_days"), alerts=v["host"].get("_alerts"))
        js = report["by"][v["id"]]["S"]
        if "_st" in v["host"] and py and js and "per_user" in py:                   # the page's own status override
            py = dict(py, per_user=dict(py["per_user"], status=js["per_user"]["status"]))
        bad += [(v["id"], d) for d in close(py, js)]
        if attrib.line(py) != report["by"][v["id"]]["line"]:
            bad.append((v["id"], attrib.line(py), report["by"][v["id"]]["line"]))
    for i, rows in enumerate(report["input"]["pool"]):
        bad += [("pool%d" % i, d) for d in close(attrib.pool([r["m"]["ret_dau"] for r in rows]), report["pool"][i]["S"])]
    grid = report["input"]["grid"]
    for g, x in list(zip(grid, report["grid"]))[:3000]:
        py = attrib.expand(g["kind"], g["host"])
        if [py["shown"][k] for k in ("total", "from_installs", "trend", "per_user")] != x[:4] or attrib.line(py) != x[8]:
            bad.append((g, x))
    assert bad == []


# ── the fixtures (once the regenerated fixtures carry the split) ────────────────────────────────────────────────────

def test_every_host_with_a_split_draws_its_block(report):
    F = report["fixtures"]
    if not F["any"]:
        pytest.skip("the committed fixtures carry no split yet (regenerate them with the engine that writes sp)")
    assert F["missing"] == [] and F["bad"] == [] and F["hosts"] > 0 and F["blocks"] == F["hosts"]
    assert F.get("notes", 0) >= 1 and F.get("impNotes", 0) >= 1          # the "Saath me:" lines, each said once
    for t in F["texts"]:
        assert not DEVA.search(t) and not BANNED.search(t), t


def test_the_pooled_tile_on_the_fixture(report):
    P = report["fixtures"]["pooled"]
    if not P or not P["any"]:
        pytest.skip("the committed fixtures carry no split yet")
    assert re.match(r"(Purane users roz \(sab \d+ apps\): [+−]?\d+% \(|\d+ apps ke purane users roz \(\d+ me se\): [+−]?\d+% \("
                    r"|Purane users roz: installs ka hissa pata nahi \(\d+ me se \d+ apps ka hisaab\)$)", P["text"]), P["text"]
    if "pata nahi" in P["text"]:                                                   # one short line, one colon
        assert len([w for w in P["text"].split() if re.search(r"[A-Za-z]", w)]) <= 14 and P["text"].count(":") == 1
    # the apps it counts are the tile's own ("15 of 16 apps" → "(16 me se …" / "(sab 16 apps)")
    ok = re.search(r"(\d+) of (\d+) apps", P["ret"])
    got = re.search(r"\((?:sab )?(\d+)(?: me se| apps)", P["text"])
    assert ok and got and ok.group(1) == got.group(1), (P["ret"], P["text"])


def test_the_split_switch_off_draws_exactly_the_old_page(report):
    """SPLIT=false writes every sp as null: every screen is byte for byte what a file without any sp draws — no block,
    no one-line form, the old Installs lines back."""
    S = report["switch_off"]
    assert S["screens"] > 30 and S["differ"] == 0 and S["splits"] == 0
