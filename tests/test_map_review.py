"""Review regressions for the map's generated, JavaScript-free page."""

import re
import unittest

from pipeline.money import map_page


class MapDefaultYearReviewTest(unittest.TestCase):
    def test_default_year_is_the_latest_with_the_default_measure(self):
        # Arrange: newer-year pupils are published before the deficit percentage.
        measures = map_page.build_measures({
            "england": {
                "name": "England",
                "by_year": {
                    "2024-25": {"all": {"in_deficit_pct": 12.0}},
                    "2025-26": {"all": {"in_deficit_pct": None}},
                },
                "pupils_by_year": {"2024-25": 1000.0, "2025-26": 1001.0},
            },
        })
        self.assertEqual(measures["years"], ["2024-25", "2025-26"])

        # Act: use the same body builder as write_pages, with no external data.
        html = map_page.map_body(
            measures, {}, has_councils=False, has_constituencies=False
        )

        # Assert: the map opens on the latest year that has the default measure, never on a blank map (2025-26 has
        # council-run returns only, so area measures stop at 2024-25); a later year stays selectable by hand.
        default_year = re.search(r'data-default-year="([^"]*)"', html).group(1)
        label = re.search(r'for="mx-year">([^<]*)</output>', html).group(1)
        self.assertEqual(default_year, "2024-25")
        self.assertEqual(label, "2024-25")
        self.assertIn("2025-26", measures["years"])
