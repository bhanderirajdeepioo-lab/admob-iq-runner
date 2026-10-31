"""GA4 device cohort probe (admob_iq.fetch.ga4_devcoh_probe) — offline against the device probe's fake GA4 (SYNTHETIC):
every read shape answers and ties to its truth, "(other)" lumping is measured, and the PUBLIC log stays counts-only."""
import re

from admob_iq.fetch import ga4_devcoh_probe as cp_
from tests.test_ga4_device_probe import NOW, RT, SECRETS, TOK, Fake, unit
from admob_iq.fetch import ga4


def _run(monkeypatch, fake):
    monkeypatch.setattr(ga4, "_call", fake)
    monkeypatch.setattr(ga4, "_sleep", lambda s: None)
    monkeypatch.setattr(ga4, "access_token", lambda cid, sec, rt: TOK)
    return cp_.run_probe([unit()], "cid", "sec", [("o", RT)], {"app_calls": 200}, now=NOW)


def test_reads_tie_and_public_log(monkeypatch, capsys):
    rep = _run(monkeypatch, Fake())
    a = list(rep["apps"].values())[0]
    assert a["complete"] and len(a["xs"]) == 3
    ties = [r["tie"] for k, r in a["reads"].items() if "tie" in r]
    assert ties and all(v == 1.0 for t in ties for v in t.values() if v is not None)
    kinds = {k.split("@")[0] for k in a["reads"]}
    assert {"T7", "MC7", "M7", "C7", "T30", "MC30", "D1T", "D1MC", "PT", "PMC"} <= kinds
    lines = cp_.public_lines(rep["counts"])
    out = capsys.readouterr().out + "\n".join(lines)
    for s in SECRETS:
        assert s not in out
    assert all(re.fullmatch(r"devcoh probe: (\w+ n \d+ ok \d+ refused \d+ tie<0\.98 \d+ other \d+|apps \d+, complete \d+, "
                            r"calls \d+, \d+s)", ln) for ln in lines), lines


def test_other_lumping_lowers_nothing_in_the_tie_but_is_flagged(monkeypatch):
    rep = _run(monkeypatch, Fake(lump=("XM-004", "XM-005")))
    c = rep["counts"]["kinds"]
    assert c["MC7"]["other"] == 3 and c["T7"]["other"] == 0
