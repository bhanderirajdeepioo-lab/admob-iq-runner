"""The app-icon second chance (admob_iq.fetch.app_icons.fill_icons_from_store_ids): an app the first icon pass marked
"none" for good (its store listing was not linked yet) gets its icon from the store id resolved LATER
(data/app_store_ids.json) — by app_id, never by name; cached per store id; a miss waits before it is asked again; capped
per build; failure-isolated; the log line is counts only. Synthetic ids / packages / URLs only; no network (the store
lookup is a stub)."""

import json
import os
import re

from admob_iq.fetch import app_icons as ai

A1, A2, A3, A4, A5 = ("demo-app~%d" % n for n in (1, 2, 3, 4, 5))
PKG = {A1: "com.example.first", A2: "com.example.twin", A3: "com.example.third", A4: "12345678", A5: "not a package"}
CAT = [{"app_id": A1, "app_name": "Demo One", "rev": 900, "selected": True},
       {"app_id": A2, "app_name": "Demo One", "rev": 5, "selected": True},          # the same name as A1
       {"app_id": A3, "app_name": "Demo Three", "rev": 50},
       {"app_id": A4, "app_name": "Demo Four", "rev": 40},
       {"app_id": A5, "app_name": "Demo Five", "rev": 30}]
URL = "https://icons.example.test/%s.png"


def _stub(found, calls):
    def resolve(sid, platform):
        calls.append((sid, platform))
        return (URL % sid) if sid in found else None
    return resolve


def test_fills_a_missing_icon_from_its_own_store_id_and_caches_it(tmp_path):
    calls = []
    icons = {A1: URL % "a1"}
    out, c = ai.fill_icons_from_store_ids(icons, CAT, PKG, str(tmp_path), resolve=_stub({"com.example.twin", "12345678"}, calls), now=1000)
    assert out[A1] == URL % "a1"                                  # an app that has its icon is never touched (nor looked up)
    assert out[A2] == URL % "com.example.twin"                    # the same-named twin gets ITS OWN listing's icon
    assert out[A4] == URL % "12345678" and A3 not in out and A5 not in out
    assert icons == {A1: URL % "a1"}                              # the input is not changed
    assert ("12345678", "IOS") in calls and ("com.example.twin", "ANDROID") in calls
    assert all(sid != "com.example.first" and sid != "not a package" for sid, _ in calls)
    assert c == {"missing": 4, "filled": 2, "looked_up": 3, "found": 2, "unresolved": 1, "waiting": 0, "no_store_id": 1}
    cache = json.load(open(os.path.join(str(tmp_path), "store_id_icons.json")))
    assert cache["v"] == 1 and cache["by_sid"]["com.example.third"] == {"u": "", "t": 1000}
    calls.clear()                                                 # the next build: from the cache, no lookups
    out2, c2 = ai.fill_icons_from_store_ids(icons, CAT, PKG, str(tmp_path), resolve=_stub(set(), calls), now=2000)
    assert calls == [] and out2 == out and c2["filled"] == 2 and c2["waiting"] == 1 and c2["looked_up"] == 0


def test_a_miss_waits_then_is_asked_again(tmp_path):
    calls = []
    d = str(tmp_path)
    ai.fill_icons_from_store_ids({}, CAT[2:3], PKG, d, resolve=_stub(set(), calls), now=1000)
    ai.fill_icons_from_store_ids({}, CAT[2:3], PKG, d, resolve=_stub(set(), calls), now=1000 + 86400)
    assert len(calls) == 1                                        # a day later: still waiting
    out, c = ai.fill_icons_from_store_ids({}, CAT[2:3], PKG, d, resolve=_stub({"com.example.third"}, calls),
                                          now=1000 + 8 * 86400)   # past the week: asked again, the listing is there now
    assert len(calls) == 2 and out[A3] == URL % "com.example.third" and c["found"] == 1


def test_capped_per_build_and_the_apps_on_screen_go_first(tmp_path):
    calls = []
    many = [{"app_id": "id-%02d" % i, "app_name": "Demo %d" % i, "rev": i, "selected": i == 3} for i in range(30)]
    sids = {"id-%02d" % i: "com.example.app%02d" % i for i in range(30)}
    out, c = ai.fill_icons_from_store_ids({}, many, sids, str(tmp_path), resolve=_stub(set(), calls), now=5, max_lookups=4)
    assert c["looked_up"] == 4 and c["waiting"] == 26 and len(calls) == 4
    assert calls[0][0] == "com.example.app03"                     # the selected app first, then by revenue
    assert [s for s, _ in calls[1:]] == ["com.example.app29", "com.example.app28", "com.example.app27"]


def test_never_raises_and_never_takes_a_bad_url(tmp_path):
    def boom(sid, platform):
        raise RuntimeError("network down")
    out, c = ai.fill_icons_from_store_ids({A1: URL % "a1"}, CAT, PKG, str(tmp_path), resolve=boom, now=1)
    assert out == {A1: URL % "a1"} and c["unresolved"] == 3
    out, _ = ai.fill_icons_from_store_ids({}, CAT[2:3], PKG, str(tmp_path / "x"), resolve=lambda s, p: "javascript:alert(1)", now=1)
    assert out == {}
    open(os.path.join(str(tmp_path), "store_id_icons.json"), "w").write("{not json")          # a broken cache is ignored
    out, c = ai.fill_icons_from_store_ids({}, CAT[2:3], PKG, str(tmp_path), resolve=_stub({"com.example.third"}, []), now=1)
    assert out == {A3: URL % "com.example.third"}
    out, c = ai.fill_icons_from_store_ids(None, None, None, str(tmp_path), resolve=boom, now=1)   # nothing to do
    assert out == {} and c["missing"] == 0
    out, c = ai.fill_icons_from_store_ids({A1: "u"}, "not a list", 7, str(tmp_path))            # junk input → as it was
    assert out == {A1: "u"}


def test_the_log_line_is_counts_only(tmp_path):
    _, c = ai.fill_icons_from_store_ids({}, CAT, PKG, str(tmp_path), resolve=_stub({"com.example.twin"}, []), now=1)
    line = ai.fill_counts_line(c)
    assert line.startswith("app icons from store ids: 5 missing, 1 filled (1 new), 4 looked up, 3 still none, ")
    assert not re.search(r"ca-app|pub-|com\.|example|Demo|https?:", line)
    assert ai.fill_counts_line({"failed": 1}).endswith("(failed)")


def test_the_build_runs_it_after_the_main_icon_pass_isolated():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "admob_iq", "build_static.py"),
               encoding="utf-8").read()
    i, j = src.index("resolve_app_icons(accounts, data_dir"), src.index("fill_icons_from_store_ids(")
    k = src.index("# ROAS: Google Ads (MCC) marketing spend")
    assert i < j < k
    blk = src[j - 400:k]
    assert "dashboard.get(\"app_store_ids\")" in blk and "print(fill_counts_line(_ic), file=sys.stderr)" in blk
    assert "except Exception as e:\n            print(f\"app icons from store ids skipped: {type(e).__name__}\"" in blk
