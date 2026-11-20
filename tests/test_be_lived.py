"""⚖️ Breakeven — the LIVED re-anchor (admob_iq.be_build LIVE_ON / BE_LIVED; owner, 20 Nov 2026: "yes"): once a day (or
a country row) has a final anchor, the shift anchors at its latest grid age whose cell is at least LIVED days old, read
as it is now; a younger day keeps no anchor; off: every file exactly as before it (digests worked out once with the
code this branch starts from). SYNTHETIC values only (apps "app~synth-…", countries AA … DH, the calendar 2030–2031)."""
import copy
import gzip
import json
import os
from datetime import timedelta

import pytest

from admob_iq import be_build as be
from tests import test_be_build as T
from tests import test_be_paid as P


R = T.R


def test_lived_cells_take_a_cell_only_lived_and_old_enough():
    X = T.TODAY.toordinal() - 9
    cum = [10.0 * (j + 1) for j in range(len(be.GRID))]
    fin = [9.0, 19.0] + [None] * (len(be.GRID) - 2)                         # (final reads differ from the latest)
    x = R(day=(T.TODAY - timedelta(days=9)).isoformat(), sp=100.0, cum=cum, fin=fin, obs=9)
    nw = T.TODAY.toordinal()
    got = be._lived_cells(x, nw)
    want = {a: (10.0 * (j + 1) if a + be.LIVED <= 9 else None) for j, a in enumerate(be.GRID)}
    want[0], want[1] = 9.0, 19.0                                              # (its final cells as they are)
    assert got == [want[a] for a in be.GRID]
    x.obs = 2                                                                 # a cell past its last observed age: none
    assert be._lived_cells(x, nw)[be.GRID.index(3)] is None


def test_the_anchor_moves_to_the_lived_cell_only_once_a_final_one_exists(monkeypatch):
    nw = T.TODAY.toordinal()
    cum = [10.0 * (j + 1) for j in range(len(be.GRID))]
    old = R(day=(T.TODAY - timedelta(days=be.CLAG + 5)).isoformat(), sp=100.0, cum=cum,
            fin=[10.0, 20.0] + [None] * (len(be.GRID) - 2), obs=be.CLAG + 5)
    a_lived = max(a for a in be.GRID if a + be.LIVED <= be.CLAG + 5)
    assert be._anchor_at(old, 360, nw) == (a_lived, cum[be.GRID.index(a_lived)] / 100.0)
    young = R(day=(T.TODAY - timedelta(days=be.CLAG - 1)).isoformat(), sp=100.0, cum=cum,
              fin=[None] * len(be.GRID), obs=be.CLAG - 1)
    assert be._anchor_at(young, 360, nw) is None                             # no final anchor yet: none (unshifted)
    monkeypatch.setattr(be, "LIVE_ON", False)
    assert be._anchor_at(old, 360, nw) == (1, 0.2)                           # off: the latest final one, as before


def test_a_lived_cell_needs_lived_days_not_final_days(monkeypatch):
    monkeypatch.setattr(be, "CLAG", 7)                                       # (production's final lag: 7 > LIVED)
    nw = T.TODAY.toordinal()
    cum = [10.0 * (j + 1) for j in range(len(be.GRID))]
    k = be.GRID.index(3) + 1
    x = R(day=(T.TODAY - timedelta(days=12)).isoformat(), sp=100.0, cum=cum, fin=cum[:k] + [None] * (len(be.GRID) - k),
          obs=12)
    a_lived = max(a for a in be.GRID if a + be.LIVED <= 12)
    assert a_lived > 3 and be._anchor_at(x, 360, nw) == (a_lived, cum[be.GRID.index(a_lived)] / 100.0)
    assert be.LIVED == 4                                                     # (the measured age)
    young = R(day=(T.TODAY - timedelta(days=6)).isoformat(), sp=100.0, cum=cum, fin=[None] * len(be.GRID), obs=6)
    assert be._lived_cells(young, nw)[be.GRID.index(2)] == cum[be.GRID.index(2)]
    assert be._anchor_at(young, 360, nw) is None                             # lived cells but no final one: none


D9 = (T.TODAY - timedelta(days=be.CLAG + 5)).isoformat()


