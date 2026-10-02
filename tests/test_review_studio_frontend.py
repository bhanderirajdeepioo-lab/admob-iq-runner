"""🗂 Review Studio — the page side (frontend/index.html's RVS closure), run in node on a synthetic Studio file + card
document the REAL build code made (tests/review_studio_synth.py → the review store + the Studio step):

  * every app of the card is rendered — the map, the cards, the table, the drawer, the tooltips, Summary, History —
    with the owner's words (English labels, "Next step:", the button names) and never "100 me" / "/din";
  * every coloured box says what it is (the feature's name inside every map box and card box);
  * every action goes to the REAL API path with the older tab's own request body (POST JSON, same-origin), the state
    comes back from the answer, and a refusal shows the older tab's own message;
  * the older views: the old Review tab's own nodes move into "🗂 Old views" and come back in their order when there is
    no Studio file, the file fails to load, or the file is not this card's.
Prints nothing on success; tests/review_studio_frontend.js is the harness."""

import contextlib
import gzip
import io
import json
import os
import re
import shutil
import subprocess
from datetime import timedelta

import pytest

from admob_iq import build_static
from admob_iq.config import settings
from tests import review_studio_synth as ss
from tests import review_synth as rs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIDS = ["kamai", "uninstall", "active", "value", "update", "ads", "deduct", "mediation", "health", "setup"]
SHORT = ["Revenue", "Uninstall", "Active", "Value", "Update", "Ads", "Deduct", "Mediation", "Health", "Setup"]
DS = rs.DAY.isoformat()
PD = (rs.DAY - timedelta(1)).isoformat()          # a PAST review day (History)


def _past_state():
    """A synthetic GET day answer for the past day PD: 4 apps reviewed (one with a note, one 🔁, one whole-app 🚩), 3
    pending; the Worker says an admin may write it (History's admin fixes)."""
    K, at = rs.K, f"{PD}T05:00:00.000Z"
    st = lambda s, who: {"st": s, "who": who, "at": at, "snz": []}
    flag = {"id": 901, "day": PD, "app": K[2], "app_label": "", "feature": None, "note": "Synthetic flag", "raised_by": rs.OWNER,
            "raised_at": at, "status": "open", "decision": None, "dec_note": None, "dec_by": None, "dec_at": None,
            "done_note": None, "done_by": None, "done_at": None, "wd_by": None, "wd_at": None}
    return {"d": PD, "open_day": DS, "writable": True, "rev": 9,
            "states": {K[1]: st("ok", rs.TEAM), K[3]: st("kal", rs.OWNER), K[8]: st("ok", rs.TEAM), K[2]: st("flag", rs.OWNER)},
            "notes": [{"id": 900, "app": K[8], "text": "Old note — synthetic", "who": rs.TEAM, "at": at}],
            "flags": [flag], "snoozes": [], "prev": None,
            "log": [{"id": 9, "at": at, "who": rs.TEAM, "act": "ok", "app": K[1], "feature": None, "note": None, "ref": None, "extra": None}]}


