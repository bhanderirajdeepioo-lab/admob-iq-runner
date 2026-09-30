"""The Review tab's frontend (frontend/index.html), its pure functions rendered for real: tests/review_frontend.js runs
the page's own script in a node vm on the committed synthetic fixture (tests/fixtures/review_sample.json — the card
document written by admob_iq.review, index.json, a synthetic GET day response and /me) and calls the §C.11 functions.
Checked here: every §C.11 function and the RV_TXT strings of §C.12 exist exactly; no Devanagari and none of the demo's
old strings anywhere in the page; the layout rules of §C.5 (an open 🚩 — raised today or earlier — and yesterday's "kal
dobara dekho" lift a card, 🆕 comes first, a snoozed red feature drops out of the top, a 🛠 kaam flag does NOT lift; with no
state the client order equals the build's order); rich text is escaped and money follows the ₹/$ toggle exactly like
the demo; a card has 10 dots, 🚩 on flagged dots and the exact button labels, history cards have no action buttons;
the admin list shows only for an admin; the calendar colours and the chart SVG. Mandatory as soon as the page has the
Review screen (data-screen="review"); skipped before that ("frontend not landed") and where node is not installed."""

import json
import os
import re
import shutil
import subprocess

import pytest

from tests import review_synth as rs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.environ.get("REVIEW_FE_FIXTURE") or rs.FIXTURE
NODE = shutil.which("node")
K = rs.K
RV_TXT = {
    "nav": "Review", "title": "Daily Review", "sub": "Har din har app ka ek card · team review",
    "tab_today": "Aaj ka review", "tab_sum": "Summary", "tab_hist": "History",
    "b_ok": "✅ Got it · Reviewed", "b_note": "📝 Note", "b_imp": "🚩 Important · Re-review",
    "imp_help": "Admin dobara dekhega — faisla hone tak ye card upar focus me rahega",
    "st_imp": "🚩 Re-review (Important)", "sum_imp": "🚩 Important · Re-review", "adm_list": "🚩 Re-review list",
    "b_kal": "🔁 Kal dobara dekho", "kal_help": "Khud kal dobara dekhna hai — admin ko nahi jaata", "b_snz": "💤 Pata hai…",
    "b_undo": "↩ Wapas lo", "b_all": "✅ Sab reviewed", "st_pend": "⏳ Baaki", "st_ok": "✅ Reviewed",
    "st_note": "📝 Reviewed + note", "st_kal": "🔁 Kal dobara dekho", "d_theek": "👍 Theek hai", "d_kaam": "🛠 Kaam do",
    "d_band": "⛔ Band karo", "d_done": "✅ Kaam ho gaya", "poori": "Poori app", "not_started": "Review abhi shuru nahi hua",
    "api_down": "Buttons abhi band hain — review server se jud nahi paaye. Cards dekh sakte ho.",
    "auth_gone": "Login session khatam — page reload karo", "save_fail": "❌ Save nahi hua — {msg}. Dobara try karo.",
    "flag_block": "🚩 Ye card Re-review me hai — admin ke faisle tak aise hi rahega. Hatana ho to ↩ Wapas lo.",
    "hist_red": "⏳ Is din ka review baaki hai",
}
FNS = ("rvEsc", "rvRt", "rvMoney", "rvEffSt", "rvIsAttn", "rvLayout", "rvCardHtml", "rvSummaryHtml", "rvCalendarHtml",
       "rvDayColor", "rvChartSvg")
OLD = ("⚠️ Important — upar bhejo", "Important (upar bheja)", "udaharan", "Demo")
ACTIONS = (RV_TXT["b_ok"], RV_TXT["b_note"], RV_TXT["b_imp"], RV_TXT["b_kal"], RV_TXT["b_undo"], RV_TXT["b_snz"],
           RV_TXT["b_all"])
MONEY_USD = ["$166/din", "$3.46", "$12.5", "−$200/din", "+$200", "$3.5", "$1,235", "$100", "$2,000/din", "$200,000",
             "$0.50", "$0.0"]
