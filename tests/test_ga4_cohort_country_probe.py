"""The cohort-by-country probe: what one read measures (ages, named vs unnamed revenue, pairs, fold entries) and which
blocks it asks. Synthetic data only (this repo is public)."""
from datetime import date

from admob_iq.fetch import ga4_cohort_country_probe as cp


class FakeGa:
    def __init__(self, rows):
        self.rows, self.calls, self.tok, self.asked = rows, 0, 0, []

    def report_all(self, body, extra=None, page_rows=None, **k):
        self.calls += 1
        self.tok += 3
        self.asked.append((body, extra))
        dims = [d["name"] for d in body["dimensions"]]
        return [{k2: v for k2, v in r.items() if k2 in dims or k2 == "totalAdRevenue"} for r in self.rows]

    def truncated(self, rows):
        return False


ROWS = [  # activity day, install day, country, revenue
    {"date": "20261001", "firstSessionDate": "20261001", "countryId": "AA", "totalAdRevenue": "1.5"},   # age 0
    {"date": "20261001", "firstSessionDate": "20260920", "countryId": "BB", "totalAdRevenue": "2"},     # age 11
    {"date": "20261001", "firstSessionDate": "20260801", "countryId": "AA", "totalAdRevenue": "4"},     # age 61
    {"date": "20261001", "firstSessionDate": "20260801", "countryId": "(not set)", "totalAdRevenue": "0.5"},
    {"date": "20261001", "firstSessionDate": "(other)", "countryId": "CC", "totalAdRevenue": "3"},
    {"date": "20261001", "firstSessionDate": "20260815", "countryId": "BB", "totalAdRevenue": "1"},     # age 47
]


def test_early_read_keeps_ages_0_to_30_and_asks_the_in_list():
    ga = FakeGa(ROWS)
    m = cp.read(ga, date(2026, 10, 1), date(2026, 10, 1), ("date", "firstSessionDate", cp.DIM), early=True)
    assert m["rev"] == 3.5 and m["named"] == 3.5 and m["countries"] == 2 and m["pairs"] == 2
    assert m["unnamed_x"] == 3.0 and m["fold_entries"] == 0 and m["calls"] == 1 and m["tokens"] == 3
    assert ga.asked[0][1][0]["filter"]["fieldName"] == "firstSessionDate"


def test_late_read_keeps_ages_31_on_and_counts_fold_entries():
    ga = FakeGa(ROWS)
    m = cp.read(ga, date(2026, 10, 1), date(2026, 10, 1), ("date", "firstSessionDate", cp.DIM), early=False)
    assert m["rev"] == 5.5 and m["named"] == 5.0 and m["unnamed_cc"] == 0.5 and m["countries"] == 2
    assert m["fold_entries"] == 2 and ga.asked[0][1] is None              # every install day: no in-list


def test_blocks_newest_year_back_oldest():
    b = cp.blocks(date(2024, 1, 1), date(2026, 10, 20))
    assert b["newest"] == (date(2026, 9, 17), date(2026, 10, 16))
    assert b["year_back"][1] == date(2025, 10, 20) and b["oldest"][0] == date(2024, 2, 1)
    young = cp.blocks(date(2026, 8, 1), date(2026, 10, 20))
    assert set(young) == {"newest"}


def test_public_line_is_counts_only():
    assert cp.public_line(cp.counts({})).startswith("cohort country probe: apps 0")
