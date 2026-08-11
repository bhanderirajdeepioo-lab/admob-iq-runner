"""App-icon resolution: maps app_id → real store URL, caches, and never re-fetches a known app.
The live HTTP (iTunes / Play) runs only in the robot; here we mock resolve_icon and list_apps."""

import os
from admob_iq.fetch import app_icons, fetcher


def test_resolve_app_icons_maps_and_caches(monkeypatch, tmp_path):
    class _C:
        def __init__(self, aid): self.aid = aid
        def list_apps(self):
            return [{"app_id": "ca-app-pub-1~A", "platform": "ANDROID", "store_id": "com.x.a", "name": "App A"},
                    {"app_id": "ca-app-pub-1~B", "platform": "IOS", "store_id": "123", "name": "App B"}]

    monkeypatch.setattr(fetcher, "make_client", lambda a, *x, **k: _C(a["account_id"]))
    calls = []
    monkeypatch.setattr(app_icons, "resolve_icon", lambda sid, plat: "http://icon/" + str(sid))
    # count real invocations via a wrapper
    real = app_icons.resolve_icon
    monkeypatch.setattr(app_icons, "resolve_icon", lambda sid, plat: (calls.append(sid) or real(sid, plat)))

    catalog = [{"app_id": "ca-app-pub-1~A", "app_name": "App A"},
               {"app_id": "ca-app-pub-1~B", "app_name": "App B"}]
    d = str(tmp_path)
    icons = app_icons.resolve_app_icons([{"account_id": "pub-1"}], d, catalog,
            client_id="x", client_secret="y", currency="USD", make_client=fetcher.make_client, mode="live")
    assert icons["ca-app-pub-1~A"] == "http://icon/com.x.a"
    assert icons["ca-app-pub-1~B"] == "http://icon/123"
    assert set(calls) == {"com.x.a", "123"}
    assert os.path.exists(os.path.join(d, "app_icons.json"))          # cache persisted

    calls.clear()                                                    # re-run → all cached → no fetches
    icons2 = app_icons.resolve_app_icons([{"account_id": "pub-1"}], d, catalog,
            client_id="x", client_secret="y", currency="USD", make_client=fetcher.make_client, mode="live")
    assert calls == []
    assert icons2 == icons


def test_resolve_icon_is_safe_on_empty():
    assert app_icons.resolve_icon(None, "ANDROID") is None
    assert app_icons.resolve_icon("", "IOS") is None


def test_list_apps_failure_is_best_effort(monkeypatch, tmp_path):
    """A report-only token (list_apps raises) must not crash — just yields no icons for that account."""
    class _Boom:
        def list_apps(self): raise Exception("403 admob.readonly required")
    monkeypatch.setattr(fetcher, "make_client", lambda a, *x, **k: _Boom())
    monkeypatch.setattr(app_icons, "resolve_icon", lambda sid, plat: ("http://icon" if sid else None))
    out = app_icons.resolve_app_icons([{"account_id": "pub-1"}], str(tmp_path),
            [{"app_id": "ca-app-pub-1~A", "app_name": "A"}],
            client_id="x", client_secret="y", currency="USD", make_client=fetcher.make_client, mode="live")
    assert out == {}                                                 # no crash, no icons