MONEY_INR = ["₹14,626/din", "₹304", "₹1,100", "−₹17,600/din", "+₹17,600", "₹308", "₹1.1 lakh", "₹8,800", "₹1.8 lakh/din",
             "₹1.76 crore", "₹44.0", "₹0"]
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


@pytest.fixture(scope="module")
def html():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        h = f.read()
    if 'data-screen="review"' not in h:
        pytest.skip("frontend not landed")
    return h


@pytest.fixture(scope="module")
def fx():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def rep(html, tmp_path_factory):
    js = max(re.findall(r"<script>(.*?)</script>", html, re.S), key=len)
    path = str(tmp_path_factory.mktemp("rvfe") / "app.js")
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    subprocess.run([NODE, "--check", path], check=True, capture_output=True)
    out = subprocess.run([NODE, os.path.join(ROOT, "tests", "review_frontend.js"), path, FIXTURE],
                         check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)


def S(rep, name):
    assert name in rep["scen"], (name, rep["errors"])
    return rep["scen"][name]


def text(h):
    """Visible text of an HTML fragment (tags dropped, entities decoded, whitespace collapsed)."""
    t = re.sub(r"<[^>]+>", " ", h)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&#34;", '"'), ("&amp;", "&")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


def buttons(h):
    return [text(b) for b in re.findall(r"<button\b[^>]*>(.*?)</button>", h, re.S)]


def dots(h):
    m = re.search(r'<ul\b[^>]*aria-label="Features"[^>]*>(.*?)</ul>', h, re.S)
    assert m, "no <ul aria-label=\"Features\"> in the card"
    return m.group(1)


def test_every_contract_function_and_string_exists(rep):
    assert rep["errors"] == []
    for f in FNS:
        assert rep["fns"][f] == "function", f
    assert rep["rv_txt_type"] == "object"
    got = rep["RV_TXT"] or {}
    for k, v in RV_TXT.items():
        assert got.get(k) == v, (k, got.get(k), v)


def test_no_devanagari_and_no_old_demo_strings(html, rep):
    assert re.search(r"[ऀ-ॿ]", html) is None
    assert re.search(r"[ऀ-ॿ]", json.dumps(rep, ensure_ascii=False)) is None
    for s in OLD:
        assert s not in html, s


def test_layout_lifts_open_flags_and_kal_but_not_kaam_and_drops_snoozed(rep, fx):
    lay = S(rep, "layout")
    # a4 (kal), a5 (open 🚩 from yesterday) and a3 (open 🚩 raised TODAY) are lifted, a1 is 🆕 → first rank (upr 0) by
    # kamai; then a8
    assert lay["top"] == [K[4], K[3], K[1], K[5], K[8]]
    assert lay["ok"] == [K[2]]                     # its only red feature is snoozed → "Sab theek"
    assert lay["small"] == [K[6]]                  # a whole-app 🛠 kaam flag does not lift a small app
    empty = S(rep, "layout_empty")                  # no state → the build's own order
    assert empty == {g: fx["day"]["order"][g] for g in ("top", "ok", "small")}
    eff, attn, attn0 = S(rep, "eff"), S(rep, "attn"), S(rep, "attn_empty")
    assert eff[K[2]]["deduct"] == "snz" and eff[K[1]]["kamai"] == "red" and eff[K[3]]["uninstall"] == "amber"
    by = {a["key"]: a for a in fx["day"]["apps"]}
    for k, fs in eff.items():
        for f, st in fs.items():
            assert st == by[k]["f"][f]["st"] or (st == "snz" and (k, f) == (K[2], "deduct")), (k, f, st)
    assert attn[K[1]] is True and attn[K[2]] is False and attn[K[4]] is False and attn[K[3]] is True
    assert attn0[K[2]] is True and attn0[K[5]] is False


