"""The school page compares a parents' association with England's and its council's in one well-covered year."""

import re
import unittest
from html import unescape

from pipeline.money import school_page, series, status, timeline
from pipeline.money.test_school_page import make_ctx, make_item, section
from pipeline.money.test_series import charity, row

# William Patten-like: £48,547 in the year to August 2025 (2024-25) over 437.5 pupils = £111 per pupil.
ROWS = [row(y, pupils=437.5) for y in ("2022-23", "2023-24", "2024-25")] + [row("2025-26", pupils=432.5)]
PTA = [charity(1103834, [("2025-08", 48_547, 50_000), ("2024-08", 33_000, 37_000)])]
NATIONAL = {"by_year": {"2023-24": {"schools": 7568, "median_pp": 40.6}, "2024-25": {"schools": 7608, "median_pp": 43.2},
                        "2025-26": {"schools": 1126, "median_pp": 49.3}}}  # 2025-26: early filers only
COUNCIL = {"name": "Hackney", "by_year": {"2024-25": {"all": {"pta_schools": 11, "pta_pp_median": 76.4}}}}


def ptfa_text(**over):
    item = make_item(pta=PTA)
    item.update(rows=ROWS, latest=ROWS[-1], status=status.assess(ROWS))
    ctx = make_ctx(item, series.school_series(ROWS, PTA), timeline=timeline.status_by_year(ROWS), **over)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", section(school_page.render(item, ctx)["body"], "ptfa"))))


class PtaComparisonTest(unittest.TestCase):
    def test_england_is_compared_in_this_ptas_year_never_a_part_filed_one(self):
        # Act
        text = ptfa_text(pta_national=NATIONAL)
        # Assert: 2024-25 (this PTA's latest year), not 2025-26 (1,126 early filers)
        self.assertIn("raised £43 per pupil in 2024-25", text)
        self.assertNotIn("2025-26", text.split("Across England", 1)[1])
        self.assertIn("raised about two and a half times that in the same school year", text)

    def test_the_council_comparison_says_how_this_pta_compares_locally(self):
        # Act
        text = ptfa_text(pta_national=NATIONAL, council=COUNCIL)
        # Assert: £111 against Hackney's £76
        self.assertIn("In Hackney, the typical registered parents' association raised £76 per pupil in 2024-25 "
                      "(11 schools with a registered one).", text)
        self.assertIn("This school's raised about half as much again as that.", text)

    def test_without_a_council_median_there_is_no_local_sentence(self):
        text = ptfa_text(pta_national=NATIONAL, council={"name": "Hackney", "by_year": {}})
        self.assertNotIn("In Hackney", text)


if __name__ == "__main__":
    unittest.main()
