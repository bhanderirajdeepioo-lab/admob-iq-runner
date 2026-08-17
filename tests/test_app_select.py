"""QA for the per-account app selection layer (which apps are kept / hidden)."""

from admob_iq.engine.app_select import (load_selection, app_visible, account_decided, selected_ids,
                                        load_known_accounts)


def test_new_account_opt_in_hidden_grandfathered_visible():
    """With a known-accounts set, an UNDECIDED grandfathered account stays visible but a brand-NEW
    account's apps default to HIDDEN (opt-in) — this stops a freshly-added account auto-bloating."""
    sel = {"accounts": {}}
    known = {"pub-old"}
    assert app_visible(sel, "pub-old", "app-a", known) is True    # grandfathered undecided → visible
    assert app_visible(sel, "pub-new", "app-a", known) is False   # brand-new undecided → hidden
    assert app_visible(sel, "pub-new", "app-a", None) is True     # opt-in disabled (no file) → visible (back-compat)
    sel2 = {"accounts": {"pub-new": {"decided": True, "selected": ["app-a"]}}}
    assert app_visible(sel2, "pub-new", "app-a", known) is True   # decided new account → its picks show
    assert app_visible(sel2, "pub-new", "app-b", known) is False


def test_load_known_accounts(tmp_path):
    assert load_known_accounts(str(tmp_path / "nope.json")) is None      # absent → None (opt-in off)
    p = tmp_path / "known.json"; p.write_text('{"accounts": ["pub-1", "pub-2"]}')
    assert load_known_accounts(str(p)) == {"pub-1", "pub-2"}
    p.write_text('["pub-3"]')                                            # bare list also accepted
    assert load_known_accounts(str(p)) == {"pub-3"}


def test_absent_account_all_visible():
    sel = {"accounts": {}}
    assert app_visible(sel, "pub-1", "app-a") is True          # undecided ⇒ everything shows
    assert account_decided(sel, "pub-1") is False
    assert selected_ids(sel, "pub-1") is None                  # None = undecided (fetch/show all)


def test_undecided_flag_all_visible():
    sel = {"accounts": {"pub-1": {"decided": False, "selected": ["app-a"]}}}
    assert app_visible(sel, "pub-1", "app-b") is True          # not decided yet ⇒ still all visible


def test_decided_hides_unselected():
    sel = {"accounts": {"pub-1": {"decided": True, "selected": ["app-a", "app-c"]}}}
    assert app_visible(sel, "pub-1", "app-a") is True
    assert app_visible(sel, "pub-1", "app-c") is True
    assert app_visible(sel, "pub-1", "app-b") is False         # not in the kept set ⇒ hidden
    assert account_decided(sel, "pub-1") is True
    assert selected_ids(sel, "pub-1") == {"app-a", "app-c"}


def test_decided_empty_hides_everything_for_that_account_only():
    sel = {"accounts": {"pub-1": {"decided": True, "selected": []}}}
    assert app_visible(sel, "pub-1", "app-a") is False         # explicitly kept nothing
    assert app_visible(sel, "pub-2", "app-a") is True          # a different account stays unaffected


def test_load_missing_is_empty(tmp_path):
    assert load_selection(str(tmp_path / "nope.json")) == {"accounts": {}}


def test_load_reads_file(tmp_path):
    p = tmp_path / "sel.json"
    p.write_text('{"accounts": {"pub-1": {"decided": true, "selected": ["x"]}}}', encoding="utf-8")
    sel = load_selection(str(p))
    assert app_visible(sel, "pub-1", "x") is True and app_visible(sel, "pub-1", "y") is False
