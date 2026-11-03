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
    assert set(a["reads"]) == {"C", "U", "UC", "UCT", "UCTD", "FCD", "C1", "UC1", "UCK1", "UN1", "C7", "UC7"}
    assert all(r["ok"] for r in a["reads"].values())
    for k in ("UC", "UCT", "UCTD", "FCD", "UC1", "UN1", "UC7"):        # (UCK1: this fake ignores the country filter)
        r = a["reads"][k]
        assert all(abs(v - 1.0) < 1e-9 for v in r["tie"].values()), (k, r["tie"])
        assert all(t["w2"] == 1.0 and t["off2"] == 0 for t in r["keys"].values()), (k, r["keys"])
    assert a["reads"]["UC"]["ukeys"]["totalAdRevenue"]["keys"] == len(UNITS)
    e = a["ecpm"]                                          # nothing folded: what GA4 keeps has the true eCPMs
    assert e["unit"]["keys"] == len(UNITS) and e["unit"]["w2"] == 1.0 and e["country"]["med"] == 0
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


def test_ecpm_check_counts_only_big_keys_and_weights_by_impressions():
    true = {("u1", "new"): [20.0, 10000.0], ("u2", "new"): [30.0, 30000.0], ("u3", "new"): [1.0, 500.0]}
    kept = {("u1", "new"): [10.0, 5000.0], ("u2", "new"): [32.4, 30000.0], ("u3", "new"): [9.0, 100.0]}
    c = nc.ecpm_check(kept, true)                          # u1 exact (half kept), u2 8 % off, u3 too small to count
    assert c["keys"] == 2 and c["w2"] == 0.25 and c["w5"] == 0.25 and c["w10"] == 1.0 and c["med"] == 0.08

