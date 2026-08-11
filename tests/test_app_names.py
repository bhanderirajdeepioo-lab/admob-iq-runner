"""Duplicate AdMob app names get a disambiguating tag, so alerts/movers trace to the right app."""

from admob_iq.build_static import _DisambiguatedRepo
from admob_iq.engine.roas import build_roas


class _FakeRepo:
    def __init__(self, rows, nested=None):
        self._rows, self._nested_ = rows, nested or {}

    def fetch_network(self):
        return list(self._rows)

    def fetch_mediation(self):
        return list(self._rows)

    def fetch_adunit_country_daily(self):
        return dict(self._nested_)

    def has_data(self):
        return True


def _row(app_id, name, account):
    return {"app_id": app_id, "app_name": name, "account_id": account, "estimated_earnings_micros": 1}


def test_duplicate_names_get_account_tag_unique_names_untouched():
    rows = [
        _row("ca-app-pub-1111111111111111~aaa", "Gallery", "pub-1111111111111111"),
        _row("ca-app-pub-2222222222222222~bbb", "Gallery", "pub-2222222222222222"),
        _row("ca-app-pub-1111111111111111~ccc", "Calculator", "pub-1111111111111111"),   # unique
    ]
    w = _DisambiguatedRepo(_FakeRepo(rows))
    out = {r["app_id"]: r["app_name"] for r in w.fetch_network()}
    assert out["ca-app-pub-1111111111111111~aaa"] == "Gallery · pub-1111…"
    assert out["ca-app-pub-2222222222222222~bbb"] == "Gallery · pub-2222…"
    assert out["ca-app-pub-1111111111111111~ccc"] == "Calculator"        # unique name left alone
    assert len(set(out.values())) == 3                                   # every name now unique


def test_friendly_account_name_used_when_configured():
    """config/account_names.json turns "Gallery · pub-1111…" into "Gallery · Helsy Main"."""
    rows = [
        _row("ca-app-pub-1111111111111111~aaa", "Gallery", "pub-1111111111111111"),
        _row("ca-app-pub-2222222222222222~bbb", "Gallery", "pub-2222222222222222"),
    ]
    names = {"pub-1111111111111111": "Helsy Main", "pub-2222222222222222": "Perfect Win"}
    out = {r["app_id"]: r["app_name"] for r in _DisambiguatedRepo(_FakeRepo(rows), names).fetch_network()}
    assert out["ca-app-pub-1111111111111111~aaa"] == "Gallery · Helsy Main"
    assert out["ca-app-pub-2222222222222222~bbb"] == "Gallery · Perfect Win"


def test_missing_account_name_falls_back_to_pub_id():
    """A partially-filled account_names.json must still produce unique names."""
    rows = [
        _row("ca-app-pub-1111111111111111~aaa", "Gallery", "pub-1111111111111111"),
        _row("ca-app-pub-2222222222222222~bbb", "Gallery", "pub-2222222222222222"),
    ]
    out = {r["app_id"]: r["app_name"]
           for r in _DisambiguatedRepo(_FakeRepo(rows), {"pub-1111111111111111": "Helsy Main"}).fetch_network()}
    assert out["ca-app-pub-1111111111111111~aaa"] == "Gallery · Helsy Main"
    assert out["ca-app-pub-2222222222222222~bbb"] == "Gallery · pub-2222…"    # fallback
    assert len(set(out.values())) == 2


def test_same_name_same_account_falls_back_to_app_id():
    rows = [
        _row("ca-app-pub-1111111111111111~900111", "Test App", "pub-1111111111111111"),
        _row("ca-app-pub-1111111111111111~900222", "Test App", "pub-1111111111111111"),
    ]
    w = _DisambiguatedRepo(_FakeRepo(rows))
    names = [r["app_name"] for r in w.fetch_network()]
    assert len(set(names)) == 2                                          # still disambiguated
    assert all(n.startswith("Test App · ") for n in names)


def test_nested_adunit_country_units_also_renamed():
    rows = [
        _row("ca-app-pub-1111111111111111~aaa", "Gallery", "pub-1111111111111111"),
        _row("ca-app-pub-2222222222222222~bbb", "Gallery", "pub-2222222222222222"),
    ]
    nested = {"units": {"u1": ["ca-app-pub-1111111111111111~aaa", "banner_1", "Gallery", "USD"]},
              "data": {"u1": []}}
    w = _DisambiguatedRepo(_FakeRepo(rows, nested))
    assert w.fetch_adunit_country_daily()["units"]["u1"][2] == "Gallery · pub-1111…"