def test_rich_text_is_escaped_and_money_follows_the_toggle(rep):
    esc = S(rep, "esc")
    assert "<" not in esc and ">" not in esc and '"' not in esc and "&amp;" in esc and "&lt;img" in esc
    usd, inr, pl = S(rep, "rt_usd"), S(rep, "rt_inr"), S(rep, "rt_plain")
    for h in (usd, inr):
        assert "<img" not in h and "&lt;img" in h and 'class="rv-m"' in h and "data-usd" in h
    assert "$166/din" in usd and "−$200" in usd and "₹" not in usd
    assert "₹14,626/din" in inr and "−₹17,600" in inr and "$" not in inr
    assert "<b>" not in pl and "&lt;b&gt;bold&lt;/b&gt;" in pl
    assert S(rep, "money_usd") == MONEY_USD
    assert S(rep, "money_inr") == MONEY_INR


def test_cards_have_ten_dots_flags_on_flagged_dots_and_the_exact_buttons(rep, fx):
    live = S(rep, "cards_live")
    assert set(live) == {a["key"] for a in fx["day"]["apps"]}
    for k, h in live.items():
        d = dots(h)
        assert len(re.findall(r"<li\b", d)) == 10, k
    assert "🚩" in dots(live[K[5]]) and "Re-review" in dots(live[K[5]])      # open flag on Kamai · eCPM
    assert "🚩" in dots(live[K[3]])                                           # today's open flag on Uninstall
    assert "🚩" not in dots(live[K[4]]) and "🚩" not in dots(live[K[1]])
    c4 = live[K[4]]
    bt = buttons(c4)
    for lab in (RV_TXT["b_ok"], RV_TXT["b_note"], RV_TXT["b_imp"], RV_TXT["b_kal"], RV_TXT["b_undo"]):
        assert any(lab in b for b in bt), (lab, bt)
    assert 'role="checkbox"' in c4 and "aria-checked" in c4 and "aria-pressed" in c4
    assert RV_TXT["kal_help"] in c4
    assert "<img" not in c4 and "&lt;img" in c4                              # the team note is escaped
    assert RV_TXT["st_note"] in text(c4) and "kal dobara dekho” kaha tha" in text(c4)
    assert RV_TXT["st_kal"] in text(live[K[3]]) and RV_TXT["st_ok"] in text(live[K[2]])
    assert RV_TXT["st_pend"] in text(live[K[1]]) and "🆕 Naya aur bigda" in text(live[K[1]])
    t5 = text(live[K[5]])
    assert "Kamai · eCPM" in t5 and "din se khula" in t5 and "Synth Echo Editor - Pro" in t5
    assert "kaam chal raha" in text(live[K[6]])
    assert "💤" in text(live[K[2]])
    t1 = text(live[K[1]])
    for q in ("Kya hua", "Kab se", "Kitna bada", "Naya ya purana", "Kya karo"):
        assert q in t1, q
    assert "Detail:" in t1 and 'class="rv-m"' in live[K[1]]
    assert "₹" in S(rep, "cards_inr")
    for k, h in S(rep, "cards_empty").items():
        assert RV_TXT["st_pend"] in text(h), k


def test_history_cards_have_no_action_buttons(rep):
    for k, h in S(rep, "cards_history").items():
        for b in buttons(h):
            assert not any(a in b for a in ACTIONS), (k, b)
        assert 'role="checkbox"' not in h
        assert len(re.findall(r"<li\b", dots(h))) == 10
    for k, h in S(rep, "cards_history_admin").items():            # admin fix on a past day: ok / note / undo only
        for b in buttons(h):
            assert not any(a in b for a in (RV_TXT["b_imp"], RV_TXT["b_kal"], RV_TXT["b_snz"])), (k, b)