def lived_world(tmp):
    """tests/test_be_build.py's world with one install day whose cells after age 1 are not final yet (df 2) in its All
    row and every country row, and earn 1.3 × from age 2 on: its final anchor is age 1, its lived one later (higher)."""
    site, data, dash = T.make(tmp)
    for fn in [f for f in os.listdir(site) if f.startswith("roi_%s" % T.KEYS["a"])]:
        p = os.path.join(site, fn)
        with gzip.open(p, "rt", encoding="utf-8") as f:
            b = json.load(f)
        rows = [b["rows"]] if "rows" in b else list(b["c"].values())
        for rs in rows:
            for r in rs:
                if r[0] == D9 and len(r) > 5:
                    r[5] = 2
                    r[4] = [v * (1.3 if a >= 2 else 1.0) for a, v in enumerate(r[4])]   # (its lived days earn more)
        with gzip.open(p, "wt", encoding="utf-8") as f:
            json.dump(b, f)
    return site, data, dash


def _day(site):
    with gzip.open(os.path.join(site, "be_%s.json.gz" % T.KEYS["a"]), "rt", encoding="utf-8") as f:
        return {x["d"]: x for x in json.load(f)["days"]}[D9]


def test_the_page_anchors_at_the_lived_cell_and_off_as_before(tmp_path, monkeypatch):
    log = []
    monkeypatch.setattr(be, "SAN_LOG", log)
    site, data, dash = lived_world(tmp_path / "on")
    P._go(copy.deepcopy(dash), data, site, {})
    on = _day(site)
    a_lived = max(a for a in be.GRID if a + be.LIVED <= be.CLAG + 5)
    judged = [e[1] for e in log if e[0] and e[0][1] == D9]
    assert judged and set(judged) == {a_lived}                               # the sanity check: the same anchor
    site2, data2, dash2 = lived_world(tmp_path / "off")
    P._go(copy.deepcopy(dash2), data2, site2, {"be_lived": False})
    off = _day(site2)
    assert be.LIVE_ON is True                                                # (the switch is the run's only)
    assert off["app"]["anc"] == 1 and on["app"]["anc"] == a_lived            # the app line: its lived age
    assert on["cty"] != off["cty"]                                           # (its countries too)


# sha256 (tests/test_be_paid._digest) of the step's outputs with BE_LIVED off on lived_world — worked out once with the
# code this branch starts from (its whole admob_iq loaded in place of this tree's, the same world and helpers) at
# GA4_FINAL_DAYS = 3 (the tests' pin)
OFF_BEFORE = "664b1657c862c042b3745454f28c1f03c876611fd50c5773995aa5261b6d9476"


def off_digest(tmp):
    site, data, dash = lived_world(tmp)
    paths, line, err = P._go(dash, data, site, {"be_lived": False})
    return P._digest(site, data, dash, paths, line, err)


def test_be_lived_off_is_every_output_byte_for_byte_as_before_it(tmp_path):
    if be.LAG != be.LAG0:
        pytest.skip("the digest was worked out at the tests' GA4_FINAL_DAYS (3)")
    assert off_digest(tmp_path) == OFF_BEFORE


@pytest.mark.parametrize("v,want", [(None, True), ("true", True), ("false", False), (" OFF", False), ("0", False)])
def test_be_lived_switch(monkeypatch, v, want):
    from admob_iq import config
    if v is None:
        monkeypatch.delenv("BE_LIVED", raising=False)
    else:
        monkeypatch.setenv("BE_LIVED", v)
    assert config.settings()["be_lived"] is want


def test_a_flip_takes_effect_on_the_next_build_with_the_same_caches(tmp_path):
    """The re-anchor is predict's only (fits and calibration never read it): no stamp — the build after a flip answers
    with it on the caches it finds, and off after on is byte for byte off after off."""
    def twice(tmp, first):
        site, data, dash = lived_world(tmp)
        P._go(copy.deepcopy(dash), data, site, first)
        a = _day(site)["app"]["anc"]
        paths, line, err = P._go(dash, data, site, {"be_lived": False})
        assert "refit no, calib no" in line                                  # (the caches as they were)
        return a, _day(site)["app"]["anc"], P._digest(site, data, dash, paths, line, err)
    a_lived = max(a for a in be.GRID if a + be.LIVED <= be.CLAG + 5)
    on1, off2, d1 = twice(tmp_path / "on_off", {})
    _, _, d2 = twice(tmp_path / "off_off", {"be_lived": False})
    assert (on1, off2) == (a_lived, 1) and d1 == d2
