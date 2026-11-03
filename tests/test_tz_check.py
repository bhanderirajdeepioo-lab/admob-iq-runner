"""admob_iq.tz_check — every time zone name the build's data uses must load on the build machine (1 Nov 2026: the
runner image lost the old alias names and every day-boundary number fell back to a guess with every build green).
Offline; the zone names are generic IANA names."""
import json
import os

from admob_iq import tz_check
from admob_iq.fetch import ga4_uninstall as gu
from admob_iq.fetch import google_ads


def test_the_old_alias_names_load_here_from_the_tzdata_package():
    # requirements.txt carries tzdata: zoneinfo falls back to it when the machine's zone files lack a name
    import importlib.resources
    import tzdata  # noqa: F401  (the package itself must be installed)
    assert importlib.resources.files("tzdata.zoneinfo").joinpath("Asia/Calcutta").is_file()
    assert tz_check.loads("Asia/Calcutta") and tz_check.loads("Etc/GMT+12") and not tz_check.loads("Mars/Olympus")


def test_names_from_every_source(tmp_path, monkeypatch):
    monkeypatch.setattr(google_ads, "ACCOUNT_TZ", {"America/New_York", ""})
    os.makedirs(tmp_path / gu.DIR)
    (tmp_path / gu.DIR / "state.json").write_text(json.dumps({"tz": {"p1": "Etc/GMT", "p2": None}}))
    got = tz_check.names("Asia/Calcutta", {"a1": "America/Los_Angeles", "a2": ""}, str(tmp_path))
    assert got == {"Asia/Calcutta", "America/Los_Angeles", "America/New_York", "Etc/GMT"}
    assert tz_check.names(None, None, str(tmp_path / "none")) == {"America/New_York"}     # a missing state: skipped


def test_a_name_that_does_not_load_puts_a_fault_on_the_page_and_counts_in_the_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(google_ads, "ACCOUNT_TZ", {"Mars/Olympus"})
    out = tmp_path / "zc.json"
    d = {"build_faults": [{"kind": "other"}]}
    assert tz_check.run(d, "Asia/Calcutta", {}, None, str(out)) == ["Mars/Olympus"]
    assert d["build_faults"] == [{"kind": "other"}, {"kind": "tz", "names": ["Mars/Olympus"], "of": 2}]
    assert json.loads(out.read_text()) == {"names": 2, "bad": 1}
    tz_check.public(str(out))
    line = capsys.readouterr().out
    assert line.startswith("::warning::zone check: 1 of 2 ") and "Mars" not in line              # counts only
    # every name loads again: the fault is cleared, the other one kept
    monkeypatch.setattr(google_ads, "ACCOUNT_TZ", {"America/New_York"})
    assert tz_check.run(d, "Asia/Calcutta", {}, None, str(out)) == []
    assert d["build_faults"] == [{"kind": "other"}]
    d2 = {"build_faults": [{"kind": "tz", "names": ["x"], "of": 1}]}
    tz_check.run(d2, "UTC")
    assert "build_faults" not in d2
    tz_check.public(str(out))
    assert capsys.readouterr().out.strip() == "zone check: 2 time zone name(s), all found"
    tz_check.public(str(tmp_path / "missing.json"))
    assert "no result" in capsys.readouterr().out


def test_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(tz_check, "names", boom)
    d = {}
    assert tz_check.run(d, "UTC") is None and d == {}