def test_summary_admin_list_only_for_admins(rep):
    adm, team = S(rep, "summary_admin"), S(rep, "summary_team")
    assert isinstance(S(rep, "summary_empty"), str)
    ta, tt = text(adm), text(team)
    assert RV_TXT["adm_list"] in ta and RV_TXT["adm_list"] not in tt
    for lab in (RV_TXT["d_theek"], RV_TXT["d_kaam"], RV_TXT["d_band"], RV_TXT["d_done"]):
        assert any(lab in b for b in buttons(adm)), lab
        assert not any(lab in b for b in buttons(team)), lab
    for h in (adm, team):
        t = text(h)
        assert RV_TXT["sum_imp"] in t and "Kamai · eCPM" in t and "Synth Echo Editor" in t
        assert "<img" not in h


def test_calendar_colours_and_charts(rep):
    assert S(rep, "daycolor") == ["green", "green", "amber", "red", "red", "none", "none", "green"]
    days = S(rep, "cal_days")
    assert len(days) == 3
    cal = S(rep, "calendar")
    assert "7/7 reviewed" in cal and "3/7 reviewed" in cal and "baaki" in cal
    assert cal.count('aria-pressed="true"') == 1 and cal.count("aria-pressed") >= 3
    assert S(rep, "calendar_sel").count('aria-pressed="true"') == 1
    charts = S(rep, "charts")
    assert len(charts) >= 3
    for svg in charts:
        assert svg.lstrip().startswith("<svg") and "NaN" not in svg and "undefined" not in svg


# ── review fixes ────────────────────────────────────────────────────────────────────────────────
def test_a_decided_whole_app_flag_no_longer_holds_the_card_in_re_review(rep):
    st = S(rep, "st_flag")
    assert st["open"] == "flag"
    assert st["decided"] == "ok" and st["decided_note"] == "note"
    card = st["card"]
    assert RV_TXT["st_ok"] in text(card) and RV_TXT["st_imp"] not in text(card)
    assert "Theek hai" in text(card)                                    # the log shows the admin's decision
    assert st["hist_later"] == "flag", "History of the flag's day: decided on a later day → still Re-review then"


def test_a_flag_raised_today_lifts_the_card_but_kaam_does_not(rep):
    lt = S(rep, "lift_today")
    assert lt["before"] == -1 and lt["after"] >= 0 and lt["kaam"] == -1


def test_small_app_chip_says_upar_laaya_only_when_the_card_is_on_top(rep):
    sc = S(rep, "small_chip")
    assert sc is not None, "the synthetic day has a small app with a new red feature"
    assert "🆕 Naya aur bigda" in text(sc["small"]) and "upar laaya" not in text(sc["small"])
    assert "upar laaya" in text(sc["lifted"])                           # a small app lifted by an open 🚩 is on top


def test_history_uses_the_review_day_of_a_decision(rep):
    h = S(rep, "hist_decday")
    assert h["same"] == "closed", "decided while the day was still open (before 09:00 IST next day) → decided that day"
    assert h["later"] == "open"
    assert "Theek hai" in text(h["log_same"]) and h["log_next"] == ""


def test_admin_band_list_keeps_14_review_days(rep):
    assert S(rep, "band") == 2


def test_a_newer_open_day_makes_the_live_view_read_only_and_live_writes_say_so(rep):
    n = S(rep, "newday")
    assert n["can0"] is True and n["older"] is None, "an OLDER open_day (stale cache) is not a new day"
    assert n["newer"] and n["can1"] is False and "Kholo" in n["msg"]
    assert n["poll"], "a poll that sees a newer open_day shows the new-day banner"
    assert n["live_body"]["live"] is True and n["live_body"]["act"] == "ok"
    assert "live" not in n["hist_body"], "History's admin correction is not a live write"


def test_an_unreachable_index_is_a_load_failure_not_review_not_started(rep):
    assert S(rep, "idx_net") == "fail" and S(rep, "idx_503") == "fail"      # offline / login redirect / server error
    assert S(rep, "idx_404") == "missing" and S(rep, "idx_empty") == "empty"  # → "Review abhi shuru nahi hua"
