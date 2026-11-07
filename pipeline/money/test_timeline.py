"""Offline tests for the year-by-year status timeline."""
import unittest

from pipeline.money import timeline


def row(urn, end, income, spend, reserve, source="CFR", pupils=300, **extra):
    year = f"{int(end[:4]) - 1}-{end[2:4]}" if source == "CFR" else f"{int(end[:4]) - 1}/{end[2:4]}"
    r = {"urn": urn, "year": year, "period_end": end, "source": source, "la": 204, "phase": "primary",
         "period_months": 12, "pupils": pupils, "total_income": income, "total_expenditure": spend,
         "in_year_balance": income - spend, "revenue_reserve": reserve}
    r.update(extra)
    return r


class StatusByYearTest(unittest.TestCase):
    def test_three_years_give_three_entries_oldest_first(self):
        # Arrange: healthy, then overspending into a tight year, then into deficit
        rows = [row("1", "2025-03", 2_000_000, 2_150_000, -50_000),
                row("1", "2023-03", 2_000_000, 1_900_000, 200_000),
                row("1", "2024-03", 2_000_000, 2_100_000, 100_000, pupils=250)]
        # Act
        points = timeline.status_by_year(rows)
        # Assert
        self.assertEqual([p["year"] for p in points], ["2022-23", "2023-24", "2024-25"])
        self.assertEqual([p["status"] for p in points], ["large_reserves", "healthy", "in_deficit"])
        self.assertEqual(points[1]["reserve"], 100_000)
        self.assertEqual(points[1]["reserve_pp"], 400)   # that year's 250 pupils, not a later count
        self.assertEqual(points[1]["pupils"], 250)
        self.assertEqual(points[2]["label"], "In deficit")

    def test_status_as_of_each_year_ignores_later_rows(self):
        # Arrange: two years of overspending with a small reserve make the latest year "heading"
        rows = [row("1", "2023-03", 2_000_000, 2_000_000, 300_000),
                row("1", "2024-03", 2_000_000, 2_100_000, 200_000),
                row("1", "2025-03", 2_000_000, 2_100_000, 100_000)]
        # Act
        points = timeline.status_by_year(rows)
        # Assert
        self.assertEqual(points[0]["status"], "large_reserves")
        self.assertEqual(points[-1]["status"], "heading_for_deficit")

    def test_academy_years_use_dash_labels_and_trust_share(self):
        # Arrange
        rows = [row("1", "2024-08", 2_000_000, 1_950_000, 50_000, source="AAR"),
                row("1", "2025-08", 2_000_000, 1_950_000, 90_000, source="AAR", revenue_reserve_incl_trust_share=120_000, pupils=400)]
        # Act
        points = timeline.status_by_year(rows)
        # Assert
        self.assertEqual([p["year"] for p in points], ["2023-24", "2024-25"])
        self.assertEqual(points[-1]["reserve"], 120_000)
        self.assertEqual(points[-1]["reserve_pp"], 300)

    def test_part_year_and_missing_rows_are_skipped(self):
        # Arrange
        rows = [row("1", "2024-03", 2_000_000, 1_900_000, 100_000, period_months=7),
                row("1", "2025-03", 2_000_000, 1_900_000, 100_000, pupils=None)]
        # Act
        points = timeline.status_by_year(rows)
        # Assert
        self.assertEqual(len(points), 1)
        self.assertIsNone(points[0]["reserve_pp"])
        self.assertEqual(timeline.status_by_year([]), [])


if __name__ == "__main__":
    unittest.main()