def test_custom_name_replaces_admob_name_everywhere():
    """The pencil on the App Report screen writes {app_id: name} — it wins over AdMob's own name."""
    rows = [
        _row("ca-app-pub-1111111111111111~aaa", "Gallery", "pub-1111111111111111"),
        _row("ca-app-pub-2222222222222222~bbb", "Gallery", "pub-2222222222222222"),
        _row("ca-app-pub-1111111111111111~ccc", "Calculator", "pub-1111111111111111"),
    ]
    nested = {"units": {"u1": ["ca-app-pub-1111111111111111~aaa", "banner_1", "Gallery", "USD"]},
              "data": {"u1": []}}
    custom = {"ca-app-pub-1111111111111111~aaa": "Gallery Main",
              "ca-app-pub-1111111111111111~ccc": "My Calculator"}   # unique name, renamed anyway
    w = _DisambiguatedRepo(_FakeRepo(rows, nested), None, custom)
    out = {r["app_id"]: r["app_name"] for r in w.fetch_network()}
    assert out["ca-app-pub-1111111111111111~aaa"] == "Gallery Main"     # no account tag: unique now
    assert out["ca-app-pub-2222222222222222~bbb"] == "Gallery"           # the clash is gone with it
    assert out["ca-app-pub-1111111111111111~ccc"] == "My Calculator"
    assert w.fetch_adunit_country_daily()["units"]["u1"][2] == "Gallery Main"   # history follows


def test_custom_name_that_still_clashes_keeps_the_account_tag():
    rows = [
        _row("ca-app-pub-1111111111111111~aaa", "Gallery", "pub-1111111111111111"),
        _row("ca-app-pub-2222222222222222~bbb", "Photos", "pub-2222222222222222"),
    ]
    custom = {"ca-app-pub-1111111111111111~aaa": "Photos"}            # renamed INTO a collision
    out = {r["app_id"]: r["app_name"]
           for r in _DisambiguatedRepo(_FakeRepo(rows), {"pub-1111111111111111": "Acme"}, custom).fetch_network()}
    assert out["ca-app-pub-1111111111111111~aaa"] == "Photos · Acme"
    assert out["ca-app-pub-2222222222222222~bbb"] == "Photos · pub-2222…"
    assert len(set(out.values())) == 2


def test_blank_and_unknown_custom_names_are_ignored():
    rows = [_row("ca-app-pub-1111111111111111~aaa", "Gallery", "pub-1111111111111111")]
    custom = {"ca-app-pub-1111111111111111~aaa": "", "ca-app-pub-9999999999999999~zzz": "Ghost App"}
    w = _DisambiguatedRepo(_FakeRepo(rows), None, custom)
    assert [r["app_name"] for r in w.fetch_network()] == ["Gallery"]
    assert w._map == {}                                              # nothing stale carried over


def test_rename_candidates_tracks_where_a_name_went():
    rows = [
        _row("ca-app-pub-1111111111111111~aaa", "Gallery", "pub-1111111111111111"),
        _row("ca-app-pub-2222222222222222~bbb", "Gallery", "pub-2222222222222222"),
        _row("ca-app-pub-1111111111111111~ccc", "Calculator", "pub-1111111111111111"),
    ]
    w = _DisambiguatedRepo(_FakeRepo(rows), None, {"ca-app-pub-1111111111111111~aaa": "Gallery Main"})
    assert w.rename_candidates("Gallery") == ["Gallery", "Gallery Main"]   # renamed one + untouched
    assert w.rename_candidates("Calculator") == ["Calculator"]               # never renamed


def test_roas_alias_survives_a_custom_rename():
    """An alias points at the AdMob name. Rename that app from the dashboard and its ENTIRE
    marketing spend would fall into 'unmatched' unless the alias follows the rename."""
    spend = {"daily": {"photo.vault.lockgallery": {"2026-07-20": 5_000_000}},
             "campaigns": {}, "currency_src": "INR", "fx": {"INR": 0.01}}
    rows = [
        _row("ca-app-pub-1111111111111111~aaa", "Gallery", "pub-1111111111111111"),
        _row("ca-app-pub-2222222222222222~bbb", "Gallery", "pub-2222222222222222"),
    ]
    w = _DisambiguatedRepo(_FakeRepo(rows), None, {"ca-app-pub-1111111111111111~aaa": "Gallery Main"})
    catalog = [{"app_id": "ca-app-pub-1111111111111111~aaa", "app_name": "Gallery Main", "rev": 2_392_013},
               {"app_id": "ca-app-pub-2222222222222222~bbb", "app_name": "Gallery", "rev": 9_410}]
    # build_static hands build_roas the alias resolved through rename_candidates
    aliases = {"photo.vault.lockgallery": w.rename_candidates("Gallery")}
    r = build_roas(spend, {}, catalog, aliases=aliases)
    assert "Gallery Main" in r["by_app"]           # highest-revenue candidate wins
    assert r["unmatched_spend_usd"] == 0


def test_roas_alias_still_resolves_after_rename():
    """An alias written against the PLAIN app name must still attribute spend once the name has
    been disambiguated — otherwise the aliased app's whole spend falls back to 'unmatched'."""
    spend = {"daily": {"photo.vault.lockgallery": {"2026-07-20": 5_000_000}},
             "campaigns": {}, "currency_src": "INR", "fx": {"INR": 0.01}}
    catalog = [{"app_id": "app-a", "app_name": "Gallery · pub-6124…", "rev": 2_392_013},
               {"app_id": "app-b", "app_name": "Gallery · pub-2117…", "rev": 9_410}]
    r = build_roas(spend, {}, catalog, aliases={"photo.vault.lockgallery": "Gallery"})
    assert "Gallery · pub-6124…" in r["by_app"]          # highest-revenue match wins
    assert r["unmatched_spend_usd"] == 0
