"""A federation lead's combined return counts the whole federation's pupils; its parents' association is one school's.

So no parents' association per-pupil figure is ever made from a federation year: not on the school page, in the
council medians, or (test_build_money, test_wrapped_js, test_deck_js) the nearby table, video and decks.
"""

import re
import unittest

from pipeline.money import areas, school_page, series, status, timeline
from pipeline.money.test_school_page import Figures, make_ctx, make_item, section
from pipeline.money.test_series import charity, federation_rows, row

PTA = [charity(1084738, [("2025-08", 25_000, 11_440), ("2024-08", 20_770, 21_485)])]


def render(rows, pta):
    item = make_item(pta=pta)
    item.update(rows=rows, latest=rows[-1], status=status.assess(rows))
    ctx = make_ctx(item, series.school_series(rows, pta), timeline=timeline.status_by_year(rows))
    return school_page.render(item, ctx)["body"]


class SchoolPageTest(unittest.TestCase):
    def test_the_ptfa_section_shows_totals_without_a_per_pupil_figure(self):
        # Arrange: Grazebrook-like, every year a federation lead's combined return (~1,750 pupils)
        rows = federation_rows()
        # Act
        ptfa = section(render(rows, PTA), "ptfa")
        # Assert: £25,000 is shown, never over the federation's pupils, and the page says why
        figures = Figures(ptfa).figures
        self.assertTrue(any(f.get("data-v") == "25000" for f in figures))
        self.assertEqual([f for f in figures if "data-pp" in f and f.get("data-mf", "").startswith("pta")], [])
        self.assertIn("covers its whole federation", re.sub(r"\s+", " ", ptfa))

    def test_a_school_outside_a_federation_keeps_its_per_pupil_figure(self):
        # Arrange
        rows = [row(y) for y in ("2022-23", "2023-24", "2024-25")]
        # Act
        ptfa = section(render(rows, PTA), "ptfa")
        # Assert: £25,000 over the same year's 200 pupils
        self.assertTrue(any(f.get("data-v") == "25000" and f.get("data-pp") == "125" for f in Figures(ptfa).figures))
        self.assertNotIn("covers its whole federation", ptfa)


class NearbyCellTest(unittest.TestCase):
    def test_a_federation_leads_pta_cell_shows_its_total_alone(self):
        # Arrange: build_money's nearby row for a federation lead: PTA year and income, no pta_pp
        entry = {"pta_year": "2024-25", "pta_income": 25_000, "federation": "New Wave Federation", "pupils": 1749.5}
        # Act
        cell = school_page._nb_money("pta_income", entry, "pta_pp", "pta_year", "2025-26")
        # Assert
        self.assertIn('data-v="25000"', cell)
        self.assertNotIn("data-pp", cell)
        self.assertIn("no per-pupil figure for a federation", cell)

    def test_a_row_without_pta_money_stays_a_dash(self):
        self.assertEqual(school_page._nb_money("pta_income", {"pupils": 300}, "pta_pp", "pta_year", "2025-26"), "—")


class CouncilMediansTest(unittest.TestCase):
    def test_a_federation_year_adds_no_pta_per_pupil_to_the_medians(self):
        # Arrange
        fed, own = federation_rows(), [dict(r, federated=None) for r in federation_rows()]
        # Act
        fed_years = {e["year"]: e for e in areas.school_years(fed, PTA)}
        own_years = {e["year"]: e for e in areas.school_years(own, PTA)}
        # Assert
        self.assertIsNone(fed_years["2024-25"]["pta_pp"])
        self.assertEqual(round(own_years["2024-25"]["pta_pp"]), round(25_000 / 1793.5))


if __name__ == "__main__":
    unittest.main()