def _script(tmp):
    html = open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()
    js = max(re.findall(r"<script>([\s\S]*?)</script>", html), key=len)
    p = os.path.join(tmp, "page.js")
    with open(p, "w", encoding="utf-8") as f:
        f.write(js)
    return p


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    tmp = str(tmp_path_factory.mktemp("rsfe"))
    site, data, dash = ss.make(tmp)
    with contextlib.redirect_stderr(io.StringIO()):
        assert build_static._review_studio_step(dash, data, site, dict(settings()), now=rs.NOW) == ["/review/*"]
    with open(os.path.join(site, "review", "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    with gzip.open(os.path.join(data, "review", "days", f"{DS}.json.gz"), "rt", encoding="utf-8") as f:
        day = json.load(f)
    with gzip.open(os.path.join(site, "review", "studio", f"{DS}.json.gz"), "rt", encoding="utf-8") as f:
        studio = json.load(f)
    K = rs.K
    fx = {"index": index, "day": day, "studio": studio, "state": rs.daystate(rs.DAY),
          "me": {"email": "owner@example.test", "admin": True, "open_day": DS, "go_live": index["go_live"],
                 "server_time": f"{DS}T05:30:00.000Z"},
          "keys": {"ok": K[1], "kal": K[2], "note": K[8], "imp": K[5], "feat": K[1], "f": "kamai", "pend": K[3]},
          "past": {"day": PD, "state": _past_state(), "pend": K[5], "noted": K[8]}}
    fp = os.path.join(tmp, "fx.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(fx, f, ensure_ascii=False)
    r = subprocess.run(["node", os.path.join(ROOT, "tests", "review_studio_frontend.js"), _script(tmp), fp],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout)
    out["_fx"] = fx
    return out


def test_no_errors_and_the_functions_exist(report):
    assert report["errors"] == []
    assert all(v == "function" for k, v in report["fns"].items() if k != "RVS") and report["fns"]["RVS"] == "object"


def test_layout_studio_on_top_and_the_old_tab_folded_whole(report):
    assert report["order0"] == [" rv-head", "rv-tabs", "rv-bans", "rv-v-today", "rv-v-sum", "rv-v-hist", "rv-toast"]
    ld = report["loading"]
    assert ld["on"] and not ld["ready"] and ld["st"] == "load" and "Review Studio load ho raha hai" in ld["html"]
    L = report["layout"]
    assert L["on"] and L["rson"]
    assert L["order"] == ["rv-bans", "rs-root", "rs-old", "rv-toast"]          # banners + toast stay visible
    assert L["fold"] == ["SUMMARY:", "DIV:rs-oldin"]
    assert L["folded"] == [" rv-head", "rv-tabs", "rv-v-today", "rv-v-sum", "rv-v-hist"]


def test_every_app_is_rendered_in_every_view(report):
    fx, H = report["_fx"], report["html"]
    keys = [a["key"] for a in fx["day"]["apps"]]
    assert sorted(a["key"] for a in report["apps"]) == sorted(keys) and len(keys) == 7
    assert not any(a["raw"] for a in report["apps"])
    for k in keys:
        assert f'data-rsgo="{k}"' in H["map"] and f'id="rs-c-{k}"' in H["list"] and f'data-key="{k}"' in H["table"]
        for f in FIDS:
            assert f'data-tk="cell:{k}:{f}"' in H["map"] and f'data-rsgo="{k}:{f}"' in H["list"]
            assert f'id="rs-fb-{f}"' in H["drawers"][k]
    for a in report["apps"]:                                                    # the name always with its account
        assert re.search(r'<span class="rs-nmt">' + re.escape(a["name"]) + r"(?: <span class=\"rs-tagw\">[^<]+</span>)? <span class=\"rs-acn\">· "
                         + re.escape(a["acct"]), H["map"])
    assert "rs-v-today" in H["root"] and "rv-card" not in H["root"] and "data-rvact" not in H["root"]
    for t in ("Today's review", "Summary", "History", "Cards frozen", "Revenue till", "Final till", "Next cards"):
        assert t in H["root"], t


def test_every_box_says_what_it_is(report):
    H = report["html"]
    boxes = re.findall(r'<button type="button" class="rs-hc [^"]+"[^>]*>(.*?)</button>', H["map"])
    assert len(boxes) == 7 * 10
    for i, b in enumerate(boxes):
        assert b.startswith(f'<span class="rs-cl" aria-hidden="true">{SHORT[i % 10]}</span>'), b
    strips = re.findall(r'<button type="button" class="rs-fc [^"]+"[^>]*>(.*?)</button>', H["list"])
    assert len(strips) == 7 * 10 and all('<span class="rs-flb">' in s for s in strips)


def test_the_owners_words(report):
    H = report["html"]
    every = "".join([H["root"], H["map"], H["hero"], H["list"], H["table"], H["sum"], H["hist"], H["frtips"], report["inr"]]
                    + list(H["drawers"].values()) + list(H["tips"].values()))
    for bad in ("100 me", "/din", "per 1,000", "har 1,000", "Har 1,000", "Bigda", "Dhyan do", "Kal dobara dekho",
                "Wapas lo", "Poora card kholo"):
        assert bad not in every, bad
    for good in ("✅ Got it · Reviewed", "📝 Note", "🚩 Important · Re-review", "🔁 Check again tomorrow",
                 "Open full card ›", "Next step:", "Same day uninstall", "Worse", "Watch", "Better", "Normal",
                 "Too early", "N/A", "🕒 Came", "📊 ", "Needs a look", "Small apps", "Feature map"):
        assert good in every, good
    assert "↩ Undo" in H["list"]                                               # (the cards with a review already)
    for d in H["drawers"].values():
        assert "Open in dashboard:" in d and "Revenue · eCPM" in d
    assert "₹" in report["inr"] and "$" not in re.sub(r"<[^>]*>", "", report["inr"]).replace("$/", "")
    # Summary (admin): the decision buttons; History: the calendar of the review days
    assert all(d in H["sum"] for d in ("👍 Fine · close", "🛠 Assign fix", "⛔ Stop")) and "Admin list" in H["sum"]
    assert f'data-rsday="{DS}"' in H["hist"] and "Who did what" in H["hist"]


def _bodies(r):
    return [x["body"] for x in r["req"]]


def test_every_action_hits_the_api_with_the_older_tabs_request(report):
    K = report["_fx"]["keys"]
    for name in ("r_ok", "r_kal", "r_note", "r_imp", "r_undo", "r_fflag", "r_unflag", "r_snz", "r_unsnz", "r_bulk", "r_dec"):
        for x in report[name]["req"]:
            assert x["method"] == "POST" and x["ct"] == "application/json" and x["cred"] == "same-origin", (name, x)
            assert x["url"] in ("/api/review/action", "/api/review/decide"), (name, x)
    assert _bodies(report["r_ok"]) == [{"d": DS, "app": K["ok"], "act": "ok", "live": True}]
    assert report["r_ok"]["st"] == "ok" and report["r_ok"]["toast"].startswith("✅ Reviewed — ")
    assert report["r_ok_again"] == {"req": [], "toast": "Pehle se reviewed hai"}
    assert _bodies(report["r_kal"]) == [{"d": DS, "app": K["kal"], "act": "kal", "live": True}] and report["r_kal"]["st"] == "kal"
    assert _bodies(report["r_note"]) == [{"d": DS, "app": K["note"], "act": "note", "note": "Synthetic note <b>x</b>", "live": True}]
    assert report["r_note"]["st"] == "note" and report["r_note"]["pnl"] is None
    assert report["r_note_empty"] == {"req": [], "toast": "Note khaali hai"}
    assert _bodies(report["r_imp"]) == [{"d": DS, "app": K["imp"], "act": "flag", "feature": None, "note": "Admin dekho", "live": True}]
    assert report["r_imp"]["st"] == "flag" and report["r_imp"]["toast"].startswith("🚩 Sent for re-review — ")
    assert report["r_ok_flagged"]["req"] == [] and report["r_ok_flagged"]["toast"].startswith("🚩 Ye card Re-review me hai")
    assert _bodies(report["r_undo"]) == [{"d": DS, "app": K["imp"], "act": "undo", "live": True}] and report["r_undo"]["st"] == "pend"
    assert _bodies(report["r_fflag"]) == [{"d": DS, "app": K["feat"], "act": "flag", "feature": "kamai", "note": "Sirf ye", "live": True}]
    assert ["kamai", "open"] in report["r_fflag"]["flags"]
    (b,) = _bodies(report["r_unflag"])
    assert b == {"d": DS, "app": K["feat"], "act": "unflag", "flag_id": b["flag_id"], "feature": "kamai", "live": True}
    assert ["kamai", "withdrawn"] in report["r_unflag"]["flags"]
    assert _bodies(report["r_snz"]) == [{"d": DS, "app": K["feat"], "act": "snooze", "feature": "kamai", "days": 14, "note": "Pata hai", "live": True}]
    assert report["r_snz"]["eff"] == "snz" and report["r_unsnz"]["eff"] == "red"
    assert _bodies(report["r_unsnz"]) == [{"d": DS, "app": K["feat"], "act": "unsnooze", "feature": "kamai", "live": True}]
    (bk,) = _bodies(report["r_bulk"])
    assert bk["act"] == "bulk_ok" and bk["d"] == DS and bk["live"] is True and bk["apps"] and set(bk) == {"d", "act", "apps", "live"}
    dec = report["a_dec"]
    assert dec["empty"].startswith("Note zaroori hai") and dec["after_kaam"] == "kaam" and dec["after_done"] == "closed"
    assert _bodies(report["r_dec"]) == [{"flag_id": dec["id"], "decision": "kaam", "note": "Developer ko bolo"},
                                        {"flag_id": dec["id"], "decision": "done", "note": ""}]


def test_a_refusal_shows_the_older_tabs_message_and_changes_nothing(report):
    r = report["r_409"]
    assert len(r["req"]) == 1 and r["st"] == "kal" and r["toast"] == r["fail"]
    a = report["r_401"]
    assert len(a["req"]) == 1 and a["auth"] is False and a["canW"] is False
    assert report["r_ro"]["req"] == [] and report["r_ro"]["toast"] == "Login session khatam — page reload karo"


def test_the_old_views_come_back_exactly_without_a_studio_file(report):
    F = report["fallback"]
    order0 = report["order0"]
    assert F["noptr"] == {"on": False, "order": order0, "rson": False, "rs": False, "old": False}
    assert F["back"] is True and F["failed"] == {"on": False, "order": order0} and F["back2"] is True
    assert F["otherCard"] == {"on": False} and F["back3"] is True


def test_an_app_the_file_left_out_is_still_shown_from_its_card(report):
    r = report["raw"]
    assert r["n"] == 7 and r["raw"] and r["card"] and r["pill"] and r["map"] and r["drawer"]


# ── 📱 the mobile fixes (the Review tab's phone audit): the toast, the Studio's own view, typing, coming back, phone Back ──
def _css():
    return open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8").read()


def test_mobile_the_toast_never_catches_a_tap(report):
    html = _css()
    base, phone = re.findall(r"#rv-root \.rv-toast\{([^}]*)\}", html)[:2]
    assert "pointer-events:none" in base                                       # a tap goes to the button under it
    assert "bottom:calc(72px" in phone and "-webkit-line-clamp:2" in phone    # phone: where #btoast sits, above the tab bar
    assert report["toast_tap"] == {"shown": "✅ Reviewed — x", "afterTap": "", "freshKept": "Fresh"}


def test_mobile_the_studio_keeps_its_own_view(report):
    v = report["views"]
    assert v["afterOldSum"] == {"studio": "today", "old": "sum", "hash": "#review", "panel": True}
    assert v["afterOldHist"] == {"studio": "today", "old": "hist", "hash": "#review"}
    assert v["studioSum"] == {"studio": "sum", "old": "sum", "hash": "#review/summary", "panel": True}
    assert v["want"]["studio"] == "hist" and v["want"]["hash"].startswith("#review/history")
    assert v["allDone"]["studio"] == "today" and "Summary tab" in v["allDone"]["toast"]


def test_mobile_a_poll_never_rebuilds_the_box_being_typed_in(report):
    assert report["typing"] == {"typing": True, "held": True, "rendered": True}


def test_mobile_coming_back_to_review_keeps_the_place(report):
    assert report["backY"] == {"saved": 12345, "keep": True, "restoredTo": 12345, "otherView": False}


def test_mobile_the_full_card_closes_on_the_phones_back(report):
    # the dashboard's one Back mechanism (hbOv): one step per open card, ✕ takes it off, the phone's Back closes the card
    assert report["hist"] == ["push", "go-1", "push"]
    assert report["drawerBack"] == {"closedByBack": True, "lock": False, "stack": []}
    assert "history.pushState(" not in _css() and "hbOv('rs-drawer',true," in _css() and "hbDrop('rs-drawer')" in _css()


def test_mobile_phone_css_targets_and_layout():
    html = _css()
    phone = re.search(r"@container rs \(max-width:700px\)\{([\s\S]*?)\n\}", html).group(1)
    assert "#rs-root .rs-seg button[data-rscur]{min-width:40px" in phone and "#rs-root .rs-seg button,#rs-root .rs-fbar button,#rs-root .rs-btn.rs-sm{min-height:36px}" in phone
    assert '#rs-root .rs-seg[role="tablist"]{flex-wrap:nowrap' in phone
    assert "#rs-root .rs-tw{max-height:none" in phone and "td.rs-app{position:sticky" in phone
    assert "#rs-root .rs-tiles>.rs-tile:last-child:nth-child(odd){grid-column:1/-1}" in phone
    assert re.search(r"\.rs-st th button\{all:unset;box-sizing:border-box;[^}]*width:100%;min-height:36px", html)
    assert ".rs-hh.rs-hr{" in html and 'class="rs-hh rs-r"' not in html                          # no red "Yesterday vs usual"
    assert "#rs-list,#rs-map,#rs-old,#rs-dayw{scroll-margin-top:calc(var(--rs-jump,0px) + 8px)}" in html



# ── 📅 History: a PAST day — every app, who reviewed, that day's own card (read-only), the admin fixes ──────────────────
def test_history_past_day_lists_every_app_by_revenue_with_who_reviewed(report):
    H = report["h_day"]
    assert H["adm"] is True and H["known"] is True and H["studio"] is False   # no Studio file named for PD: the card's own text
    assert H["fetched"] == [f"review/days/{PD}.json.gz"]                       # that day's own card document only
    keys = [a["key"] for a in report["_fx"]["day"]["apps"]]
    assert sorted(H["keys"]) == sorted(keys) and H["k7"] == sorted(H["k7"], reverse=True)   # every app, revenue order
    h = H["html"]
    pos = [h.index(f'id="rs-hr-{k}"') for k in H["keys"]]
    assert pos == sorted(pos)
    assert "Reviewed by" in h and "team" in h and "owner" in h
    assert re.search(r'✅ Reviewed</span><b>4</b><small>of 7 apps', h) and re.search(r'⏳ Pending</span><b>3</b>', h)
    K, P = rs.K, report["_fx"]["past"]
    for k in keys:
        assert f'data-rshapp="{k}"' in h                                       # a tap opens that day's card
    assert "📝 <span class=\"rs-nt\">“Old note — synthetic”</span>" in h      # the note, with who / when (IST, date)
    assert re.search(r"✅ Reviewed by <b><span class=\"rv-who\"[^>]*>team</span></b> · \d+ Sept?, \d\d:\d\d IST", h)
    assert "🚩 Important · Re-review by" in h and "admin ka faisla baaki" in h
    for k in (rs.K[4], rs.K[5], rs.K[6]):                                       # the 3 pending: a labelled "⏳ Pending" box
        assert re.search(f'id="rs-hr-{k}"[\\s\\S]*?<span class="rs-pill rs-p-pend">⏳ Pending</span>', h), k
    # every coloured box says what it is
    for lab in ("✅ Reviewed · ", "📝 + note · ", "🚩 Important · ", "🔁 Tomorrow · ", "⏳ Pending · "):
        assert lab in h, lab
    # admin: ✅ (pending / 🔁 only), 📝 on every app, ↩ where there is something to undo, ✅ All pending
    assert h.count('data-rshact="note"') == 7 and h.count('data-rshact="ok"') == 4 and h.count('data-rshact="undo"') == 4
    assert f'data-rshbulk="{PD}"' in h and "✅ All pending (3)" in h
    assert "Old views" not in h and "data-rsoldday" not in h
    assert H["stack"] == ["rs-hday"]                                            # 📱 a past day = one Back step


def test_history_past_card_is_that_days_frozen_card_read_only(report):
    C, today = report["h_card"], report["h_day"]["today"]
    assert C["dday"] == PD and C["cx"] is True                                  # (the context is only swapped while drawing)
    h = C["html"]
    assert "PAST-ONLY card line" in h and "PAST-ONLY card line" not in today    # that day's card, never today's
    assert "🔒 Read-only" in h and "frozen card · read-only" in h and "charts nahi" in h
    for bad in ('data-rsact=', 'data-rsff=', 'data-rssnz=', 'id="rs-dw-note"', 'data-rsgolink=', 'data-rsdwnote='):
        assert bad not in h, bad
    assert report["h_render"] == {"dday": PD, "past": True, "view": "hist", "day": PD}   # survives a render (refresh / poll)
    B = report["h_back"]
    assert B["stack0"] == ["rs-hday", "rs-drawer"]
    assert B["card"] == {"drawer": None, "dday": None, "stack": ["rs-hday"]}  # Back: the card first …
    assert B["day"] == {"histDay": None, "stack": [], "view": "hist"}           # … then the day (the calendar again)
    assert report["hhist"][:2] == ["push", "push"]


def test_history_past_card_reads_that_days_studio_file_when_the_index_names_it(report):
    S = report["h_studio2"]
    assert S["studio"] is True and f"review/studio/{PD}.json.gz" in S["fetched"]
    assert "PAST-STUDIO line" in S["html"] and "charts nahi" not in S["html"]
    assert report["h_studio_other"] == {"studio": False, "hf": "none"}          # another card's file: not used


def test_history_admin_fixes_send_the_older_views_requests(report):
    K, P = rs.K, report["_fx"]["past"]
    for name in ("r_hok", "r_hnote", "r_hedit", "r_hundo", "r_hbulk"):
        for x in report[name]["req"]:
            assert x["method"] == "POST" and x["url"] == "/api/review/action" and x["ct"] == "application/json", (name, x)
            assert "live" not in x["body"] and x["body"]["d"] == PD, (name, x)   # an admin fix on THAT day, never the open one
    assert _bodies(report["r_hok"]) == [{"d": PD, "app": P["pend"], "act": "ok"}] and report["r_hok"]["st"] == "ok"
    assert "(admin fix)" in report["r_hok"]["toast"]
    assert report["r_hok_again"] == {"req": [], "toast": "Pehle se reviewed hai"}
    assert report["h_note_add"] == {"kind": "hnote", "mode": "add", "slot": f"rs-hps-{P['pend']}"}
    assert _bodies(report["r_hnote"]) == [{"d": PD, "app": P["pend"], "act": "note", "note": "Admin note — synthetic"}]
    E = report["h_note_edit"]
    assert E["mode"] == 900 and E["draft"] == "Old note — synthetic" and E["same"] == "Kuch badla nahi" and E["open"] is True
    assert "✏️ Edit: “Old note — synthetic”" in E["panel"] and "➕ Add a new note" in E["panel"]
    assert _bodies(report["r_hedit"]) == [{"d": PD, "app": P["noted"], "act": "note_edit", "note_id": 900, "note": "Old note — edited"}]
    assert report["r_hedit"]["notes"] == ["Old note — edited"]
    assert report["r_hundo0"]["req"] == []                                      # ↩: the in-page confirm first
    assert _bodies(report["r_hundo"]) == [{"d": PD, "app": P["noted"], "act": "undo"}] and report["r_hundo"]["st"] == "pend"
    B = report["h_bulk"]
    assert B["kind"] == "hbulk" and report["r_hbulk0"]["req"] == []             # ✅ All pending: the in-page confirm first
    assert B["keys"] == [k for k in B["order"] if k in B["keys"]] and "Yes, mark all" in B["panel"]
    (b,) = _bodies(report["r_hbulk"])
    assert b == {"d": PD, "act": "bulk_ok", "apps": B["keys"]} and report["r_hbulk"]["pend"] == 0
    assert "confirm(" not in re.search(r"const RVS=\(function\(\)\{([\s\S]*?)\n\}\)\(\);", _css()).group(1)


def test_history_a_teammate_sees_the_same_day_without_the_admin_buttons(report):
    T = report["h_team"]
    assert T["adm"] is False and report["r_hteam"]["req"] == []
    h = T["html"]
    assert "data-rshact" not in h and "data-rshbulk" not in h and "🔒 Ye din band ho chuka" in h
    assert all(f'data-rshapp="{a["key"]}"' in h for a in report["_fx"]["day"]["apps"])


# ── 📱 chart labels never overlap (the owner: key values printed on the charts — and readable on a phone) ──────────────
def test_chart_labels_never_overlap_at_any_width_and_keep_the_key_values(report):
    L = report["labels"]
    assert L["charts"] > 150 and L["texts"] > 1500                            # every chart of every card, 4 widths × ₹/$
    assert L["issues"] == [] and L["missing"] == []                           # no overlap, nothing outside, key values on
    for w in ("360", "375", "414"):                                           # a phone: short dates (no weekday) …
        assert all(not re.search(r"\b(?:Mo|Tu|We|Th|Fr|Sa|Su) \d", x) for x in L["xl"][w]), (w, L["xl"][w])
    assert any(re.search(r"\b(?:Mo|Tu|We|Th|Fr|Sa|Su) \d", x) for x in L["xl"]["1280"])     # … a wide screen: the full ones
    html = _css()
    assert "function LB(){" in html and "function xAxis(" in html and "function tw(" in html
