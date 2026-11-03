"""GA4 first session vs returning × country probe (admob_iq.fetch.ga4_nvrcc_probe) — offline against the nvr probe's small
fake GA4 (SYNTHETIC: made-up countries, ad formats, ad units and money): every read answers and ties to its truth and
country by country, the top countries come from C, and the PUBLIC log stays counts-only."""
import re

from admob_iq.fetch import ga4
from admob_iq.fetch import ga4_nvrcc_probe as nc
from tests.test_ga4_device_probe import RT, SECRETS, TOK, unit
from tests.test_ga4_nvr_probe import CC, NOW, UNITS, FakeGA


def _run(monkeypatch, fake):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    return nc.run_probe([unit()], "cid", "sec", [("o", RT)], {"app_calls": 50}, now=NOW)


def test_reads_tie_whole_and_country_by_country(monkeypatch, capsys):
    rep = _run(monkeypatch, FakeGA())
    a = list(rep["apps"].values())[0]
    assert a["complete"] and a["top"] == len(CC)
    assert set(a["reads"]) == {"C", "U", "UC", "UCT", "UCTD", "FCD"} and all(r["ok"] for r in a["reads"].values())
    for k in ("UC", "UCT", "UCTD", "FCD"):
        r = a["reads"][k]
        assert all(abs(v - 1.0) < 1e-9 for v in r["tie"].values()), (k, r["tie"])
        assert all(t["w2"] == 1.0 and t["off2"] == 0 for t in r["keys"].values()), (k, r["keys"])
    assert a["reads"]["UC"]["ukeys"]["totalAdRevenue"]["keys"] == len(UNITS)
    lines = nc.public_lines(rep["counts"])
    out = capsys.readouterr().out + "\n".join(lines)
    for s in SECRETS + list(CC) + [u for _, u in UNITS]:
        assert s not in out
    assert all(re.fullmatch(r"nvrcc probe: (\w+ n \d+ ok \d+ refused \d+ tie<0\.98 \d+ other \d+|apps \d+, complete \d+, "
                            r"calls \d+, \d+s)", ln) for ln in lines), lines


def test_top_countries_skip_the_unknown_rows():
    rows = [{"countryId": "XA", "totalAdRevenue": 5}, {"countryId": "(other)", "totalAdRevenue": 50},
            {"countryId": "(not set)", "totalAdRevenue": 40}, {"countryId": "XB", "totalAdRevenue": 7},
            {"countryId": "XC", "totalAdRevenue": 0}]
    assert nc.top_countries(rows, 5) == ["XB", "XA"]
